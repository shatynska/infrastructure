# Test manifest — add-per-app-deploy-keys

Written by the `openspec-test-writer` dispatch, before implementation.
**This file is not part of the OpenSpec schema** — `openspec instructions
apply` will not surface it among a task's context files. Read it on
purpose before implementing any task in `tasks.md`. (It is also pointed to
by this library's `rules/` fragment that directs it be read before
implementing; this is the second, redundant pointer, since that fragment's
import path is machine-local and would not otherwise reach this
repository.)

Location: `openspec/changes/add-per-app-deploy-keys/test-manifest.md`.

No implementation of the new mechanism exists yet. `ansible/roles/deploy_user/`
currently holds only the old single-key, argument-free mechanism this
change retires (`tasks/main.yml`, `molecule/default/{molecule.yml,
converge.yml,verify.yml}`). All new tests below are written against the
change's delta spec
(`openspec/changes/add-per-app-deploy-keys/specs/iac-host-configuration/spec.md`)
and, for the REMOVED requirement, against the current
`openspec/specs/iac-host-configuration/spec.md` — never against
implementation source, because none exists for the new mechanism to read,
and the old mechanism's implementation was not consulted either (only its
spec text and its existing Molecule scenario, which lives within the
dispatched test-path glob and is fair game to read as an existing test,
not as "implementation").

## What was written

Three new files, all within the dispatched test-path glob
(`ansible/roles/*/molecule/**/*.yml`), forming a **new** Molecule
scenario named `per_app_deploy`, sibling to the existing `default`
scenario under the same role:

- `ansible/roles/deploy_user/molecule/per_app_deploy/molecule.yml`
- `ansible/roles/deploy_user/molecule/per_app_deploy/converge.yml`
- `ansible/roles/deploy_user/molecule/per_app_deploy/verify.yml`

**No existing file was edited, deleted, or disabled.** `default`'s three
files are untouched. tasks.md 3.1 phrases its own instruction as
"Add/update the role's Molecule scenario (`.../molecule/default/`)" — i.e.
it anticipates the new mechanism's tests eventually living in (or
replacing) `default` itself. Since this pass may never edit or delete an
existing test, the new tests instead live in a new, non-colliding scenario
directory. Folding `per_app_deploy` into `default` (or deleting `default`
once its now-superseded content is confirmed obsolete — see "Obsolete
tests" below) is an implementation-time action for whoever applies this
change, not something performed here.

**No implementation code was written.** `ansible/roles/deploy_user/tasks/main.yml`,
`ansible/roles/deploy_user/defaults/main.yml`, `ansible/requirements.yml`,
`ansible/inventory/group_vars/prod.yml`, and `.github/workflows/platform-deploy.yml`
were read but not modified.

## Baseline

**No baseline could be taken**, for the same reason as this project's prior
`bootstrap-ansible-host-baseline` pass: `which ansible ansible-playbook
ansible-lint molecule` finds none of them installed in this environment
(`python3 -m pip show molecule` confirms molecule itself is absent), and
even with them installed, the new mechanism the `per_app_deploy` scenario
targets doesn't exist in `ansible/roles/deploy_user/tasks/main.yml` yet — a
pre-implementation run isn't meaningful here (the target-absent situation,
per the `testing` skill). What I *did* run: a `yaml.safe_load_all` parse of
every file under the test-path glob, confirming no YAML syntax defects —
this caught and fixed two real syntax errors during authoring (an unquoted
string-concatenation `that:` clause, and a `name:` value containing an
unquoted `: ` that YAML parsed as a nested mapping). That is a syntax
check, not a baseline, and is reported as such rather than as a substitute
for one.

## Scope note: which requirements these tests cover

