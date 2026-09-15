# Bootstrapping a new host from this repository

This is the end-to-end procedure for standing up **two** servers — a reviewed production stack and an ungated staging one — and the repository and accounts around them, using this repository as the template. It is written for a developer who has shipped application code but has not run infrastructure before, so it names every account, every secret, and where each secret's value comes from, in the order you will need them. It is also the document to start from when a host has to be rebuilt (Appendix B, which covers the configured one) or when someone else has to take the system over.

What you will have at the end:

- **Two** Hetzner Cloud servers, each in its own Hetzner project, each with a firewall and a data volume, created and changed only through reviewed pull requests. Production's apply waits for a human; staging's does not.
- **The production server** configured (Docker, host firewall, a private network, restricted deploy accounts) by Ansible.
- A shared platform stack **on each server that asks for it**: Traefik with automatic TLS, PostgreSQL, Prometheus, Alertmanager, Grafana, alerts to Slack, and an external heartbeat. One definition in `platform/`, deployed once per stack, with each stack's credentials and alert targets its own.
- A path for any application repository to deploy itself **to the production host** from its own GitHub Actions workflow.
- **A staging server running the same platform stack, reachable from the internet** — stage 6 converges it alongside production and stage 7 deploys to it. Its cloud firewall opens 80 and 443 as production's does, and its **public DNS names** sit under a wildcard of its own (§4.4). (It also has a host name of its own — the converge sets that on every host; this is about DNS.) A certificate follows an application rather than the host: ACME is driven by router rules, so Traefik requests one only once an application's router names a hostname, and until then answers with its default certificate. "From here on, two hosts" says what else differs.

**Two servers is a standing cost**, not a one-off configuration: two instances and two volumes billed monthly, two hosts to patch and rebuild, two token pairs to rotate. Staging is roughly half production's bill. Decide you want that before stage 1, because the decisions that follow are shaped by it and are awkward to unpick afterwards. If you want one stack, this document still works: delete the second directory under `terraform/stacks/`, skip its secrets, and read every "two" below as "one" — including §0.4's table, which says so in its own terms.

**How to read this.** Stages are in dependency order; do not skip ahead. Each stage ends with a **Secrets created in this stage** table and a **Check** list. `<angle brackets>` are placeholders you replace. "Operator" means the person doing this. Commands are run from the repository root unless a `cd` is shown. The reasoning behind most decisions is in `openspec/specs/` and in the archived changes under `openspec/changes/archive/`; this document only says what to do.

**Time.** Roughly one working day for stages 0 to 7 if nothing goes wrong, mostly waiting on approvals and DNS. The second stack adds perhaps an hour of console work in stages 1 to 3, **a second converge in stage 6 and a second run of stage 7** — both run once per stack. Stage 8 is repeated per application.

## Before you edit this document

Two habits, learned by getting them wrong. Both are about the *kind* of mistake this document invites, which is not carelessness — every defect they exist to catch read fluently and survived a review.

**A fact stated in several places must be corrected in all of them, and the list is rebuilt by grep, never remembered.** Where a deploy key's private half lives is stated in three places; the Tailscale auth key's reuse in five; what the heartbeat ping key addresses in three. A change that fixes one and asserts it fixed them all is how a defect reaches a commit message as fixed.

**A fix aimed at the row a reviewer named will recreate the defect one row over.** Ask instead what predicate produced it and sweep every candidate: *for each creation step in a per-stack stage, what does the second run do?* *For each `ssh-keygen`, where does the private half sit and what removes it?* Both of those, swept, found instances nobody had reported.

**Two of those sweeps are now a check rather than a habit**, in `.github/tests/test_the_bootstrap_documents_static_conventions.py`: that every `ssh-keygen -f` here writes under `~/.ssh/`, and that every cross-reference — `§6.6` and the prose `stage 6.6` alike — names a heading this document actually has. Both fail the pull request, so neither needs remembering. What is *not* checked is the half that matters as much: whether the section a reference resolves to still says what the citing sentence claims it says. That stays with the habits above.

The generator behind both: **a property that holds when this document is read once, straight through, and fails when it is read the way it is actually used** — twice, once per stack; across elapsed time, with a `git add -A` in the middle; by following its own cross-references; on a rebuild, re-entering from the middle; by someone who wants one stack and is translating every "two" as they go. Each of those is a sweep, and each has caught something.

## Stage 0. Accounts, tools and keys

Nothing here touches a server. It is the shopping list.

### 0.1 Accounts you will create or need access to

| Service | Used for | Who owns the account |
|---|---|---|
| GitHub | The repository, CI, the approval gate, the container registry (GHCR) | The company organisation, not a personal account |
| Hetzner Cloud | Both servers, their firewalls, volumes and backups — **one project per stack**, created in stage 1 | The company, with billing set up |
| HCP Terraform (app.terraform.io) | Storing Terraform state and locking it — one workspace per stack | The company; the free tier is enough |
| Tailscale | A private network between both servers, CI runners and operators | The company; the free plan is enough for now |
| Slack | Alert delivery | The company workspace |
| A heartbeat service (Healthchecks.io or similar) | Noticing when the whole host or its alerting dies | The company |
| A DNS provider | Pointing each server's hostnames at it (§4.4) | Wherever the company's domain already lives |
| A GitHub App, created in stage 3.2 | Opening the weekly hook-update pull request as an identity that is not the workflow's own token | The company organisation, installed on this repository alone |

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
| `direnv` (optional but recommended) | Loads each stack's read-only Hetzner token only inside that stack's directory — one token reaches one project, so the scoping matters |
| Tailscale client | Reaching either server over the private network |

Follow `README.md`, "Local setup", steps 1 to 5. Step 5 installs Ansible into a virtual environment and the Galaxy content into `ansible/roles/`; the `-p ansible/roles` flag there is required, not optional.

### 0.3 SSH keys you will generate

Generate each with `ssh-keygen -t ed25519`. Never reuse one key for two **purposes**; each has a different holder and a different blast radius.

**A purpose may span both stacks, and several do** — the operator key most obviously; §0.4 lists the rest. Both stack directories in this repository carry the same `ssh_public_key`, and that is deliberate rather than an oversight: the key authorises `root` on hosts this repository can recreate in their entirety, both are reached by the same operator, and a second private half would be one more thing to hold, rotate and lose for no gain. What must never be shared is a key across *purposes* — the operator key, the inspection key, the platform deploy keys and each application's deploy key stay distinct, because those have different holders. Two purposes differ per deploy target rather than spanning both: the platform deploy key and each application's, so each is one key per deploy target rather than one key. If you decide otherwise for your company, generate a second operator key and put its public half in the second stack's `terraform.tfvars`; nothing else changes.

**Both of those spell the deploy target as the environment**, because the thing a deploy key authorises is an entry in `ansible/inventory/group_vars/<environment>.yml` — `deploy_apps` sits on the environment axis, and the file carrying a key's public half, the platform's included, is an environment's file. A filename spelling the stack would claim a narrower blast radius than the key has. Not everything about the platform key moves with the filename: its **private** half is per stack, held in that stack's GitHub Environment as `PLATFORM_DEPLOY_SSH_KEY` and resolved by `platform-deploy.yml`'s deploy job for that stack. Filename, comment and authorising entry on the environment; the stored secret on the stack.

**The table below carries the keys a deployment assembles once.** An application's deploy key is not among them: there is one per application per environment and it is generated when that application is onboarded, which is a different occasion and usually a much later one — `docs/onboard-an-application.md` carries that command beside the step that runs it.

**`<company>` in every path below is a literal, and `~/.ssh/` is the only place one belongs.** Every other namespace this repository writes into already belongs to one company — the Hetzner account, the HCP organisation, this repository's own clone, the tailnet, the heartbeat account — so nothing inside those carries a company segment, and §1.1 and §7.1 say so where it would otherwise be tempting. A workstation is the exception: it belongs to *you*, and yours may operate a second company tomorrow, so `~/.ssh/` is the one namespace two companies share and the filename is the only thing keeping their operator keys apart. The same reasoning covers the SSH alias you give each host and the directory you check this repository out into. `docs/naming-conventions.md`, *The workstation*, is the full list, with a second company worked through beside the first.

| Key | Command | Passphrase | Private half lives in |
|---|---|---|---|
| Operator key | `ssh-keygen -t ed25519 -f ~/.ssh/<company>-root -C "<you>@<company> root"` | Yes | Your workstation only. This is `root` on **both** servers. |
| Operator inspection key | `ssh-keygen -t ed25519 -f ~/.ssh/<company>-ops -C "ops-<you>"` | Yes | Your workstation. Unprivileged login, used daily instead of root. Configured on **both** hosts, in stage 6. |
| Platform deploy key — **one per environment** | `ssh-keygen -t ed25519 -f ~/.ssh/<company>-platform-<environment> -N "" -C "deploy@platform-<environment>"` | **No** (CI cannot type one) | That stack's own Environment secret `PLATFORM_DEPLOY_SSH_KEY` (stage 6.4); delete the local file once it is stored. **One key per environment, never one shared**: the public half is committed in that environment's `group_vars`, and one leaked private half must deploy to one host |
| Converge key — **one per stack** | `ssh-keygen -t ed25519 -f ~/.ssh/<company>-ansible-ci-<stack> -N "" -C "ansible-ci-<stack>"` | **No** (CI cannot type one) | That stack's GitHub Environment secret `ANSIBLE_SSH_PRIVATE_KEY` (stage 6.6); delete the local private half once it is stored. The public half is appended to `root`'s `authorized_keys` on that stack's host — see below |

Keep the `.pub` halves; they are committed to the repository in later stages and are not secret.

**The converge key is the one exception to that line, and to how every other key here is installed.** Its public half is *not* committed: no role manages `root`'s `authorized_keys`, so there is nowhere in this repository for it to go. You append it to `/root/.ssh/authorized_keys` on that stack's host by hand, once, at stage 6.6 — and revoking it is an edit on the host rather than a commit. That is a gap rather than a design: `docs/backlog.md` carries the entry that would give a role ownership of that file, and it is its own change because a role that owns `root`'s keys can lock every operator out of a host and wants scenarios of its own.

**Why it is not the operator key**, which already authorises `root` on both servers and would need no new keypair. Three reasons, and the first is the one that matters: a key held by continuous integration is held by whoever can reach the repository's Environment secrets, and the operator key is the human's own. Rotating CI's must not re-key the human, and a compromise of one must not be a compromise of the other. It is **one per stack** for the reason the deploy keys are one per environment: one leaked private half must not converge both hosts. The converge key takes the stack rather than the environment because its private half is a stack's GitHub Environment secret and it authorises `root` on that stack's host directly, with no `group_vars` entry in between — which makes it, as `docs/naming-conventions.md` records, the one per-stack artefact whose name lives on a workstation.

**Both platform deploy keys are stored the same way**, and each goes into its own stack's GitHub Environment as that Environment's `PLATFORM_DEPLOY_SSH_KEY`. Delete the local file once it is stored, for each of them.

This paragraph used to say otherwise, and the reason is worth keeping because it explains an interval a reader may still meet in the history: staging's private half was held in the password manager alone, because `platform-deploy.yml` declared `environment: production` and deployed to one host, so there was nothing to put staging's key into. `deploy-the-platform-stack-per-environment` gave every opted-in stack a deploy job of its own, and with it a place for that stack's key. **Verify before storing** that the file is the right one for that environment — `ssh-keygen -lf ~/.ssh/<company>-platform-<environment>` prints a fingerprint that must equal the public half committed in that environment's `group_vars`.

**Every private half above is generated into `~/.ssh/`, and none into the repository.** These are passphrase-less keys and stage 4.2 runs `git add -A`, so a key generated where you stand is one routine commit away from being published. Two things catch it and neither is a reason to relax: gitleaks reads the content at commit time, but it is a pre-commit hook and this stage runs before `pre-commit install` necessarily has; and `.gitignore` carries a private-key block anchored to the repository root, which is where the slip lands, covering the conventional names and every key name this document and `docs/onboard-an-application.md` generate — `.github/tests/test_the_bootstrap_documents_static_conventions.py` fails the build if one of them is matched by no pattern in it, which is what keeps that coverage complete as the scheme is renamed. Read it as a net rather than as a floor all the same: it is anchored to the repository root, so a key generated one directory down is caught by nothing here. Write the path out in full anyway — an ignored key is still sitting in your checkout. The platform key here is generated in stage 0 and not stored until stage 6.4: most of a working day apart, with that `git add -A` in between. An application's key, generated at onboarding time rather than here, meets the same hazard in a repository directory and `docs/onboard-an-application.md` says so where it generates one. The window used to be worst for staging's platform key, which was kept indefinitely because there was no secret to put it in; that is no longer true, and it is deleted after stage 6.4 like the others.

They are two keys rather than one because one leaked private half must not be able to deploy to both hosts.

### 0.4 What exists once, and what exists twice

Two servers do not mean two of everything. This table is the whole answer, so that you assemble the right set once rather than discovering a missing keypair at stage 6.

**Why each count is what it is**, §0.3's paragraph above already says: a different holder and a different blast radius. One thing it does not say, and which explains the pairs that are not about holders — **a Hetzner API token reaches exactly one project**, so anything scoped to a token comes in twos whatever it is allowed to do.

**If you decided on one stack** (see the note above stage 1), read this table's "How many" column as its smaller number throughout: one Hetzner project, two tokens rather than four, one workspace, one Vault password, one GitHub Environment, one platform deploy keypair. The rows already marked "1, shared" do not change — they were never per stack.

Covers stages 0 to 6. Two things sit outside it deliberately: stage 7's platform-stack secrets, a set of nine per stack, listed at §7.3 and Appendix A — `PLATFORM_DEPLOY_HOST` and `PLATFORM_DEPLOY_SSH_KEY` are created at stage 6.4 and belong to that same set; and the application deploy key, one per application per environment, which is generated at onboarding time by `docs/onboard-an-application.md` rather than here.

