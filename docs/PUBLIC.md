# Fer públic el repositori: llista per al propietari (13/11/2026)

Auditoria feta per un agent sobre l'arbre, tot l'historial (128 commits, 1153 blobs) i el que l'API de GitHub deixa
llegir. No s'ha reescrit ni esborrat res. El que no s'ha pogut llegir des d'aquí (secrets d'Actions, claus de
desplegament, webhooks, col·laboradors, logs dels runs) està marcat **[mira-ho tu]**. Els noms dels menús de GitHub
poden haver canviat una mica [A].

## 1. Abans de prémer "Change visibility"

1. **Les quatre releases porten 20 binaris sense la seva font** (`eda-tools` 14, `wine-11.0` 3, `dev-tools` 2,
   `eda-optional` 1; GPL/LGPL/MPL; cap `*.src.rpm`, la release `sources-archive` encara no existeix). Privat no és
   distribuir; públic sí. Són anteriors als SRPM (12/11) i alguns no porten ni el fitxer de llicència (netgen).
   El que no esborra res: passar-les a esborrany (un esborrany no es veu ni es pot baixar des de fora):
   ```bash
   for t in eda-tools eda-optional dev-tools wine-11.0; do gh release edit $t --repo BTomeu/SilikOs --draft; done
   ```
   Tornar-les a publicar quan cada una tingui els SRPM (punt 4): `gh release edit TAG --repo BTomeu/SilikOs --draft=false`.
   L'altra opció (decisió teva, esborra): `gh release delete-asset TAG FITXER -y` dels 20; els workflows els tornen a fer.
2. **Dos documents són estratègia interna**: `docs/COMERCIAL.md` (model de negoci, preus de referència, riscos legals
   propis) i `docs/ESTRATEGIA.md`. No tenen cap secret; decideix si vols que es llegeixin. Treure'ls de l'arbre no els
   treu de l'historial (commits cdebd32, b919050, 77b147f); treure'ls de l'historial és reescriure'l:
   `git filter-repo --invert-paths --path docs/COMERCIAL.md --path docs/ESTRATEGIA.md` i `git push --force` (canvia
   tots els hash; no recomanat si no cal).
3. **L'historial d'Actions passa a ser públic**: 133 execucions amb els seus logs i 214 artefactes (RPM sense font,
   caduquen al cap de 90 dies). **[mira-ho tu]** si un log diu res que no vulguis. Per esborrar-los tots:
   `gh run list --repo BTomeu/SilikOs --limit 200 --json databaseId -q '.[].databaseId' | xargs -n1 gh run delete --repo BTomeu/SilikOs`
4. **[mira-ho tu]** Settings → Secrets and variables → Actions (hauria d'estar buit: els workflows només fan servir
   el token del run), Environments, Deploy keys, Webhooks, Collaborators.
5. No hi ha `LICENSE`: el README diu que la llicència no està triada i que fins llavors tots els drets són reservats.
   Tria-la aviat (`docs/COMERCIAL.md`, pregunta 1): sense llicència ningú pot fer servir el codi.

## 2. Settings, en fer-lo públic

