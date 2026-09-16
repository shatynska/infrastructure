"""Static-assertion tests for making a shared-instance reset visible to its
applications.

Derived from the delta specifications of the OpenSpec change
`make-a-shared-instance-reset-visible-to-its-applications`, before any
implementation of that change existed. The path those deltas sit at is not
written here: a change's artifacts move when it is archived, and this
repository's citation convention is to name the change and the artifact in prose
instead.

The change adds two requirements to `openspec/specs/iac-host-configuration/
spec.md` -- *An Application Can Probe Its Own Database Through a Read-Only
Forced Command* and *The Host Carries an Operator-Declared Maintenance Window
for the Shared Instance* -- and one to `openspec/specs/iac-platform-services/
spec.md`, *A Destructive Window on the Shared Instance Is Announced to the
Applications That Hold Databases in It*.

WHAT LANDS HERE RATHER THAN IN MOLECULE
---------------------------------------
Most of those requirements are about what a probe ANSWERS, which is behaviour on
a host and belongs to `ansible/roles/deploy_user/molecule/probe-and-window/`
(AGENTS.md, "Testing"). What lands here is every obligation that is a static
read of a committed file, and each is here because the behavioural half cannot
reach it:

1. The declaration's path is fixed and documented, and the role, the role's
   README and `platform/README.md`'s upgrade runbook name the SAME one. A
   Molecule scenario reads whichever path it was written with, so it is green
   against a role and a runbook that disagree -- and the disagreement is
   discovered by an operator typing the wrong path mid-window.
2. The declaration's directory is provisioned root-owned, group `docker`, mode
   0775. Molecule asserts the CONVERGED result; this asserts the committed
   declaration, so a host converged before an edit cannot mask it.
3. The probe's `sudoers` line is fully qualified and carries no wildcard, and
   the task writing it validates with `visudo`. The scenario asserts this of the
   applications it enumerates; a wildcard committed in the template is invisible
   to a fixture carrying one application per rule.
4. Every application's probe key is declared beside its deploy key, and the two
   are distinct. `ansible/inventory/host_vars/` is not read by any Molecule
   scenario at all -- and is explicitly excluded from the suite's own change
   detection -- so nothing else in this repository reads it.
5. The upgrade runbook raises the declaration before its first destructive step
   and withdraws it before re-provisioning. This is a procedure written for a
   human; its ordering is a property of the committed text and of nothing else.
6. The consumer contract is written down. The other half of this contract is
   held by a repository that cannot read this one's scripts before depending on
   them, so the contract existing in prose is what makes the announcement one an
   application can take up.
7. The probe scenario's PostgreSQL fixture is the image the shared stack pins.
   `app-probe` reads its client's image from the running container, so a fixture
   on another major exercises a client this repository never ships.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_a_shared_instance_reset_is_visible\\
        .TestTheWindowDeclarationHasOneFixedPath\\
        .test_the_role_provisions_the_declared_directory

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling import below resolve. Standard library plus
PyYAML -- no network, no credential, no container runtime, no Terraform binary,
and nothing here spawns a process at all.

WHAT NO ASSERTION HERE ESTABLISHES
----------------------------------
Nothing here runs a probe, converges a host, or reads a database. A green run
establishes that the COMMITTED FILES carry these shapes -- never that a probe
answered `absent` rather than `credential-refused`, which is the whole subject of
the change and is established in Molecule.

Nor does any assertion here read whether the runbook's prose is GOOD, only that
the two acts it must carry are present and in the right order relative to the
steps around them. Whether a reason is a good reason is a question for review.

PROVENANCE ANNOTATION
---------------------
Every assertion below is annotated SPECIFIED (it traces to SHALL text in a delta
requirement) or DERIVED (it traces to that change's design.md or tasks.md, or to
this authoring pass's own judgement), which is the convention
`test_ci_configuration.py` established and the modules beside it follow. That
change's `test-plan.md` carries the scenario-to-test map, the baseline, the
unresolved project questions and the cases deliberately left uncovered.

NOTHING IN THIS FILE EDITS, DELETES OR DISABLES AN EXISTING TEST. Where a helper
a module beside this one already has is needed, it is imported rather than
restated.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from test_ci_configuration import (
    ROOT,
    compose_service_images,
    image_names_a_release,
    walked_files,
)

# --------------------------------------------------------------------------
# The identifiers this change fixes
# --------------------------------------------------------------------------

# SPECIFIED as to the directory: "Its location SHALL be a fixed, documented
# path", and the requirement's own prose names `/var/lib/platform-maintenance/`
# root-owned, group `docker`, mode 0775. DERIVED as to the file name inside it,
# which comes from that change's design.md decision 5. Both are written here
# because a check over "the fixed path" has to know which path that is; a check
# deriving it from whatever the role happens to say would agree with the role by
# construction and could never report the disagreement it exists to find.
WINDOW_DIRECTORY = "/var/lib/platform-maintenance"
WINDOW_DECLARATION = f"{WINDOW_DIRECTORY}/shared-postgres-window"

WINDOW_OWNER = "root"
WINDOW_GROUP = "docker"
WINDOW_MODE = "0775"

# The role that provisions all of this, and the two documents that must name the
# same path it does.
ROLE = "ansible/roles/deploy_user"
ROLE_README = f"{ROLE}/README.md"
PLATFORM_README = "platform/README.md"
ONBOARDING = "docs/onboard-an-application.md"
PLATFORM_COMPOSE = "platform/docker-compose.yml"
PROBE_SCENARIO = f"{ROLE}/molecule/probe-and-window"

# The files that enumerate the applications a host authorises. They are the
# HOST's own vars files, not an environment's `group_vars`: an entry there would
# authorise one key on every host in the environment, and an environment may
# hold two stacks of different tenants. See *A Host-Scoped Variable Lives in the
# Host's Own Vars File* (`openspec/specs/iac-host-configuration/spec.md`).
#
# This tuple named `group_vars` when these tests were derived, which is where
# `deploy_apps` lived then; `bound-a-deploy-key-to-one-host-when-an-environment-
# holds-two-stacks` moved it while this change was being implemented. Only the
# location changed here -- every assertion below is the one that was derived
# from the delta, and `declared_applications` still refuses a file that declares
# no `deploy_apps`, so pointing it at the wrong place cannot pass vacuously.
HOST_VARS = (
    "ansible/inventory/host_vars/main-staging.yml",
    "ansible/inventory/host_vars/main-production.yml",
)

# The six tokens, in the requirement's own precedence order.
TOKENS = (
    "window-open",
    "unreachable",
    "absent",
    "credential-refused",
    "empty",
    "populated",
)

# The two fields the input object is required to carry.
REQUIRED_INPUT_FIELDS = ("password", "table")

PRIVILEGED_SCRIPT = "/usr/local/bin/app-probe"
UNPRIVILEGED_SCRIPT = "/usr/local/bin/deploy-probe"
PROBE_SUDOERS_PREFIX = "/etc/sudoers.d/app-probe-"

# Any path under /var/lib that looks like a maintenance declaration. The point
# of the pattern is to find a path that DISAGREES with the one above -- a
# check looking only for the agreed path cannot see a second one.
MAINTENANCE_PATH = re.compile(r"/var/lib/[A-Za-z0-9_.-]*maintenance[A-Za-z0-9_./-]*")

YAML_SUFFIXES = (".yml", ".yaml")


# --------------------------------------------------------------------------
# Reading files that carry an Ansible Vault tag
# --------------------------------------------------------------------------


class _TolerantLoader(yaml.SafeLoader):
    """A loader that reads a document carrying tags it does not know.

    `ansible/inventory/group_vars/*.yml` carries `!vault` values, and
    `yaml.safe_load` raises on them. Nothing here reads a vaulted value -- what
    is read is the list of applications beside them -- so an unknown tag resolves
    to its own text rather than stopping the read.
    """


def _unknown_tag(loader: yaml.Loader, suffix: str, node: yaml.Node) -> object:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_TolerantLoader.add_multi_constructor("", _unknown_tag)


def load_tolerant_yaml(path: Path) -> object:
    """Parse a YAML file that may carry Vault tags, failing on an absent file.

    An absent file is a real failure and not a reason to skip: for a file this
    change is specified to edit, "it is not there" is a finding.
    """
    if not path.is_file():
        raise AssertionError(f"{path} does not exist")
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_TolerantLoader)


def _base(root: Path | None) -> Path:
    return ROOT if root is None else root


def _read(path: Path) -> str:
    """Read a file, failing the calling test if it is absent.

    Local rather than imported so that a check can be pointed at a fixture tree:
    the sibling helper reports an absent file by its path relative to the
    REPOSITORY root, which a scratch tree is not under.
    """
    if not path.is_file():
        raise AssertionError(f"{path} does not exist")
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# The enumeration: the role's own committed files
# --------------------------------------------------------------------------


def role_files(root: Path | None = None) -> list[Path]:
    """Every committed file under the role, EXCLUDING its Molecule scenarios.

    The scenarios are tests: they name the declaration's path and the probe's
    scripts because they exercise them, and counting them as the role's own
    content would let a scenario satisfy every check below on the role's behalf.
    """
    base = _base(root)
    directory = base / ROLE
    if not directory.is_dir():
        return []
    return [
        path
        for path in sorted(directory.rglob("*"))
        if path.is_file() and "molecule" not in path.relative_to(directory).parts
    ]


def role_yaml_files(root: Path | None = None) -> list[Path]:
    return [path for path in role_files(root) if path.suffix in YAML_SUFFIXES]


def _mappings(document: object):
    """Every mapping anywhere in a parsed YAML document.

    Walked rather than indexed, so that a task inside a `block:`, behind an
    `include_tasks:`, or written with any module at all is reached. What a check
    over an Ansible task needs is the module's own argument mapping, and that is
    a mapping wherever it sits.
    """
    if isinstance(document, dict):
        yield document
        for value in document.values():
            yield from _mappings(value)
    elif isinstance(document, list):
        for value in document:
            yield from _mappings(value)


def _normalised_mode(value: object) -> str:
    """A file mode as four octal digits, however the YAML spelled it.

    `mode: "0775"` is a string; `mode: 0775` is an integer under YAML 1.1's
    octal rule; anything else is returned as its own text so the failure names
    what was found.
    """
    if isinstance(value, int):
        return format(value, "04o")
    return str(value)


# --------------------------------------------------------------------------
# 1. The declaration's path is fixed, and three places name the same one
# --------------------------------------------------------------------------


def places_not_naming_the_declaration(root: Path | None = None) -> list[str]:
    """Report each place obliged to name the declaration that does not.

    The role must name the DIRECTORY, which is what it provisions. The role's
    README and the upgrade runbook must name the FILE, which is what an operator
    types -- a document naming only the directory leaves the operator to guess
    the rest of the path under time pressure, which is the whole reason the
    requirement fixes it.
    """
    base = _base(root)
    offenders = []
    if not any(WINDOW_DIRECTORY in path.read_text(encoding="utf-8", errors="ignore") for path in role_files(base)):
        offenders.append(
            f"no committed file under {ROLE} (outside its Molecule scenarios) names "
            f"{WINDOW_DIRECTORY}, so nothing provisions the declaration's directory"
        )
    for document in (ROLE_README, PLATFORM_README):
        path = base / document
        if not path.is_file():
            offenders.append(f"{document} does not exist")
        elif WINDOW_DECLARATION not in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(f"{document} does not name {WINDOW_DECLARATION}")
    return offenders


def files_naming_a_disagreeing_declaration_path(root: Path | None = None) -> list[str]:
    """Report each committed file naming a maintenance path that is not the one
    this change fixes.

    The obligation is that ONE path is named everywhere, and a check looking only
    for the agreed path is blind to the case it exists for: a second path,
    spelled slightly differently, in one of the three places. `openspec/` is not
    walked, by `walked_files()`'s own pruning -- a specification quoting a path
    is prose about it, not a place an operator reads it from.
    """
    base = _base(root)
    offenders = []
    for path in walked_files(base):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            for found in MAINTENANCE_PATH.finditer(line):
                named = found.group(0).rstrip("/.,;:")
                if named != WINDOW_DIRECTORY and not named.startswith(WINDOW_DIRECTORY + "/"):
                    offenders.append(
                        f"{path.relative_to(base).as_posix()}:{line_number}: {named}"
                    )
    return sorted(set(offenders))


class TestTheWindowDeclarationHasOneFixedPath(unittest.TestCase):
    """ADDED requirement: The Host Carries an Operator-Declared Maintenance
    Window for the Shared Instance -- "Its location SHALL be a fixed, documented
    path, since an operator types it under time pressure and the runbook, the
    role's own documentation and the probe must name the same thing."
    """

    def test_the_role_the_role_readme_and_the_runbook_all_name_it(self) -> None:
        """SPECIFIED -- the clause above, read as the three places it names.

        Three files written by three different edits with nothing but a string
        between them. A Molecule scenario cannot catch a disagreement here: it
        reads whichever path it was itself written with, and stays green while
        the runbook an operator follows names another.
        """
        offenders = places_not_naming_the_declaration()
        self.assertEqual(
            [],
            offenders,
            f"the declaration's path is not named everywhere it must be: {offenders}",
        )

    def test_no_committed_file_names_a_different_maintenance_path(self) -> None:
        """SPECIFIED -- the same clause read the other way. One fixed path means
        no second one: a check that only looks for the agreed path reports green
        over a tree carrying both, which is exactly the state a partial rename
        leaves behind."""
        offenders = files_naming_a_disagreeing_declaration_path()
        self.assertEqual(
            [],
            offenders,
            f"these committed files name a maintenance path other than "
            f"{WINDOW_DIRECTORY}, so the declaration does not have one fixed location "
            f"after all: {offenders}",
        )


# --------------------------------------------------------------------------
# 2. The directory the declaration lives in
# --------------------------------------------------------------------------


def declared_window_directory_mappings(root: Path | None = None) -> list[tuple[str, dict]]:
    """Every module argument mapping in the role that provisions the
    declaration's directory, as (file, mapping)."""
    base = _base(root)
    found = []
    for path in role_yaml_files(base):
        try:
            document = yaml.load(path.read_text(encoding="utf-8"), Loader=_TolerantLoader)
        except yaml.YAMLError:
            continue
        for mapping in _mappings(document):
            target = mapping.get("path", mapping.get("dest"))
            if isinstance(target, str) and target.rstrip("/") == WINDOW_DIRECTORY:
                found.append((path.relative_to(base).as_posix(), mapping))
    return found


