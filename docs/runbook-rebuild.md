# Rebuilding a host from a destroyed server

This is the sequence that takes a host of this repository from a destroyed server back to serving what it served before. It is written to be followed in order, under time pressure, by someone who has not read `docs/bootstrap-a-new-host.md` and is not going to read it now.

The commands are written for **`main-staging`**, because that is the stack the rehearsal at the end of this document was performed against, and a command that has actually been executed is worth more than a parameterised one that has not. Where production differs, the difference is stated at the phase it belongs to rather than collected somewhere else — and production has never been rebuilt, so those statements are read rather than run.

**What this document does not hold.** Two recipes belong to other documents and are cited rather than copied here, because a copy of a procedure touching a credential drifts and both copies read as authoritative: the database provisioning recipe, which lives in `docs/onboard-an-application.md`, and the two manual steps of the platform stack, which live in `platform/README.md`. What this document keeps of each is what is genuinely sequence — that it is owed, at which point, and with which secret. The checks' intended settings are likewise a register kept once, in `docs/bootstrap-a-new-host.md`'s Appendix A, and this document cites it rather than restating the values.

**Three phases are the pipeline's — 3, 4 and 10. Every other phase you perform by hand**, and five of them are performed somewhere that is not this repository at all: 5 at the DNS provider, 6 at the tailnet, 12 at the heartbeat observer, 15 in the application's own repository, and 2 partly in your password manager. Read those five before starting: two need a credential that may have expired since it was last used, and one is performed in a repository this one has no authority over.

**This covers the `server_enabled` toggle route**, which is phases 3 and 4. A host rebuilt by *replacing* the server instead enters at phase 5 and follows the rest unchanged — what differs is only the destroy and recreate pair, and what the volume does under it, which phase 3 states.

**Read the rehearsal record at the end before you start.** It says when this was last run, against which stack, and what it was wrong about — and a procedure whose last rehearsal is old is a procedure to read sceptically rather than to follow at speed.

## 1. Know what you are about to lose, and what will start alarming

**Credential:** the operator inspection key, held in `~/.ssh` on your workstation; `gh`'s own token there; this stack's read-only Hetzner token, held in `ansible/.envrc` on that workstation; and the **heartbeat observer's own account**, for the period-and-grace read below. **Phase 2 is what proves that token** — if the inventory read below fails on authentication rather than on the host, go there first and come back. `ansible/.envrc` is per working tree, so a tree cloned since the last rebuild does not have it however well the main checkout is provisioned.

Do this before anything else. Everything below it is recoverable; the contents of this phase are not, and two of them are the kind of loss nobody discovers until weeks later.

**No store on this host needs a restore, and that is a classification rather than a hope.** It is *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) that says so, store by store, and this document derives from it rather than restating its table — read it there if the host has gained a store since this was written. What follows is only the part a rebuild makes real.

**Two stores come back empty and nothing says so at the time.** Prometheus's time-series database is gone, so every metric older than the rebuild is gone with it — the dashboards render, they are simply empty to the left of today. Grafana's UI-created state is gone too: dashboards saved or edited through Grafana's own interface, its users, its preferences and its annotations. What comes back is what this repository provisions, which is the datasource and the committed dashboards. If there is a dashboard on that host somebody built by hand and wants, **export it now**; after the next phase it is not recoverable from anywhere.

**On `main-production` there is a third, and it is not this repository's to fix.** The `commerce-ops` application keeps durable data in a PostgreSQL container of its own on that host, which nothing backs up, and the requirement above records that host as unmet in that one respect rather than describing it accurately. A rebuild of `main-production` loses that data outright. `docs/backlog.md` `move-commerce-ops-durable-data-to-supabase` is what closes it. Until it does, **a production rebuild is not a routine act** and this sentence is the warning.

**Two alarms will fire, both are expected, and neither is muted.** Say so wherever your alerts are read before you start, because the whole design of this system is that a check going quiet is as loud as one that fails:

