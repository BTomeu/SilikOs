#!/usr/bin/env bash
# tests/offline/container_run.sh [MIRROR_DIR]: `silik mirror` with the real dnf, rpm and createrepo_c of EL 9, in
# almalinux:9 containers, as far as a machine without KVM goes (the offline ISO in a virtual machine is the workflow
# .github/workflows/offline.yml). What it shows, each step with its numbers (build/offline-test/run.log):
#   1  our packages; the mirror of the whole SilikOS set (MIRROR_DIR; made when it is not there: 2.7 GB), verified
#      in a container with no network device
#   2  a server and a client on an internal docker network (no route out: shown), the client a plain almalinux:9:
#      `silik mirror use URL`, `dnf install silik-tools silik-dev` from the mirror, `use off` byte for byte
#   3  the same from a folder, in a container started with --network none
#   4  tampering, each refused: a byte of a package; the same with metadata and manifest rewritten to agree; a byte
#      of repomd.xml
#   5  a newer SilikOS package: update, the client upgrades, and goes back
#   6  `--network none` from here on. A small mirror of real signed packages of the base (tzdata, three versions)
#      from a local stand-in for the source: create, update twice with --keep 2 (the oldest goes), metadata signed
#      with a key made here, a client that checks it; pack, a delta, unpack; an unsigned package refused
# Needs docker and the network (Docker Hub, repo.almalinux.org, dl.fedoraproject.org). Behind a proxy:
#   SILIK_OFFLINE_NET_ARGS="--network host -e https_proxy=... -v CA.crt:/etc/pki/ca-trust/source/anchors/ca.crt:ro"
#   (docker arguments of the containers that need the network), SILIK_OFFLINE_TOOLS_IMAGE (an almalinux:9 with
#   dnf-plugins-core createrepo_c rpm-build epel-release gnupg2, CRB enabled; made here when it is missing).
# Never starts firewalld or nftables; the containers of steps 2 to 6 have no route to the build machine's network.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
mirror=${1:-$root/build/mirrors/full}
work=$root/build/offline-test
tools=${SILIK_OFFLINE_TOOLS_IMAGE:-silik-offline-tools}
read -r -a netargs <<< "${SILIK_OFFLINE_NET_ARGS:-}"
net=silik-offline-net; server=silik-offline-server; client=silik-offline-client
silik="python3 /src/packages/silik-tools/files/silik"
rm -rf "$work"; mkdir -p "$work" "$(dirname "$mirror")"
exec > >(tee "$work/run.log") 2>&1
step() { echo; echo "=== $* ==="; }
cleanup() { docker rm -f $server ${server}2 $client > /dev/null 2>&1 || true; docker network rm $net > /dev/null 2>&1 || true; }
trap cleanup EXIT; cleanup
# run IMAGE ARGS... -- SCRIPT: a container with the repository (read-only) and the work folders
tool() { docker run --rm "$@"; }
vols=(-v "$root:/src:ro" -v "$work:/w" -v "$(dirname "$mirror"):/mirrors")
m=/mirrors/$(basename "$mirror")
echo "SilikOS offline test, $(date -u +%Y-%m-%dT%H:%MZ), commit $(git -C "$root" rev-parse --short HEAD 2>/dev/null || echo '?'), docker $(docker version --format '{{.Server.Version}}')"

step "0 the tools image ($tools)"
if ! docker image inspect "$tools" > /dev/null 2>&1; then
  docker rm -f silik-offline-mk > /dev/null 2>&1 || true
  docker run --name silik-offline-mk "${netargs[@]}" almalinux:9 bash -c 'dnf -y -q install dnf-plugins-core createrepo_c rpm-build epel-release gnupg2 && dnf config-manager --set-enabled crb'
  docker commit silik-offline-mk "$tools" > /dev/null; docker rm silik-offline-mk > /dev/null
fi
tool "$tools" bash -c 'cat /etc/redhat-release; rpm -q dnf dnf-plugins-core createrepo_c rpm gnupg2'

step "1a our packages (rpmbuild in EL 9, no network)"
tool --network none -v "$root:/src" -w /src "$tools" bash tools/build_rpms.sh | tail -10

step "1b the mirror of the SilikOS set"
if [ -f "$mirror/silik-mirror.json" ]; then
  echo "$mirror is there: not made again"
