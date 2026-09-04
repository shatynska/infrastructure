# Test manifest — add-platform-monitoring

Written by the `openspec-test-writer` pass, before this change is
implemented. **Not an artifact the OpenSpec schema knows about** — it will
not appear among `openspec instructions apply`'s context files and must be
read on purpose before implementing this change's tasks (see also
`rules/openspec.md`'s pointer to this file, which is the first, redundant
pointer alongside this report).

This pass never read any implementation — none exists yet for either delta
— and never wrote any implementation. It is additive only: no existing test
was edited, deleted, or disabled.

**Update, after this pass:** the 10 imprecise/missing `iac-platform-services`
mappings this report originally identified (scenarios 1, 2, 3, 5, 6, 7, 8,
14, 17, 18 in the table below) have since been closed by tightening or
adding verification steps in `tasks.md` — see 2.11 (real metric values, not
just target-up), 2.12 (per-app error attribution), 3.5 (one verification
per alert rule instead of one generic test), 5.6 (dashboard panels show
real data), 2.13 (data survives container recreation), and 2.14 (retention
flags confirmed applied via Prometheus's own runtime config). Unresolved
project question 2 (device-path discovery for task 1.1) was also resolved:
the mount task globs `/dev/disk/by-id/scsi-0HC_Volume_*` on-host rather than
hand-copying Terraform's `linux_device` output — see `design.md`'s "The
volume's device path is discovered on-host" decision. The scenario table
and gap notes below are left as originally written (a point-in-time
record of what this pass found); read them alongside this note, not as
still-current gaps.

## Scope and the two-delta split

This change carries two delta specs that fall on opposite sides of this
project's testing conventions, per the dispatch:

- **`iac-host-configuration`** (3 scenarios, all `ADDED`): new Ansible
  host-configuration content (mounting `main-data`). This repo's convention
  for testing Ansible role behavior is a per-role `molecule/` directory
  (`ansible/roles/{deploy_user,docker,hardening,ops_user}/molecule/`), run
  via `molecule test` from the role's own directory. New tests were written
  here: `ansible/roles/platform_data_volume/molecule/default/`.
- **`iac-platform-services`** (18 scenarios, all `ADDED`): `platform/`
  Compose-stack-level behavior. AGENTS.md states plainly there is no
  automated test layer for this yet ("There is no traditional unit-test
  layer for the Terraform code yet" / `terraform test` is named only for
  `terraform/modules/`, which this change does not touch — Impact section:
  "no resource changes expected"). No test framework exists in this
  repository for Compose-stack-level behavior. Per the dispatch, no test
  framework was invented for this delta; every one of its 18 scenarios is
  recorded below as **manual verification only**, mapped to the specific
  `tasks.md` step that is its intended verification — and, where that
  mapping is imprecise or absent, that gap is stated explicitly rather than
  papered over.

## Scenario accounting — `iac-host-configuration` (3/3 accounted for)

Requirement: "Platform Data Volume Is Mounted at a Fixed Host Path"
(`openspec/changes/add-platform-monitoring/specs/iac-host-configuration/spec.md`).

All three are covered by new Molecule tests in
`ansible/roles/platform_data_volume/molecule/default/` (scenario `default`,
run via `cd ansible/roles/platform_data_volume && molecule test --all`).
Individually selectable as the named `ansible.builtin.assert` tasks in
`verify.yml` (this project's runner, `ansible-playbook`/Molecule, selects by
running the whole `verify.yml` playbook — there is no finer per-assertion
selection mechanism, the same granularity every existing role's Molecule
scenario in this repo already has).

| # | Scenario | Test | Classification |
|---|---|---|---|
| 1 | Volume is mounted at a known path | `verify.yml` → "Assert the data volume is mounted at the fixed path, on the expected device and filesystem" | Specified |
| 2 | Mount survives a reboot | `verify.yml` → "Assert a well-formed, active fstab entry exists for the fixed mount path" + "Assert the mount comes back at the same path from `mount -a` alone" | Specified, via a stated proxy technique (see below) |
| 3 | Dependent subdirectories exist before a service needs them | `verify.yml` → "Assert every dependent subdirectory exists with the ownership and permissions its container requires" + "Assert every dependent subdirectory is genuinely on the mounted volume, not the container's root filesystem" | Specified (existence/ownership/permissions) + Derived (on-volume device-id check) |

**Scenario 2 is not, and cannot be, a genuine reboot inside a Molecule
Docker container** — there is no real init to reboot and Docker gives no
equivalent action. What is asserted instead is both mechanisms a real
reboot's init actually relies on: a well-formed, uncommented `/etc/fstab`
entry, and that `umount` followed by `mount -a` (exactly what init does with
fstab at boot) brings the mount back with no other manual step. This is
recorded as a **proxy**, not a full substitute — genuine reboot-survival
against the real host is `tasks.md` task **1.4** ("Deploy and confirm the
mount is present and persists across a reboot"), which remains the
authoritative proof for this scenario and is not superseded by the Molecule
test.

## Scenario accounting — `iac-platform-services` (18/18 accounted for)

All 18 are recorded as **manual verification only** — no automated test was
written, per the dispatch's explicit instruction not to invent a framework
this repository does not have for Compose-stack-level behavior. Each is
mapped to its closest `tasks.md` verification step, with the mapping's
precision stated honestly rather than overstated.

| # | Scenario | `tasks.md` reference | Mapping quality |
|---|---|---|---|
| 1 | Host resource metrics are available | 2.11 ("Verify each exporter's target is `up` in Prometheus after deploy") | **Imprecise.** 2.11 confirms node-exporter is scraped successfully, not that a CPU/memory/disk *value* is actually queryable. No `tasks.md` step queries an actual metric value. Gap. |
| 2 | Any container's health is observable (restart/exit/OOM via cAdvisor) | 2.11 (cAdvisor target `up`) | **Imprecise**, same reason as #1 — confirms the exporter is reachable, not that a real restart/exit/OOM event actually surfaces as a metric. Gap. |
| 3 | An application's error rate is observable | 5.3 (dashboard provisions a per-application HTTP error-rate panel) + 5.6 (dashboard reachable) | **Gap.** No `tasks.md` step triggers a 5xx from an application and confirms it is attributed to that application in a query. |
| 4 | Postgres metrics are available | 2.11 (postgres-exporter target `up`) | Direct. |
| 5 | Sustained per-application error rate triggers an alert | 3.5 ("Trigger a test alert end-to-end and confirm it reaches Slack") | **Imprecise.** 3.5 is a single generic test-alert step; it does not specify which of the four-plus alert rules (this one included) is what gets exercised. Gap: no step verifies this rule's threshold logic specifically. |
| 6 | A crash-looping container triggers an alert | 3.5 | Same imprecision as #5. Gap. |
| 7 | Host resource pressure triggers an alert | 3.5 | Same imprecision as #5. Gap. |
| 8 | A metrics source becoming unreachable triggers an alert | 3.5 | Same imprecision as #5. Gap — despite design.md's Decisions section explicitly calling this rule out ("A Prometheus target being down is itself an alert condition"), `tasks.md` assigns it no verification step of its own. |
| 9 | An application container cannot query Prometheus or an exporter | 2.11 ("verify a container attached only to `platform_edge` cannot reach Prometheus's query API, Alertmanager, Grafana, cAdvisor, node-exporter, or postgres-exporter") | Direct. |
| 10 | The reverse proxy's metrics endpoint is a stated exception | 2.11 ("but can still reach Traefik's metrics endpoint") | Direct. |
| 11 | A firing alert is delivered (Slack) | 3.5 | Direct. |
| 12 | Heartbeat is sent during normal operation | 4.5 ("heartbeat arrives during normal operation") | Direct. |
| 13 | Loss of the host is detected externally | 4.5 ("stopping Alertmanager causes the external service to detect a missed heartbeat") | Direct. |
| 14 | An operator views current health | 5.3 (dashboards provisioned) + 5.6 (dashboard reachable) | **Partial.** 5.6 confirms reachability and credential, not that the dashboard's content actually shows host/container/per-app data as claimed. |
| 15 | The dashboard interface is not reachable from the public internet | 5.6 ("unreachable via the public interface/Traefik") | Direct. |
| 16 | The dashboard interface has no default credential | 5.5 (admin credential sourced from secret) + 5.6 ("reachable ... with the configured credential") | Direct. |
| 17 | Monitoring data survives on dedicated storage (containers recreated) | *(none)* | **Gap.** `tasks.md` 1.4 verifies the Ansible *mount's* persistence across a host reboot, not that Prometheus's/Grafana's data survives a `platform/`-level container recreation (`docker compose up --force-recreate` or equivalent). No task does this. |
| 18 | Retention is bounded | 2.10 (sets `--storage.tsdb.retention.time`/`--storage.tsdb.retention.size` flags) | **Gap.** 2.10 is a configuration task, not a verification step — nothing in `tasks.md` confirms data actually gets discarded once retention is reached. |

Ten of the eighteen (1, 2, 3, 5, 6, 7, 8, 14, 17, 18) have either an
imprecise mapping or no mapping at all. This is reported as-is rather than
forced into a tidier-looking table — see **Report** below for what this
means for the implementer.

## Assertion classification (Molecule tests only — the platform-services delta has no automated assertions to classify)

- **Specified**: "volume mounted at fixed path" (device/path/fstype match),
  "fstab entry well-formed and active", "mount comes back via `mount -a`",
  "subdirectory exists with declared owner/group/mode" — each traces
  directly to the three scenarios' own text.
- **Derived**: the device-id comparison proving a subdirectory sits on the
  mounted volume rather than the container's pre-mount root filesystem. No
  scenario names this distinction; it was added because a bare `stat.exists`
  check would pass even against a same-named directory the role created
  before mounting — see `verify.yml`'s own comment for the full reasoning.
- **Deliberately untested**: exact retention/threshold values are out of
  scope everywhere in this change (design.md's Open Questions: "not fixed
  here... can change later without a spec change") — no assertion in either
  delta pins a specific number, consistent with that.

## Assumed role interface (ASSUMPTION, not a stated requirement)

`ansible/roles/platform_data_volume/` does not exist yet. This pass invented
its variable interface so the Molecule scenario could be written at all —
recorded in full, with reasoning, in `converge.yml`'s own comment block.
Summary:

- `platform_data_volume_device` (required, no default)
- `platform_data_volume_mount_path` (design.md's own example: `/mnt/main-data`)
- `platform_data_volume_fs_type` (this test uses `ext4`)
- `platform_data_volume_subdirs`: list of `{path, owner, group, mode}`

The subdirectory owner/group values used (`65534`/`65534` for `prometheus`,
`472`/`472` for `grafana`) are this test's own fixture choice — neither
`proposal.md` nor `design.md` names an actual container UID/GID for either
service. `472` is Grafana's real upstream image default UID/GID (a
checkable value); `65534` is a plausible stand-in for Prometheus's "nobody"
default. **If the implementation's actual `platform/docker-compose.yml`
service definitions run Prometheus/Grafana as different UIDs, that is an
interface mismatch to reconcile — update `converge.yml`/`verify.yml`'s
values to match, not evidence the role itself is wrong.**

## Obsolete tests

**Not applicable.** Both delta specs are `ADDED`-only — neither
`iac-host-configuration`'s nor `iac-platform-services`'s delta in this
change carries a `MODIFIED`, `REMOVED`, or `RENAMED` requirement, so there
is no superseded behavior and no existing test to search for.

## Unresolved project questions

1. **No shared Molecule fact-cache between `prepare.yml` and `converge.yml`
   in this repository.** `ansible/ansible.cfg` sets no `fact_caching`
   backend, so a dynamically-allocated fixture resource (e.g. a loop device
   from `losetup -f`) set up in `prepare.yml` has no channel to reach
   `converge.yml`'s variables. This pass worked around it with a hardcoded
   device minor number (`/dev/loop87`) — sufficient for this one scenario,
   but the same gap would recur for any future role needing a dynamically
   allocated fixture resource. Whether to add a shared `fact_caching`
   backend (e.g. `jsonfile`) is a repository-wide decision this pass has no
   authority to make; flagged for whoever owns `ansible/ansible.cfg` next.
   **Assumption taken**: hardcoded `/dev/loop87`.
   **Tests depending on it**: all of
   `ansible/roles/platform_data_volume/molecule/default/{prepare,converge,verify}.yml`.
2. **How Ansible learns the real Hetzner Volume's device path in
   production is not decided anywhere in this change's artifacts.**
   `terraform/modules/volume/outputs.tf` exposes `linux_device`, but nothing
   in `proposal.md`/`design.md`/`tasks.md` says how that value reaches
   `ansible/inventory/group_vars/prod.yml` (hand-copied, like
   `hardening_ssh_allowed_cidrs`? discovered on-host via a
   `/dev/disk/by-id/scsi-0HC_Volume_*` glob, avoiding the need to copy
   anything?). This does not block the Molecule test (which supplies its own
   fixture device), but it is a real open question for whoever implements
   task 1.1. Not something this pass can resolve by reading specs alone.
3. **Whether `ansible.posix.mount` (already pinned, 1.6.2) is in fact the
   module the implementation will use**, versus hand-rolled
   `mount`+`lineinfile`/`blockinfile` against `/etc/fstab`. `verify.yml`'s
   assertions are written against outcomes (`findmnt`, `/etc/fstab`
   content), not against which module produced them, so this does not
   affect what was written — noted so the implementer knows the tests do
   not presume a specific module.

## Baseline

**Scoped baseline taken**, not full-suite: this pass's own new scenario
only, since molecule/docker/network access existed in this environment.

- Installed the project's pinned test toolchain (`ansible/requirements-test.txt`,
  via `uv venv` per the README's own instructions) and the pinned Galaxy
  requirements (`ansible/requirements.yml`, already present).
- `ansible-playbook --syntax-check` passed clean for `prepare.yml`,
  `converge.yml`, and `verify.yml`.
- Ran `molecule converge` for the new `default` scenario: `create` and
  `prepare` (the loop-device fixture) both succeeded; `converge` itself
  ran a no-op (`changed=0`) because `ansible/roles/platform_data_volume/`
  has no `tasks/main.yml` yet — expected, since the role does not exist.
- Ran `molecule verify`: **failed**, at the very first assertion
  ("Assert the data volume is mounted at the fixed path..."), with
  `findmnt rc 1` — the mount point simply does not exist, because no role
  ran to create it. This is the expected **target-does-not-exist** failure
  state (testing skill's second state), not a fixture defect (third state):
  the fixture itself — apt install, sparse file, loop device node,
  `losetup` association — completed with `ok`/`changed` and no errors before
  reaching that assertion, which is what establishes the failure traces to
  the absent role and not to a broken test setup.
- `molecule destroy` was run afterward to tear the instance down; nothing
  from this baseline run was left behind.
- **Not run**: the existing roles' own Molecule suites
  (`deploy_user`, `docker`, `hardening`, `ops_user`) were not re-run as part
  of this baseline — this pass touches none of their files, and a full
  `--all`-scenario run across every existing role was judged disproportionate
  to what a scoped baseline needs to establish for this change specifically.
  If a full-suite baseline is wanted before implementation begins, it has
  not been taken and should be requested explicitly.

No implementation was written to make any test pass. The `platform_data_volume`
role directory contains only `molecule/` — no `tasks/`, `defaults/`, or
`meta/` — exactly as this pass left it.
