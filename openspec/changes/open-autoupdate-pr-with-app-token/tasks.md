## 1. Tests derived from the delta specs

- [ ] 1.1 Add static assertions to `.github/tests/test_ci_configuration.py` for the four new statically-checkable scenarios — that no committed workflow step opening a pull request relies on the default token (an explicit `token:` that is neither `secrets.GITHUB_TOKEN` nor `github.token`), that a step producing that token appears earlier in the same job, that an explicit `permissions:` declaration is in force for that job, and that it grants no write the separate identity performs instead — writing them over **every** workflow that opens a pull request rather than over `pre-commit-autoupdate.yml` by name, per the delta's generalised subject; verify they FAIL against the unmodified workflow by running `python3 -m unittest discover --start-directory .github/tests` from the repository root

## 2. The workflow

- [ ] 2.1 Add an `actions/create-github-app-token@v3` step to `.github/workflows/pre-commit-autoupdate.yml`, before the pull-request step, reading `APP_ID` and `APP_PRIVATE_KEY` from repository secrets, and verify `python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" .github/workflows/pre-commit-autoupdate.yml` parses (`actionlint` is not installed in this repository — see change-queue entry 6, third bullet)
- [ ] 2.2 Pass that step's token output to `peter-evans/create-pull-request` as `token:`, leaving `branch-token` defaulted per design Decision 3, and verify the step's remaining inputs are still only `commit-message`, `title`, `body`, `branch` and `delete-branch` — design Decision 2 records that the App's two permissions suffice for exactly that set, and an added `labels`, `assignees` or `team-reviewers` would invalidate it
- [ ] 2.3 Delete the job-level `permissions:` block so the workflow-level `contents: read` is what the job's `GITHUB_TOKEN` gets, and verify a workflow-level `permissions:` declaration is still present — deleting both would satisfy a naive reading of the scenario while being the opposite of what it requires
- [ ] 2.4 Update the workflow's header comment to say what opens the pull request and why it is not `GITHUB_TOKEN`, and verify the comment names no fact the file does not itself carry
- [ ] 2.5 Verify the tests from 1.1 now PASS, by running `python3 -m unittest discover --start-directory .github/tests` from the repository root

## 3. The durable record

- [ ] 3.1 Record in the README runbook that a GitHub App opens the hook-update pull request, that it is installed on this repository only with Contents and Pull requests write, that `APP_ID` and `APP_PRIVATE_KEY` hold it, and that rotation means generating a new private key on the App and replacing `APP_PRIVATE_KEY` without recreating or reinstalling the App; verify the README states all four, since after archiving this is the only place any of them lives
- [ ] 3.2 Add a `docs/change-queue.md` entry for alerting on a scheduled workflow that goes red — the gap that let this defect survive three runs, which covers `drift.yml` and the host prune too and is named a non-goal in `design.md` — and verify the entry says why it was not folded in

## 4. Verification of the whole tree

- [ ] 4.1 Provision the working tree per the README's Local setup, then run the full `.github/tests` suite and `pre-commit run --all-files`, and report any failure as pre-existing or introduced rather than reporting the run as green

## 5. Operator steps outside the repository

These cannot be performed from the repository and are the precondition for
`ship`'s confirm gate. They are the operator's, not the implementer's.

- [ ] 5.1 Create a GitHub App owned by `shatynska`, with repository permissions Contents: Read and write and Pull requests: Read and write, and no account permissions, and verify the App's settings page shows exactly those two
- [ ] 5.2 Install the App on `shatynska/infrastructure` only, and verify the installation page lists that single repository
- [ ] 5.3 Generate a private key for the App and add `APP_ID` and `APP_PRIVATE_KEY` as repository secrets, and verify `gh secret list` names both
- [ ] 5.4 Verify `gh api repos/shatynska/infrastructure/actions/permissions/workflow` still reports `can_approve_pull_request_reviews: false` — this change does not need it and it stays off

## 6. Confirming the effect

- [ ] 6.1 After this change is merged to `main` and 5.1–5.3 are done, trigger the workflow with `gh workflow run pre-commit-autoupdate.yml` and verify the run concludes successfully
- [ ] 6.2 Verify a pull request now exists from `chore/pre-commit-autoupdate`, that its author is the App rather than `github-actions[bot]`, and that both `validate` and `ansible-verify` have reported a conclusion on it — the pending-forever failure mode this change exists to prevent would show as those checks never appearing
- [ ] 6.3 Verify that pull request is **mergeable** — `gh pr view --json mergeable,mergeStateStatus` reporting a state that is not blocked on an unreported check. This is the observation that confirms the change. Whether the bumped hook revision itself passes CI is a property of that bump, not of this change: a red `validate` on it is a real result to act on, and does not mean this change failed or needs re-entering at `build`
