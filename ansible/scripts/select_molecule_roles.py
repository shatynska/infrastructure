#!/usr/bin/env python3
"""Select the Molecule roles a pull request's changed files owe.

Lives here, beside `run-molecule`, and the location is load-bearing rather
than tidy. A path under `ansible/` is a trigger under `ansible-verify.yml`'s
own change filter, and it is a path this module's attribution does not
recognise -- so editing this file runs the whole suite, which is the correct
blast radius for a change to what the suite selects. Under `.github/` it would
be neither: the suite's filter does not reach there, so an edit here would
change what every later pull request runs while running nothing itself. See
the change `select-the-molecule-matrix-per-role`, design.md Decision 6.

THE GRAPH IS DERIVED, NEVER COMMITTED. A recorded graph is a list, and a list
that falls behind the scenarios it describes under-selects silently -- the
aggregating gate sees a matrix that passed over the rows it was handed and has
no way to learn which rows it should have been handed. Everything below reads
the tree it is pointed at.

THE POLARITY IS TO RUN, NOT TO SKIP. Every way the selection can be wrong
resolves to running more roles rather than fewer: an unattributable path, an
unrecognised diff, a closure with nothing runnable in it. Wasteful is visible
and correctable in one line; narrow is silent and green.

Importable with no side effects -- `.github/tests` loads it by path to assert
the derivation -- with the command-line entry point guarded at the foot.
Standard library plus PyYAML, which `.github/requirements-ci.txt` pins.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

#: Where this repository's own roles live, relative to the tree's root.
ROLES_DIRECTORY = "ansible/roles"

#: A scenario reaches a role through exactly these. `molecule.yml` is NOT
#: among the files read for them: its `name:` carries the Docker driver and
#: the instance, and a derivation reading it produces a graph in which most
#: roles depend on `docker`. Only that file's PATH is an input, identifying
#: which role a scenario belongs to.
ROLE_INCLUSION_KEYS = frozenset(
    {
        "include_role",
        "import_role",
        "ansible.builtin.include_role",
        "ansible.builtin.import_role",
    }
)

#: Task-file inclusion. Reaches no role by name, and reaches one by path --
#: which is why the refusals below are keyed on what is reached rather than on
#: a role being named.
TASK_INCLUSION_KEYS = frozenset(
    {
        "include_tasks",
        "import_tasks",
        "include",
        "ansible.builtin.include_tasks",
        "ansible.builtin.import_tasks",
    }
)

#: Running a playbook from inside a play. Where its path is a literal the
#: derivation could follow it; where it is an expression it cannot, and
#: refuses unless an entry below covers that instance.
COMMAND_KEYS = frozenset(
    {"command", "shell", "ansible.builtin.command", "ansible.builtin.shell"}
)

#: Blocks hold tasks and are walked like any other task list. This repository's
#: `ghcr-credential-rejected` and `absent-ssh-cidrs` scenarios both reach roles
#: from inside one, so this is live rather than defensive.
BLOCK_KEYS = ("block", "rescue", "always")

#: Where a play keeps its tasks, in document order -- `pre_tasks` before
#: `tasks` before `post_tasks`. Order is immaterial to a dependency graph and
#: is kept anyway, so that a reader comparing this walker with the one in
#: `.github/tests` finds them saying the same thing.
PLAY_TASK_KEYS = ("pre_tasks", "tasks", "post_tasks", "handlers")

#: The nested-playbook instances this repository permits, keyed on the file,
#: the construction and the target it resolves to -- the form
#: `PERMITTED_CONTROLLER_READS` in `.github/tests/test_ci_configuration.py`
#: already uses for exactly this read.
#:
#: KEYED BY INSTANCE, NEVER BY CONSTRUCTION, and the difference is the whole
#: point. Exempting `ansible-playbook`-over-an-expression wholesale would
#: silently readmit every future instance of the route this refuses; an entry
#: costs one visible edit and a reason. A blanket exemption is an entry's
#: clothes over no entry.
#:
#: This entry is shipped in the same commit as the refusal that needs it. A
#: selector carrying the refusal and no entry turns the required status check
#: red on every pull request in the repository.
PERMITTED_NESTED_PLAYBOOKS: dict[tuple[str, str, str], str] = {
    (
        "ansible/roles/ops_user/molecule/revocation-steady-state/verify.yml",
        "command(ansible-playbook)",
        "expr:{{ ops_user_nested_scenario_dir }}/converge.yml",
    ): (
        "The scenario re-converges itself against the already-revoked steady "
        "state. The path is this scenario's own directory, supplied by Molecule "
        "through the variable, so it reaches no role but `ops_user` -- which is "
        "in its own closure regardless. Recorded rather than followed because "
        "the value is not a literal and nothing here can resolve it."
    ),
}


class DerivationRefused(Exception):
    """A construction reaches a role by a route the derivation cannot close over.

    Raised rather than passed over, and that polarity is the whole design. A
    construction not followed under-reads the graph, and under-reading loses
    coverage with nothing reporting -- the one failure this pipeline is built
    to refuse. A construction refused costs a visible edit to permit or to
    teach, and costs it to whoever wrote the construction rather than to
    whoever later wonders why a role stopped being tested.
    """


class EmptySelection(Exception):
    """The suite is owed and the selection resolved to no role at all.

    Distinct from the widening below, which is what an unattributable path or
    an unrunnable closure resolves to. This is reachable only where the tree
    itself carries nothing to run, and it refuses rather than handing the
    matrix an empty list -- an empty matrix skips, and a skip on an owed run is
    read by the gate as a suite that verified nothing.
    """


def _relative(path: Path, root: Path) -> str:
    """A tree-relative POSIX path, for messages a reader can act on."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


