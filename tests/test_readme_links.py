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
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
LINK_RE = re.compile(r'!?\[[^\]]*\]\(([^)]+)\)')


def _repository() -> str:
    with (ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["urls"]["Repository"].rstrip("/")


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
