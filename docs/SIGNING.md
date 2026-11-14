# Who can put a package on a SilikOS machine (13/11/2026)

The question this answers: someone very capable takes the network path, a mirror, a dependency of a GitHub Actions
workflow, or for a while the GitHub repository itself. Can they make an installed SilikOS install a package? The
audit of 13/11/2026 left six findings of this kind open (`docs/SECURITY.md`: S2, S6, S7's rest, S8, S10, and where
the signing key lives). This is what was built for each, what it proves, what it does not, and the one decision
that is the owner's. `docs/REPO.md` is the owner's to-do list for the repository; this is the reasoning under it.

## The chain, and who can break which link

| Link | What holds it | Who breaks it |
|---|---|---|
| The commit | The owner's push to `main` (branch protection: the owner's, `docs/SECURITY.md` S3) | Whoever has the GitHub account, or a token that writes |
| The build | A workflow run on GitHub's runners, from that commit; upstream sources pinned by commit or sha256 | A dependency of the workflow: an action (pinned by commit), a container image, a package the build installs |
| Where the build waits | A release, or a run's artifact | Anything with a token that writes a release |
| **Provenance** (new) | An attestation: GitHub signs "this run of this workflow file at this commit made the file with this sha256" | The GitHub account (it can change the workflow); not a stolen release token alone |
| **The signature** | SilikOS's GPG key over every package and over `repomd.xml` | Whoever holds the private key |
| The server | GitHub Pages (metadata) and releases (packages) | GitHub, a CDN node, someone on the network path |
| **Freshness** (new) | A revision inside the signed metadata; the machine refuses older ones | Nobody can go back; holding back is noticed after `warn_days` |
| The machine | `dnf`: `gpgcheck`, `repo_gpgcheck`, the plugin `silikos-repo` | root on the machine |

## Provenance: where a file was made (S2)

**What is attested.** `actions/attest-build-provenance` (pinned by commit; GitHub's own action) in:

| Workflow, job | Files | When |
|---|---|---|
| `ci.yml`, `release` | the ISOs, every package and source package of the release, by the list `SHA256SUMS`; the attestation itself is in the release as `SHA256SUMS.attestation.jsonl` | a tag `v*` |
| `repo.yml`, `attest` | every package the run puts into `repo-el9-next` / `repo-el9-stable` (signed, as uploaded) and each channel's `repomd.xml`, `repomd.xml.asc` and `STATE` | every run that publishes |
| `eda.yml` (`trial`, `kicad-trial`, `models-keep`, `keep-arm`), `dev.yml` (`trial`, `trial-arm`), `wine.yml` (`release`) | the packages a job has tried and kept in its release | every run that keeps one |

Each of those jobs, and only those, has `id-token: write` and `attestations: write`. None is started by a pull
request: `ci.yml`'s `release` runs for a tag of this repository only; the other workflows have no `pull_request`
trigger. The job of `repo.yml` that holds the signing key has neither permission, and the job that attests has no
key, no checkout and no script (a test holds all of this: `tests/test_supply.py`).

**How to check a download.**

```bash
gh release download v0.9.0 --repo BTomeu/SilikOs --dir rel
bash tools/verify_release.sh --workflow ci.yml --ref refs/tags/v0.9.0 rel
#   $ (cd rel && sha256sum --check --strict SHA256SUMS)
#   $ gh attestation verify rel/SilikOS-9.8-x86_64-netinstall.iso --repo BTomeu/SilikOs --signer-workflow BTomeu/SilikOs/.github/workflows/ci.yml --source-ref refs/tags/v0.9.0 --bundle rel/SHA256SUMS.attestation.jsonl
#   ... one line per file, then "ok: rel"
# one file, by hand:
gh attestation verify FILE --repo BTomeu/SilikOs
```

The script prints each command, fails when a package or ISO in the folder is not in the list, and never says ok when
the attestation could not be checked (`gh` missing: exit 1; `--sums-only` says "NOT CHECKED").

**What an attestation proves.** These very bytes were produced by a run of that workflow file, at that commit and
ref, in that repository, on GitHub's runners. The signature is Sigstore's, made with a certificate issued for the
run's OIDC identity: there is no key of ours to steal.

**What it does not prove.** That the commit is a good one: whoever can push to the repository, or change a workflow,
gets anything built and attested. That what the run downloaded was good (the table at the end). That the file is
the newest. And in `ci.yml` the `release` job attests files that the jobs before it built and passed on as
artifacts of the same run: it vouches for the run, not for each job. An attestation says where; only the owner's
signature says "I meant this".

**What it closes.** A release is a place where anything with a write token can put a file, and the package
repository signed whatever lay there (the audit ran it: a hand-made `tzdata-9999` came out signed). Now, before
anything is signed, `repo.yml` asks for each tool's package and each published package (`tools/vouched.sh`)
`gh attestation verify FILE --repo … --source-ref refs/heads/main --signer-workflow …/WORKFLOW --deny-self-hosted-runners`,
where WORKFLOW is the one that keeps that release: `eda.yml` for `eda-*`, `dev.yml` for `dev-tools`, `wine.yml` for
`wine-*`, and for what is published already those three or `repo.yml`. A tool's package without it is left out. A
published package without it stays only if it already carries a good signature of SilikOS's key (the owner signed
it by hand), and is otherwise removed from the channel; it is never signed (`tools/build_pkgrepo.sh --unvouched`).
SilikOS's own packages of the run need none: they are the artifact of the CI run the workflow has just checked.
The ISO is held to the same since the second pass (below): `ci.yml` and `offline.yml` put a release's package on
it only with that attestation.

