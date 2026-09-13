# Deferred work

What this project has deliberately not done, and why. An entry is deleted when it stops being true. See `AGENTS.md`, "A second change surfacing".

The first entries came out of the full-repository audit on 2026-09-06 (trunk at `245ef59`); later ones arrived from `docs/change-queue.md`, having been recorded there as identified changes and then declined. Each is a real observation deliberately **not** turned into a change.

Work that is merely waiting on something else belongs in `docs/change-queue.md`, not here. An entry moves in that direction when what it was waiting for turns out not to be an event but a decision — one nobody is positioned to take, because the case it would decide has never arisen. A queue entry in that state is not pending; it is declined and mislabelled, and it costs every reader who re-reads the queue a fresh judgement about work that is not going to be done.

---

## Splitting `platform/docker-compose.yml` into multiple files

The file is 602 lines and holds, inline, the Prometheus scrape config, seven alerting rules, the Alertmanager routing tree, and three Grafana dashboards as embedded JSON. Editing dashboard JSON inside a YAML `configs:` block inside a Compose file is genuinely unpleasant, and nothing validates that JSON.

It stays one file because of a deliberate security control, not inertia. `deploy-receive` (the `Install the deploy-receive script` task in `ansible/roles/deploy_user/tasks/main.yml`) extracts a **fixed, explicit two-member list** — `docker-compose.yml` and `.env` — from the tar it receives. GNU tar with named members extracts only those names and ignores everything else the archive contains. That is what bounds what a holder of the platform deploy key can write onto the host.

Carrying additional files would mean widening that member list, and every entry added to it is a new path an attacker with that key could write to. The editability gain does not pay for weakening the control.

**Revisit if** the stack outgrows what one file can reasonably hold, or if a mechanism appears that adds files without widening what the forced command accepts (a checksummed bundle unpacked into a fixed subdirectory, say). Until then this is the intended shape, and the inline JSON is its accepted cost.

## Separating `rebuild_protection` from `delete_protection` in `modules/server`

`terraform/modules/server/main.tf:53-54` drives both Hetzner flags from the single `delete_protection` variable. They are distinct capabilities and a consumer could in principle want one without the other.

No consumer does. Splitting them adds a variable, a validation and a test for a case that does not exist, and the coupled default is the safer one.

**Revisited 2026-09-10 by `add-a-staging-environment`, and it stands.** This entry used to argue from "There is one environment, and it wants both", which stopped being true that day: there are two, and they want opposite values. Neither wants them *apart*, which is what this entry is actually about. Prod sets `delete_protection = true` and wants rebuild protection with it; staging sets `false` and wants neither, because being rebuilt is what staging is for. The coupling holds at two environments for the same reason it held at one — the argument merely no longer rests on there being only one.

**Revisit when** an environment actually needs them apart: an environment that must be rebuildable in place while remaining undeletable, which neither of the current two is.

## Generating Ansible's CIDR variables from Terraform

`ansible/inventory/group_vars/production.yml` hand-mirrors `terraform/stacks/main-production/terraform.tfvars`'s `ssh_allowed_cidrs` and `web_allowed_cidrs`. These have drifted once already, and the file's own comment records what that cost: UFW rules assumed `web_allowed_cidrs` was unset when it was in fact `["0.0.0.0/0"]`, which would have left the host firewall blocking traffic the cloud firewall already permitted.

Deriving them from Terraform output would remove the drift class entirely, and is deliberately not done: it would make an Ansible run depend on Terraform state and an HCP Terraform token, coupling the two layers that this repository's structure exists to keep separate. The reasoning is recorded in `ansible/roles/hardening/README.md`; it is repeated here because the audit re-surfaced the drift risk as live rather than settled.

**Revisit if** it drifts a second time. One recurrence is evidence the manual sync does not hold, and would outweigh the coupling objection.

## Host-key verification on the platform deploy

`.github/workflows/platform-deploy.yml:157` runs `ssh-keyscan` into `known_hosts` on every run — trust-on-first-use, every time, which verifies nothing about the host's identity.

Accepted, because the connection it protects is already bounded by something stronger: the runner reaches the host only over the tailnet, having authenticated to it with an OAuth client scoped to the `main-production` Environment, and the key it presents is restricted to a forced command that accepts no other invocation. An attacker positioned to answer that keyscan is already inside the tailnet.

**Revisit if** the deploy ever runs over the public internet, at which point this stops being defence-in-depth and becomes the only check.

## Automatic refresh of the Molecule platform image digest

Every scenario under `ansible/roles/*/molecule/*/` pins its platform image to `geerlingguy/docker-ubuntu2204-ansible:latest@sha256:0172e3b5…`, and nothing updates that digest. It will age indefinitely until a person refreshes it by hand (`ansible/roles/docker/molecule/default/molecule.yml` carries the procedure).

Dependabot cannot see it: its `docker` ecosystem scans Dockerfiles and Compose files, not `molecule.yml`. Closing this would mean a bespoke scheduled workflow that queries the registry, rewrites eight files and opens a pull request — machinery out of proportion to a test-only base image, and machinery that would itself need pinning, testing and a credential story.

The trade is deliberate rather than reluctant. A known-stale image the suite runs against reproducibly is worth more than a current one it cannot make the same claim about twice; that reproducibility is the whole point of the pin, and an automatic refresh partly gives it back. The digest is identical across all eight scenarios and `.github/tests/test_ci_configuration.py` fails the build if they disagree, so a manual refresh is one find-and-replace, not eight decisions.