def window_directory_offences(root: Path | None = None) -> list[str]:
    """Report why the declaration's directory is not provisioned as required."""
    offenders = []
    for label, mapping in declared_window_directory_mappings(root):
        owner = mapping.get("owner")
        group = mapping.get("group")
        mode = _normalised_mode(mapping.get("mode"))
        if owner != WINDOW_OWNER:
            offenders.append(f"{label}: owner is {owner!r}, not {WINDOW_OWNER!r}")
        if group != WINDOW_GROUP:
            offenders.append(f"{label}: group is {group!r}, not {WINDOW_GROUP!r}")
        if mode != WINDOW_MODE:
            offenders.append(f"{label}: mode is {mode!r}, not {WINDOW_MODE!r}")
        if mapping.get("state") not in (None, "directory"):
            offenders.append(f"{label}: state is {mapping.get('state')!r}, not a directory")
    return offenders


class TestTheWindowDirectoryIsProvisionedForAnOperatorWithNoSudo(unittest.TestCase):
    """ADDED requirement: The Host Carries an Operator-Declared Maintenance
    Window for the Shared Instance -- "Ansible SHALL provision whatever the
    declaration is held in, so that it exists on a host before any window does,
    and so that an operator account -- which holds no `sudo` of any kind -- can
    raise and withdraw it with the capability it already has."
    """

    def test_the_role_provisions_the_declared_directory(self) -> None:
        """SPECIFIED -- the vacuity guard on the assertion below, which reports
        green over a role that provisions nothing at all. An absent role
        directory yields an empty enumeration and every offence check over it
        passes having read nothing."""
        declared = declared_window_directory_mappings()
        self.assertTrue(
            declared,
            f"no task in {ROLE} provisions {WINDOW_DIRECTORY}, so the assertion about "
            f"its ownership and mode would pass having read nothing -- and a host would "
            f"have nowhere for an operator to raise the declaration",
        )

    def test_it_is_root_owned_group_docker_and_group_writable(self) -> None:
        """SPECIFIED -- the clause above, together with the requirement that the
        declaration be raisable by an account holding no `sudo`.

        `0775` rather than `0770` is DERIVED, from that change's design.md
        decision 5: the directory is world-readable so that nothing about who may
        READ the declaration depends on group membership, while writing it stays
        with `docker`. Reconsider that deliberately rather than repairing it if
        the implementation narrows the mode on purpose.
        """
        offenders = window_directory_offences()
        self.assertEqual(
            [],
            offenders,
            f"{WINDOW_DIRECTORY} is not provisioned root-owned, group {WINDOW_GROUP}, "
            f"mode {WINDOW_MODE}: {offenders}. An operator account holds the `docker` "
            f"group and no `sudo` of any kind, so a directory the group cannot write is "
            f"one an operator cannot raise a window in without an escalation -- and an "
            f"operator in the middle of a window cannot wait on one",
        )


