#!/usr/bin/env python3
"""Pins the definition of "a section's text" in section-hash.py. Standard library only."""

import hashlib
import importlib.util
import os
import sys

spec = importlib.util.spec_from_file_location(
    "section_hash", os.path.join(os.path.dirname(os.path.abspath(__file__)), "section-hash.py")
)
sh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sh)

DOC = """# Title

intro

## `motir run` — the first

one
```sh
# a shell comment, not a heading
## nor this
```
### a subsection stays inside

## Second

two


# Another top
"""

failures = []


def check(name, got, want):
    if got != want:
        failures.append(f"{name}:\n  got  {got!r}\n  want {want!r}")


check(
    "a section runs to the next heading of the same level, through fences and deeper headings",
    sh.section(DOC, "`motir run` — the first"),
    "## `motir run` — the first\n\none\n```sh\n# a shell comment, not a heading\n## nor this\n```\n"
    "### a subsection stays inside",
)
check("trailing blank lines are dropped", sh.section(DOC, "Second"), "## Second\n\ntwo")
check("a top-level section ends at the next top-level heading", sh.section(DOC, "Title").split("\n")[-1], "two")
check("the last section runs to the end of the file", sh.section(DOC, "Another top"), "# Another top")
check(
    "the hash is sha256 of the normalised text",
    sh.digest(DOC, "Second"),
    hashlib.sha256("## Second\n\ntwo".encode("utf-8")).hexdigest(),
)
check(
    "trailing whitespace on a line does not change the hash",
    sh.digest(DOC.replace("two\n", "two  \t\n"), "Second"),
    sh.digest(DOC, "Second"),
)
for missing in ("Nope", "nor this", "a shell comment, not a heading"):
    try:
        sh.section(DOC, missing)
        failures.append(f"{missing!r} should not match a heading")
    except LookupError:
        pass
try:
    sh.section(DOC + "\n## Second\n", "Second")
    failures.append("a heading that appears twice must be refused")
except LookupError:
    pass

for f in failures:
    print(f"✘ {f}")
print("✔ section-hash definition holds" if not failures else f"{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
