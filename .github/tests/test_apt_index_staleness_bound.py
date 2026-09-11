"""Static-assertion tests for bounding how often a converge re-fetches the apt
package index.

Derived from the delta specification of the OpenSpec change
`cache-the-apt-index-within-a-converge`, before any implementation of that
change existed. The path those deltas sit at is not written here: a change's
artifacts move when it is archived, and this repository's citation convention is
to name the change and the artifact in prose instead.

The delta ADDS one requirement to `iac-host-configuration` -- *A Converge Bounds
How Often It Re-Fetches the Package Index* -- carrying seven scenarios. Four of
them are static reads of committed files and are established here; the other
three are role behaviour on a host and are established in
`ansible/roles/hardening/molecule/default/`, which is the only mechanism that
can observe them. See that change's `test-plan.md` for the scenario-to-test
mapping, the baseline, the scenarios deliberately left uncovered, the
obsolete-test candidates, and the interface assumptions taken.

Every assertion below is annotated SPECIFIED (it traces to the requirement's
SHALL text or to one of its scenarios) or DERIVED (it traces to that change's
`design.md` or `tasks.md`, or to a scoping judgment this test author made).

Why this is a tenth file in the suite rather than a section of an existing one
-----------------------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. Nothing in this file edits, deletes or disables an
existing test. Where it needs a helper a module beside it already has -- the
repository root, the YAML loader, and above all the role enumeration -- it
imports it rather than restating it, which is the idiom the nine modules already
in this directory use.

Why the role enumeration is imported rather than globbed
--------------------------------------------------------
`ansible/roles/geerlingguy.docker/` is GITIGNORED. A bare glob over
`ansible/roles/*/tasks/` or `ansible/roles/*/molecule/*/` therefore sees it in a
provisioned working tree and not in continuous integration, and that role's own
scenario carries a literal `cache_valid_time` -- so a check drawn that way would
disagree with itself between the two, which is worse than no check at all.
`role_names()` excludes a dotted directory name and `galaxy_role_directories()`
derives the installed set from `ansible/requirements.yml`, which is committed
content; subtracting the second from the first is the enumeration this file
uses everywhere.

What no assertion here establishes
----------------------------------
Not that a bounded task actually skips a fetch, and not that an unbounded one
performs one. `ansible.builtin.apt` returns `cache_updated` independently of
`changed`, and that return is the only place the distinction exists -- a fetched
index and an unfetched one leave exactly the same packages installed. Reading it
needs a converge, which is the Molecule row of this project's test table and not
this suite's. This file reads what a committed file SAYS.

Not the VALUE of the bound either. The delta makes no normative claim about how
many seconds is right, so nothing here guards the default an hour or any other
figure; what is asserted is that the bound is declared, that it is declared as a
variable, and that the two cases which must never declare one do not.

Not the same-run-source rule beyond ONE FILE. The check below reports an apt
task as installing from a source the same run added when an EARLIER TASK IN THE
SAME TASK FILE writes a destination under `/etc/apt/sources.list.d/`. A source
written by another file of the same role, by another role in the same play, or
by a playbook outside `ansible/roles/` is outside its reach. That bound is
recorded rather than assumed, and it is a real gap: an install whose source is
added by a preceding role would be reported as qualifying and required to carry
a bound it must not carry.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_apt_index_staleness_bound.TestTheBoundIsDeclaredWhereItIsOwed \\
        .test_every_qualifying_own_role_apt_task_declares_a_bound

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling import below resolve.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

from test_ci_configuration import (
    ROOT,
    galaxy_role_directories,
    role_names,
)

# --------------------------------------------------------------------------
# What the reads below are keyed on
# --------------------------------------------------------------------------

#: The module the requirement is about, in both the short and the fully
#: qualified spelling. `ansible.builtin.package` is deliberately NOT here: it is
#: a generic dispatcher with no `cache_valid_time` option, so a bound cannot be
#: declared on it at all, and a check demanding one would be unsatisfiable.
APT_MODULES = frozenset({"apt", "ansible.builtin.apt"})

#: The option `ansible.builtin.apt` takes for the staleness bound. The delta
#: names no option; it names an obligation ("SHALL declare how stale a package
#: index it is willing to install from"), and this is the only expression the
#: module has for it.
BOUND_OPTION = "cache_valid_time"

#: Keyed on the DESTINATION and not on the module. This repository's only
#: instance of an install from a same-run source writes that source with
#: `ansible.builtin.get_url`, so a check looking for `apt_repository` would
#: match nothing and pass vacuously -- a green check establishing nothing.
APT_SOURCE_DIRECTORY = "/etc/apt/sources.list.d/"

#: The keys a module argument mapping uses for "the file this writes".
DESTINATION_OPTIONS = ("dest", "path")

#: Options through which `ansible.builtin.apt` names what to install.
PACKAGE_OPTIONS = ("name", "pkg", "package", "deb")

#: Task keywords holding nested task lists. A task inside a block installs a
#: package exactly as one outside it does.
BLOCK_KEYWORDS = ("block", "rescue", "always")

#: Play keywords holding task lists. A Molecule play is a PLAYBOOK -- a list of
#: plays, each holding its tasks under one of these -- while a role's task file
#: is a bare list of tasks. One walker reads both, so the fixture-play exemption
#: and the task-file obligation cannot drift apart in how they find a task.
PLAY_KEYWORDS = ("tasks", "pre_tasks", "post_tasks", "handlers")

#: A bound expressed as a reference to exactly one variable, optionally with a
#: filter chain -- `{{ hardening_apt_cache_valid_time }}` or
#: `{{ hardening_apt_cache_valid_time | int }}`.
VARIABLE_REFERENCE = re.compile(
    r"^\s*\{\{\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\|[^}]*)?\}\}\s*$"
)


class AnsibleContentUnusable(AssertionError):
    """Raised where the committed Ansible content cannot be read at all.

    An AssertionError rather than a skip: a check that does not run reports
    success for a property nothing examined, which is the habit this repository
    refuses everywhere else.
    """


# --------------------------------------------------------------------------
# Enumeration
# --------------------------------------------------------------------------


def own_role_names() -> set[str]:
    """This repository's own roles: every role directory, less the Galaxy-installed
    ones derived from the pinned manifest."""
    return role_names() - galaxy_role_directories()


def own_role_task_files() -> list[Path]:
    """Every committed task file of this repository's own roles.

    `ansible/roles/<role>/tasks/**/*.yml`, sorted. `molecule/` is not reached
    from here by construction, which is half of what keeps the fixture plays
    outside the obligation.
    """
    found: list[Path] = []
    for role in sorted(own_role_names()):
        tasks = ROOT / "ansible" / "roles" / role / "tasks"
        if not tasks.is_dir():
            continue
        for path in sorted(tasks.rglob("*")):
            if path.is_file() and path.suffix in (".yml", ".yaml"):
                found.append(path)
    return found


def own_role_fixture_plays() -> list[Path]:
    """Every committed Molecule play of this repository's own roles.

    `ansible/roles/<role>/molecule/<scenario>/*.yml`, sorted. These are the
    plays the requirement's last scenario holds outside itself.
    """
    found: list[Path] = []
    for role in sorted(own_role_names()):
        molecule = ROOT / "ansible" / "roles" / role / "molecule"
        if not molecule.is_dir():
            continue
        for path in sorted(molecule.rglob("*")):
            if path.is_file() and path.suffix in (".yml", ".yaml"):
                found.append(path)
    return found


def _load(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise AnsibleContentUnusable(
            f"{path.relative_to(ROOT).as_posix()} could not be read as YAML, so the "
            f"apt tasks it holds were examined by nothing: {error}"
        ) from None


def flattened_tasks(document) -> list[dict]:
    """Every task in a task file, in document order, walking into blocks.

    A `block:`/`rescue:`/`always:` is flattened in place rather than skipped: a
    task inside one installs a package exactly as a task outside one does, and a
    walker that stopped at the block would report it as absent rather than as
    unbounded.

    Ordering matters to one check only -- "an earlier task in the same file
    writes an apt source" -- and flattening makes that ordering the document's,
    which is the same order a reader sees.

    A play mapping is appended alongside its tasks rather than skipped, which
    costs nothing: a play declares no module, so it is never taken for an apt
    task.

    NOT FOLLOWED, and recorded rather than discovered: `include_tasks` and
    `import_tasks`. A task file reached only through one is read on its own when
    the enumeration reaches it, so it is not missed -- but "an earlier task in
    the same file" does not reach across the include, which the module docstring
    already states as this check's bound.
    """
    tasks: list[dict] = []
    if not isinstance(document, list):
        return tasks
    for entry in document:
        if not isinstance(entry, dict):
            continue
        tasks.append(entry)
        for keyword in BLOCK_KEYWORDS + PLAY_KEYWORDS:
            nested = entry.get(keyword)
            if isinstance(nested, list):
                tasks.extend(flattened_tasks(nested))
    return tasks


def module_arguments(task: dict, module_names) -> dict | None:
    """The argument mapping a task passes to one of `module_names`, or None."""
    for key, value in task.items():
        if key in module_names:
            return value if isinstance(value, dict) else {}
    return None


def writes_an_apt_source(task: dict) -> bool:
    """Whether a task writes a file under `/etc/apt/sources.list.d/`.

    Reads every mapping value of the task rather than a named module's, because
    the module is not what this is keyed on -- see APT_SOURCE_DIRECTORY.
    """
    for value in task.values():
        if not isinstance(value, dict):
            continue
        for option in DESTINATION_OPTIONS:
            destination = value.get(option)
            if isinstance(destination, str) and destination.startswith(APT_SOURCE_DIRECTORY):
                return True
    return False


def _named_packages(arguments: dict) -> list[str]:
    named: list[str] = []
    for option in PACKAGE_OPTIONS:
        value = arguments.get(option)
        if isinstance(value, str):
            named.append(value)
        elif isinstance(value, list):
            named.extend(entry for entry in value if isinstance(entry, str))
    return named


class AptTask:
    """One `ansible.builtin.apt` task of one committed file, with the four
    properties the requirement's predicates turn on."""

    def __init__(self, path: Path, position: int, task: dict, arguments: dict, after_a_source: bool):
        self.path = path
        self.position = position
        self.name = task.get("name") or "<unnamed task>"
        self.arguments = arguments
        self.installs_from_a_same_run_source = after_a_source

    @property
    def where(self) -> str:
        return f"{self.path.relative_to(ROOT).as_posix()}: {self.name!r}"

    @property
    def installs_a_package(self) -> bool:
        return bool(_named_packages(self.arguments))

    @property
    def pins_a_version(self) -> bool:
        """`apt`'s own version-pin syntax, `name=version`.

        A `deb:` install counts as pinned too: it names an exact artifact, so an
        index older than it resolves to nothing for the same reason a named
        version does.
        """
        if isinstance(self.arguments.get("deb"), str):
            return True
        return any("=" in package for package in _named_packages(self.arguments))

    @property
    def declares_a_bound(self) -> bool:
        return BOUND_OPTION in self.arguments

    @property
    def declared_bound(self):
        return self.arguments.get(BOUND_OPTION)

    @property
    def is_qualifying(self) -> bool:
        """The requirement's own antecedent: a task in this repository's own
        roles that installs a package at no pinned version, from a source the
        same run did not add or change."""
        return (
            self.installs_a_package
            and not self.pins_a_version
            and not self.installs_from_a_same_run_source
        )


