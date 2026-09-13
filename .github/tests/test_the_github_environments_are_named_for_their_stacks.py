"""Static-assertion tests for the two GitHub Environments being named for their
stacks rather than for the environment axis.

Derived from the delta specifications of the OpenSpec change
`rename-the-github-environments`, before any implementation of that change
existed. The path those deltas sit at is not written here: a change's artifacts
move when it is archived, and this repository's citation convention is to name
the change and the artifact in prose instead.

Three capabilities carry a `MODIFIED` delta for that change, eight requirements
between them, and in every one of them the edit is the same literal: the GitHub
Environment `production` becomes `main-production`. Each class below names the
requirement and the scenario it traces to, and every assertion is annotated
SPECIFIED (it traces to SHALL text or to a scenario in a delta spec) or DERIVED
(it traces to that change's `proposal.md`, `design.md` or `tasks.md`, or to
`docs/naming-conventions.md`, rather than to a scenario). See that change's
`test-plan.md` for the scenario-to-test mapping, the baseline, the scenarios
deliberately left uncovered, the obsolete-test candidates, and the project
questions this file had to take an assumption on.

Which pull request this file rides in
-------------------------------------
The second one. That change merges in two pull requests off one branch --
staging's flip first, production's second -- and both must be green before
either merges, so an assertion about production's new Environment name cannot be
committed until the staging pull request has merged. Every assertion in this
module is about production's name, about the deploy gate that names it, or about
a property that is only true once BOTH stacks have flipped, so the whole file
belongs in the second pull request and none of it in the first. The canary's own
assertion is in `test_the_staging_github_environment_moves_first.py`, which this
file imports its readers from rather than restating them.

That change's tasks.md 2.2 requires this to be stated, and states it the same
way.

Why this is a file of its own rather than a section of an existing one
----------------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. Nothing here edits, deletes or disables an
existing test. Three literals already in this suite name the Environments this
change moves -- `PROD_GITHUB_ENVIRONMENT` in
`test_environment_agnostic_pipeline.py`, `SECOND_ENVIRONMENT_GITHUB_ENVIRONMENT`
in `test_a_second_environment.py` and `GATED_DEPLOY_ENVIRONMENT` in
`test_ci_configuration.py` -- and moving each is the implementing author's task,
recorded in `test-plan.md` rather than performed here.

What this reads that those three do not: each of them compares a committed
declaration against a constant in its own module, and that constant is moved by
the same author, in the same commit, as the file it is compared with. A green
result there establishes that one value was typed twice. The assertions below
are written by an author who has not seen the implementation, against the
literal the requirement states and against the RELATION the naming scheme
states, which no constant can satisfy by being edited alongside its own subject.

`TestTheDeployGateNamesTheEnvironmentAStackDeclares` in
`test_the_external_service_names_are_retired.py` is the nearest neighbour and is
deliberately not restated: it asserts that the deploy gate and SOME stack's
declaration name one Environment, as an equality between two committed files and
without naming either. What it cannot say is WHICH stack, and the requirement
says which -- "the same GitHub Environment protection rule already used by the
Terraform apply workflow for the production stack". That is the gap below.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable by name:
    python3 -m unittest \\
        test_the_github_environments_are_named_for_their_stacks\\
.TestTheProductionStackDeclaresTheEnvironmentNamedForIt\\
.test_the_production_stack_declares_the_environment_named_for_it

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling imports below resolve.

What no assertion here establishes
----------------------------------
Nothing whatever about GitHub. Not that a `main-production` Environment exists,
not that it carries a required reviewer, not that it holds the fifteen secrets
`production` holds, not that a pending job cannot read them, and not that the old
Environments were deleted. Every one of those is reachable only by a network call
this suite is forbidden from making, and that prohibition is itself asserted by
`TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in
`test_ci_configuration.py`, which reads this module among the others. The
change's own task list makes each of them an operator observation, and its
`test-plan.md` records every such scenario as uncovered here.

A green run is therefore weaker than it looks, and deliberately so. The
committed name and the Environment it resolves to are different facts, and this
file reads only the first. The change's central risk lives in the gap between
them: GitHub CREATES an Environment a job names, with no protection rules, so a
declaration this file reports as correct may be pointing at an Environment
nobody built -- which runs unreviewed rather than failing.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Iterable, Mapping

from test_ci_configuration import (
    ARCHIVE_SEGMENT,
    CHANGE_PATH_PREFIX,
    TrackedFilesUnavailable,
    tracked_files,
)
from test_the_external_service_names_are_retired import (
    decoded,
    gated_environments,
    platform_deploy_gated_environments,
)
from test_the_staging_github_environment_moves_first import (
    axes_that_coincide,
    declared_axes,
    off_the_stack_axis,
)

# --------------------------------------------------------------------------
# What the production stack is expected to declare
#
# SPECIFIED. Unlike staging's name, which no scenario states, this literal is
# written into the delta text in both forms: *Gated Production Apply Applies the
# Reviewed Plan* (openspec/specs/iac-cicd-pipeline/spec.md) says "The
# `main-production` Environment SHALL require a reviewer", and its scenario
# "Merge does not apply immediately" says the apply job "SHALL pause and wait for
# a required reviewer to approve the `main-production` GitHub Environment". *Gated
# Deploy Reuses the Terraform Production Environment*
# (openspec/specs/iac-platform-deploy-pipeline/spec.md) names it a third time,
# as "the Environment that stack's own committed pipeline declaration names,
# which is `main-production`".
#
# The stack DIRECTORY is not renamed by this change and is carried here only to
# say which declaration is production's.
# --------------------------------------------------------------------------

PRODUCTION_DIRECTORY = "main-production"
PRODUCTION_GITHUB_ENVIRONMENT = "main-production"

# The Ansible group the same stack converges, which this change must NOT move.
PRODUCTION_TARGET_ENVIRONMENT = "production"

# Both stacks, so that the cross-stack assertion below cannot be satisfied by a
# tree holding one. DERIVED -- `docs/naming-conventions.md`'s stack table.
EXPECTED_STACKS = ("main-production", "main-staging")

# --------------------------------------------------------------------------
# Reading the runbook's secret-writing commands
#
# `gh secret set --env <name>` is the one place in this repository's documents
# where a GitHub Environment's name is TYPED BY AN OPERATOR rather than read by
# a workflow, and it is the one needle for these two names that cannot match the
# environment axis by accident: the flag takes a deployment Environment and
# never an Ansible group, a `group_vars` file or a `--vault-id` label.
#
# That distinction is why this sweep exists and why no broader one does. The
# change's tasks.md 5.1 lists nine other needles for these names and triages
# every hit by hand, because `production` and `staging` remain correct
# everywhere on the environment axis -- see this change's `test-plan.md`, which
# records the broad sweep as deliberately untested and why.
#
# The failure this catches is a real one and is otherwise caught by nobody:
# `docs/bootstrap-a-new-host.md` is the authoritative bootstrap procedure, an
# operator follows it literally, and a stale `--env` argument here writes a
# secret into an Environment this change deletes -- reported, if at all, as an
# apply that cannot reach Hetzner.
# --------------------------------------------------------------------------

SECRET_WRITE = "gh secret set"
ENV_ARGUMENT = re.compile(r"--env(?:=|\s+)(\S+)")

# A path prefix whose documents are read as records rather than as instructions.
# `openspec/` holds the specifications and every change record, including this
# change's own artifacts, which name the Environments this change retires
# because naming what it renames from is what a change record is for.
# `.github/tests/` is this suite, where a name must be written down in order to
# be asserted -- this file does it four paragraphs above.
UNSWEPT_PREFIXES = ("openspec/", ".github/tests/")

DOCUMENT_SUFFIX = ".md"

# The document the sweep exists for. Anchored by name rather than by a count,
# which any commit would move.
RUNBOOK = "docs/bootstrap-a-new-host.md"


def swept_documents(files: Mapping[str, str]) -> dict[str, str]:
    """The committed documents this sweep reads: Markdown, outside the record
    and test-suite prefixes."""
    return {
        path: text
        for path, text in files.items()
        if path.endswith(DOCUMENT_SUFFIX)
        and not any(path.startswith(prefix) for prefix in UNSWEPT_PREFIXES)
    }


def environment_arguments(files: Mapping[str, str]) -> list[tuple[str, int, str]]:
    """Every `gh secret set ... --env <name>` a swept document writes, as
    `(path, line number, name)`.

    A placeholder is not a name and is skipped: the runbook writes
    `--env <environment>` where the reader supplies their own value, and
    reporting that as an undeclared Environment would make this sweep red on
    correct text forever -- which is how a check comes to be deleted.

    Matched only on a line that also invokes the command, because `--env` is a
    flag several tools take and only this one takes a deployment Environment.
    """
    found = []
    for path in sorted(files):
        for number, line in enumerate(files[path].splitlines(), start=1):
            if SECRET_WRITE not in line:
                continue
            for name in ENV_ARGUMENT.findall(line):
                if any(character in name for character in "<>${}\"'`"):
                    continue
                found.append((path, number, name))
    return found


def secret_writes_naming_no_declared_environment(
    arguments: Iterable[tuple[str, int, str]], declared: Iterable[str]
) -> list[str]:
    """Every documented secret write whose `--env` argument is an Environment no
    stack declares, as `<path>:<line>: <name>` with the reason.

    Takes both sides as arguments rather than reading them, so this can be
    handed a half-corrected pair -- which is the state the change passes through
    and the one nothing else in the repository would report.
    """
    names = sorted(set(declared))
    offences = []
    for path, number, name in arguments:
        if name not in names:
            offences.append(
                f"{path}:{number}: `--env {name}` names a GitHub Environment no stack "
                f"declares; the stacks declare {names}. An operator following this line "
                "writes the secret into an Environment no job attaches to, and "
                "`gh secret set` creates nothing -- it fails on the public-key fetch, "
                "several steps from the document that sent them there"
            )
    return offences


def deploy_gate_disagreements(
    gated: Iterable[str], axes: Mapping[str, tuple[str | None, str | None]], stack: str
) -> list[str]:
    """Why the platform deploy's gate does not name the Environment `stack`
    declares, as messages; empty where it does.

    Distinct from `gate_disagreements` in
    `test_the_external_service_names_are_retired.py`, which asks whether the
    gate names an Environment SOME stack declares. This asks which stack, which
    is what the requirement states and what that comparison cannot see: a deploy
    gated on the staging stack's Environment satisfies it exactly as well as one
    gated on production's.
    """
    names = sorted(set(gated))
    if len(names) != 1:
        return [
            f"the platform deploy declares {names or 'no'} deployment environment(s); "
            "the requirement names one, reused from the Terraform apply workflow"
        ]
    declared = axes.get(stack, (None, None))[0]
    if not declared:
        return [
            f"the {stack!r} stack declares no GitHub Environment, so which Environment "
            "the deploy is meant to share its approvers with is not readable from the "
            "committed files"
        ]
    if names[0] != declared:
        return [
            f"the platform deploy gates on the {names[0]!r} Environment while the "
            f"{stack!r} stack declares {declared!r}. The requirement obliges ONE "
            "Environment to gate both kinds of production change; two names means two "
            "approval lists, and the deploy's is whichever one GitHub created when the "
            "job first named it -- with no protection rules"
        ]
    return []


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Gated Production Apply Applies the Reviewed Plan
#   -- scenario "Merge does not apply immediately"
# --------------------------------------------------------------------------


class TestTheProductionStackDeclaresTheEnvironmentNamedForIt(unittest.TestCase):
    """SPECIFIED -- Gated Production Apply Applies the Reviewed Plan
    (openspec/specs/iac-cicd-pipeline/spec.md), scenario "Merge does not apply
    immediately": "the apply job SHALL pause and wait for a required reviewer to
    approve the `main-production` GitHub Environment before running
    `terraform apply`".

    Only the NAME is readable here. Whether that Environment pauses for anyone
    is a protection rule, which is a repository setting -- the requirement says
    so itself, in the sentence beginning "Whether that pauses for a human". The
    change's tasks.md 6.1 and 6.5 make the reviewer an operator observation,
    read twice, because it is the one claim about this change that has already
    gone stale once.
    """

    def setUp(self) -> None:
        self.axes = declared_axes()
        self.assertIn(
            PRODUCTION_DIRECTORY,
            self.axes,
            f"there is no {PRODUCTION_DIRECTORY!r} stack directory, so every assertion "
            "in this class would pass over a stack that is not there",
        )

    def test_the_production_stack_declares_the_environment_named_for_it(self) -> None:
        """SPECIFIED -- see the class docstring."""
        github_environment = self.axes[PRODUCTION_DIRECTORY][0]
        self.assertEqual(
            PRODUCTION_GITHUB_ENVIRONMENT,
            github_environment,
            f"the {PRODUCTION_DIRECTORY} stack declares {github_environment!r} as its "
            f"GitHub Environment rather than {PRODUCTION_GITHUB_ENVIRONMENT!r}. Its "
            "apply and converge jobs attach to whatever this field names, and GitHub "
            "creates an Environment a job names rather than refusing it -- so a stale "
            "value here is a production apply running with no required reviewer, "
            "reported as a successful run",
        )

    def test_the_production_stacks_two_axes_no_longer_spell_one_word(self) -> None:
        """DERIVED -- this change's proposal.md ("The two GitHub Environments
        move onto the stack axis") and its design.md's Non-Goals ("Touching the
        environment axis"), read together.

        Both sides are asserted rather than only the difference, for the reason
        the staging module's counterpart gives: a test reading only that the two
        differ would also pass on a tree where the GROUP had been moved instead,
        which is the edit the Non-Goals forbid by name and which resolves to a
        `group_vars` file and a `--vault-id` label that do not exist.
        """
        github_environment, target_environment = self.axes[PRODUCTION_DIRECTORY]
        self.assertEqual(
            PRODUCTION_TARGET_ENVIRONMENT,
            target_environment,
            f"the {PRODUCTION_DIRECTORY} stack declares {target_environment!r} as the "
            "Ansible group its converge targets. This change moves the GitHub "
            "Environment and must not touch the environment axis",
        )
        offences = axes_that_coincide(
            {PRODUCTION_DIRECTORY: self.axes[PRODUCTION_DIRECTORY]}
        )
        self.assertEqual([], offences, "; ".join(offences))


# --------------------------------------------------------------------------
# iac-platform-deploy-pipeline / Gated Deploy Reuses the Terraform Production
# Environment
#
# "The Environment is named for the **stack** rather than for the environment
# axis, per `docs/naming-conventions.md`."
# --------------------------------------------------------------------------


class TestEveryStacksGithubEnvironmentIsOnTheStackAxis(unittest.TestCase):
    """SPECIFIED for the relation -- Gated Deploy Reuses the Terraform
    Production Environment (openspec/specs/iac-platform-deploy-pipeline/spec.md):
    "The Environment is named for the **stack** rather than for the environment
    axis, per `docs/naming-conventions.md`."

    DERIVED for its extension to every stack. The requirement states the
    relation about the one Environment it is concerned with; that it holds of
    every stack comes from `docs/naming-conventions.md`'s own stack table, which
    derives the GitHub Environment from the stack name along with the directory,
    the HCP workspace, the Hetzner project and the read-only secret.

    THIS IS THE ASSERTION NO EXISTING LITERAL CAN MAKE. The three constants this
    change moves each compare a committed declaration against a value in the
    same author's hands: flip both and the check is green whatever the name
    became. This compares the declaration against the stack's own directory
    name, which this change does not move -- so it fails on a name that is
    merely consistent rather than correct.

    It is also the assertion that can only be green once BOTH stacks have
    flipped, which is why the whole of this module rides in the second pull
    request.
    """

    def setUp(self) -> None:
        self.axes = declared_axes()
        missing = sorted(set(EXPECTED_STACKS) - set(self.axes))
        self.assertEqual(
            [],
            missing,
            f"{missing} are not stack directories, so this comparison would run over "
            "fewer stacks than the repository has -- and at one stack every "
            "cross-stack property below is vacuous",
        )

    def test_every_stack_declares_the_github_environment_named_for_it(self) -> None:
        """SPECIFIED for the relation, DERIVED for its extension -- see the
        class docstring."""
        offences = off_the_stack_axis(self.axes)
        self.assertEqual([], offences, "; ".join(offences))

    def test_no_stacks_two_axes_spell_one_word(self) -> None:
        """DERIVED -- this change's proposal.md and design.md. The GitHub
        Environment and the Ansible group are on different axes, and while they
        coincide an edit to either reads as an edit to both."""
        offences = axes_that_coincide(self.axes)
        self.assertEqual([], offences, "; ".join(offences))


class TestTheDeployGateNamesTheProductionStacksEnvironment(unittest.TestCase):
    """SPECIFIED -- Gated Deploy Reuses the Terraform Production Environment
    (openspec/specs/iac-platform-deploy-pipeline/spec.md): the deploy "SHALL
    require manual approval via the same GitHub Environment protection rule
    already used by the Terraform apply workflow for the production stack -- the
    Environment that stack's own committed pipeline declaration names, which is
    `main-production`", and its scenario "Same approvers gate both kinds of
    production change": "both SHALL be gated by the same `main-production`
    Environment's required reviewers".

    Distinct from `TestTheDeployGateNamesTheEnvironmentAStackDeclares` in
    `test_the_external_service_names_are_retired.py` rather than a restatement
    of it. That class asks whether the gate names an Environment SOME stack
    declares, deliberately without naming either side, which is what makes it
    survive this change unedited. It is satisfied by a deploy gated on the
    STAGING stack's Environment -- an ungated production deploy, since staging's
    Environment deliberately requires no reviewer, and one that reads as
    agreement to every comparison keyed on the names that are declared. Which
    stack is what this class adds.
    """

    def test_the_deploy_gate_names_the_production_stacks_declared_environment(self) -> None:
        """SPECIFIED -- see the class docstring."""
        axes = declared_axes()
        self.assertIn(
            PRODUCTION_DIRECTORY,
            axes,
            f"there is no {PRODUCTION_DIRECTORY!r} stack directory, so this comparison "
            "would read one side of itself",
        )
        offences = deploy_gate_disagreements(
            platform_deploy_gated_environments(), axes, PRODUCTION_DIRECTORY
        )
        self.assertEqual([], offences, "; ".join(offences))

    def test_the_environment_both_are_named_for_is_the_one_the_requirement_names(
        self,
    ) -> None:
        """SPECIFIED -- "which is `main-production`". Asserted as well as the
        equality above, because an equality between two committed files is
        satisfied by any name typed into both, and this requirement now states
        which name."""
        gated = sorted(set(platform_deploy_gated_environments()))
        self.assertEqual(
            [PRODUCTION_GITHUB_ENVIRONMENT],
            gated,
            f"the platform deploy gates on {gated} rather than on "
            f"[{PRODUCTION_GITHUB_ENVIRONMENT!r}], which is the Environment this "
            "requirement names and the one the production stack's apply attaches to",
        )


# --------------------------------------------------------------------------
# The one document that TYPES an Environment's name
#
# DERIVED throughout -- this change's tasks.md 5.2 and 7.6. No scenario states
# anything about the runbook.
# --------------------------------------------------------------------------


class TestTheRunbookWritesSecretsIntoAnEnvironmentAStackDeclares(unittest.TestCase):
    """DERIVED -- this change's tasks.md 7.6, which corrects
    `docs/bootstrap-a-new-host.md`'s Environment-creation step, its
    `gh secret set --env` block and its secret inventory, and §6.6's note about
    which argument that flag takes.

    Nothing in this suite reads that document today, and it is the authoritative
    bootstrap procedure: a stale instruction in it survives every check this
    repository has and is discovered by an operator running a command that
    fails. This class is the narrow part of it that a static read can hold --
    that an Environment the document tells someone to write a secret into is one
    a stack declares.

    THIS ASSERTION IS GREEN BOTH BEFORE AND AFTER THE CHANGE, and that is worth
    saying rather than leaving for a reader to discover. It reports the
    INTERVAL: a `pipeline.yml` flipped while the runbook still names the old
    Environment. Both halves of that interval land in the same pull request, so
    what this really does is refuse to let that pull request merge with the
    declaration moved and the document not. Its discriminators below are
    therefore the only evidence that it can fail at all.
    """

    def setUp(self) -> None:
        try:
            self.documents = swept_documents(decoded(tracked_files()))
        except TrackedFilesUnavailable as unavailable:
            self.fail(str(unavailable))

    def test_the_sweep_reaches_the_runbook(self) -> None:
        """DERIVED -- no scenario states it. The assertion below is normative
        over every swept document, and a listing reaching none of them would
        pass it having read nothing."""
        self.assertIn(
            RUNBOOK,
            self.documents,
            f"{RUNBOOK} is not among the documents this sweep reads, so the one file "
            "it exists for is read by nothing",
        )

    def test_the_sweep_finds_the_commands_it_exists_to_read(self) -> None:
        """DERIVED -- no scenario states it. A pattern that matched nothing
        would satisfy the assertion below over any tree at all, and the
        difference between `no command names a stale Environment` and `no
        command was found` is the whole value of this class."""
        found = environment_arguments(self.documents)
        self.assertTrue(
            found,
            "no committed document writes a secret with an explicit `--env` argument, "
            f"so the sweep below reports nothing whatever {RUNBOOK} says. The runbook's "
            "Environment-creation stage is where those commands live",
        )

    def test_no_documented_secret_write_names_an_undeclared_environment(self) -> None:
        """DERIVED -- this change's tasks.md 7.6."""
        declared = [
            environment for environment, _ in declared_axes().values() if environment
        ]
        self.assertTrue(
            declared,
            "no stack declares a GitHub Environment, so this comparison would read one "
            "side of itself and report every documented command correct",
        )
        offences = secret_writes_naming_no_declared_environment(
            environment_arguments(self.documents), declared
        )
        self.assertEqual([], offences, "; ".join(offences))


