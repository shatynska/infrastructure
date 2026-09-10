Verification for a docs-only change is the static suite from the repository root
and `pre-commit run --all-files`. Neither reads prose for truth, so **every count
this change writes down names what proves it**, and each task below gives that.
A count nobody can check in a few minutes does not belong in §0.4.

## 1. §0.3 — the keys, and how many of each

- [ ] 1.1 Add the second platform deploy key to §0.3's table, as **two rows** rather than one parameterised row. The committed public halves carry `deploy@platform` and `deploy@platform-staging` — not `deploy@platform-prod` — so a `-C "<comment>"` placeholder would send a reader to a comment matching neither. Evidence that two exist: `ansible/inventory/group_vars/prod.yml` and `staging.yml` each carry a `deploy_apps` entry named `platform` with a **different** `public_key`.
- [ ] 1.2 **Correct the "Private half lives in" cell for those rows, which is the one instruction in this change that could destroy something.** It currently reads "GitHub secret only; delete the local file after storing it" — true of production's key, and false of staging's: there is no secret to put it in, because `platform-deploy.yml` declares `environment: production` and staging has no deploy path until `docs/change-queue.md` entry 52. `configure-the-staging-host`'s archived task 9.3 says staging's private half goes to the password manager "and in no GitHub secret in this change", and `ansible/inventory/group_vars/staging.yml` says the same. A reader following the inherited cell deletes a key with nowhere to store it, and the recovery is a new keypair, a commit, a pull request and a re-converge.
- [ ] 1.3 Correct the inspection-key row, which says "Configured on the production host only, in stage 6". Evidence that it is both: `ansible/inventory/group_vars/staging.yml` carries `ops_user_accounts`, and `ansible/playbooks/host-baseline.yml` runs `ops_user` for whatever environment it targets.
- [ ] 1.4 Re-read §0.3's paragraph about one purpose spanning both environments. It is correct and survives unchanged — it argues the operator root key is deliberately shared, and both `terraform.tfvars` do carry the same `ssh_public_key`. Check only that the new rows do not contradict it: the rule it states is one key per *purpose*, and a platform deploy key whose purpose differs per environment is an instance of that rule rather than an exception to it.

## 2. §0.4 — what exists once and what exists twice

- [ ] 2.1 Add a new §0.4 whose table lists, for every credential the procedure creates **for the infrastructure itself**, how many exist and what proves it. **Declare that boundary in the preamble** — stages 0 to 7, excluding the per-application secrets stage 8 creates — because a table read as complete and not being so is worse than no table.

      | Thing | How many | What proves it |
      |---|---|---|
      | Operator root key | 1, shared | both `terraform.tfvars` carry the same `ssh_public_key` |
      | Operator inspection key | 1, shared | both `group_vars` carry the same `ops_user_accounts` entry |
      | Platform deploy keypair | **2** | the two `deploy_apps` entries carry different public keys |
      | Hetzner project | 2 | *Each Environment Has a Dedicated Hetzner Cloud Project* (`openspec/specs/iac-state-management/spec.md`) |
      | Hetzner API token | 4 — read-only and read-write per project | §1.2. **Not six**: each read-only token is *also* exported under a second variable name for Ansible, which §1.2 says outright, and a second name is not a second token |
      | HCP workspace | 2 | the two `versions.tf` |
      | `TF_API_TOKEN` | 1, shared | *HCP Terraform Access via a Static Token, Unsplit by Privilege* (same spec file) — it writes state for both workspaces |
      | Ansible Vault password | **2** | §6.1 requires it; the two `image_prune_heartbeat_ping_key` blocks carry vault ids `prod` and `staging` |
      | Tailscale auth key | 1 reusable key can serve both joins; this repository used 2 | §5.3, and task 3.1 |
      | Tailscale OAuth client | 1 | §5.3 — one client serves every repository |
      | GHCR pull token | 1, shared | §6.1 permits the same token; both `group_vars` name the same `ghcr_pull_username` |
      | Heartbeat project ping key | 1, shared | `ansible/inventory/group_vars/staging.yml`: "the same project ping key prod uses… it addresses a DIFFERENT check because the check name is derived from `inventory_hostname`" |
      | Heartbeat checks | 5 | Appendix A lists four; §7.1's Alertmanager check is the fifth |
      | Platform stack secrets (`PLATFORM_*`) | 8, production only | §7.3; staging gets its own set with entry 52 |

      Verify each against what is named before writing it. **Compare values, not lines**: `terraform/environments/prod/terraform.tfvars` pads its `=` for alignment and staging's does not, so a line comparison reports the two `ssh_public_key` entries as differing when the keys are byte-identical — confirmed by hashing the extracted values. The same applies to the `ops_user_accounts` keys. That mistake would put **2** in a row whose truth is **1, shared**.

      Two rows were wrong in the first draft and are corrected here rather than silently: an "Ansible inventory credential | 2" row double-counted the read-only Hetzner tokens under their second variable names, and `TF_API_TOKEN` was missing entirely.

