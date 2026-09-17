"""Static-assertion tests for configuring more than one host from this repository.

Derived from the delta specs of the OpenSpec change `configure-the-staging-host`,
before any implementation of that change existed. The path those deltas sit at
is not written here: a change's artifacts move when it is archived, and this
repository's citation convention is to name the change and the artifact in prose
instead.

Every requirement below belongs to `iac-host-configuration`
(openspec/specs/iac-host-configuration/spec.md). Three are in the change's
delta: *Dynamic Inventory via the hcloud Plugin, One Source per Stack* (MODIFIED), *Host Configuration
Names the Environment It Targets* (ADDED) and *A Run Whose Target Group Resolves
to No Host Refuses* (ADDED). Each section below names the one it traces to, and
every assertion is annotated SPECIFIED (it traces to SHALL text or to a scenario
in a delta spec) or DERIVED (it traces to that change's `design.md` or
`tasks.md` rather than to a scenario). See that change's `test-plan.md` for the
scenario-to-test mapping, the baseline, the scenarios deliberately left
uncovered, the obsolete-test candidates, and the project questions this file
took an assumption on.

Why this is a seventh file in the suite rather than a section of an existing one
-------------------------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. Nothing here edits, deletes or disables an
existing test. Where a property this change states is already asserted by a
sibling module, this file cites that assertion in `test-plan.md` instead of
restating it.

`TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in
`test_ci_configuration.py` reads every module in this directory, so this file is
held to the no-network, no-credential, no-container, no-Terraform constraint by
that class. It is written to satisfy it: standard library, `yaml`, the sibling
helpers, and no spawned command at all.

Why these properties are here and not in Molecule
-------------------------------------------------
AGENTS.md's "Testing" section splits the two: Molecule asserts what a role DOES
on a host, `.github/tests` asserts what a committed file SAYS, statically.
Everything below is a read of `ansible/inventory/`, `ansible/ansible.cfg`,
`ansible/playbooks/host-baseline.yml`, `.ansible-lint` and
`.pre-commit-config.yaml` as text. None of it starts Ansible.

The consequence is stated rather than left to be discovered, because it bounds
what a green run here means: **no assertion in this file establishes that the
guard play actually refuses.** That behaviour needs `ansible-playbook` to run a
play against no host, which is neither a role on a host nor a static read, so it
has no home under any of this project's three test commands. The change's
design.md Decision 10 records that gap, its tasks.md 2.3 and 9.1a verify the
behaviour by hand, and its tasks.md 8.2 queues the missing layer. What this file
asserts is that the play is SHAPED so that it can refuse -- that the guard exists,
targets localhost, checks both conditions in separate tasks, names the
environment when it fails, and adds no input of its own to a run that resolves
hosts.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable by name:
    python3 -m unittest discover --start-directory .github/tests \\
        -k test_every_environment_directory_has_an_inventory_source_of_its_own

    # or one class:
    python3 -m unittest discover --start-directory .github/tests \\
        -k TestEachEnvironmentHasAnInventorySourceOfItsOwn

Run from the repository root, and through `discover` in both forms: it is
discovery that puts `.github/tests` on `sys.path`, which is what makes the
sibling imports below resolve. `python3 -m unittest <module>.<class>.<test>`
from the repository root does not, and fails to import this module.

Which assertions here are red before the implementation, and which are guards
-----------------------------------------------------------------------------
Both kinds are present deliberately, and the distinction matters when reading a
run of this file. `test-plan.md` records, per test, which of the current tree's
three facts it fails on.

- RED until the change lands -- every assertion in
  `TestEachEnvironmentHasAnInventorySourceOfItsOwn`,
  `TestAFurtherEnvironmentIsAddedRatherThanEditedIn`,
  `TestTheBaselinePlayNamesTheEnvironmentItTargets` and
  `TestARunWhoseTargetGroupResolvesToNoHostRefuses`, and two of the three in
  `TestANamedInventorySourceIsWhatMakesARunReachAnEnvironment`. The tree today
  has one inventory source, an `ansible.cfg` naming it as a default, and a play
  carrying the literal `hosts: prod`.
- GREEN from the moment they are written --
  `test_ansible_cfg_does_not_set_the_neighbouring_unparsed_is_failed` and both
  assertions in `TestInventoryIsResolvedLiveRatherThanFromACommittedFile`. Their
  subject is a state the current tree is already in and which this change must
  not leave: today's single source already names the plugin and groups by label,
  and today's `ansible.cfg` already sets neither of the two one-word-apart
  settings. A pass is therefore the expected result and is NOT an alarm of the
  "passed before any implementation existed" kind -- the target is not absent.
  What these assertions are for is the edit that would quietly undo them.
- `TestTheseReadsDiscriminate` at the end exists because of the second bullet: a
  predicate that returned "no offence" unconditionally would satisfy every guard
  above while checking nothing. It runs the same predicates over fixture
  documents carrying the defect each one names.

What no assertion here establishes
----------------------------------
Nothing in this file reaches the Hetzner Cloud API, a Hetzner token, a shell's
environment, or a running Ansible process. Whether a credential exists, whether
it authenticates, whether a group resolves to a host, and what Ansible does when
one does not are all run-time facts rather than repository content, and this
suite makes no network call and spawns nothing. A green run here establishes
that the committed files are SHAPED so those run-time outcomes are the ones the
requirements describe, never that they occurred.
"""

from __future__ import annotations

import configparser
import re
import unittest
from pathlib import Path

from test_a_second_environment import environment_identifiers
from test_ci_configuration import (
    PRE_COMMIT_CONFIG,
    ROOT,
    load_yaml,
    read_text,
)
from test_environment_agnostic_pipeline import environment_directories

import yaml

ANSIBLE_DIR = ROOT / "ansible"
INVENTORY_DIR = ANSIBLE_DIR / "inventory"
ANSIBLE_CFG = ANSIBLE_DIR / "ansible.cfg"
HOST_BASELINE = ANSIBLE_DIR / "playbooks" / "host-baseline.yml"
ANSIBLE_LINT_CONFIG = ROOT / ".ansible-lint"

# The plugin the requirement names, in the fully-qualified form Ansible resolves.
HCLOUD_PLUGIN = "hetzner.hcloud.hcloud"

# The label the requirement names as what hosts are grouped by, as the plugin's
# `keyed_groups` addresses it.
ENVIRONMENT_LABEL_KEY = "hcloud_labels.environment"

