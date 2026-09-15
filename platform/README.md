# platform

The shared Compose stack for services common to the whole server — a reverse proxy, a single shared PostgreSQL instance, and metrics collection/alerting/dashboards. See `iac-platform-services`.

## Boundary

- **One shared PostgreSQL instance, for non-durable data only.** An application that keeps technical or temporary relational records on this host gets a database inside this instance rather than its own PostgreSQL container. Durable data — data whose loss would not be tolerable — never goes in this instance under any circumstances. It belongs off this host altogether, save for one narrow exception, elsewhere on the host, that nothing has yet met; see "The shared database" below.
- **A new persistent store has to say why it needs no backup.** Any volume — named or anonymous, and including one an *image* declares rather than this stack definition — or any writable host bind mount, whether added here or by an application on this host, means naming which of the reasons in *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) it satisfies, in the change that adds it — or, for a store added by an application in its own repository, in the change here that records it, since nothing else would leave a record on this side. The image half is not hypothetical: Alertmanager's store exists only because `prom/alertmanager` declares one, and nothing in this file mentions it. A store satisfying no reason owes a logical backup written outside this host and a rehearsed, checked restore before it first holds data.
- **Every application on the host reuses this stack's reverse proxy** rather than defining its own, and reuses this stack's database for any non-durable relational data it keeps here. Per-application Compose files live in separate application repositories, not here.
- **Deployed by a GitHub Actions workflow, not Ansible, and to every stack that asks for it.** A PR touching `platform/**` is validated via `docker compose config` (no deploy credential); merging to `main` runs a credential-less job that posts the diff to the run's job summary, then one deploy job **per stack**, each attached to that stack's own GitHub Environment. Which stacks receive this stack is declared by each one, in `terraform/stacks/<name>/pipeline.yml`'s `deploys_platform` field — the workflow names no stack — and the same declaration's `github_environment` is what each deploy job attaches to, so the approvers who gate a stack's Terraform apply are the approvers who gate its platform deploy. Whether a deploy waits for one is that Environment's protection rules and not the workflow's: production's waits, staging's does not. Each job joins the same private Tailscale tailnet its host is a member of (`connect-platform-deploy-via-tailscale`) and authenticates as that host's `deploy` account (provisioned by `bootstrap-ansible-host-baseline`) under a keypair of that stack's own, to trigger its one fixed deploy script over SSH — reachable only over that tailnet, not the public internet, so this pipeline never needed SSH opened beyond the operator's own CIDR. See `iac-platform-deploy-pipeline` and `.github/workflows/platform-deploy.yml`. Ansible's configuration-management scope stops at the container runtime; it never templates this stack's service definitions or invokes its lifecycle commands.

- **Every value that differs between stacks arrives through `.env`, rendered at deploy time from that stack's own Environment.** Nothing in `docker-compose.yml` is parameterised per stack and nothing needs to be: it names no hostname and no environment, and both hosts mount their data volume at the same path. A stack's database credentials, dashboard credential, certificate-registration address and alert targets are secrets on its own GitHub Environment, and a value shared between stacks by being held as a *repository* secret instead is the defect to avoid — a repository secret holds one value, so both hosts would receive it.
- **No dedicated monitoring server.** Prometheus, Alertmanager, and Grafana run in this same stack, on this same host, rather than on a second server dedicated to observability. Single-host observability risk is mitigated with an external dead-man's-switch (see Monitoring and alerting below), not a second server.

## Joining the platform network

An application repository's own `docker-compose.yml` reaches Traefik and Postgres by declaring the `platform_edge` network as external and attaching its service(s) to it:

```yaml
services:
  app:
    # ...
    networks:
      - platform_edge
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.app.rule=Host(`app.example.com`)"

networks:
  platform_edge:
    external: true
```

Reach the shared Postgres instance at `postgres:5432` on that same network — see `iac-platform-services`'s "Single Shared PostgreSQL Instance, Per-Application Databases" requirement.

### The shared database

