"""Static-assertion tests for the platform data volume's mount path moving.

Derived from the delta specifications of the OpenSpec change
`move-the-platform-data-mount`, before any implementation of that change
existed -- from those deltas at commit `f3c94cd`, the commit holding the
approved plan. The path those deltas sit at is not written here: a change's
artifacts move when it is archived, and this repository's citation convention
is to name the change and the artifact in prose instead.

The change modifies two requirements. *Platform Data Volume Is Mounted at a
Fixed Host Path* (`openspec/specs/iac-host-configuration/spec.md`) gains the
obligation that a superseded mount path is not left persisting across a reboot;
that obligation is role BEHAVIOUR and is covered by two Molecule scenarios of
`ansible/roles/platform_data_volume/`, not here. *No Store on This Host Holds
Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`)
identifies two of its stores by path, and both move.

WHAT THIS MODULE IS FOR, AND WHY IT IS A SEVENTEENTH MODULE
-----------------------------------------------------------
Two propositions, neither of which anything in this repository reads today, and
both of which are static reads of a committed file (AGENTS.md, "Testing"):

1. Every host bind mount the platform stack declares whose source lies under
   `/mnt/` lies under the mount path the `platform_data_volume` role
   establishes. This is the proposition `docs/change-queue.md` entry 62
   deliberately suspended when the volume was renamed and the mount path was
   not, and its absence is why the two could drift silently. A compose file
   naming a path the role does not mount produces an empty directory on the
   root disk and a healthy-looking container, which is exactly what
   `docs/bootstrap-a-new-host.md` warns about.

2. No committed file still names the superseded path. Several files currently
   explain why the path and the volume's name differ; deleting all but one of
   them is the likely failure, and a stale path in a comment or a runbook fails
   nothing on its own.

It is a module of its own rather than a section of one beside it because these
tests were written by an author other than whoever implements the change, and
that author may only add. Three modules in this directory carry the superseded
path as a literal or explain the divergence in prose, and re-pointing those is
the implementing author's task (that change's tasks.md 3.5), recorded in this
change's test-plan.md rather than performed here. NOTHING IN THIS FILE EDITS,
DELETES OR DISABLES AN EXISTING TEST. Where a helper a module beside this one
already has is needed, it is imported rather than restated, which is the idiom
the sixteen modules already here use.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_the_platform_data_mount_moved\\
        .TestNoCommittedFileStillNamesTheSupersededMountPath\\
        .test_no_committed_file_names_the_superseded_mount_path

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling import below resolve.

What no assertion here establishes
----------------------------------
Nothing here mounts anything, reads a host, or runs Ansible. That the role
actually retires a superseded `/etc/fstab` entry, that it leaves a live mount
alone, and that it refuses a declaration naming the path in force are role
behaviour and are established by the `superseded-path-retired` and
`superseded-path-in-force-refused` Molecule scenarios. A green run here
establishes that the COMMITTED FILES agree with one another about which path
the volume is mounted at -- never that any host is mounted there.

Nor does the sweep prove the sweep was complete. Its needle is the PATH, so it
misses a file whose commitment to `docs/change-queue.md` entry 64 names no path
at all, and it is blind inside its own exempt prefixes. That change's design
records which two files are in that position; they are caught by review or not
at all.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from test_ci_configuration import (
    PLATFORM_COMPOSE,
    ROOT,
    _under,
    service_mounts,
    tracked_files,
    walked_files,
)

# --------------------------------------------------------------------------
# Identifiers this file names
# --------------------------------------------------------------------------

# The role that establishes the mount, and the variable holding the path it
# establishes. Read from the committed defaults rather than written down as a
# literal: the whole point of the first proposition is that the stack follows
# the role, so a literal here would let the two move apart while this module
# stayed green.
ROLE_DEFAULTS = "ansible/roles/platform_data_volume/defaults/main.yml"
MOUNT_PATH_VARIABLE = "platform_data_volume_mount_path"

# The qualifier that separates the two populations of host bind mount this
# stack declares, and it is chosen rather than assumed. The stack binds ten
# other host paths -- `/`, `/proc`, `/sys`, `/var/run`, `/var/lib/docker/` and
# the Docker and containerd sockets -- every one of them a read-only
# observation mount that cAdvisor, Node Exporter and Traefik take of the host
# itself. Those are owned by the host and have nothing to do with the data
# volume, so a check written over EVERY host bind mount would be red on the day
# it landed and would have to be weakened at the keyboard. `/mnt/` is where
# this host puts mounted volumes and nothing else.
HOST_VOLUME_ROOT = "/mnt/"

# The path this change moves off, and the needle of the sweep below. THE PATH,
# not the bare string `main-data`: that is also the volume's retired NAME,
# which `EXPECTED_RETIRED_VOLUME_NAMES` in
# `test_a_stack_and_its_environment_are_named_separately.py` already covers and
# which `docs/change-queue.md` entry 74 owns the remaining prose for. Sweeping
# the bare name here would take that entry's work without planning it.
SUPERSEDED_MOUNT_PATH = "/mnt/main-data"

# Prefix exemptions, each with a reason rather than a category.
#
# `openspec/` ENTIRE, not `openspec/changes/` alone. A change record names what
# it moves FROM, this change's own artifacts included; and
# `openspec/specs/iac-safety-hardening/spec.md` keeps the superseded path until
# `openspec archive` merges the delta into it, which happens in the change's
# LAST commit. A sweep exempting only `openspec/changes/` would be red for the
# whole life of the change, with no repair available short of hand-editing a
# main spec outside the archive mechanism -- and a red required check on every
# push is a check that gets ignored rather than read. It is also the exemption
# `TestNoCommittedFileStillNamesTheOldTerraformRoot` takes, for this reason
# word for word.
#
# `.github/tests/` -- where a needle must be written down in order to assert
# its absence, and where fixture trees name the path on purpose.
EXEMPT_PREFIXES = ("openspec/", ".github/tests/")

# Whole-path exemptions. Each is a decision about a file this change does not
# edit, and each is checked below for still carrying the needle, so an
# exemption cannot outlive what it exempts.
#
# `docs/review-2026-09-08-host-readiness.md` records what was observed on the
# host on one date, and on that date the mount was the superseded path. Editing
# it would make it say something that was not observed. PERMANENT.
#
# `docs/change-queue.md` names the superseded path in entry 64, which is this
# change, and that entry is deleted in the archive commit. EXPIRING: the
# assertion below requires an exempt path to still contain the needle, so
# archiving turns it red and deleting this line in that same commit is the
# repair. That is planned into this change's tasks.md rather than met as a
# surprise.
EXEMPT_WHOLE_PATHS = {
    "docs/review-2026-09-08-host-readiness.md": "records what was observed on one date",
    "docs/change-queue.md": "entry 64 is this change; expires when that entry is deleted",
}

# The exemption scoped to a LINE rather than to a file, which this change
# creates for itself. Its Decision 3 puts the superseded path into both
# `group_vars` files permanently, and its new Molecule scenarios declare a
# superseded path of their own -- so a sweep with no exemption for them is red
# before the pull request opens, and the repair reached for on the day would be
# a whole-path exemption on `ansible/inventory/group_vars/`, which blinds the
# sweep to `staging.yml`, the one file whose divergence prose the sweep was
# written to catch.
#
# So the exemption is the DECLARATION, not the file. LEADING WHITESPACE IS
# STRIPPED before the line is read, which matters rather than being a detail: a
# Molecule scenario declares the path indented under `vars:`, so a match
# anchored at column zero would miss it and the repair reached for would be a
# whole-path exemption on the scenario directory. Prose anywhere in those files
# stays swept.
#
# It costs one thing and it is worth naming: the declaration must be written in
# YAML's inline flow form, on one line, because a block sequence puts the value
# on a line of its own where the key is not there to exempt it. Requiring a
# form is cheaper than a multi-line parse, and the failure message below says
# which form to use.
SUPERSEDED_DECLARATION_KEY = "platform_data_volume_superseded_mount_paths:"

DECLARATION_FORM = (
    'platform_data_volume_superseded_mount_paths: ["' + SUPERSEDED_MOUNT_PATH + '"]'
)


# --------------------------------------------------------------------------
# Reading the mount path the role establishes, and the stack's own bind mounts
# --------------------------------------------------------------------------


def role_default_mount_path(root: Path | None = None) -> str:
    """The fixed mount path the role's committed defaults establish.

    Takes `root` so the read is exercisable against a fixture tree, which is
    what stops the containment check below passing vacuously: over the
    committed tree it reads one value and one stack, and a check that agreed
    with itself for the wrong reason would look identical.
    """
    path = (ROOT if root is None else root) / ROLE_DEFAULTS
    if not path.is_file():
        raise AssertionError(f"{ROLE_DEFAULTS} does not exist, so no mount path can be read")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise AssertionError(f"{ROLE_DEFAULTS} does not parse as a mapping")
    value = document.get(MOUNT_PATH_VARIABLE)
    if not isinstance(value, str) or not value.strip():
        raise AssertionError(
            f"{ROLE_DEFAULTS} declares no usable {MOUNT_PATH_VARIABLE}: {value!r}. "
            "Without it this check has nothing to compare the stack's bind mounts "
            "against and would pass having read nothing"
        )
    return value.strip()


def stack_host_volume_mounts(compose: Path | None = None) -> list[tuple[str, str]]:
    """Every (service, source) the stack binds from under the host's volume
    root.

    The ten runtime observation mounts fall outside this by CONSTRUCTION rather
    than by enumeration: none of `/`, `/proc`, `/sys`, `/var/run`,
    `/var/lib/docker/` or either socket path begins with the volume root, so
    none is reached here and none has to be listed anywhere.
    """
    found = []
    for service, mount in service_mounts(compose):
        source = mount.get("source")
        if isinstance(source, str) and source.startswith(HOST_VOLUME_ROOT):
            found.append((service, source))
    return found


def stack_mounts_outside_the_role_mount_path(
    compose: Path | None = None, root: Path | None = None
) -> list[str]:
    """Every host volume bind the role's mount path does not contain.

    CONTAINMENT IS COMPARED ON PATH COMPONENTS, NOT ON STRING PREFIXES, and
    this is the one detail that decides whether the check is worth having:
    `/mnt/main` is a proper string prefix of `/mnt/main-data`, so a bare
    `startswith` accepts `/mnt/main-data/prometheus` as lying under
    `/mnt/main` -- green in exactly the state the check exists to detect.
    `_under` in the module beside this one already compares that way and is
    what this reuses rather than restating.

    A source EQUAL to the mount path is accepted as well as one strictly under
    it. `_under` alone is strict, and a service binding the mount root itself
    is not the state this exists to catch. DERIVED: no scenario states it.
    """
    mount_path = role_default_mount_path(root)
    return sorted(
        f"{service} -> {source} (the role mounts the volume at {mount_path})"
        for service, source in stack_host_volume_mounts(compose)
        if source.rstrip("/") != mount_path.rstrip("/") and not _under(mount_path, source)
    )


# --------------------------------------------------------------------------
# The sweep
# --------------------------------------------------------------------------


def superseded_path_occurrences(root: Path | None = None) -> list[str]:
    """Every committed file still naming the superseded mount path, as
    `<path>:<line>`.

    THE FILE SET IS TRACKED FILES, NOT A FILESYSTEM WALK, for the reason
    `tracked_files()` itself records and `docs/change-queue.md` entry 68 names:
    a walk reads `.molecule-home/` and sibling working trees under
    `.claude/worktrees/`, which do not exist in continuous integration and
    appear the moment a developer follows this repository's own Molecule
    instructions. A check that disagrees with itself between a working machine
    and a runner trains its readers to discount it.

    A `root` argument means a scratch tree instead, which is NOT a repository
    and has no tracked files, so those are walked. That path exists for the
    discriminators below and is not a second way of reading the repository.

    Raises rather than reporting a clean tree when it reads no file at all: a
    sweep that read nothing would otherwise report success having verified
    nothing.
    """
    here = Path(__file__).resolve()
    contents: dict[str, str] = {}
    if root is None:
        for name, raw in tracked_files().items():
            if (ROOT / name).resolve() == here:
                continue
            contents[name] = raw.decode("utf-8", errors="replace")
        if not contents:
            raise AssertionError(
                "the tracked-file listing reached no file at all, so this sweep "
                "would pass having read nothing"
            )
    else:
        walked = walked_files(root)
        if not walked:
            raise AssertionError(
                f"the walk from {root} reached no file at all, so this sweep would "
                "pass having read nothing"
            )
        for path in walked:
            if path.resolve() == here:
                continue
            contents[path.relative_to(root).as_posix()] = path.read_text(
                encoding="utf-8", errors="replace"
            )

    offences: list[str] = []
    for name, text in contents.items():
        if name.startswith(EXEMPT_PREFIXES) or name in EXEMPT_WHOLE_PATHS:
            continue
        if SUPERSEDED_MOUNT_PATH not in text:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if SUPERSEDED_MOUNT_PATH not in line:
                continue
            if line.lstrip().startswith(SUPERSEDED_DECLARATION_KEY):
                continue
            offences.append(f"{name}:{number}")
    return sorted(offences)


def exemptions_naming_no_occurrence(
    exemptions: dict | None = None, root: Path | None = None
) -> list[str]:
    """Every whole-path exemption whose file no longer carries the needle.

    This is how an exemption expires. `docs/change-queue.md` is exempt because
    entry 64 names the superseded path; that entry is deleted in the archive
    commit, and this turns red at exactly that moment so the exemption is
    deleted in the same commit rather than left standing over a file it no
    longer describes. An exemption that outlives its reason is a hole nobody
    can see.
    """
    wanted = EXEMPT_WHOLE_PATHS if exemptions is None else exemptions
    base = ROOT if root is None else root
    missing = []
    for name, reason in sorted(wanted.items()):
        path = base / name
        if not path.is_file():
            missing.append(f"{name} (exempt because {reason}) no longer exists")
            continue
        if SUPERSEDED_MOUNT_PATH not in path.read_text(encoding="utf-8", errors="replace"):
            missing.append(
                f"{name} (exempt because {reason}) no longer names "
                f"{SUPERSEDED_MOUNT_PATH}"
            )
    return missing


# --------------------------------------------------------------------------
# The stack follows the role
# --------------------------------------------------------------------------


class TestEveryHostVolumeBindLiesUnderTheMountTheRoleEstablishes(unittest.TestCase):
    """SPECIFIED by iac-host-configuration / *Platform Data Volume Is Mounted
    at a Fixed Host Path*, scenario "Dependent subdirectories exist before a
    service needs them": the subdirectory a `platform/` service bind-mounts
    SHALL already exist under that mount. A service binding a path the role
    does not mount cannot satisfy that, whatever the role created -- Docker
    creates the missing source as an empty root-owned directory on the root
    disk and the container comes up healthy and empty.

    The two stores this change moves are also two rows of iac-safety-hardening's
    *No Store on This Host Holds Data Requiring Backup* table, which identifies
    them by path.
    """

    def test_every_stack_bind_under_the_host_volume_root_lies_under_the_role_mount_path(
        self,
    ) -> None:
        """SPECIFIED -- see the class docstring."""
        offences = stack_mounts_outside_the_role_mount_path()
        self.assertEqual(
            [],
            offences,
            f"these host bind mounts in {PLATFORM_COMPOSE.name} name a path under "
            f"{HOST_VOLUME_ROOT} that the platform_data_volume role does not mount: "
            f"{offences}. Compose creates a missing bind source as an empty "
            "root-owned directory on the root disk, so the container comes up "
            "healthy while the volume sits mounted somewhere else -- the drift "
            "this check exists to make visible",
        )

    def test_the_committed_stack_declares_at_least_one_host_volume_bind(self) -> None:
        """DERIVED -- a premise check. The assertion above reports a clean
        result by finding nothing, which is also what it would report having
        read the wrong file or having had the qualifier drift out from under
        it. This says the population it reads is non-empty."""
        mounts = stack_host_volume_mounts()
        self.assertNotEqual(
            [],
            mounts,
            f"{PLATFORM_COMPOSE} declares no host bind mount under "
            f"{HOST_VOLUME_ROOT} at all, so the check above passes having "
            "examined nothing",
        )

    def test_the_role_default_mount_path_is_an_absolute_path(self) -> None:
        """DERIVED -- the other half of the premise: the value the containment
        is measured against is read from the committed defaults, and an empty
        or relative one would make every comparison meaningless."""
        mount_path = role_default_mount_path()
        self.assertTrue(
            mount_path.startswith("/"),
            f"{ROLE_DEFAULTS} declares {MOUNT_PATH_VARIABLE} as {mount_path!r}, "
            "which is not an absolute host path",
        )


class TestTheContainmentCheckDiscriminates(unittest.TestCase):
    """DERIVED. The check above passes over the committed tree today and will
    pass over it after this change lands, because both literals move together.
    A check that read nothing, or compared string prefixes, would look
    identical. These supply their own material and establish that it does not.
    """

    def fixture(self, mount_path: str, sources: list[str]) -> tuple[Path, Path]:
        """A scratch tree carrying a role default and a stack definition, each
        saying what this test needs it to say."""
        directory = Path(tempfile.mkdtemp(prefix="platform-data-mount-fixture-"))
        defaults = directory / ROLE_DEFAULTS
        defaults.parent.mkdir(parents=True, exist_ok=True)
        defaults.write_text(
            f"---\n{MOUNT_PATH_VARIABLE}: {mount_path}\n", encoding="utf-8"
        )
        compose = directory / "platform" / "docker-compose.yml"
        compose.parent.mkdir(parents=True, exist_ok=True)
        body = ["services:", "  service:", "    image: nginx:1.29.3", "    volumes:"]
        body.extend(f"      - {source}:/data" for source in sources)
        compose.write_text("\n".join(body) + "\n", encoding="utf-8")
        return compose, directory

    def test_a_stack_binding_the_superseded_path_is_reported(self) -> None:
        """DERIVED -- THE discriminator this check stands or falls on. A bare
        `startswith` accepts this fixture, because `/mnt/main` is a proper
        string prefix of `/mnt/main-data`. A check that passes it is
        vacuous."""
        compose, root = self.fixture("/mnt/main", [f"{SUPERSEDED_MOUNT_PATH}/prometheus"])
        self.assertNotEqual(
            [],
            stack_mounts_outside_the_role_mount_path(compose, root),
            f"a stack binding {SUPERSEDED_MOUNT_PATH}/prometheus against a role "
            "mounting /mnt/main was not reported. Containment is being compared "
            "on string prefixes rather than on path components, which is green in "
            "exactly the state this check exists to detect",
        )

    def test_a_stack_binding_under_the_path_in_force_is_not_reported(self) -> None:
        """DERIVED -- the converse, so the check above is not satisfied by
        reporting everything."""
        compose, root = self.fixture(
            "/mnt/main", ["/mnt/main/prometheus", "/mnt/main/grafana"]
        )
        self.assertEqual(
            [],
            stack_mounts_outside_the_role_mount_path(compose, root),
            "a stack binding subdirectories of the path the role mounts was "
            "reported as an offence",
        )

    def test_moving_the_role_default_alone_is_reported(self) -> None:
        """DERIVED -- that change's tasks.md 3.3: "red when either committed
        literal is changed alone". This is the other direction from the first
        discriminator: the stack moved and the role did not."""
        compose, root = self.fixture(SUPERSEDED_MOUNT_PATH, ["/mnt/main/prometheus"])
        self.assertNotEqual(
            [],
            stack_mounts_outside_the_role_mount_path(compose, root),
            "a stack binding /mnt/main against a role still mounting "
            f"{SUPERSEDED_MOUNT_PATH} was not reported, so this check does not "
            "hold the two literals to each other",
        )

    def test_the_runtime_observation_mounts_are_out_of_reach_by_construction(self) -> None:
        """DERIVED -- that change's design: the ten observation mounts must
        fall outside the check's reach by construction rather than by
        enumeration, or the check would be red on the day it landed and would
        have to be weakened at the keyboard. None of them is named in this
        module; this establishes that none of them needs to be."""
        compose, root = self.fixture(
            "/mnt/main",
            [
                "/",
                "/proc",
                "/sys",
                "/var/run",
                "/var/lib/docker/",
                "/var/run/docker.sock",
                "/run/containerd/containerd.sock",
            ],
        )
        self.assertEqual(
            [],
            stack_mounts_outside_the_role_mount_path(compose, root),
            "a runtime observation mount of the host was reported as an offence. "
            "They are excluded by not lying under the host's volume root, which is "
            "why no list of them appears in this module",
        )

    def test_a_role_default_that_cannot_be_read_is_a_failure_not_a_pass(self) -> None:
        """DERIVED -- the read refuses rather than returning a value that would
        make every containment comparison pass."""
        directory = Path(tempfile.mkdtemp(prefix="platform-data-mount-empty-"))
        with self.assertRaises(AssertionError):
            role_default_mount_path(directory)


# --------------------------------------------------------------------------
# Nothing still names the superseded path
# --------------------------------------------------------------------------


class TestNoCommittedFileStillNamesTheSupersededMountPath(unittest.TestCase):
    """DERIVED -- that change's design Decision 5 and tasks.md 3.4, which state
    this sweep as what makes the move complete rather than mostly complete:
    several files currently explain why the path and the volume's name differ,
    a stale path in a comment or a runbook fails nothing on its own, and half a
    move leaves a reader unable to tell which of the two words is load-bearing.

    Its scope is written out rather than left to be read off the code -- see
    `EXEMPT_PREFIXES`, `EXEMPT_WHOLE_PATHS` and `SUPERSEDED_DECLARATION_KEY`
    above, each of which carries its own reason.
    """

    def test_no_committed_file_names_the_superseded_mount_path(self) -> None:
        """DERIVED -- see the class docstring."""
        offences = superseded_path_occurrences()
        self.assertEqual(
            [],
            offences,
            f"these committed files still name `{SUPERSEDED_MOUNT_PATH}`, the path "
            f"this change moves off: {offences}. Where the occurrence is a "
            "deliberate declaration of a superseded path, it must be written on one "
            f"line in the inline flow form `{DECLARATION_FORM}` -- a block sequence "
            "puts the value on a line of its own, where the key is not there to "
            "exempt it",
        )

    def test_the_openspec_tree_names_the_path_and_is_not_reported(self) -> None:
        """DERIVED -- the `openspec/` prefix exemption, established over the
        repository because a scratch tree cannot establish it: the walker the
        scratch path uses prunes `openspec` itself.

        Both halves are asserted together so the exemption cannot go vacuous:
        that the tracked `openspec/` tree DOES name the superseded path -- it
        always will, because an archived record names what its change moved
        from -- and that the sweep reports none of it.
        """
        naming = sorted(
            name
            for name, raw in tracked_files().items()
            if name.startswith("openspec/")
            and SUPERSEDED_MOUNT_PATH in raw.decode("utf-8", errors="replace")
        )
        self.assertNotEqual(
            [],
            naming,
            "no tracked file under `openspec/` names the superseded path, so the "
            "prefix exemption is exempting nothing and this assertion establishes "
            "nothing about it",
        )
        reported = [
            offence
            for offence in superseded_path_occurrences()
            if offence.startswith("openspec/")
        ]
        self.assertEqual(
            [],
            reported,
            f"the sweep reported occurrences under `openspec/`: {reported}. A change "
            "record names what it moves FROM, and the main specification keeps the "
            "superseded path until `openspec archive` merges the delta into it in "
            "the change's LAST commit -- so a sweep reaching there is red for the "
            "whole life of the change, with no repair short of hand-editing a main "
            "spec outside the archive mechanism",
        )

    def test_every_whole_path_exemption_still_names_the_path(self) -> None:
        """DERIVED -- an exemption naming a path that no longer carries the
        needle is itself an offence. This is the mechanism by which
        `docs/change-queue.md`'s exemption expires in the archive commit."""
        stale = exemptions_naming_no_occurrence()
        self.assertEqual(
            [],
            stale,
            f"these whole-path exemptions no longer describe anything: {stale}. An "
            "exemption that outlives its reason is a hole in the sweep nobody can "
            "see; delete it in the same commit that removed the occurrence",
        )


