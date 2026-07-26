## Context

The repository is currently empty aside from OpenSpec scaffolding. This is a greenfield Terraform setup targeting Hetzner Cloud, starting with one production server. There is no existing state, no existing CI, and no prior Terraform conventions in this repo to reconcile with — every decision below is a fresh choice, not a migration.

Naming note: HashiCorp renamed Terraform Cloud to **HCP Terraform** in 2024. This document uses HCP Terraform throughout; the two names refer to the same product.

## Goals / Non-Goals

**Goals:**
- Establish a repo structure, local tooling, and CI/CD pipeline that are safe to run against real infrastructure from the first `terraform apply`.
- Make destructive or unnoticed changes hard by default (review gates, destroy protection, secret scanning, drift visibility).
- Keep the pipeline's source of truth in one place (GitHub), consistent with existing developer habits.
- Leave a clean seam for adding further environments later without restructuring what's built now.

**Non-Goals:**
- Multi-environment (staging) setup — deferred to a future change. This change scopes to `environments/prod/` only.
- Specific server sizing/region/image decisions — left as `terraform.tfvars` values to fill in during implementation, not a design concern.
- HCP Terraform's VCS-driven workflow — considered and explicitly not used (see Decisions).
- **Server configuration and provisioning** — cloud-init/user-data content, package installation, and any config-management layer are out of scope. This change delivers a *provisioned, network-hardened, unconfigured* server. What runs on it is a follow-up change. The network baseline in Decision 13 is included because an internet-reachable server without it is not a safe end state, not because provisioning is in scope.

## Decisions

**1. HCP Terraform CLI-driven workflow, not VCS-driven — with workspace execution mode set to Local.**
HCP Terraform supports a VCS-driven workflow (HCP connects directly to the GitHub repo and runs plan/apply itself on webhook events, with approval via its own "Confirm & Apply" UI) and a CLI-driven workflow (HCP is used purely as remote state + locking backend, while GitHub Actions runs the `terraform` CLI and gates apply via a GitHub Environment approval rule). VCS-driven is genuinely less to configure — no apply-orchestration workflow to write. We chose CLI-driven anyway: PR-time checks (fmt, lint, Trivy, gitleaks) must run in GitHub Actions regardless, so VCS-driven would split one logical pipeline (validate → plan → review → apply) across two UIs — GitHub for checks, HCP for plan/apply/approval. CLI-driven keeps the entire pipeline in one place, matching the GitHub-PR-centric workflow already used for this project's other tooling (commitlint, etc.). The trade-off is losing HCP's built-in run history/UI and having to build the apply-gating workflow ourselves; GitHub Actions logs become the source of truth instead.

Critically, a `cloud` block defaults the workspace to **remote** execution, which would silently ship plans and applies to HCP's own runners instead of the GitHub Actions runner — quietly violating the intent above and breaking the saved-plan flow in Decision 8. The `infrastructure-prod` workspace's Execution Mode must be explicitly set to **Local**, and that setting is part of the workspace's definition of done, not an incidental console toggle.

**2. Environment folders, not environment branches.**
`environments/prod/` (and any future `environments/<env>/`) as directories in `main`, not long-lived `prod`/`staging` branches. Branch-per-environment invites drift between branches and ambiguity about which branch is "truth." A single `main` branch with folder-scoped state keeps one linear history. Even though this change only adds `prod`, the structure is chosen so a later `environments/staging/` slots in without moving anything.

*Known limit of this seam:* environments consume `modules/` by relative path, so all environments always run the same module code as of the merged commit. There is no "promote a module version through staging first" story — a module change lands for every environment simultaneously. When staging arrives, promotion has to come from *sequencing within one workflow* (apply staging, verify, then gate prod) rather than from version pinning. Getting a true promotion pipeline would require moving modules to their own repo with tags, or vendoring per-environment copies. Neither is worth doing at one environment; recording it here so it isn't discovered as a surprise later.

**3. Single environment (prod) for this change.**
Originally scoped with a staging environment from day one, but narrowed to prod-only to keep this bootstrap change small and immediately shippable. This simplifies the CI/CD pipeline for now — no cross-environment sequencing logic is needed since there's only one environment to gate. Adding staging later is a follow-up change that primarily adds a new folder + workspace + pipeline job, subject to the promotion caveat in Decision 2.

**4. `pre-commit` + `antonbabenko/pre-commit-terraform`, not a Husky-based setup.**
Husky is a Node-ecosystem git-hooks runner; the closest tool with first-class Terraform hook support is `pre-commit` (Python-based) via the `pre-commit-terraform` hook collection, which wraps `terraform fmt`, `tflint`, `terraform validate`, and can invoke security/secret scanners in one config file. This is the de facto standard in the Terraform community, so it's chosen over trying to wire Husky to shell out to Terraform tooling manually.

