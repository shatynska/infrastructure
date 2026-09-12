## Context

See `proposal.md` — *Why*. What shapes the approach is not the rename itself, which is a literal, but three facts about the host at the moment the literal moves.

**The device is already mounted, and running containers hold it.** Prometheus and Grafana bind-mount `/mnt/main-data/prometheus` and `/mnt/main-data/grafana`. A bind mount is established in the container's own mount namespace when the container is created, so the host's mount at `/mnt/main-data` is *busy* for as long as those containers run — an unmount either fails on a busy target or, if forced, pulls the filesystem out from under a running service.

**The converge and the deploy are separate gated workflows with no ordering between them.** `host-converge.yml` triggers on a merge touching `ansible/`; `platform-deploy.yml` triggers on one touching `platform/`. A single merge touching both starts both, concurrently, each with its own approval on the production Environment. Nothing in either workflow makes one wait for the other.

**Three of the comments being deleted live under `terraform/`.** `terraform/stacks/main-production/terraform.tfvars`, `terraform/stacks/main-staging/terraform.tfvars` and `terraform/stacks/main-staging/variables.tf` each explain the divergence or name entry 64. `apply.yml` triggers on `terraform/**`, so editing them adds a third gated production run to the merge. That is a cost this design accepts rather than an oversight; Decision 4 weighs it.

**Staging has the volume but not the stack.** `ansible/inventory/group_vars/staging.yml` declares `platform_data_volume_subdirs`, so staging's host mounts the volume and creates the subdirectories; `platform-deploy.yml` names one literal Environment and deploys to production only (`docs/change-queue.md` entry 52 is the change that would give staging a stack). So staging's converge is ungated, runs unattended on the merge, and exercises the whole mount move against a host where nothing holds the old path.

## Goals / Non-Goals

**Goals:**

- The path moves, and after the converge the host persists the volume at `/mnt/main` and at nothing else.
- The move is safe to perform on a host whose services are *running on the old path at that moment* — the converge does not depend on them being stopped, and does not stop them.
- The role gains the retirement as a **capability** rather than as a hardcoded fact about this repository's history, so the same obligation is dischargeable the next time a path moves.
- Nothing in the tree still explains why the volume's name and its mount path differ, because they no longer do.

**Non-Goals:**

- Zero downtime. The platform stack restarts; Prometheus and Grafana are down for the window and the scrape gap is visible afterwards. Buying that back is not worth what it costs here.
- Removing the *live* `/mnt/main-data` mount. Nothing in this change unmounts it: it persists until the next reboot, which has no fstab entry left to act on. See Decision 2.
- Parameterising `platform/docker-compose.yml`'s bind mounts per stack. `docs/bootstrap-a-new-host.md` names that as a thing a second stack in one Hetzner project would force; no second stack is in one project, and folding it in here would be scope this change did not set out to cover.
- Touching the volume's name or the `volume_name` each stack declares. `terraform/` *is* edited, but only comments and one variable description — no resource argument changes and the plan is a no-op.
- Correcting prose that names the volume by its retired **name** rather than by the mount path. `ansible/roles/swap/defaults/main.yml` and its `README.md` both say `main-data` where they mean the volume `main`; that is rot from entry 62 which nothing owns, and it is added to `docs/change-queue.md` entry 74 rather than folded in. Sweeping the bare name here would take that entry's work without planning it.

## Decisions

### 1. `state: absent_from_fstab`, not `state: absent`