# The plugin's own built-in fallback variable, and Terraform's. The MODIFIED
# requirement obliges each source to take its credential "from an environment
# variable whose name is distinct from every other environment's"; the bare name
# is distinct from no environment's, because it is what the plugin reads when a
# source names nothing, and it is simultaneously the name the Terraform provider
# reads. A source relying on it makes a run's reach a property of the shell.
PLUGIN_FALLBACK_CREDENTIAL = "HCLOUD_TOKEN"

# The play input the ADDED requirement obliges the play to take. The NAME is
# DERIVED -- no scenario states it; the delta says "an input supplied per run"
# throughout, and `target_environment` comes from the change's design.md
# Decision 4 and tasks.md 2.1. It is asserted here so the implementing author
# has a red-to-green target, and so the guard assertions below can address the
# input at all.
TARGET_INPUT = "target_environment"

# The pre-commit hook that compiles the play without running it, by its id in
# `.pre-commit-config.yaml`. DERIVED -- design.md Decision 5.
SYNTAX_CHECK_HOOK_ID = "ansible-playbook-syntax-check"

# Host names that mean "the machine the run was started from", which is what a
# play must target if it is to run when the real target group is empty.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


# --------------------------------------------------------------------------
# Reading an inventory source
#
# The plugin's `verify_file` accepts a path only if it ends with `hcloud.yml`
# or `hcloud.yaml` (design.md Decision 1), so the filename shape is forced
# rather than chosen. Sources are nonetheless discovered by CONTENT below --
# any top-level file under `ansible/inventory/` declaring the plugin -- and not
# by that suffix. Discovering by the suffix would make a source misnamed such
# that Ansible cannot parse it invisible to the census, which is the one
# mistake the census exists to catch.
# --------------------------------------------------------------------------

# `lookup('env', 'NAME')` and `lookup('ansible.builtin.env', 'NAME')`, which is
# the form design.md Decision 1 uses.
ENV_LOOKUP = re.compile(
    r"""lookup\(\s*['"](?:ansible\.builtin\.)?env['"]\s*,\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]"""
)

# A bare `{{ NAME }}`, accepted as a second spelling of the same thing so that a
# source templating its token from a variable rather than from a lookup is read
# as naming that variable rather than as naming nothing.
BARE_TEMPLATE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

# Both spellings of the plugin's token option. `api_token` is current;
# `token` is the older name the committed source's comment still uses. Accepting
# both means a source is never reported as naming no credential merely for
# spelling the option the other way.
TOKEN_OPTIONS = ("api_token", "token")


class InventorySource:
    """One committed file that resolves hosts from Hetzner, as it reads."""

    def __init__(self, path: Path, root: Path):
        self.path = path
        self.relative = path.relative_to(root).as_posix()
        self.document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(self.document, dict):
            self.document = {}

        name = path.name
        for suffix in (".hcloud.yml", ".hcloud.yaml"):
            if name.endswith(suffix):
                self.environment: str | None = name[: -len(suffix)] or None
                break
        else:
            # A source whose name carries no environment prefix at all -- the
            # single shared `hcloud.yml` this change replaces is exactly this.
            self.environment = None

        self.plugin = self.document.get("plugin")
        self.keyed_groups = self.document.get("keyed_groups") or []

        token = None
        for option in TOKEN_OPTIONS:
            if option in self.document:
                token = self.document[option]
                break
        self.declares_token_option = token is not None
        self.credential: str | None = None
        if isinstance(token, str):
            match = ENV_LOOKUP.search(token) or BARE_TEMPLATE.search(token)
            if match:
                self.credential = match.group(1)

    def groups_by_the_environment_label(self) -> bool:
        entries = self.keyed_groups if isinstance(self.keyed_groups, list) else []
        return any(
            isinstance(entry, dict) and entry.get("key") == ENVIRONMENT_LABEL_KEY
            for entry in entries
        )

    def normalised(self) -> object:
        """The source's parsed document with its own credential name removed.

        What is left is everything two sources would have to agree on if adding
        an environment is adding a file rather than editing one. Comments are
        gone by construction -- this is the PARSED document, so a header
        rewritten to describe one environment cannot make two sources read as
        differing.
        """

        def scrub(value: object) -> object:
            if isinstance(value, dict):
                return {key: scrub(item) for key, item in sorted(value.items())}
            if isinstance(value, list):
                return [scrub(item) for item in value]
            if isinstance(value, str) and self.credential:
                return value.replace(self.credential, "<credential>")
            return value

        return scrub(self.document)


def inventory_files(root: Path | None = None) -> list[Path]:
    """Every top-level YAML file under `ansible/inventory/`.

    Top-level only: `group_vars/` beneath it holds an environment's variables,
    not an inventory source, and reading those as sources would report every
    one of them as a source declaring no plugin.
    """
    base = (ROOT if root is None else root) / "ansible" / "inventory"
    if not base.is_dir():
        return []
    return sorted(
        entry
        for entry in base.iterdir()
        if entry.is_file() and entry.suffix in (".yml", ".yaml")
    )


def inventory_sources(root: Path | None = None) -> list[InventorySource]:
    """Every committed file under `ansible/inventory/` that names the plugin."""
    base = ROOT if root is None else root
    found = []
    for path in inventory_files(base):
        source = InventorySource(path, base)
        if source.plugin == HCLOUD_PLUGIN:
            found.append(source)
    return found


def host_enumerating_files(root: Path | None = None) -> list[str]:
    """Every top-level inventory file that enumerates a host itself.

    A static or hand-maintained inventory is what the requirement forbids, and
    it is recognisable without knowing its format: it names hosts, or it names
    an address for one. A source that resolves hosts from an API names neither.
    """
    offences = []
    for path in inventory_files(root):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(document, dict):
            continue
        if document.get("plugin"):
            # A plugin source may legitimately carry `groups:`/`compose:` keys.
            # It carries no host list, which is what the walk below finds.
            if "hosts" in document:
                offences.append(f"{path.name}: a plugin source that also enumerates `hosts`")
            continue
        stack: list[object] = [document]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                if "hosts" in value or "ansible_host" in value:
                    offences.append(f"{path.name}: enumerates hosts in a committed file")
                    break
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
    return offences


# --------------------------------------------------------------------------
# Reading `ansible.cfg`
# --------------------------------------------------------------------------


def ansible_config(root: Path | None = None) -> configparser.ConfigParser:
    path = (ROOT if root is None else root) / "ansible" / "ansible.cfg"
    parser = configparser.ConfigParser()
    parser.read_string(read_text(path))
    return parser


