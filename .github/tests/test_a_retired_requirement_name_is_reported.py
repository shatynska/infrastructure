"""Derived tests for the check that reports a retired requirement name.

Derived from the delta specification of the OpenSpec change
`correct-the-documents-against-the-tree`, before any implementation of that
change existed. The path that delta sits at is not written here: a change's
artifacts move when it is archived, and this repository's citation convention is
to name the change and the artifact in prose instead.

That delta carries one `MODIFIED` requirement -- *Source Files Cite
Specifications by Path and Changes by Name*
(`openspec/specs/iac-repo-foundations/spec.md`) -- which gains the obligation
that a requirement named in a committed file outside `openspec/` SHALL be one a
specification under `openspec/specs/` currently holds, and that the obligation
SHALL be asserted by the executable suite gating every pull request. Five of its
scenarios state what that assertion does, and they are this file's whole
subject. Each class below names the scenario it traces to, and every assertion
is annotated SPECIFIED (it traces to a scenario or to SHALL text) or DERIVED (it
traces to that change's `design.md` or `tasks.md` rather than to a scenario).
See that change's `test-plan.md` for the scenario-to-test mapping, the baseline,
the interface this file assumes, the obsolete-test candidates and what is left
uncovered.

Why this is a module of its own
-------------------------------
`.github/tests` is both this repository's check surface and its test surface,
and the two are separated here. The change's own module -- named by
`CHECK_MODULE` below -- is the *check*: it sweeps the committed tree and fails
the pull request. This module is the *test of that check's reader*, written by
an author other than whoever implements it, and it may only add. It edits,
deletes and disables nothing. That module's own discriminating class is
additional to these rather than a substitute: it falsifies its reader, these
trace to the scenarios.

Until that module exists every assertion here fails naming it, which is the
absent-target state rather than a wrong value: nothing below has yet been
established about the check's behaviour.

The interface this file assumes the implementation will expose
--------------------------------------------------------------
These are ASSUMPTIONS taken before the implementation, fetched lazily by
`check_symbol()` so that the failure names the absent target rather than
erroring at import -- and so that the suite-wide import audit in
`test_ci_configuration.py` does not read an import of a module the directory
does not yet contain.

  retirements(files: Mapping[str, str]) -> dict[str, str | None]
      Every requirement name an archived delta specification retired -- stated
      as `### Requirement: <name>` under a `## REMOVED Requirements` heading in
      a file under the archived-changes prefix -- less every name a
      specification under `openspec/specs/` currently holds, mapped to what the
      requirement is called now. The value is the replacement the `**Migration**`
      or `**Reason**` line of that `REMOVED` block names in emphasis, followed
      through the chain to the first name a specification currently holds, and
      `None` where the chain reaches no live name or the block records none.

  retired_name_offences(files: Mapping[str, str], names: Sequence[str],
                        live: Sequence[str]) -> list[str]
      Every swept file still naming a retired requirement, as
      `<path>:<line>: <name>`, one entry per occurrence, the line being where
      the name starts. Matched over a flattened rendering of each file, so a
      name wrapped across a comment's line break is one name rather than two
      fragments. An occurrence that is the opening of a longer name in `live` is
      not reported. Called by keyword here: `names` and `live` are supplied per
      test rather than taken from the committed archive, which is what lets a
      case be exercised against a fixture instead of against today's tree.

  idle_exemptions(files: Mapping[str, str], names: Sequence[str],
                  paths: Sequence[str]) -> list[str]
      One message per whole-path exemption in `paths` whose file no longer
      contains any of `names`, naming that exemption.

Each takes its file set as an argument, which is the shape the change's
`tasks.md` 1.1 requires of the module ("a pure offence-finder plus a thin
reader") and is not invented here.

Why the fixtures name requirements this repository does not have
---------------------------------------------------------------
Every name below -- retired, live, chained and prefixed -- is invented, and
structurally identical to the case the change's `design.md` records rather than
equal to it. Two reasons, and the first is what decides it. The check this file
tests reads `.github/tests/` and exempts exactly one module, which is not this
one: a fixture naming a genuinely retired requirement would make this file an
offence against the check it asserts, and would have to be answered with an
exemption that decision 5 of that design spends a page arguing against. Second,
a fixture built from today's archive would change meaning the next time a
requirement is renamed, while what these scenarios state does not.

What no assertion here establishes
----------------------------------
Nothing about the committed tree. Not that any file has been swept, not that the
derived retired set over the real archive is what the change measured, and not
that the check is wired into the required status check. Those are the
implementing module's own, over `tracked_files()`, and this file deliberately
reads no file on disk: every corpus below is a mapping it supplies. A green run
here says the reader behaves as the scenarios state when handed material built
to falsify it -- which is what makes that module's green sweep mean anything,
and is weaker than it looks on its own.

The failure message the reader composes is also not read here. The scenario's
AND clause is asserted at the level of the resolved replacement, through
`retirements()`; that the reader's message carries it is the implementing
module's to assert, per that change's `tasks.md` 1.5.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_a_retired_requirement_name_is_reported\\
.TestANameWrappedAcrossACommentsLineBreakIsRead\\
.test_a_name_split_across_two_comment_lines_is_reported

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling imports resolve.
"""

