"""Static-assertion tests for the shared PostgreSQL instance receiving its first
per-application database.

Derived from the delta specification of the OpenSpec change
`provision-commerce-ops-database-in-the-shared-instance`, before any
implementation of that change existed -- from that delta at commit `2315199`,
the commit holding the approved plan. The path the delta sits at is not written
here: a change's artifacts move when it is archived, and this repository's
citation convention is to name the change and the artifact in prose instead.

The delta modifies one requirement, *Single Shared PostgreSQL Instance,
Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`).
Every assertion is annotated SPECIFIED (it traces to SHALL text or to a scenario
in that delta) or DERIVED (it traces to that change's `design.md` or `tasks.md`,
or to this file's own judgment, rather than to a scenario). See that change's
`test-plan.md` for the scenario-to-test mapping, the baseline, the scenarios
deliberately left uncovered and why, and the obsolete-test search.

What this file reads, and why each is a static read
---------------------------------------------------
- **The requirement's own text**, for the scenario "The automation trigger has
  fired and the mechanism is not built", whose THEN clause is about what the
  requirement SHALL state.
- **`docs/backlog.md`**, for the entry that requirement says the mechanism is
  tracked under.
- **The recipe in `docs/bootstrap-a-new-host.md`**, which the requirement names
  as how each provisioning is performed until the mechanism exists. What it
  asserts of the recipe is a NECESSARY condition of the scenario "A new
  application requests a database" -- an isolated role, a password generated
  per run and never on a command line -- and never the scenario itself, whose
  subject is host state no read of a file can reach.
- **The change's own `design.md`**, for the scenario "An application's data
  divides into durable and non-durable parts", whose THEN clause is that the
  change recording the database SHALL state the division.

Which text of the requirement is read, and why not simply the main spec
-----------------------------------------------------------------------
The delta is merged into the main specification only when the change is
archived, and the change's implementation reaches the trunk through a pull
request before that. A test reading only the main specification would be red on
every commit of that pull request, including the one the required check must
pass to merge it. So `requirement_sources` reads the requirement as it is about
to stand: the `### Requirement:` block of any live, unarchived change's delta
specification carrying it, and the main specification only when no live change
does. That passes now against the delta, passes after archiving against the
merged main specification, and fails if archiving dropped the text. A later
change modifying this requirement again -- the provisioning mechanism landing,
which replaces the divergence paragraph -- is read in place of both, which is
the right answer: it supersedes these assertions, and its own test author
lists them as obsolete.

The change's record is found by name in the live and the archived layout
rather than at a written path, for the same reason.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable by name through discovery:
    python3 -m unittest discover --start-directory .github/tests -k \\
        test_the_shared_instance_has_its_first_database.TestTheRecipeKeepsThePasswordOffCommandLines.test_the_password_is_expanded_only_into_standard_input

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling import below resolve; `python3 -m unittest
<dotted name>` from the root does not, and errors on that import.

Every check here is a static read, so a check whose target already carries the
property passes having shown nothing about whether it can fail. Each detector is
therefore also run over material this file supplies to falsify it -- the
`...DetectorFires` classes. They add no import beyond the standard library,
spawn no subprocess, and need no network call, credential, container runtime or
Terraform binary.

What no assertion here establishes
----------------------------------
That a database exists, whom it is owned by, who can connect to it, what the
instance's log holds, or that two hosts' passwords differ. Those are host state,
checked from each host by the change's own tasks. Nor that a recipe carrying
every property below runs: that is established by running it.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from test_ci_configuration import ARCHIVE_SEGMENT, ROOT, read_text

# --------------------------------------------------------------------------
# What is read
# --------------------------------------------------------------------------

CAPABILITY = "iac-platform-services"
REQUIREMENT_NAME = "Single Shared PostgreSQL Instance, Per-Application Databases"
CHANGE_NAME = "provision-commerce-ops-database-in-the-shared-instance"

# The application the delta names as having fired the trigger.
APPLICATION = "commerce-ops"

BOOTSTRAP = ROOT / "docs" / "bootstrap-a-new-host.md"
BACKLOG = ROOT / "docs" / "backlog.md"

REQUIREMENT_HEADING = re.compile(r"^###\s+Requirement:\s*(?P<name>.+?)\s*$")
# A heading at level three or above ends a requirement block; a scenario
# (level four) does not.
BLOCK_END = re.compile(r"^#{1,3}\s")
SCENARIO_HEADING = re.compile(r"^####\s+Scenario:")


def requirement_block(spec_text: str, name: str = REQUIREMENT_NAME) -> str | None:
    """The `### Requirement:` block named `name`, heading included, or None."""
    lines = spec_text.splitlines()
    for index, line in enumerate(lines):
        heading = REQUIREMENT_HEADING.match(line)
        if heading is None or heading.group("name") != name:
            continue
        end = index + 1
        while end < len(lines) and not BLOCK_END.match(lines[end]):
            end += 1
        return "\n".join(lines[index:end])
    return None


def requirement_sources(root: Path | None = None) -> list[tuple[str, str]]:
    """The requirement as it is about to stand, as `(relative path, block)`.

    Every live change's delta specification carrying the requirement, or --
    only where none does -- the main specification. Archived changes are never
    read: their deltas are already merged into the main specification.
    """
    root = ROOT if root is None else root
    changes = root / "openspec" / "changes"
    live: list[tuple[str, str]] = []
    if changes.is_dir():
        for directory in sorted(changes.iterdir()):
            if not directory.is_dir() or directory.name == ARCHIVE_SEGMENT:
                continue
            delta = directory / "specs" / CAPABILITY / "spec.md"
            if not delta.is_file():
                continue
            block = requirement_block(delta.read_text(encoding="utf-8"))
            if block is not None:
                live.append((delta.relative_to(root).as_posix(), block))
    if live:
        return live
    main = root / "openspec" / "specs" / CAPABILITY / "spec.md"
    if main.is_file():
        block = requirement_block(main.read_text(encoding="utf-8"))
        if block is not None:
            return [(main.relative_to(root).as_posix(), block)]
    return []


def body_paragraphs(block: str) -> list[str]:
    """The requirement's prose paragraphs: heading and scenarios excluded."""
    body: list[str] = []
    for line in block.splitlines()[1:]:
        if SCENARIO_HEADING.match(line):
            break
        body.append(line)
    return [p.strip() for p in re.split(r"\n\s*\n", "\n".join(body)) if p.strip()]


