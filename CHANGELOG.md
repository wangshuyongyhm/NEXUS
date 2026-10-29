# Changelog

All notable changes to the nexusos packages are documented in this file.

Format: Keep a Changelog 1.1. The four packages share one lockstep version
line (one version number = all four packages at that version). Each release
has four sections — `nexusos-common` / `nexusos-gate` / `nexusos-mem` /
`nexusos-xdr` — with entries grouped under Added / Changed / Deprecated /
Removed / Fixed / Security. The layout_version axis (independent of package
semver) is documented in each package's README.

## [1.0.0] - 2026-10-30

First public release.

### nexusos-common

**Added**
- Anchor-resolution package: `nexus_home` / `vault_root` / `task_root` / `subpath` / `expand_env`, with explicit errors and WARN-level degradation rules.
- Private-path lint scanner `nexusos_common.lint` (15 patterns, data-driven), baselined against a full hardcode audit.
- `LAYOUT_VERSION` / `SUPPORTED_LAYOUTS` layout-version constants — a directory-layout version axis independent of package semver, reconciled with `.nexus/config.toml [meta] layout_version`.

### nexusos-gate

**Changed**
- Anchor resolution in `_vault_env`, `gate_engine._ensure_vault_root` and `_checks/_vault_root.py` now delegates to nexusos-common; inline `parents[N]` path derivation removed (no duplicate sources).
- Five vault-specific checks open-sourced by disposition: `config_key_refs` and `codegraph_wrapper` became plugins, `persist_pool_ledger` and `doc_consistency` became examples, `e2e_suite_evidence` reads its configuration from `$NEXUS_HOME/gate/e2e-paths.yaml` (missing config = WARN skip, not REJECT).
- Package renamed `nexus-gate` → `nexusos-gate` (directory, module, pyproject and imports cut over in one pass, no compatibility shim).
- Version 0.1.0 → 1.0.0, joining the four-package lockstep line.

**Added**
- `nexusos.gate.checks` entry_points plugin protocol: the engine loads plugins in stable sorted(name) order, plus declarative enablement via `checks.d`.

### nexusos-mem

**Changed**
- Anchor resolution in `_vault_env` now delegates to nexusos-common; inline `parents[N]` derivation removed.
- Package renamed `nexus-mem` → `nexusos-mem` (single cut-over, no shim).
- Version 0.1.0 → 1.0.0, joining the four-package lockstep line.

### nexusos-xdr

**Fixed**
- Four event-log incidents fixed: the migration function gained samefile+realpath double protection against self-referential loops, the guard now tail-reads with a deque (curing a readlines-whole-file freeze), and all event consumers were inventoried and reconciled (three monitor scripts, the mcp_server gate-rollup, and checks.yaml fixed together).

**Changed**
- The `~/.hermes` family of 15 path mappings migrated to `.nexus` (single env source + idempotent `nexus migrate`; three consecutive re-runs report 0 MOVED).
- Package renamed `nexus-xdr` → `nexusos-xdr` (single cut-over, no shim).
- Version line aligned with the four-package lockstep at 1.0.0.

**Added**
- Operations CLI `python3 -m nexusos_xdr.cli` (update/doctor): PyPI version comparison, layout_version migration hints, one-liner upgrades; doctor reconciles six services, the database, guards, and version consistency. (The `nexus` command name belongs to the onboarding wizard CLI in nexusos-common; xdr intentionally declares no scripts entry.)
- Tag-driven release pipeline: pushing a `v*` tag on GitHub Actions triggers build → TestPyPI (production PyPI is a manual, human-approved step).

### Migration notes

- No compatibility guarantees across the 0.x line (v1.0 starts fresh). The old package names `nexus-gate` / `nexus-mem` / `nexus-xdr` are no longer published.
