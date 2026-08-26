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


# Counts written out in prose - "twelve rules", "133 self-tests". Both of
# these went stale within a week of being written, because keeping them true
# depends on remembering. That is failure mode 1 in docs/failures.md: a
# number you maintain by hand is another copy of the thing it describes.
NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
}


def agent_rule_count() -> int:
    """Derived from AGENTS.md, never typed. A check that copies the value it
    guards becomes another copy of it."""
    import re

    return len(re.findall(r"^\d+\. \*\*", (ROOT / "AGENTS.md").read_text(encoding="utf-8"), re.M))


def test_agents_md_has_rules_to_count():
    assert agent_rule_count() >= 5, "the parser stopped matching - fix it, don't delete it"


def test_no_document_states_a_stale_rule_count():
    """"...its twelve rules" survived three rules being added.

    Scoped to sentences that are actually about AGENTS.md. A first version
    matched every "N rules" in the repo and flagged "Three rules for IDs",
    which is a different set entirely - failure mode 2, a guard that cries
    wolf gets switched off.
    """
    import re

    actual = agent_rule_count()
    wrong = []
    for md in markdown_files():
        for line in md.read_text(encoding="utf-8").splitlines():
            if not re.search(r"AGENTS\.md|\bagent(s|'s)?\b", line, re.I):
                continue
            for word in re.findall(r"\b([a-z]+|\d+) rules\b", line, re.I):
                n = NUMBERS.get(word.lower(), int(word) if word.isdigit() else None)
                if n is not None and n != actual:
                    wrong.append(f"{md.relative_to(ROOT)}: '{word} rules', AGENTS.md has {actual}")
    assert not wrong, "; ".join(wrong) + " - state no number rather than a wrong one"


def test_the_rule_count_check_catches_a_stale_number():
    """Proved in both directions, per rule 9. A guard only ever seen passing
    is decoration - this one must actually fire on the sentence that broke."""
    import re

    actual = agent_rule_count()
    line = f"Copy AGENTS.md into your project. It gives the agent its {actual + 1} rules."
    assert re.search(r"AGENTS\.md|\bagent(s|'s)?\b", line, re.I)
    hits = [
        w for w in re.findall(r"\b([a-z]+|\d+) rules\b", line, re.I)
        if NUMBERS.get(w.lower(), int(w) if w.isdigit() else None) not in (None, actual)
    ]
    assert hits, "the pattern no longer matches the sentence it was written for"


def test_the_rule_count_check_ignores_an_unrelated_rule_count():
    """And stays quiet on 'Three rules for IDs', which is a different set."""
    import re

    assert not re.search(r"AGENTS\.md|\bagent(s|'s)?\b", "### Three rules for IDs", re.I)


def test_no_document_states_a_stale_test_count():
    """The README claimed 133 self-tests while the suite ran 136."""
    import re

    actual = sum(
        len(re.findall(r"^def test_", p.read_text(encoding="utf-8"), re.M))
        for p in (ROOT / "tests").glob("test_*.py")
    )
    wrong = []
    for md in markdown_files():
        for n in re.findall(r"\b(\d+) (?:self-)?tests\b", md.read_text(encoding="utf-8")):
            if int(n) != actual:
                wrong.append(f"{md.relative_to(ROOT)} says {n}, the suite has {actual}")
    assert not wrong, "; ".join(wrong) + " - state no number rather than a wrong one"
