# Design

## Decision 1: what the window actually measures, read from the module rather than assumed

The whole change rests on one option's semantics, so they are established from ansible-core's `lib/ansible/modules/apt.py`, at the version `ansible/requirements-test.txt` pins, read from the installed copy rather than from this repository, which vendors no module, not from documentation or memory.

```python
def get_cache_mtime():
    cache_time = 0
    if os.path.exists(APT_UPDATE_SUCCESS_STAMP_PATH):      # /var/lib/apt/periodic/update-success-stamp
        cache_time = os.stat(APT_UPDATE_SUCCESS_STAMP_PATH).st_mtime
    elif os.path.exists(APT_LISTS_PATH):                    # /var/lib/apt/lists
        cache_time = os.stat(APT_LISTS_PATH).st_mtime
    return cache_time
...
if p['update_cache'] or p['cache_valid_time']:
    tdelta = datetime.timedelta(seconds=p['cache_valid_time'])
    if not mtimestamp + tdelta >= now:
        # fetch
```

Three consequences, and the first is what makes this change safe rather than merely cheap:

- **The measurement is a timestamp, not a presence check**, and it matters which. `cache_time` is `0` only where *neither* the success stamp *nor* `/var/lib/apt/lists` exists. These platform images ship the directory — emptied at build — so what forces the first fetch is its **build mtime**, not its emptiness. The safety therefore rests on the images being old, which is a property of the digest pin rather than of the module. The pins are months old and a pin is a reviewable commit, so this holds; stating it as an absence guarantee, as an earlier draft did, would have claimed something the mechanism does not provide.
- **A never-fetched host fetches for the same reason**, its recorded time being the epoch or the build date, either of which is outside any window this change would consider.
- **Within one converge, the second and later apt tasks skip**, because the first one's fetch set the stamp minutes ago. That is the entire saving, and it is the only case the window changes.

`update_cache: true` stays on every task. The option is not being removed and replaced; a bound is being added to it. A task that reaches a stale index still refreshes.

**And the field the tests read is computed from that same mtime, which is a trap worth spelling out.** `cache_updated` is not "a fetch was attempted":

```python
cache.open(progress=None)
mtimestamp, post_cache_update_time = get_updated_cache_time()
if module.check_mode or updated_cache_time != post_cache_update_time:
    updated_cache = True
```

It is true only where the value `get_cache_mtime()` returns **moved across the update**. Everything the tests assert therefore depends on the forced fetch advancing the same path the fixture back-dated, and two of the three obvious ways to back-date do not satisfy that:

- **The success stamp is the worst choice**, and the most intuitive. `get_cache_mtime()` prefers it when it exists, `python-apt`'s `cache.update()` never writes it — it is written by apt's own `15update-stamp` hook, which this base image does not carry — so back-dating it pins the read value in the past for the rest of the play. Every subsequent task would report `cache_updated: false` however much it fetched.
- **Back-dating `/var/lib/apt/lists`'s directory mtime alone** is correct only if the re-fetch rewrites entries in it. A re-fetch minutes after the converge may resolve entirely to *not modified* and write nothing, leaving the directory mtime where the fixture put it.
- **Emptying the directory and then back-dating it** is the one that holds. The fetch must write entries back, which moves the directory's mtime to now, so the flag is true. The order matters and is easy to get backwards: deleting the contents sets the directory mtime to *now*, so the back-dating has to come after the emptying, not before.

That third form is what the tasks prescribe. It costs the same single fetch already budgeted, and it leaves the invocation's second apt task on the skip path, so the figure of two survives.

**Which path the module actually reads inside the pinned image was observed, not assumed.** Everything above depends on `get_cache_mtime()` falling through to `/var/lib/apt/lists` rather than finding a success stamp, and that is a property of the image rather than of the module — so it was checked against the digest the scenarios pin, `geerlingguy/docker-ubuntu2204-ansible@sha256:0172e3b5…`, on 2026-09-11:

```
/var/lib/apt/periodic/update-success-stamp    ABSENT
/etc/apt/apt.conf.d/15update-stamp            ABSENT      (the hook that would write it)
/var/lib/apt/lists                            exists, 0 entries, mtime 2026-08-10
```

