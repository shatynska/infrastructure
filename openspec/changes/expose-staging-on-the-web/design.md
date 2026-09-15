## Context

`docs/backlog.md`'s `expose-staging-on-the-web` held two things back: the web ports, and DNS. It set the trigger as "an application reaching staging" and argued that opening the ports first would mean a dummy router for ACME to answer. Measured on 2026-09-14:

- **Staging's public address is `62.238.17.177`** (Hetzner metadata, `http://169.254.169.254/hetzner/v1/metadata/public-ipv4`, from the host). `curl -m 8 http://62.238.17.177/` and `https://62.238.17.177/` from the operator's workstation both time out: the cloud firewall refuses.
- **DNS exists.** Public resolution (`dns.google`): `*.main-staging.fincci.bike` → `62.238.17.177`, `*.main-production.fincci.bike` → `2.29.14.98`, `ops.fincci.bike` → `2.29.14.98`, `staging.shatynska.com` → `62.238.17.177`. `fincci.bike` NS `dns1`/`dns2.registrar-servers.com`, MX `0 email.fincci.bike`, apex A `162.0.212.6`.
- **Staging runs the platform stack and nothing else.** `docker ps` shows eight `platform-*` containers; no container carries a `traefik.http.routers.*` label; `/letsencrypt/acme.json` in `platform-traefik-1` is zero bytes. Only Traefik publishes on `0.0.0.0` (80, 443); Grafana publishes on `100.85.219.36:3000`.
- **What production routes for `commerce-ops`** (`docker inspect` of `commerce-ops-app-1`'s `traefik.http.routers.commerce-ops.rule`, via `ssh prod`): ``Host(`commerce-ops.main-production.fincci.bike`) || Host(`ops.fincci.bike`)``. `fuperia.shatynska.com`, which §4.4's table calls "the name commerce-ops routes", is not in it.
- **The confirmation name resolves.** `unrouted.main-staging.fincci.bike` → `62.238.17.177`, through both the workstation's resolver and `dns.google`.
- **Traefik's configuration** (`docker inspect`): docker provider with `exposedbydefault=false`, `web` redirecting to `websecure`, `websecure` defaulting to the `letsencrypt` resolver with `tlschallenge`. No `--api`.

## Goals / Non-Goals

**Goals:** staging's 80 and 443 reachable from the public internet, at both configured layers together; every committed statement that says otherwise corrected; the DNS that already exists written down where this repository keeps its zone record.

**Non-Goals:** issuing a certificate within this change; any router; host-layer filtering of container ports; DNS in Terraform.

## Decisions

### 1. Open before the application deploys

The entry's ordering was right for the reason it gave — nothing to reach — and that reason has moved. `commerce-ops`'s `deploy-commerce-ops-to-staging` handoff sequences its deploy *on* this entry: its Slack request URLs and its ClickUp webhook need inbound traffic, and its webhook registration runs at container start. Holding the ports closed until the deploy would make that deploy land unusable and need repeating.

The dummy-router objection does not apply, because this change does not try to observe an issuance. With the ports open and no router, Traefik answers `301` on 80 and a `404` behind its default certificate on 443, and requests nothing from Let's Encrypt. When the application's router appears, Traefik's TLS-ALPN-01 issuance succeeds on its first attempt instead of failing until this lands. Nothing further is needed here for that.

**Alternative rejected — wait for the deploy.** Costs a second staging deploy of `commerce-ops` and buys only that the ports are opened by a change that can also watch a certificate issue, which `commerce-ops`'s own deploy observes anyway.

### 2. `0.0.0.0/0`, production's value

Let's Encrypt validates from undisclosed, changing addresses, and Slack's and ClickUp's webhook sources are not a stable published allowlist either. An allowlist would fail issuance and webhooks intermittently rather than protect anything. Staging's cloud firewall thereby matches production's exactly, which `terraform/stacks/main-staging/terraform.tfvars`'s existing comment on SSH already argues is the right shape ("no wider for staging than for prod").

### 3. Mirror at UFW although UFW does not gate these ports

`say-what-the-host-firewall-actually-gates` established that a container-published port never reaches UFW's `INPUT` chain, so `hardening_web_allowed_cidrs` changes nothing for Traefik. It is set anyway: that entry states the mirror obligation between `terraform.tfvars` and `group_vars` survives its finding, and leaving the two files disagreeing is how a reader learns the wrong rule. The `NARROWER THAN IT READS` comment in `group_vars/staging.yml` keeps its substance — this value does not decide what reaches Traefik's ports — but two of its clauses are written against the closed state: it points at "the sentence above it", which task 1.2 rewrites, and it calls the cloud firewall "the whole of what refuses from the internet" on 80/443, where after this change it refuses nothing. Both are reworded with it.

### 4. DNS: record it, keep the migration declined, replace the revisit trigger

§4.4's revisit trigger — "staging acquires its hostnames, which is the first time the manual edit would be made twice" — has fired. What actually happened answers it differently from how it was framed:

- **The edit was not per hostname.** Staging's names sit under one wildcard per server in a second zone, `fincci.bike`, so a manual edit is owed once per server (created, rebuilt, or readdressed), not once per application hostname.
- **A separate zone did not escape the mail risk.** The entry reasoned that a staging-only zone "carries none". `fincci.bike` carries live mail (`MX 0 email.fincci.bike`), so migrating either zone's nameservers carries the same risk §4.4 declined on.

So the decline stands on its stated reason, and the trigger is rewritten. Mail moving off a zone stays a trigger **for both zones**. The rest is scoped to `fincci.bike`, because `shatynska.com` already uses per-hostname records and would meet any per-hostname clause today: a server whose address changed (the moment the wildcard edit is owed — which Appendix B's "4.4 if the address changed" already sequences), or `fincci.bike` names outside the server wildcards, such as `ops.fincci.bike`, becoming frequent enough that the manual edits recur.

§4.4 gains a `fincci.bike` table beside `shatynska.com`'s, dated 2026-09-14, with exactly these rows — A values from public resolution, routing from production's router rule (Context):

| Record | Value |
|---|---|
| `*.main-production.fincci.bike` A | `2.29.14.98` — production; `commerce-ops.main-production.fincci.bike` is routed under it |
| `main-production.fincci.bike` A | `2.29.14.98` — a record of its own |
| `*.main-staging.fincci.bike` A | `62.238.17.177` — staging |
| `main-staging.fincci.bike` A | `62.238.17.177` — a record of its own |
| `ops.fincci.bike` A | `2.29.14.98` — routed by `commerce-ops`'s production router beside its technical name |

The two bare server-name rows were added after code review found them (public resolution, 2026-09-15): a wildcard does not match the name it sits under, and there is no `*.fincci.bike` (a non-existent name returns NXDOMAIN), so each is a record an address change must edit. The plan's first DNS read had missed them.

`shatynska.com`'s `fuperia` row is corrected to what was measured: it still resolves to production, and `commerce-ops`'s router no longer names it. Whether the record is still wanted is not this change's to decide, and is not decided here. §4.4's "This table is the project's only written record of the zone" becomes plural.

The zone's nameservers (`dns1`/`dns2.registrar-servers.com`) are stated in prose, as `shatynska.com`'s are. The apex A and the MX belong to a site and mailbox this repository does not operate; the MX is named as the reason the migration stays declined, and neither is transcribed as a row. `shatynska.com`'s table gains `staging` A `62.238.17.177`, recorded as it exists; nothing routes it.

§4.4's opening instruction — an A record per hostname pointing at production — is rewritten to the shape that exists: an application hostname goes under the wildcard of the server that serves it, and staging is no longer excluded.

### 5. What confirms this change

The effect is a public listener, so confirmation is observable without a certificate. It uses a name under staging's wildcard that **nothing routes** — `unrouted.main-staging.fincci.bike` — rather than `commerce-ops.main-staging.fincci.bike`, because `commerce-ops`'s staging deploy may land before confirmation and would change what that name answers. Against the public address, from the operator's workstation (see below):

- `curl -s --resolve unrouted.main-staging.fincci.bike:80:62.238.17.177 -o /dev/null -w '%{http_code}\n' http://unrouted.main-staging.fincci.bike/` → `301`.
- `curl -sk --resolve unrouted.main-staging.fincci.bike:443:62.238.17.177 -o /dev/null -w '%{http_code}\n' https://unrouted.main-staging.fincci.bike/` → `404`, and `openssl s_client -connect 62.238.17.177:443 -servername unrouted.main-staging.fincci.bike </dev/null 2>/dev/null | openssl x509 -noout -subject` names `TRAEFIK DEFAULT CERT`.
- On the host, `sudo ufw status` lists 80 and 443 allowed from Anywhere — the mirror having converged.

The expected `301` and `404`-behind-the-default-certificate are what Traefik gave the tailnet on 2026-09-13, recorded in `docs/backlog.md`'s `say-what-the-host-firewall-actually-gates`; the public listener is the same socket. **The listener is what is confirmed, not those exact codes**: a timeout means the effect is absent; any HTTP answer from Traefik on both ports means it is present. `--resolve` pins the connection to the public address, so the workstation's resolver cannot turn a DNS fault into either reading.

The operator's workstation reaches `62.238.17.177` over the public internet, not the tailnet: the same curls that time out against it today are answered at once against the tailnet address `100.85.219.36`, so the workstation is a valid outside vantage and needs no second machine.

A trusted certificate is **not** part of confirming this change; it is observed by `commerce-ops`'s first staging deploy after this merges, which `deploy-commerce-ops-to-staging` already records as its dependency.

## Risks / Trade-offs

- **Staging becomes internet-facing with no reviewer on its apply.** Bounded by what listens: Traefik alone, no API, no router. The exposure is what production's Traefik already presents for any unmatched host. → No mitigation beyond stating it; an application's router is what widens it, and that is the application's deploy.
- **Future staging applications are public by default.** Any router added to staging is reachable from the internet, not only the tailnet, from this change on. → Stated in `docs/bootstrap-a-new-host.md` where the staging difference used to be.
- **The zone record goes stale**, as §4.4 already warns of its own table. → The new table carries the date it was read.

## Open Questions

None.
