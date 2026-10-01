#!/usr/bin/env python3
"""The plugin's runner (plugins/motir/scripts/motir), driven with stub `node` / `npx` executables on a PATH of their own: no Node refuses
in one line, Node below 22 refuses without running npx, and Node 22 hands npx the pinned package plus
every argument verbatim and returns its exit code. Standard library only."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

RUNNER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins", "motir", "scripts", "motir")
SH = shutil.which("sh")
with open(RUNNER, encoding="utf-8") as _f:
    CLI_VERSION = re.search(r'^MOTIR_CLI_VERSION="([^"]+)"', _f.read(), re.M).group(1)


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.bin = tempfile.mkdtemp(prefix="motir-runner-")
        self.addCleanup(shutil.rmtree, self.bin, True)
        self.argv_file = os.path.join(self.bin, "npx.argv")

    def stub(self, name, body):
        path = os.path.join(self.bin, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"#!{SH}\n{body}\n")
        os.chmod(path, 0o755)

    def node(self, version):
        self.stub("node", f"echo {version}")

    def npx(self, code):
        # One argument per line, so an argument containing a space stays one line.
        self.stub("npx", f"for a in \"$@\"; do printf '%s\\n' \"$a\"; done > '{self.argv_file}'\nexit {code}")

    def run_motir(self, *args):
        return subprocess.run([SH, RUNNER, *args], capture_output=True, text=True, env={"PATH": self.bin})

    def test_no_node(self):
        self.npx(0)
        done = self.run_motir("--version")
        self.assertEqual(done.returncode, 127)
        lines = done.stderr.splitlines()
        self.assertEqual(len(lines), 1, done.stderr)
        self.assertIn("Node.js 22", lines[0])
        self.assertFalse(os.path.exists(self.argv_file), "npx ran without Node")

    def test_old_node(self):
        self.node("20.11.0")
        self.npx(0)
        done = self.run_motir("--version")
        self.assertEqual(done.returncode, 1)
        lines = done.stderr.splitlines()
        self.assertEqual(len(lines), 1, done.stderr)
        self.assertIn("20.11.0", lines[0])
        self.assertFalse(os.path.exists(self.argv_file), "npx ran on Node 20")

    def test_node_22_passes_arguments_and_exit_code(self):
        self.node("22.3.0")
        self.npx(3)
        done = self.run_motir("run", "a b", "--flag")
        self.assertEqual(done.returncode, 3, done.stderr)
        with open(self.argv_file, encoding="utf-8") as f:
            argv = f.read().split("\n")[:-1]
        self.assertEqual(argv, ["--yes", f"@motir/cli@{CLI_VERSION}", "run", "a b", "--flag"])


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)
