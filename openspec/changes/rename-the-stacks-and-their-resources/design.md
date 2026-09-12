# Design

## Context

`docs/naming-conventions.md` is the scheme and is not restated here. This document records the decisions the scheme leaves open, the two mechanisms that had to be measured rather than assumed, and the one hazard that is not in `docs/change-queue.md` entry 62 because the entry's author had not found it.

The single distinction the whole change rests on: **entry 61 renamed the word, this renames the values.** `terraform/stacks/` and the vocabulary *stack* are done and are guarded by `TestNoKeeperWasSweptInsideTheStackDirectories`. Nothing here re-sweeps vocabulary. What changes is what things are called: directories, Hetzner resource names, label values, filenames.

## Decision 1 — A stack now has two names, and each artifact takes exactly one

Today `prod` is the stack directory, the inventory filename, the Hetzner `environment` label value, the Ansible group, the `group_vars` filename, the `--vault-id` label and the play's `hosts:` — one word doing seven jobs, because at one tenant the stack name and the environment name coincide. After this change they do not: the stack is `main-production` and the environment is `production`.

Each artifact takes the name of the thing it belongs to:

| Artifact | Takes | Value |
|---|---|---|
| stack directory | the **stack** | `terraform/stacks/main-production/` |
| inventory source filename | the **stack** — one Hetzner project, one source | `ansible/inventory/main-production.hcloud.yml` |
| `host-converge.yml` concurrency group | the **stack** — one apply target, one queue | `host-converge-main-production` |
| Hetzner `environment` label | the **environment** | `production` |
| Ansible group, `hosts:`, `target_environment` | the **environment** | `production` |
| `group_vars` filename | the **environment** — a `group_vars` file is named for a group | `ansible/inventory/group_vars/production.yml` |
| `--vault-id` label | the **environment** | `production` |

The `--vault-id` label follows the environment rather than the stack because of what the password protects: `ansible/inventory/group_vars/staging.yml` says in as many words that a staging-only operator must not hold the password protecting production's secrets. The password is per-environment, so its label is too.

**`staging` is unchanged on the environment axis**, which halves this change's surface and is easy to misread as an omission. The environment values are `production` and `staging`; only `prod` was abbreviated. So `group_vars/staging.yml` keeps its name and its `;staging` Vault labels, while its stack directory and inventory source move to `main-staging`.

## Decision 2 — `target_environment` is declared in `pipeline.yml`, not derived from the stack name

`host-converge.yml` feeds `TARGET_ENVIRONMENT: ${{ matrix.stack.name }}` today and carries a comment saying the two coincide at one tenant and nowhere else. Three candidates replace it:

1. **Split the stack name on `-` and take the last segment.** Rejected. It is a rule that happens to work on two names and encodes nothing: a tenant named `main-line` breaks it silently, and the failure is an Ansible group that does not exist, reported four steps later.
2. **Read the Hetzner `environment` label from the inventory.** Rejected. Discovery runs before any credential is available — it is the credential-less job — so it cannot reach Hetzner, and the value is needed to build the matrix the credential-holding job runs over.
3. **Declare it.** Taken. `pipeline.yml` is already this stack's declaration to the pipeline, already carries two facts that are not Terraform's (`github_environment`, `read_only_secret`), and is already read by this discovery body.

The field is named `target_environment`, matching the play variable it feeds and the requirement that governs it (*Host Configuration Names the Environment It Targets*). A different spelling in the file from the one in the play would be a mapping, and a mapping is the thing the declaration exists to avoid.

**It carries no uniqueness obligation, unlike the other two fields.** `github_environment` and `read_only_secret` must each be distinct per stack — two stacks sharing either share a credential. `target_environment` is the opposite: the environment axis is shared *across* tenants by design, so `main-production` and a future `analytics-production` both declare `production` and both read `group_vars/production.yml`. That is the environment-wide baseline `docs/naming-conventions.md` describes, and asserting distinctness would forbid it.

**Only `host-converge.yml`'s discovery requires the field.** The shared body that `pr-validation.yml`, `apply.yml` and `drift.yml` use refuses a stack for the fields *it* reads, and it reads neither this one nor anything Ansible. Requiring it there would fail a Terraform-only pull request for an Ansible-shaped reason.

