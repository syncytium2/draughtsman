"""The hooks and the vendored instruments must be able to fail.

WHY THIS FILE EXISTS AT ALL. This repository states its rules in CLAIMS.md and
DECISIONS.md and enforced none of them at the session boundary: no CLAUDE.md, no
`.claude/settings.json`, no hooks. Tony, quoted in bugarach's
`session_briefing.sh`: "claude.md is the first thing you ignore. we have built
tools for this purpose." A rule written in a file that must be read to be obeyed
is not mechanized.

So the estate's instruments are vendored in, and this is what holds them to their
claims. It is the same argument `tests/test_tools.py` makes for
`tools/measure_type.py` one level out: a selftest nothing invokes would pass, and
nobody could say whether it was capable of failing.

EVERY MUTATION BELOW RESTORES A DEFECT THAT ACTUALLY SHIPPED, rather than breaking
the code in whatever way is easiest to break. A mutation nobody ever made proves
the selftest can fail; a mutation somebody did make proves it can fail *in the
direction the tool exists for*. Where the defect is armory's or interface2's, the
comment says so and names it.

NO NETWORK, NO FETCH. Everything here runs against local refs and temporary
directories, because CI has no remote beyond `origin` and the hooks themselves are
forbidden to fetch (they sit on the blocking path to session start).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".claude" / "hooks"
TOOLS = ROOT / "tools"

# (label, argv) -- everything vendored or written here that claims a selftest.
SELFTESTS = [
    ("draughtsman-briefing.sh", ["bash", str(HOOKS / "draughtsman-briefing.sh"),
                                 "--selftest"]),
    ("dragnet-before-absence.py", [sys.executable,
                                   str(HOOKS / "dragnet-before-absence.py"),
                                   "--selftest"]),
    ("tools/dragnet.py", [sys.executable, str(TOOLS / "dragnet.py"), "--selftest"]),
    ("tools/estate.py", [sys.executable, str(TOOLS / "estate.py"), "--selftest"]),
]


def _run(argv, cwd=ROOT):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=180)


@pytest.mark.parametrize("label,argv", SELFTESTS, ids=[s[0] for s in SELFTESTS])
def test_every_instrument_selftest_passes(label, argv):
    r = _run(argv)
    assert r.returncode == 0, f"{label} --selftest failed:\n{r.stdout}{r.stderr}"


def test_the_briefing_names_the_board_this_repository_actually_has():
    """THE FAILURE THIS GUARDS IS A POINTER TO A BOARD THAT DOES NOT EXIST.

    The vendored generic hook hardcodes `<repo>-worktrees/SESSIONS.md` and
    `docs/session_protocol.md`; draughtsman has neither, and its board is
    `CLAIMS.md`, checked by `tests/test_claims.py`. Left uncorrected the briefing
    invites a session to create a second board -- a hand-maintained pointer going
    stale, in the repository whose subject is hand-maintained pointers going
    stale. The correction is layered rather than forked, so what is checked is
    that the correction is still being said.
    """
    out = _run(["bash", str(HOOKS / "draughtsman-briefing.sh")]).stdout
    assert "CLAIMS.md on origin/main" in out, out
    assert "do not exist" in out, out
    assert not (ROOT / "docs" / "session_protocol.md").exists(), (
        "docs/session_protocol.md now EXISTS, so the briefing is calling a real "
        "file imaginary. Correct the briefing, not this test.")


def test_the_briefing_does_not_report_the_worked_example_as_a_live_claim():
    """CLAIMS.md carries a worked row inside a fenced block for the next session
    to copy. The first version of this hook reported it as an open claim --
    `draughtsman-e9` on `name-every-axis`, a session that no longer exists and a
    branch that landed on 2026-09-02.

    `tests/test_claims.py` skips fenced blocks and explains why; this hook had to
    learn it separately. TWO PARSERS FOR ONE FORMAT is DECISIONS.md correction 5,
    and this assertion is the seam where they are required to agree.
    """
    out = _run(["bash", str(HOOKS / "draughtsman-briefing.sh")]).stdout
    fenced = "name-every-axis" in (ROOT / "CLAIMS.md").read_text()
    assert fenced, (
        "the fenced worked example has moved or gone, so this test no longer "
        "reproduces the case it guards")
    assert "name-every-axis" not in out, (
        "the briefing is reporting CLAIMS.md's documentation as a live claim:\n"
        + out)


def test_the_briefing_selftest_catches_a_parser_that_reads_the_example():
    """The mutation is the defect as it shipped: drop the fenced-block skip."""
    src = (HOOKS / "draughtsman-briefing.sh").read_text()
    skip = '/^```/      { fenced = !fenced; next }     # documentation, not data'
    assert skip in src, (
        "the fenced-block skip has moved; this mutation no longer reproduces the "
        "defect it guards, so it is not guarding anything")
    with tempfile.TemporaryDirectory() as td:
        broken = Path(td) / "draughtsman-briefing.sh"
        broken.write_text(src.replace(skip, "", 1))
        broken.chmod(0o755)
        r = _run(["bash", str(broken), "--selftest"])
    assert r.returncode != 0, (
        "with the fenced example read as data the selftest still passed:\n"
        + r.stdout)
    assert "fenced example read as a live claim" in r.stdout, (
        "the selftest failed, but not on the fenced-example case:\n" + r.stdout)


def test_the_absence_gate_selftest_catches_a_dragnet_it_cannot_reach():
    """THE ONE FAILURE MODE THAT WOULD BE SILENT.

    `dragnet-before-absence.py` locates `tools/dragnet.py` from its own path, and
    it is a PostToolUse hook that stays quiet when it finds nothing off-tree. So a
    dragnet it cannot reach looks exactly like a search that was telling the
    truth: no error, no output, and every empty grep in the session reads as
    absence again. That is the defect the gate was vendored to prevent, arriving
    through the gate itself.

    Vendoring makes this reachable in a way it was not upstream -- the two files
    move independently into each repo, so the path between them is a new seam per
    copy.
    """
    src = (HOOKS / "dragnet-before-absence.py").read_text()
    real = 'parents[2] / "tools" / "dragnet.py"'
    assert real in src, (
        "the hook no longer locates dragnet from its own path; this mutation is "
        "stale")
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / "repo"
        (stage / ".claude" / "hooks").mkdir(parents=True)
        (stage / "tools").mkdir()
        shutil.copy2(TOOLS / "dragnet.py", stage / "tools" / "dragnet.py")
        shutil.copy2(TOOLS / "estate.py", stage / "tools" / "estate.py")
        broken = stage / ".claude" / "hooks" / "dragnet-before-absence.py"
        broken.write_text(src.replace(real, 'parents[2] / "tools" / "gone.py"', 1))
        r = _run([sys.executable, str(broken), "--selftest"], cwd=stage)
    assert r.returncode != 0, (
        "the gate could not reach dragnet and its selftest still passed, so a "
        "silent gate would ship green:\n" + r.stdout + r.stderr)


def test_the_vendored_files_say_where_they_came_from():
    """A COPY IS NOT AUTOMATICALLY A DEFECT, AND THE STAMP IS WHAT SEPARATES THEM.

    armory's README: a file carrying `vendored from <repo> @ <sha>` is one
    canonical source distributed on purpose; several hand-written answers to the
    same problem are the thing that repository exists to end. Reading the stamp is
    how the two are told apart, so an unstamped copy here would be counted as a
    fork of something it is not.
    """
    vendored = {
        ".claude/hooks/session-start.sh": "interface2",
        ".claude/hooks/dragnet-before-absence.py": "armory",
        "tools/dragnet.py": "armory",
        "tools/estate.py": "armory",
    }
    for rel, origin in vendored.items():
        head = (ROOT / rel).read_text().split("\n", 6)[:6]
        stamp = [ln for ln in head if "vendored from" in ln]
        assert stamp, f"{rel} carries no vendoring stamp in its first six lines"
        assert origin in stamp[0], f"{rel} stamp does not name {origin}: {stamp[0]}"


def test_every_hook_fails_open():
    """A hook that blocks is worse than a hook that is missing -- it takes the
    session down, and the SDK's message blames auth and network, so the next
    session debugs the wrong thing. Every hook here exits 0 on a bad day."""
    with tempfile.TemporaryDirectory() as td:
        r = _run(["bash", str(HOOKS / "draughtsman-briefing.sh")], cwd=td)
        assert r.returncode == 0, f"the briefing exited {r.returncode} outside a repo"
        assert r.stdout.strip() == "", (
            "the briefing printed a board outside a git repository:\n" + r.stdout)
        r = _run([sys.executable, str(HOOKS / "dragnet-before-absence.py")], cwd=td)
        assert r.returncode == 0, f"the absence gate exited {r.returncode} on no stdin"


def test_the_settings_file_wires_hooks_that_exist():
    """THE WIRING IS THE POINT; THE FILES ALONE DO NOTHING.

    Four correct instruments in `.claude/hooks/` that no `settings.json` names are
    four files nobody runs -- and they would sit there looking like mechanization
    while the session boundary stayed exactly as unguarded as before. That is a
    worse state than having none, because it reads as done.
    """
    settings = ROOT / ".claude" / "settings.json"
    assert settings.exists(), (
        ".claude/settings.json is missing, so none of the hooks in .claude/hooks/ "
        "are wired and none of them run.")
    conf = json.loads(settings.read_text())
    hooks = conf.get("hooks", {})
    assert hooks.get("SessionStart"), "no SessionStart hook is wired"
    assert hooks.get("PostToolUse"), "no PostToolUse hook is wired"

    commands = [h["command"] for group in hooks.values() for entry in group
                for h in entry.get("hooks", [])]
    assert commands, "settings.json declares hooks but no commands"
    for cmd in commands:
        script = next((tok for tok in cmd.split() if tok.startswith(".claude/")), None)
        assert script, f"cannot find a hook script in the command {cmd!r}"
        path = ROOT / script
        assert path.is_file(), f"settings.json wires {script}, which does not exist"

    # ORDER IS LOAD-BEARING, not cosmetic. bugarach's briefing lost everything past
    # byte 2,000 to a preview on 2026-08-25 and nothing said so. draughtsman's own
    # briefing therefore runs FIRST, so a truncated injection costs the generic
    # tail -- the worktree list and the recent commits -- and never the rules.
    session_start = [h["command"] for entry in hooks["SessionStart"]
                     for h in entry.get("hooks", [])]
    assert len(session_start) >= 2, session_start
    assert "draughtsman-briefing.sh" in session_start[0], (
        "the repo-specific briefing must run FIRST so that truncation costs the "
        f"generic tail rather than the rules. Order is: {session_start}")


# ------------------------------------------------------- the stamp's own claim
#
# The vendored files carry `UNMODIFIED below this block. md5 of the upstream
# body: <hash>`, and until now the only test read the FIRST line of that stamp to
# confirm an origin was named. Nothing compared the hash. A vendored file could
# be edited in place -- the exact thing the next line of the stamp asks nobody to
# do -- and every test stayed green while the file went on claiming to be
# byte-identical to an upstream it no longer matched.
#
# That is DECISIONS.md correction 5 inside the commit that vendored these
# instruments in order to prevent it: a quantity with one correct answer, written
# down, checked by nothing. Raised by draughtsman-4f reading the two outside
# reviews.
#
# WHAT THIS CAN AND CANNOT SEE. It verifies the file against its OWN recorded
# hash, which catches an edit here. It cannot verify against upstream, because
# armory and interface2 are not present in a clone and CI has neither -- a check
# that needs a sibling repository would skip, and a skip is what silence looks
# like when it is being careful. Drift from upstream is a `propagation` problem
# and armory's instrument ledger reports that family as the one that does not
# travel; it belongs there, not here.

STAMP_LINES = 4


def _upstream_body(text: str) -> str:
    """The file as it arrived, before the stamp was inserted.

    The vendoring step puts the stamp immediately after the shebang and changes
    nothing else, so removing those lines reconstructs what was hashed.
    """
    lines = text.split("\n")
    start = 1 if lines and lines[0].startswith("#!") else 0
    return "\n".join(lines[:start] + lines[start + STAMP_LINES:])


@pytest.mark.parametrize("rel", [
    ".claude/hooks/session-start.sh",
    ".claude/hooks/dragnet-before-absence.py",
    "tools/dragnet.py",
    "tools/estate.py",
])
def test_a_vendored_file_still_matches_the_hash_it_claims(rel):
    """UNMODIFIED is a claim, so it is checked like one."""
    text = (ROOT / rel).read_text(encoding="utf-8")
    m = re.search(r"md5 of the upstream body: ([0-9a-f]{32})", text)
    assert m, f"{rel} carries no upstream md5, so its UNMODIFIED claim is unbacked"
    got = hashlib.md5(_upstream_body(text).encode("utf-8")).hexdigest()
    assert got == m.group(1), (
        f"{rel} has been edited: its body hashes to {got} and its stamp claims "
        f"{m.group(1)}. These files are vendored byte-identical on purpose -- a "
        "local fix here is a fork nobody else gets. Change it upstream and "
        "re-copy, or, if the edit is deliberate and stated, say so in the stamp "
        "the way bugarach's mutation_check.sh names its one deviation.")


def test_the_hash_check_notices_an_edited_body():
    """THE ONLY VERSION OF THE TEST ABOVE THAT MEANS ANYTHING.

    A hash test passes on a file nobody has touched whether or not it is
    comparing anything -- which is exactly how the stamp got shipped unchecked in
    the first place. So one byte is changed here and the check is required to
    notice.
    """
    src = (ROOT / "tools" / "dragnet.py").read_text(encoding="utf-8")
    edited = src.replace("CAP_TREES = 400", "CAP_TREES = 401", 1)
    assert edited != src, "the mutation no longer applies; this guard is stale"
    m = re.search(r"md5 of the upstream body: ([0-9a-f]{32})", edited)
    got = hashlib.md5(_upstream_body(edited).encode("utf-8")).hexdigest()
    assert got != m.group(1), (
        "a one-line edit to a vendored file did not change the hash the check "
        "compares, so the check cannot see an edit at all")
