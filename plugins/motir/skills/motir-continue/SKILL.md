---
name: motir-continue
description: Carry on ONE Motir card whose run DIED — `motir continue <KEY>`. Use when the user asks to continue, resume or pick up a card whose run was lost, killed, timed out or stopped (a laptop closed, a sandbox lost), on the branch that run left. It claims the continue so nobody else works the same branch, checks out the dead run's OWN branch in every repository the card spans (never a new one, never resetting a worktree), reads the CONTINUE prompt, keeps the continue alive while it works, delivers exactly as `motir run` does — push, one pull request per repository, Implemented, How to test, and the acceptance receipt published by CI where the repository's lane does it, over MCP otherwise — and closes the continue with how it ended. NOT for a card whose pull request is open and red (that is `motir-fix`), not for a card that has not started (`motir-run`), and not for the Bugs folder (`motir-fix-bugs`).
---

# `motir continue <KEY>` — carry on a dead run's work on the branch it left

A card's run died part-way: the laptop closed, the sandbox was lost, the process was killed. The card
is still In Progress and its work is on a branch. This skill hands that card to you as ONE locked
continue: you check out the branch the dead run left, carry the work on, and deliver it the way a fresh
run would. Nothing is started over.

**It is not the other commands, and the claim says so.** A card whose pull request is open (red or not)
is `motir fix <KEY>` (the `motir-fix` skill). A card that has not started is `motir run <KEY>` (the
`motir-run` skill). A card that was one leg of a parent run is continued at the parent:
`motir continue <PARENT>`.

## Runbook mode

Motir's own team keeps its full procedure in a private runbook checkout (`motir-meta`). Look for it
first; you almost certainly do not have it, and then this section ends with **Standalone mode**.

```sh
# Where the runbook is, if anywhere: $MOTIR_META, else a motir-meta checkout at or above the working
# directory (the checkout itself, or one beside an ancestor).
[ -z "${MOTIR_META:-}" ] || [ -f "$MOTIR_META/prompts/_shared.md" ] || \
  { echo "MOTIR_META=$MOTIR_META holds no prompts/_shared.md — fix it, do not fall through"; exit 1; }
META="${MOTIR_META:-}" d="$(pwd)"
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
  echo "STANDALONE MODE — no runbook at or above $(pwd)"
fi
```

**It printed `RUNBOOK MODE`:** the runbook is the rules of record, and everything below the next
heading is IGNORED — it is a condensation for people who do not have the runbook, never a second
source. `origin/main` is authoritative, not `HEAD`: when the two hashes differ, read each file with
`git show origin/main:<path>`. Read, in order:

1. `prompts/_shared.md` — the MCP mechanics and the status ladder.
2. `prompts/continue.md` — the protocol in full: what it is for, the claim and every refusal, the
   checkout on the dead run's own branches, the CONTINUE prompt, liveness, delivery and who publishes
   the acceptance receipt, a parent continue, the close on every exit, the report and the never-list.
3. `prompts/run.md` and `prompts/fix.md` — the delivery rules and the checkout rules `continue.md`
   cites, where it points at them.

**It printed `STANDALONE MODE`:** follow the procedure below.

## Standalone mode

> Condenses `prompts/continue.md` § *WHAT IT IS FOR*, § *THE CLAIM*, § *THE CHECKOUT*, § *THE PROMPT*,
> § *LIVENESS*, § *DELIVERY*, § *A PARENT CONTINUE*, § *THE CLOSE*, § *THE REPORT* and § *WHAT THIS
> PROTOCOL NEVER DOES*, as of the hashes in [`SYNC.json`](SYNC.json).

Everything here goes through the **Motir MCP server** connected to your agent, plus `git` and the
GitHub CLI (`gh`). Tools are named exactly as the server names them (your client may prefix them, e.g.
`mcp__motir__claim_work_item_continue`). If the Motir tools are not available at all, stop and tell the
user how to connect Motir: in Claude Code with the `motir` plugin installed, run `/mcp` and
authenticate `motir`; otherwise, connect the MCP as described at <https://motir.co/docs/mcp>. If a call
fails with a connection error, a 401 or a not-found, **stop and report** what you were about to do to
which card — never work around a failed call.

The tools:

| tool | what it does |
|---|---|
| `claim_work_item_continue { key }` | takes the continue lock and hands you `runId`, `deadRun` (its `id`, who ran it, when it was last heard from), `mode` (`card` or `parent`) and `branches` — each `{ repository, branch, pullRequest }`, primary first — plus, for a parent, `landedKeys` and `resumedKeys` |
| `dispatch_prompt { key, continueFrom }` | the CONTINUE prompt, with `continueFrom` = `deadRun.id` |
| `touch_work_item_continue { key, runId }` | keeps the continue alive; `open: false` means it was closed under you |
| `close_work_item_continue { key, runId, outcome }` | ends it — see step 7. Safe to repeat |

