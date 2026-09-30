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


class ValidateTest(unittest.TestCase):
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


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
