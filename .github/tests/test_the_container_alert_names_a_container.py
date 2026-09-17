"""Static-assertion tests for scoping the container restart/OOM alert to real
containers.

Derived from the delta specification of the OpenSpec change
`scope-the-restart-alert-to-real-containers`, before any implementation of that
change existed -- from that delta at commit `60e17eb`, the commit holding the
approved plan. The path that delta sits at is not written here: a change's
artifacts move when it is archived, and this repository's citation convention is
to name the change and the artifact in prose instead.

The delta modifies one requirement of `iac-platform-services` -- *Metrics-Based
Alerting Covers Host and Service Health*, held in
`openspec/specs/iac-platform-services/spec.md`. Each class below names the
scenario it traces to, and every assertion is annotated SPECIFIED (it traces to
SHALL text or to a scenario in the delta spec) or DERIVED (it traces to that
change's `design.md` or `tasks.md` rather than to a scenario), following the
convention `test_ci_configuration.py` states for itself. See that change's
`test-plan.md` for the scenario-to-test mapping, the baseline, the assertions
that pass from the moment they are written, and the obsolete-test search.

Why this suite and not another
------------------------------
Every property here is a static read of one committed file --
`platform/docker-compose.yml`, whose `prometheus_rules` config entry the
platform deploy workflow deploys. AGENTS.md's testing table routes exactly that
to this suite: the change touches no Terraform module and no Ansible role, so
neither `terraform test` nor Molecule can hold it. Nothing here opens a network
connection, reads a credential, spawns a container runtime or a Terraform
binary, and it adds no dependency beyond PyYAML, which
`.github/requirements-ci.txt` already pins.

Why this is a new module rather than a section of an existing one
-----------------------------------------------------------------
These tests were written by an author other than whoever implements the change,
from the delta spec rather than from the rule, and that author may only add.
Folding this file into `test_ci_configuration.py` or into
`test_certificate_expiry_alerting.py` afterwards is a reviewable move rather
than an authoring decision. Nothing in this file edits, deletes or disables an
existing test.

The two duration helpers below restate rather than import their twins in
`test_certificate_expiry_alerting.py`, deliberately: that module belongs to a
different change and is itself a fold candidate, and a four-line predicate is a
cheaper thing to duplicate than an import a fold would break. Everything that
locates the committed file -- `ROOT`, `PLATFORM_COMPOSE`, `stack_configs`,
`config_content` -- is imported from `test_ci_configuration.py` rather than
restated, which is the idiom this directory already uses.

Why the `$$` is undone before anything is parsed
------------------------------------------------
The Compose file escapes a literal `$` as `$$`, so that Compose's own variable
interpolation leaves a Go template alone. A reader meeting
`{{ $$labels.name }}` will otherwise take it for a typo. `rules_content` below
undoes that doubling, so what these assertions read is the rule file Prometheus
loads rather than the Compose file's rendering of it -- and
`test_the_compose_escaping_is_undone_before_the_rules_are_read` establishes that
the undoing happens.

What no assertion here establishes
----------------------------------
Not that Prometheus evaluates the narrowed rule the way the delta's scenarios
describe. A static read of a committed file cannot show that a control group
which is not a container raises nothing at runtime: that needs a Prometheus
evaluating real series, and this suite may spawn neither Prometheus nor a
container runtime. The change's own confirmation step performs that against the
deployed staging host, and nothing here discharges it.

Nor that the alert would be delivered. Routing and receivers are another
requirement's subject and are untouched by this change.

Runner
------
    python3 -m unittest discover --start-directory .github/tests

    # or a single test, individually selectable:
    python3 -m unittest \\
        test_the_container_alert_names_a_container.TestAControlGroupThatIsNotAContainerRaisesNoContainerAlert \\
        .test_the_restart_half_selects_only_series_carrying_a_container_name

Run from the repository root. Discovery puts `.github/tests` on `sys.path`,
which is what makes the sibling import below resolve.
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
    config_content,
    stack_configs,
)

# --------------------------------------------------------------------------
# iac-platform-services / Metrics-Based Alerting Covers Host and Service Health
#
# Identifiers this section names. A static read of a committed file cannot
# avoid naming what it reads, so each name below is a constraint of the test
# layer, not a property the requirement states. The requirement speaks of
# "container crash-looping or repeated restarts", "container out-of-memory
# kills", "host resource pressure" and "series that identify a container";
# these are what those resolve to in this stack.
# --------------------------------------------------------------------------

RULES_CONFIG = "prometheus_rules"

# cAdvisor's two counters. The first reports a container's start time, so a
# crash-loop shows as repeated changes in it; the second counts OOM kills.
RESTART_METRIC = "container_start_time_seconds"
OOM_METRIC = "container_oom_events_total"

# Every series cAdvisor exports under this prefix is reported per control
# group. Only a Docker container has a Docker name to report, so this is the
# label that separates a container from a control group that is not one.
CONTAINER_METRIC_PREFIX = "container_"
CONTAINER_NAME_LABEL = "name"

# WHY THE RULE IS LOCATED BY THE METRICS IT READS RATHER THAN BY ITS NAME.
# The delta's normative sentence binds "an alert rule whose subject is a
# container", not one named rule, and a rename would take a name-based read
# with it while leaving the defect in place. `ContainerRestartingOrOOMKilled`
# is what that resolves to in the committed file today; it is named below only
# so a fixture and a failure message can orient a reader, and no assertion
# requires it.
RESTART_ALERT = "ContainerRestartingOrOOMKilled"

# The families the other three scenarios read. Named rather than matched
# loosely, so a failure says which resource went unwatched.
ERROR_RATE_METRIC_PREFIX = "traefik_router_requests_total"
DISK_METRIC_PREFIX = "node_filesystem_"
CPU_METRIC_PREFIX = "node_cpu_"
MEMORY_METRIC_PREFIX = "node_memory_"
SCRAPE_HEALTH_METRIC = "up"

IDENTIFIER = re.compile(r"[A-Za-z_:][A-Za-z0-9_:]*")

# Identifiers that are never a metric selector. The scanner already passes over
# anything immediately followed by `(`, which covers every function call; these
# are the ones that can appear bare, or whose parenthesised argument is a list
# of label names rather than an expression.
GROUPING_KEYWORDS = frozenset(
    {"by", "without", "on", "ignoring", "group_left", "group_right"}
)
AGGREGATION_OPERATORS = frozenset(
    {
        "sum",
        "min",
        "max",
        "avg",
        "group",
        "count",
        "count_values",
        "topk",
        "bottomk",
        "quantile",
        "stddev",
        "stdvar",
    }
)
SET_OPERATORS = frozenset({"and", "or", "unless", "bool", "offset", "atan2"})
NOT_A_METRIC = GROUPING_KEYWORDS | AGGREGATION_OPERATORS | SET_OPERATORS

MATCHER = re.compile(
    r'^(?P<label>[A-Za-z_][A-Za-z0-9_]*)\s*'
    r'(?P<op>=~|!~|!=|=)\s*'
    r'(?P<quote>["\'`])(?P<value>.*)(?P=quote)$',
    re.DOTALL,
)

IMMEDIATE_DURATION = re.compile(r"0+(?:[smhdwy]|ms)?")


# --------------------------------------------------------------------------
# Reading the committed stack definition
# --------------------------------------------------------------------------


def rules_content(path: Path | None = None) -> str:
    """The `prometheus_rules` config's inline content, as Prometheus loads it.

    The Compose file escapes a literal `$` as `$$` so that Compose's own
    interpolation leaves the Go templates in the annotations alone. Undoing
    that here is what makes `{{ $labels.name }}` readable as the annotation
    Prometheus renders rather than as the Compose file's spelling of it.

    An absent or empty config is a failure rather than an empty result: every
    assertion over the rules would otherwise pass having read nothing.
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
    return content.replace("$$", "$")


