# Design

## The measurement

Everything below rests on one measurement, taken because the backlog entry this change closes says in as many words that the remedy "was attempted and **not** measured cleanly" and that the other "does not stop the expansion — measured". One of those two statements is wrong, and the only way to find out which was to measure both properly.

**Where the measurement is taken.** From inside a running container, reading the environment the service process actually received, encoded as base64 so that whitespace and control characters survive the comparison. Not from `docker compose config`: that command escapes a literal `$` as `$$` in its own output, so it reports a value that looks corrupted when it is not and vice versa — which is how this entry's first diagnosis went wrong twice, in opposite directions.

**Every table below was re-taken on 2026-09-16 after the harness was found defective, and five of them changed — rounds 1, 2, 3, 4 and 6, with Decision 9's table gaining a column of its own.** Round 2 then changed a second time, and Decision 2's reasoning with it; the corrections live beside the claims they correct, in rounds 2, 3, 4 and 6 and in Decisions 2 and 9. The first version discarded Compose's standard error and compared its standard output alone, so a run Compose **refused** — it rejects a file it cannot parse and reads nothing — was recorded as a value that came back *empty*. It also let a refused run leave a container behind that a later invocation could read, which put a value from one round into another round's table. Both are fixed: each invocation now takes a Compose project of its own, and the container echoes back a nonce the caller checks, so an answer that did not come from the run that asked for it is refused rather than reported. What follows is the re-taken data, and **where a round's conclusion changed, the old one is stated alongside it** rather than replaced — the correction is the more useful record.

**The harness** is committed, as `tools/env-rendering-probe/` at the repository root, and this section is its findings rather than its description. It is not a test and sits in none of `AGENTS.md`'s three test rows: it spawns a container, which the static suite may not, and its subject is a workflow's output rather than an Ansible role's behaviour on a host. It is committed because Decision 6 makes this measurement the change's only behavioural evidence, and evidence a reader cannot re-take is evidence only about its author — the standard this repository's own rule on correcting an archived record already applies to a figure. It is also the starting point for the deploy-time round trip that Decision 6 defers.

**Versions.** Docker Compose **v5.4.0**, Docker Engine 29.7.2, on the authoring workstation, 2026-09-16. The production host was read the same day and runs Compose **v5.5.0** on the same engine. The skew is stated rather than resolved — see Decision 6.

**Counts.** Round 1 ran 12 values against 5 renderings; round 2 ran 10 against one; round 3 ran those 20 against 4 escaping candidates, then 21 further values and 10 adversarial ones against the two survivors; round 4 ran 15 against the other consumption path; round 5 ran 13 against the current rendering alone; round 6 ran 6 more against it, in positions round 5 held constant; round 7 ran 3 to settle a clause round 6 had inferred. Every round was then re-taken against the corrected harness, and the counts here are the re-taken ones. The tables for rounds 1 to 4 are **excerpts** chosen to show the distinct behaviours; rounds 5 and 6 are given in full, because what they establish is partly which positions were *not* tested. The full value lists are in the committed harness.

### Round 1: quoting alone

Excerpt, 8 of 12 values; `raw` corrupts 6 of the 12 and is what the workflow does today. **Refused** means Compose rejected the file and read nothing — loud, and not the same outcome as a value coming back altered.

| Value stored | `raw` | `"…"` | `'…'` |
|---|---|---|---|
| `ab$c#d` | `ab#d` | `ab#d` | intact |
| `"abc"def` | `abc` | **refused** | intact |
| `p@ss$word` | `p@ss` | `p@ss` | intact |
| `a$$b` | `a$b` | `a$b` | intact |
| `trail   ` | `trail` | intact | intact |
| `back\nslash` | intact | *a real newline* | intact |
| `${PATH}` | **the workstation's `PATH`** | **the workstation's `PATH`** | intact |
| `A1+b/c=` | intact | intact | intact |