| Thing | How many | What proves it |
|---|---|---|
| Operator root key | **1**, shared | Both stacks' `terraform.tfvars` carry the same `ssh_public_key` |
| Operator inspection key | **1**, shared | Both `group_vars` files carry the same `ops_user_accounts` entry |
| Platform deploy keypair | **2** — one per environment | Each environment's `group_vars` carries a `platform` entry in `deploy_apps`, and the two public keys differ. The keypair is named for the environment; the private half is stored per stack, in that stack's own GitHub Environment |
| Converge keypair | **2** | Each stack's GitHub Environment carries an `ANSIBLE_SSH_PRIVATE_KEY` of its own (§6.6). Nothing in this repository proves it, which is what §0.3 says about that key: its public half is installed on the host by hand and is committed nowhere |
| Hetzner project | **2** | §1.1, and *Each Stack Has a Dedicated Hetzner Cloud Project* (`openspec/specs/iac-state-management/spec.md`) |
| Hetzner API token | **4** — read-only and read-write per project | §1.2. **Not six:** each read-only token is *also* exported under a second variable name for Ansible, and a second name is not a second token |
| HCP workspace | **2** | The two `versions.tf` name `main-production` and `main-staging` |
| `TF_API_TOKEN` | **1**, shared | *HCP Terraform Access via a Static Token, Unsplit by Privilege* (same spec file), cited for "one value, unsplit by privilege" and not for where it is stored — that requirement predates staging and names only `production`, while §3.3 now sets the token on both Environments |
| Ansible Vault password | **2** | §6.1 requires it; the two `image_prune_heartbeat_ping_key` blocks carry vault ids `production` and `staging`, one per environment |
| Tailscale auth key | **1 reusable key serves both joins**; two if single-use, or to revoke one host's join without the other — this repository used two | §5.3, and `ansible/roles/tailscale/tasks/main.yml`, which consumes it once per run and skips an already-joined host |
| Tailscale OAuth client | **1** | §5.3 — one client serves every repository |
| GHCR pull token | **1 value** unless you choose two, stored twice — encrypted separately into each stack's `group_vars` under that stack's own Vault password | `ansible/inventory/group_vars/staging.yml` records the shared *account* and the reasoning: read-only against the same packages, so a second "would be a second thing to rotate for no isolation gained". §6.1 permits reuse rather than requiring it, and the ciphertexts cannot be compared to tell which you chose |
| GitHub Environment | **2** — `main-production` and `main-staging` | §3.2, and each stack's `pipeline.yml` names the one its apply job attaches to. **Named for the stack**, like the repository secrets two rows up. GitHub offers no rename for a deployment Environment, so this repository's two were re-created and every secret on them re-entered; a new deployment names them correctly at creation and pays nothing |
| GitHub App, and its two repository secrets | **1**, whatever the stack count | §3.2. It authors one pull request on one repository and knows nothing about stacks, so a second stack adds nothing here. Its credential is a client id and a private key, both repository secrets rather than Environment ones: the workflow that mints a token from them runs on a schedule and declares no `environment:` |
| Heartbeat project ping key | **1**, shared — it addresses the **four** periodic-job checks Appendix A lists | §7.1: "It addresses one check per periodic job, listed with its period and grace in Appendix A". §7.1's Alertmanager checks are **not** among them: there is one per stack, each with a ping URL of its own held as that stack's `PLATFORM_DEADMANSWITCH_URL`, and a ping-key rotation touches none of them |

Appendix A is this same set seen from the other end — where each secret lives and what breaks when it is wrong, for rotating rather than for assembling. The two move together; if you change one, change the other.

## Stage 1. Hetzner Cloud

### 1.1 Register and create one project per stack

1. Register at console.hetzner.cloud, complete identity verification, add a payment method.
2. Create **two** projects, each named for the stack it holds: `main-production` and `main-staging`. No company prefix: one company per Hetzner account (`docs/naming-conventions.md`), so the account boundary already carries it.
3. Do **not** create a server, firewall or volume in either console. Terraform creates them in stage 4, and anything created by hand is drift the nightly check will report.

**One project per stack is a decision, and this is where it is made.** A Hetzner API token is scoped to exactly one project, so the project boundary is what the whole credential split rests on. The pipeline supports either answer; two projects is the recommendation, for two reasons that are hard to see in advance:

- **One project means one Read & Write token covering both stacks**, so staging's apply must sit behind an approver too — otherwise any push to `main` reaches a production-capable credential. An approved staging deploy is as slow as production and stops being used, which is most of what staging is for.
- **Hetzner volume names are unique per project, not globally.** In one project the second stack's volume cannot also be called `main`, so it gets a different name — and since a mount path is chosen per stack rather than derived from a volume's name, a different mount path, so that `platform/docker-compose.yml`'s hardcoded `/mnt/main/prometheus` and `/mnt/main/grafana` must be parameterised — or Prometheus and Grafana come up writing to a path that does not exist, silently.

Two projects costs a second token pair to rotate. One project costs the two items above, every time you deploy.

### 1.2 Create four API tokens, two per project

In **each** project: Security → API tokens → Generate API token. Check the project switcher before generating — a token made in the wrong project is the failure that looks like everything else.

| Token | Permission | Where it goes | Never goes |
|---|---|---|---|
| Production Read Only | Read | Your workstation, **twice**: the repo-root `.envrc` as `HCLOUD_TOKEN` for Terraform (stage 4.1), and `ansible/.envrc` as `HCLOUD_TOKEN_MAIN_PRODUCTION` for Ansible (stage 6.0). Plus the repository secret `HCLOUD_TOKEN_MAIN_PRODUCTION` (stage 3) | Nowhere else |
| Production Read & Write | Read & Write | The `main-production` Environment secret `HCLOUD_TOKEN` (stage 3) | Any local file, shell, or note. If you can run `terraform apply` from your laptop, this token is in the wrong place. |
| Staging Read Only | Read | Your workstation, **twice**: `terraform/stacks/main-staging/.envrc` as `HCLOUD_TOKEN` for Terraform (stage 4.1), and `ansible/.envrc` as `HCLOUD_TOKEN_MAIN_STAGING` for Ansible (stage 6.0). Plus the repository secret `HCLOUD_TOKEN_MAIN_STAGING` (stage 3) | Nowhere else |
| Staging Read & Write | Read & Write | The `main-staging` Environment secret `HCLOUD_TOKEN` (stage 3) | The same places. An ungated apply does not make its token less confined. |

Each token is shown once. Put all four in the password manager immediately, each labelled with its project **and** its permission level.

**Each read-only token is used by two tools under two different variable names**, and the duplication is deliberate. Terraform reads `HCLOUD_TOKEN`, whose value direnv scopes to the stack *directory* you are standing in. Ansible is always run from `ansible/`, so it cannot use a variable whose meaning depends on where you stand: each of its inventory sources names its own variable instead, and which project a run reaches is decided by the `-i` it was given rather than by shell state.

The two read-only secrets have different **names** at the repository level, and that is required rather than stylistic: a repository secret holds one value, so two stacks naming the same one would plan under a single credential. Discovery fails the pipeline, naming both offenders, if two stacks ever declare the same read-only secret or the same GitHub Environment.

### 1.3 Decide the sizing and record it

You will write these into each stack's `terraform.tfvars` in stage 3. Decide them now, for both.

| Setting | Guidance | Production | Staging |
|---|---|---|---|
| `location` | Pick one datacenter and stay in it; the volume cannot move | `hel1` (Helsinki); `fsn1` and `nbg1` are the German alternatives | The same, unless you want to rehearse a region move |
| `server_type` | `cx33` is 4 vCPU / 8 GB; for several services start at `cx43` (8 vCPU / 16 GB) or a `cpx` type. You can resize later, but only upward without a rebuild. **Read the current type names off the console** — the generation changes, and a name that no longer exists fails at apply | `cx33` | `cx23`, roughly half the bill. Deliberately tight: a staging host that cannot fit the stack is what forces container resource limits to be set, rather than deferred until production needs them |
| `image` | A current Ubuntu LTS | `ubuntu-26.04` | The same. A stack that rehearses production on a different image rehearses something else |
| `volume_size` | GB for Prometheus and Grafana state (and future logs); resizable upward only | `10` | `10` |
| `volume_name` | Keep it identical across stacks. Names are unique per project, so a project each frees the name. It is **not** the mount path and does not have to resemble one — the on-host device is `/dev/disk/by-id/scsi-0HC_Volume_<id>` — but both stacks mounting at the same path is what lets `platform/docker-compose.yml` stay unparameterised | `main` | `main` |
| `name` | The server's own name, which becomes its `inventory_hostname` and its tailnet machine name. **Give it the stack's own name**, which makes it differ between stacks by construction — two hosts sharing one name merge in any inventory that reads both projects, and share a single `<inventory_hostname>-prune-host-images` heartbeat check, where the live host's weekly success masks the other's dead timer | `main-production` | `main-staging` |
| `ssh_allowed_cidrs` | The public IP ranges allowed to reach SSH. Must not be `0.0.0.0/0`. If everyone will use Tailscale, see `docs/backlog.md` entry 1 for closing public SSH entirely | one ISP `/24` | The same |
| `web_allowed_cidrs` | `["0.0.0.0/0"]` for a public web host | `["0.0.0.0/0"]` | The same. Its applications take certificates and webhooks from the internet as production's do |

**Secrets created in this stage:** four Hetzner tokens, held in the password manager until stage 3.

**Check:** both projects exist and are empty; all four tokens are in the password manager, each labelled with its project and its permission level.

## Stage 2. HCP Terraform

Terraform needs somewhere to keep its state file (the record of what it created) that both your workstation and CI can reach, with a lock so two runs cannot overlap. HCP Terraform provides exactly that, and this setup uses nothing else from it.

1. Register at app.terraform.io. The sign-up page offers **Create HCP account** and **Create Terraform account**; choose **Create HCP account**, which is the one HashiCorp recommends — a standalone Terraform account works for this setup too, but it keeps its own password and multi-factor settings apart from every other HashiCorp product. Then create an organisation named `<company>`.
2. Create **two** workspaces, both **CLI-driven workflow**, no VCS connection, named for their stacks: `main-production` and `main-staging`. The form asks for a **Project** and offers **Default Project**. Nothing in this repository reads the project — the `cloud` block in each `versions.tf` names only the organisation and the workspace — so either choice works. The suggestion is to rename Default Project to `main` first (organisation Settings → Projects; it can be renamed but not deleted) and put both workspaces in it: `main` is the tenant both stack names begin with, so a later tenant's workspaces get a project of their own. The names are read from each stack's `versions.tf` in stage 3, so a typo there creates a second, empty workspace under whatever you typed. **No two stacks may share a workspace** — a workspace holds one state, so sharing one would have each apply read the other's resources as its own and plan them for destruction.
3. In **each** workspace's Settings → General, set **Execution Mode** to **Local**, and save. This is essential and it is per workspace: the default is Remote, so a workspace created and not adjusted is misconfigured even when its sibling is correct. Remote execution runs plans on HCP's machines, and `terraform plan -out=tfplan` then yields no plan file the apply job can apply — which breaks the saved-plan approval flow with no error naming execution mode.
4. Create an API token, and it **must be a USER token**: your avatar (top right) → **Account settings → Tokens → Create an API token**. The **Description** is required; name what uses the token, for example `infrastructure: GitHub Actions and terraform login`, so whoever finds it later knows what revoking it breaks. For the expiration, choose no expiry if offered, otherwise the longest available with its date in the password-manager entry: an expired token stops every plan, apply and nightly drift check on that date without warning. One token; this tier has no way to split it by privilege, and the Hetzner token split in stage 1 is the real security boundary.

   **Not an organisation token, and not a team token.** HCP issues three kinds and they are not interchangeable. An organisation token (Organisation settings → API token) administers organisation objects — workspaces, teams, variables — and **cannot perform state operations**. A team token is limited to that team's workspace permissions. Only a user token can lock a workspace and write state, which is what every job in this pipeline does.

   **Its failure signature, because it does not look like a credential problem.** With an organisation token, `terraform init` *succeeds* — reading a workspace is organisation administration — and the run then dies at `Error acquiring the state lock / Error message: resource not found`. HCP reports the authorisation failure as a 404, so the error names the lock, not the token, and every plausible cause it suggests is the wrong one. If you see it, check the token kind first: in HCP, Organisation settings → API token shows a `last used` timestamp, and if it matches the failing run to the second, that is your answer.

   This step previously offered an organisation token as an equivalent alternative. Following that cost an afternoon during `add-a-staging-environment`, whose record has the full diagnosis.
5. On your workstation, run `terraform login` and paste the same token when asked. It is stored in `~/.terraform.d/credentials.tfrc.json`.

**Secrets created in this stage**

| Name | Value | Stored where (stage 3) |
|---|---|---|
| `TF_API_TOKEN` | The HCP Terraform **user** API token (Account settings → Tokens — not an organisation or team token) | Repository secret **and both** Environment secrets, the same value in all three |

**Check:** **both** workspaces show Execution Mode: Local and have no runs; the token is a user token.

## Stage 3. The GitHub repository

### 3.1 Create the repository from this one

1. In the company organisation, create a **private** repository named `infrastructure`. Private, because the tree will contain your office IP ranges, server identifiers and internal hostnames.

   **Tick "Add a license", and nothing else.** The repository must not be empty, and this is the reason: the apply workflow compares a push against the commit that preceded it, and a branch's *first* push has no predecessor — it refuses that case by design, so a first push into an empty repository creates nothing and reports a failure. One initial commit gives the content push something to be compared against. It must be the license: this template already contains `README.md` and `.gitignore`, so either of those would collide with your content when you reconcile in step 2.
2. Copy this repository's tree into it. The simplest faithful way:

   ```sh
   git clone https://github.com/shatynska/infrastructure <company>-infrastructure
   cd <company>-infrastructure
   git remote set-url origin git@github.com:<company>/infrastructure.git
   ```

   Then bring the license commit underneath your history, so the push in stage 4.2 has a predecessor to be compared against:

   ```sh
   git fetch origin
   git merge --allow-unrelated-histories origin/main
   ```

   One merge commit, no conflict — the license file exists in neither history — and every template commit keeps its identity. Do **not** rebase here: your history is unrelated to that commit, so a rebase would replay every template commit onto it and rewrite the history you just chose to keep.

   Keeping the history keeps the reasoning behind every file. If you prefer a clean history, replace the block above with:

   ```sh
   git clone https://github.com/shatynska/infrastructure <company>-infrastructure
   cd <company>-infrastructure
   rm -rf .git
   git init -b main
   git remote add origin git@github.com:<company>/infrastructure.git
   ```

   `-b main` and `remote add` are both load-bearing there: without the first the branch is named whatever your Git defaults to and the push in 4.2 fails on its refspec, and without the second there is no remote to set a URL on. This variant has no commit yet, so its reconciliation waits until stage 4.2, where the commit exists. The `openspec/` archive still carries the reasoning either way.

   **A force-push is not a shortcut.** Whichever variant you take, do not overwrite the license commit — that leaves the apply workflow comparing against an object your checkout cannot resolve, which it refuses with a different message and the same result: nothing is applied.

3. Find every reference to the original owner and replace it:

   ```sh
   grep -rn 'shatynska' --exclude-dir=.git --exclude-dir=openspec .
   ```

   The ones that matter: the `organization` in **both** `terraform/stacks/main-production/versions.tf` **and** `terraform/stacks/main-staging/versions.tf` (your HCP organisation from stage 2), `company` in `ansible/inventory/group_vars/all.yml`, `ghcr_pull_username` in **each** `ansible/inventory/group_vars/<environment>.yml` (stage 6), the `Documentation=` URL in `ansible/roles/image_prune/tasks/main.yml`, and prose in `README.md`.

   Both `versions.tf` files carry it, and changing only production's is the easy miss: staging would then initialise against someone else's HCP organisation, and the error names a workspace rather than an organisation.

4. Edit **both** `terraform.tfvars` files — `terraform/stacks/main-production/` and `terraform/stacks/main-staging/` — with the stage 1.3 decisions for that stack, putting the **public** half of your operator key from stage 0 into each `ssh_public_key`. Everything in these files is non-secret and committed. Check `name` differs between them and `volume_name` does not; stage 1.3 says why each matters.