def apt_tasks(paths) -> list[AptTask]:
    """Every apt task of the supplied files, each carrying whether an earlier
    task in its own file wrote an apt source."""
    collected: list[AptTask] = []
    for path in paths:
        tasks = flattened_tasks(_load(path))
        source_written = False
        for position, task in enumerate(tasks):
            arguments = module_arguments(task, APT_MODULES)
            if arguments is not None:
                collected.append(AptTask(path, position, task, arguments, source_written))
            if writes_an_apt_source(task):
                source_written = True
    return collected


def role_of(path: Path) -> str:
    return path.relative_to(ROOT / "ansible" / "roles").parts[0]


def role_default_names(role: str) -> set[str]:
    defaults = ROOT / "ansible" / "roles" / role / "defaults" / "main.yml"
    if not defaults.is_file():
        return set()
    parsed = _load(defaults)
    return set(parsed) if isinstance(parsed, dict) else set()


# --------------------------------------------------------------------------
# iac-host-configuration / A Converge Bounds How Often It Re-Fetches the
# Package Index
# --------------------------------------------------------------------------


class TestTheBoundIsDeclaredWhereItIsOwed(unittest.TestCase):
    """ADDED requirement: A Converge Bounds How Often It Re-Fetches the Package
    Index.

    The positive obligation and the two refusals, over the task files of this
    repository's own roles.
    """

    def setUp(self) -> None:
        self.files = own_role_task_files()
        self.assertTrue(
            self.files,
            "no task file was found under ansible/roles/*/tasks/ for any of this "
            f"repository's own roles ({sorted(own_role_names())}), so every "
            "assertion in this class would pass having read nothing",
        )
        self.tasks = apt_tasks(self.files)
        self.assertTrue(
            self.tasks,
            f"none of the {len(self.files)} committed task files declares an "
            "ansible.builtin.apt task, so every assertion in this class would pass "
            "having read nothing. Either the roles stopped using apt -- in which "
            "case this requirement has no subject and should be revisited -- or the "
            "walker above stopped recognising the tasks it is meant to read",
        )

    def test_every_qualifying_own_role_apt_task_declares_a_bound(self) -> None:
        """SPECIFIED -- the requirement's own SHALL: "A task in this repository's
        own roles that installs a package at no pinned version, from a source the
        same run did not add or change, SHALL declare how stale a package index
        it is willing to install from, rather than re-fetching the index
        unconditionally on every such task."

        This is the direction nothing else covers. Without it the requirement
        regresses silently in the one direction the change exists to establish,
        and `image_prune`'s single bound -- which no Molecule scenario of this
        change asserts on -- is asserted by nothing at all.

        DERIVED, and recorded because it is a scoping judgment rather than the
        delta's words: the antecedent is read as reaching every qualifying apt
        task that INSTALLS A PACKAGE, whether or not it also declares
        `update_cache`. The narrower reading -- only tasks that today re-fetch
        unconditionally -- would be satisfiable by DELETING `update_cache`
        instead of bounding it, which is a regression that passes. Today the two
        readings select the same tasks: every apt task in this repository's own
        roles declares `update_cache`.
        """
        unbounded = [task.where for task in self.tasks if task.is_qualifying and not task.declares_a_bound]
        qualifying = [task for task in self.tasks if task.is_qualifying]
        self.assertTrue(
            qualifying,
            "no apt task in this repository's own roles qualifies -- every one of "
            f"the {len(self.tasks)} found either pins a version or installs from a "
            "source written earlier in its own file. The positive obligation would "
            "then be vacuous, which it was not when this was written",
        )
        self.assertEqual(
            [],
            unbounded,
            f"these apt tasks install an unpinned package from a source their own "
            f"file did not add, and declare no `{BOUND_OPTION}`, so each re-fetches "
            f"the whole package index every time it runs: {unbounded}. Several such "
            "tasks in one converge each download the same index minutes apart, and "
            "every one after the first re-establishes what the run already knows",
        )

    def test_a_pinned_version_apt_task_declares_no_bound(self) -> None:
        """SPECIFIED -- scenario "A pinned-version install declares no bound":
        an index predating that version resolves to no candidate rather than to
        an older one, so the install fails outright.
        """
        pinned = [task for task in self.tasks if task.pins_a_version]
        self.assertTrue(
            pinned,
            "no apt task in this repository's own roles installs a pinned version, "
            "so this refusal would pass having examined nothing. One did when this "
            "was written; if the last pinned install has genuinely gone, this "
            "assertion has lost its subject and should be revisited rather than "
            "left to report success",
        )
        offenders = [task.where for task in pinned if task.declares_a_bound]
        self.assertEqual(
            [],
            offenders,
            f"these apt tasks name an exact version AND declare a `{BOUND_OPTION}`: "
            f"{offenders}. Where an exact version is named, an index older than that "
            "version's publication does not resolve to an older candidate -- it "
            "resolves to nothing, and the install fails. The saving is not worth "
            "converting a slow converge into a broken one",
        )

    def test_an_apt_task_installing_from_a_same_run_source_declares_no_bound(self) -> None:
        """SPECIFIED -- scenario "An install from a source the same run added
        declares no bound". The sharper of the two refusals: the index is
        RECENT, because an earlier task in the same converge fetched it, and
        WRONG, because it predates the source just written. A bound consults the
        timestamp, finds it well inside the window, skips the fetch, and the
        package is reported as having no installation candidate while every
        other install on the host succeeds.

        Keyed on the destination rather than on the module -- see
        APT_SOURCE_DIRECTORY -- and bounded to one file, which the module
        docstring records as a real gap rather than a completeness claim.
        """
        same_run = [task for task in self.tasks if task.installs_from_a_same_run_source]
        self.assertTrue(
            same_run,
            "no apt task in this repository's own roles follows a task in its own "
            f"file that writes under {APT_SOURCE_DIRECTORY}, so this refusal would "
            "pass having examined nothing. One did when this was written, and a "
            "check that matches nothing is exactly the vacuous green this "
            "destination-keyed predicate was chosen to avoid",
        )
        offenders = [task.where for task in same_run if task.declares_a_bound]
        self.assertEqual(
            [],
            offenders,
            f"these apt tasks install from a source an earlier task in their own "
            f"file writes under {APT_SOURCE_DIRECTORY}, and declare a "
            f"`{BOUND_OPTION}` anyway: {offenders}. The index fetched earlier in "
            "that same run is inside any bound and predates the source, so the "
            "package resolves to no candidate. The failure names the package rather "
            "than the cause, and it appears only on the run that adds the source -- "
            "the run least likely to be repeated",
        )


