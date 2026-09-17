## Context

See this change's `proposal.md` for the measurements and the blast radius.

The mechanism, stated once so the decisions below can refer to it: Compose stores `com.docker.compose.config-hash` on each container and recreates a service when the hash it computes from the current file differs from the one on the running container. Inline `configs:` content is not an input to that hash. `docker compose config --hash='*'` prints exactly the value Compose compares, so the whole question is answerable offline, without a daemon, and without touching the host.

One further fact, read from the running host on 2026-09-09 and worth stating because it decides how bad the defect is: `platform-prometheus-1`'s only bind mount is `/mnt/main-data/prometheus`. The configuration files at `/etc/prometheus/` are **copied into the container when it is created**, not bind-mounted from the host. So a service's embedded configuration cannot change without the container being replaced — there is no path by which a corrected file on the host reaches a running container, and no reload short of recreation.

Three services mount inline configuration:

| Service | Configs |
|---|---|
| `prometheus` | `prometheus_config`, `prometheus_rules` |
| `alertmanager` | `alertmanager_config` |
| `grafana` | `grafana_datasource`, `grafana_dashboard_provider`, and three dashboards |

`app-deploy` — `ansible/roles/deploy_user/tasks/main.yml`, "Install the generic app-deploy script" — runs `docker compose pull` then `docker compose up -d --wait` in `/opt/<app>`. It is generic across applications, and this change does not touch it.

## Goals / Non-Goals

**Goals:**

- A configuration-only edit reaches the running service on the deploy that ships it.
- Only the services whose configuration changed are recreated.
- Forgetting to maintain the mechanism fails a pull request, not a deploy.

**Non-Goals:**

- Changing what `app-deploy` runs, or anything else in `ansible/`. The defect is in what the stack definition tells Compose, not in how the deploy invokes it.
- Verifying at deploy time that each running container ended up on the hash the file specifies. That is a strictly wider backstop — it would catch reasons for a service not being replaced that nobody has thought of — and it is recorded as its own queue entry rather than folded in. Note it does **not** subsume this change: without a label, a configuration-only change produces equal hashes on both sides, so such a check would pass while the configuration sat unapplied.
- Moving the configuration out of `configs:` into separate files. That is refused for an existing and unrelated reason — `docs/deferred-work.md`, "Splitting `platform/docker-compose.yml` into multiple files" — because the deploy's forced command extracts a fixed two-member list, and widening it widens what a holder of the deploy key can write to the host.

## Decisions

### Decision 1: A checksum of the configuration, as a service label

A `labels:` entry on each config-carrying service, holding a digest of the content of the configs that service mounts. A label is part of the service definition, so it is an input to the hash — measured, not assumed: adding one moved `prometheus`'s hash from `abd50e6a…` to `2c229bf2…` and left `alertmanager`'s untouched.

Scoping falls out for free. Each service's label covers only the configs it mounts, so editing an alert rule recreates `prometheus` alone, and editing a dashboard recreates `grafana` alone. Postgres and Traefik carry no inline configuration and are never recreated on this account.

Alternatives considered:

- **`--force-recreate` in `app-deploy`.** One word, and it recreates the entire stack on every deploy — including `postgres`, the one stateful service, for nothing. It would also change deploy behaviour for every application, since the script is generic.
- **`--force-recreate` scoped to the three services.** Better, but it recreates them on every deploy whether or not their configuration moved, and it puts knowledge of which services carry configuration into a script that is deliberately generic across applications.
- **Computing the checksum at deploy time** and passing it in through `.env`. This removes the maintenance burden entirely, and it is stronger than the chosen design on the one axis Decision 2 is anxious about: staleness becomes structurally impossible rather than merely detected, and impossibility beats detection wherever both are available. Note also that the Non-Goal above does not exclude it — `openspec/specs/iac-platform-deploy-pipeline/spec.md`, *Platform Secrets Rendered from CI at Deploy Time*, already has the deploy job render `.env` and ship it alongside the stack definition, so the digest could be computed there without touching the generic `app-deploy` script.

  It is rejected for one reason, stated precisely because the imprecise version is tempting and wrong: it is **not** that the configuration change would be invisible in the diff — the content is in the same file and is right there. What is lost is the *derived* fact of which services this deploy will replace, which is the consequence an approver acts on. A committed digest puts that in the diff.