# --------------------------------------------------------------------------
# The divergence paragraph
# --------------------------------------------------------------------------

ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
FIRED = re.compile(r"\btrigger\b.*\bfired\b|\bfired\b.*\btrigger\b", re.IGNORECASE | re.DOTALL)
OWED = re.compile(r"\bowed\b")
NOT_DISCHARGED = re.compile(r"manual provisioning SHALL NOT be read as discharging")
BACKLOG_ENTRY = re.compile(r"`docs/backlog\.md`\s+as\s+`(?P<entry>[a-z0-9]+(?:-[a-z0-9]+)+)`")
SUPERSEDED_PREMISE = re.compile(r"no application has needed one", re.IGNORECASE)

MISSING_FIRED = "a paragraph stating that the automation trigger fired"
MISSING_DATE = "a date on that statement"
MISSING_APPLICATION = f"the application that fired it, `{APPLICATION}`"
MISSING_OWED = "that the mechanism and its credential path are owed"
MISSING_NOT_DISCHARGED = "that a manual provisioning SHALL NOT be read as discharging the obligation"
MISSING_BACKLOG_ENTRY = "the `docs/backlog.md` entry the mechanism is tracked under"


def divergence_paragraphs(block: str) -> list[str]:
    return [p for p in body_paragraphs(block) if FIRED.search(p)]


def divergence_omissions(block: str) -> list[str]:
    """Which of the scenario's stated elements the requirement does not state."""
    paragraphs = divergence_paragraphs(block)
    if not paragraphs:
        return [
            MISSING_FIRED,
            MISSING_DATE,
            MISSING_APPLICATION,
            MISSING_OWED,
            MISSING_NOT_DISCHARGED,
            MISSING_BACKLOG_ENTRY,
        ]
    omissions: list[str] = []
    if not any(ISO_DATE.search(p) for p in paragraphs):
        omissions.append(MISSING_DATE)
    if not any(f"`{APPLICATION}`" in p for p in paragraphs):
        omissions.append(MISSING_APPLICATION)
    if not any(
        "mechanism" in p and "credential path" in p and OWED.search(p) for p in paragraphs
    ):
        omissions.append(MISSING_OWED)
    if not any(NOT_DISCHARGED.search(p) for p in paragraphs):
        omissions.append(MISSING_NOT_DISCHARGED)
    if tracked_backlog_entry(block) is None:
        omissions.append(MISSING_BACKLOG_ENTRY)
    return omissions


def tracked_backlog_entry(block: str) -> str | None:
    for paragraph in divergence_paragraphs(block):
        match = BACKLOG_ENTRY.search(paragraph)
        if match is not None:
            return match.group("entry")
    return None


class RequirementSourcesMixin:
    def sources(self) -> list[tuple[str, str]]:
        found = requirement_sources()
        self.assertTrue(  # type: ignore[attr-defined]
            found,
            f"*{REQUIREMENT_NAME}* was found neither in a live change's delta "
            f"specification for `{CAPABILITY}` nor in its main specification, so "
            "every assertion about its text would pass having read nothing",
        )
        return found


class TestTheRequirementIsReadAtAll(RequirementSourcesMixin, unittest.TestCase):
    """A check that read nothing reports success having verified nothing."""

    def test_the_requirement_block_is_found_with_its_prose_and_scenarios(self) -> None:
        """DERIVED -- precondition of every assertion over the requirement."""
        for source, block in self.sources():
            with self.subTest(source=source):
                self.assertGreaterEqual(len(body_paragraphs(block)), 3, source)
                self.assertGreaterEqual(
                    len(re.findall(r"^####\s+Scenario:", block, re.MULTILINE)), 2, source
                )


class TestTheRequirementStatesTheTriggerHasFired(RequirementSourcesMixin, unittest.TestCase):
    """SPECIFIED -- scenario "The automation trigger has fired and the mechanism
    is not built": WHEN an application's database in the shared instance has
    been provisioned, or its password delivered, by hand, THEN this requirement
    SHALL state, dated, which application fired the trigger and that the
    mechanism and its credential path are owed, AND that manual provisioning
    SHALL NOT be read as discharging the obligation to automate it."""

    def _assert_stated(self, element: str) -> None:
        for source, block in self.sources():
            with self.subTest(source=source):
                self.assertNotIn(
                    element,
                    divergence_omissions(block),
                    f"*{REQUIREMENT_NAME}* in {source} does not state {element}",
                )

    def test_the_requirement_states_that_the_trigger_fired(self) -> None:
        """SPECIFIED -- as the class docstring."""
        self._assert_stated(MISSING_FIRED)

    def test_that_statement_is_dated(self) -> None:
        """SPECIFIED -- "SHALL state, dated"."""
        self._assert_stated(MISSING_DATE)

    def test_that_statement_names_the_application_that_fired_it(self) -> None:
        """SPECIFIED -- "which application fired the trigger". The delta names
        `commerce-ops`, provisioned by hand on both hosts."""
        self._assert_stated(MISSING_APPLICATION)

    def test_it_states_the_mechanism_and_its_credential_path_are_owed(self) -> None:
        """SPECIFIED -- "that the mechanism and its credential path are owed"."""
        self._assert_stated(MISSING_OWED)

    def test_it_says_manual_provisioning_does_not_discharge_the_obligation(self) -> None:
        """SPECIFIED -- "that manual provisioning SHALL NOT be read as
        discharging the obligation to automate it"."""
        self._assert_stated(MISSING_NOT_DISCHARGED)

    def test_the_superseded_premise_is_no_longer_stated(self) -> None:
        """DERIVED -- the requirement as it stood said automation was deferred
        "because no application has needed one". The modified requirement states
        the opposite, and a requirement carrying both would assert its own
        trigger had and had not fired."""
        for source, block in self.sources():
            with self.subTest(source=source):
                self.assertIsNone(
                    SUPERSEDED_PREMISE.search(block),
                    f"*{REQUIREMENT_NAME}* in {source} still says no application "
                    "has needed a database, which the fired trigger falsifies",
                )


