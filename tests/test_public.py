#!/usr/bin/env python3
# The repository as a public one (docs/PUBLIC.md): what the workflows may do when a stranger's pull request starts
# them, and what the tree must not hold. The workflows are read as text (the base's Python has no YAML module):
# their `run:` scripts are taken by indentation.
import glob
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOWS = sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml")))
SKIP_DIRS = {".git", "build", "__pycache__", ".claude"}


def text(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:      # (an absolute path is taken as it is)
        return f.read()


def run_scripts(s):
    """[(line number, script)] of every `run:` of a workflow's text"""
    lines = s.split("\n")
    out = []
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)(- )?run: ?(.*)$", lines[i])
        if not m:
            i += 1
            continue
        indent = len(m.group(1)) + (2 if m.group(2) else 0)
        value = m.group(3)
        if value.strip() in ("|", "|-", "|+", ">", ">-"):
            body = []
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > indent):
                body.append(lines[j])
                j += 1
            out.append((i + 1, "\n".join(body)))
            i = j
        else:
            out.append((i + 1, value))
            i += 1
    return out


def jobs(s):
    """{job name: its text} of a workflow's text"""
    body = s.split("\njobs:\n", 1)[1]
    out = {}
    name = None
    for line in body.split("\n"):
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m:
            name = m.group(1)
            out[name] = ""
        elif name:
            out[name] += line + "\n"
    return out


def tree_files():
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            yield os.path.join(d, f)


