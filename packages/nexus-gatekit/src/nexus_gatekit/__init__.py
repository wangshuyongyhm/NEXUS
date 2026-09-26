"""nexus_gatekit — gate engine skeleton (renamed from nexus-gate).

Placeholder modules mirror the private monorepo layout:
  gate_engine   — scenario loader + check orchestration
  _checks/      — pluggable checks (grep_in_diff, git_diff_scope, …)
Checks are declared in etc/gates/*.yaml with severity REJECT/WARN.
"""

__version__ = "0.1.0"


def check(scenario: str, context: dict, agent: str = "unknown") -> dict:
    """Skeleton entry point. The real engine is being migrated (see
    docs/sync-strategy.md). Returns a pass-through result."""
    return {
        "scenario": scenario,
        "agent": agent,
        "passed": True,
        "hard_fails": [],
        "warnings": [],
        "note": "skeleton: no checks loaded",
    }
