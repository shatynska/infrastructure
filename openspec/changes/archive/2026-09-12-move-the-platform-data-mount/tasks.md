## 1. The role gains the retirement capability

- [x] 1.1 Add `platform_data_volume_superseded_mount_paths: []` to `ansible/roles/platform_data_volume/defaults/main.yml`, with a comment saying what an entry means, that empty is the ordinary state, and that it never unmounts; verify `ansible-lint ansible/` is clean
- [x] 1.2 Add to `ansible/roles/platform_data_volume/tasks/main.yml`, in this order (**the read-back was added during code review**, to discharge the delta's obligation that the converge establish the retirement rather than assume it — `absent_from_fstab` reports no change both when there was nothing to remove and when there was something it could not match): an `assert` **before any task that acts on the host** that no declared superseded path equals `platform_data_volume_mount_path`, comparing both sides with a trailing separator stripped so that `/mnt/main/` cannot slip past, and with a `fail_msg` naming the path and both inputs it was read from — the role's existing device assert is the idiom; **after** the mount task so a run that fails earlier has not half-retired anything, a loop over the input with `ansible.posix.mount` `state: absent_from_fstab`, normalising the item the same way; and after that a read-back of `/etc/fstab` asserting no declared path survives, skipped under `--check` because `slurp` runs there and the removal correctly does not. Verify the play parses with `ansible-playbook --syntax-check` on the host-baseline playbook
- [x] 1.3 Add the new input's row to `ansible/roles/platform_data_volume/README.md`'s variable table, and reword its "Four Molecule scenarios cover this" line so it reads as four of the role's scenarios covering *discovery* rather than as a count of the role's scenarios; verify the table has one row per variable in `defaults/main.yml`

## 2. The path moves

- [x] 2.1 Change `platform_data_volume_mount_path` to `/mnt/main` in `ansible/roles/platform_data_volume/defaults/main.yml` **and in `README.md`'s variable table row**, deleting the divergence prose from the README row while keeping its statement that the path and the volume's name are independent by construction, which stays true. `defaults/main.yml` carries no divergence prose but its comment attributes the path to `add-platform-monitoring`'s design as an example, which it no longer is — reword or drop that attribution rather than leaving it on a value it does not describe. verify no `/mnt/main-data` remains anywhere under `ansible/roles/platform_data_volume/` outside `molecule/` and the superseded-path declaration
- [x] 2.2 Set `platform_data_volume_superseded_mount_paths: ["/mnt/main-data"]` in `ansible/inventory/group_vars/production.yml` and `staging.yml`, identically and **in the inline flow form on one line** — the sweep exempts the needle only on a line beginning with that key, so a block sequence puts the value where nothing exempts it; verify both files parse as YAML, declare the same value, and are green under the sweep
- [x] 2.3 Delete the divergence explanation from `ansible/inventory/group_vars/staging.yml`'s `platform_data_volume_subdirs` comment and repoint the two example paths in the half that is kept — it names `/mnt/main-data/prometheus` and `/mnt/main-data/grafana` as the paths both stacks share; verify the only remaining `/mnt/main-data` in that file is task 2.2's declaration line, and that `production.yml`'s equivalent comment needed no edit
- [x] 2.4 Repoint Prometheus's and Grafana's bind mounts in `platform/docker-compose.yml` to `/mnt/main/prometheus` and `/mnt/main/grafana`, and correct the comment in Prometheus's `configs:` note that names its only bind mount; verify `docker compose -f platform/docker-compose.yml config --quiet` parses
- [x] 2.5 Change `swap_forbidden_prefix` to `/mnt/main` in `ansible/roles/swap/molecule/default/verify.yml`, **and the comment on the line above it, which carries the path as a literal** — that file only; `defaults/main.yml` and `README.md` name the volume's retired *name*, not the path, and are task 4.4's to record rather than to fix. Verify the verify-file's own comment still names the file the value is derived from
- [x] 2.6 Delete the divergence prose and the entry-64 commitment from `terraform/stacks/main-production/terraform.tfvars`, `terraform/stacks/main-staging/terraform.tfvars` and `terraform/stacks/main-staging/variables.tf`, correcting `variables.tf`'s description to the new path. **`main-staging/terraform.tfvars` names entry 64 without naming any path, so the sweep cannot catch a miss here — it is read by eye or not at all.** verify `terraform fmt -check` and `terraform validate` pass in both stack directories and that `terraform plan` reports no resource changes

## 3. Tests

- [x] 3.1 Update the mount-path literal in the `default` and `multiple-devices-discoverable` Molecule scenarios of `platform_data_volume`, and the `default` scenario's converge comment; verify `ansible/scripts/run-molecule test --all` from `ansible/roles/platform_data_volume` names all **six** of the role's scenarios in its SCENARIO RECAP
- [x] 3.2 **Written — `superseded-path-retired` and `superseded-path-in-force-refused`, derived from the delta before any implementation existed.** Two scenarios rather than the one this task first called for: the refusal SHALL happen before any task that changes the host has run, and that is only observable against a host nothing has yet converged, so a converged host could not tell a refusal before the mount from one after it. Between them they carry the four limbs, the loop-device fixture that exercises the double-mount of one device, and the `idempotence` action standing in for the already-retired steady state. Verify both are red against the role as it stands and green once task 1.2 lands
- [x] 3.3 **Written — `TestEveryHostVolumeBindLiesUnderTheMountTheRoleEstablishes` in `.github/tests/test_the_platform_data_mount_moved.py`, green already because it reads two literals that still agree.** It asserts that every host bind mount in `platform/docker-compose.yml` whose source begins `/mnt/` lies under the role's default `platform_data_volume_mount_path`, comparing containment **on path components** via `test_ci_configuration.py`'s existing `_under` helper and not on a string prefix — `/mnt/main` is a proper prefix of `/mnt/main-data`, so a `startswith` check is green in the one state this exists to catch. The ten runtime observation mounts (`/`, `/proc`, `/sys`, `/var/run`, `/var/lib/docker/`, the two sockets) must fall outside its reach by construction rather than by enumeration. **A second assertion added in code-review round 3** holds the premise that check rests on: no inventory file overrides `platform_data_volume_mount_path`, since the check reads the role's default while a host mounts at whatever inventory supplies — and those files already override two of this role's other inputs. Verify it is red against a compose fixture naming `/mnt/main-data/prometheus` with the role's default at `/mnt/main`, and red when either committed literal is changed alone
- [x] 3.4 **Written — the sweep in the same module, red with 18 occurrences across 9 files, each reported as `path:line`.** It sweeps tracked files, exempting the `openspec/` and `.github/tests/` prefixes, the whole path `docs/review-2026-09-08-host-readiness.md`, the expiring whole-path exemption for `docs/change-queue.md`, and — scoped to a line rather than a file — any occurrence whose line, **with leading whitespace stripped**, begins with the key `platform_data_volume_superseded_mount_paths:`, each carrying its stated reason. Verify a synthetic tree naming the path is reported; that an *indented* declaration is exempt while indented prose naming the path is not; that prose elsewhere in a file carrying that declaration is still reported; that an exemption naming a path without the needle is itself an offence; and that the sweep reaches `terraform/`, `platform/` and `docs/` through named anchors
- [x] 3.5 Update the `.github/tests` modules that carry the old path as a literal or explain the divergence in prose — `test_ci_configuration.py`, `test_a_second_environment.py`, `test_a_stack_and_its_environment_are_named_separately.py`. **All three sit inside the sweep's own exempt prefix, so none of them is caught by it** — `test_a_second_environment.py`'s entry-64 commitment in particular is read by eye. verify `python3 -m unittest discover --start-directory .github/tests` is green from the repository root

## 4. Documentation

- [x] 4.1 Update `docs/bootstrap-a-new-host.md` at its two occurrences — the §1.1 note about a second stack in one project needing a different mount path, and the §6 check line listing what a converged host holds — deleting the clauses that say the path and the volume's name differ until entry 64, and leaving §1.1's separate statement that the two are *independent*, which stays true. Verify no `/mnt/main-data` remains in that file
- [x] 4.2 Amend `docs/naming-conventions.md`'s banner so it waits on entry 75 alone, and leave the banner standing; verify the banner still says who deletes it
- [x] 4.3 Confirm `docs/review-2026-09-08-host-readiness.md` is unedited and is exempted by the sweep with its reason stated; verify the sweep is green with that file present
- [x] 4.4 Add `ansible/roles/swap/defaults/main.yml:14` and `ansible/roles/swap/README.md:28` to `docs/change-queue.md` entry 74's list of stale names, saying they name the volume `main` by its retired name `main-data`; verify entry 74 still reads as one list of the same kind of rot

## 5. Verification before the pull request

- [x] 5.1 Run `python3 -m unittest discover --start-directory .github/tests` from the repository root and confirm it is green
- [x] 5.2 Run `ansible/scripts/run-molecule test --all` from `ansible/roles/platform_data_volume` and from `ansible/roles/swap`, and confirm each SCENARIO RECAP names every scenario that role has — six for `platform_data_volume`
- [x] 5.3 Run `pre-commit run --all-files` and confirm it is clean
- [x] 5.5 Dispatch the change's code review over the diff and act on its findings

## Not performed

- 5.4 Run `terraform plan` in both stack directories under the read-only token and confirm each reports no resource changes.
  Reason: this working tree carries tracked files only — no `.envrc`, and no read-only Hetzner token in the environment — and that token is a secret this session does not hold, so the step could not be provisioned rather than being declined on judgment. `terraform fmt`, `tflint` and `terraform validate` did run, through `pre-commit`, and the change's only `terraform/` edits are three comments and one variable `description`. The plan that actually governs is the pipeline's own `plan (main-production)`, which task 6.5 already requires be read before that apply is approved — so the evidence this step would have produced is obtained there rather than lost.

## 6. Ship

- [x] 6.1 Open the pull request, its description carrying the migration plan's job table — three runs, three gated production jobs — and saying that the converge is approved before the deploy, that the apply's plan summary is read before its own approval, and what a wrong order costs
- [x] 6.2 After merge, read staging's unattended converge: the mount at `/mnt/main`, no `/mnt/main-data` in its `/etc/fstab`, `changed` non-zero on this run
- [x] 6.3 Approve **production's Host Converge** and wait for it to finish green — read the workflow name on the prompt, not the Environment, because the apply and the deploy render the same prompt
- [x] 6.4 Approve **production's Platform Deploy** and wait for it to finish green
- [x] 6.5 **Read the Terraform Apply run's plan summary for `main-production` and confirm it reports no resource changes — then approve that job.** The plan is published before the approval is requested, so there is no reason to approve it unread, and *Gated Production Apply Applies the Reviewed Plan* (`openspec/specs/iac-cicd-pipeline/spec.md`) names an approval granted with nothing read as the harm the two-job split exists to prevent. It may be granted before, between or after 6.3 and 6.4; expect the state serial to move even though nothing changes
- [x] 6.6 Confirm the effect on the production host: `/mnt/main` mounted and holding `prometheus/` and `grafana/`, `/etc/fstab` naming `/mnt/main` and not `/mnt/main-data`, Grafana serving its dashboards with a scrape gap covering the window; record the operator's confirmation in this change's artifacts

## Effect confirmed

Merged as PR #158 on 2026-09-12. All three runs green; staging's converge ran
unattended and moved its mount first, as the rehearsal.

Observed on the production host after the platform deploy, and confirmed by the
operator:

- `/etc/fstab` names `/dev/disk/by-id/scsi-0HC_Volume_106651381 /mnt/main ext4`
  and **no other `/mnt` path**. The two-paths-at-boot state entry 64 warned
  about is closed, and the role's own read-back assert ran and passed against
  the real host.
- `findmnt` shows `/dev/sdb` at **both** `/mnt/main` and `/mnt/main-data`. That
  is the expected steady state, not residue: the converge never unmounts a path
  a running service holds, and the lingering mount has no `/etc/fstab` entry
  behind it, so the next reboot ends it and does not restore it.
- `/mnt/main` holds `prometheus/` (65534) and `grafana/` (472), and
  `lost+found` — the volume's own filesystem, not a directory created on the
  root disk.
- Both containers bind the new path: `/mnt/main/prometheus -> /prometheus` and
  `/mnt/main/grafana -> /var/lib/grafana`, each `Up (healthy)`. The other six
  platform containers were not restarted.
- **The data travelled rather than being recreated.** Prometheus's TSDB blocks
  are the same ones (oldest `01M1V60EQSDKQNZQ0V9BGK0F63`) and `grafana.db` is
  1.6 MB and being written to. An empty store here is what a deploy approved
  before the converge would have produced, and it is what this confirms did not
  happen.
- The operator confirmed Grafana renders its dashboards, with the scrape gap
  covering the restart window.

**Terraform's plan was a no-op, as predicted**: `No changes. Your infrastructure
matches the configuration.` for production, and `0 added, 0 changed, 0
destroyed` for staging's unattended apply. That is the evidence task 5.4 could
not produce locally, obtained where it actually governs.

**No waiver is claimed.** The effect was observable, was observed, and is
recorded above.

## 7. Archive

- [x] 7.1 Bring the branch back to the freshly fetched trunk and delete `docs/change-queue.md` entry 64
- [x] 7.2 In that same commit, delete the sweep's `docs/change-queue.md` exemption, which the deletion above expires; verify `python3 -m unittest discover --start-directory .github/tests` is green only after both edits
- [x] 7.3 Run `openspec archive` and read every `## Purpose` it touched by hand — it reports `→ 0` and leaves them untouched
- [x] 7.4 Open the record's own pull request

**After that pull request merges**, and recorded in prose because no task in this file can be ticked after the commit that writes it: the branch and the working tree are removed, locally and on the remote, from the repository's main working tree rather than from inside the tree being removed. Nothing reclaims this tree's Molecule namespace — `.molecule-home/` goes with the tree, and any container it left is named `*-move-the-platform-data-mount-bb2c0c` and can be removed by name. Its two loop-device minors, 90 and 91, are kernel-global and outlive the tree; `docs/change-queue.md` entry 78 carries that.

**Both `## Purpose` sections `openspec archive` touched were read by hand** — `iac-host-configuration` and `iac-safety-hardening`. It reported `→ 0` and changed neither, as it has in every change running now. Both are accurate as they stand and needed no edit.