**The first run after this change** finds no attestation for the packages that are in the releases today (they
were built before): the repository then holds SilikOS's own packages only, and says so in an annotation per
package, until *EDA tools*, *Dev tools* and *Wine* have each run once (Actions → Run workflow; their builds are
cached, so it is the trials that run). This replaces step 4 of the owner's list in `docs/SECURITY.md` (deleting
`repo-el9-next` by hand).

## Old metadata served again (S6)

`dnf` checks that `repomd.xml` carries a good signature. It does not check that it is the newest. Run before the
fix, in an AlmaLinux 9.8 container: a server that gives last week's tree again, signature and all, makes a machine
that installs today take last week's package, and one channel's tree served at the other's address is taken. Both
are refused now.

**In the metadata.** `tools/build_pkgrepo.sh` writes into every `repomd.xml`, under the signature:
`<revision>` (the time the metadata were made, seconds since 1970 UTC; `--after N` makes it higher than what is
published even with a clock that is behind) and the content tags `silikos-channel=stable|next`,
`silikos-arch=…`, `silikos-commit=…`.

**On the machine.** The package `silikos-repos` ships a `dnf` plugin, `silikos-repo`
(`/usr/lib/python3.9/site-packages/dnf-plugins/silikos_repo.py`, `/etc/dnf/plugins/silikos-repo.conf`). It runs
inside every `dnf` (so in `silik update` and in the daily `dnf-automatic`), after `dnf` has loaded and verified the
metadata, and reads what `dnf` itself holds: no download and no parsing of its own, so there is no gap between what
is checked and what is used. For the channels `silikos` and `silikos-next`:

| The metadata dnf loaded | What happens |
|---|---|
| revision lower than the highest this machine has seen | **refused**: every package of that repository is taken out of the run |
| the other channel's name, or none | **refused** |
| made for another architecture (`silikos-arch=`), or for none | **refused**, and its revision is not remembered (the second pass) |
| no revision | **refused** |
| loaded with `repo_gpgcheck` off | **refused** (nothing vouches for the revision), and nothing of it is remembered |
| older than `warn_days` (45) although the server was asked within a day | **warning**: nothing was published since, or updates are held back |
| anything else | taken; the revision becomes the new mark |

The mark is `/var/lib/silikos/repo-revision` (root's, 0644, JSON, replaced whole). A refusal is an error line of
`dnf`, a note in that file, exit 1 of `silik update`, and a `▼ bad` row of `silik doctor` until a good run. The
base's updates go on: a bad SilikOS repository never stops them. The comparison of revisions does not read the
machine's clock; the age warning does.

**The 45 days** [PROPOSAL]. `repo.yml` publishes the metadata again on the 1st and the 15th of each month with
nothing new (a new revision, a new signature), so a channel's newest metadata are normally at most about two weeks
old; 45 days is three missed runs. With a key that only the owner holds, the owner signs again that often (a
command: below) or raises `warn_days`. GitHub stops scheduled workflows of a repository without activity for 60
days [A]: the warning is then what says so.

**What this does not do.**
- A machine has no memory of a repository it has never asked: a new installation that is given old metadata takes
  them (the age warning is all it has). It cannot be given the other channel's.
- The plugin is Python inside `dnf`. Programs that use `libdnf` without `dnf`'s Python (PackageKit, so GNOME
  Software) do not load it. Run on 14/11/2026 (PackageKit 1.2.6, its daemon started by hand in a container): with
  the channel `next`'s tree served at `stable`'s address, `dnf` refused it and `pkcon update` installed its package.
  On an installed system GNOME Software is there (the Workstation set) and does not start by itself (the speed
  profile); opened from Start, its updates go around this check. `silik update` and the daily update do not.