So the module falls to the lists directory, whose mtime is a month old — outside any bound this change would consider — and the first apt task fetches. The fetch writes entries into an empty directory, which moves its mtime, so `cache_updated` is true; the second task then reads a timestamp seconds old and skips. All three behavioural assertions rest on this, and it is the kind of premise that is cheap to check and expensive to assume: had the stamp been present, the bound would have been inert, the saving zero, and the tests would have failed in a shape that names the assertion rather than the image.

The observation is pinned to a digest, so it stays true until someone changes the pin — which is a reviewable commit, and the right place for this to be re-checked.

## Decision 2: the window is one hour, expressed as a variable

**One hour.** A converge is minutes long, so an hour is long enough that one run fetches once, and short enough that two runs an hour apart do not share an index. It is also the value `apt.py`'s own documentation uses in its example, so it is the least surprising number a reader can meet.

The alternative worth naming is a window sized to the converge rather than to the clock — "fetch once per play" — which Ansible has no direct expression for. Simulating it means a `run_once`-style fetch task at the top of a role and `update_cache: false` everywhere below, which is a larger change, moves where a failure surfaces, and makes each role's apt tasks depend on a task elsewhere having run. The window achieves the same effect with no coupling and degrades gracefully: if an hour is wrong for a host, it is one variable.

**Expressed as a role variable, not a literal**, and defaulted in each role's `defaults/main.yml`. Two reasons. The value is a judgment about staleness that an operator may reasonably disagree with, and this project's roles already take their judgments as variables rather than burying them. And a literal repeated at three sites in two roles is three places to edit and two places to forget — the same drift this repository's image-pin rule exists to prevent, in smaller form.

## Decision 3: what the idempotence pass stops exercising, which is the sharpest cost

Today, Molecule's idempotence pass re-runs the role minutes after the converge, and every apt task fetches the index again. After this change it will not: the stamp is minutes old, the window is an hour, and the update is skipped.

**That is a real reduction in what the suite observes**, and it is the one thing about this change that is not free. What the idempotence pass stops covering is the second fetch's behaviour — a resolve against an index fetched twice in quick succession. What it continues to cover is everything the idempotence pass is actually for: that a second run reports no change, that no task is falsely `changed`, and that the installed state is stable.

The judgment is that the lost coverage is not coverage of this repository's code. A second `apt-get update` minutes after the first exercises the Ubuntu archive and `apt` itself, neither of which this repository owns or can fix, and its failure mode is exactly the upstream slowness that prompted the change. Stating it rather than discovering it later is the point; a reviewer who disagrees should say so, because it is the argument this change turns on.

## Decision 4: three tasks, and why `tailscale`'s fourth is not one of them

A fourth `update_cache: true` sits in `ansible/roles/tailscale/tasks/main.yml`, and leaving it is deliberate.

- **It installs from a source it adds in the same run.** The role writes `/etc/apt/sources.list.d/tailscale.list` and installs from it a few tasks later. This is the reason that survives the other two lapsing, and it is the nastiest: the index is *recent* — an earlier task in the converge fetched it — and *wrong*, because it predates the source just written. A bound consults the timestamp, finds it well inside the window, skips the fetch, and the package has no installation candidate while every other install on the host succeeds. The failure names the package, not the cause, and appears only on the run that adds the source.
- **It installs a pinned version**, `tailscale=1.102.3`. A pinned install is the case where a stale index does not merely return an older candidate but fails outright: the pinned version is absent from the index the host holds, and `apt` reports a version that cannot be located. The failure is loud rather than silent, which is some comfort, but it converts a slow converge into a broken one — a bad trade for a saving this role does not need.
- **The role has no Molecule scenario.** `ansible/roles/tailscale/` carries `README.md`, `defaults/` and `tasks/` and nothing else, so nothing in this project observes what it does to a host. `docs/change-queue.md` entry 3b already owns that gap. Changing the behaviour of the one role the suite cannot see, in the same change that reduces what the suite observes elsewhere, is the wrong place to spend the risk.
- **It costs nothing today.** Being in no scenario, it contributes zero to the continuous-integration time this change exists to reduce. Its only cost is on a real converge, which runs it once.

