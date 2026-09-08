# Design

## Context

A full-repository audit on 2026-09-06 (trunk `245ef59`) found `README.md`
carrying statements that had been overtaken. The change was opened with a
`handoff.md` and no proposal. Two days of trunk moved underneath it before it
was picked up, which is itself evidence for the problem: three of the handoff's
own claims were stale by the time this proposal was written — it said five
workflows (there are six), it said the Molecule section was accurate throughout
(`docs/change-queue.md` entry 9, found the day after, says otherwise), and
every line number in it had shifted.

That is the shape of the defect. `README.md` is not wrong because anyone wrote
something false; every statement in it was true when written. It is wrong
because it states facts that other files own, and nothing connects the two.

So the interesting question in this change is not *what is stale* — the
proposal's table answers that, verified file by file. It is **how to write a
correction that does not become the next audit's table.**

## Decision 1: No specification delta

This change declares none, which is what excuses it from deriving tests under
`AGENTS.md`. That is a claim worth substantiating rather than assuming, because
the exemption is the difference between a one-file change and a four-artifact
one.

Three requirements in `openspec/specs/` bear on this file. The first two were
found by searching for the word "README", which is how the third was nearly
missed — it binds by class rather than by name:

- *Write Credentials Confined to the Gated Pipeline*
  (`openspec/specs/iac-safety-hardening/spec.md`) obliges the prohibition on
  the Read & Write token to be recorded "where it is loaded without being
  sought: the repository README runbook for human operators, and a
  repository-root `AGENTS.md` for coding agents." Satisfied today at
  `README.md:75-77`. This change does not touch those lines, so the
  requirement's state is unchanged.
- *Required Status Checks Report on Every Pull Request*
  (`openspec/specs/iac-cicd-pipeline/spec.md`) mentions a README only as an
  example of a file a pull request might change. Not an obligation on this
  file's content.
- *Source Files Cite Specifications by Path and Changes by Name*
  (`openspec/specs/iac-repo-foundations/spec.md`) binds every committed file
  outside `openspec/`, so it binds this one — by class, without naming it. It
  constrains the *form* of any citation this change writes, not the statements
  being corrected. Honoured in Decision 6 and enforced by task 5.8.

No requirement fixes the content that is stale, so correcting it changes no
requirement. The suite must stay green — see Decision 6 for why that is a real
gate here and not a formality.

**One requirement is nonetheless left disagreeing with the tree, knowingly.**
*Version Control Excludes State and Secrets*
(`openspec/specs/iac-repo-foundations/spec.md`) carries a table row describing
`terraform/environments/prod/terraform.tfvars` as holding "server type, region,
image, labels, allowed CIDRs". The README's sentence is a copy of that row, and
the "labels" entry is wrong in both — the file has none, and the only `labels`
block under `terraform/environments/prod/` is in `ssh_key.tf`.

Correcting the README and not the requirement leaves two documents disagreeing
about one file, which is this change's own defect class. Three ways out:

1. **Leave the README's copy alone** so the two agree. Cheapest, and wrong: a
   truth pass that knowingly preserves a false statement is not one.
2. **Add a `MODIFIED` delta** for that requirement. Honest, and forfeits
   `skip_specs` — the change then owes a derived-test dispatch over a five-word
   parenthetical, and gains the artifact set that goes with a delta.
3. **Correct the README, record the divergence.** Chosen.

What makes 3 defensible rather than convenient is that the parenthetical is
*illustrative*. The requirement's normative content is that the file is
committed and holds non-secret environment configuration; the list after it
gives examples of that class, and labels are non-secret environment
configuration — they are simply set in the module rather than passed through
this file. So the README and the requirement do not end up in normative
conflict, only in a factual disagreement about an example.