Two findings decide the shape of everything after them. The parser interpolates a `${VAR}` in an unquoted or double-quoted value **from the rendering process's own environment**, so a secret that happens to spell one is replaced by whatever the runner holds under that name — the `PATH` row is that, and it is a worse outcome than corruption. And a double-quoted value has backslash escapes interpreted, so `back\nslash` arrives as two lines.

Single-quoting survived all twelve. **So the backlog entry's claim that single-quoting "does not stop the expansion" is false at this layer.** What is true is the sentence in `platform-deploy.yml`'s comment block that it was probably derived from: `echo "N='<secret>'"` in the **shell** layer still rendered `ab#d`, because there the secret was substituted into the script as text and bash expanded it before any file existed. Two layers, two different mechanisms, one of which was measured and reported as though it settled the other.

### Round 2: what single-quoting breaks on

All 10 values.

| Value stored | `'…'` |
|---|---|
| `a'b` | **refused** |
| `it's` | **refused** |
| `a"b'c$d` | **refused** |
| `trailing'` | **refused** |
| `\` | **refused** |
| `` (empty) | intact |
| `line1⏎line2` | intact |
| `a=b=c` | intact |
| `secret' #1` † | **`secret`** — silently |
| `a' #b` † | **`a`** — silently |

† Added 2026-09-16 by the code review that found them. The original eight held the apostrophe's *neighbours* constant — no value among them put a quote next to a space-preceded `#` — which is what let a wrong conclusion be drawn from them twice.

**Single-quoting has both failure modes.** It **refuses** the file where a quote is unbalanced — Compose rejects what it cannot parse, exits non-zero and reads nothing, which is loud — and it **truncates silently** where a closed apostrophe is followed by a space-preceded `#`, because what remains is a well-formed line whose tail is an inline comment: `secret' #1` arrives as `secret`, exit zero, nothing said. Decision 2 rejects it on both, and on a third ground of its own.

**How this round reached that, having been wrong twice in opposite directions**, kept because the pair is more instructive than either and because a reader cannot otherwise tell which parts of the claim above were checked:

*The first version* said the five refused values resolve to **empty**, and concluded that single-quoting "converts one silent corruption into another". That was the defective harness reading a refusal as an empty result.

*The second version* corrected that and over-corrected, concluding that single-quoting therefore has **no silent failure mode at all**. The last two rows are the counter-example, and they are in the corpus rather than in this prose so that re-running the round contradicts the wrong claim rather than leaving it to be re-derived.

**Both errors are one error**, which Decision 9 names a few paragraphs down: varying one thing while holding another constant, then concluding about the thing varied. Round 5 held the *position* and concluded about the character. This round's original corpus held the apostrophe's *neighbours* and did it again.

### Round 3: escaping

Four candidates, over the 20 values of rounds 1 and 2 as they then stood:

| Rendering | Silently altered | Refused |
|---|---|---|
| `'…'` with `'` → `\'` | 0 of 22 | 1 — a value that is a lone `\` |
| `'…'` with `'` → `'\''` | 0 of 22 | 7 |
| `"…"` with `\`→`\\`, `"`→`\"`, `$`→`$$` | **0 of 22** | **none** |
| `"…"` with `\`→`\\`, `"`→`\"`, `$`→`\$` | **0 of 22** | **none** |

The two single-quoted rows previously read as 1 and 6 *corrupt*; re-taken, they alter nothing and are refused instead — and escaping the apostrophe is also what stops round 2's silent truncation, since an apostrophe that cannot close the quoted region cannot hand the remainder to a comment. The escaping rows are the only two that neither alter a value nor refuse one.

The two survivors were then run against the same 22, then against 21 further values — leading and trailing whitespace, a tab, `%`, `!`, non-ASCII, a value that is exactly `$`, one that is exactly `"`, one that is exactly `'`, one that is a lone `\`, two random `openssl rand -base64` outputs — and against 10 adversarial values mixing backslash, dollar and quote adjacently, which is where an escaper with its substitutions in the wrong order fails: `a\$b`, `\\$`, `$\`, `"\$"`, `\$$`, `$$\\`, `a\\"$b`. **Both survived all 53 values** — the 22 of rounds 1 and 2, 21 further, 10 adversarial — altering none and being refused for none.

