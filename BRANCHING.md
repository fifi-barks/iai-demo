cat << 'EOF' > BRANCHING.md
# Branching Strategy — iai-demo

## Branches

- **main** — production-ready, tagged releases only. No direct commits.
- **develop** — integration branch for features. Default for PRs.
- **feature/*** — feature branches off develop (e.g., `feature/phase4-video-recording`)
- **demo/*** — alternative demo scenarios (e.g., `demo/multi-account-enterprise`)

## Workflow

1. Create feature branch off develop: `git checkout develop && git checkout -b feature/my-feature`
2. Work and commit
3. Push: `git push origin feature/my-feature`
4. Create PR to develop on GitHub
5. Review + merge
6. When develop is stable, create PR to main
7. Tag release: `git tag -a v0.2.0 -m "Release 0.2.0"`
8. Push tags: `git push origin v0.2.0`

## Current Version

See VERSION file.
EOF