- `main-staging-alertmanager` is the host's dead-man's-switch. It is fed by Alertmanager's Watchdog every two minutes, so it goes overdue within minutes of the server being destroyed and pages `#alerts` continuously until the platform stack is running again on the rebuilt host — tens of minutes, not minutes. This is the alarm for when everything is down, and during a rebuild everything is in fact down.
- `main-staging-prune-host-images` goes red and stays red until phase 13 triggers an activation by hand. It does not clear on its own.

Do not mute either. A check muted for a rebuild is one nobody re-arms, and an unarmed dead-man's-switch is the failure this entire mechanism exists to prevent.

**Expect the host key to be rejected three separate times later, and know now that it is not a fault.** A rebuilt host is a new machine presenting a new key on every identity you reach it by, and each one fails only when that identity is first used — spread across phases 7, 8 and 10, which is why it otherwise reads as three unrelated problems:

- **the public address**, where Hetzner hands the same one back — which it may do, and did in the rehearsal, when the destroy and the create are minutes apart;
- **the tailnet name**, at phase 8;
- **the tailnet address**, behind any `~/.ssh/config` alias — accepting the key under the *name* does not record it for the *address*, so this one fails separately after the other two are cleared.

`ssh-keygen -R <the identity>` clears each, and you accept the new key on the next connection. Do not disable the check to get past it.

**Then capture the pre-state**, because "serving what it served before" is not checkable afterwards unless you wrote down what "before" was:

```sh
ssh shatynska-main-staging 'hostname; docker ps --format "{{.Names}}\t{{.Status}}"'
ssh shatynska-main-staging 'docker exec platform-prometheus-1 wget -qO- \
  "http://localhost:9090/api/v1/targets?state=active"' | \
  python3 -c 'import json,sys; [print(t["labels"]["job"], t["health"]) for t in json.load(sys.stdin)["data"]["activeTargets"]]'
curl -sS -o /dev/null -w '%{http_code}\n' https://commerce-ops.main-staging.fincci.bike/health
cd ansible && ansible-inventory -i inventory/main-staging.hcloud.yml --list | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["_meta"]["hostvars"]["main-staging"]["hcloud_ipv4"])'
ssh shatynska-main-staging 'ls -l /dev/disk/by-id/ | grep HC_Volume'
```

**Read `hcloud_ipv4` and not `ansible_host`.** They are the same value on a workstation and are not the same field: `ansible_host` is composed from `HCLOUD_CONNECT_WITH`, which the converge workflow sets to `hostname`, so a shell with that variable exported hands back a name where phases 7 and 9 need an address.

**`terraform output` is not the way to read these**, and it is worth knowing before you reach for it: every stack declares an HCP Terraform backend, so `terraform output` needs `terraform init` first, and on a workstation whose HCP credential belongs to another organisation `init` fails with *organization "shatynska" at host app.terraform.io not found*. The inventory read above needs only the read-only Hetzner token. The volume id is on the host as `scsi-0HC_Volume_<id>`, and after the rebuild it is in the apply run's log or the Hetzner console.

**Probe `/health`, not `/`, and know what a bare 404 does not prove.** This application answers **404** at `/` by design — it has no route there — so `/` reads like a failure and tells you nothing. Worse, **Traefik's own 404 is indistinguishable by status code**: a router that never matched, because DNS is stale or the certificate did not issue or the application's labels did not come back, answers 404 too. The discriminator is the `server:` header — the application answers `server: uvicorn`, Traefik answers its own. So probe a path the application really serves, and where you do read a 404, read the header with it:

```sh
curl -sS -D- -o /dev/null https://commerce-ops.main-staging.fincci.bike | grep -i '^server:'
```

Record the container set and their health, the active scrape targets, the public IPv4, the volume id, the host's tailnet address, and every hostname that resolves to this server. `dig` may not be installed; `python3 -c 'import socket; print(socket.gethostbyname("<name>"))'` answers the same question.

**Tell whoever owns each application on this host that the window is opening.** Their deploys fail for its whole length, and the failure looks like a network fault in *their* repository rather than like something you did: the deploy job cannot reach a host that does not exist, and cannot reach a rebuilt one until the converge puts it back on the tailnet. Two `commerce-ops` deploys failed exactly that way during the rehearsal recorded below. Nothing here notices or reports it, and `docs/backlog.md` `announce-a-rebuild-to-the-applications-that-hold-databases` is the entry for making it a mechanism rather than a message. Also read this stack's two checks at the heartbeat observer and write down the period and the grace each currently carries — phase 12 compares against them, and the register is a claim about the observer's configuration until somebody has actually looked.

