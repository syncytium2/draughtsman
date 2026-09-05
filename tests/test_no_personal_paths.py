"""No tracked file spells an absolute home directory. This repository is public.

WHAT WENT OUT. `lit/README.md` told a reader to run

    export MURDERBOARD_LIT=/Users/<name>/Developer/draughtsman/lit

in a fenced block, on a repository that became public on 2026-09-03. It publishes
the owner's username, and it is also simply WRONG for everyone else: nobody else's
clone is at that path, so an instruction written to be copied could not work for
any reader who copied it. The next line of the same block already said
`cd ~/Developer/...`, so the file disagreed with itself.

THE RULE IS CARRIED, NOT INVENTED. bugarach's `tools/sapper.py` blocks this at
commit time as SAP004, and its comment records the same defect reaching a public
repository and staying there:

    a home directory spelled in lowercase -- /Users/<name>/Developer/... -- matched
    none of them, and tools/matlab_ref/prep_ref_input.py carried two of those in a
    PUBLIC repo from the day it was written until 2026-08-20. A rule that covers
    the shape you thought of is worth less than it looks.

So the pattern here is the general one -- any absolute path under a user's home --
rather than the specific string that happened to leak. SAP004 additionally matches
a university prefix, `DeFazio/` and `Dropbox/`; those are not spelled out here
because writing them as literals would make this file match itself, which is the
kind of exemption that later gets widened. **If this repository ever needs the
fuller rule, vendor the sapper rather than re-deriving it** -- the estate has one
implementation and this is a second answer to a question it already answered.

WHY A TEST AND NOT A HOOK. bugarach's fires at commit time, which is better, and
this repository has no commit-time gate to hang it on. A test runs in CI on every
push, which is late but is at least somewhere nobody can forget to install.
"""

from __future__ import annotations

import re
import subprocess

from conftest import ROOT

#: Any absolute path under a home directory. Written as a pattern rather than as
#: the string that leaked, because the leaked string is the one case already
#: fixed. Note this expression does not contain a literal match for itself.
HOME_PATH = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    return [p for p in out.stdout.split("\n") if p]


def test_no_tracked_file_spells_an_absolute_home_directory():
    hits = []
    for rel in _tracked():
        path = ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue                      # binary, or a path git knows and disk does not
        if rel == "tests/test_no_personal_paths.py":
            continue                      # the rule's own statement, not an instance
        for n, line in enumerate(text.split("\n"), 1):
            if HOME_PATH.search(line):
                hits.append(f"{rel}:{n}: {line.strip()[:110]}")
    assert not hits, (
        "tracked files spell an absolute home directory, and this repository is "
        "public:\n  " + "\n  ".join(hits)
        + "\n\nWrite the path so it works in someone else's clone -- "
          '`$(git rev-parse --show-toplevel)` for a path inside this repository, '
          "`~/` for one outside it.")


def test_the_check_can_fail():
    """A guard that cannot fire is the defect this repository keeps finding.

    The string is BUILT rather than written, so this test does not plant the very
    thing the check above searches for.
    """
    planted = "/" + "Users" + "/someone/Developer/x"
    assert HOME_PATH.search(planted), (
        "the pattern no longer matches an absolute home path, so the check above "
        "is passing because it looks at nothing")
    assert not HOME_PATH.search("~/Developer/x"), "a tilde path is not a leak"
    assert not HOME_PATH.search("$(git rev-parse --show-toplevel)/lit"), (
        "the recommended replacement must not itself trip the rule")
