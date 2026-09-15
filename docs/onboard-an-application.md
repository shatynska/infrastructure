# Onboarding an application

Adding one service to a host that already runs the platform stack. `docs/bootstrap-a-new-host.md` stands a host up and hands over to this document; you do not need to have read it, and nothing here assumes you are bootstrapping anything.

`commerce-ops` is the worked example throughout. Where a step says `<app>`, it is that application's name.

## The unit of work is a cell, not an application

An application is onboarded **per deploy target**: `commerce-ops` on staging and `commerce-ops` on production are two runs of this document, not one. Each cell needs a keypair of its own, an entry in that environment's `group_vars`, a deploy job in the application's own repository, and that repository's Environment for that target.

Two axes are in play and they are not the same axis, which is the single thing most worth getting right before you start:

- **The environment** — `production`, `staging` — is what the infrastructure side sits on. `deploy_apps` lives in `ansible/inventory/group_vars/<environment>.yml`, so an application's deploy key, its `authorized_keys` line and its `sudoers` rule are one set per application per environment.
- **The stack** — `main-production`, `main-staging` — is what this repository's own GitHub Environments, Hetzner projects and Terraform state sit on. The application's repository never sees a stack name.

Today each environment holds exactly one stack, so the two coincide and nothing distinguishes them. They stop coinciding the moment a second tenant exists, and `docs/naming-conventions.md` is where the scheme is written down.

**What repeats, and what does not:**

| Step | How often |
|---|---|
| 1. The name | once per application |
| 2. The deploy authorisation on the host | once per application per environment |
| 3. The database | once per application per deploy target, if it needs one at all |
| 4. The application's own repository | the repository once; the Environment, the secrets and the deploy job once per deploy target |
| 5. The public hostname | once per deploy target |

## 1. The name

The application's name in `deploy_apps` and the last segment of its image repository must be identical: an application named `orders` publishes to `ghcr.io/<org>/orders`. Image reclamation on the host identifies an application's images by that rule and silently reclaims nothing if they differ.

**The coupling is exact and it fails quietly**, which is why it is the first thing here. The namespace is `ghcr.io/<owner>/<app>:<tag>` — exactly two path segments after the registry, the last equal to the name `app-deploy` was invoked with, and any owner. An application deployed as `foo` whose images live at `ghcr.io/<owner>/bar`, and one publishing to a deeper path such as `ghcr.io/<owner>/foo/api`, each have an **empty** namespace: they reclaim nothing at all, indistinguishably from an application that had nothing to reclaim. Its disk fills instead, one image per deploy. *Superseded Application Images Are Reclaimed at Deploy Time* (`openspec/specs/iac-host-configuration/spec.md`) is the requirement.

## 2. Authorise the deploy on the host

One pass per environment the application deploys to.

### 2.1 Generate that cell's deploy key

    ssh-keygen -t ed25519 -f ~/.ssh/<company>-<app>-<environment> -N "" -C "<app>-deploy-<environment>"

Passphrase-less, because continuous integration cannot type one. One key per application per environment, never one shared: the public half is committed in that environment's `group_vars`, and one leaked private half must deploy to one host.

**Into `~/.ssh/`, never into this checkout.** The key has no passphrase, and a routine `git add -A` in a repository directory is one command away from publishing it. Write the path out in full rather than generating where you happen to be standing. What stands behind you if you slip is `gitleaks`, which reads the content at commit time — and only once `pre-commit install` has been run, per README's Local setup. `.gitignore`'s private-key block is **not** a second net for this key: its patterns were written for an older naming scheme and do not match `<company>-<app>-<environment>` (`docs/backlog.md` carries the entry that closes that).

**Check:** `ssh-keygen -lf ~/.ssh/<company>-<app>-<environment>.pub` prints a fingerprint. Keep it — §2.2 commits the public half and §4.2 stores the private one, and the fingerprint is how you tell two of these apart afterwards. The comment is a label for a human reading the file and nothing reads it mechanically.

**The comment convention, and the two committed entries that predate it.** An application's key carries `<app>-deploy-<environment>` and the platform's carries `deploy@platform-<environment>`, so a `group_vars` entry says which cell it authorises. Production's two entries are older than the second host and carry no environment segment at all — `deploy@platform` and `commerce-ops-deploy` in `ansible/inventory/group_vars/production.yml`, against `deploy@platform-staging` and `commerce-ops-deploy-staging` in `staging.yml`. They are left as they are: rewriting a committed comment converges both hosts to change a label nothing reads, and a key is identified by the fingerprint above. Read production's two as legacy rather than as a second convention.