## 2. Confirm the credentials the sequence needs, by using them

**Credential:** the staging Vault password and the Tailscale auth key, both held in the password manager, and this stack's read-only Hetzner token, held in `ansible/.envrc`.

Three of the phases below fail late and confusingly if a credential has gone stale, and all three can be checked in under a minute now:

```sh
cd ansible
source .envrc
ansible-inventory -i inventory/main-staging.hcloud.yml --graph
```

**`source .envrc` rather than `direnv allow`, and the difference matters when you are pasting a block.** `.envrc` is plain exports, so sourcing it works in any shell, immediately. `direnv allow` only *authorises* the file — the export happens the next time direnv's hook fires, which is at your next interactive prompt, so in a pasted block the line after it still runs without the token, and in a shell with no direnv hook installed it never fires at all.

**Do not skip this. It is the step most often skipped and the one the rehearsal was caught by.** `ansible/.envrc` is per working tree and is not loaded by being present: without it the run fails with `Invalid Hetzner Cloud API Token: unable to authenticate` and `Completely failed to parse inventory source`. That is what an unprovisioned shell looks like, and meeting it here costs a minute where meeting it at phase 7 costs a half-finished converge. **If the file does not exist at all** — a working tree cloned since the last rebuild has none — copy `ansible/.envrc.example` and fill in both read-only tokens before going on.

That proves the read-only Hetzner token parses and reaches the right project. A failure names the source it could not parse rather than resolving to an environment with no host in it — `ansible.cfg`'s `any_unparsed_is_failed` is what makes that true, and without it the play would report success having converged nothing, which is byte-identical to a play against the host you have just destroyed.

**The Vault password.** Decrypt something with it rather than believing you have it. **Not with `ansible-vault view`**: this repository encrypts individual values with `encrypt_string`, so `group_vars/staging.yml` is plaintext YAML holding two `!vault |` scalars, and `view` rejects it with *Input is not vault encrypted data* whether your password is right or wrong. Force the decryption through a lookup instead, which is what the converge workflow's own preflight does:

```sh
cd ansible
ansible staging -i inventory/main-staging.hcloud.yml -c local -m debug \
  -a "msg={{ hostvars[inventory_hostname] | to_json | length }}" --vault-id staging@prompt
```

Run it only once the `--graph` above has listed a host: `ansible <group>` against a group matching nothing reports success having run nothing, which is a pre-flight that cannot fail. `SUCCESS` and a number means the password decrypted the file. A wrong one fails with *Attempt to use undecryptable variable*. The `| to_json` is what forces every value to be rendered, so do not drop it — without it the encrypted scalars are never touched and the check passes on any password at all.

**The Tailscale auth key is the one that bites.** It is reusable and expires after ninety days, and a rebuild is typically when that expiry is discovered.

**There may be more than one, and only their descriptions tell them apart.** `docs/bootstrap-a-new-host.md` §5.3 records one reusable key serving both hosts, and permits a second outright — "if you want to revoke one host's join without touching the other" — so a tailnet holding one key per stack is correct and is not what this phase assumes. Read the descriptions; take this stack's. **Where it is unclear, generate a fresh one**: it costs nothing, and a single-use key is burnt by the first join, so a rebuilt host needs one anyway.

Check its expiry in the Tailscale admin console and mint a fresh one if it has lapsed — phase 7 passes it on the command line, there is no prompt for it, and the role has no default, so a missing key fails inside `tailscale` after two roles have already changed the host.

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

**A red check on this pull request is worth reading twice before you act on it.** `validate` initialises and validates *every* stack, not only the one you touched, so it can fail on a registry timeout against a stack this change does not go near — `could not connect to registry.terraform.io: read: connection reset by peer` is what that looks like. Check which stack the failure names: one you did not touch is the registry, and a re-run of the failed job is the whole remedy. This is the pull request whose merge destroys a host, so it is the worst one to misread as "something about my change is wrong".

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