## Decision 3 — Renaming a scenario needs `REMOVED`+`ADDED`; renaming a requirement alone needs `RENAMED`

Entry 61 deferred both renames here and recorded that the tool refuses a renamed scenario. Measured against the installed OpenSpec 1.12.0 rather than assumed, because the choice of mechanism decides the shape of every delta in this change:

- A `MODIFIED` requirement whose block renames a scenario is **refused by `openspec validate`**, not merely at archive: *"MODIFIED … omits scenario(s) the current spec still has"*. A `MODIFIED` block replaces the whole requirement, and every scenario name absent from the incoming block is read as dropped.
- `## RENAMED Requirements` with `- FROM:`/`- TO:` lines **validates**, and a `MODIFIED` block referencing the **new** title may accompany it. Deltas apply in the order `RENAMED → REMOVED → MODIFIED → ADDED`, so the modification lands on the renamed block — and the scenario check applies to it exactly as before. **A `RENAMED` delta renames the requirement and cannot rename a scenario.**
- `## REMOVED Requirements` naming the old title plus `## ADDED Requirements` carrying the new title **validates**, and the added block's scenarios are whatever it says they are. This is the only mechanism in the tool that renames a scenario.

So: `REMOVED`+`ADDED` where a scenario title has to move, plain `MODIFIED` where it does not. `RENAMED` is available and is not used here — every requirement this change renames also has scenario titles to move, and `REMOVED`+`ADDED` covers both where `RENAMED` covers one. Each `REMOVED` block states its **Reason** and **Migration** naming the requirement that replaces it, so the archived record reads as a rename rather than as a deletion.

**The constraint that follows from this, and that has to be lived with:** a requirement cannot be `REMOVED` and `ADDED` under its own name — the tool refuses the collision — so **a scenario title can move only where its requirement's title moves too.** Three scenario titles are therefore left saying *environment* where they mean *stack*: *Version Control Excludes State and Secrets*' "CI has the environment configuration it needs", *Remote State Backend*' "Two environments do not share a workspace", and *Provider-Level Deletion Protection*'s "Shared module remains reusable by a future non-prod environment". Renaming those three requirements — each of which has a correct title — in order to reach a scenario title would be the worse trade, so the warts are disclosed here and in the proposal rather than swept.

**Which titles move, and which `Prod` stays.** Entry 61 deferred three renames, all of the pipeline-iterated unit: *Environment and Module Folder Structure*, *Each Environment Has a Dedicated Hetzner Cloud Project*, *Each Environment Declares Its Own Pipeline Configuration*. A fourth is renamed by this change's own substance rather than by entry 61's deferral: *Dynamic Inventory via hcloud Plugin* uses one word for the inventory source, the Ansible group and the `group_vars` file, which is exactly the coincidence this change ends.

Requirement titles carrying **`Prod`** are deliberately **not** renamed. `Prod` there abbreviates *production*, which is still the environment; what this change spells in full is the machine-read value — a label, a group, a filename — and not prose. *Conditional Prod Server Creation*, *Conditional Prod Volume Creation* and *Volume Attached to Prod Server at Creation* keep their titles and change only their bodies, which is also what `docs/change-queue.md` entry 62 asks for: it names the titles carrying *Environment* and no others.

## Decision 4 — `modules/server` stops deriving the firewall's name

The module builds `name = "${var.environment}-${var.name}"`, which is `prod-main-server` today and would be `production-main-production` after this change: the stack name repeated with its environment half in front of it. The scheme's answer is `main` — project-local, distinguished by rank — and no expression over the module's existing inputs produces it.

The firewall's name becomes a required input, `firewall_name`, validated non-empty the way `environment` already is. Alternatives considered and rejected:

- **Derive it from a new `tenant` input** (`name = var.tenant`). It produces the right string today and asserts something false: that a stack has one firewall and that its name is the tenant's. The rank axis exists precisely because a second firewall is named beside the first, and a derivation forecloses that.
- **Default it to `"main"`.** Rejected for the reason `environment` is not defaulted: a module that guesses a Hetzner resource's name is a module whose consumer can forget to name it, and the name is what an operator reads in the console.