class _AnsibleTolerantLoader(yaml.SafeLoader):
    """`SafeLoader`, plus the two tags Ansible's own YAML carries.

    `!vault` and `!unsafe` are VALID Ansible YAML, not malformed, and
    `yaml.safe_load` rejects both. `!vault` is already live in
    `ansible/inventory/group_vars/`; nothing stops it appearing in a scenario.
    Without this, such a file would fail to parse -- and under `_documents`
    below that is a refusal, so an ordinary scenario would turn the required
    check red.

    NAMED EXPLICITLY, never a catch-all. A multi-constructor over `!` would map
    every unknown tag to `None`, which would undo the refusal `_documents`
    exists to make: a tag this module has never seen would yield empty
    documents rather than saying so.
    """


for _tag in ("!vault", "!unsafe"):
    _AnsibleTolerantLoader.add_constructor(
        _tag, lambda loader, node: loader.construct_scalar(node)
    )


def _documents(path: Path, root: Path):
    """Every YAML document in a file.

    A FILE THAT CANNOT BE READ IS REFUSED, not passed over. Returning no
    documents would make an unreadable scenario contribute no edges, which is
    indistinguishable from a scenario that reaches nothing -- the silent
    under-read this module exists to prevent. `ansible-lint` and
    `--syntax-check` also report malformed YAML, and being the second thing to
    say so costs a duplicate message; being the thing that quietly stopped
    selecting a role costs the coverage.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise DerivationRefused(
            f"{_relative(path, root)}: cannot be read ({error}), so whether it "
            "reaches a role is unknown. Refused rather than treated as reaching "
            "nothing"
        ) from error
    try:
        return [
            document
            for document in yaml.load_all(text, Loader=_AnsibleTolerantLoader)
            if document is not None
        ]
    except yaml.YAMLError as error:
        raise DerivationRefused(
            f"{_relative(path, root)}: is not YAML this derivation can parse "
            f"({error}), so whether it reaches a role is unknown. Refused rather "
            "than treated as reaching nothing -- a file that silently "
            "contributes no edges is how a role stops being tested with nothing "
            "reporting"
        ) from error


def _is_literal(value) -> bool:
    """A name this derivation can close over: a plain string, no expression."""
    return isinstance(value, str) and "{{" not in value and "}}" not in value


def role_directories(root: Path) -> set[str]:
    """Every role directory, whether or not it carries scenarios.

    Dotted names are excluded, which is how the Galaxy-installed
    `geerlingguy.docker` stays invisible: it is gitignored, so a check that saw
    it would report one result on a provisioned working tree and another on a
    runner that has installed nothing. The same rule `role_names()` in
    `.github/tests` uses, and the same rule the workflow's own discovery uses.
    """
    directory = Path(root) / ROLES_DIRECTORY
    if not directory.is_dir():
        return set()
    return {
        child.name
        for child in directory.iterdir()
        if child.is_dir() and "." not in child.name
    }


def roles_with_scenarios(root: Path) -> set[str]:
    """The roles the run can actually execute: those carrying a `molecule/`.

    Attribution and the closure range over role DIRECTORIES; only these can be
    given a matrix row. The restriction between the two is what keeps a role
    with no scenarios out of the matrix.
    """
    directory = Path(root) / ROLES_DIRECTORY
    return {
        role
        for role in role_directories(root)
        if (directory / role / "molecule").is_dir()
    }


def _scenario_play_files(root: Path, role: str) -> list[Path]:
    """A role's authored plays: every `*.yml` under `molecule/` but the definition."""
    molecule = Path(root) / ROLES_DIRECTORY / role / "molecule"
    if not molecule.is_dir():
        return []
    return sorted(
        path
        for path in molecule.glob("*/*.yml")
        if path.name != "molecule.yml"
    )


