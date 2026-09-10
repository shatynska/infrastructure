Verification for a docs-only change is the static suite from the repository root
and `pre-commit run --all-files`. Neither reads prose for truth, so **every count
this change writes down names what proves it**, and each task below gives that.
A count nobody can check in a few minutes does not belong in §0.4.

## 1. §0.3 — the keys, and how many of each

- [x] 1.1 Add the second platform deploy key to §0.3's table, as **two rows** rather than one parameterised row. The committed public halves carry `deploy@platform` and `deploy@platform-staging` — not `deploy@platform-prod` — so a `-C "<comment>"` placeholder would send a reader to a comment matching neither. Evidence that two exist: `ansible/inventory/group_vars/prod.yml` and `staging.yml` each carry a `deploy_apps` entry named `platform` with a **different** `public_key`.
- [x] 1.2 **Correct the "Private half lives in" cell for those rows, which is the one instruction in this change that could destroy something.** It currently reads "GitHub secret only; delete the local file after storing it" — true of production's key, and false of staging's: there is no secret to put it in, because `platform-deploy.yml` declares `environment: production` and staging has no deploy path until `docs/change-queue.md` entry 52. `configure-the-staging-host`'s archived task 9.3 says staging's private half goes to the password manager "and in no GitHub secret in this change", and `ansible/inventory/group_vars/staging.yml` says the same. A reader following the inherited cell deletes a key with nowhere to store it, and the recovery is a new keypair, a commit, a pull request and a re-converge.
- [x] 1.3 Correct the inspection-key row, which says "Configured on the production host only, in stage 6". Evidence that it is both: `ansible/inventory/group_vars/staging.yml` carries `ops_user_accounts`, and `ansible/playbooks/host-baseline.yml` runs `ops_user` for whatever environment it targets.
- [x] 1.4 Re-read §0.3's paragraph about one purpose spanning both environments. It is correct and survives unchanged — it argues the operator root key is deliberately shared, and both `terraform.tfvars` do carry the same `ssh_public_key`. Check only that the new rows do not contradict it: the rule it states is one key per *purpose*, and a platform deploy key whose purpose differs per environment is an instance of that rule rather than an exception to it.

## 2. §0.4 — what exists once and what exists twice

- [x] 2.1 Add a new §0.4 whose table lists **every credential, and every account or object of which the procedure creates one per environment**, with how many exist and what proves it. That wording rather than "credential", because two rows — the Hetzner projects and the HCP workspaces — are not credentials.

      **Declare the boundary in the preamble: stages 0 to 6.** Carry the two facts outside it as clauses of that sentence rather than as rows: stage 7's platform-stack secrets are production's alone until entry 52, and §7.3 and Appendix A list them; and §0.3's own fourth row, one deploy key per application, belongs to stage 8. Naming both is what makes the boundary honest — a reader comparing §0.3's four rows against §0.4 otherwise meets a silent omission.

      | Thing | How many | What proves it |
      |---|---|---|
      | Operator root key | 1, shared | both `terraform.tfvars` carry the same `ssh_public_key` |
      | Operator inspection key | 1, shared | both `group_vars` carry the same `ops_user_accounts` entry |
      | Platform deploy keypair | **2** | the two `deploy_apps` entries carry different public keys |
      | Hetzner project | 2 | *Each Environment Has a Dedicated Hetzner Cloud Project* (`openspec/specs/iac-state-management/spec.md`) |
      | Hetzner API token | 4 — read-only and read-write per project | §1.2. **Not six**: each read-only token is *also* exported under a second variable name for Ansible, which §1.2 says outright, and a second name is not a second token |
      | HCP workspace | 2 | the two `versions.tf` |
      | `TF_API_TOKEN` | 1, shared | *HCP Terraform Access via a Static Token, Unsplit by Privilege* (same spec file), cited for "one value, unsplit by privilege" and not for where it is stored — that requirement predates staging, and §3.3 now places it in both Environments |
      | Ansible Vault password | **2** | §6.1 requires it; the two `image_prune_heartbeat_ping_key` blocks carry vault ids `prod` and `staging` |
      | Tailscale auth key | 1 reusable key can serve both joins; this repository used 2 | §5.3, and `ansible/roles/tailscale/tasks/main.yml`, which consumes it once per run and skips on an already-joined host |
      | Tailscale OAuth client | 1 | §5.3 — one client serves every repository |
      | GHCR pull token | 1, shared | §6.1 permits the same token; both `group_vars` name the same `ghcr_pull_username` |
      | Heartbeat project ping key | 1, shared — it addresses the **four** periodic-job checks Appendix A lists. §7.1's Alertmanager check is not one of them: it has a ping URL of its own, held as `PLATFORM_DEADMANSWITCH_URL` | §7.1: "It addresses one check per periodic job, listed with its period and grace in Appendix A", whose table has four rows |

      Verify each against what is named before writing it. **Compare values, not lines**: `terraform/environments/prod/terraform.tfvars` pads its `=` for alignment and staging's does not, so a line comparison reports the two `ssh_public_key` entries as differing when the keys are byte-identical — confirmed by hashing the extracted values. The same applies to the `ops_user_accounts` keys. That mistake would put **2** in a row whose truth is **1, shared**.

      Four rows were wrong in earlier drafts, each in a way that read fluently; the proposal's §0.4 bullet names them. Read that before trusting any row here.

