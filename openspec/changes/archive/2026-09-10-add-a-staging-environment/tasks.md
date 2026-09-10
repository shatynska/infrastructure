## 0. A note on what this task list may contain

Branch and working-tree removal happen after this change's record has merged, which is
after the commit that writes this file — a task for them would be unticked by
construction forever. They are recorded in prose in the archive group instead. This is
the repository's own convention (`AGENTS.md`, "Task lists, archived records, and
disclosing what was not done"); the archive step itself is a task and is unaffected.

Group 1 is operator work — outside this repository, or requiring credentials this
working tree does not hold. No commit can perform or verify it. Its tasks are ticked on
the operator's report, and each says what report would satisfy it. Tasks 2.5 and 2.6 are
operator work too, for the same reason, and are marked where they sit because their
ordering among the file-writing tasks is what matters. Nothing in group 2 onward may be
pushed until group 1 is complete — design.md Decision 6 is the reason, and it is the
ordering this change most depends on.

## 1. Outside the repository, and first

- [x] 1.1 Create a Hetzner Cloud project dedicated to staging. Verify by its appearing in
  the Hetzner console as a project separate from prod's, holding no resources.
- [x] 1.2 In that project, create a **Read Only** and a **Read & Write** API token.
  Verify that both are listed in that project's security settings, and that neither is
  written to any file in this repository or exported in any shell — the Read & Write one
  is confined to a GitHub Environment secret and nowhere else (*Write Credentials
  Confined to the Gated Pipeline*, `openspec/specs/iac-safety-hardening/spec.md`).
- [x] 1.3 While in that project's console, record the current 2-vCPU shared-vCPU server
  type name and its monthly price, which design.md Decision 4 leaves open because this
  working tree holds no credential to read it with. Verify by writing the confirmed
  string into task 2.3's `terraform.tfvars` rather than a guess.
- [x] 1.4 Create the HCP Terraform workspace `infrastructure-staging` in the `shatynska`
  organization, CLI-driven (no VCS connection), and set its Execution Mode to **Local**.
  Verify both in the workspace's settings — the mode is per workspace and defaults to
  remote, so a workspace created and not adjusted is misconfigured
  (*Workspace Execution Mode Set to Local*, `openspec/specs/iac-state-management/spec.md`).
- [x] 1.5 Create the GitHub Environment `staging` with **no** required reviewer, holding
  `HCLOUD_TOKEN` (staging's **Read & Write** token) and `TF_API_TOKEN` (the same HCP
  token value the `production` Environment holds). Verify that `HCLOUD_TOKEN` is defined
  *on the Environment*: an Environment that omits it silently resolves the repository
  secret of that name, which is prod's read-only token, and the apply job's guard exists
  for exactly that (*Credential Scoping by Privilege*,
  `openspec/specs/iac-cicd-pipeline/spec.md`).
- [x] 1.6 Create the **repository** secret `HCLOUD_TOKEN_STAGING` holding staging's
  **Read Only** token. Verify it is repository-scoped, not environment-scoped: plan and
  drift jobs declare no `environment:` and can reach repository secrets only.
- [x] 1.7 Confirm the whole set before anything is pushed: `gh secret list` shows
  `HCLOUD_TOKEN_STAGING` at repository scope, `gh secret list --env staging` shows
  `HCLOUD_TOKEN` and `TF_API_TOKEN`, and the `staging` Environment has no reviewer while
  `production` still has one.
