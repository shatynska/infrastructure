## Why

Adding a service to a host is a once-per-application procedure, read out of order, years apart, by someone who is not bootstrapping anything — and the whole of it is stage 8 of `docs/bootstrap-a-new-host.md`, a once-per-server runbook read front to back. The procedure also stopped being about one host: `deploy-the-platform-stack-per-environment` made it a grid of applications across environments, and the next reader of it is the company clone this repository is a template for, standing up several services rather than one.

## What Changes

- **A new document, `docs/onboard-an-application.md`**, carrying the whole procedure for adding one application to one deploy target: the naming rule and the image-namespace coupling it exists for, the deploy key, the `deploy_apps` entry and the converge that must precede the application's first deploy, GHCR read access, the database decision and its recipe, the application repository's own side, DNS, and a check after each step.
- **Stage 8 is reduced to a pointer** and keeps nothing the new document does not also say. This is an extraction, not a copy: a second copy of a procedure touching deploy keys, sudoers rules and a database decision would drift, and both copies would read as authoritative.
- **The database recipe moves with its explanations, and gains the four answers it raises the first time it is used**: where the password comes from and who holds it afterwards, that it differs per application and per host even where the secret's name is reused, that it is never the instance superuser's `PLATFORM_POSTGRES_PASSWORD`, and what to do when it is lost or leaked.
- **Three things stage 8 does not say are written down**: what is reachable over the tailnet before a public hostname or a certificate exists and why a browser is not that path; that an application enumerated in `deploy_apps` but not yet deployed contributes nothing to the image prune's keep set and is not a fault; and the comment convention a key's public half carries, which is what the application's `group_vars` entry is read back against.
- **The deploy-key naming discrepancy `docs/bootstrap-a-new-host.md` §0.3 currently carries is resolved onto the environment** — the platform row spells its per-target segment as the stack and the application row as the environment, and one of the two is wrong — and `docs/naming-conventions.md`'s *The workstation* table, which §0.3 calls the full list, gains the two deploy keys it omits.
- **`.github/tests/test_the_shared_instance_has_its_first_database.py` follows the recipe to its new document**, keeping every assertion it makes of it.
- **One requirement changes**: *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`) names `docs/bootstrap-a-new-host.md` as where the manual recipe is, and the recipe is moving. The delta changes that path, and adds one normative paragraph and one scenario obliging that the document a requirement names for a manual recipe actually holds it, and that no second committed document holds a copy — which is what keeps the next move of this procedure from leaving a requirement pointing at the wrong file.
- **Every other pointer into stage 8 is redirected** — three inside `docs/bootstrap-a-new-host.md`, where Appendix B's rebuild path re-provisions each application's database by `§8.3`'s recipe and Appendix C names it; five in `docs/backlog.md`, across four entries, three of which this change does not delete; and `platform/README.md`, which names the bootstrap document as holding that recipe.
- **`docs/backlog.md`**: entry `record-how-an-application-is-onboarded` is deleted when this change archives, and **two** entries are added for findings this change surfaces rather than fixes — that `deploy_apps` lives in `group_vars/<environment>.yml`, so a second tenant in one environment would authorise one deploy key on two hosts; and that `.gitignore`'s private-key patterns match neither the application deploy key's current name nor the platform key's under the production spelling, which predates this change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `iac-platform-services`: *Single Shared PostgreSQL Instance, Per-Application Databases* — the sentence naming the document that holds the manual provisioning recipe, which is the part of that requirement this change falsifies, plus one added paragraph and one added scenario obliging that naming to stay true.

## Impact

- `docs/onboard-an-application.md` (new), `docs/bootstrap-a-new-host.md` (stage 8 reduced to a pointer; §0.3's key table and the prose around it; the references into stage 8 from Appendix B and Appendix C; the platform deploy key's per-stack literal and wording in §0.3, §0.4, §6.1, §6.4 and Appendix A), `docs/naming-conventions.md` (*The workstation*), `docs/backlog.md` (three entries' references into stage 8, plus two entries added and one deleted at archive), `platform/README.md`, `README.md` (the `docs/` enumeration), `.gitignore` (the private-key block's comment, not its patterns).
- `.github/tests/test_the_shared_instance_has_its_first_database.py`, whose subject moves with the recipe, and `.github/tests/test_the_bootstrap_documents_static_conventions.py`, whose key-target check must reach the document the key-generation command moves into.
- `openspec/specs/iac-platform-services/spec.md`, through this change's delta.
- **No mechanism, no host state and no converge.** Nothing under `ansible/`, `terraform/`, `platform/` or `.github/workflows/` changes, and no committed public key is re-keyed.
- **Ordering**: `provision-commerce-ops-database-in-the-shared-instance` carries a live delta on the same requirement and archives first; this change's delta is written against the text that change leaves behind.
