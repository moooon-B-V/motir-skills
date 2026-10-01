#!/usr/bin/env python3
"""validate.py's MCP-entry, directory-shape, runner-pin, listing and credential-name checks: each defect
fails naming its path, and the repository itself passes. Every case copies the repository into a temporary
git tree, plants ONE defect and runs validate.main() over it. Standard library only."""

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
PLUGIN = "plugins/motir"


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
        rel = PLUGIN + "/.claude-plugin/plugin.json"
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
        self.tree.write(PLUGIN + "/bin/motir", "#!/bin/sh\n")
        self.assertFailsNaming(PLUGIN + "/bin/: a bin/ at the plugin's root")

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
        os.remove(self.tree.path(PLUGIN + "/LICENSE"))
        self.tree.add()
        self.assertFailsNaming(PLUGIN + "/LICENSE: missing")

    def test_short_readme(self):
        self.tree.write(PLUGIN + "/README.md", " ".join(["word"] * 39) + "\n")
        self.assertFailsNaming(PLUGIN + "/README.md: 39 words")

    def test_long_js_line(self):
        self.tree.write("scripts/tool.js", "x" * 2001 + "\n")
        self.assertFailsNaming("scripts/tool.js:1")

    def test_component_path_outside_root(self):
        self.tree.edit_plugin(lambda p: p["skills"].append("../elsewhere"))
        self.assertFailsNaming("../elsewhere")

    def test_runner_not_executable(self):
        subprocess.run(["git", "-C", self.tree.root, "update-index", "--chmod=-x", PLUGIN + "/scripts/motir"], check=True)
        self.assertFailsNaming("scripts/motir: must be committed executable")

    def test_runner_two_pins(self):
        rel = PLUGIN + "/scripts/motir"
        self.tree.write(rel, read(self.tree.path(rel)) + 'MOTIR_CLI_VERSION="0.8.0"\n')
        self.assertFailsNaming("scripts/motir: needs exactly one MOTIR_CLI_VERSION")

    def test_runner_unpublished_pin(self):
        validate.npm_view = lambda spec: (1, "") if spec.endswith("@0.8.99") else (0, "0.9.0")
        self.set_pin("0.8.99")
        self.assertFailsNaming("scripts/motir: MOTIR_CLI_VERSION 0.8.99 is not a published version")

    def test_registry_unreachable(self):
        validate.npm_view = lambda spec: (1, "getaddrinfo ENOTFOUND registry.npmjs.org")
        self.assertFailsNaming("scripts/motir: could not check MOTIR_CLI_VERSION 0.8.0 — the npm registry is unreachable")

    def set_pin(self, version):
        rel = PLUGIN + "/scripts/motir"
        text = re.sub(r'^MOTIR_CLI_VERSION=.*$', f'MOTIR_CLI_VERSION="{version}"', read(self.tree.path(rel)), flags=re.M)
        with open(self.tree.path(rel), "w", encoding="utf-8") as f:
            f.write(text)
        self.tree.add()


class EveryCheckFailsTest(TreeCase):
    """The failure branches of the other checks, one planted defect each."""

    SKILL = PLUGIN + "/skills/motir-run/SKILL.md"
    SYNC = PLUGIN + "/skills/motir-run/SYNC.json"

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
        os.rename(self.tree.path(PLUGIN + "/skills/motir-mark"), self.tree.path(PLUGIN + "/skills/Motir_Mark"))
        self.tree.write(PLUGIN + "/skills/Motir_Mark/SKILL.md", self.frontmatter(name="Motir_Mark"))
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
        self.tree.write(PLUGIN + "/.claude-plugin/plugin.json", "{")
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
        os.remove(self.tree.path(PLUGIN + "/README.md"))
        self.tree.add()
        self.assertFailsNaming(PLUGIN + "/README.md: missing")

    def test_missing_runner(self):
        os.remove(self.tree.path(PLUGIN + "/scripts/motir"))
        self.tree.add()
        self.assertFailsNaming("scripts/motir: missing")

    def test_no_skill_folders(self):
        shutil.rmtree(self.tree.path(PLUGIN + "/skills"))
        os.makedirs(self.tree.path(PLUGIN + "/skills"))
        self.tree.add()
        self.assertFailsNaming("skills/: no skill folders")


def png(width, height):
    """The bytes of a PNG header declaring width x height — all `image_size` reads."""
    return (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + width.to_bytes(4, "big")
            + height.to_bytes(4, "big") + b"\x08\x06\x00\x00\x00")