class TestTheBoundIsARoleVariableRatherThanALiteral(unittest.TestCase):
    """ADDED requirement: A Converge Bounds How Often It Re-Fetches the Package
    Index -- scenario "The bound is a variable, not a literal per task"."""

    def setUp(self) -> None:
        self.files = own_role_task_files()
        self.assertTrue(self.files, "no own-role task file was found; nothing would be read")
        self.declared = [task for task in apt_tasks(self.files) if task.declares_a_bound]

    def test_every_declared_bound_is_a_role_variable_carrying_a_default(self) -> None:
        """SPECIFIED -- "it SHALL take the bound from a variable of that role
        carrying a default, so that a role's declared bounds cannot drift apart
        and an operator changes that role's judgment in one place."

        Three propositions, in the order a failure is cheapest to read:

        1. The bound is a variable reference, not a literal. A literal repeated
           at each task is the drift this scenario exists to prevent.
        2. The variable is defaulted in THAT ROLE's `defaults/main.yml`. A
           reference to a name nothing defaults is an undefined-variable failure
           at converge time, pointing at the expression rather than at the cause.
        3. A role declares its bound through exactly ONE variable. "In one
           place" is the scenario's own words; two defaulted variables in one
           role are two judgments that can drift, which is the condition the
           first proposition rules out only within a single task.

        This asserts nothing about the VALUE. The delta makes no normative claim
        about it, so an hour, a minute or a week all pass here -- stating that
        plainly is better than implying a check that does not exist.
        """
        self.assertTrue(
            self.declared,
            f"no apt task in this repository's own roles declares a `{BOUND_OPTION}` "
            "at all, so this scenario has nothing to read. That is the expected "
            "state before this change is implemented, and a defect afterwards",
        )

        literals = [
            f"{task.where} declares {task.declared_bound!r}"
            for task in self.declared
            if not (
                isinstance(task.declared_bound, str)
                and VARIABLE_REFERENCE.match(task.declared_bound)
            )
        ]
        self.assertEqual(
            [],
            literals,
            f"these apt tasks declare a `{BOUND_OPTION}` that is not a reference to a "
            f"single variable: {literals}. A literal at each task is three places to "
            "edit and two places to forget, and it leaves an operator who disagrees "
            "with the judgment no one place to change it",
        )

        per_role: dict[str, set[str]] = {}
        for task in self.declared:
            match = VARIABLE_REFERENCE.match(task.declared_bound)
            per_role.setdefault(role_of(task.path), set()).add(match.group("name"))

        undefaulted = sorted(
            f"{role}: {name}"
            for role, names in per_role.items()
            for name in names
            if name not in role_default_names(role)
        )
        self.assertEqual(
            [],
            undefaulted,
            "these bound variables are referenced by a role's task file but are not "
            f"defaulted in that role's defaults/main.yml: {undefaulted}. The scenario "
            "requires a variable of that role CARRYING A DEFAULT; without one the "
            "role fails at converge time on an undefined name",
        )

        drifting = sorted(
            f"{role}: {sorted(names)}" for role, names in per_role.items() if len(names) > 1
        )
        self.assertEqual(
            [],
            drifting,
            "these roles declare their staleness bound through more than one "
            f"variable: {drifting}. Two defaulted variables in one role are two "
            "judgments that can drift apart, which is what taking the bound from "
            "one place is for",
        )


