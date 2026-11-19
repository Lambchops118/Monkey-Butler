from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from butler.services import home_automation as actions


def register(server: FastMCP) -> None:
    """Register the existing home automation tools on a FastMCP server."""

    @server.tool()
    def get_current_datetime() -> str:
        """Get the current local date, time, year, and timezone for Butler."""
        return actions.get_current_datetime()
