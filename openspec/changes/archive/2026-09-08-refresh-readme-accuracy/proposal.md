## Why

`README.md` is the first file a human reads in this repository, and it makes statements about it that are no longer true. `AGENTS.md` was refreshed; `README.md` was not.

The rot is not evenly spread. The Molecule section (L84-166) has been maintained by several changes since 2026-08-26 and is almost entirely accurate. The sections nobody had a reason to open — Non-goals, Repository layout, CI/CD, Testing, Status — describe a repository that stopped existing weeks ago.

Verified against the tree at `102a303`, not recalled:

| `README.md` says | Reality |
|---|---|
| L22: single region `fsn1` | `terraform/environments/prod/terraform.tfvars:8` — `location = "hel1"` |
| L32-44: three top-level directories | seven are committed — `.github/`, `openspec/`, `docs/` and `.claude/` are unmentioned |
| L42-44: `platform/` is a reverse proxy and a PostgreSQL instance | eight services — also Prometheus, Alertmanager, Grafana, and three exporters |
| L90: `ansible-galaxy install -r ansible/requirements.yml` | installs to `~/.ansible/roles`, which no scenario can see |
| L113-117: which roles carry several scenarios | names two of the four that do |
| L138, L144: "the eight scenarios this repository owns" | twelve |
| L170-171: `terraform.tfvars` holds "server type, region, image, allowed CIDRs, labels" | no labels; it also holds an SSH public key, volume settings and two enable flags |
| L175-186: CI/CD is three bullets | six workflows; `ansible-verify`, `platform-deploy` and `pre-commit-autoupdate` are unmentioned, and the pull-request bullet omits the CI-configuration suite and does not distinguish the two unconditional checks from the path-filtered ones |
| L190-193: module tests arrive "as `terraform/modules/` grows past `terraform/modules/server`" | `terraform/modules/server/tests/` holds five `.tftest.hcl` files and `terraform/modules/volume/tests/` three — the named module refutes the claim built on it — and two further test commands exist that the section does not mention |
| L205-210: "being bootstrapped per the change `bootstrap-hetzner-iac`" | bootstrapped; 25 changes archived |
| L216-219: `ansible/` and `platform/` are "structure and convention only" | six roles, twelve Molecule scenarios, and a 607-line Compose stack in production |

And one row that is not in `README.md` at all:

| Where | Says | Reality |
|---|---|---|
| `.ansible-lint:3`, `.gitignore:28`, `ansible/requirements.yml:6` | `ansible-galaxy install -r ansible/requirements.yml` | the same defective command as `README.md:90`, in three more committed files |

**The region is the row that matters.** Every other one misleads a reader about what the repository contains. That one sends an operator to the wrong Hetzner location, to look for a server that is not there.

**The Galaxy command is the row that costs time.** `docs/change-queue.md` entry 9 assigns it here. `ansible/ansible.cfg` sets `roles_path = roles`, which *replaces* the default search list rather than extending it, and every Molecule scenario overrides `ANSIBLE_ROLES_PATH` to `ansible/roles/`. A role installed to `~/.ansible/roles` is invisible to all of it, so following the command produces a converge that fails on the dependency rather than on anything the scenario asserts — a failure that reads as a broken suite. CI installs with `-p ansible/roles`, and `.gitignore` excludes `ansible/roles/geerlingguy.docker/` on the same assumption. The four comments telling a human what to run never caught up, and three of them sit in the very files whose behaviour depends on the role landing somewhere else.

## What Changes

**A truth pass over `README.md`**, correcting every row above against the tree. No section is added, removed or reordered, and no position the file takes is revisited.

**The same one-line correction in the three other files that carry it.** Entry 9's defect is the command, not the file — fixing one copy of four leaves a reader who opens `.gitignore` or `ansible/requirements.yml` with the same broken suite, and makes this change's own effect observation untrue. Each is a comment, each is one line, and `AGENTS.md` treats a one-line correction with nothing to specify as too small to be a change of its own.

**Three corrections are written so they cannot rot the same way.** A count and a list of examples are what rotted here, so where the useful content is "how many" or "which ones", the file gains the command that answers it rather than an answer that goes stale between changes:

- "the eight scenarios this repository owns" becomes "every scenario this repository owns", with `git ls-files 'ansible/roles/*/molecule/*/molecule.yml'` as the enumeration. It needs no exclusion clause: `.gitignore:30` excludes `ansible/roles/geerlingguy.docker/`, so *committed* and *owned* are already the same set, and stay the same set when a second Galaxy role ships scenarios.
- the parenthetical naming which roles carry more than one scenario becomes the same command. Four roles do today; the number changed twice in three weeks.
- the region is stated **and** attributed: `hel1`, with `terraform/environments/prod/terraform.tfvars` named as where it is set. A reader gets the answer without a lookup, and an editor is told, in the sentence they are editing, what the answer has to agree with.

