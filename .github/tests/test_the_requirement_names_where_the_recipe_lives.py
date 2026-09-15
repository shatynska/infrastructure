"""Static-assertion tests for the requirement naming the document that holds
the manual database-provisioning recipe, and for no second committed Markdown
document outside `openspec/` holding a copy of it.

Derived from the delta specification of the OpenSpec change
`record-how-an-application-is-onboarded`, before any implementation of that
change existed -- from that delta at commit `e0ef360`, the commit holding the
approved plan. The path the delta sits at is not written here: a change's
artifacts move when it is archived, and this repository's citation convention is
to name the change and the artifact in prose instead.

The delta modifies one requirement, *Single Shared PostgreSQL Instance,
Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`), and
adds one scenario to it -- *The document this requirement names holds the
recipe*. That scenario is the whole subject of this module. Every other
paragraph and scenario in that requirement is carried over unchanged from the
delta of `provision-commerce-ops-database-in-the-shared-instance` and is already
asserted by the module beside this one,
`test_the_shared_instance_has_its_first_database.py`; nothing here restates any
of it. See this change's `test-plan.md` for the scenario-to-test mapping, the
baseline, the assertion classifications, and the obsolete-test candidates.

Every assertion is annotated SPECIFIED (it traces to a clause of that scenario
or to the SHALL text of the paragraph the delta adds beside it) or DERIVED (it
traces to this change's `design.md` or `tasks.md`, or to this file's own
judgment about how the scenario is made checkable).

Why this is a module of its own rather than a section of its sibling
--------------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. The sibling module's own subject moves with the
recipe -- its document constant is re-pointed by this change's tasks.md 3.1, and
`test_the_bootstrap_documents_static_conventions.py`'s key-target check is
widened by its 3.2 -- and both edits are the implementing author's. Nothing in
this file edits, deletes or disables an existing test. Where it needs a helper a
module beside it already has, it imports it rather than restating it, which is
the idiom this directory uses.

`recipe_blocks` in particular is imported rather than reimplemented, so that
"what counts as a copy of the recipe" has one definition in this suite. A
second, privately spelled one could drift from its sibling's and let a copy
through the gap between them. That import reaches a helper this change's tasks
do not touch; they re-point a path constant in the same module.

Which source the document name is resolved from, and why the obvious one is wrong
--------------------------------------------------------------------------------
Not `requirement_sources()`, the sibling's helper, which reads the requirement
from EVERY live change's delta. While
`provision-commerce-ops-database-in-the-shared-instance` is live, that returns
two texts naming two different documents -- the one it names and the one this
change names -- and a detector faithful to this scenario over both would demand
that each of two documents hold the recipe while forbidding a second copy, which
nothing can satisfy.

So the rule this change's tasks.md 3.5 states is implemented here instead, in
`requirement_source()`: the name resolves from THIS change's delta while that
delta is live, and from the main specification once THIS change is archived. A
live delta naming a document this change supersedes is not a source. Both
clauses are written against this change's own life rather than another's,
because the expected archive order leaves an interval -- the other change
archived, this one still live -- in which the main specification still names the
document the recipe has left, and a rule falling back to it there would be red on
the trunk for the whole interval.

Its bound is worth stating: a LATER change modifying this requirement again is
read by this rule only once it archives. Until then this module asserts the
requirement as this change leaves it, which is the right answer while that
change is in flight and the wrong one the moment it lands. Its own test author
lists these assertions as superseded, exactly as this file's `test-plan.md`
lists its predecessors'.

The population the second clause sweeps
---------------------------------------
Committed Markdown outside `openspec/`, which the added paragraph states in as
many words. Three classes of copy in this repository are deliberate and are
excluded by that bounding rather than by an exemption list:

- change records under `openspec/` quote the recipe as history -- `walked_files`
  prunes that directory;
- the sibling module carries three fenced recipe fixtures of its own, one an
  exact copy of the living recipe -- it is Python, not Markdown;
- `platform/README.md` mentions the recipe in prose without copying it, and
  carries a fenced `CREATE ROLE pgexporter` block, a different recipe -- keying
  on `CREATE DATABASE` rather than on `CREATE ROLE` excludes it, as the sibling
  module already does.

Each of those three is exercised as a fixture below rather than trusted.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable by name through discovery:
    python3 -m unittest discover --start-directory .github/tests -k \\
        test_the_requirement_names_where_the_recipe_lives.TestTheNamedDocumentHoldsTheRecipe.test_the_named_document_holds_the_recipe

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling imports below resolve; `python3 -m unittest
<dotted name>` from the root does not, and errors on those imports.

Every check here is a static read, so a check whose target already carries the
property passes having shown nothing about whether it can fail. Each detector is
therefore also run over material this file supplies to falsify it -- the
`...DetectorFires` and `...RuleResolves` classes. They add no import beyond the
standard library and the sibling modules, spawn no subprocess, and need no
network call, credential, container runtime or Terraform binary.

What no assertion here establishes
----------------------------------
Not that the recipe in the named document WORKS, nor that it carries any of the
properties the sibling module asserts of it -- an isolated role, a password
never on a command line, the log settings pinned. Those are that module's, and
they follow the recipe to whichever document holds it. This one establishes only
that the document this requirement names is the document that holds it, and that
no second Markdown document outside `openspec/` holds another.

Nor that a reader of the requirement actually opens the named document. What a
static read can reach is the naming; whether the operator followed it is the
change's own ship-confirm observation.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from test_ci_configuration import ARCHIVE_SEGMENT, ROOT, walked_files
from test_the_shared_instance_has_its_first_database import (
    CAPABILITY,
    REQUIREMENT_NAME,
    recipe_blocks,
    requirement_block,
)

# --------------------------------------------------------------------------
# What is read
# --------------------------------------------------------------------------

CHANGE_NAME = "record-how-an-application-is-onboarded"

# The scenario bounds its own population to committed Markdown outside this
# directory, and `walked_files` prunes it already. Named here as well because
# `named_documents` below excludes a specification citation from candidacy for
# the same reason: a specification is not a document an operator provisions
# from.
SPECIFICATION_DIRECTORY = "openspec/"

# A backticked repository-relative path to a Markdown document. The scenario
# says "a committed document"; this reads the Markdown ones, which is what the
# second clause's population is and what every document in `docs/` is. A
# requirement naming a document under some other extension yields no candidate
# here and fails the assertion below loudly rather than silently.
MARKDOWN_PATH = re.compile(r"`(?P<path>[A-Za-z0-9._/-]+\.md)`")

RECIPE_WORD = re.compile(r"\brecipe\b", re.IGNORECASE)

# Emphasis markers are stripped before splitting, so that a sentence ending
# `... as of 2026-09-13.**` is not read as running into the next one. Without
# that, two paragraphs of this requirement merge into one "sentence" and a path
# named nowhere near the word "recipe" becomes a candidate.
EMPHASIS = re.compile(r"[*_]+")
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


def sentences(text: str) -> list[str]:
    """The block's sentences, emphasis markers removed.

    Scoped to the sentence rather than to the paragraph deliberately: the
    paragraph that names the recipe's document also states the automation
    obligation, and a requirement is free to cite a specification in it.
    """
    return [s for s in SENTENCE_BREAK.split(EMPHASIS.sub("", text)) if s.strip()]


def named_documents(block: str) -> list[str]:
    """Every Markdown document the requirement names as holding the recipe.

    A candidate is a backticked Markdown path in a sentence that speaks of the
    recipe, excluding a path under the specification directory. Returned in the
    order met, without repetition: the scenario's WHEN clause presupposes ONE
    named document, and two is a state to report rather than to choose between.
    """
    found: list[str] = []
    for sentence in sentences(block):
        if not RECIPE_WORD.search(sentence):
            continue
        for match in MARKDOWN_PATH.finditer(sentence):
            path = match.group("path")
            if path.startswith(SPECIFICATION_DIRECTORY) or path in found:
                continue
            found.append(path)
    return found


def requirement_source(root: Path | None = None) -> tuple[str, str] | None:
    """The requirement as this check resolves it, as `(relative path, block)`.

    This change's delta while this change is live; the main specification once
    it is archived. See the module docstring: a live delta naming a document
    this change supersedes is not a source, so no other change's delta is read
    here and there is no fall-back to the main specification while this change's
    own delta is the one in force. A live change whose delta has lost the
    requirement returns None, which fails the assertions below naming the
    absence -- rather than quietly resolving to the text this change replaces.
    """
    root = ROOT if root is None else root
    live = root / "openspec" / "changes" / CHANGE_NAME
    if live.is_dir():
        delta = live / "specs" / CAPABILITY / "spec.md"
        if not delta.is_file():
            return None
        block = requirement_block(delta.read_text(encoding="utf-8"), REQUIREMENT_NAME)
        return None if block is None else (delta.relative_to(root).as_posix(), block)
    main = root / "openspec" / "specs" / CAPABILITY / "spec.md"
    if main.is_file():
        block = requirement_block(main.read_text(encoding="utf-8"), REQUIREMENT_NAME)
        if block is not None:
            return (main.relative_to(root).as_posix(), block)
    return None


def change_record_directories(root: Path | None = None) -> list[Path]:
    """This change's directory, in the live layout or the archived one.

    The idiom its sibling uses: a change is located by NAME across both
    layouts, never by a written path into the changes directory, which this
    repository's own citation check forbids.
    """
    root = ROOT if root is None else root
    changes = root / "openspec" / "changes"
    found = [changes / CHANGE_NAME] if (changes / CHANGE_NAME).is_dir() else []
    archive = changes / ARCHIVE_SEGMENT
    if archive.is_dir():
        found.extend(
            directory
            for directory in sorted(archive.iterdir())
            if directory.is_dir() and directory.name.endswith("-" + CHANGE_NAME)
        )
    return found


def markdown_documents(root: Path | None = None) -> list[Path]:
    """Every committed Markdown document outside `openspec/`.

    `walked_files` is the suite's own enumeration and prunes that directory,
    the other working trees and the ignored subtrees already; it is a superset
    of the tracked files, which is the safe direction for a prohibition.
    """
    return [path for path in walked_files(root) if path.suffix == ".md"]


def documents_holding_the_recipe(root: Path | None = None) -> list[str]:
    """Every such document carrying a fenced provisioning block, sorted.

    Raises rather than reporting none where the sweep reaches no Markdown
    document at all: a check that read nothing would otherwise report success
    having verified nothing, and this one's whole result is an empty list.
    """
    root = ROOT if root is None else root
    documents = markdown_documents(root)
    if not documents:
        raise AssertionError(
            f"the sweep from {root} reached no Markdown document at all, so the "
            "assertion that no second one holds a copy of the recipe would pass "
            "having read nothing"
        )
    return sorted(
        path.relative_to(root).as_posix()
        for path in documents
        if recipe_blocks(path.read_text(encoding="utf-8", errors="replace"))
    )


class RequirementSourceMixin:
    def source(self) -> tuple[str, str]:
        found = requirement_source()
        self.assertIsNotNone(  # type: ignore[attr-defined]
            found,
            f"*{REQUIREMENT_NAME}* was resolved from neither this change's delta "
            f"specification for `{CAPABILITY}` nor, once this change is archived, "
            "its main specification, so every assertion about the document it "
            "names would pass having read nothing",
        )
        return found  # type: ignore[return-value]

    def named_document(self) -> str:
        source, block = self.source()
        named = named_documents(block)
        self.assertEqual(  # type: ignore[attr-defined]
            1,
            len(named),
            f"*{REQUIREMENT_NAME}* in {source} names {len(named)} Markdown document "
            f"as holding the manual provisioning recipe ({named}), not one. The "
            "scenario's WHEN clause presupposes exactly one: with none, the "
            "operator provisioning a credential by hand is sent nowhere, and with "
            "two, neither this check nor that operator can tell which is the one "
            "that must hold it",
        )
        return named[0]


class TestTheRequirementNamesOneDocumentForTheRecipe(
    RequirementSourceMixin, unittest.TestCase
):
    """SPECIFIED -- scenario "The document this requirement names holds the
    recipe": WHEN this requirement names a committed document as holding the
    manual provisioning recipe. The WHEN clause is asserted rather than assumed,
    because a requirement that stopped naming one would satisfy both THEN
    clauses vacuously."""

    def test_the_requirement_is_resolved_from_exactly_one_source(self) -> None:
        """DERIVED -- this change's tasks.md 3.5, which states the resolution
        rule, and the precondition of every assertion below."""
        source, block = self.source()
        self.assertTrue(block.strip(), f"{source} yielded an empty requirement block")

    def test_this_changes_record_exists_once_live_or_archived(self) -> None:
        """DERIVED -- the premise the resolution rule rests on: "while this
        change's delta is live" and "once this change is archived" are the two
        states, and a record present in both layouts at once is neither. The
        rule prefers the live copy, so a stale live directory beside an archived
        one would silently pin this check to text the archive has superseded."""
        directories = change_record_directories()
        self.assertEqual(
            1,
            len(directories),
            "expected this change's record once, live or archived; found "
            f"{[d.relative_to(ROOT).as_posix() for d in directories]}",
        )

    def test_the_requirement_names_exactly_one_markdown_document(self) -> None:
        """SPECIFIED -- as the class docstring; the count is DERIVED, from the
        clause's singular "a committed document"."""
        self.named_document()


