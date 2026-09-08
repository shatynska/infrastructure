## Context

See `proposal.md` — Why, for the failure and why enabling the repository setting
the error names is not the fix.

Four properties of the current repository shape everything below:

- Workflow-level `permissions:` in `pre-commit-autoupdate.yml` is `contents: read`;
  the single job overrides it with `contents: write` and `pull-requests: write`,
  both of which exist only so `peter-evans/create-pull-request` can push the branch
  and open the pull request with `GITHUB_TOKEN`.
- `main`'s required status checks are `validate` and `ansible-verify`, and both are
  `on: pull_request` only. There is no `push`-triggered route by which either
  reports.
- Branch protection is `strict: true` — a branch must be current with `main` before
  it merges — and `delete_branch_on_merge` is on.
- Actions are pinned by major tag (`actions/checkout@v7`,
  `peter-evans/create-pull-request@v8`), and the `github-actions` Dependabot
  ecosystem keeps those moving.

## Goals / Non-Goals

**Goals:**

- The autoupdate pull request opens *and* is mergeable, without a human step.
- Whatever holds the identity cannot expire on a date nobody picked.
- The part of this that lives in the repository is statically checkable, so a
  future edit cannot quietly return to `GITHUB_TOKEN`.

**Non-Goals:**

- Auto-merging the resulting pull request. It stays a reviewed pull request like
  any other; the required checks are the point of this change, not an obstacle to
  route around.
- Making the *existence* of the secrets verifiable from the tree. It is not, and
  the design accepts that rather than pretending otherwise.
- Changing anything about how Dependabot's own pull requests are opened. Dependabot
  is special-cased by GitHub and triggers workflows already; it is not affected.
- Alerting on a scheduled workflow that goes red. This change removes one cause of a
  silently-ignored red run and adds none, but the underlying gap — that nothing in
  this repository notices a failing weekly workflow, which is why the present defect
  survived three runs — is a separate concern with a separate blast radius, and it
  covers `drift.yml` and the host prune as much as this workflow. It is recorded in
  `docs/change-queue.md` rather than folded in.

## Decisions

### 1. A GitHub App installation token, not a fine-grained PAT

Both fix the immediate error and both trigger workflows. They differ on one axis
that matters more than convenience here: a fine-grained PAT carries a mandatory
expiry (one year at most).

The argument against that is **not** that expiry fails silently — it does not. An
expired token fails the pull-request step with a 401, which is red, and GitHub
emails expiry warnings besides. The argument is about who chose the date and how
often it recurs. Creating the App is a one-time step this change's own ship gate
bounds: it either happened or the automation never worked, and either way the
question is closed within this change's life. An expiry is unbounded — it returns
indefinitely, on a date set by the credential's form rather than by anyone, long
after this change is archived and at a moment when nobody is watching for it.
Failure scenario 2 below is the honest statement of what that costs: this
repository has already demonstrated that it takes about three weeks to notice a
red weekly run.

A GitHub App's private key does not expire. The token minted from it lives about an
hour and is discarded, so the durable secret is one that will not lapse and the
in-flight credential is short-lived. That is the better half of both.

The cost is real and accepted: creating and installing an App is more setup than
pasting a PAT, and the App is a second thing to remember when auditing access.

**Rejected: enabling `can_approve_pull_request_reviews`.** It removes the error and
replaces it with a pull request that never becomes mergeable. See `proposal.md`.

**Rejected: dropping pull-request creation and only reporting staleness.** The
`Automated Dependency Updates` requirement mandates that the workflow open a pull
request; this would need a spec delta weakening the only hook-pin mechanism the
repository has, in a change whose purpose is to repair it.

### 2. Mint the token in the workflow, with `actions/create-github-app-token@v3`

The action's current major is v3. It is first-party (`actions/`), which keeps the
credential path out of a third party, and Dependabot's `github-actions` ecosystem
will carry it forward like every other pin.

The minting step must come before the pull-request step, and its output is passed
as that step's `token:` input.

Two inputs are chosen deliberately.

**`client-id`, not `app-id`.** v3 marks `app-id` deprecated (`deprecationMessage: "Use
'client-id' instead."`); it still resolves, but annotates every run and is a plausible
removal in a future major that Dependabot will propose. The secret is named
`APP_CLIENT_ID` to match. This costs nothing today precisely because the secrets do not
exist yet — deferring it would mean renaming a live secret later, and a rename that goes
half-done fails this workflow in the way the change exists to end.

**`permission-contents: write` and `permission-pull-requests: write`.** The requirement
says the credential carries no authority beyond what the pull-request step exercises,
and without these that is a claim about the App's settings page — invisible from the
tree and silently falsified if the App is ever widened. Declaring them puts the token's
scope in committed content: an installation token cannot exceed what the App holds, so
if the App is later narrowed minting fails with a 422 rather than degrading, and if the
App is later widened the token does not follow. This is the same instinct as Decision 5
— prefer the assertion that lives in the repository over the one that lives in a setting.