from __future__ import annotations

import unittest
from typing import Mapping, Sequence

from test_ci_configuration import ARCHIVE_SEGMENT, CHANGE_PATH_PREFIX

# --------------------------------------------------------------------------
# The module under test, fetched lazily.
# --------------------------------------------------------------------------

CHECK_MODULE = "test_the_retired_requirement_names_are_gone"


def check_symbol(name: str):
    """Fetch a symbol the implementation must expose from `CHECK_MODULE`.

    Fails -- rather than errors -- naming the absent target, so a run before the
    implementation exists reports "the target does not exist yet" in the words
    of the thing that is missing. Imported through `__import__` on a string
    rather than by an `import` statement, for two reasons: the module does not
    exist yet, and `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource`
    in `test_ci_configuration.py` admits a sibling import only where the
    directory already holds that sibling, so a statement here would turn that
    assertion red over a file it has no quarrel with.
    """
    try:
        module = __import__(CHECK_MODULE)
    except ImportError:
        raise AssertionError(
            f"`{CHECK_MODULE}` does not exist. The change "
            "`correct-the-documents-against-the-tree` adds it as the sweep for "
            "retired requirement names (its tasks.md 1.1); until it does, this "
            "assertion has nothing to exercise. This is the absent-target failure, "
            "not a wrong value: nothing has been established about the check."
        ) from None
    try:
        return getattr(module, name)
    except AttributeError:
        raise AssertionError(
            f"`{CHECK_MODULE}` exposes no `{name}`. See the interface this file "
            "assumes, in its module docstring and in that change's test-plan.md -- "
            "the implementation is written to it rather than around it."
        ) from None


def offences(files: Mapping[str, str], names: Sequence[str], live: Sequence[str]) -> list[str]:
    """`retired_name_offences` over a supplied corpus."""
    return check_symbol("retired_name_offences")(files, names=names, live=live)


def retirements(files: Mapping[str, str]) -> dict:
    """`retirements` over a supplied corpus."""
    return check_symbol("retirements")(files)


def idle(files: Mapping[str, str], names: Sequence[str], paths: Sequence[str]) -> list[str]:
    """`idle_exemptions` over a supplied corpus."""
    return check_symbol("idle_exemptions")(files, names=names, paths=paths)


# --------------------------------------------------------------------------
# The fixture requirements
#
# Invented, for the reason the module docstring gives. Structurally each is the
# case the change's design.md records: one plain rename, one two-step chain
# whose first recorded replacement is itself retired, and one retired name that
# is a prefix of a live one.
# --------------------------------------------------------------------------

ROLLOUT_HEAD = "Each Region Declares Its Own"
ROLLOUT_TAIL = "Rollout Schedule"
RETIRED_ROLLOUT = f"{ROLLOUT_HEAD} {ROLLOUT_TAIL}"
LIVE_ROLLOUT = "Each Cell Declares Its Own Rollout Schedule"

RETIRED_LEDGER_FIRST = "Dedicated Ledger Account for the First Tenant"
RETIRED_LEDGER_SECOND = "Each Tenant Has a Dedicated Ledger Account"
LIVE_LEDGER = "Each Stack Has a Dedicated Ledger Account"

RETIRED_PREFIX = "Widget Configuration Is Verified in Continuous Delivery"
LIVE_LONGER = f"{RETIRED_PREFIX} and Gates the Merge"

UNRELATED_LIVE = "The Rollout Report Names Its Own Window"

