"""Three conventions this repository's operator runbooks hold, asserted statically.

WRITTEN AS A FIX RATHER THAN AS A CHANGE, and that is worth stating rather than
leaving to be inferred. Nothing here specifies new behaviour: each convention is
already stated where it is kept -- two in the documents themselves, the third in
`.gitignore`'s own comment -- each already holds, and this module is the
mechanism that keeps them holding. There is no delta
specification behind it and no requirement to cite, so no assertion below is
annotated SPECIFIED or DERIVED -- each traces to a sentence of the document,
quoted where it is asserted.

The three conventions, and why none survives without a check:

- **Every `ssh-keygen -f` in either document writes under `~/.ssh/`.**
  `docs/bootstrap-a-new-host.md` §0.3 says so -- *"Every private half above is
  generated into `~/.ssh/`, and none into the repository"* -- and the reason it
  says so is that these are passphrase-less keys and §4.2 runs `git add -A`. A
  relative path puts a private key in the repository root, one routine commit
  from being published. Three of the five key rows carried one; two of those
  were found only by sweeping after a reviewer reported the third.
  `docs/onboard-an-application.md` generates one more, per application per
  environment, and is read here for that reason: the rule is a property of the
  command, not of the document that first stated it.

- **Every key name either document prints is matched by `.gitignore`'s
  private-key block**, and **no directory at the repository root is.** The block
  is the layer under the one above: if a key lands in the checkout anyway, git
  refuses to stage it, and it does so without depending on `pre-commit install`
  having been run -- which stage 0 precedes. That block used to be a list of
  names nothing kept in step with either document, and it drifted exactly as
  that predicts: the scheme renamed `<company>-<app>-deploy` to
  `<company>-<app>-<environment>` and gave the platform key an environment
  suffix, and for a while the most frequently generated key of the set was
  matched by nothing. That gap was recorded in `docs/backlog.md` as
  `cover-the-live-key-names-in-the-private-key-block`; this check is what
  closes it for the next rename rather than for that one. The second half bounds
  the first: the patterns that stopped the drift are broader than a key purpose,
  and a directory swallowed by one would be invisible in a way an unignored key
  is not.

- **Every cross-reference to a numbered section resolves to a heading that
  exists.** The document carries dozens, in two forms -- `§6.6` and the prose
  `stage 6.6` -- and they move when a section is inserted or renumbered.

Each has the property that puts a convention here rather than in a reviewer's
hands: correct when written, correct when reviewed, and wrong only later, in a
commit whose author has no reason to read the rows they break. The first and
third were recorded by `prepare-two-servers-from-the-start`, whose code review
identified both; the middle one by the backlog entry named above, which
`record-how-an-application-is-onboarded` wrote after measuring the drift and
correcting the block's comment rather than its patterns.

The checks have different scopes, deliberately
---------------------------------------------
The **reference** check reads each document in `DOCUMENTS_DECLARING_SECTIONS`,
resolving that document's references against **its own** headings. What it must
never become is a repository-wide sweep: other committed files cite these
documents' sections -- archived change records name several -- and a sweep
reaching those would eventually go red on an archived record, which this
repository may correct only to make it say what actually happened. A document
that numbers and cites its own sections is a different case and carries none of
that exposure, which is why the onboarding document joined the list in the
commit that numbered it. It follows that a pointer from one of these documents
to another must be written in prose rather than as `§N.N`, which is resolved
against the citing document's own headings.

The **key-target** check reads every document in `KEY_GENERATING_DOCUMENTS`. It
resolves nothing against a set of headings at all, so scoping it to one document
would only mean a command losing its check by being moved to where it is run.

What this deliberately does not attempt
---------------------------------------
The reference check is mechanical only: that the target exists, not that it says
what the citing sentence claims. The semantic half has produced two defects and
is not statically decidable; it stays with the editor's note at the head of the
document, along with the second-run and re-derivation habits.

Named appendices (*Appendix A*, *Appendix B*) are not covered. They carry no
number, so there is nothing to resolve and nothing to renumber them.

These assertions live in this suite because they are a static read of committed
files, which is what its row in AGENTS.md's testing table describes.
They add no import beyond the standard library, spawn no subprocess, and need no
network call, credential, container runtime or Terraform binary.
"""

from __future__ import annotations

