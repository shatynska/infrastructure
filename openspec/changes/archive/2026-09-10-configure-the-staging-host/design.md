## Context

See `proposal.md` — Why. What follows is the state the approach has to fit.

**The inventory plugin.** `hetzner.hcloud.hcloud` 7.0.0 templates its `api_token` option before use, and its documented example is a templated token, so a source can take its credential from an environment variable of its own choosing rather than from the plugin's built-in `HCLOUD_TOKEN` fallback. Its `verify_file` accepts a path only if the path *ends with* `hcloud.yml` or `hcloud.yaml` — a plain suffix test, so `staging.hcloud.yml` is accepted and `hcloud-staging.yml` is not. Filenames are constrained by that, not chosen.

**Two consumers compile the play without running it**, and both break on a templated `hosts:` with nothing supplied:

- the `ansible-playbook --syntax-check` pre-commit hook, which runs with cwd `ansible/` and so does read `ansible.cfg`;
- `ansible-lint`, whose `syntax-check` rule is tagged `unskippable` and cannot be disabled per-file or per-rule.

Both were reproduced before this design was written: each reports `Error processing keyword 'hosts': 'target_environment' is undefined` and exits non-zero.

**Ansible in this repository is always run from `ansible/`.** The pre-commit hook `cd`s there deliberately, because Ansible reads `ansible.cfg` from the current directory only and never searches upward — and that config is what resolves `roles_path`. Anything this design does with credentials has to work from that directory.

**`docs/bootstrap-a-new-host.md` §4.1 already keeps two Terraform tokens apart** by directory: production's read-only token in the repository-root `.envrc`, staging's in an `.envrc` inside `terraform/environments/staging/`, both under the name `HCLOUD_TOKEN` because that is what the Terraform provider reads. direnv loads the nearest `.envrc` and does not merge the parent's.

## Goals / Non-Goals

**Goals:**

- A run reaches the environment it names, and no other, with nothing about the shell it was started from able to change that.
- A run that reaches nothing fails.
- Bringing a third environment into Ansible is adding files, not editing the ones that already exist.
- Staging converges to the same host state prod does, from a `group_vars` written for staging rather than inherited from prod's.

**Non-Goals:**

- Running the converge from CI. That is entry 23, and this change is what unblocks it by giving it a host to develop against.
- Any change to how the platform stack is deployed, or to what staging exposes to the internet. See `proposal.md` — "Not in scope, and where it went instead".
- Closing the play-scope input-validation gap in `docs/deferred-work.md`. The guard play added here is a different mechanism answering a different question — Decision 8 says why they are easy to conflate and must not be.

## Decisions

### Decision 1: One inventory source per environment, each with a credential name of its own

`ansible/inventory/hcloud.yml` becomes `ansible/inventory/prod.hcloud.yml` and `ansible/inventory/staging.hcloud.yml`. They are identical but for the environment variable each takes `api_token` from: `HCLOUD_TOKEN_PROD` and `HCLOUD_TOKEN_STAGING`.

**Why not one source and a per-run token**, which is the smaller diff: it makes which project a run reaches a property of shell state rather than of the run. The failure is not hypothetical — `.envrc.example` already warns that a `HCLOUD_TOKEN` export outlives the directory it was sourced in. With distinct names, a run's reach is decided by the file it names, and carrying the wrong token in a shell cannot silently redirect it.

**Why not an inventory directory loading every source at once**, which would let `ansible-inventory --graph` show all environments in one view: every run would then need every environment's credential in scope, and a missing one fails inventory parsing for the environments that *were* available too. That trades a targeted failure for a global one, and it gets worse with each environment added.

**Why not per-environment inventory *directories*** (`inventory/prod/`, `inventory/staging/`, each with its own `group_vars/`), which is the other common production layout: `group_vars/` is resolved from the directory *containing* the inventory source, so sibling files in one directory keep the existing `inventory/group_vars/` working unchanged. Directories would move `group_vars/prod.yml` and take a sweep of some twenty references with it, for no behaviour this design does not already get.

