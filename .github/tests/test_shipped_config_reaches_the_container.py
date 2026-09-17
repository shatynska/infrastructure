"""Static-assertion tests for the checksum label that makes a shipped
configuration change visible to the container runtime.

Derived from the delta spec of the OpenSpec change
`apply-shipped-config-on-deploy`, before any implementation of that change
existed. The requirement they trace to is *A Shipped Configuration Change Is
Visible to the Container Runtime*, held in
`openspec/specs/iac-platform-deploy-pipeline/spec.md` once that change is
archived. See that change's test-plan.md for the scenario-to-test mapping, the
baseline, the algorithm's provenance, and the scenarios deliberately left
uncovered.

Every assertion below is annotated SPECIFIED (it traces to text in the delta
spec) or DERIVED (it traces to that change's design.md or tasks.md rather than
to a scenario), following the convention `test_ci_configuration.py` states for
itself.

WHAT PASSING THIS MODULE ESTABLISHES, AND WHAT IT DOES NOT
----------------------------------------------------------
It establishes that the committed stack definition carries, for each service
that mounts embedded configuration, a property whose value is a function of
that service's own configuration and of nothing else -- so a
configuration-only edit changes the service definition, and the runtime's
own per-service comparison can see it.

It does NOT establish that a deploy reporting success has applied everything it
shipped. The requirement says so in as many words, and this module cannot say
more: it is a static read of a committed file, so it never observes a running
container, never observes what the runtime actually computed from the
definition, and never observes whether the definition reached the host at all.
A container can fail to be replaced for reasons no property of the definition
can express. That wider confirmation is not implied here and is not to be read
as discharged here.

It also does not establish that the checksum is the property the runtime
happens to hash. That the runtime's per-service digest covers a service-level
label is a measured fact recorded in that change's proposal.md, not something a
static read of this repository can check, and every assertion below rests on
it.

Why this suite and not another
------------------------------
Every property here is a static read of one committed file --
`platform/docker-compose.yml`, its `services:` and `configs:` blocks. AGENTS.md's
testing table routes exactly that to this suite: the change touches no Terraform
module and no Ansible role, so neither `terraform test` nor Molecule can hold
it. Nothing here opens a network connection, reads a credential, spawns a
container runtime or a Terraform binary, and it adds no dependency beyond
PyYAML, which `.github/requirements-ci.txt` already pins.

Held to those constraints by hand
---------------------------------
`TestTheSuiteNeedsNoPrivilegedResource` in `test_ci_configuration.py` reads
`Path(__file__)` -- its own module and no other -- so this file is NOT covered
by the suite's import, subprocess and network self-checks. It is held to them by
hand: standard library, `yaml`, and the helpers of the module beside it, with no
subprocess call of any kind.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_shipped_config_reaches_the_container.TestTheChecksumEqualsTheConfigurationItCovers \\
        .test_every_committed_checksum_equals_a_recomputation_from_the_content

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the helper import below resolve.
"""

from __future__ import annotations

import copy
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from test_ci_configuration import (
    PLATFORM_COMPOSE,
    compose_document,
    compose_services,
    service_config_mounts,
    stack_configs,
)

# --------------------------------------------------------------------------
# iac-platform-deploy-pipeline / A Shipped Configuration Change Is Visible to
# the Container Runtime
#
# Identifiers and constants this section names. A static read of a committed
# file cannot avoid naming what it reads, and the requirement deliberately
# names no algorithm -- it obliges "a property the digest does cover", leaving
# the construction to the design. So none of the four constants below is a
# property the requirement states; each is a constraint the test layer and the
# implementation must agree on, and disagreement on any one of them shows up as
# a failure of this module rather than as a silent difference.
#
# Three of the four are fixed by that change's design.md, Decision 3, which
# fixes them precisely so that two authors -- whoever writes the label and
# whoever recomputes it here -- arrive at the same value without either reading
# the other's work.
# --------------------------------------------------------------------------

# WHERE THE LABEL KEY COMES FROM, AND WHY IT IS THE ONE UNRESOLVED INPUT.
#
# Decision 3 fixes the algorithm, the truncation and the framing. It does NOT
# fix the label's key, and neither does the proposal, the requirement or the
# task list -- they say only "a service-level label". So this name is an
# assumption of this module, not a specification, and it is the single input on
# which the implementation can agree with the algorithm and still fail every
# assertion below.
#
# That is survivable rather than dangerous only because of how the failure
# reads: an implementation using a different key fails
# `TestEveryServiceMountingConfigurationCarriesTheChecksum` with a message
# naming this exact key, so the disagreement is visible in one run and costs one
# rename. It is recorded as an unresolved project question in that change's
# test-plan.md rather than silently adopted.
CHECKSUM_LABEL = "platform.config-checksum"