There is a third argument, and it is the strongest. A `MODIFIED` delta owes
derived tests. The test it would owe is "the requirement's parenthetical agrees
with `terraform/environments/prod/terraform.tfvars`" — which is exactly the
cross-file, static-read assertion Decision 8 defers as needing a requirement of
its own and a scope decision nobody has made. Taking the delta here would drag
that queued question into a documentation fix and settle it in passing, by
implication, which is the outcome Decision 8 exists to prevent. Option 3 is
therefore principled rather than merely cheap — *provided* the divergence is
tracked, which task 6.2 does.

`docs/change-queue.md` gets the entry, and task 6.4's prohibition on recording
further observations is carved out for it explicitly.

## Decision 2: Where a fact will change again, write what answers it, not the answer

Three of the eleven stale rows are the same failure: the README restated a fact
another file owns, and the two drifted. A fourth — the region — is the same
failure with a worse consequence.

The general shape of the fix is to make the README's copy either **derivable**
or **attributed**, so the next reader can close the gap in one step instead of
discovering it weeks later.

| Row | Correction | Why this form |
|---|---|---|
| "the eight scenarios this repository owns" (twice) | "every scenario this repository owns", plus `git ls-files 'ansible/roles/*/molecule/*/molecule.yml'` | The count changed twice in three weeks. The command cannot be wrong; the number always eventually is. |
| The parenthetical listing which roles carry more than one scenario | the same command | It named two of the four that do. Its purpose was to convince a reader that `-s default` is insufficient — a command that lists twelve scenarios does that better than a list of two roles. |
| Single region `fsn1` | `hel1`, attributed to `terraform/environments/prod/terraform.tfvars` | See Decision 3. |
| `terraform/modules/` "grows past `terraform/modules/server`" | states the tests that exist and where each command finds them | The claim was conditional on a future that arrived — in the very module it names, which carries five test files. |

### Why `git ls-files` and not `find`

The obvious invocation is `find ansible/roles -mindepth 4 -name molecule.yml
-not -path '*geerlingguy.docker*'`, and it is wrong in a way worth recording,
because it was this change's first answer.

`README.md:139-143` warns against globbing `ansible/roles/*/molecule/*/`:
once `ansible-galaxy` has run, that also matches
`ansible/roles/geerlingguy.docker/molecule/default/` — installed content, on a
different image, gitignored, discarded by the next reinstall. The tempting move
is to bake that warning into the command as an exclusion clause.

Doing so **hardcodes into the README the one fact `ansible/requirements.yml`
owns** — which role is installed — and so commits precisely the defect this
decision exists to prevent. `.github/tests/test_ci_configuration.py` makes the
point in the repository's own voice: its `galaxy_role_directories` helper
derives that set from the manifest "rather than from a hardcoded list", raises
rather than falling back to an empty exclusion when the manifest is unreadable,
and a sibling test exists to fail a hardcoded implementation. A README teaching
the form its own suite classifies as defective is worse than a README with a
stale number.

`git ls-files 'ansible/roles/*/molecule/*/molecule.yml'` needs no exclusion at
all. `.gitignore:30` excludes `ansible/roles/geerlingguy.docker/`, so
*committed* and *owned* are the same set by construction — and remain the same
set when a second Galaxy role ships scenarios, which is the case that breaks
the `find` form silently. It is shorter, it has no `-mindepth` to get wrong,
and its one presupposition, a git checkout, is true of anyone editing this
repository.

Two things it does not do, both correct here: it will not list an uncommitted
scenario, which for a digest refresh is the desired behaviour — an uncommitted
scenario is not yet something the repository owns — and it must be run from the
repository root. The README's neighbouring commands `cd` into a role
directory, so the working directory is stated where the command appears.

**Considered and rejected: dropping the counts entirely.** "Put that digest in
every scenario" without any sense of scale reads as a smaller job than twelve
files. The command supplies the scale on demand and never disagrees with the
tree.

### The one enumeration this change adds