**Revisit if** the image ages far enough that a scenario fails for a reason traceable to the base image rather than to the role under test, or if this repository grows a second hand-pinned digest — one is a manageable exception, two is a pattern that wants a mechanism.

## Two exclusion rules for `ansible/roles/` in the CI test suite

`.github/tests/test_ci_configuration.py` now decides twice, differently, which directories under `ansible/roles/` are this repository's own. `role_names()` excludes any name containing a `.` — the Galaxy `namespace.role` convention — and the newer image-pinning checks exclude names appearing in `ansible/requirements.yml`'s `roles:` list.

The newer rule is the stronger one: content vendored into `ansible/roles/` that is *not* pinned in the manifest stays inside the pinning obligation, where the dot heuristic would silently exempt it. The older rule is adequate for what it does — reasoning about `ansible-verify.yml`'s role discovery — and the tests built on it pass.

Unifying them is deliberately not done here. It means editing existing, passing tests, which is a change of its own rather than a rider on one whose subject is the pins. **Revisit when** something else needs to reason about that boundary, or when a directory appears that the two rules would classify differently — at which point the disagreement stops being theoretical.

## Four shape assumptions in the pull-request-identity checks

`open-autoupdate-pr-with-app-token` added a section to `.github/tests/test_ci_configuration.py` that discovers every workflow step opening a pull request and asserts what identity it uses. The discovery and its helpers make four assumptions that are true of this repository today and would each produce a **false positive** — a failing build on a legitimate change — rather than a false negative:

- `token_inputs` reads only step-level `env:`. A pull-request-opening `run:` step taking `GH_TOKEN` from a job- or workflow-level `env:`, which is the ordinary `gh` idiom, would be reported as having no explicit token.
- `step_opens_a_pull_request` requires a POST and the string `/pulls` somewhere in the same `run:` block, not in the same command. `apply.yml` already contains `/pulls` twice for read-only fetches; adding any `gh api --method POST` to that step would classify a read-only step as one that opens a pull request.
- `secrets_referenced_by` scans the whole job rather than the identity path. If the `autoupdate` job ever gains an unrelated secret — no longer hypothetical: `notice-when-a-periodic-job-stops-reporting` added `HEARTBEAT_PING_KEY` to that workflow, in a job of its own — the README tests would demand that secret be documented in the same passage as the App credential, which could only be satisfied by misdescribing it.
- `readme_sections` splits the README at any line beginning with `#`, including inside a fenced code block. Adding a shell snippet with a comment line to the section documenting the App would split that passage in two and fail two otherwise-correct tests.

None is a defect in what the tests assert; each is a limit on the shapes they can read. They are recorded rather than fixed because fixing them means editing passing tests written by an independent author from the delta specs, which is a change of its own rather than a rider on the one that introduced them.

**Revisit when** any of those four shapes is actually needed — most likely the `env:` one, the first time a workflow here opens a pull request with `gh` instead of an action.

## Two properties of the autoupdate workflow that only reading enforces

`open-autoupdate-pr-with-app-token` left `.github/workflows/pre-commit-autoupdate.yml` carrying two properties its own test section does not assert:

- The minting step's `permission-contents: write` / `permission-pull-requests: write` inputs, which down-scope every token it issues. The delta spec's clause that the credential carries no authority beyond what the pull-request step exercises is *readable* from committed content because of them, but not *checked*: an edit dropping those two lines passes the whole suite.
- The restricted input set on the pull-request step. Adding `labels` or `assignees` would need Issues, which the App does not hold, and nothing fails until the workflow next runs.

Neither is a live risk today: the App's own scope is exactly the two permissions the inputs name, so dropping them changes nothing until the App is widened. The exposure is second-order — a later widening of the App plus a later edit here.

Not folded in because a check for either is a test, and this repository has tests for a change's delta specs written by an author other than whoever wrote the implementation. Adding them during that change's own build phase would have inverted that, and neither property has a scenario in the delta to derive from — they come from a prose clause. The honest options were a test derived properly or a note; this is the note, and the workflow header says plainly which of its claims the suite does not stand behind.

**Revisit when** the App's permissions are widened beyond Contents and Pull requests, which is the moment the exposure stops being second-order — or sooner, as a small change of its own that adds the scenario and has the assertion derived from it.

## Automating per-application provisioning in the shared PostgreSQL instance

*Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) obliges this host to give an application its own database inside the shared instance when it keeps non-durable relational data here. Nothing automates that.

Note what is deferred and what is not. The step itself is **defined**: `docs/bootstrap-a-new-host.md` carries the `CREATE ROLE` / `CREATE DATABASE` recipe, run from the operator account, and `platform/README.md` documents the same shape for the `pgexporter` role. What is deferred is the **machinery** — a script or a deploy-time hook that creates the database and role, and delivers the credential to the application the way its deploy key is delivered.

It is deliberately not built because no application has ever asked for one. On 2026-09-08 the shared instance held no application database at all, and the only application on the host keeps its data elsewhere. A provisioning mechanism designed against no consumer would fix the shape of a credential path, a naming convention and a failure mode by guesswork, and the guesses would be discovered wrong by the first real user rather than by review.

**Revisit when** an application actually needs technical storage in the shared instance. That is the first moment the design has a consumer to be right about; until then the manual recipe is not a workaround but the whole of what is needed.

## Managing DNS in Terraform

Was `docs/change-queue.md` entry 26, deleted from there and recorded here on 2026-09-08 when the zone was actually read and the operator decided against the migration.

