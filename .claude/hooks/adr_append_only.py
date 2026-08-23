#!/usr/bin/env python3
"""Append-only guard for docs/decisions/ ADRs (Claude Code PreToolUse hook).

Invoked on Write | Edit | NotebookEdit with the tool call as JSON on stdin.
Decision:
  - target matches docs/decisions/0*.md and EXISTS      -> deny
  - target matches docs/decisions/0*.md and is NEW      -> ask (prompt-gated)
  - target is unrelated                                 -> no decision (normal flow)

FAIL-CLOSED BY DESIGN. The deny is the default; the permissive paths are the
explicit exceptions:
  - stdin unparseable, or no target path in the payload -> deny
  - relative target that cannot be anchored (no CLAUDE_PROJECT_DIR) but that
    looks like an ADR path                              -> deny
  - any unhandled exception                             -> deny
Both the normalized path and its realpath are tested, so a symlink disguise
in either direction is treated as an ADR.

Known residuals, stated rather than papered over:
  - Bash is a separate tool path: `sed -i docs/decisions/0013-*.md` does not
    pass through this hook. It is not allowlisted, so it prompts; narrow deny
    rules in settings.json catch the obvious in-place forms, but shell-string
    glob matching is brittle and is NOT a boundary. See the footer of
    docs/decisions/README.md for the precise guarantee.
  - If python3 itself is absent the hook command fails with exit 127, which
    Claude Code treats as non-blocking (fail-open). The repo requires
    Python >= 3.12, so this is accepted. A missing script file, by contrast,
    makes python3 exit 2, which blocks (fail-closed).
"""

import json
import os
import sys
from fnmatch import fnmatch


def _emit(decision: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def _is_adr(path: str) -> bool:
    """True if `path` names a file docs/decisions/0*.md (any prefix above it)."""
    parts = os.path.normpath(path).replace("\\", "/").split("/")
    return len(parts) >= 3 and parts[-3:-1] == ["docs", "decisions"] and fnmatch(parts[-1], "0*.md")


def main() -> None:
    data = json.loads(sys.stdin.read())
    tool_input = data.get("tool_input")
    path = None
    if isinstance(tool_input, dict):
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(path, str) or not path:
        _emit("deny", "adr_append_only: no target path in hook payload; failing closed.")
        return

    resolved = os.path.normpath(path)
    if not os.path.isabs(resolved):
        project = os.environ.get("CLAUDE_PROJECT_DIR", "")
        if not project:
            if _is_adr(resolved):
                _emit(
                    "deny",
                    "adr_append_only: relative ADR path and CLAUDE_PROJECT_DIR unset, "
                    "so existence cannot be verified; failing closed.",
                )
            return
        resolved = os.path.normpath(os.path.join(project, resolved))

    candidates = {resolved, os.path.realpath(resolved)}
    if not any(_is_adr(c) for c in candidates):
        return  # unrelated file: no decision, normal permission flow applies

    if any(os.path.lexists(c) for c in candidates):
        _emit(
            "deny",
            "ADRs are append-only: existing docs/decisions/0*.md files are never "
            "edited. Supersede with a new ADR (see docs/decisions/README.md).",
        )
    else:
        _emit("ask", "Creating a new ADR in an append-only directory: prompt-gated.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # any failure in a guard denies -- fail closed
        _emit(
            "deny",
            f"adr_append_only hook errored ({type(exc).__name__}); failing closed. "
            "Fix the hook before writing to docs/decisions/.",
        )
