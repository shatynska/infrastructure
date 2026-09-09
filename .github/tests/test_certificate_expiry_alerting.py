"""Static-assertion tests for the TLS-certificate-expiry alert this stack owes.

Derived from the delta spec of the OpenSpec change `alert-on-certificate-expiry`,
before any implementation of that change existed. The requirement they trace to
is *An Expiring TLS Certificate Is Alerted On Before It Expires*, held in
`openspec/specs/iac-platform-services/spec.md` once that change is archived. See
that change's test-plan.md for the scenario-to-test mapping, the baseline, and
the scenarios deliberately left uncovered.

Every assertion below is annotated SPECIFIED (it traces to text in the delta
spec) or DERIVED (it traces to that change's design.md or tasks.md rather than
to a scenario), following the convention `test_ci_configuration.py` states for
itself.

Why this suite and not another
------------------------------
Every property here is a static read of one committed file --
`platform/docker-compose.yml`, whose `prometheus_rules`, `prometheus_config` and
`alertmanager_config` entries the pipeline deploys. AGENTS.md's testing table
routes exactly that to this suite: the change touches no Terraform module and no
Ansible role, so neither `terraform test` nor Molecule can hold it. Nothing here
opens a network connection, reads a credential, spawns a container runtime or a
Terraform binary, and it adds no dependency beyond PyYAML, which
`.github/requirements-ci.txt` already pins.

Why this is a second file in a suite that was one file
------------------------------------------------------
These tests were written by an author other than whoever implements the rules,
from the delta spec rather than from the rules, and that change's tasks require
them committed as written before any folding or relocation. Folding this file
into `test_ci_configuration.py` afterwards is a reviewable move rather than an
authoring decision. One consequence should be understood before that happens:
`TestTheSuiteNeedsNoPrivilegedResource` in that file reads
`Path(__file__)` -- its own module and no other -- so this file is NOT covered
by the suite's import, subprocess and network self-checks while it sits here.
It is held to them by hand: standard library, `yaml`, and the helpers of the
module beside it, with no subprocess call of any kind.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_certificate_expiry_alerting.TestAnExpiringCertificateIsAlertedOn \\
        .test_an_alert_reads_the_certificate_expiry_the_proxy_publishes

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the helper import below resolve.
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
    PLATFORM_COMPOSE,
    compose_services,
    config_content,
    service_config_mounts,
    stack_configs,
)

# --------------------------------------------------------------------------
# iac-platform-services / An Expiring TLS Certificate Is Alerted On Before It
# Expires
#
# Identifiers this section names. A static read of a committed file cannot
# avoid naming what it reads, so each name below is a constraint of the test
# layer, not a property the requirement states. The requirement speaks of "the
# shared reverse proxy", "metrics the reverse proxy already publishes" and "the
# configured number of days"; these are what those resolve to in this stack.
# --------------------------------------------------------------------------

PROXY_SERVICE = "traefik"
RULES_CONFIG = "prometheus_rules"
SCRAPE_CONFIG = "prometheus_config"
ALERTMANAGER_CONFIG = "alertmanager_config"

# The gauge Traefik publishes for each certificate it holds, one series per
# certificate, carrying the common name as a label.
EXPIRY_METRIC = "traefik_tls_certs_not_after"
CERTIFICATE_LABEL = "cn"

# The scrape job that collects it. `MetricsTargetDown` covers this job at
# runtime; if the job stops being declared, that cover goes with it and the
# expiry rules evaluate an empty vector forever.
SCRAPE_JOB = "traefik"

SECONDS_PER_DAY = 86400

# WHERE THIS CONSTANT COMES FROM, AND WHY IT IS NOT A NUMBER OF THIS PROJECT'S
# OWN CHOOSING.
#
# It is Traefik's documented default renewal lead time: it begins renewing an
# ACME certificate 30 days before expiry, rechecking daily and retrying on
# failure. It is an UPSTREAM default, not a value this repository sets, and it
# holds only because the stack sets no `certificatesDuration` on its ACME
# resolver -- with that option set, Traefik derives a different lead time and 30
# stops being the number the alert threshold has to stay below.
#
# So the constant is checked rather than assumed:
# `TestTheThresholdLeavesNormalRenewalAlone
# .test_the_stack_leaves_the_certificate_duration_unset` asserts the
# precondition, and a test in that same class asserts this provenance is still
# recorded here, so it cannot be deleted while the constant survives.
#
# Being an upstream default, it can move under a Traefik upgrade without
# anything in this repository changing. That is a real limit of every assertion
# resting on it: they establish that the committed threshold is below the lead
# time Traefik documented when they were written.
RENEWAL_LEAD_TIME_DAYS = 30

# The static option that would falsify the constant above. Matched
# case-insensitively because Traefik accepts it as a CLI flag
# (`--certificatesresolvers.<name>.acme.certificatesduration`), as a TOML/YAML
# key (`certificatesDuration`), and as an environment variable.
CERTIFICATE_DURATION_OPTION = "certificatesduration"

_WORD = r"(?<![A-Za-z0-9_]){}(?![A-Za-z0-9_])"
METRIC_REFERENCE = re.compile(_WORD.format(re.escape(EXPIRY_METRIC)))
ABSENCE_CALL = re.compile(r"\babsent(?:_over_time)?\s*\(")

# `max by (cn) (...)` and `max(...) by (cn)` are both Prometheus's spelling of
# the same aggregation, so the operator and the `by` clause are recognised
# separately rather than as one pattern.
AGGREGATION_OPERATOR = re.compile(
    r"\b(?:sum|min|max|avg|group|count|topk|bottomk|quantile)\s*[(b]"
)
BY_CLAUSE = re.compile(r"\bby\s*\(([^)]*)\)")

# A threshold comparison, in the three forms a days-remaining rule can be
# written in. Which one is in use decides the unit -- see `days_threshold`.
THRESHOLD_COMPARISON = re.compile(
    r"<=?\s*(?P<value>\d+(?:\.\d+)?)(?P<scaled>\s*\*\s*" + str(SECONDS_PER_DAY) + r")?"
)
DAY_DIVISION = re.compile(r"/\s*" + str(SECONDS_PER_DAY) + r"\b")


# --------------------------------------------------------------------------
# Reading the committed stack definition
# --------------------------------------------------------------------------


def rules_document(path: Path | None = None) -> dict:
    """The `prometheus_rules` config's inline content, parsed.

    An absent or empty config is a failure rather than an empty result: every
    assertion over the rules would otherwise pass having read nothing, which is
    the vacuous pass this suite forbids elsewhere.
    """
    target = PLATFORM_COMPOSE if path is None else path
    if RULES_CONFIG not in stack_configs(path):
        raise AssertionError(
            f"{target} declares no `{RULES_CONFIG}` config, so every alert-rule "
            f"assertion below would pass having read nothing"
        )
    content = config_content(RULES_CONFIG, path)
    if not content.strip():
        raise AssertionError(
            f"the `{RULES_CONFIG}` config in {target} carries no inline content, "
            f"so the rules Prometheus evaluates are not readable from this "
            f"repository at all"
        )
    document = yaml.safe_load(content)
    if not isinstance(document, dict):
        raise AssertionError(f"the `{RULES_CONFIG}` content does not parse as a mapping")
    return document


def alerting_rules(path: Path | None = None) -> list[dict]:
    """Every `alert:` rule the stack evaluates, as
    `{"group": ..., "alert": ..., "expr": ..., "for": ..., ...}`.

    Recording rules (a `record:` key rather than an `alert:` one) are not
    alerts and are passed over.
    """
    groups = rules_document(path).get("groups")
    if not isinstance(groups, list) or not groups:
        raise AssertionError(
            f"the `{RULES_CONFIG}` content declares no rule groups, so every "
            f"assertion over the alerts would pass having read nothing"
        )
    found: list[dict] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        rules = group.get("rules")
        if not isinstance(rules, list):
            continue
        for rule in rules:
            if isinstance(rule, dict) and rule.get("alert"):
                found.append(dict(rule, group=group.get("name")))
    if not found:
        raise AssertionError(
            f"the `{RULES_CONFIG}` content declares rule groups but no alert at "
            f"all, so it is not the alerting configuration this stack deploys"
        )
    return found


def expression(rule: dict) -> str:
    return " ".join(str(rule.get("expr") or "").split())


def rules_reading_the_expiry_metric(path: Path | None = None) -> list[dict]:
    return [rule for rule in alerting_rules(path) if METRIC_REFERENCE.search(expression(rule))]


def absence_rules(path: Path | None = None) -> list[dict]:
    """Rules reporting that the expiry measurement is no longer observable."""
    return [
        rule
        for rule in rules_reading_the_expiry_metric(path)
        if ABSENCE_CALL.search(expression(rule))
    ]


def expiry_rules(path: Path | None = None) -> list[dict]:
    """Rules reading the certificates' remaining life, as distinct from the
    companion rule reporting that the measurement has gone.

    Partitioned by re-reading each rule's own expression rather than by
    subtracting the list `absence_rules` returns: each helper parses the file
    afresh, so the two lists hold equal dictionaries that are not the same
    objects, and a subtraction by identity would silently remove nothing.
    """
    return [
        rule
        for rule in rules_reading_the_expiry_metric(path)
        if not ABSENCE_CALL.search(expression(rule))
    ]


def days_threshold(expr: str) -> float | None:
    """The remaining-days threshold an expression compares against, or None.

    Three spellings are understood, because the comparison's unit depends on
    which one is used:

        (... - time()) / 86400 < 21    -> 21 days, seconds divided into days
        ... - time() < 21 * 86400      -> 21 days, days multiplied into seconds
        ... - time() < 1814400         -> 21 days, a bare number of seconds

    Anything else returns None, and the assertion that calls this says so
    rather than passing: a threshold the test layer cannot read is not a
    threshold it has checked.
    """
    matches = list(THRESHOLD_COMPARISON.finditer(expr))
    if not matches:
        return None
    match = matches[-1]
    value = float(match.group("value"))
    if match.group("scaled"):
        return value
    if DAY_DIVISION.search(expr):
        return value
    return value / SECONDS_PER_DAY


def aggregation_labels(expr: str) -> list[str]:
    """The labels of every `by (...)` clause in an aggregating expression.

    Returns [] where no aggregation operator is present at all, so that a bare
    `by` appearing in some other construct cannot be read as an aggregation.
    """
    if not AGGREGATION_OPERATOR.search(expr):
        return []
    labels: list[str] = []
    for clause in BY_CLAUSE.findall(expr):
        labels.extend(part.strip() for part in clause.split(",") if part.strip())
    return labels


def aggregates_per_certificate(expr: str) -> bool:
    return CERTIFICATE_LABEL in aggregation_labels(expr)


def sustained_duration(rule: dict) -> str:
    """A rule's `for:` duration as written, or the empty string."""
    value = rule.get("for")
    return "" if value is None else str(value).strip()


