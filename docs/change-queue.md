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
- `refresh-readme-accuracy` — README statements that are no longer true.
  **Archived 2026-09-08** (PR #76). It delivered the former entry 9, which is
  gone with it; entries 13 and 14 below were recorded by it.

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

## 12. make-openspec-validation-a-usable-gate

**Not blocked; recorded because a check that is already red cannot tell anyone
when something new goes wrong.** Found 2026-09-08 while closing
`promote-molecule-to-a-required-check`, whose own archived tasks pass — the
three below predate it.

`openspec validate --archived` reports three archived changes with unticked
tasks:

| Change | Tasks |
|---|---|
| `2026-08-19-add-prod-data-volume` | 16/19 |
| `2026-09-04-fix-cadvisor-containerd-snapshotter` | 10/11 |
| `2026-09-07-reclaim-superseded-app-images` | 24/29 |

Every one of them is a **verification** task — a live `terraform plan` against
prod, a destroy-plan check, a full `pre-commit` run — and each was left unticked
rather than recorded as not done. So the archived record cannot distinguish
"this was verified" from "nobody said". That is the same ambiguity this
repository refuses everywhere else: a check that cannot tell you which of the
two it is has told you nothing.

Deciding it means reading each one and either ticking it with the evidence, or
replacing it with a line saying it was not performed and why. Both are honest;
leaving it unticked is the only option that is not.

**The second half is why none of this was noticed.** `openspec validate` runs
**nowhere**: not in `.pre-commit-config.yaml`, not in any workflow. Nothing
checks that the specifications parse, that a change's deltas are well-formed, or
that an archived change's tasks are complete. The pipeline verifies its own
configuration thoroughly and does not verify the specifications that describe
what it is for.

Wiring it in is cheap — it needs no network, no credential and no container, so
it fits the `.github/tests` row's constraints, though as a subprocess rather
than as a Python assertion. But it should not be wired in while it is red,
because a gate that fails on arrival gets disabled rather than fixed. Hence one
change: settle the three, then add the check.

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
`reclaim-superseded-app-images`, whose proposal names all three of these as
non-goals: that change reclaims an application's superseded images *when it
deploys*, which by construction cannot reach three classes of image.

- **Fully dangling images and layers** carry no repository name, so they fall
  outside every application's namespace.
- **Untagged images that are *inside* a namespace** — images referenced by
  digest, which keep their repository name but show no tag — are deliberately
  left alone there, because a tag-shaped reference set can never name them and
  treating them as unreferenced would delete a live pin.
- **Images of an application that no longer deploys** are never revisited,
  because reclamation is driven by a deploy that will not happen again.

All three want the opposite trigger — a host-level timer rather than a deploy.

**This entry originally specified `docker image prune -af --filter until=<age>`,
and the change in flight does not use it.** That filter selects on an image's
*creation* timestamp, which for a pulled image is its upstream build date, so it
excludes essentially nothing: the running `prom/alertmanager:v0.28.1` was built
in March 2025. `-af` therefore reduces to "remove every image no container
currently holds", which loses the image of any service that is defined and never
started. The change's delta says so normatively — **age SHALL NOT be a
criterion**, and no prune may select images by absence of a tag — so there is no
retention window to choose. What replaced it is a keep set built from the union
of every enumerated application's Compose references and every container's
image, compared by image identity. See the change's `design.md`.

Worth doing only after `reclaim-superseded-app-images` has been observed
working: if the per-deploy reclamation is doing its job, this is a safety net
rather than the primary mechanism.

**It is already opened and well past proposal** — a branch, a proposal, derived
tests and a verified implementation of a new `image_prune` role, at
`build:reviewed` as of 2026-09-08, with three code-review rounds closed. The
session that resumes it should know that the ground moved underneath it:
`ansible-verify` became a **required** status check on `main` that day
(`promote-molecule-to-a-required-check`, PR #72). Two consequences, both
favourable but neither obvious:

- Role discovery enumerates `ansible/roles/*/molecule/`, so `image_prune`'s two
  scenarios are picked up with **no workflow edit** — the property that change
  claimed and did not get to demonstrate, since its own pull requests touched
  nothing under `ansible/`. This will be the first pull request to exercise it.
- Those scenarios must be **green to merge**. Under the advisory tier a red run
  was information; it now blocks. They are green locally at `d5493fe`
  (`molecule test --all`, both scenarios, `failed=0`), but CI is the first run
  on a hosted runner rather than this workstation.

## 13. assert-the-readme-agrees-with-the-tree

**Not blocked; recorded rather than folded into `refresh-readme-accuracy`,
which is the change that found it.** That change corrected eleven statements in
`README.md` that had gone stale. Two of them are static reads of committed
files, and nothing noticed either for weeks:

- the region, which the README stated as `fsn1` while
  `terraform/environments/prod/terraform.tfvars` said `hel1` — a reader
  trusting it would look in the wrong Hetzner location;
- the Molecule scenario count, stated as eight against twelve in the tree.

Both are inside what `.github/tests` can assert — a static read of two
committed files, no network, no credential, no container runtime — and this
repository already enforces a documentation convention that way. The
citation-form check exists because "no author or reviewer can catch a
violation: the citation is correct when written, correct when reviewed, and
wrong only once the change it cites has succeeded". A README fact that
duplicates another file's value is the same shape.

It was not folded in for two reasons, and the first is the binding one.
**It needs a requirement.** This repository does not enforce a convention it
has not recorded, and `refresh-readme-accuracy` declares no specification
delta — adding one would have made a documentation truth pass into a change
owing derived tests, with a different set of gates.

**Its scope is a real question, not a detail.** The region pair is one
assertion and the scenario count another, both cheap. Whether the CI/CD
section's workflow list should also be checked against `ls .github/workflows/`
is the interesting case, and it has a cost: the section would then have to be
edited in the same commit as any new workflow, or the build goes red. Deciding
that inside a documentation fix would have decided it badly. The same question
applies to the Repository layout section, which that change made checkable by
`git ls-files | grep / | sed 's|/.*||' | sort -u` without asserting it.

Note that `refresh-readme-accuracy` reduced the surface deliberately: where the
useful content was a count or a list of examples, it replaced the answer with
the command that produces it. What remains to assert is the handful of facts
that are genuinely duplicated rather than derived.

## 14. The specification says `terraform.tfvars` holds labels; it does not

**Not a change to open — a correction to batch into whatever change next
touches `iac-repo-foundations`.** Recorded so the divergence is tracked rather
than silent.

*Version Control Excludes State and Secrets*
(`openspec/specs/iac-repo-foundations/spec.md`) describes
`terraform/environments/<env>/terraform.tfvars` as holding "server type,
region, image, labels, allowed CIDRs". The file holds no labels; the only
`labels` block under `terraform/environments/prod/` is in `ssh_key.tf`.
`refresh-readme-accuracy` corrected the README's copy of that list and left
this one, because correcting a requirement means a `MODIFIED` delta.

The parenthetical is illustrative rather than an inventory — the requirement's
normative content is that the file is committed and non-secret, and labels
genuinely are non-secret environment configuration, simply set on the resource
— in the module, or in `ssh_key.tf` — rather than passed through this file. So
the two are in factual, not normative, disagreement.

The reason not to take the delta then, rather than merely the cost: a
`MODIFIED` delta owes derived tests, and the test it would owe is "the
requirement's parenthetical agrees with `terraform.tfvars`" — precisely the
cross-file assertion entry 13 defers as needing its own requirement and its own
scope decision. Taking it would have settled that queued question in passing,
by implication.

## 15. alert when the host prune stops working

**Blocked on nothing, but only worth doing once entry 10 has shipped.**

`prune-host-images` reports on every exit path and leaves a failed systemd unit
when it abandons. Nothing scrapes either. `systemctl list-units --failed` is a
manual read, and the outer backstop is `HostDiskPressure` at 90% full, which is
very late — a prune that has silently done nothing for two months is invisible
until the disk is nearly gone.

Closing it needs node-exporter's textfile collector: a `--collector.textfile.directory`
flag and a mount in `platform/docker-compose.yml`, the prune writing a `.prom`
file, and an alert on staleness rather than on failure — a unit that stops being
scheduled at all produces no failure to alert on. That is a `platform/` change,
which is why entry 10 named it a non-goal rather than folding it in.

## 16. report refused removals in the host prune

`prune-host-images` reports `considered N, removed M`, where `considered` is
every distinct image identity on the host rather than a candidate set. A
shortfall between the two therefore carries no signal: a defective keep set
prints `considered N, removed 0`, byte-identical to a healthy run over a host
where everything is referenced.

`app-deploy`'s own reclamation comment calls that shortfall "a signal worth
reading". Here it is unreadable. Counting refusals and reporting them would make
a defective keep set legible without changing any removal behaviour.

Recorded rather than folded into entry 10 because it adds a field to a report
the delta specifies exactly, and that is a specification change, not an
implementation detail.

## 17. adopt the stubbed-runtime rig for the two guards Molecule cannot reach

Entry 10 ships two guards that no assertion covers: local images are enumerated
*before* the keep set is computed, and each tag is re-resolved immediately
before removal. Both are observable only when the host's images change midway
through a run, and a black-box Molecule scenario has no seam at which to change
them. They are also the two that close the concurrent-deploy window against
`app-deploy`, so the least-verified part of that design is the part facing the
only actor competing with it.

Its code review built a rig that supplies the seam — a stubbed `docker` on
`PATH` that answers some calls and fails others — and used it to confirm both
guards present and mutation-visible, and to reproduce the fail-open that review
found. Its `test-plan.md` invites exactly this: "if a deterministic arrangement
is found for either — sized rather than slept — add it to `tasks.md` 2.7 and 2.8
together and strike it from here."

Adopting it would also cover the two abandon branches added by that review's
own fix, which are likewise unasserted.

## 18. give the Molecule shared-state hazard a permanent home

Molecule's instance name, `~/.ansible/tmp/molecule.*` and
`~/.cache/molecule/<role>` are shared across working trees and stable per role.
Two sessions running the same role's scenarios collide: a container is killed
under a live module and it surfaces as "Module result deserialization failed" at
`create`, `prepare` or `verify`, which reads as a module bug and is not one. A
colliding run can pass as easily as fail.

This is recorded nowhere in this repository. The queue entry that held it was
deleted when its change archived, and it has since cost two sessions time they
did not need to spend. It belongs in `AGENTS.md`'s Testing section, beside the
`molecule test --all` note about reading the SCENARIO RECAP, not in a queue
entry that will be deleted again.

Entry 8 (`namespace-the-molecule-suite-per-working-tree`) would remove the
hazard rather than document it; this entry is worth doing anyway and is much
cheaper, and stays true until entry 8 lands.


---

Entries 19 to 30 came out of a second full review on 2026-09-08 (trunk at
`74c7101`), made to judge whether this repository's shape can be reused for a
second, company-owned host. Only what applies to **this** host too is recorded
here; the company-only findings (repository visibility, a second approver, an
organisation-owned repository) are not this repository's concern. The review's
verdict repeated the first audit's: the architecture is sound, and what follows
is operational rather than structural. It read the live host as well as the
tree, so where an entry cites a host fact, that is what `main-server` showed on
2026-09-08, not an inference from the code.

## 19. back-up-the-shared-database-logically-and-off-host

**Not blocked. The most consequential entry in this file.**

The only backup that exists is Hetzner's daily server snapshot -- `backups =
true` in `terraform/environments/prod/terraform.tfvars`, seven retained, taken
in the 02:00-06:00 window. It covers the root disk only: the `main-data`
Volume is not part of a server backup, and Postgres's data lives in a named
Docker volume on the root disk, so it *is* captured, but crash-consistently,
once a day, restorable only by rolling the entire server back to that image.
There is no logical dump, no copy outside the Hetzner project, and nothing in
this repository records a restore ever having been performed.

*Data Durability for Stateful Resources* (`openspec/specs/iac-safety-hardening/spec.md`)
says of this exactly what it should: "Restoring from a backup is the only remedy
... and no Terraform-level guardrail substitutes for it". It does not say the
backup has to be one a database can actually be restored from.

What this wants is a scheduled `pg_dump` per database inside the shared
instance, written to object storage outside the server (Hetzner Object Storage
is the same vendor and the same bill), with a retention policy, an alert on
staleness rather than on failure -- the same reasoning as entry 15: a job that
stops being scheduled produces no failure -- and a restore rehearsed once and
written down. The host has `deploy`'s `/opt/platform` and the `platform_edge`
network to reach Postgres from; whether the dump runs as a platform service or a
host timer is the design question.

Note that the instance it would back up currently holds no application
database at all (entry 20). The two entries are independent but land better
together.

## 20. decide-the-database-model-and-define-per-application-provisioning

**Not blocked; recorded because the specification and the host disagree, and
the disagreement was found by reading the host.**

*Single Shared PostgreSQL Instance, Per-Application Databases*
(`openspec/specs/iac-platform-services/spec.md`) requires every application to
be given a database inside the platform's one instance rather than its own
container. On 2026-09-08 `docker ps` on the host showed `commerce-ops-postgres-1`
(`postgres:16-alpine`, on the application's own `app_db` network) alongside
`platform-postgres-1`, and `\l` on the shared instance listed no database
beyond the defaults. The one application this host runs does not use the
shared instance, and the requirement is not met.

The cause is the gap `platform/README.md` states openly: "How a new
application actually gets its own database/role inside that instance is not
yet defined". With no provisioning mechanism, the first application did the
only thing it could. Nothing here is the application's fault.

Two coherent resolutions, and this repository should pick one rather than keep
a requirement it does not enforce:

- **Keep the shared instance and define provisioning.** A per-application
  database and a restricted role, created by something in this repository
  (the platform deploy, a host-side script, or an operator step written down
  once), with the credential delivered through that application's own
  Environment secret the way its deploy key already is. One instance to
  back up (entry 19), tune, and watch through postgres-exporter.
- **Drop the requirement and let each application own its Postgres.**
  Isolates upgrades and failure per application, at the cost of one backup
  job, one exporter and one set of limits per instance -- and a `MODIFIED`
  delta removing the requirement.

The first is the better fit for a host expecting several small services; the
second is what the host does today. Either way the decision is a specification
change, which is why it is queued rather than folded into entry 19.

## 21. rotate-container-logs

**Not blocked; small.**

`docker info` on the host reports the `json-file` logging driver, and
`/etc/docker/daemon.json` does not exist, so no container's log is bounded:
`docker inspect` shows an empty `LogConfig` map on every service. Docker's
default here is unlimited growth per container, on the root disk, next to
Postgres's data. The `HostDiskPressure` alert fires at 90% full, which for a
log that fills a disk is a report of the outage rather than a warning of it.

`geerlingguy.docker` already accepts `docker_daemon_options`; a `log-driver`
of `json-file` with `max-size` and `max-file` in `log-opts`, set from
`ansible/inventory/group_vars/prod.yml`, is the whole change. It applies to
containers created after the daemon restart, so existing ones pick it up at
their next deploy, and the `docker` role's Molecule scenario can assert the
rendered file.

## 22. give-the-host-swap-and-treat-entry-7-as-its-companion

**Blocked on the same data as entry 7, and the same decision.**

`swapon --show` on the host is empty: an 8 GB host with no swap and no
container limits (entry 7) means the first service to leak memory is stopped
by the OOM killer, and the killer's choice is not the leaking service's --
Postgres and Prometheus are the largest resident processes and therefore the
likeliest victims. A modest swap file does not fix a leak but turns a hard
kill into a slowdown the `HostMemoryPressure` alert has time to report.

Recorded separately from entry 7 because it is a host-level change (an
Ansible task, a `vm.swappiness` sysctl) where entry 7 is a Compose-level one,
and because it is worth doing even before entry 7's data is in.

## 23. apply-host-configuration-through-a-gated-workflow

**Not blocked; recorded because it is the one path to production this
repository still leaves to a workstation.**

`ansible/playbooks/host-baseline.yml` is applied by hand: no workflow runs
`ansible-playbook` against prod, the Vault password lives only on the
operator's machine, and the `tailscale_auth_key` is supplied at the prompt.
`AGENTS.md` says nothing ships from a local machine and that local production
credentials are for reading, and the Terraform and platform layers honour it;
the host layer does not, and a converge that changes UFW rules or authorized
keys is at least as consequential as a Compose change.

The shape already exists twice in `.github/workflows/`: a credential-less job
that shows the reviewer what will change (`ansible-playbook --check --diff`
against prod, over the tailnet, with the read-only Hetzner token for
inventory), then a `production`-gated job that applies it. It needs the Vault
password and the tailnet auth key as Environment secrets, an SSH identity
for `root` that is not the operator's personal key, and a decision about
whether `--check` output is reviewable enough to approve on. That last is the
part worth thinking about; the rest is plumbing.

## 24. make-the-pipeline-environment-agnostic-before-adding-staging

**Not blocked; recorded because the README's "anticipated next environment"
is further away than it reads.**

`terraform/modules/` are parameterised for a second environment, and the
README says staging is "a second `terraform/environments/<name>/` folder
reusing the same modules". The pipeline does not agree. `apply.yml`,
`drift.yml` and `pr-validation.yml` each hardcode
`working-directory: terraform/environments/prod`; `host-baseline.yml` runs
against `hosts: prod`; `group_vars/prod.yml` carries the host's CIDRs and
application list by name. A second folder would be validated by `terraform
validate`'s discovery loop and applied by nothing.

The work is a matrix or a discovery loop over `terraform/environments/*/` in
the three workflows, a per-environment `production`-style GitHub Environment
so staging can be applied without prod's approver and prod's token, and the
same for the playbook. It also needs a decision on whether staging is a second
Hetzner server (a second `server_type` line and a second bill) or a second
project. Worth doing before the first change that would benefit from being
rehearsed -- a PostgreSQL major upgrade is the obvious one.

## 25. close-public-ssh-and-manage-sshd-explicitly

**Not blocked; a policy decision the hardening role already anticipates.**

Port 22 is open on the cloud firewall and in UFW from one ISP `/24`
(`ssh_allowed_cidrs` in `terraform.tfvars`, mirrored in `group_vars/prod.yml`).
The tailnet rule in `ansible/roles/hardening/tasks/main.yml` admits SSH from
`100.64.0.0/10` independently, and that task's own comment says an empty
public CIDR list "is safer than what prod runs". Every non-operator path (the
deploy jobs) already uses the tailnet; the public rule exists for the
operator alone, and the operator is on the tailnet too.

Closing it is `ssh_allowed_cidrs = []` -- except that `modules/server`'s
validation refuses an empty list on lockout grounds, which was the right
default before the tailnet existed and is the thing to revisit now. The
Terraform firewall rule and the UFW rule move together (the *Host-Level
Security Owned by Ansible, Cloud Firewall Owned by Terraform* requirement's
sync obligation), and the change should say what the recovery path is if the
tailnet is unreachable: Hetzner's console, which the cloud firewall does not
gate.

Two smaller things in the same area, neither managed by any role today, both
running on the image's defaults: `sshd_config` (the host has no drop-in under
`/etc/ssh/sshd_config.d/`; `PasswordAuthentication` is unset, harmless only
because no account has a password) and `unattended-upgrades` (installed and
enabled by the image, not by `hardening`, with no `Automatic-Reboot` decision
recorded). Both belong to the hardening role, and both can be asserted by its
Molecule scenario.

## 26. manage-dns-in-terraform

**Not blocked; recorded because it is the one piece of the running system
that lives in no repository.**

Traefik obtains certificates for names such as the one commerce-ops routes
(`Host(...)` in that application's Compose file), and nothing here says where
those records live or what they point at. A server rebuild (entry 30) or an
IPv4 change would be followed by a manual DNS edit nobody has written down.

The hcloud provider does not manage DNS; Hetzner's DNS has its own provider,
and Cloudflare is the other obvious candidate. Either is a `terraform/modules/`
addition, a new Dependabot directory (the CI suite will insist), and a
read-only/read-write token split like `HCLOUD_TOKEN`'s. The records themselves
are non-secret and belong in `terraform.tfvars`.

## 27. check-public-endpoints-from-outside

**Not blocked; recorded because the monitoring stack watches the host and not
the customer's path to it.**

The dead-man's switch proves Alertmanager is alive. `MetricsTargetDown` proves
the exporters are. `ApplicationHighErrorRate` needs requests to reach Traefik
before it can count them. Nothing checks, from outside the host, that a public
hostname resolves, answers on 443, and presents a certificate that is not about
to expire -- so a DNS mistake, a Traefik ACME failure, or a cloud-firewall
change that blocks 443 is invisible until a person notices.

Two shapes: an external uptime service (the dead-man's-switch provider likely
offers one) with a check per hostname, or `blackbox-exporter` in the platform
stack probing each hostname and alerting on `probe_success` and
`probe_ssl_earliest_cert_expiry`. The second stays in the stack and is
disk-free; the first is independent of the host, which is the property the
Watchdog was chosen for. Both is not excessive.

## 28. aggregate-container-logs

**Not blocked; lowest priority in this batch for a host running one
application, and the first thing missed when it runs several.**

Logs are read by `docker logs` over SSH as `ops-claude`, per container, and
are lost when a container is recreated -- which every deploy does. Alerts say
*that* a container restarted; the reason is in the log that just went away.

Loki with an Alloy (or Promtail) collector reading the Docker socket is the
stack-native answer: it joins `platform_monitoring`, Grafana already has the
datasource provisioning pattern, retention is bounded the way Prometheus's is,
and it stores on `main-data` under a `platform_data_volume_subdirs` entry the
way Prometheus does. Entry 21 is a prerequisite in spirit: the collector reads
the same json-file logs that today are unbounded.

## 29. set-traefik-wide-defaults-for-redirect-and-tls

**Not blocked; small, and it removes a class of application mistake.**

Traefik's `web` entrypoint (80) is open and serves whatever an application
routes there; there is no entrypoint-level redirect to `websecure`, and no
default `certresolver`. Every application's Compose file must therefore repeat
`entrypoints=websecure` and `tls.certresolver=letsencrypt` on each router, and
one that forgets is served over plain HTTP with no signal. commerce-ops sets
both; the next application may not.

`--entrypoints.web.http.redirections.entrypoint.to=websecure` and
`--entrypoints.websecure.http.tls.certresolver=letsencrypt` on the Traefik
service make the safe form the default and the labels optional. While there,
Traefik's access log is off; turning it on (to stdout, bounded by entry 21) is
what makes entry 28 useful for HTTP traffic.

## 30. write-and-rehearse-the-rebuild-runbook

**Not blocked; recorded because every piece exists and nobody has run them in
sequence.**

Recovering this host from nothing is: a Terraform apply through the gated
pipeline (with `server_enabled` toggled, and the destroy-override label for
the replace), DNS (entry 26), a hand-run Ansible converge with the Vault
password and a fresh tailnet key (entry 23), the platform deploy from a re-run
of `platform-deploy.yml`, one deploy per application from its own repository,
the two manual steps `platform/README.md` lists (the `pgexporter` role and the
dead-man's-switch registration), and a database restore (entry 19). Those live
in four repositories and two README sections, in no stated order, and the
time they take is unknown.

A `docs/runbook-rebuild.md` that lists them in order, names the secret each
step needs, and records the last rehearsal's date and duration is the
deliverable. The rehearsal is the point; the document is how it survives.
Entry 24's staging environment is where the rehearsal can happen without
touching prod.

## 31. cover-platform-images-with-dependabot

**Not blocked; a one-stanza change in `.github/dependabot.yml`.**

Dependabot watches `terraform` and `github-actions` here and nothing else.
The nine image pins in `platform/docker-compose.yml` -- Traefik, Postgres,
Grafana, Prometheus, Alertmanager, three exporters, cAdvisor -- are refreshed
only when a person notices, which is the same shape as the Molecule digest in
`docs/deferred-work.md`, minus that entry's argument for leaving it: these are
production services, and a stale Traefik or Postgres is a security exposure
rather than a test-reproducibility trade. Dependabot's `docker-compose`
ecosystem reads Compose files directly.

The floor check in `.github/tests` (*Shared-Stack Service Images Are Pinned to
an Exact Release*) still applies to what Dependabot proposes, and the human
half of that requirement is what the resulting pull request review is for.