class TestTheSweepDiscriminates(unittest.TestCase):
    """DERIVED. The sweep reports a clean tree by finding nothing, which is
    also what it would report having read the wrong thing, having had its
    needle drift, or having exempted more than it meant to. These build scratch
    trees and establish what it reports over each.
    """

    def tree(self, files: dict) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="platform-data-mount-sweep-"))
        for name, text in files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return directory

    def test_the_sweep_reaches_terraform_platform_and_docs(self) -> None:
        """DERIVED -- that change's tasks.md 3.4: the sweep reaches
        `terraform/`, `platform/` and `docs/` through named anchors. Every file
        this change edits outside the two exempt prefixes lives under one of
        them."""
        tree = self.tree(
            {
                "terraform/stacks/main-staging/variables.tf": (
                    f'  description = "mounted at {SUPERSEDED_MOUNT_PATH}"\n'
                ),
                "platform/docker-compose.yml": f"      - {SUPERSEDED_MOUNT_PATH}/grafana:/x\n",
                "docs/bootstrap-a-new-host.md": f"the host mounts {SUPERSEDED_MOUNT_PATH}\n",
                "ansible/roles/swap/molecule/default/verify.yml": (
                    f"    swap_forbidden_prefix: {SUPERSEDED_MOUNT_PATH}\n"
                ),
            }
        )
        self.assertEqual(
            [
                "ansible/roles/swap/molecule/default/verify.yml:1",
                "docs/bootstrap-a-new-host.md:1",
                "platform/docker-compose.yml:1",
                "terraform/stacks/main-staging/variables.tf:1",
            ],
            superseded_path_occurrences(tree),
            "the sweep did not report an occurrence under each anchor this change "
            "edits",
        )

    def test_an_indented_declaration_is_exempt(self) -> None:
        """DERIVED -- the line-scoped exemption, with leading whitespace
        stripped. A Molecule scenario declares the path indented under `vars:`,
        so a match anchored at column zero would miss it and the repair reached
        for would be a whole-path exemption on the scenario directory."""
        tree = self.tree(
            {
                "ansible/inventory/group_vars/staging.yml": (
                    f"{DECLARATION_FORM}\n"
                ),
                "ansible/roles/platform_data_volume/molecule/x/converge.yml": (
                    f"  vars:\n    {DECLARATION_FORM}\n"
                ),
            }
        )
        self.assertEqual(
            [],
            superseded_path_occurrences(tree),
            "a superseded-path declaration was reported as an offence. The "
            "declaration is what this change puts in both group_vars files "
            "permanently and in its own Molecule scenarios; sweeping it would make "
            "the sweep unsatisfiable and invite a whole-path exemption that blinds "
            "it to the prose beside it",
        )

    def test_indented_prose_naming_the_path_is_not_exempt(self) -> None:
        """DERIVED -- the exemption is the DECLARATION, not the indentation and
        not the file. This is the near-miss that would hollow it out."""
        tree = self.tree(
            {
                "ansible/inventory/group_vars/staging.yml": (
                    f"  # both stacks share {SUPERSEDED_MOUNT_PATH}/prometheus\n"
                ),
            }
        )
        self.assertEqual(
            ["ansible/inventory/group_vars/staging.yml:1"],
            superseded_path_occurrences(tree),
            "indented PROSE naming the superseded path was treated as a "
            "declaration and exempted",
        )

    def test_prose_in_a_file_carrying_the_declaration_is_still_reported(self) -> None:
        """DERIVED -- and this is the case the whole line-scoping exists for.
        `staging.yml` carries both: the declaration this change adds, and the
        divergence prose it deletes. A whole-path exemption on that file would
        be green over both."""
        tree = self.tree(
            {
                "ansible/inventory/group_vars/staging.yml": (
                    f"{DECLARATION_FORM}\n"
                    "# the volume is named main but is mounted at\n"
                    f"# {SUPERSEDED_MOUNT_PATH} until change-queue entry 64\n"
                ),
            }
        )
        self.assertEqual(
            ["ansible/inventory/group_vars/staging.yml:3"],
            superseded_path_occurrences(tree),
            "prose naming the superseded path, in the same file as the declaration "
            "that is exempt, was not reported",
        )

    def test_a_block_sequence_declaration_is_not_exempt(self) -> None:
        """DERIVED -- the cost the line-scoped exemption carries, asserted
        rather than only documented: a declaration written as a block sequence
        puts its value on a line the key is not on, so nothing exempts it. The
        sweep's own failure message names the form to use instead."""
        tree = self.tree(
            {
                "ansible/inventory/group_vars/production.yml": (
                    "platform_data_volume_superseded_mount_paths:\n"
                    f"  - {SUPERSEDED_MOUNT_PATH}\n"
                ),
            }
        )
        self.assertEqual(
            ["ansible/inventory/group_vars/production.yml:2"],
            superseded_path_occurrences(tree),
            "a block-sequence declaration was exempted, which the line-scoped "
            "exemption cannot do -- if this passes, the exemption is matching more "
            "than the line carrying the key",
        )

    def test_the_tests_prefix_is_not_swept(self) -> None:
        """DERIVED -- `.github/tests/`, where a needle must be written down in
        order to assert its absence and where fixture trees name the path on
        purpose.

        The `openspec/` half of the same exemption is NOT exercised here and
        could not be: `walked_files()`, which is what reads a scratch tree,
        prunes `openspec` at the walk root, so a fixture would be green whether
        or not the prefix exemption existed. It is established over the
        repository instead, by the sibling class's
        `test_the_openspec_tree_names_the_path_and_is_not_reported`.
        """
        tree = self.tree(
            {
                ".github/tests/test_something.py": (
                    f'PATH = "{SUPERSEDED_MOUNT_PATH}"\n'
                ),
                "docs/swept.md": f"{SUPERSEDED_MOUNT_PATH} in prose\n",
            }
        )
        self.assertEqual(
            ["docs/swept.md:1"],
            superseded_path_occurrences(tree),
            "a module of this suite naming the needle was reported, or a file "
            "outside the exempt prefix was missed",
        )

    def test_a_whole_path_exemption_is_not_swept_but_must_still_name_the_path(
        self,
    ) -> None:
        """DERIVED -- both halves of a whole-path exemption, over one tree: the
        file is not reported, and an exemption whose file no longer carries the
        needle is itself reported. The second half is how
        `docs/change-queue.md`'s exemption expires at archive."""
        exemptions = {"docs/kept.md": "records what was observed on one date"}
        tree = self.tree(
            {
                "docs/kept.md": f"observed at {SUPERSEDED_MOUNT_PATH}\n",
                "docs/expired.md": "nothing here names the path\n",
            }
        )
        self.assertEqual(
            [],
            exemptions_naming_no_occurrence(exemptions, tree),
            "an exemption over a file that does name the path was reported stale",
        )
        self.assertNotEqual(
            [],
            exemptions_naming_no_occurrence(
                {"docs/expired.md": "entry 64, deleted at archive"}, tree
            ),
            "an exemption over a file that no longer names the path was NOT "
            "reported, so nothing would force its deletion once the occurrence it "
            "covers is gone",
        )

    def test_a_tree_the_sweep_can_read_nothing_in_is_a_failure_not_a_pass(self) -> None:
        """DERIVED -- a sweep that read nothing would otherwise report success
        having verified nothing."""
        empty = Path(tempfile.mkdtemp(prefix="platform-data-mount-empty-tree-"))
        with self.assertRaises(AssertionError):
            superseded_path_occurrences(empty)


if __name__ == "__main__":
    unittest.main()
