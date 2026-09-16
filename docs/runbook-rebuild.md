# Rebuilding a host from a destroyed server

This is the sequence that takes a host of this repository from a destroyed server back to serving what it served before. It is written to be followed in order, under time pressure, by someone who has not read `docs/bootstrap-a-new-host.md` and is not going to read it now.

The commands are written for **`main-staging`**, because that is the stack the rehearsal will be performed against. **Until the record at the end of this document carries a date, every command here has been read back against the file that declares it and the sequence has not been executed** — treat it accordingly. Where production differs, the difference is stated at the phase it belongs to rather than collected somewhere else.

**What this document does not hold.** Two recipes belong to other documents and are cited rather than copied here, because a copy of a procedure touching a credential drifts and both copies read as authoritative: the database provisioning recipe, which lives in `docs/onboard-an-application.md`, and the two manual steps of the platform stack, which live in `platform/README.md`. What this document keeps of each is what is genuinely sequence — that it is owed, at which point, and with which secret. The checks' intended settings are likewise a register kept once, in `docs/bootstrap-a-new-host.md`'s Appendix A, and this document cites it rather than restating the values.

**Three phases are the pipeline's — 3, 4 and 10. Every other phase you perform by hand**, and five of them are performed somewhere that is not this repository at all: 5 at the DNS provider, 6 at the tailnet, 12 at the heartbeat observer, 15 in the application's own repository, and 2 partly in your password manager. Read those five before starting: two need a credential that may have expired since it was last used, and one is performed in a repository this one has no authority over.

**This covers the `server_enabled` toggle route**, which is phases 3 and 4. A host rebuilt by *replacing* the server instead enters at phase 5 and follows the rest unchanged — what differs is only the destroy and recreate pair, and what the volume does under it, which phase 3 states.

## 1. Know what you are about to lose, and what will start alarming

**Credential:** the operator inspection key, held in `~/.ssh` on your workstation; `gh`'s own token there; and this stack's read-only Hetzner token, held in `ansible/.envrc` on that workstation. **Phase 2 is what proves that token** — if the inventory read below fails on authentication rather than on the host, go there first and come back. `ansible/.envrc` is per working tree, so a tree cloned since the last rebuild does not have it however well the main checkout is provisioned.

Do this before anything else. Everything below it is recoverable; the contents of this phase are not, and two of them are the kind of loss nobody discovers until weeks later.

**No store on this host needs a restore, and that is a classification rather than a hope.** It is *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) that says so, store by store, and this document derives from it rather than restating its table — read it there if the host has gained a store since this was written. What follows is only the part a rebuild makes real.

**Two stores come back empty and nothing says so at the time.** Prometheus's time-series database is gone, so every metric older than the rebuild is gone with it — the dashboards render, they are simply empty to the left of today. Grafana's UI-created state is gone too: dashboards saved or edited through Grafana's own interface, its users, its preferences and its annotations. What comes back is what this repository provisions, which is the datasource and the committed dashboards. If there is a dashboard on that host somebody built by hand and wants, **export it now**; after the next phase it is not recoverable from anywhere.

**On `main-production` there is a third, and it is not this repository's to fix.** The `commerce-ops` application keeps durable data in a PostgreSQL container of its own on that host, which nothing backs up, and the requirement above records that host as unmet in that one respect rather than describing it accurately. A rebuild of `main-production` loses that data outright. `docs/backlog.md` `move-commerce-ops-durable-data-to-supabase` is what closes it. Until it does, **a production rebuild is not a routine act** and this sentence is the warning.

**Two alarms will fire, both are expected, and neither is muted.** Say so wherever your alerts are read before you start, because the whole design of this system is that a check going quiet is as loud as one that fails:

- `main-staging-alertmanager` is the host's dead-man's-switch. It is fed by Alertmanager's Watchdog every two minutes, so it goes overdue within minutes of the server being destroyed and pages `#alerts` continuously until the platform stack is running again on the rebuilt host — tens of minutes, not minutes. This is the alarm for when everything is down, and during a rebuild everything is in fact down.
- `main-staging-prune-host-images` goes red and stays red until phase 13 triggers an activation by hand. It does not clear on its own.

