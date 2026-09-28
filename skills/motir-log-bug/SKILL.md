---
name: motir-log-bug
description: File a defect into a Motir project — `motir log bug <text>`. Use when a bug turns up while running a card, verifying a story or using the product, and fixing it is not the job in hand, or when the user asks to log, file or record a bug in Motir. It root-causes the defect first, looks for the card someone already filed, then files ONE bug placed by what it blocks and linked to where it was found.
---

# `motir log bug <text>` — file one verified defect

A bug is the one work item an agent creates **directly** in Motir, with no plan for a person to
approve: it records something that already went wrong, claims no scope and changes no other card, and
it often has to block a card in the same breath. That is exactly why it is worth filing well — the
card is what the next person fixes from.

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

1. `prompts/_shared.md` — the MCP mechanics, the kind-parent rules, and why a bug is the one
   exception to *a planning pass proposes*.
2. `prompts/log-bug.md` — the protocol in full: the mandatory `<text>`, debug-it-first, the
   out-of-scope rule, the placement (an edged bug stays in its runnable container, an edge-less one is
   filed into the `Bugs` folder), the wiring and the scheduling.
3. `prompts/plan-rules/kind-bug.md` — the acceptance-criteria rules for a defect's body.
4. `prompts/run.md` — only when the root cause is a card the PLAN got wrong: that bug's home is named
   there.

**It printed `STANDALONE MODE`:** follow the procedure below.

## Standalone mode

> Condenses `prompts/log-bug.md` § *Bug title*, § *Placement* and § *Procedure*, as of the hashes in
> [`SYNC.json`](SYNC.json).

Everything here goes through the **Motir MCP server** connected to your agent — the tools are named
below exactly as the server names them (your client may prefix them, e.g. `mcp__motir__create_work_item`).
If the Motir tools are not available at all, stop and tell the user to connect the MCP first
(<https://motir.co/docs/mcp>). If a call fails with a connection error, a 401 or a not-found, **stop
and report** the whole bug you meant to file — title, placement, description, what it blocks — so
nothing is lost. Never work around a failed call.

### 1. The text is a claim — debug it before you write anything

- **No `<text>` ⇒ ask what the bug is.** Never file an empty, vague or guessed defect.
- **Find the real root cause.** Read the code, reproduce the defect (a failing test where you can),
  and establish what is actually wrong: *where* it lives (`file:line`), how to reproduce it, and the
  direction of the fix. What you file is your diagnosis, not the reporter's words.
- **Not a bug after all** — the behaviour is correct, the premise is false, or it is already fixed ⇒
  **file nothing.** Report what you found, with the evidence, and ask whether they still want it
  tracked.
- **The card is wrong, not the code** — the defect is that the work item itself asked for the wrong
  thing — is not a bug to file. It is a re-plan: in a run, that is `motir-run`'s *the card is wrong*
  step.

### 2. Look for the card that already exists — project-wide

Parallel sessions meet the same defect at the same time, so this is the cheapest read in the
procedure and the one that matters most.

- `search_work_items` over the whole project with a `text` filter on the defect's own words — the
  symptom, the error string, the file.
- `search_work_items_semantic` with the defect described **without** its implementation noun — a card
  written by someone else is worded differently.
- `git branch -r` and `gh pr list --state all --search "<the surface>"` — a fix can be on a branch or
  in review before any card names it.
- **Found it?** Add your evidence to that card with `add_comment` and do **not** file a second one.
- **Count while you are there.** If this would be the **third** open bug against the same code path
  in the same story, the path's design is the likelier defect: say so in the bug, naming either the
  three independent root causes or the re-design card it should wait on.

### 3. The edge test decides where the bug lives

One question: **does the bug `block` a card that is not Done** — usually the card you are running,
which cannot finish while the bug stands — **or is it `blocked_by` one?**

- **Yes (an edge)** ⇒ file it under the **parent** of that card — the story (or task / bug) one level
  above it, `parentKey`. Read that parent's status first (`get_work_item`): if it is Done or Cancelled,
  or the card has no parent, use the `Bugs` folder instead and still wire the edge. Filing under a
  finished card re-opens it and everything above it.
- **No edge** ⇒ file it into the project's **`Bugs` folder**: `list_folders`, take the folder whose
  `path` is exactly `["Bugs"]`, and pass its id as `folderId` with **no** `parentKey` (the two are
  exclusive). Never a sub-folder you were not sent to, never a folder you made up — this skill cannot
  create one. **No `Bugs` folder ⇒ stop and ask the user where bugs go.**
- **`relates_to` is not an edge.** Every bug gets one (step 5), so it cannot be what decides.
- **A bug is never `blocked_by` a Done card.** A defect in shipped work is recorded by `relates_to`
  to that card.

### 4. File it

`create_work_item` with `projectKey`, `kind: "bug"`, **exactly one** of `parentKey` / `folderId`, a
`priority`, the `targetRepo` the fix will land in when you know it, and:

- **`title`** — the one-line summary alone (e.g. `Primary button text fails contrast in dark mode`).
  The key Motir allocates is the id; add no prefix or number of your own.
- **`descriptionMd`** — in this shape, the first line first:

  ```
  **Found while:** running [ACME-12](motir:<id>) — branch <branch> @ <short sha>
  **Type:** bug (implementation defect)
  **Placement:** the parent of ACME-12 (the bug blocks it)  |  the Bugs folder (no edge)
  **Root cause / fix:** what is actually wrong, where (file:line), how to reproduce it, the fix direction
  **Resolution:** (open)
  ```

  The *Found while* activity is one of `running <card>` (plus branch or commit), `planning <card>`,
  `verifying <card>`, or `dogfooding <the page or route>`. It records where the bug was **found**; the
  edge test still decides where it **lives**.

Then **`update_work_item { key, explanationMd }`** — why the defect matters, in a paragraph:
`create_work_item` has no field for it.

### 5. Wire it

- `link_work_items { fromKey: <the bug>, toKey: <the card it was found in or is about>, relationship: "relates_to" }`
  — always.
- The edge from step 3, when there is one — e.g.
  `link_work_items { fromKey: <the blocked card>, toKey: <the bug>, relationship: "blocked_by" }`.
- `validate_work_item { key: <the bug> }` and read every entry in `advisories`: one naming a card that
  is not Done is a `blocked_by` to wire, not a note to leave.

### 6. When it blocks the card you are running

- `transition_status` that card → **Blocked** — correct here, because a real `blocked_by` edge now
  holds it out of the ready set.
- If that card is in a sprint, `move_to_sprint { keys: [<the bug>], sprintId }` so the bug is fixed
  in the same sprint (`get_work_item` on the card gives its `sprintId`). Not in a sprint ⇒ leave the
  bug in the backlog too.

A bug that blocks nothing leaves the in-flight card alone — file it and keep working.

### 7. Report, and keep the fix separate

- If you are inside a run, add a line to that pull request's description:
  `Discovered: bug ACME-<n> — <one line> (blocks this card | no block)`. **Never fix it inside that
  pull request** — the fix is its own card and its own pull request.
- Report the new key, where it was placed (the parent's key or the `Bugs` folder), its edges, and —
  if it blocked the card in flight — that the card is now Blocked and which sprint the bug joined.
