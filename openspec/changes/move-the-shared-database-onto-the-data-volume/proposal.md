## Why

The shared PostgreSQL instance is the only platform store that grows with what applications do and is not on the volume provisioned for platform data. Prometheus and Grafana were moved onto `main` when the volume was first mounted; `postgres_data` and `traefik_letsencrypt` stayed on the root disk, not by decision but because `add-platform-monitoring` declared moving them a Non-Goal and nothing has revisited it since. The operator wants the shared instance on the volume, intends to add a backup of it afterwards, and observes that the instance holds no durable data — `commerce-ops`'s database there is early and experimental, and the requirement that keeps that instance non-durable is unconditional rather than a description of today.

The move is worth making while the store is 70 MB and one application uses it. Every application onboarded afterwards makes the copy longer and the window it needs harder to schedule.

## What Changes

- The shared PostgreSQL instance's data moves from the Docker named volume `postgres_data`, on the host root disk, to a bind mount at `/mnt/main/postgres` on the attached Hetzner volume — the same volume Prometheus and Grafana already use.
- `platform_data_volume` creates that subdirectory on each host, owned by the PostgreSQL image's own user, the way it already creates Prometheus's and Grafana's.
- `platform/docker-compose.yml` binds the host path in place of the named volume, and stops declaring `postgres_data`.
- **The shared instance leaves the coverage of the server's automatic backups**, which are the root disk only. Nothing about its classification changes — it needs no backup either way — but the store table that records that classification names a store which will no longer exist, and the trade-off is recorded rather than left for a reader to derive.
- The existing data is copied to the new location by an attended operator step between two pull requests, so that no application's database has to be re-provisioned. The old named volume is left in place as the fallback and removed later.

Not in scope: `traefik_letsencrypt`, which is 48 KB, re-issued on demand and has no reason to move; the backup the operator intends to add, which is a change of its own and is not a precondition for this one; and any change to what the shared instance is permitted to hold.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-safety-hardening`: *No Store on This Host Holds Data Requiring Backup* — the store table's row for the shared instance names `postgres_data` / `platform_postgres_data`, which this change removes. The row is restated against the new location, and the rationale gains what the move costs: this store passes out of the root-disk snapshot's reach.
- `iac-platform-services`: *A Destructive Window on the Shared Instance Is Announced to the Applications That Hold Databases in It* — its body and one of its scenarios trigger on the instance's **volume** being discarded. After this change no such volume exists, so the announcement obligation would stop binding on the procedure that replaces it — the quietest way for it to lapse. Both are restated against the store rather than its form.

## Impact

- `platform/docker-compose.yml` — the `postgres` service's `volumes:`, and the top-level `volumes:` declaration.
- `ansible/inventory/group_vars/production.yml` and `ansible/inventory/group_vars/staging.yml` — a third `platform_data_volume_subdirs` entry each.
- `openspec/specs/iac-safety-hardening/spec.md`, `openspec/specs/iac-platform-services/spec.md` and `openspec/specs/iac-host-configuration/spec.md` — one requirement each, by delta. The third is the mirror of the second: *The Host Carries an Operator-Declared Maintenance Window for the Shared Instance* obliges the declaration to live "outside the volume whose discarding is the window", and its scenario triggers on that volume being removed — the same form-dependence, in the capability that provides the mechanism rather than the one that obliges its use.
- `.github/tests/` — `test_ci_configuration.py`'s `CLASSIFIED_STACK_STORES` and its postgres-mount check, `test_a_shared_instance_reset_is_visible.py`'s reading of the reset recipe, and a new assertion that the two sides agree.
- `docs/backlog.md` — one entry describes the store in the present tense and becomes false when this change lands; it is corrected. A second, recording what staging held on a date, is exempted with its reason, as is `ansible/roles/deploy_user/molecule/probe-and-window/verify.yml`, which stands up a store of its own rather than describing this stack's. Each exemption is stated where it is declared rather than being an omission.
- Both hosts, by an attended operator step. The copy itself is seconds at 70 MB, but the instance stays stopped from its copy until the second pull request's deploy reaches that host — across that pull request's checks, the merge, staging's deploy and its verification, and then production's Environment approval. On production that is `commerce-ops` offline for the whole of it, since its database lives in this instance; `design.md` sizes the window and says why copying production later, which would shorten it, is refused.
- Nothing in `terraform/`. The volume is provisioned and attached already, and 949 MB of 9.8 GB is in use on the fuller of the two hosts.