### Round 4: the other consumption path

The platform stack reads `.env` through `${VAR}` interpolation into the Compose file and through nothing else, which is what rounds 1 to 3 measure. `docs/onboard-an-application.md` §4.4 instructs application repositories to consume their own `.env` through `env_file:` on the service instead — a different path, and one this change corrects the instruction for, so the rule had to be established there rather than assumed to carry across. 15 values, against a service declaring `env_file:` and no `environment:`:

| Rendering | Silently altered | Refused |
|---|---|---|
| `NAME=value` | **7 of 15** | 2 |
| `NAME="escaped"` | **0 of 15** | **none** |

Previously recorded as 9 altered; two of those nine were refusals.

The path corrupts the same way and the same rule fixes it, so §4.4 carries the same sentence as the workflow.

**Two claims once stood in this paragraph and both are withdrawn**, in the order they were found:

1. *Withdrawn when round 5 was run.* It said an apostrophe survives the raw rendering on this path and is destroyed on the interpolation path. It survives both. What destroys it is the **single-quoted** candidate of round 2, a rendering this design rejects — two rows of one table read as though they belonged to one column.
2. *Withdrawn when the harness was repaired.* It said the paths differ, a value of exactly `"` or `'` resolving empty here and being yielded there. Neither half holds: both are **refused** rather than emptied, and refused on *both* paths.

So no difference between the two entry points has been measured at all. The rule was still established separately on each rather than inferred from one, which is worth doing whether or not a difference turns up. Both withdrawals are recorded rather than made silently, because this document is the change's only behavioural evidence and a reader has no other way to tell a corrected claim from one that was always right.

### Round 5: what the rendering being replaced actually corrupts

Rounds 1 to 4 establish what to write. This round establishes something only Decision 9 needs: which values the **current** rendering alters, since that is the set whose provisioned state is stale and therefore the set the migration report has to reach. 13 values, `raw` rendering, interpolation path.

| Class | Example | Current rendering |
|---|---|---|
| Dollar | `p@ss$word` | corrupt — expanded |
| Double quote | `"abc"def` | corrupt — stripped |
| **Embedded line break** | `line1⏎line2` | **corrupt — truncated at the break** |
| Leading whitespace | `' leading'` | corrupt — stripped |
| Trailing whitespace | `'trailing '` | corrupt — stripped |
| Apostrophe | `a'b`, `it's` | intact |
| Hash, leading or mid-value | `#leading-hash`, `mid#hash` | intact |
| Backslash | `a\b`, `back\slash`, `ends-with\` | intact |
| Tab, literal or embedded | `tab\there` | intact |

**The line break is the one that was missed**, and it is the most destructive of them: `printf 'NAME=%s\n' "$VALUE"` writes a second physical line into the file, so the value is truncated at the break and whatever followed is read as a further assignment or as nothing. A GitHub secret may be multi-line — one in this repository's own Environments is, `ANSIBLE_SSH_PRIVATE_KEY`, though it is not among these eight. The new rendering carries an embedded break through intact, measured in round 2; it was the report's trigger set that did not name it.

**This round varied the character and held the position**, and round 6 is what that omission cost. Read alone, the three intact rows for the apostrophe, the hash and the backslash say those characters do not corrupt. Two of the three conclusions are wrong, and the rows are not: `a'b` and `mid#hash` really are intact. They are intact **in the positions tested**, and those are not the positions where this parser treats either character as special.

### Rounds 6 and 7: the positions round 5 held constant

Round 5 tested each character in one or two positions and drew a conclusion about the character. This round tests the positions it skipped: a quote that **opens** a value, and a hash **preceded by whitespace**, which is where a dotenv parser's inline-comment rule fires. 6 values, both renderings, both consumption paths. **The two paths returned identical results for all six**, which is itself worth having.

