"""Static-assertion tests for a repository that holds more than one environment.

Derived from the delta specs of the OpenSpec change `add-a-staging-environment`,
before any implementation of that change existed -- from that change's delta
specifications at commit `3f992e6`, which is the commit holding the approved
plan. The path those deltas sit at is not written here: a change's artifacts
move when it is archived, and this repository's citation convention is to name
the change and the artifact in prose instead.

The deltas span three capabilities -- `iac-state-management`,
`iac-repo-foundations` and `iac-safety-hardening` -- and each section below
names the requirement it traces to. Every assertion is annotated SPECIFIED (it
traces to SHALL text or to a scenario in a delta spec) or DERIVED (it traces to
that change's `design.md` or `tasks.md` rather than to a scenario). See that
change's `test-plan.md` for the scenario-to-test mapping, the baseline, the
scenarios deliberately left uncovered, and the project questions this file took
an assumption on.

Why this is a sixth file in the suite rather than a section of an existing one
-----------------------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. Nothing here edits, deletes or disables an
existing test. Where a property this change states is already asserted by a
sibling module, this file cites that assertion in `test-plan.md` instead of
restating it -- `test_environment_agnostic_pipeline.py` already runs the
per-environment declaration census, and `test_ci_configuration.py` already
compares the Dependabot `terraform` directory list against the tree.

`TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in
`test_ci_configuration.py` reads every module in this directory, so this file is
held to the no-network, no-credential, no-container, no-Terraform constraint by
that class. It is written to satisfy it: standard library, `yaml` by way of the
sibling helpers, and no spawned command at all.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable by name:
    python3 -m unittest discover --start-directory .github/tests \\
        -k test_no_two_environments_name_the_same_workspace

    # or one class:
    python3 -m unittest discover --start-directory .github/tests \\
        -k TestTheSecondEnvironmentIsDeclared

Run from the repository root, and through `discover` in both forms: it is
discovery that puts `.github/tests` on `sys.path`, which is what makes the
sibling imports below resolve. `python3 -m unittest <module>.<class>.<test>`
from the repository root does not, and fails to import this module.

Which assertions here are red before the implementation, and which are guards
-----------------------------------------------------------------------------
Both kinds are present deliberately, and the distinction matters when reading a
run of this file:

- RED until the change lands -- `TestTheSecondEnvironmentIsDeclared` (there is
  no second environment directory yet) and
  `TestTheWriteCredentialRecordCoversEveryEnvironment` (both records name a
  single environment today).
- GREEN from the moment they are written -- the workspace, module-consumption
  and apply-ordering assertions. Their subject is prod's committed
  configuration and the apply workflow, both of which exist and both of which
  this change deliberately does not modify. A pass is therefore the expected
  result and establishes that what is committed already satisfies the
  generalised requirement; it is NOT an alarm of the "passed before any
  implementation existed" kind, because the target is not absent. What these
  assertions are for is the second environment: each one is written over the
  discovered set, so it acquires a subject the day a directory is added.
- VACUOUS until the change lands --
  `TestNoRecordDescribesAnExistingEnvironmentAsAnticipated` reads the README
  against the set of environment directories that exist, so it says nothing
  today and goes red at the moment the staging directory is added without the
  README being brought with it.

`TestTheseReadsDiscriminate` at the end exists because of the second bullet: a
predicate that returned "no offence" unconditionally would satisfy every guard
above while checking nothing. It runs the same predicates over fixture trees
and text carrying the defects each one names.

What no assertion here establishes
----------------------------------
Nothing in this file reads a repository setting, an HCP Terraform workspace
setting, or the Hetzner Cloud API. Whether a workspace's Execution Mode is
Local, whether a GitHub Environment requires a reviewer, which secrets it
holds, and what a given Hetzner token can reach are all settings or API facts
rather than repository content, and this suite makes no network call. The
change's own design.md Decision 9 names that boundary. A green run here
establishes that the committed files are SHAPED so those settings can be
applied safely, never that they were.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from test_ci_configuration import (
    AGENTS_FILE,
    APPLY,
    README,
    ROOT,
    flattened,
    load_yaml,
    read_text,
    uncommented,
)
from test_environment_agnostic_pipeline import (
    TERRAFORM_APPLY,
    environment_declarations,
    environment_directories,
    jobs_running,
)

MODULES_DIR = ROOT / "terraform" / "modules"
PLATFORM_COMPOSE = ROOT / "platform" / "docker-compose.yml"

# The second environment this change adds, and the three values its declaration
# and its workspace name are asserted against.
#
# THESE FOUR LITERALS ARE DERIVED, not specified. No scenario in any delta names
# an environment called `staging`: the delta specs are written over "every
# environment" throughout, which is the whole point of them. The name and the
# three values come from the change's own tasks.md 2.1 and 2.4 and design.md
# Decision 4, and they are asserted here so that the implementing author has a
# red-to-green target and so that the collision assertions below stop being
# vacuous over a set of one.
#
# The consequence worth stating rather than discovering: if staging is ever
# decommissioned by removing its directory -- which design.md's Rollback names
# as a legitimate path -- this class fails, and the correct response is to
# delete it as a change of its own, not to weaken it.
SECOND_ENVIRONMENT = "staging"
SECOND_ENVIRONMENT_READ_ONLY_SECRET = "HCLOUD_TOKEN_STAGING"
SECOND_ENVIRONMENT_GITHUB_ENVIRONMENT = "staging"
SECOND_ENVIRONMENT_DESTROY_GATE = False

# The workspace name form. This one IS specified: "Each environment SHALL have a
# workspace of its own, named `infrastructure-<environment>`" (Remote State
# Backend). `<environment>` is resolved to the environment directory's own name,
# which is the only identifier this repository gives an environment that a
# static read can reach -- prod's committed `infrastructure-prod` is what fixes
# that reading.
WORKSPACE_FORM = "infrastructure-{environment}"

# --------------------------------------------------------------------------
# Reading an environment's Terraform configuration
#
# Regex rather than an HCL parser, for the reason this suite is regex-heavy
# throughout: no HCL parser is pinned in `.github/requirements-ci.txt`, and
# adding one to read four lines out of a `terraform {}` block would be a
# dependency this suite's own "standard library and pinned dependencies"
# requirement then has to carry.
# --------------------------------------------------------------------------

CLOUD_BLOCK = re.compile(r"\bcloud\s*\{", re.MULTILINE)
CLOUD_WORKSPACE = re.compile(
    r"\bcloud\s*\{.*?\bworkspaces\s*\{.*?\bname\s*=\s*\"([^\"]+)\"", re.DOTALL
)
LOCAL_BACKEND = re.compile(r"\bbackend\s+\"local\"", re.MULTILINE)
MODULE_BLOCK = re.compile(r"^module\s+\"([^\"]+)\"\s*\{(.*?)^\}", re.DOTALL | re.MULTILINE)
MODULE_SOURCE = re.compile(r"^\s*source\s*=\s*\"([^\"]+)\"", re.MULTILINE)
MODULE_VERSION = re.compile(r"^\s*version\s*=\s*\"([^\"]+)\"", re.MULTILINE)
TFVARS_ASSIGNMENT = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\"([^\"]*)\"", re.MULTILINE)
MOUNTED_VOLUME_PATH = re.compile(r"/mnt/([A-Za-z0-9][A-Za-z0-9._-]*)/")


def terraform_source(directory: Path) -> str:
    """Every `.tf` file in an environment directory, with comments dropped.

    Comments are dropped because prod's own `versions.tf` explains the
    workspace in a comment that names it -- a text read that kept comments
    would find `infrastructure-prod` in a sentence about the HCP console and
    report it as the configured workspace. `uncommented` is the sibling
    helper, which drops whole-line `#` comments; Terraform also accepts `//`,
    so those lines are dropped here too.
    """
    kept = []
    for path in sorted(directory.glob("*.tf")):
        for line in uncommented(path.read_text(encoding="utf-8")).splitlines():
            if line.lstrip().startswith("//"):
                continue
            kept.append(line)
    return "\n".join(kept)


class Backend:
    """What one environment's committed configuration says about its state."""

    def __init__(self, name: str, source: str):
        self.name = name
        self.declares_cloud_block = bool(CLOUD_BLOCK.search(source))
        self.declares_local_backend = bool(LOCAL_BACKEND.search(source))
        match = CLOUD_WORKSPACE.search(source)
        self.workspace: str | None = match.group(1) if match else None