The change's delta spec carries two `## ADDED Requirements` (9 scenarios
total) and one `## REMOVED Requirements` entry with no scenario blocks of
its own in the delta file (standard for a REMOVED delta — its full text,
including its 4 scenarios, lives in `specsRoot`). Per this dispatch's
explicit instruction, I read `openspec/specs/iac-host-configuration/spec.md`
to establish exactly what that removed requirement ("Restricted Deploy
Account for Platform Stack Access") states before writing any obsolete-test
entries. Its 4 scenarios are enumerated below and accounted for as
uncovered, with the REMOVED operation itself as the reason, per this
dispatch's contract — they are not tests to write, and the tests that bore
on them go in the obsolete list instead.

**Total: 13 scenarios accounted for (9 ADDED + 4 REMOVED).**

## Scenario accounting — ADDED Requirement 1: Restricted Deploy Account Supports Per-Application Forced-Command Deploys (7 scenarios)

| # | Scenario | Test(s) | Status |
|---|---|---|---|
| 1 | A single SSH session delivers content and triggers deploy | `per_app_deploy/verify.yml` — "Pipe the valid archive into deploy-receive commerce-ops...", "Assert the pipe was not rejected by sudo...", "Assert deploy-receive's full pipeline (extract, permission, trigger) succeeded end to end", "Confirm commerce-ops's docker-compose.yml and .env landed under /opt/commerce-ops", "Assert both expected members were extracted", "Assert the extracted .env has restrictive permissions" | Covered |
| 2 | Archive members outside the expected set are ignored | `per_app_deploy/verify.yml` — "Pipe the decoy-bearing archive into deploy-receive platform...", "Confirm whether the decoy member was extracted...", "Assert the two real members were extracted and the decoy member was not, regardless of its name" | Covered |
| 3 | An application's key can only ever deploy that application | `per_app_deploy/verify.yml` — "Read deploy's authorized_keys", "Assert each key's line carries restrict,command= bound to its own application name only" (cross-key contamination check) | Covered (proxy — see note below) |
| 4 | A leaked key cannot be used to pivot into the host's network | `per_app_deploy/verify.yml` — same "Assert each key's line carries restrict,command=..." task, `restrict` presence half only | Covered (proxy — see note below) |
| 5 | An unenumerated application name is rejected | `per_app_deploy/verify.yml` — "Attempt sudo app-deploy for an application with no sudoers.d entry...", "Assert sudo refuses the unenumerated application name" | Covered |
| 6 | New applications are onboarded without a new account | `per_app_deploy/verify.yml` — "Confirm /opt/<name> for both platform and commerce-ops...", "Assert each /opt/<name> directory is owned deploy:deploy, mode 0750", "Read each application's sudoers.d entry...", "Assert each sudoers.d entry is the exact, fully-qualified, wildcard-free line...", "Assert exactly one `deploy` system account exists...", "Assert onboarding commerce-ops required no new Unix account, home directory, or sudoers structure" | Covered |
| 7 | Platform deploys through the same mechanism as every other application | `per_app_deploy/verify.yml` — "Assert the retired platform-compose-deploy script does not exist on this fresh instance", "Assert no separate platform-specific script is installed by this role's tasks", plus the same authorized_keys/sudoers assertions from scenarios 3/4/6, applied to platform's own entries | Covered (fresh-instance caveat — see note below) |

**Note on scenario 3/4 (proxy coverage):** the actual enforcement these two
scenarios describe is OpenSSH's own `restrict`/`command=` semantics acting
on a real SSH session opened with a given key — not logic this role's own
tasks implement (design.md is explicit: "Neither script re-validates `$1`
against an allowlist itself"). Molecule's `ansible_connection: docker`
connects via `docker exec`, not a real SSH client-to-target session, so it
cannot exercise an actual forwarding-channel-open attempt the way tasks.md
5.4 describes doing live, against real infrastructure, as a Rollout step.
This pass's tests assert the static `authorized_keys` content each key's
enforcement depends on (the `restrict,command=...` line, bound to that
key's own application name and no other) — the entirety of what this
role's own tasks control — and stop there. tasks.md 3.1 itself scopes
Molecule verification to exactly this static content check ("assert
`restrict` is present, not just `command=`"), with the live
forwarding-refusal proof assigned to 5.4 instead; this pass follows that
same scoping.

**Note on scenario 7 (fresh-instance caveat):** this `per_app_deploy`
scenario's Molecule instance never had `platform-compose-deploy` installed
on it — this role's tasks, under the new mechanism, no longer create that
file at all. Its absence here is a legitimate assertion in that isolated
context. This is a different claim from "the live production migration has
already deleted it" — production deliberately keeps that script
present-but-unreachable until tasks.md 5.6's separate, later,
validation-gated playbook run (design.md's Migration Plan), which this
role-level scenario does not attempt to reproduce (see "Deliberately
untested" below).

## Scenario accounting — ADDED Requirement 2: Host Authenticates to GHCR for Application Image Pulls (2 scenarios)

| # | Scenario | Test(s) | Status |
|---|---|---|---|
| 8 | A private GHCR package can be pulled during deploy | `per_app_deploy/verify.yml` — "Report whether the live GHCR credential-store check will run", "Read root's Docker credential store...", "Assert root's Docker credential store contains a ghcr.io entry..." | Covered (conditional proxy — see note below); actual pull success deliberately untested (see below) |
| 9 | GHCR token is never committed | `per_app_deploy/verify.yml` — "Scan the repository for literal GitHub/GHCR token markers", "Assert no literal GitHub/GHCR token is committed anywhere in the repository", "Find any ghcr_pull_token assignment that lives outside a Vault-encrypted file", "Assert every ghcr_pull_token assignment found in the repository is inside a Vault-encrypted file" | Covered |

**Note on scenario 8:** a real pull-success proof needs a real private GHCR
package and a real, valid `read:packages` token — neither of which this
pass can safely commit (a real token is a credential; a placeholder one
would legitimately fail authentication, which is not a defect in the role
and would make the test flaky/misleading rather than meaningful). tasks.md
5.5 assigns the actual pull-success proof to a manual Rollout step against
real infrastructure. This pass's credential-store-content assertion is
gated behind `MOLECULE_GHCR_PULL_TOKEN` being supplied at test-run time (a
CI secret, never committed) — when absent, the check is explicitly
reported as skipped (via the `debug` task), not silently passed. See
"Unresolved project questions" below.

## Scenario accounting — REMOVED Requirement: Restricted Deploy Account for Platform Stack Access (4 scenarios, from `specsRoot`)

Every scenario below is accounted for as **uncovered**, with the REMOVED
operation itself as the reason, per this dispatch's contract — no new test
is written for superseded behavior. The existing test(s) bearing on each
are listed in "Obsolete tests" below, not here.

| # | Scenario | Status | Reason |
|---|---|---|---|
| 10 | Deploy account's privileged access is a single fixed action, not arbitrary command injection | Uncovered | REMOVED — superseded by ADDED Requirement 1's per-application, argument-carrying mechanism |
| 11 | Deploy account can escalate via the content it is entitled to write | Uncovered | REMOVED — same underlying trust boundary persists generically across `/opt/<app_name>` (see design.md Risks), but the *scenario as written*, naming the single fixed wrapper script, is superseded |
| 12 | Deploy account is provisioned independently of any operator | Uncovered | REMOVED — the specific claim tested ("only the test-supplied deploy key is authorized," i.e. exactly one key) is superseded by a per-application multi-key model |
| 13 | Deploy private key is never committed | Uncovered | REMOVED — see "Obsolete tests" below; this one's bearing test may substantively still hold under the new model (flagged, not assumed) |

**Count check:** 13 scenarios enumerated (7 + 2 ADDED, 4 REMOVED), 13
accounted for (9 covered — 1 of which, scenario 8, only partially, with its
substantive half deliberately untested — and 4 uncovered as REMOVED).

## Assertion classification

**Specified** (traces directly to stated scenario/requirement text):
- Scenario 1: both members extracted; `.env` mode 600 (spec text: "set
  restrictive permissions on the extracted `.env`"); the pipe not being
  rejected by sudo.
- Scenario 2: decoy member not extracted, regardless of name (spec text:
  "any other archive member SHALL NOT be extracted, regardless of its name
  or path").
- Scenarios 3/4: `restrict,command=...` present, bound to the correct
  per-key application name, with no cross-key contamination — direct from
  the ADDED requirement's own text.
- Scenario 5: sudo refusal of an unenumerated name (spec text: "`sudo`
  SHALL refuse to run it").
- Scenario 6: exactly one `deploy` account, no per-application account
  (spec text: "not a new Unix account, home directory ownership model, or
  sudoers structure"); `/opt/<app_name>` owned by `deploy` (spec text names
  ownership, not mode).
- Scenario 6/general: sudoers exact line, no wildcard (spec text: "that
  exact, fully-qualified argument (no wildcard)").
- Scenario 7: no separate platform-specific script remaining (spec text,
  within this scenario's fresh-instance scope — see caveat above).
- Scenario 8: credential-store content check (spec text: "the pull SHALL
  succeed using the host's configured GHCR credential") — conditional/proxy,
  per the note above.
- Scenario 9: token not committed in plaintext; stored via Vault (spec
  text, both clauses).

**Derived** (inferred; no scenario states it directly, labeled inline in
the file's own comments too):
- `/opt/<app_name>` mode `0750` — from tasks.md 1.1/design.md's "mirrors
  `/opt/platform`'s existing shape," not the spec text itself.
- `visudo -cf` validation of each rendered sudoers file — tasks.md 3.1's
  own stated verification point, not spec-scenario text.
- `app-deploy`/`deploy-receive` exact ownership (`root:root`/`deploy:deploy`)
  and mode `0755` — from tasks.md 1.2/1.3, not the spec text, though the
  scripts' existence and behavior (what they do once invoked) is specified.
- The empty-`services: {}` Compose fixture as the technique enabling
  scenario 1's end-to-end `rc == 0` assertion without a real registry — a
  derived *test-design choice*, not a weakening of what's asserted: a
  non-zero `rc` still means some step in the one-session chain failed.
- The specific regex patterns used to detect a "GitHub/GHCR token-shaped"
  string (`gh[pousr]_...`, `github_pat_...`) — the requirement that no
  token appear in plaintext is specified; the exact detection pattern is
  this pass's own invention, same as `bootstrap-ansible-host-baseline`'s
  private-key-marker scan.

**Deliberately untested** (identified, not silently dropped):
- The live half of scenario 4 (an actual `ssh -L`/agent-forwarding/X11/pty
  attempt over a real SSH session being refused) — assigned to tasks.md
  5.4's live Rollout verification; Molecule's `docker exec`-based
  connection cannot exercise a real target-facing SSH session. See the
  proxy note above.
- The substantive half of scenario 8 (an actual private GHCR package
  successfully pulling) — assigned to tasks.md 5.5's manual Rollout
  verification; no real registry credential is committed to make this
  pass's own run of it meaningful. The credential-store-*presence* check is
  attempted, conditionally, as described above.
- **`.github/workflows/platform-deploy.yml`'s rewritten deploy job**
  (tar-pipe delivery, secret handling, the actual live CI run reaching a
  real host over the tailnet). This is deliberately outside both the
  dispatched test-path glob (`ansible/roles/*/molecule/**/*.yml` does not
  reach `.github/workflows/`) and, more fundamentally, outside the delta
  spec's own scenario surface — every scenario in
  `specs/iac-host-configuration/spec.md` describes host-configuration-level
  (Ansible-provisioned) state, not the workflow file's own behavior; the
  workflow's rewrite is described only in proposal.md/design.md/tasks.md
  (Impact/Migration Plan sections), never as a spec scenario. Its actual
  correctness is verified operationally via tasks.md's coordinated
  Rollout window (4.3 merge, then 5.1 playbook run, then 5.2 live
  validation against a real or dummy `platform/**` change) — a live,
  sequenced, human-coordinated GitHub-Actions-plus-real-host cycle that no
  unit- or role-level test framework in this repository (Molecule
  included) can reproduce. This is the same category of judgment a sibling
  dispatch made about `commerce-ops`'s own CI/CD pipeline scenarios, made
  explicit here per this dispatch's instruction rather than silently
  applied.
- Idempotency of the new `deploy_apps`-driven convergence ("a second run
  reports no changes," tasks.md 5.1) — exercised automatically by
  Molecule's own `idempotence` step within `molecule test`'s run of the
  `per_app_deploy` scenario, not by a hand-written assertion of mine; noted
  as covered by the test *command* itself, per the same convention the
  prior `bootstrap-ansible-host-baseline` manifest used.
- The full production migration-timing property (the old script staying
  present-but-unreachable through the coordinated maintenance window,
  deleted only later by 5.6) — a live, timed, human-coordinated Rollout
  property, not observable from a single ephemeral Molecule convergence of
  one role in isolation.

## Obsolete tests

**Applicable** — the change carries one REMOVED delta (and, distinctly,
two ADDED requirements that together restate what the removed requirement
covered in a generalized form). Search was bounded to the dispatched
test-path glob, `ansible/roles/*/molecule/**/*.yml`, plus the (absent)
earlier `test-manifest.md` — none was supplied to this dispatch. Within
that glob, the only existing content bearing on the removed requirement is
`ansible/roles/deploy_user/molecule/default/{converge.yml,verify.yml}`
(and, structurally rather than as an assertion, `molecule.yml`).

All entries below are **candidates for human confirmation**, not
conclusions.

| Existing test (runner-selectable: task name within `ansible/roles/deploy_user/molecule/default/verify.yml`, run via `cd ansible/roles/deploy_user && molecule test -s default`) | Superseded by | Evidence |
|---|---|---|
| "Assert deploy is not a member of the docker group…" | ADDED Req. 1 | Asserts group membership in service of the *old* single-fixed-script model's "only one privileged action" claim; the new model's privileged action is `sudo`-gated per application, not group-membership-gated either way — this specific assertion's premise (one wrapper, one door) no longer describes the mechanism, even though its literal check (no `docker` group membership) may remain true. |
| "Assert the sudoers rule is exactly the fixed, argument-free, wildcard-free invocation…" | ADDED Req. 1 | Asserts `deploy ALL=(root) NOPASSWD: /usr/local/bin/platform-compose-deploy` is the *entire* sudoers state — directly superseded: the new model has one such line **per application** (`app-deploy platform`, `app-deploy commerce-ops`, …), and the referenced script (`platform-compose-deploy`) is itself retired. |
| "Confirm the wrapper script's ownership and permissions…", "Assert the wrapper script is root-owned, mode 0755" | ADDED Req. 1 | Targets `/usr/local/bin/platform-compose-deploy` directly, a retired path; the new model's equivalent is `/usr/local/bin/app-deploy`, taking an argument. |
| "Attempt the one permitted invocation…", "Assert sudo itself did not reject the permitted invocation" | ADDED Req. 1 | Invokes `sudo -n /usr/local/bin/platform-compose-deploy` with zero arguments — the retired invocation shape entirely. |
| "Attempt to append an argument to the wrapper invocation…", "Assert appending an argument to the wrapper invocation is denied" | ADDED Req. 1 | Asserts the *old* mechanism specifically rejects any argument — directly contradicted in shape by the new mechanism, whose whole point is a fixed, enumerated argument (the application name) reaching the privileged script. Not a claim the new tests re-assert in the old form. |
| "Attempt sudo docker directly…", "Assert deploy cannot invoke docker directly with elevated privilege" | Not directly superseded | This assertion's normative content (no raw `docker`/`sudo docker` access) is not restated by either ADDED requirement's own scenario text, but nothing in this change relaxes it either. Flagged for confirmation whether it should be re-asserted under the new model rather than dropped. |
| "Attempt an arbitrary privileged command…", "Assert deploy cannot run an arbitrary privileged command" | Not directly superseded | Same reasoning as the `docker`-direct check above — likely still true, not restated by this change's own scenarios, flagged rather than assumed either way. |
| "Attempt to overwrite the wrapper script…", "Assert deploy cannot modify the wrapper script itself" | ADDED Req. 1 | Targets `/usr/local/bin/platform-compose-deploy` by path directly — retired path. An equivalent check against `/usr/local/bin/app-deploy` (root-owned, not writable by `deploy`) is a reasonable successor but is not itself spec-scenario text in either requirement; not written here as a new test since it wasn't identified as tracing to a stated scenario (see "Derived" discussion above — this pass only wrote what traces to scenario text or explicit tasks.md verification points). |
| "Confirm /opt/platform's ownership and permissions…", "Assert /opt/platform is owned deploy:deploy, mode 0750" | Not superseded | This directory's ownership/mode is unchanged by the new mechanism (design.md: "`/opt/platform` already exists" and is treated identically to every other `/opt/<app_name>`). Likely still valid as-is; flagged only because it sits inside a scenario file whose surrounding assertions are substantially rewritten. |
| "Deploy writes a new Compose file…", "Assert the write succeeded…" | Not superseded | Same reasoning — `deploy` still owns `/opt/platform` and can write into it under the new model; not itself testing the retired wrapper. |
| "Read the wrapper script's content…", "Assert the wrapper applies whatever Compose content is present, with no content validation of its own" | ADDED Req. 1 | Reads `/usr/local/bin/platform-compose-deploy`'s content directly — retired path; the successor script is `/usr/local/bin/app-deploy`. |
| "Assert the deploy account resolves with the fixed /opt/platform home…", "Assert deploy is a real account with home /opt/platform" | Ambiguous — flagged, not asserted either way | Whether `deploy`'s own home directory remains `/opt/platform` once it serves multiple applications is not stated anywhere in this change's artifacts (proposal.md/design.md/tasks.md are silent on it). `per_app_deploy/converge.yml` and `verify.yml` both assume it does (see "Unresolved project questions" below), matching this existing test's assumption, but neither this pass nor the change's own artifacts confirm it — flagged for the implementer to settle, not decided here. |
| "Read deploy's authorized_keys", "Assert only the test-supplied deploy key is authorized" | ADDED Req. 1 | Asserts **exactly one** key is authorized — directly superseded by a per-application multi-key model, where multiple `authorized_keys` lines are the intended, correct state. |
| "Scan this role's committed files for embedded private-key material…", "Assert no private-key marker is committed anywhere under the deploy_user role" | Likely not superseded | This is a generic, path-agnostic repository scan (`grep -rl` for private-key PEM markers across the role's committed files) — its assertion doesn't reference the retired script, the old sudoers shape, or the single-key model at all, and the underlying principle (private key material never committed) is unchanged and, if anything, generalized by this change (proposal.md's Impact section: "New per-application keypairs… never committed here"). Flagged as a candidate anyway, since it sits in a scenario file whose interface (`deploy_user_public_key`) is being retired in favor of `deploy_apps` — it may need no change to its own assertion, only to how/whether it's invoked once `default`'s converge is updated, which is a mechanical concern, not a rewrite of what it asserts. |
| `ansible/roles/deploy_user/molecule/default/converge.yml` (whole file, not a per-task entry) | ADDED Req. 1 / tasks.md 2.1 | Supplies `deploy_user_public_key`, a single-string variable interface tasks.md 2.1 explicitly retires in favor of `deploy_apps` (list of `{name, public_key}`). The file as a whole no longer matches the role's post-implementation interface, independent of any single assertion above. |

## Unresolved project questions / assumptions taken

Recorded per the `testing` skill's convention-question handling — no
channel exists to ask synchronously in this dispatch, so each is recorded
here with the assumption taken and which tests depend on it.

1. **Role variable interface for `deploy_apps`.** Taken directly from
   tasks.md 1.1/2.1 (`list of {name, public_key}`, no default) rather than
   invented — but no implementation exists yet to confirm the role
   actually accepts exactly this shape. All of `per_app_deploy/converge.yml`
   and every assertion in `per_app_deploy/verify.yml` depend on it. If the
   implementer picks a different key name (e.g. `key` instead of
   `public_key`), only `converge.yml`'s `vars:` needs updating to match —
   mechanical, not a rewrite of what's being asserted.
2. **`ghcr_pull_username` is invented, not stated anywhere.** Nothing in
   proposal.md/design.md/tasks.md names a companion username variable for
   `docker login ghcr.io -u <user> --password-stdin`; only `ghcr_pull_token`
   is named (tasks.md 2.3). `per_app_deploy/converge.yml` supplies both;
   if the implementer's task derives the username some other way (e.g. a
   fixed GitHub org/user baked into the task itself, not a variable), this
   converge's extra variable is simply unused, not a defect in the test.
3. **Whether `deploy`'s own home directory remains `/opt/platform` under
   the new multi-application model.** Every new test reading
   `authorized_keys` assumes it lives at `/opt/platform/.ssh/authorized_keys`,
   carried over unchanged from the old mechanism's assumption (see the
   corresponding "Obsolete tests" entry above) — but this change's own
   artifacts never revisit or restate it. If the implementer relocates
   `deploy`'s home (e.g. to something no longer tied to one specific
   application), the `src:` path in "Read deploy's authorized_keys" needs
   updating to match — again mechanical, not a re-derivation of what's
   asserted.
4. **Whether the Molecule test environment has network access to `ghcr.io`
   at all**, and whether the project wants a live, opt-in,
   secret-gated GHCR credential check in Molecule at all, versus treating
   scenario 8 as entirely out of Molecule's scope (fully deferred to
   tasks.md 5.5). This pass took the middle path — write the assertion,
   gate it behind `MOLECULE_GHCR_PULL_TOKEN`, skip explicitly (not
   silently) when absent — but the project has recorded no convention
   either way, since this is the first change to touch GHCR authentication
   at all.
5. **Whether `community.docker.docker_login` or a hand-rolled `docker
   login ghcr.io` shell task is used** (tasks.md 1.6 leaves this open, and
   correspondingly whether `community.docker` needs pinning in
   `ansible/requirements.yml`, alongside `ansible.posix` for
   `key_options`-bearing `authorized_key`, per tasks.md 1.5's own "pin it
   in `ansible/requirements.yml` if newly introduced" note). This pass's
   tests assert only observable host state (`/root/.docker/config.json`
   content, `authorized_keys` content), not which module produced it, so
   neither choice affects what's asserted — flagged here only because
   `per_app_deploy/molecule.yml`'s `dependency:` step (like `default`'s)
   points at `ansible/requirements.yml` and will only pick up whichever
   collection pins are actually added there.
6. **Docker image/OS parity**, and **pinned `molecule`/`molecule-plugins`
   versions** — same caveats already recorded in
   `bootstrap-ansible-host-baseline`'s `test-manifest.md` (points 2–4
   there), carried forward unchanged since neither this environment nor
   this pass had the ability to re-verify them against a live network.

## Test command and test-path glob (as given by the dispatch)

- Test command: `molecule test`, run from within the role's directory
  (`cd ansible/roles/deploy_user && molecule test -s per_app_deploy` for
  the new scenario this pass added; `molecule test -s default` still runs
  the existing, unmodified scenario).
- Test-path glob: `ansible/roles/*/molecule/**/*.yml`.

## What the implementation step must make pass

Once `ansible/roles/deploy_user/tasks/main.yml` (or a new `app_deploy`
role, per tasks.md 1.1's own "or add a new role" framing — see point 1
above) implements `deploy_apps`, `deploy-receive`, `app-deploy`, the
per-application `sudoers.d`/`authorized_keys` rendering, and GHCR
authentication, running `molecule test` from
`ansible/roles/deploy_user/` (or wherever the implementer places these
tasks — see the note on role placement above) against the
`per_app_deploy` scenario must turn the syntax-only baseline above into
every task in `per_app_deploy/verify.yml` passing. If a new role
(`app_deploy`) is created instead of extending `deploy_user`, relocating
`per_app_deploy/` there is a mechanical move, not a rewrite of any
assertion.

This pass adds tests and never subtracts: no existing test was edited,
weakened, or deleted, and no file was written outside
`ansible/roles/*/molecule/**/*.yml` other than this manifest itself.