### 2.2 Add the entry, and let a converge install it

Add to `deploy_apps` in `ansible/inventory/group_vars/<environment>.yml`:

```yaml
- name: <app>
  public_key: "ssh-ed25519 AAAA... <app>-deploy-<environment>"
```

Open a pull request and merge it. Merging to `main` with anything under `ansible/` changed runs the gated host converge, which installs `/opt/<app>`, the forced-command `authorized_keys` line, and the `sudoers` rule that lets that key trigger `app-deploy <app>` and nothing else. Production's converge waits for your approval; nothing announces that it is waiting, so watch for it.

**The order matters and it only works one way round.** The entry needs a converge before the application's own deploy can authenticate, so an application repository that is ready first waits on an infrastructure pull request — never the reverse.

**An entry with nothing deployed behind it is a normal state, not a fault.** Between this step and the application's first deploy, the host authorises a key for an application whose images it has never pulled. Such an application contributes nothing to the image prune's keep set, which is correct: the prune enumerates applications from this version-controlled list and protects the images each one currently references, and an application referencing none protects none. *Unreferenced Host Images Are Pruned on a Schedule* (`openspec/specs/iac-host-configuration/spec.md`) is the requirement.

**Check**, from a session on that host: `sudo ls /opt/<app>` exists, and `sudo grep <app> /etc/sudoers.d/app-deploy-<app>` shows the fully-qualified invocation.

### 2.3 Let the host pull the image

Ensure the GHCR user the host authenticates as can read the application's package. In an organisation, a package pushed by a workflow inherits the repository's access; a machine user needs read access to that repository. `ansible/roles/deploy_user/README.md` explains what happens when this is wrong, and why the converge stays green when it is.

## 3. The database

Skip this section entirely if the application keeps no relational data on this host. An application that keeps none is not owed a database.

### 3.1 The decision, before the command

This is settled, and the answer depends on one question about the data: would losing it be tolerable?

- **Durable data** — anything whose loss would not be tolerable — goes to an **external managed service that owns its own backups**, not onto this host. Never into the shared instance: that is absolute, and no backup lifts it, because holding only non-durable data is what makes that instance classifiable as needing none. Not into a PostgreSQL container of the application's own either, unless a logical backup written off the host and a restore rehearsed and checked are both in place before the data lands — *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) is where that is written, and no application has cleared that bar.
- **Non-durable relational data** — a job table, bookkeeping, state whose loss its writer can shrug at, and anything an application keeps in its database on a **staging** host, where the operator is the only party writing it and its loss is tolerable to the operator — goes in the **shared instance**, never a container of the application's own. That part is unconditional: no backup licenses a private PostgreSQL. Where an application's tables divide, only the non-durable ones go here, and the change in this repository that records the database states which are which; a table that division does not name stays out until one does. Never copy production data into a staging instance.

A **non-relational** store — a Redis cache, a queue file, an uploads directory — is not covered by either bullet and does not belong in this instance. It is governed by *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) like any other store on this host, which is to say: name which of its reasons the store satisfies, in the change that adds it, or give it a logical backup written off the host and a rehearsed restore before it holds anything.

### 3.2 Provision the role, the database and the password

Provision one role and one database, named after the application, **once per deploy target**. The application's repository needs that target's Environment first (§4.1): the recipe stores the password there, and stops before changing anything if the Environment does not exist.

Fill in the assignment line, the block's third — `<SECRET>` is the name the application's deploy reads the password from, and, for a first provisioning, must be a name that Environment, the repository and its organisation do not already use; a rotation needs it to be in the Environment already. `host` is anything `ssh` accepts, so if the key for that host is not your default one, give it an alias with an `IdentityFile` in `~/.ssh/config`. Then paste the whole block, as it stands, into one bash shell on your workstation — copied from the rendered page or from the raw file alike, since it starts at column 0 and the closing `SQL` has to:

```sh
(
set -eu
app=<app> secret=<SECRET> repo=<org>/<app> env=<environment> host=<operator>@<host> rotate=no
env_names=$(gh secret list --repo "$repo" --env "$env" --json name --jq '.[].name')
repo_names=$(gh secret list --repo "$repo" --json name --jq '.[].name')
org_names=$(gh api --paginate "repos/$repo/actions/organization-secrets" --jq '.secrets[].name')
if printf '%s\n' "$repo_names" "$org_names" | grep -qixF "$secret"; then
  echo "refusing: $secret is a repository or organisation secret, which an Environment secret of that name would override; choose another name" >&2; exit 1
fi
if printf '%s\n' "$env_names" | grep -qixF "$secret"; then
  [ "$rotate" = yes ] || { echo "refusing: $secret is already set in $env; set rotate=yes in this block only to rotate it" >&2; exit 1; }
else
  [ "$rotate" != yes ] || { echo "refusing: rotate=yes, but $secret is not set in $env, so there is nothing to rotate; check the name" >&2; exit 1; }
fi
pw=$(openssl rand -hex 32)
printf '%s' "$pw" | gh secret set "$secret" --repo "$repo" --env "$env"
ssh "$host" 'docker exec -i platform-postgres-1 sh -c '\''psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres'\' <<SQL
SET log_statement = 'none';
SET log_min_error_statement = 'panic';
SET log_min_duration_statement = -1;
SET log_min_duration_sample = -1;
SELECT NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$app') AS create_role,
       NOT EXISTS (SELECT FROM pg_database WHERE datname = '$app') AS create_database \gset
\if :create_role
CREATE ROLE "$app" WITH LOGIN PASSWORD '$pw';
\else
ALTER ROLE "$app" WITH LOGIN PASSWORD '$pw';
\endif
\if :create_database
CREATE DATABASE "$app" OWNER "$app";
\endif
REVOKE CONNECT, TEMPORARY ON DATABASE "$app" FROM PUBLIC;
SQL
)
```

Expected output: `gh`'s confirmation that the secret was set, then `SET` four times, then `CREATE ROLE` (or `ALTER ROLE`), `CREATE DATABASE` (absent on a re-run), `REVOKE`.

### 3.3 The four questions that block raises the first time

- **Where the password comes from, and who has it afterwards.** `openssl rand -hex 32` generates it inside the block, and nobody holds it: it reaches `gh` and `psql` over standard input only, so it is in no shell history and no process listing on either machine, and the subshell it lives in exits. What survives is the encrypted Environment secret in the application's repository and a hash in PostgreSQL. There is no third copy to look it up in, by design — if you need the value again, you rotate rather than recover.
- **It differs per application and per host.** Each application gets a role, a database and a password of its own, and each **deploy target** is an independent run of this block: staging's `commerce-ops` password and production's are two unrelated values, even though both are stored under the same secret name in their respective Environments. That is what makes one leaked credential reach one host.
- **It is never `PLATFORM_POSTGRES_PASSWORD`.** That is the instance superuser's password, it belongs to this repository's own stack secrets, and it never reaches an application. The name the application reads is the one you put in the `secret=` assignment — `SHARED_POSTGRES_PASSWORD` for `commerce-ops`, chosen because that repository's `POSTGRES_PASSWORD` was already taken by something else. Any name free in that Environment, its repository and its organisation will do.
- **What to do when it is lost or leaked.** Rotate: the same block with `rotate=yes` on the assignment line. The application picks the new password up on its next deploy; connections it opens before then are refused. There is nothing else to clean up, because nothing else holds the old value.

### 3.4 What each part of the block is for