def jpeg(width, height, sof=True):
    """The bytes of a JPEG: an APP0 segment, then (optionally) a baseline SOF0 declaring width x height."""
    app0 = b"\xff\xe0" + (16).to_bytes(2, "big") + b"JFIF\x00" + b"\x00" * 9
    frame = b"\xff\xc0" + (17).to_bytes(2, "big") + b"\x08" + height.to_bytes(2, "big") + width.to_bytes(2, "big")
    return b"\xff\xd8" + app0 + (frame + b"\x00" * 12 if sof else b"\xff\xd9")


class ListingTest(TreeCase):
    """`check_listing`: the icon and privacy policy URL Claude's plugin directory asks for."""

    ICON = PLUGIN + "/.claude-plugin/icon.png"

    def write_bytes(self, rel, data):
        with open(self.tree.path(rel), "wb") as f:
            f.write(data)
        self.tree.add()

    def test_shipped_icon_is_a_square_png_in_range(self):
        kind, width, height = validate.image_size(os.path.join(REPO, self.ICON))
        self.assertEqual((kind, width), ("png", height))
        self.assertTrue(512 <= width <= 2048)
        self.assertLess(os.path.getsize(os.path.join(REPO, self.ICON)), 2 * 1024 * 1024)

    def test_no_icon(self):
        self.tree.edit_plugin(lambda p: p.pop("icon"))
        self.assertFailsNaming("icon must name a square PNG or JPEG")

    def test_icon_file_missing(self):
        os.remove(self.tree.path(self.ICON))
        self.tree.add()
        self.assertFailsNaming("the icon plugin.json names does not exist")

    def test_icon_outside_root(self):
        self.tree.edit_plugin(lambda p: p.update(icon="../icon.png"))
        self.assertFailsNaming("icon '../icon.png' is outside the plugin root")

    def test_icon_not_square(self):
        self.write_bytes(self.ICON, png(512, 600))
        self.assertFailsNaming("512x600, must be square")

    def test_icon_too_small(self):
        self.write_bytes(self.ICON, png(256, 256))
        self.assertFailsNaming("256x256, must be square and 512 to 2048 px")

    def test_icon_too_large(self):
        self.write_bytes(self.ICON, png(4096, 4096))
        self.assertFailsNaming("4096x4096")

    def test_icon_over_two_megabytes(self):
        self.write_bytes(self.ICON, png(512, 512) + b"\x00" * (2 * 1024 * 1024))
        self.assertFailsNaming("must be under 2097152")

    def test_icon_not_an_image(self):
        self.write_bytes(self.ICON, b"<svg xmlns='http://www.w3.org/2000/svg'/>")
        self.assertFailsNaming("not a PNG or JPEG")

    def test_jpeg_icon_passes(self):
        os.remove(self.tree.path(self.ICON))
        self.write_bytes(PLUGIN + "/.claude-plugin/icon.jpg", jpeg(1024, 1024))
        self.tree.edit_plugin(lambda p: p.update(icon=".claude-plugin/icon.jpg"))
        code, out = run(self.tree.root)
        self.assertEqual(code, 0, out)

    def test_jpeg_without_a_frame_is_not_an_image(self):
        self.write_bytes(PLUGIN + "/.claude-plugin/icon.jpg", jpeg(1024, 1024, sof=False))
        self.tree.edit_plugin(lambda p: p.update(icon=".claude-plugin/icon.jpg"))
        self.assertFailsNaming("not a PNG or JPEG")

    def test_no_privacy_policy_url(self):
        self.tree.edit_plugin(lambda p: p.pop("privacyPolicyUrl"))
        self.assertFailsNaming("privacyPolicyUrl must be an https URL")

    def test_plain_http_privacy_policy_url(self):
        self.tree.edit_plugin(lambda p: p.update(privacyPolicyUrl="http://motir.co/legal/privacy"))
        self.assertFailsNaming("privacyPolicyUrl must be an https URL")

    def test_no_terms_of_service_url(self):
        self.tree.edit_plugin(lambda p: p.pop("termsOfServiceUrl"))
        self.assertFailsNaming("termsOfServiceUrl must be an https URL")

    def test_plain_http_terms_of_service_url(self):
        self.tree.edit_plugin(lambda p: p.update(termsOfServiceUrl="http://motir.co/legal/terms"))
        self.assertFailsNaming("termsOfServiceUrl must be an https URL")

    def test_malformed_plugin_json_is_named_once(self):
        self.tree.write(PLUGIN + "/.claude-plugin/plugin.json", "{")
        code, out = run(self.tree.root)
        self.assertEqual(code, 1, out)
        self.assertNotIn("privacyPolicyUrl", out)
        self.assertNotIn("termsOfServiceUrl", out)