import fnmatch
import re
import unittest

from test_ci_configuration import ROOT, read_text

BOOTSTRAP = ROOT / "docs" / "bootstrap-a-new-host.md"
ONBOARDING = ROOT / "docs" / "onboard-an-application.md"

# Every document that tells an operator to generate a key. The key-target check
# below reads all of them; the cross-reference check reads BOOTSTRAP alone, for
# the reason the docstring gives. The two scopes differ deliberately: a section
# number resolves within the document that declares it, while `~/.ssh/` is a
# property of every `ssh-keygen` this repository prints, wherever it prints it.
#
# `record-how-an-application-is-onboarded` moved the application deploy key's
# invocation out of the bootstrap document's §0.3 and into the onboarding
# document, where it is run. A check scoped to one document would have followed
# the table and lost the command -- the most frequently run of the two, since it
# repeats per application per environment.
KEY_GENERATING_DOCUMENTS = (BOOTSTRAP, ONBOARDING)

# Each document that numbers its own sections and cites them, with the floor
# under how many that document declares. The floor is per document because it
# guards against the headings ceasing to parse, and what counts as implausibly
# few differs: the bootstrap runbook carries dozens, the onboarding document a
# handful. Both resolve their own references against their own headings, which
# is why widening this reaches no archived record.
DOCUMENTS_DECLARING_SECTIONS = ((BOOTSTRAP, 20), (ONBOARDING, 5))

# The directory the document requires every generated private half to land in.
# One accepted spelling rather than several: an on-host absolute path such as
# `/root/.ssh/` would satisfy the property this exists for -- the key is not in
# the checkout -- but the document contains none today, and widening the rule is
# a decision to take deliberately rather than one to leave pre-taken here.
REQUIRED_KEY_DIRECTORY = "~/.ssh/"

# `-f` and its argument, anywhere after `ssh-keygen` on the same line. The
# argument stops at whitespace or at the backtick closing the code span the
# command sits in.
KEYGEN = re.compile(r"ssh-keygen\b")
KEYGEN_TARGET = re.compile(r"-f\s+(?P<path>[^\s`]+)")

# `.gitignore`'s private-key block, delimited by its own opening comment and by
# the negation that closes it. Read as a region rather than as a whole file
# because the rest of `.gitignore` ignores build output and working trees, and a
# key name matched by `node_modules/` would be matched by accident rather than
# by this block's intent.
GITIGNORE = ROOT / ".gitignore"
BLOCK_OPENING = "# Private keys."
BLOCK_CLOSING = "!*.pub"

# How each placeholder in a printed key target is expanded. Two are DERIVED from
# the committed tree, because the scheme composes a key name out of names this
# repository already declares elsewhere -- and a check reading its own list
# would go stale in exactly the way this module exists to prevent:
#
#   <environment>  the `group_vars` files other than `all.yml`, which is what an
#                  environment IS here: the axis a deploy key's authorising
#                  entry sits on.
#   <stack>        the directories under `terraform/stacks/`.
#
# The other two name things this repository does not own. `<company>` is a
# literal an operator supplies, and `<app>` is an application repository's name,
# so both are sample values rather than a set to read. The applications carry
# the adversarial one: `commerce-ops` contains a hyphen and ends in `-ops`,
# which is the shape that made an unanchored pattern dangerous in the first
# place. Neither company value is adversarial -- a company segment is what a
# pattern's leading `*` eats, so no spelling of it bears on suffix matching.
GROUP_VARS = ROOT / "ansible" / "inventory" / "group_vars"
STACKS = ROOT / "terraform" / "stacks"
SAMPLE_COMPANIES = ("acme", "shatynska")
SAMPLE_APPLICATIONS = ("app", "commerce-ops")

# A placeholder in a printed path: `<company>`, `<app>`, `<environment>`,
# `<stack>`. All four are lowercase alphabetic, and this recognises no other
# spelling -- which is why the guard below looks for a surviving ANGLE BRACKET
# rather than for this pattern. A guard keyed on the pattern would pass an
# `<app_name>` silently: unrecognised, so unexpanded, so tested as the literal
# `acme-<app_name>-staging`, which `/*-staging` matches for the wrong reason
# entirely. An unexpanded name must fail the check, not satisfy it.
PLACEHOLDER = re.compile(r"<(?P<name>[a-z]+)>")


