## Why

`docs/bootstrap-a-new-host.md` §6.6 tells the operator, as the check that closes the stage: **"the run shows the diff before any approval; staging converges unattended; production's job waits. Read staging's before approving production's — that is what makes staging the rehearsal rather than a second production."** That sentence is the whole argument for keeping a staging host on the converge path at all, and followed with the obvious `gh` command it cannot be carried out. **§6.6 gives no log route at all**, which is the defect stated at its full width: the section's only run-reading command is `gh run list` (in its dispatch block), so the reader is left to reach for whichever `gh` invocation seems to serve, and the one that does is not obvious.

`gh run view <run> --log` refuses while any job in the run is unfinished:

    run 34739844834 is still in progress; logs will be available when it is complete

and on a merge touching `ansible/` **both converges are jobs of one run** — not incidentally, but because the requirement *Host Configuration Is Applied by a Gated Workflow* (`openspec/specs/iac-cicd-pipeline/spec.md`) says so: "The workflow SHALL separate publishing from converging, in a single run… A converge job **per stack** SHALL declare that stack's own GitHub Environment". §4.2 describes the same shape for the Terraform apply, where two stacks' applies share one run and one of them pauses. So the run is incomplete precisely until production's converge, the thing the reader is deciding whether to approve, has already finished. `--job <id>` does not lift the refusal: it is a property of the run, not of the job. Measured on run `34739844834`, and recorded as `docs/change-queue.md` entry 82 by `correct-the-documents-against-the-tree`, which met it while following its own merge through §6.6.

**The failure mode is a misdiagnosis, not an inconvenience.** An operator who reaches for the obvious command gets a refusal that reads like a permissions problem or like their own timing error, at the one moment the document has told them to wait and read. The rehearsal is then available only to someone who already knows a route the document does not give, and the likely resolution under time pressure is to approve production's converge unread — which is the state §6.6 exists to prevent.

## What Changes

- **§6.6's check paragraph gains the route that works**, at the point where it gives the instruction: the job's id from `gh run view <run> --json jobs`, then `gh api repos/{owner}/{repo}/actions/jobs/<job id>/logs`, which serves a **completed** job's log from inside a still-running run. **Two measurements support that, and they are not the same measurement.** That the request works *while the run is unfinished* was measured by `correct-the-documents-against-the-tree`, which used it to read staging's recap while production's job was in flight, and is recorded in entry 82; what this change's authoring session re-measured is the completed-run half — run `34739844834`'s staging converge job, 912 lines, carrying the three lines §6.6 already tells the reader a healthy converge shows — which establishes the command form and nothing about timing.
- **It also names the refusal**, so a reader who reaches for `gh run view --log` first recognises the message rather than diagnosing it, and knows that `--job` does not help. Naming the wrong route is what keeps the reader from concluding the fault is theirs.
- **And the second working route: the web interface**, which streams a *running* job's log live and is therefore the one to use for production's own converge while it is happening, where the API route has nothing to serve yet.

### Not in scope

**The workflow is not touched.** Splitting the two converges into separate runs, so that staging's run completes on its own, would make `gh run view --log` work as written — and it would also undo the single-run, per-stack-job shape that *Host Configuration Is Applied by a Gated Workflow* requires, and that §6.6's own advice to read *which workflow and which job* you are approving is phrased in terms of. It is a specification change wearing a convenience's clothes. This change makes the document true of the pipeline as it stands; it does not reshape the pipeline to match a command.

**Nothing about approvals changes**, and no other stage is edited. §7.4 and stage 8 read runs too, but neither carries an instruction to read one job while another in the same run is still going, which is the specific defect here.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None, and `.openspec.yaml` therefore carries `skip_specs: true` — the established form here and the case `AGENTS.md` names for it. No requirement in `openspec/specs/` governs how an operator reads a run's output: the GitHub CLI is not named anywhere in the specifications — a grep for `gh` across `openspec/specs/` returns nothing — and the pipeline's own behaviour, which *is* specified, does not move here. One run per workflow, fanned out per stack, production's job gated on its Environment: all of it is exactly as it was, which is the point of documenting a route rather than building one.

Because the change declares no deltas, it owes no derived tests, only that the suite stays green. That is the exemption `AGENTS.md` states, used for the reason it states it.

## Impact

**Documentation.** `docs/bootstrap-a-new-host.md` §6.6, one passage.

**Records.** `docs/change-queue.md` entry 82 is deleted by the archive commit, as any entry is when its change is archived.

**Not touched.** `terraform/`, `ansible/`, `platform/`, `.github/`. No credential, no host, no pipeline — and, as a docs-only change, no path filter in any workflow matches it, so merging it converges nothing and deploys nothing.

**Verification.** The static suite and the pre-commit hooks, which establish the citation form and this repository's conventions and read no prose for truth. What carries the claim that the documented command works is the run it was measured against, cited above and re-measured here.

**Confirmation.** The addition is observable, and the change proposes an observation rather than reaching for a waiver — in two parts, because they cost different things.

The **mechanism** — a run refusing `--log` while unfinished, and the jobs API serving a finished job's log from inside it — is observable on **this change's own pull-request run**, which chains `discover`, `plan` and `validate` by `needs:` and so holds a finished job while a later one is still running. That costs nothing and is done before any waiver is considered.

The **end-to-end scenario** §6.6 describes — staging's converge read before production's approval is granted — needs a production converge in flight, which arises on a merge touching `ansible/` or on a dispatched converge of every stack. This change's own merge produces neither, and raising one is the operator's decision rather than a step this change takes to prove itself. That part alone is what may be waived, on the first waivable class, against the historical measurement entry 82 records.