**5. Trivy for misconfiguration scanning — kept, but not treated as the security gate.**
`tfsec` was acquired by Aqua Security and merged into Trivy; the `tfsec` project itself is in maintenance mode and points users to Trivy's `trivy config` misconfiguration scanning as the successor — same underlying rule engine, actively maintained. So Trivy over tfsec is settled.

The more important point is that this choice matters less than it appears: **neither tool ships meaningful Hetzner Cloud coverage.** Their built-in misconfiguration rule packs are overwhelmingly AWS/Azure/GCP/Kubernetes/Docker. Running `trivy config` against `hcloud_*` resources will find close to nothing. Trivy is kept because it is nearly free to run and will catch generic Terraform-level issues, but it is explicitly *not* the control that makes this infrastructure safe. The controls that actually bind for Hetzner are, in order of value:
1. Module design that makes the unsafe thing unrepresentable — a firewall is required, not optional (Decision 13).
2. `variable validation` blocks rejecting bad inputs at plan time.
3. A small set of custom Trivy/Conftest policies for the specific rules we care about (e.g. reject any `hcloud_firewall` rule allowing `0.0.0.0/0` on port 22).
4. The CI destroy-policy gate (Decision 7).

Similarly, `tflint` gets only its bundled `terraform` ruleset — there is no Hetzner/`hcloud` tflint ruleset to enable.

**6. `gitleaks` kept as a separate secret scanner, invoked as the CLI binary — not `gitleaks-action`.**
Trivy also has a secret-scanning mode, which would reduce the toolchain to one tool. `gitleaks` is kept as a dedicated second tool because it's purpose-built for fast, diff-scoped scanning of staged changes in pre-commit and has a more battle-tested secret-pattern ruleset for that specific job. `gitleaks` and Trivy check different concerns (leaked credentials vs. misconfigurations) and both run in pre-commit and CI.

In CI, the `gitleaks` **binary** is invoked directly rather than using the `gitleaks/gitleaks-action@v2` marketplace action, for two independent reasons: the action requires a paid `GITLEAKS_LICENSE` key for repositories owned by a GitHub *organization* (free only for user accounts, and the free "Starter" tier covers a single repo), and `gitleaks-action@v2` runs on Node 20, which is removed from GitHub-hosted runners on 2026-09-16. The `gitleaks` CLI itself is MIT-licensed with no key requirement and no such deadline. Taking the binary avoids both a licensing cliff and a hard expiry date on the pipeline.

**7. Layered destroy protection — provider-level `delete_protection` plus a CI destroy-policy gate, not `prevent_destroy` in the shared module.**
The original plan put `lifecycle { prevent_destroy = true }` on the server resource inside `modules/server`. That is a trap: `prevent_destroy` accepts only a **literal** value — it cannot read a variable, because it is evaluated too early. Hardcoding it inside a module shared by every environment would make the module permanently undestroyable for *all* consumers, so a future `environments/staging/` could never be torn down — directly contradicting the reuse promise in Decision 2. It also protects nothing against deletion via the Hetzner console, and only covers resources someone remembered to annotate.

Three complementary layers instead:

- **`delete_protection = var.delete_protection` on `hcloud_server`** (with `rebuild_protection` set to match, as the provider requires). This is parameterizable per environment, and unlike `prevent_destroy` it sets a server-side lock that also blocks deletion from the Hetzner console/API — a hole nothing else in this design covers. Note the provider has historically lifted this lock itself during `terraform destroy`, and that behavior has varied across provider versions; verify against the pinned version during implementation and do not rely on it as the Terraform-side guard.
- **A CI destroy-policy gate** as the Terraform-side guard: parse the saved plan with `terraform show -json` and fail the pipeline if any resource action is `delete` or `replace`, unless the pull request carries an explicit override label. This covers *every* resource automatically rather than the annotated subset, and surfaces the objection in the PR where it can be discussed, rather than as an opaque Terraform error.
- **Literal `prevent_destroy`** reserved for genuinely never-destroy resources, declared in a prod-only file under `environments/prod/` — never inside a shared module.

**8. The approval gate approves a specific diff, not a run.**
The original flow posted a plan on the PR and, on merge, ran a fresh `terraform apply` behind the `production` Environment gate. The reviewer therefore approved a job that had not yet computed its diff — the applied plan could differ from the reviewed one because of the merge commit, intervening drift, or a provider version bump. The approval was procedurally real but informationally empty.