5. Read `terraform/stacks/main-staging/pipeline.yml` and accept or change its four values: `github_environment: main-staging`, `read_only_secret: HCLOUD_TOKEN_MAIN_STAGING`, `target_environment: staging`, and `destroy_policy_gate: false`. These are what stage 3.2 and 3.3 must match — the Environment you create and the repository secret you set take their names from this file, not from any workflow. `terraform/stacks/main-production/pipeline.yml` is its counterpart, declaring `github_environment: main-production`, `read_only_secret: HCLOUD_TOKEN_MAIN_PRODUCTION` and `target_environment: production`. **`read_only_secret` and `github_environment` carry the stack's name; `target_environment` spells the environment**, because it names the Ansible group, which *is* the environment. It also names the play's `hosts:`, the `--vault-id` label and the `group_vars` file, so those three move together. **Neither stack may declare `HCLOUD_TOKEN`**, and the reason is not style: every GitHub Environment defines that name as its *Read & Write* token, and an Environment secret shadows a repository secret of the same name — so a job attached to an Environment would resolve the write token from a field that says read-only. `.github/tests` fails the build on a declaration that names it.

6. Delete the `moved` block at the bottom of `terraform/stacks/main-production/ssh_key.tf`. It records a one-time relocation in the original repository and is meaningless in a fresh state. Staging's `ssh_key.tf` has no such block and needs no edit; its own comment says why.

7. Run `pre-commit install --hook-type pre-commit --hook-type commit-msg` so your commits are checked the way CI checks them.

**Do not push yet, and the reason is now sharper than it used to be.** Because you initialised the repository with a commit in step 1, your push in stage 4.2 *will* be compared against it, *will* plan, and will therefore need every secret from 3.3 already in place. The two stacks' plan jobs run under two different repository secrets; a missing one authenticates as nobody rather than erroring cleanly.

### 3.2 Repository settings

All of these are in Settings on github.com, or via `gh`.

1. **Environments, two of them.** Settings → Environments → New environment, twice:

   - **`main-production`** — add the protection rule **Required reviewers** and name at least one person. For a company, this person should not be the only person who opens pull requests; the Environment approval is the human gate every production change passes through.
   - **`main-staging`** — add **no** protection rules at all. Its apply runs on merge, without a human.

   The names must match what each stack's `pipeline.yml` declares (step 5 of 3.1), and they must differ from each other: two stacks naming one GitHub Environment would share its write token and its protection rules, so the ungated one would hold the reviewed one's credential. Discovery fails the pipeline, naming both, if they ever collide.

   **What makes an ungated apply safe is the project boundary from stage 1, and nothing else.** Staging's write token can destroy staging's Hetzner project and cannot touch production's. Whether an Environment requires a reviewer is a repository setting that no file in this repository can verify — which cuts both ways: nothing will tell you if `main-production` loses its reviewer either.

   **AN ENVIRONMENT'S NAME CANNOT BE CHANGED AFTER YOU CREATE IT, SO CHOOSE IT HERE RATHER THAN LATER.** GitHub offers no rename: not in the interface, and not in the REST API, which exposes only create-or-update, read and delete with the name in the path (measured 2026-09-12 by `rename-the-external-services`). Moving an Environment therefore means creating a second one, re-entering **every** secret it holds — a value GitHub will not read back to you — re-adding its protection rules, and deleting the first. On this repository that is twenty-one secrets across the two, three of which are SSH private halves §0.3 has you delete once stored, so each needs a key rotation with a step on the host.

   **Name them for their stacks, `main-production` and `main-staging`**, matching the stack directories, the HCP workspaces, the read-only secrets and the inventory sources (`docs/naming-conventions.md`). Set each stack's `github_environment` to match in step 5 of §3.1.