# --------------------------------------------------------------------------
# Fixture paths
#
# The two change-record paths are ASSEMBLED rather than written as literals, for
# the same reason the sibling sweep assembles its own: this is a committed file
# outside `openspec/`, so a literal naming a change's own directory would be
# reported by `TestNoCommittedFileOutsideOpenSpecCarriesAPreArchiveCitation`.
# --------------------------------------------------------------------------

ARCHIVED_SPEC = (
    CHANGE_PATH_PREFIX
    + ARCHIVE_SEGMENT
    + "/2026-01-04-rename-the-rollout-unit/specs/example-capability/spec.md"
)
SECOND_ARCHIVED_SPEC = (
    CHANGE_PATH_PREFIX
    + ARCHIVE_SEGMENT
    + "/2026-02-11-rename-the-ledger-owner/specs/example-capability/spec.md"
)
IN_FLIGHT_SPEC = (
    CHANGE_PATH_PREFIX + "a-change-still-in-flight" + "/specs/example-capability/spec.md"
)
LIVE_SPEC = "openspec/specs/example-capability/spec.md"

RUNBOOK = "docs/runbook.md"
EXEMPT_FIXTURE_PATH = "docs/change-queue.md"

# The suite reads itself, exempting one module. Written as literals because
# which module is exempt is the whole of the fifth scenario.
SWEPT_SUITE_MODULE = ".github/tests/test_environment_agnostic_pipeline.py"
CHECK_MODULE_PATH = f".github/tests/{CHECK_MODULE}.py"
THIS_MODULE_PATH = ".github/tests/test_a_retired_requirement_name_is_reported.py"


def removed_delta(name: str, migration: str | None = None, label: str = "Migration") -> str:
    """An archived delta specification retiring one requirement.

    `migration=None` writes a `REMOVED` block that records no replacement at
    all, which is one of the two cases the scenario's AND clause makes the
    report silent about.
    """
    block = f"## REMOVED Requirements\n\n### Requirement: {name}\n\n"
    if migration is None:
        return block + "**Reason**: the obligation was dropped and nothing took it up.\n"
    return block + f"**{label}**: renamed to *{migration}*, which says the same thing.\n"


def added_delta(name: str) -> str:
    """An archived delta specification introducing one requirement."""
    return (
        f"## ADDED Requirements\n\n### Requirement: {name}\n\n"
        "The system SHALL do what this name says.\n"
    )


def specification(*names: str) -> str:
    """A specification currently holding the named requirements."""
    return "".join(
        f"### Requirement: {name}\n\nThe system SHALL do what this name says.\n\n"
        for name in names
    )


# --------------------------------------------------------------------------
# iac-repo-foundations / Source Files Cite Specifications by Path and Changes
# by Name -- scenario "A pull request naming a retired requirement is rejected"
# --------------------------------------------------------------------------


