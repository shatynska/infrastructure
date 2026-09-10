# Bootstrapping a new host from this repository

This is the end-to-end procedure for standing up a new server, and the repository and accounts around it, using this repository as the template. It is written for a developer who has shipped application code but has not run infrastructure before, so it names every account, every secret, and where each secret's value comes from, in the order you will need them. It is also the document to start from when the host has to be rebuilt, or when someone else has to take the system over.

What you will have at the end:

- A Hetzner Cloud server with a firewall and a data volume, created and changed only through reviewed pull requests.
- The server configured (Docker, host firewall, a private network, restricted deploy accounts) by Ansible.
- A shared platform stack on it: Traefik with automatic TLS, PostgreSQL, Prometheus, Alertmanager, Grafana, alerts to Slack, and an external heartbeat.
- A path for any application repository to deploy itself to the host from its own GitHub Actions workflow.

**How to read this.** Stages are in dependency order; do not skip ahead. Each stage ends with a **Secrets created in this stage** table and a **Check** list. `<angle brackets>` are placeholders you replace. "Operator" means the person doing this. Commands are run from the repository root unless a `cd` is shown. The reasoning behind most decisions is in `openspec/specs/` and in the archived changes under `openspec/changes/archive/`; this document only says what to do.

**Time.** Roughly one working day for stages 0 to 7 if nothing goes wrong, mostly waiting on approvals and DNS. Stage 8 is repeated per application.

## Stage 0. Accounts, tools and keys

Nothing here touches a server. It is the shopping list.

### 0.1 Accounts you will create or need access to

| Service | Used for | Who owns the account |
|---|---|---|
| GitHub | The repository, CI, the approval gate, the container registry (GHCR) | The company organisation, not a personal account |
| Hetzner Cloud | The server, firewall, volume, backups | The company, with billing set up |
| HCP Terraform (app.terraform.io) | Storing Terraform state and locking it | The company; the free tier is enough |
| Tailscale | A private network between the server, CI runners and operators | The company; the free plan is enough for now |
| Slack | Alert delivery | The company workspace |
| A heartbeat service (Healthchecks.io or similar) | Noticing when the whole host or its alerting dies | The company |
| A DNS provider | Pointing hostnames at the server | Wherever the company's domain already lives |

Use a shared company password manager for every credential in this document. Several values below exist in exactly one place after they are created, and the password manager is that place.

### 0.2 Tools on your workstation

Install these once. Versions are pinned by the repository where it matters.

| Tool | Why |
|---|---|
| `git`, `gh` (GitHub CLI, logged in with `gh auth login`) | Repository and settings |
| `terraform` 1.9 or newer | Local `plan` and `validate`; never `apply` |
| `tflint`, `gitleaks`, `pre-commit` | Local checks that mirror CI |
| Python 3.12 and `uv` | Ansible and its test toolchain |
| Docker (Docker Desktop on Windows/macOS, or the engine on Linux) | Molecule tests only |
| `direnv` (optional but recommended) | Loads the read-only Hetzner token only inside this directory |
| Tailscale client | Reaching the server over the private network |

Follow `README.md`, "Local setup", steps 1 to 5. Step 5 installs Ansible into a virtual environment and the Galaxy content into `ansible/roles/`; the `-p ansible/roles` flag there is required, not optional.

### 0.3 SSH keys you will generate

Generate each with `ssh-keygen -t ed25519`. Never reuse one key for two purposes; each has a different holder and a different blast radius.

| Key | Command | Passphrase | Private half lives in |
|---|---|---|---|
| Operator key | `ssh-keygen -t ed25519 -f ~/.ssh/<company>-prod -C "<you>@<company> prod root"` | Yes | Your workstation only. This is `root` on the server. |
| Operator inspection key | `ssh-keygen -t ed25519 -f ~/.ssh/<company>-prod-ops -C "ops-<you>"` | Yes | Your workstation. Unprivileged login, used daily instead of root. |
| Platform deploy key | `ssh-keygen -t ed25519 -f platform_deploy_key -N "" -C "deploy@platform"` | **No** (CI cannot type one) | GitHub secret only; delete the local file after storing it |
| One deploy key per application | `ssh-keygen -t ed25519 -f <app>_deploy_key -N "" -C "<app>-deploy"` | **No** | That application's GitHub secret only |

Keep the `.pub` halves; they are committed to the repository in later stages and are not secret.

## Stage 1. Hetzner Cloud

### 1.1 Register and create a dedicated project

1. Register at console.hetzner.cloud, complete identity verification, add a payment method.
2. Create a project named `<company>-prod`. One project per environment: the API tokens below are scoped to a project, and that scope is what keeps a leaked read-only token from reading anything else.
3. Do **not** create a server, firewall or volume in the console. Terraform creates them in stage 4, and anything created by hand is drift the nightly check will report.

### 1.2 Create two API tokens

In the project: Security → API tokens → Generate API token.

| Token | Permission | Where it goes | Never goes |
|---|---|---|---|
| Read Only | Read | Your workstation (`.envrc`, stage 4) and the repository secret `HCLOUD_TOKEN` (stage 3) | Nowhere else |
| Read & Write | Read & Write | The `production` Environment secret `HCLOUD_TOKEN` (stage 3) | Any local file, shell, or note. If you can run `terraform apply` from your laptop, this token is in the wrong place. |

Each token is shown once. Put both in the password manager immediately.

### 1.3 Decide the sizing and record it

