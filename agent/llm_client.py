"""LLM client for IAI intent understanding.

The intent agent's reasoning layer. Given a plain-language request, it interprets
what the user wants *against the platform manifest* (the source of truth for what
exists and which engine owns it), decides an action, and — when the request is
ambiguous or under-specified — asks one clarifying question instead of guessing.
This is the IAI thesis in miniature: the agent reasons about intent; it does not
pattern-match keywords.

Provider-agnostic: a fast hosted API (Groq / Cerebras / any OpenAI-compatible
endpoint) or a local Ollama model, selected by environment. Always degrades
safely to a keyword passthrough so the pipeline still runs with no model
reachable (offline / CI / rate-limited) — the passthrough never asks for
clarification; it just routes provision vs. destroy so the demo cannot hard-fail.

Why hosted by default
---------------------
Local `phi` via Ollama took ~60-90s to parse one sentence — the slowest beat in
the demo. Groq's LPU returns the same JSON in well under a second on the free
tier. The API key is a *SaaS inference key* (GROQ_API_KEY), NOT a cloud
credential: infrastructure auth stays keyless (EC2 instance role + GCP Workload
Identity Federation). The LLM only reads the sentence; it never holds cloud
permissions.

Configuration (all via environment — never hard-code keys)
----------------------------------------------------------
    IAI_LLM_PROVIDER   groq | cerebras | openai | ollama | none   (default: auto)
                       auto = groq if GROQ_API_KEY is set, else ollama
    GROQ_API_KEY / CEREBRAS_API_KEY / OPENAI_API_KEY
    IAI_LLM_MODEL      override the per-provider default model
    IAI_MANIFEST       manifest path used to ground the reasoning (default manifest.yaml)
    OLLAMA_URL         default http://localhost:11434/api/generate
    OLLAMA_MODEL       default "phi"

Get a free Groq key (no credit card) at https://console.groq.com/keys, then:
    export IAI_LLM_PROVIDER=groq
    export GROQ_API_KEY=gsk_...
"""

import json
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

# Load .env from the repo root as early as possible, so the process reliably has
# IAI_LLM_PROVIDER / *_API_KEY / INFRACOST_API_KEY however it was launched (systemd,
# a bare shell, `python -m`, the Telegram service). Real environment variables
# (shell exports, systemd EnvironmentFile) are NOT overridden — they still win.
# dotenv is optional; without it the code falls back to the ambient environment.
try:
    from pathlib import Path
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:  # pragma: no cover
    logger.debug("python-dotenv not installed; relying on the ambient environment")

# OpenAI-compatible providers: name -> (base_url, api_key_env_NAME, default_model)
# The middle field is the NAME of the environment variable that holds the key —
# never the key itself. Keys live in the environment, not in source.
_OPENAI_COMPATIBLE = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile"),
    "cerebras": ("https://api.cerebras.ai/v1", "CEREBRAS_API_KEY", "llama3.1-8b"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-4o-mini"),
}

MANIFEST_PATH = os.environ.get("IAI_MANIFEST", "manifest.yaml")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "phi")

_HOSTED_TIMEOUT = 20          # seconds — hosted inference is sub-second
_OLLAMA_CONNECT_TIMEOUT = 3   # seconds — fail fast if Ollama isn't even listening
_OLLAMA_READ_TIMEOUT = 60     # seconds — local models are slow, but never hang for 2 min
_MANIFEST_MAX_CHARS = 4000    # keep the grounding context compact


def _resolve_provider(quiet: bool = False) -> str:
    """Pick the LLM provider from the environment.

    Explicit IAI_LLM_PROVIDER wins. Otherwise prefer whichever hosted key is
    present (fast), and only fall back to local Ollama as a last resort — LOUDLY,
    because Ollama is slow and silently defaulting to it is the classic
    "why is my demo hanging for two minutes" trap.
    """
    provider = os.environ.get("IAI_LLM_PROVIDER", "").strip().lower()
    if provider:
        return provider
    for name in ("groq", "cerebras", "openai"):
        if os.environ.get(_OPENAI_COMPATIBLE[name][1]):
            return name
    if not quiet:
        logger.warning(
            "No IAI_LLM_PROVIDER set and no hosted LLM key found — defaulting to "
            "local Ollama (slow; requires `ollama serve`). For fast inference set "
            "IAI_LLM_PROVIDER=groq and GROQ_API_KEY (see .env.example)."
        )
    return "ollama"


def active_config() -> str:
    """One-line summary of the resolved LLM config — log this at startup so a
    misconfiguration is visible immediately instead of as a slow failure."""
    provider = _resolve_provider(quiet=True)
    if provider in _OPENAI_COMPATIBLE:
        _, key_env, default_model = _OPENAI_COMPATIBLE[provider]
        model = os.environ.get("IAI_LLM_MODEL", default_model)
        key_state = "set" if os.environ.get(key_env) else "MISSING"
        return f"provider={provider} model={model} key={key_state}"
    if provider == "ollama":
        return f"provider=ollama model={OLLAMA_MODEL} url={OLLAMA_URL}"
    return f"provider={provider}"

