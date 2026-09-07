## Why

Source files across this repository cite OpenSpec changes by their pre-archive
path — `openspec/changes/<name>/design.md`. Archiving moves the change to
`openspec/changes/archive/<YYYY-MM-DD>-<name>/`, so **every such citation breaks
at the moment its change succeeds**. As of 2026-09-07, 44 live source files
carry 75 citations of that form, and since `openspec/changes/` now holds only
`archive/`, all 75 are broken.

This is not gradual decay that a periodic sweep fixes. It is a step function,
one per archived change, and the author is structurally incapable of catching
it: `fix-volume-discovery-and-consistency` wrote ~13 such citations into its own
new files, which were correct when written, correct across three review rounds,
correct when merged — and wrong an hour later when the archive pull request
landed. Nor can an author pre-write the correct path: the archive directory
carries the archive date, which does not exist until archiving happens.

It has been swept before. `sweep-stale-terraform-paths` (archived 2026-08-19)
did the mechanical work and left the rule underneath unchanged; it fully
re-accumulated in three weeks. Any policy resting on an author or a reviewer
remembering is doomed for the same reason. The viable shapes are mechanical or
prohibitive, and the prohibition needs a test.

## What Changes

- **A citation rule, split by what is being cited.** A citation of a
  *requirement* names the main spec — `openspec/specs/<capability>/spec.md` —
  plus the requirement's own name. Archiving merges a change's delta into that
  file, so the path is permanent, clickable, and shows the requirement as it
  stands now rather than as one change once proposed it. A citation of
  *rationale or history* — `design.md`, `proposal.md`, `test-plan.md`,
  `test-manifest.md`, all of which live only inside a change — names the change
  and the artifact in prose, with no path to break.
- **The rule is written into `AGENTS.md`**, under the project conventions, not
  into this change's `design.md`. A rule kept in a change's design is archived
  with that change and stops being read — which is part of why the previous
  sweep did not stick.
- **The whole repository is swept onto that form**: 75 citations across 44 live
  source files. This folds in `docs/change-queue.md` entry 2
  (`sweep-stale-openspec-references`), which was blocked on this decision and
  cannot land separately, because the enforcing test cannot go green while the
  old form remains.
- **An executable test forbids the old form**, added to
  `.github/tests/test_ci_configuration.py` — the repository's only mechanism
  that statically reads committed files at repository scope, and the lever that
  made image pinning and Molecule digest pinning stick. It fails the required
  status check on any pull request that reintroduces the
  `openspec/changes/<name>` form in live source, whether or not a further path
  component follows the change's name — 27 of the 75 citations name the change
  and stop there.
- **`docs/change-queue.md` entries 1 and 2 are deleted** when this change is
  archived; entry 3 (`separate-history-from-rationale-in-source-comments`) is
  unblocked and stays queued.

Two comment blocks are load-bearing and must survive the sweep intact: the
`POLARITY` note in `ansible/roles/tailscale/tasks/main.yml` and the GHCR
tolerated/not-tolerated block in `ansible/roles/deploy_user/tasks/main.yml`.

**Not** in scope: rewriting comments that mix history with rationale — that is
entry 3, deliberately separate, and this change touches the same blocks only to
change a citation's form.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-repo-foundations`: ADDED requirement *Source Files Cite Specifications by
  Path and Changes by Name* — the citation form live source files use for the
  repository's own change records, and the requirement that a violation fails
  the required status check.

## Impact

- `AGENTS.md` — a new subsection under project conventions carrying the rule.
- `.github/tests/test_ci_configuration.py` — a new test class enumerating live
  source files and asserting none carries the pre-archive citation form. The
  suite's existing constraints hold: standard library only, no network call, no
  credential, no container runtime, no Terraform binary, and no `subprocess`
  outside `bash`/`sh` — so file enumeration is a filesystem walk, not
  `git ls-files`.
- 44 live source files, comments only, no behavioural change: 39 under
  `ansible/` (role `README.md`s, `tasks/`, `defaults/`, `meta/`, Molecule
  scenario files, `requirements-test.txt`, `playbooks/host-baseline.yml`), 2
  under `platform/`, 2 under `.github/`, and `README.md`.
- `docs/change-queue.md` — entries 1 and 2 removed at archive time.
- No Terraform, no Ansible task logic, no workflow behaviour, and no deployed
  artifact changes. The Molecule suite and the platform stack are untouched
  except for comment text.
