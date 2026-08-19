# Test manifest — bootstrap-ansible-host-baseline

Written by the `openspec-test-writer` dispatch, before implementation.
**This file is not part of the OpenSpec schema** — `openspec instructions
apply` will not surface it among a task's context files. Read it on
purpose before implementing any task in `tasks.md`.

No implementation exists yet (`ansible/playbooks/` and `ansible/roles/`
held only `.gitkeep` before this pass). All tests below are written
against the change's delta spec and the two pre-existing
`iac-host-configuration` requirements it implements for the first time —
never against implementation source, because none exists to read.

## Baseline

**No baseline could be taken.** `which ansible ansible-playbook
ansible-lint molecule` found none of them installed in this environment
(`python3 -m pip show molecule` confirms molecule itself is absent), and
even with them installed, the three roles under test don't exist yet — a
pre-existing-suite run isn't meaningful here (the target-absent situation,
per the `testing` skill). What I *did* run: a `yaml.safe_load_all` parse
of every new file under the test-path glob
(`ansible/roles/*/molecule/**/*.yml`), confirming no YAML syntax defects.
That is a syntax check, not a baseline, and is reported as such rather
than as a substitute for one.

## Scope note: which requirements these tests cover

The change's own delta spec
(`specs/iac-host-configuration/spec.md`) carries exactly one ADDED
requirement, "Restricted Deploy Account for Platform Stack Access," with
four scenarios — all four are enumerated and accounted for below. This
change has no MODIFIED, REMOVED, or RENAMED delta.

Per this dispatch's explicit instructions, I additionally derived tests
for two **pre-existing, unmodified** `iac-host-configuration` requirements
(under `openspec/specs/iac-host-configuration/spec.md`, not this change's
delta) that this change implements in working Ansible content for the
first time: "Container Runtime Installed via Pinned External Role or
Equivalent" and "Host-Level Security Owned by Ansible, Cloud Firewall
Owned by Terraform." These are listed separately below since they are not
part of the change's own delta-scenario count, but every scenario touched
is still accounted for.

## Delta-spec scenario accounting (4/4)

Requirement: **Restricted Deploy Account for Platform Stack Access**
(ADDED, `ansible/roles/deploy-user`)

| # | Scenario | Test(s) | Status |
|---|---|---|---|
| 1 | Deploy account's privileged access is a single fixed action, not arbitrary command injection | `ansible/roles/deploy-user/molecule/default/verify.yml` — tasks: "Assert deploy is not a member of the docker group…", "Assert the sudoers rule is exactly the fixed, argument-free, wildcard-free invocation…", "Assert the wrapper script is root-owned, mode 0755", "Assert sudo itself did not reject the permitted invocation", "Assert appending an argument to the wrapper invocation is denied", "Assert deploy cannot invoke docker directly with elevated privilege", "Assert deploy cannot run an arbitrary privileged command", "Assert deploy cannot modify the wrapper script itself" | Covered |
| 2 | Deploy account can escalate via the content it is entitled to write | `ansible/roles/deploy-user/molecule/default/verify.yml` — tasks: "Assert /opt/platform is owned deploy:deploy, mode 0750", "Assert the write succeeded…", "Assert the wrapper applies whatever Compose content is present, with no content validation of its own" | Covered (see note below) |
| 3 | Deploy account is provisioned independently of any operator | `ansible/roles/deploy-user/molecule/default/verify.yml` — tasks: "Assert deploy is a real account with home /opt/platform", "Assert only the test-supplied deploy key is authorized", exercised by `converge.yml` deliberately supplying no operator/personal-key variable | Covered |
| 4 | Deploy private key is never committed | `ansible/roles/deploy-user/molecule/default/verify.yml` — task: "Assert no private-key marker is committed anywhere under the deploy-user role" (static repo scan, `delegate_to: localhost`) | Covered |

**Note on scenario 2**: its normative content is that content-layer
escalation is *not* prevented and is explicitly out of scope for this
account's restriction mechanism. Per this dispatch's instructions, no test
asserts escalation is blocked here. The tests instead positively confirm
the scenario's actual THEN clause: deploy is entitled to write into
`/opt/platform`, and the wrapper applies whatever is there with no content
validation of its own (asserted by checking the wrapper script's content
contains no inspection/validation logic). This is deliberately *not* an
end-to-end proof that a hostile Compose file reaches root — see
"Deliberately uncovered" below for why that step is out of scope for this
role's isolated scenario.

