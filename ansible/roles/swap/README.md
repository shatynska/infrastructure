# `swap`

Gives the host a swap file and a swap-tendency policy that survive a reboot.

Satisfies "The Host Carries Swap That Survives a Reboot" in
`openspec/specs/iac-host-configuration/spec.md`.

## What it establishes

| | |
|---|---|
| `/swapfile` | 4 GiB by default, `0600 root:root`, formatted with `mkswap` |
| `/etc/fstab` | a `swap` entry, so a boot activates it without a manual step |
| `/etc/sysctl.d/60-swappiness.conf` | `vm.swappiness = 10` |
| the running kernel | the file swapped on, and the tendency applied — unless `swap_activate` is `false` |

## What it does not do

**It does not fix a memory leak.** It converts a hard out-of-memory kill into a
slowdown. That matters here because the OOM killer chooses by resident size
rather than by which process leaked: on this host the largest resident
processes are Postgres and Prometheus, so the likeliest victim is not the
culprit. Swap buys `HostMemoryPressure` — which is computed from
`MemAvailable/MemTotal` and is unaffected by swap existing — the ten minutes it
needs to fire.

**It does not alert on swap filling up.** Once swap exists, "swap is 80%
consumed" is the signal that a leak is underway and the killer is next.
`node_memory_SwapFree_bytes` is already scraped; the rule belongs in
`platform/docker-compose.yml`, and is recorded in `docs/change-queue.md`.

**It does not size container memory limits.** That is the companion piece, and
it is blocked on observation data rather than on this role.

## Why a file on the root filesystem

Not a partition: one cannot be added to an already provisioned host without
repartitioning it.

Not the attached `main-data` volume, and this is the one placement the
specification forbids by name. It is a network block device, so it would make
the kernel's last-resort memory tier depend on the component least able to
tolerate the pressure that makes swap necessary — and it is the volume
`platform/`'s Postgres, Prometheus and Grafana bind-mount.

## `swap_activate`

**A test affordance. Not a production switch.** `host-baseline.yml` does not
set it, and should not.

Activation is the one part of this role that writes state the run does not own.
`swapon` registers the file with the kernel, and `vm.swappiness` is **not** a
namespaced sysctl — so on a host sharing a kernel with others, both reach
outside the machine being configured. Every Molecule scenario in this
repository runs `privileged: true` with `cgroupns_mode: host`, so both writes
leave the instance.

The two halves differ in how far, and it is worth knowing which is which.
Tested on 2026-09-08 by removing this role's activation gate: `swapon` fails
outright with `Invalid argument`, because the instance's filesystem is an
overlay and the kernel refuses a swap file on overlayfs — so on that rig the
file half is unreachable rather than merely guarded, though it would reach the
kernel on a rig where activation can succeed. The live `vm.swappiness` write
has no such obstacle: the sysctl is not namespaced and no filesystem is
involved, so it changes the runner's own kernel.

With it `false`, the file, its permissions, its `fstab` record and the sysctl
file are all established and no kernel state is touched. That separation is
itself part of the requirement, so the variable is not a hole cut for the tests
— the tests are what make it observable.

**What follows for verification.** The Molecule scenario establishes the
configuration and nothing about activation. Swap actually being on, the live
tendency, and the guard against reformatting a file the kernel is swapping to
are all observed on the host instead, at the confirm gate. The change's own
`test-plan.md` records which of the two claims each scenario makes.

## Reboot persistence

`/etc/fstab` and `/etc/sysctl.d/` are the records; nothing here observes a
boot. To exercise those records through the same mechanisms a boot uses,
without rebooting:

```
swapoff -a && swapon -a     # returns swap from /etc/fstab
sysctl --system             # re-applies the tendency from /etc/sysctl.d/
```

**If `swapon -a` brings nothing back, the `fstab` record is wrong and the host
now has no swap.** Recover with `swapon /swapfile`, which does not consult
`fstab`, then fix the record and re-converge before leaving the host.

## Resizing and removal

Resize: `swapoff /swapfile`, delete the file, change `swap_size_mb`,
re-converge. The role will not resize a file in place — `creates:` guards the
write, so an existing file of the wrong size is left alone rather than
truncated under a running kernel.

**The same refusal meets a host that already had swap of its own.** An existing
`/swapfile` of a different size — the Ubuntu installer's default arrangement —
fails the run with the recovery above rather than being adopted or truncated.
Two things follow. It is deliberate: truncating a file the kernel may be
swapping to destroys the pages it holds, and silently adopting one means the
host does not have the size that was configured. And because this role runs
**last** in `host-baseline.yml`, that refusal arrives after every other role has
already applied — the run is not wasted, but the failure is late, and on a host
in that state the first converge is expected to fail once.

Remove entirely: `swapoff /swapfile`, delete the `fstab` line, delete the file,
delete the sysctl file. Nothing on the host depends on any of them being
present.

## Idempotency

A re-converge changes nothing. Three guards do that work, and only the first is
about tidiness:

- `dd` is guarded by `creates:`.
- `mkswap` runs only when the file is **neither active nor already formatted**.
  Guarding on the file's absence instead would be wrong in both directions:
  writing a signature over a file the kernel is swapping to corrupts the pages
  it holds, and a run interrupted between `dd` and `mkswap` leaves a file that
  exists and is unformatted, which an absence guard would skip forever.
- `swapon` runs only when `/proc/swaps` does not already list the file.
