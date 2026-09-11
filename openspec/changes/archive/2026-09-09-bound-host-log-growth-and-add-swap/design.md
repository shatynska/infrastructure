## Context

See `proposal.md` for why. The constraints that shape how:

- **The `docker` role is a pure wrapper.** `ansible/roles/docker/tasks/main.yml` holds no tasks; `meta/main.yml` depends on the pinned external `geerlingguy.docker` (8.0.0, pinned in `ansible/requirements.yml`) and its own comment states why the wrapper exists: so `host-baseline.yml` composes same-shaped roles rather than referencing the external role directly.
- **The external role already renders `daemon.json`.** Its `tasks/main.yml` creates `/etc/docker`, writes `docker_daemon_options | to_nice_json` to `/etc/docker/daemon.json`, and notifies `restart docker`, all gated on `docker_daemon_options.keys() | length > 0`. Its `docker_restart_handler_state` defaults to `restarted`. Nothing about entry 21 needs new tasks — only a value and a home for it.
- **Every Molecule scenario in this repository is a privileged container** sharing the runner's kernel: `privileged: true`, `cgroupns_mode: host`, `/sys/fs/cgroup` bind-mounted read-write. Fourteen authored scenarios, all pinned to one image digest that `.github/tests/test_ci_configuration.py` requires to agree across every one of them.
- **`ansible-verify.yml` discovers scenarios** rather than enumerating them, so a new role and a new scenario are picked up without a workflow edit — and `molecule test --all` stops at a role's first failing scenario, so a role's recap must be read rather than its exit code.
- **`host-baseline.yml` is applied by hand.** Merging changes nothing on prod.

## Goals / Non-Goals

**Goals**

- A ceiling on the log of every container that does not declare its own, reached without any application declaring anything — including applications this repository cannot edit.
- Swap and a swap-tendency policy recorded where the host reads them at boot, with a verification story that says which claim it makes about each.
- Safe defaults that a second host inherits without anyone editing inventory.