- **Computing it at deploy time and printing the recreation set into the pre-approval summary.** This deserves recording because it defeats the reasoning above: `openspec/specs/iac-platform-deploy-pipeline/spec.md`, *Reviewer Sees the Exact Diff Before Approving*, already mandates a credential-free job that writes a summary before the approval gate, and running `docker compose config --hash='*'` against both sides there would show the approver exactly which services will be replaced — strictly more than a digest shows, since a digest says a value moved while a hash comparison says what will happen because of it.

  It is not chosen, on one ground only: under deploy-time computation nothing can ever be stale, so the requirement's third scenario becomes vacuous and the pull-request gate this change is half about disappears. The friction the chosen design pays is bounded — the check names the correct value — and a gate that fails before merge is worth more here than one that cannot fail. Recorded rather than dismissed, because a future reader weighing this again should start from the strongest version of the alternative.

### Decision 2: The checksum is verified statically, not trusted

A committed checksum that nobody regenerates is worse than no checksum, because it reads as protection while silently restoring the defect this change exists to fix — and it restores it in the same shape, a deploy that reports success and changes nothing.

So the `.github/tests` suite recomputes each label from the content it names and fails when they disagree. This is squarely within that suite's stated subject: a static read of a committed file, no network, no credential, no container runtime. The failure message must name the value the label should hold, because the alternative is an author who knows something is wrong and not what to write.

That check is also what makes the requirement's third scenario true — and that scenario says the discrepancy blocks the pull request, not merely that something reports it. It does: `.github/tests` is invoked by the required status check, and `TestTheSuiteIsWiredIntoTheRequiredCheck` in that suite already asserts as much, so a stale label cannot merge. Recorded here so a reader need not re-derive it.

Without this check the requirement would be satisfiable only by remembering, which is the property that failed here in the first place.

### Decision 3: The digest algorithm is fixed here, not left to the implementation

Two authors must independently arrive at the same value — the implementation writing the label and the derived-test author recomputing it — so every input is fixed here rather than discovered from the committed labels. Leaving any of it open would make `tasks.md`'s derive-from-the-spec rule unexecutable.

**SHA-256, hex, truncated to the first 12 characters.** The digest defends against forgetting, not against a forger, so collision resistance beyond a few bytes buys nothing; 12 characters is short enough to read in a diff and long enough that an accidental collision is not a practical concern. Truncation is fixed at 12 rather than described as "short" precisely so two authors agree.

**The input is, for each config the service mounts, in the order the service mounts them:** the config's name, a newline, its content, and a newline. Concatenated, then hashed.

Two clauses to remove the ambiguity that would otherwise land on whoever writes the test, since it is the one input they have no other guidance for. The **name** is the key under the top-level `configs:` mapping — not the service entry's `source:` (identical today, but it need not be) and not its `target:`. The **content** is the parsed scalar value of that config's `content:` key, as a YAML loader returns it — not the raw indented source text, which carries the block's own indentation and would make the digest depend on where in the file the block happens to sit.

Including the **name** is not decoration. Without it the input is a bare concatenation of contents, so moving a block from `prometheus_config` into `prometheus_rules` leaves the concatenation byte-identical — the label unchanged, the hash unchanged, the deploy green, and the original defect surviving in its original shape. The name is the delimiter that makes the framing unambiguous.

**Only that service's own configs.** This is what makes the requirement's second scenario true: editing a Grafana dashboard must not recreate Prometheus. A single digest of all eight configs shared across the three services would satisfy every other property this change asserts and quietly recreate the whole monitoring stack on every dashboard edit.

Hashing the whole service block instead was considered and rejected: it would churn the label on changes Compose already sees, adding diff noise and a second, redundant recreation trigger for something already covered.

## Risks / Trade-offs

**Every configuration edit now requires regenerating a label.** → This is real friction and it is the price of the guarantee. It is bounded by the static check catching it immediately with the correct value in the message, so the cost is one paste, not a debugging session. The alternative — deploy-time computation — trades this friction for the pull-request gate, which Decision 1 judges the worse trade.

**Delivery of the stack definition to the host is assumed, not established.** → The claim that Compose compared a *new* file and found equality rests on the delivery step exiting zero. It cannot rest on the matching `config-hash`, because old and new files hash identically — that is the defect itself, so the one measurement closest to the question is the one with no discriminating power here. If delivery is the real failure, this change ships and the next deploy again reports all nine `Running`.

Two things bound it. The labels make it self-diagnosing from the next deploy onward: once a label is in the definition, a running container either carries it or does not, and that single fact separates "not delivered" from "not recreated" — which no evidence available today can. And task 5.2 reads the deploy log for `Recreated`, so the alternative is falsified at the first deploy rather than left open.

