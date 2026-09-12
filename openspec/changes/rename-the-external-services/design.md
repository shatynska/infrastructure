# Design

Every decision here is about **order**, **evidence**, or **what cannot be tested**. There is no architecture in this change: four names move in three web interfaces and nine files follow them. What makes it worth a design document is that both of the interfaces this change breaks temporarily fail by **creating something under the name you were about to use**, rather than by refusing.

## Decision 1: The order, and why each step sits where it does

| # | Step | Where it must sit | The mechanism that fixes it |
|---|---|---|---|
| 1 | Delete the stray `main-production` Environment; confirm `main-staging` is free | Any time before step 5 | GitHub will not rename an Environment onto a name already in use |
| 2 | Create the two new repository secrets | Any time before step 4 | The pull request's plan jobs read `secrets[<the name pipeline.yml declares>]`; an absent secret resolves to the empty string and the plan fails on authentication |
| 3 | The derived tests, the implementation commit, the documents, **and the whole of the offline verification, the tree-wide sweep and the code review** | Before step 4, all of it | Every one of them is offline. Running them after the rename would hold the window open for the length of a fix round, which is the cost step 4's placement exists to avoid |
| 4 | **Rename both HCP workspaces, then plan locally, then push** | **Immediately before the push** | `terraform init` *creates* an absent workspace, so a `versions.tf` pushed ahead of the rename takes the name the rename needs. The local plan is the only check that can run between the two |
| 5 | Rename both GitHub Environments | **Between approval and merge** | The merge's own apply and converge jobs attach to the names the merged `pipeline.yml` declares; those Environments must exist, with their secrets and their reviewer, at the moment the merge lands |
| 6 | Merge, read staging first, approve production | — | — |
| 7 | Delete the two old repository secrets; delete any workspace created inside the window | After the merge | Nothing reads them once the merged `pipeline.yml` names the new ones |
| 8 | Rename both Hetzner projects | After the merge, before the confirmation | Cosmetic; and decision 7's observation has to follow it |

**Step 4 is late, and an earlier draft of this document had it first.** The reasoning that put it first was that its window should open as early as possible so the pull request closes it immediately — which is the correct instinct and the wrong conclusion, because under this task list the pull request does not follow immediately. Between an HCP rename and a push sit the implementation, an independent test-author dispatch, six document edits, the offline verification and a code review: plausibly days, spanning at least one nightly drift run. The window is bounded by an operator instruction and by nothing else, so the only thing that actually shortens it is doing the rename later. **The window is now `rename → local plan → push → review → merge`**, which is the shortest the mechanism permits: the local plan needs both the renamed workspace and the flipped `versions.tf`, so the two cannot be separated, and the pull request cannot precede the rename because its own plan jobs would create the workspaces.

**What makes step 4 safe to defer is that nothing local reaches HCP before the push.** `pre-commit`'s `terraform_validate` hook runs `terraform init -backend=false` — hardcoded in `_common.sh` at lines 553 and 559 of `pre-commit-terraform` v1.109.1, the revision `.pre-commit-config.yaml` pins, with the only injectable argument being `-no-color`. `terraform_fmt` and `terraform_tflint` read no backend. So a commit made with the flipped `versions.tf` and the old workspace names still in HCP touches nothing remote. That precondition is checked rather than assumed, and it is version-dated because a hook revision bump could change it.

**Step 5 cannot move earlier, for the symmetric reason.** While `main` still declares `github_environment: production` and `platform-deploy.yml` still says `environment: production`, renaming that Environment makes any job reaching it **auto-create an empty one, with no protection rules**. A production apply, converge or platform deploy in that window would run without the reviewer that is the entire point of the gate. Step 5 is therefore as late as it can be while still preceding the merge.

**The standing instruction for both windows is the same and it is the operator's to hold: nothing else merges to `main` between step 4 and step 6.** A Dependabot pull request is safe — a pull request plans, it does not apply — but not free; see decision 2.

## Decision 2: What an absent HCP workspace actually costs — measured, because the received answer was wrong

`docs/change-queue.md` entry 63, the handoff that opened this change, *Remote State Backend* as entry 62 left it, and both `versions.tf` comments all say the same thing: pushing a `versions.tf` ahead of the workspace rename makes **the next plan propose creating every resource from scratch**, and on staging — whose apply requires no reviewer — that plan is applied unattended, building a second server beside the live one.

