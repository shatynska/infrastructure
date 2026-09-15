# Backlog

Changes this project has identified and not yet opened. An entry is deleted when its change is archived. See `AGENTS.md`, "A second change surfacing".

An entry carries a number, the change's name, and — where it has one — what it waits on. Not everything here is blocked: where an entry is free to be taken, it says instead why it was recorded rather than folded into the change that found it, usually because it belongs to a different concern than the one that change was closing.

Related entries tend to sit together and an entry another depends on tends to come first, but neither is a rule: a new entry is appended, so the order says nothing on its own. Where one entry actually waits on another, the entry says so.

**The number is an identifier, not a priority, and it is not stable.** This file has been renumbered from 1 before and may be again, so a number written elsewhere — in a source comment, a specification, an archived change record — may no longer name the entry it was written for. The names are stable; cite an entry by name where the citation has to survive.

---

## 1. close-public-ssh-and-manage-sshd-explicitly

**Not blocked; a policy decision the hardening role already anticipates.**

Port 22 is open on the cloud firewall and in UFW from one ISP `/24` (`ssh_allowed_cidrs` in `terraform.tfvars`, mirrored in `group_vars/production.yml`). The tailnet rule in `ansible/roles/hardening/tasks/main.yml` admits SSH from `100.64.0.0/10` independently, and that task's own comment says an empty public CIDR list "is safer than what prod runs". Every non-operator path (the deploy jobs) already uses the tailnet; the public rule exists for the operator alone, and the operator is on the tailnet too.

**What changed when the host converge moved into the pipeline.** This entry used to wait on that, and the wait is over: `host-converge.yml` reaches every host over the tailnet and needs no allowance in the cloud firewall, so closing port 22 does not lock the pipeline out. What it does close is the fallback. Until this entry lands, the ISP `/24` is what makes a converge that wedges `tailscaled` survivable without Hetzner's console -- so the order matters in one direction only: this must not precede a converge pipeline that has been seen to work. It now has one, but "seen to work" means more than one green run on production, not the first.

**One more path to enumerate before closing it**, which did not exist when this entry was written: the *first* converge of a host, and of a rebuilt host, is an operator's from a workstation over the **public** address -- the pipeline reaches a host through the tailnet, and joining the tailnet is what that play does. `docs/bootstrap-a-new-host.md` §6.3 and Appendix B are both that path. Closing public SSH outright would make a new host unreachable by the only thing that can configure it, so this change has to say how a host is bootstrapped afterwards: a temporarily widened `ssh_allowed_cidrs` applied through the pipeline, or Hetzner's console.

Closing it is `ssh_allowed_cidrs = []` -- except that `modules/server`'s validation refuses an empty list on lockout grounds, which was the right default before the tailnet existed and is the thing to revisit now. The Terraform firewall rule and the UFW rule move together (the *Host-Level Security Owned by Ansible, Cloud Firewall Owned by Terraform* requirement's sync obligation), and the change should say what the recovery path is if the tailnet is unreachable: Hetzner's console, which the cloud firewall does not gate.

Two smaller things in the same area, neither managed by any role today, both running on the image's defaults: `sshd_config` (the host has no drop-in under `/etc/ssh/sshd_config.d/`; `PasswordAuthentication` is unset, harmless only because no account has a password) and `unattended-upgrades` (installed and enabled by the image, not by `hardening`, with no `Automatic-Reboot` decision recorded). Both belong to the hardening role, and both can be asserted by its Molecule scenario.

## 2. manage-root-authorized-keys-from-a-role

**Not blocked. Recorded by `apply-host-configuration-through-a-gated-workflow`, which installs a key it cannot revoke.**

That change gives each environment a dedicated `ansible-ci` keypair whose public half authorises `root` on that host. No role manages `root`'s `authorized_keys`: the file's original entry arrives from Hetzner at server creation, and `hcloud_server.ssh_keys` cannot be changed without recreating the server. So the converge key is appended by hand at `docs/bootstrap-a-new-host.md` §6.6, and **revoking it is an edit on the host** rather than a commit.

That is not a regression -- root's existing key is unmanaged in exactly the same way -- but it is the one credential in this repository with no revocation path through the repository, and it is the most powerful one CI holds.

**Why it is its own change and not a fold-in.** A role that owns `root`'s `authorized_keys` can lock every operator out of a host, which is a different class of risk from anything the `hardening` role does today. It wants scenarios of its own, and the `ops_user` role's per-entry `state:` model -- where revocation is `state: absent` with the entry **left in place** until a converge has removed it -- is the shape to follow rather than invent. Note also that `exclusive: true` is the only form that actually revokes, and is the form that can lock everyone out; a non-exclusive managed list adds keys and never removes one.

**The chicken-and-egg is real either way and is not an argument against it**: the role that would install the key is a role CI runs, so the first installation is manual whichever shape this takes. What the change buys is every installation after the first.

## 3. report-an-absent-tailscale-auth-key

**Not blocked on another change; recorded because doing it well is a larger job than it looks, and doing it badly breaks the host's reachability.**

`fix-volume-discovery-and-consistency` added the requirement *A Role's Absent Required Input Is Reported by Name* (`iac-host-configuration`) and satisfied it for `hardening_ssh_allowed_cidrs` and `deploy_apps`. That requirement is deliberately scoped to inputs a role consumes on **every** run, and this entry is the class it excludes.

`ansible/roles/tailscale/defaults/main.yml` documents `tailscale_auth_key` in almost the same words as the two variables that were fixed, which is what makes this look like an oversight rather than a decision. It is not. The key is consumed only inside `Bring the host onto the tailnet`, guarded by a `when:` that skips when the host is already on the tailnet — so a re-converge of the prod host, the common case, never evaluates it and does not need it supplied. An unconditional assertion would start demanding it on every run and break a working path.

Three things make this its own change rather than a fold-in:

- The diagnostic has to fire under the **same** condition as the join, which means naming that four-limb condition once instead of restating it. Its `POLARITY` comment warns that reading it the wrong way silently stops a host joining the tailnet — the mechanism the deploy pipeline depends on to reach the host at all.
- `tailscale` carries **no Molecule scenario**, so there is nothing to regress against. Any change here should bring the role's first scenario with it.
- The failure is currently *censored*: the consuming task sets `no_log: true`, so an absent key surfaces as a redacted error rather than a named one. That is worth fixing on its own merits and is invisible from the outside.

**This entry now has a caller it did not have, and it owes a decision because of it.** `host-converge.yml` supplies `tailscale_auth_key` on every converge, as an **empty string** -- deliberately, because a job that reaches a host through the tailnet cannot reach one that is not on the tailnet, so there is no state in which it both connects and needs to run `tailscale up`. That makes "absent" and "empty" two different things here where this entry assumed one: a diagnostic that fires only on *undefined* would never fire for the pipeline, and one that fires on *empty* would fire on every pipeline converge of a host that is already joined -- which is all of them. Whatever this entry builds has to say which it means, and the answer is probably neither on its own but the join condition itself, which is what the entry already says is the hard part.

Recorded by `fix-volume-discovery-and-consistency`, whose `design.md` Decision 3a carries the full reasoning.

## 4. collect-each-role-s-apt-installs-into-one-task

Recorded 2026-09-11 by `cache-the-apt-index-within-a-converge`, whose Non-Goals name it and whose own saving it would extend.

That change bounded how stale an index a converge will install from, which removes the *second and later* fetch of a run. What it leaves is the tasks themselves: `hardening` installs `ufw` and then `fail2ban` as two `apt` tasks seconds apart, where `ansible.builtin.apt` accepts a list and would install both in one. One task cannot re-fetch what it just fetched, so the bound becomes belt-and-braces rather than the mechanism.

**Why it was not folded in.** It is a larger change to two roles than the bound was, and it moves things a reader depends on: which task a failure surfaces under, what a scenario's assertions name, and — for `hardening` — whether `ufw` being installed and `fail2ban` being installed remain separately observable, since the scenarios assert on each. It also interacts with the ordering the roles currently guarantee between install and configure.

**What it would actually save is smaller than it looks**, and worth measuring before it is proposed. After the bound, `hardening`'s container fetches twice, and one of those two is the test fixture's deliberate back-date. Collapsing the tasks removes neither: the first fetch of a fresh container is owed either way. The gain is on a host where the bound is inert — one carrying a maintained `update-success-stamp`, where `cache.update()` never advances what `get_cache_mtime()` reads, so every bounded task fetches again. That is the case the bound does not reach and this would.

So the honest framing is that this is the fix for the production half that `cache-the-apt-index-within-a-converge` explicitly did not deliver, rather than a further trim of the continuous-integration half it did.

## 5. report refused removals in the host prune

`prune-host-images` reports `considered N, removed M`, where `considered` is every distinct image identity on the host rather than a candidate set. A shortfall between the two therefore carries no signal: a defective keep set prints `considered N, removed 0`, byte-identical to a healthy run over a host where everything is referenced.

`app-deploy`'s own reclamation comment calls that shortfall "a signal worth reading". Here it is unreadable. Counting refusals and reporting them would make a defective keep set legible without changing any removal behaviour.

Recorded rather than folded into `prune-unreferenced-host-images-periodically` because it adds a field to a report the delta specifies exactly, and that is a specification change, not an implementation detail.

## 6. size-platform-container-resource-limits

**Blocked on data, not on another change.** No service in `platform/docker-compose.yml` declares a memory or CPU limit, on a `cx33`, while `ContainerRestartingOrOOMKilled` alerts on the consequence. A single container can currently starve the host.

Limits picked without evidence are guesses that cause the outage they were meant to prevent. The monitoring stack now collects exactly the data needed — `container_memory_usage_bytes` by container, already on the "Container health" dashboard. Let it run long enough to show real steady-state and peak, then size from observation.

## 7. alert-on-swap-utilisation

**Not blocked; recorded rather than folded into `bound-host-log-growth-and-add-swap`, which is the change that gives this host swap in the first place.** That change is host-level Ansible; this one is a `platform/` Compose change reached by a different pipeline, and folding it in would have made a single change need two deploys.

Once swap exists, "swap is 80% consumed" is the signal that a leak is underway and the OOM killer is next. Nothing says it. `node_memory_SwapFree_bytes` and `node_memory_SwapTotal_bytes` are already scraped -- node-exporter has been running since `add-platform-monitoring` -- so the rule is a few lines beside the seven already inline in `platform/docker-compose.yml`.

**What this adds is the explanation, not the detection.** `HostMemoryPressure` is computed from `MemAvailable / MemTotal`, which is RAM only and unaffected by swap existing, so a leak still drives it over 90% and still fires after ten minutes. What that alert cannot say is *why*, and on a host that now has a last-resort tier the difference between "memory is tight" and "the reserve is being consumed and there is nothing after it" is the difference between a warning and a countdown.

Worth deciding at the same time whether the threshold is a level (swap above some fraction) or a rate (swap consumed per unit time). A level fires late on a slow leak and a rate fires spuriously on a legitimate burst; this host has no history of either yet, which is a reason to pick the simpler one and revisit.

**Do not size it before entry 6.** Container memory limits change what swap is ever asked to absorb, so a threshold chosen now describes a host that is about to change.

## 9. aggregate-container-logs

**Not blocked; lowest priority in this batch for a host running one application, and the first thing missed when it runs several.**

Logs are read by `docker logs` over SSH as `ops-claude`, per container, and are lost when a container is recreated -- which every deploy does. Alerts say *that* a container restarted; the reason is in the log that just went away.

Loki with an Alloy (or Promtail) collector reading the Docker socket is the stack-native answer: it joins `platform_monitoring`, Grafana already has the datasource provisioning pattern, retention is bounded the way Prometheus's is, and it stores on `main-data` under a `platform_data_volume_subdirs` entry the way Prometheus does. Its prerequisite in spirit is already delivered: `bound-host-log-growth-and-add-swap` bounded those json-file logs at the daemon, and the collector reads the same ones. Traefik's access log was turned on to stdout on 2026-09-13 alongside the entrypoint-wide TLS defaults, so the HTTP traffic this would aggregate is now being written — and is now what shortens Traefik's own `docker logs` history, which is the argument for doing this rather than a detail of it.

## 10. upgrade-the-shared-postgres-major

**Not blocked; recorded rather than opened because it needs a maintenance window and a deliberate volume reset, neither of which a version-bump pull request can carry.** Recorded 2026-09-08, when Dependabot proposed it and the proposal was closed.

`platform/docker-compose.yml` pins `postgres:16.15`. Dependabot's first run after `cover-platform-images-with-dependabot` landed proposed **18.6** (PR #91, closed unmerged). Taking that proposal as an ordinary bump does not work, and the reason is worth writing down once:

PostgreSQL refuses to start against a `PGDATA` initialised by an earlier major version. It does not upgrade in place and it does not damage the directory -- it exits. So a merged bump reaches the host, `docker compose up -d --wait` blocks and then fails, the deploy job goes red, and the shared instance is down for every application on the host until someone intervenes. Loud, and not data loss.

**What makes this cheap here, and why it is still not automatic.** The shared instance holds no durable data: *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) classifies `postgres_data` as non-durable by policy, and *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) admits no durable data into it at all. So the upgrade path is legitimately "stop the stack, discard the volume, redeploy, let the instance re-initialise" rather than a `pg_upgrade` or a dump-and-restore. That is a decision an operator takes in a chosen window, with the applications that use the instance told first -- not something that happens because a bot opened a pull request on a Tuesday.

Note the divergence this does **not** cover: on the production host, `commerce-ops` runs its own PostgreSQL container with durable data in it (entry 19). Nothing here touches that one, and this entry must not be read as a template for it -- discarding *that* volume loses data.

**No `ignore` stanza was added, deliberately.** `cover-platform-images-with-dependabot`'s design.md Decision 3 argued this: an `ignore` is permanent and silent, and would suppress the only signal this repository gets that its PostgreSQL major has reached end of life. Closing an individual pull request keeps the signal -- Dependabot will propose the next major release when one appears, and closing it again costs nothing. Expect a recurring, correctly-refused pull request; that is the design working, not noise.

**Do first**: check whether any application is by then storing something in the shared instance that it would rather not lose, in which case the answer is that it should not have been (see the requirements above) and that is the thing to fix, not the upgrade.