class TestFixturePlaysAreNotHeldToTheBound(unittest.TestCase):
    """ADDED requirement: A Converge Bounds How Often It Re-Fetches the Package
    Index -- scenario "A test fixture play is not held to the bound"."""

    def test_a_prepare_play_may_refresh_unconditionally(self) -> None:
        """SPECIFIED -- "a play that prepares an instance for a role's tests
        ... SHALL NOT be held to this requirement, its purpose being to
        establish an index where none exists rather than to install
        economically."

        The exemption is established two ways, because either alone is weak.
        POSITIVELY: at least one committed fixture play declares an
        unconditional refresh (`cache_valid_time: 0`), and it is reported by
        none of the checks above. NEGATIVELY: the file set those checks read
        contains no Molecule play at all, so the exemption holds by
        construction rather than by an exclusion list someone could delete.

        Ten such plays are committed. A check drawn without this boundary would
        fail every one of them -- they exist because `geerlingguy.docker`
        installs `ca-certificates` and `python3-debian` with `state: present`
        and no `update_cache`, which fails against a freshly created container
        whose cache is empty.
        """
        examined = own_role_task_files()
        molecule_plays_examined = [
            path.relative_to(ROOT).as_posix() for path in examined if "molecule" in path.parts
        ]
        self.assertEqual(
            [],
            molecule_plays_examined,
            "the file set the bound checks read reaches these Molecule plays: "
            f"{molecule_plays_examined}. A fixture play is outside this requirement, "
            "and holding one to it would reintroduce the empty-cache failure those "
            "plays were written to prevent",
        )

        unconditional = [
            task.where
            for task in apt_tasks(own_role_fixture_plays())
            if task.declares_a_bound and task.declared_bound == 0
        ]
        self.assertTrue(
            unconditional,
            "no committed Molecule play of this repository's own roles declares "
            f"`{BOUND_OPTION}: 0`, so the exemption this scenario states is exempting "
            "nothing. Ten did when this was written; if they have genuinely gone, "
            "this scenario has lost its subject and should be revisited rather than "
            "left to report success",
        )


