"""A static sweep for requirement names this repository has retired.

Derived from the delta specs of the OpenSpec change
`correct-the-documents-against-the-tree`, whose `MODIFIED` requirement is
*Source Files Cite Specifications by Path and Changes by Name*
(`openspec/specs/iac-repo-foundations/spec.md`). The path those deltas sit at is
not written here: a change's artifacts move when it is archived, and this
repository's citation convention is to name the change and the artifact in prose
instead.

What this file is for
---------------------
That requirement already obliges the executable suite to assert the **path** half
of a citation, and gives the reason: the author cannot catch such a citation,
because it is correct when written, correct when reviewed, and wrong only once
the change it cites has succeeded. The same argument holds word for word for the
requirement **name** a citation carries, and nothing asserted it. A later change
renames a requirement; every file citing the old name becomes wrong in the commit
that archives the rename; and the renaming change has no reason to read the files
that cite what it renames.

Measured when this module was written: four retired names across forty-seven
occurrences in thirteen tracked files, of which **forty were in this suite** --
which states, in prose beside each assertion, the requirement that assertion
traces to. That is what decides the exemption policy below.

The names are DERIVED, not declared
-----------------------------------
`RETIRED_NAMES` is not a literal list. It is computed from the archive: every
`### Requirement:` under a `## REMOVED Requirements` heading in an archived delta
specification, less every name a specification currently holds. A hard-coded list
would put this check one rename behind by construction -- the change that retires
the next name is the change that would have to remember to extend the list, and
it is precisely the change with no reason to look. That is the defect this check
exists to remove, reintroduced in the check itself.

The sibling `test_the_external_service_names_are_retired.py` does declare its four
literals, and correctly: they are external service names, and no file in this
repository enumerates them. The archive enumerates these.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable by name:
    python3 -m unittest \\
        test_the_retired_requirement_names_are_gone\\
.TestNoCommittedFileNamesARetiredRequirement\\
.test_no_swept_file_names_a_retired_requirement

Run from the repository root. Discovery puts `.github/tests` on `sys.path`, which
is what makes the sibling imports below resolve.

What no assertion here establishes
----------------------------------
That a citation is *correct*. This module reads one thing: that no swept file
names a requirement the archive retired. A file citing a live requirement under
the wrong specification path, or naming a live requirement that has nothing to do
with what the file says, is invisible here -- the first is the sibling
pre-archive-citation assertion's subject, the second is nobody's.

It also does not read **scenario** titles, and that hole is deliberate and
recorded: thirty citations in this tree name a scenario no specification holds,
which is a different predicate over a different set. `docs/change-queue.md`
carries the entry that would close it by extending this module.

A green run is therefore evidence that the repository was swept of retired
requirement names. It is not evidence that its citations are right.
"""

from __future__ import annotations

import re
import unittest
from typing import Mapping, Sequence

from test_ci_configuration import (
    ARCHIVE_SEGMENT,
    CHANGE_PATH_PREFIX,
    TrackedFilesUnavailable,
    tracked_files,
)

# --------------------------------------------------------------------------
# Where the names come from
# --------------------------------------------------------------------------

ARCHIVE_PREFIX = CHANGE_PATH_PREFIX + ARCHIVE_SEGMENT + "/"
SPECS_PREFIX = "openspec/specs/"
OPENSPEC_PREFIX = "openspec/"

REQUIREMENT_HEADING = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$")
SECTION_HEADING = re.compile(r"^##\s+(.+?)\s*$")
REMOVED_SECTION = "REMOVED Requirements"

# Where a `REMOVED` block records its replacement, measured across this archive
# rather than assumed. All four of these occur:
#
#   - a `**Migration**` line naming it in emphasis;
#   - a `**Reason**` line naming it in emphasis, where the block has no
#     `**Migration**` line -- and a block may carry BOTH labels, with the reason
#     naming nothing and the migration naming the replacement;
#   - a `**Reason**` line naming it in double QUOTES rather than emphasis;
#   - ordinary prose directly beneath the heading, on no labelled line at all.
#
# So every emphasised or quoted span in the block is a candidate, labelled lines
# first, and `_follow` decides which one is the replacement by asking which
# resolves to a name a specification currently holds. Picking the first
# emphasised span instead would answer `environment` for *Environment and Module
# Folder Structure*, whose reason opens "The word *environment* in this title".
REPLACEMENT_LINE = re.compile(r"^\*\*(?:Migration|Reason)\*\*:\s*(.*)$")
EMPHASISED = re.compile(r"\*([^*\n]+)\*")
QUOTED = re.compile(r"\"([^\"\n]+)\"")