**Non-Goals** (beyond `proposal.md`'s)

- Changing anything about how `geerlingguy.docker` installs Docker.
- A Molecule scenario that activates swap. See Decision 7.
- A reboot of prod. Offered to the operator, not taken by this change. See Decision 7a.
- Bounding the logs of containers already running, or forcing their recreation. Docker resolves log options at container creation; see Risks.
- Overriding a container that declares its own logging options. A daemon default is a default; see Decision 2 and the delta's own wording.

## Decisions

### Decision 1: One change, two resources

Entry 21 (disk) and entry 22 (memory) are separate queue entries and were considered as separate changes.

**An argument that does not work, recorded because an earlier draft of this document relied on it.** Entry 21's half notifies `restart docker`, and with `live-restore` unset a daemon restart stops every container on the host until its `restart: unless-stopped` policy brings it back — Traefik, so the public site, included. It is tempting to call that decisive for bundling. It is not: the `swap` role notifies no handler and restarts nothing (`tasks.md` 1.6 says so explicitly, and nothing in Decision 5 gives it a handler), so the interruption belongs to the log half alone and is paid exactly once whether these ship together or apart. It is a cost to schedule, not a reason to combine.

**What the decision actually rests on** is `AGENTS.md`'s scope rule, which asks whether a change covers multiple *independent* concerns. These two are one concern — a single-host deployment with no headroom on either of its two finite resources — reached by one mechanism: a role and a variable in the same layer, converged by the same playbook, applied by the same hand-run command, observed by the same operator in the same sitting. Splitting buys nothing and costs a second full plan-build-ship cycle, a second review pair, a second confirm gate and a second operational converge of the whole playbook against prod.

*Alternative — ship 21 alone first, then 22.* Entry 21 is nearly risk-free and entry 22 carries the sizing and testability decisions below, so bundling does make the easy half wait for the hard one. Rejected on the grounds above rather than on the interruption: the hard half is a day's work, and the wait is shorter than a second cycle. The rejection is a judgement about cost, not a claim that the halves cannot be separated — they can, and if entry 22's verification story proves harder than Decision 7 expects, splitting it out remains available and cheap at that point.

### Decision 2: The bound lives at the daemon, not in Compose

`platform/docker-compose.yml` declares no `logging:` block on any of its nine services, and could gain one. It would not reach `commerce-ops`, whose Compose file lives in that application's own repository and arrives on the host through `deploy-receive`; nor would it reach a service added later by an author who did not know to annotate it. The daemon default binds both.

It also costs less: one dictionary against nine stanzas plus a second repository's cooperation.

*Alternative — `logrotate` over `/var/lib/docker/containers/*/*-json.log`.* Rejected. The daemon holds those files open, so rotation has to use `copytruncate`, which races the writer and loses lines, and leaves the daemon writing at the old offset producing a sparse file that reports its pre-truncate size. Docker's own `max-size` rotates correctly because the writer performs it.

*Alternative — the `journald` log driver with `SystemMaxUse`.* It would give central rotation and would survive a container's removal. Rejected for blast radius: it moves every container's logs out of the files cAdvisor, the deploy tooling and every existing runbook expect, in a change whose subject is a ceiling. It stays available if log aggregation (queue entry 28) makes it the right shape.

### Decision 3: `max-size: 50m`, `max-file: 3`

150 MB per container; about 1.7 GB across the eleven now running, against 65 GB free on the 75 GB root device — under 3% of what is free, and it does not grow with time, only with container count.

The reflex value is `10m`/`3`. Rejected because this host has no log aggregation (queue entry 28 is queued, not done), so `json-file` is the entire log history an incident has to read. On a Traefik fronting a public site, 30 MB is plausibly an hour. The requirement is a ceiling, not a diet, and disk is the resource this host has in surplus.

`log-driver: json-file` is written explicitly rather than relying on it being the daemon's default, so the configuration file states the whole contract.

*Revisit when* log aggregation lands, which is the event that makes small local retention harmless.

### Decision 4: The wrapper owns the interface; inventory is not edited

`ansible/roles/docker/defaults/main.yml` gains two variables of this project's own naming — a maximum log size and a maximum file count — and `meta/main.yml` passes them to the dependency:

```yaml
dependencies:
  - role: geerlingguy.docker
    docker_daemon_options:
      log-driver: json-file
      log-opts:
        max-size: "{{ docker_log_max_size }}"
        max-file: "{{ docker_log_max_files }}"
```

*Alternative — set `docker_daemon_options` directly in `ansible/inventory/group_vars/prod.yml`*, which is what queue entry 21 sketches and is one line shorter. Rejected on two counts. It names the external role's variable from inventory, which is precisely the direct reference the wrapper's own `meta/main.yml` comment says the wrapper exists to prevent. And it makes a *safe* default an *environment* fact: a host built from this repository that is not prod — the anticipated staging environment (queue entry 24), or the company-owned host this repository is a training ground for — would get unbounded logs again, silently. `ansible/roles/hardening/defaults/main.yml` already draws exactly this line, refusing a default for a source CIDR (no safe value exists) while defaulting `hardening_web_allowed_cidrs` closed (a safe value does). A bounded log has a safe value.

`prod.yml` is therefore not edited by this change. It can override either variable later if prod ever needs to differ from the default.

*Risk this introduces:* a future daemon option must be added inside `meta/main.yml`'s dictionary rather than beside it. Accepted — the wrapper owning daemon configuration is the point, not a side effect.

### Decision 5: A new `swap` role, placed last in the play

Swap gets its own role rather than tasks inside `hardening`. `hardening`'s charter is host-level *security* — its spec requirement is "Host-Level Security Owned by Ansible, Cloud Firewall Owned by Terraform" — and swap is a resource policy, not a control. The repository already has two single-purpose non-security host roles to model on, `platform_data_volume` and `image_prune`; `swap` takes the same shape (tasks, defaults, meta, README, `molecule/default`).

It is placed **last** in `host-baseline.yml`. Order is immaterial to the role itself — it depends on nothing and nothing depends on it — so the placement is chosen for what it does *not* disturb. The play carries **five** role-scope pre-flight assertions — `hardening`, `deploy_user`, `ops_user`, `platform_data_volume` and `image_prune` — and no play-scope check at all, which is what queue entry 3c records: a run missing a required input still changes the host with every role ahead of the one that refuses. Running after all five means this change adds nothing to that set, which is the most it can do about entry 3c without becoming it.

**This decision was written wrong and is corrected here rather than quietly replaced.** It first placed the role after `deploy_user` and asserted the play carried *two* assertions. Code review counted five, three of which ran after `swap` at that position — so the stated property was false, and the concrete cost was real: a host with a malformed `ops_user_accounts` entry, or an undiscoverable data volume, would have had 4 GiB written, formatted and swapped on before the run refused. The count is checkable in one command, and anyone revisiting this should re-run it rather than trust the number written here:

```
grep -n "ansible.builtin.assert" ansible/roles/*/tasks/main.yml
```

That returns **six** lines, not five: `swap`'s own is the mid-run guard on the backing file's size, not a pre-flight check on a caller-supplied input, so it is not one of the five this decision is about. Said here because a self-check that disagrees with the prose it verifies recreates the confusion the paragraph exists to prevent.

**One consequence of running last is worth stating.** The role refuses rather than adopting a `/swapfile` of the wrong size (Decision 8a), and at this position that refusal arrives after every other role has already applied. That is the correct trade — a wrong-sized file is not something to truncate under a running kernel — but it means the failure is late, and the role's README says so where an operator will meet it.

### Decision 6: A 4 GiB file at `/swapfile`, `vm.swappiness = 10`

**A file, not a partition or a volume.** A partition would mean repartitioning a provisioned host. The attached `main-data` Hetzner Volume is a network block device: putting the kernel's last-resort memory tier on the network makes the tier least able to tolerate pressure depend on the component least able to tolerate it, and it is the volume `platform/`'s Postgres, Prometheus and Grafana bind-mount. The root device has 65 GB free and is local.

**4 GiB**, half of the host's 7.6 GiB of RAM. Sized against what it is for rather than by an RAM-multiplier rule: `HostMemoryPressure` needs a leak to hold above 90% for ten minutes before it fires, and swap's job is to keep the host answering for at least that long. 4 GiB costs 6% of free root disk and is resizable later by deleting the file and re-converging.

**`vm.swappiness = 10`**, against Ubuntu's default of 60. Swap here is an overflow reserve, not a memory tier: at 60 the kernel pages out a working set on a host with 6.1 GiB available, trading latency for nothing. At 10 it still swaps under genuine pressure, which is the only case this change is about. Written to a file under `/etc/sysctl.d/` so it survives a reboot.

*Alternative — zram.* Compressed swap in RAM, no disk I/O, and increasingly the default on desktop distributions. Rejected: it buys headroom by compressing pages, which does nothing once RAM is genuinely exhausted by a leak, and it consumes RAM to do it. The failure this change addresses is a process consuming all memory; a disk-backed file is the tier that still exists at that point.

### Decision 7: Configuration and activation are separate, and only one is verified by Molecule

This is the awkward part of the change and the artifacts state it rather than implying coverage that does not exist.

```
role tasks                       Molecule (privileged container, host kernel)
─────────────────────────────    ──────────────────────────────────────────────
create /swapfile, chmod 0600     ✓ safe, asserted
mkswap                           ✓ safe, asserted (writes the file only)
fstab entry                      ✓ safe, asserted
/etc/sysctl.d/…  file written    ✓ safe, asserted
─────────────────────────────
swapon                           ✗ fails on this rig (see below); would
                                   register with the RUNNER's kernel elsewhere
sysctl --system  (live value)    ✗ vm.swappiness is not a namespaced sysctl —
                                   it would change the runner's own kernel
```

**One half of that hazard turned out to be narrower than this design first claimed, and the correction is recorded rather than quietly dropped.** The original text said a scenario that activated swap would leave a dangling reference in the runner's kernel after the instance was destroyed. Tested on 2026-09-08 by removing the role's activation gate and converging: `swapon` fails outright with `Invalid argument`, because the instance's filesystem is an overlay and the kernel refuses a swap file on overlayfs. On this rig the file half of the hazard is unreachable, not merely guarded.

The sysctl half is untouched by that: `vm.swappiness` is not namespaced and no filesystem is involved, so a live write from inside the instance does change the runner's own kernel. And the separation stands on its own footing regardless — the delta requires configuring to be separable from activating, for any host sharing a kernel, not because one particular container runtime happens to refuse the write today.

The role therefore takes a variable — default `true` — that gates the two activating tasks, and the scenario converges with it `false`. Every artifact the role produces is asserted; activation is not.

This is a deliberate test affordance and is named as one in the role's README, and the derived `test-plan.md` is obliged to name it as one too, rather than either dressing it up as production logic. The alternatives were worse: gating on `ansible_facts.virtualization_type` would make the role's behaviour depend on recognising its own test rig *and* would silently skip activation on a legitimately containerised host; a VM-driver scenario is not available, since every scenario here uses the docker driver on GitHub Actions.

**What closes the gap is `ship:confirm`, not a test.** `swapon --show` and `cat /proc/sys/vm/swappiness` on prod after the converge establish activation directly, on the only host that matters. That is a stronger observation than a container could give, and it is the gate this repository already requires before a record is archived.

### Decision 7b: The scenario cannot use the role's default swap path

Found by CI on 2026-09-09, on the first run of this change's pull request, by the scenario's own collision guard.

`/proc/swaps` is not namespaced, so the table a scenario reads is the runner's — and **GitHub's Ubuntu runners swap to `/swapfile`, which is exactly this role's default** (ubuntu-24.04 image 20260831.293.1). Left at the default, the role inside the instance reads the runner's swap file as "my file is already active", skips `mkswap`, and the run fails at the signature assertion for a reason that belongs to the rig.

This is the hazard Decision 7 describes, arriving from a direction that decision did not anticipate: not a write escaping the container, but a *read* of host state that the role mistakes for its own. Production is unaffected — on a real host `/proc/swaps` is that host's table and the check is correct — so the fix belongs to the scenario, not the role.

The scenario therefore overrides `swap_file_path` to a path nothing swaps to, and the collision guard now watches that path instead.

**Overriding it does not leave the shipped default unchecked.** `verify.yml` reads `ansible/roles/swap/defaults/main.yml` from the repository and asserts the approved literals — path, size, tendency, sysctl file, and that `swap_activate` ships enabled — directly. That is the **stronger** of the two checks: it fails whether or not any scenario happens to exercise the value, and the defaults are what a host built from this repository inherits, since nothing sets them from inventory. The `docker` role's scenario already uses the same technique to assert the external role's pin from the committed `requirements.yml`.

*What this cost, and what it bought.* A local run cannot reach this: the developer machine swaps to `/dev/sdc`. The guard was added on the theory that a collision was possible, was called "not hypothetical" on reasoning alone, and then turned out to be the CI environment itself. It is the one finding in this change that no amount of local verification would have produced.

### Decision 7a: Reboot persistence is exercised, not observed

The delta obliges swap and the swap tendency to survive a reboot. Nothing in this change reboots anything: a container has no boot, and rebooting prod is a far larger interruption than the daemon restart, on a host whose whole purpose is to stay up.

What the change does instead is exercise the boot-time records through the same mechanisms boot uses:

```
what boot does                        what the confirm step does
────────────────────────────────      ──────────────────────────────────────
reads /etc/fstab, activates swap      swapoff -a; swapon -a   → swap returns
reads /etc/sysctl.d/, applies it      sysctl --system         → tendency holds
```

Both are the real code paths, not simulations of them, and they catch the two ways this half realistically fails: an `fstab` line that does not parse or names the wrong path, and a `sysctl.d` file the kernel does not read. `swapoff -a` briefly leaves the host without swap on a machine with 6.1 GiB available, which is the state it is in today.

**The exercise has a failure state of its own, and it is the state it exists to provoke.** If the `fstab` line is wrong, `swapoff -a` succeeds and `swapon -a` brings nothing back, so the host is left with no swap — detection working exactly as intended, and the host worse off than before the step. That is recoverable in one command (`swapon <path>` directly, which does not consult `fstab`), and the record must then be corrected before leaving the host. `tasks.md` 3.8 says so, because a step that can degrade the host must state how to undo it in the same place it is described.

**This is a weaker claim than observing a boot, and it is recorded as the weaker one.** What it does not cover is anything specific to boot ordering — a swap unit that systemd's generator refuses, or a race with the data volume's mount. The delta therefore states the obligation in terms of the records, adds a scenario for exercising them, and keeps the reboot scenario as what those records exist to achieve. `test-plan.md` is obliged to say which of the two was observed.

*Alternative — reboot prod once during the maintenance window this change already opens.* It is the only thing that answers the reboot scenario directly, and the operator may choose it; `tasks.md` offers it as an explicitly optional step with the consequence of declining written down. It is not the default because a reboot is an operational decision belonging to the operator, not one a change makes on their behalf to close its own gate.

### Decision 8: Never write a swap signature over active swap

`mkswap` on a file the kernel is currently swapping to corrupts the pages it holds. Guarding on the file's *absence* alone is not enough: a run interrupted between creating the file and formatting it leaves a file that exists and is not formatted, and a later `mkswap` guarded on absence would skip it.

The role establishes the file's actual state before acting — whether the path exists, whether it carries a swap signature, and whether the kernel currently has it active — and formats only a file that is not active and does not already carry a signature. Creation itself is guarded by `creates:`, so the 4 GiB write happens once.

`dd if=/dev/zero` is used rather than `fallocate`. `fallocate` on ext4 produces unwritten extents, which `swapon` has historically refused; `dd` costs a few seconds once and is unambiguous.

### Decision 9: Reconcile the daemon restart with the scope requirement, by modifying it

`openspec/specs/iac-host-configuration/spec.md`'s "Configuration Scope Stops at the Container Runtime" carries the scenario *"no application container SHALL have been started as a result of that run"*. A daemon restarted to adopt new configuration stops every container, and each `restart: unless-stopped` policy returns it. On that scenario's plain text, that is an application container started as a result of the run.

It is not a violation of the requirement's **prose**, which forbids Ansible *invoking* a runtime's application-lifecycle command. Ansible invokes none: the handler restarts the runtime, and the containers come back because their own definitions say to. The gap is between the prose and the scenario written to check it.

**The gap predates this change.** `geerlingguy.docker` notifies the same `restart docker` handler when it installs or upgrades the Docker package, so every converge that has ever bumped Docker has done exactly this. What this change does is make it routine and put it in writing, which is what makes it this change's obligation to settle rather than something to leave for whoever notices next.

A clarifying paragraph in the *new* logging requirement was considered and rejected: a note in requirement B saying that requirement A's scenario does not mean what it says leaves the false text in place and adds a second place to read. The delta therefore takes a MODIFIED delta on the requirement itself, narrows the scenario to *"started by a task of that run"* — what the prose always meant — and adds a second scenario that is **stricter** than what it replaces: the set of running applications after such a run SHALL be exactly the set from before. That is a property the old wording did not check and the new one does, so the reconciliation tightens the requirement rather than loosening it to fit.

**That only holds if the stricter scenario is actually checked.** A narrowing compensated by a clause nobody verifies is just a narrowing, whatever it says about itself. It cannot be checked in Molecule — a single-role scenario converges no application stack, so there is no set to preserve — so it is checked where it can be: `tasks.md` 3.6 captures the running application set immediately before the converge and 3.7 compares it afterwards, naming anything that did not come back. That is two `docker ps` calls, and it also turns a claim this design was otherwise making without evidence — that `commerce-ops`'s two containers return, which depends on restart policies in a Compose file this repository cannot read — into an observation.

### Decision 10: The wrapper takes merged extra options, because three existing scenarios depend on `daemon.json` being absent

Found while deriving this change's tests, and verified in the tree rather than predicted. Three scenarios — `image_prune/default`, `image_prune/abandon-paths` and `deploy_user/default` — write `/etc/docker/daemon.json` in their `prepare.yml`, selecting the `vfs` storage driver with `containerd-snapshotter` disabled, because their fixtures build and run nested containers. All three then converge `role: docker`.

`geerlingguy.docker` renders that file with `copy:` from `docker_daemon_options` — an overwrite, not a merge — gated on the dictionary being non-empty. That gate is false today, which is the only reason those fixtures survive. Decision 4 makes it true, so as planned this change would silently wipe `vfs` from three scenarios that belong to other changes and break them.

**The fix is not to special-case them.** The wrapper gains `docker_daemon_extra_options` (default `{}`), and `meta/main.yml` composes:

```yaml
docker_daemon_options: >-
  {{ docker_daemon_extra_options | combine(<the log-bound dict>, recursive=True) }}
```

The log bound is applied **last**, so the escape hatch can add any daemon option and cannot silently remove the ceiling — which is the polarity that matters, since a scenario or a host that could unset the bound by adding an unrelated key is the failure this whole requirement exists to prevent.

The three scenarios then pass their storage-driver settings as a role variable in `converge.yml` and drop the now-dead `prepare.yml` write. That is a better expression of what those files already say they are: `prepare.yml`'s own comment calls the write a fixture, and a fixture belongs in the scenario's parameters rather than in a file the role under test overwrites. No assertion in any of the three changes, and none is relaxed.

*Alternative — let the scenarios override `docker_daemon_options` from `converge.yml`'s `vars:`.* Does not work: a dependency parameter in `meta/main.yml` is a role param, which outranks play vars in Ansible's precedence order, so the wrapper's value would win and the override would be silently ignored — the worst of the available failures.

This does soften Decision 4's accepted risk, which said a future daemon option must go inside the wrapper's dictionary. It now has a documented way out. That is a fair trade for not breaking three scenarios, and the escape hatch is constrained in the one direction that counts.

### Decision 11: The derived logging assertions move into the `docker` role's existing scenario

The test author wrote them into a new `docker/molecule/log-bound/` scenario rather than extending `docker/molecule/default/verify.yml`, because appending to an existing test file is an edit its own rules forbid it. Its report names folding them back as a reasonable implementer call.

They are folded. The two `converge.yml` files are identical — `role: docker` with no variables supplied — so the scenarios differ only in which assertions run, and keeping both would pay a second full converge of the slowest role in the suite on every pull request, to read one file.

**Every assertion moves verbatim and none is dropped, relaxed or reworded.** That distinction is the whole of what makes this a relocation rather than the weakening this repository's testing rules refuse: the fold is legitimate because the converge it moves to is the same converge, and it would not be if the receiving scenario set up the host differently.

**And that claim cannot be checked from the repository, which is a defect in how the fold was sequenced rather than in the fold.** The `log-bound` scenario was never committed, so no reviewer has a baseline to diff the folded assertions against — the independent test author's output survives only inside the implementer's edit, which is precisely the separation the derive-tests step exists to create. The right order is to commit the derived tests exactly as authored and then fold in a second commit, so the fold is reviewable as a diff. Recorded in `docs/change-queue.md` so the next change does it that way; not reconstructed here, because a reconstruction from memory would be a fabricated baseline and worse than an acknowledged gap.

## Risks / Trade-offs

- **The daemon restart briefly stops every container, including Traefik** → Seconds, and self-healing for the nine platform services, which are all `restart: unless-stopped` in a file this repository owns and can read. The two `commerce-ops` containers are **assumed** to return on the same basis and that assumption is not checkable from here — their Compose file lives in that application's own repository. Which is why 3.6 and 3.7 observe the set rather than asserting it. The converge is hand-run, so it can be timed, and the interruption is called out in `tasks.md` so nobody discovers it mid-run. It is a cost of the log half and would be paid whether or not the swap half rode along (Decision 1).
- **A container that does not come back is invisible unless someone looks** → The daemon restart stops everything; anything without a restart policy stays down, and the next signal would be `MetricsTargetDown` or a customer. This is both the operational risk and the delta's own new scenario, so one observation answers both: capture the running set before the converge, compare after, name what is missing (Decision 9).
- **All eleven restart counters step at once during the converge** → `ContainerRestartingOrOOMKilled` is worded on *repeated* restarts within a window (`openspec/specs/iac-platform-services/spec.md`), so a single simultaneous restart is not expected to fire it. Prometheus, Alertmanager and Grafana are themselves among the containers restarting, so an alert that does arrive is the converge rather than an incident. `tasks.md` 3.6 says so before the run, so nobody spends the window diagnosing it.
- **The eleven running containers stay unbounded until they are next recreated** → Inherent: Docker resolves log options at container creation. The spec states the guarantee this way rather than overclaiming. A platform deploy recreates the nine; `commerce-ops` recreates its two on a deploy this repository neither triggers nor waits for. Forcing recreation is not this change's business.
- **The confirm gate has no container to inspect** → It follows from the risk above: after the converge, every container on the host predates the configuration, so "inspect a container created after the restart" names nothing. Closed by making one on purpose — `docker create` resolves log options and starts no process, so a throwaway container from an image already on the host answers it at no cost and is removed again. Without that step the gate is unperformable and would be ticked on a weaker observation, which is the ambiguity queue entry 12 exists to refuse.
- **Molecule never proves swap activates, nor that it survives a boot** → Decisions 7 and 7a. Activation is closed at `ship:confirm` against prod; reboot persistence is *exercised* rather than observed, and the derived `test-plan.md` is obliged to record which of the two claims was made for each delta scenario rather than leaving a reader to infer coverage from an absent assertion.
- **A wrong `max-size` value silently produces an unbounded log** → Docker rejects a malformed `max-size` at container creation rather than ignoring it, so the failure is loud. The scenario asserts the rendered JSON's exact values, so a typo fails the suite before it reaches a host.
- **Swap turns a fast, loud failure into a slow, quiet one** → Partly true and deliberate: that is the trade the change is making, buying the alert time to fire. `HostMemoryPressure` is computed from `MemAvailable/MemTotal` and is unaffected by swap existing, so the condition stays observable. What is genuinely missing is a rule on swap *utilisation*, which would say why — a `platform/` change, recorded in `docs/change-queue.md` rather than folded in (`proposal.md`, Non-goals).
- **Templating a dependency parameter in `meta/main.yml` from the depending role's own defaults** → Supported, but it is the one mechanism here nothing in this repository already exercises. The `docker` scenario asserts the rendered `daemon.json` values, so a resolution failure fails the suite rather than reaching a host.

## Migration Plan

1. Merge. Nothing changes on prod: `host-baseline.yml` is hand-applied (queue entry 23).
2. **Capture the running application set** (`docker ps`) immediately before converging. It is the baseline for step 4's comparison and is worthless if taken afterwards.
3. Run `ansible-playbook host-baseline.yml` against prod at a chosen moment, accepting one short interruption of all containers when the daemon restarts.
4. **Compare the running set** against step 2's, naming anything that did not come back. This is the delta's "Restarting the runtime to adopt configuration adds no application" scenario, and the only place it can be observed.
5. Observe, on the host: `/etc/docker/daemon.json` holds the driver and both bounds; `swapon --show` reports 4 GiB backed by `/swapfile`; `cat /proc/sys/vm/swappiness` reports `10`; `/swapfile` is `0600 root:root`.
6. Make the log bound's subject, because none exists otherwise: `docker create` a throwaway container from an image already on the host, inspect its `LogConfig` for both bounds, and remove it. Inspect any of the eleven pre-existing containers and confirm it still shows the empty map the delta says it will.
7. Exercise the boot-time records without rebooting (Decision 7a): `swapoff -a && swapon -a` returns swap from `/etc/fstab`; `sysctl --system` re-applies the tendency from `/etc/sysctl.d/`. If `swapon -a` brings nothing back, the `fstab` record is wrong and the host is now without swap: recover with `swapon /swapfile` and correct the record before leaving. Optionally, and at the operator's choice rather than this change's, reboot once during the same window — that is the only step that answers the reboot scenario directly.
8. Re-run the playbook. It must report no change for the `swap` role and must not restart the daemon a second time — which is also where the active-swap reformat guard is observed, since Molecule cannot reach it.

**Rollback.** Logs: delete `/etc/docker/daemon.json` and re-converge with the variables cleared, at the cost of one further restart. Swap: `swapoff /swapfile`, remove the `fstab` line, delete the file, remove the `sysctl.d` file — no restart, and nothing on the host depends on either being present.