- [x] 2.2 **Point at §0.3's axis rather than restating it.** §0.3's paragraph — "each has a different holder and a different blast radius" — sits four lines above, and a second copy of a rationale is the cost this whole change is about. §0.4's preamble carries a pointer to it plus the one cause §0.3 does not state: **a Hetzner token reaches exactly one project**, so those come in pairs regardless of what they can do. The "What proves it" column carries the rest. §0.3 keeps the reasoning, §0.4 keeps the counts, and each is said once.

      **Do not reintroduce "read-only is shared, access-granting is per environment".** It was the first draft's rule and it mis-sorts four of these rows: the inspection key grants root-equivalent access by docker-group membership and is shared; the ping key lets its holder suppress an alarm and is shared; the Hetzner read-only tokens are read-only and come in pairs; `TF_API_TOKEN` writes state for both and is one value. It is recorded here because it is attractive and the next reader will think of it too.

- [x] 2.3 Place §0.4 after §0.3 and before stage 1, and cross-reference it with Appendix A in both directions: the same set, seen at the moment of assembling it and at the moment of rotating it. Say that the two move together. Verify by reading stages 0 to 1 straight through.

## 3. The two other places that repeat what §0.3 says

- [x] 3.1 **§6.4's "Secrets created in this stage" table carries the same destructive instruction task 1.2 fixes** — its `PLATFORM_DEPLOY_SSH_KEY` row reads "The **private** half of the platform deploy key from stage 0. Store it now, then delete the local file", inside the stage a reader now runs *once per environment*. Fixing §0.3 alone leaves the loss reachable by a second route. Mark that row and `PLATFORM_DEPLOY_HOST` production-only for now, and say where staging's private half goes until entry 52.

      An earlier draft of this task attributed that sentence to Appendix A, which is how §6.4 went unnoticed: Appendix A's cell in fact reads "`ssh-keygen`, platform key". Quote a document before correcting it.
- [x] 3.2 Update Appendix A's **Tailscale server auth key** row, which is singular, and its **`PLATFORM_DEPLOY_SSH_KEY`** and **`PLATFORM_DEPLOY_HOST`** rows, which say "Env secret" with no environment named — both, not just the first, or the asymmetry with task 3.1 recreates in miniature the drift this task exists to close. `configure-the-staging-host`'s task 7.4 gave the Vault-password, GHCR and heartbeat rows "one per environment" and left these two behind. Without this the document's own "complete secret inventory" contradicts §0.3 and §5.3 the day this lands — the exact drift this change exists to remove, re-created one appendix over.

## 4. §5.2 and §5.3 — the tailnet, for two hosts