- root can turn it off: `dnf --disableplugin=silikos-repo …` for one run (the explicit word, as `--unsigned` is for a
  mirror), `enabled = 0` in its file for all. Removing `/var/lib/silikos/repo-revision` makes the machine forget
  (the way out if a wrong revision was ever signed and published).
- Holding updates back cannot be refused, only noticed: a signed "nothing new" has to be renewed by whoever signs.
- A repository that is simply blocked never reaches the plugin: `dnf` leaves it out with one line and no error (run),
  as it does for one that is down. The note file keeps when each channel last gave metadata that were taken:
  `silik update` says "was not reached in this run", and `silik doctor` warns after 45 days [PROPOSAL] without it.

**The base's repositories.** Read on AlmaLinux 9.8: `baseos` and `appstream` use
`mirrorlist=https://mirrors.almalinux.org/mirrorlist/…` (a plain list of mirrors, not a metalink), `gpgcheck=1`
and no `repo_gpgcheck`, although AlmaLinux publishes a `repomd.xml.asc`. So for the base every package is checked
against AlmaLinux's key and the metadata are trusted to TLS and the mirror: a mirror can serve old metadata, and
nothing in `dnf` says so. The claim that a metalink protects against it was run with a hand-made metalink: `dnf`
refuses a `repomd.xml` whose sha256 is not the one the metalink names ("Downloading successful, but checksum
doesn't match"). That holds for EPEL (its file uses `metalink=https://mirrors.fedoraproject.org/…`), not for the
base. SilikOS does not change the base's repository files or `/etc/dnf/dnf.conf`; the plugin only *watches*
`baseos` and `appstream` (their `<revision>` is a time too): a revision more than three days [A] older than one
seen before, or older than `base_warn_days` (45) [A], is a warning. Nothing of the base is ever refused by it.

## Which CI run is published (the rest of S7)

`repo.yml` publishes a run only when GitHub's API says, for that run id: the workflow file is
`.github/workflows/ci.yml` (a name can be given to another file), it is completed and green, the repository and the
head repository are this one, the event is `push` or `workflow_run` (the CI that follows a tool's workflow: it runs
`main`'s file at `main`'s commit), the branch is `main` or a tag `v*` that points at that commit, and the commit is
on `main` (`compare/SHA...main`: `main` is not behind it). A run named by hand is held to the same. A pull request's
run, a run started by hand on another branch, another workflow called "CI": nothing is published (a test runs the
function against ten made-up runs). Deviation from "event push only": the CI runs that follow *EDA tools*, *Dev
tools* and *Wine* are how a new tool's package reaches the channel `next`, and they build `main`.

## The Actions cache (S8)

A cache entry is not tied to who wrote it. Every job that runs for `main`, in any workflow, with a read-only token,
can save an entry under any key that is still free, and an entry is never replaced. Pull requests cannot reach
`main`'s cache (theirs is scoped to the pull request) [A: GitHub's documented scoping, not run]. Five jobs restore
a build from the cache and pass it on to a job that keeps it in a release: `eda.yml` `build`, `kicad`, `models`;
`wine.yml` `build`, `addons`. All five run upstream's build code, so one of them could leave a package under the
key of another's next recipe.

The cache stays (it saves hours), and what it gives back is used only when it is, byte for byte, a file that a
release of this repository holds under the same name (`tools/cache_check.py`: GitHub gives each release file's
sha256). A release is written by jobs with a write token, which no build job has. Anything else is deleted and
built again. The price: a build whose trial failed was never kept, so it is built again on each run until its
recipe changes.

## Everything the repository downloads (S10)