# --------------------------------------------------------------------------
# 3. The privileged half is reachable only through a fully-qualified rule
# --------------------------------------------------------------------------

SUDOERS_GRANT = re.compile(
    r"ALL\s*=\s*\((?P<runas>[^)]*)\)\s*(?:NOPASSWD\s*:)?\s*(?P<command>.+?)\s*$"
)


def probe_sudoers_lines(root: Path | None = None) -> list[tuple[str, int, str]]:
    """Every committed line in the role granting `sudo` on the privileged probe
    script, as (file, line number, line).

    Found by reading the role's files as text rather than by knowing where the
    rule is written. A rule rendered from a template, from an inline `content:`,
    or from a file under `files/` is the same rule, and a check that knew only
    one of those shapes would report a clean tree for the other two.
    """
    base = _base(root)
    found = []
    for path in role_files(base):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "app-probe" in stripped and "ALL" in stripped and "=" in stripped:
                found.append((path.relative_to(base).as_posix(), number, stripped))
    return found


def probe_sudoers_offences(root: Path | None = None) -> list[str]:
    """Report each probe `sudoers` line that is not fully qualified to one
    application."""
    offenders = []
    for label, number, line in probe_sudoers_lines(root):
        match = SUDOERS_GRANT.search(line)
        if not match:
            offenders.append(f"{label}:{number}: not recognised as a sudoers grant: {line}")
            continue
        command = match.group("command")
        if "*" in command:
            offenders.append(f"{label}:{number}: the granted command carries a wildcard: {command}")
        if PRIVILEGED_SCRIPT not in command:
            offenders.append(
                f"{label}:{number}: the granted command does not name {PRIVILEGED_SCRIPT}: {command}"
            )
            continue
        argument = command.split(PRIVILEGED_SCRIPT, 1)[1].strip()
        if not argument:
            offenders.append(
                f"{label}:{number}: {PRIVILEGED_SCRIPT} is granted with NO argument, so any "
                f"application name would be accepted: {command}"
            )
    return offenders