def duration_is_immediate(value: str) -> bool:
    """Whether a `for:` duration waits for nothing. `0`, `0s`, `0m` and an
    absent value are all "fire on the first evaluation"."""
    if not value:
        return True
    return re.fullmatch(r"0+(?:[smhdwy]|ms)?", value) is not None


def scrape_job_names(path: Path | None = None) -> list[str]:
    """Every `job_name` the `prometheus_config` config declares."""
    target = PLATFORM_COMPOSE if path is None else path
    content = config_content(SCRAPE_CONFIG, path)
    if not content.strip():
        raise AssertionError(
            f"{target} declares no `{SCRAPE_CONFIG}` config with inline content, "
            f"so the scrape jobs feeding the certificate rules are not readable "
            f"from this repository"
        )
    document = yaml.safe_load(content) or {}
    jobs = document.get("scrape_configs") if isinstance(document, dict) else None
    if not isinstance(jobs, list) or not jobs:
        raise AssertionError(
            f"the `{SCRAPE_CONFIG}` content declares no `scrape_configs`, so every "
            f"assertion over the scrape jobs would pass having read nothing"
        )
    return [str(job.get("job_name")) for job in jobs if isinstance(job, dict) and job.get("job_name")]


def alertmanager_document(path: Path | None = None) -> dict:
    target = PLATFORM_COMPOSE if path is None else path
    content = config_content(ALERTMANAGER_CONFIG, path)
    if not content.strip():
        raise AssertionError(
            f"{target} declares no `{ALERTMANAGER_CONFIG}` config with inline "
            f"content, so how an alert is delivered is not readable from this "
            f"repository"
        )
    document = yaml.safe_load(content)
    if not isinstance(document, dict):
        raise AssertionError(
            f"the `{ALERTMANAGER_CONFIG}` content does not parse as a mapping"
        )
    return document


