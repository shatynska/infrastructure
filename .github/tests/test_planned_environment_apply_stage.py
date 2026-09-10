"""Static-assertion tests for the apply stage that runs over the environments
that produced a plan, and for the concurrency split that keeps a queued plan
away from a waiting apply.

Derived from the AMENDED delta specifications of the OpenSpec change
`make-the-pipeline-environment-agnostic` at commit `8d66bf3`, which is the
commit holding the approved amended plan, and from no implementation of them.
The path those deltas sit at is not written here: a change's artifacts move when
it is archived, and this repository's citation convention is to name the change
and the artifact in prose instead.

Two requirements of `iac-cicd-pipeline` are the subject, and only the sentences
this revisit ADDED to them:

- *Gated Production Apply Applies the Reviewed Plan* — that an environment is
  applied only where its own plan was produced, that an environment whose plan
  failed does not prevent another being applied, that an environment counts as
  having produced a saved plan only where every check its plan job performs has
  passed, that the resolution of that set fails closed while accepting an
  explicitly empty one, and that the apply stage does not reach its conclusion
  through the plan stage's aggregate result.
- *Serialized Terraform Runs* — that within the apply workflow the plan job and
  the apply job do not share a concurrency group, and that a plan run in another
  workflow is placed in neither.

Everything else in those two requirements was covered by the first derivation
pass and is not restated here. See that change's `test-plan.md` for the
scenario-to-test mapping of both passes, the baseline, the scenarios left
uncovered and the assumptions this pass took.

Why this is a fifth file in the suite
-------------------------------------
This pass may only ADD. `test_environment_agnostic_pipeline.py` is the first
pass's output and is an existing test file; nothing here edits, deletes or
disables any test in it, or in any other module. Where this file needs a helper
either sibling already has, it imports it rather than restating it, which is the
idiom the modules beside it already use.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_planned_environment_apply_stage.TestTheApplyStageRunsOverThePlanned \\
        .test_the_apply_matrix_reads_a_set_resolved_after_the_plan_stage

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the two helper imports below resolve.

What no assertion here establishes
----------------------------------
Nothing in this file reads repository settings, and nothing in it makes a
network call. Whether a GitHub Environment requires a reviewer, whether a job
awaiting its protection rules counts as *pending* for a concurrency group — the
premise the delta itself records as unestablished — and what GitHub does with an
empty matrix are all outside what a committed file can say. A green run here
establishes that the workflow text is shaped so those behaviours land where the
requirement wants them, never that they were observed.

The `gh` this file's executed body meets is a stub written into a scratch
directory and put on `PATH` for the duration of one `bash` invocation. It prints
a fixture and never reaches the network; the suite's own no-privileged-resource
constraint is what requires that, and `bash` remains the only command this
module spawns.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

import yaml

from test_ci_configuration import (
    APPLY,
    PR_VALIDATION,
    compact,
    github_output_pairs,
    jobs,
    load_yaml,
    require_external_tools,
    step_label,
    steps,
)
from test_environment_agnostic_pipeline import (
    DRIFT,
    PROD_ROW,
    STAGING_ROW,
    TERRAFORM_APPLY,
    TERRAFORM_PLAN,
    declared_environment,
    jobs_running,
    needs_of,
    run_snippet,
)

# --------------------------------------------------------------------------
# Shapes, not names
#
# Every locator below finds a job or a step by what the requirement says it
# must BE, never by the name this change happened to give it. The change's own
# tasks.md 4.3b and 3.4 fix one shape deliberately and for this suite's benefit:
# the body resolving the planned set carries no `${{ }}` and takes every input
# through `env:`, so that it can be pulled out of the workflow and executed.
# That constraint is what makes the executable class below possible at all, and
# its failure messages say so, so a red test reads as a contract rather than as
# a mystery.
# --------------------------------------------------------------------------

EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.S)
NEEDS_OUTPUT = re.compile(r"needs\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)")
NEEDS_RESULT = re.compile(r"needs\.([A-Za-z0-9_-]+)\.(result|outcome|conclusion)")
STEPS_OUTPUT = re.compile(r"steps\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)")

# The two spellings that suppress the `success()` a `needs:` edge implies. One
# of them has to be present for a job to run at all once a dependency failed,
# which is the whole of what "SHALL NOT reach its conclusion through the plan
# stage's aggregate result" asks for at the mechanism level.
SURVIVES_A_FAILED_DEPENDENCY = ("always()", "!cancelled()", "!(cancelled())")

UPLOAD_ACTION = "upload-artifact"
DOWNLOAD_ACTION = "download-artifact"

# The run context a rendered artifact name may legitimately be built from. The
# resolver has the run id and the repository through `env:` (tasks.md 4.3b), so
# a name built from either is still a name it can reconstruct; a name built from
# anything else is not, and the test says which expression it could not resolve
# rather than silently comparing against the wrong string.
RUN_ID = "424242"
REPOSITORY = "octocat/infrastructure"
SHA = "0" * 40
RUN_CONTEXT = {
    "github.run_id": RUN_ID,
    "github.repository": REPOSITORY,
    "github.sha": SHA,
    "github.run_attempt": "1",
    "github.run_number": "1",
    "github.ref_name": "main",
}

# A stub `gh`, so that a body reading this run's artifact NAMES through the API
# can be executed with no network and no credential. It answers whatever the
# body asks, including the `--jq` form, from a fixture file -- and refuses when
# the fixture says to, which is the unresolvable case the delta requires to fail
# the run.
GH_STUB = """#!/usr/bin/env bash
set -u
if [ "${STUB_GH_EXIT:-0}" != "0" ]; then
  echo "gh: HTTP 502 Bad Gateway (stub refusing on purpose)" >&2
  exit "${STUB_GH_EXIT}"
fi
filter=""
previous=""
for argument in "$@"; do
  case "${previous}" in
    --jq|-q) filter="${argument}" ;;
  esac
  case "${argument}" in
    --jq=*) filter="${argument#--jq=}" ;;
    -q=*) filter="${argument#-q=}" ;;
  esac
  previous="${argument}"
done
if [ -n "${filter}" ]; then
  jq -r "${filter}" "${STUB_GH_BODY}"
