## Why

The Molecule suite runs all seven roles whenever a pull request touches anything the scenarios read, and of the last twenty merged pull requests the ones that touched a role touched exactly one. Seven jobs run where between one and four are owed, on a required status check whose degraded runs have taken 75 minutes.

`narrow-the-molecule-trigger-to-what-it-reads` took the safe half of this — the pull requests that touch no role at all — and stopped deliberately at the contested remainder, recording it as `docs/change-queue.md` entry 67. What makes the remainder contested is that scenarios converge sibling roles: a matrix selecting only the role whose files changed would skip `image_prune` and `ops_user` on a pull request editing `docker`, and skip them **silently**, the gate seeing a green matrix over the rows it was handed. Losing coverage with nothing reporting is the one failure this pipeline is built to refuse.

## What Changes

- **The matrix is selected per role**, from the files a pull request changed rather than from the whole of `ansible/`. A diff confined to one role's directory runs that role and the roles whose scenarios converge it.
- **Selection is the reverse closure of a dependency graph derived from scenario text at run time**, not a list committed anywhere. A stored graph is a list that can go stale; a derived one cannot disagree with the scenarios it was derived from.
- **The graph derivation follows four constructions and refuses two more**, because a sweep that reads fewer under-reads the graph and under-running is the silent direction. Followed: a play's `roles:`, `include_role` and `import_role` (bare and fully qualified), `import_playbook`, and a role's own `meta/main.yml` `dependencies`. Refused unless explicitly permitted: any construction in a role's own task or handler file reaching outside that role's directory — keyed on what is reached, since a path-based include names no role and couples the two identically — and a nested `ansible-playbook` naming its playbook by expression. The first is refused as the cheaper remedy, no role in the tree doing it today; the second because the derivation cannot close over where an expression leads, and the tree contains one instance.
- **Anything not attributable to exactly one role selects every role.** The shared inputs — `ansible/requirements.yml`, `ansible/requirements-test.txt`, `ansible/scripts/run-molecule` and `ansible/ansible.cfg` — determine what every scenario runs under, and so does any path under `ansible/` that this mapping does not recognise. A base-image digest is **not** among them: it lives in a scenario's own `molecule.yml`, under its role's directory, and attributes there like any other file that role owns — the obligation that scenarios sharing an image repository agree on its digest is what makes a shared bump touch every role that shares it, rather than any rule here. The polarity is the one `narrow-the-molecule-trigger-to-what-it-reads` established in its own Decision 2: where a list can go stale, the safe direction is to run by default rather than to skip.
- **A role that nothing can test widens too, but only on its own.** `ansible/roles/tailscale/` carries tasks and defaults, no scenarios of its own, and no other role's scenarios converge it. Attribution succeeds, the closure is `{tailscale}`, and restricting that to the roles the run can execute leaves nothing — so a pull request touching only it selects every role rather than none, keeping a legitimate change mergeable. Touched alongside a role that *can* be run, it widens nothing: it is unverifiable either way.
- **The aggregating gate gains a fourth state** — the suite ran, on the subset that was owed — without reopening the hole its third state exists to close. An empty selection on a run that asked for the suite SHALL fail rather than skip.
- **The selector is checked statically** in `.github/tests`, beside `unpermitted_controller_reads`, which already reads scenario text keyed on file, construction and resolved target. The check asserts the derived closure against the scenarios, and asserts that an unattributable path widens to every role rather than narrowing to none.

**Not in scope.** Making any individual job faster; the wall-clock is dominated by upstream archive latency and by one `prepare` task, and this change stops running seven jobs when one is owed rather than making a job cheaper. Nor does it touch the lint tier in `pr-validation.yml`, which is the compensating coverage for everything the suite's filter excludes and is triggered by the whole of `ansible/` without exclusion.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-cicd-pipeline`: *Ansible Configuration Is Verified in Continuous Integration and Gates the Merge* today obliges the run to discover role scenarios rather than enumerate them, and to fail loudly where discovery finds nothing. It says nothing about which discovered roles a given pull request owes. This change adds that obligation, and the refusals that keep a narrowed matrix from becoming a green that verified nothing.

## Impact

- `.github/workflows/ansible-verify.yml` — the `discover` job gains the changed-file list and the selection; the `molecule` matrix is fed the selected subset; the `ansible-verify` gate reads one more input.
- A selector under `ansible/scripts/`, beside `run-molecule`. The location is load-bearing: a path under `ansible/` is itself a trigger under the existing filter, so editing the selector runs the suite, and it is an unattributable path, so it runs every role. A selector under `.github/` would change what the suite selects without the suite running at all.
- `.github/tests/` — a module asserting the derived graph, the closure and the widening polarity, under the same role enumeration the existing checks use, so that the gitignored Galaxy role cannot make the check disagree between a provisioned working tree and continuous integration.
- No change to what any scenario asserts, to any role's behaviour, or to the host.