| What | From | How it is checked | State |
|---|---|---|---|
| Actions (`uses:`) | github.com | commit (40 hex; a test) | closed |
| The signing step's image | Docker Hub `almalinux:9` | digest `sha256:245f8aab…7ae2` (the index of 27/10/2026, read 13/11/2026 with `docker buildx imagetools inspect almalinux:9`; the same command gives the next one) | **closed here** |
| `almalinux:9` in every other job (`container:`, `docker run`) | Docker Hub | TLS only (a tag) | open: they build what is later attested; 26 places name the tag, and a digest there is one more thing to renew by hand each time the image changes: the owner's call |
| Packages installed inside those containers (`dnf install`) | AlmaLinux's repositories | signature (the key in the image) | as the base |
| The runner's tools (`tools/ci_apt.sh`) | Ubuntu's archive | signature (apt) | as Ubuntu |
| AlmaLinux boot ISO (`tools/build_iso.sh`) | repo.almalinux.org | signature: `CHECKSUM` signed by the key of a pinned fingerprint, then sha256 | closed (run by the audit) |
| The base's source packages (`tools/fetch_base_sources.sh`) | vault.almalinux.org | signature (AlmaLinux's key, fetched over TLS) | as it was |
| Open EDA and dev tools' sources (`eda/versions`, `dev/versions`) | GitHub, GitLab, SourceForge | commit of the tag, or sha256 of the archive; PyPI archives by sha256 | closed |
| Wine's source (`tools/build_wine.sh`) | dl.winehq.org | signature by a pinned fingerprint, and sha256 (`wine/sources`) | closed |
| Wine Mono, Wine Gecko (`tools/build_wine_addons.sh`) | their release servers | hash (sha256 in `wine/sources`) | closed |
| The network installation's 1570 packages (`kickstart/silikos.ks`) | repo.almalinux.org, dl.fedoraproject.org | TLS only: the installer checks no signature (S4) | open; the offline ISO checks each package |
| NVIDIA's repository (`silik hw nvidia install`) | developer.download.nvidia.com | TLS only for the `.repo` file; the key it names is taken on first use | **open**: the fingerprint could not be read here (the session's proxy refuses that host), and none is invented |
| EDA boxes' images (`silik eda create`): `centos:6`, `centos:7`, `almalinux:8` | Docker Hub | TLS only (a tag) | **open**: the two CentOS images are frozen since 2021 and their digests were read (below), but EL 9's container tools refuse a tag together with a digest (run: skopeo 1.22.2, "Docker references with both a tag and digest are currently not supported"), and `silik eda` tells an EL6 box by the text `centos:6` in the image's name |
| `silik env` images and Python packages | the base's repositories, PyPI | signature; pip `--require-hashes` | as it was |
| Hardware facts, benchmarks (`tools/fetch_hw_facts.sh`, `tools/bench_*`) | kernel.org mirrors, GitHub | TLS only; nothing of them is shipped as code | not in the system |
| The published revision (`repo.yml`) | the Pages site | nothing: only ever used to raise the next revision | harmless |

The CentOS digests, for whoever changes `silik eda` to name the images by digest alone
(`docker.io/library/centos@sha256:…`; both forms answered `skopeo inspect` on 13/11/2026, created 15/09/2021):
`centos:6` `sha256:a93df2e96e07f56ea48f215425c6f1673ab922927894595bb5c0ee4c5a955133`,
`centos:7` `sha256:be65f488b7764ad3638f236b7b515b3678369a5124c47b8d32916d6487418ea4`.

## Where the signing key lives: the owner's decision

The attacker here: the GitHub account, or a dependency of a workflow, is taken.

| | How | Account taken | A workflow dependency taken | What it costs |
|---|---|---|---|---|
| (a) | The private key as a secret of the environment `package-signing`, limited to `main`, with the owner as required reviewer (what `docs/REPO.md` describes and `repo.yml` does today) | **signs anything**: the attacker is the reviewer, and can change the workflow and the environment | **can take the key**: an action that runs in the job before the signing step can replace the script that receives it. The actions there are pinned by commit, the image by digest, and the step has no token: narrow, not closed | one click per publication; nothing else |
| (b) | The key never leaves the owner: a hardware token (or a key file on a machine that is not GitHub). GitHub builds and attests; the owner verifies, signs with `tools/sign_release.sh`, and uploads; GitHub only checks signatures (`tools/check_signed.sh`) and serves | **cannot sign**. It can serve old signed files (refused by installed systems, above) or none (noticed after 45 days), and can push a bad commit that CI builds and attests: the owner must look at what they sign | nothing to take | the owner at an EL 9 machine with the token for every publication, and twice a month for the freshness |
| (c) | Sigstore keyless only: no GPG key, installed systems trust the attestation | **signs anything**: the identity is "a workflow of this repository", and the account controls the workflow | the dependency runs inside that identity: **signs** | `rpm` and `dnf` on EL 9 cannot verify it: a verifier of ours on every machine, and GitHub and Sigstore become the root of trust |