# Decision 3: SHA-256, hex, truncated to the first 12 characters. The digest
# defends against forgetting, not against a forger, so collision resistance
# beyond a few bytes buys nothing; the length is fixed at 12 rather than
# described as "short" precisely so two authors agree.
DIGEST_LENGTH = 12

# Decision 3's framing: for each config the service mounts, in mount order, the
# config's NAME, a newline, its CONTENT, and a newline; concatenated, then
# hashed. The name participates so that moving a block from one of a service's
# configs into another changes the digest -- without it the input is a bare
# concatenation of contents, and such a move leaves it byte-identical.
DIGEST_FRAME = "{name}\n{content}\n"

# The three services that mount embedded configuration today. NOT used by any
# check -- every check below discovers config-carrying services from the file,
# per that change's design.md Risks, because a check iterating a list of names
# holds only until someone adds a service. Recorded here solely so that
# `test_the_check_discovers_the_services_from_the_file` can show that discovery
# and enumeration currently agree, which is what makes the discovery
# non-vacuous.
SERVICES_MOUNTING_CONFIGS_TODAY = ("alertmanager", "grafana", "prometheus")


# --------------------------------------------------------------------------
# A read-through memo over the sibling module's readers.
#
# Each of `compose_services`, `stack_configs`, `compose_document` and
# `service_config_mounts` re-reads and re-parses the whole stack definition on
# every call, which is unremarkable for a handful of calls and is not for the
# per-service, per-config, per-fixture loops below: unmemoised, this module
# alone took longer than the entire suite it joins, and this suite gates every
# pull request.
#
# Keyed by the file's identity AND its modification time and size, so a fixture
# rewritten in place is re-read rather than served stale. The committed
# definition does not change within a run, and each throwaway fixture is written
# once into a directory of its own.
# --------------------------------------------------------------------------

_PARSE_MEMO: dict = {}


def _stamp(path: Path | None) -> tuple:
    target = PLATFORM_COMPOSE if path is None else path
    if not target.is_file():
        raise AssertionError(f"{target} does not exist")
    status = target.stat()
    return (str(target), status.st_mtime_ns, status.st_size)


def _memoised(kind: str, path: Path | None, produce):
    key = (kind, _stamp(path))
    if key not in _PARSE_MEMO:
        _PARSE_MEMO[key] = produce()
    return _PARSE_MEMO[key]


def configs_of(path: Path | None = None) -> dict:
    return _memoised("configs", path, lambda: stack_configs(path))


def services_of(path: Path | None = None) -> dict:
    return _memoised("services", path, lambda: compose_services(path))


def mounts_of(service: str, path: Path | None = None) -> list[dict]:
    return _memoised(f"mounts:{service}", path, lambda: service_config_mounts(service, path))


class ConfigNotDigestible(AssertionError):
    """A config a service mounts cannot be digested from committed content.

    Raised rather than digested as an empty string. A config whose top-level
    entry is missing, or which is provisioned from a file on the deploy runner
    rather than from inline `content:`, contributes nothing this repository can
    recompute -- and folding that into the digest as `""` would make a renamed
    or externalised config invisible, which is the shape of the defect this
    whole mechanism exists to catch.
    """


def config_name_of(mount: dict, path: Path | None = None) -> str:
    """The key under the top-level `configs:` mapping that a mount names.

    Decision 3 settles that the digest's name component is that key -- not the
    service entry's `source:` and not its `target:`. `source:` is what a
    service entry uses to point at the key, and the two are identical in this
    stack today, so this function is where that identity is checked rather than
    assumed: a `source:` naming no top-level config raises instead of silently
    digesting a name the stack does not define.
    """
    source = mount["source"]
    configs = configs_of(path)
    if source not in configs:
        raise ConfigNotDigestible(
            f"a service mounts config {source!r}, which the stack's top-level "
            f"`configs:` mapping does not define, so its content cannot be read "
            f"from this repository at all"
        )
    return source


def inline_config_content(name: str, path: Path | None = None) -> str:
    """The parsed scalar value of a top-level config's `content:` key.

    Decision 3: the parsed scalar, "as a YAML loader returns it" -- not the raw
    indented source text, which carries the block's own indentation and would
    make the digest depend on where in the file the block happens to sit.
    """
    definition = configs_of(path).get(name)
    if not isinstance(definition, dict):
        raise ConfigNotDigestible(f"config {name!r} declares no mapping of its own")
    content = definition.get("content")
    if not isinstance(content, str):
        raise ConfigNotDigestible(
            f"config {name!r} carries no inline `content:` scalar, so no checksum "
            f"of it can be recomputed from this repository"
        )
    return content