The entry assumed the work was a `terraform/modules/` addition and a token split. Reading the live zone showed why it is not. `shatynska.com` is served by `ns15`/`ns25`/`ns35.inhostedns.*` — the nameservers of ukraine.com.ua, neither Hetzner DNS nor Cloudflare — so managing the records in Terraform means moving the nameservers, not adding a provider. Read on 2026-09-08:

| Record | Value |
|---|---|
| `shatynska.com` A | `2.29.14.98` — the prod host |
| `www` A | `2.29.14.98` |
| `fuperia` A | `2.29.14.98` — the name commerce-ops routes, and what Traefik holds a certificate for |
| `test` A | `2.29.14.98` — **row added 2026-09-09**, record itself predates this table; see below |
| `shatynska.com` MX | `mx.ukraine.com.ua` |
| `shatynska.com` TXT | `v=spf1 include:_spf.ukraine.com.ua ~all` |

**The `test` row was missing when this table was written.** It was added on 2026-09-09 by `alert-on-certificate-expiry`, which found the record while reading Traefik's certificate metrics: Traefik holds and is still renewing a Let's Encrypt certificate for `test.shatynska.com`. The table was written on 2026-09-08 as "the records as read", and it was already incomplete that day — worth stating plainly, because the table is this project's only written record of the zone and its value depends on being read against the zone rather than trusted. `docs/change-queue.md` entry 43 covers removing the record itself.

**The zone carries live mail.** An NS migration moves the MX and SPF records with it, and a transcription error there stops mail rather than a web service — a failure that is silent to every check this repository has, because nothing here monitors mail. That is a different risk class from the one the entry was weighing, and it is the reason this is deferred rather than queued: the work is not waiting on another change, it was declined on its merits for now.

**What the original entry was right about.** DNS is still the one piece of the running system that lives in no repository, and a rebuild (`docs/change-queue.md` entry 30) or an IPv4 change is still followed by a manual edit nobody has written down. The table above is the mitigation for the moment: the records are now recorded somewhere, which is most of what the entry was protecting against.

**Revisited 2026-09-10 by `add-a-staging-environment`. Its first trigger is the one that fires, and it has not fired yet.** That change provisioned staging's infrastructure and gave it no hostname: there is a second environment, but still only one zone's worth of records and nothing to rehearse a migration against. The trigger becomes live with `docs/change-queue.md`'s staging web-exposure entry, which is where staging acquires DNS records — and that is the moment to weigh doing it in Terraform rather than by hand, since it is the first time the manual edit would be made twice. This trigger was entry 50's until `configure-the-staging-host` took that entry's host half and left the hostnames to the web-exposure entry. Entry 50 went with that change's archiving, and the pointer was moved ahead of the deletion rather than left to dangle through it.

**Revisit when** staging acquires its hostnames (the staging web-exposure entry), or when mail moves off this zone, or when a second hostname makes the manual edits frequent enough to be worth the risk. Cloudflare and Hetzner DNS were the two candidates considered; neither was chosen, and that choice is still open.

## A hard failure when volume discovery matches more than one device

Was `docs/change-queue.md` entry 3a, deleted from there and recorded here on 2026-09-09. It was queued as a policy decision awaiting an operator's answer, and it has none to wait for: nothing is posing the question.

`platform_data_volume` discovers its device by matching `/dev/disk/by-id/scsi-0HC_Volume_*`, sorting the matches and taking the lexicographically first. The alternative — refuse when the match is ambiguous, on the grounds that a wrong pick is worse than a stop — was considered in `fix-volume-discovery-and-consistency`'s `design.md` Decision 2 and rejected for that change rather than on the merits.

It is not taken here either, and for a reason that entry did not state. Refusing makes the role's success depend on **what else is attached to the host**, which the role does not own. A second Hetzner Volume mounted for some unrelated purpose would break `host-baseline.yml` on every run thereafter, and a converge that stops is a worse failure than a mount that is merely arbitrary — particularly since the pick is not arbitrary. Two Molecule scenarios hold it deterministic: `multiple-devices-discoverable` and `multiple-devices-reverse-order`, one per directory-read arrangement, since either alone would pass a role selecting `files[0]` or `files | last`.

The third arm — telling the role which device is the stack's `main` volume — is the `linux_device` hand-copying that `add-platform-monitoring` already considered and rejected. So all three are settled: the pick stays deterministic, inference stays, and the ambiguity stays tolerated.

**Revisit when** a second volume is actually attached to a host in this project. That is the first moment the question has a live case to be right about, and the operator answering it is answering about something real rather than deciding a hypothetical. Prod has one volume today.

## Two gaps in required-input validation that only the play could close

Were `docs/change-queue.md` entries 3c and 3d, deleted from there and recorded here on 2026-09-09. They are one decision at two depths, and neither can be taken in the abstract.

`iac-host-configuration`'s *A Role's Absent Required Input Is Reported by Name* is satisfied at **role** scope, which is the scope each role's Molecule scenarios verify. Two things sit outside it:

- **Play scope.** `ansible/playbooks/host-baseline.yml` runs its roles in order, so against a host whose `group_vars` omits `deploy_apps` a real run installs Docker, runs the whole of `hardening` including `Enable UFW`, and joins the tailnet before `deploy_user`'s assertion is reached. The requirement's wording — "before any task that acts on the host has changed it" — reads naturally as the play, and at that scope it is not met.
- **Element shape.** The assertions check the container — defined, a sequence, not a string, not a mapping — and nothing about the elements. So `deploy_apps: ["platform"]` passes and then fails at `item.name`, after the deploy group, the account and its `.ssh` directory already exist.

