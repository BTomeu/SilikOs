#!/usr/bin/env python3
# cache_check.py DIR...: is a build that the Actions cache gave back one this repository already vouches for?
#
# The workflows EDA tools and Wine keep a finished build in the Actions cache under a key made of its recipe, so that
# hours of building are not repeated. A cache entry is not tied to who wrote it: every job that runs for main, in any
# workflow, with a read-only token, can save an entry under any key that is still free, and an entry is never
# replaced. A job that runs upstream's build code (or a step of ours that went wrong) could so leave a package under
# the key of another tool's next recipe; a later run would restore it, try it, keep it in a release and attest it as
# its own build (the audit of 13/11/2026, S8).
#
# So a restored build is used only when every package (*.rpm) of it is, byte for byte, a file that a release of this
# repository holds under the same name: an earlier run built it, tried it and kept it there with a token that
# writes, which no build job has. GitHub gives each release file's sha256 (the API's "digest"). Anything else (a file
# no release holds, another digest, a release file without a digest, an API that does not answer) and the folders
# are emptied and the build runs again: slower, never wrong. A build whose trial failed was never kept, so it is
# built again each run until its recipe changes: the price of not trusting the cache.
#
# Prints what it found; writes ok=true or ok=false to $GITHUB_OUTPUT. Always exits 0 (the answer is the output).
# Needs GITHUB_REPOSITORY; GH_TOKEN (the run's read-only token) when there is one; GITHUB_API_URL for another server.
import glob
import hashlib
import json
import os
import shutil
import sys
import urllib.error
import urllib.request


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def released(repo, api, token, fetch=None):
    """{file name: {sha256, ...}} of every file of every release of REPO; raises when the API does not answer"""
    out = {}
    for page in range(1, 21):
        url = "%s/repos/%s/releases?per_page=100&page=%d" % (api.rstrip("/"), repo, page)
        if fetch:
            data = fetch(url)
        else:
            req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "cache-check"})
            if token:
                req.add_header("Authorization", "Bearer " + token)
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
        if not isinstance(data, list):
            raise ValueError("the releases are not a list")
        for rel in data:
            for a in rel.get("assets") or []:
                d = a.get("digest") or ""
                if isinstance(d, str) and d.startswith("sha256:") and isinstance(a.get("name"), str):
                    out.setdefault(a["name"], set()).add(d[len("sha256:"):].lower())
        if len(data) < 100:
            return out
    raise ValueError("more than 2000 releases")


def judge(files, have):
    """files: {path: sha256}; have: released(). -> [(path, why)] of the files no release vouches for"""
    bad = []
    for path, digest in sorted(files.items()):
        known = have.get(os.path.basename(path))
        if not known:
            bad.append((path, "no release holds a file of this name"))
        elif digest not in known:
            bad.append((path, "the release's file of this name has other contents"))
    return bad


def main(argv, fetch=None):
    dirs = argv[1:]
    if not dirs:
        sys.stderr.write("usage: tools/cache_check.py DIR...\n")
        return 2
    # the packages are what a later step takes from these folders (build/extra/NAME-*.rpm, build/srpm/*.src.rpm);
    # a link is never a package
    files = {}
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "**", "*.rpm"), recursive=True)):
            files[path] = "a link" if os.path.islink(path) or not os.path.isfile(path) else sha256(path)
    ok, why = False, ""
    if not files:
        why = "the cache gave no package"
    else:
        try:
            have = released(os.environ["GITHUB_REPOSITORY"], os.environ.get("GITHUB_API_URL") or "https://api.github.com",
                            os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "", fetch)
            bad = judge(files, have)
            ok = not bad
            for path, reason in bad[:20]:
                print("not vouched for: %s (%s)" % (path, reason))
            why = "%d of %d files are not a release's own" % (len(bad), len(files)) if bad else ""
        except (KeyError, OSError, ValueError, urllib.error.URLError) as e:
            why = "the releases could not be read (%s: %s)" % (type(e).__name__, e)
    if ok:
        print("the kept build is used: its %d files are the releases' own, byte for byte" % len(files))
    else:
        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)
        print("::warning title=kept build not used::%s: it is built again (tools/cache_check.py)" % why)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write("ok=%s\n" % ("true" if ok else "false"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
