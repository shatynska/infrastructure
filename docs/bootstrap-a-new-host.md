# Bootstrapping a new host from this repository

This is the end-to-end procedure for standing up **two** servers — a reviewed production environment and an ungated staging one — and the repository and accounts around them, using this repository as the template. It is written for a developer who has shipped application code but has not run infrastructure before, so it names every account, every secret, and where each secret's value comes from, in the order you will need them. It is also the document to start from when a host has to be rebuilt (Appendix B, which covers the configured one) or when someone else has to take the system over.

What you will have at the end:

- **Two** Hetzner Cloud servers, each in its own Hetzner project, each with a firewall and a data volume, created and changed only through reviewed pull requests. Production's apply waits for a human; staging's does not.
- **The production server** configured (Docker, host firewall, a private network, restricted deploy accounts) by Ansible.
- A shared platform stack **on the production server**: Traefik with automatic TLS, PostgreSQL, Prometheus, Alertmanager, Grafana, alerts to Slack, and an external heartbeat.
- A path for any application repository to deploy itself **to the production host** from its own GitHub Actions workflow.
- **A staging server, configured but running nothing** — stage 6 converges it alongside production: Docker, the host firewall, the tailnet, the operator and deploy accounts, the mounted data volume, the weekly image prune. What it does not have is an application stack, a hostname or an open web port, because `platform-deploy.yml` still deploys to one environment. "From here on, two hosts" says which and what closes it. That is the honest end state today; it is not an oversight in this procedure.

**Two servers is a standing cost**, not a one-off configuration: two instances and two volumes billed monthly, two hosts to patch and rebuild, two token pairs to rotate. Staging is roughly half production's bill. Decide you want that before stage 1, because the decisions that follow are shaped by it and are awkward to unpick afterwards. If you want one environment, this document still works: delete the second directory under `terraform/environments/`, skip its secrets, and read every "two" below as "one".

**How to read this.** Stages are in dependency order; do not skip ahead. Each stage ends with a **Secrets created in this stage** table and a **Check** list. `<angle brackets>` are placeholders you replace. "Operator" means the person doing this. Commands are run from the repository root unless a `cd` is shown. The reasoning behind most decisions is in `openspec/specs/` and in the archived changes under `openspec/changes/archive/`; this document only says what to do.

**Time.** Roughly one working day for stages 0 to 7 if nothing goes wrong, mostly waiting on approvals and DNS. The second environment adds perhaps an hour of console work in stages 1 to 3 and nothing after that, since stages 5 to 9 configure one host. Stage 8 is repeated per application.

## Stage 0. Accounts, tools and keys

Nothing here touches a server. It is the shopping list.

### 0.1 Accounts you will create or need access to

| Service | Used for | Who owns the account |
|---|---|---|
| GitHub | The repository, CI, the approval gate, the container registry (GHCR) | The company organisation, not a personal account |
| Hetzner Cloud | Both servers, their firewalls, volumes and backups — **one project per environment**, created in stage 1 | The company, with billing set up |
| HCP Terraform (app.terraform.io) | Storing Terraform state and locking it — one workspace per environment | The company; the free tier is enough |
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
| `direnv` (optional but recommended) | Loads each environment's read-only Hetzner token only inside that environment's directory — one token reaches one project, so the scoping matters |
| Tailscale client | Reaching the server over the private network |

Follow `README.md`, "Local setup", steps 1 to 5. Step 5 installs Ansible into a virtual environment and the Galaxy content into `ansible/roles/`; the `-p ansible/roles` flag there is required, not optional.

### 0.3 SSH keys you will generate

Generate each with `ssh-keygen -t ed25519`. Never reuse one key for two **purposes**; each has a different holder and a different blast radius.

**One purpose may span both environments, and the operator key does.** Both environment directories in this repository carry the same `ssh_public_key`, and that is deliberate rather than an oversight: the key authorises `root` on hosts this repository can recreate in their entirety, both are reached by the same operator, and a second private half would be one more thing to hold, rotate and lose for no gain. What must never be shared is a key across *purposes* — the operator key, the inspection key, the platform deploy key and each application's deploy key stay four distinct keys, because those have four different holders. If you decide otherwise for your company, generate a second operator key and put its public half in the second environment's `terraform.tfvars`; nothing else changes.

| Key | Command | Passphrase | Private half lives in |
|---|---|---|---|
| Operator key | `ssh-keygen -t ed25519 -f ~/.ssh/<company>-root -C "<you>@<company> root"` | Yes | Your workstation only. This is `root` on **both** servers. |
| Operator inspection key | `ssh-keygen -t ed25519 -f ~/.ssh/<company>-ops -C "ops-<you>"` | Yes | Your workstation. Unprivileged login, used daily instead of root. Configured on the production host only, in stage 6. |
| Platform deploy key | `ssh-keygen -t ed25519 -f platform_deploy_key -N "" -C "deploy@platform"` | **No** (CI cannot type one) | GitHub secret only; delete the local file after storing it |
| One deploy key per application | `ssh-keygen -t ed25519 -f <app>_deploy_key -N "" -C "<app>-deploy"` | **No** | That application's GitHub secret only |

Keep the `.pub` halves; they are committed to the repository in later stages and are not secret.

## Stage 1. Hetzner Cloud

### 1.1 Register and create one project per environment

1. Register at console.hetzner.cloud, complete identity verification, add a payment method.
2. Create **two** projects: `<company>-prod` and `<company>-staging`.
3. Do **not** create a server, firewall or volume in either console. Terraform creates them in stage 4, and anything created by hand is drift the nightly check will report.

**One project per environment is a decision, and this is where it is made.** A Hetzner API token is scoped to exactly one project, so the project boundary is what the whole credential split rests on. The pipeline supports either answer; two projects is the recommendation, for two reasons that are hard to see in advance:

- **One project means one Read & Write token covering both environments**, so staging's apply must sit behind an approver too — otherwise any push to `main` reaches a production-capable credential. An approved staging deploy is as slow as production and stops being used, which is most of what staging is for.
- **Hetzner volume names are unique per project, not globally.** In one project the second environment's volume cannot also be called `main-data`, so it gets a different name, a different mount path, and `platform/docker-compose.yml`'s hardcoded `/mnt/main-data/prometheus` and `/mnt/main-data/grafana` must be parameterised — or Prometheus and Grafana come up writing to a path that does not exist, silently.