Do not mute either. A check muted for a rebuild is one nobody re-arms, and an unarmed dead-man's-switch is the failure this entire mechanism exists to prevent.

**Then capture the pre-state**, because "serving what it served before" is not checkable afterwards unless you wrote down what "before" was:

```sh
ssh shatynska-main-staging 'hostname; docker ps --format "{{.Names}}\t{{.Status}}"'
ssh shatynska-main-staging 'docker exec platform-prometheus-1 wget -qO- \
  "http://localhost:9090/api/v1/targets?state=active"' | \
  python3 -c 'import json,sys; [print(t["labels"]["job"], t["health"]) for t in json.load(sys.stdin)["data"]["activeTargets"]]'
curl -sS -o /dev/null -w '%{http_code}\n' https://commerce-ops.main-staging.fincci.bike
cd ansible && ansible-inventory -i inventory/main-staging.hcloud.yml --list | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["_meta"]["hostvars"]["main-staging"]["hcloud_ipv4"])'
ssh shatynska-main-staging 'ls -l /dev/disk/by-id/ | grep HC_Volume'
```

**Read `hcloud_ipv4` and not `ansible_host`.** They are the same value on a workstation and are not the same field: `ansible_host` is composed from `HCLOUD_CONNECT_WITH`, which the converge workflow sets to `hostname`, so a shell with that variable exported hands back a name where phases 7 and 9 need an address.

**`terraform output` is not the way to read these**, and it is worth knowing before you reach for it: every stack declares an HCP Terraform backend, so `terraform output` needs `terraform init` first, and on a workstation whose HCP credential belongs to another organisation `init` fails with *organization "shatynska" at host app.terraform.io not found*. The inventory read above needs only the read-only Hetzner token. The volume id is on the host as `scsi-0HC_Volume_<id>`, and after the rebuild it is in the apply run's log or the Hetzner console.

Record the container set and their health, the active scrape targets, the public IPv4, the volume id, the host's tailnet address, and every hostname that resolves to this server. Also read this stack's two checks at the heartbeat observer and write down the period and the grace each currently carries — phase 12 compares against them, and the register is a claim about the observer's configuration until somebody has actually looked.

## 2. Confirm the credentials the sequence needs, by using them

**Credential:** the staging Vault password and the Tailscale auth key, both held in the password manager, and this stack's read-only Hetzner token, held in `ansible/.envrc`.

Three of the phases below fail late and confusingly if a credential has gone stale, and all three can be checked in under a minute now:

```sh
cd ansible && ansible-inventory -i inventory/main-staging.hcloud.yml --graph
```

That proves the read-only Hetzner token in `ansible/.envrc` parses and reaches the right project. A failure here names the source it could not parse rather than resolving to an environment with no host in it.

**The Vault password.** Decrypt something with it rather than believing you have it. **Not with `ansible-vault view`**: this repository encrypts individual values with `encrypt_string`, so `group_vars/staging.yml` is plaintext YAML holding two `!vault |` scalars, and `view` rejects it with *Input is not vault encrypted data* whether your password is right or wrong. Force the decryption through a lookup instead, which is what the converge workflow's own preflight does:

```sh
cd ansible
ansible staging -i inventory/main-staging.hcloud.yml -c local -m debug \
  -a "msg={{ hostvars[inventory_hostname] | to_json | length }}" --vault-id staging@prompt
```

Run it only once the `--graph` above has listed a host: `ansible <group>` against a group matching nothing reports success having run nothing, which is a pre-flight that cannot fail. `SUCCESS` and a number means the password decrypted the file. A wrong one fails with *Attempt to use undecryptable variable*. The `| to_json` is what forces every value to be rendered, so do not drop it — without it the encrypted scalars are never touched and the check passes on any password at all.

**The Tailscale auth key is the one that bites.** It is reusable and expires after ninety days, and a rebuild is typically when that expiry is discovered. Check its expiry in the Tailscale admin console and mint a fresh one if it has lapsed — phase 7 passes it on the command line, there is no prompt for it, and the role has no default, so a missing key fails inside `tailscale` after two roles have already changed the host.

You also need push access to this repository, and — for phase 15 — access to the application's own repository. Confirm both now.

