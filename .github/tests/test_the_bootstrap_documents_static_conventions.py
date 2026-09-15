"""Two conventions this repository's operator runbooks hold, asserted statically.

WRITTEN AS A FIX RATHER THAN AS A CHANGE, and that is worth stating rather than
leaving to be inferred. Nothing here specifies new behaviour: both conventions
are already stated in the document itself, both already hold of it, and this
module is the mechanism that keeps them holding. There is no delta
specification behind it and no requirement to cite, so no assertion below is
annotated SPECIFIED or DERIVED -- each traces to a sentence of the document,
quoted where it is asserted.

The two conventions, and why neither survives without a check:

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

  `.gitignore` carries a private-key block covering the conventional names and
  part of this scheme's extension-less ones, which bounds the consequence -- but
  that block is a list of names nothing keeps in step with either document, it
  is measurably incomplete today (its own comment says which spellings it
  misses), and this check is what catches a further key purpose added later
  under a name it does not match.

- **Every cross-reference to a numbered section resolves to a heading that
  exists.** The document carries dozens, in two forms -- `§6.6` and the prose
  `stage 6.6` -- and they move when a section is inserted or renumbered.

Both have the property that puts a convention here rather than in a reviewer's
hands: correct when written, correct when reviewed, and wrong only later, in a
commit whose author has no reason to read the rows they break. Recorded by
`prepare-two-servers-from-the-start`, whose code review identified both.

The two checks have different scopes, deliberately
--------------------------------------------------
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
    offences: list[str] = []
    for start in (match.start() for match in KEYGEN.finditer(text)):
        end = text.find("\n", start)
        invocation = text[start : len(text) if end == -1 else end]
        for target in KEYGEN_TARGET.finditer(invocation):
            path = target.group("path").strip("\"'")
            if path.startswith(REQUIRED_KEY_DIRECTORY):
                continue
            offences.append(f"{_line_of(text, start)}: {invocation.split('`')[0].strip()}")
    return offences


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
