"""Static-assertion tests for the Molecule fixtures' kernel-held loop devices.

Derived from the delta specification of the OpenSpec change
`namespace-the-molecule-loop-devices`, before any implementation of that change
existed. The path that delta sits at is not written here: a change's artifacts
move when it is archived, and this repository's citation convention is to name
the change and the artifact in prose instead.

The change modifies one requirement -- *Ansible Configuration Is Verified in
Continuous Integration and Gates the Merge*, in
`openspec/specs/iac-cicd-pipeline/spec.md` -- adding six scenarios. Every one of
the six is a static read of a committed file, which is why all six land here
rather than in `terraform test` or in Molecule (AGENTS.md, "Testing"): a
property held only inside a Molecule scenario covers only the pull requests that
trigger that scenario, and the suite's trigger is narrowed by change detection.

WHAT THIS MODULE IS FOR
-----------------------
A loop device minor is a handle the machine's KERNEL holds. An association made
inside a Molecule container is not namespaced by that container: it outlives the
container, so a single working tree's consecutive runs collide with themselves,
and two working trees collide with each other. A fixture inheriting one inherits
whatever the previous run left on it -- including a filesystem a previous
converge created, which makes `molecule/default`'s own subject (the role
formatting an UNFORMATTED device) a no-op that passes.

Seven propositions, none of which anything in this repository read before this
module, each a static read of a committed file:

1. No fixture play beside an authored scenario definition names a loop minor as
   a literal.
2. Every fixture play deriving a device derives it from a value the entry point
   supplies, read through `lookup('env', ...)`.
3. The entry point supplies a variable of that name -- the two halves are
   written in different languages with nothing but a variable name between them,
   so a rename on either side resolves to an UNSET value rather than to an error.
4. The entry point derives that value from the working tree's own path rather
   than fixing it. An entry point exporting a constant satisfies every check
   about the variable's existence while reinstating the shared literal.
5. A fixture play that associates a loop device releases it earlier in the same
   file, reads what holds it before releasing it, and REFUSES on that read. A
   play that reads, registers and releases regardless satisfies every read-only
   assertion while doing the exact thing the requirement forbids.
6. The enumeration of fixture plays deriving a handle is not empty. Every check
   above reports green on an empty set, so this one holds the rest up.
7. The workflow that runs the suite reaches it through the entry point. Without
   that, the fixtures' refusal fires on a required check for a reason no
   assertion names.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_the_molecule_fixtures_namespace_their_loop_devices\\
        .TestTheFixturePlayEnumerationRefusesToBeEmpty\\
        .test_some_fixture_play_derives_a_kernel_held_handle

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling import below resolve. Standard library plus
PyYAML -- no network, no credential, no container runtime, no Terraform binary,
and nothing here spawns a process at all.

WHAT NO ASSERTION HERE ESTABLISHES
----------------------------------
Nothing here associates a loop device, runs Ansible, or reads a host. A green
run establishes that the COMMITTED FILES carry these shapes -- never that a run
refused a foreign minor. The run-time refusal is not reachable in this
repository: the guard lives in `prepare`, and Molecule runs nothing between
`create` and `prepare` in which a foreign association could be planted for it to
refuse. That is the delta's own reasoning for specifying the static shape.

Nor does the attribution guard's CONDITION get read. What is checked is that a
refusal stands between the read and the release and mentions what the read
registered; whether its predicate is the right one is a question for review.

Nor is the arithmetic of the derivation checked. That two different working
trees resolve two different bases is established by running the entry point,
which this suite may not do, and that change's own tasks.md carries it.

PROVENANCE ANNOTATION
---------------------
Every assertion below is annotated SPECIFIED (it traces to SHALL text in the
delta) or DERIVED (it traces to that change's `design.md`/`tasks.md`, or to this
authoring pass's own judgement), which is the convention
`test_ci_configuration.py` established and the sixteen modules beside it follow.
That change's `test-plan.md` carries the scenario-to-test map, the baseline, the
unresolved project questions and the cases deliberately left uncovered.

NOTHING IN THIS FILE EDITS, DELETES OR DISABLES AN EXISTING TEST. Where a helper
a module beside this one already has is needed, it is imported rather than
restated -- which is also what keeps the Galaxy exclusion below derived from
`ansible/requirements.yml` rather than from a role name written down twice.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from test_ci_configuration import (
    ANSIBLE_VERIFY,
    DEFAULT_FIXTURE_MANIFEST,
    PINNED_IMAGE,
    ROOT,
    ScenarioTreeFixtureMixin,
    authored_scenario_files,
    galaxy_role_directories,
    load_yaml,
    read_text,
    scenario_document,
    step_label,
    steps,
    uncommented,
)

# --------------------------------------------------------------------------
# Identifiers this file names
# --------------------------------------------------------------------------

# The entry point that supplies this working tree's namespace and, after this
# change, its loop-device base. Named by path because the workflow assertion
# below has to read a specific file: an assertion whose target is absent must
# FAIL rather than skip, and `read_text`/`load_yaml` raise on an absent file.
ENTRY_POINT = "ansible/scripts/run-molecule"
ENTRY_POINT_NAME = Path(ENTRY_POINT).name

# The variable the entry point supplies for the kernel-held handle.
#
# DERIVED, and deliberately so. The instance-name checks in
# `test_ci_configuration.py` assert no spelling at all, because that obligation
# is over names each SCENARIO carries and a check can read whatever variable a
# scenario names. This one cannot take that route: the delta says the entry
# point's two obligations "SHALL be checked over the entry point itself", and
# the entry point carries no such carrier to read a name out of. The name comes
# from that change's design.md, Decision 2.
#
# The cost is stated rather than hidden: a COORDINATED rename of both sides
# fails this one check and costs a visible edit here. That is the polarity this
# requirement takes everywhere else -- an unrecognised construction is refused
# rather than passed over. A ONE-SIDED rename, which is the failure the delta's
# own scenario names, is caught by
# `TestTheFixturesAndTheEntryPointAgreeOnTheName`, which reads no spelling.
LOOP_BASE_VARIABLE = "INFRA_WORKTREE_LOOP_BASE"

SCENARIO_DEFINITION = "molecule.yml"
PLAY_SUFFIXES = (".yml", ".yaml")

# A loop device named by a literal minor: `/dev/loop87`. The trailing digit is
# what makes it a claim on a kernel-held handle rather than the word "loop".
LOOP_MINOR_LITERAL = re.compile(r"/dev/loop(?P<minor>\d+)")

# The same claim made through the device node rather than the path. Major 7 is
# the loop driver, so `mknod ... b 7 87` names minor 87 as a literal even where
# the path beside it is interpolated -- which is exactly the shape three of this
# role's fixtures are in today.
MKNOD_LITERAL_MINOR = re.compile(r"\bmknod\b[^\n]*?\bb\s+7\s+(?P<minor>\d+)")

# A loop device whose minor is interpolated rather than written down. Two forms
# are recognised: the path with a Jinja expression in it, and the path
# concatenated to one. A play claiming a handle by any OTHER construction is
# refused rather than passed over -- see
# `plays_claiming_a_handle_by_an_unrecognised_construction`.
LOOP_DEVICE_DERIVED = re.compile(r"/dev/loop\s*\{\{|['\"]/dev/loop['\"]\s*~")

# Whether a play claims a kernel-held handle at all: it drives `losetup`, or it
# creates a loop device node.
LOOP_HANDLE_CLAIM = re.compile(r"\blosetup\b|\bmknod\b[^\n]*?\bb\s+7\b")

# The controller's environment, read from a play. `ansible_env` is deliberately
# NOT recognised: inside a Molecule play that fact belongs to the MANAGED NODE
# -- the container -- which never sees what the entry point exported on the
# controller, so a play reading it would not be reading the entry point's value
# at all.
ENV_LOOKUP = re.compile(
    r"lookup\(\s*['\"](?:ansible\.builtin\.)?env['\"]\s*,\s*['\"](?P<name>[^'\"]+)['\"]"
)

JINJA_EXPRESSION = re.compile(r"\{\{.*?\}\}", re.DOTALL)

# A YAML line that opens a key, used to tell a folded command's continuation
# lines from the next mapping entry.
YAML_KEY_LINE = re.compile(r"^\s*-?\s*[A-Za-z_][\w.]*:(\s|$)")


# --------------------------------------------------------------------------
# The enumeration: the fixture plays beside each authored scenario definition
# --------------------------------------------------------------------------


def fixture_plays(root: Path | None = None) -> list[Path]:
    """Every fixture play beside a scenario definition THIS repository authors.

    A wider set than `authored_scenario_files()`, which returns the definitions
    themselves: the handles this module is about are claimed in `prepare.yml`,
    `converge.yml` and `verify.yml`, none of which that helper reaches. The
    Galaxy exclusion is inherited rather than restated -- these plays are found
    BESIDE the definitions that helper already excludes installed content from,
    so content pinned in `ansible/requirements.yml` drops out here for the same
    reason and by the same derivation from that manifest.
    """
    base = ROOT if root is None else root
    plays: list[Path] = []
    for definition in authored_scenario_files(base):
        for path in sorted(definition.parent.iterdir()):
            if not path.is_file():
                continue
            if path.name == SCENARIO_DEFINITION or path.suffix not in PLAY_SUFFIXES:
                continue
            plays.append(path)
    return plays


def _label(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _body(path: Path) -> str:
    """A play's text with whole-line comments dropped.

    A comment naming `/dev/loop87` is prose about what is no longer done, not a
    claim on minor 87 -- the same reading `uncommented()` was written for in
    `test_ci_configuration.py`. A TRAILING comment on a line of content is not
    stripped and is therefore read as content: the refusing direction, and it
    costs a visible edit rather than a silent gap.
    """
    return uncommented(path.read_text(encoding="utf-8"))


def plays_naming_a_kernel_held_handle_as_a_literal(root: Path | None = None) -> list[str]:
    """Report each fixture play naming a loop minor as a literal."""
    base = ROOT if root is None else root
    offenders = []
    for path in fixture_plays(base):
        body = _body(path)
        found = sorted(
            {match.group(0) for match in LOOP_MINOR_LITERAL.finditer(body)}
            | {match.group(0).strip() for match in MKNOD_LITERAL_MINOR.finditer(body)}
        )
        if found:
            offenders.append(f"{_label(path, base)} names {found}")
    return offenders


def plays_deriving_a_kernel_held_handle(root: Path | None = None) -> list[str]:
    """Report each fixture play whose loop device is interpolated rather than
    written down.

    This is the enumeration the delta obliges to refuse to be empty. It counts a
    play whose handle is DERIVED -- not the wider set of plays claiming a handle
    by any means, which is non-empty today by literal and would therefore report
    the enumeration healthy in the one condition that empties every check over
    it.

    That the derivation reaches the ENTRY POINT's value, rather than some other
    value, is established by `deriving_plays_reading_no_supplied_value` and the
    check over it. A play deriving from something else is counted here and fails
    there, rather than dropping silently out of the count.
    """
    base = ROOT if root is None else root
    return [
        _label(path, base)
        for path in fixture_plays(base)
        if LOOP_DEVICE_DERIVED.search(_body(path))
    ]


def plays_claiming_a_handle_by_an_unrecognised_construction(
    root: Path | None = None,
) -> list[str]:
    """Report each fixture play that claims a kernel-held handle by a
    construction neither recognised as a literal nor as a derivation.

    A list of recognised constructions goes stale exactly as a list of paths
    does, and the polarity that answers one answers the other: an unrecognised
    construction ignored is a silent gap, where one refused costs a visible
    edit. This is the same refusal the requirement places on its controller-read
    check.
    """
    base = ROOT if root is None else root
    offenders = []
    for path in fixture_plays(base):
        body = _body(path)
        if not LOOP_HANDLE_CLAIM.search(body):
            continue
        if LOOP_MINOR_LITERAL.search(body) or MKNOD_LITERAL_MINOR.search(body):
            continue
        if LOOP_DEVICE_DERIVED.search(body):
            continue
        offenders.append(
            f"{_label(path, base)} drives losetup or creates a loop device node, but names "
            f"its minor by a construction this check does not recognise; it can be read as "
            f"neither a literal nor a derivation, so it is refused rather than passed over"
        )
    return offenders


# --------------------------------------------------------------------------
# The name the two halves are joined by
# --------------------------------------------------------------------------


def _scenario_supplied_environment(definition: Path) -> set[str]:
    """The environment names a scenario's OWN definition supplies to its plays.

    Read so that a play reading one of them is not mistaken for a play reading
    the entry point's value -- `multiple-devices-reverse-order` supplies one
    this way today.
    """
    if not definition.is_file():
        return set()
    document = load_yaml(definition)
    if not isinstance(document, dict):
        return set()
    provisioner = document.get("provisioner")
    if not isinstance(provisioner, dict):
        return set()
    environment = provisioner.get("env")
    return set(environment) if isinstance(environment, dict) else set()


def _names_a_play_reads(path: Path) -> set[str]:
    """The controller-environment names one play reads, minus the ones supplied
    by something other than the entry point.

    Two exclusions, each with a reason rather than a category. A name the
    scenario's own `molecule.yml` declares in its provisioner environment is
    supplied by that definition. A `MOLECULE_`-prefixed name is supplied by
    Molecule itself. Neither is a value the entry point exports, so neither is
    evidence of a mismatch between the two halves.
    """
    supplied_by_the_scenario = _scenario_supplied_environment(path.parent / SCENARIO_DEFINITION)
    return {
        match.group("name")
        for match in ENV_LOOKUP.finditer(_body(path))
        if not match.group("name").startswith("MOLECULE_")
        and match.group("name") not in supplied_by_the_scenario
    }


def environment_names_the_fixtures_read(root: Path | None = None) -> dict[str, list[str]]:
    """Every controller-environment name the DERIVING fixture plays read, and
    where."""
    base = ROOT if root is None else root
    deriving = set(plays_deriving_a_kernel_held_handle(base))
    found: dict[str, list[str]] = {}
    for path in fixture_plays(base):
        label = _label(path, base)
        if label not in deriving:
            continue
        for name in sorted(_names_a_play_reads(path)):
            found.setdefault(name, []).append(label)
    return found


def deriving_plays_reading_no_supplied_value(root: Path | None = None) -> list[str]:
    """Report each play deriving a handle from no value the entry point could
    have supplied -- it interpolates a device but reads no controller
    environment name of its own."""
    base = ROOT if root is None else root
    deriving = set(plays_deriving_a_kernel_held_handle(base))
    offenders = []
    for path in fixture_plays(base):
        label = _label(path, base)
        if label not in deriving:
            continue
        if not _names_a_play_reads(path):
            offenders.append(
                f"{label} interpolates its loop device but reads no controller environment "
                f"name, so nothing connects it to the value the entry point supplies"
            )
    return offenders


# --------------------------------------------------------------------------
# Reading the entry point: what it supplies, and where the value comes from
# --------------------------------------------------------------------------

SHELL_ASSIGNMENT = re.compile(
    r"^\s*(?:export\s+|local\s+|declare\s+|readonly\s+)*"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*?)\s*\\?$"
)
SHELL_FUNCTION = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_-]*)\s*\(\)\s*\{\s*$")
SHELL_REFERENCE = re.compile(r"\$\{?(?P<name>\d+|[A-Za-z_][A-Za-z0-9_]*)\}?")
COMMAND_SUBSTITUTION = re.compile(r"\$\(\s*(?!\()(?P<call>[^()]*)\)")
OUTPUT_STATEMENT = re.compile(r"\b(printf|echo)\b")

# What produces the working tree's own path. `--show-toplevel` resolves to the
# WORKING TREE's root in a linked working tree, which is the whole point; `pwd`
# and `$PWD` are the other two ways a shell reaches it.
ROOT_PRODUCER = re.compile(r"git\s+rev-parse[^\n]*--show-toplevel|\bpwd\b|\$\{?PWD\}?")

ENVIRONMENT_NAME = re.compile(r"[A-Z][A-Z0-9_]*")


def shell_functions(text: str) -> dict[str, str]:
    """Each `name() { ... }` function's body, keyed by name.

    Recognises the one-function-per-line-brace form this repository's shell is
    written in; a function opened any other way is not found, and a check
    resting on that reads the function as absent -- which fails rather than
    passes.
    """
    bodies: dict[str, str] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        opened = SHELL_FUNCTION.match(lines[index])
        if not opened:
            index += 1
            continue
        collected: list[str] = []
        index += 1
        while index < len(lines) and lines[index].rstrip() != "}":
            collected.append(lines[index])
            index += 1
        bodies[opened.group("name")] = "\n".join(collected)
        index += 1
    return bodies


def _references(value: str) -> set[str]:
    return {match.group("name") for match in SHELL_REFERENCE.finditer(value)}


def _calls(value: str) -> list[tuple[str, str]]:
    calls = []
    for match in COMMAND_SUBSTITUTION.finditer(value):
        tokens = match.group("call").split()
        if tokens:
            calls.append((tokens[0], " ".join(tokens[1:])))
    return calls


def _function_produces_the_root(name: str, functions: dict[str, str]) -> bool:
    body = functions.get(name)
    return body is not None and bool(ROOT_PRODUCER.search(body))


def function_propagates_its_argument(
    name: str, functions: dict[str, str], seen: frozenset[str] = frozenset()
) -> bool:
    """Whether a shell function's OUTPUT depends on the argument it was handed.

    This is what separates an entry point that derives a value from one that
    supplies a constant. `loop_base=$(loop_base_for "$root")` mentions the root
    on the calling line whatever the callee does, so a check reading only the
    call site would pass over a `loop_base_for` that ignores its argument and
    prints a fixed number -- which is precisely the entry point the delta says
    SHALL fail.
    """
    body = functions.get(name)
    if body is None or name in seen:
        return False
    seen = seen | {name}
    tainted = {"1"}
    changed = True
    while changed:
        changed = False
        for line in body.splitlines():
            assignment = SHELL_ASSIGNMENT.match(line)
            if not assignment or assignment.group("name") in tainted:
                continue
            if _value_is_derived(assignment.group("value"), tainted, functions, seen):
                tainted.add(assignment.group("name"))
                changed = True
    return any(
        OUTPUT_STATEMENT.search(line) and _value_is_derived(line, tainted, functions, seen)
        for line in body.splitlines()
    )


def _value_is_derived(
    value: str, tainted: set[str], functions: dict[str, str], seen: frozenset[str]
) -> bool:
    """Whether a shell expression's value flows from something already tainted.

    A command substitution is read THROUGH: calling a function that produces the
    working tree's path taints unconditionally; calling one that propagates its
    argument taints where the argument is tainted; calling anything else taints
    where its arguments are.
    """
    remainder = value
    for match in COMMAND_SUBSTITUTION.finditer(value):
        remainder = remainder.replace(match.group(0), " ")
    for callee, arguments in _calls(value):
        if _function_produces_the_root(callee, functions):
            return True
        if callee in functions:
            if function_propagates_its_argument(callee, functions, seen) and (
                _references(arguments) & tainted
            ):
                return True
        elif _references(arguments) & tainted:
            return True
    if ROOT_PRODUCER.search(remainder):
        return True
    return bool(_references(remainder) & tainted)


def shell_assignments(text: str) -> dict[str, list[str]]:
    """Every `name=value` in a shell script, in order, keyed by name."""
    found: dict[str, list[str]] = {}
    for line in uncommented(text).splitlines():
        assignment = SHELL_ASSIGNMENT.match(line)
        if assignment:
            found.setdefault(assignment.group("name"), []).append(assignment.group("value"))
    return found


def names_derived_from_the_working_tree(text: str) -> set[str]:
    """Every shell name in a script whose value flows from the working tree's
    own path."""
    text = uncommented(text)
    functions = shell_functions(text)
    assignments = shell_assignments(text)
    tainted: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, values in assignments.items():
            if name in tainted:
                continue
            if any(_value_is_derived(value, tainted, functions, frozenset()) for value in values):
                tainted.add(name)
                changed = True
    return tainted


def environment_names_the_entry_point_supplies(text: str) -> set[str]:
    """Every upper-case name the entry point assigns.

    Upper case because that is the convention this script, and POSIX, use for a
    name that reaches a child process; the set is deliberately a SUPERSET of
    what reaches Molecule, since a check comparing the fixtures' reads against
    it only has to establish that nothing they read is unsupplied.
    """
    return {name for name in shell_assignments(text) if ENVIRONMENT_NAME.fullmatch(name)}


def value_not_derived_from_the_working_tree(text: str, variable: str) -> str | None:
    """Why `variable`'s value is not derived from the working tree's own path,
    or None where it is."""
    assignments = shell_assignments(text)
    if variable not in assignments:
        return (
            f"{ENTRY_POINT} assigns no {variable}, so it supplies no value for the "
            f"kernel-held handle at all"
        )
    value = assignments[variable][-1]
    stripped = uncommented(text)
    functions = shell_functions(stripped)
    tainted = names_derived_from_the_working_tree(stripped)
    if _value_is_derived(value, tainted, functions, frozenset()):
        return None
    return (
        f"{ENTRY_POINT} assigns {variable}={value!r}, which does not flow from the working "
        f"tree's own path; an entry point supplying a constant satisfies every check about "
        f"the variable's existence while reinstating the handle shared by every working tree "
        f"on the machine"
    )


# --------------------------------------------------------------------------
# Reading a fixture play's losetup invocations
# --------------------------------------------------------------------------

DETACH_FLAGS = {"-d", "--detach", "-D", "--detach-all"}
FIND_FLAGS = {"-f", "--find"}
READ_FLAGS = {
    "-a",
    "--all",
    "-j",
    "--associated",
    "-l",
    "--list",
    "-n",
    "--noheadings",
    "-O",
    "--output",
    "--raw",
    "--json",
}


def _command_text(lines: list[str], index: int) -> str:
    """The whole of a command beginning on `lines[index]`, folded lines joined.

    A YAML folded scalar puts a command's continuation on following lines at the
    same or greater indentation; the next mapping key ends it. A reader taking
    one line at a time would see `losetup` with no operands and classify an
    association as a read.
    """
    line = lines[index]
    text = line[line.index("losetup") :]
    indent = len(line) - len(line.lstrip())
    following = index + 1
    while following < len(lines):
        candidate = lines[following]
        if not candidate.strip() or candidate.lstrip().startswith("#"):
            break
        if YAML_KEY_LINE.match(candidate):
            break
        if len(candidate) - len(candidate.lstrip()) < indent:
            break
        text += " " + candidate.strip()
        following += 1
    return text


def losetup_invocations(body: str) -> list[tuple[int, str, str]]:
    """(offset, kind, command) for every `losetup` invocation in a play.

    `kind` is one of `detach`, `associate` or `read`. A Jinja expression is
    collapsed to a single token first, so `{{ a }}` counts as one operand rather
    than three.
    """
    invocations = []
    offset = 0
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if "losetup" in line:
            command = _command_text(lines, index)
            tokens = JINJA_EXPRESSION.sub("JINJA", command).split()[1:]
            flags = {token for token in tokens if token.startswith("-")}
            operands = [token for token in tokens if not token.startswith("-")]
            if flags & DETACH_FLAGS:
                kind = "detach"
            elif flags & FIND_FLAGS and operands:
                kind = "associate"
            elif flags & READ_FLAGS:
                kind = "read"
            elif len(operands) >= 2:
                kind = "associate"
            else:
                # A bare `losetup <device>`, or `losetup` alone: both print what
                # holds the handle, which is a read.
                kind = "read"
            invocations.append((offset + line.index("losetup"), kind, command))
        offset += len(line) + 1
    return invocations


TASK_START = re.compile(r"^\s*-\s+name:", re.MULTILINE)
REGISTERED = re.compile(r"^\s*register:\s*(?P<name>[A-Za-z_]\w*)\s*$", re.MULTILINE)
REFUSING_MODULE = re.compile(r"^\s*(?:ansible\.builtin\.)?(?:assert|fail):\s*$", re.MULTILINE)
FAILED_WHEN = re.compile(r"^\s*failed_when:\s*(?P<value>.*)$", re.MULTILINE)
FALSEY = {"false", "no", "off", "0", ""}


def _registered_by_the_task_at(body: str, offset: int) -> str | None:
    """The variable the task containing `offset` registers."""
    starts = [match.start() for match in TASK_START.finditer(body)]
    opening = max((start for start in starts if start <= offset), default=0)
    closing = min((start for start in starts if start > offset), default=len(body))
    registered = REGISTERED.search(body, opening, closing)
    return registered.group("name") if registered else None


def _refusal_between(body: str, start: int, end: int, registered: str | None) -> bool:
    """Whether a refusal stands between a read and a release, and acts on what
    the read registered.

    A play that reads what holds the handle, registers the result and then
    releases it regardless satisfies every read-only assertion while doing the
    exact thing the requirement forbids -- so the refusal, not the read, is what
    is looked for. `failed_when: false` is not one: it is how the read itself is
    kept from failing.
    """
    if registered is None:
        return False
    segment = body[start:end]
    candidates = [match.start() for match in REFUSING_MODULE.finditer(segment)]
    candidates += [
        match.start()
        for match in FAILED_WHEN.finditer(segment)
        if match.group("value").split("#")[0].strip().strip("\"'").lower() not in FALSEY
    ]
    return any(registered in segment[candidate:] for candidate in sorted(candidates))


def association_guard_offences(body: str, label: str) -> list[str]:
    """Report why a play associating a loop device does not establish the handle
    is free first."""
    invocations = losetup_invocations(body)
    associations = [offset for offset, kind, _ in invocations if kind == "associate"]
    if not associations:
        return []
    first_association = associations[0]
    releases = [
        offset
        for offset, kind, _ in invocations
        if kind == "detach" and offset < first_association
    ]
    if not releases:
        return [
            f"{label} associates a loop device without releasing it earlier in the same file, "
            f"so it inherits whatever a previous run left on that minor"
        ]
    release = releases[-1]
    reads = [offset for offset, kind, _ in invocations if kind == "read" and offset < release]
    if not reads:
        return [
            f"{label} releases a loop device without reading what holds it first, so it can "
            f"reclaim a minor the host or another project is using"
        ]
    read = reads[-1]
    if not _refusal_between(body, read, release, _registered_by_the_task_at(body, read)):
        return [
            f"{label} reads what holds the loop device but nothing between that read and the "
            f"release refuses on the result, so the play reads, registers and releases "
            f"regardless -- which is the shape this obligation exists to fail"
        ]
    return []


def plays_associating_without_establishing_the_handle_is_free(
    root: Path | None = None,
) -> list[str]:
    base = ROOT if root is None else root
    offenders: list[str] = []
    for path in fixture_plays(base):
        offenders.extend(association_guard_offences(_body(path), _label(path, base)))
    return offenders


# --------------------------------------------------------------------------
# Reading the workflow that runs the suite
# --------------------------------------------------------------------------

ENVIRONMENT_PREFIX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=[^\s$`]*$")
COMMAND_WRAPPERS = {"sudo", "env", "nice", "time", "command", "exec"}
SUBCOMMAND_RUNNERS = {"uv", "poetry", "pipenv", "pdm", "hatch"}


def _program_of(line: str) -> str | None:
    """The program a shell line invokes, leading environment assignments and
    wrappers skipped."""
    tokens = line.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if ENVIRONMENT_PREFIX.match(token) or token in COMMAND_WRAPPERS:
            index += 1
            continue
        if (
            token in SUBCOMMAND_RUNNERS
            and index + 1 < len(tokens)
            and tokens[index + 1] in {"run", "exec"}
        ):
            index += 2
            continue
        break
    if index >= len(tokens):
        return None
    return tokens[index].rsplit("/", 1)[-1]


def suite_invocations(workflow: dict) -> list[tuple[str, str, str]]:
    """(step label, command line, program) for every line in a workflow that
    invokes Molecule, through the entry point or directly.

    Read in COMMAND POSITION rather than anywhere on the line: this workflow's
    role discovery passes `-name molecule` to `find`, and a check reading the
    bare word would report that as an invocation.
    """
    found = []
    for job_name, index, step in steps(workflow):
        script = step.get("run")
        if not isinstance(script, str):
            continue
        for line in script.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            program = _program_of(stripped)
            if program in {"molecule", ENTRY_POINT_NAME}:
                found.append((step_label(job_name, index, step), stripped, program))
    return found


def suite_invocations_bypassing_the_entry_point(workflow: dict) -> list[str]:
    return [
        f"{label}: {line}"
        for label, line, program in suite_invocations(workflow)
        if program != ENTRY_POINT_NAME
    ]


# --------------------------------------------------------------------------
# Fixture material
# --------------------------------------------------------------------------

LITERAL_FIXTURE_PLAY = """---
- name: Prepare
  hosts: all
  become: true
  tasks:
    - name: Create the fixed loop device node
      ansible.builtin.command: mknod -m 0660 /dev/loop87 b 7 87
      changed_when: true

    - name: Associate the backing file with the fixed loop device
      ansible.builtin.command: losetup /dev/loop87 /root/platform-data-volume-backing.img
      changed_when: true