**And re-provision after it.** Discarding the volume discards every application database in the instance, which each application's classification tolerates and none can start without: before redeploying each, run the provisioning recipe in `docs/onboard-an-application.md` for that host with `rotate=yes`. Since 2026-09-13 `commerce-ops` has such a database on the staging host, and production's is reserved for its cutover. **Once `classify-commerce-ops-production-data-for-the-shared-instance` lands and production's data moves in, discarding production's volume deletes that application's production data for good** — tolerated by that classification, but tell the operator before the window, not after.

## 11. remove-the-stale-test-hostname

**Not blocked; small, and recorded rather than folded into `alert-on-certificate-expiry`, which found it while reading Traefik's certificate metrics on 2026-09-09.**

`test.shatynska.com` was a throwaway smoke test. The archived change `fix-traefik-docker-api-version` used a `whoami` container behind that hostname in August 2026 to confirm Traefik's Docker provider had stopped erroring, and its `tasks.md` records the confirmation. The container is long gone -- the name returns Traefik's 404 -- but two things it left behind are still live:

- the `A` record, `2.29.14.98`, which resolves today and was missing from the recorded zone table until that table was corrected (it is now in `docs/bootstrap-a-new-host.md` §4.4);
- a Let's Encrypt certificate, which Traefik still holds and **still renews every 60 days**, and which appears in `traefik_tls_certs_not_after` alongside the real one.

Nothing is broken by it. It is a standing request to a public certificate authority for a name nothing serves, and a second series in a metric that now drives an alert -- so if that renewal ever fails, the alert correctly reports a hostname nobody wants, at which point the operator has to remember what `test` was before deciding it does not matter.

**Order matters when removing it.** Take the DNS record away first, then the certificate from Traefik's `acme.json`. The reverse leaves a name resolving to the host whose certificate has already gone, which is a worse state than the one being cleaned up. There is no router to remove -- the container that had one is already gone -- so this is a DNS edit plus an `acme.json` edit, and the second requires deciding whether editing that file by hand is acceptable at all or whether the entry is better closed by leaving the certificate to lapse once the record is gone.

## 12. verify-at-deploy-time-that-what-shipped-is-what-runs

**Not blocked; recorded rather than folded into `apply-shipped-config-on-deploy`, which deliberately stops short of it.**

That change makes a configuration-only edit *visible* to Compose, so the services whose configuration moved are replaced. What it does not do — and its added requirement says so in as many words — is establish that a deploy reporting success applied everything it shipped. A container can fail to be replaced for reasons no property of the stack definition can express, and nothing today compares a running container against the definition afterwards.

The check is small: after `docker compose up -d --wait`, compare each running container's `com.docker.compose.config-hash` against `docker compose config --hash='*'` and fail the deploy on a mismatch. It would have caught the original defect on the day it happened rather than a day later, and it catches the whole class rather than the one member of it that a checksum label addresses.

**It does not subsume the label, and adding it instead would have been wrong.** Without a label, a configuration-only change produces equal hashes on both sides — the file's and the container's — so this check passes while the configuration sits unapplied. It is a backstop for reasons nobody has thought of, not a replacement for making the change visible in the first place.

Two things make it a change of its own rather than a rider. It edits `app-deploy`, which is generic across applications, so it changes deploy behaviour for `commerce-ops` and every future application, not just for `platform`. And it needs a decision about what a mismatch should do to a deploy that has already replaced some services and reported them healthy — failing after the fact is not the same as refusing to start.

Note the comparison has a trap the sibling change documented: four of the platform stack's eight services -- `grafana`, `postgres`, `postgres-exporter` and `traefik` -- interpolate `${...}` from `.env` into their service blocks, so a hash computed anywhere without the host's real `.env` does not match the host's. This check must run **on the host**, where that file is, or it will report mismatches that are artefacts of where it ran.

It also does **not** catch the second case below, despite looking as though it should: where a secret interpolated *inside* an embedded config is rotated, both sides of this comparison compute the same unchanged value, so it passes while the running container holds the superseded secret.

**The second half of this entry, and the reason the two are one change.** A configuration change that a deploy reports as applied has two ways of not being applied, and only one decision settles both — whether the digest is computed on the host, after interpolation. What follows was found in code review of `apply-shipped-config-on-deploy`, which is structurally unable to close it.

`alertmanager_config`'s content interpolates `${SLACK_WEBHOOK_URL}` and `${DEADMANSWITCH_URL}`, and `.github/workflows/platform-deploy.yml` renders both into `.env` from GitHub secrets at deploy time. Rotate the Slack webhook and the effective Alertmanager configuration changes -- but the committed text does not, so the checksum label derived from it does not, and Compose's own digest never covered embedded config content in the first place. The container is not replaced. **The revoked webhook stays live until something unrelated replaces that container**, and every alert in the meantime goes to an endpoint the rotation was meant to retire.

Nothing currently reports this. The deploy-time hash comparison above does not: both sides compute the same unchanged value, so it passes. The checksum label cannot: the value that changed is deliberately not in the repository, which is the whole point of it being a secret.

**What would work is the deploy-time computation that change considered and rejected** -- a digest taken on the host, after interpolation, moves when the interpolated value moves. That change's design.md records this as the strongest argument against its own Decision 1, found after the decision was made. Deciding this entry means revisiting that trade with this case in hand, so it is a decision about the mechanism rather than a defect to patch.

Bounded in the meantime by how rotation actually happens here: it is a manual act by the operator, who can force the replacement in the same session. Worth writing that into the rotation step of whatever runbook covers it, which is a smaller piece of work than this entry and does not wait on it.

## 13. name-every-alert-in-a-grouped-slack-notification

**Not blocked; recorded rather than folded into `alert-on-certificate-expiry`, which routed around it for its own alert and found the general case in doing so.**

Alertmanager's `slack` receiver renders `{{ .CommonAnnotations.summary }}` and `{{ .CommonAnnotations.description }}`. `CommonAnnotations` holds only the annotation pairs **identical across every alert in the notification's group** -- so any alert whose annotations name a per-series label delivers an empty title and an empty body the moment two of them group together.

`ApplicationHighErrorRate` is in exactly that state and has been since it was written: its summary names the router, `group_by` is `["alertname"]`, and two routers erroring at once -- which a shared Traefik makes correlated rather than independent -- produce a Slack message that says nothing. Nobody has seen it because the alert has not fired on two routers yet.

`alert-on-certificate-expiry` fixed this for its own alert by adding `cn` to `group_by` on that alert's own route, which is correct and minimal for one alert. It does not generalise: every future alert naming a per-series label needs the same treatment, and forgetting is silent.

The general fix is in the receiver, not in a route: render `{{ range .Alerts }}` so a grouped notification lists each alert's own annotations. That changes delivery for **every** alert in the stack, including ones nobody has re-read, which is why it is a change of its own rather than a fold-in. Worth pairing with an assertion that no alert's annotations reference a label absent from its route's `group_by`, which is a static read of the committed file and would catch the next instance instead of waiting for it to fire.

## 14. check-public-endpoints-from-outside

**Not blocked; recorded because the monitoring stack watches the host and not the customer's path to it. Narrowed on 2026-09-09 by `alert-on-certificate-expiry`, which delivered the certificate-expiry half.**

The dead-man's switch proves Alertmanager is alive. `MetricsTargetDown` proves the exporters are. `ApplicationHighErrorRate` needs requests to reach Traefik before it can count them. Nothing checks, from outside the host, that a public hostname resolves and answers on 443.

**What was delivered and is no longer in scope here.** A certificate quietly ageing out was the third of the three failures this entry named, and it turned out to need no probe at all: Traefik publishes `traefik_tls_certs_not_after`, Prometheus was already scraping it, and one alert rule now reads it. What survives of that failure is only the half no metric can express -- a hostname resolving to this host with **no** certificate at all, which produces no series because Traefik's default self-signed certificate is not published as one. `shatynska.com` and `www.shatynska.com` are in exactly that state today, by design, because no application is bound to them yet.

**`blackbox-exporter` cannot serve this entry's own motive**, which is the finding that most changes what remains. It runs on the host, and a packet addressed to an IP configured on a local interface is delivered locally -- so a probe from the host to the host's own public address never traverses the Hetzner cloud firewall, which filters ingress at the network edge. The cheaper of the two shapes this entry offered cannot see the firewall failure it was offered for. It would still catch a routing mistake and would measure what a client is actually served rather than what Traefik believes it holds; neither is the same thing as looking from outside.

**The two failures that remain, stated more accurately than this entry stated them.**

*A cloud-firewall change blocking 443* is gated in two of at least three ways it can close, not in all of them. `web_allowed_cidrs` reaches production only through the gated pipeline, where a human reviews the exact plan, and `AGENTS.md`'s firewall split makes UFW the co-equal host-level layer — whose playbook now reaches a host through the gated converge `apply-host-configuration-through-a-gated-workflow` built, so that layer is gated too. The third is a console-side change, caught only by the drift workflow. That workflow no longer fails into silence — `notice-when-a-periodic-job-stops-reporting` gave it a heartbeat whose quiet raises an alarm — but it still reports only what Terraform manages. An outside check is the only thing that would see it.

*A DNS mistake* is not bounded by how often the zone is hand-edited. `docs/bootstrap-a-new-host.md` §4.4 records that `shatynska.com` is served by third-party nameservers at ukraine.com.ua, so a provider outage or a lapsed registration is a DNS failure with no edit behind it -- and it is exactly the "invisible until a person notices" class this entry was recorded for.

**So what is left is an external uptime service**, with a check per hostname, independent of the host in the way the Watchdog is. Note that the assumption this entry made about it is probably false: the heartbeat provider named in `docs/bootstrap-a-new-host.md` is healthchecks.io, which monitors inbound pings and does not make outbound HTTP checks. This is likely a second vendor account and therefore an operator decision with a cost attached, which is the main reason it is still queued rather than opened.

## 15. reconcile-the-heartbeat-checks-with-what-the-repository-prescribes

**Not blocked. Recorded 2026-09-13 by `correct-the-documents-against-the-tree`, whose own operator step went looking for a check the observer does not hold.**

`docs/bootstrap-a-new-host.md` §7.1 tells the operator to create a check for Alertmanager's dead-man's switch under a name of the document's choosing. **No check has ever carried that name.** The observer holds *Alertmanager Dead Man's Switch* under the slug `my-first-check` — the vendor's own default first-check name, which is what you get by pinging a project's first check into existence rather than by naming one. The document prescribed, the deployment did something else, and **nothing in this repository can see the difference**, because no committed file names that check: Alertmanager posts to a full ping URL held in `PLATFORM_DEADMANSWITCH_URL`, and a URL carries no slug.

**The two kinds of check differ in exactly the way that decides what may be renamed, and that is worth stating once rather than rediscovering.**

- **Slug-addressed, and a rename of the slug breaks them.** `infrastructure-drift`, `infrastructure-pre-commit-autoupdate` and `<inventory_hostname>-prune-host-images` are reached as `hc-ping.com/<ping key>/<slug>?create=1` — by `.github/workflows/drift.yml`, `.github/workflows/pre-commit-autoupdate.yml` and the `image_prune` role. Because every ping carries `?create=1`, re-slugging one does not fail loudly: the next ping **creates a second check** under the old slug and the renamed one goes quiet, which is an alarm rather than an error and arrives a period later. The display name is free; the slug is not.
- **URL-addressed, and a rename costs nothing.** The Alertmanager check is reached only by its own ping URL, so its name and its slug may both be changed without touching a secret. That is the one this repository prescribes a name for and the one where the name is least load-bearing.

**What this entry owes.** Decide whether the Alertmanager check is renamed to match §7.1 or §7.1 is amended to match the observer — either is defensible and the divergence is not — and say in the document which field is being named, since the two kinds of check answer differently. Then state the slug rule where an operator meets it rather than here: a reader of §7.1 and Appendix A today cannot tell that renaming one check is free and renaming another quietly doubles it.

**What it must not do.** Re-slug a periodic-job check to tidy the list. `main-production-prune-host-images` and `main-staging-prune-host-images` are templated from `inventory_hostname`, so their slugs are derived rather than chosen, and changing one at the observer alone puts it permanently out of step with what the host pings.

**The same blind spot on a different field of the same check, and the cheaper half.** The observer holds settings no committed file states, so nothing detects either kind of divergence. The name is above; the timing is below, recorded 2026-09-13 by the operator, who read §7.1 against the observer's own settings and could not make the two agree.

`docs/bootstrap-a-new-host.md` §7.1 says of the Alertmanager dead-man's-switch check: *"Period **5 minutes**, grace **5 minutes**: Alertmanager pings it every 2 minutes, and the service must expect pings at least that often but tolerate one missed one."* The deployment runs **period 5, grace 2**.

**The sentence is why the divergence is hard to see, and it is wrong in a way that survives a careful reading.** The clause after the colon justifies the **period** and nothing else: a period of 5 minutes against a 2-minute cadence is exactly "tolerate one missed ping before going late". The **grace** value is then stated with no reason attached, so a reader who does the arithmetic finds a number that the sentence appears to explain and does not. That is how it reads as a contradiction when it is really an unexplained figure sitting beside an explained one.

**What the two fields actually do, since the document never says.** They are sequential, not alternatives. *Period* is how long without a ping before the check goes **late**; *grace* is how long it stays late before going **down** and alerting. Time from the last good ping to the alarm is **period + grace**. Against the real cadence — `repeat_interval: 2m` on the `Watchdog` route in `platform/docker-compose.yml` — the documented pair alarms at **10 minutes** and roughly five missed pings; the deployed pair alarms at **7 minutes** and roughly three.

**The deployed value is the better one, which is what makes this a documentation change rather than a configuration one.** This check is the alarm for when everything else is down, so a shorter time to alarm is worth having provided it does not fire on noise — and three consecutive missed pings is well clear of a transient blip or of the brief Alertmanager restart a platform deploy causes. Whoever takes this should change the document to match the observer rather than the reverse, and say *why* the grace is what it is instead of asserting a figure.

