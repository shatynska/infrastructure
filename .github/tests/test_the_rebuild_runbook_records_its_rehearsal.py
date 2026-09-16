"""Static assertions over the rebuild runbook and its rehearsal record.

Derived from the delta specification of the OpenSpec change
`write-and-rehearse-the-rebuild-runbook` -- from its single ADDED requirement,
*A Host's Rebuild Procedure Is Recorded, and Its Rehearsal State With It*
(`openspec/specs/iac-server-lifecycle/spec.md` once that change is archived) --
by an author other than whoever writes the document, and **before the document
exists**. The path the delta sits at is not written here: a change's artifacts
move when it is archived, and this repository's citation convention is to name
the change and the artifact in prose instead.

Every assertion below is annotated **SPECIFIED** (it traces to SHALL text or to
a scenario in that delta) or **DERIVED** (it traces to that change's `design.md`
or `tasks.md`, or to a form this module had to fix in order to read the property
at all). See that change's `test-plan.md` for the scenario-to-test mapping, the
baseline, the scenarios left uncovered and why, the obsolete-test candidates,
and the interface assumptions this file took.

What situation these tests are in
---------------------------------
These are static reads of committed files: nothing here executes the behaviour
it asserts, so a green result reports only that the documents could be read and
carry the shape asserted. Two consequences, both deliberate:

- **Every check here is red at authoring**, because `docs/runbook-rebuild.md`
  does not exist. That failure establishes the document's absence and nothing
  about whether these assertions are any good. It is not a defect to repair by
  creating the file from this module.
- **Each detector is therefore also run over material this file supplies**, in
  the `...DetectorFires` classes at the foot. A check whose target happens to
  carry the asserted property passes identically to one that stopped matching,
  so the fixture-driven half is what makes the green half mean anything. Every
  matcher this module introduces is exercised there against a string that must
  match and a string that must not.

What this deliberately does not attempt
---------------------------------------
Whether a step is *right*, whether the credential named is the *correct* one,
whether a rehearsal actually began with a destroyed server and ended with a
serving host, and whether a correction was made in the step rather than beside
it -- none of those is a static read of a committed file, and none is asserted
here. They are the rehearsal's business and a reviewer's.

Two structural assumptions this module makes, so that an author meets them on
purpose rather than by accident:

1. **The rehearsal record's own labelled lines sit directly under its
   `## Rehearsal record` heading**, and the prose documenting the three states
   sits under a *following* heading. The record is read from its heading to the
   next heading of any level.
2. **A labelled line quoted as documentation is written in backticks or inside
   a fence**, which is this repository's ordinary Markdown style. That is what
   separates `Last rehearsed: never` -- the record -- from a sentence about it.
   The state classifier reads unfenced lines and refuses a line that opens with
   a backtick, so a quoted example is documentation and a bare one is a record.

These assertions live in this suite because they are a static read of committed
files, which is what that row of AGENTS.md's testing table describes. They add
no import beyond the standard library and this directory's own modules, spawn no
subprocess, and need no network call, credential, container runtime or Terraform
binary.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_the_rebuild_runbook_records_its_rehearsal.TestEveryPhaseNamesTheCredentialItNeeds \\
        .test_every_phase_carries_a_credential_line

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling import below resolve.
"""

from __future__ import annotations

import re
import unittest

from test_ci_configuration import (
    LIST_ITEM,
    ROOT,
    load_yaml,
    read_text,
    unfenced_lines,
)

# --------------------------------------------------------------------------
# What is read
# --------------------------------------------------------------------------

# SPECIFIED. The delta names this path literally: *"This repository SHALL carry
# one document ... -- `docs/runbook-rebuild.md`"*.
RUNBOOK = ROOT / "docs" / "runbook-rebuild.md"

# The second account the delta forbids, and the register it obliges. Appendix B
# held the sequence before this change; Appendix A is the one place this
# repository keeps a check's intended period and grace.
BOOTSTRAP = ROOT / "docs" / "bootstrap-a-new-host.md"

STACKS = ROOT / "terraform" / "stacks"

# The requirement the runbook derives its store classification from, cited as
# this repository's convention requires -- by capability spec path plus the
# requirement's own name, never by a change directory.
STORE_REQUIREMENT = "No Store on This Host Holds Data Requiring Backup"
STORE_REQUIREMENT_PATH = "openspec/specs/iac-safety-hardening/spec.md"


def runbook_text() -> str:
    """The runbook's text, failing the calling test where it does not exist.

    An absent document is a real failure, not something to skip: before this
    change is implemented, "the document does not exist yet" IS the expected
    result, and a skip would report that as success.
    """
    return read_text(RUNBOOK)


def stack_names() -> list[str]:
    """Every stack directory under `terraform/stacks/`, read from the tree.

    Read rather than listed, because the checks a host reports to are named for
    its stack: a third stack added without its checks' settings being recorded
    is exactly the gap the register assertion exists to catch, and a check
    carrying its own list would not see it.
    """
    return sorted(path.name for path in STACKS.iterdir() if path.is_dir())


def stacks_whose_loss_is_tolerable() -> list[str]:
    """Every stack this repository's own files declare disposable.

    DERIVED, and derived rather than listed for the reason above. The criterion
    is each stack's `pipeline.yml` `destroy_policy_gate`, whose declaration in
    `terraform/stacks/main-production/pipeline.yml` says what it means in as
    many words: *"A stack that exists to be rebuilt may set this `false`; this
    one may not."* A stack the gate applies to is one whose destruction this
    repository requires a label and a reviewer for, which is what "a stack
    carrying data or service whose loss is not tolerable" reads as in a
    committed file.
    """
    tolerable = []
    for name in stack_names():
        pipeline = STACKS / name / "pipeline.yml"
        if not pipeline.is_file():
            continue
        if load_yaml(pipeline).get("destroy_policy_gate") is False:
            tolerable.append(name)
    return tolerable


# --------------------------------------------------------------------------
# Markdown shapes
# --------------------------------------------------------------------------

HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.*\S)\s*$")

# DERIVED (tasks.md 2.1, which speaks of "phase heading"s). A phase is a
# level-2 heading whose text begins with a number, with or without a `Phase`
# prefix: `## Phase 3. Converge the host`, `## 3. Converge the host`. Level 2
# rather than any level, so that a sub-step under a phase is read as part of
# that phase rather than as a phase of its own -- a phase is the unit tasks.md
# 2.1 attaches a `Credential:` line to.
PHASE_HEADING = re.compile(r"^##\s+(?:Phase\s+)?(?P<number>\d+)[.):]?\s+\S")

# The line whose merge destroys the server. The runbook writes the toggle out
# verbatim for `main-staging` (tasks.md 2.2), and it is the only line in the
# sequence that can be pointed at as "the step that destroys the server" --
# which two of the delta's scenarios order other content against. Matched over
# the RAW text rather than over unfenced lines, because it is written inside a
# fenced snippet of `terraform.tfvars`.
DESTROY_MARKER = re.compile(r"server_enabled\s*=\s*false", re.IGNORECASE)

# A duration written as an operator would read it. Used for "for roughly how
# long" an alarm lasts, and for the period and grace a register records.
DURATION = re.compile(
    r"\b(?:\d+|a few|several|tens of|a|an)[\s-]+(?:second|minute|hour|day|week)s?\b",
    re.IGNORECASE,
)

# An ISO date, which is the only spelling this repository's records use.
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# A labelled line, in the two spellings this repository already writes them in:
# `Reason: ...` and `**Reason:** ...`, either of them optionally a list item.
# The capital opening is what keeps an ordinary URL or a `http://` inside prose
# from being read as one.
ANY_LABEL = re.compile(
    r"^(?:[-*+]\s+)?\*{0,2}(?P<label>[A-Z][A-Za-z][A-Za-z '-]{0,24})\*{0,2}\s*:(?P<value>.*)$"
)