def child_routes(path: Path | None = None) -> list[dict]:
    """Every route below the top-level one, at any depth.

    The top-level route itself is excluded: it is the inherited default that
    the requirement's identification clause is defeated by, not a route of an
    alert's own.
    """
    root = alertmanager_document(path).get("route")
    if not isinstance(root, dict):
        raise AssertionError(
            f"the `{ALERTMANAGER_CONFIG}` content declares no `route:`, so every "
            f"assertion over delivery would pass having read nothing"
        )
    found: list[dict] = []
    pending = list(root.get("routes") or [])
    while pending:
        route = pending.pop(0)
        if not isinstance(route, dict):
            continue
        found.append(route)
        pending.extend(route.get("routes") or [])
    return found


def route_matchers(route: dict) -> list[str]:
    """A route's matchers, rendered as text, in either supported spelling.

    `matchers:` is the current form; `match:`/`match_re:` are the deprecated
    mappings, read too so that a route written in the older form is not
    silently taken for no route at all.
    """
    rendered: list[str] = []
    matchers = route.get("matchers")
    if isinstance(matchers, list):
        rendered.extend(str(entry) for entry in matchers)
    elif isinstance(matchers, str):
        rendered.append(matchers)
    for key in ("match", "match_re"):
        mapping = route.get(key)
        if isinstance(mapping, dict):
            rendered.extend(f"{label}={value}" for label, value in mapping.items())
    return rendered


def routes_for_alertname(name: str, path: Path | None = None) -> list[dict]:
    return [
        route
        for route in child_routes(path)
        if any("alertname" in text and name in text for text in route_matchers(route))
    ]


def route_group_by(route: dict) -> list[str]:
    value = route.get("group_by")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(entry) for entry in value]
    return []


def declared_receivers(path: Path | None = None) -> list[str]:
    receivers = alertmanager_document(path).get("receivers")
    if not isinstance(receivers, list):
        return []
    return [str(entry.get("name")) for entry in receivers if isinstance(entry, dict) and entry.get("name")]


def certificate_duration_declarations(path: Path | None = None) -> list[str]:
    """Wherever the committed file sets a certificate lifetime on the proxy.

    WHAT THIS CAN AND CANNOT SEE. It reads the proxy service's own definition
    -- its command, environment and labels -- and the inline content of every
    config the stack mounts into it. A value reaching Traefik from outside this
    file, through the uncommitted environment file the stack loads, is not
    visible to any static read and is not covered.
    """
    target = PLATFORM_COMPOSE if path is None else path
    definition = compose_services(path).get(PROXY_SERVICE)
    if not isinstance(definition, dict):
        raise AssertionError(
            f"{target} defines no `{PROXY_SERVICE}` service, so the precondition "
            f"the alert threshold rests on cannot be read at all"
        )
    found: list[str] = []
    rendered = yaml.safe_dump(definition, default_flow_style=False, sort_keys=False)
    if CERTIFICATE_DURATION_OPTION in rendered.lower():
        found.append(f"the `{PROXY_SERVICE}` service definition")
    for mount in service_config_mounts(PROXY_SERVICE, path):
        if CERTIFICATE_DURATION_OPTION in config_content(mount["source"], path).lower():
            found.append(f"the `{mount['source']}` config mounted at {mount['target']}")
    return found


def described(rules: list[dict]) -> list[str]:
    return [f"{rule.get('alert')} ({expression(rule)})" for rule in rules]


# --------------------------------------------------------------------------
# The scenarios
# --------------------------------------------------------------------------


class TestAnExpiringCertificateIsAlertedOn(unittest.TestCase):
    """ADDED requirement: An Expiring TLS Certificate Is Alerted On Before It
    Expires -- scenario "A certificate approaching expiry raises an alert".

    WHAT PASSING THIS CLASS ESTABLISHES, AND WHAT IT DOES NOT
    --------------------------------------------------------
    That the committed stack definition declares a rule of the right shape. It
    does NOT establish that the rule loads, that its expression matches a
    series Traefik actually publishes, or that a notification arrives -- a rule
    that is loaded and permanently empty is indistinguishable from a working
    one by any static read. That distinction is what the change's own
    confirmation step performs against the running stack, and nothing here
    discharges it.
    """

    def test_the_stack_definition_is_read_at_all(self) -> None:
        """DERIVED -- no scenario states it. A non-vacuity guard: every
        assertion below would pass over a file whose rules config had been
        emptied, so the read is asserted before anything is read from it."""
        rules = alerting_rules()
        self.assertTrue(
            rules,
            "the platform stack declares no alert rules at all, so no assertion "
            "about a certificate alert can mean anything",
        )

    def test_an_alert_reads_the_certificate_expiry_the_proxy_publishes(self) -> None:
        """SPECIFIED -- "an alert SHALL fire" when a certificate "is within the
        configured number of days of its expiry timestamp". The requirement
        states the alert is satisfied "by metrics the reverse proxy already
        publishes about the certificates it holds", which in this stack is
        Traefik's per-certificate expiry gauge."""
        found = expiry_rules()
        self.assertTrue(
            found,
            f"no alert rule in the platform stack reads `{EXPIRY_METRIC}`, so a "
            f"certificate approaching expiry raises nothing. The rules that do "
            f"exist are: {sorted(str(rule.get('alert')) for rule in alerting_rules())}",
        )

    def test_that_alert_waits_for_a_sustained_period(self) -> None:
        """SPECIFIED -- the scenario's "for a sustained period". A rule with no
        `for:` fires on the first evaluation that crosses the threshold, which
        a single scrape gap or a restart between scrapes is enough to
        produce."""
        rules = expiry_rules()
        self.assertTrue(
            rules,
            f"no alert rule reads `{EXPIRY_METRIC}`, so there is no alert whose "
            f"evaluation period could be checked -- stated rather than passing "
            f"over an empty list, so this assertion cannot report success having "
            f"read no rule at all",
        )
        offenders = [
            f"{rule.get('alert')} (for: {sustained_duration(rule) or '<absent>'})"
            for rule in rules
            if duration_is_immediate(sustained_duration(rule))
        ]
        self.assertEqual(
            [],
            offenders,
            f"these certificate-expiry alerts fire on the first evaluation rather "
            f"than over a sustained period: {offenders}",
        )

    def test_that_alert_names_the_certificate_rather_than_describing_it_generically(self) -> None:
        """SPECIFIED -- "identifying that certificate by the hostname it was
        issued for", and the requirement's "SHALL identify which certificate is
        affected". An annotation that says a certificate is expiring without
        saying which one leaves the recipient with the same question they
        started with.

        Read as a substring of the rendered annotations rather than as an exact
        template, because the surrounding Compose block escapes a Go template
        variable's `$` and this assertion is about which label is named, not
        about how the file escapes it.
        """
        rules = expiry_rules()
        self.assertTrue(
            rules,
            f"no alert rule reads `{EXPIRY_METRIC}`, so there is no annotation to "
            f"check for the certificate's identity",
        )
        offenders = []
        for rule in rules:
            annotations = rule.get("annotations")
            rendered = yaml.safe_dump(annotations or {}, sort_keys=False)
            if f"labels.{CERTIFICATE_LABEL}" not in rendered:
                offenders.append(f"{rule.get('alert')}: {' '.join(rendered.split())}")
        self.assertEqual(
            [],
            offenders,
            f"these certificate-expiry alerts carry no annotation naming the "
            f"`{CERTIFICATE_LABEL}` label, so the notification a recipient "
            f"receives describes the failure without identifying the certificate: "
            f"{offenders}",
        )


