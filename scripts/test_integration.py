#!/usr/bin/env python3
"""The story's integration gate over the assembled tree: the seams between the runner, the README and
validate.py, read against the REAL npm registry and the pinned Claude Code — where each check's own
unit tests only ever see their own fixture. Standard library only."""

import ast
import json
import os
import re
import subprocess
import sys
import unittest

from test_validate import PLUGIN, REPO, Tree, published, read, run, validate

CLAUDE_CODE = "@anthropic-ai/claude-code@2.1.283"


class PinSeam(unittest.TestCase):
    """The pin the runner actually carries is the one validate.py reads and asks npm about."""

    def setUp(self):
        self.tree = Tree()
        self.addCleanup(self.tree.cleanup)

    def test_real_runner_passes(self):
        code, out = run(self.tree.root)
        self.assertEqual(code, 0, out)

    def test_unpublished_pin_fails_naming_the_runner(self):
        rel = PLUGIN + "/scripts/motir"
        text = read(self.tree.path(rel))
        edited = re.sub(r'^MOTIR_CLI_VERSION=.*$', 'MOTIR_CLI_VERSION="0.8.99"', text, count=1, flags=re.M)
        self.assertNotEqual(edited, text, "the runner's pin line did not match the reader's syntax")
        self.tree.write(rel, edited)
        code, out = run(self.tree.root)
        self.assertEqual(code, 1, out)
        self.assertIn(f"✘ {PLUGIN}/scripts/motir: MOTIR_CLI_VERSION 0.8.99 is not a published version", out)


class ReadmeSecretSeam(unittest.TestCase):
    """The README's PAT example is a placeholder the secret check would catch if it became a token."""

    def setUp(self):
        self.tree = Tree()
        self.addCleanup(self.tree.cleanup)
        real, validate.npm_view = validate.npm_view, published
        self.addCleanup(setattr, validate, "npm_view", real)

    def test_placeholder_passes_and_a_token_fails(self):
        readme = read(self.tree.path("README.md"))
        self.assertIn("<your-token>", readme)
        code, out = run(self.tree.root)
        self.assertEqual(code, 0, out)
        self.tree.write("README.md", readme.replace("<your-token>", "mtr_" + "abcdefghijklmnopqrst"))
        code, out = run(self.tree.root)
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"✘ README\.md:\d+: secret-shaped string")


class DocstringMatchesMain(unittest.TestCase):
    """Two pull requests added checks to one file: its docstring and main() still agree."""

    def test_every_documented_check_runs_once_and_every_check_is_documented(self):
        source = read(os.path.join(REPO, "scripts", "validate.py"))
        tree = ast.parse(source)
        documented = set(re.findall(r"^\d+\. `(check_\w+)` — ", ast.get_docstring(tree), re.M))
        defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("check_")}
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        called = [
            n.func.id for n in ast.walk(main)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id.startswith("check_")
        ]
        self.assertEqual(documented, defined)
        self.assertEqual(sorted(called), sorted(defined), "each check_* must be called exactly once in main()")


class StandardLibraryOnly(unittest.TestCase):
    """The scripts' own contract: they run on a bare python3."""

    def test_imports(self):
        for rel in ("scripts/validate.py", "scripts/section-hash.py"):
            tree = ast.parse(read(os.path.join(REPO, rel)))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module]
                else:
                    continue
                for name in names:
                    self.assertIn(name.split(".")[0], sys.stdlib_module_names, f"{rel} imports {name}")


class ClaudeCodeStrict(unittest.TestCase):
    """The pinned Claude Code reports nothing at all — no errors and no warnings — on the real tree."""

    def test_zero_errors_and_warnings(self):
        for target in (".", PLUGIN, PLUGIN + "/.claude-plugin/plugin.json"):
            done = subprocess.run(
                ["npx", "--yes", CLAUDE_CODE, "plugin", "validate", target, "--strict", "--json"],
                cwd=REPO, capture_output=True, text=True,
            )
            report = json.loads(done.stdout)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertTrue(report["success"], report)
            for part in [report["manifest"], *report.get("contents", [])]:
                self.assertEqual(part.get("errors", []), [], f"{target}: {part}")
                self.assertEqual(part.get("warnings", []), [], f"{target}: {part}")


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
