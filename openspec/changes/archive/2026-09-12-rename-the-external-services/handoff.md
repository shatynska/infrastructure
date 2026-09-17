# Handoff — `rename-the-external-services`

`docs/change-queue.md` entry 63. Opened 2026-09-12 by the session that delivered `rename-the-stacks-and-their-resources`, which unblocked it. There is no proposal yet: writing it is the first job of the session that takes this up.

**Read entry 63 in `docs/change-queue.md` first.** It was rewritten while archiving entry 62 and already carries what that change left pointing here. This file is the context that does not belong in a queue entry.

## Why this change is unlike the two before it

**Nothing here is provable by a plan, and that is why it is a separate change rather than part of entry 62.** Entry 61 was verified by a test suite; entry 62 by a `terraform plan` showing four in-place updates. This is four renames in three web interfaces, and every one is a click whose effect no file in this repository can verify.

A green pull request will therefore mean *less* than it usually does here. Budget confidence accordingly and lean on observation — see *What to observe*.

## Order is load-bearing, and it is the opposite of entry 62's

Entry 62's operator steps went **between approval and merge**. The HCP step here goes **before the pull request opens at all**, for a mechanical reason:

1. **Rename each HCP workspace in the HCP interface FIRST.** That preserves its state. Pushing `versions.tf` ahead of the rename points the `cloud` block at a workspace that does not exist, HCP creates an empty one under that name, and **the next plan proposes creating every resource from scratch** — on production, a plan to build a second server beside the live one.
2. Then the commit that flips each `versions.tf`.
3. **GitHub cannot rename a secret.** Create `HCLOUD_TOKEN_MAIN_PRODUCTION` and `HCLOUD_TOKEN_MAIN_STAGING`, flip each `pipeline.yml`'s `read_only_secret`, merge, and delete the old two **afterwards**.
4. Renaming a GitHub **Environment** keeps its secrets and its protection rules. That matters more than it used to: since `apply-host-configuration-through-a-gated-workflow` those Environments hold the converge credentials as well as the Hetzner write token, so a lost Environment loses five secrets on production, not one.
5. The Hetzner project rename is cosmetic and its tokens survive it.

**Do not "simplify" `HCLOUD_TOKEN_MAIN_PRODUCTION` to `HCLOUD_TOKEN_PRODUCTION`.** It is knowingly the second of two secret renames: repository secrets are one flat namespace, and `PRODUCTION` stops being unique at a second tenant.

## The hazard entry 62 met, which this change meets in a worse form

**Staging's apply requires no reviewer, so it enters any broken window unattended.**

Entry 62's merge triggered `apply.yml` and `host-converge.yml` together. Staging's apply ran unreviewed at 05:37:56–05:38:07; staging's converge ran 05:37:41–05:38:06 and read Hetzner at **05:38:04, three seconds before the apply landed the label the converge needed**. It failed before the first play — the designed behaviour — and a re-run fixed it.

This change is worse-shaped for that, because a `versions.tf` pointing at a workspace that does not exist does **not** fail loudly. It plans a full create. So:

- **Do the HCP renames for BOTH stacks before opening the pull request**, not just production. Staging has no reviewer standing between a bad `versions.tf` and an apply.
- On the merge, read staging's apply output before approving production's. Staging is the canary and it is free.

## Tool behaviours established by entries 61 and 62

**`openspec archive` does not apply a `## Purpose` to an existing capability.** Entry 61 found it; entry 62 confirmed it still holds. It reports `→ 0` in the totals and silently leaves every Purpose stale — entry 62's archive read `+ 5, ~ 14, - 4, → 0` and two Purposes were wrong. **Read every touched capability's Purpose by hand and correct it in the archive commit.**

**A `MODIFIED` requirement cannot rename a scenario.** `openspec validate` refuses it: *"MODIFIED … omits scenario(s) the current spec still has"*. `RENAMED` renames the requirement and still cannot rename a scenario. Only `REMOVED` + `ADDED` can — and since a requirement cannot be removed and re-added under its own name, **a scenario title can move only where its requirement's title moves too.** Entry 62 left three scenario titles wrong for this reason and disclosed them. Measured against OpenSpec 1.12.0.

**An Ansible Vault id label is plaintext metadata outside the authenticated ciphertext.** Editing `$ANSIBLE_VAULT;1.2;AES256;prod` to `;production` in place decrypts correctly under the new label with the same password — no re-encrypt, no Vault password needed. Measured against ansible-core 2.21.3. Probably not needed here, but it is the kind of fact that saves a day when it is.

