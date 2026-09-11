## Context

Three layers reach infrastructure from this repository. Terraform reaches
Hetzner through `pr-validation.yml` → `apply.yml`, with a saved plan and a
`production`-gated apply. The platform stack reaches the host through
`platform-deploy.yml`, with a credential-less diff and a `production`-gated
deploy. The host layer reaches the host from a workstation, with
`ansible-playbook`, a Vault password that exists on one machine, and a tailnet
auth key typed at a prompt.

Everything this change needs from the repository already exists.
`configure-the-staging-host` parameterised the play over its environment, gave
each environment an inventory source naming its own read-only credential, and
added a guard play that refuses when the target group resolves to no host.
`make-the-pipeline-environment-agnostic` gave each environment a committed
`terraform/environments/<name>/pipeline.yml` naming its GitHub Environment and
its read-only secret, so no workflow names an environment.
`connect-platform-deploy-via-tailscale` put a tailnet between CI and the host and
an OAuth client in the `production` Environment. Staging exists, is converged,
and is what this is developed against.

What does not exist is any mechanism by which a committed change under
`ansible/` reaches a host without somebody typing a command.

## Goals / Non-Goals

**Goals**

- A merge to `main` touching `ansible/` converges every environment's host,
  through the same gated shape the other two layers use.
- The Vault password and the CI credential live in GitHub, per environment, so
  losing one workstation does not lose the ability to converge.
- The workflow names no environment, and adding one adds no line to it.
- The converge reaches the host over the tailnet, so entry 25 can close public
  SSH afterwards without locking CI out.

**Non-Goals**

- Scheduled drift detection for the host layer (Decision 10).
- A role that owns `root`'s `authorized_keys` (Decision 5).
- Closing public SSH, which is entry 25 and waits on this.
- Factoring the four environment-discovery bodies into one artifact
  (Decision 2).

## Decisions

### Decision 1: The reviewer's artifact is the `ansible/` diff, not a check-mode run

`apply.yml` shows its approver a **saved plan** and applies that exact file.
There is no equivalent for Ansible, and `--check --diff` is not one, for reasons
`docs/bootstrap-a-new-host.md` §6.3 already states and this change inherits:
`command` tasks skip under `--check` — `ops_user`'s three and `swap`'s four —
and `geerlingguy.docker` carries `ignore_errors: "{{ ansible_check_mode }}"` on
five tasks, so failures there are swallowed. A check-mode run is honest about
files and packages and blind to anything a command drives.

It is also the wrong *shape* for a pre-approval artifact, independent of what it
can see: it has to authenticate to the host, so it needs the credential the gate
exists to withhold. A pre-approval job holding the converge credential is the
gate's own defeat, which is why `platform-deploy.yml`'s `diff` job carries a
comment saying it must start immediately with no access to the deploy
credential.

So the artifact is the one `platform-deploy.yml` already uses: the git diff of
this merge, restricted to the layer's directory. That is not a weaker substitute
for a plan — for this layer it is *complete* in a way a Terraform diff is not.
Everything Ansible applies is committed: the roles, the play, and every
environment's `group_vars`. There is no provider computing an unknown, and no
state file to disagree with. What the reviewer cannot see from the diff is what
the host currently is, which is drift, and Decision 10 says where that belongs.

### Decision 2: Discovery runs over inventory sources, cross-checked against the pipeline declarations

The workflow must name no environment, so it needs the same two facts the
Terraform workflows need: which environments exist, and for each, its GitHub
Environment and the repository secret holding its read-only Hetzner token.

The obvious move is a fourth copy of the ~160-line discovery body the three
Terraform workflows share, which `.github/tests` asserts stays identical across
them. This change does not do that, for two reasons that are about correctness
rather than about tidiness:

- **It discovers over the wrong root.** That body enumerates
  `terraform/environments/*/`. An environment with a Terraform directory but no
  `ansible/inventory/<name>.hcloud.yml` is one this workflow cannot converge, and
  a row for it in the matrix would fail deep inside `ansible-playbook` on a `-i`
  path that does not exist. The set this workflow runs over is the set of
  inventory sources.
- **It needs a cross-check that body cannot make.** Both directions are silent
  failures worth refusing by name: a source with no environment directory has no
  declaration, so no GitHub Environment gates it; an environment directory with
  no source has a host converged by nothing, which reads exactly like an
  environment with nothing to converge. The Terraform body sees only one of the
  two sets and can refuse neither.

