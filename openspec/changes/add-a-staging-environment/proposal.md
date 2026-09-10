## Why

This repository has exactly one environment, and everything it says about
running more than one is a promise. The change `make-the-pipeline-environment-agnostic`
removed the pipeline's own obstacle — `pr-validation.yml`, `apply.yml` and
`drift.yml` discover `terraform/environments/*/` and run per environment, so
adding one changes no file under `.github/workflows/` — but it shipped at N=1,
where every multi-environment path it built is unexercised code. Discovery
emitting two entries, the affected-environment narrowing actually excluding an
environment, `secrets[matrix.environment.read_only_secret]` resolving a second
name, a nightly sweep planning two environments under two credentials: none of
that has ever run. This change runs it. What it does *not* reach — two plan
comments on one pull request, two apply jobs of which one pauses — needs a
change under `terraform/modules/`, and forcing one here would raise a
`production` approval with nothing to approve, which the pipeline's own
specification forbids by name.

Four requirements across three capabilities are written about prod alone, or
about a second environment as a future event. Each is either unmet or stale from
the moment a second environment exists, and no reading of the current tree can
tell which — that is the second reason to add one here rather than discover it
on the company server, where `docs/change-queue.md` entry 49 records that two
environments are needed on a deadline.

A staging environment is also what unblocks entry 23 (gated host configuration),
which should be built against something other than prod, and entry 38 (the
PostgreSQL major upgrade), which needs somewhere to rehearse.

## What Changes

- **A `terraform/environments/staging/` directory** calling the same
  `terraform/modules/server` and `terraform/modules/volume` as prod, with its own
  `pipeline.yml` declaring the GitHub Environment `staging`, the read-only
  repository secret `HCLOUD_TOKEN_STAGING`, and `destroy_policy_gate: false` —
  staging is disposable, which is what that field exists to say.
- **A second Hetzner Cloud project** holding staging's resources, with its own
  Read Only and Read & Write token pair. This isolates staging's write
  credential from prod's, which is what lets staging's apply run without a
  reviewer; it also frees the volume name `main-data`, so
  `platform/docker-compose.yml`'s hardcoded `/mnt/main-data/prometheus` and
  `/mnt/main-data/grafana` need no parameterisation.
- **A second HCP Terraform workspace**, `infrastructure-staging`, with Execution
  Mode set to Local — the saved-plan approval flow does not work under remote
  execution.
- **A `staging` GitHub Environment** with no required reviewer, holding its own
  `HCLOUD_TOKEN` (staging's Read & Write token) and `TF_API_TOKEN`, and a
  repository secret `HCLOUD_TOKEN_STAGING` holding staging's Read Only token.
- **A `.github/dependabot.yml` entry** for `/terraform/environments/staging`,
  which the CI-configuration suite already obliges by comparing that list against
  the tree.
- **Four requirements generalised** from prod to every environment — see
  Modified Capabilities below. One of them, *Environment and Module Folder
  Structure*, is not merely narrow: its ordered-promotion sentence prescribes a
  sequencing mechanism the pipeline does not implement, and at one environment
  that could not be observed.
- **Documentation brought to N=2**: both places the README describes staging as
  anticipated — the non-goals paragraph and the Status paragraph, the latter
  pointing at the change-queue entry this change repurposes — and the `AGENTS.md`
  record of the never-apply-locally boundary, which names prod alone and which
  the *Write Credentials Confined to the Gated Pipeline* requirement obliges this
  change to generalise.
- **The Ansible and platform half of entry 49 is not in this change** — `hosts:
  prod` becoming a parameter, `group_vars/staging.yml`, the first converge, the
  platform stack and DNS. It becomes a new `docs/change-queue.md` entry, so this
  change delivers a provisioned staging host through the pipeline and nothing
  configured on it.
- **Every `docs/deferred-work.md` entry whose revisit trigger names a second or
  staging environment** — six of them — is revisited and its disposition
  recorded, rather than left to go stale unexamined. One entry's body becomes
  factually wrong the day staging exists ("There is one environment, and it wants
  both"), and one entry's trigger genuinely fires, though on the successor change
  rather than this one.
- **Three new `docs/deferred-work.md` entries**: promotion ordering, which is now
  a discipline rather than a mechanism; the pipeline paths that two environments
  still do not exercise, and what would; and four prod-named requirements this
  change deliberately leaves prod-named.

## Capabilities

### New Capabilities

None. Every mechanism this change exercises is already specified; what changes is
how many environments those specifications describe.

### Modified Capabilities

- `iac-state-management`: *Remote State Backend* and *Workspace Execution Mode
  Set to Local* are stated over the prod environment and the
  `infrastructure-prod` workspace by name. Generalised to one workspace per
  environment, `infrastructure-<name>`, each in Local execution mode. Unmet
  rather than stale: a staging workspace left in the default remote mode breaks
  `terraform plan -out=tfplan` and nothing in the repository would say so.
- `iac-state-management`: *Dedicated Hetzner Cloud Project for Prod* is stated
  over prod alone. Generalised to every environment operating against its own
  dedicated project, which is where the decision to give staging a second project
  is recorded as a requirement rather than only in this change's design.
- `iac-repo-foundations`: *Environment and Module Folder Structure* prescribes
  that ordered promotion "SHALL be achieved by sequencing apply jobs within a
  single workflow (lower environment first, then the gated production
  environment)". The apply workflow runs environments as an unordered matrix, so
  this becomes an unmet obligation at N=2. Modified to state where promotion
  ordering actually comes from, and its residue recorded.
- `iac-safety-hardening`: *Write Credentials Confined to the Gated Pipeline*
  says its record "is generalised by the change that adds a second, at the point
  where there is a second token to confine". This is that change.

## Impact

- **New**: `terraform/environments/staging/` (`main.tf`, `variables.tf`,
  `terraform.tfvars`, `versions.tf`, `ssh_key.tf`, `outputs.tf`, `pipeline.yml`,
  `.terraform.lock.hcl`).
- **Modified**: `.github/dependabot.yml`, `README.md`, `AGENTS.md`,
  `docs/change-queue.md` (entry 49 replaced by its remaining half; entry 23's
  block lifted), `docs/deferred-work.md`, and the four specifications above.
- **Unmodified, deliberately**: every file under `.github/workflows/`. That is
  the claim *Each Environment Declares Its Own Pipeline Configuration* makes, and
  this change is its first real test. A workflow edit turning out to be necessary
  is a finding, not a licence.
- **Outside the repository**: a Hetzner Cloud project and two API tokens, an HCP
  Terraform workspace, a GitHub Environment and three secrets — plus provisioning
  this working tree with staging's read-only token and HCP credentials, without
  which the lockfile cannot be generated. These are operator steps; none can be
  performed or verified by a commit.
- **Cost**: one 2-vCPU Hetzner instance plus a 10 GB volume, running
  continuously — roughly half prod's bill.
- **Not affected**: `ansible/`, `platform/`. Staging is provisioned by this
  change and configured by its successor.