def probe_sudoers_files_without_visudo_validation(root: Path | None = None) -> list[str]:
    """Report each task writing a probe `sudoers` file without validating it."""
    base = _base(root)
    offenders = []
    for path in role_yaml_files(base):
        try:
            document = yaml.load(path.read_text(encoding="utf-8"), Loader=_TolerantLoader)
        except yaml.YAMLError:
            continue
        for mapping in _mappings(document):
            target = mapping.get("dest", mapping.get("path"))
            if not isinstance(target, str) or PROBE_SUDOERS_PREFIX not in target:
                continue
            validate = str(mapping.get("validate", ""))
            if "visudo" not in validate:
                offenders.append(
                    f"{path.relative_to(base).as_posix()}: writes {target} with "
                    f"validate={validate!r}"
                )
    return offenders


class TestThePrivilegedHalfIsBoundToOneApplication(unittest.TestCase):
    """ADDED requirement: An Application Can Probe Its Own Database Through a
    Read-Only Forced Command -- "The application name SHALL reach `deploy-probe`
    and every privileged script it invokes only as the fixed argument its forced
    command carries and the fully-qualified `sudoers.d` rule that matches it,
    never as data supplied by the connecting client."
    """

    def test_the_role_grants_sudo_on_the_privileged_probe_script(self) -> None:
        """SPECIFIED -- the vacuity guard. Every offence check below reports
        green over a role that grants nothing, which is also the state of a role
        whose probe was never implemented; the difference matters, so it is
        asserted rather than inferred."""
        lines = probe_sudoers_lines()
        self.assertTrue(
            lines,
            f"no committed line under {ROLE} grants `sudo` on {PRIVILEGED_SCRIPT}, so the "
            f"unprivileged half cannot reach the privileged one, and every assertion about "
            f"the rule's shape would pass having read nothing",
        )

    def test_every_grant_is_fully_qualified_and_carries_no_wildcard(self) -> None:
        """SPECIFIED -- the clause above. A wildcard or an argument-forwarding
        form lets any application's probe key name any application, which
        collapses the second of the two independent layers this requirement binds
        the name with -- and the Molecule scenario cannot see it, because a
        fixture enumerating one application per rule renders a correct-looking
        rule from a wildcard template."""
        offenders = probe_sudoers_offences()
        self.assertEqual(
            [],
            offenders,
            f"these `sudoers` grants on {PRIVILEGED_SCRIPT} are not fully qualified to one "
            f"application: {offenders}",
        )

    def test_every_probe_sudoers_file_is_validated_before_it_lands(self) -> None:
        """DERIVED -- that change's tasks.md 3.8 ("fully qualified with no
        wildcard and `visudo`-validated"), not the delta's own text. A malformed
        file in `/etc/sudoers.d/` can break `sudo` for every account on the host,
        including the deploy path this change does not otherwise touch."""
        offenders = probe_sudoers_files_without_visudo_validation()
        self.assertEqual(
            [],
            offenders,
            f"these tasks write a file under {PROBE_SUDOERS_PREFIX}* without validating it "
            f"with `visudo`: {offenders}",
        )


# --------------------------------------------------------------------------
# 4. A probe key is declared beside its deploy key, and is a different key
# --------------------------------------------------------------------------

PUBLIC_KEY = re.compile(r"^(ssh-(ed25519|rsa)|ecdsa-sha2-\S+)\s+\S+")
PRIVATE_KEY_MARKER = "PRIVATE KEY"


def declared_applications(root: Path | None = None) -> list[tuple[str, dict]]:
    """Every `deploy_apps` entry in every committed host vars file, as
    (file, entry)."""
    base = _base(root)
    found = []
    for name in HOST_VARS:
        document = load_tolerant_yaml(base / name)
        entries = document.get("deploy_apps") if isinstance(document, dict) else None
        if not isinstance(entries, list) or not entries:
            raise AssertionError(
                f"{name} declares no `deploy_apps` list, so every assertion about the "
                f"applications enumerated in it would pass having read nothing"
            )
        for entry in entries:
            if isinstance(entry, dict):
                found.append((name, entry))
    return found


def probe_key_offences(root: Path | None = None) -> list[str]:
    """Report each `deploy_apps` entry whose probe key is missing, malformed, or
    not a key of its own."""
    offenders = []
    for name, entry in declared_applications(root):
        application = entry.get("name", "<unnamed>")
        label = f"{name}: {application}"
        deploy_key = entry.get("public_key")
        probe_key = entry.get("probe_public_key")
        if probe_key is None:
            offenders.append(f"{label} declares no probe_public_key")
            continue
        if not isinstance(deploy_key, str) or not PUBLIC_KEY.match(deploy_key.strip()):
            offenders.append(f"{label} declares a probe key without a usable deploy key")
            continue
        if not isinstance(probe_key, str) or not PUBLIC_KEY.match(probe_key.strip()):
            offenders.append(f"{label} declares a probe_public_key that is not a public key")
            continue
        if probe_key.strip() == deploy_key.strip():
            offenders.append(
                f"{label} declares the SAME key as both its deploy key and its probe key"
            )
        if PRIVATE_KEY_MARKER in probe_key or PRIVATE_KEY_MARKER in deploy_key:
            offenders.append(f"{label} carries private key material in version control")
    return offenders