So this workflow's discovery is a different discovery: it enumerates
`ansible/inventory/*.hcloud.yml`, derives each environment name from the
filename, and reads `github_environment` and `read_only_secret` out of that
environment's declaration with the same flat-mapping `field()` reader idiom. It
refuses, by name and with a non-zero exit, on: a source whose environment
directory or declaration is absent; a declaration missing either field, or
carrying a `read_only_secret` that is not a usable GitHub secret name; a source
with no `ansible/inventory/group_vars/<name>.yml`; an environment directory
carrying a declaration but no source; and an empty result. It takes nothing from
the event, so `.github/tests` can execute it against a scratch tree the way it
already executes the Terraform body.

The consequence is four near-siblings where there were three, which is the point
at which the existing comment's "Copies are not the only available shape … Edit
them together, or factor them out together" stops being theoretical. Factoring
them out restructures three gated workflows and rewrites the assertion that makes
running one copy evidence about the others; doing that inside this change would
put a refactor of the production apply path in the same diff as the first
pipeline that converges a host. Recorded as a queue entry instead. The identity
assertion over the three Terraform workflows is not weakened by this change and
is not extended to cover a body that is deliberately not identical.

### Decision 3: The converge reaches the host over the tailnet, and the address is a per-run inventory option

The `hcloud` inventory plugin sets `ansible_host` to the server's public IPv4 by
default, and the cloud firewall admits SSH from one operator ISP `/24`. A GitHub
runner is in neither, so a converge from CI over the public address cannot
connect, and widening the firewall to GitHub's ranges is not a boundary worth
the name.

The tailnet is already there. `platform-deploy.yml` joins it with an OAuth
client tagged `tag:ci`, `hardening` admits SSH from `100.64.0.0/10`, and the
operator already logs in that way (§6.4). The plugin has a built-in option for
this: `connect_with: hostname` sets `ansible_host` to the server's Hetzner name,
which is the host's own hostname and therefore the name its tailnet peer carries.

It cannot be unconditional. The **first** converge of a host happens before the
host is on the tailnet at all — joining it is what the `tailscale` role does —
so a source that always resolved to the tailnet name would make the bootstrap
path unreachable. So each source reads the option from an environment variable
and defaults to `public_ipv4`:

```yaml
connect_with: "{{ lookup('ansible.builtin.env', 'HCLOUD_CONNECT_WITH') | default('public_ipv4', true) }}"
```

**The converge job sets it, in the job's own `env:` block**, so that every step
of that job inherits one value: the preflight that derives the address to
keyscan (Decision 7) and the play that dials it read the same variable, and
there is no second place for the two to disagree. Setting it on individual steps
would make that disagreement possible; setting it at workflow level would reach
the credential-less `diff` job, which connects to nothing and has no business
carrying a connection setting.

**The Hetzner token cannot ride in that block, and the reason is a property of
Actions rather than of this design.** Each inventory source reads a credential
under a name of its own — `HCLOUD_TOKEN_PROD`, `HCLOUD_TOKEN_STAGING` — so the
job would need an `env:` entry whose *key* comes from `matrix`. Actions
evaluates expressions in `env:` **values**; a key is a literal. Every `env:` key
in this repository's six workflows is a literal, and `apply.yml`'s plan step is
not the counter-example it looks like: it pairs the fixed key `HCLOUD_TOKEN`
with a dynamic value, which works only because Terraform's provider reads one
name whatever environment it is planning. The Ansible sources deliberately do
not have that property — `prod.hcloud.yml`'s own comment argues that a shared
name makes which project a run reaches depend on shell state rather than on the
file the run names.

So the token is written once, by the converge job's first step, as a
`<name>=<value>` line into `$GITHUB_ENV`, with the name from the matrix and the
value from `secrets[…]`. From that step onward it is in the job's environment
exactly as a block entry would have been, so the single-source property this
decision claims holds for the token too — it is established by a step rather
than declared by a block, and the difference is one line of shell, not a
weakening. Giving every source a shared fallback variable would remove the step
and is rejected: it is the hazard the per-environment names exist to prevent,
and it would reach the workstation, where shell state is real.

Local runs are unchanged by construction — the variable is not in
`ansible/.envrc` and nothing else sets it. A value the plugin does not recognise
fails at option validation, naming the choices; a *wrong but valid* value
(`public_ipv6`, say) fails at connection rather than converging something else,
because the address only decides which host to talk to and every other guard —
the environment parameter, the group's emptiness, each role's own assertions —
is unaffected by it.

