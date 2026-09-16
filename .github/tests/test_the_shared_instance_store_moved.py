"""Static-assertion tests for the shared PostgreSQL instance's store moving
onto the attached data volume.

Derived from the delta specifications of the OpenSpec change
`move-the-shared-database-onto-the-data-volume`, before any implementation of
that change existed -- from those deltas at commit `8547e77`, the commit
holding the approved plan. The path those deltas sit at is not written here: a
change's artifacts move when it is archived, and this repository's citation
convention is to name the change and the artifact in prose instead.

The change modifies three requirements, and each is form-dependent in a
different way:

* *No Store on This Host Holds Data Requiring Backup*
  (`openspec/specs/iac-safety-hardening/spec.md`) identifies the shared
  instance's store by name in its classification table, and that name moves.
* *A Destructive Window on the Shared Instance Is Announced to the Applications
  That Hold Databases in It* (`openspec/specs/iac-platform-services/spec.md`)
  triggered on the instance's VOLUME being discarded; after this change no such
  volume exists, so the trigger is restated against the store whatever form it
  takes.
* *The Host Carries an Operator-Declared Maintenance Window for the Shared
  Instance* (`openspec/specs/iac-host-configuration/spec.md`) obliged the
  declaration to live outside the store whose destruction is the window, and
  gains the clause that it live outside the VOLUME that store now sits on too.

WHAT THIS MODULE IS FOR, AND WHY IT IS A MODULE OF ITS OWN
----------------------------------------------------------
Four propositions, each a static read of a committed file and so in this
suite's stated subject (AGENTS.md, "Testing"):

1. Each environment's `group_vars` declares the `postgres` subdirectory with
   the ownership the image expects, and `platform/docker-compose.yml`'s bind
   source is one of the subdirectories those entries create. The two sides are
   edited in different pull requests of this change, and nothing else holds
   them to each other: a bind source the inventory does not create is made by
   Docker as an empty root-owned directory, the entrypoint finds no
   `PG_VERSION`, `initdb` makes a NEW EMPTY CLUSTER, and the deploy's `--wait`
   is satisfied by a healthy container over no application databases at all.
2. The maintenance declaration's path does not lie under the data volume's
   mount. Satisfied today -- the declaration is on the root disk -- so this
   protects a property rather than establishing one. Without it a later move of
   the declaration onto `/mnt/main` would put it inside the store whose
   destruction it announces, which is what the restated requirement forbids.
3. The reset recipe's container binds the store and never the bare mount. This
   is debt this change introduces rather than a hazard it removes: the act it
   replaces -- removing a named volume -- could not reach Prometheus's or
   Grafana's stores BY CONSTRUCTION, where a container given `/mnt/main` can
   destroy all three, and what stands between is otherwise a sentence in a
   document.
4. No committed file still names the superseded store, in either spelling.

It is a module of its own rather than a section of one beside it because these
tests were written by an author other than whoever implements the change, and
that author may only add. Two modules in this directory carry the superseded
store's name as a literal or read the reset recipe through a pattern that
matches only its old form, and re-pointing those is the implementing author's
task (this change's tasks.md 3.1 to 3.3), recorded in this change's
test-plan.md rather than performed here. NOTHING IN THIS FILE EDITS, DELETES OR
DISABLES AN EXISTING TEST. Where a helper a module beside this one already has
is needed, it is imported rather than restated, which is the idiom the modules
already here use.

That import also carries the third proposition's ONE PLACE. The declaration's
path is `WINDOW_DECLARATION` in the module deriving the probe-and-window
change, whose own assertions hold the role, the role's README and the upgrade
runbook to it -- so a move of the declaration that did not update that constant
is caught there rather than here, and this module reads the constant rather
than writing a fourth copy of the path.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_the_shared_instance_store_moved\\
        .TestNoCommittedFileStillNamesTheSupersededStore\\
        .test_no_committed_file_names_the_superseded_store

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling imports below resolve.

What no assertion here establishes
----------------------------------
Nothing here reads a host, runs Ansible, starts a container or copies a byte.
That `platform_data_volume` actually creates `/mnt/main/postgres` owned
`999:999` is role BEHAVIOUR and is established by that role's Molecule
scenarios over the subdirectory mechanism, which this change exercises with new
data rather than new code. That the copy is complete, that the instance comes
up on it, and that every database survived are readings of a host and are tasks
in this change, not assertions here. A green run establishes that the COMMITTED
FILES agree with one another about where the store is -- never that any host
has it there.

Nor does the sweep prove the sweep was complete. Its needles are the store's
two spellings, so it misses prose describing the store without naming it --
"the volume it announces", "after the volume reset above" -- and it is blind
inside its own exempt prefixes. This change's task list sends a human through
`platform/README.md`, `ansible/roles/deploy_user/` and two documents for
exactly that residue; it is caught by review or not at all.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from test_ci_configuration import (
    ROOT,
    _under,
    service_mounts,
    tracked_files,
    walked_files,
)
from test_a_shared_instance_reset_is_visible import (
    WINDOW_DECLARATION,
    WINDOW_DIRECTORY,
    _normalised_mode,
    load_tolerant_yaml,
    role_files,
    runbook_section,
)
from test_the_platform_data_mount_moved import role_default_mount_path

# --------------------------------------------------------------------------
# Identifiers this file names
# --------------------------------------------------------------------------

# The subdirectory of the mount the instance's store becomes. The MOUNT is read
# from the role's committed defaults rather than written down (that is what
# `role_default_mount_path` is for, and the module it comes from asserts that
# no inventory file overrides it); only the leaf is a literal, because nothing
# committed derives it -- it is this change's own choice of name, stated in its
# proposal as `/mnt/main/postgres`.
POSTGRES_SUBDIR = "postgres"

# The service that holds it, and the path the image expects its data under.
# The TARGET is the parent and not `.../data`: from 18 the image declares
# `VOLUME /var/lib/postgresql` and defaults `PGDATA` to
# `/var/lib/postgresql/<major>/docker`, and mounting the 17-and-earlier path
# makes the entrypoint refuse. That coupling is asserted in the module beside
# this one and is not restated here; what is needed here is only which mount of
# which service is the store.
POSTGRES_SERVICE = "postgres"
POSTGRES_DATA_TARGET = "/var/lib/postgresql"

# Where each environment's inventory declares what the role creates.
GROUP_VARS_DIRECTORY = "ansible/inventory/group_vars"
SUBDIRS_VARIABLE = "platform_data_volume_subdirs"

# The two environments running the platform stack as of this change. Named as a
# PREMISE only -- the assertions below are over every `group_vars` file that
# declares the subdirectory list, so a third environment is covered the day it
# is written, and these two are here so that a check reading neither of them
# reports that rather than passing over an empty population.
ENVIRONMENTS_RUNNING_THE_STACK = ("production.yml", "staging.yml")

# The ownership the image's own user carries, which is the convention the
# Prometheus (65534) and Grafana (472) entries already follow rather than a new
# rule. DERIVED, and deliberately labelled so: no scenario in any delta states
# a uid, a gid or a mode. They come from this change's design and task list,
# which state `999:999` and `0755` and give the reason for each -- `0755`
# rather than the image's own `1777`, because the sticky world-writable mode
# upstream exists so the image can run as an arbitrary uid, which this stack
# does not do.
POSTGRES_UID = "999"
POSTGRES_GID = "999"
POSTGRES_SUBDIR_MODE = "0755"

# The superseded store, in BOTH spellings. The bare one is what
# `platform/docker-compose.yml` declares and what prose about the stack uses;
# the prefixed one is what the host calls it, Compose having prefixed the
# project name. The bare needle subsumes the other as a substring, so sweeping
# it alone would find every occurrence -- both are named because the report has
# to say WHICH spelling was found, and because a later reader narrowing this to
# the prefixed one alone would silently stop seeing the stack-level spelling,
# which is the one this change actually deletes.
SUPERSEDED_STORE_NAMES = ("platform_postgres_data", "postgres_data")

# Prefix exemptions, each with a reason rather than a category.
#
# `openspec/` ENTIRE, not `openspec/changes/` alone. A change record names what
# it moves FROM, this change's own artifacts included; and
# `openspec/specs/iac-safety-hardening/spec.md` keeps the superseded row until
# `openspec archive` merges the delta into it, which happens in the change's
# LAST commit. A sweep exempting only `openspec/changes/` would be red for the
# whole life of the change, with no repair available short of hand-editing a
# main spec outside the archive mechanism -- and a red required check on every
# push is a check that gets ignored rather than read. It is the exemption the
# module beside this one takes, for this reason word for word.
#
# `.github/tests/` -- where a needle must be written down in order to assert
# its absence, and where fixture trees name the store on purpose.
EXEMPT_PREFIXES = ("openspec/", ".github/tests/")

# Whole-path exemptions. Each is a decision about a file this change does not
# edit, and each is checked below for still carrying a needle, so an exemption
# cannot outlive what it exempts.
EXEMPT_WHOLE_PATHS: dict[str, str] = {
    "ansible/roles/deploy_user/molecule/probe-and-window/verify.yml": (
        "stands up a store of its own to exercise the probe rather than "
        "describing this stack's -- the scenario creates, fills and removes a "
        "volume by that name inside its own container, so the name there is a "
        "fixture and not a claim about where the shared instance keeps its data"
    ),
}

# Exemptions scoped to a LINE rather than to a file, and this change needs the
# distinction rather than merely benefiting from it. `docs/backlog.md` names
# the store TWICE: once recording what staging held on 2026-09-13, which is a
# dated observation and would be made false by editing it, and once in
# `alert-on-the-exporter-being-unable-to-read-postgres`, which is present-tense
# and becomes false when this change lands. A whole-path exemption on that file
# would be green over both, and the second is the one this change's own task
# list exists to correct.
#
# The marker is a substring that must appear ON THE SAME LINE as the needle.
# It is read as a plain substring rather than as a pattern, and the assertion
# below reports an exemption whose marker no longer sits on a line carrying a
# needle, so an exemption cannot outlive the occurrence it describes.
EXEMPT_LINES: tuple[tuple[str, str, str], ...] = (
    (
        "docs/backlog.md",
        "so it holds stores:",
        "records what the staging host held on 2026-09-13, by the name it held "
        "it under on that date. Editing it would make it say something that was "
        "not observed",
    ),
)


# --------------------------------------------------------------------------
# 1. The inventory creates the directory the stack binds
# --------------------------------------------------------------------------


def _base(root: Path | None) -> Path:
    return ROOT if root is None else root


def group_vars_files(root: Path | None = None) -> list[Path]:
    """Every environment's `group_vars` file, sorted.

    Read by glob rather than by a list of names, so that a third environment is
    covered on the day its file is written rather than on the day someone
    remembers this module.
    """
    directory = _base(root) / GROUP_VARS_DIRECTORY
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.yml"))


def declared_subdirs(path: Path) -> list[dict]:
    """The `platform_data_volume_subdirs` entries a `group_vars` file declares.

    PARSED WITH THE VAULT-TOLERANT LOADER. A `group_vars` file carries
    Vault-encrypted values under `!vault` tags, which `yaml.safe_load` refuses
    outright -- so a plain parse here fails on every run for a reason that has
    nothing to do with what is being asserted, and the repair reached for would
    be a line-oriented read that cannot see a list entry's fields at all.
    """
    document = load_tolerant_yaml(path)
    if not isinstance(document, dict):
        raise AssertionError(f"{path} does not parse as a mapping")
    entries = document.get(SUBDIRS_VARIABLE)
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise AssertionError(
            f"{path} declares {SUBDIRS_VARIABLE} as {type(entries).__name__}, not a list"
        )
    return [entry for entry in entries if isinstance(entry, dict)]


def group_vars_declaring_subdirs(root: Path | None = None) -> list[Path]:
    """Every `group_vars` file that declares the subdirectory list at all.

    The assertions below are over this population rather than over every
    `group_vars` file, because an environment that runs no platform stack
    declares no subdirectory and owes no `postgres` entry. A premise assertion
    holds the population to containing the two environments that DO run the
    stack today, so an empty or shrunken population is reported rather than
    passed over.
    """
    return [path for path in group_vars_files(root) if declared_subdirs(path)]


def postgres_subdir_offences(root: Path | None = None) -> list[str]:
    """Report each `group_vars` file whose `postgres` subdirectory entry is
    absent or wrong."""
    base = _base(root)
    offences: list[str] = []
    for path in group_vars_declaring_subdirs(root):
        name = path.relative_to(base).as_posix()
        entries = [
            entry
            for entry in declared_subdirs(path)
            if str(entry.get("path", "")).strip("/") == POSTGRES_SUBDIR
        ]
        if not entries:
            declared = sorted(str(entry.get("path")) for entry in declared_subdirs(path))
            offences.append(
                f"{name} declares no {POSTGRES_SUBDIR!r} subdirectory; it declares "
                f"{declared}"
            )
            continue
        if len(entries) > 1:
            offences.append(
                f"{name} declares the {POSTGRES_SUBDIR!r} subdirectory {len(entries)} "
                "times, so which ownership the role applies depends on order"
            )
        entry = entries[0]
        for field, wanted in (
            ("owner", POSTGRES_UID),
            ("group", POSTGRES_GID),
            ("mode", POSTGRES_SUBDIR_MODE),
        ):
            raw = entry.get(field)
            # THE QUOTED FORM IS REQUIRED, not merely the value. DERIVED, and
            # this repository's own two entries and this change's task list both
            # write it that way. An unquoted `0755` is an integer under YAML
            # 1.1's octal rule and an unquoted `755` is a different mode
            # entirely, which is the trap the quoting exists to close; an
            # unquoted uid is an integer this check cannot tell from a login
            # name of the same spelling. `_normalised_mode` is what makes the
            # reported value legible whichever form was written, so the failure
            # names what was found rather than an integer.
            if not isinstance(raw, str):
                offences.append(
                    f"{name}: {POSTGRES_SUBDIR} {field} is written unquoted as "
                    f"{raw!r} ({_normalised_mode(raw)}); declare it as the quoted "
                    f'string "{wanted}", which is the form both other entries and '
                    "this change's task list use"
                )
                continue
            found = _normalised_mode(raw) if field == "mode" else raw
            if found != wanted:
                offences.append(
                    f"{name}: {POSTGRES_SUBDIR} {field} is {found!r}, not {wanted!r}"
                )
    return offences


def stack_postgres_bind_source(compose: Path | None = None) -> str:
    """The host path `platform/docker-compose.yml` binds as the shared
    instance's store.

    Refuses rather than returning a value nothing can be concluded from: a
    service with no mount, or with more than one, leaves this check unable to
    say which mount is the store, and returning the first would let a second
    mount arrive unread.
    """
    mounts = [
        mount for service, mount in service_mounts(compose) if service == POSTGRES_SERVICE
    ]
    if not mounts:
        raise AssertionError(
            f"the stack's {POSTGRES_SERVICE!r} service declares no mount at all, so it "
            "persists nothing outside its container's writable layer and there is no "
            "store for this check to read"
        )
    data = [mount for mount in mounts if mount["target"].rstrip("/") == POSTGRES_DATA_TARGET]
    if len(data) != 1:
        raise AssertionError(
            f"the stack's {POSTGRES_SERVICE!r} service declares {len(data)} mounts at "
            f"{POSTGRES_DATA_TARGET}, not exactly one: "
            f"{[mount['source'] for mount in mounts]}"
        )
    source = data[0]["source"]
    if not isinstance(source, str) or not source.strip():
        raise AssertionError(
            f"the stack's {POSTGRES_SERVICE!r} service mounts {POSTGRES_DATA_TARGET} from "
            f"{source!r}, which names no store this check can compare against"
        )
    return source.strip()


def store_disagreements(
    compose: Path | None = None, root: Path | None = None
) -> list[str]:
    """Report each `group_vars` file that does not create the directory the
    stack binds.

    The comparison is the STACK'S BIND SOURCE against the set of directories
    each inventory file creates -- `<mount path>/<entry path>` -- and it is
    written in that direction deliberately: `platform/docker-compose.yml`
    hardcodes one path for every stack, so an inventory file that creates a
    different set is an inventory file whose host the stack will bind a
    directory nothing created on. Docker then makes it as an empty root-owned
    directory, the entrypoint initialises a new empty cluster in it, and the
    deploy reports success.
    """
    base = _base(root)
    mount_path = role_default_mount_path(root).rstrip("/")
    source = stack_postgres_bind_source(compose)
    offences: list[str] = []
    for path in group_vars_declaring_subdirs(root):
        name = path.relative_to(base).as_posix()
        created = sorted(
            f"{mount_path}/{str(entry.get('path')).strip('/')}"
            for entry in declared_subdirs(path)
            if entry.get("path")
        )
        if source.rstrip("/") not in created:
            offences.append(
                f"{name} creates {created}, none of which is the {source!r} the stack "
                f"binds for {POSTGRES_SERVICE}"
            )
    return offences


class TestTheInventoryCreatesTheDirectoryTheStackBinds(unittest.TestCase):
    """SPECIFIED by iac-host-configuration / *Platform Data Volume Is Mounted
    at a Fixed Host Path*, scenario "Dependent subdirectories exist before a
    service needs them": the subdirectory a `platform/` service bind-mounts
    SHALL already exist under that mount, with the ownership that service
    requires. A bind source no inventory entry creates cannot satisfy that.

    The store is also the first row of iac-safety-hardening's *No Store on This
    Host Holds Data Requiring Backup* table, which identifies it by location --
    so a stack binding a location the inventory does not create makes that row
    name a store the host does not have.

    The two sides land in different pull requests of this change and nothing
    else holds them to each other.
    """

    def test_both_environments_running_the_stack_declare_the_subdirectory_list(self) -> None:
        """DERIVED -- the premise every assertion in this class rests on. They
        are written over "every `group_vars` file that declares the list", which
        is also what an empty population looks like: a check finding no file to
        examine reports a clean result identically."""
        declaring = {path.name for path in group_vars_declaring_subdirs()}
        missing = [name for name in ENVIRONMENTS_RUNNING_THE_STACK if name not in declaring]
        self.assertEqual(
            [],
            missing,
            f"these environments run the platform stack but declare no "
            f"{SUBDIRS_VARIABLE}: {missing}. The assertions in this class are over the "
            f"files that declare it, so their absence would make every one of them "
            f"pass having examined nothing; found {sorted(declaring)}",
        )

    def test_each_environment_declares_the_postgres_subdirectory(self) -> None:
        """DERIVED as to the uid, gid and mode -- see `POSTGRES_UID` above; no
        scenario in any delta states a number. What IS specified is that the
        directory exist with the ownership the service requires, and the
        ownership this change chose for it is the image's own user, exactly as
        Prometheus's entry carries 65534 and Grafana's 472.

        A directory owned by anything else is not inert: the entrypoint steps
        down to uid 999 and cannot create `18/` beneath a directory it may not
        write, so the instance fails to start -- loud, unlike the empty-cluster
        failure the assertion below catches, but a failure inside an announced
        window all the same.
        """
        offences = postgres_subdir_offences()
        self.assertEqual(
            [],
            offences,
            f"these environments do not declare the {POSTGRES_SUBDIR!r} subdirectory "
            f"as the PostgreSQL image's own user owns it: {offences}. The image starts "
            f"as root and steps down to {POSTGRES_UID}/{POSTGRES_GID}, so a directory "
            f"it cannot write is an instance that does not start",
        )

    def test_the_stack_binds_a_directory_each_environment_creates(self) -> None:
        """SPECIFIED -- see the class docstring. This is the assertion the other
        two are premises for, and it is the one that catches the failure mode
        this change's design calls the quiet one: Docker creates a missing bind
        source as an empty root-owned directory, `initdb` makes a new empty
        cluster in it, `docker compose up -d --wait` is satisfied, and the
        application meets a database that does not exist. Nothing in the
        deploy's output says what happened.
        """
        offences = store_disagreements()
        self.assertEqual(
            [],
            offences,
            f"the stack's {POSTGRES_SERVICE} bind source is not among the directories "
            f"these environments create: {offences}. A bind source nothing creates is "
            "made by Docker as an empty root-owned directory and initialised as a new "
            "empty cluster, and the deploy reports success over it",
        )


class TestTheInventoryAgreementDiscriminates(unittest.TestCase):
    """DERIVED. The checks above are RED as this module is written -- neither
    the inventory entry nor the bind source exists yet -- and will be green once
    both land. A check that read the wrong key, or compared nothing, would be
    green then too. These supply their own material and establish what each
    reports over it.
    """

    def fixture(
        self,
        subdirs: Mapping[str, Sequence[Mapping[str, str]]],
        bind_source: str,
        mount_path: str = "/mnt/main",
        vault_tag: bool = True,
    ) -> tuple[Path, Path]:
        """A scratch tree carrying a role default, one or more `group_vars`
        files and a stack definition.

        `vault_tag` puts a `!vault` value in each inventory file by default,
        because that is what the committed ones carry and it is what a plain
        `yaml.safe_load` refuses: a fixture without it would be green against a
        reader that cannot parse the real files at all.
        """
        directory = Path(tempfile.mkdtemp(prefix="shared-instance-store-fixture-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)

        defaults = directory / "ansible/roles/platform_data_volume/defaults/main.yml"
        defaults.parent.mkdir(parents=True, exist_ok=True)
        defaults.write_text(
            f"---\nplatform_data_volume_mount_path: {mount_path}\n", encoding="utf-8"
        )

        group_vars = directory / GROUP_VARS_DIRECTORY
        group_vars.mkdir(parents=True, exist_ok=True)
        for name, entries in subdirs.items():
            body = ["---"]
            if vault_tag:
                body.extend(
                    [
                        "ghcr_pull_token: !vault |",
                        "  $ANSIBLE_VAULT;1.1;AES256",
                        "  3635623133343963",
                    ]
                )
            if entries is not None:
                body.append(f"{SUBDIRS_VARIABLE}:")
                for entry in entries:
                    body.append(f"  - path: {entry['path']}")
                    for key in ("owner", "group", "mode"):
                        body.append(f"    {key}: \"{entry[key]}\"")
            (group_vars / name).write_text("\n".join(body) + "\n", encoding="utf-8")

        compose = directory / "platform" / "docker-compose.yml"
        compose.parent.mkdir(parents=True, exist_ok=True)
        compose.write_text(
            "services:\n"
            f"  {POSTGRES_SERVICE}:\n"
            "    image: postgres:18.6\n"
            "    volumes:\n"
            f"      - {bind_source}:{POSTGRES_DATA_TARGET}\n",
            encoding="utf-8",
        )
        return compose, directory

    def good(self) -> Mapping[str, Sequence[Mapping[str, str]]]:
        entry = {
            "path": POSTGRES_SUBDIR,
            "owner": POSTGRES_UID,
            "group": POSTGRES_GID,
            "mode": POSTGRES_SUBDIR_MODE,
        }
        prometheus = {"path": "prometheus", "owner": "65534", "group": "65534", "mode": "0755"}
        return {name: [prometheus, entry] for name in ENVIRONMENTS_RUNNING_THE_STACK}

    def test_the_arrangement_this_change_lands_is_not_reported(self) -> None:
        """DERIVED -- the converse of every discriminator below, so that they
        are not satisfied by a check that reports everything. This is also the
        shape the repository-level assertions above are red against today: it
        says what they will be green over."""
        compose, root = self.fixture(self.good(), f"/mnt/main/{POSTGRES_SUBDIR}")
        self.assertEqual([], postgres_subdir_offences(root))
        self.assertEqual([], store_disagreements(compose, root))

    def test_a_named_volume_bind_source_is_reported(self) -> None:
        """DERIVED -- THE discriminator this pair of checks stands or falls on,
        and the exact state of the tree before this change: the stack mounts the
        named volume `postgres_data` while the inventory creates a directory on
        the volume. A check reading only the inventory would be green over it."""
        compose, root = self.fixture(self.good(), "postgres_data")
        self.assertNotEqual(
            [],
            store_disagreements(compose, root),
            "a stack mounting the named volume against an inventory creating the "
            "directory was not reported, so these two checks do not hold the two "
            "sides of this change to each other",
        )

    def test_a_bind_source_no_entry_creates_is_reported(self) -> None:
        """DERIVED -- the near miss, and the one that produces an empty cluster
        rather than an error: a host path under the right mount that no
        inventory entry creates."""
        compose, root = self.fixture(self.good(), "/mnt/main/postgresql")
        self.assertNotEqual(
            [],
            store_disagreements(compose, root),
            "a bind source under the mount that no inventory entry creates was not "
            "reported -- Docker makes it as an empty root-owned directory and the "
            "instance initialises a new cluster in it",
        )

    def test_a_bind_source_only_one_environment_creates_is_reported(self) -> None:
        """DERIVED -- the half-landed state the two-pull-request split makes
        reachable: one environment's file edited and the other's forgotten. One
        Compose definition is deployed to every stack, so the host whose
        inventory was not edited is the one that comes up empty."""
        subdirs = dict(self.good())
        subdirs["staging.yml"] = [
            {"path": "prometheus", "owner": "65534", "group": "65534", "mode": "0755"}
        ]
        compose, root = self.fixture(subdirs, f"/mnt/main/{POSTGRES_SUBDIR}")
        self.assertNotEqual(
            [],
            store_disagreements(compose, root),
            "an environment creating no postgres directory was not reported while the "
            "other was, so a half-landed inventory edit reads as complete",
        )
        self.assertNotEqual(
            [],
            postgres_subdir_offences(root),
            "the missing entry itself was not reported either",
        )

    def test_the_wrong_ownership_is_reported(self) -> None:
        """DERIVED -- each of the three fields separately, because a check
        reading only `path` would be green over every one of them."""
        for field, value in (("owner", "472"), ("group", "0"), ("mode", "0700")):
            with self.subTest(field=field):
                entry = {
                    "path": POSTGRES_SUBDIR,
                    "owner": POSTGRES_UID,
                    "group": POSTGRES_GID,
                    "mode": POSTGRES_SUBDIR_MODE,
                }
                entry[field] = value
                subdirs = {name: [entry] for name in ENVIRONMENTS_RUNNING_THE_STACK}
                _, root = self.fixture(subdirs, f"/mnt/main/{POSTGRES_SUBDIR}")
                self.assertNotEqual(
                    [],
                    postgres_subdir_offences(root),
                    f"a {POSTGRES_SUBDIR} entry whose {field} is {value!r} was not "
                    "reported",
                )

    def test_an_unquoted_field_is_reported(self) -> None:
        """DERIVED -- the quoted form, which this check requires and which this
        discriminator is what established: WRITTEN FIRST AS A VALUE COMPARISON,
        it accepted an unquoted `999` outright, because a YAML integer and the
        string it prints as are indistinguishable once both are passed through
        `str`. The check now reads the declared type, and this is what holds it
        to that.

        The value of the quoting is not uniform across the three fields and the
        message says so: an unquoted uid is a value Ansible must decide between
        a number and a login name, where an unquoted `755` is simply a
        different mode. Requiring one form closes the family.
        """
        for field in ("owner", "group", "mode"):
            with self.subTest(field=field):
                entry = {
                    "path": POSTGRES_SUBDIR,
                    "owner": POSTGRES_UID,
                    "group": POSTGRES_GID,
                    "mode": POSTGRES_SUBDIR_MODE,
                }
                subdirs = {name: [entry] for name in ENVIRONMENTS_RUNNING_THE_STACK}
                _, root = self.fixture(subdirs, f"/mnt/main/{POSTGRES_SUBDIR}")
                path = root / GROUP_VARS_DIRECTORY / "staging.yml"
                quoted = f'{field}: "{entry[field]}"'
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        quoted, f"{field}: {entry[field]}"
                    ),
                    encoding="utf-8",
                )
                self.assertNotEqual(
                    [],
                    postgres_subdir_offences(root),
                    f"an unquoted {field} was accepted, so the check compares "
                    "something other than what the inventory actually declares",
                )

    def test_a_service_with_no_store_is_a_failure_not_a_pass(self) -> None:
        """DERIVED -- the read refuses rather than returning a value that would
        make the agreement check pass over a stack declaring no store at all."""
        directory = Path(tempfile.mkdtemp(prefix="shared-instance-store-empty-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        compose = directory / "platform" / "docker-compose.yml"
        compose.parent.mkdir(parents=True, exist_ok=True)
        compose.write_text(
            f"services:\n  {POSTGRES_SERVICE}:\n    image: postgres:18.6\n",
            encoding="utf-8",
        )
        with self.assertRaises(AssertionError):
            stack_postgres_bind_source(compose)

    def test_a_role_default_that_cannot_be_read_is_a_failure_not_a_pass(self) -> None:
        """DERIVED -- the other half of the same premise: the mount path the
        comparison is built from is read from the committed defaults, and an
        absent one would otherwise make every comparison meaningless."""
        directory = Path(tempfile.mkdtemp(prefix="shared-instance-store-no-role-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        with self.assertRaises(AssertionError):
            role_default_mount_path(directory)


# --------------------------------------------------------------------------
# 2. The declaration stays off the volume whose destruction it announces
# --------------------------------------------------------------------------


def declaration_offences(
    mount_path: str | None = None,
    declaration: str | None = None,
    root: Path | None = None,
) -> list[str]:
    """Report the maintenance declaration if it lies under the data volume's
    mount.

    CONTAINMENT IS COMPARED ON PATH COMPONENTS, NOT ON STRING PREFIXES, which
    `_under` in a module beside this one already does and this reuses:
    `/mnt/main` is a proper string prefix of `/mnt/main-data`, so a bare
    `startswith` would report a declaration on a different volume entirely.
    Equality is reported as well as strict containment -- a declaration AT the
    mount is inside it as surely as one beneath it.
    """
    mount = (role_default_mount_path(root) if mount_path is None else mount_path).rstrip("/")
    offences = []
    for label, path in (
        ("the declaration's directory", WINDOW_DIRECTORY if declaration is None else declaration),
        (
            "the declaration itself",
            WINDOW_DECLARATION
            if declaration is None
            else f"{declaration.rstrip('/')}/shared-postgres-window",
        ),
    ):
        candidate = path.rstrip("/")
        if candidate == mount or _under(mount, candidate):
            offences.append(
                f"{label} is {path}, which lies under the data volume mounted at {mount}"
            )
    return offences


def role_files_naming_the_mount(
    mount_path: str | None = None, root: Path | None = None
) -> list[str]:
    """Every committed file of the role that provisions the declaration which
    names a path under the data volume's mount, as `<path>:<line>`.

    A second reading, independent of the constant above. `declaration_offences`
    compares the path this suite holds every document to, so it catches a move
    that was carried through consistently; this catches the role acquiring a
    path on the volume in any other way -- a second file, a backup copy, a
    directory provisioned beside the declaration -- without anything having
    updated that constant.

    The role's Molecule scenarios are excluded by `role_files`, which is what
    that helper is for: a scenario naming a path is exercising it, not
    provisioning it.
    """
    mount = (role_default_mount_path(root) if mount_path is None else mount_path).rstrip("/")
    base = _base(root)
    files = role_files(root)
    if not files:
        raise AssertionError(
            "the role that provisions the maintenance declaration has no committed "
            "files, so this check would pass having read nothing"
        )
    found = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if mount in line:
                found.append(f"{path.relative_to(base).as_posix()}:{number}")
    return sorted(found)


class TestTheDeclarationDoesNotLieUnderTheVolume(unittest.TestCase):
    """SPECIFIED by iac-host-configuration / *The Host Carries an
    Operator-Declared Maintenance Window for the Shared Instance*, as this
    change restates it: the declaration SHALL live outside the store whose
    destruction is the window "and, where that store is a directory on an
    attached volume rather than a volume of its own, outside that volume too,
    so that the obligation does not turn on which form the store currently
    takes". Read with the scenario "The declaration survives the volume being
    discarded", whose WHEN this change restates against the store.

    THIS IS GREEN THE DAY IT IS WRITTEN, and that is what it is for. The
    declaration is on the root disk at `/var/lib/`, and the clause above is new
    -- so this protects a property rather than establishing one, and its value
    is entirely in the later change it stops. Moving the declaration onto
    `/mnt/main` would put it inside the store whose destruction it announces,
    and the way that failure presents is not an error: the window is declared,
    the store is cleared, the declaration goes with it, and every application's
    probe answers as though the window had been withdrawn -- in the middle of
    it. Because it is green at authoring, the fixtures in the sibling class are
    what establish that it can fail at all.
    """

    def test_the_declaration_does_not_lie_under_the_data_volume(self) -> None:
        """SPECIFIED -- see the class docstring."""
        offences = declaration_offences()
        self.assertEqual(
            [],
            offences,
            f"{offences}. The declaration announces that store's destruction, so a "
            "declaration inside it is destroyed by the act it announces -- every "
            "probe on the host then answers as though the window had been withdrawn, "
            "while it is still open",
        )

    def test_no_committed_file_of_the_role_names_a_path_under_the_mount(self) -> None:
        """DERIVED -- the independent reading described on
        `role_files_naming_the_mount`. It is wider than the requirement, which
        binds the declaration alone; it is written this way because the role
        provisioning the declaration has no business on the data volume at all,
        and a narrower check would be satisfied by a second file appearing
        beside the declaration under a different variable."""
        found = role_files_naming_the_mount()
        self.assertEqual(
            [],
            found,
            f"these committed files of the role that provisions the maintenance "
            f"declaration name a path under the data volume's mount: {found}. Nothing "
            "that has to survive the store's destruction belongs on the volume that "
            "holds it",
        )


class TestTheDeclarationContainmentCheckDiscriminates(unittest.TestCase):
    """DERIVED, and NOT OPTIONAL RIGOUR HERE. The two assertions above pass
    over the committed tree today and would pass identically if they compared
    nothing, read the wrong constant, or compared string prefixes. These supply
    their own material and establish that they do not.
    """

    def test_a_declaration_under_the_mount_is_reported(self) -> None:
        """DERIVED -- the discriminator the first assertion stands or falls on:
        the exact later change this check exists to stop."""
        self.assertNotEqual(
            [],
            declaration_offences("/mnt/main", "/mnt/main/platform-maintenance"),
            "a declaration provisioned under the data volume's mount was not "
            "reported, so this check would not notice the move it exists to stop",
        )

    def test_a_declaration_at_the_mount_itself_is_reported(self) -> None:
        """DERIVED -- equality as well as containment. A declaration written AT
        the mount is inside the volume as surely as one beneath it, and strict
        containment alone would accept it."""
        self.assertNotEqual(
            [],
            declaration_offences("/mnt/main", "/mnt/main"),
            "a declaration at the mount path itself was not reported",
        )

    def test_a_declaration_on_a_similarly_named_path_is_not_reported(self) -> None:
        """DERIVED -- the converse, and the reason containment is compared on
        path components: `/mnt/main` is a proper string prefix of
        `/mnt/main-data`, which is a different volume entirely. A `startswith`
        here would report a declaration that is nowhere near this store."""
        self.assertEqual(
            [],
            declaration_offences("/mnt/main", "/mnt/main-data/platform-maintenance"),
            "a declaration on a different volume whose name merely begins with the "
            "same characters was reported, so containment is being compared on string "
            "prefixes",
        )

    def test_the_declaration_where_it_actually_lives_is_not_reported(self) -> None:
        """DERIVED -- the converse over the real values, so the check above is
        not satisfied by one that reports everything."""
        self.assertEqual(
            [],
            declaration_offences("/mnt/main"),
            f"{WINDOW_DECLARATION} was reported as lying under /mnt/main",
        )

    def test_a_role_file_naming_the_mount_is_reported(self) -> None:
        """DERIVED -- the second reading's own discriminator, over a scratch
        copy of the role. Without it, that assertion is green over a role
        directory it failed to find."""
        directory = Path(tempfile.mkdtemp(prefix="shared-instance-store-role-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        tasks = directory / "ansible/roles/deploy_user/tasks/main.yml"
        tasks.parent.mkdir(parents=True, exist_ok=True)
        tasks.write_text(
            "---\n- name: Provision the declaration's directory\n"
            "  ansible.builtin.file:\n"
            "    path: /mnt/main/platform-maintenance\n"
            "    state: directory\n",
            encoding="utf-8",
        )
        self.assertNotEqual(
            [],
            role_files_naming_the_mount("/mnt/main", directory),
            "a role task provisioning a directory under the data volume's mount was "
            "not reported",
        )

    def test_a_role_directory_with_no_files_is_a_failure_not_a_pass(self) -> None:
        """DERIVED -- a read that reached no file would otherwise report a clean
        role having examined nothing."""
        directory = Path(tempfile.mkdtemp(prefix="shared-instance-store-no-role-files-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        with self.assertRaises(AssertionError):
            role_files_naming_the_mount("/mnt/main", directory)


# --------------------------------------------------------------------------
# 3. The reset recipe's container reaches the store and nothing beside it
# --------------------------------------------------------------------------

# `-v <source>:<target>` in either order of flags, and `--mount` with its
# comma-separated fields. Both forms are read because the recipe is written by
# hand and either is idiomatic; a check reading only `-v` would be blind to a
# recipe rewritten with the other.
BIND_FLAG = re.compile(r"(?:^|\s)-v\s+([^\s:]+):([^\s:]+)")
MOUNT_FLAG = re.compile(r"(?:^|\s)--mount[= ]([^\s]+)")


def runbook_host_binds(section: str) -> list[tuple[str, str]]:
    """Every (host source, container target) the recipe's commands bind.

    Only absolute sources are returned: a `-v name:/path` naming a Docker
    volume is not a host path and is not what this check is about.
    """
    binds: list[tuple[str, str]] = []
    for source, target in BIND_FLAG.findall(section):
        if source.startswith("/"):
            binds.append((source, target))
    for specification in MOUNT_FLAG.findall(section):
        fields = dict(
            field.split("=", 1) for field in specification.split(",") if "=" in field
        )
        source = fields.get("source") or fields.get("src") or ""
        if source.startswith("/"):
            binds.append((source, fields.get("target") or fields.get("dst") or ""))
    return binds


def reset_recipe_bind_offences(root: Path | None = None) -> list[str]:
    """Report the reset recipe's container binds that reach past the store.

    Two findings, and they are different failures rather than two readings of
    one. A recipe that binds NOTHING under the mount does not perform the act
    this change makes the destructive step, and an assertion about what it may
    not reach would pass over it vacuously. A recipe that binds the mount ITSELF
    is the debt this change introduces: the act it replaces -- removing a named
    volume -- could not reach Prometheus's or Grafana's data by construction,
    and a container given `/mnt/main` can destroy all three.
    """
    mount = role_default_mount_path(root).rstrip("/")
    store = f"{mount}/{POSTGRES_SUBDIR}"
    binds = runbook_host_binds(runbook_section(root))

    offences = []
    if not any(
        source.rstrip("/") == store or _under(store, source) for source, _ in binds
    ):
        offences.append(
            f"no command in the procedure binds {store} into a container, so the "
            "recipe does not clear the store where it now lives -- and this check's "
            "other half would pass over it having found nothing to judge"
        )
    for source, target in binds:
        candidate = source.rstrip("/")
        if candidate == store or _under(store, candidate):
            continue
        if candidate == mount or _under(mount, candidate):
            offences.append(
                f"the procedure binds {source} at {target}, which reaches past the "
                f"shared instance's store to everything else on the data volume"
            )
    return offences


class TestTheResetRecipeBindsTheStoreAndNothingBeside(unittest.TestCase):
    """SPECIFIED by iac-platform-services / *A Destructive Window on the Shared
    Instance Is Announced to the Applications That Hold Databases in It*, as
    this change restates it: "a procedure that clears a directory destroys
    exactly what a procedure that removed a volume destroyed", and a procedure
    in this repository that discards or re-initialises the instance's data is
    bound by the whole requirement.

    What this adds to the requirement's own obligations is the BOUND ON WHAT
    ELSE that procedure can destroy, which this change's design names as debt
    it introduces rather than a hazard it removes. `docker volume rm
    platform_postgres_data` could not reach Prometheus's or Grafana's store by
    construction. Its replacement is a container over a directory one path
    component away from both, and what otherwise stands between them is a
    sentence in a document.

    RED WHEN THIS MODULE WAS WRITTEN, and on the first of its two findings: the
    procedure still removes a named volume and binds nothing at all. That is
    the target-absent state, not a defect in the check.
    """

    def test_the_procedure_binds_the_store_and_never_the_bare_mount(self) -> None:
        """SPECIFIED as to the act, DERIVED as to the bound -- see the class
        docstring."""
        offences = reset_recipe_bind_offences()
        self.assertEqual(
            [],
            offences,
            f"{offences}. The store is one path component from Prometheus's and "
            "Grafana's data, and a recursive operation rooted at the mount reaches "
            "all three -- binding only the store means the container has no path to "
            "the others even if a command inside it is wrong",
        )


class TestTheResetRecipeCheckDiscriminates(unittest.TestCase):
    """DERIVED. The assertion above is red today for one reason and will be
    green for another; neither result says the check can tell a good recipe from
    a dangerous one. These supply their own runbook and establish that it can.
    """

    def runbook(self, body: str, mount_path: str = "/mnt/main") -> Path:
        directory = Path(tempfile.mkdtemp(prefix="shared-instance-store-runbook-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        defaults = directory / "ansible/roles/platform_data_volume/defaults/main.yml"
        defaults.parent.mkdir(parents=True, exist_ok=True)
        defaults.write_text(
            f"---\nplatform_data_volume_mount_path: {mount_path}\n", encoding="utf-8"
        )
        readme = directory / "platform" / "README.md"
        readme.parent.mkdir(parents=True, exist_ok=True)
        readme.write_text(
            "## Operating the shared stack\n\n"
            "### Upgrading the PostgreSQL major version\n\n"
            f"{body}\n\n"
            "## Monitoring and alerting\n\nnothing here is the procedure.\n",
            encoding="utf-8",
        )
        return directory

    def test_a_recipe_binding_only_the_store_is_not_reported(self) -> None:
        """DERIVED -- the shape this change's task list prescribes, so the
        discriminators below are not satisfied by a check reporting everything.
        """
        root = self.runbook(
            "       docker run --rm -v /mnt/main/postgres:/store postgres:18.6 \\\n"
            "         sh -c 'find /store -mindepth 1 -delete'\n"
        )
        self.assertEqual(
            [],
            reset_recipe_bind_offences(root),
            "a recipe binding only the store was reported as an offence",
        )

    def test_a_recipe_binding_the_bare_mount_is_reported(self) -> None:
        """DERIVED -- THE discriminator this check exists for. The command
        inside the container is identical; what differs is that this one can
        reach Prometheus's and Grafana's stores."""
        root = self.runbook(
            "       docker run --rm -v /mnt/main:/store postgres:18.6 \\\n"
            "         sh -c 'find /store/postgres -mindepth 1 -delete'\n"
        )
        self.assertNotEqual(
            [],
            reset_recipe_bind_offences(root),
            "a recipe binding the bare mount was not reported, even though the "
            "container it describes can destroy all three stores on the volume",
        )

    def test_a_recipe_binding_the_mount_through_the_long_form_is_reported(self) -> None:
        """DERIVED -- the same offence written with `--mount`, which a check
        reading only `-v` would be blind to."""
        root = self.runbook(
            "       docker run --rm --mount type=bind,source=/mnt/main,target=/store \\\n"
            "         postgres:18.6 sh -c 'find /store/postgres -mindepth 1 -delete'\n"
        )
        self.assertNotEqual(
            [],
            reset_recipe_bind_offences(root),
            "a `--mount` binding the bare mount was not reported, so the check reads "
            "only one of the two forms the recipe may be written in",
        )

    def test_a_recipe_binding_a_sibling_store_is_reported(self) -> None:
        """DERIVED -- the narrower near miss: not the mount itself, but another
        store on it. Nothing in this procedure has business under Prometheus's
        directory."""
        root = self.runbook(
            "       docker run --rm -v /mnt/main/prometheus:/store postgres:18.6 \\\n"
            "         sh -c 'find /store -mindepth 1 -delete'\n"
        )
        self.assertNotEqual(
            [],
            reset_recipe_bind_offences(root),
            "a recipe binding another store on the same volume was not reported",
        )

    def test_a_recipe_binding_nothing_is_reported(self) -> None:
        """DERIVED -- the vacuity guard, and the state the procedure is in as
        this module is written: it removes a named volume and binds no host
        path, so a check written only as a prohibition would be green over a
        recipe that does not perform the act at all."""
        root = self.runbook(
            "       docker rm -f platform-postgres-1\n"
            "       docker volume rm platform_postgres_data\n"
        )
        self.assertNotEqual(
            [],
            reset_recipe_bind_offences(root),
            "a procedure binding no host path at all was not reported, so the "
            "prohibition half of this check passes over a recipe it never read",
        )

    def test_a_recipe_binding_a_path_on_another_volume_is_not_reported(self) -> None:
        """DERIVED -- containment on path components again: `/mnt/main-data` is
        a different volume whose name begins with the same characters, and a
        `startswith` would report it while missing nothing real."""
        root = self.runbook(
            "       docker run --rm -v /mnt/main/postgres:/store \\\n"
            "         -v /mnt/main-data/archive:/archive postgres:18.6 sh -c 'true'\n"
        )
        self.assertEqual(
            [],
            reset_recipe_bind_offences(root),
            "a bind on a different volume was reported as reaching past the store",
        )

    def test_a_runbook_with_no_such_section_is_a_failure_not_a_pass(self) -> None:
        """DERIVED -- a section that could not be found would otherwise leave
        every assertion above reading an empty string, which reports no
        offending bind at all."""
        directory = Path(tempfile.mkdtemp(prefix="shared-instance-store-no-section-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        readme = directory / "platform" / "README.md"
        readme.parent.mkdir(parents=True, exist_ok=True)
        readme.write_text("## Operating the shared stack\n\nnothing here.\n", encoding="utf-8")
        with self.assertRaises(AssertionError):
            runbook_section(directory)


# --------------------------------------------------------------------------
# 4. Nothing still names the superseded store
# --------------------------------------------------------------------------


def _needle_in(line: str) -> str | None:
    """The longest superseded spelling the line carries, or None.

    Longest first, so a line carrying `platform_postgres_data` is reported
    under that name rather than under the bare substring inside it -- one
    offence per line either way, and the report says which spelling to look
    for.
    """
    for needle in sorted(SUPERSEDED_STORE_NAMES, key=len, reverse=True):
        if needle in line:
            return needle
    return None


def superseded_store_occurrences(
    root: Path | None = None,
    exemptions: Mapping[str, str] | None = None,
    line_exemptions: Iterable[tuple[str, str, str]] | None = None,
) -> list[str]:
    """Every committed file still naming the superseded store, as
    `<path>:<line>: <spelling>`.

    THE FILE SET IS TRACKED FILES, NOT A FILESYSTEM WALK, for the reason
    `tracked_files()` itself records: a walk reads `.molecule-home/` and sibling
    working trees under `.claude/worktrees/`, which do not exist in continuous
    integration and appear the moment a developer follows this repository's own
    Molecule instructions. A check that disagrees with itself between a working
    machine and a runner trains its readers to discount it.

    A `root` argument means a scratch tree instead, which is NOT a repository
    and has no tracked files, so those are walked. That path exists for the
    discriminators below and is not a second way of reading the repository.

    `exemptions` and `line_exemptions` substitute for the module-level ones, so
    that the exempting half can be exercised over a scratch tree rather than
    asserted only by the repository-level sweep happening to be green.

    Raises rather than reporting a clean tree when it reads no file at all: a
    sweep that read nothing would otherwise report success having verified
    nothing.
    """
    whole_paths = EXEMPT_WHOLE_PATHS if exemptions is None else exemptions
    lines = EXEMPT_LINES if line_exemptions is None else tuple(line_exemptions)
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
    for name, text in sorted(contents.items()):
        if name.startswith(EXEMPT_PREFIXES) or name in whole_paths:
            continue
        markers = [marker for path, marker, _ in lines if path == name]
        for number, line in enumerate(text.splitlines(), start=1):
            needle = _needle_in(line)
            if needle is None:
                continue
            if any(marker in line for marker in markers):
                continue
            offences.append(f"{name}:{number}: {needle}")
    return sorted(offences)


def exemptions_naming_no_occurrence(
    exemptions: Mapping[str, str] | None = None,
    line_exemptions: Iterable[tuple[str, str, str]] | None = None,
    root: Path | None = None,
) -> list[str]:
    """Every exemption that no longer describes anything.

    This is how an exemption expires. A file exempted because it names the
    store is reported once it stops naming it -- or once it stops existing --
    so the exemption is deleted in the same commit rather than left standing
    over a file it no longer describes. A LINE exemption is held to more: its
    marker must still sit on a line that carries a needle, so a marker that
    drifted onto a different sentence, or a sentence that was reworded around
    it, is reported rather than silently exempting nothing -- or, worse,
    exempting a line the sweep should have caught.
    """
    whole_paths = EXEMPT_WHOLE_PATHS if exemptions is None else exemptions
    lines = EXEMPT_LINES if line_exemptions is None else tuple(line_exemptions)
    base = _base(root)

    stale: list[str] = []
    for name, reason in sorted(whole_paths.items()):
        path = base / name
        if not path.is_file():
            stale.append(f"{name} (exempt because {reason}) no longer exists")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not any(needle in text for needle in SUPERSEDED_STORE_NAMES):
            stale.append(f"{name} (exempt because {reason}) no longer names the store")

    for name, marker, reason in lines:
        path = base / name
        if not path.is_file():
            stale.append(f"{name} (line exemption, because {reason}) no longer exists")
            continue
        matched = [
            line
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if marker in line and _needle_in(line) is not None
        ]
        if not matched:
            stale.append(
                f"{name} (line exemption on {marker!r}, because {reason}) matches no "
                "line that names the store"
            )
    return stale


class TestNoCommittedFileStillNamesTheSupersededStore(unittest.TestCase):
    """SPECIFIED by iac-safety-hardening / *No Store on This Host Holds Data
    Requiring Backup*, scenario "A classified store moves between the host's
    disks": "the table SHALL name it at the location it then occupies, so that
    no row names a store the host no longer has". A committed file naming a
    store the host no longer has is the same defect one directory over, and the
    sweep is what makes that decidable rather than a matter of whether anyone
    remembered the file.

    The failure this catches is a stale sentence, which fails nothing on its
    own: a runbook sending an operator to remove a volume that is not there, a
    backlog entry describing where a role lives, a comment explaining a
    coupling in terms of a form the stack no longer uses. Half a move leaves a
    reader unable to tell which of the two words is load-bearing, and the next
    window is where they find out.

    Its scope is written out rather than left to be read off the code -- see
    `EXEMPT_PREFIXES`, `EXEMPT_WHOLE_PATHS` and `EXEMPT_LINES` above, each of
    which carries its own reason.

    RED WHEN THIS MODULE WAS WRITTEN, over `platform/docker-compose.yml`,
    `platform/README.md` and one entry of `docs/backlog.md` -- the files this
    change's own task list edits.
    """

    def test_no_committed_file_names_the_superseded_store(self) -> None:
        """SPECIFIED -- see the class docstring."""
        offences = superseded_store_occurrences()
        self.assertEqual(
            [],
            offences,
            f"these committed files still name the shared instance's superseded "
            f"store: {offences}. After this change the instance keeps its data in a "
            f"directory on the data volume and no such volume exists, so each of "
            "these is a sentence describing a store the host does not have",
        )

    def test_the_openspec_tree_names_the_store_and_is_not_reported(self) -> None:
        """DERIVED -- the `openspec/` prefix exemption, established over the
        repository because a scratch tree cannot establish it: the walker the
        scratch path uses prunes `openspec` itself.

        Both halves are asserted together so the exemption cannot go vacuous:
        that the tracked `openspec/` tree DOES name the store -- it always
        will, because an archived record names what its change moved from --
        and that the sweep reports none of it.
        """
        naming = sorted(
            name
            for name, raw in tracked_files().items()
            if name.startswith("openspec/")
            and _needle_in(raw.decode("utf-8", errors="replace")) is not None
        )
        self.assertNotEqual(
            [],
            naming,
            "no tracked file under `openspec/` names the superseded store, so the "
            "prefix exemption is exempting nothing and this assertion establishes "
            "nothing about it",
        )
        reported = [
            offence for offence in superseded_store_occurrences()
            if offence.startswith("openspec/")
        ]
        self.assertEqual(
            [],
            reported,
            f"the sweep reported occurrences under `openspec/`: {reported}. A change "
            "record names what it moves FROM, and the main specification keeps the "
            "superseded row until `openspec archive` merges the delta into it in the "
            "change's LAST commit -- so a sweep reaching there is red for the whole "
            "life of the change, with no repair short of hand-editing a main spec "
            "outside the archive mechanism",
        )

    def test_every_exemption_still_names_the_store(self) -> None:
        """DERIVED -- an exemption naming a path that no longer carries a
        needle, or a line marker that no longer sits on one, is itself an
        offence. This is the mechanism by which an exemption is deleted in the
        commit that removes what it covered rather than left standing as a hole
        nobody can see."""
        stale = exemptions_naming_no_occurrence()
        self.assertEqual(
            [],
            stale,
            f"these exemptions no longer describe anything: {stale}. An exemption "
            "that outlives its reason is a hole in the sweep nobody can see; delete "
            "it in the same commit that removed the occurrence",
        )


class TestTheSweepDiscriminates(unittest.TestCase):
    """DERIVED. The sweep reports a clean tree by finding nothing, which is also
    what it would report having read the wrong thing, having had its needles
    drift, or having exempted more than it meant to. These build scratch trees
    and establish what it reports over each.
    """

    def tree(self, files: Mapping[str, str]) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="shared-instance-store-sweep-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        for name, text in files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return directory

    def test_the_sweep_reaches_every_anchor_this_change_edits(self) -> None:
        """DERIVED -- `platform/`, `docs/` and `ansible/` are where every file
        this change edits outside the two exempt prefixes lives."""
        tree = self.tree(
            {
                "platform/docker-compose.yml": "      - postgres_data:/var/lib/postgresql\n",
                "platform/README.md": "       docker volume rm platform_postgres_data\n",
                "docs/backlog.md": "the role lives in `postgres_data` and is recreated\n",
                "ansible/inventory/group_vars/staging.yml": "# postgres_data is the store\n",
            }
        )
        self.assertEqual(
            [
                "ansible/inventory/group_vars/staging.yml:1: postgres_data",
                "docs/backlog.md:1: postgres_data",
                "platform/README.md:1: platform_postgres_data",
                "platform/docker-compose.yml:1: postgres_data",
            ],
            superseded_store_occurrences(tree, exemptions={}, line_exemptions=()),
            "the sweep did not report an occurrence under each anchor this change "
            "edits, or reported one under the wrong spelling",
        )

    def test_the_bare_spelling_is_caught_where_the_prefixed_one_would_be_missed(self) -> None:
        """DERIVED -- and this is why the needle was widened. The prefixed
        spelling is what the HOST calls the store; the bare one is what the
        stack definition declares and what prose about the stack uses. A sweep
        for the prefixed name alone reports this file as clean."""
        tree = self.tree(
            {"docs/backlog.md": "the `pgexporter` role lives in `postgres_data`\n"}
        )
        self.assertEqual(
            ["docs/backlog.md:1: postgres_data"],
            superseded_store_occurrences(tree, exemptions={}, line_exemptions=()),
            "prose naming the stack-level spelling was not reported, so the narrower "
            "needle is in force and the Compose-level name can survive this change",
        )

    def test_the_tests_prefix_is_not_swept(self) -> None:
        """DERIVED -- `.github/tests/`, where a needle must be written down in
        order to assert its absence and where fixture trees name the store on
        purpose.

        The `openspec/` half of the same exemption is NOT exercised here and
        could not be: `walked_files()`, which is what reads a scratch tree,
        prunes `openspec` at the walk root, so a fixture would be green whether
        or not the prefix exemption existed. It is established over the
        repository instead, by the sibling class's
        `test_the_openspec_tree_names_the_store_and_is_not_reported`.
        """
        tree = self.tree(
            {
                ".github/tests/test_something.py": 'STORE = "platform_postgres_data"\n',
                "docs/swept.md": "platform_postgres_data in prose\n",
            }
        )
        self.assertEqual(
            ["docs/swept.md:1: platform_postgres_data"],
            superseded_store_occurrences(tree, exemptions={}, line_exemptions=()),
            "a module of this suite naming the needle was reported, or a file outside "
            "the exempt prefix was missed",
        )

    def test_a_whole_path_exemption_is_not_swept_but_must_still_name_the_store(self) -> None:
        """DERIVED -- both halves of a whole-path exemption over one tree: the
        file is not reported, and an exemption whose file no longer carries a
        needle is itself reported."""
        exemptions = {"ansible/roles/x/molecule/y/verify.yml": "stands up a store of its own"}
        tree = self.tree(
            {
                "ansible/roles/x/molecule/y/verify.yml": (
                    "        docker volume rm -f platform_postgres_data\n"
                ),
                "docs/expired.md": "nothing here names the store\n",
            }
        )
        self.assertEqual(
            [],
            superseded_store_occurrences(tree, exemptions, ()),
            "the exempt file's occurrence was reported, so a whole-path exemption does "
            "not actually exempt",
        )
        self.assertNotEqual(
            [],
            superseded_store_occurrences(tree, {}, ()),
            "the same tree with no exemption reported nothing, so the assertion above "
            "passes whether or not the exemption does any work",
        )
        self.assertEqual(
            [],
            exemptions_naming_no_occurrence(exemptions, (), tree),
            "an exemption over a file that does name the store was reported stale",
        )
        self.assertNotEqual(
            [],
            exemptions_naming_no_occurrence(
                {"docs/expired.md": "an entry deleted at archive"}, (), tree
            ),
            "an exemption over a file that no longer names the store was NOT reported, "
            "so nothing would force its deletion once the occurrence it covers is gone",
        )

    def test_a_line_exemption_covers_that_occurrence_and_not_the_file(self) -> None:
        """DERIVED -- and this is the case the line scoping exists for, taken
        from the file that forced it. `docs/backlog.md` names the store twice:
        once recording what a host held on a date, which is exempt because
        editing it would make it say something that was not observed, and once
        in a present-tense entry this change corrects. A whole-path exemption
        would be green over both."""
        exemptions = (("docs/backlog.md", "so it holds stores:", "a dated observation"),)
        tree = self.tree(
            {
                "docs/backlog.md": (
                    "It became live on 2026-09-13, so it holds stores: "
                    "`platform_postgres_data` and others.\n"
                    "The `pgexporter` role lives in `postgres_data` and is recreated "
                    "by hand.\n"
                )
            }
        )
        self.assertEqual(
            ["docs/backlog.md:2: postgres_data"],
            superseded_store_occurrences(tree, {}, exemptions),
            "the line exemption covered more than the line its marker sits on, or "
            "covered nothing at all -- the second occurrence is the one this change's "
            "task list corrects rather than exempts",
        )

    def test_a_line_exemption_whose_marker_has_drifted_is_reported(self) -> None:
        """DERIVED -- the expiry half, and stricter than the whole-path one: a
        marker that no longer sits on a line naming the store exempts nothing,
        or worse exempts a line the sweep should have caught, and either way it
        must be rewritten rather than left standing."""
        exemptions = (("docs/backlog.md", "so it holds stores:", "a dated observation"),)
        tree = self.tree(
            {
                "docs/backlog.md": (
                    "It became live on 2026-09-13, so it holds stores: three of them.\n"
                    "One of them was `platform_postgres_data`.\n"
                )
            }
        )
        self.assertNotEqual(
            [],
            exemptions_naming_no_occurrence({}, exemptions, tree),
            "a line exemption whose marker no longer sits on a line naming the store "
            "was not reported, so a reworded sentence leaves an exemption standing "
            "over nothing",
        )

    def test_a_tree_the_sweep_can_read_nothing_in_is_a_failure_not_a_pass(self) -> None:
        """DERIVED -- a sweep that read nothing would otherwise report success
        having verified nothing."""
        empty = Path(tempfile.mkdtemp(prefix="shared-instance-store-empty-tree-"))
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        with self.assertRaises(AssertionError):
            superseded_store_occurrences(empty)


if __name__ == "__main__":
    unittest.main()