The three that change are the three that are both verifiable and repeated: `hardening`'s `ufw` and `fail2ban`, and `image_prune`'s `curl`.

## Decision 5: the prepare plays keep `cache_valid_time: 0`

Ten Molecule prepare plays declare it explicitly, and their comments record why: `geerlingguy.docker` 8.0.0 installs `ca-certificates` and `python3-debian` with `state: present` and **no** `update_cache` at all, which fails against a freshly created container whose cache is empty. The prepare refresh is what makes the external role's install work.

They are fixture setup rather than role behaviour, they run once per scenario, and weakening them to save a fetch would reintroduce exactly the failure they were written to prevent. They stay as they are — and they are also what makes the saving land: in a scenario carrying one, the role's own apt tasks arrive at an index fetched seconds earlier and skip.

`hardening` has no prepare refresh, so its first role task does the fetching and its second skips. Both shapes are covered.

## Decision 6: each assertion sits in the play whose invocation it characterises, and asserts the rule rather than the run

Round-2 review found the first plan's observation mechanism unrunnable, and the repository says so in its own words. `ansible/roles/image_prune/molecule/absent-heartbeat-key/converge.yml` records it: *"Molecule runs `converge` and `verify` as two separate ansible-playbook invocations, so no fact set here survives into verify.yml — a file on the instance is the channel."* On top of that, `hardening`'s converge invokes the role through `roles:`, where no caller-side `register` can reach a role-internal task at all.

The file-on-the-instance channel the repository uses elsewhere does not fit here either: its content would differ between the converge and the idempotence run, so the task writing it would report `changed` and fail the very idempotence check this change is careful to preserve.

**So each assertion sits in the same play as the invocation it characterises**, reading results the role's own apt tasks register. A register is a play variable; it reaches later tasks in that play and nothing beyond it.

That splits them, and the split is not a compromise but the rule applied twice:

- *A second install task in the same converge does not re-fetch* and *An install on a host with no record of a fetch still fetches* characterise **the converge's own role run**, so they assert in `converge.yml`, immediately after the role.
- *An index older than the bound is refreshed* characterises an invocation **the test itself makes**, so it asserts in `verify.yml`, beside the invocation already there. Putting that invocation in the converge play instead would cost four fetches rather than one — Molecule runs that play twice and the bound is one variable per role, so both apt tasks would fetch on both passes — and would falsify `converge.yml`'s own header, which records that the second invocation was kept out of that file to keep the idempotence check scoped to one state.

Both give up the assertions' usual home in `verify.yml` alone, and that is worth it: a register is the only channel reaching a role-internal result without a file, and it needs no fact caching, which this project configures nowhere.

**And they assert the rule, not the outcome.** This is the part that matters, and it is not merely tidier — the obvious phrasing is wrong. Molecule runs the converge play **twice**: once to converge, once for idempotence. On the second run the index was fetched minutes earlier, so the first apt task correctly does **not** fetch. An assertion reading "the first task fetched" would therefore fail against a correct implementation on the idempotence pass, and the natural repair — skipping the assertion on the second run — is an assertion that stops asserting exactly when it is inconvenient.

What holds on both runs is the rule itself:

```
before the role runs:   record the index's last-fetch time
after the role runs:    first apt task fetched   ==  (that time was outside the bound)
                        second apt task fetched  ==  false
                        the bound-0 invocation   ==  fetched, always
```

On the first run the recorded time is the image's build date, the antecedent is true, and the task fetched. On the idempotence run the recorded time is minutes old, the antecedent is false, and it did not. One assertion, correct on both, and it is the requirement's own sentence rather than a description of one run.

The cost is a `register:` on the three role apt tasks. That is a real edit to production role files for the benefit of a test, and it is accepted here for a narrow reason: `register` changes no behaviour, and this project's alternative — asserting on host state — cannot see the distinction at all, since a fetched and an unfetched index leave the same packages installed. That last point is the whole difficulty: **the change's effect is invisible in host state by construction**, which is why it must be read from the module's own result.

