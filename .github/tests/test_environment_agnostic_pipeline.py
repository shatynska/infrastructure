"""Static-assertion tests for a pipeline that carries no environment literal.

Derived from the delta specs of the OpenSpec change
`make-the-pipeline-environment-agnostic`, before any implementation of that
change existed -- from that change's delta specifications at commit `fbef40d`,
which is the commit holding the approved plan. The path those deltas sit at is
not written here: a change's artifacts move when it is archived, and this
repository's citation convention is to name the change and the artifact in prose
instead. The deltas span two
capabilities, `iac-cicd-pipeline` and `iac-safety-hardening`; each section below
names the requirement it traces to. Every assertion is annotated SPECIFIED (it
traces to SHALL text or to a scenario in a delta spec) or DERIVED (it traces to
that change's `design.md` or `tasks.md` rather than to a scenario). See that
change's `test-plan.md` for the scenario-to-test mapping, the baseline, the
scenarios deliberately left uncovered, and the project questions this file took
an assumption on.

Why this is a fourth file in the suite rather than a section of
`test_ci_configuration.py`
--------------------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. Several assertions in `test_ci_configuration.py`
are superseded or strengthened by this change; re-expressing them is the
implementing author's task (that change's tasks.md 5.3 and 5.4) and is recorded
in `test-plan.md`'s obsolete list rather than performed here. Nothing in this
file edits, deletes or disables an existing test.

Two consequences of sitting here rather than there, both deliberate:

- `TestTheSuiteNeedsNoPrivilegedResource` in that file audits `Path(__file__)`
  -- its own module and no other -- so this file is not covered by it.
  `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in that same
  file DOES read every module in this directory, so this file is held to the
  no-network, no-credential, no-container, no-Terraform constraint by that
  class. It is written to satisfy it: standard library, `yaml`, the helpers of
  the module beside it, and `bash` as the only spawned command.
- Where this file needs a helper that file already has, it imports it rather
  than restating it, which is the idiom the two modules already beside it use.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_environment_agnostic_pipeline.TestNoWorkflowNamesAnEnvironment \\
        .test_no_terraform_workflow_names_an_environment_directory

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the helper import below resolve.

What no assertion here establishes
----------------------------------
Nothing in this file reads repository settings. Whether a GitHub Environment
exists, whether it requires a reviewer, which secrets it holds, and whether a
status check context is registered in branch protection are all settings rather
than repository content, and this suite makes no network call. The change's own
design.md names that boundary as a risk and says these tests "must not be
written to imply more". A green run here establishes that the committed files
are SHAPED so those settings can be applied safely, never that they were.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from test_ci_configuration import (
    AGENTS_FILE,
    APPLY,
    MANAGED_BLOCK_END,
    PR_VALIDATION,
    ROOT,
    WORKFLOWS,
    compact,
    flattened,
    github_output_pairs,
    jobs,
    load_yaml,
    read_text,
    require_external_tools,
    step_label,
    step_text,
    steps,
    triggers,
    uncommented,
)

# --------------------------------------------------------------------------
# Identifiers this file names, and why each is a constraint of the test layer
# rather than a property the specification states.
#
# `drift.yml` is the third workflow the change restructures and the only one
# `test_ci_configuration.py` does not already name. The delta speaks of "a
# scheduled GitHub Actions workflow"; this is what that resolves to here.
# --------------------------------------------------------------------------

DRIFT = WORKFLOWS / "drift.yml"

# The three workflows this change restructures: the validation workflow that
# plans on a pull request, the gated apply workflow, and the scheduled drift
# sweep. The ADDED requirement's prohibition is written over "any file under
# `.github/workflows/`", and the environment-literal assertions below are
# nonetheless SCOPED TO THESE THREE. That narrowing is deliberate and is stated
# rather than left to be inferred: the requirement's own sentence names "the
# validation, plan, apply and drift workflows" as what must cover a new
# environment, and a workflow outside this change's subject -- a host or
# platform deploy that legitimately addresses one host by name -- would be
# failed by a repository-wide sweep for a reason this change did not introduce
# and cannot fix. Widening the sweep is a reviewable decision, not an
# authoring one; see the change's test-plan.md.
TERRAFORM_WORKFLOWS = (PR_VALIDATION, APPLY, DRIFT)

ENVIRONMENTS_DIR = ROOT / "terraform" / "stacks"

# Suffixes an environment directory carries that are NOT its pipeline
# declaration. `.tf` and `.tfvars` are read by Terraform itself -- tasks.md 2.2
# requires the declaration not to be picked up as Terraform configuration, so a
# declaration carrying either suffix is a declaration in the wrong file.
NON_DECLARATION_SUFFIXES = frozenset(
    {".tf", ".tfvars", ".tfstate", ".tfplan", ".hcl", ".md", ".txt", ".backup"}
)

# How a declaration's three fields are identified.
#
# THIS IS AN UNRESOLVED PROJECT QUESTION, recorded in test-plan.md and repeated
# here because a reader of a red test needs it. The change's design.md Decision
# 1 fixes what the declaration must DECLARE -- the GitHub Environment name, the
# read-only secret name, and whether the destroy-policy gate applies -- and its
# tasks.md 2.1 assigns the file's name, format and field names to the
# implementing author. Neither is decided at the commit these tests were
# derived from.
#
# So no field name is asserted. Each field is resolved from the declaration's
# own keys: the gate by the one key whose name carries `destroy` and whose
# value is a boolean, the secret by a key naming a secret or a token, the
# Environment by a key naming an environment. Punctuation and case are
# normalised away, so `read_only_secret`, `read-only-secret` and
# `readOnlySecret` are one name.
#
# The gate's POLARITY cannot be read off a value, only off a name, which is why
# `destroy` is required rather than merely accepted: `disposable: true` and
# `destroy_policy_gate: true` are the same value and opposite meanings, and a
# declaration this suite read backwards would report prod's gate applicable
# while the workflow disabled it.
GATE_KEY_HINT = "destroy"
SECRET_KEY_HINTS = ("secret", "token")
ENVIRONMENT_KEY_HINT = "environment"

# Prod's own two declared values, asserted rather than assumed anywhere they
# matter.
#
# THE READ-ONLY NAME MOVED, AND THE OLD ONE WAS NOT MERELY RENAMED. This
# constant read `HCLOUD_TOKEN` under the change that introduced this module,
# justified by that change's "nothing in repository settings changes for N=1".
# `apply-host-configuration-through-a-gated-workflow` retired that premise: the
# host-converge job declares an `environment:` and reads the name this field
# states, and every Environment defines `HCLOUD_TOKEN` as its Read & Write
# token -- so the old value made a gated job resolve a write credential from a
# field that says read-only. Prod now declares a name no Environment shadows,
# and the rename is a repository-settings step that change's Migration Plan
# sequences around the merge.
#
# The assertion below is therefore re-pointed at the proposition that replaced
# it, not relaxed: prod still declares one specific secret and one specific
# Environment, and a declaration drifting from either still fails.
PROD_DIRECTORY = "prod"
PROD_READ_ONLY_SECRET = "HCLOUD_TOKEN_PRODUCTION"
PROD_GITHUB_ENVIRONMENT = "production"

TERRAFORM_PLAN = re.compile(r"terraform\s+plan\b")
TERRAFORM_APPLY = re.compile(r"terraform\s+apply\b")
ACTIONS_EXPRESSION = re.compile(r"\$\{\{")
SECRET_NAME = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")


# --------------------------------------------------------------------------
# Reading the per-environment declarations
# --------------------------------------------------------------------------


def _normalised(key: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


class Declaration:
    """One environment's pipeline declaration, or the reasons it is not one."""

    def __init__(self, name: str, path: Path | None, mapping: dict | None, offences: list[str]):
        self.name = name
        self.path = path
        self.mapping = mapping or {}
        self.offences = offences
        self.github_environment: str | None = None
        self.read_only_secret: str | None = None
        # Absent means applicable. The delta states it as a scenario -- "An
        # environment declaring nothing is gated" -- and design.md Decision 6
        # states it as the default: "a mistake in the declaration fails safe".
        self.destroy_gate_applies: bool = True


def environment_directories(root: Path | None = None) -> list[Path]:
    base = (ROOT if root is None else root) / "terraform" / "stacks"
    if not base.is_dir():
        return []
    return sorted(
        entry for entry in base.iterdir() if entry.is_dir() and not entry.name.startswith(".")
    )


def declaration_candidates(directory: Path) -> list[Path]:
    """Files in an environment directory that could be its declaration.

    Identified by shape rather than by name, because the name is not decided
    (see the note on the field hints above): a committed file Terraform does
    not read, which parses as a mapping. Every file prod's directory carries
    today -- `.tf`, `.tfvars`, the lockfile -- is excluded by suffix or fails to
    parse as a mapping, so this finds the declaration and nothing else.
    """
    found = []
    for entry in sorted(directory.iterdir()):
        if not entry.is_file() or entry.name.startswith("."):
            continue
        if entry.suffix.lower() in NON_DECLARATION_SUFFIXES:
            continue
        try:
            document = yaml.safe_load(entry.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError):
            continue
        if isinstance(document, dict):
            found.append(entry)
    return found


def _resolve_fields(declaration: Declaration) -> None:
    """Fill in the three fields, appending an offence for each one missing,
    ambiguous or of the wrong type."""
    remaining = dict(declaration.mapping)

    gate_keys = [key for key in remaining if GATE_KEY_HINT in _normalised(key)]
    if len(gate_keys) > 1:
        declaration.offences.append(
            f"{declaration.name}: more than one field names the destroy-policy gate "
            f"({sorted(map(str, gate_keys))}), so which one the pipeline reads is ambiguous"
        )
    elif gate_keys:
        key = gate_keys[0]
        value = remaining.pop(key)
        if not isinstance(value, bool):
            declaration.offences.append(
                f"{declaration.name}: field {key!r} states whether the destroy-policy "
                f"gate applies but is {value!r}, which is not a boolean; the pipeline "
                "reads applicability, not a description of it"
            )
        else:
            declaration.destroy_gate_applies = value

    secret_keys = [
        key
        for key in remaining
        if any(hint in _normalised(key) for hint in SECRET_KEY_HINTS)
    ]
    if len(secret_keys) != 1:
        declaration.offences.append(
            f"{declaration.name}: expected exactly one field naming the repository "
            "secret that holds this environment's read-only Hetzner token, found "
            f"{sorted(map(str, secret_keys))} among {sorted(map(str, declaration.mapping))}"
        )
    else:
        key = secret_keys[0]
        value = remaining.pop(key)
        if not isinstance(value, str) or not SECRET_NAME.match(value):
            declaration.offences.append(
                f"{declaration.name}: field {key!r} is {value!r}, which is not a "
                "GitHub secret name; a plan job indexes `secrets[...]` with it"
            )
        else:
            declaration.read_only_secret = value

    environment_keys = [key for key in remaining if ENVIRONMENT_KEY_HINT in _normalised(key)]
    if len(environment_keys) != 1:
        declaration.offences.append(
            f"{declaration.name}: expected exactly one field naming the GitHub "
            "Environment this environment's apply job attaches to, found "
            f"{sorted(map(str, environment_keys))} among {sorted(map(str, declaration.mapping))}"
        )
    else:
        value = remaining.pop(environment_keys[0])
        if not isinstance(value, str) or not value.strip():
            declaration.offences.append(
                f"{declaration.name}: field {environment_keys[0]!r} is {value!r}, "
                "which is not a GitHub Environment name"
            )
        else:
            declaration.github_environment = value


def environment_declarations(root: Path | None = None) -> dict[str, Declaration]:
    """Every environment directory mapped to its declaration, parsed."""
    found: dict[str, Declaration] = {}
    for directory in environment_directories(root):
        offences: list[str] = []
        candidates = declaration_candidates(directory)
        if not candidates:
            offences.append(
                f"{directory.name}: the directory carries no pipeline declaration, so "
                "this environment names no GitHub Environment, no read-only secret and "
                "no destroy-policy applicability, and the pipeline has nothing to "
                "discover"
            )
            found[directory.name] = Declaration(directory.name, None, None, offences)
            continue
        if len(candidates) > 1:
            offences.append(
                f"{directory.name}: more than one file reads as a pipeline declaration "
                f"({sorted(path.name for path in candidates)}), so which one the "
                "pipeline reads is ambiguous"
            )
        path = candidates[0]
        mapping = yaml.safe_load(path.read_text(encoding="utf-8"))
        declaration = Declaration(directory.name, path, mapping, offences)
        _resolve_fields(declaration)
        found[directory.name] = declaration
    return found


def declaration_offences(root: Path | None = None) -> list[str]:
    """Every reason the committed declarations would fail discovery.

    The census the ADDED requirement's four refusal scenarios are read against:
    an absent declaration, one missing a field the workflows read, two
    environments naming one read-only secret, and two naming one GitHub
    Environment. Takes `root` so the behaviour is exercisable against a fixture
    tree -- at N=1 every collision check is vacuous over the real repository,
    and a vacuous check is what
    `TestTheDeclarationCensusIsARealReadOfTheTree` exists to refuse.
    """
    declarations = environment_declarations(root)
    offences = [offence for declaration in declarations.values() for offence in declaration.offences]

    by_secret: dict[str, list[str]] = {}
    by_environment: dict[str, list[str]] = {}
    for name, declaration in sorted(declarations.items()):
        if declaration.read_only_secret:
            by_secret.setdefault(declaration.read_only_secret, []).append(name)
        if declaration.github_environment:
            by_environment.setdefault(declaration.github_environment, []).append(name)

    for secret, names in sorted(by_secret.items()):
        if len(names) > 1:
            offences.append(
                f"{', '.join(names)}: all declare {secret!r} as their read-only secret. "
                "A repository secret holds one value, so their plans would run under "
                "one credential against different Hetzner projects"
            )
    for environment, names in sorted(by_environment.items()):
        if len(names) > 1:
            offences.append(
                f"{', '.join(names)}: all declare the GitHub Environment "
                f"{environment!r}. They would share its write token and its protection "
                "rules, so an environment meant to be ungated would hold the reviewed "
                "environment's write credential"
            )
    return sorted(offences)


# --------------------------------------------------------------------------
# Reading the workflows
# --------------------------------------------------------------------------


def invocation_lines(script: object, pattern: re.Pattern) -> list[str]:
    """The lines of a shell body that CALL what `pattern` names.

    A message about a command is not a call of it, and the distinction is not
    pedantic here: `drift.yml` reports a failed plan with
    `echo "::error::terraform plan failed ..."`, and a matcher reading the body
    as text finds a `terraform plan` in it. Read as a plan step, that line
    carries no `-lock=false` and no saved plan file, so every assertion about
    how this repository plans would fail against a step that plans nothing.

    Two exclusions, both narrow: a line whose match sits inside an unclosed
    quote is a string being printed rather than a command, and a line that is a
    shell comment is not run at all.
    """
    found = []
    for raw in str(script).splitlines():
        line = raw.strip()
        if line.startswith("#"):
            continue
        match = pattern.search(line)
        if not match:
            continue
        prefix = line[: match.start()]
        if prefix.count('"') % 2 or prefix.count("'") % 2:
            continue
        found.append(line)
    return found


def invoking_steps(job: dict, pattern: re.Pattern):
    """(index, step, lines) for each step of a job that calls `pattern`."""
    for index, step in enumerate(job.get("steps") or []):
        lines = invocation_lines(step.get("run", ""), pattern)
        if lines:
            yield index, step, lines


def jobs_running(workflow: dict, pattern: re.Pattern) -> dict:
    """Job key -> job, for every job with a `run:` step that CALLS `pattern`."""
    return {
        name: job
        for name, job in jobs(workflow).items()
        if any(True for _ in invoking_steps(job, pattern))
    }


def declared_environment(job: dict) -> str | None:
    """A job's `environment:`, in either the scalar or the mapping spelling."""
    value = job.get("environment")
    if isinstance(value, dict):
        return str(value.get("name", ""))
    return None if value is None else str(value)


def expression_free_run_steps(job: dict):
    """(index, step) for each `run:` step whose body carries no `${{ }}`.

    The shape tasks.md 3.4 requires of every body this suite must execute, and
    the reason `ansible-verify.yml`'s own gate and discovery tests can exist:
    an expression is interpolated before the step runs, so a body carrying one
    cannot be pulled out of the workflow and run.
    """
    for index, step in enumerate(job.get("steps") or []):
        if step.get("run") and not ACTIONS_EXPRESSION.search(str(step["run"])):
            yield index, step