def environment_backends(root: Path | None = None) -> dict[str, Backend]:
    """Every environment directory mapped to what its `.tf` files configure."""
    return {
        directory.name: Backend(directory.name, terraform_source(directory))
        for directory in environment_directories(root)
    }


def module_calls(directory: Path) -> list[tuple[str, str | None, str | None]]:
    """(block name, `source`, `version`) for each `module` block in a directory."""
    found = []
    for name, body in MODULE_BLOCK.findall(terraform_source(directory)):
        source = MODULE_SOURCE.search(body)
        version = MODULE_VERSION.search(body)
        found.append(
            (name, source.group(1) if source else None, version.group(1) if version else None)
        )
    return found


def tfvars_strings(directory: Path) -> dict[str, str]:
    """The quoted scalar assignments in an environment's `terraform.tfvars`.

    Only the string-valued ones, and only the top-level ones: what is read from
    here is a resource name, never a list or a number.
    """
    path = directory / "terraform.tfvars"
    if not path.is_file():
        return {}
    return dict(TFVARS_ASSIGNMENT.findall(uncommented(path.read_text(encoding="utf-8"))))


def hardcoded_volume_mount_names(text: str) -> set[str]:
    """The volume names a host-side path in `text` hardcodes, as `/mnt/<name>/`."""
    return set(MOUNTED_VOLUME_PATH.findall(text))


# --------------------------------------------------------------------------
# Reading the two records the write-credential prohibition lives in
# --------------------------------------------------------------------------

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

# The prohibition, located by the words each record states it in. AGENTS.md's
# two fragments are the ones `test_environment_agnostic_pipeline.py` already
# matches on, reused rather than re-invented so the two modules cannot drift
# into looking for different sentences.
AGENTS_PROHIBITION_ANCHORS = ("is never run locally", "only through the gated")

# The README states the same prohibition in its own words. Its sentences are
# selected by the token the prohibition is ABOUT together with a word that makes
# the sentence a prohibition -- the README also mentions the Read & Write token
# descriptively, when listing what a new environment's GitHub Environment holds,
# and that sentence is not a statement of the boundary.
README_TOKEN_ANCHOR = "read & write"
README_PROHIBITION_MARKERS = ("never", "exclusively", "only")

# A phrase by which a sentence generalises over environments instead of naming
# one. The list is deliberately generous: the assertion below is that a
# prohibition sentence naming an environment ALSO generalises, so a phrase
# missing from this list produces a false offence, and the repair for a false
# offence is to loosen an assertion -- the repair this suite must never need.
GENERIC_ENVIRONMENT_MARKERS = (
    "every environment",
    "each environment",
    "any environment",
    "no environment",
    "that environment",
    "an environment",
    "per environment",
    "environment directory",
    "one environment",
    "the environment",
)

# `terraform/stacks/` with no name after it -- `terraform/stacks/*/`
# and the bare directory both read as generalising, `terraform/stacks/prod/`
# does not.
BARE_ENVIRONMENTS_PATH = re.compile(r"terraform/stacks/(?![A-Za-z0-9_-])")

# Words by which a record describes an environment as not existing yet. Kept
# narrow on purpose: "anticipated" alone would flag a sentence anticipating
# something else about an environment that does exist.
ANTICIPATION_MARKERS = (
    "not yet",
    "still anticipated",
    "anticipated near-term",
    "anticipated as the next",
    "does not exist yet",
    "is not in scope",
)


def prose_sentences(text: str) -> list[str]:
    """`text` as sentences, with Markdown headings dropped.

    Paragraph by paragraph rather than over the whole file, and headings
    dropped rather than flattened in: a heading carries no terminating
    punctuation, so a whole-file flatten glues "### Production changes never
    bypass the pipeline" onto the sentence beneath it and every assertion about
    that sentence then reads a word from the heading as part of it.
    """
    found = []
    for paragraph in re.split(r"\n\s*\n", text):
        lines = [line for line in paragraph.splitlines() if not line.lstrip().startswith("#")]
        flat = flattened("\n".join(lines))
        if not flat:
            continue
        found.extend(sentence.strip() for sentence in SENTENCE_BOUNDARY.split(flat) if sentence.strip())
    return found