def _refuse_redirected_scenario_plays(root: Path, role: str) -> None:
    """Refuse a scenario that points its plays somewhere this walker will not look.

    `provisioner.playbooks` in a `molecule.yml` overrides which file Molecule
    runs for `converge`, `prepare` or `verify`. A scenario using it can reach
    roles from a playbook outside its own directory, and `_scenario_play_files`
    globs `molecule/*/*.yml` -- so every edge in that playbook would be missed
    with nothing reporting.

    This is the ONE key read out of a `molecule.yml`, and reading it does not
    reopen what the prohibition elsewhere in this module closes: that
    prohibition is about `name:`, which carries the Docker driver and the
    instance rather than a role. No scenario this repository authors declares
    `provisioner.playbooks`; the Galaxy-installed role does, which is one more
    reason its dotted directory is excluded before any of this runs.
    """
    molecule_root = Path(root) / ROLES_DIRECTORY / role / "molecule"
    if not molecule_root.is_dir():
        return
    for definition in sorted(molecule_root.glob("*/molecule.yml")):
        for document in _documents(definition, root):
            if not isinstance(document, dict):
                continue
            provisioner = document.get("provisioner") or {}
            if not isinstance(provisioner, dict):
                continue
            declared = provisioner.get("playbooks")
            if declared:
                raise DerivationRefused(
                    f"{_relative(definition, root)}: declares "
                    f"`provisioner.playbooks` ({declared!r}), which redirects "
                    "this scenario's plays away from its own directory. The "
                    "derivation reads the plays it finds beside a scenario, so "
                    "any role reached from a redirected playbook would "
                    "contribute no edge and nothing would report that. Refused "
                    "rather than passed over"
                )


def _role_own_files(root: Path, role: str) -> list[Path]:
    """A role's own task and handler files.

    Read to REFUSE, not to follow. A role reaching another role from its own
    `tasks/` is the same class of coupling that makes `meta/main.yml` worth
    reading, and it lies outside every scenario directory -- so no check that
    walks those alone can see it. No role in this repository does it today,
    which is what makes refusing free.
    """
    base = Path(root) / ROLES_DIRECTORY / role
    files: list[Path] = []
    for sub in ("tasks", "handlers"):
        directory = base / sub
        if directory.is_dir():
            files.extend(sorted(path for path in directory.rglob("*.yml")))
    return files


