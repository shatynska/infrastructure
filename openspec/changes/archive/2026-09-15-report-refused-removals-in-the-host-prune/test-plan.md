# Test plan

Derived from this change's delta spec for *Unreferenced Host Images Are Pruned on a Schedule*, before any of its implementation was written, by an author other than whoever implements it. The prune script existed when these tests were written — this change modifies an installed script rather than creating one — and it was **not read**. Everything below traces to the delta's scenario text, to this change's `proposal.md` and `design.md`, or to what was observed on the fixture host and is recorded as observed.

This file is not part of the OpenSpec schema. It will not appear among the context files `openspec instructions apply` lists, so it has to be opened on purpose before implementing.

## Where the tests are, and how to run them

This change's tests are all in the **Molecule** row of `AGENTS.md`'s test table, in one file:

    ansible/roles/image_prune/molecule/default/verify.yml

Run them from `ansible/roles/image_prune`:

    ansible/scripts/run-molecule test -s default      # this change's scenario
    ansible/scripts/run-molecule test --all           # all four, read the SCENARIO RECAP

Molecule selects a **scenario**, not a task, so the runner-selectable identifier for every test below is `run-molecule test -s default`. Within that scenario a test is named by its Ansible task name, which is what the task tables below use and what the run prints. Nothing this change adds is a static read of a committed file, so nothing belongs in `.github/tests`, and nothing here is Terraform.

## Baseline

**Scoped**, and the scope is the `default` scenario of `image_prune` — the one scenario every assertion this change adds lands in. Taken with `ansible/scripts/run-molecule test -s default` from `ansible/roles/image_prune` before a line was written:

- **First attempt: not a baseline.** It failed at Molecule's `syntax` step with *"The role 'geerlingguy.docker' was not found"* — an unprovisioned working tree, not a red suite. `ansible-galaxy role install -r ansible/requirements.yml -p ansible/roles` provisioned it.
- **Second attempt: green.** `SCENARIO RECAP: default: actions=12 successful=8 missing=5 failed=0`. So every failure reported below is this change's tests and nothing inherited.

`--all` was **not** run as the baseline and is not claimed: `AGENTS.md` records that it stops at the first failure and lists nothing after it, and this repository's own notes record `--all` being memory-killed on this workstation. Continuous integration covers that path. The other three scenarios of this role were neither run nor changed.

## Scenario accounting — 27 in the delta, 27 accounted for

Twenty-three of the twenty-seven are unchanged by this change and were covered by the change `prune-unreferenced-host-images-periodically`; its own test-plan.md is the accounting for how each was derived. They are listed here because a `MODIFIED` requirement restates every scenario it carries, so this change's delta contains all twenty-seven and each must be accounted for exactly once. **This pass added no test for any of them and changed none of their tests.**

