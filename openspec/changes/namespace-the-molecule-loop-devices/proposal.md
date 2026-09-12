## Why

`docs/change-queue.md` entry 78. **A loop device minor is a kernel-global handle, and `platform_data_volume`'s Molecule fixtures claim theirs by a hardcoded literal.** `default` takes `/dev/loop87`, `multiple-devices-discoverable` and `multiple-devices-reverse-order` take 88 and 89, `superseded-path-retired` takes 90 and `superseded-path-in-force-refused` takes 91. The association a fixture makes inside a container is made by the machine's kernel and is not namespaced by that container, so it outlives the container it was made in and is still there on the next run. On the workstation this change was written on, all five were associated at the moment the change was opened, every one naming a backing file inside a container that no longer exists:

    /dev/loop87: []: (/root/platform-data-volume-backing.img)
    /dev/loop88: []: (/root/platform-data-volume-multi-a.img)
    /dev/loop89: []: (/root/platform-data-volume-multi-b.img)
    /dev/loop90: []: (/root/platform-data-volume-retire-backing.img)
    /dev/loop91: []: (/root/platform-data-volume-refusal-backing.img)

Three of the five fixtures then ask *"is this minor already associated?"* and skip associating when it is, so a run inherits whatever the last one left on that minor — **including a filesystem a previous converge created**.

**The danger is the green run, not the red one.** The red one is how this was found, and `move-the-platform-data-mount` paid for it: an assertion that the role had *not* formatted the device failed against contamination rather than against the role, and read as an implementation defect until `losetup -a` was run on the host. The silent case is worse and is live today. `molecule/default`'s whole subject is that the role formats an **unformatted** device; a run inheriting a formatted minor makes the role's format task a no-op and the scenario passes without exercising what it exists to exercise. Nothing reports that, and nothing distinguishes it from a genuine pass.

**This is the third shared handle, and it is worse than the two `AGENTS.md` already names.** *Namespacing Molecule per working tree* covers the instance name and the ephemeral directory; both are shared across working trees and both are now namespaced by `ansible/scripts/run-molecule`. The loop minor is shared across the **machine's kernel** rather than across its working trees, so two working trees are not the boundary — a single tree's consecutive runs collide with themselves, which is precisely what the five associations above are.

`iac-repo-foundations`'s *Verification Writing to Shared State Is Namespaced per Working Tree* already requires this. The loop minor is state a verification mechanism writes to, it outlives a single run, and it is reachable from every working tree on the machine. It is not excused by that requirement's carve-out for state whose sharing can only cause a run to fail: the formatted-ness of the inherited device is exactly what `molecule/default` asserts, so this is state that carries a result. The requirement is simply unmet here, and this change meets it up to the collision residual `design.md` Decision 3 states.

## What Changes