class TestAPullRequestNamingARetiredRequirementIsRejected(unittest.TestCase):
    """SPECIFIED -- scenario "A pull request naming a retired requirement is
    rejected": "WHEN a pull request leaves, in a committed file outside
    `openspec/` that no exemption names, a requirement name that an archived
    delta specification retired and that no specification under
    `openspec/specs/` currently holds -- THEN the required status check SHALL
    fail on that pull request, naming the file, the line and the retired name".

    The failure of the status check is the failure of the assertion the
    implementing module writes over the committed tree. What is exercised here
    is the offence it reports: that there is one, and that it names the file,
    the line and the name.
    """

    def report(self, files: Mapping[str, str]) -> list[str]:
        return offences(files, names=(RETIRED_ROLLOUT,), live=(LIVE_ROLLOUT,))

    def test_a_swept_file_naming_a_retired_requirement_is_reported(self) -> None:
        """SPECIFIED -- the file and the name of the report."""
        self.assertEqual(
            [f"{RUNBOOK}:1: {RETIRED_ROLLOUT}"],
            self.report({RUNBOOK: f"see *{RETIRED_ROLLOUT}* for what the host owes\n"}),
        )

    def test_the_line_reported_is_the_line_the_name_is_on(self) -> None:
        """SPECIFIED -- "naming the file, the line and the retired name". A
        message pointing at the wrong line sends the reader to the wrong
        paragraph of a runbook, which is where most of these names are."""
        corpus = {RUNBOOK: f"one\ntwo\nthree, and {RETIRED_ROLLOUT} beside it\nfour\n"}
        self.assertEqual([f"{RUNBOOK}:3: {RETIRED_ROLLOUT}"], self.report(corpus))

    def test_every_occurrence_is_reported_rather_than_the_first(self) -> None:
        """DERIVED -- no scenario states it; the change's tasks.md 2.6 to 2.11
        work file by file from this finder's own output, and a file naming a
        requirement in a banner, in a docstring and in the prose beside both
        would otherwise come back three times."""
        corpus = {
            RUNBOOK: (
                "the rule\n"
                f"is stated by {RETIRED_ROLLOUT}\n"
                "\n"
                f"and again as *{RETIRED_ROLLOUT}* in the table\n"
            )
        }
        self.assertEqual(
            [f"{RUNBOOK}:2: {RETIRED_ROLLOUT}", f"{RUNBOOK}:4: {RETIRED_ROLLOUT}"],
            self.report(corpus),
        )

    def test_a_corpus_naming_no_retired_requirement_reports_nothing(self) -> None:
        """DERIVED -- no scenario states it. Without it, a finder reporting
        every line would satisfy the assertions above while making the committed
        sweep unfailable in the other direction."""
        self.assertEqual(
            [],
            self.report(
                {
                    "README.md": f"the {LIVE_ROLLOUT} requirement governs this\n",
                    RUNBOOK: "nothing here names a requirement at all\n",
                }
            ),
        )

    def test_a_file_inside_openspec_is_not_reported(self) -> None:
        """SPECIFIED -- the obligation is over "a committed file outside
        `openspec/`". A change record names what it renames FROM, and a
        specification under `openspec/specs/` is where the live name lives."""
        for path in (ARCHIVED_SPEC, IN_FLIGHT_SPEC, LIVE_SPEC):
            with self.subTest(path=path):
                self.assertEqual([], self.report({path: f"{RETIRED_ROLLOUT}\n"}))

    def test_a_path_merely_resembling_an_exempt_one_is_still_swept(self) -> None:
        """DERIVED -- no scenario states it. The exemption is a prefix, so a
        path that merely begins or ends the same way must not inherit it."""
        for path in ("openspec-notes.md", "docs/openspec/changes.md"):
            with self.subTest(path=path):
                self.assertEqual(
                    [f"{path}:1: {RETIRED_ROLLOUT}"],
                    self.report({path: f"{RETIRED_ROLLOUT}\n"}),
                )


