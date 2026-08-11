from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from .style_profiles import list_style_profiles, load_style_profile, prompt_prefix

mcp = FastMCP("VALO Style Profiles")


@mcp.resource("style://{profile_id}")
def style_profile(profile_id: str) -> str:
    """Return one canonical VALO style profile as JSON."""
    return json.dumps(load_style_profile(profile_id), ensure_ascii=False, indent=2)


@mcp.tool()
def list_profiles() -> list[str]:
    """List canonical style profile identifiers available to the client."""
    return [load_style_profile(name)["id"] for name in list_style_profiles()]


@mcp.tool()
def get_profile(profile_id: str = "reht-visual") -> dict:
    """Return a canonical style profile for prompt construction or validation."""
    return load_style_profile(profile_id)


@mcp.tool()
def apply_profile(instruction: str, profile_id: str = "reht-visual") -> str:
    """Prepend the canonical profile contract to a user instruction."""
    instruction = instruction.strip()
    if not instruction:
        raise ValueError("instruction is required")
    return f"{prompt_prefix(profile_id)}\n\nOppgave: {instruction}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
