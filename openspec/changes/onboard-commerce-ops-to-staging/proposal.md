## Why

Staging has run the shared platform stack since `deploy-the-platform-stack-per-environment` archived on 2026-09-13, which made `platform-deploy.yml` deploy to every stack whose `pipeline.yml` declares `deploys_platform: true`. The operator now wants `commerce-ops` on that host too, as a rehearsal of the application before production changes are made to it.

It cannot deploy there today. `deploy_apps` in `ansible/inventory/group_vars/staging.yml` enumerates `platform` alone, so the staging host has no `/opt/commerce-ops`, no forced-command `authorized_keys` line for a `commerce-ops` key, and no `/etc/sudoers.d/app-deploy-commerce-ops`. A deploy attempt is refused at the SSH layer — the key authenticates as nothing — which is not a firewall problem and is not fixed by opening a port.

That absence was deliberate when the file was written, and the file says so: `commerce-ops` had no staging deploy path in its own repository, and an enumerated application with no Compose file on the host implies an authorisation nothing uses. The operator is now building that deploy path, so the reason has expired and the enumeration is what has to move first: the `deploy_apps` entry needs a converge before the application's own deploy can authenticate, so the application repository waits on this pull request rather than the reverse.

## What Changes

- Add a `commerce-ops` entry to `deploy_apps` in `ansible/inventory/group_vars/staging.yml`, carrying the public half of a **staging-only** keypair generated for this change — not production's `commerce-ops` keypair.
- Correct the comment above that list, which states that `commerce-ops` is deliberately absent and why. This change makes that sentence false, and it is the sentence a later reader would take as authority for removing the entry.
- Correct `docs/backlog.md` entry 17 (`expose-staging-on-the-web`), which rests its "nothing to serve" argument on staging enumerating `platform` alone. Its trigger — an application reaching staging — is approaching and **not** met: the authorisation lands here, the deploy is still outstanding, and an entry rewritten as though the trigger had fired would license opening both layers in front of a Traefik that still routes nothing, which is the state entry 17's own text warns against. It should say what is now outstanding rather than what has just stopped being true.
- Correct `docs/backlog.md` entry 51's claim that an application on a host with no public hostname is testable over the tailnet with a `Host:` header. It is false for the same reason the note at the end of this proposal gives, and entry 51 is the list the extracted onboarding document will be written from — so a false bullet there becomes the procedure.
- Correct `docs/bootstrap-a-new-host.md` §0.3's key table, the paragraph above it and §0.4's sentence pointing at it, all of which say **one deploy key per application**. After this change the true shape is one per application per environment — the axis the `group_vars` file carrying the entry is named for, and the axis the committed keys already follow. Left as they are, those lines instruct the next onboarding to install one private half on both hosts — the outcome this change's own keypair decision exists to prevent.
- Add one line to `docs/backlog.md` entry 51's list of what the extraction has to fix: stage 8.4's `production`-Environment sentence is falsified by the same thing its stage 8.2 parenthetical is, and that list is what an extraction reads.
- Record `docs/backlog.md` entry 52, `revoke-an-application-s-deploy-authorisation`: `deploy_user` never removes what a deleted `deploy_apps` entry once produced, so revocation is a host edit rather than a commit. Surfaced by this change's Migration Plan and not fixed by it.

No role, playbook, task, template or workflow changes. This change adds committed data to an inventory file, corrects the prose that described its absence and the two lines that would misdirect the next onboarding, and records one identified change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — `skip_specs: true` is set in this change's `.openspec.yaml`. The mechanism that turns a `deploy_apps` entry into a `/opt/<name>` directory, an `authorized_keys` line and a sudoers rule is already specified as *Restricted Deploy Account Supports Per-Application Forced-Command Deploys* (`openspec/specs/iac-host-configuration/spec.md`) and already implemented by the `deploy_user` role; this change supplies that mechanism with one more input on one more host and changes nothing about what it does with it. The prune's behaviour towards an enumerated application that has never deployed is likewise already specified — *Unreferenced Host Images Are Pruned on a Schedule*, scenario "An application that has never deployed does not abandon the run" — so this change does not introduce that case either.

## The store, which this change does not bring and does not classify

*No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) requires a store added outside this repository to state which of its reasons it satisfies **in the change here that records it**. This section is where a reader will look for that, so it says plainly why it is not here.