# A section number: `6`, `6.6`, or `6.3a`, which the document uses for a
# subsection inserted after the fact.
_SECTION = r"[0-9]+(?:\.[0-9]+[a-z]?)?"

# The two forms the document cross-references in. Both are matched wherever they
# occur, including inside a heading -- a heading referring to its own number
# resolves to itself and costs nothing.
REFERENCE_FORMS = (
    ("§", re.compile(r"§(?P<section>" + _SECTION + r")")),
    ("stage ", re.compile(r"\b[Ss]tage\s+(?P<section>" + _SECTION + r")")),
)

# A heading that declares a section number, in the three shapes the document
# uses: `## Stage 6. Ansible`, `### 6.6 Hand the converge to the pipeline`, and
# `### 6.3a When the run fails partway`.
HEADING = re.compile(r"^#{2,6}\s+(?:Stage\s+)?(?P<section>" + _SECTION + r")(?:[.\s])")


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def declared_sections(text: str) -> set[str]:
    """Every section number the document's own headings declare."""
    return {
        match.group("section")
        for match in (HEADING.match(line) for line in text.splitlines())
        if match is not None
    }


def keys_generated_outside_the_ssh_directory(text: str) -> list[str]:
    """Every `ssh-keygen -f` whose target is not under `~/.ssh/`, as
    `<line>: <matched text>`.

    An `ssh-keygen` carrying no `-f` is passed over: its target is the client's
    default, which is inside `~/.ssh/` already. The document uses that form once,
    in prose, to name the algorithm.
    """
    return [
        f"{_line_of(text, start)}: {invocation.split('`')[0].strip()}"
        for start, invocation, path in _keygen_invocations(text)
        if not path.startswith(REQUIRED_KEY_DIRECTORY)
    ]


def _keygen_invocations(text: str) -> list[tuple[int, str, str]]:
    """Every `ssh-keygen` carrying a `-f`, as `(offset, invocation, target)`.

    An `ssh-keygen` carrying no `-f` yields nothing: its target is the client's
    default, which is inside `~/.ssh/` already. Both sweeps below read this, so
    a document reaching one reaches the other -- the gap that let the private-key
    block go stale was a second reader keyed on its own list.
    """
    found: list[tuple[int, str, str]] = []
    for start in (match.start() for match in KEYGEN.finditer(text)):
        end = text.find("\n", start)
        invocation = text[start : len(text) if end == -1 else end]
        for target in KEYGEN_TARGET.finditer(invocation):
            found.append((start, invocation, target.group("path").strip("\"'")))
    return found


def keygen_targets(text: str) -> list[tuple[int, str]]:
    """Every `ssh-keygen -f` target in the document, as `(line, path)`."""
    return [
        (_line_of(text, start), path) for start, _, path in _keygen_invocations(text)
    ]


def private_key_patterns() -> list[str]:
    """Every pattern inside `.gitignore`'s private-key block, in file order.

    Order is kept because gitignore resolves a path by the LAST pattern that
    matches it, which is how `!*.pub` un-ignores a public half the block would
    otherwise catch.
    """
    lines = read_text(GITIGNORE).splitlines()
    opening = next(
        (index for index, line in enumerate(lines) if line.startswith(BLOCK_OPENING)),
        None,
    )
    if opening is None:
        return []
    closing = next(
        (
            index
            for index, line in enumerate(lines[opening:], opening)
            if line.strip() == BLOCK_CLOSING
        ),
        None,
    )
    if closing is None:
        return []
    return [
        line.strip()
        for line in lines[opening : closing + 1]
        if line.strip() and not line.strip().startswith("#")
    ]


def _pattern_matches(pattern: str, name: str, is_directory: bool) -> bool:
    """Whether one gitignore pattern matches a path lying directly at the
    repository root.

    A deliberately partial implementation of gitignore's matching, and partial
    in a direction that is safe: it covers the forms this block uses -- a
    root-anchored `/name`, a bare `name`, a trailing `/` restricting to
    directories, and `*` -- and matches nothing else. A pattern carrying an
    interior slash addresses something deeper than the root, and a NAME
    carrying one lies deeper than the root, so both come back unmatched rather
    than being approximated: `fnmatch`'s `*` crosses a separator where
    gitignore's does not, and the one place that difference could show is the
    one place this refuses to read.
    """
    if "/" in name:
        return False
    if pattern.endswith("/"):
        if not is_directory:
            return False
        pattern = pattern[:-1]
    if pattern.startswith("/"):
        pattern = pattern[1:]
    elif "/" in pattern:
        return False
    return fnmatch.fnmatchcase(name, pattern)