The Repository layout section lists three top-level directories. The repository
commits **seven**: `terraform/`, `ansible/`, `platform/`, `.github/`,
`openspec/`, `docs/` and `.claude/`.

Getting that number right took two attempts, and the first is worth recording
because it is the same failure as everything else in this decision. "Five" —
`openspec/` and `docs/` added to the three — is what `ls -d */` reports, and
`ls -d */` silently drops every dotted directory. That omits `.github/`, whose
workflows and `tests/` suite the README discusses at length, and `.claude/`,
whose OpenSpec commands and skills are committed. An enumeration completed
against an unwritten convention is not complete; it is complete-looking, which
is worse. The command that actually answers the question is
`git ls-files | sed 's|/.*||' | sort -u`, and the section states the rule it
lists by.

Adding these is an enumeration, and this decision has just spent several
paragraphs arguing against those. The distinction is that the section already
*is* an enumeration of top-level directories, and an incomplete list is a
weaker artifact than a complete one — completing it introduces no new class of
rot, where adding a list of modules or of workflows to a section that has none
would.

A second leg was drafted here — that top-level directories change on a slower
timescale than scenario counts — and removed, because it did not survive
checking. `git log --diff-filter=A --format=%as` gives 2026-07-25 for
`.claude/`, 2026-08-18 for `.github/` and **2026-09-06 for `docs/`**: two days
before this change. "Stable since August" would have been the fourth unchecked
claim these artifacts produced, in the decision that argues against unchecked
claims.

It was not needed. What makes this enumeration safe is not that it changes
slowly but that one command settles it in both directions, which is the whole
of Decision 2. An enumeration nothing can check is the thing to avoid, however
rarely it moves.

For the same reason `terraform/modules/volume` is **not** added to the modules
bullet. That bullet says "e.g. `terraform/modules/server`" — an example, marked
as one, and correct. Turning it into a list of two would create exactly the
enumeration this section is arguing against, and would have to be edited by
every change that adds a module.

## Decision 3: The region is stated *and* attributed, not one or the other

`fsn1` versus `hel1` is the only row that can send an operator to the wrong
place. Three options:

1. **Update the value.** Restores usefulness, restores nothing else — this is
   exactly the edit that was correct in August.
2. **Drop the region and point at `terraform.tfvars`.** Cannot rot. Costs every
   reader a file open to answer "where does this run", which is a question the
   Non-goals section is already answering in passing.
3. **Both**: name `hel1` and name the file that sets it.

Chosen: 3. It is one clause longer than either alternative and does two things
neither does alone — a reader gets the answer immediately, and an editor
changing the region is told, in the sentence they are editing, what the other
half of the pair is. The `README.md`↔`terraform.tfvars` link is the thing that
was missing; writing it down is the smallest durable fix available without a
check.

Note what this does **not** do. The bullet is a *non-goal*: multi-region
deployment is rejected. The region's identity is incidental to that rejection,
and the correction must not read as softening it. The bullet keeps its shape —
the rejection first, the current region as a subordinate clause.

## Decision 4: The CI/CD section describes workflows, not triggers

Today's section is three bullets — pull requests, merge to `main`, nightly —
and it was accurate when there were three workflows. It is now wrong twice
over: three of six workflows are missing, and the pull-request bullet is an
undifferentiated list of five path-filtered Terraform checks plus `gitleaks`. What it
omits is the CI-configuration suite, the Compose render, `terraform test`,
`ansible-lint` and `ansible-playbook --syntax-check` — and, more importantly,
the distinction between the two checks that run on *every* pull request (the
CI-configuration suite and `gitleaks`) and the rest, which are conditioned on
changed paths. A reader of the current bullet cannot tell that a
documentation-only pull request runs anything at all.

Two shapes were considered.

**Keep the trigger grouping and expand each bullet.** Closest to today's text.
It fails on `ansible-verify.yml`, which is a separate workflow on the same
trigger as `pr-validation.yml` and is a separately registered required context
— the distinction a contributor most needs, and precisely the one a
trigger-grouped list dissolves.