Two projects costs a second token pair to rotate. One project costs the two items above, every time you deploy.

### 1.2 Create four API tokens, two per project

In **each** project: Security → API tokens → Generate API token. Check the project switcher before generating — a token made in the wrong project is the failure that looks like everything else.

| Token | Permission | Where it goes | Never goes |
|---|---|---|---|
| Production Read Only | Read | Your workstation, **twice**: the repo-root `.envrc` as `HCLOUD_TOKEN` for Terraform (stage 4.1), and `ansible/.envrc` as `HCLOUD_TOKEN_PROD` for Ansible (stage 6.0). Plus the repository secret `HCLOUD_TOKEN` (stage 3) | Nowhere else |
| Production Read & Write | Read & Write | The `production` Environment secret `HCLOUD_TOKEN` (stage 3) | Any local file, shell, or note. If you can run `terraform apply` from your laptop, this token is in the wrong place. |
| Staging Read Only | Read | Your workstation, **twice**: `terraform/environments/staging/.envrc` as `HCLOUD_TOKEN` for Terraform (stage 4.1), and `ansible/.envrc` as `HCLOUD_TOKEN_STAGING` for Ansible (stage 6.0). Plus the repository secret `HCLOUD_TOKEN_STAGING` (stage 3) | Nowhere else |
| Staging Read & Write | Read & Write | The `staging` Environment secret `HCLOUD_TOKEN` (stage 3) | The same places. An ungated apply does not make its token less confined. |

Each token is shown once. Put all four in the password manager immediately, each labelled with its project **and** its permission level.

**Each read-only token is used by two tools under two different variable names**, and the duplication is deliberate. Terraform reads `HCLOUD_TOKEN`, whose value direnv scopes to the environment *directory* you are standing in. Ansible is always run from `ansible/`, so it cannot use a variable whose meaning depends on where you stand: each of its inventory sources names its own variable instead, and which project a run reaches is decided by the `-i` it was given rather than by shell state.

The two read-only secrets have different **names** at the repository level, and that is required rather than stylistic: a repository secret holds one value, so two environments naming the same one would plan under a single credential. Discovery fails the pipeline, naming both offenders, if two environments ever declare the same read-only secret or the same GitHub Environment.

### 1.3 Decide the sizing and record it

You will write these into each environment's `terraform.tfvars` in stage 3. Decide them now, for both.

| Setting | Guidance | Production | Staging |
|---|---|---|---|
| `location` | Pick one datacenter and stay in it; the volume cannot move | `hel1` (Helsinki); `fsn1` and `nbg1` are the German alternatives | The same, unless you want to rehearse a region move |
| `server_type` | `cx33` is 4 vCPU / 8 GB; for several services start at `cx43` (8 vCPU / 16 GB) or a `cpx` type. You can resize later, but only upward without a rebuild. **Read the current type names off the console** — the generation changes, and a name that no longer exists fails at apply | `cx33` | `cx23`, roughly half the bill. Deliberately tight: a staging host that cannot fit the stack is what forces container resource limits to be set, rather than deferred until production needs them |
| `image` | A current Ubuntu LTS | `ubuntu-26.04` | The same. An environment that rehearses production on a different image rehearses something else |
| `volume_size` | GB for Prometheus and Grafana state (and future logs); resizable upward only | `10` | `10` |
| `volume_name` | Keep it identical across environments. Names are unique per project, so a project each frees the name, and the same name means the same on-host mount path — which is what lets `platform/docker-compose.yml` stay unparameterised | `main-data` | `main-data` |
| `name` | The server's own name, which becomes its `inventory_hostname`. **Must differ between environments** — two hosts sharing one name merge in any inventory that reads both projects, and share a single `<inventory_hostname>-prune-host-images` heartbeat check, where the live host's weekly success masks the other's dead timer | `main-server` | `staging-server` |
| `ssh_allowed_cidrs` | The public IP ranges allowed to reach SSH. Must not be `0.0.0.0/0`. If everyone will use Tailscale, see `docs/change-queue.md` entry 25 for closing public SSH entirely | one ISP `/24` | The same |
| `web_allowed_cidrs` | `["0.0.0.0/0"]` for a public web host | `["0.0.0.0/0"]` | `[]` — no web rule at all, until something is deployed there. See stage 5 |

**Secrets created in this stage:** four Hetzner tokens, held in the password manager until stage 3.

**Check:** both projects exist and are empty; all four tokens are in the password manager, each labelled with its project and its permission level.

## Stage 2. HCP Terraform

Terraform needs somewhere to keep its state file (the record of what it created) that both your workstation and CI can reach, with a lock so two runs cannot overlap. HCP Terraform provides exactly that, and this setup uses nothing else from it.

1. Register at app.terraform.io and create an organisation named `<company>`.
2. Create **two** workspaces, both **CLI-driven workflow**, no VCS connection, named for their environments: `infrastructure-prod` and `infrastructure-staging`. The names are read from each environment's `versions.tf` in stage 3, so a typo there creates a second, empty workspace under whatever you typed. **No two environments may share a workspace** — a workspace holds one state, so sharing one would have each apply read the other's resources as its own and plan them for destruction.
3. In **each** workspace's Settings → General, set **Execution Mode** to **Local**, and save. This is essential and it is per workspace: the default is Remote, so a workspace created and not adjusted is misconfigured even when its sibling is correct. Remote execution runs plans on HCP's machines, and `terraform plan -out=tfplan` then yields no plan file the apply job can apply — which breaks the saved-plan approval flow with no error naming execution mode.
4. Create an API token, and it **must be a USER token**: your avatar (top right) → **Account settings → Tokens → Create an API token**. One token; this tier has no way to split it by privilege, and the Hetzner token split in stage 1 is the real security boundary.

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

   The ones that matter: the `organization` in **both** `terraform/environments/prod/versions.tf` **and** `terraform/environments/staging/versions.tf` (your HCP organisation from stage 2), `ghcr_pull_username` in **each** `ansible/inventory/group_vars/<environment>.yml` (stage 6), the `Documentation=` URL in `ansible/roles/image_prune/tasks/main.yml`, and prose in `README.md`.

   Both `versions.tf` files carry it, and changing only production's is the easy miss: staging would then initialise against someone else's HCP organisation, and the error names a workspace rather than an organisation.