# --------------------------------------------------------------------------
# Reading the host-baseline playbook
#
# The play is read as PARSED YAML rather than as text: `hosts: prod` and
# `hosts: "{{ target_environment }}"` are two values of one key, and a text
# read cannot tell either from the same words inside the header comment that
# sits above them.
# --------------------------------------------------------------------------

JINJA_EXPRESSION = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Words that appear inside a Jinja expression without being a variable the run
# has to supply: literals, operators, tests and the filters a guard of this
# shape uses. The list is deliberately generous, for the reason the sibling
# modules give for theirs: the assertion below is that a guard references NO
# variable outside a tiny allowlist, so a word missing from this list produces a
# false offence, and the repair for a false offence is to loosen an assertion --
# the repair this suite must never need.
JINJA_WORDS = frozenset(
    {
        "and", "or", "not", "in", "is", "if", "else", "true", "false", "none",
        "True", "False", "None",
        "default", "length", "count", "list", "string", "int", "trim", "lower",
        "upper", "join", "first", "last", "map", "select", "reject", "sort",
        "defined", "undefined", "none_", "sameas", "iterable", "mapping",
        "sequence", "string_", "number", "boolean", "equalto", "eq", "ne",
    }
)

# The two names the guard is allowed to read. `groups` is Ansible's own
# inventory magic variable, which no run supplies; `target_environment` is the
# input the requirement obliges the run to supply and is therefore not a
# FURTHER one.
GUARD_ALLOWED_NAMES = frozenset({TARGET_INPUT, "groups"})


def plays(root: Path | None = None) -> list[dict]:
    path = (ROOT if root is None else root) / "ansible" / "playbooks" / "host-baseline.yml"
    document = load_yaml(path)
    if not isinstance(document, list):
        raise AssertionError(
            f"{path.name} does not parse as a list of plays; it parsed as "
            f"{type(document).__name__}"
        )
    return [play for play in document if isinstance(play, dict)]


def targets_localhost(play: dict) -> bool:
    hosts = play.get("hosts")
    return isinstance(hosts, str) and hosts.strip().lower() in LOCAL_HOSTS


def converge_plays(root: Path | None = None) -> list[dict]:
    """The plays that configure a host, as distinct from the guard."""
    return [play for play in plays(root) if play.get("roles")]


def assert_tasks(play: dict) -> list[dict]:
    """Every `ansible.builtin.assert` task a play carries, in order."""
    found = []
    for key in ("pre_tasks", "tasks", "post_tasks"):
        for task in play.get(key) or []:
            if not isinstance(task, dict):
                continue
            for name in ("assert", "ansible.builtin.assert"):
                if name in task:
                    found.append(task)
                    break
    return found


def task_conditions(task: dict) -> list[str]:
    body = task.get("assert") or task.get("ansible.builtin.assert") or {}
    if not isinstance(body, dict):
        return []
    that = body.get("that")
    if isinstance(that, str):
        return [that]
    return [entry for entry in (that or []) if isinstance(entry, str)]


def task_fail_message(task: dict) -> str:
    body = task.get("assert") or task.get("ansible.builtin.assert") or {}
    if not isinstance(body, dict):
        return ""
    return str(body.get("fail_msg") or body.get("msg") or "")


def strings_in(value: object) -> list[str]:
    """Every string anywhere inside a parsed structure."""
    found: list[str] = []
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            found.append(item)
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return found


def variables_referenced(value: object) -> set[str]:
    """The names a structure's Jinja expressions read.

    Quoted literals are dropped first, so a `fail_msg` mentioning a filename in
    quotes contributes nothing; what remains is split on identifiers, and the
    Jinja vocabulary above is subtracted.
    """
    names: set[str] = set()
    for text in strings_in(value):
        for expression in JINJA_EXPRESSION.findall(text):
            stripped = QUOTED.sub(" ", expression)
            names.update(IDENTIFIER.findall(stripped))
    # A bare `that:` condition is an expression too, without the braces.
    return {name for name in names if name not in JINJA_WORDS}


def condition_variables(conditions: list[str]) -> set[str]:
    """The names a list of bare `that:` conditions reads."""
    names: set[str] = set()
    for condition in conditions:
        body = condition
        for expression in JINJA_EXPRESSION.findall(condition):
            body = expression
        stripped = QUOTED.sub(" ", body)
        names.update(IDENTIFIER.findall(stripped))
    return {name for name in names if name not in JINJA_WORDS}


# ==========================================================================
# iac-host-configuration / Dynamic Inventory via the hcloud Plugin, One Source per Stack (MODIFIED)
# ==========================================================================