**The naming is forced, not chosen.** The plugin's `verify_file` requires a path ending in `hcloud.yml`, so `<environment>.hcloud.yml` is the only shape that both carries the environment name and is accepted. A file the plugin rejects is not an error the operator sees as a naming problem: Ansible reports the source as unparseable and continues with an empty inventory.

### Decision 2: `ansible.cfg` declares no default inventory

The `inventory = inventory/hcloud.yml` line is removed rather than re-pointed. Any default is one environment's, and a default that is production's makes the most consequential target the one a forgotten flag selects. Every run names its inventory with `-i`.

This costs the convenience of bare `ansible prod -m …` ad-hoc commands, which `docs/bootstrap-a-new-host.md` §6.4 uses in four places; they gain a `-i`. It also changes what `--syntax-check` sees: with no default inventory the hook warns "No inventory was parsed" and proceeds, where today it warns that it could not parse `hcloud.yml` without a token and proceeds. Neither warning fails the hook, and neither ever did any work.

Decision 2a turns the second of those warnings into a failure everywhere except this one path, and the distinction between the two config settings that could do it is what makes that possible.

### Decision 2a: An inventory source that cannot authenticate fails the run

`ansible/ansible.cfg` gains `any_unparsed_is_failed = True` under `[inventory]`.

**Without it the requirement this change writes is false.** Ansible's default is to warn on a source it could not parse and carry on with whatever else parsed — so a `staging.hcloud.yml` whose credential is absent, empty or rejected yields an inventory in which staging simply has no host. That is byte-for-byte the state of an environment whose server does not exist, and the guard play of Decision 4 would report it as "staging resolved to no host". The operator then goes to Hetzner or to Terraform looking for a destroyed server, when the fault is a dotfile.

All three states were reproduced before this was written. On default config, `ansible-inventory -i bad.hcloud.yml --graph` with an unusable token exits **0** and prints an empty inventory; with `any_unparsed_is_failed = True` it exits **1** naming the source it could not parse.

**Not `unparsed_is_failed`, which is a different setting one word apart.** That one fires when *no* source parsed at all — which is exactly the state Decision 2 leaves the `--syntax-check` hook in, since it supplies no inventory. Reproduced as well: under `unparsed_is_failed` the syntax check exits **1** with "No inventory was parsed"; under `any_unparsed_is_failed` it exits **0**. The two settings read as synonyms and are not, so this is stated where the config change is made and asserted statically rather than left to a reader's care.

**The alternative was to weaken the requirement** to what the guard play alone delivers: a run that reaches no host refuses, whatever the cause. That is honest and needs no config change, but it gives up the diagnostic distinction the requirement exists to make, and it leaves the artifacts asserting a behaviour Ansible does not have.

### Decision 3: Ansible's credentials live in `ansible/.envrc`, and are not the ones Terraform reads

A committed `ansible/.envrc.example` documents `HCLOUD_TOKEN_PROD` and `HCLOUD_TOKEN_STAGING`; the real `ansible/.envrc` is gitignored by the existing `.envrc` pattern, which has no slash and so matches at any depth.

This is the existing directory-scoping trick applied where Ansible actually runs. In `ansible/`, direnv loads that file and not the repository root's, so the shell holds exactly the two credentials Ansible needs and does not hold `HCLOUD_TOKEN` at all. Terraform keeps `HCLOUD_TOKEN` — the name its provider reads — directory-scoped exactly as §4.1 already describes, and the two mechanisms stop sharing a variable name.

**The alternative was to leave prod's Ansible source reading `HCLOUD_TOKEN`**, on the argument that Ansible is only ever run from `ansible/`, where the root `.envrc` supplies production's token. That argument is a convention about where commands are typed, and replacing conventions with mechanisms is the point of this decision. It also breaks symmetry: a third environment would take a suffixed name while prod kept the bare one, so the "add a file and a variable" property would not hold for the environment most likely to be copied from.

**Both tokens are read-only**, so holding them in one shell widens nothing. `AGENTS.md`'s boundary is that a Read & Write token never reaches a workstation, and nothing here touches that.

### Decision 4: The play's target is supplied per run, with no default, and a first play refuses