Instead, the apply workflow is split into two jobs in one run:
- **Job A (plan)** — declares no `environment:`, so it starts immediately with the read-only Hetzner token. It runs `terraform plan -out=tfplan`, writes the human-readable diff to `$GITHUB_STEP_SUMMARY`, runs the destroy-policy gate from Decision 7, and uploads `tfplan` as an artifact.
- **Job B (apply)** — `needs: A`, declares `environment: production`, so it blocks on the required reviewer. The approver reads job A's summary — the exact diff — before approving. On approval, job B downloads `tfplan` and runs `terraform apply tfplan`, which applies precisely that plan or errors if state has moved underneath it.

This composes cleanly with the split tokens: job A holds read-only, job B holds read-write. The trade-off is that a saved plan file stores sensitive values in cleartext, so the artifact must be handled as a secret — see Risks.

**9. HCP Terraform dynamic credentials via GitHub OIDC; Hetzner tokens stay static and split by privilege.**
HCP Terraform supports GitHub OIDC workload identity, so `TF_API_TOKEN` need not exist as a long-lived repository secret at all — the workflow exchanges a short-lived OIDC token per run. That halves the static-secret surface for essentially no extra effort, so it is used. Hetzner Cloud has no OIDC support, so `HCLOUD_TOKEN` remains a static secret, split read-only/read-write per the Credential Scoping requirement in the iac-cicd-pipeline spec.

An alternative worth one sentence: dropping HCP Terraform entirely in favour of an S3 backend on Hetzner Object Storage — Terraform 1.11+ `use_lockfile` provides native state locking with no DynamoDB equivalent required — would keep state, compute, and credentials inside a single vendor. HCP is kept for its state versioning and rollback and to avoid bootstrapping a bucket before Terraform can run, but the option is recorded rather than left unexamined.

**10. Nightly drift detection, reported as one deduplicated GitHub issue.**
Runs `terraform plan` against prod on a schedule and surfaces any diff, without applying anything. Cost is roughly 1-2 minutes of GitHub Actions runtime per run, well within the free tier, and it doesn't invoke HCP run execution since the backend is CLI-driven with local execution.

A workflow that only *fails* on drift is not enough: a permanently red scheduled job gets muted within a week, at which point drift detection is theatre. The job instead creates-or-updates a **single** GitHub issue containing the diff, so drift has one durable, deduplicated home that closes when the drift is resolved. Two operational details belong to the requirement, not to implementation taste:
- GitHub **auto-disables scheduled workflows after 60 days of repository inactivity**. An infrastructure repo is exactly the kind that goes quiet, so this will happen; the drift workflow must therefore also be `workflow_dispatch`-triggerable, and re-enabling it belongs in the runbook.
- The scheduled plan runs with `-lock=false`. It writes nothing, and taking the state lock would let a nightly read collide with an in-flight apply and report a spurious failure.

**11. Dependabot for `terraform` and `github-actions`; pre-commit hooks via scheduled `pre-commit autoupdate`.**
Dependabot's `terraform` ecosystem bumps `required_providers` constraints and updates `.terraform.lock.hcl` when present. The `github-actions` ecosystem is added too — it was missing from the original plan, and it is the one that actually defends against a compromised or abandoned third-party action, which is the more realistic supply-chain risk here than a stale provider.

Dependabot has **no `pre-commit` ecosystem**, so pinned hook revisions cannot be maintained that way. A small scheduled workflow running `pre-commit autoupdate` and opening a PR covers it instead.

**12. Branch protection on `main` is a precondition, not a nicety.**
Every safety property in this design — PR review, plan visibility, the destroy-policy gate, the approval gate — assumes changes reach `main` through a pull request. A direct push to `main` bypasses all of it and triggers an apply. `main` therefore requires a pull request, passing status checks, and no force-push, and that is specified as a requirement rather than left as repo setup trivia.

One gotcha this creates: the PR validation workflow is path-filtered to `environments/` and `modules/`. A path-filtered workflow that is *also* a required status check never reports on PRs touching other paths, and those PRs become permanently unmergeable. Resolved by making the required check a job that always runs, with the Terraform work conditioned on paths inside it.

**13. Server network baseline: default-deny firewall, key-only SSH, backups enabled.**
The original safety-hardening scope protected Terraform from its operator but left the server itself unspecified — an internet-reachable prod host with no firewall requirement. Since this change creates a real server, the baseline is part of it: an `hcloud_firewall` attached to the server, default-deny inbound with explicitly enumerated allowed CIDRs, SSH by key only with password authentication disabled, and `backups = true`.

