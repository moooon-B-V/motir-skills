---
name: motir-run
description: Run Motir work end to end — `motir next`, `motir run`, `motir run <key>`, or `motir run <parent-key>` for a story whose children are all leaves. Use when the user asks to run, execute, build, work or pick up the next ready Motir card. It closes out merged work, claims the card, records its run in Motir (harness, model, each step, how it ended), builds it on its own branch, opens ONE pull request linked to the card, moves the card to Implemented and publishes How to test. A card that is wrong goes to Motir's planner instead of being built; a defect outside the card goes to motir-log-bug.
---

# `motir run` / `motir next` — work one card, end to end

A run takes one card from **To Do** to an open, linked pull request and a card at **Implemented**, and
stops there: a person reviews and merges, and the merge moves the card to Done. It never builds a card
it believes is wrong, and it never folds an unrelated fix into the card's pull request.

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
`git show origin/main:<path>`. Never run a mutating `git` command in a checkout that is not yours; a run
works in its own worktree, and the worktree IS the claim on a card. Read, in order:

1. `prompts/_shared.md` — the foundation, and the table that settles which `motir run` you are.
2. `prompts/run.md` — the command file: the selection logic for all four spellings, the close-out
   sweep, the prompt structure, the worktree rules, commit authorship, the design-reference rules, the
   CI-went-red rule, the how-to-test rule and the artifact-obtainable pre-`done` check. **The
   close-out sweep runs FIRST**, before you pick anything up.
3. The target repository's own `CLAUDE.md` — the architecture contract the code has to satisfy.
4. The lesson store — `search_lessons` before you build, `reinforce_lesson` on a hit.

A card that is wrong is THE REPLAN ACTION through the `motir-plan` door, or — when that skill is not
in this session's skill list — `prompts/run.md`'s *WHEN THE `motir-plan` SKILL IS NOT AVAILABLE*.
A defect out of the card's scope goes through `motir-log-bug`.

**It printed `STANDALONE MODE`:** follow the procedure below.

## Standalone mode

> Condenses `prompts/run.md` § *The CLOSE-OUT SWEEP*, § *A RUN ASSIGNS THE CARD*, § *A RUNBOOK RUN PUTS
> ITSELF ON THE RUN RECORD*, § *Worktree rules*,
> § *PR titles drive the status sync*, § *Design-reference rule*, § *YOUR CI WENT RED*, § *The how-to-test
> rule*, § *A RECORDED DEVIATION … is a `bug` to FILE*, § *WHEN THE `motir-plan` SKILL IS NOT
> AVAILABLE*, § *`motir run`* and § *`motir run <parent>`*, and `prompts/_shared.md` § *Status tracks
> the PR lifecycle* — as of the hashes in [`SYNC.json`](SYNC.json).

Everything here goes through the **Motir MCP server** connected to your agent, plus `git` and the
GitHub CLI (`gh`). Tools are named exactly as the server names them (your client may prefix them, e.g.
`mcp__motir__claim_work_item`). If the Motir tools are not available at all, stop and tell the user how
to connect Motir: in Claude Code with the `motir` plugin installed, run `/mcp` and authenticate
`motir`; otherwise, connect the MCP as described at <https://motir.co/docs/mcp>. If a call fails with a
connection error, a 401 or a not-found, **stop and report** what you were about to do — never work
around a failed call, and never move a status by some other route.

**Never ask the user a question mid-run.** Resolve an unclear detail from the card, the repository and
its conventions, and build. If you conclude the *card itself* is wrong, that is step 8 — an action,
not a question.

### The status ladder — who moves what

| Moment | Status | Who writes it |
|---|---|---|
| The card is claimed | **In Progress** | `claim_work_item` (this run) |
| The run is opened, reported and closed | (no status) | `start_work_item_run` · `report_action` · `close_work_item_run` (this run) |
| The pull request is open and linked | **Implemented** | `transition_status` (this run) |
| CI on that pull request is green | **In Review** | Motir, from the CI result — **never this run** |
| The pull request merges | **Done** | Motir's status sync, because the pull request is LINKED |
| The card is wrong and a correction is submitted | **Planning** | `transition_status` (this run, step 8) |

