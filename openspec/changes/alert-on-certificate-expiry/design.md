## Context

See this change's `proposal.md` for why this gap is worth closing and why the
shape queued as entry 27 was not adopted.

The facts the design rests on, all read live on 2026-09-09 unless noted:

- Prometheus already scrapes Traefik. `platform/docker-compose.yml`'s
  `prometheus_config` carries a `traefik` job with `targets: ["traefik:8082"]`,
  the unpublished metrics entrypoint.
- That endpoint publishes `traefik_tls_certs_not_after`, a gauge documented as
  "Certificate expiration timestamp", one series per certificate, labelled
  `cn`, `sans` and `serial`. Two series exist today —
  `cn="fuperia.shatynska.com"` at 1795025651 (2026-11-18 18:14 UTC) and
  `cn="test.shatynska.com"` at 1794991353 (2026-11-18 08:42 UTC).
- Those two expire **9.5 hours apart**, share one ACME account and one Traefik
  process. Whatever stops one renewing very likely stops both, so two
  certificates firing together is this alert's expected case rather than an
  edge of it.
- Traefik's own default self-signed certificate — served for a hostname it holds
  no ACME certificate for, which is the current state of `shatynska.com` and
  `www.shatynska.com` — produces **no** series in that metric. Only real
  certificates appear.
- The live certificate is a 90-day Let's Encrypt certificate: `notBefore
  2026-08-20 18:14:12`, `notAfter 2026-11-18 18:14:11`.
- Traefik's documented default is to renew 30 days before expiry, with
  `certificatesDuration` defaulting to 2160h (90 days). The stack pins
  `traefik:v3.7.13` and sets no `certificatesDuration`, so the default applies.

Alert delivery is where this change has to be careful. Alertmanager's default
route sends to the `slack` receiver with `group_by: ["alertname"]`,
`group_interval: 5m` and `repeat_interval: 4h`, and that receiver renders
`title: "{{ .CommonAnnotations.summary }}"` and
`text: "{{ .CommonAnnotations.description }}"`. `CommonAnnotations` holds only
annotations **identical across every alert in the group**, so an alert whose
annotations name a per-certificate label produces an empty title and an empty
body the moment two of them group together.

## Goals / Non-Goals

**Goals:**

- A renewal that fails is reported while there is still time to fix it by hand,
  and the notification that reaches a person names the hostname — including
  when several certificates fail together, which is the likely case.
- No new moving part: no service, image, socket mount, credential, vendor
  account or committed hostname list.
- The rule's own silent-failure mode — evaluating an empty vector forever — is
  closed for both ways it can arise: the metrics source becoming unreachable,
  and the source staying up while no longer publishing the metric.

**Non-Goals:**

- Any check made from outside the host. That is what remains of
  `docs/change-queue.md` entry 27 after this change, and it is deliberately
  still queued.
- Warning that a hostname resolving to this host has **no** certificate at all.
  `shatynska.com` and `www.shatynska.com` are in that state today, on purpose:
  no application is bound to them yet. The chosen metric cannot express it,
  because a hostname with no certificate produces no series.
- Any change to how alerts are delivered beyond this alert's own route. In
  particular, the `slack` receiver's `CommonAnnotations` templating is left
  alone; see Decision 4.

## Decisions

### Decision 1: Read Traefik's own metric rather than probe a hostname

Traefik publishes the expiry of every certificate it holds, and Prometheus is
already scraping it. Nothing needs to be added to learn the number.

The two alternatives entry 27 offered were both considered and are both worse
for **this** failure specifically:

- `blackbox-exporter` probing each public hostname would learn the same expiry
  by opening a TLS connection, at the cost of a container, an image pin, a
  scrape job, a target list to keep in step with the applications, and — if
  targets are discovered rather than hardcoded — a Docker socket mount on
  Prometheus, which today holds every metric and mounts nothing. It would
  measure the certificate a client is actually served, which is marginally
  stronger than what Traefik believes it holds, and it would additionally catch
  a routing mistake. Neither gain is the failure being closed here.
- An external uptime vendor is independent of the host, which is a real and
  distinct property — but it is a second vendor account, an operator decision
  with a cost attached, and a configuration that lives outside this repository
  and is verifiable by nothing in it. It also detects a *broken* certificate
  more naturally than it warns about an *ageing* one.

Neither is refuted in general; both are the substance of the rewritten entry 27.

### Decision 2: Fire at 21 days remaining, aggregated per certificate

Traefik begins renewing at 30 days remaining, rechecking daily, and retries on
failure. Everything between 90 and 30 days is normal operation; everything below
30 is a renewal that has started and not succeeded.

21 days puts the alert nine days inside that window — long enough that the 24h
recheck interval, ordinary jitter and a week of ACME retries all resolve without
anyone being notified, and still three weeks before a client sees an error. Much
closer to 30 would fire on ordinary renewal; much closer to 14 would eat the
margin the alert exists to preserve.

The expression aggregates as `max by (cn) (traefik_tls_certs_not_after)` rather
than reading the raw series. The metric is labelled by `serial` as well as `cn`,
so a superseded certificate whose series lingers after a renewal would otherwise
cross the threshold nine days later and fire against a hostname that is
perfectly healthy — the cheapest imaginable way to spend a new alert's
credibility on its first fire. Whether Traefik prunes the old label set was not
established, and `max by (cn)` makes the question moot rather than answering it:
the newest expiry per hostname is the one that matters either way. It also
reduces the label set to exactly the `cn` the annotation and the route need.

The aggregation is not free. It makes the alert depend on `cn` existing, and it
converts a possible false positive into a possible false negative — see the
corresponding entry under Risks. Decision 5's companion rule is matched on
`cn!=""` rather than on the bare metric name so that the dependency is covered
by the same rule that covers the metric disappearing.

The threshold is a number in a rule, not a contract — the requirement speaks of
"the configured number of days" — so retuning it needs no specification change.
What it may **not** do is reach or exceed the renewal window, because that
breaks the requirement's second normative paragraph outright; that bound is
asserted by the derived tests rather than left to a comment.

### Decision 3: `for: 1h`

The condition is a timestamp that moves one second per second; it cannot flap.
A one-hour `for` costs nothing against a three-week horizon and removes any
possibility of firing on a scrape gap, a Traefik restart between scrapes, or the
moments after a redeploy when the metric has not yet been collected.

### Decision 4: A route of this alert's own, grouping by `cn`, repeating daily

The route added for this alert does two things, and the first is the one that
makes the alert work at all.

**Grouping by `cn` as well as `alertname`.** Under the inherited
`group_by: ["alertname"]`, two certificates crossing the threshold together land
in one group; their `summary` and `description` differ because each names its
own hostname; `CommonAnnotations` is therefore empty; and the `slack` receiver
renders a notification with no title and no text. The requirement's
identification clause would be met by the alert and defeated by the delivery.
Since both live certificates expire 9.5 hours apart and fail through the same
ACME account, this is the expected case. Adding `cn` to `group_by` on the route
this change is already adding puts each certificate in its own group and each
notification back in possession of its annotations.

The alternative — rewriting the `slack` receiver to `{{ range .Alerts }}` —
would fix this and the same latent problem in `ApplicationHighErrorRate`, and
that breadth is the reason not to do it here: it changes delivery for every
alert in the stack, including the ones this change did not examine. It belongs
in a change of its own, and is recorded as one.

**`repeat_interval: 24h`.** Under the inherited 4h, an alert that legitimately
stays firing for three weeks re-notifies roughly 126 times into the `#alerts`
channel every other alert also uses. That does not increase urgency; it trains
readers to skim the channel, damaging every other alert in it. A daily countdown
is the right cadence for a deadline three weeks out.