You will write these into `terraform/environments/prod/terraform.tfvars` in stage 3. Decide them now.

| Setting | Guidance | This repository's value |
|---|---|---|
| `location` | Pick one datacenter and stay in it; the volume cannot move | `hel1` (Helsinki); `fsn1` and `nbg1` are the German alternatives |
| `server_type` | `cx33` is 4 vCPU / 8 GB; for several services start at `cx43` (8 vCPU / 16 GB) or a `cpx` type. You can resize later, but only upward without a rebuild | `cx33` |
| `image` | A current Ubuntu LTS | `ubuntu-26.04` |
| `volume_size` | GB for Prometheus and Grafana state (and future logs); resizable upward only | `10` |
| `ssh_allowed_cidrs` | The public IP ranges allowed to reach SSH. Must not be `0.0.0.0/0`. If everyone will use Tailscale, see `docs/change-queue.md` entry 25 for closing public SSH entirely | one ISP `/24` |
| `web_allowed_cidrs` | `["0.0.0.0/0"]` for a public web host | `["0.0.0.0/0"]` |

**Secrets created in this stage:** the two Hetzner tokens, held in the password manager until stage 3.

**Check:** the project exists and is empty; both tokens are in the password manager, labelled with their permission level.

## Stage 2. HCP Terraform

Terraform needs somewhere to keep its state file (the record of what it created) that both your workstation and CI can reach, with a lock so two runs cannot overlap. HCP Terraform provides exactly that, and this setup uses nothing else from it.

1. Register at app.terraform.io and create an organisation named `<company>`.
2. Create a workspace: **CLI-driven workflow**, named `infrastructure-prod`. No VCS connection.
3. In the workspace's Settings → General, set **Execution Mode** to **Local**. This is essential: the default, Remote, would run plans on HCP's machines and break the saved-plan flow the pipeline depends on.
4. Create an API token: User Settings → Tokens → Create an API token (or an organisation token under Organisation Settings → API Tokens). One token; this tier has no way to split it by privilege, and the Hetzner token split in stage 1 is the real security boundary.
5. On your workstation, run `terraform login` and paste the same token when asked. It is stored in `~/.terraform.d/credentials.tfrc.json`.

**Secrets created in this stage**

| Name | Value | Stored where (stage 3) |
|---|---|---|
| `TF_API_TOKEN` | The HCP Terraform API token | Repository secret **and** `production` Environment secret, identical value |

**Check:** the workspace shows Execution Mode: Local and has no runs.

## Stage 3. The GitHub repository

### 3.1 Create the repository from this one

1. In the company organisation, create an empty **private** repository named `infrastructure`. Private, because the tree will contain your office IP ranges, server identifiers and internal hostnames.
2. Copy this repository's tree into it. The simplest faithful way:

   ```sh
   git clone https://github.com/shatynska/infrastructure <company>-infrastructure
   cd <company>-infrastructure
   git remote set-url origin git@github.com:<company>/infrastructure.git
   ```

   Keeping the history keeps the reasoning behind every file. If you prefer a clean history, `rm -rf .git && git init` first; the `openspec/` archive still carries the reasoning either way.

3. Find every reference to the original owner and replace it:

   ```sh
   grep -rn 'shatynska' --exclude-dir=.git --exclude-dir=openspec .
   ```

   The ones that matter: the `organization` in `terraform/environments/prod/versions.tf` (your HCP organisation from stage 2), `ghcr_pull_username` in `ansible/inventory/group_vars/prod.yml` (stage 6), the `Documentation=` URL in `ansible/roles/image_prune/tasks/main.yml`, and prose in `README.md`.

4. Edit `terraform/environments/prod/terraform.tfvars` with the stage 1 decisions, and put the **public** half of your operator key from stage 0 into `ssh_public_key`. Everything in this file is non-secret and committed.

5. Delete the `moved` block at the bottom of `terraform/environments/prod/ssh_key.tf`. It records a one-time relocation in the original repository and is meaningless in a fresh state.

6. Run `pre-commit install --hook-type pre-commit --hook-type commit-msg` so your commits are checked the way CI checks them.

Do not push yet. The first push to `main` triggers the apply workflow, and it must find its secrets in place.

### 3.2 Repository settings

All of these are in Settings on github.com, or via `gh`.

1. **Environment.** Settings → Environments → New environment: `production`. Add the protection rule **Required reviewers** and name at least one person. For a company, this person should not be the only person who opens pull requests; the Environment approval is the human gate every production change passes through.
2. **Label.** Issues → Labels → New label: `destroy-override`. A merged pull request must carry this label for the apply workflow to accept a plan that deletes or replaces a resource. Without it, such plans fail on purpose.
3. **Workflow token.** Settings → Actions → General → Workflow permissions: **Read repository contents and packages permissions**. Each workflow declares the little it needs on top.
4. **Merge methods.** Leave merge commits enabled. The destroy gate reads the pull request number from the merge commit message; squash and rebase merges fall back to a slower API lookup.

### 3.3 Secrets

Repository secrets: Settings → Secrets and variables → Actions → Repository secrets. Environment secrets: Settings → Environments → production → Environment secrets. Or with `gh`:

```sh
gh secret set HCLOUD_TOKEN --body '<read-only token>'
gh secret set HCLOUD_TOKEN --env production --body '<read & write token>'
gh secret set TF_API_TOKEN --body '<hcp token>'
gh secret set TF_API_TOKEN --env production --body '<hcp token>'
```

**Secrets created in this stage**