### 1. Close out merged work first

Before picking anything up, look at the branches and worktrees earlier runs left in this checkout
(`git worktree list`, `git branch`):

- **Only a branch with commits of its own can be finished work.** `git log --oneline origin/<default>..<branch>`
  empty ⇒ it is someone's unstarted work: leave the branch, its worktree and its card alone.
- **The pull request decides** — `gh pr list --head <branch> --state all`. `MERGED` is finished;
  `OPEN`, `CLOSED` or none is not.
- **Motir closes the card itself** when a linked pull request merges. If a merged card is still not
  Done, read its latest comments (`get_work_item_activity { key, view: "comments" }`): Motir posts one
  when it holds a card on purpose (merged onto a non-default branch, a sibling pull request still
  open). **Report the hold; never override it by moving the status.**
- **Tear down only merged work, only yours.** `git worktree remove <path>` and `git branch -d <branch>`
  (`-d`, never `-D` — if it refuses, stop). A worktree with uncommitted changes is someone's live work:
  skip it silently and carry on. Leave remote branches alone.

### 2. Select the card

- **`motir run <key>` / `motir next <key>`** — that card. **`motir run` / `motir next`** with no key —
  `next_ready { projectKey }`, which returns the highest-ranked ready card (it does not claim it).
- **Read it** — `get_work_item { key }` — and stop, reporting why, when:
  - **`archivedAt` is set** — a person decided it should not be worked; report the archive comment.
  - **`readiness.ready` is false.** `openBlockers` not empty ⇒ name them and their statuses. Only an
    ancestor is blocked (`blockedByAncestor`) ⇒ name it; continue only if the user explicitly asked to
    override that ancestor's block, and say whose block you overrode.
  - **It is `manual`, or its executor is `human`** — an agent cannot do that work. Say so; the person
    closes it with `motir-mark` when it is done.
  - **It is an `epic`**, or a container whose children have children — not a run target. Name the
    stories (or child containers) to run instead.
- **A container whose children are all leaves** (a story, or a task / bug with children) is a
  **parent run** — step 9. Everything else is a single card, steps 3–7.

### 3. Claim it, then check the disk

- **`claim_work_item { key }`** — locks the card, assigns it to you and moves it to In Progress in one
  step. Do **not** also call `transition_status`. The answer is a result, not an error:
  `claimed` ⇒ yours · `mine` ⇒ you are resuming your own run · `taken` ⇒ someone else holds it, stop and
  name them · `not_claimable` ⇒ it is past To Do (or archived), stop.
- **On `claimed` or `mine`, open the run — `start_work_item_run { key, harness, model }`** — so the run
  shows in Motir's Runs page and on the card, like a run started from the Motir CLI. `harness` is your
  own name as your makers write it (`Claude Code`, `Codex`, …). `model` is the model id you run as —
  **omit it when you do not know it; never guess one**, because a delivered run records it as who built
  the card. Keep the `runId` it answers: the close needs it. `mine` answers the run you already have
  open on this card; carry on with it. (`motir next` only prints a prompt and opens no run.)
- **The worktree is the real claim.** `git worktree list` and look for a branch or directory already
  carrying the key. Uncommitted changes ⇒ a live session owns it: close your run `halted` (below) and
  report. Commits or an open
  pull request ⇒ someone has landed part of it: read the card's comments before assuming what is left.
  **Never reset, clean, stash or check out over a worktree you did not dirty.**

### 4. Read the spec

- **`dispatch_prompt { key }`** — the server-assembled prompt for this card: context, what to do,
  acceptance criteria and the git workflow. Follow it; do not rewrite it. Its `targetRepo` says which
  repository the card ships in.
