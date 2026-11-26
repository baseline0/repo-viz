#!/usr/bin/env just --justfile

# Fleet Repository Justfile Template
#
# RATIONALE: Justfiles organize recipes into groups ([dev], [testing], [audit], [fleet],
# [governance], [compliance], [inventory]) for clarity and discoverability. Recipes
# delegate to Typer CLI apps for complex logic (agents, job queuing, governance checks).
#
# PAVED ROADS:
# - Cache cleaning (clean, clean-cache) vendored from fleet-base
# - Domain-specific recipes live in this justfile so generators can discover them from the Typer app
# - Typer CLI apps (src/<repo>/cli.py) handle multi-step workflows, job dispatch
# - Job queuing via uv run <module> commands (agent dispatch, WorkItem lifecycle)
#
# USAGE:
#   1. Copy this template: cp fleet-base/templates/justfile.template ./justfile
#   2. Install the vendored just/ modules (see the imports section)
#   3. Create src/<repo>/cli.py with typer app for domain logic
#   4. Add local just/ modules for recipe organization
#   5. Run: just --list to see all recipes by group

set shell := ["bash", "-c"]

# ============================================================================
# IMPORTS: Shared recipes & modules
# ============================================================================

# Shared modules from fleet-base, vendored into just/. Install with:
#   uv run python -m fleet_base.vendor_just install --repo <this repo>   (run in fleet-base's checkout)
# The installer checks that every vendored module is imported here, so keep all three.
# A recipe name may be defined only once: to change one, rename the local recipe, never override it.
import 'just/fleet-clean.just'
import 'just/fleet-commit.just'
import 'just/repo-push.just'

# Optional: Import shared utilities (pre-commit, commit, CI checks)
# import? 'just/shared.just'

# Generated recipes belong in just/generated.just; hand-written recipes stay here.

# ============================================================================
# [dev] Development: Type check, lint, format
# ============================================================================
# These recipes use uv to run Python linters/formatters.

[group("dev")]
default:
    @just --list

# Format and auto-fix (fleet standard: ruff format + ruff check --fix)
[group("dev")]
fmt:
    uv run ruff format src/ tests/
    uv run ruff check src/ tests/ --fix

# Lint and type/format check, no mutations
[group("dev")]
check:
    uv run ruff check src/ tests/
    uv run ruff format --check src/ tests/
    uv run pyright src/

# Full validation gate (no auto-fix)
[group("dev")]
ci: check test

# ============================================================================
# [testing] Test execution: unit, integration, full suite
# ============================================================================
# Run tests using pytest. Customize test paths/markers for your repo.

[group("testing")]
test:
    @echo "🧪 Running full test suite..."
    uv run pytest tests/ -v

[group("testing")]
test-unit:
    @echo "🧪 Running unit tests..."
    uv run pytest tests/unit -v -m "not integration"

[group("testing")]
test-integration:
    @echo "🧪 Running integration tests..."
    uv run pytest tests/integration -v -m integration

[group("testing")]
test-fast:
    @echo "🧪 Running fast (unit) tests..."
    uv run pytest tests/unit -v -m unit

# ============================================================================
# [audit] Code quality: imports, boundaries, governance rules
# ============================================================================
# Recipes for import validation, code ownership, repository boundaries.

[group("audit")]
check-imports:
    @echo "🔗 Checking import boundaries..."
    uv run import-linter lint --config .importlinter

[group("audit")]
check-boundaries:
    @echo "🛑 Validating repository boundaries..."
    @if [ -f .fleet/boundaries.yaml ]; then \
        echo "✓ Boundaries defined in .fleet/boundaries.yaml"; \
    else \
        echo "⚠️  No .fleet/boundaries.yaml found"; \
    fi

# ============================================================================
# [fleet] Fleet-wide operations: agent dispatch, job queues, coordination
# ============================================================================
# Recipes for coordinating with fleet infrastructure (fleet-agents, fleet-ops).
# These delegate to Typer CLI apps or fleet-ops infrastructure.

[group("fleet")]
agent-help:
    @echo "🤖 Fleet agent workflows (see just agent-help for details)"
    @echo ""
    @echo "Dispatch work items:"
    @echo "  just dispatch WI-<id>              # Queue work item"
    @echo "  just dispatch-and-run WI-<id>      # Queue + execute"
    @echo ""
    @echo "Check agent status:"
    @echo "  just local-agent-status            # Ollama and fleet-agents health"
    @echo ""
    @echo "See: fleet-ops/just/dispatch.just for full agent recipes"

