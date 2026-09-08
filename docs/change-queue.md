# Change queue

Identified changes, recorded rather than opened. An entry is deleted when its
change is archived. See `AGENTS.md`, "A second change surfacing".

Everything here came out of a full-repository audit on 2026-09-06 (trunk at
`245ef59`). That audit's verdict was that the architecture is sound and needs
no restructuring; what follows is maintenance, not redesign.

Three of the audit's findings were ready to act on and were **opened** instead
of queued — they had branches and handoffs, not entries here:

- `fix-volume-discovery-and-consistency` — an unreachable assert, pin drift.
  **Archived 2026-09-07** (PR #66). Entries 3a, 3b, 3c and 3d below were opened
  by it.
- `refresh-readme-accuracy` — README statements that are no longer true

`decide-archived-change-reference-policy` — the citation form live source uses
for this repository's own change records, and a check that enforces it.
**Archived 2026-09-07** (PR #70). It delivered the former entries 1 and 2, which
are gone with it, and unblocked entry 3; entries 8 and 8a below were opened by
verifying it.

Most entries below are queued because they are **blocked on something that must
happen first**, and they are listed in dependency order. Where an entry is not
blocked, it says instead why it was recorded rather than folded into the change
that found it — usually because it belongs to a different concern than the one
that change was closing.

---

## 3. separate-history-from-rationale-in-source-comments

**No longer blocked.** It waited on the citation-form decision and on the
sweep that followed it; both were delivered by
`decide-archived-change-reference-policy` (archived 2026-09-07, PR #70), which
also converted every citation in the comment blocks below. What remains here is
the separation this change deliberately did not do: it changed citation *form*
only, and left the prose around it alone.

Source comments in this repository currently mix three kinds of text with no
way to tell them apart:

- **why the code is shaped this way** — irreplaceable, keep it. The tailnet
  polarity note (`ansible/roles/tailscale/tasks/main.yml:76-82`) and the GHCR
  tolerated/not-tolerated block (the `ghcr_pull_*` comment block in
  `ansible/roles/deploy_user/tasks/main.yml`)
  are load-bearing and must survive any pass.
- **what a past change did** — git log and the archive already own this.
- **a TODO whose condition has passed** — dead, and quietly misleading.

Only the first kind survives archiving. Concrete instances of the other two
(the `platform/docker-compose.yml` header, formerly listed first, was removed
by `fix-volume-discovery-and-consistency`, which was editing that file anyway):

- `terraform/environments/prod/ssh_key.tf:20-28` — a `moved` block that
  documents its own removal condition ("Safe to delete once the next apply has
  run") from a change archived 2026-08-18.
- `terraform/environments/prod/main.tf:19-21` — explains a value the file no
  longer holds.

The tailscale role is 48 comment lines against 90 non-blank; this is a style
question with a real maintenance cost, not a cosmetic one.

## 3a. decide-multiple-volume-selection-policy

**Not blocked on anything; recorded rather than folded in, because it is a
policy decision about the host rather than a defect.**

`fix-volume-discovery-and-consistency` made `platform_data_volume`'s device
discovery deterministic: where more than one `/dev/disk/by-id/scsi-0HC_Volume_*`
device is attached, it now sorts and takes the first instead of taking whatever
`find` returned first. That closes the nondeterminism, and a PAIR of Molecule scenarios holds it
closed: `multiple-devices-discoverable` and `multiple-devices-reverse-order`, one per
directory-read arrangement. Either alone is weaker than it looks — the first
catches a role selecting `files[0]`, the second one selecting `files | last`.

What it does **not** decide is whether a deterministic pick is the right
behaviour at all. The alternative — fail when discovery matches more than one
device, on the grounds that an ambiguous pick is worse than a refusal — was
considered in that change's `design.md` Decision 2 and rejected *for that
change*, not on the merits: the role does not own what else may be attached to
the host, and a second Hetzner Volume mounted for a reason unrelated to
`platform/` would then break `host-baseline.yml` for every host.

Deciding it needs an answer to a question that is the operator's: is a second
attached volume something this project ever expects, and if so, should the role
be told which one is `main-data` rather than inferring it? Note that being told
is close to the `linux_device` hand-copying that `add-platform-monitoring`
already considered and rejected, so this is not a free choice either.

Today the question is academic — prod has one volume attached — which is why it
is queued rather than opened.

## 3b. report-an-absent-tailscale-auth-key

**Not blocked on another change; recorded because doing it well is a larger
job than it looks, and doing it badly breaks the host's reachability.**

`fix-volume-discovery-and-consistency` added the requirement *A Role's Absent
Required Input Is Reported by Name* (`iac-host-configuration`) and satisfied it
for `hardening_ssh_allowed_cidrs` and `deploy_apps`. That requirement is
deliberately scoped to inputs a role consumes on **every** run, and this entry
is the class it excludes.

`ansible/roles/tailscale/defaults/main.yml` documents `tailscale_auth_key` in
almost the same words as the two variables that were fixed, which is what makes
this look like an oversight rather than a decision. It is not. The key is
consumed only inside `Bring the host onto the tailnet`, guarded by a `when:`
that skips when the host is already on the tailnet — so a re-converge of the
prod host, the common case, never evaluates it and does not need it supplied.
An unconditional assertion would start demanding it on every run and break a
working path.

Three things make this its own change rather than a fold-in:

- The diagnostic has to fire under the **same** condition as the join, which
  means naming that four-limb condition once instead of restating it. Its
  `POLARITY` comment warns that reading it the wrong way silently stops a host
  joining the tailnet — the mechanism the deploy pipeline depends on to reach
  the host at all.
- `tailscale` carries **no Molecule scenario**, so there is nothing to regress
  against. Any change here should bring the role's first scenario with it.
- The failure is currently *censored*: the consuming task sets `no_log: true`,
  so an absent key surfaces as a redacted error rather than a named one. That
  is worth fixing on its own merits and is invisible from the outside.

Recorded by `fix-volume-discovery-and-consistency`, whose `design.md`
Decision 3a carries the full reasoning.

## 3c. decide-whether-required-input-checks-belong-to-the-play

**Not blocked; recorded because it is a question about the playbook, not a
defect in either role.**

`fix-volume-discovery-and-consistency` gave `hardening` and `deploy_user` an
assertion that fires before either role changes the host, satisfying
`iac-host-configuration`'s *A Role's Absent Required Input Is Reported by Name*
at **role** scope, which is the scope its Molecule scenarios verify.

At **play** scope the guarantee is weaker, and the change's artifacts do not say
so. `ansible/playbooks/host-baseline.yml` runs `docker`, `hardening`,
`tailscale`, `deploy_user`, `ops_user`, `platform_data_volume` in that order.
Against a host whose `group_vars` omits `deploy_apps`, a real run installs and
starts Docker, runs the whole of `hardening` including `Enable UFW`, and joins
the host to the tailnet before `deploy_user`'s assertion is reached. The
requirement's wording — "before any task that acts on the host has changed it" —
reads naturally as the play, and at that scope it is not met.

The fix is not more per-role assertions: it is a `pre_tasks` block on the play,
or a validation role placed first, checking every required input of every role
the play is about to run. That is a different shape of change from the one
`fix-volume-discovery-and-consistency` proposed, which is why it is here.

Worth deciding explicitly rather than leaving the two readings ambiguous.

## 3d. assert-the-shape-of-required-input-elements

**Not blocked; small, and deliberately outside the requirement as written.**

The assertions `fix-volume-discovery-and-consistency` added check the
*container* — defined, a sequence, not a string, not a mapping — and nothing
about the elements. So `deploy_apps: ["platform"]`, a list of strings rather
than of `{name, public_key}` mappings, passes the assertion and then fails at
`item.name` in `Render each application's sudoers.d NOPASSWD rule for
app-deploy`, after the deploy group, the account and its `.ssh` directory
already exist — the partial application the assertion exists to prevent.

The requirement is scoped to an input that "was not supplied", and a
wrongly-shaped one was supplied, so this sits just outside it rather than being
a gap in it. Closing it means either widening the requirement to cover element
shape or adding the check as a local nicety; that choice is the reason this is
recorded rather than done.

## 11. matrix-the-molecule-suite-over-scenarios

**Not blocked; recorded rather than folded into
`promote-molecule-to-a-required-check`**, whose proposal names it as a non-goal.
That change decides which job is required and reshapes the workflow's triggers;
this one changes what a job *is*. Landing both in one diff would mean the
change that picks the registered context also redefines the thing being
registered.

`molecule test --all` runs a role's scenarios in sorted order and **stops at the
first failure**. Every scenario sorting after a failing one is neither executed
nor listed in that run's SCENARIO RECAP, so a red run establishes less than it
appears to and the recap still looks complete. Molecule's own remedy is
unavailable here: `--continue-on-failure` applies only with `--workers`, and
`--workers > 1` refuses with `only supported in collection mode (galaxy.yml
required)` — these are plain roles, not a collection (observed 2026-09-07).

The remedy that works is a continuous-integration matrix over **scenarios**
rather than roles. Each scenario becomes its own job, so one failing scenario
stops only itself and the rest still report. It also parallelises the suite's
longest role, which carries three scenarios and is what sets the workflow's
wall clock.

**What promotion changes about its priority, in both directions.** A red
required check that under-reports is slower to diagnose — you fix one scenario,
push, and wait six minutes to discover the next one. That is an argument for
doing this. Against it: the gate is not weaker for under-reporting. A red check
blocks the merge whether or not it enumerated every failure, so this is about
the cost of diagnosis rather than about the guarantee.

Two things it must not undo, both in
`openspec/specs/iac-cicd-pipeline/spec.md`. *Required Status Checks Report on
Every Pull Request* forbids registering a job whose name is generated from a
matrix — a per-scenario matrix generates more of those names, not fewer, so the
literal-named aggregating job stays and keeps concluding on their behalf.
*Ansible Configuration Is Verified in Continuous Integration and Gates the
Merge* requires discovery rather than enumeration, so scenario discovery must
find `ansible/roles/*/molecule/*/` without a workflow edit, and must keep
failing loudly on an empty result.

Worth noting that the per-job cost changes shape: each scenario job pays its own
checkout and toolchain install, which the current per-role jobs amortise across
a role's scenarios. Whether that is cheaper overall is an empirical question
this entry does not answer.

## 6. two-deferred-ci-items

Both noticed during `close-ci-verification-gaps`, neither a verification gap:

- **`.github/workflows/pre-commit-autoupdate.yml` installs `pre-commit`
  unpinned** (`pip install pre-commit`). That change created
  `.github/requirements-ci.txt`, which pins it; bringing this workflow onto the
  same file is a one-line fix in a workflow that change did not otherwise
  touch.
- **The destroy-policy gate's inspection logic is inline workflow shell.**
  Moving it into a version-controlled script with executable fixtures would
  make the highest-consequence logic in this repository reviewable and testable
  as code — `design.md` Decision 5 of that change names this as considered and
  deferred on merit-vs-scope grounds, not as rejected. Four fixtures already
  exist (clean, destructive, malformed, valid-JSON-that-is-not-a-plan) and are
  described in that change's `tasks.md` 1.1; the structural tests in
  `.github/tests/test_ci_configuration.py` currently assert the routes are
  closed, not that each is reached.
- **`actionlint` is named as a verification means but nothing installs it.**
  Three tasks in `close-ci-verification-gaps` cite it, and it was run manually
  from a scratch install. Adding it to `.pre-commit-config.yaml` would close
  that permanently — but it exits non-zero on two pre-existing `SC2016:info`
  findings (`pr-validation.yml`, the plan-comment step; `apply.yml`, the
  job-summary step — both single-quoted literal markdown in an `echo`, and both
  intentional). So landing the hook means dispositioning those two first,
  by fixing or ignoring them. That is the same trap this change refused to lay
  for the next person when `ansible-lint` failed on pre-existing violations,
  and it wants its own decision rather than being folded in.

## 9. README's Galaxy install step does not provision a working local suite

**Belongs to the already-opened `refresh-readme-accuracy`**, not to a new
change; recorded here so it is not lost, since that branch has a handoff rather
than a proposal.

`README.md`'s local-setup step 5 says `ansible-galaxy install -r
ansible/requirements.yml`, which installs the role to `~/.ansible/roles`.
`ansible-verify.yml:105-112` documents at length why that location is never
found: every scenario overrides `ANSIBLE_ROLES_PATH` to `ansible/roles/`, so
Molecule's own galaxy dependency step resolves nothing and converge fails on
the dependency rather than on anything the scenario asserts. CI therefore uses
`ansible-galaxy role install -r ansible/requirements.yml -p ansible/roles`, and
`.gitignore:30` ignores `ansible/roles/geerlingguy.docker/` — both consistent
with the install landing *inside* the repository, which the README's command
does not do.

Found while provisioning a fresh worktree for `pin-and-fix-molecule-suite`, and
not folded into it: that change's subject is the suite's pins and one broken
assertion, and this is a documentation defect in a file it otherwise does not
touch.

## 8. namespace-the-molecule-suite-per-working-tree

**Not blocked; recorded because it is a gap in this project's own verification
rules rather than a defect in any change, and because it silently invalidates
results.** Observed 2026-09-07 by two sessions at once —
`decide-archived-change-reference-policy` and `reclaim-superseded-app-images` —
which is why the evidence below spans two working trees.

`AGENTS.md:27` already names the hazard — *"Where verification writes to a
shared service, take your own namespace within it, named deterministically from
your working tree"* — and `AGENTS.md:29` says that where this project binds that
rule to a particular service, the binding is an adjacent section of the file.
**No such section exists, for any service.** The rule is stated and nothing is
bound to it, while Molecule is the one shared service this project's
verification actually writes to.

Three handles are shared across every working tree on the machine, and none is
derived from the working tree:

- **The container name** — every scenario's `molecule.yml` sets
  `platforms[0].name` to a literal, e.g. `deploy_user-role-instance` in
  `ansible/roles/deploy_user/molecule/default/molecule.yml`. Two working trees
  running the same role create, converge and destroy *the same container*.
  **This is the collision that matters**, and no environment variable reaches
  it. (Named by key rather than by line: an earlier draft of this entry cited
  `molecule.yml:40`, which was already wrong when written and which this very
  change shifted by one — a line citation rotting inside the change whose
  subject is citations that rot.)
- **Molecule's ephemeral directory**, `~/.ansible/tmp/molecule.<id>.<scenario>`.
  The `<id>` is **derived from the role, not from the path**, so it is identical
  across working trees by construction: on 2026-09-07 every `deploy_user` run
  from either working tree resolved to `molecule.dnU2.*`, while the other roles
  each held their own — `1UjF` `docker`, `Dp-1` `platform_data_volume`, `E127`
  `ops_user`, `HeLe` `hardening`. Relocating a working tree therefore does not
  escape it, and `MOLECULE_EPHEMERAL_DIRECTORY` is the only lever.
- **Molecule's cache**, `~/.cache/molecule/<role>` — keyed by role name alone.

Because the ephemeral id is stable per role rather than per run, **inheriting
another working tree's directory is the default rather than the exception**.
Molecule does not remove the directory when a run finishes — verified after a
clean `exit 0` run, which left all three of its scenario directories in place —
so clearing before a run is a standing requirement, not something owed only
after a crash.

The failure presents at three different stages, which is what makes it read as
three unrelated defects rather than one cause. One session hit them in this
order — progressively later in the run — which is the point: the window is not
one moment but anywhere the other party touches a shared handle.

| Stage | Symptom |
|---|---|
| `create` | `lookup plugin 'file' failed: Unable to access .../molecule.dnU2.default/molecule.yml` — a `destroy` pruned the ephemeral directory a later `create` then read |
| `prepare` | the container torn down under a running play; `UNREACHABLE ... Failed to create temporary directory` |
| `verify` | 18 tasks in, after five `All assertions passed`, a task unrelated to the change dies with **rc 137** |

The `verify` symptom is the one most likely to be misread, so it is worth
naming precisely. What makes it diagnosable is the *pairing*: SIGKILL together
with **empty** stdout and stderr. A module that fails prints something; a module
that is killed prints nothing, and Ansible then reports `Module result
deserialization failed: No start of json char found` — which reads like a module
bug, and is not.

**Serialising is necessary but not sufficient, and neither is the environment
variable.** `flock` on a shared lock file stops two runs overlapping in time; it
does nothing about a run inheriting a directory the previous session left
behind. Observed directly: a locked run, with no concurrent process anywhere on
the machine, still failed at `create` on an ephemeral directory another working
tree had created earlier.

That is contention across *time*, not a standalone defect in the suite — the
same `destroy`-then-`create` sequence runs clean on a directory the working tree
owns, as four other roles demonstrated in the same session. The distinction
matters: the suite is not broken on its own, so the fix is separating the
handles rather than reworking the test sequence.

It also means clearing the shared state is part of the safeguard and not merely
tidying, and that a session reporting it left nothing behind should be checked
rather than believed — on 2026-09-07 one did, and `molecule.dnU2.default` was
still there.

`MOLECULE_EPHEMERAL_DIRECTORY` and a cache override stop a run inheriting stale
state, but leave both runs fighting over one container. Only separating all
three handles makes a concurrent-worktree result mean anything; until then,
coordination between sessions is the whole safeguard.

`molecule test --all` compounds it. It stops at the first failing scenario, so a
collision in `default` — which sorts first for `deploy_user` — leaves
`ghcr-credential-absent` and `ghcr-credential-rejected` neither executed nor
listed in the recap, while the recap still looks complete.

The danger is not the red runs. A colliding run can equally **pass** against a
container the other session converged, which reads as evidence the change under
test is sound.

The fix is one decision covering all three: a per-working-tree instance name —
which means templating it in every `molecule.yml`, with `.github/tests`
asserting that each one does — plus the ephemeral-directory and cache
overrides, and a binding section in `AGENTS.md` that ties `AGENTS.md:27` to
Molecule the way it was always meant to be tied to something.

## 8a. a review agent's mutation check writes to the tree it is reviewing

**Not blocked; recorded next to entry 8 because it is the same class of hazard —
a shared handle nobody namespaced — and was found the same day.**

The `code-review` skill performs mutation checks against the **live working
tree**: it appends a violation to a real file, confirms the gate goes red, then
reverts. Observed 2026-09-07 during `decide-archived-change-reference-policy`'s
code-review gate, on `platform/README.md`.

The revert restored the file to its **committed** content, not to the
working-tree content it had displaced. The change under review was a 45-file
sweep of uncommitted edits, so the revert silently undid the sweep in that file
and restored six pre-archive citations. The stash list and the reflog showed
nothing, because neither a stash nor a branch checkout was involved, which is
why the cause took a while to find.

Two things follow, and only the first is about this incident:

- **A review agent that writes to the tree can destroy the work it is
  reviewing**, and does so in a way that looks like nothing happened. The
  working tree is a shared handle between a session and its own review agent,
  exactly as the container name is between two Molecule runs.
- **The mutation check itself is sound and worth keeping.** Appending a
  violation and confirming the gate goes red is what distinguishes a check that
  reads the tree from a tautology. What is wrong is performing it in place. It
  belongs against a copy, or must restore the content it displaced rather than
  the committed content.

Worth deciding whether this project constrains review agents to a read-only
tree, or accepts in-place mutation checks and requires the dispatching session
to verify the tree afterwards. In this instance the change's own new check
caught the regression unprompted and named all six restored citations by file
and line — which is evidence for that check, not a reason to assume one exists
next time.

## 7. size-platform-container-resource-limits

**Blocked on data, not on another change.** No service in
`platform/docker-compose.yml` declares a memory or CPU limit, on a `cx33`,
while `ContainerRestartingOrOOMKilled` alerts on the consequence. A single
container can currently starve the host.

Limits picked without evidence are guesses that cause the outage they were
meant to prevent. The monitoring stack now collects exactly the data needed —
`container_memory_usage_bytes` by container, already on the "Container health"
dashboard. Let it run long enough to show real steady-state and peak, then size
from observation.

## 10. prune-unreferenced-host-images-periodically

**Not blocked.** Recorded rather than folded into
`reclaim-superseded-app-images`, whose proposal names both of these as
non-goals: that change reclaims an application's superseded images *when it
deploys*, which by construction cannot reach two classes of image.

- **Fully dangling images and layers** carry no repository name, so they fall
  outside every application's namespace.
- **Untagged images that are *inside* a namespace** — images referenced by
  digest, which keep their repository name but show no tag — are deliberately
  left alone there, because a tag-shaped reference set can never name them and
  treating them as unreferenced would delete a live pin.
- **Images of an application that no longer deploys** are never revisited,
  because reclamation is driven by a deploy that will not happen again.

All three want the opposite trigger — a host-level timer rather than a deploy — and
a blunter filter (`docker image prune -af --filter until=<age>`), whose
untargeted nature is acceptable on a timer and was not acceptable inside a
deploy path. That difference in mechanism, not merely in scope, is why it is a
separate change.

Worth doing only after `reclaim-superseded-app-images` has been observed
working: if the per-deploy reclamation is doing its job, this becomes a small
safety net rather than the primary mechanism, and its retention window can be
chosen accordingly.