4. Edit **both** `terraform.tfvars` files — `terraform/environments/prod/` and `terraform/environments/staging/` — with the stage 1.3 decisions for that environment, putting the **public** half of your operator key from stage 0 into each `ssh_public_key`. Everything in these files is non-secret and committed. Check `name` differs between them and `volume_name` does not; stage 1.3 says why each matters.

5. Read `terraform/environments/staging/pipeline.yml` and accept or change its three values: `github_environment: staging`, `read_only_secret: HCLOUD_TOKEN_STAGING`, and `destroy_policy_gate: false`. These are what stage 3.2 and 3.3 must match — the Environment you create and the repository secret you set take their names from this file, not from any workflow. `terraform/environments/prod/pipeline.yml` is its counterpart and needs no change unless you rename things.

6. Delete the `moved` block at the bottom of `terraform/environments/prod/ssh_key.tf`. It records a one-time relocation in the original repository and is meaningless in a fresh state. Staging's `ssh_key.tf` has no such block and needs no edit; its own comment says why.

7. Run `pre-commit install --hook-type pre-commit --hook-type commit-msg` so your commits are checked the way CI checks them.

**Do not push yet, and the reason is now sharper than it used to be.** Because you initialised the repository with a commit in step 1, your push in stage 4.2 *will* be compared against it, *will* plan, and will therefore need every secret from 3.3 already in place. The two environments' plan jobs run under two different repository secrets; a missing one authenticates as nobody rather than erroring cleanly.

### 3.2 Repository settings

All of these are in Settings on github.com, or via `gh`.

1. **Environments, two of them.** Settings → Environments → New environment, twice:

   - **`production`** — add the protection rule **Required reviewers** and name at least one person. For a company, this person should not be the only person who opens pull requests; the Environment approval is the human gate every production change passes through.
   - **`staging`** — add **no** protection rules at all. Its apply runs on merge, without a human.

   The names must match what each environment's `pipeline.yml` declares (step 5 of 3.1), and they must differ from each other: two environments naming one GitHub Environment would share its write token and its protection rules, so the ungated one would hold the reviewed one's credential. Discovery fails the pipeline, naming both, if they ever collide.

   **What makes an ungated apply safe is the project boundary from stage 1, and nothing else.** Staging's write token can destroy staging's Hetzner project and cannot touch production's. Whether an Environment requires a reviewer is a repository setting that no file in this repository can verify — which cuts both ways: nothing will tell you if `production` loses its reviewer either.
2. **Label.** Issues → Labels → New label: `destroy-override`. A merged pull request must carry this label for the apply workflow to accept a plan that deletes or replaces a resource. Without it, such plans fail on purpose.
3. **Workflow token.** Settings → Actions → General → Workflow permissions: **Read repository contents and packages permissions**. Each workflow declares the little it needs on top.
4. **Merge methods.** Leave merge commits enabled. The destroy gate reads the pull request number from the merge commit message; squash and rebase merges fall back to a slower API lookup.

### 3.3 Secrets

Repository secrets: Settings → Secrets and variables → Actions → Repository secrets. Environment secrets: Settings → Environments → *that environment* → Environment secrets. Or with `gh`, which prompts for each value and reads it when you press Enter:

```sh
gh secret set HCLOUD_TOKEN                    # production Read Only
gh secret set HCLOUD_TOKEN_STAGING            # staging Read Only
gh secret set TF_API_TOKEN                    # the HCP user token
gh secret set HCLOUD_TOKEN --env production   # production Read & Write
gh secret set TF_API_TOKEN --env production   # the same HCP user token
gh secret set HCLOUD_TOKEN --env staging      # staging Read & Write
gh secret set TF_API_TOKEN --env staging      # the same HCP user token
```

Do not pass `--body '<token>'`: that records the secret in your shell history, where it then lives until the file rotates out.

**Secrets created in this stage**

| Name | Scope | Value from | Read by |
|---|---|---|---|
| `HCLOUD_TOKEN` | Repository | Stage 1, production Read Only | Production's PR plans, drift detection and apply-workflow plan job. **Not Ansible** — no workflow runs Ansible, and the inventory reads `HCLOUD_TOKEN_PROD` from a local file (stage 6.0) |
| `HCLOUD_TOKEN_STAGING` | Repository | Stage 1, staging Read Only | Staging's PR plans, drift detection and apply-workflow plan job |
| `HCLOUD_TOKEN` | `production` Environment | Stage 1, production Read & Write | Production's apply job only, after approval. GitHub resolves an Environment secret ahead of a repository secret of the same name, which is the whole mechanism. |
| `HCLOUD_TOKEN` | `staging` Environment | Stage 1, staging Read & Write | Staging's apply job, immediately on merge |
| `TF_API_TOKEN` | Repository | Stage 2 | Every Terraform job |
| `TF_API_TOKEN` | `production` Environment | Stage 2, same value | Production's apply job |
| `TF_API_TOKEN` | `staging` Environment | Stage 2, same value | Staging's apply job |

**`.github/dependabot.yml` already lists both environment directories**, and it must keep listing exactly the ones that exist. Dependabot's terraform ecosystem has no discovery mechanism, so a directory the list omits is not partially covered — it is uncovered, and its provider pins rot with no signal. The CI suite compares that list against the lockfiles in the tree and fails the build if a lockfile-bearing directory is missing. If you drop the second environment, drop its entry with it; if you add a third, add one.

**The two read-only secrets have different names on purpose.** A repository secret holds one value, and plan jobs declare no `environment:` — they can only reach repository secrets — so each environment needs a name of its own. Which name is read comes from that environment's own `pipeline.yml`, not from any workflow.

**Where those names come from.** No environment name and no secret name is written in any workflow. Each is declared by that environment's own `pipeline.yml`, which the pipeline's discovery step reads. If you rename one, rename it there in the same change, or the plan job resolves an empty secret and the apply job attaches to an Environment that does not exist.

