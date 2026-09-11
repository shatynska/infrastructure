"""Every route to a role is followed or refused, and none is passed over.

WRITTEN BY THE IMPLEMENTER, NOT BY THE TEST AUTHOR, and that is worth stating
rather than leaving to be inferred. `test_the_matrix_runs_the_roles_a_pull_request_owes`
was derived from the delta specification before any selector existed, by
somebody who had not written one; this module was written afterwards, by
whoever wrote the code, to cover behaviour two rounds of code review added.

That ordering is weaker and the tests here are correspondingly narrower in
what they can claim: they establish that the refusals fire on material chosen
to provoke them, not that the refusals are the right ones. The judgment that
they are belongs to the delta and to the review that asked for them.

What they cover is one obligation, stated in the delta as:

    The derivation SHALL follow, or refuse, every construction by which a
    scenario reaches a role ... Following and refusing are both conformant
    dispositions; passing over is not.

Each test below is a route that reached a role and was, at some point in this
change's life, passed over -- found by review rather than by the sweep behind
the design. Each is now followed where it can be and refused where it cannot,
and each assertion is pointed at a fixture tree written to falsify it, because
the repository's own tree contains none of these constructions and a check
whose subject carries the asserted property already cannot fail.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from test_the_matrix_runs_the_roles_a_pull_request_owes import (
    Tree,
    converge_through_roles_list,
    graph_of,
    symbol,
)

NESTED = "ansible.builtin.command: ansible-playbook {}"


def _converge_with_task(body: str) -> str:
    return "---\n- name: Converge\n  hosts: all\n  tasks:\n    - name: Reach\n      " + body + "\n"


class TestAnIncludedTaskFileIsFollowed(unittest.TestCase):
    """Followed where it can be read, refused where it cannot.

    Refusing outright was the first fix and was too broad: factoring a
    scenario's shared assertions into a second file beside its converge is
    ordinary Molecule practice, not a design smell, so a blanket refusal costs
    an author of an ordinary scenario an edit to the selector. It is also
    inconsistent -- the heavier route, a nested `ansible-playbook`, is
    followed.
    """

    def _tree(self) -> Tree:
        tree = Tree(self)
        tree.scenario("core", converge=converge_through_roles_list("- core"))
        return tree

    def test_a_scenario_local_included_file_contributes_its_edges(self) -> None:
        tree = self._tree()
        tree.scenario(
            "user",
            converge=_converge_with_task("ansible.builtin.include_tasks: assertions.yml"),
        )
        (tree.role_dir("user") / "molecule" / "default" / "assertions.yml").write_text(
            "---\n- name: Reach the sibling\n  ansible.builtin.include_role:\n    name: core\n",
            encoding="utf-8",
        )
        self.assertIn(
            "core",
            graph_of(tree.root).get("user", set()),
            "a scenario factoring its tasks into a file beside the converge lost "
            "the edge that file reaches. The included file is not a play, so "
            "nothing else in the derivation reads it",
        )

    def test_an_included_file_outside_the_scenario_is_refused(self) -> None:
        tree = self._tree()
        tree.role_file("core", "tasks/main.yml", "---\n- name: Noop\n  ansible.builtin.debug:\n    msg: core\n")
        tree.scenario(
            "user",
            converge=_converge_with_task(
                "ansible.builtin.include_tasks: ../../../core/tasks/main.yml"
            ),
        )
        with self.assertRaises(symbol("DerivationRefused")) as raised:
            graph_of(tree.root)
        self.assertIn("user/molecule/default/converge.yml", str(raised.exception))

    def test_an_included_file_named_by_expression_is_refused(self) -> None:
        tree = self._tree()
        tree.scenario(
            "user",
            converge=_converge_with_task(
                'ansible.builtin.include_tasks: "{{ chosen_file }}"'
            ),
        )
        with self.assertRaises(symbol("DerivationRefused")):
            graph_of(tree.root)

    def test_an_included_file_that_does_not_exist_is_refused(self) -> None:
        """An unresolvable target and a target reaching nothing are
        indistinguishable to a derivation that passes over the first."""
        tree = self._tree()
        tree.scenario(
            "user",
            converge=_converge_with_task("ansible.builtin.include_tasks: absent.yml"),
        )
        with self.assertRaises(symbol("DerivationRefused")):
            graph_of(tree.root)


class TestANestedPlaybookIsFollowedOrRefused(unittest.TestCase):
    """A literal path is followable, so it is followed rather than passed over."""

    def _tree(self) -> Tree:
        tree = Tree(self)
        tree.scenario("core", converge=converge_through_roles_list("- core"))
        return tree

    def test_a_literal_nested_playbook_contributes_its_edges(self) -> None:
        tree = self._tree()
        tree.scenario(
            "user",
            converge=_converge_with_task(
                NESTED.format("../../../core/molecule/default/converge.yml")
            ),
        )
        self.assertIn(
            "core",
            graph_of(tree.root).get("user", set()),
            "a scenario running another role's playbook through `ansible-playbook` "
            "contributed no edge. The path is a literal, so it is followable, and "
            "a followable route that is not followed is passed over",
        )

    def test_a_repository_root_relative_nested_playbook_is_followed(self) -> None:
        """`ansible-playbook` resolves a relative path against the controller's
        own working directory, so this is the natural spelling -- and the one a
        derivation resolving only against the including file would miss."""
        tree = self._tree()
        tree.scenario(
            "user",
            converge=_converge_with_task(
                NESTED.format("ansible/roles/core/molecule/default/converge.yml")
            ),
        )
        self.assertIn("core", graph_of(tree.root).get("user", set()))

    def test_a_literal_nested_playbook_that_does_not_resolve_is_refused(self) -> None:
        tree = self._tree()
        tree.scenario("user", converge=_converge_with_task(NESTED.format("absent.yml")))
        with self.assertRaises(symbol("DerivationRefused")):
            graph_of(tree.root)

    def test_a_cycle_through_nested_playbooks_terminates(self) -> None:
        """The cycle guard is shared across hops, not minted per hop.

        A fresh `seen` per hop protects one hop only, and two playbooks
        invoking each other then recurse until the interpreter gives up -- a
        `RecursionError`, which reads as a defect in the selector rather than
        as a scenario that cannot be closed over. `ops_user`'s steady-state
        re-converge is a self-invocation of exactly this shape, saved from it
        only by being an expression.
        """
        tree = self._tree()
        tree.scenario(
            "user",
            converge=_converge_with_task(NESTED.format("other.yml")),
        )
        (tree.role_dir("user") / "molecule" / "default" / "other.yml").write_text(
            "---\n- name: Back again\n  hosts: all\n  tasks:\n"
            "    - name: Reach\n      ansible.builtin.command: ansible-playbook converge.yml\n",
            encoding="utf-8",
        )
        try:
            graph_of(tree.root)
        except RecursionError:  # pragma: no cover -- the defect this guards
            self.fail(
                "a cycle through nested playbooks recursed until the interpreter "
                "gave up. The cycle guard must be the caller's, shared across "
                "every hop"
            )
        except Exception as error:  # noqa: BLE001 -- a refusal is also conformant
            self.assertIsInstance(error, symbol("DerivationRefused"))


class TestARolesOwnFilesMayNotRunAPlaybook(unittest.TestCase):
    def test_a_role_task_file_running_ansible_playbook_is_refused(self) -> None:
        """It reaches outside the role whatever the path resolves to."""
        tree = Tree(self)
        tree.scenario("user", converge=converge_through_roles_list("- user"))
        tree.role_file(
            "user",
            "tasks/main.yml",
            "---\n- name: Run a playbook from the role's own tasks\n"
            "  ansible.builtin.command: ansible-playbook /somewhere/else.yml\n",
        )
        with self.assertRaises(symbol("DerivationRefused")) as raised:
            graph_of(tree.root)
        self.assertIn("user/tasks/main.yml", str(raised.exception))

    def test_a_templated_include_target_in_a_roles_own_files_is_refused(self) -> None:
        """Not a value the derivation can close over, so it is refused for the
        same reason a non-literal role name is."""
        tree = Tree(self)
        tree.scenario("user", converge=converge_through_roles_list("- user"))
        tree.role_file(
            "user",
            "tasks/main.yml",
            "---\n- name: Include something templated\n"
            '  ansible.builtin.include_tasks: "{{ shared_tasks_file }}"\n',
        )
        with self.assertRaises(symbol("DerivationRefused")) as raised:
            graph_of(tree.root)
        self.assertIn("user/tasks/main.yml", str(raised.exception))


class TestTheRemainingRoutes(unittest.TestCase):
    def test_a_non_literal_meta_dependency_is_refused(self) -> None:
        """The same shape in a `roles:` list already refused; this one dropped
        the edge with nothing reporting."""
        tree = Tree(self)
        tree.scenario("user", converge=converge_through_roles_list("- user"))
        tree.role_file(
            "user",
            "meta/main.yml",
            "---\ndependencies:\n  - role: \"{{ chosen }}\"\n",
        )
        with self.assertRaises(symbol("DerivationRefused")) as raised:
            graph_of(tree.root)
        self.assertIn("user/meta/main.yml", str(raised.exception))

    def test_a_scenario_redirecting_its_plays_is_refused(self) -> None:
        """`provisioner.playbooks` points a scenario's plays away from the
        directory this derivation globs, so every edge in the redirected
        playbook would be missing."""
        tree = Tree(self)
        definition = (
            "---\ndriver:\n  name: docker\nplatforms:\n"
            '  - name: "${MOLECULE_INSTANCE_NAME:?no namespace}"\n'
            "    image: example.invalid/base@sha256:" + "0" * 64 + "\n"
            "provisioner:\n  name: ansible\n  playbooks:\n"
            "    converge: ../../../elsewhere/converge.yml\n"
        )
        tree.scenario(
            "user",
            definition=definition,
            converge=converge_through_roles_list("- user"),
        )
        with self.assertRaises(symbol("DerivationRefused")) as raised:
            graph_of(tree.root)
        self.assertIn("molecule.yml", str(raised.exception))

    def test_a_role_named_by_path_is_refused_naming_the_file(self) -> None:
        """Refused where the edge is added, so the message names the file.

        Discarding it later would have been silent in a particular way: the
        external-content filter drops any name carrying a dot, and a relative
        path carries two.
        """
        tree = Tree(self)
        tree.scenario("core", converge=converge_through_roles_list("- core"))
        tree.scenario(
            "user", converge=converge_through_roles_list("- role: ../../core")
        )
        with self.assertRaises(symbol("DerivationRefused")) as raised:
            graph_of(tree.root)
        self.assertIn(
            "user/molecule/default/converge.yml",
            str(raised.exception),
            "the refusal did not name the file holding the construction; it said "
            f"{str(raised.exception)!r}",
        )

    def test_an_unparseable_scenario_is_refused_rather_than_read_as_empty(self) -> None:
        """The one path that resolved to FEWER roles.

        A file contributing no edges because it could not be parsed is
        indistinguishable from one that reaches nothing, and the second is a
        role quietly dropping out of the matrix.
        """
        tree = Tree(self)
        tree.scenario("user", converge="---\n- name: Converge\n  hosts: all\n   bad indent:\n")
        with self.assertRaises(symbol("DerivationRefused")) as raised:
            graph_of(tree.root)
        self.assertIn("user/molecule/default/converge.yml", str(raised.exception))

    def test_ansibles_own_vault_tag_parses_rather_than_refusing(self) -> None:
        """`!vault` is valid Ansible YAML that `safe_load` rejects, and this
        repository already uses it in `group_vars`. Refusing it would turn the
        required check red on an ordinary scenario."""
        tree = Tree(self)
        tree.scenario("core", converge=converge_through_roles_list("- core"))
        tree.scenario(
            "user",
            converge=(
                "---\n- name: Converge\n  hosts: all\n  vars:\n"
                "    secret: !vault |\n      $ANSIBLE_VAULT;1.1;AES256\n      3030\n"
                "  roles:\n    - core\n"
            ),
        )
        self.assertIn(
            "core",
            graph_of(tree.root).get("user", set()),
            "a scenario carrying a `!vault` value failed to contribute its edges",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