# --------------------------------------------------------------------------
# The reads above are reads
# --------------------------------------------------------------------------


class TestTheseReadsDiscriminate(unittest.TestCase):
    """Every read in this file is a static read of a committed file, so a green
    run establishes nothing on its own: a finder that reported no offence
    whatever it was given would satisfy every assertion above, and would do so
    most convincingly on the day the change landed.

    Each test below hands a finder material this file supplies. The readers
    imported from the staging module carry their own discriminators there and
    are not re-exercised here.
    """

    def test_a_deploy_gated_on_another_stacks_environment_is_reported(self) -> None:
        """The failure the neighbouring equality cannot see: a deploy gated on
        an Environment a stack really does declare, but the wrong stack. Staging's
        Environment deliberately requires no reviewer, so this is an ungated
        production deploy that every keyed comparison reads as agreement."""
        offences = deploy_gate_disagreements(
            ["main-staging"],
            {
                "main-production": ("main-production", "production"),
                "main-staging": ("main-staging", "staging"),
            },
            "main-production",
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn("while the 'main-production' stack declares", offences[0])

    def test_a_deploy_gated_on_the_production_stacks_environment_is_not_reported(
        self,
    ) -> None:
        """Without this, a comparison refusing every input would satisfy the
        test above while making the committed assertion unfailable."""
        self.assertEqual(
            [],
            deploy_gate_disagreements(
                ["main-production"],
                {
                    "main-production": ("main-production", "production"),
                    "main-staging": ("main-staging", "staging"),
                },
                "main-production",
            ),
        )

    def test_a_deploy_declaring_no_environment_is_reported(self) -> None:
        """A deploy job whose `environment:` was dropped is ungated, and returns
        the same empty read as a workflow this comparison cannot parse."""
        offences = deploy_gate_disagreements(
            [], {"main-production": ("main-production", "production")}, "main-production"
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn("no deployment environment", offences[0])

    def test_a_deploy_declaring_two_environments_is_reported(self) -> None:
        offences = deploy_gate_disagreements(
            ["main-production", "main-staging"],
            {"main-production": ("main-production", "production")},
            "main-production",
        )
        self.assertEqual(1, len(offences), offences)

    def test_a_production_stack_declaring_nothing_is_reported_rather_than_matched(
        self,
    ) -> None:
        """`None` on the declaration side must not be compared against a name.
        Without the guard the message would read as a mismatch, sending an
        author to the workflow when the defect is in the declaration."""
        offences = deploy_gate_disagreements(
            ["main-production"], {"main-production": (None, "production")}, "main-production"
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn("declares no GitHub Environment", offences[0])

    def test_the_workflow_read_finds_the_environment_in_either_form(self) -> None:
        """GitHub accepts `environment: name` and `environment: {name: ...}`, and
        the committed workflow uses only the first -- so the mapping branch would
        go unexecuted if this file read only its own repository. A read blind to
        the mapping form reports a gate declared with a `url:` as no gate at all,
        which is the same message as a gate genuinely removed."""
        self.assertEqual(
            ["main-production"],
            gated_environments({"jobs": {"deploy": {"environment": "main-production"}}}),
        )
        self.assertEqual(
            ["main-production"],
            gated_environments(
                {
                    "jobs": {
                        "deploy": {
                            "environment": {
                                "name": "main-production",
                                "url": "https://example.invalid",
                            }
                        }
                    }
                }
            ),
        )

    def test_a_documented_write_into_an_undeclared_environment_is_reported(self) -> None:
        """The state this change passes through: the declaration moved and the
        runbook not."""
        arguments = environment_arguments(
            {RUNBOOK: "gh secret set HCLOUD_TOKEN --env production\n"}
        )
        self.assertEqual([(RUNBOOK, 1, "production")], arguments)
        offences = secret_writes_naming_no_declared_environment(
            arguments, ["main-production", "main-staging"]
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn(f"{RUNBOOK}:1:", offences[0])

    def test_a_documented_write_into_a_declared_environment_is_not_reported(self) -> None:
        """Without this, a finder reporting every command would satisfy the test
        above while making the committed assertion unfailable."""
        self.assertEqual(
            [],
            secret_writes_naming_no_declared_environment(
                environment_arguments(
                    {RUNBOOK: "gh secret set HCLOUD_TOKEN --env main-production\n"}
                ),
                ["main-production", "main-staging"],
            ),
        )

    def test_a_placeholder_argument_is_not_read_as_an_environment(self) -> None:
        """The runbook writes `--env <environment>` where the reader supplies
        their own value. Reporting that would make this sweep red on correct
        text forever, and a check that cannot go green is a check somebody
        deletes."""
        for line in (
            "gh secret set ANSIBLE_VAULT_PASSWORD --env <environment>\n",
            "gh secret set ANSIBLE_VAULT_PASSWORD --env <stack>\n",
            "gh secret set ANSIBLE_VAULT_PASSWORD --env ${STACK}\n",
            "gh secret set ANSIBLE_VAULT_PASSWORD --env `main-production`\n",
        ):
            with self.subTest(line=line.strip()):
                self.assertEqual([], environment_arguments({RUNBOOK: line}))

    def test_the_flag_is_read_only_where_the_command_is_the_one_that_takes_it(
        self,
    ) -> None:
        """`--env` is a flag several tools take, and only `gh secret set` takes a
        deployment Environment. A sweep matching the flag alone would report a
        container invocation as an undeclared Environment."""
        self.assertEqual(
            [],
            environment_arguments(
                {"README.md": "docker run --env production myimage\n"}
            ),
        )

    def test_the_equals_form_is_read_as_well_as_the_spaced_one(self) -> None:
        """`--env=production` and `--env production` are one command to `gh` and
        would be two answers to a reader that knew only one of them."""
        self.assertEqual(
            [(RUNBOOK, 1, "production")],
            environment_arguments(
                {RUNBOOK: "gh secret set HCLOUD_TOKEN --env=production\n"}
            ),
        )

    def test_the_line_reported_is_the_line_the_command_is_on(self) -> None:
        """A message pointing at the wrong line sends the reader to the wrong
        stage of a runbook, which is where every one of these commands is."""
        self.assertEqual(
            [(RUNBOOK, 3, "staging")],
            environment_arguments(
                {RUNBOOK: "one\ntwo\ngh secret set HCLOUD_TOKEN --env staging\nfour\n"}
            ),
        )

    def test_every_offending_command_is_reported_rather_than_the_first(self) -> None:
        """The runbook writes four of these in one block, and an author sent
        back for one line at a time would run the suite four times to learn what
        a single run already knew."""
        corpus = {
            RUNBOOK: (
                "gh secret set HCLOUD_TOKEN --env production\n"
                "gh secret set TF_API_TOKEN --env production\n"
                "gh secret set HCLOUD_TOKEN --env staging\n"
                "gh secret set TF_API_TOKEN --env staging\n"
            )
        }
        offences = secret_writes_naming_no_declared_environment(
            environment_arguments(corpus), ["main-production", "main-staging"]
        )
        self.assertEqual(4, len(offences), offences)

    def test_a_record_of_the_old_name_is_not_read_as_an_instruction(self) -> None:
        """A change record names what it renames FROM, and the specifications
        name what they once required. Neither is a command anybody runs, and a
        sweep that reported them would be red for as long as the archive
        exists."""
        for path in (
            CHANGE_PATH_PREFIX + ARCHIVE_SEGMENT + "/2026-01-01-something/tasks.md",
            "openspec/specs/iac-cicd-pipeline/spec.md",
            ".github/tests/test_the_github_environments_are_named_for_their_stacks.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    {},
                    swept_documents({path: "gh secret set HCLOUD_TOKEN --env production\n"}),
                )

    def test_a_path_merely_resembling_an_unswept_one_is_still_swept(self) -> None:
        """The exclusions are prefixes, so a file whose name merely begins the
        same way must not inherit one."""
        for path in ("docs/openspec-notes.md", "README.md", "platform/README.md"):
            with self.subTest(path=path):
                self.assertEqual(
                    [path],
                    sorted(
                        swept_documents(
                            {path: "gh secret set HCLOUD_TOKEN --env production\n"}
                        )
                    ),
                )

    def test_a_document_that_does_not_decode_is_read_rather_than_dropped(self) -> None:
        """`decoded` is what stands between a tracked file with a stray byte and
        a listing that raises halfway through. A file dropped instead would be a
        file the sweep silently does not cover."""
        text = decoded({RUNBOOK: b"\xff\xfe gh secret set X --env production\n"})
        self.assertEqual(
            [(RUNBOOK, 1, "production")], environment_arguments(swept_documents(text))
        )

    def test_a_reader_that_returned_nothing_is_visible_rather_than_green(self) -> None:
        """Both finders return an empty list over an empty corpus, which is
        indistinguishable from a conforming tree. That is why the committed
        class above asserts the runbook is reached and that commands were found
        before asserting anything about them -- this records the property those
        two guards exist for."""
        self.assertEqual([], environment_arguments({}))
        self.assertEqual([], secret_writes_naming_no_declared_environment([], []))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
