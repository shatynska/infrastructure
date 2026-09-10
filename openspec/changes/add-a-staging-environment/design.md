## Context

See proposal.md — Why. What shapes the approach is that most of the work is not
in this repository. The pipeline reads `terraform/environments/*/pipeline.yml`
and needs no edit; what a second environment actually takes is a Hetzner project,
two API tokens, an HCP Terraform workspace, a GitHub Environment and three
secrets, none of which a commit can create and none of which any check in this
repository can see. The committed half is a directory of eight files, and the
risk lives almost entirely in the ordering between the two halves.

Three constraints bound every decision below:

- **Local credentials are read-only, and a fresh working tree has none at all.**
  `.envrc` is gitignored, so this tree cannot reach the Hetzner API even for a
  read. Anything requiring an API answer is a task for the operator, not
  something the author can settle by checking.
- **`.github/tests` may make no network call and spawn no container** — it reads
  committed files. Every assertion this change adds is a static read, and
  everything about the two-environment pipeline that only a real run can show is
  confirmed by a real run.
- **Nothing under `.github/workflows/` may change.** That is the claim
  *Each Environment Declares Its Own Pipeline Configuration*
  (`openspec/specs/iac-cicd-pipeline/spec.md`) makes, and this change is the
  first thing that can falsify it. A workflow edit turning out to be necessary
  is a finding to report, not a licence to edit.

## Goals / Non-Goals

**Goals:**

- A `staging` environment provisioned end-to-end through the pipeline: planned on
  its pull request, applied on merge, swept nightly by drift detection.
- The multi-environment paths this change can reach actually executed, and what
  they did recorded — with the ones it cannot reach named rather than assumed
  (Decision 9).
- Four requirements that describe prod alone brought to the number of
  environments that will exist, before a reader can be misled by them.
- Staging left in a state where the follow-up change (Ansible, platform, DNS)
  needs no Terraform work and no per-environment path parameterisation.

**Non-Goals:**

- Configuring the staging host. No Ansible, no platform stack, no DNS, no
  certificates. Staging ends this change as a bare Ubuntu server with an
  attached, unmounted volume.