else
  tool "${netargs[@]}" "${vols[@]}" "$tools" bash -c "$silik mirror create $m --silikos /src/build/repo --yes" | grep -vE '^\([0-9]*/[0-9]*\): |^\[SKIPPED\]'
fi
tool --network none "${vols[@]}" "$tools" bash -c "$silik mirror status $m; du -sh --exclude=.root $m; du -sh $m/.root"

step "1c verify, in a container with no network device (--network none)"
tool --network none "${vols[@]}" "$tools" bash -c "echo network devices: \$(ls /sys/class/net); $silik mirror verify $m"

step "2a an internal network (docker network create --internal: no route out), the mirror served on it"
docker network create --internal $net > /dev/null
docker run -d --name $server --network $net "${vols[@]}" almalinux:9 $silik mirror serve $m --bind 0.0.0.0 --port 8080 > /dev/null
docker run -d --name $client --network $net -v "$root:/src:ro" -v "$work:/w" almalinux:9 sleep infinity > /dev/null
cx() { docker exec $client bash -c "$1" || echo "(the last command of this step: exit $?)"; }
sleep 2; docker logs $server
cx 'cat /etc/redhat-release; echo "the client has no route out:"; curl -sS -m 8 -o /dev/null https://repo.almalinux.org/ 2>&1; echo "curl to repo.almalinux.org: exit $?"; curl -sS -m 8 -o /dev/null http://1.1.1.1/ 2>&1; echo "curl to 1.1.1.1: exit $?"'
cx "curl -sS -o /dev/null -w 'the mirror answers: manifest HTTP %{http_code}, ' http://$server:8080/silik-mirror.json; curl -sS -o /dev/null -w 'dnf working folder HTTP %{http_code}, ' http://$server:8080/.root/; curl -sS -o /dev/null -w 'a listing HTTP %{http_code}, ' http://$server:8080/BaseOS/; curl -sS -o /dev/null -w 'a PUT HTTP %{http_code}\n' -X PUT -d x http://$server:8080/x"

step "2b a bare machine first needs dnf's config-manager: from the mirror, signature checked against the image's own key"
cx "sha256sum /etc/yum.repos.d/*.repo > /tmp/repos.before; ls /etc/pki/rpm-gpg/"
cx "dnf -y -q --disablerepo='*' --repofrompath=boot,http://$server:8080/BaseOS --setopt=boot.gpgcheck=1 --setopt=boot.gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-AlmaLinux-9 install dnf-plugins-core 2>&1 | tail -4; rpm -q dnf-plugins-core"

step "2c silik mirror use URL"
cx "$silik mirror use http://$server:8080 && echo && cat /etc/yum.repos.d/silikos-mirror.repo && echo && dnf repolist && $silik mirror status"

step "2d the installation from the mirror: dnf install silik-tools silik-dev"
cx "SECONDS=0; dnf -y install silik-tools silik-dev > /tmp/install.log 2>&1; rc=\$?; grep -E '^(Install|Upgrade) +[0-9]+ Package|^Total download size|^Installed size|^Complete|^Error|GPG' /tmp/install.log; echo \"dnf exit \$rc, \$SECONDS s\"; sed -n '/^Installing/,/^Transaction Summary/p' /tmp/install.log | grep -o 'silikos-mirror-[A-Za-z]*' | sort | uniq -c | tr '\n' ' '; echo; rpm -q silik-tools silik-dev; echo \"\$(rpm -qa | wc -l) packages installed in all\"; silik --version"

step "2e silik mirror use off: the repository files byte for byte as before; then on again"
cx "$silik mirror use off && sha256sum -c --quiet /tmp/repos.before && echo 'sha256sum -c: every repository file of before is as it was' ; ls /etc/yum.repos.d/ | tr '\n' ' '; echo; dnf -q repolist --enabled | awk 'NR>1 {print \$1}' | tr '\n' ' '; echo"
cx "$silik -q mirror use http://$server:8080 | tail -1"

step "3 from a folder, in a container started with --network none"
tool --network none "${vols[@]}" almalinux:9 bash -c "echo network devices: \$(ls /sys/class/net)
  dnf -y -q --disablerepo='*' --repofrompath=boot,file://$m/BaseOS --setopt=boot.gpgcheck=1 --setopt=boot.gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-AlmaLinux-9 install dnf-plugins-core 2>&1 | tail -2
  $silik -q mirror use $m | tail -2
  SECONDS=0; dnf -y install silik-tools silik-dev > /tmp/i.log 2>&1; rc=\$?; grep -E '^Install +[0-9]+ Package|^Total size|^Total download size|^Complete|^Error' /tmp/i.log; echo \"dnf exit \$rc, \$SECONDS s\"; rpm -q silik-tools silik-dev"

