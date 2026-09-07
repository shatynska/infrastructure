## Context

See `proposal.md` — Why. What that section does not carry is the measurement the
design rests on, and the shape of what has to be edited.

Measured on 2026-09-07, at trunk `9420798`, over committed files outside
`openspec/`:

| | |
|---|---|
| Files | 44 |
| Citations | 75 — every one broken, since `openspec/changes/` now holds only `archive/` |
| `ansible/` | 39 files |
| `platform/` | 2 · `.github/` 2 · `README.md` 1 |

Two earlier counts exist and both are low. `docs/change-queue.md` entry 1 says
"33 files, 58 references"; the handoff that opened this change says 31 and 48.
Both used a pattern requiring a `/` after the change name, which misses the 27
citations that name the change directory with nothing after it — for example
`requirement (openspec/changes/connect-platform-deploy-via-tailscale)` in
`ansible/roles/tailscale/tasks/main.yml`. Those break exactly as the others do.

What the 75 citations point at is the fact that decided the policy:

| Target | Count | Permanent home after archive |
|---|---|---|
| The change name or directory, no artifact | 33 | — |
| A delta specification (`/specs/<capability>/spec.md`) | 22 | **yes** — `openspec/specs/<capability>/spec.md` |
| `design.md` | 11 | no |
| `test-plan.md` / `test-manifest.md` | 8 | no |
| `proposal.md` | 1 | no |

Constraints that bound the implementation:

- **The archive date does not exist until archiving happens**, so no author can
  pre-write the post-archive path. This eliminates "just cite the final location
  from the start", which is otherwise the cheapest-looking answer.
- **`openspec archive --yes` moves the directory and updates the main
  specifications. It rewrites no citation anywhere** — proven by the 13 that
  broke during `fix-volume-discovery-and-consistency`'s own archive.
- **`.github/tests/test_ci_configuration.py` may not spawn a subprocess other
  than `bash`/`sh`, import a network-capable module, or use anything outside the
  standard library plus `yaml`** — `iac-cicd-pipeline`'s requirement *The
  Continuous-Integration Configuration Is Itself Verified*, asserted by that
  suite against itself. `git ls-files` is therefore unavailable for enumerating
  files.

## Goals / Non-Goals

**Goals:**

- A citation form that cannot be invalidated by archiving.
- A rule recorded where it will still be read in six months.
- An automated check that fails the pull request reintroducing the old form,
  because no human reviewer can catch it — the citation is correct until the
  moment it is not.

**Non-Goals:**

- Separating history from rationale in comment prose. That is
  `docs/change-queue.md` entry 3, deliberately left queued; this change touches
  the same comment blocks only to change a citation's form, and changes nothing
  else about them.
- Validating that a cited change name exists. See Decision 5.
- Rewriting citations inside archived changes' own artifacts, which move
  together with what they cite.
- Any change to Terraform, Ansible task logic, workflow behaviour, or a deployed
  artifact.

## Decisions

### Decision 1 — The citation form splits by what is cited

A requirement is cited as `openspec/specs/<capability>/spec.md` plus the
requirement's name. Rationale and history are cited by change name and artifact
name, with no path.

The split exists because the two targets have genuinely different fates.
Archiving *merges* a change's delta into the main specification, so a
requirement acquires a permanent home; a `design.md` never does — it only ever
lives inside the change. Treating them alike would either invent a path where
none can exist, or throw away a stable path that already does.

The specification form is also better than what it replaces, not merely
durable. `openspec/specs/iac-platform-services/spec.md` shows the requirement as
it stands now; the delta it replaces shows what one change proposed at one
moment, which may since have been modified by a later change. Twenty-two of the
75 citations improve rather than degrade.

One case does not resolve immediately. A change that introduces a **new**
capability cites a requirement at `openspec/specs/<new-capability>/spec.md`, and
archiving is what creates that file — so the citation is unresolvable for the
change's own lifetime and correct from its archive onward. That is the inverse
of the defect this change removes, and the interval is the change's remaining
lifetime — in this project days to weeks, through review rounds, a pull request,
a merge, a deploy and a confirm gate — rather than forever, so it is accepted
rather than designed around. Two alternatives were weighed. Citing by change name
until archive and then rewriting reintroduces the rewrite step this decision
rejects. Citing the capability and requirement by name permanently, with no path,
ends in a citation weaker than the one archiving would have made correct anyway —
it pays the cost of the interval forever to avoid paying it once. The delta spec
and the
`AGENTS.md` rule both state the interval, so nobody reads the resulting dead
path as a defect.