Only the first is asserted by the derived tests. The grouping is what makes a
delta scenario true, so an edit reverting it breaks a stated requirement and
must fail the pull request. The cadence carries no scenario: an edit reverting
it to 4h would make the alert noisy, not wrong, and pinning a notification
interval in a test would freeze a number the requirement deliberately leaves
open. That asymmetry is the reason Decision 5's argument about asserting
removable configuration applies to the scrape job and the grouping but not
here.

### Decision 5: Both silent-disarm paths are closed, not just the reachable one

`(… - time()) / 86400 < 21` returns an empty vector if the series does not
exist. An empty vector never fires and never complains. There are two ways to
get there and they need different answers:

- **The metrics source becomes unreachable.** `MetricsTargetDown` (`up == 0`)
  already covers the `traefik` job at runtime, and the derived tests assert that
  the `traefik` scrape job is still declared, so an edit deleting it fails the
  pull request instead of quietly disarming this alert.
- **The source stays up and stops publishing the metric.** A Traefik upgrade
  that renames or drops `traefik_tls_certs_not_after` leaves `up == 1`, leaves
  the scrape job in place, and leaves both of the above silent. Dependabot
  proposes Traefik upgrades on a schedule, so this is not hypothetical: it is
  the direction this repository's own automation points. A companion rule on
  `absent(traefik_tls_certs_not_after{cn!=""})` closes it, and is the reason the
  added requirement's last scenario is an obligation this change discharges
  rather than a restatement of `MetricsTargetDown`. The `cn!=""` matcher costs
  one token and widens the rule from "the metric is gone" to "no series carries
  the label this alert reads", which is the same upgrade hazard arriving by a
  second route — see Decision 2 and Risks.

