## 1. Repository Restructure

- [ ] 1.1 `git mv environments terraform/environments`
- [ ] 1.2 `git mv modules terraform/modules`
- [ ] 1.3 Update `.github/workflows/pr-validation.yml` path references (working directory, `terraform fmt`/`validate`/`tflint`/Trivy targets) to `terraform/environments` and `terraform/modules`
- [ ] 1.4 Update `.github/workflows/apply.yml` path references the same way
- [ ] 1.5 Update `.github/workflows/drift.yml` path references the same way
- [ ] 1.6 Update `.tflint.hcl` if it references the old paths
- [ ] 1.7 Update `README.md`'s "Repository layout" section and any other path references (including the "Local setup" and "CI/CD" sections) to the new paths
- [ ] 1.8 Update `.envrc.example` / any local tooling docs that reference the old paths
- [ ] 1.9 Run `terraform init` and `terraform plan` inside `terraform/environments/prod` locally (read-only token) and confirm an empty diff — proves the move didn't affect state

## 2. Ansible Scaffolding

- [ ] 2.1 Create `ansible/` with `inventory/`, `playbooks/`, and `roles/` subdirectories, adding a `.gitkeep` placeholder in `playbooks/` and `roles/` since both are otherwise empty and Git does not track empty directories
- [ ] 2.2 Add `ansible/inventory/hcloud.yml` configuring the `hcloud` dynamic inventory plugin, grouped by the `environment` label
- [ ] 2.3 Add `ansible/requirements.yml` pinning the `hcloud` collection and the chosen Docker-installation Galaxy role (e.g. `geerlingguy.docker`) to exact versions
- [ ] 2.4 Add `ansible/ansible.cfg` pointing at `inventory/hcloud.yml` by default
- [ ] 2.5 Confirm `ansible-inventory -i ansible/inventory/hcloud.yml --graph` resolves the existing prod server using the current read-only `HCLOUD_TOKEN`, with no separate token added
- [ ] 2.5b Confirm `ansible-inventory -i ansible/inventory/hcloud.yml --graph` returns no host for the prod group when `server_enabled = false` (verifies the spec's "Disabled server yields no stale inventory entry" scenario), or document why this check is deferred if toggling the flag isn't safe to exercise at task time
- [ ] 2.6 Add `ansible-lint` (and `ansible-playbook --syntax-check`) to `.pre-commit-config.yaml` so future Ansible changes get the same automated local gate the Terraform tooling already has

## 3. Platform Directory Scaffolding

- [ ] 3.1 Create `platform/` directory
- [ ] 3.2 Add `platform/README.md` recording the boundary this change establishes (shared reverse proxy + shared PostgreSQL instance with per-application databases; deployed by a mechanism other than Ansible, to be decided in a later change; monitoring services, when added, run on this same host rather than a dedicated server) — no `docker-compose.yml` service content yet

## 4. Conventions and Documentation

- [ ] 4.1 Add a short "Host configuration and platform stack" convention section to `AGENTS.md` (or reference `design.md`) recording: Ansible Vault as the default secrets mechanism with the render-to-disk boundary, host-firewall-vs-cloud-firewall ownership, and the scope line Ansible content must not cross
- [ ] 4.2 Update `README.md`'s "Status" section to note this change and link to `openspec/changes/integrate-ansible-host-config/`
- [ ] 4.3 Open a follow-up change to sweep the now-stale `environments/`/`modules/` path references left in `iac-cicd-pipeline`, `iac-safety-hardening`, and `iac-state-management`, and in `iac-repo-foundations`' other requirements (e.g. "Version Control Excludes State and Secrets") — not folded into this change since none of those requirements' *behavior* changes, only incidental path text (see `design.md` Risks)

## 5. Verification

- [ ] 5.1 `terraform fmt -check`, `terraform validate`, and `tflint` pass against the moved `terraform/` tree
- [ ] 5.2 `pre-commit run --all-files` passes repo-wide after the restructure
- [ ] 5.3 `ansible-lint` and `ansible-playbook --syntax-check` (or equivalent) pass against the new `ansible/` scaffolding
- [ ] 5.4 `openspec validate --change integrate-ansible-host-config --strict` passes
