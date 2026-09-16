## MODIFIED Requirements

### Requirement: Platform Secrets Rendered from CI at Deploy Time
The `.env` file consumed by `platform/docker-compose.yml` SHALL be rendered from GitHub Actions secrets by the deploy job at deploy time and transferred to the host alongside the Compose file. It SHALL NOT be committed to the repository in any form, plaintext or encrypted.

Each stack SHALL have a complete set of values of its own, held in its own GitHub Environment: its own host, its own database credentials, its own dashboard credential, its own certificate-registration address, and its own alert-delivery targets. A value SHALL NOT be shared between stacks by being held as a repository secret of the same name, since a repository secret holds one value and every stack reading it would render the same value into `.env` — a shared database password or a single alert target reached by two hosts.

Where a stack's alerts are delivered to a destination shared with another stack's, the running stack definition carries nothing identifying which host an alert came from, so the delivery target is what distinguishes them. Each stack's alert-delivery secret SHOULD therefore address a destination of its own. This is a property of the values an operator enters into an Environment; nothing in the repository can verify it.

**The value the file's own parser yields for a name SHALL be byte-identical to the secret the deploy job read.** The rendered file is not consumed as text: the file format has a parser, and that parser expands variable references, processes quotes and escapes, and strips trailing whitespace. A rendering that writes a value unaltered into the file therefore does not deliver it unaltered to whatever reads it. This obligation SHALL be read as reaching every value the deploy job writes into that file rather than only the ones that are credentials.

The obligation is stated at that parser's boundary because that is the boundary this rendering controls. A value the parser yields correctly may afterwards be placed into a further context with quoting rules of its own — a configuration document embedded in the stack definition, or a command-line argument — and **this requirement does not reach those contexts**.

**Each value SHALL therefore be escaped for that parser as it is written**, so that the parser's own processing reconstructs the original. The obligation SHALL NOT be discharged by any expectation about what the values contain. Some of the values a stack holds are issued by third-party services rather than chosen by the operator, so an alphabet restriction is not a rule the operator can apply to them; and a rule that a generated value avoids the parser's special characters is a property of the moment it was generated, not of the file that carries it. Guidance to generate a value from a safe alphabet MAY be given, and SHALL NOT be relied upon as the mechanism.

**A rendering SHALL NOT be adopted that leaves any value it may be given unrepresentable**, whether it writes such a value as something else or produces a file the parser rejects. The first failure is the one this requirement exists to prevent and is silent: a corrupted or emptied credential starts its service, satisfies the deploy's wait for health, and leaves the run green, which is the same state *An Incomplete Per-Stack Secret Set Is Reported by Name* in this capability forbids for an absent secret. The second is loud but is not therefore acceptable — it withholds the deploy of a stack whose secrets are unchanged, and some of those values are issued by third parties rather than chosen, so it names a defect no operator here can remedy. Neither SHALL be adopted on the grounds that it handles more values than the rendering it replaces.

**Every value written into that file SHALL be written through a single escaping point**, rather than each assignment carrying its own escaping. The property being defended is that a value added later is escaped too, and a convention that each author repeats is not that property. It follows that this SHALL be statically verifiable from the workflow's committed text: that the escaping point exists, that it applies the substitutions it claims in the order it claims them, and that the file is written by nothing else.

**The deploy job SHALL report, by name, each value it rendered that the rendering this requirement replaces would have altered.** Anything provisioned from such a value before this rendering existed — a database role created from a password at first boot, an account registered with a credential — is keyed to the altered form and ceases to match when the correct value is first delivered. That failure is an authentication error at an arbitrary later moment with nothing pointing at its cause, and a report naming the variable is what makes it a known consequence of a known deploy instead. Which values those are is a fact about the rendering being replaced rather than about this capability, and SHALL be established by measurement and recorded in the change that establishes it; a later measurement revising that set SHALL NOT require this requirement to change.

**That report SHALL name variables only.** It SHALL NOT contain any value, any character taken from a value, or any count of such characters. Nor SHALL any escaped form of a value be emitted: an escaping transforms a value into a string that a secret-masking facility registered against the original does not cover, so the escaped form is the one shape of a credential that reaches a log in the clear.

#### Scenario: Rendered .env never enters version control
- **WHEN** a deploy job renders `.env` from GitHub Actions secrets
- **THEN** the rendered file SHALL exist only in the workflow run's ephemeral workspace and on the host, and SHALL NOT be committed to the repository

#### Scenario: Deploy job authenticates as the provisioned deploy account
- **WHEN** a stack's deploy job connects to that stack's host
- **THEN** it SHALL authenticate as the restricted `deploy` account provisioned by the host-configuration change, not as any operator's personal account

#### Scenario: Two stacks render two different sets of values
- **WHEN** a merge deploys to two stacks
- **THEN** each stack's `.env` SHALL be rendered from that stack's own GitHub Environment's secrets, so that neither host receives the other's database credential, dashboard credential or alert targets

#### Scenario: A secret containing a character the parser treats specially survives the parse
- **WHEN** a secret whose value contains a dollar sign, a quote character, a backslash or trailing whitespace is rendered into `.env` and that file is parsed
- **THEN** the value the parser yields for that name SHALL be byte-identical to the secret

#### Scenario: A secret that spells a variable reference is not resolved from the rendering environment
- **WHEN** a secret's value spells a variable reference, such as `${PATH}`
- **THEN** the parser SHALL yield that text, and SHALL NOT yield the value that name holds in the environment of the job that rendered the file

#### Scenario: A secret containing the quote character is not yielded as empty
- **WHEN** a secret whose value contains the quote character is rendered into `.env` and that file is parsed
- **THEN** the parser SHALL yield that value, and SHALL NOT yield an empty one

#### Scenario: Every rendered value passes through the escaping point
- **WHEN** the deploy workflow's committed text is read
- **THEN** every name it writes into `.env` SHALL be written through the single escaping point, and no line SHALL write a value into that file by any other route

#### Scenario: A rendered value the previous rendering would have altered is reported by name
- **WHEN** a deploy job renders a value that the rendering this requirement replaces would have altered
- **THEN** the job SHALL report that variable's name
- **AND** the report SHALL NOT contain that variable's value, any character taken from it, or any count of such characters

#### Scenario: A deploy that altered no value says so
- **WHEN** a deploy job renders every value and none of them is one the previous rendering would have altered
- **THEN** the job SHALL report that explicitly, rather than reporting nothing

#### Scenario: The escaped form of a value is never emitted
- **WHEN** the deploy workflow's committed text is read
- **THEN** no line SHALL emit the escaped form of a rendered value, which secret masking registered against the original does not cover