Precedent exists, though it is thinner than it first looks. Eight live-source
citations already use the `openspec/specs/` form, but six of them are in
OpenSpec's own CLI-installed files under `.claude/`, which this change neither
sweeps nor authors. Within the repository's own files the precedent is two —
`.github/tests/test_ci_configuration.py` and
`ansible/roles/ops_user/molecule/default/verify.yml`. Two is enough to show the
form is already legible here; it is not enough to call it an established
convention, and the decision does not rest on it.

*Alternatives considered.* **Cite by name everywhere** — the handoff's fourth
option. Simplest possible rule and test, but discards clickability for the 22
citations that can keep it, with nothing gained. **Rewrite paths at archive
time** — keeps every citation clickable, but makes each archive a repository-wide
edit across ~44 files, needs a script wired into the archive step, and does not
stop authors writing the pre-archive form in the interim; the rewrite step then
has to catch every new citation forever, which is the same "remember to do it"
dependency in mechanical clothing. **Strip citations entirely** — queue option
2; loses the provenance trail these comments are unusually good at, and is a
larger loss than the problem. Rejected on merit.

### Decision 2 — The rule goes in `AGENTS.md`, not in this change's `design.md`

A rule kept in a change's design is archived with that change and stops being
read. `sweep-stale-terraform-paths` (archived 2026-08-19) did the mechanical
work and changed no rule; the citations fully re-accumulated within three weeks.
`docs/change-queue.md` entry 1 reaches the same conclusion independently.

The rule goes under this repository's own project conventions in `AGENTS.md`,
alongside the Testing table and the host-configuration defaults — the section a
session reads before touching this repository at all.

### Decision 3 — The sweep and the enforcing test land in this change

`docs/change-queue.md` entry 2 (`sweep-stale-openspec-references`) is folded in
rather than left for a successor. The reason is a hard coupling, not
convenience: the enforcing test fails on all 75 existing citations, so it cannot
be merged before the sweep, and the sweep without the test is precisely what was
done last time and did not hold.

Splitting them would land the rule unenforced for an interval — the mirror image
of the previous failure, and with the same outcome.

The resulting diff is large (44 files) but mechanical and comment-only. It is
reviewable in one sitting because every hunk is the same edit.

### Decision 4 — The check lives in `.github/tests/test_ci_configuration.py`

It is the only mechanism this repository has that statically reads committed
files at repository scope. `terraform test` reaches Terraform modules only;
Molecule converges a host and asserts behaviour, not file contents.

This suite already hosts assertions for capabilities other than
`iac-cicd-pipeline` — `iac-safety-hardening`, `iac-platform-services` and
`iac-host-configuration` each have a section in it — so hosting an
`iac-repo-foundations` assertion needs no widening of anything. It is also the
lever that made image pinning and Molecule digest pinning stick, which is the
outcome this change is trying to reproduce.

`AGENTS.md`'s Testing section describes this suite's subject as "CI
configuration, and any committed file the pipeline reads or executes". A
citation form is not a property the pipeline depends on, so the sentence is
narrower than the suite's actual practice — the `iac-host-configuration`
assertions already sit outside it. The Testing row is widened in the same edit
that adds the rule, to say what the suite is actually for: a static read of a
committed file, wherever that file lives.

### Decision 5 — The test keys on a *change-shaped* path segment, and does not verify that the change exists

The check fails on `openspec/changes/<segment>` in a committed file outside
`openspec/`, where `<segment>` is not `archive` and matches a change name's
shape — lowercase kebab-case, `^[a-z0-9]+(?:-[a-z0-9]+)*$` — whether or not a
further path component follows it.

Nothing may be required after the segment. Twenty-seven of the 75 citations name
the change and stop, and requiring a trailing `/` is the exact mistake that made
both earlier counts of this problem come out low; making it again in the check
would leave a third of the citations permitted by the rule written to remove
them.

Requiring the kebab shape rather than any segment is what lets documentation —
`AGENTS.md`'s own rule text, this suite's docstrings, `docs/change-queue.md` —
write the forbidden form with a metasyntactic placeholder such as
`openspec/changes/<name>/` without tripping the check it describes. Exempting
those files by name instead would punch holes that later drift into real
violations.

