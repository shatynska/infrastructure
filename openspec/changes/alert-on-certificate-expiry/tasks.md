Two steps this change owes are not in this list, because they happen after the
commit that writes this file and so could never be ticked in it: removing the
branch and removing the working tree, both after the record's own pull request
has merged and every other pull request this change opened is merged. The
archive step itself is task 6.5 below and is unaffected.

## 1. The alert rules

- [ ] 1.1 Add `TLSCertificateExpiringSoon` to the `prometheus_rules` config in `platform/docker-compose.yml`, in the existing `platform-monitoring` group: expression `(max by (cn) (traefik_tls_certs_not_after) - time()) / 86400 < 21`, `for: 1h`, `severity: warning`, with a summary naming `{{ $$labels.cn }}` and a description giving the days remaining. Note the `$$` escaping the surrounding rules block already uses for Go template variables. Verify `docker compose -f platform/docker-compose.yml config` still parses the file.
- [ ] 1.2 Add the companion rule on `absent(traefik_tls_certs_not_after{cn!=""})`, `for: 15m` — long enough to sit out a Traefik restart or a redeploy — per this change's `design.md` Decision 5. Without it, a version bump that renames the metric, or that renames the `cn` label task 1.1 aggregates on, disarms that rule while leaving `up == 1` and the scrape job intact. Verify the same `docker compose config` parse succeeds.
- [ ] 1.3 Add a matcher-scoped route for the alertname in task 1.1 to `alertmanager_config`'s `route.routes`, keeping the `slack` receiver, with `group_by: ["alertname", "cn"]` and `repeat_interval: 24h`, per this change's `design.md` Decision 4. Verify the parse succeeds and the Watchdog route is untouched.
- [ ] 1.4 Comment the additions in the style the surrounding blocks use: the 21-day threshold against Traefik's documented 30-day renewal window, the `max by (cn)` aggregation against a lingering superseded series, the `group_by` override against the `CommonAnnotations` templating in the `slack` receiver, and the 24h repeat against the inherited 4h. Verify by reading the diff — a reader who does not already know why any of the four is there should not have to leave the file.

## 2. Derived tests

Written by an author other than whoever implements section 1, from the added
requirement in this change's delta spec rather than from the rules as written.
Test command: `python3 -m unittest discover --start-directory .github/tests`,
run from the repository root; test-path glob `.github/tests/*.py`. The Terraform
and Molecule rows of `AGENTS.md`'s testing table do not apply — this change
touches neither a Terraform module nor an Ansible role.

A `.github/tests` assertion is a static read of a committed file, so it cannot
avoid naming the identifiers it reads. Naming a metric or a configuration key
below is therefore a constraint of the test layer, not the plan handing the
author its answers: what is left to the author is which properties are worth
asserting, how each is expressed, and where in the suite they belong.

- [ ] 2.1 Assert the `prometheus_rules` config declares an alert whose expression reads `traefik_tls_certs_not_after`, and whose annotations name the certificate rather than describing it generically. Derives from the requirement's first scenario. Verify the assertion fails against the file as it stands before section 1.
- [ ] 2.2 Assert the alert's threshold is strictly less than the renewal lead time it is stated against — a numeric read of the expression, compared with 30. Derives from the requirement's second normative paragraph and its "renewing normally raises no alert" scenario, which nothing else in this change holds. State in the test's own text where 30 comes from: it is Traefik's default renewal lead time, which holds only because the stack sets no `certificatesDuration`. Verify the assertion fails when the threshold is raised to 30 in a copy of the file.
- [ ] 2.3 Assert the Traefik service declares no `certificatesDuration`, which is the precondition that makes 2.2's constant the real renewal lead time rather than an unpinned upstream default reproduced by hand. A static read of the same file. Verify the assertion fails when the option is added to a copy.
- [ ] 2.4 Assert the expression aggregates per certificate rather than reading the raw series, so a superseded series cannot fire against a healthy hostname. Derives from the superseded-certificate scenario. Verify against the implemented rule and against a copy with the aggregation removed.
- [ ] 2.5 Assert the alert's route does not deliver under the inherited grouping alone: it groups by the per-certificate label as well as by alertname. Derives from the "several certificates are each identified" scenario — under the `slack` receiver's `CommonAnnotations` templating this is what makes that scenario true. Verify the assertion fails when the route's `group_by` is reduced to alertname.
- [ ] 2.6 Assert a rule exists reporting that certificate expiry is no longer observable at all, and that the `traefik` scrape job feeding both rules is still declared in `prometheus_config`. Derives from the last scenario. Verify each half fails when its target is removed from a copy of the file.
- [ ] 2.7 Assert every alert added by this change carries a `for` duration and a `severity` label, so a rule added later without either is caught. Verify against the implemented rules.
- [ ] 2.8 Run the whole suite and confirm it is green apart from the assertions section 1 has not yet satisfied, so that a later green run means something.
- [ ] 2.9 Commit the derived tests exactly as their author wrote them, before any folding or relocation, per `docs/change-queue.md` entry 42 — so that whatever the implementer changes about them afterwards is a reviewable diff rather than a claim. Verify the commit contains tests only.

