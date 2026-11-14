# SilikOS's package repository (13/11/2026)

So that an installed SilikOS receives new versions of its own packages (silik, the desktop, Wine, KiCad, ngspice,
OpenOCD...). Everything is done except one thing, which only you can do: **the signing key**. Without a key, the
workflow publishes the repository unsigned and says so, and no installed system trusts it (the channels are off and
`silik update channel` refuses to turn them on). The names of GitHub's menus may have changed a little [A].

## 1. What you have to do, once

**1. Make the key on your PC** (never in a cloud session, never inside the repository). It needs `gpg`: the Git Bash
of Git for Windows has it [A: check `gpg --version`] and so does any Linux. Keep it where you have the other keys:

```bash
export GNUPGHOME="$HOME/Documents/SilikVolt/licensing/private/silikos-gpg"
mkdir -p "$GNUPGHOME" && chmod 700 "$GNUPGHOME"
gpg --quick-generate-key "SilikOS packages (SilikVolt)" rsa4096 sign never    # it asks you for a passphrase: give it one
gpg --list-secret-keys                                # the fingerprint: 40 letters and digits; it is FPR in the commands below
gpg --armor --export-secret-keys FPR > "$GNUPGHOME/silikos-signing-private.asc"
```

- Make an offline copy of it (a USB stick in the drawer). If you lose it, nothing more can be signed with it: the
  key would have to be changed (point 4), and the systems that have only the old one would not receive the new one.
- `rsa4096`, for signing only, without a subkey and without an expiry date. Why:
  - EL 9.8's rpm (4.16.1.3-40), gnupg 2.3.3 and dnf 4.14 verify both RSA 4096 and ed25519: tried here on
    13/11/2026 with two test keys (packages and metadata signed, installed with `dnf`). The assumption that EL 9
    does not handle ed25519 well does not hold for 9.8.
  - Even so, RSA 4096: it is what AlmaLinux 9's key (read: `rsa4096`) and the rest of EL use, it works
    in FIPS mode [A: ed25519 is not approved there in RHEL 9; not tried] and in older rpm.
  - Without an expiry date: an expired key would leave every system without updates of SilikOS's own packages, and
    the package that would renew it would not reach them [A: not tried with an expired key]. A change of key is made
    with a second key (point 4).

**2. Give it to the workflow, inside an environment** (`docs/PLAN.md`, decision 10). On GitHub: Settings → Environments →
New environment → `package-signing`. Inside it:

- **Environment secrets** → `SILIKOS_GPG_PRIVATE_KEY`: the whole content of `silikos-signing-private.asc` (with the
  BEGIN and END lines); `SILIKOS_GPG_PASSPHRASE`: the passphrase.
- **Deployment branches and tags** → Selected → only `main`.
- **Required reviewers** → you, if you want each signature to wait for your approval (it is what decision 10 says;
  the price is that every green CI of `main` asks you for a click).

With `gh`, from your PC:
```bash
gh secret set SILIKOS_GPG_PRIVATE_KEY --env package-signing --repo BTomeu/SilikOs < "$GNUPGHOME/silikos-signing-private.asc"
gh secret set SILIKOS_GPG_PASSPHRASE --env package-signing --repo BTomeu/SilikOs      # it asks you for it
```

**3. Put the public key in the repository** (the public one only), with the package's version raised, and write
the fingerprint down here below:

```bash
gpg --armor --export FPR > packages/silikos-repos/files/RPM-GPG-KEY-SilikOS
sed -i 's/^Version: .*/Version:        0.2.0/' packages/silikos-repos/silikos-repos.spec
python3 -m unittest discover -s tests       # they say whether the file is not a public key, or whether anything private is in the tree
git add -A && git commit -m "The package signing key (public half)" && git push
```

Fingerprint of SilikOS's key: *(there is none yet)*

**4. Turn Pages on**: Settings → Pages → Build and deployment → Source: **GitHub Actions**. In Settings → Actions →
General, "Allow actions created by GitHub" already lets the two Pages actions through. If you have a tag rule, do
not put it on `repo-el9-*` (the workflow creates them).

**5. Start it and look at it**: Actions → Package repository → Run workflow (channel `next`). The summary must say
`signed=yes` and your fingerprint. Then:

```bash
curl -s https://btomeu.github.io/SilikOs/repo/el9/next/STATE
curl -s https://btomeu.github.io/SilikOs/repo/RPM-GPG-KEY-SilikOS | gpg --show-keys      # your fingerprint
# from clean, an almalinux:9: it installs one of our packages, checking the two signatures
docker run --rm almalinux:9 bash -c 'cd /tmp && curl -sO https://btomeu.github.io/SilikOs/repo/RPM-GPG-KEY-SilikOS &&
  dnf -y --repofrompath silikos,https://btomeu.github.io/SilikOs/repo/el9/next/x86_64/ --repo silikos \
    --setopt=silikos.gpgcheck=1 --setopt=silikos.repo_gpgcheck=1 \
    --setopt=silikos.gpgkey=file:///tmp/RPM-GPG-KEY-SilikOS install silikos-repos && rpm -qi silikos-repos | grep Signature'
```

The address `https://btomeu.github.io/SilikOs/` is an assumption [A] (it cannot be reached from the session): the
job `deploy` says the real address, checks that it answers and warns if it is not the one
`packages/silikos-repos/files/silikos.repo` has.

**The stable channel** fills when you make a `v*` tag (its green CI publishes it), or by hand: Run workflow with
channel `stable` (it takes the last green CI of `main`, or the run you tell it).

**A system installed before the key** has neither key nor channel: it cannot receive the key by itself. Once, by
hand (look at the version number in the release; then compare the fingerprint with the one in this document):

```bash
sudo dnf install https://github.com/BTomeu/SilikOs/releases/download/repo-el9-stable/silikos-repos-0.2.0-1.el9.noarch.rpm
gpg --show-keys /etc/pki/rpm-gpg/RPM-GPG-KEY-SilikOS
silik update channel stable
```

## 2. How it ends up

- **Two channels**, each for `x86_64` and `aarch64` (the `noarch` packages are in both): `stable` (what a `v*` tag
  has published) and `next` (every green CI of `main`). The last three versions of each package are kept.
- **The metadata on GitHub Pages** (`/repo/el9/<channel>/<architecture>/repodata/`; 188 kB the whole site in the test,
  with 16 packages per architecture) and **the packages in two
  releases** (`repo-el9-next`, `repo-el9-stable`); the metadata say the address of each package. Why: a Pages site
  cannot exceed 1 GB and has a soft limit of 100 GB a month; the packages already weigh more than 750 MB (KiCad's
  3D models alone, 376 MB) and KiCad and ARM are still missing. A release has no limit of total size or of traffic
  (2 GiB per file, 1000 files). Read on 13/11/2026 in the source of GitHub's documentation (github/docs). It is what
  decision 10 of the plan said.
- **Everything signed**: each package (`rpmsign`) and the `repomd.xml` of each architecture (`repomd.xml.asc`). The
  installed system always checks both (`gpgcheck=1`, `repo_gpgcheck=1`).
- **The workflow** `.github/workflows/repo.yml`: `packages` (the only job that sees the key; it has no token that
  writes; a pull request never starts it) → `attest` (GitHub signs where each file comes from: `docs/SIGNING.md`) →
  `release` (uploads the signed packages) → `deploy` (the folder `site/` at the root of Pages and the repository at
  `/repo/`; it is skipped, without failing, while Pages is not turned on) → `prune` (removes the old versions). By
  hand, `tools/build_pkgrepo.sh` does the same. On days 1 and 15 of each month it publishes the metadata again with
  a new revision, when there is a key.
- **Where each package comes from**: a package of a tool (KiCad, Wine, OpenOCD...) enters the repository only if it
  has the attestation of the workflow that made it (`docs/SIGNING.md`). The first time, *EDA tools*, *Dev tools* and
  *Wine* have to be started once (Actions → Run workflow): until then the repository carries only SilikOS's own packages.
- **On the installed system**: the package `silikos-repos` carries `/etc/yum.repos.d/silikos.repo` (the two channels
  off) and, when there is one, the key at `/etc/pki/rpm-gpg/RPM-GPG-KEY-SilikOS`. It does not touch the base's
  repositories or `/etc/dnf/dnf.conf`, and it has no script.
  - `silik update channel` says which channel is on; `silik update channel stable | next | off` changes it, showing
    the commands, and refuses if there is no key.
  - `silik update` and the daily automatic update then take SilikOS's own packages too. With
    `silik update --auto security` they do not: the repository carries no security advisories, and that mode
    installs only what has one.
  - `silik doctor` says the channel, or "SilikOS's own packages are not updated: no repository enabled".
  - A new installation with the key comes out with `stable` on (the kickstart does it). The repository of the
    installation medium (`/silikos` of the ISO) does not stay on the installed system.
  - If the repository does not answer, `dnf` leaves it aside and goes on with the base; if it answers with a bad
    signature, it also leaves it aside and installs nothing from it (tried).

