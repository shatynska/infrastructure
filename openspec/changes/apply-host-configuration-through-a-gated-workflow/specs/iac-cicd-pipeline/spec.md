## ADDED Requirements

### Requirement: Host Configuration Is Applied by a Gated Workflow
Host configuration SHALL reach a host through a workflow triggered by a merge to the default branch. A converge changes the host firewall, the accounts that may log in and the container runtime, so the path by which it reaches a host SHALL be gated in the same way the Terraform apply and the platform deploy are.

**One converge is exempt, and only one: a host's first.** Before that run the host is on no private network the workflow can reach it over and holds no credential the workflow can authenticate with, so the first converge is necessarily an operator's, from a workstation, over the host's public address. Every converge after it SHALL reach the host through the workflow. The exemption is bounded by the host's own bootstrap and SHALL NOT be read as permitting a workstation converge of a host already configured.

The workflow SHALL be structured as two jobs per environment in a single run. A job that holds **no** credential capable of reaching a host SHALL publish, for a human to read, what the merge changes under the host-configuration directory. A second job SHALL declare that environment's own GitHub Environment, taken from that environment's committed pipeline declaration, and SHALL be the only job holding the credentials a converge needs.

This layer has no saved-plan artifact and SHALL NOT pretend to one. A check-mode run is not one: it skips `command` tasks, it swallows failures in roles that ignore errors under check mode, and it must authenticate to the host — so it could only run in the job the gate exists to withhold the credential from. What the pre-approval job publishes is the committed diff, which for this layer is complete: every input a converge applies is committed, so there is no value computed elsewhere that the diff omits.

The workflow SHALL name no environment. Which environments exist, which GitHub Environment gates each, and which repository secret holds each one's read-only credential SHALL come from discovery over committed files, and adding an environment SHALL require no change to any file under `.github/workflows/`.

Discovery SHALL fail closed, with a message naming the environment and what was wrong, rather than omitting an environment from the run. An environment that can be provisioned but not converged, and one that can be converged but is gated by nothing, are both states this discovery SHALL refuse rather than pass over: an environment whose host is converged by no job is indistinguishable from an environment that has nothing to converge.

A converge job SHALL establish that the credentials it holds are usable — that the environment's secrets decrypt and that its inventory resolves — **before** any task acts on the host. Those inputs are decrypted at the moment they are first used, which is several roles into the play, so a run that starts with a wrong secret would otherwise leave a partially-converged host for a reason that had nothing to do with the host.

A converge job SHALL install the toolchain and the external content the play needs before running it, from this repository's own pinned manifests, and SHALL run from the directory whose configuration governs the run. A continuous-integration runner carries neither, and a run that reaches a missing plugin or a missing external role fails inside a mechanism, reading as a broken mechanism rather than as an unprovisioned machine. Running from the wrong directory is worse than failing: the configuration that makes a rejected credential fail the run is not loaded, so the run continues and reports a rejected credential as an environment whose server does not exist.

The version of Ansible a converge runs SHALL be the version the role-verification suite runs. A converge applying roles under a different Ansible than the one they were verified under is verified by nothing, and the agreement SHALL be asserted rather than intended, being a static read of two committed files.

A converge SHALL NOT be cancelled in favour of a later one. Runs against one environment SHALL be serialised, and an in-flight converge SHALL be allowed to finish: interrupting a play mid-run leaves the host partially converged, which is recoverable as an exception and not as a normal case.

One environment's converge failing SHALL NOT prevent another environment's from running and reporting.

#### Scenario: A merge to the host configuration converges without a workstation
- **WHEN** a merge to the default branch changes the host-configuration directory
- **THEN** each already-configured environment's host SHALL be converged by the workflow, and no step of that converge SHALL require a command run from an operator's machine

#### Scenario: A host's first converge is the operator's
- **WHEN** a host has not been converged before, so it is on no private network the workflow can reach it over and holds no credential the workflow can authenticate with
- **THEN** that one converge MAY be run from a workstation over the host's public address, and every converge of that host afterwards SHALL reach it through the workflow

#### Scenario: The pre-approval job holds no converge credential
- **WHEN** the job that publishes what the merge changes runs
- **THEN** it SHALL declare no GitHub Environment and SHALL consume no credential capable of reaching a host

#### Scenario: The converge job is gated on the environment's own GitHub Environment
- **WHEN** a converge job runs for an environment
- **THEN** it SHALL declare the GitHub Environment named by that environment's own pipeline declaration, so that its protection rules and its secrets are the ones that apply

#### Scenario: An environment that cannot be converged fails the workflow
- **WHEN** discovery finds an environment declaring a pipeline configuration but carrying no host-configuration inventory source, or an inventory source whose environment declares no pipeline configuration
- **THEN** the workflow SHALL fail with a message naming that environment and which side is missing, rather than converging the environments it could resolve

#### Scenario: Discovery finding no environment fails rather than reporting success
- **WHEN** discovery over the host-configuration inventory sources yields an empty set
- **THEN** the workflow SHALL fail with a message identifying discovery as the cause, and SHALL NOT allow a dependent job to be skipped and reported as successful

#### Scenario: A run is requested for an environment that does not exist
- **WHEN** a converge is requested by hand naming an environment discovery did not find
- **THEN** the run SHALL fail naming the environments that were found, rather than converging none and reporting success

#### Scenario: A wrong secret stops the run before the host is touched
- **WHEN** a converge job holds a credential that does not decrypt that environment's committed secrets, or a credential its inventory source rejects
- **THEN** the run SHALL fail before the first role acts on the host, rather than partway through the play

