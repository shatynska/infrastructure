## 0. A note on citations in the files this change writes

Tasks below direct rationale into files **outside** `openspec/` — role
`README.md`s, `defaults/main.yml` comments, a comment in
`host-baseline.yml`. This project's citation rule binds there, and
`.github/tests/test_ci_configuration.py` catches only the *path* form of a
violation, not this one. Where such a file needs to point at reasoning that
lives only inside this change, write **the change's name and the artifact's
name, in prose, with no path** — "the change `bound-host-log-growth-and-add-swap`,
`design.md` Decision 3" — never "design Decision 3" on its own, and never a path
under `openspec/changes/`. Requirements are cited the other way:
`openspec/specs/iac-host-configuration/spec.md` plus the requirement's own name.

Inside this change's own artifacts, a bare "Decision 3" is a sibling reference
and is fine.

## 1. Implementation

- [ ] 1.1 Give `ansible/roles/docker/` a `defaults/main.yml` holding this
  project's own two-variable interface — `docker_log_max_size` (`"50m"`) and
  `docker_log_max_files` (`"3"`) — with a comment recording why the values are
  generous rather than minimal (no log aggregation on this host, so `json-file`
  is the only history an incident can read) and naming queue entry 28 as the
  event that makes revisiting them right.
- [ ] 1.2 Pass them to the pinned external role from
  `ansible/roles/docker/meta/main.yml`'s existing `dependencies:` entry as
  `docker_daemon_options`, with `log-driver: json-file` written explicitly and
  `log-opts` carrying `max-size` and `max-file` templated from 1.1's variables.
  Both `log-opts` values must be **strings** — `to_nice_json` renders an
  unquoted `3` as a JSON number and Docker rejects a non-string `max-file`.
  Extend the file's existing comment to say the wrapper now owns daemon
  configuration, so a future daemon option is added inside this dictionary
  rather than by naming `docker_daemon_options` from inventory. Do **not** edit
  `ansible/inventory/group_vars/prod.yml`: these are safe defaults every host
  this repository configures should inherit, not prod facts.
- [ ] 1.3 Write `ansible/roles/docker/README.md`. The role has had no README
  because it had no interface; it has one now. Cover the two variables, that the
  bound reaches only containers **created after** the daemon restart and
  therefore not the containers currently running, that a container declaring its
  own logging options overrides the default, and that rendering `daemon.json`
  restarts the daemon and so briefly stops every container on the host.
- [ ] 1.4 Create `ansible/roles/swap/` with the conventional shape —
  `tasks/main.yml`, `defaults/main.yml`, `meta/main.yml`, `README.md` — modelled
  on `image_prune`. `meta/main.yml` needs the `galaxy_info`
  `namespace`/`role_name` pair every role here carries (Molecule's bundled
  ansible-compat refuses a scenario whose role has a `meta/main.yml` without a
  resolvable fully-qualified name; the `docker` role's own comment carries the
  full diagnosis) and no dependencies.

  `defaults/main.yml`: `swap_file_path` (`/swapfile`), `swap_size_mb` (`4096`),
  `swap_swappiness` (`10`), `swap_sysctl_file`
  (`/etc/sysctl.d/60-swappiness.conf`), and `swap_activate` (`true`). Every one
  has a safe default, so this role owes **no** assertion under
  `openspec/specs/iac-host-configuration/spec.md`'s "A Role's Absent Required
  Input Is Reported by Name" — that requirement reaches inputs with no safe
  default. Say so in the file's comment so the omission reads as a decision
  rather than an oversight.
- [ ] 1.5 `swap_activate` is a **test affordance and is documented as one**, in
  both `defaults/main.yml` and the README: `vm.swappiness` is not a namespaced
  sysctl and `swapon` registers with the host kernel, so a privileged container
  sharing the runner's kernel cannot activate swap without mutating state the
  run does not own. It is not a production switch, and nothing in
  `host-baseline.yml` sets it.
