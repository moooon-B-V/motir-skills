#!/usr/bin/env python3
"""validate.py's MCP-entry, directory-shape and runner-pin checks: each defect fails naming its path,
and the repository itself passes. Every case copies the repository into a temporary git tree, plants ONE
defect and runs validate.main() over it. Standard library only."""

import contextlib
import importlib.util
import io
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def load_validate():
    spec = importlib.util.spec_from_file_location("validate", os.path.join(HERE, "validate.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate = load_validate()


def published(spec):
    """Stands in for the npm registry: `@motir/cli@<v>` answers `<v>`, as a published version would."""
    return 0, spec.rpartition("@")[2]


def run(root):
    """validate.main(root) → (exit code, printed output)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = validate.main(root)
    return code, out.getvalue()


class Tree:
    """A temporary git copy of the repository's tracked and unignored files."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="motir-skills-")
        files = subprocess.run(
            ["git", "-C", REPO, "ls-files", "--cached", "--others", "--exclude-standard"],
            check=True, capture_output=True, text=True,
        ).stdout.split("\n")
        for rel in filter(None, files):
            src = os.path.join(REPO, rel)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        subprocess.run(["git", "init", "-q", self.root], check=True)
        self.add()

    def add(self):
        subprocess.run(["git", "-C", self.root, "add", "-A"], check=True)

    def path(self, rel):
        return os.path.join(self.root, rel)

    def write(self, rel, text):
        os.makedirs(os.path.dirname(self.path(rel)) or self.root, exist_ok=True)
        with open(self.path(rel), "w", encoding="utf-8") as f:
            f.write(text)
        self.add()

    def edit_plugin(self, change):
        rel = ".claude-plugin/plugin.json"
        plugin = json.load(open(self.path(rel), encoding="utf-8"))
        change(plugin)
        self.write(rel, json.dumps(plugin, indent=2) + "\n")

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class TreeCase(unittest.TestCase):
    """A fresh repository copy per test, with the npm registry stubbed as answering every version."""

    def setUp(self):
        real, validate.npm_view = validate.npm_view, published
        self.addCleanup(setattr, validate, "npm_view", real)
        self.tree = Tree()
        self.addCleanup(self.tree.cleanup)

    def assertFailsNaming(self, needle):
        code, out = run(self.tree.root)
        self.assertEqual(code, 1, out)
        failures = [line for line in out.split("\n") if line.startswith("✘")]
        self.assertTrue(any(needle in line for line in failures), f"no failure names {needle!r}:\n{out}")


class ValidateTest(TreeCase):
    def test_repository_passes(self):
        code, out = run(REPO)
        self.assertEqual(code, 0, out)

    def test_copy_passes(self):
        code, out = run(self.tree.root)
        self.assertEqual(code, 0, out)

    def test_top_level_bin(self):
        self.tree.write("bin/motir", "#!/bin/sh\n")
        self.assertFailsNaming("bin/")

    def test_mcp_headers(self):
        self.tree.edit_plugin(lambda p: p["mcpServers"]["motir"].update(headers={"Authorization": "Bearer x"}))
        self.assertFailsNaming("mcpServers.motir.headers")

    def test_user_config(self):
        self.tree.edit_plugin(lambda p: p.update(userConfig={"token": {"type": "string"}}))
        self.assertFailsNaming("userConfig")

    def test_wrong_url(self):
        self.tree.edit_plugin(lambda p: p["mcpServers"]["motir"].update(url="https://example.com/mcp"))
        self.assertFailsNaming("mcpServers.motir.url")

    def test_minified_js(self):
        self.tree.write("scripts/vendor.min.js", "var a=1;\n")
        self.assertFailsNaming("scripts/vendor.min.js")

    def test_missing_license(self):
        os.remove(self.tree.path("LICENSE"))
        self.tree.add()
        self.assertFailsNaming("LICENSE")

    def test_short_readme(self):
        self.tree.write("README.md", " ".join(["word"] * 39) + "\n")
        self.assertFailsNaming("README.md")

    def test_long_js_line(self):
        self.tree.write("scripts/tool.js", "x" * 2001 + "\n")
        self.assertFailsNaming("scripts/tool.js:1")

    def test_component_path_outside_root(self):
        self.tree.edit_plugin(lambda p: p["skills"].append("../elsewhere"))
        self.assertFailsNaming("../elsewhere")

    def test_runner_not_executable(self):
        subprocess.run(["git", "-C", self.tree.root, "update-index", "--chmod=-x", "scripts/motir"], check=True)
        self.assertFailsNaming("scripts/motir: must be committed executable")

    def test_runner_two_pins(self):
        self.tree.write("scripts/motir", read(self.tree.path("scripts/motir")) + 'MOTIR_CLI_VERSION="0.8.0"\n')
        self.assertFailsNaming("scripts/motir: needs exactly one MOTIR_CLI_VERSION")

    def test_runner_unpublished_pin(self):
        validate.npm_view = lambda spec: (1, "") if spec.endswith("@0.8.99") else (0, "0.9.0")
        self.set_pin("0.8.99")
        self.assertFailsNaming("scripts/motir: MOTIR_CLI_VERSION 0.8.99 is not a published version")

    def test_registry_unreachable(self):
        validate.npm_view = lambda spec: (1, "getaddrinfo ENOTFOUND registry.npmjs.org")
        self.assertFailsNaming("scripts/motir: could not check MOTIR_CLI_VERSION 0.8.0 — the npm registry is unreachable")

    def set_pin(self, version):
        rel = "scripts/motir"
        text = re.sub(r'^MOTIR_CLI_VERSION=.*$', f'MOTIR_CLI_VERSION="{version}"', read(self.tree.path(rel)), flags=re.M)
        with open(self.tree.path(rel), "w", encoding="utf-8") as f:
            f.write(text)
        self.tree.add()


class EveryCheckFailsTest(TreeCase):
    """The failure branches of the other checks, one planted defect each."""

    SKILL = "skills/motir-run/SKILL.md"
    SYNC = "skills/motir-run/SYNC.json"

    def set_skill_md(self, text):
        self.tree.write(self.SKILL, text)

    def frontmatter(self, name="motir-run", description="Run a card."):
        return (f"---\nname: {name}\ndescription: {description}\n---\n\n"
                "## Runbook mode\n\nx\n\n## Standalone mode\n\ny\n")

    def test_skill_without_skill_md(self):
        os.remove(self.tree.path(self.SKILL))
        self.tree.add()
        self.assertFailsNaming("skills/motir-run: no SKILL.md")

    def test_no_frontmatter(self):
        self.set_skill_md("# no frontmatter\n")
        self.assertFailsNaming("no YAML frontmatter")

    def test_unclosed_frontmatter(self):
        self.set_skill_md("---\nname: motir-run\n")
        self.assertFailsNaming("no YAML frontmatter")

    def test_name_mismatch(self):
        self.set_skill_md(self.frontmatter(name="motir-walk"))
        self.assertFailsNaming("frontmatter name is 'motir-walk'")

    def test_bad_folder_name(self):
        os.rename(self.tree.path("skills/motir-mark"), self.tree.path("skills/Motir_Mark"))
        self.tree.write("skills/Motir_Mark/SKILL.md", self.frontmatter(name="Motir_Mark"))
        self.assertFailsNaming("skills/Motir_Mark: folder name must be")

    def test_empty_description(self):
        self.set_skill_md(self.frontmatter(description=""))
        self.assertFailsNaming("frontmatter description is empty")

    def test_long_description(self):
        self.set_skill_md(self.frontmatter(description="x" * 1025))
        self.assertFailsNaming("description is 1025 characters")

    def test_sections_out_of_order(self):
        self.set_skill_md("---\nname: motir-run\ndescription: d\n---\n\n## Standalone mode\n\n## Runbook mode\n")
        self.assertFailsNaming("needs a '## Runbook mode' section")

    def test_no_sync_json(self):
        os.remove(self.tree.path(self.SYNC))
        self.tree.add()
        self.assertFailsNaming("skills/motir-run: no SYNC.json")

    def test_sync_json_invalid(self):
        self.tree.write(self.SYNC, "{")
        self.assertFailsNaming("SYNC.json: not valid JSON")

    def test_sync_json_empty(self):
        self.tree.write(self.SYNC, "[]")
        self.assertFailsNaming("SYNC.json: must be a non-empty list")

    def test_sync_json_entries(self):
        self.tree.write(self.SYNC, json.dumps(["x", {"corpusPath": "", "heading": " ", "sha256": "ABC"}]))
        code, out = run(self.tree.root)
        self.assertEqual(code, 1, out)
        for needle in ("SYNC.json[0]: must be an object", "SYNC.json[1]: corpusPath is empty",
                       "SYNC.json[1]: heading is empty", "SYNC.json[1]: sha256 must be"):
            self.assertIn(needle, out)

    def test_secret_in_a_file(self):
        self.tree.write("notes.txt", "token ghp_" + "a" * 20 + "\n")
        self.assertFailsNaming("notes.txt:1: secret-shaped string")

    def test_binary_files_are_skipped(self):
        with open(self.tree.path("logo.png"), "wb") as f:
            f.write(b"\x89PNG\xff\xfe")
        with open(self.tree.path("scripts/blob.js"), "wb") as f:
            f.write(b"\xff\xfe")
        self.tree.add()
        code, out = run(self.tree.root)
        self.assertEqual(code, 0, out)

    def test_malformed_plugin_json(self):
        self.tree.write(".claude-plugin/plugin.json", "{")
        self.assertFailsNaming(".claude-plugin:")

    def test_marketplace_does_not_offer_the_plugin(self):
        self.tree.write(".claude-plugin/marketplace.json", json.dumps({"name": "m", "plugins": []}))
        self.assertFailsNaming("marketplace.json: must offer plugin 'motir'")

    def test_mcp_servers_not_an_object(self):
        self.tree.edit_plugin(lambda p: p.update(mcpServers={"motir": "https://app.motir.co/api/mcp"}))
        self.assertFailsNaming("mcpServers.motir must be declared as an object")

    def test_mcp_server_missing(self):
        self.tree.edit_plugin(lambda p: p.pop("mcpServers"))
        self.assertFailsNaming("mcpServers.motir must be declared as an object")

    def test_mcp_type_not_http(self):
        self.tree.edit_plugin(lambda p: p["mcpServers"]["motir"].update(type="sse"))
        self.assertFailsNaming("mcpServers.motir.type is 'sse'")

    def test_string_component_path_outside_root(self):
        self.tree.edit_plugin(lambda p: p.update(commands="../commands"))
        self.assertFailsNaming("component path '../commands' is outside the plugin root")

    def test_missing_readme(self):
        os.remove(self.tree.path("README.md"))
        self.tree.add()
        self.assertFailsNaming("README.md: missing")

    def test_missing_runner(self):
        os.remove(self.tree.path("scripts/motir"))
        self.tree.add()
        self.assertFailsNaming("scripts/motir: missing")

    def test_no_skill_folders(self):
        shutil.rmtree(self.tree.path("skills"))
        os.makedirs(self.tree.path("skills"))
        self.tree.add()
        self.assertFailsNaming("skills/: no skill folders")


class NpmViewTest(unittest.TestCase):
    def test_npm_not_on_path(self):
        real = os.environ.get("PATH", "")
        os.environ["PATH"] = tempfile.mkdtemp()
        try:
            code, out = validate.npm_view("@motir/cli")
        finally:
            os.environ["PATH"] = real
        self.assertEqual(code, 1)
        self.assertTrue(out)

    def test_script_entry_point_exits_with_main(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                runpy.run_path(os.path.join(HERE, "validate.py"), run_name="__main__")
        self.assertIn(raised.exception.code, (0, 1))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