def labelled_value(line: str, label: str) -> str | None:
    """The text a named label carries on this line, or None where the line is
    not one.

    Mirrors `test_ci_configuration.reason_text` deliberately, tolerating the
    label being a nested list item and being emphasised, because neither
    changes whether the label was given. It is NOT tolerant of a line opening
    with a backtick: `` `Credential: none` `` in a sentence is documentation
    about the form, not an instance of it, and reading it as one would let a
    document satisfy the check by describing it.
    """
    stripped = line.strip()
    item = LIST_ITEM.match(stripped)
    if item:
        stripped = item.group("text").strip()
    stripped = stripped.lstrip("*_ ")
    if not stripped.lower().startswith(label.lower()):
        return None
    rest = stripped[len(label) :].lstrip("*_ ")
    if not rest.startswith(":"):
        return None
    return rest[1:].strip().strip("*_ ").strip()


def section_body(text: str, title: re.Pattern[str], *, stop_at_any_heading: bool = False):
    """Every unfenced line under the first heading whose text matches `title`,
    up to the next heading that closes it -- one of the same or a higher level,
    or, where asked, the next heading at all.

    The heading line itself is not returned. An absent heading yields an empty
    list, which every caller reports rather than passing over.
    """
    lines, _ = unfenced_lines(text)
    collected: list[tuple[int, str]] = []
    level: int | None = None
    for number, raw in lines:
        match = HEADING.match(raw)
        if level is None:
            if match and title.search(match.group("text")):
                level = len(match.group("hashes"))
            continue
        if match and (stop_at_any_heading or len(match.group("hashes")) <= level):
            break
        collected.append((number, raw))
    return collected


def heading_line(text: str, title: re.Pattern[str]) -> int | None:
    """The line number of the first heading whose text matches `title`."""
    lines, _ = unfenced_lines(text)
    for number, raw in lines:
        match = HEADING.match(raw)
        if match and title.search(match.group("text")):
            return number
    return None


def phases(text: str) -> list[dict]:
    """Every numbered phase of the runbook, as
    `{"line", "number", "heading", "body"}`.

    `body` holds the phase's unfenced lines, up to the next level-2 heading --
    a phase's own or another section's. Fenced content is excluded on purpose:
    the properties read out of a body are prose ones, and a venue named only in
    a comment inside a command block is not the step naming where it is
    performed.
    """
    lines, _ = unfenced_lines(text)
    found: list[dict] = []
    current: dict | None = None
    for number, raw in lines:
        match = PHASE_HEADING.match(raw)
        if match:
            current = {
                "line": number,
                "number": int(match.group("number")),
                "heading": raw.strip(),
                "body": [],
            }
            found.append(current)
            continue
        if raw.startswith("## "):
            current = None
            continue
        if current is not None:
            current["body"].append((number, raw))
    return found


def destroy_step_line(text: str) -> int | None:
    """The line number of the step that destroys the server, or None."""
    for number, raw in enumerate(text.splitlines(), start=1):
        if DESTROY_MARKER.search(raw):
            return number
    return None


# --------------------------------------------------------------------------
# Scenario: *A host has to be rebuilt*
# --------------------------------------------------------------------------

# DERIVED. A floor under how many phases a sequence from a destroyed server to
# a serving host has, not a count of the ones tasks.md 2.2 enumerates -- that
# list alone names nine commands. The floor exists so that a document whose
# headings stopped parsing cannot report every check below as clean having read
# nothing.
PHASE_FLOOR = 6

# SPECIFIED. *"Each step SHALL name the credential it needs and where that
# credential is held, or SHALL state that it needs none."* The label is
# design.md's, following the `Reason:` convention this suite already checks.
CREDENTIAL_LABEL = "Credential"
NO_CREDENTIAL = "none"

# DERIVED -- the vocabulary, not the obligation. The delta requires a step to
# name WHERE its credential is held; a static read needs some set of words that
# counts as naming a place. These are the places this repository actually holds
# credentials in, plus three generic locatives so that a holder nobody
# anticipated still reads as one.
#
# This list is EXTENDED, never narrowed: where a step's credential is held
# somewhere no entry names, add that holder here in the commit that introduces
# it. Deleting an entry to make a step pass is weakening the check.
CREDENTIAL_HOLDERS = (
    "password manager",
    "vault",
    "environment",
    "repository secret",
    "workstation",
    "~/.ssh",
    "keychain",
    "held in",
    "held at",
    "held by",
)

# SPECIFIED. The delta enumerates the outside-this-repository venues itself:
# *"at the DNS provider, at the tailnet, at the heartbeat observer, in an
# application's own repository"*. Each must appear AS A STEP OF THE SEQUENCE --
# inside a numbered phase -- rather than be left to be inferred from prose
# around it.
EXTERNAL_VENUES = {
    "the DNS provider": ("dns",),
    "the tailnet": ("tailnet", "tailscale"),
    "the heartbeat observer": ("healthchecks", "heartbeat"),
    "an application's own repository": (
        "own repository",
        "own actions",
        "application's own",
    ),
}


def phases_out_of_order(text: str) -> list[str]:
    """Every phase whose number does not follow the one before it, as
    `<line>: <heading>`.

    Strictly increasing rather than contiguous-from-one: the delta requires the
    steps to be given *"in the order they are performed"*, and a document that
    inserts a `2a` or starts at `0` still does that. A number that repeats or
    goes backwards does not.
    """
    offences: list[str] = []
    previous: int | None = None
    for phase in phases(text):
        if previous is not None and phase["number"] <= previous:
            offences.append(f"{phase['line']}: {phase['heading']}")
        previous = phase["number"]
    return offences


def _credential_lines(phase: dict) -> list[tuple[int, str]]:
    return [
        (number, value)
        for number, raw in phase["body"]
        for value in [labelled_value(raw, CREDENTIAL_LABEL)]
        if value is not None
    ]


def phases_declaring_no_credential(text: str) -> list[str]:
    """Every phase carrying no `Credential:` line at all, as
    `<line>: <heading>`."""
    return [
        f"{phase['line']}: {phase['heading']}"
        for phase in phases(text)
        if not _credential_lines(phase)
    ]


def credential_lines_naming_no_holder(text: str) -> list[str]:
    """Every `Credential:` line that is empty, or that names a credential
    without saying where it is held, as `<line>: <value>`.

    `Credential: none` is conformant and is the whole point of the alternative:
    a step needing no credential says so, so that silence stays detectable.
    """
    offences: list[str] = []
    for phase in phases(text):
        for number, value in _credential_lines(phase):
            if value.rstrip(".").strip().lower() == NO_CREDENTIAL:
                continue
            if not value:
                offences.append(f"{number}: (empty)")
                continue
            if not any(holder in value.lower() for holder in CREDENTIAL_HOLDERS):
                offences.append(f"{number}: {value}")
    return offences


def external_venues_not_written_as_steps(text: str) -> list[str]:
    """Every venue outside this repository that no numbered phase names, as
    `<venue>: <what is wrong>`.

    Two findings, kept apart because they need different fixes: a venue the
    document never names at all, and one it names only outside the sequence --
    in a preamble or a failure note -- which is the *"left to be inferred"*
    the delta forbids.
    """
    whole = text.lower()
    in_phases = "\n".join(
        raw.lower() for phase in phases(text) for _, raw in phase["body"]
    )
    offences = []
    for venue, terms in sorted(EXTERNAL_VENUES.items()):
        if not any(term in whole for term in terms):
            offences.append(f"{venue}: named nowhere in the document")
        elif not any(term in in_phases for term in terms):
            offences.append(f"{venue}: named only outside the numbered phases")
    return offences


# --------------------------------------------------------------------------
# Scenario: *The procedure is also described somewhere else*
# --------------------------------------------------------------------------

APPENDIX_B = re.compile(r"^Appendix B\b", re.IGNORECASE)
APPENDIX_A = re.compile(r"^Appendix A\b", re.IGNORECASE)

# A reference to one of the bootstrap document's numbered stages, in the three
# spellings Appendix B uses today: `§6.6`, `stage 6.6`, and the bare `4.2` its
# ordered list is written in.
STAGE_REFERENCE = re.compile(r"§\s*(\d{1,2}(?:\.\d{1,2}[a-z]?)?)|\b(\d{1,2}\.\d{1,2}[a-z]?)\b")

# DERIVED. A pointer that keeps *"what only it can say"* -- that a rebuild's
# first converge is a workstation converge, and why -- legitimately names the
# two or three stages that claim is about. An ordered account of the sequence
# names nine, which is what Appendix B carries today. Four is between them, and
# is a threshold to raise deliberately rather than to slide.
MAX_STAGE_REFERENCES_IN_A_POINTER = 4