Neither is closed, and the reason is the same for both. **What they produce is a partially-converged host, not a damaged one.** Every role in that play is idempotent, so the recovery is to correct `group_vars` and re-run — which is what an operator does on seeing the refusal anyway. Against that, the play-scope fix restates every role's required inputs in a second place that nothing keeps in step with the roles, so it buys an earlier refusal at the cost of a new drift class. The element-shape fix means either widening a requirement — a `MODIFIED` delta and the derived tests it owes — or adding a check the requirement does not ask for.

The exposure is also narrower than it reads. Both need a `group_vars` that is incomplete or hand-edited to a wrong shape; prod's is neither, and has not changed shape since it was written. The first host where either could bite is a **new** one.

`ansible/playbooks/host-baseline.yml` states the play-scope gap in a comment where the ordering decision depends on it, and that comment is the mitigation: the role placed last is placed there because a refusal ahead of it is possible.

**Revisited 2026-09-10 by `add-a-staging-environment`, and it stands.** A second environment now exists, but that change is Terraform and pipeline only: staging has no `group_vars` and no play that can target it, so nothing has yet been written from scratch and neither gap has acquired a real case. The trigger's own wording is what defers it — the condition is a `group_vars` written from scratch, not an environment existing — and that happens in the change recorded in the paragraph below. (That paragraph named `docs/change-queue.md` entry 50, which `configure-the-staging-host` deleted on archiving; the pointer was replaced ahead of the deletion rather than left to dangle, and what it pointed at is now named directly.)

**Revisited 2026-09-10 by `configure-the-staging-host`, the trigger firing at last, and both gaps stand.** `ansible/inventory/group_vars/staging.yml` was written from scratch in that change, so each gap now has the real case the condition was waiting for. The reasoning that deferred them is untouched: what they produce is a partially-converged host rather than a damaged one, every role in the play is idempotent, and the play-scope fix would restate every role's required inputs in a second place nothing keeps in step with the roles.

**Do not read that change's guard play as this fix.** `host-baseline.yml` now opens with a play against `localhost` that refuses when the targeted environment resolved to no host. That is a different question at a different scope: this entry is about a role's *input* being absent on a host that resolved, and the guard is about *no host resolving at all*, which is upstream of every role and of every role-scope assertion. Neither gap is narrowed by it.

One thing did change in the exposure. Staging's `group_vars` deliberately leaves `deploy_apps` unset rather than empty, so `deploy_user` refuses until the operator supplies staging's deploy keypair — which means the play-scope gap is now reachable on a real host on purpose, by design, rather than only by a hand-edit. It is still the recoverable failure described above: correct the file and re-run.

**Revisited 2026-09-12 by `move-the-platform-data-mount`, which leans on this entry in a way the two above did not, and it still stands.** That change gives `platform_data_volume` a second role-scope refusal — a declaration naming the mount path in force as a *superseded* path, which would retire the `/etc/fstab` entry the same run establishes. Its delta scopes the obligation explicitly: the refusal precedes everything **that role** changes, not everything the play changes, and it names this entry as where the remaining distance is recorded. Three places now point here for it — the delta spec, `ansible/roles/platform_data_volume/README.md`'s variable table, and the guard's own comment.

**Read carefully, because this case is not the one the entry above describes.** Both gaps above are about an input that is **absent**. This is two inputs that are both **supplied** and contradict each other, under a different requirement — *Platform Data Volume Is Mounted at a Fixed Host Path*, not *A Role's Absent Required Input Is Reported by Name*. What it shares is only the scope: a role-scope refusal meets a host that six earlier roles have already converged, and no wording inside a role can change that. So the play-scope half of this entry now carries weight for two requirements rather than one, and the revisit trigger below — which is about a `group_vars` being written — cannot fire on this case at all.

That does not change the disposition. The reasoning is the same and is if anything stronger here: a refusal leaves a partially-converged host, every role in the play is idempotent, and the recovery is to correct the inventory and re-run. The contradictory declaration is also harder to reach than an absent input — it takes an edit to `platform_data_volume_superseded_mount_paths`, which exists in exactly two files and is changed only when a mount path moves.

**Revisit when** a third environment's `group_vars` is written, or when a partially-converged host actually costs something, or when a **third** requirement comes to rest on this entry's play-scope half — the exposure is now reachable rather than hypothetical, so the next occurrence is evidence rather than a constructed case.

## Asserting that the README agrees with the tree

Was `docs/change-queue.md` entry 13, deleted from there and recorded here on 2026-09-09.

`refresh-readme-accuracy` found two README statements that had gone stale against committed files and that nothing noticed for weeks: the region, stated as `fsn1` while `terraform/stacks/main-production/terraform.tfvars` said `hel1`, and the Molecule scenario count, stated as eight against twelve in the tree. Both are inside what `.github/tests` can assert — a static read of two committed files, no network, no credential, no container runtime — and this repository already enforces a documentation convention that way.

It is not done, because **the better fix has already been applied and generalises where an assertion does not.** That same change replaced the answer with the command that produces it wherever the useful content was a count or a list; the Repository layout section is now a `git ls-files` pipeline rather than an enumeration. A fact derived on read cannot go stale, so it needs no assertion. A fact that is asserted still has to be edited in the same commit as whatever it mirrors, or the build goes red — so an assertion converts a silent staleness into a standing editing obligation, which is a trade rather than a win. Rewriting the next stale fact as its own command is cheaper and leaves nothing behind.