"""

DERIVED_FIXTURE_PLAY = """---
- name: Prepare
  hosts: all
  become: true
  vars:
    fixture_loop_base: "{{ lookup('env', 'INFRA_WORKTREE_LOOP_BASE') }}"
    fixture_device: "/dev/loop{{ fixture_loop_base | int + 0 }}"
  tasks:
    - name: Refuse to run without a base
      ansible.builtin.assert:
        that:
          - fixture_loop_base is match('^[0-9]+$')
        fail_msg: Run the suite through ansible/scripts/run-molecule.

    - name: Read what currently holds the derived loop device
      ansible.builtin.command: losetup --noheadings --output BACK-FILE {{ fixture_device }}
      register: fixture_backing
      changed_when: false
      failed_when: false

    - name: Refuse a minor this fixture cannot attribute to its own backing files
      ansible.builtin.assert:
        that:
          - fixture_backing.stdout | trim == "" or fixture_backing.stdout is match('/root/platform-data-volume-')
        fail_msg: Refusing to reclaim a loop device this fixture family did not create.

    - name: Detach the derived loop device
      ansible.builtin.command: losetup -d {{ fixture_device }}
      register: fixture_detach
      changed_when: fixture_detach.rc == 0
      failed_when: false

    - name: Associate this run's own backing file with the derived loop device
      ansible.builtin.command: losetup {{ fixture_device }} /root/platform-data-volume-backing.img
      changed_when: true