class TestTheReportNamesWhatTheRequirementIsCalledNow(unittest.TestCase):
    """SPECIFIED -- the AND clause of that same scenario: "the report SHALL name
    what the requirement is called now, where a specification holds a name the
    archive records as its replacement -- or, where that recorded replacement is
    itself retired, the first name in the chain the archive records that a
    specification currently holds".

    Asserted over the derived mapping rather than over the reader's message: the
    reader is the implementing module's and reads the committed tree, while what
    the clause turns on -- which name is offered, and whether one is offered at
    all -- is decided here.
    """

    def test_a_recorded_replacement_a_specification_holds_is_offered(self) -> None:
        """SPECIFIED -- "where a specification holds a name the archive records
        as its replacement". Both labels the change's tasks.md 1.5 names are
        exercised: a `REMOVED` block records its replacement under either."""
        for label in ("Migration", "Reason"):
            with self.subTest(label=label):
                files = {
                    ARCHIVED_SPEC: removed_delta(
                        RETIRED_ROLLOUT, migration=LIVE_ROLLOUT, label=label
                    ),
                    LIVE_SPEC: specification(LIVE_ROLLOUT),
                }
                self.assertEqual({RETIRED_ROLLOUT: LIVE_ROLLOUT}, retirements(files))

    def test_a_chained_replacement_resolves_to_the_first_live_name(self) -> None:
        """SPECIFIED -- "where that recorded replacement is itself retired, the
        first name in the chain the archive records that a specification
        currently holds". Reporting the recorded replacement instead would hand
        the reader a name this same check forbids."""
        files = {
            ARCHIVED_SPEC: removed_delta(RETIRED_LEDGER_FIRST, migration=RETIRED_LEDGER_SECOND),
            SECOND_ARCHIVED_SPEC: removed_delta(RETIRED_LEDGER_SECOND, migration=LIVE_LEDGER),
            LIVE_SPEC: specification(LIVE_LEDGER),
        }
        self.assertEqual(
            {
                RETIRED_LEDGER_FIRST: LIVE_LEDGER,
                RETIRED_LEDGER_SECOND: LIVE_LEDGER,
            },
            retirements(files),
        )

    def test_a_chain_reaching_no_live_name_offers_none(self) -> None:
        """SPECIFIED -- the clause is conditional on a specification holding the
        name. Where the chain ends in one nothing holds, the report says the
        name is retired without saying what to write instead."""
        files = {
            ARCHIVED_SPEC: removed_delta(RETIRED_LEDGER_FIRST, migration=RETIRED_LEDGER_SECOND),
            SECOND_ARCHIVED_SPEC: removed_delta(RETIRED_LEDGER_SECOND, migration=LIVE_LEDGER),
            LIVE_SPEC: specification(UNRELATED_LIVE),
        }
        self.assertEqual(
            {RETIRED_LEDGER_FIRST: None, RETIRED_LEDGER_SECOND: None},
            retirements(files),
        )

    def test_a_removed_block_recording_no_replacement_offers_none(self) -> None:
        """SPECIFIED -- same clause, the other way it goes unsatisfied: the
        block records no replacement at all."""
        files = {
            ARCHIVED_SPEC: removed_delta(RETIRED_ROLLOUT),
            LIVE_SPEC: specification(UNRELATED_LIVE),
        }
        self.assertEqual({RETIRED_ROLLOUT: None}, retirements(files))

    def test_a_name_a_later_change_reintroduced_is_not_retired(self) -> None:
        """SPECIFIED -- the scenario's WHEN clause is a name "that no
        specification under `openspec/specs/` currently holds". A name removed
        by one change and reintroduced by a later one is live, and a check
        reporting it would forbid the correct citation."""
        files = {
            ARCHIVED_SPEC: removed_delta(RETIRED_ROLLOUT, migration=LIVE_ROLLOUT),
            LIVE_SPEC: specification(RETIRED_ROLLOUT, LIVE_ROLLOUT),
        }
        self.assertEqual({}, retirements(files))

    def test_a_name_an_archived_delta_added_rather_than_removed_is_not_retired(self) -> None:
        """DERIVED -- design decision 1, which derives the set from
        `### Requirement:` under a `## REMOVED Requirements` heading. A name an
        archived change ADDED and a later change renamed is retired by that
        later change's `REMOVED` block, not by this one -- and a reader keying
        on the requirement heading alone would retire every name the archive
        ever stated."""
        files = {
            ARCHIVED_SPEC: added_delta(RETIRED_ROLLOUT),
            LIVE_SPEC: specification(UNRELATED_LIVE),
        }
        self.assertEqual({}, retirements(files))

    def test_a_change_still_in_flight_retires_nothing(self) -> None:
        """DERIVED -- design decision 1 reads the ARCHIVE. A change proposing a
        removal has not made it: until it archives the name is still held, and
        retiring it early would report every correct citation in the tree while
        the proposal is under review."""
        files = {
            IN_FLIGHT_SPEC: removed_delta(RETIRED_ROLLOUT, migration=LIVE_ROLLOUT),
            LIVE_SPEC: specification(RETIRED_ROLLOUT),
        }
        self.assertEqual({}, retirements(files))

    def test_a_corpus_holding_no_archived_removal_derives_nothing(self) -> None:
        """DERIVED -- no scenario states it. Without it, a derivation that
        returned a fixed list of names -- the hard-coded set design decision 1
        rejects -- would satisfy every assertion above."""
        self.assertEqual({}, retirements({}))
        self.assertEqual({}, retirements({LIVE_SPEC: specification(LIVE_ROLLOUT)}))


# --------------------------------------------------------------------------
# Scenario "A retired name surviving inside a longer live name is not reported"
# --------------------------------------------------------------------------


