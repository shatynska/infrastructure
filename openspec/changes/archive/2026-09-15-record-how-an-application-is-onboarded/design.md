## Context

See proposal.md for motivation. What shapes the approach is where the material already sits and what has actually been walked.

`docs/bootstrap-a-new-host.md` stage 8 holds the procedure in four subsections: a naming rule, the infrastructure side, the database, and the application side. Two of those four have been walked recently and corrected against a real run — the infrastructure side by `onboard-commerce-ops-to-staging`, the database by `provision-commerce-ops-database-in-the-shared-instance`, which ran its recipe on both hosts, met a real network failure partway and re-ran it. The application side has not: the `commerce-ops` repository's staging deploy job, its Compose file without a PostgreSQL service and its first deploy were being built when this change was opened and had not landed.

Three other files bear on the procedure. `docs/bootstrap-a-new-host.md` §0.3 generates every key the deployment uses, including the per-application deploy key stage 8 installs, and its own §0.4 already says that key "belongs to stage 8". `docs/naming-conventions.md`, *The workstation*, is what §0.3 calls "the full list" of what a workstation holds, and it lists neither deploy key. And `.github/tests/test_the_shared_instance_has_its_first_database.py` reads the database recipe out of the bootstrap document by a path constant, requiring exactly one fenced block containing `CREATE DATABASE` in that file.