def digest_input(service: str, path: Path | None = None) -> str:
    """Decision 3's digest input for one service, over its own configs alone.

    "Its own configs alone" is what makes the requirement's second scenario
    true: a single digest over every config in the stack would satisfy every
    other property asserted here and quietly recreate the whole monitoring
    stack on any dashboard edit.
    """
    mounts = mounts_of(service, path)
    if not mounts:
        raise ConfigNotDigestible(
            f"service {service!r} mounts no config, so it has no configuration "
            f"checksum to compute"
        )
    framed = []
    for mount in mounts:
        name = config_name_of(mount, path)
        framed.append(DIGEST_FRAME.format(name=name, content=inline_config_content(name, path)))
    return "".join(framed)


def expected_checksum(service: str, path: Path | None = None) -> str:
    """The value the service's checksum label should hold."""
    digest = hashlib.sha256(digest_input(service, path).encode("utf-8")).hexdigest()
    return digest[:DIGEST_LENGTH]


def service_labels(service: str, path: Path | None = None) -> dict:
    """A service's labels as a mapping, in either form Compose accepts.

    Compose takes `labels:` as a mapping or as a list of `KEY=VALUE` strings.
    Reading only the mapping form would report a correctly labelled service as
    unlabelled, which fails the pull request for a formatting choice rather
    than for a stale checksum.

    Values are coerced to `str`. A YAML loader returns an unquoted twelve-digit
    checksum as an integer, and comparing that against a hex string would
    report a correct label as wrong once in every sixteen-to-the-twelfth
    checksums.
    """
    definition = services_of(path).get(service)
    if not isinstance(definition, dict):
        raise AssertionError(f"the stack defines no service named {service!r}")
    labels = definition.get("labels")
    if isinstance(labels, dict):
        return {str(key): str(value) for key, value in labels.items()}
    if isinstance(labels, list):
        pairs = {}
        for entry in labels:
            if not isinstance(entry, str) or "=" not in entry:
                continue
            key, _, value = entry.partition("=")
            pairs[key.strip()] = value.strip()
        return pairs
    return {}


def services_mounting_configs(path: Path | None = None) -> list[str]:
    """Every service that declares a `configs:` entry, read from the file.

    Discovery rather than enumeration, per that change's design.md Risks: a
    service that gains a `configs:` entry later, with no label, is exactly the
    case an enumerated check would miss.
    """
    found = []
    for name, definition in sorted(services_of(path).items()):
        entries = definition.get("configs") if isinstance(definition, dict) else None
        if isinstance(entries, list) and entries:
            found.append(name)
    return found


def services_missing_the_checksum_label(path: Path | None = None) -> list[str]:
    return [
        service
        for service in services_mounting_configs(path)
        if CHECKSUM_LABEL not in service_labels(service, path)
    ]


def services_labelled_without_mounting_configs(path: Path | None = None) -> list[str]:
    return [
        name
        for name in sorted(services_of(path))
        if name not in services_mounting_configs(path)
        and CHECKSUM_LABEL in service_labels(name, path)
    ]


def checksum_disagreements(path: Path | None = None) -> list[str]:
    """One sentence per config-carrying service whose label is not the value a
    recomputation from its own configs produces.

    Each sentence NAMES THE VALUE THE LABEL SHOULD HOLD. That is not
    presentation: the mechanism's whole friction budget rests on it (that
    change's design.md, Decision 2), because the alternative is an author who
    knows something is wrong and does not know what to write.
    """
    offences = []
    for service in services_mounting_configs(path):
        expected = expected_checksum(service, path)
        committed = service_labels(service, path).get(CHECKSUM_LABEL)
        if committed is None:
            offences.append(
                f"{service}: carries no `{CHECKSUM_LABEL}` label; it should hold "
                f"{expected}"
            )
        elif committed != expected:
            offences.append(
                f"{service}: `{CHECKSUM_LABEL}` holds {committed}; it should hold "
                f"{expected}"
            )
    return offences


STALE_LABEL_CONSEQUENCE = (
    "a checksum that does not match the configuration it names is not a checksum "
    "-- the service definition then fails to move when its embedded configuration "
    "does, so the deploy that ships the edit recreates nothing, changes nothing "
    "and reports success"
)


