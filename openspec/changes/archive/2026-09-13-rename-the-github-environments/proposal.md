## Why

`docs/naming-conventions.md` calls for every name derived from a stack to carry that stack's name, and the two GitHub Environments are the one quarter of that scheme still undelivered: they are `production` and `staging` where the scheme says `main-production` and `main-staging`. Entries 61, 62 and 63 moved the stack directories, the HCP workspaces, the read-only repository secrets, the inventory sources and the Hetzner projects; entry 63 was scoped to move these too and found that GitHub offers no way to rename a deployment Environment, so the move was deferred rather than paid. What it buys is that `production` stops being a name a second tenant collides with, and that the naming document stops carrying a standing exception banner.

The cost was recorded as a credential rotation and **it is not one**. Entry 75 and this change's handoff both assumed the three SSH private halves were unrecoverable, because `docs/bootstrap-a-new-host.md` §0.3 instructs the operator to delete the local private half once it is stored in GitHub. They were not deleted: all three are on the operator's workstation, and `~/.ssh/shatynska-platform` derives a public half byte-identical to the `deploy_apps` entry committed in `ansible/inventory/group_vars/production.yml`. The change is therefore a re-entry of all twenty-one values, rotating nothing, rather than a rotation of three keys through a host nothing automates.

## What Changes

- **The two GitHub Environments move onto the stack axis.** `main-staging` is created; `main-production` already exists, having been left in place by `rename-the-external-services` as its rename probe. Both are populated from the values that exist today, `main-production` keeps the required reviewer it already carries, `main-staging` deliberately gets none, and the old `production` and `staging` Environments are deleted only after the new ones are observed gating real runs.
- **Each stack's `github_environment` declaration flips**, which is the only thing the apply, drift, pull-request and converge workflows read — none of them names an Environment. `.github/workflows/platform-deploy.yml`'s literal `environment:` flips with the production stack's declaration, because `.github/tests` asserts the two are equal.
- **Three literals in `.github/tests` flip**: `PROD_GITHUB_ENVIRONMENT`, `SECOND_ENVIRONMENT_GITHUB_ENVIRONMENT` and `GATED_DEPLOY_ENVIRONMENT`. **Three** name sets in that suite also gain a third source, because the flip would otherwise collapse them onto the stack names and silently narrow what they sweep for.
- **Staging goes first, as a canary.** Its half is six secrets, no unrecoverable value and no reviewer to wait on, so the create-populate-protect-point-verify sequence is exercised where a mistake costs a re-run. Production's half follows in its own pull request.
- **Eight requirement texts stop naming `production` as an Environment.** No requirement is renamed and no scenario title moves. Only the sentences that spell the Environment's name change, with one addition: *Gated Deploy Reuses the Terraform Production Environment* also gains a short non-normative paragraph saying the Environment is named for the stack, so that a reader meeting the requirement after this change does not read the new name as a change of obligation.
- **The commitments to this entry are deleted**, including `docs/naming-conventions.md`'s exception banner, which names whoever archives this change as the one who removes it. They sit in `README.md`, `docs/bootstrap-a-new-host.md`, `docs/naming-conventions.md`, both `pipeline.yml` files, `platform-deploy.yml` and three `.github/tests` modules, and this change's `handoff.md` carries the grep that enumerates them.
- **`docs/bootstrap-a-new-host.md` §6.6's note changes rather than disappearing**: `gh secret set --env` takes the stack after this change and took the environment before it, and that paragraph exists to say which.
- **Nothing is rotated, reissued or invalidated.** All four values the operator found missing from the password manager exist elsewhere and are read back: `PLATFORM_ACME_EMAIL` and `PLATFORM_DEPLOY_HOST` off the running platform stack, `TF_API_TOKEN` from `~/.terraform.d/credentials.tfrc.json` where `terraform login` put it, and the Tailscale OAuth pair from the operator's own records. No SSH key is rotated, no host's `authorized_keys` is edited, and no credential held by any other repository is affected.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-cicd-pipeline`: *Gated Production Apply Applies the Reviewed Plan* and *Scheduled Workflows Report Their Own Liveness* name the `production` Environment in their text and scenarios.
- `iac-platform-deploy-pipeline`: *Pull Request Validation Runs Without Deploy Credentials*, *Gated Deploy Reuses the Terraform Production Environment*, *Reviewer Sees the Exact Diff Before Approving*, *Deploy Job Reaches the Host Over a Private Tailnet* and *Deploy Credential Confined to the Gated Job* each name it.
- `iac-state-management`: *HCP Terraform Access via a Static Token, Unsplit by Privilege* names the `production` Environment as the Environment-scoped half of the `TF_API_TOKEN` pair.

## Impact

**Repository settings, which no committed file can verify.** Creating, populating, protecting and deleting an Environment happens in GitHub, and `.github/tests` may not make a network call — a prohibition that suite asserts of itself. Every claim this change makes about the Environments is therefore an operator observation, and the verification section of `design.md` says which observations and in which order.

**Two failure modes arrive quietly and the design is built against both.** A job naming an Environment that does not exist does not fail: GitHub creates it with no protection rules, so a mis-sequenced flip can leave a production apply, converge or deploy running unreviewed. And `TF_API_TOKEN` exists as both a repository secret and an Environment secret holding the same value, so a new Environment missing it falls back to the repository one and nothing reports the omission — unlike `HCLOUD_TOKEN`, which has no repository-scoped counterpart and fails the apply loudly.

**Files:** `terraform/stacks/main-production/pipeline.yml`, `terraform/stacks/main-staging/pipeline.yml`, `terraform/stacks/main-production/versions.tf`, `terraform/stacks/main-staging/versions.tf`, `.github/workflows/platform-deploy.yml`, `.github/tests/test_environment_agnostic_pipeline.py`, `.github/tests/test_a_second_environment.py`, `.github/tests/test_ci_configuration.py`, `.github/tests/test_the_external_service_names_are_retired.py`, `.github/tests/test_host_converge_workflow.py`, `.github/tests/test_terraform_stacks_are_the_iterated_unit.py`, `docs/naming-conventions.md`, `docs/bootstrap-a-new-host.md`, `README.md`, `platform/README.md`, `docs/deferred-work.md`, `docs/change-queue.md`.

**Not touched:** `target_environment` in either `pipeline.yml`, the Ansible groups `production` and `staging`, `group_vars/production.yml` and `group_vars/staging.yml`, the `--vault-id` labels, and the inventory sources. These are on the environment axis by design and the scheme leaves them there.
