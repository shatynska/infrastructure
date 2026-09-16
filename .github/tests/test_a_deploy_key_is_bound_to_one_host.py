"""Static-assertion tests for binding a deploy key to one host.

Derived from the delta specifications of the OpenSpec change
`bound-a-deploy-key-to-one-host-when-an-environment-holds-two-stacks`, before
any implementation of that change existed -- from those deltas at commit
`f306e94`, the commit holding the approved plan. The path those deltas sit at is
not written here: a change's artifacts move when it is archived, and this
repository's citation convention is to name the change and the artifact in prose
instead.

The deltas span two capabilities. One requirement is ADDED -- *A Host-Scoped
Variable Lives in the Host's Own Vars File*
(`openspec/specs/iac-host-configuration/spec.md`) -- and two are MODIFIED:
*Dynamic Inventory via the hcloud Plugin, One Source per Stack*
(`openspec/specs/iac-host-configuration/spec.md`) and *Each Stack Declares Its
Own Pipeline Configuration* (`openspec/specs/iac-cicd-pipeline/spec.md`). Each
class below names the requirement and the scenario it traces to, and every
assertion is annotated SPECIFIED (it traces to SHALL text or to a scenario in a
delta spec) or DERIVED (it traces to that change's `design.md` or `tasks.md`
rather than to a scenario). See that change's `test-plan.md` for the
scenario-to-test mapping, the baseline, the scenarios deliberately left
uncovered, the obsolete-test candidates this pass is forbidden to act on itself,
and the project questions this file took an assumption on.

The ADDED requirement will not resolve at
`openspec/specs/iac-host-configuration/spec.md` until this change is archived,
which is the bounded interval the delta's own text already accepts: it cites
itself the same way. The two MODIFIED requirements resolve there today.

Why this is a new module rather than a section of an existing one
-----------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. `test_the_platform_stack_deploys_per_stack.py`
already implements the obligation this change relocates -- it resolves a stack's
deploy-key authorisations through the declared Ansible group into that
environment's `group_vars` file -- and re-pointing it through that stack's own
`terraform.tfvars` server name into that host's own vars file is the
implementing author's task (that change's tasks.md 3.1). Its affected assertions
are recorded in that change's `test-plan.md` obsolete list rather than touched
here. Nothing in this file edits, deletes or disables an existing test.

The readers on the AUTHORISATION side are written here rather than imported from
that module, for the same reason the loader below is copied rather than
imported: the module they would come from is the one being rewritten, and a
sibling importing its internals would make this file a constraint on that
rewrite. The readers on the DECLARATION side -- which stacks opt in, and what
each declares -- are imported, because this change does not touch them.

`TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in
`test_ci_configuration.py` reads every module in this directory, so this file is
held to the no-network, no-credential, no-container, no-Terraform constraint by
that class. It is written to satisfy it: standard library, `yaml`, and the
helpers of the modules beside it. It spawns nothing.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or one class, individually selectable:
    python3 -m unittest discover --start-directory .github/tests \\
        -k TestEachStacksHostHasAVarsFileOfItsOwn

    # or one test:
    python3 -m unittest discover --start-directory .github/tests \\
        -k test_every_stack_has_a_host_vars_file_named_for_its_server

Run from the repository root, and through `discover` in both forms: it is
discovery that puts `.github/tests` on `sys.path`, which is what makes the
sibling imports below resolve.

Which assertions here are red before the implementation, and which are guards
-----------------------------------------------------------------------------
Both kinds are present deliberately, and the distinction matters when reading a
run of this file:

- RED until the change lands -- everything that reads
  `ansible/inventory/host_vars/`, which no committed file occupies today. That
  is every test of `TestEachStacksHostHasAVarsFileOfItsOwn`,
  `TestTheDeployKeyAuthorisationsLiveInTheHostsOwnFile`,
  `TestEachStacksOptInIsAnsweredByItsOwnHostsAuthorisation`, the disjointness
  test of `TestAnEnvironmentWideValueStaysInTheEnvironmentsFile`, the backlog
  test of `TestTheUnmetPlacementsAreTheOnesTheRequirementNames`, and
  `TestTheConsumingRolesSendAnOperatorToTheHostsOwnFile`.
- GREEN from the moment they are written -- the two guards that establish the
  other side of a comparison: that some stack opts in, and that the environments'
  own files still supply the variables an environment-wide baseline is made of.
  A pass there is the expected result and establishes what the committed tree
  already says; it is NOT an alarm of the "passed before any implementation
  existed" kind, because their target is not absent.
- GREEN AND MEANT TO STAY GREEN THROUGH THE CHANGE --
  `TestTheUnmetPlacementsAreTheOnesTheRequirementNames`'s first test. The ADDED
  requirement names three placements it does not correct and says it is to be
  read as unmet in those respects; this asserts the tree still matches that
  statement, so the disclosure cannot quietly stop being true in either
  direction.

Every read in this file is a static read of a committed file, so a predicate
that reported no offence whatever it was given would satisfy every guard above,
and would do so most convincingly on the day the move was finished.
`TestTheseReadsDiscriminate` at the end runs each predicate over material this
file supplies, carrying the defect that predicate names.

What no assertion here establishes
----------------------------------
Not that Ansible loads `ansible/inventory/host_vars/` from beside a plugin
inventory source. That is a property of a program's behaviour rather than of a
committed file, this suite may make no network call and hold no credential, and
the change's own `tasks.md` 1.1 carries it as a measurement against the live
plugin. Everything here is conditional on that measurement: if `host_vars/` is
not loaded from there, the file these assertions read is the wrong file and
going green would say nothing.

Nor what either consuming role DOES with the variable. A role consumes a host
variable without regard to which file supplied it, which is what the ADDED
requirement says in as many words, and role behaviour is the Molecule row of
this project's test table rather than this one.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from test_a_stack_and_its_environment_are_named_separately import (
    stack_names,
    stack_tfvars,
)
from test_ci_configuration import ROOT, read_text
from test_environment_agnostic_pipeline import (
    TARGET_GROUP_KEY_HINT,
    environment_declarations,
)
from test_the_platform_stack_deploys_per_stack import (
    PlatformDiscoveryFixtureMixin,
    normalised,
    opting_in,
    platform_opt_ins,
)

# --------------------------------------------------------------------------
# Identifiers this file names, and why each is a constraint of the test layer
# rather than a property the specification states.
# --------------------------------------------------------------------------

INVENTORY_SEGMENT = "ansible/inventory"
GROUP_VARS_SEGMENT = f"{INVENTORY_SEGMENT}/group_vars"
HOST_VARS_SEGMENT = f"{INVENTORY_SEGMENT}/host_vars"
STACK_ROOT_SEGMENT = "terraform/stacks"
DECLARATION_NAME = "pipeline.yml"

# `host_vars` is the directory name Ansible itself resolves inventory variables
# from, beside `group_vars`. SPECIFIED only as "a host's own vars file, named
# for the Hetzner server name that host carries" -- the requirement fixes the
# KEY and not the directory. The directory is DERIVED, from Ansible's own
# resolution and from `test_host_converge_workflow.py`, which already names
# `ansible/inventory/host_vars/` as one of the two places a vaulted inventory
# variable may live.
HOST_VARS_DIRNAME = "host_vars"

# The Terraform variable a stack's `terraform.tfvars` declares its server's name
# in, which is what the host vars file is named for. SPECIFIED -- "named for the
# Hetzner server name that host carries", and "the host vars file named for the
# server that stack's committed Terraform configuration declares SHALL exist".
# The spelling `name` is read off the committed stacks, both of which declare
# it, and is the same string `test_a_stack_and_its_environment_are_named_
# separately.py` already resolves a server's name through.
SERVER_NAME_VARIABLE = "name"

# The list a host's vars file enumerates its deploy-key authorisations in, and
# the keys naming each application and its public half within it. DERIVED from
# the committed `group_vars` files, which already carry exactly this shape: the
# requirement says "the deploy-key authorisations a host grants" and fixes no
# spelling. The move this change makes is of a list, not of a schema -- that
# change's tasks.md 2.1 says "moved verbatim" -- so following the committed
# spelling is following what the move produces.
DEPLOY_APPS_FIELD = "deploy_apps"
APPLICATION_NAME_FIELD = "name"
APPLICATION_KEY_FIELD = "public_key"

# The application name a host's deploy-key authorisations enumerate for the
# shared platform stack. DERIVED from the committed tree for the same reason:
# it is the name `deploy_apps` already lists, and the name of the `platform/`
# directory whose stack definition that deploy delivers.
PLATFORM_APPLICATION = "platform"

# The three placements the ADDED requirement names as ones it does not correct:
# "All three sit in an environment's `group_vars` today." SPECIFIED -- the
# requirement enumerates them itself, which is what makes the disclosure
# checkable rather than a claim in prose.
UNMET_PLACEMENTS = (
    "hardening_ssh_allowed_cidrs",
    "hardening_web_allowed_cidrs",
    "ops_user_accounts",
)

# The backlog entry the ADDED requirement cites by name: "they are tracked in
# `docs/backlog.md` as `put-the-remaining-host-scoped-variables-on-the-host-
# axis`". SPECIFIED -- the requirement states the name, and a citation of a name
# nothing carries is the failure the requirement's own paragraph exists to
# avoid.
BACKLOG = ROOT / "docs" / "backlog.md"
BACKLOG_ENTRY = "put-the-remaining-host-scoped-variables-on-the-host-axis"

# The two roles whose refusal message tells an operator where to set the
# variable. DERIVED -- no scenario states a message, and the ADDED requirement
# says outright that nothing here obliges a role to change. What this traces to
# is that change's tasks.md 2.4: the message is what an operator reads AS a
# converge refuses, so a stale one sends them to edit a file that no longer
# supplies the variable.
CONSUMING_ROLE_TASKS = (
    "ansible/roles/deploy_user/tasks/main.yml",
    "ansible/roles/image_prune/tasks/main.yml",
)


def _base(root: Path | None) -> Path:
    return ROOT if root is None else root


# --------------------------------------------------------------------------
# Reading a host's own vars file
# --------------------------------------------------------------------------


class AnsibleTolerantLoader(yaml.SafeLoader):
    """`SafeLoader`, plus the two tags Ansible's own YAML carries.

    An inventory variables file may carry `!vault` blocks, which
    `yaml.safe_load` refuses -- so a reader built on it would fail to parse the
    very files this module cross-checks. No host vars file carries one today,
    which the ADDED requirement states in as many words; a `group_vars` file
    does, and this module reads those too.

    NAMED EXPLICITLY, never a catch-all, which is the whole of the rule this
    copies. `_AnsibleTolerantLoader` in
    `ansible/scripts/select_molecule_roles.py` is the established shape and its
    docstring states why: a multi-constructor over `!` maps every unknown tag to
    `None`, turning a document this reader has never seen into an EMPTY one
    rather than into a refusal. Here that would be worse than there --
    `deploy_apps` read out of an empty document is an absent list, so the
    cross-check below would pass vacuously on the very pair it compares, failing
    open on the one guard this change adds.

    It is copied rather than imported for two reasons, and the second is the one
    that matters. An import of a module outside this directory is not something
    this suite's own dependency audit admits, and
    `test_the_platform_stack_deploys_per_stack.py`, which carries an identical
    loader, is the module this change rewrites -- importing its internals would
    make this file a constraint on that rewrite. The refusal is asserted here
    rather than inherited: see `TestTheseReadsDiscriminate`.
    """


for _tag in ("!vault", "!unsafe"):
    AnsibleTolerantLoader.add_constructor(
        _tag, lambda loader, node: loader.construct_scalar(node)
    )


class UnreadableVarsFile(AssertionError):
    """An inventory variables file that cannot be parsed, refused rather than
    read as authorising nothing -- and rather than read as authorising
    everything."""


def inventory_variables(path: Path) -> dict:
    """One inventory variables file as a mapping, refused rather than emptied."""
    try:
        document = yaml.load(path.read_text(encoding="utf-8"), Loader=AnsibleTolerantLoader)
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as error:
        raise UnreadableVarsFile(
            f"{path.name}: cannot be parsed ({error}), so which variables this file "
            "supplies is unknown. Refused rather than read as supplying none"
        ) from error
    if document is None:
        return {}
    if not isinstance(document, dict):
        raise UnreadableVarsFile(
            f"{path.name}: is not a mapping, so it declares no variables at all"
        )
    return document


def _variables_under(base: Path) -> dict:
    found: dict = {}
    if not base.is_dir():
        return found
    for path in sorted(base.glob("*.yml")):
        found[path.stem] = inventory_variables(path)
    return found


def group_vars_documents(root: Path | None = None) -> dict:
    """Ansible group -> the mapping that group's `group_vars` file supplies."""
    return _variables_under(_base(root) / "ansible" / "inventory" / "group_vars")