| Name | Scope | Value from | Read by |
|---|---|---|---|
| `HCLOUD_TOKEN` | Repository | Stage 1, Read Only token | PR plans, drift detection, the apply workflow's plan job, the Ansible inventory |
| `HCLOUD_TOKEN` | `production` Environment | Stage 1, Read & Write token | The apply job only, after approval. GitHub resolves an Environment secret ahead of a repository secret of the same name, which is the whole mechanism. |
| `TF_API_TOKEN` | Repository | Stage 2 | Every Terraform job |
| `TF_API_TOKEN` | `production` Environment | Stage 2, same value | The apply job |

**Check:** four secrets set; `production` shows one required reviewer; the label exists; the repository is private.

## Stage 4. First Terraform apply: the server exists

### 4.1 Prove the configuration locally

Create `.envrc` from `.envrc.example` with the **Read Only** token, run `direnv allow` (or `source .envrc`), then:

```sh
cd terraform/environments/prod
terraform init
terraform plan
```

`init` connects to the HCP workspace from stage 2. `plan` should propose creating a firewall, an SSH key, a server and a volume, and nothing else. Do not run `apply`: the read-only token would refuse it, and that refusal is the boundary this whole setup relies on.

### 4.2 Push, and approve the first apply

```sh
git add -A && git commit -m "chore: bootstrap <company> prod from the template"
git push -u origin main
```

Open Actions on github.com. Three workflows start: PR Validation and Ansible Verify do nothing useful on a push, but **Terraform Apply (prod)** runs its `plan` job, writes the plan into the run's summary, and then waits on the `production` Environment. Read the summary. If it is the four resources from 4.1, approve. The `apply` job creates them.

### 4.3 Get the address and log in

```sh
cd terraform/environments/prod && terraform output
```

`server_ipv4_address` is the public address. Log in once as root with the operator key, which also records the host's fingerprint in your `known_hosts` (Ansible requires that in stage 6):

```sh
ssh -i ~/.ssh/<company>-prod root@<ipv4>
```

### 4.4 DNS

In the DNS provider, create an `A` record per hostname an application will serve, pointing at `<ipv4>`. Nothing needs them until an application is routed in stage 8, but they take time to propagate, so create them now. There is no Terraform for DNS, deliberately — see "Managing DNS in Terraform" in `docs/deferred-work.md`, which names the provider (ukraine.com.ua, nameservers `inhostedns.*`) and lists the zone's records as read on 2026-09-08, including the MX and SPF that make an automated migration riskier than it looks.

**Secrets created in this stage:** none. `.envrc` holds the read-only token and is gitignored.

**Check:** `terraform plan` locally now says "No changes"; the nightly Drift Detection workflow, run once by hand from Actions → Drift Detection → Run workflow, also reports no drift; `ssh root@<ipv4>` works with the operator key and nothing else.

## Stage 5. Tailscale

The private network. CI runners join it for the length of one job to reach the server; operators join it permanently. SSH for deploys never crosses the public internet.

### 5.1 Create the tailnet

1. Sign up at tailscale.com with the company's identity provider. The tailnet is created with the first login.
2. Install the Tailscale client on your workstation and log in. Your machine is now on the tailnet.

### 5.2 Access control: allow the CI tag

Access controls → edit the policy file. Add the CI tag so an OAuth client can mint nodes carrying it:

```json
"tagOwners": {
  "tag:ci": ["autogroup:admin"]
}
```

The original host runs with no further restriction, so any tailnet member can reach the server's SSH port. For a company tailnet with more members, add an ACL rule that lets `tag:ci` and operators reach the server on port 22 and port 3000 (Grafana), and nothing else. Do that once the server has joined and you know its tailnet name.

### 5.3 Two credentials

| Credential | Where | Settings |
|---|---|---|
| Auth key for the server | Settings → Keys → Generate auth key | **Reusable**, **not** ephemeral, no tags, expiry as long as allowed (90 days). It is used when Ansible joins the host (stage 6), and again only if the host is rebuilt. After the host has joined, in Machines → the server → **Disable key expiry**, or the host silently drops off the tailnet in 180 days. |
| OAuth client for CI | Settings → OAuth clients → Generate OAuth client | Scope **Auth Keys: Write**, with tag `tag:ci`. Produces a client ID and a client secret. |

**Secrets created in this stage**

| Name | Scope | Value from | Read by |
|---|---|---|---|
| `TAILSCALE_OAUTH_CLIENT_ID` | `production` Environment, infrastructure repository | The OAuth client | `platform-deploy.yml`'s deploy job |
| `TAILSCALE_OAUTH_SECRET` | `production` Environment, infrastructure repository | The OAuth client | Same |
| The server auth key | Password manager only, no GitHub secret | The auth key | You, at the Ansible prompt in stage 6 |

Each application repository will need the same two OAuth values in stage 8; one OAuth client can serve all of them.

**Check:** your workstation appears in Machines; `tag:ci` appears in the policy file without a syntax error.

## Stage 6. Ansible: configure the host

This stage is run from your workstation. It installs Docker, the host firewall and fail2ban, joins the tailnet, creates the `deploy` account with a forced-command key per application, creates your unprivileged operator account, mounts the data volume, and arms the weekly image prune.

### 6.1 Fill in the inventory variables

Edit `ansible/inventory/group_vars/prod.yml`. Every value except the last two is non-secret and committed; those two are Vault-encrypted in place.

