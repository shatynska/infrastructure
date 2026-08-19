# Test manifest — add-prod-data-volume

Written by the independent test-writer pass, before `modules/volume` is
implemented. Per the `openspec-test-writer` contract, this manifest is
**not** an artifact the OpenSpec schema knows about — it will not appear
among `openspec instructions apply`'s context files and must be read on
purpose before implementing. (It is also pointed to by this library's
`rules/` fragment that directs it be read before implementing; this is the
second, redundant pointer, since that fragment's import path is
machine-local.)

Location: `openspec/changes/add-prod-data-volume/test-manifest.md`.

## What was written

Three new files, all within the dispatched test-path glob
`modules/volume/tests/*.tftest.hcl` (the directory `modules/volume/tests/`
did not exist before this pass):

- `modules/volume/tests/creation.tftest.hcl`
- `modules/volume/tests/labels.tftest.hcl`
- `modules/volume/tests/delete_protection.tftest.hcl`

No other file was written or modified, except this manifest. **Nothing
under `modules/volume/` other than `tests/` was created** — `main.tf`,
`variables.tf`, `outputs.tf`, and `versions.tf` for the module itself do
not exist yet; that is implementation and is explicitly out of scope for
this pass. `environments/prod/*` was not touched.

All three files use `mock_provider "hcloud" {}` and `command = plan` only
— no real Hetzner API call, credential, or infrastructure is touched by
these tests, per the dispatch's explicit instruction. This was verified
live (Terraform v1.9.8, no `experiments` flag needed) against a disposable
reference module built only in the scratchpad, never committed to this
repository — see "Verification performed" below.

Runner-selectable identifiers: `terraform test`'s `-filter` flag selects
by **file**, e.g. `terraform test -filter=tests/creation.tftest.hcl` (run
from `modules/volume/`, or `terraform -chdir=modules/volume test
-filter=tests/creation.tftest.hcl` from the repo root). Individual `run`
block names below (e.g. `plan_creates_volume_with_declared_configuration`)
identify a block in the file's own output but are not independently
selectable via the Terraform 1.9.8 CLI — the whole file runs together.

## Baseline taken

**Scoped baseline**, taken against the newly-created test files themselves
(the only thing in scope for this pass), by running:

```
cd modules/volume && terraform init -backend=false && terraform test
```

Result: **0 passed, 3 failed (file-level), 5 skipped.** All three files
failed with `Error: Reference to undeclared resource — A managed resource
"hcloud_volume" "this" has not been declared in the root module`, on the
first assertion of the first `run` block in each file; every subsequent
`run` block in that file then reported `skip`. This is the expected
pre-implementation state (failure state 2 in the `testing` skill's
vocabulary: "the target does not exist yet" — `modules/volume/main.tf`
does not exist). No test passed on this first run, which is itself
consistent with an absent target (a pass here would have been the alarm
state 4).

No baseline could be taken for `modules/server` or `environments/prod`
against this change's MODIFIED deltas — search and testing were bounded to
the dispatched glob (`modules/volume/tests/*.tftest.hcl`); see "Obsolete
tests" and "Uncovered scenarios" below for what that leaves unaddressed.

## Verification performed (not part of the deliverable)

Before writing the real files, the same `run`/`assert` logic was checked
against a disposable reference implementation built only under this
session's scratchpad directory (never inside this repository), using the
real `hetznercloud/hcloud` provider's schema (queried via `terraform
providers schema -json`) to confirm attribute types. This surfaced one
fact worth recording: **`hcloud_volume.server_id` is typed `number` in the
real provider schema**, not `string`. tasks.md 1.2 describes the module's
own `server_id` variable as `(string, the server to attach to)`. This is
not a defect — Terraform automatically converts a numeric string into the
resource's `number` argument, confirmed live in the scratchpad sandbox —
but the test assertions comparing `hcloud_volume.this.server_id` against
`var.server_id` use `tonumber(var.server_id)` to compare like with like,
since the equality operator itself does not perform that conversion. No
change to tasks.md is being made or requested; this is recorded here for
whoever implements, in case it's a useful cross-check.

The delete_protection parameterization test
(`plan_delete_protection_is_parameterized_not_hardcoded`) was also checked
against a deliberately broken reference (delete_protection hardcoded to
`true`) and correctly failed, confirming it discriminates rather than
trivially passing.

## Scenario accounting

15 `#### Scenario:` blocks total across the three delta spec files. Every
one is accounted for below, exactly once.