def _named_spans(text: str) -> list[str]:
    """Every span of `text` that could be naming a requirement.

    Three renderings, because the archive uses all three for a replacement: a
    name in emphasis, a name in double quotes, and -- since both of those are
    also how this repository stresses an ordinary word or quotes an ordinary
    phrase -- a great many spans that are not requirement names at all. That is
    tolerable here and would not be in the sweep: a candidate only becomes a
    replacement if it resolves to a name a specification currently holds, so a
    wrong guess yields nothing rather than a wrong answer.
    """
    return EMPHASISED.findall(text) + QUOTED.findall(text)

# --------------------------------------------------------------------------
# What the sweep does not read, and why each exemption is here
#
# Every exemption is a hole, so each one is stated with the evidence that
# required it rather than with a category. The requirement admits exactly three
# cases, and there is one exemption per case.
#
#   `openspec/`        -- scoping rather than exemption: the obligation is
#       written over "committed files outside `openspec/`". A change record
#       names what it renames FROM, and a specification under `openspec/specs/`
#       is where a live name lives. This is a PREFIX, and it is the only prefix
#       here; the requirement forbids exempting by directory otherwise.
#
#   this module        -- a check must be able to name what it forbids. Mostly
#       it does not: the names are derived rather than declared. But
#       `KNOWN_RETIRED` below is a retired name written as a literal, on purpose
#       -- it is what stops a derivation that silently returned nothing from
#       satisfying every assertion here -- so the module is an offence against
#       itself without this line. The reader is falsified by fixture trees, but
#       they live in the sibling module `test_a_retired_requirement_name_is_reported`
#       rather than here; see that module and this change's test-plan.md.
#
#   `docs/deferred-work.md` -- the retirement itself is the subject. Its section
#       "Three `iac-cicd-pipeline` requirement names that now read narrower than
#       they are" records that `add-a-staging-environment` renamed *Dedicated
#       Hetzner Cloud Project for Prod*, which is a statement about the rename
#       rather than a citation of the requirement. That is the only occurrence in
#       the file, and a reader following this reason should find it there.
#       Unlike the one below it, this exemption does not expire: the record
#       stays true.
#
#   `docs/change-queue.md` -- EXPIRES. Entry 74 names *Each Environment Has a
#       Dedicated Hetzner Cloud Project*, because naming the stale citation is
#       what that entry is for, and a queue entry is deleted only when its change
#       archives. So the file is exempt across the life of the change that
#       sweeps the tree and no longer. The archive commit deletes the entry and
#       this exemption together; `TestEveryExemptionStillExcusesSomething` below
#       is what turns red if the second is forgotten.
#
# `.github/tests/` IS NOT EXEMPT, and that is the decision this module exists to
# hold. The sibling sweep exempts it wholesale, for two reasons of which only one
# transfers: a check must name what it forbids (handled by the one-module
# exemption above), and several modules build synthetic trees naming `prod` or a
# retired secret (which has no analogue here -- the forty occurrences measured in
# this suite were banners, docstrings and reasoning prose, not fixtures). A
# directory-wide exemption would have left forty of forty-seven occurrences
# unread while reporting a clean sweep.
# --------------------------------------------------------------------------

EXEMPT_PREFIXES = (OPENSPEC_PREFIX,)

THIS_MODULE_PATH = ".github/tests/test_the_retired_requirement_names_are_gone.py"

EXEMPT_PATHS: tuple[str, ...] = (
    THIS_MODULE_PATH,
    "docs/change-queue.md",
    "docs/deferred-work.md",
)

