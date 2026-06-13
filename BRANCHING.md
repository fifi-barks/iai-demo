# Branching Strategy — iai-demo

## Branches

- **main** — stable, tagged releases only. No direct commits.
- **develop** — integration branch. Default target for PRs.
- **feature/*** — all development work, branched off `develop` (e.g., `feature/manifest-auto-update`, `feature/phase4-video`)

## Workflow

1. Branch off develop: `git checkout develop && git checkout -b feature/my-feature`
2. Work and commit
3. Push: `git push origin feature/my-feature`
4. Open PR to `develop` on GitHub
5. Review + merge
6. When `develop` is stable, open PR to `main`
7. Tag the release: `git tag -a v0.2.0 -m "Release 0.2.0"`
8. Push the tag: `git push origin v0.2.0`

## Current version

See `VERSION`.
