## ADDED Requirements

### Requirement: Superseded Application Images Are Reclaimed at Deploy Time
`/usr/local/bin/app-deploy` SHALL, after an application's containers have been brought up and reported healthy, remove the local images in that application's own image namespace that the application's current Compose file does not reference.

An application's image namespace is the set of local image references of the form `ghcr.io/<owner>/<app_name>:<tag>`, for the application name `app-deploy` was invoked with and **any** owner segment. Reclamation SHALL NOT consider an image reference outside that namespace, so an image shared with another application on the host — a base image such as `postgres:16` or `traefik:v3.7.10` — is never a candidate for removal by any application's deploy. The namespace is exactly two path segments after the registry, the last of them equal to the application name, so an application whose images live at a deeper path (`ghcr.io/<owner>/<app_name>/<component>`) or under a differing name has an empty namespace and reclaims nothing at all — silently, and indistinguishably from an application that had nothing to reclaim. That coupling SHALL be recorded in the deploy role's own onboarding documentation, so it is discoverable where an application is onboarded rather than only in the body of the script.

A local image in that namespace carrying no tag SHALL NOT be reclaimed. Such an image is one referenced by digest rather than by tag, so it can never appear in a tag-shaped reference set, and treating its absence from that set as evidence that it is unreferenced would remove an image the application may currently be pinned to.

Reclamation SHALL determine the set of referenced images before removing anything. Where that set cannot be determined, or is determined to be empty, reclamation SHALL remove nothing on that run. An unavailable reference set is indistinguishable from one naming no images, and both would otherwise make every image in the namespace a candidate — including those of services that are defined but not currently running, which is the case taking the reference set from the Compose file rather than from running containers exists to protect.

Removal SHALL NOT be forced. Reclamation SHALL rely on the container runtime refusing to remove an image that a container — running or stopped — still holds, so that the runtime's own refusal stands between a defective reference set and an image still in use. A removal that is refused SHALL be treated as a normal outcome, not as an error to be overridden.

That refusal guards the image, not the reference: a runtime refuses where removal would drop an image's **last** reference, and removes a redundant tag from an image carrying more than one. Reclamation SHALL therefore be understood to guarantee that an in-use image survives, and SHALL NOT be relied on to preserve any particular tag of it.

Reclamation SHALL run only after the deploy has succeeded, so that the images the new containers hold are held by running containers while removal is attempted.

Reclamation SHALL NOT change the outcome of a deploy that has already succeeded: a failure to enumerate or remove any image SHALL leave the deploy reported as successful, and SHALL NOT fail the invoking SSH session or the workflow that opened it.

Reclamation SHALL be bounded in duration as a whole — enumerating the local images and the reference set included, not only the removals — so that a container runtime which stops responding cannot hold the deploy session, or the workflow that opened it, open indefinitely. Enumeration is a call to the same runtime that the removals are, and a bound that covers only the removals leaves the wedged-runtime case reachable through the step that precedes them. Reaching that bound is a reclamation failure like any other and SHALL leave the deploy reported as successful. Exit status alone does not make a step non-interfering: a step that never returns fails the deploy without ever exiting non-zero.

Reclamation SHALL report on every run, and SHALL do so on every exit path. Since every failure is otherwise swallowed, a reclamation that matches nothing at all is indistinguishable from one working correctly, and the only remaining signal would be the disk filling — the outcome this requirement exists to prevent.

What is reported differs by how the run ended, because not every path can know the same things. A run that **completed** SHALL report how many images it considered and how many it removed. A run **abandoned early** — because the reference set was empty or undeterminable, because the local images could not be enumerated, or because it reached its duration bound — SHALL instead report which of those ended it, and SHALL be distinguishable from a completed run that found nothing to reclaim.

A failure to enumerate SHALL NOT be reported as a completed run of zero. Zero considered and zero removed is the truthful report of an application whose namespace is legitimately empty, so a broken enumeration reported that way is indistinguishable from a healthy one — which is the state this requirement exists to prevent, arrived at by the report itself.

The duration-bound report SHALL be emitted from outside the bounded region: a report printed inside that region cannot survive it being killed, which would leave the one run most worth hearing about as the only silent one. It follows that this path reports a reason and not a count, since no count survives the kill either.

#### Scenario: A deploy removes the image its predecessor left behind
- **WHEN** an application is deployed at one image tag, and then deployed again at a different tag of the same image repository
- **THEN** after the second deploy the first tag SHALL no longer be present on the host, and the second SHALL be

#### Scenario: The image the running containers use is never removed
- **WHEN** a deploy completes and reclamation runs
- **THEN** every image referenced by that application's current Compose file SHALL still be present on the host, and the application's containers SHALL still be running

#### Scenario: An image held by a stopped container is not removed
- **WHEN** reclamation targets an image in the application's namespace that no Compose service references but that a stopped container still holds
- **THEN** the removal SHALL be refused by the container runtime and the image SHALL still be present, rather than being forced

#### Scenario: An image shared with another application is never a candidate
- **WHEN** an application whose Compose file references a base image outside its own `ghcr.io/<owner>/<app_name>` namespace is deployed, and another tag of that same base image repository is present on the host
- **THEN** that other tag SHALL still be present after the deploy, whether or not any container is currently using it

#### Scenario: Images published under a previous owner are reclaimed
- **WHEN** an application's image repository has moved to a different owner, so that images under the previous `ghcr.io/<old owner>/<app_name>` remain on the host while the Compose file references `ghcr.io/<new owner>/<app_name>`
- **THEN** the images under the previous owner SHALL be reclaimed, since the namespace is matched on the application name with any owner rather than on the owner in force at the time

#### Scenario: An unavailable or empty reference set reclaims nothing
- **WHEN** the set of images the application's Compose file references cannot be determined, or is determined to contain no images
- **THEN** reclamation SHALL remove no image at all, rather than treating every image in the namespace as unreferenced

#### Scenario: An untagged image in the namespace is left alone
- **WHEN** the namespace contains a local image carrying no tag, because it was referenced by digest
- **THEN** reclamation SHALL NOT remove it

#### Scenario: A completed run reports what it did
- **WHEN** reclamation runs to completion, whether it removed images or found nothing to remove
- **THEN** it SHALL report how many images it considered and how many it removed

#### Scenario: A run that ends early says why
- **WHEN** reclamation is abandoned because the reference set was empty or could not be determined, because the local images could not be enumerated, or because it reached its duration bound
- **THEN** it SHALL report which of those ended it, distinguishably from a completed run that found nothing to reclaim

#### Scenario: A non-responding runtime does not hold the deploy open
- **WHEN** the container runtime stops responding while reclamation is enumerating the local images or the reference set, or while it is removing images
- **THEN** reclamation SHALL be abandoned at its duration bound and `app-deploy` SHALL exit successfully, rather than waiting on the runtime for as long as it takes

#### Scenario: A failed reclamation does not fail a successful deploy
- **WHEN** reclamation cannot remove an image after the application's containers are up and healthy
- **THEN** `app-deploy` SHALL still exit successfully, and the deploy SHALL be reported as having succeeded