Naming the host rather than carrying a committed tailnet address is deliberate.
`platform-deploy.yml` needs a literal IPv4 for Docker's port publish and
therefore carries `PLATFORM_DEPLOY_HOST`; SSH needs no such thing, and a
committed or secret-held `100.x.y.z` per environment is one more thing to be
wrong after a rebuild.

**But the runner resolving that name through MagicDNS is not assumed.** It was,
in an earlier draft, and the assumption does not survive being looked at.
`tailscale/github-action@v4` builds its `tailscale up` as `up`, the tags,
`--hostname=…`, `--accept-routes`, then whatever `args` supplies — it passes
neither `--accept-dns` nor its negation, so the CLI default applies and MagicDNS
is *probably* on. "Probably" is the wrong footing for the mechanism every
converge depends on, and this repository's own practice leans the other way:
`docs/bootstrap-a-new-host.md` records `PLATFORM_DEPLOY_HOST` as the tailnet
IPv4 because "the literal IP avoids a resolution step", and `platform-deploy.yml`
resolves a possible name to an address with `tailscale ip -4` for the one
consumer that cannot resolve one itself.

So the job resolves the name itself and stops depending on the resolver: after
deriving each address (Decision 7), `tailscale ip -4 "$name"` returns that peer's
`100.x.y.z` — a lookup in `tailscaled`'s own netmap, with no DNS involved at all
— and the pair is written to `/etc/hosts`. Everything downstream is unchanged:
the keyscan and the play still use the name, `ansible_host` is still the name,
and there is still one string. What changes is the failure mode. Under MagicDNS
a failure means "the resolver is not configured the way we assumed", which reads
as a broken runner; under this it means "the peer is not in the netmap", which is
true, actionable, and the same thing `tailscale ping` would have told you.

That is also why `tailscale ip -4` is the migration's check of the *name* and not
of resolution: it establishes that the server's Hetzner name is the name
`tailscaled` knows the peer by, which is exactly what the mapping needs, and it
would succeed with MagicDNS switched off — so it was never evidence for the
assumption it was credited with.

### Decision 4: No Tailscale auth key moves into CI, and that is sound rather than lucky

`tailscale_auth_key` is supplied at the prompt today and is consumed by exactly
one task, guarded by a `when:` that is false on an already-joined host. The queue
entry warns against leaning on that — an expired node would abort mid-play on an
undefined variable at the worst possible moment — and it is right that *absence*
is not an answer.

Decision 3 supplies a better one. CI reaches the host **through** the tailnet, so
a host that is not on the tailnet is a host CI cannot open an SSH session to. The
run fails at connection, before the first play, with a name-resolution or
connection error rather than a censored `no_log` failure deep inside the third
role. There is no reachable state in which a CI converge both connects and needs
to run `tailscale up`.

So the job supplies `-e tailscale_auth_key=''` — defined, so nothing aborts on an
undefined variable, and never templated, because the guarding `when:` is false on
every host CI can reach. One residual path exists and is worth naming rather than
hiding: a host that is on the tailnet but whose `tailscale status` returns
something unparseable satisfies the `when:` (its POLARITY comment makes
unparseable mean *not connected*, on purpose), and `tailscale up --authkey=` then
fails with the censored error §6.3a describes. That is a loud failure on an
already-diagnosable host, not a silent wrong action, and §6.3a is the existing
procedure for it.

Minting a short-lived key from the existing OAuth client would also work and is
what the queue entry suggests. It is not done here because it buys nothing: the
key would be usable only in a state CI cannot reach, and it would need the OAuth
client widened with auth-key write scope to obtain it.

### Decision 5: A dedicated `ansible-ci` keypair per environment, installed out of band

The credential is a genuine widening and the queue entry says so: CI would hold a
key that logs in as `root`. That is strictly more than `PLATFORM_DEPLOY_SSH_KEY`,
which is pinned to a forced command, and more than a Hetzner token, which can
destroy the server but cannot read it.

Three properties are wanted and two are cheap. **Distinct from the operator's own
key**, so a compromise of one is not a compromise of the other and rotating CI's
does not re-key the human. **Distinct per environment**, for the reason
`deploy_apps` already gives: one leaked private half must not converge both
hosts. Both are had by generating two keypairs and putting each private half in
its own environment's GitHub Environment.