| Value stored | Current rendering | New rendering |
|---|---|---|
| `'abc'def` | **`abc`** — the leading `'` opens a quoted region and the remainder is discarded, **silently** | intact |
| `'unclosed` | **refused** — the file is rejected and nothing is read | intact |
| `secret #1` | **`secret`** — the space-preceded `#` begins an inline comment | intact |
| `secret⇥#tab` | intact — a **tab** before the `#` does not begin one | intact |
| `\leading` | intact | intact |
| `"opens` | **refused** | intact |

**The apostrophe and the hash both corrupt, and round 5 released them.** `'abc'def` is the exact twin of round 1's `"abc"def` → `abc`, and round 1's whole `'…'` column — the basis of the rejected candidate in Decision 2 — is the demonstration that this parser honours a leading single quote. The evidence that these two are positional was on the page before round 5 was run.

**One refinement worth recording because it would be guessed wrong.** The inline-comment rule fires on a preceding **space** and not on a preceding tab. A reader reconstructing the rule from the word "whitespace" would include the tab and be wrong about it.

**The obvious analogy is the trailing-whitespace strip, and it does take both** — measured rather than assumed, because an earlier draft of this paragraph asserted it from the analogy alone and that is the reasoning the paragraph exists to warn against. Three values: `trailtab⇥` → `trailtab`, `⇥leadtab` → `leadtab`, and `trailmix ⇥ ` → `trailmix`. So the two rules genuinely differ on the tab — one scan takes it and the other does not — which is what makes reconstructing either from the other wrong in a way that looks careful.

**The backslash has no corrupting position among anything measured**, leading included. That keeps it what Decision 9 calls it — a margin — rather than quietly promoting it to a measured member.

## Decisions

### Decision 1: Escape the value rather than constrain what a secret may contain

The alternative is the shape the current documented instruction implies: refuse, at deploy time, a secret containing a character the parser treats specially. It is rejected on two grounds. Two of the seven values — the Slack webhook and the dead-man's-switch URL — are issued by a vendor, so a refusal names a defect the operator cannot remedy except by asking the vendor for a different URL. And a refusal fires on a deploy of a stack whose secret was accepted the day before, which turns a rendering defect into an outage of the deploy path. Escaping removes the question instead of relocating it.

The `openssl rand` instruction is kept all the same. It was never wrong, it costs nothing, and after this change it is hygiene rather than the mechanism — which is the part the documents have to say, because a reader who finds the instruction still there will otherwise read it as still load-bearing.

### Decision 2: Double quotes with three escapes, not single quotes

Round 2 is the measurement and carries the account of how it was reached, including the two wrong versions this decision's reasoning was written on before it. What that round establishes is that single-quoting has **both** failure modes — a refusal on an unbalanced quote, and a silent truncation where a closed apostrophe meets a space-preceded `#`. This decision's conclusion has never changed; its reasoning has been rewritten twice under it.

The comparison is therefore between a rendering that handles every value and one that, for some values, either stops the deploy or corrupts the credential without saying so. That is decisive three times over:

- **The deploy it stops is the one that cannot be fixed by the operator.** Two of the seven secrets are issued by a vendor. A webhook URL that happens to contain an apostrophe is not something anyone here can re-generate, so the refusal is not a prompt to fix the value — it is an outage of the deploy path for that stack until the vendor is persuaded to issue a different URL. Decision 1 rejects a deliberate refusal on exactly this ground; a refusal arriving as a side effect of the quoting style is the same cost without the intent.
- **It fails at the wrong moment.** The value is accepted into the Environment, renders fine, and stops the *deploy* — so the failure surfaces on the next unrelated change to `platform/`, attributed to that change, on a stack whose secrets nobody touched.
- **It corrupts silently in the case nobody looked at.** A password containing an apostrophe and a spaced `#` is not exotic — both characters are in the printable set a person picks from — and the result is a truncated credential that starts its service and reports healthy, which is the exact failure this whole change exists to remove.

