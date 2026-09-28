#!/usr/bin/env python3
"""Check the repository's shape — what CI's `validate` workflow runs, and what a contributor runs first.

1. Every folder under `skills/` holds a `SKILL.md` whose frontmatter `name` equals the folder and
   whose `description` is non-empty (at most 1024 characters, the Agent Skills limit).
2. Every `SKILL.md` has a `## Runbook mode` section followed by a `## Standalone mode` section.
3. Every skill has a `SYNC.json`: a non-empty JSON list of `{ corpusPath, heading, sha256 }`, each
   `heading` non-empty and each `sha256` a 64-character hex digest. (Whether the hashes still MATCH
   the runbook is checked where the runbook lives — `scripts/section-hash.py --verify`.)
4. No tracked file carries a secret-shaped string (a GitHub or Motir token).
5. `.claude-plugin/plugin.json` lists exactly the skill folders, and `.claude-plugin/marketplace.json`
   offers that plugin from the repository root.

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

errors = []


def fail(msg):
    errors.append(msg)


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
    folder = os.path.join(ROOT, "skills", name)
    path = os.path.join(folder, "SKILL.md")
    if not os.path.isfile(path):
        fail(f"skills/{name}: no SKILL.md")
        return
    text = open(path, encoding="utf-8").read()
    fm = frontmatter(text)
    if fm is None:
        fail(f"skills/{name}/SKILL.md: no YAML frontmatter between --- lines")
        return
    if fm.get("name") != name:
        fail(f"skills/{name}/SKILL.md: frontmatter name is {fm.get('name')!r}, must equal the folder {name!r}")
    if not NAME.match(name):
        fail(f"skills/{name}: folder name must be lowercase letters, digits and single hyphens")
    desc = fm.get("description", "")
    if not desc:
        fail(f"skills/{name}/SKILL.md: frontmatter description is empty")
    elif len(desc) > 1024:
        fail(f"skills/{name}/SKILL.md: description is {len(desc)} characters (max 1024)")
    runbook = text.find("\n## Runbook mode")
    standalone = text.find("\n## Standalone mode")
    if runbook < 0 or standalone < 0 or standalone < runbook:
        fail(f"skills/{name}/SKILL.md: needs a '## Runbook mode' section, then a '## Standalone mode' section")

    sync_path = os.path.join(folder, "SYNC.json")
    if not os.path.isfile(sync_path):
        fail(f"skills/{name}: no SYNC.json")
        return
    try:
        entries = json.load(open(sync_path, encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"skills/{name}/SYNC.json: not valid JSON ({e})")
        return
    if not isinstance(entries, list) or not entries:
        fail(f"skills/{name}/SYNC.json: must be a non-empty list")
        return
    for i, entry in enumerate(entries):
        where = f"skills/{name}/SYNC.json[{i}]"
        if not isinstance(entry, dict):
            fail(f"{where}: must be an object")
            continue
        if not str(entry.get("corpusPath", "")).strip():
            fail(f"{where}: corpusPath is empty")
        if not str(entry.get("heading", "")).strip():
            fail(f"{where}: heading is empty")
        if not SHA256.match(str(entry.get("sha256", ""))):
            fail(f"{where}: sha256 must be a 64-character lowercase hex digest")


def check_secrets():
    files = subprocess.run(
        ["git", "-C", ROOT, "ls-files", "--cached", "--others", "--exclude-standard"],
        check=True, capture_output=True, text=True,
    ).stdout.split("\n")
    for rel in filter(None, files):
        try:
            text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for n, line in enumerate(text.split("\n"), 1):
            if SECRET.search(line):
                fail(f"{rel}:{n}: secret-shaped string")


def check_manifests(skills):
    try:
        plugin = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8"))
        market = json.load(open(os.path.join(ROOT, ".claude-plugin", "marketplace.json"), encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        fail(f".claude-plugin: {e}")
        return
    listed = sorted(p.rstrip("/").removeprefix("./").removeprefix("skills/") for p in plugin.get("skills", []))
    if listed != sorted(skills):
        fail(f".claude-plugin/plugin.json: skills lists {listed}, the skill folders are {sorted(skills)}")
    offered = [p for p in market.get("plugins", []) if p.get("name") == plugin.get("name")]
    if len(offered) != 1 or offered[0].get("source") not in ("./", "."):
        fail(f".claude-plugin/marketplace.json: must offer plugin {plugin.get('name')!r} once, with source './'")


def main():
    skills_dir = os.path.join(ROOT, "skills")
    skills = sorted(d for d in os.listdir(skills_dir) if os.path.isdir(os.path.join(skills_dir, d)))
    if not skills:
        fail("skills/: no skill folders")
    for name in skills:
        check_skill(name)
    check_secrets()
    check_manifests(skills)
    for e in errors:
        print(f"✘ {e}")
    if errors:
        return 1
    print(f"✔ {len(skills)} skills: {', '.join(skills)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
