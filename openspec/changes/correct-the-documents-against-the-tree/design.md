## Context

See proposal.md, "Why". What shapes the design is one measurement and one existing mechanism.

**The measurement**, taken on 2026-09-13 against trunk `80a8ec5`. The archive holds seven retired requirement names — every `### Requirement:` sitting under a `## REMOVED Requirements` heading in `openspec/changes/archive/*/specs/*/spec.md` — against ninety-three names the specifications currently hold. Two of the seven are named nowhere outside `openspec/`: *Restricted Deploy Account for Platform Stack Access*, and *Ansible Configuration Is Verified in Continuous Integration*, which is also a **prefix of a live name** (*…and Gates the Merge*) and so matches wherever the live name is correctly cited. The remaining five are named in fourteen tracked files: four names wrongly, across **47 occurrences in 13 files**, and the fifth legitimately, as the single occurrence in `docs/deferred-work.md` that decision 1's exemption covers. Three of those thirteen files state the name **only across a comment's line break**, so a per-line reader finds nothing in them and reports a clean sweep; at occurrence granularity the wrapping is far commoner than that, ten of thirteen in `test_environment_agnostic_pipeline.py` alone.

**The mechanism** is already in this suite. `test_the_external_service_names_are_retired.py` sweeps tracked files for retired external-service names, exempts by prefix and by whole path, requires each whole-path exemption to still contain a retired name, and pins a set of sweep anchors so that a reader returning nothing cannot satisfy the assertion. Its docstring records why the file set is `git ls-files` rather than a filesystem walk: a walk reads a developer's provisioned `.molecule-home/`, which makes the sweep red on a working machine and green on a runner. This change writes a sibling of that module rather than a new idiom.

The constraint that rules out the obvious implementation: this repository states a requirement's name in at least four renderings — `*Emphasised Name*`, `"Quoted Name"`, `the Bare Name requirement`, and a name split over two comment lines — and the name appears before the path as often as after it. Parsing a citation to extract the name it carries is not reliable over 130 spec-path citations, which is why the assertion is written over retired names instead.

## Goals / Non-Goals

**Goals:**

- Every retired requirement name gone from committed files outside `openspec/`, by the predicate rather than by the rows entry 74 reported.
- A check that fails on the next one without anybody maintaining a list of names.
- `docs/bootstrap-a-new-host.md` followable end to end by someone who has never run it, including the step that currently fails.

**Non-Goals:**

- Renaming any requirement. This change reads the retired set; it does not add to it.
- Entry 75. Nothing here renames a GitHub Environment, and §3.2 already tells a new deployment to name its own for its stacks.
- Entry 70, which owns the read-only secret name in the provider comments. `terraform/stacks/main-staging/versions.tf` carries a knowingly-wrong sentence about prod's secret two lines below the retired name this change corrects; it is entry 70's and is left alone. Editing the adjacent line is how one change absorbs another's scope.
- A check over citations naming a **change**. See decision 4.
- Enforcing the citation *form* on lines this change touches for another reason, beyond the one case decision 8 names.
- Correcting stale **scenario** titles. Thirty of them, measured; see decision 7, which records them as a change of their own rather than declining them.

## Decisions

### 1. Derive the retired-name set from the archive, not from a literal list

`test_the_external_service_names_are_retired.py` hard-codes its four literals, correctly: they are external service names, and no file in this repository enumerates them. Requirement names are different — the archive already records every retirement, in a fixed structural position, because `openspec validate` requires a `REMOVED` delta to carry the name and a `**Reason**`.

So the set is computed: every `### Requirement: <name>` under a `## REMOVED Requirements` heading in `openspec/changes/archive/*/specs/*/spec.md`, minus every `### Requirement: <name>` in `openspec/specs/*/spec.md`. The subtraction is load-bearing rather than tidy: a name can be removed by one change and reintroduced by a later one, and such a name is live.