Backups carry a 20% surcharge on the server price and are enabled anyway: `delete_protection` and `prevent_destroy` protect the *resource*, and nothing in the original design protected the *data* on its disk. Restoring from a backup is the only answer to a corrupted or wiped filesystem, which no amount of Terraform guardrail prevents.

## Risks / Trade-offs

- **No staging environment yet** → every change goes from PR review straight to prod. *Mitigation*: PR-posted `terraform plan` output for human review, the saved-plan approval flow (Decision 8) so the approver sees the exact diff, required-reviewer approval on the `production` GitHub Environment, and the destroy-policy gate. Staging can be added later as a lower-stakes environment to test against first.
- **CLI-driven means building and maintaining the apply-gating workflow ourselves**, and no HCP run UI/history. *Mitigation*: GitHub Actions run logs serve as the record; the workflow is a one-time cost, not ongoing.
- **The saved plan artifact contains sensitive values in cleartext.** A `tfplan` file is not encrypted and may embed variable values and resource attributes. *Mitigation*: keep the repository private, set the shortest workable artifact retention, and restrict who can download run artifacts. If the repo ever goes public, the artifact must be symmetrically encrypted with a key from repository secrets before upload.
- **Off-the-shelf misconfiguration scanning gives us almost nothing for Hetzner** (Decision 5), so any real policy coverage is custom work we own and must maintain. *Mitigation*: keep the custom policy set deliberately small and focused on rules that would actually cause an incident; rely on module design over scanning wherever the unsafe state can be made unrepresentable.
- **Nightly drift detection may produce noise** from provider-managed attributes that change outside Terraform's control (e.g., Hetzner-assigned fields). *Mitigation*: address with `lifecycle.ignore_changes` on specific attributes as false positives are discovered — not solved preemptively.
- **Single Hetzner project/token for prod** means a compromised token affects the only environment that exists. *Mitigation*: acceptable for now since there is nothing to isolate from yet; revisit when staging is added.
- **A single write-capable token, if repo-wide, would make the approval gate cosmetic** — any workflow run (including PR-time plan) could read it before approval. *Mitigation*: split Hetzner tokens by privilege. A **Read Only** `HCLOUD_TOKEN` lives as a repo secret for plan jobs; a **Read & Write** `HCLOUD_TOKEN` lives in the `production` Environment for the gated apply job (same name, environment secret wins for gated jobs). Consequently, **no plan job may declare `environment: production`** — doing so would both block every PR on manual approval and hand the write token to an ungated job, collapsing the whole scheme. See the "Credential Scoping by Privilege" requirement in the iac-cicd-pipeline spec.

## Migration Plan

Greenfield setup — no existing state or infrastructure to migrate. Rollout order:
1. Create the HCP Terraform organization/workspace (`infrastructure-prod`, CLI-driven, **Execution Mode = Local**), configure the GitHub OIDC trust relationship for dynamic credentials, and create the Hetzner Cloud project plus its Read Only and Read & Write tokens.
2. Configure repository settings: branch protection on `main` (require PR, require status checks, no force-push), default `GITHUB_TOKEN` permissions set to read-only, the `production` Environment with a required-reviewer rule, and the split `HCLOUD_TOKEN` secrets at repository and Environment scope.
3. Scaffold repo tooling: `.gitignore`, `.pre-commit-config.yaml`, `commitlint` config, `.tflint.hcl`, `dependabot.yml`.
4. Write `modules/server` (with firewall, key-only SSH, `delete_protection`, backups) and `environments/prod` consuming it. Run `terraform init` to generate and commit `.terraform.lock.hcl`.
5. Open a PR to validate the full pipeline (fmt/lint/Trivy/gitleaks/plan-comment/destroy-policy gate) end-to-end before any real `apply`.
6. Merge, read the plan summary in job A, approve the gated apply, and confirm the server is created.
7. Trigger the drift workflow manually to confirm it runs clean and that its issue-reporting path works (verify by making a deliberate out-of-band change, then reverting it).

Rollback: since this is the first infrastructure in the account, "rollback" means `terraform destroy` via the same gated pipeline — which now requires clearing `delete_protection` and passing the destroy-policy gate's override label, deliberately. No separate rollback path is needed at this stage.

## Open Questions

- Server sizing/region/image: left to be filled in as `terraform.tfvars` during implementation, not a blocking design decision.
- Which source CIDRs the firewall should allow for SSH. A static office/home IP is the safe answer; if the operator's IP is dynamic, this needs a decision between a permissive range and an alternative access path (e.g. a bastion or VPN), and that choice should be made before the first apply rather than defaulted to `0.0.0.0/0`.
- Whether the destroy-policy override mechanism should be a PR label, a commit-message trailer, or a `workflow_dispatch` input. Label is assumed for now; settle on first contact.