**Recommended: (b) for the channel `stable`, on a hardware token, with the attestation as what the owner checks
before signing.** It is the only one of the three where taking GitHub does not give a signature, and for one
person who publishes a release now and then the cost is a command. (c) answers neither threat and cannot be
verified by the base's tools; attestations stay, as evidence. (a) is the convenient one and the workflow keeps it
working, but under this attacker it is a key that GitHub holds.

For `next` (every green build of `main`: several a day) signing by hand is not realistic. Either `next` gets no
key (it stays unsigned and no installed system can turn it on: what happens today), or a **second** key under (a)
that is only ever the `next` channel's: the metadata are checked against the key of the repository section
(`gpgkey=` in `silikos.repo`), so a `next` key in GitHub's hands cannot sign `stable`'s metadata. Two keys need a
second key file and a `gpgkey` per section: not built, it follows the decision. Until then: one key, (b), `stable`.

**The owner's steps under (b)** (the key and its public half: `docs/REPO.md`, steps 1 and 3; step 2, the secrets,
is then skipped):

```bash
# on an EL 9 machine (SilikOS itself) with the token: rpm-sign, createrepo_c, dnf-utils, gnupg2, gh
gh release download v0.9.0 --repo BTomeu/SilikOs --dir rel
bash tools/verify_release.sh --workflow ci.yml --ref refs/tags/v0.9.0 rel     # sums + attestation of each file
git log -1 --format=%H v0.9.0                                                 # the commit you tagged, not another
bash tools/sign_release.sh --key FPR --sums rel                               # SHA256SUMS.asc: the release is yours
gh release upload v0.9.0 rel/SHA256SUMS.asc --repo BTomeu/SilikOs

# the channel: the packages of that release (and the tools', each verified the same way) into a signed tree
gh release download repo-el9-stable --repo BTomeu/SilikOs --pattern '*.rpm' --dir pub      # what is published now
bash tools/sign_release.sh --key FPR --channel stable --in rel --published pub --out signed \
     --baseurl https://github.com/BTomeu/SilikOs/releases/download/repo-el9-stable
# signed/pool/stable: the packages for the release (UPLOAD names the new ones); signed/repo: the metadata;
# signed/SHA256SUMS(.asc): all of it. Twice a month, the same command with nothing new renews the revision.
bash tools/check_signed.sh --key-file packages/silikos-repos/files/RPM-GPG-KEY-SilikOS signed    # what GitHub would run
```

`sign_release.sh` signs with whatever key `gpg-agent` holds (gpg asks for the PIN or the touch itself), refuses a
key from the environment, refuses a key that is not the committed public one, verifies its own result against the
public half alone, and deletes a result that does not verify. `check_signed.sh` fails a tree that holds a link (it
would not look into it, a server would follow it) or a file its signed `SHA256SUMS` does not name; `--whole` asks
that the tree has that signed list at its top. Without the list only the packages and the metadata are vouched
for: the key file and `silikos.repo` that the tree offers are then anybody's (said in a note).

**Not built: the workflow that publishes an owner-signed tree.** Pages is deployed by a workflow, so under (b)
`repo.yml` needs a mode that takes `signed/` (as an artifact or a release file), runs `tools/check_signed.sh`
against the committed key, and deploys it without ever holding a key. It is some thirty lines; it was not written
because it only makes sense once (b) is chosen, and it could not have been run here. It must ask
`tools/check_signed.sh --whole`.

## The second pass, 14/11/2026: someone tries to get through what was built

A reviewer who had not written any of the above was given three goals: a package of theirs on an owner's machine,
that machine kept on old packages, or a signature on something they chose. Four attackers, each alone: a stranger
with a GitHub account, a stolen token that writes releases (no key, not `main`), someone between an installed
machine and the repository who holds old, well signed files, and hostile input to the signing scripts.