The escaping has none of the three, at no cost but two more substitutions.

### Decision 3: `$$` for the dollar, not `\$`

Both measured identical over 53 values, so the choice is made on which one is the parser's own rule rather than on a result. Measured outside quotes, where the question separates them:

| `.env` line | Received |
|---|---|
| `PROBE=a$$b` | `a$b` |
| `PROBE=a\$b` | `a\` |
| `PROBE="a$$b"` | `a$b` |
| `PROBE="a\$b"` | `a$b` |

`$$` is honoured in both contexts; `\$` is honoured only inside double quotes, where it is a consequence of backslash-escape processing rather than a rule about `$`. So `$$` is the escape the parser defines and `\$` is one that happens to work in the context this change writes. `$$` is also the form `platform/docker-compose.yml` already uses for the same purpose — `pg_isready -U $$POSTGRES_USER`, and `{{ $$labels.cn }}` in an alert annotation — so the repository gains no second spelling for one idea.

### Decision 4: Backslashes are escaped first

`\` → `\\`, then `"` → `\"`, then `$` → `$$`. The order is not cosmetic: escaping quotes or dollars first introduces backslashes that a later `\` → `\\` pass would double, turning `a"b` into `a\\"b` and delivering a literal backslash the operator never stored. This is the defect the ten adversarial values of round 3 exist to catch, and it is what the static check asserts about the helper — the substitutions are individually obvious and their order is not.

### Decision 5: One helper, which both escapes and writes

The render block becomes a `render <name> <value>` helper and eight calls to it. The helper escapes the value into a variable and writes the whole assignment line itself; the caller passes a name and a value and reads nothing back. Inline escaping would work identically and was the first draft.

The helper is preferred because of what it does for the check: a static assertion over eight independently-escaped `printf` lines has to establish the same property eight times and passes silently when a ninth value is added unescaped, whereas over a helper it establishes the property once and then asserts that the block contains calls and nothing else. The defect being defended against here is a value added later by someone who did not read this file, which is exactly the defect a choke point catches and a convention does not.

**No `$(…)` anywhere in it.** Command substitution strips trailing newlines and a GitHub secret may end in one, so a helper that printed and a caller that captured would reintroduce a corruption at the moment the rest of them were being removed. That is why the escaping lands in a variable rather than on standard output.

### Decision 6: The parser's behaviour is evidenced here, not asserted by a test

What the new static assertions establish is that the render step **has** the shape this design decided — the helper exists, it applies those three substitutions in that order, every value goes through it. What they cannot establish is that Compose's parser honours it, because that needs a Compose run: `.github/tests` may not spawn a container, by a constraint asserted within that suite itself, and Molecule's subject is the behaviour of an Ansible role on a host rather than a workflow's output. So the behavioural evidence for this change is the measurement above, and the harness that produced it is committed so that the evidence can be re-taken rather than trusted.

**The residual, stated plainly.** The measurement was taken on Compose v5.4.0; the host that parses the file runs v5.5.0; and a future upgrade of either could change the rule with nothing here detecting it. The failure mode if that happens is the one this change removes, returned — silent corruption — rather than a red deploy. A deploy-time round trip, rendering the file and reading it back through the **host's** own parser before the stack is brought up, is what would close it; it is recorded in `docs/backlog.md` by this change rather than built here, because it belongs to the deploy path rather than to how a value is written.

### Decision 7: The obligation is stated at the parser's boundary, and the layers after it are named rather than claimed

An earlier draft of the delta obliged that "the value a service's **process** receives" be byte-identical to the secret. That is wider than this change's mechanism and is unsatisfiable by it for two of the eight values. `SLACK_WEBHOOK_URL` and `DEADMANSWITCH_URL` never reach a process environment at all: they are interpolated into the **content of an embedded Alertmanager YAML configuration**, inside a `configs:` block, unquoted — so after Compose's parser yields the value correctly, it is placed into a YAML document, where a `:` followed by a space, a `#`, a quote or a newline would change or break the parse. `ACME_EMAIL` lands in a Traefik `command:` argument, which is a third context again.