The third — **revocable by converge** — is not cheap. No role manages `root`'s
`authorized_keys`; the file's single entry arrives from Hetzner at server
creation, and `hcloud_server.ssh_keys` cannot be changed without recreating the
server. Making a role own that file is the kind of change that locks every
operator out of a host when its input is wrong, it needs its own Molecule
scenarios, and it would arrive in the same diff as the first pipeline that
converges a host. So the public half is appended by the operator, once, during
bootstrap, and revoking it is an edit on the host.

That is not a regression: root's *existing* key is unmanaged in exactly the same
way. It is a gap, it is disclosed, and it is queued. The chicken-and-egg the
queue entry names is real either way — the role that would install the key is a
role CI runs, so the first installation is manual whichever shape this takes.

### Decision 6: Production's read-only secret is renamed to `HCLOUD_TOKEN_PROD`

This is a defect this change found rather than a preference, and it is invisible
until a job that declares an `environment:` reads an environment's *declared*
read-only secret — which no job did until now.

*Credential Scoping by Privilege* requires every environment's GitHub Environment
to define `HCLOUD_TOKEN` as that environment's **Read & Write** token, and GitHub
resolves an Environment secret ahead of a repository secret of the same name.
Production's declaration says `read_only_secret: HCLOUD_TOKEN`, which was
harmless while only the ungated plan and drift jobs read it. The converge job
declares `environment: production`, so `secrets[matrix.environment.read_only_secret]`
inside it resolves to production's **write** token — silently, with no error,
handing Hetzner write access to a job that only needs to list servers.

Renaming production's read-only repository secret to `HCLOUD_TOKEN_PROD` removes
the collision at its root rather than working around it in one workflow. It makes
the two environments symmetric (`HCLOUD_TOKEN_STAGING` already carries this
shape), and it is the name `ansible/.envrc.example` already uses for the same
token locally. The rule it exposes goes into the spec: an environment's declared
read-only secret name SHALL NOT be one its GitHub Environment also defines, and
`HCLOUD_TOKEN` is such a name for *every* environment.

Two alternatives were considered and are worse. **Reading the token in the
ungated job and passing the resolved host address on** turns a dynamic inventory
into a static one constructed at run time, against the *Dynamic Inventory via
hcloud Plugin* requirement, and loses the `keyed_groups` the `group_vars` are
keyed on. **Letting the converge job use the write token** satisfies *Write
Credentials Confined to the Gated Pipeline* but contradicts *Credential Scoping
by Privilege*, and does so in the one job that also executes an external Galaxy
role.

**Half of this is statically checkable and that half is checked.** Whether a
GitHub Environment defines a secret is repository settings, which nothing here
can read. But *Credential Scoping by Privilege* already obliges every Environment
to define `HCLOUD_TOKEN`, so the proposition "no environment declares
`read_only_secret: HCLOUD_TOKEN`" follows from a rule this repository states and
is a static read of a committed file — exactly what `.github/tests` is for. That
assertion is added, and it is what makes the delta's *A declaration naming the
write token's own name is refused* scenario enforced rather than merely written
down. What stays unverifiable is the general form — a declared name shadowed by
some *other* Environment secret this repository never names — and that is left to
the spec's wording and to `pipeline.yml`'s own comment.

The migration below sequences the rename so no window exists where either name
is unresolvable.

### Decision 7: Host-key verification is trust-on-first-use over the tailnet, against an address the inventory derives

`ansible.cfg` sets `host_key_checking = True` and CI has no committed
`known_hosts`. The job therefore runs `ssh-keyscan` before the play, which is
what `platform-deploy.yml` already does.

Trust-on-first-use is weak on an open network and is not one here: the keyscan
travels inside the tailnet, where the peer is authenticated by its node key
before any TCP connection is established, and the cloud firewall does not admit
the runner on the public address at all. A committed per-environment host key
would be stronger in principle and wrong in practice — it changes on every
rebuild, and a stale one fails a converge for a reason that looks like an attack.

**Where the address comes from is the part that needs stating**, because the
workflow may name no environment and Decision 3 rejects both a committed address
and a secret holding one. `platform-deploy.yml` can keyscan
`secrets.PLATFORM_DEPLOY_HOST`; this job has no such secret and must not grow
one. The only source is the inventory, and the preflight in Decision 9 already
queries it:

```sh
ansible-inventory -i inventory/<environment>.hcloud.yml --list \
  --vault-id <environment>@"$vault_password_file" \
  | jq -er '._meta.hostvars | to_entries[] | .value.ansible_host'
```