**The claim writes no status.** The card stays In Progress; the one change is that it is re-assigned
to you. A continue **silent for five minutes is dead** — the card reads *run died* again and someone
else may claim it — which is why step 5 exists.

**A run that closed `gated` is continued too**, once a gate that held it is approved, chosen, confirmed
or marked done: it reads *Ready to resume* on the Workbench's **To resume**, and the claim takes it on
that run's own branch. While every holding gate still awaits, there is nothing to resume yet.

### 1. Claim the continue — and refuse in words

`claim_work_item_continue { key }`, before any checkout. Keep `runId` and `deadRun.id`. A refusal
changes nothing on the card and opens nothing to close — say it, end with *Nothing was changed*, and
stop:

- `claimed` — yours: say whose work you took over (`previousAssignee`, the dead run's dispatcher and
  when it was last heard from) and name each repository's branch, then step 2.
- `mine` — you already hold it: a **resume**, same `runId`. Step 2, reusing what is there.
- `taken` — *already being continued by `<holder.name>` since `<startedAt>` — not starting a second
  agent; two agents on one branch undo each other.*
- `not_continuable`, by `reason`:
  - `run_alive` — its run is still alive (`<holder.name>`'s): wait for it to finish, or, if it has
    really stopped, try again in a few minutes, once Motir has stopped hearing from it.
  - `use_fix` — its pull request is already open, so there is nothing to continue: its checks decide
    from here; if they go red, run `motir fix <KEY>`.
  - `not_in_progress` — it is not In Progress: to start it, run `motir run <KEY>`.
  - `continue_the_parent` — it was run as part of `<parentKey>`, so it is continued from there: run
    `motir continue <parentKey>`.
  - `no_dead_run` — no run of it has died, so there is nothing to continue.
  - `no_branch` — the run that died left no branch to continue on: start over instead — set it to
    To Do and run `motir run <KEY>`.

`mode: parent` means the dead run was a scoped run over this container: follow step 6b instead of
steps 3 and 6a. **From here on the continue is open, and every exit ends in step 7.**

### 2. Check out the dead run's OWN branch, in every repository

One worktree per entry in `branches`, **on that entry's `branch`** — never a new branch, never detached,
so every commit lands on the line of work the dead run started. The worktree path is the one the
CONTINUE prompt names: **`../<repo>-<key lower-cased>`** beside the repository's clone.

1. Find the local clone of the entry's `repository` (null ⇒ the card's primary repository). None ⇒
   clone it beside the others; a clone that fails is a stop.
2. `git fetch origin +refs/heads/<branch>:refs/remotes/origin/<branch>`.
3. The worktree:
   - already there **on `<branch>`** ⇒ **reuse it as found, dirty or clean** — the claim proved its run
     dead, so any uncommitted work in it is the dead run's, and it is kept;
   - already there on anything else ⇒ a stop: the path is in the way, and say which branch it is on;
   - not there ⇒ `git worktree add <path> <branch>` if a local branch of that name exists, else
     `git worktree add --track -b <branch> <path> origin/<branch>`.
4. A repository of the card the dead run never pushed to (not in `branches`) gets the card's fresh work
   branch, cut from `origin/HEAD` as `motir run` would start it.
5. Confirm every worktree is on its branch.

**A stop ⇒ step 7 with `halted`**, then say which repository and what the person should do. **Never
reset, remove, clean, stash or re-point a worktree.**

### 3. Read the CONTINUE prompt and do what it says

`dispatch_prompt { key, continueFrom: <deadRun.id> }` returns the card's prompt with a **CONTINUE**
block — whose run it was, how it ended, where the work is — and a git workflow that checks that branch
out. Follow it; do not rewrite it. In particular:

- read `git log origin/main..HEAD` and `git status` in every worktree **before** changing anything;
- keep what is right — do not start over and do not redo finished work;
- `git merge origin/main` into the branch, and resolve any conflict;
- no new branch anywhere, and no second pull request — reuse the open one (`gh pr list --head <branch>`).

A refusal `CONTINUE_FROM_INVALID` ⇒ step 7 with `halted`. A card that turns out to be wrong is not
improvised around: hand it to Motir's planner as the `motir-run` skill does (*the card is wrong*) and
close with `replanned`. A defect outside the card is filed with the `motir-log-bug` skill.

### 4. Build

Finish the work in those worktrees. Stage specific paths (`git add <path>`, never `-A`), run the
repository's checks and only the tests you added or changed, and commit with the card's key in the
message.

### 5. Keep it alive

