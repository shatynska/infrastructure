## Why

`platform_data_volume`'s device-discovery block cannot report its own headline
failure. When no `/dev/disk/by-id/scsi-0HC_Volume_*` device is present, the
`set_fact` that reads `files[0]` raises a Jinja index error and the play aborts
*before* the `assert` written to diagnose exactly that case. The operator gets
`list object has no element 0` instead of the question they need to be asked —
"is the `main-data` Volume actually attached?" — and that case is not exotic: it
is what every host sees when `volume_enabled` is false in `terraform.tfvars`, or
while a volume is still attaching.

A full-repository audit on 2026-09-06 found the defect together with four small
consistency slips in the same files. They travel here because each is a
one-line-to-one-block edit and the audit's verdict was that this repository
needs maintenance, not restructuring — not because they share a cause.

## What Changes

**The defect (`ansible/roles/platform_data_volume/`)**

- Guard the discovery result before indexing it, so an empty `find` reaches the
  existing `assert` and its diagnostic, instead of aborting on `files[0]`.
- Make the selection deterministic when more than one matching device is
  attached. `find` guarantees no ordering; today a second volume would make the
  pick nondeterministic and silent.
- Add two Molecule scenarios: one for the empty-discovery path, one for the
  multi-device path. The `default` scenario supplies `platform_data_volume_device`
  explicitly and never exercises discovery at all, so nothing in the suite has
  ever run the block being fixed — and without the second, a later revert to
  `files[0]` would pass every scenario there is.

**Consistency slips**

- Two roles document a caller-supplied input as having no safe default, consume it
  on every run, and say so only by failing inside the task that reads it.
  `hardening_ssh_allowed_cidrs` surfaces as an undefined-variable error from a UFW
  loop (`hardening/tasks/main.yml:30`) and `deploy_apps` as the same error from its
  own (`deploy_user/tasks/main.yml:48`) — in both cases after the role has already
  changed the host. Give each an assertion naming the variable and where to set
  it, placed before any task that acts. **No default value is introduced** — a
  default here would silently narrow or widen a firewall rule, or admit an
  unintended deploy key.

  `tailscale_auth_key` is the same *documented* pattern but not the same case, and
  is deliberately left alone: `tailscale/tasks/main.yml:84` consumes it only when
  the host is not already on the tailnet, so an already-joined host converges
  today without it. An unconditional assertion would be a regression, and the role
  carries no Molecule scenario to catch one. Queued, with its reasoning, rather
  than folded in.
- `platform/docker-compose.yml`'s `postgres:16` is the only floating image tag in
  the repository — PostgreSQL's release version is `MAJOR.MINOR`, so `16` is a
  series its publisher repoints at each new release. Pin it to `postgres:16.15`,
  the version prod is running today (read from `platform-postgres-1`), so the
  deploy is a restart of the same PostgreSQL version rather than an unannounced
  upgrade. Both tags were confirmed on 2026-09-07 to resolve to the identical
  manifest, so `16.15` is known to exist and to be what is running.
- `GF_SERVER_ROOT_URL: http://localhost:3000` is the base URL Grafana builds its
  own links and redirects from, and it is `localhost` while Grafana publishes on
  the literal tailnet address `platform-deploy.yml` already renders into `.env` as
  `GRAFANA_BIND_ADDRESS`. Confirmed live on 2026-09-07: the unauthenticated
  `/login` page's boot data reports `appUrl":"http://localhost:3000/"`. Address
  the root URL at the same value the port publication already uses.
- `ansible/inventory/group_vars/prod.yml:58-64` documents `ghcr_pull_username` /
  `ghcr_pull_token` but sits above `platform_data_volume_subdirs`; a later edit
  inserted a variable into the middle of a comment. Move the comment back to the
  variables it describes.
- `platform/docker-compose.yml:6-10` carries a caveat that the monitoring image
  tags were pinned without network access to confirm they resolve. All eight
  services the stack defines are running those exact tags in production and
  healthy, so the caveat is discharged by observation rather than restated.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-host-configuration`: the data-volume mount requirement gains scenarios for
  the absent-device and multiple-device cases it is silent on today; a new
  requirement states that a role's caller-supplied input with no safe default is
  reported by name when absent, rather than surfacing as whatever error the first
  task that touches it happens to raise.
- `iac-platform-services`: a new requirement that every shared-stack service image
  names an exact release rather than a tag its publisher repoints, mirroring the
  pinning obligation `iac-cicd-pipeline` already places on Molecule's platform
  images. Because which tags float is a property of the publisher and not of the
  tag's shape, the requirement splits the obligation — an automated check for the
  statically decidable necessary condition, human review for the rest — and says
  so rather than letting a check appear to establish the whole of it. The
  dashboard requirement gains two scenarios covering the base URL the interface
  builds its own links from.

## Impact

**Code**

- `ansible/roles/platform_data_volume/tasks/main.yml` — the discovery block.
- `ansible/roles/platform_data_volume/molecule/` — two new scenarios.
- `ansible/roles/hardening/tasks/main.yml` — one added assertion.
- `ansible/roles/hardening/defaults/main.yml` — the comment that records why there
  is no default.
- `ansible/roles/hardening/molecule/` — one new scenario.
- `ansible/roles/deploy_user/tasks/main.yml` — one added assertion.
- `ansible/roles/deploy_user/defaults/main.yml` — comment only: that the absence
  of a default for `deploy_apps` is now enforced by that assertion.
- `ansible/inventory/group_vars/prod.yml` — comment placement only.
- `platform/docker-compose.yml` — one image tag, one environment value, the
  header comment.
- `.github/tests/test_ci_configuration.py` — static assertions that no
  shared-stack service image names a tag with fewer than two version components,
  and that the dashboard's base URL is not a literal address. The first is a
  necessary condition, not the whole pinning obligation — see design.md
  Decision 7.
- `AGENTS.md` — the "Testing" section gains a Molecule row, so a test-authoring
  dispatch can place a role scenario without being told the pair by hand.
- `docs/change-queue.md` — two entries recorded rather than folded in, and one
  correction to an existing entry.

**Systems**

Editing `platform/docker-compose.yml` triggers `platform-deploy.yml` on merge to
`main`, which requires a `production` Environment approval and performs a real
deploy. Both Compose edits recreate their container: `platform-postgres-1` (a
restart on the same PostgreSQL version) and `platform-grafana-1`. The Ansible
edits deploy nothing on merge; they take effect at the next operator-run
`host-baseline.yml`.

The two new assertions change no host that is already configured correctly — both
pass on the values `ansible/inventory/group_vars/prod.yml` already supplies
(`hardening_ssh_allowed_cidrs` at line 17, `deploy_apps` at line 32). They change
what an operator sees on a host that is *not*, and they change it from a partial
application into a refusal.

**Not touched**

On-host device discovery stays (hand-copying Terraform's `linux_device` output
was considered and rejected). `platform_data_volume_device` keeps its `""`
default, which is the signal meaning "discover it". Grafana stays tailnet-bound
and off Traefik. The `65534:65534` / `472:472` subdirectory ownership values and
the mount-then-create task ordering are left alone.