- [ ] 1.6 Write `ansible/roles/swap/tasks/main.yml` in this order, each task
  guarded so a re-converge is a no-op:

  1. **Establish the current state before acting.** `stat` the file; read
     whether it already carries a swap signature (`blkid -p -s TYPE`, accepting
     a non-zero return as "no signature" rather than failing, with
     `changed_when: false`); read whether the kernel currently has it active
     (`/proc/swaps`). Register all three. The file's *absence* alone is not a
     sufficient guard, because a run interrupted between creation and formatting
     leaves a file that exists and is not formatted.
  2. **Create the backing file** with `dd if=/dev/zero of=… bs=1M count=…` and
     `creates:` on the path. `dd`, not `fallocate`: `fallocate` on ext4 produces
     unwritten extents that `swapon` has refused, and the write costs a few
     seconds once.
  3. **Set ownership and permissions** to `root:root`, mode `0600`,
     unconditionally — the file holds evicted process memory, so this is the
     delta's "The swap file is not readable by an unprivileged account" scenario
     and must be enforced on every run, not only the run that created it.
  4. **Format** with `mkswap`, **only** when the file is neither active nor
     already carrying a signature. Writing a fresh signature over a file the
     kernel is swapping to corrupts the pages it holds.
  5. **Record it for boot** with `ansible.posix.mount`, `fstype: swap`,
     `opts: sw`, `state: present` — which writes `/etc/fstab` and does **not**
     activate. `state: mounted` would activate and is wrong here for exactly
     the reason 1.5 gives.
  6. **Write the swappiness file** with `ansible.posix.sysctl`,
     `sysctl_file: "{{ swap_sysctl_file }}"`, `sysctl_set: false`,
     `reload: false` — the file only, no kernel write.
  7. **Activate**, both tasks gated on `swap_activate | bool`: `swapon` the file
     when `/proc/swaps` does not already list it, and apply the live swappiness
     value with a second `ansible.posix.sysctl` (`sysctl_set: true`,
     `reload: true`). Do **not** reach for a bare `sysctl --system` command
     here: it reports changed on every run, which fails Molecule's `idempotence`
     action and task 3.9's "reports no change". The same command *is* used at
     3.8, deliberately and by hand, where re-applying is the point.

  Nothing in this role notifies a handler and nothing restarts a service.
- [ ] 1.7 Write `ansible/roles/swap/README.md`: what the role establishes and
  what it deliberately does not, the sizing reasoning, why the file is on the
  root filesystem and explicitly **not** on the `main-data` volume, what
  `swap_activate` is for and why it exists, and how to resize (`swapoff`,
  delete, re-converge) and how to remove entirely.
- [ ] 1.8 Add `swap` to `ansible/playbooks/host-baseline.yml` **after
  `deploy_user`**, with a comment giving the reason. The role is
  order-independent — it depends on nothing and nothing depends on it — so the
  placement is chosen for what it does not disturb: the play carries two
  role-scope pre-flight assertions, `hardening`'s on its CIDR list and
  `deploy_user`'s on `deploy_apps`, and no play-scope check at all (queue entry
  3c). Placing `swap` after both means this change adds nothing to what a run
  missing a required input does to the host before it refuses. Do not write
  "the play's only assertion": there are two.
- [ ] 1.9 Record the swap-utilisation alert in `docs/change-queue.md` as its own
  entry: `node_memory_SwapFree_bytes` is already scraped, the rule is a few
  lines, and it belongs in `platform/docker-compose.yml` — a different layer
  reached by a different pipeline, which is why it is not folded in. Note in it
  that `HostMemoryPressure` is RAM-based and still fires as a leak grows, so
  what the new rule adds is the explanation, not the detection. Do **not**
  delete entries 21 and 22 here; the queue's own rule deletes an entry when its
  change is archived (task 3.10).

## 2. Tests

The scenarios below are what the delta calls for. They are derived by an author
other than whoever implements section 1, from the delta specs rather than from
the implementation, per this project's workflow.

