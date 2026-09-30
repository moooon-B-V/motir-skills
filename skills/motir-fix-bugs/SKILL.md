---
name: motir-fix-bugs
description: Clear a Motir project's Bugs folder — `motir fix bugs` or `motir fix bugs <limit>`. Use when the user asks to fix, clear, work through, triage or drain the bugs in Motir's Bugs folder, or to fix the open bugs one by one. It takes the folder's own To Do bugs oldest first, one at a time, and gives each exactly one outcome — one pull request that fixes only that bug, a blocked_by edge to the card it genuinely waits on, or a comment with the evidence when it is already fixed, cannot be reproduced or needs a person — so the loop ends by itself and reports what happened to every bug.
---

# `motir fix bugs` — clear the Bugs folder, one bug at a time

A project's `Bugs` folder is where every defect that blocks nothing is filed. This skill works through
it: **one bug at a time, oldest first, and every bug leaves with exactly one outcome** — fixed in its
own pull request, wired to the card it is really waiting on, or answered with evidence. Each outcome
takes the bug out of To Do, which is what makes the loop finish instead of offering the same bug again.

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

1. `prompts/_shared.md` — the MCP mechanics, the status ladder, and why a `blocked` status is only
   honest beside a real edge.
2. `prompts/fix-bugs.md` — the protocol in full: the population, the one-bug cadence, the three
   dispositions in order, the report and the never-list. `prompts/fix-bugs.py next` is its exit test
   (`--limit <n>` for `motir fix bugs <n>`), and `record` refuses a bug that has not left To Do.
3. `prompts/run.md` — the per-card run every FIXABLE bug goes through, the reproduction rule and the
   re-plan path.

**It printed `STANDALONE MODE`:** follow the procedure below.

## Standalone mode

> Condenses `prompts/fix-bugs.md` § *THE POPULATION*, § *THE CADENCE*, § *THE DISPOSITIONS*,
> § *THE REPORT* and § *WHAT THIS PROTOCOL NEVER DOES*, as of the hashes in [`SYNC.json`](SYNC.json).

Everything here goes through the **Motir MCP server** connected to your agent, plus `git` and the
GitHub CLI (`gh`). Tools are named exactly as the server names them (your client may prefix them, e.g.
`mcp__motir__search_work_items`). If the Motir tools are not available at all, stop and tell the user
how to connect Motir: in Claude Code with the `motir` plugin installed, run `/mcp` and authenticate
`motir`; otherwise, connect the MCP as described at <https://motir.co/docs/mcp>. If a call fails with
a connection error, a 401 or a not-found, **stop and report** what you were about to do to which bug.
Never work around a failed call.

### 1. The population — the folder's OWN To Do bugs

1. `list_folders { projectKey }` and take the folder whose `path` is exactly `["Bugs"]`. **None ⇒ stop
   and ask the user where their bugs are filed.** Never pick another folder, never create one.
2. `search_work_items` with the filter `kind is_any_of ["bug"]`, `status is_any_of ["todo"]`,
   `folder is_any_of [<that folder's id>]`, paging with `nextCursor` until it is null.
3. **For each candidate, `get_work_item` and keep it only if its `folderId` IS the Bugs folder's id.**
   The `folder` filter also matches everything in folders INSIDE `Bugs` — `Bugs / Planning bugs`, the
   `Fixed bugs …` subfolders — so the filter alone returns the wrong set. (On Motir's own project it
   returned 164 bugs, of which 9 were in `Bugs` itself.)
4. Order by key number, lowest first. **Empty ⇒ say there is nothing to fix, change nothing, and
   stop.**

`motir fix bugs <limit>` stops after `<limit>` bugs. Re-take the population before every bug rather
than keeping a list: the tree is the state, and another session may have moved a bug meanwhile.

**Status `todo` — not "not done" — is the population on purpose.** Every outcome below moves the bug
to Blocked, Done, Implemented or Planning, so none of them is offered again.

### 2. One bug at a time

For the first bug in the population:

1. Read it whole — `get_work_item` (both `descriptionMd` and `explanationMd`, its edges) and, when it
   has comments, `get_work_item_activity`.
2. **Establish what is actually wrong on the default branch**: reproduce it, or confirm the diagnosis
   in the code at the file and line it names. The bug's text is a claim.