**First check whether the address actually changed, because it may not have.** Compare what phase 4 read back with what phase 1 recorded. There is no floating IP, so the address is the server's own — but Hetzner hands the same one back when the destroy and the create are close together, and it did exactly that in the rehearsal below. **If the address is unchanged, this phase is a no-op and you should skip it**: every record already points where it should, and re-entering a correct value at a DNS provider can only introduce an error.

If it did change: the records live at a third-party DNS provider and in no repository — deliberately, because the zone carries live mail that an NS migration would move.

Edit, at the provider, every record aimed at this server: the wildcard `*.main-staging.<base domain>`, the bare `main-staging.<base domain>`, and any short alias pointing at it. `docs/bootstrap-a-new-host.md` §4.4 gives the zone's shape; **neither it nor this document is a register of the zone's contents** — read the zone at the provider and edit what is actually there, rather than working from the list phase 1 had you record or from any example here.

The distinction, since this document does name one live hostname: a **published application hostname** is a fact about what the system serves, and phase 16 has to check it. The zone's **records and the addresses they carry** are the provider's, change on every rebuild, and are written down nowhere here on purpose.

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

**This is where the host key is first rejected, and it surprised the rehearsal.** A genuinely new address carries no `known_hosts` entry — but the address may have been reused, and then the entry is stale and this connection fails with `REMOTE HOST IDENTIFICATION HAS CHANGED!`. That is what happened. Clear it and accept the new key:

```sh
ssh-keygen -R <the public ipv4>
```

Phase 1 lists all three surfaces this happens on; this is the first of them, not the exception to them.

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

**Credential:** the converge key's **public** half and the operator root key, both held in `~/.ssh`. The private half is deliberately **not** on your workstation — stage 0.3 has you delete it once it is stored, and from then on it lives write-only in the stack's GitHub Environment. That is what decides how this phase is checked.

The rebuild cost the host its converge key, and nothing reinstalls it. Run this from a machine on the tailnet — the same route CI takes:

```sh
ssh-copy-id -f -i ~/.ssh/shatynska-ansible-ci-main-staging.pub \
  -o IdentityFile=~/.ssh/shatynska-root root@main-staging
```

**`-f` is load-bearing and is not a convenience.** Without it `ssh-copy-id` refuses with `ERROR: failed to open ID file '…/shatynska-ansible-ci-main-staging': No such file` — it wants the **private** half to verify the pair even when handed the public one, and that half was deleted when it was stored. So the command fails for precisely the operator who followed the bootstrap, and the error names a file they were told to remove. `-f` skips the verification and installs the public key, which is all this step needs.

**This reaches the host by its tailnet name, which is the second of the three host-key surfaces phase 1 lists** — `main-staging` is the same name on a new machine, and `ansible.cfg` sets `host_key_checking = True`. Expect `Host key verification failed` or `REMOTE HOST IDENTIFICATION HAS CHANGED`; clear it with `ssh-keygen -R main-staging` and accept the new one. **The third surface is separate and catches people out**: the `shatynska-main-staging` alias resolves to the tailnet *address*, and accepting the key under the name does not record it for the address, so `ssh-keygen -R <the tailnet ipv4>` is owed as well. Do not disable the check to get past any of them.

Then prove the key is usable, by making the pipeline use it:

```sh
gh workflow run host-converge.yml --ref main -f stack=main-staging
```

**That dispatch is the check and it is not optional**: a key installed but not usable fails at the next merge touching `ansible/`, long after you have stopped watching. It is also the only check available to you, and the reason is worth stating so that nobody restores the shorter one: the obvious test is `ssh -i ~/.ssh/shatynska-ansible-ci-main-staging root@main-staging true`, and **you cannot run it** — that private half was deleted when it was stored, and the only copy is the Environment secret the pipeline reads. The dispatch exercises exactly that copy, which is the one that has to work.

**Then read it, by phase 10's recipe** — `gh workflow run` prints no run id and returns before the run exists, so take the id of the run whose `createdAt` is after your dispatch and `gh run watch <id>`. A dispatch nobody reads is not a check. What you want is a green run; `changed=0` is the expected result and not a sign it did nothing, because this is the same play phase 7 has just run by hand.