class TestTheThresholdLeavesNormalRenewalAlone(unittest.TestCase):
    """ADDED requirement: An Expiring TLS Certificate Is Alerted On Before It
    Expires -- scenario "A certificate renewing normally raises no alert", and
    the requirement's second normative paragraph: "The threshold SHALL be
    strictly less than the lead time at which the reverse proxy begins renewing
    a certificate on its own".

    WHERE THE 30 COMES FROM. It is Traefik's documented default renewal lead
    time -- it begins renewing 30 days before expiry -- and it applies to this
    stack only because the stack sets no `certificatesDuration` on its ACME
    resolver. That precondition is asserted below rather than assumed, so the
    constant is checked rather than reproduced by hand from an upstream
    document. Being an upstream default, it can move under a Traefik upgrade
    with nothing in this repository changing; these assertions establish that
    the committed threshold is below the lead time Traefik documented when they
    were written, and not that Traefik still renews at 30 days.
    """

    def test_the_alert_threshold_is_strictly_below_the_renewal_lead_time(self) -> None:
        """SPECIFIED -- the requirement's second normative paragraph, and the
        scenario "the threshold leaves normal renewal strictly more lead time
        than the alert requires". A threshold at or above the renewal lead time
        fires on every ordinary renewal, which is the opposite of what the
        requirement asks the alert to report."""
        rules = expiry_rules()
        self.assertTrue(
            rules,
            f"no alert rule reads `{EXPIRY_METRIC}`, so there is no threshold to "
            f"compare against the renewal lead time",
        )
        unreadable = []
        offenders = []
        for rule in rules:
            threshold = days_threshold(expression(rule))
            if threshold is None:
                unreadable.append(f"{rule.get('alert')} ({expression(rule)})")
            elif threshold >= RENEWAL_LEAD_TIME_DAYS:
                offenders.append(f"{rule.get('alert')} fires at {threshold:g} days remaining")
        self.assertEqual(
            [],
            unreadable,
            f"the remaining-days threshold of these rules could not be read, so it "
            f"has not been checked against the {RENEWAL_LEAD_TIME_DAYS}-day renewal "
            f"lead time: {unreadable}. `days_threshold` understands a comparison "
            f"in days (dividing by {SECONDS_PER_DAY}), in seconds scaled by "
            f"{SECONDS_PER_DAY}, and in bare seconds -- either write the rule in "
            f"one of those, or widen the helper deliberately",
        )
        self.assertEqual(
            [],
            offenders,
            f"these rules fire at or above Traefik's {RENEWAL_LEAD_TIME_DAYS}-day "
            f"renewal lead time: {offenders}. At that threshold the alert reports a "
            f"renewal that has not happened YET rather than one that did not "
            f"happen, which the requirement forbids outright",
        )

    def test_the_stack_leaves_the_certificate_duration_unset(self) -> None:
        """DERIVED -- no scenario states it; it is the precondition that makes
        the constant above the real renewal lead time rather than an upstream
        default reproduced by hand. Traefik derives its renewal lead time from
        `certificatesDuration`, so setting that option moves the number the
        threshold is required to stay below while leaving the threshold, and
        every other assertion here, silently unchanged."""
        found = certificate_duration_declarations()
        self.assertEqual(
            [],
            found,
            f"the stack now sets a certificate duration on `{PROXY_SERVICE}` "
            f"({found}), so Traefik's default {RENEWAL_LEAD_TIME_DAYS}-day renewal "
            f"lead time is no longer the lead time the alert threshold is stated "
            f"against. Either drop the option, or restate "
            f"RENEWAL_LEAD_TIME_DAYS against the lead time the new duration "
            f"produces and re-check the committed threshold against it",
        )

    def test_the_provenance_of_the_renewal_lead_time_is_still_recorded(self) -> None:
        """DERIVED -- no scenario states it. The constant is an upstream
        default conditioned on a repository setting; a reader who meets it
        without that context has no way to tell a checked number from an
        invented one, and no way to know which assertion checks its
        precondition. A record nobody can delete without a test failing is the
        only durable form of it."""
        recorded = " ".join((type(self).__doc__ or "").split()).lower()
        for phrase in ("traefik", "renewal lead time", "certificatesduration", "upstream"):
            with self.subTest(phrase=phrase):
                self.assertIn(
                    phrase,
                    recorded,
                    f"the class no longer records where the "
                    f"{RENEWAL_LEAD_TIME_DAYS}-day constant comes from, so the "
                    f"threshold assertion now reads as checking a number of this "
                    f"project's own choosing",
                )


class TestASupersededCertificateCannotFireAgainstAHealthyHostname(unittest.TestCase):
    """ADDED requirement: An Expiring TLS Certificate Is Alerted On Before It
    Expires -- scenario "A superseded certificate does not raise an alert
    against a healthy hostname".
    """

    def test_the_expression_aggregates_per_certificate(self) -> None:
        """SPECIFIED -- the scenario: where "a record of the superseded
        certificate's earlier expiry remains observable", no alert fires for
        that hostname on its account. The metric carries a per-certificate
        `serial` label as well as `cn`, so a rule reading the raw series would
        cross the threshold on the superseded record and fire against a
        hostname whose live certificate is healthy. Taking the newest expiry
        per hostname is what makes the scenario true regardless of whether the
        superseded series lingers."""
        rules = expiry_rules()
        self.assertTrue(
            rules,
            f"no alert rule reads `{EXPIRY_METRIC}`, so there is no expression to "
            f"check for per-certificate aggregation",
        )
        offenders = [
            f"{rule.get('alert')} ({expression(rule)})"
            for rule in rules
            if not aggregates_per_certificate(expression(rule))
        ]
        self.assertEqual(
            [],
            offenders,
            f"these rules read the raw series rather than aggregating it by "
            f"`{CERTIFICATE_LABEL}`: {offenders}. A superseded certificate's "
            f"series, if it lingers after a renewal, would cross the threshold and "
            f"fire against a hostname that is perfectly healthy",
        )