- [ ] 2.1 **Before running Molecule at all**, clear the shared state its runs
  collide on. Molecule's instance name, `~/.ansible/tmp/molecule.*` and
  `~/.cache/molecule/<role>` are stable per role and shared across working
  trees, so a concurrent run in another tree surfaces as "Module result
  deserialization failed" at `create`, `prepare` or `verify` and reads as a
  module bug (queue entries 8 and 18). A colliding run can pass as easily as
  fail, so a green result taken without this is not evidence.
- [ ] 2.2 **Provision before believing any result.** A fresh working tree
  carries tracked files only: `ansible/roles/geerlingguy.docker/` is gitignored
  and absent, the Molecule toolchain in `ansible/requirements-test.txt` is not
  installed, and a suite that cannot reach what it needs skips and reports
  success. Install the pinned collections and roles
  (`ansible-galaxy collection install -r ansible/requirements.yml`, then
  `ansible-galaxy role install -r ansible/requirements.yml -p ansible/roles`)
  and the test toolchain before any claim about a run.
- [ ] 2.3 Extend `ansible/roles/docker/molecule/default/verify.yml` to assert
  the rendered `/etc/docker/daemon.json` — that it exists, parses as JSON, names
  `json-file` as `log-driver`, and carries `max-size` and `max-file` under
  `log-opts` with the **exact** values 1.1 sets, each as a JSON string. This is
  the delta's "The daemon's configuration is what carries the bound" scenario;
  asserting only that the file exists would pass against an empty object.
- [ ] 2.4 In the same scenario, assert "A container created after configuration
  has a bounded log" the only way a container can: on the converged instance's
  own daemon, **create** a container after the role has run — `docker create`,
  not `docker run`: log options are resolved at creation, so nothing needs to
  execute — and assert its `HostConfig.LogConfig` carries both bounds. Remove it
  afterwards.

  Two fallbacks, in order. If the nested daemon cannot pull an image offline,
  seed one during `prepare` — `prepare` is a fixture, so it may supply an image
  but must not touch `daemon.json`, which is the thing under test. If the nested
  daemon cannot create a container at all, do **not** weaken the assertion into
  something that passes: record in `test-plan.md` that this scenario is
  uncovered by Molecule, and name task 3.7 as its only closer. That leaves the
  scenario resting on one prod observation, which is worth knowing.
- [ ] 2.5 Create `ansible/roles/swap/molecule/default/` converging with
  `swap_activate: false` **and a small `swap_size_mb`** — the assertion is
  against the configured size, which a small value satisfies exactly as well,
  and a defaulted converge would `dd` 4 GiB inside a CI container on every run.
  Assert every artifact the role produces: the file exists at the configured
  path and is the configured size; it is `0600` and `root:root`; it carries a
  swap signature; `/etc/fstab` names it with `fstype: swap`; the sysctl file
  exists and sets the configured value. This is the delta's "Configuration is
  established without activation" scenario.
- [ ] 2.6 That scenario must **also** assert the negative half — that nothing
  was activated. Both readings available in a container are of the **runner's**
  kernel, not the instance's, so neither can be asserted as an absolute:
  `/proc/swaps` is non-empty on any runner that itself has swap, and a live
  `vm.swappiness` of anything is meaningless without knowing what it was. Capture
  both in `prepare`, before `converge`, and assert in `verify` that each is
  **unchanged from the captured value**. An absolute assertion here is either
  flaky or tautological, and a green tautology in the one place this change
  claims honesty about coverage would be worse than no assertion.
- [ ] 2.7 Cover "A re-converge leaves active swap intact" as far as a container
  allows: Molecule's `idempotence` action already runs `converge` twice and
  fails on any reported change, which establishes the configuration path is
  idempotent. It does **not** establish the active-swap guard, because swap is
  never active in the scenario. The guard is observed at task 3.9's prod
  re-converge.