*Alternative considered — hard-code the four names measured today.* Rejected because it puts the check one rename behind by construction: the change that retires the next name is the change that would have to remember to extend the list, and it is precisely the change with no reason to look. That is the defect this check exists to remove, reintroduced in the check itself.

*Cost of deriving*: the check now depends on the archive's structure. If a future `REMOVED` delta states its name some other way, the set silently shrinks and the check silently weakens. That is guarded by decision 3's anchors, which assert that the derived set is non-empty and contains a name known to be retired.

### 2. Match on a flattened rendering of each file, and report the line the match starts on

Three of the thirteen swept files wrap a name across a comment's line break, so a per-line match misses them — `.github/workflows/drift.yml`, `.github/workflows/pr-validation.yml` and `terraform/stacks/main-staging/versions.tf`, all three in exactly the position where a name is least likely to be noticed by a human. The reader therefore builds, per file, a single flattened string: each line stripped of leading whitespace and of a leading comment marker, joined by one space, runs of whitespace collapsed. It keeps an offset-to-line map while doing so, so a match still reports `<path>:<line>: <name>`, as the sibling module's failures do.

*Alternative considered — match per line, and accept the three misses.* Rejected: those three are the majority of the change's interesting surface, and a check whose blind spot is "a name long enough to wrap" is blind to exactly the long names this repository writes.

*Trade-off, stated rather than solved*: stripping a leading comment marker means a line of prose starting with `#` in Markdown — a heading — is flattened into its neighbours. A retired name spanning a heading boundary would be reported, and reported at the heading's line. No such case exists today and the report names the file, so a reader is one line away from the truth.

**The blind spot this predicate keeps, disclosed rather than closed: a citation that names only part of a retired requirement.** `.github/tests/test_terraform_stacks_are_the_iterated_unit.py:2951` holds `"Each Environment Declares Its Own Pipeline` inside a fixture that claims to reproduce `terraform/stacks/main-staging/pipeline.yml` verbatim as it stands at HEAD — and that file says `Each Stack`. The fixture is stale, and the sweep will not report it, because the name is truncated at a line boundary the fixture reproduces as a separate list element rather than as wrapped text. It is corrected by hand in task 2.7. Widening the predicate to catch a truncation would mean matching prefixes of retired names, which over ninety-three live names matches a great deal of correct prose; the narrower predicate with a disclosed hole is the better trade, and the hole is one that only a fixture quoting a comment can fall into.

### 3. Report the replacement, and anchor the sweep

The failure message names what the requirement is called now, taken from the `**Migration**` or `**Reason**` line of the `REMOVED` block where it names a replacement in emphasis. A check that says only "this name is retired" sends the reader to the archive to find out what to write; the four sweeps this change performs each needed that lookup.

**The recorded replacement is reported only where a specification currently holds it**, and the chained case is why that qualifier is not pedantry: *Dedicated Hetzner Cloud Project for Prod* records its replacement as *Each Environment Has a Dedicated Hetzner Cloud Project*, which is itself retired. Reporting it would hand the reader a name the same check forbids. Where the recorded replacement is retired, the reader follows the chain to the first live name and reports that; where the chain ends in no live name, or the block records no replacement, the message omits it and says the name is retired without saying what to write instead.

The sweep carries anchors in the sibling module's sense — tracked paths that must be among the files read, one per surface at several depths — because every assertion here is satisfied by a reader that returns nothing. It additionally asserts that the derived retired set is non-empty and contains *Each Environment Has a Dedicated Hetzner Cloud Project*, which is retired, is recorded as such in an archived delta this change does not touch, and will stay retired.

### 4. Decline the change-name check, and record why

Entry 74 raises a second candidate: a check over citations naming a **change**, since `docs/bootstrap-a-new-host.md` twice cites `add-a-staging-stack`, which never existed. It is declined, on a measurement rather than on a feeling about false positives.