class TestSeveralCertificatesAreEachIdentifiedOnDelivery(unittest.TestCase):
    """ADDED requirement: An Expiring TLS Certificate Is Alerted On Before It
    Expires -- scenario "Several certificates approaching expiry are each
    identified".

    WHY DELIVERY IS ASSERTED AND NOT JUST THE RULE. The scenario's obligation
    is over "a notification that is delivered", not over the alerts that fire.
    The stack's Slack receiver renders the annotations common to every alert in
    a notification group, and annotations naming a per-certificate label are
    not common once two certificates group together -- so under the inherited
    grouping the alert fires correctly and the notification names neither
    hostname. Grouping the alert's own route by the certificate label is what
    makes the scenario true.

    WHAT THIS CANNOT ESTABLISH. That a real multi-certificate notification
    arrives naming both hostnames. That needs two certificates actually
    approaching expiry together; no static read can produce one. These
    assertions establish the configuration under which that outcome follows.
    """

    def setUp(self) -> None:
        self.rules = expiry_rules()
        self.assertTrue(
            self.rules,
            f"no alert rule reads `{EXPIRY_METRIC}`, so there is no alert whose "
            f"delivery could be checked",
        )

    def test_the_alert_has_a_route_of_its_own(self) -> None:
        """SPECIFIED -- the scenario's "rather than the group collapsing into a
        single notification that names none". Under the top-level route alone
        that collapse is what happens, so a route matching this alert is the
        first thing the scenario needs."""
        offenders = []
        for rule in self.rules:
            name = str(rule.get("alert"))
            if not routes_for_alertname(name):
                offenders.append(name)
        self.assertEqual(
            [],
            offenders,
            f"these certificate alerts are matched by no route of their own, so "
            f"they are delivered under the inherited grouping: {offenders}. The "
            f"routes that exist match: "
            f"{[route_matchers(route) for route in child_routes()]}",
        )

    def test_that_route_groups_by_the_certificate_as_well_as_the_alertname(self) -> None:
        """SPECIFIED -- the scenario: "each affected hostname SHALL be named in
        a notification that is delivered". Grouping by the certificate label
        puts each certificate in a notification group of its own, which is what
        leaves each notification in possession of the annotation naming its
        hostname."""
        offenders = []
        for rule in self.rules:
            name = str(rule.get("alert"))
            for route in routes_for_alertname(name):
                grouping = route_group_by(route)
                if CERTIFICATE_LABEL not in grouping:
                    offenders.append(f"{name} -> group_by: {grouping or '<inherited>'}")
        self.assertEqual(
            [],
            offenders,
            f"these routes do not group by `{CERTIFICATE_LABEL}`: {offenders}. Two "
            f"certificates crossing the threshold together would then land in one "
            f"group, their differing annotations would drop out of the common set "
            f"the Slack receiver renders, and the notification would name neither "
            f"hostname",
        )

    def test_that_route_delivers_to_a_receiver_the_configuration_declares(self) -> None:
        """DERIVED -- no scenario states it, but the scenario's obligation is
        over a notification that is DELIVERED, and a route naming a receiver
        that does not exist delivers nothing. A route naming no receiver at all
        inherits the parent's and is correct, so only a named-but-undeclared
        receiver is an offence here."""
        declared = declared_receivers()
        self.assertTrue(
            declared,
            "the alerting configuration declares no receivers at all, so nothing "
            "it routes can be delivered anywhere",
        )
        offenders = []
        for rule in self.rules:
            name = str(rule.get("alert"))
            for route in routes_for_alertname(name):
                receiver = route.get("receiver")
                if receiver is not None and str(receiver) not in declared:
                    offenders.append(f"{name} -> receiver: {receiver}")
        self.assertEqual(
            [],
            offenders,
            f"these routes name a receiver the configuration does not declare: "
            f"{offenders}. Declared receivers are {sorted(declared)}",
        )


class TestExpiryNoLongerBeingObservedRaisesAnAlert(unittest.TestCase):
    """ADDED requirement: An Expiring TLS Certificate Is Alerted On Before It
    Expires -- scenario "Certificate expiry no longer being observed raises an
    alert".

    The scenario names two ways the measurement can go: the source becoming
    unreachable, and the source staying up while no longer publishing the
    measurement. They need different answers, and this class holds the static
    half of each. The first is reported at runtime by the existing
    unreachable-source alert, whose cover depends on the scrape job continuing
    to be declared -- so that declaration is asserted here. The second leaves
    the scrape job intact and the source up, and is reported by a rule of its
    own.
    """

    def test_a_rule_reports_the_measurement_no_longer_being_published(self) -> None:
        """SPECIFIED -- the scenario's second limb, "it remains reachable but
        no longer publishes that measurement", and its "rather than the
        certificate alert silently evaluating an empty result and never firing
        again". A threshold rule over a metric that has stopped existing
        returns an empty vector, which never fires and never complains."""
        found = absence_rules()
        self.assertTrue(
            found,
            f"no alert rule reports the absence of `{EXPIRY_METRIC}`, so a Traefik "
            f"upgrade that renamed or dropped it would leave the certificate alert "
            f"evaluating nothing, forever, in silence. The rules reading that "
            f"metric are: {described(rules_reading_the_expiry_metric())}",
        )

    def test_that_rule_covers_the_label_the_expiry_alert_reads(self) -> None:
        """DERIVED -- the scenario says the measurement stopping is reported;
        it does not say by which matcher. This traces to that change's design,
        which records the label as a second route to the same silence: the
        expiry rule aggregates by the certificate label, so an upgrade renaming
        that label collapses every series into one group with an empty label
        and masks a hostname genuinely days from expiry behind a healthy
        sibling. Matching on the label being non-empty is what makes the one
        rule cover both."""
        rules = absence_rules()
        self.assertTrue(
            rules,
            f"no rule reports the absence of `{EXPIRY_METRIC}` at all, so there is "
            f"no matcher to check",
        )
        offenders = [
            f"{rule.get('alert')} ({expression(rule)})"
            for rule in rules
            if CERTIFICATE_LABEL not in expression(rule)
        ]
        self.assertEqual(
            [],
            offenders,
            f"these absence rules do not mention the `{CERTIFICATE_LABEL}` label: "
            f"{offenders}. They report the metric disappearing but not the label "
            f"the expiry rule aggregates on disappearing, which silences the alert "
            f"just as completely and turns a false positive into a false negative",
        )

    def test_that_rule_waits_before_reporting(self) -> None:
        """DERIVED -- no scenario states a duration. Without one, the rule
        fires during any redeploy or Traefik restart in which the metric has
        not yet been scraped, which is a routine event: an absence alert that
        fires on every deploy is one that gets muted."""
        rules = absence_rules()
        self.assertTrue(
            rules,
            f"no rule reports the absence of `{EXPIRY_METRIC}` at all, so there is "
            f"no duration to check",
        )
        offenders = [
            f"{rule.get('alert')} (for: {sustained_duration(rule) or '<absent>'})"
            for rule in rules
            if duration_is_immediate(sustained_duration(rule))
        ]
        self.assertEqual(
            [],
            offenders,
            f"these absence rules fire on the first evaluation with no series: "
            f"{offenders}. A restart or a redeploy between scrapes is enough to "
            f"produce that",
        )

    def test_the_scrape_job_feeding_both_rules_is_still_declared(self) -> None:
        """SPECIFIED -- the scenario's first limb, "the source publishing it
        has become unreachable". That case is reported at runtime by the
        existing unreachable-source alert over this job; deleting the job would
        remove that cover AND disarm both rules above at once, with nothing
        turning red. This is the static half of the scenario."""
        jobs = scrape_job_names()
        self.assertIn(
            SCRAPE_JOB,
            jobs,
            f"the `{SCRAPE_JOB}` scrape job is no longer declared, so "
            f"`{EXPIRY_METRIC}` is not collected, the certificate rules evaluate "
            f"nothing, and the unreachable-source alert has no target to report on. "
            f"Declared jobs are {sorted(jobs)}",
        )


