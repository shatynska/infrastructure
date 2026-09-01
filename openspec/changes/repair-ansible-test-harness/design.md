## Context

See proposal.md — Why. Each defect below was reproduced during
`add-ops-account`'s implementation; the versions and exit codes are
observations from that session, not expectations.

Confirmed against the repository and against upstream:

- `ansible/requirements-test.txt` pins `molecule==24.12.0` and
  `molecule-plugins[docker]==23.5.3` and does **not** pin `ansible-core`. A
  fresh install therefore resolves `ansible-core` 2.21, whose conditional
  handling the 2023-era Docker driver predates: `destroy.yml` fails on a
  non-boolean conditional, and past that, `create.yml` reads `item.invocation`
  from a registered result that no longer carries it.
- `molecule-plugins` 26.7.15 and `molecule` 26.8.0 exist. That stack, on
  `ansible-core` 2.21.3, ran `molecule create` and `molecule destroy` against
  this repository's real `ops_user` scenario — both exit 0.
- `geerlingguy.docker`'s `setup-Debian.yml` installs `ca-certificates` and
  `python3-debian` with `state: present` and no `update_cache`. Against a
  fresh container it fails with "No package matching 'python3-debian' is
  available". **8.0.0 is the latest release and upstream `master` still has
  it**, so there is no version bump that resolves this.
- `geerlingguy/docker-ubuntu2204-ansible:latest` also lacks `python3-requests`,
  which `community.docker.docker_login` needs on the target.
- `deploy_user`'s GHCR login runs unconditionally. Given the placeholder
  credentials that role's own scenario supplies, ghcr.io answers 403 and the
  converge aborts — two tasks from the end of a role that runs fourth of five,
  so nothing after it is evaluated.
- `tailscale`'s "Check current tailnet connection status" is an
  `ansible.builtin.command` with no `check_mode: false`. Ansible skips
  `command` tasks under `--check`, so the following task's `when` evaluates
  `from_json` against an empty string and errors. `tailscale` runs third of
  five in `host-baseline.yml`.
- There is no CI workflow for Ansible. `.github/workflows/` covers Terraform
  and the platform Compose deploy only.

## Goals / Non-Goals

**Goals:**

- `molecule test --all` runnable to completion from a clean checkout with **no
  credentials supplied**, for every role that has a scenario.
- `ansible-playbook playbooks/host-baseline.yml --check --diff` reaching the
  end of the playbook instead of aborting in `tailscale`.
- Repairs confined to the layer that owns each defect: the test harness where
  the defect is a harness defect, the role where it is a role defect. No
  forking of a pinned third-party role.

**Non-Goals:**

- Beyond proposal.md's non-goals: **no assertion is re-scoped or weakened.**
  Three assertions are touched and all three are false-positive repairs —
  two scans in `deploy_user`'s `verify.yml` that match the repository's own
  correct state, and one accepted-string set in `ops_user`'s. No load-bearing
  condition changes, and nothing that should fail stops failing.

  An earlier draft of this section claimed the scenarios' content was never
  the problem and that they had simply never had the chance to run. That is
  false, and worth correcting rather than quietly dropping: `deploy_user`'s
  scenario contains two assertions that fail against the current tree
  independently of any toolchain defect. See the third decision below.

## Decisions

### Pins move forward, not backward

The obvious reading of "an unpinned `ansible-core` broke a pinned driver" is
to pin `ansible-core` down to whatever the old driver tolerates. That was the
first approach tried, and it works — `ansible-core` 2.18.19 satisfies both
`molecule-plugins` 23.5.3 and `ansible-lint` 26.8.0 (which requires
`!=2.17.*,>=2.16.19`). It is rejected anyway.

Pinning backward makes the pin a permanent debt: it freezes `ansible-core` at
a version chosen by a three-year-old plugin release, and every future tool in
this repository has to be compatible with that choice. Since a current
`molecule-plugins` exists and demonstrably works on current `ansible-core`,
the version constraint is not real — only stale.

