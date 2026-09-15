# Design

## Context

The requirement *Unreferenced Host Images Are Pruned on a Schedule* (`openspec/specs/iac-host-configuration/spec.md`) already specifies the completed run's report exactly: two counts, both deduplicated by image identity, `removed` anchored to this run's own invocations rather than to the host's state afterwards. It also already names the three outcomes that leave `removed` unchanged — a removal the runtime refused, a tag skipped because it no longer named the image it was selected as, and a tag dropped from an image that survives under another.

Those three are named and then not distinguished from each other, or from the far more common outcome of an image the keep set correctly protected and the run never touched at all. Everything that did not end in a deletion is folded into the gap between `considered` and `removed`, and `considered` counts the whole host. This change separates the first of the three out.

## Goals / Non-Goals

**Goals.** Make a removal the container runtime rejected countable and readable, on every run, without changing which images a run offers, which it removes, or what it exits with.

**Non-Goals.** Closing the blind spot entirely — see Risks, where the limit is stated plainly. Alerting. Reclaiming the image a refusal leaves behind. Any change to the keep set, the candidate set, the abandon conditions, or the exit status.

## Decision 1 — `refused` counts identities whose removal the runtime *rejected*, not identities that survived

The obvious definition is "attempted and not deleted". It is wrong, and wrong in the direction that would make the new field noise.

Three things can happen to a candidate identity once the run reaches it. The runtime deletes the image and says `Deleted:`, exiting zero. The runtime **rejects** the call, printing a `conflict:` diagnostic to stderr and exiting non-zero. Or the call succeeds, prints `Untagged:` alone and exits **zero**, having dropped a reference from an image the runtime is keeping for a reason of its own — the multi-tag case mid-loop, and the case where another image depends on this one's layers.

"Attempted and not deleted" collapses the second and third. The third is not a refusal in any useful sense: nothing pushed back, and on the ordinary multi-tag path it is what every removal but the last one looks like. A field that fires on it would read non-zero on healthy runs over ordinary hosts, which is exactly the "carries no signal" problem this change exists to fix, re-created one field to the right.

So `refused` is read from the **exit status** of the removal invocation. That is the only one of the three signals that separates a rejection from an untag: the multiple-repositories rejection exits 1, the untag-without-delete exits 0. Both were confirmed against Docker 27 with the `vfs` storage driver — the driver `ansible/roles/image_prune/molecule/default/converge.yml` pins for this role's fixtures — on 2026-09-15.

`removed` keeps reading `Deleted:` out of the invocation's output and does not move to the exit status, because the requirement fixes it as the count of identities "for which one of this run's own removal invocations reported the image deleted". A zero exit does not establish that: the untag case has one.

## Decision 2 — deduplicated by identity, with `removed` taking precedence

`refused` is a count over distinct image identities, like the two counts beside it, not over invocations. A two-tag image whose removals are both rejected contributes one. The line's shape is an invariant a reader will assume once two of its three fields hold it, and a per-invocation count would silently break it for exactly the multiply-tagged images this script handles specially.

Where an identity has both a deleted invocation and a rejected one it counts as `removed` and not as `refused`, so that `removed + refused` never exceeds `considered`. In the script as written the two cannot co-occur — a deletion makes the remaining tags unresolvable and the loop's re-check skips them — but stating the precedence means a later edit to the loop cannot make the invariant false by accident.

## Decision 3 — one new field, not two

The alternative considered was to report the **candidate** count as well — the identities the keep set did not reach — which would give the line a closed arithmetic: candidates equal removed plus refused plus skipped, and every shortfall would be attributable.

Rejected, on two grounds. The arithmetic does not actually close: the skipped term is the re-pointed-tag case, which the existing suite's own header records as unobservable in a black-box scenario, so the field that would balance the equation is the one field nothing can assert. And the diagnosis a reader needs does not need it. `refused R` with R above zero says the run offered something the runtime would not give up, and the per-refusal lines say which image and why; `refused 0` says every shortfall between `considered` and `removed` was an image the keep set protected. That is the question the backlog entry asks, answered with one field, and the entry names one field.

A candidate count remains a reasonable later addition. It is not blocked by anything here.

## Decision 4 — each refusal is named, not only counted

The count alone cannot be acted on. On this host two causes are expected, and they are not the same problem:

- *"container X is using its referenced image"* — the keep set did not contain an image a container holds, so the keep set is wrong, and the runtime's refusal is the last thing that stood between it and a live image. This is the class the requirement's *Removal SHALL NOT be forced* clause exists for.
- *"image is referenced in multiple repositories"* — an untagged image carrying two digest references, removed by identity because it has no tag to drop. Nothing is wrong with the keep set. The image is simply unreclaimable by this script, and will be offered and rejected on every run for the life of the host.

