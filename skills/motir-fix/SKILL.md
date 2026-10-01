---
name: motir-fix
description: Repair ONE Motir card's red pull requests after the run that opened them has ended — `motir fix <KEY>`. Use when the user asks to fix, repair or rescue a card's failing, red or conflicting pull request, one the merge queue threw out, or a story whose acceptance video came back with Re-run. It claims the repair so nobody else pushes over it, checks out each pull request's OWN branch (never a new one), keeps the repair alive while it works, merges the base and fixes what the failing check named — up to five attempts — re-records the acceptance video once CI is green on a re-run, and closes the repair with how it ended. It never moves the card's status, opens a pull request or merges. NOT for `motir fix bugs` (clearing the Bugs folder — that is the `motir-fix-bugs` skill) and not for building a card (`motir-run`).
---

# `motir fix <KEY>` — repair a card's red pull requests on their own branches

A card's run opened its pull requests and ended; then CI went red, the merge queue threw one out, or a
reviewer sent the story's acceptance video back with **Re-run**. This skill hands that card's pull
requests to you as ONE locked repair: you fix them on the branches they already have, and CI — not you
— moves the card on once they are green.

**Three commands start with `motir fix`, and only one is this skill.** `motir fix <KEY>` (one card's red
pull requests) is this. `motir fix bugs` is the `motir-fix-bugs` skill (the Bugs folder). `motir fix
planning bug` is not a public skill. A run whose session is still open fixes its own red CI where it
stands (`motir-run`, *CI went red*) — it does not claim a repair of its own card.

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
2. `prompts/fix.md` — the protocol in full: what it is for, the claim and every refusal, the checkout on
   each pull request's own branch, liveness, the fix, an acceptance re-run, the close on every exit,
   the report and the never-list.
3. `prompts/run.md` — § *YOUR CI WENT RED* (the fixing loop `fix.md` cites), and the worktree,
   commit-authorship, how-to-test and re-assert rules it points at.

**It printed `STANDALONE MODE`:** follow the procedure below.

## Standalone mode

> Condenses `prompts/fix.md` § *WHAT IT IS FOR*, § *THE CLAIM*, § *THE CHECKOUT*, § *LIVENESS*,
> § *THE FIX*, § *AN ACCEPTANCE RE-RUN*, § *THE CLOSE*, § *THE REPORT* and § *WHAT THIS PROTOCOL NEVER
> DOES*, as of the hashes in [`SYNC.json`](SYNC.json).

Everything here goes through the **Motir MCP server** connected to your agent, plus `git` and the
GitHub CLI (`gh`). Tools are named exactly as the server names them (your client may prefix them, e.g.
`mcp__motir__claim_work_item_repair`). If the Motir tools are not available at all, stop and tell the
user how to connect Motir: in Claude Code with the `motir` plugin installed, run `/mcp` and
authenticate `motir`; otherwise, connect the MCP as described at <https://motir.co/docs/mcp>. If a call
fails with a connection error, a 401 or a not-found, **stop and report** what you were about to do to
which card — never work around a failed call.

The three repair tools:

| tool | what it does |
|---|---|
| `claim_work_item_repair { key }` | takes the repair lock and hands you `runId`, `repairClass`, `acceptanceRefusal` and the `pullRequests` — each `{ repo, number, url, headRef, baseRef, ci, failingChecks, queueExit }` |
| `touch_work_item_repair { key, runId }` | keeps the repair alive; `open: false` means it was closed under you |
| `close_work_item_repair { key, runId, outcome }` | ends it — `outcome` is `green`, `gave_up`, `halted` or `interrupted`. Safe to repeat |

**The repair writes no status and no assignee.** The card reads *being fixed* by you while the repair
is open, and green checks move it on by themselves. A repair **silent for five minutes is dead** — the
card stops reading *being fixed* and someone else may claim it — which is why step 3 exists.

### 1. Claim the repair — and refuse in words

`claim_work_item_repair { key }`, before any checkout. Keep `runId`. A refusal changes nothing on the
card and opens nothing to close — say it, end with *Nothing was changed*, and stop:

- `claimed` — yours: name each pull request and its failing check, then step 2.
- `mine` — you already hold it: a **resume**, same `runId`. Step 2, reusing what is there.
- `taken` — *already being fixed by `<holder.name>` since `<startedAt>` — not starting a second
  repair; two agents pushing to one pull request undo each other.* Push nothing.
- `not_repairable`, by `reason`:
  - `not_implemented` — it is not waiting on a repair: this picks up a card whose run has ended and
    whose pull requests went red afterwards, or that the merge queue threw out.
  - `repair_on_run_target` — its pull requests belong to the run on `<runTargetKey>`: run `motir fix
    <runTargetKey>` instead.
  - `no_pull_requests` — it has no pull requests, so there is nothing to repair.
  - `ci_running` — its checks are still running and nothing has failed yet: wait for the verdict, and
    run this again if it goes red.
  - `not_failing` — nothing is failing on its open pull requests, so there is nothing to repair.
  - `repair_not_code` — its merge did not land for a reason no code change fixes (a repository setting
    blocked it, or somebody took it out of the queue): approve it again in Motir, or change the setting
    the card names.

**From here on the repair is open, and every exit ends in step 6.**

### 2. Check out each pull request's OWN branch

One worktree per pull request, **on its `headRef`** — never detached, never a new branch — so every
push updates the pull request that is already open:

1. Find the local clone of the pull request's `repo`. None ⇒ a stop: say which repository to clone.
2. `git fetch origin +refs/heads/<headRef>:refs/remotes/origin/<headRef>`.
3. The worktree goes beside the clone at `<repo>-fix-<key>-<number>`:
   - already there **on `<headRef>`** ⇒ reuse it;
   - already there on anything else ⇒ a stop: the path is in the way;
   - not there ⇒ `git worktree add <path> <headRef>` if a local branch of that name exists, else
     `git worktree add --track -b <headRef> <path> origin/<headRef>`.
4. `git merge --ff-only origin/<headRef>` — a local branch that has diverged holds work nobody pushed:
   a stop, never a merge.
5. Confirm the worktree is on `<headRef>`.

**A stop ⇒ step 6 with `halted`**, then say which pull request and what the person should do. **Never
reset, remove, clean, stash or re-point a worktree you did not just make.**

### 3. Keep it alive

`touch_work_item_repair { key, runId }` **at least every two minutes** from the claim to the close —
between fixing steps and on every CI poll. `open: true` ⇒ carry on. **`open: false`** ⇒ the lock is
gone: **push nothing more**, do not close (it is already closed — the answer says how), and report what
is committed but unpushed and where. The person claims again if the work should continue.

### 4. Fix it — five attempts at most

For each pull request, in its worktree:

1. **Merge the base first** — `git fetch origin && git merge origin/<baseRef>`, a merge, never a
   rebase. CI judged your branch merged with its base; until you merge, the log describes a tree you do
   not have. A red that came from the base often goes green on the merge alone, and a **conflict** is
   yours to resolve — that is also what a merge-queue exit for a conflict needs.
2. **Fix what the failing check NAMED** — `failingChecks`, or the queue's check when `queueExit` is set
   (its own checks are usually green). Read that check's log (`gh pr checks <number> --repo <repo>`,
   then `gh run view <run-id> --log-failed`) and change what it points at, nothing wider.
3. **Run only what you touched** — lint, typecheck and the test files you changed. Never the whole
   suite locally: the push re-runs CI, and that is the verdict.
4. **Commit and push to the same branch.** No new branch, no new pull request.
5. **Watch** — `gh pr checks <number> --repo <repo> --watch`, touching the repair (step 3) while it
   runs. **Green** everywhere ⇒ step 6 with `green` (or step 5's last turn first). **Still running** ⇒
   keep waiting; waiting never counts as an attempt. **Red** ⇒ the next attempt.

**Five fixing attempts is the cap** — the same as the `motir fix` CLI. A sixth red ⇒ step 6 with
`gave_up`. **An attempt that pushed nothing** (the queue still names the same head) ⇒ step 6 with
`halted`: repeating it only spends attempts. **A failure you cannot fix** — not in the diff, needs a
decision, the card itself is wrong — ⇒ step 6 with `halted`, and say what you found.

### 5. An acceptance re-run

When the claim answered **`repairClass: acceptance_rerun`**, the checks are usually green and the
problem is what a reviewer saw in the acceptance video; `acceptanceRefusal` carries their reason.

1. **Before step 4, once:** on the same branches, merge each base, find where the complaint lives by
   RUNNING or rendering the surface they watched, change the smallest thing that answers it, keep the
   tests true, and push. **Anything structural is a Re-plan, not a Re-run** — a new screen, a
   different flow, another card's work: make no commit, go to step 6 with `halted`, and say the
   reviewer should re-plan the story in Motir. **Do not record the video yet.** If the steps a person
   follows to test it changed, publish them again with `publish_test_instructions` on the story.
2. **Step 4**, unchanged.
3. **Only once CI is green:** run the story's acceptance spec with recording on, then publish it —
   `create_acceptance_upload { key }` mints an upload URL, PUT the clip to it (`Content-Type:
   video/webm`), then `publish_acceptance_result` with the pathname it returned, the chapters, the
   commit sha you pushed and the card key. **The receipt id it returns is the only proof it
   published** — report it. A red spec publishes nothing. If this turn fails ⇒ step 6 with `halted`,
   saying CI is green but the video was not re-recorded.

### 6. Close it — on every exit

`close_work_item_repair { key, runId, outcome }`:

| how it ended | `outcome` |
|---|---|
| every pull request green (and, on a re-run, the video published) | `green` |
| the five attempts are spent | `gave_up` |
| a checkout stop, a failure you could not fix, an attempt that pushed nothing, a structural re-run, a failed recording, an error | `halted` |
| the person stopped you, or the session is ending first | `interrupted` |

**No exit skips it** — an error or a failed tool call included; if the close itself times out, call it
again. A repair left open reads *being fixed* for five more minutes and refuses every other fixer. The
only exit without a close is step 3's `open: false`, where it is already closed.

**And the close is your only write to the card:** no `transition_status`, no link, no merge.

### 7. Report

The card and the outcome you closed with; each pull request (`repo#number`), its branch and final CI
state — naming the checks still failing on `gave_up` or `halted`; the attempts used out of five; on a
re-run, the acceptance receipt id (or why there is none); and what the person does next — nothing on
green (CI moves the card), or look at the named failure and run `motir fix <KEY>` again.

### Never

- A new branch or a new pull request — every push goes to a pull request's own `headRef`.
- A status or assignee change, a pull-request link, or a merge.
- A second repair over a `taken` one, or a push after a touch answered `open: false`.
- A reset, removal, clean, stash or re-point of a worktree you did not create.
- A claimed repair left open.
- An acceptance video recorded before CI is green, or reported without a receipt id.
- Answering `motir fix bugs` — that is the `motir-fix-bugs` skill.