# Files the sweep must reach for a green result to mean anything -- one per
# surface the change that added this module edits, at five different depths.
# DERIVED: no scenario states them. They are the anchors that keep a reader
# returning nothing from satisfying the assertion, chosen the way the sibling
# module chooses its own and for the same reason a count would not do.
SWEEP_ANCHORS = (
    "README.md",
    "AGENTS.md",
    "docs/bootstrap-a-new-host.md",
    "ansible/ansible.cfg",
    "ansible/roles/swap/defaults/main.yml",
    "terraform/stacks/main-staging/versions.tf",
    ".github/workflows/drift.yml",
    ".github/tests/test_environment_agnostic_pipeline.py",
)

# A name the archive records as retired in a delta this module does not touch,
# and which will stay retired. It anchors the DERIVATION the way SWEEP_ANCHORS
# anchor the read: a derivation that silently returned nothing -- because the
# archive's delta format moved under it -- would otherwise satisfy every
# assertion here while forbidding nothing.
KNOWN_RETIRED = "Each Environment Has a Dedicated Hetzner Cloud Project"


# --------------------------------------------------------------------------
# Reading a file the way a citation is written
#
# A requirement name is stated in at least four renderings in this tree --
# emphasised, quoted, bare, and wrapped across a comment's line break -- and the
# wrapped one is the majority. So the match runs over a FLATTENED rendering of
# each file: every line stripped of its indentation and of one leading run of
# comment markers, joined by single spaces, with an index back to the line each
# character came from.
#
# Joining is what makes a wrapped name findable and is also the one way this
# reader could invent a match that no file states. Two things bound it: only ONE
# leading marker run is stripped, so a divider line like `# ---` contributes
# `---` and breaks the join rather than vanishing; and a line that strips to
# nothing contributes a character no requirement name can contain, so a blank
# line breaks it too.
# --------------------------------------------------------------------------

LEADING_MARKERS = re.compile(r'^\s*(?:[#*/\-"]+\s*)?')

# Contributed by a line that strips to nothing. Outside the character set any
# requirement name uses, so a name can never match across it.
BREAK = "\x00"


def flattened(text: str) -> tuple[str, list[int]]:
    """`text` as one line, with a character-offset-to-line-number index.

    The index is what lets an offence report the line a wrapped name STARTS on,
    which is the line a reader has to open. Returning it alongside rather than
    recomputing it is deliberate: recomputing means searching the original text
    for a name that, when wrapped, does not appear in it.
    """
    pieces: list[str] = []
    lines: list[int] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = LEADING_MARKERS.sub("", line).strip()
        piece = re.sub(r"\s+", " ", stripped) if stripped else BREAK
        if pieces:
            pieces.append(" ")
            lines.append(number)
        pieces.append(piece)
        lines.extend([number] * len(piece))
    return "".join(pieces), lines


def retirements(files: Mapping[str, str]) -> dict[str, str | None]:
    """Every retired requirement name, mapped to what to write instead.

    A name is retired when an **archived** delta specification removed it and no
    specification currently holds it. Both halves are load-bearing. A change
    still in flight has not retired anything -- until it archives the name is
    still held, and retiring it early would report every correct citation in the
    tree while the proposal is under review. And a name removed by one change and
    reintroduced by a later one is live, so reporting it would forbid the correct
    citation.

    The value is the name a specification currently holds, followed through the
    chain the archive records where a recorded replacement is itself retired --
    *Dedicated Hetzner Cloud Project for Prod* records its replacement as a name
    that was later retired in turn, and offering that would hand the reader a
    name this same check forbids. It is `None` where the block records no
    replacement, and where the chain reaches no live name.
    """
    live: set[str] = set()
    for path, text in files.items():
        if not path.startswith(SPECS_PREFIX):
            continue
        for line in text.splitlines():
            heading = REQUIREMENT_HEADING.match(line)
            if heading:
                live.add(heading.group(1))

    labelled: dict[str, list[str]] = {}
    candidates: dict[str, list[str]] = {}
    for path, text in files.items():
        if not path.startswith(ARCHIVE_PREFIX):
            continue
        section = None
        current = None
        for line in text.splitlines():
            heading = SECTION_HEADING.match(line)
            if heading:
                section = heading.group(1)
                current = None
                continue
            requirement = REQUIREMENT_HEADING.match(line)
            if requirement:
                current = requirement.group(1) if section == REMOVED_SECTION else None
                if current is not None:
                    labelled.setdefault(current, [])
                    candidates.setdefault(current, [])
                continue
            if current is None:
                continue
            replacement = REPLACEMENT_LINE.match(line)
            if replacement:
                labelled[current].extend(_named_spans(replacement.group(1)))
            else:
                candidates[current].extend(_named_spans(line))

    # A labelled line is the likelier place for the replacement, so its
    # candidates are tried first; the block's body is the fallback, because the
    # archive also names a replacement in ordinary prose beneath the heading.
    ordered = {name: labelled[name] + candidates[name] for name in candidates}

    resolved: dict[str, str | None] = {}
    for name in ordered:
        if name in live:
            continue
        resolved[name] = _follow(name, ordered, live)
    return resolved