The companion rule fires if Traefik ever holds no certificates at all — which is
true of a host with no application routed over TLS. That is a correct report,
not a false one: the certificate alert would be watching nothing, and saying so
is the entire point of the rule.

### Decision 6: Severity `warning`, not `critical`

Every existing rule in this stack uses `warning`, and the stack has no
`critical` tier to route differently. Introducing one here would be a change to
alert routing, which this change is not. Three weeks of lead time is also, on
its face, a warning rather than an emergency.

## Risks / Trade-offs

**The alert measures what Traefik believes it holds, not what a client is
served.** → A mistake between Traefik's certificate store and what it presents
on the wire is not covered. No such mistake has been observed, and the class is
part of what a probe would catch; it belongs to the rewritten entry 27.

**A hostname with no certificate at all is invisible.** → Stated as a Non-Goal
above and carried into the rewritten entry 27. Today this affects only
`shatynska.com` and `www.shatynska.com`, which have no application behind them
by design. It becomes worth revisiting when an application is bound to one of
them, because the failure then looks like an outage rather than an empty record.

**The stale `test.shatynska.com` certificate will be a legitimate target of this
alert.** → It renews normally today, so it will not fire; but if it ever stops,
the alert will correctly report a hostname nobody wants. That is a reason to
clean it up, recorded as its own queue entry, not a reason to filter it out of
the rule — a filter would be a place for a real hostname to hide.

**`ApplicationHighErrorRate` has the same `CommonAnnotations` problem this
change fixes for itself.** → Its `summary` names a per-router label, so two
routers erroring together deliver a blank Slack message. This change does not
fix it, because the fix is in the shared receiver rather than in a route.
Recorded as its own queue entry rather than folded in.

**`max by (cn)` trades a false positive for a false negative.** → If an upgrade
renames the `cn` label, every series collapses into one group with an empty
`cn`, the expression returns the maximum expiry across all certificates, and a
hostname genuinely days from expiry is masked behind a healthy sibling. That is
strictly worse than the lingering-superseded-series false positive the
aggregation was chosen to prevent, which is why the companion rule in Decision 5
matches `cn!=""` and so fires on exactly this condition. Named here rather than
left implicit because a false negative in an expiry alert is the failure this
change exists to prevent.

**`cn` can also be lost piecemeal, and that defeats the alert differently.** →
If one certificate loses the label while others keep it, `absent(…{cn!=""})`
stays silent, and the affected series still aggregates — under an empty `cn`,
delivering "TLS certificate for  expires soon", which names nothing and so fails
the requirement's identification clause while appearing to work. The realistic
mechanism is a certificate authority dropping the Subject CN at renewal, which
touches only the renewed certificate and is therefore exactly this shape rather
than the wholesale one above. The companion rule carries a second clause,
`count(traefik_tls_certs_not_after{cn=""}) > 0`, for it. The cost is that the
rule no longer means one thing: it means "expiry is not observable" *or* "is not
attributable", and its summary says so. That is the right trade — a rule with
two clauses beats an alert that fires and names nothing.

**Threshold and cadence are judgment calls made against one observed
certificate.** → Both are single numbers in a committed file, changed by one
line and a redeploy. The requirement fixes neither, and the only bound the tests
impose is the one the requirement states: the threshold stays below the renewal
window.

## Migration Plan

The change is confined to `platform/docker-compose.yml`'s `prometheus_rules` and
`alertmanager_config` entries. It reaches production through the existing
platform deploy pipeline; Prometheus and Alertmanager reload their configuration
on redeploy. No host change, no Ansible run, no manual step, no state to
migrate.

Rollback is reverting the commit and redeploying. Nothing outside the two config
blocks is touched, so a revert cannot leave residue.

**Confirming the effect.** A rule that is loaded but permanently empty looks
identical to a rule that works, so the confirmation must distinguish them:

1. `docker exec platform-prometheus-1 wget -qO- http://localhost:9090/api/v1/rules`
   shows `TLSCertificateExpiringSoon` and its companion loaded, with no
   evaluation error.
2. Querying the rule's expression with the threshold widened well past every
   live certificate — substituting `< 200` for `< 21` — returns one series per
   certificate Traefik holds, each carrying a `cn` label. This is the step that
   proves the expression matches real data rather than nothing, and that the
   `max by (cn)` aggregation preserves the label the annotation and the route
   both depend on.
3. Querying it at the committed threshold returns nothing, which is the correct
   state for a host whose certificates are ~70 days from expiry.
4. `docker exec platform-alertmanager-1 wget -qO- http://localhost:9093/api/v2/status`
   shows the new route present with `group_by` including `cn`.

Step 2 is what makes this a confirmation rather than a restatement of the diff.
Delivery of a multi-certificate notification cannot be observed without a real
firing, so the grouping is confirmed as configuration in step 4 rather than as
an observed Slack message.