## What this is expected to save

Measured from `hardening`'s job on the pull request for `narrow-the-molecule-trigger-to-what-it-reads`, run under the degraded archive:

```
apt tasks              11.9m of a 15.6m job          76% of the job
worst single task      249.6s   (baseline 13.4s)     19x
fetches today          6
fetches after          1
```

**All six are in one container.** `hardening`'s `default` scenario converges the role three times — the converge, Molecule's idempotence re-run, and a second `include_role` inside its own `verify.yml` — at two apt tasks each. The `absent-ssh-cidrs` scenario contributes none: it aborts at the first assert, before any apt task, and its verify asserts that UFW was never installed. So the container fetches once and the remaining five tasks skip: `6 → 1`, not `6 → 2`.

That makes roughly `11.9m → 2m`, and the job from `15.6m → ~5.7m`, on a bad day.

**One fetch is added back by the tests themselves, and where it is added back matters more than that it is.** Establishing *An index older than the bound is refreshed* requires a run against a stale index, which costs a fetch. Putting that run in the **converge play** would cost four, not one: Molecule runs that play twice and the bound is one variable per role, so both apt tasks would fetch on both passes — returning four of the six fetches this change exists to remove, in the scenario every figure above is computed from. `verify.yml` runs once, after the idempotence pass, and already carries a third role invocation whose own header records that it was kept out of converge to keep the idempotence check scoped. Back-dating the index before that existing invocation costs **one** fetch and adds no invocation at all.

So the implemented figure is **two**: one in the first converge, one in verify. A reader comparing the prediction to a measurement should expect two, and should read five as the signal that the bound-0 run drifted back into the converge play. On a healthy day the same arithmetic applies to much smaller numbers and saves perhaps a minute. **The point is not the average; it is that the multiplier has six things to multiply and will have two.**

`image_prune` should benefit similarly or more — three of its four scenarios converge the `docker` role before its own, the fourth refusing at its heartbeat assertion before any apt task — but no measurement of its apt share is offered here, because none was taken, and the tasks ask for one alongside `hardening`'s.

## Risk: a converge installing from an index up to an hour old

The failure this introduces is not in continuous integration, where every container is fresh and every scenario's index is fetched within the run. It is on a long-lived host.

Sequence: a converge fetches the index, something is republished upstream within the hour, a second converge in that window installs from the older index. For `state: present` on a package already installed, nothing happens at all. For a package not yet installed, `apt` resolves the candidate the older index names — one version behind, at worst, for an hour.

Two things bound it. The packages involved are `ufw`, `fail2ban` and `curl`, installed once at bootstrap and `ok` on every converge afterwards — so the window is almost never consulted on a real host in the state the host is normally in. And unattended upgrades are what actually keep a running host's packages current — though on this host they run from the platform image's own defaults rather than from any role, which `docs/change-queue.md` records as an open gap with no `Automatic-Reboot` decision taken. That does not weaken the point and is worth stating precisely rather than crediting a role that does not exist: a converge is not the security-update mechanism, whoever owns that mechanism.

What would make this the wrong trade is a role that *installs a version*, which is why `tailscale` is excluded, or a host converged rarely enough that a converge is its only update path. Neither is true of the three tasks this change touches.

**One caveat runs the other way, and it is a caveat about the saving rather than about the risk.** On a host where `/var/lib/apt/periodic/update-success-stamp` exists and is maintained — apt's own `15update-stamp` hook writes it, and `apt-daily` runs it — `get_cache_mtime()` prefers that stamp, and `python-apt`'s `cache.update()` does not advance it. A converge's tasks would then keep reading the same timestamp and keep fetching, and the production half of this change's motivation would simply not be delivered. The failure direction is benign — the host fetches exactly as often as it does today, never from a staler index — but it is an open question rather than a settled one, and it is recorded here rather than discovered by someone comparing two converge logs. What the continuous-integration saving rests on is different and is established by observation, recorded in Decision 1: the pinned scenario image carries neither the stamp nor the hook that writes it.