# (a package of the mirror the client has not installed yet)
victim=$(cx 'for p in bc lsof zip unzip rsync wget nano; do rpm -q $p > /dev/null 2>&1 || { dnf -q list --available $p > /dev/null 2>&1 && echo $p && break; }; done')
[ -n "$victim" ] || { echo "no package to tamper with"; exit 1; }
step "4a tampering: one byte of a package ($victim), in a copy of the mirror"
for t in t1 t2 t3; do cp -al "$mirror" "$work/$t"; rm -rf "$work/$t/.root"; done
python3 "$here/tamper.py" byte "$(ls "$work"/t1/*/Packages/$victim-[0-9]*.rpm)"
tool --network none "${vols[@]}" "$tools" bash -c "$silik -q mirror verify /w/t1; echo \"silik mirror verify: exit \$?\""
docker run -d --name ${server}2 --network $net "${vols[@]}" almalinux:9 $silik mirror serve /w/t1 --bind 0.0.0.0 --port 8081 > /dev/null; sleep 2
cx "$silik -q mirror use http://${server}2:8081 | tail -1; dnf -y install $victim > /tmp/t1.log 2>&1; echo \"dnf install $victim: exit \$?\"; grep -iE 'checksum|Error|GPG|digest' /tmp/t1.log | cut -c1-300 | head -6; rpm -q $victim"
docker rm -f ${server}2 > /dev/null

step "4b the same byte, and the mirror made to agree with itself (createrepo_c again, the manifest rewritten): only the signature can tell"
python3 "$here/tamper.py" byte "$(ls "$work"/t2/*/Packages/$victim-[0-9]*.rpm)"; vrepo=$(basename "$(dirname "$(dirname "$(ls "$work"/t2/*/Packages/$victim-[0-9]*.rpm)")")")
tool --network none "${vols[@]}" "$tools" bash -c "rm -rf /w/t2/$vrepo/repodata && createrepo_c --quiet /w/t2/$vrepo && python3 /src/tests/offline/tamper.py forge /w/t2 && { $silik -q mirror verify /w/t2; echo \"silik mirror verify: exit \$?\"; }"
docker run -d --name ${server}2 --network $net "${vols[@]}" almalinux:9 $silik mirror serve /w/t2 --bind 0.0.0.0 --port 8081 > /dev/null; sleep 2
cx "$silik -q mirror use http://${server}2:8081 | tail -1; dnf clean all > /dev/null; dnf -y install $victim > /tmp/t2.log 2>&1; echo \"dnf install $victim: exit \$?\"; grep -iE 'checksum|Error|GPG|digest|signature' /tmp/t2.log | cut -c1-300 | head -6; rpm -q $victim"
docker rm -f ${server}2 > /dev/null

step "4c one byte of repomd.xml (BaseOS)"
python3 "$here/tamper.py" byte "$work/t3/BaseOS/repodata/repomd.xml" "$(grep -b -o '<checksum type="sha256">' "$work/t3/BaseOS/repodata/repomd.xml" | head -1 | awk -F: '{print $1 + 30}')"
tool --network none "${vols[@]}" "$tools" bash -c "$silik -q mirror verify /w/t3 | grep -v '^●'; echo \"silik mirror verify: exit \${PIPESTATUS[0]}\""
docker run -d --name ${server}2 --network $net "${vols[@]}" almalinux:9 $silik mirror serve /w/t3 --bind 0.0.0.0 --port 8081 > /dev/null; sleep 2
cx "$silik mirror status http://${server}2:8081 | grep metadata; $silik -q mirror use http://${server}2:8081; echo \"silik mirror use: exit \$?\"
    dnf -y --disablerepo='*' --repofrompath=t3,http://${server}2:8081/BaseOS --nogpgcheck install tree > /tmp/t3.log 2>&1; echo \"dnf alone, pointed at it by hand: exit \$?\"; grep -iE 'checksum|Error|repomd' /tmp/t3.log | head -4"
docker rm -f ${server}2 > /dev/null
cx "$silik -q mirror use http://$server:8080 | tail -1"
rm -rf "$work"/t1 "$work"/t2 "$work"/t3

