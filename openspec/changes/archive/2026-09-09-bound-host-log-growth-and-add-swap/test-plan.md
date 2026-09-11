# Test plan — `bound-host-log-growth-and-add-swap`

Derived from this change's delta specification for `iac-host-configuration`, before any implementation existed, by an author who has read the delta specs, `proposal.md`, `design.md` and `tasks.md` — and no implementation of the two new requirements. The plan was committed at `94f78cd`; these tests map to that baseline.

**This file is not an artifact the OpenSpec schema knows about.** It will not appear among `openspec instructions apply`'s context files, and has to be read on purpose. Whoever implements this change should read it before starting: it names, per scenario, what is checked automatically and what is not.

**This pass adds tests and never subtracts.** No existing test file was edited, deleted or disabled, and no implementation was written. Everything below is either a new file under a test-path glob or this manifest.

---

## 1. What was written

Two new Molecule scenarios. No test was added under `.github/tests/` — every property this change introduces is a property of a converged host, not a static read of a committed file, and the new `molecule.yml` files are already subject to that suite's existing digest-agreement and scenario-discovery assertions (confirmed: the suite passes with them present).

| File | Purpose |
|---|---|
| `ansible/roles/docker/molecule/default/verify.yml` | Asserts the rendered `/etc/docker/daemon.json` and that the daemon came back up on it. **Authored as a separate `log-bound` scenario and folded in by the implementer** — see open question 1 below, now resolved. Its `molecule.yml`, `prepare.yml` and `converge.yml` were discarded in the fold: the existing scenario's are identical in every respect that matters, and its `converge.yml` was already `role: docker` with no variables |
| `ansible/roles/swap/molecule/default/molecule.yml` | Scenario definition; instance name `swap-role-instance`; default test sequence, so `idempotence` runs |
| `ansible/roles/swap/molecule/default/prepare.yml` | Fixture only — captures the runner kernel's swap areas and live `vm.swappiness` **before** the converge |
| `ansible/roles/swap/molecule/default/converge.yml` | Converges `swap` with `swap_activate: false` and `swap_size_mb: 16`; every other input left at the role's own defaults |
| `ansible/roles/swap/molecule/default/verify.yml` | Asserts every artifact the role writes to the filesystem, and that nothing reached the shared kernel |

### How to run one

The runner-selectable unit is the scenario, not the assertion:

```
cd ansible/roles/docker && molecule test -s default
cd ansible/roles/swap   && molecule test -s default
```

`molecule test --all` from a role directory runs that role's scenarios in sorted order and **stops at the first failure**, so every scenario sorting after a failing one is neither executed nor listed in the SCENARIO RECAP. Read the recap and confirm it names every scenario the role has. As authored, the logging assertions lived in a `log-bound` scenario named to sort *after* `default` for exactly this reason: while it was red, a name sorting before `default` would have silently taken the docker role's existing, passing scenario out of the run. After the fold the concern is moot for this role — there is one scenario — but it still governs `swap` and every role with more than one.

A single assertion inside a converged instance can be re-run without a full scenario — this is how the assertions below were exercised during authoring:

```
molecule converge -s <scenario>
ansible-playbook -i <instance-name>, -c community.docker.docker \
  ansible/roles/<role>/molecule/<scenario>/verify.yml \
  --start-at-task "<task name>"
```

### Before believing any run

1. **Provision.** A fresh working tree carries tracked files only. `ansible/roles/geerlingguy.docker/` is gitignored and absent, and the Molecule toolchain in `ansible/requirements-test.txt` may not be installed. A suite that cannot reach what it needs skips and reports success.
2. **Clear the shared state Molecule runs collide on** — `~/.ansible/tmp/molecule.*` and `~/.cache/molecule/<role>` are stable per role and shared across working trees, and a concurrent run in another tree can make a run pass or fail for reasons unrelated to the code.

---

## 2. Baseline

Taken before any file was written, and **scoped** — to the two roles this change touches plus the whole static suite — rather than full. The scope and what it omits are stated here because a later claim that these tests fail is uninterpretable without it.

