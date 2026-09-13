"""Static-assertion tests for a Terraform root named for the stack it holds.

Derived from the delta specs of the OpenSpec change
`rename-terraform-environments-to-stacks`, before any implementation of that
change existed -- from that change's delta specifications at commit `541dec8`,
which is the commit holding the approved plan. The path those deltas sit at is
not written here: a change's artifacts move when it is archived, and this
repository's citation convention is to name the change and the artifact in
prose instead. The deltas span six capabilities -- `iac-cicd-pipeline`,
`iac-repo-foundations`, `iac-safety-hardening`, `iac-state-management`,
`iac-server-lifecycle` and `iac-data-volumes` -- and every one of their
twenty-one requirements is MODIFIED rather than ADDED. Each section below names
the requirement it traces to.

Every assertion is annotated SPECIFIED (it traces to SHALL text or to a
scenario in a delta spec) or DERIVED (it traces to that change's `design.md` or
`tasks.md` rather than to a scenario). See that change's `test-plan.md` for the
scenario-to-test mapping, the baseline, the scenarios deliberately left
uncovered, the obsolete-test candidates, and the project questions this file
took an assumption on.

What this change is, and why that shapes the tests
--------------------------------------------------
The change is a rename with no live effect: `terraform/environments/` becomes
`terraform/stacks/`, and the vocabulary the pipeline iterates with follows the
path. Every delta therefore states BEHAVIOUR THAT ALREADY HOLDS, in words the
tree does not yet use. So the assertions below are almost all reads of the new
path and the new identifiers -- which is what the change actually makes true --
rather than re-assertions of pipeline behaviour the suite already covers under
the old vocabulary.

Two consequences, both deliberate:

- Before the implementation exists these tests fail in the second of the four
  failure states `testing` enumerates: the TARGET IS ABSENT. `terraform/stacks/`
  does not exist and the workflows still say `environment`, so nothing here has
  yet exercised an assertion. Do not read a red run as evidence about the
  assertions themselves.
- Several assertions look like duplicates of ones in the modules beside this
  one. They are not: the existing ones are keyed on `terraform/environments`
  and on `matrix.environment`, and are superseded by this change. Re-expressing
  them is the implementing author's task (that change's tasks.md 4.1 and 4.2)
  and is recorded in `test-plan.md`'s obsolete list rather than performed here.
  NOTHING IN THIS FILE EDITS, DELETES OR DISABLES AN EXISTING TEST.

Why this is a ninth module rather than a section of an existing one
-------------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
and that author may only add. That change's tasks.md 4.4 also records that the
suite's MODULE FILENAMES AND TEST-METHOD NAMES are deliberately left in the old
vocabulary -- renaming them would churn several hundred identifiers without
changing what a single one checks, and is deferred to `docs/change-queue.md`
entry 62. So the old names beside this file are a recorded decision, not an
oversight, and this module does not try to correct them.

    `TestEveryModuleInTheSuiteDirectoryNeedsNoPrivilegedResource` in
    `test_ci_configuration.py` reads every module in this directory, so this
    file is held to the no-network, no-credential, no-container,
    no-Terraform-binary constraint by that class. It is written to satisfy it:
    standard library, `yaml`, and the helpers of the module beside it. It
    spawns nothing at all.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_terraform_stacks_are_the_iterated_unit\\
        .TestTheTerraformRootIsNamedForTheStack\\
        .test_the_stack_root_holds_the_stack_directories

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the helper import below resolve.

What no assertion here establishes
----------------------------------
Nothing in this file reads repository settings, makes a network call, or runs
Terraform. Whether a Hetzner API token is scoped to one project, whether an HCP
Terraform workspace is set to Local execution, whether a GitHub Environment
requires a reviewer, and what `terraform plan` would actually show are all
outside this suite's subject (AGENTS.md, "Testing"). Many of this change's
ninety-eight scenarios are about exactly those, and `test-plan.md` records each
of them as uncovered with that reason rather than omitting it. A green run here
establishes that the committed files NAME the stack root and the stack
vocabulary -- never that any cloud resource was renamed, because this change
renames none.
"""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

import yaml

from test_ci_configuration import (
    APPLY,
    DEPENDABOT,
    PR_VALIDATION,
    ROOT,
    WORKFLOWS,
    compact,
    jobs,
    load_yaml,
    read_text,
    step_label,
    steps,
    triggers,
    tracked_files,
    uncommented,
    walked_files,
)

# --------------------------------------------------------------------------
# Identifiers this file names, and why each is a constraint of the test layer
# rather than a property the specification states.
#
# `drift.yml` and `host-converge.yml` are the two workflows
# `test_ci_configuration.py` does not name. The deltas speak of "a scheduled
# GitHub Actions workflow" and of the host-configuration workflow; these are
# what those resolve to here. They are re-derived rather than imported from the
# modules that already define them, so that this module depends on one sibling
# rather than three.
# --------------------------------------------------------------------------

DRIFT = WORKFLOWS / "drift.yml"
HOST_CONVERGE = WORKFLOWS / "host-converge.yml"

# The three workflows that discover, plan, apply and drift-check a stack. The
# fourth body -- host-converge's -- is deliberately different: it enumerates
# `ansible/inventory/*.hcloud.yml` rather than the Terraform root, and reads
# each stack's declaration out of the Terraform root afterwards. See that
# change's design.md decision 2a, which settles which of that body's derived
# surfaces are the stack and which are the environment.
TERRAFORM_WORKFLOWS = (PR_VALIDATION, APPLY, DRIFT)
DISCOVERY_WORKFLOWS = TERRAFORM_WORKFLOWS + (HOST_CONVERGE,)

# The new Terraform root, as a path and as the literal the workflows carry.
STACK_ROOT_SEGMENT = "terraform/stacks"
STACK_ROOT = ROOT / "terraform" / "stacks"

# The old root, ASSEMBLED FROM PARTS RATHER THAN WRITTEN.
#
# `TestNoCommittedFileStillNamesTheOldTerraformRoot` below sweeps every
# committed file for this string. Written as one literal it would make this
# module its own counter-example, and -- worse -- would make a reader grepping
# the tree for stale occurrences land on the check that exists to forbid them.
# The sweep also excludes this module by path, for the docstrings and failure
# messages that necessarily name the old root in prose; the two guards are
# independent on purpose, so that removing either leaves the other standing.
OLD_ROOT_SEGMENT = "terraform/" + "environments"

# The directory's own name, with no prefix, taken from the constant above
# rather than written out a second time -- the assembly rule stated there
# applies to every literal in this module, not only to the first one.
OLD_ROOT_DIRECTORY = OLD_ROOT_SEGMENT.rpartition("/")[2]

# What counts as still naming the old root. The union of two shapes, and the
# second is why this is a regular expression rather than a substring:
#
#   1. the PREFIXED path, with or without a trailing slash, exactly as the
#      constant above spells it; and
#   2. a BARE reference to the directory -- the word immediately followed by a
#      slash, whatever prefix it carries or none at all.
#
# The second was added after code review found two committed files naming the
# directory without its `terraform/` prefix -- a `.tftest.hcl` comment reading
# "(not environments/prod)" and a `docs/change-queue.md` entry -- over which
# the sweep reported a clean tree. The instances were corrected; this closes
# the class.
#
# It keys on the PATH-LIKE SHAPE and never on the word. The lookbehind rejects
# a longer identifier that merely ends in it.
OLD_ROOT_REFERENCE = re.compile(
    re.escape(OLD_ROOT_SEGMENT)
    + r"|(?<![A-Za-z0-9_-])"
    + re.escape(OLD_ROOT_DIRECTORY)
    + "/"
)

# Identifiers the rename retires, each with the surface it lived on. Asserted
# ABSENT from the four workflows, always paired with the presence of its
# replacement -- an absence assertion alone passes against a deleted file.
#
# `\b` boundaries throughout, because three of the four KEEPERS below contain
# the word: `github_environment`, `target_environment` and `TARGET_ENVIRONMENT`
# must not be matched by any pattern here, and a substring search would match
# every one of them.
RETIRED_IDENTIFIERS = {
    "environments_root": re.compile(r"\benvironments_root\b"),
    "matrix.environment": re.compile(r"\bmatrix\.environment\b"),
    "inputs.environment": re.compile(r"\binputs\.environment\b"),
    "ENVIRONMENTS": re.compile(r"(?<![A-Za-z0-9_])ENVIRONMENTS(?![A-Za-z0-9_])"),
    "ENVIRONMENT_NAME": re.compile(r"(?<![A-Za-z0-9_])ENVIRONMENT_NAME(?![A-Za-z0-9_])"),
    "REQUESTED_ENVIRONMENT": re.compile(
        r"(?<![A-Za-z0-9_])REQUESTED_ENVIRONMENT(?![A-Za-z0-9_])"
    ),
    "outputs.environments": re.compile(r"\boutputs\.environments\b"),
}

# Their replacements, asserted PRESENT in the same sweep so that a workflow
# emptied of the old word has not thereby satisfied the check.
REPLACEMENT_IDENTIFIERS = {
    "stacks_root": re.compile(r"\bstacks_root\b"),
    "matrix.stack": re.compile(r"\bmatrix\.stack\b"),
    "STACKS": re.compile(r"(?<![A-Za-z0-9_])STACKS(?![A-Za-z0-9_])"),
    "STACK_NAME": re.compile(r"(?<![A-Za-z0-9_])STACK_NAME(?![A-Za-z0-9_])"),
    "outputs.stacks": re.compile(r"\boutputs\.stacks\b"),
}

# Which replacement each workflow is expected to carry. Not every workflow
# carries every one -- `drift.yml` narrows by nothing and so has no
# `STACKS` input, and `host-converge.yml`'s fourth body enumerates the
# inventory rather than the Terraform root and so declares no `stacks_root`
# for iteration but names one to read each stack's declaration. This table is
# DERIVED from that change's tasks.md 3.1-3.4 and is the one place the
# per-workflow expectation is written down.
EXPECTED_REPLACEMENTS = {
    PR_VALIDATION.name: ("stacks_root", "matrix.stack", "STACKS", "STACK_NAME", "outputs.stacks"),
    APPLY.name: ("stacks_root", "matrix.stack", "STACKS", "STACK_NAME", "outputs.stacks"),
    DRIFT.name: ("stacks_root", "matrix.stack", "STACK_NAME", "outputs.stacks"),
    HOST_CONVERGE.name: ("stacks_root", "matrix.stack", "outputs.stacks"),
}

ACTIONS_EXPRESSION = re.compile(r"\$\{\{")
NEEDS_OUTPUT = re.compile(r"\bneeds\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)")
INTERPOLATION = re.compile(r"\$\{\{[^}]*\}\}|\$\{[^}]*\}")
MODULE_SOURCE = re.compile(r'^\s*source\s*=\s*"([^"]*)"', re.MULTILINE)
MODULE_VERSION = re.compile(r'^\s*version\s*=\s*"', re.MULTILINE)
WORKSPACE_NAME = re.compile(r"workspaces\s*\{[^}]*name\s*=\s*\"([^\"]+)\"", re.DOTALL)
LABEL_ASSIGNMENT = re.compile(r'^\s*(environment|managed_by)\s*=\s*"([^"]*)"', re.MULTILINE)
TERRAFORM_APPLY = re.compile(r"terraform\s+apply\b")

# A prefix used to build workspace names in the SYNTHETIC trees below, and
# nothing more. It asserts nothing about this repository and no requirement
# obliges it.
#
# IT USED TO BE A DERIVATION AND IS NOT ONE NOW. This constant was introduced
# quoting Remote State Backend's "named `infrastructure-<stack>`", a clause that
# requirement no longer carries: it now forbids COMPUTING a workspace name from
# a stack's directory name and permits only that the two agree. Kept because the
# fixture builder needs some name and any name will do; the comment is corrected
# because a constant quoting a retired rule is how the next reader comes to
# believe the rule. Its sibling `WORKSPACE_FORM`, which had no use at all, was
# deleted by the change rename-the-external-services for the same reason.
WORKSPACE_PREFIX = "infrastructure-"

# The two required fields of a stack's pipeline declaration, by the names the
# discovery bodies already read them under. Unlike the module beside this one,
# which resolved the fields by shape because their names were not yet decided,
# these names are settled: the committed discovery bodies index them literally.
GITHUB_ENVIRONMENT_FIELD = "github_environment"
READ_ONLY_SECRET_FIELD = "read_only_secret"

# The name every GitHub Environment defines for its Read & Write token, and
# therefore the one name no stack's declaration may give as its READ-ONLY
# secret. SPECIFIED by iac-cicd-pipeline / Each Stack Declares Its Own
# Pipeline Configuration.
WRITE_TOKEN_SECRET = "HCLOUD_TOKEN"


# --------------------------------------------------------------------------
# Reading the stack root
# --------------------------------------------------------------------------


def stack_directories(root: Path | None = None) -> list[Path]:
    """Every stack directory under the Terraform stack root.

    Takes `root` so the behaviour is exercisable against a fixture tree; the
    discriminating tests at the end of this module are what stop these reads
    passing vacuously at two stacks.
    """
    base = (ROOT if root is None else root) / "terraform" / "stacks"
    if not base.is_dir():
        return []
    return sorted(
        entry for entry in base.iterdir() if entry.is_dir() and not entry.name.startswith(".")
    )


def stack_declarations(root: Path | None = None) -> dict:
    """Stack name -> the parsed `pipeline.yml` beside its Terraform files.

    A directory whose declaration is absent or does not parse as a mapping maps
    to `None`, so the caller can report WHICH stack rather than raising.
    """
    found: dict = {}
    for directory in stack_directories(root):
        path = directory / "pipeline.yml"
        if not path.is_file():
            found[directory.name] = None
            continue
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError):
            found[directory.name] = None
            continue
        found[directory.name] = document if isinstance(document, dict) else None
    return found


def stack_terraform_text(directory: Path) -> str:
    """Every `.tf` file in a stack directory, concatenated."""
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(directory.glob("*.tf"))
    )