class TestTheNamedDocumentHoldsTheRecipe(RequirementSourceMixin, unittest.TestCase):
    """SPECIFIED -- the same scenario: THEN that document SHALL hold it."""

    def test_the_named_document_exists(self) -> None:
        """SPECIFIED -- a document that is not in the repository holds nothing.
        Asserted separately from the assertion below so that an absent document
        reports its own absence, rather than reporting that the recipe is
        somewhere else."""
        named = self.named_document()
        self.assertTrue(
            (ROOT / named).is_file(),
            f"*{REQUIREMENT_NAME}* names `{named}` as holding the manual "
            "provisioning recipe, and this repository has no such file. A manual "
            "step is performed FROM the document; this sends the operator nowhere "
            "at the moment they are provisioning a credential by hand",
        )

    def test_the_named_document_holds_the_recipe(self) -> None:
        """SPECIFIED -- as the class docstring. What counts as holding it is a
        fenced block carrying `CREATE DATABASE`, which is the sibling module's
        own definition, imported rather than restated."""
        named = self.named_document()
        holders = documents_holding_the_recipe()
        self.assertIn(
            named,
            holders,
            f"*{REQUIREMENT_NAME}* names `{named}` as holding the manual "
            "provisioning recipe, and no fenced block carrying `CREATE DATABASE` "
            f"is in it. The documents that do hold one are {holders}, so the "
            "requirement names a file the procedure has left",
        )


