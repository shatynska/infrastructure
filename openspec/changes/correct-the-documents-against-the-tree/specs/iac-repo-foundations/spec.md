## MODIFIED Requirements

### Requirement: Source Files Cite Specifications by Path and Changes by Name

A change's planning artifacts move when the change is archived — from `openspec/changes/<name>/` to `openspec/changes/archive/<date>-<name>/` — and the archive date does not exist until archiving happens. A citation of the pre-archive path therefore cannot be written correctly in advance and breaks at the moment its change succeeds, in the same commit that proves the change worked.

Committed files outside `openspec/` SHALL cite the repository's own specifications and change records in one of two forms, chosen by what is being cited:

| What is cited | Form |
|---|---|
| A requirement | The path of the specification that holds it — `openspec/specs/<capability>/spec.md` — together with the requirement's own name |
| Rationale or history held only inside a change — its `proposal.md`, `design.md`, `test-plan.md` or `test-manifest.md` | The change's name and the artifact's name, in prose, with no path |

Archiving merges a change's delta specifications into the main specification, so the first form's path is permanent and names the requirement as it currently stands rather than as one change once proposed it. The second form has no path to break. A citation MAY additionally give a change's archived location as `openspec/changes/archive/<date>-<name>/…` once that location exists.

The first form names the requirement's post-archive home. Where a change introduces a **new** capability, archiving is what creates `openspec/specs/<capability>/spec.md`, so a citation written during that change does not resolve until the change is archived. That interval is accepted: it is bounded by the change's own lifetime, after which the path is permanent, and it is the inverse of the defect this requirement exists to remove.

No committed file outside `openspec/` SHALL contain a path naming a change's own directory under `openspec/changes/` — that is, `openspec/changes/<segment>` where `<segment>` is a change name rather than `archive`, **whether or not a further path component follows it**.

The trailing qualification is load-bearing rather than pedantic. Better than a third of the citations this requirement removes name the change and stop there — `requirement (openspec/changes/connect-platform-deploy-via-tailscale)` — and a prohibition written as `openspec/changes/<segment>/` permits every one of them. Two earlier attempts to measure this problem each undercounted it by exactly that class.

This prohibition SHALL be asserted by the executable test suite that gates every pull request, because the author of such a citation cannot detect it: the citation is correct when written, correct when reviewed, and wrong only once the change it cites has succeeded.

**A requirement named in a committed file outside `openspec/` SHALL be one that a specification under `openspec/specs/` currently holds.** A requirement's name is the first form's other half, and it rots by exactly the mechanism the paragraph above describes for the path: a later change renames the requirement, and every citation of the old name becomes wrong in the commit that archives that rename. No author or reviewer of the citation can detect it either, and the renaming change has no reason to read the files that cite what it renames.

This obligation SHALL be asserted by that same suite, over the set of names an archived change has **retired** — a name a delta specification removed and no specification currently holds. Asserting it that way rather than by parsing citations is what makes it enforceable: this repository states a requirement's name in at least four renderings, emphasised, quoted, bare and wrapped across a comment's line break, and the retired set is derivable from the archive without an author maintaining a list. A retired name that is a prefix of a name a specification currently holds SHALL NOT be reported where the longer name is what the file says.

A file MAY name a retired requirement in three cases: where the retirement itself is the subject, as a record of what was renamed or of work deliberately not done; where the file is the assertion, which must state a name in order to assert its absence; and where a change in flight has recorded the name in the queue of identified changes, until that change archives. Such a file SHALL be exempted by its own path rather than by a directory prefix, with the reason stated where the exemption is declared, and the assertion SHALL fail where an exemption names a file that no longer contains a retired name, so that an exemption cannot outlive what it excused.

**The assertion SHALL read the executable test suite's own modules**, exempting only a module that must name a retired requirement in order to assert its absence. That suite states which requirement each of its assertions traces to, in prose beside the assertion, and is therefore the densest surface in the repository on which this defect occurs; a directory-wide exemption over it would leave the majority of the defect unread while reporting a clean sweep.

That assertion is a static text match, and one rendering lies outside it: a citation split across a line break immediately after `openspec/changes/` whose change name is a single word with no hyphen. Distinguishing that from ordinary prose describing this rule is not possible by text, since a continuation line's first word is itself a valid single-word change name. Every change this repository has recorded is named in multiple hyphenated words, so the excluded rendering is the intersection of two shapes neither of which has occurred.

#### Scenario: A pull request reintroducing the pre-archive citation form is rejected
- **WHEN** a pull request adds, to a committed file outside `openspec/`, a path naming a change's own directory under `openspec/changes/`
- **THEN** the required status check SHALL fail on that pull request, naming the file, the line and the citation

#### Scenario: Archiving a change breaks no citation
- **WHEN** a change is archived and its directory moves to `openspec/changes/archive/<date>-<name>/`
- **THEN** no citation in any committed file outside `openspec/` SHALL be invalidated by the move

#### Scenario: A requirement is cited at its permanent location
- **WHEN** a committed file outside `openspec/` cites a requirement that a change introduced or modified
- **THEN** it SHALL name `openspec/specs/<capability>/spec.md` and the requirement's own name, rather than the delta specification inside the change that proposed it

#### Scenario: A change's own artifacts are out of scope
- **WHEN** a change's planning artifacts, live or archived, cite that change's own paths
- **THEN** the prohibition SHALL NOT apply to them, since they move together with what they cite

#### Scenario: A pull request naming a retired requirement is rejected
- **WHEN** a pull request leaves, in a committed file outside `openspec/` that no exemption names, a requirement name that an archived delta specification retired and that no specification under `openspec/specs/` currently holds
- **THEN** the required status check SHALL fail on that pull request, naming the file, the line and the retired name
- **AND** the report SHALL name what the requirement is called now, where a specification holds a name the archive records as its replacement — or, where that recorded replacement is itself retired, the first name in the chain the archive records that a specification currently holds

#### Scenario: A retired name surviving inside a longer live name is not reported
- **WHEN** a committed file names a requirement that a specification currently holds, and a retired name is a prefix of it
- **THEN** the assertion SHALL NOT report that file, because what it names is the live requirement

#### Scenario: A name wrapped across a comment's line break is read
- **WHEN** a committed file states a requirement name across two lines of a comment block, each line carrying the comment marker and its indentation
- **THEN** the assertion SHALL read it as the one name it is, rather than as two fragments neither of which matches

#### Scenario: An exemption that no longer excuses anything fails the check
- **WHEN** a file exempted from this assertion no longer contains any retired requirement name
- **THEN** the assertion SHALL fail, naming that exemption, so that it is deleted in the change that swept the file rather than left standing over a file it no longer describes

#### Scenario: The test suite's own citations are read
- **WHEN** a module of the executable test suite states in prose the requirement one of its assertions traces to, and that requirement has since been renamed
- **THEN** the assertion SHALL report it, the suite being exempted only for the one module that must name a retired requirement in order to assert its absence

