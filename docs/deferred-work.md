# Deferred work

What this project has deliberately not done, and why. An entry is deleted when
it stops being true. See `AGENTS.md`, "A second change surfacing".

These came out of the full-repository audit on 2026-09-06 (trunk at `245ef59`).
Each was identified as a real observation and then deliberately **not** turned
into a change. Work that is merely waiting on something else belongs in
`docs/change-queue.md`, not here.

---

## Splitting `platform/docker-compose.yml` into multiple files

The file is 602 lines and holds, inline, the Prometheus scrape config, seven
alerting rules, the Alertmanager routing tree, and three Grafana dashboards as
embedded JSON. Editing dashboard JSON inside a YAML `configs:` block inside a
Compose file is genuinely unpleasant, and nothing validates that JSON.

It stays one file because of a deliberate security control, not inertia.
`deploy-receive` (the `Install the deploy-receive script` task in
`ansible/roles/deploy_user/tasks/main.yml`) extracts a
**fixed, explicit two-member list** — `docker-compose.yml` and `.env` — from the
tar it receives. GNU tar with named members extracts only those names and
ignores everything else the archive contains. That is what bounds what a
holder of the platform deploy key can write onto the host.

Carrying additional files would mean widening that member list, and every entry
added to it is a new path an attacker with that key could write to. The
editability gain does not pay for weakening the control.

**Revisit if** the stack outgrows what one file can reasonably hold, or if a
mechanism appears that adds files without widening what the forced command
accepts (a checksummed bundle unpacked into a fixed subdirectory, say). Until
then this is the intended shape, and the inline JSON is its accepted cost.

## Separating `rebuild_protection` from `delete_protection` in `modules/server`

`terraform/modules/server/main.tf:53-54` drives both Hetzner flags from the
single `delete_protection` variable. They are distinct capabilities and a
consumer could in principle want one without the other.

No consumer does. There is one environment, and it wants both. Splitting them
adds a variable, a validation and a test for a case that does not exist, and
the coupled default is the safer one. **Revisit when** a second environment
actually needs them apart — most likely the anticipated staging environment,
which may want rebuild without delete protection.

## Generating Ansible's CIDR variables from Terraform

`ansible/inventory/group_vars/prod.yml:17-20` hand-mirrors
`terraform/environments/prod/terraform.tfvars`'s `ssh_allowed_cidrs` and
`web_allowed_cidrs`. These have drifted once already, and the file's own
comment records what that cost: UFW rules assumed `web_allowed_cidrs` was
unset when it was in fact `["0.0.0.0/0"]`, which would have left the host
firewall blocking traffic the cloud firewall already permitted.

Deriving them from Terraform output would remove the drift class entirely, and
is deliberately not done: it would make an Ansible run depend on Terraform
state and an HCP Terraform token, coupling the two layers that this
repository's structure exists to keep separate. The reasoning is recorded in
`ansible/roles/hardening/README.md`; it is repeated here because the audit
re-surfaced the drift risk as live rather than settled.

**Revisit if** it drifts a second time. One recurrence is evidence the manual
sync does not hold, and would outweigh the coupling objection.

## Host-key verification on the platform deploy

`.github/workflows/platform-deploy.yml:157` runs `ssh-keyscan` into
`known_hosts` on every run — trust-on-first-use, every time, which verifies
nothing about the host's identity.

Accepted, because the connection it protects is already bounded by something
stronger: the runner reaches the host only over the tailnet, having
authenticated to it with an OAuth client scoped to the `production`
Environment, and the key it presents is restricted to a forced command that
accepts no other invocation. An attacker positioned to answer that keyscan is
already inside the tailnet.

**Revisit if** the deploy ever runs over the public internet, at which point
this stops being defence-in-depth and becomes the only check.

## Automatic refresh of the Molecule platform image digest

Every scenario under `ansible/roles/*/molecule/*/` pins its platform image to
`geerlingguy/docker-ubuntu2204-ansible:latest@sha256:0172e3b5…`, and nothing
updates that digest. It will age indefinitely until a person refreshes it by
hand (`ansible/roles/docker/molecule/default/molecule.yml` carries the
procedure).

Dependabot cannot see it: its `docker` ecosystem scans Dockerfiles and Compose
files, not `molecule.yml`. Closing this would mean a bespoke scheduled workflow
that queries the registry, rewrites eight files and opens a pull request —
machinery out of proportion to a test-only base image, and machinery that would
itself need pinning, testing and a credential story.

The trade is deliberate rather than reluctant. A known-stale image the suite
runs against reproducibly is worth more than a current one it cannot make the
same claim about twice; that reproducibility is the whole point of the pin, and
an automatic refresh partly gives it back. The digest is identical across all
eight scenarios and `.github/tests/test_ci_configuration.py` fails the build if
they disagree, so a manual refresh is one find-and-replace, not eight
decisions.