Note for review: the keeper guard `OVERSWEPT_KEEPERS` matches `"<stack>-` inside `terraform/stacks/**`, which is the old derivation written down. Removing the derivation removes the thing that needle was named for; the needle stays, because it is forward cover against the derivation being reintroduced under the new word.

## Decision 5 — The `tenant` label, and the `main` Ansible group that comes with it

`tenant = "main"` joins `environment` and `managed_by` on every resource both modules create and on each stack's `hcloud_ssh_key`. It is an input to the modules rather than a literal, for the reason `environment` is: a module that hardcodes a label value is a module a second tenant cannot use.

Both inventory sources gain a second `keyed_groups` entry over `hcloud_labels.tenant`, so the groups are `main` and `production`/`staging` — the tenant-wide and environment-wide baselines the scheme describes. **No `group_vars/main.yml` is created**, because nothing yet belongs to a tenant-wide baseline; the group exists so that the label is queryable from Ansible, which is what a label is for. Creating an empty file to match a table would be the scheme written down twice.

`strict: true` reaches `keyed_groups`, and the previously measured behaviour holds: a host missing the key is not grouped rather than failing the parse. That matters for the window in Decision 10 — between the merge and the apply, no host carries `tenant` and the `main` group does not exist. Nothing reads it, so nothing notices.

## Decision 6 — The tailnet machine name is renamed out of band and pinned in the repository, and the two are different jobs

**This is not in `docs/change-queue.md` entry 62, and it is the part of this change most able to break production.**

Three names are one name today, by accident of how the host was built:

```
Hetzner server name   main-server   ─┐ cloud-init set the OS hostname from it, once, at creation
OS hostname           main-server   ─┤ `tailscale up` took the reported name from the OS hostname
tailnet machine name  main-server   ─┘ (observed: DNSName main-server.tail597fbf.ts.net)
```