One step, doing both jobs. It forces every `!vault` block to decrypt and it
prints the addresses the play will dial — and *only* those, which is why it can
be piped where a bare `--list` could not: `jq` narrows a document carrying
decrypted secrets down to the one field wanted. `-e` makes an empty result a
non-zero exit, and `set -o pipefail` makes a failure on the left of the pipe fail
the step. Because the selection of Decision 3 is already in the environment, the
address derived is the address the play uses — there is no second place for the
two to disagree.

**`jq`'s own stderr is discarded, and that is not fussiness.** On a parse failure
`jq` quotes the text near the failure, and a Vault-decrypted value is not a
registered secret, so GitHub masks nothing. The narrowing is exposure-free on the
success path only; on the failure path the discard is what makes it so, and a
fixed message naming the environment replaces what was thrown away.

**Three failures meet here and each is named.** `ansible-inventory` failing —
a rejected token, a wrong Vault password — names itself on stderr. The other two
are silent by default and are given messages: a derivation that yields no address
is the environment's group resolving to no host, which
`iac-host-configuration`'s *A Run Whose Target Group Resolves to No Host Refuses*
gives a careful diagnostic for that the play never reaches, because this step
fails first — so this step says it, naming the environment; and a keyscan that
obtains no key exits 0, so the step asserts it produced one. A fail-closed body
in these workflows that ends in a bare exit code is a body that reports less than
every sibling it sits beside.

**The keyscan is this job's first contact with the tailnet, and must wait for
it.** `platform-deploy.yml` carries nine lines about this: a new tailnet peer
propagates with a brief, eventually-consistent delay, and the steps after the
join would otherwise race it. That job mitigates it with `ping:` on the join
action, which this one cannot copy — `ping:` takes an address, and this job does
not know the address until the step that derives it, which is after the join. So
the wait moves into the keyscan: it retries, bounded, until it yields a key, and
fails naming the environment and the address when the bound is reached. That is
also why the emptiness assertion above is not redundant with the retry — the
retry is what makes an empty scan mean *unreachable* rather than *not yet*.
Without it the race is silent: `ssh-keyscan` exits 0 having obtained nothing, and
the failure surfaces later as a connection error or a host-key mismatch, which
read as a wedged host and as an attack respectively. Neither reads as
propagation, which is the failure `platform-deploy.yml` already paid for once.

The alternative is `StrictHostKeyChecking=accept-new`, and it is worth being
exact about what choosing the keyscan does and does not buy, because the
intuitive answer is wrong. On a runner whose `known_hosts` starts empty every
run, the host is *always* unknown, so `accept-new` accepts whatever key is
offered — and so does `ssh-keyscan`. The two are equivalent in what they trust.
The keyscan is chosen for two lesser reasons, neither of them a security
argument: it is the shape `platform-deploy.yml` already uses, so one reader
learns one pattern; and it fails at a step named for what it was doing, rather
than inside `ansible-playbook`'s connection phase. Anything stronger than either
would need a `known_hosts` that persists across runs, which is a change to what
this repository commits and not a flag.

### Decision 8: Every environment converges on every `ansible/**` merge, and staging is not sequenced ahead of production in workflow text

A change under `ansible/` is almost never environment-specific: the roles and the
play are shared, and only `group_vars/<name>.yml` belongs to one environment.
Narrowing the matrix by changed path would leave an environment un-converged
after a role change, which is the state this whole change exists to end. So every
discovered environment gets a row, with `fail-fast: false` so one environment's
failure does not leave the other unreported.

Sequencing staging ahead of production would be valuable and is not done, because
every way of expressing it names an environment — a `needs:` edge, a condition, a
sorted `max-parallel: 1` matrix whose order happens to put `prod` first anyway.
What sequences it instead is production's own approval gate: both rows start in
the same run, staging's converge runs unattended, and the approver reads its
result before approving production's. That is exactly how `apply.yml` stages a
two-environment merge today, and it is a property of the Environments' protection
rules rather than of workflow text.

`concurrency` is per environment with `cancel-in-progress: false`. A converge
must not be cancelled mid-play: the host is left partially converged, which §6.3a
describes and which is recoverable, but cancelling one to start another makes
that the normal case rather than the exception.

### Decision 9: The Vault password moves into GitHub, per environment

