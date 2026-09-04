#!/usr/bin/env python3
# vendored from armory @ 18e7197 (2026-09-02) -- tools/dragnet.py
# UNMODIFIED below this block. md5 of the upstream body: f6693f39aea937610a92a71c6f95fd6b
# Re-copy rather than edit: a local fix here is a fork nobody else gets.
# Upstream is the place to change it. See CONTRIBUTING.md.
# instrument: retrieval
"""Search every place a commit can hide before anyone is allowed to say "it does not exist".

A working-tree grep answers one question: is it on the branch I have checked out, right now.
In this estate that is a bad proxy for existence -- tools sit committed and off trunk, some
were deleted outright, and every repo carries sibling worktrees whose uncommitted work is in
no ref at all. Stranded code reads exactly like code that was never written, and the wrong
conclusion is expensive: it gets rewritten.

So this refuses to report absence cheaply. It sweeps nine layers -- working tree, sibling
worktrees, every branch/remote-tracking ref/tag, the stash, history by pickaxe, paths that
have left every ref, commits only the reflog can still reach, unreachable objects, and refs
that exist on the server and have never been fetched here -- and prints the status of each.
Findings are reported per artefact, not per grep line: one row per path, with where the best
copy lives, the command that retrieves it, and the first comment block of the file it found,
because that is where this estate records why a tool exists. A hit outside your checkout is
marked OFF-TREE, because that is the case that gets miscalled.

If any layer could not be searched, the verdict is INCONCLUSIVE. Absence is a claim, and it
is only earned when every layer actually ran. Layers you decline (--deep, --offline) are
reported as declined rather than folded into a clean answer.

The git primitives are estate.py, shared with the manifest pipeline. This script used to
carry its own copies of five of them, which in a repository built to end exactly that
duplication was not a defensible place to keep them.

  exit 0  found          exit 1  searched everywhere, genuinely absent
  exit 2  INCONCLUSIVE   exit 3  usage

  dragnet.py fetch_paper                 # this repo, all layers, then the estate if clean
  dragnet.py 'def burst_width' --regex   # content by regex
  dragnet.py TERM --estate --deep        # every repo in ~/Developer, unreachable objects too
  dragnet.py --selftest                  # prove the refs and history layers can go red
"""
import argparse
import json
import re
import sys
import threading
from pathlib import Path

import estate
from estate import git, pmap, short_ref

CAP_TREES = 400          # unique ref tips whose file lists we enumerate without --deep
CAP_OBJECTS = 4000       # unreachable objects read in --deep
NET_TIMEOUT = 25

BOLD, DIM, OFF = "\x1b[1m", "\x1b[2m", "\x1b[0m"
if not sys.stdout.isatty():
    BOLD = DIM = OFF = ""


def grep(repo, *args, timeout=120):
    """git grep exits 1 for 'no match', which is an answer, not a failure."""
    return git(repo, "grep", *args, ok=(0, 1), timeout=timeout)


class Layer:
    """One place a commit can hide. Whether it was searched is part of the answer."""

    def __init__(self, name):
        self.name, self.status, self.note, self.n = name, "clean", "", 0

    def failed(self, why):
        self.status, self.note = "FAILED", why

    def skipped(self, why):
        if self.status == "clean":
            self.status, self.note = "skipped", why


class Find:
    """One artefact, wherever it turned up. Locations accumulate; the path is the identity."""

    def __init__(self, path, kind):
        self.path, self.kind = path, kind
        self.locations, self.samples, self.recover, self.in_tree = [], [], "", False
        self.why = ""

    def at(self, where, recover="", sample=""):
        if where not in self.locations:
            self.locations.append(where)
        if recover and not self.recover:
            self.recover = recover
        if sample and len(self.samples) < 2 and sample not in self.samples:
            self.samples.append(sample)