**Revisit if** the image ages far enough that a scenario fails for a reason
traceable to the base image rather than to the role under test, or if this
repository grows a second hand-pinned digest — one is a manageable exception,
two is a pattern that wants a mechanism.

## Two exclusion rules for `ansible/roles/` in the CI test suite

`.github/tests/test_ci_configuration.py` now decides twice, differently, which
directories under `ansible/roles/` are this repository's own. `role_names()`
excludes any name containing a `.` — the Galaxy `namespace.role` convention —
and the newer image-pinning checks exclude names appearing in
`ansible/requirements.yml`'s `roles:` list.

The newer rule is the stronger one: content vendored into `ansible/roles/` that
is *not* pinned in the manifest stays inside the pinning obligation, where the
dot heuristic would silently exempt it. The older rule is adequate for what it
does — reasoning about `ansible-verify.yml`'s role discovery — and the tests
built on it pass.

Unifying them is deliberately not done here. It means editing existing, passing
tests, which is a change of its own rather than a rider on one whose subject is
the pins. **Revisit when** something else needs to reason about that boundary, or
when a directory appears that the two rules would classify differently — at
which point the disagreement stops being theoretical.

## Four shape assumptions in the pull-request-identity checks

`open-autoupdate-pr-with-app-token` added a section to
`.github/tests/test_ci_configuration.py` that discovers every workflow step
opening a pull request and asserts what identity it uses. The discovery and its
helpers make four assumptions that are true of this repository today and would
each produce a **false positive** — a failing build on a legitimate change —
rather than a false negative:

- `token_inputs` reads only step-level `env:`. A pull-request-opening `run:`
  step taking `GH_TOKEN` from a job- or workflow-level `env:`, which is the
  ordinary `gh` idiom, would be reported as having no explicit token.
- `step_opens_a_pull_request` requires a POST and the string `/pulls` somewhere
  in the same `run:` block, not in the same command. `apply.yml` already
  contains `/pulls` twice for read-only fetches; adding any `gh api --method
  POST` to that step would classify a read-only step as one that opens a pull
  request.
- `secrets_referenced_by` scans the whole job rather than the identity path. If
  the `autoupdate` job ever gains an unrelated secret — plausible, given
  change-queue entry 32's alerting proposal — the README tests would demand that
  secret be documented in the same passage as the App credential, which could
  only be satisfied by misdescribing it.
- `readme_sections` splits the README at any line beginning with `#`, including
  inside a fenced code block. Adding a shell snippet with a comment line to the
  section documenting the App would split that passage in two and fail two
  otherwise-correct tests.

None is a defect in what the tests assert; each is a limit on the shapes they
can read. They are recorded rather than fixed because fixing them means editing
passing tests written by an independent author from the delta specs, which is a
change of its own rather than a rider on the one that introduced them.

**Revisit when** any of those four shapes is actually needed — most likely the
`env:` one, the first time a workflow here opens a pull request with `gh`
instead of an action.

## Two properties of the autoupdate workflow that only reading enforces

`open-autoupdate-pr-with-app-token` left `.github/workflows/pre-commit-autoupdate.yml`
carrying two properties its own test section does not assert:

- The minting step's `permission-contents: write` / `permission-pull-requests:
  write` inputs, which down-scope every token it issues. The delta spec's
  clause that the credential carries no authority beyond what the pull-request
  step exercises is *readable* from committed content because of them, but not
  *checked*: an edit dropping those two lines passes the whole suite.
- The restricted input set on the pull-request step. Adding `labels` or
  `assignees` would need Issues, which the App does not hold, and nothing fails
  until the workflow next runs.

Neither is a live risk today: the App's own scope is exactly the two permissions
the inputs name, so dropping them changes nothing until the App is widened. The
exposure is second-order — a later widening of the App plus a later edit here.

Not folded in because a check for either is a test, and this repository has
tests for a change's delta specs written by an author other than whoever wrote
the implementation. Adding them during that change's own build phase would have
inverted that, and neither property has a scenario in the delta to derive from —
they come from a prose clause. The honest options were a test derived properly or
a note; this is the note, and the workflow header says plainly which of its
claims the suite does not stand behind.

**Revisit when** the App's permissions are widened beyond Contents and Pull
requests, which is the moment the exposure stops being second-order — or sooner,
as a small change of its own that adds the scenario and has the assertion derived
from it.

## Automating per-application provisioning in the shared PostgreSQL instance

*Single Shared PostgreSQL Instance, Per-Application Databases*
(`openspec/specs/iac-platform-services/spec.md`) obliges this host to give an
application its own database inside the shared instance when it keeps
non-durable relational data here. Nothing automates that.

Note what is deferred and what is not. The step itself is **defined**:
`docs/bootstrap-a-new-host.md` carries the `CREATE ROLE` / `CREATE DATABASE`
recipe, run from the operator account, and `platform/README.md` documents the
same shape for the `pgexporter` role. What is deferred is the **machinery** — a
script or a deploy-time hook that creates the database and role, and delivers
the credential to the application the way its deploy key is delivered.

It is deliberately not built because no application has ever asked for one. On
2026-09-08 the shared instance held no application database at all, and the only
application on the host keeps its data elsewhere. A provisioning mechanism
designed against no consumer would fix the shape of a credential path, a naming
convention and a failure mode by guesswork, and the guesses would be discovered
wrong by the first real user rather than by review.

**Revisit when** an application actually needs technical storage in the shared
instance. That is the first moment the design has a consumer to be right about;
until then the manual recipe is not a workaround but the whole of what is
needed.

## Managing DNS in Terraform

Was `docs/change-queue.md` entry 26, deleted from there and recorded here on
2026-09-08 when the zone was actually read and the operator decided against the
migration.

The entry assumed the work was a `terraform/modules/` addition and a token
split. Reading the live zone showed why it is not. `shatynska.com` is served by
`ns15`/`ns25`/`ns35.inhostedns.*` — the nameservers of ukraine.com.ua, neither
Hetzner DNS nor Cloudflare — so managing the records in Terraform means moving
the nameservers, not adding a provider. Read on 2026-09-08:

| Record | Value |
|---|---|
| `shatynska.com` A | `2.29.14.98` — the prod host |
| `www` A | `2.29.14.98` |
| `fuperia` A | `2.29.14.98` — the name commerce-ops routes, and what Traefik holds a certificate for |
| `shatynska.com` MX | `mx.ukraine.com.ua` |
| `shatynska.com` TXT | `v=spf1 include:_spf.ukraine.com.ua ~all` |

**The zone carries live mail.** An NS migration moves the MX and SPF records
with it, and a transcription error there stops mail rather than a web service —
a failure that is silent to every check this repository has, because nothing
here monitors mail. That is a different risk class from the one the entry was
weighing, and it is the reason this is deferred rather than queued: the work is
not waiting on another change, it was declined on its merits for now.

**What the original entry was right about.** DNS is still the one piece of the
running system that lives in no repository, and a rebuild (`docs/change-queue.md`
entry 30) or an IPv4 change is still followed by a manual edit nobody has
written down. The table above is the mitigation for the moment: the records are
now recorded somewhere, which is most of what the entry was protecting against.

**Revisit when** a staging environment exists to rehearse the migration against
(`docs/change-queue.md` entry 24), or when mail moves off this zone, or when a
second hostname makes the manual edits frequent enough to be worth the risk.
Cloudflare and Hetzner DNS were the two candidates considered; neither was
chosen, and that choice is still open.

## Four residues of namespacing Molecule per working tree

`namespace-the-molecule-suite-per-working-tree` closed the failure that matters
— a Molecule run reporting success against another session's container. Four
things it deliberately did not close are recorded here rather than in that
change's `design.md`, which is archived with it.

**A run with no namespace still writes to the shared ephemeral directory before
it refuses.** Verified while implementing: a bare `molecule create` in a role
directory resolves its inventory under `~/.ansible/tmp/molecule.<id>.<scenario>`
and only then fails at `create` on the container name. That write cannot produce
a *result* — the run dies before any play — which is why the requirement forbids
sharing state a result could come from rather than sharing anything at all. The
levers that would close it do not exist: Molecule's interpolator has no `:?`
error form, and a guard play would fire at `prepare`, after `create`.

**The entry point is a convention, not a gate.** Nothing stops a session typing
`molecule` directly; the refusing default is what makes that safe rather than
silent. The stronger form considered and not taken was deriving the namespace so
that possessing a valid one implies having used the entry point — rejected
because it spends the legibility that makes `docker ps` answer *whose container
is this*, which is the question the whole change exists to make answerable.

**Namespaces accumulate.** Nothing reclaims the `.molecule-home/` of a removed
working tree, or a container it left behind. Both are named after the tree, so
both are removable by hand; nothing does it automatically, exactly as
`AGENTS.md` says of namespaces generally.

**A working tree renamed or moved after a run orphans its state.** The namespace
is derived from the absolute path, so the old containers and ephemeral
directories become unreachable by the deterministic-resolution guarantee. Rare,
loud, and removable by name.

**Revisit when** a session is actually bitten by one of these, or when Molecule
gains an error form for an unset interpolation.
