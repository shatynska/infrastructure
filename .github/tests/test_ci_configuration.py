"""Static-assertion tests for the CI configuration this repository ships.

Derived from the delta specs of the OpenSpec change `close-ci-verification-gaps`
(`openspec/changes/close-ci-verification-gaps/specs/`), before any implementation
of that change existed. Every assertion below is annotated SPECIFIED (it traces
to SHALL text in a delta spec) or DERIVED (it traces to `design.md`/`tasks.md`
rather than to a scenario). See that change's `test-plan.md` for the
scenario-to-test mapping and for the scenarios deliberately left uncovered.

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
# iac-cicd-pipeline / Ansible Configuration Is Verified in CI (ADDED)
# --------------------------------------------------------------------------


class TestAnsibleBlockingTier(unittest.TestCase):
    """ADDED requirement: Ansible Configuration Is Verified in CI."""

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
    """ADDED requirement: Ansible Configuration Is Verified in CI."""

    def test_no_pull_request_validation_job_declares_an_environment(self) -> None:
        """SPECIFIED -- scenario "Ansible verification receives no production
        credential": no verification job declares a deployment `environment:`.
        Also the standing invariant `handoff.md` records as must-not-undo."""
        workflow = load_yaml(PR_VALIDATION)
        offenders = [name for name, job in jobs(workflow).items() if "environment" in job]
        self.assertEqual([], offenders, f"jobs declaring `environment:`: {offenders}")

    def test_the_molecule_workflow_declares_no_environment(self) -> None:
        """SPECIFIED -- same scenario, advisory tier."""
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
    """ADDED requirement: Ansible Configuration Is Verified in CI."""

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
        """SPECIFIED -- scenario "A failing Molecule scenario does not block a
        merge": the failure SHALL be visible on the pull request. Advisory
        status comes from not registering the workflow as a required check, not
        from swallowing its conclusion. Establishes the visibility half only;
        branch-protection registration is not repository state."""
        self.assertNotIn(
            "continue-on-error",
            self.text,
            "ansible-verify.yml uses continue-on-error, which reports a green "
            "conclusion for a failed scenario and destroys the signal the advisory "
            "tier exists to collect",
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
    """ADDED requirement: Ansible Configuration Is Verified in CI."""

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
    because the apply workflow is not a required check, and that the required
    check must not carry one. This asserts the second half.
    """

    def test_the_required_check_declares_no_workflow_level_path_filter(self) -> None:
        """SPECIFIED -- "The workflow that is registered as a required check
        SHALL NOT be path-filtered at the workflow level"."""
        on = triggers(load_yaml(PR_VALIDATION))
        for event, config in on.items():
            if not isinstance(config, dict):
                continue
            for key in ("paths", "paths-ignore"):
                self.assertNotIn(
                    key,
                    config,
                    f"pr-validation.yml's `{event}` trigger declares `{key}:`, which "
                    "leaves every non-matching pull request permanently pending and "
                    "so unmergeable",
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


if __name__ == "__main__":
    unittest.main()
