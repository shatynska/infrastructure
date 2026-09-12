# `hostname`

Sets the host's own name, and makes the host resolve it.

Satisfies *The Host's Own Name Is Set by the Converge* (`openspec/specs/iac-host-configuration/spec.md`).

## Why it exists

Cloud-init sets a host's name once, at creation, from the name the provisioning layer gave the server — and nothing re-sets it. Renaming a server in Terraform therefore produces a host answering to a name no committed file states, and **nothing fails**. Before this role, the production host answered to `main-server` and would have gone on answering to it after its server was renamed, indefinitely.

## The two names a host has, and why they differ

| Name | Value | Set by |
|---|---|---|
| The host's own name | `shatynska-main-production` | this role |
| The name it reports to the tailnet | `main-production` | the `tailscale` role's pin |
| The tailnet **machine** name | `main-production` | the Tailscale interface — nothing in this repository |

The divergence is the naming rule doing its job rather than an oversight. `inventory_hostname` lives inside a repository belonging to one company; the host's own name is read on a workstation that may serve two, and is the only repository-side value that reaches one. The tailnet belongs to one company and holds every stack it owns, so a name reaching it does not need the company in it — and must not have it, because every unattended consumer resolves the server's name. See `docs/naming-conventions.md`.

## Inputs

| Variable | Required | Default | Notes |
|---|---|---|---|
| `company` | **yes** | none | The operating company. Supplied from `ansible/inventory/group_vars/all.yml` — that file, and not an environment's variables file, because it is the single value a clone of this repository operated by a different company changes. |
| `hostname_loopback_address` | no | `127.0.1.1` | The address the host's own name is mapped to in `/etc/hosts`. Debian and Ubuntu use `127.0.1.1` rather than `127.0.0.1` for this. |

`company` has **no default**, and the role asserts it by name in its first task — per *A Role's Absent Required Input Is Reported by Name*. A default would name every host for whoever wrote this role, and the name it builds is the one an operator reads on their own workstation. The check is deliberately the role's first task: an unsupplied input has to be a refusal rather than a host renamed and then abandoned mid-converge.

## Two things that move together

**The name and the resolution.** `ansible.builtin.hostname` goes through `hostnamectl` and touches nothing else, so `/etc/hosts` keeps answering for the old name. Ubuntu's `sudo` then emits `unable to resolve host <name>` on every privileged task for the rest of the converge and on every login afterwards. It is a warning and not a failure, which is exactly why it would survive unnoticed: nothing goes red, the converge reports success, and the only person who ever sees it is the operator — every single time they log in. The role sets both.

## Where it runs in the play, and why the position is not arbitrary

Immediately **after** `tailscale`, in `ansible/playbooks/host-baseline.yml`.

Until that role pins it, the name a host reports to the tailnet is derived from the name this role is about to change. Running this role first would tell the tailnet a name nothing intends, for as long as the rest of the converge takes or fails in. `.github/tests` asserts the order, because it is held by nothing else and that play has been reordered before.

An earlier draft of the change that added this role put it first, on the reasoning that nothing depends on it. That reasoning was wrong, and it is recorded here rather than quietly dropped — "nothing depends on this" is the kind of claim that reads as obviously true, which is why the dependency went unnoticed.

## Testing

`ansible/scripts/run-molecule test --all`, from this directory. Two scenarios:

- `default` — converges the role against an instance created under a different name, and verifies the host answers to the derived name, that `/etc/hosts` maps it, that `getent` resolves it, and that `sudo` emits no warning.
- `absent-company` — verifies the run fails at an explicit check naming the variable and the file it belongs in, and that the host's own name was **not** changed before the run stopped.

The `default` scenario asserts the derived name's length before the role runs. Under Molecule `inventory_hostname` is the instance name, which carries the per-working-tree namespace, so a long enough working-tree name pushes the derived name past the kernel's 64-byte limit. The guard names the working tree as the cause rather than letting it surface as a failure inside `hostnamectl`.
