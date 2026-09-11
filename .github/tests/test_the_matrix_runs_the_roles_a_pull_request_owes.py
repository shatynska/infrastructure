"""Static-assertion tests for selecting the Molecule matrix per role.

Derived from the delta specification of the OpenSpec change
`select-the-molecule-matrix-per-role`, before any implementation of that change
existed. The path those deltas sit at is not written here: a change's artifacts
move when it is archived, and this repository's citation convention is to name
the change and the artifact in prose instead.

The delta ADDS one requirement to `iac-cicd-pipeline` -- *The Molecule Matrix
Runs the Roles a Pull Request Owes*. Each class below names the scenario it
traces to, and every assertion is annotated SPECIFIED (it traces to SHALL text
or to a scenario in the delta) or DERIVED (it traces to that change's
`design.md` or `tasks.md` rather than to a scenario). See that change's
`test-plan.md` for the scenario-to-test mapping, the baseline, the scenarios
deliberately left uncovered, and the interface assumptions this file took.

Why this is an eleventh module rather than a section of an existing one
----------------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. Nothing here edits, deletes or disables an
existing test. Two assertions already on the trunk rest on propositions this
delta retires -- `test_ci_configuration`'s gate table has a row the delta
reverses, and two gate locators resolve a fourth input ambiguously once the
selection joins the three they read. Re-pointing those is the implementing
author's task; they are recorded in `test-plan.md`'s findings rather than
touched here.

Where this file needs a helper a module beside it already has, it imports it
rather than restating it. Two locators are deliberately duplicated rather than
imported -- see `SelectionWorkflowMixin` below, which says why.

THIS FILE SPAWNS `bash` ONLY, to execute workflow step bodies the way
`test_ci_configuration` already does, and imports the selector by file path
through `importlib` rather than by an `import` statement -- the selector lives
under `ansible/scripts/`, which is neither this suite's directory nor a pinned
dependency, and an `import` naming it would turn
`TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` red for a reason
that is not about privilege.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_the_matrix_runs_the_roles_a_pull_request_owes.TestAttributionWidensRatherThanNarrows \\
        .test_a_path_the_attribution_does_not_recognise_runs_every_role

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling import below resolve.

What no assertion here establishes
----------------------------------
Not that the matrix GitHub Actions actually starts is the one this file
computes. That is an Actions expression evaluated on a runner, and the
observation belongs to the change's own pull request -- its tasks.md section 6
records which direction is observable there and which is its ship-confirm gate.

Not what `dorny/paths-filter` reports as its changed-file list. The selector is
asserted over file lists this file supplies; that the list it receives in
production is the filter's `list-files: json` output is a workflow-shape
assertion, made here, and a behaviour observed on a real pull request.

Not that a role does what its scenarios say. This module reads committed files;
Molecule is what observes a role's behaviour, and this change touches no role.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_ci_configuration import (
    AGGREGATING_CONTEXT,
    ANSIBLE_VERIFY,
    ROOT,
    MoleculeWorkflowShapeMixin,
    compact,
    github_output_pairs,
    require_external_tools,
    role_names,
    roles_with_molecule_scenarios,
)

# --------------------------------------------------------------------------
# The interface this file assumes the implementation will expose.
#
# These tests are written before the selector exists, so the names below are
# ASSUMPTIONS this file takes rather than facts it reads, and `test-plan.md`
# records them as such so the implementing author can implement TO them rather
# than around them. Every one of them takes its root or its graph as an
# ARGUMENT, which is what makes the negative cases below exercisable against a
# fixture tree instead of by damaging the real one -- the shape that change's
# tasks.md 1.1, 1.3 and 2.2 require, not one invented here.
#
# A Python module under `ansible/scripts/`, beside `run-molecule` (design.md
# Decision 6). `select_molecule_roles.py` is the name this file assumes; it
# accepts any `*.py` in that directory exposing `select_roles`, so the name is
# an assumption and not a requirement. The module SHALL be importable without
# side effects -- any command-line entry point guarded by `__name__`.
#
#   select_roles(changed_paths, root) -> sequence[str]
#       THE ENTRY POINT the workflow calls. The roles the matrix SHALL run,
#       given the paths a pull request changed (repository-relative POSIX
#       strings, which need not exist: a deleted file is a changed path) and
#       the repository to derive the graph from. Attribution, closure,
#       restriction to the roles carrying scenarios, and the widening of an
#       otherwise-empty selection all happen inside it. Raises `EmptySelection`
#       rather than returning an empty result. A JSON array of names is
#       accepted here as well as a list, so that a selector returning the
#       string it hands the workflow is not failed for its return type.
#
#   derive_graph(root) -> dict[str, set[str]]
#       The role-dependency graph derived from the scenario definitions under
#       `root`: role -> the roles that role's own scenarios (and its
#       `meta/main.yml` dependencies) reach. FORWARD edges; the closure below
#       reverses them. Raises `DerivationRefused` for a construction it has no
#       rule for, for a role named by anything but a literal, for a role's own
#       task or handler file reaching outside that role's directory, and for a
#       nested playbook named by expression that no permitted entry records.
#
#   reverse_closure(graph, seeds) -> set[str]
#       The seeds together with every role reaching them through the graph,
#       directly or transitively. Terminates on a cycle.
#
#   roles_with_scenarios(root) -> set[str]
#       The roles the run can execute: directories under `ansible/roles/`
#       carrying a `molecule/` directory, under the same enumeration
#       `role_names()` uses -- dotted (Galaxy) directory names excluded.
#
#   PERMITTED_NESTED_PLAYBOOKS: mapping
#       The permitted-instance entries, keyed `(file, construction, target)`
#       in the form `PERMITTED_CONTROLLER_READS` already uses, and living in
#       the SELECTOR rather than in this module: the refusal executes there,
#       so that is where the permission has to be (tasks.md 2.2a).
#
#   DerivationRefused(Exception)
#   EmptySelection(Exception)
#       The two refusals, as distinct types, so that a test asserting one is
#       not satisfied by a TypeError from a mis-specified call.
# --------------------------------------------------------------------------

SELECTOR_DIRECTORY = ROOT / "ansible" / "scripts"
ASSUMED_SELECTOR = SELECTOR_DIRECTORY / "select_molecule_roles.py"
IDENTIFYING_SYMBOL = "select_roles"

_LOADED: dict[str, object] = {}


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"_selector_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"{path} could not be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selector():
    """The selector module, imported by path.

    Fails -- rather than errors -- naming the absent target, so that a run
    before the implementation exists reports "the target does not exist yet" in
    the words of the thing that is missing, and does not mask the assertions in
    this file that need nothing new.

    The assumed filename is tried first and any other module in the directory
    after it, so that the name is this file's assumption rather than a
    requirement it imposes on the implementation.
    """
    cached = _LOADED.get("module")
    if cached is not None:
        return cached
    candidates: list[Path] = []
    if SELECTOR_DIRECTORY.is_dir():
        found = sorted(SELECTOR_DIRECTORY.glob("*.py"))
        candidates = [path for path in found if path == ASSUMED_SELECTOR]
        candidates += [path for path in found if path != ASSUMED_SELECTOR]
    rejected: list[str] = []
    for path in candidates:
        try:
            module = _load_module(path)
        except Exception as error:  # noqa: BLE001 -- reported, not swallowed
            rejected.append(f"{path.name}: {type(error).__name__}: {error}")
            continue
        if not hasattr(module, IDENTIFYING_SYMBOL):
            rejected.append(f"{path.name}: exposes no `{IDENTIFYING_SYMBOL}`")
            continue
        _LOADED["module"] = module
        return module
    raise AssertionError(
        f"no module under {SELECTOR_DIRECTORY.relative_to(ROOT)} exposes "
        f"`{IDENTIFYING_SYMBOL}`. The change `select-the-molecule-matrix-per-role` "
        f"adds the selector there -- this file assumes "
        f"{ASSUMED_SELECTOR.relative_to(ROOT)} and accepts any other `*.py` in that "
        "directory exposing that name. Until it exists, this assertion has nothing "
        "to exercise: THIS IS THE ABSENT-TARGET FAILURE, not a wrong value, and "
        "nothing has been established about the selection's behaviour. Modules "
        f"considered: {rejected or 'none'}"
    )


def symbol(name: str):
    """One name the selector must expose, fetched lazily for the same reason."""
    module = selector()
    try:
        return getattr(module, name)
    except AttributeError:
        raise AssertionError(
            f"the selector module `{Path(getattr(module, '__file__', '?')).name}` "
            f"exposes no `{name}`. See this file's interface block: every one of "
            "those names is exercised by some assertion here, and an absent one "
            "leaves that assertion with nothing to run against"
        ) from None


def selected(changed_paths, root) -> set[str]:
    """`select_roles` normalised to a set.

    A JSON array is accepted as well as a sequence: the selector hands the
    workflow a JSON list, and a selector that returns exactly what it emits is
    not a wrong answer to the question these tests ask.
    """
    result = symbol("select_roles")(list(changed_paths), root)
    if isinstance(result, str):
        result = json.loads(result)
    return set(result)


def graph_of(root) -> dict:
    derived = symbol("derive_graph")(root)
    return {str(role): set(targets) for role, targets in dict(derived).items()}


def independent_reverse_closure(graph: dict, seeds) -> set[str]:
    """The reverse closure, computed here rather than by the selector.

    A second implementation on purpose. Asserting the selector's closure
    against the selector's own closure establishes nothing; this is what gives
    the real-tree assertions below an expected value that is derived from the
    tree rather than written down as a table -- so that a scenario added later
    changes the expectation by changing the tree, which is what the delta's
    scenario about a later scenario requires.
    """
    owed = set(seeds)
    frontier = list(owed)
    while frontier:
        current = frontier.pop()
        for role, targets in graph.items():
            if current in targets and role not in owed:
                owed.add(role)
                frontier.append(role)
    return owed


# --------------------------------------------------------------------------
# Fixture trees.
#
# Every negative case and every construction below is exercised against a tree
# this file writes, not against the repository. Three reasons, and the third is
# the one that matters most: a check whose subject is a committed file passes
# identically when it reads nothing, so the only way to establish that these
# assertions can FAIL is to point them at material chosen to falsify them; the
# real tree carries no refusable construction, by design.md Decision 2's own
# sweep; and the closure's cycle case cannot be shown on a tree that has no
# cycle.
# --------------------------------------------------------------------------

MINIMAL_MANIFEST = "collections: []\nroles: []\n"

def scenario_definition(role: str) -> str:
    """A minimal `molecule.yml`, with a per-role digest.

    Concatenated rather than formatted: the instance name carries a shell
    default whose braces `str.format` would read as a field. The digest is
    derived from the role name so that no two fixture roles share an image
    reference -- this suite asserts elsewhere that scenarios naming one
    repository name one digest, and a fixture tree is not the place to
    introduce a counterexample to somebody else's check.
    """
    digest = hashlib.sha256(role.encode("utf-8")).hexdigest()
    return (
        "---\n"
        "driver:\n"
        "  name: docker\n"
        "platforms:\n"
        '  - name: "${MOLECULE_INSTANCE_NAME:?no namespace}"\n'
        "    image: example.invalid/base@sha256:" + digest + "\n"
        "provisioner:\n"
        "  name: ansible\n"
    )


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class Tree:
    """A scratch repository the selector can be pointed at."""

    def __init__(self, case: unittest.TestCase, prefix: str = "molecule-selection-"):
        self.root = Path(tempfile.mkdtemp(prefix=prefix))
        case.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        write(self.root / "ansible" / "requirements.yml", MINIMAL_MANIFEST)

    def role_dir(self, role: str) -> Path:
        return self.root / "ansible" / "roles" / role

    def role_file(self, role: str, relative: str, text: str) -> Path:
        path = self.role_dir(role) / relative
        write(path, text)
        return path

    def scenario(self, role: str, name: str = "default", *, definition: str | None = None, **plays: str) -> Path:
        """A scenario directory: its `molecule.yml` plus the plays supplied."""
        directory = self.role_dir(role) / "molecule" / name
        write(
            directory / "molecule.yml",
            scenario_definition(role) if definition is None else definition,
        )
        for play, text in plays.items():
            write(directory / f"{play}.yml", text)
        return directory


def converge_through_roles_list(*entries: str) -> str:
    """A play reaching roles through `roles:`, in the spelling supplied."""
    body = "".join(f"    {entry}\n" for entry in entries)
    return "---\n- name: Converge\n  hosts: all\n  roles:\n" + body


# --------------------------------------------------------------------------
# The derivation: the four constructions it follows.
# --------------------------------------------------------------------------


class TestTheDerivationFollowsEveryConstructionThatReachesARole(unittest.TestCase):
    """SPECIFIED -- "The derivation SHALL follow, or refuse, every construction
    by which a scenario reaches a role", and scenario "A pull request confined
    to one role runs that role and the roles converging it", which is
    unsatisfiable for any construction the derivation does not read.

    WHICH four constructions are followed is DERIVED: design.md Decision 2
    enumerates them, and the delta obliges the derivation to follow or refuse
    rather than naming them. One test per construction, per that change's
    tasks.md 1.1: a single fixture carrying all four cannot show which
    construction a regression dropped.

    Each fixture supplies the edge; the assertion is that the derivation sees
    it. This is what establishes that these checks CAN fail -- the repository's
    own tree exercises `roles:`, `include_role` and `import_playbook` but would
    pass a derivation that read only the first.
    """

    def _tree_with_a_converged_sibling(self, converge: str) -> Tree:
        tree = Tree(self)
        tree.scenario("core", converge=converge_through_roles_list("- core"))
        tree.scenario("user", converge=converge)
        return tree

    def test_a_plays_roles_list_contributes_an_edge(self) -> None:
        """SPECIFIED as above; the three spellings are DERIVED (design.md
        Decision 2: "entries as bare strings or as mappings with `role:` or
        `name:`"). All three are live YAML and a derivation reading one is
        silent about the other two."""
        for spelling in ("- core", "- role: core", "- name: core"):
            with self.subTest(entry=spelling):
                tree = self._tree_with_a_converged_sibling(
                    converge_through_roles_list(spelling)
                )
                graph = graph_of(tree.root)
                self.assertIn(
                    "core",
                    graph.get("user", set()),
                    f"a play reaching `core` through a `roles:` entry written "
                    f"`{spelling}` contributed no edge, so a pull request changing "
                    "`core` would not run `user`'s scenarios -- the under-selection "
                    "this change exists to prevent, and the one nothing reports. "
                    f"The derived graph is {graph!r}",
                )

    def test_include_role_and_import_role_contribute_an_edge(self) -> None:
        """SPECIFIED as above; the spellings are DERIVED (design.md Decision 2:
        "bare and fully qualified, including inside `block`/`rescue`/`always`").
        The nested forms are not decoration: this repository's own
        `ghcr-credential-rejected` and `absent-ssh-cidrs` scenarios reach roles
        from inside a `block:`."""
        tree = Tree(self)
        for name in ("bare", "qualified", "blocked", "rescued", "alwaysed"):
            tree.scenario(name, converge=converge_through_roles_list(f"- {name}"))
        tree.scenario(
            "user",
            converge="""---
- name: Converge
  hosts: all
  tasks:
    - name: Bare include
      include_role:
        name: bare

    - name: Fully qualified import
      ansible.builtin.import_role:
        name: qualified

    - name: Reached from inside a block
      block:
        - name: In the block body
          ansible.builtin.include_role:
            name: blocked
      rescue:
        - name: In the rescue
          ansible.builtin.include_role:
            name: rescued
      always:
        - name: In the always
          ansible.builtin.import_role:
            name: alwaysed
""",
        )
        graph = graph_of(tree.root)
        self.assertEqual(
            {"bare", "qualified", "blocked", "rescued", "alwaysed"},
            graph.get("user", set()),
            "a scenario reaching five roles through `include_role`/`import_role` "
            "did not contribute all five edges. A construction not followed "
            "under-reads the graph, and under-reading loses coverage with nothing "
            f"reporting. The derived graph is {graph!r}",
        )

    def test_import_playbook_is_followed_into_the_playbook_it_names(self) -> None:
        """SPECIFIED as above; that `import_playbook` is FOLLOWED is DERIVED
        (design.md Decision 2: "which `platform_data_volume`'s reverse-order arm
        uses to build on its sibling -- today within one role, but nothing makes
        it so").

        The imported playbook is another role's, deliberately. Within one role,
        a derivation that merely sweeps every file in a scenario directory would
        see the same edges without following anything, and this assertion would
        pass on a derivation that does not read the construction at all.
        """
        tree = Tree(self)
        tree.scenario("base", converge=converge_through_roles_list("- base"))
        tree.scenario("core", converge=converge_through_roles_list("- core", "- base"))
        tree.scenario(
            "user",
            converge="---\n- import_playbook: ../../../core/molecule/default/converge.yml\n",
        )
        graph = graph_of(tree.root)
        self.assertEqual(
            {"core", "base"},
            graph.get("user", set()),
            "a scenario importing another role's playbook did not acquire that "
            "playbook's own edges. Following the import is the only way to see "
            "`base` here: it is named in no file under `user/`. A derivation that "
            "reads scenario directories without following this construction "
            f"under-reads the graph. The derived graph is {graph!r}",
        )

    def test_a_roles_meta_dependencies_contribute_an_edge(self) -> None:
        """SPECIFIED as above; reading `meta/main.yml` is DERIVED (design.md
        Decision 2: "a role's own `meta/main.yml` `dependencies`, which `docker`
        uses. Its entry names the external Galaxy role rather than one of ours,
        so it contributes no edge today and would contribute one silently the
        day it did")."""
        for spelling in ("- core", "- role: core"):
            with self.subTest(entry=spelling):
                tree = Tree(self)
                tree.scenario("core", converge=converge_through_roles_list("- core"))
                tree.scenario("user", converge=converge_through_roles_list("- user"))
                tree.role_file("user", "meta/main.yml", f"---\ndependencies:\n  {spelling}\n")
                graph = graph_of(tree.root)
                self.assertIn(
                    "core",
                    graph.get("user", set()),
                    "a role declaring a dependency on `core` in its own "
                    "`meta/main.yml` contributed no edge. This is the construction "
                    "that contributes nothing today and would contribute silently "
                    f"the day a role declares one. The derived graph is {graph!r}",
                )

    def test_an_external_galaxy_dependency_contributes_no_edge_and_is_not_refused(
        self,
    ) -> None:
        """DERIVED (design.md Decision 2, and the Context table, which records
        `docker`'s `meta/main.yml` naming `geerlingguy.docker`). The delta
        requires a refusal for what cannot be resolved; a dotted Galaxy role
        name IS a literal and resolves to no role of this repository's, so it
        must contribute nothing rather than refuse. Reconsider this assertion,
        do not weaken it, if the derivation comes to model external roles."""
        tree = Tree(self)
        tree.scenario("user", converge=converge_through_roles_list("- user"))
        tree.role_file(
            "user", "meta/main.yml", "---\ndependencies:\n  - role: example.external\n"
        )
        graph = graph_of(tree.root)
        self.assertEqual(
            set(),
            {target for target in graph.get("user", set()) if "." in target},
            "a dependency naming an external Galaxy role contributed an edge to a "
            "role this repository does not contain; the matrix would then be handed "
            f"a row nothing can run. The derived graph is {graph!r}",
        )

    def test_the_scenario_definition_file_is_not_read_for_role_names(self) -> None:
        """DERIVED (design.md Decision 2's closing paragraph, and tasks.md 1.1:
        "Do **not** read `molecule.yml`: its `platforms[].name` carries the
        Docker driver, and a derivation reaching it produces a graph in which
        most roles depend on `docker`").

        This is a recorded defect from the change's own handoff, not a
        hypothetical: the author's first attempt matched `name: docker` in a
        scenario definition and produced a graph claiming six roles depend on
        `docker`. Over-selection is the safe direction, which is exactly why
        nothing else would have reported it.
        """
        tree = Tree(self)
        tree.scenario("core", converge=converge_through_roles_list("- core"))
        tree.scenario(
            "user",
            definition="""---
driver:
  name: core
platforms:
  - name: core
    image: example.invalid/base@sha256:{d}
""".format(d="c" * 64),
            converge=converge_through_roles_list("- user"),
        )
        graph = graph_of(tree.root)
        self.assertNotIn(
            "core",
            graph.get("user", set()),
            "the derivation read a role name out of a scenario's `molecule.yml`, "
            "where `name:` carries the DRIVER and the instance rather than a role. "
            "Only that file's PATH is an input -- it identifies which role a "
            f"scenario belongs to. The derived graph is {graph!r}",
        )


# --------------------------------------------------------------------------
# The derivation: what it refuses.
# --------------------------------------------------------------------------


class TestTheDerivationRefusesWhatItCannotResolve(unittest.TestCase):
    """SPECIFIED -- scenario "A construction the derivation cannot resolve fails
    the run": "it SHALL fail identifying that construction and the file holding
    it, rather than passing over it and deriving a graph missing that edge".

    Its own class rather than a branch of the class above, per that change's
    tasks.md 1.2: this refusal is what keeps the followed list from silently
    going stale, and a refusal asserted as an aside is a refusal nobody reads.
    """

    def _assert_refused(self, root, *, naming: str) -> None:
        refusal = symbol("DerivationRefused")
        with self.assertRaises(refusal) as raised:
            symbol("derive_graph")(root)
        message = str(raised.exception)
        self.assertIn(
            naming,
            message,
            "the derivation refused without identifying the file holding the "
            f"construction; it said {message!r}. A refusal nobody can act on costs "
            "the same visible edit as one that names its cause, and buys nothing",
        )

    def test_a_role_named_by_anything_but_a_literal_is_refused(self) -> None:
        """SPECIFIED -- "a role name that is not a literal in the scenario text
        SHALL be refused rather than resolved or skipped"."""
        tree = Tree(self)
        tree.scenario("core", converge=converge_through_roles_list("- core"))
        tree.scenario(
            "user",
            converge="""---
- name: Converge
  hosts: all
  vars:
    chosen_role: core
  tasks:
    - name: Reach a role the derivation cannot resolve statically
      ansible.builtin.include_role:
        name: "{{ chosen_role }}"
""",
        )
        self._assert_refused(
            tree.root, naming="ansible/roles/user/molecule/default/converge.yml"
        )

    def test_a_construction_the_derivation_has_no_rule_for_is_refused(self) -> None:
        """SPECIFIED -- "SHALL refuse a construction it has no rule for rather
        than passing over it. Following and refusing are both conformant
        dispositions; passing over is not."

        The fixture reaches another role by PATH, naming no role at all, which
        is the case a refusal worded as "invoking another role" does not bite
        on while the coupling is identical.
        """
        tree = Tree(self)
        tree.scenario("core", converge=converge_through_roles_list("- core"))
        tree.role_file("core", "tasks/main.yml", "---\n- name: Noop\n  ansible.builtin.debug:\n    msg: core\n")
        tree.scenario(
            "user",
            converge="""---
- name: Converge
  hosts: all
  tasks:
    - name: Reach another role's tasks by path, through a construction with no rule
      ansible.builtin.include_tasks: ../../../core/tasks/main.yml
""",
        )
        self._assert_refused(
            tree.root, naming="ansible/roles/user/molecule/default/converge.yml"
        )

    def test_a_tree_carrying_none_of_these_is_not_refused(self) -> None:
        """DERIVED (tasks.md 1.2, read against this skill's rule that a check
        which can only fail is worth as little as one that can only pass). A
        derivation that refused everything would satisfy every refusal above
        while turning the required check red on every pull request in the
        repository -- the failure tasks.md 2.2a names in as many words."""
        tree = Tree(self)
        tree.scenario("core", converge=converge_through_roles_list("- core"))
        tree.scenario("user", converge=converge_through_roles_list("- core", "- user"))
        tree.role_file(
            "user",
            "tasks/main.yml",
            "---\n- name: Role-local include\n  ansible.builtin.include_tasks: install.yml\n",
        )
        tree.role_file("user", "tasks/install.yml", "---\n- name: Noop\n  ansible.builtin.debug:\n    msg: ok\n")
        self.assertEqual(
            {"core"},
            graph_of(tree.root).get("user", set()),
            "a tree carrying only followable constructions and a role-local include "
            "was refused, or lost its edge. A role's own file reaching INSIDE its "
            "own directory is not the route design.md Decision 2 closes",
        )


ROLE_INVOCATION = re.compile(
    r"^\s*(?:-\s*)?(?:ansible\.builtin\.)?(?:include_role|import_role)\s*:",
    re.MULTILINE,
)
ROLE_NAVIGATION = re.compile(r"\.\./")


def role_files_reaching_outside(root) -> tuple[list[str], int]:
    """Role task and handler files reaching outside their own role directory,
    and how many files were read to say so.

    Takes its root as an argument for the reason every helper in this file
    does: a check whose subject is a committed file passes identically when it
    reads nothing, so the only way to establish that this one can FAIL is to
    point it at a tree written to falsify it. The real tree carries no such
    route -- that is the finding, not the check's warrant.

    Dotted directory names are excluded here as `role_names()` excludes them:
    an installed Galaxy role's own tasks are not this repository's to refuse.
    """
    base = Path(root)
    roles_directory = base / "ansible" / "roles"
    offenders: list[str] = []
    scanned = 0
    if not roles_directory.is_dir():
        return offenders, scanned
    for role in sorted(
        entry.name
        for entry in roles_directory.iterdir()
        if entry.is_dir() and not entry.name.startswith(".") and "." not in entry.name
    ):
        for subdirectory in ("tasks", "handlers"):
            directory = roles_directory / role / subdirectory
            if not directory.is_dir():
                continue
            for path in sorted([*directory.rglob("*.yml"), *directory.rglob("*.yaml")]):
                scanned += 1
                text = path.read_text(encoding="utf-8", errors="replace")
                relative = path.relative_to(base).as_posix()
                if ROLE_INVOCATION.search(text):
                    offenders.append(f"{relative}: invokes another role")
                if ROLE_NAVIGATION.search(text):
                    offenders.append(f"{relative}: navigates outside its own role")
    return sorted(set(offenders)), scanned


class TestARolesOwnFilesReachingOutsideItAreRefused(unittest.TestCase):
    """SPECIFIED -- scenario "A role's own tasks reaching outside that role is
    refused": "it SHALL fail identifying that file, rather than deriving a graph
    missing that edge -- such a route lies outside every scenario directory and
    no check that walks those alone can see it".

    And the rule keyed on what is reached: "an include of another role's task
    file by path names no role, and couples the two exactly as an invocation
    would".
    """

    def _tree(self) -> Tree:
        tree = Tree(self)
        tree.scenario("core", converge=converge_through_roles_list("- core"))
        tree.role_file("core", "tasks/main.yml", "---\n- name: Noop\n  ansible.builtin.debug:\n    msg: core\n")
        tree.scenario("user", converge=converge_through_roles_list("- user"))
        return tree

    def _assert_refused_naming(self, root, relative: str) -> None:
        refusal = symbol("DerivationRefused")
        with self.assertRaises(refusal) as raised:
            symbol("derive_graph")(root)
        self.assertIn(
            relative,
            str(raised.exception),
            "the derivation refused without identifying the role file holding the "
            f"route; it said {str(raised.exception)!r}",
        )

    def test_a_role_task_file_invoking_another_role_is_refused(self) -> None:
        """SPECIFIED -- as above, the naming half of the rule."""
        tree = self._tree()
        tree.role_file(
            "user",
            "tasks/main.yml",
            "---\n- name: Reach the sibling role from the role's own tasks\n"
            "  ansible.builtin.include_role:\n    name: core\n",
        )
        self._assert_refused_naming(tree.root, "ansible/roles/user/tasks/main.yml")

    def test_a_role_task_file_reaching_another_roles_file_by_path_is_refused(self) -> None:
        """SPECIFIED -- the half keyed on what is reached rather than on a role
        being named. This is the one a name-keyed refusal misses while the
        coupling is identical, and it is why design.md Decision 2 words the rule
        over the artefact."""
        tree = self._tree()
        tree.role_file(
            "user",
            "tasks/main.yml",
            "---\n- name: Reach the sibling role's tasks by path, naming no role\n"
            "  ansible.builtin.include_tasks: ../../core/tasks/main.yml\n",
        )
        self._assert_refused_naming(tree.root, "ansible/roles/user/tasks/main.yml")

    def test_a_handler_file_reaching_outside_its_role_is_refused(self) -> None:
        """SPECIFIED -- the rule names "a role's own task or handler file", and
        a derivation reading only `tasks/` satisfies every assertion above while
        leaving handlers a route nothing sees."""
        tree = self._tree()
        tree.role_file(
            "user",
            "handlers/main.yml",
            "---\n- name: Reach the sibling role from a handler\n"
            "  ansible.builtin.include_role:\n    name: core\n",
        )
        self._assert_refused_naming(tree.root, "ansible/roles/user/handlers/main.yml")

    def test_no_role_in_this_repository_reaches_outside_its_own_directory_today(self) -> None:
        """SPECIFIED -- the same scenario, read over the real tree, which is
        what records the refusal's cost as nil rather than assuming it
        (tasks.md 1.2a).

        Scanned here rather than asked of the selector: a derivation that never
        reads `tasks/` or `handlers/` also raises nothing, so answering this
        question with `derive_graph` alone would pass on the very defect the
        fixtures above exist to catch.
        """
        offenders, scanned = role_files_reaching_outside(ROOT)
        self.assertTrue(
            scanned,
            "no role task or handler file was read, so this assertion would record "
            "the refusal's cost as nil having examined nothing",
        )
        self.assertEqual(
            [],
            offenders,
            "these role files reach outside their own role, which the derivation "
            f"refuses: {offenders}. The refusal was adopted on the strength of this "
            "being empty -- design.md Decision 2 records the sweep. Either the route "
            "is withdrawn, or the change's decision is revisited; adding a rule to "
            "follow it is a decision, not a fix",
        )

    def test_the_scan_reports_a_role_that_does_reach_outside(self) -> None:
        """DERIVED (this library's testing floor: a check whose target already
        carries the asserted property passes without discriminating, so the
        only thing establishing that it CAN fail is running it over material
        written to falsify it).

        The real tree is clean, and will be clean tomorrow whether this scan
        reads anything or not. This is the fixture that separates "no role does
        this" from "nothing looked".
        """
        tree = Tree(self)
        tree.role_file(
            "user",
            "tasks/main.yml",
            "---\n- name: Invoke the sibling role\n"
            "  ansible.builtin.include_role:\n    name: core\n",
        )
        tree.role_file(
            "user",
            "handlers/main.yml",
            "---\n- name: Reach out by path\n"
            "  ansible.builtin.include_tasks: ../../core/tasks/main.yml\n",
        )
        tree.role_file(
            "core",
            "tasks/main.yml",
            "---\n- name: Stay inside the role\n"
            "  ansible.builtin.include_tasks: install.yml\n",
        )
        tree.role_file("core", "tasks/install.yml", "---\n- name: Noop\n  ansible.builtin.debug:\n    msg: ok\n")
        offenders, scanned = role_files_reaching_outside(tree.root)
        self.assertEqual(4, scanned, "the scan did not read every role file the fixture holds")
        self.assertEqual(
            [
                "ansible/roles/user/handlers/main.yml: navigates outside its own role",
                "ansible/roles/user/tasks/main.yml: invokes another role",
            ],
            offenders,
            "the scan over a tree written to falsify it reported something other "
            "than the two routes that tree carries -- so a green result over the "
            "real tree establishes nothing about whether a route would be seen",
        )


class TestARouteThatCannotBeClosedOverIsPermittedByInstance(unittest.TestCase):
    """SPECIFIED -- scenario "A route that cannot be closed over is permitted by
    instance, not by construction": "it SHALL refuse unless an explicit entry
    records that instance, keyed on file, construction and resolved target;
    exempting the construction wholesale SHALL NOT be accepted in place of such
    an entry"."""

    NESTED_PLAYBOOK_PLAY = """---
- name: Verify
  hosts: all
  tasks:
    - name: Re-converge through a nested playbook named by expression
      ansible.builtin.command:
        argv:
          - ansible-playbook
          - -i
          - "{{ nested_inventory }}"
          - "{{ nested_scenario_dir }}/converge.yml"
      delegate_to: localhost
      become: false
      changed_when: false
"""

    def test_a_nested_playbook_named_by_expression_is_refused_where_no_entry_covers_it(
        self,
    ) -> None:
        """SPECIFIED -- as above. A second such construction, in a file no entry
        names, refuses: that is what distinguishes an entry for the instance
        from an exemption for the construction, and a test permitting the
        construction passes on exactly the regression this guards."""
        tree = Tree(self)
        tree.scenario(
            "user",
            "revocation-like",
            converge=converge_through_roles_list("- user"),
            verify=self.NESTED_PLAYBOOK_PLAY,
        )
        refusal = symbol("DerivationRefused")
        with self.assertRaises(refusal) as raised:
            symbol("derive_graph")(tree.root)
        self.assertIn(
            "ansible/roles/user/molecule/revocation-like/verify.yml",
            str(raised.exception),
            "the derivation refused a nested playbook named by expression without "
            f"identifying the file; it said {str(raised.exception)!r}",
        )

    def test_the_permitted_entries_are_keyed_by_instance(self) -> None:
        """SPECIFIED -- "keyed on file, construction and resolved target, in the
        same form this repository already uses to permit such a read. A blanket
        exemption for the construction SHALL NOT be written in place of an entry
        for the instance."

        Reads the entry rather than restating it (tasks.md 1.2b): the test
        asserts the SHAPE the delta requires and that the tree's own instance is
        covered by one, not what the entry says.
        """
        permitted = dict(symbol("PERMITTED_NESTED_PLAYBOOKS"))
        self.assertTrue(
            permitted,
            "the selector permits no nested-playbook instance at all. This "
            "repository contains one -- `ops_user`'s `revocation-steady-state` "
            "scenario re-converges through `ansible-playbook` over an expression -- "
            "so a selector shipping the refusal with no entry turns the required "
            "check red on EVERY pull request in the repository",
        )
        malformed = [key for key in permitted if not (isinstance(key, tuple) and len(key) == 3)]
        self.assertEqual(
            [],
            malformed,
            "these permitted entries are not keyed on (file, construction, target): "
            f"{malformed}. A key carrying less than that is an exemption for the "
            "construction wearing an entry's clothes",
        )
        files = {key[0] for key in permitted}
        self.assertIn(
            "ansible/roles/ops_user/molecule/revocation-steady-state/verify.yml",
            files,
            "no permitted entry names the one file in this repository that reaches a "
            "nested playbook by expression. `PERMITTED_CONTROLLER_READS` already "
            "records that same read as `delegated-path` "
            "`expr:{{ ops_user_nested_scenario_dir }}/converge.yml`; the selector "
            f"needs its own entry, because the refusal executes there. It names {sorted(files)}",
        )

    def test_the_repositorys_own_tree_derives_without_refusal(self) -> None:
        """SPECIFIED -- the umbrella of every refusal above, read over the real
        tree. Each refusal is a fact about the repository as much as about the
        derivation: a derivation that refuses this tree turns the required check
        red on every pull request, and a permitted entry is how the one
        unclosable route is admitted."""
        graph = graph_of(ROOT)
        self.assertTrue(
            graph,
            "the derivation produced an empty graph over this repository, whose "
            "scenarios converge sibling roles in four places. An empty graph makes "
            "every closure the identity and every selection one role -- the silent "
            "under-selection this change exists to prevent",
        )


# --------------------------------------------------------------------------
# The closure.
# --------------------------------------------------------------------------


class TestTheReverseClosureOverAFixtureGraph(unittest.TestCase):
    """SPECIFIED -- scenario "A pull request confined to one role runs that role
    and the roles converging it": "directly or transitively".

    Over a fixture graph with a known answer, per tasks.md 1.3. The real tree
    has no cycle today and nothing stops one -- two roles' scenarios converging
    each other is legal -- so termination is showable here and nowhere else.
    """

    # Forward edges, as `derive_graph` produces them: the key's scenarios reach
    # the values. Reversed, `c` is owed by `b` and `a`.
    GRAPH = {
        "a": {"b"},
        "b": {"c"},
        "c": set(),
        "x": {"y"},
        "y": {"x"},
        "lonely": set(),
    }

    def test_the_closure_carries_its_own_seed(self) -> None:
        """SPECIFIED -- "the matrix SHALL run that role together with every role
        whose scenarios converge it". The seed is the role whose files changed;
        a closure that dropped it would run the convergers and not the change."""
        self.assertEqual(
            {"lonely"},
            set(symbol("reverse_closure")(self.GRAPH, {"lonely"})),
            "the closure of a role nothing converges is not that role alone",
        )

    def test_the_closure_includes_transitive_convergers(self) -> None:
        """SPECIFIED -- "directly or transitively". A closure taking one step
        returns `{c, b}` here and looks right on this repository's tree, where
        every edge happens to be one step from `docker`."""
        self.assertEqual(
            {"a", "b", "c"},
            set(symbol("reverse_closure")(self.GRAPH, {"c"})),
            "the closure of `c` missed `a`, which converges `c` through `b`. Every "
            "cross-role edge in this repository is one step today, so a one-step "
            "closure passes every real-tree assertion in this file",
        )

    def test_the_closure_terminates_on_a_cycle(self) -> None:
        """DERIVED (tasks.md 1.3) -- no scenario states this. Two roles whose
        scenarios converge each other is legal Ansible and legal Molecule, and a
        closure written as a naive recursion does not return. Reconsider this
        assertion, do not weaken it, if cycles come to be refused instead --
        refusing is a conformant disposition, silently recursing is not."""
        self.assertEqual(
            {"x", "y"},
            set(symbol("reverse_closure")(self.GRAPH, {"x"})),
            "the closure over a cycle did not resolve to the two roles in it",
        )

    def test_the_closure_of_several_seeds_is_the_union(self) -> None:
        """DERIVED (design.md's "A role is renamed" trade-off: "the diff carries
        both the old and the new directory, both attribute, and the closure
        covers both"). A pull request touching two roles is the ordinary case
        this rests on."""
        self.assertEqual(
            {"a", "b", "c", "lonely"},
            set(symbol("reverse_closure")(self.GRAPH, {"c", "lonely"})),
            "the closure of two seeds is not the union of their closures",
        )


class TestTheClosureOverTheRepositorysOwnTree(unittest.TestCase):
    """SPECIFIED -- scenario "A pull request confined to one role runs that role
    and the roles converging it", and scenario "A scenario added later is
    covered without editing the check".

    The expected values are COMPUTED FROM THE TREE, never written down. The
    Context table in design.md records that `docker` owes four roles today and
    `deploy_user` two; asserting those numerals would be asserting today's tree,
    and the delta requires a scenario added later to be covered with no edit to
    this check.
    """

    def setUp(self) -> None:
        self.graph = graph_of(ROOT)
        self.discovered = roles_with_molecule_scenarios()

    def test_the_derived_graph_carries_the_cross_role_edges_this_tree_declares(self) -> None:
        """SPECIFIED -- the derivation is what the closure is taken over, so an
        empty or partial graph satisfies every closure assertion below while
        selecting one role where four are owed.

        A SUBSET assertion, not an equality: an edge added later is covered
        without an edit here, and only an edge REMOVED -- a deliberate act on
        the scenarios -- disturbs it. The three edges named are read from the
        scenarios themselves, which converge these roles through `roles:` and
        `include_role` today.
        """
        declared = {
            ("deploy_user", "docker"),
            ("image_prune", "docker"),
            ("ops_user", "docker"),
            ("ops_user", "deploy_user"),
        }
        missing = sorted(
            f"{source} -> {target}"
            for source, target in declared
            if target not in self.graph.get(source, set())
        )
        self.assertEqual(
            [],
            missing,
            "the derivation missed edges this repository's scenarios declare: "
            f"{missing}. Each is a `roles:` or `include_role` entry in that role's "
            "own converge play. A missing edge means a pull request changing the "
            "target does not run the source's scenarios, and nothing reports it. "
            f"The derived graph is {self.graph!r}",
        )

    def test_every_roles_selection_is_the_reverse_closure_of_the_derived_graph(self) -> None:
        """SPECIFIED -- "what a set of changed files owes SHALL be the reverse
        closure of a role-dependency graph derived from the scenario definitions
        in the checkout being tested".

        The expected value comes from this module's own closure over the derived
        graph -- a second implementation -- so that the assertion is over the
        selector's closure rather than a restatement of it.
        """
        self.assertTrue(self.discovered, "no role under ansible/roles/ carries scenarios")
        for role in sorted(self.discovered):
            with self.subTest(role=role):
                expected = independent_reverse_closure(self.graph, {role}) & self.discovered
                self.assertEqual(
                    expected,
                    selected([f"ansible/roles/{role}/tasks/main.yml"], ROOT),
                    f"the selection for a change under `{role}` is not the reverse "
                    "closure of the derived graph restricted to the roles that carry "
                    f"scenarios. The derived graph is {self.graph!r}",
                )

    def test_a_role_whose_closure_is_smaller_than_the_tree_runs_no_other_role(self) -> None:
        """SPECIFIED -- scenario "A pull request confined to one role runs that
        role and the roles converging it": "and SHALL NOT run any other role",
        which is the whole prize and the half a closure assertion alone does not
        establish.

        Non-vacuity is asserted rather than assumed: if every role's closure
        were the whole tree, this check would pass having established nothing,
        and that is the state a broken derivation produces.
        """
        narrow = {
            role: independent_reverse_closure(self.graph, {role}) & self.discovered
            for role in self.discovered
        }
        proper = {role: owed for role, owed in narrow.items() if owed < self.discovered}
        self.assertTrue(
            proper,
            "every role's closure is the whole tree, so no assertion here can "
            "distinguish a narrowed run from the full suite. Either the graph is "
            "over-read -- the `molecule.yml` defect design.md Decision 2 names -- or "
            f"the tree genuinely couples every role. The derived graph is {self.graph!r}",
        )
        for role, owed in sorted(proper.items()):
            with self.subTest(role=role):
                self.assertEqual(
                    set(),
                    selected([f"ansible/roles/{role}/defaults/main.yml"], ROOT) - owed,
                    f"the selection for a change confined to `{role}` runs roles "
                    "outside its closure, which is the runner time this change "
                    "exists to stop spending",
                )

    def test_a_role_no_scenario_converges_runs_alone(self) -> None:
        """SPECIFIED -- scenario "A role no scenario converges runs alone": "the
        matrix SHALL run that role alone".

        Which roles those are is computed, not named: today `hardening`,
        `platform_data_volume` and `swap` are converged by nobody, and a
        scenario added later that converges one of them changes this
        expectation by changing the tree rather than by an edit here.
        """
        alone = sorted(
            role
            for role in self.discovered
            if not any(role in targets for source, targets in self.graph.items() if source != role)
        )
        self.assertTrue(
            alone,
            "every role in this tree is converged by another role's scenarios, so "
            "this scenario has no instance here. That is a fact worth hearing rather "
            f"than passing over. The derived graph is {self.graph!r}",
        )
        for role in alone:
            with self.subTest(role=role):
                self.assertEqual(
                    {role},
                    selected([f"ansible/roles/{role}/tasks/main.yml"], ROOT),
                    f"a change confined to `{role}`, which no other role's scenarios "
                    "converge, selected more than that role alone",
                )

    def test_a_scenario_added_later_is_covered_without_editing_this_check(self) -> None:
        """SPECIFIED -- scenario "A scenario added later is covered without
        editing the check": "the derived graph SHALL carry the new edge and the
        check SHALL assert the closure including it".

        Shown over a fixture, because showing it over the real tree would mean
        adding a scenario to the repository. The check that is not edited is
        this method: the same call is made twice, and the tree between the two
        calls is what changes.
        """
        tree = Tree(self)
        tree.scenario("core", converge=converge_through_roles_list("- core"))
        tree.scenario("late", converge=converge_through_roles_list("- late"))
        before = selected(["ansible/roles/core/tasks/main.yml"], tree.root)
        self.assertEqual(
            {"core"},
            before,
            "the fixture's starting state is not the one this assertion rests on",
        )
        tree.scenario(
            "late",
            "builds-on-core",
            converge=converge_through_roles_list("- core", "- late"),
        )
        after = selected(["ansible/roles/core/tasks/main.yml"], tree.root)
        self.assertEqual(
            {"core", "late"},
            after,
            "a scenario added after the graph was first derived did not put its role "
            "in the closure. A graph recorded in a file is a list, and a list that "
            "falls behind the scenarios it describes under-selects silently",
        )


# --------------------------------------------------------------------------
# Attribution, restriction and widening.
# --------------------------------------------------------------------------


class TestAttributionWidensRatherThanNarrows(unittest.TestCase):
    """SPECIFIED -- "Attribution is by role directory, and everything else
    widens", and the three scenarios that carry the polarity.

    The widening rule's failure mode is silent, so the check that matters most
    here is the one over an UNRECOGNISED path: a check exercising only the paths
    somebody enumerated passes on a selector that narrows an unforeseen one to
    nothing.
    """

    SHARED_INPUTS = (
        "ansible/requirements.yml",
        "ansible/requirements-test.txt",
        "ansible/scripts/run-molecule",
        "ansible/ansible.cfg",
    )

    # Paths no rule in this attribution names -- the file nobody anticipated,
    # in three shapes: a new directory, a new top-level file, and a file beside
    # the roles directory rather than inside a role.
    UNRECOGNISED = (
        "ansible/a-directory-nobody-has-considered/new-file.yml",
        "ansible/some-new-manifest.toml",
        "ansible/roles/README.md",
    )

    def setUp(self) -> None:
        self.discovered = roles_with_molecule_scenarios()
        self.assertTrue(self.discovered, "no role under ansible/roles/ carries scenarios")

    def test_a_shared_input_runs_every_role(self) -> None:
        """SPECIFIED -- scenario "A shared input runs every role": "the matrix
        SHALL run every discovered role"."""
        for path in self.SHARED_INPUTS:
            with self.subTest(path=path):
                self.assertEqual(
                    self.discovered,
                    selected([path], ROOT),
                    f"`{path}` determines what every scenario runs under, and "
                    "selected less than every discovered role",
                )

    def test_a_path_the_attribution_does_not_recognise_runs_every_role(self) -> None:
        """SPECIFIED -- scenario "A path the attribution does not recognise runs
        every role": "the matrix SHALL run every discovered role, rather than
        selecting none -- a path nobody anticipated SHALL widen the run rather
        than silently narrow it".

        THE ASSERTION IS EXPLICIT RATHER THAN INFERRED FROM THE SHARED INPUTS
        ABOVE, per tasks.md 1.5. A selector that enumerated the four shared
        inputs and resolved everything else to nothing passes that test and
        fails this one, and this is the direction that costs coverage and
        reports green.
        """
        for path in self.UNRECOGNISED:
            with self.subTest(path=path):
                self.assertEqual(
                    self.discovered,
                    selected([path], ROOT),
                    f"`{path}` is under `ansible/`, is admitted by the suite's change "
                    "detection, and matches no attribution rule. Anything but every "
                    "discovered role here is a narrowing nobody stated: wasteful and "
                    "visible is the direction this change chose over silent and green",
                )

    def test_a_shared_input_alongside_a_role_still_runs_every_role(self) -> None:
        """SPECIFIED -- "Anything not attributable to exactly one role selects
        every role". A diff carries many paths; a selector taking the first, or
        the narrowest, satisfies both tests above and loses this one."""
        role = sorted(self.discovered)[0]
        self.assertEqual(
            self.discovered,
            selected(["ansible/requirements.yml", f"ansible/roles/{role}/tasks/main.yml"], ROOT),
            "a diff carrying a shared input alongside one role's file selected less "
            "than every role; the shared input determines what every scenario runs "
            "under whatever else the diff touched",
        )

    def test_a_change_to_a_role_carrying_no_scenarios_still_runs_the_roles_that_converge_it(
        self,
    ) -> None:
        """SPECIFIED -- scenario "A change to a role carrying no scenarios still
        runs the roles that converge it": "the matrix SHALL run those other
        roles, rather than resolving the change to an empty selection".

        BOTH HALVES, per tasks.md 1.5: that the convergers are selected, and
        that the scenario-less role is NOT. A test asserting only the first
        passes on a selector that hands the matrix a row the runner cannot
        execute, which is the same wrong answer the widening case rejects.
        """
        tree = Tree(self)
        tree.role_file("base", "tasks/main.yml", "---\n- name: Noop\n  ansible.builtin.debug:\n    msg: base\n")
        tree.scenario("user", converge=converge_through_roles_list("- base", "- user"))
        tree.scenario("bystander", converge=converge_through_roles_list("- bystander"))
        self.assertEqual(
            {"user"},
            selected(["ansible/roles/base/tasks/main.yml"], tree.root),
            "a change to a role with no scenarios of its own, converged by `user`'s, "
            "did not resolve to `user` alone. Attribution rests on the DIRECTORY "
            "name rather than on the discovered set: attributing only to roles that "
            "carry scenarios drops the diff before the closure runs and loses the "
            "convergers with it, and carrying `base` into the matrix hands the "
            "runner a row for a role that never had anything to execute",
        )

    def test_a_role_in_the_closure_that_carries_no_scenarios_is_not_given_a_matrix_row(
        self,
    ) -> None:
        """SPECIFIED -- scenario "A role in the closure that carries no
        scenarios is not given a matrix row": "the selection SHALL carry only
        the roles that can be run".

        The non-seed case, reached through `meta/main.yml` -- design.md Decision
        3 records it as the reason the restriction ranges over the whole closure
        rather than over the seed, and as the case an implementer optimising
        "restrict the seed, it is the only one that can fail" gets wrong. No
        role in this repository is one today, so it is shown on a fixture.
        """
        tree = Tree(self)
        tree.scenario("core", converge=converge_through_roles_list("- core"))
        tree.scenario("runner", converge=converge_through_roles_list("- core", "- runner"))
        tree.role_file("dependent", "meta/main.yml", "---\ndependencies:\n  - role: core\n")
        tree.role_file(
            "dependent", "tasks/main.yml", "---\n- name: Noop\n  ansible.builtin.debug:\n    msg: dependent\n"
        )
        self.assertEqual(
            {"core", "runner"},
            selected(["ansible/roles/core/tasks/main.yml"], tree.root),
            "the closure of `core` contains `dependent`, which declares no scenarios, "
            "and the selection carried it into the matrix. A row the runner cannot "
            "execute fails on a role that never had anything to execute",
        )


class TestARoleNothingConvergesAndNothingTestsWidensOnItsOwn(unittest.TestCase):
    """SPECIFIED -- scenarios "A change to a role that nothing converges and
    nothing tests runs every role" and "An unverifiable role alongside a
    verifiable one does not widen the run".

    `ansible/roles/tailscale/` is named here rather than built as a fixture, per
    tasks.md 1.5a: the tree contains this case NOW, and a fixture would let it
    be read as hypothetical. `docs/change-queue.md` entry 3b owns its having no
    scenario.
    """

    UNVERIFIABLE = "tailscale"

    def setUp(self) -> None:
        self.discovered = roles_with_molecule_scenarios()
        self.assertIn(
            self.UNVERIFIABLE,
            role_names(),
            f"`ansible/roles/{self.UNVERIFIABLE}/` is not a role directory in this "
            "repository any more. This assertion is about the tree's own live "
            "instance of the widening case; if the role was removed, the case needs "
            "a new instance or a recorded decision that it has none",
        )
        self.assertNotIn(
            self.UNVERIFIABLE,
            self.discovered,
            f"`{self.UNVERIFIABLE}` now carries scenarios, so it is no longer the "
            "unverifiable role this assertion is about. That is good news and an "
            "edit to this check, not a defect in the selector",
        )

    def test_a_change_confined_to_it_runs_every_role(self) -> None:
        """SPECIFIED -- "the matrix SHALL run every discovered role, rather than
        resolving to an empty selection or to a row for a role with no scenarios
        -- a required status check SHALL NOT be left unsatisfiable for a change
        this suite cannot verify".

        Both wrong answers are asserted explicitly, per tasks.md 1.5a: not the
        empty set, and not a row for a role with no `molecule/` directory.
        Either makes a required check its author cannot make green.
        """
        selection = selected([f"ansible/roles/{self.UNVERIFIABLE}/tasks/main.yml"], ROOT)
        self.assertNotEqual(
            set(),
            selection,
            "a change confined to the unverifiable role resolved to an empty "
            "selection, which hands the matrix an empty list and leaves a legitimate "
            "pull request unable to satisfy a required check",
        )
        self.assertNotIn(
            self.UNVERIFIABLE,
            selection,
            f"the selection carries `{self.UNVERIFIABLE}`, which has no `molecule/` "
            "directory for `run-molecule test --all` to find. The restriction to the "
            "roles the run can execute happens after the closure and before the "
            "matrix, and dropping it here is the second of the two wrong answers",
        )
        self.assertEqual(
            self.discovered,
            selection,
            "a change confined to a role that nothing converges and nothing tests "
            "did not widen to every discovered role",
        )

    def test_it_does_not_widen_a_diff_that_also_touches_a_role_that_can_be_run(self) -> None:
        """SPECIFIED -- scenario "An unverifiable role alongside a verifiable one
        does not widen the run": "the matrix SHALL run the latter's selection
        alone, rather than widening to every role -- the unverifiable role is
        unverifiable whether or not the others run, so widening for it buys no
        coverage".

        THE HALF A TEST EXERCISING THE ROLE BY ITSELF CANNOT DISTINGUISH, and
        the two readings differ by six jobs. The widening is evaluated over the
        selection as a whole rather than per attributed role, which is what
        makes this row different from the one above.
        """
        graph = graph_of(ROOT)
        narrow = sorted(
            role
            for role in self.discovered
            if (independent_reverse_closure(graph, {role}) & self.discovered) < self.discovered
        )
        self.assertTrue(
            narrow,
            "no role in this tree has a closure smaller than the whole suite, so "
            "this assertion cannot distinguish the two readings it exists to "
            f"separate. The derived graph is {graph!r}",
        )
        companion = "swap" if "swap" in narrow else narrow[0]
        expected = independent_reverse_closure(graph, {companion}) & self.discovered
        self.assertEqual(
            expected,
            selected(
                [
                    f"ansible/roles/{self.UNVERIFIABLE}/defaults/main.yml",
                    f"ansible/roles/{companion}/tasks/main.yml",
                ],
                ROOT,
            ),
            f"a diff touching `{self.UNVERIFIABLE}` alongside `{companion}` widened "
            f"beyond `{companion}`'s own selection. Widening for an unverifiable role "
            "buys no coverage -- it is unverifiable whether or not the others run -- "
            "so the wider run is owed only where there would otherwise be nothing to "
            "run at all",
        )


class TestTheSelectorRefusesAnEmptySelection(unittest.TestCase):
    """SPECIFIED -- scenario "An empty selection on a run that owes the suite
    fails": "the run SHALL fail identifying the selection as the cause, and the
    matrix SHALL NOT be handed an empty list".

    Asserted against the selector rather than against the workflow, per
    tasks.md 1.7: the refusal lives where the selection is computed, and the
    workflow's only obligation is to propagate the non-zero exit -- asserted
    separately, below.
    """

    def test_a_tree_whose_roles_carry_no_scenarios_fails_rather_than_selecting_nothing(
        self,
    ) -> None:
        """SPECIFIED -- as above. This is the one reachable route to an empty
        selection: the widening cannot produce one where any role carries
        scenarios, which is precisely why an empty selection means the
        derivation is broken and the run must say so."""
        tree = Tree(self)
        tree.role_file("alpha", "tasks/main.yml", "---\n- name: Noop\n  ansible.builtin.debug:\n    msg: alpha\n")
        tree.role_file("beta", "tasks/main.yml", "---\n- name: Noop\n  ansible.builtin.debug:\n    msg: beta\n")
        refusal = symbol("EmptySelection")
        with self.assertRaises(refusal) as raised:
            symbol("select_roles")(["ansible/roles/alpha/tasks/main.yml"], tree.root)
        self.assertTrue(
            str(raised.exception).strip(),
            "the selector refused an empty selection with no message, so the run "
            "cannot name the selection as the cause",
        )

    def test_a_diff_carrying_no_path_at_all_does_not_resolve_to_nothing(self) -> None:
        """DERIVED (design.md Decision 3's third case, applied to the degenerate
        diff). No scenario states it, and the workflow does not produce it while
        the matrix is gated on whether the suite is owed. It is asserted because
        the two answers -- widen, or refuse -- are both defensible and SELECTING
        NOTHING SILENTLY is neither. Reconsider this assertion, do not weaken it,
        if the selector comes to refuse an empty file list instead."""
        selection = selected([], ROOT)
        self.assertEqual(
            roles_with_molecule_scenarios(),
            selection,
            "a selection over no changed path at all resolved to something other "
            "than every discovered role. An empty list reaching the matrix is the "
            "state the refusal above exists to stop; widening is the answer design.md "
            "Decision 3 gives for a selection whose restriction is empty",
        )


class TestTheSelectorEnumeratesRolesLikeTheRestOfTheSuite(unittest.TestCase):
    """SPECIFIED -- "The derivation and its closure SHALL be checked statically,
    by the checks that already read these scenario definitions, under the same
    enumeration of this repository's own roles -- so that installed Galaxy
    content cannot make the check report one result on a provisioned developer
    machine and another on a runner that has installed nothing"."""

    def test_the_selectors_enumeration_agrees_with_the_suites_own(self) -> None:
        """SPECIFIED -- as above. On a provisioned working tree
        `ansible/roles/geerlingguy.docker/` exists and carries its own
        scenarios; in continuous integration it does not. A selector enumerating
        by bare glob disagrees with this suite between the two, and a check
        disagreeing with itself is worse than no check."""
        self.assertEqual(
            roles_with_molecule_scenarios(),
            set(symbol("roles_with_scenarios")(ROOT)),
            "the selector's role enumeration disagrees with `role_names()`, which "
            "every other check in this suite uses. A Galaxy role installed beside "
            "this repository's own carries a dot in its directory name and ships its "
            "own scenarios; running them would verify somebody else's code",
        )

    def test_a_dotted_role_directory_carrying_scenarios_is_not_discovered(self) -> None:
        """SPECIFIED -- as above, shown on a fixture so that the assertion is
        not vacuous in continuous integration, where no Galaxy role is
        installed and the comparison above compares two sets that agree for want
        of the case that separates them."""
        tree = Tree(self)
        tree.scenario("ours", converge=converge_through_roles_list("- ours"))
        tree.scenario("vendor.theirs", converge=converge_through_roles_list("- vendor.theirs"))
        self.assertEqual(
            {"ours"},
            set(symbol("roles_with_scenarios")(tree.root)),
            "a dotted (Galaxy-namespaced) role directory carrying scenarios was "
            "discovered as one of this repository's own roles",
        )

    def test_no_selection_ever_carries_a_role_that_cannot_be_run(self) -> None:
        """SPECIFIED -- "a role in the closure that declares none SHALL be
        dropped after the closure is taken and before the matrix is fed", read
        over every path this file exercises rather than over one."""
        discovered = roles_with_molecule_scenarios()
        probes = [
            ["ansible/requirements.yml"],
            ["ansible/roles/tailscale/tasks/main.yml"],
            ["ansible/a-path-nobody-has-considered/file.yml"],
        ] + [[f"ansible/roles/{role}/tasks/main.yml"] for role in sorted(discovered)]
        for probe in probes:
            with self.subTest(changed=probe):
                self.assertEqual(
                    set(),
                    selected(probe, ROOT) - discovered,
                    "the selection carries a role with no `molecule/` directory, so "
                    "`run-molecule test --all` has nothing to find in it",
                )


# --------------------------------------------------------------------------
# The workflow: the selection it feeds the matrix, and the gate that reads it.
# --------------------------------------------------------------------------


class SelectionWorkflowMixin(MoleculeWorkflowShapeMixin):
    """Locators for the selection-shaped workflow, and a runner for a step body.

    A deliberate duplicate of the private locators inside
    `test_ci_configuration`'s `TestTheAggregatingGateDiscriminates` and
    `TestChangeDetectionResolvesTheGatesInput`, and not an import of them:
    importing a `TestCase` subclass into this module would make unittest's
    loader collect and RE-RUN every test those classes declare, under this
    module's name -- the reason the module beside this one gives for its own
    duplicate locator.

    It could not be a plain reuse in any case. Both of those locators resolve
    the gate's THIRD input as "whichever `env:` entry reads an output of the
    discovery job", and this change gives that job a second output. The locator
    below distinguishes them structurally instead: the run-suite output is the
    one the matrix job's `if:` reads, and the selection is the one its
    `strategy.matrix` reads. Nothing here edits those locators; that
    re-pointing is the implementing author's, and `test-plan.md` records it.
    """

    def _discovery_output_names(self, workflow: dict) -> tuple[str, str, str]:
        """(discovery job key, the run-suite output, the selection output)."""
        discovery_key, _ = self._discovery_job(workflow)
        matrix_key, matrix_job = self._matrix_job(workflow)

        pattern = re.compile(
            r"needs\." + re.escape(discovery_key) + r"\.outputs\.([A-Za-z0-9_-]+)"
        )
        matrix_expression = compact((matrix_job.get("strategy") or {}).get("matrix"))
        selection = sorted(set(pattern.findall(matrix_expression)))
        self.assertEqual(
            1,
            len(selection),
            f"the matrix job `{matrix_key}` builds its rows from {selection}; exactly "
            "one output of the discovery job supplies the roles to run, and it is "
            "that output this change calls the selection",
        )

        condition = compact(matrix_job.get("if"))
        gating = sorted(set(pattern.findall(condition)))
        self.assertEqual(
            1,
            len(gating),
            f"the matrix job `{matrix_key}`'s `if:` reads {gating} of the discovery "
            "job's outputs; exactly one decides whether the suite is owed. The job "
            "stays gated on whether the suite is owed rather than on the selection -- "
            "design.md Decision 5 records that keying it on the selection is what "
            "would make the two outputs able to disagree",
        )
        self.assertNotEqual(
            selection[0],
            gating[0],
            f"the matrix job's rows and its `if:` read the same output "
            f"`{selection[0]}`. Whether the suite is owed and which roles it owes are "
            "two computations, and one output cannot carry both",
        )
        return discovery_key, gating[0], selection[0]

    def _step_writing(self, job: dict, output_name: str):
        """The step whose `id:` the job's `outputs:` block reads for a name."""
        expression = compact((job.get("outputs") or {}).get(output_name))
        match = re.search(r"steps\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)", expression)
        self.assertTrue(
            match,
            f"the discovery job's `outputs:` block does not read a step output for "
            f"`{output_name}`; it declares {sorted((job.get('outputs') or {}))}",
        )
        step_id, key = match.groups()
        for index, step in enumerate(job.get("steps") or []):
            if step.get("id") == step_id:
                return index, step, key
        self.fail(
            f"the discovery job's output `{output_name}` reads `steps.{step_id}`, "
            f"which no step in that job declares as its `id:`"
        )

    def _run_body(self, step: dict, resolve, *, cwd: Path):
        """Execute a step's `run:` body under bash, with its `env:` resolved.

        `resolve` maps a declared variable's ACTIONS EXPRESSION to the value it
        should carry, so that a test names the inputs it is varying by what they
        read rather than by whatever the implementation called them.
        """
        script = str(step.get("run") or "")
        self.assertTrue(script.strip(), "the step declares an empty `run:` body")
        self.assertNotIn(
            "${{",
            script,
            "the step embeds a GitHub Actions expression in its body, so it cannot be "
            "run against the inputs it is responsible for and only its existence "
            "could be checked. Its inputs arrive through `env:` for that reason",
        )
        require_external_tools(self, ("bash",), "execute a step body of ansible-verify.yml")
        scratch = Path(tempfile.mkdtemp(prefix="matrix-selection-step-"))
        try:
            outputs = scratch / "github_output"
            summary = scratch / "step_summary"
            outputs.touch()
            summary.touch()
            env = dict(
                os.environ,
                GITHUB_OUTPUT=str(outputs),
                GITHUB_ENV=str(outputs),
                GITHUB_STEP_SUMMARY=str(summary),
            )
            for name, value in (step.get("env") or {}).items():
                env[str(name)] = resolve(compact(value))
            result = subprocess.run(
                ["bash", "-e", "-c", script],
                cwd=str(cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result, github_output_pairs(outputs)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


class TestTheMatrixIsFedTheSelection(SelectionWorkflowMixin, unittest.TestCase):
    """SPECIFIED -- "The Molecule suite SHALL run the roles a pull request's
    changed files owe, rather than every discovered role"."""

    def test_the_matrix_rows_come_from_the_step_that_runs_the_selector(self) -> None:
        """SPECIFIED -- as above. The matrix reading an output called something
        new establishes nothing on its own: what makes it the selection is that
        the step producing it runs the selector. A job renaming its existing
        discovery output satisfies every other shape assertion in this suite
        while feeding the matrix every discovered role."""
        workflow = self._workflow()
        _, _, selection_output = self._discovery_output_names(workflow)
        _, discovery_job = self._discovery_job(workflow)
        _, step, _ = self._step_writing(discovery_job, selection_output)
        body = str(step.get("run") or "")
        module_name = Path(getattr(selector(), "__file__", "")).name
        self.assertIn(
            module_name,
            body,
            f"the step producing the matrix's rows does not invoke `{module_name}`, "
            "so whatever it emits is not the selection this change computes. The step "
            f"runs: {body.strip()[:400]!r}",
        )

    def test_the_selector_lives_under_the_directory_the_suites_filter_reads(self) -> None:
        """SPECIFIED -- the delta's derivation obligations are over the checkout
        being tested; design.md Decision 6 is what makes editing the selector run
        the suite it selects for. DERIVED as to the directory: "A path under
        `ansible/` is a trigger under the existing filter, and an unattributable
        one under Decision 3 -- under `.github/` it would be neither"."""
        path = Path(getattr(selector(), "__file__", ""))
        self.assertEqual(
            SELECTOR_DIRECTORY,
            path.parent,
            f"the selector is at {path}, not under "
            f"{SELECTOR_DIRECTORY.relative_to(ROOT)}. A selector outside `ansible/` is "
            "not a trigger for the suite it selects for: editing it would change what "
            "every later pull request runs while running nothing itself",
        )

    def test_the_changed_file_list_comes_from_the_filter_that_already_runs(self) -> None:
        """DERIVED (design.md Decision 7 and tasks.md 3.1) -- no scenario names
        the mechanism. The delta says what a set of changed files owes; where
        that set comes from is decided in design.md, and it matters because the
        checkout is shallow and carries no base to diff against. Without
        `list-files: json` the filter reports only whether it matched, and the
        selector has nothing to attribute. Reconsider this assertion, do not
        weaken it, if the diff is resolved by another means."""
        workflow = self._workflow()
        _, discovery_job = self._discovery_job(workflow)
        filters = [
            step
            for step in (discovery_job.get("steps") or [])
            if "paths-filter" in str(step.get("uses", ""))
        ]
        self.assertEqual(
            1,
            len(filters),
            "expected exactly one change-filter step in the discovery job, the one "
            f"already resolving the pull request's diff, but found {len(filters)}. A "
            "second mechanism is a second answer to which files changed",
        )
        self.assertEqual(
            "json",
            str((filters[0].get("with") or {}).get("list-files", "")).strip(),
            "the change filter does not declare `list-files: json`, so it reports "
            "whether it matched and not WHAT it matched. The selector then has no "
            "changed paths to attribute, and the only answer left to it is the whole "
            f"suite. The step declares {sorted((filters[0].get('with') or {}))}",
        )

    def test_the_step_that_runs_the_selector_does_not_swallow_its_exit_status(self) -> None:
        """SPECIFIED -- scenario "An empty selection on a run that owes the suite
        fails": "the run SHALL fail". The refusal lives in the selector; the
        workflow's obligation is to let it out, and a step swallowing it turns
        the refusal into a selection nobody made."""
        workflow = self._workflow()
        _, _, selection_output = self._discovery_output_names(workflow)
        _, discovery_job = self._discovery_job(workflow)
        index, step, _ = self._step_writing(discovery_job, selection_output)
        self.assertNotEqual(
            True,
            step.get("continue-on-error"),
            f"the selection step (index {index}) declares `continue-on-error`, so a "
            "refused selection concludes success and the matrix is handed whatever "
            "the step managed to write",
        )
        body = str(step.get("run") or "")
        module_name = Path(getattr(selector(), "__file__", "")).name
        swallowing = [
            line.strip()
            for line in body.splitlines()
            if module_name in line and re.search(r"\|\||\|\s*true|set\s+\+e", line)
        ]
        self.assertEqual(
            [],
            swallowing,
            f"these lines invoke the selector and discard its exit status: {swallowing}. "
            "A non-zero exit is the whole of the workflow's share in the empty-selection "
            "refusal",
        )
        self.assertTrue(
            re.search(r"^\s*set\s+-[a-z]*e", body, re.MULTILINE),
            "the selection step's body does not `set -e`, so a failing selector leaves "
            f"the step to conclude on its last command instead. The step runs: {body.strip()[:400]!r}",
        )


class TestDiscoverysVacuityRefusalReadsTheUnfilteredTree(
    SelectionWorkflowMixin, unittest.TestCase
):
    """SPECIFIED -- scenario "Discovery still refuses a tree carrying no
    scenarios": "discovery SHALL fail as it does today, reading the tree rather
    than the selection -- a suite that has disappeared SHALL NOT be reportable as
    a correct skip".

    `test_ci_configuration.TestMoleculeDiscoveryAndScenarioCoverage
    .test_role_discovery_fails_when_it_finds_nothing` already establishes that
    discovery refuses an empty tree. What is new here, and what a naive
    implementation loses by moving the refusal behind the selection, is that it
    refuses WHATEVER THE DIFF SAID. Nothing here edits that test.
    """

    def _discovery_steps(self, discovery_job: dict):
        # Tolerant of an absent selector on purpose: this refusal is about the
        # tree rather than about the selection, so the assertion below must be
        # exercisable -- and must discriminate -- before the selector exists as
        # well as after it. Where the selector is there, a step invoking it is
        # not the vacuity refusal and is excluded.
        try:
            module_name = Path(getattr(selector(), "__file__", "")).name
        except AssertionError:
            module_name = None
        candidates = [
            (index, step)
            for index, step in enumerate(discovery_job.get("steps") or [])
            if step.get("run") and re.search(r"ansible/roles", str(step["run"]))
        ]
        self.assertTrue(
            candidates,
            "no step in the discovery job reads `ansible/roles`, so nothing in it can "
            "be refusing a tree that carries no scenario",
        )
        if module_name is None:
            return candidates
        without_selector = [
            (index, step) for index, step in candidates if module_name not in str(step["run"])
        ]
        return without_selector or candidates

    def test_discovery_refuses_a_tree_with_no_scenarios_whatever_the_diff_said(self) -> None:
        """SPECIFIED -- as above. The step is run against a scratch tree holding
        a role directory with no `molecule/` in it, with every input it declares
        set to a value meaning "this diff owes nothing" -- which is the reading
        a refusal moved behind the selection would take as permission to skip."""
        workflow = self._workflow()
        _, discovery_job = self._discovery_job(workflow)
        scratch = Path(tempfile.mkdtemp(prefix="matrix-selection-vacuity-"))
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        (scratch / "ansible" / "roles" / "alpha" / "tasks").mkdir(parents=True)
        (scratch / "ansible" / "roles" / "alpha" / "tasks" / "main.yml").write_text(
            "---\n- name: Noop\n  ansible.builtin.debug:\n    msg: alpha\n", encoding="utf-8"
        )
        for empty_diff in ("[]", '["docs/change-queue.md"]', "false", ""):
            for index, step in self._discovery_steps(discovery_job):
                with self.subTest(step=index, diff=empty_diff):
                    result, _ = self._run_body(
                        step,
                        lambda expression, value=empty_diff: (
                            "pull_request" if "github.event_name" in expression else value
                        ),
                        cwd=scratch,
                    )
                    self.assertNotEqual(
                        0,
                        result.returncode,
                        "discovery exited 0 against a tree carrying no scenario at all, "
                        f"with its inputs reading {empty_diff!r}. The vacuity refusal is a "
                        "fact about the repository rather than about the diff: moving it "
                        "behind the selection turns a vanished suite into a correct skip, "
                        "and the pull request that removed the suite is not the only one "
                        f"that should stop. It emitted "
                        f"{(result.stdout + result.stderr).strip()[-500:]!r}",
                    )


    def test_discovery_accepts_a_tree_that_does_carry_a_scenario(self) -> None:
        """DERIVED (this library's testing floor). The control the refusal above
        needs: a discovery step that refused every tree would satisfy it while
        failing every pull request in the repository, and the refusal assertion
        alone cannot tell the two apart."""
        workflow = self._workflow()
        _, discovery_job = self._discovery_job(workflow)
        scratch = Path(tempfile.mkdtemp(prefix="matrix-selection-populated-"))
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        scenario = scratch / "ansible" / "roles" / "alpha" / "molecule" / "default"
        scenario.mkdir(parents=True)
        (scenario / "molecule.yml").write_text(scenario_definition("alpha"), encoding="utf-8")
        for index, step in self._discovery_steps(discovery_job):
            with self.subTest(step=index):
                result, written = self._run_body(
                    step,
                    lambda expression: (
                        "pull_request" if "github.event_name" in expression else "true"
                    ),
                    cwd=scratch,
                )
                self.assertEqual(
                    0,
                    result.returncode,
                    "discovery refused a tree carrying a role with a scenario in it: "
                    f"{(result.stdout + result.stderr).strip()[-500:]!r}",
                )
                self.assertTrue(
                    any("alpha" in value for value in written.values()),
                    f"discovery wrote no output naming the role it found: {written!r}",
                )


class TestARunCarryingNoDiffSelectsEveryRole(SelectionWorkflowMixin, unittest.TestCase):
    """SPECIFIED -- scenario "A run carrying no diff runs every role": "the
    selection SHALL be every discovered role, resolved by the same branch that
    resolves the suite as owed on such an event".

    Easy to leave out precisely because the existing branch looks as though it
    already covers it (tasks.md 1.8a): what is new is that the same branch must
    now force the SELECTION as well as `run-suite`. The step is run in the real
    repository, so "every discovered role" has a value to be compared against.
    """

    def _resolve_for_dispatch(self, event: str):
        def resolve(expression: str) -> str:
            if "github.event_name" in expression:
                return event
            if "steps." in expression and "outputs." in expression:
                # Every step output this step could read is either the change
                # filter's, which did not run on an event carrying no diff, or
                # the discovered roles. An unrun step leaves the empty string,
                # which is exactly the value the branch must not read as
                # "nothing changed"; the discovered roles are supplied as they
                # would be in the real job.
                if re.search(r"outputs\.(roles|discovered)", expression):
                    return json.dumps(sorted(roles_with_molecule_scenarios()))
                return ""
            return ""

        return resolve

    def test_the_selection_written_on_an_event_with_no_diff_is_every_discovered_role(
        self,
    ) -> None:
        """SPECIFIED -- as above, and "by the same branch that already resolves
        the suite as owed on such an event, so that the two cannot come to
        disagree"."""
        workflow = self._workflow()
        _, _, selection_output = self._discovery_output_names(workflow)
        _, discovery_job = self._discovery_job(workflow)
        _, step, key = self._step_writing(discovery_job, selection_output)
        discovered = sorted(roles_with_molecule_scenarios())
        self.assertTrue(discovered, "no role under ansible/roles/ carries scenarios")
        for event in ("workflow_dispatch", "push", "schedule"):
            with self.subTest(event=event):
                result, written = self._run_body(
                    step, self._resolve_for_dispatch(event), cwd=ROOT
                )
                self.assertEqual(
                    0,
                    result.returncode,
                    f"the step producing the selection exited {result.returncode} on a "
                    f"`{event}` run, which carries no diff to attribute: "
                    f"{(result.stdout + result.stderr).strip()[-600:]!r}",
                )
                self.assertIn(
                    key,
                    written,
                    f"the step wrote no `{key}` to $GITHUB_OUTPUT on a `{event}` run; it "
                    f"wrote {written!r}",
                )
                emitted = written[key].strip()
                try:
                    parsed = sorted(json.loads(emitted))
                except json.JSONDecodeError:
                    self.fail(
                        f"the selection written on a `{event}` run is not JSON the matrix "
                        f"can consume with `fromJSON`: {emitted!r}"
                    )
                self.assertEqual(
                    discovered,
                    parsed,
                    f"on a `{event}` run -- an event carrying no diff -- the selection is "
                    "not every discovered role. The branch that forces the suite owed on "
                    "such an event is the one that must force this, so that the two "
                    "cannot drift",
                )

    def test_the_same_step_or_job_resolves_the_suite_as_owed_on_such_an_event(self) -> None:
        """SPECIFIED -- "resolved by the same branch that already resolves the
        suite as owed on such an event, so that the two cannot come to
        disagree". Where one step writes both outputs, this runs it once and
        reads both; where they are two steps, it runs each and asserts they
        agree on the event."""
        workflow = self._workflow()
        _, run_suite_output, _ = self._discovery_output_names(workflow)
        _, discovery_job = self._discovery_job(workflow)
        _, gate_step, gate_key = self._step_writing(discovery_job, run_suite_output)
        for event in ("workflow_dispatch", "push"):
            with self.subTest(event=event):
                _, written = self._run_body(gate_step, self._resolve_for_dispatch(event), cwd=ROOT)
                self.assertEqual(
                    "true",
                    written.get(gate_key, "").strip(),
                    f"on a `{event}` run the suite is not resolved as owed, so the "
                    "selection asserted above would be computed for a run that then "
                    "skips the matrix",
                )
        with self.subTest(event="pull_request"):
            # The control. A branch resolving `true` unconditionally satisfies
            # every assertion above while making the whole suite run on every
            # pull request in the repository, and only a row it must answer
            # differently separates the two.
            _, written = self._run_body(
                gate_step,
                lambda expression: (
                    "pull_request" if "github.event_name" in expression else "false"
                ),
                cwd=ROOT,
            )
            self.assertEqual(
                "false",
                written.get(gate_key, "").strip(),
                "on a pull request whose change filter reported `false` the suite is "
                "still resolved as owed, so the branch asserted above is not reading "
                "the event at all",
            )


class SelectionGateRow:
    """One row of the aggregating gate's decision table, as design.md Decision 5
    states it: four inputs now rather than three."""

    def __init__(self, label, discovery, run_suite, selection, matrix_results, concludes_success):
        self.label = label
        self.discovery = discovery
        self.run_suite = run_suite
        self.selection = selection
        self.matrix_results = matrix_results
        self.concludes_success = concludes_success


NARROWED = '["docker","deploy_user"]'
EVERYTHING = '["deploy_user","docker","hardening","image_prune","ops_user","platform_data_volume","swap"]'

# design.md Decision 5's table. THE EXISTING THREE ROWS ARE RE-ASSERTED RATHER
# THAN ASSUMED (tasks.md 1.8): this change edits that script, and a test
# covering only the new rows would not notice the old ones breaking.
#
# The row `success / success / suite not owed` REVERSES a row already asserted
# on the trunk, where it concludes success. That is not a disagreement between
# two checks: it is this delta superseding that expectation, and `test-plan.md`
# records the superseded test rather than editing it here.
SELECTION_GATE_TABLE = (
    SelectionGateRow(
        "discovery did not conclude, so its outputs are empty strings",
        discovery="failure",
        run_suite="",
        selection="",
        matrix_results=("skipped",),
        concludes_success=False,
    ),
    SelectionGateRow(
        "the suite ran and passed on the narrowed subset it owed",
        discovery="success",
        run_suite="true",
        selection=NARROWED,
        matrix_results=("success",),
        concludes_success=True,
    ),
    SelectionGateRow(
        "the suite ran and passed on every role",
        discovery="success",
        run_suite="true",
        selection=EVERYTHING,
        matrix_results=("success",),
        concludes_success=True,
    ),
    SelectionGateRow(
        "the suite was skipped on a run that owed it",
        discovery="success",
        run_suite="true",
        selection=NARROWED,
        matrix_results=("skipped",),
        concludes_success=False,
    ),
    SelectionGateRow(
        "the suite failed or was cancelled on a run that owed it",
        discovery="success",
        run_suite="true",
        selection=NARROWED,
        matrix_results=("failure", "cancelled"),
        concludes_success=False,
    ),
    SelectionGateRow(
        "nothing the suite reads changed and the matrix was skipped",
        discovery="success",
        run_suite="false",
        selection="[]",
        matrix_results=("skipped",),
        concludes_success=True,
    ),
    SelectionGateRow(
        "the matrix ran although the run owed the suite nothing",
        discovery="success",
        run_suite="false",
        selection="[]",
        matrix_results=("success",),
        concludes_success=False,
    ),
    SelectionGateRow(
        "the matrix failed or was cancelled although the run owed the suite nothing",
        discovery="success",
        run_suite="false",
        selection="[]",
        matrix_results=("failure", "cancelled"),
        concludes_success=False,
    ),
)

NARROWED_SUCCESS = next(
    row for row in SELECTION_GATE_TABLE if row.selection == NARROWED and row.concludes_success
)
RAN_WHILE_OWING_NOTHING = next(
    row
    for row in SELECTION_GATE_TABLE
    if row.run_suite == "false" and row.matrix_results == ("success",)
)


class TestTheAggregatingGateReadsTheSelection(SelectionWorkflowMixin, unittest.TestCase):
    """SPECIFIED -- scenarios "The aggregating job names the subset it ran" and
    "A matrix that ran where nothing was owed fails", and "Its existing refusals
    SHALL be unchanged".

    Runs the gate rather than reading it, in the shape `test_ci_configuration`
    established: the body is free of `${{ }}` and takes its inputs through
    `env:`, so it can be pulled out and executed once per row. Grepping would
    establish that a gate exists; only running it establishes that it
    discriminates.
    """

    def _gate_step(self):
        workflow = self._workflow()
        discovery_key, run_suite_output, selection_output = self._discovery_output_names(workflow)
        matrix_key, _ = self._matrix_job(workflow)
        _, aggregating = self._job_named(workflow, AGGREGATING_CONTEXT)

        candidates = []
        for index, step in enumerate(aggregating.get("steps") or []):
            if not step.get("run"):
                continue
            inputs: dict[str, str] = {}
            for name, value in (step.get("env") or {}).items():
                expression = compact(value)
                if f"needs.{discovery_key}.result" in expression:
                    inputs["discovery"] = name
                elif f"needs.{matrix_key}.result" in expression:
                    inputs["matrix"] = name
                elif f"needs.{discovery_key}.outputs.{run_suite_output}" in expression:
                    inputs["run_suite"] = name
                elif f"needs.{discovery_key}.outputs.{selection_output}" in expression:
                    inputs["selection"] = name
            if set(inputs) == {"discovery", "matrix", "run_suite", "selection"}:
                candidates.append((index, step, inputs))

        self.assertEqual(
            1,
            len(candidates),
            f"expected exactly one `run:` step in the `{AGGREGATING_CONTEXT}` job whose "
            "`env:` block carries all FOUR of the discovery result, the matrix result, "
            f"the run-suite output `{run_suite_output}` and the selection output "
            f"`{selection_output}`, but found {len(candidates)}. The gate gains one "
            "input under this change; a gate reading three cannot distinguish a "
            "narrowed run from a full one, and cannot refuse a matrix that ran where "
            "nothing was owed. The job's steps declare: "
            + repr(
                [
                    (step.get("name"), sorted(step.get("env") or {}))
                    for step in (aggregating.get("steps") or [])
                ]
            ),
        )
        return candidates[0]

    def _run_gate(self, row: SelectionGateRow, matrix_result: str):
        _, step, inputs = self._gate_step()

        def resolve(expression: str) -> str:
            for role, value in (
                ("discovery", row.discovery),
                ("matrix", matrix_result),
                ("run_suite", row.run_suite),
                ("selection", row.selection),
            ):
                name = inputs[role]
                if compact((step.get("env") or {}).get(name)) == expression:
                    return value
            return ""

        return self._run_body(step, resolve, cwd=ROOT)

    def test_the_gate_concludes_as_the_table_says_on_every_row(self) -> None:
        """SPECIFIED -- the four existing refusals, unchanged ("Its existing
        refusals SHALL be unchanged: a discovery that did not succeed, and a skip
        on a run that asked for the suite, SHALL each still fail"), plus the row
        the delta adds ("It SHALL additionally fail where the matrix ran on a run
        that owed the suite nothing").

        The passing rows are the converse the refusals need: a gate failing every
        row satisfies each refusal while blocking every pull request in the
        repository.
        """
        for row in SELECTION_GATE_TABLE:
            for matrix_result in row.matrix_results:
                with self.subTest(row=row.label, matrix=matrix_result):
                    result, _ = self._run_gate(row, matrix_result)
                    detail = (result.stdout + result.stderr).strip()[-800:]
                    if row.concludes_success:
                        self.assertEqual(
                            0,
                            result.returncode,
                            f"the gate refused the row `{row.label}` (discovery="
                            f"{row.discovery!r}, run-suite={row.run_suite!r}, selection="
                            f"{row.selection!r}, matrix={matrix_result!r}), which the "
                            f"specification requires it to pass: {detail!r}",
                        )
                    else:
                        self.assertNotEqual(
                            0,
                            result.returncode,
                            f"the gate concluded success on the row `{row.label}` "
                            f"(discovery={row.discovery!r}, run-suite={row.run_suite!r}, "
                            f"selection={row.selection!r}, matrix={matrix_result!r}), "
                            "reporting a green required status check for a run whose "
                            f"coverage nobody established: {detail!r}",
                        )

    def test_the_gate_names_the_subset_it_ran(self) -> None:
        """SPECIFIED -- scenario "The aggregating job names the subset it ran":
        "the aggregating job SHALL conclude success and SHALL state which roles
        ran and why that subset, so that a wrongly narrow run is legible to a
        reader of the check".

        The conclusion is asserted first. Without that, this reads a message and
        never checks what the gate concluded, so it would pass on a gate that
        named the subset and then refused it.
        """
        result, _ = self._run_gate(NARROWED_SUCCESS, "success")
        combined = result.stdout + result.stderr
        self.assertEqual(
            0,
            result.returncode,
            "the gate refused a narrowed run that passed, so this message assertion "
            f"would be describing a refusal: {combined.strip()[-800:]!r}",
        )
        for role in json.loads(NARROWED_SUCCESS.selection):
            self.assertIn(
                role,
                combined,
                f"the gate concluded success on a narrowed run without naming `{role}` "
                "among the roles that ran. A human reading the check is the only reader "
                "that can catch a graph defect the static check did not model, and "
                f"`molecule (docker)` on its own tells them nothing. It emitted {combined.strip()[-800:]!r}",
            )

    def test_the_gate_refuses_a_matrix_that_ran_where_nothing_was_owed(self) -> None:
        """SPECIFIED -- scenario "A matrix that ran where nothing was owed
        fails": "the aggregating job SHALL fail rather than conclude success --
        the two outputs disagreeing means the selection and the decision to run
        were computed from different things".

        design.md Decision 5 records this row as UNREACHABLE under the shape
        this change ships, and the refusal as owed anyway: it is defence against
        a later edit keying the matrix job's condition on the selection. A test
        for an unreachable row is the only thing that keeps it true.
        """
        result, _ = self._run_gate(RAN_WHILE_OWING_NOTHING, "success")
        combined = (result.stdout + result.stderr).strip()
        self.assertNotEqual(
            0,
            result.returncode,
            "the gate concluded success where the matrix ran on a run that owed the "
            f"suite nothing: {combined[-800:]!r}",
        )


if __name__ == "__main__":
    unittest.main()