#### Scenario: The converge job supplies what the run needs
- **WHEN** a converge job runs on a continuous-integration runner, which carries no external content of its own
- **THEN** it SHALL have installed the toolchain and the external content the play needs from this repository's pinned manifests, and SHALL run from the directory whose configuration governs the run

#### Scenario: The converge runs the Ansible the roles were verified under
- **WHEN** the version the converge job installs is compared with the version the role-verification suite installs
- **THEN** the two SHALL be the same, and a difference SHALL fail the required status check

#### Scenario: One environment's failure does not silence another's
- **WHEN** a converge fails for one environment in a run covering several
- **THEN** every other environment's converge SHALL still run and report its own outcome

## MODIFIED Requirements

### Requirement: Each Environment Declares Its Own Pipeline Configuration
Every directory under `terraform/environments/` SHALL carry a committed, machine-readable file declaring the pipeline configuration for that environment. Two fields are **required**: the name of the GitHub Environment its apply job attaches to, and the name of the repository secret holding its read-only Hetzner token. A third is **optional**: whether the Destroy Policy Gate applies to it, which defaults to applying when absent (see the Destroy Policy Gate requirement, whose scenario "An environment declaring nothing is gated" is the case this default serves).

The optional field SHALL name the **gate**, not its inverse — the value states whether the gate applies, rather than whether the environment is disposable. A field whose polarity has to be inferred from its name is one a reader can invert without noticing, and inverting this one silently removes the strongest guard on an apply.

Adding an environment SHALL therefore require **no change to any file under `.github/workflows/`**. Workflows SHALL NOT enumerate environments, name them in a condition, or map an environment to its secrets or its Environment name in workflow text. A pipeline that must be edited to add an environment is the defect this requirement exists to prevent, and it is the state the README already described as absent.

That claim is about workflow files and nothing wider. An environment still needs its own state workspace, its own GitHub Environment and secrets, an inventory source and a `group_vars` file of its own for the host-configuration workflow to converge it, and an entry in the Dependabot configuration for the lockfile `terraform init` creates in its directory — which the Automated Dependency Updates requirement (iac-safety-hardening) already obliges, and which this requirement does not relax.

Each environment's declared read-only secret name SHALL be distinct from every other environment's, and so SHALL its declared GitHub Environment name. Two environments naming the same read-only secret share one token; two naming the same GitHub Environment share its **write** token and its protection rules, so an environment intended to be ungated would hold the reviewed environment's write credential — contradicting the Write Credentials Confined to the Gated Pipeline requirement (iac-safety-hardening), which places each environment's Read & Write token in that environment's own GitHub Environment. Both are the defect a per-environment declaration exists to prevent, reached through committed data rather than through workflow text and therefore invisible to any check that reads only the workflows.

**No environment's declared read-only secret name SHALL be a name its own GitHub Environment also defines, and `HCLOUD_TOKEN` is such a name for every environment.** Credential Scoping by Privilege requires each environment's GitHub Environment to define `HCLOUD_TOKEN` as that environment's Read & Write token, and GitHub resolves an Environment-scoped secret ahead of a repository-scoped one of the same name. A declaration naming `HCLOUD_TOKEN` as its read-only secret is therefore correct only for a job that declares no `environment:`; read from a job that declares one, the same name yields the **write** token, silently and with no error. The declared name is read by gated jobs as well as ungated ones, so the name SHALL be one no Environment shadows.

Discovery SHALL fail closed. An environment directory whose declaration is absent, unparseable, or missing either **required** field SHALL fail the workflow with a message naming the directory and the missing field, and SHALL NOT be silently skipped. An absent optional field is not a missing field: it takes its default and discovery proceeds. A skipped environment is one that is planned by nothing, applied by nothing and drift-checked by nothing, which is indistinguishable from the environment not existing and is exactly the condition this capability is meant to make impossible.

#### Scenario: A new environment needs no workflow edit
- **WHEN** a directory is added under `terraform/environments/` carrying a valid pipeline declaration
- **THEN** the validation, plan, apply, drift and host-converge workflows SHALL each cover it on their next run, with no change to any file under `.github/workflows/`

#### Scenario: Two environments declaring the same read-only secret are refused
- **WHEN** two environment declarations name the same repository secret as their read-only token
- **THEN** the pipeline SHALL fail, naming both environments, rather than running two environments' plans under one credential

#### Scenario: Two environments declaring the same GitHub Environment are refused
- **WHEN** two environment declarations name the same GitHub Environment
- **THEN** the pipeline SHALL fail, naming both environments, rather than applying two environments under one write token and one set of protection rules

#### Scenario: A declaration naming the write token's own name is refused
- **WHEN** an environment declaration names as its read-only secret a name that every GitHub Environment defines for its Read & Write token
- **THEN** the required status check SHALL fail, naming that environment, rather than leaving a gated job to resolve a write credential from a field that says read-only

#### Scenario: An environment missing its declaration fails the pipeline
- **WHEN** a directory under `terraform/environments/` has no pipeline declaration, or one lacking either required field
- **THEN** discovery SHALL fail the workflow with a message naming that directory and the missing field, rather than omitting the environment from the matrix

#### Scenario: Discovery finding no environment fails rather than reporting success
- **WHEN** discovery over `terraform/environments/` yields an empty set
- **THEN** the workflow SHALL fail with a message identifying discovery as the cause, and SHALL NOT allow a dependent job to be skipped and reported as successful
