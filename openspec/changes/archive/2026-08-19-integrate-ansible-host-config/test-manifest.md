# Test manifest — `integrate-ansible-host-config`

Written by the `openspec-test-writer` dispatch, before implementation. This
file is **not** an OpenSpec-schema artifact — it will not appear among
`openspec instructions apply`'s context files, and must be read on purpose
before implementing this change. See also this repository's
`rules/` fragment (in the `ai-toolkit` library checkout this project uses),
which directs that it be read before implementing; this manifest's location
is the second, redundant pointer for a machine where that fragment's
machine-local import path doesn't resolve.

**This pass added zero test files.** No existing test was edited, deleted,
or disabled, and nothing was written outside this manifest's own path. Every
scenario below is accounted for — covered, or uncovered with a stated
reason — never silently dropped. The reasoning is that this change is,
by its own `proposal.md` and `design.md`, structural/scaffolding only: it
explicitly does not write Ansible role/playbook content or the `platform/`
Compose service definitions (see `proposal.md`'s closing paragraph and
`design.md`'s Non-Goals), and this project's only currently-defined
mechanized test convention — `terraform test` against
`terraform/modules/<name>/tests/*.tftest.hcl` — has no bearing on Ansible or
Compose behavior at all, and (per the reasoning under
`iac-repo-foundations` below) does not reach environment-level module
composition either. Forcing a test into that gap would mean either writing
implementation to give it something to assert against (prohibited) or
asserting only that scaffolding exists, which would not exercise the
behavior the scenario actually states — the `testing` skill's standard on
not fabricating tests for behavior that can't yet be exercised.

## Baseline taken

**Scoped baseline**, covering the entire currently-existing test-path glob
contents (`modules/<name>/tests/*.tftest.hcl` — the pre-restructure location;
this change's task 1.2 relocates it to `terraform/modules/<name>/tests/*.tftest.hcl`,
which does not yet exist):

```
$ cd modules/volume && terraform test
tests/creation.tftest.hcl...          pass (3 runs)
tests/delete_protection.tftest.hcl... pass (3 runs)
tests/labels.tftest.hcl...            pass (2 runs)

Success! 8 passed, 0 failed.
```

`modules/server` carries no `tests/` directory at all — there is nothing to
run there. Terraform v1.9.8 was used (locally installed; newer than the
repo's provider lock but not pinned itself).

Since this pass adds no new test files, there is no "new tests fail because
the target doesn't exist yet" claim to make — the baseline above establishes
only that the pass did not encounter or touch an already-broken suite.

## Scenario accounting

14 `#### Scenario:` blocks total across the three delta specs. All 14 are
accounted for below; 0 are covered by a new test; 14 are uncovered with a
stated reason.

### `iac-host-configuration` (ADDED capability — 8 scenarios)

None of these are covered. This capability's requirements describe Ansible
inventory, role-pinning, secrets, and firewall-ownership *behavior* — none
of which exists yet (no `ansible/` content is written by this change; see
`proposal.md`/`design.md` Non-Goals) — and none of it is Terraform, so it
falls outside this project's only mechanized test convention
(`terraform test` against a module) regardless of implementation state.

| Requirement | Scenario | Status | Reason |
|---|---|---|---|
| Dynamic Inventory via hcloud Plugin | Inventory resolved live from Hetzner | Uncovered | Requires a real `ansible-inventory -i ansible/inventory/hcloud.yml --graph` run against Hetzner's live API with the current `HCLOUD_TOKEN` — no inventory config exists yet (task 2.2), and even once it does, this is a live-API check, not something `terraform test`'s mock-provider convention reaches. `tasks.md` task 2.5 already names this as the intended manual verification step at implementation time. |
| Dynamic Inventory via hcloud Plugin | Disabled server yields no stale inventory entry | Uncovered | Same mechanism as above, plus requires toggling `server_enabled = false` against the real prod server to observe the inventory going empty — `tasks.md` task 2.5b explicitly anticipates this may need to be deferred/documented rather than exercised, "if toggling the flag isn't safe to exercise at task time." Recording it here as deferred for the same reason: exercising it means actually taking the real prod server down, which is outside this pass's authority and outside what a test-writing pass should trigger as a side effect. |
| Container Runtime Installed via Pinned External Role or Equivalent | External role version is pinned | Uncovered | This is a static fact about `ansible/requirements.yml` (task 2.3) — but that file doesn't exist yet, and even once it does, asserting "the pinned version string is an exact pin, not a range" is a YAML-parsing check, not a Terraform module test. It falls outside the dispatched test-path glob (`terraform/modules/<name>/tests/*.tftest.hcl`), which is the only mechanized test convention this pass is authorized to write into. |
| Secrets Never Committed in Plaintext and Never Left World-Readable on Host | Secret-bearing variable is encrypted at rest in the repository | Uncovered | No secret-bearing variable exists anywhere in this change (no Ansible content is written) — there is nothing to observe being Vault-encrypted or not. Writing a test that manufactures a fake secret to assert Vault-encryption behavior would be testing Ansible Vault's own mechanism, not this project's usage of it, and still falls outside the Terraform-only test-path glob. |
| Secrets Never Committed in Plaintext and Never Left World-Readable on Host | Rendered secret file is restricted and untracked | Uncovered | Requires an actual task that renders a Vault-decrypted value to a file on a real or ephemeral host and inspecting that file's permissions/`.gitignore` coverage — no such task exists (no playbook/role content is written by this change). This is exactly the kind of role-level behavior the `ansible` skill names Molecule for, once role content exists; not reachable by this pass. |
| Host-Level Security Owned by Ansible, Cloud Firewall Owned by Terraform | Host firewall rules are Ansible-managed | Uncovered | No host-firewall Ansible tasks exist (no role/playbook content is written by this change) — there is nothing to observe being Ansible- vs. Terraform-managed. |
| Host-Level Security Owned by Ansible, Cloud Firewall Owned by Terraform | External exposure changes go through the cloud firewall | Uncovered | The Terraform side of this split (`modules/server`'s `hcloud_firewall.this`, default-deny inbound) already exists and is pre-existing, unmodified behavior — not introduced by this change, and not what this scenario is stating as new. The scenario is about a *process* constraint (a port-reachability change is made via the cloud firewall, not solely as a host-level rule) that has no Ansible host-firewall content yet to check against; nothing here is newly testable. |
| Configuration Scope Stops at the Container Runtime | A completed run starts no application | Uncovered | Requires an actual completed Ansible playbook run to observe that no application container started and no service-definition file was generated — no playbook exists (this change adds only `ansible/inventory/`, `playbooks/.gitkeep`, `roles/.gitkeep` scaffolding per task 2.1). There is no run to observe. |

### `iac-platform-services` (ADDED capability — 4 scenarios)

None of these are covered, for the same reason as a block: this capability
describes the shared `platform/` Compose stack's behavior, and this change
adds only `platform/README.md` (task 3.2) — explicitly no
`docker-compose.yml` service content (`proposal.md`, `design.md`
Non-Goals). None of it is Terraform, so none of it is reachable through this
project's only mechanized test convention regardless.

| Requirement | Scenario | Status | Reason |
|---|---|---|---|
| Shared Services Live in a Dedicated Platform Stack | A new application reuses the platform stack | Uncovered | No `platform/docker-compose.yml` and no "new application" exists — there is nothing to deploy and observe reusing (or not reusing) a reverse proxy/database that isn't defined yet. |
| Single Shared PostgreSQL Instance, Per-Application Databases | A new application requests a database | Uncovered | Same reason — no shared PostgreSQL service definition exists yet to provision a database within. |
| Platform Stack Deployment Is Not Ansible's Responsibility | Platform stack changes bypass Ansible | Uncovered | There is no deployment mechanism yet at all (the deployment mechanism is an explicit open question in `design.md`, deferred to a future change) — nothing to observe as "outside `ansible/`'s content" versus not. |
| No Dedicated Monitoring Server | Monitoring is added to the existing host | Uncovered | No monitoring services are added by this change (explicit non-goal) — nothing to observe being scheduled on the existing host versus a new one. |

### `iac-repo-foundations` (MODIFIED requirement — 2 scenarios)

Both scenarios state a fact about `terraform/environments/prod/`'s own
configuration (which module path it calls, and that a future environment
folder wouldn't require restructuring) — not about a module's own internal
behavior. This project's only mechanized test convention is explicitly
scoped to *module*-level tests
(`modules/<name>/tests/*.tftest.hcl`/`terraform/modules/<name>/tests/*.tftest.hcl`,
per `AGENTS.md`'s Testing section and this dispatch's stated test-path
glob), and the existing test suite already establishes, in its own words,
that environment-level composition is out of that scope: see
`modules/volume/tests/creation.tftest.hcl`'s header comment — "These run
blocks exercise `modules/volume` in isolation (not `environments/prod`)...
They do NOT exercise the `environments/prod`-level ... coupling itself —
that composition lives outside this module and outside this test-path
glob." The same reasoning applies here without modification, and is the
basis both scenarios below are recorded uncovered rather than attempted via
a `run` block that overrides `module.source` to point at
`terraform/environments/prod` — that pattern would extend a
module-under-test's own test suite to assert on an unrelated root
module's file layout, which is exactly what that precedent declined to do,
and would also require standing up variables/mocking for
`terraform/environments/prod`'s full configuration (including
`hcloud_ssh_key.this`) to produce a test whose real subject is a path
string, not module behavior — fragile scaffolding built to observe a fact
`terraform plan`'s own empty-diff check (`tasks.md` task 1.9) already
verifies directly, with real state, at implementation time.

| Requirement | Scenario | Status | Reason |
|---|---|---|---|
| Environment and Module Folder Structure | Prod environment consumes a shared module | Uncovered | States a fact about `terraform/environments/prod/main.tf`'s own module `source` argument — caller-side composition, out of the module-test-path glob's scope per the precedent above. `tasks.md` task 1.9 ("run `terraform init`/`plan` inside `terraform/environments/prod` locally... confirm an empty diff") is this change's own named verification mechanism for the restructure, and is the right level for this fact: it observes the *actual* resolved module graph and remote state, which a mocked module-level test cannot substitute for. |
| Environment and Module Folder Structure | Adding a future environment does not require restructuring | Uncovered | Concerns a hypothetical future environment that doesn't exist yet — there is no `terraform/environments/staging/` (or similar) to add and observe not requiring existing files to move. Nothing exists to run a test against; this is a structural/extensibility property of the two-directory layout, not a fact any run of `terraform test` today could exercise either way. |

## Assertion classification

Not applicable — this pass wrote no assertions. (See scenario accounting
above for the per-scenario coverage/uncovered classification, which is the
applicable granularity here.)

## Obsolete-tests list

**Search conducted, no bearing test found** (this change does carry a
`MODIFIED` delta — `iac-repo-foundations`'s "Environment and Module Folder
Structure" — so "not applicable" does not apply here; a search was owed and
was performed).

Searched the dispatched test-path glob and nowhere else:
`modules/*/tests/*.tftest.hcl` (the pre-restructure location; the only one
that currently exists — `terraform/modules/` doesn't exist yet). Found:
`modules/volume/tests/creation.tftest.hcl`,
`modules/volume/tests/delete_protection.tftest.hcl`,
`modules/volume/tests/labels.tftest.hcl`. `modules/server/tests/` doesn't
exist, so nothing to search there.

Evidence: read all three files in full. Their assertions target
`hcloud_volume.this`'s resource-level attributes only — `name`, `size`,
`server_id`, `delete_protection`, `labels["environment"]`,
`labels["managed_by"]`, and a caller-supplied label merge (see
`modules/volume/tests/creation.tftest.hcl` lines 43–82,
`delete_protection.tftest.hcl` lines 34–67, `labels.tftest.hcl` lines
22–59). None reference a literal `environments/` or `modules/` path
string, and none assert anything about how a caller sources this module —
the only thing the modified requirement actually changes (the path
segments environments consume modules from). Relocating these files (as
part of `git mv modules terraform/modules`, task 1.2, which is not
performed by this pass) changes no line inside them and would not need to,
per the baseline run above. **Candidate for human confirmation**, as with
every entry in this list — but the evidence above is that none of the three
existing test files bear on what this delta changes.

## Unresolved project questions

- **What mechanized testing convention, if any, applies to Ansible content
  once written, and to `platform/`'s Compose stack once it has service
  definitions?** `AGENTS.md`'s "Testing" section states only the
  Terraform-module `*.tftest.hcl` convention; it says nothing about
  Ansible or Compose. `tasks.md` task 2.6 adds `ansible-lint` and
  `ansible-playbook --syntax-check` to pre-commit (static checking, not a
  test command), and the `ansible` skill separately names Molecule as the
  proportionate mechanism for role-level testing "once role content
  exists" — but neither `AGENTS.md` nor this change's own artifacts commit
  the project to Molecule, or to anything else, as its test command for
  `ansible/`. No assumption was taken here because no test in this pass
  depended on an answer — but whoever implements `ansible/` role/playbook
  content in a future change, and whoever next writes tests against it,
  will need this settled (recorded in `AGENTS.md`, mirroring how the
  Terraform convention is recorded there today) rather than decided ad hoc
  per change. Flagging it now since this change is where the `ansible/`
  and `platform/` directories are first scaffolded.

## What the implementation step must make pass

Nothing in this manifest — no new test was written, so there is nothing
for `openspec-apply-change` to turn from red to green as a direct
consequence of this pass. What implementation should still do, per
`tasks.md`'s own verification section (5.1–5.4) and the uncovered-scenario
reasons above:

- `terraform fmt -check`, `terraform validate`, `tflint` against the moved
  `terraform/` tree (task 5.1).
- `terraform init && terraform plan` inside `terraform/environments/prod`
  producing an empty diff (task 1.9) — the actual verification for both
  `iac-repo-foundations` scenarios recorded uncovered above.
- `ansible-lint` and `ansible-playbook --syntax-check` against the new
  `ansible/` scaffolding (task 5.3).
- `ansible-inventory -i ansible/inventory/hcloud.yml --graph` resolving the
  real prod host (task 2.5), and returning no host when disabled (task
  2.5b, or documenting why deferred) — the actual verification for the two
  `iac-host-configuration` inventory scenarios recorded uncovered above.
- The existing `modules/volume/tests/*.tftest.hcl` suite (8 runs) continuing
  to pass unchanged after `git mv modules terraform/modules` (task 1.2) —
  this is the baseline this pass recorded, and nothing in this change's
  delta specs should cause it to regress.
