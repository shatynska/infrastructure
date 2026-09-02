## Why

This project's Ansible test suite cannot be run, and its playbook cannot be
dry-run. Neither fact was known until `add-ops-account` tried to do both.

`molecule test` is red on `main` for every role that has a scenario, from a
clean checkout — three of the reasons are harness defects that stop any
scenario before its assertions run, and two more are false-positive
assertions inside `deploy_user`'s own scenario that fail against the current
tree regardless of toolchain. And `ansible-playbook playbooks/host-baseline.yml
--check` aborts inside the `tailscale` role, which runs third of five, so
nothing after it is ever evaluated: there is no way to see what a converge
would do to this host before doing it.

The cost is already concrete. `add-ops-account` could not check off its own
`molecule test` task (its `tasks.md` 4.2 records why), had to drive the
scenario's playbooks by hand to verify the role at all, and had to scope its
idempotence check to a single role because the full `--check` run dies before
reaching it. Each of those is a workaround around this change's subject, not a
property of that change.

The deeper problem is that a test suite nobody can execute stops being a test
suite. It still costs review effort and still looks like coverage in a diff,
while establishing nothing — and the longer it stays unrunnable, the more it
drifts from the code it claims to check.

## What Changes

- **Move the test toolchain pins forward** in `ansible/requirements-test.txt`.
  It pins `molecule` and `molecule-plugins` but not `ansible-core`, so a fresh
  install resolves a modern `ansible-core` against a 2023-era Docker driver
  that cannot run on it. Bump both pins to current and add an exact
  `ansible-core` pin, per this project's own "never a floating range"
  convention.
- **Add a Molecule `prepare.yml` to every scenario that converges `docker`.**
  The pinned `geerlingguy.docker` installs a package without refreshing the
  apt cache, which fails against a fresh container. `prepare` is Molecule's
  designated hook for getting an instance into a state where `converge` can
  run, and using it avoids forking a pinned third-party role.
- **Make the GHCR login conditional** on a credential actually being supplied
  (`deploy_user`). Today it runs unconditionally and aborts the converge when
  given the placeholder its own scenario supplies. **This changes production
  behaviour** — see `design.md`; the trade-off was decided deliberately, not
  as a side effect of making tests pass.
- **Make the `tailscale` role check-mode safe.** Its status probe is a plain
  `command`, which Ansible skips under `--check`, after which the next task's
  condition parses an empty string and fails the run.
- **Empty the GHCR placeholder** in the two scenario `converge.yml` files.
  They fall back to a non-empty dummy token when no env var is set, so the
  guard above would never fire and the 403 would recur unchanged. The env
  lookup stays, so a supplied credential still exercises the real path.
- **Repair two self-failing assertions** in `deploy_user`'s `verify.yml`.
  Both fail against the current tree independently of the toolchain: its
  private-key scan matches `verify.yml` itself (the same self-match already
  fixed in `ops_user`'s copy and recorded there as latent here), and its
  "GHCR token not committed in plaintext" scan flags `group_vars/prod.yml` —
  whose token *is* Vault-encrypted, as an inline `!vault` value the scan's
  whole-file test cannot see — plus both scenario `converge.yml` files.
- **Broaden one brittle assertion** in `ops_user`'s `verify.yml`: it accepts
  only two `sudo` refusal phrasings, and the real prod host produces neither.

## Capabilities

### New Capabilities
None. Nothing here grants a capability that did not exist; every item repairs
something that was already meant to work.

### Modified Capabilities
- `iac-host-configuration`: one requirement changes, "Host Authenticates to
  GHCR for Application Image Pulls". It currently reads as an unconditional
  obligation to configure the credential store. Making the login conditional
  on a supplied credential is a change to that normative statement, not an
  implementation detail, so it is recorded as a delta rather than left to be
  discovered in the role.

  The tailnet requirement is deliberately **not** modified: check-mode safety
  is how the role is implemented, not what it is required to achieve, and
  "Host Joins a Private Tailnet" already says what must happen on a real run.

## Impact

- `ansible/requirements-test.txt` — three pins (two bumped, one added).
- `ansible/roles/*/molecule/*/prepare.yml` — new files, one per scenario that
  converges `docker` (`docker`, `deploy_user`, `ops_user`'s `default`).
  `ops_user`'s `revocation-steady-state` already has its own, which creates
  the `docker` group and seeds an account through the role; it installs no
  engine, so it needs no apt refresh.
- `ansible/roles/deploy_user/tasks/main.yml` — one `when` on the GHCR login.
- `ansible/roles/tailscale/tasks/main.yml` — `check_mode: false` on the status
  probe, plus a guard so its consumer cannot parse an empty result.
- `ansible/roles/deploy_user/molecule/default/converge.yml` and
  `ansible/roles/ops_user/molecule/default/converge.yml` — the GHCR
  placeholder fallback becomes an empty string, so the new guard can fire.
- `ansible/roles/deploy_user/molecule/default/verify.yml` — two false-positive
  scans repaired; no assertion re-scoped or weakened.
- `ansible/roles/ops_user/molecule/default/verify.yml` — one assertion's
  accepted string set.
- `ansible/roles/hardening/molecule/default/` — untouched, but in scope for
  verification: it has a scenario and is equally exposed to the toolchain
  bump. Its own apt tasks already set `update_cache: true`, so it needs no
  `prepare.yml`.
- No Terraform, no cloud firewall, no UFW, no `host-baseline.yml` ordering
  change, and no change to any account this project provisions or to what it
  can do.
- Convergence remains a manual operator run; this change does not introduce
  CI for Ansible.

## Non-goals

- **Not a CI pipeline for Ansible.** There still is none, and Molecule stays
  operator-run. Making the suite runnable is a precondition for ever building
  one, not the same thing as building it.
- **Not a change to `ops_user`, or to what any operator account grants.**
  `add-ops-account` is complete and its behaviour is untouched here.
- **Not a fix for this operator's Docker credential-helper problem.**
  Molecule's driver also fails on the current workstation because
  `~/.docker/config.json` names credential helpers (`credsStore`, and a
  `credHelpers` entry) that the driver invokes and that error out. That is
  environment-specific, not a property of this repository: the workaround is
  to point `DOCKER_CONFIG` at a directory containing `{}`. It belongs in the
  README's local-setup notes at most, and is recorded here so the next person
  hitting it does not mistake it for a fourth repository defect.
