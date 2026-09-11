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


def _documents(path: Path):
    """Every YAML document in a file, or none where it does not parse.

    A file that does not parse is not a route this derivation can read, but it
    is also not evidence of one: `ansible-lint` and `--syntax-check` own
    malformed YAML, and refusing here would make this module the second thing
    reporting it, in worse words.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        return [document for document in yaml.safe_load_all(text) if document is not None]
    except yaml.YAMLError:
        return []


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
        return ".." in candidate
    try:
        resolved = (origin.parent / candidate).resolve()
        role_root.resolve().relative_to  # noqa: B018 -- attribute probe, cheap
        resolved.relative_to(role_root.resolve())
    except (ValueError, OSError):
        return True
    return False


def _walk_tasks(tasks, *, origin: Path, root: Path, role: str, edges: set[str]) -> None:
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
                edges.add(str(name))
            elif key in TASK_INCLUSION_KEYS:
                target = value.get("file") if isinstance(value, dict) else value
                if isinstance(target, str) and ".." in target:
                    raise DerivationRefused(
                        f"{_relative(origin, root)}: `{key}` reaches "
                        f"{target!r}, which navigates outside this file's own "
                        "directory. The derivation has no rule for this "
                        "construction and refuses rather than passing over it: "
                        "it names no role and couples two of them exactly as an "
                        "invocation would"
                    )
            elif key in COMMAND_KEYS:
                _refuse_unpermitted_nested_playbook(
                    value, origin=origin, root=root, key=key
                )
        for block in BLOCK_KEYS:
            if block in task:
                _walk_tasks(
                    task[block], origin=origin, root=root, role=role, edges=edges
                )


def _refuse_unpermitted_nested_playbook(value, *, origin: Path, root: Path, key: str) -> None:
    """Refuse `ansible-playbook` over an expression unless an entry covers it."""
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
            continue
        entry = (_relative(origin, root), f"{key.rsplit('.', 1)[-1]}(ansible-playbook)", f"expr:{target}")
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
    path: Path, *, root: Path, role: str, edges: set[str], seen: set[Path]
) -> None:
    """Edges a play file contributes to `role`, following `import_playbook`."""
    resolved = path.resolve()
    if resolved in seen:
        return
    seen.add(resolved)
    for document in _documents(path):
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
                        f"playbook by something other than a literal ({imported!r}), "
                        "so the derivation cannot follow it"
                    )
                target = (path.parent / str(imported)).resolve()
                if target.is_file():
                    _collect_from_play_file(
                        target, root=root, role=role, edges=edges, seen=seen
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
                edges.add(str(name))
            for key in PLAY_TASK_KEYS:
                _walk_tasks(
                    play.get(key), origin=path, root=root, role=role, edges=edges
                )


def _refuse_routes_out_of_a_roles_own_files(root: Path, role: str) -> None:
    """Refuse any construction in a role's own files reaching outside it."""
    role_root = Path(root) / ROLES_DIRECTORY / role
    for path in _role_own_files(root, role):
        for document in _documents(path):
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
        meta = root / ROLES_DIRECTORY / role / "meta" / "main.yml"
        if meta.is_file():
            for document in _documents(meta):
                if not isinstance(document, dict):
                    continue
                for entry in document.get("dependencies") or []:
                    if isinstance(entry, str):
                        name = entry
                    elif isinstance(entry, dict):
                        name = entry.get("role") or entry.get("name")
                    else:
                        name = None
                    if _is_literal(name):
                        edges.add(str(name))
        seen: set[Path] = set()
        for path in _scenario_play_files(root, role):
            _collect_from_play_file(
                path, root=root, role=role, edges=edges, seen=seen
            )
        # Two edges are dropped rather than recorded. An external, dotted
        # Galaxy role is content this repository neither authors nor tests, so
        # it contributes nothing and is not a refusal -- `docker`'s
        # `meta/main.yml` names one today. And a role's edge to ITSELF, which
        # nearly every converge declares, carries no information a reverse
        # closure can use: a role is always in its own closure as the seed, so
        # a self-edge would only make every role look like its own converger.
        graph[role] = {
            edge for edge in edges if "." not in edge and edge != role
        }
    return graph


def reverse_closure(graph, seeds) -> set[str]:
    """The seeds plus every role reaching them, transitively.

    Terminates on a cycle rather than refusing one -- two roles' scenarios
    converging each other is legal, and nothing in this repository stops it.
    """
    owed = set(seeds)
    frontier = list(owed)
    while frontier:
        current = frontier.pop()
        for role, targets in dict(graph).items():
            if current in set(targets) and role not in owed:
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
        path = str(raw).strip().lstrip("./")
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
