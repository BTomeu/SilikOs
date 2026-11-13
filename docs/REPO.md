# El repositori de paquets de SilikOS (13/11/2026)

Perquè un SilikOS instal·lat rebi versions noves dels paquets propis (silik, l'escriptori, Wine, KiCad, ngspice,
OpenOCD...). Tot està fet menys una cosa, que només pots fer tu: **la clau de signatura**. Sense clau, el workflow
publica el repositori sense signar i ho diu, i cap sistema instal·lat se'l creu (els canals estan apagats i
`silik update channel` es nega a encendre'ls). Els noms dels menús de GitHub poden haver canviat una mica [A].

## 1. El que has de fer tu, una vegada

**1. Fes la clau al teu PC** (mai en una sessió al núvol, mai dins del repositori). Cal `gpg`: el porta el Git Bash
de Git per a Windows [A: mira `gpg --version`] i qualsevol Linux. Guarda-la on tens les altres claus:

```bash
export GNUPGHOME="$HOME/Documents/SilikVolt/licensing/private/silikos-gpg"
mkdir -p "$GNUPGHOME" && chmod 700 "$GNUPGHOME"
gpg --quick-generate-key "SilikOS packages (SilikVolt)" rsa4096 sign never    # et demana una contrasenya: posa-n'hi
gpg --list-secret-keys                                # l'empremta: 40 lletres i xifres; és FPR a les ordres de sota
gpg --armor --export-secret-keys FPR > "$GNUPGHOME/silikos-signing-private.asc"
```

- Fes-ne una còpia fora de línia (un USB al calaix). Si la perds no es pot signar res més amb ella: caldria canviar
  de clau (punt 4), i els sistemes que només tenen la vella no la rebrien.
- `rsa4096`, només per signar, sense subclau i sense caducitat. Per què:
  - L'rpm d'EL 9.8 (4.16.1.3-40), el gnupg 2.3.3 i el dnf 4.14 verifiquen tant RSA 4096 com ed25519: provat aquí el
    13/11/2026 amb dues claus de prova (paquets i metadades signats, instal·lats amb `dnf`). La suposició que EL 9 no
    porta bé ed25519 no val per a 9.8.
  - Tot i així, RSA 4096: és el que fan servir la clau d'AlmaLinux 9 (llegit: `rsa4096`) i la resta d'EL, funciona
    en mode FIPS [A: ed25519 no hi és aprovat a RHEL 9; no provat] i en rpm més antics.
  - Sense caducitat: una clau caducada deixaria tots els sistemes sense actualitzacions dels paquets propis, i el
    paquet que la renovaria no els arribaria [A: no provat amb una clau caducada]. El canvi de clau es fa amb una
    segona clau (punt 4).

**2. Dona-la al workflow, dins d'un environment** (`docs/PLAN.md`, decisió 10). A GitHub: Settings → Environments →
New environment → `package-signing`. A dins:

- **Environment secrets** → `SILIKOS_GPG_PRIVATE_KEY`: tot el contingut de `silikos-signing-private.asc` (amb les
  línies BEGIN i END); `SILIKOS_GPG_PASSPHRASE`: la contrasenya.
- **Deployment branches and tags** → Selected → només `main`.
- **Required reviewers** → tu, si vols que cada signatura esperi el teu vistiplau (és el que diu la decisió 10; el
  preu és que cada CI verd de `main` et demana un clic).

Amb `gh`, des del teu PC:
```bash
gh secret set SILIKOS_GPG_PRIVATE_KEY --env package-signing --repo BTomeu/SilikOs < "$GNUPGHOME/silikos-signing-private.asc"
gh secret set SILIKOS_GPG_PASSPHRASE --env package-signing --repo BTomeu/SilikOs      # te la demana
```

**3. Posa la clau pública al repositori** (només la pública), amb la versió del paquet pujada, i apunta l'empremta
aquí sota:

```bash
gpg --armor --export FPR > packages/silikos-repos/files/RPM-GPG-KEY-SilikOS
sed -i 's/^Version: .*/Version:        0.2.0/' packages/silikos-repos/silikos-repos.spec
python3 -m unittest discover -s tests       # diuen si el fitxer no és una clau pública, o si hi ha res privat a l'arbre
git add -A && git commit -m "The package signing key (public half)" && git push
```

