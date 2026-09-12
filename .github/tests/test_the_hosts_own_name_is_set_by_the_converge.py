"""Static-assertion tests for the host's own name, and for the name it reports
to the private network, being set by the converge rather than inherited.

Derived from the delta specs of the OpenSpec change
`rename-the-stacks-and-their-resources`, before any implementation of that
change existed -- from those deltas at commit `b08a71e`, the commit holding the
approved plan. The path those deltas sit at is not written here: a change's
artifacts move when it is archived, and this repository's citation convention is
to name the change and the artifact in prose instead.

The requirement is `iac-host-configuration`'s *The Host's Own Name Is Set by the
Converge* (ADDED). Each class below names the scenario it traces to, and every
assertion is annotated SPECIFIED (it traces to SHALL text or to a scenario in a
delta spec) or DERIVED (it traces to that change's `design.md` or `tasks.md`
rather than to a scenario). See that change's `test-plan.md` for the
scenario-to-test mapping, the baseline, the scenarios deliberately left
uncovered, the obsolete-test candidates, and the interface assumptions this file
took.

Why these properties are here and not in Molecule
-------------------------------------------------
`AGENTS.md`'s "Testing" section splits the two: Molecule asserts what a role
DOES on a host, `.github/tests` asserts what a committed file SAYS, statically.
What the `hostname` role does to a host is asserted by its own two Molecule
scenarios, which this pass also writes. Three things are NOT reachable that way
and are asserted here instead:

  * The ORDER of the roles in `ansible/playbooks/host-baseline.yml`. Molecule
    runs one role against one container and never reads that play. The order is
    the single invariant standing between this change and the failure the plan's
    own review found -- a run that renames the host before pinning the reported
    name tells the private network a name nothing intends, for as long as the
    rest of the run takes -- and a comment is otherwise all that holds it. That
    file has been reordered before, and its own comments record two such moves.

  * The `tailscale` role's pin. That role has no Molecule scenario and this
    change adds none: a scenario would need a container running `tailscaled`
    and joining a real tailnet. The change's own tasks.md 5.5 records the
    substitution -- a static read here, plus the converge's play recap read by a
    human -- rather than leaving the gap to be discovered.

  * Where `company` is defined. A role's Molecule scenario supplies its own
    variables, so no scenario can establish that the repository holds this one
    in a single place, which is the property a second company's clone depends
    on.

`TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in
`test_ci_configuration.py` reads every module in this directory, so this file is
held to the no-network, no-credential, no-container, no-Terraform constraint by
that class. It is written to satisfy it: standard library, `yaml`, the sibling
helpers, and no spawned command at all.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable by name:
    python3 -m unittest \\
        test_the_hosts_own_name_is_set_by_the_converge\\
.TestTheReportedNameIsPinnedBeforeTheHostIsRenamed\\
.test_the_hostname_role_runs_after_the_role_that_pins_the_reported_name

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling imports below resolve.

What no assertion here establishes
----------------------------------
Not that the tailnet MACHINE name was renamed. That name is assigned at
registration, only the Tailscale interface changes it, and the change's own
tasks.md 10.1 and 10.2 make it an operator step confirmed by observation from a
second peer. The pin asserted below is a different field, and reading it as the
rename is the mistake the change's design.md decision 6 exists to prevent.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from test_ci_configuration import ROOT, roles_with_molecule_scenarios
from test_host_configuration_names_its_environment import converge_plays, plays

# --------------------------------------------------------------------------
# The names this change introduces
#
# DERIVED throughout: no scenario names a role or a variable. The role name
# comes from the change's tasks.md 5.1 and its design.md decision 7 ("The
# hostname is its own role, not a task inside `hardening`"); the variable name
# and the file holding it come from tasks.md 4.4 and 5.1.
# --------------------------------------------------------------------------

HOSTNAME_ROLE = "hostname"
TAILSCALE_ROLE = "tailscale"
COMPANY_VARIABLE = "company"
ALL_GROUP_VARS = "ansible/inventory/group_vars/all.yml"

ROLES_DIR = ROOT / "ansible" / "roles"
GROUP_VARS_DIR = ROOT / "ansible" / "inventory" / "group_vars"

# The identity the reported name is pinned to. SPECIFIED as to what it is --
# "the name the provisioning layer gives its server", which under this
# repository's inventory is the host's inventory identity -- and DERIVED as to
# the spelling `inventory_hostname`, which is that identity's name in Ansible
# and which tasks.md 5.3 states.
INVENTORY_IDENTITY = "inventory_hostname"

# The two surfaces the pin reaches, by the Tailscale CLI's own spelling.
JOIN_COMMAND = re.compile(r"tailscale\s+up\b")
SET_COMMAND = re.compile(r"tailscale\s+set\b")
HOSTNAME_FLAG = re.compile(r"--hostname[= ]")

# The loopback entry that answers for a host's own name on this distribution.
# DERIVED -- tasks.md 5.1a. The requirement states the obligation ("The host
# SHALL resolve its own name locally") without naming an address.
LOOPBACK_ENTRY = "127.0.1.1"
HOSTS_FILE = "/etc/hosts"

# The role's own fallback switch, and the two paths permitted to carry it.
# NOT DERIVED FROM ANY DELTA -- see `TestTheUnsafeWriteFallbackStaysOffOutsideTheScenariosThatNeedIt`,
# which says what it traces to instead.
UNSAFE_WRITES_VARIABLE = "hostname_unsafe_writes"
UNSAFE_WRITES_DEFAULTS = f"ansible/roles/{HOSTNAME_ROLE}/defaults/main.yml"
UNSAFE_WRITES_SCENARIO_ROOT = f"ansible/roles/{HOSTNAME_ROLE}/molecule/"

# An assignment of a variable at the head of a mapping entry, read as text.
# Text rather than a parsed document because the setting may sit in a role's
# defaults, a play's `vars:`, an inventory file or a task's own `vars:`, and a
# reader that understood only one of those shapes would report a tree clean
# because it had not looked at the place the value was set.
VARIABLE_ASSIGNMENT = re.compile(
    r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<value>.+?)\s*$"
)

# Values Ansible reads as true. Narrow on purpose: what is being looked for is
# a committed literal, not an expression, and an expression assigning this
# variable is itself something a reader should be made to look at.
TRUTHY = frozenset({"true", "yes", "on", "1"})


# --------------------------------------------------------------------------
# Reading the tree
#
# Each reader takes `root` so the discriminating class at the end of this file
# can point it at a tree built to falsify what it reads.
# --------------------------------------------------------------------------


def _base(root: Path | None) -> Path:
    return ROOT if root is None else root


def role_names_in_play(play: dict) -> list[str]:
    """The roles a play declares, in the order it declares them.

    Both spellings Ansible accepts: a bare string and a mapping carrying
    `role:`. A play mixing the two is ordinary and a reader seeing only one
    would report an order that is not the play's.
    """
    found = []
    for entry in play.get("roles") or []:
        if isinstance(entry, str):
            found.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("role"), str):
            found.append(entry["role"])
    return found


def baseline_role_order(root: Path | None = None) -> list[str]:
    order: list[str] = []
    for play in converge_plays(root):
        order.extend(role_names_in_play(play))
    return order


def role_task_text(role: str, root: Path | None = None) -> str:
    """Every task file a role carries, concatenated as text.

    Text rather than a parsed task list: what is asserted below is that a
    command line carries a flag, and a role is free to spell that command as a
    string, a list, or a `cmd:`.
    """
    base = _base(root) / "ansible" / "roles" / role / "tasks"
    if not base.is_dir():
        return ""
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(base.rglob("*.yml"))
    )


def role_tasks(role: str, root: Path | None = None) -> list:
    path = _base(root) / "ansible" / "roles" / role / "tasks" / "main.yml"
    if not path.is_file():
        return []
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, list) else []


def commands_in(role: str, pattern: re.Pattern, root: Path | None = None) -> list[str]:
    """Every line of a role's tasks matching a command pattern."""
    return [
        line.strip()
        for line in role_task_text(role, root).splitlines()
        if pattern.search(line) and not line.strip().startswith("#")
    ]