So: bump `molecule` and `molecule-plugins[docker]` to current, and add an
exact `ansible-core` pin. The pin is added because this project requires exact
pins ("any external role or collection used for any purpose is pinned to an
exact version, never a floating range" — AGENTS.md); it is deliberately not
the mechanism by which compatibility is achieved.

### `prepare.yml`, not a forked role and not a custom image

Three ways to get an apt cache in front of `geerlingguy.docker`:

1. **Fork or patch the pinned role.** Rejected outright: this project pins
   external roles precisely so their content is not this repository's to
   maintain, and a fork silently detaches from upstream fixes.
2. **Build a custom base image with a warm cache.** Rejected: it introduces an
   image to build, host and refresh, and a warm cache baked at image-build
   time goes stale exactly like the one being worked around.
3. **A Molecule `prepare.yml` per scenario.** Chosen. `prepare` exists for
   this: it runs once, after `create` and before `converge`, and is explicitly
   the place to bring an instance to a state where the role under test can
   run. It is not re-run for the `idempotence` action, so it cannot mask a
   role's own non-idempotence.

`python3-requests` is installed in the same task, for the same reason and with
the same justification — the base image lacks a library a converged role's
module needs. It belongs beside the apt refresh, not in a separate mechanism.

The one thing `prepare.yml` must not become is a place where the thing under
test is quietly set up. Each file gets a comment saying it is fixture only,
and naming the upstream defect it works around, so a later reader can tell
whether it is still needed.

### The scenarios' own placeholder has to go, or the guard is inert

The guard tests both credential halves (tasks.md 4.1 has the exact form), and
on its own it changes nothing: both scenario `converge.yml` files set

    ghcr_pull_token: "{{ lookup('env', 'MOLECULE_GHCR_PULL_TOKEN')
                         | default('dummy-molecule-placeholder-token-not-real', true) }}"

so with no environment variable set the value is a non-empty placeholder, the
guard evaluates true, the login runs, and ghcr.io returns the same 403. The
guard would ship, the spec delta would ship, and the defect would be exactly
where it was.

The fix is to make the fallback an empty string in both files, keeping the
`MOLECULE_GHCR_PULL_*` lookup so a supplied credential still exercises the
real path. The alternative — teaching the guard to recognise the placeholder
string — is rejected outright: it would put test-fixture knowledge inside a
production role, and would silently skip a real credential that happened to
match.

### `deploy_user`'s scenario has two assertions that fail on a correct tree

Both are false positives against the repository as it stands, and neither is
about this change's subject:

1. Its private-key scan greps `{{ playbook_dir }}/../..` — the `deploy_user`
   role directory, which contains `verify.yml` itself — for the literal
   marker strings the scan is built from. It therefore matches its own text.
   This is the same self-reference already fixed in `ops_user`'s copy, whose
   comment records it as latent here. The repair is the same: assemble the
   pattern at run time so the file does not contain the string it searches
   for.
2. Its "GHCR token is never committed in plaintext" scan tests each matching
   file with `head -c 15 "$f" | grep -q '^$ANSIBLE_VAULT'` — a whole-file
   encryption test. `ansible/inventory/group_vars/prod.yml` holds its token as
   an **inline** `!vault` value inside an otherwise plaintext file, which is
   the project's documented pattern and is correct. The scan cannot see that
   and flags it, along with both scenario `converge.yml` files. The repair is
   to accept an inline `!vault` value and to exclude scenario fixtures.

Neither repair weakens what the assertion establishes: a real committed
private key, and a real plaintext token, both still fail. This is the reason
the Non-Goals correction above matters — "the suite has never had a chance to
run" was true of the harness and false of these two.

### The GHCR guard changes production behaviour, and that is accepted

A `when` on the login task, testing that both credential halves are non-empty
(tasks.md 4.1). The operator chose this over the alternative (leave the role
alone; require a real `read:packages` token to run the suite).