2. **Label.** Issues → Labels → New label: `destroy-override`. A merged pull request must carry this label for the apply workflow to accept a plan that deletes or replaces a resource. Without it, such plans fail on purpose.
3. **Workflow token.** Settings → Actions → General → Workflow permissions: **Read repository contents and packages permissions**. Each workflow declares the little it needs on top.
4. **Merge methods.** Leave merge commits enabled. The destroy gate reads the pull request number from the merge commit message; squash and rebase merges fall back to a slower API lookup.
5. **A GitHub App, to open the weekly hook-update pull request.** Settings → Developer settings → GitHub Apps → New GitHub App. Name it for your company (this repository's is `infrastructure-autoupdate`). Give it repository permissions **Contents: read and write** (to push the update branch) and **Pull requests: read and write** (to open one), **and no account-level permissions at all**. Install it on this repository alone. Then Generate a private key, which downloads a `.pem` once, and note the App's **Client ID** from its settings page. Both become repository secrets in 3.3.

   **Why it exists, because "the workflow can just use `GITHUB_TOKEN`" is the obvious thing to try and it does not work.** Dependabot has no `pre-commit` ecosystem, so hook revisions are kept current by `pre-commit-autoupdate.yml`, which runs weekly and opens a pull request. An event caused by `GITHUB_TOKEN` starts no workflow run — so that pull request would receive no `validate` and no `ansible-verify`, and every required status check on `main` is triggered that way. It would open, report nothing, and stay unmergeable forever. That is worse than a failure, because a failure is red and this is merely permanently pending. *Automated Dependency Updates* (`openspec/specs/iac-safety-hardening/spec.md`) is where this is written down.

   **An App rather than a personal access token, and that is a requirement rather than a preference.** The same requirement forbids a credential that expires on a schedule: a one-time setup step is bounded by the change that introduces it, while a scheduled expiry recurs indefinitely at a date nobody chose, long after anyone is watching for it — and the failure it produces is this mechanism silently ceasing to open pull requests. An App's private key does not expire and the tokens minted from it live minutes; a classic PAT with a mandatory expiry date does not satisfy it.

   **Its scope is the smallest thing that works, and the workflow narrows it again.** The minting step down-scopes each token it issues to those same two permissions, in committed content, so widening the App later does not silently widen the token. That scope also bounds what the workflow's pull-request step may ask for: `labels` and `assignees` are issue operations and would need Issues, and `team-reviewers` needs an organisation permission. Adding any of them means revisiting the App's permissions, not only editing the workflow.

### 3.3 Secrets

Repository secrets: Settings → Secrets and variables → Actions → Repository secrets. Environment secrets: Settings → Environments → *that stack* → Environment secrets. Or with `gh`, which prompts for each value and reads it when you press Enter:

```sh
gh secret set HCLOUD_TOKEN_MAIN_PRODUCTION          # production Read Only
gh secret set HCLOUD_TOKEN_MAIN_STAGING             # staging Read Only
gh secret set TF_API_TOKEN                          # the HCP user token
gh secret set HCLOUD_TOKEN --env main-production    # production Read & Write
gh secret set TF_API_TOKEN --env main-production    # the same HCP user token
gh secret set HCLOUD_TOKEN --env main-staging       # staging Read & Write
gh secret set TF_API_TOKEN --env main-staging       # the same HCP user token
gh secret set APP_CLIENT_ID                         # the GitHub App's client id
gh secret set APP_PRIVATE_KEY < ~/Downloads/<app-name>.private-key.pem
```

`APP_PRIVATE_KEY` is the one secret here read from a file rather than typed: it is a multi-line PEM block, and `gh secret set` reading a prompt takes one line. Pass it with `<` and the path the browser saved it to — GitHub names that file for the App, and the line above assumes your download directory. Delete the `.pem` once it is stored — GitHub will not show it again, and an App can be given a fresh key at any time, so losing it costs one click rather than a re-registration.

Do not pass `--body '<token>'`: that records the secret in your shell history, where it then lives until the file rotates out.

**Secrets created in this stage**

| Name | Scope | Value from | Read by |
|---|---|---|---|
| `HCLOUD_TOKEN_MAIN_PRODUCTION` | Repository | Stage 1, production Read Only | Production's PR plans, drift detection, apply-workflow plan job — and its host converge, which exports this value under the same name production's inventory source reads locally (stage 6.0). The two names are one name on purpose: the converge job holds the credential under the name the declaration states and has to supply it under the name the source reads, and a workflow carrying that mapping would be naming a stack in workflow text |
| `HCLOUD_TOKEN_MAIN_STAGING` | Repository | Stage 1, staging Read Only | Staging's PR plans, drift detection, apply-workflow plan job and host converge |
| `HCLOUD_TOKEN` | `main-production` Environment | Stage 1, production Read & Write | Production's apply job only, after approval. GitHub resolves an Environment secret ahead of a repository secret of the same name, which is the whole mechanism. |
| `HCLOUD_TOKEN` | `main-staging` Environment | Stage 1, staging Read & Write | Staging's apply job, immediately on merge |
| `TF_API_TOKEN` | Repository | Stage 2 | Every Terraform job |
| `TF_API_TOKEN` | `main-production` Environment | Stage 2, same value | Production's apply job |
| `TF_API_TOKEN` | `main-staging` Environment | Stage 2, same value | Staging's apply job |
| `APP_CLIENT_ID` | Repository | The GitHub App from 3.2 | `pre-commit-autoupdate.yml`, weekly, to mint the token it opens its pull request with |
| `APP_PRIVATE_KEY` | Repository | The same App's downloaded `.pem` | The same step. **Repository-scoped, not an Environment secret**: that workflow runs on a schedule and declares no `environment:`, so an Environment secret would be unreachable to it |

**`.github/dependabot.yml` already lists both stack directories**, and it must keep listing exactly the ones that exist. Dependabot's terraform ecosystem has no discovery mechanism, so a directory the list omits is not partially covered — it is uncovered, and its provider pins rot with no signal. The CI suite compares that list against the lockfiles in the tree and fails the build if a lockfile-bearing directory is missing. If you drop the second stack, drop its entry with it; if you add a third, add one.

**The two read-only secrets have different names on purpose.** A repository secret holds one value, and plan jobs declare no `environment:` — they can only reach repository secrets — so each stack needs a name of its own. Which name is read comes from that stack's own `pipeline.yml`, not from any workflow.

**Where those names come from.** No stack name and no secret name is written in any workflow. Each is declared by that stack's own `pipeline.yml`, which the pipeline's discovery step reads. If you rename one, rename it there in the same change, or the plan job resolves an empty secret and the apply job attaches to an Environment that does not exist.

**Each Environment must define its own `HCLOUD_TOKEN`.** GitHub resolves an *absent* Environment secret to the repository secret of the same name rather than failing — so an Environment that omits it applies with whatever the repository holds under that name. **No repository secret carries that name here**, deliberately: production's read-only token is `HCLOUD_TOKEN_MAIN_PRODUCTION` and staging's is `HCLOUD_TOKEN_MAIN_STAGING`, precisely so that no job attached to an Environment can resolve a read-only field to a write token. The fallback therefore resolves to nothing, and the apply job's guard still refuses — it digests both sides and they match as the empty string. That is the guard working, not a hole: an Environment that omits its write token fails rather than applying with something else's. The fix is still here.

**Check:** nine secrets set — five at repository scope, two on each Environment; `main-production` shows one required reviewer and `main-staging` shows none; the label exists; the App is installed on this repository and on no other; the repository is private and holds exactly one commit, the license.

## Stage 4. First Terraform apply: both servers exist

### 4.1 Prove both configurations locally

Each stack needs its own read-only token in scope, because one token reaches one project. Put production's in the repo-root `.envrc` (copy `.envrc.example`), and staging's in an `.envrc` **inside** `terraform/stacks/main-staging/` — directory-scoped, so planning staging never leaves staging's token in the shell that plans production. Both paths are gitignored.

Run `direnv allow` in each directory that has one; direnv loads the nearest `.envrc` and does not merge the parent's, which is what keeps the two tokens apart. **Without direnv**, `source` the file for the stack you are about to work on, in a shell you do not then reuse for the other — the export outlives the directory, and carrying staging's token into `prod/` produces the misleading plan described below rather than an error.

This paragraph is about **Terraform's** token only. Ansible has a third `.envrc`, in `ansible/`, holding both read-only tokens under names of their own; stage 6.0 sets it up, and it is immune to the mistake above because neither name is `HCLOUD_TOKEN`.

Then, for each stack in turn:

```sh
cd terraform/stacks/main-production   # then repeat in main-staging/
terraform init
terraform plan
```

`init` connects to that stack's HCP workspace from stage 2 — check the workspace name in the output matches the directory you are in. `plan` should propose creating a firewall, an SSH key, a server and a volume, and nothing else, in each stack.

Do not run `apply`: the read-only token would refuse it, and that refusal is the boundary this whole setup relies on. **With the wrong stack's token in scope the plan is misleading rather than refused** — an empty workspace and a foreign project produce the same "four resources to create" you expect, so check the workspace name rather than the resource count.

### 4.2 Push, and approve production's apply

Commit your work:

```sh
git add -A
git commit -m "chore: bootstrap <company> from the template"
```

`git add -A` rather than `git commit -a`: after the clean-history variant's fresh `init`, every file is untracked and `-a` would commit nothing.

If you took the **clean-history** variant in 3.1, this is the commit its reconciliation waited for, so bring the license commit underneath it now:

```sh
git fetch origin
git rebase origin/main
```

If you took the keep-history variant, you merged at 3.1 and there is nothing to do here. Then push:

```sh
git push -u origin main
```

`-u` sets the upstream, which the clean-history variant does not have — it used `remote add`, not a clone.

Open Actions on github.com. **Two** workflows start, and only one of them is the one you want. PR Validation and Ansible Verify do not run at all — both are triggered by pull requests only.

- **Terraform Apply** — this is the one. Read on.
- **Platform Deploy** — triggered because this push adds the whole `platform/` tree, which is its path filter. Its `deploy` job attaches to the `main-production` Environment, so **it raises a second approval request that looks exactly like the one below**. Do not approve it. There is nothing to deploy yet: the host is not converged until stage 6, and every secret that job needs is created in stages 5 to 7. Cancel the run, or leave it pending and let it expire. Stage 7.4 is where the platform stack is deployed for the first time, deliberately and with its prerequisites in place.

The run covers **both** stacks, because this push changes files under both stack directories:

- **staging's apply runs immediately**, with no approval, and creates its four resources;
- **production's apply waits** on the `main-production` Environment. Read its plan job's summary. If it is the four resources from 4.1, approve; the `apply` job creates them.

Neither stack's failure withholds the other's apply — that separation is deliberate, so a broken staging can never be the reason a correct production change cannot ship. This is the pipeline's specified behaviour; two applies in one run, one of them pausing, is a path this repository has specified and not yet observed, so read the run rather than assuming it.

**If the run fails at "List the paths this merge changes"**, with a message about a push carrying no usable comparison base, the repository was created empty and this is its first push. That is the case step 1 of 3.1 avoids by initialising with a license. Recover by making one more commit and pushing again — and that commit must touch a file **under each** `terraform/stacks/<name>/`, because Terraform Apply is filtered to `terraform/**` at the workflow level and then narrowed to the stacks whose own directories changed. A recovery commit touching neither starts no run at all, silently; one touching a single stack leaves the other server uncreated. Do not force-push: it produces the same failure with a different message.

### 4.3 Get the addresses and log in

```sh
cd terraform/stacks/main-production && terraform output   # then repeat in main-staging/
```

Each stack's `server_ipv4_address` is that server's public address; you now have two. Record both.

Log in once as root to **the production host** with the operator key, which also records its fingerprint in your `known_hosts` — Ansible requires that in stage 6:

```sh
ssh -i ~/.ssh/<company>-root root@<prod ipv4>
```

**Log into the staging host too, the same way** — `ssh -i ~/.ssh/<company>-root root@<staging ipv4>`. This is not optional and it is not just a reachability check: it records staging's host key in your `known_hosts`, and `ansible.cfg` sets `host_key_checking = True`, so without it stage 6's first converge of staging stops at connection time with `Host key verification failed` before a single role runs.

### 4.4 DNS

In the DNS provider, point each server's hostnames at **that server's own address**. The shape in use is one wildcard `A` record per server, `*.<server>.<base domain>`, so an application's hostname under it resolves with no record of its own; a name outside a wildcard, such as a short alias, takes an `A` record of its own. Nothing needs them until an application is routed in stage 8, but they take time to propagate, so create them now.

**Staging takes hostnames too.** Its cloud firewall opens 80 and 443 as production's does, so a name aimed at it answers; the certificate for a name issues once an application's router names it.

**There is no Terraform for DNS, deliberately, and this is where the zone is written down.** `shatynska.com` is served by `ns15`/`ns25`/`ns35.inhostedns.*` — the nameservers of ukraine.com.ua, neither Hetzner DNS nor Cloudflare — so managing the records in Terraform means moving the nameservers, not adding a provider. The zone as read on 2026-09-08, corrected on 2026-09-09 and 2026-09-14:

| Record | Value |
|---|---|
| `shatynska.com` A | `2.29.14.98` — the prod host |
| `www` A | `2.29.14.98` |
| `fuperia` A | `2.29.14.98` — not routed: `commerce-ops`'s production router does not name it (read 2026-09-14) |
| `test` A | `2.29.14.98` — a throwaway smoke test's leftover; `docs/backlog.md` entry 11 covers removing it, and the certificate Traefik still renews for it |
| `staging` A | `62.238.17.177` — the staging host; nothing routes it |
| `shatynska.com` MX | `mx.ukraine.com.ua` |
| `shatynska.com` TXT | `v=spf1 include:_spf.ukraine.com.ua ~all` |

`fincci.bike` is served by `dns1`/`dns2.registrar-servers.com` — Namecheap's DNS. It too carries live mail (`MX 0 email.fincci.bike`), and a site at its apex; neither is operated from this repository, so neither is transcribed. The records this repository's hosts serve, as read on 2026-09-14:

| Record | Value |
|---|---|
| `*.main-production.fincci.bike` A | `2.29.14.98` — production; `commerce-ops.main-production.fincci.bike` is routed under it |
| `main-production.fincci.bike` A | `2.29.14.98` — a record of its own: a wildcard does not match the name it sits under |
| `*.main-staging.fincci.bike` A | `62.238.17.177` — staging |
| `main-staging.fincci.bike` A | `62.238.17.177` — likewise its own record |
| `ops.fincci.bike` A | `2.29.14.98` — routed by `commerce-ops`'s production router beside its technical name |

There is no `*.fincci.bike`: an address change edits that server's wildcard, its bare server name and every alias pointing at it, in both tables.

**These tables are the project's only written record of the two zones, and their value depends on being read against the zones rather than trusted.** `shatynska.com`'s was written on 2026-09-08 as "the records as read" and was already incomplete that day: the `test` row was missing and was added on 2026-09-09, by a change that found the record while reading Traefik's certificate metrics. Re-read the zones before relying on them.

**Why the migration is declined rather than queued.** Both zones carry live mail. An NS migration moves the MX and SPF records with it, and a transcription error there stops mail rather than a web service — a failure that is silent to every check this repository has, because nothing here monitors mail. That is a different risk class from the convenience the migration would buy. Cloudflare and Hetzner DNS were the two candidates considered; neither was chosen, and that choice is still open.

**Revisit when** mail moves off either zone, when a server's address changes — the moment its records are edited by hand — or when `fincci.bike` names outside the server wildcards, such as `ops.fincci.bike`, become frequent enough that the manual edits recur. A new application hostname is not itself a trigger: under a server's wildcard it costs no edit. What the deferral costs meanwhile is real and worth stating: DNS is the one piece of the running system that lives in no repository, so a rebuild that changes a server's address (`docs/backlog.md` entry 20) or an IPv4 change is followed by a manual edit to every record pointing at that server, and these tables are the mitigation.

**Secrets created in this stage:** none. The two `.envrc` files hold the two read-only tokens and are gitignored.

**Check:** `terraform plan` says "No changes" locally in **both** stack directories; the nightly Drift Detection workflow, run once by hand from Actions → Drift Detection → Run workflow, reports no drift for **both** stacks in one run — its own `report` job will still fail at this stage, because `HEARTBEAT_PING_KEY` is not created until stage 7.3, so read the two `drift` jobs rather than the run's overall result; `ssh root@<prod ipv4>` works with the operator key and nothing else; both servers appear in their own Hetzner projects and neither project holds anything you created by hand.

## From here on, two hosts — both of which run the platform stack

You now have two servers, and **stage 6 configures both**. It is written once and run once per stack: the inventory has a source per stack, and the host-baseline play takes the stack it targets as an input.

**Stage 7 now runs once per stack too.** It used to be production's alone, because `platform-deploy.yml` declared `environment: main-production` as a literal and deployed to a single `PLATFORM_DEPLOY_HOST`. `deploy-the-platform-stack-per-environment` removed that: the workflow discovers which stacks receive the platform stack by reading each one's `terraform/stacks/<name>/pipeline.yml`, and deploys to each from a job attached to that stack's own GitHub Environment. A stack opts in with `deploys_platform: true`; absent, it receives nothing, which is the safe direction for a stack committed before its Environment holds any platform secret.

**What still differs between the two, and it is no longer the deploy path:**

- **Not its web exposure.** Staging opens 80 and 443 to the internet as production does, so an application routed there is public, not tailnet-only; §4.4 has its hostnames.
- **Its approval gate.** Production's deploy waits for a reviewer because `main-production` requires one; staging's does not, because `main-staging` requires none. That is a repository setting, not a difference in the workflow — nothing in `platform-deploy.yml` distinguishes them.
- **Its Vault password and its deploy keypair**, both its own, for the reasons below.

So after stage 6 the staging server is a **configured** host — Docker, UFW and fail2ban, on the tailnet, data volume mounted, operator account, deploy account — and stage 7 is what puts the stack on it. Its own host name is set, like production's — the `hostname` role runs on every converge.

Two things about staging in stage 6 that differ from production, both deliberate:

- **Its own Vault password**, under the vault id `staging`. Reusing production's would mean anyone who can converge staging holds the password protecting production's secrets.
- **Its own deploy keypair** for `platform`. One leaked private half must not deploy to both stacks.

**Its weekly image prune reports failure between its first converge and its first deploy**, and that is expected rather than a fault to chase: with nothing deployed, no application contributes an image and no container holds one, so the keep set is empty and the unit abandons by its own documented contract. See stage 6.5. It goes green on the first Monday after stage 7 reaches that host — which is the observation that proves the stack is really running there, and the only one that cannot be made on the day.

**If you decide you do not want it yet**, delete `terraform/stacks/main-staging/` and `ansible/inventory/main-staging.hcloud.yml` and `ansible/inventory/group_vars/staging.yml`, drop `HCLOUD_TOKEN_MAIN_STAGING` from `ansible/.envrc`, remove its `HCLOUD_TOKEN_MAIN_STAGING` repository secret and its `main-staging` Environment (with the two secrets on it), drop its `.github/dependabot.yml` entry, and delete its Hetzner project and HCP workspace. Then skip staging wherever stage 6 says "once per stack". Nothing else in this document depends on it. Adding it back later is stages 1 to 4 again, against a running production system — which is the order this document is arranged to spare you.

## Stage 5. Tailscale

The private network. CI runners join it for the length of one job to reach a host; operators join it permanently. Both servers join it in stage 6. SSH for deploys never crosses the public internet.

**What you do in this stage:** create the tailnet, put **your workstation** on it, allow the CI tag, and create two credentials. **What you do not do: add either server.** Ansible joins each one in stage 6.3 using the auth key from §5.3; everything about a server in the Tailscale console — whether it is listed, its machine name, its key expiry — is done in §6.4, after it has joined. If the sign-up wizard asks you to add another device, skip it.

### 5.1 Create the tailnet

1. Sign up at login.tailscale.com. It offers identity providers (Google, Microsoft, GitHub and others) rather than a password; sign in with the **company's** account on that provider, not a personal one. The tailnet is created on that first login and belongs to that identity, and colleagues join it by logging in with an account from the same organisation.
2. Install the Tailscale client on your workstation and log in with the same account.

   **Linux:**

   ```sh
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up     # prints a login URL: open it and sign in with the account from step 1
   tailscale status      # your workstation, first line, with a 100.x.y.z address
   ```

   **Windows, including a WSL 2 workstation** — install it on Windows, not inside WSL: Tailscale recommends against running it inside WSL 2 (its default MTU is too small), and the Windows client carries WSL's traffic to the tailnet. In PowerShell:

   ```powershell
   winget install --exact --id Tailscale.Tailscale
   ```

   Then right-click the Tailscale icon in the system tray → **Log in**, which opens a browser; sign in with the account from step 1.

   **macOS:** download the standalone app from tailscale.com/download/mac, open it, and follow its prompts to log in.

   On any of them, the admin console's **Machines** page now lists this computer. That is the only machine that should be there at the end of this stage.

### 5.2 Access control: allow the CI tag

**`tag:ci` is not attached to anything by hand.** It is the label each CI job's runner carries while it is on the tailnet: `host-converge.yml` and `platform-deploy.yml` join through `tailscale/github-action` with `tags: tag:ci`, authenticated by the OAuth client from §5.3, so every runner joins as a short-lived node tagged `tag:ci` and is removed when the job ends. The servers and your workstation carry no tag. A tag cannot be given to an OAuth client until the policy file says who owns it, and that is all this step does.

Admin console → **Access controls** → edit the policy file. Add `tagOwners` as a top-level key, or add the line to the `tagOwners` block if the file already has one:

```json
"tagOwners": {
  "tag:ci": ["autogroup:admin"]
}
```

Both hosts run with no further restriction, so any tailnet member can reach either one's SSH port. For a company tailnet with more members, add an ACL rule that lets `tag:ci` and operators reach each host on port 22 and port 3000 (Grafana), and nothing else. Do that once both have joined and you know their tailnet names.

### 5.3 Two credentials

| Credential | Where | Settings |
|---|---|---|
| Auth key for the servers | Settings → Keys → Generate auth key | **Reusable**, **not** ephemeral, no tags, expiry as long as allowed (90 days). **One reusable key serves both hosts** — Ansible consumes it once per run and skips the join on a host already on the tailnet — so generate a second only if you make it single-use, or if you want to revoke one host's join without touching the other. A single-use key is also burnt by the *first* join, so a host that has to be rebuilt needs a fresh one. **Later, per server, once it has joined in stage 6.3** (§6.4 has you do it): Machines → that server → **Disable key expiry**, or that host silently drops off the tailnet in 180 days. It is a per-node setting; doing it for one host does nothing for the other. |
| OAuth client for CI | **Trust credentials** (called OAuth clients in older consoles) → Credential → OAuth | Scope **Auth Keys: Write**, with tag `tag:ci`, which is offered only once §5.2's `tagOwners` entry is saved. Produces a client ID and a client secret. |

**Secrets created in this stage**

| Name | Scope | Value from | Read by |
|---|---|---|---|
| `TAILSCALE_OAUTH_CLIENT_ID` | **Each** stack's GitHub Environment, infrastructure repository | The OAuth client — the same client's values in both | `platform-deploy.yml`'s deploy job and `host-converge.yml`'s converge job, both for **every** stack |
| `TAILSCALE_OAUTH_SECRET` | Same | Same | Same |
| The server auth key | Password manager only, no GitHub secret | The auth key | You, passing it with `-e tailscale_auth_key=…` in stage 6.3 — there is no prompt for it, and the role has no default, so omitting it fails inside `tailscale` after two roles have already changed the host. That form puts the key in your workstation's shell history, so clear it or accept it; §6.3a covers the separate exposure of running `tailscale up` by hand on the host |

Each application repository will need the same two OAuth values in stage 8; one OAuth client can serve all of them.

**`tag:ci` must reach every host, not production's alone.** The converge job joins the tailnet for whichever stack its matrix row names, and it reaches that host over the tailnet and by no other route — the cloud firewall admits the operator's range and nothing else. An access rule that admits `tag:ci` to one host leaves the other convergeable only from a workstation, which is the state this whole stage exists to end.

**Check:** your workstation is the one machine in Machines; the policy file saved with `tag:ci` in `tagOwners`; the auth key and the OAuth client's two values are in the password manager. **After stage 6.3, not now:** each server's **machine name is the server's own name** — `main-production` and `main-staging`. That is what the converge job looks the host up by: it asks `tailscaled` for the peer of that name and maps the answer, rather than trusting DNS. A name that does not match is a converge that cannot find its host.

**The machine name is not the same field as the name the host reports, and only one of them is this repository's to set.** The `tailscale` role pins what the host reports, to `{{ inventory_hostname }}`, so that the host's own name — which carries the company, `shatynska-main-production` — never drives it. The *machine* name is assigned when the host first joins and is changed in the Tailscale interface and nowhere else. A rename of either therefore has two halves: a commit for the first, and a click for the second.

## Stage 6. Ansible: configure the host

This stage is run from your workstation — **once per host, and only once.** Every converge after this one is a merge: `host-converge.yml` runs the same play, against the same inventory, on a merge to `main` touching `ansible/`, with production's waiting for the same Environment approval a Terraform apply waits for. §6.6 is where you hand that workflow what it needs.

The first converge cannot be the pipeline's, and the reason is not caution. The workflow reaches a host **through the tailnet**, and joining the tailnet is something this play does — so before it has run there is no route for CI to take. The host also carries no converge key yet, for the same reason: nothing has installed one. Both end the moment this stage succeeds.

This stage is run from your workstation. It installs Docker, the host firewall and fail2ban, joins the tailnet, creates the `deploy` account with a forced-command key per application, creates your unprivileged operator account, mounts the data volume, and arms the weekly image prune.

**Run it once per stack**, production first. Everything below takes the stack as an argument. **Two names are in play and they are not the same**: `<stack>` means `main-production` or `main-staging` and names the inventory source; `<environment>` means `production` or `staging` and names the Ansible group, the `group_vars` file and the Vault id. Each stack's own `pipeline.yml` states which environment it targets. The two runs share no `group_vars` file, no Hetzner token and no Vault password. What they may share is a value inside those files — the GHCR token and the heartbeat ping key are the same in both, encrypted separately; §0.4 says which is which. Do production first because it is the one you will check most carefully, and staging second because by then you are repeating a procedure you have just seen work.

### 6.0 The two tokens Ansible reads

Ansible does not use the `HCLOUD_TOKEN` you set up for Terraform in stage 4.1. That variable is scoped per stack *directory* by direnv, so its value depends on where you are standing — fine for Terraform, which is always run from inside a stack directory, and wrong for Ansible, which is always run from `ansible/`.

Instead, each stack has an inventory source of its own that names a credential of its own. Copy the example and fill in both read-only tokens from stage 1.2:

```sh
cd ansible
cp .envrc.example .envrc
direnv allow
```

**Without direnv**, `source .envrc` from `ansible/` once per shell — they are plain `export` lines, exactly as at §4.1. Unlike there, that is a perfectly good way to run this one and not a fallback with a catch: §4.1's warning exists because the root and staging `.envrc` files both export `HCLOUD_TOKEN` with different values, so an export outliving its directory points Terraform at the wrong project. These two variables collide with nothing and mean the same thing wherever you stand, which is why each inventory source names its own rather than sharing Terraform's.

Both are **Read Only** tokens. A wrong or missing one fails the run rather than producing a stack with no host in it, so a typo here cannot masquerade as a destroyed server.

### 6.1 Fill in the inventory variables

Edit `ansible/inventory/group_vars/<environment>.yml` — production's and staging's are separate files with separate values, and staging's is written from scratch rather than copied from production's. Every value except the last two is non-secret and committed; those two are Vault-encrypted in place.

| Variable | Set to |
|---|---|
| `hardening_ssh_allowed_cidrs` | Exactly the `ssh_allowed_cidrs` list from **that stack's** `terraform.tfvars`. They are kept in sync by hand; a mismatch makes the host firewall block what the cloud firewall allows. |
| `hardening_web_allowed_cidrs` | Exactly `web_allowed_cidrs` from that stack's `terraform.tfvars` — `["0.0.0.0/0"]` for both stacks. |
| `deploy_apps` | One entry: `name: platform`, `public_key:` the `.pub` of that environment's platform deploy key. **Each environment gets its own keypair** — one leaked private half must not deploy to both. Applications are added here when they are onboarded, one entry per application; `docs/onboard-an-application.md` is that procedure. |
| `ops_user_accounts` | One entry: `name: ops-<you>`, `public_key:` the `.pub` of your operator inspection key |
| `platform_data_volume_subdirs` | Leave as is |
| `ghcr_pull_username` | The GitHub username whose token is below. For an organisation, a dedicated machine user with read access to the application repositories is cleaner than a person's account. |
| `ghcr_pull_token` | Vault-encrypted, see below |
| `image_prune_heartbeat_ping_key` | Vault-encrypted, see below. **The play refuses to run without it** |

**The GHCR token.** The host must log in to GitHub's container registry to pull private application images. On github.com as the user above: Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate, scope **`read:packages`** only, expiry of your choice (note it in the password manager: when it expires, deploys start failing at `docker compose pull`). **Rotating it means re-encrypting one block per stack, each under that stack's own Vault password** — two edits, not one, and you need both passwords to hand.

**On the second stack's run you may reuse this token, and this repository does.** It is read-only against the same packages under the same account, so a second buys no isolation and adds a second thing to rotate — but two work, and nothing here depends on your choosing one. What *is* per stack either way is the encrypted block: you encrypt whichever value you chose again, under that stack's own Vault password.

Contrast the heartbeat ping key below, where reuse is not a preference: creating a second there **rotates** the first.

**Check the token before you encrypt it**, because a bad one is only discovered much later, at `docker compose pull`:

```sh
curl -sSD - -o /dev/null -u <the github username> https://api.github.com/user \
  | grep -iE 'HTTP/|x-oauth-scopes'
```

It prompts for a password; paste the token there, so it stays out of your shell history and out of `ps`. You want `200` and an `x-oauth-scopes` header naming `read:packages`.

- **`401`** — expired, revoked, or pasted truncated. These tokens are long; a missing tail looks exactly like a wrong token.
- **`200` with no `x-oauth-scopes` header at all** — this is a *fine-grained* token, not the **classic** one this procedure asks for. Fine-grained tokens carry no OAuth scopes, so there is nothing for the check above to read and no way to confirm from here that it can pull packages. Generate a classic token rather than reasoning about whether this one might work.
- **`200` with scopes that omit `read:packages`** — the right kind of token with the wrong scope.

**None of this is a gate**, so do not let it stop you: an absent GHCR credential is tolerated by design. `deploy_user` guards the registry login with a `when:` and skips it, per *Host Authenticates to GHCR for Application Image Pulls* (`openspec/specs/iac-host-configuration/spec.md`) — a host converged without one simply cannot pull private images, which matters only once an application deploys to it. Leave it unset — commented out, in a `group_vars` written from the template — and come back to it.

Choose a Vault password **for this stack** — production and staging get different ones, so that whoever can converge staging does not thereby hold the password protecting production's secrets — store it in the password manager, then encrypt the token in place:

```sh
cd ansible
ansible-vault encrypt_string --vault-id <environment>@prompt '<ghp_... token>' --name ghcr_pull_token
```

Paste the output block into `group_vars/<environment>.yml` in place of the existing `ghcr_pull_token` value. The encrypted block is safe to commit; the Vault password is not written anywhere in the repository.

Two things about `encrypt_string` that read as faults and are not:

- **It prompts `New Vault password (<environment>):` even when that vault already exists.** That is its wording for the encrypt direction, not an offer to create a second vault. Type the password you chose above — or, when adding a value to a file that already has encrypted ones, the password those were encrypted with. Ansible cannot tell you afterwards which password made a block: two values encrypted under different passwords produce a file that fails to decrypt with either, naming neither.
- **It only prints.** It writes to your terminal and edits nothing; copying its output into the file is a separate step you perform. The whole block goes in, `<name>: !vault |` line included.

Whenever you add an encrypted value, confirm the file still decrypts as a whole — this prints the value's length, never the value:

```sh
ansible localhost -m debug -a 'msg={{ <variable> | length }}' \
  -e @inventory/group_vars/<environment>.yml --vault-id <environment>@prompt
```

**The heartbeat ping key.** The `image_prune` role installs a weekly unit that reports each activation to an external observer, and it **asserts this input before any role in the play changes the host** — so an absent key aborts `host-baseline.yml` rather than installing a scheduled unit nothing watches.

Create it now, at the heartbeat service from stage 0.1: **Settings → Ping key → create**. One key addresses every periodic job's check, and the same value becomes the `HEARTBEAT_PING_KEY` repository secret in stage 7.3.

**On the second stack's run, reuse the key you already have — do not create another.** A project holds one ping key, so "create" there means *rotate*: every existing check would start rejecting pings from the value already Vault-encrypted in the first stack's `group_vars` and stored as `HEARTBEAT_PING_KEY`. **When you do deliberately rotate it, that is three places to update** — one encrypted block per stack, each under its own Vault password, plus the repository secret. The key is shared deliberately, and it still addresses a different check per host because the check name comes from the host's own name. Put it in the password manager, then encrypt it the same way:

```sh
cd ansible
ansible-vault encrypt_string --vault-id <environment>@prompt '<ping key>' --name image_prune_heartbeat_ping_key
```

The key must be a bare token of letters, digits, `_` and `-`; the role refuses anything else by name, because the value is rendered into a shell file its reporting script sources and a quote in it would make that script fail silently.

### 6.2 Check the inventory resolves

The inventory is dynamic: it asks the Hetzner API which servers exist and groups them by their `environment` label. It needs the read-only token from `.envrc`.

```sh
cd ansible
ansible-inventory -i inventory/<stack>.hcloud.yml --graph
```

You should see that stack's server under `@<environment>`, and under `@<tenant>` as well — one group per axis. If the command fails naming the source it could not parse, that stack's token in `ansible/.envrc` is missing or wrong — the run fails rather than showing you an empty inventory, which is the point.

**`Invalid Hetzner Cloud API Token: unable to authenticate (unauthorized)` does not mean the token is wrong.** It means the plugin was handed an empty one, and it says the same thing whether the value is revoked, mistyped, or *absent* — an unset variable templates to the empty string and Hetzner rejects that exactly as it rejects a bad token. So check the variable **name** before you go looking at Hetzner: the name this source reads must match the one your `ansible/.envrc` exports, and a checkout on an older commit reads an older name. That is the cheap explanation and it is usually the right one.

### 6.3 Run the playbook

```sh
cd ansible
ansible-playbook playbooks/host-baseline.yml \
  -i inventory/<stack>.hcloud.yml \
  -e target_environment=<environment> \
  --vault-id <environment>@prompt \
  --private-key ~/.ssh/<company>-root \
  -e tailscale_auth_key=<tskey-auth-... from stage 5>
```

**`company` must be right before this run, and nothing checks it for you.** The play's `hostname` role gives the host its own name, `<company>-<inventory_hostname>` — `shatynska-main-production` on the repository this was cloned from. It reads `company` from `ansible/inventory/group_vars/all.yml`, which is the single file a clone changes (§3.1 lists it among the things to edit). The role asserts the variable by name and refuses before touching the host if it is unset, so the failure you would get is loud — but it cannot tell that the value is *someone else's company*, and a host named for the repository you cloned from is a thing you find out months later on a shell prompt. Check it now, not after the converge.

**Do not add `--limit`.** The stack already selects the host set, there is nothing to narrow, and a limit filters the guard play's `localhost` out — so a run that reaches no host would exit 0 again, which is the failure the guard exists to end. `--tags` is safe — the guard is tagged `always` — with the single exception of `--skip-tags always`, which names that tag and switches the guard off.

Two prompts: the Vault password, and (if the key has one) the operator key's passphrase. A first run takes several minutes; Docker's installation is the slow part. A second run immediately afterwards should report `changed=0`; if it does not, something is not idempotent and worth understanding before moving on.

Do not rely on `--check` for the first run: apt-based tasks report changes they did not make and later tasks then fail against a stale package cache.

`--check --diff` is useful on every run after the first, with one thing to know before you read its output: **a healthy host reports `changed=2`, not zero.** Both are in the `tailscale` role — *Add the Tailscale apt signing key* and *Add the Tailscale apt repository* — and both are `get_url` tasks with no `checksum:`. Confirming such a file already matches would mean downloading it, which check mode will not do, so it reports "would change" every time and always will. Two is the baseline; compare against two, and read anything else.

**And two is a baseline for what check mode can see, which is less than the host.** `command` tasks skip under `--check` — `ops_user`'s three and `swap`'s four — and `geerlingguy.docker` carries `ignore_errors: "{{ ansible_check_mode }}"` on five, so failures there are swallowed. A clean check means no *file or package* drift was found; it is not a statement that the host is as this repository describes it. The change that moved the converge into a workflow **did not** turn this flag into a drift detector and did not remove those two tasks: a drift sweep needs the credential the gate withholds from the job a reviewer reads, and shipping one whose baseline is two would train an operator to discount the very signal it exists to create. `docs/backlog.md` carries the entry that owns both, and when it lands this paragraph changes with it.

### 6.3a When the run fails partway

It can, and the first converge of a host is where it is likeliest. **This section serves a failed pipeline converge too**, and the recovery is the same one: correct the input and run it again. Every role here is idempotent, so a second run reports `ok` for the work already done and carries on from where it stopped — whether that second run is this command or a re-run of the workflow. What differs is only that nobody is watching the pipeline's run while it fails, so the first you see of it is a red job. What a failure leaves is a **partially-converged host**: every role ahead of the failing one has applied in full, the failing role has applied up to the task that failed, and nothing after it has run.

That middle clause matters. In the case below the failing task is the *last* one in its role, so Tailscale is installed and `tailscaled` is running even though the host never joined the tailnet.

None of that is a reason to rebuild — **correct the input and run the same command again.** Every role here is idempotent, so the second run reports `ok` for the work already done and carries on from where it stopped.

**That assumes you can still reach the host.** `hardening` runs before `tailscale` and ends by enabling UFW, so at the moment of a tailscale failure the host answers on whatever `hardening_ssh_allowed_cidrs` allows — and the tailnet, which is the other way in, is precisely what has not come up. Both stacks here set an operator ISP range, so public SSH still gets you in. On a host configured for tailnet-only SSH, which the role permits and which is stricter than what this repository runs, a failure here would leave no way in at all, and rebuilding would be the recovery.

One failure hides its own cause, and it is the one most likely to bite on a first run. If *Bring the host onto the tailnet* fails, Ansible prints only:

```
fatal: [<host>]: FAILED! => {"censored": "the output has been hidden due to the
fact that 'no_log: true' was specified for this result", "changed": true}
```

That masking is deliberate, not a defect: the task's command carries the auth key, and `no_log` is what keeps it out of the run's output — the role's own comment says so. Do not go looking for a way to turn it off. Go to the host instead, and run the same command by hand, where nothing is masked:

```sh
ssh -i ~/.ssh/<company>-root root@<the host's ipv4>
systemctl is-active tailscaled     # expect: active
tailscale status                   # expect: Logged out.
read -rs KEY                       # paste the key, press Enter; it is not echoed
tailscale up --authkey="$KEY"      # this prints the real error
journalctl -u tailscaled -n 30 --no-pager
tailscale status --json | grep BackendState    # "Running" once it has joined
```

`read -rs` keeps the key out of `root`'s shell history, which is worth the extra line for a credential that is **reusable** and lives for 90 days (§5.3). Be clear about what it does not do: `--authkey="$KEY"` is expanded by the shell before `tailscale` runs, so the key is in that process's arguments and readable from `/proc/<pid>/cmdline` for as long as the command takes. On a first converge there is no unprivileged account on the host to read it — `ops_user` runs after `tailscale` — but on a re-converge of a configured host there is. This is weaker than §6.1's `curl` prompt, which never puts the token in an argument at all.

The usual causes, in rough order: the key was already consumed, because it was generated single-use rather than **reusable** (§5.3); it expired; it was pasted truncated; or the tailnet policy requires a tag the key does not carry. Once `BackendState` reads `Running`, `exit` and re-run the playbook. The `tailscale up` task will skip this time: its `when:` reads that same field, which is why the check above uses `--json` rather than plain `tailscale status`.

### 6.4 After the run

1. Tailscale admin → Machines: **the host you have just converged** is listed, under the server's own name (`main-production` or `main-staging`; §5.3's check says why). Note its tailnet IPv4 (`100.x.y.z`). Disable key expiry for it (stage 5.3) — per node, so this is done again after the other stack's converge.
2. Log in the way you will from now on, over the tailnet, unprivileged:

   ```sh
   ssh -i ~/.ssh/<company>-ops ops-<you>@100.x.y.z
   docker ps        # works: the account is in the docker group
   sudo -n true     # refused: the account has no sudo, by design
   ```

   That refusal is real, and it means anything needing root — starting a unit, reading a unit's journal, reading a `0600` file — cannot go through this account. Reach for Ansible instead, which authenticates as `root` with the operator key you already hold:

   ```sh
   cd ansible
   ansible <environment> -i inventory/<stack>.hcloud.yml \
     --private-key ~/.ssh/<company>-root \
     -m ansible.builtin.systemd_service \
     -a "name=<unit> state=started" --vault-id <environment>@prompt
   ansible <environment> -i inventory/<stack>.hcloud.yml \
     --private-key ~/.ssh/<company>-root \
     -m ansible.builtin.command \
     -a "journalctl -u <unit> -n 20 --no-pager" --vault-id <environment>@prompt
   ```

   Plenty is still readable unprivileged: `systemctl is-active`, `systemctl show --property=…`, `systemctl list-timers`, `stat`, and any world-readable file.

