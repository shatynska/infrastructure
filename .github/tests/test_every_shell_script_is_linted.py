"""The repository's shell scripts are linted, and every one of them is in scope.

Written for `docs/backlog.md`'s `lint-the-repository's-shell-scripts`, taken as
a fix rather than a change. That entry named one open decision -- whether this
suite should assert the hook exists -- and this module is that decision taken:
it should, for the reason the entry itself gives. A hook is one line to delete,
its absence looks like nothing, and the scripts it guards run as `root` on every
host.

WHAT THESE ASSERTIONS ESTABLISH, AND WHAT THEY DO NOT
-----------------------------------------------------
They read committed files. They establish that a pinned `shellcheck` hook is
configured, that it is not narrowed to a subset of the repository, and that
every committed shell script would be reached by it. They do NOT run
`shellcheck` -- that is the hook's job, and this suite may not spawn a process
for it (*The Suite Needs No Privileged or External Resource*,
`openspec/specs/iac-cicd-pipeline/spec.md`).

WHY A SHEBANG SCAN RATHER THAN A GLOB
-------------------------------------
Not one of this repository's shell scripts carries a `.sh` suffix -- they are
`ansible/scripts/run-molecule`, the two probe halves under
`ansible/roles/deploy_user/files/`, and four harness scripts under
`tools/env-rendering-probe/`. A check written against `*.sh` would pass over a
repository where nothing is linted at all, which is the failure this module
exists to make impossible.

Runner:

    python3 -m unittest discover --start-directory .github/tests
"""

from __future__ import annotations

import unittest
from pathlib import Path

from test_ci_configuration import (
    PRE_COMMIT_CONFIG,
    ROOT,
    load_yaml,
    walked_files,
)

SHELLCHECK_HOOK_ID = "shellcheck"

# A shell script is one whose first line names a shell interpreter, or whose
# suffix says so. Both, because neither alone covers this repository: every
# script here is found by the first rule, and the second is what keeps a `.sh`
# file added later from escaping.
SHELL_SUFFIXES = {".sh", ".bash"}
SHELL_INTERPRETERS = ("bash", "/bin/sh", "/usr/bin/sh", "dash", "ksh", "zsh")


def _is_shell_script(path: Path) -> bool:
    if path.suffix in SHELL_SUFFIXES:
        return True
    try:
        first = path.open("rb").readline(256)
    except OSError:
        return False
    if not first.startswith(b"#!"):
        return False
    line = first.decode("utf-8", errors="replace")
    return any(name in line for name in SHELL_INTERPRETERS)


def shell_scripts(root: Path | None = None) -> list[str]:
    """Every committed shell script, as repository-relative paths."""
    base = root or ROOT
    found = []
    for path in walked_files(base):
        if path.is_file() and _is_shell_script(path):
            found.append(str(path.relative_to(base)))
    return sorted(found)


def shellcheck_hook(root: Path | None = None) -> tuple[dict, dict] | None:
    """The (repo block, hook block) configuring shellcheck, or None."""
    config = load_yaml((root or ROOT) / ".pre-commit-config.yaml"
                       if root else PRE_COMMIT_CONFIG)
    for repo in config.get("repos") or []:
        for hook in repo.get("hooks") or []:
            if str(hook.get("id", "")).strip() == SHELLCHECK_HOOK_ID:
                return repo, hook
    return None


class TestTheRepositoryLintsItsShellScripts(unittest.TestCase):
    """`docs/backlog.md`'s `lint-the-repository's-shell-scripts`, taken as a fix."""

    def test_the_repository_has_shell_scripts_to_lint(self) -> None:
        """The vacuity guard, and it is not ceremonial: every assertion below
        reports green over a repository with no shell scripts at all, which is
        also what a broken detector looks like."""
        scripts = shell_scripts()
        self.assertTrue(
            scripts,
            "no committed file was recognised as a shell script, so every "
            "assertion in this module would pass having read nothing -- check "
            "the shebang scan before believing the repository has none",
        )

    def test_a_shellcheck_hook_is_configured(self) -> None:
        """The hook exists at all. It is one line to delete and its absence
        looks exactly like a repository that never had it."""
        self.assertIsNotNone(
            shellcheck_hook(),
            "no `shellcheck` hook is configured in .pre-commit-config.yaml, so "
            "nothing lints the shell scripts this repository runs as root on "
            "every host",
        )

    def test_the_shellcheck_hook_is_pinned_to_an_exact_revision(self) -> None:
        """This project pins every external tool to an exact version, so that a
        workstation and the runner check the same thing. A floating `rev` is the
        local-versus-CI divergence the gitleaks pin already guards against."""
        found = shellcheck_hook()
        self.assertIsNotNone(found, "no `shellcheck` hook to check the pin of")
        repo, _hook = found
        rev = str(repo.get("rev", "")).strip()
        self.assertTrue(rev, "the shellcheck repo block declares no `rev`")
        self.assertNotIn(
            rev.lower(),
            {"head", "master", "main", "latest"},
            f"the shellcheck hook's `rev` is {rev!r}, which floats -- pin it to "
            f"an exact release",
        )

    def test_the_hook_is_not_narrowed_away_from_any_shell_script(self) -> None:
        """A `files:` or `exclude:` pattern would silently drop scripts from the
        check, and the ones most worth linting are the two that run as root on
        every host -- one of them on input from an application's key. If a
        narrowing is ever wanted, this assertion is the place to state which
        scripts it gives up and why, rather than letting the pattern decide
        quietly."""
        found = shellcheck_hook()
        self.assertIsNotNone(found, "no `shellcheck` hook to check the scope of")
        _repo, hook = found
        narrowings = {
            key: hook[key] for key in ("files", "exclude", "types_or") if key in hook
        }
        self.assertEqual(
            {},
            narrowings,
            f"the shellcheck hook carries {narrowings}, which narrows what it "
            f"reads. Every committed shell script is meant to be in scope: "
            f"{shell_scripts()}",
        )


if __name__ == "__main__":
    unittest.main()