- **`latestRefusal` on the card is not null** ⇒ a reviewer sent it back: its note is what this attempt
  must change, and your pull request says how it did.
- **A card that draws or changes a screen** builds against its approved design:
  `list_designs { projectKey, blockersOf: <key> }`, then `get_design` for the files. A verdict other than
  `approved`, or a design that does not show an element you must build ⇒ **do not improvise the UI** —
  the card is missing its design, which is step 8.
- The target repository's `CLAUDE.md` / `AGENTS.md` / contributing guide are its rules for the code.
- **`motir next` stops here**: print the prompt for the user to hand to their own agent, say the card
  is claimed and In Progress, and stop. `motir run` carries on.

### Report every step, and close the run on every exit

- **Before each step you take, `report_action { key, action }`** — the step in one line: *"read the
  export service"*, *"run the changed tests"*, *"open the pull request"*. At most 500 characters, and
  **never a transcript, a diff, file contents, a prompt or a secret**: it is stored and shown to
  everyone who can read the run.
- **Add `events` at the milestones**, on the card's key. The `disposition` is what moves the card on the
  run; without it the card reads *Not reached* once the run closes.

  | when | `events` entry |
  |---|---|
  | the worktree exists | `{ kind: "checkout_ready", sessionBranch: "<branch>", disposition: "running" }` |
  | the pull request is linked | `{ kind: "delivery_linked", data: { url: "<pull request url>" } }` |
  | the card reached Implemented | `{ kind: "card_settled", disposition: "implemented" }` |
  | the card was parked or the run stopped on it | `{ kind: "card_settled", disposition: "failed" }` |

- **Staying alive needs nothing extra.** Every Motir tool call keeps your run alive; a run Motir has not
  heard from for an hour is closed for you. (In Claude Code the `motir` plugin also heartbeats it after
  every tool use.)
- **`close_work_item_run { key, runId, outcome }` on EVERY exit**, on the key you opened it on:

  | how the run ends | `outcome` |
  |---|---|
  | the card is Implemented and its pull request linked (step 6), or a parent's pull request is ready (step 9) | `completed` |
  | a parent run ran out of ready children before its last one | `drained` |
  | the card is wrong and its correction is submitted (step 8) | `replanned` |
  | a stop you could not get past — a refusal, a live worktree, a failed call | `halted` |
  | the person stopped you | `interrupted` |

  A `completed` or `drained` close records your harness and model as the card's implementer; nothing
  else does. The close changes no card's status.

### 5. Build — its own worktree, one repository, ONE pull request

```sh
git fetch origin
git worktree add ../<repo>-<KEY> -b <KEY>-<short-slug> origin/<default-branch>
```

- **One card = one repository = one branch = one pull request.** A card whose acceptance criteria
  genuinely need changes in two repositories it does not name is a wrong card (step 8), not a choice
  you make.
- **A `type: decision` card is the one exception: it ships a PAGE, not a branch.** Write ONE page in the
  card's project (`create_page` / `update_page`), and when it is complete call
  **`publish_decision_page { key, pageId }` once**. That seals the version and raises the card's
  `decision_approval` gate about exactly it. No worktree, no commit, no pull request, no link, and no
  status write: a person's Approve freezes the version and moves the card to Done. Do not edit the page
  after publishing (an edit is a new version, and a second publish replaces the question). Report it as
  **published and awaiting approval**, with the page id and version.
- Do all the work in that worktree. Stage specific paths (`git add <path>`, never `-A`).
- Run the repository's checks — lint, type-check, build — and **only the tests you added or changed**.
  The pull request's CI runs the whole suite; a full local run is a slower copy of a measurement that is
  already queued.
- **A defect you find that is not this card's** — file it with **`motir-log-bug`**, and do not fix it
  here. A sentence in a pull request or a card body describing work someone must still do is not a
  record anyone will find: if it will still be true after this card is Done, it is a bug card, filed
  in the same moment, and the sentence cites its key.

### 6. Hand it back — in this order