# DERIVED. The count above cannot see a sequence rewritten into prose with the
# numbers dropped, so the phrases that announce one are read too. These are
# Appendix B's own words.
SEQUENCE_PHRASES = ("in this order", "the same stages", "in order:")


def stage_references(lines) -> list[str]:
    """Every distinct stage number referred to across these lines."""
    found = set()
    for _, raw in lines:
        for match in STAGE_REFERENCE.finditer(raw):
            found.add(match.group(1) or match.group(2))
    return sorted(found)


def second_account_of_the_sequence() -> list[str]:
    """Every sign that `docs/bootstrap-a-new-host.md`'s Appendix B still holds
    a copy of the sequence rather than a pointer at the runbook."""
    body = section_body(read_text(BOOTSTRAP), APPENDIX_B)
    offences = []
    if not body:
        return ["Appendix B: no such section, so nothing was read"]
    if "runbook-rebuild.md" not in "\n".join(raw for _, raw in body):
        offences.append("Appendix B: names no pointer to `docs/runbook-rebuild.md`")
    referred = stage_references(body)
    if len(referred) > MAX_STAGE_REFERENCES_IN_A_POINTER:
        offences.append(
            f"Appendix B: refers to {len(referred)} stages ({', '.join(referred)})"
        )
    for number, raw in body:
        lowered = raw.lower()
        for phrase in SEQUENCE_PHRASES:
            if phrase in lowered:
                offences.append(f"{number}: announces a sequence -- {phrase!r}")
    return offences


# --------------------------------------------------------------------------
# The rehearsal record, and its three states
# --------------------------------------------------------------------------

RECORD_HEADING = re.compile(r"^Rehearsal record\b", re.IGNORECASE)

LAST_REHEARSED = "Last rehearsed"
PARTIAL_RUN = "Partial run"
NEVER = "never"

# SPECIFIED, each by name. The rehearsed state's lines, and the partial state's
# block, are enumerated in the delta.
REHEARSED_LINES = ("Duration", "Stack")
PARTIAL_LINES = ("Reached", "Wall clock", "Stopped by")

# DERIVED -- the label, not the obligation. *"The rehearsal record SHALL still
# name what was corrected"*, and the delta requires each state to be expressed
# *"in labelled lines rather than in prose"* because *"a label is what makes an
# absence detectable, and prose cannot be read by a check"*. It fixes no
# spelling for this one, so this module fixes `Corrected:`. `Corrected: none`
# is conformant: a rehearsal that found nothing wrong says so.
CORRECTED = "Corrected"

# `Partial run:` introduces a block, so its own value is allowed to be empty.
# Every other labelled line in the record carrying an empty value is the blank
# field the delta forbids.
BLOCK_LABELS = (PARTIAL_RUN,)


def record_lines(text: str) -> list[tuple[int, str]]:
    """The rehearsal record's own lines: from its heading to the next heading
    of any level.

    Any level, so that the prose documenting the three states -- which tasks.md
    2.6 requires the document to carry -- sits under a heading of its own and
    is not read as a second record.
    """
    return section_body(text, RECORD_HEADING, stop_at_any_heading=True)


def _labelled(lines, label: str) -> list[tuple[int, str]]:
    return [
        (number, value)
        for number, raw in lines
        for value in [labelled_value(raw, label)]
        if value is not None
    ]


def record_state(text: str) -> str | None:
    """Which of the three states the record is in -- `never`, `partial`,
    `rehearsed` -- or None where it is in none of them.

    The states are told apart exactly as the delta says they are: by the value
    of the `Last rehearsed:` line and by the presence of the `Partial run:`
    block, never by interpretation of prose.
    """
    lines = record_lines(text)
    rehearsed = _labelled(lines, LAST_REHEARSED)
    if len(rehearsed) != 1:
        return None
    value = rehearsed[0][1].rstrip(".").strip().lower()
    partial = _labelled(lines, PARTIAL_RUN)
    if value == NEVER:
        return "partial" if partial else "never"
    if partial:
        return None
    return "rehearsed" if ISO_DATE.search(rehearsed[0][1]) else None


def record_offences(text: str) -> list[str]:
    """Everything wrong with the rehearsal record, as `<line>: <what>`, or a
    single entry where the record is in none of its three states."""
    lines = record_lines(text)
    if not lines:
        return ["Rehearsal record: no such section, so nothing was read"]

    offences: list[str] = []
    rehearsed = _labelled(lines, LAST_REHEARSED)
    partial = _labelled(lines, PARTIAL_RUN)

    if not rehearsed:
        offences.append("Rehearsal record: carries no `Last rehearsed:` line")
    elif len(rehearsed) > 1:
        offences.append(
            "Rehearsal record: carries "
            f"{len(rehearsed)} `Last rehearsed:` lines, at "
            + ", ".join(str(number) for number, _ in rehearsed)
        )
    if len(partial) > 1:
        offences.append(
            "Rehearsal record: carries "
            f"{len(partial)} `Partial run:` blocks, at "
            + ", ".join(str(number) for number, _ in partial)
        )

    for number, raw in lines:
        stripped = raw.strip()
        if stripped.startswith("`") or stripped.startswith("|"):
            continue
        match = ANY_LABEL.match(stripped)
        if not match:
            continue
        if match.group("label").strip() in BLOCK_LABELS:
            continue
        if not match.group("value").strip().strip("*_ "):
            offences.append(f"{number}: `{match.group('label')}:` carries no value")

    state = record_state(text)
    if state is None:
        offences.append(
            "Rehearsal record: in none of its three states -- a `Last "
            "rehearsed:` line reading `never` with no `Partial run:` block, the "
            "same with one, or an ISO date beside `Duration:` and `Stack:` and "
            "no block"
        )
        return sorted(set(offences), key=_offence_order)

    if state == "partial":
        present = {label for label in PARTIAL_LINES if _labelled(lines, label)}
        for label in PARTIAL_LINES:
            if label not in present:
                offences.append(
                    f"{partial[0][0]}: the `Partial run:` block carries no "
                    f"`{label}:` line"
                )
    if state == "rehearsed":
        for label in (*REHEARSED_LINES, CORRECTED):
            if not _labelled(lines, label):
                offences.append(
                    f"{rehearsed[0][0]}: a rehearsed record carries no "
                    f"`{label}:` line"
                )
    return sorted(set(offences), key=_offence_order)


def _offence_order(entry: str) -> tuple[int, str]:
    head = entry.split(":", 1)[0]
    return (int(head), entry) if head.isdigit() else (10**9, entry)


def rehearsal_stacks_whose_loss_is_not_tolerable(text: str) -> list[str]:
    """Every `Stack:` line in a rehearsed record naming a stack this repository
    does not declare disposable, as `<line>: <value>`.

    Only in the rehearsed state: a record that names no completed rehearsal
    makes no claim about a stack.
    """
    if record_state(text) != "rehearsed":
        return []
    tolerable = stacks_whose_loss_is_tolerable()
    offences = []
    for number, value in _labelled(record_lines(text), "Stack"):
        named = [stack for stack in stack_names() if stack in value]
        if not named:
            offences.append(f"{number}: {value or '(empty)'} -- names no stack")
        elif not all(stack in tolerable for stack in named):
            offences.append(f"{number}: {value}")
    return offences


# --------------------------------------------------------------------------
# The alarms a rebuild raises, and the observer phase owed afterwards
# --------------------------------------------------------------------------

# A check a host of this repository reports to. The stack prefix is resolved
# against the tree rather than spelled here, for the reason `stack_names` gives.
CHECK_JOBS = ("alertmanager", "prune-host-images")


def check_names() -> list[str]:
    return [f"{stack}-{job}" for stack in stack_names() for job in CHECK_JOBS]


def check_mentions(lines) -> list[tuple[int, str]]:
    """Every (line number, check name) these lines name."""
    found = []
    for number, raw in lines:
        for name in check_names():
            if name in raw:
                found.append((number, name))
    return found