Today it exists in one password manager and one operator's head, and a second
operator means handing it over. After this change it also exists as an
`ANSIBLE_VAULT_PASSWORD` secret in each environment's GitHub Environment, written
to a file under `umask 077` and passed as `--vault-id <environment>@<file>`.

Two things about the vault-id label. It must be the environment's name, because
that is the label the `group_vars` blocks were encrypted under — `;1.2;AES256;prod`
and `;1.2;AES256;staging`. Production's `ghcr_pull_token` is an older `1.1` block
carrying **no** label at all; Ansible tries every supplied secret against an
unlabelled block, so one `--vault-id prod@file` decrypts both. That is a runtime
property of a file this change does not edit, so the first production converge is
where it is established, and the migration below puts a decrypt-only check ahead
of it rather than discovering it mid-play.

A staging-only operator still must not hold production's password: the two
Environments hold different values, and the `staging` Environment requires no
reviewer, so its secret is readable by any merge that reaches its converge job.
That is the same boundary staging's Hetzner token already sits behind, and it is
why the passwords were separated in the first place.

**A wrong password must not be discovered mid-play.** Ansible decrypts a
`!vault` value lazily, at the moment it is templated, and the first such moment
in `host-baseline.yml` is inside `deploy_user` — the *fourth* role. A converge
that starts with the wrong password therefore installs Docker, enables UFW and
joins the tailnet before it fails, which is the partially-converged host §6.3a
describes, reached for a reason that had nothing to do with the host. So the job
runs a preflight before the play, built on `ansible-inventory --list`: it
serialises the group's variables, which forces every `!vault` block in that
environment's `group_vars` to decrypt, and it exercises the Hetzner token and the
`keyed_groups` grouping in the same command — the three inputs a converge needs
before it touches anything.

Serialising those variables means *printing* them, so its output must never
reach the run log or the disk. Decision 7 needs one field out of that same
document, and the two are therefore **one step**: the `--list` is piped straight
into `jq`, which emits the connection addresses and nothing else. That is why
this decision states the preflight and Decision 7 states the command.

### Decision 10: Drift detection stays out, and §6.3 changes anyway

The queue entry's framing is right — `--check --diff` against the live host is
the host layer's `drift.yml`, not its `terraform plan` — and that framing is what
puts it outside this change rather than inside it. Nothing in a converge pipeline
needs it: the gate's artifact is the diff (Decision 1), and a drift sweep is a
scheduled workflow with a liveness report, an issue reporter and a baseline
problem of its own.

That baseline is the reason it is not a cheap addition. Two `tailscale` tasks —
*Add the Tailscale apt signing key* and *Add the Tailscale apt repository* — are
`get_url` with no `checksum:`, and `get_url` to an existing destination with no
checksum reports **changed** under `--check` because confirming a match would
mean downloading the file. A drift detector whose baseline is two is one an
operator learns to skip. Fixing it means either pinning a checksum upstream
rotates, or replacing the tasks — and the `tailscale` role carries no Molecule
scenario to regress against, which entry 3b already owns as its own change.

So drift becomes a queue entry that inherits three things: the `changed=2`
remedy, the role's first scenario as a prerequisite, and §6.3's paragraph. §6.3
changes in *this* change regardless, because it currently says entry 23 owns
removing those two tasks; after this change entry 23 is archived and did not, so
the sentence must point at the entry that does.

### Decision 11: `workflow_dispatch` takes a free-text environment, validated by discovery

Converging one environment on demand — re-running a converge that failed, or
reaching a host after a change that did not touch `ansible/` — needs a trigger
that is not a merge, and a `workflow_dispatch` input of type `choice` would
enumerate environments in workflow text, the one thing the pipeline's own
requirement forbids. So the input is a free-text string, and discovery refuses a
value it did not discover, naming what it did.

**It is not what proves this change works, and cannot be.** A workflow is
dispatchable only through the default branch's workflow listing, so this file
cannot be dispatched until it has merged — the constraint `ansible-verify.yml`'s
header already records. The first run of this workflow is therefore the merge
itself, which is why the Migration Plan puts staging in front of production's
approval rather than in front of the merge, and why everything provable without
the workflow is proved before it.

An **absent or empty** input selects every discovered environment; only a
non-empty value is matched against discovery and refused. Every `push` supplies
an empty one, so conflating empty with unresolvable would fail discovery on every
merge — the distinction this repository already draws by name in its refusals,
load-bearing here rather than stylistic.

A dispatched run has no push range and therefore no diff; its `diff` job says so
rather than printing an empty code fence. The gate is unaffected — a dispatched
production converge waits for the same approval.

