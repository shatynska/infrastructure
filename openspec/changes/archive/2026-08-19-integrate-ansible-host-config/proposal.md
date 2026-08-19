## Why

The server this repository provisions is currently bare: Terraform stops at
"a Hetzner VM exists," and everything from there (installing Docker,
hardening the host, running the eventual application stack) happens by hand
or not at all. That's exactly the manual, undocumented drift this repo was
built to eliminate on the provisioning side — it just hasn't reached the
configuration layer yet. Before any Ansible content or Compose stack gets
written, this repository needs a recorded structure and a firm boundary
between "provisions," "configures," and "runs applications," so that
implementation has something to conform to rather than being invented ad
hoc per playbook.

## What Changes

- Restructure the repository into `terraform/`, `ansible/`, and `platform/`
  top-level directories. `environments/` and `modules/` move under
  `terraform/` unchanged; CI workflow paths, `.tflint.hcl`, and the README's
  "Repository layout" section are updated to match. **BREAKING** for anyone
  with a local checkout referencing the old paths — no Terraform state
  impact (HCP Terraform binds by workspace name, not path).
- Establish the pipeline boundary: Terraform provisions (server, volumes,
  cloud firewall) → Ansible configures the provisioned host → Docker
  Compose runs applications, with per-application Compose files living in
  separate application repositories, not here. Ansible's scope stops once
  the container runtime is installed and ready — it never templates a
  service-definition file and never invokes a runtime's lifecycle commands,
  so this boundary stays swappable if Compose is later replaced.
- Add dynamic Ansible inventory via the `hcloud` plugin, grouped by the
  `environment` label the server already carries, reusing the existing
  read-only `HCLOUD_TOKEN`. No static or hand-maintained inventory file.
- Record the project's chosen defaults for the decisions the `ansible`
  skill explicitly defers to the consuming project: Docker installed via a
  pinned Galaxy role (e.g. `geerlingguy.docker` in a committed
  `requirements.yml`, not the only acceptable pattern going forward),
  secrets via Ansible Vault (with the plaintext-on-render boundary stated
  explicitly), and host-level security (UFW/fail2ban, SSH hardening) owned
  by Ansible while the cloud firewall stays owned by Terraform.
- Add a `platform/` directory for the single shared Compose stack (nginx as
  reverse proxy, a shared PostgreSQL instance with one database per
  application) that every application on the host depends on, kept
  co-located in this repo but deployed by a mechanism other than Ansible.
- No dedicated monitoring server: Prometheus/Grafana, when added, run
  alongside the platform stack on the same host; single-host observability
  risk is mitigated with an external dead-man's-switch rather than a second
  server.

This change establishes structure and convention only. It does not write
Ansible roles/playbooks content, does not write the `platform/`
`docker-compose.yml` service definitions, does not stand up
Prometheus/Grafana, and does not create any per-application repository.

## Capabilities

### New Capabilities
- `iac-host-configuration`: Ansible's ownership of provisioned-host
  configuration — dynamic inventory provenance, the container-runtime
  installation pattern, the secrets boundary, and the host-level vs. cloud
  firewall split. Also states the scope boundary that keeps Ansible from
  reaching into application-runtime territory.
- `iac-platform-services`: the shared `platform/` Compose stack that
  services common to the whole server (reverse proxy, shared database, and
  later monitoring) live in, distinct from per-application stacks, and its
  co-location boundary with Ansible.

### Modified Capabilities
- `iac-repo-foundations`: the "Environment and Module Folder Structure"
  requirement currently states environment folders live directly under
  `environments/` consuming `modules/` at the repo root. This changes to
  `terraform/environments/` and `terraform/modules/`.

## Impact

- Affected code: `environments/`, `modules/` (moved, not modified in
  content), `.github/workflows/{pr-validation,apply,drift}.yml`,
  `.tflint.hcl`, `README.md` (`Repository layout` section).
- New code: `ansible/` (inventory config, `requirements.yml`, empty
  role/playbook scaffolding as needed), `platform/` (directory only, or a
  minimal `docker-compose.yml` skeleton — scoped further in tasks.md).
- New dependency: `hcloud` Ansible collection (for the dynamic inventory
  plugin) and whichever Galaxy role is pinned for Docker installation.
- No impact to Terraform state, HCP Terraform workspace bindings, or
  existing GitHub Environment secrets.
