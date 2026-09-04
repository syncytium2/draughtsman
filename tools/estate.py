#!/usr/bin/env python3
# vendored from armory @ 1469e7a (2026-09-02) -- tools/estate.py
# UNMODIFIED below this block. md5 of the upstream body: 81a7178b8970c1279ef243457c945a70
# Re-copy rather than edit: a local fix here is a fork nobody else gets.
# Upstream is the place to change it. See CONTRIBUTING.md.
"""The one implementation of the git questions every tool in this repo was asking alone.

Six scripts here each grew their own answer to the same five questions -- which repos are
in the estate, how do I call git, what is this repo's trunk, which refs carry this path,
and how do I read a blob that no longer exists. That is the estate's whole complaint
reproduced inside the repository built to end it, at a scale small enough to actually fix.
So it is fixed here first, and this file is the demonstration of the merge armory exists to
perform: one version, every caller reading it, provenance kept in the comments.

Merging them was not cosmetic. It settled three disagreements the copies were having:

  TRUNK. `stranded.py` resolved origin/HEAD and then verified the LOCAL branch of that
  name; `build_armory.py` tried only main then master and had no answer for a repo using
  neither. The local-branch bug is the one instrument_ledger.py names -- "armory's own
  stranded count was derived and wrong, because it resolved trunk against a local branch
  121 commits behind its origin". Measured 2026-09-01 it is 131 behind in interface2,
  which holds 29 of the 34 tools this repo calls stranded. `trunk()` below resolves the
  REMOTE-TRACKING ref, so the question asked is "did this reach the trunk everyone shares",
  not "did it reach my stale checkout".

  FAILURE. Five wrappers disagreed on what a nonzero git means: one raised, one returned
  the empty string, two returned None, one returned None only above rc 1. Here a return of
  None means "this command could not run" and never "there was nothing there" -- the
  distinction dragnet.py's verdict depends on. Commands with a legitimate nonzero, git grep
  above all, pass `ok=(0, 1)`.

  DELETED BLOBS. recover4.py read the parent of the deletion commit; dragnet.py checked
  whether the blob was present and stepped back only if it was not. The second is right and
  subsumes the first: the last commit to TOUCH a path is usually the one that removed it.

Nothing here is estate-specific beyond DEV. The tool filters, the manifest shape and the
report formats stay in the tools that own them.
"""
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DEV = Path(os.environ.get("ESTATE_DIR", Path.home() / "Developer"))

# ARMORY is where the collection is WRITTEN and is overridable, so a pipeline run can be
# tested without touching the real repo. SELF is the checkout this code is running FROM,
# which is a different question and must not be overridable -- it is how a tool recognises
# its own repository. Conflating the two silently disabled a filter under ARMORY_DIR.
ARMORY = Path(os.environ.get("ARMORY_DIR", DEV / "armory"))
SELF = Path(__file__).resolve().parents[1]
WORKERS = 8


def self_repo():
    """The REPOSITORY this code belongs to, as the path `repos()` would list it under.

    `SELF` is the directory the code is running from, and the two differ the moment
    anyone runs the pipeline from a `git worktree` -- which this estate does constantly.
    When they differ, every `== SELF` test silently answers False and the filters that
    depend on it stop filtering: on 2026-09-02 a run from
    `armory-worktrees/<branch>` took armory's own `origin/` collection to be another
    repo's tools and turned 362 manifest rows into 714, which is the same garbage the
    ARMORY_DIR conflation produced and the reason `is_tool` has that guard at all.

    A checkout's identity is its repository. `--git-common-dir` is what knows the
    difference: from a linked worktree it points back at the main checkout's `.git`.
    """
    common = git(SELF, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common and common.strip():
        return Path(common.strip()).parent.resolve()
    return SELF


def git(repo, *args, binary=False, timeout=120, ok=(0,)):
    """stdout, or None when git could not answer. None is never 'nothing was there'."""
    try:
        r = subprocess.run(["git", "-C", str(repo)] + [str(a) for a in args],
                           capture_output=True, timeout=timeout,
                           **({} if binary else {"text": True, "errors": "replace"}))
    except (subprocess.TimeoutExpired, OSError):
        return None
    return r.stdout if r.returncode in ok else None


def pmap(fn, items, workers=WORKERS):
    """git calls are subprocess waits, not computation, so threads are the right lever."""
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, items))


def repos(root=DEV):
    """Every checkout in the estate. A `-worktrees` directory is a sibling, not a repo."""
    return sorted(d for d in Path(root).iterdir()
                  if (d / ".git").exists() and not d.name.endswith("-worktrees"))


def short_ref(name):
    for pre in ("refs/heads/", "refs/remotes/", "refs/tags/"):
        if name.startswith(pre):
            return name[len(pre):]
    return name


def refs(repo, *namespaces):
    """[(sha, full refname)]. FULL, because a short name can collide with a directory --
    armory has an `origin/` folder, and `git grep ... origin` aborts on the ambiguity."""
    ns = namespaces or ("refs/heads", "refs/remotes", "refs/tags")
    out = git(repo, "for-each-ref", "--format=%(objectname) %(refname)", *ns) or ""
    return [(ln.split(" ", 1)[0], ln.split(" ", 1)[1])
            for ln in out.splitlines() if " " in ln]