So the obligation is stated at the boundary this change controls: **the value Compose's `.env` parser yields for that name** is what must be byte-identical to the secret. That is what the escaping rule delivers, it is what the measurement measures, and it is true of all eight values.

The layer after it is named as a Non-Goal rather than silently excluded. Nothing here measures what an embedded YAML configuration does with a value carrying YAML's own metacharacters, and nothing here should be read as establishing it — a reader who takes the narrowed obligation as an end-to-end guarantee is making the mistake this decision exists to prevent. Both values are vendor-issued URLs today and neither carries such a character, which is why this is a residual rather than a defect; it is also exactly the reasoning Decision 1 refuses to accept as a discharge, so it is recorded as a thing to close rather than a thing that is fine.

### Decision 8: The two alert values do not reach their container on the deploy that corrects them

*A Shipped Configuration Change Is Visible to the Container Runtime* (`openspec/specs/iac-platform-deploy-pipeline/spec.md`) states it directly: where a value inside an embedded configuration is interpolated at deploy time, the committed text does not move when that value changes, so no property derived from it moves, and **the running container keeps the previous value**. Alertmanager's configuration is embedded, and this change alters no committed stack text.

The consequence is specific and has to be written down, because it is the sort a later reader reconstructs wrongly: if either alert URL is being corrupted today, the deploy that ships this fix renders it correctly, ships it, and leaves the running Alertmanager holding the corrupted one until something else replaces that container. The six values delivered through `environment:` do not have this problem — a changed interpolated value moves the service definition Compose hashes, so those containers are replaced.

This is why the effect observation in `tasks.md` names a deliberate replacement of Alertmanager rather than settling for "every service came up healthy", which is a check both values pass while one of them is inert.

### Decision 9: The transition is made observable rather than assumed safe

A value that is being corrupted **today** has whatever state was derived from it keyed to the corrupted form. `POSTGRES_PASSWORD` is the sharp case: `initdb` consumes it once, at the instance's first boot, so the role's stored password is the corrupted value, and a deploy that starts delivering the true one breaks authentication for every client of that instance. The stacks deploy without an order imposed between them — *Each Stack's Deploy Attaches to the Environment Its Own Declaration Names* is what forbids imposing one — so production is not behind staging and there is no lower environment that meets this first.

An earlier draft waived this in a Non-Goal, on the grounds that the generated values come from `openssl rand -base64`, whose alphabet the escapes are inert on. That reasoning is exactly what this change's own delta declares cannot discharge the obligation — a property of the moment a value was generated, not of the file that carries it — and it does not reach the two vendor-issued values at all. A change may not use as its safety argument the reasoning it is adding a requirement to forbid.

So the render step reports it. After rendering, it names — on standard output, as a notice, **without any value** — each variable the rendering being replaced would have altered. On the first deploy after this change lands, that notice is the migration signal, and a notice reporting nothing is the evidence that nothing was being corrupted and nothing needs rotating.

**The set is measured, and each member is justified by a position that corrupts.** Rounds 5 and 6 are what it is taken from:

| Member | The position that justifies it |
|---|---|
| `$` | anywhere unquoted — expanded |
| `"` | opening the value — quoted region, remainder discarded, silently |
| `'` | opening the value — the same, measured in round 6 |
| `#` | preceded by a space — begins an inline comment |
| A line break | anywhere — the value is truncated at it |
| Leading or trailing whitespace | by definition — stripped |

**Both quote characters earn their place on a silent position, not on a refusal.** `'abc'def` yields `abc` and `"abc"def` yields `abc`, with nothing said; an *unterminated* quote is refused instead, loudly, and would need no report to be noticed. The set is built from what goes unnoticed, which is what the report exists for — a member whose only failure mode is a refused deploy would be noise in it.