`hosts: "{{ target_environment }}"` on the baseline play, preceded by a play against `localhost` that asserts, in two separate tasks so each failure says which thing was wrong:

1. `target_environment` was supplied;
2. `groups[target_environment] | default([])` is non-empty.

Both were verified against a fixture play before this was written: each exits **2**, having changed nothing, where the same play without the guard exits 0 having done nothing.

`| default([])` is load-bearing. `keyed_groups` creates a group only when some host carries the label, so under production's credential the key `staging` is not merely empty — it does not exist, and indexing `groups` raises rather than returning nothing.

**Why a separate play rather than `pre_tasks`.** `pre_tasks` run on the hosts a play matched, so a play matching nothing runs none of them. The check has to live somewhere that runs when the target set is empty, and that is a play with a target of its own.

**Why not `any_errors_fatal` or a `--limit` convention.** Neither addresses it: there is no error to be fatal about, and a limit narrows a host set rather than asserting it is non-empty.

### Decision 5: Static tooling is given a sentinel environment, in configuration rather than in the play

`ansible-lint`'s `syntax-check` rule is `unskippable`, and it fails on the templated `hosts:`. Two changes feed it a value:

- `.ansible-lint` gains `extra_vars: {target_environment: syntax-check-only}`;
- the pre-commit `ansible-playbook --syntax-check` hook gains `-e target_environment=syntax-check-only`.

Both were verified: with the `extra_vars` entry, `ansible-lint` returns 0 on a play that failed without it.

**Why not give `hosts:` a never-matching default** — `{{ target_environment | default('none-supplied') }}` — which would satisfy both tools with no config change: it puts a fake value in the play so that a linter can compile it, and the play then carries a default for the very input the specification says must not have one. A reader has to know that the sentinel matches no group to know the play is safe, where the guard play states the same thing outright.

**The sentinel must not name a real environment**, or the compile step would be resolving the play against an environment nobody asked for, and a value that drifted into being a real environment name would do so invisibly. That is a static property of committed files, so `.github/tests` asserts it.

### Decision 6: Staging gets its own Vault identity, not prod's password

Staging's encrypted values carry the vault id `staging`. The convention exists already, though unevenly: `group_vars/prod.yml`'s `image_prune_heartbeat_ping_key` is `$ANSIBLE_VAULT;1.2;AES256;prod` and does carry the id, while `ghcr_pull_token` beside it is `1.1` with no id at all — an older block, still decryptable, and not evidence of the convention. What is unambiguous is `docs/bootstrap-a-new-host.md` §6.1 and §6.3, which prompt with `--vault-id prod@prompt` throughout. This change is the first to have a second value for it.

Reusing prod's password for staging's file would mean anyone who can converge staging holds the password protecting production's GHCR token and ping key — which is the opposite of what a rehearsal environment is for, and would make entry 23's "the company server needs a second operator on day one" strictly harder.

### Decision 7: Staging's `deploy_apps` seeds `platform` with a staging-only keypair

Not prod's platform key. One leaked private half must not deploy to both environments, and the keypair is generated out-of-band by the operator like every other in this repository. Only the public half is committed.

Seeding it here rather than leaving it to entry 52 does two things: it saves entry 52 a second converge to authorise the account, and it keeps the prune's enumeration non-empty, which its own contract requires — an enumeration naming no application makes the script abandon on the grounds that the keep set would reduce to `docker image prune -a`, weekly.

`commerce-ops` is deliberately **not** seeded. It has no staging deploy path in its own repository, and an enumerated application with no Compose file contributes nothing to the keep set while implying an authorisation nothing uses.

### Decision 8: The prune is armed on staging, and its check is red until entry 52

Decided with the operator. Staging converges with prod's role set, `image_prune` included, and reports to a check named from its own `inventory_hostname` — `staging-server-prune-host-images`, which is distinct from prod's precisely because `terraform/environments/staging/terraform.tfvars` names the server `staging-server` rather than `main-server`.

**Stated plainly, because it is the cost:** on a host where nothing is deployed, no enumerated application renders an image reference and no container holds one, so the keep set is empty and the unit abandons, exits non-zero and reports `/fail`. The check is created at the observer by that first ping, and it is red from the moment it exists until the platform stack reaches staging.