def matrix_source_jobs(workflow: dict, job: dict) -> list[str]:
    """The jobs whose outputs a matrix expression is built from."""
    expression = compact((job.get("strategy") or {}).get("matrix"))
    return sorted(set(re.findall(r"needs\.([A-Za-z0-9_-]+)\.outputs\.", expression)))


def needs_of(job: dict) -> list[str]:
    needs = job.get("needs")
    if needs is None:
        return []
    return [str(needs)] if isinstance(needs, str) else [str(entry) for entry in needs]


def run_snippet(script: str, environment: dict, cwd: Path) -> subprocess.CompletedProcess:
    """Execute a workflow step's body the way the runner would, minus the
    runner: `bash -e`, a scratch `$GITHUB_OUTPUT`, and nothing else."""
    return subprocess.run(
        ["bash", "-e", "-c", script],
        cwd=str(cwd),
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Each Environment Declares Its Own Pipeline Configuration
# (ADDED)
# --------------------------------------------------------------------------


class TestEveryEnvironmentCarriesAPipelineDeclaration(unittest.TestCase):
    """ADDED requirement: Each Environment Declares Its Own Pipeline
    Configuration.

    The static half of the four refusal scenarios: what the committed tree
    says. Discovery's own refusal -- that the workflow FAILS on each of these
    -- is exercised by `TestDiscoveryFailsClosed` below, which runs the
    workflow's discovery body rather than reading it.
    """

    def setUp(self) -> None:
        self.directories = environment_directories()
        self.declarations = environment_declarations()

    def test_the_repository_has_at_least_one_environment(self) -> None:
        """SPECIFIED -- scenario "Discovery finding no environment fails rather
        than reporting success", read against the committed tree. Guards every
        other assertion in this class from passing over an empty set."""
        self.assertTrue(
            self.directories,
            f"{ENVIRONMENTS_DIR} holds no environment directory, so every assertion "
            "about the declarations would pass having read nothing",
        )

    def test_every_environment_directory_carries_a_declaration(self) -> None:
        """SPECIFIED -- "Every directory under `terraform/stacks/` SHALL
        carry a committed, machine-readable file declaring the pipeline
        configuration for that environment"."""
        self.test_the_repository_has_at_least_one_environment()
        missing = sorted(
            name for name, declaration in self.declarations.items() if declaration.path is None
        )
        self.assertEqual(
            [],
            missing,
            "these environment directories carry no machine-readable pipeline "
            f"declaration: {missing}. An environment the pipeline cannot read a "
            "declaration for is planned by nothing, applied by nothing and "
            "drift-checked by nothing",
        )

    def test_every_declaration_names_all_three_fields(self) -> None:
        """SPECIFIED -- the declaration states "the name of the GitHub
        Environment its apply job attaches to, the name of the repository
        secret holding its read-only Hetzner token, and whether the Destroy
        Policy Gate applies to it".

        The third is optional and defaults to applicable, per the scenario "An
        environment declaring nothing is gated"; the first two are what the
        scenario "An environment missing its declaration fails the pipeline"
        calls "a field the workflows read", since neither has a safe default.
        """
        self.test_the_repository_has_at_least_one_environment()
        for name, declaration in sorted(self.declarations.items()):
            with self.subTest(environment=name):
                self.assertEqual(
                    [],
                    declaration.offences,
                    f"the declaration for `{name}` is not one this pipeline can read: "
                    + "; ".join(declaration.offences),
                )

    def test_no_declaration_is_a_file_terraform_reads(self) -> None:
        """DERIVED (tasks.md 2.2) -- no scenario states it. The requirement
        obliges a "committed, machine-readable file" and says nothing about
        which one; that the file must not be picked up as Terraform
        configuration is the task's own verification condition, because a
        declaration written into a `.tf` or an auto-loaded `.tfvars` would
        change what `terraform validate` and `terraform plan` see. Reconsider
        this assertion, do not weaken it, if the declaration is made invisible
        to Terraform by another means."""
        self.test_every_environment_directory_carries_a_declaration()
        offenders = sorted(
            f"{name} -> {declaration.path.name}"
            for name, declaration in self.declarations.items()
            if declaration.path is not None
            and declaration.path.suffix.lower() in {".tf", ".tfvars"}
        )
        self.assertEqual(
            [],
            offenders,
            f"these declarations are files Terraform itself reads: {offenders}",
        )

    def test_no_two_environments_declare_the_same_read_only_secret(self) -> None:
        """SPECIFIED -- scenario "Two environments declaring the same read-only
        secret are refused", and "Each environment's declared read-only secret
        name SHALL be distinct from every other environment's".

        At one environment this comparison has nothing to compare, which is why
        `TestTheDeclarationCensusIsARealReadOfTheTree` runs the same census
        over a two-environment fixture. This assertion is what carries it into
        the committed tree once there is a second environment.
        """
        self.test_the_repository_has_at_least_one_environment()
        offenders = [
            offence for offence in declaration_offences() if "read-only secret" in offence
        ]
        self.assertEqual([], offenders, "; ".join(offenders))

    def test_no_two_environments_declare_the_same_github_environment(self) -> None:
        """SPECIFIED -- scenario "Two environments declaring the same GitHub
        Environment are refused", and "so SHALL its declared GitHub Environment
        name"."""
        self.test_the_repository_has_at_least_one_environment()
        offenders = [
            offence for offence in declaration_offences() if "GitHub Environment" in offence
        ]
        self.assertEqual([], offenders, "; ".join(offenders))

    def test_prod_declares_the_secret_and_environment_it_already_uses(self) -> None:
        """SPECIFIED -- Credential Scoping by Privilege places each
        environment's Read Only token in "the read-only secret named by the
        environment's own pipeline declaration", and Gated Production Apply
        requires the `production` Environment.

        The method's NAME is now half wrong and is left alone deliberately: prod
        declares the Environment it already uses and a read-only secret it does
        not, `HCLOUD_TOKEN_PRODUCTION` having been created by
        `apply-host-configuration-through-a-gated-workflow`'s Migration Plan.
        Renaming the method would cost every reference to it in that change's
        record and in this module's own history for no assertion gained. What
        the assertion establishes is unchanged in kind: prod's declaration names
        one specific secret and one specific Environment, and drift in either
        fails. See `PROD_READ_ONLY_SECRET` above for why the value moved.
        """
        self.assertIn(
            PROD_DIRECTORY,
            self.declarations,
            f"there is no `{PROD_DIRECTORY}` environment directory; this change is "
            "verifiable at one environment only because prod is that one",
        )
        declaration = self.declarations[PROD_DIRECTORY]
        self.assertEqual(
            PROD_READ_ONLY_SECRET,
            declaration.read_only_secret,
            f"prod declares {declaration.read_only_secret!r} as its read-only secret "
            f"rather than {PROD_READ_ONLY_SECRET!r}, so the repository secret that "
            "exists today would have to be renamed in the same instant as the merge",
        )
        self.assertEqual(
            PROD_GITHUB_ENVIRONMENT,
            declaration.github_environment,
            f"prod declares {declaration.github_environment!r} as its GitHub "
            f"Environment rather than {PROD_GITHUB_ENVIRONMENT!r}, which is the "
            "Environment holding the reviewer and the read-write token today",
        )

    def test_prod_declares_the_destroy_policy_gate_applicable(self) -> None:
        """SPECIFIED -- Destroy Policy Gate: "It SHALL apply to `prod`"."""
        self.assertIn(PROD_DIRECTORY, self.declarations, "no prod environment directory")
        declaration = self.declarations[PROD_DIRECTORY]
        # Without this, the assertion below passes over an environment with no
        # declaration at all: applicability defaults to true, so "prod is
        # gated" and "prod declares nothing" are the same answer. The default
        # is what the delta requires (scenario "An environment declaring
        # nothing is gated") and is exercised as such against a fixture; here it
        # would be a green test reporting on a file that does not exist.
        self.assertIsNotNone(
            declaration.path,
            "prod carries no pipeline declaration, so its destroy-policy applicability "
            "is this suite's default rather than anything the repository states",
        )
        self.assertTrue(
            declaration.destroy_gate_applies,
            "prod's declaration does not state the destroy-policy gate as applicable, "
            "so a plan replacing the production server would reach the Environment's "
            "protection rules with no override label and no objection raised",
        )


class DeclarationTreeFixtureMixin:
    """Builds a synthetic `terraform/stacks/` tree.

    The declarations it writes are built from PROD'S OWN declaration -- same
    filename, same field names, different values -- rather than from a spelling
    this file invented. The declaration's name, format and field names are the
    implementing author's to choose (tasks.md 2.1), so a fixture that hard-coded
    any of them would fail on a legitimate choice and would be repaired by
    editing the test, which is the one repair this suite must not need.
    """

    def _template(self):
        declarations = environment_declarations()
        prod = declarations.get(PROD_DIRECTORY)
        if prod is None or prod.path is None:
            self.fail(
                "prod carries no pipeline declaration, so this fixture has no committed "
                "declaration to take its filename and field names from. Write prod's "
                "declaration first; these fixtures follow whatever shape it takes"
            )
        return prod.path.name, dict(prod.mapping), prod

    def _key_for(self, mapping: dict, resolve) -> str:
        for key in mapping:
            if resolve(_normalised(key)):
                return key
        self.fail(f"prod's declaration carries no field among {sorted(map(str, mapping))}")

    def _write_tree(self, directory: Path, environments: dict) -> None:
        """`environments` maps a directory name to the declaration mapping it
        gets, or to None for a directory carrying no declaration at all."""
        filename, _, _ = self._template()
        base = directory / "terraform" / "stacks"
        base.mkdir(parents=True, exist_ok=True)
        for name, mapping in environments.items():
            environment_directory = base / name
            environment_directory.mkdir(parents=True, exist_ok=True)
            (environment_directory / "main.tf").write_text(
                'module "server" {\n  source = "../../modules/server"\n}\n', encoding="utf-8"
            )
            if mapping is None:
                continue
            (environment_directory / filename).write_text(
                yaml.safe_dump(mapping, sort_keys=True), encoding="utf-8"
            )

    def _declaration_for(self, secret: str, environment: str, gate: bool | None = None) -> dict:
        _, template, _ = self._template()
        mapping = dict(template)
        mapping[self._key_for(mapping, lambda key: any(h in key for h in SECRET_KEY_HINTS))] = secret
        mapping[self._key_for(mapping, lambda key: ENVIRONMENT_KEY_HINT in key)] = environment
        gate_keys = [key for key in mapping if GATE_KEY_HINT in _normalised(key)]
        if gate is None:
            for key in gate_keys:
                mapping.pop(key)
        else:
            for key in gate_keys:
                mapping[key] = gate
        return mapping

    def _without_field(self, mapping: dict, hints) -> dict:
        reduced = dict(mapping)
        for key in list(reduced):
            if any(hint in _normalised(key) for hint in hints):
                reduced.pop(key)
        return reduced

    def _scratch(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="environment-declarations-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        return directory


class TestTheDeclarationCensusIsARealReadOfTheTree(
    DeclarationTreeFixtureMixin, unittest.TestCase
):
    """ADDED requirement: Each Environment Declares Its Own Pipeline
    Configuration.

    At one environment every collision assertion above passes over a set of one
    and every missing-field assertion passes over a file someone just wrote. A
    census that returned the empty list unconditionally would satisfy all of
    them. This class runs the same census over trees built to carry each
    refusal the requirement states, and asserts it reports each one -- and,
    just as importantly, reports nothing over a clean two-environment tree,
    since a census that refused everything would satisfy the refusals while
    making a second environment impossible to add.
    """

    def test_a_clean_two_environment_tree_yields_no_offence(self) -> None:
        """DERIVED -- the converse the four refusals need. No scenario states
        it; a census that refuses every tree satisfies every refusal scenario
        and contradicts the requirement's opening sentence, which is that
        adding an environment needs no workflow edit."""
        scratch = self._scratch()
        self._write_tree(
            scratch,
            {
                "prod": self._declaration_for("HCLOUD_TOKEN", "production", gate=True),
                "staging": self._declaration_for("HCLOUD_TOKEN_STAGING", "staging", gate=False),
            },
        )
        self.assertEqual(
            [],
            declaration_offences(scratch),
            "the census refused a tree carrying two well-formed, non-colliding "
            "declarations, so adding a second environment could not be done at all",
        )

    def test_an_environment_with_no_declaration_is_reported(self) -> None:
        """SPECIFIED -- scenario "An environment missing its declaration fails
        the pipeline": the message SHALL name that directory."""
        scratch = self._scratch()
        self._write_tree(
            scratch,
            {
                "prod": self._declaration_for("HCLOUD_TOKEN", "production", gate=True),
                "staging": None,
            },
        )
        offences = declaration_offences(scratch)
        self.assertTrue(
            offences, "an environment directory carrying no declaration was reported as clean"
        )
        self.assertTrue(
            any("staging" in offence for offence in offences),
            f"the census reported an offence that does not name the directory: {offences}",
        )

    def test_an_environment_missing_a_field_the_workflows_read_is_reported(self) -> None:
        """SPECIFIED -- same scenario, its second half: "or one lacking a field
        the workflows read". Run once per required field, so a census checking
        only one of them is red."""
        for label, hints in (
            ("read-only secret", SECRET_KEY_HINTS),
            ("GitHub Environment", (ENVIRONMENT_KEY_HINT,)),
        ):
            with self.subTest(field=label):
                scratch = self._scratch()
                complete = self._declaration_for("HCLOUD_TOKEN_STAGING", "staging", gate=True)
                self._write_tree(
                    scratch,
                    {
                        "prod": self._declaration_for("HCLOUD_TOKEN", "production", gate=True),
                        "staging": self._without_field(complete, hints),
                    },
                )
                offences = declaration_offences(scratch)
                self.assertTrue(
                    any("staging" in offence for offence in offences),
                    f"a declaration lacking its {label} field was reported as clean, or "
                    f"reported without naming the directory: {offences}",
                )

    def test_two_environments_declaring_one_read_only_secret_are_reported(self) -> None:
        """SPECIFIED -- scenario "Two environments declaring the same read-only
        secret are refused": the pipeline SHALL fail "naming both
        environments"."""
        scratch = self._scratch()
        self._write_tree(
            scratch,
            {
                "prod": self._declaration_for("HCLOUD_TOKEN", "production", gate=True),
                "staging": self._declaration_for("HCLOUD_TOKEN", "staging", gate=False),
            },
        )
        offences = declaration_offences(scratch)
        colliding = [offence for offence in offences if "read-only secret" in offence]
        self.assertTrue(
            colliding,
            "two environments declaring one read-only secret were reported as clean, so "
            f"both plans would run under one credential: {offences}",
        )
        for name in ("prod", "staging"):
            self.assertTrue(
                any(name in offence for offence in colliding),
                f"the collision was reported without naming `{name}`: {colliding}",
            )

    def test_two_environments_declaring_one_github_environment_are_reported(self) -> None:
        """SPECIFIED -- scenario "Two environments declaring the same GitHub
        Environment are refused": "rather than applying two environments under
        one write token and one set of protection rules"."""
        scratch = self._scratch()
        self._write_tree(
            scratch,
            {
                "prod": self._declaration_for("HCLOUD_TOKEN", "production", gate=True),
                "staging": self._declaration_for("HCLOUD_TOKEN_STAGING", "production", gate=False),
            },
        )
        offences = declaration_offences(scratch)
        colliding = [offence for offence in offences if "GitHub Environment" in offence]
        self.assertTrue(
            colliding,
            "two environments declaring one GitHub Environment were reported as clean, "
            f"so an ungated environment would hold prod's write token: {offences}",
        )
        for name in ("prod", "staging"):
            self.assertTrue(
                any(name in offence for offence in colliding),
                f"the collision was reported without naming `{name}`: {colliding}",
            )

    def test_an_environment_declaring_nothing_about_the_gate_is_gated(self) -> None:
        """SPECIFIED -- Destroy Policy Gate, scenario "An environment declaring
        nothing is gated", and "an environment that declares nothing SHALL be
        treated as though the gate applies".

        Read here rather than against the workflow because it is a property of
        how a declaration is INTERPRETED, and the interpretation is what a
        second environment inherits. That the workflow reads applicability from
        the declaration at all is asserted by
        `TestTheDestroyGateReadsApplicabilityFromTheDeclaration`.
        """
        scratch = self._scratch()
        self._write_tree(
            scratch,
            {"prod": self._declaration_for("HCLOUD_TOKEN", "production", gate=None)},
        )
        declarations = environment_declarations(scratch)
        self.assertIn("prod", declarations)
        self.assertTrue(
            declarations["prod"].destroy_gate_applies,
            "a declaration stating nothing about the destroy-policy gate was read as "
            "exempt from it, so a mistake in a declaration disables the gate rather "
            "than failing safe",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Each Environment Declares Its Own Pipeline Configuration
# -- the workflows carry no environment
# --------------------------------------------------------------------------


class TestNoWorkflowNamesAnEnvironment(unittest.TestCase):
    """ADDED requirement: Each Environment Declares Its Own Pipeline
    Configuration -- "Workflows SHALL NOT enumerate environments, name them in
    a condition, or map an environment to its secrets or its Environment name
    in workflow text".

    Scoped to the three workflows this change restructures; see the note on
    `TERRAFORM_WORKFLOWS` for why, and this change's test-plan.md for the
    narrowing recorded as a decision rather than absorbed silently.

    Matched CASE-SENSITIVELY, over the workflow with its whole-line comments
    stripped. Requirement names are cited from these workflows' comments and one
    of them is *Gated Production Apply Applies the Reviewed Plan*: a
    case-insensitive sweep would read that citation as the workflow naming the
    `production` Environment, and the repair would be to stop citing the
    requirement -- which tasks.md 4.6 requires the workflows to keep doing.
    """

    def _names(self) -> list[str]:
        names = {directory.name for directory in environment_directories()}
        for declaration in environment_declarations().values():
            if declaration.github_environment:
                names.add(declaration.github_environment)
        return sorted(names)

    def test_there_is_a_name_to_look_for(self) -> None:
        """SPECIFIED -- guards the two assertions below from passing over an
        empty set of names, which is what an unimplemented declaration or an
        emptied environments directory would produce."""
        self.assertTrue(
            self._names(),
            "no environment directory and no declared GitHub Environment name was "
            "found, so a sweep for environment literals would read nothing",
        )

    def test_no_terraform_workflow_names_an_environment_directory(self) -> None:
        """SPECIFIED -- scenario "A new environment needs no workflow edit":
        the four workflows SHALL cover a new environment "with no change to any
        file under `.github/workflows/`". A workflow naming today's single
        environment is a workflow that must be edited to add tomorrow's."""
        self.test_there_is_a_name_to_look_for()
        names = self._names()
        offenders = []
        for path in TERRAFORM_WORKFLOWS:
            body = uncommented(read_text(path))
            for name in names:
                for occurrence in re.finditer(rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])", body):
                    line = body.count("\n", 0, occurrence.start()) + 1
                    offenders.append(f"{path.name}:{line} names `{name}`")
        self.assertEqual(
            [],
            offenders,
            "these workflows name an environment in their own text, so a second "
            "environment could not be added without editing them -- which is the "
            f"defect this requirement exists to prevent: {offenders}",
        )

    def test_no_terraform_workflow_maps_an_environment_to_a_secret(self) -> None:
        """SPECIFIED -- same requirement: a workflow SHALL NOT "map an
        environment to its secrets ... in workflow text". Distinct from the
        assertion above because a mapping can be written without spelling the
        environment's name -- a `case` over directory basenames, or a literal
        read-only secret name that only one environment uses.

        THE EXEMPTION BELOW IS INERT AS OF
        `apply-host-configuration-through-a-gated-workflow`, AND THE THIRD
        ESCAPE IT NAMES IS THE ONE THAT WAS TAKEN. Read the rest of this
        docstring as the history of why it exists, not as a description of what
        it currently does: prod no longer declares `HCLOUD_TOKEN` as its
        read-only secret, so `apply.yml`'s digest emitter no longer reads a
        declared read-only secret name, so this sweep no longer flags it and
        the exemption matches nothing. The count assertion at the end passes
        over an empty list, which is why nothing here went red when the premise
        expired -- the case this note exists to stop a reader mistaking for a
        working guard.

        It is kept rather than deleted because it is a closed form keyed on a
        shape rather than on prod: were any environment ever to declare as its
        read-only secret a name the omitted-write-token guard must also read,
        the exemption would re-arm for exactly that step and nothing else. The
        new check in `test_host_converge_workflow
        .TestNoDeclarationNamesTheWriteTokensOwnName` now forbids the specific
        name that made that true, so that is not a state this repository can
        reach today.

        THE WHOLE JOB IS SWEPT, with ONE named exemption. That exemption was
        added by the implementing author, not by the author of this file, and
        the reason is recorded here rather than in a commit message because it
        is the one place two SPECIFIED assertions in this module could not both
        be satisfied.

        As first written this swept the whole job with no exemption, and so
        failed `apply.yml`'s plan job for the read of `secrets.HCLOUD_TOKEN`
        that `TestTheApplyJobEstablishesItResolvedItsOwnWriteToken
        .test_the_guard_reads_the_repository_scoped_hcloud_token_by_that_name`
        REQUIRES to be there. The Credential Scoping by Privilege requirement
        obliges the omitted-write-token guard to digest `HCLOUD_TOKEN` by that
        exact name ("The comparison is against that name specifically, because
        that is what GitHub falls back to"), and obliges it to happen where the
        REPOSITORY-scoped value is visible, which is only a job declaring no
        `environment:`. Prod declares `HCLOUD_TOKEN` as its own read-only secret
        (design.md Decision 1, so that nothing in repository settings moves at
        one environment), so the guard's mandatory read and this sweep's subject
        are the same string.

        The three escapes were each checked, and each is closed by another
        assertion in this module: moving the guard into a job that declares an
        `environment:` fails that class's own locator; reading the repository
        token under a different spelling fails
        `test_the_guard_reads_the_repository_scoped_hcloud_token_by_that_name`;
        and giving prod a different read-only secret name fails
        `test_prod_declares_the_secret_and_environment_it_already_uses`, and
        would additionally require creating a repository secret before the merge
        -- the exact repository-settings change design.md Decision 1 exists to
        avoid. So the exemption is made here.

        The third escape was taken, deliberately, and the cost it names was paid
        rather than avoided: `apply-host-configuration-through-a-gated-workflow`
        gave prod the read-only secret name `HCLOUD_TOKEN_PRODUCTION`, re-pointed that
        assertion at the new value, and created the repository secret before the
        merge as a sequenced migration step. What made it worth paying is that
        the old name was not merely inconvenient -- a job declaring an
        `environment:` resolved it to the Read & Write token.

        IT IS A CLOSED FORM, not a scope reduction, which is the standard this
        capability holds its own suppression checks to. Exactly one step is
        exempt: the one whose `id` this job publishes in its `outputs:` and
        whose `run` invokes no Terraform command -- the digest emitter, and
        nothing else that could be written. Every other read of a declared
        read-only secret anywhere in an ungated job still fails, INCLUDING the
        indirect ones a Terraform-only sweep would have missed: a step writing
        the secret to `$GITHUB_ENV` for a later plan to inherit, or an action
        handed it through `with:`.
        """
        self.test_there_is_a_name_to_look_for()
        declared_secrets = sorted(
            {
                declaration.read_only_secret
                for declaration in environment_declarations().values()
                if declaration.read_only_secret
            }
        )
        self.assertTrue(
            declared_secrets,
            "no environment declares a read-only secret name, so this assertion would "
            "read nothing",
        )
        invoking_terraform = re.compile(r"terraform\s+[a-z]")
        offenders = []
        exempted = []
        for path in TERRAFORM_WORKFLOWS:
            workflow = load_yaml(path)
            for job_name, job in jobs(workflow).items():
                if declared_environment(job) is not None:
                    # The apply job resolves `HCLOUD_TOKEN` through its own
                    # GitHub Environment, so naming that secret there is the
                    # scheme working rather than a mapping in workflow text.
                    continue
                published = compact(yaml.safe_dump(job.get("outputs") or {}, sort_keys=True))
                # Job-level `env:` reaches every step below it, so it is swept
                # as part of the job rather than attributed to any one step.
                surfaces = [("<job-level env:>", job.get("env"), False)]
                for index, step in enumerate(job.get("steps") or []):
                    step_id = str(step.get("id") or "")
                    is_digest_emitter = (
                        bool(step_id)
                        and f"steps.{step_id}.outputs." in published
                        and not invocation_lines(step.get("run", ""), invoking_terraform)
                    )
                    surfaces.append(
                        (
                            step_label(job_name, index, step),
                            {
                                "env": step.get("env"),
                                "with": step.get("with"),
                                "run": step.get("run"),
                            },
                            is_digest_emitter,
                        )
                    )
                for label, surface, is_digest_emitter in surfaces:
                    body = uncommented(yaml.safe_dump(surface or {}, sort_keys=True))
                    for secret in declared_secrets:
                        if not re.search(rf"secrets\.{re.escape(secret)}(?![A-Za-z0-9_])", body):
                            continue
                        if is_digest_emitter:
                            exempted.append(f"{path.name}:{label}")
                            continue
                        offenders.append(f"{path.name}:{label} reads `secrets.{secret}`")
        self.assertEqual(
            [],
            sorted(set(offenders)),
            "these jobs declare no `environment:` and yet read a specific "
            "environment's read-only secret by name, so the secret a plan runs under "
            "comes from workflow text rather than from that environment's own "
            f"declaration: {sorted(set(offenders))}",
        )
        self.assertLessEqual(
            len(exempted),
            1,
            "more than one step claims the omitted-write-token guard's exemption "
            f"from this sweep: {sorted(exempted)}. The exemption is for exactly one "
            "step -- the digest emitter the Credential Scoping by Privilege "
            "requirement obliges -- and a second step wearing its shape is a second "
            "literal-named credential read that nothing else here would catch",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Each Environment Declares Its Own Pipeline Configuration
# -- discovery, run rather than read
# --------------------------------------------------------------------------


class TestDiscoveryFailsClosed(DeclarationTreeFixtureMixin, unittest.TestCase):
    """ADDED requirement: Each Environment Declares Its Own Pipeline
    Configuration -- "Discovery SHALL fail closed".

    Runs the workflow's own discovery body rather than reading it, the same
    extract-and-run shape `TestTheAggregatingGateDiscriminates` and
    `TestMoleculeDiscoveryAndScenarioCoverage.test_role_discovery_fails_when_it_finds_nothing`
    use in `test_ci_configuration.py`. Grepping would establish that a
    discovery step exists; only running it establishes that it refuses.

    The body is located by shape, not by name: the one `run:` step in the
    workflow that names `terraform/stacks` and carries no `${{ }}`. That
    it carries none is tasks.md 3.4's own obligation and the reason this class
    can exist at all -- an expression is interpolated before the step runs, so a
    body carrying one cannot be executed anywhere but on a runner.
    """

    def _discovery_step(self, path: Path):
        workflow = load_yaml(path)
        candidates = [
            (job, index, step)
            for job, index, step in steps(workflow)
            if step.get("run")
            and "terraform/stacks" in str(step["run"])
            and "terraform/modules" not in str(step["run"])
            and "GITHUB_OUTPUT" in str(step["run"])
            and not ACTIONS_EXPRESSION.search(str(step["run"]))
        ]
        self.assertEqual(
            1,
            len(candidates),
            f"expected exactly one `run:` step in {path.name} that enumerates "
            "`terraform/stacks` and carries no `${{ }}` -- the discovery step "
            f"this suite must be able to execute -- but found {len(candidates)}: "
            + repr([step_label(job, index, step) for job, index, step in candidates])
            + ". Writing to `$GITHUB_OUTPUT` is part of the locator because emitting "
            "the matrix is what discovery is FOR: without it the locator also matches "
            "a step that merely mentions the path in a heading, and reports on a step "
            "that discovers nothing. Two further shapes fail it and each is a real "
            "constraint rather than an accident of matching: discovery written as an "
            "Actions expression, or carrying one in its body, cannot be executed "
            "anywhere but on a runner, so its refusals would be asserted nowhere "
            "(tasks.md 3.4); and discovery fused into the same step as the "
            "changed-path resolution -- which names `terraform/modules` too -- "
            "cannot be exercised over a tree with no diff to resolve. tasks.md 3.1 "
            "and 3.3 describe them as two steps",
        )
        return candidates[0]

    def _run_discovery(self, path: Path, tree: Path):
        job, index, step = self._discovery_step(path)
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
        result = run_snippet(str(step["run"]), environment, tree)
        return result, outputs

    def setUp(self) -> None:
        require_external_tools(
            self,
            ("bash", "find", "jq"),
            "execute the workflow's environment-discovery body",
        )

    def test_discovery_emits_every_well_formed_environment(self) -> None:
        """SPECIFIED -- scenario "A new environment needs no workflow edit":
        the workflows SHALL "each cover it on their next run". Discovery
        emitting the new environment is the whole of what "cover" means before
        a job starts.

        The converse the refusals below need: discovery that failed on every
        tree would satisfy each of them while covering nothing.
        """
        scratch = self._scratch()
        self._write_tree(
            scratch,
            {
                "prod": self._declaration_for("HCLOUD_TOKEN", "production", gate=True),
                "staging": self._declaration_for("HCLOUD_TOKEN_STAGING", "staging", gate=False),
            },
        )
        result, outputs = self._run_discovery(PR_VALIDATION, scratch)
        detail = (result.stdout + result.stderr).strip()[-800:]
        self.assertEqual(
            0,
            result.returncode,
            f"discovery refused a tree carrying two well-formed declarations: {detail!r}",
        )
        emitted = outputs.read_text(encoding="utf-8") + result.stdout
        for name in ("prod", "staging"):
            self.assertIn(
                name,
                emitted,
                f"discovery ran over a tree holding `{name}` and emitted nothing naming "
                f"it, so that environment is planned by nothing: {emitted!r}",
            )

    def test_discovery_fails_when_it_finds_no_environment(self) -> None:
        """SPECIFIED -- scenario "Discovery finding no environment fails rather
        than reporting success": "the workflow SHALL fail with a message
        identifying discovery as the cause, and SHALL NOT allow a dependent job
        to be skipped and reported as successful"."""
        scratch = self._scratch()
        (scratch / "terraform" / "stacks").mkdir(parents=True)
        result, _ = self._run_discovery(PR_VALIDATION, scratch)
        combined = (result.stdout + result.stderr).strip()
        self.assertNotEqual(
            0,
            result.returncode,
            "discovery concluded successfully over an empty `terraform/stacks/`, "
            "so every dependent job is skipped on an empty matrix and the run reports "
            f"green having planned nothing: {combined[-800:]!r}",
        )
        self.assertRegex(
            combined.lower(),
            r"environment|discover",
            "discovery refused the empty tree without naming discovery or the "
            f"environments directory as the cause: {combined[-400:]!r}",
        )

    def test_discovery_fails_on_an_environment_with_no_declaration(self) -> None:
        """SPECIFIED -- scenario "An environment missing its declaration fails
        the pipeline": discovery SHALL fail "with a message naming that
        directory ... rather than omitting the environment from the matrix"."""
        scratch = self._scratch()
        self._write_tree(
            scratch,
            {
                "prod": self._declaration_for("HCLOUD_TOKEN", "production", gate=True),
                "staging": None,
            },
        )
        result, _ = self._run_discovery(PR_VALIDATION, scratch)
        combined = (result.stdout + result.stderr).strip()
        self.assertNotEqual(
            0,
            result.returncode,
            "discovery concluded successfully over an environment directory carrying "
            "no declaration, which leaves that environment silently out of the matrix "
            f"-- indistinguishable from it not existing: {combined[-800:]!r}",
        )
        self.assertIn(
            "staging",
            combined,
            "discovery refused without naming the directory whose declaration is "
            f"missing: {combined[-400:]!r}",
        )

    def test_discovery_fails_on_a_declaration_missing_a_field(self) -> None:
        """SPECIFIED -- same scenario: "or one lacking a field the workflows
        read ... with a message naming that directory and the missing
        field"."""
        for label, hints in (
            ("read-only secret", SECRET_KEY_HINTS),
            ("GitHub Environment", (ENVIRONMENT_KEY_HINT,)),
        ):
            with self.subTest(field=label):
                scratch = self._scratch()
                complete = self._declaration_for("HCLOUD_TOKEN_STAGING", "staging", gate=True)
                self._write_tree(
                    scratch,
                    {
                        "prod": self._declaration_for("HCLOUD_TOKEN", "production", gate=True),
                        "staging": self._without_field(complete, hints),
                    },
                )
                result, _ = self._run_discovery(PR_VALIDATION, scratch)
                combined = (result.stdout + result.stderr).strip()
                self.assertNotEqual(
                    0,
                    result.returncode,
                    f"discovery concluded successfully over a declaration with no "
                    f"{label} field, so the matrix carries an environment whose plan "
                    f"has no credential to resolve: {combined[-800:]!r}",
                )
                self.assertIn(
                    "staging",
                    combined,
                    "discovery refused without naming the directory whose declaration "
                    f"is incomplete: {combined[-400:]!r}",
                )

    def test_discovery_fails_on_two_environments_sharing_a_read_only_secret(self) -> None:
        """SPECIFIED -- scenario "Two environments declaring the same read-only
        secret are refused": "the pipeline SHALL fail, naming both
        environments, rather than running two environments' plans under one
        credential"."""
        scratch = self._scratch()
        self._write_tree(
            scratch,
            {
                "prod": self._declaration_for("HCLOUD_TOKEN", "production", gate=True),
                "staging": self._declaration_for("HCLOUD_TOKEN", "staging", gate=False),
            },
        )
        result, _ = self._run_discovery(PR_VALIDATION, scratch)
        combined = (result.stdout + result.stderr).strip()
        self.assertNotEqual(
            0,
            result.returncode,
            "discovery accepted two environments declaring one read-only secret, so "
            "both environments' plans would authenticate to one Hetzner project and "
            f"the second would report every resource as absent: {combined[-800:]!r}",
        )
        for name in ("prod", "staging"):
            self.assertIn(
                name,
                combined,
                f"discovery refused the collision without naming `{name}`: "
                f"{combined[-400:]!r}",
            )

    def test_discovery_fails_on_two_environments_sharing_a_github_environment(self) -> None:
        """SPECIFIED -- scenario "Two environments declaring the same GitHub
        Environment are refused": "rather than applying two environments under
        one write token and one set of protection rules"."""
        scratch = self._scratch()
        self._write_tree(
            scratch,
            {
                "prod": self._declaration_for("HCLOUD_TOKEN", "production", gate=True),
                "staging": self._declaration_for("HCLOUD_TOKEN_STAGING", "production", gate=False),
            },
        )
        result, _ = self._run_discovery(PR_VALIDATION, scratch)
        combined = (result.stdout + result.stderr).strip()
        self.assertNotEqual(
            0,
            result.returncode,
            "discovery accepted two environments declaring one GitHub Environment, so "
            "an environment intended to be ungated would hold the reviewed "
            f"environment's write credential: {combined[-800:]!r}",
        )
        for name in ("prod", "staging"):
            self.assertIn(
                name,
                combined,
                f"discovery refused the collision without naming `{name}`: "
                f"{combined[-400:]!r}",
            )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Pull Request Plan Visibility
# --------------------------------------------------------------------------


class TestEveryPlanIsScannedInItsOwnJob(unittest.TestCase):
    """MODIFIED requirement: Pull Request Plan Visibility -- "A secret scan
    SHALL precede every plan, in the job that runs it".

    `test_ci_configuration.TestSecretScanningIsUnconditional
    .test_secret_scanning_precedes_any_terraform_plan_in_the_same_job` asserts
    the ORDERING where both a scan and a plan are found in one job, and
    `continue`s over a job holding a plan and no scan. That skip is what the
    change's design.md Decision 3 identifies as the silent failure a
    restructure would produce, and tasks.md 5.4 assigns closing it to the
    implementing author.

    This class does not edit that test. It adds the assertion the skip leaves
    unmade -- a plan in a job with no preceding scan is an offence -- so the
    scenario is covered whether or not that strengthening lands, and the two
    then agree rather than overlap: that one reads order, this one reads
    presence.
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(PR_VALIDATION)

    def test_the_workflow_still_plans(self) -> None:
        """SPECIFIED -- "The workflow SHALL run `terraform plan` for every
        environment the pull request can affect". Guards the assertion below
        from passing over a workflow that plans nothing."""
        self.assertTrue(
            jobs_running(self.workflow, TERRAFORM_PLAN),
            "no job in pr-validation.yml runs `terraform plan`, so the reviewer sees "
            "no plan and every ordering assertion about plans is vacuous",
        )

    def test_every_job_running_terraform_plan_scans_for_secrets_first(self) -> None:
        """SPECIFIED -- scenario "A secret scan precedes every plan": "that same
        job SHALL have run the secret scan earlier in its own step sequence".

        Stated over EVERY job that plans, including one holding no scan at all.
        A plan authenticates to a cloud API and writes its output into a pull
        request comment; a leaked credential reaching either is what the
        ordering exists to prevent, and a plan job with no scan does not
        prevent it less than one with the scan in the wrong place.
        """
        self.test_the_workflow_still_plans()
        offenders = []
        for job_name, job in sorted(jobs_running(self.workflow, TERRAFORM_PLAN).items()):
            job_steps = job.get("steps") or []
            scans = [
                index
                for index, step in enumerate(job_steps)
                if "gitleaks" in step_text(step).lower()
            ]
            plans = [index for index, _, _ in invoking_steps(job, TERRAFORM_PLAN)]
            if not scans:
                offenders.append(f"{job_name}: runs `terraform plan` and no secret scan at all")
            elif max(scans) > min(plans):
                offenders.append(f"{job_name}: plans at step {min(plans)} before scanning at {max(scans)}")
        self.assertEqual(
            [],
            offenders,
            "these jobs run `terraform plan` without a secret scan earlier in the same "
            f"job: {offenders}. The ordering is scoped to a job because that is where "
            "a failing step stops the next one; a scan in a different job stops "
            "nothing",
        )


class TestThePlanMatrixReportsEveryEnvironment(unittest.TestCase):
    """MODIFIED requirement: Pull Request Plan Visibility."""

    def setUp(self) -> None:
        self.workflow = load_yaml(PR_VALIDATION)
        self.planning = jobs_running(self.workflow, TERRAFORM_PLAN)

    def test_the_plan_runs_as_a_matrix_over_discovered_environments(self) -> None:
        """SPECIFIED -- "The workflow SHALL run `terraform plan` for every
        environment the pull request can affect", and scenario "A shared module
        change is planned against every environment".

        A matrix built from a job's output is what makes "every environment"
        mean the discovered set rather than a list someone maintains; a matrix
        written as a literal list would satisfy "runs per environment" and
        contradict the ADDED requirement in the same breath.
        """
        self.assertTrue(self.planning, "no job in pr-validation.yml runs `terraform plan`")
        offenders = []
        for name, job in sorted(self.planning.items()):
            matrix = (job.get("strategy") or {}).get("matrix")
            if not matrix:
                offenders.append(f"{name}: declares no `strategy.matrix`")
            elif not matrix_source_jobs(self.workflow, job):
                offenders.append(
                    f"{name}: builds its matrix from {matrix!r}, which reads no job's "
                    "output, so the environments it covers are written in the workflow"
                )
        self.assertEqual([], offenders, "; ".join(offenders))

    def test_one_environments_plan_failure_does_not_abandon_the_others(self) -> None:
        """SPECIFIED -- scenario "One environment's plan failure does not hide
        the others": "every other affected environment SHALL still be planned
        and its result posted". A matrix defaults to `fail-fast: true`, which
        cancels the siblings of the first failing row -- so a reviewer shown one
        failure cannot tell whether the rest were clean or merely
        unexamined."""
        self.assertTrue(self.planning, "no job in pr-validation.yml runs `terraform plan`")
        offenders = [
            name
            for name, job in sorted(self.planning.items())
            if (job.get("strategy") or {}).get("fail-fast") is not False
        ]
        self.assertEqual(
            [],
            offenders,
            f"these plan matrix jobs do not set `fail-fast: false`: {offenders}",
        )

    def test_each_environments_plan_comment_is_keyed_to_that_environment(self) -> None:
        """SPECIFIED -- "post each plan's full output as a comment on the pull
        request, identifying which environment each plan belongs to", and
        scenario "A shared module change is planned against every environment":
        "a plan for every environment, each identifying the environment it
        belongs to".

        Asserted as the comment-locating marker being DERIVED from the
        environment rather than constant, which tasks.md 4.2 is explicit must be
        verified statically: a constant marker with `edit-mode: replace` makes
        every environment overwrite one comment, and at one environment that
        defect and the correct behaviour are indistinguishable.
        """
        marking = [
            (job, index, step)
            for job, index, step in steps(self.workflow)
            if "comment" in str(step.get("uses", "")).lower()
        ]
        self.assertTrue(
            marking,
            "no step in pr-validation.yml uses a pull-request comment action, so the "
            "reviewer sees no plan without leaving GitHub",
        )
        offenders = []
        for job, index, step in marking:
            with_block = step.get("with") or {}
            markers = [
                str(with_block[key])
                for key in ("body-includes", "comment-id", "body", "body-path", "body-file")
                if key in with_block
            ]
            if not markers:
                offenders.append(f"{step_label(job, index, step)}: declares no comment body or marker")
            elif not any("matrix." in compact(marker) for marker in markers):
                offenders.append(
                    f"{step_label(job, index, step)}: its comment marker {markers!r} "
                    "carries no matrix value"
                )
        self.assertEqual(
            [],
            offenders,
            "these comment steps key their comment on something constant, so N "
            "environments would find and overwrite one comment and a single plan would "
            f"be left standing: {offenders}",
        )


class TestTheAggregatingValidateJobCoversThePlanMatrix(unittest.TestCase):
    """MODIFIED requirements: Pull Request Plan Visibility; Required Status
    Checks Report on Every Pull Request (carried through).

    "Where this work runs as a job whose name is generated from a matrix, it
    SHALL NOT be the registered required status check context ... which governs
    how it concludes."
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(PR_VALIDATION)
        self.planning = jobs_running(self.workflow, TERRAFORM_PLAN)

    def _validate_job(self):
        declared = jobs(self.workflow)
        self.assertIn(
            "validate",
            declared,
            "pr-validation.yml declares no `validate` job. That literal key is the "
            "status check context registered in branch protection; renaming it leaves "
            f"a required check that never reports. Its jobs are {sorted(declared)}",
        )
        return declared["validate"]

    def test_the_registered_context_is_not_the_matrix_job(self) -> None:
        """SPECIFIED -- "it SHALL NOT be the registered required status check
        context". A matrix generates one job name per row, so no single name is
        stable enough to register."""
        offenders = sorted(
            name for name, job in self.planning.items() if (job.get("strategy") or {}).get("matrix")
        )
        self.assertNotIn(
            "validate",
            offenders,
            "the `validate` job -- the registered context -- generates its name from a "
            "matrix, so the context registered in branch protection never reports",
        )

    def test_the_registered_context_concludes_on_the_plan_matrixs_behalf(self) -> None:
        """SPECIFIED -- same sentence, read forward: the matrix is not the
        context, so something registered must conclude for it. A plan matrix no
        registered job depends on is a plan that can fail while the pull
        request stays mergeable, which is the reduction design.md Decision 3a
        weighed and refused."""
        self.assertTrue(self.planning, "no job in pr-validation.yml runs `terraform plan`")
        validate = self._validate_job()
        needs = needs_of(validate)
        missing = sorted(set(self.planning) - set(needs) - {"validate"})
        self.assertEqual(
            [],
            missing,
            f"the `validate` job declares `needs: {needs}`, which does not name these "
            f"plan jobs: {missing}. A failing plan would then leave `validate` green "
            "and the pull request mergeable",
        )

    def test_the_registered_context_also_depends_on_discovery(self) -> None:
        """DERIVED (tasks.md 4.1a) -- no scenario states it. The requirement
        obliges discovery to fail closed; that `validate` must SEE that failure
        follows from tasks.md 4.1a's instruction to check the discovery result
        first, "since on discovery failure its outputs are empty and the
        'nothing to do' branch would otherwise conclude success on a run whose
        own precondition refused". Reconsider this assertion, do not weaken it,
        if the aggregation reaches discovery's result another way."""
        self.assertTrue(self.planning, "no job in pr-validation.yml runs `terraform plan`")
        validate = self._validate_job()
        needs = set(needs_of(validate))
        sources = {
            source
            for job in self.planning.values()
            for source in matrix_source_jobs(self.workflow, job)
        }
        self.assertTrue(
            sources,
            "no plan job builds its matrix from another job's output, so there is no "
            "discovery job for `validate` to depend on",
        )
        missing = sorted(sources - needs)
        self.assertEqual(
            [],
            missing,
            f"`validate` declares `needs: {sorted(needs)}` and does not name the "
            f"discovery job(s) {missing}. On a discovery failure the matrix is empty, "
            "every plan job is skipped, and an aggregation that reads only the matrix "
            "concludes 'nothing to do' on a run whose own precondition refused",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Credential Scoping by Privilege
# --------------------------------------------------------------------------


class TestPlanJobsHoldOnlyTheirOwnReadOnlyToken(unittest.TestCase):
    """MODIFIED requirement: Credential Scoping by Privilege.

    "This split SHALL hold per environment: a job planning one environment
    SHALL NOT hold a credential capable of writing to any environment."
    """

    WORKFLOWS_THAT_PLAN = TERRAFORM_WORKFLOWS

    def test_no_job_running_terraform_plan_declares_an_environment(self) -> None:
        """SPECIFIED -- "**No job that runs `terraform plan` SHALL declare an
        `environment:`.**", and scenarios "Plan jobs receive only a read-only
        Hetzner token" and "Pull request validation requires no manual
        approval". Declaring one would both pause the job on that Environment's
        protection rules and resolve `HCLOUD_TOKEN` to the write-capable token
        in an ungated job.

        `test_ci_configuration.TestSavedPlanIsWhatGetsApplied
        .test_the_planning_job_declares_no_environment` states this of
        `apply.yml` alone. This states it of every workflow that plans, which is
        what the requirement says and what the change makes true of three
        workflows rather than one.
        """
        offenders = []
        for path in self.WORKFLOWS_THAT_PLAN:
            workflow = load_yaml(path)
            for name, job in sorted(jobs_running(workflow, TERRAFORM_PLAN).items()):
                if declared_environment(job) is not None:
                    offenders.append(f"{path.name}:{name} declares `environment: {declared_environment(job)}`")
        self.assertEqual(
            [],
            offenders,
            "these jobs run `terraform plan` and declare an `environment:`, so each "
            "resolves the write-capable `HCLOUD_TOKEN` and pauses on that "
            f"Environment's protection rules: {offenders}",
        )

    def test_every_plan_job_selects_its_token_by_the_declared_secret_name(self) -> None:
        """SPECIFIED -- scenario "Plan jobs receive only a read-only Hetzner
        token": "its Hetzner token SHALL resolve to the repository-scoped Read
        Only secret named by that environment's own declaration", and scenario
        "A plan job holds no credential for another environment".

        Read as an INDEXED secret read carrying a matrix value, because that is
        the only construction that can resolve a different token per row: `${{
        }}` is evaluated before a step runs, so a literal name binds one
        compile-time-known secret and a shell loop over N environments holds one
        token for all of them.
        """
        offenders = []
        for path in self.WORKFLOWS_THAT_PLAN:
            workflow = load_yaml(path)
            for name, job in sorted(jobs_running(workflow, TERRAFORM_PLAN).items()):
                body = compact(uncommented(yaml.safe_dump(job, sort_keys=True)))
                indexed = re.findall(r"secrets\[[^\]]*matrix\.[^\]]*\]", body)
                if not indexed:
                    offenders.append(
                        f"{path.name}:{name} resolves no Hetzner token through "
                        "`secrets[<a matrix value>]`"
                    )
        self.assertEqual(
            [],
            offenders,
            "these plan jobs do not select their Hetzner credential by the secret name "
            f"their environment declares: {offenders}. At more than one environment "
            "every plan would run under one environment's token, see none of the "
            "other's resources, and report a meaningless diff",
        )


class TestTheApplyJobEstablishesItResolvedItsOwnWriteToken(unittest.TestCase):
    """MODIFIED requirement: Credential Scoping by Privilege -- "An apply job
    SHALL establish that the token it resolved is not the repository-scoped
    `HCLOUD_TOKEN`, and SHALL fail rather than apply where it is."

    GitHub resolves an ABSENT Environment secret to the repository secret of
    the same name rather than failing, so an Environment created without
    `HCLOUD_TOKEN` silently supplies whatever the repository holds -- at more
    than one environment, a different environment's token and therefore a
    different Hetzner project.

    Exercised by running both bodies rather than reading them, and without this
    file knowing how the digest is constructed: the emitter is run first and its
    own output is fed to the comparator. That is what makes the pair
    assertable while leaving the construction the implementing author's choice
    (tasks.md 4.3a).
    """

    TOKEN = "read-only-token-fixture"
    OTHER_TOKEN = "read-write-token-fixture"
    RUN_ID = "1234567890"

    def setUp(self) -> None:
        self.workflow = load_yaml(APPLY)
        require_external_tools(
            self, ("bash",), "execute apply.yml's resolved-token comparison"
        )

    def _emitting_step(self):
        """The plan job's digest step: a `${{ }}`-free `run:` step whose `env:`
        carries `secrets.HCLOUD_TOKEN`, in a job declaring no `environment:`."""
        candidates = []
        for name, job in jobs(self.workflow).items():
            if declared_environment(job) is not None:
                continue
            exposed = compact(yaml.safe_dump(job.get("outputs") or {}, sort_keys=True))
            for index, step in expression_free_run_steps(job):
                step_id = str(step.get("id") or "")
                # The step must EXPOSE what it computes as a job output. Without
                # that clause the locator also matches the plan step itself,
                # which takes `secrets.HCLOUD_TOKEN` through `env:` for the
                # ordinary reason -- and running the plan step as though it were
                # the digest emitter reports on a command that never ran.
                if not step_id or f"steps.{step_id}.outputs." not in exposed:
                    continue
                inputs = {}
                for key, value in (step.get("env") or {}).items():
                    expression = compact(value)
                    if "secrets.HCLOUD_TOKEN" in expression:
                        inputs["token"] = key
                    elif "github.run_id" in expression:
                        inputs["run_id"] = key
                if "token" in inputs:
                    candidates.append((name, index, step, inputs))
        self.assertEqual(
            1,
            len(candidates),
            "expected exactly one `run:` step in a job of apply.yml that declares no "
            "`environment:`, takes `secrets.HCLOUD_TOKEN` through its `env:` block and "
            "exposes its result as a job output -- the step that digests the "
            "REPOSITORY-scoped token, which only a job with no `environment:` can see, "
            "and passes the digest to the apply job -- but found "
            f"{len(candidates)}: "
            + repr([step_label(name, index, step) for name, index, step, _ in candidates]),
        )
        return candidates[0]

    def _comparing_step(self):
        """The apply job's comparison step: a `${{ }}`-free `run:` step in a job
        that declares an `environment:`, taking both a `needs.*.outputs.*` and
        `secrets.HCLOUD_TOKEN` through `env:`."""
        candidates = []
        for name, job in jobs(self.workflow).items():
            if declared_environment(job) is None:
                continue
            for index, step in expression_free_run_steps(job):
                inputs = {}
                for key, value in (step.get("env") or {}).items():
                    expression = compact(value)
                    if re.search(r"needs\.[A-Za-z0-9_-]+\.outputs\.", expression):
                        inputs["expected"] = key
                    elif "secrets.HCLOUD_TOKEN" in expression:
                        inputs["token"] = key
                    elif "github.run_id" in expression:
                        inputs["run_id"] = key
                if {"expected", "token"} <= set(inputs):
                    candidates.append((name, index, step, inputs))
        self.assertEqual(
            1,
            len(candidates),
            "expected exactly one `run:` step in an apply job of apply.yml taking both "
            "the plan job's digest output and its own resolved `secrets.HCLOUD_TOKEN` "
            "through its `env:` block -- the guard against an Environment that omits "
            f"`HCLOUD_TOKEN` -- but found {len(candidates)}: "
            + repr([step_label(name, index, step) for name, index, step, _ in candidates]),
        )
        return candidates[0]

    def _scratch(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="apply-token-guard-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        return directory

    def _emit(self, token: str) -> str:
        _, _, step, inputs = self._emitting_step()
        scratch = self._scratch()
        outputs = scratch / "github_output"
        summary = scratch / "step_summary"
        outputs.touch()
        summary.touch()
        environment = dict(
            os.environ,
            GITHUB_OUTPUT=str(outputs),
            GITHUB_ENV=str(outputs),
            GITHUB_STEP_SUMMARY=str(summary),
            GITHUB_RUN_ID=self.RUN_ID,
        )
        environment[inputs["token"]] = token
        if "run_id" in inputs:
            environment[inputs["run_id"]] = self.RUN_ID
        result = run_snippet(str(step["run"]), environment, scratch)
        self.assertEqual(
            0,
            result.returncode,
            "the plan job's digest step failed over a known token: "
            f"{(result.stdout + result.stderr).strip()[-800:]!r}",
        )
        written = github_output_pairs(outputs)
        self.assertTrue(
            written,
            "the plan job's digest step wrote nothing to $GITHUB_OUTPUT, so the apply "
            "job has no digest to compare its own resolved token against",
        )
        digests = [value.strip() for value in written.values() if value.strip()]
        self.assertEqual(
            1,
            len(digests),
            f"the digest step wrote {written!r}; exactly one output is the digest the "
            "apply job compares against",
        )
        self.assertNotIn(
            token,
            outputs.read_text(encoding="utf-8") + result.stdout + result.stderr,
            "the digest step published the token itself rather than a digest of it, so "
            "the repository-scoped read-only credential is now in the run's output "
            "graph and its logs",
        )
        return digests[0]

    def _compare(self, expected: str, token: str):
        _, _, step, inputs = self._comparing_step()
        scratch = self._scratch()
        outputs = scratch / "github_output"
        summary = scratch / "step_summary"
        outputs.touch()
        summary.touch()
        environment = dict(
            os.environ,
            GITHUB_OUTPUT=str(outputs),
            GITHUB_ENV=str(outputs),
            GITHUB_STEP_SUMMARY=str(summary),
            GITHUB_RUN_ID=self.RUN_ID,
        )
        environment[inputs["expected"]] = expected
        environment[inputs["token"]] = token
        if "run_id" in inputs:
            environment[inputs["run_id"]] = self.RUN_ID
        return run_snippet(str(step["run"]), environment, scratch)

    def test_the_guard_fails_when_the_apply_job_resolved_the_repository_token(self) -> None:
        """SPECIFIED -- scenario "An Environment omitting the write token does
        not apply with another's": "the job SHALL fail before applying, rather
        than authenticating against whichever Hetzner project that
        repository-scoped token belongs to"."""
        digest = self._emit(self.TOKEN)
        result = self._compare(digest, self.TOKEN)
        combined = (result.stdout + result.stderr).strip()
        self.assertNotEqual(
            0,
            result.returncode,
            "the apply job's guard passed although its resolved `HCLOUD_TOKEN` is the "
            "very repository-scoped value the plan job digested -- which is exactly "
            "what an Environment that omits the secret produces: "
            f"{combined[-800:]!r}",
        )
        self.assertNotIn(
            self.TOKEN,
            combined,
            f"the guard printed the token while refusing: {combined[-400:]!r}",
        )

    def test_the_guard_passes_when_the_environment_supplied_its_own_token(self) -> None:
        """SPECIFIED -- scenario "Apply job receives the read-write Hetzner
        token only after approval": the apply job's `HCLOUD_TOKEN` resolves to
        that Environment's Read & Write token, and the apply proceeds.

        The converse the refusal needs: a guard that failed either way would
        satisfy the scenario above and block every apply in the repository --
        including, at one environment, every production apply.
        """
        digest = self._emit(self.TOKEN)
        result = self._compare(digest, self.OTHER_TOKEN)
        combined = (result.stdout + result.stderr).strip()
        self.assertEqual(
            0,
            result.returncode,
            "the apply job's guard refused although its resolved `HCLOUD_TOKEN` differs "
            "from the repository-scoped value, which is the ordinary case on every "
            f"correctly configured environment: {combined[-800:]!r}",
        )
        self.assertNotIn(
            self.OTHER_TOKEN,
            combined,
            f"the guard printed the read-write token: {combined[-400:]!r}",
        )

    def test_the_guard_reads_the_repository_scoped_hcloud_token_by_that_name(self) -> None:
        """SPECIFIED -- "The comparison is against that name specifically,
        because that is what GitHub falls back to -- not against whatever secret
        the environment declares as its read-only one, which coincides with it
        for at most one environment and would leave the guard passing wherever
        the hazard is real."

        The two coincide for prod, so at one environment a guard digesting the
        declared read-only name behaves identically to a correct one. This is
        the assertion that tells them apart before there is a second
        environment to tell them apart for.
        """
        name, index, step, inputs = self._emitting_step()
        expression = compact((step.get("env") or {})[inputs["token"]])
        self.assertIn(
            "secrets.HCLOUD_TOKEN",
            expression,
            f"{step_label(name, index, step)} digests {expression!r} rather than the "
            "repository-scoped `secrets.HCLOUD_TOKEN`; GitHub falls back to the "
            "repository secret OF THAT NAME, so a digest of anything else compares "
            "against a value the apply job could never have resolved",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Gated Production Apply Applies the Reviewed Plan
# --------------------------------------------------------------------------


class TestEveryApplyIsGatedAndPerEnvironment(unittest.TestCase):
    """MODIFIED requirement: Gated Production Apply Applies the Reviewed Plan.

    `test_ci_configuration.TestSavedPlanIsWhatGetsApplied` locates the apply
    job by `environment == "production"`, a literal this change removes from
    the workflow. Those assertions are recorded in this change's test-plan.md as
    superseded and are not edited here. What follows is the same three
    properties re-stated over the shape the delta describes: every apply job
    declares an `environment:` resolved from a declaration, each depends on its
    plan job, and each applies that job's saved plan.
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(APPLY)
        self.applying = jobs_running(self.workflow, TERRAFORM_APPLY)

    def test_the_workflow_still_applies(self) -> None:
        """SPECIFIED -- guards every assertion below from passing over a
        workflow that no longer applies anything."""
        self.assertTrue(self.applying, "no job in apply.yml runs `terraform apply`")

    def test_every_apply_job_declares_an_environment(self) -> None:
        """SPECIFIED -- "Every environment's apply job SHALL declare an
        `environment:`", and scenario "Merge does not apply immediately". An
        apply job with no `environment:` holds a write-capable token in an
        ungated job, which is the failure Credential Scoping by Privilege
        exists to prevent -- and omitting it is how an ungated environment would
        be reached by mistake rather than by its Environment having no
        reviewer."""
        self.test_the_workflow_still_applies()
        offenders = sorted(
            name for name, job in self.applying.items() if declared_environment(job) is None
        )
        self.assertEqual(
            [],
            offenders,
            f"these jobs run `terraform apply` and declare no `environment:`: {offenders}",
        )

    def test_no_apply_job_names_its_environment_as_a_literal(self) -> None:
        """SPECIFIED -- Each Environment Declares Its Own Pipeline
        Configuration: a workflow SHALL NOT "map an environment to its ...
        Environment name in workflow text", and scenario "A shared module
        change reaches every environment": each environment applies "under its
        own GitHub Environment's protection rules"."""
        self.test_the_workflow_still_applies()
        offenders = []
        for name, job in sorted(self.applying.items()):
            environment = declared_environment(job) or ""
            if "${{" not in environment:
                offenders.append(f"{name}: `environment: {environment}`")
        self.assertEqual(
            [],
            offenders,
            "these apply jobs name their GitHub Environment as a literal, so a second "
            f"environment cannot be applied without editing apply.yml: {offenders}",
        )

    def test_each_apply_job_depends_on_a_job_that_plans(self) -> None:
        """SPECIFIED -- "An **apply job** that depends on the plan job", and
        scenario "Reviewer sees the exact diff before approving"."""
        self.test_the_workflow_still_applies()
        planning = set(jobs_running(self.workflow, TERRAFORM_PLAN))
        self.assertTrue(planning, "no job in apply.yml runs `terraform plan`")
        offenders = [
            f"{name}: needs {needs_of(job)}"
            for name, job in sorted(self.applying.items())
            if not (set(needs_of(job)) & planning)
        ]
        self.assertEqual(
            [],
            offenders,
            "these apply jobs depend on no job that plans, so nothing guarantees the "
            f"reviewer had a diff to read before approving: {offenders}",
        )

    def test_each_apply_job_applies_a_saved_plan_and_recomputes_none(self) -> None:
        """SPECIFIED -- scenario "Applied changes match the approved plan": the
        apply job "SHALL apply the saved `tfplan` artifact produced by the plan
        job for that same environment", and the requirement's "rather than
        recomputing a plan afterwards"."""
        self.test_the_workflow_still_applies()
        offenders = []
        for name, job in sorted(self.applying.items()):
            for _, _, lines in invoking_steps(job, TERRAFORM_APPLY):
                for line in lines:
                    if not re.search(r"terraform\s+apply\b[^\n]*\btfplan\b", line):
                        offenders.append(f"{name}: applies without naming a saved plan file")
            if any(True for _ in invoking_steps(job, TERRAFORM_PLAN)):
                offenders.append(f"{name}: recomputes a plan after approval")
        self.assertEqual([], sorted(set(offenders)), "; ".join(sorted(set(offenders))))

    def test_the_saved_plan_artifact_is_named_per_environment(self) -> None:
        """SPECIFIED -- "the artifact SHALL be named per environment so that one
        environment's plan cannot be applied to another"."""
        self.test_the_workflow_still_applies()
        artifact_steps = [
            (job, index, step)
            for job, index, step in steps(self.workflow)
            if "upload-artifact" in str(step.get("uses", ""))
            or "download-artifact" in str(step.get("uses", ""))
        ]
        self.assertTrue(
            artifact_steps,
            "apply.yml uploads and downloads no artifact, so the plan the reviewer saw "
            "is not the plan the apply job applies",
        )
        offenders = []
        for job, index, step in artifact_steps:
            name = compact((step.get("with") or {}).get("name", ""))
            if not name:
                offenders.append(f"{step_label(job, index, step)}: declares no artifact name")
            elif "matrix." not in name:
                offenders.append(f"{step_label(job, index, step)}: artifact name {name!r} is constant")
        self.assertEqual(
            [],
            offenders,
            "these artifact steps name the plan file the same way for every "
            f"environment, so one environment's plan can be applied to another: {offenders}",
        )

    def test_the_reviewer_reads_the_plan_from_the_run_summary(self) -> None:
        """SPECIFIED -- scenario "Reviewer sees the exact diff before
        approving": "the completed plan job's summary SHALL already display the
        full plan output for the merge commit and identify which environment it
        belongs to"."""
        planning = jobs_running(self.workflow, TERRAFORM_PLAN)
        self.assertTrue(planning, "no job in apply.yml runs `terraform plan`")
        offenders = []
        for name, job in sorted(planning.items()):
            body = yaml.safe_dump(job, sort_keys=True)
            if "GITHUB_STEP_SUMMARY" not in body:
                offenders.append(f"{name}: writes nothing to the run's job summary")
            elif "matrix." not in compact(body):
                offenders.append(f"{name}: its summary carries no matrix value")
        self.assertEqual(
            [],
            offenders,
            "the reviewer approving an Environment sees only the run's summary; these "
            "plan jobs either write no summary or write one that does not say which "
            f"environment it belongs to: {offenders}",
        )


class TestTheAffectedEnvironmentSetIsResolvedFailClosed(unittest.TestCase):
    """MODIFIED requirement: Gated Production Apply Applies the Reviewed Plan --
    "The set of affected environments SHALL be resolved fail-closed", and Pull
    Request Plan Visibility -- "Where the set of affected environments cannot be
    resolved, the workflow SHALL fail rather than resolve it to the empty set".

    The refusal is exercised; the mapping is read. The two halves are asserted
    differently on purpose, and the difference is recorded rather than glossed:

    - The REFUSAL takes no knowledge of the step's input shape. Every value it
      declares through `env:` is set to the empty string -- which is precisely
      what an unresolvable comparison base, a skipped filter or a step that did
      not conclude leaves behind -- and the step must exit non-zero.
    - The MAPPING (`terraform/modules/` selects every environment,
      `terraform/stacks/<name>/` selects that one) is asserted as a read
      of the body, because the shape in which the changed paths reach the step
      is not fixed by this change's plan. Its behavioural verification is
      tasks.md 3.3's, run by the implementing author against each case. This is
      recorded in test-plan.md as a scenario covered structurally rather than
      behaviourally, not as one covered.
    """

    def _resolution_step(self, path: Path):
        workflow = load_yaml(path)
        candidates = []
        for name, job in jobs(workflow).items():
            for index, step in expression_free_run_steps(job):
                body = str(step["run"])
                if "terraform/stacks" not in body or "terraform/modules" not in body:
                    continue
                # An input arriving through `env:` is what makes this the
                # resolution step rather than the formatting-and-validation
                # loop that already walks both directories: that loop reads the
                # working tree and takes nothing from the event, so it declares
                # no expression to take. Without this clause the locator matches
                # it, and every assertion below reports on a step that resolves
                # no environment set at all.
                declared = (step.get("env") or {}).values()
                if "GITHUB_OUTPUT" not in body:
                    continue
                if any(ACTIONS_EXPRESSION.search(str(value)) for value in declared):
                    candidates.append((name, index, step))
        self.assertEqual(
            1,
            len(candidates),
            f"expected exactly one `run:` step in {path.name} that carries no `${{{{ }}}}` "
            "and names both `terraform/modules` and `terraform/stacks` -- the "
            "step resolving which environments a change affects -- but found "
            f"{len(candidates)}: "
            + repr([step_label(name, index, step) for name, index, step in candidates])
            + ". The mapping is 'a change under `terraform/modules/` affects every "
            "environment, and a change under `terraform/stacks/<name>/` affects "
            "only that environment'; a step naming only one of the two cannot express "
            "it, and a step carrying an Actions expression cannot be executed by this "
            "suite (tasks.md 3.3, 3.4)",
        )
        return candidates[0]

    def test_the_apply_workflow_resolves_which_environments_a_merge_affects(self) -> None:
        """SPECIFIED -- "**An environment SHALL enter the run only where the
        merge could affect that environment**", and scenario "A merge affecting
        one environment raises no other environment's approval": a merge
        touching only one environment SHALL raise no other Environment's
        approval request."""
        self._resolution_step(APPLY)

    def test_the_pull_request_workflow_resolves_which_environments_are_affected(self) -> None:
        """SPECIFIED -- "The environments a pull request can affect SHALL be
        determined from the paths it changes", and scenarios "A shared module
        change is planned against every environment" and "An environment-scoped
        change is planned against that environment only"."""
        self._resolution_step(PR_VALIDATION)

    def test_the_resolution_refuses_an_unresolvable_input_rather_than_emptying_it(self) -> None:
        """SPECIFIED -- scenario "An unresolvable set of affected environments
        fails the run": "the workflow SHALL fail with a message identifying that
        resolution as the cause, and SHALL NOT proceed as though no environment
        were affected".

        The empty string is what the failure actually looks like: `apply.yml`
        runs on `push`, where `github.event.before` is all zeroes on a branch's
        first push and unresolvable after a force-push, and where a step that
        did not conclude leaves its outputs empty. Reading that as "no
        environment affected" applies nothing for a merge that did change
        infrastructure and reports a green run.
        """
        require_external_tools(
            self, ("bash",), "execute the affected-environment resolution body"
        )
        for path in (APPLY, PR_VALIDATION):
            with self.subTest(workflow=path.name):
                name, index, step = self._resolution_step(path)
                declared = sorted(step.get("env") or {})
                self.assertTrue(
                    declared,
                    f"{step_label(name, index, step)} declares no `env:` block, so it "
                    "either takes its inputs through an Actions expression -- which "
                    "this suite cannot execute -- or reads them from somewhere this "
                    "assertion cannot empty (tasks.md 3.4)",
                )
                scratch = Path(tempfile.mkdtemp(prefix="affected-environments-"))
                self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
                (scratch / "terraform" / "stacks").mkdir(parents=True)
                outputs = scratch / "github_output"
                summary = scratch / "step_summary"
                outputs.touch()
                summary.touch()
                environment = dict(
                    os.environ,
                    GITHUB_OUTPUT=str(outputs),
                    GITHUB_ENV=str(outputs),
                    GITHUB_STEP_SUMMARY=str(summary),
                    GITHUB_WORKSPACE=str(scratch),
                )
                for key in declared:
                    environment[key] = ""
                result = run_snippet(str(step["run"]), environment, scratch)
                combined = (result.stdout + result.stderr).strip()
                self.assertNotEqual(
                    0,
                    result.returncode,
                    f"{path.name}: the resolution concluded successfully with every "
                    "input empty -- the state an unresolvable comparison base or a step "
                    "that did not conclude leaves behind. Whatever it wrote, the run "
                    "then proceeds as though no environment were affected, applies "
                    f"nothing and reports green: {combined[-800:]!r}",
                )


class TestTheApplyWorkflowStillRaisesNoApprovalForNonInfrastructure(unittest.TestCase):
    """MODIFIED requirement: Gated Production Apply Applies the Reviewed Plan --
    the workflow-level path filter, carried through unchanged.

    `test_ci_configuration.TestApplyWorkflowTriggerIsPathFiltered` asserts the
    filter's patterns. What it does not assert, and what this change makes
    possible to get wrong, is that the filter names no environment: a filter
    written as `terraform/stacks/prod/**` would keep every existing
    assertion green while silently making the apply workflow blind to a second
    environment.
    """

    def test_the_path_filter_names_no_single_environment(self) -> None:
        """SPECIFIED -- Each Environment Declares Its Own Pipeline
        Configuration: adding an environment SHALL require "no change to any
        file under `.github/workflows/`", together with scenario "A merge that
        cannot change infrastructure raises no approval request", which the
        filter is what implements."""
        push = triggers(load_yaml(APPLY)).get("push") or {}
        patterns = (push if isinstance(push, dict) else {}).get("paths") or []
        self.assertTrue(
            patterns,
            "apply.yml's push trigger declares no `paths:` filter, so every merge "
            "raises an Environment approval request",
        )
        names = {directory.name for directory in environment_directories()}
        offenders = [
            pattern
            for pattern in patterns
            for name in names
            if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])", str(pattern))
        ]
        self.assertEqual(
            [],
            offenders,
            "apply.yml's path filter names an environment directory, so a merge "
            "touching a second environment would not trigger the workflow at all and "
            f"nothing would apply it: {sorted(set(offenders))}",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Destroy Policy Gate
# --------------------------------------------------------------------------


class TestTheDestroyGateReadsApplicabilityFromTheDeclaration(unittest.TestCase):
    """MODIFIED requirement: Destroy Policy Gate -- "**Whether this gate applies
    is a per-environment policy**, declared by the environment itself ... rather
    than fixed in workflow text."

    Structural, as the gate's existing assertions in `test_ci_configuration.py`
    are, and for the same reason design.md records there: the gate reads
    `terraform show -json`, and this suite may not spawn a Terraform binary. So
    what is asserted is where the gate's applicability COMES FROM, which is a
    static property of the workflow, and not what the gate concludes from a
    plan, which is not reachable from here. The default -- an environment
    declaring nothing is gated -- is exercised against the declaration census
    instead, by
    `TestTheDeclarationCensusIsARealReadOfTheTree
    .test_an_environment_declaring_nothing_about_the_gate_is_gated`.
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(APPLY)
        self.gate_steps = [
            (job, index, step)
            for job, index, step in steps(self.workflow)
            if "resource_changes" in str(step.get("run", ""))
        ]

    def test_the_gate_still_exists(self) -> None:
        """SPECIFIED -- the gate "SHALL inspect its plan's machine-readable form
        (`terraform show -json`)". Guards the assertions below from passing over
        a workflow with no gate."""
        self.assertTrue(
            self.gate_steps,
            "no step in apply.yml inspects a plan's `resource_changes`, so a plan "
            "replacing the production server would reach approval with no objection "
            "raised",
        )

    def test_the_gate_takes_its_applicability_from_the_matrix(self) -> None:
        """SPECIFIED -- scenario "A disposable environment is destroyed without
        an override label": the gate SHALL NOT fail "for an environment whose
        declaration states the gate does not apply". Applicability reaching the
        gate from the matrix is what makes it the DECLARATION's answer; read
        from workflow text it would be one answer for every environment."""
        self.test_the_gate_still_exists()
        offenders = []
        for job, index, step in self.gate_steps:
            surface = compact(
                yaml.safe_dump(
                    {"if": step.get("if"), "env": step.get("env"), "with": step.get("with")},
                    sort_keys=True,
                )
            )
            enclosing = compact(
                yaml.safe_dump((jobs(self.workflow)[job] or {}).get("env"), sort_keys=True)
            )
            if "matrix." not in surface and "matrix." not in enclosing:
                offenders.append(step_label(job, index, step))
        self.assertEqual(
            [],
            offenders,
            "these destroy-policy gate steps read no matrix value, so whether the gate "
            "applies is fixed in workflow text rather than declared by the environment "
            f"-- and a disposable environment could not be torn down without a label: {offenders}",
        )

    def test_the_gate_names_no_environment(self) -> None:
        """SPECIFIED -- Each Environment Declares Its Own Pipeline
        Configuration: a workflow SHALL NOT "name them in a condition". A gate
        conditioned on `prod` is the mapping in workflow text this requirement
        forbids, written as a condition rather than as a table."""
        self.test_the_gate_still_exists()
        names = {directory.name for directory in environment_directories()} | {
            declaration.github_environment
            for declaration in environment_declarations().values()
            if declaration.github_environment
        }
        offenders = []
        for job, index, step in self.gate_steps:
            body = uncommented(yaml.safe_dump(step, sort_keys=True))
            for name in sorted(names):
                if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])", body):
                    offenders.append(f"{step_label(job, index, step)} names `{name}`")
        self.assertEqual([], offenders, "; ".join(offenders))

    def test_the_scheduled_drift_workflow_carries_no_destroy_gate(self) -> None:
        """SPECIFIED -- scenario "Drift-detection plan is not affected by this
        gate": "the destroy-policy gate SHALL NOT fail that workflow; the drift
        is instead reported per the Scheduled Drift Detection requirement". A
        nightly plan showing a deletion is a report, and a gate there would turn
        a persistently reported drift into a persistently red scheduled job --
        which that requirement says is muted in practice."""
        drift = load_yaml(DRIFT)
        offenders = [
            step_label(job, index, step)
            for job, index, step in steps(drift)
            if "resource_changes" in str(step.get("run", ""))
            and re.search(r"exit\s+1|::error", str(step.get("run", "")))
        ]
        self.assertEqual(
            [],
            offenders,
            "these steps in drift.yml inspect a plan's `resource_changes` and fail the "
            f"run on what they find, which is the apply workflow's gate: {offenders}",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Serialized Terraform Runs
# --------------------------------------------------------------------------


class TestConcurrencyIsDeclaredPerEnvironment(unittest.TestCase):
    """MODIFIED requirement: Serialized Terraform Runs.

    "The group SHALL be derived from the environment's own identity, so that two
    environments do not share one, and SHALL be declared **at job level** on the
    jobs that plan and apply an environment."
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(APPLY)
        self.gated = {
            **jobs_running(self.workflow, TERRAFORM_PLAN),
            **jobs_running(self.workflow, TERRAFORM_APPLY),
        }

    def test_the_workflow_declares_no_workflow_level_concurrency_group(self) -> None:
        """SPECIFIED -- "A workflow-level `concurrency` declaration cannot read
        a per-environment value, so a workflow covering more than one
        environment cannot express this requirement there", and scenario "Two
        environments do not queue behind each other": a shared group would
        serialise them for no reason."""
        self.assertNotIn(
            "concurrency",
            load_yaml(APPLY),
            "apply.yml declares a workflow-level `concurrency` group. It cannot read a "
            "matrix value, so every environment queues in one group and a slow apply "
            "in one delays another",
        )

    def test_every_job_that_plans_or_applies_declares_its_own_concurrency_group(self) -> None:
        """SPECIFIED -- "SHALL declare a GitHub Actions `concurrency` group per
        environment with `cancel-in-progress: false`, so that runs queue rather
        than overlap or cancel each other", and scenario "Two merges in quick
        succession apply in order"."""
        self.assertTrue(self.gated, "no job in apply.yml plans or applies")
        offenders = []
        for name, job in sorted(self.gated.items()):
            concurrency = job.get("concurrency")
            if not concurrency:
                offenders.append(f"{name}: declares no job-level `concurrency`")
                continue
            group = compact(
                concurrency.get("group") if isinstance(concurrency, dict) else concurrency
            )
            if "matrix." not in group:
                offenders.append(
                    f"{name}: its concurrency group {group!r} reads no matrix value, so "
                    "two environments share it"
                )
            if isinstance(concurrency, dict) and concurrency.get("cancel-in-progress") is not False:
                offenders.append(
                    f"{name}: does not set `cancel-in-progress: false`, so a queued run "
                    "cancels the one applying rather than waiting for it"
                )
        self.assertEqual([], offenders, "; ".join(offenders))


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Scheduled Drift Detection
# --------------------------------------------------------------------------


class TestDriftDetectionIsPerEnvironment(unittest.TestCase):
    """MODIFIED requirement: Scheduled Drift Detection."""

    def setUp(self) -> None:
        self.workflow = load_yaml(DRIFT)
        self.planning = jobs_running(self.workflow, TERRAFORM_PLAN)

    def test_the_workflow_is_scheduled_and_manually_triggerable(self) -> None:
        """SPECIFIED -- "A scheduled GitHub Actions workflow SHALL run
        `terraform plan` against every environment on a recurring nightly
        schedule", and "The workflow SHALL also be triggerable via
        `workflow_dispatch`". Carried through unchanged by the delta; guards
        every assertion below from reading a workflow that no longer runs."""
        on = triggers(self.workflow)
        self.assertIn("schedule", on, "drift.yml declares no `schedule:` trigger")
        self.assertIn(
            "workflow_dispatch",
            on,
            "drift.yml declares no `workflow_dispatch:` trigger, so it cannot be "
            "verified after GitHub disables it for repository inactivity",
        )

    def test_the_drift_plan_runs_over_every_discovered_environment(self) -> None:
        """SPECIFIED -- "SHALL run `terraform plan` against every environment".
        Unlike the two other workflows this is unconditioned on changed paths:
        drift is divergence from what was committed, which no diff predicts."""
        self.assertTrue(self.planning, "no job in drift.yml runs `terraform plan`")
        offenders = []
        for name, job in sorted(self.planning.items()):
            if not (job.get("strategy") or {}).get("matrix"):
                offenders.append(f"{name}: declares no `strategy.matrix`")
            elif not matrix_source_jobs(self.workflow, job):
                offenders.append(f"{name}: builds its matrix from workflow text rather than discovery")
        self.assertEqual([], offenders, "; ".join(offenders))

    def test_one_environments_failure_does_not_silence_the_rest(self) -> None:
        """SPECIFIED -- scenario "One environment's failure does not silence the
        rest": "every other environment SHALL still be planned and reported, and
        the run SHALL surface the failure rather than concluding successfully".
        A sweep that stops at the first failure leaves every environment after
        it unchecked, which is silence indistinguishable from no drift."""
        self.assertTrue(self.planning, "no job in drift.yml runs `terraform plan`")
        offenders = [
            name
            for name, job in sorted(self.planning.items())
            if (job.get("strategy") or {}).get("fail-fast") is not False
        ]
        self.assertEqual(
            [],
            offenders,
            f"these drift matrix jobs do not set `fail-fast: false`: {offenders}",
        )

    def test_the_drift_issue_is_identified_per_environment(self) -> None:
        """SPECIFIED -- "The issue SHALL be identified per environment, so that
        drift in one environment neither opens a second issue for another nor
        closes another's", and scenarios "Repeated drift does not open duplicate
        issues" and "Drift in one environment does not resolve another's
        report".

        Asserted as the issue's identifying text being derived from the
        environment rather than constant. At one environment a constant title
        and a derived one behave identically, which is why tasks.md 4.5 requires
        this read statically rather than observed on a run.
        """
        candidates = []
        for job, index, step in steps(self.workflow):
            body = compact(yaml.safe_dump(step, sort_keys=True))
            if re.search(r"issue", body, re.IGNORECASE) and (
                step.get("uses") or step.get("run")
            ):
                candidates.append((job, index, step, body))
        self.assertTrue(
            candidates,
            "no step in drift.yml refers to an issue, so a non-empty plan is reported "
            "by failing the workflow alone -- which the requirement calls insufficient, "
            "since a persistently red scheduled job is muted in practice",
        )
        derived = [label for label in candidates if "matrix." in label[3]]
        self.assertTrue(
            derived,
            "no step in drift.yml that touches a drift issue reads a matrix value, so "
            "one title serves every environment: a second environment's drift would "
            "overwrite the first's issue, and one environment's clean plan would close "
            "the other's report. The steps found were "
            + repr([step_label(job, index, step) for job, index, step, _ in candidates]),
        )

    def test_the_drift_plan_does_not_take_the_state_lock(self) -> None:
        """SPECIFIED -- scenario "Drift plan does not contend with an apply":
        "the drift plan SHALL proceed without waiting on or failing due to the
        lock, because it runs with `-lock=false`". Carried through unchanged by
        the delta, and stated here because this change moves every plan in this
        workflow into a matrix job -- a move that can drop a flag silently."""
        self.assertTrue(self.planning, "no job in drift.yml runs `terraform plan`")
        offenders = []
        for name, job in sorted(self.planning.items()):
            for _, _, lines in invoking_steps(job, TERRAFORM_PLAN):
                for line in lines:
                    if "-lock=false" not in line:
                        offenders.append(f"{name}: plans without `-lock=false`")
        self.assertEqual(
            [],
            sorted(set(offenders)),
            "these scheduled plans take the state lock, so a nightly read-only sweep "
            f"collides with an in-flight apply and reports a spurious failure: {sorted(set(offenders))}",
        )

    def test_the_reporting_job_depends_on_every_other_job(self) -> None:
        """DERIVED (tasks.md 4.5) -- no scenario states it. The requirement
        obliges the sweep to report rather than to fail silently; that the
        reporting job must name every other job in `needs:` is the task's own
        verification condition, "since a skipped dependency reads as
        non-failure to its heartbeat". Reconsider this assertion, do not weaken
        it, if the heartbeat learns to distinguish a skip another way."""
        declared = jobs(self.workflow)
        self.assertTrue(declared, "drift.yml declares no jobs")
        depended_on = {
            need for job in declared.values() for need in needs_of(job)
        }
        sinks = sorted(set(declared) - depended_on)
        self.assertEqual(
            1,
            len(sinks),
            "expected exactly one job in drift.yml that no other job depends on -- the "
            "job concluding on the sweep's behalf, whose result is what the heartbeat "
            f"reads -- but found {sinks} among {sorted(declared)}. Two such jobs means "
            "two conclusions and no single one to read; none means a cycle",
        )
        sink = sinks[0]
        missing = sorted(set(declared) - set(needs_of(declared[sink])) - {sink})
        self.assertEqual(
            [],
            missing,
            f"the concluding job `{sink}` does not name {missing} in its `needs:`, so "
            "a skipped job reads to it as one that did not fail and the sweep reports "
            "success having planned nothing for that environment",
        )


# --------------------------------------------------------------------------
# iac-safety-hardening / Write Credentials Confined to the Gated Pipeline
# --------------------------------------------------------------------------

# The prohibition, in the words AGENTS.md states it in today. Matched as
# fragments rather than as a sentence, so ordinary editing around them does not
# fail the assertion while a rephrasing of the rule itself does -- which is the
# same standard `TestTheArchivedRecordCorrectionRuleIsStated` in
# `test_ci_configuration.py` is written to, for the same reason: this wording is
# what a coding agent reads before touching Terraform, so a change to it is a
# reviewed event rather than an editorial one.
WRITE_CREDENTIAL_BOUNDARY_FRAGMENTS = (
    "is never run locally",
    "only through the gated",
)

# The README states the same prohibition in its own words, and is read by
# anchor-and-neighbourhood rather than by transcription; see the assertion
# below for why the two records are probed differently.
WRITE_CREDENTIAL_ANCHOR = "Read & Write"
WRITE_CREDENTIAL_LOCALITY = 400


class TestTheWriteCredentialBoundaryIsStatedToAgents(unittest.TestCase):
    """MODIFIED requirement: Write Credentials Confined to the Gated Pipeline
    (iac-safety-hardening).

    "The prohibition SHALL be recorded where it is loaded without being sought:
    the repository README runbook for human operators, and a repository-root
    `AGENTS.md` for coding agents."

    This establishes only that the boundary is STATED. It does not establish
    that any token is where the requirement says it is: which secrets a GitHub
    Environment holds, and what is on an operator's workstation, are neither
    repository content nor reachable without a network call. Those scenarios are
    recorded in this change's test-plan.md as beyond every test command this
    project has.
    """

    def setUp(self) -> None:
        self.text = read_text(AGENTS_FILE)

    def test_the_conventions_file_states_that_apply_is_not_run_locally(self) -> None:
        """SPECIFIED -- scenario "An agent opening the repository is told the
        boundary": "a repository-root `AGENTS.md` SHALL state that
        infrastructure changes reach Hetzner only through the gated pipeline
        and that `terraform apply` is not run locally".

        The citation formerly read "production changes"; `add-a-staging-environment`
        widened the scenario to "infrastructure changes" at the point where a
        second environment existed to be silently excluded by the narrower
        word. Only the quotation moved -- the fragments this assertion matches
        survive the generalisation untouched, and weakening them to accommodate
        it would be the opposite of what that change did."""
        flat = flattened(self.text)
        missing = [
            fragment for fragment in WRITE_CREDENTIAL_BOUNDARY_FRAGMENTS if fragment not in flat
        ]
        self.assertEqual(
            [],
            missing,
            "AGENTS.md does not state the write-credential boundary in the words this "
            f"assertion is written against: {missing} not found. The rule is that "
            "`terraform apply` is never run locally and that production changes reach "
            "Hetzner only through the gated pipeline",
        )

    def test_the_boundary_is_stated_outside_the_generated_workflow_block(self) -> None:
        """DERIVED -- no scenario states it. The requirement says the record
        must be where it is "loaded without being sought"; that the top of
        AGENTS.md is a generated block replaced on update is this repository's
        own convention, so a rule stated inside it would satisfy the assertion
        above today and silently stop being true on the next regeneration. Same
        reasoning, and the same marker, as
        `test_ci_configuration.TestTheArchivedRecordCorrectionRuleIsStated
        .test_the_correction_rule_is_stated_outside_the_generated_block`."""
        end = self.text.find(MANAGED_BLOCK_END)
        self.assertNotEqual(
            -1,
            end,
            f"AGENTS.md carries no {MANAGED_BLOCK_END!r} marker, so this assertion "
            "cannot tell the generated block from the project's own conventions",
        )
        below = flattened(self.text[end + len(MANAGED_BLOCK_END) :])
        missing = [
            fragment for fragment in WRITE_CREDENTIAL_BOUNDARY_FRAGMENTS if fragment not in below
        ]
        self.assertEqual(
            [],
            missing,
            "the write-credential boundary is not stated below the generated workflow "
            f"block, so it sits where the next regeneration replaces it: {missing}",
        )

    def test_the_readme_states_the_boundary_for_human_operators(self) -> None:
        """SPECIFIED -- same sentence, its first half: "the repository README
        runbook for human operators".

        Anchored on the token the prohibition is ABOUT and read in its
        neighbourhood, rather than transcribed from the README's current
        sentence. The two records are held to different standards deliberately:
        AGENTS.md's wording is what the scenario names and is matched as
        written, while the README is a runbook whose prose this change's own
        tasks.md 6.1 edits -- a transcription would report a false offence on
        that edit, and the repair for a false offence is to loosen the
        assertion, which is the repair this suite must never need.
        """
        readme = flattened(read_text(ROOT / "README.md"))
        anchor = readme.find(WRITE_CREDENTIAL_ANCHOR)
        self.assertNotEqual(
            -1,
            anchor,
            f"README.md does not mention {WRITE_CREDENTIAL_ANCHOR!r}, so there is no "
            "statement of which token an operator may hold for this assertion to read",
        )
        # Centred on the anchor rather than started at it: the prohibition's
        # verb precedes the token it is about ("Never put the **Read & Write**
        # token ..."), so a window opening at the anchor cuts the word the
        # assertion is looking for out of its own evidence.
        start = max(0, anchor - WRITE_CREDENTIAL_LOCALITY)
        neighbourhood = readme[start : anchor + WRITE_CREDENTIAL_LOCALITY].lower()
        for word in ("never", "local"):
            self.assertIn(
                word,
                neighbourhood,
                "the README mentions the Read & Write token without stating, nearby, "
                "that it is never held locally -- so an operator reading the runbook is "
                f"not told the boundary: {neighbourhood[:300]!r}",
            )


# --------------------------------------------------------------------------
# The declaration is not self-describing prose
# --------------------------------------------------------------------------


class TestTheDeclarationReaderIsARealReadOfTheFile(
    DeclarationTreeFixtureMixin, unittest.TestCase
):
    """ADDED requirement: Each Environment Declares Its Own Pipeline
    Configuration.

    The field resolution above is the one piece of machinery every other
    assertion in this file depends on: if it silently resolved nothing, the
    census would report no offence, the literal sweep would look for no name and
    the destroy-gate default would be read off a value nobody wrote. This class
    reads a declaration whose values are known and asserts they come back.
    """

    def test_the_reader_returns_the_values_the_declaration_states(self) -> None:
        """DERIVED -- no scenario states it; it is what stops every SPECIFIED
        assertion in this file from passing over a reader that returns
        nothing."""
        scratch = self._scratch()
        self._write_tree(
            scratch,
            {"staging": self._declaration_for("HCLOUD_TOKEN_STAGING", "staging", gate=False)},
        )
        declarations = environment_declarations(scratch)
        self.assertEqual(["staging"], sorted(declarations))
        declaration = declarations["staging"]
        self.assertEqual([], declaration.offences, "; ".join(declaration.offences))
        self.assertEqual("HCLOUD_TOKEN_STAGING", declaration.read_only_secret)
        self.assertEqual("staging", declaration.github_environment)
        self.assertFalse(
            declaration.destroy_gate_applies,
            "a declaration stating the destroy-policy gate inapplicable was read as "
            "gated, so an environment that exists to be rebuilt could not be torn down "
            "without a label",
        )

    def test_a_terraform_file_is_never_read_as_a_declaration(self) -> None:
        """DERIVED (tasks.md 2.2) -- guards the discovery above from picking up
        Terraform configuration as a declaration, which would make the census's
        verdict depend on whether a `.tf` file happens to parse as YAML."""
        scratch = self._scratch()
        self._write_tree(scratch, {"staging": None})
        directory = scratch / "terraform" / "stacks" / "staging"
        (directory / "terraform.tfvars").write_text(
            'server_name: "web"\nlocation: "hel1"\n', encoding="utf-8"
        )
        self.assertEqual(
            [],
            declaration_candidates(directory),
            "a Terraform variables file was read as a pipeline declaration",
        )


# --------------------------------------------------------------------------
# Added by the implementing author, not by the author of the module above.
#
# Two things `test-plan.md` recorded as covered only structurally, and one of
# them as "the largest gap in this pass". Both were left open there because the
# shape in which a step's inputs arrive was not fixed by the change's plan, and
# inventing one would have failed a legitimate implementation. The
# implementation now fixes both shapes, so the behaviour is reachable, and the
# verifications tasks.md 3.3, 4.1a and 4.1b describe are made durable here
# rather than left as a run someone did once on a workstation.
# --------------------------------------------------------------------------


def _resolution_step_of(case: unittest.TestCase, path: Path):
    """The affected-environment resolution step, and which of its `env:` keys
    carries which input.

    The inputs are told apart by the STEP each expression reads from, never by
    the name the implementation gave the variable: the discovery input reads the
    output of the step this module's discovery locator finds, and the
    changed-path input reads some other step's.
    """
    workflow = load_yaml(path)
    discovery_ids = {
        str(step.get("id"))
        for _, _, step in steps(workflow)
        if step.get("run")
        and step.get("id")
        and "terraform/stacks" in str(step["run"])
        and "terraform/modules" not in str(step["run"])
        and "GITHUB_OUTPUT" in str(step["run"])
        and not ACTIONS_EXPRESSION.search(str(step["run"]))
    }
    case.assertEqual(
        1,
        len(discovery_ids),
        f"expected exactly one identified discovery step in {path.name}, found "
        f"{sorted(discovery_ids)}",
    )
    discovery_id = discovery_ids.pop()

    candidates = []
    for job_name, index, step in steps(workflow):
        body = str(step.get("run") or "")
        if not body or ACTIONS_EXPRESSION.search(body):
            continue
        if "terraform/stacks" not in body or "terraform/modules" not in body:
            continue
        if "GITHUB_OUTPUT" not in body:
            continue
        inputs = {}
        for key, value in (step.get("env") or {}).items():
            expression = compact(value)
            if f"steps.{discovery_id}.outputs." in expression:
                inputs["stacks"] = key
            elif ACTIONS_EXPRESSION.search(str(value)):
                inputs["paths"] = key
        if {"stacks", "paths"} <= set(inputs):
            candidates.append((job_name, index, step, inputs))
    case.assertEqual(
        1,
        len(candidates),
        f"expected exactly one resolution step in {path.name} taking both the "
        f"discovery step's output and a changed-path input through `env:`, found "
        f"{len(candidates)}: "
        + repr([step_label(j, i, s) for j, i, s, _ in candidates]),
    )
    return candidates[0]


def _run_with(case: unittest.TestCase, script: str, assignments: dict):
    """Run a step body with `$GITHUB_OUTPUT` pointed at a scratch file, and
    return (result, the pairs it wrote)."""
    scratch = Path(tempfile.mkdtemp(prefix="step-body-"))
    case.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
    outputs = scratch / "github_output"
    summary = scratch / "step_summary"
    outputs.touch()
    summary.touch()
    environment = dict(
        os.environ,
        GITHUB_OUTPUT=str(outputs),
        GITHUB_ENV=str(outputs),
        GITHUB_STEP_SUMMARY=str(summary),
        GITHUB_WORKSPACE=str(scratch),
    )
    environment.update(assignments)
    return run_snippet(script, environment, scratch), github_output_pairs(outputs)


PROD_ROW = {
    "name": "prod",
    "github_environment": "production",
    "read_only_secret": "HCLOUD_TOKEN",
    "destroy_policy_gate": True,
}
STAGING_ROW = {
    "name": "staging",
    "github_environment": "staging",
    "read_only_secret": "HCLOUD_TOKEN_STAGING",
    "destroy_policy_gate": False,
}


class TestTheAffectedEnvironmentMappingIsRunRatherThanRead(unittest.TestCase):
    """MODIFIED requirements: Pull Request Plan Visibility; Gated Production
    Apply Applies the Reviewed Plan.

    "a change under `terraform/modules/` affects every environment, and a change
    under `terraform/stacks/<name>/` affects only that environment."

    `TestTheAffectedEnvironmentSetIsResolvedFailClosed` executes the REFUSAL and
    reads the mapping, and this change's `test-plan.md` records the unexecuted
    mapping as that pass's largest gap — deliberately, because the input's shape
    was not fixed when those tests were written. It is fixed now, and the three
    scenarios that turn on the mapping are asserted at one environment only by
    running it over a two-environment set. At N=1 every one of them is
    unfalsifiable against the committed tree.
    """

    def setUp(self) -> None:
        require_external_tools(
            self, ("bash", "jq"), "execute the affected-environment mapping"
        )
        self.both = json.dumps([PROD_ROW, STAGING_ROW])

    def _resolve(self, path: Path, changed: str):
        _, _, step, inputs = _resolution_step_of(self, path)
        result, written = _run_with(
            self,
            str(step["run"]),
            {inputs["stacks"]: self.both, inputs["paths"]: changed},
        )
        detail = (result.stdout + result.stderr).strip()[-600:]
        self.assertEqual(
            0, result.returncode, f"{path.name}: the resolution refused {changed!r}: {detail!r}"
        )
        emitted = [
            value
            for value in written.values()
            if value.strip().startswith("[") or value.strip().startswith("{")
        ]
        self.assertEqual(
            1,
            len(emitted),
            f"{path.name}: expected exactly one JSON output naming the affected "
            f"environments, got {written!r}",
        )
        return sorted(entry["name"] for entry in json.loads(emitted[0]))

    def test_a_shared_module_change_selects_every_environment(self) -> None:
        """SPECIFIED -- scenarios "A shared module change is planned against
        every environment" and "A shared module change reaches every
        environment"."""
        for path in (PR_VALIDATION, APPLY):
            with self.subTest(workflow=path.name):
                self.assertEqual(
                    ["prod", "staging"],
                    self._resolve(path, "terraform/modules/server/main.tf\n"),
                    "a change to a module every environment consumes selected fewer "
                    "than every environment",
                )

    def test_an_environment_scoped_change_selects_that_environment_only(self) -> None:
        """SPECIFIED -- scenarios "An environment-scoped change is planned
        against that environment only" and "A merge affecting one environment
        raises no other environment's approval". The second is the one that
        matters most: an approval prompt raised with nothing to approve trains
        the approver to grant it without reading."""
        for path in (PR_VALIDATION, APPLY):
            with self.subTest(workflow=path.name):
                self.assertEqual(
                    ["staging"],
                    self._resolve(path, "terraform/stacks/staging/main.tf\n"),
                    "a change confined to one environment selected another as well",
                )

    def test_changes_in_two_environments_select_both(self) -> None:
        """SPECIFIED -- the same two scenarios, read forward: selecting "only
        that environment" is a filter, not a choice of one."""
        for path in (PR_VALIDATION, APPLY):
            with self.subTest(workflow=path.name):
                self.assertEqual(
                    ["prod", "staging"],
                    self._resolve(
                        path,
                        "terraform/stacks/prod/terraform.tfvars\n"
                        "terraform/stacks/staging/main.tf\n",
                    ),
                )

    def test_a_change_touching_no_environment_selects_none(self) -> None:
        """SPECIFIED -- "A pull request affecting no environment SHALL produce
        no plan", and scenario "A merge that cannot change infrastructure raises
        no approval request".

        Distinct from the refusal `TestTheAffectedEnvironmentSetIsResolvedFailClosed`
        exercises, and the distinction is the whole fail-closed argument: an
        input that RESOLVED to nothing affected is accepted, an input that could
        not be resolved is refused. A step that refused both would satisfy that
        class and plan nothing, ever.
        """
        for path in (PR_VALIDATION, APPLY):
            with self.subTest(workflow=path.name):
                self.assertEqual([], self._resolve(path, "docs/bootstrap-a-new-host.md\n"))


class TestThePlanAggregationDiscriminates(unittest.TestCase):
    """MODIFIED requirement: Pull Request Plan Visibility; Required Status Checks
    Report on Every Pull Request (carried through).

    `TestTheAggregatingValidateJobCoversThePlanMatrix` reads the `needs:` edges
    that let `validate` see the matrix's result. This runs the step that acts on
    them, once per row of the table tasks.md 4.1a describes — the same
    extract-and-run shape `test_ci_configuration.TestTheAggregatingGateDiscriminates`
    uses for `ansible-verify`'s gate, and for the same reason: reading
    establishes that a conclusion exists, running establishes that it
    discriminates.

    A green run here does NOT establish that this conclusion blocks anything.
    Blocking is branch protection — repository settings this suite makes no
    network call to read.
    """

    def setUp(self) -> None:
        require_external_tools(self, ("bash",), "execute the plan aggregation's body")
        self.workflow = load_yaml(PR_VALIDATION)

    def _concluding_step(self):
        """The `validate` job's concluding step, with its inputs identified by
        the expressions its `env:` assigns rather than by their names."""
        declared = jobs(self.workflow)
        self.assertIn("validate", declared, "pr-validation.yml declares no `validate` job")
        validate = declared["validate"]
        planning = set(jobs_running(self.workflow, TERRAFORM_PLAN))
        self.assertTrue(planning, "no job in pr-validation.yml runs `terraform plan`")

        candidates = []
        for index, step in expression_free_run_steps(validate):
            inputs = {}
            for key, value in (step.get("env") or {}).items():
                expression = compact(value)
                match = re.search(r"needs\.([A-Za-z0-9_-]+)\.result", expression)
                if match:
                    inputs["plan" if match.group(1) in planning else "discover"] = key
                elif re.search(r"needs\.[A-Za-z0-9_-]+\.outputs\.", expression):
                    inputs["expected"] = key
            if {"plan", "discover", "expected"} <= set(inputs):
                candidates.append((index, step, inputs))
        self.assertEqual(
            1,
            len(candidates),
            "expected exactly one expression-free `run:` step in `validate` whose "
            "`env:` carries the plan matrix's result, the discovery job's result and a "
            "discovery output saying whether a plan was owed — the step that concludes "
            f"on the matrix's behalf — but found {len(candidates)}. The step's inputs "
            "arrive through `env:` so that its body can be executed standalone; a "
            "conclusion written as an `if:` expression cannot be exercised at all",
        )
        return candidates[0]

    def _conclude(self, discover: str, plan: str, expected: str):
        _, step, inputs = self._concluding_step()
        result, _ = _run_with(
            self,
            str(step["run"]),
            {
                inputs["discover"]: discover,
                inputs["plan"]: plan,
                inputs["expected"]: expected,
            },
        )
        return result

    def test_a_planned_and_passing_run_concludes_success(self) -> None:
        """SPECIFIED -- the ordinary case, and the converse every refusal below
        needs: a conclusion that refused every row would satisfy all of them and
        make every pull request unmergeable."""
        result = self._conclude("success", "success", "true")
        self.assertEqual(
            0,
            result.returncode,
            "the conclusion refused a run whose discovery succeeded and whose plan "
            f"matrix passed: {(result.stdout + result.stderr)[-600:]!r}",
        )

    def test_a_pull_request_affecting_no_environment_concludes_success(self) -> None:
        """SPECIFIED -- "A pull request affecting no environment SHALL produce no
        plan". The matrix is empty and therefore skipped, and that skip is the
        correct outcome rather than a failure."""
        result = self._conclude("success", "skipped", "false")
        self.assertEqual(
            0,
            result.returncode,
            "the conclusion refused a pull request that affects no environment, so "
            "every documentation-only pull request would be unmergeable: "
            f"{(result.stdout + result.stderr)[-600:]!r}",
        )

    def test_a_skipped_matrix_on_a_run_that_owed_a_plan_is_refused(self) -> None:
        """SPECIFIED -- scenario "One environment's plan failure does not hide
        the others", read at its limit: a skipped job is not a passing one, and
        concluding success here reports a green required status check for a pull
        request nothing planned."""
        result = self._conclude("success", "skipped", "true")
        self.assertNotEqual(
            0,
            result.returncode,
            "the conclusion passed a run that resolved an affected environment and "
            "then planned nothing",
        )

    def test_a_failed_or_cancelled_matrix_is_refused(self) -> None:
        """SPECIFIED -- "the check SHALL report failure" where a plan failed. A
        cancelled matrix is refused on both settings of whether a plan was owed:
        it has verified nothing either way, and a run superseded by a newer push
        reports on the older commit."""
        for plan, expected in (
            ("failure", "true"),
            ("cancelled", "true"),
            ("cancelled", "false"),
        ):
            with self.subTest(plan=plan, expected=expected):
                result = self._conclude("success", plan, expected)
                self.assertNotEqual(
                    0,
                    result.returncode,
                    f"the conclusion passed a matrix that concluded {plan!r}",
                )

    def test_a_run_whose_discovery_did_not_succeed_is_refused(self) -> None:
        """DERIVED (tasks.md 4.1a) -- no scenario states it. Discovery is read
        FIRST because on its failure its outputs are empty strings, so the input
        saying whether a plan was owed is "" and the matrix's result is
        "skipped" — which the "nothing to plan" branch would otherwise pass,
        concluding success on a run whose own precondition refused. Reconsider
        this assertion, do not weaken it, if the aggregation learns to see
        discovery's refusal another way."""
        for discover in ("failure", "cancelled", "skipped"):
            with self.subTest(discover=discover):
                result = self._conclude(discover, "skipped", "")
                self.assertNotEqual(
                    0,
                    result.returncode,
                    f"the conclusion passed a run whose discovery concluded {discover!r} "
                    "and therefore published nothing",
                )


class TestTheDuplicatedBodiesStayIdentical(unittest.TestCase):
    """ADDED requirement: Each Environment Declares Its Own Pipeline
    Configuration -- "Discovery SHALL fail closed."

    DERIVED, and added by the implementing author: no scenario states it.

    A job attaches to one GitHub Environment and a workflow's jobs cannot be
    shared, so the discovery body exists three times -- once in each Terraform
    workflow -- and the changed-path resolution twice. Every executing assertion
    in this module runs ONE of those copies: `TestDiscoveryFailsClosed` runs
    `pr-validation.yml`'s, and the other two are read but never executed. A copy
    that drifted would keep every one of those assertions green while failing
    closed differently, or not at all, in the workflow that applies to
    production.

    So the copies are asserted identical rather than each being exercised. That
    is the assertion the suite can actually make -- it reads committed files and
    may not spawn a Terraform binary or a runner -- and it is what makes running
    one copy evidence about all three.

    Reconsider this assertion, do not weaken it, if the bodies are ever factored
    into a composite action or a called workflow, at which point there is one
    copy and nothing to compare.
    """

    def _bodies(self, label: str, matches) -> dict:
        """Every workflow's copy of one body, located BY SHAPE rather than by
        the name the implementation gave the step.

        Located by name at first, and that was wrong for the reason this suite
        avoids name-based locators everywhere else: a sibling step whose name
        merely begins the same way is indistinguishable from a second copy. The
        apply workflow's planned-environment resolution is exactly such a
        sibling, and it broke this assertion the day it was written.
        """
        found = {}
        for path in TERRAFORM_WORKFLOWS:
            workflow = load_yaml(path)
            matching = [
                str(step["run"])
                for _, _, step in steps(workflow)
                if step.get("run") and matches(str(step["run"]))
            ]
            self.assertLessEqual(
                len(matching),
                1,
                f"{path.name} carries {len(matching)} steps whose body is {label}; each "
                "workflow holds at most one copy of it",
            )
            if matching:
                found[path.name] = matching[0]
        return found

    def test_every_workflow_discovers_environments_the_same_way(self) -> None:
        """DERIVED -- see the class docstring. Every Terraform workflow runs a
        matrix over the discovered environments, so every one of them carries
        this body; a workflow that lost it would run over nothing."""
        bodies = self._bodies(
            "the environment discovery",
            lambda body: "terraform/stacks" in body
            and "terraform/modules" not in body
            and "GITHUB_OUTPUT" in body
            and not ACTIONS_EXPRESSION.search(body),
        )
        self.assertEqual(
            sorted(path.name for path in TERRAFORM_WORKFLOWS),
            sorted(bodies),
            "these Terraform workflows carry no environment-discovery step, so they "
            f"cannot run over the discovered environments at all: {sorted(bodies)}",
        )
        distinct = {body for body in bodies.values()}
        self.assertEqual(
            1,
            len(distinct),
            "the discovery bodies have drifted apart. Only one of them is executed by "
            "this suite, so a copy that fails closed differently would stay green here "
            "and refuse -- or accept -- differently in the workflow that applies to "
            f"production. Copies: {sorted(bodies)}",
        )

    def test_both_workflows_resolve_the_affected_set_the_same_way(self) -> None:
        """DERIVED -- see the class docstring. `drift.yml` deliberately carries
        no resolution: drift is divergence from what was committed, which no
        diff predicts, so it plans every environment on every run."""
        bodies = self._bodies(
            "the changed-path resolution",
            lambda body: "terraform/stacks" in body
            and "terraform/modules" in body
            and "GITHUB_OUTPUT" in body
            and not ACTIONS_EXPRESSION.search(body),
        )
        self.assertEqual(
            [APPLY.name, PR_VALIDATION.name],
            sorted(bodies),
            "the changed-path resolution is expected in exactly the two workflows that "
            f"narrow by what changed, and was found in {sorted(bodies)}",
        )
        # The two differ only in the sentence naming what supplies the paths --
        # a pull request's diff on one, a push's commit range on the other -- so
        # they are compared on the code rather than on the prose.
        stripped = {
            "\n".join(
                line for line in body.splitlines() if not line.strip().startswith("#")
            ).strip()
            for body in bodies.values()
        }
        self.assertEqual(
            1,
            len(stripped),
            "the two changed-path resolutions have drifted apart in their code, so a "
            "pull request and the merge of that same pull request could resolve "
            "different environments -- the reviewer approving one plan and the pipeline "
            f"applying another. Copies: {sorted(bodies)}",
        )


class TestTheTwoReadersOfADeclarationAgree(DeclarationTreeFixtureMixin, unittest.TestCase):
    """ADDED requirement: Each Environment Declares Its Own Pipeline
    Configuration.

    DERIVED, and added by the implementing author: no scenario states it.

    A declaration is read TWICE by different code. The workflows read it with
    `sed`, because a discovery body executed by this suite may use nothing but
    bash, jq and coreutils. This module reads it with `yaml.safe_load`, and
    locates it by shape rather than by name because the file's name was not
    decided when these tests were written.

    Every other assertion here exercises one reader or the other; none pairs
    them on one file. So a declaration the two read DIFFERENTLY -- a duplicate
    key, where `head -n 1` silently wins and YAML takes the last; a quoted value;
    a trailing comment -- passes this module's census and reaches the pipeline as
    something else. What the census approved and what the workflow ran would then
    be different declarations, and nothing would say so.

    Reconsider this assertion, do not weaken it, if the workflows ever gain a
    real YAML parser, at which point there is one reader and nothing to pair.
    """

    def setUp(self) -> None:
        require_external_tools(
            self, ("bash", "jq"), "execute the workflow's declaration reader"
        )

    def _discovery_body(self) -> str:
        candidates = [
            str(step["run"])
            for _, _, step in steps(load_yaml(PR_VALIDATION))
            if step.get("run")
            and "terraform/stacks" in str(step["run"])
            and "terraform/modules" not in str(step["run"])
            and "GITHUB_OUTPUT" in str(step["run"])
            and not ACTIONS_EXPRESSION.search(str(step["run"]))
        ]
        self.assertEqual(1, len(candidates), "expected exactly one discovery body")
        return candidates[0]

    def _shell_reading(self, tree: Path) -> dict:
        outputs = tree / "github_output"
        outputs.touch()
        result = run_snippet(
            self._discovery_body(),
            dict(os.environ, GITHUB_OUTPUT=str(outputs), GITHUB_WORKSPACE=str(tree)),
            tree,
        )
        self.assertEqual(
            0,
            result.returncode,
            "the workflow's reader refused a declaration this module's reader "
            f"accepted: {(result.stdout + result.stderr)[-600:]!r}",
        )
        emitted = github_output_pairs(outputs).get("stacks", "")
        self.assertTrue(emitted, "the discovery body emitted no environments")
        return {entry["name"]: entry for entry in json.loads(emitted)}

    def test_both_readers_return_the_same_values_for_the_committed_declarations(self) -> None:
        """DERIVED -- see the class docstring, read over the tree as committed.
        This is the pairing that matters most, because prod's declaration is the
        one file both readers actually meet in production."""
        tree = Path(tempfile.mkdtemp(prefix="reader-agreement-"))
        self.addCleanup(shutil.rmtree, tree, ignore_errors=True)
        source = ENVIRONMENTS_DIR
        shutil.copytree(source, tree / "terraform" / "stacks")

        by_shell = self._shell_reading(tree)
        by_python = environment_declarations()

        self.assertEqual(
            sorted(by_python),
            sorted(by_shell),
            "the two readers disagree about which environments exist",
        )
        for name in sorted(by_python):
            with self.subTest(environment=name):
                declaration = by_python[name]
                self.assertEqual([], declaration.offences, "; ".join(declaration.offences))
                self.assertEqual(
                    (
                        declaration.github_environment,
                        declaration.read_only_secret,
                        declaration.destroy_gate_applies,
                    ),
                    (
                        by_shell[name]["github_environment"],
                        by_shell[name]["read_only_secret"],
                        by_shell[name]["destroy_policy_gate"],
                    ),
                    f"the workflow's reader and this module's reader disagree about "
                    f"`{name}`: the census approved one declaration and the pipeline "
                    f"would run another. Workflow read {by_shell[name]!r}",
                )

    def test_both_readers_agree_on_a_declaration_written_awkwardly(self) -> None:
        """DERIVED -- the committed declarations are written the way this
        repository writes them, so agreeing on them establishes little on its
        own. These are the spellings a second environment's author could
        plausibly reach for and the two readers could plausibly split on."""
        tree = Path(tempfile.mkdtemp(prefix="reader-agreement-"))
        self.addCleanup(shutil.rmtree, tree, ignore_errors=True)
        self._write_tree(tree, {"prod": self._declaration_for("HCLOUD_TOKEN", "production", gate=True)})
        awkward = (
            "# A declaration written the long way round.\n"
            'github_environment: "staging"   # quoted, with a trailing comment\n'
            "read_only_secret:   HCLOUD_TOKEN_STAGING\n"
            "destroy_policy_gate: false\n"
        )
        directory = tree / "terraform" / "stacks" / "staging"
        directory.mkdir(parents=True)
        (directory / "pipeline.yml").write_text(awkward, encoding="utf-8")

        by_shell = self._shell_reading(tree)
        by_python = environment_declarations(tree)

        self.assertEqual(sorted(by_python), sorted(by_shell))
        for name in sorted(by_python):
            with self.subTest(environment=name):
                declaration = by_python[name]
                self.assertEqual([], declaration.offences, "; ".join(declaration.offences))
                self.assertEqual(
                    (
                        declaration.github_environment,
                        declaration.read_only_secret,
                        declaration.destroy_gate_applies,
                    ),
                    (
                        by_shell[name]["github_environment"],
                        by_shell[name]["read_only_secret"],
                        by_shell[name]["destroy_policy_gate"],
                    ),
                    f"the two readers split on `{name}`. Workflow read "
                    f"{by_shell[name]!r}",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