def _follow(
    name: str, candidates: Mapping[str, Sequence[str]], live: set[str]
) -> str | None:
    """The first live name reachable from `name` through what the archive records.

    A `REMOVED` block names its replacement in emphasis, but emphasis is also how
    this repository writes an ordinary word it wants to stress -- the rename of
    *Environment and Module Folder Structure* explains itself as "the word
    *environment* in this title", and a reader taking the first emphasised span
    would offer `environment` as the new requirement name. So every emphasised
    span in the block is a candidate and the resolution picks the first that
    means something: a name a specification currently holds, or another retired
    name that leads to one.

    Cycles are bounded by `seen`. The archive holds none today; a record that
    renamed A to B and later B back to A would otherwise not terminate.
    """
    seen = {name}
    queue = list(candidates.get(name, ()))
    while queue:
        candidate = queue.pop(0)
        if candidate in live:
            return candidate
        if candidate in seen or candidate not in candidates:
            continue
        seen.add(candidate)
        queue.extend(candidates[candidate])
    return None


def swept(path: str) -> bool:
    """Whether a tracked path is one this sweep reads."""
    if path in EXEMPT_PATHS:
        return False
    return not any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)


def decoded(files: Mapping[str, bytes]) -> dict[str, str]:
    """Each tracked file as text, undecodable bytes replaced rather than raised.

    A binary file is read too. It will not normally carry a requirement name, and
    skipping by extension would be a list of extensions to keep current -- the
    safe direction for a prohibition is to read more, not less.
    """
    return {
        path: content.decode("utf-8", errors="replace") for path, content in files.items()
    }


def retired_name_offences(
    files: Mapping[str, str],
    names: Sequence[str] | None = None,
    live: Sequence[str] | None = None,
) -> list[str]:
    """Every swept file naming a retired requirement, as `<path>:<line>: <name>`.

    One entry per occurrence rather than per file: a module naming a requirement
    in a section banner, in a docstring and in the prose beside both is three
    edits, and a sweep reporting it once sends its reader back three times.

    `names` and `live` are `Sequence` and not `Iterable`, which is not pedantry:
    both are consumed in an inner loop, so a generator would be exhausted by the
    first file and every file after it would be compared against nothing.

    `live` is what keeps a retired name that is a PREFIX of a live one from
    reporting every correct citation of the longer name -- *Ansible Configuration
    Is Verified in Continuous Integration* against *... and Gates the Merge*. The
    suppression runs over the flattened text, where the longer name is contiguous
    even when the file wraps it; per line it would suppress almost nothing, which
    over this repository's own subject is the largest false-positive class this
    check could have.
    """
    if names is None or live is None:
        derived = retirements(files)
        specifications = _live_names(files)
        names = tuple(derived) if names is None else names
        live = tuple(specifications) if live is None else live

    offences: list[str] = []
    for path in sorted(files):
        if not swept(path):
            continue
        offences.extend(_offences_in(path, files[path], names, live))
    return sorted(offences, key=_offence_order)


def _offences_in(
    path: str, text: str, names: Sequence[str], live: Sequence[str]
) -> list[str]:
    """Every retired name `text` states, as `<path>:<line>: <name>`.

    The one place a file is read for a retired name. Both callers go through it
    so that the sweep and the exemption-expiry check cannot answer the same
    question differently -- which they did, until the expiry was found counting
    a retired name that was only the prefix of a live one.
    """
    longer = tuple(sorted(live, key=len, reverse=True))
    flat, index = flattened(text)
    found: list[str] = []
    for name in names:
        start = flat.find(name)
        while start != -1:
            if not any(
                len(candidate) > len(name) and flat.startswith(candidate, start)
                for candidate in longer
            ):
                found.append(f"{path}:{index[start]}: {name}")
            start = flat.find(name, start + 1)
    return found


