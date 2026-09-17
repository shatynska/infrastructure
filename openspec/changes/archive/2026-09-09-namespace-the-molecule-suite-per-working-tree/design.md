## Context

See proposal.md — Why. What follows is only what shapes the approach.

Everything below marked *verified* was established by running the pinned toolchain (`molecule==26.8.0`, `ansible-core==2.21.3`) on 2026-09-09, against a synthetic role and a real container, rather than by reading Molecule's source alone. Where a claim rests on reading source, it says so.

Three facts about the mechanism, all verified:

- **The instance name** is a literal in each scenario's `platforms[].name`. `${VAR}` interpolation in that field works end-to-end — `create`, `converge`, `idempotence`, `verify`, `destroy` all succeeded against a container named from the environment, and it was destroyed cleanly.
- **The ephemeral directory** is `$ANSIBLE_HOME/tmp/molecule.<id>.<scenario>`, and `<id>` is `checksum(basename(role_directory), 4)` (read from `molecule/scenario.py`). It is therefore identical across working trees **by construction**, which is why relocating a working tree does not escape it. Confirmed against the live machine: computing the checksum for each role reproduces the ids recorded from a different working tree two days earlier — `deploy_user → dnU2`, `ops_user → E127`, `docker → 1UjF`, `hardening → HeLe`, `platform_data_volume → Dp-1`.
- **Molecule does not remove the ephemeral directory after a clean run.** A `molecule test` that exited 0 left `molecule.K_CD.default` in place.

And one correction to what this change was queued believing: `~/.cache/molecule/
<role>` is **not a live handle** under the pinned toolchain. The only such
directory on this machine is dated 2026-09-01 and holds an older layout. Two
handles, not three.

## Goals / Non-Goals

**Goals:**

- A Molecule result obtained while another session is running the suite means what it appears to mean.
- The failure mode of forgetting the mechanism is a refusal, not a shared container.
- `AGENTS.md`'s shared-service rule acquires the binding it has always promised.

**Non-Goals:**

- Serialising sessions. `flock` was considered and is not the answer: it stops two runs overlapping in *time* and does nothing about a run inheriting a directory an earlier session left behind — the failure observed on 2026-09-07 had no concurrent process at all.
- Reworking the test sequence. The suite is not broken on its own; the same `destroy`-then-`create` sequence runs clean on handles a working tree owns.
- Fixing `molecule test --all`'s stop-at-first-failure behaviour. That is its own queued change, and this one must merely not foreclose it.
- Namespacing anything other than Molecule. The binding section names the rule's first service; it does not claim to be the last.

## Decisions

### 1. `ANSIBLE_HOME`, not `MOLECULE_EPHEMERAL_DIRECTORY`

The queue entry named `MOLECULE_EPHEMERAL_DIRECTORY` as "the only lever". It is the wrong one. Read from `molecule/scenario.py` and confirmed by running: that variable names **one directory outright** — Molecule appends no per-scenario suffix to it — so a single exported value collapses every scenario of every role into one directory. `molecule test --all` would then run a role's scenarios through shared state, which is the hazard being fixed, reintroduced inside a single run.

`ANSIBLE_HOME` moves the tree and leaves the `molecule.<id>.<scenario>` split intact. *Verified*: with it set, the run's inventory resolved to `<namespace>/tmp/molecule.K_CD.default/inventory`, and the shared `~/.ansible/tmp/` was untouched — its newest entry still bore an earlier session's timestamp after the run completed.

**Alternative considered — leave the ephemeral directory shared.** Rejected: inheriting a directory another tree left is the *default* rather than the exception, because the id is stable per role and Molecule does not clean up.

### 2. Collections are shared, not reinstalled per namespace

`ANSIBLE_HOME` also relocates `$ANSIBLE_HOME/collections`, which is where the docker driver finds `community.docker`. *Verified*: a fresh namespace fails at `create` with `couldn't resolve module/action 'community.docker.docker_login'`.

Pointing `ANSIBLE_COLLECTIONS_PATH` at the shared collections resolves it, and the run then completed in full. Collections are read-only content pinned by `ansible/requirements.yml`, not run state: two sessions reading them cannot interfere, which is precisely what is not true of a container or an inventory.

**Alternative considered — install collections into each namespace.** Correct but wasteful: every working tree would re-download pinned content that cannot differ, and the provisioning step would grow a network dependency. Recorded because it becomes the right answer if a future scenario ever *writes* under the collections path.

