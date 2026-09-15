## Context

See `proposal.md` for the factual defect and its history. What this document has to settle is narrower than the correction itself: whether correcting the requirement's parenthetical, as a `MODIFIED` delta, owes a new derived test — and specifically whether it owes the one test an editor reaches for first, a standing cross-file assertion that the requirement's example list agrees with `terraform.tfvars`.

That question is not new. `refresh-readme-accuracy` (archived 2026-09-08) met the identical fact — this same row, this same wrong word, this same file — and its `design.md` decided it twice, from two different angles, without correcting the requirement. This change is the first to actually take the correction; it inherits both of that change's decisions rather than re-deriving them.

## Goals / Non-Goals

**Goals:**

- Correct the one factual error in the requirement's parenthetical, and no more.
- State explicitly why no new test is owed, so a reviewer does not have to reconstruct the argument from two other changes' artifacts.

**Non-Goals:**

- Building the cross-file assertion. See Decision 1.
- Auditing the parenthetical, or the requirement, for anything beyond the one wrong word measured in `proposal.md`. `terraform.tfvars` also carries `volume_name`, `volume_size`, `ssh_public_key` and `web_allowed_cidrs` today, none of which the parenthetical lists — it is illustrative rather than exhaustive, and making it exhaustive is a second, larger edit this entry never asked for and `refresh-readme-accuracy` Decision 2 already warns against: a list that must be edited in the same commit as every future variable is a new class of rot, not a fix to this one.

## Decisions

### 1. No new derived test — this repository has already declined the obvious one, twice, in one place

The `MODIFIED` delta's obvious derived test is "the requirement's parenthetical agrees with `terraform.tfvars`", read automatically off the changed table cell. It is not written here, on the strength of `refresh-readme-accuracy`'s own `design.md`:

- Its Decision 1 met this exact row and chose **not** to correct the requirement at all, specifically to avoid taking on this derived test — reasoning that the parenthetical is illustrative, the requirement's normative content (committed, non-secret) is untouched by the "labels" error, and taking a `MODIFIED` delta there "to drag that queued question into a documentation fix and settle it in passing, by implication" was the outcome to avoid.
- Its Decision 8 considered building the assertion itself, as a `.github/tests` check in the idiom this repository already uses for its citation-form rule, and declined it — for two reasons that still hold unchanged: it needs a requirement of its own (this repository does not enforce a convention it has not recorded a requirement for), and its scope is not obvious (a region pair, a scenario count and a workflow list are each their own cross-file assertion, and deciding all of them "inside a documentation fix would decide it badly").

Nothing here revisits either of those. This change corrects the row `refresh-readme-accuracy` chose to leave wrong, but does not adopt the derived test it declined to take on when the row was last touched, and does not build the enforcement mechanism Decision 8 left as a separate, unopened question. If that mechanism is wanted, it is proposed on its own terms, deciding its scope deliberately rather than inheriting whatever shape a one-cell correction happens to give it.

The suite this change must still keep green is the existing one: `openspec validate --all` (the delta resolves, the requirement header matches exactly) and `python3 -m unittest discover --start-directory .github/tests` (no assertion in that suite reads this table cell today, so none is expected to change).

*Alternative considered — take the derived test anyway, narrowly scoped to this one cell.* Rejected: a check that reads one table cell and not the others it sits beside (region, image, CIDRs) is arbitrary in exactly the way Decision 8 already declined to decide by implication, and the next reader finding a single-cell assertion has no way to tell it was deliberately narrow rather than accidentally so.

### 2. Fix the word, not the list

The correction drops `labels` from the parenthetical and changes nothing else in the row. See Non-Goals above for why the list is not made exhaustive.

*Alternative considered — replace `labels` with what the file does carry beyond the four words already there (`volume name`, `volume size`).* Rejected for the same reason Decision 1 above declines to widen scope: the parenthetical was never a complete enumeration, adding two words to make it more complete than before is a step toward the exhaustive-list failure mode without reaching it, and it invites the next reader to keep it exhaustive once it looks that way.

## Risks / Trade-offs

**The row can drift again** — a future stack could add a `labels` assignment, or drop `allowed_cidrs`, and nothing would catch the parenthetical going stale a second time. Accepted, on the same grounds Decision 1 gives: the normative content does not depend on the example list being current, and building a check for it is a decision this change is declining to make in either direction. This is the residual the requirement has carried since it was written and is not eliminated here.