# The reasoning brief. {manifest} is filled at call time so the agent decides
# against what actually exists, not a fixed schema.
_PROMPT_TEMPLATE = """\
You are the intent agent for Infrastructure as Intent (IAI).

A human describes what they want in plain language. Decide what the system should
do, grounded in the platform inventory below. Reason about intent; do not
pattern-match keywords.

How the platform is organised:
- An ENVIRONMENT (e.g. "staging") is the deployable unit. It belongs to a SERVICE
  (shown by its owner, e.g. "payments-team") and contains RESOURCES (e.g. an EC2
  app tier, a storage bucket).
- A user request may name a service, an environment, or specific resources. Your
  job is to map it to a specific environment that exists in the inventory.

Choose exactly one action:
- "provision" — create the described environment or resources.
- "modify"    — change something that already exists.
- "destroy"   — tear down existing resources. THIS IS IRREVERSIBLE.
- "clarify"   — ask ONE specific question instead of guessing.

Rules:
- Identify the exact target environment from the inventory. Put it in
  `target_environment` and name it in `understanding`.
- DESTROY and MODIFY are impactful. Resolve them directly ONLY when the user
  EXPLICITLY names an existing environment (e.g. "tear down staging"). If the
  request is vague ("get rid of them", "delete it") or names only a service or a
  resource ("payments", "the bucket"), you MUST "clarify" first — confirm the
  exact environment to act on by name. Never destroy on an inferred guess.
  (Teardown removes the WHOLE environment; it cannot remove individual resources,
  so do not offer that as an option.)
- PROVISION may be resolved directly when the environment/resources are clearly
  described.
- A clarify "question" must be SPECIFIC and reference the real options from the
  inventory — name the environment(s) and what they contain. Never ask a generic
  question like "which resource or environment?".
- One question maximum. Be concise.

Worked examples (for the inventory below):
- "tear down the staging environment" → destroy; understanding: "Tear down the
  'staging' environment (payments service): app-tier and export-bucket."
- "get rid of them" / "delete payments" → clarify; question: "Just to confirm —
  tear down the entire 'staging' environment (payments service: app-tier and
  export-bucket)? This is irreversible."

Platform inventory:
---
{manifest}
---

Return ONLY a JSON object (no markdown, no prose) with this shape:
{{
  "intent_type": "provision | modify | destroy | clarify",
  "confidence": 0.0,
  "needs_clarification": false,
  "question": "",
  "understanding": "",
  "target_environment": null,
  "resources": [],
  "clouds": [],
  "requirements": {{"criticality": "", "data_bearing": false, "tags": {{}}}}
}}

Field notes:
- confidence: 0.0–1.0, your confidence in the chosen action.
- needs_clarification: true only when intent_type is "clarify".
- question: one specific sentence for the user, only when clarifying; otherwise "".
- understanding: one plain sentence naming the exact environment and what the user wants.
- target_environment: the inventory environment this maps to, or null."""

_DESTROY_KEYWORDS = {
    "tear down", "teardown", "destroy", "decommission",
    "delete", "remove", "clean up", "cleanup",
}


def parse_intent(user_message: str, manifest_path: str | None = None) -> dict:
    """Interpret a plain-language request into a structured decision.

    Grounds the reasoning in the manifest at ``manifest_path`` (default from the
    IAI_MANIFEST env). On any provider failure, degrades to a keyword passthrough
    so the pipeline always runs.

    Returns a dict with: intent_type (provision|modify|destroy|clarify),
    confidence, needs_clarification, question, understanding, target_environment,
    resources, clouds, requirements.
    """
    inventory = _manifest_summary(manifest_path or MANIFEST_PATH)
    system_prompt = _PROMPT_TEMPLATE.format(manifest=inventory)

    provider = _resolve_provider()

    try:
        if provider in _OPENAI_COMPATIBLE:
            parsed = _parse_openai_compatible(provider, user_message, system_prompt)
            logger.info("Intent via %s: %s", provider, parsed)
            return parsed
        if provider == "ollama":
            parsed = _parse_ollama(user_message, system_prompt)
            logger.info("Intent via ollama: %s", parsed)
            return parsed
        if provider in ("none", "passthrough"):
            logger.info("LLM provider disabled — using passthrough intent")
            return _passthrough(user_message)
        logger.warning("Unknown IAI_LLM_PROVIDER=%r — using passthrough", provider)
    except Exception as exc:  # noqa: BLE001 — any failure must not break the demo
        logger.warning("Intent parse via %s failed (%s) — using passthrough", provider, exc)

    return _passthrough(user_message)


def _parse_openai_compatible(provider: str, user_message: str, system_prompt: str) -> dict:
    base_url, key_env, default_model = _OPENAI_COMPATIBLE[provider]
    api_key = os.environ.get(key_env)
    if not api_key:
        raise RuntimeError(
            f"{key_env} is not set — export it in the environment "
            f"(see .env.example), do not hard-code it"
        )

    model = os.environ.get("IAI_LLM_MODEL", default_model)
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
        },
        timeout=_HOSTED_TIMEOUT,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _coerce(json.loads(_extract_json(content)))