def _escapes(value: str, origin: Path, role_root: Path) -> bool:
    """Does this path value reach content outside the role's own directory?

    Keyed on what is reached rather than on a role being named, deliberately:
    `include_tasks: ../../core/tasks/main.yml` names no role and couples the
    two exactly as an invocation would.
    """
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = value.strip()
    if "{{" in candidate:
        # A TEMPLATED TARGET IS TREATED AS ESCAPING, whatever it spells. The
        # value is not one this derivation can close over, and the rule is
        # keyed on what is reached -- so an unresolvable target is refused for
        # the same reason an unresolvable role name is, twelve lines up.
        # Treating it as role-local would be a guess in the silent direction.
        return True
    try:
        resolved = (origin.parent / candidate).resolve()
        resolved.relative_to(role_root.resolve())
    except (ValueError, OSError):
        return True
    return False


def _walk_tasks(
    tasks, *, origin: Path, root: Path, edges: set[str], seen: set, scenario_root: Path
) -> None:
    """Collect role edges from a task list, refusing what cannot be closed over."""
    if not isinstance(tasks, list):
        return
    for task in tasks:
        if not isinstance(task, dict):
            continue
        for key, value in task.items():
            if key in ROLE_INCLUSION_KEYS:
                name = value.get("name") if isinstance(value, dict) else value
                if not _is_literal(name):
                    raise DerivationRefused(
                        f"{_relative(origin, root)}: `{key}` names a role by "
                        f"something other than a literal ({name!r}). A name this "
                        "derivation cannot close over is refused rather than "
                        "resolved or skipped -- resolving it would guess, and "
                        "skipping it would drop an edge with nothing reporting"
                    )
                _add_edge(str(name), origin=origin, root=root, edges=edges)
            elif key in TASK_INCLUSION_KEYS:
                target = value.get("file") if isinstance(value, dict) else value
                _follow_included_tasks(
                    target,
                    origin=origin,
                    root=root,
                    key=key,
                    edges=edges,
                    seen=seen,
                    scenario_root=scenario_root,
                )
            elif key in COMMAND_KEYS:
                _handle_nested_playbook(
                    value,
                    origin=origin,
                    root=root,
                    key=key,
                    edges=edges,
                    seen=seen,
                    scenario_root=scenario_root,
                )
        for block in BLOCK_KEYS:
            if block in task:
                _walk_tasks(
                    task[block],
                    origin=origin,
                    root=root,
                    edges=edges,
                    seen=seen,
                    scenario_root=scenario_root,
                )


def _add_edge(name: str, *, origin: Path, root: Path, edges: set[str]) -> None:
    """Record an edge, refusing a role named by path rather than by name.

    Checked HERE rather than over the flattened edge set, so the refusal can
    name the file holding the construction -- which is what the delta requires
    of every refusal, and what a reader needs to act on one. `- role:
    ../../other_role` satisfies every literal check; discarding it later for
    containing a `.` would drop a real edge for a reason unrelated to why the
    external-content filter exists.
    """
    if "/" in name:
        raise DerivationRefused(
            f"{_relative(origin, root)}: reaches a role by path ({name!r}) "
            "rather than by name. The derivation resolves a role name to a role "
            "directory and cannot do that for a path, so this is refused rather "
            "than silently discarded by the external-content filter"
        )
    edges.add(name)