class TestEachEnvironmentHasAnInventorySourceOfItsOwn(unittest.TestCase):
    """MODIFIED requirement: Dynamic Inventory via the hcloud Plugin, One Source per Stack -- scenario
    "An environment's source reaches only its own project"."""

    def setUp(self) -> None:
        self.sources = inventory_sources()
        self.environments = {directory.name for directory in environment_directories()}
        self.assertTrue(
            self.environments,
            "no environment directory was discovered under terraform/stacks/, "
            "so every assertion in this class would pass having compared nothing",
        )

    def test_every_environment_directory_has_an_inventory_source_of_its_own(self) -> None:
        """SPECIFIED -- "Each environment SHALL declare its own inventory
        source".

        The census runs in both directions in one assertion: an environment with
        no source is a host Ansible cannot reach, and a source naming no
        environment -- the single shared `hcloud.yml` this change replaces is
        one -- is a source whose reach is decided by whichever credential the
        shell happened to hold.
        """
        declared = {source.environment for source in self.sources if source.environment}
        anonymous = sorted(
            source.relative for source in self.sources if not source.environment
        )
        self.assertEqual(
            [],
            anonymous,
            "these inventory sources name no environment, so nothing in a run says "
            f"which project they reach: {anonymous}",
        )
        self.assertEqual(
            self.environments,
            declared,
            "the set of environments with an inventory source does not match the set "
            f"of environment directories: directories {sorted(self.environments)}, "
            f"sources {sorted(declared)}",
        )

    def test_no_two_inventory_sources_take_the_same_credential_variable(self) -> None:
        """SPECIFIED -- "each source SHALL authenticate with that environment's
        own read-only Hetzner credential, supplied from an environment variable
        whose name is distinct from every other environment's".

        Fails closed on a set too small to collide. Over one source this
        assertion is vacuous, and vacuous is exactly the state the tree is in
        before the change: the guard is what stops a green run from being read
        as evidence the credentials are separated.
        """
        self.assertGreaterEqual(
            len(self.sources),
            2,
            f"{len(self.sources)} inventory source(s) were discovered, and this "
            "repository has "
            f"{len(self.environments)} environments -- a collision check over fewer "
            "than two sources would pass having compared nothing",
        )
        seen: dict[str, str] = {}
        collisions = []
        for source in self.sources:
            if not source.credential:
                continue
            if source.credential in seen:
                collisions.append(
                    f"{seen[source.credential]} and {source.relative} both take "
                    f"{source.credential}"
                )
            seen[source.credential] = source.relative
        self.assertEqual(
            [],
            collisions,
            "two environments' inventory sources authenticate with the same "
            f"environment variable, so either can reach the other's project: {collisions}",
        )

    def test_no_inventory_source_relies_on_the_plugins_bare_credential_fallback(self) -> None:
        """SPECIFIED -- the same sentence: the credential is "supplied from an
        environment variable whose name is distinct from every other
        environment's", which the plugin's built-in fallback is not.

        Two failures, reported separately because they read differently: a
        source that declares no token option at all falls back silently, and a
        source that declares one naming the bare variable falls back visibly.
        Both make a run's reach a property of the shell -- and the bare name is
        also the one Terraform's provider reads, which is what the change's
        design.md Decision 3 separates.
        """
        silent = sorted(
            source.relative for source in self.sources if not source.declares_token_option
        )
        self.assertEqual(
            [],
            silent,
            "these inventory sources declare no token option, so the plugin falls "
            f"back to the bare {PLUGIN_FALLBACK_CREDENTIAL}: {silent}",
        )
        bare = sorted(
            source.relative
            for source in self.sources
            if source.credential == PLUGIN_FALLBACK_CREDENTIAL
        )
        self.assertEqual(
            [],
            bare,
            f"these inventory sources name {PLUGIN_FALLBACK_CREDENTIAL} itself, which "
            "is the plugin's fallback and Terraform's own variable, not an "
            f"environment's own credential: {bare}",
        )
        unnamed = sorted(
            source.relative
            for source in self.sources
            if source.declares_token_option and not source.credential
        )
        self.assertEqual(
            [],
            unnamed,
            "these inventory sources declare a token option this read cannot resolve "
            "to an environment variable name, so which credential they take is not "
            f"readable from the committed file: {unnamed}",
        )


class TestAFurtherEnvironmentIsAddedRatherThanEditedIn(unittest.TestCase):
    """MODIFIED requirement: Dynamic Inventory via the hcloud Plugin, One Source per Stack -- scenario "A
    further environment is brought into inventory"."""

    def test_the_inventory_sources_differ_only_in_the_credential_they_name(self) -> None:
        """DERIVED -- the scenario obliges a further environment to be brought
        in "without editing any existing environment's inventory source", and no
        static read can observe an edit that did not happen. What CAN be read is
        the property that makes such an edit unnecessary: two sources that agree
        on everything except the credential name are a shape a third is produced
        by copying, where two that have drifted apart are not.

        The comparison is of PARSED documents with each source's own credential
        substituted out, so differing header comments -- which the change's
        tasks.md 1.1 requires prod's to be -- are not read as a divergence.

        Reported with the keys that differ rather than as a bare inequality: the
        message is what tells the reader whether a real divergence was
        introduced or whether this assertion has outlived its subject.
        """
        sources = inventory_sources()
        self.assertGreaterEqual(
            len(sources),
            2,
            f"{len(sources)} inventory source(s) were discovered -- a comparison "
            "across sources would pass having compared nothing",
        )
        reference, *others = sources
        expected = reference.normalised()
        for source in others:
            with self.subTest(source=source.relative):
                actual = source.normalised()
                differing = sorted(
                    key
                    for key in set(expected) | set(actual)
                    if expected.get(key) != actual.get(key)
                )
                self.assertEqual(
                    expected,
                    actual,
                    f"{source.relative} and {reference.relative} differ in more than "
                    f"the credential each names -- these keys disagree: {differing}. "
                    "Adding a third environment then means editing them rather than "
                    "copying one.",
                )


class TestANamedInventorySourceIsWhatMakesARunReachAnEnvironment(unittest.TestCase):
    """MODIFIED requirement: Dynamic Inventory via the hcloud Plugin, One Source per Stack -- scenarios
    "An environment's source reaches only its own project" and "An inventory
    source cannot authenticate"."""

    def setUp(self) -> None:
        self.config = ansible_config()

    def test_ansible_cfg_declares_no_default_inventory(self) -> None:
        """SPECIFIED -- "a source reaches exactly one environment; a single
        source that every environment shares would reach whichever project the
        credential in scope happened to belong to, and nothing in a run would
        say which".

        A configured default is that shared source by another route: a run that
        names no inventory silently takes one environment's, and which
        environment that is, is a property of the config file rather than of the
        run. The change's design.md Decision 2 removes the line rather than
        re-pointing it, for the same reason its ADDED requirement gives the play
        input no default -- any default is one environment's, and the one it
        would be here is production's.
        """
        configured = None
        if self.config.has_section("defaults"):
            configured = self.config["defaults"].get("inventory")
        self.assertIsNone(
            configured,
            f"ansible/ansible.cfg declares a default inventory ({configured!r}), so a "
            "run that names none still reaches an environment, chosen by the config "
            "rather than by the run",
        )

    def test_ansible_cfg_fails_a_run_whose_inventory_source_cannot_be_parsed(self) -> None:
        """SPECIFIED -- "An inventory source whose credential is absent or is
        rejected SHALL fail the run. It SHALL NOT resolve to an empty
        environment, which is indistinguishable from an environment whose server
        does not exist."

        This assertion is the whole of what a static read can establish about
        that sentence: Ansible's default is to warn on an unparseable source and
        continue, so without this setting the requirement is false and the guard
        play of the ADDED requirement reports a bad credential as a destroyed
        server. Whether the setting has the effect described was reproduced by
        hand -- see the change's design.md Decision 2a and tasks.md 1.3a; nothing
        here runs Ansible.
        """
        self.assertTrue(
            self.config.has_section("inventory"),
            "ansible/ansible.cfg declares no [inventory] section, so an inventory "
            "source that cannot authenticate resolves to an empty environment",
        )
        section = self.config["inventory"]
        self.assertIn(
            "any_unparsed_is_failed",
            section,
            "ansible/ansible.cfg does not set `any_unparsed_is_failed`, so a source "
            "whose credential is absent, empty or rejected yields an inventory in "
            "which that environment simply holds no host",
        )
        self.assertTrue(
            section.getboolean("any_unparsed_is_failed"),
            "ansible/ansible.cfg sets `any_unparsed_is_failed` to "
            f"{section.get('any_unparsed_is_failed')!r}, which does not fail the run",
        )

    def test_ansible_cfg_does_not_set_the_neighbouring_unparsed_is_failed(self) -> None:
        """DERIVED -- design.md Decision 2a, which states this and asks for it to
        be asserted rather than left to a reader's care. GREEN before the change
        as well as after: today's `ansible.cfg` sets neither setting.

        `unparsed_is_failed` is one word from `any_unparsed_is_failed` and is a
        different setting: it fires when NO source parsed at all, which is
        exactly the state the `--syntax-check` hook is left in once the default
        inventory is removed. Setting it would fail that hook on every commit,
        and the failure would read as the OTHER setting misbehaving. This exists
        so that nobody "fixes" one into breaking the other.
        """
        if not self.config.has_section("inventory"):
            self.skipTest("ansible/ansible.cfg declares no [inventory] section")
        self.assertNotIn(
            "unparsed_is_failed",
            self.config["inventory"],
            "ansible/ansible.cfg sets `unparsed_is_failed`, which is NOT "
            "`any_unparsed_is_failed`: it fails a run in which no source parsed at "
            "all, which is the state the ansible-playbook --syntax-check hook runs "
            "in now that no default inventory is declared",
        )