| What was run | Result |
|---|---|
| `python3 -m unittest discover --start-directory .github/tests` (repository root) | 170 tests, **OK** |
| `molecule test --all` from `ansible/roles/docker/` | SCENARIO RECAP named `default`; `failed=0`, **green** |
| `molecule test --all` from `ansible/roles/swap/` | **No baseline possible** — neither the role nor its scenario existed |
| `ansible/roles/{deploy_user,hardening,image_prune,ops_user,platform_data_volume}` | **Not run.** Twelve scenarios, omitted for run time. See §6: three of them are predicted to break on this change's implementation, and that prediction is therefore *unbaselined* |

Toolchain used: `ansible-core 2.21.3`, `molecule 26.8.0`, `molecule-plugins[docker] 26.7.15`, Python 3.12 — the exact pins in `ansible/requirements-test.txt`. Docker daemon reachable; the pinned scenario image was already present at the committed digest.

### The state each new test is in now

| Test | State after this pass | What that establishes |
|---|---|---|
| `docker` / `default` | Red at "Assert the daemon configuration file exists" — `/etc/docker/daemon.json` is absent after a converge | The target does not exist yet. The later assertions have not been exercised *by this run* — but they were exercised during authoring, see below |
| `swap` / `default` | Red at "Assert the backing file exists and is a regular file" — `/swapfile` is absent after a converge | Same. Note the converge itself **succeeds**: `ansible/roles/swap/` exists as a directory (it holds `molecule/`), so Ansible resolves the role and runs its zero tasks silently. The red comes from the verification, not from role resolution |

**Every assertion in both files was exercised against a hand-built end state during authoring**, so none of them is in the "test itself is broken" state. The end state was built by hand inside a converged instance and destroyed with it — nothing was written to the repository:

* the logging assertions: with the intended `daemon.json` in place, all 11 tasks pass. With `"max-file": 3` unquoted, the bounds assertion fails.
* `swap`: with a hand-made `/swapfile` (16 MiB, `0600 root:root`, `mkswap`ed), an `fstab` line, `/etc/sysctl.d/60-swappiness.conf` and a capture file, all 24 tasks pass. Discrimination confirmed individually: `chmod 0644` fails the unprivileged-read assertion; zeroing the swap signature fails the signature assertion; the configured swap file appearing in the shared kernel's swap-area list fails the no-activation assertion. (As authored this read "a changed swap-area list". The implementer narrowed the assertion after the broader form was observed to fail on a developer machine whose own swap partition activated mid-run — see §5 question 3.)

`ansible-lint` over both scenario directories reports exactly one violation — `syntax-check`, "The role 'swap' was not found" — which is the absent target and nothing else. Note that this makes `pre-commit run --all-files` red until the `swap` role exists; per `AGENTS.md`, commit with `--no-verify` while the derived tests are red and treat it as expected rather than as a defect.

---

## 3. Every delta scenario, accounted for

Thirteen scenarios across three requirements; thirteen rows. A scenario absent from this table would read as covered by default, which is the inference the table exists to prevent.

### Requirement: Container Logs Are Bounded by the Host's Daemon Configuration (ADDED)

| Scenario | Covered by | What is actually established | What closes the rest |
|---|---|---|---|
| The daemon's configuration is what carries the bound | `docker` / `default`, tasks "Assert the daemon configuration file exists", "…parses as JSON", "…names the logging driver", "…carries both bounds, with the configured values", "…both bounds are recorded as JSON strings" | Fully covered. The file exists, parses, names `json-file`, and carries `max-size: "50m"` and `max-file: "3"` as JSON strings | — |
| A container created after configuration has a bounded log | **Nothing** | Partially approached only: "Assert the daemon came back up with the configured logging driver" establishes the daemon is running on this configuration file, not that a container inherits the bounds | The hand-run prod converge (`tasks.md` 3.7), which `docker create`s a throwaway container on the real daemon and inspects its `LogConfig`. **This scenario rests on one prod observation** |
| Containers predating the configuration are not claimed as bounded | **Nothing** | — | `tasks.md` 3.7's inspection of one of the pre-existing eleven, plus `tasks.md` 1.3's README wording. The second half of the scenario — that a run is not *recorded* as having bounded them — is a property of this repository's prose, not of a host, and no automated test can hold it |
| An application that declares no logging configuration is still bounded | **Nothing** | — | Nothing in this change for the half about an application maintained outside this repository: `commerce-ops`'s containers rebind at a deploy from that application's own repository, which this change neither triggers nor waits for. The in-repository half follows from the daemon-level bound once the row above is closed |

