## Context

See `proposal.md` - Why. Today `environments/` and `modules/` sit at the
repo root because Terraform is the only tool in this repository. This
change adds two more tools with different lifecycles (Ansible runs
per-host-config-change; the platform Compose stack runs per-deploy), so the
root can no longer be implicitly "the Terraform root" — it needs to
distinguish provisioning, host configuration, and shared-application
runtime as three visibly separate areas.

Relevant existing constraints this design must respect:
- `environments/prod` already outputs `server_ipv4_address`, and the server
  has a lifecycle toggle (`server_enabled`) that can take it to nonexistent
  — see `iac-server-lifecycle`.
- The server already carries an `environment = prod` Hetzner label (set in
  `ssh_key.tf`), predating this change.
- CI today assumes Terraform lives at `environments/` and `modules/`
  directly: `.github/workflows/{pr-validation,apply,drift}.yml` and
  `.tflint.hcl` all reference those paths.
- HCP Terraform binds state to a workspace name, not a filesystem path, so
  moving `environments/prod` does not touch remote state.

## Goals / Non-Goals

**Goals:**
- A folder structure that makes "provisions / configures / runs
  applications" visually obvious and keeps each tool's CI/tooling
  self-contained under its own top-level directory.
- An inventory mechanism that can't silently point Ansible at a host that
  no longer exists.
- A written boundary precise enough that a future contributor (human or
  agent) adding Ansible content knows, without asking, where its
  responsibility ends.

**Non-Goals:**
- Writing the actual Ansible roles/playbooks or the `platform/`
  `docker-compose.yml` service definitions — this change establishes where
  they go and what they may/may not do, not their content.
- Deciding the platform-stack deployment mechanism (CI-over-SSH, systemd +
  git pull, Watchtower, manual) — recorded as an open question below.
- Standing up Prometheus/Grafana or a per-application repository.
- Any change to Terraform state, HCP Terraform workspace bindings, or
  GitHub Environment secrets.

## Decisions

### Three top-level directories, not a nested `infra/{terraform,ansible}` split
`terraform/`, `ansible/`, and `platform/` sit as direct siblings at the
repo root rather than being grouped under a shared parent. Provisioning
and host configuration are related but run on different triggers
(Terraform on PR/merge via the gated pipeline; Ansible on a schedule or
manual run against live inventory) and shouldn't share a parent directory
that implies one governs the other. `platform/` is a sibling rather than
nested under `ansible/` specifically to keep the "Ansible never owns a
service-definition file" boundary visible in the directory layout itself,
not just stated in prose.

Alternative considered: keep `environments/`/`modules/` at the root and add
only `ansible/` and `platform/` (Option A from the earlier exploration).
Rejected because it leaves Terraform implicitly "the default tool" and
breaks the visual symmetry the other two directories would otherwise have
— worth the one-time path migration cost.

### Dynamic `hcloud` inventory over static or Terraform-written inventory
Three patterns were considered (per the `ansible` skill's inventory-
provenance guidance): a hand-maintained static file, Terraform writing the
inventory as an apply step, or a dynamic plugin querying Hetzner directly.
Static is rejected outright here because the server can be toggled off
(`server_enabled = false`) - a static file has no way to reflect that
without a human remembering to edit it. Terraform-writes-inventory was
rejected because it couples an Ansible run to having just run a Terraform
apply, when in practice host-configuration runs (e.g. re-applying a
hardening role) happen independently of provisioning changes. The dynamic
`hcloud` plugin queries live state on every run, so it can't go stale
between the two tools' independent schedules - at the cost of needing
network access to Hetzner's API at inventory-resolution time, which this
environment already has (the same read-only token already makes API calls
for `terraform plan`).

Grouping by the existing `environment` label (rather than introducing a
new one) means adding `staging` later is a label value, not an inventory
rewrite - consistent with `iac-repo-foundations`' existing requirement
that adding an environment never requires restructuring.

### Docker installation: pinned external role, not mandated to a specific one
`geerlingguy.docker` is this project's chosen default, pinned in a
committed `requirements.yml`. The `ansible` skill explicitly does not
mandate a specific role or even external-vs-hand-rolled, only that
whatever is used, if external, is pinned - so this decision is recorded
as this project's default (changeable later without an upstream skill
change), not hard-coded as the only acceptable approach in the spec
itself. See `iac-host-configuration`'s "Container Runtime Installed via
Pinned External Role or Equivalent" requirement, which is written to allow
either.

### Secrets: Ansible Vault as default, with the render-to-disk boundary stated explicitly
Vault is a natural fit given this repo's existing CI (GitHub Actions can
hold the vault password as a secret the same way it holds `HCLOUD_TOKEN`).
The requirement is written to cover the failure mode that's easy to miss:
encrypting the *source* value doesn't protect a *rendered* file - a task
that templates a Vault-decrypted value into an on-host `.env` file
produces plaintext on disk regardless of how the source was protected.
That's why the spec requirement covers both halves (source encrypted, AND
rendered file permissioned + gitignored) rather than only the first.

