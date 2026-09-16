# `.env` rendering probe

Measures what Compose's dotenv parser yields for a value written into a `.env` file, by reading the environment a container process actually received.

It exists because `.github/workflows/platform-deploy.yml` renders eight values into `platform/.env` from a stack's GitHub Environment secrets, and that file has a parser: it expands `$`, honours a quote that opens a value, begins an inline comment at a space-preceded `#`, truncates at a line break, and strips edge whitespace. A value written unaltered is not delivered unaltered, and the failure is silent. The escaping the render step applies was chosen by running this, and the change `render-the-env-file-so-a-secret-survives-it` carries the results as its `design.md`.

## What this is not

**Not a test, and in none of `AGENTS.md`'s three test rows.** No pipeline runs it and nothing fails if it stops working. It spawns a container, which `.github/tests` asserts over itself that it may not; and its subject is a workflow's output, where Molecule's is an Ansible role's behaviour on a host. That gap is why the escaping rule's behavioural evidence is a dated measurement in a change record rather than a check — `design.md` Decision 6 states the residual and `docs/backlog.md` carries the entry for the deploy-time round trip that would close it, which starts from here.

It is committed so that the evidence can be re-taken rather than trusted. A measurement nobody else can reproduce is evidence about its author.

## Running it

Needs Docker and a Compose that can reach the pinned image once.

    ./rounds all        # every round design.md records
    ./rounds 6          # one round

    ./probe raw 'ab$c#d' | base64 -d                    # one value, current rendering
    ./probe escaped 'ab$c#d' | base64 -d                # one value, the rule in force
    ./probe --path env-file raw "secret #1" | base64 -d # the application-repository path

`probe` prints base64 and never the value directly, so that whitespace and line breaks survive being read back. Decode it yourself, as above.

**If `docker compose` fails with `error getting credentials`**, a `credsStore` entry in `~/.docker/config.json` is shelling out to a helper that does not work here. Point `DOCKER_CONFIG` at a directory holding an empty `{}` for the run — the same workaround `README.md`'s Molecule section describes, for the same cause.

## Two paths, and why both are here

`interpolation.compose.yaml` is how the platform stack consumes `.env`: parsed, then interpolated as `${VAR}` into the Compose file. `env-file.compose.yaml` is how `docs/onboard-an-application.md` §4.4 tells application repositories to consume theirs: `env_file:` on the service, no interpolation. They are different entry points into the parser and were measured separately rather than assumed to agree — round 4 is that measurement. They do agree on the escaping rule, and they differ on at least one thing: a value that is exactly `"` or exactly `'` resolves empty on the `env_file:` path and is yielded intact on the interpolation path.

## Versions

The rule is a fact about a version of a parser, not about the format. The recorded rounds were taken against **Docker Compose v5.4.0** and **Docker Engine 29.7.2** on 2026-09-16; the production host was reading with **v5.5.0** the same day. Re-run `./rounds all` after a Compose upgrade — nothing else in this repository will notice if the rule changes.

The image is pinned by digest, and `.github/dependabot.yml` names this directory so the pin is refreshed weekly like every other image in the tree. That entry exists because *Automated Dependency Updates* covers every Compose file declaring a service image rather than every file that is deployed, and the CI suite reports one in an unnamed directory as uncovered — a probe nothing runs is not exempt. What does **not** watch it is `.github/tests`' image-pin assertions, which anchor on `platform/docker-compose.yml` by exact path.
