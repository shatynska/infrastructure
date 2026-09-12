# Design

## Decision 1: namespace the minor, rather than only detaching it unconditionally

`docs/change-queue.md` entry 78 leaves this open: "whether the minors should be namespaced per working tree the way the instance name is, or simply always torn down", and says the judgment belongs to the change.

An unconditional detach at the start of `prepare` is the cheaper half and it does fix what was actually observed — a tree's run inheriting its own previous run's device. It is not enough, and the reason is that `namespace-the-molecule-suite-per-working-tree` made it not enough. Before that change, two working trees could not run one role concurrently at all: they collided on the container name and one of them failed at `create`. Now they can, and the loop minor is what is left holding them together. Under unconditional detach alone, a second tree's `prepare` detaches the minor the first tree's `converge` is mid-flight on, and the two possible outcomes are a confusing failure in the first tree or — if the second tree re-associates before the first tree's next task reads the device — a pass produced against another tree's backing file. That second outcome is the exact shape `iac-repo-foundations`'s requirement exists to forbid.

So: namespace it, **and** detach unconditionally within the namespace. The two are not alternatives. The namespace separates trees; the detach separates a tree's consecutive runs from each other, which no namespace can do because the namespace is by construction the same one each time.

## Decision 2: the base comes from `run-molecule`, as a second exported variable

The derivation could live in either place, and the test suite already asserts that "the authored scenarios agree on one namespace variable" for instance names — so a second variable is worth arguing for rather than assuming.

It lives in `run-molecule`, exported as `INFRA_WORKTREE_LOOP_BASE`, for two reasons.

**A minor is a number and the namespace is a name.** `INFRA_WORKTREE_NS` is `<sanitised basename>-<6 hex>`, chosen so that `docker ps` answers *whose container is this*. Nothing about a loop device shows a name, so the two handles cannot share one value. Deriving a number from the name inside Jinja is possible — `hash('sha1')`, a hex slice, `int(base=16)`, a modulus — but it would have to appear in each of the ten plays that name a device, in a template language with no place to put a shared function, and the arithmetic would then be committed ten times in fixtures whose whole purpose is to be read quickly.

**The existing "one variable" property is about what a session sets by hand, and a session sets neither.** That assertion reads instance names in `molecule.yml` and exists so that a session cannot namespace itself by knowing one variable and not the other. `run-molecule` sets both, from one root path, in one place, so the property it protects is unchanged: there is still exactly one thing a session does to take its namespace, and it is running the entry point.

Each scenario adds a fixed offset to the base — `default` 0, `multiple-devices-*` 1 and 2, `superseded-path-retired` 3, `superseded-path-in-force-refused` 4 — so today's scenario-to-minor mapping survives the change with only its origin altered, and a reader comparing before and after is comparing one thing.

## Decision 3: the band is 1024 to 33784 in steps of 8

`base = 1024 + (digest mod 4096) * 8`, over the same six hex digits of the absolute working-tree path that `namespace_for` hashes. Four thousand and ninety-six slots of eight minors, of which five are used and three are spare for a scenario added later.

**Why not from 0.** The kernel allocates loop minors from the bottom upward — `losetup -f` hands back the lowest free one — so the low end is where a machine's real loop devices are. On this workstation `/dev/loop0` and `/dev/loop1` hold Docker Desktop's ISO cache; an Ubuntu desktop with snaps can hold thirty or forty. The existing literals at 87 to 91 were chosen high for exactly this reason, and the change should not spend that.

**Why the band is not capped at 255.** A first draft of this design stopped at 248, on the unexamined assumption that a loop minor is a byte. It is not: a device number carries twenty bits of minor, and the loop driver creates a device on first open of any minor below that ceiling rather than only the ones `max_loop` pre-created. Verified on this workstation inside the pinned scenario image, whose `/sys/module/loop/parameters/max_loop` reads `8`: `mknod -m 0660 /dev/loop<m> b 7 <m>` followed by `losetup` succeeded and detached cleanly at 1024, 1032, 5120, 33768, 33784 and 33788. Both endpoints of the band above are in that set.