class TestNoSecondDocumentHoldsACopyOfTheRecipe(
    RequirementSourceMixin, unittest.TestCase
):
    """SPECIFIED -- the same scenario: AND no other committed Markdown document
    outside `openspec/` SHALL hold a second copy of it. The added paragraph
    gives the reason in as many words -- two copies of a procedure touching a
    credential drift, and both read as authoritative."""

    def test_the_sweep_reaches_the_committed_markdown_documents(self) -> None:
        """DERIVED -- no clause states it. The assertion below concludes from an
        EMPTY list, which a sweep that reached no file produces identically.
        Anchored on documents at three depths rather than on a count, which any
        edit to the repository would move."""
        swept = {path.relative_to(ROOT).as_posix() for path in markdown_documents()}
        anchors = {"AGENTS.md", "README.md", "platform/README.md"}
        self.assertEqual(
            set(),
            anchors - swept,
            f"the sweep did not reach these committed documents: {sorted(anchors - swept)}",
        )

    def test_the_sweep_does_not_reach_the_specification_directory(self) -> None:
        """SPECIFIED -- "outside `openspec/`". The bound is what keeps the
        change records that quote the recipe as history from breaching the
        obligation on the day it lands, and it is a property of the sweep rather
        than of those records."""
        inside = sorted(
            path.relative_to(ROOT).as_posix()
            for path in markdown_documents()
            if path.relative_to(ROOT).as_posix().startswith(SPECIFICATION_DIRECTORY)
        )
        self.assertEqual(
            [],
            inside,
            f"the sweep reached {len(inside)} document(s) under "
            f"`{SPECIFICATION_DIRECTORY}`: {inside[:5]}. Change records quote the "
            "recipe as history, so every one of them would be reported as a second "
            "copy and this check would be red on a correct tree",
        )

    def test_no_other_markdown_document_outside_the_specifications_holds_a_copy(
        self,
    ) -> None:
        """SPECIFIED -- as the class docstring."""
        named = self.named_document()
        others = [path for path in documents_holding_the_recipe() if path != named]
        self.assertEqual(
            [],
            others,
            f"*{REQUIREMENT_NAME}* names `{named}` as holding the manual "
            f"provisioning recipe, and {others} also carry a fenced block "
            "creating a database. Two copies of a procedure that touches a "
            "credential drift, and both read as authoritative -- the operator "
            "reaches whichever one they opened",
        )