"""

REFUSAL_TASK = """    - name: Refuse a minor this fixture cannot attribute to its own backing files
      ansible.builtin.assert:
        that:
          - fixture_backing.stdout | trim == "" or fixture_backing.stdout is match('/root/platform-data-volume-')
        fail_msg: Refusing to reclaim a loop device this fixture family did not create.

"""


def _derived_play(*, variable: str = LOOP_BASE_VARIABLE) -> str:
    return DERIVED_FIXTURE_PLAY.replace(LOOP_BASE_VARIABLE, variable)


DERIVING_ENTRY_POINT = """#!/usr/bin/env bash
set -euo pipefail

repository_root() {
\tgit rev-parse --show-toplevel
}

digest_of() {
\tprintf '%s' "$1" | sha256sum | cut -c1-6
}

loop_base_for() {
\tlocal root="$1" digest
\tdigest=$(digest_of "$root")
\tprintf '%s\\n' "$((1024 + (16#$digest % 4096) * 8))"
}

main() {
\tlocal root base
\troot=$(repository_root)
\tbase=$(loop_base_for "$root")
\tINFRA_WORKTREE_LOOP_BASE="$base" \\
\t\texec molecule "$@"
}

main "$@"
"""

# The same entry point with the derivation replaced by a literal: the plumbing
# is intact and every fixture reading it resolves to a usable handle.
CONSTANT_ENTRY_POINT = DERIVING_ENTRY_POINT.replace(
    '\tbase=$(loop_base_for "$root")', "\tbase=2048"
)

# The subtler one: the call site still hands the root over, and only the callee
# gives the game away.
CONSTANT_FUNCTION_ENTRY_POINT = DERIVING_ENTRY_POINT.replace(
    '\tlocal root="$1" digest\n'
    '\tdigest=$(digest_of "$root")\n'
    "\tprintf '%s\\n' \"$((1024 + (16#$digest % 4096) * 8))\"",
    "\tprintf '%s\\n' 2048",
)


class LoopFixtureTreeMixin(ScenarioTreeFixtureMixin):
    """Builds throwaway trees carrying fixture PLAYS beside their definitions.

    `ScenarioTreeFixtureMixin` writes the definitions; these checks read the
    files beside them, which it does not write. Every check above takes its root
    as an argument, so each negative case below is exercised against a fixture
    rather than by damaging the real tree.
    """

    def tree_with_plays(
        self,
        plays: dict[tuple[str, str, str], str],
        manifest: str | None = DEFAULT_FIXTURE_MANIFEST,
    ) -> Path:
        scenarios = {
            (role, scenario): scenario_document(PINNED_IMAGE) for role, scenario, _ in plays
        }
        root = self.scratch_tree(scenarios, manifest=manifest)
        for (role, scenario, filename), body in plays.items():
            directory = root / "ansible" / "roles" / role / "molecule" / scenario
            (directory / filename).write_text(body, encoding="utf-8")
        return root


# --------------------------------------------------------------------------
# Scenario: A fixture naming a kernel-held handle as a literal fails the checks
# --------------------------------------------------------------------------


class TestNoFixtureNamesAKernelHeldHandleAsALiteral(unittest.TestCase):
    """MODIFIED requirement: Ansible Configuration Is Verified in Continuous
    Integration and Gates the Merge -- the clause obliging a fixture play
    claiming a handle the machine's kernel holds to derive it from a value the
    entry point supplies rather than name it as a literal.

    Read against the real tree. `TestTheFixturePlayEnumerationDiscriminates`
    runs the same checks against fixture trees, which is what establishes that
    they can fail at all.
    """

    def test_no_authored_fixture_play_names_a_loop_minor_as_a_literal(self) -> None:
        """SPECIFIED -- scenario "A fixture naming a kernel-held handle as a
        literal fails the checks": "a fixture naming a loop device minor as a
        literal SHALL fail those checks".

        A literal minor is shared by every working tree on the machine AND by a
        single tree's consecutive runs, because the kernel holds the association
        and the container that made it does not.
        """
        offenders = plays_naming_a_kernel_held_handle_as_a_literal()
        self.assertEqual(
            [],
            offenders,
            f"these fixture plays name a loop device minor as a literal, so every working "
            f"tree on the machine -- and every consecutive run of one tree -- claims the "
            f"same kernel-held handle: {offenders}",
        )

    def test_no_authored_fixture_play_claims_a_handle_by_an_unrecognised_construction(
        self,
    ) -> None:
        """SPECIFIED -- the requirement's refusal clause, read onto this
        enumeration: where a check meets a construction it does not recognise
        carrying a claim on the handle, it refuses rather than passing over it.
        An unrecognised construction ignored is a silent gap; one refused costs
        a visible edit."""
        offenders = plays_claiming_a_handle_by_an_unrecognised_construction()
        self.assertEqual(
            [],
            offenders,
            f"these fixture plays claim a kernel-held handle by a construction neither "
            f"recognised as a literal nor as a derivation, so no assertion above reads "
            f"them: {offenders}",
        )


# --------------------------------------------------------------------------
# Scenario: The entry point and the fixtures are checked against each other
# --------------------------------------------------------------------------


class TestTheFixturesAndTheEntryPointAgreeOnTheName(unittest.TestCase):
    """MODIFIED requirement: same -- "Checking one alone establishes nothing:
    the entry point and the fixtures are written in different languages with
    nothing but a variable name between them, so a rename on either side
    resolves to an unset value rather than to an error."
    """

    def test_every_name_the_deriving_fixtures_read_is_one_the_entry_point_supplies(
        self,
    ) -> None:
        """SPECIFIED -- scenario "The entry point and the fixtures are checked
        against each other": "WHEN the name ... is changed on one side alone ...
        THEN those checks SHALL fail identifying the mismatch".

        NO SPELLING IS READ. The check compares the two sides against each
        other, which is what makes it fail on a rename in EITHER direction: a
        name renamed in the entry point is no longer supplied, and a name
        renamed in the fixtures was never supplied.

        This check reports green over an empty set, and the set is empty until a
        fixture derives a device.
        `TestTheFixturePlayEnumerationRefusesToBeEmpty` is what holds it up;
        without that test this one would be a check that cannot fail.
        """
        supplied = environment_names_the_entry_point_supplies(read_text(ROOT / ENTRY_POINT))
        read = environment_names_the_fixtures_read()
        mismatched = sorted(
            f"{name} is read by {sorted(set(where))} and supplied by nothing in {ENTRY_POINT}"
            for name, where in read.items()
            if name not in supplied
        )
        self.assertEqual(
            [],
            mismatched,
            f"the fixtures and the entry point disagree about the name of the value that "
            f"joins them; Jinja resolves an unsupplied name to an UNSET value rather than to "
            f"an error, so this mismatch is silent at run time: {mismatched}",
        )

    def test_every_deriving_fixture_reads_a_value_the_entry_point_could_supply(self) -> None:
        """SPECIFIED -- the same clause read the other way: a fixture play
        deriving a handle derives it "from a value the entry point supplies". A
        play interpolating a device from a value nothing supplies is joined to
        the entry point by nothing at all, and would drop silently out of the
        check above -- which reads only the names it finds."""
        offenders = deriving_plays_reading_no_supplied_value()
        self.assertEqual(
            [],
            offenders,
            f"these fixture plays derive a loop device from no value the entry point "
            f"supplies: {offenders}",
        )


# --------------------------------------------------------------------------
# Scenario: The supplied value is derived from the working tree rather than fixed
# --------------------------------------------------------------------------


class TestTheEntryPointDerivesTheValueItSupplies(unittest.TestCase):
    """MODIFIED requirement: same -- "the entry point SHALL supply that value
    resolved to one unique to the working tree the run was started from ... An
    entry point supplying a constant satisfies the plumbing and reinstates the
    shared literal the obligation exists to remove."
    """

    def test_the_entry_point_supplies_a_value_for_the_kernel_held_handle(self) -> None:
        """SPECIFIED for the obligation, DERIVED for the spelling -- the delta
        obliges the entry point to supply the value and to have it checked "over
        the entry point itself", and that change's design.md Decision 2 is where
        the name comes from. See LOOP_BASE_VARIABLE above for why this one check
        reads a name when the instance-name checks beside it read none."""
        supplied = environment_names_the_entry_point_supplies(read_text(ROOT / ENTRY_POINT))
        self.assertIn(
            LOOP_BASE_VARIABLE,
            supplied,
            f"{ENTRY_POINT} supplies no {LOOP_BASE_VARIABLE}, so a fixture reading it "
            f"resolves an unset value; it supplies {sorted(supplied)}",
        )

    def test_the_supplied_value_derives_from_the_working_trees_own_path(self) -> None:
        """SPECIFIED -- scenario "The supplied value is derived from the working
        tree rather than fixed": "it SHALL be found to derive that value from
        the working tree's own path, and an entry point supplying a constant
        SHALL fail those checks even though every fixture reading it still
        resolves to a usable handle".

        The analysis reads THROUGH the call: a constant-returning function
        called with the root still mentions the root at its call site, so a
        check reading only the assignment would pass over exactly the entry
        point this scenario names."""
        reason = value_not_derived_from_the_working_tree(
            read_text(ROOT / ENTRY_POINT), LOOP_BASE_VARIABLE
        )
        self.assertIsNone(reason, reason)

    def test_the_analysis_recognises_the_namespace_the_entry_point_already_derives(
        self,
    ) -> None:
        """DERIVED -- a positive control on real content, not an obligation of
        the delta. `INFRA_WORKTREE_NS` is derived from the working tree's path
        today, so an analysis reporting it underived would be broken in the
        direction that makes the assertion above unfalsifiable-by-passing."""
        reason = value_not_derived_from_the_working_tree(
            read_text(ROOT / ENTRY_POINT), "INFRA_WORKTREE_NS"
        )
        self.assertIsNone(
            reason,
            f"the derivation analysis does not recognise the namespace {ENTRY_POINT} already "
            f"derives from the working tree, so it cannot be trusted about a value it "
            f"reports as derived: {reason}",
        )


# --------------------------------------------------------------------------
# Scenario: A fixture claiming a kernel-held handle establishes it is free first
# --------------------------------------------------------------------------


class TestAFixtureEstablishesTheHandleIsFreeBeforeClaimingIt(unittest.TestCase):
    """MODIFIED requirement: same -- "Where such a handle is derived rather than
    chosen, the fixture SHALL establish that the handle is free before claiming
    it, and SHALL refuse a handle it cannot attribute to its own fixtures rather
    than reclaiming it", and "That the fixture acts on what it reads SHALL be
    checked, and not only that it reads."
    """

    def test_every_associating_fixture_releases_reads_and_refuses_first(self) -> None:
        """SPECIFIED -- scenario "A fixture claiming a kernel-held handle
        establishes it is free first": "that play SHALL be found to release the
        handle earlier in the same file, to read what holds it before releasing
        it, and to refuse on that read, and a play that associates without a
        release, or that reads what holds the handle without acting on the
        result, SHALL fail those checks".

        What is checked is the committed file's SHAPE. The run-time refusal is
        not reachable here -- the guard is the first task of the first play and
        Molecule runs nothing before it in which a foreign association could be
        planted -- which is the delta's own reason for specifying the shape."""
        offenders = plays_associating_without_establishing_the_handle_is_free()
        self.assertEqual(
            [],
            offenders,
            f"these fixture plays claim a kernel-held handle without establishing it is "
            f"free and attributable first; a privileged fixture reclaiming a minor the host "
            f"is using damages the machine the verification runs on: {offenders}",
        )


