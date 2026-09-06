## Why

CI verifies Terraform and nothing else, and the one guard standing between a
merge and a destroyed production server fails open.

Every check in `pr-validation.yml` — including `gitleaks` — is gated on
`terraform/environments/**` or `terraform/modules/**` having changed. A pull
request touching only `ansible/` therefore gets no lint, no syntax check, no
secret scan, and never runs the ~1,500 lines of Molecule `verify.yml` across
eight scenarios that are this repository's largest test asset. Separately, the
destroy-policy gate in `apply.yml` treats "I could not tell" as "it is fine":
if `jq` errors on a malformed `plan.json`, `has_destructive` is the empty
string, the gate prints "No delete/replace actions in the plan" and passes.

## What Changes

**Secret scanning becomes unconditional.** `gitleaks` moves out from behind the
Terraform path gate in `pr-validation.yml` and runs on every pull request. Its
version is reconciled with `.pre-commit-config.yaml` (currently `v8.30.0`
locally against a hardcoded `8.24.2` in CI) so the local and CI scans are the
same scan.

**Ansible gains CI verification, in two tiers.**

- *Blocking, inside `pr-validation.yml`*: `ansible-lint` and
  `ansible-playbook --syntax-check`, conditioned on `ansible/**` having
  changed, mirroring what `.pre-commit-config.yaml` already runs locally. The
  checks themselves are near-instant; the job's cost is dominated by installing
  the pinned toolchain and warming the pre-commit cache. That is still a small
  fraction of the Molecule suite, which is the distinction the tiering rests
  on — not an absolute claim about seconds.
- *Advisory, in a new workflow*: `molecule test --all` per role, discovering
  `ansible/roles/*/molecule/` rather than naming the current five roles, and
  installing from `ansible/requirements-test.txt` and
  `ansible/requirements.yml` exactly. It is **not** a required status check.
  The suite has never run outside a developer machine, and its scenarios
  manipulate UFW, fail2ban and systemd inside Docker containers on a runner
  that is itself containerised; whether it survives that is unestablished.
  Making it blocking on day one risks making `main` unmergeable for a reason
  unrelated to any of these findings. A `docs/change-queue.md` entry records
  promoting it to a required check once it has proved green.

**The destroy-policy gate fails closed.** A `jq` failure, a missing
`plan.json`, or any value other than a literal `false` becomes a hard failure
with a distinct message, instead of being read as "no destructive actions".
The gate's mechanism and the `destroy-override` label are untouched.

**`apply.yml` gains a `paths:` filter** for `terraform/**`, so a docs-only
merge no longer runs a production `terraform plan` and leaves a `production`
Environment approval pending. `drift.yml` already detects out-of-band changes
nightly. `apply.yml` is not a required status check, so filtering it cannot
leave a pull request unmergeable — the opposite constraint that governs
`pr-validation.yml`, which stays unfiltered at the workflow level.

**`dependabot.yml` covers `terraform/modules/volume`**, which has its own
`.terraform.lock.hcl` and is currently unlisted, so its provider pin rots
silently.

**The CI configuration gains executable tests, and CI runs them.** The
requirements this change adds are assertions about workflow YAML,
`.github/dependabot.yml` and `.pre-commit-config.yaml` — none of which
`terraform test` can reach, which is why this repository has never had a check
over its own CI configuration. A stdlib `unittest` suite at
`.github/tests/test_ci_configuration.py` asserts them directly, and
`pr-validation.yml` runs it unconditionally.

This scope was added after the plan's review rounds, deliberately: deriving the
tests established that most of these scenarios reduce to static assertions that
*are* the scenario, and shipping a change about closing CI verification gaps
whose own guarantees nothing verifies would reproduce the defect it exists to
fix. The suite discriminates — fifteen of its assertions fail on the tree as it
stands today, and it carries a test that runs itself against two synthetic
repositories to establish that it can fail at all.

The derivation, the per-scenario accounting and the pre-implementation baseline
are recorded in `test-plan.md` beside this proposal. It is not an
OpenSpec-schema artifact, so it does not travel with the four that a reviewer
or an implementing session is dispatched with, and it has to be opened
deliberately.

## Capabilities

### New Capabilities

None. Every change here strengthens verification the pipeline already claims
to perform.

### Modified Capabilities

- `iac-cicd-pipeline` — **two added requirements**: Ansible verification in its
  two tiers, and the continuous-integration configuration being itself verified
  by an executable suite that runs unconditionally. **Three modified**: secret
  scanning is required on *every* pull request rather than only Terraform ones,
  with its version tied to the pre-commit pin; the destroy-policy gate must
  fail closed on an indeterminate plan inspection; the gated apply workflow
  triggers only on pushes that can affect the Terraform configuration.
- `iac-safety-hardening`: automated dependency updates must cover every
  directory carrying a `.terraform.lock.hcl`, enumerated exhaustively and kept
  in agreement with the lockfile set, so a newly added module cannot be
  silently omitted. Dependabot's `terraform` ecosystem has no discovery
  mechanism; the obligation is therefore on the configuration to stay complete,
  not on a glob.

## Impact

- `.github/workflows/pr-validation.yml` — gitleaks ungated, version bumped,
  Ansible lint/syntax steps added behind an `ansible` paths-filter output.
- `.github/workflows/ansible-verify.yml` — new, advisory Molecule workflow,
  also dispatchable manually so this change can exercise it.
- `.github/workflows/apply.yml` — `paths:` filter on the push trigger;
  destroy-policy gate rewritten to fail closed.
- `.github/dependabot.yml` — `/terraform/modules/volume` added.
- `.github/tests/test_ci_configuration.py` — new; the executable assertions
  behind this change's requirements, derived from the delta specs before
  implementation.
- `.github/requirements-ci.txt` — new; pins the `pre-commit` version CI
  installs, since nothing pinned it before, and pins PyYAML, which the test
  suite needs and which currently arrives only transitively via
  `ansible-core`.
- `.pre-commit-config.yaml` — gitleaks pin is the source of truth CI follows;
  changed only if reconciliation moves it.
- `AGENTS.md` — the "Testing" section gains this project's second test command
  and its glob, since `terraform test` no longer covers everything.
- `.gitignore` — `__pycache__/`, which this repository has never needed before
  and which running the suite creates.
- `README.md` — the Ansible testing section stops describing the suite as
  local-only.
- `docs/change-queue.md` — three entries: promoting Molecule to a required
  check, pinning the floating Molecule platform image, and the unpinned
  `pip install pre-commit` in `pre-commit-autoupdate.yml`.
- `openspec/specs/iac-cicd-pipeline/spec.md` — `## Purpose` extended to name
  both subjects this change adds to the capability: Ansible verification, and
  the pipeline's own configuration being verified. A capability's Purpose is not expressible as a delta,
  so it is hand-edited, in the archive pull request alongside the rest of the
  spec record rather than in the implementation one.
- No production infrastructure changes. No credential or `environment:`
  declaration is added to any pull-request-time job; the read-only/read-write
  Hetzner token split is untouched.
