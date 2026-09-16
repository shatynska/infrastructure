"""Validate one probe input object, and emit the two values a probe needs.

Installed by `ansible/roles/deploy_user` and read by `/usr/local/bin/app-probe`.
It exists as a file of its own rather than inline in that script so that the
unprivileged and privileged halves cannot drift apart on what they accept -- see
`openspec/specs/iac-host-configuration/spec.md`, "An Application Can Probe Its
Own Database Through a Read-Only Forced Command", whose input contract this is.

Reads the object on standard input and the application name from `PROBE_APP`.
On acceptance it writes the password and the table name to standard output,
NUL-separated, and exits 0; on refusal it writes one line to standard error and
exits non-zero. Nothing it emits is a token: a refusal is not an answer about
anybody's database, and the caller must not turn one into one.

NUL-separated rather than newline-separated because a JSON string may legally
carry a newline, and a caller splitting on lines would then read half a password
as a table name.
"""

import json
import os
import re
import sys

# "an optionally schema-qualified identifier" -- one identifier, or two
# separated by a dot, per that change's design.md decision 7. This is the belt
# over the transport, never the measure itself: what stops a name executing
# anything is that it reaches no command string at any layer and reaches SQL
# only as a quoted `to_regclass` argument. A pattern-based refusal is
# denylist-shaped and would be the wrong thing to rely on alone.
#
# Deliberately admits a schema, because `public.alembic_version` is a legitimate
# thing for a consumer to send and `to_regclass` resolves it -- a check refusing
# it would stop a correct deploy for nothing. Deliberately admits no third part.
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*(?:\.[A-Za-z_][A-Za-z0-9_$]*)?\Z")

# The probe reads an unauthenticated stranger's standard input. The caller bounds
# what it reads; this bound is the second half of the same guard, so that a
# caller that forgets is not the only thing standing between a parser and
# whatever it is sent.
MAX_INPUT = 65536


def refuse(message: str) -> "None":
    sys.stderr.write(f"app-probe: {message}\n")
    raise SystemExit(2)


def main() -> None:
    app = os.environ.get("PROBE_APP", "")
    if not app:
        refuse("no application name was supplied to the parser")

    raw = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        refuse(f"input object is larger than {MAX_INPUT} bytes")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        refuse(f"input object is not UTF-8: {exc}")

    try:
        obj = json.loads(text)
    except ValueError as exc:
        refuse(f"input is not a JSON object: {exc}")

    if not isinstance(obj, dict):
        refuse("input is a JSON value but not an object")

    password = obj.get("password")
    if not isinstance(password, str) or not password:
        refuse("input carries no `password`, which is required")

    table = obj.get("table")
    if not isinstance(table, str) or not table:
        refuse("input carries no `table`, which is required")

    # `role` and `database` MAY be sent and SHALL equal the names derived from
    # the forced command's argument. They are accepted so that a consumer
    # sending the fields the original cross-repository contract named is not
    # refused for being explicit -- never as a source of either name, which
    # comes from which key connected and from nothing the client says.
    for field in ("role", "database"):
        if field not in obj:
            continue
        value = obj[field]
        if value != app:
            refuse(
                f"`{field}` is {value!r} and this probe is bound to {app!r}; "
                "a probe key can only ever probe its own application"
            )

    if not IDENTIFIER.match(table):
        refuse(
            f"`table` is {table!r}, which is not an optionally schema-qualified "
            "identifier"
        )

    # Every other field is ignored on purpose: the repository holding the other
    # half of this contract may add one before this one hears of it, and a probe
    # that refused would break that consumer's deploy at the moment it was being
    # careful.
    out = sys.stdout.buffer
    out.write(password.encode("utf-8") + b"\0")
    out.write(table.encode("utf-8") + b"\0")
    out.flush()


if __name__ == "__main__":
    main()