**Detection is by presence anywhere in the value, not by position.** A member earns its place by having *a* position in which it corrupts; the notice then reports the character wherever it appears. The asymmetry is deliberate and is the rule to keep: positional detection would be a second place where this parser's rules are re-derived, in workflow code no test in this repository can exercise, and the rules are not what anyone would guess — round 6 measured a space before a `#` beginning a comment and a tab before it not doing so. Over-reporting a mid-value apostrophe costs one operator a look at a credential that turns out to be fine. Re-deriving the rule costs the thing this whole change exists to remove.

**One member beyond the measurement, named as a margin rather than smuggled in.** The backslash has no corrupting position in anything rounds 5 or 6 measured, leading position included. It is reported anyway, because it is the character whose treatment differs most across the four contexts this problem has already produced — unquoted, double-quoted, single-quoted, `env_file:` — and is therefore the likeliest to be altered somewhere neither round looked. A false positive costs one investigation; a false negative costs an authentication failure with nothing pointing at its cause. Stating that it is a margin is what stops a later reader "correcting" the set against round 6's intact backslash row.

**An earlier draft dropped the apostrophe and the hash on round 5's evidence, and that was wrong.** It is recorded rather than quietly fixed, because the mistake is instructive and repeatable: round 5 varied the character, held the position, and concluded about the character, and the drop then read as measured when it was measured only in the safe position. The margin paragraph above and that drop could not both be right about one measurement's completeness — one said round 5 might not have looked everywhere, the other said it had. Round 6 is what settled it, and the answer was that the margin's reasoning was the sound one.

**What it discloses, and why that is the right trade.** The report emits at most one bit per variable — membership in a small set, or edge whitespace — against roughly 256 bits for an `openssl rand -base64 32` value. It is held at one bit by excluding the character itself and any count; a count would be materially more, which is why the task forbids one. So the disclosure is negligible **because** these values are high-entropy and the report is deliberately impoverished, and not because metadata is categorically not a value: the same report over a short or structured secret would not be defensible on this reasoning.

**The audience changes too, and that is the part a magnitude argument alone misses.** A GitHub Environment secret is readable by nobody — not by the operator who set it. A workflow run log is readable by every reader of the repository. So the bit does not merely stay small; it moves from a store nobody can read into one many can. Against that: without the notice, the only way an operator learns a credential was silently corrupted for months is an authentication failure on production after a merge, with nothing in the run pointing at the cause. The repository is private, its readers are the people who would be doing the rotating, and one bit about a 256-bit value is worth that. The trade is recorded here so that a later change widening the report — adding the character, or a count, or extending it to a low-entropy value — has to re-make it rather than inherit it.

**The escaped form of a value is not masked and must not be printed.** GitHub registers its log masking against each secret's own value; the escaped variant is a different string, so a step that prints it defeats masking entirely. This change is the first thing to create such a variant, so the prohibition arrives with it: the escaped value is written to the file and goes nowhere else.

The notice is kept permanently rather than removed after the transition, because the same signal is what a future rotation needs — a value that newly carries such a character is correctly escaped from now on, and whatever was provisioned from its predecessor still needs re-provisioning.

### Decision 10: The onboarding instruction is corrected; the application repositories are not

`docs/onboard-an-application.md` §4.4 instructs every application repository to render `.env` from its own secrets and ship it to the host by the same `tar | ssh` path, which reproduces this defect once per application. The instruction is this repository's and is corrected. The workflows already written from it — `commerce-ops`'s, and any copied from it — are not: they live in repositories this one has no authority over, and a change here cannot edit them. Naming that boundary is the whole of what this change does about them.

§4.4 instructs `env_file:` rather than interpolation, which is a different consumption path from the platform stack's. Round 4 measures it rather than assuming the rule carries across, so the corrected instruction states a rule that was established on the path it is given for.

## What this change does not establish

A rendered value reaching the service intact says nothing about the value being *correct*. `alert-on-the-exporter-being-unable-to-read-postgres` is the entry for the case where a credential is wrong for any reason at all and nothing says so; this change removes one cause of that and leaves the detection gap exactly as it found it.
