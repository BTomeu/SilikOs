# SilikOS a ARM (aarch64)

L'únic lloc per a ARM. Els controladors del nucli aarch64 i quines màquines ARM arrenca: `docs/DRIVERS.md`. El detall
de cada prova: `docs/STATUS.md`.

**En una frase:** la base (AlmaLinux 9 aarch64, sense tocar) i tot el que és nostre funcionen a aarch64; el que no
existeix a ARM és el programari x86 d'altres (Wine, les eines EDA dels fabricants, Altium), i `silik` ho diu en lloc
de fallar.

**Com s'ha vist tot el que hi ha aquí:** en un contenidor `almalinux:9` aarch64 emulat (qemu-user 8.2.2, binfmt_misc)
sobre la màquina de compilació x86_64, i el menú d'arrencada amb qemu-system (TCG). **Cap prova en maquinari ARM.**
Els temps de compilació emulats no són el rendiment d'un ARM real: no hi ha cap xifra de velocitat d'ARM en aquest
document perquè no se n'ha mesurat cap.

## 1. Què funciona

| Part | A aarch64 | Com s'ha vist |
|---|---|---|
| Els nostres 9 paquets (`noarch`), `silik`, la barra COMMAND | es construeixen i s'instal·len amb les dependències reals (CRB, EPEL) | `tools/build_rpms.sh`, `dnf install`, `silik status / look / dev tools / eda tools / win apps --json`; proves unitàries amb Python 3.9.25 (12/11) |
| El conjunt sencer de SilikOS | resol: 895 paquets, 1,6 GB de descàrrega, 4,8 GB instal·lats (x86_64 el mateix dia: 915 / 1,6 GB / 4,7 GB); sense dependències febles 353 / 226 MB / 924 MB | `dnf install --assumeno` (12/11); no instal·lat (sense pantalla) |
| Escriptori (GNOME Shell 40.10, GDM, GTK 3, python3-gobject, qt5ct) | als repositoris aarch64 d'AlmaLinux 9 i EPEL 9 | `dnf list`; no engegat |
| Encastat de la base / EPEL: `arm-none-eabi-gcc` 12.4.0, newlib, stlink 1.7.0, gdb 16.3, can-utils, picocom, avrdude, wireshark... | hi són | `dnf list` |
| Encastat nostre: dfu-util 0.11, stm32flash 0.7, OpenOCD 0.12.0 (12/11); **silik-pylab 1.0** (python-can, cantools, esptool, pymodbus; 13/11) | construïts i provats; tots junts amb el compilador d'EPEL, `silik dev try`: **7 ok, 0 fallats** (12/11, i 13/11 amb silik-pylab) | `tools/build_dev.sh`, `dev/trial.sh` |
| EDA oberta nostra: ngspice 47 (12/11); **Netgen 1.5.328, Xschem 3.4.7, Magic 8.3.696, nng 1.12.5** (13/11) | construïts i provats: taula 2 | `tools/build_eda.sh`, `eda/trial.sh` |
| EDA oberta d'EPEL 9: Icarus Verilog 12.0, Verilator 5.022, GTKWave 3.3.118 | hi són | `dnf list` |
| Màquina virtual Windows 11 per a ARM (`silik win vm create`) | les peces hi són (qemu-kvm 10.1, libvirt 11.10, virt-install 5.1, edk2-aarch64, swtpm, passt, virtio-win); la línia d'ordres és la d'ARM (`virt`, AAVMF, TPM 2.0, virtio) | només `--dry-run`: aquí no hi ha KVM [A: les opcions són les de virt-install 5.1] |
| El que `silik` diu a ARM | `status`: línia `arch`, `vsyscall n/a`; `eda create` refusa una caixa x86_64 amb el motiu (`--arch amd64`: emulada); `hw nvidia install` es refusa; `win open FITXER.exe` diu quina via hi ha | executat allà (12/11); `tests/test_arm.py` |
| `silik win routes` (nou, 13/11) | diu quina via té un programa de Windows en aquesta màquina, pel que hi veu (KVM, mida de pàgina, emulador, Hyper-V) | executat al contenidor aarch64 (sense KVM: `vm no`, `wine no`, `emulator missing`); `tests/test_arm.py` |
| ISO | `SILIK_ARCH=aarch64 bash tools/build_iso.sh` → `build/SilikOS-9.8-aarch64-netinstall.iso` (només UEFI) | sobre un substitut de l'ISO d'arrencada d'1,5 GB: el menú UEFI "Install SilikOS 9.8" i el nucli arrenquen; l'instal·lador i una instal·lació, no |

