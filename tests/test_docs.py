"""Documentation links.

Splitting a long README into pages is how links rot: the file moves, the
link doesn't, and nobody notices until a reader hits a 404. That is a
mechanical failure, so it gets a mechanical check rather than a promise to
be careful.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# [text](target) - ignoring images and anything with a scheme
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)\)")
SCHEMES = ("http://", "https://", "mailto:", "#")


def markdown_files() -> list[Path]:
    return [p for p in ROOT.rglob("*.md") if ".git" not in p.parts]


def test_markdown_files_exist():
    assert markdown_files(), "no markdown found - the test is pointing at nothing"


def test_every_relative_link_resolves():
    broken = []
    for md in markdown_files():
        for target in LINK.findall(md.read_text(encoding="utf-8")):
            if target.startswith(SCHEMES):
                continue
            path = (md.parent / target.split("#", 1)[0]).resolve()
            if not path.exists():
                broken.append(f"{md.relative_to(ROOT)} -> {target}")
    assert not broken, "dead links: " + "; ".join(broken)


def test_every_doc_page_is_reachable_from_the_readme():
    """A page nothing links to is a page nobody reads."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    linked = set(LINK.findall(readme))
    orphans = [
        p.name
        for p in sorted((ROOT / "docs").glob("*.md"))
        if f"docs/{p.name}" not in linked
    ]
    assert not orphans, f"docs not linked from README: {orphans}"


def test_the_readme_stays_short():
    """The reason for the split. Without a number it grows back.

    Not a style rule - a long README is an unread README, and the sections
    that get skipped are the ones that explain why any of it is shaped this
    way.
    """
    n = len((ROOT / "README.md").read_text(encoding="utf-8").splitlines())
    assert n <= 200, f"README is {n} lines - move a section into docs/"


def test_documented_install_commands_pin_the_current_version():
    """Docs telling people to install a version that is not this one is the
    exact drift the pin exists to stop - and it would ship silently.

    The needle is derived from the module, never typed, so this check cannot
    become another copy of the version number.
    """
    import re
    import sys

    sys.path.insert(0, str(ROOT))
    from harness.version import __version__

    stale = []
    for md in markdown_files():
        for ref in re.findall(r"jbernec/harness@v?([0-9][^\s\"')]*)", md.read_text(encoding="utf-8")):
            if ref != __version__:
                stale.append(f"{md.relative_to(ROOT)} -> v{ref}")
    assert not stale, f"docs install v{__version__} elsewhere: {stale}"