class TestTheBacklogCarriesTheEntryTheRequirementNames(
    RequirementSourcesMixin, unittest.TestCase
):
    """SPECIFIED -- the modified requirement's body: "The mechanism is tracked in
    `docs/backlog.md` as `automate-per-application-database-provisioning`"."""

    def test_the_requirement_names_the_backlog_entry(self) -> None:
        """SPECIFIED -- as the class docstring."""
        for source, block in self.sources():
            with self.subTest(source=source):
                self.assertIsNotNone(
                    tracked_backlog_entry(block),
                    f"*{REQUIREMENT_NAME}* in {source} names no `docs/backlog.md` "
                    "entry for the owed mechanism",
                )

    def test_the_backlog_carries_that_entry(self) -> None:
        """SPECIFIED -- as the class docstring. A necessary condition only: this
        establishes that the backlog names the entry, not that it is an entry
        rather than a mention inside another one."""
        backlog = read_text(BACKLOG)
        for source, block in self.sources():
            entry = tracked_backlog_entry(block)
            if entry is None:
                continue  # reported by the test above
            with self.subTest(source=source, entry=entry):
                self.assertTrue(
                    entry in backlog,
                    f"*{REQUIREMENT_NAME}* in {source} says the owed mechanism is "
                    f"tracked in {BACKLOG.relative_to(ROOT)} as `{entry}`, and that "
                    "file does not name it",
                )


SUPERSEDED_REQUIREMENT_FIXTURE = f"""\
### Requirement: {REQUIREMENT_NAME}
The platform stack SHALL run one shared PostgreSQL instance.

This requirement binds when an application actually keeps data on this host.

How a database and its role are provisioned inside the instance is deliberately not **automated**, because no application has needed one and a mechanism designed against no consumer is guesswork.

#### Scenario: A new application requests a database
- **WHEN** an application needs one
- **THEN** a database SHALL be provisioned

#### Scenario: An application needs durable storage
- **WHEN** it needs one
- **THEN** it SHALL use an external managed service
"""

CONFORMING_REQUIREMENT_FIXTURE = f"""\
### Requirement: {REQUIREMENT_NAME}
The platform stack SHALL run one shared PostgreSQL instance.

This requirement binds when an application actually keeps data on this host.

How a database and its role are provisioned SHALL be automated, and the trigger for that obligation is the first application given a database in this instance.

**One divergence is stated rather than hidden, as of 2026-09-13.** That trigger fired on 2026-09-13, when `{APPLICATION}` became the first application given a database in this instance. The obligation is due and is not met: the mechanism and its credential path are owed and not yet built. A manual provisioning SHALL NOT be read as discharging it. The mechanism is tracked in `docs/backlog.md` as `automate-per-application-database-provisioning`.

#### Scenario: A new application requests a database
- **WHEN** an application needs one
- **THEN** a database SHALL be provisioned

## Another section
"""


class TestTheDivergenceDetectorFires(unittest.TestCase):
    """The detectors above run over material written to falsify them."""

    def test_a_conforming_requirement_yields_no_omission(self) -> None:
        block = requirement_block(CONFORMING_REQUIREMENT_FIXTURE)
        self.assertIsNotNone(block)
        self.assertEqual([], divergence_omissions(block))
        self.assertEqual(
            "automate-per-application-database-provisioning", tracked_backlog_entry(block)
        )
        self.assertIsNone(SUPERSEDED_PREMISE.search(block))

    def test_the_requirement_as_it_stood_is_reported_on_every_element(self) -> None:
        block = requirement_block(SUPERSEDED_REQUIREMENT_FIXTURE)
        self.assertIsNotNone(block)
        self.assertIn(MISSING_FIRED, divergence_omissions(block))
        self.assertIsNotNone(SUPERSEDED_PREMISE.search(block))

    def test_the_trigger_mentioned_but_not_fired_is_not_a_divergence(self) -> None:
        """The obligation paragraph names the trigger too, and must not satisfy
        the check on its own."""
        block = requirement_block(CONFORMING_REQUIREMENT_FIXTURE)
        divergence = block.split("**One divergence")[0] + "\n#### Scenario: x\n"
        self.assertIn(MISSING_FIRED, divergence_omissions(divergence))

    def _without(self, old: str, new: str) -> list[str]:
        return divergence_omissions(
            requirement_block(CONFORMING_REQUIREMENT_FIXTURE.replace(old, new))
        )

    def test_an_undated_divergence_is_reported(self) -> None:
        self.assertIn(MISSING_DATE, self._without("2026-09-13", "recently"))

    def test_a_divergence_naming_no_application_is_reported(self) -> None:
        self.assertIn(MISSING_APPLICATION, self._without(f"`{APPLICATION}`", "an application"))

    def test_a_divergence_not_saying_the_credential_path_is_owed_is_reported(self) -> None:
        self.assertIn(
            MISSING_OWED,
            self._without("the mechanism and its credential path are owed", "the mechanism is owed"),
        )

    def test_a_divergence_permitting_manual_discharge_is_reported(self) -> None:
        self.assertIn(
            MISSING_NOT_DISCHARGED,
            self._without("SHALL NOT be read as discharging", "discharges"),
        )

    def test_a_divergence_naming_no_backlog_entry_is_reported(self) -> None:
        self.assertIn(
            MISSING_BACKLOG_ENTRY,
            self._without(" as `automate-per-application-database-provisioning`", ""),
        )

    def test_a_block_stops_at_the_next_requirement(self) -> None:
        text = CONFORMING_REQUIREMENT_FIXTURE.replace(
            "## Another section", "### Requirement: Next\nno application has needed one"
        )
        self.assertIsNone(SUPERSEDED_PREMISE.search(requirement_block(text)))