class Hunt:
    def __init__(self, term, args):
        self.term, self.args = term, args
        self.rx = re.compile(term if args.regex else re.escape(term),
                             0 if args.case else re.I)
        self.grep_opts = (["-I", "-n", "-e", term]
                          + ([] if args.regex else ["-F"])
                          + ([] if args.case else ["-i"]))

    # -- per-repo state ----------------------------------------------------
    def start(self, repo):
        self.repo, self.finds, self.layers = repo, {}, []
        self.lock = threading.Lock()
        self.tree_files = set((git(repo, "ls-files", "-co", "--exclude-standard") or "")
                              .splitlines())
        # A CLONE CAN BE TRUNCATED, AND THEN THIS TOOL LIES IN ITS OWN VOICE. A shallow
        # clone has no history behind the cut and a single-branch clone has no other refs,
        # so the layers that answer "was it ever here" return empty for a reason that is
        # nothing to do with the term. Measured: the same search that reports FOUND in a
        # full clone reported "Absence is established" in a `--depth 1 --single-branch`
        # copy of it. That is the exact false negative this whole tool exists to prevent,
        # produced by the environment CI checks it out into -- `actions/checkout` is
        # shallow and single-branch by default, which armory's own workflow used.
        # A precondition a portable instrument assumes is one it eventually gets wrong;
        # flagged by armory-d1 carrying it from draughtsman-65, who hit it in a CI check
        # that reported a bad claim when what it had was a bad checkout.
        self.shallow = (git(repo, "rev-parse", "--is-shallow-repository")
                        or "").strip() == "true"
        fetch = git(repo, "config", "--get-all", "remote.origin.fetch") or ""
        self.single_branch = bool(fetch.strip()) and "*" not in fetch

    def find(self, path, kind):
        key = (path, kind)
        with self.lock:
            if key not in self.finds:
                f = Find(path, kind)
                f.in_tree = path in self.tree_files
                self.finds[key] = f
            return self.finds[key]

    def note_path(self, layer, path, where, recover=""):
        if not self.rx.search(path):
            return
        f = self.find(path, "path")
        with self.lock:
            f.at(where, recover)
        layer.n += 1
        if layer.status == "clean":
            layer.status = "HIT"

    def note_grep(self, layer, out, where, ref_prefixed):
        """git grep output -> content finds, one per path rather than one per line."""
        for ln in out.splitlines():
            parts = ln.split(":", 3 if ref_prefixed else 2)
            if len(parts) < (4 if ref_prefixed else 3):
                continue
            path, lineno, text = (parts[1], parts[2], parts[3]) if ref_prefixed \
                else (parts[0], parts[1], parts[2])
            where_ = f"{where}:{short_ref(parts[0])}" if ref_prefixed else where
            f = self.find(path, "content")
            with self.lock:
                f.at(where_, sample=f"{lineno}: {text.strip()[:120]}")
            layer.n += 1
            if layer.status == "clean":
                layer.status = "HIT"

    # -- layers ------------------------------------------------------------
    def working_tree(self):
        L = Layer("working tree")
        if git(self.repo, "ls-files") is None:
            L.failed("git ls-files failed")
        for p in self.tree_files:
            self.note_path(L, p, "working tree")
        out = grep(self.repo, "--untracked", *self.grep_opts)
        if out is None:
            L.failed("git grep failed")
        else:
            self.note_grep(L, out, "working tree", False)
        return L

    def worktrees(self):
        """Sibling checkouts. Their uncommitted work exists in no ref anywhere."""
        L = Layer("worktrees")
        porc = git(self.repo, "worktree", "list", "--porcelain")
        if porc is None:
            L.failed("git worktree list failed")
            return L
        paths = [Path(ln.split(" ", 1)[1]) for ln in porc.splitlines()
                 if ln.startswith("worktree ")]
        sib = self.repo.parent / f"{self.repo.name}-worktrees"
        if sib.is_dir():
            paths += [d for d in sorted(sib.iterdir()) if (d / ".git").exists()]
        seen, todo = {self.repo.resolve()}, []
        for wt in paths:
            if wt.exists() and wt.resolve() not in seen:
                seen.add(wt.resolve())
                todo.append(wt)

        def one(wt):
            tag = f"worktree {wt.name}"
            for p in (git(wt, "ls-files", "-co", "--exclude-standard") or "").splitlines():
                self.note_path(L, p, tag, f"cat {wt / p}")
            if self.args.fast:
                # a worktree's COMMITTED content is already covered by the refs layer; only
                # its dirty and untracked files exist nowhere else. Grepping just those is
                # the difference between one second and seven across 35 checkouts.
                dirty = [ln[3:].split(" -> ")[-1].strip('"') for ln in
                         (git(wt, "status", "--porcelain") or "").splitlines() if ln[3:]]
                if not dirty:
                    return
                out = grep(wt, "--untracked", *(self.grep_opts + ["--"] + dirty))
            else:
                out = grep(wt, "--untracked", *self.grep_opts)
            if out is None:
                L.failed(f"grep failed in {wt.name}")
            else:
                self.note_grep(L, out, tag, False)
        pmap(one, todo)
        L.note = (f"{len(todo)} sibling checkout(s)"
                  + (", dirty files only (--fast)" if self.args.fast and todo else ""))
        return L

    def refs(self):
        """Every branch, remote-tracking branch and tag -- the stranded-code layer."""
        L = Layer("refs (branches/tags)")
        allrefs = estate.refs(self.repo)
        if not allrefs:
            L.failed("for-each-ref returned nothing")
            return L, set()
        refnames = [n for _, n in allrefs]
        tips = len({sha for sha, _ in allrefs})
        L.note = f"{len(refnames)} refs, {tips} distinct tips"
        cap = None
        if tips > CAP_TREES and not self.args.deep:
            cap = CAP_TREES
            L.failed(L.note + f" -- path scan capped at {CAP_TREES}, --deep lifts it")

        index = estate.ref_path_index(self.repo, (), tips=cap)
        for p, carriers in index.items():
            self.note_path(L, p, short_ref(carriers[0]),
                           f"git -C {self.repo} show {carriers[0]}:{p}")

        def chunk(i):
            out = grep(self.repo, *(self.grep_opts + refnames[i:i + 40] + ["--"]),
                       timeout=300)
            if out is None:
                L.failed("git grep over refs failed")
            else:
                self.note_grep(L, out, "ref", True)
        pmap(chunk, range(0, len(refnames), 40))
        if self.single_branch:
            note = ("clone is single-branch -- every other ref was never fetched, so a miss "
                    "here is not evidence")
            if L.status == "HIT":
                L.note += " -- " + note
            else:
                L.failed(note)
        return L, set(index)

    def stash(self):
        L = Layer("stash")
        lst = git(self.repo, "stash", "list", "--format=%gd %H %s")
        if lst is None:
            L.failed("git stash list failed")
            return L
        entries = lst.splitlines()
        L.note = f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}"
        for ln in entries:
            f = ln.split()
            if len(f) < 2:
                continue
            gd, sha = f[0], f[1]
            for p in (git(self.repo, "ls-tree", "-r", "--name-only", sha) or "").splitlines():
                self.note_path(L, p, gd, f"git -C {self.repo} show {gd}:{p}")
            out = grep(self.repo, *(self.grep_opts + [sha, "--"]))
            if out is not None:
                self.note_grep(L, out, "stash", True)
        return L

    def history(self, live):
        """Pickaxe over content ever added or removed, plus every path that has left all refs."""
        L = Layer("history")
        pick = ["-G" if self.args.regex else "-S", self.term]
        if not self.args.case:
            pick.append("--regexp-ignore-case")
        out = git(self.repo, "log", "--all", "--reflog", *pick, "--date=short",
                  "--format=%h %ad %s", "-n", "60", timeout=600)
        if out is None:
            L.failed("pickaxe failed")
        else:
            for ln in out.splitlines():
                if not ln.strip():
                    continue
                sha = ln.split()[0]
                f = self.find(f"<commit {sha}>", "commit")
                f.at("history", f"git -C {self.repo} show {sha}", sample=ln.strip()[:140])
                L.n += 1
                if L.status == "clean":
                    L.status = "HIT"

        added = estate.paths_ever_added(self.repo, reflog=True)
        if added is None:
            L.failed("path history walk failed")
            return L
        for p, meta in added.items():
            if p in live or not self.rx.search(p):
                continue
            ref = estate.recover_ref(self.repo, p)
            f = self.find(p, "path")
            f.at(f"history, added {meta['add_date']}",
                 f"git -C {self.repo} show {ref}:{p}" if ref else "",
                 sample=(meta["add_subject"] or "")[:110])
            L.n += 1
            if L.status == "clean":
                L.status = "HIT"
        if self.shallow:
            note = ("clone is SHALLOW -- history is cut, so absence cannot be established "
                    "from it. git fetch --unshallow")
            if L.status == "HIT":
                L.note += " -- " + note
            else:
                L.failed(note)
        return L

    def reflog_only(self):
        """Commits no ref can reach any more -- what amend, reset and rebase drop on the floor."""
        L = Layer("reflog-only commits")
        out = git(self.repo, "log", "--reflog", "--not", "--all", "--date=short",
                  "--format=%h", "-n", "300", timeout=300)
        if out is None:
            L.failed("reflog walk failed")
            return L
        commits = [x for x in out.split() if x]
        L.note = f"{len(commits)} commit(s) no ref can reach"

        def tree(sha):
            for p in (git(self.repo, "ls-tree", "-r", "--name-only", sha) or "").splitlines():
                self.note_path(L, p, f"reflog {sha}", f"git -C {self.repo} show {sha}:{p}")
        pmap(tree, commits)

        def chunk(i):
            hits = grep(self.repo, *(self.grep_opts + commits[i:i + 40] + ["--"]), timeout=300)
            if hits is None:
                L.failed("grep over reflog commits failed")
            else:
                self.note_grep(L, hits, "reflog", True)
        pmap(chunk, range(0, len(commits), 40))
        return L

    def unreachable_objects(self):
        """fsck. Slow, so opt-in -- but it is the only layer that can see an orphaned blob."""
        L = Layer("unreachable objects")
        if not self.args.deep:
            L.skipped("--deep not given")
            return L
        out = git(self.repo, "fsck", "--unreachable", "--no-progress", timeout=900)
        if out is None:
            L.failed("git fsck failed")
            return L
        objs = [ln.split()[1:] for ln in out.splitlines() if ln.startswith("unreachable ")]
        L.note = f"{len(objs)} unreachable object(s)"
        for kind, sha in objs[:CAP_OBJECTS]:
            if kind == "commit":
                for p in (git(self.repo, "ls-tree", "-r", "--name-only", sha)
                          or "").splitlines():
                    self.note_path(L, p, f"dangling {sha[:10]}",
                                   f"git -C {self.repo} show {sha}:{p}")
            elif kind == "blob":
                body = git(self.repo, "cat-file", "blob", sha, timeout=20) or ""
                if self.rx.search(body):
                    f = self.find(f"<blob {sha[:10]}>", "blob")
                    f.at("dangling", f"git -C {self.repo} cat-file blob {sha}")
                    L.n += 1
                    L.status = "HIT"
        if len(objs) > CAP_OBJECTS:
            L.failed(f"read only the first {CAP_OBJECTS} of {len(objs)} objects")
        return L

    def remote_only(self):
        """Refs on the server this clone has never fetched. Unsearchable until it does."""
        L = Layer("remote refs unfetched")
        if self.args.offline:
            L.skipped("--offline")
            return L
        remotes = (git(self.repo, "remote") or "").split()
        if not remotes:
            L.note = "no remote configured"
            return L
        missing = []
        for rem in remotes:
            ls = git(self.repo, "ls-remote", rem, "refs/heads/*", "refs/tags/*",
                     "refs/pull/*/head", timeout=NET_TIMEOUT)
            if ls is None:
                L.failed(f"ls-remote {rem} failed -- offline, or not authenticated")
                continue
            for ln in ls.splitlines():
                sha, _, name = ln.partition("\t")
                if git(self.repo, "cat-file", "-e", sha + "^{commit}") is None:
                    missing.append((rem, name.strip(), sha))
        if missing:
            L.status, L.n = "UNFETCHED", len(missing)
            L.note = (f"{len(missing)} server ref(s) hold commits this clone has never seen; "
                      f"e.g. {missing[0][1]} @ {missing[0][2][:10]} "
                      f"-- git fetch {missing[0][0]} '+refs/*:refs/dragnet/*' to search them")
        return L

    def enrich(self):
        """Give every off-tree path find the first comment block of the file it points at.

        Retrieval is the job, and a filename plus a branch is only half of it -- this estate
        writes why a tool exists in its header, so the answer should carry it."""
        def one(f):
            if f.kind != "path" or f.in_tree or not f.recover:
                return
            m = re.search(r"show ([^:]+):(.+)$", f.recover)
            if m:
                f.why = estate.why(self.repo, m.group(2), m.group(1))[:200]
        pmap(one, list(self.finds.values()))

    def sweep(self, repo):
        self.start(repo)
        self.layers.append(self.working_tree())
        self.layers.append(self.worktrees())
        ref_layer, live = self.refs()
        self.layers.append(ref_layer)
        self.layers.append(self.stash())
        if self.args.fast:
            # the hook path. Only the layers that answer in about a second, and every
            # layer it drops says so, so a --fast miss can never be read as absence.
            for name in ("history", "reflog-only commits", "unreachable objects",
                         "remote refs unfetched"):
                L = Layer(name)
                L.skipped("--fast")
                self.layers.append(L)
        else:
            self.layers.append(self.history(live))
            self.layers.append(self.reflog_only())
            self.layers.append(self.unreachable_objects())
            self.layers.append(self.remote_only())
        self.enrich()
        return self.layers, self.finds


