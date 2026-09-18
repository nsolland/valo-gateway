from __future__ import annotations

from dataclasses import asdict
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP as MCPServer
except ImportError:
    try:
        from mcp.server import FastMCP as MCPServer
    except ImportError:
        from mcp.server import MCPServer

from .capability_frontdoor import CapabilityFrontDoor, CapabilityRequest

mcp = MCPServer("VALO Capability Front Door")
_frontdoor = CapabilityFrontDoor()


def configure(frontdoor: CapabilityFrontDoor) -> None:
    global _frontdoor
    _frontdoor = frontdoor


@mcp.tool()
def discover(intent: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return only the capabilities relevant to the requested intent."""
    return [asdict(item) for item in _frontdoor.discover(CapabilityRequest(intent, limit))]


@mcp.tool()
def invoke(capability_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Invoke one bound capability. Effect capabilities fail closed without authority."""
    return _frontdoor.invoke(capability_id, payload)


@mcp.tool()
def status(record_id: str) -> dict[str, Any]:
    """Return the execution receipt or normalized event for one record id."""
    return _frontdoor.status(record_id)


@mcp.tool()
def event(source: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize and record an incoming provider event."""
    return _frontdoor.event(source, event_type, payload)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
