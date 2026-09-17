# Handoff: refresh-readme-accuracy

No proposal yet. This records why the change was identified, what bears on it, and what it must not undo. The session that takes it up writes the proposal.

Identified by a full-repository audit on 2026-09-06, trunk at `245ef59`.

## Why this was identified

`README.md` makes statements about this repository that are no longer true. `AGENTS.md` was refreshed in `e8ffbec` ("update development-workflow block to v3, fix stale refs"); `README.md` was not, and has drifted since well before that.

| `README.md` says | Reality |
|---|---|
| L22: "Single region (`fsn1`)" | `terraform/environments/prod/terraform.tfvars:8` — `location = "hel1"` |
| L148: "as `terraform/modules/` grows past `terraform/modules/server`" | `terraform/modules/volume` exists, with three `.tftest.hcl` files |
| L174-177: "neither directory has role/playbook or Compose service content yet" | Six Ansible roles and a 602-line Compose stack |
| L132-143: CI/CD lists three workflows | Five exist; `platform-deploy.yml` is unmentioned entirely |
| L163-168: "This repository is being bootstrapped per…" | Bootstrapped; 19 changes archived |
| L42-44: `platform/` is "reverse proxy, shared PostgreSQL instance" | Also Prometheus, Alertmanager, Grafana, and three exporters |

The first row is the one that matters most: a reader trusting the stated region would look in the wrong Hetzner location. The rest mislead about what the repository contains and what CI actually does.

Four of these also cite `openspec/changes/<name>/` paths that no longer resolve — see the boundary below; those are **not** this change's job.

## What bears on it

- `git log --follow README.md` will show which statements were true when written. Several were accurate at the time and were simply overtaken; the proposal is a truth pass, not a rewrite.
- The five workflows as they actually stand: `pr-validation.yml`, `apply.yml`, `drift.yml`, `platform-deploy.yml`, `pre-commit-autoupdate.yml`.
- `openspec/specs/iac-repo-foundations/spec.md` may carry requirements about what the README documents. Check before assuming this is documentation-only with no spec delta.
- `close-ci-verification-gaps` (opened alongside this one) will change what the CI/CD section should say. If that change lands first, describe the result; if this lands first, describe today's behaviour accurately rather than the intended one. Do not document a pipeline that does not exist yet.
- `README.md:154-159` (re-enabling the drift workflow after 60 days of inactivity) and `README.md:84-123` (the Molecule setup, including the `DOCKER_CONFIG` / `credsStore` workaround) were both verified as still accurate during the audit. Leave them.

## What it must not undo

- **The Non-goals section, and its framing of staging.** "A staging environment is *not* a non-goal — it's an anticipated near-term addition" is a deliberate distinction. Multi-cloud, multi-region and container orchestration remain rejected; staging remains anticipated. Updating the region fact must not turn into softening the multi-region non-goal.
- **The credential guidance.** "Never put the Read & Write token here or in any other local file — it lives exclusively in the `production` GitHub Environment secret" stays, verbatim in force if not in wording.
- **The scope boundary statement** for `ansible/` — that it stops at the container runtime and never templates a service-definition file. That is a real, enforced constraint, not an aspiration.

## Explicit boundary: do not sweep the stale OpenSpec paths here

`README.md` cites `openspec/changes/bootstrap-hetzner-iac/design.md` and `openspec/changes/project-foundation/design.md`, neither of which resolves — both are under `openspec/changes/archive/<date>-<name>/` now. It is tempting to fix those four references while editing the file.

Do not. They are four of **58 such references across 33 live source files**, and `docs/change-queue.md` entry 1 records why the whole class is blocked on a policy decision that has not been made: what archiving owes source references. A previous change swept exactly these paths and they have fully re-accumulated since, because sweeping without settling the rule resets a counter rather than fixing anything.

If the policy has been decided by the time this is picked up, the sweep is a separate change (`sweep-stale-openspec-references`) and this one still stays out of it. If it has not, leave the four broken paths in place and say so in the proposal — a known-broken reference tracked in the queue is better than an untracked one-off fix that makes the class look smaller than it is.

The factual corrections in the table above are independent of that decision and can proceed regardless.