**`--ref main` is your own discipline here, not the workflow's.** Phase 10's deploy refuses a dispatch from any other ref before it names an Environment; this workflow has no such guard, so a dispatch from an unmerged branch would converge a real host with unreviewed Ansible. `docs/backlog.md` `guard-the-converge-dispatch-to-the-default-branch` is the entry for closing that.

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

**Credential:** the operator inspection key, held in `~/.ssh`, to reach the host — and nothing you have to look up. The values this step needs are `PLATFORM_POSTGRES_USER` and `PLATFORM_POSTGRES_EXPORTER_PASSWORD`, whose canonical home is the password manager since an Environment secret cannot be read back; but the running exporter already holds the second, which is how `platform/README.md` has you take it.

The shared instance came back empty, so the monitoring role it holds came back with it. Both steps are `platform/README.md`'s, under *Monitoring and alerting*, and are performed from there rather than copied here. What matters at this point in the sequence:

**You do not need to fetch the password.** `platform/README.md` gives the form that reads it from the exporter container, which is already running with that stack's value and is the authoritative copy — so the secret is never fetched, pasted or mistyped. Use that, and do not paste a password into this shell.

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

Nothing here can trigger these. For each application on this host, go to that application's own Actions. **How you start it is that application's business and may not be a button**: `commerce-ops`'s `Deploy` workflow triggers on `push` to `main` and declares no `workflow_dispatch`, so there is no Run workflow to click and looking for one wastes time.

**Re-running the last `Deploy` run is the route that belongs in a rebuild** — it redeploys the commit already on `main`, where pushing would mean inventing a commit to trigger a deploy:

```sh
gh run list --repo <org>/<app> --workflow Deploy --limit 3
gh run rerun <id> --repo <org>/<app>
```

**A failed run from during the window is expected and is the one to re-run.** A deploy that landed while the host was destroyed or not yet on the tailnet fails at `Connect to the tailnet` with `Ping host *** did not respond`. That is this rebuild's doing, not a fault in that application.

**If the last run is too old to re-run**, GitHub having dropped that ability with the run's logs, the remaining route is a push to that repository's `main` — and the two conditions correlate, since a host rebuilt after a long quiet period is one whose last deploy is old. The obligation is unchanged either way: this phase is that application's to satisfy, and this document can only say that it is owed.

If a deploy fails at connection time, phase 9's `DEPLOY_HOST` is the first thing to check. If it starts and then fails against the database, phase 14 either did not run for that application or its rotation half-completed — the recipe's own failure section covers that case.

## 16. Confirm the host is serving what it served before

**Credential:** none.

Against what phase 1 recorded, not against what looks reasonable:

```sh
curl -sS -o /dev/null -w '%{http_code}\n' https://commerce-ops.main-staging.fincci.bike/health
ssh shatynska-main-staging 'docker ps --format "{{.Names}}\t{{.Status}}"'
```

- every hostname that resolved before resolves now, over TLS on a freshly issued certificate;
- the same containers are running and healthy, eight of them from the platform stack plus each application's own;
- all five scrape targets report `up`;
- both checks at the observer are green, on the settings phase 12 confirmed;
- the applications answer, and their data is what phase 14 and phase 15 put back — which for an application whose database was re-provisioned means empty, by design.

A host that is up and serving nothing it served before has not finished this sequence.

## Rehearsal record

Last rehearsed: 2026-09-16
Duration: 57 minutes
Stack: main-staging
Corrected: twelve steps, listed below

Performed against `main-staging` by the `server_enabled` toggle route, from the merge that destroyed the server to the confirmation that the host was serving what it served before.

**Phase 2 was skipped**, and the run met at phase 7 exactly what phase 2 exists to catch — that is correction 8 below, and it is the clearest evidence in this record that phase 2 earns its place. Every other phase was performed in order. Where the text was wrong, the step above is what was corrected, and this list says what was wrong with it.

