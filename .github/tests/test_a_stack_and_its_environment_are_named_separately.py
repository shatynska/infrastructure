"""Static-assertion tests for a stack's name and its environment's name ceasing
to be one word.

Derived from the delta specs of the OpenSpec change
`rename-the-stacks-and-their-resources`, before any implementation of that
change existed -- from those deltas at commit `b08a71e`, the commit holding the
approved plan. The path those deltas sit at is not written here: a change's
artifacts move when it is archived, and this repository's citation convention is
to name the change and the artifact in prose instead.

Four capabilities are reached below. `iac-cicd-pipeline`'s *Each Stack Declares
Its Own Pipeline Configuration* (ADDED, replacing *Each Environment Declares Its
Own Pipeline Configuration*) gains the third required field and the two
scenarios that govern it. `iac-host-configuration`'s *Dynamic Inventory via the
hcloud Plugin, One Source per Stack* (ADDED) separates the source's name from
the group's. `iac-repo-foundations`' *Stack and Module Folder Structure* (ADDED)
states that a stack's directory name is not to be read as any axis it carries.
`iac-safety-hardening`'s *Consistent Resource Labeling* (MODIFIED) adds the
`tenant` axis and the full-spelling rule.

Each class names the requirement and the scenario it traces to, and every
assertion is annotated SPECIFIED (it traces to SHALL text or to a scenario in a
delta spec) or DERIVED (it traces to that change's `design.md` or `tasks.md`
rather than to a scenario). See that change's `test-plan.md` for the
scenario-to-test mapping, the baseline, the scenarios deliberately left
uncovered, the obsolete-test candidates, and the interface assumptions this file
took.

Why this is a fourteenth file in the suite rather than a section of an existing
one
-------------------------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. Nothing here edits, deletes or disables an
existing test. Several assertions already in this suite rest on propositions
these deltas retire -- that a stack's `environment` label equals its directory
name, that `TARGET_ENVIRONMENT` is fed from `matrix.stack.name`, that a
workspace's name is derived from the stack's, and that a stack's `group_vars`
file is named for the stack. Re-pointing those is the implementing author's
task, recorded in `test-plan.md`'s obsolete list rather than performed here.

`TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in
`test_ci_configuration.py` reads every module in this directory, so this file is
held to the no-network, no-credential, no-container, no-Terraform constraint by
that class. It is written to satisfy it: standard library, `yaml`, the sibling
helpers, and the one spawned command the suite already admits -- `bash`, to run
a workflow's own discovery body against a scratch tree.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable by name:
    python3 -m unittest \\
        test_a_stack_and_its_environment_are_named_separately\\
.TestEveryStackDeclaresTheGroupItConverges\\
.test_every_stack_declares_a_target_environment

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling imports below resolve.

What no assertion here establishes
----------------------------------
Not that any Hetzner resource was renamed, nor that a plan renames one in place
rather than replacing it. Both are facts about a Hetzner project reachable only
by an API call this suite is forbidden from making; the change's own tasks.md
9.2 and 11.1 make them the reviewer's and the operator's, and its `test-plan.md`
records every such scenario as uncovered here.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from test_ci_configuration import (
    ROOT,
    WORKFLOWS,
    load_yaml,
    read_text,
    require_external_tools,
    step_label,
    steps,
    uncommented,
)
from test_environment_agnostic_pipeline import run_snippet

# --------------------------------------------------------------------------
# What the tree is expected to be called
#
# DERIVED throughout. No scenario states a stack's name, an inventory
# filename or a Hetzner resource name -- the scenarios are written over "a
# stack" and "the `main` volume". The values below come from that change's
# proposal.md ("What Changes") and its tasks.md 3.1-3.5 and 4.1-4.2, which in
# turn come from `docs/naming-conventions.md`, the scheme this change brings the
# tree to. They are asserted here rather than left to review because every one
# of them is read by something that resolves it silently: a path, a group name,
# a label selector.
# --------------------------------------------------------------------------

# stack directory -> the Ansible group (and Hetzner `environment` label value)
# its host belongs to. The two differing for BOTH stacks is the whole point of
# the change; a repository in which they coincided would satisfy every
# assertion below while establishing nothing.
EXPECTED_STACKS = {
    "main-production": "production",
    "main-staging": "staging",
}

EXPECTED_TENANT = "main"
EXPECTED_FIREWALL_NAME = "main"
EXPECTED_VOLUME_NAME = "main"
EXPECTED_SSH_KEY_NAME = "operator"

# Volume names this repository has used and is retiring. DERIVED -- proposal.md
# names `main-data` as the volume's present name and `main` as its next one.
# Read only as a set of candidates for staleness: what makes one an offence is
# that no stack declares it any more.
EXPECTED_RETIRED_VOLUME_NAMES = ("main-data",)

# The declaration's filename and field names. Settled rather than inferred: the
# committed discovery bodies index the first two literally, and this change's
# design.md decision 2 fixes the third ("The field is named `target_environment`,
# matching the play variable it feeds").
DECLARATION_NAME = "pipeline.yml"
GITHUB_ENVIRONMENT_FIELD = "github_environment"
READ_ONLY_SECRET_FIELD = "read_only_secret"
TARGET_ENVIRONMENT_FIELD = "target_environment"

STACK_ROOT_SEGMENT = "terraform/stacks"
INVENTORY_SEGMENT = "ansible/inventory"
GROUP_VARS_SEGMENT = "ansible/inventory/group_vars"
SOURCE_SUFFIX = ".hcloud.yml"

HOST_CONVERGE = WORKFLOWS / "host-converge.yml"
PR_VALIDATION = WORKFLOWS / "pr-validation.yml"
APPLY = WORKFLOWS / "apply.yml"
DRIFT = WORKFLOWS / "drift.yml"
TERRAFORM_WORKFLOWS = (PR_VALIDATION, APPLY, DRIFT)

ACTIONS_EXPRESSION = re.compile(r"\$\{\{")

# An Ansible group name, which is also a Hetzner label value and a `group_vars`
# filename stem. DERIVED -- no scenario states a grammar; this is the
# intersection of what Ansible accepts as a group and what a filename may be.
GROUP_NAME = re.compile(r"\A[A-Za-z0-9_-]+\Z")

# A quoted scalar assignment in a `.tf` or `.tfvars` file, read as text rather
# than parsed: this suite may not run Terraform.
HCL_ASSIGNMENT = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"([^"]*)"', re.MULTILINE)
SSH_KEY_BLOCK = re.compile(r'resource\s+"hcloud_ssh_key"\s+"[^"]+"\s*\{(.*?)\n\}', re.DOTALL)


# --------------------------------------------------------------------------
# Reading the tree
#
# Every reader takes `root`, so that the discriminating class at the end of this
# file can point it at a tree built to falsify what it reads. At two stacks
# these reads would otherwise pass over a set small enough that a reader
# returning nothing at all satisfies them.
# --------------------------------------------------------------------------


def _base(root: Path | None) -> Path:
    return ROOT if root is None else root


def stack_names(root: Path | None = None) -> list[str]:
    base = _base(root) / "terraform" / "stacks"
    if not base.is_dir():
        return []
    return sorted(
        entry.name
        for entry in base.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    )


def stack_declarations(root: Path | None = None) -> dict[str, dict]:
    """Each stack's pipeline declaration as a mapping, or `{}` where it carries
    none or carries one that does not parse."""
    found: dict[str, dict] = {}
    for name in stack_names(root):
        path = _base(root) / "terraform" / "stacks" / name / DECLARATION_NAME
        if not path.is_file():
            found[name] = {}
            continue
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            document = None
        found[name] = document if isinstance(document, dict) else {}
    return found


def declared_groups(root: Path | None = None) -> dict[str, str | None]:
    """Each stack mapped to the Ansible group its declaration names."""
    groups: dict[str, str | None] = {}
    for name, mapping in stack_declarations(root).items():
        value = mapping.get(TARGET_ENVIRONMENT_FIELD)
        groups[name] = value if isinstance(value, str) and value.strip() else None
    return groups


def inventory_source_names(root: Path | None = None) -> list[str]:
    """The stem of every committed inventory source, which is a STACK's name."""
    base = _base(root) / "ansible" / "inventory"
    if not base.is_dir():
        return []
    return sorted(
        entry.name[: -len(SOURCE_SUFFIX)]
        for entry in base.iterdir()
        if entry.is_file() and entry.name.endswith(SOURCE_SUFFIX)
    )


