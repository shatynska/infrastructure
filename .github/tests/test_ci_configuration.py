"""Static-assertion tests for the CI configuration this repository ships.

Derived from the delta specs of the OpenSpec change `close-ci-verification-gaps`
(`openspec/changes/close-ci-verification-gaps/specs/`), before any implementation
of that change existed. Every assertion below is annotated SPECIFIED (it traces
to SHALL text in a delta spec) or DERIVED (it traces to `design.md`/`tasks.md`
rather than to a scenario). See that change's `test-plan.md` for the
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
# iac-cicd-pipeline / Ansible Configuration Is Verified in CI --
# the container image each scenario executes inside
# --------------------------------------------------------------------------
#
# Derived from the delta spec of the OpenSpec change
# `pin-and-fix-molecule-suite`
# (openspec/changes/pin-and-fix-molecule-suite/specs/iac-cicd-pipeline/spec.md),
# before any implementation of that change existed. See that change's
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
    Integration -- the clause bounding the pinning obligation to the scenarios
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
    Integration -- the extension of the pinned-manifest obligation to the
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
    Integration. Unit-level cover for the reference splitting every check above
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


# --------------------------------------------------------------------------
# iac-platform-services / Shared-Stack Service Images Are Pinned to an Exact
# Release, and Metrics Dashboards Are Available
#
# Derived from the delta specs of the OpenSpec change
# `fix-volume-discovery-and-consistency`
# (openspec/changes/fix-volume-discovery-and-consistency/specs/
# iac-platform-services/spec.md), before any implementation of that change
# existed. See that change's test-plan.md for the scenario-to-test mapping, the
# baseline, and the scenarios deliberately left uncovered.
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


if __name__ == "__main__":
    unittest.main()


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