def alarms_not_predicted_before_the_destroy(text: str) -> list[str]:
    """Every way the document fails to say, before the step that destroys the
    server, which alarms the rebuild will raise and for roughly how long."""
    destroy = destroy_step_line(text)
    if destroy is None:
        return ["the step that destroys the server was not found"]
    lines, _ = unfenced_lines(text)
    before = [(number, raw) for number, raw in lines if number < destroy]
    named = check_mentions(before)
    if not named:
        return [
            f"{destroy}: no check this host reports to is named before the "
            "step that destroys the server"
        ]
    offences = []
    alertmanager = [entry for entry in named if entry[1].endswith("-alertmanager")]
    if not alertmanager:
        offences.append(
            f"{destroy}: the dead-man's-switch check the rebuild silences is "
            "not named before the step that silences it"
        )
    passage = "\n".join(
        raw for number, raw in before if number >= min(number for number, _ in named)
    )
    if not DURATION.search(passage):
        offences.append(
            f"{destroy}: the alarms are named before the destroy step but for "
            "no stated duration"
        )
    return offences


def observer_phase(text: str) -> dict | None:
    """The phase in which the steps owed at the heartbeat observer are
    performed: the first phase after the destroy step whose body names the
    observer."""
    destroy = destroy_step_line(text)
    if destroy is None:
        return None
    terms = EXTERNAL_VENUES["the heartbeat observer"]
    for phase in phases(text):
        if phase["line"] < destroy:
            continue
        body = "\n".join(raw.lower() for _, raw in phase["body"])
        if any(term in body for term in terms):
            return phase
    return None


def observer_phase_omissions(text: str) -> list[str]:
    """Everything the observer phase owes and does not carry."""
    phase = observer_phase(text)
    if phase is None:
        return [
            "no phase after the destroy step names the heartbeat observer as "
            "where its steps are performed"
        ]
    body = "\n".join(raw for _, raw in phase["body"])
    lowered = body.lower()
    offences = []
    named = {name for _, name in check_mentions(phase["body"])}
    for job in CHECK_JOBS:
        if not any(name.endswith(f"-{job}") for name in named):
            offences.append(
                f"{phase['line']}: the observer phase names no `-{job}` check "
                "of this host individually"
            )
    for setting in ("period", "grace"):
        if setting not in lowered:
            offences.append(
                f"{phase['line']}: the observer phase does not re-read each "
                f"check against its intended {setting}"
            )
    return offences


# --------------------------------------------------------------------------
# The register: one place, cited rather than copied
# --------------------------------------------------------------------------

# DERIVED. A check's entry in the register and its period and grace are on the
# same table row, or within the labelled lines immediately under its name. Four
# lines is the window, which covers both shapes without reaching the next
# check's entry.
REGISTER_WINDOW = 4


def checks_whose_settings_the_register_does_not_record() -> list[str]:
    """Every check a host of this repository reports to whose intended period
    and grace `docs/bootstrap-a-new-host.md`'s Appendix A does not record."""
    body = section_body(read_text(BOOTSTRAP), APPENDIX_A)
    if not body:
        return ["Appendix A: no such section, so nothing was read"]
    text_by_line = {number: raw for number, raw in body}
    offences = []
    for name in check_names():
        at = next((number for number, raw in body if name in raw), None)
        if at is None:
            offences.append(f"{name}: named nowhere in Appendix A")
            continue
        window = "\n".join(
            text_by_line.get(number, "") for number in range(at, at + REGISTER_WINDOW + 1)
        )
        if len(DURATION.findall(window)) < 2:
            offences.append(f"{at}: {name} is named with no period and grace beside it")
    return offences


def register_values_copied_into(text: str) -> list[str]:
    """Every place the runbook carries a second copy of the register's values
    rather than citing where they are kept, as `<line>: <line text>`.

    Two shapes, because both would go stale: a table of its own whose columns
    are the period and the grace, and a `Period:`/`Grace:` labelled line
    carrying a duration. Saying that an alarm clears *"within minutes"* is
    neither, and is what the alarm scenario requires the document to say.
    """
    offences = []
    for number, raw in unfenced_lines(text)[0]:
        lowered = raw.lower()
        if raw.lstrip().startswith("|") and "period" in lowered and "grace" in lowered:
            offences.append(f"{number}: {raw.strip()}")
            continue
        for label in ("Period", "Grace"):
            value = labelled_value(raw, label)
            if value and DURATION.search(value):
                offences.append(f"{number}: {raw.strip()}")
    return offences


# --------------------------------------------------------------------------
# What a rebuild loses, said before the step that loses it
# --------------------------------------------------------------------------

# SPECIFIED: the delta obliges the document to name *"any store that
# requirement records as unmet"*. That requirement records exactly one --
# `commerce-ops`'s own PostgreSQL, on the production host -- and states it in as
# many words: *"this requirement SHALL be read as unmet in that one respect"*.
UNMET_STORE = "commerce-ops"

# DERIVED (proposal.md's Impact, design.md's Non-Goals): the two stores whose
# contents a rebuild does not bring back on either stack.
STORES_THAT_DO_NOT_COME_BACK = ("prometheus", "grafana")


def losses_not_stated_before_the_destroy(text: str) -> list[str]:
    """Everything the document owes its reader before the step that destroys
    the server and does not say there."""
    destroy = destroy_step_line(text)
    if destroy is None:
        return ["the step that destroys the server was not found"]
    before = "\n".join(
        raw for number, raw in unfenced_lines(text)[0] if number < destroy
    )
    lowered = before.lower()
    offences = []
    if STORE_REQUIREMENT not in before:
        offences.append(
            f"{destroy}: *{STORE_REQUIREMENT}* is not cited before the destroy step"
        )
    if STORE_REQUIREMENT_PATH not in before:
        offences.append(
            f"{destroy}: the citation of that requirement does not carry its "
            f"capability spec path, `{STORE_REQUIREMENT_PATH}`"
        )
    if UNMET_STORE not in lowered:
        offences.append(
            f"{destroy}: the store that requirement records as unmet "
            f"(`{UNMET_STORE}`'s own PostgreSQL) is not named before the "
            "destroy step"
        )
    else:
        production = [
            stack for stack in stack_names() if stack not in stacks_whose_loss_is_tolerable()
        ]
        if production and not any(stack in before for stack in production):
            offences.append(
                f"{destroy}: the unmet store is named without the stack it is "
                f"unmet on ({', '.join(production)})"
            )
    for store in STORES_THAT_DO_NOT_COME_BACK:
        if store not in lowered:
            offences.append(
                f"{destroy}: `{store}`, whose contents a rebuild does not "
                "restore, is not named before the destroy step"
            )
    return offences


# --------------------------------------------------------------------------
# A check that read nothing reports success having verified nothing, so what
# every class below reads is asserted before what any of them concludes.
# --------------------------------------------------------------------------