def ignored_by_the_block(name: str, *, is_directory: bool = False) -> bool:
    """Whether the private-key block ignores a path of this name at the
    repository root. The last matching pattern decides, and a `!` pattern
    un-ignores."""
    ignored = False
    for pattern in private_key_patterns():
        negated = pattern.startswith("!")
        if _pattern_matches(pattern[1:] if negated else pattern, name, is_directory):
            ignored = not negated
    return ignored


def _expansions_of(placeholder: str) -> tuple[str, ...]:
    if placeholder == "environment":
        return tuple(
            sorted(path.stem for path in GROUP_VARS.glob("*.yml") if path.stem != "all")
        )
    if placeholder == "stack":
        return tuple(sorted(path.name for path in STACKS.iterdir() if path.is_dir()))
    if placeholder == "company":
        return SAMPLE_COMPANIES
    if placeholder == "app":
        return SAMPLE_APPLICATIONS
    return ()


def expanded(name: str) -> list[str]:
    """Every concrete key name a printed target stands for, with each
    placeholder replaced by every value it can take.

    A name carrying a placeholder this module cannot expand comes back
    unexpanded, still carrying it; the caller reports that rather than testing
    it, because a literal `<stack>` is a name no operator types and matching it
    would establish nothing.
    """
    match = PLACEHOLDER.search(name)
    if match is None:
        return [name]
    values = _expansions_of(match.group("name"))
    if not values:
        return [name]
    return [
        further
        for value in values
        for further in expanded(name[: match.start()] + value + name[match.end() :])
    ]


def key_names_printed(text: str) -> list[str]:
    """The basename of every `ssh-keygen -f` target in the document, before
    expansion -- `<company>-platform-<environment>` and the rest."""
    return [path.rsplit("/", 1)[-1] for _, path in keygen_targets(text)]


def key_names_the_block_does_not_ignore(text: str) -> list[str]:
    """Every concrete key name the document prints that the private-key block
    would not ignore, were it generated into the repository root."""
    return sorted(
        {
            name
            for printed in key_names_printed(text)
            for name in expanded(printed)
            if not ignored_by_the_block(name)
        }
    )


def root_directories_the_block_ignores() -> list[str]:
    """Every directory lying at the repository root that the private-key block
    matches.

    `.git` is passed over: it is the repository rather than content in it, and
    no pattern here could reach it without reaching everything. Nothing else is
    excluded, untracked directories included -- a working directory swallowed
    by a widened pattern is the accident this guards against whether or not it
    has been committed yet. That half holds locally only: a CI checkout carries
    tracked content and nothing else, so what runs the gate sees the committed
    directories alone.

    Directories rather than every path, deliberately. A root-level FILE matched
    by the block is the case the block exists for -- a key generated where the
    operator stood -- and reporting it would fail the build over the very thing
    these patterns are meant to catch.
    """
    return sorted(
        path.name
        for path in ROOT.iterdir()
        if path.is_dir()
        and path.name != ".git"
        and ignored_by_the_block(path.name, is_directory=True)
    )


def unresolved_references(text: str) -> list[str]:
    """Every cross-reference naming a section no heading declares, as
    `<line>: <form><section>`."""
    declared = declared_sections(text)
    offences: list[str] = []
    for form, pattern in REFERENCE_FORMS:
        for match in pattern.finditer(text):
            section = match.group("section")
            if section in declared:
                continue
            offences.append(f"{_line_of(text, match.start())}: {form}{section}")
    return sorted(offences, key=lambda entry: int(entry.split(":", 1)[0]))


