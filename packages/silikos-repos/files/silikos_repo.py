# silikos-repo: a dnf plugin of the package silikos-repos (docs/SIGNING.md, "Old metadata served again").
#
# dnf checks that SilikOS's repository metadata carry a good signature of SilikOS's key (repo_gpgcheck). It does not
# check that they are the newest: whoever sits between the machine and the server, or holds the server, can serve
# last month's metadata again, signature and all, and the machine stays on last month's packages (or a new
# installation gets them), or serve the channel next's metadata at the address of stable. This plugin closes that
# for SilikOS's two channels and says what it sees of the base's repositories:
#
#   - Every repomd.xml that tools/build_pkgrepo.sh makes carries, under the signature, a revision (the time it was
#     made, seconds since 1970 UTC) and the channel's name (a content tag silikos-channel=NAME).
#   - The highest revision this system has seen of each channel is kept in /var/lib/silikos/repo-revision.
#   - Metadata of a SilikOS channel with a LOWER revision than that, with another channel's name, made for another
#     architecture (silikos-arch=NAME: the newest aarch64 metadata served to an x86_64 machine are well signed, of
#     the right channel and fresh, and would leave every x86_64 package without its update, in silence), with no
#     revision, or loaded with the metadata's signature check turned off, are REFUSED: every package of that
#     repository is taken out of this run (dnf's own excludes), an error line says why, and the file notes it for
#     `silik update` and `silik doctor`. The base's updates go on: a bad SilikOS repository never stops them.
#   - Metadata older than warn_days although the server was just asked get a WARNING: either nothing was published
#     in that time, or someone holds the updates back. The plugin cannot tell which; the owner publishes the
#     metadata again at least twice a month so that it is the second (docs/SIGNING.md).
#   - A repository that does not answer at all is left out by dnf itself and never reaches this plugin; the file
#     keeps when each repository was last taken ("seen"), and `silik update` and `silik doctor` say from it when
#     SilikOS's repository was not reached.
#   - The base's repositories named in `watch` (baseos, appstream) are not signed as a whole and are served by
#     mirrors: for them the plugin only WARNS (a revision lower than one seen before, or older than
#     base_warn_days), and never takes anything out. Their files and /etc/dnf/dnf.conf are not touched.
#
# It runs inside every dnf of the system (dnf, yum, dnf-automatic: the daily update), as that dnf's user; only root
# writes the file. It reads what dnf has already loaded and verified: no download, no parsing of its own. Anything
# unexpected is said in one line and the run goes on: this file must never be the reason an update of the base
# does not happen. Each repository is judged by itself: what goes wrong with one never leaves another unjudged, and
# a SilikOS channel that could not be judged gives nothing to this run (it is refused, said, and asked again next
# time): a check that fails is never a check that passed.
# `dnf --disableplugin=silikos-repo` is the explicit word that turns it off for one run.
#
# The judgement is judge(), a function of plain values, so that the tests run it without dnf.
import json
import logging
import os
import time

try:
    import dnf
    _Plugin = dnf.Plugin
except ImportError:                 # (the tests, on a machine without dnf)
    dnf = None
    _Plugin = object

STATE = "/var/lib/silikos/repo-revision"
OWN = {"silikos": "stable", "silikos-next": "next"}       # repository id (packages/silikos-repos/files/silikos.repo): channel
CHANNEL_TAG = "silikos-channel="
ARCH_TAG = "silikos-arch="
WARN_DAYS = 45              # [PROPOSAL] the metadata are published again twice a month: three missed, said
BASE_WARN_DAYS = 45         # [A] AlmaLinux 9's BaseOS and AppStream change more often than this while 9 is supported
WATCH = ("baseos", "appstream")
FRESH = 86400               # "the server was just asked": the metadata were checked against it within a day
FUTURE = 2 * 86400          # an unsigned revision further ahead than this is not remembered
BASE_LAG = 3 * 86400        # [A] a mirror of the base may be this far behind another without a word
DAY = 86400

logger = logging.getLogger("dnf")


def when(t):
    """a revision as a date (they are times), or the number when it is not one"""
    try:
        return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(int(t)))
    except (ValueError, OverflowError, OSError):
        return str(t)


def as_revision(text):
    """the revision of a repomd.xml as a number, or None: only plain digits, of a plausible length"""
    text = (text or "").strip()
    if not text.isdigit() or len(text) > 12 or not text.isascii():
        return None
    return int(text)