def trunk(repo):
    """The shared trunk, as a ref that can be read -- remote-tracking wherever one exists.

    Resolving the LOCAL branch instead is the bug that made armory's stranded count wrong;
    see this module's docstring. Falls back to a local branch only when there is no remote
    to be behind."""
    head = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    cands = ([head.strip()] if head and head.strip() else []) + \
            ["origin/main", "origin/master", "main", "master"]
    for c in cands:
        if git(repo, "rev-parse", "--verify", "-q", c + "^{commit}"):
            return c
    return None


def ref_path_index(repo, namespaces=(), tips=None):
    """{path: [full refnames carrying it]} across every ref tip, in one parallel pass.

    Values are FULL refnames for the same reason refs() returns them; callers that print
    them apply short_ref().

    stranded.py used to ask this per path per ref -- an ls-tree for every combination.
    Building the index once is the same answer and is why that script now returns in
    seconds. `tips` caps distinct commits for callers that want a bounded scan."""
    by_commit = {}
    for sha, name in refs(repo, *namespaces):
        by_commit.setdefault(sha, []).append(name)
    items = list(by_commit.items())[:tips] if tips else list(by_commit.items())

    def one(item):
        sha, names = item
        return names, (git(repo, "ls-tree", "-r", "--name-only", sha) or "").splitlines()

    index = {}
    for names, paths in pmap(one, items):
        for p in paths:
            index.setdefault(p, []).extend(names)
    return index


def paths_ever_added(repo, reflog=False):
    """{path: {add_sha, add_date, add_subject}} for every path ever added on any ref.

    The log is newest-first and the dict is overwritten as it walks, so what survives is
    the EARLIEST add -- the date the tool was written, not the date it was last moved."""
    args = ["log", "--all"] + (["--reflog"] if reflog else []) + \
           ["--diff-filter=A", "--name-only", "--format=%x01%H%x02%ad%x02%s", "--date=short"]
    out = git(repo, *args, timeout=600)
    if out is None:
        return None
    added, sha, date, subj = {}, None, None, None
    for line in out.splitlines():
        if line.startswith("\x01"):
            sha, date, subj = line[1:].split("\x02", 2)
        elif line.strip():
            added[line.strip()] = {"add_sha": sha, "add_date": date, "add_subject": subj}
    return added


def recover_ref(repo, path, reflog=True):
    """A ref expression whose blob for `path` exists, or None. Handles the deleted case.

    The last commit to touch a vanished path is usually the commit that DELETED it, where
    the blob is already gone; its parent still holds it. So the presence of the blob is
    checked rather than assumed, and `^` is only appended when it has to be."""
    args = ["rev-list", "--all"] + (["--reflog"] if reflog else []) + ["-1", "--", path]
    last = (git(repo, *args) or "").strip()[:12]
    if not last:
        return None
    for cand in (last, last + "^"):
        if git(repo, "cat-file", "-e", f"{cand}:{path}") is not None:
            return cand
    return None


def preferred_ref(refnames, trunk_short=None):
    """Pick the ref to READ a path from, given every ref that carries it.

    Prefer the trunk, so a tool's recorded `why` is the version the estate actually
    ships rather than whichever branch happened to carry it. Fall back to the first
    ref, because a tool living only on a feature branch still has a reason.
    """
    names = list(refnames or [])
    if not names:
        return None
    if trunk_short:
        for n in names:
            if short_ref(n) == trunk_short:
                return n
    return names[0]


def why(repo, path, ref=None):
    """The first comment block of a file -- where this estate records why a tool exists.

    ALWAYS PASS A REF. Reading the working tree instead was a real defect: `why` came
    back EMPTY for 23 collected tools, because a checkout sits on whatever branch its
    session last left it on and the file is simply not there. bugarach's primary
    checkout was on `declare-instrument-families` when the manifest was built, so
    `tools/check_quotes.py` -- on `origin/main`, and a commit-time gate the estate has
    every reason to know about -- was collected with no reason attached.

    The failure is silent and it reads as absence: an empty `why` looks like a tool
    that never documented itself, which is a judgement about the tool rather than
    about where we looked. The working-tree branch below is kept only for a caller
    holding no ref at all, and it is not what the pipeline uses.
    """
    if ref:
        body = git(repo, "show", f"{ref}:{path}") or ""
    else:
        f = Path(repo) / path
        body = f.read_text(errors="replace") if f.exists() else ""
    out = []
    for ln in body.splitlines()[:40]:
        s = ln.strip()
        if s.startswith("#!"):
            continue
        if s.startswith("#") or s.startswith('"""') or s.startswith("%"):
            out.append(s.lstrip("#% ").strip('"'))
        elif out:
            break
    return " ".join(x for x in out if x)[:400]