class TestTheDocumentIsReadAtAll(unittest.TestCase):
    """A check that read nothing reports success having verified nothing, so
    what the two checks below read is asserted before what they conclude."""

    def setUp(self) -> None:
        self.text = read_text(BOOTSTRAP)

    def test_the_document_declares_the_sections_it_is_written_in(self) -> None:
        for document, floor in DOCUMENTS_DECLARING_SECTIONS:
            with self.subTest(document=document.relative_to(ROOT)):
                declared = declared_sections(read_text(document))
                self.assertGreaterEqual(
                    len(declared),
                    floor,
                    f"{document.relative_to(ROOT)} declares {len(declared)} "
                    "numbered section(s). The reference check resolves against "
                    "that set, so a document whose headings stopped parsing "
                    "would report every reference as unresolved -- or, if the "
                    "references stopped parsing too, report a clean sweep "
                    "having read nothing",
                )

    def test_the_document_carries_the_key_generation_commands(self) -> None:
        self.assertGreaterEqual(
            len(KEYGEN.findall(self.text)),
            6,
            f"{BOOTSTRAP.relative_to(ROOT)} carries fewer than six `ssh-keygen` "
            "invocations. The figure is a floor under the whole document -- its "
            "key table, its verify-before-storing steps and its appendices -- "
            "not a count of that table's rows, which is why moving one row out "
            "of §0.3 does not move it. Either the commands went, or the matcher "
            "stopped matching, which would make the check below pass having "
            "read nothing",
        )

    def test_every_key_generating_document_is_read(self) -> None:
        """The floor above is one document's. Without this, a second document
        that stopped being read -- renamed, moved, or never written -- would
        leave the check below sweeping it for nothing and reporting clean."""
        for document in KEY_GENERATING_DOCUMENTS:
            with self.subTest(document=document.relative_to(ROOT)):
                self.assertTrue(
                    KEYGEN.search(read_text(document)),
                    f"{document.relative_to(ROOT)} carries no `ssh-keygen` at "
                    "all, so sweeping it for a key written outside "
                    f"`{REQUIRED_KEY_DIRECTORY}` establishes nothing. It is "
                    "listed as a document that generates keys; either it no "
                    "longer does, and belongs out of that list, or the command "
                    "it should carry is missing",
                )

    def test_every_document_declaring_sections_carries_a_reference(self) -> None:
        """The both-forms floor below is the bootstrap document's, and stays
        there: the onboarding document carries the `§` form only, so requiring
        both of it would assert a convention it does not follow. What matters
        per document is that the sweep over it has something to resolve --
        otherwise a document whose references were rewritten into prose reports
        clean having resolved none, which is this class's whole subject."""
        for document, _ in DOCUMENTS_DECLARING_SECTIONS:
            with self.subTest(document=document.relative_to(ROOT)):
                text = read_text(document)
                self.assertTrue(
                    any(pattern.search(text) for _, pattern in REFERENCE_FORMS),
                    f"{document.relative_to(ROOT)} carries no cross-reference in "
                    "any form, so resolving its references against its own "
                    "headings establishes nothing",
                )

    def test_the_document_carries_cross_references_in_both_forms(self) -> None:
        for form, pattern in REFERENCE_FORMS:
            with self.subTest(form=form):
                self.assertTrue(
                    pattern.search(self.text),
                    f"{BOOTSTRAP.relative_to(ROOT)} carries no cross-reference "
                    f"of the form `{form}`, so the check over that form verifies "
                    "nothing",
                )


class TestEveryGeneratedKeyLandsInTheSshDirectory(unittest.TestCase):
    """§0.3: *Every private half above is generated into `~/.ssh/`, and none
    into the repository.* Held over every document that generates one, not only
    the one that states the rule."""

    def test_no_ssh_keygen_writes_outside_the_ssh_directory(self) -> None:
        for document in KEY_GENERATING_DOCUMENTS:
            with self.subTest(document=document.relative_to(ROOT)):
                offences = keys_generated_outside_the_ssh_directory(read_text(document))
                self.assertEqual(
                    offences,
                    [],
                    f"{len(offences)} `ssh-keygen` invocation(s) in "
                    f"{document.relative_to(ROOT)} write a private key somewhere "
                    f"other than `{REQUIRED_KEY_DIRECTORY}`. A relative path lands "
                    "in whichever directory the command is run from, which for an "
                    "operator following either document is a checkout -- where "
                    "§4.2's `git add -A` can commit a passphrase-less private key. "
                    "Write the target out in full:\n  " + "\n  ".join(offences),
                )