class TestEveryCertificateAlertCarriesADurationAndASeverity(unittest.TestCase):
    """ADDED requirement: An Expiring TLS Certificate Is Alerted On Before It
    Expires.

    DERIVED as a class -- no scenario states a severity. It is here so a rule
    added later over the same metric cannot arrive without the two properties
    every other alert in this stack carries: a rule with no severity is routed
    and rendered differently from its siblings, and a rule with no `for:` fires
    on a single scrape artefact.
    """

    def test_every_rule_reading_the_expiry_metric_declares_a_severity(self) -> None:
        """DERIVED -- traces to that change's design, which records that every
        rule in this stack uses one severity tier and that introducing another
        would be a routing change this change is not."""
        rules = rules_reading_the_expiry_metric()
        self.assertTrue(
            rules,
            f"no alert rule reads `{EXPIRY_METRIC}`, so this class is checking "
            f"nothing",
        )
        offenders = []
        for rule in rules:
            labels = rule.get("labels")
            severity = labels.get("severity") if isinstance(labels, dict) else None
            if not severity:
                offenders.append(str(rule.get("alert")))
        self.assertEqual(
            [],
            offenders,
            f"these certificate rules carry no `severity` label: {offenders}",
        )

    def test_every_rule_reading_the_expiry_metric_waits_for_a_duration(self) -> None:
        """DERIVED -- the same guard over `for:`, applied to every rule reading
        the metric rather than to the two this change adds, so that a third one
        added later is caught by the rule that already exists."""
        rules = rules_reading_the_expiry_metric()
        self.assertTrue(
            rules,
            f"no alert rule reads `{EXPIRY_METRIC}`, so this class is checking "
            f"nothing",
        )
        offenders = [
            str(rule.get("alert"))
            for rule in rules
            if duration_is_immediate(sustained_duration(rule))
        ]
        self.assertEqual(
            [],
            offenders,
            f"these certificate rules declare no `for:` duration: {offenders}",
        )


# --------------------------------------------------------------------------
# Discrimination
# --------------------------------------------------------------------------


DEFAULT_EXPIRY_ALERT = "TLSCertificateExpiringSoon"
DEFAULT_ABSENCE_ALERT = "TLSCertificateExpiryNotObserved"
DEFAULT_EXPIRY_EXPR = (
    f"(max by ({CERTIFICATE_LABEL}) ({EXPIRY_METRIC}) - time()) / {SECONDS_PER_DAY} < 21"
)
DEFAULT_ABSENCE_EXPR = f'absent({EXPIRY_METRIC}{{{CERTIFICATE_LABEL}!=""}})'