def _offence_order(entry: str) -> tuple[str, int, str]:
    path, line, name = entry.split(":", 2)
    return path, int(line), name


def _live_names(files: Mapping[str, str]) -> set[str]:
    names: set[str] = set()
    for path, text in files.items():
        if not path.startswith(SPECS_PREFIX):
            continue
        for line in text.splitlines():
            heading = REQUIREMENT_HEADING.match(line)
            if heading:
                names.add(heading.group(1))
    return names


def idle_exemptions(
    files: Mapping[str, str],
    names: Sequence[str] | None = None,
    paths: Sequence[str] = EXEMPT_PATHS,
    live: Sequence[str] | None = None,
) -> list[str]:
    """Every whole-path exemption whose file no longer names a retired requirement.

    An exemption is a hole, and a hole nobody is looking at is one nobody closes.
    This is what makes each one self-retiring: the change that sweeps an exempt
    file is the change whose run turns red until it also deletes the exemption.
    The sibling module records that mechanism working -- its `docs/change-queue.md`
    exemption expired in the archive commit that deleted the entry it existed for.

    The read is FLATTENED, for a reason the expiry case makes sharp: an exemption
    over a file naming a retired requirement across a line break would otherwise
    be reported as idle, and deleting it -- the repair the report asks for --
    turns the sweep red on the very file the exemption was written for.

    It asks the SAME question the sweep asks, through the same finder, and that
    is load-bearing rather than tidy. A bare substring test answers "still
    needed" for a file whose only match is a retired name sitting inside a
    longer live one -- `docs/change-queue.md` cites *Ansible Configuration Is
    Verified in Continuous Integration and Gates the Merge*, which contains a
    retired name as its prefix. Under a bare test that citation alone would keep
    the exemption looking alive after the thing it was written for had gone, and
    the expiry would never fire: exactly the reminder design decision 6 depends
    on, silently absent.
    """
    if names is None or live is None:
        derived = retirements(files)
        names = tuple(derived) if names is None else names
        live = tuple(_live_names(files)) if live is None else live
    idle: list[str] = []
    for path in paths:
        text = files.get(path)
        if text is None:
            idle.append(
                f"{path}: exempted, but no such tracked file exists. An exemption over a "
                "file that is not there excuses nothing"
            )
            continue
        excused = _offences_in(path, text, names, live)
        if not excused:
            idle.append(
                f"{path}: exempted, but it names no retired requirement any more. The "
                "exemption is to be deleted in the change that swept the file"
            )
    return idle


def _tree() -> dict[str, str]:
    return decoded(tracked_files())


# --------------------------------------------------------------------------
# The assertions over the committed tree
# --------------------------------------------------------------------------