**Why the slot count matters, and why 4096 rather than 24.** Two working trees that hash to the same slot collide on all five minors, and the collision is not loud: Decision 1 establishes that after the sibling namespacing change two trees running one role concurrently collide on *nothing else*, so there is nothing to fail first. A colliding `prepare` detaches the other tree's association, and the backing-file prefix the attribution guard checks matches — it establishes that the holder is *a* run of these fixtures, not that it is another tree's — so the guard permits it and the first tree can go on to assert against the second tree's device. That is the false pass this change exists to remove, reintroduced at the collision rate. With 24 slots that rate is 1 in 24 for any concurrent pair, which is not "namespaced per working tree" in any sense the requirement's own scenario would accept; with 4096 it is 1 in 4096, and the residual is small enough to state as a residual rather than to manage with a rule telling sessions not to run concurrently. The cost of the difference is one literal in `loop_base_for()`.

**Why a modulus at all rather than a registry.** A registry of allocated minors would make the collision impossible rather than unlikely, and it is a mechanism this repository would then have to keep correct — a file to write, to read under concurrency, and to reclaim from removed working trees, none of which the two existing namespaced handles need. The residual above does not earn that.

**Why an eight-wide slot rather than a five-wide one.** A scenario added to this role later takes the next offset and needs no thought about the band. Five would make the next addition a change to the derivation, which is the kind of edit that gets made in one place and not the other.

## Decision 4: the detach refuses a minor it cannot attribute, rather than reclaiming it

The detach is what makes the fixture correct, and it is also the one new thing in this change that can damage the machine it runs on. `losetup -d /dev/loop5` inside a privileged container detaches the host's `/dev/loop5`, whatever the host was using it for. A derived minor is a number nothing outside this repository has agreed to leave alone.

So the fixture reads the association before acting on it — `losetup --noheadings --output BACK-FILE`, verified on this workstation to print the backing path — and detaches only where that path is one this fixture family creates, all of which are `/root/platform-data-volume-*.img`. Anything else fails the play, naming the minor and what holds it.

That prefix is not a strong identity and is not claimed as one: it establishes that the holder is *a* run of these fixtures, not that it is *this tree's* run, which is why Decision 3 cannot lean on it to make a slot collision loud. It is the strongest attribution available, because the backing file path the kernel records is the path inside the container that made the association, and every one of those containers is gone by the time anyone reads it. What it buys is the whole of the damage case — a host's own loop device, a different project's, a `snap` mount — and it costs nothing in the case it cannot separate, where detaching is the right action anyway.

**It goes into all four plays that detach, not only the two that gain a detach.** `superseded-path-retired` and `superseded-path-in-force-refused` already detach unconditionally, and until this change they detached a minor a human had chosen. After it they detach a derived one, which is precisely the condition that makes the guard necessary, so they need it more than they did rather than less.

**What is specified is the static shape, not the run-time refusal — and the static shape includes the refusal, not only the read.** A first draft of this delta obliged the play to *read* what holds the handle before releasing it, which a play that reads, registers the result and then releases regardless satisfies in full: the strong sentence and the weak check sat adjacent with nothing marking the gap. That is the shape `AGENTS.md` names as worse than an admitted convention. The obligation now requires that a refusal stand between the read and the release, which is as static a property as the release's position in the file and is exactly what task 3.6 implements.

The run-time behaviour behind it still cannot be staged in this repository — the guard lives in `prepare`, and Molecule runs nothing between `create` and `prepare` in which a foreign association could be planted for it to refuse — and the delta says so in its own prose rather than leaving a reader of the archived requirement to infer it from the scenario's scope.

## Decision 5: the refusal is a task in every play, not a refusing default in the name

`molecule.yml`'s instance name takes the other approach — a default value Docker refuses — and it is the better mechanism where it is available, because it cannot be forgotten. It is not available here. Every expression that turns a base into a device path runs through `| int`, and `| int` turns anything it does not understand into `0`. `/dev/loop0` exists on this workstation and holds Docker Desktop's ISO cache; a converge that reached it would format it. There is no spelling of the default that both survives the arithmetic and cannot name a device.

So each of the **ten** plays refuses as its **first task**, before anything has touched the host. Three plays for each of the three single-device scenarios, and one for `multiple-devices-discoverable/prepare.yml`, which `multiple-devices-reverse-order` imports rather than copying. Three plays per scenario rather than one, because `prepare`, `converge` and `verify` are separate `ansible-playbook` invocations with no channel between them — the same fact that made the minor a hardcoded literal in the first place. The assert is four lines and names `ansible/scripts/run-molecule` in its `fail_msg`, which is the sentence a session reading the failure needs.

The play that matters most here is the one with the least to say about it: `multiple-devices-discoverable/prepare.yml` claims *two* devices and its sibling arm reuses them, so an unset base there reaches `/dev/loop0` and `/dev/loop1` together.

## Decision 6: minors stay fixed per scenario rather than being allocated at run time