def group_vars_names(root: Path | None = None) -> list[str]:
    """The stem of every committed `group_vars` file, which is a GROUP's name."""
    base = _base(root) / "ansible" / "inventory" / "group_vars"
    if not base.is_dir():
        return []
    return sorted(
        entry.stem for entry in base.iterdir() if entry.is_file() and entry.suffix == ".yml"
    )


def stack_terraform_text(name: str, root: Path | None = None) -> str:
    directory = _base(root) / "terraform" / "stacks" / name
    if not directory.is_dir():
        return ""
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(directory.glob("*.tf"))
    )


def stack_tfvars(name: str, root: Path | None = None) -> dict[str, str]:
    path = _base(root) / "terraform" / "stacks" / name / "terraform.tfvars"
    if not path.is_file():
        return {}
    return dict(HCL_ASSIGNMENT.findall(uncommented(path.read_text(encoding="utf-8"))))


def stack_module_arguments(name: str, root: Path | None = None) -> dict[str, str]:
    """Every quoted scalar a stack's `.tf` files assign, outside its
    `hcloud_ssh_key` block.

    Read as text because this suite may not run Terraform. It is enough for
    what is asked of it: the values below are literals in the stack's own files,
    not expressions.
    """
    text = stack_terraform_text(name, root)
    for block in SSH_KEY_BLOCK.findall(text):
        text = text.replace(block, "")
    return dict(HCL_ASSIGNMENT.findall(uncommented(text)))


def ssh_key_arguments(name: str, root: Path | None = None) -> dict[str, str]:
    """The quoted scalars inside a stack's own `hcloud_ssh_key` block, labels
    included -- a resource outside a module is not outside the labeling
    obligation."""
    blocks = SSH_KEY_BLOCK.findall(stack_terraform_text(name, root))
    if not blocks:
        return {}
    return dict(HCL_ASSIGNMENT.findall(uncommented("\n".join(blocks))))


def inventory_document(name: str, root: Path | None = None) -> dict:
    path = _base(root) / "ansible" / "inventory" / f"{name}{SOURCE_SUFFIX}"
    if not path.is_file():
        return {}
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return document if isinstance(document, dict) else {}


def keyed_group_keys(name: str, root: Path | None = None) -> set[str]:
    entries = inventory_document(name, root).get("keyed_groups") or []
    return {
        str(entry.get("key"))
        for entry in entries
        if isinstance(entry, dict) and entry.get("key")
    }


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Each Stack Declares Its Own Pipeline Configuration
# --------------------------------------------------------------------------


class TestEveryStackDeclaresTheGroupItConverges(unittest.TestCase):
    """ADDED requirement: Each Stack Declares Its Own Pipeline Configuration --
    "Three fields are **required**: ... and the name of the Ansible group its
    host-configuration converge targets", and scenario "A converge reads its
    Ansible group from the declaration, not from the stack's name"."""

    def setUp(self) -> None:
        self.declarations = stack_declarations()
        self.assertTrue(
            self.declarations,
            "no stack directory was discovered under terraform/stacks/, so every "
            "assertion in this class would pass having read nothing",
        )

    def test_every_stack_declares_a_target_environment(self) -> None:
        """SPECIFIED -- the required-field clause above, and scenario "A stack
        missing its declaration fails the pipeline", whose WHEN now includes
        "one lacking a field the running workflow requires"."""
        missing = sorted(
            name for name, group in declared_groups().items() if group is None
        )
        self.assertEqual(
            [],
            missing,
            f"these stacks declare no usable `{TARGET_ENVIRONMENT_FIELD}`: {missing}. "
            "The field names the Ansible group this stack's converge targets, and "
            "after this change it cannot be read off the stack's own name",
        )

    def test_the_declared_group_is_a_name_ansible_can_resolve(self) -> None:
        """DERIVED -- no scenario states a grammar. The value becomes a play's
        `hosts:`, a `--vault-id` label and a `group_vars` filename stem, and a
        value that is none of those fails several steps after the run began,
        which is the failure mode the declaration exists to end."""
        declared = {
            name: group for name, group in declared_groups().items() if group is not None
        }
        self.assertTrue(
            declared,
            "no stack declares an Ansible group, so this assertion would pass having "
            "compared nothing -- see `test_every_stack_declares_a_target_environment`",
        )
        malformed = sorted(
            f"{name} -> {group!r}"
            for name, group in declared_groups().items()
            if group is not None and not GROUP_NAME.match(group)
        )
        self.assertEqual([], malformed, f"these declared groups are unusable: {malformed}")

    def test_no_stacks_name_and_declared_group_are_assumed_equal(self) -> None:
        """SPECIFIED -- "**The declared Ansible group SHALL NOT be derived from
        the stack's name.**", and `iac-repo-foundations`' scenario "A stack's
        name is not read as its environment".

        A tree in which every stack's name happened to equal its declared group
        would satisfy every other assertion in this file while leaving the
        derivation this change removes indistinguishable from the declaration
        that replaces it. Both of this repository's stacks are expected to
        differ, so this is asserted over all of them rather than over at least
        one.
        """
        declared = {
            name: group for name, group in declared_groups().items() if group is not None
        }
        self.assertTrue(
            declared,
            "no stack declares an Ansible group, so this assertion would pass having "
            "compared nothing -- see `test_every_stack_declares_a_target_environment`",
        )
        coinciding = sorted(
            name for name, group in declared_groups().items() if group == name
        )
        self.assertEqual(
            [],
            coinciding,
            f"these stacks declare a group equal to their own directory name: "
            f"{coinciding}. The two coincide only where a repository has one tenant, "
            "and a tree in which they coincide cannot tell a declaration from a "
            "derivation",
        )

    def test_the_other_two_required_fields_are_still_declared_and_distinct(self) -> None:
        """SPECIFIED -- "Each stack's declared read-only secret name SHALL be
        distinct from every other stack's, and so SHALL its declared GitHub
        Environment name", carried across the rename unchanged. Asserted here
        because this change edits every declaration, and a field lost while a
        third was added is the defect an edit to this file would produce."""
        for field in (GITHUB_ENVIRONMENT_FIELD, READ_ONLY_SECRET_FIELD):
            with self.subTest(field=field):
                values = {
                    name: mapping.get(field) for name, mapping in self.declarations.items()
                }
                missing = sorted(name for name, value in values.items() if not value)
                self.assertEqual([], missing, f"these stacks declare no `{field}`: {missing}")
                declared = list(values.values())
                self.assertEqual(
                    len(set(declared)),
                    len(declared),
                    f"two stacks declare the same `{field}`: {values}",
                )

    def test_the_declared_group_carries_no_distinctness_obligation(self) -> None:
        """SPECIFIED -- "**Unlike the other two required fields, the declared
        Ansible group carries no uniqueness obligation** ... Distinctness SHALL
        NOT be required of it", and scenario "Two stacks declaring the same
        Ansible group are accepted".

        What a static read can establish is that nothing in the committed
        pipeline text imposes the distinctness the other two fields are held to.
        That discovery ACCEPTS two stacks sharing a group is established by
        running it, in `TestHostConvergeDiscoveryReadsTheDeclaredGroup` below.
        """
        for path in (HOST_CONVERGE,) + TERRAFORM_WORKFLOWS:
            with self.subTest(workflow=path.name):
                text = uncommented(read_text(path))
                offending = [
                    line.strip()
                    for line in text.splitlines()
                    if TARGET_ENVIRONMENT_FIELD in line
                    and re.search(r"\b(sort\s+-u|uniq|duplicate|already declared)\b", line)
                ]
                self.assertEqual(
                    [],
                    offending,
                    f"{path.name} appears to test the declared group for distinctness: "
                    f"{offending}. Two stacks naming one Ansible group share a set of "
                    "host variables, which is what an environment-wide baseline across "
                    "tenants IS",
                )