def host_vars_documents(root: Path | None = None) -> dict:
    """Host name -> the mapping that host's own vars file supplies.

    A host with no file of its own is ABSENT from this mapping, which the
    cross-checks below report by name; that is not the same as a host whose file
    supplies nothing, which is a host the converge gives no variables to.
    """
    return _variables_under(_base(root) / "ansible" / "inventory" / HOST_VARS_DIRNAME)


def _authorisations_of(document: dict) -> dict:
    """The `{application: public half}` one variables mapping enumerates.

    An entry naming an application but no key maps to the empty string, which is
    an authorisation this reader saw and could not identify a keypair for --
    distinct from the application being absent.
    """
    entries = document.get(DEPLOY_APPS_FIELD)
    found: dict = {}
    if not isinstance(entries, list):
        return found
    for entry in entries:
        if isinstance(entry, dict) and entry.get(APPLICATION_NAME_FIELD):
            found[str(entry[APPLICATION_NAME_FIELD])] = str(
                entry.get(APPLICATION_KEY_FIELD) or ""
            )
        elif isinstance(entry, str):
            found[entry] = ""
    return found


def host_authorisations(root: Path | None = None) -> dict:
    """Host name -> the `{application: public half}` that host's own vars file
    authorises a deploy key for."""
    return {
        host: _authorisations_of(document)
        for host, document in host_vars_documents(root).items()
    }


def declared_servers(root: Path | None = None) -> dict:
    """Stack directory -> the server name its committed Terraform declares.

    `None` where the stack's `terraform.tfvars` declares none, which is itself
    reported: a stack whose server has no name has no host vars file it could be
    named for.
    """
    found: dict = {}
    for stack in stack_names(root):
        value = stack_tfvars(stack, root).get(SERVER_NAME_VARIABLE)
        found[stack] = value if isinstance(value, str) and value.strip() else None
    return found


def declaring_stacks(root: Path | None = None) -> list:
    """The stacks carrying a pipeline declaration, sorted.

    The obligation to carry a host vars file is stated of those: "A stack that
    carries a pipeline declaration SHALL carry an inventory source of its own,
    the `group_vars` file its declared group names SHALL exist, and the host
    vars file named for the server that stack's committed Terraform
    configuration declares SHALL exist."
    """
    return sorted(
        name
        for name, declaration in environment_declarations(root).items()
        if declaration.path is not None
    )


# --------------------------------------------------------------------------
# The offence predicates.
#
# Each takes every side it compares as an argument rather than reading it, so
# that the discriminating class at the end of this file can hand it a
# disagreeing set. Over the committed tree a predicate reading the tree itself
# would compare two stacks and would pass, once the change lands, having read a
# set small enough that returning the empty list unconditionally satisfies it.
# --------------------------------------------------------------------------


def missing_host_vars_offences(stacks, servers, present) -> list:
    """Every stack carrying a pipeline declaration whose declared server has no
    committed host vars file."""
    offences = []
    for stack in sorted(stacks):
        server = servers.get(stack)
        if not server:
            offences.append(
                f"{STACK_ROOT_SEGMENT}/{stack}/{DECLARATION_NAME} declares a pipeline "
                f"and {STACK_ROOT_SEGMENT}/{stack}/terraform.tfvars names no server, so "
                "there is no name a host vars file could be named for and the converge "
                "has no host variables to apply"
            )
        elif server not in present:
            offences.append(
                f"{STACK_ROOT_SEGMENT}/{stack}/ declares the server {server!r} and "
                f"{HOST_VARS_SEGMENT}/{server}.yml does not exist, so this stack can be "
                "provisioned but not converged -- the files present are "
                f"{sorted(present)}"
            )
    return offences


