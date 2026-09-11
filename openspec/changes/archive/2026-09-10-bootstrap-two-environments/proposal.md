## Why

`docs/bootstrap-a-new-host.md` is the procedure for standing up the company's infrastructure from this repository, and it stands up **one** server. It says so in as many words: *"Adding a second environment is out of this document's scope … it assumes one environment throughout."*

That was true when it was written and is now the wrong default, by the operator's decision recorded in this change: the company is to have both servers from the start, permanently. `docs/review-2026-09-08-host-readiness.md` frames its question as a second Hetzner host for a company, and `docs/change-queue.md` deliberately excludes company-only findings — neither settles the count, and this change is where the operator's answer is written down. A company following this document today provisions prod, discovers later that a pre-release environment is wanted, and adds it against a running production system — which is the expensive order, and precisely the order this repository took, deliberately, so the company would not have to.

The second environment also changes decisions the document takes in its *first* stages, not its last. One Hetzner project or two is settled at stage 1 and is awkward to revisit afterwards, because a Hetzner volume name is unique per project and the platform stack hardcodes its mount path. Two workspaces, two GitHub Environments and the read-only secret names are stage 2 and 3 decisions. By the time a reader reaches "adding an environment", every one of those has been made for one.

## What Changes

- **Stages 0 to 4 describe two environments throughout** — two Hetzner projects, four Hetzner tokens, two HCP workspaces, two GitHub Environments, two environment directories applied through the pipeline. The reader finishes stage 4 with **two servers running**, prod's reviewed and staging's ungated.
- **The template already carries `terraform/environments/staging/`**, so this is mostly a matter of the document telling the reader to fill in both `tfvars` and set both environments' secrets, rather than to delete one. Stage 3.1's template edits double accordingly: **both** `versions.tf` files carry the template author's HCP `organization`, both `terraform.tfvars` need the stage 1 values and the operator's public key, and the second environment's `pipeline.yml` must be read and accepted rather than inherited unseen.
- **Stage 4 gains the sequence that actually applies.** The document currently tells the reader to push the template to `main` and then read the plan; that push *cannot* produce one. `apply.yml` refuses a push whose comparison base is unresolvable, and a branch's first push has none — the workflow names that case in its own comment and fails closed on purpose. This is a defect the document has today at one environment; the rewrite fixes it rather than doubling it.
- **`gh secret set` reads values from standard input** rather than `--body`, which records the secret in shell history. The document is doubling every one of those commands, so it is the moment to stop copying the worse form.
- **Stage 1 states the project decision as a decision**, with the reasoning `add-a-staging-environment` recorded: a second project isolates the write token, which is what lets a lower environment's apply run ungated, and frees the volume name, which is what keeps `platform/docker-compose.yml` unparameterised across environments.
- **Stage 3 gains the pipeline's own N=2 obligations**: the two read-only secret names must differ, the two GitHub Environment names must differ, discovery fails the pipeline naming both offenders if either collides, and an Environment omitting `HCLOUD_TOKEN` silently resolves the repository secret of that name — which, at two environments, is another environment's token.
- **Stage 4 describes an apply run covering two environments**: prod waits for its reviewer, staging does not, and neither environment's failure withholds the other's apply.
- **Stages 5 to 9 state plainly what the second host cannot have yet**, naming the three mechanisms that are single-environment by construction, each with the queue entry that closes it. A reader must not be left to discover this at stage 6 with two servers already running.
- **A new `docs/change-queue.md` entry** for making `platform-deploy.yml` environment-agnostic, which nothing currently records.
- **Appendix A's secret inventory and Appendix C's company notes** are brought to two environments.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This change edits an operator runbook and a queue file; it changes no behaviour of the pipeline, the modules, the roles or the platform stack, and asserts nothing about them that the specifications do not already say. Every statement it adds about the pipeline's two-environment behaviour is a statement of a requirement that already exists — chiefly *Each Environment Declares Its Own Pipeline Configuration* and *Credential Scoping by Privilege* (`openspec/specs/iac-cicd-pipeline/spec.md`) and *Each Environment Has a Dedicated Hetzner Cloud Project* (`openspec/specs/iac-state-management/spec.md`).

`.openspec.yaml` therefore carries `skip_specs: true`, which is the established form here: four archived changes use it, and `openspec validate --all` fails a zero-delta change without it.

## Impact

- **Modified**: `docs/bootstrap-a-new-host.md` (stages 0–4 rewritten for two environments; stages 5–9 gain explicit limits; Appendix A's secret inventory doubled; Appendix B stated to cover the configured host only; Appendix C's company notes folded in), `docs/change-queue.md` (one new entry, cross-referencing entry 50 rather than duplicating it).
- **Not modified**: every workflow, module, role and Compose file. This change documents the system as it is; where the system cannot do what a company needs, it says so and points at the work rather than describing an intention as though it were a procedure.
- **What the reader ends up with**, and the document will say it in stage 0 rather than stage 4: two servers billed monthly, two hosts to patch and rotate credentials for, one of them configured and one of them bare until the queued work lands.
