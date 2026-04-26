"""
Checkmate Agent Logger — Logs agent actions and outputs to a file.
Clears the log file before each run.
"""

import json
import os
from datetime import datetime
from pathlib import Path

# Log file location
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "agent.log"


def _ensure_log_dir():
    """Ensure logs directory exists."""
    LOG_DIR.mkdir(exist_ok=True)


def clear_log():
    """Clear the log file at the start of a new run."""
    _ensure_log_dir()
    if LOG_FILE.exists():
        LOG_FILE.unlink()


def log_node_execution(node_name: str, prompt: str, output: dict):
    """
    Log a node's execution with agent name, prompt sent to LLM, and output.
    Saves everything exactly as is, without truncation.

    Args:
        node_name: Name of the agent node
        prompt: The prompt sent to the LLM
        output: The output/update returned by the node
    """
    _ensure_log_dir()

    timestamp = datetime.now().isoformat()

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"[{timestamp}] NODE: {node_name}\n")
        f.write(f"{'='*80}\n")
        f.write("\n--- PROMPT ---\n")
        f.write(prompt)
        f.write("\n\n--- OUTPUT ---\n")
        f.write(json.dumps(output, indent=2, default=str))
        f.write("\n\n")


def log_graph_invocation(initial_state: dict):
    """Log the start of a graph invocation."""
    _ensure_log_dir()

    timestamp = datetime.now().isoformat()

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'#'*80}\n")
        f.write(f"# GRAPH INVOCATION START: {timestamp}\n")
        f.write(f"{'#'*80}\n")
        f.write("\n\n")


def log_graph_completion(final_state: dict):
    """Log the completion of a graph invocation."""
    _ensure_log_dir()

    timestamp = datetime.now().isoformat()

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'#'*80}\n")
        f.write(f"# GRAPH INVOCATION COMPLETE: {timestamp}\n")
        f.write(f"{'#'*80}\n")
        f.write("\n\n")