else
  cat "${STUB_GH_BODY}"
fi
"""


def concurrency_group(holder: object) -> str | None:
    """A workflow's or a job's `concurrency` group, in either spelling."""
    if not isinstance(holder, dict):
        return None
    value = holder.get("concurrency")
    if value is None:
        return None
    if isinstance(value, dict):
        return compact(value.get("group", ""))
    return compact(value)


def collapsed(group: str) -> str:
    """A concurrency group with every `${{ }}` replaced by one placeholder.

    This is what "the two groups cannot coincide for any environment name"
    means as a static read: two groups differing only in WHICH expression they
    interpolate can hold the same value for some environment -- `terraform-${{
    matrix.name }}` and `terraform-${{ matrix.github_environment }}` coincide
    for any environment whose directory and GitHub Environment are spelled the
    same, which is exactly the case prod is one edit away from. Two groups
    differing in their LITERAL text cannot coincide for any value at all.
    """
    return EXPRESSION.sub("<expr>", str(group))


def condition_of(holder: object) -> str:
    return compact((holder or {}).get("if", "")) if isinstance(holder, dict) else ""


def transitive_needs(workflow: dict, name: str) -> set:
    """Every job reachable from `name` through `needs:` edges."""
    declared = jobs(workflow)
    reached: set = set()
    frontier = list(needs_of(declared.get(name) or {}))
    while frontier:
        current = frontier.pop()
        if current in reached:
            continue
        reached.add(current)
        frontier.extend(needs_of(declared.get(current) or {}))
    return reached


class ApplyWorkflowMixin:
    """The apply workflow's three stages, each located by what it does."""

    def setUp(self) -> None:  # noqa: N802 - unittest's own spelling
        self.workflow = load_yaml(APPLY)
        self.planning = jobs_running(self.workflow, TERRAFORM_PLAN)
        self.applying = jobs_running(self.workflow, TERRAFORM_APPLY)

    def _require_both_stages(self) -> None:
        self.assertTrue(self.planning, "no job in apply.yml runs `terraform plan`")
        self.assertTrue(self.applying, "no job in apply.yml runs `terraform apply`")

    def _resolver(self):
        """(name, job, output) of the job whose output the apply matrix reads.

        Found by the edge the requirement itself describes -- "The set of
        environments to apply SHALL instead be resolved from which environments
        actually produced a saved plan" -- and never by a job name: whichever
        job supplies the apply matrix IS that resolution, whatever it is called.
        """
        self._require_both_stages()
        supplying: dict = {}
        for name, job in sorted(self.applying.items()):
            expression = compact((job.get("strategy") or {}).get("matrix"))
            pairs = set(NEEDS_OUTPUT.findall(expression))
            self.assertTrue(
                pairs,
                f"the apply job `{name}` builds its matrix from no job's output "
                f"({expression!r}), so the environments it applies are not resolved "
                "from which environments produced a saved plan. A matrix taken from "
                "the merge's affected set applies an environment whose plan failed, "
                "or -- coupled through `needs:` -- applies none of them when any one "
                "environment failed to plan",
            )
            for source, output in pairs:
                supplying.setdefault(source, set()).add(output)
        self.assertEqual(
            1,
            len(supplying),
            "expected the apply matrix to read exactly one job's output -- the "
            "resolution of which environments produced a saved plan -- but it reads "
            f"{sorted(supplying)}",
        )
        name, outputs = next(iter(supplying.items()))
        self.assertIn(
            name,
            jobs(self.workflow),
            f"the apply matrix reads the output of `{name}`, which apply.yml declares "
            "no such job",
        )
        self.assertEqual(
            1,
            len(outputs),
            f"the apply matrix reads more than one output of `{name}`: {sorted(outputs)}. "
            "The resolved set is one value; reading several leaves it unclear which one "
            "the rows come from",
        )
        # The locator would otherwise find the resolution of the merge's
        # AFFECTED set, which is the set this revisit replaces and which every
        # assertion below would then report on -- passing or failing over a job
        # that resolves something else entirely.
        self.assertNotIn(
            name,
            self.planning,
            f"the apply matrix is supplied by `{name}`, which itself runs `terraform "
            "plan`. A matrix job's outputs are written by every row into one namespace, "
            "so a plan matrix cannot publish which of its rows succeeded",
        )
        self.assertTrue(
            transitive_needs(self.workflow, name) & set(self.planning),
            f"`{name}` supplies the apply matrix but does not depend, directly or "
            f"transitively, on any job that plans (it needs "
            f"{needs_of(jobs(self.workflow)[name])}). A set resolved before the plan "
            "stage ran is the merge's affected set, not the set of environments that "
            "produced a saved plan, and an environment whose plan then failed would "
            "have its Environment approval requested with nothing to approve",
        )
        return name, jobs(self.workflow)[name], outputs.pop()


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Gated Production Apply Applies the Reviewed Plan
# (MODIFIED — the sentences this revisit added)
# --------------------------------------------------------------------------