Empremta de la clau de SilikOS: *(encara no n'hi ha)*

**4. Activa Pages**: Settings → Pages → Build and deployment → Source: **GitHub Actions**. A Settings → Actions →
General, "Allow actions created by GitHub" ja deixa passar les dues accions de Pages. Si tens una regla de tags, no
la posis sobre `repo-el9-*` (els crea el workflow).

**5. Engega'l i mira'l**: Actions → Package repository → Run workflow (canal `next`). El resum ha de dir `signed=yes`
i la teva empremta. Després:

```bash
curl -s https://btomeu.github.io/SilikOs/repo/el9/next/STATE
curl -s https://btomeu.github.io/SilikOs/repo/RPM-GPG-KEY-SilikOS | gpg --show-keys      # la teva empremta
# en net, un almalinux:9: instal·la un paquet nostre comprovant les dues signatures
docker run --rm almalinux:9 bash -c 'cd /tmp && curl -sO https://btomeu.github.io/SilikOs/repo/RPM-GPG-KEY-SilikOS &&
  dnf -y --repofrompath silikos,https://btomeu.github.io/SilikOs/repo/el9/next/x86_64/ --repo silikos \
    --setopt=silikos.gpgcheck=1 --setopt=silikos.repo_gpgcheck=1 \
    --setopt=silikos.gpgkey=file:///tmp/RPM-GPG-KEY-SilikOS install silikos-repos && rpm -qi silikos-repos | grep Signature'
```

L'adreça `https://btomeu.github.io/SilikOs/` és una suposició [A] (no s'hi arriba des de la sessió): el job `deploy`
diu l'adreça real, comprova que respon i avisa si no és la que porta `packages/silikos-repos/files/silikos.repo`.

**El canal stable** s'omple quan fas un tag `v*` (el seu CI verd el publica), o a mà: Run workflow amb canal
`stable` (pren l'últim CI verd de `main`, o el run que li diguis).

**Un sistema instal·lat abans de la clau** no té ni clau ni canal: no la pot rebre sola. Una vegada, a mà (mira
el número de versió a la release; després compara l'empremta amb la d'aquest document):

```bash
sudo dnf install https://github.com/BTomeu/SilikOs/releases/download/repo-el9-stable/silikos-repos-0.2.0-1.el9.noarch.rpm
gpg --show-keys /etc/pki/rpm-gpg/RPM-GPG-KEY-SilikOS
silik update channel stable
```

## 2. Com queda

- **Dos canals**, cadascun per a `x86_64` i `aarch64` (els paquets `noarch` són als dos): `stable` (el que ha
  publicat un tag `v*`) i `next` (cada CI verd de `main`). Es queden les tres últimes versions de cada paquet.
- **Les metadades a GitHub Pages** (`/repo/el9/<canal>/<arquitectura>/repodata/`; 188 kB tot el lloc a la prova, amb
  16 paquets per arquitectura) i **els paquets a dues
  releases** (`repo-el9-next`, `repo-el9-stable`); les metadades diuen l'adreça de cada paquet. Per què: un lloc de
  Pages no pot passar d'1 GB i té un límit tou de 100 GB al mes; els paquets ja pesen més de 750 MB (només els
  models 3D de KiCad, 376 MB) i falten KiCad i ARM. Una release no té límit de mida total ni de trànsit (2 GiB per
  fitxer, 1000 fitxers). Llegit el 13/11/2026 a la font de la documentació de GitHub (github/docs). És el que deia
  la decisió 10 del pla.
- **Tot signat**: cada paquet (`rpmsign`) i el `repomd.xml` de cada arquitectura (`repomd.xml.asc`). El sistema
  instal·lat comprova les dues coses sempre (`gpgcheck=1`, `repo_gpgcheck=1`).