**Why the two container-dependent scenarios are uncovered, with evidence.** Not an oversight, and not a judgement that they need no test. A container cannot be created on the instance's nested daemon in this scenario. Reproduced on 2026-09-08 inside a converged instance of the scenario as authored, with the fixture image obtained offline (`tar -cf - -T /dev/null | docker import -`, which succeeds):

```
docker create --name probe molecule-log-bound-fixture:1 /bin/true
Error response from daemon: failed to mount /tmp/containerd-mount...: mount
source: "overlay", ... fstype: overlay, ... err: invalid argument
```

That is the overlay-on-overlay failure `image_prune`'s own prepare documents. The sibling scenarios that do run nested containers avoid it by writing a `daemon.json` selecting the `vfs` storage driver in `prepare.yml` — which is not available here, because `daemon.json` is the subject under test and the external role overwrites it (§6). No weaker assertion was substituted: an assertion that the daemon *could* bound a container, made without a container, is exactly the tautology this change's verification story is written to avoid.

### Requirement: The Host Carries Swap That Survives a Reboot (ADDED)

| Scenario | Covered by | What is actually established | What closes the rest |
|---|---|---|---|
| Configuration is established without activation | `swap` / `default`, tasks "Assert the backing file exists and is a regular file" through "Assert the converge wrote no live swap-tendency value to the shared kernel" | Covered, with the negative half stated precisely. Every artifact the role writes is asserted. The negative half asserts that **the configured swap file is not among** the shared kernel's active swap areas — not that the whole list is unchanged — and that live `vm.swappiness` is unchanged from `prepare.yml`'s capture. The first of those cannot be driven red on this rig: `swapon` fails on overlayfs, so a role ignoring the gate goes red one step earlier, at converge | The narrowed clause rests on the converge failure and on `tasks.md` 3.7's `swapon --show` on prod |
| The swap file is not readable by an unprivileged account | `swap` / `default`, tasks "Assert the backing file admits only root by ownership and mode" and "Assert the unprivileged read was refused" | Fully covered. Mode/ownership, plus a real refused read as `nobody` | — |
| The boot-time records are what carry persistence | `swap` / `default`, tasks "Assert the boot-time mount table names the swap file with fstype swap", "Assert the kernel-parameter file exists…", "Assert the kernel-parameter file sets the configured swap tendency" | **The records exist and hold the right values.** Not that re-reading them by the mechanism the host uses at boot yields active swap — the scenario's second clause is not covered | `tasks.md` 3.8: `swapoff -a && swapon -a` and `sysctl --system` on prod. Those are the real code paths, and that is still weaker than a boot |
| Swap tendency is set and persists | `swap` / `default`, task "Assert the kernel-parameter file sets the configured swap tendency" | **The `sysctl.d` file's contents only.** The live value is deliberately not asserted: `vm.swappiness` is not namespaced, so the reading available inside the instance is the runner's | `tasks.md` 3.7 (live value on prod), `tasks.md` 3.8 (re-application through `sysctl --system`) |
| Swap is active after a converge | **Nothing** | Activation is out of this rig's reach — `swapon` fails outright on overlayfs (`Invalid argument`, tested 2026-09-08), and would reach the runner's own kernel on a rig where it could succeed | `tasks.md` 3.7's `swapon --show` on prod |
| Swap survives a reboot | **Nothing** | — | `tasks.md` 3.8 *exercises* `/etc/fstab` through `swapon -a`; **only the optional prod reboot observes a boot**. Do not record 3.7 or 3.9 as closing this: neither reboots anything |
| A re-converge leaves active swap intact | The `idempotence` action of `swap` / `default` | **That the configuration path is idempotent** — Molecule converges twice and fails on any reported change. It does **not** establish the active-swap reformat guard, because swap is never active in this scenario | `tasks.md` 3.9's prod re-converge: a role that reformatted there would report changed |

