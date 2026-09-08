"""Static-assertion tests for the CI configuration this repository ships.

Derived from the delta specs of the OpenSpec change `close-ci-verification-gaps`,
before any implementation of that change existed. Those deltas span several
capabilities, so no single `openspec/specs/<capability>/spec.md` names them all;
each section below cites the one it traces to. Every assertion is annotated
SPECIFIED (it traces to SHALL text in a delta spec) or DERIVED (it traces to
`design.md`/`tasks.md` rather than to a scenario). See that change's `test-plan.md` for the
scenario-to-test mapping and for the scenarios deliberately left uncovered.

Sections added later carry their own provenance comment naming the change they
were derived from and that change's own test-plan.md; the annotation convention
above holds across all of them.

Runner
------
    python3 -m unittest discover -s <dir holding this file> -v

    # or a single test, individually selectable:
    python3 -m unittest test_ci_configuration.TestDependabotCoverage \
        .test_every_terraform_lockfile_directory_appears_in_dependabot_config

This is NOT `terraform test`. It needs Python 3.9+ and PyYAML -- no network, no
credential, no Terraform, no Docker.

One test, `TestMoleculeDiscoveryAndScenarioCoverage
.test_role_discovery_fails_when_it_finds_nothing`, additionally shells out to a
workflow's own discovery snippet, so it needs `bash` and the external tools that
snippet calls: `find`, `xargs`, `basename`, `grep`, `sort` and `jq`. Where any of
those is missing, that one test skips and names it -- except under CI (`CI` set
in the environment), where it fails instead, because a skipped test on a runner
is a check reporting success having verified nothing. Every other test in this
file needs Python and PyYAML alone.

The repository root is found by walking up from this file for
`openspec/config.yaml`, or taken from the `REPO_ROOT` environment variable when
set.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

# --------------------------------------------------------------------------
# Repository access helpers
# --------------------------------------------------------------------------


def _repo_root() -> Path:
    override = os.environ.get("REPO_ROOT")
    if override:
        return Path(override).resolve()
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "openspec" / "config.yaml").is_file():
            return candidate
    raise RuntimeError(
        "could not locate the repository root: no ancestor of "
        f"{here} contains openspec/config.yaml, and REPO_ROOT is unset"
    )


ROOT = _repo_root()
WORKFLOWS = ROOT / ".github" / "workflows"

PR_VALIDATION = WORKFLOWS / "pr-validation.yml"
APPLY = WORKFLOWS / "apply.yml"
ANSIBLE_VERIFY = WORKFLOWS / "ansible-verify.yml"
DEPENDABOT = ROOT / ".github" / "dependabot.yml"
PRE_COMMIT_CONFIG = ROOT / ".pre-commit-config.yaml"


def load_yaml(path: Path) -> dict:
    """Parse a YAML file, failing the calling test if it is absent.

    An absent file is a real failure, not an error to be skipped: for a
    workflow this change is specified to create, "the file does not exist yet"
    is the expected pre-implementation result.
    """
    if not path.is_file():
        raise AssertionError(f"{path.relative_to(ROOT)} does not exist")
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def uncommented(text: str) -> str:
    """Drop whole-line YAML comments, so a comment naming a thing is not read
    as the workflow using it."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def read_text(path: Path) -> str:
    if not path.is_file():
        raise AssertionError(f"{path.relative_to(ROOT)} does not exist")
    return path.read_text(encoding="utf-8")


def triggers(workflow: dict) -> dict:
    """Return a workflow's `on:` block.

    PyYAML resolves the bare key `on` to the boolean True under YAML 1.1, so
    both spellings have to be looked for.
    """
    for key in ("on", True):
        if key in workflow:
            value = workflow[key]
            return value if isinstance(value, dict) else {}
    return {}


def jobs(workflow: dict) -> dict:
    return workflow.get("jobs") or {}


def steps(workflow: dict):
    """Yield (job_name, step_index, step) across every job in a workflow."""
    for job_name, job in jobs(workflow).items():
        for index, step in enumerate(job.get("steps") or []):
            yield job_name, index, step


def step_label(job_name: str, index: int, step: dict) -> str:
    return f"{job_name}[{index}] {step.get('name') or step.get('uses') or '<unnamed>'}"


def step_text(step: dict) -> str:
    """All text a step contributes -- its name, action reference and shell."""
    parts = [str(step.get(key, "")) for key in ("name", "uses", "run")]
    parts.append(str(step.get("with", "")))
    return "\n".join(parts)


def gh_glob_matches(pattern: str, path: str) -> bool:
    """Match a POSIX-style path against a GitHub Actions path filter pattern."""
    regex = ""
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**", i):
            regex += ".*"
            i += 2
        elif char == "*":
            regex += "[^/]*"
            i += 1
        elif char == "?":
            regex += "[^/]"
            i += 1
        else:
            regex += re.escape(char)
            i += 1
    return re.fullmatch(regex, path) is not None


def terraform_lockfile_directories() -> set[str]:
    """Every repository directory carrying a `.terraform.lock.hcl`, as `/a/b`."""
    found = set()
    for lockfile in ROOT.rglob(".terraform.lock.hcl"):
        if ".git" in lockfile.parts:
            continue
        found.add("/" + lockfile.parent.relative_to(ROOT).as_posix())
    return found


def role_names() -> set[str]:
    roles_dir = ROOT / "ansible" / "roles"
    if not roles_dir.is_dir():
        return set()
    return {
        entry.name
        for entry in roles_dir.iterdir()
        if entry.is_dir() and not entry.name.startswith(".") and "." not in entry.name
    }


def roles_with_molecule_scenarios() -> set[str]:
    return {name for name in role_names() if (ROOT / "ansible" / "roles" / name / "molecule").is_dir()}


# --------------------------------------------------------------------------
# iac-safety-hardening / Automated Dependency Updates
# --------------------------------------------------------------------------


class TestDependabotCoverage(unittest.TestCase):
    """MODIFIED requirement: Automated Dependency Updates."""

    def setUp(self) -> None:
        self.config = load_yaml(DEPENDABOT)
        self.updates = self.config.get("updates") or []

    def _directories_for(self, ecosystem: str) -> list[str]:
        configured: list[str] = []
        for entry in self.updates:
            if entry.get("package-ecosystem") != ecosystem:
                continue
            if entry.get("directory"):
                configured.append(entry["directory"])
            configured.extend(entry.get("directories") or [])
        return configured

    def test_every_terraform_lockfile_directory_appears_in_dependabot_config(self) -> None:
        """SPECIFIED -- scenario "Every lockfile-bearing directory is covered".

        The scenario is verbatim a set comparison: the directories holding a
        `.terraform.lock.hcl` against the directories the `terraform` ecosystem
        lists. Dependabot's terraform ecosystem has no discovery mechanism, so
        nothing but this comparison keeps the two in agreement.
        """
        configured = self._directories_for("terraform")
        actual = terraform_lockfile_directories()
        self.assertTrue(actual, "no .terraform.lock.hcl found; the comparison would be vacuous")
        uncovered = {
            directory
            for directory in actual
            if not any(gh_glob_matches(pattern, directory) for pattern in configured)
        }
        self.assertEqual(
            set(),
            uncovered,
            "these directories carry a .terraform.lock.hcl but no Dependabot "
            f"`terraform` entry names them: {sorted(uncovered)}; configured: {sorted(configured)}",
        )

    def test_dependabot_configures_both_required_ecosystems(self) -> None:
        """SPECIFIED -- the requirement's opening sentence, which is the enabling
        condition for the "Provider version update" and "Action version update"
        scenarios. It does not establish either scenario's outcome; see the
        test plan."""
        ecosystems = {entry.get("package-ecosystem") for entry in self.updates}
        for required in ("terraform", "github-actions"):
            self.assertIn(required, ecosystems, f"no Dependabot entry for the {required} ecosystem")