**Each Environment must define its own `HCLOUD_TOKEN`.** GitHub resolves an *absent* Environment secret to the repository secret of the same name rather than failing — so an Environment that omits it applies with whatever the repository holds under that name, which here is **production's read-only token**, and at more than one environment could be another environment's write token. The apply job digests the value and refuses to apply when it matches the repository-scoped one, but the fix is here.

**Check:** seven secrets set — three at repository scope, two on each Environment; `production` shows one required reviewer and `staging` shows none; the label exists; the repository is private and holds exactly one commit, the license.

## Stage 4. First Terraform apply: both servers exist

### 4.1 Prove both configurations locally

Each environment needs its own read-only token in scope, because one token reaches one project. Put production's in the repo-root `.envrc` (copy `.envrc.example`), and staging's in an `.envrc` **inside** `terraform/environments/staging/` — directory-scoped, so planning staging never leaves staging's token in the shell that plans production. Both paths are gitignored.

Run `direnv allow` in each directory that has one; direnv loads the nearest `.envrc` and does not merge the parent's, which is what keeps the two tokens apart. **Without direnv**, `source` the file for the environment you are about to work on, in a shell you do not then reuse for the other — the export outlives the directory, and carrying staging's token into `prod/` produces the misleading plan described below rather than an error.

This paragraph is about **Terraform's** token only. Ansible has a third `.envrc`, in `ansible/`, holding both read-only tokens under names of their own; stage 6.0 sets it up, and it is immune to the mistake above because neither name is `HCLOUD_TOKEN`.

Then, for each environment in turn:

```sh
cd terraform/environments/prod        # then repeat in staging/
terraform init
terraform plan
```

`init` connects to that environment's HCP workspace from stage 2 — check the workspace name in the output matches the directory you are in. `plan` should propose creating a firewall, an SSH key, a server and a volume, and nothing else, in each environment.

Do not run `apply`: the read-only token would refuse it, and that refusal is the boundary this whole setup relies on. **With the wrong environment's token in scope the plan is misleading rather than refused** — an empty workspace and a foreign project produce the same "four resources to create" you expect, so check the workspace name rather than the resource count.

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
- **Platform Deploy** — triggered because this push adds the whole `platform/` tree, which is its path filter. Its `deploy` job attaches to the `production` Environment, so **it raises a second approval request that looks exactly like the one below**. Do not approve it. There is nothing to deploy yet: the host is not converged until stage 6, and every secret that job needs is created in stages 5 to 7. Cancel the run, or leave it pending and let it expire. Stage 7.4 is where the platform stack is deployed for the first time, deliberately and with its prerequisites in place.

The run covers **both** environments, because this push changes files under both environment directories:

- **staging's apply runs immediately**, with no approval, and creates its four resources;
- **production's apply waits** on the `production` Environment. Read its plan job's summary. If it is the four resources from 4.1, approve; the `apply` job creates them.

Neither environment's failure withholds the other's apply — that separation is deliberate, so a broken staging can never be the reason a correct production change cannot ship. This is the pipeline's specified behaviour; two applies in one run, one of them pausing, is a path this repository has specified and not yet observed, so read the run rather than assuming it.

**If the run fails at "List the paths this merge changes"**, with a message about a push carrying no usable comparison base, the repository was created empty and this is its first push. That is the case step 1 of 3.1 avoids by initialising with a license. Recover by making one more commit and pushing again — and that commit must touch a file **under each** `terraform/environments/<name>/`, because Terraform Apply is filtered to `terraform/**` at the workflow level and then narrowed to the environments whose own directories changed. A recovery commit touching neither starts no run at all, silently; one touching a single environment leaves the other server uncreated. Do not force-push: it produces the same failure with a different message.

### 4.3 Get the addresses and log in

```sh
cd terraform/environments/prod && terraform output        # then repeat in staging/
```

Each environment's `server_ipv4_address` is that server's public address; you now have two. Record both.

Log in once as root to **the production host** with the operator key, which also records its fingerprint in your `known_hosts` — Ansible requires that in stage 6:

```sh
ssh -i ~/.ssh/<company>-root root@<prod ipv4>
```

**Log into the staging host too, the same way** — `ssh -i ~/.ssh/<company>-root root@<staging ipv4>`. This is not optional and it is not just a reachability check: it records staging's host key in your `known_hosts`, and `ansible.cfg` sets `host_key_checking = True`, so without it stage 6's first converge of staging stops at connection time with `Host key verification failed` before a single role runs.

### 4.4 DNS

In the DNS provider, create an `A` record per hostname an application will serve, **pointing at the production address**. Nothing needs them until an application is routed in stage 8, but they take time to propagate, so create them now.

**Do not point a hostname at the staging server.** It ships with `web_allowed_cidrs = []`, so its cloud firewall opens neither 80 nor 443 and nothing answers there; a record aimed at it produces a hostname that times out and a certificate that never issues, with no error naming the cause. Staging gets its own hostnames from the change that deploys something to it, which also opens those ports deliberately.

There is no Terraform for DNS, deliberately — see "Managing DNS in Terraform" in `docs/deferred-work.md`, which names the provider (ukraine.com.ua, nameservers `inhostedns.*`) and lists the zone's records as read on 2026-09-08, including the MX and SPF that make an automated migration riskier than it looks.

**Secrets created in this stage:** none. The two `.envrc` files hold the two read-only tokens and are gitignored.

**Check:** `terraform plan` says "No changes" locally in **both** environment directories; the nightly Drift Detection workflow, run once by hand from Actions → Drift Detection → Run workflow, reports no drift for **both** environments in one run — its own `report` job will still fail at this stage, because `HEARTBEAT_PING_KEY` is not created until stage 7.3, so read the two `drift` jobs rather than the run's overall result; `ssh root@<prod ipv4>` works with the operator key and nothing else; both servers appear in their own Hetzner projects and neither project holds anything you created by hand.

## From here on, two hosts — but only one of them runs anything

You now have two servers, and **stage 6 configures both**. It is written once and run once per environment: the inventory has a source per environment, and the host-baseline play takes the environment it targets as an input.