### Requirement: Configuration Scope Stops at the Container Runtime (MODIFIED)

| Scenario | Covered by | What is actually established | What closes the rest |
|---|---|---|---|
| A completed run starts no application | **Nothing** | — | Trivially true by construction rather than by observation: no role in `host-baseline.yml` names an application, its service-definition file or its stack, so there is nothing for a scenario to catch. Stated here rather than left blank — see the note below on why no static test was written for it |
| Restarting the runtime to adopt configuration adds no application | **Nothing** | A single-role Molecule scenario converges no application stack, so there is no running set to preserve | `tasks.md` 3.6's `docker ps` capture and 3.7's comparison. This is the clause that makes the MODIFIED requirement a tightening rather than a loosening, and it is observed on prod or nowhere |

**A static test for "A completed run starts no application" was considered and not written.** It is in principle a static read of committed files — the `.github/tests` suite's subject — asserting that no Ansible task invokes a runtime's application-lifecycle command or templates a service-definition file. It was rejected because the assertion cannot be written without a derived judgement this pass has no mandate to make: the requirement forbids a container started *by a task of that run*, and this repository legitimately **templates** scripts (`deploy-receive`, `app-deploy`) that invoke `docker compose` when the deploy mechanism later runs them. A grep-shaped check that failed on those would be wrong, and one that excluded them would encode an untested boundary as a passing test. Recorded here so the absence of the test is distinguishable from the absence of the thought; it is a reasonable follow-up change, not part of this one.

---

## 4. Assertion classification

Per the testing floor: every assertion is specified (traces to a stated requirement), derived (inferred, with no stated requirement covering it), or deliberately untested. Each assertion in both files carries its classification in a comment immediately above it; this is the summary.

### Specified

* The daemon's configuration file exists, parses, names the logging driver, and carries both a maximum size and a maximum retained-file count.
* The swap backing file exists, is a regular file, is the configured size, is `root:root` mode `0600`, cannot be read by an unprivileged account, and carries a swap signature.
* `/etc/fstab` names the swap file with fstype `swap`.
* A file under `/etc/sysctl.d/` names the swap tendency.
* The configured swap file was not activated, and no live swap tendency was written, during a converge with activation disabled.

### Derived — every one of these obliges the implementation to satisfy something no scenario states

| Derived assertion | Where it comes from | Why it is asserted rather than left open |
|---|---|---|
| `max-size` is exactly `50m` and `max-file` exactly `3` | `design.md` Decision 3, `tasks.md` 1.1 | A ceiling nobody fixed is a ceiling nobody can verify; the reviewed plan fixed these. Changing one is a change to that decision *and* to this test, visibly |
| Both bounds are JSON **strings**, asserted against the file's raw text | `tasks.md` 1.2 | Docker rejects a non-string `max-file`, and `to_nice_json` renders an unquoted YAML `3` as a JSON number. Adds no discrimination today (the equality assertion already fails on it) and is kept as a guard on the reading — noted as such in the file |
| The swap file is at `/swapfile` | `design.md` Decision 6 | The requirement says "a file on the root filesystem" and names no path |
| The swap tendency is `10` | `design.md` Decision 6 | The requirement says "an overflow reserve rather than a routine memory tier"; `10` is what the plan chose against Ubuntu's `60` |
| The kernel-parameter file is `/etc/sysctl.d/60-swappiness.conf` | `tasks.md` 1.4 | The requirement names the directory, not the file |
| The swap file is not under `/mnt/main-data` | `design.md` Decision 6 | The requirement forbids "the host's dedicated data volume"; the mount point is this repository's |
| `docker info` succeeds and reports the configured logging driver after the converge | Nothing states it | Narrow and stated as such in the file: dockerd refuses to start on a configuration it cannot accept, and the file-reading assertions cannot tell a healthy daemon from a dead one |
| `nobody` stands for "an unprivileged account with a login on this host" | Nothing states it | The real accounts (`deploy`, `ops`) do not exist in a single-role scenario. See §5 |

### Deliberately untested

