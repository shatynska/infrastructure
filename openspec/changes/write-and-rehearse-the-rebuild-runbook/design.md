## Context

See `proposal.md` for motivation. What shapes the approach is where the sequence's pieces currently live and what each of them will and will not accept.

The sequence spans four places: this repository's Terraform and Ansible, this repository's `platform/` stack, the operator's own workstation and password manager, and an application's own repository. Its steps are already written down individually — in `docs/bootstrap-a-new-host.md`'s stages, in `docs/onboard-an-application.md`'s database recipe, in `platform/README.md`'s two manual steps — and only their order and their per-step credentials are missing. So this is a collation with a rehearsal attached, not a new mechanism.

Four properties of the pipeline decide how the rehearsal can be run at all:

- **`apply.yml` has no `workflow_dispatch`.** It triggers on `push` to `main` under `terraform/**`. So destroying and recreating a server is two merges, not two button presses.
- **`main-staging`'s GitHub Environment requires no reviewer and its `pipeline.yml` sets `destroy_policy_gate: false`.** Each of those two merges applies immediately and unattended, with no label and no approval. That is deliberate — staging is disposable and a gate trained on a disposable stack teaches the operator to click through it — and it is what makes the rehearsal affordable.
- **`platform-deploy.yml` does have a `workflow_dispatch` with a `stack` input**, added for exactly this case: a rebuilt host needs its own stack redeployed and not every stack's.
- **`host-converge.yml` reaches a host over the tailnet.** A rebuilt host is on no tailnet and holds no converge key, so its first converge is a workstation run — the one time `ansible-playbook` against an existing host is correct rather than a sign that the pipeline was left unfinished.

One fact about the staging host bears on the whole exercise: `terraform/stacks/main-staging/main.tf` gives the volume `count = var.volume_enabled && var.server_enabled ? 1 : 0`. The volume has no location of its own and cannot be created unattached, so it cannot outlive a *disabled* server. That count does not turn on the server's identity, so a replacement of the server leaves the volume in the plan as an attachment whose `server_id` changes rather than as a destroy — whether the provider can carry that through without recreating the volume is a provider question this repository cannot answer from its own files. `docs/bootstrap-a-new-host.md`'s Appendix B makes an unqualified claim across both routes, and `docs/backlog.md` `exercise-the-volume-server-coupling-against-live-state` records that the coupling has never been exercised against live state.

One fact about the observer bears on it too: the stack's `PLATFORM_DEADMANSWITCH_URL` check is fed by Alertmanager's Watchdog every two minutes, so it goes overdue within minutes of the destroy and stays overdue until the platform stack is back on the rebuilt host. The rebuild disables the mechanism that would notice a rebuild.

## Goals / Non-Goals

**Goals:**

- One document a reader who has never bootstrapped this system can follow under pressure, in order, without holding another document in their head.
- A rehearsal whose finding is written into that document rather than beside it.
- A dated, durable answer to whether staging's volume survives the toggle route, scoped to that route rather than generalised past it.
- Every alarm a rebuild raises predicted in the document before the step that raises it, so none of them is read as a real failure.

**Non-Goals:**

- **Making a rebuild faster, or automating any step of it.** The deliverable is a sequence and a measurement. An automation proposed on the strength of what the rehearsal measures is a later change with the measurement in hand — which is the order this change exists to make possible.
- **Rehearsing production.** Production is never the rehearsal's subject, and no production stack file is edited by this change.
- **Closing `exercise-the-volume-server-coupling-against-live-state`.** The rehearsal observes staging's coupling. That entry is about production's, and gains a dated note rather than being deleted.
- **Changing what a rebuild costs.** Prometheus history and Grafana's UI state do not come back, and `commerce-ops`'s own PostgreSQL on production is unbacked. The runbook says so; it does not fix either.

## Decisions

### One document, and Appendix B becomes a pointer to it

`docs/bootstrap-a-new-host.md` Appendix B is where the sequence lives today. It stays as a pointer and keeps only what the bootstrap document alone can say — chiefly that a rebuild's first converge is a workstation converge and why, which is a claim about stage 6 that reads naturally where stage 6 is.