def _follow_included_tasks(
    target,
    *,
    origin: Path,
    root: Path,
    key: str,
    edges: set[str],
    seen: set,
    scenario_root: Path,
) -> None:
    """Read an included task file, or refuse where it cannot be read.

    FOLLOWED WHERE IT CAN BE, refused where it cannot -- rather than refused
    outright. Factoring a scenario's shared assertions into a second file
    beside its converge is ordinary Molecule practice, not a design smell, so a
    blanket refusal would cost an author of an ordinary scenario an edit to
    this module. That is a different trade from the one made for a role's own
    files reaching outside themselves, where the construction IS the smell.

    The heavier route -- a nested `ansible-playbook` -- is followed when its
    path is a literal, so refusing the lighter one outright would have left
    this module answering the easier question more strictly than the harder.
    """
    if not _is_literal(target) or not isinstance(target, str):
        raise DerivationRefused(
            f"{_relative(origin, root)}: `{key}` names its file by something "
            f"other than a literal ({target!r}), so the derivation cannot read "
            "it. Refused rather than passed over: any role reached through it "
            "would contribute no edge and nothing would report that"
        )
    # THE BOUNDARY IS THE SCENARIO'S, FIXED ONCE, not `origin.parent`. On the
    # first hop those are the same; on the second `origin` is the included file
    # and the boundary would move down with it, so a helper one directory deep
    # reaching a file beside the converge would be refused as "outside the
    # scenario" while sitting squarely inside it. That reimposes on a two-level
    # helper exactly the cost the narrowing above removed from a one-level one,
    # and says something false while doing it.
    resolved = (origin.parent / target).resolve()
    try:
        resolved.relative_to(scenario_root.resolve())
    except ValueError:
        raise DerivationRefused(
            f"{_relative(origin, root)}: `{key}` reaches {target!r}, outside "
            "this scenario's own directory. The derivation reads the files it "
            "finds beside a scenario; one outside it is not read, so a role "
            "reached through it would contribute no edge"
        ) from None
    if not resolved.is_file():
        raise DerivationRefused(
            f"{_relative(origin, root)}: `{key}` reaches {target!r}, which is "
            "not a file. Refused rather than passed over -- an unresolvable "
            "target and a target reaching nothing are indistinguishable here, "
            "and one of them loses an edge"
        )
    if ("tasks", resolved) in seen:
        return
    seen.add(("tasks", resolved))
    for document in _documents(resolved, root):
        if isinstance(document, list):
            _walk_tasks(
                document,
                origin=resolved,
                root=root,
                edges=edges,
                seen=seen,
                scenario_root=scenario_root,
            )


def _handle_nested_playbook(
    value,
    *,
    origin: Path,
    root: Path,
    key: str,
    edges: set[str] | None = None,
    seen: set | None = None,
    scenario_root: Path | None = None,
) -> None:
    """Follow a nested `ansible-playbook`, or refuse where it cannot be followed.

    Both dispositions are conformant; passing over is not. A literal path that
    resolves is FOLLOWED and its edges attributed to the role holding the
    invocation -- a scenario reaching another role this way couples them
    exactly as `import_playbook` does. An expression is refused unless an entry
    covers that instance; a literal that does not resolve is refused too.

    `edges` is None where the caller is scanning a role's own task or handler
    files, which may not reach outside the role at all: there, every nested
    playbook is refused rather than followed.
    """
    if isinstance(value, dict):
        argv = value.get("argv")
        words = argv if isinstance(argv, list) else str(value.get("cmd", "")).split()
    elif isinstance(value, str):
        words = value.split()
    else:
        return
    words = [str(word) for word in words if isinstance(word, (str, int, float))]
    if not any(word.endswith("ansible-playbook") for word in words):
        return
    targets = [word for word in words if word.endswith((".yml", ".yaml"))]
    for target in targets:
        if _is_literal(target):
            if edges is None:
                raise DerivationRefused(
                    f"{_relative(origin, root)}: a role's own task or handler "
                    f"file runs `ansible-playbook` over {target!r}. That reaches "
                    "outside the role whatever the path resolves to, and is "
                    "refused for the same reason an include of another role's "
                    "file is"
                )
            # Two spellings resolve: relative to the file holding the
            # invocation, and relative to the repository root -- which is what
            # `ansible-playbook` itself resolves against, the controller's cwd,
            # and therefore the natural spelling. Both are tried before
            # refusing, so a correct invocation is followed rather than refused
            # for being written the ordinary way.
            #
            # Where BOTH resolve and name different files, the origin-relative
            # one wins here and the root-relative one is what would actually
            # run. The ambiguity is accepted rather than refused: it needs two
            # files to exist at the same relative path from two different
            # directories, and the cost of getting it wrong is a wider run
            # rather than a narrower one.
            candidates = [(origin.parent / target).resolve(), (Path(root) / target).resolve()]
            resolved = next((path for path in candidates if path.is_file()), None)
            if resolved is None:
                raise DerivationRefused(
                    f"{_relative(origin, root)}: runs `ansible-playbook` over "
                    f"{target!r}, which resolves to no file either beside this "
                    "file or from the repository root. Refused rather than "
                    "passed over: a playbook this derivation cannot read is one "
                    "whose every edge would be missing with nothing reporting"
                )
            # The CALLER'S `seen` is threaded through, never a fresh set. A new
            # set per hop makes the cycle guard protect one hop only, and two
            # playbooks invoking each other -- or one invoking itself, which is
            # the shape `ops_user`'s steady-state re-converge already has --
            # then recurse until the interpreter gives up. A RecursionError
            # reads as a defect in this module rather than as a scenario that
            # cannot be closed over.
            _collect_from_play_file(
                resolved,
                root=root,
                edges=edges,
                seen=seen if seen is not None else set(),
                scenario_root=scenario_root,
            )
            continue
        entry = (
            _relative(origin, root),
            f"{key.rsplit('.', 1)[-1]}(ansible-playbook)",
            f"expr:{target}",
        )
        if entry in PERMITTED_NESTED_PLAYBOOKS:
            continue
        raise DerivationRefused(
            f"{_relative(origin, root)}: a nested `ansible-playbook` names its "
            f"playbook by expression ({target!r}), so the derivation cannot "
            "close over where it leads. Refused rather than passed over. To "
            "permit this instance, add it to PERMITTED_NESTED_PLAYBOOKS keyed "
            f"{entry!r} with the reason it is safe -- an entry for the instance, "
            "never an exemption for the construction"
        )