step "5 a newer package of SilikOS's own (silik-tools release 2, built in a copy): update, the client upgrades and goes back"
mkdir -p "$work/newer"; tar -C "$root" --exclude=./build --exclude=./.git -cf - . | tar -C "$work/newer" -xf -
sed -i 's/^Release: .*/Release:        2%{?dist}/' "$work/newer/packages/silik-tools/silik-tools.spec"
tool --network none -v "$work/newer:/n" -w /n "$tools" bash tools/build_rpms.sh | grep silik-tools
tool "${netargs[@]}" "${vols[@]}" "$tools" bash -c "$silik mirror update $m --silikos /w/newer/build/repo --yes" | grep -vE '^\([0-9]*/[0-9]*\): |^\[SKIPPED\]|^\$ (createrepo_c|modifyrepo_c)|repo from|^Last metadata|^Dependencies resolved|^Nothing to do|^Complete|^Metadata cache|kB/s|MB/s|^ |^=+$|^$|^Install|^Downloading|^DNF will|^Transaction|^-+$'
cx "$silik mirror status | sed -n 2p; dnf -y --refresh upgrade > /tmp/up.log 2>&1; echo \"dnf upgrade: exit \$?\"; grep -E '^(Upgrade|Install) +[0-9]+ Package|^Nothing to do|Problem' /tmp/up.log | cut -c1-200; rpm -q silik-tools"
echo "(the client is a container image: it has a package the SilikOS set does not, and its newer version must come with glibc's)"
tool "${netargs[@]}" "${vols[@]}" "$tools" bash -c "$silik -q mirror update $m --add glibc-minimal-langpack --yes" | grep -E '^generation|^silik:'
cx "dnf -y --refresh upgrade > /tmp/up.log 2>&1; echo \"dnf upgrade: exit \$?\"; grep -E '^(Upgrade|Install) +[0-9]+ Package|^Nothing to do|Problem' /tmp/up.log | cut -c1-200; rpm -q silik-tools glibc
    echo 'the installed package carries the plugin:'; silik mirror status | sed -n 1,2p
    dnf -q updateinfo summary 2>&1 | head -4
    dnf -y downgrade silik-tools > /tmp/down.log 2>&1; echo \"dnf downgrade silik-tools: exit \$?\"; rpm -q silik-tools"
cx "$silik mirror use off > /dev/null && sha256sum -c --quiet /tmp/repos.before && echo 'use off: every repository file of before is as it was'; ls /etc/yum.repos.d | tr '\n' ' '; echo"
cleanup

step "6a three versions of a signed package of the base (tzdata), for a stand-in source"
tool "${netargs[@]}" "${vols[@]}" "$tools" bash -c 'mkdir -p /w/up-src && cd /w/up-src && dnf -q download tzdata-2026a-1.el9 tzdata-2026b-1.el9 tzdata-2026c-1.el9_8 && ls'