This change separates all three deliberately: the Hetzner server becomes `main-production`, the OS hostname becomes `shatynska-main-production` (the company prefix is the scheme's, and the workstation is the namespace it exists for), and the tailnet machine name must stay equal to the **Hetzner server name** — because that is the name every automated consumer resolves:

- `host-converge.yml` selects `HCLOUD_CONNECT_WITH=hostname`, so a host's address is `hcloud_name`, and the job resolves it with `tailscale ip -4` against tailscaled's own netmap.
- `platform-deploy.yml` reaches the host as `PLATFORM_DEPLOY_HOST`, an Environment secret holding that same name.

### What was measured, on the live tailnet, before any of this was designed

An earlier draft of this decision declined to establish how Tailscale treats a machine whose hostname changes, and left the change resting on the unknown. Three reads settle it, against `tailscale` 1.102.3 — the version `ansible/roles/tailscale` pins:

| Read | Result | What it establishes |
|---|---|---|
| `tailscale debug prefs` on the production host | `"Hostname": ""` | The reported name is **derived** from the OS hostname today. Nothing pins it, so changing the OS hostname changes what this host reports. |
| `tailscale status --json`, peer list | two peers report `HostName: helen` while carrying `DNSName: helen` and `helen-1` | The **machine name is not the reported name**: they are independent fields and they differ persistently. It does *not* establish what happens when a registered machine's reported name later changes — that read exercises deduplication at registration only, and nothing below depends on the stronger claim. |
| `tailscale ip -4 helen-1` | answers | `helen-1` is a **DNSName that is no peer's HostName**, so resolution reaches the machine name. That is the field CI depends on. |

So the two halves of this problem are different jobs and neither substitutes for the other:

**Renaming the machine is out of band.** The machine name is assigned at registration, and nothing on the host sets it — `tailscale set --hostname` changes the *reported* name, which is a different field. The rename is done in the Tailscale admin console or its API, and it is an operator step of the same class as entry 63's, for the same reason: no file in this repository can perform it or verify it.

**Pinning the reported name is the repository's job, and it is defence rather than mechanism.** With the pref empty, the reported name follows the OS hostname — which this change is about to prefix with the company. Whether Tailscale would then carry that change into the machine name is exactly the question the reads above leave open, and it is the wrong question to depend on: the pin removes it. `tailscale set --hostname={{ inventory_hostname }}` (and `--hostname` on a first join) makes the host report `main-production` whatever its OS hostname is, so the machine name is either left alone or updated to the name it should already have. Both outcomes are correct, and the change no longer needs to know which one occurs.

**That pin is what decides the role order**, and it decides it the opposite way an earlier draft did. Within one converge the OS hostname must not change while the reported name is still derived from it, so `tailscale` runs **before** `hostname`. A converge that fails between them then leaves the OS hostname stale, which is cosmetic and self-correcting on the next run; the reverse order leaves a window in which the host reports `shatynska-main-production` with nothing pinning it, which is the load-bearing name.

### The transition, and why it goes before the merge rather than after

From the moment the apply renames the server, CI looks for a tailnet machine named `main-production`; until the console rename happens, there is none. The converge cannot do it and could not even reach the host to try: the cloud firewall admits SSH from the operator's ISP range only, so a GitHub runner has no route except the tailnet it is failing to resolve. The step fails with the existing diagnostic (*"matches no tailnet peer this runner can see"*), before the first play, having changed nothing.

The transition is therefore an operator step, taken **immediately before the merge** — after the pull request has been reviewed and approved, not at the start of the review:

1. Rename each tailnet machine to its stack's new name — `main-server` → `main-production`, `staging-server` → `main-staging`.
2. Confirm from a second peer that `tailscale ip -4 main-production` and `tailscale ip -4 main-staging` answer. The confirmation is the gate, because the rename is performed in an interface and the repository has no other way to know it took.
3. Update `PLATFORM_DEPLOY_HOST` in the `production` GitHub Environment to the new name.

Between step 1 and the apply, a converge or a deploy fails loudly and changes nothing. **The length of that window is why the step is placed where it is**: before the *merge*, not before the *pull request*. An earlier draft put section 9 ahead of opening the pull request, which would have held CI and every emergency deploy broken across review, plan review and the required-reviewer wait — a wait entry 61 measured in long enough for HCP's state serial to move under it. Doing the rename *after* the apply is worse still and is what this ordering exists to avoid: CI would be broken with only the operator able to end it, and nobody watching for the moment it started.

## Decision 7 — The hostname is its own role, not a task inside `hardening`

`hardening` owns host-level security — SSH, UFW, fail2ban, unattended upgrades. A host's name is identity, not defence, and the only argument for putting it there is that `hardening` already exists. A role of its own carries its own README, its own required-input assertion (`company`, by name, per *A Role's Absent Required Input Is Reported by Name*) and its own Molecule scenarios, which is what makes the behaviour observable at all — `hardening`'s scenarios assert hardening.

It runs **immediately after `tailscale`** in `host-baseline.yml`, and decision 6 is the authority on why: the reported tailnet name is derived from the OS hostname until something pins it, so the OS hostname must not change before the pin is in place. Every other placement was available and this one is forced. An earlier draft put the role first, on the reasoning that nothing depends on it — which decision 6's own measurement contradicts, and which is recorded here rather than quietly replaced, because "nothing depends on this" is the kind of claim that reads as obviously true and is the reason the dependency went unnoticed.

`company` lives in a new `ansible/inventory/group_vars/all.yml`, which is the one file a second company's clone edits. It is not a role default: a default is a value the role chose, and this one is the consuming project's.

## Decision 8 — The Vault label is edited in place, without the Vault password

`ansible/inventory/group_vars/prod.yml`'s `image_prune_heartbeat_ping_key` is a `$ANSIBLE_VAULT;1.2;AES256;prod` block and the converge passes `--vault-id "production@…"` after this change. Entry 62 records that the desync very likely keeps working anyway, because `vault_id_match` is off by default and Ansible tries every supplied secret regardless of label, and asks for a re-encrypt rather than reliance on that default.

Re-encrypting needs the Vault password, which is not in this repository and is not available to the session making the change. **Measured instead, against the pinned `ansible-core` 2.21.3:** the vault id is plaintext metadata in the header line, outside the salt and the HMAC. A block encrypted under label `old` and edited to read `;new` decrypts under `--vault-id new@<same password file>` and yields the original value. The relabel is therefore a text edit, it is exactly equivalent to a re-encrypt for this purpose, and it removes an operator dependency rather than adding one.