## 3. Documentation of the alert

- [ ] 3.1 Extend the existing prose in `platform/README.md`'s "Monitoring and alerting" section with a sentence naming the certificate-expiry alert, its threshold, and that it is routed to Slack separately so each hostname is named. That section names no individual rule today and this change does not start a rule inventory there — whether the README should list every rule is `docs/change-queue.md` entry 13's question, not this change's. Verify by reading the section: the new sentence sits in the prose without implying a complete list exists.

## 4. Queue and deferred-work bookkeeping

- [ ] 4.1 Rewrite `docs/change-queue.md` entry 27. Its three named failures each get a different treatment, and the entry should say which: the **ACME failure** is narrowed rather than kept or dropped — its expiry half is delivered here, and what survives is the half this change explicitly does not cover, a hostname resolving to this host with no certificate at all; the **DNS** and **firewall** failures are kept, restating the firewall one to acknowledge the UFW layer of `AGENTS.md`'s firewall split (entry 23: applied by hand, no gate) and the drift workflow (entry 32: fails into silence), and the DNS one to acknowledge that a third-party-nameserver or registration failure is not bounded by edit frequency. Record against the mechanism choice that `blackbox-exporter` cannot serve the entry's own motive, since a probe from the host never traverses the Hetzner edge filter. Verify the entry no longer claims the certificate-expiry gap is open and no longer offers a mechanism that cannot meet it.
- [ ] 4.2 Correct the DNS record table under "Managing DNS in Terraform" in `docs/deferred-work.md`: add `test.shatynska.com` A → `2.29.14.98`, and date the correction. Verify by resolving all four names and comparing against the table.
- [ ] 4.3 Add a new `docs/change-queue.md` entry for the stale `test.shatynska.com` — the throwaway `whoami` smoke-test hostname from the archived change `fix-traefik-docker-api-version`, whose container is gone (the name 404s) while its A record and its Let's Encrypt certificate are both live and still renewing. Verify the entry states what has to be removed and in what order, so nothing is left serving a name whose certificate has already gone.
- [ ] 4.4 Add a new `docs/change-queue.md` entry recording that `ApplicationHighErrorRate` delivers a blank Slack notification whenever two routers error together, for the same `CommonAnnotations` reason this change routes around, and that the general fix is in the shared `slack` receiver and so changes delivery for every alert in the stack. Verify the entry says why this change did not fold it in.

## 5. Verification

- [ ] 5.1 Run `python3 -m unittest discover --start-directory .github/tests` from the repository root and confirm every assertion from section 2 passes.
- [ ] 5.2 Run `pre-commit run --all-files` and confirm it is clean, or that every remaining finding predates this change and is named.
- [ ] 5.3 Run `openspec validate --strict alert-on-certificate-expiry` and confirm it passes.
- [ ] 5.4 Dispatch the change's code review over the diff and record the verdict; fix and re-review until it clears.

## 6. Ship

- [ ] 6.1 Open the pull request once section 5 is green, and wait for the operator's confirmation that continuous integration passed, that it merged, and that the platform deploy is healthy.
- [ ] 6.2 Confirm the effect by the four steps in this change's `design.md` under "Confirming the effect". Step two — widening the threshold and seeing one series per certificate, each carrying a `cn` label — is the one that distinguishes a working rule from a permanently empty one. Wait for the operator's confirmation.
- [ ] 6.3 Record in this change's artifacts that multi-certificate delivery was confirmed as configuration rather than as an observed notification, since observing it needs a real firing. Verify the record names what was and was not observed.
- [ ] 6.4 Bring the branch back to the freshly fetched trunk.
- [ ] 6.5 Commit the specification record and open its own pull request.