- [ ] 2.2 State the axis the table follows, above it. **Do not use "read-only is shared, access-granting is per environment"** — it was the first draft's rule and it mis-sorts four of these rows: the inspection key grants root-equivalent access by docker-group membership and is shared; the ping key lets its holder suppress an alarm and is shared; the Hetzner read-only tokens are read-only and are per environment; `TF_API_TOKEN` writes state for both and is shared.

      Use the axis §0.3 already states — **a different holder and a different blast radius** — under which the counts fall out without exceptions: one holder means one credential (the operator's two keys); one purpose per environment means two (the platform deploy keypair, the Vault password); and a mechanical constraint means two regardless of what the credential can do (a Hetzner token reaches exactly one project). Name that third cause separately rather than folding it into the first two, because it is the reason the read-only tokens come in pairs.

- [ ] 2.3 Place §0.4 after §0.3 and before stage 1, and cross-reference it with Appendix A in both directions: the same set, seen at the moment of assembling it and at the moment of rotating it. Say that the two move together. Verify by reading stages 0 to 1 straight through.

## 3. Appendix A — the inventory that must not disagree with §0.3 and §5.3

- [ ] 3.1 Update Appendix A's **Tailscale server auth key** row, which is singular, and its **`PLATFORM_DEPLOY_SSH_KEY`** row, whose "Value from" cell says "the platform deploy key from stage 0… then delete the local file". `configure-the-staging-host`'s task 7.4 gave the Vault-password, GHCR and heartbeat rows "one per environment" and left these two behind. Without this the document's own "complete secret inventory" contradicts §0.3 and §5.3 the day this lands — the exact drift this change exists to remove, re-created one appendix over.

## 4. §5.2 and §5.3 — the tailnet, for two hosts

- [ ] 4.1 Settle the auth-key count **once**, and use the same words in §5.3 and §0.4. The truth: `ansible/roles/tailscale/tasks/main.yml` consumes `tailscale_auth_key` once per run and skips the task on an already-joined host, so **one reusable key can serve both joins**. Two are wanted if the key is single-use, or if you want to revoke one host's join without touching the other — which is what this repository did (archived task 9.4 generated staging its own). Do **not** write "one consumed per host at join": a reusable key is not consumed, and the first draft said both things in two places.
- [ ] 4.2 Make the "Disable key expiry" instruction per machine — it is a per-node setting, and a host whose expiry is left on drops off the tailnet silently in 180 days.
- [ ] 4.3 Update §5.3's "Secrets created in this stage" table for whatever 4.1 settles. The two `TAILSCALE_OAUTH_*` rows stay: one client serves every repository, and their `production` Environment scope is correct until entry 52 gives staging a deploy workflow.
- [ ] 4.4 Sweep the singular "the server" out of the rest of stages 0 and 5: §5.2's ACL guidance, §5's opening paragraph, and the Tailscale and DNS rows of §0.1 and §0.2. Keep §5.2's advice unchanged — the tailnet runs unrestricted here, and a company tailnet with more members wants an ACL letting `tag:ci` and operators reach each host on 22 and 3000.

## 5. The end-state summary and the time estimate

- [ ] 5.1 Correct the time estimate, which says the second environment "adds perhaps an hour of console work in stages 1 to 3 and nothing after that, since stages 5 to 9 configure one host". Stage 6 configures both. Say what the second environment actually costs — console work in stages 1 to 3, plus a second converge in stage 6 — **and stop there**. The first draft added "the second converge is faster than the first"; the record it cited says staging's first converge *failed* at `tailscale up`, was diagnosed by hand and completed only on re-run, and carries no wall-clock timing at all. A planning figure a company will act on is not the place for an unevidenced clause.
- [ ] 5.2 Re-read the end-state summary above it, which `align-the-bootstrap-doc-with-a-real-run` rewrote. Confirm it and the corrected estimate say the same thing about what stage 6 does; fix whichever is wrong rather than assuming the newer is right.

## 6. Records

- [ ] 6.1 Record in `docs/change-queue.md` that `ansible/inventory/group_vars/staging.yml` still carries its "THIS FILE IS INCOMPLETE, AND THE HOST IS NOT YET CONVERGED" banner above values that have since been supplied, on a host that has since converged. Out of scope here — this change touches no non-documentation file — but an implementer sent to that file for evidence meets a banner saying the opposite of what the file now is.

## 7. Verification

- [ ] 7.1 `python3 -m unittest discover --start-directory .github/tests` from the repository root, passing.
- [ ] 7.2 `pre-commit run --all-files`, passing. Neither this nor 7.1 establishes that a count is correct — task 2.1 is where that happens, one row at a time.
- [ ] 7.3 Read stages 0 to 6 straight through as an operator holding nothing, and confirm that the credentials §0.3 and §0.4 tell them to create are exactly those stages 1 to 6 then ask for — no more, nothing missing, and nothing whose storage instruction is wrong for one environment.

## 8. Ship

- [ ] 8.1 Open the pull request once verification passes and the code review has cleared, and wait for the operator's confirmation that it merged.
- [ ] 8.2 **The confirmation gate, which is answerable the day this merges and is not waived.** Not the company bootstrap: that exercises stages 1 to 6 and a gap it finds would not be attributable to this change. The decisive and immediately performable observation is a **cold read by someone other than the author** — read §0.3 and §0.4 having held none of these credentials, write down the set you would end up holding, and compare it with what §6.1, §6.3 and §6.4 ask for. It needs no Hetzner project and no console. A mismatch is this change failing at the only thing it does; a match is the confirmation. The company bootstrap is then a second, stronger observation of the whole procedure, and worth reporting when it happens, but it is not this gate.
- [ ] 8.3 Bring the branch back to the freshly fetched trunk and archive the record with `openspec archive`. Verify `openspec validate --archived` passes.

Opening the record's own pull request, and removing the branch and working tree
once it merges, happen after the commit that writes this file, so they are
recorded here in prose rather than as tasks that could never be ticked in the
file containing them.
