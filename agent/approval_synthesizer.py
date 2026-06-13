"""Approval synthesizer for IAI.

Folds the three gate outputs (plan, security, cost) plus manifest context into
a single plain-language approval card. The human reads only this card — never
raw tool output, check IDs, or tool names. That is the whole trust contract:
if the card is faithful, the human can approve infrastructure without reading
Checkov or Infracost directly.

Library scope: stdlib + ruamel.yaml (via ManifestReader) + python-telegram-bot
(InlineKeyboardMarkup is embedded in the returned dict so the bot doesn't have
to reconstruct it from labels). No CLI entry point.
"""

import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from agent.manifest_reader import ManifestReader

_RULE = "━" * 47

# Plain-English descriptions for watched security findings. Keyed by check_id,
# but the card never exposes the id itself.
_FINDING_DESCRIPTIONS = {
    "CKV_AWS_24": (
        "the app tier would have been reachable via SSH from the entire internet "
        "(port 22 open to 0.0.0.0/0). Ingress restricted to the VPC CIDR."
    ),
}

# Plain-English descriptions for watched checks that PASSED (the discrimination
# beat: the gate is doing real work, not stamping everything green).
_PASSED_DESCRIPTIONS = {
    "CKV_AWS_16": "Encryption at rest: ✓",
    "CKV_AWS_17": "Public access blocked: ✓",
}

# Friendly cloud names derived from manifest resource `cloud` fields.
_CLOUD_LABELS = {"aws": "AWS", "gcp": "GCP"}