# --------------------------------------------------------------------------
# The detectors above, run over material this file supplies to falsify them.
#
# Every fixture tree is built in a temporary directory and every helper takes
# its root as an argument, which is what makes the negative cases exercisable
# without damaging the real tree.
# --------------------------------------------------------------------------

# A fenced provisioning block, reduced to what makes it one: a here-document
# fed to psql carrying `CREATE DATABASE`. The properties of the living recipe
# are the sibling module's subject and are deliberately not reproduced.
RECIPE_FIXTURE = """\
## Provision the application's database

```sh
psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres <<SQL
CREATE ROLE "$app" WITH LOGIN PASSWORD '$pw';
CREATE DATABASE "$app" OWNER "$app";
SQL
```
"""

# `platform/README.md`'s shape: the recipe named in prose, in inline code, with
# no fenced block at all. The likeliest false positive of a text search, and
# not a copy.
PROSE_MENTION_FIXTURE = """\
Getting a database inside the instance is a manual step today -- the onboarding
document carries the `CREATE ROLE` / `CREATE DATABASE` recipe.
"""

# The other block `platform/README.md` carries: a different recipe, fenced,
# which keying on `CREATE DATABASE` rather than on `CREATE ROLE` excludes.
OTHER_RECIPE_FIXTURE = """\
```sql
CREATE ROLE pgexporter WITH LOGIN PASSWORD 'x';
GRANT pg_monitor TO pgexporter;
```
"""