class StackFixtureMixin:
    """Throwaway stack definitions differing from the committed one in exactly
    one property.

    The base every fixture starts from is the committed definition with a
    CORRECT checksum label written onto each config-carrying service, computed
    here from the algorithm the requirement's design fixes. Starting from the
    committed file instead would make every fixture fail for the reason the
    committed file already fails today -- no label -- and would establish
    nothing about the mutation under test.

    Writing those labels is not reading the implementation and does not derive
    anything from it: the values come from `expected_checksum` above, which is
    this module's own recomputation. What the fixtures test is that the checks
    respond to the file, not that the implementation is right; that is
    `TestTheChecksumEqualsTheConfigurationItCovers`'s job, against the
    committed file.
    """

    def write_stack(self, document: dict) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="platform-checksum-fixture-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "docker-compose.yml"
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, width=4096), encoding="utf-8"
        )
        return path

    def labelled_document(self) -> dict:
        document = copy.deepcopy(compose_document())
        for service in services_mounting_configs():
            document["services"][service]["labels"] = {
                CHECKSUM_LABEL: expected_checksum(service)
            }
        return document

    def labelled_stack(self) -> Path:
        return self.write_stack(self.labelled_document())

    def stack_with_edited_config(self, name: str, addition: str = "\n# edited\n") -> Path:
        """The base, with one config's content changed and every label left as
        it was -- the shape of an author who edits a rule and forgets."""
        document = self.labelled_document()
        document["configs"][name]["content"] += addition
        return self.write_stack(document)


class TestEveryServiceMountingConfigurationCarriesTheChecksum(unittest.TestCase):
    """ADDED requirement: A Shipped Configuration Change Is Visible to the
    Container Runtime.

    WHAT PASSING THIS CLASS ESTABLISHES, AND WHAT IT DOES NOT
    --------------------------------------------------------
    Only that the property EXISTS on every service the requirement obliges, and
    on no other. It says nothing about the property's VALUE, so on its own it
    is satisfied by three labels holding the same constant -- which would make
    every configuration-only deploy a no-op exactly as today. That gap is
    closed by `TestTheChecksumEqualsTheConfigurationItCovers` and by nothing
    else in this module; this class is a necessary condition and never a
    sufficient one.
    """

    def test_every_service_mounting_embedded_configuration_carries_the_label(self) -> None:
        """SPECIFIED -- "the stack definition SHALL carry -- for each service
        that mounts embedded configuration -- a property the digest does
        cover"."""
        missing = services_missing_the_checksum_label()
        self.assertEqual(
            [],
            missing,
            f"these services mount embedded configuration and carry no "
            f"`{CHECKSUM_LABEL}` label, so the runtime's per-service comparison "
            f"cannot see a change to that configuration and will leave their "
            f"containers in place: {missing}",
        )

    def test_no_service_without_embedded_configuration_carries_the_label(self) -> None:
        """SPECIFIED -- "Satisfying this by replacing every service on every
        deploy SHALL NOT be used, because it would replace stateful services
        whose configuration did not change". A label copy-pasted onto a service
        that mounts nothing widens the recreation set past what changed, which
        is the same failure in miniature: this stack's one stateful service,
        `postgres`, mounts no config."""
        widened = services_labelled_without_mounting_configs()
        self.assertEqual(
            [],
            widened,
            f"these services mount no embedded configuration and yet carry a "
            f"`{CHECKSUM_LABEL}` label, which widens what a deploy recreates past "
            f"the services whose configuration actually moved: {widened}",
        )

    def test_the_check_discovers_the_services_from_the_file(self) -> None:
        """DERIVED -- no scenario states it; it traces to that change's
        design.md Risks, "A service that gains a `configs:` entry later, with no
        label, is uncovered", which requires discovery rather than a list of
        three names.

        Asserts that discovery currently agrees with the enumeration this
        module records for reference only. Agreement is what makes the
        discovery non-vacuous today; the fixture test below is what shows it is
        discovery rather than that enumeration.
        """
        self.assertEqual(
            sorted(SERVICES_MOUNTING_CONFIGS_TODAY),
            services_mounting_configs(),
            "the set of services mounting embedded configuration has moved, so "
            "either a service gained configuration or the discovery no longer "
            "reads the file. If a service was added deliberately, give it a "
            "`platform.config-checksum` label and add its name to "
            "`SERVICES_MOUNTING_CONFIGS_TODAY` above -- this assertion pins the "
            "live set on purpose, so adding a service is a two-line edit rather "
            "than a silent widening of what these checks cover",
        )


