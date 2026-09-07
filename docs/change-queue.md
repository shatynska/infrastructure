# Change queue

Identified changes, recorded rather than opened. An entry is deleted when its
change is archived. See `AGENTS.md`, "A second change surfacing".

Everything here came out of a full-repository audit on 2026-09-06 (trunk at
`245ef59`). That audit's verdict was that the architecture is sound and needs
no restructuring; what follows is maintenance, not redesign.

Three of the audit's findings were ready to act on and were **opened** instead
of queued — they have branches and handoffs, not entries here:

- `fix-volume-discovery-and-consistency` — an unreachable assert, pin drift
- `refresh-readme-accuracy` — README statements that are no longer true

Most entries below are queued because they are **blocked on something that must
happen first**, and they are listed in dependency order. Where an entry is not
blocked, it says instead why it was recorded rather than folded into the change
that found it — usually because it belongs to a different concern than the one
that change was closing.

---

## 1. decide-archived-change-reference-policy

**Blocks entries 2 and 3. Nothing else should start until this is settled.**

Source files across this repository cite changes by their pre-archive path
(`openspec/changes/<name>/design.md`). Archiving moves a change to
`openspec/changes/archive/<date>-<name>/`, so every such citation breaks at the
moment its change succeeds. As of the audit: **33 live source files carry 58
such references**, 29 of those files under `ansible/`, plus `README.md`,
`platform/docker-compose.yml`, `platform/README.md` and
`.github/workflows/pr-validation.yml`.

This has been swept before — `openspec/changes/archive/…-sweep-stale-terraform-paths`
did exactly that — and has fully re-accumulated since. Sweeping again without
changing the rule underneath just resets a counter that will climb back.

The decision to make is what archiving owes these references. Three coherent
answers, each with a real cost:

| Option | Keeps traceability | Cost |
|---|---|---|
| Rewrite refs to `archive/<date>-<name>/` during archive | Yes | Archiving becomes a repo-wide edit; every archive touches ~30 files |
| Strip change-name citations from source; git log carries provenance | No (indirectly) | Loses the "which change decided this" trail these comments are unusually good at |
| Accept the rot; re-sweep periodically | Partially | Known-broken paths sit in production config between sweeps |

The choice is the operator's, not a reviewer's. It probably belongs in
`AGENTS.md` as a rule, not in a change's design.

## 2. sweep-stale-openspec-references

**Blocked on entry 1.** Mechanical once the policy exists; the policy
determines whether this is a rewrite, a deletion, or a decision not to run.

Do not start this as a standalone tidy-up. That is what happened last time.

## 3. separate-history-from-rationale-in-source-comments

**Blocked on entry 1**, and should follow entry 2 rather than race it — both
touch the same comment blocks.

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
`find` returned first. That closes the nondeterminism, and a Molecule scenario
(`multiple-devices-discoverable`) holds it closed under both creation orders.

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

## 4. promote-molecule-to-a-required-check

**Reading the run log: `molecule test --all` stops at the first failing
scenario.** Every scenario sorting after a failing one is neither executed nor
listed in that run's SCENARIO RECAP. This does *not* weaken the
"consecutive green runs" evidence below — a green run did execute everything —
but a **red** run establishes less than it appears to, which matters for the
per-role outcomes recorded here. Molecule's own remedy is unavailable to this
repository: `--continue-on-failure` applies only with `--workers`, and
`--workers > 1` refuses with `only supported in collection mode (galaxy.yml
required)` (observed 2026-09-07). The remedy that would work is a CI matrix over
*scenarios* rather than roles — which also parallelises the suite's longest role,
and is adjacent to the workflow reshaping point 2 below already names as the real
remaining work. Recorded by `fix-volume-discovery-and-consistency`.

**Blocked on evidence only.** `close-ci-verification-gaps` put the Molecule
suite in CI as `ansible-verify.yml`, advisory: it is not a required status
check, because whether its privileged-systemd scenarios are reproducible on a
hosted runner had never been observed.

This entry originally had a third blocker — the platform image floating on
`:latest`, and a scenario assertion that failed deterministically. Both were
delivered by `pin-and-fix-molecule-suite` (archived 2026-09-07), and their
queue entries are gone with it. Two things remain:

1. **Consecutive green runs** on pull requests touching `ansible/`. How many is
   a judgement call; two or three across different roles is meaningful, one is
   not. See the run log below for what has actually been observed — it is less
   than it first appears.