Prod's `ghcr_pull_token` is a `1.1` block, which has no label field at all, and is untouched. Staging's two blocks are labelled `staging`, which is unchanged.

## Decision 9 — *Remote State Backend* drops its workspace-name derivation

The requirement says each stack's workspace is `infrastructure-<stack>`. Renaming the stack to `main-production` makes that sentence false on merge: the workspace is `infrastructure-prod` and stays that way until entry 63 renames it in the HCP interface, first, before any `versions.tf` moves.

Three ways out, and the third is taken:

1. **Leave it and note the interval.** Rejected: a requirement that is false is worse than one that is vague, and the interval is not bounded by this change's own life — it ends when a separate change is archived.
2. **Rename the workspaces here.** Rejected: that is entry 63, and its order is load-bearing in the other direction (the HCP rename must precede the `versions.tf` push, or the next plan proposes creating every resource from scratch).
3. **State the obligation without the derivation.** Taken. The requirement is about *uniqueness* — a workspace holds one state, and two stacks sharing one plan each other's resources for destruction. The derivation was a convention riding along, and the requirement itself already says the name's uniqueness is unverifiable from this repository. Entry 63 is where the names are chosen; `docs/naming-conventions.md` is where the convention is recorded.

**What the requirement must not say, and an earlier draft did.** It must not *forbid* a workspace name that matches its stack's directory name. Entry 63 renames the workspaces to `main-production` and `main-staging`, which is exactly that match — so a prohibition would archive a requirement the next change in the sequence violates. What is forbidden is **computing** one from the other at run time, which is the thing that breaks: the two are renamed by different mechanisms, in an order that cannot be reversed, so any derivation is false for the interval between them. Agreement by convention is fine; agreement by derivation is not. The distinction is the whole of this decision and it is easy to lose in a sentence.

## Decision 10 — What the merge does, in what order, and where a human decides

One merge triggers two workflows with live effect, and both production jobs attach to the `production` GitHub Environment — so the operator controls their order by choosing which approval to give first.

```
merge to main
 ├── apply.yml         main-production  → waits for the production Environment's reviewer   (1st)
 │                     main-staging     → no reviewer, applies immediately
 └── host-converge.yml main-production  → waits for the same reviewer                       (2nd)
                       main-staging     → no reviewer, converges immediately
```

**Approve the apply before the converge.** The converge reads the Hetzner `environment` label live; before the apply, no host carries `production`, the group is empty, and the credential-proving step refuses with *"this stack's environment group names no host"* — loud, before the first play, host untouched. Approving in the other order costs a re-run, not a bad state.

**Staging races and that is tolerable**, because staging's environment value does not change. Its converge is affected only by the server rename, which is the tailnet-name problem Decision 6 sequences ahead of the merge; if staging's converge wins the race it converges the host under its old server name and its unchanged group, which is what it does today.

**Do not introduce a `--limit`.** `host-converge.yml` passes none and `docs/bootstrap-a-new-host.md` warns manual runs off it. A limit filters `localhost` out of `host-baseline.yml`'s guard play, Ansible has no per-play exemption, and both plays are then skipped with exit 0 — the silent failure the guard exists to end. The converge that follows a rename is exactly where someone reaches for one to try a single host first.

## Decision 11 — What this change does not establish, stated rather than implied

- **A green pull request does not establish that the converge works.** The guard play's own behaviour is verified by hand and by nothing else — `docs/change-queue.md` entry 54 owns the play-scope harness that would assert it. The evidence for this change's Ansible half is the converge's own play recap, read by a human.
- **No plan is asserted in advance.** Hetzner supports renaming a server, firewall, volume and SSH key in place, and the pull-request plan is what proves it did. A plan reporting `must be replaced` for any of the eight stops this change rather than being worked around.
- **The heartbeat check's rename is not observable for a week.** The slug is derived from `inventory_hostname`, so after the converge the host pings `main-production-prune-host-images` and `main-server-prune-host-images` goes quiet — which is the alarm condition. The new check is created before the converge and the old one deleted after, and the first real ping arrives on the unit's own weekly schedule.
- **`docs/naming-conventions.md`'s banner stays.** It is deleted by whoever archives the last of entries 61–64, and entries 63 and 64 remain.
