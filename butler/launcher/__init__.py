# This serves to launch the entire Monkey Butler Stack:
# - InfoPanel
# - Voice Worker
# - Ollama backend
# - Main agent (opens the shared SQLite database itself)

"""
    python -m butler.launcher            # GUI (default)
    python -m butler.launcher --no-gui   # headless, streams logs to the console
"""

from __future__ import annotations

__all__ = ["config", "core"]
