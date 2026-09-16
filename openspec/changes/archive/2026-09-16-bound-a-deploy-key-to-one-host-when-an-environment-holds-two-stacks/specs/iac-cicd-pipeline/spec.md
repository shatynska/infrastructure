## MODIFIED Requirements

### Requirement: Each Stack Declares Its Own Pipeline Configuration
Every directory under `terraform/stacks/` SHALL carry a committed, machine-readable file declaring the pipeline configuration for that stack. Three fields are **required**: the name of the GitHub Environment its apply job attaches to, the name of the repository secret holding its read-only Hetzner token, and the name of the Ansible group its host-configuration converge targets. Two are **optional**: whether the Destroy Policy Gate applies to it, which defaults to applying when absent (see the Destroy Policy Gate requirement, whose scenario "An environment declaring nothing is gated" is the case this default serves); and whether the shared platform stack is deployed to it, which defaults to **not** being deployed when absent.

**The declared Ansible group SHALL NOT be derived from the stack's name.** A stack is a *(tenant, environment)* pair and the group it converges is the environment alone, so the two are equal only where a repository has one tenant. Parsing one out of the other is a rule that holds on the names a repository happens to have and fails silently on the next one — as a group that does not exist, reported several steps after the run began. It is declared for the same reason the GitHub Environment's name is: the pipeline reads it rather than computing it.

**Unlike the other two required fields, the declared Ansible group carries no uniqueness obligation**, and the difference is not an oversight. Two stacks naming one GitHub Environment share its write token and its protection rules; two naming one read-only secret share one credential. Two stacks naming one Ansible group share a set of host variables, which is what an environment-wide baseline across tenants *is*. Distinctness SHALL NOT be required of it.

Each optional field SHALL name what happens when it is **true**, rather than its inverse — the value states whether the gate applies, or whether the platform stack is deployed, rather than whether the stack is disposable or excluded. A field whose polarity has to be inferred from its name is one a reader can invert without noticing, and inverting either of these silently removes a guard: the first, the strongest guard on an apply; the second, the guard against a stack receiving an application stack nobody decided to give it.

**Each optional field's default SHALL be the value that is safe when the field was forgotten**, and the two defaults are opposite values for that one reason. A stack whose declaration says nothing about the destroy-policy gate is gated, because the mistake to protect against is an ungated destructive apply. A stack whose declaration says nothing about the platform stack does not receive it, because a stack directory is committed before its GitHub Environment holds any platform secret, and the mistake to protect against is a deploy attempted under credentials that do not yet exist, to a host that may not yet authorise the key.

**A stack declaring that the platform stack is deployed to it SHALL also authorise that deploy on the host**, by enumerating the platform application among the deploy-key authorisations in the **host vars file of the host that stack provisions** — see *A Host-Scoped Variable Lives in the Host's Own Vars File* (`openspec/specs/iac-host-configuration/spec.md`). It SHALL NOT be the `group_vars` file of the declared Ansible group, and the difference is not cosmetic: a group is an environment, an environment may hold two stacks, and an authorisation written there would answer both stacks' opt-ins with one entry while authorising one deploy key on two hosts. The two are separate facts about separate layers and SHALL NOT be derived one from the other — a host may authorise the key before the pipeline is pointed at it, and that interval is a deliberate state rather than an error. The implication holds in one direction only, and a declaration opting in without the corresponding authorisation SHALL fail the required status check on the pull request, naming both files. **Each stack's opt-in SHALL be answered by its own host's authorisation**, so two stacks sharing an environment carry two obligations rather than one between them. Left to the deploy, the same disagreement surfaces as an authentication failure after the tailnet join and after any approval, with a cause that has to be inferred.

Adding a stack SHALL therefore require **no change to any file under `.github/workflows/`**. Workflows SHALL NOT enumerate stacks, name them in a condition, or map a stack to its secrets, its Environment name or its Ansible group in workflow text. A pipeline that must be edited to add a stack is the defect this requirement exists to prevent, and it is the state the README already described as absent.

That claim is about workflow files and nothing wider. A stack still needs its own state workspace, its own GitHub Environment and secrets, an inventory source of its own, the `group_vars` file of the environment it declares — which another stack may already have created — a host vars file of its own for the host-configuration workflow to converge it, and an entry in the Dependabot configuration for the lockfile `terraform init` creates in its directory — which the Automated Dependency Updates requirement (iac-safety-hardening) already obliges, and which this requirement does not relax.

Each stack's declared read-only secret name SHALL be distinct from every other stack's, and so SHALL its declared GitHub Environment name. Two stacks naming the same read-only secret share one token; two naming the same GitHub Environment share its **write** token and its protection rules, so a stack intended to be ungated would hold the reviewed stack's write credential — contradicting the Write Credentials Confined to the Gated Pipeline requirement (iac-safety-hardening), which places each stack's Read & Write token in that stack's own GitHub Environment. Both are the defect a per-stack declaration exists to prevent, reached through committed data rather than through workflow text and therefore invisible to any check that reads only the workflows.