Permitting `archive` keeps the two correct, permanent citations already in
`AGENTS.md` (`openspec/changes/archive/2026-08-18-project-foundation/design.md`
and the `integrate-ansible-host-config` one) rather than forcing them into a
weaker form for uniformity's sake.

The check deliberately does **not** resolve a cited change name to a directory.
A bare name in prose is an ordinary word; distinguishing a citation from a
sentence would need either a bespoke marker syntax (`change:<name>`) or a
heuristic over backticked tokens. The first is an invention this repository
would have to carry forever to catch a typo; the second produces false
positives. A misspelled change name is a low-consequence defect that a reader
notices; a broken path is a high-consequence one that no one notices. The check
is scoped to the second.

### Decision 6 — The check's own fixtures carry no literal of the forbidden form

`.github/` is not pruned, and the sweep converts this suite's own three
citations, so the file carrying the check is itself in the set the check reads.
A discrimination test that seeds `openspec/changes/some-change/design.md` as a
string literal would therefore make the suite flag its own source, turning the
required status check red on this change's own pull request.

Every fixture citation is assembled at run time from parts — a prefix constant
and a segment constant joined by an f-string — so no literal of the forbidden
form appears in a committed file. The matcher's own pattern needs no such
treatment: there, `openspec/changes/` is followed by a regular-expression group
rather than by a kebab-case segment, so the pattern does not match itself.

This suite has met the same hazard before and answered it the same way in
spirit. `test_the_suite_spawns_no_terraform_binary_or_container_runtime` reads
its own `subprocess` calls out of the abstract syntax tree precisely because a
text match cannot tell a command being run from the word "terraform" occurring
legitimately as a Dependabot ecosystem name.

The alternative — exempting `.github/tests/test_ci_configuration.py` by name — is
rejected for the reason Decision 5 gives against by-name exemptions generally,
and with more force here: the hole would sit inside the file that carries the
check.

### Decision 7 — Files are enumerated by walking the tree, not by asking the version-control tool

`subprocess` is confined to `bash`/`sh` by the suite's own assertions, so
asking the version-control tool for the tracked file list is unavailable. The
check walks from the repository root, pruning `.git`, `openspec`, `node_modules`,
`.terraform`, `ansible/roles/geerlingguy.docker` (an externally-installed Galaxy
role, ignored by `.gitignore:30`), and the two working-tree locations —
`.worktrees`, as `AGENTS.md` names it generically, and `.claude/worktrees`, where
the Claude Code binding places it. Each remaining file is read as UTF-8 with
undecodable bytes replaced.

The prune list is two kinds of entry and the check must treat them differently.
`.git`, `.terraform`, `node_modules` and `__pycache__` are pruned wherever they
occur, at any depth — `.terraform` in particular exists under each of
`terraform/environments/*/`, and a root-anchored reading would leave the walk
reading provider binaries.

`__pycache__` was added after deriving the tests showed the check reporting
`.github/tests/__pycache__/test_ci_configuration.cpython-312.pyc` as a 76th
offence alongside the 75 real ones. It is ignored by `.gitignore:33`, so it is
not a committed file and the requirement does not reach it; and running the
suite is what creates it, so it is a false positive the check inflicts on
itself on every run rather than one a developer occasionally provokes. That
distinguishes it from the untracked scratch file this decision accepts below:
a scratch file is a developer's own doing and visible to them, while a stale
`.pyc` compiled before the sweep would keep the check red after the sweep had
made it true. `openspec`, `.worktrees`, `.claude/worktrees` and
`ansible/roles/geerlingguy.docker` are pruned only at their path relative to the
walk root.

Pruning the working-tree locations matters. Without it the check descends into a
full second checkout of the repository sitting on another branch, reports every
finding twice, and fails locally for reasons that have nothing to do with the
branch under test. Continuous integration checks out one tree and is unaffected
either way.

`.claude` is **not** pruned wholesale, only its `worktrees` subdirectory. Twelve
files under it are tracked — `.claude/commands/opsx/*.md` and
`.claude/skills/openspec-*/SKILL.md` — and the requirement is normative over
every committed file outside `openspec/`. Pruning the whole directory would ship
the prohibition with a silent hole in exactly the place that documents OpenSpec's
change layout, and so is the likeliest future source of the forbidden form.