class TestTheMissingLabelCheckIsARealReadOfTheFile(
    StackFixtureMixin, unittest.TestCase
):
    """ADDED requirement: A Shipped Configuration Change Is Visible to the
    Container Runtime.

    A check that silently covered only the three services that exist today
    would pass the class above identically while catching nothing a later edit
    introduces.
    """

    def test_a_service_added_with_configuration_and_no_label_is_caught(self) -> None:
        """SPECIFIED -- the requirement's central clause holds of "each service
        that mounts embedded configuration", including one that does not exist
        yet. This is that change's tasks.md 2.1's named falsification."""
        document = self.labelled_document()
        document["configs"]["newcomer_config"] = {"content": "answer: 42\n"}
        document["services"]["newcomer"] = {
            "image": "redis:7.4.2",
            "configs": [{"source": "newcomer_config", "target": "/etc/newcomer.yml"}],
        }
        fixture = self.write_stack(document)
        self.assertEqual(
            ["newcomer"],
            services_missing_the_checksum_label(fixture),
            "a service added with embedded configuration and no checksum label was "
            "not caught, so the check enumerates the services it knows about "
            "rather than reading the file",
        )

    def test_a_label_on_a_service_mounting_nothing_is_caught(self) -> None:
        """SPECIFIED -- the same "SHALL NOT be used" clause, shown to respond to
        the file. This is that change's tasks.md 2.5's named falsification:
        `postgres` is the stateful service the clause is about."""
        document = self.labelled_document()
        document["services"]["postgres"]["labels"] = {CHECKSUM_LABEL: "0" * DIGEST_LENGTH}
        fixture = self.write_stack(document)
        self.assertEqual(
            ["postgres"],
            services_labelled_without_mounting_configs(fixture),
            "a checksum label copy-pasted onto the stack's stateful service, which "
            "mounts no configuration, was not caught",
        )

    def test_a_correctly_labelled_stack_is_accepted(self) -> None:
        """DERIVED -- the converse half. Without it, a check reporting every
        service as an offender would satisfy both tests above while failing
        every pull request regardless of what it changed."""
        fixture = self.labelled_stack()
        self.assertEqual([], services_missing_the_checksum_label(fixture))
        self.assertEqual([], services_labelled_without_mounting_configs(fixture))

    def test_the_list_form_of_labels_is_read_as_well_as_the_mapping_form(self) -> None:
        """DERIVED -- no scenario states it. Compose accepts `labels:` as a
        mapping or as a list of `KEY=VALUE` strings; a check reading only one
        form would report a correctly labelled service as unlabelled and fail
        the pull request for a formatting choice."""
        document = self.labelled_document()
        service = services_mounting_configs()[0]
        document["services"][service]["labels"] = [
            f"{CHECKSUM_LABEL}={expected_checksum(service)}"
        ]
        fixture = self.write_stack(document)
        self.assertEqual([], services_missing_the_checksum_label(fixture))
        self.assertEqual([], checksum_disagreements(fixture))


class TestTheChecksumEqualsTheConfigurationItCovers(unittest.TestCase):
    """ADDED requirement: A Shipped Configuration Change Is Visible to the
    Container Runtime.

    This is the class that carries the requirement's third scenario -- a stale
    marker fails before it reaches a deploy -- and it is the one that excludes
    every wrong construction of the property. The committed labels are
    literals: they either equal the per-service recomputation the design fixes,
    or they do not.

    WHAT PASSING THIS CLASS ESTABLISHES, AND WHAT IT DOES NOT
    --------------------------------------------------------
    It establishes that each committed label is the value the fixed algorithm
    produces from that service's own configs, today. It does NOT establish that
    the runtime's per-service digest actually covers a service-level label --
    that is a measured fact recorded in that change's proposal.md, unreachable
    by any static read of this repository, and every assertion here rests on
    it. Nor does it establish that a deploy applied what it shipped; see this
    module's own docstring.
    """

    def test_every_committed_checksum_equals_a_recomputation_from_the_content(self) -> None:
        """SPECIFIED -- scenario "A stale marker fails before it reaches a
        deploy": where the property is maintained in the stack definition
        rather than computed at deploy time and is not updated to match, "that
        discrepancy SHALL fail a check that blocks the pull request".

        This suite is invoked by the required status check --
        `TestTheSuiteIsWiredIntoTheRequiredCheck` in the module beside this one
        asserts as much -- so a failure here blocks the merge rather than
        merely reporting.
        """
        offences = checksum_disagreements()
        self.assertEqual(
            [],
            offences,
            f"{STALE_LABEL_CONSEQUENCE}. Each line names the value the label should "
            f"hold: {offences}",
        )

    def test_the_check_covers_every_service_that_mounts_configuration(self) -> None:
        """DERIVED -- no scenario states it. It guards the assertion above from
        passing vacuously over a partial read, the same failure mode this
        suite's shared-stack pinning section guards against with its own
        discovery test."""
        covered = services_mounting_configs()
        self.assertTrue(
            covered,
            "no service in the stack mounts embedded configuration, so the checksum "
            "assertions above pass having checked nothing",
        )
        for service in covered:
            with self.subTest(service=service):
                # The COMMITTED label's length, not the recomputation's.
                # `expected_checksum` returns `digest[:DIGEST_LENGTH]`, so
                # asserting the length of what it returns cannot fail -- it was
                # written that way and caught in code review. The committed
                # value can be the wrong length: a hand-truncated 8 characters,
                # or a full 64-character digest pasted whole. Either is already
                # caught by the equality assertion above; this reports it as a
                # length rather than as two long strings that differ.
                committed = service_labels(service).get(CHECKSUM_LABEL)
                if committed is None:
                    continue  # absence is the missing-label class's to report
                self.assertEqual(
                    DIGEST_LENGTH,
                    len(committed),
                    f"{service}'s `{CHECKSUM_LABEL}` is {len(committed)} characters, "
                    f"not {DIGEST_LENGTH} -- it is not a digest of the length "
                    f"that change's design.md Decision 3 fixes",
                )