**No stack's declared read-only secret name SHALL be a name its own GitHub Environment also defines, and `HCLOUD_TOKEN` is such a name for every stack.** Credential Scoping by Privilege requires each stack's GitHub Environment to define `HCLOUD_TOKEN` as that stack's Read & Write token, and GitHub resolves an Environment-scoped secret ahead of a repository-scoped one of the same name. A declaration naming `HCLOUD_TOKEN` as its read-only secret is therefore correct only for a job that declares no `environment:`; read from a job that declares one, the same name yields the **write** token, silently and with no error. The declared name is read by gated jobs as well as ungated ones, so the name SHALL be one no Environment shadows.

Discovery SHALL fail closed. A stack directory whose declaration is absent, unparseable, or missing a **required** field SHALL fail the workflow with a message naming the directory and the missing field, and SHALL NOT be silently skipped. A field is required of the discovery that reads it: a workflow that runs no converge SHALL NOT refuse a stack for the absence of a field only a converge consumes, since failing a Terraform-only pull request for a host-configuration reason names a cause the change does not have. An absent optional field is not a missing field: it takes its default and discovery proceeds. A skipped stack is one that is planned by nothing, applied by nothing and drift-checked by nothing, which is indistinguishable from the stack not existing and is exactly the condition this capability is meant to make impossible.

A stack excluded by an optional field it declares is not a skipped stack in that sense, and the difference SHALL be visible rather than inferred. It is excluded by its own committed declaration from one workflow's matrix, remains covered by every workflow that does not read that field, and SHALL be reported as excluded by the workflow that read it.

#### Scenario: A new stack needs no workflow edit
- **WHEN** a directory is added under `terraform/stacks/` carrying a valid pipeline declaration
- **THEN** the validation, plan, apply, drift and host-converge workflows SHALL each cover it on their next run, with no change to any file under `.github/workflows/`

#### Scenario: A converge reads its Ansible group from the declaration, not from the stack's name
- **WHEN** a stack whose name differs from the Ansible group its host belongs to is converged
- **THEN** the play's target group, the vault-id label and the `group_vars` file SHALL be taken from the declared field, and nothing SHALL parse them out of the stack's directory name

#### Scenario: Two stacks declaring the same read-only secret are refused
- **WHEN** two stack declarations name the same repository secret as their read-only token
- **THEN** the pipeline SHALL fail, naming both stacks, rather than running two stacks' plans under one credential

#### Scenario: Two stacks declaring the same GitHub Environment are refused
- **WHEN** two stack declarations name the same GitHub Environment
- **THEN** the pipeline SHALL fail, naming both stacks, rather than applying two stacks under one write token and one set of protection rules

#### Scenario: Two stacks declaring the same Ansible group are accepted
- **WHEN** two stack declarations name the same Ansible group, each with an inventory source reaching its own Hetzner project
- **THEN** discovery SHALL accept both, because a shared group is a shared set of host variables rather than a shared credential

#### Scenario: A declaration naming the write token's own name is refused
- **WHEN** a stack declaration names as its read-only secret a name that every GitHub Environment defines for its Read & Write token
- **THEN** the required status check SHALL fail, naming that stack, rather than leaving a gated job to resolve a write credential from a field that says read-only

#### Scenario: A stack missing its declaration fails the pipeline
- **WHEN** a directory under `terraform/stacks/` has no pipeline declaration, or one lacking a field the running workflow requires
- **THEN** discovery SHALL fail the workflow with a message naming that directory and the missing field, rather than omitting the stack from the matrix

#### Scenario: Discovery finding no stack fails rather than reporting success
- **WHEN** discovery over `terraform/stacks/` yields an empty set
- **THEN** the workflow SHALL fail with a message identifying discovery as the cause, and SHALL NOT allow a dependent job to be skipped and reported as successful

#### Scenario: A stack declaring nothing about the platform stack does not receive it
- **WHEN** a stack directory is added carrying a declaration that says nothing about whether the shared platform stack is deployed to it
- **THEN** no platform deploy SHALL be attempted for that stack, and every other workflow SHALL cover it as usual

#### Scenario: A stack opting in without authorising the deploy on its host is refused
- **WHEN** a stack's declaration states that the shared platform stack is deployed to it, and the host vars file of the host it provisions does not enumerate the platform application among that host's deploy-key authorisations
- **THEN** the required status check SHALL fail on the pull request, naming both files, rather than leaving the deploy to fail authenticating with a key the host does not authorise

#### Scenario: A host authorising the deploy key before the pipeline is pointed at it is accepted
- **WHEN** a host vars file enumerates the platform application among that host's deploy-key authorisations and that stack's declaration does not opt in to the platform deploy
- **THEN** discovery and the required status check SHALL both accept the tree, that interval being the deliberate state of a host prepared before its deploy path exists

#### Scenario: Two stacks in one environment each owe their own authorisation
- **WHEN** two stacks declare the same Ansible group and both opt in to the platform deploy, and only one of the two hosts enumerates the platform application among its deploy-key authorisations
- **THEN** the required status check SHALL fail for the stack whose host does not, naming that stack and the host vars file expected of it
- **AND** the authorisation present on the other host SHALL NOT be read as satisfying it
