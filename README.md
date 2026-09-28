# Motir skills

Skills that let the coding agent you already use work a [Motir](https://motir.co) project: log a
verified bug where it belongs, and close a manual card with a record of who confirmed it — all
through Motir's MCP server.

They are plain [Agent Skills](https://agentskills.io) — one folder per skill with a `SKILL.md` — so
any agent that reads that format can use them, and the repository is also a Claude Code plugin
marketplace.

## What you need first

- A Motir account and a project.
- **The Motir MCP server connected to your agent** — a personal access token from
  **Settings → Account → Tokens** in Motir, and the server at `https://app.motir.co/api/mcp`.
  The setup for each agent is at <https://motir.co/docs/mcp>. A token created with the default
  permissions holds everything these skills call; the full list of tools and the permission each one
  needs is at <https://app.motir.co/docs/mcp/tools>.
- `git`, and the GitHub CLI (`gh`) where a skill reads pull requests.

Nothing else: no other credential, and no access to anything but your own project.

## The skills

| Skill | Say | What it does |
|---|---|---|
| [`motir-log-bug`](skills/motir-log-bug/SKILL.md) | `motir log bug <what is wrong>` | Root-causes the defect first, looks for the card someone already filed, then files ONE bug — under the story it blocks, or in the project's `Bugs` folder — linked to the card it was found on. |
| [`motir-mark`](skills/motir-mark/SKILL.md) | `motir mark <key> done` | Closes a card no pull request can close (a manual card: an account, a secret, a setting), walking its status to Done with a comment. A card that has a pull request is closed by its merge, and the skill says so instead. |

## Install

The guide with every agent's steps will live at <https://motir.co/docs/skills>. Until then:

**Claude Code, from GitHub**

```text
/plugin marketplace add moooon-B-V/motir-skills
/plugin install motir@motir-skills
```

**Claude Code, from a local clone** — the same two commands, with the path to your clone:

```sh
git clone https://github.com/moooon-B-V/motir-skills.git
```

```text
/plugin marketplace add ./motir-skills
/plugin install motir@motir-skills
```

Then ask the agent which skills it has: the ones in the table above are listed.

**Any other agent** — copy the skill folders you want (`skills/<name>/`) into the directory your
agent loads skills from (for example a project's `.claude/skills/` or `.agents/skills/`), each folder
keeping its `SKILL.md` and `SYNC.json` together.

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
python3 scripts/validate.py          # skills, SYNC.json, secrets, manifests
python3 scripts/test_section_hash.py # the section definition
claude plugin validate .             # Claude Code accepts the manifests
```

The `validate` workflow runs all three on every push and pull request. A new skill is added to
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