**Stages 7 to 9 are still production's alone**, and one mechanism is why:

- **`.github/workflows/platform-deploy.yml` declares `environment: production`** and deploys to a single `PLATFORM_DEPLOY_HOST`. The platform stack has no per-environment path at all. That is `docs/change-queue.md`'s platform-per-environment entry.

So after stage 6 the staging server is a **configured** host — Docker, UFW and fail2ban, on the tailnet, data volume mounted, operator account, deploy account — with no application stack on it. Its cloud firewall still opens no web port (`web_allowed_cidrs = []`), and it has no hostname and no certificate; those come with the stack, in the queue entry for staging's web exposure.

Two things about staging in stage 6 that differ from production, both deliberate:

- **Its own Vault password**, under the vault id `staging`. Reusing production's would mean anyone who can converge staging holds the password protecting production's secrets.
- **Its own deploy keypair** for `platform`. One leaked private half must not deploy to both environments.

**Its weekly image prune will report failure until the stack arrives**, and that is expected rather than a fault to chase: with nothing deployed, no application contributes an image and no container holds one, so the keep set is empty and the unit abandons by its own documented contract. See stage 6.5.

**If you decide you do not want it yet**, delete `terraform/environments/staging/` and `ansible/inventory/staging.hcloud.yml` and `ansible/inventory/group_vars/staging.yml`, drop `HCLOUD_TOKEN_STAGING` from `ansible/.envrc`, remove its `HCLOUD_TOKEN_STAGING` repository secret and its `staging` Environment (with the two secrets on it), drop its `.github/dependabot.yml` entry, and delete its Hetzner project and HCP workspace. Then skip staging wherever stage 6 says "once per environment". Nothing else in this document depends on it. Adding it back later is stages 1 to 4 again, against a running production system — which is the order this document is arranged to spare you.

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

**Run it once per environment**, production first. Everything below takes the environment as an argument; `<environment>` means `prod` or `staging` throughout, and the two runs share no file, no token and no Vault password. Do production first because it is the one you will check most carefully, and staging second because by then you are repeating a procedure you have just seen work.

### 6.0 The two tokens Ansible reads

Ansible does not use the `HCLOUD_TOKEN` you set up for Terraform in stage 4.1. That variable is scoped per environment *directory* by direnv, so its value depends on where you are standing — fine for Terraform, which is always run from inside an environment directory, and wrong for Ansible, which is always run from `ansible/`.

Instead, each environment has an inventory source of its own that names a credential of its own. Copy the example and fill in both read-only tokens from stage 1.2:

```sh
cd ansible
cp .envrc.example .envrc
direnv allow
```

**Without direnv**, `source .envrc` from `ansible/` once per shell — they are plain `export` lines, exactly as at §4.1. Unlike there, that is a perfectly good way to run this one and not a fallback with a catch: §4.1's warning exists because the root and staging `.envrc` files both export `HCLOUD_TOKEN` with different values, so an export outliving its directory points Terraform at the wrong project. These two variables collide with nothing and mean the same thing wherever you stand, which is why each inventory source names its own rather than sharing Terraform's.

Both are **Read Only** tokens. A wrong or missing one fails the run rather than producing an environment with no host in it, so a typo here cannot masquerade as a destroyed server.

### 6.1 Fill in the inventory variables

Edit `ansible/inventory/group_vars/<environment>.yml` — production's and staging's are separate files with separate values, and staging's is written from scratch rather than copied from production's. Every value except the last two is non-secret and committed; those two are Vault-encrypted in place.

| Variable | Set to |
|---|---|
| `hardening_ssh_allowed_cidrs` | Exactly the `ssh_allowed_cidrs` list from **that environment's** `terraform.tfvars`. They are kept in sync by hand; a mismatch makes the host firewall block what the cloud firewall allows. |
| `hardening_web_allowed_cidrs` | Exactly `web_allowed_cidrs` from that environment's `terraform.tfvars`. Production's is `["0.0.0.0/0"]`; **staging's is `[]`**, and stays `[]` until the change that puts something behind those ports opens them in both files together. |
| `deploy_apps` | One entry: `name: platform`, `public_key:` the `.pub` of that environment's platform deploy key. **Each environment gets its own keypair** — one leaked private half must not deploy to both. Applications are added here in stage 8. |
| `ops_user_accounts` | One entry: `name: ops-<you>`, `public_key:` the `.pub` of your operator inspection key |
| `platform_data_volume_subdirs` | Leave as is |
| `ghcr_pull_username` | The GitHub username whose token is below. For an organisation, a dedicated machine user with read access to the application repositories is cleaner than a person's account. |
| `ghcr_pull_token` | Vault-encrypted, see below |
| `image_prune_heartbeat_ping_key` | Vault-encrypted, see below. **The play refuses to run without it** |

**The GHCR token.** The host must log in to GitHub's container registry to pull private application images. On github.com as the user above: Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate, scope **`read:packages`** only, expiry of your choice (note it in the password manager: when it expires, deploys start failing at `docker compose pull`).

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

Choose a Vault password **for this environment** — production and staging get different ones, so that whoever can converge staging does not thereby hold the password protecting production's secrets — store it in the password manager, then encrypt the token in place:

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

Create it now, at the heartbeat service from stage 0.1: **Settings → Ping key → create**. One key addresses every periodic job's check, and the same value becomes the `HEARTBEAT_PING_KEY` repository secret in stage 7.3. Put it in the password manager, then encrypt it the same way:

```sh
cd ansible
ansible-vault encrypt_string --vault-id <environment>@prompt '<ping key>' --name image_prune_heartbeat_ping_key
```

The key must be a bare token of letters, digits, `_` and `-`; the role refuses anything else by name, because the value is rendered into a shell file its reporting script sources and a quote in it would make that script fail silently.

### 6.2 Check the inventory resolves

The inventory is dynamic: it asks the Hetzner API which servers exist and groups them by their `environment` label. It needs the read-only token from `.envrc`.

```sh
cd ansible
ansible-inventory -i inventory/<environment>.hcloud.yml --graph
```

You should see that environment's server under `@<environment>`. If the command fails naming the source it could not parse, that environment's token in `ansible/.envrc` is missing or wrong — the run fails rather than showing you an empty inventory, which is the point.