class TestTheApplyStageRunsOverThePlanned(ApplyWorkflowMixin, unittest.TestCase):
    """MODIFIED requirement: Gated Production Apply Applies the Reviewed Plan.

    "An environment SHALL be applied only where its own plan was produced, and
    an environment whose plan failed SHALL NOT prevent any other environment
    from being applied."

    The two failures that sentence stands between are opposite, so each
    assertion below names which one it holds off. Nothing here reads the apply
    stage's behaviour on a real run; what it reads is the wiring, which is the
    only part of it a committed file states.
    """

    def test_the_apply_matrix_reads_a_set_resolved_after_the_plan_stage(self) -> None:
        """SPECIFIED -- "The set of environments to apply SHALL instead be
        resolved from which environments actually produced a saved plan", and
        scenario "One environment's failed plan does not block another's
        apply".

        A resolution made BEFORE the plans ran can only be the merge's affected
        set, which is the set this sentence replaces: it contains an environment
        whose plan then failed, and applying it raises that environment's
        approval request with nothing to approve.
        """
        self._resolver()

    def test_the_resolution_runs_outside_any_github_environment(self) -> None:
        """SPECIFIED -- "That resolution SHALL run outside any GitHub
        Environment, since it decides which Environments the run will ask for
        and so cannot be gated on one of them"."""
        name, job, _ = self._resolver()
        self.assertIsNone(
            declared_environment(job),
            f"`{name}` resolves which environments will be applied and declares "
            f"`environment: {declared_environment(job)!r}`. It would then be gated on "
            "one of the very Environments it exists to choose between, so an "
            "environment could not be applied until an approval had been granted for "
            "deciding whether to ask for it",
        )

    def test_the_resolution_runs_even_when_an_environments_plan_failed(self) -> None:
        """SPECIFIED -- scenario "One environment's failed plan does not block
        another's apply", read at the resolver: a `needs:` edge implies
        `success()` over every dependency, so a resolver carrying no condition
        of its own is skipped the moment any plan row fails -- and the apply
        stage is then skipped behind it, which is the coupling this revisit
        exists to remove."""
        name, job, _ = self._resolver()
        condition = condition_of(job)
        self.assertTrue(
            condition,
            f"`{name}` declares no `if:`, so the implicit `success()` over its "
            f"`needs:` ({needs_of(job)}) skips it whenever any environment's plan row "
            "failed. Every environment that DID plan is then not applied either, which "
            "is the defect this requirement's amendment removes",
        )
        self.assertTrue(
            any(spelling in condition for spelling in SURVIVES_A_FAILED_DEPENDENCY),
            f"`{name}`'s condition is {condition!r}, which carries neither `always()` "
            "nor `!cancelled()`. Without one of them the implicit `success()` over its "
            "`needs:` still applies and one environment's failed plan still stops every "
            "other environment being applied",
        )

    def test_no_apply_jobs_condition_resolves_through_the_plan_stages_result(self) -> None:
        """SPECIFIED -- "The apply stage SHALL NOT reach its conclusion through
        the plan stage's aggregate result. A dependency whose outcome propagates
        the plan stage's result reinstates exactly the coupling this obligation
        removes, and does so while every other part of the mechanism appears
        correct -- the resolution runs, the set is right, and the apply stage is
        skipped anyway."""
        self._require_both_stages()
        offenders = []
        for name, job in sorted(self.applying.items()):
            condition = condition_of(job)
            if not condition:
                offenders.append(
                    f"{name}: declares no `if:`, so the implicit `success()` over its "
                    f"`needs:` ({needs_of(job)}) skips it whenever the plan stage's "
                    "aggregate result is `failure`"
                )
                continue
            through_plan = sorted(
                {
                    job_name
                    for job_name, _ in NEEDS_RESULT.findall(condition)
                    if job_name in self.planning
                }
            )
            if through_plan:
                offenders.append(
                    f"{name}: its condition {condition!r} reads the result of "
                    f"{through_plan}, which is the plan stage's aggregate result. "
                    "`needs:` is scoped to a job and not to a matrix row, so that "
                    "result is `failure` when any one environment failed to plan"
                )
            if not any(spelling in condition for spelling in SURVIVES_A_FAILED_DEPENDENCY):
                offenders.append(
                    f"{name}: its condition {condition!r} carries neither `always()` "
                    "nor `!cancelled()`, so the implicit `success()` over its `needs:` "
                    "is still in force and the condition changes nothing"
                )
        self.assertEqual([], offenders, "; ".join(offenders))

    def test_each_apply_jobs_condition_requires_the_resolution_to_have_succeeded(self) -> None:
        """DERIVED (that change's design.md decision 8 and tasks.md 4.3c) -- no
        scenario states it in this form. The delta requires the run to FAIL where
        the planned set cannot be resolved; an apply stage admitted by
        `!cancelled()` alone would start on a resolution that refused, with a
        matrix built from whatever the failed step left behind.

        Reconsider this assertion, do not weaken it, if the apply stage is made
        to depend on the resolution's success by another mechanism that a
        committed file states.
        """
        resolver, _, _ = self._resolver()
        offenders = []
        for name, job in sorted(self.applying.items()):
            condition = condition_of(job)
            if not any(
                job_name == resolver for job_name, _ in NEEDS_RESULT.findall(condition)
            ):
                offenders.append(f"{name}: `if: {condition}`")
        self.assertEqual(
            [],
            offenders,
            f"these apply jobs do not require `{resolver}` -- the job resolving which "
            "environments produced a saved plan -- to have succeeded before they run, "
            "so a refused resolution is followed by an apply stage built from nothing: "
            f"{offenders}",
        )

    def test_each_apply_job_keeps_its_plan_job_in_needs(self) -> None:
        """SPECIFIED -- "An **apply job** that depends on the plan job", carried
        through this revisit unchanged and now load-bearing for a second reason:
        dropping the edge in favour of depending on the resolution alone takes
        `needs.<plan>.outputs` out of scope, and the omitted-write-token guard
        of *Credential Scoping by Privilege* then compares against an empty
        string and passes -- in exactly the configuration it exists to catch.

        `test_environment_agnostic_pipeline.TestEveryApplyIsGatedAndPerEnvironment
        .test_each_apply_job_depends_on_a_job_that_plans` asserts the same edge
        and is NOT superseded by this revisit: the shape keeps it green. This is
        stated rather than left to be noticed, because a reader meeting two
        assertions of one edge should know neither is stale.
        """
        self._require_both_stages()
        offenders = [
            f"{name}: needs {needs_of(job)}"
            for name, job in sorted(self.applying.items())
            if not (set(needs_of(job)) & set(self.planning))
        ]
        self.assertEqual(
            [],
            offenders,
            "these apply jobs name no planning job in `needs:`, so `needs.<plan>.outputs` "
            f"is out of scope for every step of theirs that reads it: {offenders}",
        )

    def test_the_write_token_guard_reads_an_output_its_plan_job_publishes(self) -> None:
        """SPECIFIED -- *Credential Scoping by Privilege*, scenario "An
        Environment omitting the write token does not apply with another's",
        read as the amendment leaves it: the guard's operand is an output of the
        plan job, so the `needs:` edge above is what keeps it resolvable.

        Asserting the edge alone is not this property. A guard whose step still
        references `needs.<plan>.outputs.<x>` while the plan job publishes no
        such output resolves to an empty string, compares two empty strings and
        passes -- silently disarmed by an edit no other check here sees.
        """
        self._require_both_stages()
        offenders = []
        for name, job in sorted(self.applying.items()):
            depended = set(needs_of(job)) & set(self.planning)
            body = compact(yaml.safe_dump(job, sort_keys=True))
            read = [
                (source, output)
                for source, output in NEEDS_OUTPUT.findall(body)
                if source in depended
            ]
            if not read:
                offenders.append(
                    f"{name}: no step of it reads any output of the plan job it depends "
                    f"on ({sorted(depended)}), so nothing establishes that it resolved "
                    "its own write token rather than the repository-scoped read-only one"
                )
                continue
            for source, output in read:
                published = (jobs(self.workflow).get(source) or {}).get("outputs") or {}
                if output not in published:
                    offenders.append(
                        f"{name}: reads `needs.{source}.outputs.{output}`, which "
                        f"`{source}` does not publish (it publishes {sorted(published)}). "
                        "The reference resolves to the empty string, so the guard "
                        "compares two empty values and passes"
                    )
        self.assertEqual([], offenders, "; ".join(offenders))

    def test_the_resolution_reads_artifact_names_and_downloads_no_saved_plan(self) -> None:
        """SPECIFIED -- "Because a saved plan file stores sensitive values in
        cleartext, the `tfplan` artifact SHALL be treated as a secret". The
        resolution needs to know WHICH plans exist, which is a fact about their
        names; downloading them to find out puts every environment's plan, in
        cleartext, into a job that has no use for their contents."""
        name, job, _ = self._resolver()
        offenders = [
            step_label(name, index, step)
            for index, step in enumerate(job.get("steps") or [])
            if DOWNLOAD_ACTION in str(step.get("uses", ""))
        ]
        self.assertEqual(
            [],
            offenders,
            f"`{name}` resolves which environments produced a plan by downloading the "
            f"plans themselves: {offenders}. Their names are the fact it needs",
        )


