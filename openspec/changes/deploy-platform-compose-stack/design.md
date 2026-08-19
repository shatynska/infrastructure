## Context

See proposal.md for why. This builds on two decisions already made outside
this document: the deploy mechanism is GitHub Actions over SSH (not
systemd+git-pull, not Watchtower, not manual), and it reuses the same
`production` GitHub Environment already gating Terraform's apply workflow
(see `iac-cicd-pipeline`'s Gated Production Apply requirement for the
precedent this mirrors). The account it authenticates as is provisioned by
`bootstrap-ansible-host-baseline`, which this change depends on.

**No independent test-authoring dispatch for this change.** Unlike the
sibling Ansible change (which adopts Molecule), this repo has no
established convention for locally testing GitHub Actions workflows or
Compose stacks, and none is introduced here — `docker compose config`
validation, the manual credential-scoping and concurrency checks, and
gitleaks (all already in tasks.md) are this change's verification bar.
Introducing a local workflow-test runner (e.g. `nektos/act`) was
considered and deferred as unnecessary scope: workflow correctness is
exercised by the real PR/merge run itself, which every task in this change
already depends on running successfully.

## Goals / Non-Goals

**Goals:**
- A `platform/docker-compose.yml` running Traefik and Postgres, reachable by
  a future application repo via a shared external Docker network.
- A GitHub Actions workflow that validates on PR and deploys on merge,
  gated the same way Terraform applies are gated.

**Non-Goals:**
- Deciding per-application database/user provisioning mechanics — noted as
  a follow-up in proposal.md.
- Changing `web_allowed_cidrs` at the Terraform layer — not needed, it's
  already set to `["0.0.0.0/0"]` (corrected from an earlier, incorrect
  "currently unset" assumption; see the sibling change's design.md for
  how that error was made). This stack's Compose file and workflow can be
  built and merged independent of the sibling change's UFW work, but
  Traefik won't actually be reachable until that sibling change's host
  firewall rules also allow 80/443.