def _selftest():
    """Prove trunk() prefers the SHARED trunk, and that `why` reads a ref rather than
    whatever branch a checkout happens to be sitting on.

    Nothing tested the first. The stale-local-trunk defect was the largest finding of the
    merge -- it moved eleven tools out of "stranded" -- and it was protected by no
    assertion anywhere, which the mutation gate found by breaking it and watching every
    selftest stay green.

    The second is the same mistake in a second place, found on 2026-09-02: `why` read the
    WORKING TREE, so 23 tools were collected with no reason attached, because their repo's
    checkout was on some other branch. One fixture covers both, and it is the same file --
    a path that is on `origin/main` and absent from the checked-out branch.

    The fixture is a repo whose local `main` is deliberately behind its `origin/main`, which
    is the exact shape of interface2 at 131 commits behind.
    """
    import subprocess
    import tempfile
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(f"  {'ok ' if cond else 'FAIL'}  {msg}")
        ok = ok and cond

    with tempfile.TemporaryDirectory() as t:
        r = Path(t) / "fixture"
        (r / "tools").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
        g = lambda *a: subprocess.run(["git", "-C", str(r)] + list(a),
                                      capture_output=True, check=True, text=True)
        g("config", "user.email", "t@t"); g("config", "user.name", "t")
        (r / "tools" / "old.py").write_text("# on both\n")
        g("add", "-A"); g("commit", "-qm", "A")
        behind = g("rev-parse", "HEAD").stdout.strip()
        (r / "tools" / "on_shared_trunk.py").write_text("# pushed, not pulled\n")
        g("add", "-A"); g("commit", "-qm", "B")
        ahead = g("rev-parse", "HEAD").stdout.strip()
        # origin/main holds B; the local branch is rewound to A, one commit behind
        g("update-ref", "refs/remotes/origin/main", ahead)
        g("reset", "-q", "--hard", behind)

        check(trunk(r) == "origin/main",
              "with no origin/HEAD, trunk is the remote-tracking ref, not the local branch")
        tree = git(r, "ls-tree", "-r", "--name-only", trunk(r)) or ""
        check("tools/on_shared_trunk.py" in tree,
              "so a tool pushed but not pulled reads as ON the trunk, not stranded")
        check("tools/on_shared_trunk.py" not in (git(r, "ls-tree", "-r", "--name-only",
                                                     "main") or ""),
              "which the local branch alone would have got wrong")

        # The same fixture answers the second defect: that file is on the trunk and NOT
        # in the working tree, which is exactly the shape that emptied `why` for 23
        # collected tools.
        check(why(r, "tools/on_shared_trunk.py") == "",
              "reading the WORKING TREE loses the reason -- the file is not on this branch")
        check(why(r, "tools/on_shared_trunk.py", trunk(r)) == "pushed, not pulled",
              "reading the trunk ref recovers it, which is what the pipeline must do")
        check(preferred_ref(["refs/heads/feature", "refs/remotes/origin/main"],
                            "origin/main") == "refs/remotes/origin/main",
              "preferred_ref takes the trunk over a feature branch carrying the same path")
        check(preferred_ref(["refs/heads/feature"], "origin/main") == "refs/heads/feature",
              "and falls back to a feature branch, since a tool there still has a reason")
        check(preferred_ref([], "origin/main") is None,
              "and answers None when no ref carries it at all")

        # Third instance of one family: a tool identifying ITSELF by its directory.
        # Add a linked worktree and self_repo() must still name the repository, or every
        # `== self_repo()` filter silently stops filtering.
        wt = Path(t) / "linked"
        g("worktree", "add", "-q", "-b", "wt", str(wt))
        real_self = globals()["SELF"]
        try:
            globals()["SELF"] = wt
            check(self_repo() == r.resolve(),
                  "self_repo() from a linked worktree names the REPOSITORY, not the worktree")
            check(Path(SELF).resolve() != r.resolve(),
                  "which the directory alone would have got wrong -- they differ here")
        finally:
            globals()["SELF"] = real_self

        g("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        check(trunk(r) == "origin/main", "origin/HEAD resolves to a remote-tracking ref too")

        # a repo with no remote at all must still answer
        r2 = Path(t) / "local_only"
        r2.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(r2)], check=True)
        subprocess.run(["git", "-C", str(r2), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(r2), "config", "user.name", "t"], check=True)
        (r2 / "f").write_text("x")
        subprocess.run(["git", "-C", str(r2), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(r2), "commit", "-qm", "x"], check=True)
        check(trunk(r2) == "main", "with no remote to be behind, the local branch is the trunk")

    print("selftest:", "PASS" if ok else "RED")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys

    def _guarded():
        """Always speak a verdict, even when the thing under test raises.

        A crash-shaped break prints a traceback to stderr and NOTHING to stdout, so there
        is no last line for a caller to read -- worse than a misleading one, because
        mutation_check.sh then scores the row MISSED and it reads as a weak test rather
        than a broken tool. Found by armory-eb in the hook; the same hole was in all three
        of the files I own.
        """
        try:
            return _selftest()
        except Exception as e:                             # noqa: BLE001
            print(f"  FAIL  selftest raised {type(e).__name__}: {e}")
            print("selftest: RED")
            return 1

    sys.exit(_guarded() if "--selftest" in sys.argv else 0)