**This change puts no store on the staging host.** It authorises a deploy; it deploys nothing, provisions no database, and leaves the host with one empty `/opt/commerce-ops` directory. The store arrives with the application's own deploy, and what classifies it — the decision already taken, that staging's `commerce-ops` takes a database inside the shared PostgreSQL instance and runs no PostgreSQL container of its own, on the ground that staging holds rehearsal data whose loss is tolerable — belongs to the change that provisions it, along with the observation that would catch a private PostgreSQL arriving anyway.

**That is a split rather than a deferral, and the reason is the specification's own.** Provisioning a database inside the instance is deliberately not automated *because no application has needed one*, and *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) says automating it, and delivering the credential with it, SHALL be done when the first application does. Provisioning staging's database is therefore not a task that can be ticked quietly inside an inventory change: it falsifies that requirement's stated premise and brings its SHALL due, which is a specification delta and the tests that follow one. Folding it in here would mean a change that edits one inventory line and silently modifies a capability.

So it is opened as a change of its own — branch `provision-commerce-ops-database-in-the-shared-instance`, with a `handoff.md` carrying the decision, the recipe, the delta it owes and the two defects found in that recipe while reading it. **This change does not depend on it; the rehearsal does.** The application cannot serve a request until its database exists, so that change is on the path to the rehearsal even though it is not on the path to this merge.

## Impact

- `ansible/inventory/group_vars/staging.yml`: one `deploy_apps` entry and the comment above it.
- `docs/backlog.md`: entry 17's premise, two edits to entry 51 — its `Host:`-header bullet and one line added to its list of what the extraction must fix — and a new entry 52.
- `docs/bootstrap-a-new-host.md`: §0.3's application-deploy-key row, the paragraph above the table, and the sentence in §0.4 that points at it.
- On merge, `host-converge.yml` runs (it triggers on `ansible/**`) and creates the three host objects named above on the staging host. It matrixes over every stack, so a production converge is queued too — a no-op, `production.yml` being unchanged, but one that sits pending until someone approves it.
- The staging image prune is unaffected. An enumerated application with no Compose file on the host contributes nothing to the keep set; staging's prune currently reports `considered 8`, `removed 0`, and any later movement in that number is the application deploying, not a fault.

## Out of scope

Named because each is a thing a reader may expect to find here and each is somewhere else:

- **The private half**, which becomes a `COMMERCE_OPS_DEPLOY_SSH_KEY` Environment secret in the `commerce-ops` repository, and the staging deploy path that repository needs (an Environment, a workflow, `DEPLOY_HOST = 100.85.219.36`). That repository is not this one's to change. **Hand it over only once `provision-commerce-ops-database-in-the-shared-instance` has landed**, and that ordering is load-bearing rather than tidiness: see the risk it closes in design.md. Merging this change does not start a clock — the authorisation sits unused until the private half moves, which is the one point in the sequence this repository still controls.
- **Staging's web ports and DNS**, `docs/backlog.md` entry 17, and **any tailnet-scoped allow for port 80**. Both layers stay `[]`, and the deploy is observed from the host itself rather than across the tailnet — see the correction below, which is the reason this bullet now names two things instead of one.
- **The database staging's `commerce-ops` will use**, and everything the specification attaches to provisioning one — the change opened for it is named in the store section above.
- **Moving `commerce-ops`'s durable data off a host**, `docs/backlog.md` entry 19; the migration is work in the application's repository.
- **Writing application onboarding as its own document**, `docs/backlog.md` entry 51 — whose recommendation is to write it from this onboarding, immediately after it, rather than to fold it in.

**A correction worth stating, because the obvious test does not work.** Traefik does route on the `Host` header, which invites the conclusion that a deploy to staging is testable from any tailnet device with `curl -H "Host: …" http://100.85.219.36/`. It is not. UFW's default-deny applies to `tailscale0` exactly as it does to the public interface: 80 and 443 are opened only from `hardening_web_allowed_cidrs`, which is `[]` here, and the role's two tailnet exceptions are hard-coded for 22 and 3000 — the second of them added by `add-grafana-tailnet-ufw-rule` for precisely this surprise. A request from a tailnet peer to port 80 is dropped. The observation that does work runs **on** the host, over the operator's SSH session, against the loopback interface UFW does not filter; tasks.md 5.3 gives it.