### Decision 12: The converge job is provisioned from this repository's own pinned manifests, and runs the suite's `ansible-core`

A GitHub runner carries no Galaxy content and no Ansible this repository has
chosen. The converge job's *first* command loads the `hcloud` inventory plugin,
and its play's first role is `geerlingguy.docker`; neither is present on the
image, and `AGENTS.md` already names the presentation this produces — a run that
fails deep inside a mechanism, reading as a broken mechanism rather than as an
unprovisioned machine. So the job checks out, installs, and only then runs, in
the four steps `ansible-verify.yml` already uses: checkout, Python, the pinned
toolchain, then `ansible-galaxy collection install -r ansible/requirements.yml`
followed by `ansible-galaxy role install -r ansible/requirements.yml -p
ansible/roles`. Two commands because `-p` applies to roles only, which that
workflow's comment states and this one inherits rather than rediscovers.

**Every command runs from `ansible/`**, named once at job level, and that is not
cosmetic. Ansible loads `./ansible.cfg` from the current directory: from the
repository root it loads none, `roles_path = roles` does not resolve, and
`any_unparsed_is_failed` reverts to its default — which is the setting
*Dynamic Inventory via hcloud Plugin*'s "an inventory source whose credential is
absent or is rejected SHALL fail the run" clause is false without, as
`ansible.cfg`'s own comment says. A converge run from the wrong directory does
not fail; it loses a guard, and reports a rejected token as a destroyed server.

**Which manifest pins the converge's `ansible-core`.** Reusing
`ansible/requirements-test.txt` would install Molecule and its docker driver into
a job that verifies nothing. So the converge gets `ansible/requirements.txt`,
pinning `ansible-core` alone — but pinned to **the same version**
`requirements-test.txt` names, and that agreement is asserted rather than
intended. The property is worth having on its own terms: the Ansible that
converges production is then the Ansible the Molecule suite verified those roles
under, which is otherwise a coincidence nobody would notice breaking. It is also
a static read of two committed files, so `.github/tests` is where it is checked.

Be exact about what the split does and does not buy, because the obvious claim is
the wrong one: it does **not** decouple the converge's Ansible from the test
toolchain. The asserted equality does the opposite — a bump to
`requirements-test.txt` that moves `ansible-core` now *must* move
`requirements.txt` too, or the check fails. That coupling is retained
deliberately and is the point of the requirement. What the split buys is that the
converge installs no Molecule, and that such a movement arrives as a visible
two-file commit rather than as an automatic consequence of a test-toolchain bump.
`requirements-test.txt`'s own Molecule-driven constraints are therefore the
effective floor for the converge's Ansible as well — which is worth knowing
before bumping either — and if the queue entry below ever brings these files
under Dependabot, the two entries must move as a pair or the check will fight it.

Dependabot covers neither file, and this change does not make that worse or
better: *Automated Dependency Updates* obliges the `terraform`, `github-actions`
and `docker-compose` ecosystems and names no `pip` ecosystem, and
`.github/dependabot.yml` configures none — so `ansible/requirements-test.txt` and
`.github/requirements-ci.txt` are already uncovered today. Adding a third
uncovered pip manifest is not a new class of gap, but it is one more thing behind
a pin nothing watches, and it is recorded as a queue entry rather than left as an
observation inside this change.

## Risks / Trade-offs

- **The first pipeline converge of production can wedge the host.** A converge
  that breaks UFW or `tailscaled` locks CI out of the host it is converging.
  Mitigated in three ways, none of which is the workflow: staging converges first
  in every run and is where this is developed; the ISP `/24` remains open until
  entry 25 closes it, so a wedged tailnet still leaves the operator a way in; and
  Hetzner's console is ungated by the cloud firewall. Entry 25 must not precede
  this change — the queue entry says so and this change does not change that.

- **CI holds a root credential.** Real, unavoidable for a converge, and bounded
  by: a keypair distinct from the operator's and per environment, an Environment
  gate in front of the job that reads it, and reachability only over a tailnet
  whose ACL admits `tag:ci`. Not bounded by revocation-through-converge, which is
  Decision 5's disclosed gap.

- **A partially-converged host now happens without anyone watching.** §6.3a's
  procedure was written for an operator sitting at the run. The mitigation is
  that it is the same procedure — re-run the same converge, every role being
  idempotent — and that a failed job is visible where a failed workstation run
  was not.

