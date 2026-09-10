## Why

`configure-the-staging-host` made stage 6 of `docs/bootstrap-a-new-host.md` a
stage run once per environment, and updated Appendix A to match. It did not
touch stages 0 and 5, which are where the credentials that stage 6 consumes are
**created**. Those stages still describe a one-host world, and two of them now
contradict stage 6 outright:

- **§0.3 says generate one platform deploy key**, `-C "deploy@platform"`.
  §6.1's table says "**Each environment gets its own keypair** — one leaked
  private half must not deploy to both." A reader who follows §0.3 arrives at
  §6.1 with one key and no instruction for the second.
- **§0.3 says the operator inspection key is "Configured on the production host
  only, in stage 6".** It is configured on both: staging's `group_vars` carries
  `ops_user_accounts`, and the account exists on that host today.

Two more assume one host without contradicting anything, and one is a planning
figure a reader will act on:

- **§5.3 offers "Auth key for the server"**, singular, and its "Secrets created
  in this stage" table lists "The server auth key" as one item. Each host
  consumes its own at join, and the "Disable key expiry" instruction is
  likewise per machine.
- **§5.2's ACL guidance** is written over "the server" throughout.
- **The time estimate at the top** says the second environment "adds perhaps an
  hour of console work in stages 1 to 3 and nothing after that, since stages 5
  to 9 configure one host." Stage 6 now configures both, so the estimate is
  wrong about the stage that takes the longest.

**Why this matters now rather than eventually.** The next reader of this
document is bootstrapping a company's infrastructure from scratch, and wants two
servers — production and staging — from the start. That is the path the document
should make hardest to get wrong, and today it is the path that walks a reader
into §6.1 missing a keypair.

## What Changes

- **§0.3's key table gains the second platform deploy key** and stops saying the
  inspection key is production-only. Its existing paragraph on what may be
  shared across environments already draws the right distinction — one purpose
  may span both, one *purpose* per key — and the platform deploy key is the case
  where the purposes differ per environment. The table is where that has to be
  visible, because the table is what a reader executes.
- **§5.3 becomes per host**: one auth key each, generated at the same time or as
  each host is converged, and the key-expiry step repeated per machine. Its
  secrets table says two.
- **§5.2's ACL guidance** names both hosts.
- **The time estimate is corrected** — the second environment adds console work
  in stages 1 to 3 *and* a second converge in stage 6.
- **A new §0.4, "What exists once and what exists twice."** This is the
  substantial addition, and it is the artifact this session most obviously
  lacked: a single table saying, for every credential and account in the
  procedure, how many of it there are and why. The rule underneath it is
  consistent and worth stating rather than leaving to be induced from eleven
  scattered mentions — **a read-only credential is shared, because a copy grants
  nothing extra; a credential that grants access is per environment.** The
  operator root key is the deliberate exception, and §0.3 already argues it.

### Not in scope

Nothing about mechanisms, and nothing about stages 7 to 9, which really are
production's alone until the platform stack reaches staging
(`docs/change-queue.md` entry 52). The document should keep saying so.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None; `.openspec.yaml` carries `skip_specs: true`. Every count this change
writes down is already true of the repository as it stands — two Hetzner
projects, two HCP workspaces, two `group_vars` files, two vault ids — and no
mechanism moves. The document is the only thing that changes.

## Impact

**Documentation.** `docs/bootstrap-a-new-host.md` — the end-state summary and
time estimate at the top, §0.3, a new §0.4, §5.2 and §5.3.

**Records.** None.

**Not touched.** Every executable file in the repository.

**Verification.** The static suite and the pre-commit hooks, neither of which
reads prose for truth. What carries the counts is that each is checkable against
a committed file in under a minute, and the change's tasks name the file for
each one. The confirmation gate is answerable in full: the reader who is about
to bootstrap a company's infrastructure can follow §0.3 and §0.4 and say whether
the set of keys they end up holding is the set stage 6 then asks for.