def _collect_from_play_file(
    path: Path, *, root: Path, edges: set[str], seen: set, scenario_root: Path | None = None
) -> None:
    """Edges a play file contributes, following `import_playbook`.

    `seen` is the caller's, shared across every hop, so a cycle through any
    construction terminates rather than recursing.
    """
    resolved = path.resolve()
    # The scenario directory this walk is bounded by. Taken from the play file
    # the caller handed in, and carried unchanged through every hop -- an
    # imported or nested playbook belongs to the scenario that reached it, not
    # to whatever directory it happens to sit in.
    if scenario_root is None:
        scenario_root = path.parent
    if ("play", resolved) in seen:
        return
    seen.add(("play", resolved))
    for document in _documents(path, root):
        if not isinstance(document, list):
            continue
        for play in document:
            if not isinstance(play, dict):
                continue
            imported = play.get("import_playbook")
            if imported is not None:
                if not _is_literal(imported):
                    raise DerivationRefused(
                        f"{_relative(path, root)}: `import_playbook` names its "
                        f"playbook by something other than a literal "
                        f"({imported!r}), so the derivation cannot follow it"
                    )
                target = (path.parent / str(imported)).resolve()
                if not target.is_file():
                    raise DerivationRefused(
                        f"{_relative(path, root)}: `import_playbook` names "
                        f"{imported!r}, which resolves to no file. Refused "
                        "rather than passed over -- every edge in the playbook "
                        "it names would otherwise be missing silently"
                    )
                _collect_from_play_file(
                    target,
                    root=root,
                    edges=edges,
                    seen=seen,
                    scenario_root=scenario_root,
                )
                continue
            for entry in play.get("roles") or []:
                if isinstance(entry, str):
                    name = entry
                elif isinstance(entry, dict):
                    name = entry.get("role") or entry.get("name")
                else:
                    name = None
                if name is None:
                    continue
                if not _is_literal(name):
                    raise DerivationRefused(
                        f"{_relative(path, root)}: a `roles:` entry names a role "
                        f"by something other than a literal ({name!r})"
                    )
                _add_edge(str(name), origin=path, root=root, edges=edges)
            for key in PLAY_TASK_KEYS:
                _walk_tasks(
                    play.get(key),
                    origin=path,
                    root=root,
                    edges=edges,
                    seen=seen,
                    scenario_root=scenario_root,
                )


