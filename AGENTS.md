<!-- ai-toolkit:development-workflow v1 -->
<!-- Generated. Do not edit inside this block — it is replaced on update.
     Project-specific conventions belong below the closing marker. -->

# Development workflow

These rules establish how work proceeds on this project once it has a
foundation. They apply independently of any single tool — each names an
obligation as a role to fill, and where this project uses Claude Code, names
the binding for that role beneath it.

## Spec-driven development

Use a specification-driven change process for non-trivial features, changes,
and significant architectural decisions. Do not begin implementing a
non-trivial change without a corresponding change proposal recording what is
intended and why.

A change's artifacts — its proposal, its design, its specification deltas —
are the record of intended behavior and the decisions behind it. They are
read before implementation, not written after the fact to describe what was
already done.

## Test design before implementation

Before implementing a change with testable behavior, have an independent
author derive tests from its specification deltas — not from the
implementation, and not written by whoever writes the implementation. Two
processes that see only the implementation share its blind spots; a test
author with no sight of the implementation does not.

*Claude Code binding:* dispatch `ai-toolkit:openspec-test-writer` after a
change is reviewed and before it is implemented.

## Independent review before completion

After implementing a change, have an independent reviewer check it against
its own specification before considering it complete. The reviewer verifies
that requirements are implemented, that the implementation matches what the
specification describes, that tests adequately cover the behavior that
changed, that no unrelated scope was introduced, and that project
conventions were followed.

*Claude Code binding:* dispatch `ai-toolkit:openspec-change-reviewer` before
treating a change as done.

## Verification before any completion claim

Implementation existing is not the same as a change being complete. Run the
verification relevant to the change — tests, type checking, linting,
formatting, a build, or whatever else the project's conventions require —
and do not report a change as complete without having run it.

## Small, reviewable commits

Prefer small, focused commits that represent a complete, meaningful unit of
work, over large commits bundling unrelated concerns. After a meaningful
milestone is reached, proactively suggest creating a commit rather than
waiting to be asked.

Before committing: look at the diff being committed, run the verification
relevant to what changed, and check that no secret or unintended file is
included. Suggest the commit; do not make it without confirmation.

## Incremental development and scope control

Prefer changes small enough to review in one sitting. Where a change grows
to cover multiple independent concerns, or grows too large to review as a
unit, consider splitting it into separate changes instead.

Implement only what belongs to the change currently in progress. An
improvement noticed along the way, that is not part of that change's stated
scope, becomes a separate proposed change rather than being folded in.

## Requirements and assumptions

Do not silently invent a requirement that was not stated and cannot
reasonably be inferred. Where an important decision cannot be inferred, ask
rather than guess.

Record significant decisions in the project's own artifacts rather than
relying on them surviving only in conversation history — a decision that
exists only in a conversation is not available to whoever reads the project
next.

## The repository is the source of truth

Do not rely on earlier conversation context for information the repository
itself can supply. Prefer reading a file, a spec, or a commit over recalling
what a previous exchange said about it — the repository does not go stale
the way a remembered conversation does, and it is what the next person, or
the next session, will actually see.
<!-- /ai-toolkit:development-workflow -->

## Project conventions

These are specific to this repository, not part of the generated workflow
block above. See `openspec/changes/project-foundation/design.md` for the
full reasoning.

### Production changes never bypass the pipeline

`terraform apply` is never run locally against `terraform/environments/prod/`.
Production changes reach Hetzner only through the gated GitHub Actions
pipeline: a PR-time plan for review, then a human-approved apply of that
exact saved plan on merge to `main`. Local runs use the read-only Hetzner
token and are for `terraform plan`/`validate` only.

### Testing

There is no traditional unit-test layer for the Terraform code yet.
Verification is static analysis (`terraform fmt`, `terraform validate`,
`tflint`, Trivy, `gitleaks`) plus mandatory human review of an exact
`terraform plan`. As `terraform/modules/` grows past `terraform/modules/server`, add
module-level tests as `terraform/modules/<name>/tests/*.tftest.hcl`, run via
`terraform test` — that is this project's test command and test-path glob
for the independent-test-authoring step in the workflow above.

### Development tooling

Run `pre-commit install --hook-type pre-commit --hook-type commit-msg`
once per clone (see README's Local setup). It runs `terraform fmt`,
`tflint`, `terraform validate`, `gitleaks`, `ansible-lint`, and
`ansible-playbook --syntax-check` on `git commit`, and `commitlint`
(Conventional Commits) on the commit message.

### Host configuration and platform stack

`ansible/` configures a Terraform-provisioned host; `platform/` holds the
shared Compose stack every application on that host depends on. See
`iac-host-configuration` and `iac-platform-services`, and
`openspec/changes/integrate-ansible-host-config/design.md` for the full
rationale. This project's defaults for the decisions those specs leave to
the consuming project:

- **Inventory**: dynamic, via the `hcloud` plugin (`ansible/inventory/hcloud.yml`),
  grouped by the existing `environment` label — never a static or
  hand-maintained hosts file, so a disabled/destroyed server can't leave a
  stale entry behind.
- **Container runtime**: installed via a pinned external Galaxy role
  (`geerlingguy.docker`, pinned in `ansible/requirements.yml`) — not the
  only acceptable pattern going forward, but this project's current default.
  Any external role or collection used for any purpose is pinned to an exact
  version, never a floating range.
- **Secrets**: Ansible Vault is the default mechanism. Encrypting the
  *source* value isn't enough — a task that renders a Vault-decrypted value
  into an on-host file (e.g. an `.env` file) produces plaintext on disk
  regardless of how the source was protected. Any such rendered file must
  have restrictive permissions and must be excluded from version control.
- **Firewall split**: the Hetzner cloud firewall (Terraform-managed) is the
  default-deny gate for what's reachable from the internet at all;
  Ansible-managed UFW/fail2ban is host-level defense-in-depth on top of what
  the cloud firewall already allows. For any given port, exactly one layer
  is the documented access gate — never opened at only one layer while
  assumed closed at the other.
- **Scope boundary**: Ansible's responsibility ends once the container
  runtime is installed and ready. It never templates an application
  service-definition file (e.g. a Compose file) and never invokes a
  runtime's application-lifecycle commands (starting, stopping, restarting
  an application stack) — that's `platform/`'s and each application's own
  Compose files, deployed by a mechanism other than Ansible.
- **No dedicated monitoring server**: Prometheus/Grafana, when added, run
  alongside `platform/`'s stack on the same host; single-host observability
  risk is mitigated with an external dead-man's-switch, not a second server.
