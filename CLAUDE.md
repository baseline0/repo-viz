# repo-viz

Static analysis pipeline and future interactive viewer for repository membranes: nested containers, semantic zoom, data/control/security tracks, and a polarized status strip. The graph snapshot is a derived artifact; on-demand audit and dispatch are separate, human-approved flows.

## Build & Test

- `just test` — hermetic unit suite
- `just check` — ruff + format check + pyright
- `just ci` — check then test
- `just analyze REPO --out graph.json` — regenerate a snapshot
- `just --list` — every recipe, by group

## Boundaries

- Only the standard library is used for parsing today; no network or sibling-repo calls in unit tests.
- `src/repo_viz/cli.py` uses Typer; argparse is banned by fleet standard.
- All path resolution comes from `src/repo_viz/constants.py` (`REPO_ROOT`); no `.parent` elsewhere.

**For universal rules, see the global `~/.claude/CLAUDE.md`, a copy of `infrastructure/claude/CLAUDE.standard.md`.**