class Workflows(unittest.TestCase):
    def test_there_are_workflows_and_their_scripts_are_found(self):
        self.assertGreaterEqual(len(WORKFLOWS), 5)
        for wf in WORKFLOWS:
            self.assertTrue(run_scripts(text(wf)), wf)
            self.assertTrue(jobs(text(wf)), wf)

    def test_no_workflow_runs_a_fork_s_code_with_the_repository_s_rights(self):
        for wf in WORKFLOWS:
            s = text(wf)
            self.assertNotIn("pull_request_target", s, wf)
            if os.path.basename(wf) != "repo.yml":       # (the package repository's signing key: the tests below)
                self.assertNotIn("secrets.", s, wf)      # (nothing but the run's own token is used)

    def test_the_signing_key_is_seen_by_one_step_that_no_stranger_starts(self):
        # .github/workflows/repo.yml: the two secrets of the package signing key (docs/REPO.md)
        s = text(".github/workflows/repo.yml")
        head = s.split("\njobs:\n", 1)[0]
        self.assertNotRegex(head, r"(?m)^  pull_request")                  # no pull request starts it
        self.assertEqual(sorted(set(re.findall(r"secrets\.([A-Za-z_]+)", s.split("\nname: ", 1)[1]))),
                         ["SILIKOS_GPG_PASSPHRASE", "SILIKOS_GPG_PRIVATE_KEY"])
        j = jobs(s)
        for name, body in j.items():
            self.assertEqual("secrets." in body, name == "packages", name)
        job = j["packages"]
        self.assertNotIn(": write", job)                                   # the job with the key writes nothing
        self.assertRegex(job, r"(?m)^    environment: package-signing$")   # the key is that environment's, not the repository's
        self.assertEqual(s.count("environment: package-signing"), 1)
        cond = re.search(r"^    if: (.*)$", job, re.M).group(1)
        for must in ("github.event.workflow_run.conclusion == 'success'", "github.event.workflow_run.event != 'pull_request'",
                     "github.event.workflow_run.head_repository.full_name == github.repository", "github.ref == 'refs/heads/main'"):
            self.assertIn(must, cond)
        steps = re.split(r"(?m)^      - ", job)
        with_key = [st for st in steps if "secrets." in st]
        self.assertEqual(len(with_key), 1)
        self.assertNotIn("github.token", with_key[0])                      # that step has no token
        self.assertNotIn("GH_TOKEN", with_key[0])
        self.assertIn("bash tools/build_pkgrepo.sh", with_key[0])          # and runs our script, in EL 9
        self.assertIn("almalinux:9", with_key[0])
        self.assertNotRegex(with_key[0], r"SILIKOS_GPG_[A-Z_]+=")          # the key is never on a command line
        for name in ("release", "deploy", "prune"):                        # the jobs that write: no checkout, no key
            self.assertNotIn("actions/checkout", j[name], name)

    def test_the_token_reads_unless_a_job_says_otherwise(self):
        for wf in WORKFLOWS:
            s = text(wf)
            head = s.split("\njobs:\n", 1)[0] + "\n"
            self.assertRegex(head, r"\npermissions:\n  contents: read\n", wf)
            self.assertNotIn("write-all", s, wf)
            for name, body in jobs(s).items():
                perms = re.findall(r"^\s+([a-z-]+): write\b", body, re.M)
                for perm in perms:
                    if os.path.basename(wf) == "repo.yml" and name == "deploy":      # (the Pages site, and nothing else)
                        self.assertIn(perm, ("pages", "id-token"), wf)
                    elif "actions/attest-build-provenance@" in body:                 # (a job that attests what it made)
                        self.assertIn(perm, ("contents", "id-token", "attestations"), "%s: job %s" % (wf, name))
                    else:
                        self.assertEqual(perm, "contents", "%s: job %s" % (wf, name))
                # the run's identity (id-token) only where it is used: to attest, or to deploy the Pages site
                if "id-token" in perms or "attestations" in perms:
                    self.assertTrue("actions/attest-build-provenance@" in body or (os.path.basename(wf) == "repo.yml" and name == "deploy"),
                                    "%s: job %s" % (wf, name))
            self.assertNotRegex(s.split("\njobs:\n", 1)[0], r": write\b", wf)

    def test_a_job_that_a_pull_request_starts_has_no_token_that_writes(self):
        seen = 0
        for wf in WORKFLOWS:
            s = text(wf)
            if not re.search(r"^  pull_request:", s.split("\njobs:\n", 1)[0], re.M):
                continue
            seen += 1
            for name, body in jobs(s).items():
                if "contents: write" not in body:
                    continue
                cond = re.search(r"^    if: (.*)$", body, re.M)
                self.assertIsNotNone(cond, "%s: job %s writes and has no condition" % (wf, name))
                self.assertRegex(cond.group(1), r"github\.ref == 'refs/heads/main'|startsWith\(github\.ref, 'refs/tags/v'\)",
                                 "%s: job %s" % (wf, name))
        self.assertGreaterEqual(seen, 1)       # (the CI is started by pull requests)

    def test_the_installation_job_has_no_token_that_writes(self):
        # (hours of the ISO's build and a virtual machine, as root on the runner: the branch ci-results is written by
        # a job of its own, from the artifact)
        j = jobs(text(".github/workflows/ci.yml"))
        self.assertNotIn("contents: write", j["install"])
        self.assertIn("contents: write", j["results"])
        self.assertIn("needs: install", j["results"])
        self.assertNotIn("actions/checkout", j["results"])
        self.assertIn("name: install-test", j["results"])

    def test_nothing_a_stranger_writes_reaches_a_script_as_code(self):
        # (an expression in a `run:` is pasted into the script before the shell reads it: only the matrix's own
        # words may be; a title, a branch name or a typed input goes through `env:`)
        for wf in WORKFLOWS:
            for n, script in run_scripts(text(wf)):
                for expr in re.findall(r"\$\{\{(.*?)\}\}", script):
                    self.assertRegex(expr.strip(), r"^matrix\.[a-z]+$", "%s:%d" % (wf, n))

    def test_every_script_is_a_script(self):
        for wf in WORKFLOWS:
            for n, script in run_scripts(text(wf)):
                p = subprocess.run(["bash", "-n"], input=re.sub(r"\$\{\{.*?\}\}", "X", script), stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, universal_newlines=True)
                self.assertEqual(p.returncode, 0, "%s:%d: %s" % (wf, n, p.stdout))

    def test_no_checkout_leaves_the_token_in_the_workspace(self):
        for wf in WORKFLOWS:
            s = text(wf)
            self.assertEqual(s.count("actions/checkout@"), s.count("persist-credentials: false"), wf)

    def test_the_actions_are_github_s_own_or_pinned_by_commit(self):
        for wf in WORKFLOWS:
            for use in re.findall(r"^\s*-? ?uses: (\S+)", text(wf), re.M):
                # every action by its commit, GitHub's own too (the audit of 13/11/2026: a tag can be moved, and the
                # jobs that hold the write token and the signing key ran `actions/checkout@v4`). The commits are the
                # ones GitHub's own log of our runs resolved the tags to that day
                self.assertRegex(use, r"@[0-9a-f]{40}$", "%s: %s is not pinned by commit" % (wf, use))