step "6b --network none: a mirror of it, updated twice (--keep 2), signed with a key made here, packed, a delta, unpacked; an unsigned package refused"
cat > "$work/tz.sh" <<'EOF'
set -uo pipefail
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY      # (an image made behind a proxy keeps its variables)
silik="python3 /src/packages/silik-tools/files/silik"
echo "network devices: $(ls /sys/class/net | tr '\n' ' ')"
mkdir -p /up/Packages && cd /w
serve() { (cd /up && createrepo_c --quiet . ); }
cp up-src/tzdata-2026a-*.rpm /up/Packages/; serve
python3 -m http.server 9000 --bind 127.0.0.1 -d /up > /dev/null 2>&1 &
sleep 1
printf 'url --url=http://127.0.0.1:9000/\n%%packages\ntzdata\n%%end\n' > tz.ks
export GNUPGHOME=/w/gnupg; mkdir -p -m 700 $GNUPGHOME
gpg --batch --quiet --pinentry-mode loopback --passphrase '' --quick-generate-key 'Lab mirror (test) <lab@example.invalid>' rsa3072 sign never
fpr=$(gpg --batch --with-colons --list-keys | awk -F: '$1 == "fpr" {print $10; exit}')
gpg --batch --armor --export "$fpr" > /w/lab-key.asc
q() { grep -vE '^\$ (dnf|createrepo_c|modifyrepo_c|rpmkeys)|repo from|^Last metadata|^Dependencies|^===|^ |^$|^Install|^Total|^Installed size|^DNF will|^Downloading|^---|^Complete|^Metadata cache|^\(|^BaseOS|^Transaction' || true; }
echo "--- create (generation 1: tzdata 2026a)"; $silik mirror create /w/tz --ks tz.ks --bare --keep 2 --sign "$fpr" --yes | q
echo "--- the source gets 2026b: update"; cp up-src/tzdata-2026b-*.rpm /up/Packages/; serve
$silik mirror update /w/tz --yes | q; ls /w/tz/BaseOS/Packages
echo "--- across the air gap: the whole mirror (generation 2) packed, and unpacked in the lab"
$silik mirror pack /w/tz -o /w/tz-gen2.tar | q
$silik -q mirror unpack /w/tz-gen2.tar /w/lab --key /w/lab-key.asc | tail -2; ls /w/lab/BaseOS/Packages
echo "--- the source gets 2026c: update (--keep 2: the oldest goes)"; cp up-src/tzdata-2026c-*.rpm /up/Packages/; serve
$silik mirror update /w/tz --yes | q; ls /w/tz/BaseOS/Packages
echo "--- verify, with the lab's key"; $silik -q mirror verify /w/tz --key /w/lab-key.asc
echo "--- next week's stick: the delta since generation 2, unpacked over the lab's mirror"
$silik mirror pack /w/tz -o /w/tz-delta.tar --since-gen 2 | q
$silik -q mirror unpack /w/tz-delta.tar /w/lab --key /w/lab-key.asc | tail -2; ls /w/lab/BaseOS/Packages
echo "--- the delta over nothing"; $silik -q mirror unpack /w/tz-delta.tar /w/empty --key /w/lab-key.asc || echo "silik mirror unpack: exit $?"
echo "--- a client that checks the metadata's signature (silik mirror use DIR --key): dnf sees the versions that stay, and can go back"
rpm -q tzdata
$silik -q mirror use /w/lab --key /w/lab-key.asc | tail -1; grep -E 'repo_gpgcheck|gpgkey' /etc/yum.repos.d/silikos-mirror.repo
dnf -y -q --showduplicates list tzdata 2>&1 | grep -E 'tzdata|Error|GPG' ; dnf -y downgrade tzdata > /tmp/d.log 2>&1; echo "dnf downgrade tzdata: exit $?"; rpm -q tzdata
echo "--- somebody removes the newest version from the lab's mirror and makes it agree with itself (createrepo_c, manifest): a freeze"
rm /w/lab/BaseOS/Packages/tzdata-2026c-*.rpm; rm -rf /w/lab/BaseOS/repodata; createrepo_c --quiet /w/lab/BaseOS; python3 /src/tests/offline/tamper.py forge /w/lab
$silik -q mirror verify /w/lab --key /w/lab-key.asc | grep -v '^●' || true
dnf clean all > /dev/null; dnf -y -q --showduplicates list tzdata > /tmp/f.log 2>&1; echo "dnf, with repo_gpgcheck: exit $?"; grep -iE 'GPG|signature|Error' /tmp/f.log | head -3
$silik -q mirror use off | tail -1
echo "--- a package without a signature in the source (built here: hello-unsigned)"
mkdir -p /tmp/rb/SPECS && printf 'Name: hello-unsigned\nVersion: 1\nRelease: 1\nSummary: unsigned\nLicense: MIT\nBuildArch: noarch\n%%description\nunsigned\n%%files\n' > /tmp/rb/SPECS/h.spec
rpmbuild -bb --quiet --define '_topdir /tmp/rb' /tmp/rb/SPECS/h.spec && cp /tmp/rb/RPMS/noarch/hello-unsigned-1-1.noarch.rpm /up/Packages/; serve
printf 'url --url=http://127.0.0.1:9000/\n%%packages\ntzdata\nhello-unsigned\n%%end\n' > bad.ks
$silik mirror create /w/bad --ks bad.ks --bare --yes 2>&1 | q; echo "silik mirror create: exit ${PIPESTATUS[0]}"; ls -A /w/bad | tr '\n' ' '; echo; find /w/bad -name 'hello-unsigned*' | wc -l
ls -la /w/*.tar | awk '{print $5 " bytes", $9}'
EOF
tool --network none "${vols[@]}" "$tools" bash /w/tz.sh
echo
echo "=== done: $(date -u +%H:%MZ) ==="
