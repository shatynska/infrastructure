## Why

**The platform deploy has been reporting success without applying the
configuration it shipped.** Found on 2026-09-09, when
`alert-on-certificate-expiry` merged, deployed green, and did not take effect.

Everything this stack configures lives in inline `configs:` blocks in
`platform/docker-compose.yml`: Prometheus's scrape configuration, all nine
alert rules, Alertmanager's entire routing tree, and three Grafana dashboards.
Compose copies each into the container when the container is created. It decides
whether to recreate a container by comparing a per-service hash it stores on the
container as `com.docker.compose.config-hash` — **and that hash does not include
the content of those blocks.**

So `docker compose up -d --wait`, which is what `app-deploy` runs, sees no
difference, recreates nothing, reports every container `Running`, waits for them
to be `Healthy`, and exits zero. Each container keeps the configuration it was
created with, and there is no reload that would change that. The pipeline is not
lying — every container really is running and really is healthy.
It is answering a different question from the one the operator asked.

**Measured, not inferred.** Against the committed `platform/docker-compose.yml`,
with Compose v5.4.0 locally and v5.5.0 on the host:

| Mutation | `prometheus` hash | `alertmanager` hash |
|---|---|---|
| none (baseline) | `abd50e6a…` | `8e9ac2f4…` |
| alert threshold changed inside `prometheus_rules` | `abd50e6a…` **unchanged** | `8e9ac2f4…` unchanged |
| image tag `v3.14.0` → `v3.14.1` | `f32f287c…` **changed** | `8e9ac2f4…` unchanged |
| a service-level `labels:` entry added | `2c229bf2…` **changed** | `8e9ac2f4…` unchanged |

The image-tag row is the control: it establishes that the hash discriminates at
all, so the unchanged row above it means something. The label row is the fix.

And on the host, `platform-prometheus-1` carries
`com.docker.compose.config-hash=abd50e6a…` — the same value the post-change file
produces. Compose compared the file it had, found equality, and correctly did
nothing. The container's `/etc/prometheus/rules.yml` is dated `Sep 8 19:04`; the
deploy ran at `05:55` on 2026-09-09. That configuration is **copied into the
container at creation**, not bind-mounted — the container's only bind is
`/mnt/main-data/prometheus` — so there is no path by which it changes without
the container being replaced.

**One thing these measurements do not establish.** That the new stack definition
reached `/opt/platform` at all. The delivery step exited zero, and that is the
whole of the evidence: the matching `config-hash` cannot help, because old and
new files hash identically — which is the defect itself. If delivery is the real
failure, this change is the wrong change. `design.md` records that as a risk
with its falsifier; the short version is that once a label exists, a running
container either carries it or does not, and that one fact separates the two
hypotheses in a way nothing available today can.

**The blast radius is every configuration change this stack has ever made or
will make.** An alert threshold, a scrape target, a routing rule, a dashboard
panel — each one deploys green and takes no effect, and the only visible signal
is the absence of the thing you were expecting. Image bumps are unaffected,
which is why this went unnoticed: those change the hash, and recreating the
container picks up whatever configuration happens to be current at that moment.
It follows — as inference from the mechanism, not from any audit of past
deploys, which was not done — that any earlier configuration change that did
take effect will have ridden in on an unrelated image bump rather than on the
deploy that shipped it.

## What Changes

**Each service that mounts inline configuration carries a checksum of that
configuration as a service-level label**, so a change to the content changes the
service definition, and Compose recreates exactly the services whose
configuration actually moved. Three services qualify today: `prometheus` (two
configs), `alertmanager` (one) and `grafana` (five).

**A static check makes the checksum impossible to forget.** A committed
checksum that nobody regenerates is worse than none, because it reads as
protection while silently reinstating the defect. The `.github/tests` suite
recomputes each checksum from the content it names and fails when they disagree,
naming the value the label should hold — so an edit that changes a rule and not
the label fails the pull request rather than the deploy.

**No behaviour of the running stack changes.** No image, port, network, volume,
credential or alert rule is touched. What changes is whether a future edit to
one of them arrives on the host.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-platform-deploy-pipeline`: gains a requirement that a shipped
  configuration change is visible to the comparison deciding whether a container
  is replaced. The capability currently specifies how the stack is delivered and
  that the delivery is bounded, but nothing in it says the delivered
  configuration takes effect — which is exactly the gap this change found, and
  the reason a green deploy was consistent with the specification while being
  useless.

  The requirement's central clause obliges the *stack definition*, which is
  `iac-platform-services`' subject rather than this one's. It is placed here
  anyway, because what it is ultimately about is what a deploy's success means,
  and that is this capability's own territory — the requirement sits directly
  alongside *Deploy Fails When Any Healthchecked Service Does Not Become
  Healthy*, which is the other requirement narrowing the gap between "the deploy
  exited zero" and "the deploy did what you wanted".

  The requirement deliberately stops short of guaranteeing that a deploy
  reporting success has applied everything it shipped. That is a wider
  guarantee, this change does not build it, and stating it would archive an
  obligation nothing discharges.

## Impact

- `platform/docker-compose.yml` — a `labels:` block on three services. No other
  service property changes.
- The `.github/tests` suite — a new checksum-agreement assertion.
- **The first deploy after this merges recreates `prometheus`, `alertmanager`
  and `grafana`**, because their definitions change for the first time in a way
  Compose can see. That is the change working, not a side effect. Prometheus's
  data is on `/mnt/main-data` and Grafana's on `/mnt/main-data`, so neither
  loses state; Alertmanager holds only in-flight notification state.
- Nothing in `ansible/` changes. `app-deploy` keeps running
  `docker compose pull && docker compose up -d --wait`; this change makes that
  command do what it already claimed to.
- `alert-on-certificate-expiry` is blocked on this: it merged, deployed and did
  not take effect, so its own confirm gate cannot be answered until this lands
  and its rules reach the host.