What remains genuinely duplicated after that pass is two facts. Buying a check for them costs a new requirement — this repository does not enforce a convention it has not recorded — plus the derived tests that requirement owes, plus a scope decision about whether the CI/CD section's workflow list is in or out. That is a poor trade for two assertions, and the scope decision is the part that cannot be taken well in the abstract.

**Revisit when** a third README fact is found stale that genuinely cannot be rewritten as the command that produces it, or when `iac-repo-foundations` is being modified for another reason and the requirement can be widened without being paid for on its own.

## The `terraform.tfvars` parenthetical that names labels

Was `docs/change-queue.md` entry 14, deleted from there and recorded here on 2026-09-09. It was recorded as a correction to batch into whatever change next touched `iac-repo-foundations`. No such change arrived for three months, and a correction waiting for a carrier that may never come is a deferral rather than a queue entry.

*Version Control Excludes State and Secrets* (`openspec/specs/iac-repo-foundations/spec.md`) describes `terraform/stacks/<name>/terraform.tfvars` as holding "server type, region, image, labels, allowed CIDRs". The file holds no labels; the only `labels` block under `terraform/stacks/main-production/` is in `ssh_key.tf`.

The disagreement is **factual, not normative**. The parenthetical is illustrative, the requirement's normative content is that the file is committed and non-secret, and labels genuinely are non-secret environment configuration — simply set on the resource rather than passed through this file. Nothing is permitted or forbidden differently because of it, and no reader is misled about what the requirement demands.

Correcting it is a `MODIFIED` delta, and the derived test it would owe is "the requirement's parenthetical agrees with `terraform.tfvars`" — precisely the cross-file assertion the entry above declines, and on the same reasoning. Paying for that machinery to fix an illustration that misleads nobody inverts the cost.

**A carrier did arrive, and it declined.** `rename-terraform-environments-to-stacks` rewrote this very row on 2026-09-11, moving the `terraform.tfvars` path onto the new Terraform root and leaving `labels` where it stands. That was the right call and is recorded so that the next reader does not take the entry's "no such change arrived" at face value and conclude nobody has looked: a vocabulary sweep is not a substantive modification of this requirement, folding a factual correction into it would have been unrelated scope, and the derived test that correction owes is the cross-file assertion the entry below still declines. What the carrier changed is the path in the row, which had to move with the tree.

**Revisit when** a change modifies *Version Control Excludes State and Secrets* for a substantive reason and can carry the correction — or if the parenthetical is ever read as an inventory rather than an illustration, which is the point at which the disagreement stops being factual and becomes normative.

## Four residues of namespacing Molecule per working tree

`namespace-the-molecule-suite-per-working-tree` closed the failure that matters — a Molecule run reporting success against another session's container. Four things it deliberately did not close are recorded here rather than in that change's `design.md`, which is archived with it.

**A run with no namespace still writes to the shared ephemeral directory before it refuses.** Verified while implementing: a bare `molecule create` in a role directory resolves its inventory under `~/.ansible/tmp/molecule.<id>.<scenario>` and only then fails at `create` on the container name. That write cannot produce a *result* — the run dies before any play — which is why the requirement forbids sharing state a result could come from rather than sharing anything at all. The levers that would close it do not exist: Molecule's interpolator has no `:?` error form, and a guard play would fire at `prepare`, after `create`.

**The entry point is a convention, not a gate.** Nothing stops a session typing `molecule` directly; the refusing default is what makes that safe rather than silent. The stronger form considered and not taken was deriving the namespace so that possessing a valid one implies having used the entry point — rejected because it spends the legibility that makes `docker ps` answer *whose container is this*, which is the question the whole change exists to make answerable.

**Namespaces accumulate.** Nothing reclaims the `.molecule-home/` of a removed working tree, or a container it left behind. Both are named after the tree, so both are removable by hand; nothing does it automatically, exactly as `AGENTS.md` says of namespaces generally.

**A working tree renamed or moved after a run orphans its state.** The namespace is derived from the absolute path, so the old containers and ephemeral directories become unreachable by the deterministic-resolution guarantee. Rare, loud, and removable by name.

**Revisit when** a session is actually bitten by one of these, or when Molecule gains an error form for an unset interpolation.

## Three `iac-cicd-pipeline` requirement names that now read narrower than they are

Recorded by `make-the-pipeline-environment-agnostic`, whose `design.md` Decision 7 declined the rename. A note kept only inside a change is archived with it, and this one outlives the change.

That change made the pipeline environment-agnostic without renaming three requirements whose names still name production alone:

- *Gated Production Apply Applies the Reviewed Plan*, which now governs every environment's apply, not production's;
- *Credential Scoping by Privilege*, whose token table it replaced with a per-environment scheme — the name is accurate but its scenarios read as production's;
- *Write Credentials Confined to the Gated Pipeline* (`iac-safety-hardening`), now stated over each environment's own Read & Write token.

Only the first is a genuine name/content mismatch; the other two are listed because the same sweep would touch them and a reader chasing one will find the others.

**Why not renamed.** Requirement names are this repository's citation form (`AGENTS.md`, "Citing this repository's own specifications and change records"), and they are cited from comments in `apply.yml`, `drift.yml` and `pr-validation.yml`, from `docs/bootstrap-a-new-host.md`, and from archived change records. Renaming sweeps every one of those into a diff that already restructures three gated workflows at once — a mechanical rename mixed into the diff that most needs to be read closely.

**Revisited 2026-09-10 by `add-a-staging-environment`, and it stands.** A second environment now exists, so the name and the content no longer describe the same set — but the trigger is a reader actually misled, and nothing has been. That change did rename a fourth requirement of this kind, *Dedicated Hetzner Cloud Project for Prod*, which it had to modify anyway; that is this entry's own stated cheap moment, taken where it arose. The three below had no content change there, so renaming them would have been the bare sweep this entry declines.