- [ ] 2.8 `ansible/roles/swap/molecule/default/molecule.yml` must satisfy
  `iac-cicd-pipeline`'s existing discovery-based checks: a content digest, not a
  tag, and the **same** digest every other authored scenario carries —
  `.github/tests/test_ci_configuration.py` fails the build on a partial refresh.
  Copy the platform stanza from an existing scenario rather than composing a new
  one, and point its comment at the `docker` scenario's shared rationale instead
  of restating it. No workflow edit is needed: `ansible-verify.yml` discovers
  roles and scenarios.
- [ ] 2.9 Write `test-plan.md` mapping each delta scenario to the assertion that
  covers it. For every scenario the suite does not establish, state which
  **claim** is actually made instead — the distinction the delta itself draws
  between observing a boot and exercising the records the host reads at boot:

  | Delta scenario | What the suite establishes | What closes the rest |
  |---|---|---|
  | Swap is active after a converge | nothing — activation is out of a container's reach | 3.7 |
  | Swap survives a reboot | nothing | 3.8 exercises `/etc/fstab` through `swapon -a`; only the optional reboot observes a boot |
  | The boot-time records are what carry persistence | the records exist and hold the right values | 3.8 |
  | Swap tendency is set and persists | the `sysctl.d` file's contents | 3.7 (live value), 3.8 (re-application) |
  | A re-converge leaves active swap intact | the configuration path is idempotent | 3.9 |
  | A container created after configuration has a bounded log | 2.4, unless its second fallback fires | 3.7 |
  | An application declaring no logging is still bounded — the half about an application maintained outside this repository | nothing | nothing in this change: `commerce-ops`'s containers rebind at a deploy from that application's own repository, which this change neither triggers nor waits for |
  | A completed run starts no application (MODIFIED) | nothing — no role names an application, so there is nothing for a scenario to catch | trivially true by construction; state that rather than leaving the row blank |
  | Restarting the runtime to adopt configuration adds no application (MODIFIED) | nothing — a single-role scenario converges no application stack | 3.6's capture and 3.7's comparison |

  **The rows above are the ones that need explaining, not the whole table.** The
  four not shown — "Containers predating the configuration are not claimed as
  bounded", "The daemon's configuration is what carries the bound", "The swap
  file is not readable by an unprivileged account" and "Configuration is
  established without activation" — are genuinely covered, by 2.3, 2.5 and 3.7,
  and still get rows of their own. Every delta scenario gets a row, the two
  MODIFIED ones included: a scenario absent from the table reads as covered by
  default, which is the inference the table exists to prevent, and reproducing
  this exemplar instead of completing it would produce exactly that. Do not write that 3.7 or 3.9 closes reboot
  persistence: neither reboots anything, and 3.8 is explicit that exercising the
  records is the weaker claim.

## 3. Verification and rollout

- [ ] 3.1 Run `molecule test --all` from `ansible/roles/docker/` and from
  `ansible/roles/swap/`. **Read the SCENARIO RECAP, not the exit code**: the
  run stops at a role's first failing scenario and every scenario sorting after
  it is silently not executed and not listed. Confirm the recap names every
  scenario each role has.
- [ ] 3.2 Run `pre-commit run --all-files` (`ansible-lint`,
  `ansible-playbook --syntax-check`, `gitleaks`, and the Terraform hooks, which
  this change does not touch).
- [ ] 3.3 Run `python3 -m unittest discover --start-directory .github/tests`
  from the repository root — the new `molecule.yml` is subject to that suite's
  digest-agreement and scenario-discovery assertions, and the change's own
  citations are subject to its citation-form check.
- [ ] 3.4 Dispatch `ai-toolkit:change-code-reviewer` over the diff, against a
  tree where 3.1–3.3 already pass.
- [ ] 3.5 Ship by merging. Nothing here reaches prod on merge:
  `host-baseline.yml` is hand-applied (queue entry 23), and merging is what
  makes the tree correct, not what applies it.