## Additional coverage: pre-existing requirements this change implements first

| Requirement | Scenario | Test(s) |
|---|---|---|
| Container Runtime Installed via Pinned External Role or Equivalent | External role version is pinned | `ansible/roles/docker/molecule/default/verify.yml` — "Assert geerlingguy.docker is pinned to an exact X.Y.Z version, not a floating range" (static check against committed `ansible/requirements.yml`) |
| Host-Level Security Owned by Ansible, Cloud Firewall Owned by Terraform | Host firewall rules are Ansible-managed | `ansible/roles/hardening/molecule/default/verify.yml` — UFW active/default-deny/SSH-allowed/HTTP-HTTPS-closed-by-default assertions, plus a second in-`verify` role invocation with `hardening_web_allowed_cidrs` set asserting HTTP/HTTPS open once configured |

Fail2ban assertions in the same `hardening` verify.yml (active service, an
`sshd` jail present) are **derived**, not tied to a named scenario: the
requirement's own text says Ansible "SHALL own host-level security
controls: the host firewall, intrusion prevention, SSH hardening…" but no
scenario names fail2ban specifically. Recorded as derived per `testing`'s
classification rule, not as satisfying a scenario that doesn't exist.

The requirement's second scenario, "External exposure changes go through
the cloud firewall," is a process constraint about *where* a reachability
change is made (Terraform, not solely a host-level rule) — not a host
state Molecule can observe by converging a role. Not tested; recorded here
rather than silently skipped.

## Assertion classification

