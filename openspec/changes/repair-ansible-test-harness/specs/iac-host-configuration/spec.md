## MODIFIED Requirements

### Requirement: Host Authenticates to GHCR for Application Image Pulls
Where a GHCR credential is supplied, Ansible SHALL configure root's Docker credential store on the host with that read-only (`read:packages`-scoped) token, so that `docker compose pull` invocations run by `/usr/local/bin/app-deploy` succeed against a private GHCR package. This credential SHALL be shared across every application on the host rather than provisioned per application, since it grants no capability beyond reading package contents.

Where no GHCR credential is supplied, Ansible SHALL skip the registry authentication step and SHALL NOT fail the run. A host that pulls no private image needs no such credential, and host configuration SHALL NOT be made contingent on one being present.

This tolerance applies only to a credential being **absent**. It SHALL NOT be extended to a credential that is present and rejected by the registry: an authentication failure against a supplied credential SHALL remain a failure of the run, not a skipped step. The consequence of skipping SHALL be documented — an absent credential moves the point of failure from configuration time to the next private-image pull during a deploy.

#### Scenario: A private GHCR package can be pulled during deploy
- **WHEN** `docker compose pull` runs as part of an application's deploy, referencing a private image hosted on GHCR
- **THEN** the pull SHALL succeed using the host's configured GHCR credential, without any application-specific pull credential being provisioned

#### Scenario: Host configuration completes when no GHCR credential is supplied
- **WHEN** the host-baseline playbook runs with no GHCR token supplied
- **THEN** the registry authentication step SHALL be skipped, the run SHALL complete successfully, and every other host configuration step SHALL be applied as it would be with a credential present

#### Scenario: A supplied credential that the registry rejects still fails the run
- **WHEN** a GHCR token is supplied and the registry refuses it
- **THEN** the run SHALL fail rather than continuing as though no credential had been supplied

#### Scenario: GHCR token is never committed
- **WHEN** the GHCR token is generated or rotated
- **THEN** it SHALL be stored outside version control (Ansible Vault) and SHALL NOT appear in plaintext anywhere in the repository
