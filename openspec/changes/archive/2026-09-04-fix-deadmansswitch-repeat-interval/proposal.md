## Why

`add-platform-monitoring`'s Alertmanager config routes the permanent
"Watchdog" alert to the external dead-man's-switch heartbeat receiver with
`repeat_interval: 5m` (`platform/docker-compose.yml`'s `alertmanager_config`).
The Watchdog rule always evaluates to firing, and Prometheus re-evaluates
it every 30s, so it never actually goes through a resolved/re-fired cycle
— by design, Alertmanager should therefore re-notify the receiver roughly
every 5 minutes indefinitely.

In practice, live on production, the real delivery cadence to the
dead-man's-switch has been a consistent ~10 minutes since Alertmanager's
first successful start today — exactly double the configured value —
confirmed both by reading the external service's own ping log (pings 10
minutes apart, `up→down` roughly 7 minutes after each `up`, `down→up` when
the next ping lands) and by watching `alertmanager_notifications_total`
directly. Because the dead-man's-switch's configured tolerance (period +
grace) is shorter than this real ~10-minute cadence, it flags a false
"down" on every single cycle — which is what actually reached Slack
repeatedly today, not a real outage.

Root cause, confirmed empirically this session via a live, reversible
hot-patch of the running Alertmanager config (`repeat_interval: 5m` →
`2m`, followed by `/-/reload`, no restart): lowering `repeat_interval` to
comfortably under `group_interval` (5m, inherited from the top-level
route) restored a real-world cadence close to 5 minutes (6 notifications
observed over 35 minutes). This points to a timing/boundary artifact in
Alertmanager's dispatch loop for a route whose `repeat_interval` exactly
equals its `group_interval`: each flush tick lands at almost exactly
`repeat_interval` since the last send, and processing/network latency
pushes the elapsed time just under the threshold often enough that every
other tick is silently skipped as a no-op, doubling the real cadence. This
diagnosis is empirical, not sourced from an upstream Alertmanager issue —
it was not independently confirmed against Alertmanager's own source or
issue tracker, only observed to fix the symptom.

## What Changes

- Lower the Watchdog route's `repeat_interval` in
  `platform/docker-compose.yml`'s `alertmanager_config` from `5m` to `2m`
  — comfortably under the inherited `group_interval` (5m), avoiding the
  boundary condition that caused the doubling.
- No change to `group_interval`, `group_wait`, the Slack route's own
  `repeat_interval` (4h), or any alert rule.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — `skip_specs: true`. No spec anywhere states a specific
`repeat_interval` value; the Watchdog/dead-man's-switch requirement (in
`add-platform-monitoring`'s own not-yet-archived delta spec) only
describes the heartbeat mechanism conceptually, not its exact interval.
This change fixes an implementation defect in an unspecified interval
value, not a specified behavior.

## Impact

- `platform/docker-compose.yml`: one value change in the
  `alertmanager_config` inline config block.
- Deployed the same way as any other `platform/` change (gated
  `platform-deploy.yml` pipeline, human-approved).
- The dead-man's-switch's own configured period/grace on the third-party
  service is unaffected by this change and does not need adjusting once
  this lands — the real cadence will match what it already expects.