def old_root_occurrences(root: Path | None = None) -> list[str]:
    """Every committed file still naming the old Terraform root, as
    `<path>:<line>`.

    WHAT IS MATCHED. `OLD_ROOT_REFERENCE`, which is the union of two shapes:
    the prefixed path `terraform/<directory>`, with or without a trailing
    slash and wherever it appears; and a BARE `<directory>/` reference,
    whatever prefix it carries or none -- so a comment reading
    "(not environments/prod)" and a note reading "`environments/prod` couples
    the volume to the server" are both offences, which they were not until
    code review found two such files the sweep had passed over.

    WHAT IS DELIBERATELY NOT MATCHED, and this is the boundary a reader should
    not have to infer from the regular expression:

    * The bare WORD, with no slash after it. `environment` and `environments`
      stay throughout this repository wherever they name a GitHub Environment,
      the Hetzner `environment` label, the environment axis, the OS process
      environment or a pre-commit hook's environment -- none of which this
      change renames. A pattern keyed on the word rather than on the path-like
      shape would light up `docs/` and `README.md` in prose many times over and
      would be unsatisfiable without the overreach the change forbids.
    * The word immediately preceded by a letter, digit, underscore or hyphen.
      That is a longer identifier ending in it, not a reference to this
      directory.
    * Anything under `openspec/`, which is filtered below. The delta specs are
      what this suite is derived FROM, so reading them as offences would be
      circular, and an archived record is history rather than a stale path;
      `openspec validate` is what checks that tree.

    THE FILE SET IS TRACKED FILES, NOT A FILESYSTEM WALK, and the difference
    is a defect this sweep shipped with. `walked_files()` prunes `.git`,
    `.terraform`, `__pycache__` and `node_modules` and nothing else, so it
    reads `.molecule-home/` -- which does not exist in continuous integration
    and appears the moment a developer follows this repository's own Molecule
    instructions, carrying vendored third-party collections. A single fixture
    under `.molecule-home/collections/ansible_collections/community/docker/`
    naming `environments/prod` made this function report two offences in code
    nobody here wrote. The widening to a bare `<directory>/` reference is what
    made it likely: that shape is common in third-party Ansible content where
    the prefixed path never was. `AGENTS.md` scopes this suite to a static read
    of a COMMITTED file, and vendored untracked content is not committed. See
    `docs/change-queue.md` entry 68, which names this class and recommends this
    helper.

    A `root` argument means a scratch tree instead, which is NOT a repository
    and has no tracked files, so those are walked. That path exists for the
    discriminators below and is not a second way of reading the repository.

    Raises rather than reporting a clean tree when it reads no file at all: a
    sweep that read nothing would otherwise report success having verified
    nothing. `tracked_files()` raises on its own account when the listing
    cannot be taken, which is the same refusal one layer down.
    """
    here = Path(__file__).resolve()
    contents: dict[str, str] = {}
    if root is None:
        for name, raw in tracked_files().items():
            if name.startswith("openspec/"):
                continue
            if (ROOT / name).resolve() == here:
                continue
            contents[name] = raw.decode("utf-8", errors="replace")
        if not contents:
            raise AssertionError(
                "the tracked-file listing reached no file at all outside `openspec/`, "
                "so this sweep would pass having read nothing"
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
        if not OLD_ROOT_REFERENCE.search(text):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if OLD_ROOT_REFERENCE.search(line):
                offences.append(f"{name}:{number}")
    return sorted(offences)


# --------------------------------------------------------------------------
# Reading the committed contents of the stack directories
#
# Nothing in this suite read `terraform/stacks/**` in either direction until
# these were added, and code review found four mis-renames there that the four
# workflow-facing classes above could not have seen -- three of them
# re-introductions of the exact defects the same commit was fixing elsewhere.
# Two properties of this suite put that blind spot where it was: the keeper
# guard reads the four workflow files and no others, and it reads them through
# `uncommented()`, which strips comments BY DESIGN.
#
# All four defects were in comments. So `uncommented()` is the wrong helper
# here and is deliberately not used; these read the file as text, and a YAML or
# HCL parser would be wrong for the same reason.
# --------------------------------------------------------------------------

# A leading comment marker in any of the three languages under this root --
# `#` for HCL and YAML, `//` and `--` for the forms HCL also accepts.
COMMENT_MARKER = re.compile(r"^\s*(?:#+|//+|--)\s?")


def stack_root_files(root: Path | None = None) -> list[Path]:
    """Every committed file under the stack root.

    `walked_files()` prunes `.terraform` anywhere, so a provider cache -- whose
    vendored CHANGELOG is arbitrary third-party prose and would be read as this
    repository's own text -- is not reached. Everything else under the root is,
    including files no parser of this suite's would open.
    """
    base = (ROOT if root is None else root) / "terraform" / "stacks"
    if not base.is_dir():
        return []
    return walked_files(base)


def committed_prose(text: str) -> str:
    """A file as one line of prose: each line stripped of leading whitespace
    and of a leading comment marker, joined with single spaces.

    Two reasons it is flattened rather than read line by line. A sentence in a
    comment block wraps, and one of the four defects this exists for -- "so an
    stack" -- straddled the break with a `#` between the article and its noun,
    so no line-wise read could see it. And a claim about a keeper is a property
    of the sentence, not of the line it happens to start on.
    """
    return " ".join(COMMENT_MARKER.sub("", line).strip() for line in text.splitlines())


# The keeper senses, and the shape each one's OVER-sweep takes. DERIVED
# throughout: no scenario states any of this. The senses come from design.md
# decision 2's four keepers -- a GitHub Environment, the `environment` label
# and variable, the environment axis and its inventory paths, and
# `target_environment` -- plus the two further senses code review's first round
# established, the OS process environment and a pre-commit hook's environment.
#
# Each pattern keys on the SENSE, through the context that identifies it, and
# never on the word `stack`, which is correct throughout these files now. A
# needle firing on the word generally would be worse than no needle.
#
# TWO LEGENDS, and the second is the one a reader is most likely to want.
#
# (*) marks a spelling that fired on a REAL committed defect, in round one or
# round two. Everything unmarked is another spelling of the same sense.
#
# LIVE / FORWARD COVER marks whether the sense can fire on these sixteen files
# AT ALL. Three of the six cannot: no file under this root mentions
# `target_environment`, `--vault-id`, an inventory source or pre-commit, which
# was checked rather than assumed. Keeping them is right -- a stack directory
# may grow a comment about any of the three, and a needle added after the fact
# is a needle added too late -- but the table's six-entry breadth would
# otherwise overstate what is actually guarded here, so it is said outright.
# No test asserts the inertness: a file legitimately gaining one of those
# mentions would then fail a check for having done nothing wrong, and the
# legend going stale is the cheaper failure.
OVERSWEPT_KEEPERS = {
    # (*) LIVE. A GitHub Environment, in the two forms it takes.
    #
    # THE KEY: `stack:` presented as a GitHub Actions job key. There is no such
    # key; the key is `environment:`, and each file that carried this named one
    # key two ways inside one comment block.
    #
    # THE PROSE: capitalised `Environment` as a proper noun, which is how both
    # `pipeline.yml` files refer to a GitHub Environment throughout -- prod
    # carries eight such occurrences and is the densest prose in the repository
    # in this sense. Renaming capitalised prose is the exact defect round one
    # found in the workflow sweep, so a needle for the key alone would be blind
    # to the form most likely to recur here. Three shapes:
    #
    #   * `GitHub Stack` outright;
    #   * a capitalised `Stack` MID-SENTENCE -- "the Stack's protection rules",
    #     "a Stack-scoped secret", "that Stack requires no reviewer". The
    #     lookbehind is what keeps a sentence or a bullet legitimately opening
    #     with the word out of it, and capitalised `Stack` never names the unit
    #     in this repository, which is always lowercase.
    #
    #     THE TRAILING LOOKAHEAD WAS ADDED by the change
    #     rename-the-stacks-and-their-resources, which moved that requirement's
    #     title off the environment axis and onto the stack, giving it the name
    #     *Each Stack Declares Its Own Pipeline Configuration* -- so both
    #     `pipeline.yml` files now cite a
    #     requirement whose Title Case name carries the word, and the limb fired
    #     on the correct citation. A capitalised word FOLLOWING is what
    #     distinguishes a Title Case name from the common-noun misuse this limb
    #     is for: every shape round one of that change's review actually found
    #     -- "Stack's", "Stack-scoped", "Stack requires" -- is followed by
    #     punctuation or a lowercase word and is still caught;
    # The `Each Stack` limb is GONE, and its removal is a supersession rather
    # than a relaxation. It was forward cover written while that requirement
    # still carried the environment axis in its title, on the
    # reasoning that "design.md decision 3 renames no requirement title". The
    # change rename-the-stacks-and-their-resources renames exactly that title,
    # so both `pipeline.yml` files now cite *Each Stack Declares Its Own
    # Pipeline Configuration* correctly -- and the limb fired on the correct
    # citation. A needle that reddens on the right answer is worse than no
    # needle. The other four limbs are untouched and still carry the two shapes
    # round one of that change's review actually found.
    "the GitHub Environment": re.compile(
        r"`stack:"
        r"|\bgithub_stack\b"
        r"|\bGitHub Stacks?\b"
        r"|(?<=[a-z,;] )Stacks?\b(?! [A-Z])"
    ),
    # (*) LIVE. The `environment` Terraform variable, and the label carrying
    # its value. `modules/server` builds `name = "${var.environment}-${var.name}"`,
    # so a `"<stack>-"` prefix is that variable's value under a wrong name --
    # and after entry 62 the two diverge, which is the coincidence design.md
    # decision 2a says not to bake in.
    #
    # The label is matched with OPTIONAL BACKTICKS OR QUOTES around the word,
    # because backticked is literally how round one's runbook defect was
    # written -- "the `stack` label" -- and the bare form would have missed the
    # instance this needle is named for.
    "the Terraform variable and its value": re.compile(
        r"\bvar\.stack\b"
        r'|"<stack>-'
        r'|\bstack\s*=\s*"'
        r"|[`'\"]?stack[`'\"]? labels?\b"
        r"|\b\w*labels?\.stack\b"
    ),
    # (*) LIVE. The OS process environment, which is what `HCLOUD_TOKEN` is
    # read from and the mechanism the bullets under that sentence qualify.
    #
    # Keyed on the PREPOSITION AND THE NOUN rather than on a list of verbs. A
    # closed verb list is a needle that catches the sentence it was written
    # from and not the next one: "taken from the stack" and "written into the
    # job's stack file" are the same defect and neither uses a listed verb.
    # The lookahead keeps a legitimate reference to a stack DIRECTORY out of
    # it, which is the one thing "from the stack" can innocently mean here.
    "the OS process environment": re.compile(
        r"\bstack (?:variable|variables|file|files)\b"
        r"|\b(?:job's|runner's|process|shell|step's) stack\b"
        r"|\b(?:from|into|in|out of) the (?:job's |runner's |process |shell )?stack\b"
        r"(?!['’]|\s+(?:director|root|name|declaration|configuration|it))"
    ),
    # FORWARD COVER. The converge play's group handle, governed by a
    # requirement this change does not modify at all. No file under this root
    # mentions it today.
    "the converge play's group handle": re.compile(
        r"(?<![A-Za-z0-9_])TARGET_STACK(?![A-Za-z0-9_])"
        r"|\btarget_stack\b"
        r"|--vault-id[^\n]{0,40}\bstack\b"
    ),
    # FORWARD COVER. The environment axis as the inventory names it; entry 62
    # renames those paths, not this change. No file under this root names an
    # inventory source today.
    "the inventory's own axis": re.compile(
        r"\bstack\.hcloud\.yml\b|\bstack_vars\b|\binventory/\$?\{?stacks?\b"
    ),
    # (*) FORWARD COVER. A pre-commit hook's environment. Round one's defect
    # was a step name reading "Cache pre-commit stacks", so the needle covers
    # the adjectival form as well as the possessive one -- the bare `hook
    # stacks` would have missed the instance it is named for. No file under
    # this root mentions pre-commit today.
    "a pre-commit hook's environment": re.compile(
        r"\bhook stacks?\b|\bpre-commit stacks?\b|\bstacks? for the hooks?\b"
    ),
}

# (*) An article stranded by a word-level substitution. Its own check rather
# than a keeper sense: nothing is renamed wrongly here, the sentence is simply
# ungrammatical, and the same defect had already been fixed once in
# `host-converge.yml` before it recurred under this root. Both directions are
# read, because a sweep can strand an article either way.
STRANDED_ARTICLE = re.compile(
    r"\ban stacks?\b|\ba environments?\b", re.IGNORECASE
)


# --------------------------------------------------------------------------
# Reading the workflows
# --------------------------------------------------------------------------


def run_bodies(path: Path):
    """(label, body) for every `run:` step of a workflow."""
    workflow = load_yaml(path)
    for job_name, index, step in steps(workflow):
        body = step.get("run")
        if body:
            yield step_label(job_name, index, step), str(body)


def discovery_bodies(path: Path) -> list[str]:
    """Every `run:` body of a workflow that IS the stack discovery.

    Located by shape rather than by name, which is the idiom the modules beside
    this one use and the one that change's design.md decision 6 records as
    load-bearing: a name-based locator was tried in this suite and was wrong.
    The shape is the stack root, no `terraform/modules` (which is what tells
    discovery apart from the changed-path resolution), a write to
    `$GITHUB_OUTPUT` (emitting the matrix is what discovery is FOR), and no
    Actions expression (that change's tasks.md 3.6 obliges it, and it is what
    lets this suite execute such a body at all).
    """
    return [
        body
        for _, body in run_bodies(path)
        if STACK_ROOT_SEGMENT in body
        and "terraform/modules" not in body
        and "GITHUB_OUTPUT" in body
        and not ACTIONS_EXPRESSION.search(body)
    ]


def resolution_bodies(path: Path) -> list[str]:
    """Every `run:` body of a workflow that resolves which stacks a change
    affects: names the stack root AND `terraform/modules`, per the path rule
    both `Pull Request Plan Visibility` and `Gated Production Apply Applies the
    Reviewed Plan` state."""
    return [
        body
        for _, body in run_bodies(path)
        if STACK_ROOT_SEGMENT in body
        and "terraform/modules" in body
        and "GITHUB_OUTPUT" in body
        and not ACTIONS_EXPRESSION.search(body)
    ]


def declared_outputs(path: Path) -> dict:
    """Job key -> the set of output names that job declares."""
    return {
        name: set((job.get("outputs") or {}).keys())
        for name, job in jobs(load_yaml(path)).items()
    }


def needs_output_reads(path: Path) -> list:
    """(job, output) for every `needs.<job>.outputs.<name>` the workflow reads."""
    return sorted(set(NEEDS_OUTPUT.findall(uncommented(read_text(path)))))


def normalised_interpolation(text: str) -> str:
    """Collapse every `${{ ... }}` and `${...}` to one placeholder.

    Two surfaces name the same thing through different mechanisms -- a shell
    variable inside a `run:` body and an Actions expression inside a `with:` --
    and they have to agree on the LITERAL part or the comment they build is
    found by nothing. Normalising the interpolation is what lets the two be
    compared at all.
    """
    return compact(INTERPOLATION.sub("<value>", str(text)))


# The four characters a backslash is special before INSIDE double quotes, and
# the only ones. Anywhere else in a double-quoted string a backslash stands for
# itself, so a substitution wider than this would silently rewrite a literal.
DOUBLE_QUOTED_ESCAPE = re.compile(r'\\([$`"\\])')


def shell_double_quoted_value(assignment: str) -> str:
    """The right-hand side of `name="..."`, as the shell will actually emit it.

    The plan-comment heading is assigned inside double quotes, so its backticks
    are written `\\`` -- while the `body-includes` locator that has to find that
    same comment is YAML and carries bare backticks. Harvested without
    unescaping, the two differ by two backslashes and by nothing else, and the
    check reports a disagreement between two surfaces that agree. That is a
    defect in the READ, not in what is asserted: what the check exists to catch
    is a heading and a locator naming different PATHS, and this repair leaves
    that assertion exactly as strong -- see
    `TestTheHeadingReadDiscriminates` at the foot of this module, which
    establishes it on material of its own.

    One matched pair of surrounding quotes is removed, rather than every
    leading and trailing quote: a heading that legitimately ends in a quote
    character is not a reason to eat it.
    """
    value = assignment.partition("=")[2].strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]
    return DOUBLE_QUOTED_ESCAPE.sub(r"\1", value)


# --------------------------------------------------------------------------
# iac-repo-foundations / Stack and Module Folder Structure,
# Version Control Excludes State and Secrets
# --------------------------------------------------------------------------