# --------------------------------------------------------------------------
# iac-host-configuration / Dynamic Inventory via the hcloud Plugin, One Source
# per Stack
# --------------------------------------------------------------------------


class TestASourcesNameIsNotReadAsItsGroupsName(unittest.TestCase):
    """ADDED requirement: Dynamic Inventory via the hcloud Plugin, One Source
    per Stack -- "**A source is named for its stack and a group is named for its
    axis, and neither SHALL be derived from the other.**", and scenario "A
    source's name is not read as its group's name"."""

    def test_every_stack_has_an_inventory_source_named_for_the_stack(self) -> None:
        """SPECIFIED -- "An inventory source's filename follows the stack it
        reaches, because what it reaches is a Hetzner project", and scenario "A
        stack that can be provisioned but not converged is reported"."""
        stacks = set(stack_names())
        self.assertTrue(stacks, "no stack directory was discovered; see the class above")
        sources = set(inventory_source_names())
        self.assertEqual(
            stacks,
            sources,
            f"the set of inventory sources does not match the set of stacks: stacks "
            f"{sorted(stacks)}, sources {sorted(sources)}. A stack with no source is "
            "one whose host configuration nothing applies; a source naming no stack is "
            "one whose reach is decided by whichever credential the shell held",
        )

    def test_the_group_vars_file_each_stack_declares_exists(self) -> None:
        """SPECIFIED -- "the `group_vars` file its declared group names SHALL
        exist", and "the `group_vars` file that supplies its variables follow
        the *environment*".

        This is the half that moves: the file is named for the GROUP, so a
        stack named `main-production` reads `group_vars/production.yml` and a
        file named for the stack would be read by nothing.
        """
        declared = {
            name: group for name, group in declared_groups().items() if group is not None
        }
        self.assertTrue(
            declared,
            "no stack declares an Ansible group, so this assertion would pass having "
            "compared nothing -- see `test_every_stack_declares_a_target_environment`",
        )
        present = set(group_vars_names())
        missing = sorted(
            f"{name} declares {group!r}, and "
            f"{GROUP_VARS_SEGMENT}/{group}.yml does not exist"
            for name, group in declared_groups().items()
            if group is not None and group not in present
        )
        self.assertEqual([], missing, "; ".join(missing) or "")

    def test_no_group_vars_file_is_named_for_a_stack_that_is_not_a_group(self) -> None:
        """SPECIFIED -- the same clause read the other way. A `group_vars` file
        named for a stack is read by nothing: Ansible resolves
        `group_vars/<group>.yml`, and no group carries the stack's name.

        DERIVED as to which names are permitted: a `group_vars` file may name a
        group no stack declares -- `all.yml` is exactly that, and this change
        creates it -- so the offence is narrowed to a file named for a STACK.
        """
        stacks = set(stack_names())
        groups = set(filter(None, declared_groups().values()))
        stranded = sorted(name for name in group_vars_names() if name in stacks - groups)
        self.assertEqual(
            [],
            stranded,
            f"these `group_vars` files are named for a stack rather than for a group, "
            f"so Ansible resolves them for nothing: {stranded}",
        )

    def test_every_source_groups_hosts_by_both_axes(self) -> None:
        """SPECIFIED -- "Hosts SHALL be grouped by the Hetzner labels already
        applied to every resource, one group per axis: by the `environment`
        label, and by the `tenant` label", and scenario "Hosts are grouped by
        every axis their labels carry"."""
        sources = inventory_source_names()
        self.assertTrue(sources, "no inventory source was discovered, so this read is vacuous")
        for name in sources:
            with self.subTest(source=name):
                keys = keyed_group_keys(name)
                for axis in ("hcloud_labels.environment", "hcloud_labels.tenant"):
                    self.assertIn(
                        axis,
                        keys,
                        f"{INVENTORY_SEGMENT}/{name}{SOURCE_SUFFIX} declares no keyed "
                        f"group over {axis}: {sorted(keys)}. A group per axis is what "
                        "lets a baseline be written for an axis without special-casing "
                        "the stacks that carry it",
                    )


# --------------------------------------------------------------------------
# iac-repo-foundations / Stack and Module Folder Structure;
# iac-safety-hardening / Consistent Resource Labeling
# --------------------------------------------------------------------------


