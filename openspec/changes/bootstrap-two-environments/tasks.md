## 0. A note on what this task list may contain

Branch and working-tree removal happen after this change's record has merged, which is
after the commit that writes this file — a task for them would be unticked by
construction forever. They are recorded in prose in the archive group instead
(`AGENTS.md`, "Task lists, archived records, and disclosing what was not done").

This change edits two documents and no mechanism. Its verification is therefore the
static suite, `openspec validate`, and a reading of the result against the repository
as it actually is — the failure mode for a runbook is a step that cannot be followed,
which no test in this repository can detect.

## 1. Establish what the document may claim

- [ ] 1.1 Re-read the three single-environment mechanisms against the tree and record
  their exact locations in this change's own notes, rather than trusting design.md's
  copy: `hosts:` in `ansible/playbooks/host-baseline.yml`, the single `HCLOUD_TOKEN`
  in `ansible/inventory/hcloud.yml`, and the literal `environment:` and single
  `PLATFORM_DEPLOY_HOST` in `.github/workflows/platform-deploy.yml`. Verify each by
  reading the file, and note the line numbers current at this commit.
- [ ] 1.2 Confirm what the pipeline genuinely does at two environments by reading the
  runs `add-a-staging-environment` produced — discovery emitting two entries, the
  affected-environment narrowing, one plan comment for a single-environment change,
  an ungated apply, and a drift sweep planning both. The document states these as
  observed fact.

  **The carve-out, because task 2.8 needs it:** three paths were recorded there as
  still unexercised — two plan comments on one pull request, two apply jobs in one
  run, and one of two applies pausing while the other proceeds. Stage 4 must
  describe the last two, since the bootstrap merge affects both environments and
  that is exactly what the reader will meet. It may state them as **what the
  pipeline is specified to do**, citing *Gated Production Apply Applies the
  Reviewed Plan* (`openspec/specs/iac-cicd-pipeline/spec.md`), and SHALL say they
  have not yet been observed together. What it may not do is report them as
  observed behaviour.
- [ ] 1.3 Establish what a first push to a new repository actually does, by reading
  `.github/workflows/apply.yml`'s changed-path step rather than the runbook's account
  of it. Verify the fail-closed condition on an unresolvable `github.event.before`,
  and that a branch's first push meets it — design.md Decision 7 rests on this, and
  the document's current stage 4.2 contradicts it.

## 2. Stages 0 to 4, rewritten for two environments

- [ ] 2.1 Stage 0: the document's "What you will have at the end" list — the four
  bullets at the top, before stage 0.1's accounts table — says **two servers, running
  permanently**, and what that costs monthly and in attention. Its items 2 to 4 (the
  host configured by Ansible, the platform stack, the application deploy path) SHALL
  be qualified as true of **one** of them, since that is what stages 5 to 9 deliver;
  leaving them unqualified is the inference design.md Decision 6 forbids. Verify the
  cost statement appears before any account is created.
- [ ] 2.1a Delete the block at stage 3's close beginning "**Adding a *second*
  environment is out of this document's scope.**" — the sentence this change exists
  to falsify. Its cost paragraph moves to stage 0 (task 2.1) and its queue pointers to
  stage 5 (task 3.1); nothing of it stays where it is. Verify by grepping the result
  for "out of this document's scope" and for the duplicated cost wording.
- [ ] 2.1b Stage 0.2 and 0.3: the tools table and the SSH-key table. **0.3 carries a
  contradiction this change must settle rather than inherit**: it says "Never reuse
  one key for two purposes", while `terraform/environments/prod/terraform.tfvars` and
  `terraform/environments/staging/terraform.tfvars` carry a byte-identical
  `ssh_public_key`. State that one operator key serves both hosts and why — the key
  authorises `root` on hosts this repository can recreate entirely, and a second
  private half would be a second thing to hold for no gain — or state that they
  differ and where the second goes. A reader left with the rule as written generates
  a second key and finds nothing that tells them where to put it. Verify against both
  committed `tfvars`.
- [ ] 2.2 Stage 1: two Hetzner projects and four tokens. Present one-project-or-two as
  a decision with its two consequences (the ungated apply, and the volume-name and
  mount-path coupling), recommend two, and state that the pipeline supports either.
  Verify against design.md Decision 3.
- [ ] 2.3 Stage 1.3: the sizing table gains a second column of values, prod first,
  with the lower environment's row stating the deliberate tightness and what it forces.
  Verify the values match `terraform/environments/*/terraform.tfvars` as committed.
- [ ] 2.4 Stage 2: two HCP workspaces, `infrastructure-<environment>`, both CLI-driven,
  both set to **Local** execution mode, one **user** token for both. Verify the
  execution-mode warning and the user-token requirement each appear once and are not
  weakened by being said twice.
