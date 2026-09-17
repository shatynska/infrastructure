## ADDED Requirements

### Requirement: Restricted Deploy Account for Platform Stack Access
Ansible SHALL provision a dedicated, non-interactive `deploy` system account and an associated SSH keypair, scoped to operating Docker Compose within the `platform/` directory on the host, distinct from any operator's personal login account.

This account exists so that a platform-stack deployment mechanism (e.g. a GitHub Actions workflow, specified separately) can reach the host without using a human operator's credentials. Provisioning the account is host configuration and therefore Ansible's responsibility; what the account is used to deploy (the `platform/` Compose stack) remains outside Ansible's scope per the Configuration Scope Stops at the Container Runtime requirement.

This account's restriction operates at the invocation layer, not the content layer: it constrains *how* the account can escalate privilege, not *what* the privileged action does once triggered. Because the account necessarily owns the directory holding the Compose file that action applies — that write access is how a deployment mechanism gets new content onto the host at all — a holder of this account's key can influence what the privileged action does by changing that file's content, up to and including obtaining root. This is a deliberately accepted trust boundary, not a gap this requirement claims to close — see the scenario below for what actually contains it.

#### Scenario: Deploy account's privileged access is a single fixed action, not arbitrary command injection
- **WHEN** the `deploy` account's SSH key is used to connect to the host
- **THEN** the only privileged action available to that session SHALL be triggering one fixed, argument-free script — the session SHALL NOT be able to pass arguments to that script, invoke `docker` or `docker compose` directly with elevated privilege, or trigger any other privileged command

#### Scenario: Deploy account can escalate via the content it is entitled to write
- **WHEN** the `deploy` account writes a new Compose file to the directory the fixed script operates on, then triggers that script
- **THEN** the script SHALL apply that file's content with root privilege exactly as written, with no content validation performed by this account's restriction mechanism — containment of what content reaches this directory is the responsibility of whatever grants access to place it there (e.g. the human-approval gate on the deployment mechanism's production credentials), not of this requirement

#### Scenario: Deploy account is provisioned independently of any operator
- **WHEN** the host configuration playbook runs
- **THEN** the `deploy` account and its authorized public key SHALL exist on the host without requiring any operator's personal SSH key or credentials

#### Scenario: Deploy private key is never committed
- **WHEN** the deploy keypair is generated or rotated
- **THEN** the private key SHALL be stored outside version control (e.g. Ansible Vault or a GitHub Actions secret) and SHALL NOT appear in plaintext anywhere in the repository
