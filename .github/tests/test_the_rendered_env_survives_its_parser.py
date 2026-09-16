"""Static-assertion tests for rendering `.env` so that a secret survives the
parser that reads it.

Derived from the delta specification of the OpenSpec change
`render-the-env-file-so-a-secret-survives-it`, before any implementation of that
change existed -- from that delta at commit `f488c21`, the commit holding the
approved plan. The path that delta sits at is not written here: a change's
artifacts move when it is archived, and this repository's citation convention is
to name the change and the artifact in prose instead.

The delta modifies one requirement of `iac-platform-deploy-pipeline` --
*Platform Secrets Rendered from CI at Deploy Time*
(`openspec/specs/iac-platform-deploy-pipeline/spec.md`) -- and adds seven
scenarios to it. Each class below names the scenario it traces to, and every
assertion is annotated SPECIFIED (it traces to SHALL text or to a scenario in
the delta) or DERIVED (it traces to that change's `design.md` or `tasks.md`
rather than to a scenario). See that change's `test-plan.md` for the
scenario-to-test mapping, the baseline, the three scenarios deliberately left
uncovered, the obsolete-test search, and the assumptions this file took.

Why this is a new module rather than a section of an existing one
----------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. `test_the_platform_stack_deploys_per_stack.py`
already reads this workflow and already carries assertions about the same
requirement; none of them is superseded by this delta, which adds clauses rather
than retiring any. Where this file needs a helper that module already has, it
imports it rather than restating it -- which is also what task 1.4 of that
change requires of the anti-vacuity floor. Nothing in this file edits, deletes
or disables an existing test.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_the_rendered_env_survives_its_parser.TestTheEscapingPointSubstitutesInOrder\\
.test_the_three_substitutions_are_applied_in_the_order_the_design_fixes

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling imports below resolve.

What no assertion here establishes
----------------------------------
**Not that Compose's `.env` parser honours the escaping.** Three of the seven
scenarios the delta adds -- *A secret containing a character the parser treats
specially survives the parse*, *A secret that spells a variable reference is not
resolved from the rendering environment*, and *A secret containing the quote
character is not yielded as empty* -- are properties of that parser, and
observing one needs a Compose run. This suite may not spawn a container, by a
constraint it asserts over itself, and Molecule's subject is an Ansible role's
behaviour on a host rather than a workflow's output. So those three are recorded
in that change's `test-plan.md` as deliberately uncovered, and the behavioural
evidence for them is the measurement in that change's `design.md` together with
the harness committed with it -- not anything in this file. A check here that
read the workflow's text and called it parser behaviour would be worse than no
check, because it would read as the evidence that measurement is.

Nor that the report's disclosure is bounded to one bit. The delta forbids "any
count of such characters"; nothing static distinguishes a variable holding a
count from a variable holding a name, so what is asserted below is the narrower,
readable property -- that the report emits no value and no escaped value, and
that what its naming branch expands is an accumulator built from the escaping
point's own name parameter.

Nor that this module obeys the static suite's own constraints. Those are
asserted over `test_ci_configuration.py` by name and, for the
no-privileged-resource half, over every module in this directory; the rest are a
reviewer's to check. `docs/backlog.md`
`hold-the-whole-static-suite-to-its-own-constraints` is the entry that would
widen them.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from test_ci_configuration import (
    PLATFORM_DEPLOY,
    load_yaml,
    step_label,
    steps,
)
from test_the_platform_stack_deploys_per_stack import env_example_variables

# --------------------------------------------------------------------------
# Identifiers this file names, and why each is a constraint of the test layer
# rather than a property the specification states
# --------------------------------------------------------------------------

# The file the deploy renders. SPECIFIED by the requirement, which names "the
# `.env` file consumed by `platform/docker-compose.yml`"; the path is the one the
# committed workflow and the committed `tar` invocation already use, so it is
# read from neither a hint nor a guess.
ENV_FILE = "platform/.env"

# The three substitutions and the order they are applied in. SPECIFIED that
# there is an order and that it is statically verifiable -- "that it applies the
# substitutions it claims in the order it claims them" -- and DERIVED, from that
# change's `design.md` Decisions 3 and 4, as to which three and which order. `\`
# first, because escaping a quote or a dollar first introduces backslashes a
# later `\` pass would double; `$$` rather than `\$`, because `$$` is the rule
# the parser defines in both quoting contexts while `\$` is honoured only inside
# double quotes.
ESCAPES = (
    ("\\", "\\\\"),
    ('"', '\\"'),
    ("$", "$$"),
)

ESCAPED_CHARACTERS = frozenset(character for character, _ in ESCAPES)

# The set the report tests each value against. DERIVED -- the delta deliberately
# does not carry it ("Which values those are is a fact about the rendering being
# replaced rather than about this capability"), and this check is the only thing
# binding the implementation to the measurement. Taken character for character
# from that change's `design.md` Decision 9: five characters with a measured
# corrupting position, the line break as the sixth, and the backslash as a
# stated margin. Leading and trailing whitespace are the seventh member and are
# not characters, so they are asserted separately below.
REPORTED_CHARACTERS = frozenset({"$", '"', "'", "#", "\n", "\\"})

# Whether a bracket expression names whitespace as a class. The whitespace
# member corrupts "by definition -- stripped", and it is the one member
# Decision 9 permits to be detected positionally; both ends strip a tab as well
# as a space (round 6's three trailing-whitespace values), so a detector
# spelling only a literal space claims the member and covers half of it. A POSIX
# class and an explicit set are both readable.
WHITESPACE_CLASSES = ("[:space:]", "[:blank:]")
WHITESPACE_CHARACTERS = frozenset(" \t")

# Commands that put text somewhere a reader can see, and the run-scoped files a
# redirect can put it in. `tee` is included because it writes a file AND
# standard output, which is precisely the shape that would put an escaped
# credential in a log while reading as a file write.
EMITTING = re.compile(r"(?<![\w-])(?:echo|printf|cat|tee)(?![\w-])")
RUN_SCOPED_FILES = re.compile(r"\$\{?GITHUB_(?:OUTPUT|ENV|STEP_SUMMARY|PATH)\b")

# A GitHub Actions workflow command that reports. DERIVED from that change's
# tasks.md 2.3, which says "as a GitHub Actions notice"; `::warning::` is
# admitted alongside it because the delta says "report" and fixes no severity,
# and a check keyed on one severity would fail a legitimate choice.
REPORT_COMMAND = re.compile(r"::(?:notice|warning)(?:\s[^:]*)?::")

# The variables a workflow-command line may expand without naming anything of
# its own. Excluded from "does this line name a variable" so that a report
# written to the job summary is not read as a naming branch for that reason.
RUN_SCOPED_NAMES = frozenset({"GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_STEP_SUMMARY"})

# Command substitution, in both spellings. DERIVED from that change's tasks.md
# 2.1 and `design.md` Decision 5: command substitution strips trailing newlines
# and a GitHub secret may end in one, so a helper that printed and a caller that
# captured would introduce a corruption at the moment the rest were removed.
COMMAND_SUBSTITUTION = re.compile(r"\$\(|(?<!\\)`")

# A shell function definition, in both spellings bash accepts.
FUNCTION_DEFINITION = re.compile(
    r"^\s*(?:function\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_-]*)\s*(?:\(\s*\))?\s*\{\s*$"
)


def _redirect_to(path: str) -> re.Pattern:
    """A redirect, or a `tee`, into a named file.

    The trailing negative lookahead is what keeps `platform/.env.example` -- a
    committed, documented, value-free file -- from being read as a write of the
    rendered one.
    """
    return re.compile(
        r"(?:>>?|(?<![\w-])tee(?![\w-])(?:\s+-[\w-]+)*)\s*"
        r"""(?P<quote>["']?)(?:\./)?""" + re.escape(path) + r"(?P=quote)(?![\w.])"
    )


ENV_FILE_REDIRECT = _redirect_to(ENV_FILE)


# --------------------------------------------------------------------------
# Reading a shell body
# --------------------------------------------------------------------------


def body_of(step: dict) -> str:
    return str(step.get("run") or "")


def code_lines(body: str) -> list:
    """`(number, text)` for every line that is not blank and not a whole-line
    shell comment.

    Only a WHOLE-LINE comment is dropped. A trailing comment is left in place
    deliberately: `#` is one of the characters the report tests for, so a
    stripper that removed everything after the first `#` would delete the
    detector it was about to read and then report its absence.
    """
    found = []
    for number, raw in enumerate(body.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        found.append((number, raw))
    return found


def emitting_in(pairs) -> list:
    """The `(number, text)` pairs that put text where a reader can see it."""
    return [
        (number, text)
        for number, text in pairs
        if EMITTING.search(text) or RUN_SCOPED_FILES.search(text)
    ]


def emitting_lines(body: str) -> list:
    return emitting_in(code_lines(body))


def report_lines(body: str) -> list:
    return [(number, text) for number, text in code_lines(body) if REPORT_COMMAND.search(text)]


def expands(text: str, name: str) -> bool:
    return bool(re.search(r"\$\{?" + re.escape(name) + r"(?![A-Za-z0-9_])", text))


def expanded_names(text: str) -> set:
    """Every variable a line expands, less the run-scoped ones."""
    return set(re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", text)) - RUN_SCOPED_NAMES


def env_file_writing_steps(workflow: dict) -> list:
    """`(label, step)` for every step whose body redirects into the rendered
    `.env`.

    The render step is located by what it DOES rather than by its name, which is
    both what the scenario reads ("no line SHALL write a value into that file by
    any other route") and what keeps a rename of the step from silently emptying
    every assertion in this file.
    """
    found = []
    for job_name, index, step in steps(workflow):
        if ENV_FILE_REDIRECT.search(body_of(step)):
            found.append((step_label(job_name, index, step), step))
    return found


def sole_render_step(workflow: dict) -> dict:
    found = env_file_writing_steps(workflow)
    if len(found) != 1:
        raise AssertionError(
            f"exactly one step writes {ENV_FILE}; found "
            f"{[label for label, _ in found]}. A second step appending to the file "
            "is the route the scenario names, and it is invisible to any check "
            "scoped to the render step"
        )
    return found[0][1]


# --------------------------------------------------------------------------
# The escaping point
# --------------------------------------------------------------------------


class ShellFunction:
    """A function definition inside a step's body, carrying its own lines with
    their numbers in the step body rather than in the function."""

    def __init__(self, name: str, first: int, last: int, lines: list) -> None:
        self.name = name
        self.first = first
        self.last = last
        self.lines = lines

    @property
    def text(self) -> str:
        return "\n".join(text for _, text in self.lines)

    def emitting(self) -> list:
        return emitting_in(self.lines)


def shell_functions(body: str) -> list:
    """Every function the body defines.

    The closing brace is found as the first following line whose whole content
    is `}`. Counting braces was the first draft and is worse here: `${value//…}`
    puts an unbalanced-looking brace on nearly every line of the very function
    this reads, so a counter has to strip parameter expansions first and then
    arrives at the answer this rule reaches directly.
    """
    lines = body.splitlines()
    found = []
    for index, raw in enumerate(lines):
        match = FUNCTION_DEFINITION.match(raw)
        if not match:
            continue
        for offset in range(index + 1, len(lines)):
            if lines[offset].strip() != "}":
                continue
            found.append(
                ShellFunction(
                    match.group("name"),
                    index + 1,
                    offset + 1,
                    [
                        (number, lines[number - 1])
                        for number in range(index + 2, offset + 1)
                        if lines[number - 1].strip()
                        and not lines[number - 1].strip().startswith("#")
                    ],
                )
            )
            break
    return found


class Substitution:
    def __init__(self, variable, glob, pattern, replacement, offset) -> None:
        self.variable = variable
        self.glob = glob
        self.pattern = pattern
        self.replacement = replacement
        self.offset = offset

    @property
    def target(self):
        """The single character this substitution replaces, or `None`.

        The pattern is unescaped before it is read, so `\\\\`, `\\"` and `\\$`
        each resolve to the one character they stand for and a bare `$` resolves
        to itself. A pattern that is not one character after that is not one of
        the three escapes, and is left unclassified rather than guessed at.
        """
        unescaped = unescape(self.pattern)
        return unescaped if len(unescaped) == 1 else None


SUBSTITUTION_START = re.compile(r"\$\{(?P<var>[A-Za-z_][A-Za-z0-9_]*)(?P<mode>//|/)")


def unescape(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def _read_until(text: str, index: int, stop: str):
    """Read to the next unescaped `stop`, refusing at an unescaped `}`."""
    out = []
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            out.append(char)
            out.append(text[index + 1])
            index += 2
            continue
        if char == stop:
            return "".join(out), index + 1
        if char == "}":
            return None, index
        out.append(char)
        index += 1
    return None, index


def substitutions(text: str) -> list:
    """Every `${var//pattern/replacement}`, in source order.

    Read with a scanner rather than with one regex because both the pattern and
    the replacement of the first of the three substitutions are made of
    backslashes, and a regex delimited on `/` and `}` reads that one as ending
    in the wrong place.
    """
    found = []
    for match in SUBSTITUTION_START.finditer(text):
        pattern, index = _read_until(text, match.end(), "/")
        if pattern is None:
            continue
        replacement, _ = _read_until(text, index, "}")
        if replacement is None:
            continue
        found.append(
            Substitution(
                variable=match.group("var"),
                glob=match.group("mode") == "//",
                pattern=pattern,
                replacement=replacement,
                offset=match.start(),
            )
        )
    return found


def escaping_substitutions(point: ShellFunction) -> list:
    return [item for item in substitutions(point.text) if item.target in ESCAPED_CHARACTERS]


def escaping_points(body: str) -> list:
    """Every function whose body applies a substitution to one of the three
    escaped characters.

    Identified by what it does rather than by a name, for the reason every other
    locator in this suite is: the requirement obliges "a single escaping point"
    and fixes no spelling for it, so a check keyed on `render` would fail a
    legitimate choice and would then be repaired by editing this file.
    """
    return [function for function in shell_functions(body) if escaping_substitutions(function)]


def sole_escaping_point(body: str) -> ShellFunction:
    points = escaping_points(body)
    if len(points) != 1:
        raise AssertionError(
            "the render step defines no single escaping point: expected exactly one "
            "shell function applying a substitution to `\\`, `\"` or `$`, found "
            f"{[point.name for point in points]}. A value is escaped either by the "
            "point every assignment goes through, or by a convention each author "
            "repeats -- and only the first is a property a ninth value inherits"
        )
    return points[0]


class Assignment:
    def __init__(self, variable: str, value: str, line: int) -> None:
        self.variable = variable
        self.value = value
        self.line = line


ASSIGNMENT = re.compile(
    r"^\s*(?:local\s+|declare\s+|export\s+)?(?P<var>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<op>\+?=)(?P<value>.*)$"
)


def assignments(text: str) -> list:
    found = []
    for number, raw in code_lines(text):
        match = ASSIGNMENT.match(raw)
        if match:
            found.append(Assignment(match.group("var"), match.group("value"), number))
    return found


def escaped_variable(point: ShellFunction):
    """The variable the escaping point's substitutions land in."""
    escaping = escaping_substitutions(point)
    return escaping[0].variable if escaping else None


def name_parameter(point: ShellFunction):
    """The variable the escaping point assigns from its first positional
    parameter, or `"1"` where it uses `$1` directly."""
    for assignment in assignments(point.text):
        if re.search(r"\$\{?1\}?", assignment.value):
            return assignment.variable
    return "1" if re.search(r"\$\{?1\}?", point.text) else None


def step_env_names(step: dict) -> list:
    return [str(name) for name in (step.get("env") or {})]


# --------------------------------------------------------------------------
# The block the file is written from
# --------------------------------------------------------------------------


def env_file_block(body: str) -> list:
    """`(number, text)` for the lines whose output becomes the rendered file.

    Two shapes are read, because both are legitimate. Where the redirect closes
    a group -- `} >platform/.env` -- the block is the group's own lines. Where it
    is attached to a single command, that command is the block.
    """
    lines = body.splitlines()
    for index, raw in enumerate(lines):
        match = ENV_FILE_REDIRECT.search(raw)
        if not match:
            continue
        before = raw[: match.start()].strip()
        if before and before != "}":
            return [(index + 1, before)]
        if not before:
            return []
        for offset in range(index - 1, -1, -1):
            if lines[offset].strip() != "{":
                continue
            return [
                (number, lines[number - 1])
                for number in range(offset + 2, index + 1)
                if lines[number - 1].strip()
                and not lines[number - 1].strip().startswith("#")
            ]
        return []
    return []


CALL = re.compile(r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_-]*)\s+(?P<rest>\S.*)$")
WORD = re.compile(r"""'([^']*)'|"([^"]*)"|(\S+)""")


def call_offences(block: list, helper: str) -> list:
    """Every line of the write block that is not a call to the escaping point.

    This is the whole of what a choke point buys over a convention, and it is
    why the assertion is written over the block rather than over each assignment
    in it: a ninth value added next month is either a call, and escaped, or it is
    reported here.
    """
    offences = []
    for number, text in block:
        match = CALL.match(text)
        if not match or match.group("name") != helper:
            offences.append(
                f"line {number} of the block written into {ENV_FILE} is not a call to "
                f"`{helper}`: {text.strip()!r}. Every value reaches the file through "
                "the single escaping point, or the point is a convention rather than "
                "a choke point"
            )
    return offences


def rendered_names(block: list, helper: str) -> list:
    """The first argument of every call in the write block, unquoted."""
    names = []
    for _, text in block:
        match = CALL.match(text)
        if not match or match.group("name") != helper:
            continue
        word = WORD.match(match.group("rest").strip())
        if not word:
            continue
        value = next(group for group in word.groups() if group is not None)
        if value:
            names.append(value)
    return names


# --------------------------------------------------------------------------
# Glob patterns, for what the report tests a value against
# --------------------------------------------------------------------------

STAR = "star"
CHAR = "char"
BRACKET = "bracket"
ANY = "any"

ANSI_C = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"'}


def glob_atoms(word: str):
    """A shell pattern word as a list of `(kind, value)`, or `None` where it does
    not read as one.

    Quoting is resolved, because quoting is how a pattern spells a character
    that is otherwise the shell's: `*'$'*`, `*"'"*` and `*$'\\n'*` each name one
    character, and a reader that skipped quotes would see two stars and no
    character in the first of them.
    """
    atoms = []
    index = 0
    while index < len(word):
        char = word[index]
        if word.startswith("$'", index):
            end = word.find("'", index + 2)
            if end < 0:
                return None
            inner, cursor = [], index + 2
            while cursor < end:
                if word[cursor] == "\\" and cursor + 1 < end:
                    inner.append(ANSI_C.get(word[cursor + 1], word[cursor + 1]))
                    cursor += 2
                else:
                    inner.append(word[cursor])
                    cursor += 1
            atoms.extend((CHAR, item) for item in inner)
            index = end + 1
        elif char == "'":
            end = word.find("'", index + 1)
            if end < 0:
                return None
            atoms.extend((CHAR, item) for item in word[index + 1 : end])
            index = end + 1
        elif char == '"':
            end = word.find('"', index + 1)
            if end < 0:
                return None
            atoms.extend((CHAR, item) for item in unescape(word[index + 1 : end]))
            index = end + 1
        elif char == "\\":
            if index + 1 >= len(word):
                return None
            atoms.append((CHAR, word[index + 1]))
            index += 2
        elif char == "*":
            atoms.append((STAR, "*"))
            index += 1
        elif char == "?":
            atoms.append((ANY, "?"))
            index += 1
        elif char == "[":
            if word.startswith("[[:", index):
                end = word.find(":]]", index)
                if end < 0:
                    return None
                atoms.append((BRACKET, word[index : end + 3]))
                index = end + 3
            else:
                end = word.find("]", index + 1)
                if end < 0:
                    return None
                atoms.append((BRACKET, word[index : end + 1]))
                index = end + 1
        else:
            atoms.append((CHAR, char))
            index += 1
    return atoms


def is_whitespace_bracket(value: str) -> bool:
    if any(name in value for name in WHITESPACE_CLASSES):
        return True
    inner = value[1:-1]
    return bool(inner) and set(inner) >= WHITESPACE_CHARACTERS


def split_alternatives(text: str) -> list:
    """Split a case pattern on `|`, ignoring a `|` inside quotes."""
    parts, current, quote = [], [], None
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "'\"":
            quote = char
            current.append(char)
            index += 1
            continue
        if char == "\\" and index + 1 < len(text):
            current.append(char)
            current.append(text[index + 1])
            index += 2
            continue
        if char == "|":
            parts.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    parts.append("".join(current).strip())
    return [part for part in parts if part]


CASE_OPEN = re.compile(r"(?<![\w-])case(?![\w-]).*?(?<![\w-])in(?![\w-])\s*$")
CASE_ARM = re.compile(r"^\s*\(?\s*(?P<patterns>[^)]+)\)")
CONDITION = re.compile(r"\[\[\s+(?P<lhs>.+?)\s+(?:==|!=)\s+(?P<pattern>.+?)\s*\]\]")


def tested_patterns(body: str) -> list:
    """`(line, alternative)` for every shell pattern the body tests a value
    against.

    Two constructs are read -- `case` arms and `[[ … == … ]]` -- because both are
    how bash asks "does this value contain that". Anything else reads as no
    detector at all, and the failure messages below say which forms this file can
    see rather than leaving a reader to guess.
    """
    found = []
    inside = False
    for number, raw in code_lines(body):
        stripped = raw.strip()
        if CASE_OPEN.search(stripped):
            inside = True
            continue
        if stripped == "esac":
            inside = False
            continue
        if inside and not stripped.startswith(";;"):
            arm = CASE_ARM.match(raw)
            if arm:
                for alternative in split_alternatives(arm.group("patterns")):
                    found.append((number, alternative))
        for match in CONDITION.finditer(raw):
            for alternative in split_alternatives(match.group("pattern")):
                found.append((number, alternative))
    return found


class Detection:
    """What one pattern alternative detects, and how."""

    def __init__(self, line, source, atoms) -> None:
        self.line = line
        self.source = source
        self.atoms = atoms

    @property
    def kinds(self) -> list:
        return [kind for kind, _ in self.atoms]

    @property
    def anywhere(self):
        """The single character this alternative finds ANYWHERE, or `None`."""
        if len(self.atoms) == 3 and self.kinds == [STAR, CHAR, STAR]:
            return self.atoms[1][1]
        return None

    @property
    def whitespace_edge(self):
        """`"leading"`, `"trailing"`, or `None`."""
        if len(self.atoms) != 2:
            return None
        (first_kind, first), (second_kind, second) = self.atoms
        if first_kind == BRACKET and second_kind == STAR and is_whitespace_bracket(first):
            return "leading"
        if first_kind == STAR and second_kind == BRACKET and is_whitespace_bracket(second):
            return "trailing"
        return None

    @property
    def positional_characters(self) -> set:
        """The reported characters this alternative finds only in a POSITION.

        Either anchored -- `'*` finds an opening apostrophe and not a mid-value
        one -- or conditioned on a neighbour, which `*" #"*` is: it finds a hash
        preceded by a space and not one preceded by a tab, and round 6 measured
        exactly that distinction, in exactly that direction, being the opposite
        of what anyone would guess. Both re-derive the parser's rules in workflow
        code nothing in this repository can exercise, which is what Decision 9
        forbids.
        """
        if self.anywhere is not None or self.whitespace_edge is not None:
            return set()
        characters = {value for kind, value in self.atoms if kind == CHAR}
        return characters & set(REPORTED_CHARACTERS)


def detections(body: str) -> list:
    found = []
    for number, alternative in tested_patterns(body):
        atoms = glob_atoms(alternative)
        if atoms is None:
            continue
        found.append(Detection(number, alternative, atoms))
    return found


def detected_anywhere(body: str) -> set:
    return {
        detection.anywhere for detection in detections(body) if detection.anywhere is not None
    }


def detected_edges(body: str) -> set:
    return {
        detection.whitespace_edge
        for detection in detections(body)
        if detection.whitespace_edge is not None
    }


def positional_offences(body: str) -> set:
    found = set()
    for detection in detections(body):
        found |= detection.positional_characters
    return found


# --------------------------------------------------------------------------
# The disclosure sweep
# --------------------------------------------------------------------------


def disclosure_offences(body: str, secrets, escaped, exempt) -> list:
    """Every line that would put a rendered value, or its escaped form, somewhere
    a reader can see it.

    The escaped form is named explicitly, and that is not a pedantic addition:
    GitHub registers its log masking against each secret's own value, so the
    escaped variant is a different string and is the one shape of a credential
    that reaches a log in the clear. This change is the first thing in this
    repository that creates such a variant, so the prohibition arrives with it.
    """
    offences = []
    for number, text in emitting_lines(body):
        if number in exempt:
            continue
        if escaped and expands(text, escaped):
            offences.append(
                f"line {number} emits `${escaped}`, the ESCAPED form of a rendered "
                f"value: {text.strip()!r}. Masking is registered against the secret's "
                "own value, so the escaped variant is not covered by it"
            )
        for name in sorted(secrets):
            if expands(text, name):
                offences.append(
                    f"line {number} emits the value of `{name}`: {text.strip()!r}. "
                    "The report names variables only"
                )
    return offences


# --------------------------------------------------------------------------
# Reading the committed workflow
# --------------------------------------------------------------------------


class RenderStepMixin:
    """Every class below reads the same one step; this is where it is found, so
    that an absent or duplicated one is reported in one place rather than in
    each."""

    def render_step(self) -> dict:
        return sole_render_step(load_yaml(PLATFORM_DEPLOY))

    def render_body(self) -> str:
        return body_of(self.render_step())

    def escaping_point(self) -> ShellFunction:
        return sole_escaping_point(self.render_body())


# --------------------------------------------------------------------------
# Scenario: Every rendered value passes through the escaping point
# --------------------------------------------------------------------------


class TestTheRenderStepHasOneEscapingPoint(RenderStepMixin, unittest.TestCase):
    """MODIFIED requirement: Platform Secrets Rendered from CI at Deploy Time --
    "Every value written into that file SHALL be written through a single
    escaping point, rather than each assignment carrying its own escaping ... it
    follows that this SHALL be statically verifiable from the workflow's
    committed text: that the escaping point exists"."""

    def test_one_step_writes_the_rendered_file(self) -> None:
        """SPECIFIED -- scenario "Every rendered value passes through the escaping
        point": "no line SHALL write a value into that file by any other route".
        Read across the whole workflow, because a second step appending to the
        file is the route the scenario names and it is invisible to a check
        scoped to the render step."""
        self.render_step()

    def test_the_render_step_defines_exactly_one_escaping_point(self) -> None:
        """SPECIFIED -- "that the escaping point exists"."""
        self.escaping_point()

    def test_the_escaping_point_writes_the_assignment_itself(self) -> None:
        """DERIVED -- that change's tasks.md 2.1 and `design.md` Decision 5: the
        helper "escapes the value into a variable and writes the whole assignment
        line itself; the caller passes a name and a value and reads nothing
        back".

        Asserted as exactly one emitting line inside the point, because the
        point's output IS the file: a second emitting line there writes into the
        rendered file too, and would be invisible to the calls-only check below,
        which reads what the block calls rather than what a call emits.
        """
        point = self.escaping_point()
        emitting = point.emitting()
        self.assertEqual(
            1,
            len(emitting),
            f"the escaping point `{point.name}` emits text on {len(emitting)} lines, "
            "and everything it emits lands in the rendered file. Exactly one line "
            "writes the assignment; a second writes something else into the file",
        )

    def test_the_step_takes_no_command_substitution(self) -> None:
        """DERIVED -- that change's tasks.md 2.1: "no `$(…)` anywhere in the step,
        since command substitution strips trailing newlines and a GitHub secret
        may end in one, so capturing would introduce a corruption at the moment
        the rest of them were being removed"."""
        offences = [
            f"line {number}: {text.strip()!r}"
            for number, text in code_lines(self.render_body())
            if COMMAND_SUBSTITUTION.search(text)
        ]
        self.assertEqual(
            [],
            offences,
            "the render step uses command substitution, which strips trailing "
            f"newlines from a value that may end in one: {offences}",
        )


class TestTheEscapingPointSubstitutesInOrder(RenderStepMixin, unittest.TestCase):
    """MODIFIED requirement: Platform Secrets Rendered from CI at Deploy Time --
    "that it applies the substitutions it claims in the order it claims them".

    The order is the whole of what this class is for. The three substitutions are
    individually obvious and a check asserting them as a SET would pass a
    rendering that escapes the quote first and then doubles the backslash it
    introduced itself, turning `a"b` into `a\\\\"b` and delivering a literal
    backslash the operator never stored -- which is the defect that change's
    `design.md` Decision 4 exists to name, and the one the ten adversarial values
    of round 3 were built to catch.
    """

    def test_the_three_substitutions_are_applied_in_the_order_the_design_fixes(self) -> None:
        """SPECIFIED that an order is asserted; DERIVED (Decisions 3 and 4) as to
        which order and which replacements."""
        point = self.escaping_point()
        relevant = escaping_substitutions(point)
        self.assertEqual(
            [character for character, _ in ESCAPES],
            [item.target for item in relevant],
            "the escaping point does not apply `\\`->`\\\\`, then `\"`->`\\\"`, then "
            "`$`->`$$`, each once and in that order. Escaping the quote or the "
            "dollar first introduces backslashes that a later `\\` pass doubles",
        )
        self.assertEqual(
            [replacement for _, replacement in ESCAPES],
            [unescape(item.replacement) for item in relevant],
            "the escaping point substitutes the right characters in the right order "
            "and replaces at least one of them with something else. `\\$` is "
            "honoured only inside double quotes; `$$` is the rule the parser itself "
            "defines, and is the spelling platform/docker-compose.yml already uses",
        )

    def test_each_substitution_replaces_every_occurrence(self) -> None:
        """DERIVED -- Decision 4 states the rule over a value rather than over its
        first character, and `${v/x/y}` replaces one occurrence where `${v//x/y}`
        replaces all. A rendering that escapes only the first backslash of
        `a\\b\\c` is the same silent corruption in a narrower case."""
        point = self.escaping_point()
        offences = [
            f"`{item.pattern}` -> `{item.replacement}` on `{item.variable}`"
            for item in escaping_substitutions(point)
            if not item.glob
        ]
        self.assertEqual(
            [],
            offences,
            "a substitution in the escaping point is written `${v/…}` and so "
            f"replaces only the first occurrence: {offences}",
        )

    def test_the_three_substitutions_act_on_one_variable(self) -> None:
        """DERIVED -- Decision 5: "the escaping lands in a variable". Three
        substitutions spread across three variables are three escapings of three
        different strings, and the order asserted above would constrain
        nothing."""
        point = self.escaping_point()
        variables = {item.variable for item in escaping_substitutions(point)}
        self.assertEqual(
            1,
            len(variables),
            "the three substitutions do not act on one variable, so their order "
            f"constrains nothing: {sorted(variables)}",
        )


class TestEveryRenderedValueGoesThroughTheEscapingPoint(RenderStepMixin, unittest.TestCase):
    """MODIFIED requirement: Platform Secrets Rendered from CI at Deploy Time --
    scenario "Every rendered value passes through the escaping point": "every
    name it writes into `.env` SHALL be written through the single escaping
    point, and no line SHALL write a value into that file by any other route"."""

    def test_the_written_block_contains_calls_and_nothing_else(self) -> None:
        """SPECIFIED -- the scenario, and "that the file is written by nothing
        else"."""
        point = self.escaping_point()
        block = env_file_block(self.render_body())
        self.assertTrue(
            block,
            f"no block of the render step is redirected into {ENV_FILE}, so there is "
            "nothing to establish the calls-only property over",
        )
        offences = call_offences(block, point.name)
        self.assertEqual([], offences, offences)

    def test_every_variable_the_env_example_documents_is_rendered(self) -> None:
        """SPECIFIED -- "this obligation SHALL be read as reaching every value the
        deploy job writes into that file rather than only the ones that are
        credentials".

        The floor is DERIVED from the committed `platform/.env.example` rather
        than written here, which is that change's tasks.md 1.4: a literal count
        of eight would go stale on the first addition -- the exact rot the choke
        point exists to defend against, reintroduced in the check that guards it.
        A ninth value is covered by this assertion the day it is documented.
        """
        point = self.escaping_point()
        documented = env_example_variables()
        self.assertTrue(documented, "platform/.env.example documents no variable")
        rendered = rendered_names(env_file_block(self.render_body()), point.name)
        missing = sorted(set(documented) - set(rendered))
        self.assertEqual(
            [],
            missing,
            f"platform/.env.example documents {len(documented)} variables and the "
            f"render block passes {len(rendered)} of them through `{point.name}`; "
            f"these are documented and not rendered through it: {missing}",
        )

    def test_the_file_is_written_once(self) -> None:
        """SPECIFIED -- "no line SHALL write a value into that file by any other
        route", read within the step: a second redirect appending to the file is
        the route the scenario names."""
        redirects = [
            f"line {number}: {text.strip()!r}"
            for number, text in code_lines(self.render_body())
            if ENV_FILE_REDIRECT.search(text)
        ]
        self.assertEqual(
            1,
            len(redirects),
            f"the render step redirects into {ENV_FILE} more than once, so the "
            f"calls-only block is not the whole of what writes it: {redirects}",
        )


# --------------------------------------------------------------------------
# Scenarios: A rendered value the previous rendering would have altered is
# reported by name; A deploy that altered no value says so
# --------------------------------------------------------------------------


class TestTheRenderStepReportsWhatTheOldRenderingWouldHaveAltered(
    RenderStepMixin, unittest.TestCase
):
    """MODIFIED requirement: Platform Secrets Rendered from CI at Deploy Time --
    "The deploy job SHALL report, by name, each value it rendered that the
    rendering this requirement replaces would have altered", and the two
    scenarios that read it.

    The report is looked for in the render step. DERIVED, and not arbitrary: the
    values reach the shell only through that step's own `env:` block, so no later
    step can see them to test them.
    """

    def test_the_step_reports(self) -> None:
        """SPECIFIED -- scenario "A rendered value the previous rendering would
        have altered is reported by name"."""
        found = report_lines(self.render_body())
        self.assertTrue(
            found,
            "the render step emits no GitHub Actions notice, so a value being "
            "silently corrupted today is reported by nothing. What that leaves is "
            "an authentication failure at an arbitrary later moment with nothing "
            "pointing at its cause, which is what the report replaces",
        )

    def test_what_it_reports_is_a_name(self) -> None:
        """SPECIFIED -- "THEN the job SHALL report that variable's name". The
        naming branch is the one that expands something, and what it expands must
        be built from the escaping point's own name parameter, or the report
        names something other than a name."""
        body = self.render_body()
        point = self.escaping_point()
        naming = [(number, text) for number, text in report_lines(body) if expanded_names(text)]
        self.assertTrue(
            naming,
            "no line of the report expands anything, so the report names no variable "
            "and cannot distinguish one altered value from another",
        )
        parameter = name_parameter(point)
        self.assertIsNotNone(
            parameter,
            f"the escaping point `{point.name}` assigns no variable from its first "
            "positional parameter, so nothing here can establish that what the "
            "report names is a NAME rather than a value",
        )
        accumulators = set()
        for _, text in naming:
            accumulators |= expanded_names(text)
        built = {
            name
            for name in accumulators
            if any(
                assignment.variable == name
                and (expands(assignment.value, parameter) or "$1" in assignment.value)
                for assignment in assignments(body)
            )
        }
        self.assertTrue(
            built,
            f"the report expands {sorted(accumulators)}, and none of those is assigned "
            f"anywhere in the step from `${parameter}`, the escaping point's name "
            "parameter. The report names variables; it does not report what they hold",
        )

    def test_a_deploy_that_altered_no_value_says_so(self) -> None:
        """SPECIFIED -- scenario "A deploy that altered no value says so": "THEN
        the job SHALL report that explicitly, rather than reporting nothing". An
        absent notice and a notice reporting nothing are the same output to a
        reader, and only one of them is evidence."""
        silent = [
            (number, text)
            for number, text in report_lines(self.render_body())
            if not expanded_names(text)
        ]
        self.assertTrue(
            silent,
            "every line of the report expands a variable, so a deploy that altered "
            "nothing emits nothing -- which is the same output as a deploy whose "
            "report was never written, and the first deploy's empty notice is this "
            "change's evidence that nothing needs rotating",
        )


class TestTheReportTestsTheMeasuredSetByPresenceAnywhere(RenderStepMixin, unittest.TestCase):
    """MODIFIED requirement: Platform Secrets Rendered from CI at Deploy Time --
    "Which values those are is a fact about the rendering being replaced rather
    than about this capability, and SHALL be established by measurement and
    recorded in the change that establishes it".

    The delta deliberately carries no set, so this class is the only thing
    binding the implementation to the measurement in that change's `design.md`
    Decision 9. Both halves of that decision are asserted, because only one of
    them is visible in a set: an editor narrowing the hash test from `#` to `" #"`
    in the name of precision leaves the set unchanged, passes a check that reads
    only the set, and reintroduces exactly the positional re-derivation
    Decision 9 forbids -- over a rule round 6 measured doing something nobody
    would guess, a space before a `#` beginning a comment and a tab before it
    not doing so.
    """

    def test_the_set_is_decision_nines_set_character_for_character(self) -> None:
        """DERIVED -- Decision 9's table: `$`, `"`, `'`, `#`, a line break, and
        the backslash as a stated margin. Asserted as an equality rather than as a
        subset, so that a later reader "correcting" the set against round 5's
        intact apostrophe row is reported rather than silently accommodated."""
        found = detected_anywhere(self.render_body())
        self.assertEqual(
            set(REPORTED_CHARACTERS),
            found,
            "the characters the report tests for anywhere in a value are not "
            f"Decision 9's set. Missing: {sorted(set(REPORTED_CHARACTERS) - found)!r}; "
            f"unexpected: {sorted(found - set(REPORTED_CHARACTERS))!r}. The forms "
            "this reads are a `case` arm and a `[[ … == … ]]` comparison",
        )

    def test_leading_and_trailing_whitespace_are_both_tested_for(self) -> None:
        """DERIVED -- Decision 9's seventh member, "leading or trailing whitespace
        ... by definition -- stripped". This is the one member whose detection is
        legitimately positional, so it is asserted at both ends separately: a
        detector spelling only the trailing end passes a set check while covering
        half the member."""
        edges = detected_edges(self.render_body())
        self.assertEqual(
            {"leading", "trailing"},
            edges,
            "the report does not test for whitespace at both ends of a value as a "
            f"whitespace CLASS (found {sorted(edges)}). Round 6 measured both ends "
            "stripping a tab as well as a space, so a literal space is half a "
            "detector",
        )

    def test_no_member_is_detected_by_position(self) -> None:
        """DERIVED -- Decision 9: "Detection is by presence anywhere in the value,
        not by position. A member earns its place by having *a* position in which
        it corrupts; the notice then reports the character wherever it appears".

        The guard below is what keeps this from passing vacuously over a step
        that tests for nothing at all, which is the state the workflow is in
        before this change lands.
        """
        body = self.render_body()
        self.assertTrue(
            detections(body),
            "the render step tests a value against no pattern at all, so this "
            "assertion would pass by having nothing to read",
        )
        offences = sorted(
            f"line {detection.line} tests for {character!r} with the pattern "
            f"{detection.source!r}, which finds it only in a position or only beside "
            "a particular neighbour. Over-reporting costs one operator a look at a "
            "credential that turns out to be fine; re-deriving this parser's rules "
            "in workflow code costs what this whole change exists to remove"
            for detection in detections(body)
            for character in sorted(detection.positional_characters)
        )
        self.assertEqual([], offences, offences)


# --------------------------------------------------------------------------
# Scenario: The escaped form of a value is never emitted
# --------------------------------------------------------------------------


class TestNoLineEmitsARenderedValueOrItsEscapedForm(RenderStepMixin, unittest.TestCase):
    """MODIFIED requirement: Platform Secrets Rendered from CI at Deploy Time --
    "That report SHALL name variables only ... Nor SHALL any escaped form of a
    value be emitted", and the scenario that reads it."""

    def test_nothing_but_the_assignment_emits_the_escaped_value(self) -> None:
        """SPECIFIED -- scenario "The escaped form of a value is never emitted".

        The one exempt line is the escaping point's own write, which puts
        `NAME="<escaped>"` into the file and is the reason an escaped form exists
        at all. Every other emitting line in the step is swept, the report's
        included.
        """
        body = self.render_body()
        point = self.escaping_point()
        escaped = escaped_variable(point)
        self.assertIsNotNone(
            escaped,
            f"the escaping point `{point.name}` assigns its substitutions to no "
            "variable this can name, so the sweep for the escaped form has no subject",
        )
        exempt = {number for number, _ in point.emitting()}
        offences = disclosure_offences(
            body, set(step_env_names(self.render_step())), escaped, exempt
        )
        self.assertEqual([], offences, offences)

    def test_the_exempt_write_is_the_assignment_and_not_a_log_line(self) -> None:
        """DERIVED -- that change's tasks.md 2.1: "the escaped variable is written
        to the file and goes nowhere else". The exemption above is granted to the
        escaping point's single emitting line, so that line has to BE the
        assignment rather than anything else the point might print."""
        point = self.escaping_point()
        escaped = escaped_variable(point)
        parameter = name_parameter(point)
        emitting = point.emitting()
        self.assertEqual(
            1, len(emitting), f"`{point.name}` emits on {len(emitting)} lines"
        )
        _, text = emitting[0]
        self.assertTrue(
            escaped and expands(text, escaped),
            f"the escaping point's one emitting line does not expand `${escaped}`, so "
            "what it writes into the file is not the escaped value",
        )
        self.assertTrue(
            parameter and expands(text, parameter),
            f"the escaping point's one emitting line does not expand `${parameter}`, "
            "so what it writes into the file carries no name",
        )
        self.assertIn(
            "=",
            text,
            "the escaping point's one emitting line writes no `=`, so it does not "
            "write an assignment",
        )


# --------------------------------------------------------------------------
# The reads above are reads
# --------------------------------------------------------------------------

CONFORMING_BODY = r"""set -euo pipefail
umask 077

altered=''

render() {
  local name="$1"
  local value="$2"
  case "$value" in
    *'\'*|*'"'*|*"'"*|*'$'*|*'#'*|*$'\n'*|[[:space:]]*|*[[:space:]])
      altered="$altered $name"
      ;;
  esac
  local escaped="$value"
  escaped="${escaped//\\/\\\\}"
  escaped="${escaped//\"/\\\"}"
  escaped="${escaped//\$/\$\$}"
  printf '%s="%s"\n' "$name" "$escaped"
}

{
  render ACME_EMAIL "$ACME_EMAIL"
  render POSTGRES_USER "$POSTGRES_USER"
} >platform/.env

if [ -n "$altered" ]; then
  echo "::notice::the previous rendering would have altered:$altered"
else
  echo "::notice::the previous rendering would have altered no rendered value"
fi
"""

CONFORMING_SECRETS = frozenset({"ACME_EMAIL", "POSTGRES_USER"})


def conforming_step(body: str | None = None) -> dict:
    return {
        "name": "Render .env from secrets",
        "env": {
            "ACME_EMAIL": "${{ secrets.PLATFORM_ACME_EMAIL }}",
            "POSTGRES_USER": "${{ secrets.PLATFORM_POSTGRES_USER }}",
        },
        "run": CONFORMING_BODY if body is None else body,
    }


def conforming_workflow(body: str | None = None) -> dict:
    return {"jobs": {"deploy": {"steps": [conforming_step(body)]}}}


class TestTheConformingFixtureSatisfiesEveryRead(unittest.TestCase):
    """Every predicate in this file is satisfiable at once, demonstrated over a
    step this file supplies.

    Without this, a predicate no implementation could satisfy would be
    indistinguishable from one whose implementation has not landed yet -- and the
    implementer would discover the difference by rewriting the workflow to fit a
    check rather than to fit the design. What the fixture below is NOT is a
    recommended implementation: it is the smallest shape every reader here can
    see, and the design decides the rest.

    This class is expected to pass from the moment it is written, which is the
    opposite of most of this file, and is stated so that its passing is not
    mistaken for coverage of the change.
    """

    def test_one_step_of_the_fixture_workflow_writes_the_file(self) -> None:
        self.assertEqual(conforming_step(), sole_render_step(conforming_workflow()))

    def test_the_escaping_point_is_found(self) -> None:
        self.assertEqual("render", sole_escaping_point(CONFORMING_BODY).name)

    def test_the_point_emits_once_and_that_line_is_the_assignment(self) -> None:
        point = sole_escaping_point(CONFORMING_BODY)
        emitting = point.emitting()
        self.assertEqual(1, len(emitting))
        self.assertIn("=", emitting[0][1])
        self.assertTrue(expands(emitting[0][1], "escaped"))
        self.assertTrue(expands(emitting[0][1], "name"))

    def test_the_substitutions_read_in_order_and_replace_every_occurrence(self) -> None:
        relevant = escaping_substitutions(sole_escaping_point(CONFORMING_BODY))
        self.assertEqual(["\\", '"', "$"], [item.target for item in relevant])
        self.assertEqual(
            ["\\\\", '\\"', "$$"], [unescape(item.replacement) for item in relevant]
        )
        self.assertTrue(all(item.glob for item in relevant))
        self.assertEqual({"escaped"}, {item.variable for item in relevant})

    def test_the_block_reads_as_calls_only(self) -> None:
        block = env_file_block(CONFORMING_BODY)
        self.assertEqual([], call_offences(block, "render"))
        self.assertEqual(["ACME_EMAIL", "POSTGRES_USER"], rendered_names(block, "render"))

    def test_the_file_is_redirected_into_once(self) -> None:
        self.assertEqual(
            1,
            sum(
                1
                for _, text in code_lines(CONFORMING_BODY)
                if ENV_FILE_REDIRECT.search(text)
            ),
        )

    def test_the_detection_set_reads_as_decision_nines(self) -> None:
        self.assertEqual(set(REPORTED_CHARACTERS), detected_anywhere(CONFORMING_BODY))

    def test_both_whitespace_edges_read(self) -> None:
        self.assertEqual({"leading", "trailing"}, detected_edges(CONFORMING_BODY))

    def test_no_positional_offence_is_reported_over_it(self) -> None:
        self.assertEqual(set(), positional_offences(CONFORMING_BODY))

    def test_the_report_has_a_naming_branch_and_a_silent_one(self) -> None:
        lines = report_lines(CONFORMING_BODY)
        self.assertEqual(2, len(lines))
        self.assertEqual(1, sum(1 for _, text in lines if expanded_names(text)))
        self.assertEqual(1, sum(1 for _, text in lines if not expanded_names(text)))

    def test_the_name_parameter_and_the_escaped_variable_read(self) -> None:
        point = sole_escaping_point(CONFORMING_BODY)
        self.assertEqual("name", name_parameter(point))
        self.assertEqual("escaped", escaped_variable(point))

    def test_the_accumulator_is_built_from_the_name_parameter(self) -> None:
        self.assertTrue(
            any(
                assignment.variable == "altered" and expands(assignment.value, "name")
                for assignment in assignments(CONFORMING_BODY)
            )
        )

    def test_no_disclosure_is_reported_over_it(self) -> None:
        point = sole_escaping_point(CONFORMING_BODY)
        exempt = {number for number, _ in point.emitting()}
        self.assertEqual(
            [],
            disclosure_offences(CONFORMING_BODY, CONFORMING_SECRETS, "escaped", exempt),
        )

    def test_it_takes_no_command_substitution(self) -> None:
        self.assertIsNone(COMMAND_SUBSTITUTION.search(CONFORMING_BODY))


class TestTheseReadsDiscriminate(unittest.TestCase):
    """Every read in this file is a static read of a committed file, so a green
    run establishes nothing on its own: a predicate that reported no offence
    whatever it was given would satisfy every assertion above, and would do so
    most convincingly on the day the implementation landed.

    Each test below hands a predicate material built to falsify it, supplied by
    this file rather than taken from the tree. The material is a variant of the
    conforming body above, so what each test establishes is that the predicate
    responds to the one property that variant breaks.

    This class is expected to pass from the moment it is written.
    """

    def variant(self, old: str, new: str) -> str:
        self.assertIn(old, CONFORMING_BODY, "the fixture no longer carries what this edits")
        return CONFORMING_BODY.replace(old, new, 1)

    # -- the escaping point ------------------------------------------------

    def test_a_body_with_no_function_has_no_escaping_point(self) -> None:
        """The state the committed workflow is in today: eight `printf` lines and
        no point at all."""
        body = "{\n" + r"  printf 'A=%s\n' " + '"$A"\n} >platform/.env\n'
        self.assertEqual([], escaping_points(body))
        with self.assertRaises(AssertionError):
            sole_escaping_point(body)

    def test_a_function_that_escapes_nothing_is_not_an_escaping_point(self) -> None:
        body = "log() {\n" + r"  printf '%s\n' " + '"$1"\n}\n'
        self.assertEqual([], escaping_points(body))

    def test_a_parameter_expansion_does_not_end_the_function(self) -> None:
        """The reason the closing brace is found by a whole-line rule: the body of
        the very function this reads is made of `${…}`."""
        point = sole_escaping_point(CONFORMING_BODY)
        self.assertIn("printf", point.text)
        self.assertIn("esac", point.text)

    def test_both_function_spellings_read(self) -> None:
        for opening in ("render() {", "function render {"):
            body = opening + "\n" + r'  v="${v//\\/\\\\}"' + "\n}\n"
            self.assertEqual(["render"], [point.name for point in escaping_points(body)], body)

    # -- the order ---------------------------------------------------------

    def test_escaping_the_quote_before_the_backslash_is_reported(self) -> None:
        """The defect Decision 4 names: a later `\\` pass doubles the backslash
        the `"` pass introduced itself."""
        reordered = self.variant(
            '  escaped="${escaped//\\\\/\\\\\\\\}"\n  escaped="${escaped//\\"/\\\\\\"}"',
            '  escaped="${escaped//\\"/\\\\\\"}"\n  escaped="${escaped//\\\\/\\\\\\\\}"',
        )
        relevant = escaping_substitutions(sole_escaping_point(reordered))
        self.assertEqual(['"', "\\", "$"], [item.target for item in relevant])

    def test_a_dollar_replaced_by_a_backslash_escape_is_reported(self) -> None:
        """Decision 3: `\\$` is honoured only inside double quotes, so it is a
        consequence of backslash processing rather than the parser's own rule for
        `$`. Both measured identical over 51 values, which is exactly why a check
        on the result would not separate them."""
        altered = self.variant(
            r'escaped="${escaped//\$/\$\$}"', r'escaped="${escaped//\$/\\\$}"'
        )
        dollar = [
            item for item in escaping_substitutions(sole_escaping_point(altered))
            if item.target == "$"
        ][0]
        self.assertEqual("\\$", unescape(dollar.replacement))

    def test_a_single_slash_substitution_reads_as_not_global(self) -> None:
        altered = self.variant(
            r'escaped="${escaped//\$/\$\$}"', r'escaped="${escaped/\$/\$\$}"'
        )
        dollar = [
            item for item in escaping_substitutions(sole_escaping_point(altered))
            if item.target == "$"
        ][0]
        self.assertFalse(dollar.glob)

    def test_substitutions_spread_over_two_variables_are_visible(self) -> None:
        altered = self.variant(
            r'escaped="${escaped//\$/\$\$}"', r'escaped="${other//\$/\$\$}"'
        )
        self.assertEqual(
            {"escaped", "other"},
            {item.variable for item in escaping_substitutions(sole_escaping_point(altered))},
        )

    # -- the block ---------------------------------------------------------

    def test_a_printf_smuggled_into_the_block_is_reported(self) -> None:
        """The defect the choke point exists to catch and a convention does not: a
        ninth value added by someone who did not read the file."""
        altered = self.variant(
            '  render POSTGRES_USER "$POSTGRES_USER"',
            '  render POSTGRES_USER "$POSTGRES_USER"\n'
            + r"  printf 'POSTGRES_PASSWORD=%s\n' " + '"$POSTGRES_PASSWORD"',
        )
        offences = call_offences(env_file_block(altered), "render")
        self.assertEqual(1, len(offences), offences)
        self.assertIn("POSTGRES_PASSWORD", offences[0])

    def test_the_floor_is_read_from_the_example_file_rather_than_written_here(self) -> None:
        """That change's tasks.md 1.4: a literal count of eight goes stale on the
        first addition. A ninth variable added to a supplied example file is in
        the floor without this module being edited."""
        holder = tempfile.TemporaryDirectory(prefix="env-example-")
        self.addCleanup(holder.cleanup)
        path = Path(holder.name) / ".env.example"
        path.write_text(
            "# documentation\nACME_EMAIL=\nPOSTGRES_USER=\nA_NINTH_VALUE=\n",
            encoding="utf-8",
        )
        documented = env_example_variables(path)
        self.assertEqual(["ACME_EMAIL", "POSTGRES_USER", "A_NINTH_VALUE"], documented)
        rendered = set(rendered_names(env_file_block(CONFORMING_BODY), "render"))
        self.assertEqual(["A_NINTH_VALUE"], sorted(set(documented) - rendered))

    def test_a_second_redirect_into_the_file_is_visible(self) -> None:
        altered = self.variant(
            "} >platform/.env\n",
            "} >platform/.env\n" + r"printf 'X=%s\n' " + '"$X" >>platform/.env\n',
        )
        self.assertEqual(
            2, sum(1 for _, text in code_lines(altered) if ENV_FILE_REDIRECT.search(text))
        )

    def test_the_example_file_is_not_read_as_the_rendered_one(self) -> None:
        self.assertIsNone(ENV_FILE_REDIRECT.search("printf x >platform/.env.example"))
        self.assertIsNotNone(ENV_FILE_REDIRECT.search("} >platform/.env"))
        self.assertIsNotNone(ENV_FILE_REDIRECT.search('printf x >>"platform/.env"'))

    def test_a_second_step_writing_the_file_is_reported(self) -> None:
        workflow = conforming_workflow()
        workflow["jobs"]["deploy"]["steps"].append(
            {"name": "One more", "run": 'printf \'X=1\\n\' >>platform/.env\n'}
        )
        self.assertEqual(2, len(env_file_writing_steps(workflow)))
        with self.assertRaises(AssertionError):
            sole_render_step(workflow)

    # -- the detection set -------------------------------------------------

    def test_a_dropped_member_is_reported(self) -> None:
        """The mistake Decision 9 records rather than quietly fixing: round 5
        varied the character, held the position, and released the apostrophe."""
        altered = self.variant("""*'"'*|*"'"*""", """*'"'*""")
        self.assertEqual({"'"}, set(REPORTED_CHARACTERS) - detected_anywhere(altered))

    def test_an_added_member_is_reported(self) -> None:
        altered = self.variant("*'#'*", "*'#'*|*'%'*")
        self.assertEqual({"%"}, detected_anywhere(altered) - set(REPORTED_CHARACTERS))

    def test_a_hash_test_narrowed_to_a_preceding_space_is_reported(self) -> None:
        """The exact edit that change's tasks.md 1.5 names: the set is unchanged,
        so a check reading only the set passes, and the positional re-derivation
        is back."""
        altered = self.variant("*'#'*", '*" #"*')
        self.assertEqual(set(REPORTED_CHARACTERS), detected_anywhere(altered) | {"#"})
        self.assertEqual({"#"}, positional_offences(altered))

    def test_an_apostrophe_test_anchored_to_the_opening_position_is_reported(self) -> None:
        altered = self.variant("""*"'"*""", """"'"*""")
        self.assertEqual({"'"}, positional_offences(altered))

    def test_a_whitespace_edge_dropped_is_reported(self) -> None:
        altered = self.variant("|[[:space:]]*|*[[:space:]]", "|*[[:space:]]")
        self.assertEqual({"trailing"}, detected_edges(altered))

    def test_a_literal_space_is_not_read_as_the_whitespace_class(self) -> None:
        """Round 6 measured both ends stripping a tab as well as a space, so a
        detector spelling only a space is half a detector."""
        altered = self.variant("[[:space:]]*|*[[:space:]]", "' '*|*' '")
        self.assertEqual(set(), detected_edges(altered))

    def test_a_bracketed_space_and_tab_does_read_as_the_class(self) -> None:
        altered = self.variant("[[:space:]]*|*[[:space:]]", "[ \t]*|*[ \t]")
        self.assertEqual({"leading", "trailing"}, detected_edges(altered))

    def test_a_double_bracket_condition_is_read_as_a_pattern(self) -> None:
        """`case` is not the only way bash asks the question, so the reader is
        shown one of each rather than one."""
        self.assertEqual({"$"}, detected_anywhere("""if [[ "$value" == *'$'* ]]; then :; fi\n"""))

    def test_a_newline_spelled_with_ansi_c_quoting_reads_as_a_line_break(self) -> None:
        """The member round 5 missed, and the most destructive of them: `printf
        'NAME=%s\\n'` writes a second physical line and the value is truncated at
        the break."""
        body = "case $v in\n" + r"*$'\n'*" + ") x=1 ;;\nesac\n"
        self.assertEqual({"\n"}, detected_anywhere(body))

    def test_a_step_that_tests_nothing_yields_no_detection(self) -> None:
        """The state the committed workflow is in today, and the reason the
        positional assertion guards on this before reading offences."""
        self.assertEqual([], detections("printf 'A=%s\\n' \"$A\" >platform/.env\n"))

    # -- the report --------------------------------------------------------

    def test_a_report_with_no_silent_branch_is_visible(self) -> None:
        altered = self.variant(
            'else\n  echo "::notice::the previous rendering would have altered no '
            'rendered value"\n',
            "else\n  :\n",
        )
        self.assertEqual([], [text for _, text in report_lines(altered) if not expanded_names(text)])

    def test_a_report_with_no_naming_branch_is_visible(self) -> None:
        altered = self.variant(
            'echo "::notice::the previous rendering would have altered:$altered"',
            'echo "::notice::the previous rendering altered something"',
        )
        self.assertEqual([], [text for _, text in report_lines(altered) if expanded_names(text)])

    def test_a_step_with_no_report_at_all_is_visible(self) -> None:
        self.assertEqual([], report_lines("printf 'A=%s\\n' \"$A\" >platform/.env\n"))

    def test_an_accumulator_not_built_from_the_name_parameter_is_visible(self) -> None:
        altered = self.variant('altered="$altered $name"', 'altered="$altered $value"')
        parameter = name_parameter(sole_escaping_point(altered))
        self.assertEqual("name", parameter)
        self.assertEqual(
            [],
            [
                assignment
                for assignment in assignments(altered)
                if assignment.variable == "altered" and expands(assignment.value, parameter)
            ],
        )

    def test_a_summary_redirect_is_not_read_as_naming_a_variable(self) -> None:
        """A report written to the job summary expands `$GITHUB_STEP_SUMMARY` and
        names nothing of its own; reading that as a naming branch would let a
        report with no names pass."""
        self.assertEqual(set(), expanded_names('echo "::notice::none" >>"$GITHUB_STEP_SUMMARY"'))

    # -- the disclosure sweep ----------------------------------------------

    def test_a_debug_echo_of_the_escaped_value_is_reported(self) -> None:
        """The one shape of a credential that masking does not cover, because
        masking is registered against the value the escaping transformed."""
        write = r'''  printf '%s="%s"\n' "$name" "$escaped"'''
        altered = self.variant(write, '  echo "rendering $escaped" >&2\n' + write)
        point = sole_escaping_point(altered)
        emitting = point.emitting()
        self.assertEqual(2, len(emitting))
        offences = disclosure_offences(altered, set(), "escaped", {emitting[1][0]})
        self.assertEqual(1, len(offences), offences)
        self.assertIn("ESCAPED", offences[0])

    def test_a_notice_carrying_a_rendered_value_is_reported(self) -> None:
        altered = self.variant(
            'echo "::notice::the previous rendering would have altered:$altered"',
            'echo "::notice::altered:$altered -- $ACME_EMAIL"',
        )
        point = sole_escaping_point(altered)
        exempt = {number for number, _ in point.emitting()}
        offences = disclosure_offences(altered, CONFORMING_SECRETS, "escaped", exempt)
        self.assertEqual(1, len(offences), offences)
        self.assertIn("ACME_EMAIL", offences[0])

    def test_a_redirect_into_the_job_summary_counts_as_emitting(self) -> None:
        self.assertEqual(
            [(1, '  : >>"$GITHUB_STEP_SUMMARY"')],
            emitting_lines('  : >>"$GITHUB_STEP_SUMMARY"\n'),
        )

    def test_a_line_that_reads_a_value_without_printing_it_is_not_a_disclosure(self) -> None:
        """Reading a value is not emitting one -- `case "$value" in` is the
        detection itself, and a sweep that reported it would report the report."""
        self.assertEqual(
            [], disclosure_offences('case "$value" in\n', {"value"}, "escaped", set())
        )

    # -- command substitution ----------------------------------------------

    def test_both_spellings_of_command_substitution_are_seen(self) -> None:
        self.assertIsNotNone(COMMAND_SUBSTITUTION.search('x="$(printf %s "$v")"'))
        self.assertIsNotNone(COMMAND_SUBSTITUTION.search('x=`printf %s "$v"`'))


if __name__ == "__main__":
    unittest.main()
