"""Static-assertion tests for a platform deploy that names no stack.

Derived from the delta specs of the OpenSpec change
`deploy-the-platform-stack-per-environment`, before any implementation of that
change existed -- from that change's delta specifications at commit `3d96cb0`,
which is the commit holding the approved plan. The path those deltas sit at is
not written here: a change's artifacts move when it is archived, and this
repository's citation convention is to name the change and the artifact in prose
instead.

The deltas span two capabilities, `iac-platform-deploy-pipeline` and
`iac-cicd-pipeline`; each section below names the requirement it traces to.
Every assertion is annotated SPECIFIED (it traces to SHALL text or to a scenario
in a delta spec) or DERIVED (it traces to that change's `design.md` or
`tasks.md` rather than to a scenario). See that change's `test-plan.md` for the
scenario-to-test mapping, the baseline, the scenarios deliberately left
uncovered, the obsolete-test entries this pass is forbidden to act on itself,
and the project questions this file took an assumption on.

Why this is a new module rather than a section of an existing one
-----------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. Four assertions across three existing modules rest
on a proposition this change retires -- that `platform-deploy.yml` declares
exactly one literal deployment Environment -- and re-pointing them is the
implementing author's task (that change's tasks.md 3.1, 3.1a and 3.1b). They are
recorded in that change's `test-plan.md` obsolete list rather than touched here.
Nothing in this file edits, deletes or disables an existing test.

`TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in
`test_ci_configuration.py` reads every module in this directory, so this file is
held to the no-network, no-credential, no-container, no-Terraform constraint by
that class. It is written to satisfy it: standard library, `yaml`, the helpers of
the modules beside it, and `bash` as the only spawned command.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or one class, individually selectable:
    python3 -m unittest discover --start-directory .github/tests \\
        -k TestThePlatformDeployNamesNoStack

    # or one test:
    python3 -m unittest discover --start-directory .github/tests \\
        -k test_no_job_declares_a_literal_github_environment

Run from the repository root, and through `discover` in both forms: it is
discovery that puts `.github/tests` on `sys.path`, which is what makes the
sibling imports below resolve.

Which assertions here are red before the implementation, and which are guards
-----------------------------------------------------------------------------
Both kinds are present deliberately, and the distinction matters when reading a
run of this file:

- RED until the change lands -- every class reading the opt-in field
  (`TestEveryStackThatReceivesThePlatformStackDeclaresIt`), every class reading
  the restructured workflow (`TestThePlatformDeployNamesNoStack`,
  `TestEachDeployRowAttachesToTheEnvironmentItsStackDeclares`,
  `TestNoStacksDeployIsOrderedBehindAnother`,
  `TestEachStacksDeployIsSerialisedOnItsOwn`,
  `TestTheSecretSetIsEstablishedBeforeAnythingIsWritten`), and
  `TestPlatformDeployDiscoveryFailsClosed`, which locates a discovery step the
  workflow does not yet have.
- GREEN from the moment they are written --
  `TestOneStacksKeyDoesNotReachAnotherStacksHost`,
  `TestTheRenderedEnvIsNeverCommitted` and
  `TestTheDeployReachesItsHostOverTheTailnetAsTheDeployAccount`. Their subject
  is what the committed tree already says and what this change deliberately does
  not alter -- the two hosts' separate authorised keys, the uncommitted `.env`,
  the tailnet join before SSH, the confinement of the deploy credential. A pass
  is the expected result and establishes that what is committed already
  satisfies the generalised requirement; it is NOT an alarm of the "passed
  before any implementation existed" kind, because the target is not absent.
  What they are for is the second stack: each is written over the discovered
  set, so it acquires a subject the day a second stack opts in.
- PART GREEN, PART RED -- `TestTheDiffIsPublishedOnceBeforeAnyGate`. The
  committed workflow already publishes the diff from one credential-free job;
  what is red is the dependency between that job and the deploy ROWS, there
  being no rows yet.
- VACUOUS until the change lands --
  `TestAStackOptingInAuthorisesTheDeployOnItsHost` compares two committed files
  over the set of stacks that opt in, and no stack opts in today. It is written
  to say so rather than to pass quietly: its guard is red until a stack opts in.

`TestTheseReadsDiscriminate` at the end exists because every read in this file
is a static read of a committed file: a predicate that reported no offence
whatever it was given would satisfy every guard above, and would do so most
convincingly on the day the sweep was finished. It runs each predicate over
material this file supplies, carrying the defect that predicate names.

What no assertion here establishes
----------------------------------
Nothing in this file reads a repository setting. Whether a GitHub Environment
exists, whether it requires a reviewer, which secrets it holds and what value
each holds are settings rather than repository content, and this suite makes no
network call. So "a reviewed stack's deploy pauses" and "two stacks render two
different sets of values" are asserted here only in the form a committed file
can carry: that the deploy attaches to the Environment its own stack declares,
that the secrets are reached by fixed names resolved against that Environment,
and that nothing in workflow text distinguishes one stack from another. A green
run establishes that the committed files are SHAPED so those settings can be
applied safely, never that they were.
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
    PLATFORM_DEPLOY,
    ROOT,
    jobs,
    load_yaml,
    read_text,
    require_external_tools,
    secrets_referenced_by,
    step_label,
    step_text,
    steps,
    uncommented,
)
from test_environment_agnostic_pipeline import (
    ACTIONS_EXPRESSION,
    DeclarationTreeFixtureMixin,
    declared_environment,
    environment_declarations,
    environment_directories,
    invocation_lines,
    matrix_source_jobs,
    needs_of,
    run_snippet,
)

# --------------------------------------------------------------------------
# Identifiers this file names, and why each is a constraint of the test layer
# rather than a property the specification states.
# --------------------------------------------------------------------------

GROUP_VARS_DIR = ROOT / "ansible" / "inventory" / "group_vars"
ENV_EXAMPLE = ROOT / "platform" / ".env.example"
GITIGNORE = ROOT / ".gitignore"

# How the opt-in field is identified. Resolved by HINT rather than by its
# spelling, for the reason the sibling module resolves the other four fields by
# hint: the MODIFIED requirement fixes what the declaration must DECLARE --
# "whether the shared platform stack is deployed to it" -- and leaves the field
# name to the implementing author (that change's tasks.md 1.1). A test keyed on
# a spelling would fail a legitimate choice and would be repaired by editing
# this file, which is the one repair this suite must not need.
#
# The hint is `platform`, which no other field in a committed declaration
# carries. The requirement additionally obliges the field to name what happens
# when it is TRUE, so a declaration spelling it `platform_excluded` would be
# read by this hint and would then be read BACKWARDS -- which is why
# `TestEveryStackThatReceivesThePlatformStackDeclaresIt` asserts the polarity
# separately rather than trusting the value.
PLATFORM_KEY_HINT = "platform"

# The spelling a FIXTURE declaration uses when the committed declarations carry
# no such field yet -- which is their state until this change lands, and is what
# would otherwise leave the discovery fixtures unable to express an opt-in at
# all. DERIVED (that change's tasks.md 1.1). Used only where the committed tree
# supplies no name to copy; once a stack declares one, the fixtures follow it.
PLATFORM_KEY_FALLBACK = "deploys_platform"

# The application name a host's deploy-key authorisations enumerate. DERIVED
# from the committed tree: it is the name `ansible/inventory/group_vars/*.yml`
# already lists in `deploy_apps`, and the name of the `platform/` directory
# whose stack definition this deploy delivers. The requirement says "the
# platform application" and fixes no string.
PLATFORM_APPLICATION = "platform"

# The list a `group_vars` file enumerates a host's deploy-key authorisations in,
# and the keys naming each application and its key within it. DERIVED from the
# committed files for the same reason.
DEPLOY_APPS_FIELD = "deploy_apps"
APPLICATION_NAME_FIELD = "name"
APPLICATION_KEY_FIELD = "public_key"

# The two secrets that are not values rendered into `.env`: the one naming the
# stack's host and the one holding the key it authenticates with. The
# requirement names both as members of the set ("the secret naming that stack's
# host, the deploy key it authenticates with") and fixes neither spelling;
# these are DERIVED from the committed workflow, which already reads both, and
# are asserted to be referenced rather than assumed present.
DEPLOY_HOST_SECRET = "PLATFORM_DEPLOY_HOST"
DEPLOY_KEY_SECRET = "PLATFORM_DEPLOY_SSH_KEY"

# The one `.env` variable the requirement excludes from the set by name: "the
# tailnet bind address is derived at deploy time, is behind no secret, and is
# resolved after this obligation is discharged". Matched on the substring rather
# than on the whole variable, so the exclusion follows the committed
# `.env.example` rather than a spelling written here.
DERIVED_AT_DEPLOY_HINT = "BIND_ADDRESS"

# The restricted account the deploy authenticates as, provisioned by the
# host-configuration change. SPECIFIED -- the scenario names it: "the restricted
# `deploy` account".
DEPLOY_ACCOUNT = "deploy"

# `ssh` ITSELF, never a command whose name merely starts with it.
# `\b` after `ssh` matches inside `ssh-keyscan`, which the committed deploy
# runs against the host BEFORE it connects -- so a matcher stopping at `\b`
# reports the known-hosts step as an SSH connection, which it is not: it
# carries no `deploy@` and would fail the deploy-account assertion for a
# reason the requirement does not state. `ssh-keygen` and `ssh-add` are the
# same shape.
SSH = re.compile(r"(?<![\w./-])ssh(?![\w.-])")
TAILSCALE = re.compile(r"tailscale", re.IGNORECASE)
STEP_SUMMARY = re.compile(r"GITHUB_STEP_SUMMARY")
SECRETS_EXPRESSION = re.compile(r"\$\{\{\s*secrets\.")
MATRIX_REFERENCE = re.compile(r"\bmatrix\.")
DISPATCH_INPUT = re.compile(r"(?:inputs|event\.inputs)\.stack\b")
PRINTING = re.compile(r"(?<![\w-])(?:echo|printf|cat)\b")
INDIRECT_EXPANSION = re.compile(r"\$\{!")


def normalised(key: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


# --------------------------------------------------------------------------
# Reading the opt-in out of a stack's declaration
# --------------------------------------------------------------------------


def platform_opt_in(mapping: dict) -> tuple:
    """`(value, offence)` for one declaration's platform opt-in.

    `None` with no offence is the field being ABSENT, which the requirement
    gives a default for -- "defaults to **not** being deployed when absent" --
    and is therefore not an offence. A value that is not a boolean IS one: the
    requirement obliges discovery to refuse a value "that is neither `true` nor
    `false`, rather than treating anything unrecognised as one of them", and a
    field this suite coerced would report an opt-in the workflow refuses, or the
    reverse.
    """
    keys = [key for key in mapping if PLATFORM_KEY_HINT in normalised(key)]
    if len(keys) > 1:
        return None, (
            "more than one field names whether the shared platform stack is deployed "
            f"to this stack ({sorted(map(str, keys))}), so which one discovery reads is "
            "ambiguous"
        )
    if not keys:
        return None, None
    value = mapping[keys[0]]
    if not isinstance(value, bool):
        return None, (
            f"field {str(keys[0])!r} states whether the shared platform stack is "
            f"deployed to this stack but is {value!r}, which is not a boolean; "
            "discovery refuses a value that is neither true nor false rather than "
            "treating it as one of them"
        )
    return value, None


def platform_opt_ins(root: Path | None = None) -> dict:
    """Stack directory -> its declared opt-in, `None` where the field is absent
    or unreadable."""
    return {
        name: platform_opt_in(declaration.mapping)[0]
        for name, declaration in environment_declarations(root).items()
    }


def opt_in_offences(root: Path | None = None) -> list:
    """Every reason a committed declaration's opt-in field is not one discovery
    could read."""
    offences = []
    for name, declaration in sorted(environment_declarations(root).items()):
        _, offence = platform_opt_in(declaration.mapping)
        if offence:
            offences.append(f"{name}: {offence}")
    return offences


def opting_in(root: Path | None = None) -> list:
    """The stacks whose own declaration opts them in, sorted."""
    return sorted(name for name, value in platform_opt_ins(root).items() if value is True)


# --------------------------------------------------------------------------
# Reading a host's deploy-key authorisations out of its `group_vars` file
# --------------------------------------------------------------------------


class AnsibleTolerantLoader(yaml.SafeLoader):
    """`SafeLoader`, plus the two tags Ansible's own YAML carries.

    `ansible/inventory/group_vars/*.yml` carry `!vault` blocks, which
    `yaml.safe_load` refuses -- so a reader built on it would fail to parse the
    very files this module cross-checks, and the change's own design.md names
    that as the cost that lands on whoever writes this check.

    NAMED EXPLICITLY, never a catch-all, which is the whole of the rule this
    copies. `_AnsibleTolerantLoader` in `ansible/scripts/select_molecule_roles.py`
    is the established shape and its docstring states why: a multi-constructor
    over `!` maps every unknown tag to `None`, turning a document this reader
    has never seen into an EMPTY one rather than into a refusal. Here that would
    be worse than there -- `deploy_apps` read out of an empty document is an
    absent list, so the cross-check below would pass vacuously on the very pair
    it compares, failing open on the one guard this change adds.

    It is copied rather than imported because an import of a module outside this
    directory is not something this suite's own dependency audit admits:
    `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` allows the
    standard library, the pinned `yaml`, and a sibling of this directory, and
    `ansible/scripts/` is none of the three. The refusal is asserted here rather
    than inherited -- see `TestTheseReadsDiscriminate
    .test_an_unknown_tag_refuses_rather_than_yielding_an_empty_document`.
    """


for _tag in ("!vault", "!unsafe"):
    AnsibleTolerantLoader.add_constructor(
        _tag, lambda loader, node: loader.construct_scalar(node)
    )


class UnreadableGroupVars(AssertionError):
    """A `group_vars` file that cannot be parsed, refused rather than read as
    authorising nothing -- and rather than read as authorising everything."""


def group_variables(path: Path) -> dict:
    try:
        document = yaml.load(path.read_text(encoding="utf-8"), Loader=AnsibleTolerantLoader)
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as error:
        raise UnreadableGroupVars(
            f"{path.name}: cannot be parsed ({error}), so which applications this host "
            "authorises a deploy key for is unknown. Refused rather than read as "
            "authorising none"
        ) from error
    if document is None:
        return {}
    if not isinstance(document, dict):
        raise UnreadableGroupVars(
            f"{path.name}: is not a mapping, so it declares no host variables at all"
        )
    return document


def authorised_applications(root: Path | None = None) -> dict:
    """Ansible group -> the applications its `group_vars` file authorises a
    deploy key for.

    A group with no file of its own is ABSENT from this mapping, which the
    cross-check reports by name; that is not the same as a group whose file
    enumerates nothing, which is a host authorising no application.
    """
    base = (ROOT if root is None else root) / "ansible" / "inventory" / "group_vars"
    found: dict = {}
    if not base.is_dir():
        return found
    for path in sorted(base.glob("*.yml")):
        entries = group_variables(path).get(DEPLOY_APPS_FIELD) or []
        names = set()
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and entry.get(APPLICATION_NAME_FIELD):
                    names.add(str(entry[APPLICATION_NAME_FIELD]))
                elif isinstance(entry, str):
                    names.add(entry)
        found[path.stem] = names
    return found


def authorised_keys(root: Path | None = None) -> dict:
    """Ansible group -> the public half of the key its host authorises for the
    platform application, for the groups that authorise one."""
    base = (ROOT if root is None else root) / "ansible" / "inventory" / "group_vars"
    found: dict = {}
    if not base.is_dir():
        return found
    for path in sorted(base.glob("*.yml")):
        entries = group_variables(path).get(DEPLOY_APPS_FIELD) or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if (
                isinstance(entry, dict)
                and str(entry.get(APPLICATION_NAME_FIELD)) == PLATFORM_APPLICATION
                and entry.get(APPLICATION_KEY_FIELD)
            ):
                found[path.stem] = str(entry[APPLICATION_KEY_FIELD])
    return found


def deploy_authorisation_offences(opt_ins, groups, authorisations) -> list:
    """Why a stack's declaration and its host's `group_vars` file disagree, as
    messages naming BOTH files; empty where they agree.

    Takes all three sides as arguments rather than reading them, so the
    discriminator at the end of this file can hand it a disagreeing pair. Over
    the committed tree the two agree today -- because no stack opts in at all --
    and a predicate that could only ever return an empty list would pass that
    having read nothing.

    ONE-DIRECTIONAL, deliberately. A host that authorises the key while its
    stack's declaration does not opt in is the deliberate interval the change's
    design.md Decision 2 is built on, and is accepted here rather than reported.
    """
    offences = []
    for stack in sorted(opt_ins):
        if opt_ins.get(stack) is not True:
            continue
        group = groups.get(stack)
        if not group:
            offences.append(
                f"terraform/stacks/{stack}/pipeline.yml declares that the shared "
                "platform stack is deployed to this stack and names no Ansible group, "
                "so no group_vars file says whether its host authorises the deploy key"
            )
            continue
        authorised = authorisations.get(group)
        if authorised is None:
            offences.append(
                f"terraform/stacks/{stack}/pipeline.yml opts in to the platform deploy "
                f"and ansible/inventory/group_vars/{group}.yml does not exist, so the "
                "deploy would authenticate with a key nothing has told the host to "
                "accept"
            )
        elif PLATFORM_APPLICATION not in authorised:
            offences.append(
                f"terraform/stacks/{stack}/pipeline.yml opts in to the platform deploy "
                f"and ansible/inventory/group_vars/{group}.yml does not enumerate "
                f"`{PLATFORM_APPLICATION}` among `{DEPLOY_APPS_FIELD}` (it names "
                f"{sorted(authorised)}), so the deploy would fail authenticating after "
                "the tailnet join and after any approval"
            )
    return offences


# --------------------------------------------------------------------------
# Reading the secret set out of the committed `.env.example`
# --------------------------------------------------------------------------


def env_example_variables(path: Path | None = None) -> list:
    """Every variable the committed `.env.example` documents, in file order."""
    text = read_text(ENV_EXAMPLE if path is None else path)
    found: list = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name = line.split("=", 1)[0].strip()
        if name and name not in found:
            found.append(name)
    return found


def secret_backed_variables(path: Path | None = None) -> list:
    """The `.env` variables whose value comes from a secret: every documented
    variable except the one the deploy derives at deploy time."""
    return [
        name for name in env_example_variables(path) if DERIVED_AT_DEPLOY_HINT not in name.upper()
    ]


def rendered_secret_resolution(referenced, variables) -> tuple:
    """`(variable -> secret name, offences)`.

    Each `.env` value that comes from a secret is matched to the secret the
    workflow actually reads for it, by suffix, rather than by a naming rule
    written here: the requirement obliges the secrets to be "reached by their own
    fixed names" and fixes no prefix. A variable no referenced secret ends with
    is an offence in its own right -- the render would interpolate it from
    nothing.
    """
    resolved = {}
    offences = []
    for variable in variables:
        candidates = sorted(name for name in referenced if name.upper().endswith(variable.upper()))
        if not candidates:
            offences.append(
                f"`{variable}` is documented in platform/.env.example and no secret "
                "this workflow reads has a name ending with it, so the rendered .env "
                "would carry an empty assignment for it and nothing would say so"
            )
        elif len(candidates) > 1:
            offences.append(
                f"`{variable}` matches more than one secret this workflow reads "
                f"({candidates}), so which one is rendered into .env is not readable"
            )
        else:
            resolved[variable] = candidates[0]
    return resolved, offences


# --------------------------------------------------------------------------
# Reading the workflow
# --------------------------------------------------------------------------


def summary_writing_jobs(workflow: dict) -> dict:
    """Jobs with a step that writes to the run's job summary.

    Matched as TEXT rather than through `invocation_lines`, and the difference is
    not pedantic: the summary is written by REDIRECTING into it, and a reader
    that skips a match inside an unclosed quote skips that redirect, finding no
    publishing job in a workflow that has one.
    """
    return {
        name: job
        for name, job in jobs(workflow).items()
        if any(
            STEP_SUMMARY.search(uncommented(str(step.get("run") or "")))
            for step in (job.get("steps") or [])
        )
    }


def matrix_jobs(workflow: dict) -> dict:
    """Jobs whose matrix is built from another job's outputs -- the deploy rows,
    identified by the property the requirement states about them rather than by a
    job key this file would have to guess."""
    return {
        name: job for name, job in jobs(workflow).items() if matrix_source_jobs(workflow, job)
    }


def gated_jobs(workflow: dict) -> dict:
    return {name: job for name, job in jobs(workflow).items() if job.get("environment") is not None}


def gate_offences(workflow: dict, declared_environments) -> list:
    """Why the deploy's gate is not the Environment each stack's own declaration
    names; empty where it is.

    Takes the declared Environments as an argument so the discriminator can hand
    it a workflow and a set of declarations that disagree. What this replaces is
    an equality against one literal, which this change retires: the hazard that
    equality held is not retired with it -- GitHub CREATES an Environment a
    workflow names, with no protection rules -- so what is asserted instead is
    that every Environment the workflow can attach to is resolved from discovery,
    per matrix row, rather than written anywhere in workflow text.
    """
    offences = []
    gated = gated_jobs(workflow)
    if not gated:
        return [
            "no job in this workflow declares an `environment:`, so no deploy attaches "
            "to any GitHub Environment -- the protection rules that gate a stack's "
            "apply gate nothing here, and the deploy key is confined to nothing"
        ]
    for name, job in sorted(gated.items()):
        value = declared_environment(job) or ""
        if not ACTIONS_EXPRESSION.search(value):
            owners = sorted(
                stack
                for stack, environment in (declared_environments or {}).items()
                if environment == value
            )
            offences.append(
                f"{name}: declares the literal GitHub Environment {value!r} (declared "
                f"by {owners or 'no stack'}). The Environment a deploy attaches to is "
                "resolved per matrix row from the stack's own declaration; a literal is "
                "the workflow naming a stack's Environment in workflow text, and one no "
                "stack declares is created unprotected rather than refused"
            )
            continue
        if not MATRIX_REFERENCE.search(value):
            offences.append(
                f"{name}: declares the Environment `{value}`, which is an expression "
                "reading no matrix value -- so every row of this deploy attaches to one "
                "Environment rather than to its own stack's"
            )
            continue
        sources = matrix_source_jobs(workflow, job)
        if not sources:
            offences.append(
                f"{name}: resolves its Environment from a matrix that is not built from "
                "another job's outputs, so the set of stacks it deploys to is written "
                "in workflow text rather than discovered from the committed "
                "declarations"
            )
            continue
        for source in sources:
            source_job = jobs(workflow).get(source) or {}
            if source_job.get("environment") is not None:
                offences.append(
                    f"{name}: takes its matrix from `{source}`, which itself declares an "
                    "`environment:` -- so discovery runs inside a gate and every stack's "
                    "deploy waits on one stack's Environment"
                )
    return offences


def ordering_offences(workflow: dict) -> list:
    """Why one stack's deploy could be held back by another's; empty where none
    can be.

    The three mechanisms the change's design.md Decision 6 names, none of which
    states a dependency a reader could find by looking for `needs:`: `fail-fast`
    at its default cancels every sibling row when one fails, `max-parallel: 1`
    sequences the rows in an order nobody chose, and a `needs:` between deploy
    jobs states it outright.
    """
    offences = []
    rows = matrix_jobs(workflow)
    if not rows:
        return [
            "no job in this workflow builds its matrix from another job's outputs, so "
            "there are no per-stack deploy rows to be ordered -- and the set of stacks "
            "deployed to is not discovered at all"
        ]
    for name, job in sorted(rows.items()):
        strategy = job.get("strategy") or {}
        if strategy.get("fail-fast") is not False:
            offences.append(
                f"{name}: does not declare `fail-fast: false` (it declares "
                f"{strategy.get('fail-fast')!r}). At its default, one stack's failed "
                "deploy cancels every other stack's row -- withholding a correct change "
                "from one stack because another broke"
            )
        if "max-parallel" in strategy:
            offences.append(
                f"{name}: declares `max-parallel: {strategy['max-parallel']!r}`, which "
                "runs the stacks' deploys one at a time in an order nobody chose -- "
                "promotion ordering imposed by the workflow rather than exercised at an "
                "approver's gate"
            )
        for other in needs_of(job):
            if other in rows and other != name:
                offences.append(
                    f"{name}: depends on `{other}`, which is itself a per-stack deploy "
                    "row, so one stack's deploy is sequenced behind another's"
                )
    return offences


def serialisation_offences(workflow: dict) -> list:
    """Why two merges racing over one host, or one stack's queue holding
    another's, is not what this workflow's concurrency does."""
    offences = []
    if workflow.get("concurrency") is not None:
        offences.append(
            "the workflow declares a workflow-level `concurrency` group "
            f"({workflow['concurrency']!r}). A workflow-level group cannot read a "
            "matrix, so it is one group across every stack: one stack's pending "
            "approval would hold another stack's deploy in a queue, which is the "
            "promotion ordering no dependency edge would show"
        )
    rows = matrix_jobs(workflow)
    if not rows:
        offences.append(
            "no job builds its matrix from another job's outputs, so no per-stack "
            "deploy row exists to be serialised"
        )
    for name, job in sorted(rows.items()):
        concurrency = job.get("concurrency")
        if concurrency is None:
            offences.append(
                f"{name}: declares no `concurrency` group, so two merges in quick "
                "succession run concurrently against one host"
            )
            continue
        group = concurrency.get("group") if isinstance(concurrency, dict) else concurrency
        group = "" if group is None else str(group)
        if not MATRIX_REFERENCE.search(group):
            offences.append(
                f"{name}: is serialised on the group `{group}`, which names no matrix "
                "value -- so it is one group across every stack, and two stacks whose "
                "deploys contend for nothing queue behind each other"
            )
        if isinstance(concurrency, dict) and concurrency.get("cancel-in-progress"):
            offences.append(
                f"{name}: declares `cancel-in-progress: true`, so the second of two "
                "merges cancels the first against the same host rather than queueing "
                "behind it"
            )
    return offences


def confinement_offences(workflow: dict, confined) -> list:
    """Every job that reads a confined secret without attaching to a GitHub
    Environment."""
    offences = []
    for name, job in sorted(jobs(workflow).items()):
        if job.get("environment") is not None:
            continue
        read = sorted(secrets_referenced_by(job) & set(confined))
        if read:
            offences.append(
                f"{name}: declares no `environment:` and reads {read}. A job attached to "
                "no Environment can read no stack's deploy credential -- and one that "
                "could would read it before any approval gate"
            )
    return offences


def connecting_jobs(workflow: dict) -> dict:
    """Jobs with a step that opens an SSH connection."""
    return {
        name: job
        for name, job in jobs(workflow).items()
        if any(invocation_lines(step.get("run", ""), SSH) for step in (job.get("steps") or []))
    }


def tailnet_ordering_offences(workflow: dict) -> list:
    """Why a job would reach its host other than over the private tailnet."""
    connecting = connecting_jobs(workflow)
    if not connecting:
        return [
            "no job in this workflow connects over SSH, so nothing here reads the "
            "tailnet ordering -- and nothing delivers the stack to a host"
        ]
    offences = []
    for name, job in sorted(connecting.items()):
        job_steps = job.get("steps") or []
        joins = [
            index
            for index, step in enumerate(job_steps)
            if TAILSCALE.search(uncommented(step_text(step)))
        ]
        connects = [
            index
            for index, step in enumerate(job_steps)
            if invocation_lines(step.get("run", ""), SSH)
        ]
        if not joins:
            offences.append(
                f"{name}: connects over SSH at step {connects[0]} and joins no tailnet, "
                "so it reaches the host over a publicly-routable address or not at all"
            )
        elif joins[0] > connects[0]:
            offences.append(
                f"{name}: its first SSH attempt is step {connects[0]} and it joins the "
                f"tailnet at step {joins[0]}, so the connection is attempted before the "
                "private path to the host exists"
            )
    return offences


def deploy_account_offences(workflow: dict) -> list:
    """Every SSH invocation that authenticates as somebody other than the
    provisioned deploy account."""
    connecting = connecting_jobs(workflow)
    if not connecting:
        return [
            "no job in this workflow connects over SSH, so which account it "
            "authenticates as is asserted over nothing"
        ]
    offences = []
    for name, job in sorted(connecting.items()):
        for index, step in enumerate(job.get("steps") or []):
            for line in invocation_lines(step.get("run", ""), SSH):
                if not re.search(rf"(?<![\w.-]){re.escape(DEPLOY_ACCOUNT)}@", line):
                    offences.append(
                        f"{step_label(name, index, step)}: {line!r} does not authenticate "
                        f"as the restricted `{DEPLOY_ACCOUNT}` account"
                    )
    return offences


def shared_key_offences(keys) -> list:
    """Every public half more than one host authorises for the platform
    application."""
    if not keys:
        return [
            "no group_vars file enumerates a public half for the platform application, "
            "so this comparison reads nothing"
        ]
    shared: dict = {}
    for group, key in sorted(keys.items()):
        shared.setdefault(key, []).append(group)
    return sorted(
        f"{groups} authorise one key ending {key[-24:]!r}, so one stack's compromised "
        "key deploys to another stack's host"
        for key, groups in shared.items()
        if len(groups) > 1
    )


def committed_env_files(root: Path | None = None) -> list:
    """Every rendered environment file committed beside the stack definition.

    Takes `root` so the read is exercisable against a fixture tree: over the real
    repository this list is empty and stays empty, which is exactly the state a
    finder that reported nothing at all would be indistinguishable from.
    """
    base = ROOT if root is None else root
    directory = base / "platform"
    if not directory.is_dir():
        return []
    return sorted(
        str(path.relative_to(base))
        for path in directory.rglob("*")
        if path.is_file() and path.name.startswith(".env") and path.name != ".env.example"
    )


def diff_offences(workflow: dict) -> list:
    """Why the reviewer would not see the exact diff, credential-free, before any
    gate is presented."""
    offences = []
    publishing = summary_writing_jobs(workflow)
    if not publishing:
        return [
            "no job writes to `$GITHUB_STEP_SUMMARY`, so nothing publishes the diff a "
            "required reviewer is asked to approve"
        ]
    if len(publishing) > 1:
        offences.append(
            f"{sorted(publishing)} all write to the run summary. One job serves every "
            "stack -- the deployed content is the same for each -- so a job per stack "
            "would publish the same diff several times and multiply the jobs that run "
            "before the gate"
        )
    rows = matrix_jobs(workflow)
    for name, job in sorted(publishing.items()):
        if job.get("environment") is not None:
            offences.append(
                f"{name}: publishes the diff and declares "
                f"`environment: {declared_environment(job)}`, so the summary a reviewer "
                "reads is written by a job that has already passed the gate -- and by "
                "one holding a deploy credential"
            )
        if secrets_referenced_by(job):
            offences.append(
                f"{name}: publishes the diff and reads "
                f"{sorted(secrets_referenced_by(job))}, so the credential-free job this "
                "requirement describes is not credential-free"
            )
        if name in rows:
            offences.append(
                f"{name}: publishes the diff from a per-stack matrix row, so the same "
                "diff is published once per stack"
            )
        for row_name, row in sorted(rows.items()):
            if name not in needs_of(row):
                offences.append(
                    f"{row_name}: does not depend on `{name}`, so its approval gate can "
                    "be reached before the diff has been written"
                )
    return offences


def secret_set_offences(job: dict, required) -> list:
    """Why the whole of a stack's secret set is not established before anything is
    joined, rendered or connected to.

    Takes the job and the set of names rather than reading either, so the
    discriminator can hand it a job whose check runs too late, or covers only
    part of the set.
    """
    if not required:
        return [
            "no secret names were resolved for this deploy, so this ordering check "
            "would pass having read nothing"
        ]
    offences = []
    job_steps = job.get("steps") or []
    establishing = [
        index for index, step in enumerate(job_steps) if set(required) <= secrets_referenced_by(step)
    ]
    if not establishing:
        covered = [sorted(set(required) & secrets_referenced_by(step)) for step in job_steps]
        best = max(covered, key=len) if covered else []
        missing = sorted(set(required) - set(best))
        return [
            "no single step of this deploy reads every secret the deploy consumes, so "
            "nothing establishes that they all resolved to a value before the deploy "
            f"acts. The widest step reads {best}; it does not read {missing}. An "
            "undefined GitHub secret resolves to an empty string rather than to an "
            "error, and an empty value rendered into .env can start a service the "
            "deploy's wait for health cannot distinguish from a correct one"
        ]
    first = establishing[0]
    acting: dict = {}
    for index, step in enumerate(job_steps):
        text = uncommented(step_text(step))
        if TAILSCALE.search(text):
            acting.setdefault("join the tailnet", index)
        if invocation_lines(step.get("run", ""), SSH):
            acting.setdefault("connect over SSH", index)
        if re.search(r"\.env\b", str(step.get("run") or "")):
            acting.setdefault("render .env", index)
    for what, index in sorted(acting.items(), key=lambda pair: pair[1]):
        if index <= first:
            offences.append(
                f"step {index} would {what} and the step establishing the secret set is "
                f"step {first}, so the deploy acts before it knows every secret "
                "resolved. The obligation is discharged before anything is written or "
                "connected to, rather than by checking afterwards"
            )
    return offences


def disclosure_offences(step: dict, names) -> list:
    """Every line of a step's body that would print a secret's value.

    The refusal "SHALL name the secrets that resolved empty and SHALL NOT emit
    any secret's value", read the only way a static check can read it: a printing
    line that expands one of the values, by name or indirectly. Reading a value
    is not emitting one -- `[ -z "${!name}" ]` is the check itself -- so only
    lines that print are swept.
    """
    offences = []
    body = str(step.get("run") or "")
    for number, raw in enumerate(body.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not PRINTING.search(line):
            continue
        if INDIRECT_EXPANSION.search(line):
            offences.append(
                f"line {number} prints an indirectly expanded value (`${{!...}}`): "
                f"{line!r}. That is the secret itself, reached through the name"
            )
            continue
        for name in sorted(names):
            if re.search(rf"\$\{{?{re.escape(name)}\b", line):
                offences.append(
                    f"line {number} prints the value of `{name}`: {line!r}. The refusal "
                    "names what is missing; it does not disclose what is present"
                )
    if SECRETS_EXPRESSION.search(body):
        offences.append(
            "this step interpolates `${{ secrets.* }}` into its shell body. An "
            "expression is substituted as TEXT before bash parses the line, so a value "
            "carrying a quote or a newline is parsed as shell -- and one of these values "
            "is a multi-line private key. Bring them in through the step's own `env:`"
        )
    return offences


def stack_name_occurrences(text: str, names, label: str) -> list:
    """Every place a body spells one of `names`, as `label:line names X`.

    Matched CASE-SENSITIVELY over the text with its whole-line comments stripped,
    for the reason the sibling sweep gives: requirement names are cited from
    these workflows' comments and a case-insensitive sweep would read a citation
    as a workflow naming a stack.
    """
    offences = []
    for name in sorted(set(names)):
        pattern = rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])"
        for occurrence in re.finditer(pattern, text):
            line = text.count("\n", 0, occurrence.start()) + 1
            offences.append(f"{label}:{line} names `{name}`")
    return sorted(offences)


def declared_names(root: Path | None = None) -> list:
    """Every name the platform deploy must not spell: the stack directories, the
    GitHub Environments they declare, and the Ansible groups they declare."""
    names = {directory.name for directory in environment_directories(root)}
    for declaration in environment_declarations(root).values():
        if declaration.github_environment:
            names.add(declaration.github_environment)
        if declaration.target_group:
            names.add(declaration.target_group)
    return sorted(names)


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Each Stack Declares Its Own Pipeline Configuration
# (MODIFIED) -- the fifth field
# --------------------------------------------------------------------------


class TestEveryStackThatReceivesThePlatformStackDeclaresIt(unittest.TestCase):
    """MODIFIED requirement: Each Stack Declares Its Own Pipeline Configuration
    (openspec/specs/iac-cicd-pipeline/spec.md) -- "Two are **optional**: ...
    whether the shared platform stack is deployed to it, which defaults to
    **not** being deployed when absent".

    RED until the change lands: no declaration carries the field today.
    """

    def setUp(self) -> None:
        self.declarations = environment_declarations()

    def test_the_repository_has_at_least_one_stack(self) -> None:
        """SPECIFIED -- guards every assertion below from passing over an empty
        set of declarations."""
        self.assertTrue(
            self.declarations,
            "terraform/stacks/ holds no stack declaration, so every assertion about the "
            "platform opt-in would pass having read nothing",
        )

    def test_no_declaration_states_the_opt_in_in_a_form_discovery_refuses(self) -> None:
        """SPECIFIED -- "A declaration that is absent, unparseable, or carries a
        malformed value for a field this workflow reads SHALL fail the workflow"
        (The Platform Deploy Names No Stack), read against the committed tree.

        An ABSENT field is not an offence here and must not be: the requirement
        gives it a default, and "A stack declaring nothing about the platform
        stack does not receive it" is a scenario rather than a defect.
        """
        self.test_the_repository_has_at_least_one_stack()
        offences = opt_in_offences()
        self.assertEqual([], offences, "; ".join(offences))

    def test_at_least_one_stack_opts_in(self) -> None:
        """SPECIFIED -- The Platform Deploy Names No Stack
        (openspec/specs/iac-platform-deploy-pipeline/spec.md): "Where no stack
        opts in, the workflow SHALL fail rather than report success over an empty
        matrix". Read against the committed tree, this is what makes the tree one
        the workflow would not refuse.

        It is also the guard the cross-check below needs: the comparison between
        a declaration and its host's authorisations has nothing to compare while
        no stack opts in.
        """
        self.test_the_repository_has_at_least_one_stack()
        self.assertTrue(
            opting_in(),
            "no stack's declaration opts in to the platform deploy, so discovery would "
            "fail the workflow over an empty matrix -- a shared platform stack deployed "
            f"to nowhere. The declarations read {sorted(platform_opt_ins().items())}",
        )

    def test_both_committed_stacks_receive_the_platform_stack(self) -> None:
        """DERIVED (that change's tasks.md 1.1 and 1.2) -- no scenario names a
        stack, and none can: the requirement is written over "every stack whose
        own committed pipeline declaration opts in". What this change DOES,
        though, is opt both committed stacks in, and nothing else in this file
        would report a change that restructured the workflow and pointed it at
        production alone.

        Reconsider this assertion, do not weaken it, if a stack is deliberately
        taken out of the platform deploy: an opt-out is legitimate and is what
        the field is for, and the repair is to record that decision here rather
        than to delete the assertion.
        """
        self.test_the_repository_has_at_least_one_stack()
        self.assertEqual(
            sorted(self.declarations),
            opting_in(),
            "every stack this repository holds is expected to receive the shared "
            "platform stack after this change; these declarations do not say so: "
            f"{sorted(platform_opt_ins().items())}",
        )

    def test_the_opt_in_field_names_what_is_true_when_it_is_true(self) -> None:
        """SPECIFIED -- "Each optional field SHALL name what happens when it is
        **true**, rather than its inverse -- the value states ... whether the
        platform stack is deployed, rather than whether the stack is ...
        excluded".

        Polarity cannot be read off a value, only off a name: `deploys_platform:
        true` and `platform_excluded: true` are the same value and opposite
        meanings, and a declaration this suite read backwards would report an
        opt-in the workflow refuses. So the field's name must not carry a
        negation.
        """
        self.test_the_repository_has_at_least_one_stack()
        offenders = []
        for name, declaration in sorted(self.declarations.items()):
            for key in declaration.mapping:
                if PLATFORM_KEY_HINT not in normalised(key):
                    continue
                if any(
                    word in normalised(key)
                    for word in ("excluded", "exclude", "without", "skip", "disabled")
                ):
                    offenders.append(f"{name}: {key!r}")
        self.assertEqual(
            [],
            offenders,
            "these fields name the inverse of what they state, so the value that opts a "
            f"stack in reads as the value that opts it out: {offenders}",
        )


class TestAStackOptingInAuthorisesTheDeployOnItsHost(unittest.TestCase):
    """MODIFIED requirement: Each Stack Declares Its Own Pipeline Configuration --
    "A stack declaring that the platform stack is deployed to it SHALL also
    authorise that deploy on the host, by enumerating the platform application
    among the deploy-key authorisations in the `group_vars` file of the Ansible
    group it declares ... a declaration opting in without the corresponding
    authorisation SHALL fail the required status check on the pull request,
    naming both files".

    THE CHECK LIVES HERE rather than in the workflow's discovery, and that is the
    change's design.md Decision 4: it fails the pull request rather than the
    deploy, which is earlier by one merge, and `deploy_apps` is a list of
    mappings, which the workflows' line readers are the wrong tool for. This
    module is reached by the required status check through the suite as a whole
    -- `test_ci_configuration.TestTheSuiteIsWiredIntoTheRequiredCheck` is what
    asserts that, and it is not restated here.

    VACUOUS until a stack opts in, which is why the first test below is the guard
    rather than a courtesy.
    """

    def test_there_is_an_opt_in_to_check(self) -> None:
        """SPECIFIED -- without this, the cross-check below passes over an empty
        set of stacks on exactly the day the field is forgotten."""
        self.assertTrue(
            opting_in(),
            "no stack's declaration opts in to the platform deploy, so the comparison "
            "between a declaration and its host's authorisations reads one side of it",
        )

    def test_every_opted_in_stacks_host_authorises_the_platform_deploy_key(self) -> None:
        """SPECIFIED -- see the class docstring."""
        self.test_there_is_an_opt_in_to_check()
        declarations = environment_declarations()
        offences = deploy_authorisation_offences(
            platform_opt_ins(),
            {name: declaration.target_group for name, declaration in declarations.items()},
            authorised_applications(),
        )
        self.assertEqual([], offences, "; ".join(offences))

    def test_a_host_prepared_before_its_deploy_path_is_not_reported(self) -> None:
        """SPECIFIED -- scenario "A host authorising the deploy key before the
        pipeline is pointed at it is accepted": "discovery and the required status
        check SHALL both accept the tree, that interval being the deliberate state
        of a host prepared before its deploy path exists".

        Read against the committed tree, which is IN that interval today: a host
        authorises the key and no declaration opts in. Asserting it here rather
        than only in the discriminator is what keeps this check from being
        repaired into a two-directional one -- the converse is deliberately not
        required, and this is the assertion that says so.
        """
        authorisations = authorised_applications()
        prepared = sorted(
            group
            for group, applications in authorisations.items()
            if PLATFORM_APPLICATION in applications
        )
        self.assertTrue(
            prepared,
            "no group_vars file authorises the platform deploy key at all, so this "
            "assertion reads nothing -- and no stack could opt in without failing the "
            f"check above. The groups read were {sorted(authorisations)}",
        )
        declarations = environment_declarations()
        offences = deploy_authorisation_offences(
            {name: None for name in declarations},
            {name: declaration.target_group for name, declaration in declarations.items()},
            authorisations,
        )
        self.assertEqual(
            [],
            offences,
            "a host authorising the platform deploy key while its stack's declaration "
            f"does not opt in was reported as an offence: {offences}",
        )


# --------------------------------------------------------------------------
# iac-platform-deploy-pipeline / The Platform Deploy Names No Stack (ADDED)
# --------------------------------------------------------------------------


class TestThePlatformDeployNamesNoStack(unittest.TestCase):
    """ADDED requirement: The Platform Deploy Names No Stack
    (openspec/specs/iac-platform-deploy-pipeline/spec.md) -- the workflow "SHALL
    NOT enumerate stacks, name one in a condition, or map one to its secrets or
    to its GitHub Environment in workflow text", and the scenario "A stack opting
    in needs no workflow edit": the next merge deploys to it "with no change to
    any file under `.github/workflows/`".

    This is the sweep `test_environment_agnostic_pipeline
    .TestNoWorkflowNamesAnEnvironment` runs over the three Terraform workflows,
    pointed at the fourth workflow this change brings onto the mechanism. Widening
    that module's own tuple is the implementing author's task (that change's
    tasks.md 3.2) and is recorded in this change's test-plan.md; what is here is
    additive and reaches this workflow whether or not that widening happens.

    RED until the change lands: the committed workflow declares `environment:` as
    a literal naming the production stack's Environment.
    """

    def _names(self) -> list:
        return declared_names()

    def test_there_is_a_name_to_look_for(self) -> None:
        """SPECIFIED -- guards the sweep below from passing over an empty set of
        names, which an emptied stacks directory or an unreadable declaration
        would produce."""
        self.assertTrue(
            self._names(),
            "no stack directory, no declared GitHub Environment and no declared Ansible "
            "group was found, so a sweep for stack literals would read nothing",
        )

    def test_the_platform_deploy_names_no_stack_environment_or_group(self) -> None:
        """SPECIFIED -- see the class docstring."""
        self.test_there_is_a_name_to_look_for()
        offences = stack_name_occurrences(
            uncommented(read_text(PLATFORM_DEPLOY)), self._names(), PLATFORM_DEPLOY.name
        )
        self.assertEqual(
            [],
            offences,
            "this workflow names a stack, its GitHub Environment or its Ansible group in "
            "its own text, so a stack could not be opted in without editing it -- which "
            f"is the defect this requirement exists to prevent: {offences}",
        )

    def test_no_job_declares_a_literal_github_environment(self) -> None:
        """SPECIFIED -- Each Stack's Deploy Attaches to the Environment Its Own
        Declaration Names: each stack is "deployed by a job of its own, attached
        to the GitHub Environment **that stack's** declaration names", and The
        Platform Deploy Names No Stack: which Environment each deploy attaches to
        "SHALL be discovered by reading the committed per-stack pipeline
        declarations".

        What this replaces is the equality against one literal that three existing
        modules assert today. The hazard that equality held is not retired by this
        change, only relocated: GitHub creates an Environment a workflow names,
        with no protection rules, so a deploy gated on a name no stack declares
        runs unreviewed rather than failing. Here the name cannot be written at
        all -- it is resolved per row from discovery -- and the census that no two
        stacks declare one Environment (`test_environment_agnostic_pipeline`) is
        the other half.
        """
        declared = {
            name: declaration.github_environment
            for name, declaration in environment_declarations().items()
            if declaration.github_environment
        }
        self.assertTrue(
            declared,
            "no stack declares a GitHub Environment, so this comparison would read one "
            "side of it",
        )
        offences = gate_offences(load_yaml(PLATFORM_DEPLOY), declared)
        self.assertEqual([], offences, "; ".join(offences))

    def test_no_matrix_row_carries_a_secret_name(self) -> None:
        """SPECIFIED -- "The per-stack secrets this deploy reads SHALL be reached
        by their own fixed names, resolved against the Environment each deploy job
        attaches to, rather than by any name derived from or mapped to the stack."

        A matrix indexed into the `secrets` context is the mapping this forbids,
        written as data rather than as workflow text -- and it is how a per-stack
        indirection would most plausibly be reintroduced once the literal
        Environment is gone.
        """
        workflow = load_yaml(PLATFORM_DEPLOY)
        rows = matrix_jobs(workflow)
        self.assertTrue(
            rows,
            "no job builds its matrix from another job's outputs, so there is no "
            "discovered matrix to read -- the stacks deployed to are written in workflow "
            "text or nowhere",
        )
        offenders = []
        for name, job in sorted(rows.items()):
            body = yaml.safe_dump(job, default_flow_style=False)
            for match in re.finditer(r"secrets\s*\[", body):
                offenders.append(f"{name}: indexes `secrets[...]` at offset {match.start()}")
        self.assertEqual(
            [],
            offenders,
            "a deploy row reaches a secret by a name built from the stack rather than by "
            f"a fixed name resolved against that stack's Environment: {offenders}",
        )


class TestEachDeployRowAttachesToTheEnvironmentItsStackDeclares(unittest.TestCase):
    """ADDED requirement: Each Stack's Deploy Attaches to the Environment Its Own
    Declaration Names -- "the workflow SHALL NOT distinguish them ... a condition
    in workflow text that treated one stack's deploy differently from another's
    would be the stack-naming this capability forbids, and would put the approval
    decision somewhere no repository setting can reach".

    Whether a deploy PAUSES is a property of the Environment's protection rules,
    which are repository settings this suite cannot read. What it can read is that
    nothing in the workflow decides it -- which is the half the requirement puts
    in the repository.

    RED until the change lands.
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(PLATFORM_DEPLOY)

    def test_every_deploy_row_attaches_to_an_environment(self) -> None:
        """SPECIFIED -- "Each such stack SHALL be deployed by a job of its own,
        attached to the GitHub Environment **that stack's** declaration names".

        Also what keeps *Automated Dependency Updates*
        (openspec/specs/iac-safety-hardening/spec.md) true once no literal
        Environment is written anywhere: an automatically proposed image bump,
        merged, reaches every deploy row, and every row attaches to an Environment
        -- so no route exists by which such a bump deploys ungated.
        """
        rows = matrix_jobs(self.workflow)
        self.assertTrue(
            rows,
            "no job builds its matrix from discovery's outputs, so there are no "
            "per-stack deploy rows at all",
        )
        ungated = sorted(name for name, job in rows.items() if job.get("environment") is None)
        self.assertEqual(
            [],
            ungated,
            "these deploy rows attach to no GitHub Environment, so their deploys are "
            f"subject to no protection rule and hold no confined credential: {ungated}",
        )

    def test_no_condition_distinguishes_one_stacks_deploy_from_anothers(self) -> None:
        """SPECIFIED -- see the class docstring. A job- or step-level `if:` reading
        a matrix value is how one stack's deploy would be treated differently
        without naming it: `if: matrix.stack.name != '...'` is caught by the name
        sweep, `if: matrix.stack.reviewed` is not."""
        offenders = []
        for name, job in sorted(matrix_jobs(self.workflow).items()):
            condition = str(job.get("if") or "")
            if MATRIX_REFERENCE.search(condition):
                offenders.append(f"{name}: job-level `if: {condition}`")
            for index, step in enumerate(job.get("steps") or []):
                step_condition = str(step.get("if") or "")
                if MATRIX_REFERENCE.search(step_condition):
                    offenders.append(f"{step_label(name, index, step)}: `if: {step_condition}`")
        self.assertEqual(
            [],
            offenders,
            "these conditions make what a deploy does depend on which stack's row it is, "
            "putting the approval decision somewhere no repository setting can reach: "
            f"{offenders}",
        )

    def test_the_same_declared_field_gates_both_kinds_of_change_to_a_stack(self) -> None:
        """SPECIFIED -- scenario "Same approvers gate both kinds of change to one
        stack": both "SHALL be gated by that stack's own declared GitHub
        Environment and its required reviewers, rather than each defining a
        separate approval list".

        What a static read can establish is that there is ONE declared field both
        mechanisms resolve their Environment from: the apply workflow already
        reads the declaration's GitHub Environment field, and this assertion is
        that the deploy resolves its own Environment from the discovered row
        rather than from a second name written alongside it. The reviewers
        themselves are a repository setting.
        """
        declared = {
            name: declaration.github_environment
            for name, declaration in environment_declarations().items()
            if declaration.github_environment
        }
        self.assertTrue(declared, "no stack declares a GitHub Environment")
        rows = matrix_jobs(self.workflow)
        self.assertTrue(rows, "no job builds its matrix from discovery's outputs")
        for name, job in sorted(rows.items()):
            with self.subTest(job=name):
                environment = declared_environment(job) or ""
                self.assertTrue(
                    MATRIX_REFERENCE.search(environment),
                    f"{name}: attaches to `{environment}`, which reads no value from the "
                    "discovered row -- so the Environment it attaches to is not the one "
                    "that stack's own declaration names",
                )
                sources = matrix_source_jobs(self.workflow, job)
                self.assertTrue(
                    sources,
                    f"{name}: its matrix is not built from another job's outputs, so the "
                    "Environment it resolves comes from workflow text rather than from "
                    "the declaration the apply job reads",
                )


class TestNoStacksDeployIsOrderedBehindAnother(unittest.TestCase):
    """ADDED requirement: Each Stack's Deploy Attaches to the Environment Its Own
    Declaration Names -- "Deploying to two stacks SHALL NOT impose an order on
    them. No stack's deploy SHALL be made to depend on another stack's deploy,
    whether by a dependency edge between them, by cancelling sibling deploys when
    one fails, or by running them one at a time."

    RED until the change lands.
    """

    def test_one_stacks_failed_deploy_does_not_withhold_anothers(self) -> None:
        """SPECIFIED -- scenario "One stack's failed deploy does not withhold
        another's"."""
        offences = ordering_offences(load_yaml(PLATFORM_DEPLOY))
        self.assertEqual([], offences, "; ".join(offences))


class TestEachStacksDeployIsSerialisedOnItsOwn(unittest.TestCase):
    """MODIFIED requirement: Serialized Deploys -- "Each stack's deploy job SHALL
    run under a GitHub Actions `concurrency` group naming that stack, so that two
    merges in quick succession queue rather than run concurrently or cancel each
    other against one host ... The group SHALL name the stack rather than being
    shared across stacks."

    RED until the change lands: the group is declared at workflow level today,
    where it cannot read a matrix.
    """

    def test_two_merges_queue_per_stack_and_one_stack_does_not_hold_another(self) -> None:
        """SPECIFIED -- both scenarios: "Two merges in quick succession deploy in
        order" and "One stack's queued deploy does not hold another's"."""
        offences = serialisation_offences(load_yaml(PLATFORM_DEPLOY))
        self.assertEqual([], offences, "; ".join(offences))


# --------------------------------------------------------------------------
# iac-platform-deploy-pipeline / An Incomplete Per-Stack Secret Set Is Reported
# by Name (ADDED)
# --------------------------------------------------------------------------


class TestTheSecretSetIsEstablishedBeforeAnythingIsWritten(unittest.TestCase):
    """ADDED requirement: An Incomplete Per-Stack Secret Set Is Reported by Name
    -- "Before joining the tailnet, rendering any file or attempting any
    connection, each stack's deploy job SHALL establish that **every** secret that
    deploy consumes resolved to a value ... and SHALL fail where any did not,
    naming the stack, the GitHub Environment the values should have come from, and
    each name that resolved empty. It SHALL NOT emit any value in doing so."

    RED until the change lands: no step reads the whole set today.

    What a static read cannot establish, and what is therefore asserted nowhere:
    that the refusal actually fires. Whether a secret resolves to an empty string
    is a repository setting, and the step's own exit status is a runtime fact.
    What is asserted is the shape the requirement puts in the repository -- that
    one step reads every name, that it runs before anything is joined, rendered or
    connected to, and that its message can carry no value.
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(PLATFORM_DEPLOY)
        self.rows = matrix_jobs(self.workflow)

    def _required(self, job: dict) -> set:
        referenced = secrets_referenced_by(job)
        resolved, offences = rendered_secret_resolution(referenced, secret_backed_variables())
        self.assertEqual([], offences, "; ".join(offences))
        required = set(resolved.values())
        for name in (DEPLOY_HOST_SECRET, DEPLOY_KEY_SECRET):
            self.assertIn(
                name,
                referenced,
                f"this deploy reads no secret called `{name}`, so the set whose "
                "completeness must be established before the tailnet join is not the set "
                f"the requirement names. It reads {sorted(referenced)}",
            )
            required.add(name)
        return required

    def test_the_set_is_every_secret_backed_value_the_deploy_consumes(self) -> None:
        """SPECIFIED -- "the secret naming that stack's host, the deploy key it
        authenticates with, and each value rendered into the `.env` the stack
        definition reads that comes from a secret (the tailnet bind address is
        derived at deploy time, is behind no secret ...)".

        The set is computed from the committed `platform/.env.example` rather than
        written here, so a variable added to the stack definition without being
        added to the refusal is reported rather than silently uncovered.
        """
        self.assertTrue(self.rows, "no job builds its matrix from discovery's outputs")
        variables = env_example_variables()
        self.assertTrue(variables, "platform/.env.example documents no variable")
        excluded = sorted(set(variables) - set(secret_backed_variables()))
        self.assertEqual(
            1,
            len(excluded),
            "exactly one documented variable is derived at deploy time rather than held "
            f"behind a secret; these were read as derived: {excluded}",
        )
        for name, job in sorted(self.rows.items()):
            with self.subTest(job=name):
                required = self._required(job)
                self.assertEqual(
                    len(secret_backed_variables()) + 2,
                    len(required),
                    f"{name}: the secret set resolved to {sorted(required)}, which is not "
                    "one name per secret-backed .env value plus the host and the key",
                )

    def test_the_whole_set_is_established_before_anything_is_joined_or_written(self) -> None:
        """SPECIFIED -- the requirement's opening SHALL, and the scenarios "A stack
        opted in before its secrets exist fails by name", "A partially entered
        secret set fails rather than deploying" and "An absent credential secret
        fails the deploy rather than starting the service". All three are the same
        ordering obligation read on three different members of the set, and the
        third is why the check cannot be a check on the host alone: an empty
        administrative credential lets the service start, satisfies the deploy's
        wait for health, and leaves the run green.
        """
        self.assertTrue(self.rows, "no job builds its matrix from discovery's outputs")
        for name, job in sorted(self.rows.items()):
            with self.subTest(job=name):
                offences = secret_set_offences(job, self._required(job))
                self.assertEqual([], offences, f"{name}: " + "; ".join(offences))

    def test_the_refusal_discloses_no_value(self) -> None:
        """SPECIFIED -- scenario "The refusal names what is missing without
        disclosing what is present": the message "SHALL name the secrets that
        resolved empty and SHALL NOT emit any secret's value"."""
        self.assertTrue(self.rows, "no job builds its matrix from discovery's outputs")
        for name, job in sorted(self.rows.items()):
            required = self._required(job)
            for index, step in enumerate(job.get("steps") or []):
                if not required <= secrets_referenced_by(step):
                    continue
                with self.subTest(step=step_label(name, index, step)):
                    offences = disclosure_offences(step, required)
                    self.assertEqual([], offences, "; ".join(offences))


# --------------------------------------------------------------------------
# iac-platform-deploy-pipeline / Reviewer Sees the Exact Diff Before Approving
# (MODIFIED)
# --------------------------------------------------------------------------


class TestTheDiffIsPublishedOnceBeforeAnyGate(unittest.TestCase):
    """MODIFIED requirement: Reviewer Sees the Exact Diff Before Approving -- "a
    job running under no `environment:` (and therefore with no access to any
    deploy credential) SHALL compute the diff this merge introduces under
    `platform/**` and write it to the workflow run's job summary ... One such job
    SHALL serve every stack the merge deploys to."

    GREEN in part from the moment it is written: the committed workflow already
    publishes the diff from a credential-free job, which this change does not
    alter. What is red until the change lands is the dependency between that job
    and the deploy ROWS, there being no rows yet.
    """

    def test_one_credential_free_job_publishes_the_diff_before_every_gate(self) -> None:
        """SPECIFIED -- the requirement's opening SHALL and the scenario "Approver
        sees the diff without leaving the workflow run"."""
        offences = diff_offences(load_yaml(PLATFORM_DEPLOY))
        self.assertEqual([], offences, "; ".join(offences))

    def test_diff_visibility_does_not_depend_on_a_review_having_occurred(self) -> None:
        """SPECIFIED -- scenario "Diff visibility does not depend on pull request
        review having occurred": a reviewed Environment's required reviewer "SHALL
        still see the exact diff at approval time, independent of whatever review,
        if any, happened on the pull request itself".

        Read the only way a committed file can carry it: the publishing job runs
        on the merge itself, under no condition that could make it depend on what
        happened on the pull request. An `if:` is the only place such a dependency
        could be written, so that is what is swept.
        """
        workflow = load_yaml(PLATFORM_DEPLOY)
        publishing = summary_writing_jobs(workflow)
        self.assertTrue(
            publishing, "no job writes to `$GITHUB_STEP_SUMMARY`, so nothing publishes the diff"
        )
        offenders = []
        for name, job in sorted(publishing.items()):
            condition = str(job.get("if") or "")
            if re.search(r"review|approv", condition, re.IGNORECASE):
                offenders.append(f"{name}: `if: {condition}`")
        self.assertEqual(
            [],
            offenders,
            "the diff a reviewer reads at approval time is published conditionally on a "
            f"review having happened earlier: {offenders}",
        )


# --------------------------------------------------------------------------
# iac-platform-deploy-pipeline / the credentials, the tailnet and the host
# (MODIFIED)
# --------------------------------------------------------------------------


class TestTheDeployReachesItsHostOverTheTailnetAsTheDeployAccount(unittest.TestCase):
    """MODIFIED requirements: Deploy Job Reaches the Host Over a Private Tailnet,
    Deploy Credential Confined to the Gated Job, and Platform Secrets Rendered
    from CI at Deploy Time.

    GREEN from the moment it is written: all three properties are already true of
    the committed workflow and this change deliberately does not alter them. What
    they are for is the second stack -- each is written over whatever deploy jobs
    the workflow has, so a second row that joined no tailnet, connected as
    somebody else, or read a credential from an ungated job would be reported.
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(PLATFORM_DEPLOY)

    def test_every_connecting_job_joins_the_tailnet_before_its_first_ssh(self) -> None:
        """SPECIFIED -- scenario "Deploy job joins the tailnet before SSH": "it
        SHALL establish tailnet connectivity before its first SSH attempt"."""
        offences = tailnet_ordering_offences(self.workflow)
        self.assertEqual([], offences, "; ".join(offences))

    def test_every_connection_authenticates_as_the_provisioned_deploy_account(self) -> None:
        """SPECIFIED -- scenario "Deploy job authenticates as the provisioned deploy
        account": "it SHALL authenticate as the restricted `deploy` account
        provisioned by the host-configuration change, not as any operator's
        personal account"."""
        offences = deploy_account_offences(self.workflow)
        self.assertEqual([], offences, "; ".join(offences))

    def test_the_tailnet_and_deploy_credentials_are_confined_to_a_gated_job(self) -> None:
        """SPECIFIED -- Deploy Credential Confined to the Gated Job, scenarios
        "Deploy key is inaccessible before approval" and "A job attached to no
        Environment can read no stack's key"; and Deploy Job Reaches the Host Over
        a Private Tailnet, scenario "Tailnet join credential is confined to the
        gated job".

        "Gated" names the ATTACHMENT, not the pause: confinement holds whether or
        not the Environment requires a reviewer, which is the half of this a
        static read can reach.
        """
        referenced = set()
        for job in jobs(self.workflow).values():
            referenced |= secrets_referenced_by(job)
        confined = {
            name
            for name in referenced
            if TAILSCALE.search(name) or name.upper().startswith("PLATFORM")
        }
        self.assertTrue(
            confined,
            "this workflow reads no deploy or tailnet credential at all, so the "
            f"confinement assertion would read nothing. It reads {sorted(referenced)}",
        )
        offences = confinement_offences(self.workflow, confined)
        self.assertEqual([], offences, "; ".join(offences))


class TestOneStacksKeyDoesNotReachAnotherStacksHost(unittest.TestCase):
    """MODIFIED requirement: Deploy Credential Confined to the Gated Job -- "One
    stack's key SHALL NOT be able to deploy to another stack's host. Each stack's
    key is a keypair of its own, whose public half that host authorises and no
    other host does."

    GREEN from the moment it is written: the two hosts already authorise different
    public halves, which is what made the staging key's private half safe to hold
    out of the pipeline. The private halves are repository settings and are
    unreadable here; the public halves are committed, and two hosts authorising ONE
    public half is the failure this can see.
    """

    def test_no_two_hosts_authorise_the_same_platform_deploy_key(self) -> None:
        """SPECIFIED -- scenario "One stack's key does not reach another stack's
        host": a compromised key "SHALL authorise a deploy to that stack's host
        alone, every other stack's host authorising a different key"."""
        offences = shared_key_offences(authorised_keys())
        self.assertEqual([], offences, "; ".join(offences))


class TestTheRenderedEnvIsNeverCommitted(unittest.TestCase):
    """MODIFIED requirement: Platform Secrets Rendered from CI at Deploy Time --
    the `.env` "SHALL NOT be committed to the repository in any form, plaintext or
    encrypted".

    GREEN from the moment it is written; this change does not alter it. What it is
    for is a per-stack render: the obvious way to give two stacks two sets of
    values is to commit two files.
    """

    def test_no_env_file_is_committed_under_the_stack_definition(self) -> None:
        """SPECIFIED -- scenario "Rendered .env never enters version control"."""
        self.assertTrue((ROOT / "platform").is_dir(), f"{ROOT / 'platform'} does not exist")
        offenders = committed_env_files()
        self.assertEqual(
            [],
            offenders,
            "these rendered environment files are committed, so a stack's secrets are in "
            f"version control: {offenders}",
        )

    def test_the_ignore_rules_keep_a_rendered_env_out(self) -> None:
        """DERIVED -- no scenario states it. The requirement forbids the file being
        committed; what keeps a locally rendered one from being committed by
        accident is an ignore rule, and the absence of the file today is equally
        consistent with nobody having rendered one yet."""
        text = read_text(GITIGNORE)
        self.assertTrue(
            any(line.strip().rstrip("/").endswith(".env") for line in text.splitlines()),
            "nothing in .gitignore names `.env`, so a rendered file sitting in a working "
            "tree is one `git add .` away from being committed",
        )


# --------------------------------------------------------------------------
# iac-platform-deploy-pipeline / discovery fails closed
# --------------------------------------------------------------------------


class PlatformDiscoveryFixtureMixin(DeclarationTreeFixtureMixin):
    """Builds a synthetic `terraform/stacks/` tree whose declarations carry the
    platform opt-in.

    Built from a COMMITTED declaration -- same filename, same field names,
    different values -- rather than from a spelling this file invented, which is
    the base mixin's rule and the reason it exists. The opt-in field is the one
    exception while the committed declarations carry none: its name then falls
    back to `PLATFORM_KEY_FALLBACK`, and follows the committed spelling from the
    moment one exists.
    """

    def _scratch(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="platform-discovery-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        return directory

    def _opt_in_key(self) -> str:
        _, template, _ = self._template()
        for key in template:
            if PLATFORM_KEY_HINT in normalised(key):
                return key
        return PLATFORM_KEY_FALLBACK

    def _declaration(self, name: str, opt_in, environment: str | None = None) -> dict:
        mapping = self._declaration_for(
            f"HCLOUD_TOKEN_{name.upper()}",
            environment if environment is not None else f"{name}-environment",
            gate=False,
        )
        key = self._opt_in_key()
        mapping.pop(key, None)
        if opt_in is not None:
            mapping[key] = opt_in
        return mapping

    def _tree(self, stacks: dict) -> Path:
        """`stacks` maps a directory name to its opt-in value, or to `None` for a
        declaration carrying no opt-in field at all."""
        scratch = self._scratch()
        self._write_tree(
            scratch, {name: self._declaration(name, opt_in) for name, opt_in in stacks.items()}
        )
        return scratch


class TestPlatformDeployDiscoveryFailsClosed(PlatformDiscoveryFixtureMixin, unittest.TestCase):
    """ADDED requirement: The Platform Deploy Names No Stack -- "Discovery SHALL
    fail closed and SHALL report what it found."

    Runs the workflow's own discovery body rather than reading it, the same
    extract-and-run shape `test_host_converge_workflow
    .TestHostConvergeDiscoveryFailsClosed` uses. Grepping would establish that a
    discovery step exists; only running it establishes that it refuses. That the
    body can be run at all is that change's tasks.md 2.3's own obligation -- "Take
    nothing from the event inside the step body, so `.github/tests` can execute it
    against a scratch tree".

    RED until the change lands: the workflow has no discovery step, so the locator
    fails and every test in this class reports that absence. That is the
    target-absent result and it establishes the absence and nothing else -- none
    of these assertions has been exercised until the step exists.

    UNRESOLVED PROJECT QUESTION, recorded in this change's test-plan.md and
    repeated here because a reader of a red test needs it: nothing in the deltas
    fixes the environment variable the dispatch input arrives under inside the
    body. It is resolved from the step's own `env:` block -- the key whose value
    references the dispatch input -- so the implementing author's choice of name
    is followed rather than asserted.
    """

    def setUp(self) -> None:
        require_external_tools(
            self,
            ("bash", "find", "jq"),
            "execute the platform deploy workflow's stack-discovery body",
        )

    def discovery_step(self):
        """The discovery body, located by shape: the one `run:` step that
        enumerates the stacks directory, writes to `$GITHUB_OUTPUT`, and carries
        no `${{ }}`."""
        workflow = load_yaml(PLATFORM_DEPLOY)
        candidates = []
        for job_name, index, step in steps(workflow):
            body = str(step.get("run") or "")
            if not body:
                continue
            if "stacks" not in body or "GITHUB_OUTPUT" not in body:
                continue
            if ACTIONS_EXPRESSION.search(body):
                continue
            candidates.append(
                (step_label(job_name, index, step), (job_name, jobs(workflow)[job_name], step))
            )
        self.assertEqual(
            1,
            len(candidates),
            f"expected exactly one `run:` step in {PLATFORM_DEPLOY.name} that enumerates "
            "`terraform/stacks/`, emits to `$GITHUB_OUTPUT` and carries no Actions "
            f"expression, found {len(candidates)}: "
            f"{sorted(label for label, _ in candidates)}. Emitting the matrix is what "
            "discovery is FOR, and discovery carrying an expression in its body cannot be "
            "executed anywhere but on a runner, so its refusals would be asserted nowhere",
        )
        return candidates[0][1]

    def _input_variable(self, job: dict, step: dict):
        for holder in (step, job):
            for key, value in (holder.get("env") or {}).items():
                if DISPATCH_INPUT.search(str(value)):
                    return str(key)
        return None

    def _run(self, tree: Path, dispatched=None):
        _, job, step = self.discovery_step()
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
                "the discovery step takes no environment variable carrying the dispatch "
                "input, so a run requested by hand for one stack reaches the body that "
                "would have to validate it through nothing. Its `env:` keys are "
                f"{sorted((step.get('env') or {}))}",
            )
            environment[variable] = dispatched
        elif variable:
            environment[variable] = ""
        result = run_snippet(str(step["run"]), environment, tree)
        emitted = outputs.read_text(encoding="utf-8") + summary.read_text(encoding="utf-8")
        return result, emitted

    def _combined(self, result) -> str:
        return (result.stdout + result.stderr).strip()

    def test_discovery_emits_every_stack_that_opts_in(self) -> None:
        """SPECIFIED -- scenario "A stack opting in needs no workflow edit": the
        next merge "SHALL deploy to it, with no change to any file under
        `.github/workflows/`".

        The converse every refusal below needs: discovery that failed on every tree
        would satisfy each of them while deploying nothing.
        """
        tree = self._tree({"alpha": True, "bravo": True})
        result, emitted = self._run(tree)
        self.assertEqual(
            0,
            result.returncode,
            "discovery refused a tree carrying two stacks that opt in: "
            f"{self._combined(result)[-800:]!r}",
        )
        published = emitted + result.stdout
        for expected in ("alpha", "bravo", "alpha-environment", "bravo-environment"):
            self.assertIn(
                expected,
                published,
                f"discovery ran over a tree holding `{expected}` and emitted nothing "
                "naming it, so that stack's deploy would take its Environment from "
                f"workflow text or not at all: {published!r}",
            )

    def test_a_stack_that_has_not_opted_in_is_excluded_and_named(self) -> None:
        """SPECIFIED -- scenarios "A stack that has not opted in is excluded and
        named" and "A stack declaring nothing about the platform stack does not
        receive it": "no deploy job SHALL run for that stack, and the run SHALL
        report that stack as excluded rather than omitting it silently"."""
        for described, declared in (("declaring false", False), ("declaring nothing", None)):
            with self.subTest(stack=described):
                tree = self._tree({"alpha": True, "bravo": declared})
                result, emitted = self._run(tree)
                self.assertEqual(
                    0,
                    result.returncode,
                    "discovery refused a tree whose second stack simply does not receive "
                    f"the platform stack: {self._combined(result)[-800:]!r}",
                )
                self.assertIn("alpha", emitted, f"the opted-in stack is not in {emitted!r}")
                self.assertNotIn(
                    "bravo",
                    emitted,
                    f"a stack that does not opt in reached the deploy matrix: {emitted!r}",
                )
                self.assertIn(
                    "bravo",
                    self._combined(result),
                    "the excluded stack is named nowhere in the run's output, so a stack "
                    "omitted by a forgotten field is invisible until somebody notices it "
                    f"was never deployed to: {self._combined(result)[-800:]!r}",
                )

    def test_no_stack_opting_in_fails_the_workflow(self) -> None:
        """SPECIFIED -- scenario "No stack opting in fails the workflow": "the
        workflow SHALL fail with a message identifying discovery as the cause, and
        SHALL NOT allow the deploy job to be skipped and the run reported as
        successful"."""
        tree = self._tree({"alpha": False, "bravo": None})
        result, emitted = self._run(tree)
        self.assertNotEqual(
            0,
            result.returncode,
            "discovery reported success over a tree no stack opts in from, so the deploy "
            "job is skipped over an empty matrix and the run is green having deployed a "
            f"shared platform stack to nowhere: {emitted!r}",
        )

    def test_a_dispatch_naming_an_unknown_stack_is_refused(self) -> None:
        """SPECIFIED -- scenario "A deploy requested for an unknown stack is
        refused": "the run SHALL fail, naming the requested stack and reporting the
        stacks discovery did find, rather than producing an empty matrix and
        reporting success"."""
        tree = self._tree({"alpha": True, "bravo": True})
        result, emitted = self._run(tree, dispatched="charlie")
        combined = self._combined(result)
        self.assertNotEqual(
            0,
            result.returncode,
            "a deploy requested by hand for a stack discovery did not find produced no "
            f"failure: {emitted!r}",
        )
        self.assertIn(
            "charlie", combined, f"the refusal does not name what was asked for: {combined!r}"
        )
        for found in ("alpha", "bravo"):
            self.assertIn(
                found,
                combined,
                "the refusal does not report the stacks discovery did find, so the "
                f"operator is told only that they were wrong: {combined!r}",
            )

    def test_a_dispatch_naming_a_stack_that_did_not_opt_in_is_refused(self) -> None:
        """SPECIFIED -- the same scenario, read on the case that is easiest to
        mistake for the one above: the stack EXISTS and is a stack discovery found,
        but is not one that opts in, so a deploy to it would run under an
        Environment holding none of this deploy's secrets."""
        tree = self._tree({"alpha": True, "bravo": False})
        result, emitted = self._run(tree, dispatched="bravo")
        self.assertNotEqual(
            0,
            result.returncode,
            "a deploy requested by hand for a stack that has not opted in produced no "
            f"failure: {emitted!r}",
        )
        self.assertIn("bravo", self._combined(result))

    def test_a_dispatch_naming_one_stack_deploys_to_that_stack_alone(self) -> None:
        """DERIVED (that change's design.md Decision 8) -- the requirement obliges
        discovery to refuse an unknown name; that a known one SELECTS is what the
        dispatch is for, so that a rebuilt host can be redeployed to without waking
        another stack's approval gate. A dispatch that selected every stack anyway
        would satisfy every refusal above and serve none of its purpose."""
        tree = self._tree({"alpha": True, "bravo": True})
        result, emitted = self._run(tree, dispatched="alpha")
        self.assertEqual(
            0,
            result.returncode,
            "discovery refused a dispatch naming a stack that opts in: "
            f"{self._combined(result)[-800:]!r}",
        )
        self.assertIn("alpha", emitted)
        self.assertNotIn(
            "bravo",
            emitted,
            "a dispatch naming one stack emitted a matrix carrying another, so a rebuild "
            "redeploys every stack and wakes a reviewed Environment's gate for a host "
            f"that did not change: {emitted!r}",
        )

    def test_an_empty_dispatch_input_selects_every_stack_that_opts_in(self) -> None:
        """DERIVED (that change's tasks.md 2.2) -- no scenario states it, and it is
        the case every `push` produces: the dispatch input is absent and must not
        be confused with a name discovery did not find. Conflating the two would
        fail every merge."""
        tree = self._tree({"alpha": True, "bravo": True})
        result, emitted = self._run(tree, dispatched="")
        self.assertEqual(
            0,
            result.returncode,
            "discovery refused a run supplying no stack name, which is every merge: "
            f"{self._combined(result)[-800:]!r}",
        )
        for expected in ("alpha", "bravo"):
            self.assertIn(expected, emitted)

    def test_a_stack_directory_carrying_no_declaration_is_refused(self) -> None:
        """SPECIFIED -- "A declaration that is absent, unparseable, or carries a
        malformed value for a field this workflow reads SHALL fail the workflow
        with a message naming the stack and the field"."""
        scratch = self._scratch()
        self._write_tree(scratch, {"alpha": self._declaration("alpha", True), "bravo": None})
        result, emitted = self._run(scratch)
        self.assertNotEqual(
            0,
            result.returncode,
            "a stack directory carrying no pipeline declaration was passed over rather "
            f"than refused: {emitted!r}",
        )
        self.assertIn(
            "bravo",
            self._combined(result),
            "the refusal does not name the stack directory that carries no declaration: "
            f"{self._combined(result)[-800:]!r}",
        )

    def test_a_stack_opting_in_without_an_environment_is_refused(self) -> None:
        """SPECIFIED -- "A declaration that ... carries a malformed value for a
        field this workflow reads SHALL fail the workflow with a message naming the
        stack and the field". A stack that opts in and declares no GitHub
        Environment is the case that matters most: GitHub creates an Environment
        for a name a workflow resolves to, with no protection rules, so an empty
        one deploys unreviewed rather than failing."""
        scratch = self._scratch()
        declaration = self._declaration("bravo", True, environment="")
        self._write_tree(
            scratch, {"alpha": self._declaration("alpha", True), "bravo": declaration}
        )
        result, emitted = self._run(scratch)
        self.assertNotEqual(
            0,
            result.returncode,
            "a stack opting in to the platform deploy while declaring no GitHub "
            f"Environment was accepted: {emitted!r}",
        )
        self.assertIn("bravo", self._combined(result))

    def test_an_opt_in_value_that_is_neither_true_nor_false_is_refused(self) -> None:
        """SPECIFIED -- the same sentence, read on the value rather than on the
        field: discovery refuses a value "that is neither `true` nor `false`,
        rather than treating anything unrecognised as one of them". Treating an
        unrecognised value as false skips a stack silently; treating it as true
        deploys to one under credentials that may not exist."""
        for value in ("maybe", "yes", "True "):
            with self.subTest(value=value):
                scratch = self._scratch()
                self._write_tree(
                    scratch,
                    {
                        "alpha": self._declaration("alpha", True),
                        "bravo": self._declaration("bravo", value),
                    },
                )
                result, emitted = self._run(scratch)
                self.assertNotEqual(
                    0,
                    result.returncode,
                    f"a declaration whose opt-in reads {value!r} was resolved to a boolean "
                    f"rather than refused: {emitted!r}",
                )

    def test_the_emitted_matrix_carries_no_secret_name(self) -> None:
        """SPECIFIED -- "The per-stack secrets this deploy reads SHALL be reached by
        their own fixed names, resolved against the Environment each deploy job
        attaches to, rather than by any name derived from or mapped to the stack."
        A matrix carrying a per-stack secret name is that mapping, written as data.
        The fixture declarations each name a read-only secret, so a discovery body
        that copied the whole declaration into the matrix is what this reports."""
        tree = self._tree({"alpha": True, "bravo": True})
        result, emitted = self._run(tree)
        self.assertEqual(0, result.returncode, self._combined(result)[-800:])
        offenders = sorted(
            name for name in ("HCLOUD_TOKEN_ALPHA", "HCLOUD_TOKEN_BRAVO") if name in emitted
        )
        self.assertEqual(
            [],
            offenders,
            "the emitted matrix carries a per-stack secret name, so a deploy row reaches "
            f"a secret by a name derived from its stack: {offenders}",
        )


# --------------------------------------------------------------------------
# The reads above are reads
# --------------------------------------------------------------------------


def _workflow(**overrides) -> dict:
    """A conforming platform-deploy workflow, in the smallest shape every
    predicate in this file reads.

    Built here rather than taken from the committed file, which does not yet have
    this shape -- and which is what the predicates are pointed at, so a fixture
    copied from it could not falsify them.
    """
    workflow = {
        "jobs": {
            "discover": {
                "runs-on": "ubuntu-24.04",
                "outputs": {"stacks": "${{ steps.read.outputs.stacks }}"},
                "steps": [
                    {"id": "read", "run": 'find terraform/stacks -type d >>"$GITHUB_OUTPUT"\n'}
                ],
            },
            "diff": {
                "runs-on": "ubuntu-24.04",
                "needs": "discover",
                "steps": [{"run": 'git diff >>"$GITHUB_STEP_SUMMARY"\n'}],
            },
            "deploy": {
                "runs-on": "ubuntu-24.04",
                "needs": ["discover", "diff"],
                "environment": "${{ matrix.stack.github_environment }}",
                "concurrency": {
                    "group": "platform-deploy-${{ matrix.stack.name }}",
                    "cancel-in-progress": False,
                },
                "strategy": {
                    "fail-fast": False,
                    "matrix": {"stack": "${{ fromJSON(needs.discover.outputs.stacks) }}"},
                },
                "steps": [
                    {
                        "name": "Establish the secret set",
                        "env": {
                            "PLATFORM_DEPLOY_HOST": "${{ secrets.PLATFORM_DEPLOY_HOST }}",
                            "PLATFORM_DEPLOY_SSH_KEY": "${{ secrets.PLATFORM_DEPLOY_SSH_KEY }}",
                            "PLATFORM_ACME_EMAIL": "${{ secrets.PLATFORM_ACME_EMAIL }}",
                        },
                        "run": 'for name in $NAMES; do [ -n "${!name}" ] || '
                        'missing="$missing $name"; done\n',
                    },
                    {"name": "Join the tailnet", "uses": "tailscale/github-action@v3"},
                    {"name": "Render the environment file", "run": "printenv >.env\n"},
                    {"name": "Deliver", "run": 'tar c . | ssh deploy@"$HOST" tar x\n'},
                ],
            },
        }
    }
    workflow.update(overrides)
    return workflow


def _deploy(workflow: dict) -> dict:
    return workflow["jobs"]["deploy"]


class TestTheseReadsDiscriminate(unittest.TestCase):
    """Every read in this file is a static read of a committed file, so a green run
    establishes nothing on its own: a predicate that reported no offence whatever
    it was given would satisfy every assertion above, and would do so most
    convincingly on the day the implementation landed.

    Each test below hands a predicate material built to falsify it, supplied by
    this file rather than taken from the tree -- which is also what keeps these
    fixtures out of the sweeps' own reach, since nothing here is a committed
    workflow naming a stack.

    This class is expected to pass from the moment it is written, which is the
    opposite of most of this file and is stated so that its passing is not
    mistaken for coverage of the change.
    """

    REQUIRED = {"PLATFORM_DEPLOY_HOST", "PLATFORM_DEPLOY_SSH_KEY", "PLATFORM_ACME_EMAIL"}

    # -- the opt-in reader ------------------------------------------------

    def test_an_absent_opt_in_reads_as_not_deployed_to(self) -> None:
        self.assertEqual((None, None), platform_opt_in({"github_environment": "x"}))

    def test_a_declared_opt_in_reads_as_declared(self) -> None:
        self.assertEqual((True, None), platform_opt_in({"deploys_platform": True}))
        self.assertEqual((False, None), platform_opt_in({"deploys_platform": False}))

    def test_a_non_boolean_opt_in_is_an_offence_rather_than_a_value(self) -> None:
        value, offence = platform_opt_in({"deploys_platform": "maybe"})
        self.assertIsNone(value)
        self.assertIn("not a boolean", offence or "")

    def test_two_fields_naming_the_opt_in_are_ambiguous(self) -> None:
        value, offence = platform_opt_in({"deploys_platform": True, "platform_excluded": False})
        self.assertIsNone(value)
        self.assertIn("ambiguous", offence or "")

    # -- the vault-tolerant loader ----------------------------------------

    def test_a_vaulted_group_vars_file_is_read_rather_than_refused(self) -> None:
        """The reason this loader exists: `yaml.safe_load` refuses `!vault`, and a
        reader built on it would fail on the very files this module reads."""
        directory = Path(tempfile.mkdtemp(prefix="group-vars-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "staging.yml"
        path.write_text(
            "deploy_apps:\n  - name: platform\n    public_key: ssh-ed25519 AAAA\n"
            "ghcr_pull_token: !vault |\n  $ANSIBLE_VAULT;1.2;AES256;staging\n  3333\n",
            encoding="utf-8",
        )
        self.assertEqual(
            {"platform"},
            {entry["name"] for entry in group_variables(path)[DEPLOY_APPS_FIELD]},
        )

    def test_an_unknown_tag_refuses_rather_than_yielding_an_empty_document(self) -> None:
        """The rule this loader copies, asserted rather than inherited. A catch-all
        multi-constructor would map an unknown tag to `None`, and `deploy_apps`
        read out of an empty document is an absent list -- so the cross-check would
        pass vacuously on the very pair it compares, failing open on the one guard
        this change adds."""
        directory = Path(tempfile.mkdtemp(prefix="group-vars-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "production.yml"
        path.write_text("deploy_apps: !something\n  - name: platform\n", encoding="utf-8")
        with self.assertRaises(UnreadableGroupVars):
            group_variables(path)

    # -- the declaration/authorisation cross-check ------------------------

    def test_an_opt_in_without_an_authorisation_is_reported(self) -> None:
        offences = deploy_authorisation_offences(
            {"main-staging": True}, {"main-staging": "staging"}, {"staging": {"someapp"}}
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn("terraform/stacks/main-staging/pipeline.yml", offences[0])
        self.assertIn("ansible/inventory/group_vars/staging.yml", offences[0])

    def test_an_opt_in_whose_group_has_no_group_vars_file_is_reported(self) -> None:
        offences = deploy_authorisation_offences(
            {"main-staging": True}, {"main-staging": "staging"}, {"production": {"platform"}}
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn("does not exist", offences[0])

    def test_an_opt_in_declaring_no_group_is_reported(self) -> None:
        offences = deploy_authorisation_offences(
            {"main-staging": True}, {"main-staging": None}, {"staging": {"platform"}}
        )
        self.assertEqual(1, len(offences), offences)

    def test_an_authorised_host_whose_stack_opts_in_is_not_reported(self) -> None:
        self.assertEqual(
            [],
            deploy_authorisation_offences(
                {"main-staging": True}, {"main-staging": "staging"}, {"staging": {"platform"}}
            ),
        )

    def test_the_implication_holds_in_one_direction_only(self) -> None:
        """A host prepared before its deploy path exists is the deliberate state
        the change's design.md Decision 2 is built on, and a check that reported it
        would be repaired by removing the authorisation -- which is the opposite of
        what the requirement asks for."""
        self.assertEqual(
            [],
            deploy_authorisation_offences(
                {"main-staging": False, "main-production": None},
                {"main-staging": "staging", "main-production": "production"},
                {"staging": {"platform"}, "production": {"platform"}},
            ),
        )

    # -- the stack-name sweep ---------------------------------------------

    def test_a_workflow_naming_a_stack_is_reported(self) -> None:
        offences = stack_name_occurrences(
            "jobs:\n  deploy:\n    environment: main-production\n",
            ["main-production", "production"],
            "platform-deploy.yml",
        )
        self.assertEqual(["platform-deploy.yml:3 names `main-production`"], offences)

    def test_a_workflow_naming_no_stack_is_not_reported(self) -> None:
        self.assertEqual(
            [],
            stack_name_occurrences(
                "    environment: ${{ matrix.stack.github_environment }}\n",
                ["main-production", "production", "staging"],
                "platform-deploy.yml",
            ),
        )

    def test_a_longer_name_is_not_read_as_a_shorter_one(self) -> None:
        """`production` is a declared Ansible group and `main-production` a declared
        Environment; a sweep that matched the first inside the second would report
        two offences for one occurrence, and would go red on text naming neither."""
        self.assertEqual(
            ["platform-deploy.yml:1 names `main-production`"],
            stack_name_occurrences(
                "main-production\n", ["main-production", "production"], "platform-deploy.yml"
            ),
        )

    # -- the gate ---------------------------------------------------------

    def test_a_conforming_workflow_reports_no_gate_offence(self) -> None:
        self.assertEqual([], gate_offences(_workflow(), {"main-production": "main-production"}))

    def test_a_literal_environment_is_reported(self) -> None:
        workflow = _workflow()
        _deploy(workflow)["environment"] = "main-production"
        offences = gate_offences(workflow, {"main-production": "main-production"})
        self.assertEqual(1, len(offences), offences)
        self.assertIn("literal", offences[0])

    def test_an_environment_no_stack_declares_is_reported_with_that_fact(self) -> None:
        workflow = _workflow()
        _deploy(workflow)["environment"] = "production"
        offences = gate_offences(workflow, {"main-production": "main-production"})
        self.assertIn("no stack", offences[0])

    def test_an_expression_reading_no_matrix_value_is_reported(self) -> None:
        workflow = _workflow()
        _deploy(workflow)["environment"] = "${{ vars.DEPLOY_ENVIRONMENT }}"
        offences = gate_offences(workflow, {"main-production": "main-production"})
        self.assertIn("reading no matrix value", offences[0])

    def test_a_matrix_written_in_workflow_text_is_reported(self) -> None:
        workflow = _workflow()
        _deploy(workflow)["strategy"]["matrix"] = {
            "stack": [{"name": "main-production", "github_environment": "main-production"}]
        }
        offences = gate_offences(workflow, {"main-production": "main-production"})
        self.assertIn("written in workflow text", offences[0])

    def test_a_workflow_gating_nothing_is_reported(self) -> None:
        workflow = _workflow()
        _deploy(workflow).pop("environment")
        self.assertIn("no job", gate_offences(workflow, {"a": "b"})[0])

    # -- ordering ---------------------------------------------------------

    def test_a_conforming_workflow_reports_no_ordering_offence(self) -> None:
        self.assertEqual([], ordering_offences(_workflow()))

    def test_the_default_fail_fast_is_reported(self) -> None:
        workflow = _workflow()
        _deploy(workflow)["strategy"].pop("fail-fast")
        self.assertIn("fail-fast", ordering_offences(workflow)[0])

    def test_max_parallel_is_reported(self) -> None:
        workflow = _workflow()
        _deploy(workflow)["strategy"]["max-parallel"] = 1
        self.assertIn("max-parallel", ordering_offences(workflow)[0])

    def test_a_dependency_between_two_deploy_rows_is_reported(self) -> None:
        workflow = _workflow()
        workflow["jobs"]["deploy-second"] = {
            "needs": ["discover", "diff", "deploy"],
            "environment": "${{ matrix.stack.github_environment }}",
            "strategy": {
                "fail-fast": False,
                "matrix": {"stack": "${{ fromJSON(needs.discover.outputs.stacks) }}"},
            },
            "steps": [],
        }
        offences = ordering_offences(workflow)
        self.assertTrue(any("sequenced behind" in offence for offence in offences), offences)

    def test_a_workflow_with_no_discovered_matrix_is_reported(self) -> None:
        workflow = _workflow()
        _deploy(workflow)["strategy"]["matrix"] = {"stack": ["main-production"]}
        self.assertIn("no job", ordering_offences(workflow)[0])

    # -- serialisation ----------------------------------------------------

    def test_a_conforming_workflow_reports_no_serialisation_offence(self) -> None:
        self.assertEqual([], serialisation_offences(_workflow()))

    def test_a_workflow_level_group_is_reported(self) -> None:
        workflow = _workflow(concurrency="platform-deploy")
        self.assertIn("workflow-level", serialisation_offences(workflow)[0])

    def test_a_group_naming_no_matrix_value_is_reported(self) -> None:
        workflow = _workflow()
        _deploy(workflow)["concurrency"]["group"] = "platform-deploy"
        self.assertIn("names no matrix value", serialisation_offences(workflow)[0])

    def test_cancelling_the_first_of_two_merges_is_reported(self) -> None:
        workflow = _workflow()
        _deploy(workflow)["concurrency"]["cancel-in-progress"] = True
        self.assertIn("cancel-in-progress", serialisation_offences(workflow)[0])

    def test_no_group_at_all_is_reported(self) -> None:
        workflow = _workflow()
        _deploy(workflow).pop("concurrency")
        self.assertIn("no `concurrency` group", serialisation_offences(workflow)[0])

    # -- confinement ------------------------------------------------------

    def test_a_conforming_workflow_reports_no_confinement_offence(self) -> None:
        self.assertEqual([], confinement_offences(_workflow(), {"PLATFORM_DEPLOY_SSH_KEY"}))

    def test_an_ungated_job_reading_a_confined_secret_is_reported(self) -> None:
        workflow = _workflow()
        workflow["jobs"]["diff"]["steps"][0]["env"] = {
            "KEY": "${{ secrets.PLATFORM_DEPLOY_SSH_KEY }}"
        }
        offences = confinement_offences(workflow, {"PLATFORM_DEPLOY_SSH_KEY"})
        self.assertEqual(1, len(offences), offences)
        self.assertIn("diff", offences[0])

    # -- the diff job -----------------------------------------------------

    def test_a_conforming_workflow_reports_no_diff_offence(self) -> None:
        self.assertEqual([], diff_offences(_workflow()))

    def test_a_second_publishing_job_is_reported(self) -> None:
        workflow = _workflow()
        workflow["jobs"]["diff-again"] = {
            "needs": "discover",
            "steps": [{"run": 'echo x >>"$GITHUB_STEP_SUMMARY"\n'}],
        }
        self.assertTrue(
            any("all write to the run summary" in offence for offence in diff_offences(workflow))
        )

    def test_a_publishing_job_holding_a_credential_is_reported(self) -> None:
        workflow = _workflow()
        workflow["jobs"]["diff"]["steps"][0]["env"] = {
            "KEY": "${{ secrets.PLATFORM_DEPLOY_SSH_KEY }}"
        }
        self.assertTrue(any("credential-free" in offence for offence in diff_offences(workflow)))

    def test_a_publishing_job_behind_the_gate_is_reported(self) -> None:
        workflow = _workflow()
        workflow["jobs"]["diff"]["environment"] = "${{ matrix.stack.github_environment }}"
        self.assertTrue(
            any("already passed the gate" in offence for offence in diff_offences(workflow))
        )

    def test_a_deploy_row_not_waiting_for_the_diff_is_reported(self) -> None:
        workflow = _workflow()
        _deploy(workflow)["needs"] = ["discover"]
        self.assertTrue(
            any("can be reached before the diff" in offence for offence in diff_offences(workflow))
        )

    def test_a_workflow_publishing_nothing_is_reported(self) -> None:
        workflow = _workflow()
        workflow["jobs"].pop("diff")
        self.assertIn("no job writes", diff_offences(workflow)[0])

    # -- the secret set ---------------------------------------------------

    def test_a_conforming_deploy_reports_no_secret_set_offence(self) -> None:
        self.assertEqual([], secret_set_offences(_deploy(_workflow()), self.REQUIRED))

    def test_a_check_reading_only_part_of_the_set_is_reported(self) -> None:
        workflow = _workflow()
        _deploy(workflow)["steps"][0]["env"].pop("PLATFORM_ACME_EMAIL")
        offences = secret_set_offences(_deploy(workflow), self.REQUIRED)
        self.assertEqual(1, len(offences), offences)
        self.assertIn("PLATFORM_ACME_EMAIL", offences[0])

    def test_a_check_that_runs_after_the_tailnet_join_is_reported(self) -> None:
        workflow = _workflow()
        job_steps = _deploy(workflow)["steps"]
        job_steps[0], job_steps[1] = job_steps[1], job_steps[0]
        offences = secret_set_offences(_deploy(workflow), self.REQUIRED)
        self.assertTrue(any("join the tailnet" in offence for offence in offences), offences)

    def test_a_check_that_runs_after_the_env_is_rendered_is_reported(self) -> None:
        workflow = _workflow()
        job_steps = _deploy(workflow)["steps"]
        job_steps.insert(0, job_steps.pop(2))
        offences = secret_set_offences(_deploy(workflow), self.REQUIRED)
        self.assertTrue(any("render .env" in offence for offence in offences), offences)

    def test_an_empty_required_set_is_reported_rather_than_satisfied(self) -> None:
        self.assertIn("read nothing", secret_set_offences(_deploy(_workflow()), set())[0])

    # -- disclosure -------------------------------------------------------

    def test_a_refusal_naming_the_empty_secrets_is_not_reported(self) -> None:
        step = {
            "env": {"PLATFORM_ACME_EMAIL": "${{ secrets.PLATFORM_ACME_EMAIL }}"},
            "run": 'for name in $NAMES; do [ -n "${!name}" ] || missing="$missing $name"; '
            'done\necho "::error::these secrets resolved empty: $missing"\n',
        }
        self.assertEqual([], disclosure_offences(step, self.REQUIRED))

    def test_a_printed_value_is_reported(self) -> None:
        step = {"run": 'echo "host is $PLATFORM_DEPLOY_HOST"\n'}
        offences = disclosure_offences(step, self.REQUIRED)
        self.assertEqual(1, len(offences), offences)
        self.assertIn("PLATFORM_DEPLOY_HOST", offences[0])

    def test_an_indirectly_printed_value_is_reported(self) -> None:
        step = {"run": 'for name in $NAMES; do echo "${!name}"; done\n'}
        self.assertIn("indirectly expanded", disclosure_offences(step, self.REQUIRED)[0])

    def test_reading_a_value_is_not_printing_it(self) -> None:
        step = {"run": '[ -n "${!name}" ] || missing="$missing $name"\n'}
        self.assertEqual([], disclosure_offences(step, self.REQUIRED))

    def test_an_interpolated_secret_expression_in_a_shell_body_is_reported(self) -> None:
        step = {"run": 'test -n "${{ secrets.PLATFORM_DEPLOY_SSH_KEY }}"\n'}
        self.assertIn("interpolates", disclosure_offences(step, self.REQUIRED)[0])

    def test_a_commented_out_disclosure_is_not_reported(self) -> None:
        step = {"run": '# echo "$PLATFORM_DEPLOY_HOST"\n'}
        self.assertEqual([], disclosure_offences(step, self.REQUIRED))

    # -- the tailnet, the account and the keys ----------------------------

    def test_a_conforming_deploy_reports_no_tailnet_or_account_offence(self) -> None:
        self.assertEqual([], tailnet_ordering_offences(_workflow()))
        self.assertEqual([], deploy_account_offences(_workflow()))

    def test_an_ssh_attempt_before_the_tailnet_join_is_reported(self) -> None:
        workflow = _workflow()
        job_steps = _deploy(workflow)["steps"]
        job_steps.insert(0, job_steps.pop(3))
        self.assertIn("before the private path", tailnet_ordering_offences(workflow)[0])

    def test_a_job_that_joins_no_tailnet_is_reported(self) -> None:
        workflow = _workflow()
        _deploy(workflow)["steps"].pop(1)
        self.assertIn("joins no tailnet", tailnet_ordering_offences(workflow)[0])

    def test_a_connection_as_another_account_is_reported(self) -> None:
        workflow = _workflow()
        _deploy(workflow)["steps"][3]["run"] = 'tar c . | ssh root@"$HOST" tar x\n'
        offences = deploy_account_offences(workflow)
        self.assertEqual(1, len(offences), offences)
        self.assertIn("root@", offences[0])

    def test_a_known_hosts_step_is_not_read_as_a_connection(self) -> None:
        """The committed deploy runs `ssh-keyscan` against the host BEFORE it
        connects. A matcher stopping at a word boundary reads that as an SSH
        invocation, finds no `deploy@` on it, and fails the deploy-account
        assertion for a reason the requirement does not state -- which is a defect
        in the test rather than in the workflow, and was one here until this case
        was written."""
        workflow = _workflow()
        _deploy(workflow)["steps"].insert(
            3, {"name": "Known hosts", "run": 'ssh-keyscan -H "$HOST" >>~/.ssh/known_hosts\n'}
        )
        self.assertEqual([], deploy_account_offences(workflow))

    def test_two_hosts_authorising_one_key_are_reported(self) -> None:
        offences = shared_key_offences({"production": "ssh-ed25519 AAAA", "staging": "ssh-ed25519 AAAA"})
        self.assertEqual(1, len(offences), offences)
        self.assertIn("production", offences[0])
        self.assertIn("staging", offences[0])

    def test_two_hosts_authorising_two_keys_are_not_reported(self) -> None:
        self.assertEqual(
            [],
            shared_key_offences(
                {"production": "ssh-ed25519 AAAA", "staging": "ssh-ed25519 BBBB"}
            ),
        )

    def test_no_authorised_key_at_all_is_reported_rather_than_passed_over(self) -> None:
        self.assertIn("reads nothing", shared_key_offences({})[0])

    def test_a_committed_env_file_is_reported(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="platform-tree-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        (directory / "platform").mkdir()
        (directory / "platform" / ".env.example").write_text("ACME_EMAIL=\n", encoding="utf-8")
        self.assertEqual([], committed_env_files(directory))
        (directory / "platform" / ".env").write_text("ACME_EMAIL=a@b.c\n", encoding="utf-8")
        self.assertEqual(["platform/.env"], committed_env_files(directory))

    def test_an_encrypted_env_file_is_reported_too(self) -> None:
        """"in any form, plaintext or encrypted" -- a name the finder matched only
        exactly would pass over the vaulted spelling, which is the form somebody
        reaching for a committed secret would most plausibly use."""
        directory = Path(tempfile.mkdtemp(prefix="platform-tree-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        (directory / "platform").mkdir()
        (directory / "platform" / ".env.vault").write_text("$ANSIBLE_VAULT;1.2\n", encoding="utf-8")
        self.assertEqual(["platform/.env.vault"], committed_env_files(directory))

    # -- the secret-set resolution ----------------------------------------

    def test_a_variable_no_secret_is_read_for_is_reported(self) -> None:
        resolved, offences = rendered_secret_resolution(
            {"PLATFORM_ACME_EMAIL"}, ["ACME_EMAIL", "GRAFANA_ADMIN_PASSWORD"]
        )
        self.assertEqual({"ACME_EMAIL": "PLATFORM_ACME_EMAIL"}, resolved)
        self.assertEqual(1, len(offences), offences)
        self.assertIn("GRAFANA_ADMIN_PASSWORD", offences[0])

    def test_a_variable_two_secrets_match_is_reported(self) -> None:
        _, offences = rendered_secret_resolution(
            {"PLATFORM_ACME_EMAIL", "STAGING_ACME_EMAIL"}, ["ACME_EMAIL"]
        )
        self.assertEqual(1, len(offences), offences)
        self.assertIn("more than one", offences[0])

    def test_the_derived_value_is_the_one_excluded_from_the_set(self) -> None:
        """The committed `.env.example` is read rather than a list written here, so
        this is the assertion that says which variable the exclusion reaches -- and
        goes red if a second variable is ever given a name carrying the same
        hint."""
        excluded = sorted(set(env_example_variables()) - set(secret_backed_variables()))
        self.assertEqual(["GRAFANA_BIND_ADDRESS"], excluded)
