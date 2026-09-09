# `docker`

Installs the container runtime by depending on the pinned external
`geerlingguy.docker` role, and owns the daemon's configuration.

The wrapper exists so `host-baseline.yml` composes same-shaped roles rather
than referencing the external role directly; `meta/main.yml` carries that
rationale and the `galaxy_info` diagnosis. Until this role gained the interface
below it had no variables of its own, which is why it had no README.

## Variables

| | Default | |
|---|---|---|
| `docker_log_max_size` | `"50m"` | maximum size of one container log file |
| `docker_log_max_files` | `"3"` | how many are retained |
| `docker_daemon_extra_options` | `{}` | anything else for `/etc/docker/daemon.json` |

Both log values are **strings**. The external role renders `daemon.json`
through `to_nice_json`, which writes an unquoted `3` as a JSON number, and the
daemon rejects a non-string `max-file`.

They are role defaults rather than values in
`ansible/inventory/group_vars/prod.yml` because an unbounded container log is
unsafe on any host this repository configures. Setting them from inventory
would hand unbounded logs to the next host built from this repository,
silently. `hardening` draws the same line from the other side: no default for a
source CIDR, because no value is safe in general.

`docker_daemon_extra_options` is merged **under** the log ceiling, so it can
add any daemon option and cannot remove the bound. That polarity is deliberate:
reversed, a caller adding an unrelated option could silently drop the ceiling,
leaving no trace in the rendered file.

## What the bound reaches, and what it does not

Satisfies "Container Logs Are Bounded by the Host's Daemon Configuration" in
`openspec/specs/iac-host-configuration/spec.md`.

**It reaches containers created after the daemon adopts the configuration.**
Docker resolves a container's log options at **creation**, so containers
already running keep what they were created with, and restarting the daemon
does not change them. On this host that means the containers running at the
time of a converge inherit the ceiling at their next deploy — `platform`'s at
the next platform deploy, `commerce-ops`'s at a deploy from that application's
own repository, which this one neither triggers nor waits for.

To confirm the bound after a converge you therefore have to create a container
on purpose. `docker create` resolves log options and starts no process, so a
throwaway container from an image already on the host answers the question at
no cost.

**It does not override a container that declares its own logging options.** A
daemon default is a default. The obligation is that a container which says
nothing is bounded rather than unlimited.

**It is a ceiling, not a diet.** This host has no log aggregation, so these
files are the only history an incident has to read. See `defaults/main.yml` for
the sizing and for when to revisit it.

## A converge that *changes* `daemon.json` restarts the daemon

`daemon.json` is now always rendered, but the external role renders it with
`copy:`, which is idempotent — so only a converge that **changes** the file
notifies its `restart docker` handler. A steady-state converge restarts
nothing, and the role's Molecule idempotence action would fail if it did.

When the file does change, `live-restore` is unset, so the daemon restart
**stops every container on the host** until each one's own restart policy
returns it — a few seconds, and self-healing for anything declaring
`restart: unless-stopped`, but not nothing. Time such a converge accordingly,
and expect every container's restart counter to step at once.

In practice that means the first converge after this role gained a daemon
configuration, and any later converge that alters one of the values above. Do
not read it as something every run does: an operator trained to expect a
restart on every converge will read an unexpected one as routine.

This is not Ansible starting an application: no task here names an application
or its stack, and what comes back is what the runtime was already holding. The
scope requirement in `openspec/specs/iac-host-configuration/spec.md` states
that distinction explicitly.

## A note for scenario authors

Three Molecule scenarios (`image_prune`'s two and `deploy_user`'s `default`)
need a `vfs` storage driver for their nested-container fixtures. They used to
write `/etc/docker/daemon.json` in `prepare.yml` and have it survive, which
worked only because this role supplied no daemon options and the external
role's render was gated on the dictionary being non-empty. It no longer is, and
that render is a `copy:` — an overwrite, not a merge. Pass
`docker_daemon_extra_options` in `converge.yml` instead.

Note also that a play-level `vars:` cannot override `docker_daemon_options`:
it is set as a dependency parameter in `meta/main.yml`, and role params outrank
play vars.
