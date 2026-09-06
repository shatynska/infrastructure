# Handoff: close-ci-verification-gaps

No proposal yet. This records why the change was identified, what bears on it,
and what it must not undo. The session that takes it up writes the proposal.

Identified by a full-repository audit on 2026-09-06, trunk at `245ef59`.

## Why this was identified

CI verifies Terraform and nothing else, and the one guard standing between a
merge and a destroyed production server fails open.

**1. Every check in `pr-validation.yml` is gated on Terraform having changed.**
`terraform fmt`, `validate`, `tflint`, `terraform test`, Trivy **and gitleaks**
all carry `if: steps.changes.outputs.terraform == 'true'`, where that filter
(lines 34-39) matches only `terraform/environments/**` and
`terraform/modules/**`.

A pull request touching only `ansible/` therefore gets no lint, no syntax
check, no Molecule run, and **no secret scan**. Confirmed: no workflow under
`.github/workflows/` mentions ansible, ansible-lint or molecule at all.

Two consequences worth stating separately:

- Roughly 1,500 lines of Molecule `verify.yml` — the largest test asset in this
  repository, across six roles and eight scenarios — has never run in CI. It is
  reachable only by a human remembering to run it locally.
- `ansible/inventory/group_vars/prod.yml` holds a Vault blob and several public
  keys, and is exempt from gitleaks. Gitleaks is the one check whose entire
  value is being unconditional; path-gating it defeats its purpose.

**2. The destroy-policy gate fails open.** `.github/workflows/apply.yml:95`:

```bash
has_destructive=$(jq -e '[.resource_changes[]? | select(...)] | length > 0' plan.json || true)
if [ "$has_destructive" != "true" ]; then ... exit 0
```

If `jq` errors — malformed `plan.json`, a `terraform show` failure — stdout is
empty, `has_destructive` is `""`, and the gate reports "No delete/replace
actions in the plan" and passes. "I could not tell" is currently treated as
"it is fine", on the check that exists to prevent an unintended destructive
apply. It must fail closed.

**3. `dependabot.yml` omits `terraform/modules/volume`.** It lists
`/terraform/environments/prod` and `/terraform/modules/server` only. The volume
module has its own `.terraform.lock.hcl`; its provider pin will rot silently.

**4. `apply.yml` has no path filter.** `on: push: branches: [main]`, unfiltered,
so every merge — including docs-only merges such as #55 — runs a production
`terraform plan` and leaves a `production` Environment approval pending. That is
approval fatigue on the exact gate that has to stay meaningful. `drift.yml`
already covers out-of-band changes nightly, so the redundancy buys little.

**5. gitleaks version drift.** `v8.30.0` in `.pre-commit-config.yaml:13`,
hardcoded `8.24.2` in `pr-validation.yml:139-140`. Local and CI scans are not
the same scan.

## What bears on it

- `AGENTS.md`, "Testing": this project's test command for Ansible is
  `molecule test --all` per role. The `--all` matters — `ops_user` has two
  scenarios and `deploy_user` three; `molecule test -s default` silently skips
  most of the suite.
- `ansible/requirements-test.txt` pins the whole Molecule toolchain exactly and
  records, at length, why those pins move forward rather than backward. CI must
  install from it, not resolve fresh.
- `README.md:84-123` documents the local Molecule setup, including that the
  suite runs offline with no GHCR credential needed, and the `DOCKER_CONFIG`
  workaround for a `credsStore` entry. The offline property is what makes a CI
  run feasible without secrets.
- Molecule uses the Docker driver, so CI needs a runner with Docker available
  and should expect the suite to be slow relative to the Terraform checks.
  Whether Ansible verification gates a merge or runs advisory-first is a real
  decision for the proposal, not a foregone conclusion.
- `.pre-commit-config.yaml` already runs `ansible-lint` and
  `ansible-playbook --syntax-check`; CI duplicating those is cheap. Molecule is
  the expensive part.
- `openspec/specs/iac-cicd-pipeline/spec.md` holds the requirements this
  workflow implements, including "Required Status Checks Report on Every Pull
  Request". Check whether closing these gaps needs a spec delta or only an
  implementation fix — the audit did not settle that.

## What it must not undo

- **The credential split.** `pr-validation.yml`'s job declares no
  `environment:` and must never gain one; that is what keeps the read-write
  Hetzner token out of pull-request runs. Same for `apply.yml`'s `plan` job and
  `platform-deploy.yml`'s `diff` job.
- **The destroy gate itself.** Fix its failure direction; do not relax, bypass
  or remove it. The `destroy-override` label mechanism stays.
- **The deliberate non-path-filtering of `pr-validation.yml` at the workflow
  level.** Its top comment records why: it is a required status check and must
  report a conclusion on every pull request, including ones touching no
  Terraform. Fix the gating *inside* the job; do not add a workflow-level
  `paths:` filter to it. Note this is the opposite of what finding 4 asks of
  `apply.yml`, which is not a required check — do not conflate the two.
- **`terraform validate`/`tflint`/`terraform test` discovering directories
  rather than naming them.** That glob shape was deliberate
  (`fix-ci-module-coverage`, archived) so a new module is covered without a
  workflow edit. Any Ansible equivalent should follow it rather than hardcode
  the current six roles.
- **The exact-version pinning convention.** If CI installs the Molecule
  toolchain, it installs from `ansible/requirements-test.txt` and
  `ansible/requirements.yml`, never a floating resolve.