| # | Scenario | Covered by | This pass |
|---|---|---|---|
| 1 | An image superseded by a newer pin is removed | `default`: *Assert the superseded tag of the base repository is gone and the referenced one remains* | pre-existing |
| 2 | An image one application references is kept when another does not | `default`: *Assert an image only one enumerated application references was kept by the union* | pre-existing |
| 3 | A defined service that is not running keeps its image | `default`: *Assert an image a defined service references with no container anywhere was kept* | pre-existing |
| 4 | A service behind an inactive profile keeps its image | `default`: *Assert an image referenced only behind an inactive profile was kept* | pre-existing |
| 5 | An image a container holds is never removed | `default`: *Assert an image a stopped container holds was kept and its container still holds it*, with *Assert the script consults no age criterion and never forces a removal* holding the unforced half | pre-existing |
| 6 | An image nothing references is removed | `default`: *Assert a tagged image nothing references and nothing holds was removed* | pre-existing |
| 7 | An untagged image nothing references is removed | `default`: *Assert an untagged image nothing references was removed by its identity* | pre-existing |
| 8 | A digest-referenced image an application pins is kept | `default`: *Assert a digest-pinned image an enumerated application references was kept* | pre-existing |
| 9 | An unreferenced image carrying more than one tag is removed through each of them | `default`: *Assert an unreferenced two-tag image was removed through each of its tags* | pre-existing |
| 10 | A tag of an image a container holds is not dropped | `default`: *Assert both tags of an image a stopped container holds are still present* | pre-existing |
| 11 | A tag re-pointed after enumeration is not removed | **Uncovered.** Observable only when the host's images change midway through a run, and a black-box scenario has no seam between the run's enumeration and its removal loop at which to change them. `verify.yml`'s header records the decision; unchanged by this change | pre-existing decision |
| 12 | A retired application's images become reclaimable | `default`: *Assert a retired application's image was reclaimed and every kept application's survived* | pre-existing |
| 13 | An unresolvable Compose file abandons the whole run | `default`: *Assert an unrenderable Compose file abandoned the whole run, removing nothing, and failed* | pre-existing |
| 14 | A malformed reference abandons the whole run | `default`: *Assert a malformed rendered reference abandoned the whole run, removing nothing, and failed* | pre-existing |
| 15 | An application that has never deployed does not abandon the run | `default`: *Assert the never-deployed application is enumerated, absent from the filesystem, and harmless* | pre-existing |
| 16 | An enumeration the host does not carry is distinguishable from one naming nothing | `abandon-paths` | pre-existing |
| 17 | An empty enumeration removes nothing | `abandon-paths` | pre-existing |
| 18 | An empty keep set removes nothing | `abandon-paths` | pre-existing |
| 19 | An old image in active use is not removed for its age | **Uncovered behaviourally**, held by the static read *Assert the script consults no age criterion and never forces a removal*. Every fixture is built during the run, so none carries an old `Created` and a behavioural assertion would pass against a conforming and a non-conforming script alike | pre-existing decision |
| 20 | A completed run reports what it did | **MODIFIED.** `default`: *Assert the completed run reported all three counts, contiguously and in order, and exited zero* | **new this pass** |
| 21 | A run whose removals were all performed reports no refusals | **NEW.** `default`: *Assert the first run reports a refused count of zero and names no refusal* | **new this pass** |
| 22 | A refused removal is counted and named | **NEW.** `default`: *Assert the refused removal was counted, named, left the image alone and exited zero*, with *Assert the named refusal carries the runtime's own message and reaches standard error* | **new this pass** |
| 23 | A refusal is distinguished from a removal that deleted nothing | **NEW.** `default`: *Assert a removal that deleted nothing was not counted as refused* | **new this pass** |
| 24 | An abandoned run says why and fails | `default`: *Assert the two abandoned runs are distinguishable from each other and from a completed run* (two branches); `abandon-paths` (the remaining three) | pre-existing |
| 25 | A non-responding runtime does not leave the unit running indefinitely | **Uncovered behaviourally**, held by the static read *Assert the schedule is the init system's and the service is a bounded oneshot*. Wedging the daemon inside a Molecule container breaks the same daemon the fixtures need, and the bound is systemd's rather than the run's | pre-existing decision |
| 26 | Configuring the host does not prune it | `default`: *Assert the converge armed the timer and executed no prune* | pre-existing |
| 27 | A host that was down at its scheduled time still runs | **Uncovered behaviourally**, held by the static read *Assert the timer carries the catch-up, UTC and randomised-delay settings*. A Molecule instance cannot be taken down across a scheduled occurrence | pre-existing decision |

Four uncovered, all four pre-existing decisions this change did not revisit, each with the reason above. No scenario this change added or modified is uncovered.

## What was added, and what it is red on

Everything below is **additive**. No existing test was edited, deleted or disabled, and no implementation was written. The only non-additive edit to `verify.yml` is its own file header (task 1.6), which carries no assertion.

### 1. The build base, recorded before the first run

Tasks: *Record the build base identity and tag count before the first run*, *Assert the build base enters the first run tagged, so its removal takes the by-tag path*.

Fixture premise only. `alpine:3.19` is this scenario's build base; every fixture is built `FROM` it with the classic builder, nothing enumerated references it and no container holds it, so it is a candidate on the first run and its removal takes the by-tag path. **Green on arrival, and correctly so** — it asserts the state of a fixture, not the behaviour under test.