class TestTheTreeCarriesTheRenamedValues(unittest.TestCase):
    """ADDED requirement: Stack and Module Folder Structure -- scenario "A
    stack directory consumes a shared module", whose WHEN now names
    `terraform/stacks/main-production/`; MODIFIED requirement: Consistent
    Resource Labeling -- scenarios "Prod resources are labeled" and "Prod volume
    is labeled", whose THEN now name `environment = "production"` and
    `tenant = "main"`; and `iac-data-volumes`' *Conditional Prod Volume
    Creation*, whose scenarios name the `main` volume.

    DERIVED as to the stack directory names themselves: no scenario states that
    this repository's stacks are called `main-production` and `main-staging`.
    They come from the change's proposal.md and `docs/naming-conventions.md`,
    and they are asserted because everything that reads them -- a path in four
    workflows, a Dependabot entry, an inventory filename -- resolves a wrong one
    silently.
    """

    def test_the_stack_directories_are_named_for_their_tenant_and_environment(self) -> None:
        """DERIVED -- proposal.md's "What Changes": `terraform/stacks/prod/` ->
        `terraform/stacks/main-production/`, `terraform/stacks/staging/` ->
        `terraform/stacks/main-staging/`."""
        self.assertEqual(
            sorted(EXPECTED_STACKS),
            stack_names(),
            "the stack directories are not the ones this change names. A stack "
            "directory is named for the stack -- a (tenant, environment) pair -- and "
            "its name is what four workflows, the Dependabot configuration and the "
            "inventory sources resolve",
        )

    def test_each_stack_declares_the_environment_axis_spelled_in_full(self) -> None:
        """SPECIFIED -- "**Environment values SHALL be spelled in full.**
        `prod` and `preprod` share a prefix", and scenario "Prod resources are
        labeled", whose THEN reads `environment = "production"`.

        The value is read from the stack's own `.tf` files, which is where the
        module call passes it. DERIVED as to WHICH value each stack carries:
        the mapping in `EXPECTED_STACKS`.
        """
        for stack, group in EXPECTED_STACKS.items():
            with self.subTest(stack=stack):
                arguments = stack_module_arguments(stack)
                self.assertEqual(
                    group,
                    arguments.get("environment"),
                    f"{STACK_ROOT_SEGMENT}/{stack}/ passes "
                    f"environment = {arguments.get('environment')!r} to its modules, "
                    f"not {group!r}. A label value is read by prefix in more places "
                    "than it is read whole",
                )

    def test_each_stack_passes_the_tenant_axis_to_its_modules(self) -> None:
        """SPECIFIED -- "one label per axis its stack is identified on: an
        `environment` label ... and a `tenant` label naming the tenant".
        DERIVED as to the value `main`: design.md decision 5."""
        for stack in EXPECTED_STACKS:
            with self.subTest(stack=stack):
                arguments = stack_module_arguments(stack)
                self.assertEqual(
                    EXPECTED_TENANT,
                    arguments.get("tenant"),
                    f"{STACK_ROOT_SEGMENT}/{stack}/ passes "
                    f"tenant = {arguments.get('tenant')!r} to its modules. It is an "
                    "input rather than a literal inside the module for the reason "
                    "`environment` is: a module that hardcodes a label value is one a "
                    "second tenant cannot use",
                )

    def test_each_stack_names_its_firewall_rather_than_deriving_it(self) -> None:
        """DERIVED -- design.md decision 4 and tasks.md 3.3. No scenario states
        a firewall's name; what the specification states is the rule the
        derivation offends, and `modules/server`'s own
        `tests/firewall_name.tftest.hcl` is where that is asserted. What is
        asserted here is the other half: that the stack supplies the input."""
        for stack in EXPECTED_STACKS:
            with self.subTest(stack=stack):
                self.assertEqual(
                    EXPECTED_FIREWALL_NAME,
                    stack_module_arguments(stack).get("firewall_name"),
                    f"{STACK_ROOT_SEGMENT}/{stack}/ does not pass "
                    f"firewall_name = {EXPECTED_FIREWALL_NAME!r}. Without it the module "
                    "has no name to give the firewall, and with a derived one the "
                    "firewall would be called `production-main-production`",
                )

    def test_each_stacks_server_is_named_for_its_stack(self) -> None:
        """DERIVED -- proposal.md's "What Changes": "The server takes its
        stack's name". The consequence the proposal states is what makes it
        worth asserting: the server's name reaches the tailnet and the heartbeat
        account, neither of which is scoped to one Hetzner project, and a
        collision there fails in the direction of a green report."""
        for stack in EXPECTED_STACKS:
            with self.subTest(stack=stack):
                self.assertEqual(
                    stack,
                    stack_tfvars(stack).get("name"),
                    f"{STACK_ROOT_SEGMENT}/{stack}/terraform.tfvars names its server "
                    f"{stack_tfvars(stack).get('name')!r} rather than {stack!r}. A name "
                    "unique per project but not per company collides in the tailnet and "
                    "in the heartbeat account",
                )

    def test_each_stacks_volume_is_named_on_the_rank_axis(self) -> None:
        """SPECIFIED -- `iac-data-volumes`' *Conditional Prod Volume Creation*:
        "**The volume's name SHALL NOT carry the role of the server it is
        attached to.**", and its scenarios, which name the `main` volume.

        A stack declaring no volume at all is not an offence; it is a stack with
        nothing to name.
        """
        declared = {
            stack: stack_tfvars(stack).get("volume_name")
            for stack in EXPECTED_STACKS
            if stack_tfvars(stack).get("volume_name") is not None
        }
        self.assertTrue(
            declared,
            "no stack declares a volume name, so this assertion would compare nothing",
        )
        wrong = {
            stack: value for stack, value in declared.items() if value != EXPECTED_VOLUME_NAME
        }
        self.assertEqual(
            {},
            wrong,
            f"these stacks name their volume something other than "
            f"{EXPECTED_VOLUME_NAME!r}: {wrong}. A volume is project-local, so it is "
            "distinguished by rank rather than by what consumes it -- and the on-host "
            "mount path is derived from the volume's id, so the name is free to change",
        )

    def test_each_stacks_ssh_key_is_named_and_labelled_like_every_other_resource(self) -> None:
        """SPECIFIED -- scenario "An SSH key a stack owns directly is labeled":
        "it SHALL carry the same axis labels every resource that stack's modules
        create carries, because a resource outside a module is not outside this
        obligation". DERIVED as to the key's own name `operator`: proposal.md's
        "keys take the identity axis"."""
        for stack, group in EXPECTED_STACKS.items():
            with self.subTest(stack=stack):
                arguments = ssh_key_arguments(stack)
                self.assertTrue(
                    arguments,
                    f"{STACK_ROOT_SEGMENT}/{stack}/ declares no `hcloud_ssh_key` this "
                    "read can see, so the assertions below would compare nothing",
                )
                self.assertEqual(
                    EXPECTED_SSH_KEY_NAME,
                    arguments.get("name"),
                    f"{stack}'s SSH key is named {arguments.get('name')!r}. A key is "
                    "named for what it authenticates, not for the rank of the stack it "
                    "happens to sit in",
                )
                self.assertEqual(
                    (group, EXPECTED_TENANT, "terraform"),
                    (
                        arguments.get("environment"),
                        arguments.get("tenant"),
                        arguments.get("managed_by"),
                    ),
                    f"{stack}'s SSH key does not carry the three axis labels every "
                    f"other resource in that stack carries: {arguments}",
                )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Each Stack Declares Its Own Pipeline Configuration --
# the discovery that reads the field
# --------------------------------------------------------------------------