### 6.3 Run the playbook

```sh
cd ansible
ansible-playbook playbooks/host-baseline.yml \
  -i inventory/<environment>.hcloud.yml \
  -e target_environment=<environment> \
  --vault-id <environment>@prompt \
  --private-key ~/.ssh/<company>-root \
  -e tailscale_auth_key=<tskey-auth-... from stage 5>
```

**Do not add `--limit`.** The environment already selects the host set, there is nothing to narrow, and a limit filters the guard play's `localhost` out — so a run that reaches no host would exit 0 again, which is the failure the guard exists to end. `--tags` is safe — the guard is tagged `always` — with the single exception of `--skip-tags always`, which names that tag and switches the guard off.

Two prompts: the Vault password, and (if the key has one) the operator key's passphrase. A first run takes several minutes; Docker's installation is the slow part. A second run immediately afterwards should report `changed=0`; if it does not, something is not idempotent and worth understanding before moving on.

Do not rely on `--check` for the first run: apt-based tasks report changes they did not make and later tasks then fail against a stale package cache.

`--check --diff` is useful on every run after the first, with one thing to know before you read its output: **a healthy host reports `changed=2`, not zero.** Both are in the `tailscale` role — *Add the Tailscale apt signing key* and *Add the Tailscale apt repository* — and both are `get_url` tasks with no `checksum:`. Confirming such a file already matches would mean downloading it, which check mode will not do, so it reports "would change" every time and always will. Two is the baseline; compare against two, and read anything else.

**And two is a baseline for what check mode can see, which is less than the host.** `command` tasks skip under `--check` — `ops_user`'s three and `swap`'s four — and `geerlingguy.docker` carries `ignore_errors: "{{ ansible_check_mode }}"` on five, so failures there are swallowed. A clean check means no *file or package* drift was found; it is not a statement that the host is as this repository describes it. `docs/change-queue.md` entry 23, which would turn this flag into the host layer's drift detector, owns removing those two — and when it does, this paragraph changes with it.

### 6.3a When the run fails partway

It can, and the first converge of a host is where it is likeliest. What a failure leaves is a **partially-converged host**: every role ahead of the failing one has applied in full, the failing role has applied up to the task that failed, and nothing after it has run.

That middle clause matters. In the case below the failing task is the *last* one in its role, so Tailscale is installed and `tailscaled` is running even though the host never joined the tailnet.

None of that is a reason to rebuild — **correct the input and run the same command again.** Every role here is idempotent, so the second run reports `ok` for the work already done and carries on from where it stopped.

**That assumes you can still reach the host.** `hardening` runs before `tailscale` and ends by enabling UFW, so at the moment of a tailscale failure the host answers on whatever `hardening_ssh_allowed_cidrs` allows — and the tailnet, which is the other way in, is precisely what has not come up. Both environments here set an operator ISP range, so public SSH still gets you in. On a host configured for tailnet-only SSH, which the role permits and which is stricter than what this repository runs, a failure here would leave no way in at all, and rebuilding would be the recovery.

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

1. Tailscale admin → Machines: the server is listed. Note its tailnet IPv4 (`100.x.y.z`). Disable key expiry for it (stage 5.3).
2. Log in the way you will from now on, over the tailnet, unprivileged:

   ```sh
   ssh -i ~/.ssh/<company>-ops ops-<you>@100.x.y.z
   docker ps        # works: the account is in the docker group
   sudo -n true     # refused: the account has no sudo, by design
   ```

   That refusal is real, and it means anything needing root — starting a unit, reading a unit's journal, reading a `0600` file — cannot go through this account. Reach for Ansible instead, which authenticates as `root` with the operator key you already hold:

   ```sh
   cd ansible
   ansible <environment> -i inventory/<environment>.hcloud.yml \
     --private-key ~/.ssh/<company>-root \
     -m ansible.builtin.systemd_service \
     -a "name=<unit> state=started" --vault-id <environment>@prompt
   ansible <environment> -i inventory/<environment>.hcloud.yml \
     --private-key ~/.ssh/<company>-root \
     -m ansible.builtin.command \
     -a "journalctl -u <unit> -n 20 --no-pager" --vault-id <environment>@prompt
   ```

   Plenty is still readable unprivileged: `systemctl is-active`, `systemctl show --property=…`, `systemctl list-timers`, `stat`, and any world-readable file.

3. Commit and push `group_vars/<environment>.yml` through a pull request. The Molecule suite runs on it; that is the `ansible-verify` check.

**Secrets created in this stage**

| Name | Scope | Value from | Read by |
|---|---|---|---|
| Vault password, one per environment | Password manager only | You chose it | Anyone running that environment's playbook |
| `ghcr_pull_token` | Encrypted inside `group_vars/<environment>.yml`, per environment | GitHub classic PAT, `read:packages` | The playbook, to log the host's Docker into GHCR |
| `image_prune_heartbeat_ping_key` | Encrypted inside `group_vars/<environment>.yml`, per environment | The heartbeat service's project ping key | The prune unit's reporting script, on every activation. The same value becomes the `HEARTBEAT_PING_KEY` repository secret in stage 7.3 |
| `PLATFORM_DEPLOY_SSH_KEY` | `production` Environment, infrastructure repository | The **private** half of the platform deploy key from stage 0. Store it now, then delete the local file. | `platform-deploy.yml`'s deploy job |
| `PLATFORM_DEPLOY_HOST` | `production` Environment, infrastructure repository | The server's tailnet IPv4 (`100.x.y.z`). A MagicDNS name also works, but the literal IP avoids a resolution step. | `platform-deploy.yml`, for both the SSH target and Grafana's bind address |

**Check**, on each host you have converged: `sudo ufw status` as root shows default deny with 22 and the tailnet rules; `tailscale status --json` on the server reports `"BackendState": "Running"` (plain `tailscale status` prints the peer table, not that word); `systemctl list-timers` shows `prune-host-images.timer`; `/mnt/main-data` is mounted and holds `prometheus/` and `grafana/`.