3. Commit and push `group_vars/<environment>.yml` through a pull request. The Molecule suite runs on it; that is the `ansible-verify` check.

**Secrets created in this stage**

| Name | Scope | Value from | Read by |
|---|---|---|---|
| Vault password, one per stack | Password manager only | You chose it | Anyone running that stack's playbook |
| `ghcr_pull_token` | One encrypted block per stack, of the same token value unless you chose two | GitHub classic PAT, `read:packages` | The playbook, to log the host's Docker into GHCR |
| `image_prune_heartbeat_ping_key` | One encrypted block per stack, of the same project ping key | The heartbeat service's project ping key | The prune unit's reporting script, on every activation. The same value becomes the `HEARTBEAT_PING_KEY` repository secret in stage 7.3, and addresses a different check per host because the check name comes from the host's name |
| `PLATFORM_DEPLOY_SSH_KEY` | **Each** stack's GitHub Environment, infrastructure repository — a different key in each | The **private** half of *that environment's* platform deploy key from stage 0. Store it, then delete the local file. Verify before storing that it is the right one: `ssh-keygen -lf ~/.ssh/<company>-platform-<environment>` must print the fingerprint of the public half committed in that environment's `group_vars` | `platform-deploy.yml`'s deploy job for that stack |
| `PLATFORM_DEPLOY_HOST` | **Each** stack's GitHub Environment, infrastructure repository | **Either** that server's tailnet IPv4 (`100.x.y.z`) **or** its tailnet machine name (the stack's name) — `platform-deploy.yml` accepts both and tests which it was given. **They fail differently, and that is the thing to choose on**; see below. **A TAILNET ADDRESS, NEVER A PUBLIC ONE**: the deploy reaches the host only over the tailnet, and this same value becomes Grafana's bind address, so a public address here publishes that stack's Grafana on the public interface. | `platform-deploy.yml`, for both the SSH target and Grafana's bind address |

**Which form to put in `PLATFORM_DEPLOY_HOST`, and why it is a real choice.** An earlier version of this document recommended the literal IP because it "avoids a resolution step", which is true and is not the reason that matters. The two forms survive different events, and neither survives both:

| Value | Survives a **rename** of the server | Survives a **rebuild** of the host |
|---|---|---|
| Tailnet IPv4 | **Yes** — the address is unchanged | **No** — a rebuilt host joins with a new address |
| Tailnet machine name | **No** — the machine is renamed with the server | **No** — Tailscale suffixes the rejoining node (`main-production-1`) and the dead one keeps the bare name, until you delete it as Appendix B says |

So the IP is the more durable of the two, and the name's advantage is only that it reads as a name. Whichever you choose, **it is not a value that maintains itself**: the rename case actually occurred — `rename-the-stacks-and-their-resources` renamed both servers and had to update this secret as a named step — and the rebuild case is Appendix B's. Nothing in this repository can check it, and nothing fails until the next merge touching `platform/`, which then fails looking like a network problem. Put it in the password manager entry beside the value, so the next person changing either one knows this exists.

**Check**, on each host you have converged: `sudo ufw status` as root shows default deny with 22 and the tailnet rules; `tailscale status --json` on the server reports `"BackendState": "Running"` (plain `tailscale status` prints the peer table, not that word); `systemctl list-timers` shows `prune-host-images.timer`; `/mnt/main` is mounted and holds `prometheus/` and `grafana/`, and `/etc/fstab` names that path and no other (the path matching the volume's name is a convenience; the two are independent, which is what lets a second stack in one project part them); and `hostname` returns `<company>-<stack>`, e.g. `shatynska-main-production`, while `tailscale status --json` reports `Self.HostName` as the stack's name alone.

The web ports are the same on both: **each shows 80 and 443 allowed.** A host without them means its `group_vars` has drifted from its `terraform.tfvars`. That checks the mirror and not reachability: UFW never sees Traefik's published ports (`docs/backlog.md`'s `say-what-the-host-firewall-actually-gates`).

**Then prove the prune reports.** Its timer is weekly, so nothing reaches the heartbeat service until it fires — and a reporter that cannot reach the observer leaves a *successful* unit behind by design, so a green `systemctl status` is not evidence. Trigger one activation and read what it says:

```sh
cd ansible
ansible <environment> -i inventory/<stack>.hcloud.yml \
  --private-key ~/.ssh/<company>-root \
  -m ansible.builtin.systemd_service \
  -a "name=prune-host-images.service state=started" --vault-id <environment>@prompt
ansible <environment> -i inventory/<stack>.hcloud.yml \
  --private-key ~/.ssh/<company>-root \
  -m ansible.builtin.command \
  -a "journalctl -u prune-host-images.service -n 20 --no-pager" --vault-id <environment>@prompt
```

The journal should carry `prune-host-images: considered N, removed M, refused R` and then a line from `prune-host-images-report` — `Created` on the first activation, which is the observer's own reply to a ping that brought the check into existence, and `OK` on every activation after it. A line reading `reporting … failed` names the endpoint and curl's status instead, and means the check is not being fed.

**`refused` should read 0 on a first activation.** If it does not, the journal also carries one `prune-host-images: refused <identity> -- <reason>` line per refusal, on standard error. A reason naming a container using the image means the keep set is wrong and wants investigating before you go further; one naming multiple repositories means an image this prune cannot reclaim and is not urgent. The role's README has both.

**Read that journal as `root`, not as the inspection account.** `ops-claude` is in `docker` and in no other group, so it is not in `systemd-journal` or `adm` — and `journalctl -u prune-host-images.service` run as that account prints `-- No entries --` rather than a permission error. That is indistinguishable from a unit that has never run, and it is a trap worth knowing about before it costs you an hour: it reads as evidence and is the absence of evidence. `systemctl show prune-host-images.service -p ExecMainStartTimestamp -p Result` needs no privilege and answers the same question honestly.

A check named `<inventory_hostname>-prune-host-images` should now exist at the heartbeat service — `main-production-prune-host-images` and `main-staging-prune-host-images`, one per host and distinctly named because the two servers are named differently on purpose. **Give each the period and grace from Appendix A now.** A check created by its own first ping carries the *observer's* default period, not the unit's weekly one, so until you correct it the observer will call a perfectly healthy weekly job overdue within a day.

### 6.5 Staging's prune fails, and that is the expected state

On staging, the run above will not say `considered N, removed M, refused R`. It will report that the run was **abandoned** because the keep set is empty, exit non-zero, and ping `/fail`. Nothing is wrong.

The prune protects images that a deployed application references or a running container holds. On a host where nothing is deployed there are neither, so an empty keep set is the honest answer — and the role treats it as a refusal rather than proceeding, because proceeding would mean `docker image prune -a`, weekly, reporting success. That guard is doing exactly what it exists to do.

So `main-staging-prune-host-images` is red from the moment it exists until the platform stack reaches it. Confirm the failure is *that* one — the journal should name the empty keep set, not a missing enumeration and not an unreachable observer — and leave it. What you must not do is mute it or delete the check: the alarm becomes meaningful the day staging runs something, and a muted check is one nobody re-arms.

**It does not go green by itself when the stack arrives, and this is the step everyone misses.** The check reflects the last *activation*, and the timer is weekly — so a stack deployed on Saturday leaves a red check until the following Saturday, with nothing wrong. Trigger one activation by hand after stage 7 reaches that host:

```sh
ssh -i ~/.ssh/<company>-root root@<that host's tailnet IP> \
  'systemctl start prune-host-images.service; \
   journalctl -u prune-host-images.service -n 25 --no-pager'
```

What you are reading for is the transition, and the journal shows both sides of it in one place:

    prune-host-images: abandoned -- the keep set is empty     <- before the stack
    prune-host-images: considered 8, removed 0, refused 0     <- after it

`considered N` with N at least 1 is the confirmation; `removed 0` is correct on a host whose images are all in use, and `refused 0` is what says so — a `removed 0` beside a non-zero `refused` means the run did offer images and the runtime turned it down, which is a different state entirely. **N should equal the number of services in `platform/docker-compose.yml`** plus whatever any deployed application contributes — anything less means an enumerated application is not rendering an image reference.

### 6.6 Hand the converge to the pipeline

Everything above happens once per host. From here the same play reaches that host on a merge to `main` touching `ansible/` — `host-converge.yml`, whose converge job attaches to that stack's own GitHub Environment, so production's waits for the same approval a Terraform apply waits for and staging's does not. Do this for **each** stack once its first converge has succeeded.

**Install the converge key on the host.** The public half of the keypair §0.3 has you generate, appended to `root`'s own `authorized_keys` — not to the operator's file, and not through Ansible, which manages neither:

```sh
ssh-copy-id -i ~/.ssh/<company>-ansible-ci-<stack>.pub \
  -o IdentityFile=~/.ssh/<company>-root root@<the host's tailnet name>
ssh -i ~/.ssh/<company>-ansible-ci-<stack> root@<the host's tailnet name> true
```

The second line is the check, and it is not optional: a key that is installed but not *usable* fails the pipeline's converge rather than this stage, where you are watching. Run both from a machine on the tailnet — the same route CI takes.

**Then store the two secrets, on that stack's GitHub Environment**, not as repository secrets. Both are read only by a job that has passed that Environment's protection rules, which is the whole reason they live there:

```sh
gh secret set ANSIBLE_SSH_PRIVATE_KEY --env <environment> <~/.ssh/<company>-ansible-ci-<stack>
gh secret set ANSIBLE_VAULT_PASSWORD --env <environment>
```

**The first command above carries both axes, a few characters apart, and that is not a typo.** The key's filename is `<stack>` and `--env` is `<environment>`: the key is a per-stack artefact and is named for its stack, while a GitHub Environment is still named for the environment. The second command carries only the Environment, having no file to read.

**`--env` takes the `<stack>`**, like this stack's converge key, its read-only secret, its HCP workspace and its inventory source. It did not always: a GitHub Environment was named for the environment until `rename-the-github-environments` moved both onto the stack axis, which needed a re-creation because GitHub offers no rename for a deployment Environment. This paragraph exists to say which argument is which, since **every other command in this stage still takes the `<environment>`** — the Ansible group, the `--vault-id` label and the `group_vars` file are all on that axis and stay there.

**A mistyped `--env` fails loudly rather than quietly**, which is worth knowing either way: to encrypt a secret `gh` first fetches that Environment's public key from GitHub's REST API, and that request returns `404 Not Found` for an Environment that does not exist — measured against this repository on 2026-09-12. **Do not read that reassurance across to a workflow's own `environment:` key**, which behaves the other way: GitHub's documented behaviour there is to create the Environment it names, with no protection rules.

Then delete the local private half, exactly as you do for the platform deploy key. Keep the Vault password in the password manager — it is still the only thing that can decrypt that stack's `group_vars`, and it is now in two places rather than one, which is the point: a second operator no longer means handing over a password and a root key.

**Check**, on the next merge that touches `ansible/`: the run shows the diff before any approval; staging converges unattended; production's job waits. Read staging's before approving production's — that is what makes staging the rehearsal rather than a second production.

**How to read it, because `gh run view <run> --log` will not.** Both converges are jobs of **one** run, so the run is unfinished precisely until production's job — the one you are deciding about — has finished, and the run-level log refuses until then:

```
run <run id> is still in progress; logs will be available when it is complete
```

`--job <id>` does not lift that: the refusal is a property of the run, not of the job. What works is the jobs API, which serves a **finished** job's log from inside a run that is still going:

```sh
run=$(gh run list --workflow host-converge.yml --limit 1 --json databaseId -q '.[0].databaseId')
job=$(gh run view "$run" --json jobs -q '.jobs[] | select(.name == "converge (<staging stack>)") | .databaseId')
gh api "repos/{owner}/{repo}/actions/jobs/$job/logs"
```

`{owner}` and `{repo}` are `gh`'s own placeholders and resolve from the checkout you run this in. The job is selected **by name**, because the jobs are not ordered by stack — and a name that matches nothing fails one step later than it happens: the `select` exits **0** with `$job` empty, and the request that follows asks for a job with no id and returns `gh: Not Found (HTTP 404)`, which reads like a missing log or a permissions problem rather than like a stack name that is not this repository's. Measured on 2026-09-13. When you meet that 404, list what the run actually has before suspecting the route:

```sh
gh run view "$run" --json jobs -q '.jobs[].name'
```

**For production's own converge while it is running**, the API has nothing to serve — a job's log exists once the job has finished. The web interface streams a running job's output live, and that is the route for watching that one. What you are reading either log *for* is the three lines below.

**Two ways a gated converge fails that are not about your host, met on 2026-09-12 and worth recognising rather than diagnosing twice.**

- **It dies at *Install Galaxy content*, before Ansible reads anything.** That step runs `ansible-galaxy install` against `galaxy.ansible.com` at converge time, with no retry and nothing vendored, so an upstream hiccup fails the job — and on the production path it fails *after* you have granted the approval, which then has to be requested and granted again. The signature is a `[WARNING]: Skipping Galaxy server` line naming a collection, followed by an `[ERROR]` about the ansible-galaxy cache. Re-run the failed job; it is transient. `docs/backlog.md` entry 23 is the change that would stop it.
- **It sits waiting behind a converge you forgot about.** Converges are serialised per stack, and an approval request that nobody grants stays pending for as long as GitHub keeps it. A production converge raised at 06:26 was still waiting when a later merge raised its own; the new one reported *"waiting on converge (main-production) … to complete"*, which reads like a stuck job and is a queue. **Approval requests look identical to each other** — the Terraform apply, the host converge and the platform deploy all gate on the same Environment and render the same prompt — so read which *workflow* and which *job* you are approving, not just the Environment name.

**What a healthy converge looks like**, so that a green tick is not the thing you read. Three lines, in this order:

- `<stack>: converging '<server name>' for group '<environment>', resolved from the tailnet netmap` — the name between the quotes is a **bare name**. Anything else there, a JSON fragment most of all, means the address derivation is wrong rather than the host.
- `<server name> | SUCCESS => { "msg": <a number> }` — the preflight, which proves this stack's Vault password decrypts its `group_vars` before any role touches the host. A number, never a value.
- `PLAY RECAP … <server name> : ok=<n> changed=0 failed=0` — **`changed=0` is the expected result on an already-converged host.** A non-zero `changed` is the host having drifted from what the repository says, and is worth understanding before you do anything else. It is not the `changed=2` of §6.3: that is check mode, and this is a real converge.

**A merge that changes nothing under `ansible/` converges nothing, and that is correct.** The workflow is filtered to that directory, so a change to the workflow itself, to `.github/tests/` or to documentation triggers no converge — which is what you want, and is also the case most likely to leave you waiting for a run that is never coming. When you need one anyway — after fixing the workflow, or after rebuilding a host — dispatch it:

```sh
gh workflow run host-converge.yml --ref main -f stack=<stack>
gh run list --workflow host-converge.yml --limit 1
```

Leave `-f stack=` off to converge every stack; name one to converge only that. A dispatched production converge waits for the same approval a merged one does — the gate is on the job, not on the trigger. This is also the only way to converge before any change to `ansible/` exists to carry one, which is the state you are in the first time you finish §6.6.

**Secrets created in this step**

| Name | Scope | Value from | Read by |
|---|---|---|---|
| `ANSIBLE_SSH_PRIVATE_KEY` | That stack's GitHub Environment | The private half of that stack's converge keypair (§0.3) | `host-converge.yml`'s converge job, to authenticate as `root` on that host |
| `ANSIBLE_VAULT_PASSWORD` | That stack's GitHub Environment | The Vault password you chose in §6.1, that stack's own | Same job, to decrypt that stack's `group_vars` |

## Stage 7. The platform stack

Traefik, PostgreSQL and monitoring, deployed by `platform-deploy.yml` on a merge to `main` that touches `platform/`. The workflow renders a `.env` from secrets, joins the tailnet, and pipes the Compose file and `.env` to the server over the forced-command SSH key. Everything below is preparation for that one merge.

### 7.1 Third-party services

**Slack.** In the workspace, create a channel `#alerts`. Then api.slack.com → Your Apps → Create New App → From scratch → enable **Incoming Webhooks** → Add New Webhook to Workspace → choose `#alerts`. Copy the webhook URL. The channel name is fixed in `platform/docker-compose.yml`'s Alertmanager config; change it there if you named the channel differently.

**Heartbeat.** At healthchecks.io (or an equivalent), create a check named `<stack>-alertmanager` — `main-production-alertmanager`, `main-staging-alertmanager` — the stack's name and the job's, the same shape Appendix A's table gives every other check. **One per stack, and each stack's ping URL goes in its own Environment**: a single check fed by two hosts stays green while either is alive, which is the opposite of what a dead-man's-switch is for. No company segment: one company per heartbeat account, so the account boundary already carries it (`docs/naming-conventions.md`). Period **5 minutes**, grace **5 minutes**: Alertmanager pings it every 2 minutes, and the service must expect pings at least that often but tolerate one missed one. Copy the ping URL. Configure where that service should alert you when pings stop, ideally somewhere other than the same Slack workspace: this is the alarm for when everything else is down.

**Periodic-job heartbeats.** The project ping key already exists — stage 6.1 created it, because the host play refuses to run without it. It addresses one check per periodic job, listed with its period and grace in Appendix A, and it is also the `HEARTBEAT_PING_KEY` **repository** secret in stage 7.3.

Nothing needs creating by hand: each job creates its own check on its first ping (`?create=1`). But an auto-created check carries the vendor's **default** period, so once each appears, set it to the value Appendix A gives — otherwise a weekly job alarms daily and you learn to ignore it. Route these checks to Slack `#alerts`, **not** to the destination the `alertmanager` check above alerts to: that one is the alarm for when everything is down, and a weekly continuous-integration failure must not erode it.

### 7.2 Generate the platform's own passwords

```sh
openssl rand -base64 32   # run three times
```

### 7.3 Secrets

**All in the GitHub Environment of the stack you are doing this for**, and a set of its own per stack — `--env main-production` or `--env main-staging`, on the stack axis like every other Environment. Nine secrets in total per stack: the seven below, plus `PLATFORM_DEPLOY_SSH_KEY` and `PLATFORM_DEPLOY_HOST` from stage 6.4.

**No value is shared between stacks, and none is held as a repository secret.** A repository secret holds one value, so a `PLATFORM_*` name defined there would render the same database password, the same dashboard credential and the same alert targets onto every host — and a GitHub Environment secret shadows a repository one of the same name, so the mistake would be invisible on the stack that also defines it and live on every stack that does not.

| Name | Value from |
|---|---|
| `PLATFORM_ACME_EMAIL` | A monitored company mailbox. Let's Encrypt sends certificate-expiry warnings here. |
| `PLATFORM_POSTGRES_USER` | A name for the shared instance's superuser, for example `platform_admin` |
| `PLATFORM_POSTGRES_PASSWORD` | First generated password |
| `PLATFORM_POSTGRES_EXPORTER_PASSWORD` | Second generated password. You will type it into Postgres by hand in 7.5. |
| `PLATFORM_GRAFANA_ADMIN_PASSWORD` | Third generated password. Grafana's `admin` login. |
| `PLATFORM_SLACK_WEBHOOK_URL` | The Slack webhook URL |
| `PLATFORM_DEADMANSWITCH_URL` | The heartbeat ping URL |

Together with `PLATFORM_DEPLOY_SSH_KEY`, `PLATFORM_DEPLOY_HOST`, `TAILSCALE_OAUTH_CLIENT_ID` and `TAILSCALE_OAUTH_SECRET` from earlier stages, that is the complete set `platform-deploy.yml` reads.

**A missing one fails the deploy before it touches the server, and by name.** The job's first step reads all nine and refuses if any resolved empty, naming the stack, the Environment and each empty name — because a GitHub secret that is not defined resolves to an *empty string* rather than to an error. That matters most for the values rendered into `.env`: `docker-compose.yml` interpolates each as `${VAR}` with no error-if-unset form, so an absent one becomes an empty assignment, and a service that tolerates an empty value starts, satisfies `docker compose up --wait`, and leaves the run green. An empty `PLATFORM_GRAFANA_ADMIN_PASSWORD` is the case to have in mind: a green deploy, and Grafana with no credential on it.

**Two of the seven are registrations, not values you invent, and each stack needs its own.** The Slack webhook should address a **channel of that stack's own** and the dead-man's-switch URL a **check of that stack's own**. Nothing in the running stack says which host an alert came from — Prometheus declares no `external_labels` — so the delivery target is the only thing that distinguishes them, and two stacks pointed at one channel produce alerts nobody can attribute. **No check in this repository reports that**, which is why it is written here rather than left to a build to catch.

One more secret belongs to this stage and is **not** in the table above, because it must not be scoped the way those are:

| Name | Where | Value from |
|---|---|---|
| `HEARTBEAT_PING_KEY` | **Repository** secret — Settings → Secrets and variables → Actions, *not* the `main-production` Environment | The project ping key stage 6.1 created and put into Ansible Vault, unchanged |

Scoping it to the `main-production` Environment would break it: a job reading an Environment secret waits on required-reviewer approval, and an alarm that waits for a human to approve its own delivery is not an alarm. The scheduled workflows read it with no `environment:` declared, and they turn red naming it if it is absent.

### 7.4 Deploy

The workflow triggers on a change under `platform/`. Open a pull request that makes one, even a one-line edit to `platform/README.md` naming the company. PR Validation runs `docker compose config` against it. Merge. In Actions, **Platform Deploy** discovers every stack whose declaration opts in and runs one deploy job per stack, having first posted the diff to the run's summary from a job holding no credential. A stack whose Environment requires a reviewer waits there; approve it. Each deploy job succeeds only when every service on that host reports healthy, and one stack's failure does not cancel or delay another's.

**The trigger is `platform/**` and the opt-in lives under `terraform/stacks/`**, which that filter does not match. A merge that opts a stack in and touches nothing under `platform/` therefore starts no run at all — the stack arrives at the next platform change. To deploy to it straight away, run **Platform Deploy** from Actions with that stack's name as the `stack` input. The same dispatch is what redeploys to a single rebuilt host without waking every other stack's gate (Appendix B).

**Doing this for a second stack** is this stage over again with that stack's own values, and nothing under `.github/workflows/` changes: set its nine secrets (§7.3), add `deploys_platform: true` to its `pipeline.yml`, merge, then §7.5 against that host.

### 7.5 Two manual steps the automation deliberately does not do

**Run both once per stack, against that host**, each with that stack's own values. They are not repeated across hosts by anything: each host has its own Postgres instance and its own heartbeat check.

**The monitoring role in Postgres.** postgres-exporter connects as a restricted role that nothing creates automatically. From your operator account on the server:

```sh
docker exec -it platform-postgres-1 psql -U <PLATFORM_POSTGRES_USER> -c \
  "CREATE ROLE pgexporter WITH LOGIN PASSWORD '<PLATFORM_POSTGRES_EXPORTER_PASSWORD>'; GRANT pg_monitor TO pgexporter;"
```

**Nothing tells you if you skip this step or mistype the password, so confirm it by hand.** This document said until 2026-09-15 that `MetricsTargetDown` fires until the role exists, and it does not: that alert is `up == 0`, and postgres-exporter serves `/metrics` with HTTP 200 whether or not it can reach the database. Measured against the pinned `v0.20.1` with a wrong password: HTTP `200`, `pg_up 0`, `pg_exporter_last_scrape_error 1`, container healthy, no alert. So the failure this step exists to prevent is silent, and the stack runs with PostgreSQL's metrics simply absent. `docs/backlog.md` `alert-on-the-exporter-being-unable-to-read-postgres` is the alert that would close it.

**Confirm the exporter can actually read the instance:**

```sh
docker exec platform-postgres-exporter-1 wget -qO- http://localhost:9187/metrics \
  | grep -E '^pg_up |^pg_exporter_last_scrape_error '
```

`pg_up 1` and `pg_exporter_last_scrape_error 0` is the pass. Anything else means the role or its password is wrong, and this is the only place it will be noticed.

**Then confirm the targets are scraped at all, and do it from inside the container.** Only Traefik (80, 443) and Grafana (the tailnet address, 3000) publish a host port — every other service in this stack is reachable on the Docker network alone, so `curl localhost:9090` on the host returns nothing at all. That silence looks like a broken Prometheus and is not:

```sh
docker exec platform-prometheus-1 wget -qO- "http://localhost:9090/api/v1/targets?state=active"
```

All five active targets should report `"health":"up"` — `prometheus`, `node-exporter`, `cadvisor`, `traefik` and `postgres-exporter`. **This does not confirm the role**, for the reason above: postgres-exporter's target reports `up` with the credential wrong, so this check answers whether the container is being scraped and the `pg_up` check answers whether the scrape means anything. Both are needed.

**The heartbeat.** Nothing to run; confirm in the heartbeat service that this host's own check is receiving pings every couple of minutes. Give it the period and grace Appendix A records — a check created by its first ping carries the observer's default until corrected.

**Check**, on each host you have deployed to: `docker ps` shows **eight** `platform-*` containers, all `(healthy)` — one per service in `platform/docker-compose.yml`, which is the count to check against rather than the number written here; `http://<that host's tailnet IP>:3000` from your workstation opens **that stack's** Grafana, and `admin` with that stack's Grafana password shows three dashboards; the heartbeat service shows that host's own check as up; a test alert (temporarily lower a threshold in the rules and redeploy, then revert) arrives in that stack's own Slack channel.

**Two of those are also the check that the stacks are genuinely separate**, and it is worth making deliberately the first time a second stack is deployed: the two Grafanas must want different passwords, and the test alert must arrive in one channel rather than both. If either fails, a value was copied between Environments — which no build reports.

**Secrets created in this stage:** the seven in 7.3, per stack.

## Stage 8. Onboarding an application

Repeat this for every service. The procedure is `docs/onboard-an-application.md`, a document of its own because it is read once per application rather than once per server — out of order, years apart, by someone who is not bootstrapping anything. Everything this stage used to carry is in it, including the database recipe and the reasoning beside it.

Three things a reader of this sequence wants at this point, each stated in full there:

- **It repeats per application per deploy target**, not once per server. The infrastructure side sits on the environment axis: `deploy_apps` lives in `ansible/inventory/group_vars/<environment>.yml`, so an application's deploy key, its `authorized_keys` line and its `sudoers` rule are one set per application per environment.
- **Its first step is the application's name**, which must equal the last segment of its image repository, because image reclamation on the host identifies an application's images by that rule and silently reclaims nothing if they differ.
- **Two of its steps have a prerequisite outside the application's control**: the `deploy_apps` entry needs a converge, which is a merge to `main` touching `ansible/`, and the database recipe needs that target's Environment to exist in the application's own repository first.

**Secrets created in this stage:** none in this repository. The ones an onboarding creates live in the application's own repository, one set per deploy target, and that document lists them.

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
4. **Pre-commit autoupdate** runs weekly and opens a pull request. Dispatch it once here, so its heartbeat check comes into existence and can be given the period and grace from Appendix A — otherwise the check first appears a week later, on its own schedule. **Its prerequisite is §3.2's GitHub App and the two secrets §3.3 sets from it**: the job's fifth step mints a token from them, so on a clone that skipped either, this dispatch runs four green steps — checkout, Python, the `pre-commit` install, the autoupdate itself — and then fails at the mint, rather than at anything to do with hooks.
5. **Prove that silence alarms.** Everything else you have tested proves a ping *arriving*. The whole design rests on the opposite — that a job which stops reporting is as loud as one that fails — and nothing in the repository can demonstrate it, because the alarm belongs to a third party's timeout.

   At the heartbeat service, add a check named `scratch-delete-me`, period **5 minutes**, grace **1 minute**, routed to `#alerts`. Ping it once, then leave it alone:

   ```sh
   curl -fsS https://hc-ping.com/<its-uuid>
   ```

   Within about six minutes Slack should carry *"scratch-delete-me is DOWN. Reason: success signal did not arrive on time, grace time passed."* — with nothing having failed anywhere. Then delete the check; on a 5-minute period it will keep alarming.

   If that message does not arrive, the routing works for failures and not for silence, and every periodic job on this host is unwatched in the one way that matters most.
6. **Confirm nothing reaches a host from your machine any more.** All three layers now go through the pipeline: Terraform through `apply.yml`, the platform stack through `platform-deploy.yml`, and the host configuration through `host-converge.yml`. What your workstation keeps is deliberate and is all of it — the read-only Hetzner tokens, the Vault passwords, the operator keys, and the *first* converge of a host, which cannot be the pipeline's because it is what puts the host on the tailnet the pipeline arrives over. Applying, deploying and converging are merges. If you find yourself running `ansible-playbook` against a host that is already configured, something in this stage was not finished.
7. **Know what a merge touching more than one layer does, because the stages above never show you.** Each stage here touches one layer at a time, so the first time several fire at once is the first ordinary change you ship — which is after you have stopped reading this document.

   A merge raises **one run per workflow whose path filter it matches**, and they start together with nothing sequencing them. `apply.yml` and `host-converge.yml` each fan out per stack inside a single run, so `gh run list` shows one row per workflow and the per-stack jobs are inside it — a merge touching all three layers is three rows and three production approvals, not six rows. Read the **workflow** name on each prompt: all three gate on the same Environment and render the same text, which is what `docs/backlog.md` entry 26 is about.

   **One ordering among them is load-bearing: converge before deploy, always.** The host layer creates what the platform layer mounts, so a deploy approved first binds a path the converge has not made yet. Docker does not fail on a missing bind source — it creates it, as an empty root-owned directory on the **root disk** — so both containers come up healthy and empty, and the converge that follows mounts the volume *over* that directory, leaving them writing to the shadowed copies. Nothing about the symptom points at the cause. The repair is to re-run Platform Deploy once the converge is green; no data is lost, because the real filesystem was on the volume throughout.

   The Terraform apply is not in that ordering and may be approved at any point — but never before reading its `plan` job's summary, which is published before the approval is requested precisely so you can. An approval prompt with nothing read behind it is the habit the plan/apply split exists to prevent.

8. **Record what you built.** In the password manager, alongside each secret, note its expiry, the stage that created it, and what breaks when it expires. In the repository, update `README.md`'s Status section.

## Appendix A. Complete secret inventory

Every credential the system uses, in one place. "Env" means a GitHub Environment; where a row names one, it says which.

**A repository secret, an HCP workspace and a GitHub Environment are named for the stack** — `main-production`, `main-staging` — while the Ansible group, the `group_vars` file and the Vault id are named for the environment: `production`, `staging`. The two coincided while this repository had one tenant and do not now. `docs/naming-conventions.md` is the scheme. **The GitHub Environment was the last to move**, because GitHub offers no way to rename one: `rename-the-github-environments` re-created both and re-entered every secret they held.

The Hetzner rows come in pairs, one per stack, because a Hetzner token reaches exactly one project. The `TF_API_TOKEN` row does not: one HCP user token serves both workspaces.

| Name | Where | Created in | Value from | Breaks when wrong |
|---|---|---|---|---|
| Production Hetzner Read Only | repo-root `.envrc` as `HCLOUD_TOKEN`; **`ansible/.envrc` as `HCLOUD_TOKEN_MAIN_PRODUCTION`**; repo secret `HCLOUD_TOKEN_MAIN_PRODUCTION` | 1 | The production Hetzner project → API tokens | Production's local plans, PR plans and drift detection; production's Ansible inventory source, locally and in the converge workflow. **Rotating it means editing two local files and one secret** — miss `ansible/.envrc` and the next local converge dies at inventory parse. The repository secret and the `ansible/.envrc` variable share a name on purpose: the converge job exports the declared secret under the name the inventory source reads |
| Production Hetzner Read & Write | `main-production` Env secret `HCLOUD_TOKEN` | 1 | Same project | Production's apply job |
| Converge key, **per stack** | That stack's Env secret `ANSIBLE_SSH_PRIVATE_KEY`; public half in `root`'s `authorized_keys` on that host | 2 | You generate it (§0.3) | `host-converge.yml`'s converge job, as `root`. **Revoking it is an edit on the host** — no role owns that file |
| Vault password, **per stack** | Password manager **and** that stack's Env secret `ANSIBLE_VAULT_PASSWORD` | 2 | You chose it (§6.1) | The play, locally and in the converge job. Two places rather than one deliberately: a lost workstation no longer means a host nobody can converge |
| Staging Hetzner Read Only | `terraform/stacks/main-staging/.envrc` as `HCLOUD_TOKEN`; **`ansible/.envrc` as `HCLOUD_TOKEN_MAIN_STAGING`**; repo secret `HCLOUD_TOKEN_MAIN_STAGING` | 1 | The **staging** Hetzner project → API tokens | Staging's local plans, PR plans and drift detection; staging's Ansible inventory source, locally and in the converge workflow. Two local files here too |
| Staging Hetzner Read & Write | `main-staging` Env secret `HCLOUD_TOKEN` | 1 | Same project | Staging's apply job |
| `TF_API_TOKEN` | Repo secret and **both** Env secrets; `terraform login` locally | 2 | HCP Terraform → **Account settings** → Tokens (a USER token; an organisation token cannot write state) | Every Terraform job, and `terraform init` locally |
| Operator SSH key | Workstation | 0 | `ssh-keygen` | Root access; Ansible |
| Operator inspection key | Workstation | 0 | `ssh-keygen` | Daily unprivileged login |
| Tailscale server auth key | Password manager | 5 | Tailscale → Keys | Joining a host to the tailnet (first run, rebuilds). One reusable key serves both hosts; see §5.3 |
| `TAILSCALE_OAUTH_CLIENT_ID` / `_SECRET` | Env secret, infrastructure and each app repo | 5 | Tailscale → OAuth clients | Every deploy job |
| Vault password, one per stack | Password manager | 6 | Chosen | Running that stack's playbook |
| `ghcr_pull_token` | One encrypted block per stack, in each `group_vars/<environment>.yml` — of the same token value, unless you chose two | 6 | GitHub classic PAT, `read:packages` | Pulling private images at deploy |
| `PLATFORM_DEPLOY_SSH_KEY` | **Each** stack's Env secret — a different key in each | 6 | `ssh-keygen`, that environment's own platform key (§0.3) | That stack's platform deploy. One leaked private half deploys to one host |
| `PLATFORM_DEPLOY_HOST` | **Each** stack's Env secret | 6 | Tailscale → Machines, that host's **tailnet** address | That stack's platform deploy, and its Grafana bind. A public address here would publish that stack's Grafana on the public interface |
| `PLATFORM_ACME_EMAIL` | **Each** stack's Env secret | 7 | A mailbox | Certificate registration |
| `PLATFORM_POSTGRES_USER` / `_PASSWORD` | **Each** stack's Env secret, its own values | 7 | Chosen / generated per stack | That host's Postgres startup; every manual `psql` there |
| `PLATFORM_POSTGRES_EXPORTER_PASSWORD` | **Each** stack's Env secret, and typed into that host's Postgres | 7 | Generated per stack | That host's Postgres metrics |
| `PLATFORM_GRAFANA_ADMIN_PASSWORD` | **Each** stack's Env secret, its own value | 7 | Generated per stack | That stack's Grafana login |
| `PLATFORM_SLACK_WEBHOOK_URL` | **Each** stack's Env secret | 7 | Slack app, **a channel per stack** | Alert delivery. Nothing labels an alert with its host, so the channel is what attributes it |
| `PLATFORM_DEADMANSWITCH_URL` | **Each** stack's Env secret | 7 | Heartbeat service, **a check per stack** | The external alarm. One check fed by two hosts stays green while either is alive |
| `HEARTBEAT_PING_KEY` | **Repo** secret, and Vault-encrypted in each `group_vars/<environment>.yml` | 7 | Heartbeat service → project ping key | Nothing notices a periodic job failing or stopping |
| `APP_CLIENT_ID` / `APP_PRIVATE_KEY` | **Repo** secrets | 3 | The GitHub App (§3.2) — client id from its settings page, private key downloaded once at creation | The weekly hook-update pull request stops being opened, and **nothing says so**: the workflow's heartbeat check reports that the *run* happened, not that a pull request came out of it, so a run that fails at the minting step still looks like a job that had nothing to do. Hook revisions then quietly stop being updated. The key does not expire; the App being uninstalled or its key revoked is what breaks it |
| `<APP>_DEPLOY_SSH_KEY`, `DEPLOY_HOST`, app secrets | App repo Env secrets | 8 | Stage 8 | That application's deploys. **One set per deploy target** — a different key and a different host in each, like the per-stack rows above |

`HEARTBEAT_PING_KEY` is a **repository** secret, never an Environment one: a job reading a `main-production` Environment secret waits on required-reviewer approval, and an alarm that waits for a human to approve its own delivery is not an alarm. The same value goes into Ansible Vault for the host's prune unit.

The checks it addresses, and the settings each needs at the observer. A check comes into existence at its job's first ping and carries the vendor's default period until it is corrected here — so read these back once each check exists, and again after any rebuild:

| Check (slug) | Reported by | Period | Grace |
|---|---|---|---|
| `infrastructure-drift` | `.github/workflows/drift.yml`, nightly | 1 day | 12 hours |
| `infrastructure-pre-commit-autoupdate` | `.github/workflows/pre-commit-autoupdate.yml`, weekly | 7 days | 2 days |
| `main-production-prune-host-images` | `prune-host-images.service` on the production host, weekly | 7 days | 2 days |
| `main-staging-prune-host-images` | `prune-host-images.service` on the staging host, weekly | 7 days | 2 days |

The graces are set against **observed** scheduling, not against the `cron:` line: GitHub starts these runs hours after the minute they name — over four hours late, consistently, on the nightly — so a tolerance derived from the declared time would alarm on a healthy system.

The host slug is templated from `inventory_hostname`, which is why the two servers are named differently in their `terraform.tfvars` — sharing a name would merge them into one check, where the live host's weekly success would keep it green while the other's timer was dead.

**Staging's prune check is red only between its first converge and its first platform deploy.** §6.5 says why — an empty keep set is a refusal, not licence to remove everything — and that interval ends at stage 7, which now runs for staging too. A prune check still red on the first Monday after a deploy is a real failure to read rather than the expected state.

**Not in this table: the per-stack Alertmanager checks** (`<stack>-alertmanager`, §7.1). They are addressed by a ping URL of their own rather than by the project ping key, one per stack, each held as that stack's `PLATFORM_DEADMANSWITCH_URL`. Count them against the free tier's twenty alongside the rows above: two stacks is six checks, not four.

## Appendix B. Rebuilding an existing host

**This covers either host.** It is written for production, which carries the applications; staging is rebuilt the same way through stage 6 and then through stage 7, its platform stack redeployed by the dispatch the sequence below names. Its DNS points at its address as production's does, so 4.4 applies to it as well if the address changed — every staging row in 4.4's tables — and its certificates reissue on their own once its applications redeploy.

An important consequence for staging specifically: its data volume is **not** wiped by a rebuild, and its `known_hosts` entry **is** invalidated. The second is the one that bites, because it presents as the converge failing at connection time rather than as a rebuild artefact.

**Delete the old machine from the tailnet, and do it for either stack.** Tailscale deduplicates machine names by suffixing, so a rebuilt host joins as `main-production-1` while the dead node keeps `main-production` — and it keeps it indefinitely, because §6.4 had you disable key expiry on it. `host-converge.yml` looks its target up by that bare name, so every converge would then resolve to a peer that no longer exists and fail at the host-key step, with a message that reads as an unreachable host rather than as a rebuild artefact. That message names this cause, but the fix is here. The same rebuild also costs the host its converge key, which nothing reinstalls: §6.6 again.

**A rebuilt host's first converge is a workstation converge again**, for the same reason a new host's is — it is on no tailnet and carries no converge key until §6.3 and §6.6 have run. That is the one time `ansible-playbook` against an existing host is correct rather than a sign that stage 9 was left unfinished.

The same stages, in this order, skipping what still exists: 4.2 (with `server_enabled` toggled off then on, or a replace with the `destroy-override` label), 4.3, 4.4 if the address changed, **delete the old machine from the tailnet** (see below), 5.3's auth key if the old one expired, 6.3, 6.6's converge key, 6.4 (new tailnet IP → that stack's `PLATFORM_DEPLOY_HOST` and every application's `DEPLOY_HOST`), 7.4 by running **Platform Deploy** from Actions **with this stack's name as the `stack` input** — re-running the last run would redeploy every stack and wake another stack's approval gate for a host that did not change — then 7.5 against this host, then each application's deploy from its own Actions. There is no database restore step: no platform-stack store needs one, because each is either recreated by a redeploy or its loss is accepted — see the database section of `docs/onboard-an-application.md` and *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`). There **is** a re-provisioning step: every application with a database in the shared instance loses it with the instance, which its classification tolerates, but cannot start until it exists again — so before each such application's deploy, run the provisioning recipe in `docs/onboard-an-application.md` for this host with `rotate=yes`, which recreates the role and database and replaces the password in that target's Environment. Two consequences to say out loud, because a rebuild is when they arrive: Prometheus's metrics history and Grafana's UI-created state do not come back, and on the production host `commerce-ops`'s own PostgreSQL — the one divergence that requirement names — is lost outright, since nothing backs it up. `docs/backlog.md` entry 19 is what closes that, and entry 20 is the plan to turn this paragraph into a rehearsed runbook with timings.

## Appendix C. What to change for a company deployment

Recorded in detail in `docs/backlog.md`. Two of them — logical off-host database backups, and a decided database model — were resolved together by `scope-the-shared-database-to-non-durable-data`, which found that the shared instance holds no application data and that what this host needed was a stated boundary rather than a backup pipeline; the database section of `docs/onboard-an-application.md` is that boundary. The one still to do before real data arrives is container resource limits, `docs/backlog.md` entry 6 — log rotation and swap were the other two and were delivered together by `bound-host-log-growth-and-add-swap`. The ones a company needs that this repository does not: a private repository in the company organisation, and an approver who is not the author. DNS as code was the third until the zone was read: it is served by a registrar carrying live MX and SPF, so managing it in Terraform means an NS migration that moves mail, and it is declined rather than queued — §4.4 records the zone, the reasoning and what would reopen it.

**Two stacks are no longer among them.** This document now stands both up, in stages 1 to 4, because deciding the count late is what costs — the Hetzner project layout, the workspace names and the read-only secret names are all stage 1 to 3 decisions, and revisiting them against a running production system is the expensive order. Both hosts are configured too: stage 6 runs once per stack. Both are publicly reachable as well: staging runs the platform stack, opens 80 and 443 as production does, and has hostnames of its own under a wildcard (§4.4).

**Renaming a server moves the slug its pings address, and there are two ways to meet that — one of which loses everything the check knows.** The slug is templated from `inventory_hostname`, so on the day a server is renamed its reporter starts addressing a new one.

**Rename the check at the observer instead of letting a new one be created.** A rename carries the slug, and with it the period and grace already set, the ping history, and whatever notification integrations the check has. Letting the reporter's `create=1` bring a new check into existence loses all four: the new one carries the **observer's default** period, which calls a healthy weekly job overdue within a day, and the old one is then pinged by nothing and goes overdue forever — two red checks where there was one green one.

`rename-the-stacks-and-their-resources` renamed both servers and did exactly this. Its task 9.1 records the reasoning and notes the approach was better than the one that change had planned; its 10.7, which existed to delete the old checks afterwards, records that **nothing needed deleting**, because the old checks had become the new ones. No orphan was created and none exists.

So the instruction is: rename, do not re-create. **If a rename is ever done the other way**, the old check is an orphan and must be deleted by hand — a permanently red check nobody can act on is worse than no check, being what teaches an operator to stop reading the list, which is the failure this whole mechanism exists to prevent.

**Heartbeat check names must stay distinct, and only half of that is automatic.** The workflow slugs carry this repository's name (`infrastructure-`), so a second repository's workflows get checks of their own. The host slug does **not**: it is `<inventory_hostname>-prune-host-images` with no repository or project segment, so two hosts both named `main-production` would share one check in the same heartbeat project, and the live one's weekly success would keep it green while the other's timer was dead. That is the masking failure this mechanism exists to end. This stopped being hypothetical when `add-a-staging-environment` added a second stack, and the naming scheme's answer is that a server carries its **stack's** name — which makes the two distinct by construction rather than by a choice someone has to remember. Give a company host an `inventory_hostname` of its own, or a heartbeat project of its own. The free tier's 20 checks is the ceiling either way; count them before adding a third host.
