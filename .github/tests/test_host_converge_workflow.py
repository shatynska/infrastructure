"""Static-assertion tests for a host converge that reaches a host through a
gated workflow rather than from a workstation.

Derived from the delta specifications of the OpenSpec change
`apply-host-configuration-through-a-gated-workflow`, before any implementation
of that change existed -- from those deltas at commit `d38fb6e`, the commit
holding the approved plan. The path those deltas sit at is not written here: a
change's artifacts move when it is archived, and this repository's citation
convention is to name the change and the artifact in prose instead.

The deltas span two capabilities, `iac-cicd-pipeline` and
`iac-host-configuration`; each class below names the requirement and the
scenario it traces to. Every assertion is annotated SPECIFIED (it traces to
SHALL text or to a scenario in a delta spec) or DERIVED (it traces to that
change's `design.md` or `tasks.md` rather than to a scenario). See that change's
`test-plan.md` for the scenario-to-test mapping, the baseline, the scenarios
deliberately left uncovered, the obsolete-test candidates, and the project
questions this file took an assumption on.

Why this is a fifth file in the suite rather than a section of an existing one
-----------------------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. Two places in
`test_environment_agnostic_pipeline.py` rest on a premise this change retires --
its pinned expectation of production's read-only secret name, and the
digest-emitter exemption justified by that same name -- and re-pointing them is
the implementing author's task (that change's tasks.md 2.2), recorded in
`test-plan.md`'s obsolete list rather than performed here. Nothing in this file
edits, deletes or disables an existing test.

Where this file needs a helper a module beside it already has, it imports it
rather than restating it, which is the idiom the four modules already in this
directory use. `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in
`test_ci_configuration.py` reads every module in this directory, so this file is
held to the no-network, no-credential, no-container, no-Terraform constraint by
that class, and is written to satisfy it: standard library, `yaml`, the helpers
of the modules beside it, and `bash` as the only spawned command.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_host_converge_workflow.TestNoDeclarationNamesTheWriteTokensOwnName \\
        .test_no_environment_declares_the_write_tokens_own_name

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling imports below resolve.

What no assertion here establishes
----------------------------------
Nothing in this file reads repository settings, reaches the Hetzner Cloud API or
a tailnet, holds a credential, or runs Ansible. Whether a GitHub Environment
exists and which secrets it holds, whether a converge authenticates, which
address a run actually dials, and whether a host is reachable at all are
run-time or settings facts rather than repository content. In particular the
`iac-host-configuration` delta's four *The Address a Converge Connects To Is
Selected Per Run* scenarios are established by the manual verification that
change's tasks.md 1.3 records, NOT here: the assertions below read the
connection-address option as it is COMMITTED, which is a different and weaker
proposition than what a run connects to. A green run here establishes that the
committed files are SHAPED so those run-time outcomes are the ones the
requirements describe, never that they occurred.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import unittest
from pathlib import Path

import yaml

from test_ci_configuration import (
    ROOT,
    WORKFLOWS,
    gh_glob_matches,
    jobs,
    load_yaml,
    read_text,
    require_external_tools,
    walked_files,
    step_label,
    steps,
    triggers,
    uncommented,
)
from test_environment_agnostic_pipeline import (
    ACTIONS_EXPRESSION,
    DeclarationTreeFixtureMixin,
    declared_environment,
    environment_declarations,
    environment_directories,
    invocation_lines,
    invoking_steps,
    run_snippet,
)
from test_host_configuration_names_its_environment import (
    BARE_TEMPLATE,
    ENV_LOOKUP,
    INVENTORY_DIR,
    inventory_sources,
)

# --------------------------------------------------------------------------
# Identifiers this file names, and why each is a constraint rather than a
# property the specification states.
# --------------------------------------------------------------------------

# The workflow the ADDED requirement obliges. The NAME is DERIVED -- the delta
# says "a workflow triggered by a merge to the default branch" and names no
# file; `host-converge.yml` comes from the change's proposal.md and tasks.md
# 3.1. It is named here so the implementing author has a red-to-green target,
# and because a locator that swept every file under `.github/workflows/` would
# read the platform deploy and the Terraform apply as candidates.
HOST_CONVERGE = WORKFLOWS / "host-converge.yml"

ANSIBLE_DIR = ROOT / "ansible"
GROUP_VARS_DIR = INVENTORY_DIR / "group_vars"

# The manifest the converge job installs from, and the one the role-verification
# suite installs from. The converge manifest's name is DERIVED (tasks.md 3.4-0);
# the verification manifest already exists and is read by `ansible-verify.yml`.
CONVERGE_MANIFEST = ANSIBLE_DIR / "requirements.txt"
VERIFICATION_MANIFEST = ANSIBLE_DIR / "requirements-test.txt"

# The distribution whose version the delta obliges the two manifests to agree
# on: "The version of Ansible a converge runs SHALL be the version the
# role-verification suite runs".
ANSIBLE_DISTRIBUTION = "ansible-core"

# The name *Credential Scoping by Privilege* obliges EVERY GitHub Environment to
# define as that environment's Read & Write token, which is what makes a
# declaration naming it as a READ-ONLY secret resolve to the write token inside
# any job declaring an `environment:`. The MODIFIED requirement states the name
# outright -- "`HCLOUD_TOKEN` is such a name for every environment" -- so this
# is SPECIFIED rather than an identifier this file chose.
SHADOWED_WRITE_TOKEN = "HCLOUD_TOKEN"

# The play a converge runs, relative to `ansible/`. SPECIFIED only as "host
# configuration"; the path is DERIVED from the committed playbook and tasks.md
# 3.6.
HOST_BASELINE_PLAY = "playbooks/host-baseline.yml"

# WHERE THE SELECTION LIVES, AND WHY IT IS NOT `connect_with:`.
#
# This file first pinned the plugin's own `connect_with:` option, on the
# reasonable reading that an option naming which address to resolve to is the
# option that selects one. Task 1.3's live verification -- the task the change
# discloses as owed precisely because no static read can stand in for it --
# established that it cannot carry a per-run value AT ALL: `connect_with` is
# validated against its `choices:` BEFORE the value is templated, so a Jinja
# expression there is refused as an invalid choice and the source does not
# parse, for CI and for a workstation alike.
#
# The selection is therefore a `compose:` entry for `ansible_host`, which is a
# Jinja context by design. What this file asserts is unchanged in substance --
# a selection exists, it resolves to an environment variable, its default is
# the public address, and both sources read one variable -- and two assertions
# are ADDED below, each guarding a way the new mechanism can be got wrong that
# the old one could not.
#
# `public_ipv4` remains the plugin's own vocabulary: it is the value
# `connect_with` defaults to, and therefore the value `ansible_host` already
# holds when `compose` runs.
CONNECT_WITH_OPTION = "connect_with"
COMPOSE_OPTION = "compose"
COMPOSED_ADDRESS = "ansible_host"
STRICT_OPTION = "strict"
PUBLIC_ADDRESS_CHOICE = "public_ipv4"

# The default branch a merge reaches, and a path under the host-configuration
# directory used to exercise the workflow's own path filter. DERIVED.
DEFAULT_BRANCH = "main"
A_HOST_CONFIGURATION_PATH = "ansible/roles/hardening/tasks/main.yml"

PIP_INSTALL = re.compile(r"\bpip3?\s+install\b")
GALAXY_COLLECTION_INSTALL = re.compile(r"\bansible-galaxy\s+collection\s+install\b")
GALAXY_ROLE_INSTALL = re.compile(r"\bansible-galaxy\s+role\s+install\b")
ANSIBLE_PLAYBOOK = re.compile(r"\bansible-playbook\b")
ANSIBLE_INVENTORY = re.compile(r"\bansible-inventory\b")
ANY_ANSIBLE_COMMAND = re.compile(r"\bansible(?:-[a-z]+)?\b(?!\.)")
STEP_SUMMARY = re.compile(r"GITHUB_STEP_SUMMARY")
GIT_DIFF = re.compile(r"\bgit\s+diff\b")
VAULT_ARGUMENT = re.compile(r"--vault-(?:id|password-file)\b")
REQUIREMENT_ARGUMENT = re.compile(r"-r\s+(\S+)")
PIN = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s#;]+)")
DEFAULT_FILTER = re.compile(r"""default\(\s*['"]([A-Za-z0-9_]+)['"]""")
DISPATCH_INPUT = re.compile(r"(?:inputs|event\.inputs)\.environment\b")
# A Jinja expression sitting in a plain inventory-option value.
ACTIONS_TEMPLATE = re.compile(r"\{\{")

# The dispatch input's own name. DERIVED -- tasks.md 3.1 gives the workflow "a
# free-text `environment` input"; no scenario names it. Used only to locate the
# input, never asserted as a spelling on its own.
DISPATCH_INPUT_NAME = "environment"


# --------------------------------------------------------------------------
# Reading the two manifests
# --------------------------------------------------------------------------


def pins(text: str) -> dict:
    """Every exact pin a pip requirements file states, as name -> version.

    Only the `==` form is read. A floating range is not a pin and this
    repository forbids one anyway (`AGENTS.md`, "pinned to an exact version,
    never a floating range"), so a file stating one resolves to no version here
    and fails the agreement assertion rather than passing it loosely.
    """
    found: dict = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        match = PIN.match(line)
        if match:
            found[match.group(1).lower()] = match.group(2).strip()
    return found


def pinned_ansible(path: Path) -> str | None:
    if not path.is_file():
        return None
    return pins(path.read_text(encoding="utf-8")).get(ANSIBLE_DISTRIBUTION)


# --------------------------------------------------------------------------
# Reading the connection-address selection out of an inventory source
# --------------------------------------------------------------------------


class ConnectionSelection:
    """One inventory source's per-run connection-address selection.

    Read from the `compose:` entry for `ansible_host` -- see the note above for
    why not from `connect_with:`. `strict` and any `connect_with` the source
    still declares are carried too, because each is a way this mechanism fails
    that the old one could not.
    """

    def __init__(self, source) -> None:
        self.source = source
        composed = (source.document.get(COMPOSE_OPTION) or {}).get(COMPOSED_ADDRESS)
        self.declared = composed is not None
        self.raw = "" if composed is None else str(composed)
        match = ENV_LOOKUP.search(self.raw) or BARE_TEMPLATE.search(self.raw)
        self.variable: str | None = match.group(1) if match else None
        fallback = DEFAULT_FILTER.search(self.raw)
        self.default: str | None = fallback.group(1) if fallback else None
        self.strict = source.document.get(STRICT_OPTION) is True
        self.templated_connect_with = ACTIONS_TEMPLATE.search(
            str(source.document.get(CONNECT_WITH_OPTION) or "")
        ) is not None


def connection_selections() -> list[ConnectionSelection]:
    return [ConnectionSelection(source) for source in inventory_sources()]


# --------------------------------------------------------------------------
# Comparing a declaration with the inventory source of the same environment
# --------------------------------------------------------------------------


def credential_disagreements(pairs) -> list[str]:
    """Every environment whose inventory source reads a variable name its own
    pipeline declaration does not state, as a message naming both.

    `pairs` is an iterable of (environment, declared name, name the source
    reads, source path as text), so the comparison is exercisable against a
    fixture pair as well as against the committed tree -- at two environments
    the committed tree cannot demonstrate that the comparison would catch a
    case-only difference, and a comparison that could not is exactly what
    tasks.md 2.4 names as the shape a lenient reading would let through.

    The comparison is LITERAL. GitHub resolves `secrets[...]` case-insensitively
    while Ansible's `lookup('env', ...)` does not, so a declaration differing
    from its source only in case resolves in the workflow and fails in the play.
    """
    offences = []
    for environment, declared, reads, where in pairs:
        if declared is None:
            offences.append(
                f"{environment}: the pipeline declaration states no read-only secret "
                "name, so the workflow has no name to supply the credential under"
            )
            continue
        if reads is None:
            offences.append(
                f"{environment}: {where} names no environment variable this read can "
                "resolve, so which credential the source takes is not readable from "
                "the committed file"
            )
            continue
        if declared != reads:
            offences.append(
                f"{environment}: the declaration states {declared!r} as the read-only "
                f"secret and {where} reads {reads!r}. The converge job holds the "
                "credential under the declared name and supplies it under the name "
                "the source reads; where the two differ the workflow would have to "
                "carry the mapping, which is the environment-naming in workflow text "
                "the pipeline's own requirements forbid"
            )
    return offences


def committed_credential_pairs() -> list[tuple]:
    declarations = environment_declarations()
    sources = {source.environment: source for source in inventory_sources()}
    pairs = []
    for name in sorted(set(declarations) & set(sources)):
        pairs.append(
            (
                name,
                declarations[name].read_only_secret,
                sources[name].credential,
                sources[name].relative,
            )
        )
    return pairs


# --------------------------------------------------------------------------
# Reading the workflow
# --------------------------------------------------------------------------


def effective_working_directory(workflow: dict, job: dict, step: dict) -> str:
    """Where a `run:` step actually runs, honouring both `defaults:` levels.

    tasks.md 3.4-2 names the job level specifically, and design.md Decision 12
    says why it is not cosmetic: Ansible loads `./ansible.cfg` from the current
    directory, so from the repository root it loads none and
    `any_unparsed_is_failed` reverts to its default -- the setting the
    "an inventory source whose credential is absent or is rejected SHALL fail
    the run" clause is false without.
    """
    for holder in (step, job, workflow):
        if holder is step:
            value = step.get("working-directory")
        else:
            value = ((holder.get("defaults") or {}).get("run") or {}).get(
                "working-directory"
            )
        if value:
            return str(value)
    return "."


def resolved_from(working_directory: str, reference: str) -> str:
    """A path a step names, as it resolves from the repository root."""
    return posixpath.normpath(posixpath.join(working_directory, reference))


def job_surfaces(job: dict):
    """(label, text) for every surface of a job that can carry a secret read."""
    yield "<job-level env:>", yaml.safe_dump(job.get("env") or {}, sort_keys=True)
    yield "<job-level with:>", yaml.safe_dump(job.get("with") or {}, sort_keys=True)
    for index, step in enumerate(job.get("steps") or []):
        body = {
            "env": step.get("env"),
            "with": step.get("with"),
            "run": step.get("run"),
            "if": step.get("if"),
        }
        yield step_label("", index, step), yaml.safe_dump(body, sort_keys=True)


class WorkflowLocatorMixin:
    """Finds the workflow's jobs and steps BY SHAPE rather than by name.

    Every job key, step name and step id in a workflow that does not exist yet
    is the implementing author's to choose (tasks.md 3.1-3.6 describe the jobs
    but fix no key), so a locator keyed on a name would fail a legitimate choice
    and would be repaired by editing this file -- the one repair this suite must
    not need. What each locator keys on instead is the property the requirement
    itself states about that job.
    """

    def workflow(self) -> dict:
        return load_yaml(HOST_CONVERGE)

    def _one(self, candidates, what: str, hint: str):
        self.assertEqual(
            1,
            len(candidates),
            f"expected exactly one {what} in {HOST_CONVERGE.name}, found "
            f"{len(candidates)}: {sorted(label for label, _ in candidates)}. {hint}",
        )
        return candidates[0][1]

    def converge_job(self):
        """The job that runs the play: the only one invoking `ansible-playbook`."""
        workflow = self.workflow()
        candidates = [
            (name, (name, job))
            for name, job in jobs(workflow).items()
            if any(True for _ in invoking_steps(job, ANSIBLE_PLAYBOOK))
        ]
        return self._one(
            candidates,
            "job invoking `ansible-playbook`",
            "The converge is one job per environment and nothing else runs the play; "
            "a second such job would mean the credentials the gate withholds are held "
            "in more than one place.",
        )

    def publishing_job(self):
        """The pre-approval job: the one writing to the run summary."""
        workflow = self.workflow()
        candidates = []
        for name, job in jobs(workflow).items():
            # Matched as TEXT rather than through `invocation_lines`, and the
            # difference is not pedantic: the summary is written by REDIRECTING
            # into it -- `} >>"$GITHUB_STEP_SUMMARY"`, which is the shape
            # `platform-deploy.yml`'s own diff job uses -- and a reader that
            # skips a match sitting inside an unclosed quote skips that
            # redirect, finding no publishing job in a workflow that has one.
            if any(
                STEP_SUMMARY.search(uncommented(str(step.get("run") or "")))
                for step in (job.get("steps") or [])
            ):
                candidates.append((name, (name, job)))
        return self._one(
            candidates,
            "job writing to `$GITHUB_STEP_SUMMARY`",
            "What the pre-approval job publishes is the committed diff, and it is the "
            "only job in this workflow that publishes anything for a human to read.",
        )

    def discovery_step(self):
        """The discovery body, located by shape: the one `run:` step that
        enumerates the inventory directory, writes to `$GITHUB_OUTPUT`, and
        carries no `${{ }}`.

        That it carries none is tasks.md 3.2's own obligation ("Take nothing
        from the event inside the step body, so `.github/tests` can execute it
        against a scratch tree") and the reason the class that runs it can exist
        at all: an expression is interpolated before the step runs, so a body
        carrying one cannot be executed anywhere but on a runner.
        """
        workflow = self.workflow()
        candidates = []
        for job_name, index, step in steps(workflow):
            body = str(step.get("run") or "")
            if not body:
                continue
            if "inventory" not in body or "GITHUB_OUTPUT" not in body:
                continue
            if ACTIONS_EXPRESSION.search(body):
                continue
            job = jobs(workflow)[job_name]
            candidates.append(
                (step_label(job_name, index, step), (job_name, job, step))
            )
        return self._one(
            candidates,
            "`run:` step that enumerates the inventory sources, emits to "
            "`$GITHUB_OUTPUT` and carries no `${{ }}`",
            "Emitting the matrix is what discovery is FOR, so writing to "
            "`$GITHUB_OUTPUT` is part of the locator; and discovery written as an "
            "Actions expression, or carrying one in its body, cannot be executed "
            "anywhere but on a runner, so its refusals would be asserted nowhere.",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Each Environment Declares Its Own Pipeline Configuration
# (MODIFIED) -- the read-only secret's name
# --------------------------------------------------------------------------


class TestNoDeclarationNamesTheWriteTokensOwnName(unittest.TestCase):
    """MODIFIED requirement: Each Environment Declares Its Own Pipeline
    Configuration -- scenario "A declaration naming the write token's own name
    is refused".

    Half of this proposition is repository settings and is unreadable here:
    whether a GitHub Environment defines a secret is not committed content. But
    *Credential Scoping by Privilege* already obliges EVERY Environment to
    define `HCLOUD_TOKEN` as its Read & Write token, so "no environment declares
    `read_only_secret: HCLOUD_TOKEN`" follows from a rule this repository states
    and is a static read of a committed file -- which is what makes the scenario
    enforced rather than merely written down (design.md Decision 6).
    """

    def setUp(self) -> None:
        self.declarations = environment_declarations()
        self.assertTrue(
            self.declarations,
            "no environment declaration was discovered under terraform/environments/, "
            "so every assertion in this class would pass having read nothing",
        )

    def test_every_declaration_states_a_read_only_secret_to_read(self) -> None:
        """DERIVED -- the converse the assertion below needs. A declaration
        resolving to no secret name at all would satisfy the sweep while saying
        nothing, and the sweep would then be green over a tree it could not
        read."""
        silent = sorted(
            name
            for name, declaration in self.declarations.items()
            if not declaration.read_only_secret
        )
        self.assertEqual(
            [],
            silent,
            "these environments declare no read-only secret name this read can "
            f"resolve, so the sweep below would pass over them having compared "
            f"nothing: {silent}",
        )

    def test_no_environment_declares_the_write_tokens_own_name(self) -> None:
        """SPECIFIED -- "No environment's declared read-only secret name SHALL
        be a name its own GitHub Environment also defines, and `HCLOUD_TOKEN` is
        such a name for every environment", and the scenario's "THEN the
        required status check SHALL fail, naming that environment".

        The message names the offending declaration and its file, as the sibling
        refusals in `test_environment_agnostic_pipeline.py` do: an operator
        reading a red required check has to be told which declaration to edit,
        not merely that one is wrong.
        """
        self.test_every_declaration_states_a_read_only_secret_to_read()
        offenders = []
        for name in sorted(self.declarations):
            declaration = self.declarations[name]
            if declaration.read_only_secret != SHADOWED_WRITE_TOKEN:
                continue
            where = (
                declaration.path.relative_to(ROOT).as_posix()
                if declaration.path
                else f"terraform/environments/{name}"
            )
            offenders.append(
                f"{name} ({where}) declares {SHADOWED_WRITE_TOKEN!r} as its read-only "
                "secret"
            )
        self.assertEqual(
            [],
            offenders,
            f"{SHADOWED_WRITE_TOKEN} is the name every GitHub Environment defines for "
            "its Read & Write token, and an Environment secret shadows a repository "
            "secret of the same name. Read from a job that declares an "
            "`environment:` -- which the converge job does -- this field yields the "
            "WRITE token, silently and with no error: " + "; ".join(offenders),
        )


# --------------------------------------------------------------------------
# iac-host-configuration / Dynamic Inventory via hcloud Plugin (MODIFIED)
# --------------------------------------------------------------------------


class TestASourcesCredentialVariableIsTheNameTheEnvironmentDeclares(unittest.TestCase):
    """MODIFIED requirement: Dynamic Inventory via hcloud Plugin -- scenario "A
    source's credential variable is the name the environment declares"."""

    def setUp(self) -> None:
        self.pairs = committed_credential_pairs()
        self.assertTrue(
            self.pairs,
            "no environment has both a pipeline declaration and an inventory source, "
            "so this comparison would read nothing",
        )

    def test_each_source_reads_the_name_its_declaration_states(self) -> None:
        """SPECIFIED -- "The environment-variable name a source reads its
        credential from SHALL be the same name that environment declares as its
        read-only secret"."""
        offences = credential_disagreements(self.pairs)
        self.assertEqual(
            [],
            offences,
            "an environment's inventory source and its pipeline declaration name "
            "different variables for the same credential, so 'adding an environment "
            "needs no workflow edit' rests on a coincidence rather than on an "
            "obligation: " + "; ".join(offences),
        )

    def test_the_comparison_is_literal_rather_than_case_insensitive(self) -> None:
        """SPECIFIED -- the clause says "the same name", and tasks.md 2.4 states
        what "same" must mean here: GitHub resolves `secrets[...]`
        case-insensitively while Ansible's env lookup does not, so a
        case-only difference resolves in the workflow and fails in the play.

        Run against a fixture pair rather than the tree: at two environments the
        committed files cannot demonstrate that this comparison discriminates,
        and a comparison that folded case would satisfy the assertion above
        while admitting exactly the shape it exists to catch.
        """
        folded = credential_disagreements(
            [("alpha", "HCLOUD_TOKEN_ALPHA", "hcloud_token_alpha", "alpha.hcloud.yml")]
        )
        self.assertEqual(
            1,
            len(folded),
            "a declaration and a source differing only in the case of one name were "
            "read as agreeing, so this comparison is case-insensitive where Ansible's "
            f"env lookup is not: {folded}",
        )
        agreeing = credential_disagreements(
            [("alpha", "HCLOUD_TOKEN_ALPHA", "HCLOUD_TOKEN_ALPHA", "alpha.hcloud.yml")]
        )
        self.assertEqual(
            [],
            agreeing,
            "a declaration and a source naming one variable were reported as "
            f"disagreeing, so this comparison refuses everything: {agreeing}",
        )


class TestAnEnvironmentThatCanBeProvisionedCanBeConverged(unittest.TestCase):
    """MODIFIED requirement: Dynamic Inventory via hcloud Plugin -- scenario "An
    environment that can be provisioned but not converged is reported", and the
    clause "An environment that carries a pipeline declaration SHALL carry an
    inventory source and a variables file of its own"."""

    def setUp(self) -> None:
        self.environments = sorted(
            directory.name for directory in environment_directories()
        )
        self.assertTrue(
            self.environments,
            "no environment directory was discovered, so this census would pass "
            "having compared nothing",
        )

    def test_every_provisioned_environment_has_a_source_and_variables_of_its_own(
        self,
    ) -> None:
        """SPECIFIED -- the clause above. The source half is also held by
        `test_host_configuration_names_its_environment
        .TestEachEnvironmentHasAnInventorySourceOfItsOwn`; the variables half is
        held nowhere else, and it is the half the converge job's discovery
        refuses on (tasks.md 3.2)."""
        sources = {source.environment for source in inventory_sources()}
        missing = []
        for name in self.environments:
            if name not in sources:
                missing.append(
                    f"{name}: carries a pipeline declaration but no inventory source, "
                    "so it can be provisioned and converged by nothing"
                )
            if not (GROUP_VARS_DIR / f"{name}.yml").is_file():
                missing.append(
                    f"{name}: carries no "
                    f"{(GROUP_VARS_DIR / f'{name}.yml').relative_to(ROOT).as_posix()}, "
                    "so a converge of it would run with no variables of its own"
                )
        self.assertEqual(
            [],
            missing,
            "an environment whose host configuration nothing applies is "
            "indistinguishable from an environment that has nothing to converge: "
            + "; ".join(missing),
        )


class TestTheConnectionAddressIsSelectableAndDefaultsToThePublicOne(unittest.TestCase):
    """ADDED requirement: The Address a Converge Connects To Is Selected Per Run.

    READ THIS BEFORE READING A GREEN RUN OF THIS CLASS. The requirement's four
    scenarios are about what a run CONNECTS TO, which no static read can
    establish and which that change's tasks.md 1.3 records as manual
    verification against the live API. What is asserted here is strictly the
    committed shape of the option -- that a selection exists, that it is read
    per run, and that its default literal is the public address -- which is the
    "The default SHALL be the public address" sentence and nothing more. See
    this change's test-plan.md, where all four scenarios are recorded as
    established elsewhere.
    """

    def setUp(self) -> None:
        self.selections = connection_selections()
        self.assertTrue(
            self.selections,
            "no inventory source was discovered, so this class would read nothing",
        )

    def test_every_source_takes_its_connection_address_per_run(self) -> None:
        """SPECIFIED -- "The address a host-configuration run connects to SHALL
        be selected per run". A source with no `connect_with` option takes the
        plugin's own default and offers a run no selection at all."""
        offenders = sorted(
            selection.source.relative
            for selection in self.selections
            if not selection.declared or selection.variable is None
        )
        self.assertEqual(
            [],
            offenders,
            "these inventory sources state no per-run connection-address selection "
            f"this read can resolve to an environment variable: {offenders}. Without "
            "one, an unattended run cannot select the tailnet address and the cloud "
            "firewall drops it",
        )

    def test_the_selection_defaults_to_the_public_address(self) -> None:
        """SPECIFIED -- "The default SHALL be the public address, so that a run
        supplying nothing behaves as it does today and the bootstrap path stays
        reachable"."""
        offenders = sorted(
            f"{selection.source.relative} defaults to {selection.default!r}"
            for selection in self.selections
            if selection.default != PUBLIC_ADDRESS_CHOICE
        )
        self.assertEqual(
            [],
            offenders,
            "a run supplying no selection must reach the host's public address, which "
            "is what a first converge of a host not yet on the tailnet requires: "
            + "; ".join(offenders),
        )

    def test_no_source_templates_the_plugins_own_connect_with_option(self) -> None:
        """DERIVED, from task 1.3's live verification rather than from a
        scenario. `connect_with` is choice-validated before templating, so a
        source carrying a Jinja expression there does not parse at all -- the
        plugin reports the template text itself as an invalid choice. It reads
        like the obvious mechanism, which is why it is refused by name."""
        offenders = sorted(
            selection.source.relative
            for selection in self.selections
            if selection.templated_connect_with
        )
        self.assertEqual(
            [],
            offenders,
            "these inventory sources put a template in the plugin's `connect_with` "
            "option, which is validated against its choices BEFORE it is templated -- "
            f"so the source does not parse, for CI or for a workstation: {offenders}",
        )

    def test_every_source_makes_an_unhonourable_selection_fail(self) -> None:
        """SPECIFIED -- "A selection the inventory cannot honour SHALL fail the
        run rather than falling back to another address".

        Under the mechanism this repository uses, that is `strict: true`: a
        `compose` expression that raises is SKIPPED silently without it, leaving
        `ansible_host` at the public address the plugin already set. The
        requirement's "rather than falling back" is exactly that fallback.
        """
        offenders = sorted(
            selection.source.relative
            for selection in self.selections
            if not selection.strict
        )
        self.assertEqual(
            [],
            offenders,
            "these inventory sources do not set `strict: true`, so a connection "
            "address selection they cannot honour is skipped silently and the run "
            f"connects to the public address instead of failing: {offenders}",
        )

    def test_every_source_reads_the_same_selection_variable(self) -> None:
        """DERIVED -- tasks.md 1.2 makes the line identical in both sources, and
        the converge job sets ONE variable for whichever environment its matrix
        row names (tasks.md 3.4a). Two sources reading different variables would
        make the job's job-level `env:` block correct for one environment and
        silently inert for the other."""
        named = sorted(
            selection.variable
            for selection in self.selections
            if selection.variable is not None
        )
        self.assertEqual(
            len(self.selections),
            len(named),
            "an inventory source states no connection-address variable this read can "
            f"resolve, so this comparison would pass over it: {named}. Without the "
            "count, a tree in which NO source states one reads as a tree in which "
            "every source agrees",
        )
        self.assertEqual(
            1,
            len(set(named)),
            "the inventory sources read different variables for the connection "
            f"address: {sorted(set(named))}. The converge job sets one name per run, "
            "so a second name is an environment whose selection nothing supplies",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Host Configuration Is Applied by a Gated Workflow (ADDED)
# -- the workflow as committed
# --------------------------------------------------------------------------


class TestAMergeConvergesWithoutAWorkstation(WorkflowLocatorMixin, unittest.TestCase):
    """ADDED requirement: Host Configuration Is Applied by a Gated Workflow --
    scenario "A merge to the host configuration converges without a
    workstation"."""

    def test_the_workflow_is_triggered_by_a_merge_touching_the_host_configuration(
        self,
    ) -> None:
        """SPECIFIED -- "Host configuration SHALL reach a host through a
        workflow triggered by a merge to the default branch"."""
        on = triggers(self.workflow())
        push = on.get("push")
        self.assertIsInstance(
            push,
            dict,
            f"{HOST_CONVERGE.name} declares no `push:` trigger, so a merge converges "
            f"nothing and the host layer still reaches a host from a workstation: "
            f"{sorted(on)}",
        )
        branches = [str(entry) for entry in (push.get("branches") or [])]
        self.assertIn(
            DEFAULT_BRANCH,
            branches,
            f"the push trigger does not name `{DEFAULT_BRANCH}`, so what reaches a "
            f"host is not a merge to the default branch: {branches}",
        )
        patterns = [str(entry) for entry in (push.get("paths") or [])]
        self.assertTrue(
            any(gh_glob_matches(pattern, A_HOST_CONFIGURATION_PATH) for pattern in patterns),
            f"no path filter matches `{A_HOST_CONFIGURATION_PATH}`, so a merge "
            f"changing the host configuration converges nothing: {patterns}",
        )

    def test_a_run_can_also_be_requested_by_hand_for_one_environment(self) -> None:
        """SPECIFIED -- scenario "A run is requested for an environment that
        does not exist" presupposes that a converge can be requested by hand.
        The input's NAME is DERIVED (tasks.md 3.1)."""
        on = triggers(self.workflow())
        self.assertIn(
            "workflow_dispatch",
            on,
            f"{HOST_CONVERGE.name} cannot be dispatched, so a converge of a single "
            "environment can only be had by pushing a commit at the host "
            "configuration",
        )
        dispatch = on.get("workflow_dispatch") or {}
        inputs = (dispatch or {}).get("inputs") or {}
        self.assertIn(
            DISPATCH_INPUT_NAME,
            inputs,
            f"the dispatch trigger takes no `{DISPATCH_INPUT_NAME}` input, so a run "
            f"requested by hand names no environment: {sorted(inputs)}",
        )
        self.assertNotIn(
            "options",
            inputs[DISPATCH_INPUT_NAME] or {},
            "the dispatch input enumerates its choices, which names every environment "
            "in workflow text -- the state 'adding an environment requires no change "
            "to any file under `.github/workflows/`' forbids (tasks.md 3.1)",
        )

    def test_the_converge_job_runs_the_host_baseline_play(self) -> None:
        """SPECIFIED -- "no step of that converge SHALL require a command run
        from an operator's machine": the play the operator runs by hand today is
        run by the workflow instead."""
        workflow = self.workflow()
        name, job = self.converge_job()
        found = []
        for index, step, lines in invoking_steps(job, ANSIBLE_PLAYBOOK):
            where = effective_working_directory(workflow, job, step)
            for line in lines:
                for token in line.split():
                    if token.endswith(".yml") or token.endswith(".yaml"):
                        found.append(resolved_from(where, token))
        self.assertIn(
            f"ansible/{HOST_BASELINE_PLAY}",
            found,
            f"the converge job in {HOST_CONVERGE.name} runs no playbook resolving to "
            f"`ansible/{HOST_BASELINE_PLAY}`, so what a merge applies is not the host "
            f"baseline an operator applies today: {sorted(set(found))}",
        )


class TestThePreApprovalJobHoldsNoConvergeCredential(
    WorkflowLocatorMixin, unittest.TestCase
):
    """ADDED requirement: Host Configuration Is Applied by a Gated Workflow --
    scenario "The pre-approval job holds no converge credential"."""

    def test_the_publishing_job_declares_no_github_environment(self) -> None:
        """SPECIFIED -- "it SHALL declare no GitHub Environment"."""
        name, job = self.publishing_job()
        self.assertIsNone(
            declared_environment(job),
            f"the job publishing what the merge changes (`{name}`) declares the "
            f"GitHub Environment `{declared_environment(job)}`, so it holds that "
            "Environment's secrets -- and it is the job whose whole purpose is to be "
            "readable before anyone approves anything",
        )

    def test_the_publishing_job_consumes_no_secret(self) -> None:
        """SPECIFIED -- "SHALL consume no credential capable of reaching a
        host". Swept over every surface of the job that can carry one -- its
        job-level `env:`, and each step's `env:`, `with:`, `run:` and `if:` --
        because a credential handed to an action through `with:` reaches the
        same place a `run:` body would put it."""
        name, job = self.publishing_job()
        offenders = []
        for label, body in job_surfaces(job):
            for match in re.finditer(r"secrets[.\[]\s*([A-Za-z0-9_'\"-]+)", body):
                offenders.append(f"{name}{label} reads `secrets.{match.group(1)}`")
        self.assertEqual(
            [],
            sorted(set(offenders)),
            "the job that publishes the diff for a human to read holds a secret, so "
            "the credential the gate exists to withhold is present before the gate: "
            f"{sorted(set(offenders))}",
        )

    def test_the_publishing_job_publishes_the_host_configuration_diff(self) -> None:
        """SPECIFIED -- "SHALL publish, for a human to read, what the merge
        changes under the host-configuration directory", and "What the
        pre-approval job publishes is the committed diff"."""
        name, job = self.publishing_job()
        diffing = [
            step_label(name, index, step)
            for index, step, _ in invoking_steps(job, GIT_DIFF)
        ]
        self.assertTrue(
            diffing,
            f"the job `{name}` writes to the run summary without taking a diff, so "
            "what it publishes is not what the merge changes. This layer has no "
            "saved-plan artifact and the committed diff is what stands in its place",
        )
        body = "\n".join(
            str(step.get("run") or "") for step in (job.get("steps") or [])
        )
        self.assertIn(
            "ansible",
            uncommented(body),
            f"the job `{name}` publishes a diff that is not scoped to the "
            "host-configuration directory, so a reviewer reads a merge's whole diff "
            "rather than what the converge will apply",
        )


class TestTheConvergeJobIsGatedOnItsOwnGitHubEnvironment(
    WorkflowLocatorMixin, unittest.TestCase
):
    """ADDED requirement: Host Configuration Is Applied by a Gated Workflow --
    scenario "The converge job is gated on the environment's own GitHub
    Environment", and the MODIFIED requirement's scenario "A new environment
    needs no workflow edit", which this change extends to name the host-converge
    workflow."""

    def test_the_converge_job_takes_its_environment_from_discovery(self) -> None:
        """SPECIFIED -- "it SHALL declare the GitHub Environment named by that
        environment's own pipeline declaration, so that its protection rules and
        its secrets are the ones that apply"."""
        workflow = self.workflow()
        name, job = self.converge_job()
        environment = declared_environment(job)
        self.assertIsNotNone(
            environment,
            f"the converge job `{name}` declares no GitHub Environment, so the "
            "credentials a converge needs are repository-scoped and no protection "
            "rule applies to a production converge",
        )
        self.assertRegex(
            str(environment),
            r"\$\{\{",
            f"the converge job `{name}` names its GitHub Environment as the literal "
            f"{environment!r}. The Environment SHALL be the one that environment's own "
            "declaration names, resolved per matrix row -- a literal is a second "
            "environment's Environment written in workflow text",
        )
        matrix = (job.get("strategy") or {}).get("matrix")
        self.assertRegex(
            re.sub(r"\s+", "", str(matrix)),
            r"needs\.[A-Za-z0-9_-]+\.outputs\.",
            f"the converge job `{name}`'s matrix is not built from another job's "
            f"outputs, so which environments it covers comes from workflow text "
            f"rather than from discovery over committed files: {matrix!r}",
        )

    def test_the_workflow_names_no_environment(self) -> None:
        """SPECIFIED -- "The workflow SHALL name no environment", and the
        MODIFIED scenario's "with no change to any file under
        `.github/workflows/`".

        Matched case-sensitively over the workflow with its whole-line comments
        stripped, which is the same sweep
        `test_environment_agnostic_pipeline.TestNoWorkflowNamesAnEnvironment`
        makes over the three Terraform workflows -- widened here to this file
        rather than by editing that one.
        """
        names = {directory.name for directory in environment_directories()}
        for declaration in environment_declarations().values():
            if declaration.github_environment:
                names.add(declaration.github_environment)
        self.assertTrue(
            names,
            "no environment directory and no declared GitHub Environment name was "
            "found, so this sweep would read nothing",
        )
        body = uncommented(read_text(HOST_CONVERGE))
        offenders = []
        for name in sorted(names):
            for occurrence in re.finditer(
                rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])", body
            ):
                line = body.count("\n", 0, occurrence.start()) + 1
                offenders.append(f"{HOST_CONVERGE.name}:{line} names `{name}`")
        self.assertEqual(
            [],
            offenders,
            "the host-converge workflow names an environment in its own text, so a "
            "further environment could not be converged without editing a file under "
            f"`.github/workflows/`: {offenders}",
        )

    def test_no_step_maps_an_environment_to_its_secret(self) -> None:
        """SPECIFIED -- "which repository secret holds each one's read-only
        credential SHALL come from discovery over committed files". A mapping
        can be written without spelling an environment's name: a literal
        read-only secret name only one environment uses is one."""
        declared = sorted(
            {
                declaration.read_only_secret
                for declaration in environment_declarations().values()
                if declaration.read_only_secret
            }
        )
        self.assertTrue(
            declared,
            "no environment declares a read-only secret name, so this sweep would "
            "read nothing",
        )
        offenders = []
        for name, job in jobs(self.workflow()).items():
            for label, body in job_surfaces(job):
                for secret in declared:
                    if re.search(
                        rf"secrets\.{re.escape(secret)}(?![A-Za-z0-9_])",
                        uncommented(body),
                    ):
                        offenders.append(f"{name}{label} reads `secrets.{secret}`")
        self.assertEqual(
            [],
            sorted(set(offenders)),
            "the workflow reads a specific environment's read-only secret by name, so "
            "which credential a converge runs under comes from workflow text rather "
            f"than from that environment's own declaration: {sorted(set(offenders))}",
        )


class TestTheConvergeJobIsProvisionedBeforeItRuns(
    WorkflowLocatorMixin, unittest.TestCase
):
    """ADDED requirement: Host Configuration Is Applied by a Gated Workflow --
    scenario "The converge job supplies what the run needs"."""

    def _first_ansible_index(self, job: dict) -> int | None:
        for index, step in enumerate(job.get("steps") or []):
            lines = invocation_lines(step.get("run", ""), ANSIBLE_PLAYBOOK)
            lines += invocation_lines(step.get("run", ""), ANSIBLE_INVENTORY)
            if lines:
                return index
        return None

    def _indices(self, job: dict, pattern) -> list:
        return [index for index, _, _ in invoking_steps(job, pattern)]

    def test_the_toolchain_and_galaxy_content_are_installed_first(self) -> None:
        """SPECIFIED -- "SHALL install the toolchain and the external content
        the play needs before running it, from this repository's own pinned
        manifests". A runner carries neither, and a run that reaches a missing
        plugin or a missing external role fails inside a mechanism, reading as a
        broken mechanism rather than as an unprovisioned machine."""
        name, job = self.converge_job()
        first = self._first_ansible_index(job)
        self.assertIsNotNone(
            first,
            f"the converge job `{name}` invokes neither `ansible-playbook` nor "
            "`ansible-inventory`, so there is nothing to provision before",
        )
        for pattern, what in (
            (PIP_INSTALL, "the pinned Python toolchain"),
            (GALAXY_COLLECTION_INSTALL, "the pinned Galaxy collections"),
            (GALAXY_ROLE_INSTALL, "the pinned Galaxy roles"),
        ):
            indices = self._indices(job, pattern)
            self.assertTrue(
                indices,
                f"the converge job `{name}` never installs {what}. The first command "
                "this job runs loads the `hcloud` inventory plugin and the play's "
                "first role is an external one; a runner carries neither",
            )
            self.assertLess(
                min(indices),
                first,
                f"the converge job `{name}` installs {what} only after it has already "
                "started running Ansible",
            )

    def test_every_ansible_command_runs_from_the_directory_that_configures_it(
        self,
    ) -> None:
        """SPECIFIED -- "SHALL run from the directory whose configuration
        governs the run". Ansible loads `./ansible.cfg` from the current
        directory, so from the repository root it loads none: `roles_path` stops
        resolving and `any_unparsed_is_failed` reverts to its default, which is
        the setting the "an inventory source whose credential is absent or is
        rejected SHALL fail the run" clause is false without. A converge run
        from the wrong directory does not fail -- it loses a guard, and reports
        a rejected token as a destroyed server."""
        self.assertTrue(
            (ANSIBLE_DIR / "ansible.cfg").is_file(),
            "ansible/ansible.cfg is absent, so this assertion names a directory whose "
            "configuration governs nothing",
        )
        workflow = self.workflow()
        name, job = self.converge_job()
        offenders = []
        for index, step in enumerate(job.get("steps") or []):
            if not invocation_lines(step.get("run", ""), ANY_ANSIBLE_COMMAND):
                continue
            where = effective_working_directory(workflow, job, step)
            if resolved_from(".", where) != "ansible":
                offenders.append(f"{step_label(name, index, step)} runs in {where!r}")
        self.assertEqual(
            [],
            offenders,
            "these steps run an Ansible command from a directory that is not "
            f"`ansible/`, where this repository's `ansible.cfg` lives: {offenders}",
        )


class TestTheConvergeRunsTheAnsibleTheRolesWereVerifiedUnder(
    WorkflowLocatorMixin, unittest.TestCase
):
    """ADDED requirement: Host Configuration Is Applied by a Gated Workflow --
    scenario "The converge runs the Ansible the roles were verified under".

    TWO assertions, and the second alone is not the scenario. Asserting only
    that the two manifests agree passes while the job installs from somewhere
    else entirely -- the files agree and the property does not hold (tasks.md
    3.4-0). So the job's install step is read as well, and the manifest it names
    is resolved from that step's own working directory rather than compared as a
    spelling: from a job that runs in `ansible/`, `ansible/requirements.txt`
    resolves to `ansible/ansible/requirements.txt`, which is the trap tasks.md
    3.4-1 names.
    """

    def test_the_converge_job_installs_from_the_repositorys_own_manifest(self) -> None:
        """SPECIFIED -- "SHALL install the toolchain ... from this repository's
        own pinned manifests", and the scenario's "the version the converge job
        installs"."""
        workflow = self.workflow()
        name, job = self.converge_job()
        named = []
        for index, step, lines in invoking_steps(job, PIP_INSTALL):
            where = effective_working_directory(workflow, job, step)
            for line in lines:
                for match in REQUIREMENT_ARGUMENT.finditer(line):
                    named.append(resolved_from(where, match.group(1)))
        self.assertIn(
            CONVERGE_MANIFEST.relative_to(ROOT).as_posix(),
            named,
            f"the converge job `{name}` installs its toolchain from "
            f"{sorted(set(named))} rather than from "
            f"{CONVERGE_MANIFEST.relative_to(ROOT).as_posix()}, so the version of "
            "Ansible it converges production under is whatever that other source "
            "resolves to. The agreement asserted below would then hold between two "
            "files neither of which the job reads",
        )

    def test_the_two_manifests_pin_one_version(self) -> None:
        """SPECIFIED -- "The version of Ansible a converge runs SHALL be the
        version the role-verification suite runs", and "a difference SHALL fail
        the required status check"."""
        verified = pinned_ansible(VERIFICATION_MANIFEST)
        self.assertIsNotNone(
            verified,
            f"{VERIFICATION_MANIFEST.relative_to(ROOT).as_posix()} states no exact "
            f"`{ANSIBLE_DISTRIBUTION}` pin, so there is no verified version for a "
            "converge to agree with",
        )
        converging = pinned_ansible(CONVERGE_MANIFEST)
        self.assertIsNotNone(
            converging,
            f"{CONVERGE_MANIFEST.relative_to(ROOT).as_posix()} states no exact "
            f"`{ANSIBLE_DISTRIBUTION}` pin (the file may not exist yet), so the "
            "Ansible that converges production is pinned by nothing",
        )
        self.assertEqual(
            verified,
            converging,
            f"the converge installs {ANSIBLE_DISTRIBUTION} {converging} while the "
            f"role-verification suite installs {verified}. A converge applying roles "
            "under a different Ansible than the one they were verified under is "
            "verified by nothing",
        )

    def test_the_pin_read_discriminates(self) -> None:
        """DERIVED -- no scenario states it. Without it, a reader returning
        `None` for every file would satisfy the equality above as soon as both
        files existed, and a reader that folded a floating range into a pin
        would report agreement between two versions that are not one."""
        self.assertEqual(
            {"ansible-core": "2.21.3"},
            pins("# a comment\nansible-core==2.21.3  # pinned\n"),
            "the pin reader does not read an exact pin carrying a trailing comment",
        )
        self.assertEqual(
            {},
            pins("ansible-core>=2.21\nmolecule\n"),
            "the pin reader read a floating range as an exact pin, so two manifests "
            "stating ranges would compare equal while resolving to different versions",
        )


class TestOneEnvironmentsConvergeDoesNotSilenceAnother(
    WorkflowLocatorMixin, unittest.TestCase
):
    """ADDED requirement: Host Configuration Is Applied by a Gated Workflow --
    scenario "One environment's failure does not silence another's", and "A
    converge SHALL NOT be cancelled in favour of a later one"."""

    def test_a_failing_converge_does_not_abandon_its_siblings(self) -> None:
        """SPECIFIED -- "every other environment's converge SHALL still run and
        report its own outcome"."""
        name, job = self.converge_job()
        strategy = job.get("strategy") or {}
        self.assertIn(
            "fail-fast",
            strategy,
            f"the converge job `{name}` declares no `fail-fast:`, which defaults to "
            "true: one environment's converge failing would cancel every other "
            "environment's before it reported",
        )
        self.assertIs(
            False,
            strategy.get("fail-fast"),
            f"the converge job `{name}` declares `fail-fast: "
            f"{strategy.get('fail-fast')!r}`",
        )

    def test_an_in_flight_converge_is_not_cancelled_by_a_later_one(self) -> None:
        """SPECIFIED -- "Runs against one environment SHALL be serialised, and
        an in-flight converge SHALL be allowed to finish: interrupting a play
        mid-run leaves the host partially converged, which is recoverable as an
        exception and not as a normal case"."""
        workflow = self.workflow()
        name, job = self.converge_job()
        concurrency = job.get("concurrency") or workflow.get("concurrency")
        self.assertTrue(
            concurrency,
            f"neither the converge job `{name}` nor {HOST_CONVERGE.name} declares a "
            "`concurrency:` group, so two merges in quick succession run two plays "
            "against one host at once",
        )
        if isinstance(concurrency, str):
            self.fail(
                f"the concurrency group is the bare string {concurrency!r}, so "
                "`cancel-in-progress` takes its default -- which is false today and "
                "is a repository-wide default this workflow must not rest on"
            )
        self.assertIs(
            False,
            concurrency.get("cancel-in-progress"),
            "an in-flight converge would be cancelled in favour of a later one, which "
            "leaves a host partially converged as a matter of routine rather than as "
            f"an exception: {concurrency!r}",
        )
        self.assertRegex(
            re.sub(r"\s+", "", str(concurrency.get("group"))),
            r"\$\{\{",
            f"the concurrency group {concurrency.get('group')!r} carries no "
            "expression, so it is one group for every environment: one environment's "
            "converge would queue behind another's for no reason, and the "
            "serialisation the requirement asks for is per environment",
        )


class TestAWrongSecretStopsTheRunBeforeTheHostIsTouched(
    WorkflowLocatorMixin, unittest.TestCase
):
    """ADDED requirement: Host Configuration Is Applied by a Gated Workflow --
    scenario "A wrong secret stops the run before the host is touched"."""

    def test_the_credentials_are_exercised_before_the_play_runs(self) -> None:
        """SPECIFIED -- "A converge job SHALL establish that the credentials it
        holds are usable -- that the environment's secrets decrypt and that its
        inventory resolves -- before any task acts on the host".

        A `!vault` value is decrypted at FIRST USE, which is several roles into
        the play (design.md Decision 9), so without a preflight a wrong password
        leaves a partially-converged host for a reason that had nothing to do
        with the host. The preflight is identified by what the requirement says
        it must do: resolve the inventory, with the vault secret in hand.
        """
        name, job = self.converge_job()
        preflight = [
            index
            for index, step, lines in invoking_steps(job, ANSIBLE_INVENTORY)
            if invocation_lines(step.get("run", ""), VAULT_ARGUMENT)
        ]
        self.assertTrue(
            preflight,
            f"the converge job `{name}` runs no step that resolves the inventory with "
            "the environment's vault secret, so the first thing to exercise either "
            "credential is the play itself",
        )
        play = [index for index, _, _ in invoking_steps(job, ANSIBLE_PLAYBOOK)]
        self.assertTrue(play, f"the converge job `{name}` runs no play")
        self.assertLess(
            min(preflight),
            min(play),
            f"the converge job `{name}` resolves its inventory only after the play "
            "has started, so a rejected credential is discovered partway through a "
            "converge rather than before the first role acts on the host",
        )

    def test_the_play_is_given_the_environment_the_matrix_row_names(self) -> None:
        """SPECIFIED -- "The selection SHALL decide only which address is
        dialled. It SHALL NOT relax any other guard: the environment the run
        names ... appl[ies] identically" (iac-host-configuration), and the
        play's own required input. DERIVED in one respect: the input's name
        comes from the committed playbook rather than from a scenario."""
        name, job = self.converge_job()
        bodies = "\n".join(
            "\n".join(invocation_lines(step.get("run", ""), ANSIBLE_PLAYBOOK))
            for _, step, _ in invoking_steps(job, ANSIBLE_PLAYBOOK)
        )
        self.assertIn(
            "target_environment",
            bodies,
            f"the converge job `{name}` runs the baseline play without naming the "
            "environment it targets, so the play's own guard has nothing to refuse "
            f"on: {bodies!r}",
        )
        self.assertRegex(
            re.sub(r"\s+", "", bodies),
            r"\$\{\{|\$[A-Z_]",
            f"the converge job `{name}` names the environment it targets as a literal "
            "rather than taking it from the matrix row",
        )


class TestTheConvergeSelectsTheAddressTheInventoryReads(
    WorkflowLocatorMixin, unittest.TestCase
):
    """ADDED requirement: The Address a Converge Connects To Is Selected Per Run
    -- "Selecting the tailnet address SHALL be a deliberate act of the run that
    wants it".

    What is established here is that the deliberate act is the converge job's,
    and that the variable it sets is the variable the committed sources read.
    That the two addresses coincide at run time is observed on the first real
    run (tasks.md 3.7 and 7.5), not here.
    """

    def test_the_converge_job_sets_the_variable_the_sources_read(self) -> None:
        """DERIVED -- tasks.md 3.4a and design.md Decision 3. No scenario states
        where the selection is set; what the scenario states is that selecting
        the tailnet address is deliberate, and a job-level `env:` block is where
        this change makes that act."""
        selections = connection_selections()
        named = sorted({s.variable for s in selections if s.variable})
        self.assertEqual(
            1,
            len(named),
            "the committed inventory sources name no single connection-address "
            f"variable, so there is no name to look for in the workflow: {named}",
        )
        variable = named[0]
        workflow = self.workflow()
        name, job = self.converge_job()
        job_level = {str(key) for key in (job.get("env") or {})}
        self.assertIn(
            variable,
            job_level,
            f"the converge job `{name}` does not set `{variable}` in its job-level "
            "`env:`, so the job dials the public IPv4 the sources default to and the "
            "cloud firewall drops it. On individual steps the preflight's derived "
            "address and the play's dialled address could disagree",
        )
        self.assertNotIn(
            variable,
            {str(key) for key in (workflow.get("env") or {})},
            f"`{variable}` is set at workflow level, so it reaches the credential-less "
            "job too -- a job that connects to nothing and must stay readable as such",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Host Configuration Is Applied by a Gated Workflow (ADDED)
# -- discovery, run rather than read
# --------------------------------------------------------------------------


class HostConvergeTreeFixtureMixin(DeclarationTreeFixtureMixin):
    """Builds a synthetic tree carrying both sides discovery cross-checks.

    Both sides are built from THIS REPOSITORY's own committed files -- prod's
    declaration for the Terraform side (the base mixin's job) and a committed
    inventory source for the Ansible side -- rather than from a shape this file
    invented. The filenames are not free: the `hcloud` plugin's `verify_file`
    accepts a path only if it ends `hcloud.yml` or `hcloud.yaml`, and Ansible
    resolves `group_vars/<group>.yml`, so a fixture spelling either differently
    would be refused by a correct discovery for the right reason and would read
    as a defect in the workflow.
    """

    def _source_template(self):
        sources = inventory_sources()
        if not sources:
            self.fail(
                "no committed inventory source was found, so this fixture has no "
                "shape to follow. Write an environment's inventory source first"
            )
        return sources[0]

    def _write_ansible_side(self, directory: Path, environments: dict) -> None:
        """`environments` maps an environment name to a pair
        (has inventory source, has group_vars file)."""
        template = self._source_template()
        inventory = directory / "ansible" / "inventory"
        (inventory / "group_vars").mkdir(parents=True, exist_ok=True)
        for name, (has_source, has_group_vars) in environments.items():
            if has_source:
                document = dict(template.document)
                if template.credential:
                    document = json.loads(
                        json.dumps(document).replace(
                            template.credential, f"HCLOUD_TOKEN_{name.upper()}"
                        )
                    )
                (inventory / f"{name}.hcloud.yml").write_text(
                    yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
                )
            if has_group_vars:
                (inventory / "group_vars" / f"{name}.yml").write_text(
                    "---\n# fixture variables for this environment\n", encoding="utf-8"
                )

    def _convergeable(self, directory: Path, names) -> None:
        """The clean tree: every environment declared, sourced and varied."""
        self._write_tree(
            directory,
            {
                name: self._declaration_for(
                    f"HCLOUD_TOKEN_{name.upper()}", f"{name}-environment", gate=False
                )
                for name in names
            },
        )
        self._write_ansible_side(directory, {name: (True, True) for name in names})


class TestHostConvergeDiscoveryFailsClosed(
    HostConvergeTreeFixtureMixin, WorkflowLocatorMixin, unittest.TestCase
):
    """ADDED requirement: Host Configuration Is Applied by a Gated Workflow --
    "Discovery SHALL fail closed, with a message naming the environment and what
    was wrong, rather than omitting an environment from the run".

    Runs the workflow's own discovery body rather than reading it, the same
    extract-and-run shape `test_environment_agnostic_pipeline
    .TestDiscoveryFailsClosed` uses over the Terraform workflows. Grepping would
    establish that a discovery step exists; only running it establishes that it
    refuses.

    UNRESOLVED PROJECT QUESTION, recorded in this change's test-plan.md and
    repeated here because a reader of a red test needs it: nothing in this
    change fixes the environment variable the dispatch input arrives under
    inside the body. It is resolved from the step's own `env:` block -- the key
    whose value references the dispatch input -- so the implementing author's
    choice of name is followed rather than asserted.
    """

    def setUp(self) -> None:
        require_external_tools(
            self,
            ("bash", "find", "jq"),
            "execute the host-converge workflow's environment-discovery body",
        )

    def _input_variable(self, job: dict, step: dict) -> str | None:
        for holder in (step, job):
            for key, value in (holder.get("env") or {}).items():
                if DISPATCH_INPUT.search(str(value)):
                    return str(key)
        return None

    def _run_discovery(self, tree: Path, dispatched: str | None = None):
        job_name, job, step = self.discovery_step()
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
        for holder in (job, step):
            for key, value in (holder.get("env") or {}).items():
                if not ACTIONS_EXPRESSION.search(str(value)):
                    environment[str(key)] = str(value)
        variable = self._input_variable(job, step)
        if dispatched is not None:
            self.assertIsNotNone(
                variable,
                "the discovery step takes no environment variable carrying the "
                "dispatch input, so a run requested by hand naming an environment "
                "reaches the body that would have to validate it through nothing. "
                f"Its `env:` keys are {sorted((step.get('env') or {}))}",
            )
            environment[variable] = dispatched
        elif variable:
            environment[variable] = ""
        result = run_snippet(str(step["run"]), environment, tree)
        return result, outputs

    def _combined(self, result) -> str:
        return (result.stdout + result.stderr).strip()

    def test_discovery_emits_every_convergeable_environment(self) -> None:
        """SPECIFIED -- "Which environments exist, which GitHub Environment
        gates each, and which repository secret holds each one's read-only
        credential SHALL come from discovery over committed files".

        The converse every refusal below needs: discovery that failed on every
        tree would satisfy each of them while converging nothing.
        """
        scratch = self._scratch()
        self._convergeable(scratch, ("alpha", "bravo"))
        result, outputs = self._run_discovery(scratch)
        detail = self._combined(result)[-800:]
        self.assertEqual(
            0,
            result.returncode,
            f"discovery refused a tree carrying two convergeable environments: "
            f"{detail!r}",
        )
        emitted = outputs.read_text(encoding="utf-8") + result.stdout
        for expected in (
            "alpha",
            "bravo",
            "alpha-environment",
            "bravo-environment",
            "HCLOUD_TOKEN_ALPHA",
            "HCLOUD_TOKEN_BRAVO",
        ):
            self.assertIn(
                expected,
                emitted,
                f"discovery ran over a tree holding `{expected}` and emitted nothing "
                "naming it, so the converge job would take that value from workflow "
                f"text or not at all: {emitted!r}",
            )

    def test_discovery_fails_on_a_source_whose_environment_declares_no_pipeline(
        self,
    ) -> None:
        """SPECIFIED -- scenario "An environment that cannot be converged fails
        the workflow": "an inventory source whose environment declares no
        pipeline configuration"."""
        scratch = self._scratch()
        self._convergeable(scratch, ("alpha",))
        self._write_ansible_side(scratch, {"bravo": (True, True)})
        result, _ = self._run_discovery(scratch)
        combined = self._combined(result)
        self.assertNotEqual(
            0,
            result.returncode,
            "discovery passed over an inventory source whose environment declares no "
            "pipeline configuration, so that environment is gated by nothing and "
            f"converged under a credential named nowhere: {combined[-800:]!r}",
        )
        self.assertIn(
            "bravo",
            combined,
            "discovery refused without naming the environment that was wrong: "
            f"{combined[-400:]!r}",
        )

    def test_discovery_fails_on_an_environment_with_no_inventory_source(self) -> None:
        """SPECIFIED -- the same scenario's other side: "an environment
        declaring a pipeline configuration but carrying no host-configuration
        inventory source". An environment that can be provisioned but not
        converged is one whose host configuration nothing applies."""
        scratch = self._scratch()
        self._convergeable(scratch, ("alpha",))
        self._write_tree(
            scratch,
            {
                "bravo": self._declaration_for(
                    "HCLOUD_TOKEN_BRAVO", "bravo-environment", gate=False
                )
            },
        )
        result, _ = self._run_discovery(scratch)
        combined = self._combined(result)
        self.assertNotEqual(
            0,
            result.returncode,
            "discovery converged the environments it could resolve and passed over an "
            "environment with no inventory source, which is the state nothing in a "
            f"provisioning run reports: {combined[-800:]!r}",
        )
        self.assertIn(
            "bravo",
            combined,
            f"discovery refused without naming the environment: {combined[-400:]!r}",
        )

    def test_discovery_fails_on_an_environment_with_no_variables_of_its_own(
        self,
    ) -> None:
        """SPECIFIED -- iac-host-configuration's scenario "An environment that
        can be provisioned but not converged is reported": "no inventory source
        OR no variables file of its own" (tasks.md 3.2 makes this one of
        discovery's refusals)."""
        scratch = self._scratch()
        self._convergeable(scratch, ("alpha",))
        self._write_tree(
            scratch,
            {
                "bravo": self._declaration_for(
                    "HCLOUD_TOKEN_BRAVO", "bravo-environment", gate=False
                )
            },
        )
        self._write_ansible_side(scratch, {"bravo": (True, False)})
        result, _ = self._run_discovery(scratch)
        combined = self._combined(result)
        self.assertNotEqual(
            0,
            result.returncode,
            "discovery accepted an environment carrying no `group_vars` file of its "
            "own, so a converge of it would run with none of its own variables: "
            f"{combined[-800:]!r}",
        )
        self.assertIn(
            "bravo",
            combined,
            f"discovery refused without naming the environment: {combined[-400:]!r}",
        )

    def test_discovery_fails_on_a_declaration_missing_a_field(self) -> None:
        """SPECIFIED -- the MODIFIED requirement's "An environment directory
        whose declaration is absent, unparseable, or missing either required
        field SHALL fail the workflow with a message naming the directory and
        the missing field"."""
        scratch = self._scratch()
        self._convergeable(scratch, ("alpha", "bravo"))
        reduced = self._without_field(
            self._declaration_for("HCLOUD_TOKEN_BRAVO", "bravo-environment", gate=False),
            ("secret", "token"),
        )
        self._write_tree(scratch, {"bravo": reduced})
        result, _ = self._run_discovery(scratch)
        combined = self._combined(result)
        self.assertNotEqual(
            0,
            result.returncode,
            "discovery accepted a declaration naming no read-only secret, so the "
            "converge job would resolve `secrets[...]` against an empty name and hold "
            f"no credential at all: {combined[-800:]!r}",
        )
        self.assertIn(
            "bravo",
            combined,
            f"discovery refused without naming the directory: {combined[-400:]!r}",
        )

    def test_discovery_fails_when_it_finds_no_environment(self) -> None:
        """SPECIFIED -- scenario "Discovery finding no environment fails rather
        than reporting success": "the workflow SHALL fail with a message
        identifying discovery as the cause, and SHALL NOT allow a dependent job
        to be skipped and reported as successful"."""
        scratch = self._scratch()
        (scratch / "ansible" / "inventory" / "group_vars").mkdir(parents=True)
        (scratch / "terraform" / "environments").mkdir(parents=True)
        result, _ = self._run_discovery(scratch)
        combined = self._combined(result)
        self.assertNotEqual(
            0,
            result.returncode,
            "discovery concluded successfully over a tree holding no inventory source, "
            "so the converge job is skipped on an empty matrix and the run reports "
            f"green having converged nothing: {combined[-800:]!r}",
        )
        self.assertRegex(
            combined.lower(),
            r"environment|discover|inventory",
            "discovery refused the empty tree without naming discovery, the inventory "
            f"sources or the environments as the cause: {combined[-400:]!r}",
        )

    def test_a_dispatched_environment_discovery_did_not_find_is_refused(self) -> None:
        """SPECIFIED -- scenario "A run is requested for an environment that
        does not exist": "the run SHALL fail naming the environments that were
        found, rather than converging none and reporting success"."""
        scratch = self._scratch()
        self._convergeable(scratch, ("alpha", "bravo"))
        result, _ = self._run_discovery(scratch, dispatched="charlie")
        combined = self._combined(result)
        self.assertNotEqual(
            0,
            result.returncode,
            "a converge dispatched against `charlie`, which discovery did not find, "
            "concluded successfully -- which on an empty matrix converges nothing and "
            f"reports green: {combined[-800:]!r}",
        )
        for found in ("alpha", "bravo"):
            self.assertIn(
                found,
                combined,
                "the refusal does not name the environments that WERE found, which is "
                "what tells an operator whether they misspelled one or are looking at "
                f"a tree that does not carry it: {combined[-400:]!r}",
            )

    def test_a_dispatched_environment_discovery_found_is_the_only_one_selected(
        self,
    ) -> None:
        """DERIVED -- no scenario states it; it is the converse the refusal
        above needs. A body refusing every non-empty input would satisfy that
        refusal while making a dispatched run impossible."""
        scratch = self._scratch()
        self._convergeable(scratch, ("alpha", "bravo"))
        result, outputs = self._run_discovery(scratch, dispatched="alpha")
        combined = self._combined(result)
        self.assertEqual(
            0,
            result.returncode,
            "a converge dispatched against `alpha`, which discovery did find, was "
            f"refused: {combined[-800:]!r}",
        )
        emitted = outputs.read_text(encoding="utf-8")
        self.assertIn(
            "alpha",
            emitted,
            f"discovery emitted no matrix naming `alpha`: {emitted!r}",
        )
        self.assertNotIn(
            "bravo",
            emitted,
            "a run dispatched against one environment emitted another as well, so a "
            f"by-hand converge of one host converges two: {emitted!r}",
        )

    def test_an_empty_dispatch_input_selects_every_environment(self) -> None:
        """DERIVED -- tasks.md 3.2: "an ABSENT or EMPTY input selects every
        discovered environment and is not refused ... Every `push` supplies an
        empty one, so conflating empty with unresolvable would fail discovery on
        every merge". This is the one place that distinction is load-bearing
        rather than stylistic, and a merge is the trigger the whole requirement
        rests on."""
        scratch = self._scratch()
        self._convergeable(scratch, ("alpha", "bravo"))
        result, outputs = self._run_discovery(scratch)
        combined = self._combined(result)
        self.assertEqual(
            0,
            result.returncode,
            "discovery refused a run supplying an empty environment input, which is "
            f"what every merge supplies: {combined[-800:]!r}",
        )
        emitted = outputs.read_text(encoding="utf-8")
        for name in ("alpha", "bravo"):
            self.assertIn(
                name,
                emitted,
                f"a run supplying no environment emitted no row for `{name}`, so a "
                f"merge converges fewer hosts than the repository carries: {emitted!r}",
            )


# --------------------------------------------------------------------------
# ADDED BY THE IMPLEMENTING AUTHOR, NOT BY THE AUTHOR OF THIS FILE.
#
# Everything above was derived from the delta specifications before any
# implementation existed. The two classes below were not: they are regression
# guards on a defect the code-review gate found, recorded here rather than in a
# commit message because the defect is one no scenario describes and one that
# would recur silently.
#
# WHAT WAS WRONG. The converge job's preflight was written to prove that an
# environment's Vault password decrypts its variables "before any task acts on
# the host", which the ADDED requirement obliges in those words. It ran
# `ansible-inventory --list --vault-id ...` and read an exit status of 0 as
# proof. Under the pinned `ansible-core` 2.21.3 that proves nothing: `--list`
# serialises with the `inventory_legacy` profile, which PRESERVES a vaulted
# value as `{"__ansible_vault": "<ciphertext>"}`. Verified against 2.21.3 -- a
# wrong `--vault-id` exits 0, with output byte-identical to the right one's.
#
# WHY THE SUITE DID NOT CATCH IT. The derived test locates the preflight by
# `ansible-inventory` plus a vault argument and asserts its POSITION relative to
# the play. That is the right assertion for the scenario it traces to, and it
# stayed green throughout -- deleting the line that does the proving would leave
# it green still. These two close that, and the second is what keeps the first
# honest as the tree changes.
# --------------------------------------------------------------------------


# `ansible` the ad-hoc command, which is not `ansible-playbook`, not
# `ansible-inventory`, not `ansible-galaxy`, not `$HOME/.ansible/`, not
# `ansible.cfg` and not `ansible.builtin.*`. `\b` is too loose for the last
# three, because `.` is a non-word character on both sides of it; the character
# classes below exclude a preceding path separator or dot and a following
# hyphen, dot or word character.
ANSIBLE_ADHOC = re.compile(r"(?<![\w./-])ansible(?![-\w.])")
HOSTVARS = re.compile(r"\bhostvars\b")

# THE SPELLING THAT FORCES A VAULTED VALUE TO DECRYPT, pinned deliberately.
#
# No static check can decide whether a Jinja expression forces decryption, so
# this pins the one spelling established by experiment against the pinned
# `ansible-core` 2.21.3, with a wrong `--vault-id`:
#
#     hostvars[inventory_hostname] | to_json | length      rc 2  <- forces
#     hostvars[inventory_hostname] | length                rc 0
#     hostvars | length                                    rc 0
#     hostvars[inventory_hostname].keys() | list | length  rc 0
#
# `| length` on the dict counts keys and templates no value, so it never
# touches a vaulted one. Dropping `| to_json` is a three-character edit that
# reads as a simplification -- "why serialise it just to take a length?" -- and
# it restores exactly the defect this guard exists to prevent, with every other
# predicate here still satisfied.
#
# So a legitimate switch to some other forcing filter SHALL go red. That is the
# point rather than a cost: whether the replacement forces decryption is a
# question only the wrong-password experiment answers, and going red is what
# makes someone re-run it instead of reading the code and concluding.
TO_JSON = re.compile(r"\bto_(?:nice_)?json\b")

VAULT_MARKER = "$ANSIBLE_VAULT"
# Where a vaulted value may live for the preflight to reach it. `hostvars` for a
# host carries INVENTORY variables, so these are the two directories Ansible
# resolves inventory variables from.
VAULT_PERMITTED_PREFIXES = (
    "ansible/inventory/group_vars/",
    "ansible/inventory/host_vars/",
)


class TestTheVaultProofIsTheCommandThatProvesIt(
    WorkflowLocatorMixin, unittest.TestCase
):
    """Regression guard, not a derived test -- see the block above.

    The requirement says the converge job SHALL establish that the environment's
    secrets decrypt before any task acts on the host. `ansible-inventory --list`
    does not establish it under the pinned `ansible-core`; templating a host's
    variables does. This asserts the command that does the proving is present
    and runs before the play, so that removing it is a red run rather than a
    silent return to the state the review found.
    """

    def test_a_templating_step_proves_the_vault_secret_before_the_play(self) -> None:
        name, job = self.converge_job()
        proving = []
        for index, step in enumerate(job.get("steps") or []):
            # EVERY PREDICATE ON ONE COMMAND, not merely somewhere in the step.
            # Continuations are joined first, because the real invocation spans
            # three lines and `invocation_lines` is line-based: matched over the
            # step, the vault argument would be supplied by the
            # `ansible-inventory` call sitting beside this one, and an ad-hoc
            # `ansible` carrying no vault argument at all would satisfy the
            # check.
            body = uncommented(str(step.get("run") or ""))
            joined = re.sub(r"\\\n\s*", " ", body)
            for line in invocation_lines(joined, ANSIBLE_ADHOC):
                # Four predicates, each closing a different escape: it is the
                # ad-hoc command; it carries the vault secret; it reads THIS
                # host's variables rather than some constant; and it renders
                # them, which is the only part that forces a decrypt.
                if not VAULT_ARGUMENT.search(line):
                    continue
                if not HOSTVARS.search(line):
                    continue
                if not TO_JSON.search(line):
                    continue
                proving.append(index)
                break
        self.assertTrue(
            proving,
            f"the converge job `{name}` runs no single ad-hoc `ansible` command that "
            "carries a vault argument, reads `hostvars` AND renders them through "
            "`to_json`, so nothing in it forces this environment's vaulted values to "
            "decrypt. `| length` alone counts keys and templates no value. "
            "`ansible-inventory "
            "--list` does NOT: under the pinned ansible-core it serialises a vaulted "
            "value as ciphertext and exits 0 on a wrong password. Without this, a "
            "stale vault password is discovered four roles into the play, on a host "
            "that is already changed",
        )
        play = [index for index, _, _ in invoking_steps(job, ANSIBLE_PLAYBOOK)]
        self.assertTrue(play, f"the converge job `{name}` runs no play")
        self.assertLess(
            min(proving),
            min(play),
            f"the converge job `{name}` proves its vault secret only after the play "
            "has started, which is the partially-converged host this check exists to "
            "prevent",
        )


class TestEveryVaultedValueIsWhereThePreflightReachesIt(unittest.TestCase):
    """Regression guard, not a derived test -- see the block above.

    The proof above templates `hostvars[inventory_hostname]`, which carries
    INVENTORY variables. It does not carry a role's `defaults/main.yml` or
    `vars/main.yml`, a `vars_files:`, an `include_vars` result, or a
    playbook-adjacent `group_vars/`. So the first vaulted value that lands in any
    of those reopens exactly the hole the review closed -- silently, with the
    preflight still green and still read as proof.

    This turns the preflight's coverage from a property of today's tree into an
    invariant. It is a static read of committed files at repository scope, which
    is what this suite is for.
    """

    def _candidates(self):
        # Walked from the REPOSITORY root and filtered, not walked from
        # `ansible/`. `walked_files` builds its prune keys relative to the root
        # it is given, so under `walked_files(ANSIBLE_DIR)` the entry
        # `ansible/roles/geerlingguy.docker` becomes `roles/geerlingguy.docker`
        # and never matches -- and a developer who has run `ansible-galaxy role
        # install` would then have this sweep read installed content, against a
        # docstring promising a static read of committed files.
        for path in walked_files():
            relative = path.relative_to(ROOT).as_posix()
            if not relative.startswith("ansible/"):
                continue
            # A Molecule scenario is a fixture for a role's own tests. It is
            # never resolved by the host-baseline play and never reaches a
            # converge, so a vaulted value in one says nothing about this.
            if "/molecule/" in relative:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if VAULT_MARKER in text:
                yield relative

    def test_every_vaulted_value_lives_where_inventory_variables_live(self) -> None:
        offenders = sorted(
            relative
            for relative in self._candidates()
            if not relative.startswith(VAULT_PERMITTED_PREFIXES)
        )
        self.assertEqual(
            [],
            offenders,
            "these files carry a Vault-encrypted value somewhere the converge job's "
            "preflight cannot reach: it templates `hostvars[inventory_hostname]`, "
            "which carries inventory variables and not a role's defaults, a "
            "`vars_files:`, an `include_vars` result or a playbook-adjacent "
            "`group_vars/`. A value here would decrypt for the first time partway "
            f"through the play, on a host already changed: {offenders}",
        )

    def test_the_tree_carries_a_vaulted_value_for_this_to_have_read(self) -> None:
        """The converse. With no vaulted value anywhere, the sweep above passes
        having read nothing -- and so does the preflight it protects, since there
        would be no secret for a wrong password to fail on."""
        self.assertTrue(
            sorted(self._candidates()),
            "no committed file under ansible/ carries a Vault-encrypted value outside "
            "a Molecule scenario, so the sweep above compared nothing",
        )

if __name__ == "__main__":  # pragma: no cover - parity with the modules beside it
    unittest.main()