def report(repo, layers, finds, args):
    print(f"\n{BOLD}{repo}{OFF}")
    for L in layers:
        mark = {"HIT": "**", "FAILED": "!!", "skipped": " -",
                "UNFETCHED": "??"}.get(L.status, "  ")
        print(f"  {mark} {L.name:24s} {L.n if L.n else '.':>5}  {L.note}")

    off = [f for f in finds.values() if not f.in_tree]
    intree = [f for f in finds.values() if f.in_tree]
    order = {"path": 0, "content": 1, "commit": 2, "blob": 3}
    for title, group in (("OFF-TREE -- not in this checkout", off),
                         ("in the working tree", intree)):
        if not group:
            continue
        total_in_group = len(group)
        print(f"\n  {BOLD}{title}{OFF}  ({total_in_group})")
        group = sorted(group, key=lambda f: (order[f.kind], f.path))
        # commits and blobs are the weakest evidence -- a pickaxe on a common word returns
        # dozens. Show a few and count the rest; the path rows are the answer.
        shown, per_kind = [], {}
        for f in group:
            per_kind[f.kind] = per_kind.get(f.kind, 0) + 1
            if f.kind in ("commit", "blob") and per_kind[f.kind] > 6:
                continue
            shown.append(f)
        group = shown
        for f in group[:args.max_finds]:
            loc = ", ".join(f.locations[:3]) + (f" +{len(f.locations)-3}"
                                                if len(f.locations) > 3 else "")
            print(f"    {f.kind:7s} {f.path:52s} {loc}")
            if f.why:
                print(f"            {DIM}why: {f.why[:110]}{OFF}")
            for s in f.samples:
                print(f"            {DIM}{s}{OFF}")
            if f.recover and not f.in_tree:
                print(f"            {DIM}$ {f.recover}{OFF}")
        hidden = total_in_group - min(len(group), args.max_finds)
        if hidden > 0:
            print(f"    ... {hidden} more")


