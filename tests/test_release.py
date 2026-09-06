"""The version is written once, and a release cannot disagree with its tag.

THE FAILURE THIS FILE IS NAMED AFTER. `draughtsman-nn` was never uploaded to PyPI
at all -- `pip install draughtsman-nn` returned a 404 for the whole time the
repository was public -- because the standing list in `CLAIMS.md` ran prep, flip
public, Zenodo, JOSS, and never named the upload. The prep commit `d0dd7f1` was
read ever after as the PyPI item being done.

What the prep left behind is the thing worth checking. `version` was a literal in
`pyproject.toml` AND in `src/draughtsman/__init__.py`, which is DECISIONS.md
correction 5 -- and the two had already gone wrong together: both said `0.1.0`
while the tags and the GitHub releases were at `v0.1.1`, and `v0.1.1`'s own tagged
tree says `0.1.0` to this day. Nobody noticed, because nothing had ever built a
distribution and nothing compared the number to the tag.

WHY THAT IS WORSE HERE THAN ANYWHERE ELSE IN THIS REPOSITORY. Every other stale
copy in these tests is a promise that can be corrected in the next commit. PyPI
accepts a version number ONCE -- not once per correct upload, once -- and a wheel
published under the wrong number cannot be replaced, corrected, or re-used after
it is yanked. So the tie between the tag and the number is a gate in the release
workflow rather than an assertion that happens to be green, and this file's job is
to hold that gate to being a gate.

Modelled on `tests/test_dist_name.py` and `tests/test_versions.py`, deliberately:
same shape, same reason, one quantity that must be true in one place.
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "src" / "draughtsman" / "__init__.py"
PUBLISH = ROOT / ".github" / "workflows" / "publish.yml"


def declared() -> str:
    """The one place the number is written. Everything else derives from it."""
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', INIT.read_text(), re.M)
    assert m, (
        f"{INIT.relative_to(ROOT)} no longer declares __version__. pyproject.toml "
        "reads the version from that line, so a build would fail -- and every "
        "assertion below would be checking nothing.")
    return m.group(1)


def _key(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


def _tags() -> list[str]:
    """Version tags this history already contains, newest last.

    `--merged HEAD` and not `--list` alone: a tag on some other branch says
    nothing about the number this tree may take, and reading one as if it did
    would fail a release for a sibling's history.
    """
    out = subprocess.run(["git", "tag", "--list", "v*", "--merged", "HEAD"],
                         cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        return []
    found = [t[1:] for t in out.stdout.split() if re.fullmatch(r"v[\d.]+", t)]
    return sorted(found, key=_key)


def test_the_version_is_a_shape_this_file_can_order():
    """A pre-release suffix is not refused because it is wrong -- it is refused
    because the comparison below does not implement PEP 440 ordering, and would
    silently answer `0.2.0rc1 < 0.2.0` by crashing or, worse, by guessing. Teach
    this file the ordering before shipping a version it cannot sort."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", declared()), (
        f"__version__ is {declared()!r}. Every check in this file orders versions "
        "by splitting on '.' and comparing integers, which is the whole of the "
        "version policy pyproject states. A suffix needs this file taught first.")


def test_pyproject_does_not_write_a_version_of_its_own():
    """THE ONE THIS FILE EXISTS FOR, in the direction it actually failed.

    A literal here is not a harmless duplicate: it is the copy a BUILD reads, so
    when the two disagree the number that reaches PyPI is the one nobody was
    looking at. Restoring `version = "..."` under `[project]` also makes the build
    fail outright while `dynamic` still names it, which is the loud half of this;
    the quiet half is somebody removing `dynamic` at the same time and shipping
    the stale literal.
    """
    text = PYPROJECT.read_text()
    assert re.search(r'^dynamic\s*=\s*\[\s*"version"\s*\]', text, re.M), (
        "pyproject no longer declares the version dynamic, so it is writing a "
        "version of its own again. That number and __version__ are then two "
        "copies of one quantity, and PyPI only ever sees one of them.")
    stray = re.search(r'^version\s*=\s*"', text, re.M)
    assert not stray, (
        "pyproject writes a literal `version = \"...\"` again. It must be read "
        f"from {INIT.relative_to(ROOT)}; see [tool.hatch.version].")