**Where the shared path comes from, since sharing it does not conjure it.** On a machine that has never installed the pinned Galaxy content, the entry point produces the *identical* `community.docker.docker_login` error this decision cites as the symptom of the wrong lever — the same message for an unprovisioned machine and for a misconfigured mechanism, which misdirects diagnosis at exactly the moment it is hardest. The entry point therefore checks the shared path before running and, where it is absent, fails naming the one-time install rather than letting Molecule fail obscurely. `AGENTS.md`'s binding section names that step too, since `AGENTS.md` already warns that verification which cannot reach what it needs is indistinguishable from a pass.

### 3. The namespace is derived from the working tree, and is readable

`<sanitised basename>-<short digest of the absolute path>`.

Deterministic, which is required rather than merely nice: a later session in the same working tree must resolve the *same* container in order to destroy one an earlier run left behind. The digest covers the case the basename alone does not — two clones of this repository on one machine, whose worktree basenames are drawn from the same change names.

**Alternative considered — the digest alone.** Rejected on the strength of this change's own subject: the question a session asks when it meets an unexpected container is *whose is this*, and `deploy_user-role-instance-a3f9c1d2` does not answer it while `deploy_user-role-instance-defer-dns-in-terraform-a3f9c1` does. Readability is the feature here, not a luxury.

### 3a. The readable name needs an explicit short `hostname` beside it

Review raised this and it was right: the name is bounded by something the design had not examined. *Verified* — the docker driver derives a container's hostname from its instance name, and Linux caps a hostname at 64 bytes, so a realistic name fails at `create` with `Bad Request ("hostname is too long (maximum 64 bytes)")`. The case tested was this change's own working tree: `wt-spike-instance-namespace-the-molecule-suite-per-working-tree-a3f9c1`, 70 characters. Left unbounded, every scenario would have failed on exactly the working trees this repository's change names produce — including the one implementing this change. The original spike used a synthetic role with a short name and could not have found it.

The fix keeps Decision 3 whole rather than retreating from it: each platform declares an explicit short `hostname` alongside the long readable `name`. *Verified* — the same 70-character name creates successfully with `hostname: wt-spike` declared, `docker ps` shows the full readable name, and `docker inspect` confirms the hostname is the short one. Readability lives in the name, which is what an operator reads; the limit applies to the hostname, which nothing here needs to be unique or meaningful.

**Alternative considered — truncate the basename to a fixed width.** Cheaper, and it keeps one field instead of two, but it spends the readability this design just argued for, and the truncation point would fall inside change names that share a prefix. **The digest-only form** remains rejected for the reason Decision 3 gives.

The hostname need not be unique across working trees, so it stays a short literal per scenario rather than becoming a second thing to namespace. What resolves a container to another container is its *name* and its network aliases, which Docker's embedded DNS registers and which remain namespaced; the hostname is what the host calls itself from the inside, and no scenario here addresses another by it.

That is not free of consequence, and the task list carries the check rather than the design asserting it away: declaring a hostname changes what `ansible_hostname` and `ansible_nodename` resolve to inside every container, from the instance literal to the short name. A role or scenario reading either would change behaviour, which is why the sweep before the rename covers each role's own files and not only the scenario directory.

### 4. The unset default fails closed, by being an invalid container name

This is the decision the change turns on. Molecule's interpolator substitutes **empty** for an unset `${VAR}` and has no `:?` error form — read from `molecule/interpolation.py`, whose `_resolve_named` supports only `:-` and `-`. So the naive spelling fails *open*: a session that forgets the variable gets the old shared name back, silently, in a change whose entire purpose is to stop a run passing against another session's container.

The default is therefore a sentinel containing a character Docker forbids in a container name. *Verified*: `create` fails with `Invalid container name … Bad Request`, no container is created, and the sentinel text appears in the error — so the message says what to set.

**Alternatives considered.** A benign sentinel (`…-unset`) makes the mistake *visible* in `docker ps` but still lets two forgetful sessions collide, which is the same fail-open wearing a label. A guard play inside each scenario would fire only at `prepare`, which is *after* `create` — it would detect the collision having already made it. Neither closes the gate; this does.

