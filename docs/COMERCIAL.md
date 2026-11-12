# SilikOS: compliment i model de negoci (12/11/2026)

Auditoria tècnica del repositori i lectura de fonts públiques feta per un agent i revisada. **No és consell legal**:
els punts marcats ⚖️ els ha de mirar un advocat abans de vendre res. [A] vol dir suposició. Les polítiques d'AlmaLinux
i Red Hat es van llegir a partir de fragments del cercador (la xarxa de la sessió no hi arribava): cal llegir-les
senceres abans de decidir.

## Estat del repositori

- No hi ha cap `LICENSE` ni `COPYING`.
- Els paquets propis declaren `License: LicenseRef-SilikVolt`, que no està definida enlloc.
- Cap script genera SRPMs (`rpmbuild -bb` només). **Ara sí** (12/11/2026): tots els scripts de build fan l'SRPM
  (`build/srpm/`), vegeu la secció 2.
- El repositori és privat.
- Els workflows esborren les versions antigues de les releases. **Ja no** (12/11/2026): les mouen a la release
  `sources-archive` amb el seu SRPM (`tools/release_keep.sh`).
- `build_iso.sh` redistribueix la boot ISO d'AlmaLinux modificada.

Mentre tot sigui privat no es distribueix a tercers [A]. Tot el que ve a continuació bloqueja la primera ISO pública,
i encara més la primera venda.

## 1. Bloquejants abans de distribuir o vendre

### B1. Llicència pròpia

Sense `LICENSE`, ningú té dret a redistribuir SilikOS.
- L'extensió del shell es carrega dins de gnome-shell (GPL-2.0+): ha de tenir una llicència compatible amb la GPL [A].
- `installer/installer-base.css` probablement ve d'anaconda (GPL-2.0+) [A]: cal atribuir-lo o reescriure'l.

### B2. Font corresponent (GPL/LGPL/MPL)

Compilar des de tags fixats d'upstream no n'hi ha prou:
- **GPLv2 §3** (openocd, dfu-util, stm32flash, klayout, xschem, qucs-s…): una distribució comercial ha d'anar amb la
  font o amb una oferta escrita vàlida 3 anys.
- **Els nostres specs i scripts** formen part de la font corresponent.
- **Wine Mono/Gecko** (MPL-2.0 §3.2): cal dir on és la font.
- **La boot ISO modificada:** també ens toca oferir la font dels paquets GPL que porta (kernel, grub2, anaconda…).

### B3. Marques AlmaLinux i Red Hat

- **AlmaLinux:** podem usar el nom (no els logos) per descriure l'origen amb veritat. El nostre branding ha de ser més
  prominent.
- **Logos d'AlmaLinux:** cal revisar què es veu encara de `almalinux-logos` i de l'Initial Setup [A].
- **"Binari a binari" és fals:** des del 2023, AlmaLinux apunta a **compatibilitat ABI** amb RHEL, no a una còpia 1:1.
- **Red Hat:** el nom es pot usar per descriure la compatibilitat amb veritat, sense logos i amb una nota d'atribució.
- **Frase segura:** *"SilikOS is built on AlmaLinux OS 9, which aims for ABI compatibility with Red Hat® Enterprise
  Linux® 9. SilikOS is not affiliated with or endorsed by Red Hat or the AlmaLinux OS Foundation."*

### B4. Vendre a la UE ⚖️

- **Responsabilitat per productes (Directiva 2024/2853):**
  - S'aplica a productes posats al mercat a partir del 9/12/2026, i hi entra el programari.
  - El programari lliure en queda fora només si no és activitat comercial.
- **Cyber Resilience Act (Reglament 2024/2847):**
  - La notificació de vulnerabilitats explotades s'aplica des de l'11/9/2026.
  - L'aplicació plena és l'11/12/2027.
  - Monetitzar SilikOS en si pot convertir SilikVolt en "fabricant" [A ⚖️].
- **Venda a particulars:** les garanties legals del consumidor s'apliquen igualment (Directiva 2019/770).

### B5. SilikStudio a la ISO

És agregació, i això és correcte. Però és propietari: necessita la seva EULA, visible i separada dels avisos GPL.

## 2. Llista de feina al repositori (per quan el propietari decideixi la llicència)

**Llicències i marca**
1. Un `LICENSE` a l'arrel (proposta: GPL-3.0-or-later per al codi de SilikOS).
2. Per a la marca:
   - `brand/LICENSE` i `TRADEMARKS.md`: tots els drets reservats.
   - Es permet redistribuir la ISO sense modificar; qui la modifiqui ha de treure la marca.
   - Proposta de registrar SilikOS i SilikVolt a l'EUIPO ⚖️.
