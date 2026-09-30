---
name: motir-guide
description: Walk a person through a Motir human card — any card whose executor is human, whatever its type (manual, verification, deploy, review…) — one step at a time — `motir guide <key>`, or `motir guide` for their own unfinished card or the next ready one. Use when the user asks to be guided, walked or talked through a human card or its to-do list — setting up an account, rotating a secret, adding a DNS record, configuring a dashboard, verifying a production release — or to help them do the human steps of a card. It claims the card, gives exactly one step at a time with its notes and the command to copy, checks what it can with read-only means before ticking the step on the card, resumes where an interrupted walk stopped, and closes the card with a summary of what was done and checked — to Done, or, when the card has a linked pull request, on that pull request's merge.
---

# `motir guide [<key>]` — one human step at a time, checked and recorded

A human card — `executor: human`, whatever its `type` — is work a person does: an account to create,
a secret to set, a record to add, a production release to verify. Its steps live on the card as a
**to-do list**. This skill walks the person through that list
**one step at a time**: it gives a step, waits, checks what it can without changing anything, ticks
the step on the card, and only then gives the next. Progress lives on the card, so a walk that stops
halfway resumes exactly where it stopped — for this person or a teammate.

## Runbook mode

Motir's own team keeps its full procedure in a private runbook checkout (`motir-meta`). Look for it
first; you almost certainly do not have it, and then this section ends with **Standalone mode**.

```sh
# Where the runbook is, if anywhere: $MOTIR_META, else a motir-meta checkout at or above the working
# directory (the checkout itself, or one beside an ancestor).
[ -z "${MOTIR_META:-}" ] || [ -f "$MOTIR_META/prompts/_shared.md" ] || \
  { echo "MOTIR_META=$MOTIR_META holds no prompts/_shared.md — fix it, do not fall through"; exit 1; }
META="${MOTIR_META:-}" d="$PWD"
while [ -z "$META" ]; do
  for c in "$d" "$d/motir-meta"; do
    [ -z "$META" ] && [ -f "$c/prompts/_shared.md" ] && META="$c"
  done
  [ "$d" = "/" ] && break
  d="$(dirname "$d")"
done
[ -n "$META" ] || ! [ -f "${WORKSPACE:-/workspace}/motir-meta/prompts/_shared.md" ] \
  || META="${WORKSPACE:-/workspace}/motir-meta"
if [ -n "$META" ]; then
  echo "RUNBOOK MODE — $META"; cd "$META" && git fetch origin && git rev-parse HEAD origin/main
else
  echo "STANDALONE MODE — no runbook at or above $PWD"
fi
```

**It printed `RUNBOOK MODE`:** the runbook is the rules of record, and everything below the next
heading is IGNORED — it is a condensation for people who do not have the runbook, never a second
source. `origin/main` is authoritative, not `HEAD`: when the two hashes differ, read each file with
`git show origin/main:<path>`. Read, in order:

1. `prompts/_shared.md` — the MCP mechanics, the status ladder, and why a halted card is parked at
   `planning` rather than Blocked.
2. `prompts/guide.md` — the protocol in full: select and refuse, claim or resume, take or derive the
   steps, one step at a time, read-only validation, tick, stop anywhere, a step that cannot be done as
   written, the close and the never-list. It cites `prompts/plan-rules/type-manual.md` (how a step is
   written), `prompts/mark.md` (the no-pull-request close) and `prompts/run.md` (the re-plan path) —
   read each where it points.

**It printed `STANDALONE MODE`:** follow the procedure below.

## Standalone mode

> Condenses `prompts/guide.md` § *SELECT AND REFUSE*, § *CLAIM*, § *TAKE THE STEPS*, § *ONE STEP AT A
> TIME*, § *VALIDATE*, § *TICK*, § *STOP ANYWHERE*, § *A STEP THAT CANNOT BE DONE AS WRITTEN*,
> § *CLOSE* and § *WHAT THIS PROTOCOL NEVER DOES*, as of the hashes in [`SYNC.json`](SYNC.json).