- [ ] 2.5 Stage 3: two GitHub Environments and the full secret set for both, including
  the distinctness obligations the pipeline enforces (both read-only secret names, both
  Environment names) and what discovery does when they collide. Verify the `gh` commands
  read secrets from stdin rather than `--body`, which records the value in shell history.
- [ ] 2.6 Stage 3: the reviewer asymmetry — `production` requires one, the lower
  environment does not, and why that is safe only because of the project boundary from
  2.2. Verify it states that neither is verifiable from any file in the repository.
- [ ] 2.7 Stage 3: the Dependabot entry obligation for both environment directories,
  which the CI suite already enforces by comparing that list against the tree. Verify by
  reading `.github/dependabot.yml` as committed.
- [ ] 2.7a Stage 3.1: the template edits, which double. Step 3's "ones that matter"
  list SHALL name **both** environments' `versions.tf` — the second one carries the
  template author's HCP `organization` exactly as prod's does, and a reader who
  changes only prod's has a second environment initialising against someone else's
  organisation. Step 4's `tfvars` edit and `ssh_public_key` are performed twice. The
  second environment's `pipeline.yml` is read and accepted or changed, rather than
  inherited unseen — its `github_environment`, `read_only_secret` and
  `destroy_policy_gate: false` are the three values stage 3.2 and 3.3 then have to
  match. Step 5's `moved`-block deletion stays prod-only, which the second
  environment's `ssh_key.tf` already explains. Verify each against the committed tree.
- [ ] 2.7b Stage 3.1 and stage 4.2: the push sequence that actually applies
  (design.md Decision 7). The repository is created with an initial commit — **a
  license, not a README**, since the template carries a root `README.md` and a
  `.gitignore` that would each collide, and no root `LICENSE` — and the local clone
  reconciles onto it before pushing: `--allow-unrelated-histories` merge for the
  keep-history variant, rebase for the clean-history one. **State where each
  reconciliation lands**: the merge at stage 3.1, as soon as the remote is
  repointed, since that clone already has commits; the rebase at stage 4.2
  immediately before the push, because the clean-history variant has no commit until
  stage 4.2 creates it and a rebase on an unborn branch fails outright. Fix that
  variant's mechanics while there: `remote set-url` has no remote to set after a
  fresh `init`, and the branch must be named `main` at init or the push's refspec
  fails. While rewriting stage 4.2's opening, correct its claim that three workflows
  start on that push: `pr-validation.yml` is `on: pull_request` only, so PR
  Validation does not. State that a force-push over the initial commit is **not** a
  shortcut, citing the second fail-closed condition in the same step. Keep the
  workflow's error text beside the step for a reader who skips the checkbox. Verify
  every claim against `.github/workflows/apply.yml` as read in task 1.3.
- [ ] 2.7c **Keep** stage 3.1's closing warning that the push must find its secrets in
  place, and state why it is true under the reconciled sequence: the content push has
  a resolvable base, so it plans, so the secrets must already exist — where the
  document's current text implies the opposite reason. What is corrected is any
  sentence treating the stage 4.2 push as the repository's first commit. Verify by
  reading stage 3.1's close and stage 4.2 together: they must describe one sequence,
  not two.
- [ ] 2.8 Stage 4: one apply run covering two environments — prod waiting for its
  reviewer, the lower environment applying immediately, and neither environment's
  failure withholding the other's apply. Verify against
  `openspec/specs/iac-cicd-pipeline/spec.md`'s *Gated Production Apply Applies the
  Reviewed Plan*, whose scenarios say exactly this.
- [ ] 2.9 Stage 4: the local `plan` step and the `.envrc` guidance become
  per-environment, since one token reaches one project and the wrong one in scope is
  silent. Verify it matches the README's Local setup, which already says this.

- [ ] 2.10 Stage 4.3 and 4.4: two addresses, one destination. `terraform output` runs
  per environment and yields two `server_ipv4_address` values. Only the configured
  host needs its fingerprint in `known_hosts`, since only it is converged in stage 6.
  **DNS records point at the configured host**, and the document says why aiming one
  at the second is worse than useless: that host ships with `web_allowed_cidrs = []`,
  so nothing answers on 80/443 and the hostname times out while its certificate never
  issues, with no error naming the cause. Verify against both committed `tfvars` and
  against the second environment's `pipeline.yml`.
- [ ] 2.11 Sweep every stage's **"Secrets created in this stage"** and **"Check"**
  blocks, the intro's **"Time"** estimate, **the document's opening paragraph** —
  which still calls itself the procedure for standing up "a new server" and names
  itself the document to start from "when the host has to be rebuilt", where
  Appendix B now covers the configured host only (task 3.5) — and **stage 0.1's
  accounts table**, whose Hetzner row reads "The server, firewall, volume, backups"
  in the singular. These are the lists a reader uses to
  decide a stage is done, and they still count one project, one workspace and four
  secrets — stage 3's Check says "four secrets set; `production` shows one required
  reviewer" where the answer is now seven and two. Bounded the way task 3.5 bounds
  Appendix B: correct the counts and say which host a check covers; do not rewrite a
  stage's procedure here. Verify each Check against the stage it closes.