**The window is a property of the check, not only of the timer, and the check is not created with the right one.** The unit is weekly, but a check the reporter brings into existence by pinging it carries the observer's *default* period until someone corrects it — `docs/bootstrap-a-new-host.md` Appendix A says so in as many words. So "one activation a week" is what the host does, and "overdue in a day" is what the observer would say, until its period and grace are set to the values Appendix A lists beside prod's. `tasks.md` makes that a step of its own rather than a consequence of the converge, because nothing in the converge does it.

With that corrected, the window is bounded by the timer: the unit is weekly, so if entry 52 lands within the week there is no red activation at all. What makes this acceptable rather than an alarm trained to be ignored is that the window is short and known. If entry 52 slips past it, that is the moment to revisit rather than to mute.

**The rejected alternative** was a per-environment switch keeping `image_prune` out of staging's converge until it had something to prune. It costs a variable whose only purpose is to be flipped once, and it makes staging's converge differ from prod's in exactly the layer entry 23 wants to rehearse.

### Decision 9: Five refusal diagnostics name the environment rather than production

`hardening`, `deploy_user` and `image_prune`'s two assertions name `ansible/inventory/group_vars/prod.yml` as where an input is set; `platform_data_volume`'s names `terraform/environments/prod/terraform.tfvars` as where to check the volume is attached. Each becomes `ansible/inventory/group_vars/<environment>.yml` and `terraform/environments/<environment>/terraform.tfvars`.

**This is a defect against a requirement already recorded, not a new rule.** *A Role's Absent Required Input Is Reported by Name* obliges a diagnostic naming the input "and where it is expected to be set". On a staging run, production's inventory file is not where it is expected to be set, so the requirement is already unmet the moment a second environment has a `group_vars`. No delta is owed; the fix is owed.

**Why a literal `<environment>` placeholder rather than the run's actual group.** Rendering the real group name reads better on a real host and is untestable on the one place the refusal is exercised: a Molecule container belongs to no environment group, so the message would name nothing there and the scenario would be asserting a template rather than a diagnostic.

**Why this touches tests.** Two scenarios assert the literal `group_vars/prod.yml` in the recorded message — `ansible/roles/hardening/molecule/absent-ssh-cidrs/verify.yml` and `ansible/roles/image_prune/molecule/absent-heartbeat-key/verify.yml`. They are updated to the new literal, exactly, rather than loosened to `group_vars/`: substring-matching the directory would pass on the message this change is replacing.

`ops_user`'s assertion names no environment-specific file and is untouched.

### Decision 10: Where each new test goes, and the one that has no home

Per this project's three test commands:

- **`.github/tests/`** — every static property: one inventory source per environment directory under `terraform/environments/`; no two sources naming the same credential variable; no source naming the plugin's bare `HCLOUD_TOKEN` fallback; the play's `hosts:` not a literal environment name; the play's first play being a `localhost` guard; `ansible.cfg` declaring no default inventory **and setting `any_unparsed_is_failed`** (Decision 2a — the assertion is what stops a later edit quietly restoring the empty-environment behaviour, and it names `unparsed_is_failed` as the wrong neighbour so nobody "fixes" it into breaking the syntax-check path); the lint sentinel not naming a real environment.
- **Molecule** — the two refusal scenarios of Decision 9, which assert role behaviour and already exist.
- **Nowhere** — that the guard *actually refuses*. Molecule's subject is a role on a host, and this is a play with no host; `.github/tests` may only read committed files statically, and this needs `ansible-playbook` to run. The behaviour was verified by hand against a fixture play while writing this design, and `tasks.md` repeats that verification against the real playbook and records its output.

**This gap is recorded rather than closed.** A fourth test command — a play-level harness — is a change of its own, and inventing one inside this change would put a new testing layer in the diff that most needs reading closely. `tasks.md` records it in `docs/change-queue.md`.

### Decision 11: The play-scope validation gap is revisited, and stands