class TestTheTerraformRootIsNamedForTheStack(unittest.TestCase):
    """MODIFIED requirements: Stack and Module Folder Structure, and
    Version Control Excludes State and Secrets (iac-repo-foundations)."""

    def test_the_stack_root_holds_the_stack_directories(self) -> None:
        """SPECIFIED -- "The repository SHALL organize Terraform configuration
        as stack directories under `terraform/stacks/`", and the scenario
        "Prod environment consumes a shared module", which names
        `terraform/stacks/prod/`.

        Asserts a non-empty root rather than a fixed membership: the
        requirement's own scenario "Adding a future environment does not
        require restructuring" obliges that adding a stack be adding a
        directory, so an assertion enumerating today's two would be the defect
        that scenario forbids. What IS fixed is that the production stack is
        among them -- the delta names its directory in four capabilities.

        RE-POINTED by the change rename-the-stacks-and-their-resources, which
        renamed that directory to `main-production`. The proposition is
        unchanged and the literal moved with the tree; the assertion is no
        weaker than it was.
        """
        directories = stack_directories()
        self.assertTrue(
            directories,
            f"{STACK_ROOT_SEGMENT}/ holds no stack directory, so the pipeline "
            "discovers nothing and every assertion below reads an empty set. "
            "Before the implementation exists this is the expected failure: the "
            "directory has not been moved yet",
        )
        self.assertIn(
            "main-production",
            [directory.name for directory in directories],
            "the delta specs name `terraform/stacks/main-production/` in "
            "iac-repo-foundations, iac-safety-hardening, iac-state-management and "
            f"iac-cicd-pipeline; the stack root holds {[d.name for d in directories]}",
        )

    def test_no_terraform_directory_is_still_divided_by_the_environment_axis(self) -> None:
        """DERIVED -- that change's proposal.md ("`terraform/environments/`
        becomes `terraform/stacks/`") and its tasks.md 2.1 and 2.4, which
        oblige the `git mv` and the removal of anything left behind. No
        scenario states it: a scenario describes what the pipeline does, and
        the absence of the old directory is a property of the move.

        Stated separately from the sweep at the end of this module because the
        two fail for different reasons and a reader needs to tell them apart: a
        directory that still EXISTS is an incomplete move, while a file that
        still NAMES the old path is an incomplete sweep. `git mv` leaving an
        empty directory or a gitignored `.terraform/` behind produces the first
        without the second.
        """
        old = ROOT / "terraform" / "environments"
        self.assertFalse(
            old.exists(),
            f"{old.relative_to(ROOT).as_posix()} still exists. `git mv` moves tracked "
            "files only, so an untracked `.terraform/` or an empty directory can "
            "survive the move and leave the tree divided by both axes at once",
        )

    def test_every_stack_consumes_the_shared_modules_by_relative_path(self) -> None:
        """SPECIFIED -- scenario "Prod environment consumes a shared module",
        and the requirement's "Stacks consume modules by relative path"."""
        directories = stack_directories()
        self.assertTrue(directories, "no stack directory to read; see the test above")
        for directory in directories:
            with self.subTest(stack=directory.name):
                text = stack_terraform_text(directory)
                self.assertTrue(
                    text.strip(),
                    f"{directory.name} carries no Terraform configuration at all",
                )
                sources = [
                    source
                    for source in MODULE_SOURCE.findall(text)
                    if "/" in source or source.startswith(".")
                ]
                relative = [
                    source
                    for source in sources
                    if source.startswith("./") or source.startswith("../")
                ]
                self.assertTrue(
                    relative,
                    f"{directory.name} calls no module by a relative path, so it either "
                    "duplicates resource definitions inline or consumes a module from "
                    f"somewhere other than terraform/modules/. Sources found: {sources}",
                )
                for source in relative:
                    self.assertIn(
                        "modules/",
                        source,
                        f"{directory.name} consumes {source!r}, which is a relative "
                        "path but not one reaching terraform/modules/",
                    )

    def test_no_stack_pins_a_module_version_of_its_own(self) -> None:
        """SPECIFIED -- "there is no per-stack module version pinning, and none
        SHALL be introduced to obtain promotion ordering", and scenario
        "Adding a future environment does not require restructuring", which
        obliges a new stack be added "without pinning a module version of its
        own".

        Read over the `module` blocks only. `required_providers` carries a
        `version` legitimately and is what `versions.tf` is for, so the search
        is confined to the file holding the module calls that names a relative
        source.
        """
        directories = stack_directories()
        self.assertTrue(directories, "no stack directory to read; see the first test")
        for directory in directories:
            for path in sorted(directory.glob("*.tf")):
                text = path.read_text(encoding="utf-8")
                if not any(
                    source.startswith("./") or source.startswith("../")
                    for source in MODULE_SOURCE.findall(text)
                ):
                    continue
                with self.subTest(stack=directory.name, file=path.name):
                    self.assertIsNone(
                        MODULE_VERSION.search(text),
                        f"{directory.name}/{path.name} calls a module by relative path "
                        "and also declares a `version`, which is a per-stack module "
                        "pin. Every stack runs the same module code as of the merged "
                        "commit",
                    )

    def test_every_stack_carries_its_committed_non_secret_configuration(self) -> None:
        """SPECIFIED -- Version Control Excludes State and Secrets: the tracked
        row of its table is now `terraform/stacks/<name>/terraform.tfvars`, and
        its scenario "CI has the environment configuration it needs" runs
        `terraform plan` against `terraform/stacks/prod/` from a clean
        checkout."""
        directories = stack_directories()
        self.assertTrue(directories, "no stack directory to read; see the first test")
        missing = [
            directory.name
            for directory in directories
            if not (directory / "terraform.tfvars").is_file()
        ]
        self.assertEqual(
            [],
            missing,
            f"these stacks under {STACK_ROOT_SEGMENT}/ carry no committed "
            f"`terraform.tfvars`: {missing}. CI plans from a clean checkout and "
            "requires the non-secret stack configuration to be present",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Each Stack Declares Its Own Pipeline Configuration
# --------------------------------------------------------------------------


class TestEveryStackDeclaresItsPipelineConfiguration(unittest.TestCase):
    """MODIFIED requirement: Each Stack Declares Its Own Pipeline
    Configuration (iac-cicd-pipeline).

    The requirement's subject moved with the path -- "Every directory under
    `terraform/stacks/` SHALL carry a committed, machine-readable file
    declaring the pipeline configuration for that stack" -- so these are reads
    of the NEW root. The module beside this one asserts the same propositions
    over the old root, and that is what makes those assertions obsolete rather
    than these redundant.
    """

    def test_every_stack_directory_carries_a_declaration_with_both_required_fields(self) -> None:
        """SPECIFIED -- "Two fields are **required**: the name of the GitHub
        Environment its apply job attaches to, and the name of the repository
        secret holding its read-only Hetzner token", and scenario "An
        environment missing its declaration fails the pipeline"."""
        declarations = stack_declarations()
        self.assertTrue(
            declarations,
            f"no stack directory under {STACK_ROOT_SEGMENT}/, so this census reads "
            "nothing; see TestTheTerraformRootIsNamedForTheStack",
        )
        offences = []
        for name, document in sorted(declarations.items()):
            if document is None:
                offences.append(f"{name}: no pipeline declaration, or one that is not a mapping")
                continue
            for field in (GITHUB_ENVIRONMENT_FIELD, READ_ONLY_SECRET_FIELD):
                value = document.get(field)
                if not isinstance(value, str) or not value.strip():
                    offences.append(f"{name}: required field {field!r} is {value!r}")
        self.assertEqual(
            [], offences, f"stack declarations that discovery would refuse: {offences}"
        )

    def test_no_two_stacks_declare_the_same_secret_or_the_same_github_environment(self) -> None:
        """SPECIFIED -- scenarios "Two environments declaring the same
        read-only secret are refused" and "Two environments declaring the same
        GitHub Environment are refused"."""
        declarations = {
            name: document
            for name, document in stack_declarations().items()
            if isinstance(document, dict)
        }
        self.assertTrue(declarations, "no parseable stack declaration to compare")
        for field in (READ_ONLY_SECRET_FIELD, GITHUB_ENVIRONMENT_FIELD):
            by_value: dict = {}
            for name, document in sorted(declarations.items()):
                value = document.get(field)
                if isinstance(value, str) and value.strip():
                    by_value.setdefault(value, []).append(name)
            shared = {value: names for value, names in by_value.items() if len(names) > 1}
            self.assertEqual(
                {},
                shared,
                f"these stacks declare the same {field!r}: {shared}. Two stacks "
                "sharing one would run under a single credential, or under a single "
                "set of protection rules and a single write token",
            )

    def test_no_stack_declares_the_write_tokens_own_name_as_its_read_only_secret(self) -> None:
        """SPECIFIED -- "No stack's declared read-only secret name SHALL be a
        name its own GitHub Environment also defines, and `HCLOUD_TOKEN` is
        such a name for every stack", and scenario "A declaration naming the
        write token's own name is refused"."""
        declarations = stack_declarations()
        self.assertTrue(
            declarations,
            f"no stack directory under {STACK_ROOT_SEGMENT}/, so this prohibition "
            "would pass having read no declaration at all",
        )
        offenders = sorted(
            name
            for name, document in declarations.items()
            if isinstance(document, dict)
            and document.get(READ_ONLY_SECRET_FIELD) == WRITE_TOKEN_SECRET
        )
        self.assertEqual(
            [],
            offenders,
            f"these stacks declare {WRITE_TOKEN_SECRET!r} as their read-only secret: "
            f"{offenders}. Every GitHub Environment defines that name as its Read & "
            "Write token, and an Environment secret shadows a repository secret of "
            "the same name, so a gated job would resolve a write credential from a "
            "field that says read-only",
        )


# --------------------------------------------------------------------------
# iac-state-management / Remote State Backend
# --------------------------------------------------------------------------


class TestEachStackNamesAWorkspaceOfItsOwn(unittest.TestCase):
    """MODIFIED requirement: Remote State Backend (iac-state-management).

    RENAMED from `TestEachStackNamesAWorkspaceDerivedFromItsOwnName` by the
    change rename-the-external-services: there is no derivation left to name.
    The requirement retired `infrastructure-<stack>` and now forbids computing a
    workspace name from a directory name, permitting only that the two agree --
    which, since that change, they do. What is asserted here is what survived:
    every stack names a workspace in its own `versions.tf`, and no two name the
    same one. Never that any HCP workspace was renamed, which this suite makes
    no network call to observe and could not establish if it tried.
    """

    def _workspaces(self) -> dict:
        found = {}
        for directory in stack_directories():
            match = WORKSPACE_NAME.search(stack_terraform_text(directory))
            found[directory.name] = match.group(1) if match else None
        return found

    def test_every_stack_names_a_workspace_in_its_own_versions_file(self) -> None:
        """SPECIFIED -- "Each stack SHALL have a workspace of its own", and
        scenario "State is not stored locally", which runs `terraform init` "in
        a stack directory under `terraform/stacks/`".

        SUPERSEDED IN PART BY THE CHANGE rename-the-stacks-and-their-resources,
        which retired the `infrastructure-<stack>` DERIVATION this test used to
        assert. The requirement now says a workspace's name SHALL NOT be
        COMPUTED from its stack's directory name -- not that the two may not
        agree, but that nothing may derive one from the other. The two are
        renamed by different mechanisms in an order that cannot be reversed (the
        HCP interface first, the `cloud` block second), so a derivation is false
        for the interval between them. This repository was inside such an
        interval and no longer is: rename-the-external-services performed the
        HCP rename and moved the `cloud` blocks after it, so the two names agree
        again -- by convention, which the requirement permits, and not by any
        derivation, which it forbids.

        What survives is what the requirement is actually for, and it is
        asserted here and in the sibling below: every stack names a workspace,
        in its own `versions.tf`, and no two name the same one.
        """
        workspaces = self._workspaces()
        self.assertTrue(workspaces, "no stack directory to read; see the first test")
        unnamed = sorted(name for name, workspace in workspaces.items() if not workspace)
        self.assertEqual(
            [],
            unnamed,
            f"these stacks name no workspace in their own `versions.tf`: {unnamed}. A "
            "stack whose `cloud` block names no workspace has no state of its own, "
            "and the failure surfaces at `terraform init` rather than here",
        )

    def test_no_two_stacks_name_the_same_workspace(self) -> None:
        """SPECIFIED -- scenario "Two environments do not share a workspace".

        THERE IS NO DERIVATION ABOVE ANY MORE, and this docstring used to say
        this followed from one. *Remote State Backend* retired
        `infrastructure-<stack>` and now forbids computing a workspace name from
        a directory name, so uniqueness is not implied by anything and is the
        whole of what this asserts: two stacks naming one workspace would have
        each apply read the other's resources as its own and plan them for
        destruction. Corrected alongside its sibling above rather than left,
        because a docstring quoting a retired rule is how the next reader comes
        to believe the rule.
        """
        workspaces = self._workspaces()
        named = [workspace for workspace in workspaces.values() if workspace]
        self.assertTrue(
            named,
            "no stack under the stack root names an HCP Terraform workspace, so this "
            "uniqueness check would pass having compared nothing",
        )
        self.assertEqual(
            len(set(named)),
            len(named),
            f"two stacks name the same HCP Terraform workspace: {workspaces}. A "
            "workspace holds one state, so each apply would read the other's "
            "resources as its own and plan them for destruction",
        )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Pull Request Validation Checks, Pull Request Plan
# Visibility, Gated Production Apply Applies the Reviewed Plan, Scheduled Drift
# Detection -- the discovery and resolution bodies
# --------------------------------------------------------------------------


class TestDiscoveryIteratesTheStackRoot(unittest.TestCase):
    """MODIFIED requirements: Each Stack Declares Its Own Pipeline
    Configuration and Scheduled Drift Detection (iac-cicd-pipeline)."""

    def test_each_terraform_workflow_carries_one_discovery_body_over_the_stack_root(self) -> None:
        """SPECIFIED -- scenario "Discovery finding no environment fails rather
        than reporting success", whose WHEN is now "discovery over
        `terraform/stacks/` yields an empty set", and Scheduled Drift
        Detection's "`terraform plan` against every stack"."""
        for path in TERRAFORM_WORKFLOWS:
            with self.subTest(workflow=path.name):
                bodies = discovery_bodies(path)
                self.assertEqual(
                    1,
                    len(bodies),
                    f"expected exactly one `run:` step in {path.name} that enumerates "
                    f"`{STACK_ROOT_SEGMENT}`, writes to `$GITHUB_OUTPUT` and carries "
                    f"no `${{{{ }}}}` -- the stack discovery -- but found {len(bodies)}",
                )

    def test_the_three_discovery_bodies_stay_identical(self) -> None:
        """DERIVED -- that change's tasks.md 3.1: "The three bodies stay
        byte-identical -- `.github/tests` asserts it, and that assertion is
        what makes running one copy evidence about all three."

        The module beside this one holds the same assertion keyed on the old
        root. Both are needed for exactly one commit: this one is what catches
        a copy the rename missed, which is the failure that change's design.md
        decision 1 names as the cost of sweeping four bodies rather than one.
        """
        bodies = {path.name: discovery_bodies(path) for path in TERRAFORM_WORKFLOWS}
        missing = sorted(name for name, found in bodies.items() if len(found) != 1)
        self.assertEqual(
            [],
            missing,
            f"these workflows carry no single stack-discovery body: {missing}; see "
            "the test above, which reports which and how many",
        )
        distinct = {found[0] for found in bodies.values()}
        self.assertEqual(
            1,
            len(distinct),
            "the three stack-discovery bodies have drifted apart. Only one of them is "
            "ever executed by this suite, so a copy the rename missed -- or renamed "
            "differently -- stays green here and discovers differently in the workflow "
            f"that applies to production. Workflows compared: {sorted(bodies)}",
        )

    def test_the_two_changed_path_resolutions_name_the_stack_root_and_stay_identical(self) -> None:
        """SPECIFIED for the path rule -- Pull Request Plan Visibility: "a
        change under `terraform/modules/` affects every stack, and a change
        under `terraform/stacks/<name>/` affects only that stack", which Gated
        Production Apply Applies the Reviewed Plan restates for the merge.
        DERIVED for the identity -- that change's tasks.md 3.1a: a pull request
        and the merge of that pull request must resolve the same set.

        `drift.yml` deliberately carries no resolution: drift is divergence
        from what was committed, which no diff predicts, so it plans every
        stack on every run.
        """
        bodies = {
            path.name: resolution_bodies(path)
            for path in (PR_VALIDATION, APPLY, DRIFT)
        }
        self.assertEqual(
            [],
            bodies[DRIFT.name],
            "drift.yml carries a changed-path resolution, which would narrow the "
            "nightly sweep by a diff. Drift is what a diff cannot predict",
        )
        for name in (PR_VALIDATION.name, APPLY.name):
            self.assertEqual(
                1,
                len(bodies[name]),
                f"expected exactly one changed-path resolution in {name} naming both "
                f"`{STACK_ROOT_SEGMENT}` and `terraform/modules`, found "
                f"{len(bodies[name])}",
            )
        stripped = {
            "\n".join(
                line
                for line in bodies[name][0].splitlines()
                if not line.strip().startswith("#")
            ).strip()
            for name in (PR_VALIDATION.name, APPLY.name)
            if bodies[name]
        }
        self.assertEqual(
            1,
            len(stripped),
            "the two changed-path resolutions have drifted apart in their code, so a "
            "pull request and the merge of that same pull request could resolve "
            "different stacks -- the reviewer approving one plan and the pipeline "
            "applying another",
        )

    def test_the_host_converge_discovery_reads_each_stacks_own_declaration(self) -> None:
        """SPECIFIED -- Each Stack Declares Its Own Pipeline
        Configuration's scenario "A new environment needs no workflow edit",
        which names the host-converge workflow among those that SHALL cover a
        new stack directory, and whose declaration now sits under
        `terraform/stacks/`.

        DERIVED for the shape -- that change's design.md decision 2a: this
        fourth body enumerates `ansible/inventory/*.hcloud.yml` rather than the
        Terraform root, and reaches into the Terraform root only to read the
        stack's declaration. So it is located by the inventory root it
        enumerates, and then asserted to name the stack root -- the reverse of
        the locator used for the other three.
        """
        candidates = [
            body
            for _, body in run_bodies(HOST_CONVERGE)
            if "ansible/inventory" in body
            and "GITHUB_OUTPUT" in body
            and not ACTIONS_EXPRESSION.search(body)
        ]
        self.assertEqual(
            1,
            len(candidates),
            "expected exactly one `run:` step in host-converge.yml that enumerates "
            f"the inventory root and writes to `$GITHUB_OUTPUT`, found {len(candidates)}",
        )
        body = candidates[0]
        self.assertIn(
            STACK_ROOT_SEGMENT,
            body,
            "host-converge.yml's discovery reads no declaration under "
            f"`{STACK_ROOT_SEGMENT}/`, so a converge row carries no GitHub Environment "
            "and no read-only secret of the stack's own",
        )
        for kept in ("inventory_root", "group_vars_root"):
            self.assertIn(
                kept,
                body,
                f"host-converge.yml's discovery no longer names {kept!r}. That handle "
                "enumerates `ansible/inventory/`, which `docs/change-queue.md` entry 62 "
                "renames and this change does not -- renaming it here is the sweep "
                "overreaching, not completing",
            )

    def test_no_discovery_body_still_names_an_environments_root(self) -> None:
        """DERIVED -- that change's tasks.md 3.1 and 3.2, and its proposal.md:
        "A directory called `stacks/` iterated by a shell variable called
        `environments_root` ... is a scheme that contradicts itself inside one
        file, and a reader has no way to tell which word is load-bearing."

        Paired with the presence of `stacks_root`, because an absence
        assertion alone passes against a body that was deleted.
        """
        for path in DISCOVERY_WORKFLOWS:
            with self.subTest(workflow=path.name):
                text = uncommented(read_text(path))
                self.assertIsNone(
                    RETIRED_IDENTIFIERS["environments_root"].search(text),
                    f"{path.name} still iterates an `environments_root`, while the "
                    "directory it names has become `terraform/stacks/`",
                )
                self.assertIsNotNone(
                    REPLACEMENT_IDENTIFIERS["stacks_root"].search(text),
                    f"{path.name} names no `stacks_root`, so either the rename has not "
                    "reached it or its discovery body is gone",
                )


# --------------------------------------------------------------------------
# iac-cicd-pipeline -- the matrix, the job outputs and the shell variables
# --------------------------------------------------------------------------


class TestTheMatrixAndItsOutputsNameTheStack(unittest.TestCase):
    """MODIFIED requirements: Pull Request Plan Visibility, Gated Production
    Apply Applies the Reviewed Plan, Serialized Terraform Runs and Scheduled
    Drift Detection (iac-cicd-pipeline).

    DERIVED throughout, and stated as such: no scenario names a matrix key or a
    job output. What the scenarios state is that the pipeline iterates over
    STACKS, and that change's design.md decision 2 is what resolves the
    obligation onto these identifiers -- "rename the word where it names the
    unit the pipeline discovers, plans, applies, drift-checks and converges".
    """

    def test_no_workflow_still_carries_a_retired_identifier(self) -> None:
        """DERIVED -- that change's tasks.md 3.3 and 8.4. 8.4 states this as
        the check that distinguishes a sweep that is complete from one that is
        mostly complete: "a stale occurrence in a comment or an `::error::`
        message fails nothing on its own"."""
        for path in DISCOVERY_WORKFLOWS:
            text = read_text(path)
            for label, pattern in sorted(RETIRED_IDENTIFIERS.items()):
                with self.subTest(workflow=path.name, identifier=label):
                    found = [
                        f"line {number}"
                        for number, line in enumerate(text.splitlines(), start=1)
                        if pattern.search(line)
                    ]
                    self.assertEqual(
                        [],
                        found,
                        f"{path.name} still carries the retired identifier {label!r} at "
                        f"{found}. Comments and `::error::` messages are read here too, "
                        "deliberately: a refusal message naming the mechanism by a word "
                        "the mechanism no longer uses is the same defect one layer out",
                    )

    def test_every_workflow_carries_the_replacements_expected_of_it(self) -> None:
        """DERIVED -- that change's tasks.md 3.3. Paired with the absence
        assertion above: a workflow emptied of the old word has not thereby
        been renamed, and the per-workflow table this reads is the one place
        the expectation is written down."""
        for path in DISCOVERY_WORKFLOWS:
            text = uncommented(read_text(path))
            for label in EXPECTED_REPLACEMENTS[path.name]:
                with self.subTest(workflow=path.name, identifier=label):
                    self.assertIsNotNone(
                        REPLACEMENT_IDENTIFIERS[label].search(text),
                        f"{path.name} names no {label!r}, which this change's tasks.md "
                        "3.3 obliges it to carry",
                    )

    def test_no_job_publishes_an_output_named_for_the_environment(self) -> None:
        """DERIVED -- that change's tasks.md 3.3: the `discover`, `affected`
        and `planned` job outputs named `environments` become `stacks`."""
        for path in DISCOVERY_WORKFLOWS:
            outputs = declared_outputs(path)
            with self.subTest(workflow=path.name):
                offenders = sorted(
                    job for job, names in outputs.items() if "environments" in names
                )
                self.assertEqual(
                    [],
                    offenders,
                    f"{path.name}: these jobs still publish an output named "
                    f"`environments`: {offenders}",
                )
                publishing = sorted(job for job, names in outputs.items() if "stacks" in names)
                self.assertTrue(
                    publishing,
                    f"{path.name} publishes no job output named `stacks`, so nothing "
                    f"downstream can iterate the discovered set. Outputs found: "
                    f"{ {job: sorted(names) for job, names in outputs.items() if names} }",
                )

    def test_every_needs_output_read_names_an_output_that_job_publishes(self) -> None:
        """DERIVED -- that change's design.md decision 6, which records that
        this agreement is asserted for `apply.yml` alone and that "`drift.yml`
        and `pr-validation.yml` have no equivalent, and a missed reference in
        either surfaces as a failing job in CI rather than as a silent skip".

        Widened here to all four. A rename that moves an output but not one of
        its readers yields `needs.discover.outputs.environments`, which
        evaluates to the empty string rather than erroring -- an empty matrix,
        a skipped dependent job and a green run that did nothing. That is the
        exact failure Each Stack Declares Its Own Pipeline Configuration's
        last scenario forbids, reached through the rename rather than through
        discovery.

        THIS TEST PASSES BEFORE THE IMPLEMENTATION EXISTS, deliberately -- it is
        the second of the two named above. The four workflows agree with
        themselves today; what this holds is that they still agree once every
        output and every reader of it has been renamed, and a rename that moved
        one but not the other is the only state that makes it red.
        """
        for path in DISCOVERY_WORKFLOWS:
            outputs = declared_outputs(path)
            with self.subTest(workflow=path.name):
                dangling = [
                    f"needs.{job}.outputs.{name}"
                    for job, name in needs_output_reads(path)
                    if name not in outputs.get(job, set())
                ]
                self.assertEqual(
                    [],
                    dangling,
                    f"{path.name} reads {dangling}, which no such job publishes. GitHub "
                    "resolves an unknown output to the empty string rather than failing, "
                    "so this is an empty matrix and a green run that did nothing",
                )

    def test_the_host_converge_dispatch_input_names_the_stack(self) -> None:
        """DERIVED -- that change's tasks.md 3.4, which calls this "the one
        operator-facing rename in the change: a dispatch typed against the old
        input name silently converges everything rather than one host, because
        an unrecognised input is not an error"."""
        inputs = (triggers(load_yaml(HOST_CONVERGE)).get("workflow_dispatch") or {}).get(
            "inputs"
        ) or {}
        self.assertIn(
            "stack",
            inputs,
            f"host-converge.yml's `workflow_dispatch` declares no `stack` input; it "
            f"declares {sorted(inputs)}",
        )
        self.assertNotIn(
            "environment",
            inputs,
            "host-converge.yml still declares a `workflow_dispatch` input named "
            "`environment`. An operator dispatching against the retired name gets no "
            "error -- an unrecognised input is silently ignored -- and converges every "
            "host rather than the one they named",
        )


# --------------------------------------------------------------------------
# The boundary: what this change deliberately does NOT rename
#
# iac-cicd-pipeline / Gated Production Apply Applies the Reviewed Plan and
# Credential Scoping by Privilege; iac-safety-hardening / Consistent Resource
# Labeling; and, for `target_environment`, iac-host-configuration's
# "Host Configuration Names the Environment It Targets", which this change
# leaves untouched in full.
# --------------------------------------------------------------------------


class TestTheEnvironmentAxisIsNotRenamedWithTheUnit(unittest.TestCase):
    """MODIFIED requirements: Gated Production Apply Applies the Reviewed Plan
    and Credential Scoping by Privilege (iac-cicd-pipeline), and Consistent
    Resource Labeling (iac-safety-hardening).

    The change's own proposal.md calls the boundary "where this change is
    easiest to get wrong", and names four keepers. A sweep that renamed them
    would be renaming a different thing that happens to share a word, and the
    tests below are the half of the check that catches OVERREACH rather than
    incompleteness -- the direction the retired-identifier sweep above cannot
    see.
    """

    def test_the_converge_play_still_names_the_environment_group_it_targets(self) -> None:
        """SPECIFIED, by a requirement this change does not modify -- Host
        Configuration Names the Environment It Targets
        (`openspec/specs/iac-host-configuration/spec.md`), which governs
        `target_environment` and the `--vault-id` label and which this change
        leaves untouched in full. DERIVED for the mapping onto these three
        surfaces: that change's design.md decision 2a.

        Renaming these would break `ansible/playbooks/host-baseline.yml`,
        `.ansible-lint` and `.pre-commit-config.yaml`, none of which this change
        touches.

        THIS TEST PASSES BEFORE THE IMPLEMENTATION EXISTS, deliberately, and
        that is recorded here rather than left to be read as an alarm. It is one
        of exactly two in this module that do: it guards against OVERREACH, so
        its subject is a property the tree already has and must keep. It goes
        red only on a sweep that went too far, which is a state the tree cannot
        be in until the sweep runs. See `test-plan.md`, which names both.
        """
        text = uncommented(read_text(HOST_CONVERGE))
        for kept in ("TARGET_ENVIRONMENT", "target_environment=", "--vault-id"):
            with self.subTest(handle=kept):
                self.assertIn(
                    kept,
                    text,
                    f"host-converge.yml no longer names {kept!r}. It names the Ansible "
                    "group the converge play targets -- the environment axis, not the "
                    "unit the pipeline iterates -- and its consumers are outside this "
                    "change's diff",
                )

    def test_the_target_environment_handle_keeps_its_name(self) -> None:
        """DERIVED -- that change's design.md decision 2: the handle "keeps its
        name and changes its source". Renaming the variable itself would break
        `ansible/playbooks/host-baseline.yml`, `.ansible-lint` and
        `.pre-commit-config.yaml`, which read it under this name.

        SUPERSEDED IN PART BY THE CHANGE rename-the-stacks-and-their-resources,
        and this test's own docstring predicted it: it used to assert the
        assignment reads `matrix.stack.name`, "what keeps this true when entry
        62 makes the group `production` while the stack is `main-production`".
        Entry 62 is that change, and the prediction was wrong in one direction
        -- the group stopped being derivable from the stack's name at all, so
        reading `matrix.stack.name` became the defect rather than the
        obligation. Where the value now comes from is asserted by
        `test_a_stack_and_its_environment_are_named_separately`, against the
        stack's own declaration.

        What survives here is the half this class is for: the handle's NAME is
        part of the environment axis and did not move when the unit was renamed.
        """
        workflow = load_yaml(HOST_CONVERGE)
        assignments = []
        for job_name, index, step in steps(workflow):
            value = (step.get("env") or {}).get("TARGET_ENVIRONMENT")
            if value is not None:
                assignments.append((step_label(job_name, index, step), compact(value)))
        self.assertTrue(
            assignments,
            "no step in host-converge.yml assigns TARGET_ENVIRONMENT, so the converge "
            "play is given no group to target -- and the handle's name is read by "
            "ansible/playbooks/host-baseline.yml, .ansible-lint and "
            ".pre-commit-config.yaml, none of which this change renames",
        )
        wrong = [
            (label, value)
            for label, value in assignments
            if "matrix.environment" in value
        ]
        self.assertEqual(
            [],
            wrong,
            f"these TARGET_ENVIRONMENT assignments still read a `matrix.environment` "
            f"key: {wrong}. That key was renamed to `matrix.stack` when the unit was "
            "renamed; a handle still reading the old one is a rename that stopped "
            "halfway",
        )

    def test_every_gated_job_still_attaches_to_the_github_environment_its_stack_declares(
        self,
    ) -> None:
        """SPECIFIED -- Gated Production Apply Applies the Reviewed Plan:
        "Every stack's apply job SHALL declare an `environment:`", and
        Credential Scoping by Privilege: "No job that runs `terraform plan`
        SHALL declare an `environment:`".

        `github_environment` and the `environment:` job key are two of the four
        keepers: they name a GitHub Environment, which is what GitHub calls it.
        What moves is only the matrix key the value is reached THROUGH.
        """
        workflow = load_yaml(APPLY)
        applying = {
            name: job
            for name, job in jobs(workflow).items()
            if any(
                TERRAFORM_APPLY.search(str(step.get("run") or ""))
                for step in (job.get("steps") or [])
            )
        }
        self.assertTrue(
            applying,
            "no job in apply.yml runs `terraform apply`, so there is no gated job to read",
        )
        for name, job in sorted(applying.items()):
            with self.subTest(job=name):
                declared = compact(job.get("environment", ""))
                self.assertTrue(
                    declared,
                    f"apply.yml's `{name}` runs `terraform apply` and declares no "
                    "`environment:`, so it is not gated at all",
                )
                self.assertIn(
                    GITHUB_ENVIRONMENT_FIELD,
                    declared,
                    f"apply.yml's `{name}` declares `environment: {declared}`, which "
                    "does not read the `github_environment` field of the stack's own "
                    "declaration. Naming an Environment in workflow text is what Each "
                    "Stack Declares Its Own Pipeline Configuration forbids",
                )
                self.assertIn(
                    "matrix.stack",
                    declared,
                    f"apply.yml's `{name}` reaches its GitHub Environment through "
                    f"{declared!r} rather than through `matrix.stack`",
                )

    def test_the_resource_labels_still_name_the_environment_axis(self) -> None:
        """SPECIFIED -- Consistent Resource Labeling: "Every `hcloud_*` resource
        ... SHALL carry an `environment` label naming the environment its stack
        belongs to and a `managed_by = "terraform"` label", and its two
        scenarios, which assert `environment = "prod"` on resources created via
        `terraform/stacks/prod/`.

        SUPERSEDED IN PART, AND RE-POINTED RATHER THAN DELETED. This test used
        to assert the environment label EQUALS the stack's directory name. That
        equality held only while a repository had one tenant, and this test's
        own docstring said so: "the first thing entry 62 will have to restate".
        The change rename-the-stacks-and-their-resources restated it -- the
        directory is `main-production` and the label is `production` -- so the
        equality is now the defect rather than the obligation, and asserting its
        NEGATION is what this class is for: the axis is not the unit. What the
        label must positively be is asserted by
        `test_a_stack_and_its_environment_are_named_separately`, which reads it
        against the stack's own declared group rather than against its name.
        """
        directories = stack_directories()
        self.assertTrue(directories, "no stack directory to read; see the first test")
        for directory in directories:
            with self.subTest(stack=directory.name):
                labels: dict = {}
                for key, value in LABEL_ASSIGNMENT.findall(stack_terraform_text(directory)):
                    labels.setdefault(key, set()).add(value)
                declared = labels.get("environment", set())
                self.assertTrue(
                    declared,
                    f"{directory.name} declares no `environment` label at all. The "
                    "axis survived the rename of the unit; a stack that carries no "
                    "environment label is one no inventory source can group",
                )
                self.assertNotIn(
                    directory.name,
                    declared,
                    f"{directory.name} declares an environment label equal to its own "
                    f"DIRECTORY name ({sorted(declared)}). The two coincided while "
                    "this repository had one tenant and they are separate axes: a "
                    "stack is a (tenant, environment) pair and the label is the "
                    "environment alone. A label that tracks the directory is the "
                    "coincidence this class exists to stop being relied on",
                )
                self.assertIn(
                    "terraform",
                    labels.get("managed_by", {"terraform"}),
                    f"{directory.name} declares a `managed_by` label that is not "
                    f"`terraform`: {sorted(labels.get('managed_by', set()))}",
                )


# --------------------------------------------------------------------------
# iac-cicd-pipeline / Pull Request Validation Checks, Pull Request Plan
# Visibility, Scheduled Drift Detection; iac-safety-hardening / Automated
# Dependency Updates -- the consumers of the path
# --------------------------------------------------------------------------


class TestThePathRuleAndItsConsumersFollowTheStackRoot(unittest.TestCase):
    """MODIFIED requirements: Pull Request Validation Checks, Pull Request Plan
    Visibility and Scheduled Drift Detection (iac-cicd-pipeline), and Automated
    Dependency Updates (iac-safety-hardening)."""

    def test_the_changed_files_filter_names_the_stack_root(self) -> None:
        """SPECIFIED -- Pull Request Plan Visibility: "The stacks a pull request
        can affect SHALL be determined from the paths it changes", and its
        scenario "Reviewer sees the plan without leaving GitHub", whose WHEN is
        a pull request changing `terraform/stacks/<name>/`.

        A filter left at the old path matches nothing after the move, so no
        pull request touching a stack is ever recognised as a Terraform change
        -- and `terraform validate`, `tflint` and every plan are conditioned on
        that filter's output. The failure is a green pull request that planned
        nothing.
        """
        workflow = load_yaml(PR_VALIDATION)
        filters = [
            str((step.get("with") or {}).get("filters"))
            for _, _, step in steps(workflow)
            if "paths-filter" in str(step.get("uses") or "")
        ]
        self.assertTrue(
            filters, "pr-validation.yml runs no changed-paths filter step"
        )
        joined = "\n".join(filters)
        self.assertIn(
            f"{STACK_ROOT_SEGMENT}/**",
            joined,
            f"pr-validation.yml's changed-files filter does not name "
            f"`{STACK_ROOT_SEGMENT}/**`; it reads: {joined!r}",
        )
        self.assertNotIn(
            OLD_ROOT_SEGMENT,
            joined,
            "pr-validation.yml's changed-files filter still names the old Terraform "
            "root, which after the move matches no file at all",
        )

    def test_validate_and_tflint_discover_directories_under_the_stack_root(self) -> None:
        """SPECIFIED -- Pull Request Validation Checks: "`terraform validate`
        and `tflint` SHALL run against every directory under
        `terraform/modules/` and `terraform/stacks/` that contains Terraform
        configuration, discovered rather than enumerated", and its scenario "A
        newly added module is validated and linted without a workflow change"."""
        found = {}
        for label, body in run_bodies(PR_VALIDATION):
            for tool in ("terraform validate", "tflint"):
                if tool in body:
                    found.setdefault(tool, []).append((label, body))
        for tool in ("terraform validate", "tflint"):
            with self.subTest(tool=tool):
                bodies = found.get(tool) or []
                self.assertTrue(bodies, f"pr-validation.yml runs no {tool} step")
                iterating = [
                    label
                    for label, body in bodies
                    if f"{STACK_ROOT_SEGMENT}/*" in body and "terraform/modules/*" in body
                ]
                self.assertTrue(
                    iterating,
                    f"no {tool} step in pr-validation.yml iterates both "
                    f"`terraform/modules/*/` and `{STACK_ROOT_SEGMENT}/*/`. A loop left "
                    "at the old root expands to nothing and the step passes having "
                    f"checked no directory at all. Steps found: "
                    f"{[label for label, _ in bodies]}",
                )

    def test_dependabot_names_every_stack_directory_under_the_stack_root(self) -> None:
        """SPECIFIED -- Automated Dependency Updates: "adding a Terraform module
        or stack SHALL include adding it here", and scenario "Every
        lockfile-bearing directory is covered".

        `TestDependabotCoverage` in `test_ci_configuration.py` already compares
        the two SETS and is written generically enough to survive this rename
        untouched. What it cannot see is a configuration that names the OLD
        root while the lockfiles have moved -- that is a divergence it reports,
        but only after the move, and its message names a missing directory
        rather than a stale one. This reads the entries themselves, which is
        what says the rename reached this file.
        """
        config = load_yaml(DEPENDABOT)
        configured: list[str] = []
        for entry in config.get("updates") or []:
            if entry.get("package-ecosystem") != "terraform":
                continue
            if entry.get("directory"):
                configured.append(str(entry["directory"]))
            configured.extend(str(value) for value in (entry.get("directories") or []))
        self.assertTrue(configured, "dependabot.yml configures no `terraform` directories")
        stale = [directory for directory in configured if OLD_ROOT_SEGMENT in directory]
        self.assertEqual(
            [],
            stale,
            f"these Dependabot `terraform` entries still name the old root: {stale}. "
            "Dependabot's terraform ecosystem has no discovery mechanism, so a "
            "directory this list misnames is not partially covered -- it is uncovered, "
            "and its provider pins rot with no signal at all",
        )
        for directory in stack_directories():
            with self.subTest(stack=directory.name):
                self.assertIn(
                    f"/{STACK_ROOT_SEGMENT}/{directory.name}",
                    configured,
                    f"no Dependabot `terraform` entry names "
                    f"/{STACK_ROOT_SEGMENT}/{directory.name}; configured: {configured}",
                )

    def test_the_plan_comment_heading_and_the_comment_locator_agree_on_the_stack_root(
        self,
    ) -> None:
        """SPECIFIED -- Pull Request Plan Visibility: the workflow SHALL post
        each plan "identifying which stack each plan belongs to", and its
        scenario "A shared module change is planned against every environment",
        which obliges a plan per stack "each identifying the stack it belongs
        to".

        The heading is built in a shell body and found again by a `body-includes`
        expression, through two different interpolation mechanisms. Their
        literal halves have to agree or the workflow finds nothing and posts a
        second comment every run -- which that change's proposal.md accepts ONCE
        as the cost of the rename, and which must not become permanent.
        """
        workflow = load_yaml(PR_VALIDATION)
        headings = set()
        for _, body in run_bodies(PR_VALIDATION):
            for line in body.splitlines():
                stripped = line.strip()
                if stripped.startswith("heading=") and "Terraform Plan" in stripped:
                    headings.add(
                        normalised_interpolation(shell_double_quoted_value(stripped))
                    )
        locators = {
            normalised_interpolation((step.get("with") or {}).get("body-includes", ""))
            for _, _, step in steps(workflow)
            if (step.get("with") or {}).get("body-includes")
        }
        self.assertEqual(
            1,
            len(headings),
            f"expected exactly one plan-comment heading in pr-validation.yml, found "
            f"{sorted(headings)}",
        )
        heading = headings.pop()
        self.assertIn(
            STACK_ROOT_SEGMENT,
            heading,
            f"the plan comment's heading does not name `{STACK_ROOT_SEGMENT}`: "
            f"{heading!r}",
        )
        matching = [locator for locator in locators if locator in heading]
        self.assertTrue(
            matching,
            f"no `body-includes` locator in pr-validation.yml is a prefix of the "
            f"heading the plan step writes. Heading: {heading!r}; locators: "
            f"{sorted(locators)}. A locator and a heading that disagree leave every "
            "run posting a new comment instead of editing its own",
        )

    def test_the_drift_issue_title_names_the_stack_root(self) -> None:
        """SPECIFIED -- Scheduled Drift Detection: the workflow SHALL create or
        update "a **single, deduplicated** GitHub issue for that stack", and
        "The issue SHALL be identified per stack".

        `drift.yml` matches its dedup key on the WHOLE title, deliberately, so
        the title and the search have to be built from the same literal. That
        change's proposal.md records the one-time cost -- an open issue under
        the old title is matched by nothing after the rename and is closed by
        hand at merge (tasks.md 9.1a) -- and that cost is only bounded if the
        title moved to the new root rather than being left behind.
        """
        titles = [
            line.strip()
            for _, body in run_bodies(DRIFT)
            for line in body.splitlines()
            if "issue_title=" in line
        ]
        self.assertTrue(titles, "drift.yml builds no issue title")
        for title in titles:
            with self.subTest(line=title):
                self.assertIn(
                    STACK_ROOT_SEGMENT,
                    title,
                    f"drift.yml's issue title does not name `{STACK_ROOT_SEGMENT}`: "
                    f"{title!r}",
                )
                self.assertNotIn(
                    OLD_ROOT_SEGMENT,
                    title,
                    "drift.yml's issue title still names the old Terraform root, so "
                    "every drift report points at a path that no longer exists",
                )


# --------------------------------------------------------------------------
# iac-safety-hardening / Write Credentials Confined to the Gated Pipeline
# --------------------------------------------------------------------------


class TestTheWriteCredentialRecordNamesTheStackRoot(unittest.TestCase):
    """MODIFIED requirement: Write Credentials Confined to the Gated Pipeline
    (iac-safety-hardening)."""

    def test_the_agents_record_states_the_prohibition_over_the_stack_root(self) -> None:
        """SPECIFIED -- scenario "An agent opening the repository is told the
        boundary", and the requirement's scenarios "Local apply is refused by
        the API" and "Local plan remains available", both of which name "any
        stack directory under `terraform/stacks/`".

        `TestTheWriteCredentialBoundaryIsStatedToAgents` and
        `TestTheWriteCredentialRecordCoversEveryEnvironment` in the modules
        beside this one already assert that the record generalises over stacks
        rather than naming one. This asserts only the half this change moves:
        that the directory the record points at is the one that now exists. A
        prohibition naming a directory that is not there is one a reader has
        been given a reason to doubt.
        """
        agents = ROOT / "AGENTS.md"
        text = read_text(agents)
        self.assertIn(
            STACK_ROOT_SEGMENT,
            text,
            f"AGENTS.md does not name `{STACK_ROOT_SEGMENT}/`, so the record of where "
            "`terraform apply` may not be run points at no directory in this tree",
        )
        self.assertNotIn(
            OLD_ROOT_SEGMENT,
            text,
            "AGENTS.md still states the never-apply-locally prohibition over the old "
            "Terraform root, which no longer exists",
        )


# --------------------------------------------------------------------------
# The completeness check
# --------------------------------------------------------------------------


class TestNoCommittedFileStillNamesTheOldTerraformRoot(unittest.TestCase):
    """DERIVED -- that change's tasks.md 8.4, which states this sweep as what
    "proves the sweep was complete rather than mostly complete, since a stale
    occurrence in a comment or an `::error::` message fails nothing".

    No scenario states it, and it is the single assertion in this module most
    likely to be argued with, so its scope is written out rather than left to
    be read off the code:

    - It reads the whole tree, not `.github/` -- AGENTS.md's "Testing" section
      puts any property that is a static read of a committed file in this
      suite's scope "wherever the file holding it lives".
    - `openspec/` is pruned by the walker this borrows, which is a superset of
      the exclusions tasks.md 8.4 names and errs permissively.
    - This module is excluded by path, because its own prose names the old root.
    - Nothing else is excluded, and no allowance list is offered. Adding one is
      a reviewable decision about what this change decided to keep, and the
      change decided to keep no occurrence of the PATH -- only four occurrences
      of the WORD, none of which this sweep matches.
    """

    def test_no_committed_file_names_the_old_terraform_root(self) -> None:
        """DERIVED -- see the class docstring."""
        offences = old_root_occurrences()
        self.assertEqual(
            [],
            offences,
            f"these committed files still name `{OLD_ROOT_SEGMENT}`, a path this "
            f"change removes: {offences}. Half a rename leaves a reader unable to tell "
            "which word is load-bearing, and a stale path in a comment, an error "
            "message or a runbook fails nothing on its own",
        )


# --------------------------------------------------------------------------
# Discriminators
#
# Several reads above are near-vacuous over a repository holding two stacks,
# and one of them -- the sweep -- reports a clean tree by finding nothing,
# which is also what it would report having read the wrong thing. These build
# a fixture tree and establish that each read reports what it claims to.
# --------------------------------------------------------------------------


class TestTheSweepReadsCommittedFilesOnly(unittest.TestCase):
    """DERIVED -- `AGENTS.md` scopes this suite to a static read of a COMMITTED
    file, and `docs/change-queue.md` entry 68 names the class this closes.

    `old_root_occurrences()` selected its files with a filesystem walk until
    this was written, and that walk prunes four directory names of which
    `.molecule-home/` is not one. That directory does not exist in continuous
    integration and appears the moment a developer follows this repository's
    own Molecule instructions, carrying vendored third-party collections -- so
    the sweep went red on a provisioned machine for code nobody here wrote,
    while staying green on a runner. A check that disagrees with itself between
    the two trains its readers to discount it.

    THE CONVERSE IS NOT RESTATED HERE, deliberately. That the sweep still
    REPORTS a bare old-root reference is established end to end by
    `TestTheseReadsDiscriminate` below, which builds scratch trees carrying the
    three real spellings and asserts each is found. Restating it in this class
    would need a tracked fixture -- a `git add` from inside a test -- and a
    weaker assertion that only proved the regular expression still compiles is
    exactly the "achieved by reading less" outcome this class exists against.
    """

    @staticmethod
    def _remove_empty(directories: list[Path]) -> None:
        for directory in reversed(directories):
            try:
                directory.rmdir()
            except OSError:
                break  # not empty: something else put content here, leave it

    def test_an_untracked_file_naming_the_old_root_is_not_an_offence(self) -> None:
        """DERIVED -- see the class docstring. The fixture's path mirrors the
        real one: a vendored collection under the Molecule home this
        repository's own per-working-tree namespacing creates."""
        relative = (
            ".molecule-home/collections/ansible_collections/community/docker/fixture.yml"
        )
        path = ROOT / relative
        if path.exists():  # a provisioned tree may hold the real thing
            self.skipTest(f"{relative} already exists; refusing to overwrite it")
        # Every directory this creates is removed again, deepest first. A test
        # that leaves `.molecule-home/` behind has planted the very thing this
        # class exists to tell a reader is not the suite's subject.
        created = [
            parent
            for parent in reversed(path.parents)
            if ROOT in parent.parents and not parent.exists()
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n- path: environments/prod\n", encoding="utf-8")
        self.addCleanup(self._remove_empty, created)
        self.addCleanup(path.unlink, missing_ok=True)

        reported = [entry for entry in old_root_occurrences() if ".molecule-home/" in entry]
        self.assertEqual(
            [],
            reported,
            "an UNTRACKED file naming the old root was reported as an offence: "
            f"{reported}. This sweep's subject is the committed file; reading a "
            "developer's provisioned content makes it red on a working machine and "
            "green on a runner, which is `docs/change-queue.md` entry 68's class",
        )


class TestTheseReadsDiscriminate(unittest.TestCase):
    """DERIVED. The idiom is the suite's own -- `TestTheseReadsDiscriminate`
    in `test_a_second_environment.py`, `TestTheSuiteDiscriminates` and the
    several `...IsARealReadOfTheFile` classes in `test_ci_configuration.py`.

    A check that passes because it read nothing is the failure mode this whole
    suite exists against, and at two stacks the collision reads below are
    vacuous over the real tree.
    """

    def _tree(self) -> Path:
        directory = tempfile.mkdtemp(prefix="stack-vocabulary-")
        self.addCleanup(self._remove, directory)
        return Path(directory)

    @staticmethod
    def _remove(directory: str) -> None:
        for here, subdirectories, filenames in os.walk(directory, topdown=False):
            for name in filenames:
                os.unlink(os.path.join(here, name))
            for name in subdirectories:
                os.rmdir(os.path.join(here, name))
        os.rmdir(directory)

    def _stack(self, tree: Path, name: str, declaration: str | None = None) -> Path:
        directory = tree / "terraform" / "stacks" / name
        directory.mkdir(parents=True)
        (directory / "main.tf").write_text(
            'module "server" {\n  source      = "../../modules/server"\n'
            f'  environment = "{name}"\n}}\n',
            encoding="utf-8",
        )
        (directory / "versions.tf").write_text(
            "terraform {\n  cloud {\n    workspaces {\n"
            f'      name = "{WORKSPACE_PREFIX}{name}"\n'
            "    }\n  }\n}\n",
            encoding="utf-8",
        )
        (directory / "terraform.tfvars").write_text("name = \"x\"\n", encoding="utf-8")
        if declaration is not None:
            (directory / "pipeline.yml").write_text(declaration, encoding="utf-8")
        return directory

    def test_the_stack_census_reads_the_directories_it_is_given(self) -> None:
        tree = self._tree()
        self._stack(tree, "alpha", "github_environment: a\nread_only_secret: A\n")
        self._stack(tree, "beta", "github_environment: b\nread_only_secret: B\n")
        self.assertEqual(
            ["alpha", "beta"],
            [directory.name for directory in stack_directories(tree)],
            "the stack census did not read the fixture tree's own directories",
        )

    def test_a_stack_missing_its_declaration_is_reported(self) -> None:
        tree = self._tree()
        self._stack(tree, "alpha", "github_environment: a\nread_only_secret: A\n")
        self._stack(tree, "beta", declaration=None)
        self.assertEqual(
            {"alpha": {"github_environment": "a", "read_only_secret": "A"}, "beta": None},
            stack_declarations(tree),
            "a stack directory carrying no `pipeline.yml` was not reported as "
            "undeclared, so the census above would pass over one",
        )

    def test_an_unparseable_declaration_is_reported_rather_than_raised(self) -> None:
        tree = self._tree()
        self._stack(tree, "alpha", "github_environment: [unclosed\n")
        self.assertEqual(
            {"alpha": None},
            stack_declarations(tree),
            "an unparseable declaration must be reported as undeclared, naming the "
            "stack, rather than raising out of the census",
        )

    def test_the_old_root_sweep_reports_a_planted_occurrence(self) -> None:
        tree = self._tree()
        (tree / "docs").mkdir()
        (tree / "docs" / "runbook.md").write_text(
            f"first line\nplan from {OLD_ROOT_SEGMENT}/prod\nlast line\n",
            encoding="utf-8",
        )
        self.assertEqual(
            ["docs/runbook.md:2"],
            old_root_occurrences(tree),
            "the sweep did not report a planted occurrence of the old root, so a "
            "clean result from it says nothing",
        )

    def test_the_old_root_sweep_reports_nothing_on_a_swept_tree(self) -> None:
        tree = self._tree()
        (tree / "docs").mkdir()
        (tree / "docs" / "runbook.md").write_text(
            f"plan from {STACK_ROOT_SEGMENT}/prod\n", encoding="utf-8"
        )
        self.assertEqual(
            [],
            old_root_occurrences(tree),
            "the sweep reported an offence against a tree naming only the new root, so "
            "it is matching something other than the old path",
        )

    def test_the_old_root_sweep_refuses_a_tree_it_could_not_read(self) -> None:
        tree = self._tree()
        with self.assertRaises(AssertionError):
            old_root_occurrences(tree)

    def test_the_old_root_sweep_reports_a_bare_directory_reference(self) -> None:
        """The defect this pair was added for. Two committed files named the
        directory WITHOUT its `terraform/` prefix -- a `.tftest.hcl` comment
        and a `docs/change-queue.md` entry -- and the sweep reported a clean
        tree over both. The instances were corrected before this was written,
        so the real tree establishes nothing about it; only a fixture can."""
        tree = self._tree()
        (tree / "docs").mkdir()
        (tree / "docs" / "queue.md").write_text(
            "first line\n"
            f"`{OLD_ROOT_DIRECTORY}/prod` couples the volume to the server\n"
            f"the {OLD_ROOT_DIRECTORY}/prod-level variable\n"
            f"(not {OLD_ROOT_DIRECTORY}/prod)\n",
            encoding="utf-8",
        )
        self.assertEqual(
            ["docs/queue.md:2", "docs/queue.md:3", "docs/queue.md:4"],
            old_root_occurrences(tree),
            "the sweep passed over a bare reference to the old directory, which is "
            "the class of stale path it was widened to catch -- in a backticked "
            "citation, in a hyphenated compound and in a parenthetical",
        )

    def test_the_old_root_sweep_does_not_fire_on_the_word_itself(self) -> None:
        """The direction that matters more, because a pattern keyed on the word
        rather than on the path-like shape would be satisfiable only by the
        overreach this change forbids. Every line below is text this repository
        keeps, and none of them names a directory."""
        tree = self._tree()
        (tree / "docs").mkdir()
        kept = (
            "each environment's own GitHub Environment gates its apply",
            "a pre-commit hook environment is built against a specific interpreter",
            "the Hetzner `environment` label names the environment axis",
            "resource labels carry environment = \"prod\"",
            "TARGET_ENVIRONMENT is exported into the process environment",
            "two environments do not queue behind each other",
            "`my_environments` and `sub-environments` are identifiers, not paths",
            "the environments and/or the stacks",
        )
        (tree / "docs" / "prose.md").write_text(
            "\n".join(kept) + "\n", encoding="utf-8"
        )
        self.assertEqual(
            [],
            old_root_occurrences(tree),
            "the sweep fired on prose that names no directory. Keyed on the word "
            "rather than on the path-like shape it would report `docs/` and "
            "`README.md` many times over, and the only route to green would be to "
            "rename the environment axis -- which is the overreach "
            "`TestTheEnvironmentAxisIsNotRenamedWithTheUnit` exists against",
        )

    def test_the_old_root_sweep_still_reports_the_prefixed_path(self) -> None:
        """Widening a pattern can narrow it. This holds that the prefixed form
        the sweep was written for -- including the form with NO trailing slash,
        which a bare-directory pattern alone would miss -- is still an offence.
        """
        tree = self._tree()
        (tree / "docs").mkdir()
        (tree / "docs" / "runbook.md").write_text(
            f"plan from {OLD_ROOT_SEGMENT}/prod\n"
            f"the whole of {OLD_ROOT_SEGMENT} moves\n",
            encoding="utf-8",
        )
        self.assertEqual(
            ["docs/runbook.md:1", "docs/runbook.md:2"],
            old_root_occurrences(tree),
            "the widened pattern no longer reports the prefixed path it was "
            "originally written for",
        )

    def test_the_retired_identifier_patterns_do_not_match_the_keepers(self) -> None:
        """The four keepers all contain the word `environment`. A pattern that
        matched one of them would make the sweep above unsatisfiable, and the
        only way to reach green would be to perform the overreach the change
        forbids."""
        keepers = (
            "github_environment: production",
            "    environment: ${{ matrix.stack.github_environment }}",
            "TARGET_ENVIRONMENT: ${{ matrix.stack.name }}",
            'ansible-playbook -e "target_environment=$TARGET_ENVIRONMENT"',
            '--vault-id "$TARGET_ENVIRONMENT@$HOME/.vault-password"',
        )
        for line in keepers:
            for label, pattern in sorted(RETIRED_IDENTIFIERS.items()):
                with self.subTest(line=line, identifier=label):
                    self.assertIsNone(
                        pattern.search(line),
                        f"the retired-identifier pattern {label!r} matches a keeper: "
                        f"{line!r}",
                    )

    def test_the_retired_identifier_patterns_match_what_they_name(self) -> None:
        """The complement of the test above: a pattern narrowed until it
        matched no keeper could also match nothing at all."""
        offending = {
            "environments_root": 'environments_root="terraform/env"',
            "matrix.environment": "name: plan (${{ matrix.environment.name }})",
            "inputs.environment": "REQUESTED: ${{ inputs.environment }}",
            "ENVIRONMENTS": "          ENVIRONMENTS: ${{ steps.discover.outputs.x }}",
            "ENVIRONMENT_NAME": 'echo "$ENVIRONMENT_NAME"',
            "REQUESTED_ENVIRONMENT": 'requested="${REQUESTED_ENVIRONMENT:-}"',
            "outputs.environments": "${{ needs.discover.outputs.environments }}",
        }
        self.assertEqual(
            sorted(RETIRED_IDENTIFIERS),
            sorted(offending),
            "every retired identifier needs a line here that it must match; this "
            "table and the pattern table have drifted apart",
        )
        for label, line in sorted(offending.items()):
            with self.subTest(identifier=label):
                self.assertIsNotNone(
                    RETIRED_IDENTIFIERS[label].search(line),
                    f"the retired-identifier pattern {label!r} matches nothing, not "
                    f"even {line!r}",
                )

    def test_the_interpolation_normaliser_brings_the_two_mechanisms_together(self) -> None:
        """The heading/locator comparison compares a shell body with an Actions
        expression. If the normaliser collapsed only one of the two forms, the
        comparison would fail for a workflow that is correct."""
        self.assertEqual(
            normalised_interpolation(
                "### Terraform Plan — `terraform/stacks/${STACK_NAME}`"
            ),
            normalised_interpolation(
                "### Terraform Plan — `terraform/stacks/${{ matrix.stack.name }}`"
            ),
            "the two interpolation forms do not normalise to one another, so the "
            "heading and its locator can never be compared",
        )
        self.assertNotEqual(
            normalised_interpolation("`terraform/stacks/${STACK_NAME}`"),
            normalised_interpolation("`terraform/environs/${STACK_NAME}`"),
            "the normaliser collapsed the literal half too, so it would report two "
            "disagreeing headings as agreeing",
        )

# --------------------------------------------------------------------------
# iac-cicd-pipeline / Host Configuration Is Applied by a Gated Workflow
# (MODIFIED) -- the converge row, and the dispatch input that narrows it
#
# This requirement reached the delta LATE, after the rest of this module was
# written: the change that originally ADDED it archived while this branch sat
# unrebased, so it is now live in `openspec/specs/iac-cicd-pipeline/spec.md` in
# the old `environment` vocabulary. That change's design.md decision 4 records
# the history.
#
# Its delta is vocabulary-only. Every SHALL and every one of its eleven
# scenarios says what it said before with `stack` where it said `environment`,
# so the BEHAVIOUR it states is already asserted, in full, by
# `test_host_converge_workflow.py` -- whose locators are written by SHAPE (the
# job that invokes `ansible-playbook`, the step that writes to
# `$GITHUB_STEP_SUMMARY`) and therefore survive a rename untouched.
#
# What is asserted below is only what the rename can break and those shape
# locators cannot see: WHICH MATRIX KEY the gate, the credential and the
# serialisation are reached THROUGH, and whether the dispatch input still
# reaches the body that validates it. The sweep in
# `TestTheMatrixAndItsOutputsNameTheStack` forbids `matrix.environment`
# anywhere in this file and requires `matrix.stack` SOMEWHERE in it; neither
# says the converge job's own gate, credential and concurrency group are the
# surfaces that carry it, and a rename that moved one of the three onto a
# different field of the row satisfies both while gating, crediting or
# serialising the wrong thing.
# --------------------------------------------------------------------------

ANSIBLE_PLAYBOOK = re.compile(r"\bansible-playbook\b")
SECRETS_LOOKUP = re.compile(r"\bsecrets\[")
GITHUB_ENVIRONMENT_THROUGH_THE_STACK = re.compile(
    r"\bmatrix\.stack\.github_environment\b"
)
READ_ONLY_SECRET_THROUGH_THE_STACK = re.compile(r"\bmatrix\.stack\.read_only_secret\b")

# The dispatch input as a step's `env:` block reads it, in both spellings
# Actions accepts. `inputs.environment` is already forbidden file-wide by
# `RETIRED_IDENTIFIERS`; the retired form is re-stated here in its
# `github.event.inputs` spelling too, and scoped to `env:` values, because it
# is the CONVERSE the carrier read below needs -- a read that found nothing
# would satisfy the presence assertion by reporting an empty mapping.
DISPATCH_INPUT_READ = re.compile(r"(?:inputs|event\.inputs)\.stack\b")
RETIRED_DISPATCH_INPUT_READ = re.compile(r"(?:inputs|event\.inputs)\.environment\b")


def converge_jobs(workflow: dict) -> list:
    """Every job that runs the converge play, located BY SHAPE.

    The same locator `test_host_converge_workflow.WorkflowLocatorMixin` uses:
    the job invoking `ansible-playbook`. Keyed on what the job does rather than
    on its key, because this change renames neither the job key nor the step
    names and a locator keyed on one would be repaired by editing a test.

    Comments are stripped first, so a job whose only mention of the play is a
    comment is not mistaken for the one that runs it.
    """
    return [
        (name, job)
        for name, job in jobs(workflow).items()
        if any(
            ANSIBLE_PLAYBOOK.search(uncommented(str(step.get("run") or "")))
            for step in (job.get("steps") or [])
        )
    ]


def env_assignments(workflow: dict):
    """Yield (job_name, label, key, value) for every `env:` entry a workflow
    declares, at job level and at step level, with the value compacted."""
    for job_name, job in jobs(workflow).items():
        block = job.get("env")
        if isinstance(block, dict):
            for key, value in block.items():
                yield job_name, f"{job_name}.env", str(key), compact(value)
    for job_name, index, step in steps(workflow):
        block = step.get("env")
        if isinstance(block, dict):
            for key, value in block.items():
                yield job_name, step_label(job_name, index, step), str(key), compact(value)


def dispatch_input_carriers(workflow: dict, pattern=DISPATCH_INPUT_READ) -> dict:
    """The `env:` keys under which the dispatch input reaches a step body, as
    key -> the places that map it."""
    found: dict = {}
    for _, label, key, value in env_assignments(workflow):
        if pattern.search(value):
            found.setdefault(key, []).append(label)
    return found


def host_converge_discovery_bodies(path: Path | None = None) -> list[str]:
    """host-converge.yml's discovery body, located by the inventory root it
    enumerates -- the locator
    `TestDiscoveryIteratesTheStackRoot
    .test_the_host_converge_discovery_reads_each_stacks_own_declaration`
    already uses.

    Written as a second copy rather than by refactoring that test to call this:
    this pass is additive only. That test is currently red, and lifting its
    locator out of it would change what a red test asserts at a moment when
    nothing could show that the change was faithful.
    """
    return [
        body
        for _, body in run_bodies(path or HOST_CONVERGE)
        if "ansible/inventory" in body
        and "GITHUB_OUTPUT" in body
        and not ACTIONS_EXPRESSION.search(body)
    ]


class TestTheConvergeRowIsReachedThroughTheStack(unittest.TestCase):
    """MODIFIED requirement: Host Configuration Is Applied by a Gated Workflow
    (iac-cicd-pipeline).

    Three surfaces of one matrix row: the GitHub Environment that gates the
    converge, the repository secret it runs under, and the group that
    serialises it. Each is SPECIFIED by the requirement as a property of the
    stack; DERIVED, per that change's design.md decision 2, is only that the
    row is reached through `matrix.stack`.
    """

    def _converge_job(self, workflow: dict):
        found = converge_jobs(workflow)
        self.assertEqual(
            1,
            len(found),
            "expected exactly one job in host-converge.yml invoking "
            f"`ansible-playbook` -- the converge -- and found {len(found)}: "
            f"{sorted(name for name, _ in found)}. A second such job would hold the "
            "credentials the gate exists to withhold in more than one place",
        )
        return found[0]

    def test_the_converge_job_is_gated_on_the_github_environment_its_stack_declares(
        self,
    ) -> None:
        """SPECIFIED -- scenario "The converge job is gated on the environment's
        own GitHub Environment": "it SHALL declare the GitHub Environment named
        by that stack's own pipeline declaration, so that its protection rules
        and its secrets are the ones that apply", and the requirement's "A
        converge job **per stack** SHALL declare that stack's own GitHub
        Environment, taken from that stack's committed pipeline declaration".

        DERIVED for the matrix key -- design.md decision 2.

        `TestTheEnvironmentAxisIsNotRenamedWithTheUnit
        .test_every_gated_job_still_attaches_to_the_github_environment_its_stack_declares`
        holds the same shape for `apply.yml`, and says in its own docstring that
        apply.yml is its subject. This is the host-converge half: the converge
        job is gated by a GitHub Environment exactly as an apply job is, and the
        two live in different files.
        """
        workflow = load_yaml(HOST_CONVERGE)
        name, job = self._converge_job(workflow)
        declared = compact(job.get("environment", ""))
        self.assertTrue(
            declared,
            f"host-converge.yml's `{name}` runs the converge play and declares no "
            "`environment:`, so the credentials a converge needs are "
            "repository-scoped and no protection rule applies to a production "
            "converge",
        )
        self.assertIsNotNone(
            GITHUB_ENVIRONMENT_THROUGH_THE_STACK.search(declared),
            f"host-converge.yml's `{name}` declares `environment: {declared}`, which "
            "does not read `matrix.stack.github_environment`. The Environment SHALL "
            "be the one that stack's own declaration names, reached through the "
            "matrix row this change renames -- a row read through any other field "
            "gates the converge on something the declaration did not say",
        )

    def test_the_converge_job_exports_the_read_only_secret_its_stack_declares(
        self,
    ) -> None:
        """SPECIFIED -- "which repository secret holds each one's read-only
        credential SHALL come from discovery over committed files", and the
        converge job "SHALL be the only job holding the credentials a converge
        needs". DERIVED for the matrix key -- design.md decision 2.

        `test_host_converge_workflow.TestTheConvergeJobIsGatedOnItsOwnGitHubEnvironment
        .test_no_step_maps_an_environment_to_its_secret` holds the other half
        and survives this rename untouched: it forbids a LITERAL secret name.
        A lookup reading the wrong field of the right row -- `secrets[matrix
        .stack.name]` -- names no literal and passes it.
        """
        workflow = load_yaml(HOST_CONVERGE)
        name, _ = self._converge_job(workflow)
        lookups = [
            (label, key, value)
            for job_name, label, key, value in env_assignments(workflow)
            if job_name == name and SECRETS_LOOKUP.search(value)
        ]
        self.assertTrue(
            lookups,
            f"host-converge.yml's `{name}` resolves no `secrets[...]` lookup in any "
            "`env:` block, so either the converge holds no read-only credential or "
            "it reads one by a name written in workflow text",
        )
        through = [
            entry for entry in lookups if READ_ONLY_SECRET_THROUGH_THE_STACK.search(entry[2])
        ]
        self.assertTrue(
            through,
            f"none of `{name}`'s secret lookups reads "
            "`matrix.stack.read_only_secret`: "
            f"{[(label, key) for label, key, _ in lookups]}. A lookup keyed on any "
            "other field of the row resolves to the empty string rather than "
            "failing, so the converge authenticates as nobody and reports that as an "
            "inventory it could not parse",
        )

    def test_the_converge_jobs_serialisation_group_is_per_stack(self) -> None:
        """SPECIFIED -- "A converge SHALL NOT be cancelled in favour of a later
        one. Runs against one stack SHALL be serialised", and scenario "One
        environment's failure does not silence another's". DERIVED for the
        matrix key -- design.md decision 2.

        `test_host_converge_workflow.TestOneEnvironmentsConvergeDoesNotSilenceAnother
        .test_an_in_flight_converge_is_not_cancelled_by_a_later_one` asserts
        `cancel-in-progress: false` and that the group carries SOME expression,
        and survives this rename. What it cannot see is a group that carries an
        expression of something other than the row -- one group for every stack,
        under which one stack's converge queues behind another's for no reason.
        The rename rewrites this line, which is what makes that reachable here.
        """
        workflow = load_yaml(HOST_CONVERGE)
        name, job = self._converge_job(workflow)
        concurrency = job.get("concurrency") or workflow.get("concurrency")
        self.assertTrue(
            concurrency,
            f"neither host-converge.yml's `{name}` nor the workflow declares a "
            "`concurrency:` group, so two merges in quick succession run two plays "
            "against one host at once",
        )
        group = compact(
            concurrency.get("group") if isinstance(concurrency, dict) else concurrency
        )
        self.assertIsNotNone(
            REPLACEMENT_IDENTIFIERS["matrix.stack"].search(group),
            f"host-converge.yml's `{name}` serialises on the group {group!r}, which "
            "does not read `matrix.stack`. Serialisation is per stack: a group that "
            "does not name the row is one queue for every host, and one that still "
            "names `matrix.environment` is a rename that stopped halfway",
        )


class TestTheDispatchInputStillReachesTheBodyThatValidatesIt(unittest.TestCase):
    """MODIFIED requirement: Host Configuration Is Applied by a Gated Workflow
    (iac-cicd-pipeline) -- scenario "A run is requested for an environment that
    does not exist".

    `TestTheMatrixAndItsOutputsNameTheStack
    .test_the_host_converge_dispatch_input_names_the_stack` renames the input
    an operator types. This is the other end of the same wire: the value has to
    arrive inside the discovery body, which is where the refusal that names the
    stacks that WERE found is written. A rename that moved the input and not
    the `env:` entry carrying it leaves the body reading an unset variable --
    which it is specified to treat as "converge everything", because that is
    what every `push` supplies. So a by-hand converge of one host would
    silently converge all of them, and nothing would be red.
    """

    def test_the_dispatch_input_is_mapped_into_the_body_under_a_name_that_body_reads(
        self,
    ) -> None:
        """SPECIFIED for the refusal the mapping feeds -- "the run SHALL fail
        naming the stacks that were found, rather than converging none and
        reporting success". DERIVED for the mechanism -- that change's
        tasks.md 3.4, and this suite's own way of executing the body: the
        variable is resolved from the step's `env:` block, which is what
        `test_host_converge_workflow.TestHostConvergeDiscoveryFailsClosed
        ._input_variable` does to run it at all.
        """
        workflow = load_yaml(HOST_CONVERGE)
        retired = dispatch_input_carriers(workflow, RETIRED_DISPATCH_INPUT_READ)
        self.assertEqual(
            {},
            retired,
            "these `env:` entries in host-converge.yml still read the retired "
            f"dispatch input: {retired}. The input an operator types is now `stack`, "
            "and an unrecognised input resolves to the empty string rather than "
            "failing",
        )
        carriers = dispatch_input_carriers(workflow)
        self.assertTrue(
            carriers,
            "no `env:` entry in host-converge.yml reads the `stack` dispatch input, "
            "so a run requested by hand naming one stack reaches the body that would "
            "have to validate it through nothing -- and an absent value means "
            "'converge every stack discovered', which is what a merge supplies",
        )
        bodies = host_converge_discovery_bodies()
        self.assertEqual(
            1,
            len(bodies),
            "expected exactly one `run:` step in host-converge.yml that enumerates "
            f"the inventory root and writes to `$GITHUB_OUTPUT`, found {len(bodies)}",
        )
        unread = sorted(key for key in carriers if key not in bodies[0])
        self.assertEqual(
            [],
            unread,
            f"host-converge.yml maps the dispatch input into {unread}, which the "
            "discovery body never reads. The value is carried to the step and "
            "dropped there, so a dispatch naming one stack converges every stack and "
            "the run is green",
        )


class TestTheseHostConvergeReadsDiscriminate(unittest.TestCase):
    """DERIVED. Nothing here asserts anything about this change.

    The four tests above are a static read of one committed file, so a green
    result reports only that the file could be read. These establish that the
    reads report what they claim to, by running them over material this test
    supplies. Same idiom as `TestTheseReadsDiscriminate` above.
    """

    @staticmethod
    def _workflow(jobs_block: dict) -> dict:
        return {"name": "fixture", "jobs": jobs_block}

    def test_the_converge_locator_finds_the_job_that_runs_the_play(self) -> None:
        workflow = self._workflow(
            {
                "publish": {"steps": [{"name": "Diff", "run": "git diff"}]},
                "converge": {
                    "steps": [
                        {"name": "Checkout", "uses": "actions/checkout@v4"},
                        {"name": "Converge", "run": "ansible-playbook playbooks/x.yml"},
                    ]
                },
            }
        )
        self.assertEqual(
            ["converge"],
            [name for name, _ in converge_jobs(workflow)],
            "the converge locator did not pick out the job that runs the play",
        )

    def test_the_converge_locator_is_not_fooled_by_a_comment(self) -> None:
        workflow = self._workflow(
            {
                "publish": {
                    "steps": [{"name": "Diff", "run": "# not ansible-playbook\ngit diff"}]
                }
            }
        )
        self.assertEqual(
            [],
            converge_jobs(workflow),
            "a job whose only mention of the play is a comment was read as the job "
            "that runs it, so the gate, the credential and the group would be "
            "asserted of the wrong job",
        )

    def test_the_gate_read_tells_the_row_from_its_fields(self) -> None:
        self.assertIsNotNone(
            GITHUB_ENVIRONMENT_THROUGH_THE_STACK.search(
                compact("${{ matrix.stack.github_environment }}")
            ),
            "the gate read does not match the expression it exists to require",
        )
        for wrong in (
            "${{ matrix.environment.github_environment }}",
            "${{ matrix.stack.name }}",
            "${{ needs.discover.outputs.github_environment }}",
        ):
            with self.subTest(expression=wrong):
                self.assertIsNone(
                    GITHUB_ENVIRONMENT_THROUGH_THE_STACK.search(compact(wrong)),
                    f"the gate read accepted {wrong!r}, which reaches a GitHub "
                    "Environment through something other than the stack's own row",
                )

    def test_the_secret_read_tells_the_row_from_its_fields(self) -> None:
        self.assertIsNotNone(
            READ_ONLY_SECRET_THROUGH_THE_STACK.search(
                compact("${{ secrets[matrix.stack.read_only_secret] }}")
            ),
            "the credential read does not match the expression it exists to require",
        )
        self.assertIsNone(
            READ_ONLY_SECRET_THROUGH_THE_STACK.search(
                compact("${{ secrets[matrix.stack.name] }}")
            ),
            "the credential read accepted a lookup keyed on the stack's NAME, which "
            "resolves to the empty string rather than failing",
        )

    def test_the_dispatch_carrier_read_reports_what_it_is_given(self) -> None:
        mapped = self._workflow(
            {
                "discover": {
                    "steps": [
                        {
                            "name": "Discover",
                            "run": "echo x",
                            "env": {"REQUESTED_STACK": "${{ inputs.stack }}"},
                        }
                    ]
                }
            }
        )
        self.assertEqual(
            ["REQUESTED_STACK"],
            sorted(dispatch_input_carriers(mapped)),
            "the carrier read did not report an `env:` entry that maps the dispatch "
            "input",
        )
        unmapped = self._workflow(
            {"discover": {"steps": [{"name": "Discover", "run": "echo x"}]}}
        )
        self.assertEqual(
            {},
            dispatch_input_carriers(unmapped),
            "the carrier read reported a mapping in a workflow that declares none, "
            "so the presence assertion above could never be red",
        )

    def test_the_dispatch_carrier_read_still_sees_the_retired_spelling(self) -> None:
        workflow = self._workflow(
            {
                "discover": {
                    "env": {"REQUESTED_ENVIRONMENT": "${{ github.event.inputs.environment }}"},
                    "steps": [{"name": "Discover", "run": "echo x"}],
                }
            }
        )
        self.assertEqual(
            ["REQUESTED_ENVIRONMENT"],
            sorted(dispatch_input_carriers(workflow, RETIRED_DISPATCH_INPUT_READ)),
            "the retired-spelling read missed the `github.event.inputs` form, under "
            "which a mapping left at the old input name would go unreported",
        )
        self.assertEqual(
            {},
            dispatch_input_carriers(workflow),
            "the new-spelling read matched the retired input, so the absence "
            "assertion and the presence assertion could be satisfied by one mapping",
        )


class TestTheHeadingReadDiscriminates(unittest.TestCase):
    """DERIVED. Nothing here asserts anything about this change.

    `shell_double_quoted_value` was added to repair
    `TestThePathRuleAndItsConsumersFollowTheStackRoot
    .test_the_plan_comment_heading_and_the_comment_locator_agree_on_the_stack_root`,
    which harvested the heading without unescaping and so compared a
    backslash-bearing string against a bare one -- reporting a disagreement
    where the two surfaces agreed.

    A repair to a read is exactly the edit that can quietly turn a check into
    one that cannot fail, so these run the repaired read over material this
    test supplies: it must still tell two headings that name DIFFERENT paths
    apart, which is the whole of what that check exists for.
    """

    HEADING = 'heading="### Terraform Plan — \\`terraform/stacks/${STACK_NAME}\\`"'
    LOCATOR = "### Terraform Plan — `terraform/stacks/${{ matrix.stack.name }}`"

    def test_the_read_unescapes_what_the_shell_would(self) -> None:
        self.assertEqual(
            "### Terraform Plan — `terraform/stacks/${STACK_NAME}`",
            shell_double_quoted_value(self.HEADING),
            "the read did not return the heading the shell will emit, so it "
            "compares a backslash-bearing string against a bare one",
        )

    def test_a_backslash_that_is_not_an_escape_survives(self) -> None:
        self.assertEqual(
            r"a\b`c",
            shell_double_quoted_value(r'heading="a\b\`c"'),
            "the read stripped a backslash the shell keeps, so it would report "
            "two headings as agreeing on a literal neither of them carries",
        )

    def test_only_a_matched_pair_of_quotes_is_removed(self) -> None:
        self.assertEqual(
            'ends in a quote"',
            shell_double_quoted_value('heading="ends in a quote\\""'),
        )
        self.assertEqual(
            "unquoted",
            shell_double_quoted_value("heading=unquoted"),
        )

    def test_the_repaired_read_still_separates_two_paths(self) -> None:
        """The load-bearing one. A repair that made the comparison pass on
        agreement AND on disagreement would have satisfied the failing test
        while destroying it."""
        agreeing = normalised_interpolation(shell_double_quoted_value(self.HEADING))
        self.assertIn(
            normalised_interpolation(self.LOCATOR),
            agreeing,
            "the repaired read does not bring the heading and the locator "
            "together on a pair that genuinely agree, so the check it repairs "
            "would still be red against a correct workflow",
        )
        mismatched = normalised_interpolation(
            shell_double_quoted_value(
                self.HEADING.replace("terraform/stacks", "terraform/" + "environments")
            )
        )
        self.assertNotIn(
            normalised_interpolation(self.LOCATOR),
            mismatched,
            "the repaired read brings a heading and a locator naming DIFFERENT "
            "roots together, so the check could no longer catch the state it "
            "exists for: a heading the locator never finds, and a second "
            "comment posted on every run",
        )


class TestNoKeeperWasSweptInsideTheStackDirectories(unittest.TestCase):
    """MODIFIED requirements: every requirement this change touches whose
    subject lives under the stack root -- but the class is DERIVED throughout,
    and says so. No scenario states what a comment inside a stack directory may
    say.

    What it is for is the half of the sweep that review caught and the suite
    could not: `TestTheEnvironmentAxisIsNotRenamedWithTheUnit` guards the four
    keepers in the four WORKFLOW files, through `uncommented()`. Four
    mis-renames landed in comments under `terraform/stacks/`, where no
    assertion looked in either direction.
    """

    def _files(self) -> list[Path]:
        files = stack_root_files()
        self.assertTrue(
            files,
            "no file was found under the stack root, so every assertion in this "
            "class would pass having read nothing",
        )
        return files

    def test_the_stack_root_carries_files_to_read(self) -> None:
        """The converse the three checks below need. At two stacks this is not
        decoration: a census that returned nothing would satisfy all of them."""
        by_stack: dict = {}
        for path in self._files():
            by_stack.setdefault(path.parent.name, []).append(path.name)
        self.assertTrue(
            all(names for names in by_stack.values()),
            f"a stack directory holds no readable file: {by_stack}",
        )
        self.assertEqual(
            sorted(directory.name for directory in stack_directories()),
            sorted(by_stack),
            f"the files read do not cover every stack directory: read {sorted(by_stack)}, "
            f"stacks {sorted(d.name for d in stack_directories())}",
        )

    def test_no_file_under_the_stack_root_renames_a_keeper(self) -> None:
        """DERIVED -- design.md decision 2's four keepers, plus the OS process
        environment and a pre-commit hook's environment, which code review
        established as two further senses of the same word.

        Read as PROSE rather than through `uncommented()` or a parser: all four
        real defects were in comments, which is the blind spot this closes.
        """
        for path in self._files():
            stream = committed_prose(path.read_text(encoding="utf-8", errors="replace"))
            for sense, pattern in sorted(OVERSWEPT_KEEPERS.items()):
                match = pattern.search(stream)
                with self.subTest(file=path.name, stack=path.parent.name, sense=sense):
                    self.assertIsNone(
                        match,
                        f"{path.parent.name}/{path.name} names {sense} as a stack: "
                        f"{stream[max(0, (match.start() if match else 0) - 60):][:150]!r}. "
                        "The sweep renames the unit the pipeline iterates and nothing "
                        "else; this sense is a keeper, and a comment explaining a "
                        "mechanism in a word that mechanism does not use is the same "
                        "defect as the identifier one layer out",
                    )

    def test_no_file_under_the_stack_root_left_an_article_behind(self) -> None:
        """DERIVED. A word-level substitution strands the article in front of
        the word it replaced, and the sentence reads as a typo rather than as a
        rename that went wrong -- which is why this recurred after being fixed
        once in `host-converge.yml`."""
        for path in self._files():
            stream = committed_prose(path.read_text(encoding="utf-8", errors="replace"))
            match = STRANDED_ARTICLE.search(stream)
            with self.subTest(file=path.name, stack=path.parent.name):
                self.assertIsNone(
                    match,
                    f"{path.parent.name}/{path.name} reads "
                    f"{stream[max(0, (match.start() if match else 0) - 60):][:140]!r}, "
                    "where a substitution left the article of the word it replaced",
                )

    def test_no_file_under_the_stack_root_carries_a_retired_identifier(self) -> None:
        """DERIVED -- the UNDER-sweep direction, widened from the four workflow
        files to these sixteen. `TestTheMatrixAndItsOutputsNameTheStack` reads
        the workflows only, so a retired identifier quoted in a comment here
        was asserted by nothing."""
        for path in self._files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for label, pattern in sorted(RETIRED_IDENTIFIERS.items()):
                with self.subTest(file=path.name, stack=path.parent.name, identifier=label):
                    self.assertIsNone(
                        pattern.search(text),
                        f"{path.parent.name}/{path.name} still carries the retired "
                        f"identifier {label!r}",
                    )

    def test_the_repository_wide_old_root_sweep_reaches_the_stack_directories(self) -> None:
        """DERIVED. The other half of the under-sweep answer, and it is a
        question worth asking rather than assuming: the widened old-root sweep
        covers these files only if its own file set contains them, and this is
        what makes that statement checkable rather than a claim in a docstring.
        It goes red if a later rule quietly removes them from that sweep's
        reach.

        It asserts against the set `old_root_occurrences()` ACTUALLY reads,
        which is the tracked files rather than a filesystem walk -- see that
        function. Asserting against the walker instead would have kept passing
        while the sweep read something else, which is the shape of check this
        module exists to avoid.
        """
        reached = set(tracked_files())
        missing = sorted(
            name
            for name in (path.relative_to(ROOT).as_posix() for path in self._files())
            if name not in reached
        )
        self.assertEqual(
            [],
            missing,
            "the repository-wide old-root sweep does not reach these files under the "
            f"stack root, so nothing checks them for a stale path: {missing}",
        )


class TestTheStackDirectoryReadsDiscriminate(unittest.TestCase):
    """DERIVED. Nothing here asserts anything about this change.

    The checks above are a static read of a clean tree, so a green result
    reports only that the files could be read. The material below is the REAL
    committed text of the four defects, quoted from `93bef69^`, and the real
    corrected text from `93bef69` -- not a reconstruction, because a
    reconstruction would establish that the needles match what this test
    imagines the defects looked like.
    """

    # Verbatim from `93bef69^`. Each is followed by the corrected line from
    # `93bef69`, so every needle is exercised in both directions on the same
    # sentence -- which is what tells a needle that discriminates from one that
    # matches the surrounding prose.
    DEFECTS = {
        "the GitHub Environment": (
            "  #   - the gated apply job, which declares `stack: production`,\n"
            "  #     resolves that Environment's Read & Write token;",
            "  #   - the gated apply job, which declares `environment: production`,\n"
            "  #     resolves that Environment's Read & Write token;",
        ),
        "the OS process environment": (
            "  # HCLOUD_TOKEN is read from the stack, and WHICH token that is\n"
            "  # depends on the job:",
            "  # HCLOUD_TOKEN is read from the environment, and WHICH token that is\n"
            "  # depends on the job:",
        ),
        "the Terraform variable and its value": (
            "# (only the firewall carries the \"<stack>-\" prefix), and the hcloud\n"
            "# inventory plugin takes each host's `inventory_hostname` from the server name.",
            "# (only the firewall carries the \"<environment>-\" prefix), and the hcloud\n"
            "# inventory plugin takes each host's `inventory_hostname` from the server name.",
        ),
    }

    # The fourth defect, which is not a keeper sense but a stranded article --
    # and the one no line-wise read could have caught, because the article and
    # its noun sit on either side of a comment marker.
    STRANDED = (
        "# same GitHub Environment share its WRITE token and its protection rules, so an\n"
        "# stack meant to be ungated would hold this one's write credential.",
        "# same GitHub Environment share its WRITE token and its protection rules, so a\n"
        "# stack meant to be ungated would hold this one's write credential.",
    )

    def test_the_prose_stream_joins_a_sentence_split_across_comment_lines(self) -> None:
        self.assertIn(
            "so an stack meant to be ungated",
            committed_prose(self.STRANDED[0]),
            "the prose stream did not bring an article and its noun back together "
            "across the comment marker between them, so the defect it exists for "
            "would be invisible to it",
        )

    def test_each_keeper_needle_reports_the_defect_it_was_written_for(self) -> None:
        """The load-bearing direction. A needle that matched nothing would let
        all four defects through exactly as the suite did."""
        for sense, (defective, _) in self.DEFECTS.items():
            with self.subTest(sense=sense):
                self.assertIsNotNone(
                    OVERSWEPT_KEEPERS[sense].search(committed_prose(defective)),
                    f"the needle for {sense} does not report the real committed "
                    f"defect it was written for: {defective!r}",
                )
        self.assertIsNotNone(
            STRANDED_ARTICLE.search(committed_prose(self.STRANDED[0])),
            "the stranded-article needle does not report the real committed defect",
        )

    def test_no_needle_fires_on_the_corrected_text(self) -> None:
        """The other direction, and the one that stops the class being
        satisfiable only by reverting the fix: the corrected sentences say the
        SAME things about the same mechanisms, and none of them is an
        offence."""
        for sense, (_, corrected) in self.DEFECTS.items():
            stream = committed_prose(corrected)
            for other, pattern in sorted(OVERSWEPT_KEEPERS.items()):
                with self.subTest(sense=sense, needle=other):
                    self.assertIsNone(
                        pattern.search(stream),
                        f"the needle for {other} fires on text that is CORRECT: "
                        f"{corrected!r}",
                    )
        self.assertIsNone(
            STRANDED_ARTICLE.search(committed_prose(self.STRANDED[1])),
            "the stranded-article needle fires on the corrected sentence",
        )

    def test_no_needle_fires_on_the_keeper_senses_written_correctly(self) -> None:
        """Broader than the pair above: every keeper sense, spelled the way
        this repository spells it. A needle keyed on the word `stack` rather
        than on the sense would light these up, and the only route to green
        would be the over-sweep the class exists against."""
        kept = (
            "the gated apply job declares `environment: production`",
            "github_environment: production",
            'name = "${var.environment}-${var.name}"',
            'environment = "prod"',
            "HCLOUD_TOKEN is read from the environment",
            "TARGET_ENVIRONMENT is exported into the process environment",
            "the inventory source is ansible/inventory/prod.hcloud.yml",
            "a pre-commit hook environment is built against a specific interpreter",
            "every stack declares its own pipeline configuration",
            "the stack's own GitHub Environment gates its apply",
        )
        stream = committed_prose("\n".join(f"# {line}" for line in kept))
        for sense, pattern in sorted(OVERSWEPT_KEEPERS.items()):
            with self.subTest(sense=sense):
                self.assertIsNone(
                    pattern.search(stream),
                    f"the needle for {sense} fires on a keeper written correctly",
                )
        self.assertIsNone(STRANDED_ARTICLE.search(stream))

    # Each widened spelling, paired with the sense whose needle must report it.
    # Every string here is the spelling its own defect ACTUALLY USED -- the
    # backticked label, the literal step name, the literal sentence -- rather
    # than a paraphrase. A needle that would not have caught the instance it is
    # named for is the thing these exist to prevent.
    WIDENED_SPELLINGS = (
        # The GitHub Environment in prose, which is the form the first workflow
        # sweep got wrong and which both `pipeline.yml` files are dense in.
        ("the GitHub Environment", "The GitHub Stack this stack's apply job attaches to"),
        ("the GitHub Environment", "a property of the Stack's protection rules"),
        ("the GitHub Environment", "a Stack-scoped secret ahead of a repository-scoped one"),
        (
            "the GitHub Environment",
            "two stacks naming the same GitHub Stack share its WRITE token",
        ),
        # RETIRED by the change rename-the-stacks-and-their-resources, and
        # retired rather than repaired because the string stopped being a
        # defect. It was `see "Each Stack Declares Its Own Pipeline
        # Configuration"` -- a citation of a requirement title that did not
        # exist when this fixture was written, which is what made it an
        # over-sweep. That change renames the requirement to exactly that title,
        # so both `pipeline.yml` files now carry the string as the CORRECT
        # citation. Keeping the fixture would oblige the needle to redden on the
        # right answer. The `Stack's` and `Stack-scoped` entries above cover the
        # common-noun misuse this sense is actually for, which is what the
        # retired entry was standing in for and not an instance of.
        # The label, backticked -- literally how round one's runbook defect was
        # written.
        ("the Terraform variable and its value", "the `stack` label names the axis"),
        ("the Terraform variable and its value", "hcloud_labels.stack is read by"),
        # The process environment, past the end of any closed verb list.
        ("the OS process environment", "HCLOUD_TOKEN is taken from the stack"),
        ("the OS process environment", "written into the job's stack file"),
        # A pre-commit hook's environment -- literally round one's step name.
        ("a pre-commit hook's environment", "- name: Cache pre-commit stacks"),
    )

    # Verbatim from the two `pipeline.yml` files and the two `versions.tf`
    # files as they stand at HEAD: every line under this root that names a
    # GitHub Environment in prose. The widened needles MUST stay silent on all
    # of them, and this is a stronger silence fixture than an invented one --
    # it is the exact text the live tree carries, eight occurrences of it in
    # prod's declaration alone.
    REAL_KEEPER_PROSE = (
        "# The GitHub Environment this stack's apply job attaches to. REQUIRED.",
        "# Whether that pauses for a human is a property of the Environment's protection",
        "# same GitHub Environment share its WRITE token and its protection rules, so a",
        "# Privilege obliges EVERY stack's GitHub Environment to define",
        "# an Environment-scoped secret ahead of a repository-scoped one of the same",
        "# Environment also defines. `.github/tests` asserts that for `HCLOUD_TOKEN`",
        "# `PRODUCTION` rather than `PROD`, matching the GitHub Environment this",
        '# discovery step -- see "Each Stack Declares Its Own Pipeline',
        "#     Environment's Read & Write token. That Environment requires no",
        "#     nothing in prod's (see the Each Stack Has a Dedicated Hetzner",
        "# of the Environment's protection rules -- repository settings, which no file",
        "# The apply job still declares this Environment, so the write token stays",
        "#   - the gated apply job, which declares `environment: production`,",
        "  # HCLOUD_TOKEN is read from the environment, and WHICH token that is",
    )

    def test_each_widened_needle_reports_the_spelling_it_is_named_for(self) -> None:
        """The gap round three found: keeper 1 had a needle for the job key and
        none for its prose form, which is the form the first workflow sweep
        actually got wrong. Three narrower misses came with it -- a backticked
        `stack` label, a `Cache pre-commit stacks` step name, and a process
        environment reached by a verb no closed list carried."""
        for sense, spelling in self.WIDENED_SPELLINGS:
            with self.subTest(sense=sense, spelling=spelling):
                self.assertIsNotNone(
                    OVERSWEPT_KEEPERS[sense].search(committed_prose(spelling)),
                    f"the needle for {sense} does not report {spelling!r}, which is "
                    "the spelling that sense's own defect used",
                )

    def test_the_widened_needles_stay_silent_on_the_real_keeper_prose(self) -> None:
        """The constraint the widening must not cost: keyed on the sense, never
        on the word. The material is every line under this root that names a
        GitHub Environment in prose, quoted verbatim from the live files -- so
        a needle that fired on capitalisation rather than on the over-sweep
        would light up the densest correct prose in the repository."""
        for line in self.REAL_KEEPER_PROSE:
            stream = committed_prose(line)
            for sense, pattern in sorted(OVERSWEPT_KEEPERS.items()):
                with self.subTest(sense=sense, line=line):
                    self.assertIsNone(
                        pattern.search(stream),
                        f"the needle for {sense} fires on prose the live tree "
                        f"carries and that is CORRECT: {line!r}",
                    )
            self.assertIsNone(
                STRANDED_ARTICLE.search(stream),
                f"the stranded-article needle fires on correct prose: {line!r}",
            )

    def test_a_legitimate_reference_to_a_stack_directory_is_not_an_offence(self) -> None:
        """The process-environment needle is keyed on a preposition and a noun
        rather than on a verb list, which is wide enough to reach the one
        innocent thing "from the stack" can mean here."""
        for innocent in (
            "the lockfile in the stack directory is committed",
            "read from the stack root rather than enumerated",
            "the module source is relative to the stack directory",
            "taken from the stack's own pipeline declaration",
            "which stacks exist comes from the stack names discovery finds",
        ):
            with self.subTest(text=innocent):
                self.assertIsNone(
                    OVERSWEPT_KEEPERS["the OS process environment"].search(
                        committed_prose(innocent)
                    ),
                    f"the process-environment needle fires on {innocent!r}, which "
                    "names a directory rather than the environment a process reads",
                )

    def test_the_stranded_article_needle_reads_both_cases(self) -> None:
        """`a Environment` opening a sentence is the same defect as
        `a environment` inside one, and a lowercase-only needle would have let
        the sentence-initial form through."""
        for stranded in (
            "so an stack meant to be ungated",
            "so an Stack meant to be ungated",
            "A environment declaring nothing is gated",
            "a environment declaring nothing is gated",
        ):
            with self.subTest(text=stranded):
                self.assertIsNotNone(
                    STRANDED_ARTICLE.search(committed_prose(stranded)),
                    f"the stranded-article needle misses {stranded!r}",
                )
        for fine in (
            "an environment declaring nothing is gated",
            "a stack declaring nothing is gated",
            "An Environment omitting the write token",
        ):
            with self.subTest(text=fine):
                self.assertIsNone(
                    STRANDED_ARTICLE.search(committed_prose(fine)),
                    f"the stranded-article needle fires on correct prose: {fine!r}",
                )

    def test_the_stack_file_census_skips_a_providers_cache(self) -> None:
        """`.terraform/` holds a vendored provider and its CHANGELOG -- third-
        party prose this repository did not write. Read as though it were
        committed text, it would decide these assertions."""
        directory = tempfile.mkdtemp(prefix="stack-files-")
        tree = Path(directory)
        # The suite's own removal idiom, borrowed rather than re-imported:
        # this module imports no `shutil`, and adding one for a cleanup would
        # widen its import surface for no reading it does.
        self.addCleanup(TestTheseReadsDiscriminate._remove, directory)
        stack = tree / "terraform" / "stacks" / "alpha"
        (stack / ".terraform" / "providers").mkdir(parents=True)
        (stack / "main.tf").write_text("# fine\n", encoding="utf-8")
        (stack / ".terraform" / "providers" / "CHANGELOG.md").write_text(
            "a vendored changelog mentioning `stack:` and an stack\n", encoding="utf-8"
        )
        found = [path.name for path in stack_root_files(tree)]
        self.assertEqual(
            ["main.tf"],
            found,
            f"the census read inside a provider cache: {found}",
        )

if __name__ == "__main__":
    unittest.main()
