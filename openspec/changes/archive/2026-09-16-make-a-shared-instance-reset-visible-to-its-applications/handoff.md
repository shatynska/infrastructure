# Handoff: make a shared-instance reset visible to its applications

Opened on 2026-09-16 by the operator, from `docs/backlog.md` entry `make-a-shared-instance-reset-visible-to-its-applications` and a request arriving from the `commerce-ops` repository. It has no proposal yet; whoever takes it writes one.

The backlog entry is the full account of why this exists and is not restated here — read it first, in full. What this handoff adds is the consumer that turned up after it was written, the amendments that consumer's request needs before any of it can be built, and the design questions that are still open.

## What was asked for, and by whom

The `commerce-ops` repository's `move-production-into-the-shared-instance` change asked this repository, on 2026-09-16, for a read-only forced command its deploy can call **before it delivers**. Their contract as they sent it:

| | |
|---|---|
| name | `deploy-probe commerce-ops`, on a key of its own — not a second command on the deploy key, since an `authorized_keys` entry carries one `command=` |
| input | JSON on stdin: `{"database": "...", "role": "...", "password": "..."}` — nothing in argv, because a command line lands in `ps` |
| what it does | connects to the shared instance from inside `platform_edge` as that role, and checks whether `alembic_version` exists and carries a row |
| output | exactly one token: `populated`, `empty`, `credential-refused`, or `unreachable` |
| must not | deliver, deploy, or write anything, in any database |

**That request is this change's second design option arriving as a concrete consumer**, not a separate favour. The backlog entry leaves open "whether the signal is an announcement made at window time or a marker an application's deploy reads before it delivers"; a probe the application calls before delivering is the second. Building it as an ad-hoc accommodation would settle that question outside the change that owns it, and would settle it against the one consumer that exists — which is the fitted-to-one-consumer trap both this entry and `automate-per-application-database-provisioning` record, met a third time.

They accepted proceeding without this and without `automate-per-application-database-provisioning`, and asked for an estimate on both. There is none to give: at the time of opening, neither had a branch and nothing was in flight on either.

## Three amendments the contract needs, and they are not negotiable style points

**The application name may not arrive as data.** *Restricted Deploy Account Supports Per-Application Forced-Command Deploys* (`openspec/specs/iac-host-configuration/spec.md`) requires that an application name reach a privileged script "only via a value fixed ahead of time by which key connected and which `sudoers` rule matches, never as data supplied by the connecting client at connection time". `deploy-probe commerce-ops` already carries the name, and `docs/onboard-an-application.md` §3.2 names both the role and the database after the application — so both are derivable and neither may be read off stdin. Accepted as sent, the probe is an off-host password-checking oracle against every role in the shared instance, `platform_admin` and `pgexporter` included, usable by whoever holds the probe key at whatever rate they like. Derive both from the forced command's argument, or accept the fields and refuse unless they equal it. Either way the input reduces to the password.

**`alembic_version` may not be a literal in this repository.** It is one application's migration tool's bookkeeping table, and a host-configuration script that names it is fitted to that application. Take the marker table from stdin alongside the password and resolve it through `to_regclass`, so the name cannot be injected and an unknown one is an ordinary answer rather than an error. This costs nothing and is what lets the next application supply its own marker.

**Four tokens are one short, and the missing distinction is the whole incident.** After the volume is discarded the role is *absent*, and PostgreSQL reports that identically to a wrong password — which is why 2026-09-15 surfaced in the other repository as `password authentication failed for user "commerce-ops"` four and a half hours after its cause. So `credential-refused` would mean "the instance was reset" and "your password is stale" indistinguishably, and the application cannot tell which. A probe that returns it is still worth more than nothing — it fails the deploy at the right moment instead of leaving a crash loop — but it does not by itself discharge what this change is for.

## What is still open, and has to be decided here

**Whether the signal is an announcement or a marker, and the backlog entry's own list of what a change owes.** Take that list as the starting point rather than this section.

**Where a marker can live, given that anything inside the volume goes with it.** The entry states the bind: anything outside the volume has to be re-created by the same step that re-creates the role, and nothing survives the reset that a later deploy could read.

**One candidate worth checking early, because it would dissolve the third amendment above rather than working around it.** The probe script runs as `root` on the host, so it can read the instance's own identity without any credential at all — `pg_controldata`'s cluster system identifier, which a re-`initdb` changes and an ordinary restart does not. A probe reporting that identifier alongside its token would let an application compare it with the one it last saw and distinguish "this instance was re-initialised" from "my password is stale", with nothing written anywhere and no credential involved. **This is inference from PostgreSQL's documented behaviour and has not been executed** — verify it against the running instance before designing on it, and check what the value costs to expose to a key holder (the reading here is: nothing, but that is a reading).

**What the application does on finding the marker absent or stale** is the other repository's, not this one's, but the answer shapes the contract. `commerce-ops`'s deploy already refuses to deliver when its own configuration is wrong, which is the behaviour to design against.

**What this change does not take on.** `automate-per-application-database-provisioning` is the durable fix for *recurrence* and is a separate entry. This is the half that survives it being built, since a mechanism re-provisioning on a schedule of its own still leaves a gap between the reset and the re-provisioning. Do not fold it in.