def test_the_build_reads_the_version_from_the_module_that_declares_it():
    """`[tool.hatch.version]` is what makes the single source real, and it points
    at a path by string. A file move that does not update it turns the build
    red -- which is survivable -- but a path that points at some OTHER module
    holding a `__version__` would build quietly and wrongly."""
    m = re.search(r'^\[tool\.hatch\.version\]\s*\npath\s*=\s*"([^"]+)"',
                  PYPROJECT.read_text(), re.M)
    assert m, "pyproject no longer tells hatchling where to read the version"
    assert (ROOT / m.group(1)) == INIT, (
        f"hatchling reads the version from {m.group(1)}, and this file checks "
        f"{INIT.relative_to(ROOT)}. One of them is not the version anybody ships.")


def test_this_checkout_can_see_the_tags_it_is_about_to_judge():
    """THE CHECK MUST REFUSE TO RUN BLIND RATHER THAN PASS BLIND.

    The comparison below is against the tags this history carries. A checkout
    with no tags answers "no tag is newer than the declared version" for every
    version there could ever be -- a guard that has lost its subject and reports
    all clear, which is DECISIONS.md correction 11 and cost this repository five
    instruments in one day.

    `actions/checkout` fetches tags when it is given `fetch-depth: 0`, which the
    test workflow already passes for `tests/test_claims.py`. Locally, `git fetch
    --tags`. Unconditional on purpose: a repository whose releases are tagged has
    tags, and their absence is a broken checkout rather than a state to tolerate.
    """
    assert _tags(), (
        "no v* tags are visible, so the version-versus-tag check below cannot "
        "fail no matter what the version says. In CI, give actions/checkout "
        "`fetch-depth: 0`. Locally, `git fetch --tags`.")


def test_the_declared_version_is_not_behind_a_tag_this_history_already_has():
    """THE DRIFT THAT ACTUALLY HAPPENED, and this test is red on the commit that
    made it: `v0.1.0` and `v0.1.1` were both cut without touching `__version__`,
    which sat at `0.1.0` behind both of them.

    Equal is legal and is the normal state of a release commit. Ahead is legal
    and is the normal state of everything after it. Behind means a tag, a GitHub
    release and a Zenodo deposit are describing a tree that calls itself something
    else -- and it means the next upload would take a number the archive has
    already promised to a different snapshot.
    """
    newest = _tags()[-1]
    assert _key(declared()) >= _key(newest), (
        f"__version__ is {declared()} but this history already carries tag "
        f"v{newest}. The releases were cut without bumping the version -- bump it "
        f"past v{newest} rather than publishing a number that is already spoken "
        "for.")


def _gate_script() -> str:
    """The python the release gate actually runs, lifted out of the workflow.

    THE GATE LIVES IN YAML, WHICH NOTHING IN THIS SUITE EXECUTES. A test that
    grepped the workflow for a reassuring substring would pass over a step that
    had been commented out, inverted, or left with its comparison removed. So the
    script is extracted and RUN, below, against a dist directory built for the
    purpose. If this extraction stops matching, that is a failure too: it means
    the gate has been rewritten into a shape nothing here has ever run.
    """
    m = re.search(r"python - <<'PY'\n(.*?)\n[ \t]*PY\n", PUBLISH.read_text(),
                  re.S)
    assert m, (
        "the release gate's inline python is gone or has changed shape, so the "
        "check below is not running the gate. It is the only thing standing "
        "between a mistyped tag and a permanent PyPI version.")
    return textwrap.dedent(m.group(1))


def _run_gate(tmp_path: Path, tag: str, names: list[str]):
    script = tmp_path / "gate.py"
    script.write_text(_gate_script())
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    for name in names:
        (dist / name).write_bytes(b"")
    return subprocess.run([sys.executable, str(script)], cwd=tmp_path,
                          capture_output=True, text=True,
                          env={"TAG": tag, "PATH": "/usr/bin:/bin"})


def test_the_release_gate_passes_the_tag_it_was_built_for(tmp_path):
    """The gate has to let a correct release through, or the first thing anyone
    does about it is delete it."""
    out = _run_gate(tmp_path, "v9.9.9",
                    ["draughtsman_nn-9.9.9-py3-none-any.whl",
                     "draughtsman_nn-9.9.9.tar.gz"])
    assert out.returncode == 0, (
        f"the gate refused a tag that matches its wheel:\n{out.stdout}{out.stderr}")


def test_the_release_gate_refuses_a_tag_that_is_not_the_built_version(tmp_path):
    """THE ONE THE WORKFLOW EXISTS FOR. `v0.1.1` tagged a tree that built 0.1.0,
    and nothing anywhere said so. Run against the artifact rather than the source,
    because the source is not what gets uploaded."""
    out = _run_gate(tmp_path, "v9.9.8",
                    ["draughtsman_nn-9.9.9-py3-none-any.whl",
                     "draughtsman_nn-9.9.9.tar.gz"])
    assert out.returncode != 0, (
        "the gate allowed tag v9.9.8 to publish a 9.9.9 wheel. That upload is "
        "not reversible.")
    assert "9.9.9" in out.stdout + out.stderr, (
        "the gate refused without naming the number it found, which leaves the "
        "next person guessing which half to fix")