3. `LicenseRef-SilikVolt` → l'SPDX triat, amb `%license LICENSE` a cada spec, i capçaleres SPDX als fitxers de codi.

**Metadades dels paquets d'upstream**
4. `LicenseRef-Upstream` (magic, netgen, ngspice, yosys) → l'SPDX real de cada tag. **Fet** (12/11/2026, llegit als
   fitxers de llicència de cada versió fixada): magic `HPND-UC-export-US` + dos avisos que no són a la llista SPDX
   (`LicenseRef-`, amb el text al paquet), netgen `GPL-1.0-or-later`, ngspice i yosys per parts (vegeu els specs).
5. `%licences` (`eda/common.inc`): ha d'aplegar més noms i fer fallar la build si no en troba cap. **Fet**: LICENSE*,
   LICENCE*, COPYING*, COPYRIGHT* en qualsevol caixa (el de netgen és `Copying` i abans no es copiava), més els fitxers
   que se li passin; si no en troba cap, la build s'atura.
6. Llicències que falten: **fet**.
   - les parts de sigrok (els quatre COPYING);
   - els subpaquets de Wine Mono/Gecko (`%license`, SPDX: el de Mono és la lectura de Fedora [A], Gecko MPL-2.0);
   - els paquets Python de silik-pylab (els fitxers de llicència de cada dist-info, o de l'arxiu font; si un paquet no
     en té, la build s'atura);
   - l'OFL de Cascadia Mono a `installer/product/` (el `LICENSE` de microsoft/cascadia-code al tag v2102.03, la versió
     de la font).

**Font corresponent**
7. SRPMs a tots els scripts de build, publicats a la mateixa release. **Fet** als scripts (`build_rpms.sh`,
   `build_eda.sh`, `build_dev.sh`, `build_wine.sh`, `build_wine_addons.sh`) i als workflows; els workflows no s'han
   executat (GitHub no engega jobs).
8. Deixar d'esborrar les versions antigues: moure-les a una release d'arxiu i conservar-les 3 anys. **Fet**:
   `tools/release_keep.sh` les mou a `sources-archive` i no n'esborra mai res. Els binaris publicats abans d'avui no
   tenen SRPM: el primer build nou en publica la font.
9. `tools/fetch_base_sources.sh`: els SRPMs dels paquets de la boot ISO (des de vault.almalinux.org), i la font de
   Wine Mono/Gecko. **Fet**: l'script (provat amb ISOs de prova; vault.almalinux.org no s'ha pogut provar des d'aquí),
   i les fonts de Wine Mono i Wine Gecko van dins l'SRPM de `silik-wine-addons`.
10. `/LEGAL.txt` a la ISO, amb:
    - els components i les seves llicències;
    - on és la font i l'oferta escrita;
    - les marques i la renúncia de garantia.
11. La font ha de ser pública: el repositori, o un mirall dels specs i les fonts.

**Textos, privacitat i proves**
12. Corregir "binari a binari" als textos.
13. `docs/PRIVACY.md`: quins servidors es contacten (mirrors d'AlmaLinux i EPEL, docker.io i vault.centos.org per a
    `silik eda`, NVIDIA si es tria, i el futur repositori de SilikOS). `silik` no envia telemetria.
14. Tests: `test_licences.py` (SPDX vàlid, llicència a cada RPM, SRPM per a cada RPM). **En part**:
    `tests/test_sources.py` comprova la forma de les expressions, el macro que atura la build sense llicència, i que
    cada script fa l'SRPM. No valida els identificadors contra la llista SPDX.
**Cadena de subministrament** (auditoria 12/11/2026): **fet**. Cada font descarregada es comprova: arxius per sha256
(`eda/versions`, `dev/versions`, `wine/sources`), arbres git pel commit, Wine per la signatura de Julliard, la boot ISO
pel CHECKSUM signat d'AlmaLinux (empremtes fixades als scripts).
15. Amb els fabricants (Cadence, Vector, Altium, ST…), només ús nominatiu: "pot executar X amb la teva llicència". Mai
    "suportat" ni "certificat", i cap logo.

## 3. Model de negoci