## 2. Les receptes a aarch64

Decidit primer llegint (el projecte original suporta aarch64? tots els `BuildRequires` existeixen a EL 9 + CRB + EPEL 9
per a aarch64?: `dnf --forcearch aarch64 repoquery`, 13/11/2026: **110 de 111 noms hi són**; l'únic que falta és
`libquadmath-devel`) [S5][S6][S7], i després construint només les petites sota emulació. Una recepta només diu
`aarch64` al seu `ExclusiveArch` quan s'ha construït **i** ha fet la seva prova allà.

| Recepta | ARM a l'origen (evidència) | `BuildRequires` aarch64 | Estat |
|---|---|---|---|
| ngspice | Fedora 45 el construeix per a aarch64 | tots | **fet** (12/11): 96 min emulat, prova ok |
| dfu-util, stm32flash, openocd | Fedora 45 (dfu-util, openocd) | tots | **fet** (12/11): 5 min, 36 s, 24,5 min; proves ok |
| netgen | Fedora 45 (`netgen` 1.3.7 [A: el mateix programa, versió antiga]) | tots | **fet** (13/11): 529 s emulat, RPM de 232 KB; la prova (LVS d'un inversor: coincideix, i amb una porta equivocada no) ok |
| xschem | Fedora 45 (3.4.7) | tots | **fet** (13/11): 822 s emulat, RPM d'11,6 MB; la prova (arrenca i diu la versió) ok |
| magic | Fedora 45 (8.3.684) | tots | **fet** (13/11): 1284 s emulat, RPM d'1,7 MB; la prova (una caixa de metal1 pintada i desada) ok |
| silik-pylab | fonts de PyPI: Python pur i dues extensions en C (wrapt, bitstruct), compilades allà | tots (python3.12) | **fet** (13/11): 637 s emulat, RPM de 2,5 MB; la prova (una trama DBC descodificada, el bus virtual de python-can, esptool, una petició Modbus) ok |
| nng | Fedora 45 (1.12.2) | tots | **fet** (13/11), amb `tools/arm_candidate.sh nng` (el que executa el flux): 919 s emulat entre construir i provar, RPM de 232 KB; la prova (un missatge per un parell de sòcols, des d'un programa compilat contra la biblioteca) ok |
| klayout | rodes `manylinux aarch64` a PyPI (0.30.13) | tots (Qt 5, Ruby) | candidata al CI |
| yosys | Fedora 45 (0.67) | tots (gcc-toolset-14, cmake 3.31) | candidata al CI |
| nvc | el README no anomena arquitectures (Linux, macOS, Windows) [A] | tots (LLVM 21) | candidata al CI |
| qucs-s | Fedora 45 (26.1.1) | tots (Qt 6.10 d'EPEL) | candidata al CI |
| opencascade | Fedora 45 (7.9.3) | tots | candidata al CI |
| kicad | Fedora 45 (10.0.6) | tots, més opencascade, nng i ngspice nostres | candidata al CI (construeix primer les tres) |
| devsim | l'origen suporta AlmaLinux 8 `aarch64` (README) i publica rodes aarch64 | **falta `libquadmath-devel`** (els floats de 128 bits són d'x86_64) | candidata al CI; la recepta ja té la branca d'ARM com la fa l'script de l'origen (`nofloat128`). Començada aquí (13/11, límit de 40 min): les dependències resolen, symdiff i UMFPACK construïts, cmake accepta la configuració, i la compilació era al 42 % quan el límit la va aturar: **no acabada, no provada** |
| savvycan | Qt 5 sense codi d'arquitectura [A] | tots (qt5-qtserialbus) | candidata al CI |
| sigrok (libsigrok, sigrok-cli, PulseView) | Fedora 45 | tots | candidata al CI |
| sdcc | Fedora 45 (4.6.0) | tots | candidata al CI; una línia de la recepta deia `x86_64-pc-linux-gnu`: generalitzada [A: no construïda] |
| kicad-symbols, -footprints, -templates, -packages3d, sigrok-firmware-fx2lafw | — | — | `noarch`: el mateix paquet serveix a ARM |

Els `noarch` es guarden als llançaments `eda-tools` / `dev-tools` (fets a x86_64).

## 3. Què no existeix a ARM, i l'alternativa

### Programes de Windows (x86) i programes Linux x86_64

SilikOS fa servir el nucli per defecte de la base: `kernel-core 5.14.0-687.66.2.el9_8.aarch64` té
`CONFIG_ARM64_4K_PAGES=y` (llegit del seu `config`, 13/11) [S5]. `kernel-64k` (pàgines de 64K) existeix a BaseOS i el
kickstart no l'instal·la. Importa: Wine a ARM exigeix pàgines de 4K (notes de Wine 10.0) [S1]. La columna dels
paquets: `dnf --forcearch aarch64 repoquery` [S5] i el llistat de Fedora 45 [S6].

| Via | Què és | Llicència | Paquet a EL 9 / EPEL 9 aarch64 | Notes |
|---|---|---|---|---|
| **Windows 11 per a ARM en una VM (KVM)** [S14] | Windows executa x86 i x64 amb la seva pròpia emulació (Prism) | Windows: llicència de Microsoft | les peces de la VM hi són totes; l'ISO d'ARM64 la dóna Microsoft | només programes d'usuari: **un controlador de nucli ha de ser ARM64** (sondes, dongles). Cal KVM |
| Wine ARM64 + FEX-Emu (interfície d'emulació de Wine 10) [S1][S2] | Wine natiu; només el codi x86-64 del programa s'emula | LGPL-2.1+ / MIT | **cap** (ni wine, ni fex-emu) | pàgines de 4K (les tenim); Fedora 45 aarch64 té fex-emu 2604 i no té wine |
| Hangover (Wine + FEX / Box64 com a DLL) [S4] | x86_32 i x86_64 de Windows sobre Wine aarch64 | LGPL-2.1 | **cap**; només `.deb` (Debian 11-13, Ubuntu 20.04-25.10) | — |
| box64 + Wine x86_64 [S3] | emulador d'usuari de Linux x86_64 | MIT | **cap** (Fedora 45 té box64 0.3.6) | no executa binaris de 32 bits (Box86 / Box32, experimental, o el Wine WOW64) |
| qemu-user + binfmt_misc | emulació d'usuari; és el que fan servir les caixes EDA (`silik eda create NOM --arch amd64`) | GPL-2.0 | **cap** (`qemu-user-static` no és a EL 9; Fedora 45 sí que té `qemu-user-static-x86`) | lent; cap fabricant ho suporta; no és una via per a Windows |
| Windows mateix | SilikOS com a VM d'un portàtil Windows on ARM | — | — | el Windows de fora executa el programa; dins la VM no hi ha KVM |

**PROPOSTA (per decidir):** a ARM, els programes de Windows van a **Windows 11 per a ARM dins d'una màquina virtual**
(`silik win vm create`), i quan SilikOS és ell mateix una VM d'un portàtil Windows on ARM, al Windows de fora. No
empaquetar Wine + FEX per a EL 9 ara: no hi ha paquets d'EL, ningú no ho suporta i caldria mantenir dos emuladors; es
torna a mirar si hi ha demanda. `silik win routes` ja diu quina de les dues vies té la màquina; `silik win open
FITXER.exe` l'anomena en lloc de dir només que no hi ha Wine. No provat: la VM (cal KVM en maquinari ARM).

Què diuen els fabricants sobre Windows on ARM (les marcades † s'han llegit pel resum del cercador: la pàgina no
s'obre des d'aquesta sessió):

| Programa | Què diu | Font |
|---|---|---|
| Emulació de Windows (Prism) † | tradueix x86 / x64 d'usuari; els components de nucli han de ser ARM64 | [S14] |
| LTspice † | LTspice 26.0 té descàrrega per a Windows ARM64, al costat de la d'x64 | [S15] |
| SEGGER J-Link † | natiu a Windows ARM64 des de la V7.60 (sondes velles: canviar a WinUSB) | [S16] |
| PEAK (PCAN) † | controladors per a Windows on ARM des del paquet 4.4 | [S17] |
| MATLAB † | R2026a suportat a Windows on ARM a través de Prism; no natiu | [S18] |
| ST (CubeIDE, CubeProgrammer, CubeMX, ST-LINK) † | "no suportem Windows ARM de moment"; sense controladors ST-LINK natius; CubeProgrammer funciona emulat segons usuaris | [S19] |
| Altium Designer † | requisits: Windows 11 / 10 de 64 bits, processador Intel Core i5 o equivalent; cap menció d'ARM; fora de Windows remet a virtualització | [S20] |
| Vector (CANoe, CANalyzer, controladors) † | Windows 11 de 64 bits; cap menció d'ARM64 trobada; els controladors, "Windows 10 i 11 (64 bits)" | [S21] |
| Keil MDK (µVision) † | la guia d'Arm demana una màquina Windows x86 de 64 bits | [S22] |

Conclusió per al banc: a Windows on ARM el programa sol arrencar emulat, i el que falla és **el controlador de la
sonda o de la interfície CAN** quan el fabricant no en té d'ARM64 (ST-LINK, Vector [A]); amb J-Link i PCAN sí.

### La resta

| No hi és | Per què | Alternativa |
|---|---|---|
| Virtuoso, Sentaurus i les caixes EL6 / EL7 | programes x86_64 | una màquina x86_64 (local o remota); la caixa emulada (`--arch amd64`) existeix a `silik` i no s'ha engegat mai |
| Altium | Windows x86 | la VM de Windows per a ARM (emulat per Windows; no ho suporta Altium) o una màquina x86_64 |
| NVIDIA (`silik hw nvidia install`) | el repositori que es configura és el d'x86_64 | es refusa amb el motiu |
| Les receptes "candidata al CI" de la taula 2 | no construïdes encara a ARM | el flux "ARM candidates" |

## 4. Què demostrarà el CI

Tot escrit i **no executat**: GitHub no engega feines en aquest compte fins que el repositori sigui públic. Els
executors són els ARM de GitHub (`ubuntu-24.04-arm`; gratuïts per a repositoris públics [A]): natius, sense hores
d'emulació.

| Flux | Feines | Què demostra |
|---|---|---|
| CI | `arm` | les proves a aarch64, els paquets instal·lats a EL 9 aarch64 i l'ISO aarch64 feta sobre l'ISO d'arrencada real d'AlmaLinux |
| Dev tools | `build-arm`, `trial-arm` | dfu-util, stm32flash, OpenOCD, silik-pylab: construïts, provats, la pila sencera (`silik dev try`), i guardats a `dev-tools` |
| EDA tools | `build-arm`, `keep-arm` | ngspice, Netgen, Xschem, Magic, nng: construïts, provats i guardats a `eda-tools-aarch64` |
| **ARM candidates** (nou; només a mà) | `try` (una per recepta), `summary` | cada recepta que encara no diu `aarch64`: construïda amb `SILIK_TRY_ARCH=1` (una còpia de la recepta eixamplada; la recepta no es toca), provada en un contenidor net; no publica res; **una taula** al resum: construïda / prova ok / fallada amb les últimes línies d'error |

El mateix a mà en qualsevol ARM amb docker: `bash tools/arm_candidate.sh klayout`.

## 5. On es pot fer servir avui

Ordenat de més segur a menys, segons el que publica cada fabricant. Res d'això s'ha executat.

| On | Què en sabem | Certesa |
|---|---|---|
| Núvol: AWS Graviton, Azure (i Oracle) | AlmaLinux publica imatges oficials d'AlmaLinux 9 `arm64` (AWS Marketplace; Azure `almalinux:almalinux-arm:9-arm-gen2`) i una imatge genèrica `AlmaLinux-9-GenericCloud-latest.aarch64.qcow2` [S9][S10][S11]; Oracle Cloud, x86_64 i aarch64 des de la 9.0 † [S30] | alta: la mateixa base, imatge del fabricant; a sobre, `tools/install_on_alma.sh`. Sense pantalla: `silik`, l'encastat i l'EDA oberta per línia d'ordres |
| Servidors Ampere Altra (i Hetzner CAX, que en fa servir) | el catàleg de Red Hat té els processadors Ampere Altra Max per a RHEL 9.0-9.x aarch64 i un sistema certificat (GIGABYTE MP72-HB0) † [S12]; Hetzner diu que les seves imatges suporten Arm † [S13] (AlmaLinux 9 a CAX: no confirmat [A]) | alta en servidor; com a estació de treball depèn de la gràfica (`docs/DRIVERS.md`) |
| VM en un Mac amb Apple silicon | RHEL 9 fa servir pàgines de 4K (Apple silicon només en suporta de 4K i 16K: RHEL 8, amb 64K, no hi arrencava) † [S23]; Red Hat va instal·lar RHEL 9 ARM a UTM 4.0 † [S24]; Parallels llista RHEL 10 i 9 per a Mac amb xips M † [S25]; VMware Fusion, "RHEL 9 o posterior" (amb una nota sobre `vmwgfx` a la instal·lació) † [S26] | mitjana-alta: RHEL 9 hi és anomenat; AlmaLinux no (mateixos binaris [A]) |
| Hyper-V en un Windows on ARM (Snapdragon X) | la guia d'Arm: Windows 11 22H2 o posterior pot executar VM de Linux a Windows on Arm (exemple: Ubuntu) † [S27]; el nucli aarch64 d'EL 9 porta `CONFIG_HYPERV=m` (llegit) i `hyperv-daemons` és a AppStream; la llista de convidats de Microsoft no anomena distribucions ARM64 † [S28] | mitjana: ningú no anomena EL 9 |
| Raspberry Pi 5 | les imatges d'AlmaLinux per a Pi porten **un altre nucli** (`raspberrypi2-kernel4`, de les fonts de Raspberry Pi; repositori `raspberrypi`), no el 5.14 d'EL 9 [S8] | **no és la mateixa base**: els nostres paquets `noarch` s'hi haurien d'instal·lar [A], però deixa de ser "idèntic a RHEL 9". Com a experiment |
| Snapdragon X directament (sense Windows) | — | no: `docs/DRIVERS.md` |

Dins d'una VM (Mac, Hyper-V) no hi ha KVM si l'hoste no dóna virtualització niada (Apple: M3 o posterior amb macOS 15
per a convidats Linux, segons informes d'usuaris † [S29]): `silik win routes` ho diu.

**Com fer-ho en una VM (no executat):**

1. `SILIK_ARCH=aarch64 bash tools/build_iso.sh` (`docs/BUILD.md`) → `build/SilikOS-9.8-aarch64-netinstall.iso`
   (el flux CI, feina `arm`, la construeix a cada execució i la deixa com a artefacte en una etiqueta `v*`).
2. VM nova d'arquitectura ARM64, **UEFI**, amb xarxa (és una ISO de xarxa) i disc per als 4,8 GB del conjunt i la
   feina. UTM: "Virtualize" → Linux → la ISO [A]. Hyper-V: generació 2, Secure Boot amb la plantilla "Microsoft UEFI
   Certificate Authority" [A].
3. Al menú, "Install SilikOS 9.8"; la pantalla del disc és interactiva (el kickstart no en tria cap).
4. Camí alternatiu, més segur: la imatge o l'ISO d'AlmaLinux 9 aarch64 del fabricant, i a sobre
   `bash tools/install_on_alma.sh`.

## 6. Pes i rendiment

- Pes: l'únic mesurat és el conjunt de paquets (taula 1, 12/11): pràcticament igual que a x86_64.
- Rendiment: **no mesurat**. Tot el que hi ha són temps de compilació sota emulació (molt més lents que la màquina
  que emula, amb 2 dels 4 processadors compartits amb altres feines); no diuen res d'un ARM real. La primera xifra
  real sortirà del CI (la durada de les feines a `ubuntu-24.04-arm`).

## Fonts

Llegides directament (13/11/2026):

- [S1] Notes de Wine 10.0 (ARM64, interfície d'emulació, pàgines de 4K) i la seva llicència (LGPL-2.1 o posterior): https://raw.githubusercontent.com/wine-mirror/wine/wine-10.0/ANNOUNCE.md , https://raw.githubusercontent.com/wine-mirror/wine/wine-10.0/LICENSE ; la de QEMU (GPL-2.0): https://raw.githubusercontent.com/qemu/qemu/master/LICENSE
- [S2] FEX-Emu, README i llicència (MIT): https://github.com/FEX-Emu/FEX/blob/main/Readme.md , https://raw.githubusercontent.com/FEX-Emu/FEX/main/LICENSE
- [S3] box64, README i llicència (MIT): https://github.com/ptitSeb/box64/blob/main/README.md , https://raw.githubusercontent.com/ptitSeb/box64/main/LICENSE
- [S4] Hangover, README i llicència (LGPL-2.1): https://github.com/AndreRH/hangover/blob/master/README.md , https://raw.githubusercontent.com/AndreRH/hangover/master/LICENSE
- [S5] Repositoris d'AlmaLinux 9 i EPEL 9 per a aarch64 (`dnf --forcearch aarch64 repoquery`; `config` de `kernel-core` i `kernel-64k-core`): https://repo.almalinux.org/almalinux/9/ , https://dl.fedoraproject.org/pub/epel/9/Everything/aarch64/
- [S6] Paquets de Fedora 45 per a aarch64 (llistat): https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Everything/aarch64/os/Packages/
- [S7] DEVSIM (plataformes; `scripts/build_manylinux_2_28.sh`), KLayout i DEVSIM a PyPI, NVC: https://github.com/devsim/devsim , https://pypi.org/project/devsim/ , https://pypi.org/project/klayout/ , https://github.com/nickg/nvc
- [S8] AlmaLinux per a Raspberry Pi (wiki i repositori): https://wiki.almalinux.org/documentation/raspberry-pi.html , https://repo.almalinux.org/almalinux/9/raspberrypi/aarch64/os/Packages/
- [S9] AlmaLinux a AWS: https://wiki.almalinux.org/cloud/AWS.html
- [S10] AlmaLinux a Azure: https://wiki.almalinux.org/cloud/Azure.html
- [S11] Imatges de núvol aarch64: https://repo.almalinux.org/almalinux/9/cloud/aarch64/images/

Llegides pel resum del cercador (†: la pàgina no s'obre des d'aquesta sessió; cal confirmar-les abans de citar-les):

- [S12] Catàleg de Red Hat, Ampere Altra Max i GIGABYTE MP72-HB0: https://catalog.redhat.com/en/hardware/system/detail/220797
- [S13] Hetzner, servidors Arm64 (CAX): https://www.hetzner.com/press-release/arm64-cloud
- [S14] Microsoft, com funciona l'emulació a Arm: https://learn.microsoft.com/windows/arm/apps-on-arm-x86-emulation
- [S15] Analog Devices, LTspice, última descàrrega: https://ez.analog.com/design-tools-and-calculators/ltspice/a/faqs-docs/FD560/latest-download-release-notes
- [S16] SEGGER, J-Link a Windows ARM: https://kb.segger.com/J-Link_on_Windows_ARM
- [S17] PEAK-System, controladors per a Windows on ARM: https://www.peak-system.com/Details.114+M5c09b1388bc.0.html?&L=1 , https://electronicspecifier.com/products/windows-on-arm-support-for-can-and-lin-interfaces
- [S18] MathWorks, MATLAB a Windows on ARM: https://www.mathworks.com/matlabcentral/answers/2182415
- [S19] ST Community (CubeIDE i ST-LINK a Windows on ARM): https://community.st.com/t5/stm32cubeide-mcus/stm32cubeide-compatibility-with-snapdragon-x-windows-on-arm/td-p/689028 , https://community.st.com/t5/stm32-mcus-boards-and-hardware/stlink-stcubeprogrammer-support-on-windows-arm64/td-p/224127
- [S20] Altium, requisits del sistema i plataformes que no són Windows: https://www.altium.com/documentation/altium-designer/installation-management/system-requirements , https://www.altium.com/documentation/knowledge-base/altium-designer/run-altium-on-non-windows-platform
- [S21] Vector, CANoe i centre de descàrregues: https://www.vector.com/en/product/canoe/ , https://www.vector.com/us/en/download/
- [S22] Arm, guia d'instal·lació de Keil µVision: https://learn.arm.com/install-guides/mdk/
- [S23] Red Hat, el nucli de 64K i el de 4K per defecte; els errors de RHEL 8 a Apple M1: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/managing_monitoring_and_updating_the_kernel/what-is-kernel-64k_managing-monitoring-and-updating-the-kernel , https://bugzilla.redhat.com/show_bug.cgi?id=2001569 , https://bugzilla.redhat.com/show_bug.cgi?id=1978730
- [S24] Red Hat Developer, RHEL 9 a UTM en un Mac M1: https://developers.redhat.com/articles/2022/10/21/rhel-9-and-single-node-openshift-vms-macos-ventura
- [S25] Parallels Desktop, requisits (convidats Arm): https://kb.parallels.com/122662
- [S26] Broadcom, convidats Arm a Fusion: https://knowledge.broadcom.com/external/article/315602
- [S27] Arm, VM de Linux amb Hyper-V a Windows on Arm: https://learn.arm.com/learning-paths/laptops-and-desktops/hyper-v/
- [S28] Microsoft, convidats suportats a Hyper-V: https://learn.microsoft.com/virtualization/hyper-v-on-windows/about/supported-guest-os
- [S29] Fòrum de Parallels, virtualització niada a M3 i macOS 15: https://forum.parallels.com/threads/macos-15-sequoia-nested-virtualization-for-m3-macs.364397/
- [S30] AlmaLinux 9.0, anunci (Oracle Cloud per a x86_64 i aarch64): https://almalinux.org/blog/almalinux-9-now-available/
- Microsoft, ISO de Windows 11 per a ARM64: https://www.microsoft.com/software-download/windows11arm64
