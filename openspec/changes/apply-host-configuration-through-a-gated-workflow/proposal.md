## Why

`ansible/playbooks/host-baseline.yml` is the one path to production this repository still leaves to a workstation. The Terraform layer reaches Hetzner only through a gated pipeline, and the platform layer reaches the host only through `platform-deploy.yml`; the host layer is applied by hand, with the Vault password on exactly one machine and the tailnet auth key typed at a prompt.

`AGENTS.md` says nothing ships from a local machine and that local production credentials are for reading. A converge that changes UFW rules, `authorized_keys` or the container runtime is at least as consequential as a Compose change, and 41 commits touched `ansible/` in the 60 days to 2026-09-09, so this is not a dormant layer. The Vault password existing on one machine is the sharper edge: lose it and the host cannot be converged at all, by anyone, and a second operator today means handing over that password and a root key.

The block that held this back is gone. `configure-the-staging-host` made the play take its environment as a parameter, gave staging an inventory source and a `group_vars` of its own, and made a run that reaches no host fail instead of exiting 0 — which matters more in CI than locally, since a workflow reporting green over a converge that touched nothing is exactly the failure an unattended job hides. Staging was converged on 2026-09-10, so there is a non-production host to develop this against.

## What Changes

- **A new `.github/workflows/host-converge.yml`**, shaped like `platform-deploy.yml`: a credential-less `diff` job that writes the `ansible/` diff this merge carries to the job summary, then a `converge` job per environment that attaches to that environment's own GitHub Environment and runs `ansible-playbook playbooks/host-baseline.yml -i inventory/<environment>.hcloud.yml -e target_environment=<environment>`. Triggered by a merge to `main` touching `ansible/**`, and by `workflow_dispatch` naming one environment.

- **It names no environment.** Discovery enumerates `ansible/inventory/*.hcloud.yml`, and reads the GitHub Environment and the read-only secret name out of that environment's existing `terraform/environments/<name>/pipeline.yml`. It fails closed on every asymmetry: an inventory source with no environment directory, an environment directory with no inventory source or no `group_vars`, a declaration missing a field, and an empty result.

- **The converge reaches the host over the tailnet**, not over the public internet. Each inventory source gains a per-run choice of connection address, defaulting to the public IPv4 it uses today; CI selects the server's name on a runner joined to the tailnet with the OAuth client `platform-deploy.yml` already uses, and resolves that name from `tailscaled`'s own netmap rather than through MagicDNS, so nothing rests on how the runner's resolver is configured. The cloud firewall therefore needs no allowance for GitHub's runners, and entry 25 can close public SSH without locking CI out.

- **No Tailscale auth key moves into CI.** Because CI reaches the host *through* the tailnet, a host that is not on the tailnet is one CI cannot reach at all: the run fails at connection, before any play. `tailscale up` can never usefully run from a CI converge, so the job supplies an empty `tailscale_auth_key` and rejoining a fallen-off host stays operator work from the workstation, which is the only place with a path to it.

- **Two genuinely new secrets per environment, both GitHub Environment-scoped**: the Ansible Vault password, which ends the one-machine problem, and the private half of a dedicated `ansible-ci` keypair distinct from the operator's own root key. Each environment gets its own of both, for the same reason each has its own platform deploy key: one leaked half must not converge both hosts.

- **Production's read-only Hetzner secret is renamed to `HCLOUD_TOKEN_PROD`.** Every environment's GitHub Environment defines `HCLOUD_TOKEN` as its *Read & Write* token, and an Environment secret shadows the repository secret of the same name — so the converge job, which declares an `environment:`, would resolve production's write token from a declaration that says `read_only_secret: HCLOUD_TOKEN`. This change makes the two environments symmetric, on the name `ansible/.envrc.example` already uses locally, and states the rule that produced the collision.

- **`docs/bootstrap-a-new-host.md` gains the split** between the first converge, which is manual because the host is not yet on the tailnet and holds no CI key, and every converge after it, which is a merge.

## Non-Goals

- **Scheduled host drift detection.** `--check --diff` against the live host is a drift signal, not a plan: it needs the credential, so it cannot be the credential-less artifact a reviewer sees before approving, and its baseline is `changed=2` rather than zero — two `get_url` tasks in the `tailscale` role that report drift on every run forever. Removing that baseline means changing those tasks and bringing that role its first Molecule scenario, which entry 3b already owns. Recorded as its own queue entry, which inherits `docs/bootstrap-a-new-host.md` §6.3's paragraph on the `changed=2` baseline.

- **Managing `root`'s `authorized_keys` from a role.** No role manages them today; root's key arrives from Hetzner at server creation. The `ansible-ci` public key is installed out of band, like the operator key and the deploy keys' private halves, and revoking it is a manual edit on the host. Making a role own that file is a lockout-capable change that wants scenarios of its own. Recorded as its own queue entry.

- **Closing public SSH.** Entry 25's, and it waits on this: the ISP `/24` fallback is what makes an unproven CI converge survivable.

- **Factoring the environment-discovery shell into one shared artifact.** This workflow's discovery is deliberately *not identical* to the Terraform body — it runs over a different root and makes a cross-check that body cannot — so it falls outside the identity assertion in `.github/tests`, which is left covering the three Terraform workflows exactly as it does today. It does share idiom and several refusals with them, and that four near-siblings now exist where the decision to keep three copies was taken is recorded as a queue entry.

## Capabilities

- `iac-cicd-pipeline` — MODIFIED. A new requirement placing the host converge in the same gated shape as the Terraform apply and the platform deploy, and a clause on the read-only secret's name that the collision above exposed.
- `iac-host-configuration` — MODIFIED. The connection address a converge uses is selected per run, defaulting to what a workstation uses today; and an environment's inventory source reads its credential from the same name that environment declares as its read-only secret, which was true by coincidence and becomes an obligation now that a workflow depends on it.

## Impact

- New: `.github/workflows/host-converge.yml`, `.github/tests/test_host_converge_workflow.py`, `ansible/requirements.txt` — `ansible-core` alone, pinned to the version `ansible/requirements-test.txt` names, so the Ansible that converges production is the Ansible the Molecule suite verified those roles under.
- Changed: `ansible/inventory/prod.hcloud.yml`, `ansible/inventory/staging.hcloud.yml`, `terraform/environments/prod/pipeline.yml`, `.github/tests/test_environment_agnostic_pipeline.py` — whose pinned expectation of production's read-only secret name, and whose digest-emitter exemption, both rest on the premise the rename retires — `docs/bootstrap-a-new-host.md`, `docs/change-queue.md`, `README.md`.
- Repository settings, operator work: two new Environment secrets per environment, the `staging` Environment's copy of the Tailscale OAuth client, one renamed repository secret, and one public key installed on each host.