NAMED_DOCUMENT = "docs/onboard-an-application.md"
SUPERSEDED_DOCUMENT = "docs/bootstrap-a-new-host.md"


def requirement_fixture(document: str | None, extra: str = "") -> str:
    """A requirement block naming `document` as holding the recipe, in the
    shape the delta's own paragraph gives it."""
    naming = (
        f"Until that automation exists, each provisioning is performed by hand by "
        f"an operator, by the recipe in `{document}`, and this requirement obliges "
        f"the provisioning rather than any particular mechanism for it."
        if document is not None
        else "Until that automation exists, each provisioning is performed by hand."
    )
    return f"""\
### Requirement: {REQUIREMENT_NAME}
The platform stack SHALL run one shared PostgreSQL instance.

**One divergence is stated rather than hidden, as of 2026-09-13.** The mechanism is tracked in `docs/backlog.md` as `automate-per-application-database-provisioning`; durable data is governed by *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`).

How a database and its role are provisioned SHALL be automated. {naming}{extra}

#### Scenario: The document this requirement names holds the recipe
- **WHEN** this requirement names a committed document as holding the manual provisioning recipe
- **THEN** that document SHALL hold it
- **AND** no other committed Markdown document outside `openspec/` SHALL hold a second copy of it
"""


class FixtureTreeMixin:
    # Assembled from parts: a literal change-shaped segment after the changes
    # prefix is what this repository's citation sweep forbids.
    CHANGES = "openspec/" + "changes/"
    OTHER_CHANGE = "another" + "-change"
    MAIN = "openspec/specs/" + CAPABILITY + "/spec.md"

    def tree(self, files: dict[str, str]) -> Path:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)  # type: ignore[attr-defined]
        root = Path(scratch.name)
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root

    def delta_of(self, change: str) -> str:
        return self.CHANGES + change + "/specs/" + CAPABILITY + "/spec.md"

    def archived_delta_of(self, change: str, date: str = "2026-09-20") -> str:
        return (
            self.CHANGES
            + ARCHIVE_SEGMENT
            + "/"
            + date
            + "-"
            + change
            + "/specs/"
            + CAPABILITY
            + "/spec.md"
        )


