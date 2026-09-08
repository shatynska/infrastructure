## Why

The weekly `pre-commit autoupdate` workflow has not opened a pull request since it
was written. Its last three scheduled runs — 2026-08-24, 2026-08-31 and
2026-09-07 — each pushed the update branch and then failed on the final step with
`GitHub Actions is not permitted to create or approve pull requests`, because this
repository has `can_approve_pull_request_reviews: false`. The bump those runs
produced (`pre-commit-terraform` v1.109.0 to v1.109.1) is sitting on
`origin/chore/pre-commit-autoupdate` with no pull request and no way to reach
`main`. The `Automated Dependency Updates` requirement in
`openspec/specs/iac-safety-hardening/spec.md` is the only mechanism this
repository has for refreshing pinned hook revisions — Dependabot has no
`pre-commit` ecosystem — so while this is broken, those pins rot with no signal
other than a red workflow nobody is required to look at.

The obvious repair is to enable the repository setting the error names, and it is
the wrong one. A pull request created with the workflow's default `GITHUB_TOKEN`
does not trigger workflow runs. This repository's required status checks —
`validate` from `pr-validation.yml` and `ansible-verify` from
`ansible-verify.yml` — fire only `on: pull_request`, so neither would ever report
on such a pull request. It would open and then sit permanently pending and
unmergeable: a loud weekly failure traded for a silent one, and precisely the
defect the `Required Status Checks Report on Every Pull Request` requirement in
`iac-cicd-pipeline` exists to forbid, reached by a route that requirement does not
currently name.

## What Changes

- The autoupdate workflow mints a short-lived GitHub App installation token with
  `actions/create-github-app-token`, from new `APP_CLIENT_ID` and
  `APP_PRIVATE_KEY` repository secrets, and passes it to
  `peter-evans/create-pull-request` as `token:`. The minting step down-scopes
  each token it issues to Contents and Pull requests, so the credential's bound
  is committed content rather than a claim about a settings page. The pull request is then authored by the App rather than by
  `GITHUB_TOKEN`, so `validate` and `ansible-verify` run on it and it is
  mergeable.
- The workflow's `pull-requests: write` job permission becomes unnecessary for
  opening the pull request — the App token carries that authority — and
  `contents: write` likewise. The job's `GITHUB_TOKEN` is reduced to `contents:
  read`, so the default token no longer holds write authority it does not use.
- `.github/tests/test_ci_configuration.py` gains assertions that the autoupdate
  workflow's pull-request step is given an explicit non-default token and that
  the token-minting step precedes it. This is a static read of a committed file,
  and it is the only thing that can catch a future edit silently reverting to
  `GITHUB_TOKEN` — the symptom would be a pull request that opens and never
  becomes mergeable, weeks after the edit.
- The `Automated Dependency Updates` requirement records the identity constraint
  and why a scheduled-expiry credential is not acceptable for it.
- The README runbook records that the App exists, what it is scoped to, which
  secrets hold it, and how its key is rotated. Without this, the repository
  acquires a long-lived credential whose only description lives in a change that
  is about to be archived.

Two things this change does **not** do:

- It does not enable `can_approve_pull_request_reviews`. That setting stays off;
  the App token is what opens the pull request.
- It does not fix change-queue entry 6's first bullet — this same workflow
  installing `pre-commit` unpinned via `pip install pre-commit` rather than from
  `.github/requirements-ci.txt`. That is a different concern in the same file and
  stays queued.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-safety-hardening`: `Automated Dependency Updates` gains the constraint that
  **any** workflow in this repository that opens a pull request SHALL open it with
  an identity whose events start workflow runs; that the credential behind that
  identity SHALL be scoped to this repository and no wider than the authority its
  pull-request step exercises, SHALL NOT expire on a schedule, and SHALL be
  documented in the README runbook; and that what is committed SHALL be
  statically verifiable, including that an explicit `permissions:` declaration is
  present rather than merely absent.

  The constraint is written over every such workflow rather than over the
  hook-update one alone because nothing about it is specific to hook revisions,
  and today there is exactly one workflow it binds — so stating it generally
  costs nothing and closes the case of a second one written later.

## Impact

- `.github/workflows/pre-commit-autoupdate.yml` — a new token-minting step, a
  `token:` input on the pull-request step, narrowed job permissions.
- `.github/tests/test_ci_configuration.py` — new static assertions.
- `README.md` — the runbook passage naming the App, its scope and its rotation
  procedure. This is not incidental: the delta's "documented where it can be
  found" clause is discharged here and nowhere else.
- `docs/change-queue.md` — entry 32, the unaddressed signal gap this change
  names as a non-goal.
- `docs/deferred-work.md` — the shape assumptions in the new tests, and the two
  properties of the workflow header that are enforced by reading rather than by
  the suite.
- **Operator steps outside the repository, which the change cannot perform for
  itself**: create a GitHub App named `infrastructure-autoupdate`, install it on
  `shatynska/infrastructure` with Contents: Read and write and Pull requests:
  Read and write, and add its Client ID and private key as the `APP_CLIENT_ID`
  and `APP_PRIVATE_KEY` repository secrets. The name is not cosmetic — the README
  names it so a later reader can find the App whose key they are being told to
  rotate. Until the secrets exist the workflow fails at the minting step rather
  than at the pull-request step — a different error, not a fixed one.
- `origin/chore/pre-commit-autoupdate` is left in place. It is the branch the
  workflow reuses by name; once this change is on `main`, a `workflow_dispatch`
  run updates that branch and opens its pull request, and merging it deletes the
  branch (`delete_branch_on_merge` is on).