class TestInventoryIsResolvedLiveRatherThanFromACommittedFile(unittest.TestCase):
    """MODIFIED requirement: Dynamic Inventory via the hcloud Plugin, One Source per Stack -- scenarios
    "Inventory resolved live from Hetzner" and "Disabled server yields no stale
    inventory entry".

    Both assertions here are GREEN before the change: today's single source
    already names the plugin and groups by the label, and the tree holds no
    committed hosts file. Their subject is what this change must not lose while
    splitting one source into several -- a copy that dropped `keyed_groups`
    would leave the environment groups the play targets nonexistent.
    """

    def test_every_inventory_source_resolves_hosts_from_the_plugin_and_groups_by_label(
        self,
    ) -> None:
        """SPECIFIED -- "Ansible SHALL discover target hosts via the `hcloud`
        dynamic inventory plugin", "Hosts SHALL be grouped by the `environment`
        label already applied to Hetzner resources", and scenario "Inventory
        resolved live from Hetzner"."""
        sources = inventory_sources()
        self.assertTrue(
            sources,
            "no inventory source declaring "
            f"`plugin: {HCLOUD_PLUGIN}` was discovered under ansible/inventory/, so "
            "this assertion would pass having read nothing",
        )
        ungrouped = sorted(
            source.relative
            for source in sources
            if not source.groups_by_the_environment_label()
        )
        self.assertEqual(
            [],
            ungrouped,
            "these inventory sources do not group hosts by "
            f"`{ENVIRONMENT_LABEL_KEY}`, so the environment group a play targets "
            f"does not exist under them: {ungrouped}",
        )

    def test_no_committed_inventory_file_enumerates_a_host(self) -> None:
        """SPECIFIED -- "rather than a static or hand-maintained inventory
        file", and scenario "Disabled server yields no stale inventory entry".

        What this establishes is bounded: a host that no committed file names
        cannot go stale in one. That an actually-destroyed server yields no
        entry is a fact about a live API call, and is deliberately untested here
        -- see this module's header.
        """
        offences = host_enumerating_files()
        self.assertEqual(
            [],
            offences,
            "these files under ansible/inventory/ enumerate hosts themselves, so a "
            f"destroyed server can leave a stale entry behind: {offences}",
        )


# ==========================================================================
# iac-host-configuration / Host Configuration Names the Environment It Targets
# (ADDED)
# ==========================================================================


class TestTheBaselinePlayNamesTheEnvironmentItTargets(unittest.TestCase):
    """ADDED requirement: Host Configuration Names the Environment It Targets --
    scenarios "A run names the environment it configures" and "A run supplying
    no environment refuses"."""

    def setUp(self) -> None:
        self.converging = converge_plays()
        self.assertTrue(
            self.converging,
            "no play in ansible/playbooks/host-baseline.yml declares `roles:`, so "
            "there is no converge play for these assertions to read",
        )
        self.environments = environment_identifiers()

    def test_the_baseline_play_takes_its_target_from_a_supplied_input(self) -> None:
        """SPECIFIED -- "The host-baseline play SHALL take the environment it
        configures as an input supplied per run, rather than naming one
        environment in the play itself", and scenario "A run names the
        environment it configures".

        Two failures, separated: a `hosts:` that is not a template at all, and a
        template reading something other than the input. The first is the
        current tree's `hosts: prod`.
        """
        for play in self.converging:
            with self.subTest(play=play.get("name")):
                hosts = play.get("hosts")
                self.assertIsInstance(
                    hosts,
                    str,
                    f"the converge play's `hosts:` is {hosts!r}, which this read "
                    "cannot resolve to either a literal or an input",
                )
                named = {
                    environment
                    for environment in self.environments
                    if re.search(rf"\b{re.escape(environment)}\b", hosts)
                }
                self.assertEqual(
                    set(),
                    named,
                    f"the converge play's `hosts:` is {hosts!r}, which names the "
                    f"environment(s) {sorted(named)} in the play itself",
                )
                self.assertIn(
                    TARGET_INPUT,
                    variables_referenced(hosts),
                    f"the converge play's `hosts:` is {hosts!r}, which does not read "
                    f"the `{TARGET_INPUT}` input a run supplies",
                )

    def test_the_baseline_play_gives_its_target_no_default(self) -> None:
        """SPECIFIED -- "That input SHALL have no default", and scenario "A run
        supplying no environment refuses": the run must fail "rather than
        defaulting to an environment".

        Read as the absence of a `default(...)` filter on the `hosts:`
        expression, which is the one way a play can supply the default itself.
        The change's design.md Decision 5 rejects exactly this spelling as the
        way to satisfy the linter, so it is a spelling someone will reach for.
        """
        for play in self.converging:
            with self.subTest(play=play.get("name")):
                hosts = str(play.get("hosts"))
                for expression in JINJA_EXPRESSION.findall(hosts):
                    self.assertNotRegex(
                        expression,
                        r"\bdefault\s*\(",
                        f"the converge play's `hosts:` is {hosts!r}, which supplies a "
                        "default for the input the requirement says must have none",
                    )
                self.assertTrue(
                    JINJA_EXPRESSION.search(hosts),
                    f"the converge play's `hosts:` is {hosts!r}, which is a literal "
                    "rather than an input, so the question of its default does not "
                    "arise -- and the play names one environment",
                )


