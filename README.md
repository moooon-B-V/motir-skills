# Motir skills

Skills that let the coding agent you already use work a [Motir](https://motir.co) project: take the
next card from To Do to a linked pull request, log a verified bug where it belongs, clear the `Bugs`
folder one pull request per bug, be walked through a human card one checked step at a time, and
close a manual card with a record of who confirmed it — all through Motir's MCP server.

They are plain [Agent Skills](https://agentskills.io) — one folder per skill with a `SKILL.md` — so
any agent that reads that format can use them, and the repository is also a Claude Code plugin
marketplace.

## Install in Claude Code

```text
/plugin marketplace add moooon-B-V/motir-skills
/plugin install motir@motir-skills
```

From a local clone, use the path instead: `git clone https://github.com/moooon-B-V/motir-skills.git`,
then `/plugin marketplace add ./motir-skills` and the same `/plugin install`.

One install brings three things:

- **The six skills** in the table below.
- **The `motir` MCP server** at `https://app.motir.co/api/mcp`. Claude Code signs into it in the
  browser the first time it is used — run `/mcp`, pick `motir`, choose **Authenticate** — and on
  Motir's consent screen you pick the workspace and approve. There is no token to create or paste.
- **The `motir` CLI**, through the plugin's `scripts/motir` runner. It runs one pinned `@motir/cli`
  version with `npx`, so nothing is installed globally, and it needs **Node.js 22 or newer**. The CLI
  signs in on its own (`motir login`); it does not share the MCP's sign-in.

Claude Code lists the skills once the plugin is installed, and `/mcp` shows `motir`. An organisation
on claude.ai can also add the same plugin for all its members from its plugin settings — see
Anthropic's [plugin admin guide](https://claude.com/docs/plugins/admin).

## What you need first

- A Motir account and a project.
- **In Claude Code, nothing else** — the plugin connects Motir (above).
- **For any other agent, for CI, or for a client without OAuth**, connect the MCP by hand with a
  personal access token: create one in Motir under **Settings → Account → Tokens**, and point the
  client at `https://app.motir.co/api/mcp` with the token as a bearer header. In Claude Code that
  would be:

  ```sh
  claude mcp add --transport http motir https://app.motir.co/api/mcp \
    --header "Authorization: Bearer <your-token>"
  ```

  The setup for each agent is at <https://motir.co/docs/mcp>. A token created with the default
  permissions holds everything these skills call; the full list of tools and the permission each one
  needs is at <https://app.motir.co/docs/mcp/tools>.
- `git`, and the GitHub CLI (`gh`) where a skill reads pull requests.
- **Node.js 22 or newer**, only for the `motir` CLI runner.

Nothing else: no other credential, and no access to anything but your own project.

## The skills

| Skill | Say | What it does |
|---|---|---|
| [`motir-run`](skills/motir-run/SKILL.md) | `motir run` · `motir run <key>` · `motir next` | Closes out merged work, claims the card, builds it on its own branch, opens ONE pull request linked to the card, moves it to Implemented and publishes How to test. A card that cannot be built as written is handed to Motir's planner with the correction, not built. |
| [`motir-log-bug`](skills/motir-log-bug/SKILL.md) | `motir log bug <what is wrong>` | Root-causes the defect first, looks for the card someone already filed, then files ONE bug — under the story it blocks, or in the project's `Bugs` folder — linked to the card it was found on. |
| [`motir-fix`](skills/motir-fix/SKILL.md) | `motir fix <KEY>` | Repairs ONE card's red pull requests after the run that opened them has ended — failing checks, a merge-queue ejection, or an acceptance video sent back with Re-run. Claims the repair so nobody pushes over it, fixes on each pull request's OWN branch (never a new one), up to five attempts, re-records the acceptance video once CI is green, and closes the repair with how it ended. Never moves the card's status or merges. Not `motir fix bugs` — that is `motir-fix-bugs`, the row below. |
| [`motir-fix-bugs`](skills/motir-fix-bugs/SKILL.md) | `motir fix bugs` · `motir fix bugs <limit>` | Works through the project's `Bugs` folder one bug at a time, oldest first. Each bug gets exactly one outcome: ONE pull request fixing only that bug, a `blocked_by` edge to the card it genuinely waits on, or a comment with the evidence when it is already fixed, cannot be reproduced or needs a person. Ends by itself and reports every bug. |
| [`motir-guide`](skills/motir-guide/SKILL.md) | `motir guide <key>` · `motir guide` | Walks you through a human card — `executor: human`, whatever its type — one step at a time: claims it, gives ONE step with its notes and the command to copy, checks what it can with read-only means (`dig`, a URL, a CLI `status`) before ticking the step on the card, resumes where an interrupted walk stopped, and closes the card to Done (or leaves it to its pull request's merge) with a summary of what was done and checked. A card with no steps gets proposed steps, written to the card only with your OK. |
| [`motir-mark`](skills/motir-mark/SKILL.md) | `motir mark <key> done` | Closes a card no pull request can close (a manual card: an account, a secret, a setting), walking its status to Done with a comment. A card that has a pull request is closed by its merge, and the skill says so instead. |

## Install in any other agent

The guide with every agent's steps will live at <https://motir.co/docs/skills>. Until then, copy the
skill folders you want (`skills/<name>/`) into the directory your agent loads skills from (for example
a project's `.claude/skills/` or `.agents/skills/`), each folder keeping its `SKILL.md` and
`SYNC.json` together, and connect the MCP with a token as described under *What you need first*.

## Contributing

Each skill is ONE copy with TWO modes, and every new skill follows the same shape.

### The two-mode `SKILL.md`

1. **Frontmatter** — `name` equal to the folder name, and a `description` carrying the phrases a user
   says to trigger it (at most 1024 characters).
2. **`## Runbook mode`** — Motir's own team keeps the full procedures in a private runbook
   (`motir-meta`). The section opens with the lookup block every skill shares: `$MOTIR_META`, else a
   `motir-meta` checkout at or above the working directory. When it finds one, the skill routes into
   the runbook's files — freshen `origin/main`, read the named `prompts/…` files in order — and
   **ignores everything below**, so the runbook stays the only home of the rules for that team.
3. **`## Standalone mode`** — for everyone else: a short procedure that talks to Motir **only through
   MCP tools** a default project token holds (plus `git` / `gh`), named exactly as the server names
   them. It opens by naming the runbook sections it condenses.

A standalone procedure is a **condensation, not a port**: it keeps every rule whose absence breaks the
workflow and leaves the team-specific history behind. Repository-specific rules (architecture, test
commands) belong to the target repository's own `CLAUDE.md` / `AGENTS.md`, not here.

### `SYNC.json` — what each procedure was written against

Every skill carries `skills/<name>/SYNC.json`, one entry per runbook section its standalone procedure
condenses:

```json
[{ "corpusPath": "prompts/log-bug.md", "heading": "Procedure", "sha256": "<64 hex>" }]
```

The hash is of that section's text on the runbook's `origin/main` when the procedure was last brought
up to date. **`scripts/section-hash.py` is the single definition of "a section's text"** — a heading
and everything up to the next heading of the same or a higher level, fenced code excluded, trailing
whitespace ignored — and both this repository and the runbook use it:

```sh
python3 scripts/section-hash.py --verify <runbook-checkout> skills/*/SYNC.json   # does each still match?
python3 scripts/section-hash.py --update <runbook-checkout> skills/<name>/SYNC.json
```

Run `--update` only after re-reading the drifted sections and bringing the procedure up to date: the
hash says what the procedure was written against, not merely what exists today. The runbook side
checks these hashes against its own `origin/main` and fails when a condensed section moves.

### Checks

```sh
python3 scripts/validate.py          # skills, SYNC.json, secrets, manifests, the MCP entry,
                                     # the directory's shape, and the runner's npm pin
python3 scripts/test_validate.py     # validate.py's checks, each against a planted defect
python3 scripts/test_motir.py        # the CLI runner, with stub node / npx
python3 scripts/test_section_hash.py # the section definition
claude plugin validate . --strict    # Claude Code accepts the manifests, warnings included
```

The `validate` workflow runs all of them on every push and pull request. A new skill is added to
`.claude-plugin/plugin.json`'s `skills` list in the same pull request — the validator refuses a
folder the manifest does not list.

### Releasing

`main` is protected: every change is a reviewed pull request. A release is cut from what has merged:

1. A pull request bumps `version` in `.claude-plugin/plugin.json` (semantic versioning — a new skill
   is a minor bump, a procedure fix a patch) and merges.
2. Tag that merge commit `v<version>` and push the tag.
3. Publish a GitHub release from the tag, listing the skills it carries and what changed.
4. Install from the tag as a consumer would, and check the skills load.

## Licence

[MIT](LICENSE) — © moooon B.V.