| Variable | Set to |
|---|---|
| `hardening_ssh_allowed_cidrs` | Exactly the `ssh_allowed_cidrs` list from `terraform.tfvars`. They are kept in sync by hand; a mismatch makes the host firewall block what the cloud firewall allows. |
| `hardening_web_allowed_cidrs` | Exactly `web_allowed_cidrs` from `terraform.tfvars` |
| `deploy_apps` | One entry: `name: platform`, `public_key:` the `.pub` of the platform deploy key from stage 0. Applications are added here in stage 8. |
| `ops_user_accounts` | One entry: `name: ops-<you>`, `public_key:` the `.pub` of your operator inspection key |
| `platform_data_volume_subdirs` | Leave as is |
| `ghcr_pull_username` | The GitHub username whose token is below. For an organisation, a dedicated machine user with read access to the application repositories is cleaner than a person's account. |
| `ghcr_pull_token` | Vault-encrypted, see below |
| `image_prune_heartbeat_ping_key` | Vault-encrypted, see below. **The play refuses to run without it** |

**The GHCR token.** The host must log in to GitHub's container registry to pull private application images. On github.com as the user above: Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate, scope **`read:packages`** only, expiry of your choice (note it in the password manager: when it expires, deploys start failing at `docker compose pull`).

Choose a Vault password, store it in the password manager, then encrypt the token in place:

```sh
cd ansible
ansible-vault encrypt_string --vault-id prod@prompt '<ghp_... token>' --name ghcr_pull_token
```

Paste the output block into `group_vars/prod.yml` in place of the existing `ghcr_pull_token` value. The encrypted block is safe to commit; the Vault password is not written anywhere in the repository.

Two things about `encrypt_string` that read as faults and are not:

- **It prompts `New Vault password (prod):` even when the vault already exists.** That is its wording for the encrypt direction, not an offer to create a second vault. Type the password you chose above — or, when adding a value to a file that already has encrypted ones, the password those were encrypted with. Ansible cannot tell you afterwards which password made a block: two values encrypted under different passwords produce a file that fails to decrypt with either, naming neither.
- **It only prints.** It writes to your terminal and edits nothing; copying its output into the file is a separate step you perform. The whole block goes in, `<name>: !vault |` line included.

Whenever you add an encrypted value, confirm the file still decrypts as a whole — this prints the value's length, never the value:

```sh
ansible localhost -m debug -a 'msg={{ <variable> | length }}' \
  -e @inventory/group_vars/prod.yml --vault-id prod@prompt
```

**The heartbeat ping key.** The `image_prune` role installs a weekly unit that reports each activation to an external observer, and it **asserts this input before any role in the play changes the host** — so an absent key aborts `host-baseline.yml` rather than installing a scheduled unit nothing watches.

Create it now, at the heartbeat service from stage 0.1: **Settings → Ping key → create**. One key addresses every periodic job's check, and the same value becomes the `HEARTBEAT_PING_KEY` repository secret in stage 7.3. Put it in the password manager, then encrypt it the same way:

```sh
cd ansible
ansible-vault encrypt_string --vault-id prod@prompt '<ping key>' --name image_prune_heartbeat_ping_key
```

The key must be a bare token of letters, digits, `_` and `-`; the role refuses anything else by name, because the value is rendered into a shell file its reporting script sources and a quote in it would make that script fail silently.

### 6.2 Check the inventory resolves

The inventory is dynamic: it asks the Hetzner API which servers exist and groups them by their `environment` label. It needs the read-only token from `.envrc`.

```sh
cd ansible
ansible-inventory -i inventory/hcloud.yml --graph
```

You should see your server under `@prod`. If you see nothing, `HCLOUD_TOKEN` is not set in this shell.

### 6.3 Run the playbook

```sh
cd ansible
ansible-playbook playbooks/host-baseline.yml \
  --vault-id prod@prompt \
  --private-key ~/.ssh/<company>-prod \
  -e tailscale_auth_key=<tskey-auth-... from stage 5>
```

Two prompts: the Vault password, and (if the key has one) the operator key's passphrase. A first run takes several minutes; Docker's installation is the slow part. A second run immediately afterwards should report `changed=0`; if it does not, something is not idempotent and worth understanding before moving on.

Do not rely on `--check` for the first run: apt-based tasks report changes they did not make and later tasks then fail against a stale package cache. `--check --diff` is useful on every run after the first.

### 6.4 After the run

1. Tailscale admin → Machines: the server is listed. Note its tailnet IPv4 (`100.x.y.z`). Disable key expiry for it (stage 5.3).
2. Log in the way you will from now on, over the tailnet, unprivileged:

   ```sh
   ssh -i ~/.ssh/<company>-prod-ops ops-<you>@100.x.y.z
   docker ps        # works: the account is in the docker group
   sudo -n true     # refused: the account has no sudo, by design
   ```

   That refusal is real, and it means anything needing root — starting a unit, reading a unit's journal, reading a `0600` file — cannot go through this account. Reach for Ansible instead, which authenticates as `root` with the operator key you already hold:

   ```sh
   cd ansible
   ansible prod -m ansible.builtin.systemd_service \
     -a "name=<unit> state=started" --vault-id prod@prompt
   ansible prod -m ansible.builtin.command \
     -a "journalctl -u <unit> -n 20 --no-pager" --vault-id prod@prompt
   ```

   Plenty is still readable unprivileged: `systemctl is-active`, `systemctl show --property=…`, `systemctl list-timers`, `stat`, and any world-readable file.