def orphaned_host_vars_offences(servers, present) -> list:
    """Every committed host vars file named for a server no stack declares.

    The other reading of the same clause, and the one a rename produces: the
    stack is renamed, the file is not, and the stack now resolves to a file that
    does not exist while a file nothing resolves to sits beside it.
    """
    declared = {server for server in servers.values() if server}
    return [
        f"{HOST_VARS_SEGMENT}/{host}.yml carries variables for a host no stack's "
        f"committed Terraform declares -- the servers declared are {sorted(declared)}. "
        "A renamed server leaves its variables behind rather than taking them"
        for host in sorted(set(present) - declared)
    ]


def group_vars_authorisation_offences(documents) -> list:
    """Every `group_vars` file supplying the deploy-key authorisations.

    The ADDED requirement's own prohibition: a variable whose blast radius is one
    host "SHALL NOT be supplied from an environment's `group_vars`", and an entry
    written there "would authorise both hosts".
    """
    return [
        f"{GROUP_VARS_SEGMENT}/{group}.yml supplies `{DEPLOY_APPS_FIELD}`, so every host "
        f"in the `{group}` group authorises {sorted(_authorisations_of(document))} -- "
        "one entry authorising a second tenant's host is the widening this placement "
        "exists to prevent"
        for group, document in sorted(documents.items())
        if DEPLOY_APPS_FIELD in document
    ]


def repeated_variable_offences(groups, hosts) -> list:
    """Every variable supplied from both an environment's file and a host's.

    Scenario "A value that is a property of the environment": an environment-wide
    value "SHALL NOT be repeated in each host's vars file, which would make an
    environment-wide correction a per-host edit that nothing enumerates".
    """
    offences = []
    for host, document in sorted(hosts.items()):
        for group, group_document in sorted(groups.items()):
            shared = sorted(set(document) & set(group_document))
            if shared:
                offences.append(
                    f"{HOST_VARS_SEGMENT}/{host}.yml and {GROUP_VARS_SEGMENT}/{group}.yml "
                    f"both supply {shared}. A value is either a property of the "
                    "environment or of the host; supplied from both, an environment-wide "
                    "correction is a per-host edit that nothing enumerates"
                )
    return offences


def duplicate_public_half_offences(authorisations) -> list:
    """Every public half more than one host authorises.

    The invariant the ADDED requirement states outright: "one leaked private half
    SHALL reach one host", and "no single entry SHALL authorise a deploy to more
    than one host". Read over every application rather than over the platform
    stack alone -- the scenario is written of "one application", and an
    application deployed to two hosts "SHALL do so with two keypairs".
    """
    if not authorisations:
        return [
            f"no committed file under {HOST_VARS_SEGMENT}/ enumerates a deploy-key "
            "authorisation, so this comparison reads nothing"
        ]
    holders: dict = {}
    for host, entries in sorted(authorisations.items()):
        for application, key in sorted(entries.items()):
            if key:
                holders.setdefault(key, []).append(f"{host}/{application}")
    return sorted(
        f"{names} authorise one public half ending {key[-24:]!r}, so one leaked private "
        "half deploys to more than one host"
        for key, names in holders.items()
        if len(names) > 1
    )


def opt_in_authorisation_offences(opt_ins, servers, authorisations) -> list:
    """Why a stack's declaration and its own host's vars file disagree, as
    messages naming BOTH files; empty where they agree.

    ONE-DIRECTIONAL, deliberately. A host that authorises the key while its
    stack's declaration does not opt in is the deliberate interval the MODIFIED
    requirement accepts -- "that interval being the deliberate state of a host
    prepared before its deploy path exists" -- and is accepted here rather than
    reported.

    PER STACK, deliberately. Every opt-in is resolved through that stack's own
    declared server, so two stacks sharing an Ansible group carry two
    obligations: "the authorisation present on the other host SHALL NOT be read
    as satisfying it".
    """
    offences = []
    for stack in sorted(opt_ins):
        if opt_ins.get(stack) is not True:
            continue
        server = servers.get(stack)
        if not server:
            offences.append(
                f"{STACK_ROOT_SEGMENT}/{stack}/{DECLARATION_NAME} declares that the "
                "shared platform stack is deployed to this stack and "
                f"{STACK_ROOT_SEGMENT}/{stack}/terraform.tfvars names no server, so no "
                "host vars file says whether its host authorises the deploy key"
            )
            continue
        authorised = authorisations.get(server)
        if authorised is None:
            offences.append(
                f"{STACK_ROOT_SEGMENT}/{stack}/{DECLARATION_NAME} opts in to the platform "
                f"deploy and {HOST_VARS_SEGMENT}/{server}.yml does not exist, so the "
                "deploy would authenticate with a key nothing has told that host to "
                "accept"
            )
        elif PLATFORM_APPLICATION not in authorised:
            offences.append(
                f"{STACK_ROOT_SEGMENT}/{stack}/{DECLARATION_NAME} opts in to the platform "
                f"deploy and {HOST_VARS_SEGMENT}/{server}.yml does not enumerate "
                f"`{PLATFORM_APPLICATION}` among `{DEPLOY_APPS_FIELD}` (it names "
                f"{sorted(authorised)}), so the deploy would fail authenticating after "
                "the tailnet join and after any approval. Another host's authorisation "
                "does not answer this stack's opt-in"
            )
    return offences


def deploy_apps_refusal_messages(path: Path) -> list:
    """The `fail_msg` of every task asserting that `deploy_apps` was supplied.

    Read out of the parsed task list rather than out of the file's lines, and
    that is not a stylistic preference: both roles write the message as a FOLDED
    scalar, so `group_vars` and `deploy_apps` never share a line and a line-wise
    read reports nothing over exactly the defect this exists to catch.

    Selected by the assertion's own `that:` clauses, so that the two OTHER
    refusals in these files -- the heartbeat ping key's and the hardening
    CIDRs' -- are not read. Both name an environment's file legitimately: the
    values they refuse over are ones this change deliberately leaves there.
    """
    document = yaml.load(path.read_text(encoding="utf-8"), Loader=AnsibleTolerantLoader)
    if not isinstance(document, list):
        raise UnreadableVarsFile(f"{path.name}: is not a list of tasks")
    messages = []
    for task in document:
        if not isinstance(task, dict):
            continue
        for key in ("ansible.builtin.assert", "assert"):
            body = task.get(key)
            if not isinstance(body, dict):
                continue
            clauses = body.get("that")
            clauses = clauses if isinstance(clauses, list) else [clauses]
            if any(DEPLOY_APPS_FIELD in str(clause) for clause in clauses):
                messages.append(str(body.get("fail_msg") or ""))
    return messages


# --------------------------------------------------------------------------
# iac-host-configuration / Dynamic Inventory via the hcloud Plugin, One Source
# per Stack (MODIFIED) -- the host axis
# --------------------------------------------------------------------------


