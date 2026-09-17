## Why

`ContainerRestartingOrOOMKilled` fires on things that are not containers, and when it does the notification names nothing. On 2026-09-17 it sent eight such notifications to the staging alert channel, each reading `Container  is crash-looping or was OOM-killed` with a hole where the container's name belongs. No container on that host had restarted: every one of the ten had `RestartCount=0` and `OOMKilled=false`, and the host was at 1.4 GB of 3.8 GB with swap untouched.

The rule's two expressions select every series cAdvisor exports. On the staging host that is 46 `container_start_time_seconds` series, of which 10 are Docker containers; the other 36 are systemd cgroups, which carry no `name` label. Two ordinary events churned them that day — `unattended-upgrades` restarting `polkit`, `packagekit`, `fail2ban`, `systemd-networkd` and `systemd-udevd` between 07:01 and 07:02 UTC, and a run of short-lived SSH sessions recreating `/user.slice/user-1000.slice/…` around 11:41 UTC — and each cleared `changes(...) > 3` on its own.

This is the same false-positive class `fix-cadvisor-containerd-snapshotter` addressed. That change fixed cAdvisor's ability to see Docker containers at all, and regression-tested that the deep `/user.slice/user-*` series stopped appearing. Both of those were real; neither is the guard this rule needs. The deep `/user.slice` series are present on staging today, `/system.slice/*.service` was never in that check's scope, and no cAdvisor version will stop exporting cgroup-level series, because exporting them is what cAdvisor is for. The fix belongs in the rule's own selector, not in the exporter.

Left alone, the cost is not the noise. An alert that fires without naming a subject teaches whoever reads the channel to skim it, and this is the rule that would report a real crash-loop — including, by `platform/README.md`'s own account, a `postgres` upgrade going wrong.

## What Changes

- Scope both halves of `ContainerRestartingOrOOMKilled`'s expression to series that carry a container name, so its subject is the Docker containers on the host rather than every cgroup on it. This makes an empty `{{ $labels.name }}` impossible by construction rather than unlikely.
- Bring the rule into line with the Grafana dashboard panels that read the same two metrics in the same file, which already select on a present container name and so have never shown a systemd cgroup.
- State in the specification that the alert's subject is containers, and that a cgroup which is not a container does not raise it — today the requirement says an alert fires "identifying that container" and says nothing about anything else, which is the gap this delta closes: firing on a non-container is behaviour the requirement never anticipated rather than behaviour it forbids, and a requirement silent about the case cannot be the thing that catches it.
- Add a static assertion that the rule carries the selector, so its removal fails a pull request. Nothing today reads the expression: the alert was correct when written, correct when reviewed, and wrong only against a host's own cgroup churn, which no reviewer sees.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-platform-services`: the *Metrics-Based Alerting Covers Host and Service Health* requirement's scenario *A crash-looping container triggers an alert* gains the negative case it is missing — that a cgroup which is not a container raises nothing — and states that the alert identifies the container by name.

## Impact

- `platform/docker-compose.yml` — the `prometheus_rules` config entry, `ContainerRestartingOrOOMKilled` only. No other rule, service, network or volume is touched.
- `.github/tests/` — one new module asserting the rule's selector statically, per `AGENTS.md`'s testing table: the property is a static read of a committed file, so it belongs to the `python3 -m unittest discover --start-directory .github/tests` suite rather than to `terraform test` or Molecule. It adds no dependency beyond PyYAML, already pinned in `.github/requirements-ci.txt`.
- `docs/backlog.md` — one entry, `hold-every-alert-to-naming-what-it-fires-about`, holding the generalization this change declines to make. It sits outside the change directory deliberately: a note kept inside one is archived with it.
- Deployment reaches both stacks through the existing `Platform Deploy` workflow on merge to `main`; the rule change is a Prometheus config reload, not a container replacement.
- Alerting behaviour narrows and never widens: every notification this rule would have raised about a real container, it still raises. What stops is notification about cgroups that are not containers.

Out of scope, and recorded rather than folded in: the staging host has had a reboot pending since 07:01 UTC on 2026-09-17 (`/var/run/reboot-required` names `linux-image-7.0.0-31-generic`, `libc6`, `linux-base`, while the running kernel is `7.0.0-30-generic`). That is `docs/backlog.md`'s `notice-a-pending-reboot-and-decide-what-does-it`, now with a live instance, and it is a host-lifecycle question rather than an alerting one.
