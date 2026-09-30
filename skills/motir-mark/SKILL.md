---
name: motir-mark
description: Close a Motir work item that has no pull request — `motir mark <key> done`. Use when the user says a manual card (dashboard, secret, account or other human work) is finished, or types `motir mark` out of habit. It walks the card's status up to Done and records who confirmed it. A card that has a pull request is NOT closed here — its merge closes it — so the skill explains that instead of flipping it.
---

# `motir mark <key> done` — close a card no pull request can close

Motir moves a card to **Done** by itself when the pull request linked to it merges. The only card
that never gets that signal is one whose work happens outside a repository — a `manual` card, or one
whose executor is a human: creating an account, setting a secret, flipping a setting. For that card
the person saying *"it's done"* is the signal, and this skill turns it into the status change.

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
`git show origin/main:<path>`. The command is **DEPRECATED** there: a merged pull request is the
close-out signal, and everything else it did runs as the close-out sweep at the head of every
`motir run`. Do not refuse it — run the sweep scoped to that item. Read, in order:

1. `prompts/_shared.md` — the MCP mechanics and the status → pull-request lifecycle.
2. `prompts/run.md` — the CLOSE-OUT SWEEP, which is what actually runs now.
3. `prompts/mark.md` — the reference semantics, and the one surviving explicit use: a
   `type: manual` subtask, which has no pull request for the status sync to see.

**It printed `STANDALONE MODE`:** follow the procedure below.

## Standalone mode

> Condenses `prompts/mark.md` (the whole file) and `prompts/run.md` § *The CLOSE-OUT SWEEP*, as of
> the hashes in [`SYNC.json`](SYNC.json).

Everything here goes through the **Motir MCP server** connected to your agent — the tools are named
below exactly as the server names them (your client may prefix them, e.g. `mcp__motir__get_work_item`).
If the Motir tools are not available at all, stop and tell the user how to connect Motir: in Claude
Code with the `motir` plugin installed, run `/mcp` and authenticate `motir`; otherwise, connect the MCP
as described at <https://motir.co/docs/mcp>. If a call fails with a connection error, a 401 or a
not-found, **stop and report** the change you intended (the key and the target status) — never work
around it.

1. **Get the key.** `motir mark <key> done` needs a work-item key such as `ACME-12`. No key ⇒ ask
   which card; do not guess one.

2. **Read the card** — `get_work_item { key }`. Note its `kind`, `type`, `executor`, `status`,
   `children` and `deliveries` (the pull requests linked to it).

3. **Refuse the cards a merge closes, and say why.** Stop without changing anything when:
   - **It has a linked pull request** (`deliveries` is not empty). Its merge closes it: Motir's
     status sync moves a linked card to Done when the pull request merges. If that pull request has
     merged and the card is still not Done, read the card's latest comments
     (`get_work_item_activity { key, view: "comments" }`) — Motir posts a comment when it holds a
     card on purpose (a merge onto a branch other than the default, a sibling pull request still
     open). Report that reason. **Never override a hold by flipping the status.**
   - **It is a code card with no pull request** (`type` is not `manual` and `executor` is not
     `human`). Its work is not finished until a pull request carrying it merges — that is what
     `motir-run` produces.
   - **It is a container** (it has `children`). Completing a container closes every child under it,
     whatever state they are in. Close the children, and Motir derives the container's status from
     them.
   - **It is already Done or Cancelled.** Nothing to do; say so.

4. **The user's word is the confirmation.** Saying `motir mark <key> done` means the person has
   finished the work — you do not ask again. If the card's `readiness.openBlockers` is not empty,
   the work it depended on is not finished either: name those blockers and ask whether to close it
   anyway.

5. **Walk the status up, one legal step at a time** — `transition_status { key, status }`:
   - from `todo` or `blocked` → `in_progress`, then → `done`;
   - from `in_progress` → `done`.

   If a step is refused, the error lists the statuses the card may move to: take the one that leads
   towards Done and continue. **Never use `cancelled`** — cancelled means the work was not done.
   Never skip a refusal by editing the card instead.

6. **Record it** — `add_comment { key, body }`: that the work was confirmed done, by whom, and
   anything the person told you about it (what was set up, where it lives — never a secret's value).

7. **Report** — the card and its final status (read it back with `get_work_item`), and its parent's
   status as Motir now shows it. Motir derives a parent's status from its children; do not move the
   parent by hand.
