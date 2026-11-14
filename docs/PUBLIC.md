# Making the repository public: a list for the owner (13/11/2026)

An audit made by an agent of the tree, the whole history (128 commits, 1153 blobs) and what GitHub's API lets one
read. Nothing was rewritten or deleted. What could not be read from here (Actions secrets, deploy keys,
webhooks, collaborators, the runs' logs) is marked **[check it yourself]**. The names of GitHub's menus
may have changed a little [A].

## 1. Before pressing "Change visibility"

1. **The four releases carry 20 binaries without their source** (`eda-tools` 14, `wine-11.0` 3, `dev-tools` 2,
   `eda-optional` 1; GPL/LGPL/MPL; no `*.src.rpm`, the release `sources-archive` does not exist yet). Private is not
   distributing; public is. They are older than the SRPMs (12/11) and some do not even carry the licence file (netgen).
   What deletes nothing: turn them into drafts (a draft cannot be seen or downloaded from outside):
   ```bash
   for t in eda-tools eda-optional dev-tools wine-11.0; do gh release edit $t --repo BTomeu/SilikOs --draft; done
   ```
   Publish them again when each one has its SRPMs (point 4): `gh release edit TAG --repo BTomeu/SilikOs --draft=false`.
   The other option (your decision, it deletes): `gh release delete-asset TAG FILE -y` for the 20; the workflows make them again.
2. **Two documents are internal strategy**: `docs/COMMERCIAL.md` (business model, reference prices, our own legal
   risks) and `docs/STRATEGY.md`. They hold no secret; decide whether you want them to be read. Taking them out of
   the tree does not take them out of the history (commits cdebd32, b919050, 77b147f); taking them out of the history is rewriting it:
   `git filter-repo --invert-paths --path docs/COMMERCIAL.md --path docs/STRATEGY.md` and `git push --force` (it
   changes every hash; not recommended unless it is needed).
3. **The history of Actions becomes public**: 133 runs with their logs and 214 artifacts (RPMs without source;
   they expire after 90 days). **[check it yourself]** whether a log says anything you do not want. To delete them all:
   `gh run list --repo BTomeu/SilikOs --limit 200 --json databaseId -q '.[].databaseId' | xargs -n1 gh run delete --repo BTomeu/SilikOs`
4. **[check it yourself]** Settings → Secrets and variables → Actions (it should be empty: the workflows use only
   the run's token; the one exception, since 13/11, is the package signing key, which goes as a secret of
   the environment `package-signing`: `docs/REPO.md`), Environments, Deploy keys, Webhooks, Collaborators.
5. There is no `LICENSE`: the README says that the licence is not chosen and that until then all rights are reserved.
   Choose it soon (`docs/COMMERCIAL.md`, question 1): without a licence nobody may use the code.

## 2. Settings, when making it public

- **Actions → General → Fork pull request workflows**: *Require approval for all external contributors* (or "all
  outside collaborators"). The CI starts on `pull_request`: without this, a stranger can run 3 hours of
  machine time with a PR.
- **Actions → General → Workflow permissions**: *Read repository contents and packages permissions*; unticked,
  "Allow GitHub Actions to create and approve pull requests". (The workflows already ask for `contents: read` and
  only the jobs that say so write.)
- **Actions → General → Actions permissions**: *Allow BTomeu, and select non-BTomeu, actions* → only "Allow actions
  created by GitHub" (no other one is used).
- **Advanced Security** (formerly "Code security"): **Private vulnerability reporting** → Enable (it is where
  `SECURITY.md` points); Secret scanning and Push protection → Enable (free in a public repository).
- **Rules → Rulesets → New branch ruleset**, target `main` (only `main`: the workflow does `push --force` to
  `ci-results`): *Restrict deletions*, *Block force pushes*. Requiring a PR or checks for `main` is up to you (today
  you push to it directly).
- **Rules → New tag ruleset**, target `v*`: *Restrict creations* (with you as the exception). A `v*` tag makes a release
  with the ISO. Do not put it on the other tags (`eda-tools`, `dev-tools`, `wine-*`, `sources-archive`,
  `eda-tools-aarch64`): the workflows create them.
- **General**: Issues on (it is where the system's `BUG_REPORT_URL` points), Wiki off.

## 3. What starts by itself with the first push to `main`

Making it public starts nothing; the first push does, depending on the files it touches:

| Workflow | Starts if the push touches | What it does | Weight (measured in earlier runs, with fewer tools) |
|---|---|---|---|
| CI | anything outside `docs/`, README, `eda/`, `dev/`, `wine/` | tests, packages, the aarch64 ISO, the ISO installed in a VM; writes the branch `ci-results` | 14-47 min (17 runs) |
| EDA tools | `eda/**`, `tools/build_eda.sh`, `tools/release_keep.sh`, `eda.yml` | 14 tools + KiCad + 3D models + ngspice ARM; writes `eda-tools`, `eda-optional`, `eda-tools-aarch64`, `sources-archive` | 58-73 min (3 runs, with the cache); without the cache, hours (KiCad: limit 340 min) |
| Dev tools | `dev/**`, `tools/build_dev.sh`, `tools/release_keep.sh`, `dev.yml`, `packages/silik-dev/**` | 8 x86_64 tools + 3 ARM; writes `dev-tools`, `sources-archive` | 6 min (3 runs, when there were 2 tools) |
| Wine | `wine/**`, `tools/build_wine*.sh`, `tools/release_keep.sh`, `wine.yml` | Wine and the add-ons; writes `wine-<version>`, `sources-archive` | 2-5 min with the cache; about 30 min without [A: the workflow says so] |
| Bench | `tools/bench_ngspice_flags.sh`, `bench.yml` | measures, writes nothing | 15-17 min |
| Package repository | nothing directly: it starts when a CI of `main` or of a `v*` tag ends green, or if the push touches `site/**` | signs the packages and publishes the repository (`docs/REPO.md`); writes the releases `repo-el9-next`, `repo-el9-stable` and the Pages site | not run yet |

The merge of this round touches `eda.yml`, `tools/build_eda.sh` and `tools/build_dev.sh`: **CI, EDA tools and
Dev tools will start at the same time**, and EDA's caches are of no use (the script changes). When EDA tools, Dev
tools or Wine end, the CI starts again by itself (`workflow_run`) and cancels the CI that was running on `main`.

## 4. The order by hand so that the ISO finds the releases

1. **Wine** (Actions → Wine → Run workflow), **Dev tools** and **EDA tools** (the last two will already have started
   with the push; if not, by hand). They can run at the same time.
2. When they end: each release must have, for each package, its `*.src.rpm`
   (`gh release view TAG --repo BTomeu/SilikOs --json assets -q '.assets[].name'`). If you had turned them into
   drafts, publish them now (`--draft=false`).
3. **CI** by hand (Actions → CI → Run workflow) if it has not started by itself after step 2. A CI that runs while a
   release is a draft or is empty makes an ISO without those packages (it says so with a warning "no such release
   yet") and the checks that expect them fail: it is not the system, it is the order.
4. Look at the branch `ci-results` and `docs/STATUS.md`: everything that today says "written, not run" (ARM jobs,
   SRPMs, `release_keep.sh`, the new `results` job) will be seen here for the first time.

## 5. What stays open

- The old binaries that a new build of the same name replaces go to `sources-archive` without an SRPM of their own
  (the new one is of the same version). If you want the archive clean, delete the 20 old files before the first build (point 1.1).
- `installer/installer-base.css` comes from anaconda (GPL-2.0-or-later) [A: by its comments] and does not say so.
- Our own packages declare `License: LicenseRef-SilikVolt`, which is not defined.
- The actions (`actions/checkout@v4`, `upload-artifact@v4`, `download-artifact@v4`, `cache@v4`) and the image
  `almalinux:9` are pinned by tag, not by hash. They are GitHub's and AlmaLinux's; pinning them by hash is an improvement.
- "Binary identical to RHEL" still appears in `docs/PLAN.md`, `docs/STRATEGY.md` and `CLAUDE.md` (AlmaLinux says
  ABI compatibility: `docs/COMMERCIAL.md`, B3).