class TestTheRequirementIsReadWhereItIsAboutToStand(unittest.TestCase):
    """DERIVED -- this file's choice, stated in the module docstring: the text
    read survives the change being archived."""

    def _tree(self, files: dict[str, str]) -> Path:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name)
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root

    MAIN = f"openspec/specs/{CAPABILITY}/spec.md"
    # Assembled from parts: a literal change-shaped segment after the
    # changes prefix is what this repository's citation sweep forbids.
    FIXTURE_CHANGE = "some" + "-change"
    LIVE = "openspec/changes/" + FIXTURE_CHANGE + "/specs/" + CAPABILITY + "/spec.md"
    ARCHIVED = (
        "openspec/changes/" + ARCHIVE_SEGMENT + "/2026-01-01-" + FIXTURE_CHANGE + "/specs/"
        + CAPABILITY + "/spec.md"
    )

    def test_a_live_delta_is_read_in_place_of_the_main_specification(self) -> None:
        root = self._tree(
            {
                self.MAIN: SUPERSEDED_REQUIREMENT_FIXTURE,
                self.LIVE: "## MODIFIED Requirements\n\n" + CONFORMING_REQUIREMENT_FIXTURE,
            }
        )
        sources = requirement_sources(root)
        self.assertEqual([self.LIVE], [source for source, _ in sources])

    def test_the_main_specification_is_read_once_no_live_delta_carries_it(self) -> None:
        root = self._tree(
            {
                self.MAIN: CONFORMING_REQUIREMENT_FIXTURE,
                self.ARCHIVED: "## MODIFIED Requirements\n\n" + SUPERSEDED_REQUIREMENT_FIXTURE,
            }
        )
        sources = requirement_sources(root)
        self.assertEqual([self.MAIN], [source for source, _ in sources])
        self.assertEqual([], divergence_omissions(sources[0][1]))

    def test_a_live_delta_of_another_requirement_is_not_read(self) -> None:
        root = self._tree(
            {
                self.MAIN: CONFORMING_REQUIREMENT_FIXTURE,
                self.LIVE: "## MODIFIED Requirements\n\n### Requirement: Other\ntext\n",
            }
        )
        self.assertEqual([self.MAIN], [source for source, _ in requirement_sources(root)])

    def test_a_tree_carrying_the_requirement_nowhere_yields_nothing(self) -> None:
        root = self._tree({self.MAIN: "### Requirement: Other\ntext\n"})
        self.assertEqual([], requirement_sources(root))


# --------------------------------------------------------------------------
# The recipe
# --------------------------------------------------------------------------