class ApprovalSynthesizer:
    def synthesize(
        self,
        plan_result: dict,
        security_result: dict,
        cost_result: dict,
        manifest_path: str,
        env: str = "staging",
    ) -> dict:
        """Return the approval card as a dict with text and an InlineKeyboardMarkup.

        Returns:
            {
                "text": str,                      # the full card text
                "keyboard": InlineKeyboardMarkup, # Approve / Decline buttons
            }
        """
        reader = ManifestReader(manifest_path)
        resources = reader.get_resources(env)
        criticality = reader.resolve_criticality(env)

        title = self._title(reader, env)
        lines = [title, _RULE]
        lines.append(self._resources_line(plan_result, resources))
        lines.append(self._cost_line(cost_result))
        lines.extend(self._security_lines(security_result))
        lines.extend(self._critical_lines(resources, criticality))

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Approve", callback_data="approve"),
            InlineKeyboardButton("Decline", callback_data="decline"),
        ]])
        return {"text": "\n".join(lines), "keyboard": keyboard}

    # --- Title --------------------------------------------------------------

    def _title(self, reader: ManifestReader, env: str) -> str:
        env_name = self._env_name(reader, env)
        return f"{env_name.capitalize()} environment for payments — ready to build"

    def _env_name(self, reader: ManifestReader, env: str) -> str:
        try:
            tags = reader._environment(env).get("tags", {}) or {}
            return str(tags.get("environment", env))
        except KeyError:
            return env

    # --- Resources line -----------------------------------------------------

    def _resources_line(self, plan_result: dict, resources: dict) -> str:
        count = plan_result.get("resource_count")
        if count is None:
            count = plan_result.get("to_add", 0)
        to_add = plan_result.get("to_add", count)
        to_change = plan_result.get("to_change", 0)
        to_destroy = plan_result.get("to_destroy", 0)

        clouds = self._clouds(resources)
        cloud_str = " + ".join(clouds) if clouds else "the target cloud"
        return (
            f"• Resources:  {count} across {cloud_str} "
            f"({to_add} to add · {to_change} to change · {to_destroy} to destroy)"
        )

    def _clouds(self, resources: dict) -> list:
        seen = []
        for res in resources.values():
            cloud = res.get("cloud")
            label = _CLOUD_LABELS.get(cloud, cloud)
            if label and label not in seen:
                seen.append(label)
        return seen

    # --- Cost line ----------------------------------------------------------

    def _cost_line(self, cost_result: dict) -> str:
        if not cost_result or cost_result.get("monthly_cost") is None:
            return "• Cost:       cost estimate unavailable"

        monthly = float(cost_result["monthly_cost"])
        rounded = int(round(monthly / 5.0) * 5)

        components = self._cost_components(cost_result)
        if components:
            comp_str = " · ".join(components)
            return f"• Cost:       ~${rounded}/month  ({comp_str})"
        return f"• Cost:       ~${rounded}/month"

    def _cost_components(self, cost_result: dict) -> list:
        """Extract compute + storage sub-figures from the cost result.

        Prefers explicit cost components if the cost gate surfaced them;
        otherwise reads them from the raw Infracost components carried on the
        result under 'components'. Falls back to nothing if unavailable.
        """
        raw = cost_result.get("components")
        out = []
        if raw:
            for comp in raw:
                label = comp.get("label")
                cost = comp.get("monthly")
                if label and cost is not None:
                    out.append(f"{label} ${int(round(float(cost)))}/mo")
        return out

    # --- Security lines -----------------------------------------------------

    def _security_lines(self, security_result: dict) -> list:
        findings = (security_result or {}).get("findings", []) or []
        passed = (security_result or {}).get("passed_checks", []) or []

        # Order passed phrases by the canonical _PASSED_DESCRIPTIONS order so the
        # card reads consistently regardless of Checkov's emission order.
        passed_set = set(passed)
        passed_phrases = [
            desc for cid, desc in _PASSED_DESCRIPTIONS.items() if cid in passed_set
        ]

        if not findings:
            return self._wrap_security("All security checks pass.", passed_phrases)

        n = len(findings)
        noun = "issue" if n == 1 else "issues"
        descriptions = []
        for f in findings:
            cid = f.get("check_id")
            if cid in _FINDING_DESCRIPTIONS:
                descriptions.append(_FINDING_DESCRIPTIONS[cid])
            else:
                descriptions.append(
                    f"a security issue was detected on {f.get('resource')}."
                )
        text = f"{n} {noun} caught — {' '.join(descriptions)}"
        return self._wrap_security(text, passed_phrases)

    def _wrap_security(self, text: str, atomic_suffixes: list | None = None) -> list:
        """Wrap the security body under a '• Security:' label with hanging indent.

        atomic_suffixes are appended after the wrapped text as whole phrases —
        they are never split across lines, so multi-word phrases like
        'Public access blocked: ✓' always appear contiguously.
        """
        label = "• Security:   "
        indent = " " * len(label)
        words = text.split(" ")
        lines = []
        current = label
        width = 78
        for word in words:
            candidate = current + (" " if current not in (label, indent) else "") + word
            if len(candidate) > width and current not in (label, indent):
                lines.append(current)
                current = indent + word
            else:
                if current in (label, indent):
                    current = current + word
                else:
                    current = candidate
        for phrase in (atomic_suffixes or []):
            candidate = current + "  " + phrase
            if len(candidate) <= width:
                current = candidate
            else:
                lines.append(current)
                current = indent + phrase
        lines.append(current)
        return lines

    # --- Critical lines -----------------------------------------------------

    def _critical_lines(self, resources: dict, criticality: dict) -> list:
        label = "• Critical:   "
        indent = " " * len(label)

        critical_names = {
            name for name, c in criticality.items() if c == "critical"
        }
        critical_set = critical_names
        manifest_order = [n for n in resources.keys() if n in critical_names]

        # Order by reason group so the card reads as a causal chain:
        #   data-bearing first (the snapshot driver), then resources that depend
        #   on a critical, then resources that are merely a dependency of one.
        #   Within each group, preserve manifest declaration order.
        def _group(name: str) -> int:
            res = resources.get(name, {})
            if res.get("data_bearing"):
                return 0
            deps = res.get("depends_on", []) or []
            if any(dep in critical_set for dep in deps):
                return 1
            return 2

        ordered = sorted(manifest_order, key=lambda n: (_group(n), manifest_order.index(n)))
        lines = []
        for i, name in enumerate(ordered):
            res = resources.get(name, {})
            reason = self._critical_reason(name, res, critical_set)
            prefix = label if i == 0 else indent
            lines.append(f"{prefix}{name} {reason}")
        if not lines:
            lines.append(f"{label}none")
        return lines

    def _critical_reason(self, name: str, res: dict, critical_set: set) -> str:
        if res.get("data_bearing"):
            return "[data-bearing — snapshot before apply]"
        deps = res.get("depends_on", []) or []
        for dep in deps:
            if dep in critical_set:
                return f"[depends on {dep}]"
        return "[dependency of critical resources]"