**Group by workflow.** Chosen. One entry per file in `.github/workflows/`, each
naming its trigger and what it does. A reader comparing the section against
`ls .github/workflows/` gets a one-to-one correspondence, which is the same
derivability principle as Decision 2 — the section's completeness becomes
checkable by a command rather than by trust.

The two required contexts are called out, because *which* checks block a merge
is not visible from the workflow list.

## Decision 5: Branch protection keeps its existing hedge

`README.md:101-107` already says the `ansible-verify` job is the registered
context and then immediately says that whether it *is* registered is a
repository setting, pointing at
`gh api repos/:owner/:repo/branches/main/protection`. That paragraph was
written on 2026-09-08 and is accurate: both `validate` and `ansible-verify` are
registered, `strict: true`, `enforce_admins: true`.

The CI/CD section does not repeat the registration claim, and does not add a
second one of its own. `ansible-verify.yml`'s own top comment explains the
discipline — a claim about repository *settings* cannot be verified by anything
in repository *content*, and `.github/tests` may make no network call, so such
a claim is unfalsifiable from inside the repository and rots silently. One
carefully hedged statement of it is the right number; two is one too many. The
CI/CD section names which contexts gate a merge and points at the same command.

## Decision 6: The Testing section names three commands and stops

`AGENTS.md` carries a three-row table — `terraform test`, `molecule test --all`,
`python3 -m unittest discover --start-directory .github/tests` — with the
subject and test-path glob for each, plus several paragraphs on which row a
given subject belongs to and how `molecule test --all` under-reports.

The README's Testing section currently describes a repository with none of
this. It gets the three commands, the glob for each, and a pointer to
`AGENTS.md` for the rest. It does not reproduce the row-selection reasoning or
the stop-at-first-failure caveat: those matter to someone writing a test, who
is already reading `AGENTS.md`, and a second copy is a second thing to keep
true. This change exists because of a first copy that was not kept true.

**This is also the one place the change interacts with the suite it must keep
green.** `test_ci_configuration.py`'s citation check walks every committed file
outside `openspec/` — `README.md` is one of its four named anchors — and fails
on any path naming a change's own directory under `openspec/changes/`. The
Testing section is where a citation is most tempting, so every reference it
adds is either an `openspec/specs/<capability>/spec.md` path or a change named
in prose.

## Decision 7: Status describes what exists, without naming what deploys onto it

The Status section says the repository is being bootstrapped and that
`ansible/` and `platform/` hold "structure and convention only". Both were true
on 2026-08-19. Today `prod` is provisioned, configured by
`ansible/playbooks/host-baseline.yml`, and running `platform/`'s eight-service
stack; twenty-five changes are archived.

The section is rewritten to say that, and to keep the staging paragraph, which
is still true and is load-bearing for the Non-goals framing.

It does **not** name the applications running on the host. They are deployed
from their own repositories through `deploy_user`'s per-application path; which
ones exist is not this repository's fact to state, and it is a fact that
changes without any commit here — the exact failure mode this change is
correcting. The section says applications deploy onto the host and names the
mechanism, which is stable.

## Decision 8: Enforcement is queued, not folded in