class Tree(unittest.TestCase):
    def test_no_key_licence_or_environment_file(self):
        bad = re.compile(r"(\.(svkey|svlic|pem|key|p12|pfx|jks|kdbx|lic|dat|ovpn)|(^|/)\.env(\..*)?|(^|/)id_(rsa|ed25519|ecdsa)(\.pub)?)$")
        for f in tree_files():
            self.assertIsNone(bad.search(os.path.relpath(f, ROOT)), f)

    def test_the_only_binary_files_are_pictures_and_the_font(self):
        for f in tree_files():
            with open(f, "rb") as h:
                if b"\0" in h.read(8192):
                    self.assertRegex(f, r"\.(png|ttf)$", f)

    def test_no_token_or_private_key_in_a_text_file(self):
        token = re.compile(
            r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}"
            r"|AIza[0-9A-Za-z_-]{35}|glpat-[A-Za-z0-9_-]{20}|-----BEGIN [A-Z ]*PRIVATE KEY")
        for f in tree_files():
            with open(f, "rb") as h:
                data = h.read()
            if b"\0" in data[:8192]:
                continue
            m = token.search(data.decode("utf-8", "replace"))
            self.assertIsNone(m, "%s: %s" % (f, m.group(0)[:12] if m else ""))

    def test_the_only_addresses_are_the_ones_known(self):
        # (an e-mail address in the tree is an upstream author's in a licence text or a recipe, or a made-up one of a
        # test: a new one is looked at before it is published)
        known = {"noreply@anthropic.com", "aaron@sajatypeworks.com", "lumin@debian.org", "gurkan@phys.ethz.ch",
                 "julliard@winehq.org", "silik-shell@silikvolt.com", "user-theme@gnome-shell-extensions.gcampax.github.com",
                 "secret@proxy.example.org", "pw@private.example.org",
                 # the name on the base's package signing key (tests/data/compliance); an example in CycloneDX's schema
                 "packager@almalinux.org", "firstname.lastname@example.com"}
        mail = re.compile(r"(?<![$A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:com|org|net|edu|es|cat|eu|ch|de|uk|io)\b")
        for f in tree_files():
            if f == os.path.abspath(__file__):
                continue
            with open(f, "rb") as h:
                data = h.read()
            if b"\0" in data[:8192]:
                continue
            for a in mail.findall(data.decode("utf-8", "replace")):
                self.assertIn(a, known, f)


class FirstPage(unittest.TestCase):
    def test_the_readme_says_what_the_licence_is(self):
        readme = text("README.md")
        if not any(os.path.exists(os.path.join(ROOT, n)) for n in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")):
            self.assertIn("not chosen yet", readme)
            self.assertIn("all rights are\n  reserved".replace("\n  ", " "), " ".join(readme.split()))
        self.assertIn("not licensed for reuse", readme)
        self.assertIn("docs/STATUS.md", readme)
        self.assertIn("not affiliated with or endorsed by", readme)

    def test_how_to_report_a_vulnerability(self):
        s = text("SECURITY.md")
        self.assertIn("Report a vulnerability", s)
        self.assertIn("security/advisories/new", s)
        self.assertNotRegex(s, r"[A-Za-z0-9._-]+@[A-Za-z0-9-]+\.[a-z]{2,}")      # (no address was invented)
        self.assertIn("SECURITY.md", text("README.md"))

    def test_the_owner_s_list(self):
        s = text("docs/PUBLIC.md")
        for word in ("Require approval", "Private vulnerability reporting", "ci-results", "sources-archive", "--draft"):
            self.assertIn(word, s)


if __name__ == "__main__":
    unittest.main()