- **Actions → General → Fork pull request workflows**: *Require approval for all external contributors* (o "all
  outside collaborators"). El CI s'engega amb `pull_request`: sense això, un desconegut pot fer córrer 3 hores de
  màquina amb un PR.
- **Actions → General → Workflow permissions**: *Read repository contents and packages permissions*; desmarcat
  "Allow GitHub Actions to create and approve pull requests". (Els workflows ja demanen `contents: read` i només
  escriuen els jobs que ho diuen.)
- **Actions → General → Actions permissions**: *Allow BTomeu, and select non-BTomeu, actions* → només "Allow actions
  created by GitHub" (no se'n fa servir cap altra).
- **Advanced Security** (abans "Code security"): **Private vulnerability reporting** → Enable (és on apunta
  `SECURITY.md`); Secret scanning i Push protection → Enable (gratuït en un repositori públic).
- **Rules → Rulesets → New branch ruleset**, objectiu `main` (només `main`: el workflow fa `push --force` a
  `ci-results`): *Restrict deletions*, *Block force pushes*. Demanar PR o checks per a `main` és cosa teva (avui hi
  puges directament).
- **Rules → New tag ruleset**, objectiu `v*`: *Restrict creations* (amb tu com a excepció). Un tag `v*` fa una release
  amb la ISO. No el posis sobre els altres tags (`eda-tools`, `dev-tools`, `wine-*`, `sources-archive`,
  `eda-tools-aarch64`): els creen els workflows.
- **General**: Issues activat (és on apunta `BUG_REPORT_URL` del sistema), Wiki desactivat.

## 3. Què s'engega tot sol amb el primer push a `main`

Fer-lo públic no engega res; el primer push sí, segons els fitxers que toqui:

| Workflow | S'engega si el push toca | Què fa | Pes (mesurat en runs anteriors, amb menys eines) |
|---|---|---|---|
| CI | qualsevol cosa fora de `docs/`, README, `eda/`, `dev/`, `wine/` | tests, paquets, ISO aarch64, ISO instal·lada en una VM; escriu la branca `ci-results` | 14-47 min (17 runs) |
| EDA tools | `eda/**`, `tools/build_eda.sh`, `tools/release_keep.sh`, `eda.yml` | 14 eines + KiCad + models 3D + ngspice ARM; escriu `eda-tools`, `eda-optional`, `eda-tools-aarch64`, `sources-archive` | 58-73 min (3 runs, amb memòria cau); sense memòria cau, hores (KiCad: límit 340 min) |
| Dev tools | `dev/**`, `tools/build_dev.sh`, `tools/release_keep.sh`, `dev.yml`, `packages/silik-dev/**` | 8 eines x86_64 + 3 ARM; escriu `dev-tools`, `sources-archive` | 6 min (3 runs, quan eren 2 eines) |
| Wine | `wine/**`, `tools/build_wine*.sh`, `tools/release_keep.sh`, `wine.yml` | Wine i els complements; escriu `wine-<versió>`, `sources-archive` | 2-5 min amb memòria cau; uns 30 min sense [A: ho diu el workflow] |
| Bench | `tools/bench_ngspice_flags.sh`, `bench.yml` | mesura, no escriu res | 15-17 min |

El merge d'aquesta ronda toca `eda.yml`, `tools/build_eda.sh` i `tools/build_dev.sh`: **s'engegaran CI, EDA tools i
Dev tools alhora**, i les memòries cau d'EDA no serveixen (canvia l'script). Quan EDA tools, Dev tools o Wine acaben,
el CI torna a començar sol (`workflow_run`) i cancel·la el CI que hi hagués en marxa a `main`.

## 4. Ordre a mà perquè la ISO trobi les releases

1. **Wine** (Actions → Wine → Run workflow), **Dev tools** i **EDA tools** (els dos últims ja s'hauran engegat amb el
   push; si no, a mà). Poden anar alhora.
2. Quan acabin: cada release ha de tenir, per cada paquet, el seu `*.src.rpm`
   (`gh release view TAG --repo BTomeu/SilikOs --json assets -q '.assets[].name'`). Si les havies passat a esborrany,
   publica-les ara (`--draft=false`).
3. **CI** a mà (Actions → CI → Run workflow) si no s'ha engegat sol després del pas 2. Un CI que corre mentre una
   release és un esborrany o és buida fa una ISO sense aquells paquets (ho diu amb un avís "no such release yet") i
   les comprovacions que els esperen fallen: no és el sistema, és l'ordre.
4. Mira la branca `ci-results` i `docs/STATUS.md`: tot el que avui diu "written, not run" (jobs ARM, SRPM,
   `release_keep.sh`, el job `results` nou) es veurà aquí per primer cop.

## 5. Què queda obert

- Els binaris vells que un build nou del mateix nom substitueix van a `sources-archive` sense SRPM propi (el nou és
  de la mateixa versió). Si vols l'arxiu net, esborra els 20 fitxers vells abans del primer build (punt 1.1).
- `installer/installer-base.css` ve de l'anaconda (GPL-2.0-or-later) [A: pels seus comentaris] i no ho diu.
- Els paquets propis declaren `License: LicenseRef-SilikVolt`, que no està definida.
- Les accions (`actions/checkout@v4`, `upload-artifact@v4`, `download-artifact@v4`, `cache@v4`) i la imatge
  `almalinux:9` van fixades per etiqueta, no per hash. Són de GitHub i d'AlmaLinux; fixar-les per hash és una millora.
- "Binari idèntic a RHEL" encara surt a `docs/PLAN.md`, `docs/ESTRATEGIA.md` i `CLAUDE.md` (AlmaLinux diu
  compatibilitat ABI: `docs/COMERCIAL.md`, B3).