3. Take the outcomes in section 3 **in order** and perform the FIRST one that applies — all of it.
4. `get_work_item` the bug again and **check it is no longer `todo`**. Still `todo` ⇒ the outcome is
   unfinished; finish it before anything else, or the next read hands you the same bug.
5. Go back to section 1. Never two bugs in flight, and do not stop to summarise while the population
   is not empty (unless `<limit>` is reached).

### 3. The three outcomes — tested IN THIS ORDER

**A. It WAITS ON ANOTHER CARD.** The fix needs the output of a card that is not Done — a column it
adds, a surface it builds, a decision it records. Read this strictly: working in the same area is not
waiting, and a hard bug is not a waiting bug. **A Done card never blocks**: a bug caused by finished
work is fixable (B or C).

1. `link_work_items { fromKey: <bug>, toKey: <that card>, relationship: "blocked_by" }`.
2. Re-home it: an edged bug lives in the story (the container one level above leaves) that holds the
   card it waits on. `get_work_item` that card, take its `parent`, read the parent's `status`, and
   `move_to_parent { key: <bug>, parentKey: <parent> }`. If the parent is Done or Cancelled, or the
   card has no parent, leave the bug in the folder — the edge is still wired. Never put a bug under a
   Done card: it re-opens it.
3. `transition_status { key: <bug>, status: "blocked" }`.
4. `add_comment` starting `FIX-BUGS: waits on <KEY>`, saying what the fix needs from that card.

**B. It is NOT FIXABLE HERE — for another reason.**

- **Already fixed** — it does not reproduce AND you can name what fixed it (a commit, a pull request,
  a `file:line`). `add_comment` starting `FIX-BUGS: already fixed` with that evidence and the check you
  ran, then `transition_status` to `in_progress` and then to `done` (To Do → Done is not one step).
  No evidence of a fix ⇒ it is the next case.
- **Cannot reproduce** — `add_comment` starting `FIX-BUGS: cannot reproduce` with exactly what you ran
  and at which commit, and what the reporter should supply; then `blocked`.
- **Needs a person's decision** — the fix forks on a behaviour, a product question or access you do
  not have. `add_comment` starting `FIX-BUGS: needs a decision` with the question, its options and
  your recommendation; then `blocked`.

A Blocked bug with no edge is a label for people, not a lock. A person who answers it moves it back
to To Do, and the next run picks it up.

**C. It is FIXABLE — run it like any card, ONE pull request for this bug alone.** If the
`motir-run` skill is installed, follow it for this bug's key. Otherwise:

1. `claim_work_item { key: <bug> }` — it assigns the bug to you and moves it to In Progress.
2. A fresh branch from the default branch (`git fetch origin && git worktree add ../<repo>-<KEY> -b
   fix/<KEY>-<slug> origin/<default>`), and work only there.
3. Reproduce it first — a failing test where the repository has tests — then fix it, and follow the
   repository's own `CLAUDE.md` / `AGENTS.md` and checks.
4. `git add` the paths you changed (never everything), commit, push, and open ONE pull request, ready
   for review, with the bug's key in the title. **Immediately** `link_pull_request { key: <bug>, url:
   <the PR>, headRef, baseRef }` — the link, not the title, is what lets the merge close the bug.
5. `transition_status { key: <bug>, status: "implemented" }` and `publish_test_instructions` onto the
   bug (how to check the fix, every command in its own fenced block).
6. Leave the merge to a person — the merge moves the bug to Done.

The next bug starts again from the default branch, on its own branch — never this one. A different
defect met while fixing is filed separately (the `motir-log-bug` skill), not fixed in this pull
request. If the fix turns out to need new cards or a design, do not re-plan here: `add_comment` what
it needs, `transition_status` it to `planning`, and name it in the report as needing a person.

### 4. Report

When the population is empty or `<limit>` is reached, report:

- how many bugs were taken, and how many per outcome — and how many To Do bugs remain if you stopped
  at a limit;
- each pull request, with the bug it fixes;
- each bug that now waits on a card: the card, and the story it was moved under;
- each bug that needs a person, with its question — first, because a reader acts on these;
- each bug closed as already fixed, with the evidence.

### Never

- Two bugs on one branch, or one pull request with two fixes.
- A bug from any folder inside `Bugs` (`Planning bugs`, `Fixed bugs …`) — only the folder's own.
- A `blocked_by` to a Done card, or "waiting" as a place to park a hard bug.
- Re-planning, merging, moving closed bugs into `Fixed bugs …` folders, or creating a folder.