def _refuse_routes_out_of_a_roles_own_files(root: Path, role: str) -> None:
    """Refuse any construction in a role's own files reaching outside it."""
    role_root = Path(root) / ROLES_DIRECTORY / role
    for path in _role_own_files(root, role):
        for document in _documents(path, root):
            tasks = document if isinstance(document, list) else None
            if tasks is None:
                continue
            _refuse_tasks_reaching_out(tasks, origin=path, root=root, role_root=role_root)


def _refuse_tasks_reaching_out(tasks, *, origin: Path, root: Path, role_root: Path) -> None:
    for task in tasks:
        if not isinstance(task, dict):
            continue
        for key, value in task.items():
            if key in ROLE_INCLUSION_KEYS:
                name = value.get("name") if isinstance(value, dict) else value
                raise DerivationRefused(
                    f"{_relative(origin, root)}: a role's own task or handler "
                    f"file invokes another role ({name!r}). This route lies "
                    "outside every scenario directory, so no check that walks "
                    "those alone can see it, and following it is not attempted: "
                    "no role in this repository does this today, which is what "
                    "makes refusing free. See design.md Decision 2 of the change "
                    "`select-the-molecule-matrix-per-role`"
                )
            if key in COMMAND_KEYS:
                _handle_nested_playbook(
                    value, origin=origin, root=root, key=key, edges=None
                )
            if key in TASK_INCLUSION_KEYS:
                target = value.get("file") if isinstance(value, dict) else value
                if _escapes(target, origin, role_root):
                    raise DerivationRefused(
                        f"{_relative(origin, root)}: a role's own task or handler "
                        f"file reaches {target!r}, outside that role's own "
                        "directory. The rule is keyed on what is reached rather "
                        "than on a role being named -- an include of another "
                        "role's task file by path names no role and couples the "
                        "two exactly as an invocation would"
                    )
        for block in BLOCK_KEYS:
            if block in task:
                _refuse_tasks_reaching_out(
                    task[block], origin=origin, root=root, role_root=role_root
                )


def derive_graph(root) -> dict[str, set[str]]:
    """Forward edges: role -> the roles its own scenarios and `meta` reach.

    Ranges over every role DIRECTORY, not only the runnable ones. A role
    carrying no scenarios can still be reached, and a change to it is owed by
    whoever reaches it.
    """
    root = Path(root)
    graph: dict[str, set[str]] = {}
    for role in sorted(role_directories(root)):
        edges: set[str] = set()
        _refuse_routes_out_of_a_roles_own_files(root, role)
        _refuse_redirected_scenario_plays(root, role)
        meta = root / ROLES_DIRECTORY / role / "meta" / "main.yml"
        if meta.is_file():
            for document in _documents(meta, root):
                if not isinstance(document, dict):
                    continue
                for entry in document.get("dependencies") or []:
                    if isinstance(entry, str):
                        name = entry
                    elif isinstance(entry, dict):
                        name = entry.get("role") or entry.get("name")
                    else:
                        name = None
                    if name is None:
                        continue
                    if not _is_literal(name):
                        raise DerivationRefused(
                            f"{_relative(meta, root)}: a `dependencies` entry "
                            f"names a role by something other than a literal "
                            f"({name!r}). Refused rather than skipped, exactly "
                            "as the same shape is in a `roles:` list -- a "
                            "dependency this derivation cannot close over is an "
                            "edge it would otherwise drop with nothing reporting"
                        )
                    _add_edge(str(name), origin=meta, root=root, edges=edges)
        seen: set = set()
        for path in _scenario_play_files(root, role):
            _collect_from_play_file(path, root=root, edges=edges, seen=seen)
        # A role named by PATH is refused where the edge is ADDED, in
        # `_add_edge`, so the refusal can name the file holding it. Refusing
        # here instead would name only this directory: the edge set is
        # flattened by now and provenance is gone.
        #
        # Two edges are dropped rather than recorded. An external, dotted
        # Galaxy role is content this repository neither authors nor tests, so
        # it contributes nothing and is not a refusal -- `docker`'s
        # `meta/main.yml` names one today, and it is installed under a dotted
        # directory this module never enumerates. And a role's edge to ITSELF,
        # which nearly every converge declares, carries no information a reverse
        # closure can use: a role is always in its own closure as the seed, so
        # a self-edge would only make every role look like its own converger.
        #
        # What is NOT closed here: a plain literal naming no role directory at
        # all -- a typo -- contributes nothing and is not refused. Refusing it
        # would be the consistent polarity, and it is not done because the name
        # may legitimately be external content installed under a name this
        # module cannot see. Such a name fails at converge time, loudly, in
        # Molecule's own words rather than these.
        graph[role] = {
            edge for edge in edges if "." not in edge and edge != role
        }
    return graph