## 3. Destroy the server

**Credential:** none. The write token lives only in the stack's GitHub Environment and never reaches a workstation.

There is no `workflow_dispatch` on the apply workflow: it triggers on a push to `main` under `terraform/**`. So destroying the server is a merge.

Open a pull request setting `server_enabled = false` in `terraform/stacks/main-staging/terraform.tfvars`:

```hcl
server_enabled = false
```

**Read the plan comment before merging.** It should destroy exactly three things — the server, its firewall, and the volume — and leave `hcloud_ssh_key.this` alone, which is not gated on the toggle and is deliberately owned by the stack so that it outlives the server. Record the whole plan summary rather than only those three.

**The volume goes with the server on this route**, and that is the answer for the toggle route specifically: the volume has no location of its own, so its `count` depends on both toggles. A *replace* of the server is a different question — the volume's count does not turn on the server's identity, so a replace leaves it as an attachment whose `server_id` changes — and nothing in this repository has observed that route. Do not read the toggle's answer across to it.

Merging applies immediately: `main-staging`'s GitHub Environment requires no reviewer, and its `pipeline.yml` sets `destroy_policy_gate: false`.

**On `main-production` both of those are different.** Its Environment requires a reviewer, so the apply waits; and its destroy-policy gate applies, so **the pull request must carry the `destroy-override` label before it is merged** — the gate reads the labels of the merged pull request, and a label added afterwards does nothing for a run already going. Its server also carries `delete_protection` and `backups`, which must be considered before either is toggled.

## 4. Recreate the server

**Credential:** this stack's read-only Hetzner token, held in `ansible/.envrc`, for reading the new address back. The write token that applies the change is confined to the stack's GitHub Environment, exactly as in phase 3.

Open a second pull request setting the same value back to `true`:

```hcl
server_enabled = true
```

Over phases 3 and 4 together the net change to `terraform.tfvars` is zero, which is how you can tell you have finished them correctly.

The apply creates a new server and a new volume. **Both have new identities**: a new public IPv4, and a new volume id — the on-host device path is derived from that id, which is why the mount is by-id and why nothing needs editing for it. Record both, reading the address the same way phase 1 did:

```sh
cd ansible && ansible-inventory -i inventory/main-staging.hcloud.yml --list | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["_meta"]["hostvars"]["main-staging"]["hcloud_ipv4"])'
```

The volume id is in the apply run's log, or in the Hetzner console. Re-enabling needs no configuration to be reconstructed. If the plan wants to create anything you did not expect, or wants to re-import a key, stop and read it rather than approving.

## 5. Point the DNS at the new address

**Credential:** the DNS provider's own account, held in the password manager.

The server's address changed, and there is no floating IP. The records live at a third-party DNS provider and in no repository — deliberately, because the zone carries live mail that an NS migration would move.

Edit, at the provider, every record aimed at this server: the wildcard `*.main-staging.<base domain>`, the bare `main-staging.<base domain>`, and any short alias pointing at it. `docs/bootstrap-a-new-host.md` §4.4 gives the zone's shape; **it does not give the live values, and neither does anything else here** — read the zone at the provider rather than trusting any written record of it.

Certificates reissue on their own once the applications redeploy, provided the names resolve to the new address first. Doing this now rather than later is what keeps phase 16 from failing on a certificate that could not be issued.

## 6. Delete the dead machine from the tailnet

**Credential:** the Tailscale admin console, held in the password manager.

This is not optional and it is not tidying. Tailscale deduplicates machine names by suffixing, so the rebuilt host joins as `main-staging-1` while the dead node keeps `main-staging` — indefinitely, because key expiry was disabled on it. The converge workflow looks its target up by that bare name, so every later converge resolves to a peer that no longer exists and fails at the host-key step with a message that reads as an unreachable host rather than as a rebuild artefact.

In the Tailscale admin console, Machines, delete the old `main-staging` node. Do it now, before phase 7 joins the new one.

## 7. Converge the host from your workstation

**Credential:** the staging Vault password and the Tailscale auth key, both held in the password manager, and the operator root key, held in `~/.ssh`.

