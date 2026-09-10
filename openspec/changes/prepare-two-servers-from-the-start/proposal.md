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
  in this stage" table lists "The server auth key" as one item. It never says
  whether one key serves both hosts — it does, if generated reusable — nor that
  "Disable key expiry" is a per-node setting that has to be repeated.
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
  shared across environments already draws the right distinction — one *purpose*
  per key — and the platform deploy key is the case where the purposes differ per
  environment. The table is where that has to be visible, because the table is
  what a reader executes.

  **And the same table's "Private half lives in" cell has to become per
  environment**, which is the one correction here that prevents a loss rather
  than a confusion. It says "GitHub secret only; delete the local file after
  storing it" — true of production's key, false of staging's, whose private half
  belongs in the password manager and in no GitHub secret until entry 52 gives
  staging a deploy workflow to read it.
- **§5.3 says what one key does and does not cover.** A *reusable* key serves
  both joins — the role consumes it once per run and skips on an already-joined
  host — so two are wanted only if the key is single-use or if you want to revoke
  one host's join without touching the other, which is what this repository in
  fact did. The key-expiry step is per node and has to be repeated. An earlier
  draft of this change wrote "one consumed per host at join" in one place and
  "a reusable key can serve both" in another; saying it once, correctly, is the
  point.
- **§5.2's ACL guidance** names both hosts.
- **The time estimate is corrected** — the second environment adds console work
  in stages 1 to 3 *and* a second converge in stage 6.
- **A new §0.4, "What exists once and what exists twice."** This is the
  substantial addition, and it is the artifact this session most obviously
  lacked: a single table saying, for every credential the procedure creates for
  the infrastructure itself, how many of it there are and what proves the count.
  It declares that boundary — **stages 0 to 6** — because a table read as
  complete and not being so is worse than none, and it names the two things it
  deliberately leaves out: stage 7's platform-stack secrets, which are
  production's alone until entry 52, and §0.3's own application-deploy-key row,
  which belongs to stage 8.

  **The axis it sorts on is the one §0.3 already states**: a different holder and
  a different blast radius, plus the mechanical constraint that a Hetzner token
  reaches exactly one project. An earlier draft proposed a different rule — that
  read-only credentials are shared and access-granting ones are per environment —
  and it is recorded here because it is attractive and wrong: it mis-sorts four
  of the table's own rows. The inspection key grants root-equivalent access by
  docker-group membership and is shared; the ping key lets its holder suppress an
  alarm and is shared; the read-only Hetzner tokens are read-only and come in
  pairs; `TF_API_TOKEN` writes state for both environments and is one value.

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
time estimate at the top, §0.3, a new §0.4, §5.2, §5.3, the opening of stage 5,
two rows in §0.1 and one in §0.2, **§6.4's "Secrets created in this stage"
table** — which repeats §0.3's "delete the local file" instruction inside the
stage that now runs once per environment — and **Appendix A**, whose Tailscale
auth key and `PLATFORM_DEPLOY_SSH_KEY` rows are still singular. That appendix is the
document's own "complete secret inventory", so leaving it would have this change
create the drift it exists to remove, one appendix over.

**Records.** One entry in `docs/change-queue.md`:
`ansible/inventory/group_vars/staging.yml` still carries a banner saying the
file is incomplete and the host unconverged, above values that have since been
supplied on a host that has since converged. Out of scope to fix here, and an
implementer sent to that file for evidence meets it.

**Not touched.** Every executable file in the repository.

**Verification.** The static suite and the pre-commit hooks, neither of which
reads prose for truth. What carries the counts is that each is checkable — most
against a committed file, two against a recorded requirement — and the tasks
name what proves each row.

The confirmation gate is a **cold read by someone other than the author**:
holding none of these credentials, read §0.3 and §0.4, write down the set you
would end up holding, and compare it with what §6.1, §6.3 and §6.4 ask for. That
is performable the day this merges and needs no Hetzner project. The company
bootstrap is a stronger observation of the whole procedure and a weaker one of
this change, because a gap it finds anywhere in stages 1 to 6 would not be
attributable here.