class DiscoveryTreeFixtureMixin:
    """Builds a synthetic tree carrying both sides the converge's discovery
    cross-checks: a stack root and an Ansible inventory.

    Both sides are built from THIS REPOSITORY's own committed files -- a
    committed declaration for the Terraform side and a committed inventory
    source for the Ansible side -- rather than from a shape this file invented.
    The filenames are not free: the `hcloud` plugin's `verify_file` accepts a
    path only if it ends `hcloud.yml`, and Ansible resolves
    `group_vars/<group>.yml`, so a fixture spelling either differently would be
    refused by a correct discovery for the right reason.
    """

    def _scratch(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="stack-and-environment-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        return directory

    def _declaration_template(self) -> dict:
        declarations = stack_declarations()
        for name, mapping in sorted(declarations.items()):
            if mapping.get(GITHUB_ENVIRONMENT_FIELD):
                return dict(mapping)
        self.fail(
            "no committed stack carries a pipeline declaration naming a GitHub "
            "Environment, so this fixture has no committed shape to follow"
        )

    def _source_text(self) -> str:
        base = ROOT / "ansible" / "inventory"
        sources = sorted(base.glob(f"*{SOURCE_SUFFIX}")) if base.is_dir() else []
        if not sources:
            self.fail(
                "no committed inventory source was found, so this fixture has no shape "
                "to follow"
            )
        return sources[0].read_text(encoding="utf-8")

    def _declaration(
        self,
        secret: str,
        github_environment: str,
        target_environment: str | None,
    ) -> dict:
        mapping = self._declaration_template()
        mapping[READ_ONLY_SECRET_FIELD] = secret
        mapping[GITHUB_ENVIRONMENT_FIELD] = github_environment
        mapping.pop(TARGET_ENVIRONMENT_FIELD, None)
        if target_environment is not None:
            mapping[TARGET_ENVIRONMENT_FIELD] = target_environment
        return mapping

    def _write_stack(
        self,
        tree: Path,
        name: str,
        *,
        declaration: dict | None,
        source: bool = True,
        group_vars: str | None = None,
    ) -> None:
        directory = tree / "terraform" / "stacks" / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "main.tf").write_text(
            'module "server" {\n  source = "../../modules/server"\n}\n', encoding="utf-8"
        )
        if declaration is not None:
            (directory / DECLARATION_NAME).write_text(
                yaml.safe_dump(declaration, sort_keys=True), encoding="utf-8"
            )
        inventory = tree / "ansible" / "inventory"
        (inventory / "group_vars").mkdir(parents=True, exist_ok=True)
        if source:
            (inventory / f"{name}{SOURCE_SUFFIX}").write_text(
                self._source_text(), encoding="utf-8"
            )
        if group_vars is not None:
            (inventory / "group_vars" / f"{group_vars}.yml").write_text(
                "---\n# fixture variables for this group\n", encoding="utf-8"
            )

    def _converge_discovery_step(self):
        """The converge workflow's discovery body, located by shape: the one
        `run:` step that enumerates the inventory directory, writes to
        `$GITHUB_OUTPUT`, and carries no Actions expression. That it carries
        none is what lets this suite execute it at all."""
        workflow = load_yaml(HOST_CONVERGE)
        candidates = []
        for job_name, index, step in steps(workflow):
            body = str(step.get("run") or "")
            if not body or "inventory" not in body or "GITHUB_OUTPUT" not in body:
                continue
            if ACTIONS_EXPRESSION.search(body):
                continue
            candidates.append((step_label(job_name, index, step), step))
        self.assertEqual(
            1,
            len(candidates),
            f"expected exactly one discovery body in {HOST_CONVERGE.name} this suite "
            f"can execute, found {[label for label, _ in candidates]}",
        )
        return candidates[0][1]

    def _run(self, step, tree: Path):
        outputs = tree / "github_output"
        summary = tree / "step_summary"
        outputs.touch()
        summary.touch()
        environment = dict(
            os.environ,
            GITHUB_OUTPUT=str(outputs),
            GITHUB_ENV=str(outputs),
            GITHUB_STEP_SUMMARY=str(summary),
            GITHUB_WORKSPACE=str(tree),
        )
        for key, value in (step.get("env") or {}).items():
            if not ACTIONS_EXPRESSION.search(str(value)):
                environment[str(key)] = str(value)
        result = run_snippet(str(step["run"]), environment, tree)
        return result, outputs.read_text(encoding="utf-8")


class TestHostConvergeDiscoveryReadsTheDeclaredGroup(
    DiscoveryTreeFixtureMixin, unittest.TestCase
):
    """ADDED requirement: Each Stack Declares Its Own Pipeline Configuration --
    scenarios "A converge reads its Ansible group from the declaration, not from
    the stack's name", "Two stacks declaring the same Ansible group are
    accepted" and "A stack missing its declaration fails the pipeline"; and
    `iac-host-configuration`'s scenario "A stack that can be provisioned but not
    converged is reported".

    Runs the workflow's own discovery body rather than reading it, the shape
    `test_host_converge_workflow.TestHostConvergeDiscoveryFailsClosed`
    established. Grepping would establish that a field is mentioned; only
    running it establishes that discovery reads it, refuses without it, and
    cross-checks the right file.

    This class is also this file's fixture-driven discriminator for the
    discovery body: every tree below is one this test supplies, so a body that
    accepted or refused everything is caught by the row that expects the
    opposite.
    """

    def setUp(self) -> None:
        require_external_tools(
            self,
            ("bash", "jq", "mktemp"),
            "execute the host-converge workflow's stack-discovery body",
        )
        self.step = self._converge_discovery_step()

    def _combined(self, result) -> str:
        return (result.stdout + result.stderr).strip()

    def test_a_stack_whose_group_differs_from_its_name_is_accepted_and_emitted(self) -> None:
        """SPECIFIED -- scenario "A converge reads its Ansible group from the
        declaration, not from the stack's name": "the play's target group, the
        vault-id label and the `group_vars` file SHALL be taken from the
        declared field".

        The converse every refusal below needs: a discovery that refused every
        tree would satisfy each of them while converging nothing.
        """
        tree = self._scratch()
        self._write_stack(
            tree,
            "alpha-live",
            declaration=self._declaration("HCLOUD_TOKEN_ALPHA", "live", "live"),
            group_vars="live",
        )
        result, emitted = self._run(self.step, tree)
        self.assertEqual(
            0,
            result.returncode,
            "discovery refused a stack whose declared group differs from its own name, "
            f"with its `group_vars` file named for the group: {self._combined(result)[-800:]!r}",
        )
        for expected in ("alpha-live", "live"):
            self.assertIn(
                expected,
                emitted + result.stdout,
                f"discovery emitted no {expected!r} for the matrix, so the converge job "
                "has one of the two names and must derive the other",
            )

    def test_a_stack_declaring_no_group_is_refused_by_name(self) -> None:
        """SPECIFIED -- "A stack directory whose declaration is absent,
        unparseable, or missing a **required** field SHALL fail the workflow
        with a message naming the directory and the missing field, and SHALL NOT
        be silently skipped"."""
        tree = self._scratch()
        self._write_stack(
            tree,
            "alpha-live",
            declaration=self._declaration("HCLOUD_TOKEN_ALPHA", "live", None),
            group_vars="live",
        )
        result, _ = self._run(self.step, tree)
        detail = self._combined(result)
        self.assertNotEqual(
            0,
            result.returncode,
            "discovery accepted a stack declaring no Ansible group. The converge would "
            "then have to compute one from the stack's name, which is the derivation "
            f"this change removes: {detail[-800:]!r}",
        )
        self.assertIn("alpha-live", detail, f"the refusal does not name the stack: {detail!r}")
        self.assertIn(
            TARGET_ENVIRONMENT_FIELD,
            detail,
            f"the refusal does not name the missing field: {detail!r}",
        )

    def test_the_group_vars_cross_check_follows_the_declared_group(self) -> None:
        """SPECIFIED -- `iac-host-configuration`'s "the `group_vars` file its
        declared group names SHALL exist", and its scenario "A stack that can be
        provisioned but not converged is reported".

        The fixture supplies a `group_vars` file named for the STACK and none
        named for the group. A discovery still cross-checking the stack's name
        accepts this tree; a correct one refuses it, and its message has to say
        which of the two names it is talking about.
        """
        tree = self._scratch()
        self._write_stack(
            tree,
            "alpha-live",
            declaration=self._declaration("HCLOUD_TOKEN_ALPHA", "live", "live"),
            group_vars="alpha-live",
        )
        result, _ = self._run(self.step, tree)
        detail = self._combined(result)
        self.assertNotEqual(
            0,
            result.returncode,
            "discovery accepted a stack whose declared group has no `group_vars` file, "
            "because a file named for the STACK was present. A converge of it would "
            f"run with none of that environment's variables: {detail[-800:]!r}",
        )
        self.assertIn(
            "group_vars/live.yml",
            detail,
            "the refusal does not name the file it looked for, so a reader cannot tell "
            f"which of the stack's two names it is talking about: {detail!r}",
        )

    def test_two_stacks_declaring_one_group_are_accepted(self) -> None:
        """SPECIFIED -- scenario "Two stacks declaring the same Ansible group
        are accepted": "discovery SHALL accept both, because a shared group is a
        shared set of host variables rather than a shared credential"."""
        tree = self._scratch()
        self._write_stack(
            tree,
            "alpha-live",
            declaration=self._declaration("HCLOUD_TOKEN_ALPHA", "alpha-live", "live"),
            group_vars="live",
        )
        self._write_stack(
            tree,
            "bravo-live",
            declaration=self._declaration("HCLOUD_TOKEN_BRAVO", "bravo-live", "live"),
        )
        result, emitted = self._run(self.step, tree)
        self.assertEqual(
            0,
            result.returncode,
            "discovery refused two stacks declaring one Ansible group, each with its "
            "own credential and its own GitHub Environment. That is what an "
            "environment-wide baseline across tenants IS, and asserting distinctness "
            f"of this field would forbid it: {self._combined(result)[-800:]!r}",
        )
        for expected in ("alpha-live", "bravo-live"):
            self.assertIn(
                expected,
                emitted + result.stdout,
                f"discovery emitted no row for {expected!r}",
            )