class TestTheseAssertionsAreARealReadOfTheFile(unittest.TestCase):
    """ADDED requirement: An Expiring TLS Certificate Is Alerted On Before It
    Expires.

    Every class above would pass identically against helpers that returned a
    fixed answer and read nothing. These run the same helpers over throwaway
    stack definitions differing from a satisfying one in exactly one property,
    and assert the verdict differs -- which is also what lets these assertions
    be exercised before any implementation of the change exists. Without them
    the classes above would sit in the state where the target is merely absent,
    establishing nothing about whether the assertions discriminate.

    The fixtures are built from scratch rather than copied from the committed
    file, so nothing here depends on what that file happens to contain today.
    """

    def compose_fixture(
        self,
        *,
        expiry_expr: str | None = DEFAULT_EXPIRY_EXPR,
        expiry_for: str = "1h",
        expiry_summary: str = "certificate for {{ $labels.cn }} expires soon",
        expiry_severity: str = "warning",
        absence_expr: str | None = DEFAULT_ABSENCE_EXPR,
        absence_for: str = "15m",
        route_group_by_labels: list[str] | None = None,
        route_receiver: str = "slack",
        scrape_jobs: tuple[str, ...] = (SCRAPE_JOB, "prometheus"),
        proxy_command: list[str] | None = None,
    ) -> Path:
        """A minimal stack definition carrying exactly the four things these
        assertions read: a proxy service, a scrape config, a rules config and
        an alerting config."""
        rules: list[dict] = []
        if expiry_expr is not None:
            rule: dict = {"alert": DEFAULT_EXPIRY_ALERT, "expr": expiry_expr}
            if expiry_for:
                rule["for"] = expiry_for
            if expiry_severity:
                rule["labels"] = {"severity": expiry_severity}
            rule["annotations"] = {"summary": expiry_summary}
            rules.append(rule)
        if absence_expr is not None:
            absent_rule: dict = {"alert": DEFAULT_ABSENCE_ALERT, "expr": absence_expr}
            if absence_for:
                absent_rule["for"] = absence_for
            absent_rule["labels"] = {"severity": "warning"}
            absent_rule["annotations"] = {"summary": "certificate expiry is not observable"}
            rules.append(absent_rule)

        grouping = ["alertname", CERTIFICATE_LABEL] if route_group_by_labels is None else route_group_by_labels
        alertmanager = {
            "route": {
                "receiver": "slack",
                "group_by": ["alertname"],
                "repeat_interval": "4h",
                "routes": [
                    {"matchers": ['alertname="Watchdog"'], "receiver": "deadmansswitch"},
                    {
                        "matchers": [f'alertname="{DEFAULT_EXPIRY_ALERT}"'],
                        "receiver": route_receiver,
                        "group_by": grouping,
                        "repeat_interval": "24h",
                    },
                ],
            },
            "receivers": [{"name": "slack"}, {"name": "deadmansswitch"}],
        }
        scrape = {
            "scrape_configs": [
                {"job_name": job, "static_configs": [{"targets": [f"{job}:8082"]}]}
                for job in scrape_jobs
            ]
        }
        proxy: dict = {"image": "traefik:v3.7.13"}
        if proxy_command:
            proxy["command"] = proxy_command
        document = {
            "services": {
                PROXY_SERVICE: proxy,
                "prometheus": {
                    "image": "prom/prometheus:v3.7.3",
                    "configs": [
                        {"source": SCRAPE_CONFIG, "target": "/etc/prometheus/prometheus.yml"},
                        {"source": RULES_CONFIG, "target": "/etc/prometheus/rules.yml"},
                    ],
                },
            },
            "configs": {
                SCRAPE_CONFIG: {"content": yaml.safe_dump(scrape, sort_keys=False)},
                RULES_CONFIG: {
                    "content": yaml.safe_dump(
                        {"groups": [{"name": "platform-monitoring", "rules": rules}]},
                        sort_keys=False,
                    )
                },
                ALERTMANAGER_CONFIG: {"content": yaml.safe_dump(alertmanager, sort_keys=False)},
            },
        }
        directory = Path(tempfile.mkdtemp(prefix="certificate-alert-fixture-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "docker-compose.yml"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return path

    def test_a_stack_satisfying_every_property_is_accepted(self) -> None:
        """DERIVED -- the converse half, and the one that makes the rest
        readable. Without it, helpers that reported every stack as offending
        would satisfy every discrimination test below while failing the
        committed file no matter what it said."""
        fixture = self.compose_fixture()
        expiry = expiry_rules(fixture)
        self.assertEqual(1, len(expiry), described(expiry))
        self.assertEqual(21, days_threshold(expression(expiry[0])))
        self.assertTrue(aggregates_per_certificate(expression(expiry[0])))
        self.assertEqual("1h", sustained_duration(expiry[0]))
        self.assertEqual(1, len(absence_rules(fixture)))
        self.assertIn(SCRAPE_JOB, scrape_job_names(fixture))
        self.assertEqual([], certificate_duration_declarations(fixture))
        routes = routes_for_alertname(DEFAULT_EXPIRY_ALERT, fixture)
        self.assertEqual(1, len(routes))
        self.assertIn(CERTIFICATE_LABEL, route_group_by(routes[0]))

    def test_removing_the_expiry_rule_is_caught(self) -> None:
        """SPECIFIED -- the discriminating half of scenario "A certificate
        approaching expiry raises an alert"."""
        fixture = self.compose_fixture(expiry_expr=None)
        self.assertEqual(
            [],
            expiry_rules(fixture),
            "a stack with no expiry rule was reported as having one, so the "
            "assertion above does not read the file",
        )

    def test_a_threshold_raised_to_the_renewal_lead_time_is_caught(self) -> None:
        """SPECIFIED -- the discriminating half of scenario "A certificate
        renewing normally raises no alert". The threshold is the one number the
        requirement bounds, and 30 is the exact value it forbids: at the
        renewal lead time itself the alert fires on every ordinary renewal."""
        raised = DEFAULT_EXPIRY_EXPR.replace("< 21", f"< {RENEWAL_LEAD_TIME_DAYS}")
        fixture = self.compose_fixture(expiry_expr=raised)
        threshold = days_threshold(expression(expiry_rules(fixture)[0]))
        self.assertEqual(float(RENEWAL_LEAD_TIME_DAYS), threshold)
        self.assertFalse(
            threshold < RENEWAL_LEAD_TIME_DAYS,
            f"a threshold of {threshold} was accepted as strictly below the "
            f"{RENEWAL_LEAD_TIME_DAYS}-day renewal lead time",
        )

    def test_the_threshold_is_read_in_each_form_its_unit_can_be_written_in(self) -> None:
        """DERIVED -- no scenario states a spelling. Without this, a rule
        written in seconds would return an unreadably large "days" figure and
        pass the bound while firing 21 times too late, or the helper would
        return None and the assertion would fail for a reason unrelated to the
        threshold."""
        cases = {
            f"({EXPIRY_METRIC} - time()) / {SECONDS_PER_DAY} < 21": 21,
            f"{EXPIRY_METRIC} - time() < 21 * {SECONDS_PER_DAY}": 21,
            f"{EXPIRY_METRIC} - time() < {21 * SECONDS_PER_DAY}": 21,
            f"({EXPIRY_METRIC} - time()) / {SECONDS_PER_DAY} <= 20.5": 20.5,
        }
        for expr, expected in cases.items():
            with self.subTest(expr=expr):
                self.assertEqual(expected, days_threshold(expr))
        self.assertIsNone(
            days_threshold(f"{EXPIRY_METRIC} - time() < some_other_series"),
            "a comparison with no numeric threshold was read as a threshold, so a "
            "rule the helper cannot understand would pass unchecked",
        )

    def test_removing_the_per_certificate_aggregation_is_caught(self) -> None:
        """SPECIFIED -- the discriminating half of scenario "A superseded
        certificate does not raise an alert against a healthy hostname"."""
        flattened = f"({EXPIRY_METRIC} - time()) / {SECONDS_PER_DAY} < 21"
        fixture = self.compose_fixture(expiry_expr=flattened)
        self.assertFalse(
            aggregates_per_certificate(expression(expiry_rules(fixture)[0])),
            "an expression reading the raw series was reported as aggregating per "
            "certificate",
        )
        self.assertFalse(
            aggregates_per_certificate(f"sum by (job) ({EXPIRY_METRIC}) - time() < 21"),
            "an expression aggregating by some other label was reported as "
            "aggregating per certificate",
        )

    def test_a_route_grouped_by_alertname_alone_is_caught(self) -> None:
        """SPECIFIED -- the discriminating half of scenario "Several
        certificates approaching expiry are each identified". This is the exact
        edit the scenario exists to forbid: the route survives, and the
        notification stops naming anything."""
        fixture = self.compose_fixture(route_group_by_labels=["alertname"])
        routes = routes_for_alertname(DEFAULT_EXPIRY_ALERT, fixture)
        self.assertEqual(1, len(routes))
        self.assertNotIn(
            CERTIFICATE_LABEL,
            route_group_by(routes[0]),
            "a route grouping by alertname alone was reported as grouping per "
            "certificate",
        )

    def test_an_alert_with_no_route_of_its_own_is_caught(self) -> None:
        """SPECIFIED -- the other half of the same scenario: the route being
        deleted outright rather than narrowed."""
        fixture = self.compose_fixture(expiry_expr=DEFAULT_EXPIRY_EXPR)
        self.assertEqual(
            [],
            routes_for_alertname("SomeAlertWithNoRoute", fixture),
            "a route was reported for an alertname no route matches",
        )

    def test_a_route_in_the_deprecated_matcher_form_is_still_found(self) -> None:
        """DERIVED -- no scenario states a spelling. Alertmanager accepts
        `match:` as well as `matchers:`; a reader that saw only the newer form
        would report a correctly routed alert as unrouted, which is a false
        failure rather than a false pass, but an equally useless verdict."""
        route = {"match": {"alertname": DEFAULT_EXPIRY_ALERT}}
        self.assertEqual(
            [f"alertname={DEFAULT_EXPIRY_ALERT}"],
            route_matchers(route),
        )

    def test_removing_the_absence_rule_is_caught(self) -> None:
        """SPECIFIED -- the discriminating half of scenario "Certificate expiry
        no longer being observed raises an alert"."""
        fixture = self.compose_fixture(absence_expr=None)
        self.assertEqual(
            [],
            absence_rules(fixture),
            "a stack with no absence rule was reported as having one",
        )

    def test_an_absence_rule_that_ignores_the_certificate_label_is_caught(self) -> None:
        """DERIVED -- the discriminating half of the label-rename limb. A rule
        on the bare metric name still reports the metric vanishing, so the test
        above would pass while the second route to the same silence stayed
        open."""
        fixture = self.compose_fixture(absence_expr=f"absent({EXPIRY_METRIC})")
        rule = absence_rules(fixture)[0]
        self.assertNotIn(
            CERTIFICATE_LABEL,
            expression(rule),
            "a rule on the bare metric name was reported as covering the label the "
            "expiry rule aggregates on",
        )

    def test_removing_the_scrape_job_is_caught(self) -> None:
        """SPECIFIED -- the discriminating half of the scenario's first limb.
        Deleting the job is the edit that disarms both rules while leaving them
        in the file, looking exactly as they do when they work."""
        fixture = self.compose_fixture(scrape_jobs=("prometheus",))
        self.assertNotIn(
            SCRAPE_JOB,
            scrape_job_names(fixture),
            "a stack that scrapes the proxy nowhere was reported as scraping it",
        )

    def test_a_certificate_duration_added_to_the_proxy_is_caught(self) -> None:
        """DERIVED -- the discriminating half of the precondition the threshold
        constant rests on."""
        fixture = self.compose_fixture(
            proxy_command=[
                "--certificatesresolvers.letsencrypt.acme.certificatesDuration=1440",
            ]
        )
        self.assertEqual(
            [f"the `{PROXY_SERVICE}` service definition"],
            certificate_duration_declarations(fixture),
            "a certificate duration set on the proxy's command line was not found, "
            "so the threshold's precondition is asserted over a read that does not "
            "see it",
        )

    def test_an_alert_missing_its_duration_or_severity_is_caught(self) -> None:
        """DERIVED -- the discriminating half of the two standing guards."""
        fixture = self.compose_fixture(expiry_for="", expiry_severity="")
        rule = expiry_rules(fixture)[0]
        self.assertTrue(duration_is_immediate(sustained_duration(rule)))
        self.assertIsNone(rule.get("labels"))
        for value in ("0", "0s", "0m", ""):
            with self.subTest(value=value):
                self.assertTrue(duration_is_immediate(value))
        for value in ("1h", "15m", "30s"):
            with self.subTest(value=value):
                self.assertFalse(duration_is_immediate(value))

    def test_a_rules_config_with_no_rules_fails_rather_than_reading_nothing(self) -> None:
        """DERIVED -- the file-level non-vacuity guard, matching the one this
        suite's store census already applies. A stack whose rules config was
        emptied must fail loudly rather than report no offences."""
        fixture = self.compose_fixture(expiry_expr=None, absence_expr=None)
        with self.assertRaises(AssertionError):
            alerting_rules(fixture)

    def test_a_stack_declaring_none_of_the_configs_fails_rather_than_reading_nothing(self) -> None:
        """DERIVED -- the same guard one level up: the configs themselves
        going missing, rather than their content losing a rule."""
        directory = Path(tempfile.mkdtemp(prefix="certificate-alert-fixture-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "docker-compose.yml"
        path.write_text(
            yaml.safe_dump({"services": {PROXY_SERVICE: {"image": "traefik:v3.7.13"}}}),
            encoding="utf-8",
        )
        for reader in (alerting_rules, scrape_job_names, alertmanager_document):
            with self.subTest(reader=reader.__name__):
                with self.assertRaises(AssertionError):
                    reader(path)

    def test_the_committed_file_is_the_one_these_assertions_read(self) -> None:
        """DERIVED -- no scenario states it. Every test above runs against a
        fixture; this is what ties the classes above to the file the pipeline
        actually deploys, so a helper defaulting to somewhere else would be
        visible."""
        self.assertEqual(
            ROOT / "platform" / "docker-compose.yml",
            PLATFORM_COMPOSE,
            "the assertions in this file no longer read the stack definition the "
            "platform deploy workflow deploys",
        )
        self.assertTrue(
            PLATFORM_COMPOSE.is_file(),
            f"{PLATFORM_COMPOSE} does not exist, so every assertion above is "
            f"failing for a reason unrelated to the alert",
        )


if __name__ == "__main__":
    unittest.main()
