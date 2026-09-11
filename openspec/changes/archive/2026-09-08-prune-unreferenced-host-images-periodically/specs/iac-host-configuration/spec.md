## ADDED Requirements

### Requirement: Unreferenced Host Images Are Pruned on a Schedule
Ansible SHALL install, on the configured host, a scheduled unit that periodically removes every local container image that no enumerated application and no container on that host still references. The schedule SHALL be owned by the host's init system rather than by the removal script, SHALL survive a host being down at its scheduled time by running once afterwards rather than skipping that occurrence, and SHALL NOT be triggered by a deploy. Installing or updating the unit SHALL NOT itself remove an image, so that configuring the host is never also a mutation of what it stores.

This is complementary to, and SHALL NOT replace, the reclamation `/usr/local/bin/app-deploy` performs at deploy time. The two differ in what they may claim authority over, not only in how often they run.

**The set of images to keep SHALL be the union, over every application enumerated in version control, of the images that application's Compose file on the host references, unioned with the image held by every container on the host, running or stopped.** A single application's reference set is not authority over an image other applications also use, which is why deploy-time reclamation does not consider one, per its own requirement; the union over every enumerated application is such an authority, and it is what allows a shared base image superseded by a newer pin to be removed here and nowhere else.

**An application's references SHALL span every profile its Compose file declares, not only the profiles active at the moment the set is computed.** A Compose file's rendered image list omits any service gated behind an inactive profile, so a set taken from a single rendering is short by exactly the services that are defined and not running — the class this union exists to protect, and the one a prune driven by current container state already loses.

The enumeration of applications SHALL be the version-controlled list from which that host's deploy accounts, `sudoers` rules and forced commands are generated. It SHALL NOT be derived from directories or Compose files found on the host: an application's directory and its last Compose file outlive its removal from that list, so a filesystem-derived enumeration would let a retired application's stale file protect its images indefinitely — the outcome the schedule exists to reach. It follows that removing an application from that list SHALL make its images reclaimable, and that this consequence SHALL be recorded in the installing role's own documentation.

Where the enumeration names no application at all, the run SHALL remove nothing and SHALL report that condition. The keep set would otherwise reduce to the images containers currently hold, which is precisely the untargeted claim about a moment that this requirement's union exists to avoid making.

**Age SHALL NOT be a criterion.** An image is kept because something references it or it is removed. In particular, the container runtime's `until` image filter selects on an image's creation timestamp — which for a pulled image is set by whoever built it upstream, not by this host — so it does not distinguish an image this host has stopped using from one it uses constantly, and SHALL NOT be relied on as a retention window or presented as one.

**References SHALL be compared as the images they resolve to, not as the strings that name them.** Each reference in the keep set SHALL be resolved to a local image identity before comparison, and local images SHALL be matched against the keep set by that identity.

A reference that is well-formed but resolves to no local image SHALL contribute nothing and SHALL NOT be treated as an error, since it names an image this host has not pulled. A reference that is **not well-formed** SHALL instead be treated as an unresolvable reference set and abandon the run. Rendering a Compose file whose interpolation variables are unset yields a malformed reference and reports success, so an implementation that treats every unresolvable reference alike cannot distinguish an image the host lacks from a reference set silently missing its application's images. A reference naming an image by digest is well-formed: it is the form this requirement exists to honour, and rejecting it would abandon every run of a host whose applications pin their images.

It follows that an image referenced by digest rather than by tag SHALL be kept where an enumerated application references it, even though it carries no tag, and SHALL be removed where the union does not reach it. Its absence of a tag SHALL NOT by itself be treated as evidence that nothing references it: that property is what deploy-time reclamation had no way to see past, and an identity-shaped keep set SHALL decide it on evidence instead.

**Removal SHALL NOT be forced.** An image carrying tags SHALL be removed through each of its tags, so that the runtime deletes it when its last reference is dropped; an image carrying no tag SHALL be removed by its identity. A removal the runtime refuses SHALL be treated as a normal outcome and SHALL NOT be retried with force, so that the runtime's own refusal to remove an image a container holds stands between a defective keep set and an image still in use.

**A tag SHALL be confirmed to still name the image it was selected as, at the moment it is removed.** A tag is selected by the identity it resolved to during enumeration and removed by name afterwards, and a tag may be re-pointed at a different image in between — by a concurrent deploy, or by any pull of a moving tag. Removing it without re-checking drops a reference to whichever image the tag names by then, which for a freshly pulled image is a reference no container holds yet.

A prune SHALL NOT be performed through a runtime facility that selects images by absence of a tag, since that selects digest-referenced images on a property this requirement establishes is not evidence.