class CredentialNameTest(TreeCase):
    """`check_credential_names`: inside the plugin, a variable or function the directory's scanner reads as a
    credential fails, naming the line; the repository's own tooling outside the plugin is not scanned.
    Lines are planted in the plugin's README, which the bundle allows, and the planted names are assembled
    from pieces so this file does not itself carry one."""

    D = "$"
    README = PLUGIN + "/README.md"

    def plant(self, text):
        self.tree.write(self.README, read(self.tree.path(self.README)) + text)
        return len(read(self.tree.path(self.README)).split("\n")) - 1

    def test_working_directory_reference(self):
        n = self.plant('d="' + self.D + 'PWD"\n')
        self.assertFailsNaming(f"{self.README}:{n}: variable PWD reads as a credential (PWD)")

    def test_braced_reference(self):
        n = self.plant("curl -H " + self.D + "{MOTIR_" + "TOKEN} https://app.motir.co\n")
        self.assertFailsNaming(f"{self.README}:{n}: variable MOTIR_TOKEN reads as a credential (TOKEN)")

    def test_assignment(self):
        n = self.plant("PIN" + "=$(cat scripts/motir)\n")
        self.assertFailsNaming(f"{self.README}:{n}: variable PIN reads as a credential (PIN)")

    def test_exported_assignment(self):
        n = self.plant("export API_" + "KEY=abc\n")
        self.assertFailsNaming(f"{self.README}:{n}: variable API_KEY reads as a credential (KEY)")

    def test_function_named_pass(self):
        n = self.plant("pa" + 'ss() { echo "ok $1"; }\n')
        self.assertFailsNaming(f"{self.README}:{n}: function pass reads as a credential (pass)")

    def test_function_keyword_form(self):
        n = self.plant("function get_" + "token {\n")
        self.assertFailsNaming(f"{self.README}:{n}: function get_token reads as a credential (token)")

    def test_two_references_on_one_line_are_named_once(self):
        n = self.plant("echo " + self.D + "PIN " + self.D + "PIN\n")
        code, out = run(self.tree.root)
        self.assertEqual(code, 1, out)
        self.assertEqual(out.count(f"{self.README}:{n}: variable PIN"), 1, out)

    def test_plain_names_pass(self):
        self.plant("CLI_VERSION=1\necho " + self.D + "CHECKOUT " + self.D + "(pwd)\n"
                   + "PINNED=1; KEYS=2\nkey=3\nok() { :; }\n")
        code, out = run(self.tree.root)
        self.assertEqual(code, 0, out)

    def test_tooling_outside_the_plugin_is_not_scanned(self):
        self.tree.write("scripts/x.sh", "pa" + "ss() { :; }\n" + "PIN" + "=1\n")
        code, out = run(self.tree.root)
        self.assertEqual(code, 0, out)


class BundleTest(TreeCase):
    """`check_bundle` and the marketplace source: the plugin folder ships only what a user runs."""

    def test_a_test_file_in_the_plugin_fails(self):
        self.tree.write(PLUGIN + "/scripts/test_motir.py", "print(1)\n")
        self.assertFailsNaming(PLUGIN + "/scripts/test_motir.py: does not belong in the plugin")

    def test_an_extra_file_in_a_skill_fails(self):
        self.tree.write(PLUGIN + "/skills/motir-run/notes.md", "notes\n")
        self.assertFailsNaming(PLUGIN + "/skills/motir-run/notes.md: does not belong in the plugin")

    def test_an_icon_the_manifest_does_not_name_fails(self):
        self.tree.write(PLUGIN + "/.claude-plugin/old-icon.png", "x")
        self.assertFailsNaming(PLUGIN + "/.claude-plugin/old-icon.png: does not belong in the plugin")

    def test_files_beside_the_plugin_are_fine(self):
        self.tree.write("plugins/README.md", "about the plugins folder\n")
        code, out = run(self.tree.root)
        self.assertEqual(code, 0, out)

    def test_marketplace_offering_the_repository_root_fails(self):
        rel = ".claude-plugin/marketplace.json"
        market = json.loads(read(self.tree.path(rel)))
        market["plugins"][0]["source"] = "./"
        self.tree.write(rel, json.dumps(market))
        self.assertFailsNaming("marketplace.json: must offer plugin 'motir' once, with source './plugins/motir'")


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