### Firewall split: cloud firewall is the default-deny gate, host firewall is defense-in-depth
Terraform/Hetzner's cloud firewall is treated as the actual access-control
gate for what's reachable from the internet at all; Ansible-managed
UFW/fail2ban adds host-level defense (rate limiting, intrusion prevention,
narrowing further within what the cloud firewall already allows) rather
than independently deciding what's externally reachable. This avoids the
failure mode named in the `ansible` skill: a host rule opening a port the
cloud firewall closes does nothing, and a cloud firewall open to a port
the host firewall was meant to restrict silently exposes it. Per-port
ownership gets documented at implementation time, in the Ansible role/host
firewall config itself, not enumerated speculatively here before any port
exists to document.

### Platform stack stays single-host; single-instance-server risk mitigated externally, not architecturally
A second server dedicated to Prometheus/Grafana was considered and
rejected: this repo already commits to single-region/single-VM "for the
foreseeable future" (see `README.md`), and a personal/small-scale
deployment doesn't have enough hosts yet to justify dedicated monitoring
infrastructure. The real risk this trades away - losing observability
exactly when the host it monitors goes down - is real but is better
addressed with an external dead-man's-switch (a third-party heartbeat
check) than with a second server, since that gets the one property a
second server would provide (alerting that survives the host dying)
without the ongoing cost of provisioning and maintaining another machine.
This is written into `iac-platform-services` as a binding requirement now
("No Dedicated Monitoring Server"), not deferred as a mere intention,
because `proposal.md`'s "What Changes" already commits to it as a decided
placement for whenever monitoring is added — not something left open until
that later change happens. The dead-man's-switch mitigation itself is not
spec'd here: it's an external, third-party operational practice, not a
behavior of this repository, so it stays recorded as design rationale
rather than as a testable requirement.

## Risks / Trade-offs

- [Risk] The repo restructure touches CI workflow paths, `.tflint.hcl`,
  and README content in the same change as adding two new directories -
  a larger diff than either change alone. → Mitigation: no Terraform state
  or HCP workspace impact, so the move is mechanical; sequenced as its own
  task batch in `tasks.md`, verified with `terraform plan` producing an
  empty diff after the move, before any Ansible/platform content is added.
- [Risk] The `hcloud` dynamic inventory plugin makes every Ansible run
  depend on Hetzner API availability and the read-only token being valid
  in whatever environment runs Ansible (a contributor's machine, or CI).
  → Mitigation: this is the same dependency `terraform plan` already has
  locally; no new secret distribution problem is introduced.
- [Risk] Stating the Ansible/Compose boundary in prose and directory
  layout doesn't mechanically prevent a future playbook from crossing it
  (e.g. adding a `community.docker.docker_compose_v2` task "just this
  once"). → Mitigation: `iac-host-configuration`'s scope requirement gives
  reviewers (human or the `openspec-change-reviewer` agent) a concrete
  spec line to check future Ansible changes against.
- [Risk] `openspec/specs/iac-cicd-pipeline/spec.md`,
  `openspec/specs/iac-safety-hardening/spec.md`,
  `openspec/specs/iac-state-management/spec.md`, and the requirements
  within `iac-repo-foundations` other than "Environment and Module Folder
  Structure" (e.g. "Version Control Excludes State and Secrets") all
  contain literal `environments/`/`modules/` path references that become
  stale the moment this change's restructuring lands, but none of them are
  requirements whose *behavior* changes - only incidental path mentions.
  → Mitigation: not folded into this change's delta set, to keep it scoped
  to the one requirement that actually changes; tracked as a follow-up
  cleanup task in `tasks.md` instead of silently left inconsistent.

## Open Questions

- What deploys/updates `platform/`'s Compose stack on the host? Candidates
  named during exploration: a CI workflow that applies it over SSH
  (mirroring the Terraform apply gate), a systemd unit paired with a `git
  pull`, Watchtower, or a manual step. Deferred to a future change once
  `platform/docker-compose.yml` actually has content to deploy - doesn't
  block this change's structure or specs.
- Naming/count of per-application repositories (one shared "apps" pattern
  vs. one repo per application) - referenced as "elsewhere, not this repo"
  but not pinned down further, since no application exists yet to force
  the decision.
- How Ansible authenticates via SSH to the dynamically-resolved host
  (private key storage/distribution for local runs vs. CI runs) is
  distinct from the Hetzner API token and Vault mechanisms this change
  does specify, and isn't decided yet - including whether it reuses the
  existing operator key registered in `ssh_key.tf` or a separate
  deploy-scoped key. Deferred alongside the platform-deployment-mechanism
  question above; doesn't change this change's structure or specs, since
  no Ansible content that would need SSH access is written here yet.