2. **Removing the workflow-level `paths:` filter first**, and moving the gating
   inside an always-running job — the shape `pr-validation.yml` already uses. A
   `paths:`-filtered required check never reports on a non-matching pull
   request, leaving it permanently pending and unmergeable under branch
   protection. This is exactly what the *Required Status Checks Report on Every
   Pull Request* requirement exists to forbid, and promotion is **not** just a
   branch-protection toggle. `ansible-verify.yml`'s own top comment says so.
   **This is the real remaining work.**

**First observed baseline** — to be filled in from the post-merge
`workflow_dispatch` run on `main` (that trigger is only exposed once the file is
on the default branch). Record per-role outcome and duration here, not in the
change's own artifacts, which are archived:

First run was on PR #57 itself, not a post-merge dispatch — that change
fixed three lint violations under `ansible/`, so its own pull request matched
the `ansible/**` filter after all:

| Role | Outcome | Duration |
|---|---|---|
| `deploy_user` (3 scenarios) | pass | 6m33s |
| `ops_user` (2 scenarios) | pass | 4m47s |
| `hardening` | pass | 3m03s |
| `docker` | pass | 2m55s |
| `platform_data_volume` | **fail** — a defect in its own assertion, fixed by `pin-and-fix-molecule-suite` | 2m12s |

Repeated post-merge as a manual `workflow_dispatch` on `main`
([run 34046099603](https://github.com/shatynska/infrastructure/actions/runs/34046099603)),
which also confirmed that trigger works — promotion depends on it. Same
outcome, same single failure: `deploy_user` 7m38s, `ops_user` 4m42s,
`hardening` 2m36s, `docker` 2m41s, `platform_data_volume` fail 2m07s. Two
independent runs agreeing means the failure is deterministic, not flaky.

So the suite **does** run on a hosted runner: the privileged-systemd
scenarios, UFW and fail2ban all converge and verify. That was the open
question the advisory tier existed to answer, and the answer is yes. Longest
role is under eight minutes, and the roles run in parallel.

The one failure is a defect in a scenario's own assertion, not a runner
problem.

**Neither of those two runs is a green run**, and that matters for point 1:
they establish that the privileged-systemd scenarios work on a hosted runner,
which was the question the advisory tier existed to answer, but a run with a
failing job is not evidence toward "consecutive green".

**Third run — the first fully green one.** On PR #64
([run 34057674462](https://github.com/shatynska/infrastructure/actions/runs/34057674462)),
which pinned the platform image and fixed the assertion:

| Role | Outcome | Duration | Was |
|---|---|---|---|
| `deploy_user` (3 scenarios) | pass | 6m06s | 6m33s |
| `ops_user` (2 scenarios) | pass | 4m29s | 4m42s |
| `docker` | pass | 2m31s | 2m41s |
| `hardening` | pass | 2m11s | 2m36s |
| `platform_data_volume` | **pass** | 1m40s | **fail** 2m07s |

Every scenario green, and modestly faster across the board. The speed-up is
smaller than the same change produced locally, which is what one would expect:
removing an `apt-get` install helps a developer's connection more than a hosted
runner sitting next to a package mirror.

**Fourth run — post-merge `workflow_dispatch` on `main`**
([run 34058142743](https://github.com/shatynska/infrastructure/actions/runs/34058142743)),
at `d635965`. All five roles green, workflow conclusion success:
`deploy_user` 5m53s, `ops_user` 4m20s, `hardening` 2m32s, `docker` 2m23s,
`platform_data_volume` 1m35s. This is the same trigger on the same branch that
concluded **failure** two runs earlier, so it is a direct before/after on the
trunk rather than an inference from a green pull request.

**Where point 1 actually stands: two green runs, both of the same change.**
Runs one and two carried a failing job and are not evidence toward
"consecutive green". Runs three and four are green, but both observe
`pin-and-fix-molecule-suite` — the change that fixed the failure — from a
pull request and then from the trunk. That is one subject observed twice, not
two independent observations.

What would settle it is a green run on the next unrelated pull request
touching `ansible/`. Until then, treat point 1 as **partially** satisfied and
resist reading the run log as three-of-four green.

One thing that change establishes bears on the evidence question: until now the
suite installed `python3 sudo bash ca-certificates iproute2 python3-apt
aptitude rsync` via `apt-get` inside every container on every `molecule
create`, because no scenario set `pre_build_image` and all used the driver's
default `Dockerfile.j2`. Runs before that change were therefore not
reproducible in a second respect beyond the floating image tag, and a red run
could have been attributable to a package archive. Runs after it reach no
package archive during `create` at all, so "consecutive green runs" starts
meaning something stricter than it did.

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
