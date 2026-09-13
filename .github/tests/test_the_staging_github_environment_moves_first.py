"""Static-assertion tests for the staging stack's GitHub Environment moving
onto the stack axis, which is the canary half of a two-pull-request change.

Derived from the delta specifications of the OpenSpec change
`rename-the-github-environments`, before any implementation of that change
existed. The path those deltas sit at is not written here: a change's artifacts
move when it is archived, and this repository's citation convention is to name
the change and the artifact in prose instead.

Every assertion below is annotated SPECIFIED (it traces to SHALL text or to a
scenario in a delta spec) or DERIVED (it traces to that change's `proposal.md`,
`design.md` or `tasks.md`, or to `docs/naming-conventions.md`, rather than to a
scenario). See that change's `test-plan.md` for the scenario-to-test mapping,
the baseline, the scenarios deliberately left uncovered, the obsolete-test
candidates, and the project questions this file had to take an assumption on.

Why the staging half is a file of its own
-----------------------------------------
That change merges in TWO pull requests off one branch: staging's flip first,
production's second, and both must be green before either merges. A single
module holding both halves could not be committed without turning one of them
red -- an assertion about production's new Environment name, committed in the
staging pull request, fails that pull request's required check, and the remedy
a red canary invites is deleting or weakening the assertion. So the split is a
split of FILES rather than a split of commits within one file, which makes it
mechanical: this module is added in the staging pull request, and
`test_the_github_environments_are_named_for_their_stacks.py` -- which imports
the readers below rather than restating them -- is added in the production one.

That change's tasks.md 2.2 requires this to be stated, and states it the same
way.

Why this is a twenty-first file in the suite rather than a section of an
existing one
-----------------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. Nothing here edits, deletes or disables an
existing test. Three literals already in this suite name the Environments this
change moves -- `PROD_GITHUB_ENVIRONMENT` in
`test_environment_agnostic_pipeline.py`, `SECOND_ENVIRONMENT_GITHUB_ENVIRONMENT`
in `test_a_second_environment.py` and `GATED_DEPLOY_ENVIRONMENT` in
`test_ci_configuration.py` -- and moving each is the implementing author's task,
recorded in `test-plan.md` rather than performed here.

What this reads that those three do not: each of them compares a committed
declaration against a constant in its own module, so the pair moves together and
a green result establishes that one value was typed twice. This module asserts
the RELATION the naming scheme states -- that a stack's GitHub Environment is
named for the stack -- which no constant can satisfy by being edited alongside
the file it is compared with.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable by name:
    python3 -m unittest \\
        test_the_staging_github_environment_moves_first\\
.TestTheStagingStackDeclaresTheEnvironmentNamedForIt\\
.test_the_staging_stack_declares_the_environment_named_for_it

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling imports below resolve.

What no assertion here establishes
----------------------------------
Nothing whatever about GitHub. Not that a `main-staging` Environment exists, not
that it holds the six secrets `staging` holds, not that it carries no protection
rules, and not that the old `staging` Environment was deleted. Each is reachable
only by a network call this suite is forbidden from making, and that prohibition
is itself asserted by
`TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in
`test_ci_configuration.py`, which reads this module among the others. The
change's own task list makes every one of them an operator observation.

A green run here is therefore weaker than it looks, and deliberately so: it is
evidence that the committed declaration was moved, never that the Environment it
now names is there to attach to. That asymmetry is the change's central risk
rather than a footnote -- GitHub CREATES an Environment a job names, with no
protection rules, so a declaration pointing at an Environment nobody built runs
ungated rather than failing.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Mapping

from test_environment_agnostic_pipeline import environment_declarations

# --------------------------------------------------------------------------
# What the staging stack is expected to declare
#
# DERIVED, and the derivation is worth stating because it is NOT a scenario. No
# scenario in any of this change's three delta specs names `main-staging` as a
# GitHub Environment: the `iac-cicd-pipeline` scenarios that mention the staging
# stack name its DIRECTORY (`terraform/stacks/main-staging/`), which this change
# does not move, and every scenario that names an Environment names
# `main-production`. The value below comes from that change's proposal.md
# ("`main-staging` is created"), its tasks.md 4.1, and `docs/naming-conventions.md`,
# whose stack table gives the GitHub Environment the stack's own name.
#
# Asserted here rather than left to review because the field is read by a
# workflow that resolves it silently: a job attaches to whatever name it is
# given, and a wrong one is an ungated apply rather than an error.
# --------------------------------------------------------------------------

STAGING_DIRECTORY = "main-staging"
STAGING_GITHUB_ENVIRONMENT = "main-staging"

# The Ansible group the same stack converges, which this change must NOT move.
# Carried here only so the assertion that the two axes have come apart has both
# sides of it; the field's own correctness is asserted elsewhere in this suite.
STAGING_TARGET_ENVIRONMENT = "staging"


# --------------------------------------------------------------------------
# Reading the declarations
#
# Split into a thin reader over the committed tree and pure finders that take
# what they examine as an argument. Over the committed tree alone, a finder that
# reported no offence whatever it was given would satisfy every assertion below,
# and would do so most convincingly on the day the change landed.
# --------------------------------------------------------------------------


def declared_axes(root: Path | None = None) -> dict[str, tuple[str | None, str | None]]:
    """Each stack directory mapped to the two names its own declaration states:
    the GitHub Environment its apply job attaches to, and the Ansible group its
    converge targets.

    Both are read through `environment_declarations`, the reader the pipeline's
    own discovery is asserted against, rather than by parsing the file again --
    a second parser would be a second answer to the question of what the
    declaration says, and the pipeline only has one.

    Takes `root` so the finders below can be exercised against a tree this file
    supplies.
    """
    return {
        name: (declaration.github_environment, declaration.target_group)
        for name, declaration in environment_declarations(root).items()
    }


def off_the_stack_axis(
    axes: Mapping[str, tuple[str | None, str | None]]
) -> list[str]:
    """Every stack whose declared GitHub Environment is not that stack's own
    name, as messages; empty where each is.

    A stack declaring NO GitHub Environment is reported rather than passed over.
    That branch is not defensive tidiness: the field is resolved by a hint match
    on the key, so a declaration whose key was mistyped, whose value was left
    blank, or which failed to parse at all arrives here as `None` -- and a
    finder that skipped it would report the tree conforming on the one input
    that means nothing was read.
    """
    offences = []
    for stack in sorted(axes):
        github_environment = axes[stack][0]
        if not github_environment:
            offences.append(
                f"{stack} declares no GitHub Environment at all, so the name its apply "
                "job attaches to is not readable from the committed files -- and a job "
                "naming nothing is a job GitHub does not refuse"
            )
        elif github_environment != stack:
            offences.append(
                f"{stack} declares the {github_environment!r} GitHub Environment rather "
                f"than {stack!r}. `docs/naming-conventions.md` gives the Environment the "
                "stack's own name, because a GitHub Environment is scoped to one "
                "repository and a second tenant's environment would collide with a name "
                "carrying only the environment axis"
            )
    return offences


def axes_that_coincide(
    axes: Mapping[str, tuple[str | None, str | None]]
) -> list[str]:
    """Every stack whose GitHub Environment and declared Ansible group spell one
    word, as messages; empty where they differ.

    The two fields spelled the same word is not by itself a defect -- it is the
    state this change ends. What makes it worth reporting afterwards is that the
    two are read by different mechanisms and moved by different changes: while
    they coincide, an edit to either reads as an edit to both, and nothing says
    which one a reader is looking at.
    """
    offences = []
    for stack in sorted(axes):
        github_environment, target_environment = axes[stack]
        if github_environment and target_environment and github_environment == target_environment:
            offences.append(
                f"{stack} declares {github_environment!r} as both its GitHub Environment "
                "and the Ansible group its converge targets. The first is on the stack "
                "axis and the second on the environment axis; two stacks of different "
                "tenants in one environment share the group and may never share the "
                "Environment"
            )
    return offences


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Gated Production Apply Applies the Reviewed Plan
#   -- scenario "A merge affecting one environment raises no other
#      environment's approval", for the half of it that is a static read
#
# The scenario is about which approval a merge raises, which is a run of a
# workflow and is not readable here. What IS readable is the committed value
# that decides which Environment this stack's apply job attaches to, and that
# value is what this change moves.
# --------------------------------------------------------------------------


class TestTheStagingStackDeclaresTheEnvironmentNamedForIt(unittest.TestCase):
    """DERIVED -- this change's proposal.md and tasks.md 4.1, not a scenario.
    No delta scenario names `main-staging` as a GitHub Environment; see the
    constants block above for why, and `test-plan.md` for the full accounting.

    This is the canary's own assertion, and the only one of this change's tests
    that rides in the staging pull request. It is red from the moment it is
    committed until tasks.md 4.1 moves the declaration, which happens in that
    same pull request.
    """

    def setUp(self) -> None:
        self.axes = declared_axes()
        self.assertIn(
            STAGING_DIRECTORY,
            self.axes,
            f"there is no {STAGING_DIRECTORY!r} stack directory, so every assertion in "
            "this class would pass over a stack that is not there",
        )

    def test_the_staging_stack_declares_the_environment_named_for_it(self) -> None:
        """DERIVED -- see the class docstring."""
        github_environment = self.axes[STAGING_DIRECTORY][0]
        self.assertEqual(
            STAGING_GITHUB_ENVIRONMENT,
            github_environment,
            f"the {STAGING_DIRECTORY} stack declares {github_environment!r} as its "
            f"GitHub Environment rather than {STAGING_GITHUB_ENVIRONMENT!r}. Its apply "
            "and converge jobs attach to whatever this field names, and GitHub creates "
            "an Environment a job names rather than refusing it -- so a stale value "
            "here is a job running against an Environment holding no secrets and no "
            "protection rules, reported as a credential failure several steps later",
        )

    def test_the_staging_stacks_two_axes_no_longer_spell_one_word(self) -> None:
        """DERIVED -- this change's proposal.md ("The two GitHub Environments
        move onto the stack axis") and its design.md's Non-Goals ("Touching the
        environment axis"), read together.

        Both sides are asserted rather than only the difference: a test that
        read `github_environment != target_environment` alone would also pass on
        a tree where this change had wrongly moved the GROUP instead, which is
        the edit the change's Non-Goals forbid by name and which would break the
        converge's `group_vars` lookup and its `--vault-id` label together.
        """
        github_environment, target_environment = self.axes[STAGING_DIRECTORY]
        self.assertEqual(
            STAGING_TARGET_ENVIRONMENT,
            target_environment,
            f"the {STAGING_DIRECTORY} stack declares {target_environment!r} as the "
            "Ansible group its converge targets. This change moves the GitHub "
            "Environment and must not touch the environment axis: the group names the "
            "play's `hosts:`, the `--vault-id` label and the `group_vars` file, and all "
            "three resolve silently to nothing when it moves",
        )
        self.assertEqual(
            [],
            axes_that_coincide({STAGING_DIRECTORY: self.axes[STAGING_DIRECTORY]}),
            "; ".join(axes_that_coincide({STAGING_DIRECTORY: self.axes[STAGING_DIRECTORY]})),
        )


# --------------------------------------------------------------------------
# The reads above are reads
# --------------------------------------------------------------------------


class TestTheseReadsDiscriminate(unittest.TestCase):
    """Every read in this file is a static read of a committed file, so a green
    run establishes nothing on its own. Each test below hands a finder material
    built to falsify it, and the material is a mapping this file supplies or a
    scratch tree it writes -- never the repository.

    `declared_axes` is exercised against a scratch tree for the same reason: it
    is the one function here that touches the filesystem, and a reader returning
    an empty mapping would make both finders above report a conforming tree.
    """

    def _scratch(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="stack-axis-"))
        self.addCleanup(shutil.rmtree, directory, True)
        return directory

    @staticmethod
    def _stack(root: Path, name: str, body: str) -> None:
        directory = root / "terraform" / "stacks" / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "pipeline.yml").write_text(body, encoding="utf-8")

    def test_a_stack_whose_environment_is_not_its_name_is_reported(self) -> None:
        """The state this change ends, and the state it must not return to."""
        offences = off_the_stack_axis({"main-staging": ("staging", "staging")})
        self.assertEqual(1, len(offences), offences)
        self.assertIn("rather than 'main-staging'", offences[0])

    def test_a_stack_on_the_stack_axis_is_not_reported(self) -> None:
        """Without this, a finder reporting every stack would satisfy the test
        above while making the committed assertion unfailable in the direction
        that matters."""
        self.assertEqual(
            [],
            off_the_stack_axis(
                {
                    "main-production": ("main-production", "production"),
                    "main-staging": ("main-staging", "staging"),
                }
            ),
        )

    def test_a_stack_declaring_no_environment_is_reported(self) -> None:
        """`None` is what an unparsed declaration, a mistyped key and a blank
        value all arrive as, and it is the input on which a finder that skipped
        it would report the tree conforming having read nothing."""
        offences = off_the_stack_axis({"main-staging": (None, "staging")})
        self.assertEqual(1, len(offences), offences)
        self.assertIn("declares no GitHub Environment", offences[0])

    def test_every_offending_stack_is_reported_rather_than_the_first(self) -> None:
        """Both stacks are off the axis before this change lands, and an author
        sent back for one file at a time would run the suite twice to learn
        what a single run already knew."""
        offences = off_the_stack_axis(
            {"main-production": ("production", "production"), "main-staging": ("staging", "staging")}
        )
        self.assertEqual(2, len(offences), offences)

    def test_two_axes_spelling_one_word_are_reported(self) -> None:
        self.assertEqual(
            1, len(axes_that_coincide({"main-production": ("production", "production")}))
        )

    def test_two_axes_spelling_different_words_are_not_reported(self) -> None:
        self.assertEqual(
            [], axes_that_coincide({"main-production": ("main-production", "production")})
        )

    def test_a_stack_missing_either_axis_is_not_read_as_a_collision(self) -> None:
        """Two absent fields are equal to each other, and a comparison made
        before the absence was ruled out would report a collision that is really
        a declaration nobody could read. The absence itself is
        `off_the_stack_axis`'s to report, and it does."""
        self.assertEqual([], axes_that_coincide({"main-staging": (None, None)}))
        self.assertEqual([], axes_that_coincide({"main-staging": (None, "staging")}))
        self.assertEqual([], axes_that_coincide({"main-staging": ("main-staging", None)}))

    def test_the_reader_returns_the_two_names_a_declaration_states(self) -> None:
        """The reader is what every assertion above is given, and one returning
        nothing would report a conforming tree from an empty repository."""
        scratch = self._scratch()
        self._stack(
            scratch,
            "main-staging",
            "github_environment: main-staging\n"
            "read_only_secret: HCLOUD_TOKEN_MAIN_STAGING\n"
            "target_environment: staging\n",
        )
        self.assertEqual(
            {"main-staging": ("main-staging", "staging")}, declared_axes(scratch)
        )

    def test_the_reader_separates_the_two_fields_rather_than_conflating_them(self) -> None:
        """Both field names carry the word `environment`, and a reader matching
        on that alone would answer one of them for both -- which would make the
        collision finder above report every stack, or none, depending on which
        it picked."""
        scratch = self._scratch()
        self._stack(
            scratch,
            "main-production",
            "github_environment: main-production\n"
            "read_only_secret: HCLOUD_TOKEN_MAIN_PRODUCTION\n"
            "target_environment: production\n",
        )
        self.assertEqual(
            {"main-production": ("main-production", "production")}, declared_axes(scratch)
        )

    def test_the_reader_reports_an_unreadable_declaration_as_absent(self) -> None:
        """A declaration naming no Environment must reach the finder as `None`
        rather than as a string, since the finder's absence branch is what
        stands between an unreadable file and a green sweep."""
        scratch = self._scratch()
        self._stack(scratch, "main-staging", "target_environment: staging\n")
        self.assertEqual({"main-staging": (None, "staging")}, declared_axes(scratch))

    def test_a_tree_carrying_no_stacks_reads_as_no_stacks(self) -> None:
        """Which is why the committed assertions above check the stack is in the
        mapping before reading it: this is what a wrong root, a moved directory
        or a reader that failed silently looks like, and both finders pass it."""
        self.assertEqual({}, declared_axes(self._scratch()))
        self.assertEqual([], off_the_stack_axis({}))
        self.assertEqual([], axes_that_coincide({}))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