`docs/deferred-work.md`'s "Two gaps in required-input validation that only the play could close" names *this* moment as its revisit trigger: the first time a `group_vars` is written from scratch rather than inherited.

It is revisited and it stands. The reasoning that deferred it is unchanged — what the gap produces is a partially-converged host, every role in the play is idempotent, and the play-scope fix restates every role's required inputs in a second place nothing keeps in step with the roles. Writing staging's `group_vars` from scratch gives the gap a real case for the first time, and the case is met by the file being complete and reviewed rather than by a new check.

**The guard play is not that fix and must not be read as one.** The gap is about a role's *input* being absent on a host that resolved; the guard is about *no host resolving at all*, which is upstream of every role and of every role-scope assertion. The delta spec states that distinction inside the requirement so the two are not conflated later.

## Risks / Trade-offs

**Every existing Ansible invocation changes shape.** After this, a prod converge is `ansible-playbook playbooks/host-baseline.yml -i inventory/prod.hcloud.yml -e target_environment=prod --vault-id prod@prompt …`. Muscle memory and any local script break. → The break is loud, not silent: without `-i` there is no inventory and the guard refuses; without `-e` the guard refuses. Every affected invocation in `docs/bootstrap-a-new-host.md` and `README.md` is updated in the same change.

**Staging's prune check is red until entry 52 lands.** → Decision 8 states the window and what to do if it is exceeded.

**A first converge cannot be run by CI and is not run by whoever writes this change.** The tasks that converge staging, create its Vault password, its tailnet auth key and its deploy keypair are the operator's, on their own workstation, against credentials that exist nowhere in this repository. → They are listed as prerequisites in `tasks.md` rather than discovered mid-run, and the change's `ship:confirm` gate *is* that converge — this change cannot be archived on a green pull request alone.

**`ansible/.envrc` is a fourth gitignored file an operator must create**, and a missing one produces an inventory that cannot authenticate. → Decision 2a is what makes that a failure rather than an empty environment; without it this risk has no mitigation, which is why the setting is a task and an assertion rather than a note. `ansible/.envrc.example` is committed beside it.

**The two Molecule scenarios of Decision 9 are edited, not added to.** Editing an existing test to match new expected output is the shape of a test weakened to reach green. → The replacement is an exact literal rather than a loosened substring, so it fails against the message being replaced as well as against no message at all; `tasks.md` requires confirming that both scenarios fail on the current tree before the role change lands.

## Migration Plan

There is nothing deployed to migrate — no state, no running service, no consumer. What follows is ordering, because two steps have to be true before the converge is attempted.

1. **Repository first, host second.** The inventory split, the play, the diagnostics, the docs and the tests land and pass on a pull request while staging is still unconverged. Nothing in that pull request touches prod.
2. **Prod's invocation is proved unbroken before staging's is attempted**, by running the new form against the live production host with `--check --diff` and confirming it resolves the host and proposes nothing. `--check`, not a converge: `AGENTS.md` allows local production credentials for reading and not for applying, and what has to be established here is that the new inventory source and the new target still reach production — which a check-mode run answers completely. `docs/bootstrap-a-new-host.md` §6.3 already says `--check --diff` is useful on every run after the first, and this host is long past its first.
3. **Then the operator's out-of-band steps**, all five of which must exist before the play is run at all: staging's Vault password, its tailnet auth key, its `platform` deploy keypair, its GHCR and heartbeat values encrypted into `group_vars/staging.yml`, and its SSH host key recorded in the operator's `known_hosts`. The host key belongs in this list and not in the converge: `ansible/ansible.cfg` sets `host_key_checking = True`, so without it the first converge stops at connection time with `Host key verification failed`, before any role runs.
4. **Then staging's first converge**, locally, then immediately again to confirm `changed=0`.

**Rollback.** Before the converge: revert the pull request; prod's invocation returns to its previous form and nothing else moves. After it: staging is disposable by construction — `server_enabled = false` destroys it, and `terraform/environments/staging/main.tf` sets `delete_protection = false` and `backups = false` deliberately so that this is available. Nothing on staging is irreplaceable, and this change is required not to make that untrue.