| What was found | How bad | Run | State |
|---|---|---|---|
| **The ISO took whatever lay in the releases.** `ci.yml` and `offline.yml` downloaded every package of `eda-tools`, `dev-tools` and `wine-*` and `tools/build_iso.sh` put each on the ISO and its name into the kickstart: installed as root, unsigned, on every new machine. The gate of S2 stood before the signature only. Also reached by starting *EDA tools* by hand on another branch (its packages go to the same release) | high | the workflow's step with a made-up `gh`, and `build_iso.sh`'s own lines: a stranger's package in the ISO's repository and kickstart | **fixed**: a release's package goes on an ISO only with the attestation of the workflow that keeps that release, on `main` (`tools/vouched.sh`); not run on GitHub yet |
| **An old package under the next version's name.** An attestation is asked by a file's sha256, never its name. A package really built, attested and signed here, put back into `repo-el9-*` as `NAME-NEXTVERSION…rpm`, was "vouched", "signed" and "already published": the real new build was left out, for good, and installed systems stayed on the old one with "Nothing to do" | high | real rpm, gpg, createrepo_c, dnf: the client stayed on 1.0 while 2.0 was built | **fixed**: `tools/build_pkgrepo.sh` holds every package to the name in its own header; a release's file never takes the place of one of the CI run's own packages. Run again: 2.0 published and installed |
| **The other architecture's metadata.** The channel's own newest aarch64 metadata at the x86_64 address: right channel, newest revision, good signature. The machine's x86_64 packages (Wine, KiCad, ngspice, OpenOCD) got no update; `silik update` ended with 0 and the doctor said ok | medium | real dnf with the plugin, `silik update`, dnf-automatic | **fixed**: refused, exit 1, `▼ bad` (run) |
| **A tag on a commit that is not `main`'s** got an ISO built, a release, and this repository's attestation (`ci.yml`, `refs/tags/v…`): `verify_release.sh --workflow ci.yml --ref refs/tags/v…` says ok. `repo.yml` asked whether the commit is on `main`; the CI's release job did not | medium | the step with a made-up `gh`; GitHub's compare API read for a commit on `main` (0), `main` itself (0), a branch without common history (an error, not 0) | **fixed** against a token that cannot change workflow files; a token that can is stopped only by the tag ruleset (`docs/SECURITY.md`, the owner's step 1) |
| **Any workflow of `main` vouched.** The gate asked for an attestation "of this repository, from `main`", whatever the workflow file: a workflow that attests what it is handed would vouch for anything. None does today (read: every `attest-build-provenance` step attests files of its own run) | low | read on the real repository: one package carries two attestations, `dev.yml`'s and `repo.yml`'s | **fixed**: the workflow is named |
| A problem with one repository stopped the plugin's whole check: the ones after it were not judged, with a warning only. Not reached from outside (no content of a repository was found that raises) | low | unit tests | **fixed**: each repository by itself; a SilikOS channel that cannot be judged gives nothing to that run |
| `check_signed.sh` passed a tree with an unsigned package or unsigned metadata behind a link, with files nobody signed beside the signed ones, and with the offered key file replaced when the list was removed | low | run | **fixed** (above) |
| A file both put into a release and removed from it in one run (a published file of unknown origin, and the real package of that name among the new ones): the metadata then name a file that is gone | low | run | **fixed** |
| **PackageKit / GNOME Software** go around the plugin | medium | run (above) | **open**, the owner's: the options are a libdnf plugin in C (a compiled package per architecture), or GNOME Software without its package updates |
| **The Actions cache check can be cheated by what it checks.** A cache entry is a tar archive unpacked with absolute names allowed [A: `actions/cache`'s `tar -P`, from its source, not run on GitHub]: an entry made by a hostile build can replace `tools/cache_check.py` or the build script before either runs. Needs code running in a build job of `main` first, and such a job can also take another tool's artifact name in the same run | low | tar's behaviour, locally | **open**: closing it means a fresh job that receives only the packages; `eda.yml` and `wine.yml` were not touched for it |
| **Old instead of new through the gate.** A token that writes releases can delete the newest packages from `repo-el9-*` and leave (or put back) older, genuine ones: the channel then offers the older version. Installed systems never go back; a machine that installs that tool for the first time gets the old one | low | follows from the name-squat run | **open**: needs the published versions remembered somewhere a release token does not reach (the Pages site) |
| A package signed for `next` can be put into `stable`'s release and is published there (one key, and the gate cannot tell the channels apart) | low | read | **open**: closes with option (b), or two keys |
| A refusal, a channel that is not reached and old metadata are said by `silik update` and `silik doctor` only: nothing in the status bar | low | read | **fixed for a refusal** (silikos-desktop 0.18.1): the status bar's update field reads the plugin's notes and says `update repository refused` while a SilikOS channel's metadata were refused in the last three days (the daily update renews the note; a good run takes it away). Seen in the rig's GNOME Shell 40 with a note written as the plugin writes it: the word appears, and leaves when the file is replaced; not on an installed system. **Open**: a channel not reached and old metadata, the two commands only |
| A new installation has no memory: the oldest metadata that carry the channel's name are taken. Silent while they are younger than 45 days, a warning (never a refusal) after | low | read; the audit ran the 60-day warning | as designed, said |

**What was tried and held.** A stranger's pull request reaches no token that writes, no secret and no identity:
no `pull_request_target`, no self-hosted runner; a fork's run gets a read-only token whatever the file says. The
only expression inside a script is `${{ matrix.tool }}`, from lists in the file; what comes from an event (a branch
name, a run id, a typed version) reaches the shell as a variable and is compared or matched before use. `repo.yml`
never checks out or runs anything of the CI run it publishes; it takes two artifacts of a run it has held to the
workflow file, the event, the repository, the branch and the commit on `main`. A pull request's cache is its own
[A: GitHub's documented scoping]. Every release file has a sha256 in GitHub's API (read: 436 of 436), and a file
without one is built again. One channel's metadata for the other, old metadata, and metadata without the
signature check were refused again.

**Which of the owner's five steps stop what.** The tag ruleset (step 1) stops the tag on a foreign commit and a
stranger's tag promoting `main` to `stable`; the branch ruleset stops a token that writes from changing what `main`
builds. Neither stops a token that writes releases from doing what is open above: that is what option (b) is for.

## What was run, and what was not

Run on 13/11/2026 in an AlmaLinux 9.8 container (dnf 4.14.0, rpm 4.16.1.3, gnupg 2.3.3, createrepo_c 0.20.1), with
keys made there and deleted: the package `silikos-repos` built with its plugin and installed; a client taken to
revision 2; revision 1 served again and refused by `dnf`, by `silik update` (exit 1), by `dnf-automatic`, with
nothing of it installed; the same without the plugin, where `dnf` installed the old package; the other channel's
tree refused; a tree with the signature check turned off refused; 60-day-old metadata warned about; the channel
turned on by hand on a system without the key ignored by `dnf`; a damaged note file; the base's repository files
read and the plugin's warning for an older `baseos`; the metalink claim; `tools/sign_release.sh` and
`tools/check_signed.sh` with two keys in the keyring and six ways of spoiling the result; `tools/cache_check.py`
against this repository's real releases.

Run on 14/11/2026 (the second pass, the same container, keys made there and deleted): the name squat and its
refusal with `dnf` updating a client; the other architecture's metadata against the plugin, `silik update` and
dnf-automatic, before and after; `check_signed.sh` against links, added files and a tree without its list;
`build_pkgrepo.sh` on nine packages of the real release `repo-el9-next` (none misnamed); the ISO's step with a
made-up `gh`; PackageKit beside `dnf`. Read on the real repository: the attestations of one release file, the
compare API, the digests.

Run on GitHub on 14/11/2026: `tools/vouched.sh` in `ci.yml` (run 43549553439: the ISO's 27 tool packages, each
`gh attestation verify` with `--source-ref refs/heads/main --signer-workflow … --deny-self-hosted-runners`, none
left out) and in `repo.yml` (run 43556210168: it took the CI run of main, left out 2 packages without an
attestation, made one attestation for 18 files, put the packages in the release, skipped the deploy because Pages
is off, and said the tree is not signed). The plugin is loaded by dnf as root on an installed system under SELinux
(row `update.replay-check`).

`offline.yml`'s gate ran too (run 43560436638: 27 vouched for, none left out).

Not run: the tag check and the attestation step of the CI's release job (they need a tag),
the schedule, the cache check inside a job, signing (no key), a hardware token, the plugin refusing a real replay
on an installed system, the real timer.