class TestTheTerraformDiscoveryDoesNotRequireTheConvergeField(unittest.TestCase):
    """ADDED requirement: Each Stack Declares Its Own Pipeline Configuration --
    "A field is required of the discovery that reads it: a workflow that runs no
    converge SHALL NOT refuse a stack for the absence of a field only a converge
    consumes".

    Asserted as a read of the three Terraform workflows rather than by running
    them: what the clause forbids is that those bodies READ the field at all,
    and a body that does not mention it cannot refuse a stack for its absence.
    The three bodies are asserted byte-identical to one another by
    `test_terraform_stacks_are_the_iterated_unit`, so this holds of each or of
    none.
    """

    def test_no_terraform_workflow_reads_the_converge_only_field(self) -> None:
        """SPECIFIED -- the clause above, and design.md decision 2's "Only
        `host-converge.yml`'s discovery requires the field"."""
        for path in TERRAFORM_WORKFLOWS:
            with self.subTest(workflow=path.name):
                self.assertNotIn(
                    TARGET_ENVIRONMENT_FIELD,
                    uncommented(read_text(path)),
                    f"{path.name} names `{TARGET_ENVIRONMENT_FIELD}`, a field only a "
                    "converge consumes. Requiring it here fails a Terraform-only pull "
                    "request for a host-configuration reason -- a cause the change does "
                    "not have",
                )

    def test_the_converge_workflow_does_read_it(self) -> None:
        """DERIVED -- the converse of the assertion above, which on its own
        would be satisfied by a repository in which the field existed nowhere.
        No scenario states it; it is what makes the negative read above
        non-vacuous."""
        self.assertIn(
            TARGET_ENVIRONMENT_FIELD,
            uncommented(read_text(HOST_CONVERGE)),
            f"{HOST_CONVERGE.name} never names `{TARGET_ENVIRONMENT_FIELD}`, so the "
            "negative assertion above holds of a repository where the field is read by "
            "nothing",
        )