**Two things to fix while in there.** Give the arithmetic — `period + grace` is the time to alarm — because no reader can size either field without it. And state which of the two numbers the "tolerate one missed one" reasoning belongs to, since attaching it to the pair is what produced this entry.

## 19. move-commerce-ops-durable-data-to-supabase

**Not blocked, and its middle step is not this repository's to do — recorded because `openspec/specs/iac-safety-hardening/spec.md` names it as a divergence and nothing else tracks it.**

*No Store on This Host Holds Data Requiring Backup* classifies every store on this host as needing no backup, and states one exception: on the production host, `commerce-ops` keeps durable data in a PostgreSQL container of its own, on its own `app_db` network — staging's `commerce-ops` has none, its database being in staging's shared instance. On 2026-09-08 production's private database held 12 MB. Most of its rows are transient — roughly 17,000 across the `procrastinate_*` queue tables, which are exactly the non-durable class the shared instance exists for — but the part that matters is small and hand-curated: 358 `playbook_steps`, 35 `launch_journal_entries`, 26 `launch_clickup_tasks`, 11 `roles`, 8 `role_holders`, 7 `known_work`, 5 `products`. Nothing backs any of it up. The daily Hetzner snapshot covers the root disk the volume sits on, crash-consistently, restorable only by rolling the whole server back.

