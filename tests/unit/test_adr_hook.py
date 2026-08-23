"""The ADR append-only guard (.claude/hooks/adr_append_only.py) fails closed.

The hook is a security control; these tests pin its decision table and,
critically, its failure direction: every path that matches the ADR pattern
must produce a deny unless the target verifiably does not exist. Hermetic:
each test builds its own project directory under tmp_path and invokes the
script as Claude Code does — a subprocess with the tool call as JSON on
stdin and CLAUDE_PROJECT_DIR in the environment.
"""

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "adr_append_only.py"


def run_hook(payload, project_dir=None, cwd=None):
    """Run the hook; return the parsed decision dict, or None for no decision."""
    env = {"PATH": "/usr/bin:/bin"}
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)["hookSpecificOutput"]


def make_project(tmp_path):
    project = tmp_path / "proj"
    (project / "docs" / "decisions").mkdir(parents=True)
    adr = project / "docs" / "decisions" / "0001-existing.md"
    adr.write_text("# ADR-0001\n")
    return project, adr


def test_existing_adr_is_denied(tmp_path):
    project, adr = make_project(tmp_path)
    out = run_hook({"tool_input": {"file_path": str(adr)}}, project_dir=project)
    assert out["permissionDecision"] == "deny"


def test_new_adr_is_ask(tmp_path):
    project, _ = make_project(tmp_path)
    new = project / "docs" / "decisions" / "0002-new.md"
    out = run_hook({"tool_input": {"file_path": str(new)}}, project_dir=project)
    assert out["permissionDecision"] == "ask"


def test_unrelated_path_is_silent(tmp_path):
    project, _ = make_project(tmp_path)
    other = project / "src" / "module.py"
    out = run_hook({"tool_input": {"file_path": str(other)}}, project_dir=project)
    assert out is None


def test_relative_path_resolves_against_project_dir_not_cwd(tmp_path):
    """The original inline hook's bug: `[ -e ]` on a relative path tested
    against the hook's CWD, so an existing ADR looked absent (-> ask, a
    fail-open). With CWD pointed elsewhere, the existing ADR must still deny."""
    project, _ = make_project(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    out = run_hook(
        {"tool_input": {"file_path": "docs/decisions/0001-existing.md"}},
        project_dir=project,
        cwd=elsewhere,
    )
    assert out["permissionDecision"] == "deny"


def test_relative_adr_without_project_dir_is_denied(tmp_path):
    """Existence cannot be verified without an anchor: deny, never ask."""
    project, _ = make_project(tmp_path)
    out = run_hook(
        {"tool_input": {"file_path": "docs/decisions/0001-existing.md"}},
        project_dir=None,
        cwd=project,  # even with CWD at the project, the anchor is the env var
    )
    assert out["permissionDecision"] == "deny"


def test_malformed_stdin_is_denied(tmp_path):
    project, _ = make_project(tmp_path)
    out = run_hook("this is not json", project_dir=project)
    assert out["permissionDecision"] == "deny"


def test_payload_without_path_is_denied(tmp_path):
    project, _ = make_project(tmp_path)
    out = run_hook({"tool_input": {}}, project_dir=project)
    assert out["permissionDecision"] == "deny"


def test_dotdot_disguise_is_denied(tmp_path):
    """A path that only normalizes into docs/decisions/ is still an ADR."""
    project, _ = make_project(tmp_path)
    disguised = project / "docs" / "method" / ".." / "decisions" / "0001-existing.md"
    out = run_hook({"tool_input": {"file_path": str(disguised)}}, project_dir=project)
    assert out["permissionDecision"] == "deny"


def test_notebook_path_is_covered(tmp_path):
    """NotebookEdit sends notebook_path, not file_path; the guard reads both."""
    project, adr = make_project(tmp_path)
    out = run_hook({"tool_input": {"notebook_path": str(adr)}}, project_dir=project)
    assert out["permissionDecision"] == "deny"