*Alternative considered: leave the procedure in Appendix B and only rehearse it.* Rejected on two grounds. The bootstrap document is read once, front to back, by someone standing something up; a rebuild is read under time pressure by someone who may not have read the bootstrap at all, and Appendix B's steps are `§`-references into a document that reader is not holding. And the drift the proposal names is what two accounts of one procedure already cost, with only one of them being maintained.

*Alternative considered: a third document holding only the rehearsal record.* Rejected — a record kept apart from the procedure it dates is a record nobody reads before following the procedure.

### The runbook covers both stacks, with `main-staging` as the worked example

Commands are written out for `main-staging`, because that is what the rehearsal ran and a command that was actually executed is worth more than a parameterised one that was not. Production's divergences are named inline at the steps where they differ: its Environment requires a reviewer, its `destroy_policy_gate` applies so the merged pull request needs the `destroy-override` label, its server carries `delete_protection` and `backups`, and it holds `commerce-ops`'s own unbacked PostgreSQL.

*Alternative considered: one document per stack.* Rejected — two documents whose steps are the same in all but five places is the drift problem again, deliberately created.

### The rehearsal takes the `server_enabled` toggle route, not a replace

Two reasons. The toggle is what the stack's own variable description names as the route — *"the only rollback for this stack that does not orphan resources"*. And the toggle is the route this repository has specified: `iac-server-lifecycle`'s scenarios and `iac-data-volumes`'s are written about it, so rehearsing it exercises specified behaviour rather than improvising past it.

*Not a reason, though it reads like one:* that `main-staging` sets `destroy_policy_gate: false`. That setting removes the `destroy-override` label requirement — it makes destructive applies on staging *easier*, not unreachable. What cannot be rehearsed on staging is the label ceremony itself, which is a production divergence the runbook must describe correctly and which no staging run can exercise. This is written down because the inverted reading is the natural one and would otherwise reach the runbook.

The consequence of the toggle route is that the volume goes with the server. **That is an answer about the toggle route and the runbook says so as one.** The replace route is not rehearsed, so nothing here licenses a general claim in either direction, and the corrected Appendix B sentence, the runbook and the dated backlog note all carry the route with the answer. The rehearsal's plan output is the evidence, and what gets recorded is what the plan showed rather than what it implies.

### The rehearsal runs against the document as merged, in a second pull request

The document merges first, and the rehearsal is then performed by following the merged text. Rehearsing a draft held in the author's head measures the author, not the document.

This is also forced: the rehearsal's two Terraform toggles only take effect on merge to `main`, so they cannot sit on the change's branch waiting to be reviewed with everything else.

The derived tests come before the document, not after it: the plan is committed, `ai-toolkit:change-test-writer` derives the module from the delta, and the document is then written to satisfy assertions it did not author. That ordering is what makes the module a check rather than a description.

So this change opens five pull requests, which is more than the workflow's floor of two and is stated rather than discovered:

1. The runbook, the Appendix B reduction, the cross-reference updates, and the static test module.
2. `server_enabled = false` on `main-staging`. Merging applies it; the server, its firewall and its volume are destroyed.
3. `server_enabled = true` again. Merging applies it; the server and volume are created afresh, with a new public IPv4 and a new volume id. The net diff of 2 and 3 over `terraform.tfvars` is zero.
4. The rehearsal record, the corrections the rehearsal found, and the dated note on `exercise-the-volume-server-coupling-against-live-state`.
5. The specification record, at archive.

### The rehearsal record has three named states, and the unrehearsed one is a sentinel

The document merges before it has been rehearsed, so the record's first state has to be one the document can hold and a check can accept. Left as blank date and duration fields, that state is indistinguishable from a record someone forgot to fill in — and the static module the same pull request adds would fail the required check, making the document unmergeable and gating the rehearsal behind a red build.

So the unrehearsed state is written out: `Last rehearsed: never`. The partially-rehearsed state is the third, added because it is the *likeliest* first outcome and the one the package would otherwise leave undefined — a run that stops at the application deploy is neither a rehearsal nor nothing.

**All three states are labelled lines, not prose, and the delta fixes their forms** — the same argument as the `Credential:` line below, applied to the record: a label is what makes an absence detectable, and a check cannot read a sentence. The `Last rehearsed:` line is present in all three states and the `Partial run:` block in exactly one, so the states are told apart by the presence of a block and the value of a line rather than by interpretation:

| State | `Last rehearsed:` | `Partial run:` block |
|---|---|---|
| Never rehearsed | `never` | absent |
| Partially rehearsed | `never` | present, with `Reached:`, `Wall clock:`, `Stopped by:` |
| Rehearsed | the date, beside `Duration:` and `Stack:` | absent |

A partial run keeping `Last rehearsed: never` is the honest reading and not a compromise: a run that did not complete rehearsed nothing. It is also what makes the discriminator between the first two states a block's presence rather than a sentence's wording.

*Alternative considered: split the static module out of pull request 1 and land it with the record.* Rejected — it leaves the document unchecked over exactly the interval in which it is most edited, and gives up the detector-fires discipline at the moment it would first pay. The sentinel is smaller and keeps coverage continuous.

*Alternative considered: forbid any partial record in the document, keeping phase timings in the change's artifacts until a complete run exists.* That satisfies the requirement as written and loses the durability the risk section wants — a change's artifacts are archived, and a runbook's reader does not read them. Three states get both.

### The observer's settings stay in Appendix A; the runbook carries the step, not the table

The runbook needs an observer phase — the checks a rebuild leaves wrong, re-read against what they should be. What it does *not* do is restate their values, because `README.md` states that the checks, their slugs and their periods and graces "are listed once, in `docs/bootstrap-a-new-host.md`'s Appendix A", and Appendix A's own table says to read them back "again after any rebuild". A second copy would falsify that claim and create exactly the drift this change exists to end.

*Alternative considered: move the table into the runbook and reduce Appendix A and README to pointers.* Rejected. That table is a register of every check this system has, workflow checks included, and two of its four rows have nothing to do with a host rebuild. A rebuild document is the wrong home for a register that a bootstrap reader needs first and an operator adding a check needs later.

**The distinction against this change's own single-account rule is the kind of content, and it is worth stating because the two look alike.** A *sequence* is followed step by step under pressure, so it must be in front of its reader and a second copy of it drifts unseen — that is Appendix B's failure. A *register of settings*, or a *recipe the sequence invokes*, is looked up; copying a lookup is what makes it stale, and citing it is how it stays true.

**The same line decides two other things the runbook might have copied, and in one of them the repository has already decided it.** *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) confines the database provisioning recipe to `docs/onboard-an-application.md` and forbids a second copy in any committed Markdown document outside `openspec/` — for this change's own reason, that "two copies of a procedure touching a credential drift, and both read as authoritative" — and `.github/tests/test_the_requirement_names_where_the_recipe_lives.py` enforces it on every pull request. A rebuild runbook is exactly a document an operator would follow, so it is inside that population. It cites the recipe with the `rotate=yes` argument named, as Appendix B does today. `platform/README.md`'s two manual steps are cited for the same reason, though only the first is mechanically caught. What the runbook keeps of each is what is genuinely sequence: that it is owed, at which point, and with which secret.

What the change does owe is the missing half of the register: Appendix A covers the prune checks and explicitly excludes the per-stack Alertmanager checks, whose intended period and grace no committed file records at all. The rehearsal's pre-state capture reads them from the observer and they are written into Appendix A — a real gain this change can claim rather than a gap it inherits, and without it the rehearsal's own "green on their correct period and grace" check has nothing to check against.

**They land as a second block, not as rows in the existing table, and the reason is the same grouping that kept the register in Appendix A at all.** That table is introduced as "the checks *it* addresses", where *it* is `HEARTBEAT_PING_KEY`, and the secret inventory above it states the ping key addresses four checks and that a ping-key rotation touches none of the Alertmanager ones. The grouping that matters there is which credential addresses the check. Adding rows to that table would make a credential-scope claim false in the one document an operator reads while holding credentials — so the new block is addressed by `PLATFORM_DEADMANSWITCH_URL`, and the paragraph that currently says "Not in this table" becomes the pointer to it.

### Each step names its credential on a labelled line

A step's credential is written on its own line introduced by a `Credential:` label, or `Credential: none`. This follows the `Reason:` convention that `## Not performed` already uses and that `.github/tests/` already checks for: a label is what makes silence detectable, which prose cannot be.

### The static tests assert the document's form, not its content