# --------------------------------------------------------------------------
# Scenario: Checks over the fixture plays fail rather than passing over an
# empty set
# --------------------------------------------------------------------------


class TestTheFixturePlayEnumerationRefusesToBeEmpty(unittest.TestCase):
    """MODIFIED requirement: same -- "The fixture plays are a second
    enumeration, and it SHALL refuse to pass over nothing."

    This is the test the others rest on. Every check over the fixture plays
    reports green on an empty set, so a path change, a rename or an edit to the
    helper that builds the set would withdraw the whole static half of these
    obligations with nothing failing.
    """

    def test_the_fixture_play_enumeration_is_not_empty(self) -> None:
        """SPECIFIED -- the enumeration itself has to find the plays before any
        subset of it can be counted."""
        plays = fixture_plays()
        self.assertTrue(
            plays,
            "no fixture play was discovered beside any authored scenario definition, so "
            "every check over them above would pass having read nothing",
        )

    def test_some_fixture_play_derives_a_kernel_held_handle(self) -> None:
        """SPECIFIED -- scenario "Checks over the fixture plays fail rather than
        passing over an empty set": "WHEN those checks find no fixture play ...
        deriving a handle the machine's kernel holds from the value the entry
        point supplies THEN they SHALL fail naming the enumeration as the
        cause".

        THE SET COUNTED IS THE DERIVING SUBSET, not the wider set of plays
        claiming such a handle by any means. The wider set is non-empty wherever
        a play names a literal -- the very state these obligations forbid -- so
        counting it would report the enumeration healthy in exactly the
        condition that withdraws every other check over it."""
        deriving = plays_deriving_a_kernel_held_handle()
        self.assertTrue(
            deriving,
            "no fixture play beside an authored scenario definition derives a loop device "
            "from a value the entry point supplies; the enumeration is EMPTY, so the "
            "interpolation, agreement and attribution checks above are each reporting "
            "success for a property nothing examined",
        )


