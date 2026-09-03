"""The tools carry selftests, and something has to run them.

A selftest nothing invokes is the same defect one level out: it would pass, and
nobody could say whether it was capable of failing. `pytest` is this repository's
gate, so the gate runs it.

armory's house standard goes further — `mutation_check.sh` breaks each tool at a
named line and requires the matching selftest to flip red. This is the local
half: the selftest runs on every push, and the second test below restores the
original defect and requires the selftest to catch it.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"

WIDE = r'''r"font-size\s*[:=]\s*[\"']?\s*([\d.]+)\s*(px|pt|pc|mm|cm|in|em|rem|%)?",'''
NARROW = r'''r"font-size\s*[:]\s*([\d.]+)\s*(px)",'''


def test_measure_type_selftest_passes():
    r = subprocess.run([sys.executable, str(TOOLS / "measure_type.py"), "--selftest"],
                       capture_output=True, text=True)
    assert r.returncode == 0, (
        "tools/measure_type.py --selftest failed:\n" + r.stdout + r.stderr)


def test_measure_type_selftest_can_fail():
    """THE ONLY VERSION OF THIS TEST THAT MEANS ANYTHING.

    The tool's first pattern read `font-size:7px` and was blind to SVG's own
    `font-size="7"` — and then reported `ok`, so a figure whose every label was
    3pt passed silently. draughtsman happens to emit the CSS form, so the
    selftest was green on the only producer it had ever seen. Found by
    murderboard-7a pointing it at a file this repository did not write.

    So the narrow pattern is restored here and the selftest is required to go
    red, on that case by name. Without this, the test above is decoration.
    """
    src = (TOOLS / "measure_type.py").read_text(encoding="utf-8")
    assert WIDE in src, (
        "the size pattern has moved; this mutation no longer reproduces the "
        "defect it guards, so it is not guarding anything")
    with tempfile.TemporaryDirectory() as td:
        broken = Path(td) / "broken.py"
        broken.write_text(src.replace(WIDE, NARROW, 1), encoding="utf-8")
        r = subprocess.run([sys.executable, str(broken), "--selftest"],
                           capture_output=True, text=True)
    assert r.returncode != 0, (
        "with the narrow pattern restored the selftest still passed, so it does "
        "not test what it claims to")
    assert "presentation attribute" in r.stdout, (
        "the selftest failed, but not on the attribute-form case:\n" + r.stdout)