def role_default_variables(role: str, root: Path | None = None) -> set[str]:
    path = _base(root) / "ansible" / "roles" / role / "defaults" / "main.yml"
    if not path.is_file():
        return set()
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return set(document) if isinstance(document, dict) else set()


def yaml_files_under(directory: str, root: Path | None = None) -> list[Path]:
    """Every committed YAML file under a directory of the repository.

    Directories whose name begins with a dot are skipped: `.molecule-home/`
    inside a working tree holds Molecule's own ephemeral copies of the very
    scenarios being read, and reporting one of those as a second place the
    variable is set would be reporting the reader's own footprints.
    """
    base = _base(root) / directory
    if not base.is_dir():
        return []
    return sorted(
        path
        for path in base.rglob("*.y*ml")
        if path.is_file()
        # Relative to the repository, never absolute: this repository's own
        # working trees live under `.claude/worktrees/`, so a dot-check over the
        # absolute path excludes every file in the tree and the reader reports a
        # repository that sets nothing anywhere.
        and not any(part.startswith(".") for part in path.relative_to(_base(root)).parts)
    )


def variable_assignments(variable: str, root: Path | None = None) -> list[tuple[str, str]]:
    """Every place under `ansible/` that assigns a variable, as
    (repository-relative path, value as written).

    Comment lines are skipped; a line whose assignment sits inside a comment is
    prose about the variable rather than a setting of it, and this role's files
    carry several.
    """
    found: list[tuple[str, str]] = []
    for path in yaml_files_under("ansible", root):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#"):
                continue
            match = VARIABLE_ASSIGNMENT.match(line)
            if match and match.group("name") == variable:
                value = match.group("value").split("#", 1)[0].strip().strip("\"'")
                found.append((path.relative_to(_base(root)).as_posix(), value))
    return found


def unsafe_write_offences(root: Path | None = None) -> list[str]:
    """Every place that turns the role's fallback on outside the role's own
    Molecule scenarios."""
    return sorted(
        f"{path} -> {value}"
        for path, value in variable_assignments(UNSAFE_WRITES_VARIABLE, root)
        if value.lower() in TRUTHY and not path.startswith(UNSAFE_WRITES_SCENARIO_ROOT)
    )


def inventory_unsafe_write_offences(root: Path | None = None) -> list[str]:
    """Every inventory assignment of the fallback, at any value.

    Stricter than the reader above, and deliberately: under `ansible/inventory/`
    the value is not the point, because a setting of `false` there is one
    character from the setting that is not, in the one place whose variables
    reach every play a host runs.
    """
    return sorted(
        f"{path} -> {value}"
        for path, value in variable_assignments(UNSAFE_WRITES_VARIABLE, root)
        if path.startswith("ansible/inventory/")
    )