The obvious response to "the README disagreed with `terraform.tfvars` for
weeks" is a `.github/tests` assertion that they agree. It is in scope for that
suite by construction — a static read of two committed files, no network, no
credential, no container — and this repository already asserts a documentation
convention that way (the citation-form check exists because "no author or
reviewer can catch a violation", which is equally true here).

It is still a separate change, for two reasons:

- **It needs a requirement.** This repository does not enforce a convention it
  has not recorded; the citation rule has one in
  `openspec/specs/iac-repo-foundations/spec.md`. Adding a requirement makes
  this a change with a delta, which owes derived tests and a different set of
  gates — a materially different change from a truth pass.
- **Its scope is not obvious.** The region pair is one cross-file assertion.
  The scenario count is another. Whether the CI/CD section's workflow list
  should be checked against `ls .github/workflows/` is a real design question
  with a cost — a section that must be edited in the same commit as any new
  workflow. Deciding that inside a documentation fix would decide it badly.

`AGENTS.md` is explicit that an improvement noticed along the way becomes a
separate proposed change. Recorded in `docs/change-queue.md`.

## Decision 9: The Galaxy correction covers all four copies, not the README's

`docs/change-queue.md` entry 9 describes the defect as "README's Galaxy install
step does not provision a working local suite", and this change was scoped to
`README.md`. Reading the tree rather than the entry found the same command in
three more committed files:

| File | Context |
|---|---|
| `.ansible-lint:3` | explaining why `ansible/roles/geerlingguy.docker/` is excluded from linting |
| `.gitignore:28` | explaining why that directory is ignored |
| `ansible/requirements.yml:6` | "Install with:", in the manifest's own header |

Each tells a human to run the command that puts the role where nothing looks
for it. The last is the sharpest: the manifest instructs an install whose
result its own consumers cannot see.

Three arguments settle this in favour of fixing all four.

**These are not a second concern; they are the rest of this one.**
`AGENTS.md`'s scope rule is about *independent* concerns — "where one grows to
cover multiple independent concerns, consider splitting it" — and three further
copies of one wrong string are not independent of the string. Queue entry 9
names `README.md` in its title but reasons entirely about the command and about
where the role lands: its subject was always the command, and the README was
where it was first noticed. This is the extent of the defect the change already
owns, not an improvement noticed alongside it.

**It is below the threshold for a change of its own.** `AGENTS.md`: work too
small to be a change — "a typo, a one-line correction with nothing to specify"
— skips `plan`. Three comment lines, each a copy of a correction this change is
already making and already substantiating, is that. Queueing them would mean a
second change, two more pull requests, and an interval during which the
repository states the same thing two ways.

**The effect gate cannot otherwise be met honestly.** `tasks.md` 8.4 proposes
observing that the README's commands, copy-pasted into a fresh clone, land the
role inside `ansible/roles/`. A reader who opens `ansible/requirements.yml`
instead — the manifest the README points them at — gets the broken command and
the broken suite. This is the weakest of the three, because the gate is
authored by this change and could have been narrowed instead; it is listed
last for that reason.

The surrounding prose in each file stays untouched, and the replacement is not
uniform. Every one of those comments explains something true and non-obvious —
why installed content is excluded from linting, why it is gitignored, why the
pin is exact. `ansible/requirements.yml`'s header covers four collections and
one role, so it takes both commands; the other two are explaining a single
installed *role directory*, so they take the role command alone. Giving all
three the same text would put a collection install in two comments that have
nothing to do with collections, or strip the collections from the manifest that
pins them.

**One occurrence must survive.** `.github/workflows/pr-validation.yml:232`
quotes `ansible-galaxy install -r ... -p ...` as a deliberate negative example,
explaining that `-p` is silently ignored for collections — the reason the
two-command split exists at all. Any verification of this decision must be
written so that comment does not read as a fifth copy to fix; `tasks.md` 4.5
carries that trap, because the loose grep this change first wrote would have
matched it.

## Risks

**The corrections are stale on arrival.** Trunk moved twice under the handoff.
Mitigated by verifying every row against the tree at implementation time rather
than trusting this document's table, and by Decision 2 removing three of the
rows from the class that can rot at all.

**A truth pass turns into a rewrite.** The file has opinions worth keeping and
mechanism prose that took several changes to get right. Mitigated by the
proposal's *What this must not undo* section, and by the review gate reading
the diff against it.

**The Non-goals edit weakens a non-goal.** Called out in Decision 3 and checked
explicitly in `tasks.md`.
