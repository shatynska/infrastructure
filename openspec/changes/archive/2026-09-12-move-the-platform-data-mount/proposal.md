## Why

The platform's data volume is named `main` and is mounted at `/mnt/main-data`. The two disagree because `rename-the-stacks-and-their-resources` renamed the volume and deliberately left the path alone — the on-host device is `/dev/disk/by-id/scsi-0HC_Volume_<id>`, keyed on the volume's id, so a volume rename costs no migration and no remount. That left the path behind, and it left a commitment: the `platform_data_volume` role's README, `ansible/inventory/group_vars/staging.yml`, two stacks' `terraform.tfvars`, `docs/bootstrap-a-new-host.md` and `.github/tests/test_a_second_environment.py` each carry prose saying the two differ **until `docs/change-queue.md` entry 64**; `terraform/stacks/main-staging/variables.tf` and two further `.github/tests` modules explain the divergence or carry the old path without naming the entry. This is that entry. Closing it is what makes `docs/naming-conventions.md` true of the mount path, and deleting those comments is part of the work rather than a tidy-up after it.

The debt is not only cosmetic. While the path and the volume disagree, every reader of either has to be told they are independent, and that explanation is currently spread across eight tracked files — three of them under `terraform/`, which is what makes this merge start a Terraform apply as well as a converge and a deploy.

## What Changes

- `platform_data_volume_mount_path` becomes `/mnt/main`, and with it the two bind mounts in `platform/docker-compose.yml`, the literals three `.github/tests` modules assert, and the Molecule scenarios of `platform_data_volume` and `swap` that name it.
- The role gains an obligation it does not have today: **removing the superseded `/etc/fstab` entry.** `ansible.posix.mount` with `state: mounted` adds the new entry and leaves the old one, so without this the device is persisted at two paths and remounts at both on the next reboot — invisible until then.
- **The removal removes the fstab entry and not the live mount.** A running Prometheus or Grafana holds a bind into `/mnt/main-data`, so an unmount would either fail on a busy target or be forced under a running service. `state: absent_from_fstab` (`ansible.posix` 1.6.2, already pinned) does exactly the narrow thing: it takes the reboot-time duplicate out and leaves the live mount alone. The deploy that follows releases the containers' hold on it; the mount itself persists until the next reboot, which no longer has an fstab entry to act on.
- Every comment committing this repository to entry 64 is deleted, and `docs/naming-conventions.md`'s banner drops 64 from the entries it is waiting on. **The banner itself stays**: entry 75 is still outstanding, and whoever archives *that* deletes it.
- `docs/change-queue.md` entry 64 is deleted in the archive commit.
- **Not a rename of the volume, and not a data migration.** The filesystem and its subdirectories live on the volume and travel with it; only the mountpoint moves.

**The change costs a platform-stack restart**, so Prometheus and Grafana are down for the window and the scrape gap is visible in the dashboards afterwards. It needs **a host converge and a platform deploy**, in that order, and it drags a no-op Terraform apply along with it because three of the comments being deleted live under `terraform/`. The ordering is the operator's to enforce — see `design.md`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-host-configuration`: *Platform Data Volume Is Mounted at a Fixed Host Path* gains the obligation that a **superseded** mount path is not left persisted across a reboot, stated so that satisfying it cannot require disturbing a service that currently holds the old path.
- `iac-safety-hardening`: *No Store on This Host Holds Data Requiring Backup* identifies two of the stores in its table by path — `/mnt/main-data/prometheus` and `/mnt/main-data/grafana`. Both move.

## Impact

**Ansible.** `ansible/roles/platform_data_volume/` — `defaults/main.yml`, `tasks/main.yml`, `README.md`, and the `default` and `multiple-devices-discoverable` Molecule scenarios. `ansible/roles/swap/molecule/default/verify.yml`, whose `swap_forbidden_prefix` is the data volume's mount path. `ansible/inventory/group_vars/production.yml` and `staging.yml` gain the new input; only `staging.yml` carries a comment to delete.

**Terraform.** `terraform/stacks/main-production/terraform.tfvars`, `terraform/stacks/main-staging/terraform.tfvars` and `terraform/stacks/main-staging/variables.tf` each explain the divergence or name entry 64. They are comments and a variable description, so the plan is a no-op — but the merge is inside `apply.yml`'s path filter, which is the third gated production approval this change asks for and is accounted for in `design.md`'s migration plan rather than met on the day.

**Platform.** `platform/docker-compose.yml` — Prometheus's and Grafana's bind mounts, and the comment in Prometheus's `configs:` note that names `/mnt/main-data` as its only bind mount. Touching this file puts the merge inside `platform-deploy.yml`'s path filter, which is intended here: the deploy is what moves the running containers onto the new path.

**Static tests.** `.github/tests/test_ci_configuration.py`, `test_a_second_environment.py` and `test_a_stack_and_its_environment_are_named_separately.py` each assert the old path as a literal or explain in prose why it differs from the volume's name.

**Documentation and specs.** `docs/bootstrap-a-new-host.md` §1.1 and its §6.4 check line; `docs/naming-conventions.md`'s banner; `openspec/specs/iac-safety-hardening/spec.md`'s durability table. `docs/review-2026-09-08-host-readiness.md` records what was observed on a date and is **not** edited.

**Operations.** Three runs on the merge — a Terraform apply, a host converge and a platform deploy, the first two fanning out per stack — carrying three gated production jobs between them. Staging's two jobs are unattended; production's three are separate approvals rendering identical prompts — `docs/change-queue.md` entry 77 — separable by workflow. Only one ordering among them matters, and the apply's plan summary is read before its approval rather than after. `design.md`'s migration plan is where that is stated.

**Not in scope, recorded instead.** `ansible/roles/swap/defaults/main.yml` and its `README.md` call the volume `main-data`, which is its retired *name* rather than the mount path — rot from entry 62 that nothing owns. They are added to `docs/change-queue.md` entry 74, which is exactly that entry's subject, rather than folded in here.