def alerting_rules(path: Path | None = None) -> list[dict]:
    """Every `alert:` rule the stack evaluates, as
    `{"group": ..., "alert": ..., "expr": ..., ...}`.

    Recording rules (a `record:` key rather than an `alert:` one) are not
    alerts and are passed over.
    """
    document = yaml.safe_load(rules_content(path))
    if not isinstance(document, dict):
        raise AssertionError(
            f"the `{RULES_CONFIG}` content does not parse as a mapping"
        )
    groups = document.get("groups")
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


def annotations_text(rule: dict) -> str:
    return " ".join(
        yaml.safe_dump(rule.get("annotations") or {}, sort_keys=False).split()
    )


def sustained_duration(rule: dict) -> str:
    """A rule's `for:` duration as written, or the empty string."""
    value = rule.get("for")
    return "" if value is None else str(value).strip()


def duration_is_immediate(value: str) -> bool:
    """Whether a `for:` duration waits for nothing. `0`, `0s`, `0m` and an
    absent value are all "fire on the first evaluation"."""
    if not value:
        return True
    return IMMEDIATE_DURATION.fullmatch(value) is not None


# --------------------------------------------------------------------------
# Reading an expression, rather than matching its text
#
# Asserting that the expression CONTAINS `name!=""` twice would pass on one
# metric carrying the selector twice and the other left bare, and would fail on
# a reformat that put a space inside the braces. So the expression is scanned
# into its metric selectors and each one's label matchers are read.
# --------------------------------------------------------------------------


def _skip_quoted(text: str, start: int) -> int:
    """The index just past the string literal opening at `start`."""
    quote = text[start]
    index = start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == quote:
            return index + 1
        index += 1
    return len(text)


def _skip_group(text: str, start: int, opening: str, closing: str) -> int:
    """The index just past the bracket group opening at `start`, ignoring
    brackets that occur inside a string literal."""
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if char in "\"'`":
            index = _skip_quoted(text, index)
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(text)