**A rotated secret inside an embedded config moves nothing.** → Found in code review, and it is the one place the chosen mechanism is structurally unable to help. `alertmanager_config`'s content interpolates `${SLACK_WEBHOOK_URL}` and `${DEADMANSWITCH_URL}`, which `.github/workflows/platform-deploy.yml` renders into `.env` from GitHub secrets — so rotating the Slack webhook changes what Alertmanager would run with, while the committed text, the label derived from it, and Compose's own digest all stay exactly where they were. The container is not replaced and keeps the revoked webhook until something unrelated replaces it. Queue entry 47's deploy-time comparison does not catch it either: both sides of that comparison compute the same unchanged value.

No committed checksum can close this, because the value that changed is deliberately not in the repository. **This is the strongest argument for the deploy-time computation Decision 1 rejects** — a digest computed on the host, after interpolation, would move. It did not surface while the alternatives were being weighed, and it is recorded here rather than quietly left out, because it is the case a future reader reopening Decision 1 should weigh first. It is not acted on here: the requirement is scoped to the committed configuration and says so, and secret rotation is rare enough and manual enough that a deliberate replace is a reasonable interim. Queue entry 48 records it.

**A local hash cannot in general be compared with the host's.** → Found while verifying this change: four of the eight services — `grafana`, `postgres`, `postgres-exporter` and `traefik` — interpolate `${...}` from `.env` into their service blocks, and `.env` is not in the repository, so a local `docker compose config --hash='*'` computes them from empty values. Their hashes differ from the running containers' for that reason alone, with nothing wrong. `prometheus` and `alertmanager` interpolate nothing and are genuinely comparable — both matched the host exactly before this change, which is what made the original diagnosis possible — but `grafana` is not. The sound comparison is the file against its own parent commit in one environment, which is what task 4.4 does. Worth recording because the confounded comparison is the obvious one to reach for, and it looks like evidence.

**A recreated service may not come back healthy.** → These three containers have run continuously; this is the first cold start of their mounts, permissions and volumes in some time. Under `openspec/specs/iac-platform-deploy-pipeline/spec.md`, *Deploy Fails When Any Healthchecked Service Does Not Become Healthy*, the deploy then fails — the correct outcome, but it is an outage of monitoring rather than a no-op, and it lands on the deploy that follows this merge rather than on some later one.

**The first deploy after this merges recreates three services.** → Intended and disclosed in `proposal.md`'s Impact. Prometheus and Grafana keep their data on `/mnt/main-data`; Alertmanager loses only in-flight notification state. Worth saying plainly because it is the one deploy where this change looks like a larger event than it is.

**The label defends against forgetting, not against a wrong understanding of what Compose hashes.** → If a future Compose release starts including `configs:` content in the hash, this becomes redundant rather than wrong: the label still changes with the content, and the service is still recreated once. Nothing breaks; the mechanism is simply doing work that has become unnecessary.

**A service that gains a `configs:` entry later, with no label, is uncovered.** → The static check must therefore be written to discover config-carrying services from the file rather than to iterate a list of three names. Named here because it is the difference between a check that holds and one that holds until someone adds a service.

## Migration Plan

One commit's worth of change to `platform/docker-compose.yml` plus the static check. It reaches production through the existing gated pipeline.

There is no rollback concern beyond the ordinary: reverting removes the labels, which itself changes the service definitions and so recreates the three services once more, landing back on the previous configuration.

**Confirming the effect.** This change's own confirmation is unusually direct, because the thing it fixes is observable as a difference between two deploys:

1. Before merging, `docker compose config --hash='*'` over the branch's file and over its parent commit's, in one environment, shows exactly `prometheus`, `alertmanager` and `grafana` moved and the other five byte-identical. Not against the running containers: that comparison is confounded by `.env`, per the Risks entry above — an earlier version of this step prescribed it, and it is not performable.
2. The deploy's log shows `Recreated` for `prometheus`, `alertmanager` and `grafana`, and `Running` for the rest — the distinction that was absent from the deploy that exposed this.
3. Prometheus then serves the rules `alert-on-certificate-expiry` shipped: `/api/v1/rules` lists `TLSCertificateExpiringSoon` and `CertificateExpiryNotObserved`, and Alertmanager's `/api/v2/status` carries the route grouping on `cn`.

Step 3 is the real confirmation, and it belongs to this change rather than to that one: the rules are already committed and already on the host's stack definition, so their appearance proves the deploy applied shipped configuration. It simultaneously unblocks `alert-on-certificate-expiry`'s own confirm gate, which is why that change stays open until this one lands.