- **Renaming production's read-only secret has a window.** Sequenced in the
  migration so both names resolve at once; the plan and drift jobs read whichever
  the declaration names, so the declaration changes last.

- **A new environment's first merge produces a red converge row, by
  construction.** Adding an environment means adding an inventory source, which
  is a change under `ansible/**`, which triggers this workflow — against a host
  that has not been bootstrapped and is therefore on no tailnet. Decision 8 puts
  every discovered environment in the matrix, so that row fails at connection.
  This is accepted rather than worked around: the alternative is a declaration
  field saying "do not converge me yet", which is a second place for an
  environment's readiness to be recorded and a second place for it to be wrong.
  What makes it tolerable is that it is loud, isolated by `fail-fast: false`, and
  ends at the environment's first manual converge. The bootstrap document says so
  at the point where an operator adds an environment.

- **The server's Hetzner name is assumed to be the name `tailscaled` knows the
  peer by.** True because the host's hostname is its server name — which is also
  why the prune check is called `main-server-prune-host-images` — but it is a
  tailnet property, not a repository one, and the workflow cannot prove it in
  advance: a workflow is dispatchable only once it is on the default branch, so
  its first run is the merge. The migration therefore proves it without the
  workflow, before the merge, with `tailscale ip -4 <server name>` from a tailnet
  peer — which is a netmap lookup and is evidence for exactly this and for
  nothing about DNS. If it returns no address the name is wrong, and Decision 3's
  derivation needs another source: a decision to raise rather than to patch
  around in the workflow.

  It is also, newly, a risk about that name being **unique on the tailnet**.
  Tailscale deduplicates machine names by suffixing, and a rebuilt host joins as
  a new node while the old one persists — indefinitely, since §6.4 has the
  operator disable key expiry on it. The bare name then belongs to the dead
  peer: `tailscale ip -4` returns its address, the mapping succeeds against a
  corpse, and the converge fails at a keyscan whose message reads as an
  unreachable host. Nothing has met this yet because this change is the first
  consumer of the name at all — §6.3 dials the public address and
  `PLATFORM_DEPLOY_HOST` is a literal IP. The remedy is a line in Appendix B's
  rebuild sequence and a cause named in the failure message, both of which this
  change makes; the vendor behaviour is asserted from outside this repository and
  is confirmed in the admin console before being written down as fact.

  What this is *no longer* a risk about is MagicDNS. An earlier draft rested on
  the runner resolving that name and credited this same command with proving it;
  it proves no such thing, and Decision 3 now removes the dependency rather than
  arguing about it.

## Migration Plan

Repository work lands first and changes nothing about how the host is converged
until the operator does the settings work, because the workflow's trigger is a
merge touching `ansible/**` and this change touches `ansible/inventory/` — so the
sequence matters.

1. **Before the merge**, the operator adds the repository secret
   `HCLOUD_TOKEN_PROD` with production's existing Read Only token value, leaving
   the old `HCLOUD_TOKEN` repository secret in place. Both names now resolve.
2. **Before the merge**, the operator generates two `ansible-ci` keypairs,
   appends each public half to `root`'s `authorized_keys` on that environment's
   host, and adds per environment: `ANSIBLE_SSH_PRIVATE_KEY`,
   `ANSIBLE_VAULT_PASSWORD`, and — for `staging` only — copies of
   `TAILSCALE_OAUTH_CLIENT_ID` and `TAILSCALE_OAUTH_SECRET`.
3. **The merge** carries the workflow, the inventory change and the renamed
   declaration. It touches `ansible/**`, so it triggers a converge of both
   environments: staging runs unattended, production waits for approval. Do not
   approve production's until step 4.
4. **Read staging's converge**, and only then approve production's. A failure
   here is a failure of this change, not of the host.
5. **After the first production converge**, the operator deletes the repository
   secret `HCLOUD_TOKEN`. The `production` Environment's `HCLOUD_TOKEN` — the
   write token — stays exactly as it is; it is a different secret at a different
   scope, and `apply.yml`'s guard that the two differ depends on the Environment
   one continuing to exist.
6. **The Vault label assumption is proved before the play, not during it.** The
   preflight in Decision 9 runs ahead of `ansible-playbook` in both rows, so
   production's unlabelled `1.1` `ghcr_pull_token` block is established to
   decrypt under `--vault-id prod@…` before any role acts on the host. A failure
   there is a wrong secret, not a wrong host.