def judge(rid, revision, tags, signed, mark, now, age=0, warn_days=WARN_DAYS, base_warn_days=BASE_WARN_DAYS, arch=None):
    """What to do with the metadata dnf loaded for the repository RID.
    revision: the text of <revision>; tags: its content tags; signed: the metadata's signature was checked
    (repo_gpgcheck); mark: the highest revision seen before (0: none); now: seconds; age: seconds since the metadata
    were checked against the server; arch: this machine's (dnf's $basearch: x86_64, aarch64), None when not known.
    -> (verdict, why, text, new mark): verdict "ok" | "warn" | "refuse"; why "" | "stale" | "older" | "rollback" |
    "channel" | "arch" | "no-revision" | "unsigned"; the new mark is never lower than the old one."""
    rev = as_revision(revision)
    own = rid in OWN
    if own:
        channel = OWN[rid]
        if not signed:
            return ("refuse", "unsigned", "%s: the signature check of its metadata is off (repo_gpgcheck): nothing says "
                    "these are SilikOS's. Turn it on: silik update channel %s" % (rid, channel), mark)
        if rev is None:
            return ("refuse", "no-revision", "%s: its metadata carry no revision: not made by SilikOS's tools, or cut" % rid, mark)
        named = sorted(t[len(CHANNEL_TAG):] for t in tags if t.startswith(CHANNEL_TAG))
        if named != [channel]:
            return ("refuse", "channel", "%s: these metadata are %s, not the channel %s's: another repository is served "
                    "at this address" % (rid, ("the channel %s's" % ", ".join(named)) if named else "of no channel", channel), mark)
        # (before the revision is looked at, and it is not remembered: the other architecture's metadata carry the
        # channel's newest revision)
        made_for = sorted(t[len(ARCH_TAG):] for t in tags if t.startswith(ARCH_TAG))
        if arch and made_for != [arch]:
            return ("refuse", "arch", "%s: these metadata were made for %s, not for this machine's %s: another "
                    "architecture's repository is served at this address, and this machine's packages would get no update"
                    % (rid, ", ".join(made_for) if made_for else "no architecture", arch), mark)
        if rev < mark:
            return ("refuse", "rollback", "%s: metadata of %s (revision %d) are older than the ones this system has "
                    "already seen, of %s (revision %d): an old repository is served again"
                    % (rid, when(rev), rev, when(mark), mark), mark)
        if warn_days > 0 and age <= FRESH and now - rev > warn_days * DAY:
            return ("warn", "stale", "%s: the newest metadata the server gives are of %s, %d days ago: nothing was "
                    "published since, or updates are held back" % (rid, when(rev), (now - rev) // DAY), rev)
        return ("ok", "", "", rev)
    # a repository of the base: unsigned as a whole, served by mirrors; said, never refused
    if rev is None or rev < 1000000000:        # (not a time: some repositories number their revisions otherwise)
        return ("ok", "", "", mark)
    if rev < mark - BASE_LAG:
        return ("warn", "older", "%s: this mirror's metadata are of %s, older than the ones this system has already "
                "seen, of %s: a mirror that is behind, or an old repository served again" % (rid, when(rev), when(mark)), mark)
    if rev > now + FUTURE:
        return ("ok", "", "", mark)             # (nothing vouches for it: not remembered)
    if base_warn_days > 0 and age <= FRESH and now - rev > base_warn_days * DAY:
        return ("warn", "stale", "%s: the newest metadata this mirror gives are of %s, %d days ago: updates may be "
                "held back" % (rid, when(rev), (now - rev) // DAY), rev)
    return ("ok", "", "", max(rev, mark))


def read_state(path=None):
    """{repository id: {"revision": N, "seen": T, "said": {...} or absent}}; {} when there is none or it is not ours"""
    try:
        with open(path or STATE, encoding="utf-8") as f:
            data = json.loads(f.read(1 << 20))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for rid, row in data.items():
        if isinstance(rid, str) and isinstance(row, dict) and isinstance(row.get("revision", 0), int) and row.get("revision", 0) >= 0:
            out[rid] = row
    return out


def write_state(state, path=None):
    """root's file, 0644, replaced whole (a reader never sees half of it)"""
    path = path or STATE
    d = os.path.dirname(path)
    os.makedirs(d, mode=0o755, exist_ok=True)
    tmp = "%s.%d" % (path, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(state, indent=1, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.rename(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def note(state, rid, verdict, why, text, mark, revision, now, reached=None):
    """the row of RID after this run: the mark, when the server last gave metadata that were taken (REACHED: now
    less the age of dnf's copy, so that a run from the cache does not count as an answer of the server), and the
    refusal or warning of this run if any"""
    reached = now if reached is None else reached
    row = dict(state.get(rid) or {})
    changed = False
    if mark != row.get("revision", 0):
        row["revision"] = mark
        changed = True
    if verdict == "ok" or (verdict == "warn" and why == "stale"):
        # when the repository last gave metadata that were taken: `silik update` and `silik doctor` read from it
        # that a repository was not reached (it does not answer, or is blocked: dnf then leaves it out in silence)
        if reached > row.get("seen", 0):
            row["seen"] = reached
            changed = True
    said = {"verdict": verdict, "why": why, "text": text, "revision": as_revision(revision), "when": now} if verdict != "ok" else None
    key = (verdict, why, as_revision(revision))
    old = row.get("said")
    if said is None:
        if old is not None:
            del row["said"]
            changed = True
    elif old is None or (old.get("verdict"), old.get("why"), old.get("revision")) != key or now - old.get("when", 0) >= 3600:
        row["said"] = said
        changed = True
    row.setdefault("revision", 0)
    state[rid] = row
    return changed


class SilikosRepo(_Plugin):
    name = "silikos-repo"

    def __init__(self, base, cli):
        if dnf is not None:
            super(SilikosRepo, self).__init__(base, cli)
        self.base = base
        self.warn_days, self.base_warn_days, self.watch = WARN_DAYS, BASE_WARN_DAYS, WATCH

    def config(self):
        try:
            cp = self.read_config(self.base.conf)
            if cp.has_section("main"):
                if cp.has_option("main", "warn_days"):
                    self.warn_days = max(0, cp.getint("main", "warn_days"))
                if cp.has_option("main", "base_warn_days"):
                    self.base_warn_days = max(0, cp.getint("main", "base_warn_days"))
                if cp.has_option("main", "watch"):
                    self.watch = tuple(cp.get("main", "watch").replace(",", " ").split())
        except Exception as e:         # (a broken configuration file: the defaults, said)
            logger.warning("silikos-repo: its configuration could not be read (%s): the defaults are used", e)

    def sack(self):
        try:
            self._check()
        except Exception as e:         # never the reason an update of the base does not happen
            logger.warning("silikos-repo: the check of the repositories' revisions did not run (%s: %s)", type(e).__name__, e)
            # (what could not be checked is not taken: SilikOS's own channels give nothing to this run)
            try:
                for repo in self.base.repos.iter_enabled():
                    if repo.id in OWN:
                        self._refuse(repo.id, "%s: it was not checked" % repo.id)
            except Exception as e2:
                logger.error("silikos-repo: SilikOS's channels could neither be checked nor left out (%s: %s)", type(e2).__name__, e2)

    def _arch(self):
        """this machine's architecture as dnf names it in a repository's address ($basearch), or None"""
        try:
            arch = self.base.conf.substitutions.get("basearch")
            return arch if isinstance(arch, str) and arch else None
        except Exception:
            return None

    def _refuse(self, rid, text):
        """every package of the repository RID out of this run -> how many"""
        q = self.base.sack.query().filterm(reponame=rid)
        n = len(q)
        if n:
            self.base.sack.add_excludes(q)
        logger.error("silikos-repo: REFUSED %s. Nothing is taken from it in this run (%d packages left out); "
                     "the other repositories go on.", text, n)
        return n

    def _one(self, repo, state, now, arch):
        """one repository judged -> its notes changed"""
        rid = repo.id
        r = repo._repo
        try:
            revision, tags, age = r.getRevision(), tuple(r.getContentTags()), int(r.getAge())
        except Exception as e:
            # not loaded: it did not answer, or failed its own checks; dnf said so and gives nothing of it. Should
            # dnf all the same hold packages of a SilikOS channel whose metadata cannot be read here, they go out
            if rid in OWN and len(self.base.sack.query().filterm(reponame=rid)):
                text = "%s: its metadata could not be read by the check (%s)" % (rid, type(e).__name__)
                self._refuse(rid, text)
                return note(state, rid, "refuse", "unread", text, (state.get(rid) or {}).get("revision", 0), None, now)
            return False
        if not revision and not tags and rid not in OWN:
            return False
        mark = (state.get(rid) or {}).get("revision", 0)
        verdict, why, text, new = judge(rid, revision, tags, bool(repo.repo_gpgcheck), mark, now, age,
                                        self.warn_days, self.base_warn_days, arch)
        if verdict == "refuse":
            self._refuse(rid, text)
        elif verdict == "warn":
            logger.warning("silikos-repo: %s.", text)
        return note(state, rid, verdict, why, text, new, revision, now, now - max(0, age))

    def _check(self):
        now = int(time.time())
        state = read_state()
        arch = self._arch()
        changed = False
        for repo in self.base.repos.iter_enabled():
            rid = repo.id
            if rid not in OWN and rid not in self.watch:
                continue
            try:
                changed = self._one(repo, state, now, arch) or changed
            except Exception as e:
                # one repository's trouble is its own: the others are still judged. A SilikOS channel that could
                # not be judged gives nothing to this run; a repository of the base is only ever said
                if rid in OWN:
                    try:
                        self._refuse(rid, "%s: the check of its metadata did not run (%s: %s)" % (rid, type(e).__name__, e))
                    except Exception as e2:
                        logger.error("silikos-repo: %s could neither be checked nor left out (%s: %s)", rid, type(e2).__name__, e2)
                else:
                    logger.warning("silikos-repo: the check of %s did not run (%s: %s)", rid, type(e).__name__, e)
        if changed and os.geteuid() == 0:
            write_state(state)
