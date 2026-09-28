#!/usr/bin/env python3
"""The ONE definition of "a section's text" — shared by this repository and the runbook it condenses.

Each skill's standalone procedure condenses sections of a Markdown corpus, and records in its
`SYNC.json` which sections, and what they said, when it was last written. This script is how
both sides compute that record, so the two can never disagree about what "the section" means.

A SECTION is an ATX heading line (`#` .. `######`, followed by a space) and every line after it,
up to — not including — the next heading of the SAME OR A HIGHER level (fewer or equal `#`s), or
the end of the file. Lines inside fenced code blocks (``` or ~~~) are never headings, so a shell
comment in a code sample does not end a section. A heading is matched by its TEXT: the line with
its leading `#`s and the following whitespace removed, and trailing whitespace stripped. It must
match exactly one heading in the file.

The HASH is the SHA-256 hex digest of the section's lines, each with trailing whitespace
stripped, trailing blank lines dropped, joined with "\\n", encoded as UTF-8. Whitespace at a line's
END is invisible in review and editors disagree about it, so it is not part of the text.

Usage:
  section-hash.py <file|-> <heading>            print the section's hash
  section-hash.py --show <file|-> <heading>     print the section's text
  section-hash.py --verify <runbook-checkout> [--ref <git-ref>] <SYNC.json>...
      re-hash every entry of every SYNC.json against the runbook at <git-ref>
      (default `origin/main`) and exit 1 naming each entry that no longer matches.
  section-hash.py --update <runbook-checkout> [--ref <git-ref>] <SYNC.json>...
      the same, but REWRITE each `sha256` to the value at <git-ref>. Run it only after the
      standalone procedure has been re-read against those sections and brought up to date:
      the hash records what the procedure was written against, not merely what exists today.

Standard library only.
"""

import hashlib
import json
import re
import subprocess
import sys

HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")
FENCE = re.compile(r"^ {0,3}(```|~~~)")


def headings(lines):
    """Yield (index, level, text) for every heading outside a fenced code block."""
    fence = None
    for i, line in enumerate(lines):
        m = FENCE.match(line)
        if m:
            if fence is None:
                fence = m.group(1)
            elif m.group(1) == fence:
                fence = None
            continue
        if fence is not None:
            continue
        h = HEADING.match(line)
        if h:
            yield i, len(h.group(1)), h.group(2)


def section(text, heading):
    """Return the section's normalised text. Raises LookupError unless exactly one heading matches."""
    lines = text.split("\n")
    found = list(headings(lines))
    matches = [(i, level) for i, level, t in found if t == heading.strip()]
    if len(matches) != 1:
        raise LookupError(f"{len(matches)} headings match {heading!r} (need exactly one)")
    start, level = matches[0]
    end = next((i for i, lv, _ in found if i > start and lv <= level), len(lines))
    body = [line.rstrip() for line in lines[start:end]]
    while body and body[-1] == "":
        body.pop()
    return "\n".join(body)


def digest(text, heading):
    return hashlib.sha256(section(text, heading).encode("utf-8")).hexdigest()


def read(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def verify(checkout, ref, sync_files, update=False):
    """Re-hash every SYNC.json entry against <checkout> at <ref>. Returns the number of mismatches
    (with `update`, rewrites the drifted hashes and returns the number of missing sections only)."""
    bad = 0
    cache = {}
    for sync_file in sync_files:
        with open(sync_file, encoding="utf-8") as f:
            entries = json.load(f)
        for entry in entries:
            path, heading, want = entry["corpusPath"], entry["heading"], entry["sha256"]
            if path not in cache:
                cache[path] = subprocess.run(
                    ["git", "-C", checkout, "show", f"{ref}:{path}"],
                    check=True, capture_output=True, text=True,
                ).stdout
            try:
                got = digest(cache[path], heading)
            except LookupError as e:
                print(f"MISSING  {sync_file}: {path} § {heading} — {e}")
                bad += 1
                continue
            if got == want:
                print(f"ok       {sync_file}: {path} § {heading}")
            elif update:
                entry["sha256"] = got
                print(f"UPDATED  {sync_file}: {path} § {heading}")
            else:
                print(f"DRIFTED  {sync_file}: {path} § {heading}\n         recorded {want}\n         at {ref}  {got}")
                bad += 1
        if update:
            with open(sync_file, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
                f.write("\n")
    return bad


def main(argv):
    if len(argv) >= 2 and argv[0] in ("--verify", "--update"):
        update = argv[0] == "--update"
        checkout, rest, ref = argv[1], argv[2:], "origin/main"
        if len(rest) >= 2 and rest[0] == "--ref":
            ref, rest = rest[1], rest[2:]
        if not rest:
            print(__doc__, file=sys.stderr)
            return 2
        return 1 if verify(checkout, ref, rest, update) else 0
    show = bool(argv) and argv[0] == "--show"
    if show:
        argv = argv[1:]
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        text = read(argv[0])
        print(section(text, argv[1]) if show else digest(text, argv[1]))
    except LookupError as e:
        print(f"section-hash: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