class TestTheRunbookIsReadAtAll(unittest.TestCase):
    """The document these assertions read exists, parses into the shapes they
    resolve against, and carries the two landmarks the ordering assertions are
    written against.

    Until `docs/runbook-rebuild.md` is written, every test in this class fails
    because the document is absent. That failure establishes the document's
    absence and nothing else -- see this module's docstring.
    """

    def test_the_runbook_exists_and_is_not_empty(self) -> None:
        text = runbook_text()
        self.assertGreater(
            len(text.strip()),
            0,
            f"{RUNBOOK.relative_to(ROOT)} is empty. Every check in this module "
            "reads it, so an empty document would report a clean sweep having "
            "read nothing",
        )

    def test_the_runbook_leaves_no_code_fence_open(self) -> None:
        """An unterminated fence hides the whole remainder of the file from
        every unfenced sweep below -- a clean report reached by the one route
        that means nothing was read."""
        _, left_open = unfenced_lines(runbook_text())
        self.assertFalse(
            left_open,
            f"{RUNBOOK.relative_to(ROOT)} leaves a code fence open at end of "
            "file, so everything after it is invisible to the checks below",
        )

    def test_the_runbook_is_written_in_numbered_phases(self) -> None:
        found = phases(runbook_text())
        self.assertGreaterEqual(
            len(found),
            PHASE_FLOOR,
            f"{RUNBOOK.relative_to(ROOT)} parses as {len(found)} numbered "
            f"phase(s), fewer than the floor of {PHASE_FLOOR}. The credential "
            "check and the venue check both resolve against that list, so a "
            "document whose headings stopped parsing would report both clean "
            "having read nothing",
        )

    def test_the_step_that_destroys_the_server_is_found(self) -> None:
        """Two of the delta's scenarios order content *before* this step, so a
        marker that stopped matching would make both checks vacuous."""
        self.assertIsNotNone(
            destroy_step_line(runbook_text()),
            f"{RUNBOOK.relative_to(ROOT)} carries no line setting "
            "`server_enabled = false`, which is the step that destroys the "
            "server and the point the alarm and store warnings must precede",
        )

    def test_the_rehearsal_record_section_is_found(self) -> None:
        self.assertTrue(
            record_lines(runbook_text()),
            f"{RUNBOOK.relative_to(ROOT)} carries no `## Rehearsal record` "
            "section, so the state check below has nothing to classify",
        )

    def test_the_bootstrap_documents_two_appendices_are_found(self) -> None:
        """Appendix B is where a second copy of the sequence would live;
        Appendix A is the one place the register lives. Both are read by name,
        and a renamed appendix would make both checks pass vacuously."""
        text = read_text(BOOTSTRAP)
        for label, pattern in (("Appendix A", APPENDIX_A), ("Appendix B", APPENDIX_B)):
            with self.subTest(appendix=label):
                self.assertIsNotNone(
                    heading_line(text, pattern),
                    f"{BOOTSTRAP.relative_to(ROOT)} carries no {label} heading. "
                    "The checks that read it resolve against that heading, so "
                    "a renamed appendix reports clean having read nothing",
                )

    def test_the_stacks_are_enumerated_from_the_tree(self) -> None:
        """Every check name, and the tolerable-loss criterion, is composed from
        this list. An empty one would make several checks below vacuous."""
        self.assertGreaterEqual(len(stack_names()), 2, stack_names())
        self.assertTrue(stacks_whose_loss_is_tolerable(), stack_names())


# --------------------------------------------------------------------------
# Scenario: *A host has to be rebuilt*
# --------------------------------------------------------------------------


class TestTheRunbookGivesTheStepsInTheOrderTheyArePerformed(unittest.TestCase):
    """SPECIFIED. *"one document in this repository SHALL give the steps in the
    order they are performed"*."""

    def test_no_phase_number_repeats_or_goes_backwards(self) -> None:
        offences = phases_out_of_order(runbook_text())
        self.assertEqual(
            offences,
            [],
            f"{len(offences)} phase heading(s) in "
            f"{RUNBOOK.relative_to(ROOT)} carry a number that repeats or goes "
            "backwards. The document's whole claim is that its steps are in "
            "the order they are performed, and a reader under time pressure "
            "follows the numbers rather than the prose:\n  "
            + "\n  ".join(offences),
        )


class TestEveryPhaseNamesTheCredentialItNeeds(unittest.TestCase):
    """SPECIFIED. *"Each step SHALL name the credential it needs and where that
    credential is held, or SHALL state that it needs none."*

    The labelled line is design.md's form, for the reason the `Reason:` label
    already in this suite exists: a label is what makes an absence detectable,
    and prose cannot be read by a check.
    """

    def test_every_phase_carries_a_credential_line(self) -> None:
        offences = phases_declaring_no_credential(runbook_text())
        self.assertEqual(
            offences,
            [],
            f"{len(offences)} phase(s) in {RUNBOOK.relative_to(ROOT)} carry no "
            f"`{CREDENTIAL_LABEL}:` line. A step whose credential is unstated "
            "is one an operator discovers they cannot perform at the moment "
            "they reach it, which on a rebuild is the worst moment. Where the "
            f"step needs none, say `{CREDENTIAL_LABEL}: {NO_CREDENTIAL}` -- "
            "silence and 'none' must not look alike:\n  " + "\n  ".join(offences),
        )

    def test_every_credential_line_says_where_the_credential_is_held(self) -> None:
        offences = credential_lines_naming_no_holder(runbook_text())
        self.assertEqual(
            offences,
            [],
            f"{len(offences)} `{CREDENTIAL_LABEL}:` line(s) in "
            f"{RUNBOOK.relative_to(ROOT)} name a credential without saying "
            "where it is held. Naming the secret is not enough: an operator "
            "who does not already know where it lives is stopped exactly as "
            "hard as one who does not know it is needed. Either name the "
            "holder, or -- where this repository holds a credential somewhere "
            "`CREDENTIAL_HOLDERS` does not yet name -- add that holder to the "
            "list in the commit that introduces it:\n  " + "\n  ".join(offences),
        )


class TestEveryStepPerformedElsewhereIsWrittenAsAStep(unittest.TestCase):
    """SPECIFIED. *"A step performed outside this repository -- at the DNS
    provider, at the tailnet, at the heartbeat observer, in an application's own
    repository -- SHALL be written as a step of the sequence rather than left to
    be inferred, and SHALL name where it is performed."*"""

    def test_every_external_venue_is_named_inside_a_numbered_phase(self) -> None:
        offences = external_venues_not_written_as_steps(runbook_text())
        self.assertEqual(
            offences,
            [],
            f"{len(offences)} venue(s) outside this repository are not written "
            f"as steps of {RUNBOOK.relative_to(ROOT)}'s sequence. A step "
            "nobody wrote down is a step nobody performs -- and these are the "
            "ones a reader cannot infer from the repository, because nothing "
            "here can perform them:\n  " + "\n  ".join(offences),
        )


# --------------------------------------------------------------------------
# Scenario: *The procedure is also described somewhere else*
# --------------------------------------------------------------------------


class TestTheSequenceHasExactlyOneHome(unittest.TestCase):
    """SPECIFIED. *"That document SHALL be the only place that sequence is
    written. Another document MAY name it ... but SHALL NOT restate the
    sequence -- two accounts of one procedure drift, and the drift is invisible
    until the procedure is next needed."*

    Read against Appendix B specifically, which is where the sequence lived
    before this change and where the drift this change cites was measured.
    """

    def test_appendix_b_names_the_runbook_and_restates_no_sequence(self) -> None:
        offences = second_account_of_the_sequence()
        self.assertEqual(
            offences,
            [],
            f"{len(offences)} sign(s) that {BOOTSTRAP.relative_to(ROOT)}'s "
            "Appendix B still carries an account of the rebuild sequence "
            "rather than a pointer at it. Two accounts of one procedure drift, "
            "and only one of them is maintained -- which is how the appendix "
            "came to claim of 'a rebuild' something that is true of one route "
            "and false of the other. Keep what only the bootstrap document can "
            "say, and hand the sequence over:\n  " + "\n  ".join(offences),
        )


# --------------------------------------------------------------------------
# The rehearsal record's three states
# --------------------------------------------------------------------------


class TestTheRehearsalRecordIsInExactlyOneOfThreeStates(unittest.TestCase):
    """SPECIFIED. *"The document SHALL carry a rehearsal record, and that record
    SHALL be in exactly one of three states ... The record SHALL carry a `Last
    rehearsed:` line in every state, and a `Partial run:` block in exactly
    one."*

    This one test covers four scenarios at once, because they are four states
    of one classifier: a rehearsal performed, one never performed, a run that
    stopped before the host was serving, and a later run replacing a partial
    record rather than accumulating beside it. The last is read as the record
    carrying exactly one `Last rehearsed:` line and at most one `Partial run:`
    block -- accumulation is what more than one of either IS.
    """

    def test_the_record_is_in_one_of_its_three_states_and_carries_that_states_lines(
        self,
    ) -> None:
        offences = record_offences(runbook_text())
        self.assertEqual(
            offences,
            [],
            f"{len(offences)} defect(s) in {RUNBOOK.relative_to(ROOT)}'s "
            "rehearsal record. The three states are told apart by the value of "
            "one line and the presence of one block, so that a reader can tell "
            "a procedure that has been exercised from one that has merely been "
            "written -- and the never-state is written out as "
            f"`{LAST_REHEARSED}: {NEVER}` rather than left blank, because a "
            "blank field is indistinguishable from one someone forgot to fill "
            "in and the two mean opposite things:\n  " + "\n  ".join(offences),
        )