| Empresa | Model | Preu públic |
|---|---|---|
| Red Hat | RHEL Workstation, self-support | 197 $/any i sistema (MSRP de revenedor) |
| Canonical | Ubuntu Pro Desktop | 25 $/any (self-support), 300 $/any (24/7); gratis fins a 5 màquines personals |
| CIQ | Rocky Linux from CIQ Pro | 350 / 600 / 825 $ per node i any |
| TuxCare | Suport d'AlmaLinux | Per pressupost, o paquets d'hores |
| Slimbook, System76 | Maquinari | KDE Slimbook VI: 1.099 € de llançament |
| Bluefin | Donacions | — |
| IIC-OSIC-TOOLS (JKU) | Imatge EDA gratuïta, finançada per la universitat | — |

Efabless va tancar el març de 2025 per falta de finançament: un model només de servei, sense ingressos recurrents, és
fràgil.

**O1. Posada en marxa EDA/banc (servei).**
- Què inclou:
  - migrar el flux d'un client a SilikOS: capses EDA i llicències FlexLM;
  - una VM de Windows amb passthrough USB;
  - un banc CAN.
- Infraestructura: poca.
- Riscos: no escala i depèn d'una persona.
- Regulació: menys exposat a la PLD i el CRA [A ⚖️].

**O2. SilikOS gratuït com a canal de SilikStudio.**
- Què es ven: la llicència de SilikStudio.
- Què cal: el repositori públic signat i l'EULA de SilikStudio.
- Esforç: 2–4 setmanes [A].

**O3. SilikOS Teams/Edu, subscripció per lloc.**
- Què inclou: un canal Pro signat amb actualitzacions esglaonades, un mirall local per al laboratori, configuració de
  flota i suport amb SLA.
- Preu: per decidir [A], prenent com a referència els preus d'Ubuntu Pro.
- Què cal:
  - repositori signat, mirall de fonts i procés de suport;
  - el procés del CRA: punt de contacte, i notificar a ENISA en 24 h si hi ha una vulnerabilitat explotada.
- Esforç: 2–3 mesos [A].

**O4. Portàtil certificat amb un partner** (per exemple Slimbook, a València [A]).
- Què cal: una matriu de proves de maquinari, garantia de consumidor i logística.
- Esforç: molt alt; cal capital.

**Recomanació de l'agent:**
1. Començar per **O1 + O2**: SilikOS gratuït i redistribuïble, amb una política de marca.
2. Construir el repositori signat i públic, que serveix per a O2 i per a O3.
3. Passar a O3 quan hi hagi 2–3 clients d'O1 i el procés del CRA estigui escrit.
4. O4 només després d'una instal·lació real verificada.

## 4. Preguntes per al propietari

1. Llicència del codi propi: GPL-3.0-or-later o Apache-2.0? I la marca: tots els drets reservats, amb redistribució
   sense modificar?
2. Repositori públic, o un mirall públic dels specs i les fonts?
3. On allotjar el repositori de paquets i la ISO, i qui opera els servidors (RGPD)?
4. Clients particulars, o només empreses i universitats?
5. Monetitzar SilikOS en si, o només els serveis i SilikStudio?
6. Hi ha un advocat disponible (via UPC o el col·legi)?
7. SilikStudio contacta algun servidor (llicències, actualitzacions)?
8. Registrar les marques a l'EUIPO?

Sources:
- https://www.gnu.org/licenses/gpl-2.0.html
- https://www.gnu.org/licenses/gpl-3.0.html
- https://www.gnu.org/licenses/gpl-faq.html
- https://www.mozilla.org/en-US/MPL/2.0/
- https://openfontlicense.org/
- https://almalinux.org/p/the-almalinux-os-trademark-usage-policy/
- https://almalinux.org/p/the-almalinux-os-licensing-policy/
- https://almalinux.org/blog/future-of-almalinux/
- https://www.redhat.com/en/about/trademark-guidelines-and-policies
- https://gjs.guide/extensions/review-guidelines/review-guidelines.html
- https://eur-lex.europa.eu/eli/dir/2024/2853
- https://eur-lex.europa.eu/eli/reg/2024/2847/oj
- https://eur-lex.europa.eu/eli/reg/2021/821/oj
- https://eur-lex.europa.eu/eli/dir/2019/770/oj
- https://www.enisa.europa.eu/sites/default/files/2026-07/ENISA_CRA_SRP_Factsheet_v1.0_0.pdf
- https://ubuntu.com/pricing/pro
- https://ciq.com/pricing
- https://tuxcare.com/almalinux-commercial-support/
- https://github.com/iic-jku/IIC-OSIC-TOOLS
- https://tinytapeout.com/news/efabless-shutsdown/
- https://docs.projectbluefin.io/donations
- https://www.linuxpromagazine.com/index.php/Online/News/New-KDE-Slimbook-Plasma-Available-for-Preorder