Sweeping every `entry <N>` and every backticked kebab-case token that resolves like a change name finds forty-odd occurrences, and the overwhelming majority are **historical statements that are correct**: "the former entry 50", "Was `docs/change-queue.md` entry 26, deleted from there and recorded here", "8 by `namespace-the-molecule-suite-per-working-tree`". `docs/change-queue.md` and `docs/deferred-work.md` are *built* out of such statements — saying what became of a deleted entry is their job. A check reporting them would be exempting both files entirely, which leaves it reading almost nothing, or carrying a per-occurrence exemption list that is longer than the defect.

The asymmetry with requirement names is the reason one is checkable and the other is not: a retired requirement name has **no legitimate use** outside a record of its own retirement, and that set is one file and one line today. A retired change name has many.

Recorded in `docs/deferred-work.md`, not in the queue. `AGENTS.md` gives the two files opposite meanings — the queue holds identified changes worth doing, `deferred-work` holds what this project has deliberately not done — and the paragraphs above argue this check is not worth building at any cost, which is the second. The record exists so that the next person meeting a citation of a change that does not exist finds the measurement rather than repeating it.

### 5. Exempt the new module alone, not `.github/tests/` wholesale

The sibling sweep exempts the whole of `.github/tests/`, and its docstring gives two reasons: a check must name what it forbids, and several modules build synthetic trees naming `prod`, `staging` or a retired secret in order to exercise a reader. Only the first of those reasons transfers.

The measurement says why it matters. Forty-seven occurrences of a retired requirement name exist outside `openspec/`, and **forty of them are in `.github/tests/`** — thirteen in `test_environment_agnostic_pipeline.py` alone. Every one that was read is prose: a section banner (`# iac-cicd-pipeline / Each Environment Declares Its Own Pipeline Configuration`), a docstring stating which requirement a class or method traces to (`"""MODIFIED requirement: Dynamic Inventory via hcloud Plugin — scenario …"""`), or a sentence of reasoning naming the requirement it rests on. **None is a fixture.** A suite whose every `SPECIFIED` docstring cites a requirement by name is the densest citation surface in the repository, and exempting it would leave eighty-five per cent of the defect behind a hole — which is what the sibling module's own docstring criticises an over-wide exemption for.

So the exemption is one path: the new module itself, which has to state retired names in order to assert their absence and which builds the fixture trees that falsify its reader. The other six modules are swept and corrected like any other file.

*Alternative considered — exempt `.github/tests/` and correct the six modules anyway, as ordinary edits.* Rejected: the edits would land and nothing would hold them. The next `SPECIFIED` docstring written against a requirement that is later renamed would rot exactly as these forty did, inside the suite whose job is to catch that.

### 6. Exempt `docs/change-queue.md` for the life of this change, and delete the exemption in the archive commit

The check would otherwise be **red on this change's own pull request**. `docs/change-queue.md:631` is entry 74, which names *Each Environment Has a Dedicated Hetzner Cloud Project* because naming it is what the entry is for — and `AGENTS.md` deletes a queue entry when its change archives, not when the implementation merges. So between the two there is a commit range where the tree carries a retired name in a file the sweep reads, and the required check is red on the trunk.

The exemption is that file, by path, with entry 74 named as the reason, and a task deleting it in the archive commit. That is not a workaround: it is the expiry machinery of decision 1's sibling module, which records `docs/change-queue.md` as having been exempt for exactly this reason under entry 63 and having gone red in the archive commit when the entry was deleted — which is what forced the exemption's removal in that same commit. Task 1.8's assertion is what makes it self-retiring, so the same event recurs here by construction rather than by anyone remembering.

**This cost recurs for every future rename**, and it is worth writing down rather than rediscovering: a change proposing to rename a requirement writes the old name into the queue, and is exempt until it archives. That is one line of exemption per such change, paid in the change that causes it and removed by the check itself.