# --------------------------------------------------------------------------
# Scenario: The workflow reaches the suite through the entry point
# --------------------------------------------------------------------------


class TestTheWorkflowReachesTheSuiteThroughTheEntryPoint(unittest.TestCase):
    """MODIFIED requirement: same -- "The workflow that runs the suite SHALL
    invoke it through the entry point that supplies these values, and that SHALL
    be asserted statically rather than left to the workflow's author."
    """

    def test_the_workflow_invokes_the_molecule_suite(self) -> None:
        """SPECIFIED -- the vacuity guard on the assertion below, which reports
        green over a workflow it recognises no invocation in. An absent workflow
        FAILS rather than skips: `load_yaml` raises on a file that is not
        there."""
        invocations = suite_invocations(load_yaml(ANSIBLE_VERIFY))
        self.assertTrue(
            invocations,
            f"no step in {ANSIBLE_VERIFY.name} was recognised as invoking Molecule, so the "
            f"assertion that it reaches the suite through {ENTRY_POINT} would pass having "
            f"read nothing",
        )

    def test_no_step_invokes_the_tool_directly(self) -> None:
        """SPECIFIED -- scenario "The workflow reaches the suite through the
        entry point": "it SHALL be found to invoke the entry point that supplies
        the namespace and the derived handles, and a workflow invoking the tool
        directly SHALL fail those checks".

        A workflow invoking `molecule` directly supplies neither value, which
        makes every fixture play's refusal fire and every other scenario fail at
        `create` on the instance-name default -- a required check failing for a
        reason no assertion names."""
        offenders = suite_invocations_bypassing_the_entry_point(load_yaml(ANSIBLE_VERIFY))
        self.assertEqual(
            [],
            offenders,
            f"these steps invoke Molecule directly rather than through {ENTRY_POINT}, which "
            f"supplies neither the instance namespace nor the loop-device base: {offenders}",
        )