- [x] 4.1 Settle the auth-key count **once**, and use the same words in §5.3 and §0.4. The truth: `ansible/roles/tailscale/tasks/main.yml` consumes `tailscale_auth_key` once per run and skips the task on an already-joined host, so **one reusable key can serve both joins**. Two are wanted if the key is single-use, or if you want to revoke one host's join without touching the other — which is what this repository did (archived task 9.4 generated staging its own). Do **not** write "one consumed per host at join": a reusable key is not consumed, and the first draft said both things in two places.
- [x] 4.2 Make the "Disable key expiry" instruction per machine — it is a per-node setting, and a host whose expiry is left on drops off the tailnet silently in 180 days.
- [x] 4.3 Update §5.3's "Secrets created in this stage" table for whatever 4.1 settles. The two `TAILSCALE_OAUTH_*` rows stay: one client serves every repository, and their `production` Environment scope is correct until entry 52 gives staging a deploy workflow.
- [x] 4.4 Sweep the singular "the server" out of the rest of stages 0 and 5: §5.2's ACL guidance, §5's opening paragraph, and **two rows in §0.1 and one in §0.2** — §0.2 has only the Tailscale-client row, and no DNS row at all. Keep §5.2's advice unchanged: the tailnet runs unrestricted here, and a company tailnet with more members wants an ACL letting `tag:ci` and operators reach each host on 22 and 3000.

      **One singular in that sweep must stay singular, and making it plural would cause the failure §4.4 warns about.** §0.1's DNS row — "Pointing hostnames at the server" — is correct: §4.4 says "**Do not point a hostname at the staging server**", because staging ships `web_allowed_cidrs = []` and a record aimed at it yields a hostname that times out and a certificate that never issues, with no error naming the cause. Make that row say *the production server* specifically, and leave the reason to §4.4.

## 5. The end-state summary and the time estimate

- [x] 5.1 Correct the time estimate, which says the second environment "adds perhaps an hour of console work in stages 1 to 3 and nothing after that, since stages 5 to 9 configure one host". Stage 6 configures both. Say what the second environment actually costs — console work in stages 1 to 3, plus a second converge in stage 6 — **and stop there**. The first draft added "the second converge is faster than the first"; the record it cited says staging's first converge *failed* at `tailscale up`, was diagnosed by hand and completed only on re-run, and carries no wall-clock timing at all. A planning figure a company will act on is not the place for an unevidenced clause.
- [x] 5.2 Re-read the end-state summary above it, which `align-the-bootstrap-doc-with-a-real-run` rewrote. Confirm it and the corrected estimate say the same thing about what stage 6 does; fix whichever is wrong rather than assuming the newer is right.

## 6. Records

- [x] 6.1 Record in `docs/change-queue.md` that `ansible/inventory/group_vars/staging.yml` still carries its "THIS FILE IS INCOMPLETE, AND THE HOST IS NOT YET CONVERGED" banner above values that have since been supplied, on a host that has since converged. Out of scope here — this change touches no non-documentation file — but an implementer sent to that file for evidence meets a banner saying the opposite of what the file now is.

## 7. Verification

- [x] 7.1 `python3 -m unittest discover --start-directory .github/tests` from the repository root, passing.
- [x] 7.2 `pre-commit run --all-files`, passing. Neither this nor 7.1 establishes that a count is correct — task 2.1 is where that happens, one row at a time.
- [x] 7.3 Read stages 0 to 6 straight through as an operator holding nothing, and confirm that the credentials §0.3 and §0.4 tell them to create are exactly those stages 1 to 6 then ask for — no more, nothing missing, and nothing whose storage instruction is wrong for one environment.

- [x] 7.4 **Read every location of every fact this document states more than once, and confirm they agree.** This closes the defect class rather than the instances, and it is the check that would have caught the last two rounds' findings before a reviewer did: every major after the first round arose the same way — a fact stated in several places, corrected in one of them. The list, and it is short enough to walk:

      | Fact | Stated at |
      |---|---|
      | Where a platform deploy key's private half lives | §0.3, §6.4's secrets table, Appendix A |
      | How many Tailscale auth keys, reusable versus single-use, and key expiry | §5.3's prose, §5.3's secrets table, **§6.3a twice** (the `read -rs` paragraph and the usual-causes list), **§6.4 step 1** (disable key expiry), Appendix A |
      | Which hosts the inspection key is configured on | §0.3, §6.1 |
      | What the heartbeat project ping key addresses | §6.1, §7.1, Appendix A |
      | What stage 6 configures | the end-state summary, the time estimate, **§6's own opening**, "From here on, two hosts" |

      **Rebuild this list rather than trusting it**, by grepping each fact's distinctive phrase — `reusable`, `key expiry`, `delete the local file`, `ping key`, `once per environment`. A hand-written inventory of a document's duplicated facts is itself subject to the mechanism it exists to close, and this one was: two of its five rows were short when first written, both discovered by a reader rather than by the list.

      Note that §7.3 above reads stages 0 to 6, and three of these five have a location **outside** that range — which is how §6.4 and Appendix A were missed twice. This task is not bounded by stage.