class TestStaticToolingIsGivenASentinelRatherThanAnEnvironment(unittest.TestCase):
    """ADDED requirement: Host Configuration Names the Environment It Targets.

    DERIVED throughout -- no scenario states any of this. Two tools compile the
    play without running it and fail on a templated `hosts:` with nothing
    supplied, and design.md Decision 5 feeds each a sentinel in configuration.
    The requirement these assertions protect is the one above: a sentinel that
    drifted into naming a real environment would mean the compile step resolves
    the play against an environment nobody asked for, and it would do so
    invisibly. Decision 5 asks for this to be asserted statically, in as many
    words.
    """

    def _lint_sentinel(self) -> str:
        document = load_yaml(ANSIBLE_LINT_CONFIG)
        extra = document.get("extra_vars") if isinstance(document, dict) else None
        self.assertIsInstance(
            extra,
            dict,
            ".ansible-lint declares no `extra_vars:` mapping, so its unskippable "
            "syntax-check rule has no value for the play's templated `hosts:`",
        )
        self.assertIn(
            TARGET_INPUT,
            extra,
            f".ansible-lint's `extra_vars:` does not supply `{TARGET_INPUT}`",
        )
        value = extra[TARGET_INPUT]
        self.assertIsInstance(value, str)
        self.assertTrue(value.strip(), ".ansible-lint supplies an empty sentinel")
        return str(value).strip()

    def test_the_lint_sentinel_names_no_environment_this_repository_has(self) -> None:
        """DERIVED -- design.md Decision 5: "The sentinel must not name a real
        environment"."""
        sentinel = self._lint_sentinel()
        self.assertNotIn(
            sentinel,
            environment_identifiers(),
            f".ansible-lint compiles the play against `{TARGET_INPUT}={sentinel}`, "
            "which names an environment this repository actually has",
        )

    def test_the_syntax_check_hook_supplies_the_same_sentinel(self) -> None:
        """DERIVED -- design.md Decision 5 and tasks.md 3.2. Two tools, one
        value: a hook and a linter compiling the play against different
        sentinels means the property asserted above holds of one of them and is
        unasserted for the other."""
        sentinel = self._lint_sentinel()
        document = load_yaml(PRE_COMMIT_CONFIG)
        entries = []
        for repository in document.get("repos") or []:
            for hook in repository.get("hooks") or []:
                if hook.get("id") == SYNTAX_CHECK_HOOK_ID:
                    entries.append(str(hook.get("entry") or ""))
        self.assertTrue(
            entries,
            f".pre-commit-config.yaml declares no hook with id "
            f"`{SYNTAX_CHECK_HOOK_ID}`, so nothing was read",
        )
        for entry in entries:
            with self.subTest(entry=entry[:60]):
                supplied = re.findall(
                    rf"{re.escape(TARGET_INPUT)}=([^\s'\";]+)", entry
                )
                self.assertTrue(
                    supplied,
                    f"the `{SYNTAX_CHECK_HOOK_ID}` hook supplies no "
                    f"`{TARGET_INPUT}`, so it fails on the play's templated `hosts:`",
                )
                self.assertEqual(
                    [sentinel],
                    sorted(set(supplied)),
                    f"the `{SYNTAX_CHECK_HOOK_ID}` hook compiles the play against "
                    f"{sorted(set(supplied))} where .ansible-lint uses "
                    f"`{sentinel}` -- the two tools must agree, or the "
                    "not-a-real-environment property holds of only one of them",
                )


# ==========================================================================
# iac-host-configuration / A Run Whose Target Group Resolves to No Host Refuses
# (ADDED)
# ==========================================================================


