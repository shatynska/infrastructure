# Change queue

Identified changes, recorded rather than opened. An entry is deleted when its
change is archived. See `AGENTS.md`, "A second change surfacing".

Everything here came out of a full-repository audit on 2026-09-06 (trunk at
`245ef59`). That audit's verdict was that the architecture is sound and needs
no restructuring; what follows is maintenance, not redesign.

Three of the audit's findings were ready to act on and were **opened** instead
of queued — they had branches and handoffs, not entries here:

- `fix-volume-discovery-and-consistency` — an unreachable assert, pin drift.
  **Archived 2026-09-07** (PR #66). It opened entries 3a, 3b, 3c and 3d. Only
  3b remains below: the other three were declined on their merits on
  2026-09-09 and are now in `docs/deferred-work.md`.
- `refresh-readme-accuracy` — README statements that are no longer true.
  **Archived 2026-09-08** (PR #76). It delivered the former entry 9, which is
  gone with it, and recorded entries 13 and 14 — both likewise declined on
  2026-09-09 and moved to `docs/deferred-work.md`.

`decide-archived-change-reference-policy` — the citation form live source uses
for this repository's own change records, and a check that enforces it.
**Archived 2026-09-07** (PR #70). It delivered the former entries 1 and 2, which
are gone with it, and unblocked entry 3. It also opened entries 8 and 8a; 8 was
delivered by `namespace-the-molecule-suite-per-working-tree` and is gone with
it, and 8a remains below.

Most entries below are queued because they are **blocked on something that must
happen first**, and they are listed in dependency order. Where an entry is not
blocked, it says instead why it was recorded rather than folded into the change
that found it — usually because it belongs to a different concern than the one
that change was closing.

---

## 3. separate-history-from-rationale-in-source-comments

**No longer blocked.** It waited on the citation-form decision and on the
sweep that followed it; both were delivered by
`decide-archived-change-reference-policy` (archived 2026-09-07, PR #70), which
also converted every citation in the comment blocks below. What remains here is
the separation this change deliberately did not do: it changed citation *form*
only, and left the prose around it alone.

Source comments in this repository currently mix three kinds of text with no
way to tell them apart:

- **why the code is shaped this way** — irreplaceable, keep it. The tailnet
  polarity note (`ansible/roles/tailscale/tasks/main.yml:76-82`) and the GHCR
  tolerated/not-tolerated block (the `ghcr_pull_*` comment block in
  `ansible/roles/deploy_user/tasks/main.yml`)
  are load-bearing and must survive any pass.
- **what a past change did** — git log and the archive already own this.
- **a TODO whose condition has passed** — dead, and quietly misleading.

Only the first kind survives archiving. Concrete instances of the other two
(the `platform/docker-compose.yml` header, formerly listed first, was removed
by `fix-volume-discovery-and-consistency`, which was editing that file anyway):

- `terraform/environments/prod/ssh_key.tf:20-28` — a `moved` block that
  documents its own removal condition ("Safe to delete once the next apply has
  run") from a change archived 2026-08-18.
- `terraform/environments/prod/main.tf:19-21` — explains a value the file no
  longer holds.

The tailscale role is 48 comment lines against 90 non-blank; this is a style
question with a real maintenance cost, not a cosmetic one.

## 3b. report-an-absent-tailscale-auth-key

**Not blocked on another change; recorded because doing it well is a larger
job than it looks, and doing it badly breaks the host's reachability.**

`fix-volume-discovery-and-consistency` added the requirement *A Role's Absent
Required Input Is Reported by Name* (`iac-host-configuration`) and satisfied it
for `hardening_ssh_allowed_cidrs` and `deploy_apps`. That requirement is
deliberately scoped to inputs a role consumes on **every** run, and this entry
is the class it excludes.

`ansible/roles/tailscale/defaults/main.yml` documents `tailscale_auth_key` in
almost the same words as the two variables that were fixed, which is what makes
this look like an oversight rather than a decision. It is not. The key is
consumed only inside `Bring the host onto the tailnet`, guarded by a `when:`
that skips when the host is already on the tailnet — so a re-converge of the
prod host, the common case, never evaluates it and does not need it supplied.
An unconditional assertion would start demanding it on every run and break a
working path.

Three things make this its own change rather than a fold-in:

- The diagnostic has to fire under the **same** condition as the join, which
  means naming that four-limb condition once instead of restating it. Its
  `POLARITY` comment warns that reading it the wrong way silently stops a host
  joining the tailnet — the mechanism the deploy pipeline depends on to reach
  the host at all.
- `tailscale` carries **no Molecule scenario**, so there is nothing to regress
  against. Any change here should bring the role's first scenario with it.
- The failure is currently *censored*: the consuming task sets `no_log: true`,
  so an absent key surfaces as a redacted error rather than a named one. That
  is worth fixing on its own merits and is invisible from the outside.

Recorded by `fix-volume-discovery-and-consistency`, whose `design.md`
Decision 3a carries the full reasoning.

## 11. matrix-the-molecule-suite-over-scenarios

**Not blocked; recorded rather than folded into
`promote-molecule-to-a-required-check`**, whose proposal names it as a non-goal.
That change decides which job is required and reshapes the workflow's triggers;
this one changes what a job *is*. Landing both in one diff would mean the
change that picks the registered context also redefines the thing being
registered.

`molecule test --all` runs a role's scenarios in sorted order and **stops at the
first failure**. Every scenario sorting after a failing one is neither executed
nor listed in that run's SCENARIO RECAP, so a red run establishes less than it
appears to and the recap still looks complete. Molecule's own remedy is
unavailable here: `--continue-on-failure` applies only with `--workers`, and
`--workers > 1` refuses with `only supported in collection mode (galaxy.yml
required)` — these are plain roles, not a collection (observed 2026-09-07).

Not to be confused with the shared-state hazard, which was a different cause
with an overlapping symptom and is now closed: instance names and the ephemeral
directory are namespaced per working tree, and `AGENTS.md`'s *Namespacing
Molecule per working tree* is the binding. What remains here is Molecule's own
stop-at-first-failure behaviour, which namespacing does not touch.

The remedy that works is a continuous-integration matrix over **scenarios**
rather than roles. Each scenario becomes its own job, so one failing scenario
stops only itself and the rest still report. It also parallelises the suite's
longest role, which carries three scenarios and is what sets the workflow's
wall clock.

**What promotion changes about its priority, in both directions.** A red
required check that under-reports is slower to diagnose — you fix one scenario,
push, and wait six minutes to discover the next one. That is an argument for
doing this. Against it: the gate is not weaker for under-reporting. A red check
blocks the merge whether or not it enumerated every failure, so this is about
the cost of diagnosis rather than about the guarantee.

Two things it must not undo, both in
`openspec/specs/iac-cicd-pipeline/spec.md`. *Required Status Checks Report on
Every Pull Request* forbids registering a job whose name is generated from a
matrix — a per-scenario matrix generates more of those names, not fewer, so the
literal-named aggregating job stays and keeps concluding on their behalf.
*Ansible Configuration Is Verified in Continuous Integration and Gates the
Merge* requires discovery rather than enumeration, so scenario discovery must
find `ansible/roles/*/molecule/*/` without a workflow edit, and must keep
failing loudly on an empty result.

Worth noting that the per-job cost changes shape: each scenario job pays its own
checkout and toolchain install, which the current per-role jobs amortise across
a role's scenarios. Whether that is cheaper overall is an empirical question
this entry does not answer.

## 6. two-deferred-ci-items

Both noticed during `close-ci-verification-gaps`, neither a verification gap:

- **`.github/workflows/pre-commit-autoupdate.yml` installs `pre-commit`
  unpinned** (`pip install pre-commit`). That change created
  `.github/requirements-ci.txt`, which pins it; bringing this workflow onto the
  same file is a one-line fix in a workflow that change did not otherwise
  touch.
- **The destroy-policy gate's inspection logic is inline workflow shell.**
  Moving it into a version-controlled script with executable fixtures would
  make the highest-consequence logic in this repository reviewable and testable
  as code — `design.md` Decision 5 of that change names this as considered and
  deferred on merit-vs-scope grounds, not as rejected. Four fixtures already
  exist (clean, destructive, malformed, valid-JSON-that-is-not-a-plan) and are
  described in that change's `tasks.md` 1.1; the structural tests in
  `.github/tests/test_ci_configuration.py` currently assert the routes are
  closed, not that each is reached.
- **`actionlint` is named as a verification means but nothing installs it.**
  Three tasks in `close-ci-verification-gaps` cite it, and it was run manually
  from a scratch install. Adding it to `.pre-commit-config.yaml` would close
  that permanently — but it exits non-zero on two pre-existing `SC2016:info`
  findings (`pr-validation.yml`, the plan-comment step; `apply.yml`, the
  job-summary step — both single-quoted literal markdown in an `echo`, and both
  intentional). So landing the hook means dispositioning those two first,
  by fixing or ignoring them. That is the same trap this change refused to lay
  for the next person when `ansible-lint` failed on pre-existing violations,
  and it wants its own decision rather than being folded in.

## 8a. a review agent's mutation check writes to the tree it is reviewing

**Not blocked. Recorded beside the Molecule shared-state entry, since deleted by
`namespace-the-molecule-suite-per-working-tree`, because it is the same class of
hazard — a shared handle nobody namespaced — and was found the same day. This
one is untouched by that change: the shared handle here is the working tree
itself, between a session and its own review agent.**

The `code-review` skill performs mutation checks against the **live working
tree**: it appends a violation to a real file, confirms the gate goes red, then
reverts. Observed 2026-09-07 during `decide-archived-change-reference-policy`'s
code-review gate, on `platform/README.md`.

The revert restored the file to its **committed** content, not to the
working-tree content it had displaced. The change under review was a 45-file
sweep of uncommitted edits, so the revert silently undid the sweep in that file
and restored six pre-archive citations. The stash list and the reflog showed
nothing, because neither a stash nor a branch checkout was involved, which is
why the cause took a while to find.

Two things follow, and only the first is about this incident:

- **A review agent that writes to the tree can destroy the work it is
  reviewing**, and does so in a way that looks like nothing happened. The
  working tree is a shared handle between a session and its own review agent,
  exactly as the container name is between two Molecule runs.
- **The mutation check itself is sound and worth keeping.** Appending a
  violation and confirming the gate goes red is what distinguishes a check that
  reads the tree from a tautology. What is wrong is performing it in place. It
  belongs against a copy, or must restore the content it displaced rather than
  the committed content.

Worth deciding whether this project constrains review agents to a read-only
tree, or accepts in-place mutation checks and requires the dispatching session
to verify the tree afterwards. In this instance the change's own new check
caught the regression unprompted and named all six restored citations by file
and line — which is evidence for that check, not a reason to assume one exists
next time.

## 7. size-platform-container-resource-limits

**Blocked on data, not on another change.** No service in
`platform/docker-compose.yml` declares a memory or CPU limit, on a `cx33`,
while `ContainerRestartingOrOOMKilled` alerts on the consequence. A single
container can currently starve the host.

Limits picked without evidence are guesses that cause the outage they were
meant to prevent. The monitoring stack now collects exactly the data needed —
`container_memory_usage_bytes` by container, already on the "Container health"
dashboard. Let it run long enough to show real steady-state and peak, then size
from observation.

## 15. alert when the host prune stops working

**Blocked on nothing.** `prune-unreferenced-host-images-periodically` shipped
on 2026-09-08; this is the gap it named and deliberately left open.

`prune-host-images` reports on every exit path and leaves a failed systemd unit
when it abandons. Nothing scrapes either. `systemctl list-units --failed` is a
manual read, and the outer backstop is `HostDiskPressure` at 90% full, which is
very late — a prune that has silently done nothing for two months is invisible
until the disk is nearly gone.

Closing it needs node-exporter's textfile collector: a `--collector.textfile.directory`
flag and a mount in `platform/docker-compose.yml`, the prune writing a `.prom`
file, and an alert on staleness rather than on failure — a unit that stops being
scheduled at all produces no failure to alert on. That is a `platform/` change,
which is why `prune-unreferenced-host-images-periodically` named it a non-goal
rather than folding it in.

## 16. report refused removals in the host prune

`prune-host-images` reports `considered N, removed M`, where `considered` is
every distinct image identity on the host rather than a candidate set. A
shortfall between the two therefore carries no signal: a defective keep set
prints `considered N, removed 0`, byte-identical to a healthy run over a host
where everything is referenced.

`app-deploy`'s own reclamation comment calls that shortfall "a signal worth
reading". Here it is unreadable. Counting refusals and reporting them would make
a defective keep set legible without changing any removal behaviour.

Recorded rather than folded into `prune-unreferenced-host-images-periodically`
because it adds a field to a report
the delta specifies exactly, and that is a specification change, not an
implementation detail.

## 17. adopt the stubbed-runtime rig for the two guards Molecule cannot reach

`prune-unreferenced-host-images-periodically` shipped two guards that no
assertion covers: local images are enumerated
*before* the keep set is computed, and each tag is re-resolved immediately
before removal. Both are observable only when the host's images change midway
through a run, and a black-box Molecule scenario has no seam at which to change
them. They are also the two that close the concurrent-deploy window against
`app-deploy`, so the least-verified part of that design is the part facing the
only actor competing with it.

Its code review built a rig that supplies the seam — a stubbed `docker` on
`PATH` that answers some calls and fails others — and used it to confirm both
guards present and mutation-visible, and to reproduce the fail-open that review
found. Its `test-plan.md` invites exactly this: "if a deterministic arrangement
is found for either — sized rather than slept — add it to `tasks.md` 2.7 and 2.8
together and strike it from here."

Adopting it would also cover the two abandon branches added by that review's
own fix, which are likewise unasserted.

---

The entries from here to 31 came out of a second full review on 2026-09-08
(trunk at `74c7101`), made to judge whether this repository's shape can be
reused for a second, company-owned host. It opened with 19 and 20 — logical
off-host backups of the shared database, and a decision on the database model —
and both are gone from this file, resolved together by
`scope-the-shared-database-to-non-durable-data`: reading the host showed the
instance those entries argued over holds no application data at all, and
that what this host needs is a stated boundary rather than a backup
pipeline. Entries recorded after that review continue the numbering.

Only what applies to **this** host too is recorded here; the company-only
findings (repository visibility, a second approver, an
organisation-owned repository) are not this repository's concern. The review's
verdict repeated the first audit's: the architecture is sound, and what follows
is operational rather than structural. It read the live host as well as the
tree, so where an entry cites a host fact, that is what `main-server` showed on
2026-09-08, not an inference from the code.

## 23. apply-host-configuration-through-a-gated-workflow

**Not blocked; recorded because it is the one path to production this
repository still leaves to a workstation.**

`ansible/playbooks/host-baseline.yml` is applied by hand: no workflow runs
`ansible-playbook` against prod, the Vault password lives only on the
operator's machine, and the `tailscale_auth_key` is supplied at the prompt.
`AGENTS.md` says nothing ships from a local machine and that local production
credentials are for reading, and the Terraform and platform layers honour it;
the host layer does not, and a converge that changes UFW rules or authorized
keys is at least as consequential as a Compose change.

The shape already exists twice in `.github/workflows/`: a credential-less job
that shows the reviewer what will change (`ansible-playbook --check --diff`
against prod, over the tailnet, with the read-only Hetzner token for
inventory), then a `production`-gated job that applies it. It needs the Vault
password and the tailnet auth key as Environment secrets, an SSH identity
for `root` that is not the operator's personal key, and a decision about
whether `--check` output is reviewable enough to approve on. That last is the
part worth thinking about; the rest is plumbing.

## 24. make-the-pipeline-environment-agnostic-before-adding-staging

**Not blocked; recorded because the README's "anticipated next environment"
is further away than it reads.**

`terraform/modules/` are parameterised for a second environment, and the
README says staging is "a second `terraform/environments/<name>/` folder
reusing the same modules". The pipeline does not agree. `apply.yml`,
`drift.yml` and `pr-validation.yml` each hardcode
`working-directory: terraform/environments/prod`; `host-baseline.yml` runs
against `hosts: prod`; `group_vars/prod.yml` carries the host's CIDRs and
application list by name. A second folder would be validated by `terraform
validate`'s discovery loop and applied by nothing.

The work is a matrix or a discovery loop over `terraform/environments/*/` in
the three workflows, a per-environment `production`-style GitHub Environment
so staging can be applied without prod's approver and prod's token, and the
same for the playbook. It also needs a decision on whether staging is a second
Hetzner server (a second `server_type` line and a second bill) or a second
project. Worth doing before the first change that would benefit from being
rehearsed -- a PostgreSQL major upgrade is the obvious one.

## 25. close-public-ssh-and-manage-sshd-explicitly

**Not blocked; a policy decision the hardening role already anticipates.**

Port 22 is open on the cloud firewall and in UFW from one ISP `/24`
(`ssh_allowed_cidrs` in `terraform.tfvars`, mirrored in `group_vars/prod.yml`).
The tailnet rule in `ansible/roles/hardening/tasks/main.yml` admits SSH from
`100.64.0.0/10` independently, and that task's own comment says an empty
public CIDR list "is safer than what prod runs". Every non-operator path (the
deploy jobs) already uses the tailnet; the public rule exists for the
operator alone, and the operator is on the tailnet too.

Closing it is `ssh_allowed_cidrs = []` -- except that `modules/server`'s
validation refuses an empty list on lockout grounds, which was the right
default before the tailnet existed and is the thing to revisit now. The
Terraform firewall rule and the UFW rule move together (the *Host-Level
Security Owned by Ansible, Cloud Firewall Owned by Terraform* requirement's
sync obligation), and the change should say what the recovery path is if the
tailnet is unreachable: Hetzner's console, which the cloud firewall does not
gate.

Two smaller things in the same area, neither managed by any role today, both
running on the image's defaults: `sshd_config` (the host has no drop-in under
`/etc/ssh/sshd_config.d/`; `PasswordAuthentication` is unset, harmless only
because no account has a password) and `unattended-upgrades` (installed and
enabled by the image, not by `hardening`, with no `Automatic-Reboot` decision
recorded). Both belong to the hardening role, and both can be asserted by its
Molecule scenario.

## 27. check-public-endpoints-from-outside

**Not blocked; recorded because the monitoring stack watches the host and not
the customer's path to it. Narrowed on 2026-09-09 by
`alert-on-certificate-expiry`, which delivered the certificate-expiry half.**

The dead-man's switch proves Alertmanager is alive. `MetricsTargetDown` proves
the exporters are. `ApplicationHighErrorRate` needs requests to reach Traefik
before it can count them. Nothing checks, from outside the host, that a public
hostname resolves and answers on 443.

**What was delivered and is no longer in scope here.** A certificate quietly
ageing out was the third of the three failures this entry named, and it turned
out to need no probe at all: Traefik publishes `traefik_tls_certs_not_after`,
Prometheus was already scraping it, and one alert rule now reads it. What
survives of that failure is only the half no metric can express -- a hostname
resolving to this host with **no** certificate at all, which produces no series
because Traefik's default self-signed certificate is not published as one.
`shatynska.com` and `www.shatynska.com` are in exactly that state today, by
design, because no application is bound to them yet.

**`blackbox-exporter` cannot serve this entry's own motive**, which is the
finding that most changes what remains. It runs on the host, and a packet
addressed to an IP configured on a local interface is delivered locally -- so a
probe from the host to the host's own public address never traverses the Hetzner
cloud firewall, which filters ingress at the network edge. The cheaper of the
two shapes this entry offered cannot see the firewall failure it was offered
for. It would still catch a routing mistake and would measure what a client is
actually served rather than what Traefik believes it holds; neither is the same
thing as looking from outside.

**The two failures that remain, stated more accurately than this entry stated
them.**

*A cloud-firewall change blocking 443* is gated in one of at least three ways it
can close, not in all of them. `web_allowed_cidrs` reaches production only
through the gated pipeline, where a human reviews the exact plan -- but
`AGENTS.md`'s firewall split makes UFW the co-equal host-level layer, entry 23
records that the playbook applying it is run by hand with no gate at all, and
entry 32 records that a console-side change is caught only by a drift workflow
that itself fails into silence. An outside check is the only thing that would
see the other two.

*A DNS mistake* is not bounded by how often the zone is hand-edited.
`docs/deferred-work.md` records that `shatynska.com` is served by third-party
nameservers at ukraine.com.ua, so a provider outage or a lapsed registration is
a DNS failure with no edit behind it -- and it is exactly the "invisible until a
person notices" class this entry was recorded for.

**So what is left is an external uptime service**, with a check per hostname,
independent of the host in the way the Watchdog is. Note that the assumption
this entry made about it is probably false: the heartbeat provider named in
`docs/bootstrap-a-new-host.md` is healthchecks.io, which monitors inbound pings
and does not make outbound HTTP checks. This is likely a second vendor account
and therefore an operator decision with a cost attached, which is the main
reason it is still queued rather than opened.

## 28. aggregate-container-logs

**Not blocked; lowest priority in this batch for a host running one
application, and the first thing missed when it runs several.**

Logs are read by `docker logs` over SSH as `ops-claude`, per container, and
are lost when a container is recreated -- which every deploy does. Alerts say
*that* a container restarted; the reason is in the log that just went away.

Loki with an Alloy (or Promtail) collector reading the Docker socket is the
stack-native answer: it joins `platform_monitoring`, Grafana already has the
datasource provisioning pattern, retention is bounded the way Prometheus's is,
and it stores on `main-data` under a `platform_data_volume_subdirs` entry the
way Prometheus does. Entry 21 is a prerequisite in spirit: the collector reads
the same json-file logs that today are unbounded.

## 29. set-traefik-wide-defaults-for-redirect-and-tls

**Not blocked; small, and it removes a class of application mistake.**

Traefik's `web` entrypoint (80) is open and serves whatever an application
routes there; there is no entrypoint-level redirect to `websecure`, and no
default `certresolver`. Every application's Compose file must therefore repeat
`entrypoints=websecure` and `tls.certresolver=letsencrypt` on each router, and
one that forgets is served over plain HTTP with no signal. commerce-ops sets
both; the next application may not.

`--entrypoints.web.http.redirections.entrypoint.to=websecure` and
`--entrypoints.websecure.http.tls.certresolver=letsencrypt` on the Traefik
service make the safe form the default and the labels optional. While there,
Traefik's access log is off; turning it on (to stdout, where the host's daemon
now bounds it -- see *Container Logs Are Bounded by the Host's Daemon
Configuration* in openspec/specs/iac-host-configuration/spec.md) is what makes
entry 28 useful for HTTP traffic.

## 30. write-and-rehearse-the-rebuild-runbook

**Not blocked; recorded because every piece exists and nobody has run them in
sequence.**

Recovering this host from nothing is: a Terraform apply through the gated
pipeline (with `server_enabled` toggled, and the destroy-override label for
the replace), DNS (a manual edit at ukraine.com.ua — the records are listed
under "Managing DNS in Terraform" in `docs/deferred-work.md`, which is where
the automation of this step was declined), a hand-run Ansible converge with the Vault
password and a fresh tailnet key (entry 23), the platform deploy from a re-run
of `platform-deploy.yml`, one deploy per application from its own repository,
the two manual steps `platform/README.md` lists (the `pgexporter` role and the
dead-man's-switch registration). No *platform-stack* store needs restoring:
`scope-the-shared-database-to-non-durable-data` classified each of them as
needing no backup — each is either recreated by a redeploy or its loss is
accepted, and the runbook should say which, because Prometheus's history and
Grafana's UI-created state fall in the second group and do not come back.
That leaves one gap, and it is the one the same change names as a divergence —
`commerce-ops` keeps durable data in a PostgreSQL container of its own that
nothing backs up, so a rebuild today loses it. Entry 33 is what closes that;
until it does, the runbook has to say so. Those steps live
in four repositories and two README sections, in no stated order, and the
time they take is unknown.

A `docs/runbook-rebuild.md` that lists them in order, names the secret each
step needs, and records the last rehearsal's date and duration is the
deliverable. The rehearsal is the point; the document is how it survives.
Entry 24's staging environment is where the rehearsal can happen without
touching prod.

## 32. notice-a-scheduled-workflow-that-goes-red

**Not blocked.** Recorded by `open-autoupdate-pr-with-app-token`, whose
`design.md` names it a non-goal.

That change repairs `pre-commit-autoupdate.yml`, which had failed on every one
of its last three scheduled runs -- 2026-08-24, 2026-08-31, 2026-09-07 -- with
`GitHub Actions is not permitted to create or approve pull requests`. Each
failure was red in the Actions tab and each sent GitHub's own failure email to
the workflow file's last committer. Three weeks passed anyway. The signal
existed and did not work.

That is not a property of the workflow being repaired, and repairing it changes
nothing about the next one. `drift.yml` runs nightly and `image_prune` runs
weekly; both fail the same way, into the same silence. Entry 15 (*alert when the
host prune stops working*) is the same concern reached from the host side and
wants reconciling with this rather than solving twice -- the question is
plausibly one mechanism covering every scheduled workflow, not one alert per
workflow.

It was not folded into `open-autoupdate-pr-with-app-token` because its blast
radius is every scheduled workflow in the repository rather than the one being
fixed, and because that change can be confirmed without it: its own confirm gate
is a pull request that opens and reports its checks, which is observable
directly.

Worth deciding as part of it: whether the dead-man's-switch this project already
runs for single-host observability is the right place, or whether a failing
GitHub Actions run wants its own path.

## 33. move-commerce-ops-durable-data-to-supabase

**Not blocked, and not this repository's to do — recorded because
`openspec/specs/iac-safety-hardening/spec.md` now names it as a divergence and
nothing else tracks it.**

*No Store on This Host Holds Data Requiring Backup* classifies every store on
this host as needing no backup, and states one exception: `commerce-ops` keeps
durable data in a PostgreSQL container of its own, on its own `app_db` network.
On 2026-09-08 that database held 12 MB. Most of its rows are transient —
roughly 17,000 across the `procrastinate_*` queue tables, which are exactly the
non-durable class the shared instance exists for — but the part that matters is
small and hand-curated: 358 `playbook_steps`, 35 `launch_journal_entries`, 26
`launch_clickup_tasks`, 11 `roles`, 8 `role_holders`, 7 `known_work`, 5
`products`. Nothing backs any of it up. The daily Hetzner snapshot covers the
root disk the volume sits on, crash-consistently, restorable only by rolling the
whole server back.

The resolution is that the application's durable data moves to Supabase, which
owns its own backups. That is work in the commerce-ops repository, over which
this repository has no authority — which is the reason this entry exists rather
than a task somewhere.

**Resolving it takes two steps, and the second has no other owner.** The
migration, there; and the deletion of the divergence paragraph from *No Store on
This Host Holds Data Requiring Backup*, here. No change in this repository would
otherwise prompt the second, so a completed migration would quietly leave the
specification describing a divergence that no longer exists.

Worth knowing for whoever takes it: the migration is not all-or-nothing. The
`procrastinate_*` tables could legitimately stay on this host, in the shared
instance, under the scoping that requirement now records.

## 35. catch-up-the-drifted-galaxy-pins

**Not blocked.** Recorded 2026-09-08, from an inventory taken while archiving
`open-autoupdate-pr-with-app-token`.

`ansible/requirements.yml` pins five things. Two are current; three are behind
by at least a major version:

| Collection | Pinned | Latest on 2026-09-08 |
|---|---|---|
| `hetzner.hcloud` | 7.0.0 | 7.0.0 |
| `geerlingguy.docker` (role) | 8.0.0 | 8.0.0 |
| `community.general` | 9.5.0 | 13.4.0 |
| `ansible.posix` | 1.6.2 | 2.2.2 |
| `community.docker` | 4.1.0 | 5.3.0 |

This is the most drifted manifest in the repository, and it is the one no tool
watches: Dependabot has no `ansible-galaxy` ecosystem, so unlike the Terraform
and Actions pins nothing has ever proposed a bump here.

Four majors is a migration rather than a version bump, which is why this is an
entry and not a rider on anything. The collections are used by the hardening
role (`community.general.ufw`), `deploy_user`
(`ansible.posix.authorized_key`'s `key_options`, `community.docker.docker_login`)
and the dynamic inventory. Molecule is the check that would catch a break, and
`molecule test --all` per role is the gate this change has to pass -- read the
SCENARIO RECAP rather than the exit code, per the note in `AGENTS.md`.

**Also delete the stale caveat while here.** Four of the five pins carry a
comment saying the version "was chosen without the ability to query Galaxy from
this environment (no network access) -- confirm it resolves". All five were
confirmed against the Galaxy API on 2026-09-08 and every one resolves. The
comment is now false where it is not merely stale, and it invites the next
reader to re-do work that has been done.

## 36. cover-the-pip-manifests-with-dependabot

**Not blocked; the same shape as `cover-platform-images-with-dependabot`** —
the former entry 31, deleted from this file when that change landed.

**Do not inherit that entry's estimate.** It called itself "a one-stanza change
in `.github/dependabot.yml`" and was not one: *Automated Dependency Updates*
(`openspec/specs/iac-safety-hardening/spec.md`) enumerates its ecosystems by
name and the CI-configuration suite reads that enumeration back, so a fourth
ecosystem is a stanza **plus** a specification delta widening that enumeration
**plus** the tests that hold it. Budget for the same here.

Dependabot watches `terraform` and `github-actions`. Nothing watches the five
pip pins: `.github/requirements-ci.txt` (`pre-commit==4.6.2`, `PyYAML==6.0.1`)
and `ansible/requirements-test.txt` (`ansible-core==2.21.3`, `molecule==26.8.0`,
`molecule-plugins[docker]==26.7.15`). Dependabot's `pip` ecosystem reads both
file shapes.

Lower stakes than the platform images were -- these are the test and CI
toolchain rather than production services -- but the cost is a few lines and
the alternative is the same "when a person notices" that entry 35 is the
consequence of.

Note the ordering constraint against entry 35: `ansible-core` is pinned here and
the collections are pinned there, and the two are a matched set --
`ansible/requirements-test.txt`'s own comment records that the toolchain was
"verified together, in this combination, on Python 3.12". A Dependabot bump of
`ansible-core` landing mid-migration would confuse which half broke.

## 37. decide-renovate-versus-dependabot

**Not blocked, but deliberately deferred.** Recorded 2026-09-08 with a
recommendation attached, so that revisiting it starts from a position rather
than from scratch.

Seven manifests in this repository carry pins. Four are watched -- the Terraform
lockfiles and Actions refs by Dependabot, `.pre-commit-config.yaml` by the
workflow `open-autoupdate-pr-with-app-token` repaired, and the eight
`platform/docker-compose.yml` images by the `docker-compose` ecosystem
`cover-platform-images-with-dependabot` added (this was the former entry 31,
unwatched when this entry was written). Three are not: the five galaxy pins
(entry 35) and the five pip pins across two files (entry 36).

Renovate has native managers for all seven, including `pre-commit` and
`ansible-galaxy`, which Dependabot has for neither. One tool and one config
would close every gap and retire the bespoke workflow.

**The recommendation is to stay with Dependabot, for now,** and it is stronger
than when written: one of the two gaps this paragraph counted on configuration
to close has since been closed that way, by
`cover-platform-images-with-dependabot`, with no new trust relationship. Entry
36 closes the other on the same terms. What Renovate uniquely adds is the
galaxy manager -- and entry 35
argues that a four-major backlog wants a deliberate migration, not a bot
proposing it. Hosted Renovate is also a third-party application with write
access, which cuts against the reasoning already recorded in the
*Automated Dependency Updates* requirement about third-party supply-chain risk.

Self-hosted Renovate is the interesting middle: it would reuse the
`infrastructure-autoupdate` GitHub App, which is already scoped to Contents and
Pull requests on this repository alone, so no third party gains write access and
the credential work is done. The generalised requirement was written to permit
exactly this -- *any* workflow opening a pull request, not just the hook-update
one.

**Revisit when** a second Compose stack appears, or the galaxy manifest grows
past a handful of entries, or entry 35's migration is done and the small
incremental bumps it will then need start being missed again. The single-config
argument strengthens as the manifest count rises; at four unwatched manifests it
does not yet carry the trust cost.

**Do not revisit before entry 32.** Adding a fifth automation to a repository
where nothing notices a red scheduled run makes the observability gap worse, not
better -- which is the lesson `open-autoupdate-pr-with-app-token` was.

## 38. upgrade-the-shared-postgres-major

**Not blocked; recorded rather than opened because it needs a maintenance
window and a deliberate volume reset, neither of which a version-bump pull
request can carry.** Recorded 2026-09-08, when Dependabot proposed it and the
proposal was closed.

`platform/docker-compose.yml` pins `postgres:16.15`. Dependabot's first run
after `cover-platform-images-with-dependabot` landed proposed **18.6** (PR #91,
closed unmerged). Taking that proposal as an ordinary bump does not work, and
the reason is worth writing down once:

PostgreSQL refuses to start against a `PGDATA` initialised by an earlier major
version. It does not upgrade in place and it does not damage the directory --
it exits. So a merged bump reaches the host, `docker compose up -d --wait`
blocks and then fails, the deploy job goes red, and the shared instance is down
for every application on the host until someone intervenes. Loud, and not data
loss.

**What makes this cheap here, and why it is still not automatic.** The shared
instance holds no durable data: *No Store on This Host Holds Data Requiring
Backup* (`openspec/specs/iac-safety-hardening/spec.md`) classifies
`postgres_data` as non-durable by policy, and *Single Shared PostgreSQL
Instance, Per-Application Databases*
(`openspec/specs/iac-platform-services/spec.md`) admits no durable data into it
at all. So the upgrade path is legitimately "stop the stack, discard the
volume, redeploy, let the instance re-initialise" rather than a `pg_upgrade` or
a dump-and-restore. That is a decision an operator takes in a chosen window,
with the applications that use the instance told first -- not something that
happens because a bot opened a pull request on a Tuesday.

Note the divergence this does **not** cover: `commerce-ops` runs its own
PostgreSQL container with durable data in it (entry 33). Nothing here touches
that one, and this entry must not be read as a template for it -- discarding
*that* volume loses data.

**No `ignore` stanza was added, deliberately.**
`cover-platform-images-with-dependabot`'s design.md Decision 3 argued this: an
`ignore` is permanent and silent, and would suppress the only signal this
repository gets that its PostgreSQL major has reached end of life. Closing an
individual pull request keeps the signal -- Dependabot will propose the next
major release when one appears, and closing it again costs nothing. Expect a
recurring, correctly-refused pull request; that is the design working, not
noise.

**Do first**: check whether any application is by then storing something in the
shared instance that it would rather not lose, in which case the answer is that
it should not have been (see the requirements above) and that is the thing to
fix, not the upgrade.
## 39. exercise-the-volume-server-coupling-against-live-state

**Not blocked; recorded because an archived change is where it would be lost.**
Recovered 2026-09-08 by `make-openspec-validation-a-usable-gate` while settling
the red archived records. `add-prod-data-volume`'s task 3.5 was left unticked
with the note *"Still open; consider doing this as a follow-up plan-only check"*
— real outstanding work, sitting in prose inside a change that had already been
archived, which is precisely where nobody would look for it. That task is now
disclosed under that change's `## Not performed`; the work it names is here.

`environments/prod` couples the volume to the server:
`count = var.volume_enabled && var.server_enabled ? 1 : 0`, so the volume cannot
outlive the server it derives its location from. **That coupling has never been
exercised against live state.** `terraform/modules/volume/tests/*.tftest.hcl`
cannot reach it — the coupling lives in the environment, not the module, and the
module's tests do not evaluate the environment's `count` expression.

Two plan-only reads, **never applied**:

- Set `volume_enabled = false` (uncommitted) and re-plan: the volume is planned
  for destruction and nothing else changes.
- Restore it, set `server_enabled = false` instead, and re-plan: the plan
  destroys server, firewall **and** volume together.

Revert both local edits afterwards. Use the read-only Hetzner token; this is a
`terraform plan` and never a `terraform apply`, per this project's rule that
production changes reach Hetzner only through the gated pipeline. A destroy plan
run locally reads state and proposes; it changes nothing.

The requirement this protects is *Conditional Prod Volume Creation* in
`openspec/specs/iac-data-volumes/spec.md`, and the two reads above are literally
its scenarios *Volume toggle disabled creates nothing* and *Disabling the server
also removes the volume* — both of which say `terraform plan` SHALL show the
volume planned for destruction. The specification states them; nothing has ever
run them.

Worth doing before the coupling is next relied on — a volume that survived its
server would be an orphaned resource with no location, which is the failure the
coupling exists to prevent and which nothing has yet observed being prevented.
## 40. alert-on-swap-utilisation

**Not blocked; recorded rather than folded into
`bound-host-log-growth-and-add-swap`, which is the change that gives this host
swap in the first place.** That change is host-level Ansible; this one is a
`platform/` Compose change reached by a different pipeline, and folding it in
would have made a single change need two deploys.

Once swap exists, "swap is 80% consumed" is the signal that a leak is underway
and the OOM killer is next. Nothing says it. `node_memory_SwapFree_bytes` and
`node_memory_SwapTotal_bytes` are already scraped -- node-exporter has been
running since `add-platform-monitoring` -- so the rule is a few lines beside
the seven already inline in `platform/docker-compose.yml`.

**What this adds is the explanation, not the detection.** `HostMemoryPressure`
is computed from `MemAvailable / MemTotal`, which is RAM only and unaffected by
swap existing, so a leak still drives it over 90% and still fires after ten
minutes. What that alert cannot say is *why*, and on a host that now has a
last-resort tier the difference between "memory is tight" and "the reserve is
being consumed and there is nothing after it" is the difference between a
warning and a countdown.

Worth deciding at the same time whether the threshold is a level (swap above
some fraction) or a rate (swap consumed per unit time). A level fires late on a
slow leak and a rate fires spuriously on a legitimate burst; this host has no
history of either yet, which is a reason to pick the simpler one and revisit.

**Do not size it before entry 7.** Container memory limits change what swap is
ever asked to absorb, so a threshold chosen now describes a host that is about
to change.

## 41. assert-every-role-has-a-mock_roles-entry

**Not blocked; recorded rather than folded into
`bound-host-log-growth-and-add-swap`, which is the change that hit it.** Adding
the missing entry belonged to that change; asserting the invariant is a
different concern, and the `.github/tests` suite is not that change's subject.

`.ansible-lint`'s `mock_roles:` hand-enumerates every role referenced by name,
because ansible-lint does not resolve role references through
`ansible/ansible.cfg`'s `roles_path` the way `ansible-playbook` does. The file's
own comment says so. What it does not say, and what nothing enforces, is that
the list must be complete: a role added under `ansible/roles/` and referenced
from `ansible/playbooks/host-baseline.yml` without a matching entry fails
`ansible-lint` with a false-positive "role not found" -- twice, once for the
playbook and once for the role's own `converge.yml`.

Observed 2026-09-08 while adding the `swap` role. The diagnostic names a
search path that does not include `ansible/roles/`, which reads as a
configuration problem rather than as a missing line in a list, so the time is
spent in the wrong file.

This is a **static read of a committed file** -- the set of directories under
`ansible/roles/` minus the gitignored external role, against the `mock_roles`
list in `.ansible-lint` -- so it fits the `.github/tests` row exactly: no
network, no credential, no container runtime, no Terraform binary. It is the
same shape as the existing "every lockfile-bearing directory is covered" check.

Worth doing because the cost is paid by whoever adds the *next* role, not by
whoever left the list short, and because the failure arrives as a message
pointing somewhere else.

## 42. commit-derived-tests-before-folding-them

**Not blocked; small, and about the workflow rather than about any code.**
Recorded by `bound-host-log-growth-and-add-swap`, whose code review found it.

`AGENTS.md` has an author other than the implementer derive tests from the
approved delta specs. That author may not edit an existing test file, so when
the tests a change needs belong in one, they arrive as a new file instead --
in that change, a whole `molecule/log-bound/` scenario whose `converge.yml` was
character-for-character the existing `default`'s.

The implementer then folded them into the existing scenario and deleted the
new one, which was the right call on its merits: two identical converges of the
suite's slowest role, on every pull request, to read one file. But the folded
scenario was **never committed**, so the derived assertions exist nowhere but
inside the implementer's edit. No reviewer can diff what the independent author
wrote against what survived, and the claim "every assertion moved verbatim"
rests on the implementer's word -- which is exactly the separation the
derive-tests step exists to create.

The fix is ordering, not policy: **commit the derived tests as authored, then
fold in a second commit.** The fold becomes a reviewable diff and costs one
extra commit on a branch that is squashed anyway.

Worth writing into `AGENTS.md`'s derive-tests paragraph rather than leaving it
as a queue entry, since the next change hits it the same way and the cost is
invisible until review.

## 43. remove-the-stale-test-hostname

**Not blocked; small, and recorded rather than folded into
`alert-on-certificate-expiry`, which found it while reading Traefik's
certificate metrics on 2026-09-09.**

`test.shatynska.com` was a throwaway smoke test. The archived change
`fix-traefik-docker-api-version` used a `whoami` container behind that hostname
in August 2026 to confirm Traefik's Docker provider had stopped erroring, and
its `tasks.md` records the confirmation. The container is long gone -- the name
returns Traefik's 404 -- but two things it left behind are still live:

- the `A` record, `2.29.14.98`, which resolves today and was missing from the
  zone table in `docs/deferred-work.md` until that table was corrected;
- a Let's Encrypt certificate, which Traefik still holds and **still renews
  every 60 days**, and which appears in `traefik_tls_certs_not_after` alongside
  the real one.

Nothing is broken by it. It is a standing request to a public certificate
authority for a name nothing serves, and a second series in a metric that now
drives an alert -- so if that renewal ever fails, the alert correctly reports a
hostname nobody wants, at which point the operator has to remember what `test`
was before deciding it does not matter.

**Order matters when removing it.** Take the DNS record away first, then the
certificate from Traefik's `acme.json`. The reverse leaves a name resolving to
the host whose certificate has already gone, which is a worse state than the one
being cleaned up. There is no router to remove -- the container that had one is
already gone -- so this is a DNS edit plus an `acme.json` edit, and the second
requires deciding whether editing that file by hand is acceptable at all or
whether the entry is better closed by leaving the certificate to lapse once the
record is gone.

## 44. name-every-alert-in-a-grouped-slack-notification

**Not blocked; recorded rather than folded into
`alert-on-certificate-expiry`, which routed around it for its own alert and
found the general case in doing so.**

Alertmanager's `slack` receiver renders `{{ .CommonAnnotations.summary }}` and
`{{ .CommonAnnotations.description }}`. `CommonAnnotations` holds only the
annotation pairs **identical across every alert in the notification's group** --
so any alert whose annotations name a per-series label delivers an empty title
and an empty body the moment two of them group together.

`ApplicationHighErrorRate` is in exactly that state and has been since it was
written: its summary names the router, `group_by` is `["alertname"]`, and two
routers erroring at once -- which a shared Traefik makes correlated rather than
independent -- produce a Slack message that says nothing. Nobody has seen it
because the alert has not fired on two routers yet.

`alert-on-certificate-expiry` fixed this for its own alert by adding `cn` to
`group_by` on that alert's own route, which is correct and minimal for one
alert. It does not generalise: every future alert naming a per-series label
needs the same treatment, and forgetting is silent.

The general fix is in the receiver, not in a route: render `{{ range .Alerts }}`
so a grouped notification lists each alert's own annotations. That changes
delivery for **every** alert in the stack, including ones nobody has re-read,
which is why it is a change of its own rather than a fold-in. Worth pairing with
an assertion that no alert's annotations reference a label absent from its
route's `group_by`, which is a static read of the committed file and would catch
the next instance instead of waiting for it to fire.

## 45. hold-the-whole-static-suite-to-its-own-constraints

**Not blocked; small, and recorded by `alert-on-certificate-expiry`, which is
the change that made it untrue.**

`AGENTS.md` says of the `.github/tests` suite that it may not make a network
call, use a credential, spawn a container runtime or need a Terraform binary,
and that "those constraints are themselves asserted by tests in that suite".
They are: three assertions in `TestTheSuiteNeedsNoPrivilegedResource` and its
neighbours parse the suite and check its imports and subprocess use.

What they parse is `SUITE_PATH`, which is `Path(__file__)` -- that one module.
While `test_ci_configuration.py` was the whole suite that was the same thing.
`alert-on-certificate-expiry` added `test_certificate_expiry_alerting.py` as a
second module, and the new file sits outside all three checks. It was held to
them by hand, which is exactly the assurance those assertions exist to replace.

The fix is to widen the three from their own file to every `test_*.py` in the
suite directory. The alternative -- keeping the suite to one file so the
self-check stays honest -- is worse: it is already 8,600 lines, and it would
make "add a test" mean "edit the file the derive-tests step forbids an
independent author from touching".

Note this is the second entry recorded from the same edge: entry 42 is about
derived tests arriving as a new file and being folded, and this one is about
what happens when they are not folded. Whichever way that question is settled,
both should be settled with it.

## 46. lint-the-repository's-shell-scripts

**Not blocked; recorded rather than folded into
`namespace-the-molecule-suite-per-working-tree`**, which added the script that
makes this worth doing.

`ansible/scripts/run-molecule` is this repository's first committed shell
script, and nothing checks it. `.pre-commit-config.yaml` carries hooks for
Terraform, Ansible, secrets and commit messages, and none for shell. That
change's own test-authoring step declined to verify the script with ShellCheck
for the reason `AGENTS.md` gives about unpinned tools: an ad-hoc invocation of a
linter this repository does not pin is unrepeatable, and a check that cannot be
reached is indistinguishable from one that passed. Its `tasks.md` discloses the
refusal under `## Not performed`.

The work is a pinned `shellcheck` hook in `.pre-commit-config.yaml`, and a
decision about whether `.github/tests` should assert that the hook exists — the
same shape as the pins that suite already reads. Small, and worth doing before
there is a second script.
## 47. verify-at-deploy-time-that-what-shipped-is-what-runs

**Not blocked; recorded rather than folded into
`apply-shipped-config-on-deploy`, which deliberately stops short of it.**

That change makes a configuration-only edit *visible* to Compose, so the
services whose configuration moved are replaced. What it does not do — and its
added requirement says so in as many words — is establish that a deploy
reporting success applied everything it shipped. A container can fail to be
replaced for reasons no property of the stack definition can express, and
nothing today compares a running container against the definition afterwards.

The check is small: after `docker compose up -d --wait`, compare each running
container's `com.docker.compose.config-hash` against `docker compose config
--hash='*'` and fail the deploy on a mismatch. It would have caught the original
defect on the day it happened rather than a day later, and it catches the whole
class rather than the one member of it that a checksum label addresses.

**It does not subsume the label, and adding it instead would have been wrong.**
Without a label, a configuration-only change produces equal hashes on both
sides — the file's and the container's — so this check passes while the
configuration sits unapplied. It is a backstop for reasons nobody has thought
of, not a replacement for making the change visible in the first place.

Two things make it a change of its own rather than a rider. It edits
`app-deploy`, which is generic across applications, so it changes deploy
behaviour for `commerce-ops` and every future application, not just for
`platform`. And it needs a decision about what a mismatch should do to a deploy
that has already replaced some services and reported them healthy — failing
after the fact is not the same as refusing to start.

Note the comparison has a trap the sibling change documented: four of the
platform stack's eight services -- `grafana`, `postgres`, `postgres-exporter`
and `traefik` -- interpolate `${...}` from `.env` into their service blocks, so
a hash computed anywhere without the host's real `.env` does not match the
host's. This check must run **on the host**, where that file is, or it will
report mismatches that are artefacts of where it ran.

It also does **not** catch entry 47's case, despite looking as though it should:
where a secret interpolated *inside* an embedded config is rotated, both sides
of this comparison compute the same unchanged value, so it passes while the
running container holds the superseded secret.

## 47. replace-a-service-when-a-secret-inside-its-config-rotates

**Not blocked; found in code review of `apply-shipped-config-on-deploy`, which
is structurally unable to close it.**

`alertmanager_config`'s content interpolates `${SLACK_WEBHOOK_URL}` and
`${DEADMANSWITCH_URL}`, and `.github/workflows/platform-deploy.yml` renders both
into `.env` from GitHub secrets at deploy time. Rotate the Slack webhook and the
effective Alertmanager configuration changes -- but the committed text does not,
so the checksum label derived from it does not, and Compose's own digest never
covered embedded config content in the first place. The container is not
replaced. **The revoked webhook stays live until something unrelated replaces
that container**, and every alert in the meantime goes to an endpoint the
rotation was meant to retire.

Nothing currently reports this. Entry 46's deploy-time hash comparison does not:
both sides compute the same unchanged value, so it passes. The checksum label
cannot: the value that changed is deliberately not in the repository, which is
the whole point of it being a secret.

**What would work is the deploy-time computation that change considered and
rejected** -- a digest taken on the host, after interpolation, moves when the
interpolated value moves. That change's design.md records this as the strongest
argument against its own Decision 1, found after the decision was made. Deciding
this entry means revisiting that trade with this case in hand, so it is a
decision about the mechanism rather than a defect to patch.

Bounded in the meantime by how rotation actually happens here: it is a manual
act by the operator, who can force the replacement in the same session. Worth
writing that into the rotation step of whatever runbook covers it, which is a
smaller piece of work than this entry and does not wait on it.
