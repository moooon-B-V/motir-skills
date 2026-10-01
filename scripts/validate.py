#!/usr/bin/env python3
"""Check the repository's shape — what CI's `validate` workflow runs, and what a contributor runs first.

The repository is a marketplace whose one plugin lives in its own folder, `plugins/motir/`: that folder
is the bundle Claude Code installs and Claude's plugin directory scans, so it holds only what a user
runs. The repository root holds the marketplace manifest and this tooling, which never ships.

1. `check_skill` — Every folder under `plugins/motir/skills/` holds a `SKILL.md` whose frontmatter `name` equals the folder and
   whose `description` is non-empty (at most 1024 characters, the Agent Skills limit).
2. `check_skill` — Every `SKILL.md` has a `## Runbook mode` section followed by a `## Standalone mode` section.
3. `check_skill` — Every skill has a `SYNC.json`: a non-empty JSON list of `{ corpusPath, heading, sha256 }`, each
   `heading` non-empty and each `sha256` a 64-character hex digest. (Whether the hashes still MATCH
   the runbook is checked where the runbook lives — `scripts/section-hash.py --verify`.)
4. `check_secrets` — No tracked file carries a secret-shaped string (a GitHub or Motir token).
5. `check_manifests` — The plugin's `.claude-plugin/plugin.json` lists exactly the skill folders, and the
   repository's `.claude-plugin/marketplace.json` offers that plugin once, from `./plugins/motir`.
6. `check_mcp_server` — The plugin's `.claude-plugin/plugin.json` declares the `motir` MCP server as `type: http` at
   `https://app.motir.co/api/mcp`, with no `headers` / `headersHelper`, and carries no `userConfig` —
   the plugin signs in over OAuth and has no token path.
7. `check_directory_shape` — The tree has the shape Claude's plugin directory and the claude.ai / Cowork install accept: no
   `bin/` at the plugin's root, no minified or bundled JavaScript (`*.min.js`, `*.bundle.js`, or a `.js` / `.mjs` /
   `.cjs` line over 2,000 characters), every component path in `plugin.json` inside the plugin root,
   and a `LICENSE` plus a `README.md` of at least 40 words in the plugin.
8. `check_runner` — The plugin's `scripts/motir` is committed executable (mode 100755) with exactly one `MOTIR_CLI_VERSION=` pin,
   and that version of `@motir/cli` is published on npm. An unreachable registry is reported as such,
   never as an unpublished version.
9. `check_listing` — The plugin's `.claude-plugin/plugin.json` names an `icon` that is a square PNG or JPEG inside the plugin,
   512 to 2048 px on a side and under 2 MB, and sets `privacyPolicyUrl` to an https URL. Claude's plugin
   directory warns on both, and reads the icon only the first time the plugin is saved or submitted there.
10. `check_credential_names` — No file in the plugin names a shell variable with a credential-shaped word as
   one of its underscore-separated parts (PWD, PIN, TOKEN, SECRET, KEY, …), as a reference or an
   assignment, or defines a shell function named with one (`pass`, `token`, …). The directory's scanner
   reads one beside a remote URL as a credential leaving the machine and holds the plugin for review;
   use the command (`pwd`) or a plainer name instead.
11. `check_bundle` — The plugin folder holds only what a user runs: its manifest, the icon it names, the
   skills (`SKILL.md` and `SYNC.json` each), the runner, `README.md` and `LICENSE`. Anything else — a
   test, a CI script — is scanned by the directory as part of the plugin, and has held it for review.

Each item names the `check_*` function that performs it; `main()` calls every one of them once.
Exits 1 and names every failure. Standard library only.
"""

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET = re.compile(r"(ghp|gho|ghs|ghu|github_pat|mtr|motir_pat)_[A-Za-z0-9_]{10,}")
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MCP_URL = "https://app.motir.co/api/mcp"
MAX_JS_LINE = 2000
MIN_README_WORDS = 40
CLI_PACKAGE = "@motir/cli"
PLUGIN = "plugins/motir"
MARKETPLACE_SOURCE = "./" + PLUGIN
RUNNER = "scripts/motir"
VERSION_LINE = re.compile(r'^MOTIR_CLI_VERSION="?([^"\s]*)"?\s*$', re.MULTILINE)
ICON_MIN, ICON_MAX, ICON_MAX_BYTES = 512, 2048, 2 * 1024 * 1024
# A shell variable whose name has one of these words as an underscore-separated part reads, to Claude's
# plugin-directory scanner, as a credential taken from the user's machine — `PWD` as a password, `PIN` as
# a PIN — and one beside a remote URL is held for review. Its own remedy is to remove the read.
CREDENTIAL_WORDS = {"PWD", "PIN", "PASS", "PASSWD", "PASSWORD", "TOKEN", "SECRET", "KEY", "APIKEY",
                    "CREDENTIAL", "CREDENTIALS", "AUTH"}