def _skip_space(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def metric_selectors(expr: str) -> list[dict]:
    """Every metric selector in a PromQL expression, as
    `{"metric": ..., "matchers": ...}`, in the order they are written.

    What is deliberately NOT a selector: a function call (an identifier
    followed by `(`), the label list of a `by`/`without`/`on`/`ignoring`
    clause, an aggregation or set operator, the contents of a range or offset
    in `[...]`, anything inside a string literal, and the unit suffix of a
    duration such as the `m` of `10m`.
    """
    selectors: list[dict] = []
    index = 0
    length = len(expr)
    while index < length:
        char = expr[index]
        if char in "\"'`":
            index = _skip_quoted(expr, index)
            continue
        if char == "[":
            index = _skip_group(expr, index, "[", "]")
            continue
        if char == "{":
            end = _skip_group(expr, index, "{", "}")
            selectors.append({"metric": "", "matchers": expr[index:end]})
            index = end
            continue
        match = IDENTIFIER.match(expr, index)
        if not match:
            index += 1
            continue
        name = match.group(0)
        # A duration's unit suffix, or the tail of an identifier already read.
        if index and (expr[index - 1].isalnum() or expr[index - 1] in "._"):
            index = match.end()
            continue
        after = _skip_space(expr, match.end())
        if name in GROUPING_KEYWORDS and after < length and expr[after] == "(":
            index = _skip_group(expr, after, "(", ")")
            continue
        if after < length and expr[after] == "(":
            index = match.end()
            continue
        if name in NOT_A_METRIC:
            index = match.end()
            continue
        if after < length and expr[after] == "{":
            end = _skip_group(expr, after, "{", "}")
            selectors.append({"metric": name, "matchers": expr[after:end]})
            index = end
            continue
        selectors.append({"metric": name, "matchers": ""})
        index = match.end()
    return selectors


def _split_matchers(matchers: str) -> list[str]:
    inner = matchers.strip()
    if inner.startswith("{"):
        inner = inner[1:]
    if inner.endswith("}"):
        inner = inner[:-1]
    parts: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(inner):
        char = inner[index]
        if char in "\"'`":
            end = _skip_quoted(inner, index)
            current.append(inner[index:end])
            index = end
            continue
        if char == ",":
            parts.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def label_matchers(matchers: str) -> list[dict]:
    """A selector's label matchers, as `{"label", "op", "value", "text"}`.

    A matcher this reader cannot parse is returned with `label` None and its
    text intact, rather than dropped: an unreadable matcher is a matcher that
    has not been checked, and the assertions below say so instead of passing.
    """
    parsed: list[dict] = []
    for part in _split_matchers(matchers):
        match = MATCHER.match(part)
        if match is None:
            parsed.append({"label": None, "op": None, "value": None, "text": part})
            continue
        parsed.append(
            {
                "label": match.group("label"),
                "op": match.group("op"),
                "value": match.group("value"),
                "text": part,
            }
        )
    return parsed


def excludes_the_empty_string(matcher: dict) -> bool | None:
    """Whether a matcher admits no series whose label is empty, or None where
    this reader cannot tell.

    `label!=""` and an equality against any non-empty value both exclude it. A
    regex matcher is decided by whether the pattern matches the empty string --
    PromQL anchors its regexes, so a full match is the right question -- with
    the sense inverted for `!~`.
    """
    operator, value = matcher.get("op"), matcher.get("value")
    if operator is None or value is None:
        return None
    if operator == "!=":
        return value == ""
    if operator == "=":
        return value != ""
    try:
        pattern = re.compile(value)
    except re.error:
        return None
    matches_empty = pattern.fullmatch("") is not None
    if operator == "=~":
        return not matches_empty
    return matches_empty


def restricts_to_a_named_container(selector: dict) -> bool | None:
    """Whether a selector admits only series carrying a container name, or None
    where a matcher could not be read."""
    unreadable = False
    for matcher in label_matchers(selector["matchers"]):
        if matcher["label"] is None:
            unreadable = True
            continue
        if matcher["label"] != CONTAINER_NAME_LABEL:
            continue
        verdict = excludes_the_empty_string(matcher)
        if verdict is None:
            unreadable = True
            continue
        if verdict:
            return True
    return None if unreadable else False


def rules_reading(prefix: str, path: Path | None = None) -> list[dict]:
    """Every alert rule with a metric selector whose name starts with
    `prefix`."""
    found = []
    for rule in alerting_rules(path):
        metrics = [
            selector["metric"] for selector in metric_selectors(expression(rule))
        ]
        if any(metric.startswith(prefix) for metric in metrics):
            found.append(rule)
    return found


def container_subject_rules(path: Path | None = None) -> list[dict]:
    """Every alert rule whose subject is a container -- the delta's own scope
    for the restriction, resolved here as a rule reading any `container_*`
    series."""
    return rules_reading(CONTAINER_METRIC_PREFIX, path)


def unrestricted_selectors(rule: dict) -> list[str]:
    """The metric selectors of a rule that admit a series carrying no container
    name, rendered for a failure message."""
    offenders = []
    for selector in metric_selectors(expression(rule)):
        if restricts_to_a_named_container(selector) is False:
            offenders.append(f"{selector['metric']}{selector['matchers'] or '{}'}")
    return offenders


def unreadable_selectors(rule: dict) -> list[str]:
    offenders = []
    for selector in metric_selectors(expression(rule)):
        if restricts_to_a_named_container(selector) is None:
            offenders.append(f"{selector['metric']}{selector['matchers'] or '{}'}")
    return offenders


def described(rules: list[dict]) -> list[str]:
    return [f"{rule.get('alert')} ({expression(rule)})" for rule in rules]


# --------------------------------------------------------------------------
# The scenarios
# --------------------------------------------------------------------------


class TestACrashLoopingContainerTriggersAnAlert(unittest.TestCase):
    """MODIFIED requirement: Metrics-Based Alerting Covers Host and Service
    Health -- scenario "A crash-looping container triggers an alert", as
    revised: the alert identifies that container BY NAME.

    WHAT PASSING THIS CLASS ESTABLISHES, AND WHAT IT DOES NOT. That the
    committed stack definition declares a rule of the right shape. It does NOT
    establish that the rule loads, that a real crash-loop crosses its
    threshold, or that a notification arrives. That is the change's own
    confirmation step against the deployed host.

    These assertions hold of the rule as it stands at the plan commit, so they
    pass from the moment they are written -- they are the half of the scenario
    this change must not break, recorded so that narrowing the selector cannot
    quietly delete the alert instead of scoping it.
    """

    def test_the_stack_definition_is_read_at_all(self) -> None:
        """DERIVED -- no scenario states it. A non-vacuity guard: every
        assertion below would pass over a file whose rules config had been
        emptied, so the read is asserted before anything is read from it."""
        rules = alerting_rules()
        self.assertTrue(
            rules,
            "the platform stack declares no alert rules at all, so no assertion "
            "about a container alert can mean anything",
        )

    def test_an_alert_reads_the_restart_and_out_of_memory_counters(self) -> None:
        """SPECIFIED -- the requirement's "container crash-looping or repeated
        restarts, container out-of-memory kills", and the scenario's "restarts
        repeatedly within a short window, or is OOM-killed". Both limbs, since
        the scenario names both and a rule covering one leaves the other
        unwatched."""
        for metric in (RESTART_METRIC, OOM_METRIC):
            with self.subTest(metric=metric):
                found = rules_reading(metric)
                self.assertTrue(
                    found,
                    f"no alert rule in the platform stack reads `{metric}`, so that "
                    f"limb of the crash-loop scenario raises nothing. The rules that "
                    f"do exist are: "
                    f"{sorted(str(rule.get('alert')) for rule in alerting_rules())}",
                )

    def test_that_alert_names_the_container_rather_than_describing_it_generically(
        self,
    ) -> None:
        """SPECIFIED -- the scenario's "identifying that container by name",
        and the requirement's account of why: a rule that fires on a series
        carrying no container name "can name no container" in its
        notification. Read as a substring of the rendered annotations, because
        this assertion is about which label is named and not about how the
        Compose file escapes it."""
        rules = container_subject_rules()
        self.assertTrue(
            rules,
            f"no alert rule reads a `{CONTAINER_METRIC_PREFIX}*` series, so there "
            f"is no annotation to check for the container's identity",
        )
        offenders = [
            f"{rule.get('alert')}: {annotations_text(rule) or '<no annotations>'}"
            for rule in rules
            if f"labels.{CONTAINER_NAME_LABEL}" not in annotations_text(rule)
        ]
        self.assertEqual(
            [],
            offenders,
            f"these container alerts carry no annotation naming the "
            f"`{CONTAINER_NAME_LABEL}` label, so the notification a recipient "
            f"receives describes the failure without identifying the container: "
            f"{offenders}",
        )


class TestAControlGroupThatIsNotAContainerRaisesNoContainerAlert(unittest.TestCase):
    """MODIFIED requirement: Metrics-Based Alerting Covers Host and Service
    Health -- scenario "A control group that is not a container raises no
    container alert".

    The two tests below are the scenario's two limbs, kept apart because the
    scenario keeps them apart: the series reporting starts, and -- its **AND**
    clause -- the series reporting out-of-memory kills, "the restriction
    applying to every series the rule reads rather than only to the one that
    reports starts". A half-applied selector passes one and fails the other,
    which is the outcome a single combined assertion would hide.

    WHAT NO ASSERTION HERE ESTABLISHES. That no alert fires for a system
    service or a login session at runtime. That needs a Prometheus evaluating
    real series against a host whose control groups are churning, which this
    suite may not spawn; the change's own confirmation step provokes exactly
    that churn on the deployed host and reads the silence against it.
    """

    def _rules_reading(self, metric: str) -> list[dict]:
        rules = rules_reading(metric)
        self.assertTrue(
            rules,
            f"no alert rule reads `{metric}`, so there is no selector to check -- "
            f"stated rather than passing over an empty list, so this assertion "
            f"cannot report success having read no rule at all",
        )
        return rules

    def _check(self, rules: list[dict], metric: str, consequence: str) -> None:
        for rule in rules:
            with self.subTest(alert=str(rule.get("alert"))):
                selectors = [
                    selector
                    for selector in metric_selectors(expression(rule))
                    if selector["metric"] == metric
                ]
                self.assertTrue(
                    selectors, f"{rule.get('alert')} reads no `{metric}` selector"
                )
                unreadable = [
                    f"{selector['metric']}{selector['matchers']}"
                    for selector in selectors
                    if restricts_to_a_named_container(selector) is None
                ]
                self.assertEqual(
                    [],
                    unreadable,
                    f"the label matchers of these selectors could not be read, so "
                    f"the restriction has not been checked: {unreadable}",
                )
                offenders = [
                    f"{selector['metric']}{selector['matchers'] or '{}'}"
                    for selector in selectors
                    if restricts_to_a_named_container(selector) is False
                ]
                self.assertEqual(
                    [],
                    offenders,
                    f"{rule.get('alert')} selects every control group cAdvisor "
                    f"reports `{metric}` for, not only the containers: {offenders}. "
                    f"{consequence}",
                )

    def test_the_restart_half_selects_only_series_carrying_a_container_name(
        self,
    ) -> None:
        """SPECIFIED -- the scenario's WHEN and THEN: a control group that is
        not a container, starting "repeatedly within the same window that would
        raise the crash-looping alert for a container", raises no container
        alert, "because the rule's subject is restricted to series that
        identify a container"."""
        self._check(
            self._rules_reading(RESTART_METRIC),
            RESTART_METRIC,
            "A system service an unattended upgrade restarts, or a login session's "
            "control group recreated by repeated short-lived logins, clears the "
            "same threshold and fires this alert with an empty "
            f"`{CONTAINER_NAME_LABEL}` in the notification.",
        )

    def test_the_out_of_memory_half_selects_only_series_carrying_a_container_name(
        self,
    ) -> None:
        """SPECIFIED -- the scenario's **AND**: "an out-of-memory kill inside
        such a control group SHALL likewise raise no container alert, the
        restriction applying to every series the rule reads rather than only to
        the one that reports starts"."""
        self._check(
            self._rules_reading(OOM_METRIC),
            OOM_METRIC,
            "An out-of-memory kill inside a system unit's control group raises the "
            "same nameless notification the restart half was narrowed to stop.",
        )


class TestEveryContainerSubjectRuleSelectsOnlyContainers(unittest.TestCase):
    """MODIFIED requirement: Metrics-Based Alerting Covers Host and Service
    Health -- its added normative paragraph: "An alert rule whose subject is a
    container SHALL select only series that identify one."

    Stated over every rule reading a `container_*` series rather than over the
    one rule this change narrows, because that is how the requirement states
    it: a second container rule written later is bound by it too, and would
    otherwise arrive carrying exactly the defect this change closes.
    """

    def test_every_series_a_container_rule_reads_carries_a_container_name(self) -> None:
        """SPECIFIED -- the normative paragraph, applied to every selector of
        every container-subject rule. This is the assertion the delta's
        sentence binds; the two limbs above are the same property read through
        the scenario that states each."""
        rules = container_subject_rules()
        self.assertTrue(
            rules,
            f"no alert rule reads a `{CONTAINER_METRIC_PREFIX}*` series at all, so "
            f"this class is checking nothing -- and the requirement's "
            f"container-crash-loop coverage is absent",
        )
        unreadable = []
        offenders = []
        for rule in rules:
            for text in unreadable_selectors(rule):
                unreadable.append(f"{rule.get('alert')}: {text}")
            for text in unrestricted_selectors(rule):
                offenders.append(f"{rule.get('alert')}: {text}")
        self.assertEqual(
            [],
            unreadable,
            f"the label matchers of these selectors could not be read, so the "
            f"restriction has not been checked: {unreadable}",
        )
        self.assertEqual(
            [],
            offenders,
            f"these selectors admit series that identify no container: {offenders}. "
            f"The container metrics this stack collects are reported per control "
            f"group, and a host runs many control groups that are not containers; a "
            f"rule reading them reports their ordinary churn as a container incident "
            f"in a notification that can name no container. The rules read are "
            f"{described(rules)}",
        )


class TestSustainedApplicationErrorRateTriggersAnAlert(unittest.TestCase):
    """MODIFIED requirement: Metrics-Based Alerting Covers Host and Service
    Health -- scenario "Sustained per-application error rate triggers an
    alert", whose text the delta leaves unchanged.

    PASSES FROM THE MOMENT IT IS WRITTEN, and is recorded as such rather than
    as coverage of this change: it holds of the rules at the plan commit. It is
    here because the requirement is MODIFIED as a whole, and because a change
    editing this config entry is exactly the occasion on which an unrelated
    rule can be lost without anything noticing.
    """

    def test_an_alert_reads_the_proxys_per_application_request_counts(self) -> None:
        """SPECIFIED -- "an application's HTTP 5xx rate, as observed via
        Traefik's metrics"."""
        found = rules_reading(ERROR_RATE_METRIC_PREFIX)
        self.assertTrue(
            found,
            f"no alert rule reads `{ERROR_RATE_METRIC_PREFIX}`, so a sustained "
            f"per-application error rate raises nothing",
        )

    def test_that_alert_waits_for_a_sustained_period_and_identifies_the_application(
        self,
    ) -> None:
        """SPECIFIED -- "exceeds a configured threshold for a sustained period"
        and "identifying that application". A rule with no `for:` fires on the
        first evaluation that crosses the threshold, and an annotation
        interpolating no label names no application."""
        rules = rules_reading(ERROR_RATE_METRIC_PREFIX)
        self.assertTrue(rules, f"no alert rule reads `{ERROR_RATE_METRIC_PREFIX}`")
        immediate = [
            f"{rule.get('alert')} (for: {sustained_duration(rule) or '<absent>'})"
            for rule in rules
            if duration_is_immediate(sustained_duration(rule))
        ]
        self.assertEqual(
            [],
            immediate,
            f"these error-rate alerts fire on the first evaluation rather than over "
            f"a sustained period: {immediate}",
        )
        anonymous = [
            str(rule.get("alert"))
            for rule in rules
            if "labels." not in annotations_text(rule)
        ]
        self.assertEqual(
            [],
            anonymous,
            f"these error-rate alerts interpolate no label into their annotations, "
            f"so the notification names no application: {anonymous}",
        )


class TestHostResourcePressureTriggersAnAlert(unittest.TestCase):
    """MODIFIED requirement: Metrics-Based Alerting Covers Host and Service
    Health -- scenario "Host resource pressure triggers an alert", whose text
    the delta leaves unchanged.

    PASSES FROM THE MOMENT IT IS WRITTEN, for the reason the class above gives.
    """

    def test_an_alert_reads_each_resource_the_scenario_names(self) -> None:
        """SPECIFIED -- "host disk usage, CPU usage, or memory usage exceeds a
        configured threshold for a sustained period", and "identifying the
        affected resource": one rule per resource is what leaves a notification
        able to say which."""
        for resource, prefix in (
            ("disk", DISK_METRIC_PREFIX),
            ("CPU", CPU_METRIC_PREFIX),
            ("memory", MEMORY_METRIC_PREFIX),
        ):
            with self.subTest(resource=resource):
                found = rules_reading(prefix)
                self.assertTrue(
                    found,
                    f"no alert rule reads a `{prefix}*` series, so host {resource} "
                    f"pressure raises nothing",
                )
                immediate = [
                    f"{rule.get('alert')} "
                    f"(for: {sustained_duration(rule) or '<absent>'})"
                    for rule in found
                    if duration_is_immediate(sustained_duration(rule))
                ]
                self.assertEqual(
                    [],
                    immediate,
                    f"these host {resource} alerts fire on the first evaluation "
                    f"rather than over a sustained period: {immediate}",
                )


class TestAnUnreachableMetricsSourceTriggersAnAlert(unittest.TestCase):
    """MODIFIED requirement: Metrics-Based Alerting Covers Host and Service
    Health -- scenario "A metrics source becoming unreachable triggers an
    alert", whose text the delta leaves unchanged.

    PASSES FROM THE MOMENT IT IS WRITTEN, for the reason two classes above
    gives.
    """

    def test_an_alert_reports_a_scrape_target_that_stopped_answering(self) -> None:
        """SPECIFIED -- "a metrics source the platform stack scrapes ...
        becomes unreachable for a sustained period", and "rather than that
        metrics gap going unnoticed". `up` is the per-target series Prometheus
        writes for every scrape, so a rule over it covers every source rather
        than an enumerated few."""
        found = [
            rule
            for rule in alerting_rules()
            if any(
                selector["metric"] == SCRAPE_HEALTH_METRIC
                for selector in metric_selectors(expression(rule))
            )
        ]
        self.assertTrue(
            found,
            f"no alert rule reads the `{SCRAPE_HEALTH_METRIC}` series, so a metrics "
            f"source going unreachable goes unnoticed. The rules that exist are "
            f"{sorted(str(rule.get('alert')) for rule in alerting_rules())}",
        )
        immediate = [
            f"{rule.get('alert')} (for: {sustained_duration(rule) or '<absent>'})"
            for rule in found
            if duration_is_immediate(sustained_duration(rule))
        ]
        self.assertEqual(
            [],
            immediate,
            f"these unreachable-source alerts fire on the first evaluation rather "
            f"than over a sustained period, so a single missed scrape notifies: "
            f"{immediate}",
        )


# --------------------------------------------------------------------------
# Discrimination
# --------------------------------------------------------------------------


RESTRICTION = '{name!=""}'
DEFAULT_SUMMARY = "Container {{ $labels.name }} is crash-looping or was OOM-killed"


class TestTheseAssertionsAreARealReadOfTheFile(unittest.TestCase):
    """MODIFIED requirement: Metrics-Based Alerting Covers Host and Service
    Health.

    Every class above would pass identically against helpers that returned a
    fixed answer and read nothing. These run the same helpers over throwaway
    stack definitions differing from a satisfying one in exactly one property,
    and assert the verdict differs -- which is also what lets the narrowing
    assertions be exercised before the implementation of this change exists.
    Without them, the classes above would sit in the state where the property
    is merely absent, establishing nothing about whether the assertions
    discriminate.

    The fixtures are built from scratch rather than copied from the committed
    file, so nothing here depends on what that file happens to contain today --
    including the escaping, which the fixtures reproduce by doubling every `$`
    the way Compose requires.
    """

    def compose_fixture(
        self,
        *,
        restart_matchers: str = RESTRICTION,
        oom_matchers: str = RESTRICTION,
        summary: str = DEFAULT_SUMMARY,
        include_rule: bool = True,
        rule_for: str = "0m",
    ) -> Path:
        """A minimal stack definition carrying the one thing these assertions
        read: a `prometheus_rules` config whose content is a rule file."""
        rules: list[dict] = []
        if include_rule:
            rules.append(
                {
                    "alert": RESTART_ALERT,
                    "expr": (
                        f"increase({OOM_METRIC}{oom_matchers}[10m]) > 0 "
                        f"or "
                        f"changes({RESTART_METRIC}{restart_matchers}[10m]) > 3"
                    ),
                    "for": rule_for,
                    "labels": {"severity": "warning"},
                    "annotations": {"summary": summary},
                }
            )
        document = {
            "services": {
                "prometheus": {
                    "image": "prom/prometheus:v3.7.3",
                    "configs": [
                        {"source": RULES_CONFIG, "target": "/etc/prometheus/rules.yml"}
                    ],
                }
            },
            "configs": {
                RULES_CONFIG: {
                    "content": yaml.safe_dump(
                        {"groups": [{"name": "platform-monitoring", "rules": rules}]},
                        sort_keys=False,
                    ).replace("$", "$$")
                }
            },
        }
        directory = Path(tempfile.mkdtemp(prefix="container-alert-fixture-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "docker-compose.yml"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return path

    def test_a_rule_restricted_on_both_halves_is_accepted(self) -> None:
        """DERIVED -- the converse half, and the one that makes the rest
        readable. Without it, helpers reporting every rule as offending would
        satisfy every discrimination test below while failing the committed
        file no matter what it said."""
        fixture = self.compose_fixture()
        rules = container_subject_rules(fixture)
        self.assertEqual(1, len(rules), described(rules))
        self.assertEqual([], unrestricted_selectors(rules[0]))
        self.assertEqual([], unreadable_selectors(rules[0]))
        self.assertIn(f"labels.{CONTAINER_NAME_LABEL}", annotations_text(rules[0]))

    def test_a_half_applied_selector_is_caught(self) -> None:
        """SPECIFIED -- the discriminating half of the scenario's **AND**
        clause, and the exact defect a text match for `name!=""` would miss:
        the restriction on the series that reports starts, and nothing on the
        series that reports out-of-memory kills."""
        fixture = self.compose_fixture(oom_matchers="")
        rules = container_subject_rules(fixture)
        self.assertEqual(
            [f"{OOM_METRIC}{{}}"],
            unrestricted_selectors(rules[0]),
            "a rule restricted on one of its two metrics was reported as "
            "restricted on both, so the scenario's AND clause is not checked",
        )
        reversed_fixture = self.compose_fixture(restart_matchers="")
        reversed_rules = container_subject_rules(reversed_fixture)
        self.assertEqual(
            [f"{RESTART_METRIC}{{}}"],
            unrestricted_selectors(reversed_rules[0]),
            "a rule restricted only on its out-of-memory metric was reported as "
            "restricted on both",
        )

    def test_a_rule_with_no_restriction_at_all_is_caught(self) -> None:
        """SPECIFIED -- the discriminating half of the scenario: this is the
        rule as it stands before this change, and it must be reported."""
        fixture = self.compose_fixture(restart_matchers="", oom_matchers="")
        rules = container_subject_rules(fixture)
        self.assertEqual(
            [f"{OOM_METRIC}{{}}", f"{RESTART_METRIC}{{}}"],
            unrestricted_selectors(rules[0]),
            "a rule selecting every control group on the host was reported as "
            "selecting only containers",
        )

    def test_a_reformatted_or_differently_spelled_restriction_is_still_accepted(
        self,
    ) -> None:
        """DERIVED -- that change's design.md requires that a half-applied
        selector fail and a reformat not. Without this, the check would be a
        text match wearing a parser's clothes: an author who put a space inside
        the braces, added a second matcher, or wrote the restriction as a regex
        would see a failure naming a defect that is not there."""
        for matchers in (
            '{ name != "" }',
            '{name!="",id=~"^/docker/.*"}',
            '{id=~"^/docker/.*",name!=""}',
            '{name=~".+"}',
            '{name!~"^$"}',
            '{name="platform-grafana-1"}',
        ):
            with self.subTest(matchers=matchers):
                fixture = self.compose_fixture(
                    restart_matchers=matchers, oom_matchers=matchers
                )
                rules = container_subject_rules(fixture)
                self.assertEqual(
                    [],
                    unrestricted_selectors(rules[0]),
                    f"{matchers} admits no series without a container name, but was "
                    f"reported as unrestricted",
                )
                self.assertEqual([], unreadable_selectors(rules[0]))

    def test_a_restriction_that_still_admits_the_empty_name_is_caught(self) -> None:
        """SPECIFIED -- the discriminating half of the scenario, against the
        spellings that LOOK like the restriction and are not. `name=""` selects
        exactly the control groups the scenario excludes; `name=~".*"` and
        `name!="something"` both admit them."""
        for matchers in ('{name=""}', '{name=~".*"}', '{name!="platform-grafana-1"}'):
            with self.subTest(matchers=matchers):
                fixture = self.compose_fixture(
                    restart_matchers=matchers, oom_matchers=matchers
                )
                rules = container_subject_rules(fixture)
                self.assertEqual(
                    2,
                    len(unrestricted_selectors(rules[0])),
                    f"{matchers} admits series carrying no container name, but was "
                    f"reported as restricting to containers",
                )

    def test_a_restriction_on_some_other_label_alone_is_caught(self) -> None:
        """DERIVED -- that change's design.md chose `name!=""` over an `id`
        pattern, because the name is what the notification interpolates and one
        proposition then covers both. A selector restricted only by `id` would
        select the same series today and leaves the notification's emptiness a
        second fact rather than a consequence."""
        fixture = self.compose_fixture(
            restart_matchers='{id=~"^/docker/.*"}', oom_matchers='{id=~"^/docker/.*"}'
        )
        rules = container_subject_rules(fixture)
        self.assertEqual(
            2,
            len(unrestricted_selectors(rules[0])),
            "a selector carrying no `name` matcher at all was reported as "
            "restricting to series that identify a container",
        )

    def test_an_annotation_that_names_no_container_is_caught(self) -> None:
        """SPECIFIED -- the discriminating half of "identifying that container
        by name"."""
        fixture = self.compose_fixture(summary="A container is crash-looping")
        rules = container_subject_rules(fixture)
        self.assertNotIn(
            f"labels.{CONTAINER_NAME_LABEL}",
            annotations_text(rules[0]),
            "an annotation naming no label was reported as identifying the "
            "container",
        )

    def test_a_matcher_this_reader_cannot_parse_is_reported_rather_than_passed(
        self,
    ) -> None:
        """DERIVED -- no scenario states it. A matcher the reader cannot read
        is a matcher it has not checked, and the distinction between that and a
        satisfied one is the whole difference between a check and a
        formality."""
        fixture = self.compose_fixture(
            restart_matchers="{name}", oom_matchers='{name=~"(unclosed"}'
        )
        rules = container_subject_rules(fixture)
        self.assertEqual(
            2,
            len(unreadable_selectors(rules[0])),
            "a malformed matcher and an invalid regex were both read as a verdict "
            "rather than reported as unreadable",
        )
        self.assertEqual([], unrestricted_selectors(rules[0]))

    def test_the_compose_escaping_is_undone_before_the_rules_are_read(self) -> None:
        """DERIVED -- that change's design.md states the `$$` doubling has to
        be undone before the content parses as a rule file. Without this, the
        annotation assertion would be reading the Compose file's spelling of a
        Go template rather than the template Prometheus renders, and a rule
        file that lost its escaping entirely would read identically."""
        fixture = self.compose_fixture()
        content = rules_content(fixture)
        self.assertNotIn(
            "$$",
            content,
            "the `$$` Compose escaping survived into what these assertions read",
        )
        self.assertIn("$labels.name", content)

    def test_the_selector_reader_ignores_functions_grouping_labels_and_durations(
        self,
    ) -> None:
        """DERIVED -- no scenario states it. The reader is this module's one
        piece of machinery, and each case below is a construct the committed
        rules already contain: a function call, an aggregation's label list, a
        range duration whose unit suffix reads as an identifier, and a label
        value that is itself a regex."""
        cases = {
            f"increase({OOM_METRIC}[10m]) > 0 or changes({RESTART_METRIC}[10m]) > 3": [
                OOM_METRIC,
                RESTART_METRIC,
            ],
            'sum by (router) (rate(traefik_router_requests_total{code=~"5.."}[5m]))': [
                "traefik_router_requests_total"
            ],
            "up == 0": ["up"],
            '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 90': [
                "node_cpu_seconds_total"
            ],
            '(node_filesystem_avail_bytes{mountpoint="/"} / '
            'node_filesystem_size_bytes{mountpoint="/"}) < 0.1': [
                "node_filesystem_avail_bytes",
                "node_filesystem_size_bytes",
            ],
            'absent(traefik_tls_certs_not_after{cn!=""}) '
            'or count(traefik_tls_certs_not_after{cn=""}) > 0': [
                "traefik_tls_certs_not_after",
                "traefik_tls_certs_not_after",
            ],
            "vector(1)": [],
        }
        for expr, expected in cases.items():
            with self.subTest(expr=expr):
                self.assertEqual(
                    expected,
                    [selector["metric"] for selector in metric_selectors(expr)],
                )

    def test_a_rules_config_with_no_rules_fails_rather_than_reading_nothing(
        self,
    ) -> None:
        """DERIVED -- the file-level non-vacuity guard, matching the one the
        module beside this applies. A stack whose rules config was emptied must
        fail loudly rather than report no offences."""
        fixture = self.compose_fixture(include_rule=False)
        with self.assertRaises(AssertionError):
            alerting_rules(fixture)

    def test_a_stack_declaring_no_rules_config_fails_rather_than_reading_nothing(
        self,
    ) -> None:
        """DERIVED -- the same guard one level up: the config itself going
        missing, rather than its content losing a rule."""
        directory = Path(tempfile.mkdtemp(prefix="container-alert-fixture-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "docker-compose.yml"
        path.write_text(
            yaml.safe_dump(
                {"services": {"prometheus": {"image": "prom/prometheus:v3.7.3"}}}
            ),
            encoding="utf-8",
        )
        with self.assertRaises(AssertionError):
            alerting_rules(path)

    def test_the_committed_file_is_the_one_these_assertions_read(self) -> None:
        """DERIVED -- no scenario states it. Every test in this class runs
        against a fixture; this is what ties the classes above to the file the
        platform deploy workflow actually deploys, so a helper defaulting to
        somewhere else would be visible."""
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