- [ ] 3.6 **Capture the running application set, then apply to prod** by hand at
  a chosen moment. `docker ps` **before** converging — that list is the baseline
  task 3.7 compares against, and it cannot be reconstructed afterwards.

  Say out loud first, so nothing in the window is discovered rather than
  expected: rendering `daemon.json` notifies `restart docker`; the daemon
  restart stops every container on the host — Traefik and the public site
  included — for a few seconds until each `restart: unless-stopped` policy
  brings it back; all eleven restart counters step at once, and Prometheus,
  Alertmanager and Grafana are themselves among the containers restarting.
  `ContainerRestartingOrOOMKilled` is worded on *repeated* restarts within a
  window (`openspec/specs/iac-platform-services/spec.md`), so a single
  simultaneous restart is not expected to fire it — an alert that does arrive is
  the converge, not an incident.
- [ ] 3.7 **Confirm what the converge established.** First, compare `docker ps`
  against 3.6's baseline: the set of running applications must be exactly the
  set from before, and anything missing must be named rather than noticed later.
  This is the delta's "Restarting the runtime to adopt configuration adds no
  application" scenario, it is the clause that makes the MODIFIED requirement a
  tightening rather than a loosening, and this is the only place it can be
  observed — a single-role Molecule scenario converges no application stack, so
  there is no set to preserve. It is also what settles, by observation rather
  than assumption, whether `commerce-ops`'s two containers return: their restart
  policies live in a Compose file this repository cannot read.

  **If anything did not return**, restore it before leaving the host — start it,
  or trigger its owning repository's deploy — record what was down and for how
  long, and do **not** tick this gate on a host with a service missing. A
  converge that leaves an application down is not a delivered change, and the
  disposition belongs in the change's own artifacts rather than in whatever the
  operator remembers afterwards.

  Then, on the host:
  `/etc/docker/daemon.json` names the driver and both bounds; `swapon --show`
  reports the configured size backed by the configured path;
  `cat /proc/sys/vm/swappiness` reads the configured value; `/swapfile` is
  `0600 root:root`.

  Then make the log bound a subject to inspect, because after the converge every
  container on the host predates it and there is otherwise nothing to look at:
  `docker create` a throwaway container from an image already on the host —
  creation resolves log options and starts no process — assert its `LogConfig`
  carries both bounds, and remove it. Inspect one of the pre-existing eleven and
  confirm it still shows the empty map the delta says it will. Do not wait for a
  platform deploy to supply the subject, and do not tick this on the daemon
  configuration alone.
- [ ] 3.8 **Exercise the boot-time records, and record that this is what was
  done.** `swapoff -a && swapon -a` returns swap from `/etc/fstab`;
  `sysctl --system` re-applies the tendency from `/etc/sysctl.d/`. Both are the
  code paths boot uses, and they catch the two ways this half realistically
  fails — an `fstab` line that does not parse or names the wrong path, and a
  `sysctl.d` file the kernel does not read.

  **If `swapon -a` brings nothing back, the step has found the defect it exists
  to find and has left the host without swap.** Recover immediately with
  `swapon <swap_file_path>`, which does not consult `/etc/fstab`, then correct
  the record and re-converge before leaving the host. Do not leave prod in the
  degraded state this step can produce.

  This is **not** an observation of a reboot, and the confirmation must not be
  written as one. A reboot is the only step that answers the delta's "Swap
  survives a reboot" scenario directly; offer it to the operator as an optional
  step in the same window, and if it is declined, record in the change's own
  artifacts that the scenario rests on the records rather than on a boot.
- [ ] 3.9 **Re-run the playbook.** The `swap` role must report no change and the
  daemon must not restart a second time. This is where the active-swap reformat
  guard is observed, since Molecule cannot reach it (2.7): a role that
  reformatted here would report changed.
- [ ] 3.10 Archive: bring the branch back to the freshly fetched trunk, commit
  the specification record, and delete entries 21 and 22 from
  `docs/change-queue.md` in that same pull request.