The permission set was checked against what the step actually uses rather than assumed.
`create-pull-request`'s inputs here are `commit-message`, `title`, `body`, `branch` and
`delete-branch` — none needing authority beyond pushing a branch and opening a pull
request. Had the step used `labels` or `assignees` it would additionally need Issues, and
`team-reviewers` an organisation permission that does not exist to grant here — the
App is user-owned on a personal repository, so that input is unavailable rather
than withheld. Individual `reviewers`
would in fact work, being a pull-request operation; the bound is real but it is not
"any reviewer input", and stating it too broadly would be its own small falsehood.

### 3. One token for both the branch push and the pull request

`create-pull-request` has a separate `branch-token`, defaulting to `token`. Leave it
defaulted. Splitting them — App token for the pull request, `GITHUB_TOKEN` for the
branch — would open the pull request correctly but make every later push to that
branch a `GITHUB_TOKEN` push, which produces no `synchronize` event and so no
re-run of the required checks. That is the same defect on the update path instead of
the create path, and it is subtler.

### 4. The job's `GITHUB_TOKEN` drops to `contents: read`

Once the App token pushes the branch and opens the pull request, the default token's
only remaining use is `actions/checkout`. Deleting the job-level `permissions:` block
leaves the workflow-level `contents: read` in force. This is not incidental tidying:
the `Least-Privilege Workflow Permissions` requirement in `iac-cicd-pipeline` says
no job SHALL hold `contents: write` unless it needs to push, and after this change
this job does not. A reader would also reasonably infer from those permissions that
`GITHUB_TOKEN` is still what opens the pull request.

### 5. The static check asserts shape, not function

`.github/tests` may not make a network call, so it cannot establish that the secrets
exist, that the App is installed, or that a pull request was opened. What it can
establish is what the committed file says: that the pull-request step receives an
explicit `token:` that is neither `secrets.GITHUB_TOKEN` nor `github.token`, that a
step producing that value appears earlier in the same job, and that the job grants no
write permission to the default token.

One subtlety decides whether that third assertion is worth anything. "The job grants
no write" is trivially true of a workflow that declares no `permissions:` at all — the
weakest possible state would pass a check written to enforce the strongest, and the way
to satisfy it would be to delete the declaration. So the assertion is that an explicit
declaration is **present**, at workflow or job level, and that its effective value for
the job grants no write. An absent declaration falls back to the repository default,
which is a setting rather than repository content and can change without a commit;
that is exactly the class of fact `.github/tests` cannot see and must therefore refuse
to accept.

That is the whole of what a reviewer would otherwise have to notice by eye, and it is
the half that rots — the App, once installed, does not silently change; an edit to the
workflow file silently can. This mirrors how `ansible-verify.yml`'s required-check
shape is asserted: the file is checked for the shape that makes the setting safe, and
the setting itself is left to the branch-protection API.

### 6. `origin/chore/pre-commit-autoupdate` is not touched by this change

The branch is the automation's own, named literally in the workflow's `branch:` input,
and it carries a valid unmerged bump. Once this change is on `main`, one
`workflow_dispatch` run rebases that branch onto `main` and opens its pull request
properly; merging it deletes the branch. Hand-opening a pull request for it now would
land the bump without ever exercising the thing this change is for.

## Risks / Trade-offs

- **The secrets do not exist when the workflow next runs** → the run fails at the
  minting step instead of the pull-request step. This is not worse than today, and it
  is still red. The task list makes creating the App and adding the secrets a
  precondition of the `workflow_dispatch` that confirms the change, so the two do not
  drift apart.
- **The App private key is a long-lived secret held in the repository** → it is scoped
  to this one repository and to Contents and Pull requests only, so its blast radius
  is a branch and a pull request, both of which still face branch protection and the
  required checks. It is rotatable by generating a new key without recreating the App.
- **The App is uninstalled, or its permissions are narrowed, outside the repository** →
  minting or the pull-request step fails loudly. Nothing about this design can be
  broken into silence except by editing the workflow, which is what the static check
  covers. "Loudly" here means a red run in the Actions tab and GitHub's own failure
  email to the workflow file's last committer — which is precisely the signal that did
  not get acted on for three weeks in the failure this change repairs. The design does
  not improve on it and does not claim to; see the corresponding non-goal.
- **`create-github-app-token` gains a new major version** → Dependabot proposes the
  bump as it does for every other action; the pin does not float.
- **The App-authored pull request now triggers `validate` and `ansible-verify` weekly**
  → a small, intended increase in CI minutes. That is the change working.