**This is the one time running `ansible-playbook` against a host is correct** rather than a sign that something was left unfinished. The converge pipeline reaches a host over the tailnet, and joining the tailnet is what this play does — so the first converge of a rebuilt host cannot be the pipeline's.

Record the host key first, or the play stops at connection time before a single role runs:

```sh
ssh -i ~/.ssh/shatynska-root root@<the new public ipv4>
```

**The old entry in `known_hosts` is now wrong**, and this is the failure most likely to cost you time here: the address may be new, but if anything resolves to a name you have connected to before, `ansible.cfg` sets `host_key_checking = True` and the run dies with `Host key verification failed`. Remove the stale entry rather than disabling the check.

Then converge:

```sh
cd ansible
ansible-playbook playbooks/host-baseline.yml \
  -i inventory/main-staging.hcloud.yml \
  -e target_environment=staging \
  --vault-id staging@prompt \
  --private-key ~/.ssh/shatynska-root \
  -e tailscale_auth_key=<the key from phase 2>
```

Do not add `--limit`: it filters the guard play's `localhost` out. A second run should report `changed=0`.

**If it fails partway inside the `tailscale` role**, the output is masked by `no_log` and will not tell you why. `docs/bootstrap-a-new-host.md` §6.3a has the on-host recovery. The usual cause is the auth key phase 2 was supposed to have checked.

Afterwards, in the Tailscale admin console: confirm the host is listed under the bare name `main-staging`, note its tailnet IPv4, and **disable key expiry on it** — this is per node, so the rebuilt node does not inherit it.

## 8. Hand the converge back to the pipeline

**Credential:** the converge keypair, held in `~/.ssh`, and the stack's GitHub Environment.

The rebuild cost the host its converge key, and nothing reinstalls it. Run both lines from a machine on the tailnet — the same route CI takes:

```sh
ssh-copy-id -i ~/.ssh/shatynska-ansible-ci-main-staging.pub \
  -o IdentityFile=~/.ssh/shatynska-root root@main-staging
ssh -i ~/.ssh/shatynska-ansible-ci-main-staging root@main-staging true
```

**The second line is the check and it is not optional**: a key installed but not usable fails the pipeline rather than this phase, where you are watching.

The Environment secrets survive a rebuild and do not need re-entering, so there is no `gh secret set` here — phase 9 is where one is. If you are rebuilding a host whose keypair was also lost and you re-enter `ANSIBLE_SSH_PRIVATE_KEY`, note that `--env` takes the **GitHub Environment's** name, which is `main-staging` — the stack's name, not the Ansible group `staging` that the `--vault-id` and `group_vars` take. A mistyped value fails with a `404` rather than silently.

## 9. Update the two addresses the rebuild invalidated

**Credential:** the stack's GitHub Environment, and the application's own Environment in its own repository.

The host's tailnet address changed, and **three** things hold it. Two are secrets; the third is on your own workstation and nothing will remind you of it:

```sh
gh secret set PLATFORM_DEPLOY_HOST --env main-staging
```

That value is read twice by the platform deploy — as the SSH target and as Grafana's bind address — so **it must be a tailnet address and never a public one**, or that stack's Grafana is published on the public interface.

Then the same address as `DEPLOY_HOST` in each application's own repository, one per deploy target. For `commerce-ops` that is its `staging` Environment. Phase 15 fails at connection time if this is missed, in a way that reads like a network problem.

**Third, your own `~/.ssh/config`.** The `ssh shatynska-main-staging` alias that phases 1, 10 and 16 use is a workstation-local convenience declared in no committed file. If its `HostName` pins the old address, those phases fail with a connection error that reads as the host being down. Update it, or drop the alias and use the tailnet name.

## 10. Deploy the platform stack

**Credential:** none at your end — the nine `PLATFORM_*` secrets are held in the stack's GitHub Environment and are read only by the deploy job.

Dispatch the deploy for **this stack alone**. Re-running the last run would redeploy every stack and wake another stack's approval gate for a host that did not change:

```sh
gh workflow run platform-deploy.yml --ref main -f stack=main-staging
```

