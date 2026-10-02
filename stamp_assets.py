"""Version the site's stylesheet and script links by what the files hold.

GitHub Pages lets a browser cache a file for ten minutes, so a freshly deployed
page can arrive with the stylesheet it replaced and render against rules that
are no longer there. Each local `.css` or `.js` link therefore carries
`?v=<hash>` of the file it points at: any change to the file is a new address;
an unchanged file keeps its address and its cache.

**The hash is of the content, line endings normalised.** CRLF is read as LF
before hashing, so a Windows checkout and the LF blob GitHub serves agree and a
run on another machine does not rewrite every page.

**Local links only.** A link that names a scheme, starts `//` or is
root-absolute is somebody else's file or a path this page cannot resolve, so
it is left exactly as written.

Idempotent: a page whose links already carry the current hashes is left alone
rather than rewritten; each page's line endings are kept byte for byte. A
link to a file that does not exist stops the run before any page is written.
Run it from the repository root, else let a build script call `main()`.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SITE_DIR = ROOT / "docs"
PAGE_PATTERN = "**/*.html"
HASH_LENGTH = 10
QUERY_KEY = "v"
ASSET_LINK = re.compile(
    r'(?P<attr>\b(?:href|src))="(?P<path>[^"?#]+\.(?:css|js))'
    r'(?:\?[^"#]*)?(?P<fragment>#[^"]*)?"'
)
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


class MissingAsset(Exception):
    """A page links a local stylesheet or script that is not on disk."""


def is_local(link: str) -> bool:
    """True for a path relative to the page; False for anything off-site."""
    return not (link.startswith("/") or SCHEME.match(link))


def content_hash(path: pathlib.Path) -> str:
    """The short hash of a file's bytes with CRLF read as LF."""
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()[:HASH_LENGTH]


def versioned(page: pathlib.Path, text: str, hashes: dict[pathlib.Path, str]) -> str:
    """This page's text with every local asset link carrying its hash."""

    def replace(match: re.Match[str]) -> str:
        link = match.group("path")
        if not is_local(link):
            return match.group(0)
        target = (page.parent / link).resolve()
        if target not in hashes:
            if not target.is_file():
                raise MissingAsset(f"{page.relative_to(ROOT)} links {link}: {target}")
            hashes[target] = content_hash(target)
        fragment = match.group("fragment") or ""
        return f'{match.group("attr")}="{link}?{QUERY_KEY}={hashes[target]}{fragment}"'

    return ASSET_LINK.sub(replace, text)


def main() -> int:
    """Version the whole site, saying which pages were actually touched."""
    if not SITE_DIR.is_dir():
        print(f"no site at {SITE_DIR}, nothing to stamp")
        return 0
    hashes: dict[pathlib.Path, str] = {}
    pending: list[tuple[pathlib.Path, bytes]] = []
    try:
        for page in sorted(SITE_DIR.glob(PAGE_PATTERN)):
            text = page.read_bytes().decode("utf-8")
            stamped = versioned(page, text, hashes)
            if stamped != text:
                pending.append((page, stamped.encode("utf-8")))
    except MissingAsset as missing:
        print(f"missing asset, nothing stamped: {missing}", file=sys.stderr)
        return 1
    if not pending:
        print("site assets already versioned")
        return 0
    print("stamped asset versions into:")
    for page, data in pending:
        page.write_bytes(data)
        print(f"  {page.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
