## Why

Traefik terminates TLS for every public hostname this host serves, and renews
each certificate through Let's Encrypt at roughly 30 days remaining. Nothing
reports a renewal that does not happen.

Every other total-outage failure this host can suffer already has a detector.
The host, the platform stack or the alerting pipeline dying is caught by the
permanent Watchdog routed to the external dead-man's-switch, within about ten
minutes — `openspec/specs/iac-platform-services/spec.md`, *External
Dead-Man's-Switch Heartbeat*. A service or exporter dying is caught by
`MetricsTargetDown`. A container crash-looping, an OOM kill, and host disk, CPU
and memory pressure each have a rule. A certificate quietly ageing out does not.
It is silent for the whole 30 days it is failing, and then every visitor gets a
browser interstitial at once.

The cost of closing it turns out to be a single alert rule. Read from
`platform-prometheus-1` on 2026-09-09, Traefik's own metrics endpoint — already
scraped by the `traefik` job at `traefik:8082` — carries:

```
# HELP traefik_tls_certs_not_after Certificate expiration timestamp
# TYPE traefik_tls_certs_not_after gauge
traefik_tls_certs_not_after{cn="fuperia.shatynska.com",...} 1.795025651e+09
traefik_tls_certs_not_after{cn="test.shatynska.com",...}    1.794991353e+09
```

An expiry timestamp per certificate, labelled by common name, in Prometheus
today. The gap is not that the data is missing. It is that no rule reads it.

**Why this shape and not the queued one.** `docs/change-queue.md` entry 27
proposed either an external uptime service or `blackbox-exporter` in the
platform stack, probing each public hostname from outside, and named three
failures it would catch: a DNS mistake, a Traefik ACME failure, and a
cloud-firewall change blocking 443. Exploring it against the running system did
not refute the entry — it separated one of the three failures out as needing no
prober at all:

- **`blackbox-exporter` cannot see the firewall case at all.** It runs on the
  host, and a probe from the host to the host's own public address never
  traverses the Hetzner cloud firewall, which filters ingress at the network
  edge. The option the entry offered as the cheaper of the two does not satisfy
  the entry's own stated motive. This is the finding that most changes what the
  entry should say.
- **The firewall case has partial cover, not full cover.** `web_allowed_cidrs`
  reaches production only through the gated pipeline of
  `openspec/specs/iac-cicd-pipeline/spec.md`, where a human reviews the exact
  plan, and a plan closing 443 is among the most visible diffs that pipeline can
  produce. But the Hetzner firewall is only one of the layers between the
  internet and 443: `AGENTS.md`'s firewall-split convention makes UFW the
  co-equal host-level layer, entry 23 records that the playbook applying it is
  run by hand with no gate, and entry 32 records that a console-side change is
  caught only by a drift workflow that itself fails into silence. So the
  reachability of 443 is gated in one of at least three ways it can close, and
  an outside check remains the only thing that would see the other two.
- **The DNS case is not bounded by how often the zone is edited.**
  `docs/deferred-work.md` records that `shatynska.com` is served by third-party
  nameservers at ukraine.com.ua. A provider outage or a lapsed registration is a
  DNS failure with no edit behind it, and it is exactly the "invisible until a
  person notices" class the entry names.
- **The certificate case is the one that is both total and silent** — and
  uniquely among the three, it needs no prober, inside or outside, because
  Traefik already publishes the number.

So this change delivers the certificate failure with a rule. Entry 27 keeps its
DNS and firewall failures, restated more accurately than it states them today;
its third, the ACME failure, is narrowed rather than kept — the expiry half
ships here, and what survives in the entry is the half this change does not
cover, a hostname resolving to this host with no certificate at all. The entry
also gains the finding that one of its two proposed mechanisms cannot serve its
own motive.

## What Changes

**One alert rule is added to the `prometheus_rules` config in
`platform/docker-compose.yml`**, firing when any certificate Traefik serves is
within a configured number of days of expiry, and naming the affected common
name. It reads a metric the existing `traefik` scrape job already collects: no
new service, no new image, no additional Docker socket mount, no external vendor
account, and no committed list of hostnames to keep in step with reality.