class TestARehearsalNamesAStackWhoseLossIsTolerable(unittest.TestCase):
    """SPECIFIED. *"A rehearsal SHALL be performed against a stack whose loss is
    tolerable, and SHALL NOT be performed against a stack carrying data or
    service whose loss is not. The stack it was performed against SHALL be named
    in the record."*

    Which stacks those are is read from each stack's own `pipeline.yml` rather
    than listed here -- see `stacks_whose_loss_is_tolerable`.
    """

    def test_a_rehearsed_record_names_a_disposable_stack(self) -> None:
        offences = rehearsal_stacks_whose_loss_is_not_tolerable(runbook_text())
        self.assertEqual(
            offences,
            [],
            f"{len(offences)} `Stack:` line(s) in "
            f"{RUNBOOK.relative_to(ROOT)}'s rehearsal record name a stack this "
            "repository does not declare disposable. A rehearsal destroys the "
            "host it runs against; the stacks it may run against are the ones "
            "whose `pipeline.yml` sets `destroy_policy_gate: false`, which is "
            "that field's own stated meaning. A rehearsal recorded against any "
            "other stack is either a misrecorded stack name or a rehearsal "
            "that should not have happened:\n  " + "\n  ".join(offences),
        )


# --------------------------------------------------------------------------
# Scenario: *A rebuild silences the host's own reporters*
# --------------------------------------------------------------------------


class TestTheAlarmsARebuildRaisesArePredictedBeforeTheyFire(unittest.TestCase):
    """SPECIFIED. *"the document SHALL say, before that step, which alarms the
    rebuild is expected to raise and for roughly how long"* -- because *"an
    alarm that fires because a rebuild is in progress and that no step predicted
    is indistinguishable from a real one, and is what teaches an operator to
    stop reading the list."*"""

    def test_the_expected_alarms_are_named_before_the_destroy_step(self) -> None:
        offences = alarms_not_predicted_before_the_destroy(runbook_text())
        self.assertEqual(
            offences,
            [],
            f"{len(offences)} defect(s) in what {RUNBOOK.relative_to(ROOT)} "
            "says before it destroys the server. The rebuild disables the "
            "mechanism that would notice a rebuild, and the operator is paged "
            "by it for the whole window. Naming the check afterwards is too "
            "late; naming it without a duration leaves the operator unable to "
            "tell a predicted alarm from one that has not cleared:\n  "
            + "\n  ".join(offences),
        )


class TestTheObserverPhaseIsOwedOnceTheHostIsBack(unittest.TestCase):
    """SPECIFIED. *"It SHALL also carry the steps owed at the external observer
    once the host is back, naming that observer as where they are performed, and
    including re-reading each of that host's checks against its intended period
    and grace -- a check re-created by its own first ping carries the observer's
    default rather than the one the reporter needs."*"""

    def test_a_phase_after_the_destroy_step_names_the_observer_and_its_checks(
        self,
    ) -> None:
        offences = observer_phase_omissions(runbook_text())
        self.assertEqual(
            offences,
            [],
            f"{len(offences)} defect(s) in {RUNBOOK.relative_to(ROOT)}'s "
            "observer phase. A check re-created by its own first ping carries "
            "the vendor's default period, which calls a healthy weekly job "
            "overdue within a day -- so a host that is serving again can still "
            "leave two checks wrong, and nothing on the host says so:\n  "
            + "\n  ".join(offences),
        )


# --------------------------------------------------------------------------
# Scenario: *A check's intended settings are recorded nowhere*
# --------------------------------------------------------------------------


class TestEveryCheckAHostReportsToHasItsSettingsRecordedOnce(unittest.TestCase):
    """SPECIFIED. *"Every check a host of this repository reports to SHALL have
    its intended period and grace recorded in one place in this repository, and
    the rebuild sequence SHALL cite that place rather than copy the values into
    itself."*

    The one place is `docs/bootstrap-a-new-host.md`'s Appendix A, which
    `README.md` already says the values are listed once in. A check whose
    intended settings are recorded nowhere cannot be verified after a rebuild at
    all, so recording them is part of satisfying the requirement rather than a
    precondition of it -- which is why this test reads the register rather than
    only the runbook.
    """

    def test_the_register_records_a_period_and_a_grace_for_every_check(self) -> None:
        offences = checks_whose_settings_the_register_does_not_record()
        self.assertEqual(
            offences,
            [],
            f"{len(offences)} check(s) a host of this repository reports to "
            f"have no intended period and grace recorded in "
            f"{BOOTSTRAP.relative_to(ROOT)}'s Appendix A. After a rebuild the "
            "question 'are the checks back on their correct settings' then has "
            "no answer in any committed file, and the observer's default is "
            "what the check silently keeps:\n  " + "\n  ".join(offences),
        )


class TestTheRunbookCitesTheRegisterRatherThanCopyingIt(unittest.TestCase):
    """SPECIFIED. *"the rebuild sequence SHALL cite that place rather than carry
    a second copy of the values."* A sequence is followed step by step and must
    be in front of its reader; a register of settings is looked up, and a copied
    lookup is what goes stale."""

    def test_the_runbook_names_the_register_it_reads_against(self) -> None:
        text = runbook_text()
        for cited in ("Appendix A", "bootstrap-a-new-host.md"):
            with self.subTest(cited=cited):
                self.assertIn(
                    cited,
                    text,
                    f"{RUNBOOK.relative_to(ROOT)} does not cite "
                    f"`{cited}`. The checks' intended period and grace are "
                    "listed once, and the document that re-reads them after a "
                    "rebuild has to say where that once is",
                )

    def test_the_runbook_carries_no_second_copy_of_the_values(self) -> None:
        offences = register_values_copied_into(runbook_text())
        self.assertEqual(
            offences,
            [],
            f"{len(offences)} place(s) in {RUNBOOK.relative_to(ROOT)} carry a "
            "period or a grace value rather than citing where they are kept. "
            "`README.md` states those values are listed once, in the bootstrap "
            "document's Appendix A; a second copy falsifies that sentence and "
            "then drifts from it, which is the failure this whole change "
            "exists to end:\n  " + "\n  ".join(offences),
        )


# --------------------------------------------------------------------------
# Scenario: *A store the rebuilt host held does not come back*
# --------------------------------------------------------------------------


class TestWhatARebuildLosesIsStatedBeforeItIsLost(unittest.TestCase):
    """SPECIFIED. *"For the stores the rebuilt host held, the document SHALL
    state which contents come back and which do not, deriving that from* No
    Store on This Host Holds Data Requiring Backup *... and SHALL name any store
    that requirement records as unmet -- a store whose loss a rebuild makes real
    is the one fact a rebuild's operator most needs before starting, and the one
    no green run will report."*"""

    def test_the_losses_are_named_before_the_step_that_destroys_the_server(
        self,
    ) -> None:
        offences = losses_not_stated_before_the_destroy(runbook_text())
        self.assertEqual(
            offences,
            [],
            f"{len(offences)} thing(s) {RUNBOOK.relative_to(ROOT)} owes its "
            "reader before the destroy step and does not say there. A store "
            "whose loss a rebuild makes real cannot be reported by any run, "
            "green or red, and the moment to learn of it is before the merge "
            "that destroys the server rather than after:\n  "
            + "\n  ".join(offences),
        )


# --------------------------------------------------------------------------
# The repository's own documents will satisfy every check above, and would
# satisfy them just as readily if a matcher had stopped matching. Each detector
# is therefore also run over material written here to falsify it.
# --------------------------------------------------------------------------


