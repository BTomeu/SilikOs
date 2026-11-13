# SilikOS: els números (13/11/2026)

Full de números del sistema. Cada un diu data, màquina i mètode; cap és estimat. El que no s'ha mesurat és a la
secció 9. Suposicions: [A]. Propostes: PROPOSTA (no s'ha tocat res del kickstart).

**Mètode (pes).** No s'instal·la res. El gestor de paquets de cada sistema resol el conjunt **des d'un disc buit**
(dnf: `--installroot` buit; apt: fitxer d'estat de dpkg buit) amb `install --assumeno` / `-s`, i se sumen els bytes
que les metadades dels repositoris donen per a cada paquet. MB = 1024 × 1024 bytes. "Instal·lat" és la mida que
declara el paquet, **no l'espai ocupat al disc** (secció 7).
**Màquina.** Contenidor de núvol (Ubuntu 24.04, 4 nuclis, Docker), x86_64, 13/11/2026. Cada sistema dins la seva
imatge oficial: `almalinux:9` (AlmaLinux 9.8, dnf 4.14.0), `fedora:latest` (Fedora 45, dnf 5.4.6), `ubuntu:24.04`
(24.04.5, apt); les dues últimes baixades per `mirror.gcr.io` (Docker Hub havia arribat al límit de baixades).
**Per refer-los.** `bash tools/weigh.sh` (SilikOS; uns 3 minuts; `--json`, `--plan`, `--leave-out A,B`) i
`bash tools/weigh_others.sh` (els altres). En un sistema instal·lat: `silik doctor system`, fila `weight`.

## 1. Quant pesa SilikOS

El conjunt de `kickstart/silikos.ks` (`%packages`), amb les seves fonts (BaseOS, AppStream, CRB, extras, EPEL 9) i
els nostres paquets.

| Conjunt | Paquets | Es baixa | Instal·lat |
|---|---|---|---|
| Minimal Install de la base | 325 | 918 MB | 1,2 GB |
| Workstation de la base (GNOME: l'entorn del kickstart) | 1223 | 1,9 GB | 4,5 GB |
| **SilikOS: el kickstart amb els 10 paquets de `packages/`** | **1524** | **2,5 GB** | **7,1 GB** |
| ídem, amb el nucli i el carregador que hi posa l'instal·lador [A: aquests 8 noms] | 1532 | 2,5 GB | 7,1 GB |
| **SilikOS amb els 19 paquets de les releases** (Wine, eines EDA, OpenOCD: la ISO de la CI) | **1623** | **2,9 GB** (2,6 de xarxa, 354 MB a la ISO) | **9,2 GB** |
| SilikOS sense dependències febles (no és com s'instal·la) | 1201 | 1,9 GB | 4,4 GB |

- Sobre el Workstation de la base, SilikOS hi posa 302 paquets, 565 MB de baixada i 2,6 GB instal·lats (només
  repositoris); amb les releases, 390 paquets, 976 MB i 4,7 GB (diferència de dues files mesurades).
- Sense dependències febles gairebé no afegeix res: els nostres paquets ho demanen tot amb `Recommends`, perquè un
  nom que falti no aturi la instal·lació.
- Les releases s'han pesat amb les capçaleres dels RPM publicats (nom, dependències, mides), sense baixar-ne el
  contingut. No hi són encara: KiCad, sigrok, SavvyCAN, SDCC, stm32flash, silik-pylab (construïts, no publicats).

## 2. D'on ve el pes

Amb les releases. **Sol**: el que porta aquell paquet sobre el Workstation (dos paquets poden portar el mateix).
**Només ell**: el que marxa del conjunt si es treu només aquell (0 si un altre el requereix).

| Paquet | Sol: paquets | Sol: baixada | Sol: instal·lat | Només ell: paquets | Només ell: instal·lat |
|---|---|---|---|---|---|
| silik-dev | 65 | 313 MB | 1,7 GB | 41 | 1,6 GB |
| silik-win | 145 | 351 MB | 1,5 GB | 79 | 1,2 GB |
| silik-eda-open | 139 | 305 MB | 1,4 GB | 105 | 1,2 GB |
| silik-eda-compat | 109 | 107 MB | 381 MB | 43 | 149 MB |
| silikos-desktop | 23 | 23 MB | 75 MB | 3 | 1,8 MB |
| silikos-security | 21 | 22 MB | 74 MB | 3 | 91 kB |
| silik-command | 19 | 22 MB | 74 MB | 0 | 0 |
| silikos-power | 19 | 22 MB | 74 MB | 1 | 1 kB |
| silik-tools | 18 | 22 MB | 74 MB | 0 | 0 |
| silikos-branding | 1 | 17 kB | 46 kB | 0 | 0 |

Sense les releases: silik-dev 57 paquets / 1,7 GB, silik-win 140 / 512 MB, silik-eda-open 89 / 504 MB; la resta igual.
Els 74 MB que comparteixen els petits són podman i els seus (el porta silik-tools). L'escriptori, la seguretat, la
marca i l'energia junts pesen menys de 2 MB propis.

## 3. Els 20 paquets més grossos (amb les releases)

| Paquet | Instal·lat | El porta | Si es treu (`dnf -x`) |
|---|---|---|---|
| arm-none-eabi-gcc-cs | 1,0 GB | silik-dev (feble) | −2 paquets, −1,0 GB |
| linux-firmware | 705 MB | la base (Minimal) | −1, −705 MB (els controladors: no es toca) |
| silik-wine | 620 MB | silik-win (feble) | −5, −1,0 GB (amb Mono i Gecko) |
| firefox | 369 MB | la base (Workstation) | −2, −369 MB |
| arm-none-eabi-newlib | 354 MB | silik-dev (feble) | −1, −354 MB |
| silik-wine-mono | 225 MB | silik-win (feble) | −1, −225 MB |
| kicad-symbols | 221 MB | silik-eda-open (feble) | −1, −221 MB |
| glibc-all-langpacks | 217 MB | la base (Workstation) | 0, −217 MB (entra glibc-minimal-langpack) |
| klayout | 207 MB | silik-eda-open (feble) | −13, −228 MB |
| silik-wine-gecko | 207 MB | silik-win (feble) | −1, −207 MB |
| google-noto-serif-cjk-ttc-fonts | 173 MB | la base (Workstation) | −1, −173 MB |
| kicad-footprints | 149 MB | silik-eda-open (feble) | −1, −149 MB |
| google-noto-sans-cjk-ttc-fonts | 125 MB | la base (Workstation) | −1, −125 MB |
| llvm-libs | 123 MB | la base (Mesa) | res: entra llvm21-libs |
| wireshark-cli | 106 MB | silik-dev (feble) | −3, −130 MB |
| webkit2gtk3 | 103 MB | la base (yelp, evolution) | no es pot treure |
| ibus | 89 MB | la base (gnome-shell) | no es pot treure |
| iwl7260-firmware | 88 MB | la base (Minimal) | −1, −88 MB |
| yosys | 87 MB | silik-eda-open (feble) | −1, −87 MB |
| gcc | 86 MB | silik-eda-open, silik-win | −18, −230 MB (amb gcc-c++, kernel-devel…) |

## 4. Els nostres paquets

| Què | RPM | Instal·lat |
|---|---|---|
| Els 10 de `packages/` (noarch) | 414 kB | 1,1 MB |
| el més gros: silikos-desktop 0.15.0 | 238 kB | 708 kB |
| silik-tools 0.6.14 | 77 kB | 280 kB |
| Els 19 de les releases (x86_64) | 354 MB | 1,9 GB |
| els més grossos: silik-wine-gecko / silik-wine / silik-wine-mono | 83 / 70 / 61 MB | 207 / 620 / 225 MB |
| klayout, opencascade, yosys | 43 / 25 / 24 MB | 207 / 100 / 87 MB |

## 5. La ISO

No s'ha baixat ni construït avui. Les mides de la base són els bytes escrits al fitxer `CHECKSUM` d'AlmaLinux,
signat per la clau `BF18AC2876178908D6E71267D36CB86CB86B3716` (comprovat amb gpgv, 13/11/2026).

| Què | Bytes | |
|---|---|---|
| ISO d'arrencada de la base, x86_64 (la que refà `tools/build_iso.sh`) | 1 519 271 936 | 1,4 GB |
| ídem, aarch64 | 1 458 331 648 | 1,4 GB |
| El que hi afegeix SilikOS sense releases (kickstart 3 399, `product.img` 160 168 sense `.buildstamp`, repositori 459 510) | 623 077 | 608 kB |
| **ISO de SilikOS sense releases** (calculat) | 1 519 895 013 | 1,4 GB |
| El que hi afegeix amb les 19 releases | 371 977 326 | 355 MB |
| **ISO de SilikOS amb releases** (calculat) | 1 891 249 262 | 1,8 GB |
| Per comparar: ISO minimal i DVD de la base | 2 838 495 232 / 15 151 923 200 | 2,6 / 14,1 GB |

És una ISO d'instal·lació per xarxa: després baixa 2,5 GB (2,6 GB amb releases a la ISO). La del 09/11 construïda
de debò feia 1,5 GB (`docs/STATUS.md`).

## 6. Comparació amb altres sistemes

Mateix mètode i mateix punt de partida (disc buit, dependències febles activades, nucli i carregador inclosos).
**Escriptori**: l'entorn d'escriptori de sèrie. **Banc**: el que cal afegir-hi per tenir el compilador ARM amb
newlib, OpenOCD, can-utils, sigrok (sigrok-cli + PulseView), KiCad, ngspice, Wine, podman i QEMU/libvirt.

| Sistema | Escriptori: paquets | baixada | instal·lat | Banc: paquets | baixada | instal·lat | Del banc, no hi és |
|---|---|---|---|---|---|---|---|
| AlmaLinux 9.8 Workstation + EPEL | 1233 | 1,9 GB | 4,5 GB | +137 | 369 MB | 1,9 GB | OpenOCD, sigrok, KiCad, ngspice; Wine hi és però no s'instal·la |
| **SilikOS 9.8** (mateix escriptori + EPEL + paquets propis) | 1233 | 1,9 GB | 4,5 GB | +151 | 448 MB | 2,5 GB | sigrok i KiCad (construïts, encara no publicats) |
| Fedora 45 Workstation | 1859 | 2,1 GB | 6,1 GB | +273 | 2,0 GB | 6,8 GB | res |
| Ubuntu 24.04 `ubuntu-desktop` | 1627 | 1,7 GB | 4,1 GB | +212 | 890 MB | 4,7 GB | res |
| Ubuntu 24.04 `ubuntu-desktop-minimal` | 1486 | 1,5 GB | 3,6 GB | | | | |
| Debian 13 `task-gnome-desktop` | no mesurat | | | | | | deb.debian.org no és accessible des d'aquesta màquina |
| openSUSE | no mesurat | | | | | | no s'ha fet |

Peça a peça (paquets nous / instal·lat):

| Eina | AlmaLinux + EPEL | SilikOS | Fedora 45 | Ubuntu 24.04 |
|---|---|---|---|---|
| Compilador ARM + newlib | 4 / 1,4 GB | 4 / 1,4 GB | 4 / 1,9 GB | 6 / 2,9 GB |
| OpenOCD | no hi és | 9 / 19 MB | 7 / 8 MB | 6 / 15 MB |
| can-utils | 1 / 1 MB | 1 / 1 MB | 1 / 1 MB | 1 / 1 MB |
| sigrok | no hi és | no publicat | 23 / 74 MB | 31 / 75 MB |
| KiCad | no hi és | no publicat | 114 / 2,4 GB | 34 / 686 MB |
| ngspice | no hi és | 3 / 21 MB | 3 / 37 MB | 1 / 28 MB |
| Wine | no s'instal·la | 3 / 621 MB | 114 / 2,3 GB | 42 / 756 MB |
| podman | 17 / 73 MB | 17 / 73 MB | ja hi és | 16 / 125 MB |
| QEMU / libvirt | 119 / 434 MB | 119 / 434 MB | 11 / 20 MB | 88 / 211 MB |

**Què diu aquesta comparació.**
- L'escriptori de SilikOS és el de la base: 4,5 GB. És més petit que el de Fedora 45 (6,1 GB) i semblant al
  d'Ubuntu (4,1 GB sense comptar els snaps).
- El SilikOS sencer (9,2 GB amb releases) porta molt més que "escriptori + banc": 11 eines EDA, les biblioteques per
  a Cadence/Synopsys, Wine amb Mono i Gecko. Escriptori + banc: SilikOS 7,0 GB (sense sigrok ni KiCad, encara no
  publicats), Ubuntu 8,8 GB, Fedora 12,9 GB.
- El compilador ARM d'EPEL ocupa la meitat que el d'Ubuntu (1,4 contra 2,9 GB).

**Què no diu.**
- No és espai al disc, ni memòria, ni velocitat.
- Ubuntu Desktop porta a més 13 snaps (Firefox, Thunderbird, l'App Center, el runtime de GNOME…: manifest oficial
  de la ISO 24.04.5.1). No són paquets d'apt i **no estan comptats**; la botiga de snaps no respon des d'aquesta
  màquina.
- El conjunt resolt no és exactament el que posa cada instal·lador: el manifest d'Ubuntu llista 1823 paquets deb i
  aquí en surten 1627 (la ISO porta també paquets d'idioma i l'instal·lador; no desglossat).
- Fedora i Ubuntu instal·len KiCad amb les seves biblioteques recomanades (a Fedora, també els models 3D); a SilikOS
  els models 3D són a part.

## 7. Contrast amb sistemes instal·lats de debò

| Mesurat instal·lant (CI) | Resolt amb aquest mètode | Diferència |
|---|---|---|
| 10/11, run 42836687192: 1427 paquets instal·lats amb 7 paquets nostres (en una prova anterior amb 8, l'instal·lador anunciava 1420 RPM i 2,13 GiB) | 13/11, els mateixos 7 paquets (`dnf` a mà, mateix muntatge): 1420, i 1428 amb nucli i carregador; 2,1 GB | 1 paquet (0,1 %), amb 3 dies de canvis als repositoris |
| el mateix sistema: 6,3 G ocupats al disc (`df`) | 5,1 GB de mida de paquets | el disc ocupa 1,24 vegades la mida dels paquets |
| 11/11, run 43062105280: 1603 paquets, 11 GB ocupats (ISO amb releases) | 13/11: 1623 paquets, 9,2 GB | el conjunt ha canviat (silikos-power, silik-dev 0.5.0): no és el mateix sistema |

El conjunt d'avui no s'ha instal·lat: el seu espai real al disc no està mesurat.
Les sumes exactes quadren amb els totals que imprimeix dnf (2552 MB contra "2.5 G"; 7232 MB contra "7.1 G").

## 8. Candidats a aprimar (PROPOSTA)

Mesurat traient-los del conjunt sense releases (`tools/weigh.sh --leave-out A,B`). Res d'això s'ha aplicat.

| Què | Paquets | Baixada | Instal·lat | Qui ho porta | Risc |
|---|---|---|---|---|---|
| SystemTap (`systemtap-devel`, `systemtap-client`) | −18 | −33 MB | −119 MB | recomanats per `qemu-kvm-tools`; res nostre els fa servir | arrossega `kernel-devel` (−81 MB dels 119), que `silik hw nvidia install` torna a instal·lar: en una màquina NVIDIA l'estalvi real és de 38 MB |
| Bases GeoIP (`geolite2-city`, `geolite2-country`) | −2 | −24 MB | −64 MB | recomanades per `ipcalc` (via `dhcp-client`, de libguestfs) | cap de conegut: només `ipcalc --geoinfo` |
| Els dos junts | −20 | −58 MB | −182 MB | | |
| Lletres CJK (`google-noto-*-cjk-ttc-fonts`) | −3 | −197 MB | −298 MB | el grup de lletres del Workstation de la base | text xinès, japonès i coreà sense lletra; canvia el conjunt de la base |
| `glibc-all-langpacks` | 0 | −18 MB | −217 MB | el Workstation de la base | caldria afegir `glibc-langpack-en/ca/es`; un programa que demani un altre idioma no el trobaria; canvia el conjunt de la base |
| Wireshark amb finestra (`wireshark`; queda `tshark`) | −3 | −5 MB | −12 MB | silik-dev | poc guany |

No es poden treure sense perdre una altra cosa: `qemu-kvm-docs` i Ceph (`librbd1`, `librados2`: els requereix
`qemu-kvm`), TeX Live (el requereixen `python3-matplotlib` i l'Evince de la base), `webkit2gtk3`, `ibus`.
El pes gros és volgut: compilador ARM (1,4 GB), Wine (1,0 GB), eines EDA, firmware (18 paquets, 812 MB: "tots els
controladors").

**Decisió de l'amo:** les dues primeres files (182 MB) no toquen la base; les lletres CJK i els langpacks (515 MB)
sí que en canvien el conjunt de paquets.

## 9. Arrencada i memòria del sistema instal·lat (primera mesura)

Workflow CI, run 43393494218 (commit b596ffc, 13/11/2026): SilikOS instal·lat en una màquina virtual KVM d'un runner de
GitHub (4096 MB de memòria, sense targeta gràfica), mesurat per `silik bench system` dins la màquina, dues arrencades amb
el perfil de `silik speed` posat i dues després de `silik speed undo`. Són quatre captures d'una sola execució en una
màquina virtual compartida: una primera mesura, no una mitjana.

| Captura | Arrencada (nucli + initrd + espai d'usuari) | `gdm.service` engegat | Escriptori | Memòria usada | Processos | Unitats en marxa |
|---|---|---|---|---|---|---|
| perfil posat, 1 | 1,1 + 2,1 + 6,1 = 9,3 s | 5,7 s | 8,9 s | 990 MB | 99 | 44 |
| perfil posat, 2 | 1,2 + 2,3 + 6,1 = 9,7 s | 6,0 s | 9,2 s | 982 MB | 99 | 44 |
| perfil tret, 1 | 1,3 + 2,1 + 6,8 = 10,2 s | 6,0 s | 9,6 s | 1625 MB | 122 | 50 |
| perfil tret, 2 | 1,1 + 2,1 + 6,8 = 10,1 s | 5,9 s | 9,4 s | 1355 MB | 109 | 49 |

- El perfil estalvia entre 0,4 i 0,9 s d'arrencada (0,7 s d'espai d'usuari a les quatre captures) i entre 365 i 643 MB
  de memòria usada; les dues captures sense perfil difereixen entre elles 270 MB, o sigui que la xifra de memòria té
  aquest soroll.
- La mateixa execució: 113 comprovacions bé, 1 fallada (la de la prova mateixa, `look.default`, ja arreglada), 14G de
  disc després d'instal·lar.
- Segona execució (run 43436222754, commit 4c4163f, el mateix dia; 120 comprovacions bé, cap de fallada, 15G de disc):
  amb el perfil 9,3 i 9,3 s, escriptori a 8,8 s, 986 i 981 MB; sense, 9,7 i 9,9 s, escriptori a 9,1 i 9,3 s, 1607 i
  1350 MB. Coincideix amb la primera.
- En maquinari real: encara no.

### Al costat de l'AlmaLinux Workstation de sèrie

Workflow Compare, run 43446488850 (commit fd6e090, 13/11/2026): SilikOS (la seva ISO, sessió X11, perfil de `silik
speed` posat) i l'AlmaLinux 9 Workstation tal com l'instal·la la base (la seva sessió per defecte, Wayland), instal·lats
a la mateixa màquina virtual (4 CPU, 4096 MB, KVM) del mateix runner, dues arrencades de cadascun, mesurats pel mateix
`silik bench system` dos minuts després de tenir l'escriptori. Una sola execució: una primera mesura.

| | SilikOS 1 | SilikOS 2 | AlmaLinux 1 | AlmaLinux 2 |
|---|---|---|---|---|
| Arrencada: nucli + initrd + espai d'usuari | 1,34 + 3,11 + 7,62 = 12,07 s | 1,41 + 3,02 + 7,43 = 11,86 s | 1,37 + 3,06 + 6,93 = 11,37 s | 1,32 + 3,06 + 7,13 = 11,51 s |
| `gdm.service` engegat | 7,34 s | 7,29 s | 7,23 s | 7,14 s |
| Escriptori | 11,41 s | 11,26 s | 10,61 s | 10,56 s |
| Memòria usada | 984 MB | 979 MB | 1135 MB | 1145 MB |
| Memòria disponible (de 3655 MB) | 2671 MB | 2675 MB | 2520 MB | 2510 MB |
| Processos | 99 | 99 | 106 | 106 |
| Memòria dels processos (proporcional) | 778 MB | 777 MB | 909 MB | 900 MB |
| Unitats en marxa (serveis) | 44 (32) | 44 (32) | 48 (36) | 48 (36) |
| Disc usat a / | 8101 MB | 8101 MB | 5329 MB | 5329 MB |
| Paquets (mida instal·lada) | 1551 (7363 MB) | 1551 (7363 MB) | 1231 (4582 MB) | 1231 (4582 MB) |

- **Memòria: SilikOS en fa servir 151 a 166 MB menys** (979-984 contra 1135-1145 MB), amb 7 processos i 4 unitats
  menys. És el perfil de `silik speed`.
- **Arrencada: SilikOS arriba a l'escriptori 0,65 a 0,85 s més tard** (11,26-11,41 contra 10,56-10,61 s), i l'espai
  d'usuari li costa 0,3 a 0,7 s més. No és més ràpid que la base en arrencar: és més lent.
- On és la diferència (segona execució, 43461175134, commit acc8cd1, que ja apunta com arrenca la sessió; dona el
  mateix quadre: memòria 991 / 976 contra 1145 / 1153 MB, escriptori a 11,45 / 11,35 contra 10,03 / 10,6 s). Les
  dues màquines entren a la sessió soles (`AutomaticLogin`): **no hi ha pantalla d'inici**. La sessió de SilikOS és
  X11 (`WaylandEnable=false`, per les eines EDA, que són programes X11); la de l'AlmaLinux és Wayland.

  | Des que arrenca el gestor de l'usuari | SilikOS 1 | SilikOS 2 | AlmaLinux 1 | AlmaLinux 2 |
  |---|---|---|---|---|
  | `graphical-session.target` (l'escriptori) | 3,65 s | 3,72 s | 3,15 s | 3,13 s |
  | la unitat de GNOME Shell (`org.gnome.Shell@x11` / `@wayland`) | 1,74 s | 1,74 s | 1,81 s | 1,78 s |
  | `org.gnome.SettingsDaemon.XSettings` (només a X11) | 0,67 s | 0,66 s | no hi és | no hi és |

  **La shell de SilikOS, amb la nostra extensió i el nostre tema, no triga més que la de sèrie** (1,74 contra
  1,78-1,81 s). El mig segon de més és de la sessió X11 fora de la shell: el servidor Xorg, que s'ha d'engegar abans,
  i el que X11 demana a més. És el preu d'una decisió presa (X11 per a l'EDA), no una cosa nostra a arreglar. A la
  segona parella de captures la sessió s'obre al mateix moment als dos sistemes (7,55 i 7,52 s): la part del sistema
  abans de la sessió és igual.
- `systemd-binfmt.service` (0,59 s) és a la cadena crítica de SilikOS i no a la de la base: el `ksh` de la base (el
  demana silik-eda-compat, pels scripts dels fabricants) porta `/etc/binfmt.d/kshcomp.conf`, i amb un sol fitxer la
  unitat ja s'engega. `sysinit.target` hi arriba 0,13 s més tard. Es deixa com està.
- Aquesta execució arrenca més lenta que les del CI del mateix dia (12 s contra 9,3 s, l'initrd 3,1 contra 2,1 s): és
  un altre runner. Per això la comparació només val dins d'una mateixa execució.
- No mesurat: una màquina amb pantalla d'inici (les de prova no en tenen), on la pantalla d'inici podria anar sobre
  Wayland i la sessió sobre Xorg; ni cap maquinari real.

## 10. Encara no mesurat

| Què | Qui ho omplirà |
|---|---|
| Arrencada i memòria en maquinari real | el Ryzen |
| Temps d'instal·lació i temps d'actualització | CI |
| Espai real al disc del conjunt d'avui; mida de la ISO construïda | CI (`tools/build_iso.sh`, test d'instal·lació) |
| aarch64 amb aquest mètode (del 12/11 només hi ha els nou RPM resolts sobre un contenidor: 895 paquets, 1,6 GB, 4,8 GB; no és comparable amb la taula 1) | `tools/weigh.sh` en una màquina ARM (segueix l'arquitectura) |
| Debian, openSUSE; els snaps d'Ubuntu | `tools/weigh_others.sh debian` on deb.debian.org respongui |
| El pes amb KiCad, sigrok i la resta del banc publicats | `tools/weigh.sh` amb `build/extra/` ple |
| Qualsevol comparació de velocitat amb altres sistemes | ningú encara: cal la mateixa màquina amb cada sistema instal·lat |