The remedy for the first is to find the defect in the keep set; for the second there is no remedy inside this change at all, and an operator needs to know that rather than go looking for one. The requirement already takes this position for a different pair — an absent enumeration versus an empty one — on the grounds that a report conflating two conditions with different remedies sends an operator to the wrong place. The same reasoning applies here, so the runtime's own message is carried to stderr, one line per refused identity, rather than reconstructed or classified by the script.

**Those two are the causes expected on a managed host, not the whole set the runtime can produce.** *"image has dependent child images"* is a third, returned for an untagged image whose layers another image builds on, and `-f` cannot override that one either. Production and staging pull images rather than build them, so it is not expected there — but it is not theoretical, and the evidence is this change's own fixture host: see Decision 7. Carrying the runtime's own text rather than classifying it is what makes an unanticipated cause readable instead of misfiled, and it is why the documentation names its causes as the expected ones rather than as a list to match against.

Capturing stderr is the only part of this that touches existing code paths: the invocation currently sends it to `/dev/null`. It is captured into the same single-slot temporary file the reference-resolution step already uses for this purpose, on the same reasoning — one message at a time, so a message that must be attributed to one identity is not mixed with another's.

## Decision 5 — the count is appended to the line, not inserted

`considered N, removed M, refused R`. Appending keeps the existing pair adjacent and in the order a reader already knows, and keeps every static match on the current line true rather than breaking it in the same commit that changes the thing it guards.

**That the scenario's existing shape assertion keeps passing is not a reason to leave it alone.** It matches `considered N, removed M` unanchored, so it passes against a three-field line while establishing nothing about the third field — which is the difference between a migration that is safe and a guard that is complete. It is listed as this change's obsolete test for that reason: it survives the change and must be strengthened to match all three fields, or two of them stay guarded and the new one does not.

## Decision 6 — the refusal fixture is a multiply-referenced digest, because a container-held one is unreachable

The new count has to be drivable to a non-zero value by a test, or it is a guard that could be inverted and still pass — the false-green shape this role's existing scenario was explicitly written to avoid, and which its `verify.yml` header lists three properties as deliberately *not* asserted rather than assert vacuously.

The refusal an operator would expect — a container holding the image — cannot be arranged from outside the script. Every container's image is in the keep set by construction, so a container-held image is never a candidate and is never offered. Making it one needs a seam between the run's container enumeration and its removal loop, and there is none.

The multiply-referenced digest case needs no seam. One image identity, pushed to two repository paths, pulled back by digest with its build tags dropped, is an identity carrying two references and no tag. The script's own by-identity removal path — the path it takes precisely *because* there is no tag to drop — is the one the runtime rejects with *"must be forced — image is referenced in multiple repositories"*, exit 1. Nothing about the fixture is contrived to produce a failure: it is the digest-pinned class this mechanism was built to honour, arranged so that the host has it from two registries rather than one.

The `default` scenario already runs a local registry inside the instance for its digest-pin fixture, and already builds images and pushes to it, so this costs one more build and two more pushes.

**The fixture is split across `converge.yml` and `verify.yml`, and which half goes where is load-bearing rather than tidiness.** The registry half — build, tag into two repository paths, push both — is fixture construction and belongs with the rest of it in `converge.yml`, next to the readiness probe that push loop already is. The host half — pulling both references back by digest — belongs in the arrangement step inside `verify.yml`, **after** every keep-set and removal assertion and **before** the two abandon arrangements, which is the ordering that file already declares load-bearing.

Building the whole fixture in `converge.yml` was the obvious placement and does not work. Everything in that file exists before the scenario's first run, so the identity would be refusable from that run onward and every run would report a refusal — leaving *A run whose removals were all performed reports no refusals* with no run in this role's suite to assert against. Split, the same host yields both: the first run reports no refusals at all, and a run below the arrangement reports the fixture's.

**The count below the arrangement is not asserted as a literal, and Decision 7 is why.** The assertion is that the post-arrangement run's output carries a refusal line naming the fixture's own identity, and that its refused count is **exactly one greater** than the count reported by the run immediately preceding the arrangement — two runs bracketing the arrangement with nothing else changed between them. That form uses the per-refusal naming this change specifies anyway, and it is indifferent to whatever else the host happens to refuse.