class TestEveryGeneratedKeyNameIsIgnored(unittest.TestCase):
    """`.gitignore`: *Both documents above write each into `~/.ssh/`; these
    catch the relative-path slip that writes one here instead.*

    The sibling class above asserts that no document tells an operator to
    generate a key into the checkout. This one asserts the layer under it: that
    if one lands here anyway, the block catches it. The two fail independently
    and neither substitutes for the other -- a path written out in full is still
    typed by a human at a shell.
    """

    def test_every_printed_key_name_is_matched_by_the_private_key_block(self) -> None:
        for document in KEY_GENERATING_DOCUMENTS:
            with self.subTest(document=document.relative_to(ROOT)):
                missed = key_names_the_block_does_not_ignore(read_text(document))
                self.assertEqual(
                    missed,
                    [],
                    f"{len(missed)} key name(s) {document.relative_to(ROOT)} "
                    "tells an operator to generate are matched by no pattern in "
                    f"`.gitignore`'s private-key block. A passphrase-less "
                    "private half of that name, generated into this checkout by "
                    "a relative path, is unignored and one `git add -A` from "
                    "being published. Either add a pattern covering it or rename "
                    "the key:\n  " + "\n  ".join(missed),
                )

    def test_every_placeholder_in_a_printed_target_can_be_expanded(self) -> None:
        """A name still carrying `<stack>` after expansion was tested as a
        literal no operator types, which is a pass that establishes nothing --
        and is what a fifth placeholder added to the scheme would produce.

        Keyed on the bracket rather than on `PLACEHOLDER`, so a spelling that
        pattern does not recognise -- `<app_name>`, `<Company>` -- is caught
        too. A name carrying one ends in `-staging` as readily as an expanded
        one does, so `/*-staging` matches it and the check above reports clean
        having verified nothing.
        """
        unexpanded = sorted(
            {
                name
                for document in KEY_GENERATING_DOCUMENTS
                for printed in key_names_printed(read_text(document))
                for name in expanded(printed)
                if "<" in name or ">" in name
            }
        )
        self.assertEqual(
            unexpanded,
            [],
            f"{len(unexpanded)} printed key name(s) carry a placeholder this "
            "module cannot expand, so the check above matched a literal angle "
            "bracket against the block rather than a name an operator types. "
            "Teach `_expansions_of` the new placeholder:\n  "
            + "\n  ".join(unexpanded),
        )


class TestThePrivateKeyBlockSwallowsNothingReal(unittest.TestCase):
    """The other direction, and the reason the block's patterns are anchored to
    the root: *Unanchored, `*-ops` would silently swallow a directory called
    `commerce-ops` added later.*

    Two of the patterns are broader than a key purpose -- `/*-staging` and
    `/*-production` cover the platform key and every application's, which is
    what stopped them going stale a third time -- and that breadth is what this
    bounds. A directory ignored by accident is invisible in exactly the way an
    unignored key is not: `git status` reports nothing, and the loss shows up
    when someone clones.
    """

    def test_no_directory_at_the_repository_root_is_matched(self) -> None:
        swallowed = root_directories_the_block_ignores()
        self.assertEqual(
            swallowed,
            [],
            f"{len(swallowed)} director(y/ies) at the repository root are "
            "matched by `.gitignore`'s private-key block, so git ignores them "
            "and their contents wholesale. Either the directory is misnamed for "
            "this repository, or the block was widened past what it can safely "
            "match -- and it is the block that must narrow, since the pattern "
            "exists for a file an operator never meant to create:\n  "
            + "\n  ".join(swallowed),
        )