## Verification record

**7.1** 557 static tests, OK. **7.2** `pre-commit run --all-files`, all hooks —
after provisioning the worktree, which a first run without the pinned Galaxy
role fails on. Neither reads prose for truth.

**7.3 — stages 0 to 6 read as an operator holding nothing.** The credentials
§0.3 and §0.4 name are the set stages 1 to 6 ask for, and no storage
instruction is now wrong for one environment.

**7.4 — every location of every twice-stated fact, walked.** Rebuilt by grep
rather than from the task's list, which is the point of the task:

| Fact | Locations | Agree? |
|---|---|---|
| Where a platform deploy key's private half lives | §0.3 ×3 (two rows and the explanatory paragraph), §6.4's secrets table | yes |
| Tailscale auth key: reusable, count, expiry | §0.4, §5.3's row, §6.3a ×2, §6.4 step 1, Appendix A | **one fixed** |
| Which hosts the inspection key is configured on | §0.3, §0.4, §6.1, Appendix A | yes |
| What the heartbeat ping key addresses | §0.4, §7.1, Appendix A | yes |
| What stage 6 configures | end-state summary, time estimate, "From here on, two hosts", §6's opening, **Appendix C** | **one fixed** |
| Whether the GHCR token is one value or two | §0.4, §6's opening, §6.4's secrets table, Appendix A | **all four reconciled** |

Its first walk caught one: §6.4 step 1 read "Tailscale admin → Machines: **the
server** is listed… Disable key expiry for it" — unambiguous when stage 6 ran
once, ambiguous now that it runs per environment. It now names the host just
converged and says the step repeats.

**Code review then found two the walk had missed, and both were missing rows
rather than missed locations.** The GHCR token was not on the list at all, and
the document stated it four ways: §0.4 said "1, shared", Appendix A said "one
per environment", §6's opening said the two runs "share no token", and §6.4 said
"per environment". A value counted one way and its storage another, with no
sentence distinguishing them — all four now say one value, stored twice. And
"what stage 6 configures" had a fifth location in Appendix C, still telling a
company reader that the second host *configured* is something they do not get.

Recorded rather than quietly fixed. A hand-built inventory of a document's
duplicated facts is subject to the mechanism it exists to close; this task says
so and then demonstrated it. Six facts now, and the instruction stands: rebuild
the list by grep, do not trust it.

## 8. Ship

- [ ] 8.1 Open the pull request once verification passes and the code review has cleared, and wait for the operator's confirmation that it merged.
- [ ] 8.2 **The confirmation gate, which is answerable the day this merges and is not waived.** Not the company bootstrap: that exercises stages 1 to 6 and a gap it finds would not be attributable to this change. The decisive and immediately performable observation is a **cold read by someone other than the author** — read §0.3 and §0.4 having held none of these credentials, write down the set you would end up holding, and compare it with what §6.1, §6.3 and §6.4 ask for. It needs no Hetzner project and no console. A mismatch is this change failing at the only thing it does; a match is the confirmation. The company bootstrap is then a second, stronger observation of the whole procedure, and worth reporting when it happens, but it is not this gate.
- [ ] 8.3 Bring the branch back to the freshly fetched trunk and archive the record with `openspec archive`. Verify `openspec validate --archived` passes.

Opening the record's own pull request, and removing the branch and working tree
once it merges, happen after the commit that writes this file, so they are
recorded here in prose rather than as tasks that could never be ticked in the
file containing them.