class TestARunWhoseTargetGroupResolvesToNoHostRefuses(unittest.TestCase):
    """ADDED requirement: A Run Whose Target Group Resolves to No Host Refuses --
    scenarios "A targeted environment resolves to no host" and "A run that
    resolves hosts is unaffected".

    Every assertion here reads the guard's SHAPE. That it actually refuses is
    not established by anything in this file, and has no home under any of this
    project's three test commands -- see this module's header, and the change's
    design.md Decision 10.
    """

    def setUp(self) -> None:
        self.plays = plays()
        self.assertTrue(self.plays, "ansible/playbooks/host-baseline.yml holds no play")
        self.guard = self.plays[0]

    def test_the_playbook_opens_with_a_play_that_runs_when_no_host_resolved(self) -> None:
        """SPECIFIED -- the run "SHALL fail ... before any task acts on a host",
        which requires a play that runs at all when the target group is empty.

        `pre_tasks` on the converge play cannot do this: they run on the hosts
        the play matched, so a play matching nothing runs none of them. The
        check has to be a play with a target of its own, and it has to be first
        -- a guard after the converge play guards nothing.
        """
        self.assertTrue(
            targets_localhost(self.guard),
            "the first play in ansible/playbooks/host-baseline.yml targets "
            f"{self.guard.get('hosts')!r} rather than localhost, so it does not run "
            "when the environment's group is empty -- and every role in the converge "
            "play is ahead of any check that follows it",
        )
        self.assertNotIn(
            self.guard,
            converge_plays(),
            "the first play both guards and converges, so its own check runs only on "
            "the hosts it already matched",
        )
        self.assertIs(
            False,
            self.guard.get("become", False),
            "the guard play declares `become:`, which it needs for nothing and which "
            "would have it act on a host before the check it exists to perform",
        )

    def test_the_guard_refuses_a_run_that_supplied_no_environment(self) -> None:
        """SPECIFIED -- Host Configuration Names the Environment It Targets,
        scenario "A run supplying no environment refuses": the run "SHALL fail
        before any task acts on a host"."""
        conditions = [
            condition
            for task in assert_tasks(self.guard)
            for condition in task_conditions(task)
        ]
        self.assertTrue(
            conditions,
            "the guard play carries no `assert` task with a `that:` condition, so it "
            "refuses nothing",
        )
        definedness = [
            condition
            for condition in conditions
            if TARGET_INPUT in condition and re.search(r"\b(is\s+defined|is\s+not\s+defined|is\s+undefined)\b", condition)
        ]
        self.assertTrue(
            definedness,
            "no condition in the guard play tests whether "
            f"`{TARGET_INPUT}` was supplied at all, so a run that named no "
            f"environment reaches the converge play: {conditions}",
        )

    def test_the_guard_refuses_a_target_group_that_holds_no_host(self) -> None:
        """SPECIFIED -- "A host-configuration run whose target group resolves to
        no host SHALL fail ... before any task acts on a host", and scenario "A
        targeted environment resolves to no host".

        The `| default([])` is asserted as part of it, and is load-bearing
        rather than stylistic: `keyed_groups` creates a group only when some
        host carries the label, so under one environment's credential another's
        key does not merely hold nothing -- it is absent, and indexing `groups`
        raises rather than returning nothing. A guard that raised instead of
        refusing would still fail the run, but not with the diagnostic the
        scenario obliges.
        """
        emptiness = [
            condition
            for task in assert_tasks(self.guard)
            for condition in task_conditions(task)
            if "groups" in condition and TARGET_INPUT in condition
        ]
        self.assertTrue(
            emptiness,
            "no condition in the guard play reads "
            f"`groups[{TARGET_INPUT}]`, so a run targeting an environment whose group "
            "is empty is skipped and exits 0",
        )
        for condition in emptiness:
            with self.subTest(condition=condition):
                self.assertRegex(
                    condition,
                    r"default\s*\(\s*\[\s*\]\s*\)",
                    "the guard reads the target group without `| default([])`, so an "
                    "environment whose group does not exist at all under the "
                    "credential in use raises instead of refusing by name",
                )

    def test_the_two_refusals_are_separate_tasks(self) -> None:
        """DERIVED -- design.md Decision 4 and tasks.md 2.1, which require "two
        separate `assert` tasks, so each failure says which thing was wrong". No
        scenario states it. A single compound assertion would still refuse both
        runs, and would report the same message for an unsupplied input as for
        an environment that resolved to nothing -- which are different mistakes
        with different repairs."""
        tasks = assert_tasks(self.guard)
        self.assertGreaterEqual(
            len(tasks),
            2,
            f"the guard play carries {len(tasks)} `assert` task(s); the two "
            "conditions it checks are different mistakes and need messages of their "
            "own",
        )
        compound = [
            task_conditions(task)
            for task in tasks
            if any(TARGET_INPUT in condition for condition in task_conditions(task))
            and any("groups" in condition for condition in task_conditions(task))
            and len(task_conditions(task)) > 1
        ]
        self.assertEqual(
            [],
            compound,
            "one `assert` task checks both the input and the group, so its message "
            f"cannot say which of the two failed: {compound}",
        )

    def test_each_guard_refusal_names_the_environment_in_its_diagnostic(self) -> None:
        """SPECIFIED -- "SHALL fail with a diagnostic naming the environment
        that resolved to nothing", and scenario "A targeted environment resolves
        to no host": the failure names "that environment".

        Naming it means rendering the run's own value, not printing the word:
        a `fail_msg` reading `{{ target_environment }}` names the environment,
        and one reading "the target environment" names nothing.
        """
        tasks = assert_tasks(self.guard)
        self.assertTrue(tasks, "the guard play carries no `assert` task")
        silent = []
        for index, task in enumerate(tasks):
            message = task_fail_message(task)
            if not message:
                silent.append(f"assert[{index}]: no fail_msg")
            elif TARGET_INPUT not in variables_referenced(message):
                silent.append(f"assert[{index}]: {message!r}")
        # The definedness check is exempt: an input that was never supplied has
        # no value to render, so its message names the INPUT rather than an
        # environment. It is exempted by what it asserts, not by its position.
        exempt = {
            index
            for index, task in enumerate(tasks)
            if any(
                re.search(r"\bis\s+(not\s+)?defined\b|\bis\s+undefined\b", condition)
                for condition in task_conditions(task)
            )
        }
        remaining = [
            entry
            for entry in silent
            if int(entry.split("[")[1].split("]")[0]) not in exempt
        ]
        self.assertEqual(
            [],
            remaining,
            "these guard refusals do not render the environment that resolved to "
            f"nothing, so the operator is not told which one it was: {remaining}",
        )

    def test_the_guard_adds_no_further_required_input_to_a_run_that_resolves_hosts(
        self,
    ) -> None:
        """SPECIFIED -- scenario "A run that resolves hosts is unaffected": "the
        check SHALL add no further required input to it".

        Read three ways, because a play can require an input by three different
        means: a variable its templates read, a `vars_prompt` that stops the run
        to ask, and a `vars_files` that must exist. `target_environment` is not a
        FURTHER input -- the other requirement already obliges the run to supply
        it -- and `groups` is Ansible's own inventory variable, which no run
        supplies.
        """
        self.assertTrue(
            targets_localhost(self.guard),
            "the first play does not target localhost, so there is no guard play and "
            "this read would run over the converge play instead -- reporting no "
            "further input for a check that does not exist",
        )
        self.assertNotIn(
            "vars_prompt",
            self.guard,
            "the guard play declares `vars_prompt`, which stops every run -- "
            "including one whose group resolves -- to ask for something",
        )
        self.assertNotIn(
            "vars_files",
            self.guard,
            "the guard play declares `vars_files`, which every run must then be able "
            "to read, whether or not its group resolves",
        )
        referenced = variables_referenced(self.guard) | condition_variables(
            [
                condition
                for task in assert_tasks(self.guard)
                for condition in task_conditions(task)
            ]
        )
        outside = sorted(referenced - GUARD_ALLOWED_NAMES)
        self.assertEqual(
            [],
            outside,
            "the guard play reads variables beyond the input the run already "
            f"supplies and Ansible's own `groups`: {outside}",
        )


# ==========================================================================
# The reads above, run against documents carrying the defects they name
# ==========================================================================