3. Commit and push `group_vars/prod.yml` through a pull request. The Molecule suite runs on it; that is the `ansible-verify` check.

**Secrets created in this stage**

| Name | Scope | Value from | Read by |
|---|---|---|---|
| Vault password | Password manager only | You chose it | Anyone running the playbook |
| `ghcr_pull_token` | Encrypted inside `group_vars/prod.yml` | GitHub classic PAT, `read:packages` | The playbook, to log the host's Docker into GHCR |
| `image_prune_heartbeat_ping_key` | Encrypted inside `group_vars/prod.yml` | The heartbeat service's project ping key | The prune unit's reporting script, on every activation. The same value becomes the `HEARTBEAT_PING_KEY` repository secret in stage 7.3 |
| `PLATFORM_DEPLOY_SSH_KEY` | `production` Environment, infrastructure repository | The **private** half of the platform deploy key from stage 0. Store it now, then delete the local file. | `platform-deploy.yml`'s deploy job |
| `PLATFORM_DEPLOY_HOST` | `production` Environment, infrastructure repository | The server's tailnet IPv4 (`100.x.y.z`). A MagicDNS name also works, but the literal IP avoids a resolution step. | `platform-deploy.yml`, for both the SSH target and Grafana's bind address |

**Check:** `sudo ufw status` as root shows default deny with 22, 80, 443 and the tailnet rules; `tailscale status` on the server shows `Running`; `systemctl list-timers` shows `prune-host-images.timer`; `/mnt/main-data` is mounted and holds `prometheus/` and `grafana/`.

**Then prove the prune reports.** Its timer is weekly, so nothing reaches the heartbeat service until it fires — and a reporter that cannot reach the observer leaves a *successful* unit behind by design, so a green `systemctl status` is not evidence. Trigger one activation and read what it says:

```sh
cd ansible
ansible prod -m ansible.builtin.systemd_service \
  -a "name=prune-host-images.service state=started" --vault-id prod@prompt
ansible prod -m ansible.builtin.command \
  -a "journalctl -u prune-host-images.service -n 20 --no-pager" --vault-id prod@prompt
```

The journal should carry `prune-host-images: considered N, removed M` and then a line from `prune-host-images-report` — `Created` on the first activation, which is the observer's own reply to a ping that brought the check into existence. A line reading `reporting … failed` names the endpoint and curl's status instead, and means the check is not being fed. A check named `<inventory_hostname>-prune-host-images` should now exist at the heartbeat service; give it the period and grace from Appendix A.

## Stage 7. The platform stack

Traefik, PostgreSQL and monitoring, deployed by `platform-deploy.yml` on a merge to `main` that touches `platform/`. The workflow renders a `.env` from secrets, joins the tailnet, and pipes the Compose file and `.env` to the server over the forced-command SSH key. Everything below is preparation for that one merge.

### 7.1 Third-party services

**Slack.** In the workspace, create a channel `#alerts`. Then api.slack.com → Your Apps → Create New App → From scratch → enable **Incoming Webhooks** → Add New Webhook to Workspace → choose `#alerts`. Copy the webhook URL. The channel name is fixed in `platform/docker-compose.yml`'s Alertmanager config; change it there if you named the channel differently.

**Heartbeat.** At healthchecks.io (or an equivalent), create a check named `<company>-prod alertmanager`. Period **5 minutes**, grace **5 minutes**: Alertmanager pings it every 2 minutes, and the service must expect pings at least that often but tolerate one missed one. Copy the ping URL. Configure where that service should alert you when pings stop, ideally somewhere other than the same Slack workspace: this is the alarm for when everything else is down.

**Periodic-job heartbeats.** The project ping key already exists — stage 6.1 created it, because the host play refuses to run without it. It addresses one check per periodic job, listed with its period and grace in Appendix A, and it is also the `HEARTBEAT_PING_KEY` **repository** secret in stage 7.3.

Nothing needs creating by hand: each job creates its own check on its first ping (`?create=1`). But an auto-created check carries the vendor's **default** period, so once each appears, set it to the value Appendix A gives — otherwise a weekly job alarms daily and you learn to ignore it. Route these checks to Slack `#alerts`, **not** to the destination the `alertmanager` check above alerts to: that one is the alarm for when everything is down, and a weekly continuous-integration failure must not erode it.

### 7.2 Generate the platform's own passwords

```sh
openssl rand -base64 32   # run three times
```

### 7.3 Secrets

All in the `production` Environment of the infrastructure repository.

| Name | Value from |
|---|---|
| `PLATFORM_ACME_EMAIL` | A monitored company mailbox. Let's Encrypt sends certificate-expiry warnings here. |
| `PLATFORM_POSTGRES_USER` | A name for the shared instance's superuser, for example `platform_admin` |
| `PLATFORM_POSTGRES_PASSWORD` | First generated password |
| `PLATFORM_POSTGRES_EXPORTER_PASSWORD` | Second generated password. You will type it into Postgres by hand in 7.5. |
| `PLATFORM_GRAFANA_ADMIN_PASSWORD` | Third generated password. Grafana's `admin` login. |
| `PLATFORM_SLACK_WEBHOOK_URL` | The Slack webhook URL |
| `PLATFORM_DEADMANSWITCH_URL` | The heartbeat ping URL |

Together with `PLATFORM_DEPLOY_SSH_KEY`, `PLATFORM_DEPLOY_HOST`, `TAILSCALE_OAUTH_CLIENT_ID` and `TAILSCALE_OAUTH_SECRET` from earlier stages, that is the complete set `platform-deploy.yml` reads. If any is missing the deploy job fails at the step that needs it, before touching the server.