*Alternative considered — delete entries 73 and 74 in the implementation commit instead of at archive.* Rejected: it contradicts `AGENTS.md`, and it loses the queue entries while the change is still in flight and could still be abandoned.

**The same hazard exists one commit later, at the archive, and is closed by constraining what the new queue entry may quote.** The archive commit deletes entries 73 and 74 *and* the exemption that covered them, while decision 7's task adds a new entry about citations of renamed requirements — and an entry written in this repository's usual style would quote the thing it is about. If it quotes a retired **requirement** name, the archive pull request is red, and the only repairs are to keep a hole this change opened or to reword under pressure.

So the entry quotes **scenario** titles, which is what it is about, and never a retired requirement name. That costs the entry nothing: a scenario title is not in the retired set the check reads, and the thirty instances it records are scenario titles in the first place. The entry itself is written during implementation, as `AGENTS.md` requires of a surfaced change — the constraint is not what makes it safe then, since the file is still exempt, but what keeps it safe in the archive commit once that exemption is gone. A task re-runs the suite over the archive commit's own content rather than trusting this paragraph.

### 7. Leave stale **scenario** titles to a change of their own, and record the measurement

A requirement's citation names the requirement and often a scenario inside it: `"""MODIFIED requirement: Dynamic Inventory via hcloud Plugin -- scenario "A source's credential variable is the name the environment declares"."""`. Both halves rotted in the same rename, and correcting only the first leaves that docstring naming a live requirement and a scenario it does not have. Measured 2026-09-13: **thirty scenario-title citations name no scenario any specification currently holds**, twenty-nine in `.github/tests` and one in `.github/workflows/drift.yml`.

It is left out, against decision 8's own principle about not leaving a known-wrong citation on a line you are editing, for two reasons that decision 8's case does not have. It is a **different predicate** — the live scenario set, not the retired requirement set — so it needs a reader of its own, and the check this change builds would not hold it. And it is thirty instances whose replacements are not mechanical: some scenario titles were reworded rather than renamed, so each needs a judgment rather than a substitution. Folding it in doubles the diff and puts a second unchecked sweep inside the change whose point is that unchecked sweeps recur.

What is **not** acceptable is to leave the artifacts asserting that the citations are right afterwards, which is what they said before this decision. They now say what remains. It is recorded in `docs/change-queue.md` as an identified change rather than in `docs/deferred-work.md`, because it is worth doing and extends this change's own check to a second predicate — not work declined.

### 8. Correct the citation *form* only where this change's own check will read the line

`ansible/ansible.cfg` cites `iac-host-configuration`'s "Dynamic Inventory via hcloud Plugin" by capability name and requirement name, with no path — which the requirement being modified here obliges to be `openspec/specs/<capability>/spec.md` plus the name. The name is corrected because it is retired; the path is added in the same edit, because leaving a known violation of the requirement on the very line a new check reads is how the next sweep finds it again.

Everywhere else the form is left as found. The change corrects names, not renderings.

### 9. The GitHub App travels with the sweep rather than becoming its own change

It is independent of entries 73 and 74, it needs no delta, and it is the one defect here that makes a documented step fail — so `AGENTS.md`'s scope rule fairly asks why it is not split out. Three reasons, and the first is the one that decides it.

The **reader is the same reader, and the document is the same document**. Every bullet in this change is a correction to `docs/bootstrap-a-new-host.md` for the benefit of someone cloning the repository; splitting the App gap out means that person reads a runbook corrected in two passes, and the pass that fixes the names lands first while the pass that fixes the failing step waits behind a second review. Second, the edits **touch the same sections**: §0.4's table and Appendix A are each edited by both halves — §0.4 by tasks 2.5 and 5.2, Appendix A by 3.6 and 5.5 — so splitting them means two changes contending for the same paragraphs. Third, it is small — five tasks, none of them requiring a decision, against a requirement that already says what the App must be.

What would change this: if the sweep needed a second review round and the App gap did not, the App gap should be lifted out and shipped rather than held. That is a judgment for `build`, not for now.

### 10. The GitHub App is a documentation gap against an existing requirement, not a new one

*Automated Dependency Updates* (`openspec/specs/iac-safety-hardening/spec.md`) already obliges the separate identity, obliges that its credential be scoped to this repository, and obliges that it not be one that expires on a schedule — and gives the reasoning for each. Nothing about the obligation is missing; what is missing is the runbook telling a new deployment to create one. So this part of the change writes documentation and declares no delta: §0.1 gains the App among the accounts, §3.2 gains its creation with the two permissions the requirement bounds it to, §3.3 gains the two repository secrets, Appendix A gains the row that makes it a complete inventory, and stage 9.4 stops being a step that fails.

### 11. Correct dead change-queue pointers only where they read as live

Most references to a deleted entry are history and are correct — decision 4's measurement is the same one. What is corrected here is the narrower set that points at a dead entry as a **live owner or successor**: Appendix C's "still to do before real data arrives: log rotation (21), swap and container limits (22, 7)", which names two delivered entries as outstanding work; `docs/deferred-work.md`'s "**Owner:** `docs/change-queue.md` entry 62"; and the four citations of entry 23 as the change that *would* move the converge into a workflow, which it did, in `ansible/roles/platform_data_volume/tasks/main.yml`, `ansible/roles/swap/tasks/main.yml` and queue entries 25 and 30.

### 12. Rewrite the naming banner rather than delete it

`docs/naming-conventions.md`'s banner says the scheme is not in effect and that entry 75 alone remains after entry 64. Both halves are wrong in the same direction: every name the scheme governs has moved except the two GitHub Environments, and entries 73 and 74 are outstanding beside 75. Deleting it is not available — entry 75 genuinely is undelivered, and the banner is what tells a reader why the Environments do not match. It is rewritten to state what is true: the scheme is in effect; the GitHub Environments are the exception; a new deployment pays nothing, and §3.2 is where it acts on that.

The banner's instruction "whoever archives 75 deletes this banner" survives the rewrite, because it is still correct.

## Risks / Trade-offs

**The derived retired set could silently empty if the archive's delta format changes** → decision 3's anchor asserts a known-retired name is in the set, so an empty or broken derivation fails rather than passing over nothing.

**Forty of the forty-seven occurrences are in `.github/tests/`, and correcting them is most of this change's diff** → decision 5 takes them rather than exempting them, so the diff is large and almost entirely one exact string replaced by another. The review risk is therefore a missed occurrence rather than a wrong edit, and the check added by decision 1 is what turns the re-measurement into a run instead of a reading. What it is **not** is a complete repair of those citations: decision 7 leaves the scenario title beside each requirement name for a change of its own, so a docstring this change edits can still name a scenario that no longer exists.

**The heartbeat check rename needs a step at the observer, which no check can hold** → §7.1's `<company>-prod alertmanager` already exists under the old name at healthchecks.io. The document edit alone leaves the tree correct and the observer stale. It is written as an operator task with the rename and the re-pointing of `PLATFORM_DEADMANSWITCH_URL` named together, since the ping URL follows the check rather than the name.

**Correcting a comment that `.github/tests` asserts verbatim turns that test red** → `test_terraform_stacks_are_the_iterated_unit.py` asserts `terraform/stacks/main-staging/versions.tf`'s comment line as a literal. That is the mechanism working, not an obstacle: the literal moves in the same commit.

**The change edits many files and each edit is small** → the review risk is a missed instance rather than a wrong one. Every sweep here is performed by the predicate and then re-measured, and the check added by decision 1 is what makes the re-measurement mechanical rather than a reviewer's reading.

## Open Questions

None. The one judgment entry 74 left open — whether to build the check-shaped half — is decision 1 and decision 4.
