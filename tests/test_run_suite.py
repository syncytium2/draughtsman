"""The local runner has to be able to fail, or it is worse than not having one.

`tools/run_suite.py` exists because pytest is not installed on the machines this
repository is written on: test modules `import pytest` at the top and cannot be
imported here, so a session can run no test locally and learns about a mistake
from CI. That happened on 2026-09-04 -- a claim named the figures a layout change
would re-render but not `tests/test_layout.py`, which asserted the route-point
count the change altered, and `main` went red on the commit.

A stand-in for pytest is a checker, and this repository's recurring defect is a
checker that cannot fail in the direction it exists for. The improvised version of
this shim had exactly that bug: its `raises` returned True from `__exit__` for
everything, so every `pytest.raises` block passed whether or not the exception
came -- twelve tests across six files, green and proving nothing. So the mutation
below is that bug, and it must break the runner's own selftest.

These tests never call `run()`. Under real pytest that would import and execute
the suite a second time from inside itself.
"""

from __future__ import annotations

import os
import subprocess
import sys

from conftest import ROOT

TOOL = ROOT / "tools" / "run_suite.py"


def test_the_runner_selftest_passes():
    r = subprocess.run([sys.executable, str(TOOL), "--selftest"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_runner_can_fail():
    """THE ONLY VERSION OF THE TEST ABOVE THAT MEANS ANYTHING.

    `raises` that swallows everything is the bug this tool shipped with in its
    scratch form, and it is invisible: the suite goes green and the assertions it
    was carrying stop being assertions.
    """
    src = TOOL.read_text(encoding="utf-8")
    good = "        if exc_type is None:\n            raise AssertionError("
    assert good in src, (
        "the raises guard has been rewritten; this mutation no longer reproduces "
        "the defect it guards, so it is not guarding anything")
    broken = src.replace(good, "        if False:\n            raise AssertionError(", 1)
    # `__file__` because the module derives ROOT from its own location, and an
    # exec namespace has none.
    ns: dict = {"__name__": "run_suite_mutated", "__file__": str(TOOL)}
    exec(compile(broken, "run_suite_mutated", "exec"), ns)      # noqa: S102
    # A broken guard may fail loudly rather than return non-zero -- with the None
    # check gone, `issubclass(None, ValueError)` raises TypeError. Either is the
    # mutant failing; only a clean 0 would mean the selftest is not looking.
    try:
        outcome = ns["selftest"]()
    except Exception as exc:                       # noqa: BLE001
        outcome = f"raised {type(exc).__name__}"
    assert outcome != 0, (
        "a `raises` that never fires still passed the runner's selftest, so the "
        "selftest is not checking the thing it names")


def test_the_runner_states_what_it_could_not_run():
    """A PARTIAL RUNNER THAT READS AS A FULL ONE IS THE SAME BUG AGAIN.

    It cannot run everything -- torch is absent on these machines, and some
    fixtures it does not know how to build -- and a summary that omits that count
    invites the reader to treat a local pass as CI. Three instruments here failed
    this way in one day by reporting as fine what they had not examined, so the
    count of unrun tests is part of the result rather than a footnote.
    """
    src = TOOL.read_text(encoding="utf-8")
    assert "NOT RUN, of" in src, (
        "the summary no longer states how many tests were not run")
    assert "CI is still the verdict" in src, (
        "the summary no longer says that CI, not this tool, decides")
    # A module that will not import was never filtered by the selector, so
    # counting it inside the selection reads as one of your cases vanishing --
    # which is the single thing someone running one test must not have to guess
    # about. Reported by `draughtsman-b2` on first use.
    assert "could not be imported at all" in src, (
        "module-level import failures are no longer separated from the "
        "selection's own NOT RUN count")


def test_nothing_under_test_can_block_on_stdin():
    """A HANG IS A RUNNER THAT NOBODY LEAVES RUNNING.

    `test_hooks` runs the session hooks and a hook reads its payload from stdin.
    Alone it finished in 0.1s; after the rest of the suite it blocked until the
    per-test deadline killed it, and before there was a deadline it took the whole
    run with it silently. The runner hands every test -- and every subprocess a
    test starts, which is why this is done at the file-descriptor level -- a stdin
    that is already at end of file.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import run_suite

    with run_suite._null_stdin():
        assert os.read(0, 1) == b"", "stdin returned data instead of EOF"