### `specs/iac-data-volumes/spec.md` (ADDED capability) — 6 scenarios

| # | Scenario | Status | Test(s) / reason |
|---|---|---|---|
| 1 | Toggle enabled creates the volume | **Covered (partial)** | `creation.tftest.hcl::plan_creates_volume_with_declared_configuration`. Exercises the module's own creation-with-declared-config behavior when invoked with a `server_id`, as a proxy for "both toggles true." Does **not** exercise the `environments/prod`-level `count = var.volume_enabled && var.server_enabled` gate itself — see reason under scenario 2. |
| 2 | Volume toggle disabled creates nothing | **Uncovered** | The count-driven absence is `environments/prod`-level composition (`count = var.volume_enabled && var.server_enabled` in `environments/prod/main.tf`, not yet written). `modules/volume` has no enable/disable toggle of its own — there is no module-level analog of "creates nothing" to assert. Testing this requires either an `environments/prod`-level test, or a harness/setup module wrapping `modules/volume` with the same coupling logic — both outside the dispatched test-path glob (`modules/volume/tests/*.tftest.hcl` only). |
| 3 | Disabling the server also removes the volume | **Uncovered** | Same reason as scenario 2 — this is the same `count` coupling, viewed from the server-toggle side. Duplicated by `iac-server-lifecycle` scenario 14 below. |
| 4 | Re-enabling requires no lost configuration | **Uncovered** | Configuration persistence across a toggle change is an `environments/prod`-variables/tfvars-level property; `modules/volume` itself has no toggle or persistence concept to observe this against. |
| 5 | Volume is created already attached | **Covered (partial)** | `creation.tftest.hcl::plan_attaches_to_server_at_creation` asserts `server_id` is set on the resource at plan time. The scenario's "no separate attachment step required" clause (i.e. no standalone `hcloud_volume_attachment` resource exists) is not independently assertable through `terraform test`'s `assert` DSL — referencing an undeclared resource type there is a compile error, not a boolean check — so that half of the scenario is left to code review, not test coverage. |
| 6 | Volume shares the server's location | **Uncovered** | `location` is Hetzner-computed, derived from the attached server; not knowable at plan time without asserting claims about mock-provider unknown-value semantics for computed-only attributes, which were not verified live in this pass and so were deliberately not relied on (see "Assertions never made" below). Real verification happens at the live-plan review step (tasks.md 3.3) or via apply, neither of which this pass performs. |

### `specs/iac-safety-hardening/spec.md` (MODIFIED capability) — 5 scenarios

| # | Scenario | Status | Test(s) / reason |
|---|---|---|---|
| 7 | Prod server is protected against console deletion | **Uncovered** | Concerns `hcloud_server` / `modules/server`, not `modules/volume`. Out of the dispatched test-path glob. |
| 8 | Prod volume is protected against console deletion | **Covered (proxy)** | `delete_protection.tftest.hcl::plan_delete_protection_true_is_set_on_the_resource`. Asserts the plan-time precondition (`delete_protection = true` reaches the resource). The scenario's actual outcome — Hetzner refusing a console/API deletion — is server-side provider behavior, not observable via `terraform plan` or any test that never touches real infrastructure. |
| 9 | Shared module remains reusable by a future non-prod environment | **Covered (partial)** | `delete_protection.tftest.hcl::plan_delete_protection_is_parameterized_not_hardcoded` proves `delete_protection = false` is reflected on the resource untouched (no override), i.e. the module doesn't hardcode protection. The scenario's full outcome — that `terraform destroy` then actually succeeds, and that no `lifecycle { prevent_destroy = true }` is hardcoded inside the module — is not observable via `command = plan` (`prevent_destroy` only affects destroy/replace operations); left uncovered at this level. |
| 10 | Prod resources are labeled | **Uncovered** | Concerns `hcloud_server`, not `modules/volume`. Out of the dispatched test-path glob. |
| 11 | Prod volume is labeled | **Covered** | `labels.tftest.hcl::plan_applies_environment_and_managed_by_labels`. |