# --------------------------------------------------------------------------
# The checks above are static reads. These establish that they can fail.
# --------------------------------------------------------------------------


class TestTheFixturePlayEnumerationDiscriminates(LoopFixtureTreeMixin, unittest.TestCase):
    """Every check above reads committed files rather than executing the
    behaviour it asserts, so a green result establishes nothing on its own.
    These run the same checks over material chosen to falsify them."""

    def test_a_play_beside_a_definition_is_discovered(self) -> None:
        """DERIVED -- the enumeration's positive case."""
        root = self.tree_with_plays({("role", "default", "prepare.yml"): DERIVED_FIXTURE_PLAY})
        self.assertEqual(
            ["ansible/roles/role/molecule/default/prepare.yml"],
            [path.relative_to(root).as_posix() for path in fixture_plays(root)],
        )

    def test_the_definition_itself_is_not_counted_as_a_fixture_play(self) -> None:
        """DERIVED -- the definitions are a different enumeration with different
        checks over them; counting one here would make this set non-empty on a
        tree carrying no fixture play at all."""
        root = self.tree_with_plays({("role", "default", "prepare.yml"): DERIVED_FIXTURE_PLAY})
        self.assertNotIn(SCENARIO_DEFINITION, [path.name for path in fixture_plays(root)])

    def test_installed_galaxy_content_contributes_no_fixture_play(self) -> None:
        """SPECIFIED -- the delta's "same Galaxy exclusion as the definitions
        themselves". Derived from `ansible/requirements.yml` rather than from a
        role name: the manifest below pins `vendor.role`, so its plays drop out
        while the authored role's stay."""
        root = self.tree_with_plays(
            {
                ("authored", "default", "prepare.yml"): DERIVED_FIXTURE_PLAY,
                ("vendor.role", "default", "prepare.yml"): LITERAL_FIXTURE_PLAY,
            },
            manifest='roles:\n  - name: vendor.role\n    version: "1.0.0"\n',
        )
        self.assertIn("vendor.role", galaxy_role_directories(root))
        self.assertEqual(
            ["ansible/roles/authored/molecule/default/prepare.yml"],
            [path.relative_to(root).as_posix() for path in fixture_plays(root)],
        )
        self.assertEqual([], plays_naming_a_kernel_held_handle_as_a_literal(root))

    def test_a_tree_whose_plays_all_name_literals_fails_twice_over(self) -> None:
        """SPECIFIED -- scenario "Checks over the fixture plays fail rather than
        passing over an empty set": "a tree in which every such play names its
        handle by literal instead SHALL therefore fail these checks twice over,
        once for the literal and once for the empty set". This is the tree as it
        stands today."""
        root = self.tree_with_plays({("role", "default", "prepare.yml"): LITERAL_FIXTURE_PLAY})
        self.assertNotEqual([], plays_naming_a_kernel_held_handle_as_a_literal(root))
        self.assertEqual([], plays_deriving_a_kernel_held_handle(root))

    def test_a_tree_whose_plays_derive_their_handles_satisfies_both(self) -> None:
        """DERIVED -- the positive case of the same pair, so that the assertion
        above is not satisfied by a check that reports every tree empty."""
        root = self.tree_with_plays({("role", "default", "prepare.yml"): DERIVED_FIXTURE_PLAY})
        self.assertEqual([], plays_naming_a_kernel_held_handle_as_a_literal(root))
        self.assertNotEqual([], plays_deriving_a_kernel_held_handle(root))

    def test_a_literal_minor_in_a_mknod_is_caught_behind_a_derived_path(self) -> None:
        """SPECIFIED -- a fixture "naming a loop device minor as a literal"
        covers the device node as much as the path: three of this role's
        fixtures interpolate the path and write the minor out in
        `mknod ... b 7 90`, which a check reading only `/dev/loopN` would
        pass."""
        play = DERIVED_FIXTURE_PLAY.replace(
            "    - name: Refuse to run without a base",
            "    - name: Create the derived loop device node\n"
            "      ansible.builtin.command: mknod -m 0660 {{ fixture_device }} b 7 90\n"
            "      changed_when: true\n\n"
            "    - name: Refuse to run without a base",
        )
        root = self.tree_with_plays({("role", "default", "prepare.yml"): play})
        self.assertNotEqual([], plays_naming_a_kernel_held_handle_as_a_literal(root))

    def test_a_claim_by_an_unrecognised_construction_is_refused(self) -> None:
        """SPECIFIED -- the refusal clause: a play driving `losetup` whose
        device this check can read as neither a literal nor a derivation is
        reported rather than passed over."""
        play = """---
- name: Prepare
  hosts: all
  tasks:
    - name: Associate a device named by something this check cannot read
      ansible.builtin.command: losetup {{ fixture_device_from_somewhere }} /root/img
      changed_when: true
"""
        opaque = self.tree_with_plays({("role", "default", "prepare.yml"): play})
        self.assertNotEqual([], plays_claiming_a_handle_by_an_unrecognised_construction(opaque))
        recognised = self.tree_with_plays(
            {("role", "default", "prepare.yml"): DERIVED_FIXTURE_PLAY}
        )
        self.assertEqual(
            [], plays_claiming_a_handle_by_an_unrecognised_construction(recognised)
        )