- Enforcing promotion ordering in the pipeline. Decision 7.
- Generalising every prod-named requirement. Only the four that go unmet or
  actively mislead at N=2 are touched. Four others stay prod-named on purpose —
  *Conditional Prod Server Creation* (`openspec/specs/iac-server-lifecycle/spec.md`),
  *Conditional Prod Volume Creation* (`openspec/specs/iac-data-volumes/spec.md`),
  and *Data Durability for Stateful Resources* and *No Store on This Host Holds
  Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`), the last
  two of which say "this host" and become ambiguous at two hosts. They stay true
  of prod and nothing on staging contradicts them while staging holds no store, so
  they are recorded in `docs/deferred-work.md` with that as the trigger rather
  than swept now. Only the three narrow `iac-cicd-pipeline` names were already
  recorded there; this change writes the entry covering these four.
- Making staging cheap by making it unlike prod. It runs the same modules, the
  same image and the same volume layout; only the instance tier differs.

## Decisions

### 1. Staging gets its own Hetzner Cloud project

Settled by the operator before this change was drafted, and carried here from
`docs/change-queue.md` entry 49, which recommended it.

A Hetzner API token is scoped to exactly one project. One project would therefore
mean one Read & Write token covering both environments, which forces staging's
apply behind an approver — otherwise any push to `main` reaches a prod-capable
credential — and an approved staging deploy is as slow as prod and stops being
used, which is most of staging's value gone. It would also collide on the volume
name: `platform/docker-compose.yml` hardcodes `/mnt/main-data/prometheus` and
`/mnt/main-data/grafana`, Hetzner volume names are unique per project, so within
one project staging's volume takes a different name, a different mount path, and
Prometheus and Grafana come up writing to a path that does not exist — silently,
which is the part that makes it a trap rather than a chore.

**Alternative considered:** one project, staging gated, Compose paths
parameterised. Rejected on both counts above. The recurring cost of a second
project is a second token pair to rotate; the cost of the alternative is paid
every time staging is deployed to.

This is recorded as a requirement rather than only here — see the
`iac-state-management` delta — because a decision that lives only in an archived
design is one the next environment's author has no reason to find.

### 2. `staging`'s GitHub Environment requires no reviewer

The point of staging is that a merge reaches it without ceremony. Its apply job
still declares `environment: staging`, so the write token is confined to that
job, as *Credential Scoping by Privilege* and *Write Credentials Confined to the
Gated Pipeline* both require of every environment — the reviewer and the
confinement are independent, and only the reviewer is being dropped.

What makes that safe is Decision 1 and nothing else: staging's Read & Write token
can destroy staging's project and can touch nothing in prod's. The blast radius
of an unreviewed apply is exactly the environment it exists to be unreviewed in.

Nothing in this repository can verify the absence of a reviewer, or its presence
on `production` — both are repository settings. That is already stated in
`terraform/environments/prod/pipeline.yml` and in the requirement itself; this
change adds a second instance of an unverifiable fact rather than a new class of
one.

### 3. `destroy_policy_gate: false` for staging

The field exists for this. Staging is rebuilt on purpose — that is what entry 49
means by a place to rehearse a PostgreSQL major upgrade — and requiring a label
on every destructive plan against a disposable environment trains the operator to
apply the label, which is the same failure mode as an approval prompt with
nothing to approve.

Prod keeps `destroy_policy_gate: true`, and the polarity note in prod's
`pipeline.yml` is why this field is named for the gate: `disposable: true` and
`destroy_policy_gate: true` would be the same value with opposite meanings.

**Consequence accepted:** a merge that destroys staging's server and volume
applies without a second signal. What bounds the loss is that staging holds
nothing which is not reproducible by this repository — and that property is not
self-sustaining. `docs/change-queue.md` entry 49 decides staging is the
*permanent, application-facing* environment, so its successor will put
applications and a database on it. The constraint therefore travels: the
successor's change-queue entry states it, so that whoever spends it does so
knowingly rather than by not having read an archived design.

### 4. Same modules, same image, same volume; a smaller instance

Staging calls `terraform/modules/server` and `terraform/modules/volume` with the
same `image` and the same `volume_name = "main-data"` and `volume_size = 10` as
prod. The volume name matters beyond tidiness: it is what keeps the on-host mount
path identical across environments, so the follow-up change needs no
per-environment path and `platform/docker-compose.yml` stays as it is. Decision 1
is what makes reusing the name possible at all.

What differs, and why:

| Value | Prod | Staging | Why |
|---|---|---|---|
| `server_type` | `cx33` (4 vCPU / 8 GB) | half that tier — 2 vCPU | Entry 49's shape: roughly half prod's bill, and deliberately tight, so container resource limits are forced rather than deferred |
| `delete_protection` | `true` | `false` | Rebuilding staging is the point; provider-level protection would make Decision 3 unreachable |
| `backups` | `true` | `false` | Nothing on staging is worth restoring, and backups are a percentage of the instance price |
| `github_environment` | `production` | `staging` | Distinctness is required by the declaration requirement, and discovery fails the pipeline on a collision |
| `read_only_secret` | `HCLOUD_TOKEN` | `HCLOUD_TOKEN_STAGING` | Same reason: a repository secret holds one value |
| `web_allowed_cidrs` | `["0.0.0.0/0"]` | `[]` | Staging runs nothing this change deploys. `[]` is the module default and creates no web rule at all; opening 80/443 belongs to the change that puts something behind them |

Everything not in that table is prod's value, and three are worth naming because
"the same" is doing real work: `location = "hel1"` (a volume takes its location
from the server it attaches to, so both live where prod lives),
`ssh_allowed_cidrs = ["176.104.184.0/24"]` (the same operator ISP range, so the
cloud firewall is no wider for staging than for prod), and `image` (the same
Ubuntu release, since an environment that rehearses prod on a different image
rehearses something else).

Staging also declares `server_enabled` and `volume_enabled`, prod's own toggles,
with the same defaults. They are not decoration: `server_enabled = false` is this
change's only post-merge rollback that does not orphan resources, and the only
way to stop paying for staging without deleting its configuration. The mechanism
comes from using the same modules and the same variable shape; the requirements
that oblige it — *Conditional Prod Server Creation* and *Conditional Prod Volume
Creation* — are stated over prod alone and stay that way (see Non-Goals).

**The exact `server_type` string is confirmed against the Hetzner API when the
project is created, not asserted here.** This tree holds no credential to check
it with, `docs/bootstrap-a-new-host.md` names `cx33` and `cx43` but no 2-vCPU
member of that generation, and a wrong type name is discovered at apply as an API
error naming the type — loud, non-destructive, and cheap to correct. Writing a
guess into `terraform.tfvars` and calling it verified is the failure this note
exists to prevent.

### 5. `main.tf` is prod's, with prod's exceptions removed

Prod's `main.tf` carries two things staging must not inherit: `delete_protection`
and `backups` (Decision 4), and a `moved` block in `ssh_key.tf` recording a
one-time relocation of a key that predates Terraform. Staging's SSH key is
created fresh in its own project with `name = "staging"`, so no `moved` block and
no import.

The SSH **public key** is the same operator key prod uses. A separate key pair
for staging would be a second private key to hold for no gain: the key authorises
`root` on a host whose entire contents this repository can recreate, and staging
exists to be reached by the same operator.

### 6. The operator's steps come first, and the pull request comes second

This is the ordering the change turns on. `pr-validation.yml` plans every
environment a pull request **affects**, and it is a required check; a change
under `terraform/environments/<name>/` affects that environment. This pull
request adds `terraform/environments/staging/`, so it affects staging by that
rule and CI tries to plan it the moment the branch is pushed: `terraform init`
needs the `infrastructure-staging` workspace to exist and `TF_API_TOKEN` to
reach it, and `terraform plan` needs the repository secret
`HCLOUD_TOKEN_STAGING` to hold a token for a project that exists.

So the Hetzner project, both tokens, the workspace (in **Local** execution mode),
the GitHub Environment and all three secrets are created **before** the branch is
pushed. Doing it the other way round produces a red required check on a pull
request whose content is correct, and the obvious way to make it green — pushing
a commit that removes the directory — is also the way to lose the change.

One consequence worth stating: the lockfile. `.terraform.lock.hcl` must be
committed (*Provider Lockfile Committed*, `openspec/specs/iac-repo-foundations/spec.md`),
and it is produced by `terraform init` in the new directory.

**Corrected during implementation (2026-09-10).** This decision first said the
lockfile needed the workspace to exist, and that is true only of a full
`terraform init`. `terraform init -backend=false` skips backend initialisation
entirely and still resolves providers and writes the lockfile, so it needs no
HCP credential, no Hetzner token and no workspace — it was run in this tree, and
`terraform validate` passed after it. The result is byte-identical to prod's
lockfile, which is what the same provider and the same constraint at the same
commit should produce; the difference from copying prod's is that this one was
*produced*, and identity is the observation rather than the assumption. The
paragraph below stands as the rule for anything that genuinely needs the
backend — a plan, an apply, a state read.

**That local run is operator work, not authoring work.** `terraform init` needs
HCP credentials and `terraform plan` needs staging's Read Only Hetzner token, and
this working tree holds neither: `.envrc` is gitignored, so a tree checked out
fresh has no credential at all (Context, first constraint). Provisioning this
tree with staging's read-only token is therefore itself a stage-1 step, and the
tasks that run `init` and `plan` belong to whoever holds those credentials.

If that cannot be done, the lockfile is **not** copied from prod's directory. The
two would very likely be byte-identical — same provider, same constraint, same
commit — and that is exactly what makes the substitution attractive and wrong: a
lockfile is a record of what a resolution actually produced, and one presented as
generated when it was copied is the same class of claim as a `server_type`
asserted without checking. The honest outcome is a disclosed unperformed task.

**A disclosure is not a closure, and this one leaves a requirement unmet.** A
staging directory shipped without `.terraform.lock.hcl` fails *Provider Lockfile
Committed*, and nothing detects it: the Dependabot coverage check walks from
lockfiles to configured directories and never the other way, and
`openspec validate --archived` is satisfied by the `Reason:` label alone. So that
path also opens a `docs/change-queue.md` entry to produce the lockfile, and the
disclosure names it — otherwise the obligation exists only in a `Reason:` line in
an archived task list.

### 7. Promotion ordering is not added to the pipeline

*Environment and Module Folder Structure* currently prescribes that ordered
promotion "SHALL be achieved by sequencing apply jobs within a single workflow
(lower environment first, then the gated production environment)". At one
environment that sentence described nothing; at two it describes a mechanism the
apply workflow does not have, so it is unmet the day staging exists.

It is not merely unimplemented. *Gated Production Apply Applies the Reviewed
Plan* obliges that one environment's **failed plan** not withhold a correct
change from another, and gives the mechanical reason: a stage-scoped dependency
cannot distinguish this environment's outcome from another's. Sequencing
staging's apply ahead of prod's reintroduces that dependency one step later, so a
broken staging becomes a reason prod cannot be fixed. The obligation is stated
there for plans and holds here for the same reason — an extension by analogy
rather than a literal contradiction, and the delta says it that way.

So the requirement is modified rather than implemented: applies stay unordered
and independently gated, and promotion ordering — where it is wanted — comes from
prod's approver, who can withhold approval until staging's apply has been seen to
succeed. That is a discipline, not a mechanism, and the delta says so rather than
claiming a guarantee.

**Alternative considered:** a rank field in `pipeline.yml` and `needs:` between
matrix jobs. Rejected twice over — it reinstates the coupling above, and it is
pipeline work in a change whose scope is one environment directory. The residue
goes to `docs/deferred-work.md` so that a future change that wants ordering finds
the argument rather than re-deriving it.

### 8. Every deferred entry whose trigger names a second environment is revisited

The set is derived from `docs/deferred-work.md` by reading each entry's stated
trigger, not from memory of which change recorded which. It is **six** entries,
and they do not all end the same way — two are affected in substance:

- **Separating `rebuild_protection` from `delete_protection` in `modules/server`**
  — its body asserts "There is one environment, and it wants both", which is
  false the day staging exists. Its trigger names staging specifically, as an
  environment that "may want rebuild without delete protection". Staging does not:
  Decision 4 sets `delete_protection = false`, which turns both flags off, and
  rebuilding staging without deleting it is not a case anything here needs. The
  entry stands, with its premise corrected to two environments neither of which
  needs them apart — a correction, not a closure.
- **Managing DNS in Terraform** — its trigger is "a staging environment exists to
  rehearse the migration against", and that **fires**. It does not fire on this
  change: staging gets no hostname here, so there is nothing to rehearse against
  yet. The entry is updated to say the trigger fires on the successor, the change
  that gives staging its DNS records, which is where the rehearsal is actually
  available.
- **Two gaps in required-input validation that only the play could close** — its
  trigger is "a second environment exists … the first moment a `group_vars` is
  written from scratch rather than inherited". A second environment now exists,
  but `group_vars/staging.yml` belongs to the successor, so the trigger's own
  reasoning points there.
- **Three narrow `iac-cicd-pipeline` requirement names** — the trigger is a reader
  actually misled, not the count. Note that this change renames a fourth such
  requirement (*Dedicated Hetzner Cloud Project for Prod*) because its content had
  to change anyway, which is exactly the condition that entry names as the cheap
  moment to rename. The other three have no content change here.
- **Whether the drift heartbeat stays one check** — the trigger is an
  environment's plan failing often enough to mute the shared check, or an
  environment whose sweep is deliberately allowed to fail. Staging is neither.
  Worth noting that the nightly sweep is where two environments first share a
  mechanism for real, so this entry's evidence starts accumulating now.
- **Whether an Environment-approval-pending job is "pending" for concurrency** —
  the trigger is applies queuing often enough to matter. Staging's applies are
  ungated and prod's are unaffected.

**"An apply can still cancel another apply" is not in the set.** Its trigger is a
cancellation actually observed, or a queue deep enough for a third merge behind a
pending approval to be unremarkable — neither names a second environment. Naming
it here would be revisiting an entry on a trigger it does not have, which is the
same error as leaving one unexamined.

Each entry in the set records that it was revisited on this change and what its
disposition now is, so the next reader does not re-derive it.

### 9. What this change asserts statically, and what only a run can show

`.github/tests` gains assertions for properties that are a static read of a
committed file, chiefly: that every environment directory's `versions.tf` names a
workspace no other environment names (the new *Remote State Backend* scenario),
and that the never-apply-locally record in `AGENTS.md` and the README states the
prohibition in terms covering every environment rather than naming one (the new
*Write Credentials Confined to the Gated Pipeline* scenario). The Dependabot
coverage of the new directory is already asserted by the existing suite, which
compares that list against the tree — no new test needed, and a failure there is
the check working.

Everything else this change is for is behaviour of a live pipeline run with two
environments in it, which no static check can reach. It is confirmed by observing
the actual runs — and **the observation has to be what the pipeline is specified
to do, not what "two environments" suggests.**

This pull request changes `terraform/environments/staging/` and no shared module,
so the affected-environment rule selects staging alone: one plan comment, not
two, and on merge one apply job, not two. Both workflows narrow this way, and
*Pull Request Plan Visibility* and *Gated Production Apply Applies the Reviewed
Plan* (`openspec/specs/iac-cicd-pipeline/spec.md`) each carry a scenario
requiring exactly that. A confirm gate asking for two plan comments would record
correct behaviour as a failure, and the obvious repair — editing a workflow —
is the one thing this change may not do.

So what the pull request and merge confirm is:

- discovery emits **two** entries, staging among them;
- the affected-environment narrowing selects staging and excludes prod — the
  first time that path has had anything to exclude;
- `secrets[matrix.environment.read_only_secret]` resolves `HCLOUD_TOKEN_STAGING`,
  a name no run has ever resolved;
- one apply job runs, and it does not pause — this repository's first apply to
  reach real infrastructure without an approval click;
- no `production` approval is requested.

And what the **nightly drift sweep** confirms, which is the genuine N=2 exercise
this change can reach: `drift.yml` plans every discovered environment
unconditionally, so its next run is two plan jobs in one run, under two different
read-only secrets, reporting to one shared heartbeat. Not in two concurrency
groups — `drift.yml` declares none, and *Serialized Terraform Runs* says a drift
plan "SHALL NOT be placed in either group", running with `-lock=false` precisely
so it contends with nothing.

Three paths remain unexercised afterwards: two plan comments on one pull request,
two apply jobs in one run, and one of two applies pausing while the other
proceeds. All three need a change under `terraform/modules/`, which the next such
change will supply for free. Manufacturing one here — a whitespace edit to a
module — would raise a `production` approval with nothing to approve, which
*Gated Production Apply Applies the Reviewed Plan* names as the thing that trains
an approver not to read. They go to `docs/deferred-work.md` instead, named, with
that as the trigger.

## Risks / Trade-offs

- **A wrong `server_type` string reaches the first apply** → It fails at the
  Hetzner API naming the type, destroys nothing, and is corrected by a one-line
  pull request. This is the accepted cost of having no local credential to
  confirm it with; the alternative — asserting the type is right — would be a
  claim this tree cannot support.
- **The staging directory is pushed before its secrets and workspace exist** →
  A red required check on a correct pull request, and a tempting wrong fix.
  Mitigated by Decision 6's ordering being explicit tasks with the operator steps
  first, and by the branch not being pushed until they are done.
- **The `staging` GitHub Environment is created without `HCLOUD_TOKEN`** → GitHub
  silently resolves the repository secret of that name, which is *prod's Read Only
  token* — a plan against staging's directory authenticating to prod's project.
  The apply job already detects and refuses exactly this (*Credential Scoping by
  Privilege*), which is a guard written at N=1 for a hazard that only becomes real
  now. Its first real exercise is part of what the confirm gate observes.
- **Two environments contend on the drift heartbeat** → One environment's failed
  plan takes the whole nightly sweep red, without saying which. Accepted and
  already recorded in `docs/deferred-work.md`; staging is not an environment whose
  sweep is allowed to fail, so the condition that would force a split is absent.
- **Staging's ungated apply is a path to Hetzner that no human reads** → Bounded
  by Decision 1 to staging's own project, covered by the same nightly drift sweep
  as prod, and reversible by rebuilding an environment that holds nothing
  irreplaceable. It is a deliberate widening, not an oversight, and it is the
  first one this repository has made.
- **Cost is recurring and easy to forget** → One 2-vCPU instance plus 10 GB of
  volume, running continuously. `server_enabled = false` decommissions staging
  without losing its configuration, so pausing it is a one-line change rather than
  a deletion. This holds only because staging declares those toggles, which
  Decision 4 requires and which is a task rather than an inheritance — the
  requirements obliging them are stated over prod.

## Migration Plan

There is nothing to migrate: prod is untouched, and every file this change adds
is new except the four specifications, `.github/dependabot.yml`, `README.md`,
`AGENTS.md` and the two `docs/` files.

The rollout order is Decision 6's, and its stages are:

1. **Outside the repository** — Hetzner project, Read Only and Read & Write
   tokens, `infrastructure-staging` workspace with Execution Mode set to **Local**,
   `staging` GitHub Environment (no reviewer) holding `HCLOUD_TOKEN` and
   `TF_API_TOKEN`, repository secret `HCLOUD_TOKEN_STAGING`.
   Stage 1 also provisions this working tree: staging's Read Only token in the
   tree's gitignored environment file, and HCP credentials for the CLI, without
   which stage 2 cannot run at all.
2. **Locally** — write the environment directory, run `terraform init` to produce
   the committed lockfile, and `terraform plan` under the read-only token to see
   what the first apply will create.
3. **On the branch** — push, and read the pull request against Decision 9's list
   of what this run is specified to do.
4. **On merge** — staging's apply runs without approval; prod's does not run at
   all, because the merge touches no file that affects prod.
5. **On the next nightly sweep** — two environments planned in one run, which is
   the two-environment exercise this change can actually reach.

**Rollback.** Before merge, closing the pull request costs nothing and leaves only
the out-of-repository objects, which can be deleted or left dormant. After merge,
`server_enabled = false` in staging's `terraform.tfvars` removes the server and
its volume on the next apply while keeping the configuration — the path
*Conditional Prod Server Creation* exists to provide. Removing the directory
outright also removes staging from discovery, and is the correct rollback only if
the workspace is deleted with it; a directory removed while its state still holds
resources leaves them managed by nothing.

## Open Questions

- **Which 2-vCPU type name is current** (Decision 4). Deferred safely: it changes
  one string in `terraform.tfvars`, and the answer arrives with the Hetzner project
  the operator creates in stage 1, before the plan in stage 2.
- **Whether staging's volume should be smaller than prod's 10 GB.** Deferred: the
  size is a variable, changing it later is a resize rather than a rebuild, and
  Hetzner's minimum makes the saving negligible. Staging matching prod is the
  better default while the follow-up change is still to come.