`provision-commerce-ops-database-in-the-shared-instance` is at its ship gate with a live delta on *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`), which is the requirement this change also modifies.

**One item `docs/backlog.md`'s entry records as outstanding is already delivered**, and is named here so that deleting that entry on this change's archive does not read as this change having closed it: the entry quotes stage 8.4 as saying a `production` Environment is right for an application because "it has one deploy target and no stacks", and that sentence is gone — §8.4 now reads "One Environment per deploy target, each with the reviewer that target warrants", corrected by `onboard-commerce-ops-to-staging`.

## Goals / Non-Goals

**Goals:**

- One document that an operator adding a service reads on its own, with a command and a check at every step that has one.
- Exactly one authority per fact: nothing is copied, and stage 8 keeps nothing the new document does not say.
- The safety properties of the database recipe survive the move intact, and so does the test that holds them.
- The deploy-key naming axis is decided, rather than carried as a known discrepancy for a third document to inherit.

**Non-Goals:**

- Automating the database provisioning — `docs/backlog.md` `automate-per-application-database-provisioning`, and the divergence paragraph this change leaves standing.
- The general sweep of what the host firewall gates — `docs/backlog.md` `say-what-the-host-firewall-actually-gates`. Only the statement an onboarding reader needs is written here.
- The public hostname scheme — `docs/backlog.md` `record-the-hostname-scheme`.
- Taking a deploy authorisation back — `docs/backlog.md` `revoke-an-application-s-deploy-authorisation`.
- Re-keying anything, editing any committed public key, or any change reaching a host.
- The `commerce-ops` repository's own side, over which this repository has no authority.

## Decisions

### 1. `docs/onboard-an-application.md`, and stage 8 becomes a pointer

A document named for the act, in `docs/` beside the two documents that already sit there. Stage 8 keeps its heading and its place in the bootstrap sequence — a first server does onboard its first application — and its body becomes a pointer plus the one sentence a reader of the bootstrap document needs at that point: that onboarding repeats per application and per environment while the bootstrap document does not.

*Alternative rejected:* leave stage 8 in place and write a short "adding a service" note pointing back into it. That is the shape that made this an entry: the reader who is not bootstrapping still lands in a once-per-server runbook, and the grid is still described in a document organised around one server.

### 2. Extraction preserves; new prose only where the step has been walked

The application-repository half has not been walked (Context). It moves **as it stands**, edited only where the extraction itself requires it — a cross-reference that now points across documents rather than within one. The material this change authors is the material whose steps have been walked: the database explanations, the tailnet reachability, the prune's treatment of an enumerated-but-undeployed application, and the key-comment convention.

*Alternatives rejected:* waiting for that deploy, which blocks a documentation change on another repository's work with no gain in accuracy for the four-fifths already walked; and marking the unwalked steps provisional in the document, which is text that must be maintained to stay true and which the operator's stated preference rules out. The change records in `tasks.md` which half was re-walked and which was carried over, where that fact belongs — in the record of what was done, not in the procedure someone follows.

### 3. The deploy-key axis is the **environment**, for the platform key as well as an application's

`docs/bootstrap-a-new-host.md` §0.3 spells the platform deploy key's per-target segment as the stack and an application's as the environment, and says in as many words that one of the two is wrong. The environment is right for both, and the reason is that the thing a deploy key authorises is an entry in `ansible/inventory/group_vars/<environment>.yml`: `deploy_apps` sits on the environment axis, so the file that carries a key's public half — the platform's included — is an environment's file. A filename claiming the stack would claim a narrower blast radius than the key has.

It also restores a statement `docs/naming-conventions.md` already makes and entry 51 had questioned: that the converge key is the only per-stack artefact whose name lives on a workstation. The converge key really is per stack — its private half goes into that stack's GitHub Environment — and after this the two deploy keys are per environment, so that sentence is true again rather than nearly true.

*Alternative rejected:* spelling both as the stack, which is what the platform row does today. It reads naturally because this repository has one tenant, so each environment holds exactly one stack and the two axes coincide. The committed artefact has already chosen: staging's platform entry carries the comment `deploy@platform-staging`, the environment, where §0.3's row prescribes `deploy@platform-<stack>` — so the row is falsified by the file it describes rather than merely inconsistent with its neighbour.

**Not everything about that key moves onto the environment, and the change says which.** The filename, the key comment and the `deploy_apps` entry that authorises it are per environment. The private half stays per **stack**: it lives in that stack's GitHub Environment as `PLATFORM_DEPLOY_SSH_KEY`, and `platform-deploy.yml`'s deploy job for that stack is what resolves it. Both facts are stated in one place rather than left to be inferred from a filename, because the document names that key in four sections and a reader meeting only one of them will generalise from it.

**And that coincidence is the finding this decision surfaces rather than fixes.** A second tenant in one environment gives two stacks two hosts and **one** `group_vars/production.yml`, so one `deploy_apps` list — and one deploy key authorised on both hosts, which is the invariant §0.3 states as "one leaked private half must deploy to one host". Nothing in this repository prevents it, and nothing reports it. It is a change of its own, on the inventory's group layout rather than on a filename, and it goes to `docs/backlog.md` per `AGENTS.md`'s rule on a second change surfacing.

### 4. The key-comment convention is stated; production's two entries are not re-keyed

An application's key comment is `<app>-deploy-<environment>` and the platform's is `deploy@platform-<environment>`, which is what staging's two entries already carry. Production's two — `deploy@platform` and `commerce-ops-deploy` — predate the second host and carry no environment segment. They are left as they are and said to be legacy where the convention is given.

Rewriting a committed `public_key` comment is an edit under `ansible/`, which triggers a converge of both hosts and rewrites an `authorized_keys` line on each, for a documentation change. It also buys nothing: a key is identified by its fingerprint, and `ssh-keygen -lf` against the committed public half is what §0.3 already tells a reader to compare. The comment is a label for a human reading the file, and one that says less than the others is worth a sentence, not a converge.

### 5. §0.3 stops generating the application deploy key, and the onboarding document generates it

The command moves where it is run. §0.3 keeps the four keys a deployment assembles once and gains a line saying an application's key is generated per application per environment when that application is onboarded. This is the only key in that table whose generation is not once-per-server, and §0.4 already says so.

**Removing a row falsifies the prose around it, and that prose is part of the move rather than collateral.** §0.3 counts its keys above the table ("the table below has a row for each") and places them below it ("Every platform and application key here is generated in stage 0 and not stored until stage 6 or 8"), so both sentences are settled in the same edit. The second is the more important: it is the passphrase-less-key warning, and the rule it states — generated into `~/.ssh/`, never into the checkout, because stage 4.2 runs `git add -A` — travels with the command into the onboarding document rather than staying behind with the table. A machine check that the document's `-f` targets are under `~/.ssh/` is not the same thing as an operator being told why.

The alternative — the table keeping the row and the onboarding document naming it rather than repeating it — costs the onboarding reader a jump to another document for step one. Repeating the command in both is the option this change exists to refuse: two spellings of a filename convention is the defect being fixed, not a shape to reproduce.

**The consequence is not the one it first appears to be, and the difference decides what this change owes.** `.github/tests/test_the_bootstrap_documents_static_conventions.py` asserts two things about `ssh-keygen` in that document: a floor on how many invocations it carries, and that every `-f` target is under `~/.ssh/`. The floor is 6 against 13 occurrences in the document as a whole, so removing §0.3's row leaves 12 and the floor needs no movement — lowering it would loosen a live assertion for no reason, and this change does not touch it.

What does move is the **target check's reach**. It reads one document, deliberately, and the command being moved is the one an operator runs most often: once per application per environment, passphrase-less, on the stage that precedes a `git add -A`. After the move it would sit in a file nothing reads. So this change widens that check to read both documents, keeping the *cross-reference* check scoped to the bootstrap document for the reason that module's own docstring gives — a repository-wide reference sweep would eventually go red on an archived record, which may be corrected only to say what actually happened.

**A gap that check would not close either way, recorded rather than fixed here.** `.gitignore`'s root-anchored private-key block predates the current application-key spelling: its `/*-deploy` pattern was written for `<company>-<app>-deploy`, and a key named `<company>-<app>-<environment>` matches none of its patterns. That is true today, before this change moves anything, so it is a second change surfacing and goes to `docs/backlog.md`. The platform key belongs in the same entry and is the worse shape of the two: under the environment spelling `<company>-platform-staging` is matched by `/*-platform-staging` and `<company>-platform-production` by nothing, so the block covers one environment and not the other, which is harder to notice than covering neither. The block's **comment** is corrected here, because it names a retired spelling and a key count this change changes; its **patterns** are not, because widening one is a behaviour change rather than a correction.

### 6. The recipe's test follows the recipe, and the requirement gains a scenario binding the two

`.github/tests/test_the_shared_instance_has_its_first_database.py` re-points its document constant at `docs/onboard-an-application.md` and keeps every assertion: the single fenced block, the here-document terminating at column 0, the unquoted delimiter, the four log settings, the three secret-name listings, each refusal branch, case-insensitive comparison, and `rotate` assigned inside the block. Re-pointing a test at the file its subject moved to is not weakening it; dropping an assertion is.

The delta adds one paragraph and one scenario — the document the requirement names holds the recipe, and no second committed document holds a copy of it. That is what makes the path in the requirement a checkable claim rather than a citation that rots the next time the procedure moves, and it is a static read of committed files, which puts it in the suite that already reads both sides.

**That scenario is a new obligation, not a restatement, so it owes a check nothing here writes.** Re-pointing the existing module's document constant satisfies the first half and not the second: "no second committed document holds a copy" needs a detector over committed documents that does not exist. It comes from this change's test-authoring dispatch, from the scenario, like any other derived test — and whoever writes it should know what this change measured: `platform/README.md` mentions the recipe without copying it, so a mention must not count; that same file carries a fenced `CREATE ROLE pgexporter` block, a different recipe and the likeliest false positive, which keying on `CREATE DATABASE` rather than `CREATE ROLE` excludes, as the existing module already does; and `openspec/` holds real fenced copies inside change records, so the sweep needs the same `openspec/` exclusion its sibling modules use.

**And it owes a resolution rule, which is the part the overlap makes non-obvious.** The scenario turns on what "the document this requirement names" resolves to, and the suite's own `requirement_sources()` reads the requirement from *every* live change's delta — a helper written precisely so a test is not red on the pull request implementing the change it tests. While `provision-commerce-ops-database-in-the-shared-instance` is live, that returns two documents: the one it names and the one this change names. A detector faithful to the scenario across both would require each to hold the recipe while forbidding a second copy, which nothing can satisfy — and the window is real, because this change's implementation can merge before that change archives. The rule is that the name resolves from this change's delta while **that delta** is live, and from the main specification once **this** change is archived; a live delta naming a document this change supersedes is not a source. Both clauses are written against this change's own life rather than the other's, because the expected order leaves an interval — the other change archived, this one not yet — in which the main specification still names the document the recipe has left. It is stated in `tasks.md` 3.5 so the test author has it, rather than left to be met as a red required check that reads like a defect in the move.

**The population the second half sweeps is bounded in the delta itself**, for the same reason: committed Markdown outside `openspec/`. Three classes of copy in this repository are deliberate and would otherwise breach the new obligation on the day it lands — change records under `openspec/` quoting the recipe as history, the test module's own three fenced fixtures, and a prose mention that is not a copy at all.

### 7. This change's delta is written over the in-flight one, and archives after it

`provision-commerce-ops-database-in-the-shared-instance` modifies the same requirement and is ahead. A `MODIFIED` requirement replaces its block whole, so a delta written against today's main specification would silently drop that change's paragraphs when it merged. This change's delta is therefore written against the requirement **as it is about to stand** — that change's delta text, with the document path changed and the scenario added — and this change must not archive before it. The same reasoning is already recorded in the test module that reads this requirement, which resolves it from a live change's delta in preference to the main specification.

**The gate is on the archive, and the merge is deliberately not gated with it.** The specification hazard is an archive-ordering one: a `MODIFIED` block replaces its predecessor whole, which only happens at archive. The *check* hazard, decision 6's resolution rule, is what the merge window needs, and it is closed by naming the source rather than by making this change wait on another change's ship gate — work that is otherwise independent of it, and a discipline no check enforces. Where both land in the other order anyway, nothing here breaks: the rule resolves to the main specification once merged, which is the same document.

### 8. What stays in the bootstrap document

DNS (§4.4), the secret inventory (Appendix A), the once-per-server keys (§0.3), and the Environments and branch protection a repository is given once. The onboarding document points at those and does not restate them. What it holds is everything that repeats per application or per deploy target.

**Pointing works in both directions and the outward one is swept, not enumerated from memory.** Stage 8 is reduced to a pointer; every *other* place in the tree that names a part of stage 8 is redirected to the new document. Outside `openspec/`, that is two files and eight references: three inside the bootstrap document itself (Appendix B twice, Appendix C once) and five in `docs/backlog.md`, across four entries — `upgrade-the-shared-postgres-major`, `write-and-rehearse-the-rebuild-runbook`, `automate-per-application-database-provisioning` twice, and one inside this change's own entry, which is deleted at archive and takes its reference with it. `platform/README.md` is a pointer of the same class, naming the document rather than a section.

**The two halves fail differently, which is why both are swept rather than one trusted.** A stale `§8.3` inside the bootstrap document turns the required check red at merge; the same reference inside `docs/backlog.md` is read by nothing, so it survives every gate this repository has — and two of the five carry the re-provisioning step that a rebuild and a major-version volume reset each depend on, where a pointer to a section that does not exist is met at the worst moment to meet it.

## Risks / Trade-offs

- **The extraction drops a sentence nobody notices is gone** → the removed text is diffed against the new document rather than read for a sense of completeness, and the check stated in the handoff is applied literally: stage 8 must say nothing the new document does not.
- **Removing stage 8's subsection headings orphans the references into them, and that is the live direction rather than the hypothetical one** → `test_the_bootstrap_documents_static_conventions.py` resolves `§N.N` against that document's own headings, and three references to `§8.3` sit outside stage 8: twice in Appendix B, whose rebuild path tells the operator to re-provision each application's database before its deploy, and once in Appendix C. Left alone they turn the required check red and point the rebuild runbook at a section that no longer exists. The remedy is a sweep of `§8\.\d` and `stage 8\.\d` over the whole document, tasked rather than left to the reduction, with each hit rewritten in the cross-document prose form decision 8 prescribes.
- **A pointer written across documents in `§N.N` form resolves against the wrong headings** → the same checker reads the form, not the target document, so a pointer to the new document's sections must name the file and the section in prose. The suite is run before the change is reported verified, which is what catches both directions.
- **Archiving out of order silently reverts another change's specification text** → decision 7, plus a task that reads the other change's state before this one's archive rather than assuming it.
- **The unwalked half is wrong in a way extraction preserves** → accepted, and bounded: it is wrong in the bootstrap document today, this change does not make it more wrong, and the first real deploy from the `commerce-ops` repository is what corrects it. What this change must not do is make it *look* verified.
- **Two documents now describe adjacent procedures, and a future edit lands in one** → mitigated only by the pointer and the single-authority rule, which is a convention rather than a check. The one fact with a check on both sides is the database recipe, through the scenario in decision 6.