## 3. The limits, stated where the reader meets them

- [ ] 3.1 Open stage 5 with what the second host cannot have yet: no Ansible run can
  target it, the dynamic inventory sees one project per token, and the platform stack
  has no per-environment deploy path. Name the queue entry for each. Verify a reader
  arriving with two running servers learns this before performing any step of stage 5.
- [ ] 3.2 State what the second host therefore *is* at the end of the document — a
  provisioned, reachable, unconfigured server with an attached unmounted volume — and
  that dropping it is deleting a directory and two secrets. Verify design.md Decision
  2's "worse than one that stops" argument is honoured: no step is written for the
  second host that cannot be followed.
- [ ] 3.3 Appendix A: the secret inventory covers both environments, with each row
  saying which environment's value it holds. Verify every secret named in stages 1 to 4
  appears, and that the two read-only Hetzner secrets are distinguishable.
- [ ] 3.4 Appendix C: fold the two-environment material into the company notes,
  naming the sentences actually changed rather than a claim about a
  single-environment copy of this shape, which the appendix does not make. Its
  heartbeat-check-names paragraph SHALL be **preserved**: it is cited from inside the
  tree by the second environment's `terraform.tfvars`, where the server name records
  why the two hosts must not share one. Verify no sentence in the appendix
  contradicts stages 0 to 4, and that the citation still resolves.
- [ ] 3.5 Appendix B (rebuilding an existing host): state which host it covers. After
  this rewrite it silently says "the host" in a document about two, and the rebuild it
  describes is the configured one. Verify one sentence is enough — this task does not
  license rewriting the appendix for two hosts, which would describe a rebuild of a
  host nothing configures.

## 4. The work this change does not do

- [ ] 4.1 Add a `docs/change-queue.md` entry for making `platform-deploy.yml`
  environment-agnostic: the literal `environment: production`, the single
  `PLATFORM_DEPLOY_HOST`, and the per-environment `PLATFORM_*` secret set it implies.
  **Read entry 50 in full first**, rather than grepping for the workflow's name: its
  platform bullet already carries the stack onto the second host without naming the
  workflow, so the two overlap. Verify the outcome is either one entry cross-
  referencing the other or a single extended entry — not two entries describing the
  same work in different words.
- [ ] 4.2 Verify entry 50 already covers the two Ansible mechanisms, and extend it only
  if it does not. It gained the inventory problem during `add-a-staging-environment`;
  the `hosts:` parameter it has carried since it was written.

## 5. Verification

- [ ] 5.1 Run `python3 -m unittest discover --start-directory .github/tests` from the
  repository root and confirm it passes. This change declares no deltas and owes no new
  tests (`AGENTS.md`, "A change declaring no specification deltas owes no new tests,
  only that the suite stays green"), but the suite reads committed files repository-wide
  and a docs edit can break a citation-form assertion.
- [ ] 5.2 Run `openspec validate --all` and `openspec validate --archived`, and confirm
  `.openspec.yaml` carries `skip_specs: true` alongside `schema:` and `created:` —
  without the schema line the change fails to resolve and the error reads as though the
  setting did not work.
- [ ] 5.3 Read the rewritten stages 0 to 4 against the repository as committed,
  checking every command, secret name, file path and workspace name resolves. The
  failure mode here is a step that cannot be followed, and no check in this repository
  detects one. **Resolving names is not sufficient**: the stage 4 defect this change
  fixes was a step whose every name resolved and whose behaviour the workflow refuses,
  so verify each behavioural claim in stages 3 and 4 against
  `.github/workflows/apply.yml` and `pr-validation.yml` themselves — what triggers,
  what the path filter selects, what fails closed.

## 6. Review and ship

- [ ] 6.1 Dispatch `ai-toolkit:change-code-reviewer` over the diff once 5.1–5.3 pass,
  and record the round and its findings here.
- [ ] 6.2 Open the pull request, let continuous integration run, and wait for the
  operator's confirmation that it merged.
- [ ] 6.3 Confirm the effect: the operator reads stages 0 to 4 and confirms they
  describe standing up two servers, with no step that cannot be followed and no claim
  that the second host can be configured today. **This is the only confirmation
  available** — the document's real test is the company setup, which has not happened,
  so this gate is a reading rather than an observation and says so.
- [ ] 6.4 Archive the change: bring the branch back to the freshly fetched trunk, commit
  the record, and open its own pull request. The branch and working tree are removed
  afterwards, from the repository's main working tree — in prose here, because a task
  for them can never be ticked in the file that contains them.