**The alert gets a route of its own**, because the default one would defeat it.
Alertmanager groups by `alertname` and the Slack receiver renders
`{{ .CommonAnnotations.summary }}`, which is empty whenever the alerts in a
group carry differing annotations. Two certificates approaching expiry together
would therefore deliver a notification naming neither — and the two certificates
this host holds expire nine and a half hours apart through one ACME account, so
that is the expected case rather than an edge. The route groups by `cn` as well,
and takes a `repeat_interval` of 24h so a three-week countdown does not post to
`#alerts` 126 times.

**Both of the rule's silent-death modes are closed.** A rule over
`traefik_tls_certs_not_after` produces no series if the metric stops existing,
and a rule evaluating an empty vector never fires and never complains. If
Traefik becomes unreachable, `MetricsTargetDown` already reports it; if Traefik
stays up and a version bump renames or drops the metric, nothing today would —
so a companion rule on `absent(traefik_tls_certs_not_after{cn!=""})` covers the
second case, and the derived tests assert the scrape job that feeds both. The
`cn!=""` matcher is what makes that rule cover a renamed label as well as a
renamed metric, which matters because the main rule aggregates on `cn`.

Four pieces of bookkeeping travel with it, because each is a fact this change
established and none belongs inside the change record, which is archived:

- `docs/change-queue.md` entry 27 is rewritten: the certificate clause is
  removed as delivered here, the three failures it named are retained with the
  firewall and DNS cases stated more accurately than the entry states them
  today, and the finding that `blackbox-exporter` cannot serve the entry's own
  motive is recorded against the mechanism choice.
- The DNS record table under "Managing DNS in Terraform" in
  `docs/deferred-work.md`, written on 2026-09-08 as the records as read, is
  corrected: it omits `test.shatynska.com`, which resolves to the host today.
- A new `docs/change-queue.md` entry records the stale `test.shatynska.com`
  itself — a throwaway `whoami` smoke-test hostname from the archived change
  `fix-traefik-docker-api-version`, whose container is long gone but whose A
  record and Let's Encrypt certificate are both still live and still being
  renewed. Cleaning that up is separate work.
- A new `docs/change-queue.md` entry records that `ApplicationHighErrorRate` has
  the same blank-notification problem this change fixes for itself, and that
  fixing it properly means changing the shared Slack receiver — which alters
  delivery for every alert in the stack and so belongs in its own change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-platform-services`: gains a requirement that a TLS certificate the shared
  reverse proxy serves is alerted on before it expires, with enough lead time to
  act, and that the notification names it.

  It is a requirement of its own rather than a scenario under the existing
  *Metrics-Based Alerting Covers Host and Service Health*, on the strength of
  what it says rather than of what that requirement enumerates — its normative
  content is a *relationship between two numbers*, the alert threshold and the
  proxy's own renewal lead time, which no scenario under an alert-coverage
  enumeration would carry, plus an explicit statement of what it does not cover.
  (The enumeration argument would be weak on its own: that requirement already
  houses a scenario about unreachable metrics sources, which its own list does
  not name either.)

  The other candidate home, considered and not chosen, is *Reverse Proxy Is
  Traefik with ACME-Issued TLS*, which does own certificate lifecycle. It was
  rejected because that requirement is about the proxy issuing certificates, and
  this one is about the monitoring stack observing them — placing it there would
  put an alerting obligation in the one requirement that says nothing about
  alerting.

## Impact

- `platform/docker-compose.yml` — the `prometheus_rules` and
  `alertmanager_config` entries only. No service, network, volume, image pin or
  environment variable changes, so `platform/.env.example` is unaffected and
  `platform/README.md` gains only a sentence.
- The `.github/tests` suite gains assertions over the committed Compose file,
  run by `python3 -m unittest discover --start-directory .github/tests`. Which
  file in that suite they land in is the test author's call, not this
  proposal's.
- `docs/change-queue.md` and `docs/deferred-work.md` — as described above.
- Deployment is the existing platform deploy pipeline; a Prometheus or
  Alertmanager configuration change takes effect on redeploy and needs no host
  or Ansible change.
- No new dependency. Dependabot's `platform-monitoring-images` group is
  untouched, because no image is added.