class TestTheChecksumCheckIsARealReadOfTheConfiguration(
    StackFixtureMixin, unittest.TestCase
):
    """ADDED requirement: A Shipped Configuration Change Is Visible to the
    Container Runtime.

    The falsification half of the class above: the same check run over
    throwaway definitions differing in exactly one property, so its verdict is
    shown to depend on the configuration content rather than on anything
    written into the test.
    """

    def test_an_edited_rule_with_the_label_left_alone_is_caught(self) -> None:
        """SPECIFIED -- the third scenario's own case, and that change's
        tasks.md 2.2's named falsification: one alert rule edited, the label
        untouched."""
        fixture = self.stack_with_edited_config(
            "prometheus_rules", "\n# a threshold moved\n"
        )
        offences = checksum_disagreements(fixture)
        self.assertEqual(
            1,
            len(offences),
            f"an edit to one service's embedded configuration with its label left "
            f"stale produced {len(offences)} offences rather than exactly one: "
            f"{offences}",
        )
        self.assertTrue(
            offences[0].startswith("prometheus:"),
            f"the stale label was not attributed to the service whose configuration "
            f"moved: {offences}",
        )

    def test_the_failure_names_the_value_the_label_should_hold(self) -> None:
        """SPECIFIED -- scenario "A stale marker fails before it reaches a
        deploy" requires the discrepancy to fail a check; that change's
        design.md Decision 2 requires the failure to name the correct value,
        because the alternative is an author who knows something is wrong and
        not what to write.

        Asserted by provoking the check rather than by reading its source: a
        message asserted to CONTAIN the recomputed digest cannot be satisfied
        by a message that merely mentions one.
        """
        fixture = self.stack_with_edited_config(
            "alertmanager_config", "\n# a route moved\n"
        )
        should_hold = expected_checksum("alertmanager", fixture)
        offences = checksum_disagreements(fixture)
        self.assertTrue(offences, "the check reported nothing to name a value in")
        self.assertIn(
            should_hold,
            offences[0],
            f"the failure does not name the value the label should hold "
            f"({should_hold}), so an author reading it learns that something is "
            f"wrong and not what to write: {offences[0]}",
        )

    def test_a_correctly_labelled_stack_reports_no_disagreement(self) -> None:
        """DERIVED -- the converse half. Without it, a check reporting every
        service as stale would satisfy the two tests above while failing every
        pull request regardless of what it changed."""
        self.assertEqual([], checksum_disagreements(self.labelled_stack()))

    def test_a_config_with_no_inline_content_fails_rather_than_digesting_nothing(
        self,
    ) -> None:
        """DERIVED -- no scenario states it. A config that cannot be read from
        this repository would otherwise contribute the empty string, so
        renaming or externalising it would leave the digest computable and
        wrong -- a silent reinstatement of the defect."""
        document = self.labelled_document()
        document["configs"]["prometheus_rules"] = {"file": "./rules.yml"}
        fixture = self.write_stack(document)
        with self.assertRaises(ConfigNotDigestible):
            checksum_disagreements(fixture)

    def test_a_service_mounting_a_config_the_stack_does_not_define_fails(self) -> None:
        """DERIVED -- the same non-vacuity guard, on the other side of the
        reference. Decision 3 names the top-level `configs:` key as the digest's
        name component; this is where the identity between that key and the
        service entry's `source:` is checked rather than assumed."""
        document = self.labelled_document()
        document["services"]["alertmanager"]["configs"] = [
            {"source": "no_such_config", "target": "/etc/alertmanager/alertmanager.yml"}
        ]
        fixture = self.write_stack(document)
        with self.assertRaises(ConfigNotDigestible):
            checksum_disagreements(fixture)