class TestEachStacksHostHasAVarsFileOfItsOwn(unittest.TestCase):
    """MODIFIED requirement: *Dynamic Inventory via the hcloud Plugin, One
    Source per Stack* (`openspec/specs/iac-host-configuration/spec.md`) -- "the
    host vars file named for the server that stack's committed Terraform
    configuration declares SHALL exist", and "It does always add a **host vars
    file**, because a stack provisions a host of its own and the variables
    scoped to that host have nowhere else they may go".

    Also the ADDED requirement's two scenarios about the filename: "A stack whose
    declared server has no vars file is reported" and "A host vars file is keyed
    on the name Terraform declares".

    RED until the change lands: no committed file occupies
    `ansible/inventory/host_vars/` today.
    """

    def test_every_stack_carrying_a_declaration_declares_a_server_name(self) -> None:
        """SPECIFIED -- the clause resolves a filename through the server name a
        stack's Terraform declares, so a stack declaring none has no name the
        file could be keyed on. GREEN today; it is the other side of the
        comparison below, and without it that comparison passes over a set of
        stacks whose servers are all anonymous."""
        stacks = declaring_stacks()
        self.assertTrue(
            stacks,
            f"no directory under {STACK_ROOT_SEGMENT}/ carries a pipeline declaration, "
            "so the obligation below is stated of nothing",
        )
        servers = declared_servers()
        anonymous = sorted(stack for stack in stacks if not servers.get(stack))
        self.assertEqual(
            [],
            anonymous,
            f"these stacks carry a pipeline declaration and name no server in their "
            f"`terraform.tfvars`: {anonymous}",
        )

    def test_every_stack_has_a_host_vars_file_named_for_its_server(self) -> None:
        """SPECIFIED -- scenario "A stack that can be provisioned but not
        converged is reported", whose WHEN now includes "or the server it
        declares has no host vars file"; and scenario "A stack whose declared
        server has no vars file is reported"."""
        offences = missing_host_vars_offences(
            declaring_stacks(), declared_servers(), set(host_vars_documents())
        )
        self.assertEqual([], offences, "; ".join(offences))

    def test_no_host_vars_file_is_named_for_a_server_no_stack_declares(self) -> None:
        """SPECIFIED -- scenario "A host vars file is keyed on the name Terraform
        declares": a stack renaming its server without renaming the file is a
        mismatch that "SHALL be reported rather than resolved". A rename leaves
        both halves of that: a stack resolving to nothing, which the test above
        reports, and a file nothing resolves to, which this one does."""
        present = set(host_vars_documents())
        self.assertTrue(
            present,
            f"no committed file sits under {HOST_VARS_SEGMENT}/, so this read has "
            "nothing to compare against the servers the stacks declare",
        )
        offences = orphaned_host_vars_offences(declared_servers(), present)
        self.assertEqual([], offences, "; ".join(offences))


# --------------------------------------------------------------------------
# iac-host-configuration / A Host-Scoped Variable Lives in the Host's Own Vars
# File (ADDED)
# --------------------------------------------------------------------------


class TestTheDeployKeyAuthorisationsLiveInTheHostsOwnFile(unittest.TestCase):
    """ADDED requirement: *A Host-Scoped Variable Lives in the Host's Own Vars
    File* (`openspec/specs/iac-host-configuration/spec.md`) -- "The deploy-key
    authorisations a host grants are such a variable, and the invariant behind
    them is stated rather than left implied: one leaked private half SHALL reach
    one host."

    And its scenario "Two stacks share an environment", read against the
    committed tree: each host's authorisation in that host's own file, and
    neither in the environment's `group_vars` file.

    RED until the change lands.
    """

    def _authorisations(self) -> dict:
        authorisations = host_authorisations()
        self.assertTrue(
            authorisations,
            f"no committed file sits under {HOST_VARS_SEGMENT}/, so every assertion "
            "about what a host's own file authorises reads nothing",
        )
        return authorisations

    def test_no_environments_file_supplies_the_deploy_key_authorisations(self) -> None:
        """SPECIFIED -- "Such a variable SHALL NOT be supplied from an
        environment's `group_vars`", and the scenario's AND clause: "neither SHALL
        be enumerated in the environment's `group_vars` file, where one entry
        would authorise both hosts"."""
        documents = group_vars_documents()
        self.assertTrue(
            documents,
            f"no committed file sits under {GROUP_VARS_SEGMENT}/, so this prohibition "
            "reads nothing",
        )
        offences = group_vars_authorisation_offences(documents)
        self.assertEqual([], offences, "; ".join(offences))

    def test_a_hosts_own_file_supplies_its_authorisations(self) -> None:
        """SPECIFIED -- "A variable SHALL be supplied from a host's own vars
        file"; "A deploy key's public half therefore sits in the vars file of the
        one host it authorises".

        The converse of the prohibition above, and not implied by it: a tree that
        deleted the list outright would satisfy that one.
        """
        authorisations = self._authorisations()
        empty = sorted(host for host, entries in authorisations.items() if not entries)
        self.assertEqual(
            [],
            empty,
            "these hosts have a vars file of their own that authorises no deploy key at "
            f"all: {empty}. Every host this repository provisions authorises at least "
            "the shared platform stack",
        )

    def test_no_public_half_is_authorised_on_two_hosts(self) -> None:
        """SPECIFIED -- the scenario's THEN: "each naming a keypair of its own",
        and "no single entry SHALL authorise a deploy to more than one host".

        Read over the committed public halves, which are the readable half of the
        invariant: a private half is generated out of band and never enters this
        repository, so the failure this can see is two hosts enumerating one
        public half.
        """
        offences = duplicate_public_half_offences(self._authorisations())
        self.assertEqual([], offences, "; ".join(offences))


class TestAnEnvironmentWideValueStaysInTheEnvironmentsFile(unittest.TestCase):
    """ADDED requirement: *A Host-Scoped Variable Lives in the Host's Own Vars
    File* -- scenario "A value that is a property of the environment".

    The half of the requirement that is not about moving anything: "An
    environment's `group_vars` file SHALL carry only what is true of every host
    in that environment whichever tenant owns it". Without it the requirement is
    satisfiable by emptying `group_vars` into per-host files, which is the
    opposite defect and is the one the scenario's AND clause names.
    """

    def test_the_environments_files_still_supply_an_environment_wide_baseline(self) -> None:
        """SPECIFIED -- "it SHALL be supplied from that environment's `group_vars`
        file". GREEN today and meant to stay green: this change moves one variable
        and leaves the baseline where it is."""
        documents = group_vars_documents()
        empty = sorted(group for group, document in documents.items() if not document)
        self.assertTrue(documents, f"no committed file sits under {GROUP_VARS_SEGMENT}/")
        self.assertEqual(
            [],
            empty,
            f"these environments' files supply no variable at all: {empty}. An "
            "environment-wide baseline read from nowhere is not a baseline",
        )

    def test_no_variable_is_supplied_from_both_an_environments_file_and_a_hosts(self) -> None:
        """SPECIFIED -- the scenario's AND clause: an environment's value "SHALL
        NOT be repeated in each host's vars file".

        Asserted as disjointness rather than as a list of names, because the
        requirement states the rule and not the roster. A variable in both files
        also resolves by precedence rather than by intent, which is a fact about
        Ansible that the change's own tasks.md 1.2 measures rather than assumes.
        """
        hosts = host_vars_documents()
        self.assertTrue(
            hosts,
            f"no committed file sits under {HOST_VARS_SEGMENT}/, so this disjointness "
            "holds over an empty set",
        )
        offences = repeated_variable_offences(group_vars_documents(), hosts)
        self.assertEqual([], offences, "; ".join(offences))


