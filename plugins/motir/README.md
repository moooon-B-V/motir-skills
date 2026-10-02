# Motir

Skills that let your coding agent work a [Motir](https://motir.co) project: take the next card from
To Do to a linked pull request, repair a card's red pull requests, carry on a card whose run died, log a verified bug where it belongs,
clear the `Bugs` folder one pull request per bug, be walked through a human card one checked step at a
time, and close a manual card with a record of who confirmed it.

Installing the plugin brings three things:

- **Seven skills**: `motir-run`, `motir-fix`, `motir-continue`, `motir-log-bug`, `motir-fix-bugs`,
  `motir-guide` and `motir-mark`. Each one says, in its `SKILL.md`, what to type to use it.
- **The `motir` MCP server** at `https://app.motir.co/api/mcp`. Claude Code signs into it in the
  browser the first time it is used — run `/mcp`, pick `motir`, choose **Authenticate** — and on
  Motir's consent screen you pick the workspace and approve. There is no token to create or paste.
- **The `motir` CLI**, through the `scripts/motir` runner, which runs one pinned `@motir/cli` version
  with `npx`. It needs **Node.js 22 or newer** and signs in on its own (`motir login`).

You need a Motir account and a project, `git`, and the GitHub CLI (`gh`) where a skill reads pull
requests. Setup for other agents: <https://motir.co/docs/mcp>. Source, documentation and issues:
<https://github.com/moooon-B-V/motir-skills>.

## Licence

[MIT](LICENSE) — © moooon B.V.