The web ports are where the two differ, and the difference is the check: **production shows 80 and 443, staging shows neither.** Staging carries `web_allowed_cidrs = []` at both layers, so a staging host with UFW rules for 80/443 means its `group_vars` has drifted from its `terraform.tfvars`.

**Then prove the prune reports.** Its timer is weekly, so nothing reaches the heartbeat service until it fires — and a reporter that cannot reach the observer leaves a *successful* unit behind by design, so a green `systemctl status` is not evidence. Trigger one activation and read what it says:

```sh
cd ansible
ansible <environment> -i inventory/<environment>.hcloud.yml \
  --private-key ~/.ssh/<company>-root \
  -m ansible.builtin.systemd_service \
  -a "name=prune-host-images.service state=started" --vault-id <environment>@prompt
ansible <environment> -i inventory/<environment>.hcloud.yml \
  --private-key ~/.ssh/<company>-root \
  -m ansible.builtin.command \
  -a "journalctl -u prune-host-images.service -n 20 --no-pager" --vault-id <environment>@prompt
```

The journal should carry `prune-host-images: considered N, removed M` and then a line from `prune-host-images-report` — `Created` on the first activation, which is the observer's own reply to a ping that brought the check into existence. A line reading `reporting … failed` names the endpoint and curl's status instead, and means the check is not being fed.

A check named `<inventory_hostname>-prune-host-images` should now exist at the heartbeat service — `main-server-prune-host-images` and `staging-server-prune-host-images`, one per host and distinctly named because the two servers are named differently on purpose. **Give each the period and grace from Appendix A now.** A check created by its own first ping carries the *observer's* default period, not the unit's weekly one, so until you correct it the observer will call a perfectly healthy weekly job overdue within a day.

### 6.5 Staging's prune fails, and that is the expected state

On staging, the run above will not say `considered N, removed M`. It will report that the run was **abandoned** because the keep set is empty, exit non-zero, and ping `/fail`. Nothing is wrong.

The prune protects images that a deployed application references or a running container holds. On a host where nothing is deployed there are neither, so an empty keep set is the honest answer — and the role treats it as a refusal rather than proceeding, because proceeding would mean `docker image prune -a`, weekly, reporting success. That guard is doing exactly what it exists to do.

So `staging-server-prune-host-images` is red from the moment it exists until the platform stack reaches staging. Confirm the failure is *that* one — the journal should name the empty keep set, not a missing enumeration and not an unreachable observer — and leave it. What you must not do is mute it or delete the check: the alarm becomes meaningful the day staging runs something, and a muted check is one nobody re-arms.

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

**Check** (the production host): `docker ps` shows nine `platform-*` containers, all `(healthy)`; `http://100.x.y.z:3000` from your workstation opens Grafana and `admin` with the Grafana password shows three dashboards; the heartbeat service shows the check as up; a test alert (temporarily lower a threshold in the rules and redeploy, then revert) arrives in `#alerts`.

**Secrets created in this stage:** the seven in 7.3.

## Stage 8. Onboarding an application

Repeat this for every service. The infrastructure side is one inventory entry and one playbook run; the application side is one workflow and one Compose file. commerce-ops is the worked example.

### 8.1 Naming rule

The application's name in `deploy_apps` and the last segment of its image repository must be identical: an application named `orders` publishes to `ghcr.io/<org>/orders`. Image reclamation on the host identifies an application's images by that rule and silently reclaims nothing if they differ.

### 8.2 Infrastructure side

1. Generate the application's deploy key (stage 0.3 table).
2. Add to `deploy_apps` in `ansible/inventory/group_vars/prod.yml` (and, once an application has a staging deploy path, to `staging.yml` with a keypair of its own):

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

Every credential the system uses, in one place. "Env" means a GitHub Environment; where a row names one, it says which.

The Hetzner rows come in pairs, one per environment, because a Hetzner token reaches exactly one project. The `TF_API_TOKEN` row does not: one HCP user token serves both workspaces.

| Name | Where | Created in | Value from | Breaks when wrong |
|---|---|---|---|---|
| Production Hetzner Read Only | repo-root `.envrc` as `HCLOUD_TOKEN`; **`ansible/.envrc` as `HCLOUD_TOKEN_PROD`**; repo secret `HCLOUD_TOKEN` | 1 | The production Hetzner project → API tokens | Production's local plans, PR plans and drift detection; production's Ansible inventory source. **Rotating it means editing two local files, not one** — miss `ansible/.envrc` and the next converge dies at inventory parse |
| Production Hetzner Read & Write | `production` Env secret `HCLOUD_TOKEN` | 1 | Same project | Production's apply job |
| Staging Hetzner Read Only | `terraform/environments/staging/.envrc` as `HCLOUD_TOKEN`; **`ansible/.envrc` as `HCLOUD_TOKEN_STAGING`**; repo secret `HCLOUD_TOKEN_STAGING` | 1 | The **staging** Hetzner project → API tokens | Staging's local plans, PR plans and drift detection; staging's Ansible inventory source. Two local files here too |
| Staging Hetzner Read & Write | `staging` Env secret `HCLOUD_TOKEN` | 1 | Same project | Staging's apply job |
| `TF_API_TOKEN` | Repo secret and **both** Env secrets; `terraform login` locally | 2 | HCP Terraform → **Account settings** → Tokens (a USER token; an organisation token cannot write state) | Every Terraform job, and `terraform init` locally |
| Operator SSH key | Workstation | 0 | `ssh-keygen` | Root access; Ansible |
| Operator inspection key | Workstation | 0 | `ssh-keygen` | Daily unprivileged login |
| Tailscale server auth key | Password manager | 5 | Tailscale → Keys | Joining the host to the tailnet (first run, rebuilds) |
| `TAILSCALE_OAUTH_CLIENT_ID` / `_SECRET` | Env secret, infrastructure and each app repo | 5 | Tailscale → OAuth clients | Every deploy job |
| Vault password, one per environment | Password manager | 6 | Chosen | Running that environment's playbook |
| `ghcr_pull_token` | Vault-encrypted in `group_vars/<environment>.yml`, one per environment | 6 | GitHub classic PAT, `read:packages` | Pulling private images at deploy |
| `PLATFORM_DEPLOY_SSH_KEY` | Env secret | 6 | `ssh-keygen`, platform key | Platform deploys |
| `PLATFORM_DEPLOY_HOST` | Env secret | 6 | Tailscale → Machines | Platform deploys, Grafana bind |
| `PLATFORM_ACME_EMAIL` | Env secret | 7 | A mailbox | Certificate registration |
| `PLATFORM_POSTGRES_USER` / `_PASSWORD` | Env secret | 7 | Chosen / generated | Postgres startup; every manual `psql` |
| `PLATFORM_POSTGRES_EXPORTER_PASSWORD` | Env secret and typed into Postgres | 7 | Generated | Postgres metrics |
| `PLATFORM_GRAFANA_ADMIN_PASSWORD` | Env secret | 7 | Generated | Grafana login |
| `PLATFORM_SLACK_WEBHOOK_URL` | Env secret | 7 | Slack app | Alert delivery |
| `PLATFORM_DEADMANSWITCH_URL` | Env secret | 7 | Heartbeat service | The external alarm |
| `HEARTBEAT_PING_KEY` | **Repo** secret, and Vault-encrypted in each `group_vars/<environment>.yml` | 7 | Heartbeat service → project ping key | Nothing notices a periodic job failing or stopping |
| `<APP>_DEPLOY_SSH_KEY`, `DEPLOY_HOST`, app secrets | App repo Env secrets | 8 | Stage 8 | That application's deploys |

