## ADDED Requirements

### Requirement: Unprivileged Operator Accounts Support Interactive Host Inspection
Unprivileged, interactive operator accounts on the prod host SHALL be enumerated in version control as a list of named entries, each carrying exactly one SSH public key. For each entry in that list, Ansible SHALL provision: a Unix account with a home directory and an interactive shell, no password-based login, membership of the `docker` group, and an `authorized_keys` entry carrying that entry's public key with neither a forced command nor the `restrict` option, so that the key can open an interactive session.

Each such account SHALL have no `sudoers` entry of any kind. Ansible SHALL NOT grant it passwordless or password-protected `sudo`, narrow or otherwise.

These accounts SHALL be distinct from the `deploy` account and SHALL NOT be granted ownership of, or group access to, any `/opt/<app_name>` directory or its contents. The `deploy` account's forced-command model SHALL remain unchanged: no key on `deploy` SHALL be given an interactive session in order to satisfy this requirement.

The capability granted SHALL be documented as `docker` group membership being root-equivalent by escalation, and the account SHALL NOT be described or relied upon as a confidentiality or integrity boundary against its own key holder. What it bounds is host administration through the ordinary path, attribution of sessions, and revocability — not what a determined holder of its key can ultimately reach.

Removing an entry's account SHALL succeed in a single playbook run even when that entry's holder is logged in at the time: Ansible SHALL terminate the account's sessions and processes before removing it, rather than failing on an in-use account or removing it while leaving an established session alive. Revocation SHALL be documented as ending access rather than as being retroactive — it SHALL NOT be described as stopping containers the account started through the Docker API, which run as root under the container runtime and outlive the account.

An operator's public key SHALL be committed in plaintext, and the corresponding private key SHALL NOT appear anywhere in this repository.

#### Scenario: An operator key opens an interactive session
- **WHEN** an enumerated operator's SSH key connects to its own account
- **THEN** the session SHALL be granted an interactive shell with a pty, unlike a `deploy` key, whose session is bound to a single forced command

#### Scenario: Container state and logs are inspectable without privilege escalation
- **WHEN** an operator session inspects running containers, reads their logs, or executes a command inside one
- **THEN** those operations SHALL succeed by virtue of `docker` group membership alone, without `sudo` being invoked

#### Scenario: The account has no sudo capability
- **WHEN** an operator session attempts any `sudo` invocation
- **THEN** it SHALL be refused, and no `sudoers.d` file naming that account SHALL exist on the host

#### Scenario: An operator cannot read another application's deployed secrets from the filesystem
- **WHEN** an operator session attempts to read `/opt/<app_name>/.env` or overwrite `/opt/<app_name>/docker-compose.yml`
- **THEN** the attempt SHALL be refused by filesystem permissions, the operator account being neither the owner of those paths nor a member of a group granted access to them

#### Scenario: Revoking an operator is a converge, not a manual cleanup
- **WHEN** an operator's entry is marked absent in the enumerated list and the playbook is re-run
- **THEN** that account and its authorized key SHALL be removed from the host by that run, without any hand-run command on the host and without affecting any other operator entry or the `deploy` account

#### Scenario: Revoking an operator who is currently logged in still completes
- **WHEN** an operator's entry is marked absent while that account has a live session or a running process on the host
- **THEN** the run SHALL terminate that session and its processes and then remove the account, completing rather than failing on an in-use account, and SHALL NOT leave an established session with continued access after reporting the account removed

#### Scenario: Rotating an operator's key removes the previous one
- **WHEN** an operator entry's public key is replaced with a different one and the playbook is re-run
- **THEN** the account's `authorized_keys` SHALL contain only the new key, the superseded key having been removed rather than left alongside it

#### Scenario: Operator private keys are never committed
- **WHEN** an operator keypair is generated or rotated
- **THEN** only its public half SHALL be committed to this repository, and the private half SHALL remain on the operator's own machine

#### Scenario: The deploy account's restrictions are unaffected
- **WHEN** this requirement is satisfied
- **THEN** every key on the `deploy` account SHALL still carry `restrict` and its per-application forced command, and no new interactive path onto the `deploy` account SHALL exist
