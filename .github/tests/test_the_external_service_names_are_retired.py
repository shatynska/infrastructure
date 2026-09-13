"""A static sweep for the external-service names this repository is retiring.

Derived from the delta specs of the OpenSpec change
`rename-the-external-services`, before any implementation of that change
existed. The path those deltas sit at is not written here: a change's artifacts
move when it is archived, and this repository's citation convention is to name
the change and the artifact in prose instead.

What this file is for
---------------------
That change renames four things that live outside this repository -- two HCP
Terraform workspaces, two GitHub Environments, two read-only repository secrets
and two Hetzner projects. Three capabilities carry a `MODIFIED` delta for it,
and in every one of them the edit is a single literal: the GitHub Environment
`production` becomes `main-production`. No delta scenario states a workspace
name, a repository secret name or a Hetzner project name at all.

So the deltas leave the *declarations* covered -- each stack's `pipeline.yml`,
each `versions.tf`'s `cloud` block, each inventory source's credential variable,
and `platform-deploy.yml`'s gated job are all already read by assertions in this
suite, and those assertions move with the tree. What no existing assertion reads
is the **prose around** a declaration: the runbook step an operator types, the
README paragraph naming a secret, the comment in a `versions.tf` explaining the
one beside it. That is most of this change's surface, and a name missed there is
found by a human running a command that fails, or not found at all.

This module is that one mechanism: it reads every tracked file and reports any
that still names a retired external service.

The idiom is the suite's own. `TestNoCommittedFileStillNamesTheOldTerraformRoot`
in `test_terraform_stacks_are_the_iterated_unit.py` is the same shape, written
for the change that renamed the Terraform root, and the file set here is tracked
files rather than a filesystem walk for the reason that class's own
`TestTheSweepReadsCommittedFilesOnly` records: a walk reads a developer's
provisioned `.molecule-home/`, which makes a sweep red on a working machine and
green on a runner. What differs is the exemptions -- that sweep excludes
`openspec/` entire, this one keeps `openspec/specs/` in scope, because no
requirement names any of these four values today and one that started to would
be a finding rather than history.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable by name:
    python3 -m unittest \\
        test_the_external_service_names_are_retired\\
.TestNoCommittedFileNamesARetiredExternalService\\
.test_no_swept_file_names_a_retired_external_name

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling import below resolve.

What no assertion here establishes
----------------------------------
Nothing about any external service. Not that an HCP workspace was renamed or
kept its state, not that a GitHub Environment was renamed or kept its secrets
and its required reviewer, not that a repository secret exists under its new
name, and not that a Hetzner project's API token survived its project's rename.
Every one of those is reachable only by a network call this suite is forbidden
from making, and that prohibition is itself asserted by
`TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in
`test_ci_configuration.py`, which reads this module among the others. The
change's own task list makes each of them an operator observation. This file
asserts one thing: that no committed file still says the old name.

A green run here is therefore weaker than it looks, and deliberately so. The
absence of a retired name is evidence that the repository was swept -- not that
the rename happened.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Mapping, Sequence

from test_ci_configuration import (
    ARCHIVE_SEGMENT,
    CHANGE_PATH_PREFIX,
    PLATFORM_DEPLOY,
    ROOT,
    TrackedFilesUnavailable,
    jobs,
    load_yaml,
    tracked_files,
)
from test_environment_agnostic_pipeline import environment_declarations

# --------------------------------------------------------------------------
# The names being retired
#
# DERIVED throughout. No requirement in `openspec/specs/` names a workspace, a
# repository secret or a Hetzner project as a value -- the change's proposal
# says so explicitly, and that is why only one of the four renames reaches a
# delta spec at all. These four literals come from that change's proposal.md
# ("What Changes") and its tasks.md 3.2, which names exactly this set.
#
# The GitHub Environment names `production` and `staging` are NOT swept here,
# and their absence is a decision rather than an oversight: `production` and
# `staging` are also the Ansible group names, which this change does not touch
# and must not, and a sweep for either would report every correct use of the
# environment axis. The change's tasks.md 6.4 makes those four needles a manual
# read instead. What that costs is recorded in this change's test-plan.md.
# --------------------------------------------------------------------------

RETIRED_NAMES = (
    "HCLOUD_TOKEN_PRODUCTION",
    "HCLOUD_TOKEN_STAGING",
    "infrastructure-prod",
    "infrastructure-staging",
)

# What each retired name becomes, carried only so the failure message tells a
# reader what to write instead. Never asserted as present: that a file names the
# NEW name is read by the declaration assertions elsewhere in this suite, over
# the declarations rather than over prose.
REPLACEMENTS = {
    "HCLOUD_TOKEN_PRODUCTION": "HCLOUD_TOKEN_MAIN_PRODUCTION",
    "HCLOUD_TOKEN_STAGING": "HCLOUD_TOKEN_MAIN_STAGING",
    "infrastructure-prod": "main-production",
    "infrastructure-staging": "main-staging",
}

# --------------------------------------------------------------------------
# What the sweep does not read, and why each exemption is here
#
# Every exemption is a hole, so each one is stated with the evidence that
# required it rather than with a category.
#
#   `openspec/changes/`  -- a change record names what it renames FROM. This
#       change's own proposal.md, design.md, tasks.md and handoff.md each name
#       these four literals as the from-side of a rename, and an archived record
#       says what was decided at the time. Wider than tasks.md 3.2's wording,
#       which exempts `openspec/changes/archive/` alone: under that wording this
#       assertion is red on the change's own pull request, for its own planning
#       artifacts. The widening is recorded in this change's test-plan.md.
#
#   `.github/tests/`     -- this suite. It is where a check must NAME a retired
#       name in order to assert its absence (this module does, four lines
#       above), and where several modules build synthetic trees naming `prod`,
#       `staging`, `HCLOUD_TOKEN_STAGING` or `infrastructure-prod` to exercise a
#       reader. Those fixtures assert nothing about this repository and do not
#       move. The constants that DO move -- `PROD_READ_ONLY_SECRET`,
#       `SECOND_ENVIRONMENT_WORKSPACE` and the rest -- lose no coverage by
#       sitting behind this exemption: each is compared against the committed
#       declaration by its own module, so a constant left behind while the
#       declaration moves fails there.
#
#   `docs/change-queue.md` WAS EXEMPT AND IS NOT ANY MORE, which is the
#       exemption machinery working rather than a loosening. Entry 63 named all
#       four retired literals as the work it described, and a queue entry is
#       deleted only when its change archives -- so the file had to be exempt
#       across the whole of that change and no longer. The assertion below
#       requires a whole-path exemption to still CONTAIN a retired name, so
#       deleting entry 63 in the archive commit turned it red and the repair was
#       to delete the exemption in that same commit. It is swept from here on.
#
# `docs/deferred-work.md` is deliberately NOT exempt, though it is the paired
# surface: an entry there records work not done, and about a rename that means
# the old name genuinely persists -- which is a thing to report.
# --------------------------------------------------------------------------

EXEMPT_PREFIXES = (
    CHANGE_PATH_PREFIX,
    ".github/tests/",
)

# No whole-path exemption stands today. Kept as an empty tuple rather than
# removed, because the assertion that each one still earns its keep is what
# emptied it, and the next change needing one should find the mechanism here.
EXEMPT_PATHS: tuple[str, ...] = ()

# Files the sweep must reach for a green result to mean anything. One per
# surface the change edits, at four different depths. DERIVED -- no scenario
# states them; they are the anchors that keep a reader returning nothing from
# satisfying the assertion below, chosen the way
# `TestNoCommittedFileOutsideOpenSpecCarriesAPreArchiveCitation` chooses its
# own, and for the same reason a count would not do.
SWEEP_ANCHORS = (
    "README.md",
    ".envrc.example",
    "docs/bootstrap-a-new-host.md",
    "ansible/.envrc.example",
    "ansible/inventory/main-production.hcloud.yml",
    "terraform/stacks/main-production/versions.tf",
    "terraform/stacks/main-production/pipeline.yml",
    ".github/workflows/platform-deploy.yml",
    "openspec/specs/iac-cicd-pipeline/spec.md",
)


# --------------------------------------------------------------------------
# Reading the tree
#
# Split into a pure offence-finder and a thin reader, so that the discriminating
# class at the end of this file can hand the finder material built to falsify
# it. Over the committed tree alone a finder that searched for nothing, or that
# exempted everything, would satisfy every assertion above.
# --------------------------------------------------------------------------


def swept(path: str) -> bool:
    """Whether a tracked path is one this sweep reads."""
    if path in EXEMPT_PATHS:
        return False
    return not any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)


def decoded(files: Mapping[str, bytes]) -> dict[str, str]:
    """Each tracked file as text, undecodable bytes replaced rather than raised.

    A binary file is read too. It will not normally carry one of these names,
    and skipping by extension would be a list of extensions to keep current --
    the safe direction for a prohibition is to read more, not less.
    """
    return {
        path: content.decode("utf-8", errors="replace") for path, content in files.items()
    }


def retired_name_offences(
    files: Mapping[str, str], names: Sequence[str] = RETIRED_NAMES
) -> list[str]:
    """Every swept file still naming a retired external service, as
    `<path>:<line>: <name>`, one entry per occurrence.

    `names` is a `Sequence` and not an `Iterable`, which is not pedantry: it is
    consumed in the innermost loop, so a generator would be exhausted by the
    first line of the first file and every line after it would be compared
    against nothing. That is the "finder that searched for nothing" the
    discriminating class below exists to rule out, and no fixture there would
    catch it, since all of them pass tuples.

    The match is a plain substring on each line rather than a word boundary:
    these names appear inside prose, inside a shell command, inside a YAML
    scalar and inside a Terraform comment, and the point of this read is the
    prose. `HCLOUD_TOKEN_MAIN_PRODUCTION` does not contain
    `HCLOUD_TOKEN_PRODUCTION`, so the replacement names cannot match their own
    predecessors -- which the discriminator below is what establishes.
    """
    offences: list[str] = []
    for path in sorted(files):
        if not swept(path):
            continue
        for number, line in enumerate(files[path].splitlines(), start=1):
            for name in names:
                if name in line:
                    offences.append(f"{path}:{number}: {name}")
    return offences


def committed_text(root: Path | None = None) -> dict[str, str]:
    """Every tracked file of the repository at `root`, as text.

    Raises `TrackedFilesUnavailable` rather than returning an empty mapping
    where the listing cannot be made: a sweep that read nothing would otherwise
    report the repository clean.
    """
    return decoded(tracked_files(root))


# --------------------------------------------------------------------------
# iac-cicd-pipeline / iac-state-management / iac-platform-deploy-pipeline
#
# No scenario in any of the three states this. See the module docstring for what
# the deltas do state and where it is already asserted.
# --------------------------------------------------------------------------


class TestNoCommittedFileNamesARetiredExternalService(unittest.TestCase):
    """DERIVED -- this change's tasks.md 3.2, not a scenario.

    Eight of the nine modified requirements move one literal, the GitHub
    Environment's name, and that literal is read from a declaration by
    assertions this suite already carries. This class reads what those cannot:
    every other committed file.
    """

    def setUp(self) -> None:
        try:
            self.files = committed_text()
        except TrackedFilesUnavailable as unavailable:
            self.fail(str(unavailable))

    def test_the_sweep_reaches_the_files_the_rename_moves(self) -> None:
        """DERIVED -- no scenario states it. The assertion below is normative
        over every tracked file outside the exemptions, and a listing that
        reached none of them would pass it having read nothing. Anchored on one
        file per surface the change edits rather than on a count, which any
        commit would move."""
        missing = sorted(set(SWEEP_ANCHORS) - set(self.files))
        self.assertEqual(
            [],
            missing,
            f"the tracked-file listing did not reach {missing}, so this sweep passes "
            "over the documents whose prose is the whole reason it exists",
        )
        unswept = sorted(name for name in SWEEP_ANCHORS if not swept(name))
        self.assertEqual(
            [],
            unswept,
            f"{unswept} are exempt from the sweep, so they are listed as anchors and "
            "read by nothing",
        )

    def test_every_exemption_names_something_the_repository_has(self) -> None:
        """DERIVED -- no scenario states it. An exemption is a hole, and one
        that no longer covers anything is a hole kept open for a reason that has
        gone. Checked against the listing rather than the filesystem, so it
        reports a path that stopped being tracked as well as one that was
        deleted."""
        for prefix in EXEMPT_PREFIXES:
            with self.subTest(exemption=prefix):
                self.assertTrue(
                    any(path.startswith(prefix) for path in self.files),
                    f"no tracked file lies under {prefix!r}, so this exemption covers "
                    "nothing and should go rather than stand as a hole",
                )
        for path in EXEMPT_PATHS:
            with self.subTest(exemption=path):
                self.assertIn(
                    path,
                    self.files,
                    f"{path!r} is exempt from the sweep and is not tracked, so this "
                    "exemption covers nothing",
                )
                # A WHOLE-PATH EXEMPTION MUST STILL BE EARNING ITS KEEP, which a
                # prefix exemption cannot be held to: `openspec/changes/` and
                # `.github/tests/` cover many files and will always hold one,
                # while `docs/change-queue.md` is exempt for a single entry that
                # is deleted when its change archives. Requiring the file to
                # still CONTAIN a retired name makes the exemption self-
                # retiring: the archive commit that deletes the entry turns this
                # red, and the repair is to delete the exemption with it rather
                # than to leave a hole with nothing behind it.
                # Scanned directly rather than through `retired_name_offences`,
                # which drops an exempt path by construction and would therefore
                # return nothing here whatever the file said -- an assertion
                # that cannot fail, which is the shape this class exists against.
                text = self.files[path]
                still_named = sorted(name for name in RETIRED_NAMES if name in text)
                self.assertTrue(
                    still_named,
                    f"{path!r} is exempt from the sweep and no longer names any "
                    "retired external service, so the exemption has outlived what it "
                    "was for -- delete it rather than keeping the hole open",
                )

    def test_no_swept_file_names_a_retired_external_name(self) -> None:
        """DERIVED -- this change's tasks.md 3.2. The four names are the two
        retired HCP workspaces and the two retired read-only repository secrets.

        Red until the change lands, on every file its tasks.md sections 4 and 5
        name. That is this assertion working: it is the only mechanism in the
        repository that reports a document the sweep missed, and its failure
        list is that sweep's own worklist.
        """
        offences = retired_name_offences(self.files)
        self.assertEqual(
            [],
            offences,
            "these committed files still name an external service this repository "
            "has retired -- a workspace, a repository secret or a Hetzner project "
            "that no longer answers to the name written here, so an operator "
            "following the text reaches nothing: "
            + "; ".join(offences)
            + ". The replacements are "
            + ", ".join(f"{old} -> {new}" for old, new in sorted(REPLACEMENTS.items())),
        )


# --------------------------------------------------------------------------
# iac-platform-deploy-pipeline / Gated Deploy Reuses the Terraform Production
# Environment
#
# The one obligation in these deltas that IS a static read of committed files
# and that nothing in this suite reads yet. Everything else the deltas say about
# the Environment -- that it requires a reviewer, that it holds the deploy key,
# that a pending job cannot read it -- is a repository setting.
# --------------------------------------------------------------------------


def gated_environments(workflow: dict) -> list[str]:
    """Every GitHub Environment a workflow's jobs declare, in workflow order,
    read in both the scalar and the mapping form the schema permits.

    Takes the parsed workflow rather than reading the committed one, so the
    class at the end of this file can hand it the mapping form. The committed
    workflow uses the scalar, so a reader that read only its own file would
    leave the mapping branch unexecuted -- and that branch's failure mode is the
    one this read exists to distinguish: it returns nothing, and nothing is also
    what a genuinely removed gate returns.
    """
    found = []
    for job in jobs(workflow).values():
        declared = job.get("environment")
        if isinstance(declared, dict):
            declared = declared.get("name")
        if declared:
            found.append(str(declared))
    return found


def platform_deploy_gated_environments() -> list[str]:
    """`gated_environments` over the committed `platform-deploy.yml`."""
    return gated_environments(load_yaml(PLATFORM_DEPLOY))


def declared_github_environments() -> dict[str, str]:
    """Each stack directory and the GitHub Environment its own `pipeline.yml`
    declares."""
    return {
        name: declaration.github_environment
        for name, declaration in environment_declarations().items()
        if declaration.github_environment
    }


def gate_disagreements(gated, declared) -> list[str]:
    """Why the platform deploy's gate and the stacks' declarations do not name
    one Environment, as messages; empty where they do.

    Takes both sides as arguments rather than reading them, so that the
    discriminator below can hand it a half-renamed pair. Over the committed
    tree the two agree today and must agree again afterwards -- what this
    catches is the interval between, which is one commit wide and which the
    change's own proposal calls the more dangerous of its two windows: GitHub
    CREATES an Environment a workflow names, with no protection rules, so a
    deploy gated on a name no stack declares runs unreviewed rather than
    failing.
    """
    offences = []
    names = sorted(set(gated))
    if len(names) != 1:
        offences.append(
            f"platform-deploy.yml declares {names or 'no'} deployment environment(s); "
            "the requirement names one, reused from the Terraform apply workflow"
        )
        return offences
    name = names[0]
    owners = sorted(stack for stack, environment in declared.items() if environment == name)
    if not owners:
        offences.append(
            f"platform-deploy.yml gates its deploy on the {name!r} Environment and no "
            f"stack declares it -- the stacks declare {sorted(set(declared.values()))}. "
            "GitHub creates an Environment a workflow names, with no protection rules, "
            "so this deploy is gated on nothing rather than refused"
        )
    elif len(owners) > 1:
        offences.append(
            f"{owners} all declare the {name!r} Environment, so which stack's apply "
            "the deploy shares its approvers with is not readable from the committed "
            "files"
        )
    return offences


class TestTheDeployGateNamesTheEnvironmentAStackDeclares(unittest.TestCase):
    """SPECIFIED -- Gated Deploy Reuses the Terraform Production Environment
    (openspec/specs/iac-platform-deploy-pipeline/spec.md): "SHALL require manual
    approval via the same GitHub Environment protection rule already used by the
    Terraform apply workflow for the production stack -- the Environment that
    stack's own committed pipeline declaration names, which is
    `main-production`", and its scenario "Same approvers gate both kinds of
    production change": "both SHALL be gated by the same `main-production`
    Environment's required reviewers, rather than each defining its own separate
    approval list".

    ASSERTED AGAINST THE STANDING REQUIREMENT, not against a delta. This class
    arrived with rename-the-external-services, which drafted a delta moving that
    literal to `main-production` and withdrew it, GitHub offering no way to
    rename a deployment Environment. `rename-the-github-environments` made the
    move the only way GitHub allows -- creating the Environment and re-entering
    every secret -- and the quotations above follow the requirement text as that
    change left it. The quotation is the thing to keep current here: it is
    correct when written, correct when reviewed, and wrong only once a later
    change edits the requirement it quotes.

    Written as an EQUALITY between two committed files rather than against any
    literal, deliberately, and that is what let it survive the rename unedited.
    Whether the Environment requires a reviewer is a repository setting no
    static read can reach, so a literal would assert only that a name was typed
    twice -- while this reports the failure a rename actually risks:
    `platform-deploy.yml` and a stack's `pipeline.yml` moving in different
    commits, or one of them not moving at all. Nothing read the two as the same
    Environment before this.

    `test_ci_configuration.py`'s
    `TestAProposedImageUpdateIsNotExemptFromTheStacksObligations
    .test_the_stack_deploy_stays_gated_on_the_production_environment` already
    asserts that exactly one job in that workflow declares the Environment
    `GATED_DEPLOY_ENVIRONMENT` names, and this does not restate it: that
    constant and the one prod's declaration is read against are separate
    literals in separate modules, and nothing until now read them as the same
    Environment.
    """

    def test_the_deploy_gate_and_a_stacks_declaration_name_one_environment(self) -> None:
        """SPECIFIED -- see the class docstring."""
        declared = declared_github_environments()
        self.assertTrue(
            declared,
            "no stack declares a GitHub Environment, so this comparison would read "
            "one side of it",
        )
        offences = gate_disagreements(platform_deploy_gated_environments(), declared)
        self.assertEqual([], offences, "; ".join(offences))


# --------------------------------------------------------------------------
# The reads above are reads
# --------------------------------------------------------------------------


class TestTheseReadsDiscriminate(unittest.TestCase):
    """Every read in this file is a static read of a committed file, so a green
    run establishes nothing on its own: a finder that reported no offence
    whatever it was given would satisfy the assertions above, and would do so
    most convincingly on the day the sweep was finished.

    Each test below hands the finder a corpus built to falsify it. The corpus is
    a mapping this file supplies, not a tree on disk -- which is also what keeps
    these fixtures out of the sweep's own reach, since nothing here is a
    committed file naming a retired service.
    """

    def test_a_swept_file_naming_a_retired_name_is_reported(self) -> None:
        for name in RETIRED_NAMES:
            with self.subTest(name=name):
                offences = retired_name_offences({"docs/runbook.md": f"set {name} first\n"})
                self.assertEqual(["docs/runbook.md:1: " + name], offences)

    def test_the_line_reported_is_the_line_the_name_is_on(self) -> None:
        """A message pointing at the wrong line sends the reader to the wrong
        paragraph of a runbook, which is where most of these names are."""
        corpus = {"docs/runbook.md": "one\ntwo\nthree HCLOUD_TOKEN_STAGING\nfour\n"}
        self.assertEqual(
            ["docs/runbook.md:3: HCLOUD_TOKEN_STAGING"], retired_name_offences(corpus)
        )

    def test_a_clean_corpus_reports_nothing(self) -> None:
        """Without this, a finder reporting every line would satisfy the
        subTests above while making the sweep unfailable in the other
        direction."""
        self.assertEqual(
            [],
            retired_name_offences(
                {
                    "README.md": "the read-only tokens and the two workspaces\n",
                    "docs/runbook.md": "rename the project in the console\n",
                }
            ),
        )

    def test_the_new_names_are_not_read_as_their_own_predecessors(self) -> None:
        """The trap this substring match could have fallen into, and the reason
        `HCLOUD_TOKEN_MAIN_PRODUCTION` was chosen over a shorter form: a needle
        that were a substring of its replacement would keep the sweep red
        forever, on the very text the change writes."""
        corpus = {
            "README.md": (
                "export HCLOUD_TOKEN_MAIN_PRODUCTION=...\n"
                "export HCLOUD_TOKEN_MAIN_STAGING=...\n"
                "workspaces main-production and main-staging\n"
            )
        }
        self.assertEqual([], retired_name_offences(corpus))

    def test_an_exempt_path_naming_a_retired_name_is_not_reported(self) -> None:
        """The two change-record paths are ASSEMBLED at run time rather than
        written as literals, for the same reason `test_ci_configuration.py`
        assembles its own: this file is a committed file outside `openspec/`,
        so a literal naming a change's own directory would be reported by
        `TestNoCommittedFileOutsideOpenSpecCarriesAPreArchiveCitation` -- the
        check that keeps a citation from breaking on the day its change is
        archived. It read this file and said so.
        """
        for path in (
            CHANGE_PATH_PREFIX + ARCHIVE_SEGMENT + "/2026-01-01-something/proposal.md",
            CHANGE_PATH_PREFIX + "some-change-in-flight" + "/tasks.md",
            ".github/tests/test_the_external_service_names_are_retired.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    [], retired_name_offences({path: "infrastructure-prod\n"})
                )

        # `docs/change-queue.md` was the fourth case here until its exemption
        # expired with entry 63. It is swept now, and is asserted as swept rather
        # than dropped from this class: a path that stops being exempt and is
        # merely deleted from the list leaves nothing saying which way it goes.
        self.assertEqual(
            ["docs/change-queue.md:1: infrastructure-prod"],
            retired_name_offences({"docs/change-queue.md": "infrastructure-prod\n"}),
        )

    def test_a_path_merely_resembling_an_exempt_one_is_still_swept(self) -> None:
        """The exemptions are prefixes and whole paths, so a file whose name
        merely begins the same way must not inherit one. `openspec/specs/` is
        the case that matters: no requirement names these values today, and a
        sweep that had quietly exempted the specification tree would not say so
        if one started to."""
        for path in (
            "openspec/specs/iac-state-management/spec.md",
            "openspec/changes-are-not-a-file.md",
            ".github/workflows/apply.yml",
            "docs/change-queue-notes.md",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    ["%s:1: infrastructure-prod" % path],
                    retired_name_offences({path: "infrastructure-prod\n"}),
                )

    def test_every_occurrence_is_reported_rather_than_the_first(self) -> None:
        """A runbook names a secret in a table, in a command and in the prose
        beside both. Reporting the first would send an author back for the same
        file three times."""
        corpus = {
            "docs/runbook.md": (
                "gh secret set HCLOUD_TOKEN_PRODUCTION\n"
                "and then HCLOUD_TOKEN_STAGING\n"
                "in workspace infrastructure-prod\n"
            )
        }
        self.assertEqual(
            [
                "docs/runbook.md:1: HCLOUD_TOKEN_PRODUCTION",
                "docs/runbook.md:2: HCLOUD_TOKEN_STAGING",
                "docs/runbook.md:3: infrastructure-prod",
            ],
            retired_name_offences(corpus),
        )

    def test_a_file_that_does_not_decode_is_read_rather_than_dropped(self) -> None:
        """`decoded` is what stands between a tracked binary and a listing that
        raises halfway through. A file dropped instead would be a file the
        sweep silently does not cover."""
        text = decoded({"docs/runbook.md": b"\xff\xfe HCLOUD_TOKEN_STAGING\n"})
        self.assertEqual(
            ["docs/runbook.md:1: HCLOUD_TOKEN_STAGING"], retired_name_offences(text)
        )

    def test_a_half_renamed_gate_is_reported(self) -> None:
        """The failure this change actually risks, and the one no existing
        assertion sees: `platform-deploy.yml` moved to the new Environment while
        a stack's `pipeline.yml` still declares the old one, or the reverse."""
        offences = gate_disagreements(
            ["main-production"],
            {"main-production": "production", "main-staging": "staging"},
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn("no stack declares it", offences[0])

    def test_an_agreeing_pair_is_not_reported(self) -> None:
        """Without this, a comparison that refused every input would satisfy the
        test above while making the committed assertion unfailable."""
        self.assertEqual(
            [],
            gate_disagreements(
                ["main-production"],
                {"main-production": "main-production", "main-staging": "main-staging"},
            ),
        )

    def test_a_workflow_gating_on_no_environment_is_reported(self) -> None:
        """A deploy job whose `environment:` was dropped is ungated, and reads
        as agreement to any comparison keyed on the names that ARE declared."""
        offences = gate_disagreements([], {"main-production": "main-production"})
        self.assertEqual(1, len(offences), offences)
        self.assertIn("no deployment environment", offences[0])

    def test_two_stacks_declaring_the_gated_environment_are_reported(self) -> None:
        """`test_environment_agnostic_pipeline` asserts the stacks' declared
        Environments are distinct, so this is that assertion's shadow here --
        kept because this comparison would otherwise pick an owner arbitrarily
        and report agreement."""
        offences = gate_disagreements(
            ["main-production"],
            {"main-production": "main-production", "other": "main-production"},
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn("which stack's apply", offences[0])

    def test_the_workflow_read_finds_the_environment_in_either_form(self) -> None:
        """GitHub accepts `environment: name` and `environment: {name: ...}`,
        and a read that saw only the first would report the second as ungated --
        which is the same message as a gate genuinely removed.

        BOTH FORMS ARE EXERCISED HERE, and only one of them by the committed
        workflow. An earlier version of this test called the committed read
        alone; the mapping branch was then never executed, so the test
        established the scalar form and claimed both. A `url:` on the deploy job
        -- which requires the mapping form -- would have been the first thing to
        find out.
        """
        gated = platform_deploy_gated_environments()
        self.assertEqual(
            1,
            len(gated),
            f"platform-deploy.yml declares {gated} deployment environment(s); the read "
            "above is what the comparison is given, and a read returning nothing "
            "would report the deploy ungated whatever the workflow said",
        )
        self.assertEqual(
            ["main-production"],
            gated_environments({"jobs": {"deploy": {"environment": "main-production"}}}),
            "the scalar form is not read",
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
            "the mapping form is not read, so a gate declared with a `url:` would "
            "report as no gate at all",
        )

    def test_the_reader_refuses_rather_than_reporting_an_empty_tree_clean(self) -> None:
        """`tracked_files` raises where the listing cannot be made, and this
        file must not turn that into a green sweep. Pointed at a directory that
        is no repository."""
        with self.assertRaises(TrackedFilesUnavailable):
            committed_text(ROOT / "does-not-exist")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