class TestEveryProbeKeyIsDeclaredBesideItsDeployKeyAndIsADifferentKey(unittest.TestCase):
    """ADDED requirement: An Application Can Probe Its Own Database Through a
    Read-Only Forced Command -- "An application's probe public key SHALL be
    enumerated in version control alongside its deploy key, and the two SHALL be
    distinct keys: one `authorized_keys` entry carries one forced command, so a
    key that could do both would be a key bound to neither."
    """

    def test_every_enumerated_application_declares_a_distinct_probe_key(self) -> None:
        """SPECIFIED as to distinctness and to being enumerated beside the deploy
        key. DERIVED as to every entry having one at all: the requirement makes a
        probe key OPTIONAL per application, and it is that change's tasks.md 4.1
        that names both entries in both files as ones to be given a keypair. If a
        later decision leaves an application without one deliberately, reconsider
        this assertion rather than repairing it -- and say where the key is
        declared why, as tasks.md 4.1 requires of `platform`'s.

        Nothing else in this repository reads these files: they are excluded from
        the Molecule suite's own change detection, so a probe key mistyped into
        the deploy key's field would otherwise reach a host before anything
        noticed.
        """
        offenders = probe_key_offences()
        self.assertEqual(
            [],
            offenders,
            f"these enumerated applications do not carry a probe key declared beside a "
            f"deploy key it differs from: {offenders}",
        )


# --------------------------------------------------------------------------
# 5. The upgrade runbook's two new acts, and where they stand
# --------------------------------------------------------------------------

RUNBOOK_HEADING = "### Upgrading the PostgreSQL major version"

RAISE_ACT = re.compile(
    rf"\b(touch|install|tee)\b[^\n]*{re.escape(WINDOW_DECLARATION)}|>\s*{re.escape(WINDOW_DECLARATION)}"
)
WITHDRAW_ACT = re.compile(rf"\brm\b[^\n]*{re.escape(WINDOW_DECLARATION)}")
# The step that destroys the data. Either command ends the instance the window
# is declared over; the earlier of the two is the first destructive step.
DESTRUCTIVE_ACT = re.compile(
    r"docker\s+volume\s+rm\s+\S*postgres\S*|docker\s+rm\s+-f\s+platform-postgres-1"
)
# The step that re-provisions each application's database, which is what the
# withdrawal must precede.
REPROVISION_STEP = re.compile(r"rotate=yes|re-provision every application database")


def runbook_section(root: Path | None = None) -> str:
    """The upgrade runbook, from its own heading to the next top-level one."""
    text = _read(_base(root) / PLATFORM_README)
    start = text.find(RUNBOOK_HEADING)
    if start == -1:
        raise AssertionError(
            f"{PLATFORM_README} carries no section titled {RUNBOOK_HEADING!r}, so the "
            f"assertions about the procedure's ordering have nothing to read"
        )
    end = text.find("\n## ", start)
    return text[start:] if end == -1 else text[start:end]


def runbook_announcement_offences(root: Path | None = None) -> list[str]:
    """Report why the upgrade runbook does not declare and withdraw a window
    where it must.

    Read by POSITION within the section rather than by which numbered step the
    text happens to be under: a step renumbered, split or merged moves the
    numbering and moves nothing about what has to come before what.
    """
    section = runbook_section(root)
    raise_at = RAISE_ACT.search(section)
    withdraw_at = WITHDRAW_ACT.search(section)
    destructive_at = DESTRUCTIVE_ACT.search(section)
    reprovision_at = REPROVISION_STEP.search(section)

    offenders = []
    if destructive_at is None:
        offenders.append(
            "no step in the procedure was recognised as destroying the instance's data, "
            "so nothing here can say what the declaration must come before"
        )
    if reprovision_at is None:
        offenders.append(
            "no step in the procedure was recognised as re-provisioning the application "
            "databases, so nothing here can say what the withdrawal must come before"
        )
    if raise_at is None:
        offenders.append(
            f"the procedure carries no act that raises the declaration at "
            f"{WINDOW_DECLARATION}. An announcement SHALL NOT be a sentence addressed to a "
            f"human: the 2026-09-15 window was announced exactly that way, its "
            f"re-provisioning step was not performed, and the application that lost its "
            f"database learnt of it four and a half hours later from a message naming a "
            f"credential"
        )
    if withdraw_at is None:
        offenders.append(
            f"the procedure carries no act that withdraws the declaration at "
            f"{WINDOW_DECLARATION}. A declaration left raised keeps every application on "
            f"the host from delivering, indefinitely"
        )
    if offenders:
        return offenders

    if raise_at.start() > destructive_at.start():
        offenders.append(
            "the declaration is raised AFTER the first step that destroys data; it SHALL "
            "be declared before it, or the applications are told nothing until their "
            "databases are already gone"
        )
    if withdraw_at.start() < destructive_at.start():
        offenders.append(
            "the declaration is withdrawn before the destructive step it announces, which "
            "leaves the window itself unannounced"
        )
    if withdraw_at.start() > reprovision_at.start():
        offenders.append(
            "the declaration is withdrawn AFTER the step that re-provisions the "
            "application databases. Those re-provisionings and the redeploys they require "
            "go through the probe like any other, so a declaration still standing blocks "
            "the step that ends the window -- the mechanism deadlocking on itself"
        )
    return offenders


class TestTheUpgradeRunbookAnnouncesTheWindowItOpens(unittest.TestCase):
    """ADDED requirement: A Destructive Window on the Shared Instance Is
    Announced to the Applications That Hold Databases in It -- "A procedure in
    this repository that discards, re-creates or re-initialises that instance's
    data SHALL declare a window on that host before the first destructive step,
    and SHALL withdraw that declaration once the instance is serving again --
    before the step that re-provisions the application databases."
    """

    def test_the_procedure_declares_and_withdraws_the_window_in_the_right_order(self) -> None:
        """SPECIFIED -- scenario "A destructive procedure declares a window
        before its first destructive step", both limbs.

        And scenario "Prose alone does not discharge the announcement", which is
        the same assertion read as a refusal: what is looked for is an ACT naming
        the declaration's path, so a procedure whose only announcement is a
        sentence addressed to a human fails this check. That is the shape the
        procedure was in on 2026-09-15.
        """
        offenders = runbook_announcement_offences()
        self.assertEqual(
            [],
            offenders,
            f"{PLATFORM_README}'s upgrade procedure does not announce the window it "
            f"opens: {offenders}",
        )


# --------------------------------------------------------------------------
# 6. The contract the other repository depends on
# --------------------------------------------------------------------------


def undocumented_contract_terms(root: Path | None = None) -> list[str]:
    """Report each term of the probe's contract that the onboarding document
    does not carry."""
    text = _read(_base(root) / ONBOARDING)
    missing = [f"the token `{token}`" for token in TOKENS if f"`{token}`" not in text]
    missing += [
        f"the required input field `{field}`"
        for field in REQUIRED_INPUT_FIELDS
        if f"`{field}`" not in text
    ]
    if UNPRIVILEGED_SCRIPT not in text and "deploy-probe" not in text:
        missing.append("the probe's own forced command")
    if "probe_public_key" not in text:
        missing.append("the probe keypair an application declares")
    return missing