### `specs/iac-server-lifecycle/spec.md` (MODIFIED capability) — 4 scenarios

| # | Scenario | Status | Test(s) / reason |
|---|---|---|---|
| 12 | Toggle enabled creates the server | **Uncovered** | Concerns `hcloud_server`/`hcloud_firewall`, `modules/server`. Out of the dispatched test-path glob. |
| 13 | Toggle disabled creates nothing | **Uncovered** | Same as 12. |
| 14 | Toggle disabled also removes resources coupled to the server | **Uncovered** | Same underlying coupling as scenario 3 (the `environments/prod`-level `count` gate); not testable from within `modules/volume`, which has no knowledge of the server's own toggle. |
| 15 | Re-enabling requires no lost configuration | **Uncovered** | Concerns server sizing/image/location/SSH-key persistence in `environments/prod`/`modules/server`, not `modules/volume`. |

**Count check:** 15 scenarios enumerated, 15 accounted for (5 covered —
1, 5, 8, 9, 11, three of which are explicitly partial/proxy coverage — and
10 uncovered — 2, 3, 4, 6, 7, 10, 12, 13, 14, 15).

## Assertion classification

| Test | Assertion | Classification |
|---|---|---|
| `creation.tftest.hcl::plan_creates_volume_with_declared_configuration` | `name == var.name` | Specified (scenario 1) |
| | `size == var.size` | Specified (scenario 1) |
| `creation.tftest.hcl::plan_attaches_to_server_at_creation` | `server_id == tonumber(var.server_id)` | Specified (scenario 5) |
| `creation.tftest.hcl::plan_requires_non_empty_server_id` | `expect_failures` on empty `server_id` | **Derived** — grounded in design.md Decision 3 ("`server_id` must always be non-null whenever the volume is created"), not delta-spec scenario text. Not itself required by any tasks.md item; a future implementer must add a `nullable = false`/validation constraint (or equivalent) to satisfy it. |
| `labels.tftest.hcl::plan_applies_environment_and_managed_by_labels` | `labels["environment"] == var.environment`, `labels["managed_by"] == "terraform"` | Specified (scenario 11) |
| `labels.tftest.hcl::plan_merges_caller_supplied_labels_without_losing_automatic_ones` | caller label merges in; automatic label survives | **Derived** — inferred from `modules/server`'s existing `locals.labels = merge({...}, var.labels)` pattern, which design.md's Goals section says this module should mirror; not itself scenario text. |
| `delete_protection.tftest.hcl::plan_delete_protection_defaults_to_true` | `delete_protection == true` with no input override | **Derived** — from tasks.md 1.2 ("`delete_protection` (bool, default `true`)"), not delta-spec scenario text. |
| `delete_protection.tftest.hcl::plan_delete_protection_true_is_set_on_the_resource` | `delete_protection == true` when set | Specified (scenario 8), proxy — see scenario table for the limitation. |
| `delete_protection.tftest.hcl::plan_delete_protection_is_parameterized_not_hardcoded` | `delete_protection == false` when set | Specified (scenario 9), proxy — see scenario table for the limitation. |

### Deliberately untested (identified, not asserted)

- **`location` matching the server's location** (scenario 6) — see scenario
  table. Not asserted because the plan-time value of a computed-only
  attribute under a mocked provider was not verified live in this pass,
  and asserting on it without that verification would be an unverified
  claim about mock-provider behavior, not a meaningful test.