**The local images a run may consider SHALL be enumerated before the keep set is computed, and the keep set SHALL be determined before anything is removed.** An image that appears on the host after that enumeration is therefore never a candidate, while a reference that appears after it is still honoured — so the interval can only narrow what a run may remove, never widen it. The reverse order leaves an image pulled by a concurrent deploy inside the candidate set and outside the keep set, in the interval before any container holds it and so before the runtime's refusal can engage.

**A run that cannot determine the keep set completely SHALL remove nothing.** Where an enumerated application's Compose file is present on the host but its references cannot be resolved, the entire run SHALL be abandoned rather than that application's contribution merely omitted — an incomplete union offers live images for removal, so a partial keep set is a wrong keep set. Where an enumerated application has no Compose file on the host at all, that application SHALL contribute nothing and the run SHALL proceed, since an application that has never deployed has no image on the host to remove. Where the resulting union is empty, the run SHALL remove nothing.

**The run SHALL be bounded in duration as a whole** — resolving the keep set and enumerating local images included, not only the removals — so that a container runtime which stops responding cannot leave the unit running indefinitely. Enumeration is a call to the same runtime the removals are.

**The run SHALL report on every exit path, and a run that was abandoned SHALL fail.** A run that completed SHALL report how many images it considered and how many it removed. Both counts SHALL be deduplicated by image identity, so that an image carrying several tags counts once however many removals it took. The considered count SHALL be the number of distinct identities the run enumerated. The removed count SHALL be the number of **those** identities for which one of this run's own removal invocations reported the image deleted — anchored to the invocation, not to the host's state at the end of the run. An image a concurrent actor removed is therefore not counted as this run's work, and an image this run deleted is still counted where a concurrent deploy has since re-pulled it. A removal the runtime refused, a tag skipped because it no longer named the image it was selected as, and a tag dropped from an image that survives under another each leave it unchanged. A run abandoned early SHALL instead report which condition ended it — an unresolvable or malformed reference set, an enumeration the host does not yet carry, an enumeration naming no application, an empty keep set, or a failure to enumerate local images — and SHALL be distinguishable from a completed run that found nothing to remove. Where the enumeration is unavailable because the host has not yet been configured with one, the report SHALL say so distinguishably from an enumeration that is present and names no application: the two have different remedies, and a report that conflates them sends an operator to the inventory when the host merely needs a converge. Unlike deploy-time reclamation, which SHALL NOT change the outcome of a deploy that already succeeded, this unit has no caller to damage and SHALL therefore exit non-zero on an abandoned run, so that the host records a failed unit rather than a silent one.

A run ended by its duration bound is the one path that reports nothing itself, and SHALL instead be recorded by the init system that bounded it, as a logged expiry and a failed unit. A report emitted from within the bounded region cannot survive that region being killed, so this path SHALL NOT be specified as a line the run prints.

#### Scenario: An image superseded by a newer pin is removed
- **WHEN** the host carries two tags of the same base image repository and only the newer is referenced by any enumerated application's Compose file, and no container holds the older
- **THEN** the scheduled run SHALL remove the older tag and SHALL leave the newer

#### Scenario: An image one application references is kept when another does not
- **WHEN** one enumerated application's Compose file references an image that another enumerated application's does not
- **THEN** that image SHALL be kept, because the keep set is the union across every enumerated application rather than any one of them

#### Scenario: A defined service that is not running keeps its image
- **WHEN** an enumerated application's Compose file references an image for which no container currently exists on the host
- **THEN** that image SHALL still be present after the run

#### Scenario: A service behind an inactive profile keeps its image
- **WHEN** an enumerated application's Compose file defines a service behind a profile that is not active, so that rendering the file without that profile does not name its image, and no container of that service exists
- **THEN** that image SHALL still be present after the run, the reference set having spanned every profile the file declares

#### Scenario: An image a container holds is never removed
- **WHEN** the host holds a container, running or stopped, whose image no enumerated application's Compose file references
- **THEN** that image SHALL still be present after the run, and the removal SHALL NOT have been forced

#### Scenario: An image nothing references is removed
- **WHEN** the host carries a tagged image that no enumerated application's Compose file references and no container holds
- **THEN** the scheduled run SHALL remove it

#### Scenario: An untagged image nothing references is removed
- **WHEN** the host carries a local image with no tag that no enumerated application's Compose file resolves to and no container holds
- **THEN** the scheduled run SHALL remove it by its identity

#### Scenario: A digest-referenced image an application pins is kept
- **WHEN** an enumerated application's Compose file references an image by digest, so that the image is present on the host carrying no tag
- **THEN** that image SHALL still be present after the run, having been kept by resolving the digest reference rather than by carrying a tag

