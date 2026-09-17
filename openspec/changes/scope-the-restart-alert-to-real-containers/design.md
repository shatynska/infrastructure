## Context

See `proposal.md` — Why, for the incident and the measurements behind it. What the design has to work with:

`ContainerRestartingOrOOMKilled` lives in the `prometheus_rules` config entry of `platform/docker-compose.yml`, alongside every other rule this stack evaluates and alongside the Grafana dashboard JSON that reads the same two metrics.

**Editing that entry does not reach the host by itself.** Compose decides whether to replace a container from a digest of the service definition, and that digest does not cover the content of an inline `configs:` block; the content is copied into the container at creation and Prometheus has no reload path here. `apply-shipped-config-on-deploy` added the `platform.config-checksum` label on the `prometheus` service for exactly this reason — a property that moves when the content moves, so the deploy recreates the container. So this change has two edits in one file, not one, and the second is not bookkeeping: without it the deploy replaces nothing, reports every container running and healthy, exits zero and changes nothing. `.github/tests/test_shipped_config_reaches_the_container.py` fails the pull request and names the value the label should hold.

Measured against staging's Prometheus on 2026-09-17, cAdvisor v0.60.5 exports:

| Metric | Series | Series carrying a `name` label |
|---|---|---|
| `container_start_time_seconds` | 46 | 10 |
| `container_oom_events_total` | 55 | 10 |

Ten is the number of Docker containers on that host, and the ten names returned are exactly those containers. Everything else is a control group the init system owns — `/`, `/system.slice`, `/system.slice/<unit>.service`, `/user.slice/user-1000.slice/…` — and carries an `id` but no `name`. That asymmetry is not a defect in this cAdvisor build and not something a later one will remove: reporting per-cgroup resource usage is what cAdvisor is for, and only a Docker container has a Docker name to report.