class TestTheConsumerContractIsWrittenDown(unittest.TestCase):
    """ADDED requirement: A Destructive Window on the Shared Instance Is
    Announced to the Applications That Hold Databases in It -- "What this
    requirement binds is that the announcement exists, is machine-readable, CAN
    BE TAKEN UP by any application holding a database in the instance that asks
    to ... A means that could not be taken up would be [evidence against it]."

    And the probe requirement's own reason for fixing the encoding in the
    specification: "the contract is held by another repository, which cannot read
    this one's scripts before depending on them."
    """

    def test_the_onboarding_document_carries_every_term_of_the_contract(self) -> None:
        """DERIVED as to WHERE -- that change's tasks.md 5.2 and 5.3 put the
        keypair in §2 and the consumer contract in §4 of this document.
        SPECIFIED as to WHAT: the six tokens are the requirement's own, and
        `password` and `table` are the two fields it makes required.

        What this cannot establish is that the prose is any good -- that each
        token's meaning is right, that the document says which of them should
        stop a delivery, or that a reader meeting `absent` finds the `platform`
        exception. Those are questions for review, and that change's tasks.md
        assigns them there.
        """
        missing = undocumented_contract_terms()
        self.assertEqual(
            [],
            missing,
            f"{ONBOARDING} does not carry these terms of the probe's contract: {missing}. "
            f"The repository holding the other half of it cannot read this one's scripts "
            f"before depending on them, so a contract that exists only in a script is one "
            f"no application can take up",
        )


# --------------------------------------------------------------------------
# 7. The probe scenario's fixture instance is the instance the stack runs
# --------------------------------------------------------------------------

POSTGRES_IMAGE = re.compile(r"\bpostgres:[A-Za-z0-9_.\-]+(?:@sha256:[0-9a-f]{64})?")


def stack_postgres_image(root: Path | None = None) -> str | None:
    """The image `platform/docker-compose.yml` pins for the shared instance."""
    base = _base(root)
    for name, image in compose_service_images(base / PLATFORM_COMPOSE):
        if name == "postgres":
            return image
    return None


def fixture_postgres_images(root: Path | None = None) -> list[tuple[str, str]]:
    """Every `postgres:<tag>` reference in the probe scenario's own files, as
    (file, image)."""
    base = _base(root)
    directory = base / PROBE_SCENARIO
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line in text.splitlines():
            if line.strip().startswith("#"):
                continue
            for match in POSTGRES_IMAGE.finditer(line):
                found.append((path.relative_to(base).as_posix(), match.group(0)))
    return found


def fixture_image_offences(root: Path | None = None) -> list[str]:
    """Report each fixture image that is not the release the shared stack
    pins."""
    pinned = stack_postgres_image(root)
    offenders = []
    if pinned is None:
        return [f"{PLATFORM_COMPOSE} declares no image for its `postgres` service"]
    if not image_names_a_release(pinned):
        offenders.append(f"the stack's own pin, {pinned}, does not name an exact release")
    for label, image in fixture_postgres_images(root):
        if image != pinned:
            offenders.append(f"{label} runs {image}, and the stack pins {pinned}")
    return offenders


class TestTheProbeFixtureRunsTheInstanceTheStackRuns(unittest.TestCase):
    """ADDED requirement: An Application Can Probe Its Own Database Through a
    Read-Only Forced Command -- read against that change's design.md decision 7,
    which has `app-probe` read its client's image from the RUNNING container
    rather than carry a copy of the pin.

    That decision is what makes the fixture's image load-bearing rather than
    incidental: the probe's own client is whatever the fixture instance runs, so
    a fixture on another major exercises a `psql` this repository never ships
    beside a server it never runs.
    """

    def test_the_probe_scenario_stands_up_a_postgres_fixture(self) -> None:
        """SPECIFIED -- the vacuity guard. The agreement check below reports
        green over a scenario naming no image at all, which is also a scenario
        that stands no instance up and therefore reaches none of the six
        tokens."""
        found = fixture_postgres_images()
        self.assertTrue(
            found,
            f"no file under {PROBE_SCENARIO} names a `postgres:` image, so the scenario "
            f"stands no shared instance up and the agreement assertion below would pass "
            f"having read nothing",
        )

    def test_the_fixture_image_is_the_release_the_shared_stack_pins(self) -> None:
        """DERIVED -- that change's tasks.md 1.5 ("the fixture image being
        pinned") and its design.md decision 7. The delta itself fixes no image.

        Agreement with the stack rather than a digest of its own: this repository
        pins the shared instance to an exact release and explains why a digest is
        not used for it, and a second pin in a fixture would drift from the first
        silently -- which is the same argument design.md decision 7 makes for not
        writing the image down in `app-probe` either.
        """
        offenders = fixture_image_offences()
        self.assertEqual(
            [],
            offenders,
            f"the probe scenario's PostgreSQL fixture does not run the release the shared "
            f"stack pins: {offenders}",
        )


# --------------------------------------------------------------------------
# The checks above are static reads. These establish that they can fail.
# --------------------------------------------------------------------------


