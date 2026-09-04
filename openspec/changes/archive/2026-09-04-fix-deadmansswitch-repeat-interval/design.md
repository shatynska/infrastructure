## Context

See proposal.md - Why. The diagnosis was validated empirically on the live
production Alertmanager container before proposing this change: its
config file was hot-patched in place (`repeat_interval: 5m` → `2m` for the
Watchdog route only) and reloaded via `/-/reload` (no restart, no data
loss — Alertmanager holds no persistent state relevant here). Real
delivery cadence to the dead-man's-switch, measured via
`alertmanager_notifications_total{integration="webhook"}`, went from a
consistent ~10 minutes to ~5.8 minutes over a 35-minute observation window
— close enough to the intended 5-minute cadence to be a clear fix, not
noise. That hot-patch was diagnostic only and is not itself persisted
anywhere in git or the deploy pipeline — it remains live on the running
container only until the next container recreation (including this
change's own deploy, which will recreate Alertmanager from the committed
compose file regardless of the hot-patch's state). This change codifies
the same fix properly, so the fix survives independent of that live,
unpersisted state.

## Goals / Non-Goals

**Goals:**
- Stop the dead-man's-switch's false "down" flapping, which is currently
  reaching Slack on every cycle.
- Keep the fix to the smallest change that resolves the symptom.

**Non-Goals:**
- Root-causing Alertmanager's dispatch-loop timing behavior against its
  own source code or upstream issue tracker. The empirical fix is
  sufficient and low-risk; a deeper investigation isn't warranted for a
  single-value config change with a clearly observed result.
- Changing the dead-man's-switch's own configured period/grace on the
  third-party service. Once real cadence matches ~5 minutes again, its
  existing tolerance (already set up for a 5-minute period) is correct as
  configured.

## Decisions

**Set `repeat_interval: 2m` rather than some other value comfortably under
`group_interval` (5m).** Chosen to leave clear margin below `group_interval`
so the same boundary condition can't recur even with minor timing jitter,
while still being close enough to the originally-intended 5-minute
heartbeat cadence not to meaningfully change Alertmanager's behavior for
this route in any other way (Watchdog's own annotations/labels never
change, so a shorter repeat_interval here has no effect beyond sending the
heartbeat slightly more often).

**Did not touch `group_interval`.** Alternatives considered: raising
`group_interval` instead of lowering `repeat_interval` — rejected because
`group_interval` is inherited from the top-level route and shared with the
`slack` receiver's alert grouping behavior; changing it would have a wider
blast radius than necessary for a fix scoped to the Watchdog route alone.

## Risks / Trade-offs

- [Risk] The root cause is diagnosed empirically, not confirmed against
  Alertmanager's own source/issue tracker — there's a small chance the
  real mechanism is different and this value change only coincidentally
  fixed the symptom during the observation window. → Mitigation: task 3
  re-verifies real-world cadence again post-deploy over a similar
  observation window before considering this closed. If verification
  shows the fix didn't work (cadence still ~10min, or false-down
  notifications continue), the fallback is to revert to `5m` via the same
  gated pipeline and open a proper investigation against Alertmanager's
  source/issue tracker — not to guess at a different value without
  understanding the mechanism.
- [Risk] None to alerting correctness — Watchdog's annotations and target
  receiver are unchanged; only how often an already-correct notification
  repeats.

## Migration Plan

Standard `platform/` deploy (gated `platform-deploy.yml` pipeline). No
data migration, no rollback complexity beyond reverting the one value.