class TestTheIgnoreMatcherFires(unittest.TestCase):
    """The matcher is a partial reimplementation of gitignore's own, so what it
    reads has to be exercised rather than trusted."""

    def test_the_block_is_found_and_carries_its_patterns(self) -> None:
        patterns = private_key_patterns()
        self.assertGreaterEqual(
            len(patterns),
            8,
            "`.gitignore`'s private-key block parsed as "
            f"{len(patterns)} pattern(s). Both checks above resolve against that "
            "list, so a block that stopped being found would report every key "
            f"name unignored -- or, with an empty list, report the root clean "
            "having matched nothing",
        )

    def test_a_root_anchored_pattern_matches_a_name_at_the_root(self) -> None:
        self.assertTrue(_pattern_matches("/*-ops", "acme-ops", False))

    def test_a_path_below_the_root_is_not_matched(self) -> None:
        """`fnmatch`'s `*` crosses a `/` where gitignore's does not, so a name
        below the root is refused rather than approximated. Nothing this module
        tests lies below the root -- a key is generated in the directory the
        command is run from."""
        self.assertFalse(_pattern_matches("/*-ops", "deeper/acme-ops", False))
        self.assertFalse(_pattern_matches("*.pem", "deeper/acme.pem", False))

    def test_a_bare_pattern_matches_a_name_at_the_root(self) -> None:
        self.assertTrue(_pattern_matches("id_rsa", "id_rsa", False))

    def test_a_pattern_naming_a_deeper_path_matches_nothing_here(self) -> None:
        self.assertFalse(
            _pattern_matches("ansible/roles/geerlingguy.docker/", "geerlingguy.docker", True)
        )

    def test_a_directory_pattern_does_not_match_a_file(self) -> None:
        self.assertFalse(_pattern_matches("node_modules/", "node_modules", False))
        self.assertTrue(_pattern_matches("node_modules/", "node_modules", True))

    def test_the_public_half_is_not_ignored(self) -> None:
        """`!*.pub` is why order is kept, and a matcher taking the FIRST match
        would report the public half ignored -- which would be its own defect."""
        self.assertTrue(ignored_by_the_block("acme-platform-staging"))
        self.assertFalse(ignored_by_the_block("acme-platform-staging.pub"))

    def test_every_placeholder_expands_to_something(self) -> None:
        for placeholder in ("environment", "stack", "company", "app"):
            with self.subTest(placeholder=placeholder):
                self.assertTrue(
                    _expansions_of(placeholder),
                    f"`<{placeholder}>` expands to nothing, so every name "
                    "carrying it is tested unexpanded -- which the check above "
                    "reports, but only because this one says what it should "
                    "have expanded to",
                )

    def test_the_environments_are_read_from_the_group_vars_files(self) -> None:
        """DERIVED, not listed: the check must follow a third environment
        without an edit here, since an environment added without its key names
        being covered is the gap this module exists for."""
        self.assertIn("production", _expansions_of("environment"))
        self.assertNotIn("all", _expansions_of("environment"))

    def test_a_name_expands_over_every_value_of_each_placeholder(self) -> None:
        names = expanded("<company>-platform-<environment>")
        self.assertEqual(
            len(names), len(SAMPLE_COMPANIES) * len(_expansions_of("environment")), names
        )
        self.assertIn("acme-platform-production", names)

    def test_a_key_name_no_pattern_matches_is_reported(self) -> None:
        offences = key_names_the_block_does_not_ignore(
            "`ssh-keygen -t ed25519 -f ~/.ssh/acme-unforeseen-purpose`\n"
        )
        self.assertEqual(offences, ["acme-unforeseen-purpose"], offences)

    def test_a_directory_named_for_an_environment_would_be_reported(self) -> None:
        """The swallow check reports `[]` against this repository's root, and
        would report `[]` just as readily if it had stopped matching. What it
        looks for has to be shown to match something."""
        self.assertTrue(ignored_by_the_block("commerce-ops-staging", is_directory=True))

    def test_the_block_ends_the_file(self) -> None:
        """`private_key_patterns` reads to `!*.pub` and stops, which is the
        whole block only while nothing follows it. A pattern appended after it
        -- the natural place, the block being the file's tail -- would be
        outside the region, and a WIDENING one added there would be invisible
        to the swallow check. This is that assumption, made explicit."""
        lines = [line for line in read_text(GITIGNORE).splitlines() if line.strip()]
        self.assertEqual(
            lines[-1].strip(),
            BLOCK_CLOSING,
            "`.gitignore` carries a pattern after the private-key block's "
            f"closing `{BLOCK_CLOSING}`. Everything this module reads stops "
            "there, so a pattern below it is unread -- move it above the block, "
            "or teach `private_key_patterns` where the block now ends",
        )

    def test_the_retired_application_spelling_is_still_matched(self) -> None:
        """A key generated before the rename is still sitting in someone's
        `~/.ssh/`, which is why the retired patterns were kept."""
        self.assertTrue(ignored_by_the_block("acme-commerce-ops-deploy"))