class PlannedSetHarnessMixin(ApplyWorkflowMixin):
    """Locating and executing the planned-set resolution body.

    A mixin rather than a base test case, which is this repository's own idiom
    (`DeclarationTreeFixtureMixin`, and `ApplyWorkflowMixin` above): a second
    test class inheriting a `TestCase` would re-run every assertion of the first
    under a second name, reporting one property twice and doubling the cost of
    every execution in it.
    """

    def setUp(self) -> None:
        super().setUp()
        require_external_tools(
            self, ("bash", "jq"), "execute the planned-environment resolution body"
        )

    # -- locating -----------------------------------------------------------

    def _body(self):
        """(job name, step index, step) of the step the resolver job publishes."""
        name, job, output = self._resolver()
        published = compact((job.get("outputs") or {}).get(output, ""))
        self.assertTrue(
            published,
            f"the apply matrix reads `needs.{name}.outputs.{output}`, but `{name}` "
            f"publishes {sorted((job.get('outputs') or {}))}. The matrix would be built "
            "from an empty string",
        )
        identifiers = {step_id for step_id, _ in STEPS_OUTPUT.findall(published)}
        self.assertEqual(
            1,
            len(identifiers),
            f"`{name}`'s output `{output}` is {published!r}, which names "
            f"{sorted(identifiers)} steps. Exactly one step writes the resolved set; "
            "this test executes that step",
        )
        wanted = identifiers.pop()
        for index, step in enumerate(job.get("steps") or []):
            if str(step.get("id", "")) == wanted:
                self.assertTrue(
                    step.get("run"),
                    f"{step_label(name, index, step)} publishes the resolved set but "
                    "runs no shell body, so it cannot be executed standalone",
                )
                self.assertIsNone(
                    EXPRESSION.search(str(step["run"])),
                    f"{step_label(name, index, step)} carries a `${{{{ }}}}` in its "
                    "body. An expression is interpolated before the step runs, so a "
                    "body carrying one cannot be pulled out of the workflow and "
                    "executed -- the constraint every other fail-closed body in these "
                    "workflows observes, and the reason their tests can exist "
                    "(tasks.md 3.4, 4.3b)",
                )
                return name, index, step
        self.fail(
            f"`{name}` publishes the resolved set from a step with id {wanted!r}, and "
            "declares no step with that id"
        )

    def _artifact_template(self) -> str:
        """The name the plan job gives its saved plan, as a template.

        Taken from the workflow rather than invented, because the resolution
        matches artifact names against environments and only the workflow says
        how those names are spelled.
        """
        templates = set()
        for name, job in sorted(self.planning.items()):
            for index, step in enumerate(job.get("steps") or []):
                if UPLOAD_ACTION in str(step.get("uses", "")):
                    templates.add(str((step.get("with") or {}).get("name", "")))
        self.assertEqual(
            1,
            len(templates),
            f"expected the plan job(s) of apply.yml to upload their saved plan under "
            f"one name template, found {sorted(templates)}",
        )
        return templates.pop()

    def _render(self, template: str, row: dict) -> str:
        unresolved = []

        def substitute(match):
            expression = compact(match.group(1))
            # Both shapes a JSON array of rows can be given to a matrix: one
            # dimension per field (`matrix.name`), or one dimension holding the
            # whole row (`matrix.<dimension>.name`). The dimension's name is the
            # implementation's to choose, so it is never assumed -- the LAST
            # segment is the row's field either way.
            field = re.fullmatch(r"matrix((?:\.[A-Za-z0-9_-]+){1,2})", expression)
            if field:
                leaf = field.group(1).lstrip(".").split(".")[-1]
                if leaf not in row:
                    unresolved.append(expression)
                    return ""
                return str(row[leaf])
            if expression in RUN_CONTEXT:
                return RUN_CONTEXT[expression]
            unresolved.append(expression)
            return ""

        rendered = EXPRESSION.sub(substitute, template)
        self.assertEqual(
            [],
            unresolved,
            f"the saved plan's artifact name {template!r} is built from {unresolved}, "
            "which is neither a value of the matrix row nor a fact about this run that "
            "the resolution has through `env:`. The resolution reads artifact names to "
            "decide which environments produced a plan, so a name it cannot reconstruct "
            "per environment is a name it cannot match. Reconsider this assertion, do "
            "not weaken it, if the resolution learns to identify an environment's plan "
            "by something other than its artifact name",
        )
        return rendered

    # -- executing ----------------------------------------------------------

    def _inputs(self, step: dict, job: dict, rows: list, listing: str):
        """Every `env:` value the step sees, filled from the expression it
        carries rather than from the name it was given."""
        declared = {}
        declared.update((job.get("env") or {}))
        declared.update((step.get("env") or {}))
        assignments = {}
        unclassified = []
        for key, value in declared.items():
            expression = compact(value)
            if not EXPRESSION.search(str(value)):
                assignments[key] = str(value)
            elif compact(EXPRESSION.sub(r"\1", str(value))) in RUN_CONTEXT:
                # Every fact about the run this module already knows how to
                # supply, resolved from one table rather than from a chain of
                # names. `_render` reads the same table, so a run-context value
                # the artifact name may be built from is by construction one this
                # body may take through `env:` -- which is the property that let
                # `github.run_attempt` sit in the table and be unclassifiable
                # here at the same time.
                assignments[key] = RUN_CONTEXT[compact(EXPRESSION.sub(r"\1", str(value)))]
            elif "github.run_id" in expression:
                assignments[key] = RUN_ID
            elif "github.repository" in expression:
                assignments[key] = REPOSITORY
            elif "github.sha" in expression:
                assignments[key] = SHA
            elif "secrets." in expression or "github.token" in expression.lower():
                assignments[key] = "stub-token-never-sent-anywhere"
            elif STEPS_OUTPUT.search(expression):
                assignments[key] = listing
            elif NEEDS_OUTPUT.search(expression):
                assignments[key] = json.dumps(rows)
            else:
                unclassified.append(f"{key}: {expression}")
                assignments[key] = ""
        return assignments, unclassified

    def _run(self, rows, artifacts, gh_exit: int = 0, blank: bool = False, body=None):
        name, index, step = self._body()
        job = jobs(self.workflow)[name]
        listing = (
            body
            if body is not None
            else json.dumps({"total_count": len(artifacts), "artifacts": artifacts})
        )
        assignments, unclassified = self._inputs(step, job, rows, listing)
        if not blank:
            self.assertEqual(
                [],
                unclassified,
                f"{step_label(name, index, step)} takes inputs this test cannot supply "
                f"a value for, because it cannot tell what they are: {unclassified}. "
                "Every input of this body arrives through `env:` so that it can be run "
                "standalone (tasks.md 4.3b); an input whose provenance is not the run "
                "id, the repository, a credential, another step's output or the set of "
                "candidate environments is one this test would be guessing at",
            )

        scratch = Path(tempfile.mkdtemp(prefix="planned-environments-"))
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        (scratch / "terraform" / "environments").mkdir(parents=True)
        binaries = scratch / "bin"
        binaries.mkdir()
        stub = binaries / "gh"
        stub.write_text(GH_STUB, encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        fixture = scratch / "artifacts.json"
        fixture.write_text(listing, encoding="utf-8")
        outputs = scratch / "github_output"
        summary = scratch / "step_summary"
        outputs.touch()
        summary.touch()

        environment = dict(
            os.environ,
            PATH=os.pathsep.join([str(binaries), os.environ.get("PATH", "")]),
            GITHUB_OUTPUT=str(outputs),
            GITHUB_ENV=str(outputs),
            GITHUB_STEP_SUMMARY=str(summary),
            GITHUB_WORKSPACE=str(scratch),
            STUB_GH_BODY=str(fixture),
            STUB_GH_EXIT=str(gh_exit),
        )
        for key in assignments:
            environment[key] = "" if blank else assignments[key]
        result = run_snippet(str(step["run"]), environment, scratch)
        return result, github_output_pairs(outputs)

    def _resolved_names(self, written: dict, detail: str):
        emitted = []
        for key, value in sorted(written.items()):
            text = str(value).strip()
            if not text.startswith("["):
                continue
            try:
                document = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(document, list):
                emitted.append((key, document))
        self.assertEqual(
            1,
            len(emitted),
            "expected the resolution to write exactly one JSON list naming the "
            f"environments that produced a saved plan, and it wrote {written!r}. {detail}",
        )
        _, document = emitted[0]
        return sorted(
            str(entry.get("name", entry)) if isinstance(entry, dict) else str(entry)
            for entry in document
        )

    def _artifacts_for(self, rows):
        template = self._artifact_template()
        return [
            {"name": self._render(template, row), "expired": False, "id": index + 1}
            for index, row in enumerate(rows)
        ]


class TestThePlannedSetResolutionIsRunRatherThanRead(
    PlannedSetHarnessMixin, unittest.TestCase
):
    """MODIFIED requirement: Gated Production Apply Applies the Reviewed Plan --
    the fail-closed shape of the planned-set resolution, executed.

    Reading establishes that a resolution exists; running establishes that it
    DISCRIMINATES. The distinction is the whole of the fail-closed argument
    here, and the delta draws it explicitly: an input that resolves to "no
    environment planned" is accepted, an input that cannot be resolved at all is
    refused. A body refusing both would satisfy the refusal below and apply
    nothing, ever; a body accepting both would report a green apply workflow for
    a run whose resolution never concluded.

    The body is located through the workflow's own wiring -- the apply matrix
    names the resolver job's output, the job's `outputs:` names the step that
    wrote it -- so no step name is assumed. The four inputs are told apart by
    the EXPRESSION each `env:` value carries, never by the variable's name.
    """

    # -- the four inputs ----------------------------------------------------

    def test_every_environment_that_produced_a_plan_is_in_the_resolved_set(self) -> None:
        """SPECIFIED -- "An environment SHALL be applied only where its own plan
        was produced", read forward. The converse every refusal below needs: a
        resolution that emitted nothing would satisfy all of them and apply
        nothing, ever."""
        rows = [PROD_ROW, STAGING_ROW]
        result, written = self._run(rows, self._artifacts_for(rows))
        detail = (result.stdout + result.stderr).strip()[-600:]
        self.assertEqual(
            0, result.returncode, f"the resolution refused a run every plan of which "
            f"produced a saved plan: {detail!r}"
        )
        self.assertEqual(
            ["prod", "staging"],
            self._resolved_names(written, detail),
            "an environment that produced a saved plan was left out of the set, so a "
            "reviewed change would never be applied",
        )

    def test_an_environment_whose_plan_failed_is_absent_and_the_others_remain(self) -> None:
        """SPECIFIED -- scenario "One environment's failed plan does not block
        another's apply": "the other environment SHALL still be applied under
        its own GitHub Environment's protection rules, and no approval SHALL be
        requested for the environment whose plan failed".

        The environment whose plan failed published no artifact -- the upload is
        the last step of the plan job and carries no condition, so a row that
        failed for any reason never reached it. Both halves of the scenario are
        one assertion here: the surviving environment is present, and the failed
        one is absent.
        """
        rows = [PROD_ROW, STAGING_ROW]
        result, written = self._run(rows, self._artifacts_for([PROD_ROW]))
        detail = (result.stdout + result.stderr).strip()[-600:]
        self.assertEqual(
            0,
            result.returncode,
            "the resolution refused a run in which one environment planned and another "
            f"did not, so the environment that DID plan is not applied: {detail!r}",
        )
        self.assertEqual(
            ["prod"],
            self._resolved_names(written, detail),
            "the resolved set is not exactly the environments that produced a saved "
            "plan. An environment missing from it is a correct change that never "
            "reaches its cloud; an environment present in it without a plan raises its "
            "Environment's approval request with nothing to approve",
        )

    def test_an_explicitly_empty_planned_set_is_accepted(self) -> None:
        """SPECIFIED -- "An **explicitly empty** planned set is not that case and
        SHALL NOT fail the run -- a merge matching this workflow's path filter
        while affecting no environment reaches the apply stage with nothing to
        apply, and that is the correct outcome rather than an error"."""
        rows = [PROD_ROW, STAGING_ROW]
        result, written = self._run(rows, [])
        detail = (result.stdout + result.stderr).strip()[-600:]
        self.assertEqual(
            0,
            result.returncode,
            "the resolution failed the run over an explicitly empty set of saved plans. "
            "A merge matching apply.yml's path filter while affecting no environment "
            f"reaches this stage with nothing to apply, and is then red: {detail!r}",
        )
        self.assertEqual(
            [],
            self._resolved_names(written, detail),
            "the resolution accepted an empty set of saved plans and then named "
            "environments to apply anyway",
        )

    def test_a_resolution_that_could_not_read_the_run_fails_it(self) -> None:
        """SPECIFIED -- scenario "An unresolvable set of planned environments
        fails the run": "the workflow SHALL fail with a message identifying that
        resolution as the cause, and SHALL NOT proceed as though no environment
        had been planned".

        Two shapes, and both are needed. Emptying every input is what a step
        that did not conclude leaves behind; a read that refuses on inputs which
        are otherwise valid is an expired credential or an API returning 502,
        and it is the one a body guarding only its inputs passes. Reading either
        as "nothing was planned" applies nothing for a merge that did change
        infrastructure and reports a green run, and the next thing to notice
        would be the nightly drift sweep.
        """
        rows = [PROD_ROW, STAGING_ROW]
        for label, arguments in (
            ("every input empty and the read refusing", {"blank": True}),
            ("valid inputs and the read refusing", {"blank": False}),
        ):
            with self.subTest(unresolvable=label):
                result, written = self._run(rows, [], gh_exit=1, **arguments)
                detail = (result.stdout + result.stderr).strip()[-600:]
                self.assertNotEqual(
                    0,
                    result.returncode,
                    f"the resolution concluded successfully with {label}, and wrote "
                    f"{written!r}: {detail!r}",
                )

    def test_a_listing_that_is_not_a_valid_set_fails_rather_than_emptying(self) -> None:
        """SPECIFIED -- the same scenario at its other input: a read that
        SUCCEEDED and returned something that is not a set. "Where the set can
        be neither read as a valid set nor read as an explicit empty one, the
        workflow SHALL fail with a message identifying that resolution as the
        cause."

        This is the case a `set -e` alone does not catch: a body piping a
        malformed document into a parser inside a pipeline sees the pipeline's
        last exit status, not the parser's, and carries on with an empty result.
        """
        rows = [PROD_ROW, STAGING_ROW]
        result, written = self._run(
            rows, [], body="<html><head><title>502 Bad Gateway</title></head></html>"
        )
        detail = (result.stdout + result.stderr).strip()[-600:]
        self.assertNotEqual(
            0,
            result.returncode,
            "the resolution accepted a listing of this run's artifacts that is not a "
            f"set at all, and concluded: {written!r} / {detail!r}",
        )


class TestASavedPlanIsPublishedOnlyAfterItsOwnChecksPassed(
    ApplyWorkflowMixin, unittest.TestCase
):
    """MODIFIED requirement: Gated Production Apply Applies the Reviewed Plan --
    "An environment counts as having produced a saved plan only where every
    check its plan job performs has passed."

    Scenario: "A plan its own gate refused is not applied".

    The saved plan's EXISTENCE is not that fact. The Destroy Policy Gate runs
    inside the plan job and after the plan exists, so a plan the gate refused is
    a plan that was produced; where the resolution above reads an artifact, the
    artifact is what has to carry the fact instead. Three ways an implementation
    can publish a refused plan while every other assertion in this file passes,
    and one test each: publishing before the gate, publishing conditionally on
    having reached it, and letting the gate fail without failing the job.
    """

    def _plan_uploads(self):
        self.assertTrue(self.planning, "no job in apply.yml runs `terraform plan`")
        found = []
        for name, job in sorted(self.planning.items()):
            declared = job.get("steps") or []
            uploads = [
                (index, step)
                for index, step in enumerate(declared)
                if UPLOAD_ACTION in str(step.get("uses", ""))
            ]
            self.assertEqual(
                1,
                len(uploads),
                f"the plan job `{name}` publishes its saved plan in {len(uploads)} "
                "steps. The apply stage resolves which environments to apply from which "
                "plans were published, so exactly one step decides that per environment",
            )
            found.append((name, job, declared, uploads[0]))
        return found

    def test_no_step_of_the_plan_job_runs_after_the_saved_plan_is_published(self) -> None:
        """SPECIFIED -- "Where the resolution is made by observing an artifact,
        the artifact SHALL therefore be published only after every such check
        has passed".

        A check placed after the upload is a check whose refusal comes too late:
        the artifact is already there, the resolution already counts that
        environment as planned, and the apply proceeds behind an approval the
        gate exists because it does not trust.
        """
        offenders = []
        for name, job, declared, (index, step) in self._plan_uploads():
            trailing = [
                step_label(name, position, later)
                for position, later in enumerate(declared)
                if position > index
            ]
            if trailing:
                offenders.append(
                    f"{name}: {step_label(name, index, step)} publishes the saved plan, "
                    f"and these steps run after it: {trailing}"
                )
        self.assertEqual([], offenders, "; ".join(offenders))

    def test_the_publication_of_a_saved_plan_carries_no_condition(self) -> None:
        """SPECIFIED -- "and unconditionally on their having passed -- never on
        the plan job having merely reached that point".

        `if: always()` and `if: success() || failure()` are the two spellings
        that turn correct ordering into no gate at all: the gate fails, the
        upload runs anyway, the plan is resolved as produced. Asserting the KEY
        IS ABSENT rather than that its value is truthy is deliberate -- an
        expression-valued condition reads as a harmless string here and is
        decided on the runner.
        """
        offenders = [
            f"{step_label(name, index, step)}: if: {step['if']!r}"
            for name, _, _, (index, step) in self._plan_uploads()
            if "if" in step
        ]
        self.assertEqual(
            [],
            offenders,
            "these steps publish a saved plan under a condition of their own, so what "
            "the run concluded about the plan's own checks is not what decides whether "
            f"the plan is published: {offenders}",
        )

    def test_neither_the_plan_job_nor_any_step_of_it_can_suppress_a_failure(self) -> None:
        """SPECIFIED -- the same sentence read at its suppression sibling. A
        `continue-on-error` on the destroy-policy gate lets a refused plan reach
        an upload that is correctly ordered and correctly unconditional: every
        other assertion in this class passes, and the gate is defeated anyway --
        an environment then counts as having produced a saved plan where a check
        its plan job performed did NOT pass.

        The closed form this capability already holds its own record-validation
        step to: the key must be ABSENT, in any form, including one whose value
        is an expression.
        """
        offenders = []
        for name, job in sorted(self.planning.items()):
            if "continue-on-error" in job:
                offenders.append(f"{name}: continue-on-error: {job['continue-on-error']!r}")
            for index, step in enumerate(job.get("steps") or []):
                if "continue-on-error" in step:
                    offenders.append(
                        f"{step_label(name, index, step)}: continue-on-error: "
                        f"{step['continue-on-error']!r}"
                    )
        self.assertEqual(
            [],
            offenders,
            "a failing check in the plan job can be suppressed here, so the plan is "
            "published and applied with that check's refusal recorded as a green run: "
            f"{offenders}",
        )

    def test_the_destroy_policy_gate_carries_no_condition_but_its_applicability(self) -> None:
        """DERIVED (that change's tasks.md 4.3d) -- no scenario states it. The
        delta obliges the artifact to be published only after every check has
        passed; a check conditioned away is a check that did not run, and the
        artifact is then published after nothing.

        The ONE condition admitted is a bare reference to the environment's own
        declared applicability -- `if: matrix.<field>` in either spelling and
        containing nothing else -- because the gate is per-environment policy
        (*Destroy Policy Gate*: "Whether this gate applies is a per-environment
        policy") and skipping it for an environment that declared it
        inapplicable is the requirement working. Anything else, `if: false` and
        `if: always()` alike, is refused.

        Reconsider this assertion, do not weaken it, if applicability comes to
        reach the gate some other way -- it is asserted here in the shape
        tasks.md 4.3d names, and the narrowing to the applicability reference is
        this pass's, recorded in that change's test-plan.md.
        """
        # One or two segments, for the same reason `_render` accepts both: a
        # JSON array of rows reaches a matrix either as one dimension per field
        # or as one dimension holding the whole row.
        admitted = re.compile(r"\A(?:\$\{\{)?matrix(?:\.[A-Za-z0-9_-]+){1,2}(?:\}\})?\Z")
        gates = [
            (name, index, step)
            for name, index, step in steps(self.workflow)
            if "resource_changes" in str(step.get("run", ""))
        ]
        self.assertTrue(
            gates,
            "no step in apply.yml inspects a plan's `resource_changes`, so the plan "
            "whose publication this class guards passes through no gate at all",
        )
        offenders = [
            f"{step_label(name, index, step)}: if: {compact(step['if'])}"
            for name, index, step in gates
            if "if" in step and not admitted.match(compact(step["if"]))
        ]
        self.assertEqual(
            [],
            offenders,
            "these destroy-policy gate steps carry a condition that is not a plain "
            "reference to the environment's declared applicability, so whether the gate "
            f"runs at all is decided by something other than that declaration: {offenders}",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Serialized Terraform Runs (MODIFIED — the sentence this
# revisit added)
# --------------------------------------------------------------------------


class TestThePlanAndApplyGroupsAreSeparate(ApplyWorkflowMixin, unittest.TestCase):
    """MODIFIED requirement: Serialized Terraform Runs -- "**Within the apply
    workflow, its plan job and its apply job SHALL NOT share a group.**"

    Scenario: "A queued plan does not cancel an apply awaiting approval".

    `test_environment_agnostic_pipeline.TestConcurrencyIsDeclaredPerEnvironment`
    asserts that each of these jobs declares a group of its own, derived from
    the matrix, with `cancel-in-progress: false`. Neither of its assertions is
    superseded by this revisit and neither is restated here: a plan job and an
    apply job sharing ONE such group satisfies both, which is exactly the
    configuration this sentence was added to forbid.
    """

    def _group_of(self, name: str) -> str:
        group = concurrency_group(jobs(self.workflow).get(name))
        self.assertTrue(
            group,
            f"`{name}` declares no job-level `concurrency` group in apply.yml, so this "
            "assertion has nothing to compare",
        )
        return group

    def test_no_plan_job_shares_a_concurrency_group_with_an_apply_job(self) -> None:
        """SPECIFIED -- the added sentence, and the scenario it carries: "the
        queued plan SHALL NOT cancel or displace the waiting apply, because the
        two do not share a concurrency group".

        Compared with every `${{ }}` collapsed to one placeholder, which is what
        "for any environment name" means as a static read: two groups differing
        only in which expression they interpolate hold the same value for some
        environment, and the loss they admit is silent -- a cancellation is not
        a failure, and nothing in this repository reads one.
        """
        self._require_both_stages()
        offenders = []
        for plan in sorted(self.planning):
            for apply in sorted(self.applying):
                first, second = self._group_of(plan), self._group_of(apply)
                if collapsed(first) == collapsed(second):
                    offenders.append(
                        f"{plan} ({first}) and {apply} ({second}) resolve to the same "
                        f"group for any environment: {collapsed(first)}"
                    )
        self.assertEqual(
            [],
            offenders,
            "these plan and apply jobs share a concurrency group, so a later merge's "
            "queued plan can cancel an apply that is waiting for its Environment's "
            f"reviewer -- as a cancellation rather than a failure: {offenders}",
        )

    def test_no_plan_outside_the_apply_workflow_joins_either_group(self) -> None:
        """SPECIFIED -- "This sentence is about that workflow alone; a plan run
        on a pull request or on the drift schedule is not serialized by this
        requirement at all, and SHALL NOT be placed in either group -- the
        nightly drift plan in particular runs with `-lock=false` precisely so
        that it contends with nothing".

        A pull-request plan placed in the apply group would queue behind a
        production apply awaiting its reviewer; a drift plan placed there would
        do the same nightly, and `-lock=false` -- which
        `test_environment_agnostic_pipeline.TestDriftDetectionIsPerEnvironment
        .test_the_drift_plan_does_not_take_the_state_lock` asserts -- would buy
        nothing, since the contention would no longer be over the state lock.
        """
        self._require_both_stages()
        forbidden = {
            collapsed(self._group_of(name))
            for name in sorted(set(self.planning) | set(self.applying))
        }
        offenders = []
        for path in (PR_VALIDATION, DRIFT):
            workflow = load_yaml(path)
            declared = [("<workflow>", concurrency_group(workflow))]
            declared.extend(
                (name, concurrency_group(job)) for name, job in sorted(jobs(workflow).items())
            )
            for name, group in declared:
                if group and collapsed(group) in forbidden:
                    offenders.append(f"{path.name}: {name} declares `{group}`")
        self.assertEqual(
            [],
            offenders,
            "these declarations put a plan that this requirement does not serialize "
            "into one of the apply workflow's per-environment groups, where it queues "
            f"behind -- or cancels -- an apply: {offenders}",
        )


class TestThePlannedSetIsNeverResolvedFromAPartialListing(
    PlannedSetHarnessMixin, unittest.TestCase
):
    """MODIFIED requirement: Gated Production Apply Applies the Reviewed Plan --
    "Where the set can be neither read as a valid set nor read as an explicit
    empty one, the workflow SHALL fail with a message identifying that
    resolution as the cause."

    DERIVED, and added by the IMPLEMENTING author rather than by the author of
    the module above: no scenario names either shape, and both became reachable
    only once the resolution was built on a paginated API.

    They are here rather than in a scratch run for the reason this change gives
    everywhere else — a fail-closed path guarded by a check nobody runs again is
    guarded by nothing. Both were confirmed to fail the resolution before being
    written down.

    Takes the harness from `PlannedSetHarnessMixin` rather than from the test
    class above it, so the assertions there run once rather than twice under two
    names. That mixin was extracted for this, which is the idiom
    `DeclarationTreeFixtureMixin` and `ApplyWorkflowMixin` already set here.
    """

    def test_a_listing_carrying_no_artifacts_at_all_fails_rather_than_emptying(self) -> None:
        """DERIVED -- a document that PARSES and is not a listing. A filter
        tolerant of the missing key evaluates it to an empty set and reports it
        as read-and-empty, which is indistinguishable from the run genuinely
        having planned nothing — and that is the reading the delta refuses. The
        destroy-policy gate asserts `format_version` on a plan for exactly this
        reason; this is the same assertion one level up."""
        rows = [PROD_ROW, STAGING_ROW]
        result, written = self._run(rows, [], body=json.dumps({"total_count": 0}))
        self.assertNotEqual(
            0,
            result.returncode,
            "the resolution accepted a document carrying no artifact listing at all "
            f"and concluded that no environment produced a plan: {written!r} / "
            f"{(result.stdout + result.stderr).strip()[-600:]!r}",
        )

    def test_a_truncated_listing_fails_rather_than_dropping_environments(self) -> None:
        """DERIVED -- the one shape of this failure that is SILENT. A listing
        page holding fewer artifacts than the run has drops environments from
        the planned set, and a dropped environment is not an error anywhere: it
        is a reviewed, approved change that simply never reaches its cloud, with
        the run green. Reconsider this assertion, do not weaken it, if the
        resolution learns to page through the listing instead."""
        rows = [PROD_ROW, STAGING_ROW]
        artifacts = self._artifacts_for([PROD_ROW])
        result, written = self._run(
            rows,
            artifacts,
            body=json.dumps({"total_count": len(artifacts) + 6, "artifacts": artifacts}),
        )
        self.assertNotEqual(
            0,
            result.returncode,
            "the resolution read a listing that reports more artifacts than it returned "
            "and resolved the planned set from it anyway, so an environment whose plan "
            f"succeeded would never be applied: {written!r} / "
            f"{(result.stdout + result.stderr).strip()[-600:]!r}",
        )


if __name__ == "__main__":  # pragma: no cover - convenience only
    unittest.main()