SHELL_VARIABLE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)|(?:^|[\s;&|(])(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=")
SHELL_FUNCTION = re.compile(r"(?:^|[\s;&|])(?:function\s+([A-Za-z_][A-Za-z0-9_]*)|([A-Za-z_][A-Za-z0-9_]*)\s*\(\))")
SKILL_FILE = re.compile(r"^skills/[^/]+/(SKILL\.md|SYNC\.json)$")

errors = []


def fail(msg):
    errors.append(msg)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def plugin_path(*parts):
    """A path inside the plugin folder."""
    return os.path.join(ROOT, PLUGIN, *parts)


def read_plugin():
    """The plugin's manifest, or None when it is missing or malformed (check_manifests names that)."""
    try:
        return read_json(plugin_path(".claude-plugin", "plugin.json"))
    except (OSError, json.JSONDecodeError):
        return None


def frontmatter(text):
    """The `key: value` pairs between the opening and closing `---` lines (single-line values)."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            fields[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return None


def check_skill(name):
    folder = plugin_path("skills", name)
    path = os.path.join(folder, "SKILL.md")
    if not os.path.isfile(path):
        fail(f"{PLUGIN}/skills/{name}: no SKILL.md")
        return
    text = read_text(path)
    fm = frontmatter(text)
    if fm is None:
        fail(f"{PLUGIN}/skills/{name}/SKILL.md: no YAML frontmatter between --- lines")
        return
    if fm.get("name") != name:
        fail(f"{PLUGIN}/skills/{name}/SKILL.md: frontmatter name is {fm.get('name')!r}, must equal the folder {name!r}")
    if not NAME.match(name):
        fail(f"{PLUGIN}/skills/{name}: folder name must be lowercase letters, digits and single hyphens")
    desc = fm.get("description", "")
    if not desc:
        fail(f"{PLUGIN}/skills/{name}/SKILL.md: frontmatter description is empty")
    elif len(desc) > 1024:
        fail(f"{PLUGIN}/skills/{name}/SKILL.md: description is {len(desc)} characters (max 1024)")
    runbook = text.find("\n## Runbook mode")
    standalone = text.find("\n## Standalone mode")
    if runbook < 0 or standalone < 0 or standalone < runbook:
        fail(f"{PLUGIN}/skills/{name}/SKILL.md: needs a '## Runbook mode' section, then a '## Standalone mode' section")

    sync_path = os.path.join(folder, "SYNC.json")
    if not os.path.isfile(sync_path):
        fail(f"{PLUGIN}/skills/{name}: no SYNC.json")
        return
    try:
        entries = read_json(sync_path)
    except json.JSONDecodeError as e:
        fail(f"{PLUGIN}/skills/{name}/SYNC.json: not valid JSON ({e})")
        return
    if not isinstance(entries, list) or not entries:
        fail(f"{PLUGIN}/skills/{name}/SYNC.json: must be a non-empty list")
        return
    for i, entry in enumerate(entries):
        where = f"{PLUGIN}/skills/{name}/SYNC.json[{i}]"
        if not isinstance(entry, dict):
            fail(f"{where}: must be an object")
            continue
        if not str(entry.get("corpusPath", "")).strip():
            fail(f"{where}: corpusPath is empty")
        if not str(entry.get("heading", "")).strip():
            fail(f"{where}: heading is empty")
        if not SHA256.match(str(entry.get("sha256", ""))):
            fail(f"{where}: sha256 must be a 64-character lowercase hex digest")


def tree_files():
    """Tracked files plus untracked ones git does not ignore, relative to ROOT."""
    out = subprocess.run(
        ["git", "-C", ROOT, "ls-files", "--cached", "--others", "--exclude-standard"],
        check=True, capture_output=True, text=True,
    ).stdout.split("\n")
    return [rel for rel in out if rel]


def plugin_files():
    """The tree's files inside the plugin folder, relative to it."""
    prefix = PLUGIN + "/"
    return [rel[len(prefix):] for rel in tree_files() if rel.startswith(prefix)]


def check_secrets():
    for rel in tree_files():
        try:
            text = read_text(os.path.join(ROOT, rel))
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for n, line in enumerate(text.split("\n"), 1):
            if SECRET.search(line):
                fail(f"{rel}:{n}: secret-shaped string")


def check_manifests(skills):
    try:
        plugin = read_json(plugin_path(".claude-plugin", "plugin.json"))
        market = read_json(os.path.join(ROOT, ".claude-plugin", "marketplace.json"))
    except (OSError, json.JSONDecodeError) as e:
        fail(f".claude-plugin: {e}")
        return
    listed = sorted(p.rstrip("/").removeprefix("./").removeprefix("skills/") for p in plugin.get("skills", []))
    if listed != sorted(skills):
        fail(f"{PLUGIN}/.claude-plugin/plugin.json: skills lists {listed}, the skill folders are {sorted(skills)}")
    offered = [p for p in market.get("plugins", []) if p.get("name") == plugin.get("name")]
    if len(offered) != 1 or offered[0].get("source") != MARKETPLACE_SOURCE:
        fail(f".claude-plugin/marketplace.json: must offer plugin {plugin.get('name')!r} once,"
             f" with source {MARKETPLACE_SOURCE!r}")


def check_mcp_server():
    plugin = read_plugin()
    if plugin is None:
        return  # check_manifests already named it
    where = f"{PLUGIN}/.claude-plugin/plugin.json"
    if "userConfig" in plugin:
        fail(f"{where}: userConfig is not allowed — the plugin signs in over OAuth and has no token field")
    servers = plugin.get("mcpServers")
    server = servers.get("motir") if isinstance(servers, dict) else None
    if not isinstance(server, dict):
        fail(f"{where}: mcpServers.motir must be declared as an object")
        return
    if server.get("type") != "http":
        fail(f"{where}: mcpServers.motir.type is {server.get('type')!r}, must be 'http'")
    if server.get("url") != MCP_URL:
        fail(f"{where}: mcpServers.motir.url is {server.get('url')!r}, must be {MCP_URL!r}")
    for key in ("headers", "headersHelper"):
        if key in server:
            fail(f"{where}: mcpServers.motir.{key} is not allowed — no static credential ships in the plugin")


def component_paths(plugin):
    """Every path-valued component field of plugin.json, as written."""
    paths = []
    for key in ("skills", "commands", "agents", "hooks", "mcpServers", "lspServers", "outputStyles"):
        value = plugin.get(key)
        if isinstance(value, str):
            paths.append(value)
        elif isinstance(value, list):
            paths.extend(v for v in value if isinstance(v, str))
    return paths


def check_directory_shape():
    if os.path.isdir(plugin_path("bin")):
        fail(f"{PLUGIN}/bin/: a bin/ at the plugin's root is not allowed — the claude.ai / Cowork install refuses it")
    for rel in tree_files():
        name = os.path.basename(rel)
        if name.endswith((".min.js", ".bundle.js")):
            fail(f"{rel}: minified or bundled code is not allowed")
            continue
        if not name.endswith((".js", ".mjs", ".cjs")):
            continue
        try:
            text = read_text(os.path.join(ROOT, rel))
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for n, line in enumerate(text.split("\n"), 1):
            if len(line) > MAX_JS_LINE:
                fail(f"{rel}:{n}: a {len(line)}-character line reads as minified or bundled code (max {MAX_JS_LINE})")
                break
    plugin = read_plugin() or {}
    root = os.path.realpath(plugin_path())
    for p in component_paths(plugin):
        resolved = os.path.realpath(plugin_path(p))
        if os.path.isabs(p) or os.path.commonpath([root, resolved]) != root:
            fail(f"{PLUGIN}/.claude-plugin/plugin.json: component path {p!r} is outside the plugin root")
    if not os.path.isfile(plugin_path("LICENSE")):
        fail(f"{PLUGIN}/LICENSE: missing")
    readme = plugin_path("README.md")
    if not os.path.isfile(readme):
        fail(f"{PLUGIN}/README.md: missing")
    else:
        words = len(read_text(readme).split())
        if words < MIN_README_WORDS:
            fail(f"{PLUGIN}/README.md: {words} words, needs at least {MIN_README_WORDS}")


def npm_view(spec):
    """`npm view <spec> version` → (exit code, stripped stdout)."""
    try:
        done = subprocess.run(["npm", "view", spec, "version"], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return done.returncode, done.stdout.strip()


def check_runner():
    path = plugin_path(RUNNER)
    runner = f"{PLUGIN}/{RUNNER}"
    if not os.path.isfile(path):
        fail(f"{runner}: missing")
        return
    staged = subprocess.run(
        ["git", "-C", ROOT, "ls-files", "-s", "--", runner], check=True, capture_output=True, text=True,
    ).stdout.split()
    if not staged or staged[0] != "100755":
        fail(f"{runner}: must be committed executable (git mode 100755), is {staged[0] if staged else 'untracked'}")
    pins = VERSION_LINE.findall(read_text(path))
    if len(pins) != 1 or not pins[0]:
        fail(f"{runner}: needs exactly one MOTIR_CLI_VERSION=\"<version>\" line, found {len(pins)}")
        return
    pin = pins[0]
    code, out = npm_view(f"{CLI_PACKAGE}@{pin}")
    if code == 0 and out == pin:
        return
    control, _ = npm_view(CLI_PACKAGE)
    if control != 0:
        fail(f"{runner}: could not check MOTIR_CLI_VERSION {pin} — the npm registry is unreachable")
    else:
        fail(f"{runner}: MOTIR_CLI_VERSION {pin} is not a published version of {CLI_PACKAGE}")


def image_size(path):
    """(kind, width, height) of a PNG or JPEG file, or None when it is neither."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return "png", int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 <= len(data) and data[i] == 0xFF:
        marker = data[i + 1]
        length = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            return "jpeg", int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + length
    return None


def check_listing():
    plugin = read_plugin()
    if plugin is None:
        return  # check_manifests already named it
    where = f"{PLUGIN}/.claude-plugin/plugin.json"
    url = plugin.get("privacyPolicyUrl")
    if not isinstance(url, str) or not url.startswith("https://"):
        fail(f"{where}: privacyPolicyUrl must be an https URL — the plugin connects to a remote MCP server")
    icon = plugin.get("icon")
    if not isinstance(icon, str) or not icon:
        fail(f"{where}: icon must name a square PNG or JPEG in the plugin")
        return
    root = os.path.realpath(plugin_path())
    path = os.path.realpath(plugin_path(icon))
    if os.path.isabs(icon) or os.path.commonpath([root, path]) != root:
        fail(f"{where}: icon {icon!r} is outside the plugin root")
        return
    if not os.path.isfile(path):
        fail(f"{PLUGIN}/{icon}: the icon plugin.json names does not exist")
        return
    size = os.path.getsize(path)
    if size >= ICON_MAX_BYTES:
        fail(f"{PLUGIN}/{icon}: {size} bytes, must be under {ICON_MAX_BYTES}")
    shape = image_size(path)
    if shape is None:
        fail(f"{PLUGIN}/{icon}: not a PNG or JPEG")
        return
    _, width, height = shape
    if width != height or not ICON_MIN <= width <= ICON_MAX:
        fail(f"{PLUGIN}/{icon}: {width}x{height}, must be square and {ICON_MIN} to {ICON_MAX} px on a side")


def credential_word(name, fold=False):
    """The credential-shaped part of a name, or None. `fold` matches a lowercase name too (`pass`)."""
    for part in name.split("_"):
        if (part.upper() if fold else part) in CREDENTIAL_WORDS:
            return part
    return None


def check_credential_names():
    for rel in plugin_files():
        try:
            text = read_text(plugin_path(rel))
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for n, line in enumerate(text.split("\n"), 1):
            found = {}
            for m in SHELL_VARIABLE.finditer(line):
                name = m.group(1) or m.group(2)
                found.setdefault(("variable", name), credential_word(name))
            for m in SHELL_FUNCTION.finditer(line):
                name = m.group(1) or m.group(2)
                found.setdefault(("function", name), credential_word(name, fold=True))
            for (kind, name), word in found.items():
                if word:
                    fail(f"{PLUGIN}/{rel}:{n}: {kind} {name} reads as a credential ({word})"
                         " to the plugin directory's scanner")


def check_bundle():
    plugin = read_plugin() or {}
    allowed = {".claude-plugin/plugin.json", RUNNER, "README.md", "LICENSE"}
    if isinstance(plugin.get("icon"), str):
        allowed.add(os.path.normpath(plugin["icon"]))
    for rel in plugin_files():
        if rel not in allowed and not SKILL_FILE.match(rel):
            fail(f"{PLUGIN}/{rel}: does not belong in the plugin — only the manifest, its icon, the skills,"
                 " the runner, README.md and LICENSE ship")


def main(root=None):
    global ROOT, errors
    if root is not None:
        ROOT = root
    errors = []
    skills_dir = plugin_path("skills")
    skills = sorted(d for d in os.listdir(skills_dir) if os.path.isdir(os.path.join(skills_dir, d)))
    if not skills:
        fail(f"{PLUGIN}/skills/: no skill folders")
    for name in skills:
        check_skill(name)
    check_secrets()
    check_manifests(skills)
    check_mcp_server()
    check_directory_shape()
    check_runner()
    check_listing()
    check_credential_names()
    check_bundle()
    for e in errors:
        print(f"✘ {e}")
    if errors:
        return 1
    print(f"✔ {len(skills)} skills: {', '.join(skills)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