class TestTheNameAgreementCheckDiscriminates(LoopFixtureTreeMixin, unittest.TestCase):
    def test_a_rename_in_the_fixtures_alone_is_a_mismatch(self) -> None:
        """SPECIFIED -- scenario "The entry point and the fixtures are checked
        against each other", the fixtures' side."""
        root = self.tree_with_plays(
            {
                ("role", "default", "prepare.yml"): _derived_play(
                    variable="INFRA_WORKTREE_LOOP_SEED"
                )
            }
        )
        supplied = environment_names_the_entry_point_supplies(DERIVING_ENTRY_POINT)
        read = environment_names_the_fixtures_read(root)
        self.assertEqual(["INFRA_WORKTREE_LOOP_SEED"], sorted(read))
        self.assertEqual([], sorted(name for name in read if name in supplied))

    def test_a_rename_in_the_entry_point_alone_is_a_mismatch(self) -> None:
        """SPECIFIED -- the same scenario's other side. The fixtures are
        unchanged and the entry point's name moves."""
        root = self.tree_with_plays({("role", "default", "prepare.yml"): DERIVED_FIXTURE_PLAY})
        renamed = DERIVING_ENTRY_POINT.replace(LOOP_BASE_VARIABLE, "INFRA_WORKTREE_LOOP_SEED")
        supplied = environment_names_the_entry_point_supplies(renamed)
        read = environment_names_the_fixtures_read(root)
        self.assertEqual([LOOP_BASE_VARIABLE], sorted(read))
        self.assertEqual([], sorted(name for name in read if name in supplied))

    def test_two_sides_naming_the_same_value_agree(self) -> None:
        """DERIVED -- the positive case, so that the two above are not satisfied
        by a check that reports every pair mismatched."""
        root = self.tree_with_plays({("role", "default", "prepare.yml"): DERIVED_FIXTURE_PLAY})
        supplied = environment_names_the_entry_point_supplies(DERIVING_ENTRY_POINT)
        read = environment_names_the_fixtures_read(root)
        self.assertEqual([LOOP_BASE_VARIABLE], sorted(read))
        self.assertTrue(set(read) <= supplied)

    def test_a_name_molecule_supplies_is_not_read_as_the_entry_points(self) -> None:
        """DERIVED -- `multiple-devices-discoverable/prepare.yml` reads
        `MOLECULE_MULTI_DEVICE_REVERSE_ORDER`, which Molecule's own provisioner
        environment supplies. Reading it as the entry point's would make every
        such play a permanent mismatch, and the repair reached for would be to
        weaken the comparison."""
        play = DERIVED_FIXTURE_PLAY.replace(
            "  tasks:",
            "    fixture_arm: \"{{ lookup('env', 'MOLECULE_MULTI_DEVICE_REVERSE_ORDER') }}\"\n"
            "  tasks:",
            1,
        )
        root = self.tree_with_plays({("role", "default", "prepare.yml"): play})
        self.assertEqual([LOOP_BASE_VARIABLE], sorted(environment_names_the_fixtures_read(root)))

    def test_a_name_the_scenario_definition_supplies_is_not_read_as_the_entry_points(
        self,
    ) -> None:
        """DERIVED -- the same exclusion derived from the scenario's own
        definition rather than from a prefix, so a name carrying no `MOLECULE_`
        prefix but declared in the scenario's provisioner environment is
        excluded too."""
        play = DERIVED_FIXTURE_PLAY.replace(
            "  tasks:",
            "    fixture_arm: \"{{ lookup('env', 'FIXTURE_ARM') }}\"\n  tasks:",
            1,
        )
        root = self.tree_with_plays({("role", "default", "prepare.yml"): play})
        definition = root / "ansible" / "roles" / "role" / "molecule" / "default" / "molecule.yml"
        definition.write_text(
            definition.read_text(encoding="utf-8")
            + 'provisioner:\n  name: ansible\n  env:\n    FIXTURE_ARM: "1"\n',
            encoding="utf-8",
        )
        self.assertEqual([LOOP_BASE_VARIABLE], sorted(environment_names_the_fixtures_read(root)))

    def test_a_play_deriving_a_device_from_nothing_supplied_is_reported(self) -> None:
        """SPECIFIED -- a play interpolating a device from a value nothing
        supplies reads no name at all, so the comparison above would find
        nothing to mismatch."""
        play = """---
- name: Prepare
  hosts: all
  vars:
    fixture_device: "/dev/loop{{ 87 + 0 }}"
  tasks:
    - name: Associate
      ansible.builtin.command: losetup {{ fixture_device }} /root/img
      changed_when: true
"""
        unsupplied = self.tree_with_plays({("role", "default", "prepare.yml"): play})
        self.assertNotEqual([], plays_deriving_a_kernel_held_handle(unsupplied))
        self.assertNotEqual([], deriving_plays_reading_no_supplied_value(unsupplied))
        supplied = self.tree_with_plays(
            {("role", "default", "prepare.yml"): DERIVED_FIXTURE_PLAY}
        )
        self.assertEqual([], deriving_plays_reading_no_supplied_value(supplied))