**That is not what happens, and this repository's own specification already said so.** *Workspace Execution Mode Set to Local* (`openspec/specs/iac-state-management/spec.md`) states that a workspace created for a new stack carries the **remote** default until it is changed, and that under remote execution `terraform plan -out=tfplan` does not yield a locally applicable plan file. The two claims cannot both be true: a workspace `terraform init` creates is a newly created workspace.

**Measured, rather than argued.** The `shatynska` organisation's `default-execution-mode` is `remote`, read from the HCP API on 2026-09-12. So a workspace `terraform init` brings into existence is a remote-execution workspace holding no variables — not a local-execution one ready to plan. What the pipeline does with it is then governed by the requirement above: the saved-plan flow has no plan file to save, so the run fails rather than producing something appliable.

**What this establishes and what it does not.** It establishes the organisation default, which is what decides a created workspace's mode, and it is the same API path `terraform init` uses to create one. It does **not** establish the exact error text, the precise step at which each of the four workflows fails, or that no arrangement of them could apply anything — nothing here ran a plan against an empty workspace, and this change deliberately does not create one to find out. So the correct statement of the hazard is: **a run inside the window fails, and leaves behind an empty workspace holding a name.** The catastrophic reading is retired; the ordering it was used to justify survives on the weaker and better-supported ground that the empty workspace **takes the name the rename needs**, which is the same failure the stray GitHub Environment already demonstrates in the other interface.

**The correction is written back into the requirement**, as a fourth `MODIFIED` delta on *Remote State Backend*. Leaving it would hand the next person planning a workspace rename the same false premise, from the requirement that exists to govern exactly that. This is the rule the handoff transmitted — *a probe that reaches the wrong code path is worse than no probe* — applied to a claim nobody probed at all.

## Decision 3: Renaming rather than re-creating the GitHub Environments

The alternative was to **create** `main-production` and `main-staging` as new Environments carrying copies of the old ones' secrets and protection rules, leave `production` and `staging` in place across the merge, and delete them afterwards. That has no window at all: both names resolve throughout, and the flip is safe in either direction.

It was rejected on one fact: **a GitHub secret's value cannot be read back.** Re-creating the two Environments means re-entering twenty-one secret values by hand, and the operator has to *hold* all twenty-one. Most are recoverable from the password manager by construction (`docs/bootstrap-a-new-host.md` Appendix A says which). Two are not obviously so — each stack's `HCLOUD_TOKEN` write token, shown once by Hetzner, and each stack's `ANSIBLE_SSH_PRIVATE_KEY`, whose public half is installed on the host by hand and committed nowhere. A migration that silently depends on a credential nobody can produce fails at the worst moment, and its recovery is a fresh Hetzner token and a host edit.

**The rename keeps every secret without anyone having to know its value**, which is the property being bought. What it costs is the window in decision 1, bounded by an instruction rather than by a mechanism.

**This rests on a claim this repository cannot test: that GitHub offers an Environment rename preserving secrets and protection rules.** It is asserted by the handoff and by nothing else here. So it is probed rather than assumed, and the probe is free — decision 4.

## Decision 4: The stray `main-production` Environment is deleted, and is used as the probe on the way out

An Environment named `main-production` already exists: created 2026-09-12T06:11:52Z, no secrets, no protection rules, no deployments, and no workflow run at that minute — so it was created by hand, four minutes before `PLATFORM_DEPLOY_HOST` was rewritten, during entry 62's out-of-band steps. It has to go, because it holds the name step 5 renames onto.

Before deleting it, rename it — `rename-probe` will do — and then delete it under the new name. That establishes three things at a cost of nothing: that a rename control exists in this interface at all, which decision 3 depends on and no file here can assert; that it is reachable for this repository and this operator; and that the name is free afterwards.

**It does not establish that a rename preserves secrets or protection rules**, because this Environment has neither. That half stays unproven until step 5 and is checked immediately afterwards by re-listing both Environments against the counts recorded in `proposal.md` — fifteen on production, six on staging, one required reviewer on production.

**It also establishes nothing about `main-staging`**, which step 5 renames onto too and which no probe touches. The Environment listing read on 2026-09-12 shows no such name; the task re-reads it rather than trusting that, because a rename that fails on the second name leaves the pair half-moved with `production` already gone.

