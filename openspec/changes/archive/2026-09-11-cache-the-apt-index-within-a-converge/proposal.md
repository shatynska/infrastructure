## Why

Three `apt` tasks in this repository's own roles carry `update_cache: true` with no bound on how recently the index was fetched, so **every one of them fetches the whole package index again**. Nothing reuses what the task before it just downloaded.

The cost is ordinarily small and was invisible for that reason. On 2026-09-11 it stopped being invisible: the Ubuntu archive became slow to reach from GitHub-hosted runners, and a single `apt-get update` inside a scenario's container went from 13 seconds to 309. `hardening`'s job that morning spent **11.9 of its 15.6 minutes inside two apt tasks** — 76% of the job — because those two tasks run six times across the role's scenarios and each one re-fetched. `image_prune`, the most expensive role, went from a steady 9–11 minutes to 74.5.

The degradation is upstream and not this repository's to fix. What is this repository's is that it pays for the same index six times where once would do, and that the multiplier lands on a **required status check** every pull request waits for.

This is not only a continuous-integration concern. A production converge pays it too, and `docs/bootstrap-a-new-host.md` describes a first converge run from a workstation over a possibly slow link — though whether a long-lived host realises the saving depends on whether it carries a maintained apt update stamp, which `design.md`'s Risk section records as an open question rather than a settled benefit. The continuous-integration saving is the measured one.

**The knob is already established here, at the other extreme.** Ten Molecule prepare plays declare `cache_valid_time: 0` — always refresh — as a deliberate workaround: `geerlingguy.docker` 8.0.0 installs `ca-certificates` and `python3-debian` with `state: present` and no `update_cache` at all, which fails against a freshly created container whose cache is empty. So the repository already reasons about this option; it has simply never applied it to the role tasks, where the repetition is.

## What Changes

- **Three role `apt` tasks gain a cache window**: `ansible/roles/hardening/tasks/main.yml` (`ufw` and `fail2ban`) and `ansible/roles/image_prune/tasks/main.yml` (`curl`). Each keeps `update_cache: true`; what is added is a bound on how stale an index may be before the task re-fetches it. The first apt task of a converge still fetches; the ones after it, minutes later in the same run, do not.

- **`tailscale` is deliberately excluded**, and it carries a fourth such task. Three reasons, and the third is the one that would survive the other two lapsing: the role writes `/etc/apt/sources.list.d/tailscale.list` and then installs from it **in the same run**, so an index fetched earlier in that converge is inside any bound and predates the source — the package resolves to no candidate while every other install on the host succeeds. The other two: it installs a **pinned version**, `tailscale=1.102.3`, where a stale index makes the pin unresolvable rather than merely old; and the role has **no Molecule scenario at all**, so the change would be unobservable by the mechanism this project uses for role behaviour (`docs/change-queue.md` entry 3b owns that gap). It also contributes nothing to the cost this change exists to reduce, being in no scenario.

- **The prepare plays keep `cache_valid_time: 0`.** They are the reason a scenario's index is fresh when the role runs, and weakening them to save a fetch would reintroduce the empty-cache failure their comments record. They are fixture setup, not role behaviour, and they stay as they are.

- **A requirement records what the window means.** No specification in this repository says anything today about how fresh a package index must be when a security-relevant package is installed. That silence is what makes this a design decision rather than a tweak, so it is written down rather than left in a task file.

## Non-Goals

- **Changing what is installed, or when.** No package, version, or ordering moves. A converge installs exactly what it installed before.

- **Reducing the number of `apt` tasks**, by collecting each role's installs into one. That would cut fetches further still, and is a larger refactor of two roles that changes where a failure surfaces and which task a reader finds it under. Out of scope, and recorded as a queue entry rather than left as a sentence here — `tasks.md` 5.2 does the recording.

- **Anything about `geerlingguy.docker`'s own apt behaviour.** It is pinned external content, reinstalled wholesale by the next `ansible-galaxy` run, and not editable here. The prepare plays' `cache_valid_time: 0` exists precisely to work around it, and that arrangement is left alone.

- **Bounding the Molecule matrix with a timeout.** Queued as entry 66 by `narrow-the-molecule-trigger-to-what-it-reads`, which merged as pull request #142 on 2026-09-11 — so that entry is on `main`, though not in this change's working tree, which was branched before it. It depends on this change either way: it must choose its value against durations this change lowers.

## Capabilities

- `iac-host-configuration` — **ADDED**: *A Converge Bounds How Often It Re-Fetches the Package Index*. No requirement in this capability governs package installation today, so there is nothing to modify — the freshness judgment, and the two cases that must never take a bound, are stated as a requirement of their own. It references the existing ownership of unattended upgrades rather than restating or changing it.

## Impact

- Changed: `ansible/roles/hardening/tasks/main.yml` and `ansible/roles/image_prune/tasks/main.yml` — each apt task gains the bound, and `hardening`'s two also gain a `register:` for the tests rather than for the role, because the change's effect leaves no trace in host state and can be read only from the module's own return. Each role's `defaults/main.yml` gains the bound as a variable with a default, which the delta requires rather than leaves open, and each role's `README.md` gains a row for it in its variables table. `ansible/roles/hardening/molecule/default/converge.yml` gains the two assertions that characterise the converge's own role run; the third, which characterises an invocation the test itself makes, sits in `verify.yml`. `design.md` Decision 6 states the rule that splits them — each assertion sits in the play whose invocation it characterises, a register being a play variable that reaches no further. A comment is added to `ansible/roles/tailscale/tasks/main.yml` recording why it takes no bound.
- New: five assertions in `.github/tests`, covering the four scenarios that are static reads of committed files — the positive obligation, the two refusals (pinned version, same-run source), the variable-not-literal rule, and the fixture-play exemption. `ansible/roles/hardening/molecule/default/verify.yml` gains a back-dating task **and the bound-refresh assertion**, before and after the role invocation it already carries.
- Tests: the Molecule row of this project's test table. Role behaviour on a host is what changes, so `hardening` and `image_prune` scenarios are where it is observed — including the idempotence pass, whose meaning this change alters and which is the sharpest thing review should look at.
- No workflow, pipeline or repository-settings change. The saving is a consequence of the roles doing less, not of continuous integration being told to.