class TestTheseReadsDiscriminate(unittest.TestCase):
    """DERIVED -- no scenario states any of this.

    Several assertions above are GREEN on the tree as it stands, and a
    predicate that returned "no offence" unconditionally would satisfy every one
    of them while reading nothing. Each test here feeds the same predicate a
    document carrying the defect that predicate names, and requires it to be
    found -- so a later simplification that empties a predicate fails here
    rather than passing everywhere.

    Fixtures are strings and in-memory structures. Nothing here writes to the
    repository, spawns a process, or reaches the network.
    """

    def _source_from(self, name: str, text: str) -> InventorySource:
        """An `InventorySource` built from a document, without touching disk."""
        source = InventorySource.__new__(InventorySource)
        source.path = Path(name)
        source.relative = name
        document = yaml.safe_load(text) or {}
        source.document = document if isinstance(document, dict) else {}
        source.environment = None
        for suffix in (".hcloud.yml", ".hcloud.yaml"):
            if name.endswith(suffix):
                source.environment = name[: -len(suffix)] or None
                break
        source.plugin = source.document.get("plugin")
        source.keyed_groups = source.document.get("keyed_groups") or []
        token = None
        for option in TOKEN_OPTIONS:
            if option in source.document:
                token = source.document[option]
                break
        source.declares_token_option = token is not None
        source.credential = None
        if isinstance(token, str):
            match = ENV_LOOKUP.search(token) or BARE_TEMPLATE.search(token)
            if match:
                source.credential = match.group(1)
        return source

    def test_the_credential_read_finds_the_bare_fallback_and_the_silent_one(self) -> None:
        naming_it = self._source_from(
            "prod.hcloud.yml",
            "plugin: hetzner.hcloud.hcloud\n"
            "api_token: \"{{ lookup('ansible.builtin.env', 'HCLOUD_TOKEN') }}\"\n",
        )
        self.assertEqual(PLUGIN_FALLBACK_CREDENTIAL, naming_it.credential)
        silent = self._source_from(
            "prod.hcloud.yml", "plugin: hetzner.hcloud.hcloud\n"
        )
        self.assertFalse(silent.declares_token_option)
        self.assertIsNone(silent.credential)
        proper = self._source_from(
            "staging.hcloud.yml",
            "plugin: hetzner.hcloud.hcloud\n"
            "api_token: \"{{ lookup('env', 'HCLOUD_TOKEN_STAGING') }}\"\n",
        )
        self.assertEqual("HCLOUD_TOKEN_STAGING", proper.credential)
        self.assertEqual("staging", proper.environment)

    def test_the_environment_read_finds_a_source_naming_none(self) -> None:
        anonymous = self._source_from("hcloud.yml", "plugin: hetzner.hcloud.hcloud\n")
        self.assertIsNone(
            anonymous.environment,
            "`hcloud.yml` carries no environment prefix, and a read that resolved one "
            "for it would report the shared source this change replaces as compliant",
        )

    def test_the_normalised_comparison_finds_a_real_divergence(self) -> None:
        one = self._source_from(
            "prod.hcloud.yml",
            "plugin: hetzner.hcloud.hcloud\n"
            "api_token: \"{{ lookup('env', 'HCLOUD_TOKEN_PRODUCTION') }}\"\n"
            "keyed_groups:\n  - key: hcloud_labels.environment\n    separator: ''\n",
        )
        same = self._source_from(
            "staging.hcloud.yml",
            "plugin: hetzner.hcloud.hcloud\n"
            "api_token: \"{{ lookup('env', 'HCLOUD_TOKEN_STAGING') }}\"\n"
            "keyed_groups:\n  - key: hcloud_labels.environment\n    separator: ''\n",
        )
        self.assertEqual(
            one.normalised(),
            same.normalised(),
            "two sources differing only in their credential were read as differing",
        )
        drifted = self._source_from(
            "staging.hcloud.yml",
            "plugin: hetzner.hcloud.hcloud\n"
            "api_token: \"{{ lookup('env', 'HCLOUD_TOKEN_STAGING') }}\"\n"
            "keyed_groups:\n  - key: hcloud_labels.role\n    separator: ''\n",
        )
        self.assertNotEqual(
            one.normalised(),
            drifted.normalised(),
            "a source grouping by a different label was read as identical",
        )

    def test_the_label_grouping_read_finds_a_source_that_does_not_group(self) -> None:
        ungrouped = self._source_from(
            "staging.hcloud.yml", "plugin: hetzner.hcloud.hcloud\n"
        )
        self.assertFalse(ungrouped.groups_by_the_environment_label())
        grouped = self._source_from(
            "staging.hcloud.yml",
            "plugin: hetzner.hcloud.hcloud\n"
            "keyed_groups:\n  - key: hcloud_labels.environment\n    separator: ''\n",
        )
        self.assertTrue(grouped.groups_by_the_environment_label())

    def test_the_localhost_read_finds_a_play_that_targets_an_environment(self) -> None:
        self.assertTrue(targets_localhost({"hosts": "localhost"}))
        self.assertTrue(targets_localhost({"hosts": "127.0.0.1"}))
        self.assertFalse(targets_localhost({"hosts": "prod"}))
        self.assertFalse(targets_localhost({"hosts": "{{ target_environment }}"}))

    def test_the_variable_read_finds_a_further_input_and_ignores_filters(self) -> None:
        message = "{{ target_environment }} resolved to no host under {{ vault_password }}"
        self.assertEqual(
            {TARGET_INPUT, "vault_password"},
            variables_referenced(message),
            "a fail_msg reading a second variable was not reported as reading one",
        )
        filtered = "{{ groups[target_environment] | default([]) | length }}"
        self.assertEqual(
            {"groups", TARGET_INPUT},
            variables_referenced(filtered),
            "filter names were read as variables a run must supply",
        )
        quoted = "{{ 'ansible/inventory/group_vars/staging.yml' }}"
        self.assertEqual(
            set(),
            variables_referenced(quoted),
            "a quoted literal was read as a variable",
        )

    def test_the_condition_read_finds_the_names_a_bare_condition_uses(self) -> None:
        self.assertEqual(
            {TARGET_INPUT},
            condition_variables([f"{TARGET_INPUT} is defined"]),
        )
        self.assertEqual(
            {"groups", TARGET_INPUT},
            condition_variables(
                [f"groups[{TARGET_INPUT}] | default([]) | length > 0"]
            ),
        )

    def test_the_assert_reader_finds_tasks_under_either_module_name(self) -> None:
        play = {
            "hosts": "localhost",
            "tasks": [
                {"assert": {"that": ["a is defined"], "fail_msg": "one"}},
                {"ansible.builtin.assert": {"that": ["b | length > 0"], "fail_msg": "two"}},
                {"ansible.builtin.debug": {"msg": "not an assertion"}},
            ],
        }
        tasks = assert_tasks(play)
        self.assertEqual(2, len(tasks), "the reader missed an assert task, or found a debug")
        self.assertEqual(["a is defined"], task_conditions(tasks[0]))
        self.assertEqual("two", task_fail_message(tasks[1]))

    def test_the_host_enumeration_read_finds_a_committed_hosts_file(self) -> None:
        """Runs the walk's own logic over a fixture structure rather than over a
        temporary tree, so nothing is written anywhere."""
        static_inventory = yaml.safe_load(
            "all:\n  hosts:\n    main-server:\n      ansible_host: 203.0.113.10\n"
        )
        stack: list[object] = [static_inventory]
        found = False
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                if "hosts" in value or "ansible_host" in value:
                    found = True
                    break
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
        self.assertTrue(
            found,
            "the host-enumeration walk did not find a hosts file that enumerates a "
            "host, so the assertion built on it would pass over one",
        )


if __name__ == "__main__":
    unittest.main()