- **`ansible/scripts/run-molecule` derives a per-working-tree loop-minor base** from the same absolute path its instance namespace is derived from, and exports it as `INFRA_WORKTREE_LOOP_BASE`. A session takes it the same way it takes the instance namespace: by running the suite through the entry point. `--print-loop-base` computes it and runs nothing, matching `--print-namespace`.
- **Every fixture derives its device from that base plus a fixed offset** rather than from a hardcoded literal, in all **ten** plays that name one — the `prepare.yml`, `converge.yml` and `verify.yml` of each of the three single-device scenarios, and `multiple-devices-discoverable/prepare.yml`, which two scenarios share. Offsets 0 through 4 preserve today's scenario-to-minor mapping.
- **Every one of those ten plays refuses, as its first task, to run without a base.** This is not decoration: with the variable unset, an unguarded `| int` resolves to `0`, and `/dev/loop0` on this workstation is a real device holding Docker Desktop's ISO cache. A converge that reached it would format it.
- **Association becomes unconditional, preceded by a detach — and the detach refuses a minor it cannot attribute to itself.** A minor whose backing file is not one this fixture family creates is reported by name and the run fails, rather than being reclaimed. A verification mechanism that detaches a handle it cannot attribute can damage the machine it is running on, and a derived minor can still land on one the host holds. This guard is new to **all four** plays that detach, including the two that already detach unconditionally.
- **Every fixture asserts its device starts with no filesystem**, after associating and before converge. `superseded-path-retired` and `superseded-path-in-force-refused` already do; the other three gain it. This is the premise the later assertions rest on, checked rather than assumed, and it is the check that would have named the contamination immediately.
- **`.github/tests` gains a module asserting the static half**: that no authored fixture names a loop minor as a literal; that the ones deriving a device derive it from the variable `run-molecule` exports; that `run-molecule` exports the variable the fixtures read; that `run-molecule` derives that variable's value from the working tree's own path rather than from a constant, which is the property an entry point could satisfy the plumbing without having; that a file associating a loop device releases it earlier in the same file, reads what holds it before releasing it, and refuses on that read rather than merely registering it; that the checks over the fixture plays fail rather than pass where that enumeration is empty, which is the state they start in and the assertion the other three rest on; and that the workflow running the suite invokes the entry point rather than the tool.
- **`AGENTS.md`'s *Namespacing Molecule per working tree* names the third handle**, as entry 78 asks.
- **Not a change to `platform_data_volume` itself.** No task, default, README line or specification of the role's behaviour moves. The subject is the fixtures and the entry point that runs them.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-cicd-pipeline`: *Ansible Configuration Is Verified in Continuous Integration and Gates the Merge* gains the obligation that a fixture claiming a handle the machine's kernel holds derives it from a value the entry point supplies rather than naming it as a literal, that the entry point supplies it, that both are checked statically over the **fixture plays** and not only over the scenario definitions, that such a fixture establishes the handle is free and refuses one it cannot attribute, and that the workflow reaches the suite through the entry point. This extends the requirement's existing instance-name paragraph, whose static checks are scoped to `molecule.yml` and therefore do not reach the files this change protects.

`iac-repo-foundations`'s *Verification Writing to Shared State Is Namespaced per Working Tree* is **not** modified. Its run-time obligation is stated in terms of "state that outlives a single run and is reachable from more than one working tree on the same machine", which reaches a kernel-held handle as written, and the `AGENTS.md` binding it obliges is one this change extends rather than adds.

## Impact

**Ansible.** `ansible/scripts/run-molecule` gains the derivation and a second print flag. Thirteen fixture files under `ansible/roles/platform_data_volume/molecule/` change: the ten plays enumerated above, and the header comments of the three `molecule.yml` files that explain the hardcoded minor — `default`, `multiple-devices-discoverable` and `multiple-devices-reverse-order`. The two `superseded-path-*` scenario definitions carry no such paragraph, and `multiple-devices-reverse-order` imports its sibling's `prepare.yml` and has no play of its own to edit.

**Static tests.** A new `.github/tests` module. No existing module changes: the current namespace checks read instance names in `molecule.yml` and are untouched by a variable that appears in fixture plays.

**Continuous integration.** No workflow file changes, and this was established rather than assumed — `.github/workflows/ansible-verify.yml`'s Molecule step already runs `../../scripts/run-molecule test --all`, so the base arrives there exactly as the namespace does. That this keeps holding is what the new module's last assertion is for: it is the premise every fixture play's refusal now rests on, and nothing asserted it before.

A second premise was checked the same way and needed nothing: this change puts `ansible/scripts/run-molecule` in the class of files that determine what every scenario runs under, so a pull request touching only it must still run the suite. It already does, and it is already asserted — `.github/tests/test_the_suite_is_triggered_by_what_it_reads.py` carries that path in its `SELECTED_BY_THE_SUITE` set. No delta sentence is owed for a property this repository already checks.

**Documentation.** `AGENTS.md`'s *Namespacing Molecule per working tree* and its *Testing* section, both of which currently say Molecule shares **two** handles.

**Operations.** None. No workflow, stack, inventory or platform file is touched, so the merge starts no apply, no converge and no deploy. The Molecule matrix runs, because `ansible/` changed.

**This workstation.** The five minors above are orphaned by this change rather than reclaimed by it: nothing will ever detach them, and each holds a deleted sparse file whose blocks the kernel cannot free while the association stands. Detaching them is a one-time local command needing `sudo`, recorded in `tasks.md` rather than performed by the change.

**Not in scope, recorded instead.** Whether Molecule's own `cleanup` should detach a scenario's minor at the end of a run, so that associations do not accumulate at all. Entry 78 forbids the global sweep and says why; a per-scenario detach is not that, but it is a second mechanism with a failure mode of its own and it buys nothing this change needs. It goes to `docs/deferred-work.md`.