* **Any absolute value of `/proc/swaps` or of the live `vm.swappiness`.** Both readings inside the instance are of the runner's kernel. Confirmed on the authoring machine: the runner reports swap on `/dev/sdc` and `vm.swappiness = 60`. An absolute assertion would be flaky on a runner with swap and tautological on one already at the value. The comparison against a `prepare`-time capture is what replaces it.
* **Activation, and anything that writes to the kernel.** Not merely untested — prohibited: it would mutate the CI runner's own kernel and leave a reference the runner's own kernel on any rig where `swapon` can succeed at all. On this overlayfs-backed rig it fails outright instead (tested 2026-09-08); the live `vm.swappiness` write reaches that kernel either way.
* **The `Used` column of `/proc/swaps`.** Live accounting on a busy machine; comparing it would be a flaky assertion wearing a strict one's clothes. The comparison is over the list of active swap areas.
* **Whether the swap file's filesystem is the *root* filesystem**, as opposed to merely not the data volume. Inside a container the instance's `/` is an overlay, so the reading would say nothing about a real host.

---

## 5. Unresolved project questions

Questions that arose while deriving these tests and that neither `AGENTS.md`, `CLAUDE.md` nor this change's artifacts answer. This pass had no channel to ask on, so each is recorded with the assumption taken and the tests that depend on it, rather than resolved silently.

1. **The logging assertions were directed into an existing test file; this pass may not edit one.** The dispatch and `tasks.md` 2.3–2.4 both say to extend `ansible/roles/docker/molecule/default/verify.yml`. The same dispatch also forbids editing, deleting or disabling any existing test, as does this pass's own standing rule — and appending to a file is editing it. *Assumption taken:* additive-only wins; the assertions went into a new `log-bound` scenario instead, which touches nothing existing. *Depends on it:* every file under `ansible/roles/docker/molecule/default/`. *What to do about it:* folding `log-bound`'s verify tasks into `default`'s and deleting the scenario is a reasonable implementer decision — it would remove one duplicated converge of the heaviest role in the suite. It is an edit to an existing test, which is why this pass did not make it. **RESOLVED by the implementer: folded.** Every assertion moved verbatim, none dropped, relaxed or reworded; the two `converge.yml` files were identical, which is what makes it a relocation rather than a weakening. See the change's `design.md` Decision 11.

2. **Whether `50m`/`3`, `/swapfile`, `10` and `60-swappiness.conf` are fixed enough to assert as literals.** They come from `design.md` and `tasks.md`, not from the delta specs. *Assumption taken:* yes — the plan is reviewed, conditionally approved with conditions applied, and committed at `94f78cd`. *Depends on it:* the value assertions in both verify files. If any value changes, the plan and the test change together, which is the intended coupling.

3. **Whether the `docker` wrapper will offer a merge point for daemon options it does not own.** Unanswered, and it decides whether the two container-dependent logging scenarios can ever be covered by Molecule: with a merge point, a scenario could select the `vfs` storage driver alongside the log bounds and create a container. Without one, they stay prod-only. *Assumption taken:* none is offered; the scenarios are recorded uncovered. *Depends on it:* the two uncovered rows in §3, and §6's collision.

4. **Which unprivileged account stands for the host's interactive one.** The requirement's reason names "an unprivileged interactive account" on the real host; a single-role scenario has neither `deploy` nor `ops`. *Assumption taken:* `nobody`, present in the pinned image. *Depends on it:* "Assert the unprivileged read was refused".

---

## 6. Obsolete tests, and one collision that is not an obsolescence

### Obsolete tests: none found, and the search was bounded

This change carries a MODIFIED delta, so the list is applicable rather than "not applicable". **No entry.** The search covered the two test-path globs this change may write to and nothing else:

* `ansible/roles/*/molecule/*/` — searched for the requirement's name ("Configuration Scope Stops at the Container Runtime"), for its scenario wording ("starts no application", "service-definition", "application- lifecycle"), and for the subjects of the two new requirements ("log-opts", "max-size", "LogConfig", "swap", "daemon.json").
* `.github/tests/*.py` — same terms.