One more secret belongs to this stage and is **not** in the table above, because it must not be scoped the way those are:

| Name | Where | Value from |
|---|---|---|
| `HEARTBEAT_PING_KEY` | **Repository** secret — Settings → Secrets and variables → Actions, *not* the `production` Environment | The project ping key stage 6.1 created and put into Ansible Vault, unchanged |

Scoping it to the `production` Environment would break it: a job reading an Environment secret waits on required-reviewer approval, and an alarm that waits for a human to approve its own delivery is not an alarm. The scheduled workflows read it with no `environment:` declared, and they turn red naming it if it is absent.

### 7.4 Deploy

The workflow triggers on a change under `platform/`. Open a pull request that makes one, even a one-line edit to `platform/README.md` naming the company. PR Validation runs `docker compose config` against it. Merge. In Actions, **Platform Deploy** posts the diff to its summary and waits for approval; approve. The deploy job succeeds only when every service reports healthy.

### 7.5 Two manual steps the automation deliberately does not do

**The monitoring role in Postgres.** postgres-exporter connects as a restricted role that nothing creates automatically. From your operator account on the server:

```sh
docker exec -it platform-postgres-1 psql -U <PLATFORM_POSTGRES_USER> -c \
  "CREATE ROLE pgexporter WITH LOGIN PASSWORD '<PLATFORM_POSTGRES_EXPORTER_PASSWORD>'; GRANT pg_monitor TO pgexporter;"
```

Until this is done the `MetricsTargetDown` alert fires for `postgres-exporter`, which is the intended signal that the step is missing.

**The heartbeat.** Nothing to run; confirm in the heartbeat service that pings are arriving every couple of minutes.

**Check:** `docker ps` shows nine `platform-*` containers, all `(healthy)`; `http://100.x.y.z:3000` from your workstation opens Grafana and `admin` with the Grafana password shows three dashboards; the heartbeat service shows the check as up; a test alert (temporarily lower a threshold in the rules and redeploy, then revert) arrives in `#alerts`.

**Secrets created in this stage:** the seven in 7.3.

## Stage 8. Onboarding an application

Repeat this for every service. The infrastructure side is one inventory entry and one playbook run; the application side is one workflow and one Compose file. commerce-ops is the worked example.

### 8.1 Naming rule

The application's name in `deploy_apps` and the last segment of its image repository must be identical: an application named `orders` publishes to `ghcr.io/<org>/orders`. Image reclamation on the host identifies an application's images by that rule and silently reclaims nothing if they differ.

### 8.2 Infrastructure side

1. Generate the application's deploy key (stage 0.3 table).
2. Add to `deploy_apps` in `ansible/inventory/group_vars/prod.yml`:

   ```yaml
   - name: <app>
     public_key: "ssh-ed25519 AAAA... <app>-deploy"
   ```

3. Open a pull request, merge it, then run the playbook (stage 6.3, the tailnet key may be omitted now that the host has joined). This creates `/opt/<app>`, the forced-command `authorized_keys` line, and the sudoers rule that lets that key trigger `app-deploy <app>` and nothing else.
4. Ensure the GHCR user from stage 6.1 can read the application's package. In an organisation, a package pushed by a workflow inherits the repository's access; a machine user needs read access to that repository.

### 8.3 Database

This is settled, and the answer depends on one question about the data: would losing it be tolerable?

- **Durable data** — anything whose loss would not be tolerable — goes to an **external managed service that owns its own backups**, not onto this host. Never into the shared instance: that is absolute, and no backup lifts it, because holding only non-durable data is what makes that instance classifiable as needing none. Not into a PostgreSQL container of the application's own either, unless a logical backup written off the host and a restore rehearsed and checked are both in place before the data lands — *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) is where that is written, and no application has cleared that bar.
- **Non-durable relational data** — a job table, bookkeeping, state whose loss its writer can shrug at — goes in the **shared instance**, never a container of the application's own. That part is unconditional: no backup licenses a private PostgreSQL. From your operator account, create a database and a role:

  ```sh
  docker exec -it platform-postgres-1 psql -U <PLATFORM_POSTGRES_USER> -c \
    "CREATE ROLE <app> WITH LOGIN PASSWORD '<generated>'; CREATE DATABASE <app> OWNER <app>;"
  ```

  The application reaches it at `postgres:5432` over `platform_edge` with that role. Automating this step, and delivering that password the way a deploy key is delivered, is deliberately deferred until an application needs it — see `docs/deferred-work.md`.

  A **non-relational** store — a Redis cache, a queue file, an uploads directory — is not covered by either bullet and does not belong in this instance. It is governed by *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) like any other store on this host, which is to say: name which of its reasons the store satisfies, in the change that adds it, or give it a logical backup written off the host and a rehearsed restore before it holds anything.

  `commerce-ops` runs a PostgreSQL container of its own, which is what the first bullet forbids. That is a known divergence, named as such in the requirement above, and its resolution is in that application's own repository rather than here. Do not read it as a pattern to copy.

### 8.4 Application side

In the application repository:

1. **Anything your Compose file persists — a volume, named or anonymous, or a writable bind mount — has to say why it needs no backup.** Name which reason in *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) the store satisfies, in the change that adds it; a store satisfying none owes a logical backup written off this host and a rehearsed, checked restore before it first holds data. This catches the store a bumped image newly declares as much as one you wrote.
2. A `Dockerfile` and a `docker-compose.yml` whose web service joins the external network `platform_edge` and carries the Traefik labels shown in `platform/README.md`, "Joining the platform network", with its hostname and its container port. Use `env_file: .env` for runtime secrets and `image: ghcr.io/<org>/<app>:${IMAGE_TAG}`.
2. A `production` Environment with a required reviewer, as in stage 3.2.
3. A deploy workflow on push to `main` with two jobs, copied from commerce-ops: a `build-and-push` job (`permissions: packages: write`, `docker/login-action` with `GITHUB_TOKEN`, `docker/build-push-action` tagging the image with `github.sha`), then a `deploy` job on the `production` Environment that joins the tailnet with `tailscale/github-action`, renders `.env` from secrets (including `IMAGE_TAG=${{ github.sha }}`), and runs:

   ```sh
   tar -czf - docker-compose.yml .env | ssh -i ~/.ssh/deploy_key deploy@${{ secrets.DEPLOY_HOST }}
   ```

   The host extracts exactly those two files into `/opt/<app>` and runs `docker compose pull && docker compose up -d --wait`; the job fails if any service does not become healthy.

4. A DNS `A` record for the hostname (stage 4.4). Traefik requests the certificate on the first request to it.

**Secrets created in this stage**, all in the application repository's `production` Environment:

| Name | Value from |
|---|---|
| `TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_SECRET` | The same OAuth client as stage 5, or a second one with the same tag |
| `DEPLOY_HOST` | The server's tailnet IPv4, same value as `PLATFORM_DEPLOY_HOST` |
| `<APP>_DEPLOY_SSH_KEY` | The private half of the key from 8.2; delete the local file after storing |
| `POSTGRES_PASSWORD` and the application's own settings | 8.3, and whatever the application needs |

**Check:** the deploy run is green; `https://<hostname>` answers with a valid certificate; the application appears on Grafana's "Application HTTP error rates" dashboard after its first requests; `docker ps` shows the application's containers `(healthy)`.

## Stage 9. Closing the gates

Do these once the first pull requests have run, since branch protection can only name checks GitHub has seen.

1. **Branch protection** on `main`: require a pull request; require status checks `validate` and `ansible-verify`, strict (branch must be up to date); block force pushes and deletions; include administrators. Required approving reviews: 0 if one person operates the repository, 1 or more for a team.

   ```sh
   gh api -X PUT repos/<org>/infrastructure/branches/main/protection \
     --input - <<'EOF'
   {"required_status_checks":{"strict":true,"contexts":["validate","ansible-verify"]},
    "enforce_admins":true,
    "required_pull_request_reviews":{"required_approving_review_count":0},
    "restrictions":null,"allow_force_pushes":false,"allow_deletions":false}
   EOF
   ```

2. **Dependabot** is configured by `.github/dependabot.yml` and starts on its own. Its pull requests go through the same checks.
3. **Drift Detection** runs nightly. GitHub disables scheduled workflows after 60 days without commits; `README.md` says how to re-enable it. That disabling now announces itself — the workflow reports to a heartbeat check on every run, and a check that stops being reported to alarms — but re-enabling is still a manual act, and a manual `workflow_dispatch` reports too, so it resets the silence timer. After dispatching one to recover a disabled workflow, confirm the schedule itself is enabled rather than reading the green check as evidence.
4. **Pre-commit autoupdate** runs weekly and opens a pull request. Dispatch it once here, so its heartbeat check comes into existence and can be given the period and grace from Appendix A — otherwise the check first appears a week later, on its own schedule.
5. **Prove that silence alarms.** Everything else you have tested proves a ping *arriving*. The whole design rests on the opposite — that a job which stops reporting is as loud as one that fails — and nothing in the repository can demonstrate it, because the alarm belongs to a third party's timeout.

   At the heartbeat service, add a check named `scratch-delete-me`, period **5 minutes**, grace **1 minute**, routed to `#alerts`. Ping it once, then leave it alone:

   ```sh
   curl -fsS https://hc-ping.com/<its-uuid>
   ```

   Within about six minutes Slack should carry *"scratch-delete-me is DOWN. Reason: success signal did not arrive on time, grace time passed."* — with nothing having failed anywhere. Then delete the check; on a 5-minute period it will keep alarming.

   If that message does not arrive, the routing works for failures and not for silence, and every periodic job on this host is unwatched in the one way that matters most.
6. **Record what you built.** In the password manager, alongside each secret, note its expiry, the stage that created it, and what breaks when it expires. In the repository, update `README.md`'s Status section.

## Appendix A. Complete secret inventory

Every credential the system uses, in one place. "Env" means the `production` GitHub Environment.