class TestThePhaseAndCredentialDetectorsFire(unittest.TestCase):
    PHASED = (
        "# Rebuilding a host\n\n"
        "## 1. Destroy the server\n\n"
        "Credential: the staging Vault password, from the password manager.\n\n"
        "## 2. Re-create it\n\n"
        "Credential: none\n\n"
    )

    def test_a_numbered_phase_is_found_with_its_body(self) -> None:
        found = phases(self.PHASED)
        self.assertEqual([phase["number"] for phase in found], [1, 2], found)
        self.assertTrue(any("Vault" in raw for _, raw in found[0]["body"]))

    def test_a_phase_prefixed_with_the_word_phase_is_found_too(self) -> None:
        self.assertEqual(
            [phase["number"] for phase in phases("## Phase 4. Converge\n\nBody\n")],
            [4],
        )

    def test_a_sub_step_is_not_read_as_a_phase_of_its_own(self) -> None:
        found = phases("## 1. Destroy\n\n### 1.2 Toggle the flag\n\nCredential: none\n")
        self.assertEqual([phase["number"] for phase in found], [1], found)
        self.assertEqual(credential_lines_naming_no_holder("## 1. D\n\nCredential: none\n"), [])

    def test_a_repeated_phase_number_is_reported(self) -> None:
        offences = phases_out_of_order("## 1. One\n\n## 1. One again\n")
        self.assertEqual(len(offences), 1, offences)

    def test_phases_in_order_are_not_reported(self) -> None:
        self.assertEqual(phases_out_of_order(self.PHASED), [])

    def test_a_phase_with_no_credential_line_is_reported(self) -> None:
        offences = phases_declaring_no_credential("## 1. Destroy\n\nJust prose.\n")
        self.assertEqual(len(offences), 1, offences)
        self.assertIn("Destroy", offences[0])

    def test_a_phase_with_a_credential_line_is_not_reported(self) -> None:
        self.assertEqual(phases_declaring_no_credential(self.PHASED), [])

    def test_a_credential_naming_no_holder_is_reported(self) -> None:
        offences = credential_lines_naming_no_holder(
            "## 1. Deploy\n\nCredential: `PLATFORM_DEPLOY_HOST`\n"
        )
        self.assertEqual(len(offences), 1, offences)

    def test_an_empty_credential_line_is_reported(self) -> None:
        offences = credential_lines_naming_no_holder("## 1. Deploy\n\nCredential:\n")
        self.assertEqual(offences and offences[0].endswith("(empty)"), True, offences)

    def test_a_credential_line_naming_a_holder_is_not_reported(self) -> None:
        self.assertEqual(credential_lines_naming_no_holder(self.PHASED), [])

    def test_an_emphasised_credential_label_is_read(self) -> None:
        self.assertEqual(
            labelled_value("**Credential:** none", CREDENTIAL_LABEL), "none"
        )

    def test_a_quoted_credential_label_is_not_read_as_one(self) -> None:
        """A sentence about the form is documentation, not an instance of it --
        otherwise a document could satisfy the check by describing it."""
        self.assertIsNone(
            labelled_value("`Credential: none` is what a step needing none says.", CREDENTIAL_LABEL)
        )

    def test_a_venue_named_only_outside_the_phases_is_reported(self) -> None:
        document = (
            "Rebuilding touches DNS, the tailnet, healthchecks.io and the "
            "application's own repository.\n\n## 1. Destroy\n\nNothing here.\n"
        )
        offences = external_venues_not_written_as_steps(document)
        self.assertEqual(len(offences), len(EXTERNAL_VENUES), offences)
        self.assertTrue(all("only outside" in entry for entry in offences), offences)

    def test_a_venue_named_nowhere_is_reported_differently(self) -> None:
        offences = external_venues_not_written_as_steps("## 1. Destroy\n\nNothing.\n")
        self.assertTrue(all("nowhere" in entry for entry in offences), offences)

    def test_every_venue_named_inside_a_phase_is_not_reported(self) -> None:
        document = (
            "## 1. DNS\n\nEdit the record at the DNS provider.\n\n"
            "## 2. Tailnet\n\nDelete the stale tailnet peer.\n\n"
            "## 3. Observer\n\nRe-read the checks at healthchecks.io.\n\n"
            "## 4. Application\n\nTrigger the deploy from its own repository.\n"
        )
        self.assertEqual(external_venues_not_written_as_steps(document), [])


class TestTheRecordStateDetectorFires(unittest.TestCase):
    """One case per state, and one per way a state can be malformed. The three
    states are the delta's own table, and a classifier that collapsed two of
    them would be invisible against a document sitting in the third."""

    NEVER_STATE = "## Rehearsal record\n\nLast rehearsed: never\n"
    PARTIAL_STATE = (
        "## Rehearsal record\n\n"
        "Last rehearsed: never\n\n"
        "Partial run:\n\n"
        "Reached: the platform deploy\n"
        "Wall clock: 3 hours 10 minutes\n"
        "Stopped by: an expired Tailscale auth key\n"
    )
    REHEARSED_STATE = (
        "## Rehearsal record\n\n"
        "Last rehearsed: 2026-09-20\n"
        "Duration: 4 hours 5 minutes\n"
        "Stack: main-staging\n"
        "Corrected: the tailnet-peer deletion moved before the first converge\n"
    )

    def test_the_never_state_is_classified_and_clean(self) -> None:
        self.assertEqual(record_state(self.NEVER_STATE), "never")
        self.assertEqual(record_offences(self.NEVER_STATE), [])

    def test_the_partial_state_is_classified_and_clean(self) -> None:
        self.assertEqual(record_state(self.PARTIAL_STATE), "partial")
        self.assertEqual(record_offences(self.PARTIAL_STATE), [])

    def test_the_rehearsed_state_is_classified_and_clean(self) -> None:
        self.assertEqual(record_state(self.REHEARSED_STATE), "rehearsed")
        self.assertEqual(record_offences(self.REHEARSED_STATE), [])

    def test_a_blank_date_field_is_reported_rather_than_read_as_never(self) -> None:
        """The whole reason the never-state is a sentinel: a blank field is
        indistinguishable from one someone forgot to fill in."""
        blank = "## Rehearsal record\n\nLast rehearsed:\nDuration:\nStack:\n"
        self.assertIsNone(record_state(blank))
        self.assertTrue(record_offences(blank))

    def test_a_partial_block_missing_a_line_is_reported(self) -> None:
        offences = record_offences(
            self.PARTIAL_STATE.replace(
                "Stopped by: an expired Tailscale auth key\n", ""
            )
        )
        self.assertEqual(len(offences), 1, offences)
        self.assertIn("Stopped by", offences[0])

    def test_a_partial_run_keeps_last_rehearsed_at_never(self) -> None:
        """*"a run that did not complete rehearsed nothing"* -- so a date
        beside a partial block is two records, not one state."""
        both = self.PARTIAL_STATE.replace(
            "Last rehearsed: never", "Last rehearsed: 2026-09-20"
        )
        self.assertIsNone(record_state(both))
        self.assertTrue(record_offences(both))

    def test_a_record_accumulating_a_second_run_is_reported(self) -> None:
        accumulated = self.REHEARSED_STATE + "\nLast rehearsed: never\n"
        offences = record_offences(accumulated)
        self.assertTrue(
            any("`Last rehearsed:` lines" in entry for entry in offences), offences
        )

    def test_a_rehearsed_record_naming_no_correction_is_reported(self) -> None:
        offences = record_offences(
            self.REHEARSED_STATE.replace(
                "Corrected: the tailnet-peer deletion moved before the first converge\n",
                "",
            )
        )
        self.assertEqual(len(offences), 1, offences)
        self.assertIn("Corrected", offences[0])

    def test_a_rehearsal_date_that_is_not_a_date_is_reported(self) -> None:
        self.assertIsNone(
            record_state(self.REHEARSED_STATE.replace("2026-09-20", "yes, we did it"))
        )

    def test_the_state_documentation_under_a_later_heading_is_not_read_as_a_record(
        self,
    ) -> None:
        """tasks.md 2.6 has the document explain its own three states. That
        prose sits under a heading of its own, so the record ends before it."""
        documented = self.NEVER_STATE + (
            "\n### The three states\n\n"
            "- **Never rehearsed** -- `Last rehearsed: never`, and no "
            "`Partial run:` block.\n"
            "- **Rehearsed** -- `Last rehearsed:` carries the date.\n"
        )
        self.assertEqual(record_state(documented), "never")
        self.assertEqual(record_offences(documented), [])

    def test_a_missing_record_is_reported_rather_than_passed_over(self) -> None:
        self.assertEqual(record_state("# A document with no record\n"), None)
        self.assertTrue(record_offences("# A document with no record\n"))

    def test_a_rehearsal_against_a_stack_that_is_not_disposable_is_reported(
        self,
    ) -> None:
        not_tolerable = next(
            stack
            for stack in stack_names()
            if stack not in stacks_whose_loss_is_tolerable()
        )
        offences = rehearsal_stacks_whose_loss_is_not_tolerable(
            self.REHEARSED_STATE.replace("main-staging", not_tolerable)
        )
        self.assertEqual(len(offences), 1, offences)

    def test_a_rehearsal_against_a_disposable_stack_is_not_reported(self) -> None:
        tolerable = stacks_whose_loss_is_tolerable()[0]
        self.assertEqual(
            rehearsal_stacks_whose_loss_is_not_tolerable(
                self.REHEARSED_STATE.replace("main-staging", tolerable)
            ),
            [],
        )

    def test_a_never_rehearsed_record_makes_no_claim_about_a_stack(self) -> None:
        self.assertEqual(
            rehearsal_stacks_whose_loss_is_not_tolerable(self.NEVER_STATE), []
        )


