"""nexus_xdr — agent message bus skeleton.

Placeholder modules mirror the private monorepo layout:
  mcp_server   — FastMCP + starlette HTTP, :19998 by default
  credential   — HMAC-SHA256 credential issue/verify lifecycle
  guards       — dangerous-operation guards for dispatched tasks
"""

__version__ = "1.0.0"


def serve(port: int = 19998, host: str = "127.0.0.1") -> None:
    raise NotImplementedError(
        "skeleton: bus server is being migrated, see docs/sync-strategy.md"
    )
