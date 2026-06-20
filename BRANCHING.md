# Branching Strategy — iai-demo

Trunk-based: **`main` is the single source of truth.** It's always deployable and
it's what people clone. Work happens on short-lived `feature/*` branches and
merges back via pull request.

## Branches

- **main** — the trunk. Stable, always working. Releases are tagged here.
- **feature/*** — development work, branched off `main` (e.g.
  `feature/resource-scoped-destroy`). Short-lived; delete after merge.

## Workflow

1. Branch off main: `git checkout main && git pull && git checkout -b feature/my-feature`
2. Work and commit.
3. Push: `git push -u origin feature/my-feature`
4. Open a PR to `main` on GitHub, review, and merge.
5. Delete the feature branch.
6. Tag releases on `main` and bump `VERSION` to match:
   `git tag -a v1.1.0 -m "Release 1.1.0" && git push origin v1.1.0`

For small fixes, committing straight to `main` is fine — this is a solo demo
repo, not a regulated release pipeline.

## Current version

See `VERSION`.