class TestTheResolutionRuleResolves(FixtureTreeMixin, unittest.TestCase):
    """DERIVED -- this change's tasks.md 3.5. The rule is the part of this
    module a reader is most likely to mistake for an oversight, so each of its
    clauses is exercised over a tree written to break it."""

    def test_this_changes_live_delta_is_read_over_another_live_delta_and_the_main_specification(
        self,
    ) -> None:
        """The interval the rule exists for, exactly as it stands today: another
        change carrying a live delta of the same requirement names the document
        this change supersedes, and the main specification still does too. A
        detector reading either would demand two documents each hold the recipe
        while forbidding a second copy, which nothing can satisfy."""
        root = self.tree(
            {
                self.MAIN: requirement_fixture(SUPERSEDED_DOCUMENT),
                self.delta_of(self.OTHER_CHANGE): "## MODIFIED Requirements\n\n"
                + requirement_fixture(SUPERSEDED_DOCUMENT),
                self.delta_of(CHANGE_NAME): "## MODIFIED Requirements\n\n"
                + requirement_fixture(NAMED_DOCUMENT),
            }
        )
        source = requirement_source(root)
        self.assertIsNotNone(source)
        self.assertEqual(self.delta_of(CHANGE_NAME), source[0])
        self.assertEqual([NAMED_DOCUMENT], named_documents(source[1]))

    def test_the_main_specification_is_read_once_this_change_is_archived(self) -> None:
        """The rule's second clause. The archived record is not read: its delta
        is merged into the main specification by then, and reading both would
        reintroduce the two-source ambiguity from the other side."""
        root = self.tree(
            {
                self.MAIN: requirement_fixture(NAMED_DOCUMENT),
                self.archived_delta_of(CHANGE_NAME): "## MODIFIED Requirements\n\n"
                + requirement_fixture(SUPERSEDED_DOCUMENT),
            }
        )
        source = requirement_source(root)
        self.assertIsNotNone(source)
        self.assertEqual(self.MAIN, source[0])
        self.assertEqual([NAMED_DOCUMENT], named_documents(source[1]))

    def test_a_live_delta_that_has_lost_the_requirement_does_not_fall_back(self) -> None:
        """A fall-back here would resolve to the main specification, which names
        the document this change supersedes -- so the check would go green
        against the superseded name at exactly the moment the delta was broken."""
        root = self.tree(
            {
                self.MAIN: requirement_fixture(SUPERSEDED_DOCUMENT),
                self.delta_of(CHANGE_NAME): "## MODIFIED Requirements\n\n"
                "### Requirement: Something Else\ntext\n",
            }
        )
        self.assertIsNone(requirement_source(root))

    def test_a_tree_carrying_the_requirement_nowhere_yields_nothing(self) -> None:
        root = self.tree({self.MAIN: "### Requirement: Something Else\ntext\n"})
        self.assertIsNone(requirement_source(root))

    def test_the_record_is_found_by_name_in_both_layouts(self) -> None:
        root = self.tree(
            {
                self.delta_of(CHANGE_NAME): "x\n",
                self.archived_delta_of(CHANGE_NAME): "x\n",
                self.archived_delta_of(self.OTHER_CHANGE): "x\n",
            }
        )
        self.assertEqual(
            [CHANGE_NAME, "2026-09-20-" + CHANGE_NAME],
            [directory.name for directory in change_record_directories(root)],
        )


class TestTheNamingDetectorFires(unittest.TestCase):
    """Each reading of the requirement's own text, over material written to
    falsify it."""

    def test_a_requirement_naming_the_document_yields_it(self) -> None:
        block = requirement_block(requirement_fixture(NAMED_DOCUMENT), REQUIREMENT_NAME)
        self.assertIsNotNone(block)
        self.assertEqual([NAMED_DOCUMENT], named_documents(block))

    def test_a_requirement_naming_no_document_yields_none(self) -> None:
        """The vacuous case: with no document named, both THEN clauses are
        satisfiable by a repository holding the recipe nowhere at all."""
        block = requirement_block(requirement_fixture(None), REQUIREMENT_NAME)
        self.assertEqual([], named_documents(block))

    def test_a_requirement_naming_two_documents_yields_both(self) -> None:
        """Reported rather than resolved: this is the shape a half-finished move
        leaves, and choosing one of the two is choosing which half to believe."""
        block = requirement_block(
            requirement_fixture(
                NAMED_DOCUMENT,
                extra=f" The older copy of the recipe is in `{SUPERSEDED_DOCUMENT}`.",
            ),
            REQUIREMENT_NAME,
        )
        self.assertEqual([NAMED_DOCUMENT, SUPERSEDED_DOCUMENT], named_documents(block))

    def test_a_specification_citation_is_not_read_as_the_recipe_document(self) -> None:
        """The requirement cites `openspec/specs/...` several times, and the
        backlog once. Neither is a document an operator provisions from."""
        block = requirement_block(requirement_fixture(NAMED_DOCUMENT), REQUIREMENT_NAME)
        self.assertNotIn("docs/backlog.md", named_documents(block))
        self.assertEqual(
            [],
            [path for path in named_documents(block) if path.startswith("openspec/")],
        )

    def test_a_path_in_a_sentence_that_does_not_speak_of_the_recipe_is_not_read(
        self,
    ) -> None:
        """The scoping that keeps the assertion above from depending on the
        exclusion list rather than on what the sentence says."""
        block = requirement_block(
            requirement_fixture(
                NAMED_DOCUMENT,
                extra=" The rebuild runbook is `docs/rebuild-the-host.md`.",
            ),
            REQUIREMENT_NAME,
        )
        self.assertEqual([NAMED_DOCUMENT], named_documents(block))

    def test_an_emphasised_sentence_does_not_run_into_the_next_one(self) -> None:
        """Without the emphasis stripping, the divergence paragraph's bolded
        lead-in runs into the sentence naming the backlog entry, and a sentence
        naming the recipe nowhere becomes a candidate carrying `docs/backlog.md`."""
        text = "**Stated as of 2026-09-13.** The recipe is tracked in `docs/backlog.md`."
        self.assertEqual(2, len(sentences(text)))
        self.assertEqual(["docs/backlog.md"], named_documents(text))