def _parse_ollama(user_message: str, system_prompt: str) -> dict:
    prompt = f"{system_prompt}\n\nUser request: {user_message}"
    resp = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"},
        timeout=(_OLLAMA_CONNECT_TIMEOUT, _OLLAMA_READ_TIMEOUT),
    )
    resp.raise_for_status()
    raw = resp.json().get("response", "")
    return _coerce(json.loads(_extract_json(raw)))


def _passthrough(user_message: str) -> dict:
    """Keyword fallback: route provision/destroy so the demo never hard-fails.

    The passthrough deliberately never asks for clarification — it is the
    offline safety net, not the reasoning path.
    """
    lower = (user_message or "").lower()
    intent_type = "destroy" if any(kw in lower for kw in _DESTROY_KEYWORDS) else "provision"
    return {
        "intent_type": intent_type,
        "confidence": None,
        "needs_clarification": False,
        "question": "",
        "understanding": "",
        "target_environment": "staging",
        "resources": [],
        "clouds": [],
        "requirements": {
            "environment": "staging",
            "criticality": "high",
            "data_bearing": False,
            "tags": {},
        },
    }


def _manifest_summary(manifest_path: str) -> str:
    """A concise, structured inventory of the manifest for the reasoning prompt.

    Clearer for the model than raw YAML-with-comments: it lists each environment,
    its owning service (owner tag), clouds, deployment state, and resources — so
    the agent can map "payments" → the staging environment and ask precise
    questions. Falls back to raw manifest text if parsing fails.
    """
    try:
        from ruamel.yaml import YAML

        with open(manifest_path, "r", encoding="utf-8") as fh:
            data = YAML(typ="safe").load(fh) or {}
        envs = data.get("environments", {}) or {}

        in_scope, out_scope = [], []
        for name, env in envs.items():
            if not isinstance(env, dict):
                continue
            if str(env.get("scope", "")).startswith("out-of-scope"):
                out_scope.append(f"{name} ({env.get('engine', '?')})")
                continue
            tags = env.get("tags", {}) or {}
            owner = tags.get("owner", "?")
            clouds = ", ".join(env.get("clouds", []) or []) or "?"
            resources = env.get("resources", {}) or {}
            statuses = {
                (r.get("state", {}) or {}).get("status", "pending")
                for r in resources.values()
                if isinstance(r, dict)
            }
            if statuses and statuses <= {"applied"}:
                state = "applied/live"
            elif statuses <= {"pending", ""} or not statuses:
                state = "not yet provisioned"
            else:
                state = "mixed"
            res_desc = ", ".join(
                f"{rn} ({r.get('type', '?')}, {r.get('criticality', '?')})"
                for rn, r in resources.items()
                if isinstance(r, dict)
            ) or "none"
            in_scope.append(
                f'- "{name}" — owner {owner} · clouds: {clouds} · state: {state}\n'
                f"    resources: {res_desc}"
            )

        lines = ["Environments (the deployable units):"]
        lines += in_scope or ["  (none defined)"]
        if out_scope:
            lines.append("Declared but OUT OF SCOPE (cannot act on): " + "; ".join(out_scope))
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001 — fall back to raw text, never block parsing
        logger.debug("manifest summary failed (%s); using raw manifest text", exc)
        return _load_manifest_text(manifest_path)


def _load_manifest_text(manifest_path: str) -> str:
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
        if len(text) > _MANIFEST_MAX_CHARS:
            text = text[:_MANIFEST_MAX_CHARS] + "\n# … (truncated)"
        return text or "(manifest is empty)"
    except OSError as exc:
        logger.warning("Could not read manifest at %s (%s) — reasoning without it", manifest_path, exc)
        return "(manifest not available)"


def _extract_json(text: str) -> str:
    """Strip markdown fences / prose and return the first JSON object found."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def _coerce(parsed: dict) -> dict:
    """Normalize a parsed decision to the expected shape with safe defaults."""
    if not isinstance(parsed, dict):
        raise ValueError("LLM did not return a JSON object")

    intent_type = parsed.get("intent_type", "provision")
    if intent_type not in ("provision", "modify", "destroy", "clarify"):
        intent_type = "provision"
    parsed["intent_type"] = intent_type

    parsed.setdefault("confidence", None)
    parsed.setdefault("question", "")
    parsed.setdefault("understanding", "")
    parsed.setdefault("target_environment", None)
    parsed.setdefault("resources", [])
    parsed.setdefault("clouds", [])

    # clarify and needs_clarification must agree.
    needs = bool(parsed.get("needs_clarification")) or intent_type == "clarify"
    parsed["needs_clarification"] = needs
    if needs:
        parsed["intent_type"] = "clarify"
        if not parsed.get("question"):
            parsed["question"] = "Could you clarify exactly what you'd like me to do?"

    req = parsed.setdefault("requirements", {})
    if isinstance(req, dict):
        req.setdefault("environment", parsed.get("target_environment") or "staging")
        req.setdefault("criticality", "high")
        req.setdefault("data_bearing", False)
        req.setdefault("tags", {})
    return parsed