class TestTheChecksumCoversEveryConfigTheServiceMounts(
    StackFixtureMixin, unittest.TestCase
):
    """ADDED requirement: A Shipped Configuration Change Is Visible to the
    Container Runtime.

    A digest built from only the first of a service's configs would satisfy
    every assertion above -- the committed labels would still equal it, and it
    would still move on an edit -- while leaving four of Grafana's five
    dashboards and one of Prometheus's two configs as invisible to the deploy
    as they are today. These tests are about the recomputation, so they assert
    over mutated copies; a committed literal cannot respond to a mutation.
    """

    def test_editing_any_one_of_a_services_configs_moves_that_services_checksum(
        self,
    ) -> None:
        """SPECIFIED -- scenario "A configuration-only change reaches the
        running service" requires the service definition to differ whenever the
        change is "confined to a service's embedded configuration", with no
        restriction to the first such config. Discovered from the file, so a
        config added to a service later is covered without a test edit."""
        base = self.labelled_stack()
        for service in services_mounting_configs():
            for mount in mounts_of(service, base):
                name = mount["source"]
                with self.subTest(service=service, config=name):
                    moved = self.stack_with_edited_config(name)
                    self.assertNotEqual(
                        expected_checksum(service, base),
                        expected_checksum(service, moved),
                        f"editing {name} left {service}'s checksum where it was, so "
                        f"the digest does not cover every config that service "
                        f"mounts and an edit to this one would deploy green and "
                        f"take no effect",
                    )

    def test_editing_grafanas_last_dashboard_moves_grafanas_checksum(self) -> None:
        """SPECIFIED -- the same scenario, at the position a first-config-only
        digest would miss most visibly. This is that change's tasks.md 2.3's
        named falsification, kept as its own selectable test rather than left
        implicit in the loop above."""
        mounts = mounts_of("grafana")
        self.assertGreater(
            len(mounts), 1, "grafana no longer mounts more than one config"
        )
        last = mounts[-1]["source"]
        base = self.labelled_stack()
        moved = self.stack_with_edited_config(last, '\n{"appended": true}\n')
        self.assertNotEqual(
            expected_checksum("grafana", base),
            expected_checksum("grafana", moved),
            f"editing {last}, the last config grafana mounts, left grafana's "
            f"checksum where it was",
        )
        self.assertEqual(
            ["grafana"],
            [offence.split(":")[0] for offence in checksum_disagreements(moved)],
            "an edit to grafana's last dashboard was not reported against grafana",
        )


class TestEachChecksumIsAFunctionOfThatServicesOwnConfigsAlone(
    StackFixtureMixin, unittest.TestCase
):
    """ADDED requirement: A Shipped Configuration Change Is Visible to the
    Container Runtime.

    WHAT THIS CLASS ADDS, AND WHAT IT DOES NOT
    ------------------------------------------
    Less than it looks. `TestTheChecksumEqualsTheConfigurationItCovers` is what
    excludes every wrong construction, because the committed labels are
    literals that either equal the specified per-service recomputation or do
    not -- including the awkward variant that digests a service's own configs
    together with all of them, which is distinct per service and yet moves all
    three on any edit.

    Distinctness is therefore a true but WEAK necessary condition, and nothing
    below should be read as establishing the second scenario on its own. The
    second test is a property of this module's recomputation function rather
    than of the committed labels -- a literal cannot respond to a mutated copy
    -- so it is written as a regression guard on that function, not as a
    constraint on the implementation.
    """

    def test_the_committed_checksums_are_pairwise_distinct(self) -> None:
        """SPECIFIED -- scenario "Only the service whose configuration changed
        is replaced". A necessary condition only: identical labels across the
        three would mean one service's edit moved all three definitions, but
        distinct labels do not by themselves mean each is a function of its own
        configuration."""
        held = {
            service: service_labels(service).get(CHECKSUM_LABEL)
            for service in services_mounting_configs()
        }
        absent = sorted(name for name, value in held.items() if value is None)
        self.assertEqual(
            [],
            absent,
            f"these services carry no `{CHECKSUM_LABEL}` label, so there is no value "
            f"to compare: {absent}",
        )
        values = list(held.values())
        self.assertEqual(
            len(set(values)),
            len(values),
            f"two services carry the same configuration checksum, so an edit to one "
            f"service's configuration would move both definitions and recreate a "
            f"service whose configuration did not change: {held}",
        )

    def test_editing_one_services_configuration_moves_only_its_own_checksum(self) -> None:
        """SPECIFIED -- the same scenario, asserted as a guard on this module's
        recomputation rather than on the committed labels, for the reason this
        class's docstring gives. That change's tasks.md 2.4's named
        falsification: one config edited, the other two services' expected
        values recomputed."""
        base = self.labelled_stack()
        for service in services_mounting_configs():
            edited = mounts_of(service, base)[0]["source"]
            moved = self.stack_with_edited_config(edited)
            for other in services_mounting_configs():
                with self.subTest(edited=edited, observed=other):
                    if other == service:
                        continue
                    self.assertEqual(
                        expected_checksum(other, base),
                        expected_checksum(other, moved),
                        f"editing {edited}, which {service} mounts, moved {other}'s "
                        f"checksum as well -- so the digest is not a function of "
                        f"each service's own configs alone, and a dashboard edit "
                        f"would recreate the whole monitoring stack",
                    )