| Name | Where | Created in | Value from | Breaks when wrong |
|---|---|---|---|---|
| Hetzner Read Only token | `.envrc`; repo secret `HCLOUD_TOKEN` | 1 | Hetzner project → API tokens | Local plans, PR plans, drift detection, Ansible inventory |
| Hetzner Read & Write token | Env secret `HCLOUD_TOKEN` | 1 | Same | The apply job |
| `TF_API_TOKEN` | Repo secret and Env secret; `terraform login` locally | 2 | HCP Terraform → Tokens | Every Terraform job, and `terraform init` locally |
| Operator SSH key | Workstation | 0 | `ssh-keygen` | Root access; Ansible |
| Operator inspection key | Workstation | 0 | `ssh-keygen` | Daily unprivileged login |
| Tailscale server auth key | Password manager | 5 | Tailscale → Keys | Joining the host to the tailnet (first run, rebuilds) |
| `TAILSCALE_OAUTH_CLIENT_ID` / `_SECRET` | Env secret, infrastructure and each app repo | 5 | Tailscale → OAuth clients | Every deploy job |
| Vault password | Password manager | 6 | Chosen | Running the playbook |
| `ghcr_pull_token` | Vault-encrypted in `group_vars/prod.yml` | 6 | GitHub classic PAT, `read:packages` | Pulling private images at deploy |
| `PLATFORM_DEPLOY_SSH_KEY` | Env secret | 6 | `ssh-keygen`, platform key | Platform deploys |
| `PLATFORM_DEPLOY_HOST` | Env secret | 6 | Tailscale → Machines | Platform deploys, Grafana bind |
| `PLATFORM_ACME_EMAIL` | Env secret | 7 | A mailbox | Certificate registration |
| `PLATFORM_POSTGRES_USER` / `_PASSWORD` | Env secret | 7 | Chosen / generated | Postgres startup; every manual `psql` |
| `PLATFORM_POSTGRES_EXPORTER_PASSWORD` | Env secret and typed into Postgres | 7 | Generated | Postgres metrics |
| `PLATFORM_GRAFANA_ADMIN_PASSWORD` | Env secret | 7 | Generated | Grafana login |
| `PLATFORM_SLACK_WEBHOOK_URL` | Env secret | 7 | Slack app | Alert delivery |
| `PLATFORM_DEADMANSWITCH_URL` | Env secret | 7 | Heartbeat service | The external alarm |
| `HEARTBEAT_PING_KEY` | **Repo** secret, and Vault-encrypted in `group_vars/prod.yml` | 7 | Heartbeat service → project ping key | Nothing notices a periodic job failing or stopping |
| `<APP>_DEPLOY_SSH_KEY`, `DEPLOY_HOST`, app secrets | App repo Env secrets | 8 | Stage 8 | That application's deploys |

`HEARTBEAT_PING_KEY` is a **repository** secret, never an Environment one: a job reading a `production` Environment secret waits on required-reviewer approval, and an alarm that waits for a human to approve its own delivery is not an alarm. The same value goes into Ansible Vault for the host's prune unit.

The checks it addresses, and the settings each needs at the observer. A check comes into existence at its job's first ping and carries the vendor's default period until it is corrected here — so read these back once each check exists, and again after any rebuild:

| Check (slug) | Reported by | Period | Grace |
|---|---|---|---|
| `infrastructure-drift` | `.github/workflows/drift.yml`, nightly | 1 day | 12 hours |
| `infrastructure-pre-commit-autoupdate` | `.github/workflows/pre-commit-autoupdate.yml`, weekly | 7 days | 2 days |
| `<inventory_hostname>-prune-host-images` | `prune-host-images.service` on the host, weekly | 7 days | 2 days |

The graces are set against **observed** scheduling, not against the `cron:` line: GitHub starts these runs hours after the minute they name — over four hours late, consistently, on the nightly — so a tolerance derived from the declared time would alarm on a healthy system. The host slug is templated per host, so a second host converged by the same role reports to a check of its own.

## Appendix B. Rebuilding an existing host

The same stages, in this order, skipping what still exists: 4.2 (with `server_enabled` toggled off then on, or a replace with the `destroy-override` label), 4.3, 4.4 if the address changed, 5.3's auth key if the old one expired, 6.3, 6.4 (new tailnet IP → `PLATFORM_DEPLOY_HOST` and every application's `DEPLOY_HOST`), 7.4 by re-running the last Platform Deploy from Actions, 7.5, then each application's deploy from its own Actions. There is no database restore step: no platform-stack store needs one, because each is either recreated by a redeploy or its loss is accepted — see §8.3 and *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`). Two consequences to say out loud, because a rebuild is when they arrive: Prometheus's metrics history and Grafana's UI-created state do not come back, and `commerce-ops`'s own PostgreSQL — the one divergence that requirement names — is lost outright, since nothing backs it up. `docs/change-queue.md` entry 33 is what closes that, and entry 30 is the plan to turn this paragraph into a rehearsed runbook with timings.

## Appendix C. What to change for a company host

Recorded in detail in `docs/review-2026-09-08-host-readiness.md` and in `docs/change-queue.md`. The first two findings there — logical off-host database backups, and a decided database model — were resolved together by `scope-the-shared-database-to-non-durable-data`, which found that the shared instance holds no application data and that what this host needed was a stated boundary rather than a backup pipeline; §8.3 above is that boundary. The ones still to do before real data arrives: log rotation (21), swap and container limits (22, 7). The ones a company needs that this repository does not: a private repository in the company organisation, an approver who is not the author, and DNS as code (26).

**Heartbeat check names must stay distinct, and only half of that is automatic.** The workflow slugs carry this repository's name (`infrastructure-`), so a second repository's workflows get checks of their own. The host slug does **not**: it is `<inventory_hostname>-prune-host-images` with no repository or project segment, so two hosts both named `main-server` — the name this repository's own tfvars uses — would share one check in the same heartbeat project, and the live one's weekly success would keep it green while the other's timer was dead. That is the masking failure this mechanism exists to end. Give a company host an `inventory_hostname` of its own, or a heartbeat project of its own. The free tier's 20 checks is the ceiling either way; count them before adding a third host.
