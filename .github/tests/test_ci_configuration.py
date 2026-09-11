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
import functools
import os
import posixpath
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


def _selects(patterns, path: str) -> bool:
    """Whether a dorny/paths-filter pattern list selects a path, negations included.

    Last matching pattern wins, and a file must be matched by a positive before
    a negation can exclude it. A deliberately approximate reimplementation of
    picomatch, written here because this suite may not take the dependency and
    may not reach the network: where the two disagree the action is the
    authority, and the behaviour is established by observation on a real pull
    request. It is worth having anyway, being the only thing that can go red
    when someone deletes a negation.
    """
    selected = False
    for pattern in patterns:
        text = str(pattern)
        negated = text.startswith("!")
        if gh_glob_matches(text[1:] if negated else text, path):
            selected = not negated
    return selected


def terraform_lockfile_directories(root: Path | None = None) -> set[str]:
    """Every repository directory carrying a `.terraform.lock.hcl`, as `/a/b`.

    Walks with `walked_files()` rather than with `rglob`, because AGENTS.md
    requires every change to take a working tree -- at `.claude/worktrees/<name>`
    under the Claude Code binding, or `.worktrees/<name>` generally -- and a
    working tree is a FULL COPY of the repository. An `rglob` pruning only
    `.git` therefore finds one phantom lockfile directory per worktree per real
    one and reports each uncovered by Dependabot. That condition holds whenever
    any change is in progress, which is most of the time.

    Continuous integration never saw it, because a checkout carries tracked files
    only; and it does not reproduce from INSIDE a worktree, because the walk
    starts at that tree's own root. It failed from the repository's main working
    tree -- exactly where a session runs the suite after leaving one. The cost
    was a red suite a session had to learn to disbelieve, which is the habit this
    repository refuses everywhere else.

    `.gitignore` is not an alternative to this, and the two are not the same fix.
    A filesystem walk does not consult git, so ignoring `.claude/worktrees/`
    leaves this walk finding precisely what it found before. Both working-tree
    roots are ignored for the other reason -- it stops a `git add -A` from the
    main working tree staging a duplicate copy of the whole repository -- and
    `TestTheWorkingTreeRootsAreIgnored` holds them there.

    Takes `root` so the behaviour is exercisable against a fixture tree. The
    forward reference to `walked_files()`, defined further down this file, is
    resolved at call time.

    Inherited from that walker, and accepted rather than discovered later: it
    also prunes `openspec/` and `ansible/roles/geerlingguy.docker`, so a lockfile
    under either is outside this assertion's reach. Neither is a Terraform root
    Dependabot could update -- planning artifacts are not deployed, and the
    Galaxy role is not committed here.
    """
    base = ROOT if root is None else root
    found = set()
    for path in walked_files(base):
        if path.name != ".terraform.lock.hcl":
            continue
        relative = path.parent.relative_to(base).as_posix()
        found.add("/" if relative == "." else "/" + relative)
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

    # `test_dependabot_configures_both_required_ecosystems` was removed by
    # `cover-platform-images-with-dependabot`, not renamed. Its body iterated
    # the literal pair ("terraform", "github-actions") and its name asserted
    # "both" -- the enumeration that change widens to three. Its replacement is
    # `TestDependabotWatchesEveryRequiredEcosystem
    # .test_dependabot_configures_every_required_ecosystem`, which reads the
    # requirement's full set. The lockfile-directory assertion above is
    # untouched and stays here.


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

    @staticmethod
    def _is_a_scan(step: dict) -> bool:
        """Whether a step INVOKES gitleaks, rather than merely mentioning it.

        A shell comment naming gitleaks is not a secret scan, and reading one as
        one is not pedantic here: the environment-discovery body cites the
        gitleaks step as the precedent for reading a pin out of a committed
        file, so the job holding it counted as a scan job -- and an assertion
        that some scan runs unconditionally was satisfied by a comment.
        """
        for key in ("name", "uses"):
            if "gitleaks" in str(step.get(key, "")).lower():
                return True
        for line in str(step.get("run", "")).splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "gitleaks" in stripped.lower():
                return True
        return False

    def setUp(self) -> None:
        self.workflow = load_yaml(PR_VALIDATION)
        self.gitleaks_steps = [
            (job, index, step)
            for job, index, step in steps(self.workflow)
            if self._is_a_scan(step)
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

    def test_at_least_one_secret_scan_is_wholly_unconditional(self) -> None:
        """SPECIFIED -- "`gitleaks` SHALL run on every pull request, whether or
        not Terraform configuration changed", and scenario "A credential outside
        Terraform is still caught".

        Stated POSITIVELY, and added because the two assertions above cannot
        carry this between them. Both are refusals -- no scan step, and no job
        holding one, may be conditioned on Terraform having changed -- and a
        refusal is satisfied by a condition that gates the scan on something
        spelled differently. `make-the-pipeline-environment-agnostic` created
        exactly that situation: its plan matrix job carries a second gitleaks
        copy, for a different obligation (an ordering, which has nothing to
        order where there is no plan), and gates the job on a discovery output.
        That is correct, and it is indistinguishable to the refusals above from
        gating EVERY scan the same way.

        So this asserts what the requirement actually wants: somewhere in this
        workflow, a gitleaks step runs on every pull request whatever it touched
        -- no condition of its own, and none on its job that could evaluate
        false. `always()` on the enclosing job is admitted, through the same
        predicate the two unconditionality requirements are read with, because it
        cannot evaluate false and so gates nothing; that job is an aggregator and
        carries `always()` for a reason argued elsewhere.
        """
        self.test_the_workflow_has_a_secret_scanning_step_at_all()
        unconditional = [
            step_label(job, index, step)
            for job, index, step in self.gitleaks_steps
            if step.get("if") is None
            and job_condition_is_admissible(jobs(self.workflow)[job] or {})
        ]
        self.assertTrue(
            unconditional,
            "every gitleaks step in pr-validation.yml sits behind a condition, on the "
            "step or on its job, so a pull request that does not satisfy those "
            "conditions is not scanned at all. At least one scan must run on every "
            "pull request whatever it touched. The steps found were "
            + repr([step_label(job, index, step) for job, index, step in self.gitleaks_steps]),
        )

    def test_secret_scanning_precedes_any_terraform_plan_in_the_same_job(self) -> None:
        """SPECIFIED -- scenario "PR with a leaked credential fails validation":
        the workflow "SHALL fail before any `terraform plan` is executed", and
        the MODIFIED *Pull Request Plan Visibility*: "**A secret scan SHALL
        precede every plan, in the job that runs it.**"

        STRENGTHENED by `make-the-pipeline-environment-agnostic`, not
        re-expressed. Its previous body skipped any job in which it found no
        gitleaks step (`if not scan_indices or not plan_indices: continue`), so
        moving a plan into a job of its own made this assertion VACUOUS rather
        than red -- which is exactly the restructure that change's design.md
        Decision 3 forbids, and it was the only thing guarding it. A plan in a
        job with no scan at all is now an offence, because a plan job with no
        scan does not prevent a leaked credential reaching a cloud API or a pull
        request comment any less than one with the scan in the wrong place.

        A job holding a scan and NO plan is still not an offence: that is
        `validate`, whose scan is unconditional precisely so that a pull request
        planning nothing is still scanned.
        """
        self.test_the_workflow_has_a_secret_scanning_step_at_all()
        offenders = []
        for job_name, job in sorted(jobs(self.workflow).items()):
            job_steps = job.get("steps") or []
            scan_indices = [
                i for i, s in enumerate(job_steps) if "gitleaks" in step_text(s).lower()
            ]
            plan_indices = [
                i
                for i, s in enumerate(job_steps)
                if re.search(r"terraform\s+plan\b", str(s.get("run", "")))
            ]
            if not plan_indices:
                continue
            if not scan_indices:
                offenders.append(
                    f"{job_name}: runs `terraform plan` and carries no secret scan at all"
                )
            elif max(scan_indices) > min(plan_indices):
                offenders.append(
                    f"{job_name}: plans at step {min(plan_indices)}, before the scan at "
                    f"step {max(scan_indices)}"
                )
        self.assertEqual(
            [],
            offenders,
            "the ordering is scoped to a job because that is where a failing step stops "
            f"the next one; a scan in a different job stops nothing: {offenders}",
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


class TestTheAdmittedJobConditionIsExactlyOneLiteral(unittest.TestCase):
    """MODIFIED requirements: The Specification Record Is Verified in Continuous
    Integration; The Continuous-Integration Configuration Is Itself Verified.

    Both admit `always()` on a job declaring `needs:` "as that exact literal and
    not as a class". The two assertions above consult
    `job_condition_is_admissible` for that, and an allowance that admitted too
    much would leave both of them green over a job that CAN be skipped -- which
    is the whole property they exist to hold. So the predicate is pinned here,
    against the exact spellings this change's tasks.md 5.3 names.
    """

    def test_a_job_with_no_condition_is_admitted(self) -> None:
        """SPECIFIED -- the unamended case, which the allowance does not touch."""
        self.assertTrue(job_condition_is_admissible({}))
        self.assertTrue(job_condition_is_admissible({"needs": ["discover"]}))

    def test_the_bare_and_wrapped_spellings_of_always_are_admitted(self) -> None:
        """SPECIFIED -- "in either the bare or the `${{ }}`-wrapped spelling"."""
        for spelling in ("always()", "${{ always() }}", "${{always()}}"):
            with self.subTest(condition=spelling):
                self.assertTrue(
                    job_condition_is_admissible({"needs": ["discover"], "if": spelling}),
                    f"{spelling!r} is the literal both requirements admit",
                )

    def test_always_is_refused_on_a_job_declaring_no_dependency(self) -> None:
        """SPECIFIED -- "and only on a job declaring `needs:`". The allowance is
        argued from a dependent job being skipped when a dependency fails; on a
        job with no dependencies it buys nothing an absent key does not."""
        self.assertFalse(job_condition_is_admissible({"if": "always()"}))

    def test_every_other_condition_is_refused(self) -> None:
        """SPECIFIED -- "No other expression is permitted by it, and neither is
        `always()` joined to anything"."""
        for spelling in (
            "github.event_name == 'pull_request'",
            "always() && github.event_name == 'pull_request'",
            "${{ always() && steps.changes.outputs.terraform == 'true' }}",
            "success() || failure()",
            "!cancelled()",
            "true",
        ):
            with self.subTest(condition=spelling):
                self.assertFalse(
                    job_condition_is_admissible({"needs": ["discover"], "if": spelling}),
                    f"{spelling!r} was admitted; only the bare literal `always()` is",
                )


class TestSavedPlanIsWhatGetsApplied(unittest.TestCase):
    """MODIFIED requirement: Gated Production Apply Applies the Reviewed Plan.

    Regression guards for scenarios the delta carries through unchanged.

    RE-EXPRESSED BY `make-the-pipeline-environment-agnostic`, not weakened.
    Three of these located the apply job by `environment == "production"`, a
    literal that change removes from the workflow -- the delta forbids a
    workflow to "map an environment to its ... Environment name in workflow
    text", so the old locator finds zero jobs and its assertion fails for a
    reason that is the change working. Each now reads the shape the delta
    describes instead: EVERY apply job declares an `environment:`, no plan job
    declares one, each apply job depends on a job that plans, and each applies a
    saved plan rather than recomputing one.
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(APPLY)
        self.jobs = jobs(self.workflow)

    def _jobs_running(self, pattern: str) -> list:
        return [
            name
            for name, job in sorted(self.jobs.items())
            if any(
                re.search(pattern, str(step.get("run", "")))
                for step in (job.get("steps") or [])
            )
        ]

    def _declared_environment(self, job: dict):
        value = job.get("environment")
        if isinstance(value, dict):
            return value.get("name")
        return value

    def test_every_apply_job_is_gated_on_a_github_environment(self) -> None:
        """SPECIFIED -- scenarios "Merge does not apply immediately" and "Apply
        credentials are inaccessible before approval", read over the shape the
        delta states: "Every environment's apply job SHALL declare an
        `environment:`", resolved from that environment's own declaration rather
        than named here.

        Replaces `test_exactly_one_job_declares_the_production_environment`,
        whose count of one was a fact about there being one environment rather
        than a property of the pipeline.
        """
        applying = self._jobs_running(r"terraform\s+apply\b")
        self.assertTrue(applying, "no job in apply.yml runs `terraform apply`")
        offenders = [
            name for name in applying if self._declared_environment(self.jobs[name]) is None
        ]
        self.assertEqual(
            [],
            offenders,
            "these jobs run `terraform apply` and declare no `environment:`, so a "
            f"write-capable Hetzner token lives in an ungated job: {offenders}",
        )
        literal = [
            f"{name}: {self._declared_environment(self.jobs[name])}"
            for name in applying
            if "${{" not in str(self._declared_environment(self.jobs[name]))
        ]
        self.assertEqual(
            [],
            literal,
            "these apply jobs name their GitHub Environment as a literal rather than "
            f"resolving it from the environment's own declaration: {literal}",
        )

    def test_the_planning_job_declares_no_environment(self) -> None:
        """SPECIFIED -- "A **plan job** that declares no `environment:`". This is
        what keeps the read-write token out of the pre-approval job."""
        planning = self._jobs_running(r"terraform\s+plan\b")
        self.assertTrue(planning, "no job in apply.yml runs `terraform plan`")
        offenders = [name for name in planning if "environment" in self.jobs[name]]
        self.assertEqual([], offenders, f"planning jobs declaring `environment:`: {offenders}")

    def test_the_apply_job_depends_on_the_planning_job(self) -> None:
        """SPECIFIED -- "An **apply job** that depends on the plan job"."""
        applying = self._jobs_running(r"terraform\s+apply\b")
        planning = set(self._jobs_running(r"terraform\s+plan\b"))
        self.assertTrue(applying, "no job in apply.yml runs `terraform apply`")
        self.assertTrue(planning, "no job in apply.yml runs `terraform plan`")
        offenders = []
        for name in applying:
            needs = self.jobs[name].get("needs") or []
            needs = [needs] if isinstance(needs, str) else list(needs)
            if not set(map(str, needs)) & planning:
                offenders.append(f"{name}: needs {needs}")
        self.assertEqual(
            [],
            offenders,
            "these apply jobs depend on no job that plans, so nothing guarantees the "
            f"reviewer had a diff to read before approving: {offenders}",
        )

    def test_the_apply_job_applies_a_saved_plan_file(self) -> None:
        """SPECIFIED -- scenario "Applied changes match the approved plan": the
        apply job "SHALL apply the saved `tfplan` artifact produced by the plan
        job", rather than recomputing a plan after approval."""
        applying = self._jobs_running(r"terraform\s+apply\b")
        self.assertTrue(applying, "no job in apply.yml runs `terraform apply`")
        for name in applying:
            job = self.jobs[name]
            commands = [
                str(step.get("run"))
                for step in (job.get("steps") or [])
                if re.search(r"terraform\s+apply\b", str(step.get("run", "")))
            ]
            for command in commands:
                self.assertRegex(
                    command,
                    r"terraform\s+apply\b[^\n]*\btfplan\b",
                    f"job {name} does not apply the saved plan file; a plan recomputed "
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
                f"the approval-gated job {name} recomputes a plan; it must apply the "
                "saved one",
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
        step-level assertion green while reopening the hole.

        THE TWO HALVES DIFFER, and the difference is the requirement's. The STEP
        half is unchanged: no condition of any kind is admitted there. The JOB
        half is re-expressed against the allowance the requirement now carries
        -- "Where the enclosing job declares `needs:` ... it MAY carry the single
        condition `always()` and no other" -- because
        `make-the-pipeline-environment-agnostic` makes this job an aggregator,
        and a dependent job with no `always()` is skipped whenever a dependency
        fails, producing no status check context at all. See
        `job_condition_is_admissible`.
        """
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
            {
                job
                for job, _, _ in self.invoking
                if not job_condition_is_admissible(jobs(self.workflow)[job])
            }
        )
        self.assertEqual(
            [],
            job_offenders,
            "these jobs gate the suite behind a condition the requirement does not "
            "admit -- it admits the single literal `always()`, and only on a job "
            f"declaring `needs:`: {job_offenders}",
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

    # The version-control binary is admitted for one reason and bounded by it:
    # this suite reads the repository's TRACKED files, and the binary that
    # enumerates them exists wherever the repository was obtained at all. That
    # is not a general relaxation -- a tool that must be INSTALLED for the suite
    # to work is a dependency this suite would have to pin and provision, and
    # remains excluded. See `narrow-the-molecule-trigger-to-what-it-reads`,
    # design.md Decision 5.
    SPAWNABLE = {"bash", "sh", "git"}
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
    "ansible/roles/image_prune/tasks/main.yml": "deploy_apps",
}

# The same obligation over an input that is a STRING rather than a list, which
# is why it needs limbs of its own: `is sequence` accepts a string and `is not
# mapping` says nothing useful about one, so the list-shaped set above would
# pass on a value this role cannot use. `image_prune_heartbeat_ping_key` is the
# address the scheduled unit reports its own liveness under, and a converge
# that installed the timer while silently omitting the reporting would leave a
# scheduled unit running unobserved -- the state "Scheduled Host Units Report
# Their Own Liveness" (openspec/specs/iac-host-configuration/spec.md) exists to
# end. An EMPTY key is the case the length limb is for: it is supplied, so `is
# defined` passes, and it builds a URL addressing no check at all.
REQUIRED_STRING_INPUT_ASSERTIONS = {
    "ansible/roles/image_prune/tasks/main.yml": "image_prune_heartbeat_ping_key",
}

REQUIRED_STRING_INPUT_LIMBS = ("is defined", "is string", "| length > 0")

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


class TestRequiredStringRoleInputsAreAssertedBeforeTheRoleActs(unittest.TestCase):
    """ADDED requirement: A Role's Absent Required Input Is Reported by Name,
    reached through Scheduled Host Units Report Their Own Liveness.

    Written by the implementer rather than by the test author of the change
    `notice-when-a-periodic-job-stops-reporting`: covering the new input meant
    editing an existing test's data, which that change's test-plan.md records
    as outside a test author's remit. Its tasks.md 3.2 assigns it here for the
    same reason.
    """

    def _asserted_variables(self, relative_path):
        """Every variable named in an assert that runs before any task acts on
        the host -- the leading run of assertions, and nothing after it."""
        parsed = yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))
        self.assertIsInstance(
            parsed, list, f"{relative_path} did not parse as a task list"
        )
        clauses = []
        for task in parsed:
            if not isinstance(task, dict) or "ansible.builtin.assert" not in task:
                break
            clauses.extend(task["ansible.builtin.assert"].get("that") or [])
        return clauses

    def test_the_assertion_runs_before_any_task_acts_on_the_host(self) -> None:
        """SPECIFIED -- the assertion "SHALL fail naming it, before it changes
        anything on the host". A check placed after the first host-changing
        task leaves a partially configured host behind."""
        for path, variable in REQUIRED_STRING_INPUT_ASSERTIONS.items():
            with self.subTest(role=path):
                clauses = self._asserted_variables(path)
                self.assertTrue(
                    any(variable in clause for clause in clauses),
                    f"{path} does not assert {variable} in its leading run of "
                    "assertions, so either it is not checked at all or a task has "
                    "already changed the host by the time it is",
                )

    def test_the_assertion_carries_every_limb(self) -> None:
        """SPECIFIED -- the absence must be reported by name "rather than with
        an undefined-variable, index, or type error raised by a task that
        consumed it". An empty string is the case the length limb carries: it
        is supplied, so `is defined` passes, and it addresses no check."""
        for path, variable in REQUIRED_STRING_INPUT_ASSERTIONS.items():
            clauses = " ".join(self._asserted_variables(path))
            for limb in REQUIRED_STRING_INPUT_LIMBS:
                with self.subTest(role=path, limb=limb):
                    self.assertIn(
                        f"{variable} {limb}",
                        clauses,
                        f"{path}'s assertion is missing `{variable} {limb}`",
                    )

    def test_no_default_was_introduced_for_the_asserted_variable(self) -> None:
        """SPECIFIED -- a required input "SHALL NOT satisfy this obligation by
        adopting a default value". Here that would be worse than a wrong
        answer: a defaulted key addresses a check nobody watches, so the unit
        reports into nothing while every assertion passes."""
        for path, variable in REQUIRED_STRING_INPUT_ASSERTIONS.items():
            with self.subTest(role=path):
                defaults_path = Path(path).parent.parent / "defaults" / "main.yml"
                defaults = yaml.safe_load(
                    (ROOT / defaults_path).read_text(encoding="utf-8")
                ) or {}
                self.assertNotIn(
                    variable,
                    defaults,
                    f"{defaults_path} now defines {variable}; the role would converge "
                    "on the default and report to a check nobody is watching",
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


# The ONE condition the two unconditionality requirements admit on the job
# enclosing their checks, in either spelling and containing nothing else.
#
# `make-the-pipeline-environment-agnostic` makes `validate` an aggregator over a
# plan matrix, and a job declaring `needs:` is otherwise skipped whenever a
# dependency fails -- producing no status check context at all, which under
# branch protection is a required check that never reports: the same
# permanently-pending state a path filter produces. Both *The Specification
# Record Is Verified in Continuous Integration* and *The Continuous-Integration
# Configuration Is Itself Verified* were amended by that change to admit
# `always()` and nothing else, on the argument that their intent is that the job
# must not be SKIPPABLE and `always()` cannot evaluate false.
#
# Admitted as that exact literal rather than as a class of truthy expressions,
# which is what keeps the closed form those requirements insist on: `always() &&
# <anything>` stays forbidden, and so does `success() || failure()`, which is
# equivalent in most runs and false for a cancelled one.
ADMITTED_JOB_CONDITION = re.compile(r"\A(?:\$\{\{\s*always\(\)\s*\}\}|always\(\))\Z")


def job_condition_is_admissible(job: dict) -> bool:
    """Whether a job's `if:` is one the unconditionality requirements admit.

    No `if:` at all is admissible. `always()` alone is admissible ONLY on a job
    declaring `needs:` -- on a job with no dependencies it buys nothing the
    absent key does not already give, so admitting it there would widen the
    allowance past the argument that justifies it. Everything else is refused.
    """
    condition = job.get("if")
    if condition is None:
        return True
    if not job.get("needs"):
        return False
    return bool(ADMITTED_JOB_CONDITION.match(str(condition).strip()))


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

    # Representative of what the SUITE READS, not of the configuration
    # directory's breadth: a filter narrowed to any one of these subtrees
    # reports a legitimate `false` for a pull request that changed another.
    #
    # Two paths left this tuple when the suite's trigger was narrowed to what
    # its scenarios read, and they are asserted NOT selected below. The whole
    # -directory claim they used to carry now belongs to the lint tier in
    # `pr-validation.yml`, which is triggered without exclusion and is asserted
    # to be, in the module that covers that narrowing. This is not a test
    # weakened to reach green: the proposition changed in the specification and
    # the assertion is re-pointed at what now holds. See the change
    # `narrow-the-molecule-trigger-to-what-it-reads`.
    CONFIGURATION_PATHS = (
        "ansible/roles/some_role/tasks/main.yml",
        "ansible/roles/some_role/molecule/default/molecule.yml",
        "ansible/requirements.yml",
        "ansible/requirements-test.txt",
        "ansible/ansible.cfg",
    )
    # Under `ansible/`, and deliberately NOT selected: no scenario reads them.
    EXCLUDED_CONFIGURATION_PATHS = (
        "ansible/playbooks/host-baseline.yml",
        "ansible/inventory/prod.hcloud.yml",
        "ansible/inventory/group_vars/prod.yml",
        "ansible/requirements.txt",
        "ansible/.envrc.example",
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
        # NEGATION-AWARE, and it has to be: `any(...)` over every declared
        # pattern cannot see a negation at all, so the positive `ansible/**`
        # would keep this check green while the filter excluded these paths --
        # an assertion stating the opposite of the requirement, structurally
        # incapable of failing on it.
        still_selected = [
            path for path in self.EXCLUDED_CONFIGURATION_PATHS if _selects(patterns, path)
        ]
        self.assertEqual(
            [],
            still_selected,
            f"the change filter's patterns {patterns} still select these paths under "
            f"ansible/, which no scenario reads: {still_selected}. The suite would go "
            "on converging seven roles in containers for pull requests it has nothing "
            "to say about",
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
        # Known hole, deliberately left. An anonymous volume is keyed on
        # its target alone, so two services each declaring `- /data` would
        # collapse into one entry, and classifying either would silently
        # classify the other. Unreachable today -- the stack declares no
        # anonymous volume at all -- and closing it changes the shape of
        # this identifier, which a derived test asserts. Left for whoever
        # adds the first one.
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
    # `"/".rstrip("/") + "/"` is `"/"`, which every absolute path starts with,
    # so without the emptiness guard a provider path or volume target of `/`
    # would satisfy every containment check while provisioning nothing.
    root = directory.rstrip("/")
    return bool(root) and target.startswith(root + "/")


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
            "      - source: app_config\n        target: /etc/app/app.yml\n"
            "    volumes:\n      - configured_data:/data\n",
            extra=(
                "configs:\n  app_config:\n    content: |\n      key: value\n"
                "volumes:\n  configured_data:\n"
            ),
        )
        self.assertEqual(
            ["configured_data (configured -> /data)"],
            unclassified_stack_declared_stores(fixture),
            "the config mount was counted as a store, or the volume beside it "
            "was missed. The service carries both deliberately: with only a "
            "`configs:` block the census would return [] whether or not it "
            "distinguished the two, and the test would pass for the wrong "
            "reason",
        )

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


# --------------------------------------------------------------------------
# iac-safety-hardening / Automated Dependency Updates -- the `docker-compose`
# ecosystem
#
# Derived from the delta specs of the OpenSpec change
# `cover-platform-images-with-dependabot`, before any implementation of that
# change existed. The requirement is held in
# `openspec/specs/iac-safety-hardening/spec.md`; the requirement its bumps stay
# subject to, *Shared-Stack Service Images Are Pinned to an Exact Release*, is
# held in `openspec/specs/iac-platform-services/spec.md`. See that change's
# test-plan.md for the scenario-to-test mapping, the baseline, and the
# scenarios deliberately left uncovered.
#
# These assertions live in THIS suite rather than in `terraform test` or in a
# Molecule scenario because every one of them is a static read of a committed
# file: `.github/dependabot.yml` compared against the Compose files the tree
# holds (AGENTS.md, "Testing"). None needs a network call, a credential, a
# container runtime or a Terraform binary, and none adds an import: the
# wildcard matcher below is written with `re`, which this suite already uses.
#
# WHAT THIS SECTION CANNOT SEE
# ----------------------------
# That Dependabot in fact opens a pull request. That is the behaviour of a
# service outside this repository, and no static read reaches it -- the same
# boundary the `terraform` and `github-actions` assertions above already
# accept. And whether a proposed image declares a persistent store the current
# one does not: that is declared by the image rather than by the stack
# definition, so establishing it means a registry call, which this suite
# forbids itself and asserts that it forbids. The delta spec names that half as
# belonging to review of the pull request; the two README assertions at the end
# of this section are the only static trace of it there can be.
# --------------------------------------------------------------------------

COMPOSE_ECOSYSTEM = "docker-compose"

# The requirement's opening sentence, as the delta widens it: three ecosystems,
# not two.
REQUIRED_ECOSYSTEMS = ("terraform", "github-actions", COMPOSE_ECOSYSTEM)

PLATFORM_DEPLOY = WORKFLOWS / "platform-deploy.yml"
GATED_DEPLOY_ENVIRONMENT = "production"

# Dependabot's Docker Compose file fetcher selects by filename, transcribed
# from `dependabot-core`'s `docker/lib/dependabot/docker_compose/file_fetcher.rb`
# as read on 2026-09-08 and quoted in this change's design.md:
#
#     FILENAME_REGEX = /(docker-)?compose(-[\w]+)?(?>\.[\w-]+)?\.ya?ml/i
#
# Two deliberate transcription differences, neither of which changes what this
# pattern accepts or rejects for any filename a repository would carry:
#
#   * the atomic group `(?>...)` is written `(?:...)`. Python's `re` gained
#     atomic grouping only in 3.11 and this suite states 3.9+ as its floor. The
#     `?` quantifier sits OUTSIDE the group in both spellings, so "skip the
#     group entirely" is reachable either way; atomicity would only forbid
#     `[\w-]+` giving characters back, and giving them back never produces a
#     match here because what follows is a literal `.`.
#   * Ruby's `match?` is unanchored, so `re.search` is used rather than
#     `re.fullmatch` -- the pattern matches any name CONTAINING it, which is
#     why `docker-compose.yml.bak` matches and a check anchoring the pattern
#     would be narrower than the fetcher it models.
COMPOSE_FILENAME_PATTERN = re.compile(
    r"(docker-)?compose(-[\w]+)?(?:\.[\w-]+)?\.ya?ml", re.IGNORECASE
)

# The two services deliberately left out of the monitoring group: the reverse
# proxy that terminates TLS for every public hostname, and the one stateful
# service (design.md Decision 4, "the split is by blast radius"). Written as
# Dependabot dependency names -- an image reference with its tag stripped --
# because that, not the Compose service key, is what a group's patterns are
# matched against.
UNGROUPED_DEPENDENCIES = ("traefik", "postgres")

# The vocabulary the README passage required by this change is matched on. As
# with the credential-runbook assertions above, the OBLIGATION is specified and
# the WORDS are derived: a prose sentence has no other static form, and this
# check may read nothing but the committed file.
STACK_REFRESH_VOCABULARY = ("dependabot", COMPOSE_ECOSYSTEM, "image")
STORE_REVIEW_VOCABULARY = ("volume", "persistent store", "backup")


def fetcher_matches_filename(name: str) -> bool:
    """Whether Dependabot's Compose file fetcher would select this filename."""
    return COMPOSE_FILENAME_PATTERN.search(name) is not None


def declares_a_service_image(document: object) -> bool:
    """The SHAPE rule that decides whether a file is a stack definition owing
    coverage: a top-level `services:` mapping at least one of whose entries
    declares an `image:`.

    Content decides this, never the filename. Dependabot's own filename pattern
    matches `ansible/roles/geerlingguy.docker/tasks/docker-compose.yml`, which
    is an Ansible task list -- a YAML sequence -- and a stack definition is not
    what it is. Excluding it by path would make this the third rule in this
    suite deciding which content under `ansible/roles/` is this repository's
    own; the shape rule adds none (design.md Decision 2).
    """
    if not isinstance(document, dict):
        return False
    services = document.get("services")
    if not isinstance(services, dict):
        return False
    return any(
        isinstance(definition, dict)
        and isinstance(definition.get("image"), str)
        and definition["image"].strip()
        for definition in services.values()
    )


@functools.lru_cache(maxsize=None)
def compose_shaped_files(root: Path | None = None) -> tuple[Path, ...]:
    """Every file in the tree whose content is a stack definition.

    Walks with this suite's existing `walked_files()` rather than a fresh
    `rglob`, because it prunes the working trees AGENTS.md requires every change
    to take. A naive walk finds a phantom `<worktree>/platform` and reports it
    uncovered from the main working tree (design.md Decision 2, "Which walker").

    This was written while the `terraform` assertion above was still failing
    exactly that way, from an `rglob` this one deliberately did not copy.
    `terraform_lockfile_directories()` has since been moved onto this same
    walker, so the two now agree; that function carries the full account.

    Two consequences of that walker are accepted rather than discovered later:
    it also prunes `openspec/` and `ansible/roles/geerlingguy.docker`, so a
    stack-shaped file under either is outside this assertion's reach. Planning
    artifacts are not deployed, and the Galaxy role drops out on shape anyway.

    Every file is offered to the YAML parser rather than only those with a
    `.yml`/`.yaml` suffix, because it is the shape that decides. A file that
    cannot be decoded or parsed is not a stack definition and is passed over.

    The walk reads untracked files too -- deliberately, since that is the safe
    direction for a coverage obligation, and the same trade `walked_files()`
    already documents. The local-only consequence: an untracked stack-shaped
    scratch file under a name the fetcher does not match (`platform/local.yml`)
    turns this assertion red on a workstation while continuous integration,
    which checks out tracked files only, stays green.

    Cached because the walk parses every file in the tree and several
    assertions call this; the cache is keyed on `root`, so a fixture tree is
    still read on its own.
    """
    found: list[Path] = []
    for path in walked_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        try:
            document = yaml.safe_load(text)
        except yaml.YAMLError:
            continue
        if declares_a_service_image(document):
            found.append(path)
    return tuple(found)


def dependabot_config(config: dict | None = None) -> dict:
    return load_yaml(DEPENDABOT) if config is None else config


def dependabot_updates(config: dict | None = None) -> list:
    return dependabot_config(config).get("updates") or []


def dependabot_ecosystems(config: dict | None = None) -> set:
    return {entry.get("package-ecosystem") for entry in dependabot_updates(config)}


def missing_required_ecosystems(config: dict | None = None) -> list[str]:
    configured = dependabot_ecosystems(config)
    return [name for name in REQUIRED_ECOSYSTEMS if name not in configured]


def configured_directories(ecosystem: str, config: dict | None = None) -> list[str]:
    """Every directory an ecosystem's entries name, by either spelling."""
    directories: list[str] = []
    for entry in dependabot_updates(config):
        if entry.get("package-ecosystem") != ecosystem:
            continue
        if entry.get("directory"):
            directories.append(entry["directory"])
        directories.extend(entry.get("directories") or [])
    return directories


def repository_directory_of(path: Path, root: Path | None = None) -> str:
    base = ROOT if root is None else root
    relative = path.parent.relative_to(base).as_posix()
    return "/" if relative == "." else "/" + relative


def compose_coverage_offences(
    root: Path | None = None, config: dict | None = None
) -> list[str]:
    """Every stack definition in the tree the committed configuration cannot
    reach, on either of the two conditions the fetcher applies.

    Both conditions are necessary because the fetcher applies both: it lists
    the configured directory and selects entries whose NAME matches its
    filename pattern, and it does not recurse. A file failing either is not
    partially covered -- it is uncovered, while every configured entry goes on
    reporting success. The two failures are reported distinguishably, because
    the filename one is the harder to notice: the directory holding it is named
    and green.
    """
    directories = configured_directories(COMPOSE_ECOSYSTEM, config)
    base = ROOT if root is None else root
    offences = []
    for path in compose_shaped_files(root):
        relative = path.relative_to(base).as_posix()
        directory = repository_directory_of(path, root)
        if not any(gh_glob_matches(pattern, directory) for pattern in directories):
            offences.append(
                f"{relative}: sits in {directory}, which no `{COMPOSE_ECOSYSTEM}` "
                f"entry names (configured: {sorted(directories)})"
            )
        elif not fetcher_matches_filename(path.name):
            offences.append(
                f"{relative}: sits in a configured directory under a name the "
                f"fetcher's filename pattern does not match, so it is never "
                f"fetched and the directory's own success says nothing about it"
            )
    return offences


def dependency_name(image: str) -> str:
    """The name Dependabot matches a group's patterns against: the image
    reference with its tag, its digest AND ITS REGISTRY HOST stripped.

    NOT the Compose service key. The two differ for all six monitoring images,
    which is why a group written in service names would match nothing at all
    rather than merely under-match, leaving the grouping inert with nothing red
    to say so.

    AND NOT the reference as written, either. `dependabot-core`'s
    `shared_file_parser.rb` builds the dependency as
    `Dependency.new(name: details.fetch("image"), ..., source:
    source_from(details))` -- the `image` capture group alone. The registry is
    carried in the requirement's `source`, never in the name. So
    `quay.io/prometheuscommunity/postgres-exporter:v0.17.1` is the dependency
    `prometheuscommunity/postgres-exporter`.

    This function asserted the opposite until 2026-09-08 and the configuration
    agreed with it, because both were written from the same wrong reading of an
    external system. `cover-platform-images-with-dependabot` shipped two
    registry-prefixed patterns that matched nothing; the suite stayed green,
    having established only that the check and the config shared an
    assumption. Dependabot's first run said otherwise, opening
    `prometheuscommunity/postgres-exporter` as its own pull request outside the
    group. `OBSERVED_DEPENDENCY_NAMES` below is anchored to that run so this
    cannot be re-derived from a reading of the docs alone.

    WHAT IS OBSERVED HERE AND WHAT IS STILL INFERRED
    ------------------------------------------------
    Of the registry-bearing images this stack declares, only the `quay.io` one
    has been seen in a Dependabot pull request -- `ghcr.io/google/cadvisor`
    opened none, because v0.60.5 was current. So "a host-looking first segment
    is stripped" is OBSERVED for `quay.io` and INFERRED for everything else,
    `ghcr.io`, a `host:port` and a bare `localhost` included. Add cadvisor's
    pair below the first time Dependabot names it, rather than treating the
    inference as settled.

    One known divergence, hypothetical for this repository. The test below is
    `"." in head`, which accepts a dotted-quad address, so `10.0.0.1/img` reads
    here as registry + `img`. `dependabot-core`'s own registry pattern is
    reported to require an alphabetic top-level domain and would keep the
    address in the name. Nothing in `platform/docker-compose.yml` is addressed
    that way. It is recorded rather than coded around because a narrower test
    written from another unverified reading is exactly what produced the defect
    this function exists to document.
    """
    repository = parse_image_reference(image)[0]
    head, _, rest = repository.partition("/")
    if rest and ("." in head or ":" in head or head == "localhost"):
        return rest
    return repository


def pattern_matches_dependency(pattern: str, name: str) -> bool:
    """A Dependabot group pattern against a dependency name.

    The semantics Dependabot documents for these patterns: `*` matches any run
    of characters INCLUDING `/`, `?` matches one, and matching is
    case-insensitive. Distinct from `gh_glob_matches` above, whose `*` stops at
    a `/` because a GitHub Actions path filter says so -- a difference that
    matters here, since every dependency name but two carries a `/`.

    That this repository's committed patterns select what they are meant to
    under those semantics is what the assertions below establish; that
    Dependabot applies them is behaviour of a service outside this repository
    and is not established here.
    """
    regex = ""
    for char in pattern:
        if char == "*":
            regex += ".*"
        elif char == "?":
            regex += "."
        else:
            regex += re.escape(char)
    return re.fullmatch(regex, name, re.IGNORECASE) is not None


def group_patterns(ecosystem: str, config: dict | None = None) -> list[str]:
    """Every pattern under every `groups:` entry for an ecosystem, whatever the
    groups are named -- the assertions are about which dependencies the
    committed patterns select, not about a group's name."""
    patterns: list[str] = []
    for entry in dependabot_updates(config):
        if entry.get("package-ecosystem") != ecosystem:
            continue
        for group in (entry.get("groups") or {}).values():
            if isinstance(group, dict):
                patterns.extend(group.get("patterns") or [])
    return patterns


def stack_dependency_names(path: Path | None = None) -> dict:
    """service -> dependency name, over the shared stack's declared images."""
    return {
        service: dependency_name(image)
        for service, image in compose_service_images(path)
        if image is not None
    }


def dependencies_matched_by(patterns, names) -> set:
    return {
        name
        for name in names
        if any(pattern_matches_dependency(pattern, name) for pattern in patterns)
    }


class ComposeTreeFixtureMixin:
    """Builds throwaway trees the coverage check is run over, and throwaway
    Dependabot configurations to run it against.

    The committed tree holds exactly one stack definition, in the one directory
    the configuration will name, so the assertion over the tree passes
    identically whether the check reads both of the fetcher's conditions or only
    the directory -- which is the precise silent uncoverage this change exists
    to prevent, reproduced inside the check meant to prevent it. These fixtures
    are what make the check's verdict depend on the file.
    """

    TASK_LIST = (
        "---\n"
        "- name: Install docker-compose\n"
        "  ansible.builtin.package:\n"
        "    name: docker-compose\n"
    )
    STACK = "---\nservices:\n  traefik:\n    image: traefik:v3.7.10\n"

    def compose_tree(self, files: dict) -> Path:
        root = Path(tempfile.mkdtemp(prefix="compose-coverage-fixture-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for relative, body in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        return root

    def config_naming(self, *directories: str) -> dict:
        return {
            "version": 2,
            "updates": [
                {
                    "package-ecosystem": COMPOSE_ECOSYSTEM,
                    "directories": list(directories),
                    "schedule": {"interval": "weekly"},
                }
            ],
        }

    def discovered_in(self, files: dict) -> list[str]:
        root = self.compose_tree(files)
        return sorted(
            path.relative_to(root).as_posix() for path in compose_shaped_files(root)
        )

    def offences_over(self, files: dict, *directories: str) -> list[str]:
        root = self.compose_tree(files)
        return compose_coverage_offences(root, self.config_naming(*directories))


class TestDependabotWatchesEveryRequiredEcosystem(unittest.TestCase):
    """MODIFIED requirement: Automated Dependency Updates."""

    def test_dependabot_configures_every_required_ecosystem(self) -> None:
        """SPECIFIED -- the requirement's opening sentence as this change
        amends it: `terraform`, `github-actions` AND `docker-compose`. It is
        the enabling condition for the "Provider version update", "Action
        version update" and "Platform image update" scenarios, and establishes
        none of their outcomes -- see the test plan.

        This superseded `TestDependabotCoverage
        .test_dependabot_configures_both_required_ecosystems`, whose name
        asserted "both" and whose body iterated that literal pair -- false of
        three. That method was removed by this change's implementation
        commit; a note stands in its place. This assertion is a strict
        superset of it, and is paired with a discrimination test below.
        """
        missing = missing_required_ecosystems()
        self.assertEqual(
            [],
            missing,
            f"no Dependabot entry for these required ecosystems: {missing}",
        )

    def test_the_ecosystem_check_reads_the_configuration(self) -> None:
        """DERIVED -- no scenario states it. Without it the test above passes
        identically whether it reads the file or enumerates nothing, and it
        will keep passing once the stanza lands. Runs the same check over a
        configuration that omits the new ecosystem."""
        without = {
            "version": 2,
            "updates": [
                {"package-ecosystem": "terraform", "directory": "/terraform"},
                {"package-ecosystem": "github-actions", "directory": "/"},
            ],
        }
        self.assertEqual([COMPOSE_ECOSYSTEM], missing_required_ecosystems(without))


class TestEveryComposeFileDeclaringAServiceImageIsCovered(unittest.TestCase):
    """MODIFIED requirement: Automated Dependency Updates."""

    def test_the_tree_holds_a_stack_definition_at_all(self) -> None:
        """SPECIFIED -- the non-vacuity guard the requirement's own reasoning
        demands, mirroring the `terraform` lockfile assertion's. A comparison
        over an empty discovery would report full coverage of nothing."""
        discovered = compose_shaped_files()
        self.assertTrue(
            discovered,
            "no file in the tree declares a top-level `services:` mapping with an "
            "`image:`, so the coverage comparison below would pass having read "
            "nothing",
        )

    def test_the_shared_platform_stack_is_among_the_files_discovered(self) -> None:
        """SPECIFIED -- the requirement covers "every Compose file in the
        repository that declares a service image", and `platform/` holds the
        stack whose staleness this change exists to signal. Discovery that
        missed it would leave every assertion below vacuous."""
        discovered = {path.resolve() for path in compose_shaped_files()}
        self.assertIn(
            PLATFORM_COMPOSE.resolve(),
            discovered,
            "the shared platform stack was not discovered as a stack definition, so "
            "the coverage assertion below says nothing about the eight images it pins",
        )

    def test_every_compose_file_declaring_a_service_image_is_covered(self) -> None:
        """SPECIFIED -- scenario "Every Compose file declaring a service image
        is covered": every such file "SHALL sit in a directory that
        configuration names, AND SHALL carry a name the fetcher matches", and
        one failing either condition "SHALL be reported as uncovered, rather
        than the configured entries' own success being read as coverage of the
        repository"."""
        self.test_the_tree_holds_a_stack_definition_at_all()
        offences = compose_coverage_offences()
        self.assertEqual(
            [],
            offences,
            "these stack definitions are not reachable by the committed "
            f"`{COMPOSE_ECOSYSTEM}` configuration: {offences}",
        )

    def test_every_configured_directory_holds_a_file_the_fetcher_selects(self) -> None:
        """DERIVED -- the converse of the assertion above, and the one failure
        the delta's scenarios do not name.

        The assertion above walks tree -> configuration: every stack definition
        must be reachable. Nothing there walks configuration -> tree, and the
        fetcher makes that direction fail hard rather than silently: it
        `raise_appropriate_error`s when the configured directory holds no file
        matching its filename pattern ("Repo must contain a docker-compose.yaml
        file."). A directory named here that holds none -- a stanza added for a
        path that does not exist yet, a `directories:` entry left behind after a
        stack moved -- errors on every Dependabot run, opens no pull request,
        and leaves this suite entirely green.

        That is the mechanism design.md Decision 1 rests on when it argues
        `directory: "/"` would fail rather than scan, so it is asserted here
        rather than only reasoned about. Matching the fetcher, the listing is
        of the directory itself and does not descend.
        """
        empty = []
        for directory in configured_directories(COMPOSE_ECOSYSTEM):
            resolved = ROOT / directory.lstrip("/")
            if not resolved.is_dir():
                empty.append(f"{directory} (no such directory)")
                continue
            if not any(
                entry.is_file() and fetcher_matches_filename(entry.name)
                for entry in resolved.iterdir()
            ):
                empty.append(f"{directory} (no file the fetcher would select)")
        self.assertEqual(
            [],
            empty,
            f"the `{COMPOSE_ECOSYSTEM}` ecosystem names directories the fetcher would "
            f"error on rather than read, so it opens no pull request at all: {empty}",
        )


class TestTheComposeCoverageCheckIsARealReadOfTheTree(
    ComposeTreeFixtureMixin, unittest.TestCase
):
    """MODIFIED requirement: Automated Dependency Updates.

    The assertion over the committed tree has one file to read, in the one
    directory the configuration names. These tests run the same check over
    throwaway trees differing in exactly one property, so its verdict is shown
    to depend on what a file is and where it sits.
    """

    def test_a_task_list_under_a_matching_name_is_not_a_stack_definition(self) -> None:
        """SPECIFIED -- "What decides that a file is a stack definition owing
        coverage is its content -- a top-level service mapping declaring an
        image". `ansible/roles/geerlingguy.docker/tasks/docker-compose.yml` is
        an Ansible task list whose name Dependabot's own pattern matches; the
        shape rule is what excludes it, and no path exclusion is added.

        The committed tree cannot demonstrate this: the walker prunes that role
        by path before the shape rule is consulted, so an assertion made over
        the tree alone could not fail.
        """
        self.assertEqual(
            [], self.discovered_in({"tasks/docker-compose.yml": self.TASK_LIST})
        )

    def test_a_services_mapping_declaring_no_image_is_not_a_stack_definition(self) -> None:
        """DERIVED -- the shape rule's second limb ("declaring an image") has no
        instance in the committed tree either. A file Dependabot would find
        nothing to update in owes no coverage."""
        imageless = "---\nservices:\n  built:\n    build: .\n"
        self.assertEqual(
            [], self.discovered_in({"platform/docker-compose.yml": imageless})
        )

    def test_a_stack_definition_is_discovered_whatever_it_is_named(self) -> None:
        """SPECIFIED -- "the fetcher's filename pattern SHALL be used only to
        decide whether a file so identified can be reached, never to decide
        whether a file is a stack definition at all". A discovery that filtered
        by name first could never report scenario "A stack file the fetcher's
        name pattern does not match is reported"."""
        self.assertEqual(
            ["platform/stack.yml"],
            self.discovered_in({"platform/stack.yml": self.STACK}),
        )

    def test_a_stack_file_the_filename_pattern_does_not_match_is_reported(self) -> None:
        """SPECIFIED -- scenario "A stack file the fetcher's name pattern does
        not match is reported": a stack definition in a directory the ecosystem
        names, under a name the pattern does not match, "SHALL be reported as
        uncovered, because the configured directory's own success says nothing
        about a file within it that is never fetched"."""
        offences = self.offences_over({"platform/stack.yml": self.STACK}, "/platform")
        self.assertEqual(1, len(offences), f"expected one offence, got {offences}")
        self.assertIn("platform/stack.yml", offences[0])
        self.assertIn("filename pattern", offences[0])

    def test_a_stack_file_in_a_directory_the_configuration_omits_is_reported(self) -> None:
        """SPECIFIED -- the first of the scenario's two conditions. The fetcher
        lists the configured directory only and does not descend, so a second
        stack at `platform/monitoring/docker-compose.yml` is not partially
        covered by the `/platform` entry: it is uncovered, silently, with that
        entry still green."""
        offences = self.offences_over(
            {
                "platform/docker-compose.yml": self.STACK,
                "platform/monitoring/docker-compose.yml": self.STACK,
            },
            "/platform",
        )
        self.assertEqual(1, len(offences), f"expected one offence, got {offences}")
        self.assertIn("platform/monitoring/docker-compose.yml", offences[0])
        self.assertIn("entry names", offences[0])

    def test_a_stack_file_meeting_both_conditions_is_accepted(self) -> None:
        """DERIVED -- the converse half. Without it a check reporting every file
        it found would satisfy both tests above while failing any change to the
        tree regardless of what it changed."""
        self.assertEqual(
            [],
            self.offences_over({"platform/docker-compose.yml": self.STACK}, "/platform"),
        )

    def test_a_directory_pattern_is_read_as_a_glob(self) -> None:
        """DERIVED -- from Dependabot's `directories:` accepting globs, which
        design.md Decision 1 declines to use but the committed configuration
        may later. A check treating a pattern as a literal would report a file
        a glob entry does cover."""
        self.assertEqual(
            [],
            self.offences_over(
                {"platform/docker-compose.yml": self.STACK}, "/platform*"
            ),
        )


class TestTheFetcherFilenamePatternIsTranscribedFaithfully(unittest.TestCase):
    """MODIFIED requirement: Automated Dependency Updates.

    DERIVED throughout -- no scenario states these names. The whole force of
    the filename condition rests on this transcription of a regular expression
    read out of `dependabot-core` on a particular day (design.md, "Context"),
    and a transcription error would silently move the boundary the two
    scenarios above are written about: too narrow reports a covered file as
    uncovered, too wide passes a file that is never fetched.
    """

    MATCHED = (
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "compose-prod.yml",
        "docker-compose.override.yml",
    )
    UNMATCHED = (
        "stack.yml",
        "monitoring.yml",
        "platform.yaml",
        "docker-compose.json",
        "values.yaml",
    )

    def test_the_names_the_fetcher_selects_are_matched(self) -> None:
        rejected = [name for name in self.MATCHED if not fetcher_matches_filename(name)]
        self.assertEqual(
            [],
            rejected,
            f"the fetcher would fetch these; the pattern rejects them: {rejected}",
        )

    def test_the_names_the_fetcher_passes_over_are_not_matched(self) -> None:
        accepted = [name for name in self.UNMATCHED if fetcher_matches_filename(name)]
        self.assertEqual(
            [],
            accepted,
            "the pattern accepts these names, so a stack definition under one of them "
            f"would be reported covered while never being fetched: {accepted}",
        )


class TestDependencyNamingMatchesWhatDependabotActuallyDid(unittest.TestCase):
    """DERIVED -- no scenario states it, and it exists because its absence let a
    defect ship.

    `cover-platform-images-with-dependabot` grouped six monitoring images and
    asserted the grouping. Two of its patterns carried a registry host
    (`quay.io/...`, `ghcr.io/...`) and matched nothing, because Dependabot's
    dependency name excludes the registry. The assertion passed anyway: it
    computed expected names with the same helper the configuration had been
    written from, so it established that the check and the config agreed --
    never that either matched Dependabot.

    A test derived from a belief about an external system can only be anchored
    by an observation of that system. These pairs are transcribed from the pull
    requests Dependabot opened against this repository on 2026-09-08, the first
    run after that change merged, and each is quoted with the title it came
    from. Replace one only against a newer observation, never against a reading
    of the documentation.
    """

    # (image as `platform/docker-compose.yml` writes it, dependency name
    #  Dependabot used) -- from the titles and bodies of these pull requests:
    #
    #   #92 "Bump prometheuscommunity/postgres-exporter from v0.17.1 to v0.20.1
    #        in /platform"                    <- registry host absent
    #   #91 "Bump postgres from 16.15 to 18.6 in /platform"
    #   #90 "Bump traefik from v3.7.10 to v3.7.13 in /platform"
    #   #89 "Bumps the platform-monitoring-images group in /platform with 4
    #        updates: prom/node-exporter, prom/prometheus, prom/alertmanager
    #        and grafana/grafana."
    OBSERVED_DEPENDENCY_NAMES = (
        ("quay.io/prometheuscommunity/postgres-exporter:v0.17.1", "prometheuscommunity/postgres-exporter"),
        ("postgres:16.15", "postgres"),
        ("traefik:v3.7.10", "traefik"),
        ("prom/node-exporter:v1.9.1", "prom/node-exporter"),
        ("prom/prometheus:v3.7.3", "prom/prometheus"),
        ("prom/alertmanager:v0.28.1", "prom/alertmanager"),
        ("grafana/grafana:12.3.0", "grafana/grafana"),
    )

    def test_the_helper_reproduces_every_observed_dependency_name(self) -> None:
        """The anchor. Every pair here was read off a real Dependabot pull
        request rather than inferred."""
        wrong = {
            image: dependency_name(image)
            for image, observed in self.OBSERVED_DEPENDENCY_NAMES
            if dependency_name(image) != observed
        }
        self.assertEqual(
            {},
            wrong,
            "the dependency-name helper disagrees with the names Dependabot used in "
            f"pull requests it actually opened: {wrong}. Every group pattern is "
            "matched through this helper, so a disagreement here means the committed "
            "patterns are asserted against names that do not exist",
        )

    def test_a_registry_prefixed_pattern_is_shown_not_to_match(self) -> None:
        """The specific defect, kept as a regression rather than only as prose.
        `ghcr.io/google/cadvisor` produced no pull request on 2026-09-08 only
        because v0.60.5 was current, so this failure mode was invisible in the
        observation above and is pinned here instead."""
        self.assertEqual(
            set(),
            dependencies_matched_by(
                ["ghcr.io/google/cadvisor", "quay.io/prometheuscommunity/postgres-exporter"],
                {dependency_name("ghcr.io/google/cadvisor:v0.60.5"),
                 dependency_name("quay.io/prometheuscommunity/postgres-exporter:v0.17.1")},
            ),
            "a registry-prefixed pattern now reads as matching, so the assertion that "
            "caught this defect would no longer catch it",
        )


class TestTheImageGroupSplitsByBlastRadius(unittest.TestCase):
    """MODIFIED requirement: Automated Dependency Updates.

    DERIVED throughout -- the grouping is design.md Decision 4, and no scenario
    states it. It is asserted rather than left to inspection because both of
    its failure modes are silent: a group written in Compose service names
    matches no dependency at all and is simply inert, and an over-broad
    `postgres*` pulls the shared database into a group whose whole purpose is
    to keep it out. Neither is visible in a diff that reads plausibly.
    """

    def setUp(self) -> None:
        self.names = stack_dependency_names()
        self.patterns = group_patterns(COMPOSE_ECOSYSTEM)

    def test_the_stack_declares_the_two_dependencies_left_ungrouped(self) -> None:
        """DERIVED -- the non-vacuity guard. With neither name present, the
        assertion that no pattern matches them passes over an empty set."""
        missing = [
            name for name in UNGROUPED_DEPENDENCIES if name not in self.names.values()
        ]
        self.assertEqual(
            [],
            missing,
            f"the shared stack declares no image whose dependency name is {missing}, so "
            "the blast-radius split below is asserted over a service that is not there",
        )

    def test_the_ecosystem_declares_a_group_at_all(self) -> None:
        """DERIVED -- second non-vacuity guard: with no patterns configured,
        every assertion below is true of the empty set."""
        self.assertTrue(
            self.patterns,
            f"the `{COMPOSE_ECOSYSTEM}` ecosystem declares no `groups:` patterns, so a "
            "routine week opens one pull request per image and each merge runs its own "
            "gated production deploy",
        )

    def test_no_group_pattern_matches_the_database_or_the_reverse_proxy(self) -> None:
        """DERIVED -- design.md Decision 4: "No pattern may match `postgres` or
        `traefik`". Traefik terminates TLS for every public hostname and
        PostgreSQL is the one stateful service; each is meant to reach the
        deploy approver as its own diff. `postgres*` -- the decision's own
        rejected alternative arrived at by a typo -- is caught here."""
        self.test_the_ecosystem_declares_a_group_at_all()
        caught = sorted(dependencies_matched_by(self.patterns, UNGROUPED_DEPENDENCIES))
        self.assertEqual(
            [],
            caught,
            f"these are grouped with the monitoring images: {caught}; patterns: "
            f"{sorted(self.patterns)}",
        )

    def test_the_patterns_select_every_other_image_the_stack_declares(self) -> None:
        """DERIVED -- the converse half, and the one that catches an inert
        group: patterns written as Compose service names match nothing, which
        the test above would accept. Expected membership is computed from the
        stack rather than enumerated here, so a monitoring service added later
        must be grouped or must be argued about."""
        self.test_the_ecosystem_declares_a_group_at_all()
        expected = {
            name for name in self.names.values() if name not in UNGROUPED_DEPENDENCIES
        }
        matched = dependencies_matched_by(self.patterns, set(self.names.values()))
        self.assertEqual(
            expected,
            matched,
            "the committed group patterns do not select exactly the stack's images "
            f"other than {list(UNGROUPED_DEPENDENCIES)}; patterns: {sorted(self.patterns)}",
        )

    def test_the_group_check_reads_the_patterns(self) -> None:
        """DERIVED -- discrimination. Runs the same matcher over the rejected
        alternative, so the assertion above is shown to depend on what is
        written rather than on the check knowing the answer."""
        self.assertEqual(
            {"postgres"},
            dependencies_matched_by(["postgres*"], UNGROUPED_DEPENDENCIES),
            "`postgres*` no longer reads as matching the shared database, so the "
            "assertion above would not catch the typo it exists for",
        )
        self.assertEqual(
            set(),
            dependencies_matched_by(
                ["prometheus", "grafana"], {"prom/prometheus", "grafana/grafana"}
            ),
            "patterns written as Compose service names read as matching dependency "
            "names, so an inert group would pass the assertion above",
        )


class TestAProposedImageUpdateIsNotExemptFromTheStacksObligations(unittest.TestCase):
    """MODIFIED requirement: Automated Dependency Updates.

    Scenario "A proposed image update is not exempt from the stack's own
    obligations". Its first limb is decidable statically only as an enabling
    condition -- that the file this ecosystem proposes changes to is the file
    the pinning floor check reads, and that a merge of such a change still
    passes the deploy gate. Its second limb, whether a bumped image declares a
    persistent store the current one does not, is decidable by no static read
    of a committed file at all: the store is declared by the image, and reading
    it is a registry call this suite forbids itself.
    """

    def test_the_file_the_pinning_floor_check_reads_is_one_this_ecosystem_covers(self) -> None:
        """SPECIFIED -- "that pull request SHALL pass the pinning requirement's
        automated floor check". The floor check reads
        `platform/docker-compose.yml`; unless that file is one the ecosystem
        can reach, no pull request it opens is subject to it."""
        relative = PLATFORM_COMPOSE.relative_to(ROOT).as_posix()
        offences = [
            offence
            for offence in compose_coverage_offences()
            if offence.startswith(relative)
        ]
        self.assertEqual(
            [],
            offences,
            "the stack the pinning requirement governs is not reachable by the "
            f"`{COMPOSE_ECOSYSTEM}` configuration: {offences}",
        )

    def test_the_stack_deploy_stays_gated_on_the_production_environment(self) -> None:
        """SPECIFIED -- scenario "Platform image update is proposed
        automatically": such a pull request is "subject to ... the same gated
        deploy approval as any other change to the stack definition". This
        change alters no pipeline behaviour; the assertion exists because the
        gate is what makes an automatically proposed bump acceptable, and its
        removal would be invisible to every other test in this suite."""
        workflow = load_yaml(PLATFORM_DEPLOY)
        gated = [
            name
            for name, job in jobs(workflow).items()
            if str(job.get("environment", "")) == GATED_DEPLOY_ENVIRONMENT
            or (
                isinstance(job.get("environment"), dict)
                and job["environment"].get("name") == GATED_DEPLOY_ENVIRONMENT
            )
        ]
        self.assertEqual(
            1,
            len(gated),
            "expected exactly one job in platform-deploy.yml to declare "
            f"`environment: {GATED_DEPLOY_ENVIRONMENT}`, found {gated}",
        )

    def _refresh_sections(self) -> list[str]:
        sections = [
            section
            for section in readme_sections(read_text(README))
            if all(word in section.lower() for word in STACK_REFRESH_VOCABULARY)
        ]
        self.assertTrue(
            sections,
            "no single README section says that the shared stack's image pins are "
            f"refreshed by Dependabot's `{COMPOSE_ECOSYSTEM}` ecosystem, so the one "
            "place a reader learns how each kind of pin stays fresh is silent about "
            "the eight images the host actually runs",
        )
        return sections

    def test_the_readme_says_the_stack_images_are_refreshed_by_this_ecosystem(self) -> None:
        """DERIVED -- from design.md's first risk and this change's tasks, not
        from a scenario. The README's CI/CD section already explains why
        `pre-commit` revisions are refreshed by a workflow rather than by
        Dependabot; leaving image pins unstated there is what makes the next
        reader's model of this repository wrong."""
        self._refresh_sections()

    def test_the_readme_passage_names_the_question_no_check_can_answer(self) -> None:
        """DERIVED for the vocabulary, SPECIFIED for the obligation -- "whether
        the proposed image declares a persistent store the current one does not
        ... SHALL be established by that review".

        Stating it in the specification is necessary and not sufficient: a
        reviewer of a routine version bump does not open `openspec/specs/`
        unprompted. This is the same reasoning the requirement already applies
        to a credential's rotation procedure -- a fact whose only home is the
        change that introduced it becomes undocumented at archive.
        """
        sections = self._refresh_sections()
        self.assertTrue(
            any(
                word in section.lower()
                for section in sections
                for word in STORE_REVIEW_VOCABULARY
            ),
            "the README passage on automatically refreshed image pins does not tell a "
            "reviewer they owe the one question no check in this repository can answer: "
            "whether the proposed image declares a persistent store the current one does "
            "not, per *No Store on This Host Holds Data Requiring Backup*",
        )


# `unittest.main()` stays at the END of this file, not in the middle of it.
# `cover-platform-images-with-dependabot` appended a section after the block's
# previous position and a direct `python3 .github/tests/test_ci_configuration.py`
# then ran 169 tests and reported OK while 23 were never defined -- a check
# reporting success having verified nothing, which is what this suite exists to
# refuse. Continuous integration was unaffected (it uses `unittest discover`),
# which is exactly why nothing caught it. Append below this comment, never
# above it.
# iac-cicd-pipeline / The Specification Record Is Verified in Continuous
# Integration
#
# Derived from the delta spec of the OpenSpec change
# `make-openspec-validation-a-usable-gate`, before any implementation of that
# change existed. The requirement these assertions trace to is
# `iac-cicd-pipeline`'s "The Specification Record Is Verified in Continuous
# Integration" -- which exists only as that change's delta until it is
# archived; its permanent path is openspec/specs/iac-cicd-pipeline/spec.md. See
# that change's test-plan.md for the scenario-to-test mapping, the baseline,
# and the scenarios deliberately left uncovered.
#
# These assertions live in THIS suite rather than in `terraform test` or in a
# Molecule scenario because every one of them is a static read of a committed
# file (AGENTS.md, "Testing"). The delta is explicit that the validating tool
# itself must NOT be run from here: doing so would break this suite's own
# "spawns nothing outside bash/sh" and "stdlib plus pinned dependencies only"
# assertions, and routing it through `bash -c` to evade the AST check is
# recorded as refused in that change's design.md, Decision 5. The division of
# labour is the pipeline's existing one: the workflow runs the tool, and this
# suite asserts statically that the workflow does so, unconditionally, from a
# pinned manifest, without suppressing the result.
#
# `json` is imported here rather than in the header import block so that this
# section is purely additive to a file that was already complete. It is
# standard library, as
# `TestTheSuiteNeedsNoPrivilegedResource
# .test_the_suite_imports_only_the_standard_library_and_pinned_dependencies`
# requires of everything this file imports.
# --------------------------------------------------------------------------

import json

OPENSPEC_MANIFEST = ROOT / ".github" / "package.json"
OPENSPEC_LOCKFILE = ROOT / ".github" / "package-lock.json"
AGENTS_FILE = ROOT / "AGENTS.md"
CHANGES_DIRECTORY_NAME = "changes"

# The npm PACKAGE and the BINARY it installs carry different names, and both
# are load-bearing here. The package is scoped -- `@fission-ai/openspec` -- and
# is what the manifest, the lockfile and Dependabot key on. The executable it
# puts on PATH is plain `openspec`, and is what the workflow's script names.
#
# One constant covering both roles was this author's wrong assumption, found
# while the gate was being implemented: it made the manifest assertions
# unsatisfiable by a CORRECT manifest, whose dependency key must be the scoped
# name -- a test dictating a fact about the world rather than reading one.
#
# The reconciliation deliberately NOT taken is an npm alias
# (`"openspec": "npm:@fission-ai/openspec@1.12.0"`). It would make the literal
# key the old assertion wanted appear, at the cost of bending the manifest to
# fit the test; and the alias string is not an exact version, so
# `EXACT_NPM_VERSION` would then fail on it. `TestThePinMatchersReadTheScoped
# PackageName` pins that refusal so it cannot be quietly reintroduced.
VALIDATING_PACKAGE = "@fission-ai/openspec"
VALIDATING_TOOL = "openspec"
VALIDATING_SUBCOMMAND = "validate"
VALIDATING_FLAGS = ("--all", "--archived")

# The command the step runs must BE the binary the lockfile-exact install
# places, named by a path into that install tree. Not `npx`, and not a bare
# `openspec` resolved off PATH.
#
# `npx` was admitted here on the belief that it resolves the locally installed
# binary. It does not, and this workflow's install is precisely the case where
# it cannot: `npm ci` installs into `.github/node_modules`, and npx searches
# `node_modules/.bin` UPWARD from the working directory, so a `.github` that is
# a child of the repository root is never on that search path. Verified rather
# than reasoned: with the install moved aside, `npx openspec validate --all`
# still exited 0, having resolved from the npx cache. A runner has no cache, so
# the same line resolves off the registry at run time -- the freshly resolved
# dependency the requirement forbids, reached by a line that looks pinned.
#
# A bare `openspec` is refused for the same reason: whatever PATH offers is not
# established to be what the manifest pins.
#
# This is a fact about npx's search, not a preference. The comment it replaces
# asserted the opposite and was wrong; the workflow's own comment records the
# same verification.
NODE_BIN_SEGMENT = "node_modules/.bin"
MANIFEST_DIRECTORY = OPENSPEC_MANIFEST.parent.relative_to(ROOT).as_posix()
INSTALLED_BINARY = f"{MANIFEST_DIRECTORY}/{NODE_BIN_SEGMENT}/{VALIDATING_TOOL}"

NPM_ECOSYSTEM = "npm"
NPM_MANIFEST_NAME = "package.json"

PACKAGE_MANAGERS = frozenset({"npm", "yarn", "pnpm"})
LOCKFILE_EXACT_INSTALL = ("npm", "ci")

EXACT_NPM_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")

SETUP_NODE = "setup-node"
MUTABLE_ACTION_REFS = frozenset({"", "main", "master", "head", "latest", "trunk", "develop"})

MANAGED_BLOCK_END = "<!-- /ai-toolkit:development-workflow -->"

# The rule's own words, because the delta requires the assertion to be written
# "so that rephrasing the rule fails it, rather than so that a rephrasing which
# inverts the rule passes". "only" and "never" are the polarity-bearing words;
# an inversion cannot keep them and still mean the opposite.
CORRECTION_RULE_FRAGMENTS = (
    "corrected only to",
    "what actually happened",
    "never to change what was decided or built",
)
CORRECTION_RULE_ANCHOR = "corrected only to"
CORRECTION_RULE_LOCALITY = 400

# The canonical heading is `## Not performed`, per this change's tasks.md 5.2
# and the rule it writes into AGENTS.md. It is matched LOOSELY -- any heading
# whose text BEGINS with the phrase, so `## Not performed:` and
# `## Not performed (two tasks)` open the section too. An exact, `$`-anchored
# match fails OPEN: an author writing either of those produces a section that
# discloses work and a scan that reports nothing, and no checkbox is left for
# `openspec validate --archived` to catch it either -- silence, arrived at by
# the one route the check exists to close.
#
# It must BEGIN with the phrase rather than merely contain it, so that an
# ordinary numbered section mentioning it -- `## 4. Settle the work not
# performed` -- is not read as a disclosure section and its outstanding tasks
# are not read as silent disclosures. That direction matters: a false offence
# blocks every pull request in the repository until someone edits an archived
# record, which is the operational cost design.md's Risks section names.
DISCLOSURE_HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+not\s+performed\b", re.IGNORECASE)
MARKDOWN_HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+\S")

# A fenced block QUOTING the heading is documentation, not a section. Without
# fence awareness, quoting it opens the section for the rest of the file and
# turns every later top-level task into an entry owing a `Reason:` -- an
# unsatisfiable failure on a change that did nothing wrong. This change's own
# artifacts already quote the heading in prose, so the fenced case is a live
# path rather than a hypothetical one.
CODE_FENCE = re.compile(r"^[ \t]*(?P<fence>`{3,}|~{3,})")
LIST_ITEM = re.compile(r"^(?P<indent>[ \t]*)(?:[-*+]|\d+[.)])\s+(?P<text>.*)$")
REASON_LABEL = "Reason"


def relative_directory(value: object) -> str:
    """Normalise a directory reference to a repository-relative POSIX path."""
    text = str(value).strip()
    if text.startswith("./"):
        text = text[2:]
    return text.lstrip("/").rstrip("/")


def significant_lines(script: object) -> list[str]:
    """The lines of a `run:` script that are neither blank nor whole-line
    comments.

    A `#` line following a backslash continuation is not a comment, so dropping
    it here could in principle hide text. It cannot hide anything from the
    closed-form check below, which rejects the continuation line itself: the
    trailing backslash is an extra token no permitted invocation carries.
    """
    return [
        line.strip()
        for line in str(script).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def resolved_command(base: str, command: str) -> str:
    """`command` as a repository-relative path, read from the directory `base`
    the step runs in."""
    prefix = relative_directory(base)
    joined = f"{prefix}/{command}" if prefix else command
    return os.path.normpath(joined).lstrip("/")


def validating_invocation_flag(line: str, base: str = "") -> str | None:
    """The flag `line` invokes the validating tool with, or None where the line
    is not exactly one permitted invocation, run from `base`.

    This is the positive half of the closed form the delta specifies. Nothing
    is blocklisted: a line either is an invocation or it is not, so `|| true`,
    `|| :`, `; true`, a pipe, a redirection, a command substitution, a captured
    status and every construction nobody has thought of yet all fail the same
    way -- by contributing a token the permitted shape has no place for.

    The command is required to RESOLVE to the binary the lockfile-exact install
    places, not merely to end in its name: `npx openspec`, a bare `openspec` off
    PATH, and a path into some other install tree each run something the
    committed manifest and lockfile do not describe. `base` is the directory the
    step actually runs in -- its own `working-directory`, or its job's, or the
    workflow's -- because the same script line means different things under
    each.
    """
    tokens = line.split()
    if len(tokens) != 3:
        return None
    command, subcommand, flag = tokens
    if resolved_command(base, command) != INSTALLED_BINARY:
        return None
    if subcommand != VALIDATING_SUBCOMMAND:
        return None
    if flag not in VALIDATING_FLAGS:
        return None
    return flag


def record_validation_steps(workflow: dict | None = None):
    """Every `run:` step of the required check that mentions the validating
    tool and its subcommand, whatever shape it is in.

    Deliberately looser than `validating_invocation_flag`: a step whose script
    is `openspec validate --all || true` must be FOUND, so that the shape
    assertions fail on it, rather than missed so that they pass over it.
    """
    workflow = load_yaml(PR_VALIDATION) if workflow is None else workflow
    found = []
    for job, index, step in steps(workflow):
        script = str(step.get("run", ""))
        if VALIDATING_TOOL in script and VALIDATING_SUBCOMMAND in script:
            found.append((job, index, step))
    return found


def steps_delegating_the_validation(workflow: dict | None = None):
    """Steps that reach the validating tool through `uses:` rather than by
    running it, which is the relocation the delta forbids."""
    workflow = load_yaml(PR_VALIDATION) if workflow is None else workflow
    return [
        (job, index, step)
        for job, index, step in steps(workflow)
        if VALIDATING_TOOL in str(step.get("uses", ""))
    ]


def run_defaults(container: object) -> dict:
    """A workflow's or a job's `defaults.run` mapping, or an empty one.

    Both levels are read, at both call sites: a setting placed at either applies
    to every `run:` step below it, so an assertion reading only the step is
    satisfied while the setting does its work one level up.
    """
    if not isinstance(container, dict):
        return {}
    defaults = container.get("defaults") or {}
    if not isinstance(defaults, dict):
        return {}
    run = defaults.get("run") or {}
    return run if isinstance(run, dict) else {}


def effective_working_directory(workflow: dict, job_name: str, step: dict) -> str:
    """The directory a step's script runs in: its own `working-directory`, else
    its job's default, else the workflow's."""
    job = jobs(workflow).get(job_name) or {}
    for candidate in (
        step.get("working-directory"),
        job_defaults_working_directory(job),
        run_defaults(workflow).get("working-directory"),
    ):
        normalised = relative_directory(candidate or "")
        if normalised:
            return normalised
    return ""


def job_defaults_working_directory(job: dict) -> str:
    """The `working-directory` a job's `defaults.run` declares, or "".

    Takes the job's MAPPING, not its name. `steps()` yields the job NAME, so a
    caller copying that idiom would hand this function a `str`; that is refused
    by name here rather than raising a bare `AttributeError` from somewhere
    inside, because the two read very differently in a failure report. The one
    caller resolves the mapping with `jobs(workflow)[job_name]` before calling.
    """
    if not isinstance(job, dict):
        raise AssertionError(
            "job_defaults_working_directory takes the job's mapping, not "
            f"{job!r}; resolve it with jobs(workflow)[job_name] first"
        )
    defaults = job.get("defaults") or {}
    if not isinstance(defaults, dict):
        return ""
    run = defaults.get("run") or {}
    if not isinstance(run, dict):
        return ""
    return relative_directory(run.get("working-directory", ""))


def install_targets(job: dict, step: dict) -> set[str]:
    """The directories an install step operates in: its own or its job's
    `working-directory`, plus any `--prefix`/`-C` the script names."""
    targets = set()
    for candidate in (step.get("working-directory"), job_defaults_working_directory(job)):
        normalised_candidate = relative_directory(candidate or "")
        if normalised_candidate:
            targets.add(normalised_candidate)
    for line in significant_lines(step.get("run", "")):
        tokens = line.split()
        for position, token in enumerate(tokens):
            if token in ("--prefix", "-C") and position + 1 < len(tokens):
                targets.add(relative_directory(tokens[position + 1]))
            elif token.startswith("--prefix="):
                targets.add(relative_directory(token.split("=", 1)[1]))
    return targets


def package_manager_lines(workflow: dict | None = None):
    """(step label, line) for every script line in the required check whose
    first word is a package manager."""
    workflow = load_yaml(PR_VALIDATION) if workflow is None else workflow
    found = []
    for job, index, step in steps(workflow):
        for line in significant_lines(step.get("run", "")):
            tokens = line.split()
            if tokens and tokens[0] in PACKAGE_MANAGERS:
                found.append((step_label(job, index, step), line))
    return found


def npm_manifest(path: Path | None = None) -> dict:
    path = OPENSPEC_MANIFEST if path is None else path
    if not path.is_file():
        raise AssertionError(f"{path.relative_to(ROOT).as_posix()} does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_pin(name: str, manifest: dict) -> str | None:
    for section in ("dependencies", "devDependencies"):
        block = manifest.get(section) or {}
        if isinstance(block, dict) and name in block:
            return str(block[name])
    return None


def lockfile_versions(name: str, path: Path | None = None) -> set[str]:
    """Every version an npm lockfile records for `name`.

    `name` is the PACKAGE name, scope included. npm keys `packages` by install
    path, so a scoped package appears as `node_modules/@scope/name` and a nested
    one as `node_modules/other/node_modules/@scope/name`; splitting on the last
    `node_modules/` recovers the package name from both. Matching on the bare
    basename instead would both miss the scoped entry and match a different
    scope's package of the same name.
    """
    path = OPENSPEC_LOCKFILE if path is None else path
    if not path.is_file():
        raise AssertionError(f"{path.relative_to(ROOT).as_posix()} does not exist")
    data = json.loads(path.read_text(encoding="utf-8"))
    versions = set()
    packages = data.get("packages") or {}
    if isinstance(packages, dict):
        for key, entry in packages.items():
            if not key or not isinstance(entry, dict):
                continue
            if key.rsplit("node_modules/", 1)[-1] != name:
                continue
            if entry.get("version"):
                versions.add(str(entry["version"]))
    legacy = data.get("dependencies") or {}
    if isinstance(legacy, dict):
        entry = legacy.get(name)
        if isinstance(entry, dict) and entry.get("version"):
            versions.add(str(entry["version"]))
    return versions


def npm_manifest_directories(root: Path | None = None) -> set[str]:
    """Every repository directory holding a committed `package.json`, as `/a/b`.

    Walks with `walked_files()`, which prunes `node_modules` -- so an installed
    dependency's own manifest is not mistaken for one this repository owns -- as
    well as `.claude/worktrees`, without which every change's working tree would
    report a phantom copy of this one.
    """
    return {
        repository_directory_of(path, root)
        for path in walked_files(root)
        if path.name == NPM_MANIFEST_NAME
    }


def reason_text(line: str) -> str | None:
    """The text a `Reason:` label carries, or None where the line is not one.

    Tolerant of the label being a nested list item and of it being emphasised,
    because neither changes whether a reason was given. It is not tolerant of a
    different label: the delta names `Reason:` literally, and the label is the
    whole mechanism by which silence becomes detectable.
    """
    stripped = line.strip()
    item = LIST_ITEM.match(stripped)
    if item:
        stripped = item.group("text").strip()
    stripped = stripped.lstrip("*_ ")
    if not stripped.startswith(REASON_LABEL):
        return None
    rest = stripped[len(REASON_LABEL) :].lstrip("*_ ")
    if not rest.startswith(":"):
        return None
    return rest[1:].strip().strip("*_ ").strip()


def unfenced_lines(text: str) -> tuple[list[tuple[int, str]], bool]:
    """Every (line number, line) lying outside a fenced code block, and whether
    a fence was left open at end of file.

    The second element matters because an unterminated fence would otherwise
    hide the whole remainder of a file from the scan -- the same fail-open the
    fence awareness was added to prevent, reached from the other side.
    """
    lines: list[tuple[int, str]] = []
    fence: str | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        match = CODE_FENCE.match(raw)
        if match:
            token = match.group("fence")
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is None:
            lines.append((number, raw))
    return lines, fence is not None


def disclosure_sections(text: str) -> list[tuple[int, str, list[tuple[int, list[str]]]]]:
    """Every disclosure section, as (heading line number, heading, entries).

    A section is returned even when it holds no entries, so that a heading which
    discloses nothing is visible to the caller rather than indistinguishable
    from a file with no heading at all.

    A top-level list item that is itself a `Reason:` label is attached to the
    preceding entry rather than read as a new one, so that a disclosure written
    with its reason as a sibling item is still read as carrying one.
    """
    lines, _ = unfenced_lines(text)
    sections: list[tuple[int, str, list[tuple[int, list[str]]]]] = []
    entries: list[tuple[int, list[str]]] | None = None
    current: tuple[int, list[str]] | None = None
    level: int | None = None

    def close_entry() -> None:
        nonlocal current
        if current is not None and entries is not None:
            entries.append(current)
        current = None

    for number, raw in lines:
        heading = MARKDOWN_HEADING.match(raw)
        if heading:
            depth = len(heading.group("hashes"))
            if DISCLOSURE_HEADING.match(raw):
                close_entry()
                entries = []
                sections.append((number, raw.strip(), entries))
                level = depth
                continue
            if level is not None and depth <= level:
                close_entry()
                entries = None
                level = None
            continue
        if level is None:
            continue
        item = LIST_ITEM.match(raw)
        if item and not item.group("indent"):
            if current is not None and reason_text(raw) is not None:
                current[1].append(raw)
                continue
            close_entry()
            current = (number, [raw])
            continue
        if current is not None:
            current[1].append(raw)
    close_entry()
    return sections


def disclosure_entries(text: str):
    """Yield (line number, [lines]) for every disclosed item, across sections."""
    for _, _, entries in disclosure_sections(text):
        for entry in entries:
            yield entry


def task_lists(root: Path | None = None) -> list[Path]:
    """Every `tasks.md` under the changes directory, archived or active."""
    root = ROOT if root is None else root
    changes = root / "openspec" / CHANGES_DIRECTORY_NAME
    if not changes.is_dir():
        return []
    return sorted(path for path in changes.rglob("tasks.md") if path.is_file())


def disclosure_offences(root: Path | None = None) -> list[str]:
    """Every disclosure the check refuses, as `<path>:<line>: <what is wrong>`.

    Three kinds, and all three are the same thing -- silence the reader cannot
    see:

    * an entry carrying no `Reason:` label, or one whose text is empty. This is
      the scenario's own case.
    * a section that discloses NOTHING: a heading followed by prose alone, or by
      nothing at all. Prose is not a disclosure this check can read, so a
      section shaped that way reports zero offences while carrying exactly the
      silence the label exists to make detectable -- and `openspec validate
      --archived` is green over it too, there being no checkbox left. Prose
      INTRODUCING the entries is fine and is the shape the settled archived
      records already use; what is refused is a section with no entries at all.
    * a file that leaves a code fence open while naming the heading somewhere.
      The scan cannot then tell a quoted heading from a real one, and says so
      rather than guessing in the direction that reports nothing.
    """
    root = ROOT if root is None else root
    offences: list[str] = []
    for path in task_lists(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(root).as_posix()
        _, fence_left_open = unfenced_lines(text)
        if fence_left_open and any(
            DISCLOSURE_HEADING.match(line) for line in text.splitlines()
        ):
            offences.append(
                f"{relative}:1: a code fence is left open in a file that names the "
                "disclosure heading, so the scan cannot tell a quoted heading from a "
                "real one"
            )
            continue
        for heading_number, heading, entries in disclosure_sections(text):
            if not entries:
                offences.append(
                    f"{relative}:{heading_number}: discloses nothing: {heading!r} is "
                    "followed by no list item, so whatever it discloses is prose the "
                    "check cannot read"
                )
            for number, lines in entries:
                given = [
                    reason
                    for reason in (reason_text(line) for line in lines)
                    if reason is not None
                ]
                entry = " ".join(lines[0].split())
                if not given:
                    offences.append(f"{relative}:{number}: no `Reason:` label: {entry}")
                elif not any(given):
                    offences.append(f"{relative}:{number}: empty `Reason:` label: {entry}")
    return offences


def flattened(text: str) -> str:
    """Collapse whitespace, so a rule wrapped across lines still reads as one
    sentence."""
    return " ".join(text.split())


class TestTheSpecificationRecordIsValidatedByTheRequiredCheck(unittest.TestCase):
    """ADDED requirement: The Specification Record Is Verified in Continuous
    Integration."""

    def setUp(self) -> None:
        self.workflow = load_yaml(PR_VALIDATION)
        self.validating = record_validation_steps(self.workflow)

    def _require_located(self) -> None:
        self.assertTrue(
            self.validating,
            "no step in pr-validation.yml runs "
            f"`{VALIDATING_TOOL} {VALIDATING_SUBCOMMAND}`, so the specification "
            "record is not validated by the required status check at all -- and "
            "every shape assertion over that step would pass having read nothing",
        )

    def test_the_required_check_validates_the_specification_record(self) -> None:
        """SPECIFIED -- the requirement's opening SHALL: the record "SHALL be
        validated by its authoring tool as part of the required pull request
        status check, unconditionally".

        This is also the guard that keeps every other assertion in this section
        from passing vacuously, and the assertion that forecloses relocating the
        invocations into a called workflow or composite action: a relocated
        invocation is not a `run:` step of this workflow and is not found here.
        """
        self._require_located()

    def test_both_the_active_and_the_archived_record_are_validated(self) -> None:
        """SPECIFIED -- "Validation SHALL cover both the active record and the
        archived one. These are distinct properties reached by distinct
        invocations, and neither implies the other"."""
        self._require_located()
        flags: list[str] = []
        for job, _, step in self.validating:
            base = effective_working_directory(self.workflow, job, step)
            for line in significant_lines(step.get("run", "")):
                flag = validating_invocation_flag(line, base)
                if flag:
                    flags.append(flag)
        self.assertEqual(
            sorted(VALIDATING_FLAGS),
            sorted(flags),
            "the required check does not run exactly one validation of the active "
            "record and one of the archived record; the invocations it runs are "
            f"{sorted(flags)}",
        )

    def test_the_validation_is_invoked_by_a_run_step_rather_than_delegated(self) -> None:
        """SPECIFIED -- "Relocating the invocations into a called workflow or
        composite action SHALL NOT be used to escape that shape"."""
        delegating = [
            step_label(job, index, step)
            for job, index, step in steps_delegating_the_validation(self.workflow)
        ]
        self.assertEqual(
            [],
            delegating,
            "these steps reach the validating tool through `uses:`, which moves its "
            f"script somewhere this suite cannot read the shape of: {delegating}",
        )

    def test_the_validating_step_is_unconditional(self) -> None:
        """SPECIFIED -- scenario "The validation runs regardless of what a pull
        request touched", and "The check SHALL run on every pull request rather
        than only on those that change a file under the specification
        directory". Asserts the key is absent: `if: true` is still a condition
        declared where the requirement says there is none."""
        self._require_located()
        offenders = [
            step_label(job, index, step) for job, index, step in self.validating if "if" in step
        ]
        self.assertEqual(
            [],
            offenders,
            f"these steps gate the record validation behind an `if:`: {offenders}",
        )

    def test_the_job_enclosing_the_validating_step_is_unconditional(self) -> None:
        """SPECIFIED -- "The job enclosing the check SHALL itself be
        unconditional ... a step that cannot be skipped inside a job that can is
        skippable", together with the allowance the requirement now carries:
        "Where the enclosing job declares `needs:` ... it MAY carry the single
        condition `always()` and no other."

        Re-expressed, not relaxed. Its previous body treated the PRESENCE of an
        `if:` key as the offence, which the allowance makes wrong for one exact
        literal and for nothing else -- see `job_condition_is_admissible`, whose
        discrimination `TestTheAdmittedJobConditionIsExactlyOneLiteral` pins.
        """
        self._require_located()
        offenders = sorted(
            {
                job
                for job, _, _ in self.validating
                if not job_condition_is_admissible(jobs(self.workflow)[job] or {})
            }
        )
        self.assertEqual(
            [],
            offenders,
            "these jobs gate the record validation behind a condition the requirement "
            "does not admit -- it admits the single literal `always()`, and only on a "
            f"job declaring `needs:`: {offenders}",
        )

    def test_the_validating_step_runs_inside_a_registered_required_context(self) -> None:
        """SPECIFIED -- the requirement's opening SHALL: validated "as part of
        the required pull request status check".

        Every other assertion here locates the step by scanning all jobs and then
        reads whichever job holds it, which is satisfied by a job that is not
        registered in branch protection at all. Moving the steps into a new
        `spec-check` job would leave those assertions green while a pull request
        with the record validation red stayed mergeable -- green-because-
        unregistered, which is the same defect as green-because-skipped.

        `REQUIRED_STATUS_CHECK_WORKFLOWS` is this suite's existing record of
        which contexts are registered; this is the assertion that finally
        consults it for these steps.
        """
        self._require_located()
        registered = {
            context
            for context, workflow_path in REQUIRED_STATUS_CHECK_WORKFLOWS.items()
            if workflow_path == PR_VALIDATION
        }
        self.assertTrue(
            registered,
            "REQUIRED_STATUS_CHECK_WORKFLOWS names no context for pr-validation.yml, "
            "so this assertion would pass having compared against nothing",
        )
        holding = {
            job_context_name(job, jobs(self.workflow)[job] or {}) for job, _, _ in self.validating
        }
        offenders = sorted(holding - registered)
        self.assertEqual(
            [],
            offenders,
            f"these jobs hold the record validation but produce no registered "
            f"required context: {offenders}; registered: {sorted(registered)}. A "
            "check that is not a required context does not gate the merge",
        )

    def test_the_workflow_carrying_the_validation_declares_no_path_filter(self) -> None:
        """SPECIFIED -- "the workflow SHALL NOT reach it through a
        workflow-level path filter".

        `TestRequiredCheckIsNotPathFiltered` asserts the same property of the
        same file for a different requirement. The duplication is deliberate, in
        the pattern that class already documents: this requirement's own
        obligation must not rest on a test that a change to another requirement
        could legitimately retire.
        """
        self._require_located()
        on = triggers(self.workflow)
        self.assertTrue(on, "pr-validation.yml declares no triggers at all")
        for event, config in on.items():
            if not isinstance(config, dict):
                continue
            for key in ("paths", "paths-ignore"):
                self.assertNotIn(
                    key,
                    config,
                    f"pr-validation.yml's `{event}` trigger declares `{key}:`, so a "
                    "pull request touching no specification file would carry a stale "
                    "record past the gate",
                )

    def test_the_validation_runs_on_every_pull_request(self) -> None:
        """SPECIFIED -- "The check SHALL run on every pull request"."""
        self._require_located()
        self.assertIn(
            "pull_request",
            triggers(self.workflow),
            "pr-validation.yml does not trigger on `pull_request`, so the record "
            "validation does not run on pull requests at all",
        )


class TestTheRecordValidationCannotReportSuccessOverAFailure(unittest.TestCase):
    """ADDED requirement: The Specification Record Is Verified in Continuous
    Integration.

    Scenario "The check cannot report success over a failed validation". Every
    other obligation on this step is satisfied by a step that runs
    unconditionally, installs from the pinned manifest, and then throws its
    result away: such a step exists, is not skipped, is exactly pinned, and
    reports green forever.

    Asserted as a CLOSED POSITIVE SHAPE, never as a blocklist of evasions -- the
    delta requires this in those words, and that change's design.md Decision 9
    records that a blocklist written against `|| true` is defeated by `|| :`,
    and that a step-level reading is defeated by a job-level setting. Both are
    asserted here.
    """

    def setUp(self) -> None:
        self.workflow = load_yaml(PR_VALIDATION)
        self.validating = record_validation_steps(self.workflow)
        self.assertTrue(
            self.validating,
            "no step in pr-validation.yml runs "
            f"`{VALIDATING_TOOL} {VALIDATING_SUBCOMMAND}`, so these shape "
            "assertions would pass having read nothing",
        )

    def test_the_validating_step_script_is_the_invocations_and_nothing_else(self) -> None:
        """SPECIFIED -- "its script SHALL consist of the validating invocations
        and nothing else -- no shell operator joining them to anything, no
        redirection or capture of their status"."""
        offenders = []
        for job, index, step in self.validating:
            base = effective_working_directory(self.workflow, job, step)
            for line in significant_lines(step.get("run", "")):
                if validating_invocation_flag(line, base) is None:
                    offenders.append(f"{step_label(job, index, step)}: {line}")
        self.assertEqual(
            [],
            offenders,
            "these script lines are not one of the permitted validating "
            f"invocations, so the step's script is not the closed form the "
            f"requirement specifies: {offenders}. The permitted form is a path "
            f"resolving to `{INSTALLED_BINARY}` from the directory the step runs "
            f"in, then `{VALIDATING_SUBCOMMAND}`, then exactly one of "
            f"{list(VALIDATING_FLAGS)}, and no other token -- not `npx`, which "
            "does not find this install, and not a bare name off PATH. A "
            "legitimate edit to this step is meant to fail this assertion until "
            "the assertion is updated with it",
        )

    def test_the_validating_step_declares_no_shell_override(self) -> None:
        """SPECIFIED -- "no shell override". A `shell:` key can reintroduce every
        construction the closed form excludes -- a shell without exit-on-error,
        or an interpreter that reads the script as something other than a list of
        commands."""
        offenders = [
            f"{step_label(job, index, step)}: shell: {step['shell']}"
            for job, index, step in self.validating
            if "shell" in step
        ]
        self.assertEqual([], offenders, f"steps overriding `shell:`: {offenders}")

    def test_the_job_enclosing_the_validating_step_declares_no_shell_default(self) -> None:
        """SPECIFIED -- "no shell override", read at the job level, and delta
        ¶24's requirement that suppression be read at both levels.

        A `defaults: run: shell:` on the job applies to every `run:` step in it,
        so a step-level assertion passes over it entirely. A custom shell is an
        argv template with `{0}` substituted for the script path, so a wrapper of
        the shape `bash -c 'bash "$0"; exit 0'` runs the script and throws its
        status away -- the construction nobody listed, which is the whole reason
        the form is closed rather than blocklisted.
        """
        offenders = sorted(
            {
                f"{job}: defaults.run.shell: {run_defaults(jobs(self.workflow)[job])['shell']}"
                for job, _, _ in self.validating
                if "shell" in run_defaults(jobs(self.workflow)[job])
            }
        )
        self.assertEqual([], offenders, f"jobs defaulting `shell:`: {offenders}")

    def test_the_workflow_declares_no_shell_default(self) -> None:
        """SPECIFIED -- the same clause read one level higher again. A
        workflow-level `defaults: run: shell:` reaches every job, so a reading
        that stopped at the job would be satisfied by moving it up one line."""
        declared = run_defaults(self.workflow)
        self.assertNotIn(
            "shell",
            declared,
            "pr-validation.yml declares a workflow-level `defaults.run.shell`, "
            f"which applies to the validating steps: {declared.get('shell')!r}",
        )

    def test_the_validating_step_declares_no_continue_on_error(self) -> None:
        """SPECIFIED -- "neither the step nor its enclosing job SHALL declare a
        continue-on-error setting in any form, including one whose value is an
        expression".

        Asserts the KEY IS ABSENT rather than that its value is falsy: an
        expression-valued setting reads as a harmless string here and is true on
        the runner.
        """
        offenders = [
            f"{step_label(job, index, step)}: continue-on-error: {step['continue-on-error']}"
            for job, index, step in self.validating
            if "continue-on-error" in step
        ]
        self.assertEqual([], offenders, f"steps declaring continue-on-error: {offenders}")

    def test_the_job_enclosing_the_validating_step_declares_no_continue_on_error(self) -> None:
        """SPECIFIED -- the same clause read at the job level. A step that cannot
        suppress its failure inside a job that can is suppressible, and a
        step-level-only assertion is satisfied by one `continue-on-error` on the
        job."""
        offenders = sorted(
            {
                f"{job}: continue-on-error: "
                f"{(jobs(self.workflow)[job] or {})['continue-on-error']}"
                for job, _, _ in self.validating
                if "continue-on-error" in (jobs(self.workflow)[job] or {})
            }
        )
        self.assertEqual([], offenders, f"jobs declaring continue-on-error: {offenders}")


class TestTheClosedFormIsARealReadOfTheScript(unittest.TestCase):
    """ADDED requirement: The Specification Record Is Verified in Continuous
    Integration.

    A shape assertion that accepted everything would pass over the workflow
    above while establishing nothing. These exercise the matcher directly
    against the constructions the delta and design.md Decision 9 name -- and, as
    importantly, against ones they do not name, which is the property a
    blocklist cannot have.
    """

    def test_the_permitted_invocations_are_recognised(self) -> None:
        """DERIVED -- no scenario states it. The converse half: a matcher that
        rejected everything would satisfy every rejection below while failing
        any correct workflow.

        Every permitted form names a path into the install tree the committed
        manifest and lockfile describe, read from wherever the step runs.
        """
        for line, base, expected in (
            (f"./{INSTALLED_BINARY} {VALIDATING_SUBCOMMAND} --all", "", "--all"),
            (f"{INSTALLED_BINARY} {VALIDATING_SUBCOMMAND} --archived", "", "--archived"),
            (f"./{NODE_BIN_SEGMENT}/{VALIDATING_TOOL} {VALIDATING_SUBCOMMAND} --all",
             MANIFEST_DIRECTORY, "--all"),
            (f"{NODE_BIN_SEGMENT}/{VALIDATING_TOOL} {VALIDATING_SUBCOMMAND} --archived",
             f"./{MANIFEST_DIRECTORY}", "--archived"),
        ):
            self.assertEqual(expected, validating_invocation_flag(line, base), line)

    def test_an_invocation_outside_the_pinned_install_tree_is_rejected(self) -> None:
        """SPECIFIED -- "SHALL install the exact version the committed manifest
        pins ... and SHALL NOT be resolved freshly at run time", read on the line
        that runs the tool rather than on the line that installs it.

        `npx` is here because it was previously ADMITTED, on the false belief
        that it finds the local install. It does not: `npm ci` installs into
        `.github/node_modules`, npx searches upward from the working directory,
        and `.github` is a child of the root rather than an ancestor. With the
        install moved aside it still exits 0, resolving from a cache no runner
        has. A bare name off PATH fails for the same reason, and so does a path
        into an install tree nothing here pins.
        """
        for line, base in (
            (f"npx {VALIDATING_TOOL} {VALIDATING_SUBCOMMAND} --all", ""),
            (f"npx --yes {VALIDATING_TOOL} {VALIDATING_SUBCOMMAND} --all", ""),
            (f"{VALIDATING_TOOL} {VALIDATING_SUBCOMMAND} --all", ""),
            (f"{VALIDATING_TOOL} {VALIDATING_SUBCOMMAND} --archived", MANIFEST_DIRECTORY),
            (f"/usr/local/bin/{VALIDATING_TOOL} {VALIDATING_SUBCOMMAND} --all", ""),
            (f"./{NODE_BIN_SEGMENT}/{VALIDATING_TOOL} {VALIDATING_SUBCOMMAND} --all", ""),
            (f"elsewhere/{NODE_BIN_SEGMENT}/{VALIDATING_TOOL} {VALIDATING_SUBCOMMAND} --all", ""),
        ):
            self.assertIsNone(validating_invocation_flag(line, base), f"{line!r} from {base!r}")

    def test_a_suppressed_invocation_is_rejected(self) -> None:
        """SPECIFIED -- scenario "The check cannot report success over a failed
        validation". `|| :` and `; true` are here because they are what a
        blocklist written against `|| true` lets through."""
        binary = f"./{INSTALLED_BINARY}"
        for line in (
            f"{binary} validate --all || true",
            f"{binary} validate --all || :",
            f"{binary} validate --all ; true",
            f"{binary} validate --all && echo ok",
            f"{binary} validate --all | tee log.txt",
            f"{binary} validate --all > /dev/null 2>&1",
            "set +e",
            f"if ! {binary} validate --all; then echo soft; fi",
            f"status=$({binary} validate --all)",
            f"{binary} validate --all &",
            f"bash -c '{binary} validate --all || true'",
        ):
            self.assertIsNone(validating_invocation_flag(line), line)

    def test_a_line_that_is_not_the_validation_is_rejected(self) -> None:
        """SPECIFIED -- "its script SHALL consist of the validating invocations
        and nothing else"."""
        binary = f"./{INSTALLED_BINARY}"
        for line in (
            "npm ci",
            "echo validating",
            f"{binary} validate",
            f"{binary} validate --all --quiet",
            f"{binary} list",
            "cd .github",
        ):
            self.assertIsNone(validating_invocation_flag(line), line)


class TestTheValidatingToolIsInstalledFromAPinnedManifest(unittest.TestCase):
    """ADDED requirement: The Specification Record Is Verified in Continuous
    Integration. Scenario "The validating tool is not resolved freshly at run
    time"."""

    def setUp(self) -> None:
        self.workflow = load_yaml(PR_VALIDATION)
        self.validating = record_validation_steps(self.workflow)
        self.manifest_directory = OPENSPEC_MANIFEST.parent.relative_to(ROOT).as_posix()

    def _validating_jobs(self) -> list[str]:
        self.assertTrue(
            self.validating,
            "no step in pr-validation.yml runs the validating tool, so these "
            "install assertions would pass having read nothing",
        )
        return sorted({job for job, _, _ in self.validating})

    def test_the_manifest_and_its_lockfile_are_committed(self) -> None:
        """SPECIFIED -- "installed from a manifest that pins it to an exact
        version and is committed to this repository", and "SHALL fail rather than
        proceed where the manifest and its lockfile disagree", which presupposes
        a committed lockfile."""
        for path in (OPENSPEC_MANIFEST, OPENSPEC_LOCKFILE):
            self.assertTrue(
                path.is_file(),
                f"{path.relative_to(ROOT).as_posix()} is not committed, so the "
                "validating tool's version is not pinned by anything this "
                "repository holds",
            )

    def test_the_manifest_pins_the_tool_to_an_exact_version(self) -> None:
        """SPECIFIED -- "pins it to an exact version ... and SHALL NOT be
        resolved freshly at run time". A range, a channel tag or a URL is a fresh
        resolution wearing a manifest."""
        pin = manifest_pin(VALIDATING_PACKAGE, npm_manifest())
        self.assertIsNotNone(
            pin,
            f"{OPENSPEC_MANIFEST.relative_to(ROOT).as_posix()} names no "
            f"`{VALIDATING_PACKAGE}` dependency. The npm package is scoped; the "
            f"binary it installs is `{VALIDATING_TOOL}`, and the manifest keys on "
            "the package",
        )
        self.assertRegex(
            pin,
            EXACT_NPM_VERSION,
            f"`{VALIDATING_PACKAGE}` is pinned as {pin!r}, which is not an exact "
            "version: two installs at different times could resolve differently and "
            "silently change what the gate checks. An npm alias "
            f'(`"{VALIDATING_TOOL}": "npm:{VALIDATING_PACKAGE}@<version>"`) fails '
            "here for that reason, and is refused on purpose",
        )

    def test_the_lockfile_records_the_version_the_manifest_pins(self) -> None:
        """SPECIFIED -- "SHALL fail rather than proceed where the manifest and
        its lockfile disagree". The workflow's install enforces this at run time;
        this is the same property read statically, so a disagreement is a red
        test rather than a red pipeline."""
        pin = manifest_pin(VALIDATING_PACKAGE, npm_manifest())
        self.assertIsNotNone(pin, "the manifest names no validating tool to compare against")
        versions = lockfile_versions(VALIDATING_PACKAGE)
        self.assertTrue(
            versions,
            f"the lockfile records no version of `{VALIDATING_PACKAGE}` at all, so "
            "the install would have nothing exact to install",
        )
        self.assertEqual(
            {pin},
            versions,
            f"the manifest pins `{VALIDATING_PACKAGE}` {pin} and the lockfile records "
            f"{sorted(versions)}",
        )

    def test_the_workflow_installs_the_tool_with_a_lockfile_exact_install(self) -> None:
        """SPECIFIED -- "SHALL install the exact version the committed manifest
        pins ... and SHALL fail rather than proceed where the manifest and its
        lockfile disagree".

        DERIVED in one respect, recorded in the test plan: that npm's
        lockfile-exact install is spelled `npm ci` -- and that a resolving
        `npm install` is not it -- comes from that change's design.md Decision 7,
        not from the delta, which states the property rather than the command.
        """
        validating_jobs = self._validating_jobs()
        installing = []
        for job, index, step in steps(self.workflow):
            if job not in validating_jobs:
                continue
            for line in significant_lines(step.get("run", "")):
                if tuple(line.split()[:2]) != LOCKFILE_EXACT_INSTALL:
                    continue
                if self.manifest_directory in install_targets(jobs(self.workflow)[job] or {}, step):
                    installing.append(step_label(job, index, step))
        self.assertTrue(
            installing,
            "no step in the job that validates the record runs "
            f"`{' '.join(LOCKFILE_EXACT_INSTALL)}` against {self.manifest_directory}/, "
            "so the tool the step runs is not the one the committed manifest and "
            "lockfile pin",
        )

    def test_the_install_target_helper_takes_the_jobs_mapping_not_its_name(self) -> None:
        """DERIVED -- no scenario states it. `steps()` yields the job NAME, and
        the assertion above resolves the job's mapping with
        `jobs(self.workflow)[job]` before calling `install_targets`. A future
        call site copying the iterator's idiom would hand it a `str` instead;
        this pins both halves -- that a job-level `defaults.run.working-directory`
        IS read when the mapping is passed, which is the path a reviewer flagged
        as unreachable, and that passing the name is refused by name rather than
        raising a bare `AttributeError` from somewhere inside.
        """
        job = {"defaults": {"run": {"working-directory": ".github"}}}
        step = {"run": " ".join(LOCKFILE_EXACT_INSTALL)}
        self.assertEqual({".github"}, install_targets(job, step))
        with self.assertRaises(AssertionError):
            install_targets("validate", step)

    def test_no_package_is_installed_by_a_resolving_command(self) -> None:
        """SPECIFIED -- "SHALL NOT be resolved freshly at run time".

        Stated as a closed shape rather than as a list of resolving commands:
        every package-manager line in the required check must be the
        lockfile-exact install. `npm install`, `npm i`, `yarn add`, a global
        install pinned inline in the workflow, and anything else are rejected
        together, by not being it.
        """
        offenders = [
            f"{label}: {line}"
            for label, line in package_manager_lines(self.workflow)
            if tuple(line.split()[:2]) != LOCKFILE_EXACT_INSTALL
        ]
        self.assertEqual(
            [],
            offenders,
            "these package-manager invocations are not the lockfile-exact install "
            f"`{' '.join(LOCKFILE_EXACT_INSTALL)}`, so they resolve a version at run "
            f"time: {offenders}",
        )

    def test_the_runtime_that_executes_the_tool_is_pinned(self) -> None:
        """SPECIFIED -- "The runtime that executes it SHALL be pinned in the same
        sense: a freshly resolved interpreter beneath an exactly pinned tool
        leaves the pin describing less than it appears to"."""
        validating_jobs = self._validating_jobs()
        setups = [
            (job, index, step)
            for job, index, step in steps(self.workflow)
            if job in validating_jobs and SETUP_NODE in str(step.get("uses", ""))
        ]
        self.assertTrue(
            setups,
            "the job that validates the record sets up no Node runtime, so the "
            "interpreter beneath the exactly pinned tool is whatever the runner "
            "image happens to carry",
        )
        offenders = []
        for job, index, step in setups:
            label = step_label(job, index, step)
            reference = str(step["uses"])
            ref = reference.rsplit("@", 1)[-1] if "@" in reference else ""
            if ref.strip().lower() in MUTABLE_ACTION_REFS:
                offenders.append(f"{label}: action reference {reference!r} is not pinned")
            with_block = step.get("with") or {}
            version = str(with_block.get("node-version", "")).strip()
            version_file = str(with_block.get("node-version-file", "")).strip()
            if version:
                if not version[0].isdigit():
                    offenders.append(f"{label}: node-version {version!r} names no explicit version")
            elif version_file:
                referenced = ROOT / relative_directory(version_file)
                if not referenced.is_file():
                    offenders.append(f"{label}: node-version-file {version_file!r} is not committed")
            else:
                offenders.append(f"{label}: declares neither node-version nor node-version-file")
        self.assertEqual([], offenders, f"the Node runtime is not pinned: {offenders}")


class TestThePinMatchersReadTheScopedPackageName(unittest.TestCase):
    """ADDED requirement: The Specification Record Is Verified in Continuous
    Integration.

    The manifest assertions above rest on two matchers and on one fact about the
    world: the npm package is `@fission-ai/openspec` and the binary it installs
    is `openspec`. An earlier revision of these tests assumed the two names were
    one, which made the assertions unsatisfiable by a correct manifest -- the
    test asserting a fact rather than reading one. These fixtures pin the
    distinction so it cannot be lost again, and they read no repository file, so
    they discriminate whether or not the manifest is committed yet.
    """

    SCOPED_LOCKFILE = {
        "lockfileVersion": 3,
        "packages": {
            "": {"dependencies": {VALIDATING_PACKAGE: "1.12.0"}},
            f"node_modules/{VALIDATING_PACKAGE}": {"version": "1.12.0"},
        },
    }

    def _lockfile(self, document: dict) -> Path:
        root = Path(tempfile.mkdtemp(prefix="lockfile-fixture-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        path = root / "package-lock.json"
        path.write_text(json.dumps(document, indent=2), encoding="utf-8")
        return path

    def test_the_manifest_matcher_finds_the_scoped_package(self) -> None:
        """SPECIFIED -- "installed from a manifest that pins it to an exact
        version", read against the name the manifest actually carries."""
        for section in ("dependencies", "devDependencies"):
            manifest = {section: {VALIDATING_PACKAGE: "1.12.0"}}
            self.assertEqual("1.12.0", manifest_pin(VALIDATING_PACKAGE, manifest), section)

    def test_the_manifest_matcher_does_not_answer_to_the_binary_name(self) -> None:
        """DERIVED -- no scenario states it. This is the wrong assumption itself,
        written down: a manifest keyed on the package must not be readable under
        the binary's name, or the two roles collapse back into one and the next
        author cannot tell which is which."""
        manifest = {"dependencies": {VALIDATING_PACKAGE: "1.12.0"}}
        self.assertIsNone(manifest_pin(VALIDATING_TOOL, manifest))

    def test_the_lockfile_matcher_reads_a_scoped_install_path(self) -> None:
        """SPECIFIED -- "SHALL fail rather than proceed where the manifest and
        its lockfile disagree". npm keys `packages` by install path, so the
        scoped package appears as `node_modules/@scope/name`."""
        path = self._lockfile(self.SCOPED_LOCKFILE)
        self.assertEqual({"1.12.0"}, lockfile_versions(VALIDATING_PACKAGE, path))

    def test_the_lockfile_matcher_reads_a_nested_install_path(self) -> None:
        """DERIVED -- no scenario states it. A transitively installed copy sits
        under a second `node_modules/`, and a matcher that missed it would report
        agreement it had not checked."""
        path = self._lockfile(
            {
                "packages": {
                    "": {},
                    f"node_modules/other/node_modules/{VALIDATING_PACKAGE}": {
                        "version": "1.12.0"
                    },
                }
            }
        )
        self.assertEqual({"1.12.0"}, lockfile_versions(VALIDATING_PACKAGE, path))

    def test_the_lockfile_matcher_reads_the_legacy_dependencies_block(self) -> None:
        """DERIVED -- no scenario states it. Lockfile version 1 records versions
        under `dependencies` rather than `packages`, and the assertion must not
        silently read nothing if npm writes one."""
        path = self._lockfile({"dependencies": {VALIDATING_PACKAGE: {"version": "1.12.0"}}})
        self.assertEqual({"1.12.0"}, lockfile_versions(VALIDATING_PACKAGE, path))

    def test_the_lockfile_matcher_ignores_another_scopes_package_of_the_same_name(self) -> None:
        """DERIVED -- no scenario states it. Matching on the bare basename would
        read `@someone-else/openspec` as this pin and report an agreement between
        a manifest and a lockfile that describe different packages."""
        path = self._lockfile(
            {"packages": {"": {}, "node_modules/@someone-else/openspec": {"version": "9.9.9"}}}
        )
        self.assertEqual(set(), lockfile_versions(VALIDATING_PACKAGE, path))

    def test_the_lockfile_matcher_does_not_answer_to_the_binary_name(self) -> None:
        """DERIVED -- no scenario states it. The converse of the manifest case,
        for the same reason."""
        path = self._lockfile(self.SCOPED_LOCKFILE)
        self.assertEqual(set(), lockfile_versions(VALIDATING_TOOL, path))

    def test_an_npm_alias_is_not_an_exact_version(self) -> None:
        """DERIVED -- no scenario states it. An alias
        (`"openspec": "npm:@fission-ai/openspec@1.12.0"`) would make the literal
        key the old, wrong assertion wanted appear in the manifest. It is refused
        because it bends the manifest to fit a test; this asserts that the pin
        check refuses it too, rather than leaving the refusal to a comment."""
        alias = f"npm:{VALIDATING_PACKAGE}@1.12.0"
        self.assertNotRegex(alias, EXACT_NPM_VERSION)
        self.assertRegex("1.12.0", EXACT_NPM_VERSION)


class TestThePinIsWatchedByTheDependencyUpdateConfiguration(unittest.TestCase):
    """ADDED requirement: The Specification Record Is Verified in Continuous
    Integration. Scenario "The pin is watched by the dependency-update
    configuration"."""

    def test_the_dependency_update_configuration_covers_the_manifests_directory(self) -> None:
        """SPECIFIED -- "That manifest SHALL be covered by the repository's
        dependency-update configuration, so that the pin is maintained rather
        than left to rot -- a pinned dependency nothing watches is the failure
        this repository has recorded against itself four times over"."""
        directory = "/" + MANIFEST_DIRECTORY
        configured = configured_directories(NPM_ECOSYSTEM)
        self.assertTrue(
            configured,
            ".github/dependabot.yml has no `npm` entry, so nothing raises a new "
            "version of the validating tool as a reviewable pull request",
        )
        self.assertTrue(
            any(gh_glob_matches(pattern, directory) for pattern in configured),
            f"no Dependabot `npm` entry names {directory}, where the validating "
            f"tool's manifest lives; configured: {sorted(configured)}",
        )

    def test_every_directory_holding_an_npm_manifest_is_watched(self) -> None:
        """DERIVED -- the converse of the assertion above, and the one this
        stanza was missing while both its neighbours carry it: the `terraform`
        ecosystem asserts that every lockfile-bearing directory is named, and the
        Compose one that every stack-shaped file is reachable.

        Asserting only the forward direction leaves a second `package.json`
        added anywhere in the tree unwatched, with nothing red to say so -- which
        is the failure this repository has recorded against itself four times
        over, and the failure the npm stanza exists to stop repeating. A set
        comparison is the whole check, because Dependabot's npm ecosystem has no
        discovery of its own.
        """
        found = npm_manifest_directories()
        self.assertTrue(
            found,
            "no package.json was found anywhere in the tree, so this comparison "
            "would pass having read nothing",
        )
        configured = configured_directories(NPM_ECOSYSTEM)
        uncovered = sorted(
            directory
            for directory in found
            if not any(gh_glob_matches(pattern, directory) for pattern in configured)
        )
        self.assertEqual(
            [],
            uncovered,
            f"these directories hold a package.json that no Dependabot "
            f"`{NPM_ECOSYSTEM}` entry names, so their pins are watched by nobody: "
            f"{uncovered}; configured: {sorted(configured)}",
        )


class TestUnperformedWorkIsDisclosedWithAReason(unittest.TestCase):
    """ADDED requirement: The Specification Record Is Verified in Continuous
    Integration. Scenario "Unperformed work disclosed without a reason fails the
    check"."""

    def test_the_scan_reaches_the_repositorys_task_lists(self) -> None:
        """DERIVED -- no scenario states it. The assertion below is over every
        `tasks.md` under the changes directory; a scan that reached none of them
        would report a clean repository having read nothing, which is the vacuous
        success this whole change is about."""
        found = task_lists()
        self.assertTrue(found, "the scan reached no tasks.md at all under the changes directory")
        archived = [path for path in found if ARCHIVE_SEGMENT in path.relative_to(ROOT).parts]
        self.assertTrue(
            archived,
            "the scan reached no archived tasks.md, so the disclosures the gate "
            "exists to read would be invisible to it",
        )

    def test_every_disclosure_carries_a_reason_with_text(self) -> None:
        """SPECIFIED -- "A disclosed item that states no reason SHALL fail the
        check exactly as an unticked task does", and "the check SHALL assert that
        the label is present and its text non-empty, and SHALL NOT attempt to
        assess whether the reason is a good one".

        Scoped to every `tasks.md` under the changes directory, archived or
        active, per the delta: the first disclosure this repository writes is in
        an active change, and a check that only read the archive would not see
        it.
        """
        offences = disclosure_offences()
        self.assertEqual(
            [],
            offences,
            "these disclosures of unperformed work state no reason, which is less "
            f"information than the unticked box they replaced: {offences}",
        )


class TestTheDisclosureCheckIsARealReadOfTheFile(unittest.TestCase):
    """ADDED requirement: The Specification Record Is Verified in Continuous
    Integration.

    The repository-scoped assertion above is green, and greenness alone does not
    say why: it reads the same as a scan that found nothing to judge. These
    fixtures are what separate the two. They were written when no
    `## Not performed` section existed anywhere in the repository -- this change
    writes the first ones -- and they still carry the whole discrimination now
    that the settled records each carry one, because a repository whose
    disclosures happen to be well formed exercises none of the rejections below.
    """

    def _fixture(self, body: str) -> Path:
        root = Path(tempfile.mkdtemp(prefix="not-performed-fixture-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        directory = (
            root / "openspec" / CHANGES_DIRECTORY_NAME / ARCHIVE_SEGMENT / "2026-01-01-a-change"
        )
        directory.mkdir(parents=True)
        (directory / "tasks.md").write_text(body, encoding="utf-8")
        return root

    def test_a_disclosure_with_a_reason_is_accepted(self) -> None:
        """SPECIFIED -- the converse half of the scenario. Without it, a check
        that reported an offence unconditionally would satisfy every rejection
        below while failing every honest disclosure."""
        root = self._fixture(
            "# Tasks\n\n"
            "## 1. Section\n\n"
            "- [x] 1.1 Something that happened\n\n"
            "## Not performed\n\n"
            "- 1.2 Something that did not happen\n"
            "  Reason: no credential for it existed in the authoring sandbox.\n"
        )
        self.assertEqual([], disclosure_offences(root))

    def test_a_reason_wrapped_across_lines_is_accepted(self) -> None:
        """DERIVED -- no scenario states it. Prose in this repository wraps at
        eighty columns, so a check that required the whole reason on the label
        line would reject the ordinary case."""
        root = self._fixture(
            "## Not performed\n\n"
            "- 1.2 Something that did not happen\n"
            "  Reason: the run this describes is gone and the counts it reported\n"
            "  were never captured.\n"
        )
        self.assertEqual([], disclosure_offences(root))

    def test_a_reason_written_as_a_sibling_item_is_accepted(self) -> None:
        """DERIVED -- no scenario states it. The delta requires the label, not a
        particular indentation of it."""
        root = self._fixture(
            "## Not performed\n\n"
            "- 1.2 Something that did not happen\n"
            "- Reason: it was declined on judgment.\n"
        )
        self.assertEqual([], disclosure_offences(root))

    def test_a_disclosure_with_no_reason_label_is_rejected(self) -> None:
        """SPECIFIED -- "an archived change discloses work as not performed and
        carries no `Reason:` label"."""
        root = self._fixture("## Not performed\n\n- 1.2 Something that did not happen\n")
        offences = disclosure_offences(root)
        self.assertEqual(1, len(offences), offences)

    def test_a_disclosure_with_an_empty_reason_is_rejected(self) -> None:
        """SPECIFIED -- "or carries one whose text is empty"."""
        root = self._fixture(
            "## Not performed\n\n- 1.2 Something that did not happen\n  Reason:\n"
        )
        offences = disclosure_offences(root)
        self.assertEqual(1, len(offences), offences)

    def test_a_reason_of_whitespace_alone_is_rejected(self) -> None:
        """SPECIFIED -- the same clause. Whitespace is silence spelled
        differently."""
        root = self._fixture(
            "## Not performed\n\n- 1.2 Something that did not happen\n  Reason:    \n"
        )
        offences = disclosure_offences(root)
        self.assertEqual(1, len(offences), offences)

    def test_a_reason_stated_outside_the_section_does_not_satisfy_a_disclosure(self) -> None:
        """DERIVED -- no scenario states it. A file-wide search for the label
        would let one reason cover every silent disclosure in the file."""
        root = self._fixture(
            "## 1. Section\n\n"
            "- [ ] 1.1 An ordinary outstanding task\n"
            "  Reason: this is not a disclosure at all.\n\n"
            "## Not performed\n\n"
            "- 1.2 Something that did not happen\n"
        )
        offences = disclosure_offences(root)
        self.assertEqual(1, len(offences), offences)

    def test_each_silent_disclosure_is_reported_separately(self) -> None:
        """DERIVED -- no scenario states it. A check reporting one offence per
        file would tell an author to fix one of two silences."""
        root = self._fixture(
            "## Not performed\n\n"
            "- 1.2 Something that did not happen\n"
            "- 1.3 Something else that did not happen\n"
        )
        offences = disclosure_offences(root)
        self.assertEqual(2, len(offences), offences)

    def test_an_ordinary_task_list_raises_no_offence(self) -> None:
        """SPECIFIED -- the check reaches disclosures, not task lists. An
        outstanding `- [ ]` is the validating tool's business, and this suite is
        specified not to reimplement it."""
        root = self._fixture("# Tasks\n\n## 1. Section\n\n- [ ] 1.1 Outstanding\n- [x] 1.2 Done\n")
        self.assertEqual([], disclosure_offences(root))

    def test_the_section_ends_at_the_next_heading(self) -> None:
        """DERIVED -- no scenario states it. A section that ran to end of file
        would read every later task as a silent disclosure and make the check
        unsatisfiable."""
        root = self._fixture(
            "## Not performed\n\n"
            "- 1.2 Something that did not happen\n"
            "  Reason: it was declined on judgment.\n\n"
            "## 2. A later section\n\n"
            "- [ ] 2.1 An ordinary outstanding task\n"
        )
        self.assertEqual([], disclosure_offences(root))

    def test_a_heading_with_trailing_punctuation_still_opens_the_section(self) -> None:
        """SPECIFIED -- "in any `tasks.md` under the changes directory", read
        against the scenario it serves. An exact-match heading fails OPEN here:
        the section becomes invisible, the silent entry inside it goes
        unreported, and no checkbox is left for the validating tool to catch."""
        root = self._fixture("## Not performed:\n\n- 1.2 Something that did not happen\n")
        offences = disclosure_offences(root)
        self.assertEqual(1, len(offences), offences)

    def test_a_heading_with_a_trailing_parenthetical_still_opens_the_section(self) -> None:
        """SPECIFIED -- the same clause and the same fail-open, reached by the
        other ordinary author deviation."""
        root = self._fixture(
            "## Not performed (two tasks)\n\n"
            "- 1.2 Something that did not happen\n"
            "- 1.3 Something else that did not happen\n"
        )
        offences = disclosure_offences(root)
        self.assertEqual(2, len(offences), offences)

    def test_a_disclosure_written_as_prose_is_rejected(self) -> None:
        """SPECIFIED -- "A disclosed item that states no reason SHALL fail the
        check exactly as an unticked task does". A prose paragraph under the
        heading states no `Reason:` label the check can read, so accepting it
        would be accepting silence in the one shape the label cannot cover."""
        root = self._fixture(
            "## Not performed\n\n"
            "Task 1.2 was not performed, and the reasons are complicated enough that\n"
            "they are set out here rather than on a line of their own.\n"
        )
        offences = disclosure_offences(root)
        self.assertEqual(1, len(offences), offences)

    def test_a_section_that_discloses_nothing_is_rejected(self) -> None:
        """DERIVED -- no scenario states it. A heading with nothing under it is
        either a leftover or a disclosure that never got written; both read as a
        clean scan, which is what this check exists to make impossible."""
        root = self._fixture("# Tasks\n\n## Not performed\n\n## 2. A later section\n")
        offences = disclosure_offences(root)
        self.assertEqual(1, len(offences), offences)

    def test_prose_introducing_the_entries_is_accepted(self) -> None:
        """SPECIFIED -- the converse half of the two rejections above, and the
        shape the settled archived records actually use: a paragraph explaining
        why the section exists, then the entries. Without this, the empty-section
        rule would turn every one of those records red."""
        root = self._fixture(
            "## Not performed\n\n"
            "Three tasks in section 1 were not performed. They are moved here with\n"
            "their original dispositions preserved word for word.\n\n"
            "- 1.2 Something that did not happen\n"
            "  Reason: no credential for it existed in the authoring sandbox.\n"
        )
        self.assertEqual([], disclosure_offences(root))

    def test_a_numbered_section_merely_mentioning_the_phrase_is_not_a_disclosure(self) -> None:
        """DERIVED -- no scenario states it. The loose heading match must not
        reach an ordinary section whose title happens to contain the phrase: its
        outstanding `- [ ]` tasks are the validating tool's business, and reading
        them as silent disclosures would fail a change that did nothing wrong."""
        root = self._fixture(
            "# Tasks\n\n"
            "## 4. Settle the work not performed\n\n"
            "- [ ] 4.1 An ordinary outstanding task\n"
            "- [x] 4.2 A done one\n"
        )
        self.assertEqual([], disclosure_offences(root))

    def test_a_heading_quoted_inside_a_code_fence_opens_no_section(self) -> None:
        """DERIVED -- no scenario states it. Without fence awareness a quoted
        heading opens the section for the rest of the file, and every later task
        becomes an entry owing a reason: an unsatisfiable red on a change that
        did nothing wrong. This change's artifacts already quote the heading."""
        root = self._fixture(
            "# Tasks\n\n"
            "## 1. Section\n\n"
            "The disclosure format is:\n\n"
            "```markdown\n"
            "## Not performed\n\n"
            "- 1.2 The task\n"
            "  Reason: why\n"
            "```\n\n"
            "- [ ] 1.1 An ordinary outstanding task\n"
        )
        self.assertEqual([], disclosure_offences(root))

    def test_a_fenced_block_inside_a_real_section_does_not_end_it(self) -> None:
        """DERIVED -- no scenario states it. The converse half: fence awareness
        must not make a real section stop being read because an entry quotes
        something."""
        root = self._fixture(
            "## Not performed\n\n"
            "- 1.2 Something that did not happen\n"
            "  Reason: the command it needed was never available here:\n"
            "  ```\n"
            "  terraform plan\n"
            "  ```\n"
            "- 1.3 Something else that did not happen\n"
        )
        offences = disclosure_offences(root)
        self.assertEqual(1, len(offences), offences)
        self.assertIn("1.3", offences[0])

    def test_an_unterminated_fence_over_a_disclosure_heading_is_rejected(self) -> None:
        """DERIVED -- no scenario states it. An unterminated fence hides the rest
        of the file from the scan, which is the fence fix's own fail-open reached
        from the other side. Refused only where the file names the heading, so an
        unrelated malformed file is not this check's business."""
        root = self._fixture(
            "# Tasks\n\n"
            "```markdown\n"
            "## Not performed\n\n"
            "- 1.2 Something that did not happen\n"
        )
        offences = disclosure_offences(root)
        self.assertEqual(1, len(offences), offences)
        self.assertIn("code fence", offences[0])

    def test_an_active_change_is_scanned_as_well_as_an_archived_one(self) -> None:
        """SPECIFIED -- "in any `tasks.md` under the changes directory, archived
        or active". The first disclosure this repository writes is in an active
        change, before it is archived."""
        root = Path(tempfile.mkdtemp(prefix="not-performed-fixture-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        directory = root / "openspec" / CHANGES_DIRECTORY_NAME / "an-active-change"
        directory.mkdir(parents=True)
        (directory / "tasks.md").write_text(
            "## Not performed\n\n- 12.3 Something that did not happen\n", encoding="utf-8"
        )
        offences = disclosure_offences(root)
        self.assertEqual(1, len(offences), offences)


class TestTheArchivedRecordCorrectionRuleIsStated(unittest.TestCase):
    """ADDED requirement: The Specification Record Is Verified in Continuous
    Integration.

    The delta concedes one blind spot openly: a task deleted outright rather
    than disclosed is invisible both to the check above and to the validating
    tool. It delegates that case to a convention, and then obliges this suite to
    assert that the convention is stated -- because "a delegation to a rule
    nothing checks for is a delegation to nothing".

    These assertions establish only that the rule is STATED. They do not
    establish that it is followed; the deletion case still ends at a reviewer,
    and this is what makes the rule they review against durable.
    """

    def setUp(self) -> None:
        self.text = read_text(AGENTS_FILE)
        self.flat = flattened(self.text)

    def test_the_conventions_file_states_the_correction_rule(self) -> None:
        """SPECIFIED -- "That convention SHALL be stated in the repository-root
        `AGENTS.md`, and that it is stated there SHALL itself be asserted by the
        suite".

        Matched on the rule's own words, because the delta requires the assertion
        to be "written so that rephrasing the rule fails it, rather than so that
        a rephrasing which inverts the rule passes". A rephrasing failing here is
        the intended behaviour: this wording is what a reviewer relies on, so a
        change to it is a reviewed event rather than an editorial one.
        """
        missing = [fragment for fragment in CORRECTION_RULE_FRAGMENTS if fragment not in self.flat]
        self.assertEqual(
            [],
            missing,
            "AGENTS.md does not state the archived-record correction rule in the "
            f"words this assertion is written against: {missing} not found. The rule "
            "is that an archived change's record may be corrected only to make it "
            "say what actually happened, with the evidence cited, and never to "
            "change what was decided or built",
        )

    def test_the_correction_rule_requires_the_evidence_to_be_cited(self) -> None:
        """DERIVED -- the delta states the rule as "corrected only to say what
        actually happened" and does not mention evidence; the evidence clause
        comes from that change's design.md Decision 2 and its tasks.md 5.2. It is
        asserted near the rule rather than anywhere in the file, so an unrelated
        use of the word cannot satisfy it."""
        anchor = self.flat.find(CORRECTION_RULE_ANCHOR)
        self.assertNotEqual(
            -1,
            anchor,
            f"AGENTS.md does not state {CORRECTION_RULE_ANCHOR!r}, so there is no "
            "correction rule for this assertion to read",
        )
        neighbourhood = self.flat[anchor : anchor + CORRECTION_RULE_LOCALITY]
        self.assertIn(
            "evidence",
            neighbourhood,
            "the correction rule does not require the correction's evidence to be "
            "cited, so a retroactive tick asserting nothing would satisfy it",
        )

    def test_the_correction_rule_is_stated_outside_the_generated_block(self) -> None:
        """DERIVED -- no scenario states it. That change's design.md Decision 4
        records that the workflow block at the top of AGENTS.md is generated and
        replaced on update: a rule stated inside it is a rule that disappears on
        the next regeneration, which would satisfy the assertion above today and
        silently stop being true."""
        end = self.text.find(MANAGED_BLOCK_END)
        self.assertNotEqual(
            -1,
            end,
            f"AGENTS.md carries no {MANAGED_BLOCK_END!r} marker, so this assertion "
            "cannot tell the generated block from the project's own conventions",
        )
        below = flattened(self.text[end + len(MANAGED_BLOCK_END) :])
        missing = [fragment for fragment in CORRECTION_RULE_FRAGMENTS if fragment not in below]
        self.assertEqual(
            [],
            missing,
            "the archived-record correction rule is not stated below the generated "
            f"workflow block, so it sits where the next regeneration replaces it: "
            f"{missing} not found there",
        )


# --------------------------------------------------------------------------
# iac-host-configuration / Container Logs Are Bounded by the Host's Daemon
# Configuration
# --------------------------------------------------------------------------


class TestDockerLogBoundCannotBeUnset(unittest.TestCase):
    """The `docker` wrapper composes `/etc/docker/daemon.json` by merging a
    caller-supplied `docker_daemon_extra_options` with its own log ceiling.

    The ORDER of that merge is the whole guarantee. `combine` lets the
    right-hand operand win, so the ceiling must be second: a caller can then add
    any daemon option and cannot remove the bound. Reversed, a scenario or a
    host adding an unrelated option could silently drop `max-size` -- and the
    rendered file would look entirely reasonable.

    Nothing else in this repository would notice. The `docker` role's Molecule
    scenario supplies no variables by design, and the three scenarios that do
    pass `docker_daemon_extra_options` pass only `storage-driver` and
    `features`, which never collide with the log keys -- so the operands can be
    swapped and every Molecule scenario stays green. That is why the check lives
    here: it is a static read of a committed file, which is this suite's remit,
    and it is the only place the polarity is observable at all.

    Bounded claim: this checks the operands of the FIRST `combine`. A
    re-application -- `extra | combine(bound) | combine(extra)` -- would put
    `extra` on the left and the log keys after that first `combine(`, so both
    assertions below would pass while the polarity was in fact broken. That
    shape is contrived enough not to be worth parsing for; it is named so the
    claim above is read as "the only place it is observed", not "the only way
    it could be broken".
    """

    META = ROOT / "ansible" / "roles" / "docker" / "meta" / "main.yml"

    def setUp(self) -> None:
        self.dependencies = load_yaml(self.META).get("dependencies") or []
        self.entry = next(
            (
                dep
                for dep in self.dependencies
                if isinstance(dep, dict) and dep.get("role") == "geerlingguy.docker"
            ),
            None,
        )

    def test_the_wrapper_supplies_daemon_options_to_the_external_role(self) -> None:
        self.assertIsNotNone(
            self.entry,
            "ansible/roles/docker/meta/main.yml no longer depends on geerlingguy.docker",
        )
        self.assertIn(
            "docker_daemon_options",
            self.entry,
            "the docker wrapper no longer passes docker_daemon_options, so nothing "
            "renders /etc/docker/daemon.json and no container log is bounded",
        )

    def test_the_log_bound_is_merged_last_so_it_cannot_be_unset(self) -> None:
        expression = str(self.entry["docker_daemon_options"])
        combine = re.search(r"\|\s*combine\(", expression)
        self.assertIsNotNone(
            combine,
            "docker_daemon_options is no longer composed with `combine`; if the "
            "extra-options passthrough was removed, delete this test with it, and "
            "if it was kept, the polarity below still has to hold",
        )
        before, after = expression[: combine.start()], expression[combine.end() :]
        self.assertIn(
            "docker_daemon_extra_options",
            before,
            "docker_daemon_extra_options is not the LEFT operand of `combine`. "
            "Whatever is on the right wins, so a caller's extra options would "
            "override the log ceiling -- exactly the silent unset this "
            "arrangement exists to prevent.",
        )
        for key in ("log-driver", "max-size", "max-file"):
            self.assertIn(
                key,
                after,
                f"{key!r} is not in the RIGHT operand of `combine`, so it is not "
                "what wins the merge. The log ceiling has to be applied last.",
            )


# --------------------------------------------------------------------------
# Molecule's shared state across working trees is stated in AGENTS.md.
#
# This is a static read of a committed file, so it belongs here (AGENTS.md,
# "Testing"). It asserts only that the hazard is STATED -- nothing here can
# establish that a session heeded it.
#
# It exists because the knowledge has already been lost once. It was recorded
# in a `docs/change-queue.md` entry, that entry was deleted when its change
# archived, as the queue's own rule requires, and two later sessions then spent
# time rediscovering it. Moving the text into AGENTS.md is what makes it
# durable against archiving; this assertion is what makes it durable against
# an editorial pass, by turning its removal into a red required check rather
# than a silent deletion no reviewer is guaranteed to notice.
#
# Matched on the hazard's own load-bearing words rather than on a heading, for
# the reason the archived-record correction rule is matched that way: a
# rephrasing SHOULD fail here. The wording is what a session reads before
# trusting a Molecule result, so changing it is a reviewed event.
#
# Deliberately NOT asserted: the count of shared handles. The entry that
# recorded this hazard named three, and the third -- `~/.cache/molecule/<role>`
# -- proved not to be written by the pinned toolchain at all. A count is the
# part of this knowledge most likely to go stale against a Molecule upgrade,
# and a check pinning one would fail for a correct file.
# --------------------------------------------------------------------------

MOLECULE_SHARED_STATE_FRAGMENTS = (
    "shared across working trees",
    "the same container",
    "basename",
    "rc 137",
    "can equally pass",
)
MOLECULE_SHARED_STATE_ANCHOR = "shared across working trees"
MOLECULE_SHARED_STATE_LOCALITY = 2000


class TestTheConventionsFileStatesTheMoleculeSharedStateHazard(unittest.TestCase):
    """DERIVED -- this change declares no specification deltas. The rule it
    guards is AGENTS.md's own Testing section, and what makes the guard worth
    having is recorded in the block above."""

    def setUp(self) -> None:
        self.text = read_text(AGENTS_FILE)
        self.flat = flattened(self.text)

    def test_the_conventions_file_states_the_hazard(self) -> None:
        missing = [
            fragment for fragment in MOLECULE_SHARED_STATE_FRAGMENTS if fragment not in self.flat
        ]
        self.assertEqual(
            [],
            missing,
            "AGENTS.md does not state the Molecule shared-state hazard in the words "
            f"this assertion is written against: {missing} not found. The hazard is "
            "that Molecule's instance name and ephemeral directory are shared across "
            "working trees and stable per role, so two sessions running one role "
            "drive the same container -- and that such a run can pass as readily as "
            "it fails",
        )

    def test_the_hazard_names_what_a_colliding_run_looks_like(self) -> None:
        """A statement of the hazard that does not say how it PRESENTS leaves a
        session to read `rc 137` as a module bug, which is the misreading that
        cost the two sessions their time. Asserted near the hazard rather than
        anywhere in the file, so an unrelated mention cannot satisfy it."""
        anchor = self.flat.find(MOLECULE_SHARED_STATE_ANCHOR)
        self.assertNotEqual(
            -1,
            anchor,
            f"AGENTS.md does not state {MOLECULE_SHARED_STATE_ANCHOR!r}, so there is "
            "no statement of the hazard for this assertion to read",
        )
        neighbourhood = self.flat[anchor : anchor + MOLECULE_SHARED_STATE_LOCALITY]
        for fragment in ("rc 137", "can equally pass"):
            self.assertIn(
                fragment,
                neighbourhood,
                f"the Molecule shared-state hazard is stated without {fragment!r} "
                "near it, so a session meeting a collision has nothing to recognise "
                "it by",
            )

    def test_the_hazard_is_stated_outside_the_generated_block(self) -> None:
        """The workflow block at the top of AGENTS.md is generated and replaced
        on update, so a statement inside it is one the next regeneration
        deletes -- the same disappearance this whole entry exists to prevent,
        reached by a different route."""
        end = self.text.find(MANAGED_BLOCK_END)
        self.assertNotEqual(
            -1,
            end,
            f"AGENTS.md carries no {MANAGED_BLOCK_END!r} marker, so this assertion "
            "cannot tell the generated block from the project's own conventions",
        )
        below = flattened(self.text[end + len(MANAGED_BLOCK_END) :])
        missing = [
            fragment for fragment in MOLECULE_SHARED_STATE_FRAGMENTS if fragment not in below
        ]
        self.assertEqual(
            [],
            missing,
            "the Molecule shared-state hazard is not stated below the generated "
            "workflow block, so it sits where the next regeneration replaces it: "
            f"{missing} not found there",
        )


# --------------------------------------------------------------------------
# The suite stays green in the repository's MAIN working tree.
#
# The obligation was recorded in `docs/change-queue.md` until this change
# deleted that entry, as the queue's own rule requires; the account below is
# self-contained so that nothing here cites a note that no longer exists.
#
# Two fixes, deliberately separate, because the entry proposed the cheaper one
# as though it were sufficient and it is not:
#
#   - `terraform_lockfile_directories()` now walks with `walked_files()`, whose
#     prune list already carried `.worktrees` and `.claude/worktrees`. This is
#     what turns the suite green; the assertion below fails against the `rglob`
#     it replaces.
#   - `.gitignore` now names both working-tree roots. This does NOTHING for the
#     walk -- a filesystem walk does not consult git -- and is worth having for
#     the entry's other reason: it stops a `git add -A` from the main working
#     tree staging a duplicate copy of the whole repository.
#
# Both are asserted, because each would otherwise be undone without a red
# check: the walker by someone reaching for `rglob` again, and the ignore line
# by an editorial pass through a file nothing else reads.
# --------------------------------------------------------------------------

GITIGNORE_FILE = ROOT / ".gitignore"
WORKING_TREE_ROOTS = (".worktrees/", ".claude/worktrees/")


class TestLockfileDiscoveryPrunesWorkingTrees(unittest.TestCase):
    """DERIVED -- this change declares no specification deltas. The requirement
    the repaired assertion serves is unchanged (`iac-cicd-pipeline`'s Dependabot
    coverage); what is asserted here is that discovery reads the repository and
    not the copies of it that AGENTS.md requires to live inside it.
    """

    def tree_with_worktrees(self) -> Path:
        """A fixture tree holding one real lockfile directory and one phantom
        per working-tree root, arranged as a worktree actually arranges them:
        a full copy of the repository nested inside it."""
        root = Path(tempfile.mkdtemp(prefix="worktree-prune-fixture-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for relative in (
            "terraform/environments/prod",
            "terraform/modules/server",
            ".claude/worktrees/some-change/terraform/environments/prod",
            ".claude/worktrees/some-change/terraform/modules/server",
            ".worktrees/another-change/terraform/environments/prod",
        ):
            directory = root / relative
            directory.mkdir(parents=True)
            (directory / ".terraform.lock.hcl").write_text("# fixture\n", encoding="utf-8")
        return root

    def test_discovery_ignores_lockfiles_inside_working_trees(self) -> None:
        root = self.tree_with_worktrees()
        self.assertEqual(
            {"/terraform/environments/prod", "/terraform/modules/server"},
            terraform_lockfile_directories(root),
            "lockfile discovery reached inside a working tree, so every change in "
            "progress adds a phantom directory that no Dependabot entry can ever "
            "name -- a red suite whose redness means nothing",
        )

    def test_discovery_still_finds_the_repository_s_own_lockfiles(self) -> None:
        """The failure mode of a prune is over-pruning, and it fails SILENTLY:
        the assertion this feeds guards vacuity with `assertTrue(actual)`, so a
        discovery returning nothing would be caught, but one returning a subset
        would pass while covering less than it claims. Read against the real
        tree, where the answer is known."""
        found = terraform_lockfile_directories()
        self.assertIn(
            "/terraform/environments/prod",
            found,
            "lockfile discovery no longer finds the prod environment's own "
            f"lockfile, so the Dependabot coverage check reads less than the "
            f"repository holds: {sorted(found)}",
        )


class TestTheWorkingTreeRootsAreIgnored(unittest.TestCase):
    """DERIVED -- no scenario states it. Both roots were untracked AND unignored,
    so each showed up in `git status` from the main working tree and stood one
    `git add -A` away from a full copy of the repository being committed into
    it."""

    def setUp(self) -> None:
        self.lines = {
            line.strip()
            for line in read_text(GITIGNORE_FILE).splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

    def test_both_working_tree_roots_are_ignored(self) -> None:
        missing = [root for root in WORKING_TREE_ROOTS if root not in self.lines]
        self.assertEqual(
            [],
            missing,
            f".gitignore does not ignore {missing}, so a working tree there is "
            "untracked and unignored -- it shows up in `git status` and a "
            "`git add -A` from the main working tree stages a full copy of the "
            "repository",
        )

    def test_the_claude_directory_is_not_ignored_wholesale(self) -> None:
        """`.claude/commands/` and `.claude/skills/` are committed. Ignoring
        `.claude/` outright would satisfy the assertion above by removing them
        from version control, which is the wrong fix arrived at by the right
        words."""
        for pattern in (".claude", ".claude/", "/.claude", "/.claude/"):
            self.assertNotIn(
                pattern,
                self.lines,
                f".gitignore ignores {pattern!r} wholesale, which would drop the "
                "committed files under .claude/ from version control",
            )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Ansible Configuration Is Verified in Continuous
# Integration and Gates the Merge -- its instance-name and host-name clauses.
# iac-repo-foundations / Verification Writing to Shared State Is Namespaced
# per Working Tree -- its "The binding is stated, not merely implied" scenario.
#
# Derived from the delta specs of the OpenSpec change
# `namespace-the-molecule-suite-per-working-tree`, before any implementation of
# that change existed. See that change's test-plan.md for the
# scenario-to-test mapping, the baseline, and the scenarios deliberately left
# uncovered. Several of that change's run-time scenarios are properties of TWO
# working trees at once, or of state left on the machine between sessions.
# Neither this suite nor a Molecule scenario can observe those: this suite may
# not start a container, and a Molecule scenario runs inside one container in
# one working tree and cannot observe Molecule's own `create` refusing. They
# are recorded as gaps in that manifest rather than covered here by something
# weaker wearing their name.
#
# What IS here is the static half, and it belongs here for the reason AGENTS.md
# ("Testing") gives: a property of a `molecule.yml` is a static read of a
# committed file, while the behaviour that scenario exercises is Molecule's.
# These read the same scenario definitions the digest-pinning checks above
# already read, through the same `authored_scenario_files()`, so a scenario
# added later is covered without an edit here and installed Galaxy content is
# excluded by the same manifest-derived rule rather than by a second list.
#
# Nothing below needs a network call, a credential, a container runtime or a
# Terraform binary, and nothing below adds an import.
# --------------------------------------------------------------------------

# Molecule's own interpolation, in the forms `molecule/interpolation.py`
# actually resolves: `${VAR}`, `${VAR:-default}` and `${VAR-default}`. There is
# no `:?` error form, so an unset variable substitutes EMPTY rather than
# failing -- which is why the DEFAULT's own form is what has to fail closed
# (design.md Decision 4) and why the check below reads it.
SCENARIO_INTERPOLATION = re.compile(
    r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::?-(?P<default>[^}]*))?\}"
)

# Docker's container-name grammar. A string matching it in FULL is one Docker
# will accept, which is exactly what a name resolved with the namespace unset
# must not be: a default that creates an instance successfully reinstates the
# shared literal under a different spelling.
DOCKER_CONTAINER_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*")

# Linux caps a host name at 64 bytes, and the docker driver derives a
# container's host name from its instance name where the scenario declares
# none. Verified by running, against this change's own working tree: a
# 70-character instance name fails at `create` with
# `Bad Request ("hostname is too long (maximum 64 bytes)")`, and the same name
# creates once a short explicit `hostname` is declared (design.md Decision 3a).
HOSTNAME_BYTE_LIMIT = 64

# Stands in for whatever the namespace resolves to, so that two scenarios which
# differ ONLY inside their interpolation are seen to collide: within one
# working tree the namespace is one value, so they would resolve to one name.
NAMESPACE_PLACEHOLDER = "<namespace>"


def scenario_platform_declarations(root: Path | None = None):
    """Yield (scenario, platform, declaration) over every authored scenario.

    `declaration` is the platform's own mapping, or None where the document
    cannot be parsed, declares no `platforms:`, declares an empty one, or
    declares an entry that is not a mapping. None is yielded rather than the
    entry being passed over, for the reason `scenario_platform_images()` gives:
    a scenario silently exempted from a check is indistinguishable from one
    that satisfies it.
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
            if not isinstance(platform, dict):
                yield label, f"platforms[{index}]", None
                continue
            name = platform.get("name")
            suffix = f" ({name})" if isinstance(name, str) and name.strip() else ""
            yield label, f"platforms[{index}]{suffix}", platform


def declared_field(declaration: object, field: str) -> str | None:
    """The platform's `field`, or None where it is absent, empty, or not a
    string."""
    if not isinstance(declaration, dict):
        return None
    value = declaration.get(field)
    return value if isinstance(value, str) and value.strip() else None


def name_with_the_namespace_unset(name: str) -> str:
    """The name Molecule hands the driver when nothing supplies the namespace:
    every interpolation replaced by its declared default, or by the empty
    string where it declares none."""
    return SCENARIO_INTERPOLATION.sub(lambda match: match.group("default") or "", name)


def name_with_the_namespace_elided(name: str) -> str:
    return SCENARIO_INTERPOLATION.sub(NAMESPACE_PLACEHOLDER, name)


def scenario_names_carrying_no_namespace(root: Path | None = None) -> list[str]:
    """Report each platform whose instance name is a bare literal -- shared by
    every working tree on the machine -- or which declares no name at all."""
    offenders = []
    for scenario, platform, declaration in scenario_platform_declarations(root):
        name = declared_field(declaration, "name")
        if name is None:
            offenders.append(f"{scenario}: {platform} declares no instance name to read")
        elif not SCENARIO_INTERPOLATION.search(name):
            offenders.append(f"{scenario}: {platform} -> {name}")
    return offenders


def scenario_names_whose_unset_default_names_a_container(
    root: Path | None = None,
) -> list[str]:
    """Report each interpolated instance name that STILL names a container when
    the namespace is unset.

    Names carrying no interpolation are left to the check above rather than
    reported twice; the two properties are distinct and read better apart.
    """
    offenders = []
    for scenario, platform, declaration in scenario_platform_declarations(root):
        name = declared_field(declaration, "name")
        if name is None or not SCENARIO_INTERPOLATION.search(name):
            continue
        resolved = name_with_the_namespace_unset(name)
        if DOCKER_CONTAINER_NAME.fullmatch(resolved):
            offenders.append(
                f"{scenario}: {platform} -> {name} resolves to {resolved!r} with the "
                f"namespace unset, which Docker accepts as a container name"
            )
    return offenders


def scenario_namespace_variables(root: Path | None = None) -> dict[str, list[str]]:
    """Every variable the authored instance names interpolate, and where."""
    found: dict[str, list[str]] = {}
    for scenario, platform, declaration in scenario_platform_declarations(root):
        name = declared_field(declaration, "name")
        if name is None:
            continue
        for match in SCENARIO_INTERPOLATION.finditer(name):
            found.setdefault(match.group("name"), []).append(f"{scenario}: {platform}")
    return found


def scenario_names_colliding_within_one_working_tree(
    root: Path | None = None,
) -> list[str]:
    """Report each resolved name more than one platform would take inside one
    working tree, where the namespace is a single value."""
    by_resolved: dict[str, list[str]] = {}
    for scenario, platform, declaration in scenario_platform_declarations(root):
        name = declared_field(declaration, "name")
        if name is None:
            continue
        by_resolved.setdefault(name_with_the_namespace_elided(name), []).append(
            f"{scenario}: {platform}"
        )
    return sorted(
        f"{resolved} is declared by {sorted(where)}"
        for resolved, where in by_resolved.items()
        if len(where) > 1
    )


def scenarios_declaring_no_explicit_host_name(root: Path | None = None) -> list[str]:
    offenders = []
    for scenario, platform, declaration in scenario_platform_declarations(root):
        if declared_field(declaration, "hostname") is None:
            offenders.append(f"{scenario}: {platform}")
    return offenders


def host_names_not_bounded_independently_of_the_instance_name(
    root: Path | None = None,
) -> list[str]:
    """Report each declared host name the 64-byte limit is not known to hold
    for: one carrying an interpolation, whose length is therefore decided by
    the working tree rather than by the scenario, or one already over it."""
    offenders = []
    for scenario, platform, declaration in scenario_platform_declarations(root):
        hostname = declared_field(declaration, "hostname")
        if hostname is None:
            continue
        if "$" in hostname:
            offenders.append(
                f"{scenario}: {platform} -> hostname {hostname!r} is interpolated, so "
                f"its length is decided by the working tree rather than by the scenario"
            )
            continue
        size = len(hostname.encode("utf-8"))
        if size > HOSTNAME_BYTE_LIMIT:
            offenders.append(
                f"{scenario}: {platform} -> hostname {hostname!r} is {size} bytes, over "
                f"the {HOSTNAME_BYTE_LIMIT}-byte limit `create` enforces"
            )
    return offenders


# The variable name below is a FIXTURE's, not a constraint on the
# implementation: nothing here reads it, and every check above reads whatever
# variable a scenario names. design.md Decision 5 rules out a
# `MOLECULE_`-prefixed one, which is why this fixture does not use one either.
FIXTURE_NAMESPACE_VARIABLE = "WORKTREE_NAMESPACE"

# A default containing a character Docker forbids in a container name, so a run
# with nothing set fails at `create` and the message says what to set.
FIXTURE_REFUSING_DEFAULT = "unset:run-molecule-through-the-entry-point"


def namespaced_scenario_document(
    name: str,
    hostname: str | None = "instance",
    image: str | None = PINNED_IMAGE,
) -> str:
    """A structurally real scenario definition whose instance name and host name
    a fixture chooses. `scenario_document()` above builds the same shape for the
    pinning checks; this one adds the two fields these checks read."""
    body = f'---\ndriver:\n  name: docker\nplatforms:\n  - name: "{name}"\n'
    if hostname is not None:
        body += f'    hostname: "{hostname}"\n'
    if image is not None:
        body += f"    image: {image}\n"
    return body


class TestEveryAuthoredScenarioNamesItsInstancePerWorkingTree(
    ScenarioTreeFixtureMixin, unittest.TestCase
):
    """MODIFIED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge -- the clause obliging every scenario to
    declare an instance name resolving per working tree, a default that cannot
    name a container at all, and an explicit host name.

    Read against the real tree. The class below runs the same checks against
    fixture trees, which is what establishes that they discriminate.
    """

    def test_every_authored_scenarios_instance_name_carries_the_namespace(self) -> None:
        """SPECIFIED -- scenario "Every authored scenario's instance name carries
        the namespace": "every declared instance name SHALL carry the
        working-tree namespace ... a scenario declaring a bare literal name ...
        SHALL fail those checks".

        WHICH variable carries it is deliberately not asserted: the requirement
        obliges the name to resolve per working tree, not to spell one
        identifier, and pinning a spelling here would oblige an implementation
        to a name no artifact of this change fixes.
        """
        offenders = scenario_names_carrying_no_namespace()
        self.assertEqual(
            [],
            offenders,
            f"these instance names are literals shared by every working tree on the "
            f"machine, so two sessions running the role drive one container: "
            f"{offenders}",
        )

    def test_every_authored_scenarios_unset_default_cannot_name_a_container(self) -> None:
        """SPECIFIED -- the second half of the same scenario: "its default SHALL
        be one that cannot name a container at all rather than one that merely
        looks wrong; ... a default that would successfully create a shared
        instance, SHALL fail those checks".

        Molecule substitutes EMPTY for an unset variable and has no error form,
        so a name spelled `${VAR}` fails OPEN -- it resolves to the old shared
        literal with an empty tail. This check reads the RESOLVED string, which
        catches that alongside a benign `-unset` default.

        Guarded against reading nothing: a tree whose names interpolate nothing
        has no default to inspect, and this assertion would pass over it in
        silence -- which is how it would read on the arrangement before this
        change, and on any later one that removed the namespace outright.
        """
        self.assertTrue(
            scenario_namespace_variables(),
            "no authored instance name interpolates anything, so there is no "
            "default for this assertion to read and its silence establishes "
            "nothing",
        )
        offenders = scenario_names_whose_unset_default_names_a_container()
        self.assertEqual(
            [],
            offenders,
            f"a run started with no namespace would create these instances rather "
            f"than refusing, which reinstates the shared name under another "
            f"spelling: {offenders}",
        )

    def test_the_authored_scenarios_agree_on_one_namespace_variable(self) -> None:
        """DERIVED -- no scenario states it. The requirement says "the
        working-tree namespace", singular, and a session sets one variable
        before running the suite; a scenario reading a second one would be
        namespaced only for a session that happened to know about it, and would
        silently keep a shared name for every other.
        """
        variables = scenario_namespace_variables()
        self.assertTrue(
            variables,
            "no authored scenario interpolates anything into its instance name, so "
            "there is no namespace for this assertion to read",
        )
        self.assertEqual(
            1,
            len(variables),
            f"the authored scenarios interpolate more than one variable into their "
            f"instance names, so setting the one a session knows about leaves the "
            f"others on a shared name: "
            f"{ {name: sorted(where) for name, where in variables.items()} }",
        )

    def test_no_two_authored_scenarios_resolve_to_one_name_within_a_working_tree(
        self,
    ) -> None:
        """DERIVED -- tasks.md 2.2 ("no two names collide within one working
        tree"); no scenario states it. Within one working tree the namespace is
        a single value, so two scenarios differing only inside their
        interpolation resolve to one container -- the collision this change
        exists to remove, reproduced inside a single session.
        """
        offenders = scenario_names_colliding_within_one_working_tree()
        self.assertEqual(
            [],
            offenders,
            f"these scenarios resolve to one instance name inside a working tree, so "
            f"a sibling's live container collides with them on `create`: {offenders}",
        )

    def test_every_authored_scenario_declares_an_explicit_host_name(self) -> None:
        """SPECIFIED -- scenario "Every authored scenario bounds its instance's
        host name": "every scenario SHALL declare an explicit host name for its
        instance, and a scenario declaring none SHALL fail those checks"."""
        offenders = scenarios_declaring_no_explicit_host_name()
        self.assertEqual(
            [],
            offenders,
            f"these platforms declare no `hostname`, so the docker driver derives one "
            f"from the namespaced instance name and `create` fails once a working "
            f"tree's own name grows past {HOSTNAME_BYTE_LIMIT} bytes: {offenders}",
        )

    def test_every_declared_host_name_is_bounded_by_the_scenario_itself(self) -> None:
        """SPECIFIED -- the same scenario's "bounded independently of the
        instance name". A host name interpolating the namespace would be bounded
        by the working tree's own name again, which is the thing the `hostname`
        field exists to stop being true.

        This establishes the limit is respected by what the file DECLARES. That
        the docker driver then creates the instance is a run-time property of a
        container this suite may not start -- see test-plan.md.

        Guarded against reading nothing, for the reason its sibling above gives:
        a tree declaring no `hostname` anywhere leaves this check inspecting an
        empty set, which passes while establishing nothing.
        """
        self.assertEqual(
            [],
            scenarios_declaring_no_explicit_host_name(),
            "some scenario declares no `hostname`, so this assertion is reading a "
            "partial set; the sibling assertion above names them",
        )
        offenders = host_names_not_bounded_independently_of_the_instance_name()
        self.assertEqual(
            [],
            offenders,
            f"these host names are not bounded by the scenario that declares them: "
            f"{offenders}",
        )


class TestTheInstanceNameChecksAreARealReadOfTheFile(
    ScenarioTreeFixtureMixin, unittest.TestCase
):
    """MODIFIED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge.

    The class above would pass identically if every check returned an empty list
    unconditionally. These run the same checks against fixture trees carrying
    each defect the requirement names, so that a green result there means the
    checks discriminate rather than that they read nothing.
    """

    NAMESPACED = f"instance-${{{FIXTURE_NAMESPACE_VARIABLE}:-{FIXTURE_REFUSING_DEFAULT}}}"

    def test_a_bare_literal_name_is_reported(self) -> None:
        """SPECIFIED -- "a scenario declaring a bare literal name ... SHALL fail
        those checks". This is the shape of every scenario's name before this
        change."""
        root = self.scratch_tree(
            {
                ("literal", "default"): namespaced_scenario_document("swap-role-instance"),
                ("namespaced", "default"): namespaced_scenario_document(self.NAMESPACED),
            }
        )
        offenders = scenario_names_carrying_no_namespace(root)
        self.assertEqual(1, len(offenders), f"expected exactly the literal: {offenders}")
        self.assertIn("ansible/roles/literal/molecule/default/molecule.yml", offenders[0])
        self.assertIn("swap-role-instance", offenders[0])

    def test_a_benign_default_that_would_still_create_an_instance_is_reported(self) -> None:
        """SPECIFIED -- "its default SHALL be one that cannot name a container at
        all rather than one that merely looks wrong".

        `-unset` is the alternative design.md Decision 4 rejects by name: it
        makes the mistake visible in `docker ps` while still letting two
        forgetful sessions collide, which is the same fail-open wearing a label.
        A check looking only for the PRESENCE of an interpolation would pass it.
        """
        root = self.scratch_tree(
            {
                ("benign", "default"): namespaced_scenario_document(
                    f"instance-${{{FIXTURE_NAMESPACE_VARIABLE}:-unset}}"
                ),
            }
        )
        self.assertEqual(
            [],
            scenario_names_carrying_no_namespace(root),
            "a benign default was reported as carrying no namespace at all, which is "
            "not the defect it has",
        )
        offenders = scenario_names_whose_unset_default_names_a_container(root)
        self.assertEqual(
            1, len(offenders), f"the benign default was not reported: {offenders}"
        )
        self.assertIn("instance-unset", offenders[0])

    def test_an_interpolation_declaring_no_default_at_all_is_reported(self) -> None:
        """SPECIFIED -- the same clause, reached by the route design.md Decision 4
        says is the naive one: Molecule substitutes EMPTY for an unset variable,
        so `${VAR}` resolves to the old shared literal with an empty tail and
        creates it."""
        root = self.scratch_tree(
            {
                ("no_default", "default"): namespaced_scenario_document(
                    f"swap-role-instance-${{{FIXTURE_NAMESPACE_VARIABLE}}}"
                ),
            }
        )
        offenders = scenario_names_whose_unset_default_names_a_container(root)
        self.assertEqual(
            1, len(offenders), f"the empty substitution was not reported: {offenders}"
        )
        self.assertIn("swap-role-instance-", offenders[0])

    def test_a_default_that_cannot_name_a_container_is_accepted(self) -> None:
        """SPECIFIED -- the positive half. Without it the two checks above would
        be satisfied by one rejecting every default, which would leave no name
        able to pass."""
        root = self.scratch_tree(
            {("ok", "default"): namespaced_scenario_document(self.NAMESPACED)}
        )
        self.assertEqual([], scenario_names_carrying_no_namespace(root))
        self.assertEqual([], scenario_names_whose_unset_default_names_a_container(root))
        self.assertEqual([], scenarios_declaring_no_explicit_host_name(root))
        self.assertEqual([], host_names_not_bounded_independently_of_the_instance_name(root))

    def test_a_scenario_declaring_no_platform_is_reported_rather_than_passed_over(
        self,
    ) -> None:
        """SPECIFIED -- the same reason its sibling pinning check gives: a
        scenario silently exempted from a check is indistinguishable from one
        that satisfies it. Three shapes leave nothing to read."""
        root = self.scratch_tree(
            {
                ("no_platforms", "default"): "---\ndriver:\n  name: docker\n",
                ("empty_platforms", "default"): "---\ndriver:\n  name: docker\nplatforms: []\n",
                ("no_name", "default"): (
                    "---\ndriver:\n  name: docker\nplatforms:\n  - hostname: instance\n"
                ),
                ("ok", "default"): namespaced_scenario_document(self.NAMESPACED),
            }
        )
        offenders = scenario_names_carrying_no_namespace(root)
        self.assertEqual(3, len(offenders), f"expected three scenarios reported: {offenders}")
        for role in ("no_platforms", "empty_platforms", "no_name"):
            self.assertTrue(
                any(f"ansible/roles/{role}/molecule/default/" in entry for entry in offenders),
                f"the scenario under {role}/ was passed over rather than identified: "
                f"{offenders}",
            )
        self.assertFalse(any("/ok/" in entry for entry in offenders))

    def test_a_scenario_declaring_no_host_name_is_reported(self) -> None:
        """SPECIFIED -- "a scenario declaring none SHALL fail those checks"."""
        root = self.scratch_tree(
            {
                ("bare", "default"): namespaced_scenario_document(
                    self.NAMESPACED, hostname=None
                ),
                ("ok", "default"): namespaced_scenario_document(self.NAMESPACED),
            }
        )
        offenders = scenarios_declaring_no_explicit_host_name(root)
        self.assertEqual(1, len(offenders), f"expected exactly the bare scenario: {offenders}")
        self.assertIn("ansible/roles/bare/molecule/default/molecule.yml", offenders[0])

    def test_a_host_name_interpolating_the_namespace_is_reported(self) -> None:
        """SPECIFIED -- "bounded independently of the instance name". A
        `hostname` carrying the namespace would be back under the working tree's
        own length, which is precisely the failure the field exists to prevent
        -- and a check testing only for the field's PRESENCE would pass it."""
        root = self.scratch_tree(
            {
                ("derived", "default"): namespaced_scenario_document(
                    self.NAMESPACED,
                    hostname=f"instance-${{{FIXTURE_NAMESPACE_VARIABLE}}}",
                ),
            }
        )
        offenders = host_names_not_bounded_independently_of_the_instance_name(root)
        self.assertEqual(
            1, len(offenders), f"the interpolated host name was not reported: {offenders}"
        )
        self.assertIn("interpolated", offenders[0])

    def test_a_host_name_over_the_byte_limit_is_reported(self) -> None:
        """SPECIFIED -- the limit itself. 65 bytes is one past what `create`
        accepted in the run design.md Decision 3a records; the sibling at
        exactly the limit is asserted NOT to be reported, so the boundary is
        established rather than assumed."""
        root = self.scratch_tree(
            {
                ("long", "default"): namespaced_scenario_document(
                    self.NAMESPACED, hostname="a" * (HOSTNAME_BYTE_LIMIT + 1)
                ),
                ("at_limit", "default"): namespaced_scenario_document(
                    self.NAMESPACED, hostname="b" * HOSTNAME_BYTE_LIMIT
                ),
            }
        )
        offenders = host_names_not_bounded_independently_of_the_instance_name(root)
        self.assertEqual(1, len(offenders), f"expected exactly the over-long name: {offenders}")
        self.assertIn("ansible/roles/long/molecule/default/molecule.yml", offenders[0])
        self.assertIn(str(HOSTNAME_BYTE_LIMIT + 1), offenders[0])

    def test_two_scenarios_resolving_to_one_name_are_reported(self) -> None:
        """DERIVED -- tasks.md 2.2. Two scenarios whose literal parts agree
        resolve to one container inside any single working tree, however well
        namespaced they are against another tree."""
        root = self.scratch_tree(
            {
                ("role_a", "default"): namespaced_scenario_document(self.NAMESPACED),
                ("role_b", "default"): namespaced_scenario_document(self.NAMESPACED),
                ("role_c", "default"): namespaced_scenario_document(f"other-{self.NAMESPACED}"),
            }
        )
        offenders = scenario_names_colliding_within_one_working_tree(root)
        self.assertEqual(1, len(offenders), f"expected exactly the shared name: {offenders}")
        self.assertIn("role_a", offenders[0])
        self.assertIn("role_b", offenders[0])
        self.assertNotIn("role_c", offenders[0])

    def test_scenarios_disagreeing_on_the_namespace_variable_are_reported(self) -> None:
        """DERIVED -- see the real-tree assertion of the same property."""
        root = self.scratch_tree(
            {
                ("role_a", "default"): namespaced_scenario_document(
                    f"a-${{{FIXTURE_NAMESPACE_VARIABLE}:-{FIXTURE_REFUSING_DEFAULT}}}"
                ),
                ("role_b", "default"): namespaced_scenario_document(
                    f"b-${{ANOTHER_NAMESPACE:-{FIXTURE_REFUSING_DEFAULT}}}"
                ),
            }
        )
        self.assertEqual(
            {FIXTURE_NAMESPACE_VARIABLE, "ANOTHER_NAMESPACE"},
            set(scenario_namespace_variables(root)),
            "the two variables the fixture scenarios interpolate were not both read",
        )

    def test_the_checks_reach_a_scenario_at_a_role_path_they_do_not_name(self) -> None:
        """SPECIFIED -- "A scenario SHALL NOT be exempt from this by being newly
        added" and "A scenario added later SHALL be covered without an edit to
        the check". A scenario is placed at a role path appearing nowhere in
        this file and each check is asserted to reach it."""
        root = self.scratch_tree(
            {
                ("ok", "default"): namespaced_scenario_document(self.NAMESPACED),
                ("a_role_added_later", "a_scenario_added_later"): namespaced_scenario_document(
                    "a-literal-instance", hostname=None
                ),
            }
        )
        added = "ansible/roles/a_role_added_later/molecule/a_scenario_added_later/molecule.yml"
        self.assertIn(added, self.discovered(root))
        self.assertTrue(
            any(added in entry for entry in scenario_names_carrying_no_namespace(root)),
            "a scenario added later with a bare literal name was passed over",
        )
        self.assertTrue(
            any(added in entry for entry in scenarios_declaring_no_explicit_host_name(root)),
            "a scenario added later declaring no host name was passed over",
        )

    def test_installed_galaxy_content_is_not_held_to_these_obligations(self) -> None:
        """SPECIFIED -- "The obligation SHALL NOT extend to scenarios shipped by
        Galaxy content installed from `ansible/requirements.yml`", and the clause
        requiring the exclusion be derived from that manifest.

        The Galaxy scenario here carries every defect the checks look for. It is
        excluded because the fixture manifest names its directory, not because
        anything here names it -- and with the manifest emptied, the identical
        scenario IS reported, which is what shows the exclusion is derived
        rather than hardcoded.
        """
        excluded = self.scratch_tree(
            {
                ("ok", "default"): namespaced_scenario_document(self.NAMESPACED),
                ("geerlingguy.docker", "default"): namespaced_scenario_document(
                    "instance", hostname=None
                ),
            }
        )
        self.assertEqual([], scenario_names_carrying_no_namespace(excluded))
        self.assertEqual([], scenarios_declaring_no_explicit_host_name(excluded))
        self.assertEqual([], scenario_names_whose_unset_default_names_a_container(excluded))
        unbounded = self.scratch_tree(
            {
                ("ok", "default"): namespaced_scenario_document(self.NAMESPACED),
                ("geerlingguy.docker", "default"): namespaced_scenario_document(
                    "instance", hostname=None
                ),
            },
            manifest="roles: []\n",
        )
        self.assertTrue(
            scenario_names_carrying_no_namespace(unbounded),
            "with the manifest naming no installed content, the same scenario was "
            "still excluded -- so the exclusion is not derived from the manifest",
        )


# --------------------------------------------------------------------------
# iac-repo-foundations / Verification Writing to Shared State Is Namespaced per
# Working Tree -- "`AGENTS.md` SHALL carry a section binding this requirement
# to each service it governs, naming the state, the namespace, and how a
# session takes one", and its scenario "The binding is stated, not merely
# implied": "the pipeline's own configuration checks SHALL fail where that
# statement is absent".
#
# The sibling of TestTheConventionsFileStatesTheMoleculeSharedStateHazard
# above, and deliberately separate from it. That class asserts the hazard is
# DESCRIBED, so a session can recognise a collision. This one asserts the rule
# is BOUND, so the hazard is removed rather than merely recognisable. A file can
# satisfy the first and not the second -- which is exactly the state this
# repository has been in, and what this change closes.
#
# Matched on load-bearing words rather than on a heading, for the reason that
# class gives. The fragments are ones a description of the hazard alone does not
# already satisfy: `collections` and `ansible-galaxy` appear nowhere below the
# generated block before this change, so this cannot pass on the pre-change
# file.
# --------------------------------------------------------------------------

MOLECULE_BINDING_ANCHOR = "ANSIBLE_HOME"
MOLECULE_BINDING_FRAGMENTS = (
    "Molecule",
    "namespace",
    "ephemeral directory",
    "collections",
    "ansible-galaxy",
)
MOLECULE_BINDING_LOCALITY = 2500
COORDINATION_IS_THE_WHOLE_SAFEGUARD = "coordination between sessions is the whole safeguard"

BACKTICKED = re.compile(r"`([^`\n]+)`")
NOT_IN_A_PATH = set(" \t*<>~$|()[]{}")


def conventions_below_the_generated_block(text: str) -> str:
    """The project's own conventions, flattened, with the generated workflow
    block dropped. A statement inside that block is one the next regeneration
    deletes, so it does not count as stated."""
    end = text.find(MANAGED_BLOCK_END)
    if end == -1:
        raise AssertionError(
            f"AGENTS.md carries no {MANAGED_BLOCK_END!r} marker, so this check cannot "
            f"tell the generated block from the project's own conventions"
        )
    return flattened(text[end + len(MANAGED_BLOCK_END) :])


def binding_spans(text: str) -> list[str]:
    """Every neighbourhood of the conventions in which the binding could be
    stated: a window either side of each mention of the lever it turns on."""
    below = conventions_below_the_generated_block(text)
    spans = []
    start = below.find(MOLECULE_BINDING_ANCHOR)
    while start != -1:
        spans.append(
            below[max(0, start - MOLECULE_BINDING_LOCALITY) : start + MOLECULE_BINDING_LOCALITY]
        )
        start = below.find(MOLECULE_BINDING_ANCHOR, start + 1)
    return spans


def binding_fragments_missing(text: str) -> list[str]:
    """What the closest thing to a binding section still lacks, or [] where some
    one neighbourhood carries every fragment.

    Order is not asserted: the requirement obliges the section to NAME three
    things, not to name them in a sequence, and a check pinning one would fail a
    correct file.
    """
    spans = binding_spans(text)
    if not spans:
        return [MOLECULE_BINDING_ANCHOR, *MOLECULE_BINDING_FRAGMENTS]
    closest = None
    for span in spans:
        folded = span.casefold()
        missing = [
            fragment
            for fragment in MOLECULE_BINDING_FRAGMENTS
            if fragment.casefold() not in folded
        ]
        if not missing:
            return []
        if closest is None or len(missing) < len(closest):
            closest = missing
    return closest or []


def entry_points_named_by_the_binding(text: str, root: Path | None = None) -> list[str]:
    """Repository paths the binding names that resolve to a runnable file.

    "How a session takes one" is not satisfied by prose alone: a session needs
    something to run. A backticked token is read as an entry point where it
    resolves to a committed file that is executable or opens with a shebang --
    which no file this repository commits did before this change.
    """
    base = ROOT if root is None else root
    found = set()
    for span in binding_spans(text):
        for token in BACKTICKED.findall(span):
            candidate = token.strip()
            if candidate.startswith("./"):
                candidate = candidate[2:]
            if not candidate or candidate.startswith("/"):
                continue
            if set(candidate) & NOT_IN_A_PATH:
                continue
            path = base / candidate
            if not path.is_file():
                continue
            with path.open("rb") as handle:
                shebang = handle.read(2) == b"#!"
            if shebang or os.access(path, os.X_OK):
                found.add(candidate)
    return sorted(found)


class TestTheConventionsFileBindsTheSharedStateRuleToMolecule(unittest.TestCase):
    """ADDED requirement: Verification Writing to Shared State Is Namespaced per
    Working Tree.

    Read against the real file. Every assertion reads the conventions BELOW the
    generated workflow block, so a binding stated inside that block -- which the
    next regeneration replaces -- satisfies none of them.
    """

    def setUp(self) -> None:
        self.text = read_text(AGENTS_FILE)

    def test_the_conventions_file_carries_the_binding_section(self) -> None:
        """SPECIFIED -- "`AGENTS.md` SHALL carry a section binding this
        requirement to each service it governs, naming the state, the namespace,
        and how a session takes one", and scenario "The binding is stated, not
        merely implied".

        DERIVED in its fragments: `collections` and `ansible-galaxy` trace to
        design.md Decision 2, which records that a fresh namespace fails at
        `create` until the shared collections path is supplied and that the
        binding section names that one-time install. They are the fragments a
        statement of the hazard alone does not already carry.
        """
        missing = binding_fragments_missing(self.text)
        self.assertEqual(
            [],
            missing,
            f"AGENTS.md states the Molecule shared-state hazard but binds no mechanism "
            f"to it: {missing} not found near {MOLECULE_BINDING_ANCHOR!r} below the "
            f"generated block. A stated rule with nothing bound to it is not "
            f"enforceable by a reviewer, which is the state this repository ran in "
            f"for months",
        )

    def test_the_binding_names_an_entry_point_committed_to_this_repository(self) -> None:
        """SPECIFIED -- "how a session takes one". A session takes a namespace by
        running something; naming no runnable thing leaves the mechanism a ritual
        each session reconstructs, which design.md Decision 6 is written against.

        DERIVED in what counts as runnable: a committed file that is executable
        or opens with a shebang. No file this repository commits satisfied that
        before this change, so this cannot pass vacuously.
        """
        found = entry_points_named_by_the_binding(self.text)
        self.assertTrue(
            found,
            "the binding names no committed, runnable entry point, so a session is "
            "left to reconstruct the invocation -- and a reconstruction that omits "
            "the ephemeral directory looks identical to one that does not",
        )

    def test_the_conventions_file_no_longer_says_coordination_is_the_whole_safeguard(
        self,
    ) -> None:
        """DERIVED -- tasks.md 5.4; no scenario states it. AGENTS.md currently
        tells a session that "coordination between sessions is the whole
        safeguard". Once the binding exists that is false, and a session
        believing it would coordinate by hand instead of using the mechanism --
        leaving the change's whole benefit unclaimed while the file says the old
        thing.
        """
        below = conventions_below_the_generated_block(self.text)
        self.assertNotIn(
            COORDINATION_IS_THE_WHOLE_SAFEGUARD,
            below,
            "AGENTS.md still tells a session that coordination between sessions is "
            "the whole safeguard, which the binding this change adds makes untrue",
        )


class TestTheBindingCheckIsARealReadOfTheFile(unittest.TestCase):
    """ADDED requirement: Verification Writing to Shared State Is Namespaced per
    Working Tree -- the discriminating half of scenario "The binding is stated,
    not merely implied": the checks "SHALL fail where that statement is absent".

    The class above would pass identically against a check that read nothing.
    These run it over synthetic conventions files, which is what establishes it
    fails on a tree with the section removed rather than only passing on one
    with it present.
    """

    BOUND = (
        "## Testing\n\n"
        "Molecule is the one shared service this repository's verification writes "
        "to. Each working tree takes its own namespace, computed deterministically "
        "from the tree, and both live handles carry it: the instance name in each "
        "platform's name field, and the ephemeral directory under a relocated "
        "`ANSIBLE_HOME`. Run the suite through `scripts/molecule-run`, which "
        "computes both and execs Molecule. Collections stay shared and are "
        "installed once per machine with `ansible-galaxy`.\n"
    )

    def conventions(self, body: str, above: str = "") -> str:
        return (
            "<!-- ai-toolkit:development-workflow v3 -->\n"
            f"{above}\n"
            f"{MANAGED_BLOCK_END}\n\n"
            "## Project conventions\n\n"
            f"{body}"
        )

    def tree_carrying(self, files: dict, executable: tuple = ()) -> Path:
        root = Path(tempfile.mkdtemp(prefix="molecule-binding-fixture-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            if name in executable:
                path.chmod(0o755)
        return root

    def test_a_bound_conventions_file_raises_no_offence(self) -> None:
        self.assertEqual([], binding_fragments_missing(self.conventions(self.BOUND)))

    def test_a_conventions_file_that_only_describes_the_hazard_is_reported(self) -> None:
        """The pre-change state, in miniature: the hazard is stated, the lever is
        named, and nothing is bound to it."""
        described = (
            "## Testing\n\nMolecule's state is shared across working trees. The "
            "ephemeral directory is `$ANSIBLE_HOME/tmp/molecule.<id>.<scenario>` and "
            "Molecule does not remove it. Until these handles are namespaced per "
            "working tree, coordination between sessions is the whole safeguard.\n"
        )
        missing = binding_fragments_missing(self.conventions(described))
        self.assertEqual(
            ["collections", "ansible-galaxy"],
            missing,
            f"a file that only describes the hazard was not reported as unbound: "
            f"{missing}",
        )

    def test_a_binding_stated_inside_the_generated_block_does_not_count(self) -> None:
        """The generated workflow block is replaced on update, so a statement
        inside it is one the next regeneration deletes -- the disappearance this
        assertion exists to prevent, reached by another route."""
        missing = binding_fragments_missing(
            self.conventions("## Testing\n\nNothing.\n", above=self.BOUND)
        )
        self.assertEqual(
            [MOLECULE_BINDING_ANCHOR, *MOLECULE_BINDING_FRAGMENTS],
            missing,
            f"a binding stated inside the generated block was accepted: {missing}",
        )

    def test_a_conventions_file_with_no_marker_fails_rather_than_reading_nothing(
        self,
    ) -> None:
        """An absent marker means the check cannot tell the generated block from
        the project's own conventions. It refuses rather than reading the whole
        file, which would accept a binding stated inside the block."""
        with self.assertRaises(AssertionError):
            binding_fragments_missing("## Testing\n\n" + self.BOUND)

    def test_the_statement_this_change_retires_is_detected(self) -> None:
        """The negative assertion's own discrimination: it has to see the
        sentence where it is present, or its silence establishes nothing."""
        described = self.conventions(
            "## Testing\n\nUntil these handles are namespaced per working tree, "
            "coordination between sessions is the whole safeguard.\n"
        )
        self.assertIn(
            COORDINATION_IS_THE_WHOLE_SAFEGUARD,
            conventions_below_the_generated_block(described),
        )
        self.assertNotIn(
            COORDINATION_IS_THE_WHOLE_SAFEGUARD,
            conventions_below_the_generated_block(self.conventions(self.BOUND)),
        )

    def test_a_named_entry_point_that_is_committed_and_runnable_is_found(self) -> None:
        root = self.tree_carrying(
            {"scripts/molecule-run": '#!/usr/bin/env bash\nexec molecule "$@"\n'}
        )
        self.assertEqual(
            ["scripts/molecule-run"],
            entry_points_named_by_the_binding(self.conventions(self.BOUND), root),
        )

    def test_an_entry_point_named_but_not_committed_is_not_found(self) -> None:
        """A binding may name a script the change forgot to add. Prose alone is
        not a mechanism, so the check reads the tree rather than the sentence."""
        self.assertEqual(
            [],
            entry_points_named_by_the_binding(
                self.conventions(self.BOUND),
                self.tree_carrying({"README.md": "nothing here\n"}),
            ),
        )

    def test_a_configuration_file_the_binding_mentions_is_not_read_as_an_entry_point(
        self,
    ) -> None:
        """The binding will name files that are not entry points -- a manifest, a
        workflow. Neither is runnable, and reading one as the mechanism would let
        this pass with no entry point at all."""
        body = self.BOUND.replace("`scripts/molecule-run`", "`ansible/requirements.yml`")
        root = self.tree_carrying({"ansible/requirements.yml": "roles: []\n"})
        self.assertEqual([], entry_points_named_by_the_binding(self.conventions(body), root))

    def test_an_entry_point_carrying_the_executable_bit_and_no_shebang_is_found(self) -> None:
        """DERIVED -- either signal is accepted. Requiring both would fail a
        correct entry point for a reason no artifact of this change states."""
        root = self.tree_carrying(
            {"scripts/molecule-run": 'exec molecule "$@"\n'},
            executable=("scripts/molecule-run",),
        )
        self.assertEqual(
            ["scripts/molecule-run"],
            entry_points_named_by_the_binding(self.conventions(self.BOUND), root),
        )

# iac-cicd-pipeline / Scheduled Workflows Report Their Own Liveness
# iac-host-configuration / Scheduled Host Units Report Their Own Liveness
#
# Derived from the delta specs of the OpenSpec change
# `notice-when-a-periodic-job-stops-reporting`, before any implementation of
# that change existed and without reading any implementation of it -- none
# exists. See that change's test-plan.md for the scenario-to-test mapping, the
# recorded baseline, every assertion's SPECIFIED/DERIVED classification, and
# the delta scenarios deliberately left uncovered.
#
# WHY THESE PROPERTIES ARE HERE AND NOT IN MOLECULE. Every one below is a
# static read of a committed file: a workflow's `on:` block and its jobs, a
# role's inline unit and reporting script, a Molecule scenario's own
# variables. None needs a network call, a credential, a container runtime or a
# Terraform binary, and none adds an import. THE REPORTERS' URLS ARE ASSERTED
# AS TEXT AND ARE NEVER REQUESTED -- that change's tasks.md 4.11 requires
# exactly that, and `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource`
# at the end of this section holds it for `.github/tests/` as a whole rather
# than for this one module, which is all the pre-existing audit above covers.
#
# WHAT NONE OF IT ESTABLISHES, stated because a static read of a reporter is
# easy to mistake for evidence that reporting works: that the ping key exists,
# that the check exists at the observer, that its period and grace are right,
# or that any alert reaches anybody. Both deltas put the alarm in the
# observer's SILENCE, and no assertion in this repository can observe a third
# party's timeout. That is the change's own confirm gate's business, and its
# test-plan.md records the scenarios resting on it as uncovered rather than
# approximating them here.
# --------------------------------------------------------------------------


# This repository's own name, per design Decision 4's derivation table. A slug
# is a pure function of the reporter's own filename, so the test below derives
# what it expects rather than consulting a second list that can drift from the
# first: DISTINCTNESS ALONE WOULD PASS `drift.yml` CARRYING THE AUTOUPDATE
# SLUG, leaving two checks silently swapped and both green.
LIVENESS_SLUG_PREFIX = "infrastructure-"

# The observer's production base URL (design Decision 12). Named here so a
# Molecule scenario left pointing at it can be identified; nothing in this
# suite requests it.
PRODUCTION_HEARTBEAT_BASE_URL = "https://hc-ping.com"

# What makes a job a liveness reporter, read from what the job says it is.
# Matched against the job's CODE with whole-line shell comments dropped, so
# the comment tasks.md 2.3 requires beside each reporting step cannot by
# itself make a job look like a reporter.
LIVENESS_HINT = re.compile(r"hc-ping|healthcheck|heartbeat|liveness|ping[_-]?key", re.I)

# Secrets on the `production` Environment carry this prefix in this
# repository (`PLATFORM_SLACK_WEBHOOK_URL`, `PLATFORM_DEADMANSWITCH_URL`). A
# job reading one must declare that Environment, and such a job waits on
# required-reviewer approval -- design Decision 6: an alarm that waits for a
# human to approve its own delivery is not an alarm.
ENVIRONMENT_SECRET_PREFIX = "PLATFORM_"

# `${{ ... }}` carries spaces, which would truncate a URL token at the first
# one. Collapsed to a space-free placeholder before any URL is read, so that
# `.../${{ secrets.HEARTBEAT_PING_KEY }}/slug?create=1` reads as one URL.
GITHUB_EXPRESSION = re.compile(r"\$\{\{[^}]*\}\}")

URL_TOKEN = re.compile(r"https?://[^\s\"'`\\<>]+")

# A quoted or bare argument, quotes kept, so that `"$BASE/$KEY"` stays one
# token and is read as carrying an expansion.
SHELL_ARGUMENT = re.compile(r"""'[^']*'|"[^"]*"|\S+""")

CURL_INVOCATION = re.compile(r"(?<![\w.-])curl\b")
CURL_COMMAND = re.compile(r"curl\b")

# An endpoint a shell script builds: rooted at a literal scheme or at a
# variable holding the base, and carrying at least one path segment.
SHELL_ENDPOINT = re.compile(
    r"""(?:https?://|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?)[^\s"'`;|)]*"""
)

# Variable names that carry a check's address or its credential.
HEARTBEAT_VARIABLE = re.compile(r"PING|KEY|SLUG|HEARTBEAT|CHECK|HC_", re.I)

# Endpoints the observer defines beyond the plain success ping. Stripped when
# reading a slug out of a URL, so `/<slug>/fail` and `/<slug>` are read as
# addressing the same check.
PING_SUFFIXES = ("fail", "start", "log")

COPY_ACTIONS = ("ansible.builtin.copy", "copy", "ansible.builtin.template", "template")

ROLES_DIR = ROOT / "ansible" / "roles"


def without_shell_comments(text: str) -> str:
    """Drop whole-line shell comments, so a comment naming a URL is not read
    as the script requesting one. Mirrors `uncommented()` for YAML; an inline
    trailing comment is deliberately left in place, because splitting on `#`
    would cut a URL fragment and a quoted string."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def with_expressions_collapsed(text: str) -> str:
    return GITHUB_EXPRESSION.sub("$EXPR", text)


def step_code(step: dict) -> str:
    """Everything a step contributes EXCEPT its shell comments."""
    parts = [str(step.get(key, "")) for key in ("name", "uses", "id", "if")]
    for block in ("with", "env"):
        value = step.get(block)
        if value:
            parts.append(yaml.safe_dump(value, default_flow_style=False))
    parts.append(without_shell_comments(str(step.get("run", ""))))
    return "\n".join(parts)


def job_code(job: dict) -> str:
    parts = [str(job.get(key, "")) for key in ("name", "if", "environment")]
    if job.get("env"):
        parts.append(yaml.safe_dump(job["env"], default_flow_style=False))
    parts.extend(step_code(step) for step in (job.get("steps") or []))
    return "\n".join(parts)


def scheduled_workflows() -> list:
    """Every committed workflow whose triggers include `schedule`.

    The set is DISCOVERED, never enumerated: the requirement is over "every
    workflow in this repository triggered by `schedule:`", and a workflow
    added later has to be covered without a test edit.
    """
    found = []
    for path in workflow_files():
        workflow = load_yaml(path)
        if isinstance(workflow, dict) and "schedule" in triggers(workflow):
            found.append((path, workflow))
    return found


def expected_workflow_slug(path: Path) -> str:
    return LIVENESS_SLUG_PREFIX + path.stem


def liveness_reporting_jobs(workflow: dict) -> list:
    return [
        (key, job)
        for key, job in jobs(workflow).items()
        if LIVENESS_HINT.search(job_code(job))
    ]


def ping_urls(text: str) -> list:
    """Every URL a reporter's code carries, other than GitHub's own."""
    found = []
    for token in URL_TOKEN.findall(with_expressions_collapsed(text)):
        token = token.rstrip("\\\"'`,;)")
        if "github.com" in token:
            continue
        found.append(token)
    return found


def endpoint_slug(url: str):
    """The check identifier a ping URL addresses, or None if it addresses no
    path at all. `/fail`, `/start` and `/log` are the observer's endpoints on
    a check rather than identifiers of their own."""
    path = url.split("?", 1)[0].split("#", 1)[0]
    segments = [segment for segment in path.split("/")[3:] if segment]
    while segments and segments[-1] in PING_SUFFIXES:
        segments.pop()
    return segments[-1] if segments else None


def role_task_list(role: str) -> list:
    path = ROLES_DIR / role / "tasks" / "main.yml"
    if not path.is_file():
        return []
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, list) else []


def inline_files_installed_by(role: str) -> dict:
    """Every file a role writes with an inline body, keyed by destination.

    THIS REPOSITORY WRITES ITS UNITS AND SCRIPTS INLINE IN `tasks/main.yml`
    via `copy:`/`content:`, not under `templates/` -- design.md's Risks
    section names that as the shakier half of this change's coverage and says
    the read will need revisiting if a role ever templates its units instead.
    Recorded here, in the discovery itself, so the next reader meets the
    assumption where it is made rather than in a test that mysteriously finds
    nothing. `template:` is included among the actions read so that an inline
    `content:` under it is not dropped; what WOULD be dropped is a unit moved
    into a separate file under `templates/`, which is why every assertion
    quantified over this discovery is guarded by a test that fails when the
    discovery finds nothing.
    """
    installed = {}
    for task in role_task_list(role):
        if not isinstance(task, dict):
            continue
        for action in COPY_ACTIONS:
            spec = task.get(action)
            if not isinstance(spec, dict):
                continue
            if spec.get("dest") is None or spec.get("content") is None:
                continue
            installed[str(spec["dest"])] = {
                "content": str(spec["content"]),
                "mode": str(spec.get("mode", "")),
                "owner": str(spec.get("owner", "")),
                "task": str(task.get("name", "")),
                "role": role,
            }
    return installed


def role_texts(role: str) -> dict:
    """Every committed text a role carries that could hold a script: the
    inline bodies above, plus anything under `files/` and `templates/`."""
    texts = {
        dest: spec["content"] for dest, spec in inline_files_installed_by(role).items()
    }
    for sub in ("files", "templates"):
        directory = ROLES_DIR / role / sub
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                texts[str(path.relative_to(ROOT))] = path.read_text(
                    encoding="utf-8", errors="replace"
                )
    return texts


def timer_installing_roles() -> dict:
    """Role -> its `.timer` units. The scope of the host delta is units THIS
    REPOSITORY DEFINES, not every timer on the host: a package this repository
    installs may ship timers of its own -- unattended security updates do --
    and those are the packager's to define, report and bound."""
    found = {}
    for role in sorted(role_names()):
        units = {
            dest: spec
            for dest, spec in inline_files_installed_by(role).items()
            if dest.endswith(".timer")
        }
        if units:
            found[role] = units
    return found


def unit_stem(dest: str) -> str:
    return Path(dest).stem


def reporting_scripts(role: str) -> dict:
    """Every committed text in a role that invokes `curl` -- the reporting
    script, and nothing else this repository's roles carry."""
    return {
        label: text
        for label, text in role_texts(role).items()
        if CURL_INVOCATION.search(without_shell_comments(text))
    }


def curl_invocations(text: str) -> list:
    """Each `curl` command line in a script, continuations joined and comment
    lines dropped.

    Each line is split at its command separators and a segment is read as an
    invocation only where `curl` stands in COMMAND POSITION -- after the
    leading `then`/`else`/`do`, a `!`, or an environment assignment. Matching
    the word anywhere on the line instead reads
    `printf "reported %s (curl status %s)" ...` as a second invocation with
    the message as its arguments, and the reporting script tasks.md 3.3
    prescribes writes exactly that line to stderr.
    """
    joined = re.sub(r"\\\n\s*", " ", without_shell_comments(text))
    found = []
    for line in joined.splitlines():
        for segment in re.split(r"\|\||\||&&|;", line):
            stripped = re.sub(
                r"^(?:!\s*|then\s+|else\s+|do\s+|[A-Za-z_][A-Za-z0-9_]*=\S*\s+)+",
                "",
                segment.strip(),
            )
            if CURL_COMMAND.match(stripped):
                found.append(stripped)
    return found


def curl_arguments(invocation: str) -> list:
    return SHELL_ARGUMENT.findall(invocation)[1:]


# Curl options that consume the token after them. A value-taking option
# MISSING from this set turns its value into a spurious operand and fails a
# conforming script; a boolean wrongly IN it lets an operand after that
# boolean escape. The set is therefore generous, and the name and literal
# tests below are what carry the detection -- this positional rule is the
# belt, not the braces.
CURL_VALUE_OPTIONS = frozenset(
    {
        "--config", "-K",
        "--max-time", "-m",
        "--connect-timeout",
        "--retry", "--retry-delay", "--retry-max-time",
        "--data", "-d", "--data-raw", "--data-binary", "--data-urlencode",
        "--header", "-H",
        "--user-agent", "-A",
        "--output", "-o",
        "--write-out", "-w",
        "--request", "-X",
        "--url",
        "--proto", "--interface",
    }
)

# Options whose value IS an address: naming one puts the address on the
# command line however the value is spelled.
CURL_ADDRESS_OPTIONS = frozenset({"--url"})

NAMED_EXPANSION = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)")
COMMAND_SUBSTITUTION = re.compile(r"\$\(|`")

# Variable names that may hold a check's address or its credential. Matched
# against the NAME, because a variable's value is not readable from here.
ADDRESS_OR_CREDENTIAL = re.compile(
    r"PING|KEY|SLUG|HEARTBEAT|CHECK|HC_|URL|ENDPOINT|TOKEN|SECRET", re.I
)


def curl_arguments_carrying_an_address(invocation: str) -> list:
    """Arguments on a `curl` command line that carry, or may expand to, the
    ping URL or the ping key.

    Three rules, because forbidding a literal alone is not enough --
    `curl "$PING_URL"` contains no literal and puts the key in
    `/proc/<pid>/cmdline` exactly as design Decision 9 forbids:

      1. any argument containing `://`, or a command substitution;
      2. any argument expanding a variable whose NAME could hold the address
         or the credential (a variable's value is not readable from here, so
         the name is what there is to read);
      3. any OPERAND -- an argument in neither flag nor flag-value position --
         because curl's operands are URLs, and so is the value of `--url`.

    What this deliberately does NOT forbid: an expansion whose name is
    unrelated to the address, in the value of a flag. Decision 9 carries
    `$EXIT_STATUS` through as diagnostic text in the ping body, and a rule
    refusing every expansion would fail the very script tasks.md 3.3
    prescribes.

    The residual hole, stated rather than papered over: `curl --silent "$X"`,
    where `X` was assigned the URL earlier under a name matching nothing in
    rule 2, is read as `--silent`'s value and passes. Closing it needs the
    script's dataflow rather than its text.
    """
    arguments = curl_arguments(invocation)
    offending = []
    awaiting_value_for = None
    for argument in arguments:
        if awaiting_value_for is not None:
            role, flag = "value", awaiting_value_for
            awaiting_value_for = None
        elif argument.startswith("-") and argument != "-":
            role, flag = "flag", None
            if argument in CURL_VALUE_OPTIONS:
                awaiting_value_for = argument
        else:
            role, flag = "operand", None

        if "://" in argument or COMMAND_SUBSTITUTION.search(argument):
            offending.append(argument)
            continue
        names = NAMED_EXPANSION.findall(argument)
        if any(ADDRESS_OR_CREDENTIAL.search(name) for name in names):
            offending.append(argument)
            continue
        if role == "operand":
            offending.append(argument)
            continue
        if role == "value" and flag in CURL_ADDRESS_OPTIONS:
            offending.append(argument)
    return offending


def shell_endpoints(text: str) -> list:
    """Ping endpoints a shell script builds, literal or variable-rooted."""
    found = []
    for candidate in SHELL_ENDPOINT.findall(without_shell_comments(text)):
        candidate = candidate.rstrip("\\\"'`,;)")
        if candidate.count("/") < 2:
            continue
        if (
            "create=" in candidate
            or "/fail" in candidate
            or "hc-ping" in candidate
            or HEARTBEAT_VARIABLE.search(candidate)
        ):
            found.append(candidate)
    return found


def scenario_directories(role: str) -> list:
    molecule = ROLES_DIR / role / "molecule"
    if not molecule.is_dir():
        return []
    return sorted(
        path
        for path in molecule.iterdir()
        if path.is_dir() and (path / "converge.yml").is_file()
    )


def _flatten_task(task):
    """A task, and every task nested inside its block/rescue/always."""
    if not isinstance(task, dict):
        return
    yield task
    for key in ("block", "rescue", "always"):
        for inner in task.get(key) or []:
            yield from _flatten_task(inner)


def _tasks_in(play: dict):
    for key in ("pre_tasks", "tasks", "post_tasks", "handlers"):
        for task in play.get(key) or []:
            yield from _flatten_task(task)


def scenario_role_invocations(scenario: Path, role: str) -> list:
    """(playbook, variables in force) at every point a scenario converges the
    role -- in ANY of its playbooks, not only `converge.yml`.

    `notice-when-a-periodic-job-stops-reporting`'s tasks.md 4.8b named
    `converge.yml`, and reading only that file was not enough: this role's
    `default` and `abandon-paths` scenarios ALSO converge it from their
    `verify.yml`, through `include_role` with task-level `vars:`, to arrange
    a retired application and a never-deployed one. Those re-converges are
    converges -- they need the role's required inputs, and left on the
    production base URL they would ping the external observer from a hosted
    runner exactly as a converge would. The narrower read was widened here
    after both scenarios failed on it; the finding is recorded in that
    change's test-plan.md.
    """
    found = []
    for path in sorted(scenario.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for play in document if isinstance(document, list) else []:
            if not isinstance(play, dict):
                continue
            play_vars = play.get("vars") if isinstance(play.get("vars"), dict) else {}
            for entry in play.get("roles") or []:
                named = entry if isinstance(entry, str) else None
                if isinstance(entry, dict):
                    named = entry.get("role") or entry.get("name")
                if named != role:
                    continue
                supplied = dict(play_vars)
                if isinstance(entry, dict) and isinstance(entry.get("vars"), dict):
                    supplied.update(entry["vars"])
                found.append((path.name, supplied))
            for task in _tasks_in(play):
                spec = task.get("ansible.builtin.include_role") or task.get(
                    "include_role"
                )
                if not isinstance(spec, dict) or spec.get("name") != role:
                    continue
                supplied = dict(play_vars)
                if isinstance(task.get("vars"), dict):
                    supplied.update(task["vars"])
                found.append((path.name, supplied))
    return found


def scenario_expects_a_refusal(scenario: Path) -> bool:
    """Whether a scenario converges the role EXPECTING it to fail.

    Read from the structure `hardening/molecule/absent-ssh-cidrs` established
    -- a `rescue:` recording the failure the unsupplied input produced -- and
    not from the scenario's name. Such a scenario is the host delta's "An
    absent report address is reported by name", and obliging it to supply the
    address would delete the scenario it exists to be. Its base-URL obligation
    is NOT waived: see `TestNoTimerRoleScenarioReachesTheExternalObserver`.
    """
    return "rescue:" in (scenario / "converge.yml").read_text(encoding="utf-8")


class TestEveryScheduledWorkflowReportsItsOwnLiveness(unittest.TestCase):
    """ADDED requirement: Scheduled Workflows Report Their Own Liveness."""

    def setUp(self) -> None:
        self.scheduled = scheduled_workflows()

    def _reporters(self) -> list:
        """(path, workflow, job key, job) for each scheduled workflow's
        reporting job, failing rather than returning nothing."""
        self.test_the_repository_carries_at_least_one_scheduled_workflow()
        found = []
        for path, workflow in self.scheduled:
            reporters = liveness_reporting_jobs(workflow)
            self.assertTrue(
                reporters,
                f"{path.name} is schedule-triggered and carries no liveness report; "
                "see the test that states this obligation on its own",
            )
            for key, job in reporters:
                found.append((path, workflow, key, job))
        return found

    def test_the_repository_carries_at_least_one_scheduled_workflow(self) -> None:
        """DERIVED (tasks.md 4.2, 4.7) -- every assertion in this class is
        universally quantified over what discovery finds, and a discovery that
        finds nothing would leave each of them quantified over an empty set
        and green. *Ansible Configuration Is Verified in Continuous
        Integration and Gates the Merge*
        (openspec/specs/iac-cicd-pipeline/spec.md) already requires exactly
        this of Molecule role discovery and is the precedent.
        """
        self.assertTrue(
            self.scheduled,
            "no workflow under .github/workflows/ declares a `schedule:` trigger, so "
            "every assertion about scheduled workflows below would pass having read "
            "nothing -- this repository has two, so a discovery finding none is a "
            "defect in the discovery, not a change in the repository",
        )

    def test_every_scheduled_workflow_carries_a_liveness_report(self) -> None:
        """SPECIFIED -- "Every workflow in this repository triggered by
        `schedule:` SHALL report the outcome of each scheduled run to an
        external observer", and scenario "A scheduled workflow added without a
        report fails the pull request": the required status check SHALL fail.
        This assertion IS that check; that it gates the pull request is held by
        `TestTheSuiteIsWiredIntoTheRequiredCheck` above.
        """
        self.test_the_repository_carries_at_least_one_scheduled_workflow()
        without = [
            path.name
            for path, workflow in self.scheduled
            if not liveness_reporting_jobs(workflow)
        ]
        self.assertEqual(
            [],
            without,
            f"these schedule-triggered workflows carry no liveness report: {without}. "
            "A run of one that fails, is killed, or never happens at all is visible "
            "to nothing -- and GitHub disables a scheduled workflow after 60 days of "
            "repository inactivity, which emits no failure and no run",
        )

    def test_every_reporter_addresses_the_slug_derived_from_its_own_filename(self) -> None:
        """SPECIFIED -- "SHALL address its own report by an identifier that is
        a literal in the workflow file, distinct per workflow". The particular
        derivation (`infrastructure-` + the file's stem) is DERIVED, from
        design Decision 4 and tasks.md 4.2, and is what catches the failure
        distinctness alone does not: `drift.yml` carrying the autoupdate slug,
        so that two checks silently swap meaning while both stay green.
        """
        for path, _, key, job in self._reporters():
            with self.subTest(workflow=path.name, job=key):
                expected = expected_workflow_slug(path)
                urls = ping_urls(job_code(job))
                self.assertTrue(
                    urls,
                    f"{path.name}'s reporting job {key!r} carries no ping URL at all, "
                    "so nothing in the committed file says which check it addresses",
                )
                addressed = sorted(
                    {slug for slug in (endpoint_slug(url) for url in urls) if slug}
                )
                self.assertEqual(
                    [expected],
                    addressed,
                    f"{path.name}'s reporting job {key!r} addresses {addressed} rather "
                    f"than exactly {[expected]}. The slug is a pure function of the "
                    "workflow's own filename, so that no second list can drift from "
                    "the first",
                )

    def test_the_reporting_job_depends_on_every_other_job_in_its_workflow(self) -> None:
        """SPECIFIED -- "The report SHALL be emitted from a job that runs
        whatever the outcome of the rest of the workflow, and that depends on
        every other job in it", and scenario "A failure in an early job is
        still reported"."""
        for path, workflow, key, job in self._reporters():
            with self.subTest(workflow=path.name, job=key):
                declared = job.get("needs") or []
                if isinstance(declared, str):
                    declared = [declared]
                missing = sorted(set(jobs(workflow)) - {key} - set(declared))
                self.assertEqual(
                    [],
                    missing,
                    f"{path.name}'s reporting job {key!r} does not depend on {missing}. "
                    "A job it does not need can fail without the report saying so, and "
                    "the failure would then be caught only by the observer's silence "
                    "timeout -- slower than the signal that was available at the time",
                )

    def test_the_reporting_job_runs_whatever_the_outcome(self) -> None:
        """SPECIFIED -- scenario "A scheduled run that fails is reported as a
        failure": it SHALL report that failure "without waiting for the
        observer's silence timeout to expire", which requires the job to run
        at all after a failed one."""
        for path, _, key, job in self._reporters():
            with self.subTest(workflow=path.name, job=key):
                condition = str(job.get("if", ""))
                self.assertIn(
                    "always()",
                    condition,
                    f"{path.name}'s reporting job {key!r} is conditioned on "
                    f"{condition!r}. Without `always()` a needed job's failure skips "
                    "the reporter, and a failed run reports nothing at all",
                )

    def test_the_failure_branch_keys_on_a_needed_job_having_failed(self) -> None:
        """SPECIFIED -- scenario "A run in which a conditional job is skipped
        reports success": a skipped job is an ordinary outcome of a healthy
        run, and "an alarm that fires when nothing is wrong is an alarm that
        stops being read". Under `if: always()`, `success()` is FALSE whenever
        a needed job was merely skipped, so a reporter keyed on it pings
        `/fail` on a healthy nightly (design Decision 7). The discriminator
        has to read a needed job's own result.
        """
        for path, _, key, job in self._reporters():
            with self.subTest(workflow=path.name, job=key):
                code = job_code(job)
                self.assertTrue(
                    re.search(r"needs\.(?:\*|[A-Za-z0-9_-]+)\.result", code)
                    and "failure" in code,
                    f"{path.name}'s reporting job {key!r} does not discriminate on a "
                    "needed job's `result` being 'failure'. Nothing else available "
                    "under `if: always()` tells a failed run from one carrying a "
                    "skipped conditional job",
                )
                self.assertNotIn(
                    "success()",
                    code,
                    f"{path.name}'s reporting job {key!r} uses `success()`. Under "
                    "`if: always()` that is false for a merely SKIPPED needed job, so "
                    "the reporter would ping /fail on a healthy run -- the one outcome "
                    "that destroys this mechanism's credibility fastest",
                )

    def test_a_cancelled_run_reports_neither_success_nor_failure(self) -> None:
        """SPECIFIED -- scenario "A cancelled run raises no alarm of its own":
        "no failure SHALL be reported for that run". A cancellation is an
        operator's act rather than a defect; the observer's silence timeout
        remains the backstop if cancellations continue.
        """
        for path, _, key, job in self._reporters():
            with self.subTest(workflow=path.name, job=key):
                self.assertIn(
                    "cancelled(",
                    job_code(job),
                    f"{path.name}'s reporting job {key!r} never mentions `cancelled()`, "
                    "so a cancelled run takes the same branch as a failed one and "
                    "reports a failure the operator caused deliberately",
                )

    def test_no_reporting_job_declares_a_deployment_environment(self) -> None:
        """SPECIFIED -- scenario "The report needs no human approval": the
        reporting job "SHALL declare no deployment `environment:`, so that it
        is never queued behind a required-reviewer approval"."""
        for path, _, key, job in self._reporters():
            with self.subTest(workflow=path.name, job=key):
                self.assertIsNone(
                    job.get("environment"),
                    f"{path.name}'s reporting job {key!r} declares "
                    f"environment {job.get('environment')!r}. The `production` "
                    "Environment is gated on required-reviewer approval, and an alarm "
                    "that waits for a human to approve its own delivery is not an alarm",
                )

    def test_the_reporting_job_reads_a_repository_scoped_secret(self) -> None:
        """SPECIFIED -- "The credential that report is sent under SHALL be
        repository-scoped and SHALL NOT be an Environment secret", and
        scenario "The routine alarm does not consume the last-resort one":
        the destination SHALL NOT be the one the platform stack's
        dead-man's-switch alerts to. `PLATFORM_DEADMANSWITCH_URL` is that
        destination and is itself an Environment secret, so both clauses meet
        in this one read. The `PLATFORM_` prefix as the marker of an
        Environment secret is DERIVED, from design Decision 6.
        """
        for path, _, key, job in self._reporters():
            with self.subTest(workflow=path.name, job=key):
                named = secrets_referenced_by(job)
                self.assertTrue(
                    named,
                    f"{path.name}'s reporting job {key!r} reads no secret at all, so "
                    "either it addresses no check or its credential is committed",
                )
                environment_scoped = sorted(
                    name
                    for name in named
                    if name.upper().startswith(ENVIRONMENT_SECRET_PREFIX)
                )
                self.assertEqual(
                    [],
                    environment_scoped,
                    f"{path.name}'s reporting job {key!r} reads {environment_scoped}. "
                    "Those are secrets on the `production` Environment: reading one "
                    "means declaring that Environment and waiting on required-reviewer "
                    "approval, and PLATFORM_DEADMANSWITCH_URL is additionally the "
                    "out-of-band destination this change must not erode",
                )

    def test_every_ping_url_requests_the_check_be_created(self) -> None:
        """DERIVED (design Decision 5, tasks.md 4.5) -- no scenario states
        `?create=1`; the requirement it serves is the observer alarming on
        silence at all. A slug-addressed ping to a check that does not exist
        returns 404 and does nothing: the reporter believes it is reporting,
        the observer has nothing to go quiet, and the whole mechanism is
        decorative. It has to be on BOTH URLs -- a job that fails from its
        first run never takes the success path, so a success-only `create=1`
        leaves the chronically failing case reported by nothing at all.

        THE SHAPE THIS READS IS AN ASSUMPTION: two whole URLs, each carrying
        its own query string. An implementation that builds one URL and
        appends `/fail` and `?create=1` separately satisfies the requirement
        and fails this test. That is a DERIVED assertion to be RECONSIDERED
        against the implementation, deliberately and recorded -- not weakened
        to green.
        """
        for path, _, key, job in self._reporters():
            with self.subTest(workflow=path.name, job=key):
                urls = ping_urls(job_code(job))
                failing = [url for url in urls if "/fail" in url]
                succeeding = [url for url in urls if "/fail" not in url]
                self.assertTrue(
                    failing and succeeding,
                    f"{path.name}'s reporting job {key!r} does not carry both a success "
                    f"and a /fail ping URL; it carries {urls}",
                )
                without = sorted(url for url in urls if "create=1" not in url)
                self.assertEqual(
                    [],
                    without,
                    f"{path.name}'s reporting job {key!r} carries ping URLs without "
                    f"`create=1`: {without}. A ping to a check that does not exist "
                    "404s silently, and the failure path is where that matters most",
                )


class TestEveryTimerInstallingRoleReportsItsUnitsLiveness(unittest.TestCase):
    """ADDED requirement: Scheduled Host Units Report Their Own Liveness."""

    def setUp(self) -> None:
        self.roles = timer_installing_roles()

    def test_at_least_one_role_installs_a_timer_unit(self) -> None:
        """DERIVED (tasks.md 4.7, which states the obligation in those words)
        -- the assertions below are universally quantified over what discovery
        finds. A role that later writes its units from a file under
        `templates/` rather than inline would leave them quantified over an
        empty set, and green. Failing here is what turns that into a visible
        change of shape rather than a silent loss of cover.
        """
        self.assertTrue(
            self.roles,
            "no role under ansible/roles/ installs a `.timer` unit inline in its "
            "tasks/main.yml, so every assertion about scheduled host units below "
            "would pass having read nothing. `image_prune` installs one; if this "
            "fails, the discovery no longer matches the shape this repository "
            "writes its units in",
        )

    def test_every_timer_installs_a_service_unit_of_its_own(self) -> None:
        """SPECIFIED -- the requirement is over "Every scheduled unit whose
        definition a role in this repository writes"; the service unit is
        where the report is attached, so a timer without one cannot carry a
        report at all."""
        self.test_at_least_one_role_installs_a_timer_unit()
        for role, units in self.roles.items():
            installed = inline_files_installed_by(role)
            for dest in units:
                with self.subTest(role=role, timer=dest):
                    service = [
                        other
                        for other in installed
                        if other.endswith(".service")
                        and unit_stem(other) == unit_stem(dest)
                    ]
                    self.assertTrue(
                        service,
                        f"{role} installs {dest} but no {unit_stem(dest)}.service "
                        "carrying its definition",
                    )

    def _service_units(self) -> list:
        self.test_at_least_one_role_installs_a_timer_unit()
        found = []
        for role, units in self.roles.items():
            installed = inline_files_installed_by(role)
            for dest in units:
                for other, spec in installed.items():
                    if other.endswith(".service") and unit_stem(other) == unit_stem(dest):
                        found.append((role, other, spec))
        self.assertTrue(found, "no service unit was found for any installed timer")
        return found

    def test_every_such_service_unit_reports_from_the_init_system(self) -> None:
        """SPECIFIED -- "The report SHALL come from the init system rather
        than from inside the unit's own script", and scenario "A run killed by
        its own bound is reported": a run terminated from outside the process
        cannot report its own death, and that kill is precisely the case the
        duration bound exists for. `ExecStopPost=` is DERIVED (design Decision
        9) as the one directive that runs on every exit path including that
        kill -- unlike `OnFailure=` (failure only) or `ExecStartPost=`
        (success path only).
        """
        for role, dest, spec in self._service_units():
            with self.subTest(role=role, unit=dest):
                self.assertIn(
                    "ExecStopPost=",
                    spec["content"],
                    f"{role}'s {dest} carries no ExecStopPost=. A run killed on its "
                    "own TimeoutStartSec produces no output and cannot report itself; "
                    "only the init system can report that activation",
                )

    def test_a_failed_report_cannot_fail_the_unit(self) -> None:
        """SPECIFIED -- scenario "An undeliverable report leaves a local
        trace": "the unit's own result SHALL be unaffected by the delivery
        having failed". A prune that did its work correctly must not be
        recorded as failed because a third party was briefly unreachable; the
        unsent ping becomes silence, and silence is what the observer alarms
        on. The `-` prefix is systemd's spelling of that (design Decision 9).
        """
        for role, dest, spec in self._service_units():
            with self.subTest(role=role, unit=dest):
                lines = [
                    line.strip()
                    for line in spec["content"].splitlines()
                    if line.strip().startswith("ExecStopPost=")
                ]
                self.assertTrue(lines, f"{role}'s {dest} carries no ExecStopPost= line")
                unprefixed = [
                    line
                    for line in lines
                    if not line.split("=", 1)[1].lstrip().startswith("-")
                ]
                self.assertEqual(
                    [],
                    unprefixed,
                    f"{role}'s {dest} has ExecStopPost= lines that are not prefixed "
                    f"with `-`: {unprefixed}. Without it a failed ping marks a "
                    "SUCCESSFUL run's unit failed, which reports the third party's "
                    "outage as a defect in this host's own work",
                )

    def test_every_host_reporter_addresses_a_slug_templated_per_host(self) -> None:
        """SPECIFIED -- "The identifier the unit reports under SHALL be
        distinct from every other reporter's". The specific template
        (`{{ inventory_hostname }}-<unit stem>`) is DERIVED, from design
        Decision 4: this role is meant to be run against a second host, and
        two hosts sharing one check would mean the live host's weekly success
        keeps the check green while the other host's timer is dead. Templating
        makes that collision unreachable rather than documented.
        """
        self.test_at_least_one_role_installs_a_timer_unit()
        for role, units in self.roles.items():
            joined = "\n".join(role_texts(role).values())
            for dest in units:
                with self.subTest(role=role, timer=dest):
                    pattern = re.compile(
                        r"\{\{\s*inventory_hostname\s*\}\}-" + re.escape(unit_stem(dest))
                    )
                    self.assertTrue(
                        pattern.search(joined),
                        f"{role} does not address a check named "
                        f"`{{{{ inventory_hostname }}}}-{unit_stem(dest)}`. A slug "
                        "written as a literal makes a second converged host share this "
                        "one's check and mask its silence",
                    )


class TestEveryReportersIdentifierIsDistinct(unittest.TestCase):
    """ADDED requirements: Scheduled Workflows Report Their Own Liveness, and
    Scheduled Host Units Report Their Own Liveness.

    The host delta's distinctness clause reaches ACROSS the two halves of this
    change -- "distinct from every other reporter's -- every other unit's and
    every schedule-triggered workflow's" -- which no single-role or
    single-workflow test can establish (tasks.md 4.6).
    """

    def _identifiers(self) -> dict:
        found = {}
        scheduled = scheduled_workflows()
        self.assertTrue(
            scheduled,
            "no schedule-triggered workflow was discovered, so this distinctness "
            "assertion would compare an empty set with itself and pass",
        )
        for path, workflow in scheduled:
            reporters = liveness_reporting_jobs(workflow)
            self.assertTrue(reporters, f"{path.name} carries no liveness report")
            slugs = sorted(
                {
                    slug
                    for _, job in reporters
                    for slug in (endpoint_slug(url) for url in ping_urls(job_code(job)))
                    if slug
                }
            )
            self.assertEqual(
                1,
                len(slugs),
                f"{path.name} addresses {slugs}; a reporter addressing none has no "
                "identifier to be distinct, and one addressing several cannot be told "
                "apart from a reporter that was copied and half-edited",
            )
            found[f".github/workflows/{path.name}"] = slugs[0]

        roles = timer_installing_roles()
        self.assertTrue(
            roles,
            "no timer-installing role was discovered, so the host half of this "
            "distinctness assertion would read nothing",
        )
        for role, units in roles.items():
            joined = "\n".join(role_texts(role).values())
            for dest in units:
                match = re.search(
                    r"\{\{\s*inventory_hostname\s*\}\}-(" + re.escape(unit_stem(dest)) + r")",
                    joined,
                )
                self.assertIsNotNone(
                    match,
                    f"{role} addresses no per-host slug for {dest}; see the test that "
                    "states that obligation on its own",
                )
                found[f"ansible/roles/{role}:{unit_stem(dest)}"] = (
                    "{{ inventory_hostname }}-" + match.group(1)
                )
        return found

    def test_every_reporter_this_repository_defines_addresses_its_own_check(self) -> None:
        """SPECIFIED -- "distinct per workflow" (CI delta) and "distinct from
        every other reporter's" (host delta). Two reporters sharing one check
        means one of them going silent is invisible for as long as the other
        keeps reporting."""
        identifiers = self._identifiers()
        self.assertGreaterEqual(
            len(identifiers),
            2,
            "fewer than two reporters were discovered, so pairwise distinctness "
            f"establishes nothing: {identifiers}",
        )
        values = list(identifiers.values())
        collisions = {
            slug: sorted(name for name, value in identifiers.items() if value == slug)
            for slug in set(values)
            if values.count(slug) > 1
        }
        self.assertEqual(
            {},
            collisions,
            f"these reporters share a check identifier: {collisions}. One of them "
            "going silent stays invisible for as long as the other keeps reporting",
        )


class TestTheHostReporterKeepsTheAddressOffTheCommandLine(unittest.TestCase):
    """ADDED requirement: Scheduled Host Units Report Their Own Liveness."""

    def _scripts(self) -> list:
        roles = timer_installing_roles()
        self.assertTrue(
            roles,
            "no timer-installing role was discovered, so every assertion about a "
            "reporting script below would read nothing",
        )
        found = []
        for role in roles:
            scripts = reporting_scripts(role)
            self.assertTrue(
                scripts,
                f"{role} installs a timer unit and carries no committed text invoking "
                "curl, so there is no reporting script to read. The report is what "
                "makes a unit that fails, is killed, or stops being scheduled visible",
            )
            for label, text in scripts.items():
                found.append((role, label, text))
        return found

    def test_the_reporting_script_hands_curl_the_url_off_its_command_line(self) -> None:
        """SPECIFIED -- the address "SHALL NOT be left world-readable on the
        host": a command line is readable from `/proc/<pid>/cmdline` by any
        local account for as long as the process runs, and this host
        deliberately carries unprivileged operator accounts. Expanding the
        ping key into argv defeats the `0600` file it was just read from,
        during exactly the window the ping is in flight. `--config` (or `-K`)
        is DERIVED, from design Decision 9, as curl's way of taking a URL off
        the command line.
        """
        for role, label, text in self._scripts():
            for invocation in curl_invocations(text):
                with self.subTest(role=role, script=label, invocation=invocation[:60]):
                    arguments = curl_arguments(invocation)
                    self.assertTrue(
                        any(argument in ("--config", "-K") for argument in arguments),
                        f"{role}'s {label} invokes curl without `--config`/`-K`, so "
                        "the URL can only have reached it on the command line: "
                        f"{invocation}",
                    )

    def test_no_curl_argument_carries_or_expands_to_the_url_or_the_ping_key(self) -> None:
        """SPECIFIED -- as above, and this is the negative that has to be
        precise. FORBIDDING ONLY A LITERAL IS NOT ENOUGH: `curl "$PING_URL"`
        contains no literal and puts the key in `/proc/<pid>/cmdline` exactly
        as the requirement forbids. So this refuses BOTH a literal URL and ANY
        parameter expansion or command substitution among curl's arguments --
        a variable's value is not readable from here, so an argument that
        expands to something cannot be shown not to expand to the address.

        The width of that negative is DERIVED (tasks.md 4.8a states the
        obligation; refusing every expansion is this test's way of meeting
        it), and it has a cost worth naming: `--max-time "$timeout"` would
        fail here too. Reconsider this assertion deliberately, and record the
        reconsideration, if an implementation needs an expansion that provably
        cannot carry the address -- do not weaken it to green.
        """
        for role, label, text in self._scripts():
            for invocation in curl_invocations(text):
                with self.subTest(role=role, script=label, invocation=invocation[:60]):
                    offending = curl_arguments_carrying_an_address(invocation)
                    self.assertEqual(
                        [],
                        offending,
                        f"{role}'s {label} passes {offending} on curl's command line. "
                        "A literal address, or a variable that may hold one, is "
                        "readable from /proc/<pid>/cmdline by any local account while "
                        f"the ping is in flight: {invocation}",
                    )

    def test_both_endpoints_the_reporter_builds_request_the_check_be_created(self) -> None:
        """DERIVED (design Decision 5, tasks.md 4.8a) -- Decision 5 calls a
        missing check "the worst one available here" and names the
        chronically failing prune as its example: a unit that fails from its
        first activation never takes the success path, so a success-only
        `create=1` leaves its check never created, its /fail pings 404ing, and
        the unit reported by nothing.

        Reads the same two-whole-endpoints shape the continuous-integration
        half does, and carries the same caveat: an implementation that appends
        `/fail` and the query string separately satisfies the requirement and
        fails this test. That is a reconsideration, recorded, and not a
        weakening.
        """
        for role, label, text in self._scripts():
            with self.subTest(role=role, script=label):
                endpoints = shell_endpoints(text)
                failing = [endpoint for endpoint in endpoints if "/fail" in endpoint]
                succeeding = [endpoint for endpoint in endpoints if "/fail" not in endpoint]
                self.assertTrue(
                    failing and succeeding,
                    f"{role}'s {label} does not build both a success and a /fail "
                    f"endpoint; what was read: {endpoints}",
                )
                without = sorted(
                    endpoint for endpoint in endpoints if "create=1" not in endpoint
                )
                self.assertEqual(
                    [],
                    without,
                    f"{role}'s {label} builds endpoints without `create=1`: {without}",
                )

    def test_the_report_branches_on_the_service_result_not_the_exit_status(self) -> None:
        """SPECIFIED -- scenario "A run killed by its own bound is reported":
        a unit "terminated by the init system on expiry of its configured
        start timeout, producing no output of its own" SHALL still report a
        failure. systemd sets `$EXIT_STATUS` to a SIGNAL NAME (`KILL`) on
        exactly that path, so any construction treating it as a number breaks
        there and only there -- the worst place for a defect to hide.
        `$SERVICE_RESULT` is the discriminator (design Decision 9);
        `$EXIT_STATUS` may be carried as diagnostic text, and that use is not
        what this forbids.
        """
        for role, label, text in self._scripts():
            with self.subTest(role=role, script=label):
                body = without_shell_comments(text)
                self.assertIn(
                    "SERVICE_RESULT",
                    body,
                    f"{role}'s {label} never reads $SERVICE_RESULT, so it cannot tell "
                    "a successful activation from one killed on its start timeout",
                )
                branching = [
                    line.strip()
                    for line in body.splitlines()
                    if "EXIT_STATUS" in line
                    and re.search(r"^\s*(if|elif|case|while|until)\b|\[\[|\[ ", line)
                ]
                self.assertEqual(
                    [],
                    branching,
                    f"{role}'s {label} branches on $EXIT_STATUS: {branching}. On the "
                    "TimeoutStartSec path -- the one this reporting exists for -- "
                    "systemd sets it to `KILL`, a signal name and not a number",
                )

    def test_an_undeliverable_report_is_written_to_the_hosts_log(self) -> None:
        """SPECIFIED -- scenario "An undeliverable report leaves a local
        trace": "the attempted endpoint and the delivery's outcome SHALL be
        written to the host's log". Because the `-` prefix makes a failed ping
        invisible to systemd deliberately, this write is the ONLY local trace
        of it -- an operator answering the resulting silence days later
        otherwise finds a successful unit and no account of why nothing was
        reported. Curl's `--show-error` and the script's own stderr write are
        DERIVED (tasks.md 3.3/4.8a) as the means; that stderr from
        `ExecStopPost=` reaches the journal is systemd's behaviour.
        """
        for role, label, text in self._scripts():
            for invocation in curl_invocations(text):
                with self.subTest(role=role, script=label, invocation=invocation[:60]):
                    arguments = curl_arguments(invocation)
                    self.assertTrue(
                        any(
                            argument in ("--show-error", "-S")
                            or (
                                argument.startswith("-")
                                and not argument.startswith("--")
                                and "S" in argument
                            )
                            for argument in arguments
                        ),
                        f"{role}'s {label} invokes curl without --show-error, so a "
                        f"failed delivery says nothing at all: {invocation}",
                    )
                    silenced = [
                        argument for argument in arguments if argument.startswith("2>")
                    ]
                    self.assertEqual(
                        [],
                        silenced,
                        f"{role}'s {label} redirects curl's stderr away: {silenced}. "
                        "The journal is then the only trace of an undeliverable "
                        "report, and it would be empty",
                    )
            with self.subTest(role=role, script=label, wrote="stderr"):
                written = [
                    line.strip()
                    for line in without_shell_comments(text).splitlines()
                    if ">&2" in line
                ]
                self.assertTrue(
                    written,
                    f"{role}'s {label} writes nothing to stderr, so the endpoint it "
                    "tried is recorded nowhere on this host",
                )


class TestNoTimerRoleScenarioReachesTheExternalObserver(unittest.TestCase):
    """ADDED requirement: Scheduled Host Units Report Their Own Liveness --
    scenario "A report is observable without reaching the external observer".

    This is what turns "the reporting scenarios use a sink" from a constraint
    on one scenario into a property of ALL of them (tasks.md 4.8b, 4.11). The
    role's scenarios activate the unit, so a scenario left on the production
    base URL would ping the observer from a hosted runner and, with
    `?create=1`, CREATE a check there -- on every pull request touching
    `ansible/`.
    """

    def _scenarios(self) -> list:
        roles = timer_installing_roles()
        self.assertTrue(
            roles,
            "no timer-installing role was discovered, so this assertion would read "
            "no scenario at all",
        )
        found = []
        for role in roles:
            scenarios = scenario_directories(role)
            self.assertTrue(
                scenarios,
                f"{role} installs a timer unit and carries no Molecule scenario, so "
                "nothing observes what its reporting converges to",
            )
            found.extend((role, scenario) for scenario in scenarios)
        return found

    def test_no_scenario_leaves_the_reporter_pointed_at_the_external_observer(self) -> None:
        """SPECIFIED -- the report "SHALL be directable to a local
        destination, so that what a failing, a killed and a successful
        activation report can be asserted without a credential or a call to
        the third-party observer". Asserted over EVERY scenario, including the
        ones that assert nothing about reporting: it is those that would ping
        the observer unnoticed. The variable's name is DERIVED, from tasks.md
        3.1.
        """
        for role, scenario in self._scenarios():
            invocations = scenario_role_invocations(scenario, role)
            self.assertTrue(
                invocations,
                f"{role}/molecule/{scenario.name} converges {role} nowhere this read "
                "can see, so every assertion below would pass having read nothing",
            )
            for playbook, supplied in invocations:
                with self.subTest(
                    role=role, scenario=scenario.name, playbook=playbook
                ):
                    variable = f"{role}_heartbeat_base_url"
                    self.assertIn(
                        variable,
                        supplied,
                        f"{role}/molecule/{scenario.name}/{playbook} converges the "
                        f"role supplying no {variable}, so the reporter runs against "
                        "its production default and pings the external observer from "
                        "a hosted runner",
                    )
                    value = str(supplied[variable])
                    self.assertNotEqual(
                        PRODUCTION_HEARTBEAT_BASE_URL,
                        value.rstrip("/"),
                        f"{role}/molecule/{scenario.name}/{playbook} points the "
                        "reporter at the production observer",
                    )
                    self.assertTrue(
                        any(
                            local in value
                            for local in ("127.0.0.1", "localhost", "[::1]")
                        ),
                        f"{role}/molecule/{scenario.name}/{playbook} points the "
                        f"reporter at {value!r}, which is not a local sink -- a "
                        "scenario may reach no third party",
                    )

    def test_every_scenario_supplies_the_ping_key_the_role_requires(self) -> None:
        """DERIVED (tasks.md 3.6/4.8b) -- the requirement itself makes the
        address a required input; this is the consequence for the scenarios,
        and without it `molecule test --all` is red on its first run for a
        reason no other test explains.

        A scenario that converges the role EXPECTING it to fail is exempt, and
        is identified by its `rescue:` rather than by its name: it is the host
        delta's "An absent report address is reported by name", and obliging
        it to supply the address would delete the scenario it exists to be.
        """
        for role, scenario in self._scenarios():
            if scenario_expects_a_refusal(scenario):
                continue
            invocations = scenario_role_invocations(scenario, role)
            self.assertTrue(
                invocations,
                f"{role}/molecule/{scenario.name} converges {role} nowhere this read "
                "can see, so this assertion would pass having read nothing",
            )
            for playbook, supplied in invocations:
                with self.subTest(
                    role=role, scenario=scenario.name, playbook=playbook
                ):
                    variable = f"{role}_heartbeat_ping_key"
                    self.assertIn(
                        variable,
                        supplied,
                        f"{role}/molecule/{scenario.name}/{playbook} converges the "
                        f"role supplying no {variable}; the role requires it and this "
                        "scenario does not converge expecting a refusal, so the run "
                        "fails for want of an input rather than on anything it "
                        "asserts -- a re-converge from verify.yml is a converge",
                    )


class TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource(unittest.TestCase):
    """ADDED requirement: The Continuous-Integration Configuration Is Itself
    Verified -- scenario "The suite needs no privileged or external resource".

    `TestTheSuiteNeedsNoPrivilegedResource` above audits THIS MODULE by name.
    `notice-when-a-periodic-job-stops-reporting`'s tasks.md 4.11 states the
    constraint over `.github/tests` as a whole -- no network call, no
    credential, no container runtime, no Terraform binary -- and that change
    adds assertions about URLs which must never be requested. A module added
    to this directory later would be outside an audit by name; this reads
    every module the directory holds, and reuses that audit's own constants so
    the two cannot drift apart.
    """

    def _modules(self) -> list:
        modules = sorted(SUITE_DIR.glob("*.py"))
        self.assertTrue(
            modules,
            f"no Python module was discovered under {SUITE_DIR}, so this audit would "
            "pass having read nothing -- this file is one",
        )
        return modules

    def _imported_roots(self, module: Path) -> set:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
        return roots

    def test_no_module_in_the_directory_imports_a_network_capable_module(self) -> None:
        """SPECIFIED -- the suite completes without a network call. The
        reporters' URLs are asserted as TEXT and are never requested; this is
        what holds that for the directory rather than for one file."""
        for module in self._modules():
            with self.subTest(module=module.name):
                offenders = sorted(
                    self._imported_roots(module)
                    & TestTheSuiteNeedsNoPrivilegedResource.NETWORK_MODULES
                )
                self.assertEqual(
                    [],
                    offenders,
                    f"{module.name} imports network-capable modules: {offenders}",
                )

    def test_no_module_in_the_directory_imports_outside_the_pinned_manifest(self) -> None:
        """SPECIFIED -- "SHALL depend only on its runtime's standard library
        and on dependencies pinned exactly in a repository manifest".

        A module of this suite importing a SIBLING module of the same suite is
        neither: it is the suite reusing its own helpers, which is what keeps a
        discovery rule or a parser in one place. Two modules on the trunk do
        exactly that. So the siblings are enumerated from the directory and
        allowed -- narrowly, by their own filenames, so that an import of
        anything the directory does not contain still fails.
        """
        siblings = {module.stem for module in self._modules()}
        for module in self._modules():
            with self.subTest(module=module.name):
                outside = sorted(
                    root
                    for root in self._imported_roots(module)
                    if root not in sys.stdlib_module_names
                    and root not in TestTheSuiteNeedsNoPrivilegedResource.ALLOWED_THIRD_PARTY
                    and root not in siblings
                )
                self.assertEqual(
                    [],
                    outside,
                    f"{module.name} imports neither standard library nor a pinned "
                    f"dependency: {outside}",
                )

    def test_no_module_in_the_directory_spawns_a_container_runtime_or_terraform(self) -> None:
        """SPECIFIED -- the suite completes without a container runtime or a
        Terraform binary. Reads each module's own `subprocess` calls out of
        its AST, as the audit above does, rather than grepping its text."""
        for module in self._modules():
            with self.subTest(module=module.name):
                tree = ast.parse(module.read_text(encoding="utf-8"))
                spawned = []
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    target = node.func
                    if not (
                        isinstance(target, ast.Attribute)
                        and target.attr
                        in ("run", "Popen", "call", "check_output", "check_call")
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "subprocess"
                    ):
                        continue
                    if not node.args:
                        continue
                    argv = node.args[0]
                    if isinstance(argv, ast.List) and argv.elts:
                        head = argv.elts[0]
                        if isinstance(head, ast.Constant) and isinstance(head.value, str):
                            spawned.append(head.value)
                    elif isinstance(argv, ast.Constant) and isinstance(argv.value, str):
                        words = argv.value.split()
                        spawned.append(words[0] if words else argv.value)
                offenders = sorted(
                    {
                        name
                        for name in spawned
                        if name not in TestTheSuiteNeedsNoPrivilegedResource.SPAWNABLE
                    }
                )
                self.assertEqual(
                    [],
                    offenders,
                    f"{module.name} spawns commands outside the shell the suite needs "
                    f"to exercise a workflow snippet: {offenders}",
                )

class TestTheLivenessChecksAreARealReadOfTheFile(unittest.TestCase):
    """ADDED requirements: Scheduled Workflows Report Their Own Liveness, and
    Scheduled Host Units Report Their Own Liveness.

    Every assertion above this class is red until
    `notice-when-a-periodic-job-stops-reporting` is implemented, so nothing
    else here establishes that they would go GREEN on a conforming reporter --
    or that they would stay red on the specific defects they name. A check
    that can only fail is worth as little as one that can only pass.

    So this class exercises the same predicates against fixture text: one
    shape the change's tasks.md prescribes, and one defect per assertion. It
    reads no committed file and is expected to pass from the moment it is
    written, which is the opposite of every other new test in this section and
    is stated so that its passing is not mistaken for coverage of the change.
    """

    CONFORMING_REPORTER = {
        "name": "report",
        "needs": ["drift"],
        "if": "always()",
        "steps": [
            {
                "name": "Report this run's liveness to the external observer",
                "if": "${{ !cancelled() && !contains(needs.*.result, 'failure') }}",
                "env": {"KEY": "${{ secrets.HEARTBEAT_PING_KEY }}"},
                "run": (
                    "# Silence, not this ping, is what raises the alarm.\n"
                    'curl --fail --silent --show-error --retry 3 '
                    '"https://hc-ping.com/$KEY/infrastructure-drift?create=1"\n'
                ),
            },
            {
                "name": "Report this run's failure",
                "if": "${{ !cancelled() && contains(needs.*.result, 'failure') }}",
                "env": {"KEY": "${{ secrets.HEARTBEAT_PING_KEY }}"},
                "run": (
                    'curl --fail --silent --show-error --retry 3 '
                    '"https://hc-ping.com/$KEY/infrastructure-drift/fail?create=1"\n'
                ),
            },
        ],
    }

    CONFORMING_SCRIPT = (
        "#!/bin/bash\n"
        "# Reports this unit's activation. See https://hc-ping.com in a comment only.\n"
        "set -euo pipefail\n"
        ". /etc/prune-host-images/heartbeat.env\n"
        'endpoint="${HEARTBEAT_BASE_URL}/${HEARTBEAT_PING_KEY}/${HEARTBEAT_SLUG}?create=1"\n'
        'if [ "${SERVICE_RESULT:-}" != "success" ]; then\n'
        '  endpoint="${HEARTBEAT_BASE_URL}/${HEARTBEAT_PING_KEY}/${HEARTBEAT_SLUG}/fail?create=1"\n'
        "fi\n"
        'printf "url = \\"%s\\"\\n" "$endpoint" | '
        "curl --config - --max-time 10 --retry 2 --silent --show-error "
        '--data-raw "EXIT_STATUS=${EXIT_STATUS:-}"\n'
        'status=$?\n'
        'printf "prune-host-images: reported %s (curl status %s)\\n" "$endpoint" "$status" >&2\n'
    )

    def test_a_conforming_reporting_job_is_recognised_as_one(self) -> None:
        self.assertTrue(
            LIVENESS_HINT.search(job_code(self.CONFORMING_REPORTER)),
            "the shape tasks.md 2.1 prescribes is not recognised as a reporting job, "
            "so every assertion quantified over reporting jobs would read nothing",
        )

    def test_a_job_naming_a_reporter_only_in_a_comment_is_not_recognised(self) -> None:
        commented = {
            "name": "drift",
            "steps": [{"name": "plan", "run": "# no heartbeat here yet\nterraform plan\n"}],
        }
        self.assertIsNone(
            LIVENESS_HINT.search(job_code(commented)),
            "a job that only MENTIONS a heartbeat in a shell comment is read as "
            "carrying one, which would let a comment satisfy the coverage assertion",
        )

    def test_both_ping_urls_are_read_from_a_conforming_job(self) -> None:
        urls = ping_urls(job_code(self.CONFORMING_REPORTER))
        self.assertEqual(2, len(urls), urls)
        self.assertTrue(all("create=1" in url for url in urls), urls)
        self.assertEqual(
            ["infrastructure-drift"],
            sorted({endpoint_slug(url) for url in urls}),
            "the success URL and the /fail URL must read as addressing ONE check; "
            f"they read as {[endpoint_slug(url) for url in urls]}",
        )

    def test_a_ping_url_written_as_a_github_expression_is_still_read(self) -> None:
        """`${{ secrets.X }}` carries spaces. Without collapsing it first, a URL
        token would end at the first space and both the slug and `create=1`
        would be invisible -- the check would pass by reading nothing."""
        job = {
            "steps": [
                {
                    "name": "heartbeat",
                    "run": (
                        "curl --fail "
                        '"https://hc-ping.com/${{ secrets.HEARTBEAT_PING_KEY }}'
                        '/infrastructure-drift?create=1"\n'
                    ),
                }
            ]
        }
        urls = ping_urls(job_code(job))
        self.assertEqual(1, len(urls), urls)
        self.assertIn("create=1", urls[0])
        self.assertEqual("infrastructure-drift", endpoint_slug(urls[0]))

    def test_a_ping_url_missing_create_is_read_as_missing_it(self) -> None:
        url = "https://hc-ping.com/$KEY/infrastructure-drift/fail"
        self.assertNotIn("create=1", url)
        self.assertEqual("infrastructure-drift", endpoint_slug(url))

    def test_curl_passing_a_url_variable_is_flagged(self) -> None:
        """THE EXACT DEFECT tasks.md 4.8a names: `curl "$PING_URL"` carries no
        literal address and puts the ping key in `/proc/<pid>/cmdline` all the
        same. A negative that forbade only a literal would pass it."""
        invocations = curl_invocations('curl --fail --silent "$PING_URL"\n')
        self.assertEqual(1, len(invocations), invocations)
        self.assertEqual(
            ['"$PING_URL"'], curl_arguments_carrying_an_address(invocations[0])
        )

    def test_curl_passing_a_literal_url_is_flagged(self) -> None:
        invocations = curl_invocations('curl "https://hc-ping.com/k/s?create=1"\n')
        self.assertEqual(
            ['"https://hc-ping.com/k/s?create=1"'],
            curl_arguments_carrying_an_address(invocations[0]),
        )

    def test_a_conforming_script_passes_every_assertion_made_about_one(self) -> None:
        """The one test here that would catch this section shipping assertions
        no conforming implementation can satisfy: it runs the whole host-side
        read against the shape tasks.md 3.3 prescribes."""
        text = self.CONFORMING_SCRIPT
        invocations = curl_invocations(text)
        self.assertEqual(1, len(invocations), invocations)
        arguments = curl_arguments(invocations[0])
        self.assertIn("--config", arguments)
        self.assertEqual(
            [],
            curl_arguments_carrying_an_address(invocations[0]),
            f"a conforming script's own curl line was flagged: {arguments}",
        )
        self.assertIn("--show-error", arguments)

        endpoints = shell_endpoints(text)
        self.assertTrue(
            [endpoint for endpoint in endpoints if "/fail" in endpoint], endpoints
        )
        self.assertTrue(
            [endpoint for endpoint in endpoints if "/fail" not in endpoint], endpoints
        )
        self.assertEqual(
            [],
            [endpoint for endpoint in endpoints if "create=1" not in endpoint],
            f"a conforming script's endpoints were read as missing create=1: {endpoints}",
        )
        self.assertIn("SERVICE_RESULT", without_shell_comments(text))
        self.assertTrue(
            [line for line in text.splitlines() if ">&2" in line],
            "a conforming script's stderr write was not seen",
        )

    def test_a_script_branching_on_the_exit_status_is_flagged(self) -> None:
        """systemd sets `$EXIT_STATUS` to `KILL` on the TimeoutStartSec path --
        the one path this reporting exists for."""
        text = 'if [ "$EXIT_STATUS" -eq 0 ]; then\n  :\nfi\n'
        branching = [
            line.strip()
            for line in without_shell_comments(text).splitlines()
            if "EXIT_STATUS" in line
            and re.search(r"^\s*(if|elif|case|while|until)\b|\[\[|\[ ", line)
        ]
        self.assertEqual(1, len(branching), branching)

    def test_carrying_the_exit_status_as_diagnostic_text_is_not_flagged(self) -> None:
        """The complement of the test above, so that the assertion is known to
        forbid the branch rather than the variable: Decision 9 carries
        `$EXIT_STATUS` through as diagnostic text deliberately."""
        text = 'printf "status=%s\\n" "${EXIT_STATUS:-}" >&2\n'
        branching = [
            line.strip()
            for line in without_shell_comments(text).splitlines()
            if "EXIT_STATUS" in line
            and re.search(r"^\s*(if|elif|case|while|until)\b|\[\[|\[ ", line)
        ]
        self.assertEqual([], branching)

    def test_a_scenarios_variables_are_read_from_its_converge_playbook(self) -> None:
        """The scenario read is the one property here that touches the
        filesystem, so it is exercised against a scratch tree rather than
        against a committed scenario -- which, before this change is
        implemented, supplies neither variable."""
        scratch = Path(tempfile.mkdtemp(prefix="heartbeat-scenario-"))
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        (scratch / "converge.yml").write_text(
            "---\n"
            "- name: Prepare\n"
            "  hosts: all\n"
            "  tasks: []\n"
            "- name: Converge\n"
            "  hosts: all\n"
            "  vars:\n"
            "    image_prune_heartbeat_base_url: http://127.0.0.1:8099\n"
            "    image_prune_heartbeat_ping_key: fixture-key\n"
            "  roles:\n"
            "    - role: image_prune\n",
            encoding="utf-8",
        )
        invocations = scenario_role_invocations(scratch, "image_prune")
        self.assertEqual(
            1,
            len(invocations),
            "the scenario read found the wrong number of role convergences",
        )
        _, supplied = invocations[0]
        self.assertEqual(
            "http://127.0.0.1:8099", supplied["image_prune_heartbeat_base_url"]
        )
        self.assertEqual("fixture-key", supplied["image_prune_heartbeat_ping_key"])

    def test_a_re_converge_from_a_verify_playbook_is_read_as_a_convergence(self) -> None:
        """Reading `converge.yml` alone was not enough, and this fixture is
        why: `default` and `abandon-paths` both converge the role a second
        time from their `verify.yml`, through `include_role` with task-level
        `vars:`. Those re-converges need the role's required inputs and, left
        on the production base URL, would ping the external observer exactly
        as a converge would. Both scenarios failed on this after the narrower
        read passed them."""
        scratch = Path(tempfile.mkdtemp(prefix="heartbeat-reconverge-"))
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        (scratch / "converge.yml").write_text(
            "---\n"
            "- name: Converge\n"
            "  hosts: all\n"
            "  vars:\n"
            "    image_prune_heartbeat_base_url: http://127.0.0.1:8099\n"
            "    image_prune_heartbeat_ping_key: fixture-key\n"
            "  roles:\n"
            "    - role: image_prune\n",
            encoding="utf-8",
        )
        (scratch / "verify.yml").write_text(
            "---\n"
            "- name: Verify\n"
            "  hosts: all\n"
            "  tasks:\n"
            "    - name: Re-converge with a reduced enumeration\n"
            "      ansible.builtin.include_role:\n"
            "        name: image_prune\n"
            "      vars:\n"
            "        deploy_apps: []\n",
            encoding="utf-8",
        )
        invocations = scenario_role_invocations(scratch, "image_prune")
        playbooks = sorted(playbook for playbook, _ in invocations)
        self.assertEqual(
            ["converge.yml", "verify.yml"],
            playbooks,
            "a re-converge from verify.yml was not read as a convergence, so a "
            "scenario could point it at the production observer unnoticed",
        )
        supplied = dict(invocations)["verify.yml"]
        self.assertNotIn(
            "image_prune_heartbeat_base_url",
            supplied,
            "this fixture's re-converge deliberately supplies no base URL: the read "
            "must report what that invocation actually has in force, not what a "
            "sibling playbook supplied",
        )
        self.assertFalse(
            scenario_expects_a_refusal(scratch),
            "a scenario with no rescue: was read as one that expects a refusal, which "
            "would exempt every scenario from supplying the ping key",
        )

    def test_a_scenario_that_expects_a_refusal_is_recognised_as_one(self) -> None:
        scratch = Path(tempfile.mkdtemp(prefix="heartbeat-refusal-"))
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        (scratch / "converge.yml").write_text(
            "---\n"
            "- name: Converge\n"
            "  hosts: all\n"
            "  tasks:\n"
            "    - name: Converge with no ping key supplied\n"
            "      block:\n"
            "        - name: Run the role\n"
            "          ansible.builtin.include_role:\n"
            "            name: image_prune\n"
            "      rescue:\n"
            "        - name: Record the refusal\n"
            "          ansible.builtin.debug:\n"
            "            msg: refused\n",
            encoding="utf-8",
        )
        self.assertTrue(scenario_expects_a_refusal(scratch))


# ============================================================================
# The repository's tracked files, and the credential scans built on them.
#
# These three scans arrived here from Molecule verify plays, where they were
# static reads of committed files wearing the shape of host verification. Two
# scanned the whole repository and one scanned `ansible/inventory/`, and all
# three ran only on pull requests that happened to change `ansible/` -- which
# is not the scope a repository-wide claim needs. They run here on every pull
# request instead, which is what makes the claim true, and their relocation is
# what made narrowing the Molecule trigger safe: excluding `ansible/inventory/`
# would otherwise have withdrawn the only check reading it.
#
# See the change `narrow-the-molecule-trigger-to-what-it-reads`, design.md
# Decisions 4 and 5.
# ============================================================================


class TrackedFilesUnavailable(AssertionError):
    """The repository's tracked files could not be enumerated.

    An AssertionError rather than a skip, and that is the whole point. This
    suite's other external-tool guards skip when their tool is missing, which
    is the right shape for an assertion whose absence leaves another check
    standing. It is the wrong shape here: a scan for committed credential
    material that skips reports success for a property nothing examined, and
    nothing else in this repository reads the tracked tree.
    """


def tracked_files(root: Path | None = None) -> dict[str, bytes]:
    """Every tracked file, as repository-relative path -> bytes.

    THE FILE SET IS TRACKED FILES, NOT A FILESYSTEM WALK. This suite runs on
    developer machines as well as on runners, and a working tree holds what a
    checkout does not: dependency caches, virtual environments, `.molecule-home/`,
    sibling working trees under `.claude/worktrees/`, and the gitignored
    `ansible/.envrc` where a real GHCR pull token legitimately lives. Walking
    those reports a developer's own uncommitted credential as a committed
    secret, and the remedy anyone reaches for is a path-exclusion list -- which
    blinds the scan permanently in whichever directory acquired it. An
    uncommitted credential is the commit hook's to catch; this suite's subject
    is the committed file.

    BYTES, NOT DECODED TEXT. The markers are ASCII, and decoding every tracked
    file would make an undecodable one -- none is tracked today, nothing
    prevents one -- a hard failure that examined nothing.

    Spawning the version-control binary is this suite's one admitted exception
    to its standard-library limit, and it is bounded by how the binary comes to
    be present: it exists wherever the repository was obtained at all. That is
    not a general admission of binaries, and it does not touch the prohibition
    on running a separately installed one.
    """
    base = ROOT if root is None else Path(root)
    try:
        listed = subprocess.run(
            ["git", "-C", str(base), "ls-files", "-z"],
            capture_output=True,
            timeout=120,
        )
    except FileNotFoundError:
        raise TrackedFilesUnavailable(
            "the version-control binary is not available, so the repository's tracked "
            "files could not be enumerated. Refusing to skip: a credential scan that "
            "does not run reports success for a property nothing examined"
        ) from None
    except subprocess.SubprocessError as error:
        raise TrackedFilesUnavailable(
            f"the tracked files could not be enumerated: {error}"
        ) from None
    if listed.returncode != 0:
        detail = listed.stderr.decode("utf-8", errors="replace").strip()
        raise TrackedFilesUnavailable(
            f"`git ls-files` exited {listed.returncode} in {base}, so the tracked "
            f"files could not be enumerated: {detail!r}. Refusing to skip"
        )
    names = [name for name in listed.stdout.decode("utf-8", errors="replace").split("\0") if name]
    files: dict[str, bytes] = {}
    missing: list[str] = []
    for name in names:
        path = base / name
        try:
            files[name] = path.read_bytes()
        except (FileNotFoundError, NotADirectoryError):
            missing.append(name)
        except OSError as error:
            raise TrackedFilesUnavailable(
                f"the tracked file {name} could not be read: {error}"
            ) from None
    if missing:
        raise TrackedFilesUnavailable(
            "these paths are tracked but absent from the working tree, so the scans "
            "would establish a property over files they never read: "
            f"{', '.join(sorted(missing))}. A sparse or interrupted checkout is a "
            "state to hear about rather than to scan around"
        )
    return files


# Assembled rather than spelled out, for the same reason the private-key
# pattern below is: this module is itself a tracked file, so a pattern written
# whole would make every scan report its own source as a committed secret.
_TOKEN_PREFIX = "gh"
_PAT_PREFIX = "g"
_PAT_INFIX = "ithub_pat_"
TOKEN_MARKER = re.compile(
    _TOKEN_PREFIX + r"[pousr]_[A-Za-z0-9]{20,}|"
    + _PAT_PREFIX + _PAT_INFIX + r"[A-Za-z0-9_]{20,}"
)

_KEY_OPENING = "-----BEGIN"
_KEY_CLOSING = "PRIVATE KEY-----"
PRIVATE_KEY_MARKER = re.compile(
    re.escape(_KEY_OPENING) + r" (OPENSSH |RSA )?" + re.escape(_KEY_CLOSING)
)

GHCR_TOKEN_ASSIGNMENT = re.compile(r"^([ \t]*)ghcr_pull_token[ \t]*:(.*)$")


def files_carrying_a_token_marker(files: dict) -> list[str]:
    """Tracked files carrying a literal GitHub or GHCR token marker."""
    pattern = TOKEN_MARKER.pattern.encode("ascii")
    compiled = re.compile(pattern)
    return sorted(name for name, body in files.items() if compiled.search(body))


def files_carrying_a_private_key_marker(files: dict) -> list[str]:
    """Tracked files carrying an operator private-key delimiter.

    Widened from `ansible/inventory/` to the whole tracked tree when this scan
    moved here. Its old root was DERIVED -- the scan's own comment said no
    scenario named that path, but that it was where the key material lived --
    and a scan rooted at one directory while its siblings scan the repository
    claims a scope its root does not give it.
    """
    pattern = PRIVATE_KEY_MARKER.pattern.encode("ascii")
    compiled = re.compile(pattern)
    return sorted(name for name, body in files.items() if compiled.search(body))


def ghcr_token_literal_assignments(files: dict) -> list[str]:
    """`ghcr_pull_token` assignments whose value is a committed literal.

    A LINE-ORIENTED READING CANNOT DO THIS, and that is why the loop below
    absorbs continuations. Both of `deploy_user`'s credentialled scenario
    converge files assign the token as a YAML FOLDED scalar, so the assignment
    line is bare -- `ghcr_pull_token: >-` -- and the `lookup('env', ...)` that
    makes it acceptable sits on the following, more-indented lines. Reading the
    assignment together with its continuation is the whole point; a grep, or a
    rewrite against a YAML parser that discards line structure, passes over
    both files and reports a clean tree.

    Excluding those two files by path would have been simpler and is
    deliberately not done: it would blind the scan permanently in exactly the
    files most likely to acquire a pasted real token, since running the
    credentialled verification means having a live token at the keyboard while
    editing them. An assignment is acceptable where its value is an inline
    `!vault` value or a `lookup('env', ...)` expression; anything else is a
    literal and fails.
    """
    offenders: list[str] = []
    for name in sorted(files):
        if not name.endswith((".yml", ".yaml")):
            continue
        lines = files[name].decode("utf-8", errors="replace").splitlines()
        for index, line in enumerate(lines):
            match = GHCR_TOKEN_ASSIGNMENT.match(line)
            if not match:
                continue
            indent, value = len(match.group(1)), match.group(2)
            for continuation in lines[index + 1:]:
                if continuation.strip() and (
                    len(continuation) - len(continuation.lstrip())
                ) <= indent:
                    break
                value += " " + continuation.strip()
            if not value.strip():
                continue
            if "!vault" in value or "lookup('env'" in value or 'lookup("env"' in value:
                continue
            offenders.append(f"{name}:{index + 1}")
    return offenders


# ============================================================================
# The premise the Molecule trigger's exclusions rest on.
#
# `ansible-verify.yml` excludes four paths under `ansible/` from the Molecule
# suite's change detection, on the strength of a sweep establishing that no
# scenario reads them. THAT PREMISE IS WHAT ROTS. A filter assertion cannot
# catch it: the filter stays perfectly correct about a premise that has stopped
# being true, the suite skips on the pull requests that change the path, and
# the gate reports green. So the premise is asserted here, over scenario text.
#
# THE CRITERION IS A CONTROLLER-SIDE READ OF A REPOSITORY FILE, and both halves
# carry weight. A read of the MANAGED NODE cannot be affected by a filter over
# this repository -- around twenty `slurp` tasks read absolute paths inside the
# container -- and a delegated task deriving a value from an already-registered
# fact opens nothing. Drawn wider than this the check fires on the bulk of
# ordinary scenario text, and the only escapes are to permit those sites
# wholesale, which makes it meaningless, or to narrow it by a rule nobody wrote
# down, which is how the first version of this design went wrong.
#
# `slurp` has no `remote_src` option at all, so DELEGATION rather than any
# option on the module is what puts its read on the controller.
#
# See `narrow-the-molecule-trigger-to-what-it-reads`, design.md Decisions 1
# and 1a.
# ============================================================================

FILE_READING_LOOKUPS = frozenset(
    {"file", "template", "fileglob", "ini", "csvfile", "first_found", "unvault"}
)

# Lookups that reach no file. `env` is the one this repository uses; the rest
# are named so that a scenario adopting one is not reported as an unrecognised
# construction when it reads nothing.
NON_FILE_LOOKUPS = frozenset({"env", "pipe", "vars", "varnames", "password", "random_choice"})

# Modules that send a file TO the managed node, whose `src:` is therefore a
# controller path unless the module is told otherwise.
SENDING_MODULES = frozenset({"copy", "template", "script", "unarchive", "assemble"})

INCLUSION_KEYS = frozenset(
    {
        "vars_files",
        "include_vars",
        "import_playbook",
        "include_tasks",
        "import_tasks",
        "tasks_from",
        "vars_from",
    }
)

LOOKUP_CALL = re.compile(r"lookup\(\s*['\"]([A-Za-z0-9_.]+)['\"]\s*,(.*?)\)", re.DOTALL)
TASK_START = re.compile(r"^(\s*)-\s+name:\s")
MODULE_KEY = re.compile(r"^\s*(?:ansible\.builtin\.|ansible\.posix\.|community\.general\.)?([a-z_]+):")
# What makes an expression worth resolving. `MOLECULE_SCENARIO_DIRECTORY` and
# `MOLECULE_PROJECT_DIRECTORY` are Molecule's own, supplied at run time and
# pointing into this repository just as `playbook_dir` does.
PATH_BEARING = re.compile(
    r"(?:playbook_dir|MOLECULE_PROJECT_DIRECTORY|MOLECULE_SCENARIO_DIRECTORY|\.\./)"
)

# A quoted path built on a variable this check cannot evaluate: `{{ x }}/y.yml`.
# Such a read is not passed over -- it resolves to an `expr:` target and must be
# permitted explicitly, which is the conservative direction.
VARIABLE_PATH = re.compile(r"\{\{[^}]+\}\}/[\w./-]+")


def _normalise_expression(text: str) -> str:
    return " ".join(text.split()).strip().strip("\"'")


def _resolve_target(expression: str, scenario_dir: str) -> str:
    """Resolve a path expression to a repository-relative path where it can be.

    THE BASE DEPENDS ON THE VARIABLE. `playbook_dir` and Molecule's
    `MOLECULE_SCENARIO_DIRECTORY` both name the scenario directory;
    `MOLECULE_PROJECT_DIRECTORY` names the ROLE directory, two levels above it.
    Resolving everything against one base silently mislocates the second, which
    is how `ANSIBLE_ROLES_PATH` came to read as an absolute path on the managed
    node rather than as `ansible/roles/`.

    Where the expression carries a variable this check cannot evaluate, the
    normalised expression is returned under an `expr:` prefix. Such a read is
    not passed over: it must be permitted explicitly like any other.
    """
    raw = _normalise_expression(expression)
    role_dir = posixpath.normpath(posixpath.join(scenario_dir, "..", ".."))

    base = scenario_dir
    substituted = False
    if "MOLECULE_PROJECT_DIRECTORY" in raw:
        base = role_dir
        substituted = True
    elif "playbook_dir" in raw or "MOLECULE_SCENARIO_DIRECTORY" in raw:
        substituted = True

    stripped = re.sub(r"\{\{\s*playbook_dir\s*\}\}", "", raw)
    stripped = re.sub(r"\bplaybook_dir\b", "", stripped)
    stripped = re.sub(r"\$\{MOLECULE_PROJECT_DIRECTORY\}", "", stripped)
    stripped = re.sub(
        r"\{\{\s*lookup\(\s*['\"]env['\"]\s*,\s*['\"]MOLECULE_(?:SCENARIO_DIRECTORY|PROJECT_DIRECTORY)['\"]\s*\)\s*\}\}",
        "",
        stripped,
    )
    stripped = stripped.replace("+", " ").replace("'", " ").replace('"', " ")
    stripped = " ".join(stripped.split())

    if "{{" in stripped or "${" in stripped:
        return f"expr:{raw}"
    candidate = stripped.replace(" ", "")
    if not candidate:
        return f"expr:{raw}"
    if candidate.startswith("/"):
        # A leading slash AFTER a variable was removed is the join between the
        # variable and the rest of the path, not an absolute path on the host.
        if not substituted:
            return f"node:{candidate}"
        candidate = candidate.lstrip("/")
        if not candidate:
            return base
    joined = posixpath.normpath(posixpath.join(base, candidate))
    if joined.startswith(".."):
        return f"expr:{raw}"
    return joined


def _task_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    current: list[str] = []
    indent = None
    for line in lines:
        start = TASK_START.match(line)
        if start:
            if current:
                blocks.append("\n".join(current))
            current = [line]
            indent = len(start.group(1))
            continue
        if current:
            bare = line.strip()
            if bare and not line.startswith(" " * (indent + 1)) and not line.startswith("#"):
                blocks.append("\n".join(current))
                current = []
                indent = None
                continue
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _reads_in_play(text: str, scenario_dir: str) -> list[tuple[str, str, str]]:
    """(construction, target, detail) for every controller read in a play file."""
    found: list[tuple[str, str, str]] = []

    for name, argument in LOOKUP_CALL.findall(text):
        short = name.rsplit(".", 1)[-1]
        if short in NON_FILE_LOOKUPS:
            continue
        if short in FILE_READING_LOOKUPS:
            found.append((f"lookup({short})", _resolve_target(argument, scenario_dir), name))
            continue
        if PATH_BEARING.search(argument):
            found.append(
                ("unrecognised-lookup", _resolve_target(argument, scenario_dir), name)
            )

    # An inclusion key carries its path either on its own line or, for the
    # list-valued ones, on the items beneath it. `vars_files:` is almost always
    # the second shape, so reading only the key's own line passes over exactly
    # the route most likely to reach an excluded path.
    lines = text.splitlines()
    for index, line in enumerate(lines):
        bare = line.strip()
        if bare.startswith("#") or ":" not in bare:
            continue
        key, _, value = bare.partition(":")
        key = key.lstrip("- ").strip()
        if key not in INCLUSION_KEYS:
            continue
        if value.strip():
            found.append((key, _resolve_target(value, scenario_dir), value.strip()))
            continue
        indent = len(line) - len(line.lstrip())
        for item in lines[index + 1:]:
            if not item.strip():
                continue
            if (len(item) - len(item.lstrip())) <= indent and not item.lstrip().startswith("-"):
                break
            entry = item.strip()
            if not entry.startswith("-"):
                break
            entry = entry.lstrip("- ").strip()
            if entry:
                found.append((key, _resolve_target(entry, scenario_dir), entry))

    for block in _task_blocks(text):
        delegated = re.search(r"^\s*delegate_to:\s*localhost\s*$", block, re.MULTILINE)
        remote_src = re.search(r"^\s*remote_src:\s*(true|yes)\s*$", block, re.MULTILINE | re.I)
        modules = [
            match.group(1)
            for line in block.splitlines()[1:]
            for match in [MODULE_KEY.match(line)]
            if match
        ]
        sending = [module for module in modules if module in SENDING_MODULES]
        source = re.search(r"^\s*src:\s*(.+?)\s*$", block, re.MULTILINE)
        if sending and source and not remote_src:
            found.append(("src", _resolve_target(source.group(1), scenario_dir), sending[0]))
            continue
        if not delegated:
            continue
        source_target = None
        if source:
            source_target = _resolve_target(source.group(1), scenario_dir)
            found.append(("delegated-src", source_target, "delegated"))
        for candidate in re.findall(r"((?:\{\{\s*[\w.]+\s*\}\}|[\w./-])+/\.\.[\w./-]*)", block):
            if not PATH_BEARING.search(candidate):
                continue
            resolved = _resolve_target(candidate, scenario_dir)
            # One read, not two: where the block already declared a `src:`, the
            # bare path found in its text is the same read seen again.
            if resolved == source_target:
                continue
            found.append(("delegated-path", resolved, "delegated"))
        for candidate in VARIABLE_PATH.findall(block):
            if "playbook_dir" in candidate or ".." in candidate:
                continue
            found.append(
                ("delegated-path", _resolve_target(candidate, scenario_dir), "delegated")
            )
    return found


def _reads_in_scenario_definition(text: str, scenario_dir: str) -> list[tuple[str, str, str]]:
    """Paths a scenario declares in its own configuration file.

    Two spellings are live here and neither is a task or a play: the provisioner
    environment, and the options passed to dependency resolution. The second was
    found by the author deriving this change's tests rather than by either
    sweep -- every authored scenario carries `requirements-file`, and two sweeps
    had read these files for `ANSIBLE_ROLES_PATH` without seeing it.
    """
    found: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        bare = line.strip()
        if bare.startswith("#") or ":" not in bare:
            continue
        key, _, value = bare.partition(":")
        key = key.strip()
        value = value.strip()
        if not value or not PATH_BEARING.search(value):
            continue
        if key == "requirements-file":
            found.append((key, _resolve_target(value, scenario_dir), value))
        elif key.isupper() or key.startswith("ANSIBLE_") or key.startswith("MOLECULE_"):
            found.append(("provisioner-env", _resolve_target(value, scenario_dir), key))
    return found


# The permitted reads, keyed by the file that holds each, the construction that
# performs it and the target it resolves to -- NEVER by a line offset. The
# commit that relocated three scans out of two of these files shifted every
# offset below it, so an offset-keyed set would have been wrong on the commit
# that introduced it.
#
# The value is the number of occurrences permitted WITHIN THAT FILE. Identity
# alone does not separate one read from two, and the natural place to add a
# second read of `ansible/requirements.yml` is the file already holding the
# first. Per file rather than in total, because the two declaration entries are
# one declaration each across seventeen scenarios.
PERMITTED_CONTROLLER_READS: dict[tuple[str, str, str], int] = {
    # Role-local private-key scans. Their own role directory changing selects
    # the suite anyway, so they stay where they are.
    ("ansible/roles/deploy_user/molecule/default/verify.yml", "delegated-path", "ansible/roles/deploy_user"): 1,
    ("ansible/roles/ops_user/molecule/default/verify.yml", "delegated-path", "ansible/roles/ops_user"): 1,
    # The role's own README, asserted to record what the role grants.
    ("ansible/roles/ops_user/molecule/default/verify.yml", "delegated-src", "ansible/roles/ops_user/README.md"): 1,
    # A nested `ansible-playbook` over this scenario's own directory.
    ("ansible/roles/ops_user/molecule/revocation-steady-state/verify.yml", "delegated-path", "expr:{{ ops_user_nested_scenario_dir }}/converge.yml"): 1,
    # The role's own shipped defaults, read to assert them.
    ("ansible/roles/swap/molecule/default/verify.yml", "lookup(file)", "ansible/roles/swap/defaults/main.yml"): 1,
    # The Galaxy manifest, read to assert the external role's pin. Escapes the
    # role directory; its target is a trigger.
    ("ansible/roles/docker/molecule/default/verify.yml", "lookup(file)", "ansible/requirements.yml"): 1,
    # One scenario built on its sibling's plays, three files deep.
    ("ansible/roles/platform_data_volume/molecule/multiple-devices-reverse-order/converge.yml", "import_playbook", "ansible/roles/platform_data_volume/molecule/multiple-devices-discoverable/converge.yml"): 1,
    ("ansible/roles/platform_data_volume/molecule/multiple-devices-reverse-order/prepare.yml", "import_playbook", "ansible/roles/platform_data_volume/molecule/multiple-devices-discoverable/prepare.yml"): 1,
    ("ansible/roles/platform_data_volume/molecule/multiple-devices-reverse-order/verify.yml", "import_playbook", "ansible/roles/platform_data_volume/molecule/multiple-devices-discoverable/verify.yml"): 1,
}

# The two declarations every authored scenario carries. Keyed by construction
# and target only, with a count of one PER `molecule.yml`, because a total
# would be seventeen and would go red whenever a scenario is added or removed.
PERMITTED_SCENARIO_DECLARATIONS: dict[tuple[str, str], int] = {
    ("provisioner-env", "ansible/roles"): 1,
    ("requirements-file", "ansible/requirements.yml"): 1,
}


def unpermitted_controller_reads(root: Path | None = None) -> list[str]:
    """Controller-side reads of repository files that no permitted entry covers.

    Refuses rather than passes over: a construction this check has no rule for,
    carrying a path that resolves into the repository, is reported. A route list
    goes stale exactly as a path list does, and the polarity that answers one
    answers the other -- an unrecognised construction ignored is a silent gap,
    where one refused costs a visible edit to permit.
    """
    base = ROOT if root is None else Path(root)
    offenders: list[str] = []
    for definition in authored_scenario_files(base):
        scenario_root = definition.parent
        scenario_dir = scenario_root.relative_to(base).as_posix()
        for path in sorted(scenario_root.rglob("*.yml")):
            relative = path.relative_to(base).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.name == "molecule.yml":
                reads = _reads_in_scenario_definition(text, scenario_dir)
            else:
                reads = _reads_in_play(text, scenario_dir)
            seen: dict[tuple[str, str, str], int] = {}
            for construction, target, detail in reads:
                if target.startswith("node:"):
                    continue
                key = (relative, construction, target)
                seen[key] = seen.get(key, 0) + 1
                allowed = PERMITTED_CONTROLLER_READS.get(key)
                if allowed is None:
                    allowed = PERMITTED_SCENARIO_DECLARATIONS.get((construction, target))
                if allowed is None:
                    offenders.append(
                        f"{relative}: {construction} -> {target} ({detail}) is a "
                        f"controller-side read of a repository file that no permitted "
                        f"entry covers"
                    )
                elif seen[key] > allowed:
                    offenders.append(
                        f"{relative}: {construction} -> {target} occurs {seen[key]} "
                        f"times where {allowed} is permitted; a second read of an "
                        f"already-permitted target is enumerated separately or not at all"
                    )
    return sorted(set(offenders))


class TestNoCredentialIsCommittedAnywhereInTheRepository(unittest.TestCase):
    """SPECIFIED -- The Continuous-Integration Configuration Is Itself Verified:
    "A scan at repository scope ... SHALL live here rather than inside a check
    that runs only when some particular directory changes, because unconditional
    execution is exactly what makes such a claim true."

    These three arrived from Molecule verify plays, where they ran only on pull
    requests that happened to change `ansible/`. `gitleaks` already covers the
    diff of every pull request; what these add is a structural rule it has no
    equivalent of, and a read of the tracked tree rather than of the diff.
    """

    def test_no_tracked_file_carries_a_token_marker(self) -> None:
        offenders = files_carrying_a_token_marker(tracked_files())
        self.assertEqual(
            [],
            offenders,
            "a GitHub/GHCR token-shaped marker is committed in: "
            f"{offenders}. The GHCR pull token SHALL be stored outside version "
            "control and SHALL NOT appear in plaintext anywhere in the repository",
        )

    def test_no_tracked_file_carries_a_private_key_marker(self) -> None:
        offenders = files_carrying_a_private_key_marker(tracked_files())
        self.assertEqual(
            [],
            offenders,
            "a private-key marker is committed in: "
            f"{offenders}. Only an operator keypair's public half SHALL be "
            "committed; the private half SHALL remain on the operator's own machine",
        )

    def test_no_ghcr_pull_token_assignment_carries_a_committed_literal(self) -> None:
        offenders = ghcr_token_literal_assignments(tracked_files())
        self.assertEqual(
            [],
            offenders,
            "ghcr_pull_token is assigned a committed literal in: "
            f"{offenders}. It SHALL be stored outside version control (Ansible "
            "Vault), not merely referenced without a committed default",
        )


class TestNoScenarioReadsAPathTheSuiteIsNoLongerTriggeredBy(unittest.TestCase):
    """SPECIFIED -- "The premise the exclusions rest on SHALL itself be checked."

    The exclusions in `ansible-verify.yml` rest on a sweep of scenario text. A
    scenario acquiring a read of an excluded path makes that sweep false, the
    filter goes on excluding a path that is now read, and the suite skips on the
    pull requests that change it -- with the gate reporting green. Nothing else
    in this repository can observe that.
    """

    def test_every_controller_side_read_is_one_the_exclusions_were_established_against(
        self,
    ) -> None:
        offenders = unpermitted_controller_reads()
        self.assertEqual(
            [],
            offenders,
            "these controller-side reads of repository files are not in the "
            "permitted set the Molecule trigger's exclusions were established "
            f"against:\n  " + "\n  ".join(offenders) + "\n"
            "Either the read reaches a path the filter excludes -- in which case "
            "the exclusion is now wrong and `ansible-verify.yml` must change -- or "
            "it is a new read of a path that remains a trigger, in which case add "
            "it to PERMITTED_CONTROLLER_READS with the reason. Do not widen the "
            "check's rules to make this pass: an unstated narrowing is the defect "
            "this check exists to prevent",
        )

if __name__ == "__main__":
    unittest.main()