`HEARTBEAT_PING_KEY` is a **repository** secret, never an Environment one: a job reading a `production` Environment secret waits on required-reviewer approval, and an alarm that waits for a human to approve its own delivery is not an alarm. The same value goes into Ansible Vault for the host's prune unit.

The checks it addresses, and the settings each needs at the observer. A check comes into existence at its job's first ping and carries the vendor's default period until it is corrected here — so read these back once each check exists, and again after any rebuild:

| Check (slug) | Reported by | Period | Grace |
|---|---|---|---|
| `infrastructure-drift` | `.github/workflows/drift.yml`, nightly | 1 day | 12 hours |
| `infrastructure-pre-commit-autoupdate` | `.github/workflows/pre-commit-autoupdate.yml`, weekly | 7 days | 2 days |
| `main-server-prune-host-images` | `prune-host-images.service` on the production host, weekly | 7 days | 2 days |
| `staging-server-prune-host-images` | `prune-host-images.service` on the staging host, weekly | 7 days | 2 days |

The graces are set against **observed** scheduling, not against the `cron:` line: GitHub starts these runs hours after the minute they name — over four hours late, consistently, on the nightly — so a tolerance derived from the declared time would alarm on a healthy system.

The host slug is templated from `inventory_hostname`, which is why the two servers are named differently in their `terraform.tfvars` — sharing a name would merge them into one check, where the live host's weekly success would keep it green while the other's timer was dead. **Staging's check is expected to be red** until the platform stack reaches it; §6.5 says why, and that is a state to leave alone rather than mute.

## Appendix B. Rebuilding an existing host

**This covers the production host**, which is the one running an application stack. Staging is rebuilt the same way as far as stage 6 — `server_enabled` toggled off and on in its own `terraform.tfvars`, its new address read, its host key re-recorded (4.3), a fresh tailnet auth key if the old one expired, then 6.3 — and stops there, having no stack to redeploy.

An important consequence for staging specifically: its data volume is **not** wiped by a rebuild, and its `known_hosts` entry **is** invalidated. The second is the one that bites, because it presents as the converge failing at connection time rather than as a rebuild artefact.

The same stages, in this order, skipping what still exists: 4.2 (with `server_enabled` toggled off then on, or a replace with the `destroy-override` label), 4.3, 4.4 if the address changed, 5.3's auth key if the old one expired, 6.3, 6.4 (new tailnet IP → `PLATFORM_DEPLOY_HOST` and every application's `DEPLOY_HOST`), 7.4 by re-running the last Platform Deploy from Actions, 7.5, then each application's deploy from its own Actions. There is no database restore step: no platform-stack store needs one, because each is either recreated by a redeploy or its loss is accepted — see §8.3 and *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`). Two consequences to say out loud, because a rebuild is when they arrive: Prometheus's metrics history and Grafana's UI-created state do not come back, and `commerce-ops`'s own PostgreSQL — the one divergence that requirement names — is lost outright, since nothing backs it up. `docs/change-queue.md` entry 33 is what closes that, and entry 30 is the plan to turn this paragraph into a rehearsed runbook with timings.

## Appendix C. What to change for a company deployment

Recorded in detail in `docs/review-2026-09-08-host-readiness.md` and in `docs/change-queue.md`. The first two findings there — logical off-host database backups, and a decided database model — were resolved together by `scope-the-shared-database-to-non-durable-data`, which found that the shared instance holds no application data and that what this host needed was a stated boundary rather than a backup pipeline; §8.3 above is that boundary. The ones still to do before real data arrives: log rotation (21), swap and container limits (22, 7). The ones a company needs that this repository does not: a private repository in the company organisation, an approver who is not the author, and DNS as code (26).

**Two environments are no longer among them.** This document now stands both up, in stages 1 to 4, because deciding the count late is what costs — the Hetzner project layout, the workspace names and the read-only secret names are all stage 1 to 3 decisions, and revisiting them against a running production system is the expensive order. What a company still gets that this repository does not is the second host *configured*, and that waits on the entries stage 5 names.

**Heartbeat check names must stay distinct, and only half of that is automatic.** The workflow slugs carry this repository's name (`infrastructure-`), so a second repository's workflows get checks of their own. The host slug does **not**: it is `<inventory_hostname>-prune-host-images` with no repository or project segment, so two hosts both named `main-server` — the name prod's tfvars uses — would share one check in the same heartbeat project, and the live one's weekly success would keep it green while the other's timer was dead. That is the masking failure this mechanism exists to end. This stopped being hypothetical when `add-a-staging-environment` added a second environment: staging's `terraform.tfvars` names its server `staging-server` for exactly this reason, and says so where the value is set. Give a company host an `inventory_hostname` of its own, or a heartbeat project of its own. The free tier's 20 checks is the ceiling either way; count them before adding a third host.