class TestTheConvergeSeparatesTheTwoHandles(unittest.TestCase):
    """ADDED requirement: Each Stack Declares Its Own Pipeline Configuration --
    scenario "A converge reads its Ansible group from the declaration, not from
    the stack's name"; and `iac-host-configuration`'s scenario "A source's name
    is not read as its group's name": "the inventory source named with `-i`
    SHALL be the one named for the stack, and the group targeted, the vault-id
    label and the `group_vars` file SHALL be the ones named for the declared
    environment".

    The matrix key each handle is reached through is the implementing author's
    to choose, so nothing below asserts a spelling. What is asserted is that the
    two handles are DIFFERENT fields of the matrix row, and which surface each
    one reaches.
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(HOST_CONVERGE)
        self.text = uncommented(read_text(HOST_CONVERGE))

    def _matrix_fields_by_environment_key(self) -> dict[str, str]:
        """Every step `env:` key whose value reads one field of the matrix row,
        mapped to that field's name."""
        found: dict[str, str] = {}
        for _, _, step in steps(self.workflow):
            for key, value in (step.get("env") or {}).items():
                match = re.search(r"matrix\.[A-Za-z0-9_]+\.([A-Za-z0-9_]+)", str(value))
                if match:
                    found[str(key)] = match.group(1)
        return found

    def _handle_used_in(self, pattern: str) -> set[str]:
        """The shell variables the converge's own command lines interpolate at a
        given surface."""
        found: set[str] = set()
        for line in self.text.splitlines():
            for occurrence in re.finditer(pattern, line):
                found.update(re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)", occurrence.group(0)))
        return found

    def test_the_inventory_path_and_the_group_are_taken_from_different_handles(self) -> None:
        """SPECIFIED -- the scenario above. Stated as an inequality rather than
        as two spellings, because the inequality is the obligation: one handle
        for both names is the coincidence this change ends."""
        fields = self._matrix_fields_by_environment_key()
        self.assertTrue(
            fields,
            "no step in the converge workflow takes a field of the matrix row through "
            "its `env:`, so this read has nothing to compare",
        )
        inventory_handles = self._handle_used_in(r'-i\s+"?inventory/\$[^"\s]*')
        group_handles = self._handle_used_in(r'--vault-id\s+"?\$[^"\s@]*')
        self.assertTrue(
            inventory_handles,
            "no command line in the converge workflow builds an inventory path from a "
            "variable, so the split this asserts cannot be read",
        )
        self.assertTrue(
            group_handles,
            "no command line in the converge workflow builds a `--vault-id` label from "
            "a variable",
        )
        inventory_fields = {fields.get(name) for name in inventory_handles} - {None}
        group_fields = {fields.get(name) for name in group_handles} - {None}
        self.assertTrue(
            inventory_fields and group_fields,
            "the handles the converge uses are not resolvable to matrix fields: "
            f"inventory {sorted(inventory_handles)}, group {sorted(group_handles)}, "
            f"fields {fields}",
        )
        self.assertEqual(
            set(),
            inventory_fields & group_fields,
            "the inventory path and the `--vault-id` label are built from the same "
            f"matrix field ({sorted(inventory_fields & group_fields)}). The source is "
            "named for the stack and the label for the environment; one handle for "
            "both is exactly the coincidence this change ends",
        )

    def test_the_play_variable_is_fed_from_the_declared_group(self) -> None:
        """SPECIFIED -- the same scenario, read at the play's own input. The
        variable keeps its name and changes its source: what this asserts is
        that its source is not the stack's name."""
        fields = self._matrix_fields_by_environment_key()
        play_handles = self._handle_used_in(r'target_environment=\$?\{?[A-Za-z_][A-Za-z0-9_]*')
        self.assertTrue(
            play_handles,
            "no command line in the converge workflow passes `target_environment=` from "
            "a variable, so the play is given no group to target",
        )
        wrong = sorted(name for name in play_handles if fields.get(name) == "name")
        self.assertEqual(
            [],
            wrong,
            f"these handles feed `target_environment=` from the matrix row's stack name: "
            f"{wrong}. The play's group is the environment, read from the stack's own "
            "declaration -- a stack's name and its environment are equal only where a "
            "repository has one tenant",
        )

    def test_the_concurrency_group_stays_on_the_stack(self) -> None:
        """DERIVED -- tasks.md 6.4 and design.md decision 1: the concurrency
        group "serialises runs against one Hetzner project, and two stacks
        sharing an environment must not share a queue". No scenario states it,
        and it is the one surface in this workflow that must NOT follow the
        environment."""
        converge_jobs = [
            job
            for job in (self.workflow.get("jobs") or {}).values()
            if isinstance(job, dict) and job.get("concurrency")
        ]
        self.assertTrue(
            converge_jobs,
            "no job in the converge workflow declares a concurrency group, so two runs "
            "against one Hetzner project could overlap",
        )
        for job in converge_jobs:
            concurrency = job["concurrency"]
            expression = str(
                concurrency.get("group") if isinstance(concurrency, dict) else concurrency
            )
            match = re.search(r"matrix\.[A-Za-z0-9_]+\.([A-Za-z0-9_]+)", expression)
            self.assertIsNotNone(
                match,
                f"the concurrency group {expression!r} reads no field of the matrix row",
            )
            self.assertEqual(
                "name",
                match.group(1),
                f"the concurrency group is keyed on the matrix row's {match.group(1)!r} "
                "rather than on the stack's name. Two stacks sharing an environment "
                "would then share a queue, serialising runs against two different "
                "Hetzner projects",
            )


# --------------------------------------------------------------------------
# iac-host-configuration / Platform Data Volume Is Mounted at a Fixed Host Path
# --------------------------------------------------------------------------


class TestTheMountIsNotKeyedOnTheVolumesName(unittest.TestCase):
    """MODIFIED requirement: Platform Data Volume Is Mounted at a Fixed Host
    Path -- "**Discovery SHALL NOT be keyed on the volume's name.** The device
    is identified by the volume's id, so the mount is unaffected by the volume
    being renamed -- which is the property that lets the provisioning layer
    rename a volume without a migration, and the reason the mount path and the
    volume's name are allowed to differ."

    This is the clause that makes the rename safe to perform at all, and it is
    the one a reader is most likely to assume rather than check: the mount path
    stays `/mnt/main-data` while the volume becomes `main`, and the two
    deliberately disagree until a later change moves the path.
    """

    ROLE_TASKS = ROOT / "ansible" / "roles" / "platform_data_volume" / "tasks"

    def _discovery_text(self) -> str:
        """The role's task files with their comments removed.

        Comments are removed rather than read: the role's own prose names the
        volume and the mount path, which is prose about the rename rather than a
        discovery keyed on a name, and a reader that matched it would report an
        offence the role does not commit.
        """
        if not self.ROLE_TASKS.is_dir():
            self.fail(
                "ansible/roles/platform_data_volume/tasks/ does not exist, so this read "
                "has nothing to inspect"
            )
        return uncommented(
            "\n".join(
                path.read_text(encoding="utf-8")
                for path in sorted(self.ROLE_TASKS.rglob("*.yml"))
            )
        )

    def _discovery_task(self) -> dict:
        """The role's on-host device discovery, located by shape: the `find`
        task whose result the device path is resolved from."""
        for path in sorted(self.ROLE_TASKS.rglob("*.yml")):
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            for task in document if isinstance(document, list) else []:
                if not isinstance(task, dict):
                    continue
                for key in ("ansible.builtin.find", "find"):
                    if isinstance(task.get(key), dict):
                        return task[key]
        self.fail(
            "the platform_data_volume role declares no `find` task, so the discovery "
            "this reads cannot be located"
        )

    def test_discovery_is_keyed_on_the_volumes_id_and_on_no_name(self) -> None:
        """SPECIFIED -- "**Discovery SHALL NOT be keyed on the volume's name.**
        The device is identified by the volume's id". DERIVED as to the literal
        `scsi-0HC_Volume_`, which is Hetzner's own documented naming and which
        the role already uses.

        Read over the discovery task's OWN arguments rather than over the
        role's text: a diagnostic that mentions a volume by name is stale prose,
        which the assertion below covers, and is not a discovery keyed on a
        name.
        """
        arguments = self._discovery_task()
        rendered = yaml.safe_dump(arguments)
        self.assertIn(
            "scsi-0HC_Volume_",
            rendered,
            "the platform_data_volume role's discovery no longer matches Hetzner's "
            f"id-keyed device name: {arguments}. The mount's independence from the "
            "volume's name is what this change's rename of the volume rests on",
        )
        names = {
            stack_tfvars(stack).get("volume_name")
            for stack in stack_names()
            if stack_tfvars(stack).get("volume_name")
        }
        self.assertTrue(
            names, "no stack declares a volume name, so this would search for nothing"
        )
        keyed = sorted(name for name in names if name and name in rendered)
        self.assertEqual(
            [],
            keyed,
            f"the discovery is keyed on a volume's name: {keyed}. Keyed on the name, a "
            "renamed volume would stop being discovered -- and the failure would be a "
            "host that converges with no data volume mounted",
        )

    def test_no_task_still_names_a_volume_no_stack_declares(self) -> None:
        """DERIVED -- tasks.md 7.3, not a scenario. The role's own diagnostic
        names the volume it expects to be attached, and after the rename that
        name is one no stack declares: an operator reading the refusal would
        look in the Hetzner console for a volume that is not there.

        Written over the names the stacks declare rather than over a literal, so
        that it reports a stale name whatever the volume is next called. It is
        green on the trunk and goes red when the stacks are renamed and the
        diagnostic is not.
        """
        text = self._discovery_text()
        declared = {
            stack_tfvars(stack).get("volume_name")
            for stack in stack_names()
            if stack_tfvars(stack).get("volume_name")
        }
        self.assertTrue(declared, "no stack declares a volume name")
        candidates = set(EXPECTED_RETIRED_VOLUME_NAMES) - declared
        stale = sorted(name for name in candidates if name in text)
        self.assertEqual(
            [],
            stale,
            f"the platform_data_volume role's tasks name {stale}, which no stack "
            "declares as its volume's name. The mount path and the volume's name "
            "deliberately differ after this change -- which is exactly why a diagnostic "
            "naming the old one reads as a typo rather than as a decision",
        )