**What it is for.** Technical or temporary records **in a relational database**, whose loss is tolerable to the application that wrote them: a job table, bookkeeping an application would rather not put in its system of record. An application that keeps data of that kind on this host gets a database and a role inside this instance rather than running a PostgreSQL container of its own.

A non-relational store — a Redis cache, a queue file, an uploads directory — is outside this instance and outside that requirement. It is governed instead by *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`), like any other store on this host.

**Nothing in it is backed up, and that is a decision rather than an omission.** It is what the scoping above buys: because the instance holds only data whose loss its writer can tolerate, the host needs no backup mechanism for it, and *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) records that classification along with what becomes owed if it ever stops being true. Do not read the absence of a dump as a gap someone forgot to close — read it as the reason durable data is not welcome here.

**Durable data goes to an external managed service that owns its own backups.** Never into this instance: that prohibition is absolute, and no backup lifts it, because holding only non-durable data is exactly what makes this instance classifiable as needing no backup. Not into a PostgreSQL container of the application's own on this host either — unless the logical backup written off the host and the rehearsed, checked restore that *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) demands are both in place before the data lands. That is a bar, not a footnote, and no application has cleared it.

**Getting a database inside the instance** is a manual step today — `docs/onboard-an-application.md` carries the `CREATE ROLE` / `CREATE DATABASE` recipe, beside the step that runs it. Automating it, and delivering the credential the way an application's deploy key is delivered, is **owed and not yet built**: the obligation's trigger fired on 2026-09-13, when `commerce-ops` became the first application given a database here, and *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) states the divergence rather than hiding it. `docs/backlog.md` `automate-per-application-database-provisioning` is the mechanism. Until it lands, a manual provisioning does not discharge the obligation.

### Upgrading the PostgreSQL major version

**A major bump is an operator's window, never an ordinary pull request.** PostgreSQL refuses to start against a `PGDATA` initialised by an earlier major. It does not upgrade in place and it does not damage the directory — it exits. So a bump merged on its own reaches the host, `docker compose up -d --wait` blocks and then fails, the deploy job goes red, and the shared instance is down for every application on that host until someone intervenes. Loud, and not data loss.

**A major can also move where the image expects its data, and that is a second thing to check rather than a restatement of the first.** From 18 the official image declares `VOLUME /var/lib/postgresql` and defaults `PGDATA` to `/var/lib/postgresql/<major>/docker`, so the 16-to-18 bump had to move the mount point with it — a volume mounted at the older `/var/lib/postgresql/data` makes 18 exit 1 whether it holds an earlier cluster, holds nothing, or was recreated empty a second earlier. **Read the image's `PGDATA` and `VOLUME` before planning the window**, and ship any mount change in the same pull request as the pin, because discarding the volume does not work around this one:

    docker pull postgres:<new major>.<minor>
    docker image inspect postgres:<new major>.<minor> --format '{{json .Config.Env}} {{json .Config.Volumes}}'

The `pull` is not optional: `inspect` reads the local store, and a workstation planning a window has by definition not run the new release yet, so without it the answer is `No such image` — which reads as the release not existing.

**What makes the upgrade cheap here is the scoping above.** Nothing in this instance is durable — that is what *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) and *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) between them guarantee — so the upgrade path is "discard the volume and let the instance re-initialise" rather than a `pg_upgrade` or a dump and restore. What it costs instead is re-provisioning, because discarding the volume discards every role and database in it.

**Do this first, before anything else.** Read what the instance holds and confirm that every database in it is one whose loss the party that owns it accepts. Two answers pass: data that is non-durable under the requirements above, and data a recorded classification admits as tolerable to lose. Anything else is a breach of those requirements, and it is the breach that is the thing to fix — not the upgrade.

Where a classification is what admits the data, tell the operator before the window rather than after. On the production host a database is already provisioned for `commerce-ops` and stands empty, reserved for a cutover that waits on a specification change classifying that application's production data as tolerable to lose; from the moment that lands and the data moves in, discarding production's volume deletes it for good.

Then, **per host**, in this order, and **take the ungated stacks first** — step 3 explains why that ordering is free. One merge reaches *every* stack whose GitHub Environment has no reviewer, so steps 1 and 2 must be complete on **all** of them before the merge, not on one of them: a second ungated stack left with its volume in place meets the new major unattended and its instance is down with nobody watching. A stack whose deploy waits for a reviewer is the one whose volume you discard last, after you have watched the instance come up healthy on the new major somewhere else. That is the only protection against an image-level incompatibility like the one above: found on an ungated stack it costs a re-plan; found on a reviewed one it is found with that host's data already gone.

**Hold every other `platform/**` merge and every `platform-deploy.yml` dispatch for the length of the window, and say so to anyone else working on the stack.** Step 2 leaves the host without the container its Compose definition declares, and any platform deploy landing in that gap — an unrelated merge, or the rebuild dispatch in `docs/bootstrap-a-new-host.md`'s Appendix B — recreates `postgres` on the **old** major and re-initialises an empty cluster in a fresh volume. That silently undoes step 2, and the rest of the window then runs against a repopulated volume as though nothing had happened.

Each step says where it runs. The on-host commands address the containers and the volume directly rather than through `docker compose`, and that is deliberate: `/opt/platform` is `deploy:deploy` mode `0750` and `ansible/roles/ops_user` grants an operator account the `docker` group and never `deploy`, so it cannot read the Compose file `docker compose` would need — and `docker` group membership is enough for every command below.

1. **On the host — tell the applications that use the instance**, and agree the window with whoever runs them. `\l` in the instance lists who they are:

       ssh <host>
       docker exec platform-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "\l"'

   The `$POSTGRES_USER` is expanded **inside** the container deliberately: that variable is the instance's superuser name from this stack's own `.env`, and it exists in the container's environment and not in the shell you are typing into. Expanded outside, it is empty and `psql` tries to connect as your own account.

2. **On the host — discard the database and its volume.** **First confirm the pull request carrying the pin is green and mergeable**, because this step is irreversible and the merge is what ends the outage it opens. A red required check, a failing `openspec validate`, an unavailable reviewer or a conflict with the trunk all leave the instance discarded and the stack that would restore it unmergeable, for as long as that takes to clear. Make the pull request ready to merge, then discard — not the other way round.

   Only the `postgres` container — Traefik, Grafana and the rest keep serving. `postgres-exporter` does **not** go red: it keeps serving `/metrics` with HTTP 200 and reports `pg_up 0`, so its container stays healthy, its Prometheus target stays up, and **no alert fires today for the instance being gone**. That is a statement about the rules as they stand, and `docs/backlog.md` `alert-on-the-exporter-being-unable-to-read-postgres` proposes the alert that would change it: `pg_up == 0` holds for the whole window, far longer than any `for:` that entry would set, so once it lands this step pages on every stack for the duration. Whoever implements it updates this paragraph, and that entry says so. Nothing else mounts this volume, so removing that one container is what frees it:

       docker rm -f platform-postgres-1
       docker volume rm platform_postgres_data

   **Check** `docker volume ls --filter name=platform_postgres_data` lists no volume. **On the production host, `commerce-ops-postgres-1` and `commerce-ops_commerce_ops_pgdata` are not this instance** — that is an application's own container, holding durable data, and nothing here touches it.

   **The applications on top of it may alert, and those pages are the window rather than an incident.** An application still answering requests but returning `5xx` without its database trips `ApplicationHighErrorRate` after five minutes. One whose container exits may trip `ContainerRestartingOrOOMKilled`, but only if it restarts more than three times in ten minutes or is OOM-killed — an application that exits once and stays down trips nothing. Say to anyone else watching that channel that these are expected until step 5 has redeployed the applications, and do not let a second operator start triaging them.

   **`ContainerRestartingOrOOMKilled` naming `platform-postgres-1` is the exception, and it is not noise — it is step 3 failing.** A `postgres` container that cannot start exits under `restart: unless-stopped` and crash-loops, which clears that rule's threshold within the window. So the one alert that reports the upgrade itself going wrong is the one this paragraph would otherwise have told an operator to ignore. Read every other container's restart alert as the window; read that container's as a stop.

   **Silence is not evidence that the applications are up**, for the reason above, so do not read it as one: what confirms them is step 5's own per-application check. What *would* be a real signal is either alert still firing once step 5 is done.

3. **From a workstation — let the deploy carry the new major to that host.** Merging the pull request that changes the pin starts one `platform-deploy.yml` run covering every opted-in stack; a stack whose GitHub Environment has no reviewer deploys immediately, and one that has a reviewer waits in that run for an approval. So the merge is what reaches every ungated stack at once, and an approval is what reaches each reviewed one — which is why steps 1 and 2 come before the merge on all of the first kind and before the approval on each of the second, and why the ungated ones go first: their whole window can complete while a reviewed stack's deploy is still sitting unapproved and its data still on disk. A host whose window falls after that run is over is redeployed on its own, by a `workflow_dispatch` of that workflow from the default branch naming its stack.

   **Check**, on the host, that the instance came back on the new major. `docker ps` without `-a` is not the check: after a failed upgrade the container is precisely not running, and the filter prints an empty table and exits 0, which reads like output you have not scrolled to.

       docker ps -a --filter name=platform-postgres-1 --format '{{.Image}}\t{{.Status}}'
       docker exec platform-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "select version()"'

   If it exited, `docker logs platform-postgres-1` says why, and the entrypoint's refusals name what they found. **Stop here rather than continuing to the next host.**

4. **On the host — recreate postgres-exporter's role.** It lives in the volume that was just discarded, so it is gone — run "One manual step per stack: postgres-exporter's monitoring role" below, with that stack's own `PLATFORM_POSTGRES_EXPORTER_PASSWORD`.

   **Check** the exporter can actually reach the instance. `MetricsTargetDown` is not that check and cannot be: it is `up == 0`, and the exporter answers `/metrics` with HTTP 200 whether or not it can connect, so a mistyped password leaves the target up, the alert silent and PostgreSQL's metrics quietly absent.

       docker exec platform-postgres-exporter-1 wget -qO- http://localhost:9187/metrics | grep -E '^pg_up |^pg_exporter_last_scrape_error '

   `pg_up 1` and `pg_exporter_last_scrape_error 0` is the pass. Anything else means the role or its password is wrong, and it is worth fixing here rather than discovering later — nothing in this stack alerts on it.

5. **From a workstation — re-provision every application database, then redeploy that application.** Each is gone with the volume, which each application's classification tolerates and none can start without. Run the recipe in `docs/onboard-an-application.md` for that host, per application, with `rotate=yes`. **That block is a workstation paste, not an on-host one** — it calls `gh` and then reaches the host over `ssh` itself, so pasted into a session on the host it aborts at the first `gh` under `set -eu`, having changed nothing. The password is generated fresh and delivered to that application's Environment, so only that application's **next deploy** picks it up. Trigger that deploy from the application's own repository; nothing here can. **Check** per application that it comes up and that `\l` in the instance lists its database owned by its own role.

**Dependabot will propose the next major, and closing that proposal is the design working.** No `ignore` stanza is configured for this image, deliberately: an `ignore` is permanent and silent, and would suppress the only signal this repository gets that its PostgreSQL major has reached end of life. Closing an individual pull request keeps the signal and costs nothing — so expect a recurring, correctly-refused pull request rather than noise. `cover-platform-images-with-dependabot`'s design.md, decision 3, is where that was argued.

## Monitoring and alerting

Prometheus collects metrics from node-exporter (host), cAdvisor (every container on the host), postgres-exporter (the shared Postgres instance), and Traefik's own metrics endpoint (per-application HTTP status/error-rate counts). Alertmanager routes alerts to Slack, plus a permanent Watchdog alert routed to an external dead-man's-switch heartbeat service. Grafana provides dashboards.

**Nothing here labels an alert with the host it came from.** Prometheus declares no `external_labels`, so a `MetricsTargetDown` from one stack and one from another are identical text. What separates them is the delivery target: each stack's `PLATFORM_SLACK_WEBHOOK_URL` should address a channel of its own, and each stack's dead-man's-switch check should be its own. That is a property of the values in each Environment, and **nothing in this repository can check it** — two stacks pointed at one channel produce unattributable alerts and no build fails. `docs/backlog.md` carries the entry that would label them at the source.

Traefik's certificate expiry is alerted on separately, at 21 days remaining — Traefik renews at 30, so anything under that is a renewal that started and did not finish, and it is otherwise silent until the certificate actually expires. That alert takes a route of its own so each hostname is named in its own notification rather than several collapsing into one that names none; `alert-on-certificate-expiry`'s design.md has the reasoning.

See `add-platform-monitoring`'s design.md for the full rationale — network placement, why configuration is inline in `docker-compose.yml`, and the trade-offs accepted along the way.

**Grafana is reachable only over the private Tailscale tailnet** — not routed through Traefik, not on the public interface. From a device already on the tailnet, open `http://<tailnet-IP-or-MagicDNS-name>:3000` and sign in as `admin` with the credential in that stack's own `PLATFORM_GRAFANA_ADMIN_PASSWORD` secret. **Each stack has a Grafana of its own, with its own credential**, and the bind address is that stack's tailnet address — resolved by the deploy job from the same secret that names its SSH target, which is why that secret must be a tailnet address and never a public one.

### Editing an inline config: regenerate the service's checksum

**Every service mounting a `configs:` block carries a `platform.config-checksum` label, and editing that block means regenerating it.** This is not bookkeeping. Compose decides whether to replace a container by comparing a digest of the service definition, and that digest does not cover the content of inline configs — which are copied into the container when it is created, with no reload path. Before these labels existed, editing a scrape target, an alert rule, a routing rule or a dashboard produced a deploy that replaced nothing, reported every container healthy, exited zero and changed nothing on the host.

You do not have to compute the value. The `.github/tests` suite recomputes it, fails the pull request when it disagrees, and names the value the label should hold — so this is a paste. Expect the edit to replace that service on the next deploy; that is the point. `apply-shipped-config-on-deploy`'s design.md carries the algorithm and the reasoning.

One thing the label does **not** cover: a value the config interpolates from `.env`, such as Alertmanager's Slack webhook. Rotating that secret changes nothing the checksum can see, so the container is not replaced and keeps the old value — force a replacement by hand when you rotate one. `docs/backlog.md` entry 12 covers closing this properly.

### One manual step per stack: postgres-exporter's monitoring role

postgres-exporter connects to the shared Postgres instance as a dedicated, restricted-privilege role — never the instance's superuser credential. This role is **not** created by any automation in this repository (deliberately — see design.md's "That role is created by a one-time manual operator step, not by this change's automation"): run this once **per stack**, by hand, against that host's running `postgres` container, using a password matching whatever is stored in that stack's own `PLATFORM_POSTGRES_EXPORTER_PASSWORD` secret — each stack has its own instance, its own role and its own password:

```sql
CREATE ROLE pgexporter WITH LOGIN PASSWORD '<value of PLATFORM_POSTGRES_EXPORTER_PASSWORD>';
GRANT pg_monitor TO pgexporter;
```

`pg_monitor` is Postgres's own built-in predefined role: read-only access to the statistics views postgres-exporter's standard collectors query, no table data access, no superuser.

**`#`, `@`, `/`, `?` and `:` are safe in this password; `$` and a leading quote are not.** Until 2026-09-15 the first four were not either: the exporter was given a single `DATA_SOURCE_NAME` URL with the password interpolated into it, so any of them silently changed what the URL meant rather than failing — `#` discarded the host, the port and the database after it. Both hosts ran that way with a password containing `#`, reporting `pg_up 0` while their containers stayed healthy and their Prometheus targets stayed up. The exporter now takes `DATA_SOURCE_URI`, `DATA_SOURCE_USER` and `DATA_SOURCE_PASS` separately, so the password reaches it as a value rather than as part of a URL.

**`$` and a leading quote are a different defect, still open, and they corrupt the value before the exporter ever sees it** — so this is not a warning about the exporter but about every secret this stack renders. `platform-deploy.yml` writes `.env` with an unquoted `echo`, and Compose's dotenv parser expands `$…` in an unquoted value and strips a wrapping quote. Measured with `docker compose config` on 2026-09-15: `ab$c#d` arrives as `ab#d`, and `"abc"def` as `abc`. The result is a wrong password, an HTTP 200, `pg_up 0`, a healthy container and no alert — the same silence as before. `docs/backlog.md` `render-the-env-file-so-a-secret-survives-it` is that gap. **Until it closes, generate these passwords without `$` and without a leading quote.**

What `.github/tests` enforces, stated exactly rather than generally: in `platform/docker-compose.yml`, a secret-bearing variable may not sit against URL punctuation within its own word, where that word is a URL — a scheme, a `user:secret@host` authority, a query parameter, or text concatenated onto a secret that is itself a URL. It reads a service's `environment:` and the inline `configs:` blocks, in both the `${VAR}` and `$VAR` forms. **Which names count as secrets is read from `platform-deploy.yml`'s render step rather than guessed from keywords**, which is how `SLACK_WEBHOOK_URL` and `DEADMANSWITCH_URL` are covered — both are credentials and neither name says so. A value that is nothing but the secret, as Alertmanager's `api_url` is, is the opposite case and passes. Nothing checks the `.env` rendering above, which is why that paragraph names a backlog entry rather than a check.

**If this role is ever missing or its password out of sync — after rebuilding the shared instance, or after the volume reset above — nothing tells you.** `MetricsTargetDown` does not, whatever an earlier reading of it suggested: it is `up == 0`, and postgres-exporter serves `/metrics` with HTTP 200 and `pg_up 0` when it cannot connect, so its target stays up and no alert fires while PostgreSQL's metrics are absent. Verified against `v0.20.1` on 2026-09-15. `pg_up` is what would catch it and nothing alerts on it yet — `docs/backlog.md` `alert-on-the-exporter-being-unable-to-read-postgres` is that gap. Until it lands, this is checked by hand, with the command in *Upgrading the PostgreSQL major version* above.

### One manual step per stack: dead-man's-switch registration

Register **each** host with a third-party heartbeat/dead-man's-switch service (e.g. Healthchecks.io) and put the ping URL it gives you in that stack's own `PLATFORM_DEADMANSWITCH_URL` secret. One check per host: a single check fed by two hosts stays green while either one is alive, which is the opposite of what this exists to notice. Configure that service's expected check-in interval to comfortably exceed Alertmanager's Watchdog `repeat_interval` (2 minutes, per `platform/docker-compose.yml`'s `alertmanager_config` -- lowered from an original 5 minutes after `fix-deadmansswitch-repeat-interval` found that value, equal to the inherited `group_interval`, caused real delivery to silently halve to every ~10 minutes instead), so a single delayed gossip round doesn't produce a false page. This is the actual implementation of the mitigation named in "No dedicated monitoring server" above — if the host, Alertmanager, or the whole platform stack goes down, this is what notices.

## Status

`docker-compose.yml` defines Traefik (ACME-issued TLS, Docker-label routing), a single shared PostgreSQL instance, and the monitoring/alerting stack described above, deployed by `.github/workflows/platform-deploy.yml` to every stack whose declaration opts in. One definition, several hosts: what differs between them is `.env` and nothing in this directory. See `deploy-platform-compose-stack` for the change that built the original stack, `integrate-ansible-host-config` for the change that established the boundary above, and `add-platform-monitoring` for the monitoring/alerting stack.

Every service in this stack defines a real Docker `healthcheck:` reflecting its own readiness, not just that its process is running -- this is what lets `docker compose up -d --wait` (in `app-deploy` on the host) actually fail the deploy job when a service comes up broken, instead of reporting false success. When adding a new service here, give it a real healthcheck too (see `add-platform-service-healthchecks` for why this matters and what it does and doesn't catch).