The resolution, as the operator decided on 2026-09-14, comes in two stages (`provision-commerce-ops-database-in-the-shared-instance`'s design, decision 3). First, production's whole `commerce-ops` database — the hand-curated tables and the `procrastinate_*` queue tables alike, since the application enqueues inside its domain transaction and its queue cannot live in a second database — moves into the database already provisioned for it in production's shared instance, once its data is classified as tolerable to lose. Later it moves to Supabase, which owns its own backups. Staging is the other case: its whole database is already in staging's shared instance under the rehearsal-data policy.

**Ending the private container takes four steps, and this repository owns three.**

1. Done by that change: a `commerce-ops` role and database in production's shared instance, their password in the `commerce-ops` repository's `production` Environment as `SHARED_POSTGRES_PASSWORD` — deliberately not `POSTGRES_PASSWORD`, which the private PostgreSQL still reads.
2. Here: `classify-commerce-ops-production-data-for-the-shared-instance`. Nothing from production may land in the shared instance before it merges.
3. In the `commerce-ops` repository, over which this one has no authority: move the whole database into production's shared-instance database — a dump of `commerce-ops-postgres-1` restored as role `commerce-ops` — point `DATABASE_URL` at `commerce-ops@postgres:5432/commerce-ops` with `SHARED_POSTGRES_PASSWORD`, and remove its own PostgreSQL service, its volume and its `app_db` network. While both exist, `postgres` names two servers to a container on `app_db` and `platform_edge` at once, so the switch and the service's removal belong in one deploy. Until that service is gone, the divergence stands.
4. Here: delete the divergence paragraph from *No Store on This Host Holds Data Requiring Backup*. No change in this repository would otherwise prompt it, so a completed migration would quietly leave the specification describing a divergence that no longer exists. **Gate it on the host, not on the migration being reported done**: from a session on production, `docker ps --filter name=commerce-ops` shows no PostgreSQL container and `docker volume ls` no longer lists `commerce-ops_commerce_ops_pgdata`. A specification calling the divergence closed while that container runs is worse than one admitting it.

**The later move to Supabase**, recorded so it is not re-derived: use its session pooler — `aws-1-eu-west-1.pooler.supabase.com:5432` with user `postgres.<ref>`, which answered `pg_isready` from a container on staging's `platform_edge` on 2026-09-14. Supabase's direct connection is IPv6-only and `platform_edge` has IPv6 disabled, the transaction pooler on port 6543 cannot carry the worker's `LISTEN/NOTIFY`, and the Free plan has no backups.

## 20. write-and-rehearse-the-rebuild-runbook

**Not blocked; recorded because every piece exists and nobody has run them in sequence.**

Recovering this host from nothing is: a Terraform apply through the gated pipeline (with `server_enabled` toggled, and the destroy-override label for the replace), DNS (a manual edit at ukraine.com.ua — the records are listed in `docs/bootstrap-a-new-host.md` §4.4, which is also where the automation of this step is declined), the first converge of the rebuilt host, which is a hand-run one from a workstation with the Vault password and a fresh tailnet key -- the pipeline reaches a host over the tailnet and joining it is what that play does, so `apply-host-configuration-through-a-gated-workflow` did not remove this step and could not, the platform deploy from a re-run of `platform-deploy.yml`, one deploy per application from its own repository, the two manual steps `platform/README.md` lists (the `pgexporter` role and the dead-man's-switch registration). No *platform-stack* store needs restoring: `scope-the-shared-database-to-non-durable-data` classified each of them as needing no backup — each is either recreated by a redeploy or its loss is accepted, and the runbook should say which, because Prometheus's history and Grafana's UI-created state fall in the second group and do not come back. An application's database in the shared instance falls in the second group too, but is not the end of it: the application cannot start without one, so the runbook needs a re-provisioning step per application — the provisioning recipe in `docs/onboard-an-application.md` for that host with `rotate=yes` — before that application's deploy. That leaves one gap, and it is the one the same change names as a divergence — on the production host, `commerce-ops` keeps durable data in a PostgreSQL container of its own that nothing backs up, so a rebuild today loses it. Entry 19 is what closes that; until it does, the runbook has to say so. Those steps live in four repositories and two README sections, in no stated order, and the time they take is unknown.

A `docs/runbook-rebuild.md` that lists them in order, names the secret each step needs, and records the last rehearsal's date and duration is the deliverable. The rehearsal is the point; the document is how it survives. Staging is where the rehearsal can happen without touching prod — converged since 2026-09-10, though entry 16 is what puts a platform stack on it to rehearse against.

## 21. exercise-the-volume-server-coupling-against-live-state

**Not blocked; recorded because an archived change is where it would be lost.** Recovered 2026-09-08 by `make-openspec-validation-a-usable-gate` while settling the red archived records. `add-prod-data-volume`'s task 3.5 was left unticked with the note *"Still open; consider doing this as a follow-up plan-only check"* — real outstanding work, sitting in prose inside a change that had already been archived, which is precisely where nobody would look for it. That task is now disclosed under that change's `## Not performed`; the work it names is here.

`stacks/prod` couples the volume to the server: `count = var.volume_enabled && var.server_enabled ? 1 : 0`, so the volume cannot outlive the server it derives its location from. **That coupling has never been exercised against live state.** `terraform/modules/volume/tests/*.tftest.hcl` cannot reach it — the coupling lives in the stack, not the module, and the module's tests do not evaluate the stack's `count` expression.

Two plan-only reads, **never applied**:

- Set `volume_enabled = false` (uncommitted) and re-plan: the volume is planned for destruction and nothing else changes.
- Restore it, set `server_enabled = false` instead, and re-plan: the plan destroys server, firewall **and** volume together.

Revert both local edits afterwards. Use the read-only Hetzner token; this is a `terraform plan` and never a `terraform apply`, per this project's rule that production changes reach Hetzner only through the gated pipeline. A destroy plan run locally reads state and proposes; it changes nothing.

The requirement this protects is *Conditional Prod Volume Creation* in `openspec/specs/iac-data-volumes/spec.md`, and the two reads above are literally its scenarios *Volume toggle disabled creates nothing* and *Disabling the server also removes the volume* — both of which say `terraform plan` SHALL show the volume planned for destruction. The specification states them; nothing has ever run them.

Worth doing before the coupling is next relied on — a volume that survived its server would be an orphaned resource with no location, which is the failure the coupling exists to prevent and which nothing has yet observed being prevented.

## 22. narrow-the-converge-trigger-to-what-a-converge-reads

**Not blocked. Recorded 2026-09-12, from the merge of `rename-terraform-environments-to-stacks` (PR #148).**

`host-converge.yml` triggers on any merge to `main` touching `ansible/`, with no filter on *what* under `ansible/` changed. That merge's entire `ansible/` diff was **eleven lines, every one a comment** — citation paths in two role READMEs, a role's `tasks/main.yml`, a Molecule `prepare.yml`, the two inventory sources, both `group_vars` files and `.envrc.example`. It converged production and staging: run `34669351690`, nine minutes against prod, `changed=0` on both hosts.

Idempotency is what made that harmless, and "we rely on idempotency" is a weaker guarantee than "it does not run". A converge changes the host firewall, the accounts that may log in and the container runtime; a comment fix should not reach a production host to discover it has nothing to do.

**The asymmetry that makes this visible.** `ansible-verify.yml`'s Molecule trigger was deliberately narrowed by `narrow-the-molecule-trigger-to-what-it-reads` and now excludes `ansible/inventory/**`, the playbooks, the converge workflow's own `requirements.txt` and `.envrc*`. Those exclusions are exactly why the same merge ran 2 Molecule roles of 7. The converge trigger never got the same treatment, and it has the larger blast radius of the two.

**Why this is NOT a copy of that change, and the reason is the whole difficulty.** The two triggers read different sets, and the exclusion lists are close to inverses:

- Molecule may exclude `ansible/inventory/**` because no scenario reads it. A **converge** reads the inventory source and the `group_vars` for its stack — they are its inputs, not its scaffolding. Excluding them would be a defect.
- Molecule may exclude the playbooks because scenarios have their own converge playbooks. A converge runs `playbooks/host-baseline.yml` itself.
- Both may exclude `ansible/.envrc*`, a document and a gitignored operator file.

So the safe exclusion set is roughly: documentation (`**/README.md`), `.envrc*`, and Molecule's own scenario directories — which a converge never reads. The role `tasks/`, `defaults/`, `handlers/`, `templates/` and `meta/`, the playbooks, the inventory and the `group_vars` all stay.

**The failure mode to design against, and it is the expensive one.** Getting the Molecule filter wrong under-runs a test suite, which is loud on the next real change. Getting this one wrong means **a host silently not converging when it should** — the merge reports green, the host keeps its old firewall or its old container runtime, and nothing says so. That asymmetry argues for a conservative exclusion list and for the same `some-with-excludes` quantifier discipline `ansible-verify.yml` already documents, plus a `.github/tests` assertion that every path a converge actually reads is **not** excluded.

**A second instance, 2026-09-13, and it is the one this entry was written for.** The merge of `namespace-the-molecule-loop-devices` (PR #161) triggered run `34716999142`. Its entire `ansible/` diff was `ansible/roles/platform_data_volume/molecule/**` and `ansible/scripts/run-molecule` — **exactly the exclusion set this entry proposes**, Molecule's own scenario directories plus the entry point that runs them, and nothing else. Both hosts reported `changed=0`: 87 tasks on production, 85 on staging.

The cost was not the wall clock. Production's job sat **6h34m** waiting for its Environment approval, because the change's own author had told the operator the merge would start no converge and nobody was watching for one. A test-fixture change held a production approval open overnight to discover it had nothing to do. That is the concrete form of "a comment fix should not reach a production host", and it is now twice.

**Weigh it against the alternative of doing nothing.** The cost today is wall-clock and a standing risk that a documentation change perturbs production. The benefit of the current coarse trigger is that it cannot under-converge. That is a real benefit and this entry should not be taken as a foregone conclusion — a reviewer may decide the coarse trigger is the right answer for the host layer precisely because the failure mode is silent.

## 23. make-the-converge-survive-a-galaxy-outage

**Not blocked. Recorded 2026-09-12, from the merge of `rename-the-external-services` (PR #155), whose gated production converge failed on it.**

`host-converge.yml`'s *Install Galaxy content* step runs two commands with no retry, no vendoring and no fallback:

    ansible-galaxy collection install -r requirements.yml
    ansible-galaxy role install -r requirements.yml -p roles

On that merge the first of them failed against `galaxy.ansible.com`, resolving `community.library_inventory_filtering_v1`:

    [WARNING]: Skipping Galaxy server https://galaxy.ansible.com/api/. Got an unexpected
    error when getting available versions of collection
    community.library_inventory_filtering_v1: Missing expected 'results' in
    ansible-galaxy cache ...

**It is transient and upstream, and the evidence is that its neighbours passed.** Three converges performed the identical install within twenty minutes: staging's at 10:00:02 and the previous run's production converge at 10:08:43 both succeeded; only the 10:17:54 one failed. The error's own suggestion — concurrent `ansible-galaxy` runs — does not apply here: the concurrency group had serialised the two production converges (10:08:43–10:16:00, then 10:17:54), each job runs on a fresh ephemeral runner, and the workflow carries no `actions/cache` step, so the cache it complained about was written seconds earlier in that same job.

**Why it is worth fixing rather than re-running.** The failure lands on the **gated production** path, so the cost is not a red run but an approval spent on nothing: the operator grants the production Environment, the job dies before Ansible reads the inventory, and the whole approval has to be requested and granted again. A converge is also the one workflow whose failure can leave a host unconverged while everything else reports green.

**What it must not become.** A blind retry loop around an installer that is also this repository's version-pinning mechanism would hide a genuine pin failure — `ansible/requirements.yml` pins exact versions, per `AGENTS.md`, and a resolution error that means *the pinned version is gone* must stay loud. So the change owes a distinction between "could not reach the server" and "the server says this version does not exist", and only the first is retryable.

**Options, in rough order of cost.** A bounded retry with backoff on the install step. `--no-cache` or `--clear-response-cache`, which the error message itself suggests and which costs a slower install. Caching the resolved collections between runs, which trades an upstream dependency for a cache-invalidation problem and interacts with the pinning rule. Or vendoring the collections into the repository, which removes the run-time dependency entirely and is the largest change of the four.

**Twice now, and the second instance widens the entry beyond the converge.** On 2026-09-12 the same step failed on a **pull request**, in `ansible-verify.yml`'s Molecule matrix rather than in `host-converge.yml` — PR #161, run 34715212029, job 103611145944, 45 seconds in:

    [ERROR]: Unknown error when attempting to call Galaxy at
    'https://galaxy.ansible.com/api/v3/collections/hetzner/hcloud/versions/7.0.0/':
    <urlopen error [Errno 104] Connection reset by peer>

A different collection, a different error and a different workflow, so a fix aimed only at the cache-shaped message above would not have caught it. The install is verbatim the same two commands, and both workflows run them unguarded. **The neighbours passed again**: seven other Molecule roles in that same matrix ran the identical install and every one succeeded, which is the same evidence of transience the production instance gave. Re-running the failed job alone turned it green with no other change.

The cost here is lower than on the converge — a red check and a re-run, not a spent production approval — but it broadens the subject: whatever the fix is, it belongs to **every** workflow that installs Galaxy content, not to `host-converge.yml` alone. Weigh the options above against how often this happens: twice in one day, on two different workflows, against two different collections.

## 24. detect-host-drift-on-a-schedule

**Not blocked, and deliberately not done by `apply-host-configuration-through-a-gated-workflow`**, which is the change that made it possible and the one that declined it. That change's own `design.md` Decision 10 carries the full reasoning; what follows is what this entry inherits.

A converge applies what is committed. Nothing reports what a host has drifted to between converges, and the host layer is the only one of the three without that: `drift.yml` sweeps Terraform nightly, and the platform stack is redeployed wholesale on every merge. `--check --diff` against a live host is the host layer's `drift.yml` -- not its `terraform plan`, and the distinction is why it could not be folded into the converge workflow. A pre-approval job must hold no credential capable of reaching a host, and a check-mode run has to authenticate.

**It cannot ship with the baseline it has today.** Two `tailscale` tasks -- *Add the Tailscale apt signing key* and *Add the Tailscale apt repository* -- are `ansible.builtin.get_url` with no `checksum:`, and `get_url` to an existing destination with no checksum reports **changed** under `--check`, because establishing that the file already matches would mean downloading it. So a healthy host reports `changed=2`, forever. A drift detector whose baseline is two is one an operator learns to skip, which is the same failure mode as an approval prompt with nothing to approve. Three remedies, none free: pin a `checksum:` (upstream rotates the key), replace `get_url` with a task that can verify itself in check mode, or filter those two by name and say in the workflow why.

**Entry 3 is a prerequisite rather than a neighbour.** The `tailscale` role carries no Molecule scenario, so any of those remedies would be made against nothing. Entry 3 already owns bringing that role its first scenario.

**Two documents move with it.** `docs/bootstrap-a-new-host.md` §6.3 states the `changed=2` baseline and names this entry as owning its removal -- that paragraph is written to change when this lands. And what check mode can see is less than the host: `command` tasks skip under `--check` (`ops_user`'s three, `swap`'s four) and `geerlingguy.docker` carries `ignore_errors: "{{ ansible_check_mode }}"` on five, so a clean check is a statement about files and packages and not about the host. Whatever this ships must say so where it reports, not only in a design document.

Shape it as `drift.yml`'s sibling: scheduled, per environment, an issue per environment deduplicated by title, and a liveness report -- the last is obligatory, since *Scheduled Workflows Report Their Own Liveness* reaches every `schedule:`-triggered workflow.

## 25. say-what-a-stale-saved-plan-is-and-how-to-recover-from-it

**Not blocked. Recorded 2026-09-12, from the same merge.**

`apply (prod)` failed with Terraform's raw error:

    Error: Saved plan is stale
    The given plan file can no longer be applied because the state was changed
    by another operation after the plan was created.

That is the gate working — *Gated Production Apply Applies the Reviewed Plan* obliges applying the **exact** plan a human reviewed, and Terraform refused a plan that no longer matched state. What is missing is that `apply.yml` says nothing about it. The job already fails cleanly for the neighbouring case — a missing or expired plan artifact gets a named `::error::` and a stated recovery — and a stale plan, which is at least as likely, gets nothing.

**Why it is at least as likely.** Prod's apply waits for a required reviewer, and that wait is the window. On this run the plan was saved at 03:04:16 and the apply began at 03:18:51; staging, which requires no reviewer, applied 12 seconds after its plan and succeeded. **The gate that makes production safe is the same thing that makes its saved plan perishable**, and the longer the approval takes the more certain this becomes.

**What the evidence showed**, recorded because the diagnosis took an HCP state-version query that the next person should not have to repeat. Prod's state serial moved 44 → 45 at 03:18:20, thirty-one seconds before the apply job started, and the two versions are **identical in every resource attribute** — same lineage, same four resources, no value changed. Nothing about the infrastructure moved; only the serial. Staging's serial 3 was written at 03:04:38 by its own no-op apply, which is the same signature, so a Terraform operation that changes nothing still bumps the serial and still invalidates a saved plan made against the previous one.

**What the change owes:**

- A named failure for this case, distinguishing it from the artifact case: what a stale plan means, that no infrastructure change was lost, and that the recovery is a **fresh run of the whole workflow** rather than re-running the failed job, which re-downloads the same stale artifact and fails identically.
- A decision on whether the message should name the likely causes. A local `terraform plan` or `apply` against the stack during the approval window is one; this repository permits the former and forbids the latter, and if a permitted local `plan` can invalidate a pending production apply then that is a hole in the workflow's own rules and belongs in `AGENTS.md` rather than only in an error message. **A local plan is now measured not to do it**: `rename-the-external-services` ran `terraform init && terraform plan` under each stack's read-only token on 2026-09-12 and both workspaces' state serials and current-state-version timestamps were unchanged afterwards — production 46, staging 4, each still carrying the version written by that morning's apply. That closes the candidate this bullet was most worried about and leaves the hole it feared unopened; what wrote serial 45 is still unidentified.

**What wrote serial 45 was not identified, and the elimination is recorded so it is not repeated.** Not continuous integration: six workflow runs existed that day, none was active at 03:18:20, and the apply was a single attempt whose job was queued at 03:04:22 and started at 03:18:50 on approval. Not the operator's checkout: its `.terraform/` had not been touched for three weeks, and the operator merged and approved and did nothing else. Not the working trees of the change itself, whose every local run used `-backend=false` and so never reached remote state. Not an HCP health assessment: `assessments-enabled` is `false` on that workspace. The remaining avenue is the workspace's own **States** view in the HCP interface, which labels each version with its source — worth a look before this change is designed, because a cause nobody can name is a cause nobody can prevent, and the recovery this entry specifies is correct whether or not the cause is ever found.

**Not in scope here:** auto-replanning on staleness. That would apply a plan no human reviewed, which is the requirement this entry exists to respect.

## 26. make-a-waiting-approval-announce-itself

**Not blocked. Recorded 2026-09-12 by `rename-the-external-services`, which lost three and a half hours to it and recorded the recognition advice without recording the gap.**

**Nothing tells the operator that a gated run is waiting for them.** A production converge raised at 06:26 on 2026-09-12 sat unapproved until 09:56. It was not noticed by anyone watching for it; it was noticed because a *later* merge raised its own converge, which queued behind the first and reported `waiting on converge (main-production) … to complete`. That message reads like a hung job and is a concurrency queue, so the first thing it provokes is a diagnosis of the wrong run.

**Three things compound it, and each is worth designing against separately.**

- **A pending approval is invisible unless you go and look.** `gh run list --status waiting` is the query, and nothing in this repository or in the operator's routine runs it.
- **Approval prompts are indistinguishable.** The Terraform apply, the host converge and the platform deploy all gate on the **same** GitHub Environment and render the same prompt, naming the Environment rather than the work. Three pending requests cannot be told apart without opening each one — which is also the failure mode `docs/bootstrap-a-new-host.md` §6.6 now warns about under "read which *workflow* and which *job* you are approving".
- **A pending approval blocks the stack.** Converges are serialised per stack, so an approval nobody grants stalls every later converge behind it, and the symptom surfaces on the *newer* run.

**Establish what GitHub already sends before building anything.** GitHub raises a *deployment review requested* notification to each required reviewer, and the cheapest possible outcome here is that the notification exists, is not being delivered where the operator reads, and the whole entry is a settings change plus a sentence in §6.6. Measure that first; only if it is genuinely absent or genuinely unreadable does anything get built.

**What could be built, in rough order of cost.** A line in the operator's routine — `gh run list --status waiting` — which costs nothing and is forgotten by construction. A scheduled workflow that queries the same thing and pushes somewhere the operator actually reads. Or reusing the alerting path the platform stack already has, which is where the trap is: `SLACK_WEBHOOK_URL` reaches Alertmanager from `PLATFORM_SLACK_WEBHOOK_URL`, a **production Environment** secret, so a workflow that wants it gates on the very Environment whose pending approval it is trying to announce. A notifier must draw its credential from somewhere ungated, or it cannot fire on the case that matters.

**What it must not become.** A notifier that fires on every run teaches the operator to ignore it, and the run that then goes unapproved is indistinguishable from the noise. The signal is specifically *waiting on a human*, and it is worth a reminder that repeats while the state persists rather than one announcement at the moment the request is raised — the 06:26 request was raised while nobody was reading.

**A related gap, not this entry's to close.** Nothing in this repository bounds how long a request may wait. GitHub is understood to expire a pending deployment review after some weeks and cancel the run — unverified here, and worth measuring against the documentation rather than trusting this sentence. Either way, whether an unapproved converge *should* expire sooner is a separate decision from whether anyone is told about it.

**A second instance, 2026-09-13: 6h34m.** The merge of `namespace-the-molecule-loop-devices` (PR #161) left `converge (main-production)` in run `34716999142` pending approval from 20:24 until 02:58. Nothing announced it. It was found only because the operator mentioned a check still running, and the session then read `gh run list` — which is the failure this entry names: the run is visible to anyone who goes looking, and nothing makes anyone look.

Two things make this instance worse than the first. The approval **should not have been requested at all** — entry 22 above covers why, and this same run is its evidence. And the session that opened the pull request had stated the merge would start no converge, so the operator had been told there was nothing to watch for. A mechanism that announces a waiting approval does not depend on anyone having predicted it correctly, which is the argument for building one rather than relying on the author's summary.

## 27. factor-the-four-stack-discovery-bodies

**Not blocked. Recorded when the fourth one was written.**

`pr-validation.yml`, `apply.yml` and `drift.yml` share one ~160-line stack-discovery body, asserted identical across the three by `.github/tests` -- and that assertion is what makes running one copy evidence about all three. `host-converge.yml` now carries a fourth that is **deliberately not identical**: it enumerates `ansible/inventory/*.hcloud.yml` rather than `terraform/stacks/*/`, and it cross-checks the two sets in both directions, which the Terraform body sees only one side of. So it sits outside that assertion, and the family is no longer covered as a whole.

The existing comment in those three anticipated this: *"Copies are not the only available shape … Edit them together, or factor them out together."* It declined a composite action on two grounds, and one of them has since weakened -- it cost "a fourth file in a diff already restructuring three gated workflows", which is not what this change would be.

**A script under `.github/scripts/` is likely simpler than a composite action**, and for a reason specific to this repository: `.github/tests` currently locates a discovery body **by the `terraform/stacks` path literal the body contains** — not by step name, and `test_environment_agnostic_pipeline.py`'s own docstring records that a name-based locator was tried and was wrong — then executes it against a scratch tree. A script is executed directly, which removes that indirection rather than adding a second one. The shared parts are the flat `key: value` reader, the secret-name validation, the empty-result refusal and the JSON emission; the roots and the cross-checks differ and would stay parameters.

Weigh it against the cost this repository has already paid twice for touching gated workflows: the diff restructures the production apply path, and the identity assertion has to be replaced rather than merely retargeted.

## 28. matrix-the-molecule-suite-over-scenarios-and-bound-each-job

**Not blocked; recorded rather than folded into `promote-molecule-to-a-required-check`**, whose proposal names it as a non-goal. That change decides which job is required and reshapes the workflow's triggers; this one changes what a job *is*. Landing both in one diff would mean the change that picks the registered context also redefines the thing being registered.

`molecule test --all` runs a role's scenarios in sorted order and **stops at the first failure**. Every scenario sorting after a failing one is neither executed nor listed in that run's SCENARIO RECAP, so a red run establishes less than it appears to and the recap still looks complete. Molecule's own remedy is unavailable here: `--continue-on-failure` applies only with `--workers`, and `--workers > 1` refuses with `only supported in collection mode (galaxy.yml required)` — these are plain roles, not a collection (observed 2026-09-07).

Not to be confused with the shared-state hazard, which was a different cause with an overlapping symptom and is now closed: instance names and the ephemeral directory are namespaced per working tree, and `AGENTS.md`'s *Namespacing Molecule per working tree* is the binding. What remains here is Molecule's own stop-at-first-failure behaviour, which namespacing does not touch.

The remedy that works is a continuous-integration matrix over **scenarios** rather than roles. Each scenario becomes its own job, so one failing scenario stops only itself and the rest still report. It also parallelises the suite's longest role, which carries three scenarios and is what sets the workflow's wall clock.

**What promotion changes about its priority, in both directions.** A red required check that under-reports is slower to diagnose — you fix one scenario, push, and wait six minutes to discover the next one. That is an argument for doing this. Against it: the gate is not weaker for under-reporting. A red check blocks the merge whether or not it enumerated every failure, so this is about the cost of diagnosis rather than about the guarantee.

Two things it must not undo, both in `openspec/specs/iac-cicd-pipeline/spec.md`. *Required Status Checks Report on Every Pull Request* forbids registering a job whose name is generated from a matrix — a per-scenario matrix generates more of those names, not fewer, so the literal-named aggregating job stays and keeps concluding on their behalf. *Ansible Configuration Is Verified in Continuous Integration and Gates the Merge* requires discovery rather than enumeration, so scenario discovery must find `ansible/roles/*/molecule/*/` without a workflow edit, and must keep failing loudly on an empty result.

Worth noting that the per-job cost changes shape: each scenario job pays its own checkout and toolchain install, which the current per-role jobs amortise across a role's scenarios. Whether that is cheaper overall is an empirical question this entry does not answer.

**The bound on each job, which this change chooses at the same time as it reshapes them.** Recorded separately on 2026-09-11, and merged here because a timeout is chosen against observed durations and this change is what changes them: a value picked for per-role jobs is the wrong value for per-scenario ones. It is independent of `cache-the-apt-index-within-a-converge`, which is where the durations below come from.

No workflow in `.github/workflows/` declares `timeout-minutes` anywhere, so every job inherits GitHub's 360-minute default. For the Molecule matrix that is the difference between learning about a hung scenario and not: `ansible-verify` is a **required** status check, so a scenario that hangs leaves a pull request pending for six hours with no signal distinguishing it from one that is merely slow.

`AGENTS.md`'s own Molecule section describes several ways a run hangs rather than fails — a `prepare` whose container is torn down under a running play, a `verify` task killed with rc 137 and empty output — which is what makes the unbounded default worth closing rather than theoretical.

**The trade-off is the whole content of the change, and it is sharper than it looks.** A timeout tight enough to catch a hang promptly would have failed the runs of 2026-09-11 that prompted `cache-the-apt-index-within-a-converge`, which were slow and green rather than hung: `image_prune` took 74.5 minutes and passed. So the value has to sit above the degraded-but-working ceiling and below six hours, which means it is chosen against observed durations rather than against the baseline — and the baseline, around 10 minutes, is a bad guide. Record the durations the proposal is based on, since they are what a later reader will want when the number looks arbitrary.

`cache-the-apt-index-within-a-converge` has since lowered both the baseline and the ceiling, so the durations this one chooses against are the ones measured after it and not the ones quoted above. They are independent in mechanism and not in the number.

## 29. two-deferred-ci-items

Both noticed during `close-ci-verification-gaps`, neither a verification gap:

- **`.github/workflows/pre-commit-autoupdate.yml` installs `pre-commit` unpinned** (`pip install pre-commit`). That change created `.github/requirements-ci.txt`, which pins it; bringing this workflow onto the same file is a one-line fix in a workflow that change did not otherwise touch.
- **The destroy-policy gate's inspection logic is inline workflow shell.** Moving it into a version-controlled script with executable fixtures would make the highest-consequence logic in this repository reviewable and testable as code — `design.md` Decision 5 of that change names this as considered and deferred on merit-vs-scope grounds, not as rejected. Four fixtures already exist (clean, destructive, malformed, valid-JSON-that-is-not-a-plan) and are described in that change's `tasks.md` 1.1; the structural tests in `.github/tests/test_ci_configuration.py` currently assert the routes are closed, not that each is reached.
- **`actionlint` is named as a verification means but nothing installs it.** Three tasks in `close-ci-verification-gaps` cite it, and it was run manually from a scratch install. Adding it to `.pre-commit-config.yaml` would close that permanently — but it exits non-zero on two pre-existing `SC2016:info` findings (`pr-validation.yml`, the plan-comment step; `apply.yml`, the job-summary step — both single-quoted literal markdown in an `echo`, and both intentional). So landing the hook means dispositioning those two first, by fixing or ignoring them. That is the same trap this change refused to lay for the next person when `ansible-lint` failed on pre-existing violations, and it wants its own decision rather than being folded in.

## 30. lint-the-repository's-shell-scripts

**Not blocked; recorded rather than folded into `namespace-the-molecule-suite-per-working-tree`**, which added the script that makes this worth doing.

`ansible/scripts/run-molecule` is this repository's first committed shell script, and nothing checks it. `.pre-commit-config.yaml` carries hooks for Terraform, Ansible, secrets and commit messages, and none for shell. That change's own test-authoring step declined to verify the script with ShellCheck for the reason `AGENTS.md` gives about unpinned tools: an ad-hoc invocation of a linter this repository does not pin is unrepeatable, and a check that cannot be reached is indistinguishable from one that passed. Its `tasks.md` discloses the refusal under `## Not performed`.

The work is a pinned `shellcheck` hook in `.pre-commit-config.yaml`, and a decision about whether `.github/tests` should assert that the hook exists — the same shape as the pins that suite already reads. Small, and worth doing before there is a second script.

## 31. adopt the stubbed-runtime rig for the two guards Molecule cannot reach

`prune-unreferenced-host-images-periodically` shipped two guards that no assertion covers: local images are enumerated *before* the keep set is computed, and each tag is re-resolved immediately before removal. Both are observable only when the host's images change midway through a run, and a black-box Molecule scenario has no seam at which to change them. They are also the two that close the concurrent-deploy window against `app-deploy`, so the least-verified part of that design is the part facing the only actor competing with it.

Its code review built a rig that supplies the seam — a stubbed `docker` on `PATH` that answers some calls and fails others — and used it to confirm both guards present and mutation-visible, and to reproduce the fail-open that review found. Its `test-plan.md` invites exactly this: "if a deterministic arrangement is found for either — sized rather than slept — add it to `tasks.md` 2.7 and 2.8 together and strike it from here."

Adopting it would also cover the two abandon branches added by that review's own fix, which are likewise unasserted.

---

The entries from here to 13 came out of a second full review on 2026-09-08 (trunk at `74c7101`), made to judge whether this repository's shape can be reused for a second, company-owned host. It opened with two entries that are gone from this file, logical off-host backups of the shared database and a decision on the database model, resolved together by `scope-the-shared-database-to-non-durable-data`: reading the host showed the instance those entries argued over holds no application data at all, and that what this host needs is a stated boundary rather than a backup pipeline.

Only what applies to **this** host too is recorded here; the company-only findings (repository visibility, a second approver, an organisation-owned repository) are not this repository's concern. The review's verdict repeated the first audit's: the architecture is sound, and what follows is operational rather than structural. It read the live host as well as the tree, so where an entry cites a host fact, that is what `main-server` showed on 2026-09-08, not an inference from the code.

## 32. test-a-play-at-play-scope

Recorded 2026-09-10 by `configure-the-staging-host`, whose `design.md` Decision 10 found the gap and whose test author independently confirmed it.

That change adds a guard play to `ansible/playbooks/host-baseline.yml` that refuses when the targeted environment resolved to no host — closing a path where a converge that reached nothing exited 0. **Its behaviour is verified by hand and by nothing else**, and the two test commands this project has cannot take it:

- **Molecule's subject is a role on a host.** This is a play, and the case under test is the one where there is no host.
- **`.github/tests` may only read committed files statically.** Running `ansible-playbook` is not a static read, and that is enforced rather than conventional: `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in `test_ci_configuration.py` reads every module in the directory and would fail one that spawned it.

So what exists today is a static assertion that the guard is *present* and correctly shaped, plus a manual run recorded in that change's task list. **A green pull request does not establish that the guard fires.**

**One bypass is known and open, and a harness is what would have caught it.** `--limit` filters `localhost` out of the guard play, and Ansible has no per-play exemption from it, so `ansible-playbook … --limit <host>` against an empty group skips both plays and exits 0 — the very outcome the guard exists to prevent. With no `target_environment` supplied it also loses the designed diagnostic and reports the raw `Error processing keyword 'hosts'`. The sibling `--tags` bypass WAS closable and is closed (`tags: always`); this one can only be stated, in the play's header and in `docs/bootstrap-a-new-host.md`. A play-scope harness would be the thing that asserts the refusal under each of these invocation shapes rather than only the bare one.

What a play-scope harness would cover, beyond this one guard: any play-level behaviour at all — role ordering, `when:` conditions on role inclusion, and the play-scope input validation `ansible/playbooks/host-baseline.yml` states in the comment above its role list, which is deferred partly because nothing could test a fix for it.

Not blocked. The cost is a fourth row in `AGENTS.md`'s test-command table and whatever runner it needs, which is why it was not invented inside a change whose diff most needed reading closely.

## 33. tighten-the-refusal-scenario-s-own-filesystem-assert

**Not blocked. Recorded 2026-09-12 by `namespace-the-molecule-loop-devices`, whose code review found it in a file that change edits but in a line it does not author.**

`ansible/roles/platform_data_volume/molecule/superseded-path-in-force-refused/verify.yml` asserts `platform_data_volume_blkid.rc != 0` to establish that the role refused *before* formatting the device. That is the scenario's load-bearing assertion: the role's filesystem task is the first thing that changes the host, so a device still carrying no filesystem is the evidence the refusal came first.

**It fails open.** `rc != 0` reads every non-zero code as "no filesystem", and `blkid` returns 1 on a usage error — a probe that did not happen reports the refusal established. The four `prepare.yml` plays of this role were tightened to `rc != 2` by the change that recorded this entry, `rc 2` being the only code that means "looked, found nothing"; measured in the pinned image, twice and independently: unformatted 2, formatted 0, usage error 1, absent device 2. This assert was left alone because it is pre-existing and outside that change's diff, and folding a fifth edit into a file it had not otherwise touched is how a fourth review round becomes a fifth.

**A second, separate hazard in the same assert, which tightening the predicate does NOT close.** Each play redeclares its loop-minor offset by hand, so `verify.yml` and `prepare.yml` could drift apart. A drifted `verify` probes an unassociated minor, gets rc 2, and passes — under `rc != 2` exactly as under `rc != 0`. Whoever takes this entry should fix the rc-1 case and record the drift as still open, rather than closing one believing it closed the other. Deriving both from one place, or asserting in `verify` that the device is the one `prepare` associated, are the two shapes available.

## 34. hold-the-whole-static-suite-to-its-own-constraints

**Not blocked; small, and recorded by `alert-on-certificate-expiry`, which is the change that made it untrue.**

`AGENTS.md` says of the `.github/tests` suite that it may not make a network call, use a credential, spawn a container runtime or need a Terraform binary, and that "those constraints are themselves asserted by tests in that suite". They are: three assertions in `TestTheSuiteNeedsNoPrivilegedResource` and its neighbours parse the suite and check its imports and subprocess use.

What they parse is `SUITE_PATH`, which is `Path(__file__)` -- that one module. While `test_ci_configuration.py` was the whole suite that was the same thing. `alert-on-certificate-expiry` added `test_certificate_expiry_alerting.py` as a second module, and every module since has landed outside all three checks: the suite holds 22 as of 2026-09-13, of which the self-constraint assertions read one. Each was held to them by hand, which is exactly the assurance those assertions exist to replace.

The fix is to widen the three from their own file to every `test_*.py` in the suite directory. The alternative -- keeping the suite to one file so the self-check stays honest -- is worse: it is already 8,600 lines, and it would make "add a test" mean "edit the file the derive-tests step forbids an independent author from touching".

Note the edge this sits on. The derive-tests step has an author other than the implementer write a change's tests, and forbids that author editing an existing test file — so tests belonging in one arrive as a new module instead. Whether such a module is then folded into an existing one or left standing is a question about that workflow rather than about this repository, and it is settled where the workflow is written. This entry is what the tree owes either way: a module left standing must be held to the suite's own constraints.

## 35. prune-the-repository-walkers-of-provisioned-content

Recorded 2026-09-11 by the test author deriving `cache-the-apt-index-within-a-converge`, who met it as a red suite on a provisioned working tree.

`.github/tests/test_ci_configuration.py`'s `TestEveryComposeFileDeclaringAServiceImageIsCovered` walks the repository for Compose files and fails on six that live under `.molecule-home/collections/` — integration fixtures shipped by `community.docker` and `community.general`, which arrive the moment `ansible-galaxy collection install` runs into this project's per-working-tree Molecule namespace.

**It is green in continuous integration and red on a provisioned developer machine**, which is the defect rather than an inconvenience. The `validate` job that runs this suite never provisions Molecule, so `.molecule-home/` does not exist there; a developer who follows this repository's own Molecule instructions creates it and inherits a failure they did not cause. A check that disagrees with itself between the two is worse than no check: it trains its readers to discount it.

`cache-the-apt-index-within-a-converge` names this class in its own `tasks.md` 1.5 and handles it for the checks that change wrote, by enumerating roles from committed content rather than globbing a directory. This entry is the same rule applied to the walkers that were already there.

**The fix is not simply to prune one directory.** What makes a path this suite's subject is that it is *committed*, which is the boundary `AGENTS.md` draws for the suite and which already has a helper: `tracked_files()` in that same module, added by `narrow-the-molecule-trigger-to-what-it-reads`, enumerates the repository's tracked files and refuses rather than skips when it cannot. Re-pointing the repository-scope walkers at that helper closes the class rather than the instance, and would also reach `.terraform/`, virtual environments and sibling working trees under `.claude/worktrees/` — none of which any walker prunes today either.

Worth doing before the next person meets it: this failure reads as "your tree is broken", and the natural response is to delete `.molecule-home/`, which throws away the provisioning the suite's Molecule row depends on.

**It is also a race, not only a false positive.** That directory is *live* while Molecule runs — the ephemeral `tmp/` is created and removed under it — so running this suite during a Molecule run produces an intermittent error on top of the steady failure, as a file the walker has listed disappears before it is read. Observed 2026-09-11 while both ran at once, and not reproducible afterwards, which is the worst shape for anyone trying to diagnose it. Reading tracked files removes the race with the false positive, since nothing under that directory is tracked.

## 36. unify-the-two-role-exclusion-rules

**Not blocked.** Recorded as declined until 2026-09-13, and re-read then as work deferred on diff-hygiene grounds rather than a decision taken, which is what puts it here.

`.github/tests/test_ci_configuration.py` decides twice, differently, which directories under `ansible/roles/` are this repository's own. `role_names()` excludes any name containing a `.` — the Galaxy `namespace.role` convention — and the newer image-pinning checks exclude names appearing in `ansible/requirements.yml`'s `roles:` list.

The newer rule is the stronger one: content vendored into `ansible/roles/` that is *not* pinned in the manifest stays inside the pinning obligation, where the dot heuristic would silently exempt it. The older rule is adequate for what it does — reasoning about `ansible-verify.yml`'s role discovery — and the tests built on it pass.

**Why it was not folded into the change that created the second rule.** Unifying them means editing existing, passing tests, which is a change of its own rather than a rider on one whose subject is the pins.

Worth doing before a directory appears that the two rules would classify differently, at which point the disagreement stops being theoretical and one of the two is silently wrong about a real role.

## 37. widen-what-the-pull-request-identity-checks-can-read

**Not blocked.** Recorded as declined until 2026-09-13.

`open-autoupdate-pr-with-app-token` added a section to `.github/tests/test_ci_configuration.py` that discovers every workflow step opening a pull request and asserts what identity it uses. The discovery and its helpers make four assumptions that are true of this repository today and would each produce a **false positive** — a failing build on a legitimate change — rather than a false negative:

- `token_inputs` reads only step-level `env:`. A pull-request-opening `run:` step taking `GH_TOKEN` from a job- or workflow-level `env:`, which is the ordinary `gh` idiom, would be reported as having no explicit token.
- `step_opens_a_pull_request` requires a POST and the string `/pulls` somewhere in the same `run:` block, not in the same command. `apply.yml` already contains `/pulls` twice for read-only fetches; adding any `gh api --method POST` to that step would classify a read-only step as one that opens a pull request.
- `secrets_referenced_by` scans the whole job rather than the identity path. If the `autoupdate` job ever gains an unrelated secret — no longer hypothetical: `notice-when-a-periodic-job-stops-reporting` added `HEARTBEAT_PING_KEY` to that workflow, in a job of its own — the README tests would demand that secret be documented in the same passage as the App credential, which could only be satisfied by misdescribing it.
- `readme_sections` splits the README at any line beginning with `#`, including inside a fenced code block. Adding a shell snippet with a comment line to the section documenting the App would split that passage in two and fail two otherwise-correct tests.

None is a defect in what the tests assert; each is a limit on the shapes they can read.

**Why it was not folded in.** Fixing them means editing passing tests written by an independent author from the delta specs, which is a change of its own rather than a rider on the one that introduced them.

The first of the four is the one most likely to bite: it fires the first time a workflow here opens a pull request with `gh` instead of an action, and it fires as a red build on a correct change.

## 38. assert-the-autoupdate-workflow-s-two-unchecked-properties

**Not blocked.** Recorded as declined until 2026-09-13, though with its own successor already named: "a small change of its own that adds the scenario and has the assertion derived from it".

`.github/workflows/pre-commit-autoupdate.yml` carries two properties its own test section does not assert:

- The minting step's `permission-contents: write` / `permission-pull-requests: write` inputs, which down-scope every token it issues. The delta spec's clause that the credential carries no authority beyond what the pull-request step exercises is *readable* from committed content because of them, but not *checked*: an edit dropping those two lines passes the whole suite.
- The restricted input set on the pull-request step. Adding `labels` or `assignees` would need Issues, which the App does not hold, and nothing fails until the workflow next runs.

Neither is a live risk today: the App's own scope is exactly the two permissions the inputs name, so dropping them changes nothing until the App is widened. The exposure is second-order — a later widening of the App plus a later edit here.

**Why it was not folded in.** A check for either is a test, and this repository has a change's tests derived from its approved delta specs by an author other than the implementer. Adding them during that change's own build phase would have inverted that, and neither property has a scenario in the delta to derive from — they come from a prose clause. So this change owes the scenario first and the assertion from it, which is the order that makes the test derivable at all.

The workflow header says plainly which of its claims the suite does not stand behind, and that note is what this entry replaces.

## 39. assert-every-role-has-a-mock_roles-entry

**Not blocked; recorded rather than folded into `bound-host-log-growth-and-add-swap`, which is the change that hit it.** Adding the missing entry belonged to that change; asserting the invariant is a different concern, and the `.github/tests` suite is not that change's subject.

`.ansible-lint`'s `mock_roles:` hand-enumerates every role referenced by name, because ansible-lint does not resolve role references through `ansible/ansible.cfg`'s `roles_path` the way `ansible-playbook` does. The file's own comment says so. What it does not say, and what nothing enforces, is that the list must be complete: a role added under `ansible/roles/` and referenced from `ansible/playbooks/host-baseline.yml` without a matching entry fails `ansible-lint` with a false-positive "role not found" -- twice, once for the playbook and once for the role's own `converge.yml`.

Observed 2026-09-08 while adding the `swap` role. The diagnostic names a search path that does not include `ansible/roles/`, which reads as a configuration problem rather than as a missing line in a list, so the time is spent in the wrong file.

This is a **static read of a committed file** -- the set of directories under `ansible/roles/` minus the gitignored external role, against the `mock_roles` list in `.ansible-lint` -- so it fits the `.github/tests` row exactly: no network, no credential, no container runtime, no Terraform binary. It is the same shape as the existing "every lockfile-bearing directory is covered" check.

Worth doing because the cost is paid by whoever adds the *next* role, not by whoever left the list short, and because the failure arrives as a message pointing somewhere else.

## 40. assert-every-tfvars-assigns-its-required-variables

Recorded 2026-09-10 by `add-a-staging-environment`'s code review, which found the gap by falling into it.

That change shipped `terraform/stacks/main-staging/terraform.tfvars` with `server_type` deliberately unassigned, and `variables.tf` declares it with no default. Nothing in this repository detects that. The consequence is not subtle once it reaches CI — `pr-validation.yml`, `apply.yml` and `drift.yml` all run Terraform with `-input=false`, so the plan exits non-zero with `No value for required variable`, the conclusion step fails the required check, and a nightly drift sweep would fail for that environment every night and take the shared heartbeat with it — but it is detected by a *plan*, which needs a credential, a workspace and a network. The same fact is a pure static read: for each environment directory, every variable `variables.tf` declares without a `default` appears as an assignment in `terraform.tfvars`.

That places it squarely in `.github/tests`, whose subject is any property that is a static read of a committed file, and which may make no network call and invoke no Terraform binary. The parser is the only real work: `terraform.tfvars` assignments and `variable` blocks with and without defaults, without importing HCL machinery the suite does not have. `test_a_second_environment.py` already reads `terraform.tfvars` for volume names and can lend its approach.

**Not blocked.** It was left out of `add-a-staging-environment` because the gap it covers was that change's own disclosed, in-flight state — writing the check that fails the tree you are still assembling is a different change than the one that assembled it.

## 42. assert-markdown-prose-is-not-hard-wrapped

Recorded 2026-09-11, alongside the fix that removed the hard wraps this entry exists to keep out. `AGENTS.md`'s "Throughout" section now states the rule — *"Do not hard-wrap prose. Keep each paragraph on a single line whatever its length"* — and nothing checks it.

It has the property that puts a convention in `.github/tests` rather than in a reviewer's hands: it is a static read of committed files at repository scope, and it re-accumulates silently. The sweep this entry was recorded beside rewrapped 72 of 211 tracked markdown files, and the hard wraps were not a recent regression — they appeared in every week of the project's life, 3 on 2026-08-18 rising to 17 on 2026-09-09. The citation-form check was written after a sweep that "changed no rule and re-accumulated in three weeks"; this is the same shape.

The rule makes the assertion crisp rather than heuristic: under "one line per paragraph", a prose paragraph that spans more than one line is a violation, with no line-length threshold to tune. What the detector must exempt is the structure Markdown itself requires a break for — fenced and indented code, tables, YAML frontmatter, list-item continuations, and a line ending in two spaces or a backslash, which is an explicit hard break and semantic.

**Scope is markdown prose only.** Comments in `.py`, `.yml`, `.sh` and `.tf` files stay hard-wrapped; `.pre-commit-config.yaml`'s comments are the shape to preserve. A check that walks every file type would be the wrong check.

**What this deliberately does not attempt.** Not a formatter. Prettier's `proseWrap: "never"` would auto-fix, but it rewrites list markers, emphasis characters, table alignment and heading style across the tree, and it would rewrite archived records — which `AGENTS.md` says may be touched only to make them say what actually happened. There is also no Node toolchain in this repository to hang it on. markdownlint is the wrong tool for a different reason: `MD013` enforces a maximum line length, and there is no rule for the opposite.

Not blocked. One new module in `.github/tests`, whose constraints it fits: a static read of committed files, no network, no credential, no container.

## 43. catch-up-the-drifted-galaxy-pins

**Not blocked.** Recorded 2026-09-08, from an inventory taken while archiving `open-autoupdate-pr-with-app-token`.

`ansible/requirements.yml` pins five things. Two are current; three are behind by at least a major version:

| Collection | Pinned | Latest on 2026-09-08 |
|---|---|---|
| `hetzner.hcloud` | 7.0.0 | 7.0.0 |
| `geerlingguy.docker` (role) | 8.0.0 | 8.0.0 |
| `community.general` | 9.5.0 | 13.4.0 |
| `ansible.posix` | 1.6.2 | 2.2.2 |
| `community.docker` | 4.1.0 | 5.3.0 |

This is the most drifted manifest in the repository, and it is the one no tool watches: Dependabot has no `ansible-galaxy` ecosystem, so unlike the Terraform and Actions pins nothing has ever proposed a bump here.

Four majors is a migration rather than a version bump, which is why this is an entry and not a rider on anything. The collections are used by the hardening role (`community.general.ufw`), `deploy_user` (`ansible.posix.authorized_key`'s `key_options`, `community.docker.docker_login`) and the dynamic inventory. Molecule is the check that would catch a break, and `molecule test --all` per role is the gate this change has to pass -- read the SCENARIO RECAP rather than the exit code, per the note in `AGENTS.md`.

**Also delete the stale caveat while here.** Four of the five pins carry a comment saying the version "was chosen without the ability to query Galaxy from this environment (no network access) -- confirm it resolves". All five were confirmed against the Galaxy API on 2026-09-08 and every one resolves. The comment is now false where it is not merely stale, and it invites the next reader to re-do work that has been done.

## 44. cover-the-unwatched-manifests-and-settle-the-watcher

**Not blocked; the same shape as `cover-platform-images-with-dependabot`**, whose entry was deleted from this file when that change landed.

**Do not inherit that entry's estimate.** It called itself "a one-stanza change in `.github/dependabot.yml`" and was not one: *Automated Dependency Updates* (`openspec/specs/iac-safety-hardening/spec.md`) enumerates its ecosystems by name and the CI-configuration suite reads that enumeration back, so a further ecosystem is a stanza **plus** a specification delta widening that enumeration **plus** the tests that hold it. Budget for the same here.

Dependabot watches four ecosystems — `terraform`, `github-actions`, `docker-compose`, and `npm`, the last added so the OpenSpec CLI pin has a manifest it can see. Nothing watches the six pip pins: `.github/requirements-ci.txt` (`pre-commit==4.6.2`, `PyYAML==6.0.1`), `ansible/requirements-test.txt` (`ansible-core==2.21.3`, `molecule==26.8.0`, `molecule-plugins[docker]==26.7.15`) and `ansible/requirements.txt` (`ansible-core==2.21.3`). Dependabot's `pip` ecosystem reads all three file shapes.

**The third pip manifest arrived with `apply-host-configuration-through-a-gated-workflow` and changes what this entry must do**, because it does not merely add a file to watch. `ansible/requirements.txt` pins `ansible-core` at the version `ansible/requirements-test.txt` pins, and `.github/tests` fails the build on a difference -- so the converge runs the Ansible the Molecule suite verified those roles under. A Dependabot configuration that opened a pull request against one of the two would be red on arrival, every time. Whatever this entry does, the two must move as a pair: a grouped update, or one manifest watched and the other asserted to follow it.

Lower stakes than the platform images were -- these are the test and CI toolchain rather than production services -- but the cost is a few lines and the alternative is the same "when a person notices" that entry 43 is the consequence of.

Note the ordering constraint against entry 43: `ansible-core` is pinned here and the collections are pinned there, and the two are a matched set -- `ansible/requirements-test.txt`'s own comment records that the toolchain was "verified together, in this combination, on Python 3.12". A Dependabot bump of `ansible-core` landing mid-migration would confuse which half broke.

**Which watcher, decided rather than assumed.** Recorded separately on 2026-09-08 with a recommendation attached, so that the question is settled once by whoever closes the gap above rather than re-opened every time a manifest goes unwatched. The recommendation is attached, so that revisiting it starts from a position rather than from scratch.

Eight manifests in this repository carry pins, and five are watched: the Terraform lockfiles and Actions refs by Dependabot, `.pre-commit-config.yaml` by the workflow `open-autoupdate-pr-with-app-token` repaired, the eight `platform/docker-compose.yml` images by the `docker-compose` ecosystem `cover-platform-images-with-dependabot` added, and the OpenSpec CLI pin by the `npm` ecosystem that followed it. Three are not: the five galaxy pins (entry 43) and the five pip pins across two files, which is the half above.

Renovate has native managers for all seven, including `pre-commit` and `ansible-galaxy`, which Dependabot has for neither. One tool and one config would close every gap and retire the bespoke workflow.

**The recommendation is to stay with Dependabot, for now,** and it is stronger than when written: the gaps this paragraph counted on configuration to close have been closed that way twice since, by `cover-platform-images-with-dependabot` and by the `npm` stanza, neither needing a new trust relationship. The half above closes the pip gap on the same terms. What Renovate uniquely adds is the galaxy manager -- and entry 43 argues that a four-major backlog wants a deliberate migration, not a bot proposing it. Hosted Renovate is also a third-party application with write access, which cuts against the reasoning already recorded in the *Automated Dependency Updates* requirement about third-party supply-chain risk.

Self-hosted Renovate is the interesting middle: it would reuse the `infrastructure-autoupdate` GitHub App, which is already scoped to Contents and Pull requests on this repository alone, so no third party gains write access and the credential work is done. The generalised requirement was written to permit exactly this -- *any* workflow opening a pull request, not just the hook-update one.

**Revisit when** a second Compose stack appears, or the galaxy manifest grows past a handful of entries, or entry 43's migration is done and the small incremental bumps it will then need start being missed again. The single-config argument strengthens as the manifest count rises; at three unwatched manifests it does not yet carry the trust cost.

**The condition this waited on is met.** It said: do not add a fifth automation to a repository where nothing notices a red scheduled run, which is the lesson `open-autoupdate-pr-with-app-token` was. Something notices now — `notice-when-a-periodic-job-stops-reporting` gives every scheduled workflow a heartbeat check whose silence alarms, and its own coverage test obliges any workflow added later to carry one. The trust cost argued above is what remains to weigh.

## 45. sweep-the-stale-scenario-titles-and-check-them

**Not blocked. Recorded 2026-09-13 by `correct-the-documents-against-the-tree`, which swept the requirement half of this defect and measured the scenario half rather than folding it in.**

A citation in this repository names a requirement and, very often, a scenario inside it — a docstring reading `MODIFIED requirement: Dynamic Inventory via the hcloud Plugin, One Source per Stack -- scenario "A source's credential variable is the name the environment declares"` is the ordinary shape. Both halves rot in the same rename, and that change corrected only the first, so a docstring it edited can name a live requirement and, in the next breath, a scenario that no longer exists.

**Measured 2026-09-13, at trunk `80a8ec5`: thirty citations name a scenario no specification under `openspec/specs/` currently holds.** Twenty-nine are in `.github/tests`, one is in `.github/workflows/drift.yml`.

**The one in `drift.yml` is the inverse case and is half somebody else's.** That comment cites a scenario as *"Drift in one stack does not resolve another's report"* while the specification still titles it *"Drift in one environment does not resolve another's report"* — the citation is ahead of the specification rather than behind it. The specification side of that rename was deliberately left alone by `rename-terraform-environments-to-stacks`, for a reason that still binds: a `MODIFIED` requirement replaces its block whole, so `openspec validate` reads a renamed scenario as a *dropped* one and refuses the change. A change wanting to rename one needs a mechanism, not an edit — and that is this entry's other half. Sweeping the twenty-nine without deciding this one would leave the tree citing a title the specification does not have, which is this entry's own defect in the opposite direction.

**Why it was not folded into the sweep that found it.** It is a different predicate over a different set — the live scenario titles, not the retired requirement names — so the check that change built does not hold it and would not have caught a single one of the thirty. And the replacements are not mechanical: several scenario titles were reworded rather than renamed, so each needs a reading rather than a substitution. Folding it in would have doubled that change's diff and put a second unchecked sweep inside the change whose whole argument is that unchecked sweeps re-accumulate.

**Do the check with the sweep, not after it.** `.github/tests/test_the_retired_requirement_names_are_gone.py` already reads every tracked file, already flattens each one so a title wrapped across a comment's line break is found, and already derives its subject from committed specifications. The scenario predicate is the inverse of its current one — a cited title that is **not** among the live scenario titles, rather than a name that **is** among the retired ones — so it needs a reader of its own rather than a second literal. Its false-positive risk is the thing to measure first: a quoted phrase that is not a citation at all looks exactly like a citation of a scenario that does not exist.

## 46. rename-the-requirements-that-read-narrower-than-they-are

**Not blocked.**

`make-the-pipeline-environment-agnostic` made the pipeline environment-agnostic without renaming three requirements whose names still name production alone:

- *Gated Production Apply Applies the Reviewed Plan*, which now governs every environment's apply, not production's;
- *Credential Scoping by Privilege*, whose token table it replaced with a per-environment scheme — the name is accurate but its scenarios read as production's;
- *Write Credentials Confined to the Gated Pipeline* (`iac-safety-hardening`), now stated over each environment's own Read & Write token.

Only the first is a genuine name/content mismatch; the other two are listed because the same sweep would touch them and a reader chasing one will find the others.

**Why it was deferred, and what the change must budget for.** Requirement names are this repository's citation form (`AGENTS.md`, "Citing this repository's own specifications and change records"), and they are cited from comments in `apply.yml`, `drift.yml` and `pr-validation.yml`, from `docs/bootstrap-a-new-host.md`, and from archived change records. Renaming sweeps every one of those. It was declined because doing it inside the change that restructured three gated workflows would have mixed a mechanical rename into the diff that most needed reading closely — which is an argument against that carrier, not against the work.

`.github/tests/test_a_retired_requirement_name_is_reported.py` is what makes the sweep checkable rather than hopeful, and it did not exist when this was deferred.

**The precedent to follow.** `add-a-staging-environment` renamed a fourth requirement of this kind — the one that now reads *Each Stack Has a Dedicated Hetzner Cloud Project*, and then named prod alone — taking the rename where it already had a content change to carry it. These three have no such moment coming, which is why they need a change of their own.

**The second set, swept by the same change.** Six more requirements are stated over prod alone, or over "this host" at a repository that now has two. They are the same mechanical rename over a different capability, and separating them would mean paying the citation sweep twice.

**Not blocked, and unblocked by nothing — this half is simply the larger of the two.**

Six requirements are stated over prod alone, or over "this host" at a repository that now has two:

- *Conditional Prod Server Creation* (`openspec/specs/iac-server-lifecycle/spec.md`)
- *Conditional Prod Volume Creation* (`openspec/specs/iac-data-volumes/spec.md`)
- *Data Durability for Stateful Resources* and *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`)
- *Host Joins a Private Tailnet for Non-Operator SSH Access* — "the prod host"
- *Unprivileged Operator Accounts Support Interactive Host Inspection* — "on the prod host"

The last two are in `openspec/specs/iac-host-configuration/spec.md`, and both acquired a second subject the moment staging converged on 2026-09-10: a staging host joins the same tailnet and carries the same operator account, and the requirements describing that name only prod.

The first two describe a mechanism both environments now use: staging declares `server_enabled` and `volume_enabled` with prod's semantics, and its rollback and its cost-pause both rest on them. They are obliged for staging by nothing — the requirements name prod. The middle two say "this host", which was unambiguous at one host and is not at two.

**Why it was deferred.** Nothing on staging contradicts any of them: it holds no store, so the durability and backup requirements have no second subject yet, and the lifecycle toggles are correct at both environments whether or not the requirement says so. Generalising six requirements across four capabilities inside a change whose scope was one environment directory would have mixed a mechanical sweep into the diff that most needed reading closely.

**What makes it live rather than theoretical.** Entry 16 puts the platform stack and a database on staging. That is the moment "this host" stops being merely imprecise and starts being wrong about which host a durability obligation binds — so this is worth taking before 29 rather than after it.

## 47. correct-the-tfvars-parenthetical-that-names-labels

**Not blocked, and small.** It waited three months as a correction to batch into whatever change next touched the requirement, and no such change came — which is what makes it an entry of its own.

*Version Control Excludes State and Secrets* (`openspec/specs/iac-repo-foundations/spec.md`) describes `terraform/stacks/<name>/terraform.tfvars` as holding "server type, region, image, labels, allowed CIDRs". The file holds no labels; the only `labels` block under `terraform/stacks/main-production/` is in `ssh_key.tf`.

The disagreement is **factual, not normative**. The parenthetical is illustrative, the requirement's normative content is that the file is committed and non-secret, and labels genuinely are non-secret environment configuration — simply set on the resource rather than passed through this file. Nothing is permitted or forbidden differently because of it, and no reader is misled about what the requirement demands. That is why it is cheap and low in priority, not why it should be left.

**Two carriers have now gone past it.** `rename-terraform-environments-to-stacks` rewrote this very row on 2026-09-11, moving the `terraform.tfvars` path onto the new Terraform root and leaving `labels` where it stands; a vocabulary sweep is not a substantive modification of this requirement, and folding a factual correction into it would have been unrelated scope. Being walked past is not an argument for a third pass.

**What it costs is the part to decide when it is proposed.** Correcting it is a `MODIFIED` delta, and the derived test it would owe is "the requirement's parenthetical agrees with `terraform.tfvars`" — a cross-file assertion this repository has declined twice on its own merits, on the grounds that an assertion converts a silent staleness into a standing editing obligation. So this change should probably correct the prose and argue explicitly that the scenario it owes is not that assertion.

## 49. separate-history-from-rationale-in-source-comments

**No longer blocked.** It waited on the citation-form decision and on the sweep that followed it; both were delivered by `decide-archived-change-reference-policy` (archived 2026-09-07, PR #70), which also converted every citation in the comment blocks below. What remains here is the separation this change deliberately did not do: it changed citation *form* only, and left the prose around it alone.

Source comments in this repository currently mix three kinds of text with no way to tell them apart:

- **why the code is shaped this way** — irreplaceable, keep it. The tailnet polarity note (`ansible/roles/tailscale/tasks/main.yml:76-82`) and the GHCR tolerated/not-tolerated block (the `ghcr_pull_*` comment block in `ansible/roles/deploy_user/tasks/main.yml`) are load-bearing and must survive any pass.
- **what a past change did** — git log and the archive already own this.
- **a TODO whose condition has passed** — dead, and quietly misleading.

Only the first kind survives archiving. Concrete instances of the other two (the `platform/docker-compose.yml` header, formerly listed first, was removed by `fix-volume-discovery-and-consistency`, which was editing that file anyway):

- `terraform/stacks/main-production/ssh_key.tf` — a `moved` block that documents its own removal condition ("Safe to delete once the next apply has run") from a change archived 2026-08-18.
- `terraform/stacks/main-production/main.tf` — explains a value the file no longer holds.

The tailscale role is 140 comment lines against 197 non-blank, measured 2026-09-13; it was 48 against 90 when this entry was written, so the ratio has worsened rather than held. This is a style question with a real maintenance cost, not a cosmetic one.

## 50. label-each-stack-s-alerts-with-the-stack-they-came-from

Recorded 2026-09-13 by `deploy-the-platform-stack-per-environment`, which put the platform stack on a second host and found that nothing distinguishes the two hosts' alerts.

`platform/docker-compose.yml`'s Prometheus configuration declares no `external_labels`, so a `MetricsTargetDown` raised on staging and one raised on production are **identical text**. Alertmanager adds nothing either: its routes group on the alert's own labels, and none of them names a host, a stack or an environment.

**What that change did instead, and why it is not enough.** Each stack's `PLATFORM_SLACK_WEBHOOK_URL` and `PLATFORM_DEADMANSWITCH_URL` are secrets on that stack's own GitHub Environment, so the operator can — and on 2026-09-13 did — point each stack at a channel and a dead-man's-switch check of its own. Attribution then comes from *where the message arrived* rather than from anything in it. That works, costs nothing, and is what `docs/bootstrap-a-new-host.md` §7.3 now instructs.

It is not enough because **nothing enforces it**. An operator who pastes production's webhook into staging's Environment gets two hosts alerting into one channel with no way to tell them apart, and no check in this repository reports it — the values are repository settings, and `.github/tests` may not read those. The failure is also silent in the direction that matters: the alerts keep arriving, so nothing looks broken until someone acts on the wrong host.

**Why it was not folded in.** It is a change to the committed stack definition — `external_labels` under Prometheus's `global:`, a new variable in `platform/.env.example`, a tenth `PLATFORM_*` secret, and a regenerated `platform.config-checksum` on the Prometheus service. The change that found it had declared parameterising the Compose file a Non-Goal, and its deltas were approved on that boundary.

**Worth settling when it is taken.** Whether the label is the stack (`main-staging`) or the environment (`staging`) — these are different axes and this repository has been bitten by conflating them before; whether the value is rendered from the existing `PLATFORM_DEPLOY_HOST` rather than adding a secret, which would avoid a tenth value to enter per stack; and whether Alertmanager's routes should group on it, which is what would stop two stacks' alerts collapsing into one notification that names neither.

Not blocked.

## 51. record-how-an-application-is-onboarded

Recorded 2026-09-13 by the operator, who is about to onboard `commerce-ops` to a second host and found the procedure written as a stage of a document about bootstrapping a **host**.

`docs/bootstrap-a-new-host.md` stage 8 is the whole of what exists, and it is in the wrong document for what it now has to serve: that document is a once-per-server procedure read front to back, while this is a once-per-application procedure read out of order, years apart, by someone who is not bootstrapping anything. Extract it to a document of its own and leave a pointer in stage 8.

**Extract rather than copy.** A second copy of a procedure that touches deploy keys, sudoers rules and a database decision would drift from the first, and the drift would be invisible: both would read as authoritative. The test is whether stage 8 still says anything the new document does not — if it does, the extraction was partial.

**What the move has to fix, and it is the reason this is not a file rename.** Stage 8 is written for one host, and says so in a parenthetical: *"Add to `deploy_apps` in `ansible/inventory/group_vars/production.yml` (and, once an application has a staging deploy path, to `staging.yml` with a keypair of its own)"*. That parenthetical was accurate while the platform stack reached one host. `deploy-the-platform-stack-per-environment` ended that, and the real shape is a **grid**: several applications across several environments, where each cell needs a keypair of its own, a `deploy_apps` entry in that environment's `group_vars`, a deploy path in the application's own repository, and a secret set in an Environment there. The axis is the environment throughout — `deploy_apps` lives in `group_vars/<environment>.yml` — and this paragraph said "stacks" until `onboard-commerce-ops-to-staging` corrected it, which is the confusion worth naming rather than repeating. The document should say which steps repeat on which axis, because getting that wrong is how one leaked private half ends up deploying to two hosts. `onboard-commerce-ops-to-staging` corrected §0.3's key table and the paragraph above it to one key per application per environment, so that much is done; two things in stage 8 are not, and both are the same class of sentence written when there was one deploy target. Stage 8.4's "A `production` Environment with a required reviewer … it has one deploy target and no stacks, so `production` is right for it" is falsified by an application that now has a staging deploy path as well. Add `docs/naming-conventions.md`'s *The workstation* table to the same decision: it lists the converge key and not the two deploy keys, and says the converge key is "the only per-stack artefact whose name lives on a workstation", which two per-deploy-target keys make questionable. And §0.3's platform-deploy-key row spells its per-target segment `<stack>` while the application row now spells it `<environment>` — one of the two is wrong and the extraction is where one is chosen. **What is committed settles it only for a sibling.** `docs/naming-conventions.md`'s *The workstation* table does carry `~/.ssh/` filenames and does rule on this axis — "the converge key carries the stack, not the environment" — but it lists neither deploy key, and `docs/bootstrap-a-new-host.md` §0.3 calls it "the full list", so start there and notice what it omits. The key *comments*, which are committed, have four spellings, no two alike — `deploy@platform` and `commerce-ops-deploy` in `production.yml` carry no target segment at all, while `deploy@platform-staging` and `commerce-ops-deploy-staging` in `staging.yml` carry the environment. §0.3's own "Verify before storing" step asks a reader to tell two private halves apart by that comment, which the production pair cannot do.

**Three things stage 8 does not say and the first real onboarding will want:**

- **What is reachable before DNS exists.** Traefik routes on the `Host` header, so an application deployed to a host with no public hostname is fully testable over the tailnet with a `Host:` header — `curl -k --resolve '<hostname>:443:<tailnet IP>' https://<hostname>/`, and **not** the plain `http://` form, which the `web` entrypoint answers with a `301` to `websecure` whatever the `Host` header says — but **not from a browser**, because the certificate cannot issue while 443 is closed to the public internet (the resolver uses TLS-ALPN-01, which Let's Encrypt performs by connecting inbound) and what answers instead is Traefik's own default certificate. That distinction decides whether a given stack needs its web ports opened at all, and it is currently written down nowhere. **Write down with it why the host firewall is not what closes those ports**: a container-published port is DNAT'd and forwarded, never offered to UFW's `INPUT` chain, so `hardening_web_allowed_cidrs` does not gate Traefik on any interface and the cloud firewall is the whole of what refuses from outside. `onboard-commerce-ops-to-staging` got this wrong from reading the role rather than probing the host, and entry 53 is where the general case is recorded.
- **The order that avoids a wasted converge.** The `deploy_apps` entry needs a converge before the application's own deploy can authenticate, and that converge is a merge to `main` touching `ansible/` — so an application repository that is ready first waits on an infrastructure pull request rather than the reverse.
- **What an enumerated-but-undeployed application does to the image prune.** `ansible/inventory/group_vars/staging.yml` records it: such an application "contributes nothing to the keep set" and may legitimately sit there before anything deploys behind it, the converge that creates its authorisation having to run first. Harmless, and worth knowing before it is read as a fault.

**Write it from a real onboarding rather than from stage 8's text.** The operator is onboarding `commerce-ops` to staging now; a procedure transcribed from a document is a procedure nobody has walked, and this one has a parenthetical in it that was true for exactly as long as there was one host. Taking this immediately after that onboarding is what makes it accurate.

Not blocked. It touches `docs/` and no mechanism.

## 52. revoke-an-application-s-deploy-authorisation

Recorded 2026-09-13 by `onboard-commerce-ops-to-staging`, which added a `deploy_apps` entry and found, while stating what reverting it would cost, that nothing in this repository takes one back.

`deploy_user` renders three things per entry — `/opt/<name>`, `/etc/sudoers.d/app-deploy-<name>`, and an `authorized_keys` line carrying the forced command — and removes none of them for an entry that is gone. The `ansible.posix.authorized_key` task leaves `exclusive` at its default, deliberately, so that each loop iteration manages only its own key and no application's entry disturbs another's; the sudoers files are written one per application with nothing enumerating the directory; and the `/opt` directory is created and never reaped. **So deleting an entry stops the role acting on it and leaves the host authorising that key exactly as before.** Revocation is an edit on the host, or a rotation of the private half in the application's own repository — neither of which is a commit here, and neither of which any converge would notice.

This is the same shape as entry 2's finding about `root`'s `authorized_keys`, and the same two things are true of it: `exclusive: true` is the only form that actually revokes and is the form that can lock everyone out, and the `ops_user` role's per-entry `state:` model — where revocation is `state: absent` with the entry **left in place** until a converge has removed it — is the shape to follow rather than invent. The two entries are worth taking together for that reason, though neither blocks the other.

Not blocked. Nothing has needed revoking yet, which is why this is an entry rather than an incident.

## 53. say-what-the-host-firewall-actually-gates

**Recorded 2026-09-13 by `onboard-commerce-ops-to-staging`, which asserted the opposite in three documents and was caught by a code review that probed the host instead of reading the role.**

Measured from the operator's workstation, over the tailnet, against staging — whose `hardening_web_allowed_cidrs` was `[]` and whose `web_allowed_cidrs` was `[]` at the time, and whose UFW is `active`:

    curl -H 'Host: example.com' http://100.85.219.36/   ->  301
    curl -k https://100.85.219.36/                       ->  404   (CN = TRAEFIK DEFAULT CERT)

**A container-published port is not filtered by UFW, on any interface.** Docker DNATs it in `nat/PREROUTING` and accepts it in the `FORWARD` chain; UFW's rules hang off `INPUT`, which those packets never traverse. So `hardening_web_allowed_cidrs` gates nothing for `platform-traefik-1`, which publishes `0.0.0.0:80` and `0.0.0.0:443`, and what refuses a request from the public internet is the Hetzner cloud firewall alone. Nothing in `ansible/roles/` touches `DOCKER-USER` or `after.rules`, which is where a fix would go.

**What this falsifies, and it is the reason this is an entry rather than a note.** The firewall convention in `AGENTS.md` says the two layers are the cloud firewall and UFW, and that for any given port exactly one of them is the documented access gate. For a container-published port that is not a split at all — there is one layer, and a reader who closes UFW and believes the port shut is wrong. `docs/bootstrap-a-new-host.md` said "both firewall layers refuse inbound traffic to them" in two places, both rewritten by `expose-staging-on-the-web` when it opened staging's web ports; `expose-staging-on-the-web`'s backlog entry carried the two-layer obligation as one of the two things it said existed nowhere else, until that change was archived; the obligation itself is stated in `ansible/roles/hardening/README.md`. `ansible/inventory/group_vars/staging.yml`'s comment above `hardening_web_allowed_cidrs` reasoned from it directly and was corrected by the change that recorded this entry, since it was editing that file anyway — it is the worked example of what the others need, not an outstanding item. Each of the rest needs to say which ports it is true of. Entry 14 is the one place that draws a wrong *conclusion* rather than just restating the rule: it counts a cloud-firewall change blocking 443 as gated "in two of at least three ways", one of them UFW as "the co-equal host-level layer" — and for 443 UFW is not in the path, so that count is overstated. The mirror obligation itself survives all of this: `terraform.tfvars` and `group_vars` still have to agree, and the reason is unchanged for every port UFW does gate.

**One thing to settle while doing it, because the answer is not obvious.** `add-grafana-tailnet-ufw-rule` exists because Grafana was found unreachable from the tailnet until a UFW allow for 3000 was added by hand, and `platform-grafana-1` publishes `100.85.219.36:3000->3000/tcp` — a container-published port, which by the mechanism above UFW never filtered. Either that rule does nothing and the original diagnosis was wrong, or something distinguishes that case. Find out before writing the general rule down, since one of those two is currently recorded as a worked example in an archived change.

**What is not owed here.** Nothing about this is an exposure: what reaches Traefik from the internet is decided by the cloud firewall on both hosts, and a tailnet peer is an authenticated device of the operator's own. This is a documentation defect about which mechanism does the refusing, and the decision of whether to close container ports at the host layer as well — `DOCKER-USER` rules, or publishing to `127.0.0.1` and reaching containers another way — is a change of its own that this entry does not prejudge.

Not blocked.

## 54. automate-per-application-database-provisioning

**Not blocked; recorded because its obligation is due and unmet.** *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) obliges automating how an application's database and role are provisioned in the shared instance and how the role's password reaches the application. That obligation's trigger — the first application given a database there — fired on 2026-09-13 with `commerce-ops` on the staging host, and production's database followed by the same recipe. `provision-commerce-ops-database-in-the-shared-instance` provisioned both by hand, by the recipe now in `docs/onboard-an-application.md`, and recorded the obligation in that requirement as a stated divergence rather than building the mechanism.

**Why it was not built then.** A credential path, naming rule and failure mode fitted to one consumer are fitted to one application's Compose file and one repository's secret names, and are discovered wrong by the next application rather than by review. That change met one such fit on its first host: production's `commerce-ops` Environment already held `POSTGRES_PASSWORD`, for the application's private PostgreSQL, so the shared-instance password had to take a name of its own, `SHARED_POSTGRES_PASSWORD`. A mechanism has to handle that collision for every application, not only the one it was designed against.

**What a design has to answer**, taken from what the manual recipe had to: where the password is generated and how it reaches the application's deploy without a command line, a log line or a file in this repository; what happens when the secret name is already taken; that a re-run is a rotation which the application picks up only on its next deploy; re-provisioning after a rebuild or a volume reset; and per-host independence, so that one leaked credential reaches one host.

**Archiving it obliges a delta elsewhere.** The requirement's paragraph "One divergence is stated rather than hidden, as of 2026-09-13" says it is replaced when this mechanism lands, and nothing else would prompt that; that recipe then becomes whatever the mechanism makes of it.

## 55. classify-commerce-ops-production-data-for-the-shared-instance

**Not blocked; recorded because it is a specification change, decided by the operator after the change that provisioned the database had merged.** On 2026-09-14 the operator decided that production's `commerce-ops` leaves its private PostgreSQL for the database `provision-commerce-ops-database-in-the-shared-instance` provisioned in production's shared instance, and moves to Supabase only later (`move-commerce-ops-durable-data-to-supabase`). Its data includes the hand-curated rows that entry records — durable under *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) as it stands, which keeps durable data out of the shared instance unconditionally, because holding none is what lets that instance go without a backup. Asked whether to keep the private database until Supabase, or to admit the data only with an off-host backup and a rehearsed restore, the operator chose to classify `commerce-ops`'s production data as tolerable to lose, to the operator, with no backup — a temporary decision, taken because the application is at a very early, experimental stage, and ending with its move to Supabase.

**What the change owes.** A MODIFIED delta on that requirement recording the policy — whose loss it treats as tolerable, which application and host it covers, and that it ends with the move to Supabase — in the shape of the staging rehearsal-data policy the requirement already carries, and a delta on *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`), whose store table and divergence paragraph it bears on. It merges before any production row lands in the shared instance, and the `commerce-ops` repository's production cutover waits on it.

**What the operator accepted, and what it must not become.** The shared instance is treated as disposable: `upgrade-the-shared-postgres-major` plans to discard its volume, and a rebuild recreates it empty. Once `commerce-ops`'s production data is there, either deletes it for good, and that entry and the rebuild runbook have to say so where an operator reads them before acting. The classification names one application on one host and must not be read as permission for any other application's durable data.

## 56. record-the-hostname-scheme

**Recorded 2026-09-14 by `expose-staging-on-the-web`, which wrote down the DNS the scheme produces and not the scheme.** The public names this repository's hosts serve follow `<service>.<server>.<base domain>` — `commerce-ops.main-production.fincci.bike`, `commerce-ops.main-staging.fincci.bike` — resolved by one wildcard `A` record per server, with a short alias such as `ops.fincci.bike` as a record of its own. The rule was decided in the `commerce-ops` repository, whose `deploy-commerce-ops-to-staging` handoff names `docs/naming-conventions.md` here as its home. That file names servers, stacks, keys and the OS hostname, and not the public names under them.

**What the entry owes:** the rule; where the base domain comes from; and how it composes with the `<company>` segment and the stack name that file already rules on, since a company-owned base domain is a naming axis `<company>` does not yet cover. `docs/bootstrap-a-new-host.md` §4.4 describes the wildcard shape and should point at the rule rather than restate it.

Not blocked. It touches `docs/` and no mechanism.

## 57. quieten-the-certificate-expiry-guard-on-a-host-serving-nothing

**Recorded 2026-09-15 by the operator and this session, from the host rather than from the rules.** `CertificateExpiryNotObserved` has been firing on staging since 2026-09-13 17:01 UTC, which is the hour the platform stack first reached that host. Measured two ways: `amtool alert` inside `platform-alertmanager-1`, and Prometheus's own `/api/v1/alerts`, where it carries `activeAt` `2026-09-13T16:46:46Z` against the rule's `for: 15m`. It predates `expose-staging-on-the-web` by two days, so opening staging's web ports neither caused it nor cleared it.

**The alert is correct, and on this host it is noise.** Its expression in `platform/docker-compose.yml` is `absent(traefik_tls_certs_not_after{cn!=""}) or count(traefik_tls_certs_not_after{cn=""}) > 0`, and it exists to stop `TLSCertificateExpiringSoon` from silently watching nothing — the reasoning is in the change `alert-on-certificate-expiry`. Staging publishes no such series because it holds no certificate: Traefik requests one per router, no container there carries a router label, and `/letsencrypt/acme.json` is 0 bytes. It reaches Slack, since the routing tree sends every alert but `Watchdog` to that receiver (`amtool config routes test severity=warning alertname=CertificateExpiryNotObserved` returns `slack`).

**The design content is telling two silences apart**, which is why this is an entry rather than a one-line fix. Suppressing the alert wherever no certificate exists also suppresses the case it was written for: a Traefik that served certificates and now serves none. A fix therefore needs a series that says the host is *meant* to serve one — a router count, or a per-stack expectation — so that a host with nothing routed is quiet while a host that lost its certificates still alarms.

**Not blocked, and it may close itself.** An application reaching staging clears it: the `commerce-ops` repository's `deploy-commerce-ops-to-staging` is the deploy that would. If that lands first, what survives is the general case, which the next empty host meets on its first day — a second staging, or any new stack whose platform deploy precedes its first application.

## 58. bound-a-deploy-key-to-one-host-when-an-environment-holds-two-stacks

**Not blocked. Recorded 2026-09-15 by `record-how-an-application-is-onboarded`, which decided the deploy keys' naming axis and found that the axis is load-bearing in a way no name can fix.**

`deploy_apps` lives in `ansible/inventory/group_vars/<environment>.yml`, so an entry there authorises its key on **every host in that environment**. Today each environment holds exactly one stack and therefore one host, so "one key per environment" and "one key per host" are the same sentence. A second tenant ends that: `main-production` and `analytics-production` are two stacks and two hosts in one environment, reading one `group_vars` file — so one application's deploy key, and the `platform` entry's key with it, would authorise a deploy to both.

**That is the invariant `docs/bootstrap-a-new-host.md` §0.3 states in as many words** — "one leaked private half must deploy to one host" — and the naming decision this entry came from does not secure it. It puts each key's *name* on the axis its authorisation actually sits on, which is the honest spelling of the current shape; it does not make that shape one host per key.

**Where the fix has to go is the inventory's group layout, not a filename.** The candidates, none costed here: `deploy_apps` moving to a per-stack or per-host vars file; a group per tenant-environment pair rather than per environment; or the entry gaining a host selector the role honours. Each changes what a converge reads, so each wants its own Molecule coverage, and the choice interacts with what `AGENTS.md` records about a source being named for its stack and a group for its axis.

**Nothing reports it, which is the part worth keeping in view.** A second tenant would be onboarded by following `docs/onboard-an-application.md`, which would produce a key per environment as instructed, and the over-authorisation would be silent: both hosts would accept the key and both deploys would work. Take this before a second tenant exists rather than after, since afterwards the remedy is a re-key rather than a layout.