- **A subshell with `set -eu`**: a failing step ends the run before the next one, and the password disappears with the subshell. Paste it bare — wrapped in `if`, `&&` or `||`, `set -e` is suspended. Each secret listing is its own assignment for the same reason: several commands inside one `$(…)` would report only the last one's failure.
- **The name check refuses** if `<SECRET>` is already set in that Environment, in the repository, or in the organisation for this repository — an Environment secret overrides a repository or organisation secret of the same name for that environment's jobs, so any of the three would be overwritten from the application's point of view, which is an outage whose old value GitHub cannot give back. A name held by the repository or the organisation is refused outright: choose another. A name already in the Environment is refused unless `rotate=yes` is on the assignment line, meaning this run replaces that very secret — and `rotate=yes` is itself refused when the name is not in the Environment, so a mistyped or taken name cannot pass as a rotation. Keep it on that line rather than in your shell: a variable left set in the shell would switch the check off for the next paste. Names are compared ignoring case, as GitHub treats secret names. GitHub answers the organisation listing with `404` both for a repository owned by a personal account and for a token that cannot see an organisation's secrets, and the block stops there, having changed nothing. Only when `gh api repos/<org>/<app> --jq .owner.type` prints `User` is there no organisation to override anything — then make that line `org_names=` for that paste; otherwise fix the token's access.
- **The password reaches `gh` and `psql` only over standard input** — never a command line, so it is in no shell history and no process listing on either machine. A single `psql -c` would not work in any case: it sends several statements as one transaction, and `CREATE DATABASE` cannot run inside one. The here-document's delimiter is unquoted so that `$app` and `$pw` expand; quoted, the run would create a role literally named `$app` and still exit 0.
- **Every log setting that writes statement text is off for the session**, so a failing `CREATE ROLE … PASSWORD` does not put the password into `docker logs`, which every `docker`-group account can read.
- **Identifiers are double-quoted**, because an application name may carry a hyphen, which PostgreSQL otherwise parses as a subtraction.
- **It converges**: it creates the role or resets its password, creates the database if absent, and revokes `CONNECT` and `TEMPORARY` from `PUBLIC` — which a new database otherwise grants to every role in the instance, so without it any other application's role could connect.

### 3.5 When it fails

What it leaves depends on where. A secret-name listing failed: nothing was set and the host is untouched; fix the cause — for a `404` on the organisation listing, see the name check above — and paste it again. If it then refuses, act on what the refusal says: each message names its own remedy. `gh secret set` failed: the host is untouched; paste it again unchanged, and if it now refuses because the name is in the Environment after all, the set went through — paste it with `rotate=yes`. The host step failed on a first provisioning: the Environment holds a password no role has, which nothing uses yet; paste it again with `rotate=yes`. The host step failed on a rotation: the Environment is ahead of the role, and the application's next deploy would render a password the role rejects; paste it again with `rotate=yes` before that deploy.

**Check** from a session on the host: `\l` in `platform-postgres-1` lists the database owned by its role; `SELECT has_database_privilege('pgexporter', '<app>', 'CONNECT')` returns `f`; `docker logs --since <when you ran it> platform-postgres-1 2>&1 | grep -ciE 'create role|alter role'` returns `0`.

The application reaches it at `postgres:5432` over `platform_edge` with that role. This step is manual and is not meant to stay so. *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) obliges automating the provisioning and the delivery of the password; that obligation's trigger fired on 2026-09-13, when `commerce-ops` became the first application given a database here, and it is unmet. The mechanism is `docs/backlog.md` `automate-per-application-database-provisioning`.

On the **production** host, `commerce-ops` still runs a PostgreSQL container of its own holding durable data, which is what §3.1's first bullet forbids. That is a known divergence, named as such in *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`), and its resolution — its whole database, job queue included, moving into the database already provisioned for it in production's shared instance, and that container removed — is in that application's own repository rather than here. It waits on a specification change here first: that data includes durable rows, which the first bullet keeps out of the shared instance until `docs/backlog.md` `classify-commerce-ops-production-data-for-the-shared-instance` records the operator's acceptance of losing them. The queue moves with the rest because `commerce-ops` enqueues inside its domain transaction, which a second database cannot join. An external managed service comes later. Staging's `commerce-ops` has no such container. Do not read production's as a pattern to copy.

## 4. The application's own repository

### 4.1 One Environment per deploy target

One Environment per deploy target, each with the reviewer that target warrants, as in `docs/bootstrap-a-new-host.md`'s repository-settings stage. The names are the application repository's own — `production` for the production host, `staging` for a staging one — and they sit on the environment axis whatever this repository's own Environments are called. An application deploying to one host needs one; everything below repeats per Environment, which is what keeps one private half to one host.

Create it before §3.2, which refuses to store a password in an Environment that does not exist.

### 4.2 The secrets, per Environment

The whole table repeats per Environment, and every row after the first takes that target's own values:

| Name | Value from |
|---|---|
| `TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_SECRET` | The same OAuth client as the host bootstrap's tailnet stage, or a second one with the same tag |
| `DEPLOY_HOST` | That target's server's tailnet IPv4, same value as that stack's `PLATFORM_DEPLOY_HOST` |
| `<APP>_DEPLOY_SSH_KEY` | The private half of **that target's** key from §2.1 — one per application per environment, never one shared; delete the local file after storing |
| The shared-instance database password, under the name §3.2 gave it — `SHARED_POSTGRES_PASSWORD` for `commerce-ops` | Written by §3.2's recipe, with that target's own independently generated value — never set by hand here, and never under a name the Environment already holds |
| The application's own settings | Whatever the application needs |

**Delete each private half from your workstation once it is stored**, and verify before storing that it is the right one: `ssh-keygen -lf ~/.ssh/<company>-<app>-<environment>.pub` must print the fingerprint of the public half you committed in §2.2 — the same command and the same `.pub` target as §2.1's check, so the two figures are comparable at a glance.

### 4.3 Anything it persists has to say why it needs no backup

**Anything your Compose file persists — a volume, named or anonymous, or a writable bind mount — has to say why it needs no backup.** Name which reason in *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`) the store satisfies, in the change that adds it; a store satisfying none owes a logical backup written off this host and a rehearsed, checked restore before it first holds data. This catches the store a bumped image newly declares as much as one you wrote.

### 4.4 The Compose file and the deploy workflow

A `Dockerfile` and a `docker-compose.yml` whose web service joins the external network `platform_edge` and carries the Traefik labels shown in `platform/README.md`, "Joining the platform network", with its hostname and its container port. Use `env_file: .env` for runtime secrets and `image: ghcr.io/<org>/<app>:${IMAGE_TAG}`.

A deploy workflow on push to `main` with two jobs, copied from `commerce-ops` — **one `deploy` job per target**, each naming its own Environment, since an Environment is what selects which host's `DEPLOY_HOST` and deploy key the job resolves: a `build-and-push` job (`permissions: packages: write`, `docker/login-action` with `GITHUB_TOKEN`, `docker/build-push-action` tagging the image with `github.sha`), then a `deploy` job on **that target's** Environment that joins the tailnet with `tailscale/github-action`, renders `.env` from secrets (including `IMAGE_TAG=${{ github.sha }}`), and runs:

```sh
tar -czf - docker-compose.yml .env | ssh -i ~/.ssh/deploy_key deploy@${{ secrets.DEPLOY_HOST }}
```

The host extracts exactly those two files into `/opt/<app>` and runs `docker compose pull && docker compose up -d --wait`; the job fails if any service does not become healthy.

## 5. The public hostname

A DNS `A` record for the hostname, added where `docs/bootstrap-a-new-host.md`'s DNS stage records this repository's zone and its nameservers. Traefik requests the certificate on the first request to it.

**Check:** the deploy run is green; `https://<hostname>` answers with a valid certificate; the application appears on Grafana's "Application HTTP error rates" dashboard after its first requests; `docker ps` shows the application's containers `(healthy)`.

## 6. Reaching it before a hostname exists

An application deployed to a host with no public DNS record is fully testable, and the way to do it is not obvious.

Traefik routes on the `Host` header, so from a tailnet peer:

    curl -k --resolve '<hostname>:443:<that host's tailnet IP>' https://<hostname>/

**Not the plain `http://` form**, which the `web` entrypoint answers with a `301` to `websecure` whatever the `Host` header says — so a request that looks like it reached nothing has merely been redirected. And **not from a browser**: `-k` is doing real work here, because no certificate can issue while 443 is closed to the public internet. The resolver uses TLS-ALPN-01, which Let's Encrypt performs by connecting inbound, so what answers instead is Traefik's own default self-signed certificate. A browser will refuse it, correctly.

**What closes those ports is the cloud firewall, not the host's.** A container-published port is DNAT'd by the container runtime in `nat/PREROUTING` and accepted in the `FORWARD` chain; UFW's rules hang off `INPUT`, which those packets never traverse. So `hardening_web_allowed_cidrs` gates nothing for Traefik, which publishes `0.0.0.0:80` and `0.0.0.0:443`, and the Hetzner cloud firewall is the whole of what refuses a request from the public internet. Do not read a closed UFW rule as a closed port for anything a container publishes. The general case, and which documents still state it the other way round, is `docs/backlog.md` `say-what-the-host-firewall-actually-gates`.