class TestTheChecksumFramesEachConfigByName(StackFixtureMixin, unittest.TestCase):
    """ADDED requirement: A Shipped Configuration Change Is Visible to the
    Container Runtime.

    A digest over a bare concatenation of a service's config contents leaves a
    block moved from one of them into another byte-identical: the label
    unchanged, the definition unchanged, the deploy green, and the original
    defect surviving in its original shape. That change's design.md, Decision 3,
    puts the config's NAME in the digest input as the delimiter that makes the
    framing unambiguous.

    Like the class above, this is a property of the recomputation rather than of
    the committed labels, and is written as a guard.
    """

    MOVED_LINES = 4

    def moved_block(self) -> tuple[Path, Path]:
        """The base, and a copy in which a block moves from `prometheus_config`
        into `prometheus_rules` with the total content unchanged.

        Neither half is valid Prometheus configuration afterwards, and does not
        need to be: what is under test is the digest's framing, which is a
        static property of two strings and their names.
        """
        document = self.labelled_document()
        head = document["configs"]["prometheus_config"]["content"]
        tail = document["configs"]["prometheus_rules"]["content"]
        lines = head.splitlines(keepends=True)
        self.assertGreater(len(lines), self.MOVED_LINES, "prometheus_config is too short to split")
        kept, moved = lines[: -self.MOVED_LINES], lines[-self.MOVED_LINES :]
        document["configs"]["prometheus_config"]["content"] = "".join(kept)
        document["configs"]["prometheus_rules"]["content"] = "".join(moved) + tail
        return self.labelled_stack(), self.write_stack(document)

    def test_the_moved_block_leaves_the_bare_concatenation_identical(self) -> None:
        """DERIVED -- no scenario states it. It is what makes the test below
        non-tautological: without it, a fixture that happened to change the
        total content would show the digest moving for a reason that has
        nothing to do with framing."""
        base, moved = self.moved_block()
        self.assertEqual(
            "".join(
                inline_config_content(mount["source"], base)
                for mount in mounts_of("prometheus", base)
            ),
            "".join(
                inline_config_content(mount["source"], moved)
                for mount in mounts_of("prometheus", moved)
            ),
            "the fixture changed prometheus's total configuration content, so it "
            "does not isolate the digest's framing",
        )

    def test_a_block_moved_between_two_of_a_services_configs_moves_the_checksum(
        self,
    ) -> None:
        """SPECIFIED -- scenario "A configuration-only change reaches the
        running service" holds of a change "confined to a service's embedded
        configuration", which a block moved between two of that service's
        configs is: the files the container is created with differ afterwards.
        That change's tasks.md 2.6's named falsification."""
        base, moved = self.moved_block()
        self.assertNotEqual(
            expected_checksum("prometheus", base),
            expected_checksum("prometheus", moved),
            "moving a block from prometheus_config into prometheus_rules left the "
            "checksum where it was, so the digest is a bare concatenation of "
            "contents and the config's name does not participate -- a change that "
            "alters both files on disk would deploy green and take no effect",
        )

    def test_the_moved_block_is_caught_against_a_stale_label(self) -> None:
        """SPECIFIED -- the third scenario, over the same move: the label was
        not updated, so the check must report it."""
        _, moved = self.moved_block()
        self.assertEqual(
            ["prometheus"],
            [offence.split(":")[0] for offence in checksum_disagreements(moved)],
            "a block moved between two of prometheus's configs, with the label left "
            "alone, was not reported against prometheus",
        )
