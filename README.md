# infrastructure

Terraform-managed infrastructure on Hetzner Cloud. State lives in HCP Terraform
(CLI-driven, local execution); GitHub Actions runs the `terraform` CLI and
gates every apply behind manual approval. See
`bootstrap-hetzner-iac`'s design.md for the full rationale
behind these choices.

Manual, ad-hoc server provisioning is hard to audit and drifts silently from
whatever's documented. This repository replaces that with declarative,
version-controlled infrastructure — every change goes through a reviewed
`terraform plan`, an exact saved plan approved before apply, and nightly
drift detection — prioritizing reliability, drift prevention, and
auditability of the infrastructure layer itself, ahead of any specific
workload. It's operated primarily by agentic/automated workflows (e.g.
Claude Code), with a human required to approve every change that reaches
production; see `AGENTS.md` for the conventions that assumes.

## Non-goals

- **Multi-cloud support.** Hetzner Cloud only.
- **Multi-region deployment.** A single region for the foreseeable future —
  `location = "hel1"` in `terraform/environments/prod/terraform.tfvars`.
- **Container orchestration.** Plain VMs via `hcloud_server`; no
  Kubernetes, Nomad, or similar.

A staging environment is *not* a non-goal, and is no longer hypothetical:
`terraform/environments/staging/` exists (see Status below).

## Repository layout

This repository commits seven top-level directories:

```sh
git ls-files | grep / | sed 's|/.*||' | sort -u
```

- `terraform/` — Terraform provisions infrastructure (server, volumes, cloud
  firewall).
  - `terraform/modules/` — shared, reusable Terraform modules (e.g.
    `terraform/modules/server`).
  - `terraform/environments/<name>/` — one folder per environment (`prod` and
    `staging`), each calling the shared modules with environment-specific
    variables. New environments are added as new folders, never as branches.
- `ansible/` — Ansible configures the provisioned host (container runtime,
  host-level security). Scope stops at the container runtime; it never
  templates a service-definition file or manages application lifecycle.
- `platform/` — the shared Compose stack that every application on the host
  depends on, deployed by a mechanism other than Ansible: reverse proxy,
  shared PostgreSQL instance, and the monitoring services (Prometheus,
  Alertmanager, Grafana and three exporters).
- `.github/` — the pipeline: workflows, the CI-configuration test suite under
  `.github/tests/`, `dependabot.yml`, and the pinned CI dependencies.
- `openspec/` — this repository's specifications (`openspec/specs/`) and the
  record of every change made to it.
- `docs/` — `change-queue.md`, identified changes not yet opened, and
  `deferred-work.md`, what this project has deliberately not done.
- `.claude/` — coding-agent tooling: the OpenSpec slash commands and skills
  under `commands/` and `skills/` are committed. Working trees live under
  `.claude/worktrees/` and are not.

## Local setup