**What is given up, stated plainly:** today a rotated, revoked or mistyped
GHCR token fails the converge, loudly, at the moment the host is configured.
After this change, an *absent* credential is silently fine, and the failure
that would have surfaced at converge instead surfaces at the next
`docker compose pull` during a deploy — later, in a different pipeline, and
more expensive to diagnose.

The likeliest real-world instance of that is not a bad token at all: it is a
**variable that is misnamed, or a vars file that is not loaded**, on a host
that genuinely does need the credential. Before this change that aborts the
run; after it, it is an ordinary `skipping:` line indistinguishable from a
deliberate absence. Because that case is both the most probable and the
quietest, the skip branch is made to say so explicitly rather than passing in
silence — an absent credential is a legitimate configuration, but it should
never be an invisible one.

The guard also tests `ghcr_pull_username`, not just the token. A token
supplied without a username would otherwise pass the guard and then fail on an
undefined variable — an error that matches none of the delta's scenarios and
reads as a bug rather than as a misconfiguration.

**What is bought:** the entire test suite becomes runnable offline with no
credential at all. Requiring a real registry token to run tests means a fresh
checkout cannot be verified, that the token must be distributed to anyone who
wants to run them, and that the suite's health depends on a credential's
lifetime. That is a worse failure mode than the one being accepted, because it
degrades silently into "nobody runs the tests".

The guard is deliberately narrow, and the spec delta says so: it tolerates a
credential being **absent**, not a supplied credential being **rejected**. A
403 against a real token still fails the run. This matters — a guard written
as "ignore errors from docker_login" would have bought the same testability
while discarding the fail-fast property entirely, and it is not what is being
done here.

### `check_mode: false` plus a guard, not one or the other

The `tailscale` status probe is read-only (`tailscale status --json`), so
running it under `--check` is safe and is what `check_mode: false` is for.
That alone fixes the reported failure.

The guard on its consumer is added anyway. `check_mode` is not the only way
that task can produce an empty `stdout` — a `tailscaled` that is installed but
not yet answering does it too — and a conditional that parses unvalidated
command output is fragile independently of check mode. Fixing only the
symptom that happened to be observed would leave the same class of failure
reachable by a different route.

## Risks / Trade-offs

- **A major toolchain bump changes more than the driver.** `molecule` 24 → 26
  spans behaviour beyond the docker plugin; a scenario that passes today could
  fail on something unrelated to the defects being fixed. → Mitigated by the
  success criterion being every existing scenario green, not just the ones
  touched here. A failure surfaced by the bump is in scope to diagnose; if it
  turns out to be a genuine incompatibility rather than a latent defect, that
  is the signal to reconsider the version, and the finding is recorded either
  way.
- **The GHCR guard's cost is real and deferred.** A revoked token now fails at
  deploy time, not converge time. → Not mitigated away, by choice. Recorded
  here, in the spec delta's own normative text, and in `deploy_user`'s README,
  so the next person reading any of the three finds it rather than
  rediscovering it during an outage.
- **`prepare.yml` files outlive their reason.** If upstream ever adds
  `update_cache`, these become inert and their comments become misleading. →
  Each file names the exact upstream task and the version checked, so the
  check is a version comparison rather than an investigation.
- **Nothing enforces that the suite stays runnable.** With no CI for Ansible,
  the same rot can recur the moment a dependency shifts. → Out of scope and
  deliberately so (proposal.md, Non-goals), but worth naming: this change buys
  a working suite, not a suite that stays working. That is what an Ansible CI
  job would buy, and this change is its precondition.
- **The verified stack was verified on one machine.** `create`/`destroy` was
  proven on Python 3.12 against this operator's Docker. → The change's own
  verification step re-runs the full suite rather than trusting the earlier
  observation.

## Migration Plan

No host state changes and nothing needs to be rolled out. The role edits are
the only two that change host behaviour, and only in cases that currently
abort the run; everything else is test-harness-only.

Rollback is `git revert` — there is no converged artifact to undo. The one
consideration is ordering: the `tailscale` fix should be verified by an actual
`--check` run against prod before this change is considered done, since that
run is the only way to observe the defect it fixes.