`ansible.posix.mount` offers `absent`, `absent_from_fstab`, `unmounted`, `mounted`, `present`, `remounted` and `ephemeral` at the version this repository pins (`ansible.posix` 1.6.2 — the choices list is in the module's own argument spec). Only `absent_from_fstab` edits `/etc/fstab` **without** touching the live mount.

That is the whole reason it is chosen. `absent` unmounts, removes the fstab entry and removes the mountpoint directory; against a path a running Prometheus holds, the unmount is the failure mode this change most needs to avoid — either the converge goes red on a busy target, or it succeeds and a running service loses its filesystem. `unmounted` has the same problem and leaves the fstab entry, which is the defect being fixed. A `lineinfile` against `/etc/fstab` would work and is rejected: it re-implements the module's parsing of a file where a mistake is a host that does not boot.

**Alternative considered: do nothing and let a rebuild clear it.** Rejected — that is exactly the trap `docs/change-queue.md` entry 64 names. The two-path state is invisible on a running host and arrives at a reboot months later, and a rebuilt host inherits `/etc/fstab` from the converge rather than from the old host, so a rebuild would clear it only by accident.

### 2. The live mount at the old path is left to be shed, not unmounted

After the converge, the device is mounted at both `/mnt/main` (new, in fstab) and `/mnt/main-data` (live, no longer in fstab). Both are the same filesystem, so nothing disagrees about content.

**The deploy releases the containers' hold on the old path; it does not unmount it.** A container's bind mount is a copy of the host's mount into that container's own namespace, so recreating Prometheus and Grafana against `/mnt/main` drops their reference — and with it the `EBUSY` that reference would cause — while the host's own mount of the device at `/mnt/main-data` stays exactly where it was. Nothing in this change runs `umount`, so that mount survives until the next reboot, which finds no fstab entry for it and does not bring it back. A `findmnt` taken after the deploy therefore shows two mounts of one device, and that is the expected steady state until the host reboots rather than a sign the change is incomplete.

This is deliberately weaker than "the old path is gone when the converge finishes", and the specification states it that way: the obligation is on what the host mounts **at boot**. Making the stronger claim would require the converge to reach into the container runtime, which *Configuration Scope Stops at the Container Runtime* forbids.

**What this leaves behind after that reboot:** an empty `/mnt/main-data` directory on the root disk, which nothing removes. It is four bytes of inode and is left rather than added to the role as a second cleanup task with its own failure modes.

### 3. The superseded paths are inventory, not a literal in the role

The role takes a new input:

```yaml
platform_data_volume_superseded_mount_paths: []
```

defaulting to empty, and each environment's `group_vars` file supplies `["/mnt/main-data"]` — `production.yml` and `staging.yml`, identically and on purpose, which is exactly how `platform_data_volume_subdirs` is already carried and for the same reason: both hosts mounted at the same path, so both have the same entry to retire.

**Not `group_vars/all.yml`**, though it is the file that covers both groups in one line. That file says of itself that it holds one thing and is meant to — `company`, the single value a different company's clone changes — and a fleet-historical path is not that thing.

**Why not hardcode `/mnt/main-data` in the role's task.** The role would then carry a fact about one repository's history, a new deployment built from this template would inherit a task naming a path it never had, and the next path move would edit the task rather than the inventory. As an input it is testable against arbitrary paths, it empties when the fleet stops needing it, and the role states a capability the specification can be written against.

**Why not a single `platform_data_volume_superseded_mount_path` string.** A list costs nothing now and is what a second move would need. An empty list is also the honest default for a fresh host, where a string default would have to be `""` and be length-tested.

**Alternative considered: keep the task permanent and remove it later in a cleanup change.** Rejected as the default: a task that must be remembered to be removed is the same shape of debt this entry is paying off. The list makes the removal an inventory edit with nothing to remember — and if it is never emptied, the cost is one no-op task per converge.

### 3a. A declaration naming the path in force refuses, rather than being filtered

The retirement loop runs *after* the mount task, so a superseded list containing the fixed path would mount the device, write its `/etc/fstab` entry, and then delete that entry — a host that converges green, passes `findmnt`, serves every container, and comes up at the next boot with no data volume mounted and Prometheus and Grafana bound to empty root-disk directories. It is the defect this change exists to prevent, arrived at from the other side, and it is equally invisible on a running host.

So the role asserts it and fails before touching anything, in the idiom it already uses for an undiscoverable device. **The comparison normalises a trailing separator on both sides**, because the one bypass of a guard like this is a near-miss spelling — `/mnt/main/` against `/mnt/main` — and what lies past the bypass is the catastrophic outcome the guard exists to prevent, arrived at with nothing said about which way it went. **Not by filtering the fixed path out of the list**, which is the tempting one-liner: that converges a contradictory declaration cleanly and hides the inventory mistake that produced it, and a mistake that converges is one nobody fixes. **Not by moving the retirement ahead of the mount either** — that would mask the case for this change's own forward run while leaving a genuinely two-path host unrepaired whenever the mount fails, and it costs the property the current order was chosen for, that a run failing early has not half-retired anything.

The nearest way in is not hypothetical: the rollback below has the operator point the list at `/mnt/main` while reverting the path to `/mnt/main-data`, and the adjacent slip — reverting the path and leaving the list — is exactly this state, reached under time pressure.

### 4. One pull request, ordered at the approval gates

The implementation lands in a single pull request touching both `ansible/` and `platform/`, and the operator approves **the converge first, then the deploy**.

The two workflows start together and both wait on the production Environment, so the approval order *is* the execution order. Staging's converge is ungated and runs unattended, which makes it the rehearsal: read it before approving production's, as `docs/bootstrap-a-new-host.md` §6.6 already instructs.

**The merge starts three runs, and three gated jobs sit inside them.** `apply.yml` triggers on `terraform/**` and the three comment corrections are under it, so a Terraform apply joins the converge and the deploy. Each workflow runs **once** — `apply.yml` with two per-stack matrices, `plan (<stack>)` and `apply (<stack>)`, `host-converge.yml` with one, `converge (<stack>)` — so `gh run list` shows three entries and cannot tell staging's jobs from production's; the per-stack distinction is inside each run's job list. Staging's apply job and staging's converge job run unattended; production's apply, converge and deploy each raise an approval, and `docs/change-queue.md` entry 77 has just recorded that those three prompts are indistinguishable from one another because they all gate on the same Environment. The prompts *are* separable by workflow, which is why the plan names the workflow at each approval rather than the count.

**The extra apply raises a prompt this repository has a rule about, and the rule is not discharged by the ordering argument.** *Gated Production Apply Applies the Reviewed Plan* (`openspec/specs/iac-cicd-pipeline/spec.md`) structures the apply as a plan job that publishes the diff to the run summary and an apply job gated afterwards, precisely so the approver sees what will be applied — and it names, by name, the harm of a prompt with nothing to approve: it trains the approver to grant without reading. This change manufactures exactly such a prompt, so the plan summary is read **before** that approval, not after it. That is free — the plan is already published by the time the request is raised — and it is a different property from the ordering constraint below, which is about *when* relative to the other two runs. Only the ordering is argued for; approving unread is not licensed by it.

The only ordering constraint among the three is converge-before-deploy. The apply is a comment change whose plan is a no-op, and once its summary has been read it may be approved at any point.

**Why not split into two pull requests to make the ordering structural.** It was seriously considered, because `docs/change-queue.md` entry 77 has just recorded that these approval prompts are indistinguishable from one another, and relying on an operator to order two identical prompts is precisely the hazard that entry names. What decided it the other way is the window a split creates: between PR 1's converge and PR 2's deploy, production's stack definition still names `/mnt/main-data`, which is live-mounted but no longer in fstab — so a **reboot** in that window brings Prometheus and Grafana up bound to an empty directory on the root disk, with the real data on an unmounted volume. A split trades a bounded, attended ordering risk for an unbounded, unattended one.

**What a wrong order costs, so that it is weighed rather than assumed away.** If the deploy is approved first, Compose binds `/mnt/main/prometheus`, which does not exist yet; Docker creates it as an empty root-owned directory on the root disk, and Prometheus and Grafana come up empty. The converge then mounts the volume over `/mnt/main`, shadowing those directories while the containers keep writing to the shadowed ones. It is loud — no metrics, an empty Grafana — and the repair is to re-run the platform deploy once the converge is green. No data is lost: the real filesystem is on the volume throughout.

**Why not a third pull request that retires the old fstab entry after the deploy.** That removes the window entirely, and it makes the retirement a step that must be remembered — which is the failure this entry exists to prevent. The retirement is put in the same converge as the move for that reason.

### 5. What gets tested, and where

Three test surfaces, per `AGENTS.md`'s table:

- **Molecule**, for the role's behaviour, in four limbs: that a superseded path named in the new input leaves `/etc/fstab`; that the live mount at that path is **not** disturbed by its removal; that the run reports no change both where the input is empty and where a declared path is already absent from `/etc/fstab`; and that a declaration naming the path in force refuses before the mount, per Decision 3a. The third of those is not an edge case but the steady state — the inventory keeps `["/mnt/main-data"]` indefinitely under Decision 3, so every converge after the first is that case.

  **The fixture mounts one device at two paths, and that is load-bearing rather than incidental.** Decision 2's end state depends on ext4 accepting a second mountpoint for a device already mounted, and that is the one mechanically uncertain step in the forward run. A scenario whose superseded path holds a *different* loop device, or a tmpfs, passes all four limbs while exercising none of it — and the first place the real thing would then be tried is staging's unattended converge against a live host. So the fixture mounts the scenario's own loop device at the superseded path and lets the role mount that same device at the fixed one. The `default` scenario already unmounts and remounts inside its container, so the mechanism for asserting a live mount exists there.
- **`.github/tests`**, for a static proposition nothing reads today: that every host bind mount in `platform/docker-compose.yml` whose source begins `/mnt/` lies under the role's default `platform_data_volume_mount_path`. This is the proposition entry 62 deliberately suspended and this change restores, and its absence is why the two could drift silently in the first place — a compose file naming a path the role does not mount produces an empty directory and a healthy-looking container, which is exactly what `docs/bootstrap-a-new-host.md` warns about.

  **Containment is compared on path components, not on string prefixes, and this is the one detail that decides whether the check is worth having.** `/mnt/main` is a proper string prefix of `/mnt/main-data`, so a bare `startswith` accepts `/mnt/main-data/prometheus` as lying under `/mnt/main` — green in exactly the state the check exists to detect. `test_ci_configuration.py`'s own `_under` helper already compares components and is what this reuses. The discriminator that proves it is a compose fixture naming `/mnt/main-data/prometheus` against a role default of `/mnt/main`: a check that passes that fixture is vacuous.

  **`/mnt/` is the qualifier, and it is chosen rather than assumed.** The stack binds ten other host paths — `/`, `/proc`, `/sys`, `/var/run`, `/var/lib/docker/`, the Docker and containerd sockets — every one of them a read-only observation mount that cAdvisor, Node Exporter and Traefik take of the host itself. Those are owned by the host and have nothing to do with the data volume, so a check written over *every* host bind mount would be red on the day it landed and would have to be weakened at the keyboard. `/mnt/` is where this host puts mounted volumes and nothing else, which makes it the line between the two populations rather than a filter that happens to fit.
- **`.github/tests`**, for a sweep: that no committed file still names `/mnt/main-data`. Several files currently explain why the path and the volume's name differ, and deleting all but one of them is the likely failure.

  **What the sweep does not reach, said plainly, because a completeness proof that is not one is worse than none.** Six files name `docs/change-queue.md` entry 64 as a commitment, and the needle is a *path* — so it misses `terraform/stacks/main-staging/terraform.tfvars`, whose commitment names no path at all, and `.github/tests/test_a_second_environment.py`, which sits inside an exempt prefix. Those two are named by tasks 2.6 and 3.5 and are caught by review or not at all. A second needle for the entry reference itself was considered and not taken: it would have to be deleted at archive along with the queue entry, which makes it a check that exists for one change and rots by construction.

**Where the sweep lives.** A module of this change's own, following `TestNoCommittedFileStillNamesTheOldTerraformRoot` in `test_terraform_stacks_are_the_iterated_unit.py` — the established idiom is that a sweep lives with the change that did the renaming. **Not** in `test_the_external_service_names_are_retired.py`, whose subject is external services; a host path is not one, and widening it would make its name false.

**The needle is `/mnt/main-data`, the path — not the bare string `main-data`.** The bare string is also the volume's retired *name*, which `EXPECTED_RETIRED_VOLUME_NAMES` in `test_a_stack_and_its_environment_are_named_separately.py` already covers and which `docs/change-queue.md` entry 74 owns the remaining prose for. Sweeping the bare string here would take that entry's work without planning it.

**Two prefix exemptions, each with a reason rather than a category.**

`openspec/` **entire**, not `openspec/changes/` alone — which is the exemption `TestNoCommittedFileStillNamesTheOldTerraformRoot` takes, and for a reason that applies here word for word. A change record names what it moves *from*, this change's own artifacts included; and `openspec/specs/iac-safety-hardening/spec.md` keeps `/mnt/main-data` until `openspec archive` merges the delta into it, which happens in the change's *last* commit. A sweep exempting only `openspec/changes/` would therefore be red for the whole life of the change, with no repair available short of hand-editing a main spec outside the archive mechanism — and a red required check on every push is a check that gets ignored rather than read.

`.github/tests/` — where a needle must be written down in order to assert its absence, and where fixture trees name the path on purpose.

**And one exemption scoped to a line rather than to a file, which the change creates for itself.** Decision 3 puts `/mnt/main-data` into both `group_vars` files permanently, and the new Molecule scenario declares a superseded path of its own — so a sweep over tracked files with no exemption for them is red before the pull request opens, and the repair reached for on the day would be a whole-path exemption on `ansible/inventory/group_vars/`, which blinds the sweep to `staging.yml`, the one file whose divergence prose the sweep was written to catch.

So the exemption is the **declaration**, not the file: an occurrence is exempt where the line it sits on, with leading whitespace stripped, begins with the key `platform_data_volume_superseded_mount_paths:`. Stripping matters rather than being a detail — the new Molecule scenario declares the path indented under `vars:` or `host_vars:`, so a match anchored at column zero would miss it and the repair reached for would be a whole-path exemption on the scenario directory. Prose anywhere in those files stays swept. That costs one thing and it is worth naming — the declaration must be written in YAML's inline flow form, `platform_data_volume_superseded_mount_paths: ["/mnt/main-data"]`, on one line, because a block sequence puts the value on a line of its own where the key is not there to exempt it. Requiring a form is cheaper than a multi-line parse, and the sweep's own failure message says which form to use.

**And one whole-path exemption that expires**, `docs/change-queue.md`, which names `/mnt/main-data` in entry 64 and stops when that entry is deleted in the archive commit. It expires by the same mechanism entry 63's did: the assertion requires an exempt path to still contain the needle, so archiving turns it red and deleting the exemption in that commit is the repair. It is planned into `tasks.md` rather than met as a surprise.

### 6. `docs/review-2026-09-08-host-readiness.md` is not edited

It records what was observed on the host on one date, and on that date the mount was `/mnt/main-data`. Editing it would make it say something that was not observed. It is therefore a second whole-path exemption on the sweep — a permanent one, unlike `docs/change-queue.md`'s, which expires at archive — and it is stated here so that a reader does not take it for an oversight.

### 7. The date on the durability table is not moved

`openspec/specs/iac-safety-hardening/spec.md`'s store table is introduced as "as at 2026-09-08", and the delta changes two path literals inside it and nothing else. The date stays: re-dating the table would assert that every store in it was re-classified today, which this change did not do. What moved is where a store is, not what it is or why it needs no backup.

## Risks / Trade-offs

**The deploy is approved before the converge** → The stack comes up on an empty directory. Loud, and recoverable by re-running the platform deploy after the converge is green. Mitigated by naming the order and the two run URLs in `tasks.md`, and by staging's unattended converge arriving first as the rehearsal.

**The old path is left mounted until something sheds it** → Two paths resolve to one filesystem for a window. Harmless — same device, same content — and `/etc/fstab` already names one path, so a reboot ends it. Accepted rather than mitigated; see Decision 2.

**A reboot between the converge and the deploy** → `/mnt/main-data` does not come back, and the still-unmoved containers bind an empty directory. The window is minutes within one attended pull request, which is the reason Decision 4 keeps it to one.

**`absent_from_fstab` behaves differently from what is assumed here** → The whole approach rests on it editing `/etc/fstab` and never unmounting. It is asserted by a Molecule scenario against a live mount rather than trusted, which is what makes that scenario load-bearing rather than incidental.

**The sweep's expiring exemption is forgotten** → The archive commit goes red on `docs/change-queue.md`. That is the mechanism working; `tasks.md` carries the step.

**A `platform/` file is touched that was not meant to be** → Any edit under `platform/` puts the merge inside `platform-deploy.yml`'s path filter. Here that is intended. It is named because the previous change nearly started an unplanned production deploy with a one-word fix to `platform/README.md`. The same holds of `terraform/` and `apply.yml`, which is why the three comment corrections are listed in the migration plan's run table rather than left to be discovered.

**Three indistinguishable approval prompts instead of two** → The merge raises a production apply, a production converge and a production deploy, all naming the same Environment. Mitigated by the run table above, by naming the workflow rather than the Environment at each approval, and by the fact that only one ordering among the three is load-bearing. It is the hazard `docs/change-queue.md` entry 77 records, met deliberately here rather than avoided by leaving two files asserting a commitment that has been discharged.

**The rollback is performed as a plain revert** → `/mnt/main` is left in `/etc/fstab` beside a re-added `/mnt/main-data`. Mitigated only by the migration plan saying so; nothing detects it, which is exactly the property that made the forward defect worth a change.

## Migration Plan

1. Merge the single pull request. **Three runs start.** Their jobs, ignoring the discovery, publish and plan-resolution jobs that carry no per-stack identity:

   | Job | Workflow | Gate |
   |---|---|---|
   | `plan (main-staging)`, `plan (main-production)` | Terraform Apply | none — the plan job declares no `environment:`, which is what puts the diff in front of the approver |
   | `apply (main-staging)` | Terraform Apply | none — staging's Environment requires no reviewer |
   | `converge (main-staging)` | Host Converge | none |
   | `apply (main-production)` | Terraform Apply | **production Environment** |
   | `converge (main-production)` | Host Converge | **production Environment** |
   | `deploy` | Platform Deploy | **production Environment** |

   Three approvals, one per workflow. `gh run list --limit 5` shows the three runs; open each run's job list for the per-stack rows — `plan (main-production)` is the one whose summary step 5 has you read. Read the **workflow** name on every approval prompt before granting it; the Environment name is the same on all three.

2. Read **staging's converge**. It moves the mount and retires the fstab entry on a host where nothing holds the old path — the rehearsal, and the only free one.
3. Approve **production's converge**. Wait for it to finish green.
4. Approve **production's platform deploy**. It recreates Prometheus and Grafana against `/mnt/main`.
5. **Read the Terraform Apply run's plan summary for `main-production` first**, confirm it reports no resource changes, and only then approve that job. It may be approved before, between or after the two above — the ordering constraint is on the converge and the deploy, not on it — but never before its plan has been read, for the reason Decision 4 gives. Expect the state serial to move even though nothing changes; that pairing is the signature of a clean no-op.
6. Observe: `/mnt/main` mounted and holding `prometheus/` and `grafana/`; `/etc/fstab` naming `/mnt/main` and not `/mnt/main-data`; Grafana serving the dashboards it served before, with a scrape gap covering the window.

**Rollback, and it takes one step more than a revert.** Reverting the merge removes the retirement task *and* the inventory input along with the path change — so the reverted converge re-adds `/mnt/main-data` to `/etc/fstab` and leaves `/mnt/main` sitting there beside it. That is the two-paths-at-boot defect this change exists to prevent, arrived at from the other direction, and the sweep and the scenario that would have caught it have been reverted too.

So a rollback is: revert, then **before converging**, point `platform_data_volume_superseded_mount_paths` at `/mnt/main` in both `group_vars` files and keep the retirement task — i.e. revert everything except the mechanism. **Both halves, or neither**: reverting the path to `/mnt/main-data` while leaving the list pointing at it is the self-defeating declaration Decision 3a describes, and the role refuses it rather than converging a host that will not mount at its next boot. Converge, and the host is back to one path. Failing that, remove the `/mnt/main` line from `/etc/fstab` by hand on each host and record it.

Before the deploy, a rollback disturbs nothing running: the live mount at `/mnt/main-data` was never removed. After the deploy it additionally needs a redeploy to move the containers back. The data is on the volume throughout and neither direction touches it.

## Open Questions

None. The one question that would have changed the approach — whether `ansible.posix` at the pinned version offers a state that edits `/etc/fstab` without unmounting — was answered against the installed collection before this design was written.