#### Scenario: An unreferenced image carrying more than one tag is removed through each of them
- **WHEN** the host carries an image bearing more than one tag, none of which any enumerated application's Compose file references, and no container holds it
- **THEN** the scheduled run SHALL remove it, having dropped each of its tags in turn rather than attempting to remove it by identity, which the runtime refuses for a multiply-referenced image unless forced

#### Scenario: A tag of an image a container holds is not dropped
- **WHEN** a container holds an image bearing more than one tag and no enumerated application's Compose file references any of them
- **THEN** every one of those tags SHALL still be present after the run, the image having been kept by the container's own entry in the keep set rather than only by the runtime's refusal, which guards the image and not its individual tags

#### Scenario: A tag re-pointed after enumeration is not removed
- **WHEN** a tag selected for removal is made to name a different image between the run enumerating it and the run removing it
- **THEN** that tag SHALL NOT be removed, and the image it now names SHALL still be present

#### Scenario: A retired application's images become reclaimable
- **WHEN** an application is removed from the version-controlled enumeration, the configuration management run that refreshes the host's copy of that enumeration has completed, its directory and last Compose file remain on the host, and no container of its remains
- **THEN** the scheduled run SHALL remove its images, rather than reading the stale Compose file on the host and keeping them

#### Scenario: An unresolvable Compose file abandons the whole run
- **WHEN** an enumerated application has a Compose file on the host whose image references cannot be resolved
- **THEN** the run SHALL remove no image at all, including images of every other enumerated application, and SHALL report that condition and fail

#### Scenario: A malformed reference abandons the whole run
- **WHEN** rendering an enumerated application's Compose file succeeds but yields a reference that is not a well-formed image reference, as an unset interpolation variable produces
- **THEN** the run SHALL remove no image at all, and SHALL report that condition and fail, rather than treating that reference as naming an image the host has not pulled

#### Scenario: An application that has never deployed does not abandon the run
- **WHEN** an application is enumerated but has no Compose file on the host
- **THEN** the run SHALL proceed, contributing nothing to the keep set for that application, rather than treating its absence as an unresolvable reference set

#### Scenario: An enumeration the host does not carry is distinguishable from one naming nothing
- **WHEN** the run finds no enumeration on the host at all, because the host has not been configured with one
- **THEN** it SHALL remove nothing, and SHALL report that condition distinguishably from an enumeration that is present and names no application, since the first is remedied by configuring the host and the second by editing the version-controlled list

#### Scenario: An empty enumeration removes nothing
- **WHEN** the version-controlled enumeration names no application at all
- **THEN** the run SHALL remove no image at all, and SHALL report that condition and fail, rather than proceeding with a keep set of only the images containers currently hold

#### Scenario: An empty keep set removes nothing
- **WHEN** the union of every enumerated application's references and every container's image is empty
- **THEN** the run SHALL remove no image at all

#### Scenario: An old image in active use is not removed for its age
- **WHEN** an image whose creation timestamp is far older than the schedule's interval is referenced by an enumerated application's Compose file or held by a container
- **THEN** that image SHALL still be present after the run

#### Scenario: A completed run reports what it did
- **WHEN** a scheduled run completes, whether it removed images or found nothing to remove
- **THEN** it SHALL report how many images it considered and how many it removed, counted over distinct image identities, and SHALL exit zero

#### Scenario: An abandoned run says why and fails
- **WHEN** a scheduled run is abandoned because the keep set could not be determined, because a reference was malformed, because the host carries no enumeration at all, because the enumeration names no application, because the keep set was empty, or because local images could not be enumerated
- **THEN** it SHALL report which of those ended it, distinguishably from a completed run that found nothing to remove, and SHALL exit non-zero so the host records a failed unit

#### Scenario: A non-responding runtime does not leave the unit running indefinitely
- **WHEN** the container runtime stops responding during a scheduled run, whether while resolving the keep set, while enumerating local images, or while removing one
- **THEN** the run SHALL be terminated at its duration bound, and that termination SHALL be recorded by the init system as a failed unit rather than reported by the run itself

#### Scenario: Configuring the host does not prune it
- **WHEN** the configuration management run that installs or updates the unit completes
- **THEN** no image SHALL have been removed as a result of that run, and the scheduled unit SHALL be armed for its next occurrence rather than having been executed

#### Scenario: A host that was down at its scheduled time still runs
- **WHEN** the host is not running at a scheduled occurrence and is later started
- **THEN** the run SHALL take place once after that start, rather than the occurrence being skipped
