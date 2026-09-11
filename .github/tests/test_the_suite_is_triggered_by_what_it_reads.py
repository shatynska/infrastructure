"""Static-assertion tests for narrowing the Molecule suite's trigger to the
Ansible content its scenarios actually read, and for the three repository-scope
scans that move out of the suite to make that narrowing safe.

Derived from the delta specifications of the OpenSpec change
`narrow-the-molecule-trigger-to-what-it-reads`, before any implementation of
that change existed -- from those deltas at commit `5b190b5`, the commit holding
the approved plan. The path those deltas sit at is not written here: a change's
artifacts move when it is archived, and this repository's citation convention is
to name the change and the artifact in prose instead.

The deltas modify two requirements of `iac-cicd-pipeline` -- *Ansible
Configuration Is Verified in Continuous Integration and Gates the Merge* and
*The Continuous-Integration Configuration Is Itself Verified*. Each class below
names the requirement and the scenario it traces to, and every assertion is
annotated SPECIFIED (it traces to SHALL text or to a scenario in a delta spec)
or DERIVED (it traces to that change's `design.md` or `tasks.md` rather than to
a scenario). See that change's `test-plan.md` for the scenario-to-test mapping,
the baseline, the scenarios deliberately left uncovered, the obsolete-test
candidates, and the interface assumptions this file took.

Why this is a ninth file in the suite rather than a section of an existing one
-----------------------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. The change's own implementation lands in
`test_ci_configuration.py` -- the relocated scans, the tracked-file helper and
the premise check over scenario text all live there, by that change's tasks.md
1.1 -- and two assertions already in that module rest on propositions these
deltas retire. Re-pointing those is the implementing author's task (tasks.md 2.3
and 2.4), recorded in `test-plan.md`'s obsolete list rather than performed here.
Nothing in this file edits, deletes or disables an existing test.

Where this file needs a helper a module beside it already has, it imports it
rather than restating it, which is the idiom the eight modules already in this
directory use. One locator is deliberately duplicated rather than imported --
see `GateBodyMixin` below, which says why.

THIS FILE SPAWNS `git`, and that is a deliberate, reported consequence rather
than an oversight. `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource`
in `test_ci_configuration.py` admits only `bash` and `sh`, so this file turns
that assertion red until `git` joins its `SPAWNABLE` set. The implementation
must widen it regardless of this file: tasks.md 1.1 puts a `git ls-files`
subprocess in `test_ci_configuration.py` itself, and the delta admits the
enumeration explicitly as an exception to the standard-library limit, bounded to
"the version-control binary that placed the files there". `git` is neither a
network call, a credential, a container runtime nor a Terraform binary, which is
what that constraint names.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_the_suite_is_triggered_by_what_it_reads.TestTheSuiteFilterNamesWhatTheSuiteReads \\
        .test_the_filter_declares_the_directory_and_exactly_the_established_negations

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling import below resolve.

What no assertion here establishes
----------------------------------
Not what `dorny/paths-filter` DOES with the patterns this file reads. Picomatch
is not reproducible here without a dependency this suite is forbidden from
taking, and the action cannot be run without a network call it is forbidden from
making. The matcher below is a deliberate approximation, written for this
suite's own use: where it and the action disagree, the action wins. The
behaviour is established by observation on a real pull request -- that change's
tasks.md section 6 records which direction is observable on its own pull request
and which is its ship-confirm gate.

Nor that a credential scan finds everything a credential scan could find. These
assertions establish that the relocated scans match what they were written to
match over a supplied file list, that the file list is the repository's tracked
files, and that an unavailable enumeration fails rather than skips. Whether the
patterns themselves are the right patterns is unchanged by this change and is
not re-litigated here.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from test_ci_configuration import (
    AGGREGATING_CONTEXT,
    ANSIBLE_VERIFY,
    PR_VALIDATION,
    ROOT,
    MoleculeWorkflowShapeMixin,
    compact,
    gh_glob_matches,
    load_yaml,
    read_text,
    require_external_tools,
    steps,
)

# --------------------------------------------------------------------------
# The interface this file assumes the implementation will expose.
#
# These tests are written before the implementation, so the names below are
# ASSUMPTIONS this file takes rather than facts it reads, and `test-plan.md`
# records them as such so the implementing author can implement TO them rather
# than around them. Each is fetched lazily, by `suite_symbol()` below, so that
# the assertions about committed workflow files -- which need none of them --
# fail on their own grounds rather than on an import error at module load.
#
#   tracked_files(root: Path | None = None) -> dict[str, bytes]
#       Every path `git ls-files` reports for the repository at `root`, as
#       repository-relative POSIX strings, mapped to that file's BYTES.
#       Raises `TrackedFilesUnavailable` where the enumeration cannot be made,
#       and where a listed path is absent from the working tree.
#
#   TrackedFilesUnavailable(AssertionError)
#       The refusal above. An `AssertionError` subclass for the reason
#       `ManifestNotUsable` already is in the module beside this one: an
#       unhandled one FAILS the calling test rather than erroring it.
#
#   files_carrying_a_token_marker(files) -> list[str]
#   files_carrying_a_private_key_marker(files) -> list[str]
#       Sorted paths within the supplied mapping whose bytes carry the marker.
#
#   ghcr_token_literal_assignments(files) -> list[str]
#       Entries of the form "<path>:<line>" for every `ghcr_pull_token`
#       assignment in the supplied mapping whose value -- read together with
#       its folded/block continuation -- is a committed literal.
#
#   unpermitted_controller_reads(root: Path | None = None) -> list[str]
#       One entry per controller-side read of a repository file, in a scenario
#       this repository authors under `root`, that the permitted enumeration
#       does not account for -- including an unrecognised construction carrying
#       a repository-resolvable path. Each entry names the scenario file and
#       the read.
#
# Every one of these takes its file set or its root as an argument, which is
# what makes the negative cases below exercisable against a fixture instead of
# by damaging the real tree. That shape is required by that change's tasks.md
# 1.5 and 3.4, not invented here.
# --------------------------------------------------------------------------

SUITE_MODULE = "test_ci_configuration"


def suite_symbol(name: str):
    """Fetch a symbol the implementation must add to `test_ci_configuration`.

    Fails -- rather than errors -- naming the absent target, so that a run
    before the implementation exists reports "the target does not exist yet"
    in the words of the thing that is missing, and does not mask the
    assertions in this file that need nothing new.
    """
    module = __import__(SUITE_MODULE)
    try:
        return getattr(module, name)
    except AttributeError:
        raise AssertionError(
            f"`{SUITE_MODULE}` exposes no `{name}`. The change "
            "`narrow-the-molecule-trigger-to-what-it-reads` relocates three "
            "repository-scope scans and the premise check into that module; until "
            "it does, this assertion has nothing to exercise. This is the "
            "absent-target failure, not a wrong value: nothing here has been "
            "established about the scan's behaviour."
        ) from None


# --------------------------------------------------------------------------
# Change-detection patterns, and a negation-aware reading of them.
# --------------------------------------------------------------------------


def declared_filter_patterns(path: Path, name: str = "ansible") -> list[list[str]]:
    """Every `dorny/paths-filter` declaration of the named filter in a workflow,
    one pattern list per declaring step.

    A list of lists rather than one flattened list, deliberately: a workflow
    declaring the filter twice is a different fact from one declaring it once,
    and flattening would hide it behind a set of patterns that still looked
    right.
    """
    workflow = load_yaml(path)
    found: list[list[str]] = []
    for _, _, step in steps(workflow):
        if "paths-filter" not in str(step.get("uses", "")):
            continue
        declared = (step.get("with") or {}).get("filters")
        parsed = yaml.safe_load(declared) if isinstance(declared, str) else declared
        if not isinstance(parsed, dict) or name not in parsed:
            continue
        entry = parsed[name]
        found.append([str(pattern) for pattern in (entry if isinstance(entry, list) else [entry])])
    return found


def selects(patterns, path: str) -> bool:
    """Whether a filter's declared patterns select a path: matched by some
    positive AND by no negation, which is `predicate-quantifier:
    some-with-excludes`.

    THE QUANTIFIER IS WHY THIS IS THE RULE. Under the action's default, `some`,
    patterns are compiled independently and OR-ed, and picomatch inverts a
    matcher built from a `!`-prefixed pattern -- so a negation matches every
    path it does not exclude and the filter matches nearly everything. A
    matcher modelling "last pattern wins" would agree with this one on an
    ordered list and certify a selection the action produces only when
    `some-with-excludes` is declared. Order is irrelevant here and exclusion is
    final.

    An approximation of picomatch written for this suite's own use, not
    authority on what `dorny/paths-filter` does; the module docstring says why
    the real behaviour is established by observation instead. It is worth having
    anyway, and this change is the reason: with the negations invisible to it, a
    matcher can assert that a filter selects a path it has just been edited to
    exclude, and stay green while asserting the opposite of the requirement.
    """
    selected = False
    for pattern in patterns:
        text = str(pattern).strip()
        if text.startswith("!"):
            if gh_glob_matches(text[1:].strip(), path):
                return False
        elif gh_glob_matches(text, path):
            selected = True
    return selected


# The exclusions design.md Decision 1a establishes, in the spelling tasks.md 2.1
# requires. Asserted as an exact set rather than as a subset: a negation this
# change did not establish is as much a defect as a missing one, because the
# whole safety argument is that each exclusion was justified by reading scenario
# text.
ESTABLISHED_NEGATIONS = frozenset(
    {
        "ansible/inventory/**",
        "ansible/playbooks/**",
        "ansible/requirements.txt",
        "ansible/.envrc*",
    }
)

CONFIGURATION_DIRECTORY_POSITIVE = "ansible/**"

# Representative of each excluded subtree, not of its current contents. Both of
# the first two are the paths tasks.md 2.3 moves out of the existing selection
# test's tuple and tasks.md 2.4 asserts the LINT tier still selects; the pair
# read together is this change's whole safety argument.
EXCLUDED_FROM_THE_SUITE = (
    "ansible/inventory/prod.hcloud.yml",
    "ansible/inventory/group_vars/prod.yml",
    "ansible/playbooks/host-baseline.yml",
    "ansible/requirements.txt",
    "ansible/.envrc.example",
)

# What the suite does read, including the two pinned manifests the delta names
# explicitly ("Neither manifest SHALL be excluded from change detection"), the
# configuration file design.md Decision 1a records as deliberately NOT excluded,
# and a path under `ansible/` that no exclusion names -- the last standing for
# the scenario about a file nobody considered.
SELECTED_BY_THE_SUITE = (
    "ansible/roles/docker/molecule/default/verify.yml",
    "ansible/roles/some_role/tasks/main.yml",
    "ansible/requirements.yml",
    "ansible/requirements-test.txt",
    "ansible/ansible.cfg",
    "ansible/scripts/run-molecule",
    "ansible/a-directory-nobody-has-considered/new-file.yml",
)


class TestTheSuiteFilterNamesWhatTheSuiteReads(unittest.TestCase):
    """MODIFIED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge.

    The suite tier's change detection, in `ansible-verify.yml`. Its companion
    below reads the lint tier's, in `pr-validation.yml`; neither assertion is
    worth much without the other, because what makes an exclusion safe is that
    the other tier still covers the excluded path.
    """

    def _patterns(self) -> list[str]:
        declared = declared_filter_patterns(ANSIBLE_VERIFY)
        self.assertEqual(
            1,
            len(declared),
            "expected exactly one change-filter step in ansible-verify.yml declaring "
            f"an `ansible:` filter, but found {len(declared)}: {declared}. Two "
            "declarations are two answers to which paths run the suite, and nothing "
            "says which one the workflow reads.",
        )
        return declared[0]

    def test_the_filter_declares_the_directory_and_exactly_the_established_negations(
        self,
    ) -> None:
        """SPECIFIED -- "Change detection SHALL match the whole of `ansible/`
        and then subtract the paths established, by reading the scenarios
        themselves, to be unread by any of them."

        Three propositions, and the third is the one a looser assertion would
        drop. That the positive is declared; that it comes FIRST, because
        `dorny/paths-filter` requires a file to be matched by a positive pattern
        before a negation can exclude it, so a negation ahead of it excludes
        nothing; and that the negations are EXACTLY the four this change
        established. A fifth negation is not a smaller version of this defect:
        every exclusion here rests on a sweep of scenario text, and one added
        without that sweep is an exclusion nobody established.

        This asserts the DECLARATION and not the behaviour -- reproducing
        picomatch would need a dependency this suite is forbidden from taking,
        and running the action would need a network call. The behaviour is
        established by observation on a real pull request.
        """
        patterns = self._patterns()
        self.assertTrue(patterns, "the `ansible:` filter declares no patterns at all")
        self.assertEqual(
            CONFIGURATION_DIRECTORY_POSITIVE,
            patterns[0].strip(),
            f"the `ansible:` filter's first pattern is {patterns[0]!r}, not "
            f"{CONFIGURATION_DIRECTORY_POSITIVE!r}. dorny/paths-filter excludes a "
            "file with `!` only once a positive pattern has matched it, so the "
            "polarity this change chose -- match the directory, then subtract -- "
            f"needs {CONFIGURATION_DIRECTORY_POSITIVE!r} at the head; the patterns "
            f"declared are {patterns}",
        )
        negations = {
            pattern.strip()[1:].strip() for pattern in patterns if pattern.strip().startswith("!")
        }
        self.assertEqual(
            set(ESTABLISHED_NEGATIONS),
            negations,
            "the `ansible:` filter's negations are "
            f"{sorted(negations)}, not {sorted(ESTABLISHED_NEGATIONS)}. A MISSING "
            "negation runs seven containerised jobs on a pull request no scenario "
            "reads a line of; an EXTRA one excludes a path from the suite on nobody's "
            "authority -- design.md Decision 1's sweep is what justifies each of the "
            "four, and a fifth has no sweep behind it",
        )

    def test_the_filter_does_not_select_the_paths_no_scenario_reads(self) -> None:
        """SPECIFIED -- scenario "A pull request changing only Ansible content
        no scenario reads starts no container": the Molecule matrix is skipped
        rather than executed.

        The matcher here is negation-aware on purpose. A matcher that asks only
        whether ANY declared pattern matches reports every one of these paths as
        selected, because the positive `ansible/**` still matches each of them
        and the negations are invisible to it -- which is exactly how an
        existing assertion in the module beside this one survives this change
        stating the opposite of it and never goes red.
        """
        patterns = self._patterns()
        still_selected = [path for path in EXCLUDED_FROM_THE_SUITE if selects(patterns, path)]
        self.assertEqual(
            [],
            still_selected,
            f"the `ansible:` filter's patterns {patterns} still select "
            f"{still_selected}. Each is a path design.md Decision 1's sweep "
            "established no scenario reads, and each one selected is seven "
            "containerised jobs started on a pull request the suite has nothing to "
            "say about -- which is the cost this change exists to stop paying",
        )

    def test_the_filter_still_selects_what_the_scenarios_do_read(self) -> None:
        """SPECIFIED -- scenario "An unconsidered new path under the
        configuration directory runs the suite", and scenario "A change to a
        pinned manifest runs the suite" ("Neither manifest SHALL be excluded
        from change detection: a change to either changes what every scenario
        runs under").

        The converse the assertion above needs. A filter narrowed to nothing
        satisfies every exclusion in this file while withdrawing the suite from
        the whole repository, and the failure would be silent: the matrix skips,
        the gate reaches its correct-skip branch, and the required check
        concludes success.

        `ansible/a-directory-nobody-has-considered/new-file.yml` is the
        scenario's own case rather than a path that exists. Under an INCLUSION
        list it would be silently unselected; under the exclusion list this
        change chose it runs the suite, wastefully and visibly. Wasteful and
        visible is the recoverable direction.
        """
        patterns = self._patterns()
        unselected = [path for path in SELECTED_BY_THE_SUITE if not selects(patterns, path)]
        self.assertEqual(
            [],
            unselected,
            f"the `ansible:` filter's patterns {patterns} do not select "
            f"{unselected}. A pull request changing one of them would be reported as "
            "touching nothing the suite reads, the matrix would skip, and the "
            "required check would conclude success having verified nothing",
        )


class TestTheLintTierStaysUnexcluded(unittest.TestCase):
    """MODIFIED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge -- "This tier SHALL be triggered by any
    change under `ansible/`, without exclusion: it is the tier that covers the
    paths the suite tier does not read."

    Read together with the class above, this is the whole safety argument of
    the change, stated as two assertions that must DISAGREE about the same two
    paths. The delta says in as many words that an assertion establishing only
    that a filter for this directory exists does not establish this -- which is
    what `TestAnsibleBlockingTier
    .test_an_ansible_path_filter_selects_changes_under_ansible` in the module
    beside this one establishes, and all it establishes.
    """

    def _patterns(self) -> list[str]:
        declared = declared_filter_patterns(PR_VALIDATION)
        self.assertEqual(
            1,
            len(declared),
            "expected exactly one change-filter step in pr-validation.yml declaring "
            f"an `ansible:` filter, but found {len(declared)}: {declared}",
        )
        return declared[0]

    def test_the_lint_filter_declares_the_directory_with_no_negation(self) -> None:
        """SPECIFIED -- scenario "Narrowing the lint tier's trigger fails the
        pipeline's own checks".

        The two filters ceasing to be identical is this change's point rather
        than a drift, and this is the side that must not move. A negation here
        is not a smaller version of the same edit: it withdraws the compensating
        coverage for a path the suite tier has already stopped selecting, and
        nothing else in this repository would report it.
        """
        patterns = self._patterns()
        self.assertIn(
            CONFIGURATION_DIRECTORY_POSITIVE,
            [pattern.strip() for pattern in patterns],
            f"pr-validation.yml's `ansible:` filter declares {patterns}, which does "
            f"not carry {CONFIGURATION_DIRECTORY_POSITIVE!r}. The lint tier is what "
            "covers every path the suite tier excludes",
        )
        negations = [pattern for pattern in patterns if pattern.strip().startswith("!")]
        self.assertEqual(
            [],
            negations,
            f"pr-validation.yml's `ansible:` filter declares the negations {negations}. "
            "This tier is triggered by any change under `ansible/` WITHOUT exclusion; "
            "it needs no container runtime and no credential, so there is nothing to "
            "buy by narrowing it, and what a narrowing costs is the only coverage the "
            "excluded paths have left",
        )

    def test_the_lint_filter_selects_the_paths_the_suite_no_longer_does(self) -> None:
        """SPECIFIED -- scenario "A pull request changing only Ansible content
        no scenario reads starts no container": "the lint tier SHALL still run
        over those paths".

        Asserted behaviourally, over the same paths the class above asserts the
        suite tier does NOT select, so the two cannot drift into agreeing.
        """
        patterns = self._patterns()
        unselected = [path for path in EXCLUDED_FROM_THE_SUITE if not selects(patterns, path)]
        self.assertEqual(
            [],
            unselected,
            f"pr-validation.yml's `ansible:` filter {patterns} does not select "
            f"{unselected} -- paths the suite tier no longer selects either. A pull "
            "request changing one of them would then be covered by neither tier, "
            "which is the withdrawal of coverage this change's exclusions are only "
            "safe without",
        )


class GateBodyMixin(MoleculeWorkflowShapeMixin):
    """Locates and runs `ansible-verify.yml`'s aggregating gate.

    A deliberate duplicate of the private locator inside
    `TestTheAggregatingGateDiscriminates`, and not an import of it: importing a
    `TestCase` subclass into this module would make unittest's loader collect
    and RE-RUN every test that class declares, under this module's name. The
    assertions below are new ones about the gate's MESSAGE on two rows; the
    rows' conclusions are already asserted there and are not restated here.
    """

    def _gate_step(self):
        workflow = self._workflow()
        discovery_key, _ = self._discovery_job(workflow)
        matrix_key, _ = self._matrix_job(workflow)
        _, aggregating = self._job_named(workflow, AGGREGATING_CONTEXT)

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
            "carrying the discovery result, the matrix result and the change-detection "
            f"output through its `env:` block, but found {len(candidates)}",
        )
        _, step, inputs = candidates[0]
        return step, inputs

    def _run_gate(self, discovery: str, changed: str, matrix: str):
        step, inputs = self._gate_step()
        script = str(step["run"])
        require_external_tools(self, ("bash",), "execute ansible-verify.yml's gate")
        scratch = Path(tempfile.mkdtemp(prefix="suite-trigger-gate-"))
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
            env[inputs["discovery"]] = discovery
            env[inputs["changed"]] = changed
            env[inputs["matrix"]] = matrix
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


class TestACorrectSkipSaysWhatWasActuallyUnchanged(GateBodyMixin, unittest.TestCase):
    """MODIFIED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge.

    Runs the gate rather than reading it, for the reason the class beside it
    already gives: grepping would establish that a message exists, only running
    it establishes which branch says it.
    """

    def test_the_correct_skip_says_nothing_the_suite_reads_changed(self) -> None:
        """SPECIFIED -- scenario "A correct skip says what was actually
        unchanged": "its message SHALL state that nothing the suite reads
        changed, rather than that nothing under the configuration directory
        changed".

        Both halves are asserted, and the negative half is the load-bearing one.
        A message that says the suite reads nothing new AND still says nothing
        under the configuration directory changed is the false sentence this
        scenario exists to remove, so asserting only the presence of the new
        wording would pass on a message that kept both.

        Anchored to the conclusion first, as the sibling message assertion in
        the module beside this one is: without that, this test reads a message
        and never checks that the gate concluded success on the row it is
        describing.
        """
        result = self._run_gate(discovery="success", changed="false", matrix="skipped")
        combined = (result.stdout + result.stderr).strip()
        self.assertEqual(
            0,
            result.returncode,
            "the gate refused the row this scenario is about -- discovery succeeded, "
            "change detection said the suite was not owed, the matrix skipped -- so "
            f"this message assertion would be describing a refusal: {combined!r}",
        )
        lowered = combined.lower()
        self.assertNotIn(
            "configuration directory",
            lowered,
            "the gate's correct-skip message still says nothing under the "
            "configuration directory changed. Once a path under `ansible/` can change "
            "and be excluded, that sentence is false on exactly the runs a reader "
            f"consults it about -- one of them being why the suite did not run: {combined!r}",
        )
        self.assertIn(
            "read",
            lowered,
            "the gate's correct-skip message does not say that nothing the suite "
            "READS changed. That is the distinction the whole branch now turns on, "
            f"and the message is the only place a reader meets it: {combined!r}",
        )

    def test_a_failed_discovery_is_not_reported_as_a_correct_skip(self) -> None:
        """SPECIFIED -- scenario "Discovery failing is not reported as a correct
        skip": "the aggregating job SHALL fail identifying discovery as the
        cause, rather than concluding success on the ground that the suite was
        not owed".

        The row is discovery `failure` with change detection reporting `false`,
        which the gate's existing table does not carry: its discovery-failure
        row pairs the failure with an EMPTY change-detection output, on the
        ground that a failed job's outputs are empty. This change makes the
        `false` pairing the ordinary case rather than an oddity -- most pull
        requests now legitimately resolve `false` -- so the row is worth
        stating. A gate that read change detection before the discovery result
        would conclude success here.
        """
        result = self._run_gate(discovery="failure", changed="false", matrix="skipped")
        combined = (result.stdout + result.stderr).strip()
        self.assertNotEqual(
            0,
            result.returncode,
            "the gate concluded success on a run whose role discovery FAILED, on the "
            "ground that change detection had said the suite was not owed. The suite "
            "that gates every merge having silently disappeared is not a fact only "
            f"pull requests touching `ansible/` should learn: {combined!r}",
        )
        self.assertIn(
            "discover",
            combined.lower(),
            "the gate refused the row without naming discovery as the cause, so a "
            "reader meets a failed required check and looks at the change filter: "
            f"{combined!r}",
        )


# --------------------------------------------------------------------------
# The three relocated scans, and the file set they read.
#
# EVERY PAYLOAD BELOW IS ASSEMBLED AT RUN TIME, from halves, and that is
# required rather than stylistic. This module is itself a tracked file, so a
# literal token marker or private-key delimiter written here would be matched by
# the very scans it is testing -- the scan would report its own test module --
# and `gitleaks`, which `pre-commit` runs on every commit, would very likely
# refuse the commit that introduced it. The role-level scan this change
# relocates assembles its search pattern for the same reason, and its comment
# says so; what this change adds is that the PAYLOAD the pattern is tested
# against must be assembled too.
# --------------------------------------------------------------------------

TOKEN_MARKERS = (
    "gh" + "p_" + "A" * 24,
    "gh" + "o_" + "B" * 24,
    "github" + "_pat_" + "C" * 24,
)

PRIVATE_KEY_MARKERS = (
    "-----BEGIN" + " " + "PRIVATE KEY-----",
    "-----BEGIN" + " OPENSSH " + "PRIVATE KEY-----",
    "-----BEGIN" + " RSA " + "PRIVATE KEY-----",
)

# A value that is a committed literal without being a token marker: this module
# is scanned by the marker scan too, so a fixture for the `ghcr_pull_token`
# assignment scan must not double as a fixture for the one beside it.
COMMITTED_LITERAL = "a-literal-someone-pasted-here"


def as_bytes(files: dict) -> dict:
    """The mapping shape `tracked_files()` returns: path -> bytes."""
    return {
        path: body if isinstance(body, bytes) else body.encode("utf-8")
        for path, body in files.items()
    }


class TestTheRelocatedScansMatchOverASuppliedFileList(unittest.TestCase):
    """MODIFIED requirements: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge; The Continuous-Integration Configuration Is
    Itself Verified.

    The negative cases for all three scans, against fixtures rather than
    against the repository, per that change's tasks.md 1.5. A scan whose red
    state has never been seen establishes nothing: its patterns could be
    misspelled, its file set empty, its loop never entered, and every one of
    those reads as a clean repository.
    """

    def test_a_token_marker_is_caught_wherever_in_the_repository_it_lands(self) -> None:
        """SPECIFIED -- scenario "A committed credential is caught wherever in
        the repository it lands": "in any tracked file -- including one under no
        directory the Molecule suite is triggered by".

        The fixture puts the marker under `terraform/`, which is the point
        rather than a convenience: held inside a Molecule verify play this scan
        ran only on pull requests that changed `ansible/`, so a token pasted
        here was seen by this check on no pull request at all.
        """
        scan = suite_symbol("files_carrying_a_token_marker")
        for marker in TOKEN_MARKERS:
            with self.subTest(marker=marker[:4]):
                files = as_bytes(
                    {
                        "terraform/environments/prod/main.tf": f'variable "t" {{ default = "{marker}" }}\n',
                        "README.md": "# infrastructure\n",
                    }
                )
                offenders = scan(files)
                self.assertIn(
                    "terraform/environments/prod/main.tf",
                    offenders,
                    "a committed GitHub/GHCR token marker under `terraform/` was not "
                    f"reported; the scan returned {offenders}",
                )

    def test_a_private_key_marker_is_caught_wherever_in_the_repository_it_lands(self) -> None:
        """SPECIFIED -- the same scenario, for the operator private-key marker,
        and the one scan this change WIDENS: from `ansible/inventory/` to every
        tracked file. The fixture puts the key outside `ansible/` entirely,
        which the scan's old root could not have reached.
        """
        scan = suite_symbol("files_carrying_a_private_key_marker")
        for marker in PRIVATE_KEY_MARKERS:
            with self.subTest(marker=marker):
                files = as_bytes(
                    {
                        "platform/secrets/operator": marker + "\nAAAA\n-----END PRIVATE KEY-----\n",
                        "README.md": "# infrastructure\n",
                    }
                )
                offenders = scan(files)
                self.assertIn(
                    "platform/secrets/operator",
                    offenders,
                    "a committed operator private key outside `ansible/` was not "
                    f"reported; the scan returned {offenders}",
                )

    def test_a_clean_file_list_yields_no_offender(self) -> None:
        """SPECIFIED -- the converse both assertions above need. A scan that
        reported every file would satisfy them while saying nothing, and would
        make the repository permanently red rather than permanently green --
        the second being the failure this capability refuses everywhere, and
        the first being the one that gets a check deleted.
        """
        files = as_bytes(
            {
                "README.md": "# infrastructure\n",
                "ansible/inventory/group_vars/prod.yml": "ops_user_accounts: []\n",
                "terraform/environments/prod/main.tf": 'module "server" {}\n',
            }
        )
        self.assertEqual([], list(suite_symbol("files_carrying_a_token_marker")(files)))
        self.assertEqual([], list(suite_symbol("files_carrying_a_private_key_marker")(files)))
        self.assertEqual([], list(suite_symbol("ghcr_token_literal_assignments")(files)))

    def test_the_scans_report_only_what_the_supplied_file_list_holds(self) -> None:
        """SPECIFIED -- scenario "An ignored file is not scanned and does not
        fail the suite": "the scans SHALL read the repository's tracked files
        only".

        Half of that scenario, asserted where it is cheap: the scans are a pure
        function of the list they are given, so a path absent from the list is
        not reported however much of a marker it carries. The other half -- that
        the list IS the tracked files -- needs a repository and is asserted
        below.
        """
        marker = TOKEN_MARKERS[0]
        present = as_bytes({"ansible/.envrc": f"export MOLECULE_GHCR_PULL_TOKEN={marker}\n"})
        self.assertEqual(
            ["ansible/.envrc"],
            list(suite_symbol("files_carrying_a_token_marker")(present)),
            "the scan did not report a marker in the file list it was given, so this "
            "assertion's converse below would establish nothing",
        )
        self.assertEqual(
            [],
            list(suite_symbol("files_carrying_a_token_marker")(as_bytes({"README.md": "# x\n"}))),
            "the scan reported a file that was not in the list it was given, so what "
            "it reads is not the list at all",
        )

    def test_matching_is_over_bytes_so_an_undecodable_file_fails_nothing(self) -> None:
        """SPECIFIED -- "Matching within a tracked file SHALL be over its bytes
        rather than over a decoded string, so that a file this suite cannot
        decode fails no assertion it was not going to fail anyway."

        None is tracked today and nothing prevents one. Decoded as text, an
        undecodable file is a hard failure that examined nothing -- which is the
        shape of failure this whole decision exists to prevent, reached from the
        other side.
        """
        marker = TOKEN_MARKERS[0]
        files = as_bytes(
            {
                "docs/binary.bin": b"\xff\xfe\x00\x01 not utf-8 \x80\x81",
                "docs/pasted.txt": f"token={marker}\n",
            }
        )
        offenders = suite_symbol("files_carrying_a_token_marker")(files)
        self.assertEqual(
            ["docs/pasted.txt"],
            list(offenders),
            "the scan did not read past an undecodable tracked file; it returned "
            f"{offenders}",
        )

    # ----------------------------------------------------------------------
    # The `ghcr_pull_token` assignment scan, whose continuation-absorbing
    # reading is the property a casual reimplementation loses.
    # ----------------------------------------------------------------------

    FOLDED_LITERAL = (
        "---\n"
        "deploy_user_per_app:\n"
        "  - name: app\n"
        "    ghcr_pull_token: >-\n"
        f"      {COMMITTED_LITERAL}\n"
    )
    FOLDED_ENV_LOOKUP = (
        "---\n"
        "deploy_user_per_app:\n"
        "  - name: app\n"
        "    ghcr_pull_token: >-\n"
        "      {{ lookup('env', 'MOLECULE_GHCR_PULL_TOKEN') }}\n"
    )
    INLINE_VAULT = (
        "---\n"
        "ghcr_pull_token: !vault |\n"
        "  $ANSIBLE_VAULT;1.1;AES256\n"
        "  6162636465666768696a6b6c6d6e6f70\n"
    )

    def test_a_folded_scalar_assignment_of_a_literal_is_caught(self) -> None:
        """SPECIFIED -- scenario "A credential assigned across a folded scalar's
        continuation is still caught": the scan reads the assignment together
        with its continuation and fails where that value is a committed literal.

        The fixture is pinned to the hard case, and the precondition below is
        what pins it: the assignment LINE carries no value at all. A
        line-oriented reading sees `ghcr_pull_token: >-`, finds nothing after
        the colon, and passes over it -- which the scenario says SHALL NOT
        satisfy this requirement. Both of this repository's real scenario
        converge files assign the token exactly this way, so a line-oriented
        reimplementation would pass over every assignment there is.
        """
        assignment = [
            line for line in self.FOLDED_LITERAL.splitlines() if "ghcr_pull_token" in line
        ]
        self.assertEqual(
            1, len(assignment), "the fixture should carry exactly one assignment line"
        )
        self.assertEqual(
            "",
            assignment[0].split(":", 1)[1].replace(">-", "").strip(),
            "the fixture's assignment line carries a value, so it is not the folded "
            "case this scenario is about and a line-oriented scan would pass it",
        )
        offenders = suite_symbol("ghcr_token_literal_assignments")(
            as_bytes({"ansible/roles/deploy_user/molecule/default/converge.yml": self.FOLDED_LITERAL})
        )
        self.assertTrue(
            any(
                entry.startswith("ansible/roles/deploy_user/molecule/default/converge.yml")
                for entry in offenders
            ),
            "a `ghcr_pull_token` assigned a committed literal across a folded scalar's "
            f"continuation was not reported; the scan returned {offenders}",
        )

    def test_a_folded_scalar_assignment_of_an_environment_lookup_is_accepted(self) -> None:
        """SPECIFIED -- the same scenario's acceptance half: the scan accepts
        the value "only where it is an inline vault value or an environment
        lookup".

        This is the fixture that keeps the assertion above from being satisfied
        by a scan that reports every assignment it finds. It is also the shape
        both of this repository's scenario converge files carry, and those files
        are deliberately NOT excluded by path -- excluding them would blind the
        scan permanently in exactly the files most likely to acquire a pasted
        real token, since running the credentialled verification means having a
        live token at the keyboard while editing them.
        """
        offenders = suite_symbol("ghcr_token_literal_assignments")(
            as_bytes(
                {"ansible/roles/deploy_user/molecule/default/converge.yml": self.FOLDED_ENV_LOOKUP}
            )
        )
        self.assertEqual(
            [],
            list(offenders),
            "a `ghcr_pull_token` read from the environment across a folded scalar's "
            f"continuation was reported as a committed literal: {offenders}. This is "
            "this project's correct pattern; a scan red on a correct tree is a scan "
            "somebody deletes",
        )

    def test_an_inline_vault_value_is_accepted(self) -> None:
        """SPECIFIED -- the same scenario's other acceptance: an inline `!vault`
        value. `ansible/inventory/group_vars/prod.yml` carries the token this
        way inside an otherwise plaintext file, which is this project's
        documented pattern.
        """
        offenders = suite_symbol("ghcr_token_literal_assignments")(
            as_bytes({"ansible/inventory/group_vars/prod.yml": self.INLINE_VAULT})
        )
        self.assertEqual(
            [],
            list(offenders),
            f"an inline `!vault` token value was reported as a committed literal: "
            f"{offenders}",
        )

    def test_the_assignment_scan_reads_yaml_files(self) -> None:
        """DERIVED (that change's tasks.md 1.3: the file set becomes the tracked
        files "filtered to the same extensions ... the YAML restriction is the
        scan's subject rather than an optimisation"). No scenario states which
        extensions are read.

        Asserted as the positive only. That a `.txt` carrying the same text is
        NOT reported is the other half of the restriction and is deliberately
        left untested: reporting it would be harmless, the delta does not
        require the narrowing, and an assertion that the scan reads LESS is one
        this change's author would be inventing.
        """
        for name in (
            "ansible/roles/deploy_user/molecule/default/converge.yml",
            "ansible/inventory/group_vars/prod.yaml",
        ):
            with self.subTest(path=name):
                offenders = suite_symbol("ghcr_token_literal_assignments")(
                    as_bytes({name: self.FOLDED_LITERAL})
                )
                self.assertTrue(
                    any(entry.startswith(name) for entry in offenders),
                    f"a committed literal in {name} was not reported: {offenders}",
                )


class TestTheScansReadTheRepositorysTrackedFiles(unittest.TestCase):
    """MODIFIED requirement: The Continuous-Integration Configuration Is Itself
    Verified -- "The file set such a scan reads SHALL be the repository's
    tracked files."

    Every fixture here is a real repository built in a temporary directory, and
    every one of them spawns `git`. See this module's docstring for why that is
    a reported consequence rather than an oversight.
    """

    def _repository(self, tracked: dict, ignored: dict | None = None) -> Path:
        require_external_tools(
            self,
            ("git",),
            "build the throwaway repository these assertions read tracked files from",
        )
        root = Path(tempfile.mkdtemp(prefix="tracked-files-fixture-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        self._git(root, "init", "--quiet")
        for relative, body in {**tracked, **(ignored or {})}.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(body, bytes):
                target.write_bytes(body)
            else:
                target.write_text(body, encoding="utf-8")
        if ignored:
            (root / ".gitignore").write_text(
                "".join(f"{name}\n" for name in ignored) + ".gitignore\n", encoding="utf-8"
            )
        for relative in tracked:
            self._git(root, "add", "--", relative)
        return root

    def _git(self, root: Path, *arguments: str) -> None:
        # Spawned openly: the delta admits "the version-control binary that
        # placed the files there" as the one exception to this suite's
        # standard-library limit, and reads the tracked set through it.
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            0,
            result.returncode,
            f"the fixture repository could not be built: `git {' '.join(arguments)}` "
            f"exited {result.returncode}: {(result.stdout + result.stderr).strip()!r}",
        )

    def test_ignored_content_is_not_scanned_and_does_not_fail_the_suite(self) -> None:
        """SPECIFIED -- scenario "An ignored file is not scanned and does not
        fail the suite": "a dependency cache, a virtual environment, another
        working tree, or an ignored environment file carrying a real credential".

        The fixture's ignored file is `ansible/.envrc`, which is where this
        repository's `MOLECULE_GHCR_PULL_TOKEN` legitimately lives, so it
        plausibly holds a real token on a developer's machine. A walk of the
        filesystem reports it, the remedy reached for is a path-exclusion list,
        and that list blinds the scan permanently in whichever directory
        acquired it. An uncommitted credential is the commit hook's to catch.
        """
        marker = TOKEN_MARKERS[0]
        root = self._repository(
            tracked={"README.md": "# infrastructure\n"},
            ignored={"ansible/.envrc": f"export MOLECULE_GHCR_PULL_TOKEN={marker}\n"},
        )
        files = suite_symbol("tracked_files")(root)
        self.assertIn("README.md", files, f"the tracked file was not enumerated: {sorted(files)}")
        self.assertNotIn(
            "ansible/.envrc",
            files,
            "an ignored file was enumerated as tracked, so the scans would report a "
            "developer's real, uncommitted credential as a committed secret and the "
            f"suite would be red on a correct tree: {sorted(files)}",
        )
        self.assertEqual(
            [],
            list(suite_symbol("files_carrying_a_token_marker")(files)),
            "the scan reported ignored content as a committed secret",
        )

    def test_the_enumeration_returns_the_bytes_of_each_tracked_file(self) -> None:
        """SPECIFIED -- "Matching within a tracked file SHALL be over its bytes
        rather than over a decoded string." The helper is where that is decided;
        a helper returning decoded text makes the scans' byte matching
        impossible however they are written.
        """
        root = self._repository(
            tracked={"docs/binary.bin": b"\xff\xfe\x00\x01", "README.md": "# infrastructure\n"}
        )
        files = suite_symbol("tracked_files")(root)
        self.assertEqual(
            b"\xff\xfe\x00\x01",
            files.get("docs/binary.bin"),
            "the enumeration did not return an undecodable tracked file's bytes "
            f"unchanged; it returned {files.get('docs/binary.bin')!r}",
        )

    def test_an_unavailable_enumeration_fails_rather_than_skipping(self) -> None:
        """SPECIFIED -- scenario "A scan that cannot enumerate tracked files
        fails rather than skipping": "the affected assertion SHALL fail, naming
        the enumeration as the cause, rather than skipping and allowing the
        suite to report success for a property nothing examined".

        This is the one place this suite's existing skip-guard must NOT be
        copied, and the test therefore refuses a skip explicitly rather than
        merely asserting that something is raised. A guarded skip is the right
        shape for an assertion whose absence leaves another check standing; it
        is the wrong shape for a scan for committed credential material, where a
        skip reports success for a property nothing examined.
        """
        require_external_tools(self, ("git",), "establish what an unavailable enumeration does")
        outside = Path(tempfile.mkdtemp(prefix="not-a-repository-"))
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (outside / "README.md").write_text("# not a repository\n", encoding="utf-8")
        enumerate_tracked = suite_symbol("tracked_files")
        try:
            result = enumerate_tracked(outside)
        except unittest.SkipTest as skipped:
            self.fail(
                "the enumeration SKIPPED where the tracked files could not be listed: "
                f"{skipped}. A skipped credential scan reports success for a property "
                "nothing examined, which is the hole this clause exists to refuse"
            )
        except AssertionError as refusal:
            self.assertRegex(
                str(refusal),
                r"git|track|enumerat",
                "the enumeration refused without naming the enumeration as the cause, "
                f"so a reader meets a failed scan and looks for a committed secret: {refusal}",
            )
        else:
            self.fail(
                "the enumeration returned "
                f"{result!r} for a directory that is not a repository, rather than "
                "failing. Whatever it returned, every scan built on it then examines "
                "that and reports the repository clean"
            )

    def test_a_tracked_path_absent_from_the_working_tree_fails_naming_it(self) -> None:
        """SPECIFIED -- "a tracked path absent from the working tree SHALL fail
        naming that path, a partial checkout being unable to establish a
        property over the committed tree".

        A sparse or interrupted checkout is a state to hear about rather than to
        scan around: silently skipping the missing path leaves the scan
        reporting a clean tree it never read.
        """
        root = self._repository(
            tracked={"README.md": "# infrastructure\n", "docs/gone.md": "# removed\n"}
        )
        (root / "docs" / "gone.md").unlink()
        try:
            result = suite_symbol("tracked_files")(root)
        except unittest.SkipTest as skipped:
            self.fail(f"the enumeration skipped on a partial checkout: {skipped}")
        except AssertionError as refusal:
            self.assertIn(
                "docs/gone.md",
                str(refusal),
                "the enumeration refused without naming the absent path, so nobody can "
                f"tell which file the checkout is missing: {refusal}",
            )
        else:
            self.fail(
                "the enumeration passed over a tracked path absent from the working "
                f"tree, returning {sorted(result)}. Every scan built on it then "
                "reports a property established over a file it never read"
            )


class TestTheRepositoryScopeScansNoLongerRunOnlyWhenAnsibleChanges(unittest.TestCase):
    """MODIFIED requirements: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge -- "A static property of committed files
    reaching outside the role directory whose scenario holds it SHALL NOT be
    verified only by the suite"; and The Continuous-Integration Configuration Is
    Itself Verified -- scenario "A repository-scope scan is not confined to one
    directory's trigger".

    A scan COPIED rather than MOVED leaves the suite asserting what
    `.github/tests` now asserts, on a subset of the pull requests -- and leaves
    the exclusions unsafe for the one scan whose root is the directory the
    exclusions remove.
    """

    RELOCATED_FROM = (
        "ansible/roles/deploy_user/molecule/default/verify.yml",
        "ansible/roles/ops_user/molecule/default/verify.yml",
    )

    # Three `../` climb from `<role>/molecule/<scenario>/` past the role
    # directory. Every read design.md Decision 1's table leaves in these two
    # files is role-local and reaches at most `../..`; each of the three this
    # change relocates climbs to `ansible/` or to the repository root.
    ESCAPES_THE_ROLE_DIRECTORY = "../../../"

    def test_no_relocated_scan_remains_in_the_verify_plays(self) -> None:
        """SPECIFIED -- the clauses above. Asserted by what the committed
        scenario text still reaches rather than by the scan's own words, so
        that a relocation which respells the path is not reported as a failure
        and a copy which renames the task is not reported as a success.
        """
        for relative in self.RELOCATED_FROM:
            with self.subTest(scenario=relative):
                text = read_text(ROOT / relative)
                self.assertNotIn(
                    self.ESCAPES_THE_ROLE_DIRECTORY,
                    text,
                    f"{relative} still carries a path climbing above its own role "
                    "directory. The repository-scope scans belong in this suite, which "
                    "runs on every pull request unconditionally; held here they cover "
                    "only the pull requests that happen to change `ansible/`, which is "
                    "not the scope they claim -- and the inventory scan would stop "
                    "running on precisely the pull requests it exists to watch, since "
                    "`ansible/inventory/**` no longer selects the suite",
                )


# --------------------------------------------------------------------------
# The premise the exclusions rest on: no authored scenario reads a path the
# exclusions name.
#
# A check of this kind that has never been seen red establishes nothing; one
# never seen to IGNORE the managed-node class will be narrowed by whoever meets
# the twenty-five-site version of it; and one never seen to survive a line shift
# is the defect design.md Decision 1a exists to prevent. The five fixtures that
# change's tasks.md 3.4 enumerates are below, plus one per route from its 3.2.
# --------------------------------------------------------------------------

MINIMAL_SCENARIO_DEFINITION = "---\ndriver:\n  name: docker\nplatforms:\n  - name: instance\n"

FIXTURE_GALAXY_MANIFEST = 'roles:\n  - name: geerlingguy.docker\n    version: "8.0.0"\n'

# The permitted read design.md Decision 1's table records for `docker`, spelled
# as that scenario spells it: a file-reading lookup built by CONCATENATION
# rather than by interpolation, which is what the first sweep's path pattern
# missed.
PERMITTED_DOCKER_READ = """---
- name: Verify
  hosts: all
  tasks:
    - name: Read the committed requirements.yml from the repository
      ansible.builtin.set_fact:
        content: "{{ lookup('file', playbook_dir + '/../../../../requirements.yml') }}"
      delegate_to: localhost
      become: false
"""

SECOND_READ_OF_THE_SAME_TARGET = """---
- name: Verify
  hosts: all
  tasks:
    - name: Read the committed requirements.yml from the repository
      ansible.builtin.set_fact:
        content: "{{ lookup('file', playbook_dir + '/../../../../requirements.yml') }}"
      delegate_to: localhost
      become: false

    - name: Read the committed requirements.yml again, for a second assertion
      ansible.builtin.set_fact:
        content_again: "{{ lookup('file', playbook_dir + '/../../../../requirements.yml') }}"
      delegate_to: localhost
      become: false
"""

PERMITTED_DOCKER_READ_SHIFTED_DOWN = """---
# This scenario's header grew by a paragraph, and three tasks were added above
# the read below. Nothing about the read itself changed.
- name: Verify
  hosts: all
  tasks:
    - name: Gather an unrelated fact
      ansible.builtin.command: docker info
      register: info
      changed_when: false

    - name: Assert over that fact
      ansible.builtin.assert:
        that:
          - info.rc == 0

    - name: Read the committed requirements.yml from the repository
      ansible.builtin.set_fact:
        content: "{{ lookup('file', playbook_dir + '/../../../../requirements.yml') }}"
      delegate_to: localhost
      become: false
"""

READS_AN_EXCLUDED_PATH = """---
- name: Verify
  hosts: all
  tasks:
    - name: Scan the committed inventory for key material
      ansible.builtin.slurp:
        src: "{{ playbook_dir }}/../../../../inventory/group_vars/prod.yml"
      register: scanned
      delegate_to: localhost
      become: false
"""

UNRECOGNISED_CONSTRUCTION = """---
- name: Verify
  hosts: all
  tasks:
    - name: Read the manifest through a lookup this check has no rule for
      ansible.builtin.set_fact:
        content: "{{ lookup('an_unfamiliar_plugin', playbook_dir + '/../../../../requirements.yml') }}"
"""

MANAGED_NODE_READS = """---
- name: Verify
  hosts: all
  tasks:
    - name: Read the operator's authorized_keys on the managed node
      ansible.builtin.slurp:
        src: /home/ops-claude/.ssh/authorized_keys
      register: authorized_keys

    - name: Read the sshd configuration on the managed node
      ansible.builtin.slurp:
        src: /etc/ssh/sshd_config.d/60-hardening.conf
      register: sshd_config
"""

DELEGATED_TASK_OPENING_NO_FILE = """---
- name: Verify
  hosts: all
  tasks:
    - name: Select the configured log driver from an already-registered fact
      ansible.builtin.set_fact:
        driver: "{{ info.stdout | from_json | json_query('LoggingDriver') }}"
      delegate_to: localhost
      become: false

    - name: Assert over that value
      ansible.builtin.assert:
        that:
          - driver == 'json-file'
      delegate_to: localhost
      become: false
"""

# One per route from design.md Decision 1, each reaching a path the exclusions
# name and none of them delegating. A check built on delegation alone passes
# every one of these.
UNDELEGATED_ROUTES = {
    "a file-reading lookup": (
        "verify.yml",
        """---
- name: Verify
  hosts: all
  tasks:
    - name: Read the host baseline playbook
      ansible.builtin.set_fact:
        baseline: "{{ lookup('file', playbook_dir + '/../../../../playbooks/host-baseline.yml') }}"
""",
    ),
    "controller-resolved inclusion of a play": (
        "verify.yml",
        """---
- name: Reuse the host baseline play
  import_playbook: ../../../../playbooks/host-baseline.yml
""",
    ),
    "controller-resolved inclusion of variables": (
        "verify.yml",
        """---
- name: Verify
  hosts: all
  vars_files:
    - "{{ playbook_dir }}/../../../../inventory/group_vars/prod.yml"
  tasks:
    - name: Assert the accounts loaded
      ansible.builtin.assert:
        that:
          - ops_user_accounts is defined
""",
    ),
    "a controller-side source path": (
        "verify.yml",
        """---
- name: Verify
  hosts: all
  tasks:
    - name: Ship the host baseline playbook to the node
      ansible.builtin.copy:
        src: ../../../../playbooks/host-baseline.yml
        dest: /tmp/host-baseline.yml
        mode: "0644"
""",
    ),
    "a path in the provisioner environment": (
        "molecule.yml",
        """---
driver:
  name: docker
platforms:
  - name: instance
provisioner:
  name: ansible
  env:
    ANSIBLE_INVENTORY: ${MOLECULE_PROJECT_DIRECTORY}/../../inventory/prod.hcloud.yml
""",
    ),
}


class ScenarioTextFixtureMixin:
    """Builds throwaway trees shaped like `ansible/`, holding scenario TEXT.

    The mixin beside this one in `test_ci_configuration.py` writes `molecule.yml`
    files only, because the checks it serves read platform images. The premise
    check reads converge, prepare and verify plays as well, so this one writes
    whatever it is handed.
    """

    def scenario_tree(self, files: dict) -> Path:
        root = Path(tempfile.mkdtemp(prefix="scenario-text-fixture-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        bodies = {"ansible/requirements.yml": FIXTURE_GALAXY_MANIFEST, **files}
        for relative, body in bodies.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        return root

    def scenario(self, role: str, scenario: str, files: dict) -> dict:
        """One scenario directory: a `molecule.yml` unless one is supplied, plus
        whatever play files the fixture names."""
        prefix = f"ansible/roles/{role}/molecule/{scenario}"
        built = {f"{prefix}/molecule.yml": MINIMAL_SCENARIO_DEFINITION}
        built.update({f"{prefix}/{name}": body for name, body in files.items()})
        return built

    def offenders(self, root: Path) -> list[str]:
        return list(suite_symbol("unpermitted_controller_reads")(root))


class TestThePremiseTheExclusionsRestOnIsChecked(ScenarioTextFixtureMixin, unittest.TestCase):
    """MODIFIED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge -- "The premise the exclusions rest on SHALL
    itself be checked."

    Not a test of the filter. A filter can be perfectly correct about a premise
    that has stopped being true, and the delta says so: "A check on the filter's
    declared patterns does not establish this and is not a substitute for it."
    """

    def test_a_scenario_reaching_an_excluded_path_is_named(self) -> None:
        """SPECIFIED -- scenario "A scenario reaching an excluded path fails the
        pipeline's own checks": the checks "SHALL fail identifying that scenario
        and that read, rather than leaving the exclusion silently covering a
        path that is now read".

        The quiet failure this stands against: someone adds a scenario reading
        `ansible/inventory/`, the filter keeps excluding a path that is now
        read, the suite skips, the gate reports green, and nothing observes the
        gap.
        """
        scenario_file = "ansible/roles/ops_user/molecule/default/verify.yml"
        root = self.scenario_tree(
            self.scenario("ops_user", "default", {"verify.yml": READS_AN_EXCLUDED_PATH})
        )
        offenders = self.offenders(root)
        self.assertTrue(
            offenders,
            "a scenario reading `ansible/inventory/group_vars/prod.yml` from the "
            "controller was reported by nothing. The exclusion for that directory "
            "then covers a path a scenario reads, and the suite skips on the pull "
            "requests that change it",
        )
        self.assertTrue(
            any(scenario_file in offender for offender in offenders),
            f"the refusal does not name the scenario that holds the read: {offenders}",
        )
        self.assertTrue(
            any("inventory" in offender for offender in offenders),
            f"the refusal does not name the read it refused: {offenders}",
        )

    def test_a_second_read_of_an_already_permitted_path_is_refused(self) -> None:
        """SPECIFIED -- scenario "A second read of an already-permitted path is
        still refused": "including one in the same file, by the same
        construction, resolving to the same target, so that it is
        indistinguishable from the permitted read by identity alone ... each
        entry's permitted occurrence count being what separates one such read
        from two".

        Pinned to the hard case deliberately. A fixture putting the second read
        in a DIFFERENT file passes for free under plain set membership, and
        would leave the occurrence count -- the whole point of the clause --
        unexercised. The control below is what makes the refusal readable: the
        same file with ONE read must be permitted, or this test would pass
        against a check that refuses `docker`'s scenario outright.
        """
        permitted = self.scenario_tree(
            self.scenario("docker", "default", {"verify.yml": PERMITTED_DOCKER_READ})
        )
        self.assertEqual(
            [],
            self.offenders(permitted),
            "the single permitted read of `ansible/requirements.yml` in `docker`'s "
            "scenario was refused, so the assertion below would establish nothing -- "
            "and the check is red on the tree as it stands",
        )
        scenario_file = "ansible/roles/docker/molecule/default/verify.yml"
        duplicated = self.scenario_tree(
            self.scenario("docker", "default", {"verify.yml": SECOND_READ_OF_THE_SAME_TARGET})
        )
        offenders = self.offenders(duplicated)
        self.assertTrue(
            offenders,
            "a SECOND read of `ansible/requirements.yml`, in the same file and by the "
            "same construction as the permitted one, was admitted without anyone "
            "looking at it. The enumeration is over individual reads rather than over "
            "the paths they reach, and this is the addition it exists to make someone "
            "consider",
        )
        self.assertTrue(
            any(scenario_file in offender for offender in offenders),
            f"the refusal does not name the file carrying the second read: {offenders}",
        )

    def test_an_unrecognised_construction_carrying_a_repository_path_is_refused(self) -> None:
        """SPECIFIED -- "Where the check meets a construction it does not
        recognise, carrying a path that resolves into this repository, it SHALL
        refuse rather than pass over it."

        The design's chief anti-staleness property, and by that change's own
        tasks.md 3.4 a branch never seen red could be implemented as a
        pass-over with nothing noticing. The fixture's lookup does not delegate
        and is not one of the recognised file-reading lookups, so no other route
        reaches it: a check without the refusal branch sees NO read here at all
        and passes.
        """
        scenario_file = "ansible/roles/some_role/molecule/default/verify.yml"
        root = self.scenario_tree(
            self.scenario("some_role", "default", {"verify.yml": UNRECOGNISED_CONSTRUCTION})
        )
        offenders = self.offenders(root)
        self.assertTrue(
            offenders,
            "an unrecognised construction carrying a path that resolves into this "
            "repository was passed over. A list of routes goes stale exactly as a list "
            "of paths does, and an unrecognised construction that is ignored is a "
            "silent gap where one that is refused costs a visible edit to permit",
        )
        self.assertTrue(
            any(scenario_file in offender for offender in offenders),
            f"the refusal does not name the construction it refused: {offenders}",
        )

    def test_a_controller_read_that_does_not_delegate_is_still_a_controller_read(self) -> None:
        """SPECIFIED -- scenario "A controller read that does not delegate is
        still a controller read": "through a file-reading lookup expression, a
        controller-resolved inclusion of variables, tasks or plays, or a
        controller-side source path -- or through a path declared in its
        provisioner environment, which carries no task at all".

        The inclusion-of-plays route is not hypothetical: this repository's
        `platform_data_volume` scenario reads three sibling files through
        `import_playbook` today, carrying no delegation at all, and a check
        built without that route passes them silently. A filter assertion would
        have caught none of these.
        """
        for route, (filename, body) in UNDELEGATED_ROUTES.items():
            with self.subTest(route=route):
                root = self.scenario_tree(
                    self.scenario("some_role", "default", {filename: body})
                )
                offenders = self.offenders(root)
                self.assertTrue(
                    offenders,
                    f"a controller read reaching an excluded path through {route} was "
                    "passed over for carrying no delegation. A check recognising only "
                    "delegation passes a scenario that reads an excluded path through "
                    "any of the others, which is the same vacuous green this "
                    "capability refuses everywhere else",
                )

    def test_a_read_of_the_managed_node_is_not_held_to_the_enumerated_paths(self) -> None:
        """SPECIFIED -- scenario "A read of the managed node is not held to the
        enumerated paths": the checks "SHALL pass over it, no filter over this
        repository being capable of affecting it".

        Roughly twenty undelegated `slurp` tasks read absolute paths inside the
        container today, and `slurp` has no `remote_src` option at all -- so
        delegation rather than any module option is what puts a read on the
        controller. A check drawn wider than this criterion is red on around
        twenty-five sites on day one, and the only recoveries are to permit them
        wholesale, which makes the check meaningless, or to narrow it by a rule
        nobody wrote down, which is how the first version of this design went
        wrong.
        """
        root = self.scenario_tree(
            self.scenario("ops_user", "default", {"verify.yml": MANAGED_NODE_READS})
        )
        self.assertEqual(
            [],
            self.offenders(root),
            "an undelegated read of an absolute path inside the container was held to "
            "the enumerated repository paths. No filter over this repository can "
            "affect it, so requiring it to be enumerated buys nothing and costs the "
            "check its usability",
        )

    def test_a_delegated_task_that_opens_no_file_is_passed_over(self) -> None:
        """DERIVED (design.md Decision 1's second deliberately-excluded class).
        No scenario names it: the scenario above states the managed-node case,
        and this is the other half of the same criterion -- *of a repository
        file*, as distinct from *on the controller*.

        Three sites in this repository derive a value from an already-registered
        fact on the controller while opening nothing, and one runs `docker save`
        into `/tmp` on the controller while reading no repository file at all.
        "Touches the controller" was the wrong criterion, and this fixture is
        what keeps someone from reaching for it. Reconsider this assertion, do
        not weaken it, if the criterion itself is restated.
        """
        root = self.scenario_tree(
            self.scenario("docker", "default", {"verify.yml": DELEGATED_TASK_OPENING_NO_FILE})
        )
        self.assertEqual(
            [],
            self.offenders(root),
            "a delegated task that opens no file was reported as a controller read of "
            "a repository file. It runs on the controller and reads nothing from this "
            "repository, so no exclusion can affect it",
        )

    def test_a_permitted_read_shifted_to_another_line_is_still_recognised(self) -> None:
        """SPECIFIED -- scenario "Editing a scenario above a permitted read does
        not invalidate the permitted set": "including the commit that relocates
        reads out of that same file ... its identity resting on the file, the
        construction and the target it resolves to rather than on a line
        offset".

        Immediate rather than theoretical: this change's own section 1 deletes
        three tasks from two of the files the permitted table names, so every
        surviving read below them sits at a different offset the moment the
        relocation lands. A check keyed on offsets is wrong on the commit that
        introduces it, and wrong in both directions -- it reports the surviving
        role-local scans as violations, and it permits whatever text has slid
        onto the recorded numbers.
        """
        shifted = self.scenario_tree(
            self.scenario("docker", "default", {"verify.yml": PERMITTED_DOCKER_READ_SHIFTED_DOWN})
        )
        self.assertEqual(
            [],
            self.offenders(shifted),
            "a permitted read moved to a different line in the same file was reported "
            "as unpermitted. The permitted set is then wrong on any commit that edits "
            "a scenario above one of its entries, and the reads it names are reported "
            "as violations while whatever text took their offsets is permitted",
        )
        # The shift must be real, or this test passes against a check that keys
        # on the offset the fixture happened not to move.
        original = PERMITTED_DOCKER_READ.splitlines().index(
            "    - name: Read the committed requirements.yml from the repository"
        )
        moved = PERMITTED_DOCKER_READ_SHIFTED_DOWN.splitlines().index(
            "    - name: Read the committed requirements.yml from the repository"
        )
        self.assertNotEqual(
            original,
            moved,
            "the fixture did not actually move the read to a different line, so this "
            "assertion establishes nothing about line offsets",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
