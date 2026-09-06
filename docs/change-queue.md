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
  tolerated/not-tolerated block (`ansible/roles/deploy_user/tasks/main.yml:124-148`)
  are load-bearing and must survive any pass.
- **what a past change did** — git log and the archive already own this.
- **a TODO whose condition has passed** — dead, and quietly misleading.

Only the first kind survives archiving. Concrete instances of the other two:

- `platform/docker-compose.yml:1-4` — a commit message stuck to the top of the
  production stack definition ("Comment-only change … exercises
  add-per-app-deploy-keys tasks.md 5.2's validation deploy").
- `terraform/environments/prod/ssh_key.tf:20-28` — a `moved` block that
  documents its own removal condition ("Safe to delete once the next apply has
  run") from a change archived 2026-08-18.
- `terraform/environments/prod/main.tf:19-21` — explains a value the file no
  longer holds.

The tailscale role is 48 comment lines against 90 non-blank; this is a style
question with a real maintenance cost, not a cosmetic one.

## 4. promote-molecule-to-a-required-check

**Blocked on entry 5 landing first, and on evidence.** `close-ci-verification-gaps`
put the Molecule suite in CI as `ansible-verify.yml`, advisory: it is not a
required status check, because whether its privileged-systemd scenarios are
reproducible on a hosted runner had never been observed.

Promotion needs three things, and the middle one is the trap:

1. **Consecutive green runs** on pull requests touching `ansible/`. How many is
   a judgement call; two or three across different roles is meaningful, one is
   not.
2. **Removing the workflow-level `paths:` filter first**, and moving the gating
   inside an always-running job — the shape `pr-validation.yml` already uses. A
   `paths:`-filtered required check never reports on a non-matching pull
   request, leaving it permanently pending and unmergeable under branch
   protection. This is exactly what the *Required Status Checks Report on Every
   Pull Request* requirement exists to forbid, and promotion is **not** just a
   branch-protection toggle. `ansible-verify.yml`'s own top comment says so.
3. **Entry 5 landing first.** While the platform image floats on `:latest`,
   "consecutive green runs" is evidence about a moving target, and a red run
   may be attributable to an upstream image rather than to the runner.

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
| `platform_data_volume` | **fail** — see entry 8 | 2m12s |

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
problem. Promotion still waits on entry 8 being resolved and on entry 5.

**Both named blockers are closed by `pin-and-fix-molecule-suite`**, pending its
merge: entry 5's pin is applied to all eight scenarios and entry 8's assertion
is fixed. What promotion still needs after that is the evidence in point 1 —
consecutive green runs on pull requests — and the `paths:`-filter removal in
point 2, which is not a branch-protection toggle and remains this entry's real
work.

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

Point 1's "how many is a judgement call" now has two green runs behind it — the
runs on PRs #57 and the `main` dispatch were green **except** for
`platform_data_volume`, so they establish the privileged-systemd scenarios are
reproducible on a hosted runner but are not themselves green runs. This is the
first. One more on an unrelated `ansible/`-touching pull request would make the
evidence real rather than a single observation of the change that fixed it.

One thing that change establishes bears on the evidence question: until now the
suite installed `python3 sudo bash ca-certificates iproute2 python3-apt
aptitude rsync` via `apt-get` inside every container on every `molecule
create`, because no scenario set `pre_build_image` and all used the driver's
default `Dockerfile.j2`. Runs before that change were therefore not
reproducible in a second respect beyond the floating image tag, and a red run
could have been attributable to a package archive. Runs after it reach no
package archive during `create` at all, so "consecutive green runs" starts
meaning something stricter than it did.

## 8. fix-platform-data-volume-verify-attribute-access

**Found by the first CI run of the Molecule suite** (PR #57), and the reason
that tier was made advisory rather than blocking.

`ansible/roles/platform_data_volume/molecule/default/verify.yml:194` asserts:

```yaml
- item.stat.pw_name == item.item.owner or item.stat.uid | string == item.item.owner
```

and fails with `object of type 'dict' has no attribute 'pw_name'`. The `or`
fallback never runs: Jinja evaluates the left operand first, and on a `stat`
result where the uid does not resolve to a name, `pw_name` is simply absent —
so the expression raises instead of falling through to the uid comparison the
author clearly intended as the fallback.

**Correction, from `pin-and-fix-molecule-suite`'s investigation.** This entry
originally blamed uid `65534`. That uid *does* resolve inside the image, to
`nobody` — verified with `getent passwd 65534` against the pinned digest. The
failing fixture is the other one, `grafana`, whose `472/472` has no `passwd`
or `group` record at all. The mechanism above is right; the uid named was not.
Note also that the name comparison could never have passed regardless: the
declared owners are numeric strings (`"472"`, `"65534"`) in both the scenario
and `ansible/inventory/group_vars/prod.yml`, so `pw_name == "472"` is false
even where `pw_name` exists. The uid comparison was always the only branch
capable of passing.

The fix is to make the access safe (`item.stat.pw_name is defined and …`, or
compare on uid/gid alone), not to relax what is asserted.

Worth noting *why* this was never seen: the same assertion presumably passed
on a developer machine, so either the uid resolves there or it did under an
earlier `ansible-core` whose undefined-attribute behaviour was laxer. Entry 5
is relevant either way — the platform image floats on `:latest`, so "it passed
locally" and "it passes in CI" were never statements about the same image.

## 5. pin-the-molecule-platform-image

**Blocks entry 4.** Every scenario under `ansible/roles/*/molecule/*/molecule.yml`
pins its platform as `geerlingguy/docker-ubuntu2204-ansible:latest` — a floating
tag, against AGENTS.md's "any external role or collection used for any purpose
is pinned to an exact version". Affects all eight scenarios across
`deploy_user`, `docker`, `hardening`, `ops_user` and `platform_data_volume`.

Noticed while implementing `close-ci-verification-gaps` and deliberately not
folded in: it changes what the test suite runs against, which is a different
concern from getting the suite to run at all.

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