class TestTheSecondAccountDetectorFires(unittest.TestCase):
    def test_an_ordered_list_of_stages_is_read_as_a_sequence(self) -> None:
        appendix = [(1, "The same stages, in this order: 4.2, 4.3, 4.4, 5.3, 6.3, 6.6.")]
        self.assertGreater(len(stage_references(appendix)), MAX_STAGE_REFERENCES_IN_A_POINTER)

    def test_a_pointer_naming_two_stages_is_not_read_as_a_sequence(self) -> None:
        appendix = [(1, "A rebuilt host's first converge is a workstation converge (§6.3, §6.6).")]
        self.assertLessEqual(
            len(stage_references(appendix)), MAX_STAGE_REFERENCES_IN_A_POINTER
        )

    def test_the_bare_and_sectioned_forms_are_both_read(self) -> None:
        self.assertEqual(stage_references([(1, "§6.3 and 4.2 and stage 7")]), ["4.2", "6.3"])

    def test_a_sequence_phrase_is_reported_even_with_the_numbers_dropped(self) -> None:
        """The count above cannot see a sequence rewritten into prose."""
        self.assertTrue(
            any(
                phrase in "Repeat the same stages, skipping what still exists.".lower()
                for phrase in SEQUENCE_PHRASES
            )
        )


class TestTheRegisterAndDurationDetectorsFire(unittest.TestCase):
    def test_a_duration_is_recognised_in_the_spellings_a_register_uses(self) -> None:
        for spelling in ("7 days", "5 minutes", "2 hours", "a few minutes", "several days"):
            with self.subTest(spelling=spelling):
                self.assertTrue(DURATION.search(spelling), spelling)

    def test_a_bare_number_is_not_read_as_a_duration(self) -> None:
        self.assertIsNone(DURATION.search("main-staging-alertmanager | 5 | 2"))

    def test_a_register_table_row_carries_two_durations(self) -> None:
        row = "| `main-staging-alertmanager` | Watchdog | 5 minutes | 2 minutes |"
        self.assertEqual(len(DURATION.findall(row)), 2, row)

    def test_a_period_and_grace_table_in_the_runbook_is_reported(self) -> None:
        offences = register_values_copied_into(
            "| Check | Period | Grace |\n|---|---|---|\n| a | 5 minutes | 2 minutes |\n"
        )
        self.assertEqual(len(offences), 1, offences)

    def test_a_period_labelled_line_in_the_runbook_is_reported(self) -> None:
        offences = register_values_copied_into("Period: 5 minutes\nGrace: 2 minutes\n")
        self.assertEqual(len(offences), 2, offences)

    def test_saying_how_long_an_alarm_lasts_is_not_read_as_a_copied_value(self) -> None:
        """The alarm scenario requires the document to say how long an alarm
        lasts. A detector that read that as a copied register value would make
        two requirements of one delta contradict each other."""
        self.assertEqual(
            register_values_copied_into(
                "`main-staging-alertmanager` goes overdue within a few minutes "
                "of the destroy and stays overdue for the whole window.\n"
            ),
            [],
        )

    def test_a_check_named_with_no_settings_beside_it_is_reported(self) -> None:
        """Exercised through the same window logic the register check uses, over
        material supplied here rather than over Appendix A."""
        body = [(1, "| `main-staging-alertmanager` | Alertmanager's Watchdog |")]
        window = "\n".join(raw for _, raw in body)
        self.assertLess(len(DURATION.findall(window)), 2, window)


class TestTheOrderingDetectorsFire(unittest.TestCase):
    DOCUMENT = (
        "## 1. Before you destroy anything\n\n"
        "`main-staging-alertmanager` pages for the whole window, roughly 2 hours. "
        "Prometheus's history and Grafana's UI state do not come back; on "
        "main-production, commerce-ops's own PostgreSQL is lost outright. See "
        "*No Store on This Host Holds Data Requiring Backup* "
        "(`openspec/specs/iac-safety-hardening/spec.md`).\n\n"
        "## 2. Destroy the server\n\n"
        "```hcl\nserver_enabled = false\n```\n\n"
        "## 3. The observer\n\n"
        "At healthchecks.io, re-read `main-staging-alertmanager` and "
        "`main-staging-prune-host-images` against the period and grace "
        "Appendix A records.\n"
    )

    def test_the_destroy_step_is_found_inside_a_fenced_snippet(self) -> None:
        """It is written as `terraform.tfvars` content, so a detector reading
        only unfenced lines would never find it. Line 8 of the fixture above is
        inside its ```hcl fence."""
        self.assertEqual(destroy_step_line(self.DOCUMENT), 8)
        self.assertNotIn(
            8, [number for number, _ in unfenced_lines(self.DOCUMENT)[0]]
        )

    def test_an_alarm_named_before_the_destroy_step_is_not_reported(self) -> None:
        self.assertEqual(alarms_not_predicted_before_the_destroy(self.DOCUMENT), [])

    def test_an_alarm_named_only_after_the_destroy_step_is_reported(self) -> None:
        late = self.DOCUMENT.replace("`main-staging-alertmanager` pages", "Something pages")
        offences = alarms_not_predicted_before_the_destroy(late)
        self.assertTrue(offences, offences)

    def test_an_alarm_named_with_no_duration_is_reported(self) -> None:
        undated = self.DOCUMENT.replace(", roughly 2 hours", "")
        offences = alarms_not_predicted_before_the_destroy(undated)
        self.assertTrue(any("duration" in entry for entry in offences), offences)

    def test_the_observer_phase_is_found_after_the_destroy_step(self) -> None:
        phase = observer_phase(self.DOCUMENT)
        self.assertIsNotNone(phase)
        self.assertEqual(phase["number"], 3)
        self.assertEqual(observer_phase_omissions(self.DOCUMENT), [])

    def test_an_observer_phase_naming_no_check_individually_is_reported(self) -> None:
        vague = self.DOCUMENT.replace("`main-staging-prune-host-images`", "the other check")
        offences = observer_phase_omissions(vague)
        self.assertTrue(any("prune-host-images" in entry for entry in offences), offences)

    def test_an_observer_phase_re_reading_no_settings_is_reported(self) -> None:
        vague = self.DOCUMENT.replace("against the period and grace", "against what")
        offences = observer_phase_omissions(vague)
        self.assertEqual(len(offences), 2, offences)

    def test_the_losses_stated_before_the_destroy_step_are_not_reported(self) -> None:
        self.assertEqual(losses_not_stated_before_the_destroy(self.DOCUMENT), [])

    def test_an_unmet_store_named_only_after_the_destroy_step_is_reported(self) -> None:
        late = self.DOCUMENT.replace("commerce-ops's own PostgreSQL is lost outright", "")
        offences = losses_not_stated_before_the_destroy(late)
        self.assertTrue(any(UNMET_STORE in entry for entry in offences), offences)

    def test_a_citation_without_its_capability_path_is_reported(self) -> None:
        pathless = self.DOCUMENT.replace(
            "(`openspec/specs/iac-safety-hardening/spec.md`)", ""
        )
        offences = losses_not_stated_before_the_destroy(pathless)
        self.assertTrue(
            any(STORE_REQUIREMENT_PATH in entry for entry in offences), offences
        )

    def test_a_store_that_does_not_come_back_going_unnamed_is_reported(self) -> None:
        silent = self.DOCUMENT.replace("Prometheus's history and ", "")
        offences = losses_not_stated_before_the_destroy(silent)
        self.assertTrue(any("prometheus" in entry for entry in offences), offences)


if __name__ == "__main__":
    unittest.main()