`touch_work_item_continue { key, runId }` **at least every two minutes** from the claim to the close.
`open: true` ⇒ carry on. **`open: false`** ⇒ the lock is gone: **push nothing more**, do not close (it is
already closed — the answer says how), and report what is committed but unpushed and where. The person
claims again if the work should go on.

### 6a. Deliver — exactly as a fresh run does

1. **Push** each branch before anything says the work is built.
2. **ONE pull request per repository, only where none is open** — ready for review, against the
   default branch, the card's key in the title as a label, with a **How to test** section.
3. **`link_pull_request { key, url, headRef, baseRef }`** per repository, in the same step — the link,
   not the title, is what lets the merge close the card. A pull request the dead run opened is usually
   linked already; linking again is harmless.
4. **`publish_test_instructions { key, bodyMd, repos }`** — the same How to test: the precondition, the
   local setup (each command in its own fenced block) and, where something visible changed, the
   click-path.
5. **`transition_status { key, status: "implemented" }`** — never `in_review`; CI writes that.

**On a card that records a story's acceptance video**, first find out WHO publishes the receipt. In the
checkout that holds the acceptance spec, run:

```
grep -rlE 'uses:\s*\./\.github/actions/upload-acceptance-video' .github/workflows/
```

- **It prints a file** ⇒ that repository's acceptance lane publishes the receipt itself, from a green
  pull-request run, over keyless OIDC. **Publish nothing** — no `create_acceptance_upload`, no
  `publish_acceptance_result`. Confirm the spec declares its story with `acceptanceStory()`, push, and
  report that the lane publishes the receipt on a green run and no MCP publish was made.
- **It prints nothing** ⇒ no lane publishes there, and you do: record the spec green, then
  `create_acceptance_upload { key }` mints an upload URL, PUT the clip to it (`Content-Type:
  video/webm`), and `publish_acceptance_result` with the pathname it returned, the chapters, the pushed
  commit sha and the card key as `producedByKey`. **Nothing else makes that call** — report the receipt
  id it returns.

A red spec publishes nothing, in either branch.

### 6b. A parent continue (`mode: parent`)

The dead run was a scoped run over this container, so the whole scope resumes — on its session branch in
each repository (`branches`, checked out as step 2 says, with `origin/main` merged in first), through
the pull request it already opened, never a second one. **Never run a key in `landedKeys` again** — it
landed before the run died. **Run every key in `resumedKeys`** — it was in flight, the claim re-assigned
it to you, and it stays In Progress. Then run the remaining ready children of the container, one commit
each, as the `motir-run` skill's parent run does. Keep touching (step 5) throughout.

### 7. Close it — on every exit

`close_work_item_continue { key, runId, outcome }`:

| how it ended | `outcome` |
|---|---|
| delivered — pushed, the pull request open and linked, the card Implemented | `completed` |
| a parent continue ran out of ready children | `drained` |
| a parent continue stopped at a card limit the person set | `max` |
| a checkout stop, an invalid `continueFrom`, a step you could not get past, an error | `halted` |
| the card turned out wrong and went to Motir's planner | `replanned` |
| it stopped at an approval gate again (a design, decision, choice or manual card awaiting its press) — never `halted` | `gated` |
| the person stopped you, or the session is ending first | `interrupted` |
| you are giving the work up for somebody to start over | `abandoned` |

**No exit skips it** — an error or a failed tool call included; if the close itself times out, call it
again. A continue left open reads *being continued* for five more minutes and refuses every other agent
as `taken`. The only exit without a close is step 5's `open: false`, where it is already closed. **The
close writes no status** — step 6a's `transition_status` does, and CI moves the card on from there.

### 8. Report

The card, whose run you took over (who ran it, when it was last heard from) and the outcome you closed
with; each repository's branch, worktree path and pull request (yours, or the dead run's reused); for a
parent, the children landed now and those already landed; the card's status as you read it back; on an
acceptance-recording card, the receipt and WHO publishes it — CI (no MCP publish made) or your MCP
publish with its receipt id — or why there is none; and what the person does next — nothing (CI moves
the card; a red pull request is `motir fix <KEY>`), or the stop's own remedy.

### Never

- Start the card over — a new branch where the dead run left one, or a second pull request where one is
  open.
- Reset, remove, clean, stash or re-point a worktree — the dead run's is reused as found.
- Start a second agent over a `taken` continue, or push after a touch answered `open: false`.
- Continue a card whose run is alive, whose pull request is open (`motir fix`), that never started
  (`motir run`), or that is a leg of a parent run (`motir continue <PARENT>`).
- Leave a claimed continue open.
- Publish an acceptance receipt over MCP where the repository's lane carries the uploader, or report a
  receipt you did not publish — one CI published is reported as CI's.
- Set `in_review`, merge, or delete a branch.