def parser():
    ap = argparse.ArgumentParser(
        description="Sweep every layer a commit can hide in before reporting absence.")
    ap.add_argument("term", nargs="?", help="filename fragment and/or content string")
    ap.add_argument("--repo", default=".", help="repo to sweep (default: cwd)")
    ap.add_argument("--estate", action="store_true", help="sweep every repo in ~/Developer")
    ap.add_argument("--regex", action="store_true", help="treat term as a regex")
    ap.add_argument("--case", action="store_true", help="case sensitive")
    ap.add_argument("--deep", action="store_true", help="also fsck for unreachable objects")
    ap.add_argument("--offline", action="store_true", help="skip the remote layer")
    ap.add_argument("--fast", action="store_true",
                    help="working tree, worktrees, refs and stash only -- for the hook")
    ap.add_argument("--no-escalate", action="store_true",
                    help="do not fall through to the estate when this repo is clean")
    ap.add_argument("--json", metavar="FILE", nargs="?", const="dragnet.json")
    ap.add_argument("--max-finds", type=int, default=25)
    ap.add_argument("--selftest", action="store_true")
    return ap


def selftest():
    """Build a repo whose tools are stranded, deleted and present, then require each layer
    to find its own case.

    EACH ASSERTION IS AIMED AT ONE LAYER, so that removing that layer turns this red rather
    than quietly narrowing the sweep -- the failure mode a green selftest is worst at. The
    stranded fixture is invisible without the refs layer; the deleted fixture is invisible
    without the history layer AND without estate.recover_ref stepping back past the deletion;
    and the absent name must stay absent, or the search is matching noise.
    """
    import subprocess
    import tempfile
    ok = True

    def check(cond, msg):
        nonlocal ok
        if not cond:
            print("  FAIL", msg)
            ok = False
        else:
            print("  ok  ", msg)

    with tempfile.TemporaryDirectory() as t:
        r = Path(t) / "fixture"
        (r / "tools").mkdir(parents=True)
        run = lambda *a: subprocess.run(["git", "-C", str(r)] + list(a),
                                        capture_output=True, check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
        run("config", "user.email", "t@t"); run("config", "user.name", "t")
        (r / "tools" / "present.py").write_text("#!/usr/bin/env python3\n# on the trunk\n")
        run("add", "-A"); run("commit", "-qm", "trunk")
        # deleted outright: added on the trunk, then removed. Only history can see it.
        (r / "tools" / "vanished_helper.py").write_text("# why: it computed the tolerance\n")
        run("add", "-A"); run("commit", "-qm", "add helper")
        (r / "tools" / "vanished_helper.py").unlink()
        run("add", "-A"); run("commit", "-qm", "remove it")
        # stranded: committed on a side branch that was never merged. Only refs can see it.
        run("checkout", "-q", "-b", "side")
        (r / "tools" / "stranded_probe.py").write_text("# why: never merged anywhere\n")
        run("add", "-A"); run("commit", "-qm", "side work")
        run("checkout", "-q", "main")

        def sweep(term, **over):
            a = parser().parse_args([term, "--repo", str(r), "--offline", "--no-escalate"])
            for k, v in over.items():
                setattr(a, k, v)
            _, finds = Hunt(term, a).sweep(r)
            return finds

        f = sweep("stranded_probe")
        hit = [x for x in f.values() if x.kind == "path" and not x.in_tree]
        check(any("stranded_probe" in x.path for x in hit),
              "refs layer finds a tool committed only on an unmerged branch")
        check(any("side" in x.recover for x in hit if "stranded_probe" in x.path),
              "and names the branch in a command that retrieves it")

        f = sweep("vanished_helper")
        hit = [x for x in f.values() if x.kind == "path" and not x.in_tree]
        check(bool(hit), "history layer finds a path deleted from every ref")
        rec = next((x.recover for x in hit if "vanished_helper" in x.path), "")
        check(bool(rec), "and offers a command for it")
        if rec:
            m = re.search(r"show ([^:]+):(.+)$", rec)
            body = git(r, "show", f"{m.group(1)}:{m.group(2)}") if m else None
            check(bool(body) and "tolerance" in body,
                  "which actually retrieves the blob past the deletion commit")

        f = sweep("present")
        check(any(x.in_tree for x in f.values()),
              "a file on the trunk is reported as in the working tree, not off-tree")

        f = sweep("zzq_absent_name")
        check(not f, "a name that is nowhere returns nothing")

        # A TRUNCATED CLONE MUST NOT PRODUCE A CONFIDENT ABSENCE. Measured before the fix:
        # the same search that returns FOUND in a full clone returned "Absence is
        # established" in a --depth 1 --single-branch copy of it, which is this tool
        # committing the error it exists to prevent, in the environment CI checks out by
        # default. The fixture is built here rather than assumed about the host.
        shallow = Path(t) / "shallow"
        cp = subprocess.run(["git", "clone", "-q", "--depth", "1", "--single-branch",
                             f"file://{r}", str(shallow)], capture_output=True)
        if cp.returncode == 0:
            a = parser().parse_args(["vanished_helper", "--repo", str(shallow),
                                     "--offline", "--no-escalate"])
            layers, finds = Hunt("vanished_helper", a).sweep(shallow)
            by = {L.name: L for L in layers}
            check(by["history"].status == "FAILED",
                  "a SHALLOW clone marks the history layer unsearchable")
            check("shallow" in by["history"].note.lower(),
                  "and says the clone is why, not the term")
            check(by["refs (branches/tags)"].status == "FAILED",
                  "a SINGLE-BRANCH clone marks the refs layer unsearchable")
            check(not any(not x.in_tree for x in finds.values()),
                  "and it genuinely cannot see the file, so the verdict is all that saves it")
        else:
            check(False, "could not build the shallow fixture: " + cp.stderr.decode()[:80])

    print("selftest:", "PASS" if ok else "RED")
    return 0 if ok else 1


def main(argv=None):
    a = parser().parse_args(argv)
    if a.selftest:
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
    if not a.term:
        print("dragnet: a search term is required", file=sys.stderr)
        return 3

    if a.estate:
        repos = estate.repos()
    else:
        root = git(Path(a.repo).resolve(), "rev-parse", "--show-toplevel")
        if not root or not root.strip():
            print(f"dragnet: {a.repo} is not inside a git repository", file=sys.stderr)
            return 3
        repos = [Path(root.strip())]

    print(f"dragnet: {BOLD}{a.term}{OFF} across {len(repos)} repo(s)", file=sys.stderr)
    hunt, blob, total, degraded, offtree = Hunt(a.term, a), {}, 0, [], 0
    declined = {}
    for repo in repos:
        layers, finds = hunt.sweep(repo)
        report(repo, layers, finds, a)
        total += len(finds)
        offtree += sum(1 for f in finds.values() if not f.in_tree)
        # a layer that could not run is a hole in the evidence; one you declined is a caveat
        degraded += [f"{repo.name}/{L.name}: {L.note or L.status}"
                     for L in layers if L.status in ("FAILED", "UNFETCHED")]
        for L in layers:
            if L.status == "skipped":
                declined.setdefault(f"{L.name} ({L.note})", []).append(repo.name)
        blob[str(repo)] = {
            "layers": [{"layer": L.name, "status": L.status, "note": L.note, "n": L.n}
                       for L in layers],
            "finds": [{"kind": f.kind, "path": f.path, "in_tree": f.in_tree,
                       "locations": [short_ref(x) for x in f.locations],
                       "recover": f.recover, "samples": f.samples, "why": f.why}
                      for f in finds.values()]}

    if total == 0 and not a.estate and not a.no_escalate:
        print("\nnothing here. escalating to the estate before concluding absence.\n",
              file=sys.stderr)
        return main([a.term, "--estate"] + [f for f, on in
                    (("--regex", a.regex), ("--case", a.case), ("--deep", a.deep),
                     ("--offline", a.offline), ("--fast", a.fast)) if on])

    print()
    if a.json:
        Path(a.json).write_text(json.dumps(blob, indent=1))
        print(f"wrote {a.json}")
    if total:
        print(f"{BOLD}FOUND{OFF}  {total} artefact(s) for {a.term!r}; {offtree} of them are "
              f"OFF-TREE. It exists. Recover it, do not rewrite it.")
        return 0
    if degraded:
        print(f"{BOLD}INCONCLUSIVE{OFF}  no hits, but {len(degraded)} layer(s) could not be "
              f"searched:")
        for d in degraded[:12]:
            print(f"   - {d}")
        if len(degraded) > 12:
            print(f"   ... {len(degraded) - 12} more")
        print("Absence is NOT established. Close those layers, then re-run.")
        return 2
    print(f"{BOLD}NOT FOUND{OFF}  {a.term!r} is absent from every searched layer of "
          f"{len(repos)} repo(s): working tree, sibling worktrees, all refs and tags, stash, "
          f"history, paths deleted from every ref, reflog-only commits, and the remote.")
    for what, where in declined.items():
        print(f"   declined: {what} in {len(where)} repo(s)")
    print("Absence is established" + (" for every layer you did not decline." if declined
                                      else "."))
    return 1


if __name__ == "__main__":
    sys.exit(main())