class TestEveryCrossReferenceResolves(unittest.TestCase):
    """A reference to a section is a reference to a heading that exists."""

    def test_no_cross_reference_names_a_section_the_document_does_not_have(self) -> None:
        for document, _ in DOCUMENTS_DECLARING_SECTIONS:
            with self.subTest(document=document.relative_to(ROOT)):
                offences = unresolved_references(read_text(document))
                self.assertEqual(
                    offences,
                    [],
                    f"{len(offences)} cross-reference(s) in "
                    f"{document.relative_to(ROOT)} name a section no heading "
                    "declares. A section was inserted, renumbered or removed "
                    "without its references following, or a pointer to another "
                    "document was written as `§N.N` -- which resolves against "
                    "this document's headings, so it must be prose:\n  "
                    + "\n  ".join(offences),
                )


# The repository's own document satisfies both conventions, so a check run only
# over it cannot fail and cannot be seen to work. Each detector below is
# therefore also run over material written to falsify it.


class TestTheKeyDetectorFires(unittest.TestCase):
    def test_a_relative_target_is_reported(self) -> None:
        offences = keys_generated_outside_the_ssh_directory(
            "| Key | `ssh-keygen -t ed25519 -f acme-root -C \"root\"` | Yes |\n"
        )
        self.assertEqual(len(offences), 1, offences)
        self.assertIn("acme-root", offences[0])

    def test_a_target_in_another_directory_is_reported(self) -> None:
        offences = keys_generated_outside_the_ssh_directory(
            "`ssh-keygen -t ed25519 -f ~/keys/acme-root`\n"
        )
        self.assertEqual(len(offences), 1, offences)

    def test_a_target_under_the_ssh_directory_is_not_reported(self) -> None:
        self.assertEqual(
            keys_generated_outside_the_ssh_directory(
                "`ssh-keygen -t ed25519 -f ~/.ssh/acme-root -C \"root\"`\n"
            ),
            [],
        )

    def test_an_invocation_naming_no_target_is_not_reported(self) -> None:
        """The client's default is inside `~/.ssh/`, so the form the document
        uses in prose is conformant rather than exempt."""
        self.assertEqual(
            keys_generated_outside_the_ssh_directory("Generate each with `ssh-keygen -t ed25519`.\n"),
            [],
        )

    def test_a_second_offending_row_is_reported_too(self) -> None:
        """The defect this exists for arrived three rows at a time, and a
        detector reporting the first would have sent the sweep back to the
        document once per row."""
        offences = keys_generated_outside_the_ssh_directory(
            "`ssh-keygen -f acme-root`\n\n`ssh-keygen -f acme-ops`\n"
        )
        self.assertEqual(len(offences), 2, offences)


class TestTheReferenceDetectorFires(unittest.TestCase):
    DOCUMENT = "## Stage 6. Ansible\n\n### 6.1 Fill in the inventory\n\n"

    def test_a_reference_to_an_absent_section_is_reported(self) -> None:
        offences = unresolved_references(self.DOCUMENT + "See §6.2 for the rest.\n")
        self.assertEqual(len(offences), 1, offences)
        self.assertIn("§6.2", offences[0])

    def test_a_prose_reference_to_an_absent_section_is_reported(self) -> None:
        offences = unresolved_references(self.DOCUMENT + "See stage 6.2 for the rest.\n")
        self.assertEqual(len(offences), 1, offences)
        self.assertIn("stage 6.2", offences[0])

    def test_a_reference_to_a_declared_section_is_not_reported(self) -> None:
        self.assertEqual(
            unresolved_references(self.DOCUMENT + "See §6.1, and stage 6 as a whole.\n"),
            [],
        )

    def test_a_trailing_sentence_period_is_not_read_as_part_of_the_number(self) -> None:
        self.assertEqual(unresolved_references(self.DOCUMENT + "See §6.1.\n"), [])

    def test_a_letter_suffixed_section_resolves(self) -> None:
        self.assertEqual(
            unresolved_references(
                "### 6.3a When the run fails partway\n\nSee §6.3a.\n"
            ),
            [],
        )

    def test_the_reference_is_reported_at_its_own_line(self) -> None:
        offences = unresolved_references(self.DOCUMENT + "\n\nSee §9.9.\n")
        self.assertEqual(offences, ["7: §9.9"], offences)


if __name__ == "__main__":
    unittest.main()