1. **The serving probe read `/`**, which this application answers 404 by design — and Traefik's own 404, from a router that never matched, is indistinguishable by status code. Phases 1 and 16 now probe `/health` and read the `server:` header.
2. **`dig` was not installed** on the operator's workstation. A `python3` one-liner is given instead.
3. **Phase 1's credential line omitted the heartbeat observer's account**, which the same phase needs for the period-and-grace read.
4. **`validate` failed transiently on a stack the change did not touch.** It validates every stack; the remedy is a re-run, and phase 3 now says so — it is the pull request whose merge destroys a host and the worst one to misread.
5. **The public address did not change.** Hetzner handed the same one back seven minutes after the destroy, so phase 5 was a no-op. It is written as conditional now, because a slower rebuild would get a new one.
6. **The host key was rejected three times, not once** — at the reused public address, at the tailnet name, and at the tailnet address behind a local alias, which the name's entry does not cover. Said once in phase 1 with all three named.
7. **There was one auth key per stack**, which §5.3 permits, where phase 2 assumed the documented single key. Descriptions are what tell them apart.
8. **The converge failed at inventory parse** because `direnv` was not active. Phase 2 now leads with `source .envrc`, which works in a pasted block where `direnv allow` does not, and names the failure it prevents.
9. **`ssh-copy-id` refused** without the private half the bootstrap has you delete. `-f` is what it needs, and it is now in the command.
10. **Phase 11 did not need the password manager.** The exporter container already holds the value; it is read on the host and piped into `psql`, never entering a shell history.
11. **Phase 15 named a button that does not exist.** That application's deploy has no `workflow_dispatch`; re-running the last run is the route.
12. **The rebuild broke two deploys in another repository**, failing at `Connect to the tailnet` with a cause that reads as a network fault in *their* history. Phase 1 now says to tell each application's owner the window is opening.

**One thing the rehearsal confirmed rather than corrected**, recorded because its absence would read as an omission: the tailnet address moved even though the public one did not, and phase 9's three holders — the two Environment secrets and `~/.ssh/config` — were all owed. That step was already right, because code review had found the third holder missing before the rehearsal ran.

**What the rehearsal found beyond the sequence, before anything was destroyed.** Three live defects, none of which any check in this repository could have reached, because all three lived in per-stack GitHub Environment secrets that no committed file can see: both hosts pinged one dead-man's-switch check, so production's liveness alarm was masked; both posted alerts through one webhook into one channel in the **staging** workspace, so production's alerts had never reached the Slack its operator watches; and a rotated secret does not reach its container on a deploy, which is why the first two survived being fixed until the config block was edited. The first two are fixed. The third is `docs/backlog.md` `make-a-rotated-secret-reach-its-inline-config`.

**What the duration does and does not say.** Fifty-seven minutes is one operator on one stack with this document in front of them. It is not the number for an unrehearsed rebuild, and it is not production's: production has a reviewer on both applies, a `destroy-override` label to apply before merging, delete protection to clear, and an application whose durable data no backup covers.

### How this record is written

The record is always in exactly one of three states, and a later editor moves it between them rather than inventing a fourth. Each is told apart by the value of one line and the presence of one block, so that a reader and a check reach the same answer:

- **Never rehearsed.** `Last rehearsed: never`, and no `Partial run:` block. Written out rather than left as a blank date, because a blank field is indistinguishable from one somebody forgot to fill in and the two mean opposite things.
- **Partially rehearsed.** A run began and did not reach a serving host. `Last rehearsed:` still reads `never` — a run that did not complete rehearsed nothing — and a `Partial run:` block is added carrying `Reached:`, `Wall clock:` and `Stopped by:`. A partial run is worth recording and is not evidence that the procedure works.
- **Rehearsed.** `Last rehearsed:` carries the date, beside `Duration:`, `Stack:` and `Corrected:`. No `Partial run:` block.

A rehearsal is a run of this whole sequence against a real host, beginning with its server destroyed and ending with it serving what it served before. Reading the steps is not a rehearsal. A rehearsal is performed against a stack whose loss is tolerable and never against one whose loss is not.

**Where a rehearsal finds a step wrong, missing or out of order, correct the step above** rather than noting it here. The record says *what* was corrected; the corrected procedure is what the next reader needs, and an erratum is not that.