class TestTheDerivationAnalysisDiscriminates(unittest.TestCase):
    def test_an_entry_point_deriving_the_value_passes(self) -> None:
        """DERIVED -- the positive case. Without it the three below are
        satisfied by an analysis that reports every entry point underived."""
        self.assertIsNone(
            value_not_derived_from_the_working_tree(DERIVING_ENTRY_POINT, LOOP_BASE_VARIABLE)
        )

    def test_an_entry_point_assigning_a_constant_fails(self) -> None:
        """SPECIFIED -- scenario "The supplied value is derived from the working
        tree rather than fixed": "an entry point supplying a constant SHALL fail
        those checks even though every fixture reading it still resolves to a
        usable handle"."""
        reason = value_not_derived_from_the_working_tree(CONSTANT_ENTRY_POINT, LOOP_BASE_VARIABLE)
        self.assertIsNotNone(reason)
        self.assertIn(LOOP_BASE_VARIABLE, reason or "")

    def test_an_entry_point_whose_derivation_ignores_its_argument_fails(self) -> None:
        """SPECIFIED -- the same scenario, in the shape a check reading only the
        assignment passes over: `base=$(loop_base_for "$root")` mentions the
        root at its call site whatever the callee does, so the analysis has to
        read through the call to find that the callee returns a constant."""
        reason = value_not_derived_from_the_working_tree(
            CONSTANT_FUNCTION_ENTRY_POINT, LOOP_BASE_VARIABLE
        )
        self.assertIsNotNone(
            reason,
            "an entry point whose derivation ignores the working tree it was handed was "
            "reported as deriving from it, which is the vacuous pass this scenario names",
        )

    def test_an_entry_point_supplying_nothing_fails(self) -> None:
        """SPECIFIED -- the absent case: a value that is not supplied at all is
        not a value derived from the working tree, and must be reported rather
        than passed over."""
        reason = value_not_derived_from_the_working_tree(
            DERIVING_ENTRY_POINT.replace(LOOP_BASE_VARIABLE, "SOMETHING_ELSE"),
            LOOP_BASE_VARIABLE,
        )
        self.assertIsNotNone(reason)

    def test_the_supplied_set_is_what_the_script_assigns(self) -> None:
        """DERIVED -- the set the name-agreement check compares against."""
        self.assertIn(
            LOOP_BASE_VARIABLE, environment_names_the_entry_point_supplies(DERIVING_ENTRY_POINT)
        )
        self.assertNotIn(
            LOOP_BASE_VARIABLE,
            environment_names_the_entry_point_supplies(
                DERIVING_ENTRY_POINT.replace(LOOP_BASE_VARIABLE, "SOMETHING_ELSE")
            ),
        )


class TestTheAssociationGuardCheckDiscriminates(unittest.TestCase):
    def test_a_play_that_releases_reads_and_refuses_passes(self) -> None:
        """DERIVED -- the positive case."""
        self.assertEqual([], association_guard_offences(DERIVED_FIXTURE_PLAY, "fixture"))

    def test_a_play_associating_without_a_release_fails(self) -> None:
        """SPECIFIED -- "a play that associates without a release ... SHALL fail
        those checks"."""
        offences = association_guard_offences(LITERAL_FIXTURE_PLAY, "fixture")
        self.assertNotEqual([], offences)
        self.assertIn("without releasing it earlier", offences[0])

    def test_a_play_releasing_without_reading_what_holds_it_fails(self) -> None:
        """SPECIFIED -- the fixture must "read what holds it before releasing
        it". This is the shape all four of this role's associating plays are in
        today."""
        play = "\n".join(
            line
            for line in DERIVED_FIXTURE_PLAY.splitlines()
            if "--noheadings" not in line
            and "fixture_backing" not in line
            and "Read what currently holds" not in line
            and "Refuse a minor this fixture" not in line
        )
        offences = association_guard_offences(play, "fixture")
        self.assertNotEqual([], offences)
        self.assertIn("without reading what holds it", offences[0])

    def test_a_play_that_reads_registers_and_releases_regardless_fails(self) -> None:
        """SPECIFIED -- "a play that ... reads what holds the handle without
        acting on the result, SHALL fail those checks". This is the shape a
        read-only assertion passes in full while the play does the exact thing
        the obligation forbids."""
        play = DERIVED_FIXTURE_PLAY.replace(REFUSAL_TASK, "")
        self.assertNotIn("Refusing to reclaim", play)
        offences = association_guard_offences(play, "fixture")
        self.assertNotEqual([], offences)
        self.assertIn("nothing between that read and the release refuses", offences[0])

    def test_a_failed_when_false_on_the_read_is_not_a_refusal(self) -> None:
        """SPECIFIED -- the same clause. `failed_when: false` is how the read
        itself is kept from failing; counting it would make every reading play
        pass, the removed refusal included."""
        play = DERIVED_FIXTURE_PLAY.replace(REFUSAL_TASK, "")
        self.assertIn("failed_when: false", play)
        self.assertNotEqual([], association_guard_offences(play, "fixture"))

    def test_a_refusal_naming_nothing_the_read_registered_does_not_count(self) -> None:
        """SPECIFIED -- the same clause: the refusal has to act on WHAT WAS
        READ. An assert standing in the right place but testing something else
        is the same read-register-release shape with a decoration on it."""
        play = DERIVED_FIXTURE_PLAY.replace(
            "          - fixture_backing.stdout | trim == \"\" or fixture_backing.stdout is "
            "match('/root/platform-data-volume-')",
            "          - fixture_loop_base is match('^[0-9]+$')",
        )
        self.assertNotIn("fixture_backing.stdout | trim", play)
        offences = association_guard_offences(play, "fixture")
        self.assertNotEqual([], offences)
        self.assertIn("nothing between that read and the release refuses", offences[0])

    def test_a_play_claiming_no_handle_is_not_held_to_this(self) -> None:
        """DERIVED -- `no-device-discoverable` carries no `prepare.yml` and
        `multiple-devices-*/verify.yml` names no device; a check reporting them
        would be red on content this obligation says nothing about."""
        play = "---\n- name: Verify\n  hosts: all\n  tasks: []\n"
        self.assertEqual([], association_guard_offences(play, "fixture"))

    def test_a_folded_command_is_read_as_one_invocation(self) -> None:
        """DERIVED -- this repository's fixtures write long commands as YAML
        folded scalars, so a reader taking one line at a time would see
        `losetup` with no operands and classify an association as a read."""
        folded = """---
- name: Prepare
  hosts: all
  tasks:
    - name: Associate
      ansible.builtin.command: >-
        losetup {{ fixture_device }}
        /root/platform-data-volume-backing.img
      changed_when: true
"""
        self.assertEqual(["associate"], [kind for _, kind, _ in losetup_invocations(folded)])


class TestTheWorkflowCheckDiscriminates(unittest.TestCase):
    @staticmethod
    def _workflow(command: str) -> dict:
        return {"jobs": {"molecule": {"steps": [{"name": "molecule", "run": command}]}}}

    def test_an_invocation_through_the_entry_point_passes(self) -> None:
        """DERIVED -- the positive case, and the shape the committed workflow is
        in today."""
        workflow = self._workflow("../../scripts/run-molecule test --all")
        self.assertEqual(1, len(suite_invocations(workflow)))
        self.assertEqual([], suite_invocations_bypassing_the_entry_point(workflow))

    def test_an_invocation_of_the_tool_directly_fails(self) -> None:
        """SPECIFIED -- scenario "The workflow reaches the suite through the
        entry point": "a workflow invoking the tool directly SHALL fail those
        checks"."""
        workflow = self._workflow("molecule test --all")
        self.assertNotEqual([], suite_invocations_bypassing_the_entry_point(workflow))

    def test_a_workflow_invoking_nothing_is_recognised_as_invoking_nothing(self) -> None:
        """SPECIFIED -- the vacuity guard: the bypass check reports green over a
        workflow with no invocation in it, so the enumeration is asserted
        separately."""
        workflow = self._workflow("echo nothing to do")
        self.assertEqual([], suite_invocations(workflow))
        self.assertEqual([], suite_invocations_bypassing_the_entry_point(workflow))

    def test_the_word_molecule_in_an_argument_is_not_an_invocation(self) -> None:
        """DERIVED -- this workflow's role discovery passes `-name molecule` to
        `find`. A check reading the bare word would report it as an invocation
        of the tool, and the repair reached for would be an exemption that
        blinds the check to the step it exists to read."""
        workflow = self._workflow(
            "roles=$(find ansible/roles -mindepth 2 -maxdepth 2 -type d -name molecule)"
        )
        self.assertEqual([], suite_invocations(workflow))

    def test_an_invocation_behind_a_wrapper_is_still_read(self) -> None:
        """DERIVED -- `sudo`, a leading environment assignment and `uv run` each
        move the program along the line without changing what is invoked."""
        for command in (
            "sudo molecule test --all",
            "MOLECULE_DEBUG=1 molecule test --all",
            "uv run molecule test --all",
        ):
            with self.subTest(command=command):
                self.assertNotEqual(
                    [], suite_invocations_bypassing_the_entry_point(self._workflow(command))
                )