class TestTheUnmetPlacementsAreTheOnesTheRequirementNames(unittest.TestCase):
    """ADDED requirement: *A Host-Scoped Variable Lives in the Host's Own Vars
    File* -- "The placements this requirement's own change examined and did not
    correct are named here rather than left to be discovered, and this
    requirement SHALL be read as unmet in those respects."

    A general SHALL the tree knowingly breaks in three places is read as advisory
    the first time someone notices, and `openspec validate` cannot see a
    variable's placement. So the requirement names the three and says "This
    paragraph is replaced when those three move, and not before". This class
    asserts the disclosure is true of the tree in BOTH directions: the three are
    still where it says they are, and none of them has quietly acquired a
    per-host placement the paragraph would then be wrong about.
    """

    def test_the_three_named_placements_are_where_the_requirement_says_they_are(self) -> None:
        """SPECIFIED -- "All three sit in an environment's `group_vars` today."

        GREEN today and meant to stay green through this change. It goes red when
        one of the three moves, which is the moment the requirement's own
        paragraph has to be replaced -- and the paragraph has no other alarm.
        """
        groups = group_vars_documents()
        self.assertTrue(groups, f"no committed file sits under {GROUP_VARS_SEGMENT}/")
        supplied = {name for document in groups.values() for name in document}
        missing = sorted(set(UNMET_PLACEMENTS) - supplied)
        self.assertEqual(
            [],
            missing,
            f"these variables are named by the requirement as sitting in an "
            f"environment's `group_vars` today and no such file supplies them: {missing}. "
            "If they have moved, the requirement's paragraph naming them as unmet is to "
            "be replaced",
        )
        hosts = host_vars_documents()
        moved = sorted(
            f"{host}: {sorted(set(UNMET_PLACEMENTS) & set(document))}"
            for host, document in hosts.items()
            if set(UNMET_PLACEMENTS) & set(document)
        )
        self.assertEqual(
            [],
            moved,
            "these host vars files supply a variable the requirement names as one it "
            f"did NOT move: {moved}. Moving it is legitimate work; doing so without "
            "replacing that paragraph leaves the specification asserting something of "
            "the tree that is false",
        )

    def test_the_backlog_entry_the_requirement_cites_exists(self) -> None:
        """SPECIFIED -- "they are tracked in `docs/backlog.md` as
        `put-the-remaining-host-scoped-variables-on-the-host-axis`". The
        requirement states the name, so the two have to agree; a citation of an
        entry nothing carries is the deferral recorded nowhere.

        RED until the change lands -- that change's tasks.md 5.1 adds the entry.
        """
        self.assertTrue(BACKLOG.is_file(), f"{BACKLOG} does not exist")
        self.assertIn(
            BACKLOG_ENTRY,
            read_text(BACKLOG),
            f"docs/backlog.md carries no entry named {BACKLOG_ENTRY!r}, which the "
            "requirement cites as where the three placements it does not correct are "
            "tracked",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Each Stack Declares Its Own Pipeline Configuration
# (MODIFIED) -- the opt-in is answered per host
# --------------------------------------------------------------------------


class TestEachStacksOptInIsAnsweredByItsOwnHostsAuthorisation(unittest.TestCase):
    """MODIFIED requirement: *Each Stack Declares Its Own Pipeline
    Configuration* (`openspec/specs/iac-cicd-pipeline/spec.md`) -- "A stack
    declaring that the platform stack is deployed to it SHALL also authorise
    that deploy on the host, by enumerating the platform application among the
    deploy-key authorisations in the **host vars file of the host that stack
    provisions** ... It SHALL NOT be the `group_vars` file of the declared
    Ansible group".

    Scenarios "A stack opting in without authorising the deploy on its host is
    refused" and "A host authorising the deploy key before the pipeline is
    pointed at it is accepted", both of whose WHEN clauses moved from the
    `group_vars` file to the host vars file.

    THE CHECK LIVES HERE rather than in the workflow's discovery, which is where
    the existing module already put it and which this change does not revisit: it
    fails the pull request rather than the deploy, and `deploy_apps` is a list of
    mappings, which the workflows' line readers are the wrong tool for. This
    module is reached by the required status check through the suite as a whole
    -- `test_ci_configuration.TestTheSuiteIsWiredIntoTheRequiredCheck` is what
    asserts that, and it is not restated here.
    """

    def test_there_is_an_opt_in_to_check(self) -> None:
        """SPECIFIED -- without this, the cross-check below passes over an empty
        set of stacks on exactly the day the field is forgotten. GREEN today:
        both committed stacks opt in."""
        self.assertTrue(
            opting_in(),
            "no stack's declaration opts in to the platform deploy, so the comparison "
            "between a declaration and its own host's authorisations reads one side of "
            "it",
        )

    def test_every_opted_in_stacks_own_host_authorises_the_platform_deploy_key(self) -> None:
        """SPECIFIED -- see the class docstring, and the requirement's "Each
        stack's opt-in SHALL be answered by its own host's authorisation"."""
        self.test_there_is_an_opt_in_to_check()
        offences = opt_in_authorisation_offences(
            platform_opt_ins(), declared_servers(), host_authorisations()
        )
        self.assertEqual([], offences, "; ".join(offences))

    def test_a_host_prepared_before_its_deploy_path_is_not_reported(self) -> None:
        """SPECIFIED -- scenario "A host authorising the deploy key before the
        pipeline is pointed at it is accepted": "discovery and the required status
        check SHALL both accept the tree, that interval being the deliberate state
        of a host prepared before its deploy path exists".

        Asserting it here rather than only in the discriminator is what keeps this
        check from being repaired into a two-directional one -- the converse is
        deliberately not required, and this is the assertion that says so.
        """
        authorisations = host_authorisations()
        prepared = sorted(
            host
            for host, entries in authorisations.items()
            if PLATFORM_APPLICATION in entries
        )
        self.assertTrue(
            prepared,
            f"no file under {HOST_VARS_SEGMENT}/ authorises the platform deploy key at "
            "all, so this assertion reads nothing -- and no stack could opt in without "
            f"failing the check above. The hosts read were {sorted(authorisations)}",
        )
        offences = opt_in_authorisation_offences(
            {stack: None for stack in declaring_stacks()},
            declared_servers(),
            authorisations,
        )
        self.assertEqual(
            [],
            offences,
            "a host authorising the platform deploy key while its stack's declaration "
            f"does not opt in was reported as an offence: {offences}",
        )


class HostVarsFixtureMixin(PlatformDiscoveryFixtureMixin):
    """Builds a synthetic tree carrying stacks, their servers and their hosts'
    vars files.

    Extends the declaration fixture the sibling modules already use -- the
    declarations it writes are built from a COMMITTED declaration, same filename,
    same field names, different values -- with the two files this change's
    resolution path adds to it: each stack's `terraform.tfvars`, which names the
    server, and each host's own vars file, which carries the authorisations.

    A synthetic tree is the only way the two-stacks-in-one-environment case can
    be expressed at all. No committed stack set expresses it: this repository has
    one tenant, so environment, stack and host are one-to-one, and the whole
    point of the change is what happens when they stop being.
    """

    def _scratch(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="host-scoped-variables-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        return directory

    def _host_tree(self, stacks, host_vars=None, group_vars=None) -> Path:
        """`stacks` maps a stack directory name to `(opt_in, group, server)`;
        `server` may be `None` for a stack whose `terraform.tfvars` names none.

        `host_vars` maps a host name to the `deploy_apps` list its own file
        carries, or to a mapping for a file carrying other variables; a host
        absent from it gets no file at all. `group_vars` maps a group name to the
        mapping its file carries.
        """
        scratch = self._scratch()
        declarations = {}
        for stack, (opt_in, group, _) in stacks.items():
            mapping = self._declaration(stack, opt_in)
            for key in [key for key in mapping if TARGET_GROUP_KEY_HINT in normalised(key)]:
                mapping[key] = group
            declarations[stack] = mapping
        self._write_tree(scratch, declarations)
        for stack, (_, _, server) in stacks.items():
            if server is not None:
                (scratch / "terraform" / "stacks" / stack / "terraform.tfvars").write_text(
                    f'{SERVER_NAME_VARIABLE} = "{server}"\n', encoding="utf-8"
                )
        inventory = scratch / "ansible" / "inventory"
        for name, contents in (
            (HOST_VARS_DIRNAME, host_vars or {}),
            ("group_vars", group_vars or {}),
        ):
            directory = inventory / name
            directory.mkdir(parents=True, exist_ok=True)
            for stem, value in contents.items():
                document = value if isinstance(value, dict) else {DEPLOY_APPS_FIELD: value}
                (directory / f"{stem}.yml").write_text(
                    yaml.safe_dump(document, sort_keys=True), encoding="utf-8"
                )
        return scratch

    def _offences_over(self, tree: Path) -> list:
        """The whole resolution path, run end to end over a synthetic tree:
        declaration -> declared server -> that host's own vars file."""
        return opt_in_authorisation_offences(
            platform_opt_ins(tree), declared_servers(tree), host_authorisations(tree)
        )


class TestTwoStacksInOneEnvironmentEachOweTheirOwnAuthorisation(
    HostVarsFixtureMixin, unittest.TestCase
):
    """MODIFIED requirement: *Each Stack Declares Its Own Pipeline
    Configuration* -- scenario "Two stacks in one environment each owe their own
    authorisation", and the ADDED requirement's scenario "Two stacks share an
    environment".

    This is the tree the change exists to prevent and the one no committed stack
    set can express. Under the resolution this change retires -- through the
    declared Ansible group into that environment's `group_vars` file -- both
    stacks resolve to ONE file, so one `platform` entry answers both opt-ins and
    the required status check passes on exactly this tree. Every assertion here
    is therefore about a tree that must be built rather than read.
    """

    GROUP = "live"
    KEY_ALPHA = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAlpha deploy@alpha"
    KEY_BETA = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAbeta deploy@beta"

    def _stacks(self):
        return {
            "alpha-live": (True, self.GROUP, "alpha-live"),
            "beta-live": (True, self.GROUP, "beta-live"),
        }

    def _entry(self, key: str) -> list:
        return [{APPLICATION_NAME_FIELD: PLATFORM_APPLICATION, APPLICATION_KEY_FIELD: key}]

    def test_the_two_stacks_share_one_group_and_provision_two_hosts(self) -> None:
        """SPECIFIED -- the scenario's WHEN, asserted of the fixture before
        anything is concluded from it. A fixture whose two stacks silently
        declared two groups would make every assertion below pass while testing
        the case this change does not change."""
        tree = self._host_tree(
            self._stacks(),
            host_vars={
                "alpha-live": self._entry(self.KEY_ALPHA),
                "beta-live": self._entry(self.KEY_BETA),
            },
        )
        declarations = environment_declarations(tree)
        self.assertEqual(
            {self.GROUP},
            {declaration.target_group for declaration in declarations.values()},
            "the fixture's two stacks do not declare one Ansible group between them, so "
            "it does not express two stacks in one environment",
        )
        self.assertEqual(
            {"alpha-live": "alpha-live", "beta-live": "beta-live"},
            declared_servers(tree),
            "the fixture's two stacks do not declare two servers",
        )
        self.assertEqual(["alpha-live", "beta-live"], opting_in(tree))

    def test_two_hosts_that_each_authorise_the_key_yield_no_offence(self) -> None:
        """SPECIFIED -- the converse the refusal below needs. A check that
        refused every two-stack tree would satisfy the scenario while making a
        second tenant impossible to add, which is the state this change exists to
        make possible rather than to forbid."""
        tree = self._host_tree(
            self._stacks(),
            host_vars={
                "alpha-live": self._entry(self.KEY_ALPHA),
                "beta-live": self._entry(self.KEY_BETA),
            },
        )
        self.assertEqual([], self._offences_over(tree))

    def test_the_stack_whose_host_does_not_authorise_is_named(self) -> None:
        """SPECIFIED -- "the required status check SHALL fail for the stack whose
        host does not, naming that stack and the host vars file expected of
        it"."""
        tree = self._host_tree(
            self._stacks(),
            host_vars={"alpha-live": self._entry(self.KEY_ALPHA)},
        )
        offences = self._offences_over(tree)
        self.assertEqual(1, len(offences), f"expected exactly one offence, got {offences}")
        self.assertIn("beta-live", offences[0])
        self.assertIn(f"{HOST_VARS_SEGMENT}/beta-live.yml", offences[0])
        self.assertIn(f"{STACK_ROOT_SEGMENT}/beta-live/{DECLARATION_NAME}", offences[0])

    def test_the_other_hosts_authorisation_does_not_satisfy_it(self) -> None:
        """SPECIFIED -- "the authorisation present on the other host SHALL NOT be
        read as satisfying it".

        The same fixture read from the other side, and the assertion that fails
        under the resolution this change retires: the two stacks' declared group
        is one, so a check resolving through the group finds `platform`
        authorised and reports nothing.
        """
        tree = self._host_tree(
            self._stacks(),
            host_vars={"alpha-live": self._entry(self.KEY_ALPHA)},
        )
        authorisations = host_authorisations(tree)
        self.assertIn(
            PLATFORM_APPLICATION,
            authorisations.get("alpha-live", {}),
            "the fixture's satisfied host does not authorise the platform deploy key, so "
            "this does not express one authorisation being offered for two opt-ins",
        )
        self.assertNotIn("alpha-live", " ".join(self._offences_over(tree)))
        self.assertTrue(
            self._offences_over(tree),
            "one host's authorisation was read as answering both stacks' opt-ins, which "
            "is the tree this change exists to prevent",
        )

    def test_an_entry_in_the_shared_environments_file_answers_neither_stack(self) -> None:
        """SPECIFIED -- ADDED scenario "Two stacks share an environment": "neither
        SHALL be enumerated in the environment's `group_vars` file, where one
        entry would authorise both hosts"."""
        tree = self._host_tree(
            self._stacks(),
            group_vars={self.GROUP: self._entry(self.KEY_ALPHA)},
        )
        offences = self._offences_over(tree)
        self.assertEqual(
            2,
            len(offences),
            f"an entry in the environment's shared file answered a stack's opt-in: "
            f"{offences}",
        )
        self.assertEqual(
            [
                f"{GROUP_VARS_SEGMENT}/{self.GROUP}.yml supplies `{DEPLOY_APPS_FIELD}`, so "
                f"every host in the `{self.GROUP}` group authorises "
                f"['{PLATFORM_APPLICATION}'] -- one entry authorising a second tenant's "
                "host is the widening this placement exists to prevent"
            ],
            group_vars_authorisation_offences(group_vars_documents(tree)),
        )

    def test_each_host_authorises_a_keypair_of_its_own(self) -> None:
        """SPECIFIED -- ADDED scenario "Two stacks share an environment": "each
        naming a keypair of its own", and "Where one application deploys to two
        hosts it SHALL do so with two keypairs"."""
        shared = self._host_tree(
            self._stacks(),
            host_vars={
                "alpha-live": self._entry(self.KEY_ALPHA),
                "beta-live": self._entry(self.KEY_ALPHA),
            },
        )
        offences = duplicate_public_half_offences(host_authorisations(shared))
        self.assertEqual(
            1,
            len(offences),
            f"two hosts enumerating one public half was not reported: {offences}",
        )
        self.assertIn("alpha-live/platform", offences[0])
        self.assertIn("beta-live/platform", offences[0])

        separate = self._host_tree(
            self._stacks(),
            host_vars={
                "alpha-live": self._entry(self.KEY_ALPHA),
                "beta-live": self._entry(self.KEY_BETA),
            },
        )
        self.assertEqual([], duplicate_public_half_offences(host_authorisations(separate)))


class TestTheConsumingRolesSendAnOperatorToTheHostsOwnFile(unittest.TestCase):
    """DERIVED -- no scenario states a message, and the ADDED requirement says
    outright that nothing in it obliges a role to change.

    What this traces to is that change's tasks.md 2.4: both consuming roles
    assert `deploy_apps` is defined and name the file to set it in, and that
    sentence is what an operator reads AS the converge refuses. A stale one sends
    them to edit a file that no longer supplies the variable, which is a failure
    this suite can see statically and nothing else in the repository can.

    Asserted on the DIRECTORY NAME the message carries rather than on a whole
    path, because the wording is the implementing author's. That is strictly
    stronger in the prohibiting direction -- a message shortened to
    `group_vars/<environment>.yml` still names the retired file and is still
    reported -- and deliberately looser in the requiring direction, where
    anything naming `host_vars` satisfies it.

    Two Molecule scenarios assert the retired literal of OTHER inputs -- the
    heartbeat ping key and `hardening_ssh_allowed_cidrs`, both of which this
    change leaves in an environment's file -- and neither is read here, which is
    why this reads each role's `tasks/main.yml` and nothing under `molecule/`.
    """

    GROUP_VARS_DIRNAME = "group_vars"

    def _messages(self, relative: str) -> list:
        path = ROOT / relative
        self.assertTrue(path.is_file(), f"{relative} does not exist")
        messages = deploy_apps_refusal_messages(path)
        self.assertEqual(
            1,
            len(messages),
            f"{relative} carries {len(messages)} assertion(s) over `{DEPLOY_APPS_FIELD}` "
            "rather than exactly one, so which message an operator reads as the converge "
            f"refuses is not determined: {messages}",
        )
        self.assertTrue(
            messages[0].strip(),
            f"{relative}'s `{DEPLOY_APPS_FIELD}` assertion carries no `fail_msg`, so the "
            "converge refuses without saying what to set or where",
        )
        return messages

    def test_neither_role_sends_an_operator_to_the_environments_file(self) -> None:
        """DERIVED -- see the class docstring."""
        for relative in CONSUMING_ROLE_TASKS:
            with self.subTest(role=relative):
                message = self._messages(relative)[0]
                self.assertNotIn(
                    self.GROUP_VARS_DIRNAME,
                    message,
                    f"{relative}'s `{DEPLOY_APPS_FIELD}` refusal names "
                    f"`{self.GROUP_VARS_DIRNAME}`: {message!r}. An operator reading that as "
                    "the converge refuses edits a file that no longer supplies the "
                    "variable",
                )

    def test_each_role_names_the_hosts_own_file(self) -> None:
        """DERIVED -- the converse. A message naming no file at all satisfies the
        prohibition above and leaves the operator with nowhere to go."""
        for relative in CONSUMING_ROLE_TASKS:
            with self.subTest(role=relative):
                message = self._messages(relative)[0]
                self.assertIn(
                    HOST_VARS_DIRNAME,
                    message,
                    f"{relative}'s `{DEPLOY_APPS_FIELD}` refusal names no host vars file: "
                    f"{message!r}. It does not say where the variable is now set",
                )


# --------------------------------------------------------------------------
# Every read above is a static read of a committed file
# --------------------------------------------------------------------------


class TestTheseReadsDiscriminate(HostVarsFixtureMixin, unittest.TestCase):
    """Every assertion above is a static read of a committed file, so a
    predicate that reported no offence whatever it was given would satisfy all of
    them -- and would do so most convincingly on the day the move was finished.

    This class runs each predicate over material this file supplies, carrying the
    defect that predicate names, and over material carrying none. Both directions
    are needed: a predicate refusing everything satisfies every refusal while
    making a legitimate tree impossible.
    """

    KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAone one@host"
    OTHER = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAtwo two@host"

    def _entry(self, key: str) -> list:
        return [{APPLICATION_NAME_FIELD: PLATFORM_APPLICATION, APPLICATION_KEY_FIELD: key}]

    # -- the loader ------------------------------------------------------

    def test_a_vaulted_file_is_read_rather_than_refused(self) -> None:
        tree = self._scratch()
        path = tree / "production.yml"
        path.write_text(
            "image_prune_heartbeat_ping_key: !vault |\n"
            "  $ANSIBLE_VAULT;1.2;AES256;production\n  3132\n"
            f"{DEPLOY_APPS_FIELD}:\n  - {APPLICATION_NAME_FIELD}: {PLATFORM_APPLICATION}\n"
            f"    {APPLICATION_KEY_FIELD}: ssh-ed25519 AAAA\n",
            encoding="utf-8",
        )
        self.assertEqual({PLATFORM_APPLICATION: "ssh-ed25519 AAAA"}, _authorisations_of(
            inventory_variables(path)
        ))

    def test_an_unknown_tag_refuses_rather_than_yielding_an_empty_document(self) -> None:
        tree = self._scratch()
        path = tree / "main-production.yml"
        path.write_text(
            f"{DEPLOY_APPS_FIELD}: !something\n  - {APPLICATION_NAME_FIELD}: "
            f"{PLATFORM_APPLICATION}\n",
            encoding="utf-8",
        )
        with self.assertRaises(UnreadableVarsFile):
            inventory_variables(path)

    def test_a_document_that_is_not_a_mapping_refuses(self) -> None:
        tree = self._scratch()
        path = tree / "main-staging.yml"
        path.write_text("- one\n- two\n", encoding="utf-8")
        with self.assertRaises(UnreadableVarsFile):
            inventory_variables(path)

    def test_an_entry_naming_no_key_is_read_as_an_authorisation_without_one(self) -> None:
        """An entry this reader saw and could not identify a keypair for is not
        the application being absent -- the cross-check must still report the
        opt-in as answered, and the duplicate check must not pair two of them."""
        self.assertEqual(
            {PLATFORM_APPLICATION: ""},
            _authorisations_of({DEPLOY_APPS_FIELD: [{APPLICATION_NAME_FIELD: "platform"}]}),
        )
        self.assertEqual(
            [],
            duplicate_public_half_offences(
                {"one": {PLATFORM_APPLICATION: ""}, "two": {PLATFORM_APPLICATION: ""}}
            ),
        )

    # -- the host vars file exists ---------------------------------------

    def test_a_stack_whose_declared_server_has_no_vars_file_is_reported(self) -> None:
        offences = missing_host_vars_offences(["alpha-live"], {"alpha-live": "alpha-live"}, set())
        self.assertEqual(1, len(offences), offences)
        self.assertIn(f"{HOST_VARS_SEGMENT}/alpha-live.yml", offences[0])

    def test_a_stack_whose_server_has_a_vars_file_is_not_reported(self) -> None:
        self.assertEqual(
            [],
            missing_host_vars_offences(
                ["alpha-live"], {"alpha-live": "alpha-live"}, {"alpha-live"}
            ),
        )

    def test_a_stack_naming_no_server_is_reported_rather_than_passed_over(self) -> None:
        offences = missing_host_vars_offences(["alpha-live"], {"alpha-live": None}, {"alpha-live"})
        self.assertEqual(1, len(offences), offences)
        self.assertIn("names no server", offences[0])

    def test_a_renamed_server_leaves_a_file_nothing_resolves_to(self) -> None:
        """Both halves of the rename: the stack resolving to a file that does not
        exist, and the file no stack resolves to."""
        servers = {"alpha-live": "alpha-live-2"}
        present = {"alpha-live"}
        self.assertEqual(
            1, len(missing_host_vars_offences(["alpha-live"], servers, present))
        )
        orphans = orphaned_host_vars_offences(servers, present)
        self.assertEqual(1, len(orphans), orphans)
        self.assertIn(f"{HOST_VARS_SEGMENT}/alpha-live.yml", orphans[0])
        self.assertEqual([], orphaned_host_vars_offences(servers, {"alpha-live-2"}))

    def test_the_readers_resolve_a_server_name_out_of_a_synthetic_tree(self) -> None:
        """The readers themselves, not only the predicates they feed. A reader
        returning `{}` for every tree satisfies every predicate above."""
        tree = self._host_tree(
            {"alpha-live": (True, "live", "alpha-live")},
            host_vars={"alpha-live": self._entry(self.KEY)},
        )
        self.assertEqual({"alpha-live": "alpha-live"}, declared_servers(tree))
        self.assertEqual(["alpha-live"], declaring_stacks(tree))
        self.assertEqual(
            {"alpha-live": {PLATFORM_APPLICATION: self.KEY}}, host_authorisations(tree)
        )
        self.assertEqual([], missing_host_vars_offences(
            declaring_stacks(tree), declared_servers(tree), set(host_vars_documents(tree))
        ))

    # -- where the authorisations live -----------------------------------

    def test_an_environments_file_supplying_the_authorisations_is_reported(self) -> None:
        offences = group_vars_authorisation_offences(
            {"live": {DEPLOY_APPS_FIELD: self._entry(self.KEY)}}
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn(f"{GROUP_VARS_SEGMENT}/live.yml", offences[0])

    def test_an_environments_file_supplying_other_variables_is_not_reported(self) -> None:
        self.assertEqual(
            [], group_vars_authorisation_offences({"live": {"ansible_user": "ops"}})
        )

    def test_an_empty_authorisation_list_in_an_environments_file_is_still_reported(self) -> None:
        """A `deploy_apps:` key with nothing under it is still the variable being
        supplied from the environment's file, and is the shape a half-finished
        move leaves behind."""
        offences = group_vars_authorisation_offences({"live": {DEPLOY_APPS_FIELD: []}})
        self.assertEqual(1, len(offences), offences)

    def test_a_variable_supplied_from_both_files_is_reported(self) -> None:
        offences = repeated_variable_offences(
            {"live": {"ansible_user": "ops"}}, {"alpha-live": {"ansible_user": "ops"}}
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn("ansible_user", offences[0])

    def test_two_files_supplying_different_variables_are_not_reported(self) -> None:
        self.assertEqual(
            [],
            repeated_variable_offences(
                {"live": {"ansible_user": "ops"}},
                {"alpha-live": {DEPLOY_APPS_FIELD: self._entry(self.KEY)}},
            ),
        )

    # -- one leaked private half reaches one host ------------------------

    def test_two_hosts_authorising_one_public_half_are_reported(self) -> None:
        offences = duplicate_public_half_offences(
            {"alpha-live": {PLATFORM_APPLICATION: self.KEY}, "beta-live": {"shop": self.KEY}}
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn("alpha-live/platform", offences[0])
        self.assertIn("beta-live/shop", offences[0])

    def test_two_hosts_authorising_two_public_halves_are_not_reported(self) -> None:
        self.assertEqual(
            [],
            duplicate_public_half_offences(
                {
                    "alpha-live": {PLATFORM_APPLICATION: self.KEY},
                    "beta-live": {PLATFORM_APPLICATION: self.OTHER},
                }
            ),
        )

    def test_one_host_authorising_two_applications_is_not_reported(self) -> None:
        """Two applications on ONE host are two entries and not a shared key, as
        production's own pair already is."""
        self.assertEqual(
            [],
            duplicate_public_half_offences(
                {"alpha-live": {PLATFORM_APPLICATION: self.KEY, "shop": self.OTHER}}
            ),
        )

    def test_no_authorisation_at_all_is_reported_rather_than_passed_over(self) -> None:
        self.assertEqual(1, len(duplicate_public_half_offences({})))

    # -- the opt-in is answered per host ---------------------------------

    def test_an_opt_in_without_an_authorisation_is_reported(self) -> None:
        offences = opt_in_authorisation_offences(
            {"alpha-live": True}, {"alpha-live": "alpha-live"}, {"alpha-live": {"shop": self.KEY}}
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn(f"{HOST_VARS_SEGMENT}/alpha-live.yml", offences[0])
        self.assertIn(f"{STACK_ROOT_SEGMENT}/alpha-live/{DECLARATION_NAME}", offences[0])

    def test_an_opt_in_whose_host_has_no_vars_file_is_reported(self) -> None:
        offences = opt_in_authorisation_offences(
            {"alpha-live": True}, {"alpha-live": "alpha-live"}, {}
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn("does not exist", offences[0])

    def test_an_opt_in_declaring_no_server_is_reported(self) -> None:
        offences = opt_in_authorisation_offences({"alpha-live": True}, {"alpha-live": None}, {})
        self.assertEqual(1, len(offences), offences)
        self.assertIn("names no server", offences[0])

    def test_an_authorised_host_whose_stack_opts_in_is_not_reported(self) -> None:
        self.assertEqual(
            [],
            opt_in_authorisation_offences(
                {"alpha-live": True},
                {"alpha-live": "alpha-live"},
                {"alpha-live": {PLATFORM_APPLICATION: self.KEY}},
            ),
        )

    def test_the_implication_holds_in_one_direction_only(self) -> None:
        """A host prepared before its deploy path exists is the deliberate
        interval, and is accepted rather than reported."""
        self.assertEqual(
            [],
            opt_in_authorisation_offences(
                {"alpha-live": None},
                {"alpha-live": "alpha-live"},
                {"alpha-live": {PLATFORM_APPLICATION: self.KEY}},
            ),
        )

    def test_another_hosts_authorisation_does_not_answer_this_stacks_opt_in(self) -> None:
        """The assertion the retired resolution could not make: two stacks, one
        group, one authorised host."""
        offences = opt_in_authorisation_offences(
            {"alpha-live": True, "beta-live": True},
            {"alpha-live": "alpha-live", "beta-live": "beta-live"},
            {"alpha-live": {PLATFORM_APPLICATION: self.KEY}},
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn("beta-live", offences[0])
        self.assertNotIn("alpha-live", offences[0])

    # -- the disclosure the requirement makes about itself ---------------

    def test_the_unmet_placements_are_read_out_of_the_files_rather_than_assumed(self) -> None:
        """The disclosure test above reads two directions out of two mappings; a
        reader returning `{}` for host files would satisfy its second half
        silently."""
        tree = self._host_tree(
            {"alpha-live": (True, "live", "alpha-live")},
            host_vars={"alpha-live": {UNMET_PLACEMENTS[0]: ["10.0.0.0/8"]}},
            group_vars={"live": {UNMET_PLACEMENTS[1]: ["0.0.0.0/0"]}},
        )
        self.assertEqual(
            {UNMET_PLACEMENTS[0]}, set(host_vars_documents(tree)["alpha-live"])
        )
        self.assertEqual({UNMET_PLACEMENTS[1]}, set(group_vars_documents(tree)["live"]))

    # -- the role message ------------------------------------------------

    STALE_TASKS = (
        "- name: Fail loudly if the applications allowed to deploy were not supplied\n"
        "  ansible.builtin.assert:\n"
        "    that:\n"
        f"      - {DEPLOY_APPS_FIELD} is defined\n"
        "    fail_msg: >-\n"
        f"      {DEPLOY_APPS_FIELD} was not supplied. Set it in\n"
        f"      {GROUP_VARS_SEGMENT}/<environment>.yml, the file for the environment\n"
        "      this run targets.\n"
    )
    OTHER_INPUT_TASK = (
        "- name: Assert the heartbeat ping key was supplied\n"
        "  ansible.builtin.assert:\n"
        "    that:\n"
        "      - image_prune_heartbeat_ping_key is defined\n"
        "    fail_msg: >-\n"
        "      image_prune_heartbeat_ping_key was not supplied. Set it in\n"
        f"      {GROUP_VARS_SEGMENT}/<environment>.yml.\n"
    )

    def _tasks_file(self, text: str) -> Path:
        path = self._scratch() / "main.yml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_refusal_naming_the_environments_file_is_read_out_of_a_folded_scalar(self) -> None:
        """The read is of the PARSED message rather than of the file's lines, and
        this is the case that decides it: the committed roles fold the message, so
        `group_vars` and `deploy_apps` never share a line. A line-wise predicate
        passes here having read nothing."""
        messages = deploy_apps_refusal_messages(self._tasks_file(self.STALE_TASKS))
        self.assertEqual(1, len(messages), messages)
        self.assertIn(GROUP_VARS_SEGMENT, messages[0])
        self.assertNotIn(HOST_VARS_SEGMENT, messages[0])

    def test_a_refusal_naming_the_hosts_own_file_carries_neither_defect(self) -> None:
        corrected = self.STALE_TASKS.replace(GROUP_VARS_SEGMENT, HOST_VARS_SEGMENT)
        messages = deploy_apps_refusal_messages(self._tasks_file(corrected))
        self.assertEqual(1, len(messages), messages)
        self.assertNotIn(GROUP_VARS_SEGMENT, messages[0])
        self.assertIn(HOST_VARS_SEGMENT, messages[0])

    def test_another_inputs_refusal_is_not_read_as_this_one(self) -> None:
        """Both roles carry a second refusal naming an environment's file
        legitimately, over a value this change leaves there. A predicate reading
        the file rather than the assertion reports it as this defect."""
        self.assertEqual([], deploy_apps_refusal_messages(self._tasks_file(self.OTHER_INPUT_TASK)))
        self.assertEqual(
            1,
            len(
                deploy_apps_refusal_messages(
                    self._tasks_file(self.OTHER_INPUT_TASK + self.STALE_TASKS)
                )
            ),
            "a file carrying both refusals yields only the one over `deploy_apps`",
        )

    def test_a_file_that_is_not_a_task_list_refuses(self) -> None:
        with self.assertRaises(UnreadableVarsFile):
            deploy_apps_refusal_messages(self._tasks_file("not: a list\n"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