### 2. The third count, read as a field (scenario 20)

Tasks: *Read the first run's report as three counted fields*, *Assert the completed run reported all three counts, contiguously and in order, and exited zero*.

**Red.** Observed: `SHAPE3 0`, `REFUSED no-such-field`; the run's report today is `prune-host-images: considered 14, removed 5`.

The refused count is extracted **from the report line itself**, not from anywhere in the run's output — a per-refusal line naming an identity could otherwise be matched first and its digits read as the count. Where the line carries no third field the read emits `REFUSED no-such-field`, so an assertion on the field can distinguish *the field says zero* from *there is no field*. That distinction is the whole of this change: before it, a host whose removals were blocked was byte-identical to a healthy one.

### 3. A run with nothing refusable reports zero (scenario 21)

Task: *Assert the first run reports a refused count of zero and names no refusal*.

**Red**, for the same reason: `REFUSED no-such-field`. The removed count is asserted non-zero alongside the zero refused count, so the assertion cannot be satisfied by a run that offered nothing. `RUNTIME-CONFLICTS 0` supplements it by counting lines carrying the runtime's own conflict wording (`conflict:`, `must be forced`, `cannot be forced`) rather than the script's vocabulary.

### 4. A removal that deleted nothing is not a refusal (scenario 23)

Tasks: *Read the build base state after the first run*, *Assert a removal that deleted nothing was not counted as refused*.

Two invocations of the first run perform a removal that deletes no image, and neither may be counted as refused: the build base, untagged while the runtime keeps the image a dozen fixtures depend on; and the first of the two-tag fixture's tags. Both exit zero.

**Observed on the fixture host, after the first run:** `alpine:3.19` is gone as a reference and the identity survives carrying no tag. That is this change's `design.md`, Decision 7, confirmed live rather than taken on trust.

**Red** on the `REFUSED 0` term alone; its three premise terms pass.

### 5. The multiply-referenced refusal fixture (scenario 22)

Tasks: *Run the prune immediately before the refusal fixture is pulled back*, *Read the bracketing run's own report*, *Pull the multiply-referenced fixture back from both of its repository paths*, *Assert the pulled-back fixture is one untagged identity with two references*, *Run the prune immediately after the refusal fixture is in place*, *Read the post-arrangement run's own report*, *Read the lines of that run which name the refused fixture*, *Read the refused fixture state after the run that was refused*, *Assert the refused removal was counted, named, left the image alone and exited zero*, *Assert the named refusal carries the runtime's own message and reaches standard error*.

Placed after every keep-set and removal assertion and before the two abandon arrangements, which is the ordering `verify.yml`'s header already declares load-bearing — a refused image is still on the host afterwards, so an assertion above this point could read the fixture's survival as a keep-set outcome, and an abandoning run below it produces no removal at all.

**The count is asserted as a delta of one across the two bracketing runs, never as a literal.** This host refuses a second identity this change did not arrange: from its second run onward the build base is an untagged image with dependent children, and the runtime rejects removing it by identity. Confirmed live on the fixture host:

    conflict: unable to delete 83b2b6703a62 (cannot be forced) - image has dependent child images

A literal `refused 1` would be wrong about this host and would read as a defect in the accumulator.

**Red.** With the fixture in place and the current script: `RC 0`, `SHAPE3 0`, `REFUSED no-such-field`, no line naming the fixture, and the fixture present afterwards with two references and no tag. The run's whole report is `prune-host-images: considered 10, removed 0` — the signal-free report this change exists to remove, printed over a host that did refuse something.

### The section-3 dependency, and what happens until it lands

The arrangement step reads `MULTIREPO_REF_A` and `MULTIREPO_REF_B` from `/var/tmp/image-prune-fixtures.env`. **Those two names are this pass's contract with section 3 of `tasks.md`**, which writes the registry half of the fixture in `converge.yml` and records the two digest references. Until that section is written the arrangement fails deliberately, with a message naming the section and saying that this is the expected state while only the tests exist. Whoever writes section 3 either uses those two names or changes them in both files.

Everything else about the fixture was confirmed against the fixture host before these assertions were written, so section 3 is building to an observed shape rather than a guessed one:

- building one image, tagging it into two repository paths under the local registry, pushing both and then dropping **both build tags by name** leaves the host holding nothing for that identity — the `Deleted:` line was observed, which is `design.md` Decision 6's premise confirmed;
- pulling both references back by digest yields **one** identity with `RepoDigests` of 2, `RepoTags` of 0, held by no container;
- removing that identity by identity is rejected: `conflict: unable to delete 465df16f011c (must be forced) - image is referenced in multiple repositories`, exit 1, image still present.

## Assertion classification

**Specified** — traces to the delta's scenario or requirement text:

- the report carries three counts, over distinct identities, and the run exits zero (scenario 20, and the requirement's report clause);
- the refused count reads zero where the runtime rejected nothing (scenario 21);
- a rejected removal is counted, the identity and the reason are reported, the run still exits zero, and the image is unchanged on the host (scenario 22, and the *SHALL NOT change the run's outcome* clause);
- an invocation that succeeded without deleting the image is not counted as refused (scenario 23);
- the refused count is deduplicated by identity — carried by the delta-of-one form: the fixture is one identity and contributes exactly one.

**Derived** — no requirement fixes these, and each is stated here so it is reviewable rather than indistinguishable from the above:

- **The three counts are contiguous and in that order** (`SHAPE3`). The requirement names three counts and fixes no layout. This change's `design.md`, Decision 5, decides the count is appended rather than inserted, which is what makes every existing static quotation of the line survive; the assertion holds the implementation to that decision.
- **The refusal line carries the runtime's own text for this cause** — matched on `repositor`, in its own task, separated from the specified assertions for exactly this reason. The requirement says *the reason the runtime gave* and does not fix the wording. What the assertion discriminates is a line carrying the runtime's message from one carrying a constant the script supplies. If the pinned runtime's wording moves, correct the pattern rather than dropping the assertion.
- **The refusal line reaches standard error.** Named by this change's `proposal.md` and by `tasks.md` 2.3, not by the requirement.
- **A refusal line carries more than the identity** (`CARRIES-MORE-THAN-THE-IDENTITY`): the line has alphabetic content once the identity is struck out of it. Derived, and weaker than the assertion above on purpose — it is the one that survives a wording change.
- **`RUNTIME-CONFLICTS 0` on the first run.** An absence, and absences are weak; it supplements the field-based zero rather than carrying scenario 21 on its own.
- **The build base loses its tag and survives the first run**, and **the two-tag fixture is absent after it**. Premises of scenario 23 rather than the scenario itself: they establish that an untag-without-delete really occurred in the run whose refused count is asserted zero. Both were confirmed live; if either fails, the premise has gone and not the property, which the fail message says.
- **The fixture's four premises**: two references, no tag, one identity via both references, held by no container, and distinct from `PINNED_ID`. Each is separately sufficient to make scenario 22's assertions pass having exercised nothing. `tasks.md` 1.5 requires the first three; the container premise and the one-identity-via-both premise are this pass's own additions on the same reasoning.

**Deliberately untested** — see the four uncovered scenarios in the accounting table (11, 19, 25, 27), all pre-existing decisions. This change adds none of its own: every scenario it introduces or modifies is covered.

One further thing left deliberately unasserted: **that `removed + refused` never exceeds `considered`**, and that an identity both deleted and rejected counts as removed. The precedence rule is stated in the requirement and in `design.md` Decision 2, but in the script as written the two cannot co-occur, so no fixture in a black-box scenario can produce an identity that is both — an assertion would pass against a conforming and a non-conforming script alike. It is held by review of the implementation instead.

## Obsolete tests

One entry. It is **not a file** and **was not edited, deleted or disabled by this pass** — it is a candidate for a destructive action by whoever implements this change, and it is recorded here so that action is taken deliberately.

| Superseded test | Superseding delta | Evidence | Status |
|---|---|---|---|
| `ansible/roles/image_prune/molecule/default/verify.yml`, the task *Assert the completed run reported both counts, deduplicated by identity, and exited zero*, specifically its `SHAPE` term and the `SHAPE` line in *Run the prune once, as the completed run every assertion below reads* that produces it | The `MODIFIED` scenario *A completed run reports what it did*, which now requires three counts | The shape read is `grep -ciE 'considered[[:space:]]*[0-9]+,[[:space:]]*removed[[:space:]]*[0-9]+'` — **unanchored**, so it matches a three-field line and passes while establishing nothing about the third field. Confirmed in this pass's own run: against today's two-field line it reported `SHAPE 1` and passed, in the same play in which the new three-field read reported `SHAPE3 0`. It will keep passing after the implementation lands, guarding two fields forever. This change's `design.md`, Decision 5, names it as this change's obsolete test on exactly these grounds | **Candidate for human confirmation.** The recommended action is to strengthen `SHAPE` to match all three fields, or to delete it as subsumed by the new assertion — not to leave it as it stands |

The search for bearing tests was bounded to the dispatched test-path glob, `ansible/roles/image_prune/molecule/<scenario>/`, and to the scenario-to-test mapping in the change `prune-unreferenced-host-images-periodically`'s test-plan.md as supplied. Within that bound, **no other test bears on anything this change supersedes**: nothing else in the four scenarios matches on the report line's shape, and grepping the glob for `considered`, `removed` and `refus` finds the report reads in `default` and the `HAS-CONSIDERED` reads in `abandon-paths`, which assert the *absence* of a report line on an abandoned run and are unaffected by a third field. That is *no such test exists* within the bound, not *none was found*.

## Unresolved project questions

Recorded rather than resolved, because a dispatched subagent has no channel to ask on. Each names the assumption taken and what depends on it.

1. **The variable names the registry half of the fixture will record.** `AGENTS.md` records no convention for fixture variable names, and section 3 of `tasks.md` is not written. **Assumed:** `MULTIREPO_REF_A` and `MULTIREPO_REF_B` in `/var/tmp/image-prune-fixtures.env`, following the `PINNED_REF` form already there. **Depends on it:** every task in section 5 above. The failure is loud and self-describing, not silent.
2. **Whether the refusal line goes to standard error.** The delta's requirement text does not say; this change's `proposal.md` and `tasks.md` 2.3 do. **Assumed:** standard error. **Depends on it:** the `NAMES-FIXTURE-ON-STDERR` term of *Assert the named refusal carries the runtime's own message and reaches standard error*, which is why that term sits in a separate task from the specified assertions.
3. **The runtime's exact wording for the multiple-repositories rejection.** Observed on the pinned rig as *"image is referenced in multiple repositories"* and matched on `repositor`. **Depends on it:** the `NAMES-RUNTIME-REASON` term of the same task.
4. **Whether `ansible/scripts/run-molecule test --all` can complete on this workstation.** Not attempted; this repository's own notes record it being memory-killed. **Assumed:** continuous integration covers the `--all` path. **Depends on it:** nothing in this file — the scoped baseline and every run reported here are `-s default`.

## What the implementation must make pass

From `ansible/roles/image_prune`, `ansible/scripts/run-molecule test -s default` must reach the end of `verify.yml` with no failure. Concretely, the implementation must:

1. make the completed run's report read `considered N, removed M, refused R` — the third field appended, contiguous with the second, numeric;
2. report `refused 0` as a **field** on a run the runtime rejected nothing in, rather than omitting it;
3. count an identity as refused when one of the run's own removal invocations was rejected — read from the invocation's **exit status**, so that the build base's untag-without-delete and the two-tag fixture's first tag drop, both exiting zero, keep the first run's refused count at zero;
4. emit one line per refused identity, on standard error, naming the identity and carrying the runtime's own message;
5. leave the run's exit status at zero with refusals present, and remove nothing it did not remove before;
6. and, in `converge.yml`, build the registry half of the refusal fixture recording `MULTIREPO_REF_A` and `MULTIREPO_REF_B` — without it the arrangement step fails and everything below it is unreachable.

Provisioning note, since verification that cannot reach what it needs reports nothing useful: this working tree needed `ansible-galaxy role install -r ansible/requirements.yml -p ansible/roles` before Molecule could get past its syntax step.