**What this deliberately does not close, stated plainly.** A run with no namespace set writes to the shared *ephemeral directory* before `create` reaches the container name and refuses. That is a nuisance failure of the kind `AGENTS.md`'s Testing section already teaches a session to recognise, not a silent pass, and it is the residue this design accepts. The dangerous failure — a green run against someone else's container — is closed.

The requirement is written to that boundary rather than past it: it forbids sharing state *from which a result could be produced*, and says so, because a prohibition on sharing anything at all would be one this mechanism does not honour. Proposal records the same acceptance, so all three artifacts agree on what is guaranteed.

**That carve-out is conditional, and the condition is the sentinel.** The ephemeral directory is not intrinsically incapable of carrying a result — a stale `instance_config.yml` beside another tree's live container is exactly a pass-carrying combination. What makes the sharing harmless is that the only runs which reach the shared tree are namespace-less ones, and those abort at `create` before any play can produce a result. So the static check on the default's form is not a tidiness assertion: it is what holds this carve-out true, and the requirement's obligation on that default exists for the same reason.

There is a stronger form worth naming, since review raised it and it is not taken here. If the namespace were derived so that supplying it by hand were impractical, possessing a valid one would imply having run the entry point that also sets `ANSIBLE_HOME` — turning wrapper discipline into a consequence of the sentinel rather than a convention beside it. It is rejected for this change because it trades a legible, hand-computable namespace for an opaque one, and Decision 3 has just argued that legibility is the feature. It is recorded in `docs/deferred-work.md` rather than lost, because the trade could reasonably be made differently later.

### 5. The variable is not `MOLECULE_`-prefixed

Molecule holds `${MOLECULE_*}` references back through its first interpolation pass and resolves them in a second, whose own source comment reads "This is probably __very__ bad". A `MOLECULE_`-prefixed name does work — checked — but this change has no reason to depend on that path. A plainly-named variable is substituted in the first pass like any other, which is the behaviour the end-to-end spike exercised.

### 6. One documented entry point, and the static check is what enforces it

A wrapper computes both values from the working tree and runs Molecule with them, so the correct invocation is the easy one. But a wrapper cannot bind a session that types `molecule test` directly, so it is not the enforcement — the sentinel is, at run time, and `.github/tests` is, at review time, by asserting that every authored scenario's name carries the namespace and the sentinel.

The assertion reuses the discovery the digest-pin checks already use (`authored_scenario_files`), so a scenario added later is covered without an edit, and Galaxy-installed content is excluded by the same manifest-derived rule rather than by a second list that could drift from the first.

### 7. The requirement lives in `iac-repo-foundations`

Its stated purpose is "repo scaffolding and local developer quality gates", and this hazard is local: continuous-integration runners are isolated by construction and never observe it. The *static* obligation over scenario files attaches instead to `iac-cicd-pipeline`'s existing Ansible-verification requirement, beside the digest-pin obligations that already read the same files through the same suite — one mechanism, not two.

## Risks / Trade-offs

- **The sentinel makes every existing invocation fail until it is updated, including CI's.** → Intended, and the reason it is safe: the failure is loud, immediate, at `create`, and names what to set. The task list updates the workflow in the same change, and the suite's own assertions fail if a scenario is left without the namespace.
- **`ANSIBLE_HOME` per working tree adds a provisioning step**, and `AGENTS.md` already warns that verification which cannot reach what it needs *skips and reports success*. → The collections decision keeps the step to setting variables rather than installing anything, and the entry point sets them, so the step is "use the entry point" rather than a new manual ritual.
- **Namespaces accumulate.** Nothing here reclaims one, exactly as `AGENTS.md` says of namespaces generally. → Accepted and stated rather than solved; the ephemeral tree under a removed working tree is inert, and removing it is cheap.
- **Readable names are long.** `docker ps` output gets wider. → Accepted; the alternative optimises for column width against the one question the operator actually asks.
- **The verification of this change is itself subject to the hazard it fixes.** A session testing it while another runs the suite could observe either outcome for the wrong reason. → The implementation's own verification must run with the namespace set, and must confirm the container name it created rather than only that the run went green.

## Migration Plan

No deployment and no rollback: nothing here reaches a host. The change lands in one pull request, and a session already mid-run when it merges is unaffected — its next run picks up the new scenario files and the new entry point together.

## Open Questions

None that can be deferred. The two that could have changed the approach — which lever relocates the ephemeral directory, and whether an unset namespace can be made to fail — were settled by spike before this document was written.