def environment_identifiers(root: Path | None = None) -> set[str]:
    """Every word that names one environment and not the others.

    Both spellings an environment is referred to by: its directory name, and
    the GitHub Environment its declaration names. Prod is `prod` in a path and
    `production` in a secret store, and a record naming either one has named a
    single environment.
    """
    names = {directory.name for directory in environment_directories(root)}
    for declaration in environment_declarations(root).values():
        if declaration.github_environment:
            names.add(declaration.github_environment)
    return names


def environments_named_in(sentence: str, identifiers: set[str]) -> set[str]:
    lowered = sentence.lower()
    return {
        name
        for name in identifiers
        if re.search(rf"\b{re.escape(name.lower())}\b", lowered)
    }


def generalises_over_environments(sentence: str) -> bool:
    lowered = sentence.lower()
    if BARE_ENVIRONMENTS_PATH.search(lowered):
        return True
    return any(marker in lowered for marker in GENERIC_ENVIRONMENT_MARKERS)


def narrowed_to_named_environments(sentence: str, identifiers: set[str]) -> set[str]:
    """The environments a sentence names WHILE generalising over none.

    The empty set means the sentence covers every environment: either it names
    none, or it names one alongside a phrase that reaches the rest. A non-empty
    set is a sentence whose subject is those environments and no others.
    """
    named = environments_named_in(sentence, identifiers)
    if not named or generalises_over_environments(sentence):
        return set()
    return named


def prohibition_sentences_in_agents(text: str) -> list[str]:
    return [
        sentence
        for sentence in prose_sentences(text)
        if any(anchor in sentence.lower() for anchor in AGENTS_PROHIBITION_ANCHORS)
    ]


def prohibition_sentences_in_readme(text: str) -> list[str]:
    found = []
    for sentence in prose_sentences(text):
        lowered = sentence.lower()
        if README_TOKEN_ANCHOR not in lowered:
            continue
        if any(marker in lowered for marker in README_PROHIBITION_MARKERS):
            found.append(sentence)
    return found


# --------------------------------------------------------------------------
# iac-state-management / Remote State Backend
# --------------------------------------------------------------------------