1. **Push and open the pull request**, ready for review (not a draft), against the default branch, with
   the card's key in the title as a label — e.g. `ACME-12 Add the export button`. Pass every label in
   the `gh pr create` call itself; adding one afterwards re-triggers CI. Include a **How to test**
   section in the body.
2. **`link_pull_request { key, url, headRef, baseRef }`** — IMMEDIATELY. The link, not the title, is
   what lets the merge close the card: an unlinked pull request moves nothing, however it is named.
3. **`publish_test_instructions { key, bodyMd, repos: [{ repo, commitSha }] }`** — the same How to
   test: the precondition (sign-in, role, data), the local setup (install, migrate, seed, run — each
   command in its own fenced block), and, when the card changes something a person can see, the
   click-path with what they should see. No rendered surface ⇒ say why there is no click-path.
4. **`transition_status { key, status: "implemented" }`.** Never `in_review` — CI writes that.
5. **Close the run:** `report_action` with the `delivery_linked` and `card_settled` (`implemented`)
   events, then **`close_work_item_run { key, runId, outcome: "completed" }`** — the close that records
   who built the card.

Then **stop**: do not merge, do not delete the branch or worktree. The next run's step 1 tears it down
after the merge.

### 7. CI went red

1. **Merge the pull request's base branch into yours first** (`git fetch origin && git merge
   origin/<base>`) — CI judged your branch merged with its base, so until you merge you are not looking
   at the tree it failed. Often the failure was inherited, and the merge alone fixes it.
2. Fix what the log **named**. Run at most that one test file locally.
3. **Push.** The new CI run is the verification — do not re-run the suite locally to confirm it.
4. If the fix changed a step in How to test, publish it again (`publish_test_instructions`, the whole
   corrected body) and update the pull request's section to match.

### 8. The card is wrong — hand the correction to Motir's planner, and stop

A card is wrong when it cannot be built as written: mis-scoped, premised on something that does not
exist (check the code first — a hunch is not evidence), missing its design, straddling two
repositories, or contradicting itself. **Do not build it, do not quietly narrow it, and do not create
the missing cards yourself** — a run creates no work item except a bug. Hand the WHAT to Motir's
planner, in this order, each step once:

1. **`transition_status { key, status: "planning" }`** — the first write. **Never `blocked`:** no
   dependency edge exists until a person approves the correction, so a Blocked card still looks ready
   and another run would claim it. Planning keeps it out of every claim. (In a parent run, this is the
   wrong CHILD, never the parent.)
2. **`append_plan_turn { projectKey, targetKeys: [<key>], body }`** — ONE turn, one paragraph: what
   the card says, the evidence it cannot be built as written (paths, commits on the default branch),
   and the correction you would make. Keep the `id` it returns.
3. **`submit_plan_session { projectKey, targetKeys: [<key>], sessionId, requirement }`** — anchored on
   the card, **submitted ONCE** (it spends the project owner's AI credits). `requirement` is six fields,
   written from your own diagnosis — nobody will come back to ask you:
   - **`outcome`** — who the corrected card serves and what becomes possible once it is built right.
   - **`behaviour`** — the observable rules of the corrected shape, input → result, including the
     states that are not the happy path and any new edge (*the card waits on the new prerequisite*).
   - **`scopeEdge`** — what the correction must not touch: siblings, the parts already right. `""`
     means you considered it and there is none.
   - **`constraints`** — what already binds it: the card's repository and parent, its edges, its
     design, the repository's rules, your evidence. `""` only if truly nothing.
   - **`acceptance`** — how a reviewer of the resulting plan will know it is right, as an observation
     (*"a design card sits beside ACME-12 and ACME-12 waits on it"*).
   - **`assumptions`** — what you concluded that nobody confirmed.

   `outcome`, `behaviour` and `acceptance` must be non-empty, or the planner opens a conversation
   instead of planning. *"See my comment"* is not a WHAT. If the tool rejects the arguments, nothing
   happened: submit once more without `requirement`.
4. **`get_plan_status { planId }`** a few times, until it leaves `generating` or reports FAILED. Still
   generating when you stop is a fine answer — report it. Approval is a person's, in Motir; never yours.
5. **`add_comment` on the card** — the step-2 paragraph, the `planId`, and the status you last read.
6. **Close the run `replanned`** (`close_work_item_run`), then **stop and report**: the card parked at
   Planning, the `planId`, its status, and that a plan waits for review. Build nothing.

**A refusal is a stop, too** — and the thread is kept, so a person can submit it later:

| Refusal | Means | Do |
|---|---|---|
| `PERMISSION_DENIED` | the token cannot run AI planning (`ai:plan`) | do not retry |
| `MOTIR_AI_OUT_OF_CREDITS` | the owner's AI credits are spent | do not retry |
| `MOTIR_AI_UNAVAILABLE` | the planner could not be reached | retry the submit ONCE, then stop |
| `RATE_LIMITED` | the shared planning budget is spent | stop; do not wait it out |

Every refusal ends the same way: the card stays at Planning, an `add_comment` carries the whole
correction — the paragraph and all six fields — plus the refusal code, the run closes `halted`, and you
report that you stopped and why. Never write the plan or the missing cards yourself as a fallback.

### 9. A parent run — a story whose children are all leaves

- **Claim the parent** (`claim_work_item`), then check `validate_work_item { key }`: a child waiting
  on a card **outside** the story is skipped and named, with everything that waits on it.
- **ONE run, on the PARENT's key.** `start_work_item_run` on a parent needs you to hold every child that
  is not Done, so `claim_work_item` each of them first, then open the run with the parent's key. A
  `not_claimed` answer names the child you do not hold (`offenderKey`): claim it, then open again.
  `report_action` names the CHILD you are working as its `key`, with `checkout_ready` as you start a
  child and `card_settled` (`implemented`) as its commit lands.
- **One branch per repository the children ship in**, named for the parent —
  `git worktree add ../<repo>-<PARENT-KEY> -b <PARENT-KEY>-<slug> origin/<default-branch>`. **Re-running
  resumes:** reuse the branch, merge the default branch into it, and skip every child already committed.
- **Order the children by their `blocked_by` edges.** For each ready child: `claim_work_item` it, read
  its `dispatch_prompt`, build it in the parent's worktree, run the checks, and land **ONE commit** whose
  message names the child's key and title. Then `transition_status` the child → `implemented`. No pull
  request per child.
- **A `decision` child gets no commit either**: it publishes its page as step 5 says, and its
  dependents wait until a person approves it.
- **At the FIRST commit in a repository**, push and open that repository's pull request **as a DRAFT**
  (`gh pr create --draft`), its title carrying the PARENT's key, and **`link_pull_request` it to the
  PARENT** in the same step. A draft cannot merge — which matters, because merging a parent's pull
  request moves the parent to Done and **closes every child under it**, built or not.
- **A child that cannot be committed stops only its own chain**: a `manual` child (the person does it),
  a design the user has not approved yet, or a wrong child (step 8, anchored at that child). Run every
  other ready child.
- **At the LAST child in a repository**: read the parent's children again (`get_work_item`) — any child
  not yet Implemented, including one filed during this run, is run, moved out of the story, or reported
  and the draft left as it is. Then `publish_test_instructions` on the **PARENT**, rewrite the pull
  request body to list every child commit, mark it ready (`gh pr ready`), `transition_status` the
  parent → `implemented`, and close the run `completed`.
- **Stopped before the last child?** Leave the pull request a draft and the parent In Progress, publish
  no How to test, close the run — `drained` when no child was left ready, `halted` when something
  stopped you — and say so in the report.

### 10. Report

What was built, the pull request (and whether it is a draft or ready), the card's status as you read it
back, how the run closed, any bug you filed, any card you parked at Planning with its `planId`, and what is ready next.