## 3. What this does NOT give

- **No guarantee of service.** GitHub is the single point: if it goes down, or closes the account, there are no
  updates of SilikOS's own packages (the base's go on). There are no mirrors and no CDN of our own.
- **Pages is not for doing business on**: its terms say that it is not free hosting for an online
  business. A package repository of an open system fits there [A ⚖️]; if SilikOS is sold, move it (below).
- **The key is worth what the GitHub account is worth.** Whoever can change the workflow of `main` or the
  environment can sign whatever they want: 2FA on the account, and the "Required reviewers". If you do not want the
  key on GitHub at all (it is what `docs/SIGNING.md` recommends for the channel `stable`), sign on your PC with
  `tools/sign_release.sh --key FPR` (it calls `tools/build_pkgrepo.sh --gpg-name FPR`, verifies the result with the
  public key alone and accepts no key from the environment) and upload the tree yourself.
- **`next` is not a tested release**: it is every build of `main` that has passed the CI.
- **Old metadata**: `dnf` by itself does not look at whether the metadata are the latest (tried: with an old tree,
  well signed, it installs the old package). Now each `repomd.xml` carries a revision under the signature, and the
  `dnf` plugin of the package `silikos-repos` rejects the ones that are older than those the system has already
  seen, or those of the other channel (tried; `docs/SIGNING.md`). What remains: holding updates back cannot be
  prevented, only warned about (at 45 days [PROPOSAL]), and a newly installed system has no memory. It cannot make
  a system install anything that you have not signed.
- A version already published is not published again with other content: if you change a package without raising
  its version, the workflow warns and leaves the published one.

**Keeping a copy of it somewhere else** (any web server; on an EL 9 or an `almalinux:9` container with
`rpm-sign createrepo_c dnf-utils`):

```bash
gh release download repo-el9-stable --repo BTomeu/SilikOs --pattern '*.rpm' --dir pub
bash tools/build_pkgrepo.sh --out mirror --channel stable --published pub --gpg-name FPR --keep 0
rsync -a --delete mirror/ user@server:/var/www/silikos/repo/
```

The packages stay identical (already signed); the metadata are made and signed again, with the packages inside the
tree. Then, the second address in `baseurl` of `silikos.repo` (one per line): `dnf` goes to the second if the first
does not answer (tried). A system that already has a channel on receives the new file as `silikos.repo.rpmnew`, and
`silik update channel stable` takes it.

**The host name** is still open (decision 10): with a domain of yours on Pages (Settings → Pages → Custom domain)
and in `silikos.repo`, the repository can be moved without touching any installed system. Decide it before there
are systems with the channel on.

## 4. Changing the key

1. Make the new key (point 1.1) and add it to the public file, after the old one:
   `gpg --armor --export FPR_NEW >> packages/silikos-repos/files/RPM-GPG-KEY-SilikOS`. Raise the version of
   `silikos-repos`. It is published signed with the old one, and the systems receive it.
2. Wait weeks, not days. Each system receives the file with the two keys, and the service of the daily update
   (`silikos-update.service`) puts it into rpm's keyring again before each run.
3. Then change the two secrets to the new key. If the private key is none of the public ones in the file, the
   workflow stops and publishes nothing.
4. When no package signed with the old one is left in the channels, take it out of the file.

Why step 2 is in the service: EL 9.8's `dnf-automatic` imports no key by itself, and a single package signed with
a key that rpm does not know stops its whole update, the base's included (seen here). With the service's line, the
same test ends well. `silik update` and `silik update channel stable` import it too.

A system that was switched off during the whole change has only the old key: it cannot verify the new metadata,
`dnf` leaves the repository aside (the base goes on) and it needs the step by hand at the end of point 1 [A:
deduced from the bad-signature tests, not tried as such].

## 5. What ran and what did not

Ran here (an AlmaLinux 9.8 container, test keys made inside the container and deleted): signing, `dnf`
installing from the tree, a byte changed in a package or in the metadata rejected, the repository split between two
servers with a redirection (as Pages and the releases are), `silik update channel`, the automatic update, the
change of key, the mirror, and the steps of the workflow that do not need GitHub. **Not run**: the workflow on GitHub
(the CI's artifact, uploading to the releases, Pages, the environment), the real address of Pages, anything on a
really installed system or on a real `aarch64`. `docs/STATUS.md` has the rows.
