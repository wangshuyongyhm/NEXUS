# Changelog

All notable changes to the nexusos packages are documented in this file.

Format: Keep a Changelog 1.1. The four packages share one lockstep version
line (one version number = all four packages at that version). Each release
has four sections — `nexusos-common` / `nexusos-gate` / `nexusos-mem` /
`nexusos-xdr` — with entries grouped under Added / Changed / Deprecated /
Removed / Fixed / Security. The layout_version axis (independent of package
semver) is documented in each package's README.

## [1.2.0] - 2026-11-27

Security-and-robustness release for the three service packages; `nexusos-common` unchanged (1.0.0). Every line below is backed by the `git diff --name-status origin/master HEAD` listing of the three package repositories (published 1.1.0 → this snapshot).

### nexusos-common

No changes (1.0.0).

### nexusos-gate

**Added**
- `etc/gates/_checks/commit_file_cap.py`: single-commit file-count cap.
- `etc/gates/_checks/session_log_selfcheck.py`: session-log self-check.
- `scripts/staged_tests_grouped.py`: grouped test runner used by the code gate (C5).

**Changed**
- `gate_engine.py`: event signing, dispatch hard-block, blocked-debt made visible; new `RETIRED_SCENARIOS` registry — calling a retired scenario (`loop_start` / `loop_complete` / `deploy-sync`) now returns an explicit "retired" message instead of silently passing.
- `etc/gates/_checks/done_ack.py`, `outcome_backfill.py`, `pool_rows_flipped.py`, `persist_pool_ledger.py`, `pool_write_channel.py`, `doc_symbol_refs.py` and `tests/test_2611111773_g1_annotation.py`: aligned with the gate-core changes (`pool_rows_flipped.py` also drops a docstring reference to a retired checker).
- `README.md`: examples path corrected to the bundled `etc/checks/examples/` (the previously documented `./examples/gates/` does not exist in the installed wheel).

**Removed**
- Three retired gate scenarios and their dedicated checkers (`loop_start` / `loop_complete` / `deploy-sync`; `agent_archive_updated.py`, `deploy_synced.py`, three scenario YAMLs) — removed from the source tree (recoverable from history), no longer in this snapshot.

### nexusos-mem

**Added**
- `redact_credential.py`: credential IDs in ingested text are replaced with a fixed placeholder — both slice-ingest entry points and both write-API entry points use the same function and placeholder; replace, never reject.
- `machine_identities.py`: machine identities — names on the machine roster are no longer issued search credentials.

**Changed**
- `search.py`: full-text search no longer forces a sequential scan (short queries take the window short-cut; the planner is consulted, the old statement kept when it does not already scan); re-ranker cooldown reserved for "service is down" — when merely busy, degrade in place and return a retry hint, and the response says whether re-ranking happened.
- `rerank_server.py`: cooldown / degradation aligned.
- `embed_server.py`, `embed_corpus.py`: embedding service pads to fixed shapes (20 tiers), clears cache per mode, self-restarts on memory overshoot.
- `api_server.py`: result endpoints validate credential and record ownership; heavy-request concurrency gauge exposes `busy_rejects` on `/health`; the 403 missing-credential message now says where to get one.
- `apply_honesty.py`, `shared.py`: search-credential issuance decision consolidated into one function.
- `context_capture.py`, `skip_rules.py`, `scripts/backfill_identity.py`: aligned.
- `README.md`: new "Known limitations" section — the standalone package does not ship the schema; create the database first from the open-source repository's `db/` directory.

**Fixed**
- `search.py`: three defects in the statement-error fallback — missing rollback, "transaction aborted" treated as internal error, statement timeout not reset after rollback.

**Security**
- `api_server.py`, `apply_honesty.py`, `shared.py`: result endpoints validate credential and record ownership; issuance decision consolidated.

### nexusos-xdr

**Added**
- `ack_policy.py`: the dispatcher signs off on delivery, sign-offs land in the ledger; delivery receipts and sign-offs are separate fields.
- `callback/cred_gate.py`: callbacks must present the dispatch credential (switch defaults to log-only).
- `proc_origin.py`, `proclog_filter.py`: the server records the process origin of every write request (log only).
- `hooks/sensitive_ops.py`, `hooks/sensitive_ops_guard.py`: sensitive-operation guards.
- `stall_watch.py`: stall watch; steer-script path prefers `NEXUS_STEER_SCRIPT`, else the previous default.
- `task_aliases.py`: task-number aliases.
- `email_inbound.py`: email inbound — decision-required notices become email callbacks (the per-agent hook scripts it relies on are not shipped in the open-source edition).

**Changed**
- `ack.py`, `callback/handler.py`, `callback/outcome_autofill.py`, `credential.py`, `dispatch/main.py`, `dispatchd.py`, `task_state.py`, `session_state.py`: unified callback / sign-off commands — identity and credential handling; receipts vs. sign-offs as separate fields.
- `patrol/loop.py`: patrol's "done" detection timing.
- `mcp_server.py`: removed the dead `loop_start` on-pass hook (`_on_loop_start_pass`) and its registration; `mcp_auth.py`, `httpapi/routes.py`, `presence/routes.py` aligned.
- `hooks/broadcast_guard.py`, `completion_guard.py`, `interaction_guard.py`, `selfcheck_evidence_guard.py`, `state_transition_guard.py`: guards aligned.
- `exp_injector.py`, `needdecision_notify.py`, `notify_push.py`: notification chain aligned.
- `p02_hardblock.py`, `layer2_calibrate.py`, `fault_http_server.py`, `tools/registry.py`: aligned.

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