class TestARetiredNameSurvivingInsideALongerLiveNameIsNotReported(unittest.TestCase):
    """SPECIFIED -- scenario "A retired name surviving inside a longer live name
    is not reported": "WHEN a committed file names a requirement that a
    specification currently holds, and a retired name is a prefix of it -- THEN
    the assertion SHALL NOT report that file, because what it names is the live
    requirement".

    The requirement states the same obligation directly: "A retired name that is
    a prefix of a name a specification currently holds SHALL NOT be reported
    where the longer name is what the file says."
    """

    def report(self, files: Mapping[str, str]) -> list[str]:
        return offences(files, names=(RETIRED_PREFIX,), live=(LIVE_LONGER,))

    def test_the_fixture_pair_really_is_a_prefix(self) -> None:
        """DERIVED -- a premise of every assertion in this class. Were the two
        fixture names to stop standing in that relation, the class would go on
        passing while exercising nothing."""
        self.assertTrue(LIVE_LONGER.startswith(RETIRED_PREFIX))
        self.assertNotEqual(LIVE_LONGER, RETIRED_PREFIX)

    def test_a_citation_of_the_longer_live_name_is_not_reported(self) -> None:
        """SPECIFIED -- the scenario itself."""
        self.assertEqual(
            [], self.report({RUNBOOK: f"gated by *{LIVE_LONGER}* on every pull request\n"})
        )

    def test_the_longer_live_name_wrapped_across_lines_is_not_reported(self) -> None:
        """DERIVED -- this change's tasks.md 1.4: the suppression runs over the
        FLATTENED text, not per line. Almost every citation of the live name
        this case exists for wraps, so a per-line suppression would report every
        correct one of them -- the check's largest possible false-positive
        class, over its own subject."""
        corpus = {
            ".github/workflows/pr-validation.yml": (
                f"# {RETIRED_PREFIX}\n#   and Gates the Merge -- the required check\n"
            )
        }
        self.assertEqual([], self.report(corpus))

    def test_the_retired_name_standing_alone_is_still_reported(self) -> None:
        """SPECIFIED -- the scenario suppresses the report "because what it names
        is the live requirement", which the bare name is not. Without this the
        suppression could be blanket, and the prefix pair the design names would
        be unreportable anywhere in the tree."""
        self.assertEqual(
            [f"{RUNBOOK}:1: {RETIRED_PREFIX}"],
            self.report({RUNBOOK: f"gated by *{RETIRED_PREFIX}* on every pull request\n"}),
        )

    def test_a_bare_retired_name_beside_a_live_citation_is_reported(self) -> None:
        """DERIVED -- no scenario states it. The suppression is per occurrence
        and not per file: a document citing the live name correctly in one
        paragraph and the retired one in the next is the ordinary shape of a
        half-finished sweep, and suppressing the file would hide exactly the
        residue this check exists to find."""
        corpus = {
            RUNBOOK: (
                f"gated by *{LIVE_LONGER}* on every pull request\n"
                "\n"
                f"and, further down, *{RETIRED_PREFIX}* alone\n"
            )
        }
        self.assertEqual([f"{RUNBOOK}:3: {RETIRED_PREFIX}"], self.report(corpus))


# --------------------------------------------------------------------------
# Scenario "A name wrapped across a comment's line break is read"
# --------------------------------------------------------------------------


