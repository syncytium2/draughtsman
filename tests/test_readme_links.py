"""README links must survive being rendered off the repository.

    "PyPI prep. `project.urls`, a version policy, and the one that bites: every
     relative link in `README.md` renders dead on the PyPI project page."
                                            — CLAIMS.md, the path to public

PyPI renders `readme` as a standalone page. There is no repository around it, so
a relative link resolves against `pypi.org` and dies — silently, and only on the
page most first-time readers see. Making them absolute fixes that and creates a
new problem in its place: the repository URL is now kept in `pyproject.toml` and
in every link in `README.md`, which is DECISIONS.md correction 5's shape. So it
is checked.

Three things, and the third is the one a human would not notice:

1. No link in README.md is relative.
2. Every repository link is built from the `Repository` URL `pyproject.toml`
   declares, so the two cannot drift apart.
3. Every repository link points at a path this repository actually has. An
   absolute link cannot be caught by a broken-link check the way a relative one
   can, so a file renamed or removed leaves a link that looks right and 404s.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
LINK_RE = re.compile(r'!?\[[^\]]*\]\(([^)]+)\)')


def _repository() -> str:
    """Read `Repository` out of pyproject without tomllib.

    `tomllib` is 3.11+, and this project supports 3.10 — a floor
    `tests/test_versions.py` ties to the pyproject and the CI matrix, so a test
    that quietly needs 3.11 breaks a promise the repository makes elsewhere. The
    first version of this file imported it and went red on the 3.10 job.
    """
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^\s*Repository\s*=\s*"([^"]+)"', text, re.M)
    assert m, "pyproject.toml declares no [project.urls] Repository"
    return m.group(1).rstrip("/")


def _links() -> list[str]:
    return LINK_RE.findall(README.read_text(encoding="utf-8"))


def test_the_readme_declares_at_least_one_link():
    """So the assertions below cannot pass by having nothing to check."""
    assert _links(), "README.md has no markdown links at all — parser broken?"


def test_no_readme_link_is_relative():
    relative = [t for t in _links()
                if not t.startswith(("http://", "https://", "#", "mailto:"))]
    assert not relative, (
        f"README.md carries relative links: {relative}. PyPI renders the readme "
        "with no repository around it, so each of these resolves against "
        "pypi.org and 404s on the page most first-time readers see."
    )


def test_repository_links_use_the_url_pyproject_declares():
    repo = _repository()
    owner_repo = repo.split("github.com/", 1)[-1]
    wrong = [t for t in _links()
             if owner_repo.split("/")[0] in t and not (
                 t.startswith(repo) or t.startswith(
                     f"https://raw.githubusercontent.com/{owner_repo}/"))]
    assert not wrong, (
        f"README.md links do not match `Repository` in pyproject.toml ({repo}): "
        f"{wrong}. The URL is kept in two places, so it is checked in one."
    )


def test_every_repository_link_points_at_a_path_that_exists():
    repo = _repository()
    owner_repo = repo.split("github.com/", 1)[-1]
    blob = f"{repo}/blob/main/"
    raw = f"https://raw.githubusercontent.com/{owner_repo}/main/"
    missing = []
    for t in _links():
        for prefix in (blob, raw):
            if t.startswith(prefix):
                rel = t[len(prefix):].split("#")[0].rstrip("/")
                if rel and not (ROOT / rel).exists():
                    missing.append(rel)
    assert not missing, (
        f"README.md links to paths this repository does not have: {missing}. "
        "An absolute link cannot be checked by following it from the repo, so a "
        "renamed or deleted file leaves a link that looks correct and 404s."
    )


# --- the DOI, which is now kept in two files ---------------------------------

CITATION = ROOT / "CITATION.cff"
_DOI_RE = re.compile(r"10\.5281/zenodo\.\d+")


def test_the_readme_badge_and_the_citation_name_the_same_doi():
    """One quantity, two files — so it is checked in one place.

    The badge in README.md and the identifier in CITATION.cff are the same DOI
    written twice, which is DECISIONS.md correction 5's exact shape: a value with
    a single correct answer, kept in two places, free to disagree. Nothing would
    notice a badge left pointing at an old record — least of all a reader, who
    would follow it and land somewhere plausible.
    """
    readme = {m.group(0) for m in _DOI_RE.finditer(README.read_text(encoding="utf-8"))}
    cff = {m.group(0) for m in _DOI_RE.finditer(CITATION.read_text(encoding="utf-8"))}
    assert readme, "README.md names no Zenodo DOI; the badge has gone"
    assert cff, "CITATION.cff names no Zenodo DOI"
    assert readme == cff, (
        f"README.md cites {sorted(readme)} and CITATION.cff cites {sorted(cff)}. "
        "They must be the same concept DOI — a badge pointing at a different "
        "record than the citation file sends a reader somewhere plausible and "
        "wrong.")


def test_the_doi_cited_is_the_concept_doi_not_a_version():
    """A concept DOI outlives a release; a version DOI is stale on the next one.

    Zenodo mints both. The version DOI for v0.1.1 is 10.5281/zenodo.22289006 and
    the concept DOI is 10.5281/zenodo.22286341; citing the former would pin every
    future reader to one release. This cannot tell them apart by inspection, so
    it pins the one that was chosen — if it changes, that has to be deliberate.
    """
    concept = "10.5281/zenodo.22286341"
    cited = {m.group(0) for m in _DOI_RE.finditer(CITATION.read_text(encoding="utf-8"))}
    assert cited == {concept}, (
        f"CITATION.cff cites {sorted(cited)}; the concept DOI is {concept}. A "
        "version DOI pins readers to one release and goes stale at the next.")
