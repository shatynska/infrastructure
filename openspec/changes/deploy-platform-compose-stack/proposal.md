## Why

`iac-platform-services` already specifies the shape of the shared platform
stack (one reverse proxy, one shared Postgres instance, deployed by
something other than Ansible) but nothing has been built yet —
`platform/README.md` is the only file under `platform/`. Application repos
(starting with a LangGraph + FastAPI service) can't be deployed to the host
until this stack exists and there's a working, reviewable mechanism to
deploy and update it.

## What Changes

- Add `platform/docker-compose.yml` defining Traefik (reverse proxy, with
  TLS via ACME) and PostgreSQL (single shared instance), on a Docker network
  named and exposed so that a separate application repository's own Compose
  file can join it and be routed by Traefik, per the existing "A new
  application reuses the platform stack" scenario.
- Add a GitHub Actions workflow that deploys this stack over SSH:
  - On any pull request touching `platform/**`: validate via
    `docker compose config` (no SSH credential required — the PR diff on
    the Compose YAML is the change under review, there is no separate
    "plan" step).
  - On merge to `main`: a job with no deploy credential first posts the
    diff this merge introduces under `platform/**` to the run's job
    summary; only then does the deploy job — gated by the same
    `production` GitHub Environment approval already used by the Terraform
    apply workflow, so the approver sees that diff first — authenticate as
    the `deploy` account provisioned by the `bootstrap-ansible-host-
    baseline` change, render `.env` from GitHub Actions secrets, and
    trigger that account's one fixed, argument-free `sudo`-permitted
    deploy script (also provisioned by `bootstrap-ansible-host-baseline`)
    to run `docker compose pull` and `docker compose up -d --wait` on the
    host.
- **Depends on** `bootstrap-ansible-host-baseline`: the `deploy` account and
  its SSH key must exist on the host before this workflow's deploy job can
  authenticate. This change does not provision that account itself.
- Does not open HTTP/HTTPS at the Hetzner cloud firewall layer
  (`web_allowed_cidrs` in `terraform/environments/prod/terraform.tfvars` is
  currently unset) — that is a separate, small Terraform change and a
  prerequisite for Traefik to serve any public traffic, tracked as an
  external dependency rather than folded in here.
- Does not define the per-application database provisioning process (how a
  new application actually gets a database inside the shared Postgres
  instance) — flagged as a follow-up, not solved by this change.

## Capabilities

### New Capabilities
- `iac-platform-deploy-pipeline`: the GitHub Actions workflow mechanics for
  deploying and updating `platform/`'s Compose stack — PR validation,
  gated post-merge deploy, credential scoping, and secrets rendering.

### Modified Capabilities
- `iac-platform-services`: adds requirements for the reverse proxy's
  specific identity (Traefik) and TLS handling, the shared Docker network
  new application repos join, and that platform-level secrets are rendered
  from CI rather than committed — none of which the existing spec states at
  this level of detail.

## Impact

- `platform/docker-compose.yml`, `platform/.env.example` (or equivalent) —
  new.
- `.github/workflows/` — new workflow file for platform validation + deploy.
- Requires `bootstrap-ansible-host-baseline` to be implemented first (the
  `deploy` account/key it provisions).
- Requires a small, separate Terraform change to set `web_allowed_cidrs`
  before Traefik can serve public HTTP/HTTPS traffic — noted as a blocker,
  not addressed here.
- No changes to `ansible/` or `terraform/` in this change.