What the suite can hold is: the document exists and was read; every step declares a credential or declares it needs none; the rehearsal record is in exactly one of its three defined states; the document's internal cross-references resolve to its own headings; and Appendix B carries no second copy of the sequence. Whether a step is *right* is a question for the rehearsal, and whether a credential is the *correct* one is a question for a reviewer. Both are stated here so the module is not read as covering more than it does.

**The module is derived from the delta specification by an author other than whoever writes the document**, per this project's workflow, and against the static row of its three test commands — `python3 -m unittest discover --start-directory .github/tests`, placing files under `.github/tests/*.py`. No exemption is claimed: this change declares a delta, its scenarios are static reads of a committed file, and a module written by the document's own author is precisely the check the rule exists to prevent. The dispatch happens after the approved plan is committed and before the document is written.

The module is built on `test_the_bootstrap_documents_static_conventions.py`'s shape — offence-list helpers, a "read at all" guard class first so a check that matched nothing cannot report green, and detector-fires classes proving the matchers still match, including one per record state.

### The shared-instance maintenance window does not cover a rebuild, and the runbook says so rather than pretending

`platform/README.md`'s declaration file lives at `/var/lib/platform-maintenance/shared-postgres-window` — on the host. An application probing during a rebuild does not read `window-open`; it reads nothing, because the host it would probe is gone. So the mechanism that announces a destructive act on the shared instance cannot announce the most destructive one there is.

That gap is not closed here. It is recorded in `docs/backlog.md` as a change of its own, and the runbook's announcement step is prose addressed to the operator rather than a declaration any application can read.

## Risks / Trade-offs

**The rebuilt staging host does not come back.** → The runbook is itself the recovery, and the failure is the finding: a sequence that does not restore the host is exactly what a rehearsal exists to discover, on the stack where discovering it is cheap. Nothing in production depends on staging. Re-enabling is specified to need no reconstructed configuration, and the configuration itself is committed.

**A stale tailnet peer holds the host's name after the rebuild**, so every later converge resolves to a dead peer and fails in a way that reads as an unreachable host. → The deletion of the old machine is a numbered step placed before the first converge, not a note.

**The Tailscale auth key has expired or been burnt.** → A fresh key is a step of its own with the password manager named as where it comes from. The key is reusable and 90-day; a rebuild is when that expiry is noticed.

**`commerce-ops`'s staging deploy lives in another repository and cannot be triggered from here.** → It is an operator step. If it cannot be performed, the run lands in the *partially rehearsed* state rather than being recorded as a pass one step short.

**The rebuild pages the operator from the mechanism it just destroyed, for the whole window.** → `main-staging-alertmanager` is expected to fire and the runbook says so, with its expected duration, before the step that causes it. It is not muted and not deleted: a check muted for a rebuild is one nobody re-arms, and this repository's own documents argue at length that a red check nobody can act on is what teaches an operator to stop reading the list. What the runbook adds is the sentence that makes it actionable — that this one was predicted, and when it should clear.

**The rehearsal takes far longer than expected, or strands the operator mid-sequence.** → Each phase is timed as it completes rather than at the end, and an interrupted run lands in the record's *partially rehearsed* state — what was reached, the wall clock, what stopped it, and an explicit statement that it was not a rehearsal. A half-timed sequence recorded honestly is worth more than an untimed one, and labelling it as not-a-rehearsal is what keeps it from being read as the opposite.

**The runbook reads correctly to its author and not to a reader.** → The reviewer in `build` reads the merged document cold, and the rehearsal is performed by following the text rather than by recalling the intent. Where the text had to be interpreted, the interpretation is the correction.

### The verification baseline is a measured green run, not a remembered number

Measured in this change's own working tree on 2026-09-16, at the merge base `d0b27f5`, before any file was edited: `python3 -m unittest discover --start-directory .github/tests` ran **1475 tests** and reported `OK`, and `openspec validate --all` reported 9 passed, 0 failed. That is the figure task 5.1's check is read against. It is stated with its date and its commit because a count taken from a mid-change record — where the same number appeared beside five failures — would let a module that added nothing still pass a "count exceeds" check.

## Migration Plan

The pull-request sequence above. Rollback for pull request 1 is a revert — the document is new, and nothing depends on it. Rollback for 2 is 3, which is the sequence's own next step rather than a separate recovery. There is no state to migrate.

## Open Questions

None that block. The wall-clock cost of the sequence is unknown by construction; measuring it is the change.