class TestTheCopyDetectorFires(FixtureTreeMixin, unittest.TestCase):
    """The sweep for a second copy, over trees written to falsify it. Each
    fixture below is one of the three deliberate copy classes the added
    paragraph names, plus the copy it actually forbids."""

    def test_the_named_document_holding_the_recipe_is_found(self) -> None:
        root = self.tree({NAMED_DOCUMENT: RECIPE_FIXTURE, "README.md": "# tree\n"})
        self.assertEqual([NAMED_DOCUMENT], documents_holding_the_recipe(root))

    def test_a_second_markdown_document_holding_a_copy_is_reported(self) -> None:
        root = self.tree(
            {
                NAMED_DOCUMENT: RECIPE_FIXTURE,
                SUPERSEDED_DOCUMENT: RECIPE_FIXTURE,
            }
        )
        self.assertEqual(
            [SUPERSEDED_DOCUMENT, NAMED_DOCUMENT],
            documents_holding_the_recipe(root),
        )

    def test_a_prose_mention_of_the_recipe_is_not_a_copy(self) -> None:
        """`platform/README.md`'s shape. A mention names the document; it does
        not send an operator through a second procedure."""
        root = self.tree(
            {NAMED_DOCUMENT: RECIPE_FIXTURE, "platform/README.md": PROSE_MENTION_FIXTURE}
        )
        self.assertEqual([NAMED_DOCUMENT], documents_holding_the_recipe(root))

    def test_a_fenced_block_creating_only_a_role_is_not_a_copy(self) -> None:
        """The `CREATE ROLE pgexporter` block in that same file: a different
        recipe, and the likeliest remaining false positive."""
        root = self.tree(
            {NAMED_DOCUMENT: RECIPE_FIXTURE, "platform/README.md": OTHER_RECIPE_FIXTURE}
        )
        self.assertEqual([NAMED_DOCUMENT], documents_holding_the_recipe(root))

    def test_a_copy_inside_a_change_record_is_not_a_copy(self) -> None:
        """Change records quote the recipe as history. The population is bounded
        to documents outside the specification directory for that reason, and
        this is the fixture that establishes the bound holds."""
        root = self.tree(
            {
                NAMED_DOCUMENT: RECIPE_FIXTURE,
                self.CHANGES + self.OTHER_CHANGE + "/design.md": RECIPE_FIXTURE,
            }
        )
        self.assertEqual([NAMED_DOCUMENT], documents_holding_the_recipe(root))

    def test_a_copy_inside_a_python_module_is_not_a_copy(self) -> None:
        """The sibling module carries three fenced recipe fixtures, one an exact
        copy of the living recipe. The population is Markdown documents, which
        is what excludes them -- and this suite asserting properties of the
        recipe is not a second procedure for an operator to follow."""
        root = self.tree(
            {
                NAMED_DOCUMENT: RECIPE_FIXTURE,
                ".github/tests/test_a_module.py": 'FIXTURE = """' + RECIPE_FIXTURE + '"""\n',
            }
        )
        self.assertEqual([NAMED_DOCUMENT], documents_holding_the_recipe(root))

    def test_a_tree_holding_no_markdown_document_refuses(self) -> None:
        """The guard the empty-list conclusion needs: a sweep that reached
        nothing returns the same empty list as a repository with one copy."""
        root = self.tree({"README.txt": "not markdown\n"})
        with self.assertRaises(AssertionError) as refusal:
            documents_holding_the_recipe(root)
        self.assertIn("reached no Markdown document", str(refusal.exception))


if __name__ == "__main__":
    unittest.main()