def group_vars_defining(variable: str, root: Path | None = None) -> list[str]:
    """Every `group_vars` file that assigns a variable, as a repository-relative
    path.

    A vaulted file parses as a string rather than a mapping and is reported as
    defining nothing, which is correct for what this is used for: the variable
    below is not a secret and is not vaulted.
    """
    base = _base(root) / "ansible" / "inventory" / "group_vars"
    if not base.is_dir():
        return []
    found = []
    for path in sorted(base.glob("*.yml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if isinstance(document, dict) and variable in document:
            found.append(path.relative_to(_base(root)).as_posix())
    return found


# --------------------------------------------------------------------------
# The order the two names are set in
# --------------------------------------------------------------------------


class TestTheReportedNameIsPinnedBeforeTheHostIsRenamed(unittest.TestCase):
    """ADDED requirement: The Host's Own Name Is Set by the Converge --
    scenario "The reported name is pinned before the host's own name changes",
    and the clause it traces to: "**Setting it explicitly SHALL precede changing
    the host's own name within a run**, because until it is set the reported
    name follows the host's own."

    This is the class the change's tasks.md 5.7 asks for, and the invariant the
    plan's own review found missing. The failure it guards is not a broken run:
    it is a window, however long the rest of the converge takes or fails in,
    during which the private network is told a name nothing intends.
    """

    def setUp(self) -> None:
        self.order = baseline_role_order()
        self.assertTrue(
            self.order,
            "no play in ansible/playbooks/host-baseline.yml declares `roles:`, so "
            "there is no order for these assertions to read",
        )

    def test_the_baseline_play_runs_the_role_that_sets_the_hosts_own_name(self) -> None:
        """SPECIFIED -- "A converge SHALL set the host's own name rather than
        leaving it as the host was first given one", and scenario "A host
        renamed in the provisioning layer answers to the new name after a
        converge". A role no play runs sets nothing."""
        self.assertIn(
            HOSTNAME_ROLE,
            self.order,
            f"ansible/playbooks/host-baseline.yml runs {self.order}, which does not "
            f"include `{HOSTNAME_ROLE}`. A host's name is set once, at creation, from "
            "the name the provisioning layer gave the server -- so a converge that does "
            "not set it leaves a host answering to a name no committed file states, and "
            "nothing fails",
        )

    def test_the_baseline_play_still_runs_the_role_that_pins_the_reported_name(self) -> None:
        """DERIVED -- the precondition the ordering assertion needs. No scenario
        states that this play runs `tailscale`; it does, and an assertion about
        two roles' relative order is vacuous if either is absent."""
        self.assertIn(
            TAILSCALE_ROLE,
            self.order,
            f"ansible/playbooks/host-baseline.yml runs {self.order}, which does not "
            f"include `{TAILSCALE_ROLE}` -- so the ordering assertion below would "
            "compare one position against nothing",
        )

    def test_the_hostname_role_runs_after_the_role_that_pins_the_reported_name(self) -> None:
        """SPECIFIED -- the clause above, and scenario "The reported name is
        pinned before the host's own name changes": "the pin SHALL be applied
        first, so that no part of the run leaves the reported name deriving from
        a host name this run has already changed".

        The message names the reason rather than the order, because a reader who
        meets this red has to know why the position is not free. An earlier
        draft of the change put the role first, on the reasoning that nothing
        depends on it; that reasoning was wrong, and it is the kind of claim
        that reads as obviously true.
        """
        self.test_the_baseline_play_runs_the_role_that_sets_the_hosts_own_name()
        self.test_the_baseline_play_still_runs_the_role_that_pins_the_reported_name()
        self.assertLess(
            self.order.index(TAILSCALE_ROLE),
            self.order.index(HOSTNAME_ROLE),
            f"ansible/playbooks/host-baseline.yml runs `{HOSTNAME_ROLE}` before "
            f"`{TAILSCALE_ROLE}`: {self.order}. The name the host reports to the private "
            "network follows the host's own name until the pin sets it explicitly, so "
            "renaming the host first tells the tailnet a name nothing intends -- for as "
            "long as the rest of the run takes, or fails in. Every unattended consumer, "
            "the converge and the platform deploy among them, resolves the host by that "
            "reported name",
        )


# --------------------------------------------------------------------------
# The pin itself
# --------------------------------------------------------------------------


class TestTheReportedNameIsPinnedRatherThanInherited(unittest.TestCase):
    """ADDED requirement: The Host's Own Name Is Set by the Converge --
    "**The name a host reports to the private network SHALL be set explicitly to
    the name the provisioning layer gives its server, and SHALL NOT be left to
    be inherited from the host's own name.**", and scenarios "The host's name
    carries the company and the reported name does not" and "A host already on
    the private network has its reported name corrected".

    `tailscale` has no Molecule scenario and this change adds none, so this
    static read plus the converge's own play recap is what stands in for one.
    That substitution is the change's tasks.md 5.5, recorded there rather than
    discovered here.
    """

    def test_the_join_pins_the_name_the_host_reports(self) -> None:
        """SPECIFIED -- the clause above. A join that supplies no name leaves
        the reported name following the OS hostname, which is the value this
        change is about to prefix with the company."""
        joins = commands_in(TAILSCALE_ROLE, JOIN_COMMAND)
        self.assertTrue(
            joins,
            f"the `{TAILSCALE_ROLE}` role never invokes `tailscale up`, so this read has "
            "no join to inspect",
        )
        unpinned = [line for line in joins if not HOSTNAME_FLAG.search(line)]
        self.assertEqual(
            [],
            unpinned,
            f"these joins supply no `--hostname`: {unpinned}. The reported name would "
            "then be inherited from the host's own name -- which this change prefixes "
            "with the company, making an identifier automation depends on a by-product "
            "of one that it does not",
        )

    def test_the_pinned_name_is_the_hosts_inventory_identity_and_carries_no_company(
        self,
    ) -> None:
        """SPECIFIED -- scenario "The host's name carries the company and the
        reported name does not": "its own name SHALL carry the operating company
        and its inventory identity, and the name it reports to the private
        network SHALL be its inventory identity alone".

        The two failures are separated: a pin reading something other than the
        inventory identity, and a pin that carries the company as well. The
        second is the one that looks right.
        """
        pinned = [
            line
            for line in commands_in(TAILSCALE_ROLE, HOSTNAME_FLAG)
            if JOIN_COMMAND.search(line) or SET_COMMAND.search(line)
        ]
        self.assertTrue(
            pinned,
            f"no command in the `{TAILSCALE_ROLE}` role supplies a `--hostname`, so this "
            "read has nothing to inspect",
        )
        for line in pinned:
            with self.subTest(command=line):
                self.assertIn(
                    INVENTORY_IDENTITY,
                    line,
                    f"{line!r} pins a reported name that is not the host's inventory "
                    "identity. That identity is the name the provisioning layer gave "
                    "the server, and it is what every unattended consumer resolves",
                )
                self.assertNotIn(
                    COMPANY_VARIABLE,
                    line,
                    f"{line!r} carries `{COMPANY_VARIABLE}` into the name the host "
                    "reports. The company's namespace is the workstation, which serves "
                    "more than one company; the private network belongs to one company "
                    "and holds every stack it owns, so the reported name is the "
                    "inventory identity alone",
                )

    def test_a_host_already_on_the_private_network_has_its_reported_name_corrected(
        self,
    ) -> None:
        """SPECIFIED -- scenario "A host already on the private network has its
        reported name corrected": the name "SHALL be set to its current
        inventory identity, rather than left deriving from whatever the host is
        called".

        The join alone does not satisfy this: it runs only when the host is not
        already connected, which the live host is. A separate `tailscale set`
        is what reaches a host that joined before this change.
        """
        self.assertTrue(
            commands_in(TAILSCALE_ROLE, SET_COMMAND),
            f"the `{TAILSCALE_ROLE}` role never invokes `tailscale set`. The join is "
            "guarded on the host not already being connected, so on every host that is "
            "already a member -- which is every host this change is about -- the pin "
            "would never run",
        )

    def test_the_correcting_task_reports_its_own_changed_state(self) -> None:
        """DERIVED -- tasks.md 5.3: the `set` task's "changed-state is read from
        the `tailscale_status_check` the role already registers rather than
        reported unconditionally". No scenario states it; what it buys is that a
        converge whose only effect was to re-assert an already-correct name does
        not report a change, which is what makes a play recap readable as
        evidence at all -- and the recap is what stands in for the Molecule
        scenario this role does not have."""
        text = role_task_text(TAILSCALE_ROLE)
        self.assertTrue(text, f"the `{TAILSCALE_ROLE}` role carries no task files")
        set_blocks = [
            block
            for block in re.split(r"\n(?=- name:)", text)
            if SET_COMMAND.search(block) and HOSTNAME_FLAG.search(block)
        ]
        self.assertTrue(
            set_blocks,
            "no task in the role both invokes `tailscale set` and supplies a "
            "`--hostname`, so this read has no task to inspect",
        )
        for block in set_blocks:
            with self.subTest(task=block.splitlines()[0].strip()):
                match = re.search(r"changed_when:\s*(.+)", block)
                self.assertIsNotNone(
                    match,
                    "the task correcting the reported name declares no `changed_when`, "
                    "so it reports a change on every converge and a play recap says "
                    "nothing about whether the name needed correcting",
                )
                self.assertNotEqual(
                    "true",
                    match.group(1).strip().lower(),
                    "the task correcting the reported name reports a change "
                    "unconditionally. Its changed-state is readable from the status the "
                    "role already registers",
                )


# --------------------------------------------------------------------------
# Where the company is named
# --------------------------------------------------------------------------


class TestTheCompanyIsHeldInOnePlace(unittest.TestCase):
    """ADDED requirement: The Host's Own Name Is Set by the Converge -- "that
    variable SHALL be held in one place, applying to every host, so that a clone
    of this repository operated by a different company changes it once", and
    "It is a required input ...: it has no safe default"."""

    def test_the_company_is_defined_for_every_host_in_one_file(self) -> None:
        """SPECIFIED -- the clause above. DERIVED as to which file: tasks.md 4.4
        creates `ansible/inventory/group_vars/all.yml`, which is Ansible's own
        name for variables applying to every host."""
        defining = group_vars_defining(COMPANY_VARIABLE)
        self.assertEqual(
            [ALL_GROUP_VARS],
            defining,
            f"`{COMPANY_VARIABLE}` is defined in {defining or 'no group_vars file'}, "
            f"rather than in {ALL_GROUP_VARS} alone. Held in one place it is the single "
            "variable a second company's clone changes; held per environment it is a "
            "value that can disagree with itself, and the disagreement is a host name",
        )

    def test_no_role_gives_the_company_a_default(self) -> None:
        """SPECIFIED -- "it has no safe default, and a converge that cannot
        resolve it SHALL fail by name rather than converge a host under a name
        assembled from a blank". A default in the role's own `defaults/` is
        exactly such a blank: it resolves, so nothing refuses."""
        if not ROLES_DIR.is_dir():
            self.fail("ansible/roles/ does not exist, so this read has nothing to scan")
        offenders = sorted(
            role.name
            for role in ROLES_DIR.iterdir()
            if role.is_dir() and COMPANY_VARIABLE in role_default_variables(role.name)
        )
        self.assertEqual(
            [],
            offenders,
            f"these roles give `{COMPANY_VARIABLE}` a default: {offenders}. A default "
            "makes the company a property of what the operator forgot rather than of "
            "what they asked for, and the host is then named for whoever wrote the role",
        )


class TestTheHostnameRoleRefusesAndResolves(unittest.TestCase):
    """ADDED requirement: The Host's Own Name Is Set by the Converge --
    scenarios "An absent company variable refuses" and "The host resolves the
    name it was just given".

    Both scenarios' BEHAVIOUR is asserted by this role's two Molecule scenarios,
    which this pass also writes. What is asserted here is the shape those
    scenarios cannot establish over the committed file: that the check is the
    role's FIRST task, which a Molecule run establishes only for the tasks that
    happen to precede the one it observes, and that the loopback entry is the
    same role's concern rather than a second one's.
    """

    def setUp(self) -> None:
        self.tasks = role_tasks(HOSTNAME_ROLE)
        self.assertTrue(
            self.tasks,
            f"ansible/roles/{HOSTNAME_ROLE}/tasks/main.yml does not exist or declares no "
            "task, so every assertion in this class would read nothing. The role is what "
            "this change adds",
        )

    def test_the_check_is_the_roles_first_task(self) -> None:
        """SPECIFIED -- "a converge that cannot resolve it SHALL fail by name
        ... before any task acts on the host", which at role scope means
        literally first: this role has no `meta/main.yml` to run anything ahead
        of it."""
        first = self.tasks[0]
        self.assertTrue(
            isinstance(first, dict)
            and any(key in first for key in ("assert", "ansible.builtin.assert")),
            f"the `{HOSTNAME_ROLE}` role's first task is "
            f"{first.get('name') if isinstance(first, dict) else first!r}, not an "
            f"assert -- a task acting on the host runs before `{COMPANY_VARIABLE}` is "
            "checked",
        )

    def test_the_check_names_the_variable_and_where_it_is_set(self) -> None:
        """SPECIFIED -- "SHALL fail with a diagnostic naming that variable and
        where it is expected to be set". DERIVED as to the path named: the file
        tasks.md 4.4 creates. The full literal is asserted rather than a
        `group_vars/` substring, which would also match an environment's file --
        the wrong answer for a variable a clone changes once."""
        first = self.tasks[0]
        rendered = yaml.safe_dump(first)
        self.assertIn(
            COMPANY_VARIABLE,
            rendered,
            f"the `{HOSTNAME_ROLE}` role's first task does not name "
            f"`{COMPANY_VARIABLE}`",
        )
        self.assertIn(
            ALL_GROUP_VARS,
            rendered,
            f"the `{HOSTNAME_ROLE}` role's check does not name {ALL_GROUP_VARS}, so an "
            "operator meeting the refusal is told which input was not supplied but not "
            "how to supply it",
        )

    def test_the_role_sets_the_loopback_entry_as_well_as_the_name(self) -> None:
        """SPECIFIED -- "**The host SHALL resolve its own name locally**, and
        the converge SHALL make it do so as part of setting that name rather
        than leaving the two to be set by different mechanisms".

        DERIVED as to the two literals: `/etc/hosts` and `127.0.1.1` are this
        distribution's mechanism, which tasks.md 5.1a names. The symptom of
        omitting this is not a failure but a warning on every privileged command
        thereafter -- which is exactly why it would survive.
        """
        text = role_task_text(HOSTNAME_ROLE)
        for literal in (HOSTS_FILE, LOOPBACK_ENTRY):
            with self.subTest(literal=literal):
                self.assertIn(
                    literal,
                    text,
                    f"the `{HOSTNAME_ROLE}` role never names {literal}. Setting a host's "
                    "name does not by itself make it resolvable -- the loopback entry "
                    "that answers for it is a separate file -- and a name a host cannot "
                    "resolve is a name only half set",
                )


class TestTheNewRoleIsCoveredByTheSuiteThatRunsRoles(unittest.TestCase):
    """ADDED requirement: The Host's Own Name Is Set by the Converge, read
    through `iac-cicd-pipeline`'s *Ansible Configuration Is Verified in
    Continuous Integration and Gates the Merge* -- the change's tasks.md 5.6
    asks that the new role be covered by the Molecule matrix "rather than
    silently outside it".

    Role discovery in `ansible-verify.yml` enumerates rather than names, so
    coverage follows from the role carrying scenarios at all. That is what this
    asserts; the scenarios' own image pins and instance naming are asserted for
    every role by `test_ci_configuration.py`, and are not restated here.
    """

    def test_the_hostname_role_carries_molecule_scenarios(self) -> None:
        """DERIVED -- tasks.md 5.4 and 5.6. No scenario states that a role
        carries a Molecule scenario; what the specification obliges is the
        behaviour, and this repository's own answer to "what observes a role's
        behaviour" is Molecule."""
        self.assertIn(
            HOSTNAME_ROLE,
            roles_with_molecule_scenarios(),
            f"the `{HOSTNAME_ROLE}` role carries no `molecule/` directory, so the "
            "matrix that runs the roles a pull request owes runs nothing for it -- and "
            "what it does to a host is observed by nothing",
        )

    def test_the_role_carries_both_a_converging_and_a_refusing_scenario(self) -> None:
        """DERIVED -- tasks.md 5.4: "a `default` converging the name, and a
        scenario for the absent-`company` refusal". The pair is what the
        requirement's two halves need: a role that only refuses satisfies the
        refusal scenario and configures nothing."""
        base = ROLES_DIR / HOSTNAME_ROLE / "molecule"
        scenarios = sorted(entry.name for entry in base.iterdir()) if base.is_dir() else []
        self.assertIn(
            "default",
            scenarios,
            f"the `{HOSTNAME_ROLE}` role declares no `default` scenario: {scenarios}",
        )
        self.assertTrue(
            [name for name in scenarios if "absent" in name],
            f"the `{HOSTNAME_ROLE}` role declares no scenario for the absent-"
            f"`{COMPANY_VARIABLE}` refusal: {scenarios}",
        )


class TestTheUnsafeWriteFallbackStaysOffOutsideTheScenariosThatNeedIt(unittest.TestCase):
    """NOT DERIVED FROM ANY DELTA SCENARIO, and stated first so that nothing
    here is read as a requirement-derived assertion.

    This is a guard on an implementation decision. No requirement in this
    change mentions `unsafe_writes`; the role acquired it because
    `/etc/hostname` and `/etc/hosts` are bind mounts inside a container and the
    rename an atomic write ends with fails over one with `EBUSY`, so without a
    fallback the role could not be exercised by a scenario at all. It is
    asserted because the change's own code review found that a prose comment in
    `defaults/main.yml` was the only thing holding it, and this repository's
    conventions say a check replaces a comment wherever a check is possible.

    WHAT IS AT STAKE IN EACH DIRECTION, since the setting is load-bearing in
    both. Off, on a real host, the atomic write succeeds and the fallback is
    never consulted -- except where something is already wrong, a read-only
    `/etc` or a full filesystem being the cases. There, falling back means an
    interrupted in-place write can truncate `/etc/hosts` and leave a host that
    cannot resolve its own name: the exact condition the task writing that file
    exists to prevent, reached through the mechanism meant to prevent it. On,
    in this role's own scenarios, it is what makes the role runnable and
    therefore verified by anything at all.

    THE CASE THIS IS MOST FOR is not the default being flipped, which a diff
    shows plainly. It is a `group_vars` file, or a second role, setting the
    variable for a host: that reaches a real converge, and nothing else in this
    repository would notice.
    """

    def test_the_role_defaults_the_fallback_off(self) -> None:
        """DERIVED -- the role's own `defaults/main.yml` and the code review
        that asked for this check. The value is read as a literal `false`
        rather than as anything Ansible would treat as false, because what a
        reviewer has to be able to see at a glance is the word."""
        assignments = dict(variable_assignments(UNSAFE_WRITES_VARIABLE))
        self.assertIn(
            UNSAFE_WRITES_DEFAULTS,
            assignments,
            f"{UNSAFE_WRITES_DEFAULTS} does not declare `{UNSAFE_WRITES_VARIABLE}`. "
            "Undeclared, the role's tasks reference an undefined variable and the "
            "setting's value becomes whatever a caller last happened to leave in scope",
        )
        self.assertEqual(
            "false",
            assignments[UNSAFE_WRITES_DEFAULTS].lower(),
            f"{UNSAFE_WRITES_DEFAULTS} defaults `{UNSAFE_WRITES_VARIABLE}` to "
            f"{assignments[UNSAFE_WRITES_DEFAULTS]!r}. On a real host the atomic write "
            "succeeds and this fallback is consulted only where something is already "
            "wrong -- and there, an interrupted in-place write can truncate /etc/hosts "
            "and leave a host that cannot resolve its own name",
        )

    def test_only_this_roles_own_scenarios_turn_the_fallback_on(self) -> None:
        """DERIVED -- the same. The offence is stated over the whole of
        `ansible/`, not over `group_vars` alone: a play, a second role's
        defaults or a task's own `vars:` would reach a real converge by exactly
        the same route."""
        offenders = unsafe_write_offences()
        self.assertEqual(
            [],
            offenders,
            f"these files turn `{UNSAFE_WRITES_VARIABLE}` on outside this role's own "
            f"Molecule scenarios: {offenders}. A setting that reaches a real converge "
            "arms the non-atomic write on a host whose atomic write would have "
            "succeeded, and the failure it enables -- a truncated /etc/hosts -- is the "
            "one the task writing that file exists to prevent",
        )

    def test_no_inventory_variable_sets_the_fallback_at_all(self) -> None:
        """DERIVED -- the case the code review most wanted caught, asserted
        separately and more strictly than the one above: under `ansible/
        inventory/` the offence is the assignment, whatever its value.

        Stricter because the value there is not the point. An inventory setting
        it `false` is redundant with the role's own default and is the edit one
        character away from the setting that is not, in the one place in this
        repository whose variables reach every play a host runs.
        """
        offenders = inventory_unsafe_write_offences()
        self.assertEqual(
            [],
            offenders,
            f"these inventory files assign `{UNSAFE_WRITES_VARIABLE}`: {offenders}. "
            "The setting belongs to the role that consumes it and to the scenarios that "
            "need it overridden -- not to a host's variables, where it would apply to "
            "every converge that host ever runs",
        )

    def test_the_permitted_override_is_actually_present(self) -> None:
        """DERIVED, and it is what makes the three assertions above
        non-vacuous. Each of them is a negative read: over a repository where
        the variable existed nowhere, or where no scenario overrode it, all
        three would pass having found nothing. This is the positive control --
        the override exists, in this role's own scenario, which is the only
        place it is permitted."""
        permitted = sorted(
            path
            for path, value in variable_assignments(UNSAFE_WRITES_VARIABLE)
            if value.lower() in TRUTHY and path.startswith(UNSAFE_WRITES_SCENARIO_ROOT)
        )
        self.assertTrue(
            permitted,
            f"no scenario under {UNSAFE_WRITES_SCENARIO_ROOT} turns "
            f"`{UNSAFE_WRITES_VARIABLE}` on, so the assertions above would pass over a "
            "repository in which the setting had been removed entirely -- and the role "
            "would then be exercisable by no scenario at all, because neither "
            "/etc/hostname nor /etc/hosts can be written atomically in a container",
        )


# --------------------------------------------------------------------------
# The reads above are reads
# --------------------------------------------------------------------------


class TestTheseReadsDiscriminate(unittest.TestCase):
    """Every read in this file is a static read of a committed file, so a green
    run establishes nothing on its own: a reader that returned the expected
    value whatever it was given would satisfy every assertion above. Each test
    below points one reader at material this test supplies.
    """

    def _tree(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="host-name-reads-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        return directory

    def _play(self, tree: Path, body: str) -> None:
        playbooks = tree / "ansible" / "playbooks"
        playbooks.mkdir(parents=True, exist_ok=True)
        (playbooks / "host-baseline.yml").write_text(body, encoding="utf-8")

    def test_the_role_order_reader_reads_both_spellings_in_order(self) -> None:
        tree = self._tree()
        self._play(
            tree,
            "---\n"
            "- name: Converge\n"
            "  hosts: all\n"
            "  roles:\n"
            "    - docker\n"
            "    - role: tailscale\n"
            "    - role: hostname\n",
        )
        self.assertEqual(
            ["docker", "tailscale", "hostname"],
            baseline_role_order(tree),
            "the role-order reader either dropped a spelling it does not recognise -- "
            "which would report an order that is not the play's -- or reordered them",
        )

    def test_the_role_order_reader_reports_the_wrong_order_as_wrong(self) -> None:
        tree = self._tree()
        self._play(
            tree,
            "---\n"
            "- name: Converge\n"
            "  hosts: all\n"
            "  roles:\n"
            "    - role: hostname\n"
            "    - role: tailscale\n",
        )
        order = baseline_role_order(tree)
        self.assertLess(
            order.index(HOSTNAME_ROLE),
            order.index(TAILSCALE_ROLE),
            "the reader did not report the order the play declares, so the assertion "
            "that reads it could not fail on the arrangement this change forbids",
        )

    def test_the_role_order_reader_ignores_a_play_declaring_no_roles(self) -> None:
        """The guard play in this repository's own baseline declares `tasks:`
        and no `roles:`; a reader counting it would report a position for a play
        that runs no role."""
        tree = self._tree()
        self._play(
            tree,
            "---\n"
            "- name: Guard\n"
            "  hosts: localhost\n"
            "  tasks:\n"
            "    - name: Refuse\n"
            "      ansible.builtin.assert:\n"
            "        that: [true]\n"
            "- name: Converge\n"
            "  hosts: all\n"
            "  roles:\n"
            "    - role: tailscale\n",
        )
        self.assertEqual(["tailscale"], baseline_role_order(tree))
        self.assertEqual(2, len(plays(tree)), "the play reader lost a play")

    def test_the_command_reader_finds_a_flag_and_reports_its_absence(self) -> None:
        tree = self._tree()
        tasks = tree / "ansible" / "roles" / TAILSCALE_ROLE / "tasks"
        tasks.mkdir(parents=True)
        (tasks / "main.yml").write_text(
            "---\n"
            "- name: Bring the host onto the tailnet\n"
            '  ansible.builtin.command: "tailscale up --authkey={{ key }}"\n'
            "  changed_when: true\n",
            encoding="utf-8",
        )
        joins = commands_in(TAILSCALE_ROLE, JOIN_COMMAND, tree)
        self.assertEqual(1, len(joins), f"the command reader found {joins}")
        self.assertEqual(
            [],
            [line for line in joins if HOSTNAME_FLAG.search(line)],
            "the reader reported a `--hostname` in a command that carries none, so the "
            "assertion reading it could not fail on an unpinned join",
        )

        (tasks / "main.yml").write_text(
            "---\n"
            "- name: Bring the host onto the tailnet\n"
            '  ansible.builtin.command: >-\n'
            '    tailscale up --authkey={{ key }} --hostname={{ inventory_hostname }}\n'
            "  changed_when: true\n",
            encoding="utf-8",
        )
        pinned = commands_in(TAILSCALE_ROLE, JOIN_COMMAND, tree)
        self.assertTrue(
            pinned and HOSTNAME_FLAG.search(pinned[0]),
            f"the reader did not see a `--hostname` the command carries: {pinned}",
        )

    def test_the_group_vars_reader_reports_which_file_defines_a_variable(self) -> None:
        tree = self._tree()
        base = tree / "ansible" / "inventory" / "group_vars"
        base.mkdir(parents=True)
        (base / "all.yml").write_text(f"{COMPANY_VARIABLE}: somebody\n", encoding="utf-8")
        (base / "production.yml").write_text("some_other: value\n", encoding="utf-8")
        self.assertEqual([ALL_GROUP_VARS], group_vars_defining(COMPANY_VARIABLE, tree))

        (base / "production.yml").write_text(
            f"{COMPANY_VARIABLE}: somebody-else\n", encoding="utf-8"
        )
        self.assertEqual(
            [ALL_GROUP_VARS, "ansible/inventory/group_vars/production.yml"],
            group_vars_defining(COMPANY_VARIABLE, tree),
            "the reader did not report a second file defining the variable, so the "
            "assertion reading it could not fail on the value disagreeing with itself",
        )

    def test_the_assignment_reader_reports_where_and_what_is_set(self) -> None:
        """The reader behind the `unsafe_writes` guard, pointed at a tree that
        sets the variable in three places and at three values -- including the
        `group_vars` setting that guard exists for, which no committed file in
        this repository carries."""
        tree = self._tree()
        defaults = tree / "ansible" / "roles" / HOSTNAME_ROLE / "defaults"
        scenario = tree / "ansible" / "roles" / HOSTNAME_ROLE / "molecule" / "default"
        group_vars = tree / "ansible" / "inventory" / "group_vars"
        for directory in (defaults, scenario, group_vars):
            directory.mkdir(parents=True)
        (defaults / "main.yml").write_text(
            f"# {UNSAFE_WRITES_VARIABLE}: true   <- prose, not a setting\n"
            f"{UNSAFE_WRITES_VARIABLE}: false\n",
            encoding="utf-8",
        )
        (scenario / "converge.yml").write_text(
            f"    {UNSAFE_WRITES_VARIABLE}: true\n", encoding="utf-8"
        )
        (group_vars / "production.yml").write_text(
            f"{UNSAFE_WRITES_VARIABLE}: yes\n", encoding="utf-8"
        )
        self.assertEqual(
            [
                (f"ansible/inventory/group_vars/production.yml", "yes"),
                (f"ansible/roles/{HOSTNAME_ROLE}/defaults/main.yml", "false"),
                (f"ansible/roles/{HOSTNAME_ROLE}/molecule/default/converge.yml", "true"),
            ],
            sorted(variable_assignments(UNSAFE_WRITES_VARIABLE, tree)),
            "the assignment reader either missed a place the variable is set -- the "
            "`group_vars` one being what the guard exists for -- or read the commented "
            "line as a setting, which would report an offence the tree does not commit",
        )

    def test_the_fallback_guard_reports_a_tree_that_arms_it(self) -> None:
        """The guard itself, over a tree carrying each offence it exists for:
        a `group_vars` file arming the fallback for every play a host runs, and
        a second role arming it for its own. Neither shape exists in this
        repository, which is why the guard's green run over the real tree
        establishes nothing without this.
        """
        tree = self._tree()
        group_vars = tree / "ansible" / "inventory" / "group_vars"
        other_role = tree / "ansible" / "roles" / "somewhere_else" / "defaults"
        scenario = tree / "ansible" / "roles" / HOSTNAME_ROLE / "molecule" / "default"
        for directory in (group_vars, other_role, scenario):
            directory.mkdir(parents=True)
        (scenario / "converge.yml").write_text(
            f"    {UNSAFE_WRITES_VARIABLE}: true\n", encoding="utf-8"
        )
        self.assertEqual(
            [],
            unsafe_write_offences(tree),
            "the guard reported the role's own scenario, which is the one place the "
            "override is permitted -- a guard that refused it would make the role "
            "exercisable by nothing",
        )

        (group_vars / "production.yml").write_text(
            f"{UNSAFE_WRITES_VARIABLE}: true\n", encoding="utf-8"
        )
        (other_role / "main.yml").write_text(
            f"{UNSAFE_WRITES_VARIABLE}: yes\n", encoding="utf-8"
        )
        self.assertEqual(
            [
                "ansible/inventory/group_vars/production.yml -> true",
                "ansible/roles/somewhere_else/defaults/main.yml -> yes",
            ],
            unsafe_write_offences(tree),
            "the guard did not report a tree that arms the non-atomic write for a real "
            "converge, so its green run over this repository says nothing",
        )

    def test_the_inventory_guard_reports_an_assignment_at_any_value(self) -> None:
        """The stricter of the two, over the value that would otherwise read as
        harmless: an inventory setting the fallback OFF is redundant with the
        role's own default and is the edit one character away from the setting
        that is not."""
        tree = self._tree()
        group_vars = tree / "ansible" / "inventory" / "group_vars"
        group_vars.mkdir(parents=True)
        self.assertEqual([], inventory_unsafe_write_offences(tree))
        (group_vars / "production.yml").write_text(
            f"{UNSAFE_WRITES_VARIABLE}: false\n", encoding="utf-8"
        )
        self.assertEqual(
            ["ansible/inventory/group_vars/production.yml -> false"],
            inventory_unsafe_write_offences(tree),
            "the inventory guard read the value rather than the assignment, so it would "
            "admit the setting whose only defect is where it is",
        )

    def test_the_assignment_reader_ignores_a_similarly_named_variable(self) -> None:
        """A prefix match would report `hostname_unsafe_writes_reason` as the
        setting itself, and a substring match would report any line mentioning
        it."""
        tree = self._tree()
        defaults = tree / "ansible" / "roles" / HOSTNAME_ROLE / "defaults"
        defaults.mkdir(parents=True)
        (defaults / "main.yml").write_text(
            f"{UNSAFE_WRITES_VARIABLE}_reason: bind mounts\n"
            f"other: \"{UNSAFE_WRITES_VARIABLE}: true\"\n",
            encoding="utf-8",
        )
        self.assertEqual([], variable_assignments(UNSAFE_WRITES_VARIABLE, tree))

    def test_the_defaults_reader_reports_a_default_the_role_gives(self) -> None:
        tree = self._tree()
        defaults = tree / "ansible" / "roles" / HOSTNAME_ROLE / "defaults"
        defaults.mkdir(parents=True)
        (defaults / "main.yml").write_text(f"{COMPANY_VARIABLE}: acme\n", encoding="utf-8")
        self.assertIn(COMPANY_VARIABLE, role_default_variables(HOSTNAME_ROLE, tree))
        (defaults / "main.yml").write_text("hostname_use: systemd\n", encoding="utf-8")
        self.assertNotIn(COMPANY_VARIABLE, role_default_variables(HOSTNAME_ROLE, tree))


if __name__ == "__main__":
    unittest.main()