FENCE = re.compile(r"^\s*(?P<marker>```+|~~~+)")
CREATE_DATABASE = re.compile(r"\bCREATE\s+DATABASE\b")
# `<<` or `<<-`, an optionally quoted delimiter; `<<<` is a here-string and not
# a here-document.
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(?P<quote>['\"]?)(?P<word>[A-Za-z_][A-Za-z0-9_]*)(?P=quote)")
PASSWORD_ASSIGNMENT = re.compile(r"\b(?P<var>[A-Za-z_][A-Za-z0-9_]*)=\$\(\s*openssl\s+rand\b")
PSQL = re.compile(r"\bpsql\b")
COMMAND_OPTION = re.compile(r"(?:^|\s)(?:-c|--command)(?:\s|=|$)")
STATEMENT_OUTSIDE_STDIN = re.compile(r"\b(?:CREATE|ALTER)\s+(?:ROLE|DATABASE)\b|\bREVOKE\s")
GH_SECRET_LIST = re.compile(r"\bgh\s+secret\s+list\b")
GH_SECRET_SET = re.compile(r"\bgh\s+secret\s+set\b")
SSH = re.compile(r"(?:^|[\s(;|&])ssh\s")
NONZERO_EXIT = re.compile(r"\bexit\s+[1-9][0-9]*\b")

IDENTIFIER_POSITIONS = (
    re.compile(r"\b(?:CREATE|ALTER)\s+ROLE\s+(?P<id>[^\s;]+)", re.IGNORECASE),
    re.compile(r"\bCREATE\s+DATABASE\s+(?P<id>[^\s;]+)", re.IGNORECASE),
    re.compile(r"\bOWNER\s+(?:TO\s+)?(?P<id>[^\s;]+)", re.IGNORECASE),
    re.compile(r"\bON\s+DATABASE\s+(?P<id>[^\s;]+)", re.IGNORECASE),
)
# `"name"`, or psql's own identifier interpolation `:"variable"`.
QUOTED_IDENTIFIER = re.compile(r':?"[^"]+"')
CREATE_ROLE = re.compile(r"\bCREATE\s+ROLE\s+(?P<id>[^\s;]+)", re.IGNORECASE)
CREATE_DATABASE_OWNED = re.compile(
    r"\bCREATE\s+DATABASE\s+(?P<db>[^\s;]+)(?:\s+(?:WITH\s+)?OWNER\s*=?\s*(?P<owner>[^\s;]+))?",
    re.IGNORECASE,
)
REVOKE = re.compile(
    r"\bREVOKE\s+(?P<privileges>[A-Za-z_,\s]+?)\s+ON\s+DATABASE\s+(?P<db>[^\s;]+)\s+FROM\s+(?P<grantees>[^;]+)",
    re.IGNORECASE,
)


def fenced_blocks(text: str) -> list[tuple[int, str]]:
    """Every fenced code block, as `(line number of its first content line, content)`."""
    blocks: list[tuple[int, str]] = []
    marker: str | None = None
    start = 0
    content: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if marker is None:
            fence = FENCE.match(line)
            if fence is not None:
                marker, start, content = fence.group("marker"), number + 1, []
            continue
        if line.strip().startswith(marker):
            blocks.append((start, "\n".join(content)))
            marker = None
            continue
        content.append(line)
    return blocks


def recipe_blocks(text: str) -> list[tuple[int, str]]:
    """The fenced blocks that provision a database: those carrying `CREATE DATABASE`."""
    return [block for block in fenced_blocks(text) if CREATE_DATABASE.search(block[1])]


def heredoc_openers(lines: list[str]) -> list[int | None]:
    """For each line, the index of the line whose here-document it is body of --
    the terminating delimiter line included -- or None for a command line."""
    owner: list[int | None] = [None] * len(lines)
    pending: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if pending:
            opener, word = pending[0]
            owner[index] = opener
            if line.strip() == word:
                pending.pop(0)
            continue
        if line.lstrip().startswith("#"):
            continue
        pending.extend((index, match.group("word")) for match in HEREDOC.finditer(line))
    return owner


def command_lines(block: str) -> list[tuple[int, str]]:
    """`(index, line)` for every line the shell reads as a command, not as
    here-document input and not as a comment."""
    lines = block.splitlines()
    owner = heredoc_openers(lines)
    return [
        (index, line)
        for index, line in enumerate(lines)
        if owner[index] is None and not line.lstrip().startswith("#")
    ]


def standard_input_sql(block: str) -> str:
    """Every here-document body in the block, SQL comments removed."""
    lines = block.splitlines()
    owner = heredoc_openers(lines)
    body = [re.sub(r"--.*$", "", line) for index, line in enumerate(lines) if owner[index] is not None]
    return "\n".join(body)


def password_variable(block: str) -> str | None:
    match = PASSWORD_ASSIGNMENT.search(block)
    return None if match is None else match.group("var")


def password_on_command_lines(block: str) -> list[str]:
    """Every command line expanding the generated password other than a shell
    builtin writing it into a pipe. A here-document body is standard input and
    is not a command line."""
    variable = password_variable(block)
    if variable is None:
        return []
    expansion = re.compile(r"\$\{?" + re.escape(variable) + r"\b")
    safe_feed = re.compile(
        r"^\s*(?:printf\s+(['\"])%s(?:\\n)?\1|echo(?:\s+-n)?)\s+\"\$\{?"
        + re.escape(variable)
        + r"\}?\"\s*\|"
    )
    return [
        f"{index + 1}: {line.strip()}"
        for index, line in command_lines(block)
        if expansion.search(line) and not safe_feed.match(line)
    ]


def statements_not_over_standard_input(block: str) -> list[str]:
    """Every `psql` given a statement as an option, and every provisioning
    statement written on a command line rather than in a here-document."""
    offences: list[str] = []
    for index, line in command_lines(block):
        psql = PSQL.search(line)
        if psql is not None and COMMAND_OPTION.search(line[psql.end():]):
            offences.append(f"{index + 1}: psql given a statement as an option: {line.strip()}")
        elif STATEMENT_OUTSIDE_STDIN.search(line):
            offences.append(f"{index + 1}: statement on a command line: {line.strip()}")
    lines = block.splitlines()
    owner = heredoc_openers(lines)
    openers = {owner[index] for index, line in enumerate(lines) if owner[index] is not None and CREATE_DATABASE.search(line)}
    if not openers:
        offences.append("no here-document carries `CREATE DATABASE`")
    for opener in sorted(o for o in openers if o is not None):
        if not PSQL.search(lines[opener]):
            offences.append(
                f"{opener + 1}: the here-document carrying `CREATE DATABASE` is not fed to psql on its own line"
            )
    return offences


def unquoted_identifiers(sql: str) -> list[str]:
    offences: list[str] = []
    for pattern in IDENTIFIER_POSITIONS:
        for match in pattern.finditer(sql):
            if not QUOTED_IDENTIFIER.fullmatch(match.group("id")):
                offences.append(" ".join(match.group(0).split()))
    return offences


def database_ownership_offences(sql: str) -> list[str]:
    roles = {match.group("id") for match in CREATE_ROLE.finditer(sql)}
    offences: list[str] = []
    databases = list(CREATE_DATABASE_OWNED.finditer(sql))
    if not databases:
        offences.append("no `CREATE DATABASE`")
    for match in databases:
        owner = match.group("owner")
        if owner is None:
            offences.append(f"database {match.group('db')} is created with no OWNER")
        elif owner not in roles:
            offences.append(
                f"database {match.group('db')} is owned by {owner}, which is not the role the recipe creates ({sorted(roles)})"
            )
    return offences


def privileges_revoked_from_public(sql: str) -> dict[str, set[str]]:
    revoked: dict[str, set[str]] = {}
    for match in REVOKE.finditer(sql):
        grantees = {g.strip().upper() for g in match.group("grantees").split(",")}
        if "PUBLIC" not in grantees:
            continue
        privileges: set[str] = set()
        for privilege in match.group("privileges").split(","):
            name = " ".join(privilege.split()).upper()
            if name in ("ALL", "ALL PRIVILEGES"):
                privileges |= {"CONNECT", "TEMPORARY", "CREATE"}
            elif name == "TEMP":
                privileges.add("TEMPORARY")
            else:
                privileges.add(name)
        revoked.setdefault(match.group("db"), set()).update(privileges)
    return revoked


def created_databases(sql: str) -> list[str]:
    return [match.group("db") for match in CREATE_DATABASE_OWNED.finditer(sql)]


def unrevoked_privilege(sql: str, privilege: str) -> list[str]:
    revoked = privileges_revoked_from_public(sql)
    databases = created_databases(sql)
    if not databases:
        return ["no `CREATE DATABASE`"]
    return [
        f"{privilege} on database {db} is not revoked from PUBLIC"
        for db in databases
        if privilege not in revoked.get(db, set())
    ]


def refusal_offences(block: str) -> list[str]:
    """Whether the Environment's secret names are read, and a non-zero exit
    is reachable, before the secret is set or the host is touched."""
    lines = command_lines(block)

    def first(pattern: re.Pattern[str]) -> int | None:
        return next((index for index, line in lines if pattern.search(line)), None)

    listed, setting, host = first(GH_SECRET_LIST), first(GH_SECRET_SET), first(SSH)
    offences: list[str] = []
    if listed is None:
        offences.append("the Environment's secret names are never read (`gh secret list`)")
    if setting is None:
        offences.append("the secret is never set (`gh secret set`)")
    if offences:
        return offences
    before = min(i for i in (setting, host) if i is not None)
    if listed > before:
        offences.append("the secret names are read only after the secret is set or the host is reached")
        return offences
    if not any(listed < index < before and NONZERO_EXIT.search(line) for index, line in lines):
        offences.append(
            "no non-zero exit lies between reading the secret names and setting the secret, so nothing refuses"
        )
    return offences


class RecipeMixin:
    def recipe(self) -> str:
        blocks = recipe_blocks(read_text(BOOTSTRAP))
        self.assertEqual(  # type: ignore[attr-defined]
            1,
            len(blocks),
            f"{BOOTSTRAP.relative_to(ROOT)} carries {len(blocks)} fenced block(s) "
            "carrying `CREATE DATABASE`, at line(s) "
            f"{[start for start, _ in blocks]}; the recipe is one block pasted whole, "
            "so that one shell holds the password for both the secret and the host",
        )
        return blocks[0][1]


class TestTheRecipeIsReadAtAll(RecipeMixin, unittest.TestCase):
    def test_the_document_carries_exactly_one_provisioning_block(self) -> None:
        """DERIVED -- design.md decision 5 and 6: the recipe is pasted whole into
        one shell, because its guarantees rest on one shell holding the password
        for both `gh secret set` and `psql`. Also the precondition of every
        recipe assertion below."""
        self.recipe()

    def test_that_block_generates_the_password_it_delivers(self) -> None:
        """DERIVED -- a necessary condition of scenario "A new application
        requests a database": "that role's password SHALL be generated for this
        host alone". A password generated inside the block, per paste, is what
        makes one run's password independent of another's; design.md decision
        5 names `openssl rand -hex 32`, and only the generator is asserted."""
        self.assertIsNotNone(
            password_variable(self.recipe()),
            "the provisioning block assigns no variable from `openssl rand`, so the "
            "password is not generated per run inside the block",
        )


class TestTheRecipeKeepsThePasswordOffCommandLines(RecipeMixin, unittest.TestCase):
    """DERIVED -- design.md decision 5, "The password never on a command line",
    as a necessary condition of scenario "A new application requests a
    database": the password "delivered only to this host's deploy target"."""

    def test_the_password_is_expanded_only_into_standard_input(self) -> None:
        recipe = self.recipe()
        self.assertIsNotNone(password_variable(recipe), "no generated password to follow")
        offences = password_on_command_lines(recipe)
        self.assertEqual(
            [],
            offences,
            "the generated password is expanded onto a command line, where shell "
            "history and /proc/<pid>/cmdline carry it:\n  " + "\n  ".join(offences),
        )


class TestTheRecipeRunsItsStatementsOverStandardInput(RecipeMixin, unittest.TestCase):
    """DERIVED -- design.md decision 5, "Statements over stdin": `CREATE
    DATABASE` cannot run inside the transaction block a multi-statement `psql
    -c` opens, which is the defect the change found by running the recipe."""

    def test_no_statement_is_passed_to_psql_as_an_option(self) -> None:
        offences = statements_not_over_standard_input(self.recipe())
        self.assertEqual([], offences, "\n".join(offences))


class TestTheRecipeQuotesItsIdentifiers(RecipeMixin, unittest.TestCase):
    """DERIVED -- design.md decision 4: `commerce-ops` carries a hyphen, and an
    unquoted hyphenated identifier is a syntax error."""

    def test_every_role_and_database_identifier_is_double_quoted(self) -> None:
        sql = standard_input_sql(self.recipe())
        offences = unquoted_identifiers(sql)
        self.assertTrue(CREATE_DATABASE.search(sql), "no `CREATE DATABASE` in standard input to check")
        self.assertEqual([], offences, "unquoted identifier(s):\n  " + "\n  ".join(offences))


class TestTheRecipeGivesTheDatabaseToItsOwnRole(RecipeMixin, unittest.TestCase):
    """Necessary conditions of scenario "A new application requests a
    database": "that database SHALL be owned by a role of the application's own,
    which no other application's role can connect to"."""

    def test_the_database_is_owned_by_the_role_the_recipe_creates(self) -> None:
        """SPECIFIED -- "owned by a role of the application's own", read as a
        property of the recipe that performs each provisioning."""
        offences = database_ownership_offences(standard_input_sql(self.recipe()))
        self.assertEqual([], offences, "\n".join(offences))

    def test_connect_is_revoked_from_public(self) -> None:
        """SPECIFIED -- "which no other application's role can connect to". A
        database created with defaults grants CONNECT to PUBLIC (design.md,
        Context, measured), so without the revoke every role in the instance
        can connect."""
        offences = unrevoked_privilege(standard_input_sql(self.recipe()), "CONNECT")
        self.assertEqual([], offences, "\n".join(offences))

    def test_temporary_is_revoked_from_public(self) -> None:
        """DERIVED -- design.md decision 5 revokes TEMPORARY with CONNECT; the
        scenario names connecting only."""
        offences = unrevoked_privilege(standard_input_sql(self.recipe()), "TEMPORARY")
        self.assertEqual([], offences, "\n".join(offences))


class TestTheRecipeRefusesAnAlreadySetSecretName(RecipeMixin, unittest.TestCase):
    """DERIVED -- design.md decision 5, "A secret name nothing in that
    Environment already uses": production's Environment already holds
    `POSTGRES_PASSWORD`, and overwriting it is an outage with the old value
    unrecoverable, so the block reads the names first and refuses."""

    def test_secret_names_are_read_and_a_refusal_precedes_any_write(self) -> None:
        offences = refusal_offences(self.recipe())
        self.assertEqual([], offences, "\n".join(offences))


CONFORMING_RECIPE_DOCUMENT = r"""
### 8.3 Provision the application's database

```sh
(
set -eu
app=<app> secret=<SECRET> repo=<org>/<app> env=<environment> host=<operator>@<host> rotate=no
names=$(gh secret list --repo "$repo" --env "$env" --json name --jq '.[].name')
if printf '%s\n' "$names" | grep -qx "$secret" && [ "$rotate" != yes ]; then
  echo "refusing: $secret is already set in $env" >&2; exit 1
fi
pw=$(openssl rand -hex 32)
printf '%s' "$pw" | gh secret set "$secret" --repo "$repo" --env "$env"
ssh "$host" 'docker exec -i platform-postgres-1 sh -c '\''psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres'\' <<SQL
SET log_statement = 'none';
SELECT NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$app') AS create_role,
       NOT EXISTS (SELECT FROM pg_database WHERE datname = '$app') AS create_database \gset
\if :create_role
CREATE ROLE "$app" WITH LOGIN PASSWORD '$pw';
\else
ALTER ROLE "$app" WITH LOGIN PASSWORD '$pw';
\endif
\if :create_database
CREATE DATABASE "$app" OWNER "$app";
\endif
REVOKE CONNECT, TEMPORARY ON DATABASE "$app" FROM PUBLIC;
SQL
)
```

Another block, which provisions nothing:

```sh
docker ps
```
"""

# The shape the committed recipe had before this change, as the change's
# handoff and proposal describe it: one `psql -c` carrying both statements,
# the password on its command line, identifiers unquoted, nothing revoked.
SUPERSEDED_RECIPE_DOCUMENT = """
```sh
PASSWORD=$(openssl rand -hex 32)
docker exec platform-postgres-1 psql -U postgres -c "CREATE ROLE commerce-ops LOGIN PASSWORD '$PASSWORD'; CREATE DATABASE commerce-ops OWNER commerce-ops;"
```
"""


class TestTheRecipeDetectorsFire(unittest.TestCase):
    """Each recipe detector runs over material written to falsify it."""

    def recipe(self, document: str = CONFORMING_RECIPE_DOCUMENT) -> str:
        blocks = recipe_blocks(document)
        self.assertEqual(1, len(blocks), blocks)
        return blocks[0][1]

    def replaced(self, old: str, new: str) -> str:
        self.assertIn(old, CONFORMING_RECIPE_DOCUMENT)
        return self.recipe(CONFORMING_RECIPE_DOCUMENT.replace(old, new))

    def test_the_conforming_recipe_yields_no_offence(self) -> None:
        recipe = self.recipe()
        sql = standard_input_sql(recipe)
        self.assertEqual("pw", password_variable(recipe))
        self.assertEqual([], password_on_command_lines(recipe))
        self.assertEqual([], statements_not_over_standard_input(recipe))
        self.assertEqual([], unquoted_identifiers(sql))
        self.assertEqual([], database_ownership_offences(sql))
        self.assertEqual([], unrevoked_privilege(sql, "CONNECT"))
        self.assertEqual([], unrevoked_privilege(sql, "TEMPORARY"))
        self.assertEqual([], refusal_offences(recipe))

    def test_the_superseded_recipe_is_reported_on_every_property(self) -> None:
        recipe = self.recipe(SUPERSEDED_RECIPE_DOCUMENT)
        sql = standard_input_sql(recipe)
        self.assertEqual(1, len(password_on_command_lines(recipe)))
        self.assertTrue(statements_not_over_standard_input(recipe))
        self.assertTrue(unrevoked_privilege(sql, "CONNECT"))
        self.assertTrue(refusal_offences(recipe))
        # Nothing reaches psql over standard input, so the quoting check reads
        # the command line instead to show it fires on this shape.
        self.assertEqual(3, len(unquoted_identifiers(recipe)))

    def test_two_provisioning_blocks_are_both_found(self) -> None:
        document = CONFORMING_RECIPE_DOCUMENT + SUPERSEDED_RECIPE_DOCUMENT
        self.assertEqual(2, len(recipe_blocks(document)))

    def test_the_password_passed_as_an_argument_is_reported(self) -> None:
        recipe = self.replaced(
            """printf '%s' "$pw" | gh secret set "$secret" --repo "$repo" --env "$env\"""",
            """gh secret set "$secret" --body "$pw" --repo "$repo" --env "$env\"""",
        )
        offences = password_on_command_lines(recipe)
        self.assertEqual(1, len(offences), offences)
        self.assertIn("--body", offences[0])

    def test_the_password_in_a_braced_expansion_is_reported(self) -> None:
        recipe = self.replaced("--env \"$env\"\nssh", "--env \"$env\"\necho ${pw}\nssh")
        self.assertEqual(1, len(password_on_command_lines(recipe)))

    def test_a_statement_passed_with_c_is_reported(self) -> None:
        recipe = self.replaced(
            "-d postgres'\\' <<SQL",
            "-d postgres -c \"CREATE DATABASE x\"'\\' <<SQL",
        )
        self.assertTrue(statements_not_over_standard_input(recipe))

    def test_a_here_document_fed_to_something_other_than_psql_is_reported(self) -> None:
        recipe = self.replaced(
            "ssh \"$host\" 'docker exec -i platform-postgres-1 sh -c '\\''psql -X -v ON_ERROR_STOP=1 -U \"$POSTGRES_USER\" -d postgres'\\' <<SQL",
            "cat > /tmp/provision.sql <<SQL",
        )
        offences = statements_not_over_standard_input(recipe)
        self.assertEqual(1, len(offences), offences)
        self.assertIn("not fed to psql", offences[0])

    def test_an_unquoted_identifier_is_reported(self) -> None:
        sql = standard_input_sql(self.replaced('CREATE DATABASE "$app" OWNER "$app"', "CREATE DATABASE $app OWNER $app"))
        self.assertEqual(2, len(unquoted_identifiers(sql)))

    def test_a_psql_variable_quoted_as_an_identifier_is_accepted(self) -> None:
        self.assertEqual([], unquoted_identifiers('CREATE ROLE :"app" LOGIN;'))

    def test_a_database_owned_by_another_role_is_reported(self) -> None:
        sql = standard_input_sql(self.replaced('OWNER "$app"', 'OWNER "postgres"'))
        self.assertEqual(1, len(database_ownership_offences(sql)))

    def test_a_database_created_with_no_owner_is_reported(self) -> None:
        sql = standard_input_sql(self.replaced(' OWNER "$app";', ";"))
        self.assertEqual(1, len(database_ownership_offences(sql)))

    def test_a_missing_revoke_is_reported_for_both_privileges(self) -> None:
        sql = standard_input_sql(self.replaced('REVOKE CONNECT, TEMPORARY ON DATABASE "$app" FROM PUBLIC;', ""))
        self.assertEqual(1, len(unrevoked_privilege(sql, "CONNECT")))
        self.assertEqual(1, len(unrevoked_privilege(sql, "TEMPORARY")))

    def test_a_revoke_of_connect_alone_leaves_temporary_reported(self) -> None:
        sql = standard_input_sql(self.replaced("REVOKE CONNECT, TEMPORARY", "REVOKE CONNECT"))
        self.assertEqual([], unrevoked_privilege(sql, "CONNECT"))
        self.assertEqual(1, len(unrevoked_privilege(sql, "TEMPORARY")))

    def test_a_revoke_from_a_named_role_rather_than_public_is_reported(self) -> None:
        sql = standard_input_sql(self.replaced("FROM PUBLIC", 'FROM "pgexporter"'))
        self.assertEqual(1, len(unrevoked_privilege(sql, "CONNECT")))

    def test_revoking_all_covers_both_privileges(self) -> None:
        sql = standard_input_sql(self.replaced("REVOKE CONNECT, TEMPORARY", "REVOKE ALL PRIVILEGES"))
        self.assertEqual([], unrevoked_privilege(sql, "CONNECT"))
        self.assertEqual([], unrevoked_privilege(sql, "TEMPORARY"))

    def test_a_revoke_in_a_sql_comment_does_not_count(self) -> None:
        sql = standard_input_sql(self.replaced("REVOKE CONNECT", "-- REVOKE CONNECT"))
        self.assertEqual(1, len(unrevoked_privilege(sql, "CONNECT")))

    def test_a_name_check_that_does_not_refuse_is_reported(self) -> None:
        recipe = self.replaced(" >&2; exit 1", " >&2")
        self.assertEqual(1, len(refusal_offences(recipe)))

    def test_a_refusal_after_the_secret_is_set_is_reported(self) -> None:
        document = CONFORMING_RECIPE_DOCUMENT.replace(
            "pw=$(openssl rand -hex 32)\nprintf '%s' \"$pw\" | gh secret set \"$secret\" --repo \"$repo\" --env \"$env\"\n",
            "",
        ).replace(
            "names=$(gh secret list",
            "pw=$(openssl rand -hex 32)\nprintf '%s' \"$pw\" | gh secret set \"$secret\" --repo \"$repo\" --env \"$env\"\nnames=$(gh secret list",
        )
        self.assertNotEqual(document, CONFORMING_RECIPE_DOCUMENT)
        self.assertEqual(1, len(refusal_offences(self.recipe(document))))

    def test_a_recipe_never_reading_the_secret_names_is_reported(self) -> None:
        recipe = self.replaced("gh secret list", "true")
        self.assertIn(
            "the Environment's secret names are never read (`gh secret list`)",
            refusal_offences(recipe),
        )

    def test_a_here_document_body_line_is_not_read_as_a_command(self) -> None:
        lines = self.recipe().splitlines()
        owner = heredoc_openers(lines)
        body = [line for index, line in enumerate(lines) if owner[index] is not None]
        self.assertIn('CREATE DATABASE "$app" OWNER "$app";', body)
        self.assertIn("SQL", body)
        self.assertNotIn(")", body)


# --------------------------------------------------------------------------
# The table division in the change's own record
# --------------------------------------------------------------------------

NON_DURABLE_TABLES = "procrastinate_"
DURABLE_TABLES = (
    "playbook_steps",
    "launch_journal_entries",
    "launch_clickup_tasks",
    "roles",
    "role_holders",
    "known_work",
    "products",
)

MISSING_DIVISION = "a paragraph dividing the application's tables"
MISSING_NON_DURABLE = "the job-queue tables stated as non-durable"
MISSING_UNCLASSIFIED = "that every table the division does not name is unclassified"


def change_record_directories(root: Path | None = None) -> list[Path]:
    """This change's directory, in the live layout or the archived one."""
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


def division_omissions(design_text: str) -> list[str]:
    paragraphs = [p for p in re.split(r"\n\s*\n", design_text) if NON_DURABLE_TABLES in p]
    if not paragraphs:
        return [MISSING_DIVISION]
    best: list[str] | None = None
    for paragraph in paragraphs:
        omissions: list[str] = []
        if "non-durable" not in paragraph:
            omissions.append(MISSING_NON_DURABLE)
        durable_stated = re.search(r"(?<!non-)\bdurable\b", paragraph) is not None
        for table in DURABLE_TABLES:
            if not durable_stated or f"`{table}`" not in paragraph:
                omissions.append(f"`{table}` stated as durable")
        if "unclassified" not in paragraph:
            omissions.append(MISSING_UNCLASSIFIED)
        if best is None or len(omissions) < len(best):
            best = omissions
    return best or []


class TestTheChangeRecordStatesTheTableDivision(unittest.TestCase):
    """SPECIFIED -- scenario "An application's data divides into durable and
    non-durable parts": THEN the change in this repository that records that
    database SHALL state which tables are non-durable and which are durable,
    AND a table the division does not name SHALL NOT be placed there until a
    change classifies it. The table names are DERIVED -- design.md decision 3
    states them; the delta deliberately states only the rule."""

    def test_the_change_record_exists_exactly_once(self) -> None:
        directories = change_record_directories()
        self.assertEqual(
            1,
            len(directories),
            f"expected this change's record once, live or archived; found "
            f"{[d.relative_to(ROOT).as_posix() for d in directories]}",
        )

    def test_its_design_states_the_division(self) -> None:
        directories = change_record_directories()
        self.assertTrue(directories, "this change's record was not found")
        for directory in directories:
            with self.subTest(record=directory.name):
                omissions = division_omissions(read_text(directory / "design.md"))
                self.assertEqual(
                    [],
                    omissions,
                    f"{directory.name}'s design.md does not state: " + "; ".join(omissions),
                )


CONFORMING_DIVISION = """\
### 3. Classify production's database table by table

The `procrastinate_*` tables are non-durable. The hand-curated tables are durable and SHALL NOT be placed in the shared instance: `playbook_steps`, `launch_journal_entries`, `launch_clickup_tasks`, `roles`, `role_holders`, `known_work`, `products`. **Every other table is unclassified**.

The delta states the rule and not the table names.
"""


class TestTheDivisionDetectorFires(unittest.TestCase):
    def test_a_conforming_division_yields_no_omission(self) -> None:
        self.assertEqual([], division_omissions(CONFORMING_DIVISION))

    def test_a_record_with_no_division_is_reported(self) -> None:
        self.assertEqual([MISSING_DIVISION], division_omissions("## Decisions\n\nNothing here.\n"))

    def test_a_division_naming_no_unclassified_remainder_is_reported(self) -> None:
        self.assertEqual(
            [MISSING_UNCLASSIFIED],
            division_omissions(CONFORMING_DIVISION.replace("**Every other table is unclassified**.", "")),
        )

    def test_a_durable_table_dropped_from_the_division_is_reported(self) -> None:
        self.assertEqual(
            ["`role_holders` stated as durable"],
            division_omissions(CONFORMING_DIVISION.replace(" `role_holders`,", "")),
        )

    def test_a_division_calling_every_table_non_durable_is_reported(self) -> None:
        omissions = division_omissions(
            CONFORMING_DIVISION.replace("tables are durable", "tables are non-durable too")
        )
        self.assertEqual(len(DURABLE_TABLES), len(omissions), omissions)

    def test_a_division_split_across_paragraphs_is_reported(self) -> None:
        """The division is one statement; the unnamed remainder must be
        classified where the named tables are."""
        split = CONFORMING_DIVISION.replace(" **Every other", "\n\n**Every other")
        self.assertEqual([MISSING_UNCLASSIFIED], division_omissions(split))

    def test_the_record_is_found_live_and_archived(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            changes = root / "openspec" / "changes"
            (changes / CHANGE_NAME).mkdir(parents=True)
            (changes / ARCHIVE_SEGMENT / ("2026-09-20-" + CHANGE_NAME)).mkdir(parents=True)
            (changes / ARCHIVE_SEGMENT / ("2026-09-20-other-" + "change")).mkdir(parents=True)
            self.assertEqual(
                [CHANGE_NAME, "2026-09-20-" + CHANGE_NAME],
                [d.name for d in change_record_directories(root)],
            )


if __name__ == "__main__":
    unittest.main()