The split has a premise the converge half must assert rather than assume: after pushing, the host holds **no** local image for that identity. Dropping the two build tags by name is in fact sufficient — a push gives the identity a `repo@digest` reference in each repository, and removing a repository's last tag drops that repository's digest reference with it, so the second removal deletes the image and the host ends empty-handed. Observed on the same rig and date as everything else here.

The assertion is not guarding a known failure, then; it is guarding a property that belongs to the runtime rather than to this fixture, in a step whose whole purpose is to leave the host in a particular state. A reference surviving would reintroduce the whole-in-converge placement through the back door, and what it would cost depends on how many survive: two, and the first run's by-identity removal is rejected and the `refused 0` assertion fails loudly; one, and the first run deletes the identity, which costs nothing because the arrangement re-pulls it. Neither is silent, and that is the argument for asserting rather than for elaborating the cleanup.

One thing the cleanup must **not** do is remove by identity. `docker image rm <id>` on an identity carrying two repository references is the very rejection this fixture exists to produce, so a cleanup written that way fails on its own subject.

Putting a build and two pushes in `converge.yml` while the pull-back sits in `verify.yml` is not a departure from how that scenario is written: `verify.yml` already builds images inline for its abandon arrangements, and the registry interaction stays where the probe that guards it is.

That the fixture survives its own run is the point and is asserted: a rejected removal removes nothing.

## Decision 7 — the fixture host refuses a second identity by construction, and the assertions accommodate it rather than remove it

The `default` scenario pulls `alpine:3.19` and builds every fixture image it has from it with the classic builder, which records a parent link from each child to that base. No enumerated application references `alpine` and no container holds it, so it is a candidate on every run — and it behaves differently on the first run than on every run after it, in a way that turns out to demonstrate two of this change's own distinctions:

- On the **first** run it still carries its tag, so the by-tag path takes it. The removal untags it, the runtime keeps the image because its children depend on its layers, and the invocation exits **zero**. Correctly not a refusal — this is Decision 1's third category, occurring by itself on the rig. One surviving child is enough for this and for the rejection below; the scenario has a dozen and this change adds another, so nothing here is sensitive to the exact number.
- From the **second** run on it is an untagged identity with dependent children, so the by-identity path takes it, and the runtime rejects that with *"cannot be forced — image has dependent child images"*, exit 1. A refusal, and the third cause Decision 4 names.

Both observed on the pinned rig on 2026-09-15. So the fixture host produces refusals this change did not arrange, from its second run onward, and any assertion phrased as a literal count below the arrangement would be wrong about the host it runs on — reading as a defect in the accumulator, which is the most expensive way for a test to be wrong.

The alternative was to put `alpine:3.19` into the fixture host's keep set, restoring an exact count. Rejected: it adds a reference to a Compose file whose purpose is not evident from reading it, it perturbs the identity and row counts the first run's `considered` assertion is tied to, and it would delete the one piece of direct evidence this repository has that Decision 4's third cause is real. The named-line-plus-delta form above costs one more assertion and survives the host changing underneath it, which is the better trade for a scenario that already carries eleven fixtures.

It is worth being explicit that this is a property of the **fixture host** and not of the hosts the requirement describes. Production and staging pull images and build none, so neither carries a parent chain; the scenario carries one because building fixtures is how it makes images at all.

## Risks / Trade-offs

**`refused` sees only the defects the runtime blocks, and that is a real limit on what this change claims.** A keep set that offers an image no container holds — an image of a defined-but-never-started service, or one behind an inactive profile, which are exactly the classes the union exists to protect — is not refused. It is removed, successfully, and counted in `removed`. No count in this line can see that, and adding one would not help: a run cannot tell an image it was right to remove from one it was wrong to remove, which is why the keep set is computed the way it is rather than checked afterwards. This change narrows the blind spot to the class the backstop catches; it does not close it, and the README says so rather than implying otherwise.

**A host carrying a multiply-referenced image reports `refused 1` every week forever.** A recurring non-zero number with a known cause is the kind that gets tuned out — this repository has met that before, in the staging prune's expected weekly failure. The mitigation is that the per-refusal line names the image and the reason each time, so the state is readable rather than merely persistent, and that the backlog entry this change opens says what removing it would take. It is not muted here, because a suppression list is a mechanism with its own failure mode and there is currently nothing on either host that needs one.

**Neither host is known to carry such an image today.** The condition this change makes visible may well report zero on both for a long time. That is the expected outcome of adding a signal that was previously absent, and not evidence the change did nothing: before it, a host that did carry one was indistinguishable from a host that did not.