class TestEachEnvironmentHasAWorkspaceOfItsOwn(unittest.TestCase):
    """MODIFIED requirement: Remote State Backend (iac-state-management).

    "Terraform state for **every** environment SHALL be stored remotely in HCP
    Terraform ... Each environment SHALL have a workspace of its own, named
    `infrastructure-<environment>`, and no two environments SHALL share one."

    The requirement's own prose says the uniqueness of a workspace name "is a
    property of the HCP Terraform organization" that no file in this repository
    can detect. That is true of the ORGANIZATION -- a workspace this repository
    never names could still collide there. What IS a static read, and what these
    assertions cover, is the other half: that no two environments COMMITTED here
    name one workspace, which is the collision the requirement describes the
    consequence of (each apply reading the other's resources as its own).
    """

    def setUp(self) -> None:
        self.backends = environment_backends()

    def test_the_repository_has_an_environment_to_read(self) -> None:
        """SPECIFIED -- guards every assertion below from passing over an empty
        set. A sweep of no directories reports no offence."""
        self.assertTrue(
            self.backends,
            "no environment directory was discovered under terraform/stacks/, so "
            "every assertion in this class would pass having read nothing",
        )

    def test_every_environment_configures_an_hcp_workspace_as_its_backend(self) -> None:
        """SPECIFIED -- scenario "State is not stored locally": "Terraform SHALL
        configure that environment's own HCP Terraform workspace as the
        backend"."""
        self.test_the_repository_has_an_environment_to_read()
        offenders = sorted(
            name
            for name, backend in self.backends.items()
            if not backend.declares_cloud_block or backend.workspace is None
        )
        self.assertEqual(
            [],
            offenders,
            "these environment directories declare no `cloud` block naming a workspace, "
            f"so their state has no configured remote home: {offenders}",
        )

    def test_no_environment_configures_a_local_backend(self) -> None:
        """SPECIFIED -- same scenario, its second half: state is stored
        remotely "rather than as a local state file"."""
        self.test_the_repository_has_an_environment_to_read()
        offenders = sorted(
            name for name, backend in self.backends.items() if backend.declares_local_backend
        )
        self.assertEqual(
            [],
            offenders,
            f"these environment directories declare a local backend: {offenders}",
        )

    def test_no_environment_directory_holds_a_state_file(self) -> None:
        """SPECIFIED -- same scenario: "no persistent `.tfstate` file SHALL be
        written to the local filesystem or committed to git".

        Read as the presence of the file rather than as a `git ls-files` call:
        this suite spawns no command, and a `.tfstate` sitting in an environment
        directory is the offence whether or not it has been staged.

        `.terraform/` is excluded, and the exclusion is a correction rather than
        a concession. `terraform init` against a `cloud` backend writes
        `.terraform/terraform.tfstate` in every environment directory it
        initialises: that file holds `{version, terraform_version, backend}` and
        no `resources` key at all -- it is the backend configuration cache, which
        carries the name for historical reasons and is not state. Without this
        exclusion the assertion fails on any machine that has run the `terraform
        init` this repository's own README prescribes, which is a defect in the
        check rather than a finding about the tree. It first fired on
        `add-a-staging-environment`'s own first real init.

        What it still catches is the whole offence: a local-backend
        `terraform.tfstate` or `terraform.tfstate.backup` written at an
        environment directory's root, which is where real state lands, at any
        depth other than the initialisation cache. The companion assertions cover
        the rest -- one reads the backend declaration, the other reads
        `.gitignore`.
        """
        offenders = sorted(
            str(path.relative_to(ROOT))
            for directory in environment_directories()
            for path in directory.rglob("*.tfstate*")
            if ".terraform" not in path.relative_to(directory).parts
        )
        self.assertEqual(
            [],
            offenders,
            f"these state files sit inside an environment directory: {offenders}",
        )

    def test_the_state_exclusion_is_recorded_in_gitignore(self) -> None:
        """SPECIFIED -- same scenario: no `.tfstate` is "committed to git". The
        assertion above reads the tree as it stands; this reads the rule that
        keeps it that way, so a state file produced tomorrow is untrackable
        rather than merely absent today."""
        patterns = {
            line.strip()
            for line in read_text(ROOT / ".gitignore").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertIn(
            "*.tfstate",
            patterns,
            ".gitignore does not exclude `*.tfstate`, so a local state file produced by "
            "an environment whose backend is misconfigured would be committable",
        )

    def test_every_workspace_name_follows_the_per_environment_form(self) -> None:
        """SPECIFIED -- "Each environment SHALL have a workspace of its own,
        named `infrastructure-<environment>`"."""
        self.test_every_environment_configures_an_hcp_workspace_as_its_backend()
        offenders = sorted(
            f"{name} -> {backend.workspace!r}"
            for name, backend in self.backends.items()
            if backend.workspace != WORKSPACE_FORM.format(environment=name)
        )
        self.assertEqual(
            [],
            offenders,
            "these environments name a workspace that is not "
            f"{WORKSPACE_FORM.format(environment='<environment>')!r}: {offenders}",
        )

    def test_no_two_environments_name_the_same_workspace(self) -> None:
        """SPECIFIED -- scenario "Two environments do not share a workspace":
        an environment's configuration "SHALL name a workspace no other
        environment names, so that its state is separate from every other
        environment's".

        At one environment this comparison has nothing to compare, which is why
        `TestTheseReadsDiscriminate` runs the same read over a two-environment
        fixture. This assertion is what carries it into the committed tree once
        there is a second environment.
        """
        self.test_the_repository_has_an_environment_to_read()
        by_workspace: dict[str, list[str]] = {}
        for name, backend in sorted(self.backends.items()):
            if backend.workspace:
                by_workspace.setdefault(backend.workspace, []).append(name)
        offenders = sorted(
            f"{', '.join(names)} all name {workspace!r}"
            for workspace, names in by_workspace.items()
            if len(names) > 1
        )
        self.assertEqual(
            [],
            offenders,
            "a workspace holds one state, so these environments would each read the "
            f"other's resources as their own and plan them for destruction: {offenders}",
        )


# --------------------------------------------------------------------------
# iac-state-management / Each Environment Has a Dedicated Hetzner Cloud Project
# --------------------------------------------------------------------------


class TestIdenticalResourceNamesAcrossEnvironmentsAreKept(unittest.TestCase):
    """ADDED requirement: Each Environment Has a Dedicated Hetzner Cloud
    Project (iac-state-management).

    "Resource names are unique per project rather than globally, so
    environments in separate projects MAY carry identically named resources ...
    it lets every environment use the same volume name, and therefore the same
    on-host mount path, so host-side configuration that hardcodes a path stays
    correct across environments instead of needing a per-environment value."

    The requirement's two other scenarios -- that one environment's token
    cannot reach another's project, and that an ungated environment's write
    token cannot touch a reviewed one's resources -- are facts about a Hetzner
    API token and a GitHub Environment's protection rules. Neither is a
    committed file and neither is reachable without a network call; both are
    recorded in this change's test-plan.md as beyond every test command this
    project has.

    What is a static read is the consequence stated above, and this is the file
    it is a consequence FOR: `platform/docker-compose.yml` bind-mounts an
    absolute host path, so an environment that named its volume anything else
    would bring Prometheus and Grafana up writing to a path that does not
    exist -- silently, which is what makes it worth an assertion rather than a
    note.
    """

    def setUp(self) -> None:
        self.volume_names = {
            directory.name: tfvars_strings(directory).get("volume_name")
            for directory in environment_directories()
        }
        self.declared = {
            name: value for name, value in self.volume_names.items() if value is not None
        }

    def test_the_platform_stack_hardcodes_exactly_one_volume_mount_name(self) -> None:
        """DERIVED -- design.md Decision 1 and Decision 4 state that the shared
        volume name is what keeps the hardcoded mount path correct. No scenario
        states the path; this locates it, and guards the assertion below from
        comparing against nothing."""
        mounted = hardcoded_volume_mount_names(read_text(PLATFORM_COMPOSE))
        self.assertEqual(
            1,
            len(mounted),
            "platform/docker-compose.yml hardcodes host paths under more than one "
            f"volume name, so there is no single name for an environment to match: "
            f"{sorted(mounted)}",
        )

    def test_every_environment_that_declares_a_volume_names_it_identically(self) -> None:
        """DERIVED -- no scenario states a value. The scenario states that two
        environments MAY name a resource identically; design.md Decision 4 and
        tasks.md 2.3 state that staging DOES, `volume_name = "main-data"`, and
        that this is what keeps `platform/docker-compose.yml` unparameterised.

        Recorded as derived because it is stronger than the scenario: the
        scenario permits a shared name, this requires one. It is asserted
        rather than left to review because the failure it catches is silent --
        a differently named volume plans, applies and mounts, and only the
        containers that expected the old path notice.

        An environment declaring no volume at all is not an offence; it is an
        environment with nothing to name.
        """
        self.test_the_platform_stack_hardcodes_exactly_one_volume_mount_name()
        mounted = hardcoded_volume_mount_names(read_text(PLATFORM_COMPOSE)).pop()
        offenders = sorted(
            f"{name} -> {value!r}"
            for name, value in self.declared.items()
            if value != mounted
        )
        self.assertEqual(
            [],
            offenders,
            f"platform/docker-compose.yml bind-mounts /mnt/{mounted}/..., so these "
            f"environments would mount their volume somewhere nothing reads: {offenders}",
        )


# --------------------------------------------------------------------------
# iac-repo-foundations / Environment and Module Folder Structure
# --------------------------------------------------------------------------


class TestEveryEnvironmentConsumesTheSharedModules(unittest.TestCase):
    """MODIFIED requirement: Environment and Module Folder Structure
    (iac-repo-foundations).

    "Environments consume modules by relative path, which means every
    environment runs the same module code as of the merged commit -- there is
    no per-environment module version pinning, and none SHALL be introduced to
    obtain promotion ordering."

    The scenario "Adding a future environment does not require restructuring"
    also says "without moving or renaming existing files". That half is a
    property of a diff rather than of a tree, and no single static read of the
    committed files can see it; it is recorded in this change's test-plan.md as
    deliberately untested, with review as the mechanism.
    """

    def setUp(self) -> None:
        self.calls = {
            directory.name: module_calls(directory) for directory in environment_directories()
        }

    def test_every_environment_calls_at_least_one_shared_module(self) -> None:
        """SPECIFIED -- scenario "Prod environment consumes a shared module":
        an environment "SHALL do so by calling a module under
        `terraform/modules/` ... rather than duplicating resource definitions
        inline", and the scenario "Adding a future environment does not require
        restructuring", which states the same of a new folder.

        Written over the discovered set rather than over prod: the delta's
        opening sentence is about the repository's organisation, and an
        environment added later that inlined its resources would satisfy a
        prod-only assertion.
        """
        self.assertTrue(
            self.calls,
            "no environment directory was discovered, so this assertion would pass "
            "having read nothing",
        )
        offenders = sorted(name for name, calls in self.calls.items() if not calls)
        self.assertEqual(
            [],
            offenders,
            "these environment directories call no module, so whatever they define is "
            f"defined inline: {offenders}",
        )

    def test_every_module_call_resolves_to_a_relative_path_under_terraform_modules(self) -> None:
        """SPECIFIED -- "Environments consume modules by relative path, which
        means every environment runs the same module code as of the merged
        commit". A registry or git source would run module code of its own,
        which is the per-environment pinning the next assertion refuses."""
        self.test_every_environment_calls_at_least_one_shared_module()
        offenders = []
        for name, calls in sorted(self.calls.items()):
            directory = ROOT / "terraform" / "stacks" / name
            for block, source, _ in calls:
                if not source:
                    offenders.append(f"{name}.{block}: declares no `source`")
                    continue
                if not source.startswith((".", "..")):
                    offenders.append(f"{name}.{block}: source {source!r} is not a relative path")
                    continue
                resolved = (directory / source).resolve()
                if MODULES_DIR not in resolved.parents and resolved != MODULES_DIR:
                    offenders.append(
                        f"{name}.{block}: source {source!r} resolves outside "
                        f"{MODULES_DIR.relative_to(ROOT)}"
                    )
                elif not resolved.is_dir():
                    offenders.append(f"{name}.{block}: source {source!r} is not a directory")
        self.assertEqual([], offenders, "; ".join(offenders))

    def test_no_environment_pins_a_module_version_of_its_own(self) -> None:
        """SPECIFIED -- "there is no per-environment module version pinning, and
        none SHALL be introduced to obtain promotion ordering", and scenario
        "Adding a future environment does not require restructuring": a new
        environment is added "without pinning a module version of its own"."""
        self.test_every_environment_calls_at_least_one_shared_module()
        offenders = sorted(
            f"{name}.{block} -> {version!r}"
            for name, calls in self.calls.items()
            for block, _, version in calls
            if version is not None
        )
        self.assertEqual(
            [],
            offenders,
            "these module calls pin a version, so this environment would stop running "
            f"the module code of the merged commit: {offenders}",
        )


class TestNoEnvironmentsApplyWaitsOnAnother(unittest.TestCase):
    """MODIFIED requirement: Environment and Module Folder Structure
    (iac-repo-foundations).

    "**Promotion ordering is not a property of the apply workflow.** A merge
    affecting several environments SHALL plan and apply each of them
    independently, each under its own GitHub Environment's protection rules,
    and an environment's apply SHALL NOT be made to depend on another
    environment's apply."

    This is the one place in this file where the modified requirement asks for
    LESS than the workflow already does: the sentence it replaces prescribed
    sequencing, `apply.yml` never implemented it, and these assertions are what
    stop it being introduced. They pass from the moment they are written, and
    the module docstring says why that is the expected result rather than an
    alarm.

    `test_planned_environment_apply_stage.py` asserts the same decoupling
    against the iac-cicd-pipeline requirement that states it for a FAILED plan.
    This states it for ORDER, over the requirement that until this change
    prescribed the opposite -- the two read the same workflow for different
    reasons, and neither is edited by the other.
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(APPLY)
        self.applying = jobs_running(self.workflow, TERRAFORM_APPLY)

    def test_the_workflow_still_applies(self) -> None:
        """SPECIFIED -- guards every assertion below from passing over a
        workflow that no longer applies anything."""
        self.assertTrue(self.applying, "no job in apply.yml runs `terraform apply`")

    def test_no_apply_job_depends_on_another_environments_apply(self) -> None:
        """SPECIFIED -- "an environment's apply SHALL NOT be made to depend on
        another environment's apply", and scenario "A shared module change
        reaches every environment without an imposed order": "neither
        environment's apply SHALL be blocked by the other's outcome"."""
        self.test_the_workflow_still_applies()
        offenders = []
        for name, job in sorted(self.applying.items()):
            needs = job.get("needs") or []
            needs = [needs] if isinstance(needs, str) else list(needs)
            for dependency in needs:
                if dependency in self.applying and dependency != name:
                    offenders.append(f"{name} needs {dependency}, which also applies")
        self.assertEqual(
            [],
            offenders,
            "these apply jobs are sequenced behind another apply, so a failure in one "
            f"environment withholds a correct change from another: {offenders}",
        )

    def test_the_apply_matrix_is_neither_serialised_nor_abandoned_on_a_sibling(self) -> None:
        """SPECIFIED -- same scenario. Two matrix settings would reinstate the
        ordering the requirement removes without any `needs:` edge to read:
        `fail-fast` at its default cancels every sibling row when one fails,
        and `max-parallel: 1` runs the rows in sequence, which is promotion
        ordering by another name and in an order nobody chose."""
        self.test_the_workflow_still_applies()
        offenders = []
        for name, job in sorted(self.applying.items()):
            strategy = job.get("strategy") or {}
            if not strategy.get("matrix"):
                offenders.append(f"{name}: declares no `strategy.matrix`, so it applies one environment")
                continue
            if strategy.get("fail-fast") is not False:
                offenders.append(f"{name}: does not set `fail-fast: false`")
            if strategy.get("max-parallel") == 1:
                offenders.append(f"{name}: sets `max-parallel: 1`, which sequences the environments")
        self.assertEqual([], offenders, "; ".join(offenders))

    def test_every_apply_job_attaches_to_an_environment_resolved_per_row(self) -> None:
        """SPECIFIED -- "each under its own GitHub Environment's protection
        rules", and scenario "Promotion ordering is exercised at the approval,
        not by the workflow": the reviewed environment's approval is where
        ordering is exercised, which requires each row to attach to its OWN
        Environment rather than to one the workflow names.

        This asserts only that the attachment is per row. Whether the
        Environment it resolves to requires a reviewer is a repository setting,
        and the approver's discipline of withholding approval until a lower
        environment has been seen to succeed is a human act -- neither is a
        committed file, and both are recorded as uncovered in this change's
        test-plan.md.
        """
        self.test_the_workflow_still_applies()
        offenders = []
        for name, job in sorted(self.applying.items()):
            declared = job.get("environment")
            declared = declared.get("name", "") if isinstance(declared, dict) else declared
            if not declared:
                offenders.append(f"{name}: declares no `environment:`")
            elif "matrix." not in str(declared):
                offenders.append(
                    f"{name}: attaches to {str(declared)!r}, which does not vary by matrix row"
                )
        self.assertEqual([], offenders, "; ".join(offenders))


# --------------------------------------------------------------------------
# iac-safety-hardening / Write Credentials Confined to the Gated Pipeline
# --------------------------------------------------------------------------


class TestTheWriteCredentialRecordCoversEveryEnvironment(unittest.TestCase):
    """MODIFIED requirement: Write Credentials Confined to the Gated Pipeline
    (iac-safety-hardening).

    "**That record SHALL state the prohibition over every environment rather
    than naming one.** A record naming a single environment is read as silent
    about the others ... and the environment most likely to be omitted is the
    one added last."

    `test_environment_agnostic_pipeline.TestTheWriteCredentialBoundaryIsStatedToAgents`
    already asserts that both records STATE the boundary. Nothing here repeats
    that; what is asserted here is the sentence's SUBJECT, which is what the
    modified requirement adds and what a record written at one environment gets
    wrong by construction.

    Both assertions are red on the committed records today: AGENTS.md states
    the prohibition "against `terraform/stacks/prod/`", and the README
    states that the write token "lives exclusively in the `production` GitHub
    Environment secret". Each names one environment and generalises over none.

    What this does NOT establish: that any token is where the requirement says
    it is. Which secrets a GitHub Environment holds, and what sits on an
    operator's workstation, are neither repository content nor reachable
    without a network call.
    """

    def setUp(self) -> None:
        self.identifiers = environment_identifiers()

    def _assert_each_covers_every_environment(self, record: str, sentences: list[str]) -> None:
        offenders = sorted(
            f"{sorted(narrowed)}: {sentence!r}"
            for sentence in sentences
            for narrowed in [narrowed_to_named_environments(sentence, self.identifiers)]
            if narrowed
        )
        self.assertEqual(
            [],
            offenders,
            f"{record} states the write-credential prohibition over named environments "
            "and generalises over none, so an environment it does not name is one a "
            "reader has been given no reason to treat as confined -- and the one most "
            f"likely to be missing is the one added last: {offenders}",
        )

    def test_the_conventions_file_states_the_prohibition_over_every_environment(self) -> None:
        """SPECIFIED -- scenario "The record covers an environment added after
        it was written": "the README runbook and `AGENTS.md` SHALL already
        state the prohibition in terms that cover it, rather than requiring an
        edit naming it before its write token is treated as confined".

        A sentence naming an environment is an offence only if it generalises
        over none. Prod's reviewer gate is prod's and stays stated as prod's
        (the change's tasks.md 3.2 says so); a sentence saying the prohibition
        holds for every environment and prod is additionally reviewed names
        prod and passes.
        """
        found = prohibition_sentences_in_agents(read_text(AGENTS_FILE))
        self.assertTrue(
            found,
            "AGENTS.md carries no sentence matching "
            f"{AGENTS_PROHIBITION_ANCHORS}, so this assertion has no statement of the "
            "prohibition to read the subject of",
        )
        self._assert_each_covers_every_environment("AGENTS.md", found)

    def test_the_readme_runbook_states_the_prohibition_over_every_environment(self) -> None:
        """SPECIFIED -- same scenario, its README half."""
        found = prohibition_sentences_in_readme(read_text(README))
        self.assertTrue(
            found,
            f"README.md carries no sentence naming the {README_TOKEN_ANCHOR!r} token "
            f"alongside one of {README_PROHIBITION_MARKERS}, so there is no statement "
            "of the prohibition for this assertion to read the subject of",
        )
        self._assert_each_covers_every_environment("README.md", found)


class TestNoRecordDescribesAnExistingEnvironmentAsAnticipated(unittest.TestCase):
    """MODIFIED requirement: Write Credentials Confined to the Gated Pipeline
    (iac-safety-hardening), and the same records the scenario "The record
    covers an environment added after it was written" is about.

    DERIVED throughout -- no scenario states this. It traces to the change's
    tasks.md 3.3, which brings "**both** places the README describes staging as
    anticipated to what is now true".

    It is asserted rather than left to review because of what it guards: the
    scenario above is about a record that has not kept up with the tree, and a
    README still calling an environment anticipated is the same defect in its
    most readable form -- a reader told the environment does not exist has no
    reason to look for its write token at all.

    Vacuous today, on purpose: it reads the README against the environment
    directories that EXIST, and there is one. It acquires its subject at the
    moment the second directory is added.
    """

    def test_no_readme_sentence_calls_an_existing_environment_anticipated(self) -> None:
        """DERIVED -- tasks.md 3.3."""
        identifiers = environment_identifiers()
        offenders = sorted(
            f"{sorted(named)}: {sentence!r}"
            for sentence in prose_sentences(read_text(README))
            if any(marker in sentence.lower() for marker in ANTICIPATION_MARKERS)
            for named in [environments_named_in(sentence, identifiers)]
            if named
        )
        self.assertEqual(
            [],
            offenders,
            "the README describes an environment that exists in "
            "terraform/stacks/ as not yet existing: " + "; ".join(offenders),
        )


# --------------------------------------------------------------------------
# The second environment this change adds
# --------------------------------------------------------------------------


class TestTheSecondEnvironmentIsDeclared(unittest.TestCase):
    """DERIVED throughout -- the change's tasks.md 2.1 and 2.4, and design.md
    Decision 4. No delta scenario names an environment called `staging`; every
    one of them is written over "every environment", which is what the change
    is for.

    This class is here for two reasons that the generalised assertions above
    cannot serve. It is the red-to-green target the implementing author works
    against -- every other assertion in this file is either already green over
    prod or vacuous until a directory appears. And it is what makes the
    collision assertions above non-vacuous: until a second environment is
    committed, "no two environments name the same workspace" compares a set of
    one against itself.

    See the note on `SECOND_ENVIRONMENT` above for what to do with this class
    if staging is ever decommissioned.
    """

    def test_a_second_environment_directory_exists(self) -> None:
        """DERIVED -- proposal.md's What Changes: "A
        `terraform/stacks/staging/` directory calling the same
        `terraform/modules/server` and `terraform/modules/volume` as prod"."""
        names = sorted(directory.name for directory in environment_directories())
        self.assertIn(
            SECOND_ENVIRONMENT,
            names,
            f"terraform/stacks/ holds {names}, and no {SECOND_ENVIRONMENT!r} "
            "directory -- so every collision assertion in this file compares a set of "
            "one against itself",
        )

    def test_the_second_environment_names_its_own_workspace(self) -> None:
        """SPECIFIED as to form -- "named `infrastructure-<environment>`", and
        "no two environments SHALL share one". DERIVED as to which environment
        that is: tasks.md 1.4 and 2.1 name `infrastructure-staging`."""
        self.test_a_second_environment_directory_exists()
        backend = environment_backends()[SECOND_ENVIRONMENT]
        self.assertEqual(
            WORKSPACE_FORM.format(environment=SECOND_ENVIRONMENT),
            backend.workspace,
            f"{SECOND_ENVIRONMENT}'s `cloud` block names {backend.workspace!r}",
        )

    def test_the_second_environment_declares_its_own_secret_and_environment(self) -> None:
        """DERIVED -- tasks.md 2.4: `github_environment: staging`,
        `read_only_secret: HCLOUD_TOKEN_STAGING`.

        That the two must DIFFER from every other environment's is specified,
        and is asserted over the whole tree by
        `test_environment_agnostic_pipeline.TestEveryEnvironmentIsDeclared`.
        What is derived is the two values themselves, which is what task 1.5
        and task 1.6 create outside the repository and what this repository
        must name to reach them.
        """
        self.test_a_second_environment_directory_exists()
        declaration = environment_declarations()[SECOND_ENVIRONMENT]
        self.assertEqual([], declaration.offences, "; ".join(declaration.offences))
        self.assertEqual(
            (
                SECOND_ENVIRONMENT_GITHUB_ENVIRONMENT,
                SECOND_ENVIRONMENT_READ_ONLY_SECRET,
                SECOND_ENVIRONMENT_DESTROY_GATE,
            ),
            (
                declaration.github_environment,
                declaration.read_only_secret,
                declaration.destroy_gate_applies,
            ),
            f"{SECOND_ENVIRONMENT}'s pipeline declaration does not name the GitHub "
            "Environment, the read-only repository secret and the destroy-policy "
            "applicability the change's tasks.md 2.4 states",
        )


# --------------------------------------------------------------------------
# The reads above are reads
# --------------------------------------------------------------------------


class TestTheseReadsDiscriminate(unittest.TestCase):
    """Every assertion above that sweeps the discovered set is green over the
    committed tree from the moment it is written, and most of them will still
    be green over a tree with a second environment in it. A predicate that
    found nothing, returned nothing, or matched nothing would satisfy all of
    them.

    So this class runs the same predicates over fixture trees and fixture text
    carrying the defect each one names -- and over a clean two-environment
    tree, since a predicate that refused everything would satisfy every refusal
    while making a second environment impossible to add.

    DERIVED throughout: no scenario states any of it. It is what stops the
    SPECIFIED assertions above from passing over machinery that reads nothing.
    """

    CLOUD_TEMPLATE = (
        "terraform {{\n"
        "  # the {workspace} workspace, named in a comment\n"
        "  cloud {{\n"
        '    organization = "shatynska"\n'
        "\n"
        "    workspaces {{\n"
        '      name = "{workspace}"\n'
        "    }}\n"
        "  }}\n"
        "}}\n"
    )

    def _scratch(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="second-environment-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        return directory

    def _tree(self, workspaces: dict[str, str], extra: str = "") -> Path:
        scratch = self._scratch()
        for name, workspace in workspaces.items():
            directory = scratch / "terraform" / "stacks" / name
            directory.mkdir(parents=True)
            (directory / "versions.tf").write_text(
                self.CLOUD_TEMPLATE.format(workspace=workspace) + extra, encoding="utf-8"
            )
        return scratch

    def test_the_workspace_read_finds_the_configured_name_not_the_commented_one(self) -> None:
        """DERIVED -- the fixture's comment names the same workspace, so this
        would pass on a text match. Its point is the converse: a comment naming
        a DIFFERENT workspace must not be what the read returns."""
        scratch = self._tree({"prod": "infrastructure-prod"})
        versions = scratch / "terraform" / "stacks" / "prod" / "versions.tf"
        versions.write_text(
            "# set infrastructure-decoy's Execution Mode to Local\n"
            + self.CLOUD_TEMPLATE.format(workspace="infrastructure-prod"),
            encoding="utf-8",
        )
        backends = environment_backends(scratch)
        self.assertEqual({"prod"}, set(backends))
        self.assertEqual("infrastructure-prod", backends["prod"].workspace)
        self.assertTrue(backends["prod"].declares_cloud_block)
        self.assertFalse(backends["prod"].declares_local_backend)

    def test_a_clean_two_environment_tree_yields_two_distinct_workspaces(self) -> None:
        """DERIVED -- the converse the collision assertion needs. A read that
        reported a collision over every tree would satisfy the refusal and make
        a second environment impossible to add."""
        backends = environment_backends(
            self._tree(
                {"prod": "infrastructure-prod", "staging": "infrastructure-staging"}
            )
        )
        self.assertEqual(
            {"prod": "infrastructure-prod", "staging": "infrastructure-staging"},
            {name: backend.workspace for name, backend in backends.items()},
        )

    def test_two_environments_sharing_a_workspace_are_visible_to_the_read(self) -> None:
        """DERIVED -- the defect the scenario "Two environments do not share a
        workspace" names, which at one committed environment cannot occur."""
        backends = environment_backends(
            self._tree({"prod": "infrastructure-prod", "staging": "infrastructure-prod"})
        )
        self.assertEqual(
            ["infrastructure-prod", "infrastructure-prod"],
            [backends[name].workspace for name in sorted(backends)],
        )

    def test_a_missing_cloud_block_and_a_local_backend_are_both_visible(self) -> None:
        """DERIVED -- the two shapes `test_every_environment_configures_an_hcp_
        workspace_as_its_backend` and `test_no_environment_configures_a_local_
        backend` refuse."""
        scratch = self._scratch()
        directory = scratch / "terraform" / "stacks" / "local"
        directory.mkdir(parents=True)
        (directory / "versions.tf").write_text(
            'terraform {\n  backend "local" {\n    path = "terraform.tfstate"\n  }\n}\n',
            encoding="utf-8",
        )
        backend = environment_backends(scratch)["local"]
        self.assertIsNone(backend.workspace)
        self.assertFalse(backend.declares_cloud_block)
        self.assertTrue(backend.declares_local_backend)

    def test_a_pinned_module_version_is_visible_to_the_module_read(self) -> None:
        """DERIVED -- the defect `test_no_environment_pins_a_module_version_of_
        its_own` refuses, which no committed environment carries."""
        scratch = self._scratch()
        directory = scratch / "terraform" / "stacks" / "pinned"
        directory.mkdir(parents=True)
        (directory / "main.tf").write_text(
            'module "server" {\n'
            "  # source = \"../../modules/decoy\"\n"
            '  source  = "../../modules/server"\n'
            '  version = "1.2.3"\n'
            "}\n"
            "\n"
            'module "volume" {\n'
            '  source = "../../modules/volume"\n'
            "}\n",
            encoding="utf-8",
        )
        self.assertEqual(
            [
                ("server", "../../modules/server", "1.2.3"),
                ("volume", "../../modules/volume", None),
            ],
            module_calls(directory),
        )

    def test_a_volume_mount_name_is_read_out_of_a_compose_bind_mount(self) -> None:
        """DERIVED -- what
        `test_every_environment_that_declares_a_volume_names_it_identically`
        compares against."""
        self.assertEqual(
            {"main-data"},
            hardcoded_volume_mount_names(
                "    volumes:\n"
                "      - /mnt/main-data/prometheus:/prometheus\n"
                "      - /mnt/main-data/grafana:/var/lib/grafana\n"
            ),
        )

    def test_a_tfvars_string_assignment_is_read_and_a_comment_is_not(self) -> None:
        """DERIVED -- what the volume-name assertion reads an environment's own
        value out of."""
        scratch = self._scratch()
        directory = scratch / "environment"
        directory.mkdir(parents=True)
        (directory / "terraform.tfvars").write_text(
            '# volume_name = "decoy"\n'
            'name        = "main-server"\n'
            'volume_name = "main-data"\n'
            "volume_size = 10\n",
            encoding="utf-8",
        )
        self.assertEqual(
            {"name": "main-server", "volume_name": "main-data"}, tfvars_strings(directory)
        )

    # ----------------------------------------------------------------------
    # The record predicates
    # ----------------------------------------------------------------------

    IDENTIFIERS = {"prod", "production", "staging"}

    def test_a_prohibition_naming_one_environment_is_an_offence(self) -> None:
        """DERIVED -- the committed AGENTS.md sentence, in the shape that makes
        it one. This is what
        `test_the_conventions_file_states_the_prohibition_over_every_environment`
        is red on today."""
        self.assertEqual(
            {"prod"},
            narrowed_to_named_environments(
                "`terraform apply` is never run locally against "
                "`terraform/stacks/prod/`.",
                self.IDENTIFIERS,
            ),
        )
        self.assertEqual(
            {"production"},
            narrowed_to_named_environments(
                "Never put the **Read & Write** token here or in any other local file "
                "- it lives exclusively in the `production` GitHub Environment secret.",
                self.IDENTIFIERS,
            ),
        )

    def test_a_prohibition_that_generalises_is_not_an_offence(self) -> None:
        """DERIVED -- the converse. A predicate that flagged every sentence
        would be red now and red after the change, which is the same as
        checking nothing."""
        for sentence in (
            "`terraform apply` is never run locally against any environment directory "
            "under `terraform/stacks/`.",
            "Every environment's Read & Write token lives exclusively in that "
            "environment's own GitHub Environment secret, and prod's apply is "
            "additionally held behind a reviewer.",
            "Infrastructure changes reach Hetzner only through the gated pipeline.",
        ):
            with self.subTest(sentence=sentence):
                self.assertEqual(
                    set(), narrowed_to_named_environments(sentence, self.IDENTIFIERS)
                )

    def test_an_environment_name_is_matched_as_a_word_not_a_substring(self) -> None:
        """DERIVED -- `prod` is a substring of `production`, and a substring
        match would report a sentence naming the GitHub Environment as naming
        the directory too, which is two offences for one defect."""
        self.assertEqual(
            {"production"},
            environments_named_in("the `production` Environment secret", self.IDENTIFIERS),
        )
        self.assertEqual(
            {"prod"},
            environments_named_in("terraform/stacks/prod/main.tf", self.IDENTIFIERS),
        )

    def test_a_heading_is_not_glued_onto_the_sentence_beneath_it(self) -> None:
        """DERIVED -- why `prose_sentences` reads paragraph by paragraph. A
        whole-file flatten would put "Production" into the sentence below the
        heading, and every sentence in that section would then name an
        environment it does not mention."""
        sentences = prose_sentences(
            "## Production changes never bypass the pipeline\n"
            "\n"
            "`terraform apply` is never run locally against any environment.\n"
        )
        self.assertEqual(
            ["`terraform apply` is never run locally against any environment."], sentences
        )

    def test_the_two_record_selectors_find_the_prohibition_and_not_its_neighbours(self) -> None:
        """DERIVED -- a selector matching nothing would make both assertions in
        `TestTheWriteCredentialRecordCoversEveryEnvironment` fail on their own
        guard rather than on the record, and a selector matching everything
        would report the README's descriptive mentions as prohibitions."""
        agents = (
            "`terraform apply` is never run locally. Local runs use the read-only "
            "token. Infrastructure changes reach Hetzner only through the gated "
            "pipeline.\n"
        )
        self.assertEqual(2, len(prohibition_sentences_in_agents(agents)))

        readme = (
            "Never put the **Read & Write** token here or in any other local file.\n"
            "\n"
            "- a GitHub Environment of the declared name, holding `HCLOUD_TOKEN` "
            "(that environment's **Read & Write** token) and `TF_API_TOKEN`.\n"
        )
        self.assertEqual(
            ["Never put the **Read & Write** token here or in any other local file."],
            prohibition_sentences_in_readme(readme),
        )

    def test_an_anticipation_sentence_is_found_only_when_it_names_an_environment(self) -> None:
        """DERIVED -- what
        `test_no_readme_sentence_calls_an_existing_environment_anticipated`
        reads. The second sentence anticipates something that is not an
        environment, and must not be reported."""
        named = [
            sentence
            for sentence in prose_sentences(
                "A staging environment is still anticipated as the next environment, "
                "but is not yet in scope.\n"
                "\n"
                "A dedicated monitoring host is not yet warranted.\n"
            )
            if any(marker in sentence.lower() for marker in ANTICIPATION_MARKERS)
            and environments_named_in(sentence, self.IDENTIFIERS)
        ]
        self.assertEqual(1, len(named), named)
        self.assertIn("staging", named[0])


if __name__ == "__main__":
    unittest.main()