# --------------------------------------------------------------------------
# The reads above are reads
# --------------------------------------------------------------------------


class TestTheseReadsDiscriminate(unittest.TestCase):
    """Every read in this file is a static read of a committed file, so a green
    run establishes nothing on its own: a reader that returned the expected
    value whatever it was given would satisfy every assertion above.

    Each test below points one reader at a tree built to falsify it. The
    discovery body has its own discriminator -- it is run over supplied trees
    throughout `TestHostConvergeDiscoveryReadsTheDeclaredGroup`, whose
    accept-rows and refuse-rows falsify one another.
    """

    def _tree(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="stack-naming-reads-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        return directory

    def _stack(self, tree: Path, name: str, terraform: str = "", tfvars: str = "") -> Path:
        directory = tree / "terraform" / "stacks" / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "main.tf").write_text(terraform, encoding="utf-8")
        if tfvars:
            (directory / "terraform.tfvars").write_text(tfvars, encoding="utf-8")
        return directory

    def test_the_declaration_reader_reports_the_field_it_is_given(self) -> None:
        directory = self._stack(self._tree(), "one-somewhere")
        tree = directory.parents[2]
        (directory / DECLARATION_NAME).write_text(
            f"{TARGET_ENVIRONMENT_FIELD}: somewhere\n", encoding="utf-8"
        )
        self.assertEqual({"one-somewhere": "somewhere"}, declared_groups(tree))

    def test_the_declaration_reader_reports_an_absent_field_as_absent(self) -> None:
        directory = self._stack(self._tree(), "one-somewhere")
        tree = directory.parents[2]
        (directory / DECLARATION_NAME).write_text("github_environment: live\n", encoding="utf-8")
        self.assertEqual({"one-somewhere": None}, declared_groups(tree))
        (directory / DECLARATION_NAME).write_text(
            f"{TARGET_ENVIRONMENT_FIELD}: '   '\n", encoding="utf-8"
        )
        self.assertEqual(
            {"one-somewhere": None},
            declared_groups(tree),
            "a blank value is read as a declared group, so a declaration that names the "
            "field and says nothing would pass the census",
        )

    def test_the_module_argument_reader_does_not_read_the_ssh_key_block(self) -> None:
        """The two readers are separated on purpose: the SSH key's own `name` is
        `operator` while the server's is the stack's, and a reader that conflated
        them would report whichever appeared first."""
        directory = self._stack(
            self._tree(),
            "one-somewhere",
            terraform=(
                'module "server" {\n'
                '  environment   = "somewhere"\n'
                '  tenant        = "one"\n'
                '  firewall_name = "main"\n'
                "}\n\n"
                'resource "hcloud_ssh_key" "this" {\n'
                '  name = "operator"\n\n'
                "  labels = {\n"
                '    environment = "somewhere"\n'
                '    tenant      = "one"\n'
                '    managed_by  = "terraform"\n'
                "  }\n"
                "}\n"
            ),
        )
        tree = directory.parents[2]
        arguments = stack_module_arguments("one-somewhere", tree)
        self.assertEqual(
            {"environment": "somewhere", "tenant": "one", "firewall_name": "main"},
            arguments,
            "the module-argument reader saw the SSH key block, whose own `name` would "
            "then be read as a module argument",
        )
        self.assertEqual(
            {
                "name": "operator",
                "environment": "somewhere",
                "tenant": "one",
                "managed_by": "terraform",
            },
            ssh_key_arguments("one-somewhere", tree),
        )

    def test_the_module_argument_reader_reports_a_wrong_value_as_wrong(self) -> None:
        directory = self._stack(
            self._tree(),
            "one-somewhere",
            terraform='module "server" {\n  environment = "swh"\n}\n',
        )
        tree = directory.parents[2]
        self.assertEqual("swh", stack_module_arguments("one-somewhere", tree).get("environment"))

    def test_the_tfvars_reader_reads_only_uncommented_assignments(self) -> None:
        directory = self._stack(
            self._tree(),
            "one-somewhere",
            tfvars=(
                "# name        = \"the-old-name\"\n"
                'name        = "one-somewhere"\n'
                'volume_name = "main"\n'
                "volume_size = 10\n"
            ),
        )
        tree = directory.parents[2]
        self.assertEqual(
            {"name": "one-somewhere", "volume_name": "main"},
            stack_tfvars("one-somewhere", tree),
            "the tfvars reader either read a commented-out assignment -- which would let "
            "a stale name satisfy the census -- or read a numeric one as a string",
        )

    def test_the_inventory_readers_separate_a_source_from_a_group_vars_file(self) -> None:
        tree = self._tree()
        inventory = tree / "ansible" / "inventory" / "group_vars"
        inventory.mkdir(parents=True)
        (tree / "ansible" / "inventory" / f"one-somewhere{SOURCE_SUFFIX}").write_text(
            "plugin: hetzner.hcloud.hcloud\n"
            "keyed_groups:\n"
            "  - key: hcloud_labels.environment\n"
            "    separator: ''\n"
            "  - key: hcloud_labels.tenant\n"
            "    separator: ''\n",
            encoding="utf-8",
        )
        (inventory / "somewhere.yml").write_text("---\n", encoding="utf-8")
        (inventory / "all.yml").write_text("---\n", encoding="utf-8")
        self.assertEqual(["one-somewhere"], inventory_source_names(tree))
        self.assertEqual(["all", "somewhere"], group_vars_names(tree))
        self.assertEqual(
            {"hcloud_labels.environment", "hcloud_labels.tenant"},
            keyed_group_keys("one-somewhere", tree),
        )

    def test_the_keyed_group_reader_reports_a_missing_axis(self) -> None:
        tree = self._tree()
        (tree / "ansible" / "inventory").mkdir(parents=True)
        (tree / "ansible" / "inventory" / f"one-somewhere{SOURCE_SUFFIX}").write_text(
            "plugin: hetzner.hcloud.hcloud\n"
            "keyed_groups:\n"
            "  - key: hcloud_labels.environment\n"
            "    separator: ''\n",
            encoding="utf-8",
        )
        self.assertEqual(
            {"hcloud_labels.environment"},
            keyed_group_keys("one-somewhere", tree),
            "the keyed-group reader reported an axis the source does not declare",
        )


if __name__ == "__main__":
    unittest.main()