class TestNoCommittedFileNamesARetiredRequirement(unittest.TestCase):
    """SPECIFIED -- *Source Files Cite Specifications by Path and Changes by
    Name* (`openspec/specs/iac-repo-foundations/spec.md`): "A requirement named
    in a committed file outside `openspec/` SHALL be one that a specification
    under `openspec/specs/` currently holds", and the scenario "A pull request
    naming a retired requirement is rejected".

    This is the assertion whose failure is the required status check failing.
    """

    def setUp(self) -> None:
        try:
            self.files = _tree()
        except TrackedFilesUnavailable as unavailable:
            self.fail(str(unavailable))
        self.retired = retirements(self.files)

    def test_no_swept_file_names_a_retired_requirement(self) -> None:
        """SPECIFIED -- the obligation itself."""
        names = tuple(self.retired)
        offences = retired_name_offences(
            self.files, names=names, live=tuple(_live_names(self.files))
        )
        replacements = {
            name: self.retired[name] for name in names if self.retired[name] is not None
        }
        self.assertEqual(
            [],
            offences,
            "a committed file outside `openspec/` names a requirement this repository "
            "retired. Each line is `<path>:<line>: <name>`; write instead: "
            + (
                "; ".join(f"{old} -> {new}" for old, new in sorted(replacements.items()))
                or "(the archive records no live replacement for these)"
            ),
        )

    def test_the_sweep_reaches_every_surface_it_claims_to(self) -> None:
        """DERIVED -- no scenario states it. Every assertion in this class is
        satisfied by a reader that returns nothing, so the anchors are what
        establish that the read happened at all."""
        read = {path for path in self.files if swept(path)}
        for anchor in SWEEP_ANCHORS:
            with self.subTest(anchor=anchor):
                self.assertIn(
                    anchor,
                    read,
                    f"{anchor} is not among the files this sweep reads, so a green "
                    "result says nothing about it",
                )

    def test_the_suite_itself_is_swept(self) -> None:
        """SPECIFIED -- the scenario "The test suite's own citations are read",
        and the requirement's "exempting only a module that must name a retired
        requirement in order to assert its absence". Forty of the forty-seven
        occurrences measured when this module was written were in this suite; a
        directory-wide exemption would report a clean sweep over them."""
        read = {path for path in self.files if swept(path)}
        suite = {path for path in self.files if path.startswith(".github/tests/")}
        self.assertEqual(
            {THIS_MODULE_PATH},
            suite - read,
            "this suite is exempt for exactly one module -- the one that must name "
            "what it forbids",
        )


class TestTheRetiredNamesAreDerivedRatherThanDeclared(unittest.TestCase):
    """DERIVED -- design decision 1 of the change that added this module. The
    derivation is what keeps the check from being one rename behind, and it is
    also the one thing here that can fail silently: a `REMOVED` block stating its
    name some other way shrinks the set without failing anything.
    """

    def setUp(self) -> None:
        try:
            self.files = _tree()
        except TrackedFilesUnavailable as unavailable:
            self.fail(str(unavailable))

    def test_the_derived_set_is_not_empty(self) -> None:
        """DERIVED -- a derivation returning nothing forbids nothing, and every
        other assertion here would pass over it."""
        self.assertNotEqual({}, retirements(self.files))

    def test_a_name_known_to_be_retired_is_in_the_set(self) -> None:
        """DERIVED -- stronger than non-emptiness: it pins the derivation to a
        name an archived delta records as removed, in a record this module does
        not touch and which will not change."""
        self.assertIn(KNOWN_RETIRED, retirements(self.files))

    def test_no_derived_name_is_one_a_specification_holds(self) -> None:
        """SPECIFIED -- the obligation is over a name "that no specification
        under `openspec/specs/` currently holds". A derivation admitting a live
        name would forbid the correct citation of it."""
        self.assertEqual(
            set(), set(retirements(self.files)) & _live_names(self.files)
        )

    def test_every_offered_replacement_is_a_name_a_specification_holds(self) -> None:
        """SPECIFIED -- the scenario's AND clause. A replacement this check
        offered while forbidding it would send the reader to write the next
        offence."""
        live = _live_names(self.files)
        for name, replacement in sorted(retirements(self.files).items()):
            if replacement is None:
                continue
            with self.subTest(name=name):
                self.assertIn(replacement, live)


class TestEveryExemptionStillExcusesSomething(unittest.TestCase):
    """SPECIFIED -- the scenario "An exemption that no longer excuses anything
    fails the check", and the requirement's "the assertion SHALL fail where an
    exemption names a file that no longer contains a retired name, so that it is
    deleted in the change that swept the file rather than left standing over a
    file it no longer describes".
    """

    def setUp(self) -> None:
        try:
            self.files = _tree()
        except TrackedFilesUnavailable as unavailable:
            self.fail(str(unavailable))

    def test_no_exemption_is_idle(self) -> None:
        """SPECIFIED -- the scenario itself."""
        self.assertEqual([], idle_exemptions(self.files))

    def test_the_only_prefix_exemption_is_the_requirements_own_scope(self) -> None:
        """SPECIFIED -- "Such a file SHALL be exempted by its own path rather
        than by a directory prefix". `openspec/` is not an exemption but the
        obligation's own scope, which is why it is the only prefix here."""
        self.assertEqual((OPENSPEC_PREFIX,), EXEMPT_PREFIXES)


if __name__ == "__main__":
    unittest.main()
