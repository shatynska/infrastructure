# Section 5 — the sweep, enumerated

`tasks.md` 5.1 to 5.3 triage rather than edit, so that section 7 corrects from a list instead of re-deriving one mid-edit. This is that list, produced 2026-09-13 against the tree at commit `1e716b7`, after staging's flip and before production's.

**Why enumerated rather than left as a rule.** The rule-based form of this triage was rewritten in three consecutive review rounds and was wrong each time — it missed a third collapsing name set, a `platform/**` file, two `versions.tf` comments and a line-wrapped comment. The fifth round's reviewer observed that three failures of the same shape is evidence about the *form* rather than about any one wording of it. The tree is one pull request away from frozen, and 7.9 runs last, so a list is affordable now in a way it was not when the plan was written.

**Method.** Every needle `tasks.md` 5.1 names, run over `git ls-files` only, excluding `openspec/changes/archive/` and this change's own directory: `entry 75`; `` `production` Environment ``; `` `staging` Environment ``; `environment: production`; `environment: staging`; `--env production`; `--env staging`; bare `` `production` `` and `` `staging` ``; and the unbackticked `production Environment` / `staging Environment`.

**167 hit lines across 32 files.** The broad needles dominate: most bare `` `production` `` hits name the Ansible group, which this change keeps.

## Bucket 1 — the environment axis, kept by design

The largest bucket and the reason 7.9 is a triage rather than an expected-empty sweep. `environment: production` is a substring of `target_environment: production`, which this change deliberately preserves, and the bare backticked names legitimately appear wherever the Ansible group, the `group_vars` file or the `--vault-id` label is meant.

- `ansible/**` throughout — inventory sources, `group_vars/production.yml`, `group_vars/staging.yml`, role READMEs.
- `.github/workflows/host-converge.yml:28` and its siblings — the group the converge targets.
- `terraform/stacks/main-production/pipeline.yml:108` and `terraform/stacks/main-staging/pipeline.yml:57` — `target_environment`, which stays.
- `AGENTS.md`, `docs/naming-conventions.md:39` — the scheme's own statement that the group is on the environment axis.

**Leave every one.** A correction here would be the over-sweep the scheme exists to prevent.

## Bucket 2 — this change's own directory

Excluded from the sweep by construction, and correct as written: `proposal.md`, `design.md`, `tasks.md`, `handoff.md`, `credential-audit.md`, this file, and the two derived test modules' fixture strings.

## Bucket 3 — the three deliberate exclusions from 5.3

- `docs/bootstrap-a-new-host.md:892`, `:893`, `:903` — the application-repository stage. That `production` Environment belongs to a *different* repository, which names its own Environment and has no stacks; `:892` says so explicitly.
- `ansible/roles/deploy_user/README.md:25` — same, an application repository's own Environment.
- `docs/review-2026-09-08-host-readiness.md:15`, `:54`, `:68` — a dated record of what was true on 2026-09-08. Correcting it would make it describe a state that did not exist on its own date.

## Bucket 4 — commentary this change corrects

Reached by no earlier task, because none carries an `entry 75` literal and none is a constant. **These are task 7.6's, and they are the bucket the three earlier rule-based triages kept missing.**

| Site | What it says |
|---|---|
| `.github/tests/test_ci_configuration.py:1699` | unbackticked "production Environment approval request" |
| `.github/tests/test_ci_configuration.py:10502`, `:11153` | the `PLATFORM_` prefix's Environment, and reading one |
| `.github/tests/test_environment_agnostic_pipeline.py:636`, `:967` | prose outside its entry-75 commentary |
| `.github/tests/test_the_external_service_names_are_retired.py:462`, `:465` | the requirement quotation task 7.4 corrects |
| `docs/change-queue.md:378`, `:651`, `:681` | entries describing the deploy job's literal |
| `docs/deferred-work.md:43`, `:293` | both name the old Environment |
| `platform/README.md:10` | "a `production`-Environment-gated job" — **also the deploy trigger**, per task 7.7 |
| `README.md:51`, `:131`, `:155`, `:156` | the write-token line, the entry-75 sentence, the workflow summaries |
| `docs/bootstrap-a-new-host.md` — `:115`, `:143`, `:246`, `:260`–`:269`, `:289`–`:292`, `:307`–`:311`, `:376`, `:381`, `:421`, `:432`, `:682`, `:683`, `:747`, `:804`, `:822`, `:824`, `:959`, `:990` | the whole runbook surface, which is why 5.2 reads it end to end rather than at line numbers |
| `docs/naming-conventions.md:5`, `:51` | the exception banner and its row annotation, task 7.5 |
| `terraform/stacks/main-production/pipeline.yml:19`, `:32`, `:33`, `:82`–`:92` | the declaration and its comment blocks, task 7.1 |
| `terraform/stacks/main-production/versions.tf:47` | task 7.8 |
| `openspec/specs/**` — `iac-cicd-pipeline:163`, `:194`, `:198`, `:792`; `iac-platform-deploy-pipeline:8`–`:63`; `iac-state-management:48` | the eight requirement texts, applied by `openspec archive` at task 10.3 rather than by hand |

**Two already corrected**, in the staging pull request rather than here, because staging's flip falsified them a pull request early: `docs/bootstrap-a-new-host.md:291`–`:292` (`--env staging`) and `terraform/stacks/main-staging/versions.tf:43`.

## Bucket 5 — quotations frozen to a commit, which SHALL NOT be edited

All in `.github/tests/test_terraform_stacks_are_the_iterated_unit.py`, and this is the bucket where a well-meant correction does damage that nothing reports.

- **`DEFECTS`, around `:2800`–`:2823`.** Its own comment reads *"Verbatim from `93bef69^`. Each is followed by the corrected line from `93bef69`, so every needle is exercised in both directions on the same sentence."* Rewriting the defective half to the new Environment name would leave the test **green** while the pair stopped being the before-and-after it claims to be — a needle that no longer discriminates, with no signal at all.
- **The keeper tuples at `:2088` and `:2884`–`:2885`.** Synthetic strings a needle must *not* match, asserting it does not over-sweep. Two of them spell `environment = "prod"` and `ansible/inventory/prod.hcloud.yml` — names that exist nowhere in this tree any more, which is the proof they are deliberately historical rather than claims about HEAD.

**The distinction from `REAL_KEEPER_PROSE` at `:2941`–`:2962`, which task 7.8 *does* correct**, is that its comment claims *"as they stand at HEAD"* and it quotes lines tasks 4.1, 4.4, 7.1 and 7.8 rewrite. A fixture claiming HEAD must follow the tree; a fixture claiming a commit must not.

## What 7.9 verifies

Not an empty sweep. Every remaining hit triages into exactly one of the five buckets above, and the buckets that permit a hit to remain are 1, 2, 3 and 5.