- Choosing the deploy account's restriction shape or its privileged
  command — settled by `bootstrap-ansible-host-baseline`, not here: a
  plain restricted user (ordinary `scp`/`ssh`, no SSH-layer forced
  command) whose only privileged capability is `sudo`-triggering one
  fixed, argument-free wrapper script,
  `/usr/local/bin/platform-compose-deploy`, at `/opt/platform` (that
  account's home directory). This change's workflow only needs to call
  that one command — it does not construct or pass any `docker compose`
  arguments itself.

## Decisions

**PR validation has no computed-diff-against-live-state step.** Unlike
Terraform, there's no live host state to diff against — `docker compose
config` only renders and validates the YAML locally, so the PR's own file
diff on `platform/docker-compose.yml` is what a PR-time reviewer, if any,
would look at. This remains a genuinely lesser guarantee than Terraform's
`terraform plan`, which computes drift against real infrastructure — that
gap isn't closed by anything in this change and is accepted as-is (revisit
by adding a read-only SSH step diffing image digests against what's
currently running, if this ever proves insufficient).

**A second, separate diff-visibility step covers the approval gate
itself — this is not the same guarantee as the PR-time review above, and
does not depend on it.** On review, `bootstrap-ansible-host-baseline`'s
design.md was found to rely on a claim this change didn't actually
deliver: that the `deploy` account's content-layer escalation risk (it
necessarily owns the directory the wrapper script applies as root) is
contained by "a human approving the exact diff before the key becomes
readable." Two things undercut that as originally written: this repo's
branch protection (`iac-cicd-pipeline`) requires only a passing status
check to merge, not an approving review — so a PR could merge unreviewed
by a second person — and nothing here showed the `production` Environment's
required reviewer the actual diff at approval time, unlike `apply.yml`'s
job-summary step for Terraform.

Fixed by adding the same pattern `apply.yml` already uses: a job that
declares no `environment:` (so it never touches the deploy credential),
computes the diff this merge introduces under `platform/**` (via the
push event's `before`/`after` SHAs, not assuming a single-commit merge),
and writes it to the run's job summary — before the `production`
Environment's approval gate is presented. This makes the guarantee true
regardless of whether the originating PR had an approving review: the
Environment's required reviewer sees the exact content about to be
deployed at the moment they approve it. See the new "Reviewer Sees the
Exact Diff Before Approving" requirement and tasks.md §3.

This is now the accurate statement of what contains
`bootstrap-ansible-host-baseline`'s accepted content-layer risk: not "PR
review happened," but "the Environment's required reviewer saw this exact
diff immediately before approving." That sibling change's design.md has
been corrected to say so.

**Deploy job authenticates via `scp` + `ssh`** (not a stdin-piped tarball),
per the plain-restricted-user decision inherited from
`bootstrap-ansible-host-baseline`. Sequence:

1. `scp platform/docker-compose.yml` and the rendered `.env` to
   `/opt/platform/` — `deploy`'s home directory, already created
   `deploy`-owned by `bootstrap-ansible-host-baseline`. This change
   provisions nothing there itself; if the directory is ever missing,
   that is a defect in the sibling change, not something this workflow
   works around.
2. `ssh deploy@host chmod 600 /opt/platform/.env` — tightens the just-
   transferred secrets file, satisfying `iac-platform-services`'s
   "restrictive permissions" requirement on rendered secret files.
3. `ssh deploy@host sudo /usr/local/bin/platform-compose-deploy` — the
   one fixed, argument-free command `bootstrap-ansible-host-baseline`'s
   `sudoers.d` rule permits. This workflow never passes `-f`, a working
   directory, or any other argument: the wrapper script already `cd`s to
   `/opt/platform` and knows which compose file to use, so there is
   nothing here to fall out of sync with that rule's exact-match grant.

`platform-compose-deploy`'s `docker compose up -d --wait` blocks until
every service is running/healthy and exits non-zero otherwise, so step 3
alone fails this job on a partial deploy — see the post-deploy-check risk
below; no separate `docker compose ps` step is added, since `deploy` has
no unprivileged way to reach the Docker socket in the first place.

**Platform PR-validation is added to the existing `pr-validation.yml`
job, not a new workflow.** That workflow is already this repo's required
status check, deliberately structured with no workflow-level `paths:`
trigger and an internal `dorny/paths-filter` step so it reports a
conclusion on every pull request (see `iac-cicd-pipeline`'s Required
Status Checks Report on Every Pull Request requirement). Adding a
*separate*, `platform/**`-path-triggered workflow and marking it required
would reproduce the exact anti-pattern that existing requirement was
written to prevent — such a workflow never reports for PRs that don't
touch `platform/**`, leaving them permanently unmergeable. Instead, this
change adds a `platform` key to the existing job's `dorny/paths-filter`
step and conditions its new `docker compose config` step on
`steps.changes.outputs.platform == 'true'`, exactly mirroring how the
existing `terraform` filter key conditions the Terraform-specific steps.
The deploy job (post-merge, `production`-gated) is unaffected by this and
remains its own, separate, non-required workflow — only the PR-time
validation step needs to live inside the required check.

**One shared `production` Environment, not a separate one.** Considered
splitting into a `platform-production` Environment with its own approvers,
to scope "restart Traefik/Postgres" separately from "reprovision the
server." Decided against for now — same approvers, and there's no current
need to differentiate. Revisit if the approver list for infrastructure and
for application-platform changes needs to diverge.

## Risks / Trade-offs

- [No computed diff against *live state* before approval, unlike
  Terraform's plan] → Mitigated by keeping the Compose file small and by
  the PR diff being directly readable; accepted as a real, lesser
  guarantee than Terraform's pipeline offers on this specific axis (see
  Decisions above). This is distinct from — and not to be conflated with —
  diff *visibility at approval time*, which this change does provide (see
  next entry); what remains lesser than Terraform is only the absence of a
  diff computed against the host's actual running state.
- [Branch protection doesn't require an approving PR review, so a
  `platform/**` change could merge with no second person having read it]
  → Mitigated, for the specific risk this matters for
  (`bootstrap-ansible-host-baseline`'s accepted content-layer escalation),
  by the "Reviewer Sees the Exact Diff Before Approving" job-summary step:
  the `production` Environment's required reviewer sees the exact diff
  immediately before approving, independent of whether PR-time review
  happened. This does not add a general code-review requirement to this
  repo — it only guarantees *someone* sees the exact content before the
  deploy credential becomes readable.
- [Shared Postgres instance means one compromised or misbehaving
  application could affect every application's database] → Out of scope
  for this change (inherent to the already-decided "one shared instance"
  requirement in `iac-platform-services`); mitigation is future work
  (connection limits, per-database roles) if it becomes a problem.
- [This stack can be merged before `bootstrap-ansible-host-baseline`'s UFW
  rules actually allow 80/443 at the host layer, producing a Traefik that
  can't obtain ACME certificates yet] → Acceptable: the stack simply won't
  serve public HTTPS until that sibling change's host firewall rules land;
  no broken intermediate state, just an inert one. (Earlier drafts of this
  entry attributed the blocker to an unset `web_allowed_cidrs` at the
  Terraform layer — that was incorrect; the cloud firewall already allows
  it, the sibling change's host-level UFW rules are the actual remaining
  prerequisite.)
- [`docker compose pull` succeeds but `up -d` fails partway (bad `.env`,
  port conflict, image pull auth), leaving a mixed running/updated state]
  → Mitigated by `platform-compose-deploy`'s use of `docker compose up -d
  --wait`, which blocks until every service is running/healthy and exits
  non-zero otherwise — this fails the SSH step, and therefore the deploy
  job, loudly rather than leaving a silent partial deploy. No automated
  rollback is implemented, so recovery from a failed deploy remains manual.
- [The `.env` transferred by `scp` could be left at a non-restrictive
  permission mode, readable by other accounts on the host] → Mitigated by
  an explicit `chmod 600` step immediately after transfer (see Decisions
  above), satisfying `iac-platform-services`'s restrictive-permissions
  requirement.