- **Specified** (traces to a stated scenario's THEN clause):
  - All scenario 1 assertions except the wrapper-overwrite one (docker
    group absence, exact sudoers line, argument rejection, no direct
    `docker`/arbitrary-command access).
  - Scenario 2's "write succeeds" and "wrapper applies content with no
    validation" assertions.
  - Scenario 3's account-exists / key-installed assertions.
  - Scenario 4's private-key-scan assertion.
  - Docker role's exact-pin assertion.
  - Hardening role's UFW active / default-deny / SSH-allowed /
    HTTP-HTTPS-closed-by-default / HTTP-HTTPS-open-when-configured
    assertions ("Host firewall rules are Ansible-managed").
- **Derived** (inferred, no scenario states it directly, labeled inline in
  each file's comments too):
  - Wrapper script's root:root/mode-0755 ownership check, and the
    "deploy cannot overwrite the wrapper" check — support the "fixed
    script" premise scenario 1 depends on, but the scenario text doesn't
    itself specify file mode/ownership values (those come from
    `design.md`/`tasks.md` 3.3).
  - `/opt/platform` ownership/mode (`deploy:deploy`, `0750`) — from
    `design.md`/tasks.md 3.1, not the spec text itself.
  - Docker role's "docker.service is active / `docker info` succeeds"
    assertions — the spec scenario only covers the *pin*, not runtime
    behavior; this traces to design.md's stated Goal instead.
  - Hardening role's fail2ban assertions (see above).
- **Deliberately untested** (identified, not silently dropped):
  - An actual end-to-end run of `docker compose pull && docker compose up
    -d --wait` through the wrapper against real Compose content. The
    `deploy-user` role's Molecule scenario deliberately does not install
    Docker (see its `molecule.yml` comment) to keep this role's tests
    independent of the `docker` role, per design.md's "each can be
    run/tested independently" rationale. Full end-to-end verification
    (Docker installed, UFW/fail2ban active, deploy account working
    together) is tasks.md 4.3/4.4/4.5's job — a manual/CI check against a
    real or disposable host, not a per-role Molecule scenario under this
    project's one-scenario-per-role convention.
  - "External exposure changes go through the cloud firewall" scenario
    (see table above) — a process constraint, not host state.
  - tasks.md 2.3 (documenting UFW/Terraform sync in the role's README) —
    a documentation task, not a scenario in either the delta spec or the
    two pre-existing requirements named for this pass; no observable host
    behavior to assert on.
  - Idempotency (tasks.md 4.5, "re-run reports no changes") is exercised
    automatically by Molecule's own `idempotence` step within `molecule
    test`, re-running each role's `converge.yml` — not a hand-written
    assertion of mine, so not claimed as one, but worth noting it's
    covered by the test *command* itself, not by content I authored.

## Obsolete tests

**Not applicable.** This change carries no MODIFIED, REMOVED, or RENAMED
delta — only ADDED. There is also no prior `test-manifest.md` for this
change (none was supplied to this dispatch), and no pre-existing test
content exists anywhere under the test-path glob
(`ansible/roles/*/molecule/**/*.yml` was entirely empty before this pass —
`ansible/roles/` held only `.gitkeep`). Nothing to search for, nothing
found.

## Unresolved project questions / assumptions taken

Recorded per the `testing` skill's convention-question handling — no
channel exists to ask synchronously, so each is recorded here with the
assumption taken and which tests depend on it, for confirmation before or
during implementation.

1. **Role variable interface.** No implementation exists, so I invented
   variable names the tests assume the roles will expose:
   `hardening_ssh_allowed_cidrs` / `hardening_web_allowed_cidrs` (hardening
   role) and `deploy_user_public_key` (deploy-user role). Every test in
   `hardening/molecule/default/{converge,verify}.yml` and
   `deploy-user/molecule/default/converge.yml` depends on these exact
   names. If the implementer picks different names, either the role
   should accept these, or these test files' `vars:` need updating to
   match — that update is additive/mechanical, not a rewrite of what's
   being asserted.
2. **`community.general` collection likely needed, not currently pinned.**
   The `hardening` role's UFW tasks will plausibly need
   `community.general.ufw` (the standard idiom for UFW in Ansible), but
   `ansible/requirements.yml` does not currently pin the
   `community.general` collection. Flagged as a probable gap for the
   implementer to close (add and pin it) rather than assumed silently;
   the hardening/deploy-user `molecule.yml` files' `dependency:` step
   already points at `ansible/requirements.yml` so the pin will be
   installed automatically once added.
3. **Test image OS does not match production exactly.** All three
   scenarios use `geerlingguy/docker-ubuntu2204-ansible:latest` (a
   systemd-capable Molecule image) as the closest available match; the
   actual target per `terraform/environments/prod/terraform.tfvars` is
   `ubuntu-26.04`. No systemd-capable Molecule image pinned to that exact
   release was available to select with confidence from this environment.
   Flagged for the implementer to confirm or swap.
4. **Pinned test-dependency versions unconfirmed against PyPI.**
   `ansible/requirements-test.txt` pins `molecule==24.12.0` and
   `molecule-plugins[docker]==23.5.3` — exact pins per convention, but
   chosen without the ability to query PyPI from this environment.
   Confirm these resolve, or bump to whichever exact versions do.
5. **`sudo -n` non-interactive denial message wording.** The scenario-1
   negative assertions (argument injection, direct `docker`, arbitrary
   command) check for `'password is required'` or `'not allowed'` in
   `sudo -n`'s stderr, which is standard `sudo` behavior but was not
   verified against a live `sudo` binary in this environment. If a given
   `sudo` build's non-interactive denial message differs, the assertion on
   message text (not on non-zero `rc`, which is checked separately) may
   need adjusting — flagged rather than silently assumed correct.

## Test command and test-path glob (as given by the dispatch)

- Test command: `molecule test`, run from within each role's directory
  (`cd ansible/roles/<role> && molecule test`).
- Test-path glob: `ansible/roles/*/molecule/**/*.yml`.
- New pinned test dependency file: `ansible/requirements-test.txt` (`pip
  install -r ansible/requirements-test.txt`).

## Files written by this pass

- `ansible/requirements-test.txt`
- `ansible/roles/docker/molecule/default/{molecule.yml,converge.yml,verify.yml}`
- `ansible/roles/hardening/molecule/default/{molecule.yml,converge.yml,verify.yml}`
- `ansible/roles/deploy-user/molecule/default/{molecule.yml,converge.yml,verify.yml}`
- `openspec/changes/bootstrap-ansible-host-baseline/test-manifest.md` (this file)

No playbook or role implementation code was written. No existing test was
edited, deleted, or disabled (none existed). No file was written outside
`ansible/roles/*/molecule/**/*.yml`, `ansible/requirements-test.txt`, or
this manifest.