**The `terraform/modules/server` example stays an example.** It is correct as written — `server` is a module and a fair illustration. What is wrong is the claim built on it, that module-level tests are a future concern, when that very module carries five of them.

## Non-goals

**Enforcing any of this.** The README's region diverged from `terraform.tfvars` for weeks with nothing to notice, and both facts are static reads of committed files — squarely inside what `.github/tests` can assert. Adding that check is the improvement noticed along the way that `AGENTS.md` says becomes its own change: this repository does not enforce a convention it has not recorded, so the check would need a requirement, which would make this a change with a delta and a different set of gates. Recorded in `docs/change-queue.md`.

**Correcting the same parenthetical in the specification.** *Version Control Excludes State and Secrets* in `openspec/specs/iac-repo-foundations/spec.md` describes `terraform.tfvars` as holding "server type, region, image, labels, allowed CIDRs" — the README's sentence is a copy of it, and the "labels" entry is wrong in both. The requirement's normative content is that the file is committed and non-secret; the parenthetical illustrates rather than inventories, which is why correcting the README does not put the two in normative conflict. It is still wrong, and correcting it means a `MODIFIED` delta, which costs this change its no-delta exemption and obliges a derived-test dispatch over a five-word list. Disproportionate here, and recorded in `docs/change-queue.md` so the divergence is tracked rather than silent.

**Sweeping stale `openspec/changes/<name>/` paths.** The handoff reserved this explicitly, and it is now moot: `decide-archived-change-reference-policy` (archived 2026-09-07) converted all four, and `grep -n 'openspec/changes' README.md` returns nothing. The citations this change writes follow the settled rule — a requirement as `openspec/specs/<capability>/spec.md` plus its name, a change by name in prose.

**Documenting a pipeline that does not exist.** The handoff warned that `close-ci-verification-gaps` would change what the CI/CD section should say. It landed, and so did `promote-molecule-to-a-required-check`. The section describes the six workflows in the tree and the branch protection read from `gh api repos/:owner/:repo/branches/main/protection` on 2026-09-08, not an intended state.

**Restating what `AGENTS.md` owns.** The Testing section names the three test commands and where each one's tests live. It does not reproduce the reasoning about which row a given subject belongs to, or the `molecule test --all` stop-at-first-failure caveat — those matter to someone already inside the workflow, and duplicating them creates a second copy to keep true.

## What this must not undo

Carried from the handoff, each verified still present in the tree:

- **The Non-goals framing of staging.** "A staging environment is *not* a non-goal — it's an anticipated near-term addition" is a deliberate distinction. Multi-cloud, multi-region and container orchestration remain rejected. Correcting the region must not soften the multi-region non-goal.
- **The credential guidance** at L75-77. It is not decoration: the *Write Credentials Confined to the Gated Pipeline* requirement in `openspec/specs/iac-safety-hardening/spec.md` obliges the README to record that prohibition.
- **The `ansible/` scope boundary** at L39-41 — that it stops at the container runtime and never templates a service-definition file or manages application lifecycle. A real, enforced constraint, not an aspiration.
- **The drift re-enablement runbook** at L196-201, and the whole of the Molecule section's mechanism prose — the digest-pin rationale, why the bare-digest form rather than tag-plus-digest, the `DOCKER_CONFIG` workaround. Verified accurate; only the two counts inside it and the Galaxy command change.
- **The three comments' surrounding prose.** `.ansible-lint`, `.gitignore` and `ansible/requirements.yml` each explain why the installed role is excluded or pinned. Only the command inside each changes.

## Impact

- `README.md` — Non-goals, Repository layout, local-setup step 5, Environment variables and secrets, CI/CD, Testing, Status
- `.ansible-lint`, `.gitignore`, `ansible/requirements.yml` — one comment line each
- `docs/change-queue.md` — entry 9 is delivered here and is deleted with this change, along with the intro bullet naming this change as opened; two new entries record the enforcement and the specification parenthetical this change declines
- No specification delta — `skip_specs: true` is set in this change's `.openspec.yaml`, and `design.md` Decision 1 substantiates it against the three requirements in `openspec/specs/` that bear on this file. No code, no workflow, no Terraform, no Ansible task. Under `AGENTS.md` a change declaring no deltas owes no new tests — only that `python3 -m unittest discover --start-directory .github/tests` stays green. That is not a formality here: its citation-form check walks every committed file outside `openspec/` and `README.md` is one of its four named anchors.
