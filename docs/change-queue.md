# Change queue

Identified changes, recorded rather than opened. An entry is deleted when its
change is archived. See `AGENTS.md`, "A second change surfacing".

Everything here came out of a full-repository audit on 2026-09-06 (trunk at
`245ef59`). That audit's verdict was that the architecture is sound and needs
no restructuring; what follows is maintenance, not redesign.

Three of the audit's findings were ready to act on and were **opened** instead
of queued — they have branches and handoffs, not entries here:

- `close-ci-verification-gaps` — CI verification holes and a fail-open gate
- `fix-volume-discovery-and-consistency` — an unreachable assert, pin drift
- `refresh-readme-accuracy` — README statements that are no longer true

The entries below are queued because each one is **blocked on something that
must happen first**. They are listed in dependency order.

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

## 4. size-platform-container-resource-limits

**Blocked on data, not on another change.** No service in
`platform/docker-compose.yml` declares a memory or CPU limit, on a `cx33`,
while `ContainerRestartingOrOOMKilled` alerts on the consequence. A single
container can currently starve the host.

Limits picked without evidence are guesses that cause the outage they were
meant to prevent. The monitoring stack now collects exactly the data needed —
`container_memory_usage_bytes` by container, already on the "Container health"
dashboard. Let it run long enough to show real steady-state and peak, then size
from observation.
