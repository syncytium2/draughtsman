#!/usr/bin/env python3
"""Run this repository's test suite on a machine with no pytest.

    tools/run_suite.py                              # everything it can run
    tools/run_suite.py test_layout                  # one module
    tools/run_suite.py test_layout::test_the_main_chain_comes_out_straight
    tools/run_suite.py chain                        # any substring of module::test
    tools/run_suite.py --list-unrun                 # what it could NOT run, and why
    tools/run_suite.py --selftest

RUNNING ONE TEST IS THE POINT, not running the suite. `draughtsman-b2`, who spent
a session writing tests it could only validate by pushing and reading CI: "what I
could not do locally was not 'run the suite' so much as run ONE test I had just
written." So a selector is a module stem, a `module::test` node id, or any
substring of `module::test[param]`, and an unmatched selector is an error rather
than a quiet run of nothing.

WHY THIS EXISTS
---------------
The suite runs in CI and nowhere else. pytest is not installed on the machines
this repository is written on, and test modules `import pytest` at the top, so
they cannot even be IMPORTED here -- a session cannot run one test, and the first
thing it learns about a mistake is a red `main`.

That happened on 2026-09-04. A claim named the figures a layout change would
re-render but not `tests/test_layout.py`, which asserted the number of route
points a skipping edge produces. The change altered exactly that number. Nothing
local could have said so, and `main` went red on the commit.

WHAT IT IS, AND WHAT IT IS NOT
------------------------------
It installs a small stand-in for `pytest` into `sys.modules`, imports the test
modules against it, resolves their fixtures, and calls them. It is NOT pytest and
must never be mistaken for it: no plugins, no assertion rewriting, no collection
rules, no reporting hooks. **CI remains the verdict.** This is the thing that
tells you not to bother pushing yet.

If real pytest is installed it refuses to run at all rather than shadow it.

KNOWN LOCAL DIFFERENCES, so a failure here is read correctly
-----------------------------------------------------------
`test_reproduces` and `test_trace` need torch, which CI installs and these
machines do not have. They are reported as NOT RUN -- not passed, not failed,
because neither would be true.

`tests/test_claims.py` reads the live board and live git refs, so it reflects what
other sessions are doing right now: a row whose branch has not been pushed yet, or
which names a file that exists only on someone else's branch, fails here and
passes in CI moments later. A failure in that file is a question about the board,
not usually about your change.

THE RULE IT IS BUILT AROUND, and it is this repository's own subject:
A CHECKER MUST NOT BE ABLE TO REPORT AS FINE WHAT IT DID NOT EXAMINE.
Three separate instruments here failed that way in one day -- a collision detector
that summed an edge's separate crossings into one, a mutation guard anchored to a
defect that then got fixed, and a stage-box reader that skipped stages drawing no
rect and reported the figures clean. So this tool never prints a bare "PASS": every
run states how many tests it could not run, and exits non-zero if that number is
unknown. A partial runner that reads as a full one is the same bug again.

The improvised version of this shim got that wrong in the most embarrassing way
available: its `raises` returned True from `__exit__` unconditionally, so every
`pytest.raises` block passed whether or not the exception came -- twelve tests
across six files, green and proving nothing. `raises` below checks the type and
fails when no exception is raised.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import inspect
import io
import os
import shutil
import signal
import sys
import tempfile
import traceback
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"


# --------------------------------------------------------------- the stand-in
class _Raises:
    """`pytest.raises`, and it must be able to fail.

    The version this replaces returned True from __exit__ for everything, which
    swallows the case that matters -- no exception raised at all -- and turns the
    assertion into a no-op that always passes.
    """

    def __init__(self, expected, match=None):
        self.expected = expected
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError(
                f"DID NOT RAISE {getattr(self.expected, '__name__', self.expected)}")
        if not issubclass(exc_type, self.expected):
            return False                   # not ours: let it propagate as a failure
        self.value = exc
        return True


class _Approx:
    def __init__(self, value, abs=None, rel=None):
        self.value = value
        self.tol = abs if abs is not None else 1e-6

    def __eq__(self, other):
        try:
            return abs(other - self.value) <= self.tol
        except TypeError:
            return NotImplemented

    def __repr__(self):
        return f"approx({self.value})"


class _Skipped(Exception):
    """Raised by skip() / importorskip(). Reported as skipped, never as passed."""


class _Mark:
    """`pytest.mark.<anything>`; only parametrize carries meaning here."""

    @staticmethod
    def parametrize(argnames, argvalues, ids=None, **_):
        names = ([n.strip() for n in argnames.split(",")]
                 if isinstance(argnames, str) else list(argnames))

        def deco(fn):
            cases = getattr(fn, "_params", [])
            values = list(argvalues)
            # `ids` is a list OR a callable -- test_payload and
            # test_gallery_imports both pass a lambda, and assuming a list made
            # those two modules unimportable, which the runner then reported as
            # "NOT RUN" rather than as its own bug.
            if callable(ids):
                labels = [str(ids(v)) for v in values]
            elif ids:
                labels = [str(x) for x in ids]
            else:
                labels = None
            cases.append((names, values, labels))
            fn._params = cases
            return fn
        return deco

    def __getattr__(self, _name):
        def anything(*a, **k):
            if len(a) == 1 and callable(a[0]) and not k:
                return a[0]                # bare @pytest.mark.foo
            return lambda fn: fn
        return anything


def _make_pytest() -> types.ModuleType:
    m = types.ModuleType("pytest")
    m.mark = _Mark()
    m.raises = lambda expected, **k: _Raises(expected, **k)
    m.approx = _Approx
    m.skip = lambda *a, **k: (_ for _ in ()).throw(_Skipped(a[0] if a else "skipped"))
    m.fail = lambda msg="", **k: (_ for _ in ()).throw(AssertionError(msg))
    m.xfail = lambda *a, **k: None

    def fixture(*a, **k):
        def wrap(fn):
            fn._fixture_scope = k.get("scope", "function")
            return fn
        if len(a) == 1 and callable(a[0]) and not k:
            return wrap(a[0])
        return wrap
    m.fixture = fixture

    def importorskip(name, *a, **k):
        try:
            return importlib.import_module(name)
        except ImportError:
            raise _Skipped(f"no {name}")
    m.importorskip = importorskip
    m.Skipped = _Skipped
    return m


# ------------------------------------------------------------------- fixtures
class _MonkeyPatch:
    def __init__(self):
        self._undo = []

    def setattr(self, target, name, value=None, raising=True):
        if value is None and isinstance(target, str):
            mod, _, attr = target.rpartition(".")
            target, name, value = importlib.import_module(mod), attr, name
        old = getattr(target, name, None)
        had = hasattr(target, name)
        self._undo.append(lambda: setattr(target, name, old) if had
                          else delattr(target, name))
        setattr(target, name, value)

    def delattr(self, target, name, raising=True):
        old = getattr(target, name)
        self._undo.append(lambda: setattr(target, name, old))
        delattr(target, name)

    def setenv(self, name, value, prepend=None):
        old = os.environ.get(name)
        self._undo.append(lambda: os.environ.__setitem__(name, old) if old is not None
                          else os.environ.pop(name, None))
        os.environ[name] = str(value)

    def delenv(self, name, raising=True):
        old = os.environ.pop(name, None)
        self._undo.append(lambda: os.environ.__setitem__(name, old)
                          if old is not None else None)

    def syspath_prepend(self, path):
        sys.path.insert(0, str(path))
        self._undo.append(lambda: sys.path.remove(str(path)))

    def chdir(self, path):
        old = os.getcwd()
        os.chdir(str(path))
        self._undo.append(lambda: os.chdir(old))

    def undo(self):
        for fn in reversed(self._undo):
            try:
                fn()
            except Exception:
                pass
        self._undo.clear()


class _Captured:
    def __init__(self, out, err):
        self.out, self.err = out, err


class _Capsys:
    def __init__(self):
        self._out, self._err = io.StringIO(), io.StringIO()
        self._ctx = contextlib.ExitStack()
        self._ctx.enter_context(contextlib.redirect_stdout(self._out))
        self._ctx.enter_context(contextlib.redirect_stderr(self._err))

    def readouterr(self):
        out, err = self._out.getvalue(), self._err.getvalue()
        self._out.truncate(0), self._out.seek(0)
        self._err.truncate(0), self._err.seek(0)
        return _Captured(out, err)

    def close(self):
        self._ctx.close()


class Unresolvable(Exception):
    """A fixture this runner does not know how to build."""


def _resolve(name, module, conftest, session_cache, teardown):
    if name == "tmp_path":
        d = Path(tempfile.mkdtemp(prefix="run_suite_"))
        teardown.append(lambda: shutil.rmtree(d, ignore_errors=True))
        return d
    if name == "monkeypatch":
        mp = _MonkeyPatch()
        teardown.append(mp.undo)
        return mp
    if name in ("capsys", "capfd"):
        c = _Capsys()
        teardown.append(c.close)
        return c
    fn = getattr(module, name, None) or getattr(conftest, name, None)
    if fn is None or not callable(fn) or not hasattr(fn, "_fixture_scope"):
        raise Unresolvable(name)
    if fn._fixture_scope == "session" and name in session_cache:
        return session_cache[name]
    args = [_resolve(p, module, conftest, session_cache, teardown)
            for p in inspect.signature(fn).parameters]
    value = fn(*args)
    if fn._fixture_scope == "session":
        session_cache[name] = value
    return value


# -------------------------------------------------------------------- running
def _cases(fn):
    """[(id_suffix, {argname: value})] for a test, one entry when unparametrised."""
    params = getattr(fn, "_params", None)
    if not params:
        return [("", {})]
    out = [("", {})]
    for names, values, ids in reversed(params):
        grown = []
        for i, v in enumerate(values):
            vals = dict(zip(names, v if len(names) > 1 else [v]))
            label = ids[i] if ids else str(i)
            for suffix, acc in out:
                grown.append((f"[{label}]{suffix}", {**acc, **vals}))
        out = grown
    return out


def _module_skippable(selection) -> bool:
    """True when every selector names a module, so others need not be imported."""
    return all("::" in sel or "/" not in sel and sel.startswith("test_")
               for sel in selection)


def _selected(selection, module, name, suffix) -> bool:
    if not selection:
        return True
    node = f"{module}::{name}{suffix}"
    return any(sel == module or sel == f"{module}::{name}" or sel in node
               for sel in selection)


@contextlib.contextmanager
def _null_stdin():
    """Nothing under test may block reading standard input.

    `test_hooks` runs the session hooks, and a hook reads its payload from stdin.
    Run alone it finishes in 0.1s; run after the rest of the suite it blocked
    until the per-test deadline killed it, because by then fd 0 was no longer
    something that returns promptly. pytest does the same thing for the same
    reason -- it swaps sys.stdin for a reader that refuses -- and this is the fd
    level version, so a SUBPROCESS started by a test inherits it too.
    """
    try:
        null = os.open(os.devnull, os.O_RDONLY)
    except OSError:
        yield
        return
    saved = os.dup(0)
    try:
        os.dup2(null, 0)
        yield
    finally:
        os.dup2(saved, 0)
        os.close(saved)
        os.close(null)


class _Timeout(Exception):
    pass


@contextlib.contextmanager
def _deadline(seconds: float):
    """Turn a hang into a legible failure.

    A test here can shell out -- the briefing hook runs git, `test_hooks` runs the
    hook -- and an external call that blocks takes the whole run with it silently.
    A runner that can hang is one nobody leaves running, so the hang is converted
    into a named failure on the test that caused it.
    """
    if not seconds or not hasattr(signal, "SIGALRM"):
        yield
        return

    def fire(_sig, _frm):
        raise _Timeout(f"timed out after {seconds:g}s")

    old = signal.signal(signal.SIGALRM, fire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


#: Imports this repository does not ship. Missing here and present in CI, so a
#: test needing one CANNOT BE JUDGED on this machine -- which is not the same as
#: passing and not the same as failing, and saying either would be a lie.
OPTIONAL = ("torch", "torchvision", "numpy")


def run(selection=None, timeout=30.0):
    """Returns (passed, failures, skipped, unrun, unimported).

    `unrun` is per-test and belongs to the selection: a fixture this runner cannot
    build, or an optional dependency it does not have. `unimported` is per-MODULE
    and does not, because a module that will not import cannot be filtered -- its
    test names were never knowable. Folding the two together made a narrow
    selection ambiguous in the one direction that matters here; see report().
    """
    if "pytest" not in sys.modules:
        sys.modules["pytest"] = _make_pytest()
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(TESTS))
    os.environ.setdefault("DRAUGHTSMAN_NO_SKIPS", "1")
    conftest = importlib.import_module("conftest")

    passed = skipped = 0
    failures, unrun, unimported = [], [], []
    session_cache: dict = {}
    with _null_stdin():
        return _walk(selection, timeout, conftest, passed, skipped,
                     failures, unrun, unimported, session_cache)


def _walk(selection, timeout, conftest, passed, skipped,
          failures, unrun, unimported, session_cache):
    for path in sorted(TESTS.glob("test_*.py")):
        # A module can only be skipped without importing it when every selector
        # says which module it means. A bare substring may match a test name that
        # cannot be known until the module is imported, so those import everything.
        if selection and _module_skippable(selection) and not any(
                sel == path.stem or sel.startswith(path.stem + "::")
                for sel in selection):
            continue
        try:
            module = importlib.import_module(path.stem)
        except Exception as exc:
            unimported.append((path.stem, f"{type(exc).__name__}: {exc}"))
            continue
        for name, fn in sorted(vars(module).items()):
            if not name.startswith("test_") or not callable(fn):
                continue
            if inspect.getmodule(fn) is not module:
                continue
            for suffix, bound in _cases(fn):
                if not _selected(selection, path.stem, name, suffix):
                    continue
                teardown: list = []
                try:
                    args = {p: bound[p] if p in bound
                            else _resolve(p, module, conftest, session_cache, teardown)
                            for p in inspect.signature(fn).parameters}
                except Unresolvable as exc:
                    unrun.append((path.stem, name + suffix, f"fixture {exc}"))
                    for t in teardown:
                        t()
                    continue
                try:
                    with _deadline(timeout):
                        fn(**args)
                    passed += 1
                except _Skipped:
                    skipped += 1
                except _Timeout as exc:
                    failures.append((path.stem, name + suffix, str(exc)))
                except ModuleNotFoundError as exc:
                    if (exc.name or "").split(".")[0] in OPTIONAL:
                        unrun.append((path.stem, name + suffix,
                                      f"needs {exc.name}, not installed here"))
                    else:
                        failures.append((path.stem, name + suffix,
                                         f"ModuleNotFoundError: {exc.name}"))
                except AssertionError as exc:
                    failures.append((path.stem, name + suffix,
                                     str(exc).strip().split("\n")[0][:200]))
                except Exception:
                    failures.append((path.stem, name + suffix,
                                     traceback.format_exc().strip().split("\n")[-1][:200]))
                finally:
                    for t in reversed(teardown):
                        t()
    return passed, failures, skipped, unrun, unimported


def report(selection=None, list_unrun=False, timeout=30.0) -> int:
    passed, failures, skipped, unrun, unimported = run(selection, timeout)
    for mod, name, why in failures:
        print(f"FAIL  {mod}::{name}\n      {why}")
    if list_unrun:
        for mod, name, why in unrun:
            print(f"unrun {mod}::{name}  ({why})")
        for mod, why in unimported:
            print(f"unimported {mod}  ({why})")
    total = passed + len(failures) + skipped + len(unrun)
    # NEVER A BARE PASS. The count it could not run is part of the result, not a
    # footnote -- a partial runner that reads as a full one is the failure this
    # repository keeps finding in its own instruments.
    print(f"\n{passed} passed, {len(failures)} failed, {skipped} skipped, "
          f"{len(unrun)} NOT RUN, of {total} collected"
          + (" in this selection" if selection else ""))
    # AND THE MODULES ARE COUNTED APART FROM THE SELECTION, because they are not
    # in it. A module that will not import never yielded test names to match
    # against, so attributing it to the selection reads as a case that vanished --
    # which is the one thing someone running a single test must not be left
    # guessing about. Reported by `draughtsman-b2`, from first use.
    if unimported:
        names = ", ".join(m for m, _ in unimported)
        plural = "module" if len(unimported) == 1 else "modules"
        print(f"plus {len(unimported)} {plural} that could not be imported at all "
              f"and {'is' if len(unimported) == 1 else 'are'} outside that count: "
              f"{names}")
    print("This is not pytest and CI is still the verdict; "
          + ("see --list-unrun for what it skipped."
             if (unrun or unimported) and not list_unrun
             else "it ran everything it could collect."))
    return 1 if failures else 0


# ------------------------------------------------------------------- selftest
def selftest() -> int:
    fail = 0

    def t(label, ok):
        nonlocal fail
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            fail = 1

    pt = _make_pytest()

    # THE BUG THE IMPROVISED SHIM SHIPPED WITH, and the reason this file exists in
    # the repository rather than in a scratch directory.
    raised = False
    try:
        with pt.raises(ValueError):
            pass                                   # nothing raised
    except AssertionError:
        raised = True
    t("raises() fails when nothing is raised", raised)

    with pt.raises(ValueError):
        raise ValueError("expected")
    t("raises() passes on the expected exception", True)

    wrong = False
    try:
        with pt.raises(ValueError):
            raise KeyError("other")
    except KeyError:
        wrong = True
    t("raises() lets an unexpected exception through", wrong)

    # parametrize has to actually multiply the cases, or the runner silently
    # covers one input and reports a pass for all of them.
    @pt.mark.parametrize("d", [1, 2, 3], ids=["a", "b", "c"])
    def sample(d):
        pass
    t("parametrize expands to one case per value", len(_cases(sample)) == 3)
    t("and carries its ids", [s for s, _ in _cases(sample)] == ["[a]", "[b]", "[c]"])

    def plain():
        pass
    t("an unparametrised test is one case", _cases(plain) == [("", {})])

    t("approx compares within tolerance", _Approx(1.0) == 1.0000001)
    t("approx still refuses a real difference", not (_Approx(1.0) == 1.5))

    print("PASS" if not fail else "FAIL")
    return fail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("modules", nargs="*", help="test module stems, e.g. test_layout")
    ap.add_argument("--list-unrun", action="store_true",
                    help="name every test this runner could not run, and why")
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="per-test seconds before it is failed as a hang (0 = off)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    try:
        import pytest                                          # noqa: F401
    except ImportError:
        pass
    else:
        print("pytest is installed here -- run `pytest -q` instead. This tool is "
              "for machines without it and will not shadow the real one.")
        return 2
    return report(a.modules or None, a.list_unrun, a.timeout)


if __name__ == "__main__":
    sys.exit(main())