**Take the run id from Actions, or wait for one newer than the dispatch.** `gh workflow run` returns as soon as the dispatch is accepted, before the run exists — so `gh run list --limit 1` immediately afterwards commonly hands back the *previous* run, whose green result reads as this deploy's:

```sh
sleep 10
gh run list --workflow platform-deploy.yml --event workflow_dispatch --limit 3 \
  --json databaseId,status,createdAt
```

Take the id of the run whose `createdAt` is after your dispatch, and watch that one: `gh run watch <id>`.

It runs only from the default branch, and refuses before naming any Environment if dispatched from another.

**Ordering matters here and only in one direction: the converge must have happened first**, and phases 7 and 8 are why it has. The host layer creates what the platform layer mounts. A deploy that lands before the converge binds a path that does not exist yet, and Docker creates it as an empty root-owned directory on the root disk rather than failing — so every container comes up healthy and empty, the later converge mounts the volume over the top, and nothing about the symptom points at the cause.

Confirm eight `platform-*` containers, all healthy:

```sh
ssh shatynska-main-staging 'docker ps --format "{{.Names}}\t{{.Status}}"'
```

## 11. Redo the two manual steps the automation deliberately does not do

**Credential:** `PLATFORM_POSTGRES_USER` and `PLATFORM_POSTGRES_EXPORTER_PASSWORD`, held in the stack's GitHub Environment.

The shared instance came back empty, so the monitoring role it holds came back with it. Both steps are `platform/README.md`'s, under *Monitoring and alerting*, and are performed from there rather than copied here. What matters at this point in the sequence:

- **The `pgexporter` monitoring role** must be recreated inside the new Postgres container, with this stack's own exporter password. **Nothing alerts if you skip it**: the exporter answers HTTP 200 with `pg_up 0`, and the alert that would catch a dead target fires on the target being absent, not on it being wrong. Its check is `pg_up 1` and `pg_exporter_last_scrape_error 0`.
- **The dead-man's-switch registration** is already done on a rebuild — the check exists and its URL is unchanged. What is owed is confirming pings have resumed, which is phase 12.

## 12. Re-read this host's checks at the observer

**Credential:** the heartbeat observer's own account, held in the password manager.

These steps are performed at the heartbeat service — healthchecks.io or whatever equivalent this deployment uses — and not in this repository. A check that was re-created by its own first ping carries the **observer's default** rather than the value its reporter needs, which means a perfectly healthy weekly job is called overdue within a day and an operator learns to ignore the list.

For each of this host's two checks — `main-staging-alertmanager` and `main-staging-prune-host-images` — confirm it is receiving pings again, and confirm its period and its grace are the ones the register records. **The register is `docs/bootstrap-a-new-host.md`'s Appendix A**, which holds those settings once for every check this system has; read them there rather than from memory, and rather than from any copy.

`main-staging-alertmanager` should clear on its own within a few minutes of phase 10 completing. `main-staging-prune-host-images` will not; phase 13 is what clears it.

**Where what you find at the observer differs from what the register records, the register is what is right and the observer is what you correct.** That is the whole reason this phase exists: a check re-created by its own first ping carries the vendor's default, so a disagreement here is the expected damage of a rebuild rather than news about what the settings should be. Set the observer to the register's values. Do not edit the register to match what you found — that writes the vendor default into the one place this repository says what a check's settings should be, and the next rebuild then has nothing to compare against.

The opposite reading applies only at phase 1, before anything is destroyed: a disagreement *there* is between two claims about a running system, and is worth settling in the register's own pull request before you go on.

## 13. Trigger one image prune, so its check goes green

**Credential:** the operator root key, held in `~/.ssh`.

The prune timer is weekly, so its check stays red until the next firing — a host rebuilt on a Saturday leaves a red check until the following Saturday with nothing wrong, which is exactly the shape of alarm people learn to skip.

```sh
ssh -i ~/.ssh/shatynska-root root@main-staging \
  'systemctl start prune-host-images.service; \
   journalctl -u prune-host-images.service -n 25 --no-pager'
```

Read it for `prune-host-images: considered N, removed 0, refused 0` with N at least 1. An **`abandoned`** line means the keep set is empty, which at this point in the sequence means an enumerated application is rendering no image reference — worth chasing before phase 16. `considered 0` is a different statement: it counts the images the host holds, and `considered 0, removed 0, refused 0` is byte-identical to a healthy run over a host with nothing to reclaim, which is not what you should see here.