class TestScheduledHookRefresh(unittest.TestCase):
    """MODIFIED requirement: Automated Dependency Updates."""

    def test_a_scheduled_workflow_runs_pre_commit_autoupdate(self) -> None:
        """SPECIFIED -- "pinned hook revisions SHALL instead be maintained by a
        scheduled workflow that runs `pre-commit autoupdate`". Establishes that
        the workflow exists and is scheduled, not that it opens a pull request."""
        matches = []
        for path in sorted(WORKFLOWS.glob("*.yml")):
            workflow = load_yaml(path)
            if "schedule" not in triggers(workflow):
                continue
            if "pre-commit autoupdate" in read_text(path):
                matches.append(path.name)
        self.assertTrue(
            matches,
            "no workflow under .github/workflows/ is both schedule-triggered and runs "
            "`pre-commit autoupdate`",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Pull Request Validation Checks
# --------------------------------------------------------------------------


class TestSecretScanningIsUnconditional(unittest.TestCase):
    """MODIFIED requirement: Pull Request Validation Checks."""

    def setUp(self) -> None:
        self.workflow = load_yaml(PR_VALIDATION)
        self.gitleaks_steps = [
            (job, index, step)
            for job, index, step in steps(self.workflow)
            if "gitleaks" in step_text(step).lower()
        ]

    def test_the_workflow_has_a_secret_scanning_step_at_all(self) -> None:
        """SPECIFIED -- guards every other test in this class from passing
        vacuously over a workflow that no longer scans for secrets."""
        self.assertTrue(
            self.gitleaks_steps,
            "no step in pr-validation.yml references gitleaks",
        )

    def test_no_secret_scanning_step_is_conditioned_on_terraform_changes(self) -> None:
        """SPECIFIED -- "`gitleaks` SHALL run on every pull request, whether or
        not Terraform configuration changed", and scenario "A credential
        outside Terraform is still caught"."""
        self.test_the_workflow_has_a_secret_scanning_step_at_all()
        offenders = [
            step_label(job, index, step)
            for job, index, step in self.gitleaks_steps
            if "terraform" in str(step.get("if", "")).lower()
        ]
        self.assertEqual(
            [],
            offenders,
            "these gitleaks steps carry an `if:` gated on Terraform having changed, "
            f"so a non-Terraform pull request is not scanned: {offenders}",
        )

    def test_no_job_containing_a_secret_scanning_step_is_conditioned_on_terraform_changes(self) -> None:
        """SPECIFIED -- same requirement text. Separate from the step-level test
        because moving the condition from the step to its job would leave the
        step-level assertion green while reopening the hole."""
        self.test_the_workflow_has_a_secret_scanning_step_at_all()
        offenders = []
        for job_name, _, _ in self.gitleaks_steps:
            job_if = str(jobs(self.workflow)[job_name].get("if", "")).lower()
            if "terraform" in job_if:
                offenders.append(job_name)
        self.assertEqual(
            [], sorted(set(offenders)), f"job-level `if:` gated on Terraform: {sorted(set(offenders))}"
        )

    def test_secret_scanning_precedes_any_terraform_plan_in_the_same_job(self) -> None:
        """SPECIFIED -- scenario "PR with a leaked credential fails validation":
        the workflow "SHALL fail before any `terraform plan` is executed".
        Establishes the ordering half only; gitleaks' own detection is its
        behavior, not this repository's."""
        self.test_the_workflow_has_a_secret_scanning_step_at_all()
        for job_name, job in jobs(self.workflow).items():
            job_steps = job.get("steps") or []
            scan_indices = [
                i for i, s in enumerate(job_steps) if "gitleaks" in step_text(s).lower()
            ]
            plan_indices = [
                i
                for i, s in enumerate(job_steps)
                if re.search(r"terraform\s+plan\b", str(s.get("run", "")))
            ]
            if not scan_indices or not plan_indices:
                continue
            self.assertLess(
                max(scan_indices),
                min(plan_indices),
                f"in job {job_name}, a `terraform plan` step runs before the secret scan",
            )


class TestSecretScanVersionParity(unittest.TestCase):
    """MODIFIED requirement: Pull Request Validation Checks."""

    VERSION = re.compile(r"\b\d+\.\d+\.\d+\b")

    def setUp(self) -> None:
        self.pinned = self._precommit_pin()
        self.workflow = load_yaml(PR_VALIDATION)

    def _precommit_pin(self) -> str:
        config = load_yaml(PRE_COMMIT_CONFIG)
        for repo in config.get("repos") or []:
            if "gitleaks" in str(repo.get("repo", "")).lower():
                rev = str(repo.get("rev", "")).strip()
                self.assertTrue(rev, "the gitleaks pre-commit repo block declares no `rev`")
                return rev.lstrip("v")
        self.fail("no gitleaks repo block found in .pre-commit-config.yaml")

    def test_ci_installs_the_version_the_precommit_config_pins(self) -> None:
        """SPECIFIED -- scenario "Local and CI secret scans agree": the version
        invoked in CI SHALL match the revision pinned in the pre-commit
        configuration, with the pre-commit pin as the source of truth.

        Satisfied either by a literal equal to the pin, or by deriving the
        version from `.pre-commit-config.yaml` at run time. A workflow that
        does neither cannot be shown to run the same scan as the local hook.
        """
        literals: dict[str, set[str]] = {}
        for job, index, step in steps(self.workflow):
            text = step_text(step)
            if "gitleaks" not in text.lower():
                continue
            found = set(self.VERSION.findall(text))
            if found:
                literals[step_label(job, index, step)] = found

        mismatched = {
            label: sorted(found - {self.pinned})
            for label, found in literals.items()
            if found - {self.pinned}
        }
        self.assertEqual(
            {},
            mismatched,
            f"the pre-commit config pins gitleaks {self.pinned}, but these CI steps "
            f"name a different version: {mismatched}",
        )

        if not literals:
            self.assertIn(
                ".pre-commit-config.yaml",
                read_text(PR_VALIDATION),
                "no gitleaks step names a version and none reads the pin out of "
                ".pre-commit-config.yaml, so the version CI installs cannot be "
                "shown to match the local one",
            )


class TestSecretScanningNeedsNoLicense(unittest.TestCase):
    """MODIFIED requirement: Pull Request Validation Checks."""

    def test_no_workflow_references_a_gitleaks_license_secret(self) -> None:
        """SPECIFIED -- scenario "Secret scanning requires no third-party
        license"."""
        offenders = [
            path.name
            for path in sorted(WORKFLOWS.glob("*.yml"))
            if "GITLEAKS_LICENSE" in uncommented(read_text(path))
        ]
        self.assertEqual([], offenders, f"GITLEAKS_LICENSE referenced by: {offenders}")

    def test_secret_scanning_uses_the_cli_not_the_marketplace_action(self) -> None:
        """SPECIFIED -- "`gitleaks` SHALL be invoked as its CLI binary rather
        than via the `gitleaks/gitleaks-action` marketplace action"."""
        offenders = []
        for path in sorted(WORKFLOWS.glob("*.yml")):
            workflow = load_yaml(path)
            for job, index, step in steps(workflow):
                if str(step.get("uses", "")).startswith("gitleaks/gitleaks-action"):
                    offenders.append(f"{path.name}:{step_label(job, index, step)}")
        self.assertEqual([], offenders, f"marketplace gitleaks action used by: {offenders}")


class TestTerraformChecksDiscoverDirectories(unittest.TestCase):
    """MODIFIED requirement: Pull Request Validation Checks.

    Regression guards for two scenarios the delta carries through unchanged.
    """

    def setUp(self) -> None:
        self.text = read_text(PR_VALIDATION)

    def test_the_workflow_names_no_terraform_module_directory_literally(self) -> None:
        """SPECIFIED -- scenario "A newly added module is validated and linted
        without a workflow change": the directories are "discovered rather than
        enumerated by a fixed list of directory names"."""
        modules_dir = ROOT / "terraform" / "modules"
        literals = [
            entry.name
            for entry in sorted(modules_dir.iterdir())
            if entry.is_dir() and f"terraform/modules/{entry.name}" in self.text
        ]
        self.assertEqual(
            [],
            literals,
            "pr-validation.yml names these module directories literally, so a new "
            f"module would not be covered without a workflow edit: {literals}",
        )

    def test_the_workflow_runs_terraform_test(self) -> None:
        """SPECIFIED -- scenario "A module's tests run in CI"."""
        self.assertRegex(
            self.text,
            r"terraform\s+test\b",
            "pr-validation.yml invokes no `terraform test`",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Ansible Configuration Is Verified in Continuous
# Integration and Gates the Merge
# --------------------------------------------------------------------------


class TestAnsibleBlockingTier(unittest.TestCase):
    """ADDED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge.

    The tier this class covers is the requirement's *Lint tier*, called the
    *Blocking tier* when this class was written -- a name that distinguished it
    from an advisory one, which no longer exists. The class and its methods
    keep their names: they are runner-selectable identifiers cited by an
    archived `test-plan.md`, and renaming them would break that citation to say
    nothing new. The assertions are unchanged; both tiers block, and this one
    always did.
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(PR_VALIDATION)
        self.text = read_text(PR_VALIDATION)

    def _paths_filter_inputs(self) -> list[str]:
        found = []
        for _, _, step in steps(self.workflow):
            if str(step.get("uses", "")).startswith("dorny/paths-filter"):
                filters = (step.get("with") or {}).get("filters")
                if filters:
                    found.append(str(filters))
        return found

    def test_an_ansible_path_filter_selects_changes_under_ansible(self) -> None:
        """SPECIFIED -- "Every pull request that changes files under `ansible/`
        SHALL trigger continuous-integration checks over that configuration"."""
        filters = self._paths_filter_inputs()
        self.assertTrue(filters, "pr-validation.yml declares no dorny/paths-filter step")
        self.assertTrue(
            any(re.search(r"^\s*ansible\s*:", block, re.MULTILINE) for block in filters),
            "no `ansible:` entry in the paths-filter `filters:` block, so Ansible "
            "changes select no check",
        )

    def test_the_blocking_tier_runs_ansible_lint(self) -> None:
        """SPECIFIED -- "`ansible-lint` ... SHALL run as part of the required
        pull request status check"."""
        self.assertIn("ansible-lint", self.text, "pr-validation.yml never invokes ansible-lint")

    def test_the_blocking_tier_runs_an_ansible_syntax_check(self) -> None:
        """SPECIFIED -- "`ansible-playbook --syntax-check` SHALL run as part of
        the required pull request status check"."""
        self.assertTrue(
            "syntax-check" in self.text or "syntax_check" in self.text,
            "pr-validation.yml never invokes an Ansible syntax check",
        )


class TestVerificationJobsCarryNoCredential(unittest.TestCase):
    """ADDED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge."""

    def test_no_pull_request_validation_job_declares_an_environment(self) -> None:
        """SPECIFIED -- scenario "Ansible verification receives no production
        credential": no verification job declares a deployment `environment:`.
        Also the standing invariant `handoff.md` records as must-not-undo."""
        workflow = load_yaml(PR_VALIDATION)
        offenders = [name for name, job in jobs(workflow).items() if "environment" in job]
        self.assertEqual([], offenders, f"jobs declaring `environment:`: {offenders}")

    def test_the_molecule_workflow_declares_no_environment(self) -> None:
        """SPECIFIED -- same scenario, suite tier. The requirement's two tiers
        were named *Blocking* and *Advisory* while only one of them gated;
        `promote-molecule-to-a-required-check` renamed them *Lint* and *Suite*,
        because both gate now and what separates them is what they run. The
        credential prohibition was always over both and is unchanged."""
        workflow = load_yaml(ANSIBLE_VERIFY)
        offenders = [name for name, job in jobs(workflow).items() if "environment" in job]
        self.assertEqual([], offenders, f"jobs declaring `environment:`: {offenders}")

    def test_the_molecule_workflow_consumes_no_secret(self) -> None:
        """SPECIFIED -- same scenario: the run completes without a Hetzner API
        token, an SSH deploy key or a registry credential. The suite runs
        offline against local containers."""
        text = read_text(ANSIBLE_VERIFY)
        references = sorted(set(re.findall(r"secrets\.[A-Za-z_][A-Za-z0-9_]*", text)))
        allowed = {"secrets.GITHUB_TOKEN"}
        offenders = [ref for ref in references if ref not in allowed]
        self.assertEqual([], offenders, f"secret references in ansible-verify.yml: {offenders}")


class TestMoleculeDiscoveryAndScenarioCoverage(unittest.TestCase):
    """ADDED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge."""

    # The discovery snippet is real shell: it calls these before it can reach
    # its own failure branch. Without them it exits non-zero for a reason that
    # has nothing to do with discovery.
    DISCOVERY_SNIPPET_TOOLS = ("find", "xargs", "basename", "grep", "sort", "jq")

    def setUp(self) -> None:
        self.workflow = load_yaml(ANSIBLE_VERIFY)
        self.text = read_text(ANSIBLE_VERIFY)

    def _require_discovery_snippet_tools(self) -> None:
        """Precondition, not an assertion: refuse to read a non-zero exit as
        evidence about discovery when the snippet could not run at all.

        DERIVED. `assertNotEqual(0, returncode)` passes on an accident when a
        tool the snippet calls is absent -- `jq: command not found` is also a
        non-zero exit -- and the message assertion then fails for a cause the
        workflow is not responsible for. So the tools are checked up front.

        Outside CI a missing tool is a fact about the machine, and the test
        skips, naming it; unittest reports the skip and its reason rather than
        counting it a pass. Under CI it fails instead, because a silently
        skipped check is precisely the "green having verified nothing" failure
        this change exists to close.
        """
        missing = [tool for tool in self.DISCOVERY_SNIPPET_TOOLS if shutil.which(tool) is None]
        if not missing:
            return
        reason = (
            "cannot exercise ansible-verify.yml's role-discovery snippet: it calls "
            f"{', '.join(missing)}, absent on this machine, so its exit status would "
            "say nothing about whether discovery fails on an empty tree"
        )
        if os.environ.get("CI"):
            self.fail(
                f"{reason}. Running under CI, where skipping this test would report "
                "success having verified nothing; install the tool on the runner."
            )
        self.skipTest(reason)

    def test_the_workflow_names_no_role_literally(self) -> None:
        """SPECIFIED -- "The Molecule run SHALL discover role scenarios rather
        than enumerate them, so that a role or scenario added under
        `ansible/roles/` is covered without a workflow edit"
        (scenario "A newly added role scenario runs without a workflow change").
        """
        roles = roles_with_molecule_scenarios()
        self.assertTrue(roles, "no role under ansible/roles/ carries a molecule/ directory")
        literals = sorted(role for role in roles if re.search(rf"\b{re.escape(role)}\b", self.text))
        self.assertEqual(
            [],
            literals,
            "ansible-verify.yml names these roles literally, so a newly added role "
            f"or scenario would need a workflow edit to be covered: {literals}",
        )

    def test_molecule_is_invoked_across_all_scenarios(self) -> None:
        """SPECIFIED -- "SHALL execute every scenario a role declares rather
        than only its `default` scenario" (scenario "Every scenario a role
        declares is executed")."""
        invocations = [
            line.strip()
            for line in self.text.splitlines()
            if re.search(r"\bmolecule\s+test\b", line)
        ]
        self.assertTrue(invocations, "ansible-verify.yml never invokes `molecule test`")
        without_all = [line for line in invocations if "--all" not in line]
        self.assertEqual(
            [],
            without_all,
            "these `molecule test` invocations omit `--all`, so only each role's "
            f"`default` scenario would run: {without_all}",
        )

    def test_the_workflow_uses_no_continue_on_error(self) -> None:
        """SPECIFIED -- scenario "A failing Molecule scenario blocks the merge":
        the failure SHALL be visible on the pull request and the aggregating job
        SHALL conclude failure.

        The assertion is unchanged; what it protects is not. While this workflow
        was advisory, `continue-on-error` would have destroyed the signal the
        tier existed to collect. Now that the workflow is a required check, it
        would report a GREEN REQUIRED STATUS CHECK for a failed suite and let
        the merge through -- the same conflation the aggregating gate refuses
        for a skipped matrix, reached by a different route.

        Establishes the visibility half only. Whether the merge is then blocked
        is branch protection, which is repository settings and not repository
        state this suite can read.
        """
        self.assertNotIn(
            "continue-on-error",
            self.text,
            "ansible-verify.yml uses continue-on-error, which reports a green "
            "conclusion for a failed scenario -- on a required status check, that "
            "is a merge let through by a suite that failed",
        )

    def test_role_discovery_fails_when_it_finds_nothing(self) -> None:
        """DERIVED (tasks.md 5.2, design Decision 4) -- scenario "Discovering no
        roles fails rather than passes" states the outcome; the shape asserted
        here (a shell snippet exercisable standalone against a scratch tree) is
        the verification tasks.md 5.2 prescribes, not something the scenario
        requires. Reconsider this assertion, do not weaken it, if the
        implementation satisfies the scenario by another means.
        """
        candidates = [
            (job, index, step)
            for job, index, step in steps(self.workflow)
            if step.get("run") and "molecule" in str(step.get("run"))
            and re.search(r"ansible/roles", str(step.get("run")))
        ]
        if not candidates:
            candidates = [
                (job, index, step)
                for job, index, step in steps(self.workflow)
                if step.get("run") and re.search(r"ansible/roles", str(step.get("run")))
            ]
        self.assertTrue(
            candidates,
            "no step in ansible-verify.yml discovers roles under ansible/roles/",
        )

        job, index, step = candidates[0]
        script = str(step["run"])
        self.assertNotIn(
            "${{",
            script,
            f"the discovery snippet {step_label(job, index, step)} embeds a GitHub "
            "Actions expression, so it cannot be exercised against a scratch tree "
            "as tasks.md 5.2 requires",
        )

        self._require_discovery_snippet_tools()

        scratch = Path(tempfile.mkdtemp(prefix="molecule-discovery-"))
        try:
            (scratch / "ansible" / "roles").mkdir(parents=True)
            outputs = scratch / "github_output"
            outputs.touch()
            env = dict(os.environ, GITHUB_OUTPUT=str(outputs), GITHUB_ENV=str(outputs))
            result = subprocess.run(
                ["bash", "-e", "-c", script],
                cwd=scratch,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertNotEqual(
                0,
                result.returncode,
                "role discovery exited 0 against a tree containing no role, so an "
                "empty matrix would skip the Molecule job and the workflow would "
                "conclude success having verified nothing",
            )
            combined = (result.stdout + result.stderr).lower()
            self.assertTrue(
                any(word in combined for word in ("discover", "role", "no roles")),
                "role discovery failed without a message identifying discovery as "
                f"the cause; it emitted: {combined.strip()!r}",
            )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


class TestToolchainIsInstalledFromPinnedManifests(unittest.TestCase):
    """ADDED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge."""

    PIP_INSTALL = re.compile(r"pip\d*\s+install\s+(?P<args>[^\n]*)")

    def _bare_installs(self, path: Path) -> list[str]:
        offenders = []
        for match in self.PIP_INSTALL.finditer(read_text(path)):
            args = match.group("args").strip()
            tokens = [token for token in args.split() if not token.startswith("-")]
            flags = [token for token in args.split() if token.startswith("-")]
            if "-r" not in flags and "--requirement" not in flags:
                offenders.append(f"{path.name}: pip install {args}")
            elif tokens and "-r" in flags:
                # tokens following -r are the manifest paths; anything else is a
                # bare package named alongside a manifest.
                pieces = args.split()
                named_manifests = {
                    pieces[i + 1] for i, token in enumerate(pieces) if token in ("-r", "--requirement")
                }
                extras = [token for token in tokens if token not in named_manifests]
                if extras:
                    offenders.append(f"{path.name}: pip install {args}")
        return offenders

    def test_the_molecule_workflow_installs_only_from_requirement_manifests(self) -> None:
        """SPECIFIED -- "SHALL install its toolchain from the repository's exact
        pinned manifests ... and SHALL NOT resolve any dependency version
        freshly at run time"."""
        offenders = self._bare_installs(ANSIBLE_VERIFY)
        self.assertEqual([], offenders, f"unpinned installs: {offenders}")

    def test_the_validation_workflow_installs_only_from_requirement_manifests(self) -> None:
        """SPECIFIED -- same clause, applied to the blocking tier's installs."""
        offenders = self._bare_installs(PR_VALIDATION)
        self.assertEqual([], offenders, f"unpinned installs: {offenders}")

    def test_the_molecule_workflow_names_both_pinned_manifests(self) -> None:
        """SPECIFIED -- the manifests are named in the requirement:
        `ansible/requirements-test.txt` and `ansible/requirements.yml`."""
        text = read_text(ANSIBLE_VERIFY)
        for manifest in ("ansible/requirements-test.txt", "ansible/requirements.yml"):
            self.assertIn(manifest, text, f"ansible-verify.yml never installs from {manifest}")


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Ansible Configuration Is Verified in Continuous
# Integration and Gates the Merge --
# the container image each scenario executes inside
# --------------------------------------------------------------------------
#
# Derived from the delta spec of the OpenSpec change
# `pin-and-fix-molecule-suite`, before any implementation of that change
# existed. The requirement these assertions trace to is
# `iac-cicd-pipeline`'s "Ansible Configuration Is Verified in Continuous
# Integration and Gates the Merge" (openspec/specs/iac-cicd-pipeline/spec.md). See that change's
# test-plan.md for the scenario-to-test mapping, the baseline, and the
# scenarios deliberately left uncovered.

GALAXY_MANIFEST = "ansible/requirements.yml"
SCENARIO_GLOB = "ansible/roles/*/molecule/*/molecule.yml"
CONTENT_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class ManifestNotUsable(AssertionError):
    """The Galaxy manifest the exclusion is derived from could not be read, or
    one of its entries could not be resolved to the directory name
    `ansible-galaxy` installs it under.

    An `AssertionError` subclass so that an unhandled one fails the calling
    test rather than erroring it: the requirement is that the check FAIL
    identifying the entry or the file, never that it yield an empty or partial
    exclusion set (design.md decision 3a -- a silently widened exclusion lets an
    unpinned scenario through, which is the vacuous pass this capability
    forbids elsewhere).
    """


def _galaxy_directory_name(entry: object, position: int) -> str:
    """Resolve one `roles:` entry to the directory `ansible-galaxy` installs it
    under: `name` where given, else the `src` basename with any version
    qualifier and `.git` suffix stripped (design.md decision 3a)."""
    source: object = None
    if isinstance(entry, str):
        source = entry
    elif isinstance(entry, dict):
        if entry.get("name"):
            return str(entry["name"])
        source = entry.get("src")
    if not isinstance(source, str) or not source.strip():
        raise ManifestNotUsable(
            f"{GALAXY_MANIFEST} roles[{position}] gives neither a `name` nor a `src`, "
            f"so the directory ansible-galaxy installs it under cannot be named and "
            f"the exclusion cannot be derived from it: {entry!r}"
        )
    basename = source.split(",")[0].strip().rstrip("/").rsplit("/", 1)[-1]
    if basename.endswith(".git"):
        basename = basename[: -len(".git")]
    if not basename:
        raise ManifestNotUsable(
            f"{GALAXY_MANIFEST} roles[{position}] has a `src` that resolves to no "
            f"directory name: {entry!r}"
        )
    return basename


def galaxy_role_directories(root: Path | None = None) -> set[str]:
    """Directory names under `ansible/roles/` that hold installed Galaxy content,
    derived from `ansible/requirements.yml` rather than from a hardcoded list."""
    base = ROOT if root is None else root
    manifest = base / GALAXY_MANIFEST
    if not manifest.is_file():
        raise ManifestNotUsable(
            f"{GALAXY_MANIFEST} does not exist, so the set of role directories to "
            f"exclude from the pinning check cannot be derived; refusing to fall "
            f"back to an empty exclusion set"
        )
    try:
        parsed = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ManifestNotUsable(
            f"{GALAXY_MANIFEST} could not be parsed, so the exclusion cannot be "
            f"derived from it: {error}"
        ) from None
    if not isinstance(parsed, dict):
        raise ManifestNotUsable(
            f"{GALAXY_MANIFEST} is not a mapping, so it declares no `roles:` list to "
            f"derive the exclusion from"
        )
    entries = parsed.get("roles")
    if entries is None:
        return set()
    if not isinstance(entries, list):
        raise ManifestNotUsable(
            f"{GALAXY_MANIFEST}'s `roles:` is not a list, so its entries cannot be "
            f"resolved to directory names"
        )
    return {_galaxy_directory_name(entry, position) for position, entry in enumerate(entries)}


def authored_scenario_files(root: Path | None = None) -> list[Path]:
    """Every Molecule scenario definition THIS repository authors.

    Scenarios shipped by Galaxy content installed from `ansible/requirements.yml`
    are excluded: they install beside this repository's own roles, are not
    committed here, are discarded by the next reinstall, and are already pinned
    as a whole by that manifest.
    """
    base = ROOT if root is None else root
    installed = galaxy_role_directories(base)
    return [
        path
        for path in sorted(base.glob(SCENARIO_GLOB))
        if path.relative_to(base).parts[2] not in installed
    ]


def parse_image_reference(image: str) -> tuple[str, str, str]:
    """Split an image reference into (repository, tag, digest).

    The tag is looked for after the last `/`, so a registry host carrying a port
    is not mistaken for one. A reference with no digest yields `""` for it.
    """
    reference, _, digest = image.partition("@")
    last_segment = reference.rfind("/") + 1
    colon = reference.find(":", last_segment)
    if colon == -1:
        return reference, "", digest
    return reference[:colon], reference[colon + 1 :], digest


def scenario_platform_images(root: Path | None = None):
    """Yield (scenario, platform, image) over every authored scenario.

    A scenario declaring no `platforms:`, a platform that is not a mapping, or a
    platform with no `image:` yields an image of `None` rather than being passed
    over -- a scenario silently exempted from a pinning check is
    indistinguishable from one that satisfies it.
    """
    base = ROOT if root is None else root
    for path in authored_scenario_files(base):
        label = path.relative_to(base).as_posix()
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            yield label, f"<unparseable: {error.__class__.__name__}>", None
            continue
        platforms = document.get("platforms") if isinstance(document, dict) else None
        if not isinstance(platforms, list) or not platforms:
            yield label, "<no platforms declared>", None
            continue
        for index, platform in enumerate(platforms):
            name = platform.get("name") if isinstance(platform, dict) else None
            plabel = f"platforms[{index}]" + (f" ({name})" if name else "")
            image = platform.get("image") if isinstance(platform, dict) else None
            yield label, plabel, image if isinstance(image, str) and image.strip() else None


def scenarios_declaring_no_platform_image(root: Path | None = None) -> list[str]:
    return [
        f"{scenario}: {platform}"
        for scenario, platform, image in scenario_platform_images(root)
        if image is None
    ]


def scenarios_with_an_unpinned_platform_image(root: Path | None = None) -> list[str]:
    offenders = []
    for scenario, platform, image in scenario_platform_images(root):
        if image is None:
            continue
        _, _, digest = parse_image_reference(image)
        if not CONTENT_DIGEST.fullmatch(digest):
            offenders.append(f"{scenario}: {platform} -> {image}")
    return offenders


def image_repositories_named_at_disagreeing_digests(root: Path | None = None) -> list[str]:
    """Report each image repository named at more than one digest across the
    authored scenarios. A scenario carrying no digest counts as its own value,
    so a partial refresh -- and a partial pin -- is a disagreement."""
    by_repository: dict[str, dict[str, list[str]]] = {}
    for scenario, platform, image in scenario_platform_images(root):
        if image is None:
            continue
        repository, _, digest = parse_image_reference(image)
        by_repository.setdefault(repository, {}).setdefault(digest or "<no digest>", []).append(
            f"{scenario}: {platform}"
        )
    return sorted(
        f"{repository} is named at {len(by_digest)} different digests: "
        + "; ".join(f"{digest} by {sorted(where)}" for digest, where in sorted(by_digest.items()))
        for repository, by_digest in by_repository.items()
        if len(by_digest) > 1
    )


def scenario_document(image: str | None, extra: str = "") -> str:
    """A minimal but structurally real scenario definition for a fixture tree."""
    body = "---\ndriver:\n  name: docker\nplatforms:\n  - name: instance\n"
    if image is not None:
        body += f"    image: {image}\n"
    return body + extra


DEFAULT_FIXTURE_MANIFEST = 'roles:\n  - name: geerlingguy.docker\n    version: "8.0.0"\n'


class ScenarioTreeFixtureMixin:
    """Builds throwaway trees shaped like `ansible/`.

    The checks above take their root as an argument, so every negative case
    below -- an unpinned scenario, a scenario with no image, a partial digest
    refresh, an unresolvable manifest entry -- is exercised against a fixture
    rather than by temporarily damaging the real tree.
    """

    def scratch_tree(
        self,
        scenarios: dict[tuple[str, str], str],
        manifest: str | None = DEFAULT_FIXTURE_MANIFEST,
    ) -> Path:
        root = Path(tempfile.mkdtemp(prefix="molecule-pin-fixture-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "ansible").mkdir()
        if manifest is not None:
            (root / "ansible" / "requirements.yml").write_text(manifest, encoding="utf-8")
        for (role, scenario), document in scenarios.items():
            directory = root / "ansible" / "roles" / role / "molecule" / scenario
            directory.mkdir(parents=True)
            (directory / "molecule.yml").write_text(document, encoding="utf-8")
        return root

    def discovered(self, root: Path) -> list[str]:
        return [path.relative_to(root).as_posix() for path in authored_scenario_files(root)]


PINNED_IMAGE = (
    "geerlingguy/docker-ubuntu2204-ansible:latest"
    "@sha256:0000000000000000000000000000000000000000000000000000000000000000"
)
OTHER_PINNED_IMAGE = (
    "geerlingguy/docker-ubuntu2204-ansible:latest"
    "@sha256:1111111111111111111111111111111111111111111111111111111111111111"
)


class TestMoleculeScenarioDiscoveryIsBoundedByThePinnedManifest(
    ScenarioTreeFixtureMixin, unittest.TestCase
):
    """MODIFIED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge -- the clause bounding the pinning obligation to the scenarios
    this repository authors."""

    def test_discovery_finds_the_scenarios_this_repository_authors(self) -> None:
        """SPECIFIED -- scenario "Every scenario's platform image is pinned by
        digest" reads "every scenario definition this repository authors under
        `ansible/roles/*/molecule/`". Guards every check below from passing
        vacuously over an empty discovery, the same failure mode this
        requirement's "Discovering no roles fails rather than passes" scenario
        forbids of the workflow's own discovery."""
        discovered = self.discovered(ROOT)
        self.assertTrue(
            discovered,
            f"no scenario was discovered under {SCENARIO_GLOB}; every pinning "
            f"assertion below would pass having checked nothing",
        )

    def test_every_role_carrying_scenarios_contributes_at_least_one(self) -> None:
        """SPECIFIED -- same clause, read in the other direction: the obligation
        is over EVERY scenario this repository authors, so no role of its own may
        drop out of discovery. `roles_with_molecule_scenarios()` computes the
        role set from directory names independently of the glob above.

        `roles_with_molecule_scenarios()` rests on `role_names()`, which excludes
        a directory whose name contains a `.` -- the older, weaker of this file's
        two notions of "installed content". Subtracting the manifest-derived set
        as well keeps this assertion on the same rule the pinning checks use, so
        a Galaxy entry resolving to a dotless directory name (`ansible-role-docker`,
        say) cannot make it fail. Neither `role_names()` nor any test resting on
        it is touched."""
        discovered_roles = {
            path.relative_to(ROOT).parts[2] for path in authored_scenario_files()
        }
        missing = sorted(
            roles_with_molecule_scenarios() - galaxy_role_directories() - discovered_roles
        )
        self.assertEqual(
            [],
            missing,
            f"these roles carry a molecule/ directory but contributed no scenario "
            f"to the pinning check: {missing}",
        )

    def test_installed_galaxy_content_is_excluded_from_discovery(self) -> None:
        """SPECIFIED -- scenario "Installed Galaxy content is not held to this
        repository's pinning obligation": the checks SHALL exclude it, deriving
        the exclusion from that manifest.

        Read against the real tree, where the exclusion only has anything to do
        once the tree is provisioned. The second half runs only where the
        installed role is actually present, so that the test asserts the same
        thing on a runner that has installed nothing -- it never skips.
        """
        installed = galaxy_role_directories()
        offenders = [
            path.relative_to(ROOT).as_posix()
            for path in authored_scenario_files()
            if path.relative_to(ROOT).parts[2] in installed
        ]
        self.assertEqual(
            [],
            offenders,
            f"these scenarios belong to Galaxy content pinned in {GALAXY_MANIFEST} and "
            f"are not this repository's to pin: {offenders}",
        )
        raw = {path.relative_to(ROOT).as_posix() for path in ROOT.glob(SCENARIO_GLOB)}
        installed_scenarios = {
            path for path in raw if path.split("/")[2] in installed
        }
        if installed_scenarios:
            self.assertTrue(
                installed_scenarios - set(self.discovered(ROOT)),
                "the tree is provisioned and the unbounded glob sees installed Galaxy "
                "scenarios, but discovery excluded none of them",
            )

    def test_discovery_is_identical_with_and_without_installed_galaxy_content(self) -> None:
        """SPECIFIED -- the second half of that scenario: the checks SHALL
        "report the same result on a provisioned developer machine as on a
        continuous-integration runner that has installed nothing".

        Two fixture trees differing only by the presence of the installed role's
        directory. Asserting this on the real tree is impossible: it is in one
        state or the other, never both.
        """
        own = {("docker", "default"): scenario_document(PINNED_IMAGE)}
        runner = self.scratch_tree(own)
        provisioned = self.scratch_tree(
            {
                **own,
                ("geerlingguy.docker", "default"): scenario_document(
                    "geerlingguy/docker-${MOLECULE_DISTRO:-rockylinux9}-ansible:latest"
                ),
            }
        )
        self.assertEqual(
            self.discovered(runner),
            self.discovered(provisioned),
            "discovery returned a different scenario set on a provisioned tree than "
            "on one that has installed nothing",
        )
        self.assertEqual([], scenarios_with_an_unpinned_platform_image(provisioned))

    def test_the_exclusion_is_derived_from_the_manifest_rather_than_hardcoded(self) -> None:
        """SPECIFIED -- "SHALL derive that exclusion from the manifest's own
        contents rather than from a hardcoded list of role names, so that adding
        or removing pinned Galaxy content cannot leave the exclusion stale in
        either direction".

        Both directions: a role name added to the manifest drops out of
        discovery, and `geerlingguy.docker` -- the only name a hardcoded
        implementation would plausibly carry -- is discovered once the manifest
        stops naming it. A hardcoded string passes the test above and fails this.
        """
        scenarios = {
            ("some_vendored_role", "default"): scenario_document(PINNED_IMAGE),
            ("geerlingguy.docker", "default"): scenario_document(PINNED_IMAGE),
        }
        named = self.scratch_tree(
            scenarios, manifest='roles:\n  - name: some_vendored_role\n    version: "1.0.0"\n'
        )
        self.assertEqual(
            ["ansible/roles/geerlingguy.docker/molecule/default/molecule.yml"],
            self.discovered(named),
            "a role named in the manifest was not excluded, or a role the manifest "
            "does not name was excluded anyway",
        )
        unnamed = self.scratch_tree(scenarios, manifest="roles: []\n")
        self.assertEqual(
            [
                "ansible/roles/geerlingguy.docker/molecule/default/molecule.yml",
                "ansible/roles/some_vendored_role/molecule/default/molecule.yml",
            ],
            self.discovered(unnamed),
            "a manifest naming no role still excluded something, so the exclusion is "
            "not derived from the manifest",
        )

    def test_a_manifest_entry_that_cannot_be_named_fails_the_check(self) -> None:
        """SPECIFIED -- "SHALL NOT be exempt ... rather than being caught by
        review alone", read with design.md decision 3a: an entry the resolution
        cannot name SHALL fail the check identifying the entry, never yield a
        partial exclusion set."""
        root = self.scratch_tree(
            {("docker", "default"): scenario_document(PINNED_IMAGE)},
            manifest='roles:\n  - version: "8.0.0"\n',
        )
        with self.assertRaises(ManifestNotUsable) as raised:
            authored_scenario_files(root)
        self.assertIn("roles[0]", str(raised.exception))

    def test_a_missing_galaxy_manifest_fails_the_check(self) -> None:
        """SPECIFIED -- same clause. An absent manifest must not resolve to an
        empty exclusion set, which would silently hold installed Galaxy content
        to this repository's obligation, nor to a skipped check."""
        root = self.scratch_tree(
            {("docker", "default"): scenario_document(PINNED_IMAGE)}, manifest=None
        )
        with self.assertRaises(ManifestNotUsable) as raised:
            authored_scenario_files(root)
        self.assertIn(GALAXY_MANIFEST, str(raised.exception))

    def test_an_unparseable_galaxy_manifest_fails_the_check(self) -> None:
        """SPECIFIED -- same clause, for the other way the manifest can stop
        being readable."""
        root = self.scratch_tree(
            {("docker", "default"): scenario_document(PINNED_IMAGE)},
            manifest="roles:\n  - name: geerlingguy.docker\n   version: broken\n\t\n",
        )
        with self.assertRaises(ManifestNotUsable) as raised:
            authored_scenario_files(root)
        self.assertIn(GALAXY_MANIFEST, str(raised.exception))

    def test_a_manifest_entry_given_as_a_source_resolves_to_its_directory_name(self) -> None:
        """DERIVED -- design.md decision 3a states the resolution rule (`name`
        where given, else the `src` basename with any `.git` suffix and version
        qualifier stripped). The delta spec requires only that the exclusion be
        derived from the manifest, so the exact resolution is design-level, not
        SHALL text.

        Recorded as derived because it constrains the implementation beyond what
        a scenario states: today's manifest has one entry, in `name` form, so
        nothing in the repository exercises this path yet.
        """
        root = self.scratch_tree(
            {
                ("geerlingguy.docker", "default"): scenario_document(PINNED_IMAGE),
                ("docker", "default"): scenario_document(PINNED_IMAGE),
            },
            manifest=(
                "roles:\n"
                "  - src: https://github.com/geerlingguy/ansible-role-docker.git,8.0.0\n"
            ),
        )
        self.assertEqual(
            {"ansible-role-docker"},
            galaxy_role_directories(root),
            "a `src`-only entry did not resolve to the directory name ansible-galaxy "
            "installs it under",
        )
        self.assertEqual(
            {"geerlingguy.docker", "docker"},
            {path.relative_to(root).parts[2] for path in authored_scenario_files(root)},
            "resolving a `src`-only entry excluded a directory the manifest does not "
            "install to",
        )


class TestMoleculeScenarioImagesArePinnedByDigest(
    ScenarioTreeFixtureMixin, unittest.TestCase
):
    """MODIFIED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge -- the extension of the pinned-manifest obligation to the
    container image each scenario executes inside."""

    def test_every_scenario_declares_its_platform_image_by_immutable_digest(self) -> None:
        """SPECIFIED -- scenario "Every scenario's platform image is pinned by
        digest": "every declared platform image SHALL carry an immutable content
        digest, and a scenario declaring an image by mutable tag alone SHALL
        fail those checks".

        Also the only observable form scenario "An upstream re-push cannot change
        what the suite ran against" takes in a suite that makes no network call:
        the digest is asserted to be a content address (`sha256:` plus 64 hex),
        which is what makes a re-published tag unable to change what the
        reference resolves to. The registry's behaviour itself is not observable
        here -- see test-plan.md.

        Every entry of every scenario's `platforms:` list is checked, not only
        the first.
        """
        offenders = scenarios_with_an_unpinned_platform_image()
        self.assertEqual(
            [],
            offenders,
            f"these platform images carry no immutable content digest, so what the "
            f"suite runs against can change with no commit to this repository: "
            f"{offenders}",
        )

    def test_no_scenario_declares_a_platform_without_an_image(self) -> None:
        """SPECIFIED -- scenario "A scenario declaring no platform image fails
        rather than being skipped", read against the real tree."""
        offenders = scenarios_declaring_no_platform_image()
        self.assertEqual(
            [],
            offenders,
            f"these scenarios declare no platform, or a platform with no image, so "
            f"the pinning check has nothing to read for them: {offenders}",
        )

    def test_a_scenario_declaring_no_platform_image_is_reported_by_name(self) -> None:
        """SPECIFIED -- the discriminating half of that scenario: "the checks
        SHALL fail identifying that scenario, rather than passing over it".

        Three shapes a scenario can take that leave nothing to pin: no
        `platforms:` key, a platform entry with no `image:`, and an empty
        `platforms:` list.
        """
        root = self.scratch_tree(
            {
                ("no_platforms", "default"): "---\ndriver:\n  name: docker\n",
                ("no_image", "default"): scenario_document(None),
                ("empty_platforms", "default"): "---\ndriver:\n  name: docker\nplatforms: []\n",
                ("pinned", "default"): scenario_document(PINNED_IMAGE),
            }
        )
        reported = scenarios_declaring_no_platform_image(root)
        self.assertEqual(3, len(reported), f"expected three scenarios reported: {reported}")
        for role in ("no_platforms", "no_image", "empty_platforms"):
            self.assertTrue(
                any(f"ansible/roles/{role}/molecule/default/molecule.yml" in entry for entry in reported),
                f"the scenario under {role}/ was passed over rather than identified: {reported}",
            )
        self.assertFalse(
            any("/pinned/" in entry for entry in reported),
            f"a scenario that does declare an image was reported anyway: {reported}",
        )

    def test_scenarios_sharing_an_image_repository_name_the_same_digest(self) -> None:
        """SPECIFIED -- scenario "Scenarios sharing an image repository agree on
        its digest", read against the real tree."""
        offenders = image_repositories_named_at_disagreeing_digests()
        self.assertEqual(
            [],
            offenders,
            f"a partial refresh has left the suite running against two versions of the "
            f"same image while appearing pinned: {offenders}",
        )

    def test_a_partial_digest_refresh_is_reported(self) -> None:
        """SPECIFIED -- the discriminating half of that scenario: "a partial
        refresh leaving one at a different digest SHALL fail those checks".

        A pin left behind at a mutable tag is the same defect and is reported
        too: the surviving `:latest` is a value of its own, not an absence.
        """
        refreshed = self.scratch_tree(
            {
                ("docker", "default"): scenario_document(PINNED_IMAGE),
                ("hardening", "default"): scenario_document(OTHER_PINNED_IMAGE),
            }
        )
        offenders = image_repositories_named_at_disagreeing_digests(refreshed)
        self.assertTrue(
            offenders and "geerlingguy/docker-ubuntu2204-ansible" in offenders[0],
            f"two scenarios naming one repository at two digests were not reported: "
            f"{offenders}",
        )
        partly_pinned = self.scratch_tree(
            {
                ("docker", "default"): scenario_document(PINNED_IMAGE),
                ("hardening", "default"): scenario_document(
                    "geerlingguy/docker-ubuntu2204-ansible:latest"
                ),
            }
        )
        self.assertTrue(
            image_repositories_named_at_disagreeing_digests(partly_pinned),
            "a scenario left at a mutable tag while its sibling was pinned was not "
            "reported as a disagreement",
        )

    def test_a_scenario_on_a_different_image_repository_is_not_reported(self) -> None:
        """SPECIFIED -- the scoping clause: "This constrains only scenarios that
        already agree on an image; it does not require the suite to standardise
        on a single base image."

        Without this, an implementation asserting one digest across the whole
        suite would pass the test above while blocking a future scenario that
        legitimately needs a different base image.
        """
        root = self.scratch_tree(
            {
                ("docker", "default"): scenario_document(PINNED_IMAGE),
                ("debian_role", "default"): scenario_document(
                    "geerlingguy/docker-debian12-ansible:latest"
                    "@sha256:2222222222222222222222222222222222222222222222222222222222222222"
                ),
            }
        )
        self.assertEqual(
            [],
            image_repositories_named_at_disagreeing_digests(root),
            "two scenarios on different image repositories were required to name the "
            "same digest",
        )
        self.assertEqual([], scenarios_with_an_unpinned_platform_image(root))

    def test_every_platform_a_scenario_declares_is_checked_not_only_the_first(self) -> None:
        """SPECIFIED -- "every declared platform image": a scenario declaring two
        platforms with the first pinned would otherwise pass while running half
        its suite against a moving target."""
        root = self.scratch_tree(
            {
                ("two_platforms", "default"): (
                    "---\n"
                    "driver:\n"
                    "  name: docker\n"
                    "platforms:\n"
                    "  - name: first\n"
                    f"    image: {PINNED_IMAGE}\n"
                    "  - name: second\n"
                    "    image: geerlingguy/docker-ubuntu2204-ansible:latest\n"
                )
            }
        )
        offenders = scenarios_with_an_unpinned_platform_image(root)
        self.assertEqual(1, len(offenders), f"expected exactly the second platform: {offenders}")
        self.assertIn("second", offenders[0])

    def test_the_checks_reach_a_scenario_at_a_role_path_they_do_not_name(self) -> None:
        """SPECIFIED -- "A scenario SHALL NOT be exempt from this by being newly
        added: the obligation is over every scenario this repository authors".

        A scenario is placed at a role path that appears nowhere in this file, and
        the pinning, missing-image and digest-agreement checks are each asserted
        to reach it with no edit here. Asserting that the glob "is not a fixed
        list" would not establish this.
        """
        root = self.scratch_tree(
            {
                ("docker", "default"): scenario_document(PINNED_IMAGE),
                ("a_role_added_later", "a_scenario_added_later"): scenario_document(
                    "geerlingguy/docker-ubuntu2204-ansible:latest"
                ),
                ("another_role_added_later", "default"): scenario_document(None),
            }
        )
        added = "ansible/roles/a_role_added_later/molecule/a_scenario_added_later/molecule.yml"
        self.assertIn(added, self.discovered(root))
        self.assertEqual(
            [f"{added}: platforms[0] (instance) -> geerlingguy/docker-ubuntu2204-ansible:latest"],
            scenarios_with_an_unpinned_platform_image(root),
        )
        self.assertTrue(
            any(
                "another_role_added_later" in entry
                for entry in scenarios_declaring_no_platform_image(root)
            ),
            "a scenario added later declaring no image was passed over",
        )
        self.assertTrue(
            image_repositories_named_at_disagreeing_digests(root),
            "a scenario added later at a mutable tag did not disagree with its pinned "
            "sibling on the same repository",
        )


class TestImageReferenceParsing(unittest.TestCase):
    """MODIFIED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge. Unit-level cover for the reference splitting every check above
    depends on -- the smallest level at which these cases are observable."""

    def test_the_combined_tag_and_digest_form_is_read_as_pinned(self) -> None:
        """SPECIFIED -- "where a multi-architecture image is published, the
        digest declared SHALL be the multi-architecture one", together with
        design.md decision 1's `repo:tag@sha256:...` form. The tag alongside a
        digest informs the reader and carries no authority; the check must not
        read it as a mutable pin."""
        repository, tag, digest = parse_image_reference(PINNED_IMAGE)
        self.assertEqual("geerlingguy/docker-ubuntu2204-ansible", repository)
        self.assertEqual("latest", tag)
        self.assertEqual(PINNED_IMAGE.split("@", 1)[1], digest)

    def test_the_bare_digest_form_is_read_as_pinned(self) -> None:
        """SPECIFIED -- same clause. design.md decision 1 names
        `repo@sha256:...` as a fallback if the Docker driver rejects the
        combined form, so the check must accept either."""
        bare = "geerlingguy/docker-ubuntu2204-ansible@" + PINNED_IMAGE.split("@", 1)[1]
        repository, tag, digest = parse_image_reference(bare)
        self.assertEqual("geerlingguy/docker-ubuntu2204-ansible", repository)
        self.assertEqual("", tag)
        self.assertEqual(PINNED_IMAGE.split("@", 1)[1], digest)

    def test_a_registry_port_is_not_mistaken_for_a_tag(self) -> None:
        """DERIVED -- no scenario states this; it guards the parsing itself
        against a reference form this repository does not currently use. Nothing
        in the delta requires a registry host to be supported."""
        repository, tag, digest = parse_image_reference("registry.example:5000/img:1.2@sha256:abc")
        self.assertEqual("registry.example:5000/img", repository)
        self.assertEqual("1.2", tag)
        self.assertEqual("sha256:abc", digest)

    def test_a_mutable_tag_alone_yields_no_digest(self) -> None:
        """SPECIFIED -- "a scenario declaring an image by mutable tag alone SHALL
        fail those checks"."""
        self.assertEqual(
            ("geerlingguy/docker-ubuntu2204-ansible", "latest", ""),
            parse_image_reference("geerlingguy/docker-ubuntu2204-ansible:latest"),
        )

    def test_a_digest_that_is_not_a_content_address_is_not_accepted(self) -> None:
        """SPECIFIED -- "immutable content digest". A truncated or non-sha256
        value is not one, and accepting it would let a pin that resolves to
        nothing read as satisfying the requirement."""
        for digest in ("sha256:abc", "latest", "sha512:" + "a" * 128, "sha256:" + "A" * 64):
            self.assertIsNone(
                CONTENT_DIGEST.fullmatch(digest), f"{digest} was accepted as a content digest"
            )
        self.assertIsNotNone(CONTENT_DIGEST.fullmatch("sha256:" + "0" * 64))


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Gated Production Apply Applies the Reviewed Plan
# --------------------------------------------------------------------------


class TestApplyWorkflowTriggerIsPathFiltered(unittest.TestCase):
    """MODIFIED requirement: Gated Production Apply Applies the Reviewed Plan."""

    NON_INFRASTRUCTURE_PATHS = [
        "README.md",
        "docs/change-queue.md",
        "ansible/roles/docker/tasks/main.yml",
        "platform/docker-compose.yml",
        "openspec/specs/iac-cicd-pipeline/spec.md",
    ]

    def setUp(self) -> None:
        push = triggers(load_yaml(APPLY)).get("push") or {}
        self.push = push if isinstance(push, dict) else {}

    def test_the_push_trigger_declares_a_path_filter(self) -> None:
        """SPECIFIED -- "The apply workflow SHALL be triggered only by pushes
        that can affect the Terraform configuration, identified by a
        workflow-level path filter"."""
        self.assertIn(
            "paths",
            self.push,
            "apply.yml's push trigger declares no `paths:` filter, so every merge "
            "raises a production Environment approval request",
        )

    def test_the_path_filter_still_covers_terraform_changes(self) -> None:
        """SPECIFIED -- the filter identifies "pushes that can affect the
        Terraform configuration"; a module change alters the prod plan without
        touching the environment directory."""
        patterns = self.push.get("paths") or []
        self.assertTrue(patterns, "apply.yml's push trigger declares no `paths:` filter")
        for path in (
            "terraform/environments/prod/main.tf",
            "terraform/modules/server/main.tf",
            "terraform/modules/volume/variables.tf",
        ):
            self.assertTrue(
                any(gh_glob_matches(pattern, path) for pattern in patterns),
                f"apply.yml's paths filter would not trigger on a change to {path}",
            )

    def test_the_path_filter_excludes_changes_that_cannot_affect_infrastructure(self) -> None:
        """SPECIFIED -- scenario "A merge that cannot change infrastructure
        raises no approval request"."""
        patterns = self.push.get("paths") or []
        self.assertTrue(
            patterns,
            "apply.yml's push trigger declares no `paths:` filter, so this "
            "exclusion check would pass vacuously",
        )
        matched = [
            path
            for path in self.NON_INFRASTRUCTURE_PATHS
            if any(gh_glob_matches(pattern, path) for pattern in patterns)
        ]
        self.assertEqual(
            [],
            matched,
            "apply.yml would still run -- and request a production approval -- for "
            f"these non-infrastructure changes: {matched}",
        )

    def test_the_branch_constraint_is_intact(self) -> None:
        """SPECIFIED -- "`terraform apply` against the prod environment SHALL
        run only after a pull request is merged to `main`". Guards the path
        filter from being added in a way that drops the branch constraint."""
        branches = self.push.get("branches") or []
        self.assertEqual(["main"], list(branches), f"apply.yml push branches: {branches}")


class TestRequiredCheckIsNotPathFiltered(unittest.TestCase):
    """MODIFIED requirement: Gated Production Apply Applies the Reviewed Plan.

    The delta adds the constraint that the path filter is permissible only
    because the apply workflow is not a required check, and that a required
    check must not carry one. This asserts the second half.

    `promote-molecule-to-a-required-check` made a second workflow a required
    check, and that requirement's "The workflow that is registered as a
    required check" became "Any workflow that is registered as a required
    check". The workflows below are therefore named LITERALLY rather than read
    out of `REQUIRED_STATUS_CHECK_WORKFLOWS`, which
    `TestEveryRequiredCheckIsShapedToBeRegistrable` iterates. That is
    deliberate duplication, not an oversight: a loop over a mapping passes
    vacuously if the mapping is emptied, and this constraint is the one whose
    violation leaves every pull request in the repository unmergeable. Two
    workflows spelled out here cost one line each and survive that edit.

    The method name is left unchanged: it is a runner-selectable identifier
    that an archived `test-plan.md` cites.
    """

    LITERALLY_REQUIRED = (PR_VALIDATION, ANSIBLE_VERIFY)

    def test_the_two_lists_of_required_check_workflows_agree(self) -> None:
        """DERIVED -- no scenario states it. Deliberate duplication has a
        deliberate failure mode: a third required check added to
        `REQUIRED_STATUS_CHECK_WORKFLOWS` and not to `LITERALLY_REQUIRED` would
        leave the literal guard covering two of three workflows, silently. This
        is the assertion that makes forgetting loud instead."""
        self.assertEqual(
            sorted(REQUIRED_STATUS_CHECK_WORKFLOWS.values(), key=str),
            sorted(self.LITERALLY_REQUIRED, key=str),
            "the mapping the shape checks iterate and the literal tuple this class "
            "names have diverged; a workflow in one and not the other is covered by "
            "only half of the path-filter prohibition",
        )

    def test_the_required_check_declares_no_workflow_level_path_filter(self) -> None:
        """SPECIFIED -- "Any workflow that is registered as a required check
        SHALL NOT be path-filtered at the workflow level"."""
        for path in self.LITERALLY_REQUIRED:
            on = triggers(load_yaml(path))
            self.assertTrue(
                on,
                f"{path.name} declares no triggers at all, so this check would pass "
                "having read nothing",
            )
            for event, config in on.items():
                if not isinstance(config, dict):
                    continue
                for key in ("paths", "paths-ignore"):
                    self.assertNotIn(
                        key,
                        config,
                        f"{path.name}'s `{event}` trigger declares `{key}:`, which "
                        "leaves every non-matching pull request permanently pending "
                        "and so unmergeable",
                    )


class TestSavedPlanIsWhatGetsApplied(unittest.TestCase):
    """MODIFIED requirement: Gated Production Apply Applies the Reviewed Plan.

    Regression guards for scenarios the delta carries through unchanged.
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(APPLY)
        self.jobs = jobs(self.workflow)

    def _job_with_environment(self, name: str):
        return [
            job_name
            for job_name, job in self.jobs.items()
            if str(job.get("environment", "")) == name
            or (isinstance(job.get("environment"), dict) and job["environment"].get("name") == name)
        ]

    def test_exactly_one_job_declares_the_production_environment(self) -> None:
        """SPECIFIED -- scenario "Merge does not apply immediately" and
        "Apply credentials are inaccessible before approval": the plan job
        declares no `environment:`; the apply job declares
        `environment: production`."""
        matches = self._job_with_environment("production")
        self.assertEqual(
            1,
            len(matches),
            f"expected exactly one job declaring `environment: production`, found {matches}",
        )

    def test_the_planning_job_declares_no_environment(self) -> None:
        """SPECIFIED -- "A **plan job** that declares no `environment:`". This is
        what keeps the read-write token out of the pre-approval job."""
        planning = [
            name
            for name, job in self.jobs.items()
            if any(
                re.search(r"terraform\s+plan\b", str(step.get("run", "")))
                for step in (job.get("steps") or [])
            )
        ]
        self.assertTrue(planning, "no job in apply.yml runs `terraform plan`")
        offenders = [name for name in planning if "environment" in self.jobs[name]]
        self.assertEqual([], offenders, f"planning jobs declaring `environment:`: {offenders}")

    def test_the_apply_job_depends_on_the_planning_job(self) -> None:
        """SPECIFIED -- "An **apply job** that depends on the plan job"."""
        matches = self._job_with_environment("production")
        self.assertEqual(1, len(matches), f"expected one production job, found {matches}")
        needs = self.jobs[matches[0]].get("needs")
        self.assertTrue(needs, f"job {matches[0]} declares no `needs:` on the plan job")

    def test_the_apply_job_applies_a_saved_plan_file(self) -> None:
        """SPECIFIED -- scenario "Applied changes match the approved plan": the
        apply job "SHALL apply the saved `tfplan` artifact produced by the plan
        job", rather than recomputing a plan after approval."""
        matches = self._job_with_environment("production")
        self.assertEqual(1, len(matches), f"expected one production job, found {matches}")
        job = self.jobs[matches[0]]
        applies = [
            str(step.get("run"))
            for step in (job.get("steps") or [])
            if re.search(r"terraform\s+apply\b", str(step.get("run", "")))
        ]
        self.assertTrue(applies, f"job {matches[0]} runs no `terraform apply`")
        for command in applies:
            self.assertRegex(
                command,
                r"terraform\s+apply\b[^\n]*\btfplan\b",
                "the apply job does not apply the saved plan file; a plan recomputed "
                "after approval is not the diff the reviewer approved",
            )
        plans_after_approval = [
            str(step.get("run"))
            for step in (job.get("steps") or [])
            if re.search(r"terraform\s+plan\b", str(step.get("run", "")))
        ]
        self.assertEqual(
            [],
            plans_after_approval,
            "the approval-gated job recomputes a plan; it must apply the saved one",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Destroy Policy Gate
# --------------------------------------------------------------------------


class TestDestroyPolicyGateFailsClosed(unittest.TestCase):
    """MODIFIED requirement: Destroy Policy Gate.

    Structural assertions over the gate's shell. They do not establish the
    scenarios behaviorally -- design Decision 5 deliberately keeps the gate as
    inline workflow shell rather than a script with fixtures, and queues the
    extraction separately. See the test plan.
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(APPLY)
        self.gate_steps = [
            (job, index, step)
            for job, index, step in steps(self.workflow)
            if "resource_changes" in str(step.get("run", ""))
        ]

    def test_the_gate_exists(self) -> None:
        """SPECIFIED -- the gate "SHALL inspect its plan's machine-readable form
        (`terraform show -json`)". Guards the tests below from passing
        vacuously over a workflow that no longer has a gate."""
        self.assertTrue(
            self.gate_steps,
            "no step in apply.yml inspects a plan's `resource_changes`",
        )

    def test_the_gate_does_not_swallow_an_inspection_failure(self) -> None:
        """DERIVED (design Decision 5) -- the scenario "An uninspectable plan
        blocks the pipeline" states the outcome; `|| true` on the inspection is
        the specific mechanism design Decision 5 names as the current defect. A
        `|| true` leaves the empty string behind, which takes the pass branch.
        """
        self.test_the_gate_exists()
        offenders = [
            step_label(job, index, step)
            for job, index, step in self.gate_steps
            if "|| true" in str(step["run"])
        ]
        self.assertEqual(
            [],
            offenders,
            "the destroy-policy gate tolerates a failed inspection with `|| true`, "
            f"so 'I could not tell' reads as 'the plan is safe': {offenders}",
        )

    def test_the_gate_asserts_the_document_is_a_terraform_plan(self) -> None:
        """DERIVED (design Decision 5, route 2) -- `.resource_changes[]?`
        suppresses the missing-key error, so a well-formed JSON document that is
        not a plan evaluates to a legitimate `false` and the gate reports
        inspected-and-clean. Plan identity has to be asserted separately."""
        self.test_the_gate_exists()
        offenders = [
            step_label(job, index, step)
            for job, index, step in self.gate_steps
            if "format_version" not in str(step["run"])
        ]
        self.assertEqual(
            [],
            offenders,
            "the destroy-policy gate never asserts `format_version`, so a "
            "well-formed document that is not a Terraform plan would be reported "
            f"as inspected and clean: {offenders}",
        )

    def test_the_gate_distinguishes_an_uninspectable_plan_from_a_clean_one(self) -> None:
        """SPECIFIED -- "SHALL fail the workflow with a message distinguishing
        it from a plan that was inspected and found clean" (scenario "An
        uninspectable plan blocks the pipeline"). Establishes that two distinct
        messages exist in the gate's shell, not that each is reached."""
        self.test_the_gate_exists()
        for job, index, step in self.gate_steps:
            script = str(step["run"]).lower()
            self.assertTrue(
                re.search(r"inspect|could not (be )?(read|render|determine)|not a .*plan", script),
                f"{step_label(job, index, step)} carries no message identifying plan "
                "inspection as a cause of failure, so an uninspectable plan would "
                "fail indistinguishably from any other crash",
            )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / The Continuous-Integration Configuration Is Itself Verified
# --------------------------------------------------------------------------

SUITE_PATH = Path(__file__).resolve()
SUITE_DIR = SUITE_PATH.parent
SUITE_MARKER = ".github/tests"


class TestTheSuiteIsWiredIntoTheRequiredCheck(unittest.TestCase):
    """ADDED requirement: The Continuous-Integration Configuration Is Itself
    Verified."""

    def setUp(self) -> None:
        self.workflow = load_yaml(PR_VALIDATION)
        self.invoking = [
            (job, index, step)
            for job, index, step in steps(self.workflow)
            if SUITE_MARKER in str(step.get("run", ""))
        ]

    def test_the_required_check_invokes_the_suite(self) -> None:
        """SPECIFIED -- "that suite SHALL run on every pull request as part of
        the required status check". Guards the two tests below from passing
        vacuously over a workflow that never runs the suite at all."""
        self.assertTrue(
            self.invoking,
            f"no step in pr-validation.yml runs the suite under {SUITE_MARKER}/",
        )

    def test_the_step_invoking_the_suite_is_unconditional(self) -> None:
        """SPECIFIED -- scenario "The suite runs regardless of what a pull
        request touched", and the requirement's "unconditionally". Checks the
        step and its job, because moving the condition to the job would leave a
        step-level assertion green while reopening the hole."""
        self.test_the_required_check_invokes_the_suite()
        step_offenders = [
            step_label(job, index, step)
            for job, index, step in self.invoking
            if step.get("if") is not None
        ]
        self.assertEqual(
            [],
            step_offenders,
            f"these steps gate the suite behind an `if:`: {step_offenders}",
        )
        job_offenders = sorted(
            {job for job, _, _ in self.invoking if jobs(self.workflow)[job].get("if") is not None}
        )
        self.assertEqual(
            [], job_offenders, f"these jobs gate the suite behind an `if:`: {job_offenders}"
        )

    def test_the_step_invoking_the_suite_does_not_swallow_its_result(self) -> None:
        """SPECIFIED -- scenario "A regression in CI configuration fails the
        pull request that introduces it": the required status check SHALL fail.
        A `continue-on-error` step reports green for a failed suite."""
        self.test_the_required_check_invokes_the_suite()
        offenders = [
            step_label(job, index, step)
            for job, index, step in self.invoking
            if step.get("continue-on-error")
        ]
        self.assertEqual([], offenders, f"steps using continue-on-error: {offenders}")


class TestTheSuiteDiscriminates(unittest.TestCase):
    """ADDED requirement: The Continuous-Integration Configuration Is Itself
    Verified.

    A suite that is always red, or always green, fails the pull request either
    way it is read and establishes nothing. This pair runs the suite as a
    subprocess against two synthetic repositories differing in exactly one
    property, and asserts the verdict differs. It is the executable form of the
    "absence of evidence read as evidence of absence" objection this capability
    raises against its own destroy gate and its own secret scanning.
    """

    DEPENDABOT_TEST = (
        "test_ci_configuration.TestDependabotCoverage"
        ".test_every_terraform_lockfile_directory_appears_in_dependabot_config"
    )

    def _scratch_repo(self, covered_directories: list[str]) -> Path:
        root = Path(tempfile.mkdtemp(prefix="ci-suite-fixture-"))
        (root / "openspec").mkdir()
        (root / "openspec" / "config.yaml").write_text("schema: spec-driven\n")
        for module in ("server", "volume"):
            module_dir = root / "terraform" / "modules" / module
            module_dir.mkdir(parents=True)
            (module_dir / ".terraform.lock.hcl").write_text("# fixture\n")
        listed = "\n".join(f"      - {directory}" for directory in covered_directories)
        (root / ".github").mkdir()
        (root / ".github" / "dependabot.yml").write_text(
            "version: 2\n"
            "updates:\n"
            "  - package-ecosystem: terraform\n"
            "    directories:\n"
            f"{listed}\n"
            "    schedule:\n"
            "      interval: weekly\n"
            "  - package-ecosystem: github-actions\n"
            "    directory: /\n"
            "    schedule:\n"
            "      interval: weekly\n"
        )
        return root

    def _run_against(self, root: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "unittest", self.DEPENDABOT_TEST],
            cwd=SUITE_DIR,
            env=dict(os.environ, REPO_ROOT=str(root), PYTHONPATH=str(SUITE_DIR)),
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_the_suite_fails_a_configuration_that_violates_a_required_property(self) -> None:
        """SPECIFIED -- scenario "A regression in CI configuration fails the
        pull request that introduces it"."""
        root = self._scratch_repo(["/terraform/modules/server"])
        try:
            result = self._run_against(root)
            self.assertNotEqual(
                0,
                result.returncode,
                "the suite reported success against a fixture whose Dependabot "
                "configuration omits a lockfile-bearing directory, so a regression "
                "of exactly the kind this change fixes would not fail a pull request",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_the_suite_passes_a_configuration_that_satisfies_it(self) -> None:
        """SPECIFIED -- the converse half of the same scenario. Without it, a
        suite that always fails would satisfy the test above while failing every
        pull request regardless of what it changed."""
        root = self._scratch_repo(["/terraform/modules/server", "/terraform/modules/volume"])
        try:
            result = self._run_against(root)
            self.assertEqual(
                0,
                result.returncode,
                "the suite reported failure against a fixture that satisfies the "
                "property, so its verdict does not depend on the configuration: "
                f"{(result.stdout + result.stderr).strip()[-800:]}",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestTheSuiteNeedsNoPrivilegedResource(unittest.TestCase):
    """ADDED requirement: The Continuous-Integration Configuration Is Itself
    Verified."""

    ALLOWED_THIRD_PARTY = {"yaml"}

    def test_the_suite_imports_only_the_standard_library_and_pinned_dependencies(self) -> None:
        """SPECIFIED -- "SHALL depend only on its runtime's standard library
        and on dependencies pinned exactly in a repository manifest", and
        scenario "The suite needs no privileged or external resource".

        The requirement is language-agnostic. This suite's runtime is Python
        (design Decision 7), so "its runtime's standard library" resolves to
        `sys.stdlib_module_names` below. The method name is left unchanged: it
        is a runner-selectable identifier that `test-plan.md` cites.
        """
        tree = ast.parse(SUITE_PATH.read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
        outside = sorted(
            root
            for root in roots
            if root not in sys.stdlib_module_names and root not in self.ALLOWED_THIRD_PARTY
        )
        self.assertEqual(
            [],
            outside,
            f"the suite imports modules that are neither standard library nor a "
            f"pinned dependency: {outside}",
        )

    SPAWNABLE = {"bash", "sh"}
    NETWORK_MODULES = {"urllib", "http", "socket", "ssl", "ftplib", "smtplib", "requests", "httpx"}

    def test_the_suite_spawns_no_terraform_binary_or_container_runtime(self) -> None:
        """SPECIFIED -- scenario "The suite needs no privileged or external
        resource": it completes without a container runtime or a Terraform
        binary.

        Reads the suite's own `subprocess` calls out of its AST rather than
        grepping its text: the string "terraform" occurs legitimately as a
        Dependabot ecosystem name, and a text match cannot tell that from a
        command being run.
        """
        tree = ast.parse(SUITE_PATH.read_text(encoding="utf-8"))
        spawned = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            if not (
                isinstance(target, ast.Attribute)
                and target.attr in ("run", "Popen", "call", "check_output", "check_call")
                and isinstance(target.value, ast.Name)
                and target.value.id == "subprocess"
            ):
                continue
            if not node.args:
                continue
            argv = node.args[0]
            if isinstance(argv, ast.List) and argv.elts:
                head = argv.elts[0]
                # `sys.executable` is the running interpreter, not an external tool.
                if isinstance(head, ast.Constant) and isinstance(head.value, str):
                    spawned.append(head.value)
            elif isinstance(argv, ast.Constant) and isinstance(argv.value, str):
                spawned.append(argv.value.split()[0] if argv.value.split() else argv.value)

        offenders = sorted({name for name in spawned if name not in self.SPAWNABLE})
        self.assertEqual(
            [],
            offenders,
            "the suite spawns commands outside the shell it needs to exercise a "
            f"workflow snippet: {offenders}",
        )

    def test_the_suite_imports_no_network_capable_module(self) -> None:
        """SPECIFIED -- scenario "The suite needs no privileged or external
        resource": it completes without a network call. Being standard-library
        only does not establish this; `urllib` is standard library."""
        tree = ast.parse(SUITE_PATH.read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
        offenders = sorted(roots & self.NETWORK_MODULES)
        self.assertEqual(
            [], offenders, f"the suite imports network-capable modules: {offenders}"
        )


# --------------------------------------------------------------------------
# iac-platform-services / Shared-Stack Service Images Are Pinned to an Exact
# Release, and Metrics Dashboards Are Available
#
# Derived from the delta specs of the OpenSpec change
# `fix-volume-discovery-and-consistency`, before any implementation of that
# change existed. Both requirements named in this section's heading above are
# held in `iac-platform-services`
# (openspec/specs/iac-platform-services/spec.md). See that change's
# test-plan.md for the scenario-to-test mapping, the baseline, and the
# scenarios deliberately left uncovered.
#
# These assertions live in THIS suite rather than in `terraform test` or in a
# Molecule scenario because both are static reads of a committed file the
# pipeline deploys: `platform/docker-compose.yml` is read and deployed by
# `.github/workflows/platform-deploy.yml` (AGENTS.md, "Testing"; design.md
# Decision 7). Neither needs a network call, a credential, a container runtime
# or a Terraform binary, and neither adds an import.
# --------------------------------------------------------------------------

PLATFORM_COMPOSE = ROOT / "platform" / "docker-compose.yml"

# Tags naming a channel rather than a version. Every one of them also names
# zero version components, so the floor below already rejects each; they are
# named separately because the scenario states the rejection of `latest` and
# other channel tags as an obligation of its own, and because a failure that
# says "this is a channel tag" tells the reader more than one that says "fewer
# than two version components".
CHANNEL_TAGS = frozenset(
    {
        "latest",
        "stable",
        "edge",
        "main",
        "master",
        "nightly",
        "dev",
        "devel",
        "release",
        "current",
        "rolling",
    }
)

# The FLOOR, and never a ceiling: two is the fewest version components any
# publisher represented in this stack uses for a release (PostgreSQL's release
# version has two), so no correctly pinned tag can name fewer. Nothing below
# rejects a tag for naming MORE -- a ceiling would reject `traefik:v3.7.10` and
# `postgres:16.15` alike, which is the contradiction design.md Decision 7
# records.
VERSION_COMPONENT_FLOOR = 2

# `${VAR}`, `${VAR:-default}` and the bare `$VAR` form, which is what Compose
# interpolation accepts.
COMPOSE_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)[^}]*\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def compose_variables(text: str) -> set[str]:
    """Every environment variable name a Compose value interpolates."""
    return {braced or bare for braced, bare in COMPOSE_VARIABLE.findall(text)}


def tag_version_components(tag: str) -> int:
    """How many leading numeric version components a tag names.

    `16` -> 1, `16.15` -> 2, `v3.7.10` -> 3, `latest` -> 0, `16.15-alpine` -> 2.
    A leading `v` and a trailing variant suffix are stripped because they are
    naming conventions, not version components; counting stops at the first
    non-numeric component so a tag such as `16.15rc1` is not credited with a
    component it does not have.
    """
    core = tag.split("-", 1)[0].split("_", 1)[0]
    if core[:1] in ("v", "V"):
        core = core[1:]
    count = 0
    for part in core.split("."):
        if not part.isdigit():
            break
        count += 1
    return count


def image_names_a_release(image: str) -> bool:
    """Whether an image reference passes the NECESSARY condition this suite can
    decide: a content digest, or a tag naming at least `VERSION_COMPONENT_FLOOR`
    version components and not naming a channel.

    Passing establishes only a necessary condition. See the class docstrings
    below for what it does not establish.
    """
    _, tag, digest = parse_image_reference(image)
    if CONTENT_DIGEST.fullmatch(digest):
        return True
    if not tag or tag.lower() in CHANNEL_TAGS:
        return False
    return tag_version_components(tag) >= VERSION_COMPONENT_FLOOR


def compose_services(path: Path | None = None) -> dict:
    """The `services:` mapping of the shared platform stack definition.

    A definition with no services is a failure, not an empty result: every
    check below would otherwise pass having read nothing, which is the vacuous
    pass this suite forbids elsewhere.
    """
    target = PLATFORM_COMPOSE if path is None else path
    if not target.is_file():
        raise AssertionError(f"{target} does not exist")
    document = yaml.safe_load(target.read_text(encoding="utf-8"))
    services = document.get("services") if isinstance(document, dict) else None
    if not isinstance(services, dict) or not services:
        raise AssertionError(
            f"{target} declares no `services:` mapping, so every shared-stack "
            f"pinning assertion would pass having checked nothing"
        )
    return services


def compose_service_images(path: Path | None = None):
    """Yield (service, image) over every service the stack defines.

    A service declaring no `image:` yields `None` rather than being passed
    over -- a service silently exempted from a pinning check is
    indistinguishable from one that satisfies it.
    """
    for name, definition in sorted(compose_services(path).items()):
        image = definition.get("image") if isinstance(definition, dict) else None
        yield name, image if isinstance(image, str) and image.strip() else None


def shared_stack_services_naming_no_release(path: Path | None = None) -> list[str]:
    offenders = []
    for name, image in compose_service_images(path):
        if image is None:
            offenders.append(f"{name}: declares no image:")
        elif not image_names_a_release(image):
            offenders.append(f"{name}: {image}")
    return offenders


def service_environment(name: str, path: Path | None = None) -> dict:
    """A service's `environment:` block, in either the mapping or the
    `KEY=value` list form Compose accepts."""
    definition = compose_services(path).get(name)
    if not isinstance(definition, dict):
        raise AssertionError(f"the stack defines no service named {name!r}")
    environment = definition.get("environment")
    if isinstance(environment, dict):
        return {str(key): "" if value is None else str(value) for key, value in environment.items()}
    if isinstance(environment, list):
        pairs = {}
        for entry in environment:
            key, _, value = str(entry).partition("=")
            pairs[key] = value
        return pairs
    return {}


def published_port_variables(name: str, path: Path | None = None) -> set[str]:
    """Every variable the service's published-port declarations interpolate."""
    definition = compose_services(path).get(name)
    if not isinstance(definition, dict):
        raise AssertionError(f"the stack defines no service named {name!r}")
    ports = definition.get("ports")
    if not isinstance(ports, list):
        return set()
    referenced: set[str] = set()
    for entry in ports:
        referenced |= compose_variables(str(entry))
    return referenced


def url_host(url: str) -> str:
    """The host part of an absolute URL, port and path removed.

    Deliberately not `urllib.parse`: importing `urllib` would trip this suite's
    own `test_the_suite_imports_no_network_capable_module`, and the parsing
    needed here is a split on `://` and `/`.
    """
    authority = url.split("://", 1)[-1].split("/", 1)[0]
    return re.sub(r":\d+$", "", authority)


DASHBOARD_SERVICE = "grafana"
DASHBOARD_ROOT_URL = "GF_SERVER_ROOT_URL"


def dashboard_base_url_offence(path: Path | None = None) -> str | None:
    """Why the dashboard's configured base URL fails the requirement, or None.

    Returns a sentence rather than a boolean so a failing assertion names which
    of the several ways it can fail actually occurred.
    """
    environment = service_environment(DASHBOARD_SERVICE, path)
    if DASHBOARD_ROOT_URL not in environment:
        return f"the {DASHBOARD_SERVICE} service declares no {DASHBOARD_ROOT_URL}"
    url = environment[DASHBOARD_ROOT_URL]
    host = url_host(url)
    referenced = compose_variables(host)
    if not referenced:
        return (
            f"{DASHBOARD_ROOT_URL} is {url!r}, whose host {host!r} is a literal "
            f"address rather than an interpolation of the value that determines "
            f"where the interface is published"
        )
    published = published_port_variables(DASHBOARD_SERVICE, path)
    if not published:
        return (
            f"the {DASHBOARD_SERVICE} service publishes no port through an "
            f"interpolated variable, so there is nothing for {DASHBOARD_ROOT_URL} "
            f"to be derived from"
        )
    if not referenced & published:
        return (
            f"{DASHBOARD_ROOT_URL} is {url!r}, interpolating {sorted(referenced)}, "
            f"while the published port uses {sorted(published)}: the base URL is "
            f"not derived from the same value that determines the address it is "
            f"published on"
        )
    return None


class TestSharedStackServiceImagesArePinnedToAnExactRelease(unittest.TestCase):
    """ADDED requirement: Shared-Stack Service Images Are Pinned to an Exact
    Release.

    WHAT PASSING THIS CLASS ESTABLISHES, AND WHAT IT DOES NOT
    --------------------------------------------------------
    Only a NECESSARY condition. Which tags float is a property of the
    publisher, not of the tag's shape, and cannot be read off a committed file:
    PostgreSQL's release version has two components, so `postgres:16` floats
    while `postgres:16.15` is a release, whereas the other publishers in this
    stack release `MAJOR.MINOR.PATCH`, where a two-component tag is a series.
    A tag specific enough to pass this floor may therefore still be a series
    under its own publisher's scheme -- `traefik:v3.7` would pass here and is
    not a release. That residue is carried by the human review every change to
    the stack definition already passes through (the requirement splits the
    obligation deliberately), and no assertion below should be read as
    discharging it.

    The condition is a floor on specificity and NEVER a ceiling: nothing here
    rejects a tag for being more specific than some threshold, because such a
    rule would reject correctly pinned releases, `postgres:16.15` among them.
    """

    def test_the_check_reads_every_service_the_stack_defines(self) -> None:
        """DERIVED -- no scenario states it. It guards every assertion below
        from passing vacuously over an empty or partial read of the file, the
        same failure mode this suite's Molecule-pinning section guards against
        with its own discovery test."""
        services = sorted(compose_services())
        read = sorted(name for name, _ in compose_service_images())
        self.assertTrue(services, "the stack definition declares no services")
        self.assertEqual(
            services,
            read,
            "the pinning check does not read every service the stack defines, so a "
            "service could be added and never checked",
        )

    def test_every_shared_stack_service_names_an_exact_release(self) -> None:
        """SPECIFIED -- scenario "A service declares a tag that names no
        specific release", and scenario "The automated check enforces a floor
        and says so": the check rejects `latest`, any other tag naming a
        channel, and any tag naming fewer than two version components.

        Passing establishes only the necessary condition described in this
        class's docstring -- a tag specific enough to pass may still be a
        series under its own publisher's scheme, and that residue is carried by
        human review, not by this test.
        """
        offenders = shared_stack_services_naming_no_release()
        self.assertEqual(
            [],
            offenders,
            "these shared-stack services do not name an exact release -- each names "
            "a channel tag, a tag naming fewer than "
            f"{VERSION_COMPONENT_FLOOR} version components, or no image at all, so "
            "the version actually running is a function of when the last deploy "
            f"happened rather than of what is committed: {offenders}",
        )

    def test_a_two_component_postgresql_release_is_accepted(self) -> None:
        """SPECIFIED -- scenario "The check does not reject a correctly pinned
        release": a service naming a release with the number of components its
        own publisher uses, such as a two-component PostgreSQL release, is
        accepted."""
        self.assertTrue(
            image_names_a_release("postgres:16.15"),
            "postgres:16.15 is a PostgreSQL release, and a check that rejected it "
            "would be a ceiling on specificity rather than a floor",
        )

    def test_a_bare_series_tag_is_rejected(self) -> None:
        """SPECIFIED -- same scenario's rejection of "a tag naming a version
        series that its publisher repoints at each new release within that
        series"."""
        for image in ("postgres:16", "traefik:v3", "grafana/grafana:12"):
            with self.subTest(image=image):
                self.assertFalse(
                    image_names_a_release(image),
                    f"{image} names a bare series, which cannot name a release under "
                    f"any publisher's scheme",
                )

    def test_a_channel_tag_is_rejected(self) -> None:
        """SPECIFIED -- scenario "The automated check enforces a floor and says
        so": the check rejects `latest` and any other tag naming a channel
        rather than a version. An image with no tag at all resolves to `latest`
        and is rejected for the same reason."""
        for image in (
            "postgres:latest",
            "traefik:stable",
            "prom/prometheus:edge",
            "grafana/grafana:main",
            "postgres",
        ):
            with self.subTest(image=image):
                self.assertFalse(
                    image_names_a_release(image),
                    f"{image} names a channel rather than a release",
                )

    def test_a_more_specific_tag_is_never_rejected_for_being_specific(self) -> None:
        """SPECIFIED -- "The necessary condition SHALL be a floor on
        specificity, never a ceiling". A ceiling is the defect the round-1
        draft carried (design.md Decision 7); this is the assertion that would
        catch its reintroduction."""
        for image in (
            "traefik:v3.7.10",
            "prom/node-exporter:v1.9.1",
            "ghcr.io/google/cadvisor:v0.60.5",
            "grafana/grafana:12.3.0",
            "postgres:16.15.2",
            "postgres:16.15-alpine",
        ):
            with self.subTest(image=image):
                self.assertTrue(
                    image_names_a_release(image),
                    f"{image} was rejected for naming more version components than "
                    f"the floor requires, which makes the check a ceiling",
                )

    def test_a_content_digest_is_accepted_whatever_its_tag(self) -> None:
        """SPECIFIED -- "an immutable content digest, or the tag its publisher
        assigns to one release". The requirement admits either form; it does
        not adopt `iac-cicd-pipeline`'s digest-only remedy."""
        digest = "@sha256:" + "0" * 64
        self.assertTrue(image_names_a_release("postgres" + digest))
        self.assertTrue(image_names_a_release("postgres:16" + digest))

    def test_the_check_records_that_it_establishes_only_a_necessary_condition(self) -> None:
        """SPECIFIED -- scenario "The automated check enforces a floor and says
        so", second limb: the check "SHALL record that passing establishes only
        a necessary condition -- a tag specific enough to pass may still be a
        series under its own publisher's scheme, and that residue is carried by
        human review".

        Asserted over this class's own docstring, which is where that record
        lives. A caveat nobody can delete without a test failing is the only
        form of "SHALL record" an automated check can actually keep.
        """
        recorded = (type(self).__doc__ or "").lower()
        for phrase in ("necessary condition", "human review", "publisher"):
            with self.subTest(phrase=phrase):
                self.assertIn(
                    phrase,
                    recorded,
                    "the pinning check no longer records what passing it does and does "
                    "not establish, so it now presents its necessary condition as the "
                    "whole obligation -- which reports a floating tag as pinned",
                )


class TestTheSharedStackPinningCheckIsARealReadOfTheFile(unittest.TestCase):
    """ADDED requirement: Shared-Stack Service Images Are Pinned to an Exact
    Release.

    An assertion that silently covered only the services that exist today would
    pass the class above identically while catching nothing a later edit
    introduces. These tests run the same check over throwaway stack definitions
    that differ from the committed one in exactly one property, so the check's
    verdict is shown to depend on the file rather than on an enumeration
    written into the test.
    """

    GRAFANA_BLOCK = (
        "  grafana:\n"
        "    image: grafana/grafana:12.3.0\n"
        "    environment:\n"
        "      GF_SERVER_ROOT_URL: http://${GRAFANA_BIND_ADDRESS}:3000\n"
        '    ports:\n      - "${GRAFANA_BIND_ADDRESS}:3000:3000"\n'
    )

    def compose_fixture(self, services: str) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="platform-compose-fixture-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "docker-compose.yml"
        path.write_text("---\nservices:\n" + services, encoding="utf-8")
        return path

    def test_a_service_added_with_a_moving_tag_is_caught_with_no_test_edit(self) -> None:
        """SPECIFIED -- scenario "A service declares a tag that names no
        specific release" holds of "every service defined in the shared
        platform Compose stack", including one that does not exist yet."""
        fixture = self.compose_fixture(
            self.GRAFANA_BLOCK + "  newcomer:\n    image: redis:latest\n"
        )
        self.assertEqual(
            ["newcomer: redis:latest"],
            shared_stack_services_naming_no_release(fixture),
            "a service added to the stack with a moving tag was not caught, so the "
            "check enumerates the services it knows about rather than reading the "
            "file",
        )

    def test_a_service_declaring_no_image_fails_by_name_rather_than_being_skipped(self) -> None:
        """DERIVED -- no scenario states it. A service passed over for
        declaring no `image:` is indistinguishable from one that satisfies the
        requirement, which is the vacuous pass this suite forbids elsewhere."""
        fixture = self.compose_fixture(
            self.GRAFANA_BLOCK + "  imageless:\n    restart: unless-stopped\n"
        )
        self.assertEqual(
            ["imageless: declares no image:"],
            shared_stack_services_naming_no_release(fixture),
            "a service declaring no image: was skipped rather than reported by name",
        )

    def test_a_stack_declaring_no_services_fails_rather_than_reading_nothing(self) -> None:
        """DERIVED -- the same non-vacuity guard, at the file level."""
        directory = Path(tempfile.mkdtemp(prefix="platform-compose-fixture-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "docker-compose.yml"
        path.write_text("---\nvolumes:\n  postgres_data:\n", encoding="utf-8")
        with self.assertRaises(AssertionError):
            shared_stack_services_naming_no_release(path)

    def test_a_stack_whose_services_all_name_releases_is_accepted(self) -> None:
        """DERIVED -- the converse half. Without it, a check that reported
        every service as an offender would satisfy the three tests above while
        failing every change to the stack regardless of what it changed."""
        fixture = self.compose_fixture(
            self.GRAFANA_BLOCK
            + "  postgres:\n    image: postgres:16.15\n"
            + "  traefik:\n    image: traefik:v3.7.10\n"
        )
        self.assertEqual([], shared_stack_services_naming_no_release(fixture))


class TestDashboardBaseUrlIsNotALiteralAddress(unittest.TestCase):
    """MODIFIED requirement: Metrics Dashboards Are Available -- the added
    clause obliging a generated absolute URL to address the host at the same
    private-tailnet address the interface is published on.

    This is the half of that obligation a static read can decide. That the URL
    Grafana actually serves changed is confirmed against the running host
    (design.md's Migration Plan step 3), not here.
    """

    def compose_fixture(self, root_url: str, ports: str = '"${GRAFANA_BIND_ADDRESS}:3000:3000"') -> Path:
        directory = Path(tempfile.mkdtemp(prefix="platform-compose-fixture-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "docker-compose.yml"
        path.write_text(
            "---\nservices:\n"
            "  grafana:\n"
            "    image: grafana/grafana:12.3.0\n"
            "    environment:\n"
            f"      GF_SERVER_ROOT_URL: {root_url}\n"
            "    ports:\n"
            f"      - {ports}\n",
            encoding="utf-8",
        )
        return path

    def test_the_configured_base_url_is_derived_from_where_the_interface_is_published(
        self,
    ) -> None:
        """SPECIFIED -- scenario "The configured base URL is not a literal that
        ignores where the interface is published": read from the stack's own
        definition, the base URL SHALL be derived from the same value that
        determines the address it is published on, rather than being a literal
        address -- including `localhost` -- that is correct only on the host
        itself."""
        offence = dashboard_base_url_offence()
        self.assertIsNone(
            offence,
            "the dashboard's configured base URL does not follow where the "
            f"interface is published: {offence}",
        )

    def test_any_literal_host_is_rejected_not_only_localhost(self) -> None:
        """SPECIFIED -- the same scenario's "rather than being a literal
        address -- including `localhost`". The word "including" is what makes
        this test necessary: a check keyed on the string `localhost` would pass
        a literal tailnet IP, which is equally a literal and equally wrong the
        moment the address changes."""
        for url in (
            "http://localhost:3000",
            "http://100.101.102.103:3000",
            "http://grafana.example.internal:3000",
            "http://127.0.0.1:3000",
        ):
            with self.subTest(url=url):
                self.assertIsNotNone(
                    dashboard_base_url_offence(self.compose_fixture(url)),
                    f"{url} is a literal address and was accepted",
                )

    def test_interpolating_a_different_variable_is_rejected(self) -> None:
        """SPECIFIED -- the same scenario's "derived from the same value that
        determines the address it is published on". An interpolation of some
        other variable is not a literal, but it is not derived from the
        publication either."""
        fixture = self.compose_fixture("http://${SOME_OTHER_ADDRESS}:3000")
        self.assertIsNotNone(
            dashboard_base_url_offence(fixture),
            "a base URL interpolating a variable unrelated to the published port "
            "was accepted",
        )

    def test_the_expected_form_is_accepted(self) -> None:
        """DERIVED -- the converse half. Without it, a check that rejected
        every URL would satisfy the two tests above while never being
        satisfiable."""
        fixture = self.compose_fixture("http://${GRAFANA_BIND_ADDRESS}:3000")
        self.assertIsNone(dashboard_base_url_offence(fixture))

    def test_an_absent_root_url_is_reported_rather_than_skipped(self) -> None:
        """DERIVED -- no scenario states it. A dashboard service declaring no
        base URL at all would otherwise pass a check written only over the
        value's shape."""
        directory = Path(tempfile.mkdtemp(prefix="platform-compose-fixture-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "docker-compose.yml"
        path.write_text(
            "---\nservices:\n  grafana:\n    image: grafana/grafana:12.3.0\n",
            encoding="utf-8",
        )
        self.assertIsNotNone(dashboard_base_url_offence(path))




# --------------------------------------------------------------------------
# iac-host-configuration / A Role's Absent Required Input Is Reported by Name
# --------------------------------------------------------------------------


REQUIRED_INPUT_ASSERTIONS = {
    "ansible/roles/hardening/tasks/main.yml": "hardening_ssh_allowed_cidrs",
    "ansible/roles/deploy_user/tasks/main.yml": "deploy_apps",
}

# Every limb the assertion needs, and why each is load-bearing. `is defined`
# alone leaves the undefined case; `is sequence` alone accepts a string, which
# Ansible then iterates character by character; `is not mapping` is the limb a
# code review had to add, because a dict satisfies BOTH `is sequence` and
# `is not string` and then dies in the consuming loop with "The `loop` value
# must resolve to a 'list', not 'dict'" -- the type error the requirement's
# "A required input is not supplied" scenario forbids.
REQUIRED_INPUT_LIMBS = ("is defined", "is sequence", "is not string", "is not mapping")


class TestRequiredRoleInputsAreAssertedBeforeTheRoleActs(unittest.TestCase):
    """ADDED requirement: A Role's Absent Required Input Is Reported by Name.

    A static read, because the behavioural cover is partial by design: the
    Molecule scenarios exercise the *absent* case only, so three of the four
    limbs -- including the one added in response to a review finding -- are
    asserted by nothing that runs. This class is what keeps a limb from being
    dropped again silently.
    """

    def _tasks(self, relative_path):
        parsed = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))
        self.assertIsInstance(
            parsed, list, f"{relative_path} did not parse as a task list"
        )
        return parsed

    def test_the_assertion_is_the_first_task_in_the_role(self) -> None:
        """SPECIFIED -- scenario "The check precedes the tasks that consume the
        input": the run SHALL fail "before any task that acts on the host has
        changed it". At role scope that means literally first, since neither
        role has a meta/main.yml to run anything ahead of it."""
        for path, variable in REQUIRED_INPUT_ASSERTIONS.items():
            with self.subTest(role=path):
                first = self._tasks(path)[0]
                self.assertIn(
                    "ansible.builtin.assert",
                    first,
                    f"{path}'s first task is {first.get('name')!r}, not an assert -- "
                    f"a task acting on the host now runs before {variable} is checked",
                )

    def test_no_role_dependency_runs_ahead_of_the_assertion(self) -> None:
        """SPECIFIED -- the premise the test above rests on. "First task in the
        file" only means "first thing that runs" while the role pulls in no
        dependency: a meta/main.yml declaring `dependencies:` would run another
        role, and its host-changing tasks, before the assert -- with every
        other test here still green."""
        for path, variable in REQUIRED_INPUT_ASSERTIONS.items():
            with self.subTest(role=path):
                meta = ROOT / Path(path).parent.parent / "meta" / "main.yml"
                if not meta.exists():
                    continue
                declared = (yaml.safe_load(meta.read_text(encoding="utf-8")) or {}).get(
                    "dependencies"
                )
                self.assertFalse(
                    declared,
                    f"{meta} declares dependencies {declared!r}; those roles run "
                    f"before the assertion guarding {variable}, so it is no longer "
                    f"the first thing that acts on the host",
                )

    def test_the_assertion_carries_every_limb(self) -> None:
        """SPECIFIED -- "rather than with an undefined-variable, index, or type
        error raised by a task that consumed it". Each missing limb readmits
        exactly one such error."""
        for path, variable in REQUIRED_INPUT_ASSERTIONS.items():
            with self.subTest(role=path):
                that = self._tasks(path)[0]["ansible.builtin.assert"]["that"]
                for limb in REQUIRED_INPUT_LIMBS:
                    self.assertIn(
                        f"{variable} {limb}",
                        that,
                        f"{path}'s assertion is missing `{variable} {limb}`; without "
                        f"it a value reaches the consuming loop and fails there",
                    )

    def test_no_default_was_introduced_for_the_asserted_variable(self) -> None:
        """SPECIFIED -- "SHALL NOT satisfy this obligation by adopting a default
        value". A default would make the assertion pass while substituting a
        wrong answer for a stated one, which is what its absence prevents."""
        for path, variable in REQUIRED_INPUT_ASSERTIONS.items():
            with self.subTest(role=path):
                defaults_path = Path(path).parent.parent / "defaults" / "main.yml"
                defaults = yaml.safe_load(
                    (ROOT / defaults_path).read_text(encoding="utf-8")
                ) or {}
                self.assertNotIn(
                    variable,
                    defaults,
                    f"{defaults_path} now defines {variable}; the assertion in {path} "
                    f"would pass on the default rather than on a supplied value",
                )


# --------------------------------------------------------------------------
# iac-repo-foundations / Source Files Cite Specifications by Path and Changes
# by Name
#
# Derived from the delta spec of the OpenSpec change
# `decide-archived-change-reference-policy`, before any implementation of that
# change existed. See that change's test-plan.md for the scenario-to-test
# mapping, the baseline, and the scenarios deliberately left uncovered. Both
# citations in this comment take the second of the two forms the requirement
# names -- the change's name and the artifact's name, in prose, with no path --
# because the artifacts they name live only inside a change and so have no
# permanent path to cite.
#
# Reflexivity note (design Decision 6). This suite is itself a committed file
# outside `openspec/`, so it is inside the set of files the check below reads.
# No fixture here may therefore carry a literal of the prohibited form: every
# one is assembled at run time from CHANGE_PATH_PREFIX and a separate segment.
# The matcher's own patterns need no such treatment -- there the prefix is
# followed by a regular-expression group rather than by a change-shaped
# segment, so the pattern does not match itself.
#
# These assertions live in THIS suite rather than in `terraform test` or in a
# Molecule scenario because they are a static read of committed files at
# repository scope, which is the only thing that can perform them: the
# requirement obliges the prohibition to be asserted by the executable suite
# that gates every pull request, and this is that suite (AGENTS.md, "Testing";
# design Decision 4). They add no import, spawn no subprocess, and need no
# network call, credential, container runtime or Terraform binary.
# --------------------------------------------------------------------------

CHANGE_PATH_PREFIX = "openspec/changes/"
ARCHIVE_SEGMENT = "archive"

# A change name's shape: lowercase kebab-case (design Decision 5). Requiring
# the shape rather than any segment is what lets documentation state the rule
# with a metasyntactic placeholder without tripping the check it describes.
_CHANGE_NAME = r"[a-z0-9]+(?:-[a-z0-9]+)*"

# Across a line break the segment must additionally carry a hyphen. Without
# that narrowing, any prose line ending in the prefix whose continuation begins
# with an ordinary lowercase word would be flagged. The requirement records
# what this excludes: a wrapped citation of a single-word change name.
_HYPHENATED_CHANGE_NAME = r"[a-z0-9]+(?:-[a-z0-9]+)+"

# Nothing is required after the segment. Twenty-seven of the citations this
# requirement removes name the change and stop there, and requiring a trailing
# separator is the exact error that made two earlier counts of the problem low.
CONTIGUOUS_CITATION = re.compile(
    re.escape(CHANGE_PATH_PREFIX) + r"(?P<segment>" + _CHANGE_NAME + r")"
)

WRAPPED_CITATION = re.compile(
    re.escape(CHANGE_PATH_PREFIX)
    + r"[ \t]*\r?\n[ \t]*(?:[#>*]+|//|--)?[ \t]*"
    + r"(?P<segment>"
    + _HYPHENATED_CHANGE_NAME
    + r")"
)

# Pruned wherever they occur, at any depth: `.terraform` in particular exists
# under each of `terraform/environments/*/`, and a root-anchored reading would
# leave the walk reading provider binaries.
#
# `__pycache__` is here because the requirement is scoped to committed files and
# `.gitignore` ignores it, so the compiled module is not one -- and because
# running this suite is what creates it, making it a false positive the check
# would inflict on itself on every run rather than one a developer provokes and
# can see. That is what separates it from the untracked scratch file design
# Decision 7 deliberately accepts.
# NOTE: this list and `PRUNED_AT_ROOT_RELATIVE` below hand-mirror part of
# `.gitignore`, and nothing keeps the two in step. The prohibition is over
# *committed* files, so an ignored path added to `.gitignore` later -- a second
# Galaxy role from `ansible/requirements.yml`, a repo-local `.venv`,
# `.pytest_cache` -- becomes readable here and can turn the check red on a file
# nobody committed. That is local-only; continuous integration checks out a
# clean tree. When adding an ignore rule for something that lands inside the
# working tree, add it here too.
PRUNED_ANYWHERE = frozenset({".git", ".terraform", "__pycache__", "node_modules"})

# Pruned only at their path relative to the walk root. `.claude` is NOT pruned
# wholesale, only its `worktrees` subdirectory: the files tracked under
# `.claude/commands/` and `.claude/skills/` are committed files outside
# `openspec/`, and the prohibition covers them (design Decision 7).
PRUNED_AT_ROOT_RELATIVE = frozenset(
    {"openspec", "ansible/roles/geerlingguy.docker", ".worktrees", ".claude/worktrees"}
)


def walked_files(root: Path | None = None) -> list[Path]:
    """Every file the prohibition covers, found by walking rather than by
    asking the version-control tool.

    `subprocess` is confined to `bash`/`sh` by this suite's own assertions, so
    a tracked-file listing is unavailable (design Decision 7). The walk is a
    superset of the tracked files -- an untracked scratch file in the tree is
    read too -- which is the safe direction for a prohibition.
    """
    root = ROOT if root is None else root
    found: list[Path] = []
    for directory, subdirectories, filenames in os.walk(root):
        here = Path(directory)
        relative = here.relative_to(root).as_posix()
        kept = []
        for name in sorted(subdirectories):
            child = name if relative == "." else f"{relative}/{name}"
            if name in PRUNED_ANYWHERE or child in PRUNED_AT_ROOT_RELATIVE:
                continue
            kept.append(name)
        subdirectories[:] = kept
        for name in sorted(filenames):
            path = here / name
            if path.is_file():
                found.append(path)
    return found


def pre_archive_citations(root: Path | None = None) -> list[str]:
    """Every citation of a change's own directory under `openspec/changes/`,
    as `<path>:<line>: <matched text>`.

    Raises rather than reporting a clean tree when the walk reaches no file at
    all: a check that read nothing would otherwise report success having
    verified nothing.
    """
    root = ROOT if root is None else root
    files = walked_files(root)
    if not files:
        raise AssertionError(
            f"the walk from {root} reached no file at all, so every citation "
            f"assertion over it would pass having read nothing"
        )
    offences: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        found = []
        for pattern in (CONTIGUOUS_CITATION, WRAPPED_CITATION):
            for match in pattern.finditer(text):
                if match.group("segment") == ARCHIVE_SEGMENT:
                    continue
                found.append((match.start(), match.group(0)))
        for offset, matched in sorted(found):
            line = text.count("\n", 0, offset) + 1
            relative = path.relative_to(root).as_posix()
            offences.append(f"{relative}:{line}: {' '.join(matched.split())}")
    return offences


class TestNoCommittedFileOutsideOpenSpecCarriesAPreArchiveCitation(unittest.TestCase):
    """ADDED requirement: Source Files Cite Specifications by Path and Changes
    by Name."""

    def test_the_walk_reaches_the_committed_files_the_prohibition_covers(self) -> None:
        """DERIVED -- no scenario states it. The requirement is normative over
        every committed file outside `openspec/`, and a walk that reached none
        of them would pass the assertion below having read nothing. Anchors on
        files at four different depths rather than on a count, which any edit
        to the repository would move."""
        walked = {path.relative_to(ROOT).as_posix() for path in walked_files()}
        anchors = {
            "AGENTS.md",
            "README.md",
            "platform/docker-compose.yml",
            ".github/tests/test_ci_configuration.py",
        }
        self.assertEqual(
            set(),
            anchors - walked,
            f"the walk did not reach these committed files: {sorted(anchors - walked)}",
        )

    def test_the_walk_reaches_the_tracked_files_under_the_agent_directory(self) -> None:
        """DERIVED -- design Decision 7, which prunes `.claude/worktrees` only
        and not `.claude` wholesale, because the files tracked beneath it are
        committed files outside `openspec/` and are the likeliest future source
        of the prohibited form: they document OpenSpec's change layout.

        Asserted against an enumeration of the directory rather than against a
        count of what it holds today. A count fails on an unrelated file the
        OpenSpec CLI adds or removes; this fails on what actually matters -- a
        prune-list edit that drops part of `.claude` out of the prohibition's
        scope. The two subtree assertions are the floor beneath it: without
        them, pruning `.claude` in its entirety would empty both sides of the
        comparison and pass.
        """
        agent_directory = ROOT / ".claude"
        if not agent_directory.is_dir():
            self.skipTest("this repository has no .claude/ directory")
        walked = {path.relative_to(ROOT).as_posix() for path in walked_files()}
        # Independent of PRUNED_AT_ROOT_RELATIVE, which is what this test is
        # about. It excludes only the `worktrees` subtree, which Decision 7
        # prunes because it is a second checkout of this repository, and the
        # any-depth entries, which are not at issue here.
        expected = {
            path.relative_to(ROOT).as_posix()
            for path in agent_directory.rglob("*")
            if path.is_file()
            and path.relative_to(agent_directory).parts[0] != "worktrees"
            and not set(path.relative_to(ROOT).parts) & PRUNED_ANYWHERE
        }
        missing = sorted(expected - walked)
        self.assertEqual(
            [],
            missing,
            f"the walk did not reach these files under .claude/, so the "
            f"prohibition is silently unenforced over them: {missing}",
        )
        for subtree in (".claude/commands/", ".claude/skills/"):
            self.assertTrue(
                any(name.startswith(subtree) for name in walked),
                f"the walk reached no file under {subtree}; pruning it would "
                f"drop the files OpenSpec installs there out of the "
                f"prohibition's scope without failing anything",
            )

    def test_no_committed_file_outside_openspec_carries_a_pre_archive_citation(self) -> None:
        """SPECIFIED -- "No committed file outside `openspec/` SHALL contain a
        path naming a change's own directory under `openspec/changes/`", and
        scenario "Archiving a change breaks no citation": a citation that names
        no change directory cannot be invalidated by that directory moving."""
        offences = pre_archive_citations()
        self.assertEqual(
            [],
            offences,
            f"{len(offences)} citation(s) name a change's own directory and so "
            f"break when that change is archived:\n" + "\n".join(offences),
        )

    def test_the_walk_reads_nothing_inside_the_specification_directory(self) -> None:
        """SPECIFIED -- scenario "A change's own artifacts are out of scope":
        the prohibition does not apply to a change's planning artifacts, live
        or archived, since they move together with what they cite."""
        inside = sorted(
            path.relative_to(ROOT).as_posix()
            for path in walked_files()
            if path.relative_to(ROOT).as_posix().startswith("openspec/")
        )
        self.assertEqual(
            [], inside, f"the walk descended into openspec/: {inside[:10]}"
        )

    def test_a_changes_own_artifacts_do_carry_the_form_the_walk_excludes(self) -> None:
        """DERIVED -- no scenario states it. Without it, the exclusion above is
        indistinguishable from an exclusion of a directory that never contained
        the form, and the scenario it covers would be satisfied vacuously."""
        specification_root = ROOT / "openspec"
        if not specification_root.is_dir():
            self.skipTest("this repository has no openspec/ directory")
        carrying = []
        for path in sorted(specification_root.rglob("*.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in CONTIGUOUS_CITATION.finditer(text):
                if match.group("segment") != ARCHIVE_SEGMENT:
                    carrying.append(path.relative_to(ROOT).as_posix())
                    break
            if carrying:
                break
        self.assertTrue(
            carrying,
            "no artifact under openspec/ carries a citation of a change's own "
            "directory, so excluding openspec/ from the walk demonstrates "
            "nothing about the exclusion",
        )


class CitationTreeFixtureMixin:
    """Builds throwaway trees the citation check is run over.

    Every citation is assembled at run time from CHANGE_PATH_PREFIX and a
    segment, so that no literal of the prohibited form is committed in this
    file (design Decision 6).
    """

    def citation(self, segment: str, tail: str = "") -> str:
        return CHANGE_PATH_PREFIX + segment + tail

    def wrapped_citation(self, segment: str, tail: str = "") -> str:
        """The same citation split across a line break immediately after the
        prefix, with a comment marker opening the continuation line."""
        return CHANGE_PATH_PREFIX + "\n# " + segment + tail

    def citation_tree(self, files: dict[str, str]) -> Path:
        root = Path(tempfile.mkdtemp(prefix="citation-fixture-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for relative, body in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        return root

    def offences_over(self, body: str, name: str = "notes.md") -> list[str]:
        return pre_archive_citations(self.citation_tree({name: body}))


class TestThePreArchiveCitationCheckIsARealReadOfTheTree(
    CitationTreeFixtureMixin, unittest.TestCase
):
    """ADDED requirement: Source Files Cite Specifications by Path and Changes
    by Name.

    The assertion over the committed tree passes identically whether the check
    reads the files or matches nothing at all, and it will keep passing once
    the tree is swept. These tests run the same check over throwaway trees
    differing in exactly one property, so its verdict is shown to depend on
    what a file says.
    """

    def test_a_citation_naming_an_artifact_inside_a_change_is_flagged(self) -> None:
        """SPECIFIED -- scenario "A pull request reintroducing the pre-archive
        citation form is rejected"."""
        offences = self.offences_over("# see " + self.citation("some-change", "/design.md"))
        self.assertEqual(1, len(offences), f"expected one offence, got {offences}")

    def test_a_citation_that_names_the_change_and_stops_is_flagged(self) -> None:
        """SPECIFIED -- "whether or not a further path component follows it".
        A prohibition written to require a trailing separator permits this
        form, and better than a third of the citations the requirement removes
        take it."""
        offences = self.offences_over("# see " + self.citation("some-change") + "\n")
        self.assertEqual(1, len(offences), f"expected one offence, got {offences}")

    def test_a_citation_of_a_delta_specification_inside_a_change_is_flagged(self) -> None:
        """SPECIFIED -- scenario "A requirement is cited at its permanent
        location": a requirement is named at `openspec/specs/<capability>/
        spec.md` "rather than the delta specification inside the change that
        proposed it"."""
        offences = self.offences_over(
            "# see " + self.citation("some-change", "/specs/iac-repo-foundations/spec.md")
        )
        self.assertEqual(1, len(offences), f"expected one offence, got {offences}")

    def test_a_wrapped_citation_naming_a_further_component_is_flagged(self) -> None:
        """SPECIFIED -- the requirement excludes exactly one wrapped rendering,
        the single-word change name, which entails that a wrapped hyphenated
        one is inside the check. No citation in the tree wraps in this
        position, so only a synthesised fixture can exercise it."""
        offences = self.offences_over(
            "# a note ending at " + self.wrapped_citation("some-change", "/design.md")
        )
        self.assertEqual(1, len(offences), f"expected one offence, got {offences}")

    def test_a_wrapped_citation_that_names_the_change_and_stops_is_flagged(self) -> None:
        """SPECIFIED -- the same exclusion, combined with "whether or not a
        further path component follows it"."""
        offences = self.offences_over(
            "# a note ending at " + self.wrapped_citation("some-change") + "\n"
        )
        self.assertEqual(1, len(offences), f"expected one offence, got {offences}")

    def test_an_offence_names_the_file_the_line_and_the_citation(self) -> None:
        """SPECIFIED -- scenario "A pull request reintroducing the pre-archive
        citation form is rejected": the check fails "naming the file, the line
        and the citation". A verdict that named none of the three would leave
        the author unable to act on it."""
        body = "first\nsecond\n# see " + self.citation("some-change", "/design.md") + "\n"
        offences = self.offences_over(body, name="ansible/roles/example/tasks/main.yml")
        self.assertEqual(1, len(offences), f"expected one offence, got {offences}")
        reported = offences[0]
        self.assertTrue(
            reported.startswith("ansible/roles/example/tasks/main.yml:3: "),
            f"the offence names neither the file nor the line it is on: {reported}",
        )
        self.assertIn(CHANGE_PATH_PREFIX + "some-change", reported)

    def test_the_archived_location_is_not_flagged(self) -> None:
        """SPECIFIED -- "A citation MAY additionally give a change's archived
        location as `openspec/changes/archive/<date>-<name>/...` once that
        location exists"."""
        offences = self.offences_over(
            "# see "
            + self.citation(ARCHIVE_SEGMENT, "/2026-08-18-project-foundation/design.md")
        )
        self.assertEqual([], offences, f"the archived location was flagged: {offences}")

    def test_a_metasyntactic_placeholder_is_not_flagged(self) -> None:
        """DERIVED -- design Decision 5, not a scenario. The rule has to be
        statable in AGENTS.md and in this suite's own prose; a check that
        flagged its own statement would be unshippable, and exempting those
        files by name would punch a hole that later drifts into a real
        violation."""
        offences = self.offences_over("# never write " + self.citation("<name>", "/design.md"))
        self.assertEqual([], offences, f"a placeholder was flagged: {offences}")

    def test_a_requirement_cited_at_its_permanent_location_is_not_flagged(self) -> None:
        """SPECIFIED -- scenario "A requirement is cited at its permanent
        location": the form the requirement obliges must itself pass, or the
        check would forbid the only permitted way to cite a requirement."""
        offences = self.offences_over(
            "# see openspec/specs/iac-repo-foundations/spec.md, requirement "
            "Source Files Cite Specifications by Path and Changes by Name"
        )
        self.assertEqual([], offences, f"the permitted form was flagged: {offences}")

    def test_prose_ending_in_the_prefix_before_an_ordinary_word_is_not_flagged(self) -> None:
        """SPECIFIED -- the requirement's own statement of what the wrapped
        match must not reach: "a continuation line's first word is itself a
        valid single-word change name". Documentation describing this rule
        wraps exactly here, and flagging it would redden the required check on
        the files that state the rule."""
        offences = self.offences_over(
            "# a path naming a change's own directory under " + CHANGE_PATH_PREFIX + "\n"
            "# is not permitted in a committed file\n"
        )
        self.assertEqual([], offences, f"prose describing the rule was flagged: {offences}")

    def test_a_wrapped_single_word_change_name_is_knowingly_not_flagged(self) -> None:
        """SPECIFIED -- and unusual: it asserts a gap the requirement records
        rather than a behaviour it wants. "One rendering lies outside it: a
        citation split across a line break immediately after
        the prefix whose change name is a single word with no hyphen."
        Pinning it means a later change that closes the gap does so knowingly,
        and sees that it must also keep the prose case above passing."""
        offences = self.offences_over(
            "# a note ending at " + self.wrapped_citation("foundation", "/design.md")
        )
        self.assertEqual(
            [],
            offences,
            "the wrapped single-word rendering was flagged; the requirement "
            f"records it as outside the check: {offences}",
        )

    def test_a_tree_carrying_no_such_citation_yields_no_offence(self) -> None:
        """DERIVED -- the converse half. Without it, a check that reported
        every file as an offender would satisfy every positive case above
        while failing every pull request regardless of what it changed."""
        offences = pre_archive_citations(
            self.citation_tree(
                {
                    "README.md": "# see openspec/specs/iac-repo-foundations/spec.md\n",
                    "ansible/roles/example/tasks/main.yml": (
                        "# rationale: see the change decide-archived-change-reference-"
                        "policy, design.md\n"
                    ),
                }
            )
        )
        self.assertEqual([], offences, f"a clean tree was reported as offending: {offences}")

    def test_a_tree_the_walk_finds_nothing_in_fails_rather_than_reading_nothing(self) -> None:
        """DERIVED -- the non-vacuity guard at the tree level, the same one
        this suite applies to Molecule scenario discovery. A check that read no
        file would report success having verified nothing."""
        root = Path(tempfile.mkdtemp(prefix="citation-fixture-empty-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        with self.assertRaises(AssertionError):
            pre_archive_citations(root)

    def test_the_pruned_directories_are_not_read(self) -> None:
        """DERIVED -- design Decision 7. Without pruning, the check descends
        into a second checkout of this repository sitting on another branch and
        reports every finding twice, and into `openspec/`, whose artifacts the
        requirement puts out of scope."""
        citation = "# see " + self.citation("some-change", "/design.md") + "\n"
        root = self.citation_tree(
            {
                CHANGE_PATH_PREFIX + "some-change/design.md": citation,
                ".claude/worktrees/other/README.md": citation,
                ".worktrees/other/README.md": citation,
                "terraform/environments/prod/.terraform/providers/notes.md": citation,
                "ansible/roles/geerlingguy.docker/README.md": citation,
                "node_modules/package/readme.md": citation,
                "README.md": "# see openspec/specs/iac-repo-foundations/spec.md\n",
            }
        )
        self.assertEqual(
            [],
            pre_archive_citations(root),
            "a pruned directory was read",
        )

    def test_compiled_bytecode_beneath_a_pycache_directory_is_not_read(self) -> None:
        """DERIVED -- design Decision 7, which prunes `__pycache__` wherever it
        occurs. The requirement is scoped to committed files and `.gitignore`
        ignores `__pycache__/`, so a compiled module is not one; and running
        this suite is what writes it, so a compiled copy of a citation swept
        out of the source would otherwise keep the check red after the sweep
        had already made it true. Written over a fixture rather than over this
        repository's own bytecode, which exists only after a run."""
        citation = "# see " + self.citation("some-change", "/design.md") + "\n"
        root = self.citation_tree(
            {
                ".github/tests/__pycache__/test_ci_configuration.cpython-312.pyc": citation,
                "ansible/roles/example/__pycache__/module.cpython-312.pyc": citation,
                "README.md": "# see openspec/specs/iac-repo-foundations/spec.md\n",
            }
        )
        self.assertEqual(
            [],
            pre_archive_citations(root),
            "compiled bytecode under __pycache__ was read, so every run of this "
            "suite would report a citation it had just compiled itself",
        )

    def test_a_file_outside_the_pruned_directories_is_still_read(self) -> None:
        """DERIVED -- the converse of the test above: a prune list that
        excluded the whole tree would satisfy it while checking nothing. Pairs
        with it over one fixture differing in exactly one file."""
        offences = pre_archive_citations(
            self.citation_tree(
                {
                    CHANGE_PATH_PREFIX + "some-change/design.md": (
                        "# see " + self.citation("some-change", "/design.md") + "\n"
                    ),
                    ".claude/skills/example/SKILL.md": (
                        "# see " + self.citation("some-change", "/design.md") + "\n"
                    ),
                }
            )
        )
        self.assertEqual(
            # The matched text is the prefix and the change-name segment; the
            # trailing path component is not part of the match, because nothing
            # may be required after the segment.
            [".claude/skills/example/SKILL.md:1: " + CHANGE_PATH_PREFIX + "some-change"],
            offences,
            "a tracked file under .claude/ was not read, or openspec/ was",
        )


class TestThePreArchiveCitationCheckGatesEveryPullRequest(unittest.TestCase):
    """ADDED requirement: Source Files Cite Specifications by Path and Changes
    by Name -- "This prohibition SHALL be asserted by the executable test suite
    that gates every pull request, because the author of such a citation cannot
    detect it"."""

    def test_the_citation_check_lives_in_the_suite_the_required_check_invokes(self) -> None:
        """SPECIFIED -- scenario "A pull request reintroducing the pre-archive
        citation form is rejected": the required status check fails on that
        pull request. The check discriminating correctly establishes nothing if
        nothing runs it."""
        module = sys.modules[pre_archive_citations.__module__]
        location = Path(module.__file__).resolve().as_posix()
        self.assertIn(
            SUITE_MARKER,
            location,
            f"the citation check is defined in {location}, outside the directory "
            f"the required status check runs",
        )
        workflow = load_yaml(PR_VALIDATION)
        invoking = [
            step_label(job, index, step)
            for job, index, step in steps(workflow)
            if SUITE_MARKER in str(step.get("run", ""))
        ]
        self.assertTrue(
            invoking,
            f"no step in pr-validation.yml runs the suite under {SUITE_MARKER}/",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Ansible Configuration Is Verified in Continuous
# Integration and Gates the Merge; Required Status Checks Report on Every Pull
# Request; Branch Protection on the Default Branch
#
# Derived from the delta specs of the OpenSpec change
# `promote-molecule-to-a-required-check`, before any implementation of that
# change existed. See that change's test-plan.md for the scenario-to-test
# mapping, the baseline, the assertion classifications, and the scenarios no
# test command in this repository can reach.
#
# NOTHING IN THIS SECTION ESTABLISHES THAT A STATUS CHECK CONTEXT IS
# REGISTERED. Registering a context is repository settings rather than
# repository content, and this suite makes no network call -- The
# Continuous-Integration Configuration Is Itself Verified requires that, and
# `TestTheSuiteNeedsNoPrivilegedResource` asserts it of this suite. Every
# assertion below is a static read of a committed workflow file, or an
# execution of a snippet taken out of one. Together they establish only that
# the workflow is *shaped* so a context can be registered on it safely: no
# workflow-level path filter, a literal job name to register, and a gate that
# discriminates. Whether the operator registered it, whether a direct push to
# `main` is rejected, and whether a red check blocks a merge are read from the
# branch-protection API and from the forge during this change's ship stage, and
# are not things a green run here has checked.
#
# The requirement name above does not appear in openspec/specs/ until this
# change is archived. That bounded interval is recorded deliberately in this
# change's design.md rather than being an oversight.
# --------------------------------------------------------------------------

# The status check contexts branch protection registers on `main`, each mapped
# to the workflow that produces it. A third required check is then added here
# as a name rather than as a test.
REQUIRED_STATUS_CHECK_WORKFLOWS = {
    "validate": PR_VALIDATION,
    "ansible-verify": ANSIBLE_VERIFY,
}

# The context this change adds, and the job whose literal `name:` produces it.
AGGREGATING_CONTEXT = "ansible-verify"


def job_context_name(job_key: str, job: dict) -> str:
    """The status check context a job produces: its `name:` where it declares
    one, otherwise its key."""
    name = job.get("name")
    return str(name) if name else job_key


def compact(value: object) -> str:
    """An Actions expression with its whitespace removed, so
    `${{ needs.discover.result }}` and `${{needs.discover.result}}` are matched
    by the same substring."""
    return re.sub(r"\s+", "", str(value))


def require_external_tools(case: unittest.TestCase, tools, purpose: str) -> None:
    """Precondition, not an assertion: refuse to read a subprocess's exit
    status as evidence about a workflow snippet when the snippet could not run
    at all.

    Same skip-vs-fail handling as
    `TestMoleculeDiscoveryAndScenarioCoverage._require_discovery_snippet_tools`,
    for the same reason: outside CI a missing tool is a fact about the machine
    and the test skips naming it, while under CI it fails instead, because a
    silently skipped check on a runner is a required status check reporting
    success having verified nothing.
    """
    missing = [tool for tool in tools if shutil.which(tool) is None]
    if not missing:
        return
    reason = (
        f"cannot {purpose}: it needs {', '.join(missing)}, absent on this machine, "
        "so an exit status from it would say nothing about the workflow"
    )
    if os.environ.get("CI"):
        case.fail(
            f"{reason}. Running under CI, where skipping this test would report "
            "success having verified nothing; install the tool on the runner."
        )
    case.skipTest(reason)


def github_output_pairs(path: Path) -> dict:
    """Parse a `$GITHUB_OUTPUT` file the way the runner does: `key=value`
    lines, plus the heredoc form a multi-line value uses."""
    pairs: dict = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        heredoc = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)<<(\S+)\s*$", line)
        if heredoc:
            key, delimiter = heredoc.groups()
            body = []
            index += 1
            while index < len(lines) and lines[index].strip() != delimiter:
                body.append(lines[index])
                index += 1
            pairs[key] = "\n".join(body)
        elif "=" in line:
            key, _, value = line.partition("=")
            pairs[key.strip()] = value
        index += 1
    return pairs


class MoleculeWorkflowShapeMixin:
    """Locators shared by the classes below.

    Each asserts rather than returning nothing, so a workflow that has not been
    reshaped yet fails these tests for the reason the specification names
    rather than erroring on a `None`.
    """

    def _workflow(self) -> dict:
        return load_yaml(ANSIBLE_VERIFY)

    def _job_named(self, workflow: dict, context: str):
        matches = [
            (key, job)
            for key, job in jobs(workflow).items()
            if job_context_name(key, job) == context
        ]
        self.assertEqual(
            1,
            len(matches),
            f"ansible-verify.yml declares {len(matches)} jobs whose status check "
            f"context is `{context}`; branch protection registers exactly one, and "
            "the contexts this workflow declares are "
            f"{sorted(job_context_name(k, j) for k, j in jobs(workflow).items())}",
        )
        return matches[0]

    def _discovery_job(self, workflow: dict):
        """The job that feeds the matrix, read from the matrix's own expression.

        Identified structurally rather than by what its shell says. Selecting
        on `ansible/roles` matched the matrix job too, which installs Galaxy
        content into that directory; narrowing to `find ansible/roles` fixed
        that but coupled six tests to one spelling of a path, so quoting it --
        an ordinary refactor changing no behaviour -- would break them all.

        What actually makes a job the discovery job is that the matrix is built
        from its output. That is what is read here, and it survives any rewrite
        of the discovery shell.
        """
        matrix_key, matrix_job = self._matrix_job(workflow)
        expression = compact((matrix_job.get("strategy") or {}).get("matrix"))
        referenced = sorted(set(re.findall(r"needs\.([A-Za-z0-9_-]+)\.outputs\.", expression)))
        self.assertEqual(
            1,
            len(referenced),
            f"the matrix job `{matrix_key}` builds its matrix from "
            f"{len(referenced)} job outputs, {referenced}; exactly one job supplies "
            "the roles to run, and it is that job these checks call the discovery "
            f"job. The matrix expression is {(matrix_job.get('strategy') or {}).get('matrix')!r}",
        )
        discovery_key = referenced[0]
        declared = jobs(workflow)
        self.assertIn(
            discovery_key,
            declared,
            f"the matrix job `{matrix_key}` reads an output of `{discovery_key}`, "
            f"which this workflow does not declare; its jobs are {sorted(declared)}",
        )
        return discovery_key, declared[discovery_key]

    def _matrix_job(self, workflow: dict):
        """The job whose name is generated from a matrix -- the one that must
        never be the registered context."""
        matches = [
            (key, job)
            for key, job in jobs(workflow).items()
            if (job.get("strategy") or {}).get("matrix")
        ]
        self.assertTrue(
            matches, "no job in ansible-verify.yml declares a `strategy.matrix`"
        )
        return matches[0]


class TestEveryRequiredCheckIsShapedToBeRegistrable(
    MoleculeWorkflowShapeMixin, unittest.TestCase
):
    """MODIFIED requirements: Required Status Checks Report on Every Pull
    Request; Branch Protection on the Default Branch.

    Establishes the workflow-file half of both, and nothing else. It does NOT
    establish that either context is registered in `main`'s branch protection,
    that a direct push to `main` is rejected, or that a pull request with a
    failing check is blocked from merging: those are repository settings and
    merge outcomes, which this suite makes no network call to read. A green run
    here means the workflows are shaped so those settings can be applied
    safely, never that they were applied.
    """

    def test_no_required_check_workflow_declares_a_workflow_level_path_filter(self) -> None:
        """SPECIFIED -- "That work MAY be path-filtered, but the filtering SHALL
        occur *inside* an always-running job rather than via a workflow-level
        `paths` or `paths-ignore` filter", and scenario "Documentation-only pull
        request remains mergeable" in its workflow-file half. Both keys are
        checked because the requirement forbids the mechanism rather than one
        spelling of it, and every workflow behind a registered context is
        checked because the requirement is now over each of them.

        Says nothing about whether such a pull request is in fact mergeable:
        that is a merge outcome, observed on the forge rather than here.
        """
        for context, path in sorted(REQUIRED_STATUS_CHECK_WORKFLOWS.items()):
            on = triggers(load_yaml(path))
            self.assertTrue(
                on,
                f"{path.name} declares no triggers at all, so this check over the "
                f"context `{context}` would pass having read nothing",
            )
            for event, config in on.items():
                if not isinstance(config, dict):
                    continue
                for key in ("paths", "paths-ignore"):
                    self.assertNotIn(
                        key,
                        config,
                        f"{path.name}'s `{event}` trigger declares `{key}:`, which "
                        "leaves every non-matching pull request permanently pending "
                        f"on the required context `{context}` and so unmergeable",
                    )

    def test_every_required_context_names_a_job_whose_name_is_a_literal(self) -> None:
        """SPECIFIED -- scenario "Every registered context names a literal job":
        "the job that context names SHALL carry a literal `name:`, containing no
        GitHub Actions expression".

        Establishes the workflow-file half only: that each named workflow
        declares a job producing that context, by a literal. It does NOT
        establish that the context is registered on `main` -- that half is read
        from the protection API, not from this repository.
        """
        for context, path in sorted(REQUIRED_STATUS_CHECK_WORKFLOWS.items()):
            workflow = load_yaml(path)
            declared = {
                job_context_name(key, job): job for key, job in jobs(workflow).items()
            }
            self.assertIn(
                context,
                sorted(declared),
                f"{path.name} declares no job whose status check context is "
                f"`{context}`, so registering that context would register a check "
                f"that never reports; the workflow declares {sorted(declared)}",
            )
            self.assertNotIn(
                "${{",
                str(declared[context].get("name", context)),
                f"{path.name}'s `{context}` job carries an Actions expression in its "
                "`name:`, so the context it produces is generated rather than literal "
                "and cannot be enumerated in branch protection in advance",
            )

    def test_the_generated_matrix_context_is_not_the_one_registered(self) -> None:
        """SPECIFIED -- "Where a required check's work is performed by a job
        whose name is generated rather than literal -- a matrix job, whose
        context names vary with the matrix -- that job SHALL NOT be the
        registered context".

        Establishes that the matrix job's context differs from the registered
        name. It does NOT establish which contexts branch protection holds.
        """
        workflow = self._workflow()
        matrix_key, matrix_job = self._matrix_job(workflow)
        self.assertNotEqual(
            AGGREGATING_CONTEXT,
            job_context_name(matrix_key, matrix_job),
            "the matrix job itself produces the context this change registers, so a "
            "role added under ansible/roles/ would change which contexts report",
        )
        self.assertIn(
            "${{",
            str(matrix_job.get("name", matrix_key)),
            "the matrix job's name is a literal, which means either it no longer "
            "varies with the matrix or the matrix has moved to another job; re-read "
            "which job produces which context before relying on the assertions about "
            "the aggregating job below",
        )


class TestTheMoleculeWorkflowRunsOnPullRequestsAndOnDispatch(unittest.TestCase):
    """ADDED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge."""

    def test_the_workflow_triggers_on_pull_requests_and_on_a_manual_dispatch(self) -> None:
        """SPECIFIED for the `pull_request` limb -- "Every pull request that
        changes files under `ansible/` SHALL trigger continuous-integration
        checks over that configuration".

        DERIVED for the `workflow_dispatch` limb: scenario "A manual run
        verifies the whole suite" states what SHALL happen when the workflow is
        started other than by a pull request, which presupposes such a trigger
        without requiring this spelling of it. Reconsider that limb, do not
        weaken it, if the manual path is provided by another event.
        """
        on = triggers(load_yaml(ANSIBLE_VERIFY))
        self.assertIn(
            "pull_request",
            on,
            "ansible-verify.yml no longer runs on pull requests, so the required "
            f"context `{AGGREGATING_CONTEXT}` would never report on one",
        )
        self.assertIn(
            "workflow_dispatch",
            on,
            "ansible-verify.yml declares no manual trigger, so the suite cannot be "
            "run against the trunk, which is the run the scenario \"A manual run "
            'verifies the whole suite" is about',
        )


class TestTheAggregatingJobConcludesOnTheSuitesBehalf(
    MoleculeWorkflowShapeMixin, unittest.TestCase
):
    """MODIFIED requirement: Required Status Checks Report on Every Pull
    Request.

    Establishes the structure that lets a literal-named job report for a
    generated-name matrix. It does NOT establish that this job is registered as
    a required status check: that is repository settings, unreadable here.
    """

    def test_the_aggregating_job_depends_on_discovery_and_on_the_matrix(self) -> None:
        """SPECIFIED -- "A job whose name is a literal SHALL depend on it, run
        regardless of its outcome, and conclude on its behalf", and "An
        aggregating job SHALL treat its own change-detection input as
        trustworthy only where the job producing it concluded successfully",
        which it cannot read at all without depending on that job."""
        workflow = self._workflow()
        _, aggregating = self._job_named(workflow, AGGREGATING_CONTEXT)
        discovery_key, _ = self._discovery_job(workflow)
        matrix_key, _ = self._matrix_job(workflow)
        declared = aggregating.get("needs") or []
        declared = [declared] if isinstance(declared, str) else list(declared)
        for required in (discovery_key, matrix_key):
            self.assertIn(
                required,
                declared,
                f"the `{AGGREGATING_CONTEXT}` job does not depend on `{required}`, so "
                "it can neither read that job's result nor conclude on its behalf; it "
                f"depends on {declared}",
            )

    def test_the_aggregating_job_runs_whatever_its_dependencies_concluded(self) -> None:
        """SPECIFIED -- "run regardless of its outcome". A job left with the
        default `success()` condition is itself skipped when a dependency fails
        or is skipped, and a skipped job produces no context at all -- the same
        permanent pending this requirement exists to prevent, reintroduced one
        layer down."""
        workflow = self._workflow()
        _, aggregating = self._job_named(workflow, AGGREGATING_CONTEXT)
        self.assertIn(
            "always()",
            compact(aggregating.get("if", "")),
            f"the `{AGGREGATING_CONTEXT}` job's condition is "
            f"{aggregating.get('if')!r}; without `always()` it is skipped whenever a "
            "dependency fails or is skipped, and then produces no context for branch "
            "protection to read",
        )


class TestOnlyTheMoleculeMatrixIsGated(MoleculeWorkflowShapeMixin, unittest.TestCase):
    """ADDED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge."""

    def test_the_matrix_job_is_conditioned_on_the_change_detection_output(self) -> None:
        """SPECIFIED -- scenario "A pull request touching no Ansible file starts
        no container": "the Molecule matrix SHALL be skipped rather than
        executed". The condition reads an output of the discovery job because
        that is where the requirement puts change detection -- "triggered by
        change detection *inside* an always-running workflow rather than by a
        workflow-level path filter"."""
        workflow = self._workflow()
        discovery_key, _ = self._discovery_job(workflow)
        matrix_key, matrix_job = self._matrix_job(workflow)
        condition = compact(matrix_job.get("if", ""))
        self.assertTrue(
            condition,
            f"the matrix job `{matrix_key}` carries no `if:`, so every pull request "
            "starts the containers the suite runs in, including one that touches "
            "nothing under ansible/",
        )
        self.assertIn(
            f"needs.{discovery_key}.outputs.",
            condition,
            f"the matrix job's condition {matrix_job.get('if')!r} reads no output of "
            f"the discovery job `{discovery_key}`, so whatever it is gated on is not "
            "the change detection this requirement places inside that job",
        )
        # The polarity, not merely the reference. Reading an output of the
        # discovery job is satisfied equally by the inverse condition, which
        # runs the whole container matrix on every pull request that touches
        # nothing under ansible/ -- the outcome this scenario forbids -- while
        # skipping it on the ones that do.
        self.assertIn(
            "=='true'",
            condition,
            f"the matrix job's condition {matrix_job.get('if')!r} does not run the "
            "suite WHERE the change detection says to. Inverted, a documentation-only "
            "pull request starts every container and an Ansible one starts none",
        )
        # Scoped to the operand, for the reason given on the change-filter
        # step's own negation check.
        for negation in ("!='true'", "!("):
            self.assertNotIn(
                negation,
                condition,
                f"the matrix job's condition {matrix_job.get('if')!r} negates the "
                "change detection -- see above",
            )

    def test_no_step_inside_the_matrix_job_carries_its_own_condition(self) -> None:
        """SPECIFIED -- the same scenario, in the half a job-level assertion
        alone would miss. A step-level condition leaves the job itself running:
        it concludes success having executed nothing, and the aggregating job
        then reads that as a genuine success rather than as a skip."""
        workflow = self._workflow()
        matrix_key, matrix_job = self._matrix_job(workflow)
        offenders = [
            step_label(matrix_key, index, step)
            for index, step in enumerate(matrix_job.get("steps") or [])
            if step.get("if") is not None
        ]
        self.assertEqual(
            [],
            offenders,
            "these steps inside the matrix job carry their own condition, which "
            "leaves the job green having run nothing rather than skipping it: "
            f"{offenders}",
        )

    def test_role_discovery_runs_whatever_a_pull_request_touched(self) -> None:
        """SPECIFIED -- scenario "Role discovery runs even where the suite does
        not": "role discovery SHALL still run, and where it finds no role its
        failure SHALL fail the required status check". Checks the discovery step
        and its job, because moving the condition to the job would leave a
        step-level assertion green while reopening the hole."""
        workflow = self._workflow()
        discovery_key, discovery_job = self._discovery_job(workflow)
        self.assertIsNone(
            discovery_job.get("if"),
            f"the discovery job `{discovery_key}` is conditioned on "
            f"{discovery_job.get('if')!r}, so a repository state in which no role "
            "carries a molecule/ directory would stop only the pull requests that "
            "touch ansible/ -- the suite that gates every merge having silently "
            "disappeared is not a fact only those pull requests should learn",
        )
        offenders = [
            step_label(discovery_key, index, step)
            for index, step in enumerate(discovery_job.get("steps") or [])
            if step.get("if") is not None
            and re.search(r"ansible/roles", str(step.get("run", "")))
        ]
        self.assertEqual(
            [],
            offenders,
            f"these role-discovery steps carry an `if:`: {offenders}",
        )


class TestDiscoveryDeclaresTheLeastPrivilegeItNeeds(
    MoleculeWorkflowShapeMixin, unittest.TestCase
):
    """ADDED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge -- "Discovery SHALL declare the least
    privilege its change detection needs, per the *Least-Privilege Workflow
    Permissions* requirement, and SHALL receive no write scope"."""

    WRITE_SCOPES = {"write", "write-all"}

    def test_the_discovery_job_declares_the_read_scopes_its_change_detection_uses(self) -> None:
        """SPECIFIED -- the sentence above. `pull-requests: read` is what
        reading which files a pull request touched needs; `contents: read` is
        asserted beside it because a job-level `permissions:` block replaces the
        workflow-level one rather than adding to it, so a block naming only the
        new scope silently strips the job's own checkout."""
        workflow = self._workflow()
        discovery_key, discovery_job = self._discovery_job(workflow)
        declared = discovery_job.get("permissions")
        self.assertIsInstance(
            declared,
            dict,
            f"the discovery job `{discovery_key}` declares no job-level "
            "`permissions:` block, so it inherits the workflow's `contents: read` "
            "alone and its change detection has no scope to read a pull request with",
        )
        for scope in ("contents", "pull-requests"):
            self.assertEqual(
                "read",
                str(declared.get(scope)),
                "the discovery job's `permissions:` block declares "
                f"`{scope}: {declared.get(scope)!r}`; a job-level block replaces the "
                "workflow-level one, so both scopes are named here or the job loses "
                "one of them, and neither may exceed read",
            )

    def test_no_job_in_the_molecule_workflow_receives_a_write_scope(self) -> None:
        """SPECIFIED -- "SHALL receive no write scope: reading which files a
        pull request touched is a read"."""
        workflow = self._workflow()
        # Refuse to read this workflow's job blocks as evidence when the block
        # they inherit from is absent. Widening the workflow-level block is
        # caught by the loop below; DELETING it is not -- every job would then
        # contribute no offenders while receiving the repository's default
        # token scope. That default is "SHALL be set to read-only" per
        # Least-Privilege Workflow Permissions, but it is a repository setting,
        # and this suite makes no network call to read one. Passing here would
        # be resting on an assumption about settings, which is the one thing
        # this workflow is otherwise careful never to do.
        self.assertIsInstance(
            workflow.get("permissions"),
            dict,
            "ansible-verify.yml declares no workflow-level `permissions:` block, so "
            "every job with no block of its own receives the repository's default "
            "token scope -- a repository setting this suite cannot read, and so a "
            "scope this check would be passing without having read",
        )
        offenders = []
        for key, job in jobs(workflow).items():
            # What a job RECEIVES, which is what the requirement is about --
            # not what it declares. A job-level block replaces the
            # workflow-level one; a job with no block of its own inherits it
            # whole, so reading `job.get("permissions")` alone would leave two
            # of this workflow's three jobs unchecked and a workflow-level
            # `contents: write` invisible to every test in this file.
            declared = job.get("permissions", workflow.get("permissions"))
            if isinstance(declared, str):
                if declared != "read-all":
                    offenders.append(f"{key}: {declared}")
                continue
            for scope, level in (declared or {}).items():
                if str(level) in self.WRITE_SCOPES:
                    offenders.append(f"{key}: {scope}: {level}")
        self.assertEqual(
            [],
            offenders,
            f"these jobs in ansible-verify.yml receive a write scope: {offenders}",
        )


class GateRow:
    """One row of the aggregating gate's decision table.

    A row names one or more matrix results, exactly as the table's own cells do
    -- `failure / cancelled` is a single cell there -- because the delta states
    those two as separate scenarios and a gate can discriminate one while
    conflating the other.
    """

    def __init__(self, label, discovery, changed, matrix_results, concludes_success):
        self.label = label
        self.discovery = discovery
        self.changed = changed
        self.matrix_results = matrix_results
        self.concludes_success = concludes_success


# design.md Decision 4's table, in its own order: seven rows, four refusals and
# three passes. The refusals are what the gate is for; the passes are what
# stops a gate that refuses everything from satisfying them.
GATE_TABLE = (
    GateRow(
        "discovery did not conclude, so its outputs are empty strings",
        discovery="failure",
        changed="",
        matrix_results=("skipped",),
        concludes_success=False,
    ),
    GateRow(
        "the suite ran and passed on a pull request that changed ansible/",
        discovery="success",
        changed="true",
        matrix_results=("success",),
        concludes_success=True,
    ),
    GateRow(
        "the suite was skipped on a pull request that changed ansible/",
        discovery="success",
        changed="true",
        matrix_results=("skipped",),
        concludes_success=False,
    ),
    GateRow(
        "the suite failed or was cancelled on a pull request that changed ansible/",
        discovery="success",
        changed="true",
        matrix_results=("failure", "cancelled"),
        concludes_success=False,
    ),
    GateRow(
        "nothing under ansible/ changed and the suite was skipped",
        discovery="success",
        changed="false",
        matrix_results=("skipped",),
        concludes_success=True,
    ),
    GateRow(
        "nothing under ansible/ changed and the suite ran anyway",
        discovery="success",
        changed="false",
        matrix_results=("success",),
        concludes_success=True,
    ),
    GateRow(
        "the suite failed or was cancelled although nothing under ansible/ changed",
        discovery="success",
        changed="false",
        matrix_results=("failure", "cancelled"),
        concludes_success=False,
    ),
)

# The row the gate is most likely to get wrong, selected by the inputs that
# DEFINE it rather than by its position, so that reordering the table above
# cannot silently retarget the message assertion onto another row. An index
# would have said the same thing in a comment while not doing it: retargeted
# onto the `changed="false"` skip, the message assertion below passes on that
# row's SUCCESS message, which also contains the word "skip".
SKIPPED_YET_CHANGED = next(
    row
    for row in GATE_TABLE
    if row.discovery == "success"
    and row.changed == "true"
    and row.matrix_results == ("skipped",)
)


class TestTheAggregatingGateDiscriminates(
    MoleculeWorkflowShapeMixin, unittest.TestCase
):
    """MODIFIED requirement: Required Status Checks Report on Every Pull
    Request; ADDED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge.

    Runs the gate rather than reading it. Its `run:` body is free of `${{ }}`
    and takes its three inputs through the step's `env:` block, so it can be
    pulled out of the workflow and executed under `bash` once per row of the
    table above -- the same extract-and-run shape
    `TestMoleculeDiscoveryAndScenarioCoverage.test_role_discovery_fails_when_it_finds_nothing`
    uses for role discovery. Grepping would establish that a gate exists; only
    running it establishes that it discriminates.

    What a green run here does NOT establish: that this gate's conclusion
    blocks anything. Blocking is branch protection -- repository settings this
    suite makes no network call to read.
    """

    def _gate_step(self):
        """The aggregating job's gate step, with its three inputs identified by
        the expressions its `env:` block assigns rather than by whatever names
        the implementation chose for them."""
        workflow = self._workflow()
        discovery_key, _ = self._discovery_job(workflow)
        matrix_key, _ = self._matrix_job(workflow)
        job_key, aggregating = self._job_named(workflow, AGGREGATING_CONTEXT)

        candidates = []
        for index, step in enumerate(aggregating.get("steps") or []):
            if not step.get("run"):
                continue
            inputs = {}
            for name, value in (step.get("env") or {}).items():
                expression = compact(value)
                if f"needs.{discovery_key}.result" in expression:
                    inputs["discovery"] = name
                elif f"needs.{matrix_key}.result" in expression:
                    inputs["matrix"] = name
                elif f"needs.{discovery_key}.outputs." in expression:
                    inputs["changed"] = name
            if set(inputs) == {"discovery", "matrix", "changed"}:
                candidates.append((index, step, inputs))

        self.assertEqual(
            1,
            len(candidates),
            f"expected exactly one `run:` step in the `{AGGREGATING_CONTEXT}` job "
            "whose `env:` block carries all three of the discovery job's result, the "
            "matrix job's result and the discovery job's change-detection output, but "
            f"found {len(candidates)}. The gate takes its inputs through `env:` so "
            "that its body stays free of Actions expressions and can be executed "
            "standalone; a gate written as an `if:` expression, or reading those "
            "expressions inline, cannot be exercised by this suite at all. The job's "
            "steps declare: "
            + repr(
                [
                    (step.get("name"), sorted(step.get("env") or {}))
                    for step in (aggregating.get("steps") or [])
                ]
            ),
        )
        index, step, inputs = candidates[0]
        return job_key, index, step, inputs

    def _run_gate(self, script: str, inputs: dict, row: GateRow, matrix_result: str):
        scratch = Path(tempfile.mkdtemp(prefix="ansible-verify-gate-"))
        try:
            outputs = scratch / "github_output"
            summary = scratch / "step_summary"
            outputs.touch()
            summary.touch()
            env = dict(
                os.environ,
                GITHUB_OUTPUT=str(outputs),
                GITHUB_ENV=str(outputs),
                GITHUB_STEP_SUMMARY=str(summary),
            )
            env[inputs["discovery"]] = row.discovery
            env[inputs["changed"]] = row.changed
            env[inputs["matrix"]] = matrix_result
            return subprocess.run(
                ["bash", "-e", "-c", script],
                cwd=scratch,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_the_gate_script_can_be_executed_standalone(self) -> None:
        """DERIVED (design.md Decision 5, tasks.md 3.2) -- no scenario states
        this shape. The scenarios state what the gate SHALL conclude; that its
        body is free of `${{ }}` and takes its inputs through `env:` is how this
        repository makes such a gate testable at all, decided in design.md
        rather than required by the specification. Reconsider this assertion, do
        not weaken it, if the gate is made executable by another means."""
        job_key, index, step, _ = self._gate_step()
        self.assertNotIn(
            "${{",
            str(step["run"]),
            f"the gate {step_label(job_key, index, step)} embeds a GitHub Actions "
            "expression in its body, so it cannot be run against the table of "
            "conclusions it is responsible for and only its existence could be "
            "checked",
        )

    def test_the_gate_concludes_as_the_table_says_on_every_row(self) -> None:
        """SPECIFIED -- one row per stated conclusion:

        - "A required check whose change detection did not conclude does not
          report success" (row 1: discovery `failure`, whose outputs are then
          empty strings -- an empty "nothing changed" is indistinguishable from
          a genuine one, and this is the row a gate that checks the change
          detection first would pass);
        - "A required check whose work was skipped does not report success"
          (row 3, the vacuous green);
        - "A cancelled dependency does not report success" and "A failed
          dependency reports failure whatever the change detection said"
          (rows 4 and 7, each run for both results);
        - "A required check reports without doing work it was not asked to do"
          and "Documentation-only pull request remains mergeable" in their
          reporting half (rows 5 and 6: the check concludes rather than pending
          when the work was skipped for want of a relevant change);
        - "A failing Molecule scenario blocks the merge" in its aggregating-job
          half (row 4): "the aggregating job SHALL conclude failure". Whether
          the merge is then blocked is branch protection, and is not established
          here.

        Rows 2, 5 and 6 are the converse the refusals need: a gate that failed
        every row would satisfy the four refusals while blocking every pull
        request in the repository.
        """
        _, _, step, inputs = self._gate_step()
        script = str(step["run"])
        require_external_tools(self, ("bash",), "execute ansible-verify.yml's gate")
        for row in GATE_TABLE:
            for matrix_result in row.matrix_results:
                with self.subTest(row=row.label, matrix=matrix_result):
                    result = self._run_gate(script, inputs, row, matrix_result)
                    detail = (result.stdout + result.stderr).strip()[-800:]
                    if row.concludes_success:
                        self.assertEqual(
                            0,
                            result.returncode,
                            f"the gate refused the row `{row.label}` (discovery="
                            f"{row.discovery!r}, changed={row.changed!r}, matrix="
                            f"{matrix_result!r}), which the specification requires it "
                            f"to pass: {detail!r}",
                        )
                    else:
                        self.assertNotEqual(
                            0,
                            result.returncode,
                            f"the gate concluded success on the row `{row.label}` "
                            f"(discovery={row.discovery!r}, changed={row.changed!r}, "
                            f"matrix={matrix_result!r}), reporting a green required "
                            f"status check for a suite that verified nothing: "
                            f"{detail!r}",
                        )

    def test_the_gate_names_the_skip_when_it_refuses_the_vacuous_green(self) -> None:
        """DERIVED (tasks.md 3.2) -- the specification requires the conclusion,
        not a message. A distinct message is what makes this refusal
        diagnosable rather than a bare non-zero exit, and this is the row a
        reader is least likely to expect. Reconsider this assertion, do not
        weaken it, if the implementation reports the case another way."""
        _, _, step, inputs = self._gate_step()
        script = str(step["run"])
        require_external_tools(self, ("bash",), "execute ansible-verify.yml's gate")
        result = self._run_gate(script, inputs, SKIPPED_YET_CHANGED, "skipped")
        combined = (result.stdout + result.stderr).lower()
        # Anchor the message to the refusal. Without this the test reads a
        # message and never checks what the gate concluded, so it would pass on
        # a gate that named the skip and then exited 0 -- reporting the vacuous
        # green in prose while producing it.
        self.assertNotEqual(
            0,
            result.returncode,
            "the gate concluded success on the skipped-yet-changed row, so this "
            "message assertion would be describing a green required status check "
            f"for a suite that verified nothing: {combined.strip()!r}",
        )
        self.assertIn(
            "skip",
            combined,
            "the gate refused the skipped-yet-changed row without naming the skip as "
            f"the reason; it emitted {combined.strip()!r}",
        )


class TestChangeDetectionResolvesTheGatesInput(
    MoleculeWorkflowShapeMixin, unittest.TestCase
):
    """ADDED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge.

    A second extracted script, and not a row of the gate's table. The gate
    takes "Ansible changed" as given and decides what to conclude from it; this
    step decides what that input *is*, from the event name. The polarity lives
    here, and is invisible to a test that feeds the gate its input directly.
    """

    def _resolution_step(self):
        """The discovery job's change-detection resolution step, identified by
        the `github.event_name` its `env:` block passes in."""
        workflow = self._workflow()
        discovery_key, discovery_job = self._discovery_job(workflow)
        candidates = []
        for index, step in enumerate(discovery_job.get("steps") or []):
            if not step.get("run"):
                continue
            inputs = {}
            for name, value in (step.get("env") or {}).items():
                expression = compact(value)
                if "github.event_name" in expression:
                    inputs["event"] = name
                elif re.search(r"steps\.[A-Za-z0-9_-]+\.outputs\.", expression):
                    inputs["filter"] = name
            if "event" in inputs:
                candidates.append((index, step, inputs))
        self.assertEqual(
            1,
            len(candidates),
            "expected exactly one `run:` step in the discovery job "
            f"`{discovery_key}` taking `github.event_name` through its `env:` block "
            "-- the step that resolves whether the suite runs -- but found "
            f"{len(candidates)}. Without it the workflow either performs no such "
            "resolution, or expresses it as an Actions expression this suite cannot "
            "execute, leaving the manual-run polarity asserted nowhere.",
        )
        index, step, inputs = candidates[0]
        self.assertIn(
            "filter",
            inputs,
            "the resolution step takes the event name but no output of an earlier "
            "step, so on a pull request it cannot be taking the change filter's "
            f"result; its `env:` block declares {sorted(step.get('env') or {})}",
        )
        return discovery_key, discovery_job, index, step, inputs

    def _resolved_output_name(self, discovery_job: dict, step: dict) -> str:
        """The output key this step writes, read from the job's own `outputs:`
        block so that the test does not have to guess the name."""
        step_id = step.get("id")
        self.assertTrue(
            step_id,
            "the resolution step declares no `id:`, so the job cannot expose its "
            "result as an output and the matrix job has nothing to be gated on",
        )
        for expression in (discovery_job.get("outputs") or {}).values():
            match = re.search(
                r"steps\." + re.escape(str(step_id)) + r"\.outputs\.([A-Za-z0-9_-]+)",
                compact(expression),
            )
            if match:
                return match.group(1)
        self.fail(
            "no entry in the discovery job's `outputs:` block reads "
            f"`steps.{step_id}.outputs.*`, so whatever this step resolves never "
            "leaves the job, and neither the matrix job nor the gate can read it; "
            f"the job declares the outputs {sorted(discovery_job.get('outputs') or {})}"
        )

    def _resolve(self, script: str, inputs: dict, output_name: str, event: str, filtered: str):
        scratch = Path(tempfile.mkdtemp(prefix="ansible-verify-resolution-"))
        try:
            outputs = scratch / "github_output"
            summary = scratch / "step_summary"
            outputs.touch()
            summary.touch()
            env = dict(
                os.environ,
                GITHUB_OUTPUT=str(outputs),
                GITHUB_ENV=str(outputs),
                GITHUB_STEP_SUMMARY=str(summary),
            )
            env[inputs["event"]] = event
            env[inputs["filter"]] = filtered
            result = subprocess.run(
                ["bash", "-e", "-c", script],
                cwd=scratch,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(
                0,
                result.returncode,
                f"the resolution step exited {result.returncode} on a {event!r} run "
                f"whose change filter reported {filtered!r}: "
                f"{(result.stdout + result.stderr).strip()[-800:]!r}",
            )
            written = github_output_pairs(outputs)
            self.assertIn(
                output_name,
                written,
                f"the resolution step wrote no `{output_name}` to $GITHUB_OUTPUT on a "
                f"{event!r} run; it wrote {written!r}",
            )
            return written[output_name].strip()
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_a_run_that_is_not_a_pull_request_resolves_to_the_whole_suite(self) -> None:
        """SPECIFIED -- scenario "A manual run verifies the whole suite": "the
        suite SHALL run in full rather than being skipped for want of a diff to
        inspect, and the workflow SHALL NOT conclude success having skipped it",
        and "Where the workflow is started by any other event there is no diff
        to resolve against, and the suite SHALL run in full rather than
        defaulting to skipped".

        The `false` case on a dispatch is the polarity itself: the resolution
        has to branch on the event, not on whatever value an unrun filter left
        behind.
        """
        _, discovery_job, _, step, inputs = self._resolution_step()
        output_name = self._resolved_output_name(discovery_job, step)
        script = str(step["run"])
        require_external_tools(
            self, ("bash",), "execute ansible-verify.yml's change-detection resolution"
        )
        for event, filtered in (
            ("workflow_dispatch", ""),
            ("workflow_dispatch", "false"),
            ("push", ""),
            ("schedule", ""),
        ):
            with self.subTest(event=event, filter_output=filtered):
                self.assertEqual(
                    "true",
                    self._resolve(script, inputs, output_name, event, filtered),
                    f"on a `{event}` run the resolution produced something other than "
                    "`true`, so the matrix is skipped and the workflow reports a green "
                    "conclusion on precisely the trigger this repository uses to run "
                    "the suite against the trunk",
                )

    def test_a_pull_request_resolves_to_what_the_change_filter_found(self) -> None:
        """SPECIFIED -- "Change detection resolves against a pull request's
        diff", in the two conclusions the delta's scenarios state: a pull
        request changing files under `ansible/` runs the suite (scenario "A
        failing Molecule scenario blocks the merge" presupposes it ran), and one
        changing none of them does not (scenario "A pull request touching no
        Ansible file starts no container")."""
        _, discovery_job, _, step, inputs = self._resolution_step()
        output_name = self._resolved_output_name(discovery_job, step)
        script = str(step["run"])
        require_external_tools(
            self, ("bash",), "execute ansible-verify.yml's change-detection resolution"
        )
        for filtered, expected in (("true", "true"), ("false", "false")):
            with self.subTest(filter_output=filtered):
                self.assertEqual(
                    expected,
                    self._resolve(script, inputs, output_name, "pull_request", filtered),
                    f"on a pull request whose change filter reported {filtered!r} the "
                    f"resolution produced something other than {expected!r}, so the "
                    "matrix is gated on something other than the diff",
                )

    def test_a_pull_request_whose_change_filter_did_not_run_is_refused(self) -> None:
        """SPECIFIED -- "An aggregating job SHALL treat its own change-detection
        input as trustworthy only where the job producing it concluded
        successfully. Where that job did not, its outputs are empty, and an
        empty 'nothing changed' is indistinguishable from a genuine one." The
        requirement states it of the aggregating job; the same emptiness
        reaches the same conclusion one step earlier, and is refused here too.

        This is the failure mode that makes the change-filter step's condition
        load-bearing beyond its polarity. A skipped filter leaves the empty
        string, and reading that as `false` skips the matrix and concludes
        SUCCESS on a pull request nothing verified. NARROWING that condition
        produces it just as surely as inverting it does -- a plausible-looking
        `&& github.actor != 'dependabot[bot]'` would silently green every
        Dependabot pull request. Refusing the value here makes every such
        narrowing loud, which no assertion about the condition's spelling can
        do without also rejecting conditions that are fine.
        """
        _, discovery_job, _, step, inputs = self._resolution_step()
        self._resolved_output_name(discovery_job, step)
        script = str(step["run"])
        require_external_tools(
            self, ("bash",), "execute ansible-verify.yml's change-detection resolution"
        )
        for filtered in ("", "skipped", "TRUE"):
            with self.subTest(filter_output=filtered):
                result = subprocess.run(
                    ["bash", "-e", "-c", script],
                    cwd=tempfile.gettempdir(),
                    env=dict(
                        os.environ,
                        GITHUB_OUTPUT=os.devnull,
                        GITHUB_ENV=os.devnull,
                        GITHUB_STEP_SUMMARY=os.devnull,
                        **{inputs["event"]: "pull_request", inputs["filter"]: filtered},
                    ),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                combined = (result.stdout + result.stderr).strip()
                self.assertNotEqual(
                    0,
                    result.returncode,
                    f"on a pull request whose change filter produced {filtered!r} -- "
                    "which is what a filter step that did not run leaves behind -- the "
                    "resolution concluded successfully. Whatever it wrote, the suite "
                    f"is then gated on a value nothing produced: {combined[-400:]!r}",
                )
                # Turning a silent green into a red is worth only as much as the
                # red is diagnosable. The whole reason this refusal exists is
                # that the empty string is indistinguishable from "nothing
                # changed" -- so the message has to say which one it is, or the
                # next person reads a failed discovery job and looks at the
                # discovery step.
                self.assertIn(
                    "filter",
                    combined.lower(),
                    "the resolution refused the value without naming the change "
                    f"filter as the cause; it emitted {combined[-400:]!r}",
                )

    # Representative of the configuration directory's breadth, not of its
    # current contents: a filter narrowed to any one of these subtrees reports
    # a legitimate `false` for a pull request that changed another.
    CONFIGURATION_PATHS = (
        "ansible/playbooks/host-baseline.yml",
        "ansible/roles/some_role/tasks/main.yml",
        "ansible/roles/some_role/molecule/default/molecule.yml",
        "ansible/requirements.yml",
        "ansible/requirements-test.txt",
        "ansible/ansible.cfg",
        "ansible/inventory/hcloud.yml",
    )
    NON_CONFIGURATION_PATHS = (
        "README.md",
        "terraform/environments/prod/main.tf",
        "platform/docker-compose.yml",
        ".github/workflows/ansible-verify.yml",
    )

    def test_the_change_filter_selects_the_whole_configuration_directory(self) -> None:
        """SPECIFIED -- "Every pull request that changes files under `ansible/`
        SHALL trigger continuous-integration checks over that configuration",
        and its converse, scenario "A pull request touching no Ansible file
        starts no container".

        This is the third input to the gate, and the one neither other check
        reaches. Whether the filter step RUNS is asserted below; whether it
        produced a real value is refused at run time by the resolution itself.
        What it LOOKS AT is asserted here, and nothing else does.

        Narrow the pattern to a subdirectory and the failure is silent in a way
        the other two are not: the filter runs, reports a perfectly legitimate
        `false` for a pull request that changed `ansible/playbooks/`, the matrix
        skips, the refusal does not fire because the value is valid, and the
        gate concludes success on a pull request that changed files under
        `ansible/`. That is the sentence the requirement opens with, defeated
        without a single check going red.

        Asserted behaviourally rather than as the literal string `ansible/**`,
        so that any pattern covering the directory passes and any pattern
        missing part of it fails.
        """
        workflow = self._workflow()
        discovery_key, discovery_job = self._discovery_job(workflow)
        patterns: list[str] = []
        for step in discovery_job.get("steps") or []:
            if "paths-filter" not in str(step.get("uses", "")):
                continue
            declared = (step.get("with") or {}).get("filters")
            parsed = yaml.safe_load(declared) if isinstance(declared, str) else declared
            self.assertIsInstance(
                parsed,
                dict,
                f"the change-filter step in `{discovery_key}` declares `filters:` as "
                f"{declared!r}, which is not a mapping of filter name to patterns",
            )
            for entry in parsed.values():
                patterns.extend(entry if isinstance(entry, list) else [entry])
        self.assertTrue(
            patterns,
            f"the change-filter step in `{discovery_key}` declares no patterns, so "
            "this check would pass having read nothing",
        )
        unmatched = [
            path
            for path in self.CONFIGURATION_PATHS
            if not any(gh_glob_matches(str(pattern), path) for pattern in patterns)
        ]
        self.assertEqual(
            [],
            unmatched,
            f"the change filter's patterns {patterns} do not select these files under "
            f"ansible/: {unmatched}. A pull request changing one of them would be "
            "reported as touching nothing, the suite would be skipped, and the "
            "required check would conclude success having verified nothing",
        )
        overmatched = [
            path
            for path in self.NON_CONFIGURATION_PATHS
            if any(gh_glob_matches(str(pattern), path) for pattern in patterns)
        ]
        self.assertEqual(
            [],
            overmatched,
            f"the change filter's patterns {patterns} also select these files outside "
            f"ansible/: {overmatched}, so the suite would run on pull requests that "
            "cannot affect it -- the cost this gating exists to avoid",
        )

    def test_the_change_filter_itself_runs_only_where_there_is_a_diff(self) -> None:
        """DERIVED (design.md Decision 1, tasks.md 2.3) -- no scenario states
        it. The specification requires the suite to run in full on an event
        carrying no diff; skipping the filter step on such an event is how this
        change makes the polarity above structurally unreachable rather than
        merely handled, which is a design choice rather than a stated
        obligation. Nothing in this repository has observed the filter action on
        a diffless event, which is why this change also observes it on a manual
        dispatch after merge. Reconsider this assertion, do not weaken it, if
        the filter is made safe on such an event by another means."""
        workflow = self._workflow()
        discovery_key, discovery_job = self._discovery_job(workflow)
        filters = [
            (index, step)
            for index, step in enumerate(discovery_job.get("steps") or [])
            if "paths-filter" in str(step.get("uses", ""))
        ]
        self.assertTrue(
            filters,
            f"the discovery job `{discovery_key}` carries no change-filter step, so "
            "the resolution above has nothing to resolve on a pull request",
        )
        for index, step in filters:
            condition = compact(step.get("if", ""))
            label = step_label(discovery_key, index, step)
            self.assertIn(
                "github.event_name",
                condition,
                f"the change-filter step {label} is conditioned on "
                f"{step.get('if')!r}, which does not test the event: on an event "
                "carrying no diff it runs anyway, and what it does there is not "
                "something this repository has observed",
            )
            # The polarity, not merely the mention. Asserting that the condition
            # names the event would be satisfied by its own negation, and the
            # negation is not a lesser version of this check -- it is silently
            # catastrophic. With the filter skipped on a pull request its output
            # is the empty string, the resolution reads that as `false`, the
            # matrix skips, and the gate's skipped-and-not-asked-for branch
            # concludes SUCCESS. That is a green required status check on
            # exactly the pull requests this workflow exists to gate, and every
            # other test in this file stays green while it happens.
            self.assertIn(
                "=='pull_request'",
                condition,
                f"the change-filter step {label} is conditioned on "
                f"{step.get('if')!r}, which does not run it ON a pull request. "
                "Inverted, the filter is skipped where the diff exists, its output "
                "is empty, the matrix is skipped as though nothing changed, and the "
                "required check reports success having run no scenario",
            )
            # Scoped to the OPERAND, not to the whole condition. Checking for
            # `!=` anywhere reasons about the condition as a bag of characters:
            # it rejects a legitimate conjunct such as
            # `... && github.actor != 'dependabot[bot]'`, while still admitting
            # `!(github.event_name == 'pull_request')` -- valid Actions syntax,
            # identical in effect to the inversion, and containing no `!=` at
            # all. One mistake with two faces, so one fix for both.
            for negation in ("!='pull_request'", "!("):
                self.assertNotIn(
                    negation,
                    condition,
                    f"the change-filter step {label} is conditioned on "
                    f"{step.get('if')!r}, which negates the event test -- see "
                    "above: the failure is a green conclusion, not a red one",
                )


# --------------------------------------------------------------------------
# iac-safety-hardening / Automated Dependency Updates -- the identity a
# workflow opens a pull request with
#
# Derived from the delta specs of the OpenSpec change
# `open-autoupdate-pr-with-app-token`, before any implementation of that change
# existed. The requirement is held in `iac-safety-hardening`
# (openspec/specs/iac-safety-hardening/spec.md); the clauses these tests trace
# to do not appear there until that change is archived, which is the one
# bounded interval this repository's citation rule accepts. See that change's
# test-plan.md for the scenario-to-test mapping, the baseline, and the
# scenarios deliberately left uncovered.
#
# The subject is EVERY workflow that opens a pull request, discovered by
# reading steps rather than by naming `pre-commit-autoupdate.yml`: the delta
# states the constraint over all of them so that a second such workflow written
# later cannot reintroduce the defect without violating anything. Today exactly
# one workflow matches, which is why the discovery below carries a vacuity
# guard -- with no match every other assertion here passes over an empty list,
# and a discovery that has stopped matching is then indistinguishable from a
# repository that satisfies the requirement.
#
# What is asserted is shape, not function. This suite makes no network call, so
# it cannot establish that the secrets exist, that an App is installed, or that
# a pull request opened and became mergeable. That last one is the change's own
# confirm-gate observation, not a static read of a committed file.
# --------------------------------------------------------------------------

README = ROOT / "README.md"

# An action whose job is to open a pull request. Matched on the action's own
# name rather than on one vendor's full reference, so a fork, a rename or a
# major-version bump of `peter-evans/create-pull-request` is still discovered.
PR_OPENING_ACTION = re.compile(r"create-pull-request", re.IGNORECASE)

# A shell step that opens one. `gh api repos/.../pulls/<n>` is deliberately not
# matched here: apply.yml READS a pull request that way, and reading is not
# opening. Only a POST to the collection creates one.
PR_OPENING_COMMANDS = (
    re.compile(r"\bgh\s+pr\s+create\b"),
    re.compile(r"\bhub\s+pull-request\b"),
)
PR_OPENING_API_POST = (
    re.compile(r"(?:-X|--method)\s+POST"),
    re.compile(r"/pulls\b"),
)

# The two spellings of the token a workflow gets for free, lowercased: Actions
# context names are case-insensitive, and `secrets.GITHUB_TOKEN` carries an
# underscore where `github.token` carries a dot, so neither matches the other.
DEFAULT_TOKEN_EXPRESSIONS = ("secrets.github_token", "github.token")

# Environment names through which a shell step receives a token.
TOKEN_ENVIRONMENT_NAMES = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN")

STEP_OUTPUT_REFERENCE = re.compile(r"steps\.([A-Za-z0-9_-]+)\.outputs\.[A-Za-z0-9_-]+")
SECRET_REFERENCE = re.compile(r"secrets\.([A-Za-z_][A-Za-z0-9_]*)")

WRITE_PERMISSION_LEVELS = frozenset({"write", "write-all"})
NON_WRITE_BLANKET_LEVELS = frozenset({"read-all", "none"})

# Vocabulary the README runbook is read for. The obligations are the delta's
# ("the authority it is scoped to", "how it is rotated"); the words are this
# check's own choice, because a runbook sentence has no other static form.
ROTATION_VOCABULARY = ("rotat",)
AUTHORITY_VOCABULARY = ("permission", "scope", "authorit", "read and write", "write access")


def workflow_files() -> list[Path]:
    """Every committed workflow, both spellings of the YAML suffix."""
    if not WORKFLOWS.is_dir():
        return []
    return sorted(
        path for path in WORKFLOWS.iterdir() if path.suffix in (".yml", ".yaml") and path.is_file()
    )


def step_opens_a_pull_request(step: dict) -> bool:
    """Whether a step opens a pull request, read from what the step does."""
    if not isinstance(step, dict):
        return False
    if PR_OPENING_ACTION.search(str(step.get("uses", ""))):
        return True
    run = str(step.get("run", ""))
    if any(pattern.search(run) for pattern in PR_OPENING_COMMANDS):
        return True
    return all(pattern.search(run) for pattern in PR_OPENING_API_POST)


class PullRequestOpeningStep:
    """One discovered step, with the job and workflow it sits in.

    The job and the workflow travel with the step because two of the three
    scenarios below are about the job's `permissions:`, and a job-level block
    is only readable against the workflow-level one it replaces.
    """

    def __init__(self, path: Path, workflow: dict, job_key: str, job: dict, index: int, step: dict):
        self.path = path
        self.workflow = workflow
        self.job_key = job_key
        self.job = job
        self.index = index
        self.step = step

    @property
    def label(self) -> str:
        return f"{self.path.name}:{step_label(self.job_key, self.index, self.step)}"

    @property
    def job_steps(self) -> list:
        return self.job.get("steps") or []


def pull_request_opening_steps() -> list[PullRequestOpeningStep]:
    """Every step in every committed workflow that opens a pull request."""
    found: list[PullRequestOpeningStep] = []
    for path in workflow_files():
        workflow = load_yaml(path)
        if not isinstance(workflow, dict):
            continue
        for job_key, job in jobs(workflow).items():
            if not isinstance(job, dict):
                continue
            for index, step in enumerate(job.get("steps") or []):
                if step_opens_a_pull_request(step):
                    found.append(
                        PullRequestOpeningStep(path, workflow, job_key, job, index, step)
                    )
    return found


def token_inputs(step: dict) -> dict:
    """Every input through which the step receives a token, by input name.

    For an action step that is `with: token:` and any sibling ending `-token`
    (`create-pull-request`'s `branch-token` is one, and design.md Decision 3
    turns on it). For a shell step it is the environment names the GitHub CLI
    reads. A step giving none is not a step whose token happens to be fine --
    it is one running on the default token implicitly.
    """
    inputs: dict = {}
    with_block = step.get("with")
    if isinstance(with_block, dict):
        for name, value in with_block.items():
            key = str(name)
            if key == "token" or key.endswith("-token"):
                inputs[f"with.{key}"] = str(value)
    env_block = step.get("env")
    if isinstance(env_block, dict):
        for name, value in env_block.items():
            if str(name) in TOKEN_ENVIRONMENT_NAMES:
                inputs[f"env.{name}"] = str(value)
    return inputs


def is_default_token(expression: str) -> bool:
    """Whether an expression resolves to the workflow's own `GITHUB_TOKEN`."""
    compacted = compact(expression).lower()
    return any(default in compacted for default in DEFAULT_TOKEN_EXPRESSIONS)


def declared_permissions(workflow: dict, job: dict):
    """`(source, declaration)` for what a job's `GITHUB_TOKEN` actually gets.

    A job-level block REPLACES the workflow-level one rather than adding to it,
    and a job declaring none inherits the workflow's whole -- so what a job
    receives is not what it declares, and reading `job["permissions"]` alone
    would call a workflow-level `contents: write` a job with no write.

    Where neither level declares one, the source is `None`. What the job
    receives is then the repository's default token scope: a repository
    setting, not repository content, which this suite makes no network call to
    read and so must refuse to accept rather than read as permissive.
    """
    if isinstance(job, dict) and "permissions" in job:
        holder, source = job, "job"
    elif isinstance(workflow, dict) and "permissions" in workflow:
        holder, source = workflow, "workflow"
    else:
        return None, None
    value = holder["permissions"]
    if not isinstance(value, (dict, str)):
        # `permissions:` with an empty value parses to None. That is not a
        # grant of nothing; it is a line no reader can tell from a typo.
        return None, value
    return source, value


def write_scopes(declaration) -> list[str]:
    """The write grants in a permissions declaration, as `scope: level`.

    The blanket string form is handled separately from the mapping form:
    `write-all` grants every scope, and an unrecognised string is reported
    rather than passed, because a level this check cannot read is not one it
    has established to be read-only.
    """
    if isinstance(declaration, str):
        return [] if declaration in NON_WRITE_BLANKET_LEVELS else [declaration]
    if not isinstance(declaration, dict):
        return []
    return sorted(
        f"{scope}: {level}"
        for scope, level in declaration.items()
        if str(level) in WRITE_PERMISSION_LEVELS
    )


def secrets_referenced_by(job: dict) -> set[str]:
    """Repository secrets a job names, other than the free `GITHUB_TOKEN`."""
    text = yaml.safe_dump(job, default_flow_style=False)
    names = {match.group(1) for match in SECRET_REFERENCE.finditer(text)}
    return {name for name in names if name.upper() != "GITHUB_TOKEN"}


def readme_sections(text: str) -> list[str]:
    """The README split at its Markdown headings, each section keeping its own
    heading line, so a passage can be read as a passage rather than as two
    facts that merely both appear in one long file."""
    sections: list[list[str]] = [[]]
    for line in text.splitlines():
        if line.startswith("#"):
            sections.append([])
        sections[-1].append(line)
    return ["\n".join(lines) for lines in sections if lines]


class PullRequestIdentityMixin:
    """The discovery every class below shares, with its vacuity guard."""

    def _opening_steps(self) -> list[PullRequestOpeningStep]:
        found = pull_request_opening_steps()
        self.assertTrue(
            found,
            "no step in any committed workflow was discovered opening a pull request. "
            "Either the repository has stopped refreshing pinned hook revisions by "
            "pull request -- which the Automated Dependency Updates requirement "
            "mandates -- or this discovery no longer recognises the way one is opened. "
            "Both are failures; neither is this section passing.",
        )
        return found


class TestNoWorkflowOpensAPullRequestWithTheDefaultToken(
    PullRequestIdentityMixin, unittest.TestCase
):
    """MODIFIED requirement: Automated Dependency Updates."""

    def test_a_committed_workflow_step_opens_a_pull_request_at_all(self) -> None:
        """SPECIFIED -- "pinned hook revisions SHALL instead be maintained by a
        scheduled workflow that runs `pre-commit autoupdate` and opens a pull
        request with the result". Stated as its own test rather than left as a
        setUp precondition because it is the one failure that would otherwise
        turn every other test in this section green."""
        self._opening_steps()

    def test_every_pull_request_opening_step_is_given_an_explicit_token(self) -> None:
        """SPECIFIED -- scenario "No workflow opens a pull request with the
        default workflow token": the step "SHALL be given an explicit token
        input". A step supplying none does not thereby avoid the defect -- it
        falls back to the default token silently, which is the state this
        repository has already spent three scheduled runs in."""
        offenders = [
            record.label for record in self._opening_steps() if not token_inputs(record.step)
        ]
        self.assertEqual(
            [],
            offenders,
            "these steps open a pull request with no explicit token input, so they run "
            f"on the workflow's own GITHUB_TOKEN by default: {offenders}",
        )

    def test_no_pull_request_opening_step_is_given_the_default_workflow_token(self) -> None:
        """SPECIFIED -- same scenario: the token "SHALL be ... neither
        `secrets.GITHUB_TOKEN` nor `github.token`".

        Every token-shaped input is read, not `token:` alone. That extension is
        DERIVED, from design.md Decision 3: passing the App token as `token:`
        while pinning `branch-token:` to the default would open the pull
        request correctly and then push every later update to its branch as
        GITHUB_TOKEN, producing no `synchronize` event and so no re-run of the
        required checks -- the same defect on the update path, and subtler.
        """
        # A step with no token input at all satisfies the loop below over an
        # empty set, and does so while running on precisely the token this test
        # forbids. The guard is called rather than duplicated so that the two
        # halves of the scenario cannot drift apart.
        self.test_every_pull_request_opening_step_is_given_an_explicit_token()
        offenders = []
        for record in self._opening_steps():
            for name, expression in token_inputs(record.step).items():
                if is_default_token(expression):
                    offenders.append(f"{record.label} -> {name}: {expression}")
        self.assertEqual(
            [],
            sorted(offenders),
            "these pull-request-opening steps are given the workflow's own default "
            "token. An event caused by GITHUB_TOKEN starts no workflow run, so the "
            "pull request receives no `on: pull_request` run, no required status check "
            f"reports on it, and it stays pending and unmergeable: {sorted(offenders)}",
        )

    def test_a_step_producing_that_token_appears_earlier_in_the_same_job(self) -> None:
        """SPECIFIED -- same scenario: "a step producing that token SHALL appear
        before it in the same job".

        A token drawn straight from `secrets.SOME_PAT` references no step and
        fails here. That is the scenario's own consequence, not this check
        being strict: the requirement forbids a credential that expires on a
        schedule, and a token minted per run from a non-expiring secret is what
        satisfies both clauses at once.
        """
        # Same reason as above: with no token input there is nothing whose
        # producer could be missing, and the check would pass over the state it
        # exists to reject.
        self.test_every_pull_request_opening_step_is_given_an_explicit_token()
        offenders = []
        for record in self._opening_steps():
            ids_before = {
                str(step.get("id"))
                for step in record.job_steps[: record.index]
                if isinstance(step, dict) and step.get("id")
            }
            for name, expression in token_inputs(record.step).items():
                if is_default_token(expression):
                    continue  # already reported by the test above
                produced_by = set(STEP_OUTPUT_REFERENCE.findall(compact(expression)))
                if not produced_by:
                    offenders.append(
                        f"{record.label} -> {name}: {expression} names no step output"
                    )
                    continue
                missing = sorted(produced_by - ids_before)
                if missing:
                    offenders.append(
                        f"{record.label} -> {name}: no earlier step in job "
                        f"`{record.job_key}` has id {missing}"
                    )
        self.assertEqual(
            [],
            sorted(offenders),
            "the token these steps open a pull request with is not produced by a step "
            f"running before them in the same job: {sorted(offenders)}",
        )


class TestThePullRequestJobLeavesTheDefaultTokenNoWrite(
    PullRequestIdentityMixin, unittest.TestCase
):
    """MODIFIED requirement: Automated Dependency Updates."""

    def test_the_job_opening_a_pull_request_declares_permissions_explicitly(self) -> None:
        """SPECIFIED -- scenario "A permissions declaration is present rather
        than merely absent": the job's effective permissions "SHALL come from an
        explicit declaration at workflow or job level".

        This one holds today and is expected to keep holding; it is not
        coverage of behaviour this change introduces, it is the guard on the
        way that behaviour would be faked. "Grants no write" is trivially true
        of a workflow declaring nothing, so deleting both blocks is the
        cheapest way to make the next test green -- and it is the opposite of
        what the requirement asks, because an absent declaration falls back to
        a repository setting that can change with no commit at all.
        """
        offenders = []
        for record in self._opening_steps():
            source, value = declared_permissions(record.workflow, record.job)
            if source is None:
                offenders.append(
                    f"{record.path.name}: job `{record.job_key}` -- declared: {value!r}"
                )
        self.assertEqual(
            [],
            sorted(offenders),
            "these jobs open a pull request while no explicit `permissions:` "
            "declaration is in force for them at either workflow or job level, so what "
            "their GITHUB_TOKEN receives is the repository's default token scope -- a "
            f"setting, not repository content, and unreadable here: {sorted(offenders)}",
        )

    def test_the_job_opening_a_pull_request_receives_no_write_scope(self) -> None:
        """SPECIFIED -- scenario "The default workflow token is not left holding
        unused write authority": an explicit declaration "SHALL be in force for
        that job, and the permissions it grants SHALL NOT include a write that
        the separate identity performs instead".

        Absence is an offender here as well as in the test above, deliberately:
        the scenario is satisfied by a declaration granting no write and NOT by
        the absence of one, so a check that accepted absence would report
        success over the weakest state the workflow can be in.
        """
        offenders = []
        for record in self._opening_steps():
            source, declaration = declared_permissions(record.workflow, record.job)
            if source is None:
                offenders.append(f"{record.path.name}: `{record.job_key}` declares none")
                continue
            for grant in write_scopes(declaration):
                offenders.append(f"{record.path.name}: `{record.job_key}` ({source}) {grant}")
        self.assertEqual(
            [],
            sorted(offenders),
            "the default token of these pull-request-opening jobs still holds write "
            "authority the separate identity exercises instead, contrary to the "
            f"Least-Privilege Workflow Permissions requirement: {sorted(offenders)}",
        )


class TestPermissionsReading(unittest.TestCase):
    """MODIFIED requirement: Automated Dependency Updates. Unit-level cover for
    the two helpers the pair above rests on -- the smallest level at which the
    absent-versus-declared distinction is observable, and the one this section
    would otherwise assert only against a tree where it happens to hold."""

    def test_a_job_block_replaces_the_workflow_block_rather_than_adding_to_it(self) -> None:
        """DERIVED -- no scenario states the precedence; it is GitHub Actions'
        own semantics, and reading it the other way would let a job-level
        `contents: write` hide behind a workflow-level `contents: read`."""
        workflow = {"permissions": {"contents": "read"}}
        job = {"permissions": {"contents": "write"}}
        self.assertEqual(("job", {"contents": "write"}), declared_permissions(workflow, job))
        self.assertEqual(
            ("workflow", {"contents": "read"}), declared_permissions(workflow, {"steps": []})
        )

    def test_a_declaration_absent_at_both_levels_is_read_as_absent(self) -> None:
        """SPECIFIED -- scenario "A permissions declaration is present rather
        than merely absent". Without this case the check above is only ever
        exercised against a tree that declares one, so its discrimination would
        rest on nothing."""
        self.assertEqual((None, None), declared_permissions({"jobs": {}}, {"steps": []}))
        self.assertEqual((None, None), declared_permissions({"permissions": None}, {}))

    def test_an_empty_mapping_is_a_declaration_granting_no_write(self) -> None:
        """SPECIFIED -- same scenario, its other side: `permissions: {}` grants
        nothing and is the strongest state a job can declare, so reading it as
        absent would fail the one workflow that had done exactly what the
        requirement asks."""
        source, declaration = declared_permissions({}, {"permissions": {}})
        self.assertEqual("job", source)
        self.assertEqual([], write_scopes(declaration))

    def test_write_grants_are_recognised_in_both_the_mapping_and_blanket_forms(self) -> None:
        """SPECIFIED -- "the permissions it grants SHALL NOT include a write".
        `write-all` is a write in one word and would pass a check that only
        looked inside a mapping."""
        self.assertEqual(
            ["contents: write", "pull-requests: write"],
            write_scopes({"contents": "write", "pull-requests": "write", "issues": "read"}),
        )
        self.assertEqual([], write_scopes({"contents": "read"}))
        self.assertEqual(["write-all"], write_scopes("write-all"))
        self.assertEqual([], write_scopes("read-all"))

    def test_the_default_token_is_recognised_in_both_its_spellings(self) -> None:
        """SPECIFIED -- scenario "No workflow opens a pull request with the
        default workflow token": "neither `secrets.GITHUB_TOKEN` nor
        `github.token`". Whitespace and case vary freely inside an Actions
        expression and must not decide the verdict."""
        for expression in (
            "${{ secrets.GITHUB_TOKEN }}",
            "${{secrets.github_token}}",
            "${{ github.token }}",
            "${{ GITHUB.TOKEN }}",
        ):
            self.assertTrue(is_default_token(expression), expression)
        for expression in ("${{ steps.app-token.outputs.token }}", "${{ secrets.APP_TOKEN }}"):
            self.assertFalse(is_default_token(expression), expression)


class TestTheAutomationCredentialIsDocumentedInTheReadme(
    PullRequestIdentityMixin, unittest.TestCase
):
    """MODIFIED requirement: Automated Dependency Updates."""

    def _credential_secrets(self) -> set[str]:
        names: set[str] = set()
        for record in self._opening_steps():
            names |= secrets_referenced_by(record.job)
        self.assertTrue(
            names,
            "the job opening a pull request names no repository secret other than "
            "GITHUB_TOKEN, so it has no separate identity to open one with. The "
            "requirement's identity is supplied by repository secrets; a job "
            "referencing none is running on the default token however its inputs read.",
        )
        return names

    def test_the_pull_request_job_draws_its_identity_from_a_repository_secret(self) -> None:
        """DERIVED -- from the requirement's "such an identity is supplied by
        repository secrets rather than by repository content", not from a
        scenario. It is the enabling condition for the three tests below: with
        no secret discovered they would each pass over an empty set, and the
        README obligation would be satisfied by a README saying nothing."""
        self._credential_secrets()

    def test_every_secret_holding_that_credential_is_named_in_the_readme(self) -> None:
        """SPECIFIED -- scenario "A long-lived automation credential is
        documented where it can be found": the runbook "SHALL name that
        credential, the secrets holding it ...". A credential whose only
        description lives in the change that introduced it is undocumented from
        the moment that change is archived."""
        text = read_text(README)
        missing = sorted(name for name in self._credential_secrets() if name not in text)
        self.assertEqual(
            [],
            missing,
            "the workflow that opens a pull request reads these repository secrets and "
            f"the README names none of them: {missing}",
        )

    def _documenting_sections(self) -> list[str]:
        names = self._credential_secrets()
        sections = [
            section for section in readme_sections(read_text(README))
            if all(name in section for name in names)
        ]
        self.assertTrue(
            sections,
            "no single README section names all of "
            f"{sorted(names)}, so there is no passage documenting the credential -- "
            "only mentions a reader would have to assemble one",
        )
        return sections

    def test_the_readme_passage_says_how_that_credential_is_rotated(self) -> None:
        """SPECIFIED for the obligation -- "and how it is rotated". DERIVED for
        the word matched: a runbook sentence has no other static form, and this
        check may not read anything but the committed file."""
        sections = self._documenting_sections()
        self.assertTrue(
            any(
                word in section.lower() for section in sections for word in ROTATION_VOCABULARY
            ),
            "the README passage naming the secrets that hold the automation credential "
            "does not say how it is rotated, so the one durable record of the procedure "
            "is the change that introduced it -- which is about to be archived",
        )

    def test_the_readme_passage_states_the_authority_that_credential_holds(self) -> None:
        """SPECIFIED for the obligation -- "the authority it is scoped to".
        DERIVED for the vocabulary, as above. The requirement bounds the
        credential to this repository and to no more than the pull-request step
        exercises; a reader who cannot see what it was scoped to cannot tell
        whether a later widening broke that bound."""
        sections = self._documenting_sections()
        self.assertTrue(
            any(
                word in section.lower() for section in sections for word in AUTHORITY_VOCABULARY
            ),
            "the README passage naming the secrets that hold the automation credential "
            "does not state the authority it is scoped to",
        )


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------------------
# iac-safety-hardening / No Store on This Host Holds Data Requiring Backup
#
# Derived from the delta specs of the OpenSpec change
# `scope-the-shared-database-to-non-durable-data`, before any implementation of
# that change existed. The requirement named in this section's heading is held
# in `openspec/specs/iac-safety-hardening/spec.md`; the requirement it defers to
# for the shared PostgreSQL instance, *Single Shared PostgreSQL Instance,
# Per-Application Databases*, is held in
# `openspec/specs/iac-platform-services/spec.md`. See that change's
# test-plan.md for the scenario-to-test mapping, the baseline, and the several
# scenarios of that change deliberately left uncovered.
#
# These assertions live in THIS suite rather than in `terraform test` or in a
# Molecule scenario because they are static reads of a committed file the
# pipeline deploys: `platform/docker-compose.yml` (AGENTS.md, "Testing"). They
# need no network call, credential, container runtime or Terraform binary, and
# they add no import.
#
# WHY A SPECIFICATION-ONLY CHANGE HAS TESTS AT ALL
# ------------------------------------------------
# The change adds no code. What it adds is a classification of the host's
# persistent stores, and two of the five reasons that classification rests on
# are properties of this committed file -- Prometheus's retention bounds, and
# Grafana's provisioned datasource and dashboards. That change's design records
# the silent disappearance of those properties as the failure mode the
# requirement exists to catch: no new data arrives, no clause reads as
# breached, and the host is then holding unrecoverable data under a
# specification asserting it holds none. The scenario "A store's stated reason
# ceases to hold" is written for exactly that, and the classes below are its
# executable half.
#
# WHAT THIS SECTION CANNOT SEE
# ----------------------------
# The requirement's scope reaches "any volume, named or anonymous, including
# one an image declares rather than the stack definition". An image-declared
# volume is not in this file -- `prom/alertmanager` declares `VOLUME
# /alertmanager`, so Alertmanager holds an anonymous volume the stack
# definition never mentions, and that store is deliberately absent from
# CLASSIFIED_STACK_STORES below because it is not stack-declared. Reading it
# would need `docker inspect` against a running host, which this suite is
# specified not to do. The census below is therefore a NECESSARY condition over
# the stack-declared subset and never the whole obligation; the whole of it is
# carried by the host census the change's own tasks require.
# --------------------------------------------------------------------------

TSDB_SERVICE = "prometheus"

# Grafana is `DASHBOARD_SERVICE`, defined with the dashboard-base-URL helpers
# above and reused here rather than shadowed.

# Retention flags whose presence and non-disabling value are what make
# Prometheus's store "bounded by both time and size". The requirement's table
# states the property, not the numbers, so nothing below asserts `28d` or
# `4GB`: shortening the window preserves the reason, and removing either flag
# does not.
TSDB_RETENTION_FLAGS = ("--storage.tsdb.retention.time", "--storage.tsdb.retention.size")
TSDB_PATH_FLAG = "--storage.tsdb.path"

GRAFANA_DATASOURCE_DIR = "/etc/grafana/provisioning/datasources"
GRAFANA_DASHBOARD_PROVIDER_DIR = "/etc/grafana/provisioning/dashboards"

# The dashboard-state policy in the requirement's body is written against these
# two settings being what the stack sets them to. It is stated as a standing
# property of the store rather than a hypothetical, so a change to either makes
# the requirement's own text false and obliges a restatement.
DASHBOARD_PROVIDER_STANDING_SETTINGS = {"allowUiUpdates": True, "disableDeletion": False}

# Every store the stack definition itself declares, and the reason the
# requirement gives for it needing no backup. Not a copy of the requirement's
# table: the table also carries Alertmanager's image-declared volume, which no
# read of this file can reach. Adding a store to the stack without adding it
# here fails `test_every_persistent_store_the_stack_declares_is_classified` --
# which is the point, because the requirement obliges a store added later to
# state which reason it satisfies.
CLASSIFIED_STACK_STORES = {
    "postgres_data": (
        "non-durable by policy -- Single Shared PostgreSQL Instance, "
        "Per-Application Databases limits it to technical or temporary records"
    ),
    "traefik_letsencrypt": "certificates re-issued on demand by the certificate authority",
    "/mnt/main-data/prometheus": (
        "rolling retention Prometheus enforces on itself, bounded by both time and size"
    ),
    "/mnt/main-data/grafana": (
        "split -- the provisioned datasource and dashboards are reproduced by a "
        "redeploy; the rest is non-durable under the dashboard-state policy"
    ),
}


def compose_document(path: Path | None = None) -> dict:
    """The whole stack definition, parsed.

    `compose_services` above reads the same file for the `services:` mapping;
    this is needed as well because `volumes:` and `configs:` are siblings of it.
    """
    target = PLATFORM_COMPOSE if path is None else path
    if not target.is_file():
        raise AssertionError(f"{target} does not exist")
    document = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise AssertionError(f"{target} does not parse as a Compose document")
    return document


def stack_configs(path: Path | None = None) -> dict:
    """The top-level `configs:` mapping, or an empty mapping."""
    configs = compose_document(path).get("configs")
    return configs if isinstance(configs, dict) else {}


def normalised_mount(entry: object) -> dict | None:
    """A service's mount entry as {source, target, read_only, kind}, or None
    where the entry is not a mount this check can read.

    Handles both forms Compose accepts: the short `SRC:DST[:OPTS]` string and
    the long mapping. `source` is None for an anonymous volume -- a short entry
    naming only a destination, which the stack declares and Compose backs with
    an unnamed volume. That case is kept rather than dropped: an anonymous
    volume the stack declares persists data exactly as a named one does, and
    the requirement's scope names it.
    """
    if isinstance(entry, dict):
        kind = str(entry.get("type") or "volume")
        source = entry.get("source")
        return {
            "source": str(source) if source is not None else None,
            "target": str(entry.get("target") or ""),
            "read_only": bool(entry.get("read_only")),
            "kind": kind,
        }
    if not isinstance(entry, str) or not entry.strip():
        return None
    fields = entry.split(":")
    if len(fields) == 1:
        return {"source": None, "target": fields[0], "read_only": False, "kind": "volume"}
    source, target = fields[0], fields[1]
    options = fields[2].split(",") if len(fields) > 2 else []
    return {
        "source": source,
        "target": target,
        "read_only": "ro" in options,
        "kind": "bind" if source.startswith(("/", "./", "../", "~")) else "volume",
    }


def service_mounts(path: Path | None = None):
    """Yield (service, normalised mount) for every `volumes:` entry in the
    stack, in service order.

    `configs:` entries are deliberately not yielded. Nothing persists into one:
    every deploy recreates it from the stack definition, which is why the
    change's own host census passes over them.
    """
    for name, definition in sorted(compose_services(path).items()):
        if not isinstance(definition, dict):
            continue
        entries = definition.get("volumes")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            mount = normalised_mount(entry)
            if mount is not None:
                yield name, mount


def stack_declared_stores(path: Path | None = None) -> dict:
    """Every store the stack definition declares, as identifier -> where.

    A store is a mount data can be persisted into. Excluded, for the reason the
    requirement's own scope clause gives -- data persisted "outside its
    container's writable layer":

    * a read-only mount, into which nothing persists. This is what removes the
      host paths cAdvisor and node-exporter read (`/`, `/proc`, `/sys`,
      `/var/lib/docker`, the Docker and containerd sockets), each of which the
      stack mounts `:ro`. They are excluded for being read-only, never for
      being on a list, so one remounted writable would appear here.
    * a `tmpfs` mount, which does not survive the container.
    """
    stores: dict[str, str] = {}
    for service, mount in service_mounts(path):
        if mount["read_only"] or mount["kind"] == "tmpfs":
            continue
        source = mount["source"]
        identifier = source if source else f"<anonymous volume at {mount['target']}>"
        stores.setdefault(identifier, f"{service} -> {mount['target']}")
    return stores


def unclassified_stack_declared_stores(path: Path | None = None) -> list[str]:
    return sorted(
        f"{identifier} ({where})"
        for identifier, where in stack_declared_stores(path).items()
        if identifier not in CLASSIFIED_STACK_STORES
    )


def service_command_words(name: str, path: Path | None = None) -> list[str]:
    """A service's `command:`, in either the list or the string form Compose
    accepts, as a flat list of words."""
    definition = compose_services(path).get(name)
    if not isinstance(definition, dict):
        raise AssertionError(f"the stack defines no service named {name!r}")
    command = definition.get("command")
    if isinstance(command, list):
        return [str(word) for word in command]
    if isinstance(command, str):
        return command.split()
    return []


def command_flag_value(name: str, flag: str, path: Path | None = None) -> str | None:
    """The value a service's command gives a flag, or None where it gives none.

    Accepts both `--flag=value` and `--flag value`; the stack uses the first.
    """
    words = service_command_words(name, path)
    for index, word in enumerate(words):
        if word == flag:
            following = words[index + 1] if index + 1 < len(words) else ""
            return "" if following.startswith("-") else following
        if word.startswith(flag + "="):
            return word.split("=", 1)[1]
    return None


def bound_is_disabling(value: str | None) -> bool:
    """Whether a retention value leaves the store unbounded.

    A bound with no non-zero digit is Prometheus's own way of spelling "no
    limit": `--storage.tsdb.retention.time=0` disables time-based retention and
    `--storage.tsdb.retention.size=0` disables the size cap, so a flag present
    with such a value bounds nothing while looking, to a grep, exactly like one
    that does.
    """
    if value is None:
        return True
    return re.search(r"[1-9]", value) is None


def unbounded_tsdb_retention(path: Path | None = None) -> list[str]:
    offences = []
    for flag in TSDB_RETENTION_FLAGS:
        value = command_flag_value(TSDB_SERVICE, flag, path)
        if value is None:
            offences.append(f"{flag}: absent")
        elif bound_is_disabling(value):
            offences.append(f"{flag}: {value!r}, which sets no bound")
    return offences


def service_config_mounts(name: str, path: Path | None = None) -> list[dict]:
    """A service's `configs:` entries as {source, target}, in either form.

    A short entry naming only a source resolves to `/<source>`, which is what
    Compose does with it.
    """
    definition = compose_services(path).get(name)
    if not isinstance(definition, dict):
        raise AssertionError(f"the stack defines no service named {name!r}")
    entries = definition.get("configs")
    if not isinstance(entries, list):
        return []
    mounts = []
    for entry in entries:
        if isinstance(entry, dict):
            source = entry.get("source")
            if source is None:
                continue
            target = entry.get("target") or f"/{source}"
            mounts.append({"source": str(source), "target": str(target)})
        elif isinstance(entry, str) and entry.strip():
            mounts.append({"source": entry, "target": f"/{entry}"})
    return mounts


def _under(directory: str, target: str) -> bool:
    return target.startswith(directory.rstrip("/") + "/")


def config_content(source: str, path: Path | None = None) -> str:
    """The inline `content:` of a top-level config, or the empty string.

    A config provisioned from a file on the deploy runner rather than from
    inline content would return empty here, which is the honest answer: the
    reason under test is that the artifacts are "reproduced from this
    repository by a redeploy", and content this file does not carry is not
    reproduced from this repository.
    """
    definition = stack_configs(path).get(source)
    if not isinstance(definition, dict):
        return ""
    content = definition.get("content")
    return content if isinstance(content, str) else ""


def dashboard_provider_entries(path: Path | None = None) -> list[dict]:
    """Every provider declared by whatever config the stack mounts into
    Grafana's dashboard-provisioning directory."""
    providers = []
    for mount in service_config_mounts(DASHBOARD_SERVICE, path):
        if not _under(GRAFANA_DASHBOARD_PROVIDER_DIR, mount["target"]):
            continue
        document = yaml.safe_load(config_content(mount["source"], path) or "") or {}
        declared = document.get("providers") if isinstance(document, dict) else None
        if isinstance(declared, list):
            providers.extend(entry for entry in declared if isinstance(entry, dict))
    return providers


def grafana_provisioning_offences(path: Path | None = None) -> list[str]:
    """Why Grafana's provisioned half is not reproduced by a redeploy, or [].

    Sentences rather than a boolean, so a failure names which limb of the
    reason went: the datasource, the provider, the dashboards, or the path that
    connects the last two.
    """
    offences = []
    mounts = service_config_mounts(DASHBOARD_SERVICE, path)

    datasources = [m for m in mounts if _under(GRAFANA_DATASOURCE_DIR, m["target"])]
    if not datasources:
        offences.append(
            f"no config is mounted into {GRAFANA_DATASOURCE_DIR}, so the datasource "
            f"is no longer provisioned from this repository"
        )
    for mount in datasources:
        if not config_content(mount["source"], path).strip():
            offences.append(
                f"the datasource config {mount['source']!r} carries no inline content, "
                f"so a redeploy does not reproduce it from this repository"
            )

    providers = [m for m in mounts if _under(GRAFANA_DASHBOARD_PROVIDER_DIR, m["target"])]
    if not providers:
        offences.append(
            f"no config is mounted into {GRAFANA_DASHBOARD_PROVIDER_DIR}, so no "
            f"dashboard provider is provisioned and no dashboard is loaded from disk"
        )

    provider_paths = []
    for entry in dashboard_provider_entries(path):
        options = entry.get("options")
        if isinstance(options, dict) and options.get("path"):
            provider_paths.append(str(options["path"]))
    if providers and not provider_paths:
        offences.append(
            "the dashboard provider names no options.path, so nothing states where "
            "the provisioned dashboards are read from"
        )

    dashboards = [
        m
        for m in mounts
        if any(_under(provider_path, m["target"]) for provider_path in provider_paths)
    ]
    if provider_paths and not dashboards:
        offences.append(
            f"the stack mounts no dashboard under any of {sorted(set(provider_paths))}, "
            f"so the provider provisions nothing and the dashboards this repository "
            f"carries are not reproduced by a redeploy"
        )
    for mount in dashboards:
        if not config_content(mount["source"], path).strip():
            offences.append(
                f"the dashboard config {mount['source']!r} carries no inline content, "
                f"so a redeploy does not reproduce it from this repository"
            )
    return offences


def bind_mount_targets(service: str, source: str, path: Path | None = None) -> list[str]:
    """Where a named host path is mounted inside a service's container."""
    return [
        mount["target"]
        for name, mount in service_mounts(path)
        if name == service and mount["source"] == source
    ]


class TestEveryPersistentStoreTheStackDeclaresIsClassified(unittest.TestCase):
    """ADDED requirement: No Store on This Host Holds Data Requiring Backup.

    WHAT PASSING THIS CLASS ESTABLISHES, AND WHAT IT DOES NOT
    --------------------------------------------------------
    Only a NECESSARY condition, over the stack-declared subset of the host's
    stores. The requirement is normative over every store on the host,
    including one an image declares rather than the stack definition and one an
    application deployed from another repository persists. Neither is in this
    file. Alertmanager's `/alertmanager` is the worked example: the image
    declares it, the stack definition does not mention it, and the change's own
    first draft missed it by reading this file rather than the host.

    So a green result here means no store was added to the stack definition
    without a stated reason. It does NOT mean the host holds no unclassified
    store, and no assertion below should be read as discharging the host census
    the requirement's own change performs.
    """

    def test_the_census_reaches_every_service_the_stack_defines(self) -> None:
        """DERIVED -- no scenario states it. It guards the assertion below from
        passing vacuously over a partial read, the same non-vacuity guard this
        suite's shared-stack pinning section applies to its own discovery."""
        services = sorted(compose_services())
        self.assertTrue(services, "the stack definition declares no services")
        visited = sorted({service for service, _ in service_mounts()})
        self.assertTrue(
            visited,
            "the census found no mount at all in a stack that declares named "
            "volumes, so it is not reading the file",
        )
        self.assertEqual(
            [],
            sorted(set(visited) - set(services)),
            "the census reports mounts for services the stack does not define",
        )

    def test_every_persistent_store_the_stack_declares_is_classified(self) -> None:
        """SPECIFIED -- scenario "A persistent store is added to the host": a
        store added to the platform stack, or an existing service beginning to
        persist there, "SHALL be recoverable without a backup of it, for one of
        the reasons above". This is the half of that a static read can decide:
        every store the stack declares carries a stated reason."""
        offenders = unclassified_stack_declared_stores()
        self.assertEqual(
            [],
            offenders,
            "these stores are declared by the platform stack and carry no stated "
            "reason for needing no backup: "
            f"{offenders}. Each one has to be classified under one of the reasons "
            "the requirement enumerates -- or, failing all of them, given a logical "
            "backup and a rehearsed restore before it first holds data -- and then "
            "named in CLASSIFIED_STACK_STORES above",
        )

    def test_every_classified_store_is_still_declared_by_the_stack(self) -> None:
        """DERIVED -- no scenario states it. The converse half: without it, a
        store removed or renamed in the stack definition would leave the
        requirement's dated table naming a store that no longer exists, and the
        assertion above would keep passing because the enumeration only ever
        grows stale in the permissive direction."""
        declared = set(stack_declared_stores())
        missing = sorted(set(CLASSIFIED_STACK_STORES) - declared)
        self.assertEqual(
            [],
            missing,
            "these stores carry a stated reason but are no longer declared by the "
            f"platform stack: {missing}. Either the stack moved them, in which case "
            "the classification names a store that does not exist, or they were "
            "removed, in which case the requirement's table needs the deletion",
        )

    def test_the_census_records_that_it_cannot_see_an_image_declared_volume(self) -> None:
        """DERIVED -- no scenario states it. The requirement's scope explicitly
        reaches a volume "an image declares rather than the stack definition",
        and this file cannot show one. A caveat nobody can delete without a
        test failing is the only durable form of that record; without it, a
        later reader takes a green census for the whole obligation, which is
        the exact reading that missed Alertmanager's store."""
        recorded = (type(self).__doc__ or "").lower()
        for phrase in ("necessary condition", "image declares", "alertmanager", "host census"):
            with self.subTest(phrase=phrase):
                self.assertIn(
                    phrase,
                    recorded,
                    "the census no longer records that it reads only the "
                    "stack-declared subset, so it now presents a partial read as the "
                    "whole obligation",
                )


class TestTheStoreCensusIsARealReadOfTheFile(unittest.TestCase):
    """ADDED requirement: No Store on This Host Holds Data Requiring Backup.

    The class above would pass identically if the census enumerated the four
    stores that exist today and read nothing. These run the same census over
    throwaway stack definitions differing from the committed one in exactly one
    property, so its verdict is shown to depend on the file.
    """

    BASE = "  traefik:\n    image: traefik:v3.7.10\n"

    def compose_fixture(self, services: str, extra: str = "") -> Path:
        directory = Path(tempfile.mkdtemp(prefix="platform-store-fixture-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "docker-compose.yml"
        path.write_text("---\nservices:\n" + services + extra, encoding="utf-8")
        return path

    def test_a_named_volume_added_to_a_service_is_caught_with_no_test_edit(self) -> None:
        """SPECIFIED -- scenario "A persistent store is added to the host", the
        limb covering "a service that persists data outside its container's
        writable layer is added to the platform stack"."""
        fixture = self.compose_fixture(
            self.BASE + "  newcomer:\n    image: redis:7.4.2\n    volumes:\n      - redis_data:/data\n",
            extra="volumes:\n  redis_data:\n",
        )
        self.assertEqual(
            ["redis_data (newcomer -> /data)"],
            unclassified_stack_declared_stores(fixture),
            "a named volume added to the stack was not caught, so the census "
            "enumerates the stores it knows about rather than reading the file",
        )

    def test_a_host_bind_mount_added_to_a_service_is_caught_with_no_test_edit(self) -> None:
        """SPECIFIED -- the same scenario's limb covering a host bind mount,
        which is the form both `/mnt/main-data` stores take."""
        fixture = self.compose_fixture(
            self.BASE
            + "  uploads:\n    image: nginx:1.29.3\n    volumes:\n      - /mnt/main-data/uploads:/srv/uploads\n"
        )
        self.assertEqual(
            ["/mnt/main-data/uploads (uploads -> /srv/uploads)"],
            unclassified_stack_declared_stores(fixture),
            "a host bind mount added to the stack was not caught",
        )

    def test_an_anonymous_volume_the_stack_declares_is_caught(self) -> None:
        """SPECIFIED -- the scenario names "any volume -- named or anonymous,
        declared by the stack definition or by the image". The stack-declared
        half of "anonymous" is readable here; the image-declared half is not,
        which is what the census's own docstring records."""
        fixture = self.compose_fixture(
            self.BASE + "  spool:\n    image: nginx:1.29.3\n    volumes:\n      - /var/spool/app\n"
        )
        self.assertEqual(
            ["<anonymous volume at /var/spool/app> (spool -> /var/spool/app)"],
            unclassified_stack_declared_stores(fixture),
            "an anonymous volume the stack itself declares was passed over, which "
            "is the form the requirement's scope was widened to reach",
        )

    def test_a_read_only_host_path_is_not_counted_as_a_store(self) -> None:
        """SPECIFIED -- the requirement's scope clause covers data persisted
        "outside its container's writable layer", and nothing persists into a
        read-only mount. This is the converse half: without it a census that
        reported every mount would satisfy the three tests above while failing
        on the read-only host paths cAdvisor and node-exporter already mount."""
        fixture = self.compose_fixture(
            self.BASE
            + "  reader:\n    image: prom/node-exporter:v1.9.1\n    volumes:\n"
            "      - /proc:/host/proc:ro\n"
            "      - /:/host/root:ro\n"
            "      - /var/run/docker.sock:/var/run/docker.sock:ro\n"
        )
        self.assertEqual(
            [],
            unclassified_stack_declared_stores(fixture),
            "a read-only mount was counted as a store, which would report the host "
            "paths the monitoring services read as unclassified data stores",
        )

    def test_a_read_only_path_remounted_writable_becomes_a_store(self) -> None:
        """DERIVED -- no scenario states it. The exclusion above is by the
        mount's own read-only flag and never by a list of paths; this is the
        assertion that would catch it degenerating into one."""
        fixture = self.compose_fixture(
            self.BASE + "  writer:\n    image: prom/node-exporter:v1.9.1\n    volumes:\n      - /proc:/host/proc\n"
        )
        self.assertEqual(
            ["/proc (writer -> /host/proc)"],
            unclassified_stack_declared_stores(fixture),
            "a host path mounted writable was excluded anyway, so the census "
            "excludes paths by name rather than by whether anything can persist "
            "into them",
        )

    def test_a_config_mount_is_not_counted_as_a_store(self) -> None:
        """DERIVED -- no scenario states it, and the change's own host census
        names the eight `configs:` mounts as expected non-stores: every deploy
        recreates them from the stack definition, so nothing persists into
        one."""
        fixture = self.compose_fixture(
            self.BASE
            + "  configured:\n    image: nginx:1.29.3\n    configs:\n"
            "      - source: app_config\n        target: /etc/app/app.yml\n",
            extra="configs:\n  app_config:\n    content: |\n      key: value\n",
        )
        self.assertEqual([], unclassified_stack_declared_stores(fixture))

    def test_a_stack_whose_stores_all_carry_a_reason_is_accepted(self) -> None:
        """DERIVED -- the converse half. Without it, a census that reported
        every store as unclassified would satisfy the tests above while failing
        every change to the stack regardless of what it changed."""
        fixture = self.compose_fixture(
            self.BASE
            + "  postgres:\n    image: postgres:16.15\n    volumes:\n      - postgres_data:/var/lib/postgresql/data\n"
            "  prometheus:\n    image: prom/prometheus:v3.7.3\n    volumes:\n      - /mnt/main-data/prometheus:/prometheus\n",
            extra="volumes:\n  postgres_data:\n",
        )
        self.assertEqual([], unclassified_stack_declared_stores(fixture))

    def test_a_stack_declaring_no_services_fails_rather_than_reading_nothing(self) -> None:
        """DERIVED -- the file-level non-vacuity guard, matching the one this
        suite's shared-stack pinning section already applies."""
        directory = Path(tempfile.mkdtemp(prefix="platform-store-fixture-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "docker-compose.yml"
        path.write_text("---\nvolumes:\n  postgres_data:\n", encoding="utf-8")
        with self.assertRaises(AssertionError):
            unclassified_stack_declared_stores(path)


class TestTheStatedReasonsForTheClassifiedStoresStillHold(unittest.TestCase):
    """ADDED requirement: No Store on This Host Holds Data Requiring Backup --
    scenario "A store's stated reason ceases to hold".

    The scenario names its two examples outright: "the retention settings that
    bound Prometheus's database, or the provisioning from this repository that
    reproduces Grafana's dashboards". Both are properties of
    `platform/docker-compose.yml`, and both can be removed by a change that
    adds no data and breaches no other clause. These are the assertions that
    make such a change fail rather than pass quietly.

    WHAT PASSING THIS CLASS ESTABLISHES, AND WHAT IT DOES NOT
    --------------------------------------------------------
    That the committed stack definition still carries the properties the two
    reasons rest on. NOT that the running host is deployed from this file at
    this commit, and NOT that Prometheus is in fact discarding data on that
    schedule -- both are observations of a running host, which this suite is
    specified not to make.
    """

    def test_prometheus_bounds_its_database_by_both_time_and_size(self) -> None:
        """SPECIFIED -- the store's stated reason is "rolling retention it
        enforces on itself, bounded by both time and size", and the scenario
        names "the retention settings that bound Prometheus's database" as the
        property a change must not silently remove.

        Asserts the bounds exist and bound something. It deliberately does not
        assert the numbers: the reason is boundedness, so shortening the window
        preserves it, while dropping a flag -- or setting it to Prometheus's own
        spelling of "no limit" -- does not.
        """
        offences = unbounded_tsdb_retention()
        self.assertEqual(
            [],
            offences,
            "Prometheus's time-series database is no longer bounded by both time "
            f"and size: {offences}. The store's stated reason for needing no backup "
            "rests on exactly that, so this change either restores the bound, "
            "restates the store's reason as another of the ones the requirement "
            "enumerates, or puts a logical backup and a rehearsed restore in place",
        )

    def test_the_retention_bounds_govern_the_store_the_classification_names(self) -> None:
        """SPECIFIED -- the classification names a particular store,
        `/mnt/main-data/prometheus`, and the retention flags bound whatever
        directory `--storage.tsdb.path` names. If those two came apart, the
        bounds would be enforced over a directory other than the classified
        store, and every assertion above would still pass."""
        tsdb_path = command_flag_value(TSDB_SERVICE, TSDB_PATH_FLAG)
        self.assertTrue(
            tsdb_path,
            f"the {TSDB_SERVICE} service names no {TSDB_PATH_FLAG}, so nothing "
            f"states which directory its retention bounds",
        )
        targets = bind_mount_targets(TSDB_SERVICE, "/mnt/main-data/prometheus")
        self.assertTrue(
            targets,
            "the stack no longer mounts /mnt/main-data/prometheus into the "
            f"{TSDB_SERVICE} service, so the store the classification names is not "
            "the one this service writes into",
        )
        self.assertTrue(
            any(tsdb_path == target or _under(target, tsdb_path) for target in targets),
            f"{TSDB_PATH_FLAG} is {tsdb_path!r}, which is not inside the classified "
            f"store mounted at {targets}: the retention bounds and the store the "
            f"requirement classifies have come apart, so the bound no longer bounds "
            f"the data the classification is about",
        )

    def test_grafanas_datasource_and_dashboards_are_provisioned_from_this_repository(self) -> None:
        """SPECIFIED -- the Grafana store's reason is split, and its first half
        is that "the datasource and the dashboards this repository provisions
        are reproduced by a redeploy". The scenario names "the provisioning
        from this repository that reproduces Grafana's dashboards" as the
        property a change must not silently remove."""
        offences = grafana_provisioning_offences()
        self.assertEqual(
            [],
            offences,
            "Grafana's provisioned half is no longer reproduced by a redeploy: "
            f"{offences}. That is the stated reason the classified store needs no "
            "backup, so this change either restores the provisioning, restates the "
            "store's reason, or puts a logical backup and a rehearsed restore in "
            "place before it lands",
        )

    def test_the_grafana_store_the_classification_names_is_the_one_grafana_writes_into(self) -> None:
        """SPECIFIED -- the same store identification as the Prometheus
        assertion above, and additionally what makes the split coherent: the
        provisioned dashboards are written inside the very directory the table
        classifies, so a provider path outside it would mean the reproduced
        half is not part of the store the row is about."""
        targets = bind_mount_targets(DASHBOARD_SERVICE, "/mnt/main-data/grafana")
        self.assertTrue(
            targets,
            "the stack no longer mounts /mnt/main-data/grafana into the "
            f"{DASHBOARD_SERVICE} service, so the store the classification names is "
            "not the one this service writes into",
        )
        provider_paths = [
            str(entry["options"]["path"])
            for entry in dashboard_provider_entries()
            if isinstance(entry.get("options"), dict) and entry["options"].get("path")
        ]
        self.assertTrue(provider_paths, "the dashboard provider names no options.path")
        for provider_path in provider_paths:
            with self.subTest(provider_path=provider_path):
                self.assertTrue(
                    any(
                        provider_path == target or _under(target, provider_path)
                        for target in targets
                    ),
                    f"the dashboard provider reads {provider_path!r}, which is not "
                    f"inside the classified store mounted at {targets}",
                )

    def test_the_dashboard_provider_still_permits_the_ui_edits_the_policy_covers(self) -> None:
        """SPECIFIED -- the requirement's dashboard-state policy states these
        two settings as fact: "The stack permits such edits -- its dashboard
        provider sets `allowUiUpdates` true and `disableDeletion` false -- so
        this is a standing property of that store rather than a hypothetical".

        A change to either makes that sentence false, whichever direction it
        moves in, which the scenario answers with "restate the store's reason".
        The assertion is therefore on the stated values and not on a judgement
        about which values would be safer.
        """
        providers = dashboard_provider_entries()
        self.assertTrue(
            providers,
            "the stack declares no dashboard provider, so the settings the "
            "dashboard-state policy is written against are gone entirely",
        )
        for entry in providers:
            name = entry.get("name", "<unnamed>")
            for key, stated in DASHBOARD_PROVIDER_STANDING_SETTINGS.items():
                with self.subTest(provider=name, setting=key):
                    self.assertEqual(
                        stated,
                        entry.get(key),
                        f"the dashboard provider {name!r} sets {key} to "
                        f"{entry.get(key)!r}, where the requirement's dashboard-state "
                        f"policy states it as {stated!r}. That policy is what covers "
                        f"the non-provisioned half of the Grafana store, so its own "
                        f"stated basis has changed and the requirement needs "
                        f"restating rather than this assertion being edited to match",
                    )


class TestTheStatedReasonChecksAreARealReadOfTheFile(unittest.TestCase):
    """ADDED requirement: No Store on This Host Holds Data Requiring Backup --
    scenario "A store's stated reason ceases to hold".

    The class above asserts of the committed file. These run the same checks
    over throwaway definitions in which exactly one reason has been removed, so
    each check is shown to fail when the property it is about goes -- which is
    the whole of what the scenario asks for.
    """

    PROVIDER_CONTENT = (
        "configs:\n"
        "  grafana_datasource:\n"
        "    content: |\n"
        "      apiVersion: 1\n"
        "      datasources:\n"
        "        - name: Prometheus\n"
        "  grafana_dashboard_provider:\n"
        "    content: |\n"
        "      apiVersion: 1\n"
        "      providers:\n"
        "        - name: platform-monitoring\n"
        "          options:\n"
        "            path: {provider_path}\n"
        "  grafana_dashboard_host:\n"
        "    content: |\n"
        '      {{"title": "Host resources"}}\n'
    )

    def compose_fixture(self, body: str) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="platform-reason-fixture-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "docker-compose.yml"
        path.write_text(body, encoding="utf-8")
        return path

    def prometheus_fixture(self, *flags: str) -> Path:
        command = "".join(f"      - {flag}\n" for flag in flags)
        return self.compose_fixture(
            "---\nservices:\n  prometheus:\n    image: prom/prometheus:v3.7.3\n"
            "    command:\n" + command + "    volumes:\n      - /mnt/main-data/prometheus:/prometheus\n"
        )

    def grafana_fixture(
        self, dashboard_target: str, provider_path: str = "/var/lib/grafana/dashboards"
    ) -> Path:
        return self.compose_fixture(
            "---\nservices:\n  grafana:\n    image: grafana/grafana:12.3.0\n"
            "    configs:\n"
            "      - source: grafana_datasource\n"
            "        target: /etc/grafana/provisioning/datasources/prometheus.yml\n"
            "      - source: grafana_dashboard_provider\n"
            "        target: /etc/grafana/provisioning/dashboards/dashboards.yml\n"
            f"      - source: grafana_dashboard_host\n        target: {dashboard_target}\n"
            "    volumes:\n      - /mnt/main-data/grafana:/var/lib/grafana\n\n"
            + self.PROVIDER_CONTENT.format(provider_path=provider_path)
        )

    def test_a_retention_flag_removed_is_caught(self) -> None:
        """SPECIFIED -- the scenario's first named example, "the retention
        settings that bound Prometheus's database"."""
        fixture = self.prometheus_fixture(
            "--storage.tsdb.path=/prometheus", "--storage.tsdb.retention.time=28d"
        )
        self.assertEqual(
            ["--storage.tsdb.retention.size: absent"],
            unbounded_tsdb_retention(fixture),
            "the size bound was removed and the check did not notice, so the store "
            "is bounded by time alone while the classification says both",
        )

    def test_a_retention_flag_left_present_but_disabled_is_caught(self) -> None:
        """DERIVED -- no scenario names this form. It is the failure a check
        written as "the flag is present" would miss entirely: `0` is
        Prometheus's own spelling of no limit, so the flag survives every text
        search while bounding nothing."""
        fixture = self.prometheus_fixture(
            "--storage.tsdb.path=/prometheus",
            "--storage.tsdb.retention.time=0",
            "--storage.tsdb.retention.size=0",
        )
        self.assertEqual(
            [
                "--storage.tsdb.retention.time: '0', which sets no bound",
                "--storage.tsdb.retention.size: '0', which sets no bound",
            ],
            unbounded_tsdb_retention(fixture),
            "a retention flag set to Prometheus's own value for 'no limit' was read "
            "as a bound",
        )

    def test_a_prometheus_bounded_by_both_is_accepted(self) -> None:
        """DERIVED -- the converse half, and the assertion that keeps the check
        a floor rather than a demand for particular numbers: a shorter window
        preserves the reason and must not fail."""
        fixture = self.prometheus_fixture(
            "--storage.tsdb.path=/prometheus",
            "--storage.tsdb.retention.time=7d",
            "--storage.tsdb.retention.size=512MB",
        )
        self.assertEqual([], unbounded_tsdb_retention(fixture))

    def test_removing_the_dashboard_provisioning_stanza_is_caught(self) -> None:
        """SPECIFIED -- the scenario's second named example, "the provisioning
        from this repository that reproduces Grafana's dashboards"."""
        fixture = self.compose_fixture(
            "---\nservices:\n  grafana:\n    image: grafana/grafana:12.3.0\n"
            "    volumes:\n      - /mnt/main-data/grafana:/var/lib/grafana\n"
        )
        offences = grafana_provisioning_offences(fixture)
        self.assertTrue(
            offences,
            "the whole provisioning stanza was deleted and the check reported no "
            "offence, so the reason the Grafana store needs no backup could be "
            "removed without anything failing",
        )
        self.assertTrue(
            any(GRAFANA_DASHBOARD_PROVIDER_DIR in offence for offence in offences),
            f"the deleted dashboard provider was not named among {offences}",
        )

    def test_a_dashboard_provisioned_outside_the_providers_path_is_caught(self) -> None:
        """DERIVED -- no scenario names it. It is the quiet form of the same
        loss: the stanza survives, every source is still mounted, and the
        provider reads a directory none of the dashboards land in, so nothing
        is reproduced by a redeploy while the file still looks provisioned."""
        fixture = self.grafana_fixture(dashboard_target="/tmp/host-resources.json")
        offences = grafana_provisioning_offences(fixture)
        self.assertTrue(
            offences,
            "a dashboard mounted outside the provider's own path was accepted, so "
            "the check confirms the stanza's presence rather than that it "
            "reproduces anything",
        )

    def test_a_config_carrying_no_inline_content_is_caught(self) -> None:
        """DERIVED -- no scenario names it. The reason is "reproduced from THIS
        repository by a redeploy"; a config whose content this file does not
        carry is reproduced from somewhere else, and the distinction is
        invisible to a check that only counts mounts."""
        fixture = self.compose_fixture(
            "---\nservices:\n  grafana:\n    image: grafana/grafana:12.3.0\n"
            "    configs:\n"
            "      - source: grafana_datasource\n"
            "        target: /etc/grafana/provisioning/datasources/prometheus.yml\n"
            "      - source: grafana_dashboard_provider\n"
            "        target: /etc/grafana/provisioning/dashboards/dashboards.yml\n"
            "      - source: grafana_dashboard_host\n"
            "        target: /var/lib/grafana/dashboards/host-resources.json\n"
            "configs:\n"
            "  grafana_datasource:\n    file: ./datasource.yml\n"
            "  grafana_dashboard_provider:\n"
            "    content: |\n"
            "      apiVersion: 1\n"
            "      providers:\n"
            "        - name: platform-monitoring\n"
            "          options:\n"
            "            path: /var/lib/grafana/dashboards\n"
            "  grafana_dashboard_host:\n"
            "    content: |\n"
            '      {"title": "Host resources"}\n'
        )
        offences = grafana_provisioning_offences(fixture)
        self.assertTrue(
            any("inline content" in offence for offence in offences),
            f"a config provisioned from outside this repository was accepted: {offences}",
        )

    def test_a_fully_provisioned_grafana_is_accepted(self) -> None:
        """DERIVED -- the converse half. Without it, a check that reported an
        offence unconditionally would satisfy every test above while failing
        every change to the stack regardless of what it changed."""
        fixture = self.grafana_fixture(
            dashboard_target="/var/lib/grafana/dashboards/host-resources.json"
        )
        self.assertEqual([], grafana_provisioning_offences(fixture))