def test_the_release_gate_refuses_a_dist_it_cannot_speak_for(tmp_path):
    """It reads the version off a single wheel. Two wheels is a build that has
    produced something this check was not written for, and passing on the first
    one it happens to sort is how a guard reports on what it did not examine."""
    out = _run_gate(tmp_path, "v9.9.9",
                    ["draughtsman_nn-9.9.9-py3-none-any.whl",
                     "draughtsman_nn-9.9.9-py2-none-any.whl",
                     "draughtsman_nn-9.9.9.tar.gz"])
    assert out.returncode != 0, (
        "the gate spoke for a dist containing two wheels by reading one of them")


def test_the_workflow_can_only_publish_from_a_tag():
    """`workflow_dispatch` is there so the build and the gate can be exercised
    without spending a tag. That is only safe while the publishing job refuses to
    run off anything but a tag ref -- otherwise the dry run is a second door to
    PyPI, and the gate step, which is itself conditional on a tag, is skipped on
    the way through it."""
    text = PUBLISH.read_text()
    m = re.search(r"^  publish:\n(.*?)(?=^  \w|\Z)", text, re.M | re.S)
    assert m, "publish.yml no longer has a `publish` job under that name"
    assert re.search(r"^\s*if:.*refs/tags/v", m.group(1), re.M), (
        "the publish job is no longer conditional on a tag ref, so a manual run "
        "from a branch would upload -- skipping the version gate, which is "
        "conditional on the same thing.")
    assert re.search(r'tags:\s*\["v\*"\]', text), (
        "the workflow no longer triggers on v* tags, so releases are silently "
        "manual again -- which is the state this whole file is about")


def test_every_file_that_writes_this_version_is_checked_here():
    """The guard against the guard, and it greps rather than trusting a list.

    `tests/test_dist_name.py` learned this the hard way: its first version named
    three files, asserted they existed, and passed while a FOURTH file carried the
    wrong name. A version number is easy to write down helpfully -- in
    `CITATION.cff`, in a docs header, in a badge -- and every copy is one that can
    be behind the one that ships.
    """
    for path in (PYPROJECT, INIT, PUBLISH):
        assert path.exists(), f"{path} has moved; this test is checking nothing"

    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.split()
    # This file quotes real version numbers in its docstrings to say what went
    # wrong, and the fabricated 9.9.9 above is not a claim about anything. The
    # exemption is one path wide, and it is why the pattern below matches an
    # assignment rather than a mention.
    exempt = {str(INIT.relative_to(ROOT)), "tests/test_release.py"}
    writes = re.compile(r'^\s*(?:__version__|version)\s*[:=]\s*["\']?\d+\.\d+\.\d+',
                        re.M)
    others = []
    for rel in tracked:
        if rel in exempt or rel.endswith((".svg", ".json", ".png")):
            continue
        try:
            text = (ROOT / rel).read_text()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        if writes.search(text):
            others.append(rel)
    assert not others, (
        f"these files write a version number of their own: {others}. There is one "
        f"place it may be written -- {INIT.relative_to(ROOT)} -- and anything else "
        "that needs it should read it from there, because a copy that is behind "
        "the shipped one cannot be corrected on PyPI.")


def test_the_release_run_creates_the_github_release_after_the_upload():
    """v0.1.2 was a tag with no release. PyPI listens to tags; Zenodo listens to
    releases; so pip installed 0.1.2 while the DOI resolved to v0.1.1. The run
    now creates the release itself, and only once the upload has succeeded, so
    the archive never describes a version PyPI refused."""
    text = PUBLISH.read_text()
    m = re.search(r"^  release:\n(.*?)(?=^  \w|\Z)", text, re.M | re.S)
    assert m, "publish.yml has no `release` job; Zenodo deposits on nothing"
    job = m.group(1)
    assert re.search(r"needs:\s*publish", job), "the release must wait for the upload"
    assert "refs/tags/v" in job, "the release job must be reachable only from a tag"
    assert "contents: write" in job, "creating a release needs contents: write"
    assert "gh release create" in job and "--verify-tag" in job, (
        "the release is created from the tag that triggered the run, verified")