def reverse_closure(graph, seeds) -> set[str]:
    """The seeds plus every role reaching them, transitively.

    Terminates on a cycle rather than refusing one -- two roles' scenarios
    converging each other is legal, and nothing in this repository stops it.
    """
    edges = {role: set(targets) for role, targets in graph.items()}
    owed = set(seeds)
    frontier = list(owed)
    while frontier:
        current = frontier.pop()
        for role, targets in edges.items():
            if current in targets and role not in owed:
                owed.add(role)
                frontier.append(role)
    return owed


def attribute(changed_paths, root) -> set[str] | None:
    """The roles a changed-file list attributes to, or None to widen.

    None rather than an empty set on purpose: they mean different things, and
    conflating them is how a selection narrows to nothing. None is "this diff
    is not attributable, run everything"; an empty set never leaves here.
    """
    known = role_directories(root)
    seeds: set[str] = set()
    for raw in changed_paths:
        path = str(raw).strip()
        # `removeprefix`, not `lstrip`: the latter strips a CHARACTER SET, so
        # `.github/workflows/x.yml` would become `github/...`. Both spellings
        # widen, so nothing is riding on it today -- but a reader should not
        # have to work that out to know the line is correct.
        path = path.removeprefix("./")
        if not path:
            continue
        parts = path.split("/")
        if len(parts) >= 4 and parts[0] == "ansible" and parts[1] == "roles" and parts[2] in known:
            seeds.add(parts[2])
        else:
            # A shared manifest, the entry point, `ansible.cfg`, or a path
            # nobody anticipated. Widen. Wasteful is visible and correctable
            # in one line; narrow is silent and green.
            return None
    if not seeds:
        return None
    return seeds


def select_roles(changed_paths, root):
    """The roles this changed-file list owes, as a sorted list."""
    root = Path(root)
    runnable = roles_with_scenarios(root)
    if not runnable:
        raise EmptySelection(
            f"no role under {ROLES_DIRECTORY}/ carries a molecule/ directory, so "
            "there is nothing for the suite to run. Refusing to hand the matrix "
            "an empty list: an empty matrix is skipped, and a skip on a run that "
            "owed the suite is a green required status check for a suite that "
            "verified nothing"
        )
    seeds = attribute(changed_paths, root)
    if seeds is None:
        return sorted(runnable)
    graph = derive_graph(root)
    selection = reverse_closure(graph, seeds) & runnable
    if not selection:
        # The restriction left nothing, evaluated over the SELECTION as a whole
        # rather than per attributed role. A role with no scenarios that nothing
        # converges is unverifiable by this suite whether or not other roles
        # run, so widening for it buys no coverage where something else is
        # already running -- and where nothing is, a required check that cannot
        # be made green is worse than a wasted run.
        return sorted(runnable)
    return sorted(selection)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", default=".", help="the tree to read (default: the working directory)"
    )
    parser.add_argument(
        "--changed-files",
        default="",
        help="JSON array of the paths a pull request changed; empty selects every role",
    )
    arguments = parser.parse_args(argv)
    raw = arguments.changed_files.strip()
    changed = json.loads(raw) if raw else []
    try:
        print(json.dumps(select_roles(changed, arguments.root)))
    except (DerivationRefused, EmptySelection) as refusal:
        print(f"::error::{refusal}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover -- exercised through the workflow
    raise SystemExit(_main())