1. Install [pre-commit](https://pre-commit.com/) and the tools its hooks
   shell out to: `terraform`, [`tflint`](https://github.com/terraform-linters/tflint),
   [`gitleaks`](https://github.com/gitleaks/gitleaks), and
   [`ansible-core`](https://pypi.org/project/ansible-core/) (for
   `ansible-playbook --syntax-check`; `ansible-lint` itself is installed by
   `pre-commit` into its own managed environment).
2. From the repo root, run:

   ```sh
   pre-commit install --hook-type pre-commit --hook-type commit-msg
   ```

   This installs the formatting/linting/validation/secret-scan hooks (running
   on `git commit`) and the Conventional Commits message check (running on
   the commit message itself).
3. Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/)
   (`feat:`, `fix:`, `docs:`, `chore:`, ...) — enforced locally by the
   `commitlint` hook and mirrored by CI.
4. Local `terraform plan`/`validate` needs the **Read Only** Hetzner token as
   `HCLOUD_TOKEN`. Recommended: [`direnv`](https://direnv.net/) so it's only
   loaded while you're in this directory:

   ```sh
   cp .envrc.example .envrc   # fill in the real token; .envrc is gitignored
   direnv allow
   ```

   Never put a **Read & Write** token here or in any other local file. This
   holds for every environment: each one's write token lives exclusively in
   that environment's own GitHub Environment secret — prod's in `production`,
   staging's in `staging` — and an environment whose Environment requires no
   reviewer is no exception, since the reviewer and the confinement are
   independent. What belongs in this file is a **Read Only** token, and
   nothing else. See `AGENTS.md`.

   **One token reaches one environment**, because each environment has a
   Hetzner project of its own and a Hetzner token cannot span projects. Put
   prod's read-only token in the repo-root `.envrc`, and staging's in an
   `.envrc` inside `terraform/environments/staging/` — directory-scoped, so
   planning staging never leaves staging's token in the shell that plans prod.

   Without `direnv`, `source .envrc` from the repo root once per shell —
   it is a plain `export`. That path loses the isolation above, since the
   export outlives the directory: source the environment's own file in a
   shell you do not reuse for another environment, or the next
   `ansible -i inventory/hcloud.yml prod` silently resolves no hosts. The dynamic inventory needs `HCLOUD_TOKEN` too,
   not just Terraform: without it `ansible -i inventory/hcloud.yml prod`
   resolves no hosts. It resolves no hosts under the *wrong* environment's
   token either, and that failure is quiet — a play matching no host exits 0.
   The inventory sees only the project its token belongs to.

5. To run the Ansible tests, install the pinned Molecule toolchain:

   ```sh
   uv venv ~/.venvs/molecule                                  # or python -m venv
   VIRTUAL_ENV=~/.venvs/molecule uv pip install -r ansible/requirements-test.txt
   export PATH=~/.venvs/molecule/bin:$PATH                    # add to your shell rc
   ansible-galaxy collection install -r ansible/requirements.yml
   ansible-galaxy role install -r ansible/requirements.yml -p ansible/roles
   ```

   Install into a virtualenv, not system Python — recent Debian/Ubuntu mark
   the system interpreter externally-managed and refuse a bare
   `pip install`. If `python3 -m venv` fails with an `ensurepip` error, that
   is the `python3-venv` package missing; [`uv`](https://docs.astral.sh/uv/)
   sidesteps it entirely, which is why it is shown here.

   `-p ansible/roles` is load-bearing, not a preference. `ansible/ansible.cfg`
   sets `roles_path = roles`, which *replaces* the default search list rather
   than extending it, and every Molecule scenario overrides
   `ANSIBLE_ROLES_PATH` to the same place — so a role installed to the default
   `~/.ansible/roles` is invisible to all of it, and converge fails on the
   dependency rather than on anything the scenario asserts. The two commands
   are separate because `-p` applies only to roles: passing it alongside
   collections silently ignores them, with a warning that is easy to miss.

   CI runs `ansible-lint` and `ansible-playbook --syntax-check` on every pull
   request touching `ansible/`, and the Molecule suite in a separate
   `Ansible Verify` workflow. **All three are meant to block a merge**: the
   `ansible-verify` job is the status check context registered on `main`, so a
   red scenario is a blocked pull request rather than something to notice. A
   pull request touching nothing under `ansible/` starts no container and the
   check still reports. Whether the context is registered is a repository
   setting rather than anything in this repository — `gh api
   repos/:owner/:repo/branches/main/protection` is what answers it.

   Running the suite locally before opening a pull request is therefore worth
   more, not less: it is roughly six minutes of hosted-runner time to find out
   there, and the failure now stops the merge.

   Run them **per role, with `--all`**:

   ```sh
   cd ansible/roles/<role> && ../../scripts/run-molecule test --all
   ```

   Through `run-molecule`, not `molecule` directly: it gives this working
   tree its own container names and ephemeral directory, so a run here
   cannot collide with a run in another working tree on the same machine.
   Invoked bare, every scenario now fails at `create` with `Invalid
   container name` — deliberately, and the offending name says what to
   run instead. `AGENTS.md`, "Namespacing Molecule per working tree",
   carries the reasoning.

   Several roles carry more than one scenario, so a run without `--all`
   silently skips most of the suite. To see how much, from the repository
   root: `git ls-files 'ansible/roles/*/molecule/*/molecule.yml'`.

   The suite runs offline: no GHCR credential is needed. Setting
   `MOLECULE_GHCR_PULL_TOKEN` and `MOLECULE_GHCR_PULL_USERNAME` **together**
   additionally exercises the real registry-login path.

   **The platform image is pinned by digest, and refreshing it is manual.**
   Every scenario runs `geerlingguy/docker-ubuntu2204-ansible@sha256:…` with
   `pre_build_image: true`. That image publishes no versioned tag, so a digest
   is the only exact pin available, and nothing updates it automatically —
   Dependabot does not read `molecule.yml`. To refresh:

   ```sh
   curl -s https://hub.docker.com/v2/repositories/geerlingguy/docker-ubuntu2204-ansible/tags/latest \
     | jq -r .digest
   ```

   Put that digest in **every scenario this repository owns** — the same
   listing as above, run from the repository root:

   ```sh
   git ls-files 'ansible/roles/*/molecule/*/molecule.yml'
   ```

   It selects committed files, which is why it is the right question to ask.
   Do not glob `ansible/roles/*/molecule/*/` instead: once you have run
   `ansible-galaxy`, that also matches
   `ansible/roles/geerlingguy.docker/molecule/default/molecule.yml`, which is
   installed content on a different image, is gitignored, and is discarded by
   the next reinstall. All of them must agree, and
   `.github/tests/test_ci_configuration.py` fails the build if they do not.

   Write the reference **without** the tag. `…:latest@sha256:…` looks more
   informative and costs a registry round-trip on *every* `molecule create`,
   because `community.docker` then builds a digest lookup that cannot match the
   image already on your machine — and on a host with a `credsStore` it fails
   outright. With the bare form, once the image has been fetched once, `create`
   makes no registry call, so the `DOCKER_CONFIG` workaround below is only
   needed for that first fetch rather than on every run. The rationale for all
   of this, including why `pre_build_image` is load-bearing rather than a
   speed-up, is in `ansible/roles/docker/molecule/default/molecule.yml`.

   **If `create` fails with `Invalid container name`**, Molecule was invoked
   directly rather than through `ansible/scripts/run-molecule`. That is the
   designed refusal, not a defect: each scenario's instance name defaults to
   a value Docker cannot accept, so a run with no working-tree namespace
   stops instead of quietly sharing a container with another working tree.
   The name Docker echoes back says what to run.

   **If `create` fails with `couldn't resolve module/action`**, the pinned
   Galaxy collections are not installed. `run-molecule` checks for them
   first and names the one-time install; reaching this error means Molecule
   was invoked directly.

   **If `create` fails with a `StoreError` before any test runs**, check
   `~/.docker/config.json`. A `credsStore` or `credHelpers` entry makes
   Molecule's Docker driver shell out to a credential helper that may not
   work in your environment. This is an environment quirk, not a repository
   defect — point `DOCKER_CONFIG` at a directory holding an empty `{}` for
   the run:

   ```sh
   mkdir -p /tmp/molecule-docker && echo '{}' > /tmp/molecule-docker/config.json
   DOCKER_CONFIG=/tmp/molecule-docker ../../scripts/run-molecule test --all
   ```

## Environment variables and secrets

Each `terraform/environments/<env>/terraform.tfvars` is committed and holds **non-secret**
configuration only (server name and type, `location`, image, SSH public key,
allowed CIDRs, volume name and size, and the server/volume enable flags). Files
matching `*.secret.tfvars` or `secrets.auto.tfvars` are gitignored and must
never be committed.

Repository secrets in GitHub hold `HCLOUD_TOKEN` and `HCLOUD_TOKEN_STAGING`
(one read-only token per environment, since a repository secret holds one value
and each environment's project needs its own), `TF_API_TOKEN` (see CI/CD
below for the privilege split on those), `APP_CLIENT_ID` / `APP_PRIVATE_KEY`,
and `HEARTBEAT_PING_KEY` — the last of those deliberately repository-scoped
rather than an Environment secret, because the scheduled workflows report their
own liveness with it and a job reading an Environment secret would wait on
required-reviewer approval. This is not the full list of secrets the workflows read: the
`PLATFORM_*` and `TAILSCALE_OAUTH_*` values, and the read-write overrides of
`HCLOUD_TOKEN` and `TF_API_TOKEN`, are consumed only by jobs declaring an
`environment:` — `production` or `staging` — and are Environment secrets rather
than repository ones. Declaring the Environment is what confines them; whether
it also pauses for a reviewer is a separate property, and `staging` does not.

`APP_CLIENT_ID` and `APP_PRIVATE_KEY` identify a GitHub App named
**`infrastructure-autoupdate`**, owned by `shatynska` and reachable at
<https://github.com/settings/apps/infrastructure-autoupdate>. It exists for one
reason: `pre-commit-autoupdate.yml` opens a pull request, and a pull request
opened with a workflow's default `GITHUB_TOKEN` starts no workflow run — so
`validate` and `ansible-verify` would never report on it and it could never be
merged. The workflow mints a short-lived installation token from the App
instead, and the App authors the pull request.

Its scope is deliberately the smallest thing that works: installed on this
repository alone, with repository permissions Contents (to push the update
branch) and Pull requests (to open one) at read and write, and no account-level
permissions at all. Nothing else in this repository uses it. The minting step
additionally down-scopes each token it issues to those same two permissions, in
committed content, so widening the App later does not silently widen the token.

That scope bounds what the workflow's pull-request step may ask for. `labels`
and `assignees` are issue operations and would need Issues. `team-reviewers` is
unavailable rather than merely withheld: it needs an organisation permission,
and this App is user-owned on a personal repository. Adding either of the first
two means revisiting the App's permissions, not only editing the workflow.

To rotate the credential, generate a new private key on that App's settings page
and replace the `APP_PRIVATE_KEY` secret with it, then delete the old key. The
App itself is not recreated and `APP_CLIENT_ID` does not change. A GitHub App
private key does not expire, which is why the App was chosen over a personal
access token — a token with a mandatory expiry date would stop this workflow
opening pull requests on a date nobody chose, which is the exact failure the App
was introduced to end.

## CI/CD

One entry per file in `.github/workflows/`:

- **`pr-validation.yml`** (every pull request) — the `validate` job. Two checks
  run **unconditionally**, so a documentation-only pull request is not a
  pull request that runs nothing: the CI-configuration test suite
  (`.github/tests`) and `gitleaks` secret scanning. The rest are conditioned on
  what changed — `terraform fmt -check`, `terraform validate`, `tflint`,
  `terraform test`, Trivy misconfiguration scanning and a `terraform plan`
  posted as a PR comment for `terraform/`; `docker compose config` for
  `platform/`; `ansible-lint` and `ansible-playbook --syntax-check` for
  `ansible/`.
- **`ansible-verify.yml`** (every pull request) — the Molecule suite, matrixed
  over roles, behind an `ansible-verify` job that aggregates the matrix. Like
  `validate`, it always reports; a pull request touching nothing under
  `ansible/` starts no container.
- **`apply.yml`** (merge to `main`, path-filtered) — a two-job apply. A plan
  job (read-only Hetzner token) saves a plan file and posts its diff to the run
  summary, plus a destroy-policy check; an apply job (read-write token) applies
  that exact saved plan, and only after that environment's own GitHub
  Environment lets it — which for `production` means a required reviewer, and
  for `staging` means immediately. Both run per environment, over whichever
  environments the merge affects.
- **`platform-deploy.yml`** (merge to `main` touching `platform/`) — the same
  diff-then-approve split for the Compose stack: a diff job with no credential,
  then a deploy job gated on the same `production` Environment.
- **`drift.yml`** (nightly) — a drift-detection plan, no apply. Opens or
  updates a single GitHub issue when the committed configuration diverges from
  real infrastructure, and closes it once resolved.
- **`pre-commit-autoupdate.yml`** (weekly) — runs `pre-commit autoupdate` and
  opens a pull request with the result. Dependabot has no `pre-commit`
  ecosystem, so pinned hook revisions are refreshed here. The pull request is
  opened by the `infrastructure-autoupdate` GitHub App rather than by
  `GITHUB_TOKEN`, so that `validate` and `ansible-verify` actually report on it;
  see Environment variables and secrets.

`validate` and `ansible-verify` are the two job names intended to gate a merge.
Whether they are registered as required contexts is a repository setting, not
anything this repository can state — see the note in Local setup step 5 for
what answers it.

Dependabot covers the rest, across three ecosystems: `terraform` provider pins,
`github-actions` references, and — via `docker-compose` over `/platform` — the
shared stack's eight container image pins. Those pins are exact by requirement,
so they never move on their own; this is what proposes the move, and the
proposal then goes through the same review and the same gated deploy as a
hand-written bump.

**Reviewing one of those image pull requests carries an obligation no check in
this repository can discharge.** Ask whether the proposed image declares a
persistent store the current one does not — a volume the image itself declares,
which appears in no committed file and which `docker-compose.yml` therefore
cannot be read for. Establishing that needs a registry call, which the
CI-configuration suite forbids itself; a new store arriving unnoticed is what
*No Store on This Host Holds Data Requiring Backup*
(`openspec/specs/iac-safety-hardening/spec.md`) exists to prevent, and its
classification of every store on this host is what a silent one would falsify.
Version tags are the other half: the automated floor rejects a tag naming fewer
than two version components, and whether a tag that passes is a release rather
than a series its publisher repoints is likewise yours to decide.

### Testing

Terraform has no traditional unit-test layer here; verification is the static
checks and plan review above, plus three test commands, each with its own
subject:

| Subject | Command | Tests live in |
|---|---|---|
| Terraform modules | `terraform test`, from each module directory | `terraform/modules/<name>/tests/*.tftest.hcl` |
| What an Ansible role does to a host | `ansible/scripts/run-molecule test --all`, from each role directory | `ansible/roles/<name>/molecule/<scenario>/` |
| Any property that is a static read of a committed file | `python3 -m unittest discover --start-directory .github/tests`, from the repository root | `.github/tests/*.py` |

`AGENTS.md` carries the rules for choosing between them, and the caveats that
matter when running them. See the change `project-foundation`'s design.md for
the full testing strategy.

### When a periodic job stops working

Every periodic job — the nightly drift check, the weekly hook autoupdate, and
the weekly image prune on the host — reports each run to a heartbeat check of
its own, and **the alarm is the check going quiet**, delivered to Slack
`#alerts`. A run that failed, a run killed mid-flight and a run that never
happened at all therefore look the same to it, which is the point: the last of
those emits no failure for anything else to notice.

**This is only live once three things exist outside this repository**: the
`HEARTBEAT_PING_KEY` repository secret, the same key Vault-encrypted in
`ansible/inventory/group_vars/prod.yml`, and the checks' routing at the
observer. Until then the reporters fail loudly rather than quietly — a
scheduled run turns red naming the missing secret, and a host converge refuses
— but nothing is being watched. `docs/bootstrap-a-new-host.md` stage 6.1, stage
7.1 and stage 7.3 are where those three are set, and its Appendix A carries the
period and grace each check needs.

The three checks, the slug each reports under, and the period and grace that
decide when silence becomes an alarm are listed once, in
`docs/bootstrap-a-new-host.md`'s Appendix A, beside the `HEARTBEAT_PING_KEY`
secret they are addressed with. They are the observer's configuration, not this
repository's, so nothing here can verify them.

### Re-enabling the drift-detection workflow

GitHub automatically disables `schedule`-triggered workflows after 60 days
without any repository activity. If the nightly drift check appears to have
stopped running, check **Actions → Drift Detection → ⋯ → Enable workflow**,
then trigger it once manually (`workflow_dispatch`) to confirm it runs clean.

**A manual dispatch reports to the heartbeat check too, and so resets its
silence timer.** After dispatching, confirm the schedule itself is enabled
rather than reading the green check as evidence that it is: a workflow that is
still disabled will look healthy for one whole period — a day for drift, a week
for the autoupdate — before the alarm you were acting on comes back.

## Status

The bootstrap is done. `prod` is provisioned from
`terraform/environments/prod/`, configured by
`ansible/playbooks/host-baseline.yml`, and runs `platform/`'s Compose stack;
applications deploy onto it from their own repositories, through the
per-application deploy-key path the `deploy_user` role sets up. Project
identity, scope, and non-goals are recorded in the change
`project-foundation`'s design.md; every change since is recorded under
`openspec/`.

`staging` is the second environment, provisioned from
`terraform/environments/staging/` and reached by the same pipeline: it is
planned on every pull request that affects it, applied on merge, and swept by
the nightly drift run. Two things distinguish it from prod, both deliberate and
both recorded in its own `pipeline.yml` — its apply requires no reviewer, and
the destroy-policy gate does not apply to it. Neither is a relaxation of where
its write credential lives; that is identical to prod's. It runs in a **separate
Hetzner Cloud project**, which is what makes both safe and what frees it to
reuse prod's `main-data` volume name, and therefore the same on-host mount path.

**Two servers now run**, one per environment: prod's `cx33` (4 vCPU / 8 GB) and
staging's `cx23` (2 vCPU), each with its own 10 GB `main-data` volume, in
separate Hetzner projects. Two bills, two hosts to patch and converge, two
tailnet members to keep track of — staging costs roughly half what prod does and
is not free in either money or attention.

What staging is *not*, yet: configured. It carries no Ansible group variables,
no platform stack and no DNS records, so it is a provisioned host rather than a
place applications deploy to. `docs/change-queue.md` records that half.

Adding the environment after it changed **no file under
`.github/workflows/`** — `pr-validation.yml`, `apply.yml` and `drift.yml`
discover `terraform/environments/*/` and run per environment. What adding one
does still take is everything outside those files:

- a `terraform/environments/<name>/` folder reusing the same modules, carrying
  its own `pipeline.yml` — the committed declaration naming the GitHub
  Environment its apply job attaches to, the repository secret holding its
  read-only Hetzner token, and whether the destroy-policy gate applies to it.
  Its read-only secret name and its GitHub Environment name must both be
  distinct from every other environment's, and discovery fails the pipeline if
  they are not;
- its own HCP Terraform workspace, and a `.github/dependabot.yml` entry for the
  lockfile `terraform init` creates in that folder;
- a GitHub Environment of the declared name, holding `HCLOUD_TOKEN` (that
  environment's **Read & Write** token) and `TF_API_TOKEN` (an HCP **user**
  token, from Account settings → Tokens — an organisation token can read a
  workspace but cannot write its state, and fails as
  `Error acquiring the state lock: resource not found` long after `init`
  succeeded). An Environment that omits `HCLOUD_TOKEN` silently resolves to the
  repository secret of that name, so the apply job refuses to apply where it
  detects that;
- a repository secret of the declared read-only name, holding that
  environment's **Read Only** token;
- whatever the environment is *for* — a host to configure, group variables, DNS.
  For staging, `docs/change-queue.md` records what that half still needs;
- and the thing the rest of this list does not say, because it is about secrets
  and settings: **an environment is a second server, running permanently.**
  Another instance and another volume on the bill every month, another host to
  patch, converge, monitor and rebuild, and another set of credentials to rotate.
  Adding one is a standing commitment rather than a one-off configuration.

The `terraform/`/`ansible/`/`platform/` structure, and the pipeline boundary
between the three, were established by the change
`integrate-ansible-host-config`.