**If the rename control does not exist**, this change stops before step 4 and returns to the operator with decision 3's rejected alternative and the question that route depends on: whether all twenty-one values can be produced. That is the operator's decision, not the session's, because the failure mode of guessing wrong is an unrecoverable credential.

## Decision 5: What proves the workspace rename, and why it is not the States view

The handoff proposes reading each workspace's *States* view after the rename and checking it is not empty. That is sound and is kept, but it is the weaker of two available observations.

**A rename preserves the workspace id.** So the stronger check is that `ws-QxowEvdjeZzziZ33` answers to `main-production` and `ws-b2HGxWg9zz2SoCC5` to `main-staging`, and that each still reports four resources and a state serial no lower than the one recorded before — 46 and 4 respectively, read 2026-09-12. An empty workspace created under the intended name has a **different id**, so the id comparison distinguishes the two cases a resource count alone could confuse.

**The second observation is a local plan, and it is the strongest evidence this change can produce before pushing anything.** After the workspace renames, with the flipped `versions.tf` committed but not pushed: `terraform init && terraform plan` in each stack directory, under that stack's **read-only** token, must report `No changes`. A plan proposing to *create* the server, firewall, volume or SSH key means the `cloud` block points at an empty workspace, and the change stops there. `AGENTS.md` permits this — local runs use the read-only token and are for `plan`/`validate` — and it is deliberately done **before** the pull request rather than during production's approval wait, because `docs/change-queue.md` entry 72 records that a plan computed during that wait can be invalidated by anything that moves the state serial, and a local run is one of the candidates that entry could not rule out.

**Staging's half of this needs a file that does not exist on this workstation.** `terraform/stacks/main-staging/.envrc` is absent; without it, `direnv` supplies the repository-root value and the staging plan runs against production's project, which produces a plausible-looking result rather than an error. It is a task rather than a footnote for that reason.

## Decision 6: Staging is the canary, and reading it first is most of what the merge buys

Staging's apply requires no reviewer, so on the merge it runs unattended and reports before production's approval is even requested. Entry 62 met this as a hazard — its staging converge lost a three-second race with its own apply. Here it is an asset: **read staging's plan and apply output before approving production's.**

Both plans must read `No changes`. Staging's is free, arrives first, and is produced by exactly the mechanism production's will use. If staging's plan proposes creates, production's will too, and the approval is simply not given — which leaves production untouched, because a plan that is never approved never applies.

The merge also triggers `host-converge.yml`, because `ansible/inventory/*.hcloud.yml` changes. Unlike entry 62's merge there is **no race** with the apply: this change alters no Hetzner label, so the converge's inventory parse does not depend on the apply having landed. What it does depend on is steps 2 and 5 both having happened.

## Decision 7: The Hetzner project rename is the one claim with no evidence, so it gets an observation of its own

"The Hetzner project rename is cosmetic and its tokens survive it" appears in the queue entry and in the handoff. **Nothing in this change has measured it**, and no file in this repository could. It is plausible — a Hetzner API token is an object inside a project rather than a name derived from it — but plausible is what entry 62's inventory comment was.

So the rename is placed **after** the merge and **before** the confirmation, and the confirmation carries a fifth observation: after the projects are renamed, a local `terraform plan` under each stack's read-only token still reports `No changes`. That is a real authentication against the renamed project, and it is the only evidence this change produces on the point. Placing the rename last also means that if the claim is wrong, it is wrong *after* everything else has landed and been observed, rather than in the middle of the window.

Without that observation the change would archive on a confirmation covering three of its four deliverables, and a token failure would surface afterwards as apparent drift.

## Decision 8: The specification deltas rename a literal, and correct one claim

Eight requirements state the GitHub Environment `production` by name. The available treatments were three:

1. **Replace the literal** — `production` becomes `main-production`. Chosen.
2. **Generalise it** — replace *"the `production` Environment"* with *"that stack's own GitHub Environment"*, the way *Credential Scoping by Privilege* already reads. Rejected: it is a better requirement and a different one. *"The `production` Environment SHALL require a reviewer"* is an obligation about one specific Environment, and a generalised form either drops that obligation or invents a new one about every Environment — neither of which is a rename.
3. **Leave them** — on the reading that `production` there means the environment rather than the Environment. Rejected on the text: *"a secret scoped to the `production` GitHub Environment"* names an identifier, and after this change that identifier resolves to nothing.