- **El workflow** `.github/workflows/repo.yml`: `packages` (l'únic job que veu la clau; no té cap token que
  escrigui; mai l'engega un pull request) → `release` (puja els paquets signats) → `deploy` (la carpeta `site/` a
  l'arrel de Pages i el repositori a `/repo/`) → `prune` (treu les versions velles). A mà fa el mateix
  `tools/build_pkgrepo.sh`.
- **Al sistema instal·lat**: el paquet `silikos-repos` porta `/etc/yum.repos.d/silikos.repo` (els dos canals
  apagats) i, quan n'hi ha, la clau a `/etc/pki/rpm-gpg/RPM-GPG-KEY-SilikOS`. No toca els repositoris de la base ni
  `/etc/dnf/dnf.conf`, i no té cap script.
  - `silik update channel` diu quin canal hi ha; `silik update channel stable | next | off` el canvia ensenyant les
    ordres, i es nega si no hi ha clau.
  - `silik update` i l'actualització automàtica de cada dia agafen llavors també els paquets propis. Amb
    `silik update --auto security` no: el repositori no porta avisos de seguretat, i aquell mode només instal·la
    el que en té.
  - `silik doctor` diu el canal, o "SilikOS's own packages are not updated: no repository enabled".
  - Una instal·lació nova amb la clau surt amb `stable` encès (ho fa el kickstart). El repositori del medi
    d'instal·lació (`/silikos` de la ISO) no es queda al sistema instal·lat.
  - Si el repositori no respon, `dnf` el deixa de banda i segueix amb la base; si respon amb una signatura dolenta,
    també el deixa de banda i no n'instal·la res (provat).

## 3. El que això NO dona

- **Cap garantia de servei.** GitHub és l'únic punt: si cau, o tanca el compte, no hi ha actualitzacions dels
  paquets propis (les de la base segueixen). No hi ha miralls ni CDN propi.
- **Pages no és per fer-hi negoci**: les seves condicions diuen que no és un allotjament gratuït per a un negoci en
  línia. Un repositori de paquets d'un sistema obert hi cap [A ⚖️]; si SilikOS es ven, mou-lo (a sota).
- **La clau val el que val el compte de GitHub.** Qui pugui canviar el workflow de `main` o l'environment pot signar
  el que vulgui: 2FA al compte, i els "Required reviewers". Si no vols la clau a GitHub de cap manera, signa al teu
  PC amb `tools/build_pkgrepo.sh --gpg-name FPR` i puja l'arbre tu.
- **`next` no és una release provada**: és cada build de `main` que ha passat el CI.
- **Metadades velles**: qui controli la xarxa pot servir metadades antigues ben signades i amagar una actualització
  [A: dnf no mira l'edat de les metadades]. No pot fer instal·lar res que tu no hagis signat.
- Una versió ja publicada no es torna a publicar amb un altre contingut: si canvies un paquet sense pujar-li la
  versió, el workflow avisa i deixa el publicat.

**Tenir-ne una còpia en un altre lloc** (un servidor web qualsevol; en un EL 9 o un contenidor `almalinux:9` amb
`rpm-sign createrepo_c dnf-utils`):

```bash
gh release download repo-el9-stable --repo BTomeu/SilikOs --pattern '*.rpm' --dir pub
bash tools/build_pkgrepo.sh --out mirror --channel stable --published pub --gpg-name FPR --keep 0
rsync -a --delete mirror/ usuari@servidor:/var/www/silikos/repo/
```

Els paquets queden idèntics (ja signats); les metadades es fan i se signen de nou, amb els paquets dins de l'arbre.
Després, la segona adreça a `baseurl` de `silikos.repo` (una per línia): `dnf` passa a la segona si la primera no
respon (provat). Un sistema que ja té un canal encès rep el fitxer nou com a `silikos.repo.rpmnew`, i
`silik update channel stable` el pren.

**El nom de host** segueix obert (decisió 10): amb un domini teu a Pages (Settings → Pages → Custom domain) i a
`silikos.repo`, el repositori es pot moure sense tocar cap sistema instal·lat. Decideix-ho abans que hi hagi
sistemes amb el canal encès.

## 4. Canviar de clau

1. Fes la clau nova (punt 1.1) i afegeix-la al fitxer públic, darrere de la vella:
   `gpg --armor --export FPR_NOVA >> packages/silikos-repos/files/RPM-GPG-KEY-SilikOS`. Puja la versió de
   `silikos-repos`. Es publica signat amb la vella, i els sistemes el reben.
2. Espera setmanes, no dies. Cada sistema rep el fitxer amb les dues claus, i el servei de l'actualització diària
   (`silikos-update.service`) el torna a posar al clauer d'rpm abans de cada execució.
3. Llavors canvia els dos secrets per la clau nova. Si la privada no és cap de les públiques del fitxer, el
   workflow s'atura i no publica res.
4. Quan no quedi cap paquet signat amb la vella als canals, treu-la del fitxer.

Per què el pas 2 és al servei: el `dnf-automatic` d'EL 9.8 no importa cap clau tot sol, i un sol paquet signat amb
una clau que rpm no coneix li atura tota l'actualització, la de la base inclosa (vist aquí). Amb la línia del
servei, la mateixa prova acaba bé. `silik update` i `silik update channel stable` també la importen.

Un sistema que hagi estat apagat durant tot el canvi només té la clau vella: no pot verificar les metadades noves,
`dnf` deixa el repositori de banda (la base segueix) i cal el pas a mà del final del punt 1 [A: deduït de les
proves de signatura dolenta, no provat tal qual].

## 5. Què s'ha executat i què no

Executat aquí (contenidor AlmaLinux 9.8, claus de prova fetes dins del contenidor i esborrades): signar, `dnf`
instal·lant des de l'arbre, un byte canviat a un paquet o a les metadades rebutjat, el repositori repartit entre dos
servidors amb una redirecció (com Pages i les releases), `silik update channel`, l'actualització automàtica, el
canvi de clau, el mirall, i els passos del workflow que no necessiten GitHub. **No executat**: el workflow a GitHub
(l'artefacte del CI, pujar a les releases, Pages, l'environment), l'adreça real de Pages, res en un sistema
instal·lat de veritat ni en un `aarch64` de veritat. `docs/STATUS.md` té les files.