Those twelve files are installed by the OpenSpec CLI, so a future `openspec
update` could write the forbidden form into a file this repository does not
author. None carries it today. Should one arrive, the remedy is to edit the file
and re-apply the edit after each update, or to raise it upstream — not to add a
by-name exemption, which is not made without a recorded decision, for the reason
Decision 5 gives.

The walk is a superset of the tracked files, not an exact match — an untracked
scratch file in the tree would be read. That is the safe direction for a
prohibition: it can report a violation that git would not carry, which a
developer sees and resolves, but it cannot miss one that git does.

## Risks / Trade-offs

**The sweep touches 44 files, two of which carry load-bearing comment blocks** →
The `POLARITY` note in `ansible/roles/tailscale/tasks/main.yml` and the GHCR
tolerated/not-tolerated block in `ansible/roles/deploy_user/tasks/main.yml` must
survive intact. Both are cited by name in `tasks.md` with an explicit
before/after check, and the diff for both files is read line by line rather than
skim-reviewed. Neither block's citation is inside the part that carries the
reasoning.

**A 44-file comment-only diff invites rubber-stamping** → Every hunk is the same
edit, which is what makes the diff reviewable, but also what makes a wrong hunk
easy to miss. The verification is not the reviewer: the enforcing test fails
unless every citation was converted, and the Molecule suite still converges the
roles whose files were touched.

**Clickability is lost for the 53 citations that name only a change** → A reader
who wants the artifact runs `ls openspec/changes/archive/*-<name>/`. This is the
cost the operator accepted; no option preserves both permanence and a clickable
path to an artifact that has no permanent path.

**The check is a text match and can be evaded** → Splitting the string across a
line break defeats a naive matcher. No citation in the tree wraps where that
would matter. Several are line-wrapped, but the wrap always falls *after* the
change-name segment — `…/fix-volume-discovery-and-consistency/specs/` ends one
line and `iac-host-configuration/spec.md` continues the next — which a plain
contiguous match already catches. The tolerance for a wrap between the prefix
and the segment is therefore insurance against a form nobody has written yet,
not a fix for one that exists. It is cheap, and what it guards against is the
silent miss this whole change exists to prevent, so it is kept — but it is
exercised only by a synthesised fixture, and no task may cite an existing file
as evidence that it works.

The tolerance is deliberately narrower than the contiguous match in one respect:
across a line break the segment must contain a hyphen. Contiguously, a bare
`openspec/changes/some-change` is flagged, because 27 real citations take that
form. Applying the same latitude across a line break would flag any prose line
ending in the prefix whose continuation begins with an ordinary lowercase word —
`…a path under \`openspec/changes/\`` followed by `# is not permitted` offers
`is` as a kebab-shaped segment. That would redden the required check on
documentation describing the rule, in the same three files Decision 5 keeps
passable.

Requiring a hyphen separates the two cleanly, where requiring a following `/`
would not. Every change this repository has recorded is named in multiple
hyphenated words; the prose continuations that motivate the narrowing — `is`,
`not`, `the` — are single words. So the hyphen test flags a wrapped citation
whether or not a further path component follows it, and still passes the prose.
What it excludes is a wrapped citation of a single-word change name, which is
the intersection of two shapes neither of which has occurred, and which the
requirement itself records rather than leaving to this section — this section is
archived with the change, and the requirement is not. A citation obfuscated
further than a line break is out of scope, as it would be for any check of this
kind.

**Comment-only edits to Molecule scenario files could break the suite** → YAML
comments cannot change behaviour, but a mangled comment marker can make a file
unparseable. `molecule test --all` is run per touched role, and its SCENARIO
RECAP read scenario by scenario rather than by exit code — the run stops at the
first failing scenario and silently skips every scenario sorting after it.

## Migration Plan

No deployment, no rollback: the change alters comment text, one convention
document, and one test file. Nothing it touches is read at run time by a
deployed artifact.

The archive step deletes `docs/change-queue.md` entries 1 and 2 and leaves entry
3 queued. Entry 3's blocking line names both of them — "**Blocked on entry 1**,
and should follow entry 2 rather than race it" — so both clauses are removed
together; taking only the first leaves a reference to an entry that no longer
exists.
