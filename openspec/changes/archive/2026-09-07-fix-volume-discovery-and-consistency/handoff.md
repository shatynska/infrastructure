# Handoff: fix-volume-discovery-and-consistency

No proposal yet. This records why the change was identified, what bears on it,
and what it must not undo. The session that takes it up writes the proposal.

Identified by a full-repository audit on 2026-09-06, trunk at `245ef59`.

## Why this was identified

One genuine defect, and a set of small consistency slips that the audit found
alongside it. Whether these travel as one change or two is the proposal's call
— the defect is the reason to act; the rest is cheap while the files are open.

### The defect: an assert that cannot be reached in its own headline case

`ansible/roles/platform_data_volume/tasks/main.yml:13-38` runs three tasks in
this order:

```yaml
- find: paths=/dev/disk/by-id patterns="scsi-0HC_Volume_*"   # register: ..._by_id
  when: platform_data_volume_device | length == 0

- set_fact:
    platform_data_volume_device: "{{ platform_data_volume_by_id.files[0].path }}"
  when: platform_data_volume_device | length == 0

- assert:
    that: [platform_data_volume_device | length > 0]
    fail_msg: "No ... device was found on this host. Is the main-data Hetzner
               Volume actually attached ...?"
```

When `find` matches nothing, `files` is an empty list and `files[0]` raises
`list object has no element 0` — the play aborts on the `set_fact`, and the
`assert` below never runs. The carefully-written diagnostic describes precisely
the situation it cannot report.

The failure it is meant to catch is a real one and not exotic: it is what a
host sees when `volume_enabled` is false in `terraform.tfvars`, or when the
volume has not finished attaching. The operator currently gets a Jinja index
error instead of the question they need to be asked.

Secondary, same task: `files[0]` has no guaranteed ordering. With one volume
attached this is invisible; with a second it becomes a nondeterministic pick.

### Consistency slips

- **`postgres:16` is the only floating image tag in the repository.**
  `platform/docker-compose.yml:75`. Traefik, Grafana, cAdvisor, node-exporter,
  postgres-exporter, Prometheus, Alertmanager, Tailscale and every Galaxy role
  pin exactly, and `AGENTS.md` mandates exact pinning for external
  dependencies. Postgres patch releases currently float in unannounced.
- **`GF_SERVER_ROOT_URL: http://localhost:3000`** (`docker-compose.yml:250`)
  while Grafana publishes on a literal tailnet address
  (`GRAFANA_BIND_ADDRESS`). Generated links, redirects and alert URLs point at
  the viewer's own localhost rather than at the host.
- **An orphaned comment block.** `ansible/inventory/group_vars/prod.yml:58-64`
  explains `ghcr_pull_username` / `ghcr_pull_token`, but now sits directly above
  `platform_data_volume_subdirs` — the variables it documents are at lines
  81-89. A later edit inserted a variable into the middle of a comment.
- **`hardening` asserts nothing about its required input.** Both roles follow
  the "no safe default, caller must supply" pattern, but
  `platform_data_volume` fails loudly on a missing value while `hardening`
  lets an absent `hardening_ssh_allowed_cidrs` surface as an undefined-variable
  loop error. Same class of variable, two different failure modes.

## What bears on it

- **The on-host discovery decision is deliberate.** The role discovers the
  device via `/dev/disk/by-id/scsi-0HC_Volume_*` rather than consuming
  Terraform's `linux_device` output, and that choice is reasoned in
  `openspec/changes/archive/2026-09-04-add-platform-monitoring/design.md`
  ("The volume's device path is discovered on-host"). The bug is in how the
  discovery result is handled, not in discovering.
- `ansible/roles/platform_data_volume/molecule/default/` already exists and its
  `verify.yml` is 228 lines. A container has no `/dev/disk/by-id` entry
  matching the pattern, so the empty-result path may already be exercisable
  there — check before assuming a new scenario is needed.
- `platform/docker-compose.yml:1-10` carries a caveat that the monitoring image
  tags were pinned without network access to confirm they resolve. If the
  proposal touches pins, that caveat is worth resolving or restating rather
  than silently inheriting.
- Grafana's root URL interacts with `platform-deploy.yml`'s "Resolve Grafana's
  tailnet bind address" step, which already resolves a literal IPv4 into
  `.env`. The same value is likely what the root URL wants.
- Changing `platform/docker-compose.yml` triggers `platform-deploy.yml` on
  merge, which needs a `production` Environment approval and performs a real
  deploy. The Compose-side items are not free the way the Ansible-side ones
  are; sequencing them matters.

## What it must not undo

- **On-host device discovery.** Do not "fix" this by hand-copying Terraform's
  `linux_device` output into inventory. That was considered and rejected.
- **The "no safe default" pattern.** `hardening_ssh_allowed_cidrs` and
  `tailscale_auth_key` correctly have no default; the fix for `hardening` is a
  clear assertion, never a default value that would silently narrow or widen a
  firewall rule.
- **`platform_data_volume_device` defaulting to `""` rather than being
  undefined.** `defaults/main.yml:9` explains why: empty string is the signal
  that means "discover it". Preserve that contract.
- **Grafana's tailnet-only binding.** `GRAFANA_BIND_ADDRESS` is a literal
  tailnet IPv4 and never `0.0.0.0`; a root-URL fix must not become a reason to
  publish Grafana more widely or route it through Traefik.
- **The subdirectory ownership values.** `65534:65534` for Prometheus and
  `472:472` for Grafana match each image's own default user so no `user:`
  override is needed. Leave them alone.
- **The mount-then-create ordering** in `tasks/main.yml`. The comment at the
  end of the file records why: a subdirectory created before the mount is
  shadowed by it.