- [x] 1.8 Provision **this working tree** for tasks 2.5–2.6: staging's **Read Only**
  token, and HCP credentials available to the Terraform CLI. A fresh working tree carries
  tracked files only and therefore no credential at all (`AGENTS.md`, "Provision before
  relying on any verification result"). `HCLOUD_TOKEN` is one environment variable and
  each environment has a token of its own, so scope staging's to staging's directory — a
  `.envrc` inside `terraform/environments/staging/` (both `.envrc` and `.env` are
  gitignored), or an explicit export in the shell that runs 2.5–2.6 only. Verify the HCP
  half with `terraform init` in `terraform/environments/prod/`, which needs no Hetzner
  token at all, and verify the Read & Write token is in none of it. **Do not verify by
  planning prod under staging's token**: it would refresh prod's state against staging's
  project, 404 every resource, and print a plan that reads as though prod's
  infrastructure were gone.

## 2. The environment directory

- [x] 2.1 Add `terraform/environments/staging/versions.tf` with the `cloud` block naming
  the `infrastructure-staging` workspace, and a provider comment stating which token
  applies in which context — this environment's read-only secret is
  `HCLOUD_TOKEN_STAGING`, and its Environment-scoped `HCLOUD_TOKEN` is the write one.
  Verify that no other environment's `versions.tf` names the same workspace.
- [x] 2.2 Add `variables.tf`, `outputs.tf` and `ssh_key.tf`. `variables.tf` SHALL declare
  `server_enabled` and `volume_enabled` with prod's defaults — design.md's rollback and
  its cost-pause both rest on them, and no requirement obliges them for staging, so
  omitting them would leave two documented properties silently absent. `ssh_key.tf`
  creates `hcloud_ssh_key` named `staging` with the `environment = "staging"` label and
  **no** `moved` block — prod's exists for a one-time relocation that has no staging
  analogue (design.md Decision 5). Verify `terraform fmt -check` passes for the directory
  and that `terraform plan` in 2.6 shows the toggles working by inspection of the
  variable defaults.
- [x] 2.3 Add `main.tf` and `terraform.tfvars`: the same `server` and `volume` modules
  prod calls, `environment = "staging"`, the server type confirmed in 1.3,
  `location = "hel1"`, `ssh_allowed_cidrs = ["176.104.184.0/24"]`,
  `web_allowed_cidrs = []` (no web rule until something is behind it),
  `server_enabled = true`, `volume_enabled = true`, `volume_name = "main-data"`,
  `volume_size = 10`, `delete_protection = false` and `backups = false` on the server,
  and `delete_protection = false` on the volume. Verify every value against design.md
  Decision 4's table and the paragraph under it, which states the ones that are
  deliberately prod's.

  **Result (2026-09-10). Written except `server_type`, which is why this stays
  unticked.** `main.tf` and `terraform.tfvars` carry every value above. `server_type`
  is deliberately absent, with a comment in `terraform.tfvars` naming task 1.3 and
  saying why: no credential in this tree can confirm which 2-vCPU type name is
  current, and an unset required variable fails `terraform plan` by name, loudly,
  destroying nothing — where a plausible guess would be discovered at apply against
  a project that already exists. Ticking this task is task 1.3's operator writing
  the confirmed string in.

  **Result (2026-09-10). Closed by task 1.3: `server_type = "cx23"`**, read off the
  Hetzner console for staging's own project by the operator and written in with the
  comment kept, so the next reader sees it was read rather than assumed. The plan in
  2.6 accepted it.
- [x] 2.4 Add `pipeline.yml` declaring `github_environment: staging`,
  `read_only_secret: HCLOUD_TOKEN_STAGING` and `destroy_policy_gate: false`, with
  comments explaining the last rather than restating the field. Verify both names differ
  from prod's — discovery fails the pipeline naming both offenders otherwise — and that
  `terraform validate` and `terraform fmt -check` still pass, since Terraform must not
  read this file.
- [x] 2.5 Run `terraform init` in the new directory and commit the generated
  `.terraform.lock.hcl`
  (*Provider Lockfile Committed*, `openspec/specs/iac-repo-foundations/spec.md`). Verify
  the file is committed and that its provider version matches prod's lockfile — both
  directories consume the same modules at the same commit. **Do not copy prod's
  lockfile** if `init` cannot be run: the two would probably be identical, which is what
  makes the substitution tempting and wrong, and the correct outcome is this task
  disclosed under `## Not performed` with a `Reason:` label (`AGENTS.md`, "Work not
  performed is disclosed"), **plus** a `docs/change-queue.md` entry to produce the
  lockfile, named in the disclosure — without one, *Provider Lockfile Committed* stays
  unmet with nothing in this repository able to detect it.

  **Result (2026-09-10). Done, and the credential premise was wrong.** This task and
  design.md Decision 6 both assumed the lockfile needed the workspace to exist.
  `terraform init -backend=false` skips backend initialisation entirely, resolves
  providers and writes the lockfile with no HCP credential, no Hetzner token and no
  workspace. Run in this tree; `terraform validate` passed afterwards. The result is
  byte-identical to prod's `.terraform.lock.hcl` — the outcome the copy would have
  produced, reached by generating it, so identity is an observation rather than an
  assumption. Neither the no-copy rule nor the disclosure contingency was needed;
  both stay written down for the case that genuinely needs the backend. Decision 6
  is corrected in place.
- [x] 2.6 **(operator, needs 1.8)** Run `terraform plan` in the new directory under
  staging's **Read Only** token and read what the first apply will create. Verify it
  shows the server, its firewall, the SSH key and the volume, destroys nothing, and — the
  point of running it locally at all — that the read-only token is refused nothing a plan
  needs, so the pipeline's plan job will behave the same.

  **Result (2026-09-10). `Plan: 4 to add, 0 to change, 0 to destroy.`** The four are
  `hcloud_ssh_key.this` (named `staging`), `module.server[0].hcloud_firewall.this`,
  `module.server[0].hcloud_server.this` and `module.volume[0].hcloud_volume.this`.
  Every value the design fixes appears as declared: `cx23`, `ubuntu-26.04`, `hel1`,
  `staging-server`, `delete_protection = false`, `rebuild_protection = false`,
  `main-data` at 10 GB, and the `environment = "staging"` label on all four.

  Two things the plan establishes that no file could. **The firewall carries exactly
  one rule** — SSH from `176.104.184.0/24` — and no 80/443 rule at all, which is
  `web_allowed_cidrs = []` working as Decision 4 says rather than as an empty list
  that happens to render as an open one. And **the run was local**: the output
  carries no "Running plan in HCP Terraform" banner, which is the observable
  difference between Local and the remote default, so task 1.4's Execution Mode
  setting took effect. Run under staging's Read Only token; nothing was refused.

  Operator group 1 verified from this tree rather than taken on report:
  `HCLOUD_TOKEN_STAGING` present at repository scope, `HCLOUD_TOKEN` and
  `TF_API_TOKEN` present on the `staging` Environment, and that Environment's
  `protection_rules` is `[]` with no branch policy — the absent reviewer Decision 2
  requires, confirmed rather than assumed. `terraform init` reached
  `infrastructure-staging` and reused the committed lockfile without changing it,
  which retroactively confirms 2.5's `-backend=false` lockfile was the real one.
- [x] 2.7 Add `/terraform/environments/staging` to `.github/dependabot.yml`'s terraform
  `directories`. Verify by running the CI-configuration suite, which compares that list
  against the tree and fails on divergence.

## 3. Bringing the record to two environments

- [x] 3.1 Apply the four specification deltas — they are this change's own delta files
  and reach `openspec/specs/` only at archive; verify with `openspec validate
  add-a-staging-environment --strict`.
- [x] 3.2 Generalise the never-apply-locally record in `AGENTS.md`'s "Production changes
  never bypass the pipeline" section so it states the prohibition over every environment
  rather than naming `terraform/environments/prod/`, keeping prod's reviewer gate stated
  as prod's. Verify against the *Write Credentials Confined to the Gated Pipeline*
  scenario "The record covers an environment added after it was written".
- [x] 3.3 Generalise the same record in the README's runbook, and bring **both** places
  the README describes staging as anticipated to what is now true — the "not a non-goal"
  paragraph near the top and the Status paragraph near the end, including its pointer to
  `docs/change-queue.md` entry 49 as recording "the full list for staging specifically",
  which task 3.4 repurposes. Keep the adding-an-environment checklist as what *adding an
  environment* takes. Verify by grepping the README for `staging` and reading every hit,
  and that no environment is the sole subject of the local-apply prohibition.
- [x] 3.4 Replace `docs/change-queue.md` entry 49 with an entry for the half this change
  does not carry — the Ansible and platform work, `hosts:` becoming a parameter,
  `group_vars/staging.yml`, the first local converge, DNS — preserving entry 49's own
  reasoning for each rather than summarising it away, and lift entry 23's block, whose
  stated blocker was staging's existence. The new entry SHALL also carry forward the
  constraint design.md Decision 3 depends on: staging holds nothing irreplaceable, and a
  change that puts a store on it either preserves that or states that it is spending it.
  It SHALL also record that staging ships with `web_allowed_cidrs = []` and therefore no
  cloud-firewall rule on 80/443, so the successor opens them deliberately rather than
  meeting a platform stack that comes up unreachable with nothing in its own diff to
  explain why.
  Verify both entries read correctly against what this change actually delivered, not
  against what it proposed.

  **Result (2026-09-10). Done, and entry 23's block was re-pointed rather than
  lifted.** Entry 49 is replaced by entry 50, `configure-the-staging-host`, carrying
  entry 49's own reasoning for the two purposes, the first-converge genesis argument
  and the memory finding, plus the two constraints this change asks it not to undo
  (`web_allowed_cidrs = []`, and staging holding nothing irreplaceable). This task's
  own wording said to *lift* entry 23's block; that turned out to be wrong against
  what was delivered. Entry 23 needs a non-prod host to **converge** against, and
  staging is not yet an Ansible target — no `group_vars`, no play that can name it,
  no first converge. Its block now names entry 50, with the re-pointing and its date
  recorded in the entry itself.
- [x] 3.5 Revisit **every** `docs/deferred-work.md` entry whose stated revisit trigger
  names a second or staging environment — derived by reading the file, not from a count;
  design.md Decision 8 lists the six and why "An apply can still cancel another apply" is
  not among them. Verify that the `rebuild_protection` entry's "There is one environment"
  premise is corrected, that the DNS entry records that its trigger fires on the
  successor rather than here, and that each remaining entry names a trigger that still
  has not fired.
- [x] 3.6 Add a `docs/deferred-work.md` entry for promotion ordering — that applies are
  unordered by design, that the ordering a reader might expect is the approver's
  discipline, and what a future change wanting a mechanism must not reintroduce
  (design.md Decision 7). Verify it states a revisit trigger.
- [x] 3.7 Add a `docs/deferred-work.md` entry naming the three pipeline paths two
  environments still do not exercise — two plan comments on one pull request, two apply
  jobs in one run, one of two applies pausing — why manufacturing a module change to
  reach them was refused, and that the next change under `terraform/modules/` supplies
  them for free (design.md Decision 9). Verify it names that as the trigger.
- [x] 3.8 Add a `docs/deferred-work.md` entry for the four requirements left prod-named
  on purpose — *Conditional Prod Server Creation*, *Conditional Prod Volume Creation*,
  *Data Durability for Stateful Resources* and *No Store on This Host Holds Data
  Requiring Backup*, the last two of which say "this host" and become ambiguous at two.
  Verify it names staging acquiring a persistent store as the trigger, and that
  design.md's Non-Goals no longer claims they were already recorded.

## 4. Verification

- [x] 4.1 Run the derived tests for this change and confirm they pass:
  `python3 -m unittest discover --start-directory .github/tests` from the repository root.
  Until this is run in a provisioned tree it is not evidence — `pip install -r
  .github/requirements-ci.txt` first.
  **Result (2026-09-10).** `python3 -m unittest discover --start-directory .github/tests`
  from the repository root: **529 tests, OK**. Baseline before the implementation was
  529 with 5 failures, all five in `test_a_second_environment.py` and all five closed
  by this change's own work — the environment directory closed two, the `AGENTS.md`
  and README record edits closed two more, and the README's anticipation wording
  closed the last. Tree provisioned first: `pip install -r .github/requirements-ci.txt`,
  `ansible-galaxy role install -r ansible/requirements.yml -p ansible/roles`,
  `npm --prefix .github ci`, all exit 0.

  One existing test's **docstring** was corrected, not its assertion:
  `test_environment_agnostic_pipeline.TestTheWriteCredentialBoundaryIsStatedToAgents`
  quoted the scenario as requiring "production changes", which this change's delta
  widens to "infrastructure changes". The fragments it matches survive the
  generalisation and still pass.

  **A second test correction (2026-09-10), found by running the real
  `terraform init`.** `test_no_environment_directory_holds_a_state_file` walked
  `*.tfstate*` at every depth under an environment directory, so it failed the
  moment a `cloud` backend was initialised: `terraform init` writes
  `.terraform/terraform.tfstate`, which holds `{version, terraform_version,
  backend}` and no `resources` key — the backend configuration cache, carrying
  that name for historical reasons. The assertion would have failed on any machine
  that ran the `terraform init` this repository's own README prescribes, which is
  a defect in the check rather than a finding about the tree.

  `.terraform/` is now excluded, and the assertion was **not** otherwise
  weakened: it still fails on a `terraform.tfstate` at an environment directory's
  root, which is where a local backend actually writes state. Verified by
  injecting one — the test went red — and removing it again, red to green in the
  same run. The exclusion is documented in the test's own docstring, including
  what it still catches and which companion assertions cover the rest.

- [x] 4.2 Run the rest of this repository's static verification over the new directory:
  `terraform fmt -check`, `terraform validate`, `tflint`, and the pre-commit hooks.
  Verify each passes for `terraform/environments/staging/` specifically, not only for the
  tree as a whole.

  **Result (2026-09-10).** All four pass against the staging directory: `terraform
  fmt -check -recursive terraform/`, `tflint` (exit 0, no findings), `terraform
  validate` ("Success! The configuration is valid" — after `terraform init
  -backend=false`, which installs the modules `validate` needs without touching the
  backend), and the pre-commit hooks on the implementation commit, where the three
  Terraform hooks report Passed rather than Skipped for the first time in this
  change.
- [x] 4.3 Run `openspec validate --all` and `openspec validate --archived`. Verify both
  pass, since the pull request requires them.
- [x] 4.4 Confirm that `git diff --stat` against `main` shows **no file under
  `.github/workflows/`**. Verify by reading the list rather than by recalling the intent:
  this is the claim *Each Environment Declares Its Own Pipeline Configuration* makes, and
  the first change able to falsify it.

  **Result (2026-09-10).** `git diff --name-only origin/main` filtered to
  `.github/workflows/` returns nothing: 24 files changed, none of them a workflow.
  Compared against `origin/main` rather than the local `main` ref, which is stale by
  one merge and would have shown the previous change's diff as this one's. The claim
  holds for the first environment ever added under it. `openspec validate --all`:
  10 passed, 0 failed. `openspec validate --archived`: 37 passed, 0 failed (4.3).

## 5. Review, ship and observe

- [x] 5.1 Dispatch `ai-toolkit:change-code-reviewer` over this change's diff once 4.1–4.4
  pass, and act on its verdict. Verify the round is recorded here with what it found.

  **Result (2026-09-10), round 1, nine findings, all acted on.** No defect in the
  Terraform and no weakened test; the review confirmed the deliberate differences
  and matches against Decision 4, the lockfile's legitimacy, the four requirement
  implementations, and that no workflow file is touched.

  Two findings were substantive. **The dynamic inventory cannot see two Hetzner
  projects** — a hazard this change's own Decision 1 creates and no artifact
  recorded: `ansible/inventory/hcloud.yml` authenticates with one `HCLOUD_TOKEN`,
  which reaches one project, so the `staging` group is empty under prod's token and
  `prod` is empty under staging's. A play matching no host exits 0, so a converge
  that reached nothing reads as success. Fixed in three places — the inventory
  comment that still claimed adding staging was "a label value, not an inventory
  rewrite", entry 50, which now owns it as work, and the README's step 4, which
  prescribed the repo-root `.envrc` where task 1.8 prescribes a directory-scoped
  one. **`server_type` unset** was confirmed as blocking: all three workflows run
  `-input=false`, so the plan exits non-zero and `pr-validation.yml`'s conclusion
  step fails the required check. It stays as it is — the branch is not pushed until
  task 1.3 closes — and the reviewer's suggestion of a static check that every
  `terraform.tfvars` assigns each no-default variable is queued rather than built.

  Also fixed: four README passages and `.envrc.example` that describe the
  repository at one environment in sentences containing no occurrence of the word
  `staging`, which task 3.3's grep could not reach; entry 50 having dropped entry
  49's secret set (Vault password, tailnet OAuth client, platform's eight); a
  deferred-work entry written in the past tense about runs that have not happened;
  `proposal.md` still saying entry 23's block was "lifted"; two `design.md`
  pointers to the deleted entry 49; and `name = "staging-server"`, which the module
  composes into the firewall name `staging-staging-server` — now `main-server`,
  free for the same reason `main-data` is, with a row added to Decision 4's table
  since it looks like it should differ.

  **Round 2 (2026-09-10), one finding, and it was a regression the previous round
  introduced.** Eight of the nine fixes held. The ninth did not: `main-server` was
  the reviewer's round-1 suggestion and mine to apply without checking what else
  consumes the value. `modules/server` sets the **server's** name from it and
  composes only the **firewall's** as `<environment>-<name>`, and the hcloud
  inventory plugin derives `inventory_hostname` from the server name — so
  `main-server` would have given both environments one host name. That merges them
  under any inventory reading both projects, and gives them one
  `<inventory_hostname>-prune-host-images` heartbeat check, where prod's weekly
  success masks a dead staging timer. `docs/bootstrap-a-new-host.md`, Appendix C,
  already described that failure as a hypothetical about a company host; it would
  have become true of this repository. Reverted to `staging-server`, accepting the
  cosmetic firewall name `staging-staging-server`: a wart in a console beats a
  silent one in an alarm. Decision 4's row records the trade, `terraform.tfvars`
  says it where the value is set, and Appendix C now names staging as the reason
  the warning is no longer hypothetical.

  Also from round 2: the README's non-`direnv` path (`source .envrc`) loses the
  directory-scoping the fix above relies on, since the export outlives the
  directory — one clause added saying to use a shell you do not reuse. Round 2
  confirmed the inventory fix holds and that entry 50 is a complete enough brief
  that its author will not re-derive the problem.
- [x] 5.2 Open the pull request and read it against design.md Decision 9's list of what
  this run is **specified** to do — this pull request affects staging alone, so one plan
  comment is correct and two would be a defect. Verify, and record here: discovery
  emitted two entries; the affected-environment narrowing selected staging and excluded
  prod; exactly one plan comment appeared, for staging; its plan authenticated under
  `HCLOUD_TOKEN_STAGING`, a secret name no run has resolved before; no job paused for an
  approval; every required check passed.

  **Result (2026-09-10), PR #125, run 34457522320.** Every observation this task
  asks for, read off the run:

  - **Discovery emitted two entries** — `[{"name":"prod","github_environment":"production","read_only_secret":"HCLOUD_TOKEN","destroy_policy_gate":true},{"name":"staging","github_environment":"staging","read_only_secret":"HCLOUD_TOKEN_STAGING","destroy_policy_gate":false}]`. The first time this step has produced a set rather than a single-element list, and the distinctness rules it enforces had two names to compare rather than one.
  - **The narrowing excluded prod** — `Affected environments (1): [staging]`. That path has existed since `make-the-pipeline-environment-agnostic` and until now had nothing it could exclude.
  - **Exactly one plan comment**, for staging: `Plan: 4 to add, 0 to change, 0 to destroy`. Two would have been the defect; the round-1 plan review is what caught this task originally asking for two.
  - **`HCLOUD_TOKEN_STAGING` resolved** — the matrix carried the name, the plan authenticated, and no run before this one had ever resolved a second read-only secret.
  - **No job paused**, and no `production` approval was requested.
  - Every required check passed, including seven Molecule scenarios and `validate`.

  **One failure on the way, and it was not this change.** The first `plan (staging)`
  died on `Error acquiring the state lock`, and the lock it collided with had been
  created **120 ms earlier by a GitHub runner running a plan** — the same job. No
  other run in the repository touched that workspace and no local `terraform`
  process was alive, so the lock request reached HCP, its response was lost, and
  the client's retry was refused by its own lock. The workspace was left `locked:
  true` with `current-run: null`: a lock with no operation behind it, which every
  later plan would keep failing against. `validate` then failed at exactly one step
  — "Conclude on the plan matrix's behalf" — which is the required check doing its
  job rather than a second fault.

  Released via the HCP API after establishing there was nothing to protect: the
  workspace had **no current state version at all** (404) and no run in flight, so
  no concurrent writer could be corrupted. Re-ran the failed jobs; both passed.
  Worth knowing for the next environment, since a first plan against a brand-new
  workspace is where this appeared.
- [x] 5.3 On the operator's confirmation that it merged, record what the apply run did:
  which environments entered it (staging only), that staging's apply ran without pausing
  — this repository's first apply reaching real infrastructure with no approval click —
  and that no `production` approval was requested. Verify against the run, not against
  the expectation.

  **Result (2026-09-10), run 34458573224, after five attempts.** `Apply complete!
  Resources: 4 added, 0 changed, 0 destroyed` — `server_id = 165402032`,
  `server_ipv4_address = 62.238.17.177`, `volume_id = 106839043`. Staging alone
  entered the run; no `production` approval was requested; the apply did not pause.

  **The four failures before it were one cause: the `staging` Environment's
  `TF_API_TOKEN` was an HCP *organisation* token.** HCP issues three kinds and they
  are not interchangeable — an organisation token administers workspaces, teams and
  variables but cannot perform state operations, which a user token can. The
  signature is what made it expensive: `terraform init` **succeeds**, because
  reading a workspace is organisation administration, and the run then dies at
  `Error acquiring the state lock / Error message: resource not found`, because HCP
  reports the authorisation failure as a 404. The error names the lock; the cause is
  the credential; every remedy the message suggests is the wrong one.

  What identified it: the organisation token's `last-used` timestamp read
  `2026-09-10T09:24:47.741Z`, and the failing job's `terraform init` ran at
  09:24:47.74 with its lock failing at 09:24:49.66. Nothing else was talking to HCP
  in that second. The asymmetry was visible throughout and was read too slowly — the
  plan jobs, which use the *repository* copy of `TF_API_TOKEN`, locked the same
  workspace successfully in every one of those runs.

  **Two changes made while chasing it were unnecessary, and are disclosed rather
  than presented as steps.** The workspace's `terraform-version` was changed from
  HCP's creation default of `1.16.2` to `1.9.8`, matching the `~> 1.9` the pipeline
  pins; harmless and arguably more accurate, and it is left in place. An empty state
  version (`serial 1`, `resources: []`) was pushed by the operator to test whether a
  workspace that had never held state was the cause; it was not, the apply overwrote
  it as serial 2, and nothing depends on it. Neither belongs in the runbook, and the
  runbook does not gain them.

  **What does go in the runbook** is the token kind. `docs/bootstrap-a-new-host.md`
  stage 2 previously offered an organisation token as an equivalent alternative to a
  user token, which is what was followed; it now requires a user token from Account
  settings → Tokens, names the two kinds that do not work, and carries the failure
  signature and the `last-used` check that identifies it. The README's
  adding-an-environment checklist and both secret tables say the same.

  One further finding, from a wrong turn of mine: **`gh run rerun --failed` can never
  repair a failed apply.** The plan job does not re-run, so no artifact is produced
  for the new attempt, while the apply job derives the artifact name from the current
  attempt number — the download fails with `Artifact not found for name:
  tfplan-staging-attempt-2`. The workflow's own error message prescribes the remedy
  (a fresh push to `main`); a full `gh run rerun` also works, since it re-runs the
  plan job. Nothing states this where a person looks before trying.
- [x] 5.4 Confirm the effect with the operator: staging's server and volume exist in the
  staging Hetzner project, prod's project is unchanged, and the **next nightly drift
  sweep** plans both environments in one run. That sweep is the genuine two-environment
  exercise this change reaches — two plan jobs, two read-only secrets, one shared
  heartbeat, and no concurrency group at all, since a drift plan runs with `-lock=false`
  precisely so it contends with nothing (*Serialized Terraform Runs*). Verify by reading
  the run, and record whether the shared heartbeat behaved as `docs/deferred-work.md`
  assumes it does.

  **Result (2026-09-10).** The operator confirmed staging's server and volume in the
  staging Hetzner project, and prod unchanged. The sweep was **dispatched rather
  than waited for**, so the observation is this change's own rather than tomorrow
  morning's: run 34464225639, `workflow_dispatch`, green.

  It is the two-environment exercise design.md Decision 9 names, and it did what
  that decision predicted: **two plan jobs in one run** — `drift (prod)` and
  `drift (staging)` — each authenticating under its own read-only secret, and a
  single `report` job pinging the one shared `infrastructure-drift` heartbeat.
  Staging reported `No changes. Your infrastructure matches the configuration`, so
  the apply and the committed configuration agree, which is the drift sweep
  confirming the apply rather than merely running. No concurrency group was
  involved, as `drift.yml` declares none — the correction the plan review caught.

  `docs/deferred-work.md`'s "Whether the drift heartbeat stays one check" now has
  its first real evidence rather than reasoning: one heartbeat covered two
  environments, and neither trigger that would force a split has fired.

  A note for whoever reads the heartbeat's silence timer: this dispatch reset it,
  as the 2026-09-10 06:00 UTC dispatch did before it.
- [x] 5.5 Archive the change: bring the branch back to the freshly fetched trunk, commit
  the specification record, and open its own pull request. In that same commit, fix
  `openspec/specs/iac-state-management/spec.md`'s `## Purpose`, which describes "the
  dedicated Hetzner Cloud project for the prod environment" and survives the rename
  untouched — a delta rewrites requirements, not the capability's Purpose. Verify by
  reading the archived capability's Purpose against its requirements.

  **Result (2026-09-10).** Branch rebased onto the freshly fetched trunk after
  PR #125 merged, the record archived, and the capability Purpose corrected in the
  same commit. The branch and its working tree are removed after this record's own
  pull request merges — recorded here in prose because a task for them can never be
  ticked in the file that contains them.

  Two operator actions taken during this change live outside the repository and are
  recorded here because nothing else holds them: the `infrastructure-staging`
  workspace's `terraform-version` was set to `1.9.8` (from HCP's creation default of
  `1.16.2`), and an empty state version was pushed to it before the first successful
  apply. Both are disclosed in task 5.3 as unnecessary — neither was the cause of
  the failures, and neither is a step the runbook now prescribes. The branch and working tree are
  removed afterwards, from the repository's main working tree — recorded here in prose
  because a task for them can never be ticked in the file that contains them.
