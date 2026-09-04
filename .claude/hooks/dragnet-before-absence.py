#!/usr/bin/env python3
# vendored from armory @ 1469e7a (2026-09-02) -- .claude/hooks/dragnet-before-absence.py
# UNMODIFIED below this block. md5 of the upstream body: 172c5097430083b333fef2ded1211e15
# Re-copy rather than edit: a local fix here is a fork nobody else gets.
# Upstream is the place to change it. See CONTRIBUTING.md.
"""PostToolUse gate. A search that came back EMPTY is checked against every other place
the thing could be, before the session gets to call it absent.

WHY THIS IS PostToolUse AND NOT PreToolUse, WHICH IS WHAT THIS ESTATE USUALLY WRITES.
The other gates here -- no-heredoc-source.sh, the-folder-is-the-input.sh -- can see the
mistake in the command itself and refuse it. This one cannot. `grep foo` and `ls tools/foo.py`
are correct commands; nothing is wrong with running them. The mistake happens one step later,
when a zero-result working-tree search gets read as "it does not exist". So the trigger is
the RESULT, not the command, and the hook costs nothing on any search that succeeded.

IT ANSWERS, IT DOES NOT ONLY WARN -- the same argument the-folder-is-the-input.sh makes for
itself. A hook that said "your search may be incomplete" would leave the session exactly as
stuck as it was. This one runs `tools/dragnet.py --fast` and hands back the branch the file
is actually on and the `git show` that retrieves it. If dragnet finds nothing off-tree, the
hook stays silent: the empty search was telling the truth and there is nothing to add.

WHAT --fast COSTS. Working tree, sibling worktrees (dirty files only -- the rest is covered
by refs), every branch/remote-tracking ref/tag, and the stash. About a second here, 5.6s on
interface2 with 227 refs and 35 worktrees, and only ever after a search that already failed.
History, reflog-only commits, unreachable objects and the remote are NOT swept in --fast; the
message says so, so silence from this hook is never evidence of absence. That claim needs the
full sweep, which is `python3 tools/dragnet.py TERM` with no flags.

SELF-CONFIGURING. It locates dragnet from its own path, so this file and tools/dragnet.py can
be copied into any repo unchanged -- the property that made session-start.sh the one
instrument in this estate that travelled.

EXIT  0 always. This gate never blocks; it only adds what the search missed.
      python3 .claude/hooks/dragnet-before-absence.py --selftest   to check it still fires.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DRAGNET = Path(__file__).resolve().parents[2] / "tools" / "dragnet.py"
TIMEOUT = 45
MIN_TERM = 3

# a result that means "nothing found", across the tools that can report one
EMPTY = re.compile(r"^\s*$|no matches found|no files found|found 0 |0 matches|0 files",
                   re.I)
MISSING_PATH = re.compile(r"([\w./~@+-]+):?\s*(?:No such file or directory"
                          r"|does not exist|cannot find|not found)", re.I)
REGEXISH = re.compile(r"[\\^$.|?*+()\[\]{}]")


def looked_empty(resp):
    text = resp if isinstance(resp, str) else json.dumps(resp)
    if isinstance(resp, dict):
        text = "\n".join(str(resp.get(k, "")) for k in
                         ("content", "stdout", "output", "result", "stderr")) or text
    return bool(EMPTY.search(text.strip()[:4000])), text


def term_from(tool, tool_input, text):
    """What did this session fail to find? Empty string means 'not an existence question'."""
    if tool in ("Grep", "Glob"):
        pat = str(tool_input.get("pattern", "")).strip()
        if tool == "Glob":                      # **/build_ecdf*.py -> build_ecdf
            pat = re.split(r"[*?\[]", Path(pat).name)[0].strip("._-")
        return pat
    if tool == "Bash":                          # ls: tools/x.py: No such file or directory
        m = MISSING_PATH.search(text)
        return m.group(1) if m else ""
    return ""


def sweep(term, cwd, regex):
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out = Path(tf.name)
    cmd = [sys.executable, str(DRAGNET), term, "--fast", "--offline", "--no-escalate",
           "--json", str(out)] + (["--regex"] if regex else [])
    try:
        subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT)
        data = json.loads(out.read_text()) if out.stat().st_size else {}
    except (subprocess.TimeoutExpired, OSError, ValueError, json.JSONDecodeError):
        return []
    finally:
        out.unlink(missing_ok=True)
    return [f for repo in data.values() for f in repo["finds"] if not f["in_tree"]]


def message(term, finds):
    paths = [f for f in finds if f["kind"] == "path"]
    content = [f for f in finds if f["kind"] == "content"]
    lines = [f"Your search for {term!r} came back empty, but it is NOT absent. "
             f"dragnet found it off this checkout:"]
    for f in (paths + content)[:8]:
        where = ", ".join(f["locations"][:3])
        lines.append(f"  {f['kind']:7s} {f['path']}  --  {where}")
        if f["recover"]:
            lines.append(f"          $ {f['recover']}")
    if len(paths) + len(content) > 8:
        lines.append(f"  ... {len(paths) + len(content) - 8} more")
    lines += [
        "",
        "This is committed work that is not on the branch you have checked out. Read it "
        "before writing anything new against this name -- in this estate 34 of 306 tools "
        "are stranded off trunk, and the usual cost of missing one is that it gets "
        "rewritten.",
        f"Full sweep, including history, deleted paths, reflog-only commits and the "
        f"remote: python3 tools/dragnet.py {term!r} (add --estate for every repo).",
    ]
    return "\n".join(lines)


def run(payload):
    """Returns the additionalContext string, or '' to stay silent."""
    if payload.get("hook_event_name") != "PostToolUse":
        return ""
    tool = payload.get("tool_name", "")
    if tool not in ("Grep", "Glob", "Bash"):
        return ""
    empty, text = looked_empty(payload.get("tool_response", ""))
    if not empty and tool != "Bash":
        return ""
    term = term_from(tool, payload.get("tool_input", {}) or {}, text)
    if len(term) < MIN_TERM or term in (".", "..", "*"):
        return ""
    regex = tool == "Grep" and bool(REGEXISH.search(term))
    if regex:
        try:
            re.compile(term)
        except re.error:
            regex = False
    finds = sweep(term, payload.get("cwd") or ".", regex)
    return message(term, finds) if finds else ""


def selftest():
    """Fires on a stranded path, stays silent on everything else -- all of it on a fixture.

    EVERY CASE USED TO RUN AGAINST THE LIVE REPOSITORY, and that is a bug this file has now
    had twice. The first version probed a named repo in ~/Developer, which passed on one
    laptop and could not run in CI at all. The replacement still pointed four of its cases at
    armory itself, and on 2026-09-02 it went red for a reason that was nobody's mistake: a
    sibling worktree gained a documentation line mentioning `dragnet.py`, so a term that had
    been "in the working tree and nowhere else" acquired an off-tree hit, and the assertion
    expired underneath a correct tool. Four sessions were editing that checkout.

    A selftest whose result depends on what else is in the repository is not testing the
    thing it names. All of it is hermetic now: one fixture, built here, thrown away after.
    """
    import subprocess
    import tempfile
    bad = 0

    def check(cond, why):
        nonlocal bad
        print(f"  {'ok ' if cond else 'FAIL'}  {why}")
        bad += not cond

    with tempfile.TemporaryDirectory() as t:
        r = Path(t) / "fixture"
        (r / "tools").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
        g = lambda *a: subprocess.run(["git", "-C", str(r)] + list(a),
                                      capture_output=True, check=True)
        g("config", "user.email", "t@t"); g("config", "user.name", "t")
        (r / "tools" / "present_tool.py").write_text("# on the trunk and nowhere else\n")
        g("add", "-A"); g("commit", "-qm", "trunk")
        g("checkout", "-q", "-b", "side")
        (r / "tools" / "stranded_probe.py").write_text("# why: never merged\n")
        g("add", "-A"); g("commit", "-qm", "side work")
        g("checkout", "-q", "main")
        repo = str(r)

        for payload, want, why in [
            ({"hook_event_name": "PostToolUse", "tool_name": "Grep", "cwd": repo,
              "tool_input": {"pattern": "present_tool"}, "tool_response": "No matches found"},
             False, "a term that IS in this working tree must not fire"),
            ({"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": repo,
              "tool_input": {"command": "ls tools/zzq_nope.py"},
              "tool_response": "ls: tools/zzq_nope.py: No such file or directory"},
             False, "a name that is nowhere must stay silent"),
            ({"hook_event_name": "PostToolUse", "tool_name": "Write", "cwd": repo,
              "tool_input": {}, "tool_response": ""}, False, "non-search tools are ignored"),
            ({"hook_event_name": "PostToolUse", "tool_name": "Grep", "cwd": repo,
              "tool_input": {"pattern": "x"}, "tool_response": ""},
             False, "short terms skipped"),
        ]:
            check(bool(run(payload)) == want, why)

        out = run({"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": repo,
                   "tool_input": {"command": "ls tools/stranded_probe.py"},
                   "tool_response":
                   "ls: tools/stranded_probe.py: No such file or directory"})
        check("stranded_probe" in out and "git" in out,
              "an empty ls on a stranded path fires and names the branch")
        check("side" in out, "and the branch it names is the one holding it")

        # A SEARCH THAT FOUND SOMETHING MUST NOT BE SECOND-GUESSED. The whole cost argument
        # for this gate is that it is free on every successful search; a version that swept
        # regardless would be silent about it and merely slow, so it needs its own case.
        noisy = run({"hook_event_name": "PostToolUse", "tool_name": "Grep", "cwd": repo,
                     "tool_input": {"pattern": "stranded_probe"},
                     "tool_response": "tools/other.py:1:stranded_probe is referenced here"})
        check(not noisy, "a search that DID return results is left alone")

    print("selftest:", "PASS" if not bad else "RED")
    return 1 if bad else 0


def main():
    if "--selftest" in sys.argv:
        # ALWAYS SPEAK A VERDICT, EVEN WHEN THE THING UNDER TEST RAISES. A crash-shaped
        # break prints a traceback to stderr and NOTHING to stdout, so there is no last line
        # for a caller to read -- worse than a misleading one, because mutation_check.sh
        # then scores the row MISSED and it reads as a weak test rather than a broken tool.
        # Found by armory-eb in the hook; the same hole was in all three files I own.
        try:
            return selftest()
        except Exception as e:                             # noqa: BLE001
            print(f"  FAIL  selftest raised {type(e).__name__}: {e}")
            print("selftest: RED")
            return 1
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    try:
        ctx = run(payload)
    except Exception:                                  # noqa: BLE001 -- never break a session
        return 0
    if ctx:
        json.dump({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                          "additionalContext": ctx},
                   "systemMessage": "dragnet: that search was empty, but the thing exists "
                                    "off this checkout"}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