The rule as it stands today, quoted so that what follows can be checked against it rather than taken on trust (the `$$` is the Compose file's escape for a literal `$`, not a typo):

```yaml
- alert: ContainerRestartingOrOOMKilled
  expr: >-
    increase(container_oom_events_total[10m]) > 0
    or
    changes(container_start_time_seconds[10m]) > 3
  for: 0m
  labels:
    severity: warning
  annotations:
    summary: "Container {{ $$labels.name }} is crash-looping or was OOM-killed"
    description: "{{ $$labels.name }} has restarted repeatedly or hit an OOM kill in the last 10 minutes."
```

Both halves evaluate per series — `increase` and `changes` are range-vector functions returning one sample per input series, and the `or` is a set union over those results, with no aggregation anywhere. That is what makes the selector purely subtractive: adding a label matcher removes series from each half's result set and changes no value in what remains, so the rule after this change fires on a subset of what it fires on today and never on anything new.

The same file already selects on a present name four times. The "Container health" dashboard's four panels read `container_cpu_usage_seconds_total{name!=""}`, `container_memory_usage_bytes{name!=""}`, `changes(container_start_time_seconds{name!=""}[1h])` and `increase(container_oom_events_total{name!=""}[1h])`. The third and fourth of those are this rule's own two expressions with the selector the rule lacks, which is why the dashboard has never shown a systemd cgroup while the rule has alerted on them eight times in a day.

The `prometheus_rules` entry was surveyed for other rules the delta's new normative sentence would bind. There are none: of the nine rules in the file, `ContainerRestartingOrOOMKilled` is the only one reading a `container_*` metric at all. `ApplicationHighErrorRate` and the two certificate rules read `traefik_*`, the three `Host*` rules read `node_*`, `MetricsTargetDown` reads `up`, and `Watchdog` reads `vector(1)`. So the sentence binds exactly one rule today, and on archive it ships met rather than aspirational — while still binding the next container-subject rule anyone writes, which is the point of stating it as a property rather than as a fix.

One further precedent sits two rules below: `CertificateExpiryNotObserved`, added by `alert-on-certificate-expiry`, already writes `traefik_tls_certs_not_after{cn!=""}`. The idiom is established in this file; this rule simply predates it.

## Goals / Non-Goals

**Goals:**

- The rule's subject is the Docker containers on the host, and a notification it raises can always name one.
- The guard sits where a reader of the rule sees it, so nobody has to know what a scrape config or an exporter flag does elsewhere to know what the rule watches.
- Its removal fails a pull request, because nothing about this defect is visible to a reviewer reading the diff.

**Non-Goals:**

- Changing what counts as crash-looping. The thresholds — an OOM event in ten minutes, or more than three starts in ten — are untouched; only the set of series they are evaluated over narrows.
- Making the same guarantee for every other rule in the file. Two others interpolate a label whose emptiness they do not exclude, and fixing those is a separate change (see Decisions, "The general property is not asserted here").
- Anything about the host's pending reboot, or about container memory limits — `docs/backlog.md`'s `size-platform-container-resource-limits` is what would stop a container being OOM-killed rather than reporting it.

## Decisions

### The selector goes in the rule, not in the exporter or the scrape configuration

Three places could exclude cgroup series, and only one of them keeps the statement next to the thing it constrains.

- **In the rule**, as `{name!=""}` on both metrics. Chosen.
- **In cAdvisor**, via its `--docker_only` flag, which stops it reporting non-container cgroups at all. Rejected: it deletes data rather than declining to alert on it, and the data it deletes includes the root cgroup and the system slice, which are what a future host-level question would be asked of. It also makes this rule's correctness a property of a container's command line in a different section of the file — a reader of the rule learns nothing about what it watches, and a later change restoring cAdvisor's default silently re-arms the defect.
- **In Prometheus's scrape configuration**, as a `metric_relabel_configs` drop on the `cadvisor` job. Rejected for the same reason, plus one of its own: a drop at ingest is invisible in the rule, invisible in the dashboards, and indistinguishable at query time from the exporter having never reported the series.

The deciding argument is the one the incident demonstrates. This defect survived authoring, review and a dedicated follow-up change because nothing about the rule's text says what it excludes. Putting the answer in the rule's own selector is the only one of the three that a reader of the rule can check.

### `name!=""` rather than an `id` pattern

`id=~"^/docker/"` would select the same series today. `name!=""` is preferred because it and the annotation state one proposition rather than two: the rule fires only where there is a name, and the notification prints the name. There is then no arrangement in which the rule fires and the message is blank — that is the defect being closed, closed by construction rather than by two facts happening to agree.

An `id` pattern would also couple the rule to cAdvisor's cgroup path layout, which varies with the cgroup driver (`systemd` vs `cgroupfs`) and with the container runtime. The `name` label varies with neither.

### Both halves of the expression, not only the restart half

The restart half is what fired, so it is tempting to treat the OOM half as sound. It is not: `container_oom_events_total` has 55 series on staging and 10 with a name, the same shape. An OOM kill inside a systemd unit's cgroup would raise exactly the same nameless notification. Both halves get the selector, and the rule keeps reporting every OOM kill inside a container.

### The assertion is a new module in `.github/tests`

`AGENTS.md`'s testing table routes this property to the static suite: it is a read of one committed file, needs no network, credential, container runtime or Terraform binary, and takes no dependency past the PyYAML `.github/requirements-ci.txt` already pins. That suite runs unconditionally on every pull request — `pr-validation.yml` gates the Terraform, platform and Ansible work on `dorny/paths-filter` but deliberately does not gate this step — so no trigger needs widening.

A new module rather than a section of `test_ci_configuration.py`, following `test_certificate_expiry_alerting.py`, which the closest prior change wrote for the closest prior reason. The tests for this change are written by an author other than the implementer and that author may only add; folding the module into its neighbour afterwards is a reviewable move rather than an authoring decision.

### The assertion parses the expression rather than matching its text

Asserting that the `expr` string contains `name!=""` twice would pass on `container_start_time_seconds{name!=""}` written twice and on one written twice with the other left bare, and would fail on a reformat that put a space inside the braces. The assertion instead loads `platform/docker-compose.yml`, parses the `prometheus_rules` entry's `content` as YAML, locates the rule by its `alert` name, extracts every metric selector in its `expr`, and requires each to carry a `name` matcher that excludes the empty string. A half-applied selector is then a failure, and a reformat is not.

The `$$` doubling the Compose file uses to escape `$` for interpolation has to be undone before the content parses as a rule file; the module states that where it does it, because a reader meeting `{{ $$labels.name }}` will otherwise take it for a typo.

### The general property is not asserted here

The defect generalizes: any rule interpolating `$labels.<L>` into its notification should exclude series where `<L>` is empty. Asserting that across the file would fail today on two rules that are out of this change's scope — `ApplicationHighErrorRate` aggregates `by (router)` without excluding an empty `router`, and `TLSCertificateExpiringSoon` aggregates `by (cn)` without excluding an empty `cn`, which is the very condition its companion rule `CertificateExpiryNotObserved` exists to detect.

Whether those two are actually reachable is a real question and not one this change answers. It goes to `docs/backlog.md` as `hold-every-alert-to-naming-what-it-fires-about`, so the general check is proposed rather than folded into a change whose subject is one rule.

## Risks / Trade-offs

**A real OOM kill or crash-loop outside a container stops being reported** → Accepted, and it is the point. Nothing was watching for that: the alert's text, its name and the requirement it implements all say "container". A host-level concern that deserves an alert deserves a rule of its own, worded for it — `docs/backlog.md`'s `alert-on-a-scheduled-units-own-output` is where that thought already lives.

**cAdvisor could stop setting `name` on container series, silencing the rule entirely** → The upgrade path already proved this is the label that breaks first: `fix-cadvisor-containerd-snapshotter` was a case where cAdvisor could not identify containers at all. The mitigation is not in this change — `MetricsTargetDown` covers the exporter vanishing, and it does not cover the exporter reporting without names. That gap predates this change and is not widened by it, because the four dashboard panels already depend on the same label; it is noted here so it is not discovered as a surprise. It belongs with the backlog entry above.

**The verification cannot establish runtime behaviour** → A static read of a committed file cannot show that Prometheus evaluates the narrowed rule the way the delta's scenarios describe. The static suite may not spawn a Prometheus binary, and that constraint is itself asserted. So the negative scenario is confirmed by observation on the deployed staging host at the ship-confirm gate, not by a test, and `tasks.md` says exactly what to run and what result would mean it worked.

**A merge deploys to both stacks** → `Platform Deploy` runs on merge to `main` for production and staging alike, so production gets the narrowed rule at the same time. That is the intended reach, and the direction of change is one-way: the rule fires on strictly fewer series than before, never on more, so the worst case is an alert that would have been raised about a non-container and now is not.

## Migration Plan

No state to migrate and no data to carry over. The rule is text in a config entry, and the moved `platform.config-checksum` is what carries it: the deploy recreates the `prometheus` container, which is created holding the narrowed rule. Rollback is reverting the commit — both edits together, since reverting the rule without the checksum leaves a deploy that changes nothing — and letting the same workflow deploy it.

Two consequences to state rather than discover:

- Prometheus's own container is replaced, so its in-memory alert state goes with it while its metrics storage does not, that being on the data volume. Any `ContainerRestartingOrOOMKilled` *currently firing* on a cgroup at deploy time therefore resolves, which sends a resolved notification to Slack for an alert nobody wanted. Alertmanager's `group_interval` is five minutes, so that arrives within one grouping cycle and then stops.
- That replacement is itself a container restart, and cAdvisor sees it. One restart is not more than three in ten minutes, so it does not raise the very rule being changed — the same reasoning `bound-host-log-growth-and-add-swap` recorded before a converge that restarted all eleven containers at once. It is said here so that nobody spends the deploy window diagnosing it.