class TestANameWrappedAcrossACommentsLineBreakIsRead(unittest.TestCase):
    """SPECIFIED -- scenario "A name wrapped across a comment's line break is
    read": "WHEN a committed file states a requirement name across two lines of
    a comment block, each line carrying the comment marker and its indentation
    -- THEN the assertion SHALL read it as the one name it is, rather than as
    two fragments neither of which matches".

    The requirement gives the reason: this repository states a requirement's
    name in at least four renderings, "emphasised, quoted, bare and wrapped
    across a comment's line break", and the change's design.md measures the
    wrapped one as the majority of its interesting surface.
    """

    def report(self, files: Mapping[str, str]) -> list[str]:
        return offences(files, names=(RETIRED_ROLLOUT,), live=(LIVE_ROLLOUT,))

    def test_the_fixture_fragments_are_the_name_split(self) -> None:
        """DERIVED -- a premise of every assertion in this class, as above: were
        the two fragments to stop joining into the name, each wrapped fixture
        below would go on passing over material that matches nothing."""
        self.assertEqual(RETIRED_ROLLOUT, f"{ROLLOUT_HEAD} {ROLLOUT_TAIL}")

    def test_a_name_split_across_two_comment_lines_is_reported(self) -> None:
        """SPECIFIED -- the scenario itself, in the rendering the change's
        tasks.md 2.1 and 2.2 found in three workflow and Terraform files."""
        corpus = {
            ".github/workflows/drift.yml": (
                f"# {ROLLOUT_HEAD}\n#   {ROLLOUT_TAIL} -- one job per stack\n"
            )
        }
        self.assertEqual(
            [f".github/workflows/drift.yml:1: {RETIRED_ROLLOUT}"], self.report(corpus)
        )

    def test_the_line_reported_is_the_line_the_name_starts_on(self) -> None:
        """SPECIFIED -- "naming the file, the line and the retired name", read
        together with this scenario: a wrapped name has two lines and the report
        names one. Design decision 2 keeps an offset-to-line map for it."""
        corpus = {
            "terraform/stacks/main-staging/versions.tf": (
                "terraform {\n"
                "  # the project this stack provisions into, per\n"
                f"  # {ROLLOUT_HEAD}\n"
                f"  #   {ROLLOUT_TAIL}\n"
                "}\n"
            )
        }
        self.assertEqual(
            [f"terraform/stacks/main-staging/versions.tf:3: {RETIRED_ROLLOUT}"],
            self.report(corpus),
        )

    def test_each_rendering_the_tree_wraps_a_name_in_is_read(self) -> None:
        """SPECIFIED -- "each line carrying the comment marker and its
        indentation". Both renderings the change measures are exercised: the
        hash comment of a workflow, an Ansible configuration file and a
        Terraform file, and the bare indentation of a Python docstring, which
        carries no marker at all and is where forty of the forty-seven measured
        occurrences sit."""
        renderings = {
            "hash comment": f"# {ROLLOUT_HEAD}\n#   {ROLLOUT_TAIL}\n",
            "python docstring": (
                f'    """MODIFIED requirement: {ROLLOUT_HEAD}\n'
                f'    {ROLLOUT_TAIL} -- scenario "a stack declares its own".\n'
                '    """\n'
            ),
            "markdown prose": f"as required by {ROLLOUT_HEAD}\n{ROLLOUT_TAIL} in the tree\n",
        }
        for rendering, text in renderings.items():
            with self.subTest(rendering=rendering):
                self.assertEqual(
                    [f"{RUNBOOK}:1: {RETIRED_ROLLOUT}"], self.report({RUNBOOK: text})
                )

    def test_fragments_separated_by_other_text_are_not_joined_into_a_name(self) -> None:
        """DERIVED -- no scenario states it. Flattening joins lines, so without
        this a reader that discarded everything between the fragments would
        satisfy every assertion above while reporting a name no file states --
        and the report would name a line the reader cannot find it on."""
        corpus = {
            RUNBOOK: f"# {ROLLOUT_HEAD}\n# ---\n# {ROLLOUT_TAIL}\n",
        }
        self.assertEqual([], self.report(corpus))


# --------------------------------------------------------------------------
# Scenario "An exemption that no longer excuses anything fails the check"
# --------------------------------------------------------------------------


class TestAnExemptionThatNoLongerExcusesAnythingFailsTheCheck(unittest.TestCase):
    """SPECIFIED -- scenario "An exemption that no longer excuses anything fails
    the check": "WHEN a file exempted from this assertion no longer contains any
    retired requirement name -- THEN the assertion SHALL fail, naming that
    exemption, so that it is deleted in the change that swept the file rather
    than left standing over a file it no longer describes".

    The requirement states the same obligation: a file "SHALL be exempted by its
    own path rather than by a directory prefix, with the reason stated where the
    exemption is declared, and the assertion SHALL fail where an exemption names
    a file that no longer contains a retired name". The change's design decision
    6 is what depends on it: `docs/change-queue.md` is exempt for one queue
    entry, and the archive commit that deletes the entry is what must delete the
    exemption.
    """

    def idle_over(self, files: Mapping[str, str]) -> list[str]:
        return idle(files, names=(RETIRED_ROLLOUT,), paths=(EXEMPT_FIXTURE_PATH,))

    def test_an_exemption_over_a_file_naming_no_retired_requirement_is_reported(self) -> None:
        """SPECIFIED -- the scenario itself, and "naming that exemption"."""
        reported = self.idle_over(
            {EXEMPT_FIXTURE_PATH: "entry 74 was deleted when its change archived\n"}
        )
        self.assertEqual(1, len(reported), reported)
        self.assertIn(EXEMPT_FIXTURE_PATH, reported[0])

    def test_an_exemption_over_a_file_still_naming_one_is_not_reported(self) -> None:
        """SPECIFIED -- the scenario turns on the file NO LONGER containing one.
        Without this the expiry check could report every exemption, which would
        make the exemption mechanism unusable for the case the requirement
        admits: a file whose subject is the retirement itself."""
        self.assertEqual(
            [],
            self.idle_over(
                {EXEMPT_FIXTURE_PATH: f"entry 74 renames *{RETIRED_ROLLOUT}* away\n"}
            ),
        )

    def test_an_exemption_over_a_file_naming_one_across_a_line_break_is_not_reported(
        self,
    ) -> None:
        """DERIVED -- the conjunction of this scenario with "A name wrapped
        across a comment's line break is read": the expiry check asks whether
        the file still CONTAINS a retired name, and a per-line read of a wrapped
        one answers no. That answer retires an exemption the file still needs,
        and the repair -- deleting it -- turns the sweep red on the file the
        exemption was written for."""
        self.assertEqual(
            [],
            self.idle_over(
                {EXEMPT_FIXTURE_PATH: f"- entry 74 renames {ROLLOUT_HEAD}\n  {ROLLOUT_TAIL}\n"}
            ),
        )


