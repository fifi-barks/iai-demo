"""Manifest reader for IAI.

Loads the platform manifest with ruamel.yaml so that all human-authored
comments round-trip cleanly on every rewrite (the auto-update contract).
Resolves transitive criticality across the dependency graph and writes back
only the agent-maintained `state:` block of each resource.

Library scope: stdlib + ruamel.yaml only.
"""

import io

from ruamel.yaml import YAML


class ManifestReader:
    CRITICALITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}

    # Reverse lookup: rank int -> criticality string.
    _RANK_TO_NAME = {v: k for k, v in CRITICALITY_RANK.items()}

    def __init__(self, path: str) -> None:
        """Load manifest from path using ruamel.yaml (preserves comments)."""
        self._path = path
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        with open(path) as f:
            self._data = self._yaml.load(f)

    def _environments(self) -> dict:
        return self._data.get("environments", {})

    def _environment(self, env: str) -> dict:
        envs = self._environments()
        if env not in envs:
            raise KeyError(f"environment {env!r} not found in manifest")
        return envs[env]

    def get_environments(self) -> list:
        """Return list of all environment names."""
        return list(self._environments().keys())

    def get_engine(self, env: str) -> str:
        """Return IaC engine for the named environment ('terraform' | 'ansible')."""
        return self._environment(env)["engine"]

    def get_resources(self, env: str) -> dict:
        """Return raw resource dict for the named environment (keyed by resource name)."""
        return self._environment(env).get("resources", {})

    def resolve_criticality(self, env: str) -> dict:
        """Return name -> effective_criticality after transitivity is applied.

        Rule: if resource B is in resource A's depends_on, then
        effective(B) = max(effective(B), effective(A)) by CRITICALITY_RANK.
        Iterate until stable (handles multi-hop chains).
        Resources with no 'resources' key (e.g. edge-network) return {}.
        """
        resources = self.get_resources(env)
        if not resources:
            return {}

        effective = {name: res["criticality"] for name, res in resources.items()}

        changed = True
        while changed:
            changed = False
            for name_a, res_a in resources.items():
                incoming = self.CRITICALITY_RANK[effective[name_a]]
                for dep_name in res_a.get("depends_on", []):
                    if dep_name not in effective:
                        continue
                    current = self.CRITICALITY_RANK[effective[dep_name]]
                    if incoming > current:
                        effective[dep_name] = self._RANK_TO_NAME[incoming]
                        changed = True

        return effective

    def update_resource_state(self, env: str, name: str, updates: dict) -> None:
        """Mutate the state: sub-block for the named resource in-memory.

        Only the keys present in `updates` are written. All other fields
        (criticality, depends_on, type, cloud, comments) are untouched.
        Does NOT write to disk — call write() after.
        """
        resources = self.get_resources(env)
        if name not in resources:
            raise KeyError(f"resource {name!r} not found in environment {env!r}")

        resource = resources[name]
        if "state" not in resource:
            raise KeyError(
                f"resource {name!r} in environment {env!r} has no state block"
            )

        state = resource["state"]
        # Assign scalars into the existing CommentedMap so comments survive.
        for key, value in updates.items():
            state[key] = value

    def write(self) -> None:
        """Write the in-memory YAML back to self._path, preserving all comments."""
        with open(self._path, "w") as f:
            self._yaml.dump(self._data, f)

    def write_to(self, path: str) -> None:
        """Write the in-memory YAML to an arbitrary path (used by tests)."""
        with open(path, "w") as f:
            self._yaml.dump(self._data, f)

    def to_string(self) -> str:
        """Serialise the in-memory YAML to a string (convenience for tests)."""
        buf = io.StringIO()
        self._yaml.dump(self._data, buf)
        return buf.getvalue()
