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

A staging environment is *not* a non-goal — it's an anticipated near-term
addition (see Status below), not a rejected idea.

## Repository layout

This repository commits seven top-level directories:

```sh
git ls-files | grep / | sed 's|/.*||' | sort -u
```

- `terraform/` — Terraform provisions infrastructure (server, volumes, cloud
  firewall).
  - `terraform/modules/` — shared, reusable Terraform modules (e.g.
    `terraform/modules/server`).
  - `terraform/environments/<name>/` — one folder per environment (currently
    only `prod`), each calling the shared modules with environment-specific
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

   Never put the **Read & Write** token here or in any other local file — it
   lives exclusively in the `production` GitHub Environment secret. See
   `AGENTS.md`.

   Without `direnv`, `source .envrc` from the repo root once per shell —
   it is a plain `export`. The dynamic inventory needs `HCLOUD_TOKEN` too,
   not just Terraform: without it `ansible -i inventory/hcloud.yml prod`
   resolves no hosts.

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
   cd ansible/roles/<role> && molecule test --all
   ```

   Several roles carry more than one scenario, so `molecule test -s default`
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

   **If `molecule create` fails on your machine before any test runs**, check
   `~/.docker/config.json`. A `credsStore` or `credHelpers` entry makes
   Molecule's Docker driver shell out to a credential helper that may not
   work in your environment, and it fails during `create` with a
   `StoreError`. This is an environment quirk, not a repository defect —
   point `DOCKER_CONFIG` at a directory holding an empty `{}` for the run:

   ```sh
   mkdir -p /tmp/molecule-docker && echo '{}' > /tmp/molecule-docker/config.json
   DOCKER_CONFIG=/tmp/molecule-docker molecule test --all
   ```

## Environment variables and secrets

Each `terraform/environments/<env>/terraform.tfvars` is committed and holds **non-secret**
configuration only (server name and type, `location`, image, SSH public key,
allowed CIDRs, volume name and size, and the server/volume enable flags). Files
matching `*.secret.tfvars` or `secrets.auto.tfvars` are gitignored and must
never be committed.

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
  that exact saved plan only after a required reviewer approves the
  `production` GitHub Environment.
- **`platform-deploy.yml`** (merge to `main` touching `platform/`) — the same
  diff-then-approve split for the Compose stack: a diff job with no credential,
  then a deploy job gated on the same `production` Environment.
- **`drift.yml`** (nightly) — a drift-detection plan, no apply. Opens or
  updates a single GitHub issue when the committed configuration diverges from
  real infrastructure, and closes it once resolved.
- **`pre-commit-autoupdate.yml`** (weekly) — runs `pre-commit autoupdate` and
  opens a pull request with the result. Dependabot has no `pre-commit`
  ecosystem, so pinned hook revisions are refreshed here.

`validate` and `ansible-verify` are the two job names intended to gate a merge.
Whether they are registered as required contexts is a repository setting, not
anything this repository can state — see the note in Local setup step 5 for
what answers it.

### Testing

Terraform has no traditional unit-test layer here; verification is the static
checks and plan review above, plus three test commands, each with its own
subject:

| Subject | Command | Tests live in |
|---|---|---|
| Terraform modules | `terraform test`, from each module directory | `terraform/modules/<name>/tests/*.tftest.hcl` |
| What an Ansible role does to a host | `molecule test --all`, from each role directory | `ansible/roles/<name>/molecule/<scenario>/` |
| Any property that is a static read of a committed file | `python3 -m unittest discover --start-directory .github/tests`, from the repository root | `.github/tests/*.py` |

`AGENTS.md` carries the rules for choosing between them, and the caveats that
matter when running them. See the change `project-foundation`'s design.md for
the full testing strategy.

### Re-enabling the drift-detection workflow

GitHub automatically disables `schedule`-triggered workflows after 60 days
without any repository activity. If the nightly drift check appears to have
stopped running, check **Actions → Drift Detection → ⋯ → Enable workflow**,
then trigger it once manually (`workflow_dispatch`) to confirm it runs clean.

## Status

The bootstrap is done. `prod` is provisioned from
`terraform/environments/prod/`, configured by
`ansible/playbooks/host-baseline.yml`, and runs `platform/`'s Compose stack;
applications deploy onto it from their own repositories, through the
per-application deploy-key path the `deploy_user` role sets up. Project
identity, scope, and non-goals are recorded in the change
`project-foundation`'s design.md; every change since is recorded under
`openspec/`.

A staging environment (a second `terraform/environments/<name>/` folder reusing
the same modules) is still anticipated as the next environment, but is not yet
in scope.

The `terraform/`/`ansible/`/`platform/` structure, and the pipeline boundary
between the three, were established by the change
`integrate-ansible-host-config`.