# --------------------------------------------------------------------------
# Scenario "The test suite's own citations are read"
# --------------------------------------------------------------------------


class TestTheTestSuitesOwnCitationsAreRead(unittest.TestCase):
    """SPECIFIED -- scenario "The test suite's own citations are read": "WHEN a
    module of the executable test suite states in prose the requirement one of
    its assertions traces to, and that requirement has since been renamed --
    THEN the assertion SHALL report it, the suite being exempted only for the
    one module that must name a retired requirement in order to assert its
    absence".

    The requirement gives the reason: this suite "states which requirement each
    of its assertions traces to, in prose beside the assertion, and is therefore
    the densest surface in the repository on which this defect occurs; a
    directory-wide exemption over it would leave the majority of the defect
    unread while reporting a clean sweep". The change's design decision 5
    measures that majority at forty of forty-seven occurrences.
    """

    def report(self, files: Mapping[str, str]) -> list[str]:
        return offences(files, names=(RETIRED_ROLLOUT,), live=(LIVE_ROLLOUT,))

    def test_a_suite_modules_own_citation_is_reported(self) -> None:
        """SPECIFIED -- the scenario itself, in the rendering the suite actually
        uses: a docstring naming the requirement an assertion traces to, wrapped
        across the lines of that docstring."""
        corpus = {
            SWEPT_SUITE_MODULE: (
                "class TestSomething(unittest.TestCase):\n"
                f'    """SPECIFIED -- {ROLLOUT_HEAD}\n'
                f'    {ROLLOUT_TAIL}, and the scenario beneath it."""\n'
            )
        }
        self.assertEqual([f"{SWEPT_SUITE_MODULE}:2: {RETIRED_ROLLOUT}"], self.report(corpus))

    def test_the_one_module_that_must_name_them_is_exempt(self) -> None:
        """SPECIFIED -- "exempted only for the one module that must name a
        retired requirement in order to assert its absence". That module is the
        sweep itself: a check must be able to name what it forbids."""
        self.assertEqual(
            [],
            self.report({CHECK_MODULE_PATH: f"RETIRED = ({RETIRED_ROLLOUT!r},)\n"}),
        )

    def test_this_module_is_swept_like_any_other_file(self) -> None:
        """SPECIFIED -- the same clause, from the other side: ONLY that one
        module is exempt, so the exemption is a path and not a rule about test
        modules, about this change's own files, or about fixtures. This file
        names no retired requirement -- every name in it is invented, for
        exactly this reason -- so being swept costs it nothing and being exempt
        would cost the check its stated boundary."""
        self.assertEqual(
            [f"{THIS_MODULE_PATH}:1: {RETIRED_ROLLOUT}"],
            self.report({THIS_MODULE_PATH: f"{RETIRED_ROLLOUT}\n"}),
        )

    def test_a_sibling_suite_module_is_not_exempt_by_the_directory(self) -> None:
        """SPECIFIED -- the scenario's "the suite being exempted only for the one
        module". The sibling sweep for external-service names exempts
        `.github/tests/` wholesale and design decision 5 declines to copy it;
        this is what holds that decision after the sweep is finished, when a
        directory-wide exemption would show up as a clean run."""
        for path in (
            ".github/tests/test_host_converge_workflow.py",
            ".github/tests/test_the_external_service_names_are_retired.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    [f"{path}:1: {RETIRED_ROLLOUT}"],
                    self.report({path: f"{RETIRED_ROLLOUT}\n"}),
                )


if __name__ == "__main__":
    unittest.main()