A ninth requirement, *Remote State Backend*, is modified for a different reason: decision 2's measurement makes one of its rationale sentences false. That edit changes no obligation — the requirement still obliges one workspace per stack and no derivation between the names — only the explanation of what pushing in the wrong order costs.

**No requirement title and no scenario title moves.** A `MODIFIED` block cannot rename a scenario — `openspec validate` refuses one that omits a scenario the current spec has — and `RENAMED` renames the requirement without reaching its scenarios, so a scenario title can move only where its requirement's title moves too, via a `REMOVED` + `ADDED` pair. Measured against OpenSpec 1.12.0 by entry 62, which left three titles wrong for this reason and disclosed them. Here nothing needs to move: the three titles carrying *production* — *Gated **Production** Apply Applies the Reviewed Plan*, *Gated Deploy Reuses the Terraform **Production** Environment* and *Same approvers gate both kinds of **production** change* — read it as prose, and are still correct.

## Decision 9: Entry 70 is left standing, deliberately, inside a line this change edits

Both `versions.tf` provider comments state prod's read-only secret name wrongly — production's says the name *"for this stack is `HCLOUD_TOKEN`"*, staging's says *"for this stack HCLOUD_TOKEN_STAGING, and for prod HCLOUD_TOKEN"*. That is `docs/change-queue.md` entry 70, recorded by entry 61's code review.

This change edits staging's sentence, because it contains `HCLOUD_TOKEN_STAGING` — a name it moves — and leaves the `HCLOUD_TOKEN`-for-prod half wrong. **Both files carry a parenthesis saying so**, production's added after code review pointed out that the argument below holds only where the note is present: a knowingly-wrong claim with nothing beside it is indistinguishable from an unnoticed one, and production's was the file where the claim is about the stack the reader is standing in. That reads as sloppiness and is the opposite: correcting a factual error about credential names inside a rename is the unrelated scope entry 70 was recorded to hold, and entry 70's own text argues the correction deserves a check rather than a quiet edit. What this change owes instead is that **entry 70 still quotes the tree accurately afterwards** — its two quotations move with the comments it is about.

**Decision 2 corrects a different factual error in those same two comment blocks, and the difference is not that one error is more tolerable.** The creates-claim is the premise this change's own ordering rests on: it is what decides where the HCP rename sits, it was measured in the course of deciding that, and leaving it would mean shipping a comment this change knows to be false about the very step it is performing. Entry 70's error is about credential names, is reached by nothing this change decides, and has a recorded owner. An error a change had to measure in order to act is its own; an error it merely walked past is not.

## Decision 10: This change's verification surface, stated with its holes

What can be checked statically, and is:

- every stack's declaration names the new secret and the new Environment, and the two remain distinct across stacks;
- each inventory source's credential variable equals its stack's declared `read_only_secret` — already asserted generically, and this change is what keeps it true;
- `platform-deploy.yml` declares `environment: main-production` — already asserted, through a constant this change moves rather than a test it adds;
- **no committed file outside `openspec/changes/archive/` names `HCLOUD_TOKEN_PRODUCTION`, `HCLOUD_TOKEN_STAGING`, `infrastructure-prod` or `infrastructure-staging`.** New, and the only mechanism in this repository that can catch a name this change misses — every other check reads a *declaration*, and most of this change's surface is prose around one.

What cannot be checked here, and is not:

- **that any external rename happened.** No test in this repository makes a network call — that constraint is itself asserted by the suite — so every claim about HCP, GitHub settings or Hetzner rests on an observation a human makes and reports. Where this change says a thing was observed, the observation is named and dated.
- **that `ansible/.envrc` on any workstation was updated.** It is gitignored. Nothing sees it, review cannot catch it, and a stale one fails the next local converge at inventory parse.
- **that either GitHub Environment kept its secrets.** `gh secret list --env` is how a human checks it, and it is the only place a loss would show before a deploy failed.
- **that a Hetzner token survives its project's rename.** Decision 7.

**No Molecule namespace is taken, and that is a decision rather than an omission.** `AGENTS.md` obliges taking one where verification writes to that shared service; this change adds no role, edits no role and touches no scenario, and its two Ansible files are read by no scenario. Nothing it does runs Molecule, so nothing it does needs a namespace.