**Revisit when** a change modifies *Gated Production Apply Applies the Reviewed Plan* for a substantive reason and can carry the rename, or when a reader is actually misled by one of these names into believing the requirement does not bind an environment other than prod.

## Whether the drift heartbeat stays one check across all environments

Recorded by `make-the-pipeline-environment-agnostic`, from that change's `design.md` Open Questions, for the same reason as the entry above: the question outlives the change that raised it.

`drift.yml` now plans every environment in a matrix, but reports to a single external heartbeat check, `infrastructure-drift`, from a single `report` job.

**The working assumption this change ships with is that one check is right.** What the heartbeat answers is *did the nightly sweep run at all*, which is a property of the run rather than of an environment: GitHub disables a schedule-triggered workflow after 60 days of repository inactivity and emits nothing when it does, and that silence is per workflow. Per-environment drift is already reported per environment — each environment gets its own deduplicated GitHub issue — so the heartbeat is not the mechanism carrying that signal.

The cost of the assumption, stated plainly: the `report` job names every other job in `needs:` and pings `/fail` when any of them failed, so one environment's failed plan takes the whole heartbeat red. That is the correct polarity for an alarm and the wrong one for attribution — the alert says the sweep is unhealthy without saying which environment.

**Revisited 2026-09-10 by `add-a-staging-environment`, and it stands — but its evidence starts accumulating now.** A second environment exists, and the nightly sweep is the first mechanism the two share for real: one run, two plan jobs, two read-only secrets, one heartbeat. Staging is neither of the two cases that would force a split — its plan is not expected to fail, and its sweep is not deliberately allowed to fail. So the working assumption is unchanged and is, for the first time, actually being tested rather than reasoned about.

**Revisit when** one of two things happens: an environment's plan fails often enough that the shared heartbeat is muted in practice, which is the failure mode *Scheduled Drift Detection* already names for a persistently red job; or an environment is added whose sweep is deliberately allowed to fail, at which point one check cannot express both states.

## Whether a job awaiting an Environment's approval is "pending" for concurrency

Recorded by `make-the-pipeline-environment-agnostic`, whose `design.md` Decision 9 declines to settle it. The delta names it as unestablished, but a delta is archived into the main specification and `design.md` is archived with its change — so without an entry here the question would quietly become settled fact the moment the change archives.

**The question.** GitHub cancels a *previously pending* job in a concurrency group when a new one queues, and does so even under `cancel-in-progress: false` — that much is documented. What is not established is whether a job that is waiting on a GitHub Environment's protection rules counts as *pending* for that purpose, or as something else. If it counts as pending, then any job queuing into the same group can cancel an approved apply that is waiting for its reviewer, and it does so as a **cancellation** rather than a failure — which nothing in this repository reads as an alarm.

**What was done instead.** `apply.yml`'s plan job and apply job were given separate per-environment groups, so a queued plan can no longer be the thing that cancels a waiting apply. That is correct under *both* answers: where a waiting apply is pending, the separation removes a silent-loss path; where it is not, the separation costs only a plan that Terraform later refuses as stale, loudly. The experiment would establish whether that cost is necessary, not whether the separation is right.

**Why the experiment was not run.** Tasks 1.1 and 1.2 of that change ran exactly this kind of scratch-workflow probe for two matrix mechanisms, so the precedent exists. This one is more expensive: it needs a scratch GitHub Environment *carrying a required reviewer*, a merge to the trunk to trigger the apply path, and a second and third merge timed against a human approval — repository-settings churn well beyond what those probes needed, against a Migration Plan that promises none.

**Revisited 2026-09-10 by `add-a-staging-environment`, and it stands.** A second environment exists, and it makes the question no more pressing than it was: staging's applies are ungated, so they never wait on a protection rule and never occupy the state this question is about, and prod's queue is unchanged. The answer starts to matter only when two environments' applies contend, which needs a busier trunk than this repository has.

**Revisit when** applies queue often enough for the answer to matter, or when an approved apply is ever observed to have been cancelled rather than run. The second is the observation that settles it for free, and the entry below is where to look first if it happens.

## An apply can still cancel another apply, silently

Recorded by `make-the-pipeline-environment-agnostic`. Its `design.md` Decision 9 argues from the hazard class above and closes only one pairing of it, so the residue is written down rather than left to read as closed.

Separating the plan and apply concurrency groups stops a queued *plan* cancelling a waiting *apply*. It does nothing about an apply cancelling an apply: three merges affecting one environment in quick succession leave the second merge's pending apply liable to be cancelled by the third's, with the same property that makes it worth recording — a cancellation is not a failure, so a change that was reviewed, approved and never applied leaves a run that looks unremarkable.

**This is pre-existing, not introduced.** The workflow-level `concurrency` group that change replaces had the same property at run level; only the granularity moved. It is out of that change's scope for the same reason.

**Mitigation available today:** the nightly drift sweep detects the divergence a cancelled apply leaves behind, within a day, and opens an issue for it. That is the backstop, and it is why this is an entry rather than a change.

**Revisit when** a cancelled apply is actually observed, or when the queue is deep enough that a third merge behind a pending approval stops being unusual — which needs either a busier trunk or an environment whose approval sits unread.

## Promotion ordering between environments is a discipline, not a mechanism

Recorded by `add-a-staging-environment`, whose `design.md` Decision 7 settles it by modifying a requirement rather than implementing one.