`losetup -f --show` allocates a free minor atomically and would remove the shared handle outright, with no band, no modulus and no collision. It was rejected for what it does to the leak.

A fixed minor is reused: five associations exist on this workstation no matter how many times the suite has run. An allocated minor is not: each run takes a fresh one and nothing gives it back, so the count grows with the number of runs, and each association holds a deleted sparse file whose blocks the kernel cannot free. A month of development would leave hundreds. The obvious remedy — detach in `cleanup` — does not hold, because a run that fails between `prepare` and `cleanup` never reaches it, and a failing run is the common case while a change is being built.

Bounded-and-stale beats unbounded-and-tidy here. It also matches what `AGENTS.md` already says of namespaces generally: they accumulate, they are named after the tree, and nothing reclaims them.

## Decision 7: the two `multiple-devices` arms keep sharing one pair of minors

`multiple-devices-reverse-order` imports `multiple-devices-discoverable`'s `prepare.yml` deliberately, so that the two arms cannot drift into asserting different things. They therefore share offsets 1 and 2, and one arm runs against a minor the other arm left associated.

That is safe for the same reason a tree's consecutive runs are safe: the unconditional detach runs at the start of every `prepare`, and Molecule runs a role's scenarios sequentially. Giving each arm its own offsets would mean the offset could no longer be a literal in the imported file — it would have to come from `MOLECULE_SCENARIO_NAME` — which spends the property the import exists to protect in order to buy something the detach already provides.

## Decision 8: what the static suite asserts, and what it does not

`iac-cicd-pipeline` already obliges that a static property of committed files reaching outside the role directory be asserted by `.github/tests` rather than by the Molecule suite — a Molecule assertion covers only the pull requests that trigger that scenario, and the suite's trigger is narrowed by change detection. Seven properties qualify and are asserted: that no authored fixture names a loop minor as a literal; that a fixture deriving a device derives it from the variable `run-molecule` exports; that `run-molecule` exports the variable the fixtures read; that `run-molecule` derives that variable's value from the working tree's own path; that a file associating a loop device releases it earlier in the same file, reads what holds it before releasing it, and refuses on that read; that the checks over the fixture plays fail rather than pass where that enumeration is empty; and that the workflow running the suite invokes the entry point rather than the tool.

One of those seven holds the rest up: that the enumeration of fixture plays *deriving* a device is not empty. The subset matters and the wider set will not do — plays that touch a loop minor at all are non-empty today, by literal, which is precisely the state these checks exist to forbid, so counting those would report the enumeration healthy in the one condition that empties every other check over it. Every check over the subset reports green on an empty one, and the interpolation check is green on an empty set **today**, before any fixture derives a device — so the vacuous state is not a hypothetical this change guards against in advance, it is the state the checks start in. This requirement already refuses an empty set in three other places, for its role discovery, its image pins and its tracked-file scan, and the reason is the same each time: a check that cannot fail establishes nothing, and "the tests pass" is exactly what hides it.

Three of the others exist because nothing else connects the halves they join, and each was added only after asking what would make the check itself pass vacuously. The entry point is shell and the fixtures are Jinja, with a variable name between them: a rename on either side produces an unset value, not an error. A variable that is exported but computed from a constant satisfies every check about the variable's *existence* while restoring the shared literal the change removes, so the derivation is checked and not the export alone. And the fixtures' refusal is only a safe mechanism if the workflow actually reaches them through the entry point — `.github/workflows/ansible-verify.yml` does today, by a line no assertion read until now, and this change makes every scenario in the matrix depend on it.

One premise that would otherwise belong here needed no work: `ansible/scripts/run-molecule` is now a file that determines what every scenario runs under, so the suite must run on a pull request touching only it. `.github/tests/test_the_suite_is_triggered_by_what_it_reads.py` already asserts exactly that, carrying the path in its `SELECTED_BY_THE_SUITE` set, so the property is checked and no delta sentence is owed for it.

The remaining candidate — that each fixture asserts its device starts with no filesystem — is deliberately left to Molecule. It is a claim about what a run establishes rather than about what a file says, and the static form of it would be a substring search that any rearrangement satisfies vacuously. Molecule asserts it by executing it, which is the distinction `AGENTS.md`'s *Testing* section draws between the two suites.

The new module excludes scenarios shipped by Galaxy content installed from `ansible/requirements.yml`, deriving that exclusion from the manifest, by reusing `test_ci_configuration.py`'s existing helpers rather than restating the rule.