Read that journal as `root`. The unprivileged inspection account is in `docker` and in neither `systemd-journal` nor `adm`, so the same command as that account prints `-- No entries --`, which is indistinguishable from a unit that has never run.

## 14. Re-provision each application's database

**Credential:** the operator key held in `~/.ssh`, and `gh`'s token on your workstation.

The shared PostgreSQL instance came back empty. Every application holding a database in it lost that database — which its classification tolerates — but it cannot start without one, so this comes **before** that application's deploy and not after.

Use the provisioning recipe in `docs/onboard-an-application.md`, which is where it lives and where it is maintained. Two things about using it here rather than at onboarding:

- **`rotate=yes` is required**, not optional. The secret still exists in that target's Environment while the role does not, so the block refuses with `rotate=no` — correctly, since that guard exists to stop an accidental rotation.
- **It is pasted on your workstation, not on the host.** It calls `gh` and then reaches the host over `ssh` itself; pasted into a session on the host it aborts at the first `gh` and changes nothing.

On `main-staging` there is exactly one such application, `commerce-ops`. The `platform` entry beside it in `deploy_apps` holds no database and never should — do not run the recipe for it.

## 15. Deploy each application from its own repository

**Credential:** held in that application's own repository, one set per deploy target — nothing in this repository can reach them.

Nothing here can trigger these. For each application on this host, go to that application's own Actions and run its deploy for this target. For `commerce-ops` that is its own repository and its `staging` environment.

If a deploy fails at connection time, phase 9's `DEPLOY_HOST` is the first thing to check. If it starts and then fails against the database, phase 14 either did not run for that application or its rotation half-completed — the recipe's own failure section covers that case.

## 16. Confirm the host is serving what it served before

**Credential:** none.

Against what phase 1 recorded, not against what looks reasonable:

```sh
curl -sS -o /dev/null -w '%{http_code}\n' https://commerce-ops.main-staging.fincci.bike
ssh shatynska-main-staging 'docker ps --format "{{.Names}}\t{{.Status}}"'
```

- every hostname that resolved before resolves now, over TLS on a freshly issued certificate;
- the same containers are running and healthy, eight of them from the platform stack plus each application's own;
- all five scrape targets report `up`;
- both checks at the observer are green, on the settings phase 12 confirmed;
- the applications answer, and their data is what phase 14 and phase 15 put back — which for an application whose database was re-provisioned means empty, by design.

A host that is up and serving nothing it served before has not finished this sequence.

## Rehearsal record

Last rehearsed: never

This procedure has been collated from the pieces that were already written down, and every command in it was read back against the file that declares it — but the sequence as a whole has not yet been run against a host. Until the line above carries a date, this document is a plan and not evidence.

### How this record is written

The record is always in exactly one of three states, and a later editor moves it between them rather than inventing a fourth. Each is told apart by the value of one line and the presence of one block, so that a reader and a check reach the same answer:

- **Never rehearsed.** `Last rehearsed: never`, and no `Partial run:` block. Written out rather than left as a blank date, because a blank field is indistinguishable from one somebody forgot to fill in and the two mean opposite things.
- **Partially rehearsed.** A run began and did not reach a serving host. `Last rehearsed:` still reads `never` — a run that did not complete rehearsed nothing — and a `Partial run:` block is added carrying `Reached:`, `Wall clock:` and `Stopped by:`. A partial run is worth recording and is not evidence that the procedure works.
- **Rehearsed.** `Last rehearsed:` carries the date, beside `Duration:`, `Stack:` and `Corrected:`. No `Partial run:` block.

A rehearsal is a run of this whole sequence against a real host, beginning with its server destroyed and ending with it serving what it served before. Reading the steps is not a rehearsal. A rehearsal is performed against a stack whose loss is tolerable and never against one whose loss is not.

**Where a rehearsal finds a step wrong, missing or out of order, correct the step above** rather than noting it here. The record says *what* was corrected; the corrected procedure is what the next reader needs, and an erratum is not that.