*Stack and Module Folder Structure* (`openspec/specs/iac-repo-foundations/spec.md`) used to prescribe that ordered promotion "SHALL be achieved by sequencing apply jobs within a single workflow (lower environment first, then the gated production environment)". At one environment that sentence described nothing. At two it describes a mechanism the apply workflow does not have, so it was unmet the day staging existed.

**It was not implemented, and the reason is not effort.** Sequencing staging's apply ahead of prod's makes prod's apply depend on staging's outcome, which is the coupling *Gated Production Apply Applies the Reviewed Plan* (`openspec/specs/iac-cicd-pipeline/spec.md`) exists to remove: a broken staging would become a reason a correct prod fix cannot reach production. That requirement states the obligation for plans, and it holds here for the same mechanical reason — a stage-scoped dependency cannot tell this environment's outcome from another's.

**What holds instead**, and it is weaker: a merge affecting both environments applies to staging immediately and raises prod's approval at the same time, so promotion ordering is available to prod's approver, who can withhold approval until staging's apply has been seen to succeed. Nothing enforces it. An approver who clicks first gets prod before staging, and no check says so.

**What a future change wanting a mechanism must not do:** reintroduce a dependency between environments' apply jobs, in either direction. If ordering is wanted, it has to come from something that cannot make one environment's failure withhold another's change — a gate on prod's approval that reads staging's last apply, say, rather than a `needs:` between them.

**Revisit when** an approver actually promotes out of order and it matters, or when a third environment makes "lower environment first" ambiguous rather than merely unenforced.

## Three pipeline paths that two environments still do not exercise

Recorded by `add-a-staging-environment`. Its `design.md` Decision 9 lists what that change's own runs confirmed and what they could not, and this is the second half, kept where it outlives the change.

Adding staging is what exercises: discovery emitting two entries, the affected-stack narrowing actually excluding a stack, `secrets[matrix.stack.read_only_secret]` resolving a second name, an ungated apply, and — in the nightly sweep — two stacks planned in one run under two credentials against one heartbeat. Written before those runs happened, and deliberately in that tense: what they actually did is recorded in that change's own task list, and this entry is about the paths they do *not* reach.

Three paths remain unexercised at two environments:

- two plan comments on one pull request;
- two apply jobs in one run;
- one of two applies pausing for its reviewer while the other proceeds.

All three need a merge that affects **both** environments, which means a change under `terraform/modules/`. Manufacturing one — a whitespace edit to a module — was refused deliberately: it would raise a `production` approval with nothing to approve, which *Gated Production Apply Applies the Reviewed Plan* names as the thing that trains an approver to grant without reading. Paying that to test the pipeline would spend the property the pipeline exists to protect.

**Revisit when** the next change under `terraform/modules/` merges, which supplies all three for free. Read its run rather than assuming it: these paths have never run, and the two-environment behaviour of this pipeline is inference until one of them does.

## Four requirements still stated over prod alone

Recorded by `add-a-staging-environment`, which generalised four requirements to every environment and deliberately left these four as they were.

