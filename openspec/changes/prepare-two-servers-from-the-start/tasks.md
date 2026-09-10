Verification for a docs-only change is the static suite from the repository root
and `pre-commit run --all-files`. Neither reads prose for truth, so **every
count this change writes down names the committed file that proves it**, and
each task below gives that file. A count nobody can check in a minute does not
belong in §0.4.

## 1. §0.3 — the keys, and how many of each

- [ ] 1.1 Add the second platform deploy key to §0.3's table. One row per environment, or one row saying "one per environment" with the `-C` comment parameterised — whichever reads better against the existing rows. The reason is already written at §6.1 and must not be restated in full here: one leaked private half must not deploy to both. Evidence that two exist: `ansible/inventory/group_vars/prod.yml` and `staging.yml` each carry a `deploy_apps` entry named `platform` with a **different** `public_key`.
- [ ] 1.2 Correct the inspection-key row, which says "Configured on the production host only, in stage 6". Evidence that it is both: `ansible/inventory/group_vars/staging.yml` carries `ops_user_accounts`, and `ansible/playbooks/host-baseline.yml` runs `ops_user` for whatever environment it targets.
- [ ] 1.3 Re-read §0.3's paragraph about one purpose spanning both environments. It is correct and should survive unchanged — it argues the operator root key is deliberately shared, and that is still true (`terraform/environments/prod/terraform.tfvars` and `staging/terraform.tfvars` carry the same `ssh_public_key`). Check only that the new rows do not contradict it: sharing by *purpose* is the rule, and the platform deploy key is a case where the purpose differs per environment rather than an exception to it.

## 2. §0.4 — what exists once and what exists twice

- [ ] 2.1 Add a new §0.4 whose table lists, for every credential and account the procedure creates, how many exist and why. Each row cites what makes it checkable. The set, with its evidence:

      | Thing | How many | Checkable against |
      |---|---|---|
      | Operator root key | 1, shared | both `terraform.tfvars` carry the same `ssh_public_key` |
      | Operator inspection key | 1, shared | both `group_vars` carry the same `ops_user_accounts` entry |
      | Platform deploy keypair | **2** | the two `deploy_apps` entries differ |
      | Hetzner project | 2 | §1.1 |
      | Hetzner API tokens | 4 — read-only and read-write per project | §1.2 |
      | HCP workspace | 2 | §2, and each environment's `versions.tf` |
      | Ansible inventory credential | 2 | `ansible/inventory/prod.hcloud.yml`, `staging.hcloud.yml` |
      | Ansible Vault password | **2** | the two `!vault` blocks' vault ids: `prod` and `staging` |
      | Tailscale auth key | **2** — one consumed per host at join | §5.3 |
      | Tailscale OAuth client | 1 | §5.3; one client serves every repository |
      | GHCR pull token | 1, shared | both `group_vars` carry the same `ghcr_pull_username` |
      | Heartbeat project ping key | 1, shared | one key addresses every check |
      | Heartbeat checks | 5 | Appendix A's table lists four, plus Alertmanager's from §7.1 |

      Verify each count against the file named before writing it. Any that cannot be checked that way is either wrong or belongs in prose rather than the table.

      **Compare values, not lines.** `terraform/environments/prod/terraform.tfvars` pads its `=` for alignment and staging's does not, so a naive line-by-line comparison reports the two `ssh_public_key` entries as differing when the keys are byte-identical — confirmed by extracting the quoted value from each and hashing it, same digest. The same care applies to the `ops_user_accounts` public keys, likewise identical and likewise formatted differently. Getting this wrong would put **2** in a row whose truth is **1, shared**, and the whole point of the table is that its numbers are right.

- [ ] 2.2 State the rule the table follows, in a sentence or two above it: **a read-only credential is shared, because a copy of it grants nothing extra; a credential that grants access is per environment.** Name the operator root key as the deliberate exception and point at §0.3's paragraph rather than re-arguing it. Do not overstate the rule — the GHCR token is shared because it is read-only, and the ping key because it addresses different checks by host name, which is a second reason and worth the half-sentence.
- [ ] 2.3 Place §0.4 after §0.3 and before stage 1, so a reader meets it while still assembling credentials rather than after committing to a shape. Verify by reading stages 0 to 1 straight through.

## 3. §5.2 and §5.3 — the tailnet, for two hosts

- [ ] 3.1 Make §5.3's auth-key row per host: one key each, and the "Disable key expiry" step repeated per machine. Say that a key generated **reusable** can serve both joins, and that a single-use key cannot — which is also what a failed converge burns. Evidence: `ansible/roles/tailscale/tasks/main.yml` consumes `tailscale_auth_key` once per run, and its `when:` skips the task on an already-joined host.
- [ ] 3.2 Update §5.3's "Secrets created in this stage" table: the auth-key row is two keys, one per host, password manager only. The two `TAILSCALE_OAUTH_*` rows stay as they are — one client serves every repository, and their `production` Environment scope is correct until entry 52 gives staging a deploy workflow of its own.
- [ ] 3.3 Update §5.2's ACL guidance, which is written over "the server" throughout, to name both hosts. Keep its actual advice unchanged: the tailnet runs unrestricted here, and a company tailnet with more members wants an ACL letting `tag:ci` and operators reach each host on 22 and 3000.

## 4. The end-state summary and the time estimate

- [ ] 4.1 Correct the time estimate, which says the second environment "adds perhaps an hour of console work in stages 1 to 3 and nothing after that, since stages 5 to 9 configure one host". Stage 6 configures both. Say what the second environment actually costs: console work in stages 1 to 3, plus a second converge in stage 6 — and note that the second converge is faster than the first, because by then the operator has seen the procedure work once. Evidence: this session's own runs, recorded in `configure-the-staging-host`'s archived task list.
- [ ] 4.2 Re-read the end-state summary above it, which `align-the-bootstrap-doc-with-a-real-run` rewrote. Confirm it and the corrected estimate now say the same thing about what stage 6 does; fix whichever is wrong rather than assuming the newer one is right.

## 5. Verification

- [ ] 5.1 `python3 -m unittest discover --start-directory .github/tests` from the repository root, passing.
- [ ] 5.2 `pre-commit run --all-files`, passing. Neither this nor 5.1 establishes that a count is correct — 2.1 is where that happens, one file at a time.
- [ ] 5.3 Read stages 0 to 6 straight through as an operator holding nothing, and confirm that the set of credentials §0.3 and §0.4 tell them to create is exactly the set stages 1 to 6 then ask for — no more, and nothing missing. This is the check the change exists to make possible, and it is the one a static suite can never do.

## 6. Ship

- [ ] 6.1 Open the pull request once verification passes and the code review has cleared, and wait for the operator's confirmation that it merged.
- [ ] 6.2 **The confirmation gate is answerable and is not waived.** The operator is about to bootstrap a company's infrastructure from this document. The observation is theirs: follow §0.3 and §0.4, assemble the credentials, and report whether the set they hold is the set stage 6 asks for. A gap found there is this change failing at the only thing it does; a clean pass is the confirmation. If that bootstrap is not imminent when this merges, say so and let the operator decide between waiting and waiving — do not waive it unasked.
- [ ] 6.3 Bring the branch back to the freshly fetched trunk and archive the record with `openspec archive`. Verify `openspec validate --archived` passes.

Opening the record's own pull request, and removing the branch and working tree
once it merges, happen after the commit that writes this file, so they are
recorded here in prose rather than as tasks that could never be ticked in the
file containing them.