**`tracked_files()` raises when a tracked file is absent from the working tree.** Mid-`git mv`, or while an archive rename is unstaged, three credential scans and three sweep tests fail with `TrackedFilesUnavailable`. **That is the guard working.** Stage the rename and they clear.

## A methodological mistake worth not repeating

Entry 62 claimed — in a file comment, in `design.md`, and to the operator — that a missing label under `strict: true` leaves a host ungrouped rather than failing the inventory parse. **It fails the whole parse.** `Constructable._add_host_to_keyed_groups` raises `AnsibleParserError`, and `ansible.cfg`'s `any_unparsed_is_failed` fails the run.

The claim was inherited from a comment already in the inventory sources — one marked *"MEASURED rather than assumed, against the live API"* — and "confirmed" with a probe using `ansible.builtin.constructed` over a static host var, which does not reach the hcloud plugin's templating path. **A probe that reaches the wrong code path is worse than no probe, because it gets reported as a measurement.** Both inventory sources and that change's `design.md` now carry the correction.

The transferable form, for a change that is four interface clicks: **when you cannot test a thing, say you cannot test it.** Do not reach for the nearest testable thing and let it stand in.

## What to observe, since no plan proves any of this

Entry 62's confirmation was three observations, and they are the model:

- **HCP** — after each workspace rename, the workspace's *States* view still shows its history and its current serial. A workspace that lost its state shows an empty list, and that is the failure this ordering exists to prevent. Check **before** pushing `versions.tf`.
- **The first plan after the flip** must read `No changes` — or at minimum must not propose *creating* the server, firewall, volume or SSH key. A plan proposing creates means the `cloud` block points at an empty workspace. **Stop there.**
- **The Environments** — after renaming, re-list their secrets (`gh secret list --env main-production`). Five on production, two on staging. A rename that lost them shows up here and nowhere else until a deploy fails.

## Files this change touches

Code, and it is genuinely small:

- `terraform/stacks/main-production/versions.tf` and `main-staging/versions.tf` — the `cloud` block's `workspaces.name`, **plus the comment each now carries saying the two names are deliberately out of step until this change.** Those comments are a commitment; deleting them is part of the work.
- `terraform/stacks/*/pipeline.yml` — `github_environment` and `read_only_secret`. **Not `target_environment`**: it names the Ansible group, which is the environment axis, already spelled in full, and is not this change's business.
- `ansible/inventory/main-production.hcloud.yml` and `main-staging.hcloud.yml` — each reads its credential from an environment variable whose name **must equal** the `read_only_secret` its stack declares. That equality is an obligation rather than a coincidence, and `.github/tests` compares the pair. Change them together or the build fails.
- `ansible/.envrc.example`, and every operator's own `ansible/.envrc` — which is gitignored, so review cannot catch a stale one. Say so in the tasks.

`.github/tests` literals, all of which go red until moved:

- `test_a_second_environment.py`: `SECOND_ENVIRONMENT_READ_ONLY_SECRET`, `SECOND_ENVIRONMENT_WORKSPACE`.
- `test_environment_agnostic_pipeline.py`: `PROD_READ_ONLY_SECRET`, `PROD_GITHUB_ENVIRONMENT`.
- Fixture trees in both modules build synthetic declarations from **production's own committed declaration**; a synthetic `prod`/`staging` name in a scratch tree asserts nothing about this repository and does not have to move.

Documents: `README.md` (two paragraphs), `docs/bootstrap-a-new-host.md` (the credential tables and stages 2, 3 and 4 — it is a runbook, so read it end to end rather than grepping it), and `docs/change-queue.md` entry 60, which quotes secret names in passing.

## Specification work

*Remote State Backend* (`openspec/specs/iac-state-management/spec.md`) was rewritten by entry 62 to forbid **computing** a workspace name from a stack's directory name while **explicitly permitting the two to agree**. That wording was chosen so this change is performable: a requirement forbidding the agreement would have made it violate the spec it was delivering. Do not reintroduce a derivation when the names line up — the point is that they agree by convention rather than by rule.

Whether this change owes a delta at all is left to the session that takes it: it changes no *behaviour* any requirement states, so it may well be a `skip_specs: true` change. Its `.openspec.yaml` already carries that line, placed there because an opened change with no deltas fails the required check without it.

## What this change must not undo

- The split between a stack's name and its environment's name. `target_environment` stays where entry 62 put it, and the `group_vars` files stay named for groups.
- The `versions.tf` comments explaining the interval — they are deleted *because this change closes the interval*, not because they were noise.
- *Remote State Backend*'s prohibition on computing one name from the other.

## Sequencing

63 → 64, then 60. Entry 64 is independent and may go either side, but it costs a platform-stack restart and a visible Prometheus scrape gap, so it wants a quieter moment than this one does.