- *Conditional Prod Server Creation* (`openspec/specs/iac-server-lifecycle/spec.md`)
- *Conditional Prod Volume Creation* (`openspec/specs/iac-data-volumes/spec.md`)
- *Data Durability for Stateful Resources* and *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`)

**Two more joined them on 2026-09-10**, added by `configure-the-staging-host` rather than generalised by it, for the reason the "why not swept" paragraph below already gives:

- *Host Joins a Private Tailnet for Non-Operator SSH Access* — "the prod host"
- *Unprivileged Operator Accounts Support Interactive Host Inspection* — "on the prod host"

Both are in `openspec/specs/iac-host-configuration/spec.md`, and both acquire a second subject the moment staging converges with the same role set: a staging host joins the same tailnet and carries the same operator account, and the requirements describing that name only prod. Staging is not converged yet — `configure-the-staging-host` made a converge reachable and left the converge itself to the operator — so at the time of writing these two are in the same position as the four above. They part company from them the moment that run happens, and not before.

The first two describe a mechanism both environments now use: staging declares `server_enabled` and `volume_enabled` with prod's semantics, and its rollback and its cost-pause both rest on them. They are obliged for staging by nothing — the requirements name prod. The last two say "this host", which was unambiguous at one host and is not at two.

**Why not swept.** Nothing on staging contradicts any of them: it holds no store, so the durability and backup requirements have no second subject yet, and the lifecycle toggles are correct at both environments whether or not the requirement says so. Generalising four requirements across three capabilities in a change whose scope was one environment directory would have mixed a mechanical sweep into the diff that most needed reading closely — the same argument the requirement-naming entry above makes.

**Revisit when** staging acquires a persistent store — `docs/change-queue.md` entry 52, which puts the platform stack and a database on it. That is the moment "this host" becomes genuinely ambiguous and the durability requirements have to say which host they mean.

This trigger named entry 50 until 2026-09-10. `configure-the-staging-host` took that entry's host half and deleted it on archiving, and the trigger followed the *subject* rather than the number: a persistent store arrives with the platform stack, which is entry 52's, not with staging's ports opening, which is the web-exposure entry's.

## The stack rename left the word in test identifiers and in specification titles

Recorded by `rename-terraform-environments-to-stacks`, which moved the Terraform root to `terraform/stacks/` and swept the vocabulary that names the unit the pipeline discovers, plans, applies, drift-checks and converges. Three surfaces were deliberately left in the old vocabulary, so that a reader of the tree does not take them for an oversight:

- **`.github/tests` module and method names.** `test_environment_agnostic_pipeline.py`, `test_a_second_environment.py`, `test_planned_environment_apply_stage.py` and `test_host_configuration_names_its_environment.py`, and method names such as `test_a_run_can_also_be_requested_by_hand_for_one_environment`. None of them asserts anything about the word in its own name; renaming them churns several hundred identifiers and changes what no single one checks. Their **literals** were swept — the constants, the path segments and the scratch trees — so the modules assert the new vocabulary under old names.
- **Requirement titles carrying *Environment*.** Renaming a requirement is a `RENAMED` delta, and that change deferred rather than took it. **This bullet is closed**: `rename-the-stacks-and-their-resources` took the rename, as a removal and re-addition rather than a `RENAMED` delta, and moved four titles off the environment axis. Two requirement titles still carry the word — *Host Configuration Names the Environment It Targets* and *Gated Deploy Reuses the Terraform Production Environment* — and both are correct, because each is genuinely about the environment axis rather than about the unit the pipeline iterates.
- **Scenario titles.** Barred by the tool rather than chosen: a `MODIFIED` requirement replaces its block whole, so `openspec validate` reads a renamed scenario as a *dropped* one and refuses the change. A change wanting to rename one needs a mechanism, not an edit. Still open, and it now has a measured cost: thirty citations in this tree name a scenario no specification currently holds. `docs/change-queue.md` carries the entry that would sweep them and extend the retired-name check to the scenario predicate.

The visible cost is roughly twenty-five scenario titles saying *Environment* while the prose under them says *stack* — and the thirty citations of them the bullet above measures — plus a test module named for an axis it no longer asserts.

**What became of its owner.** This section named `docs/change-queue.md` entry 62 as the change that would rewrite it. That change archived as `rename-the-stacks-and-their-resources`, which closed the second bullet above and left the first and third. The first has no owner and wants none: it is a decision to leave several hundred identifiers alone, not work waiting to be done. The third's owner is the queue entry named in its own bullet.


## Loop associations still accumulate, one set per working tree

Recorded by `namespace-the-molecule-loop-devices`, which namespaced the loop device minors `platform_data_volume`'s fixtures claim. It stopped a run inheriting the previous run's device and stopped two working trees sharing one; it did not stop the associations existing after the run that made them.

Nothing detaches a minor at the end of a scenario, so after any suite run this tree's seven associations stand until something removes them by hand, each pinning the inode of a sparse file inside a container that no longer exists. `losetup -a` on a workstation that has run this role shows them, and they are what made the original defect legible in the first place.

**Why not closed.** The obvious remedy is a detach in Molecule's own `cleanup`. What that change was asked not to do was narrower: sweep minors *globally* in `cleanup` or `destroy`, because Molecule runs a role's scenarios sequentially today but may not always, and a teardown detaching a minor another scenario is mid-run on would be worse than the problem it solves. A per-scenario detach of your own minor is not that sweep, and was not ruled out by it. The pointer is stated here rather than aimed at the change-queue entry that said it, because that entry is deleted when this change archives — the same handling *Managing DNS in Terraform* and *Two gaps in required-input validation that only the play could close* already record for entry 50, where the pointer was moved ahead of the deletion rather than left to dangle through it. It was still declined, for two reasons. A run that fails between `prepare` and `cleanup` never reaches it, and while a change is being built a failing run is the common case, so the mechanism would not hold in the condition it exists for. And what it would buy is small: the leak is **bounded** at seven associations per working tree, because the minors are fixed offsets that every run reuses, rather than growing with the number of runs. That boundedness is the same property that argued against allocating minors with `losetup -f --show`, which would have leaked one set per run instead.

This is what `AGENTS.md` already says of namespaces generally — they accumulate, they are named after the tree, and nothing reclaims them. The loop minor is now one more of those.

**Revisit when** a workstation is actually inconvenienced by the accumulation, or when a scenario is added whose `prepare` cannot release its own minor for some reason the current fixtures do not have.

## A check over citations naming a change

Declined 2026-09-13 by `correct-the-documents-against-the-tree`, which built the sibling check over citations naming a **requirement** and measured this one rather than assuming it would work the same way.

`docs/change-queue.md` entry 74 raised it: `docs/bootstrap-a-new-host.md` twice cited a change named `add-a-staging-stack`, which never existed, and no check in this repository could see it. That is the same shape as the requirement-name defect — a citation correct when written and wrong once something it names moves — so the same remedy suggests itself.

**It was declined on a measurement, not on a feeling about false positives.** Sweeping every `entry <N>` and every backticked kebab-case token that resolves like a change name finds forty-odd occurrences, and the overwhelming majority are **historical statements that are correct**: "the former entry 50", "Was `docs/change-queue.md` entry 26, deleted from there and recorded here", "8 by `namespace-the-molecule-suite-per-working-tree`". This file and the change queue are *built* out of such statements — saying what became of a deleted entry is their job. A check reporting them would have to exempt both files entirely, which leaves it reading almost nothing, or carry a per-occurrence exemption list longer than the defect it finds.

**The asymmetry with requirement names is what makes one checkable and the other not.** A retired requirement name has no legitimate use outside a record of its own retirement, and that set was one file and one line when the sibling check was written. A retired change name has many legitimate uses, and they are concentrated in exactly the two files that would have to be exempt.

**Revisit when** a mechanism exists to distinguish a citation from a historical mention — an explicit marker at the citation, or a citation form that a record of a deletion would not match. Without one, the check cannot be written without either blinding itself to the two files where change names are densest or reporting correct prose.