No earlier `test-plan.md` was supplied to this pass, so no scenario-to-test mapping from a previous change was available to draw on.

**"No such test exists", not merely "none was found."** The MODIFIED requirement's superseded scenario — "no application container SHALL have been started **as a result of** that run", narrowed to "**by a task of** that run" — is asserted by no test in either glob. Only two files mention the requirement at all (`ansible/roles/platform_data_volume/README.md` and that role's `tasks/main.yml`), and both are prose, not assertions. That is consistent with `design.md` Decision 9, whose whole point is that the gap between the requirement's prose and its scenario has never been checked by anything. There is therefore nothing for anyone to delete or rewrite, and no candidate is put forward for confirmation.

### A collision the implementation will hit, which is not an obsolete test

Reported here because it is a finding of this pass, and because it is a change to existing test files that only whoever implements may make.

Three existing scenarios write `/etc/docker/daemon.json` in their `prepare.yml` to put the nested daemon on the `vfs` storage driver, because their fixtures run real containers and overlay-on-overlay does not mount:

* `ansible/roles/image_prune/molecule/default/prepare.yml`
* `ansible/roles/image_prune/molecule/abandon-paths/prepare.yml`
* `ansible/roles/deploy_user/molecule/default/prepare.yml`

`geerlingguy.docker` 8.0.0 renders that same file with `copy:` from `docker_daemon_options | to_nice_json` — it **overwrites, it does not merge** — gated on `docker_daemon_options.keys() | length > 0`. That gate is false today, which is why those three scenarios pass. `tasks.md` 1.2 makes it true.

So after the implementation lands, each of those three converges will replace the `vfs` daemon configuration with the log bounds and restart the daemon on the default snapshotter, and their container fixtures are expected to fail.

This is **not** an obsolete test and nothing here should be deleted: the fixtures are still correct about what they need. It is a reconciliation the implementation owes — for example a merge point on the wrapper that a scenario can add options through, which would also unblock §3's two uncovered logging scenarios and §5's question 3.

**Not verified by running.** Those three scenarios were not in the baseline scope (§2), so this is a prediction from reading the external role's task and the three prepares, not an observed failure. Whoever implements should run `molecule test --all` from `ansible/roles/image_prune/` and `ansible/roles/deploy_user/` and read the recaps.

---

## 6a. Amendment, 2026-09-09: the scenario no longer converges the default path

CI's first run of this change failed `swap` / `default` at the scenario's own collision guard: GitHub's Ubuntu runners swap to `/swapfile`, the role's default, and `/proc/swaps` is shared with the container.

`converge.yml` now overrides `swap_file_path`, and `verify.yml` gained an assertion that reads `ansible/roles/swap/defaults/main.yml` from the repository and checks the approved literals there. So the shipped defaults are still covered — more strictly than before, because that assertion does not depend on a scenario exercising them — while the behavioural assertions run against a path that cannot collide with the runner's own swap.

Mutation-checked: changing `swap_swappiness` to 60 in the committed defaults turns `verify` red.

## 7. What the implementation must make pass

* `cd ansible/roles/docker && molecule test --all` — recap must name `default`, `failed=0`. (As authored this read "**both** `default` and `log-bound`"; the implementer folded the second into the first.)
* `cd ansible/roles/swap && molecule test --all` — recap must name `default`, `failed=0`. The `idempotence` action is part of that: a second converge must report no change.
* `python3 -m unittest discover --start-directory .github/tests` from the repository root — 170 tests, and the new `molecule.yml` files are inside its digest-agreement and scenario-discovery assertions.
* `pre-commit run --all-files` — currently red on `ansible-lint`'s `syntax-check` for the absent `swap` role, and on nothing else.
* The three scenarios named in §6, which are outside this change's own test surface but inside what its implementation touches.

What no test will make pass, and what therefore has to be observed on prod before this change can be archived: swap activation, reboot persistence, the live swap tendency, the active-swap reformat guard, a container created after the daemon was configured, a container predating it, and the preservation of the running application set across the daemon restart. That is seven of the thirteen scenarios resting on `tasks.md` 3.6–3.9, and it is the reason those steps are written the way they are.
