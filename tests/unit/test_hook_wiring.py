"""settings.json actually invokes the ADR guard — the wiring, not the script.

tests/unit/test_adr_hook.py exercises .claude/hooks/adr_append_only.py in
isolation; nothing there fails if settings.json stops invoking it. That is
exactly what happened in the #28 merge (a483bb9): a conflict resolution
restored the inline fail-open shell hook, the script sat orphaned, and the
suite stayed green — the exp001 failure shape (a test measuring something
other than what is deployed) reproduced inside the permission system. These
tests pin the deployment, so that revert is a red suite, not a silent one.
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT_REL = ".claude/hooks/adr_append_only.py"


def settings():
    return json.loads((REPO / ".claude" / "settings.json").read_text())


def file_edit_hook_commands():
    blocks = [
        b
        for b in settings().get("hooks", {}).get("PreToolUse", [])
        if b.get("matcher") == "Write|Edit|NotebookEdit"
    ]
    assert len(blocks) == 1, "expected exactly one PreToolUse block on Write|Edit|NotebookEdit"
    return [h["command"] for h in blocks[0]["hooks"] if h.get("type") == "command"]


def test_pretooluse_invokes_the_guard_script():
    commands = file_edit_hook_commands()
    assert any(SCRIPT_REL in c for c in commands), (
        f"no PreToolUse command references {SCRIPT_REL}; the guard is not wired"
    )


def test_guard_is_not_the_inline_shell_form():
    """The reverted form: a jq shell pipeline with a cwd-relative `[ -e ]`
    existence check and no error handling — all three failure modes open."""
    for command in file_edit_hook_commands():
        assert "jq " not in command, f"inline jq hook deployed instead of the script: {command!r}"


def test_guard_script_exists_where_settings_points():
    assert (REPO / SCRIPT_REL).exists(), f"{SCRIPT_REL} missing: settings would invoke nothing"


def test_bash_in_place_deny_rules_present():
    """Defence-in-depth rules for the Bash residual (brittle by design, but
    they were silently reverted by the same merge and nothing noticed)."""
    deny = set(settings()["permissions"]["deny"])
    for rule in (
        "Bash(sed -i*docs/decisions/*)",
        "Bash(tee*docs/decisions/*)",
        "Bash(*>docs/decisions/*)",
        "Bash(*> docs/decisions/*)",
    ):
        assert rule in deny, f"missing defence-in-depth deny rule: {rule}"