# Placeholder: Uncomment and customize for your repo's agent needs
# [group("fleet")]
# dispatch WORK_ITEM:
#     @echo "🤖 Dispatching {{WORK_ITEM}} to local agents..."
#     uv run python -m <your_module>.cli queue dispatch "{{WORK_ITEM}}"

# ============================================================================
# [governance] Governance checks: compliance, policy enforcement
# ============================================================================
# Recipes for validating governance rules and metadata.

[group("governance")]
governance-check:
    @echo "⚖️  Checking governance compliance..."
    @if [ -f .fleet/catalog-info.yaml ]; then \
        echo "✓ Catalog info: .fleet/catalog-info.yaml"; \
    else \
        echo "⚠️  No .fleet/catalog-info.yaml found"; \
    fi

[group("governance")]
validate-metadata:
    @echo "🔍 Validating repository metadata..."
    @echo "Check: registry entry in fleet-coordination/registry/repos.yaml"

# ============================================================================
# [compliance] Security & standards: license, security, code ownership
# ============================================================================
# Recipes for compliance validation (licenses, security, CODEOWNERS).

[group("compliance")]
check-licenses:
    @echo "📜 Checking dependency licenses..."
    @echo "Run: pip-audit or license-checker (configure as needed)"

[group("compliance")]
check-security:
    @echo "🔐 Running security checks..."
    @echo "Run: bandit, semgrep, or other security scanner"

# ============================================================================
# [inventory] Repository metadata: catalog, dependencies, health
# ============================================================================
# Recipes for discovering repo metadata, dependencies, and health status.

[group("inventory")]
inventory:
    @echo "📋 Repository metadata:"
    @echo "  Name: $(shell basename $(pwd))"
    @echo "  Path: $(pwd)"
    @if [ -f .fleet/catalog-info.yaml ]; then \
        echo "  ✓ Registered in fleet"; \
    else \
        echo "  ⚠️  Not yet registered"; \
    fi

[group("inventory")]
inventory-deps:
    @echo "📊 Dependencies:"
    @uv pip list --format=freeze 2>/dev/null | head -20

# ============================================================================
# Repository-Specific Recipes
# ============================================================================
# Add custom recipes below. Organize with comments and groups.

# Regenerate the versioned graph artifact for a checkout (derived; never hand-edit).
[group("dev")]
analyze REPO OUT="graph.json" DAYS="30":
    uv run python -m repo_viz.cli analyze "{{REPO}}" --out "{{OUT}}" --days "{{DAYS}}"

[group("dev")]
summary SNAPSHOT:
    uv run python -m repo_viz.cli summary "{{SNAPSHOT}}"

# Frontend: npm install is guarded, matching the fleet's periodic-table-inspector recipe.
[group("dev")]
frontend-install:
    @test -d frontend/node_modules || (cd frontend && npm install --no-audit --no-fund)

[group("dev")]
frontend-check: frontend-install
    cd frontend && npm run check

[group("dev")]
frontend-build: frontend-install
    cd frontend && npm run build

# Validate that the tracked indicator configuration parses and resolves.
[group("dev")]
check-indicators:
    uv run python -m repo_viz.cli check-indicators --config config/indicators.toml

[group("dev")]
indicators SNAPSHOT OUT="indicators.json" TRIGGER="render" REPO="":
    uv run python -m repo_viz.cli evaluate-indicators "{{SNAPSHOT}}" --out "{{OUT}}" --trigger "{{TRIGGER}}" {{ if REPO != "" { "--repo \"" + REPO + "\"" } else { "" } }}

[group("dev")]
serve GRAPH PORT="8080" *ARGS: frontend-build
    uv run python -m repo_viz.cli serve "{{GRAPH}}" --port "{{PORT}}" {{ARGS}}

# Example: If this repo manages jobs
# [group("fleet")]
# queue-status:
#     @echo "📦 Job queue status..."
#     uv run python -m <your_module>.cli queue list

# ============================================================================
# Deprecation Aliases (optional; for backward compatibility)
# ============================================================================
# When renaming a recipe, add a deprecation alias so scripts using the old
# name still work (with a warning).

# Example: Renamed check-lint → check
# [private]
# check-lint:
#     @echo "⚠️  'just check-lint' is deprecated; use 'just check' instead" >&2
#     @just check
