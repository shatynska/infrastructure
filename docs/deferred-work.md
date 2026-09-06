# Deferred work

What this project has deliberately not done, and why. An entry is deleted when
it stops being true. See `AGENTS.md`, "A second change surfacing".

These came out of the full-repository audit on 2026-09-06 (trunk at `245ef59`).
Each was identified as a real observation and then deliberately **not** turned
into a change. Work that is merely waiting on something else belongs in
`docs/change-queue.md`, not here.

---

## Splitting `platform/docker-compose.yml` into multiple files

The file is 602 lines and holds, inline, the Prometheus scrape config, seven
alerting rules, the Alertmanager routing tree, and three Grafana dashboards as
embedded JSON. Editing dashboard JSON inside a YAML `configs:` block inside a
Compose file is genuinely unpleasant, and nothing validates that JSON.

It stays one file because of a deliberate security control, not inertia.
`deploy-receive` (`ansible/roles/deploy_user/tasks/main.yml:73-85`) extracts a
**fixed, explicit two-member list** — `docker-compose.yml` and `.env` — from the
tar it receives. GNU tar with named members extracts only those names and
ignores everything else the archive contains. That is what bounds what a
holder of the platform deploy key can write onto the host.

Carrying additional files would mean widening that member list, and every entry
added to it is a new path an attacker with that key could write to. The
editability gain does not pay for weakening the control.

**Revisit if** the stack outgrows what one file can reasonably hold, or if a
mechanism appears that adds files without widening what the forced command
accepts (a checksummed bundle unpacked into a fixed subdirectory, say). Until
then this is the intended shape, and the inline JSON is its accepted cost.

## Separating `rebuild_protection` from `delete_protection` in `modules/server`

`terraform/modules/server/main.tf:53-54` drives both Hetzner flags from the
single `delete_protection` variable. They are distinct capabilities and a
consumer could in principle want one without the other.

No consumer does. There is one environment, and it wants both. Splitting them
adds a variable, a validation and a test for a case that does not exist, and
the coupled default is the safer one. **Revisit when** a second environment
actually needs them apart — most likely the anticipated staging environment,
which may want rebuild without delete protection.

## Generating Ansible's CIDR variables from Terraform

`ansible/inventory/group_vars/prod.yml:17-20` hand-mirrors
`terraform/environments/prod/terraform.tfvars`'s `ssh_allowed_cidrs` and
`web_allowed_cidrs`. These have drifted once already, and the file's own
comment records what that cost: UFW rules assumed `web_allowed_cidrs` was
unset when it was in fact `["0.0.0.0/0"]`, which would have left the host
firewall blocking traffic the cloud firewall already permitted.

Deriving them from Terraform output would remove the drift class entirely, and
is deliberately not done: it would make an Ansible run depend on Terraform
state and an HCP Terraform token, coupling the two layers that this
repository's structure exists to keep separate. The reasoning is recorded in
`ansible/roles/hardening/README.md`; it is repeated here because the audit
re-surfaced the drift risk as live rather than settled.

**Revisit if** it drifts a second time. One recurrence is evidence the manual
sync does not hold, and would outweigh the coupling objection.

## Host-key verification on the platform deploy

`.github/workflows/platform-deploy.yml:157` runs `ssh-keyscan` into
`known_hosts` on every run — trust-on-first-use, every time, which verifies
nothing about the host's identity.

Accepted, because the connection it protects is already bounded by something
stronger: the runner reaches the host only over the tailnet, having
authenticated to it with an OAuth client scoped to the `production`
Environment, and the key it presents is restricted to a forced command that
accepts no other invocation. An attacker positioned to answer that keyscan is
already inside the tailnet.

**Revisit if** the deploy ever runs over the public internet, at which point
this stops being defence-in-depth and becomes the only check.