- **Absence of a standalone `hcloud_volume_attachment` resource**
  (scenario 5's second half) — not expressible as a boolean `assert`
  condition in `terraform test`'s DSL; left to code/design review.
- **`prevent_destroy` not hardcoded, and an actual `terraform destroy`
  succeeding** (scenario 9's second half) — not observable via
  `command = plan`, which the dispatch scoped this pass to; would require
  a `command = apply`/destroy-cycle test (still against a mocked
  provider, never real infrastructure), which was not written because the
  dispatch's stated scope was plan-only.

## Obsolete tests

**Not empty by default reasoning, but nothing found by a bounded search.**
This change carries two `MODIFIED` deltas (`iac-safety-hardening`,
`iac-server-lifecycle`), so the obsolete-tests question is applicable —
this is not the "no MODIFIED/REMOVED delta" case.

The search was bounded to the dispatched test-path glob,
`modules/volume/tests/*.tftest.hcl`, plus the (absent) earlier
`test-manifest.md` — none was supplied for this dispatch. That directory
did not exist before this pass (confirmed via `ls` before writing
anything). **No bearing test was found, because none existed to find** —
this is "no such test exists" within the searched scope, not merely "none
was found by this search."

This search was **not** extended to `modules/server/tests/` (which does
not currently exist either, per a direct `ls` check) or to any
`environments/prod`-level test location, because both are outside the
dispatched glob. If tests bearing on the MODIFIED requirements' restated
server-side scenarios (7, 9's destroy aspect, 10, 12, 13, 15) exist
somewhere outside `modules/volume/tests/`, this pass makes no claim about
them either way.

## Unresolved project questions

1. **Whether `mock_provider` is the project's intended convention for
   plan-only module tests.** AGENTS.md's Testing section states the test
   command and glob (`terraform test`, `modules/<name>/tests/*.tftest.hcl`)
   but says nothing about whether tests should mock the provider or run
   against the real one with a read-only token. This pass assumed
   `mock_provider "hcloud" {}` throughout, per the dispatch's explicit "no
   real Hetzner API calls" instruction, and verified live that this works
   under the pinned Terraform version (1.9.8) with no `experiments` flag.
   All tests in this pass depend on this assumption.
2. **Whether the test-path glob should extend to cover environment-level
   composition.** Five of the ten uncovered scenarios (2, 3, 4, 6 partly,
   14) turn on the `environments/prod`-level `count =
   var.volume_enabled && var.server_enabled` coupling that this change's
   design explicitly calls "the crux of the change." Neither
   `modules/volume` alone nor the dispatched glob
   (`modules/volume/tests/*.tftest.hcl`) can express that composition.
   AGENTS.md's Testing section covers only module-level tests under
   `modules/<name>/tests/`; it records no convention for testing
   environment-level `count`/toggle composition at all. Flagging this as
   an open question for whoever reviews or extends this pass — either the
   glob needs to be widened (e.g. to allow a `modules/volume/tests/setup/`
   harness module wrapping the coupling logic, or an
   `environments/prod/tests/` location) or this coupling is accepted as
   verified only by the live `terraform plan` review step already in
   tasks.md 3.3, never by an automated test.

## What the implementation step must make pass

Once `modules/volume/{main,variables,outputs,versions}.tf` exist (tasks.md
section 1), running `terraform test` from `modules/volume/` must turn the
baseline above (0 passed, 3 failed, 5 skipped) into all 8 `run` blocks
passing:

- `creation.tftest.hcl`: `plan_creates_volume_with_declared_configuration`,
  `plan_attaches_to_server_at_creation`, `plan_requires_non_empty_server_id`
- `labels.tftest.hcl`: `plan_applies_environment_and_managed_by_labels`,
  `plan_merges_caller_supplied_labels_without_losing_automatic_ones`
- `delete_protection.tftest.hcl`: `plan_delete_protection_defaults_to_true`,
  `plan_delete_protection_true_is_set_on_the_resource`,
  `plan_delete_protection_is_parameterized_not_hardcoded`

None of these tests were edited, weakened, or deleted to reach this state
— this pass only adds tests, never subtracts, and none existed before it.