# --------------------------------------------------------------------------
# The predicates themselves, against fixture text
# --------------------------------------------------------------------------


class TestThePredicatesAreARealReadOfATaskFile(unittest.TestCase):
    """DERIVED -- traces to no scenario. This class exists because every
    assertion above is RED until this change is implemented, so nothing else
    here establishes that they would go GREEN on a conforming shape, or that
    they would stay red on the specific defects they name. A check that can only
    fail is worth as little as one that can only pass.

    It reads no committed file and is expected to pass from the moment it is
    written, which is the opposite of every other test in this module and is
    stated so that its passing is not mistaken for coverage of the change. The
    idiom is this suite's own -- see `TestTheLivenessChecksAreARealReadOfTheFile`
    in the module beside this one.
    """

    def _tasks(self, text: str) -> list[AptTask]:
        document = yaml.safe_load(text)
        collected: list[AptTask] = []
        source_written = False
        for position, task in enumerate(flattened_tasks(document)):
            arguments = module_arguments(task, APT_MODULES)
            if arguments is not None:
                collected.append(
                    AptTask(ROOT / "ansible" / "roles" / "a_role" / "tasks" / "main.yml",
                            position, task, arguments, source_written)
                )
            if writes_an_apt_source(task):
                source_written = True
        return collected

    CONFORMING = """
- name: Write a keyring
  ansible.builtin.get_url:
    url: https://example.invalid/key
    dest: /usr/share/keyrings/example.gpg
    mode: "0644"

- name: Install an unpinned package under a bound
  ansible.builtin.apt:
    name: ufw
    state: present
    update_cache: true
    cache_valid_time: "{{ a_role_apt_cache_valid_time }}"

- name: Install a second unpinned package under the same bound
  ansible.builtin.apt:
    name:
      - fail2ban
    state: present
    update_cache: true
    cache_valid_time: "{{ a_role_apt_cache_valid_time | int }}"

- name: Add an apt source
  ansible.builtin.get_url:
    url: https://example.invalid/example.list
    dest: /etc/apt/sources.list.d/example.list
    mode: "0644"

- name: Install a pinned package from the source just added, under no bound
  ansible.builtin.apt:
    name: "example=1.2.3"
    state: present
    update_cache: true
"""

    def test_a_conforming_file_offends_no_predicate(self) -> None:
        tasks = self._tasks(self.CONFORMING)
        self.assertEqual(3, len(tasks), "the walker did not find all three apt tasks")
        qualifying = [task for task in tasks if task.is_qualifying]
        self.assertEqual(2, len(qualifying), "the antecedent selected the wrong tasks")
        self.assertTrue(all(task.declares_a_bound for task in qualifying))
        refusing = [task for task in tasks if not task.is_qualifying]
        self.assertEqual(1, len(refusing))
        self.assertTrue(refusing[0].pins_a_version)
        self.assertTrue(refusing[0].installs_from_a_same_run_source)
        self.assertFalse(refusing[0].declares_a_bound)
        for task in qualifying:
            self.assertRegex(task.declared_bound, VARIABLE_REFERENCE)

    def test_a_qualifying_task_without_a_bound_is_caught(self) -> None:
        text = """
- name: Install an unpinned package with no bound
  ansible.builtin.apt:
    name: ufw
    state: present
    update_cache: true
"""
        task = self._tasks(text)[0]
        self.assertTrue(task.is_qualifying)
        self.assertFalse(task.declares_a_bound)

    def test_a_literal_bound_is_not_a_variable_reference(self) -> None:
        text = """
- name: Install an unpinned package under a literal bound
  ansible.builtin.apt:
    name: ufw
    state: present
    update_cache: true
    cache_valid_time: 3600
"""
        task = self._tasks(text)[0]
        self.assertTrue(task.declares_a_bound)
        self.assertNotIsInstance(task.declared_bound, str)

    def test_a_pinned_install_is_recognised_in_both_spellings(self) -> None:
        text = """
- name: Pinned by version, as a scalar
  ansible.builtin.apt:
    name: "tailscale=1.102.3"
    state: present

- name: Pinned by version, inside a list
  ansible.builtin.apt:
    name:
      - curl
      - "tailscale=1.102.3"
    state: present

- name: Pinned by artifact
  ansible.builtin.apt:
    deb: /tmp/example_1.2.3_amd64.deb
"""
        self.assertTrue(all(task.pins_a_version for task in self._tasks(text)))

    def test_a_same_run_source_is_recognised_whatever_module_writes_it(self) -> None:
        """The trap this predicate exists for: the repository's only instance
        writes its source with `ansible.builtin.get_url`, so a check keyed on
        `apt_repository` would match nothing and pass vacuously."""
        for module, option in (
            ("ansible.builtin.get_url", "dest"),
            ("ansible.builtin.copy", "dest"),
            ("ansible.builtin.template", "dest"),
            ("ansible.builtin.file", "path"),
            ("ansible.builtin.apt_repository", "filename"),
        ):
            with self.subTest(module=module):
                text = f"""
- name: Write the source
  {module}:
    {option}: /etc/apt/sources.list.d/example.list

- name: Install from it
  ansible.builtin.apt:
    name: example
    state: present
"""
                task = self._tasks(text)[0]
                expected = option in DESTINATION_OPTIONS
                self.assertEqual(
                    expected,
                    task.installs_from_a_same_run_source,
                    f"{module} writing its source through `{option}` is "
                    f"{'not ' if expected else ''}seen by this predicate. "
                    "`apt_repository`'s `filename:` is a BARE NAME, not a path, so it "
                    "is deliberately outside a destination-keyed read -- recorded "
                    "here so the gap is a decision rather than a surprise",
                )

    def test_an_apt_task_inside_a_block_is_not_missed(self) -> None:
        text = """
- name: A guarded install
  block:
    - name: Install an unpinned package with no bound
      ansible.builtin.apt:
        name: ufw
        state: present
  rescue:
    - name: Install a fallback with no bound
      apt:
        name: iptables
        state: present
"""
        tasks = self._tasks(text)
        self.assertEqual(2, len(tasks), "a task inside a block or rescue was not walked into")
        self.assertTrue(all(task.is_qualifying and not task.declares_a_bound for task in tasks))

    def test_a_task_naming_no_package_does_not_qualify(self) -> None:
        """An index-refresh-only task installs nothing, so the requirement's
        antecedent -- "a task ... that installs a package" -- does not reach
        it."""
        text = """
- name: Refresh the index and install nothing
  ansible.builtin.apt:
    update_cache: true
"""
        self.assertFalse(self._tasks(text)[0].is_qualifying)


if __name__ == "__main__":
    unittest.main()