## What it must not undo

- **The two layers that pin an application name.** A forced command and a fully-qualified `sudoers` rule, independently, both naming the application. `deploy_user`'s tasks and `add-per-app-deploy-keys`'s design are where that is argued; the probe adds a third script and a second rule to the same pattern and must not weaken it.
- **`deploy` is not in the `docker` group**, and must not be put there. It reaches the runtime only through `sudo /usr/local/bin/app-deploy <app>`, fully qualified. A probe that needs the runtime needs a rule of its own — `/usr/local/bin/app-probe <app>`, or whatever it is called — on exactly that pattern, and the SSH-layer half stays `deploy`-owned the way `deploy-receive` is.
- **The instance superuser's credential never reaches the probe path.** `PLATFORM_POSTGRES_PASSWORD` belongs to this repository's own stack secrets and never reaches an application; a probe invoked over an application's key is an application path.
- **`restrict` on every key on the `deploy` account.** The requirement above states it as an invariant over *every* key, not over deploy keys — a probe key carrying `command=` without `restrict` breaches it, and it is asserted in that requirement's own scenarios.
- **Do not widen `deploy-receive`'s member list**, and do not give the probe a way to write anything anywhere. The comment above that task in `deploy_user`'s tasks says what that list bounds and why the platform stack is one 600-line file because of it.
- **Do not fix the key-per-environment problem here.** `deploy_apps` lives in `ansible/inventory/group_vars/<environment>.yml`, so an entry there authorises its key on every host in that environment; a probe key added the same way inherits exactly that. `docs/backlog.md` `bound-a-deploy-key-to-one-host-when-an-environment-holds-two-stacks` is that change, a branch for it already exists on the workstation, and this one should not pre-empt its layout decision — add the probe key on whatever shape `deploy_apps` has when this is implemented, and say in the proposal that it inherits the same bound.
- **Do not hardcode the PostgreSQL image pin.** It is `postgres:18.6` in `platform/docker-compose.yml` today and Dependabot proposes the next one. If the probe needs a client, take the image from the running container rather than from a second copy of the pin.
- **Do not let the probe's answer depend on the deploy having run.** It is called *before* delivery; that is its point.

## Facts you will need

| | |
|---|---|
| the account | `deploy`, home `/opt/platform`, group `deploy`, no `docker` group, shell `/bin/bash`, password `!` |
| the existing shape to copy | `deploy-receive <app>` (SSH-layer, `deploy:deploy` 0755, reads stdin) → `sudo /usr/local/bin/app-deploy <app>` (root, fully-qualified `sudoers.d/app-deploy-<app>`) |
| where keys are declared | `deploy_apps` in `ansible/inventory/group_vars/<environment>.yml`, one entry per application, public half committed |
| key naming | `docs/onboard-an-application.md` §2.1 — `~/.ssh/<company>-<app>-<environment>`, comment `<app>-deploy-<environment>`; a probe key needs a convention of its own and §2.1 is where it goes |
| the instance | container `platform-postgres-1`, Compose project `platform` under `/opt/platform`, `postgres:18.6`, no published host port, reached at `postgres:5432` over the external `platform_edge` network |
| the role and database | both named after the application; the password lives in that application's own Environment under a name that repository chooses — `SHARED_POSTGRES_PASSWORD` for `commerce-ops`, because its `POSTGRES_PASSWORD` was already taken |
| the window this exists for | `platform/README.md`, *Upgrading the PostgreSQL major version* — step 5 re-provisions every application database and redeploys, from a workstation, with `rotate=yes` |
| what already gates that window | step 2's pin pull request opens as a **draft**, so GitHub refuses the merge until the operator marks it ready. Step 5 has no gate, and it is step 5 that was not run on 2026-09-15 |
| the reporting path this replaces | this repository learnt of the 2026-09-15 breakage from `Fuperia-IT/commerce-ops` |

## The tests it will owe

Three commands, per `AGENTS.md`'s table, and this change plausibly touches two of them. A role's behaviour on a host — that the probe exists, that its key carries `restrict` and its own forced command, that it writes nothing, that it refuses a name it was not invoked with — is Molecule, under `ansible/roles/deploy_user/molecule/<scenario>/`, and it is the only tier that can observe the refusal path. A static read of a committed file — the `sudoers` line's shape, a key declared without its probe counterpart, the image pin not being duplicated — is `.github/tests/*.py`. Dispatch the test author with the row that fits, not with the Terraform row.

## Read before starting

`AGENTS.md`; `docs/backlog.md` entries `make-a-shared-instance-reset-visible-to-its-applications`, `automate-per-application-database-provisioning`, `bound-a-deploy-key-to-one-host-when-an-environment-holds-two-stacks` and `hold-every-platform-deploy-for-the-length-of-a-window`; *Restricted Deploy Account Supports Per-Application Forced-Command Deploys* (`openspec/specs/iac-host-configuration/spec.md`) in full, with its scenarios; *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`); `platform/README.md`'s *Upgrading the PostgreSQL major version*; `docs/onboard-an-application.md` §2 and §3; and `add-per-app-deploy-keys`'s design, which is where the two-layer pinning and the `restrict` decision were argued.