class FixtureTreeMixin:
    """Builds throwaway trees the checks above can be pointed at.

    Every check takes its root as an argument, so each negative case below is
    exercised against a fixture rather than by damaging the real tree. Without
    these, a green run of this module would establish only that its files could
    be read: a check reading a path that has been renamed reports the same clean
    result as one whose subject really is correct.
    """

    def scratch_tree(self, files: dict[str, str]) -> Path:
        root = Path(tempfile.mkdtemp(prefix="shared-instance-reset-fixture-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for name, body in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        return root


GOOD_ROLE_TASKS = f"""---
- name: Ensure the maintenance declaration's directory exists
  ansible.builtin.file:
    path: {WINDOW_DIRECTORY}
    state: directory
    owner: root
    group: docker
    mode: "0775"

- name: Render each application's probe sudoers rule
  ansible.builtin.copy:
    dest: "{PROBE_SUDOERS_PREFIX}{{{{ item.name }}}}"
    content: |
      deploy ALL=(root) NOPASSWD: {PRIVILEGED_SCRIPT} {{{{ item.name }}}}
    validate: "visudo -cf %s"
"""

GOOD_ROLE_README = f"Raise the declaration with `touch {WINDOW_DECLARATION}`.\n"

GOOD_RUNBOOK = f"""## Operating the shared stack

{RUNBOOK_HEADING}

1. **On the host -- declare the window.**

       touch {WINDOW_DECLARATION}

2. **On the host -- discard the database and its volume.**

       docker rm -f platform-postgres-1
       docker volume rm platform_postgres_data

3. **From a workstation -- let the deploy carry the new major to that host.**

4. **On the host -- recreate postgres-exporter's role**, then withdraw the window.

       rm {WINDOW_DECLARATION}

5. **From a workstation -- re-provision every application database**, with rotate=yes.

## Monitoring and alerting
"""

GOOD_HOST_VARS = """---
deploy_apps:
  - name: platform
    public_key: "ssh-ed25519 AAAADEPLOYPLATFORM deploy@platform"
    probe_public_key: "ssh-ed25519 AAAAPROBEPLATFORM probe@platform"
  - name: commerce-ops
    public_key: "ssh-ed25519 AAAADEPLOYCOMMERCE deploy@commerce-ops"
    probe_public_key: "ssh-ed25519 AAAAPROBECOMMERCE probe@commerce-ops"
ghcr_pull_token: !vault |
  $ANSIBLE_VAULT;1.2;AES256;staging
  6162636465
"""

GOOD_ONBOARDING = (
    "## 2. Keys\n\nGenerate a probe keypair and record it as probe_public_key.\n"
    "The probe's forced command is /usr/local/bin/deploy-probe <app>.\n\n"
    "## 4. What the application does\n\nSend a JSON object carrying `password` and `table`.\n"
    + "".join(f"- `{token}`: what it means.\n" for token in TOKENS)
)

GOOD_COMPOSE = """---
services:
  postgres:
    image: postgres:18.6
"""

GOOD_SCENARIO = """---
- name: Fixture
  ansible.builtin.command: docker run -d --name platform-postgres-1 postgres:18.6
"""


def _good_tree() -> dict[str, str]:
    files = {
        f"{ROLE}/tasks/main.yml": GOOD_ROLE_TASKS,
        ROLE_README: GOOD_ROLE_README,
        PLATFORM_README: GOOD_RUNBOOK,
        PLATFORM_COMPOSE: GOOD_COMPOSE,
        ONBOARDING: GOOD_ONBOARDING,
        f"{PROBE_SCENARIO}/verify.yml": GOOD_SCENARIO,
    }
    for name in HOST_VARS:
        files[name] = GOOD_HOST_VARS
    return files


class TestTheChecksDiscriminate(FixtureTreeMixin, unittest.TestCase):
    """Every check in this module reads committed files rather than executing
    the behaviour it asserts, so a green result establishes nothing on its own --
    a check whose target had been renamed would report the same clean result.

    Each case below falsifies one check on the property it exists to assert, over
    material this test supplies. A case is here because it discriminates, not
    because it is expressible: this is not an enumeration of the checks' input
    space.
    """

    def test_the_checks_pass_over_a_tree_that_satisfies_them(self) -> None:
        """The positive control the negatives rest on. A check that reported an
        offence for every tree would 'catch' each case below while asserting
        nothing."""
        root = self.scratch_tree(_good_tree())
        self.assertEqual([], places_not_naming_the_declaration(root))
        self.assertEqual([], files_naming_a_disagreeing_declaration_path(root))
        self.assertTrue(declared_window_directory_mappings(root))
        self.assertEqual([], window_directory_offences(root))
        self.assertTrue(probe_sudoers_lines(root))
        self.assertEqual([], probe_sudoers_offences(root))
        self.assertEqual([], probe_sudoers_files_without_visudo_validation(root))
        self.assertEqual([], probe_key_offences(root))
        self.assertEqual([], runbook_announcement_offences(root))
        self.assertEqual([], undocumented_contract_terms(root))
        self.assertTrue(fixture_postgres_images(root))
        self.assertEqual([], fixture_image_offences(root))

    def test_a_runbook_naming_another_path_is_caught(self) -> None:
        """The disagreement a Molecule scenario cannot see: the role provisions
        one path and the operator is told to type another."""
        files = _good_tree()
        # Assembled from two halves rather than written out: a scan whose
        # pattern is spelled literally matches THIS FILE, and the walk's target
        # tree contains the scan. Written out, it reports itself as a
        # disagreeing path -- a false positive no implementation can clear.
        elsewhere = "/var/lib/platform-" + "maintenance-window/postgres"
        files[PLATFORM_README] = GOOD_RUNBOOK.replace(WINDOW_DECLARATION, elsewhere)
        root = self.scratch_tree(files)
        self.assertNotEqual([], places_not_naming_the_declaration(root))
        self.assertNotEqual([], files_naming_a_disagreeing_declaration_path(root))

    def test_a_group_writable_bit_removed_from_the_directory_is_caught(self) -> None:
        """`0755` reads as an ordinary, tidy-looking mode and is exactly the one
        that stops an operator holding no `sudo` from raising a window at all."""
        files = _good_tree()
        files[f"{ROLE}/tasks/main.yml"] = GOOD_ROLE_TASKS.replace('"0775"', '"0755"')
        root = self.scratch_tree(files)
        self.assertNotEqual([], window_directory_offences(root))

    def test_a_directory_owned_by_the_wrong_group_is_caught(self) -> None:
        files = _good_tree()
        files[f"{ROLE}/tasks/main.yml"] = GOOD_ROLE_TASKS.replace("group: docker", "group: root")
        root = self.scratch_tree(files)
        self.assertNotEqual([], window_directory_offences(root))

    def test_a_role_that_provisions_nothing_fails_the_vacuity_guard(self) -> None:
        """The enumeration being empty is what withdraws the ownership and mode
        checks, so it is asserted separately rather than left to them."""
        files = _good_tree()
        del files[f"{ROLE}/tasks/main.yml"]
        root = self.scratch_tree(files)
        self.assertEqual([], declared_window_directory_mappings(root))
        self.assertEqual(
            [],
            window_directory_offences(root),
            "the ownership and mode check reported an offence over a tree that "
            "provisions nothing, so it is not the empty enumeration that makes it "
            "green here and the vacuity guard is measuring something else",
        )

    def test_a_wildcard_in_the_probe_sudoers_rule_is_caught(self) -> None:
        """The template a fixture enumerating one application per rule renders
        correctly, and which grants every application to every probe key."""
        files = _good_tree()
        files[f"{ROLE}/tasks/main.yml"] = GOOD_ROLE_TASKS.replace(
            f"{PRIVILEGED_SCRIPT} {{{{ item.name }}}}", f"{PRIVILEGED_SCRIPT} *"
        )
        root = self.scratch_tree(files)
        self.assertNotEqual([], probe_sudoers_offences(root))

    def test_a_probe_rule_granting_no_argument_at_all_is_caught(self) -> None:
        files = _good_tree()
        files[f"{ROLE}/tasks/main.yml"] = GOOD_ROLE_TASKS.replace(
            f"{PRIVILEGED_SCRIPT} {{{{ item.name }}}}", PRIVILEGED_SCRIPT
        )
        root = self.scratch_tree(files)
        self.assertNotEqual([], probe_sudoers_offences(root))

    def test_a_probe_sudoers_file_written_without_validation_is_caught(self) -> None:
        files = _good_tree()
        files[f"{ROLE}/tasks/main.yml"] = GOOD_ROLE_TASKS.replace(
            '    validate: "visudo -cf %s"\n', ""
        )
        root = self.scratch_tree(files)
        self.assertNotEqual([], probe_sudoers_files_without_visudo_validation(root))

    def test_a_probe_key_equal_to_its_deploy_key_is_caught(self) -> None:
        """One `authorized_keys` entry carries one forced command, so a key
        appearing in both fields is bound to neither -- and both entries look
        perfectly well-formed."""
        files = _good_tree()
        files[HOST_VARS[0]] = GOOD_HOST_VARS.replace(
            'probe_public_key: "ssh-ed25519 AAAAPROBEPLATFORM probe@platform"',
            'probe_public_key: "ssh-ed25519 AAAADEPLOYPLATFORM deploy@platform"',
        )
        root = self.scratch_tree(files)
        self.assertNotEqual([], probe_key_offences(root))

    def test_an_application_left_without_a_probe_key_is_caught(self) -> None:
        files = _good_tree()
        files[HOST_VARS[1]] = GOOD_HOST_VARS.replace(
            '    probe_public_key: "ssh-ed25519 AAAAPROBECOMMERCE probe@commerce-ops"\n', ""
        )
        root = self.scratch_tree(files)
        self.assertNotEqual([], probe_key_offences(root))

    def test_a_group_vars_file_with_no_applications_refuses_rather_than_passing(self) -> None:
        """Every assertion over the enumerated applications reports green over an
        empty list, so the reader raises instead of returning one."""
        files = _good_tree()
        files[HOST_VARS[0]] = "---\ndeploy_apps: []\n"
        root = self.scratch_tree(files)
        with self.assertRaises(AssertionError):
            probe_key_offences(root)

    def test_a_runbook_announcing_the_window_only_in_prose_is_caught(self) -> None:
        """Scenario "Prose alone does not discharge the announcement", exercised.
        This is the shape the procedure was in on 2026-09-15: a sentence telling
        an operator to tell the applications, and no act at all."""
        files = _good_tree()
        files[PLATFORM_README] = GOOD_RUNBOOK.replace(
            f"       touch {WINDOW_DECLARATION}\n",
            "   Tell the applications that use the instance, and agree the window.\n",
        )
        root = self.scratch_tree(files)
        self.assertNotEqual([], runbook_announcement_offences(root))

    def test_a_window_raised_after_the_volume_is_discarded_is_caught(self) -> None:
        """The ordering defect that leaves the applications told nothing until
        their databases are already gone. Both acts are present, so a check
        reading only for their presence passes."""
        files = _good_tree()
        files[PLATFORM_README] = GOOD_RUNBOOK.replace(
            f"1. **On the host -- declare the window.**\n\n       touch {WINDOW_DECLARATION}\n",
            "1. **On the host -- read what the instance holds.**\n",
        ).replace(
            "3. **From a workstation -- let the deploy",
            f"   Now declare the window.\n\n       touch {WINDOW_DECLARATION}\n\n"
            "3. **From a workstation -- let the deploy",
        )
        root = self.scratch_tree(files)
        self.assertNotEqual([], runbook_announcement_offences(root))

    def test_a_window_withdrawn_after_re_provisioning_is_caught(self) -> None:
        """The deadlock: the re-provisioning step's own redeploys go through the
        probe, so a declaration still standing blocks the step that ends the
        window."""
        files = _good_tree()
        files[PLATFORM_README] = GOOD_RUNBOOK.replace(
            f"       rm {WINDOW_DECLARATION}\n", ""
        ).replace(
            "## Monitoring and alerting",
            f"   Then withdraw the window.\n\n       rm {WINDOW_DECLARATION}\n\n"
            "## Monitoring and alerting",
        )
        root = self.scratch_tree(files)
        self.assertNotEqual([], runbook_announcement_offences(root))

    def test_a_contract_missing_one_token_is_caught(self) -> None:
        """A consumer cannot act on a token it was never told about, and
        `absent` is the one the whole change exists to deliver."""
        files = _good_tree()
        files[ONBOARDING] = GOOD_ONBOARDING.replace("- `absent`: what it means.\n", "")
        root = self.scratch_tree(files)
        self.assertNotEqual([], undocumented_contract_terms(root))

    def test_a_fixture_on_another_major_is_caught(self) -> None:
        """The fixture and the stack agreeing is what makes the probe's own
        client the one this repository ships."""
        files = _good_tree()
        files[f"{PROBE_SCENARIO}/verify.yml"] = GOOD_SCENARIO.replace(
            "postgres:18.6", "postgres:16.4"
        )
        root = self.scratch_tree(files)
        self.assertNotEqual([], fixture_image_offences(root))

    def test_a_stack_pinned_to_a_floating_tag_is_caught(self) -> None:
        files = _good_tree()
        files[PLATFORM_COMPOSE] = GOOD_COMPOSE.replace(
            "postgres:18.6", "postgres:latest"
        )
        files[f"{PROBE_SCENARIO}/verify.yml"] = GOOD_SCENARIO.replace(
            "postgres:18.6", "postgres:latest"
        )
        root = self.scratch_tree(files)
        self.assertNotEqual([], fixture_image_offences(root))


if __name__ == "__main__":
    unittest.main()