Everything here goes through the **Motir MCP server** connected to your agent — the tools are named
below exactly as the server names them (your client may prefix them, e.g.
`mcp__motir__list_work_item_todos`). If the Motir tools are not available at all, stop and tell the
user how to connect Motir: in Claude Code with the `motir` plugin installed, run `/mcp` and
authenticate `motir`; otherwise, connect the MCP as described at <https://motir.co/docs/mcp>. If a
call fails with a connection error, a 401 or a not-found, **stop and report** what you were about to
do to which card and step — never work around a failed call.

The three to-do tools:

| tool | what it does |
|---|---|
| `list_work_item_todos { key }` | the card's steps in order — each `{ id, text, notesMd, commandText, executor, done }` — and `progress` (`done` of `total`) |
| `add_work_item_todo { key, text, notesMd?, commandText?, executor? }` | appends ONE step at the end |
| `set_work_item_todo_done { key, todoId, done }` | ticks (`true`) or unticks (`false`) one step |

**Ticking the last step does NOT move the card** — closing it is step 9 below, never a side effect.
Ticking is idempotent, so a repeated tick keeps who ticked it first.

### 1. Select, and refuse the cards this is not for

- **`motir guide <key>`** — `get_work_item { key }`, and keep the result.
- **`motir guide`** — first the person's own unfinished walk: `whoami`, then `search_work_items` with
  `status is_any_of ["in_progress"]`, `assignee is_any_of [<their id>]`. Its rows carry no `executor`,
  so read each with `get_work_item`, lowest key first; the first whose `executor` is `human` is
  resumed. None ⇒ `list_ready { projectKey }`, paging, and take the first row whose `executor` is
  `human`. Neither ⇒ say there is no human card to guide and stop.

Refuse, in this order — **say why, and change nothing**:

1. `executor` is not `human` ⇒ an agent builds it, it is not guided: point at `motir run <key>` (the
   `motir-run` skill). The `type` decides nothing — a human card of any type is guided.
2. Status `done` or `cancelled` ⇒ it is already finished. Re-opening it is a person's decision.
3. Archived ⇒ say so, with the reason from its latest comment.
4. `readiness.ready` is false ⇒ name the cards it waits on (`openBlockers`) and their status. A step
   done before its prerequisite is the step most likely to be done twice.

### 2. Claim it, or resume

`claim_work_item { key }` — it assigns the card to the person and moves it to In Progress in one call.
Do not use `transition_status` instead: it assigns nobody. The answer:

- `claimed` — theirs now; go on.
- `mine` — already In Progress and theirs: **resume**. Step 4 starts at the first unticked step.
- `taken` — someone else holds it (named). Say who and stop.
- `not_claimable` — Planning, Implemented, In Review, Approved or archived. Say which and stop; a card
  at Planning is waiting for its plan to be corrected (step 8).

### 3. Take the steps

`list_work_item_todos { key }`.

- **It has steps** ⇒ they ARE the steps, in their order. Never rewrite, reorder or skip a list the plan
  wrote; a step the person thinks is wrong goes to step 8.
- **It has none** ⇒ derive ordered steps from the card's description, one **operation** per step (a
  step that needs "and" is two steps; "go to the page" is not a step — it goes in the next step's
  `notesMd`; a command goes in `commandText`, not in the text; text at most 200 characters, notes 2000,
  command 500). **Show the whole list and ask.** On the person's OK, `add_work_item_todo` each step in
  order — they then appear on the card and survive this session. No OK ⇒ write nothing, guide from the
  proposal, and say progress will not be saved.
- **Nothing to derive from** ⇒ step 8: the card is missing its content.

### 4. One step at a time

Take the **first unticked** step and give the person exactly that: its `text`, its `notesMd`, its
`commandText` in its own code block to copy, and where they are (`2 of 5`). **Then wait.** Never give
two steps at once. Their answer is one of:

- **done** ⇒ step 5;
- **a question** ⇒ answer it; the step is still open;
- **it can't be done as written** ⇒ step 8;
- **stop** ⇒ step 7.

A step whose `executor` is `coding_agent`: offer to do it yourself, saying exactly what you will run.
**Only on their go-ahead**, do it, then check it in step 5 like any other. The executor is a label; it
authorizes nothing.

### 5. Check it — read-only — before ticking

Check the step with the strongest **read-only** means it allows, and **say what you saw**: fetch a URL,
run a read-only command (`dig`, `gh … view`, `curl -I`, a CLI's `status` / `list` / `whoami`), or read
Motir. **Never change a third-party system to check a step** — no writes, no test transactions.

- **Passes** ⇒ step 6.
- **Cannot be checked** (a dashboard setting, a secret you must not read) ⇒ say so, take their word,
  step 6 — and remember it was on their word, for step 9.
- **Fails** ⇒ **do not tick it.** Say exactly what you saw (the record returned, the status code) and
  offer the same step again. Propagation delays (DNS, caches) are said out loud and re-checked, never
  assumed away. Repeated failure is a reason to offer step 7 or step 8 — never to tick anyway.

### 6. Tick it

`set_work_item_todo_done { key, todoId: <the step's id>, done: true }`, and tell them the progress it
returns. Only after their confirmation and a passing check where one was possible; one step at a time,
never ahead of its turn. A step ticked by mistake is unticked with `done: false`, and you say so. Then
the next unticked step (step 4), or step 9 when every step is ticked.

### 7. Stop anywhere

They may stop at any step. **Ticked steps stay ticked, the card stays In Progress and theirs.** Tell
them which step they stopped at and that `motir guide <key>` picks up there. Write nothing else: the
list is the record.

### 8. A step that cannot be done as written

The step is wrong, the system changed, a prerequisite is missing, or there was nothing to derive steps
from. **Do not invent a replacement step and do not edit the list** — the card is wrong, and that is a
decision for the plan, not for this walk:

1. `add_comment { key, body }` — which step, what they found, what you checked, and the correction you
   would suggest.
2. `transition_status { key, status: "planning" }` — so no one picks it up until it is corrected. (Not
   Blocked: a Blocked card can still be claimed.) Ticked steps stay ticked.
3. Stop, and tell them the card needs its plan corrected in Motir (or through Motir's planner) before
   the walk can continue; `motir guide <key>` then resumes at the first unticked step.

### 9. Close it

When every step is ticked:

1. `add_comment { key, body }` — each step and how it was confirmed: **checked** (and what the check
   saw), **on the person's word**, or **done by the agent** (and checked). Never a secret's value. A
   human card usually has no pull request, so this comment is the record the close rests on.
2. **No linked pull request** (the card's `deliveries` is empty) ⇒ walk it to Done:
   `transition_status { key, status: "done" }` from In Progress. If a step is refused, the error lists
   the statuses it may move to — take the one leading to Done and continue. Never `cancelled`: the work
   was done. **A linked pull request** (a human review, say) ⇒ do not move the status: its merge closes
   the card. Say so and name the pull request.
3. `get_work_item { key }` and report the status it now reads and the cards it unblocks (`blocks`).

**Never close with an unticked step.** A step they agree is unnecessary goes to step 8 — removing it is
a plan change.

### Never

- More than one step at a time, or a tick before the person confirms.
- A tick on a step whose check failed.
- A write to a third-party system to check a step.
- An agent step without the person's go-ahead.
- Rewriting, reordering or deleting a list the plan wrote, or writing derived steps without their OK.
- Improvising a replacement for a step that cannot be done as written.
- Guiding a card whose `executor` is not `human`, re-opening a finished one, closing one with an
  unticked step, or hand-closing one whose pull request has not merged.
