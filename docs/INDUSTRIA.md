# SilikOS per a la indústria: eines de fabricant i laboratoris idèntics (13/11/2026)

**Res d'aquesta pàgina s'ha provat amb l'instal·lador real de cap fabricant.** No s'ha baixat, executat ni desat cap
programa de fabricant. El que hi ha és el que diuen les pàgines públiques de requisits, i com s'ha llegit cadascuna:

- **llegit de la pàgina del fabricant**: s'ha obert el text del mateix fabricant (el codi font de la seva documentació
  o el seu repositori). Només 7 de 39.
- **extracte del cercador [A]**: la web del fabricant no era accessible des de la màquina de treball (el seu host no
  hi és permès); el que es diu surt de l'extracte que el cercador dona de la pàgina oficial. S'ha de confirmar a la
  pàgina (l'URL és a `silik vendor list`).
- **no confirmat [A]**: no s'ha trobat.

Les suposicions van marcades [A]. Els noms de paquet sí que estan comprovats (vegeu "Què s'ha executat").

## Què hi ha

```
silik vendor list [--json]              les eines: què diu el fabricant d'EL 9, per a quina versió, com, quan i on s'ha llegit
silik vendor check EINA... [--json]     aquest sistema contra els requisits publicats: ok / warn / bad / unknown / info,
silik vendor check --all --json           i a cada fila que no és ok, l'ordre que l'arregla
silik vendor prepare EINA...            executa aquestes ordres (cada una impresa; --dry-run no executa res) i diu què queda a mà
silik vendor lib libtinfo.so.5          quin paquet d'EL 9 porta la biblioteca que demana un programa
silik manifest export [FITXER]          l'estat de la màquina en un JSON (--with-host hi afegeix nom, usuari i MAC)
silik manifest diff FITXER              què difereix entre aquesta màquina i el fitxer (surt 0 si són iguals)
silik manifest apply FITXER             la transacció de dnf i les ordres `silik` que porten aquesta màquina al fitxer
                                          (--prune per treure paquets, --kernel per tocar el kernel, --dry-run)
```

Al COMMAND bar: `vendor/list`, `vendor/check`, `vendor/EINA`, `sys/manifest` (EN, CA, ES).

**Què comprova `silik vendor check`** (cada comprovació és fixa al codi; el fitxer de dades només tria quines):

| Comprovació | Què mira | Qui ho arregla |
|---|---|---|
| suport del fabricant | la versió menor d'EL 9 d'aquest sistema contra les que anomena el fabricant | ningú: la llista és del fabricant |
| noms que llegeix un instal·lador | `ID`, `VERSION_ID`, `/etc/redhat-release` (els de la base) | `silik identity base` si compara el nom visible |
| paquets, repositoris | els noms d'EL 9 del que demana el fabricant (`rpm -q`), i si EPEL i CRB hi són | `prepare`: `dnf install` |
| versions mínimes, disc, memòria | les xifres que dona el projecte (Zephyr, Yocto, ESP-IDF) | a mà |
| carregador de llicències | `/lib64/ld-lsb-x86-64.so.3`: lmgrd el demana per aquest nom, i EL 9 no té `redhat-lsb-core` | `prepare`: un enllaç |
| host id de la llicència | les adreces MAC, i si NetworkManager en posa una d'aleatòria (perfil o valor per defecte) | a mà: `nmcli` (s'imprimeix) |
| nom de la màquina | que sigui fix i que es resolgui | a mà: `hostnamectl` |
| `/usr/tmp`, locale, X11, SELinux | que hi siguin; la sessió de SilikOS és X11 | `prepare` (enllaç, paquet) o a mà |
| límits i ajustos del kernel | `ulimit` i uns quants `sysctl`: només s'informen | mai des d'aquí: `sudo sysctl -w` el fa la persona |
| regles udev del fabricant | si el fitxer del fabricant hi és (mai es copia) | l'instal·lador del fabricant |
| ports sèrie, instruments USB | les regles de `silik-dev` (uaccess): sense grup `dialout`, USBTMC per a l'usuari | `prepare`: `silik-dev` |
| driver CAN | si està carregat el del kernel (SocketCAN) o el del fabricant (`pcan`, linuxcan), i si aquest ha posat el del kernel a la llista negra | a mà |
| capçaleres del kernel | `kernel-devel` del kernel en marxa, per als mòduls que el fabricant compila (NI, Keysight) | `prepare` |

`prepare` només executa `dnf` (instal·lar paquets, activar un repositori) i dos enllaços. No toca mai un perfil de
xarxa, un ajust del kernel, un mòdul ni un fitxer del fabricant (un test ho sosté per a totes les eines).

## Les eines

Paquets: quants noms porta la recepta; [A] vol dir que no surten de la llista del fabricant (informes d'usuaris, o el
paquet que porta una biblioteca que l'eina demana).

| Recepta | Eina | Versió llegida | Què diu el fabricant d'EL 9 | Paquets | Llegit de la pàgina del fabricant (13/11/2026) | Provat instal·lant-lo |
|---|---|---|---|---|---|---|
| **Llicències** | | | | | | |
| `flexlm` | FlexNet (lmgrd i el dimoni del fabricant) | FlexNet Publisher 11.19 | només RHEL 9; AlmaLinux no hi surt | - | no: extracte del cercador [A] | no |
| **FPGA** | | | | | | |
| `vivado` | AMD Vivado / Vitis | 2026.1 | sí: anomena AlmaLinux 9 (9.4, 9.5, 9.6, 9.7) | 1 [A] | no: extracte del cercador [A] | no |
| `quartus` | Altera Quartus Prime Pro | 25.3 | només RHEL 9; AlmaLinux no hi surt | - | no: extracte del cercador [A] | no |
| `libero` | Microchip Libero SoC | v2026.1 | sí: anomena AlmaLinux 9 (9.6) | - | no: extracte del cercador [A] | no |
| `radiant` | Lattice Radiant | 2026.1 | només RHEL 9; AlmaLinux no hi surt (9.6) | - | no: extracte del cercador [A] | no |
| **Càlcul i simulació** | | | | | | |
| `matlab` | MathWorks MATLAB / Simulink | R2026b | sí: anomena AlmaLinux 9 | 56 | sí | no |
| `matlab-r2026a` | MathWorks MATLAB / Simulink | R2026a | només RHEL 9; AlmaLinux no hi surt | 54 | sí | no |
| `matlab-r2025b` | MathWorks MATLAB / Simulink | R2025b | només RHEL 9; AlmaLinux no hi surt | 55 | sí | no |
| `ansys` | Ansys | 2026 R1 | només RHEL 9; AlmaLinux no hi surt | - | no: extracte del cercador [A] | no |
| `comsol` | COMSOL Multiphysics | 6.4 | només RHEL 9; AlmaLinux no hi surt | 1 | no: extracte del cercador [A] | no |
| **Disseny de xips i RF** | | | | | | |
| `cadence` | Cadence (Virtuoso, Spectre, Xcelium, Innovus) | 2025.x (IC23.1, IC25.1) | sí: anomena AlmaLinux 9 | 21 [A] | no: extracte del cercador [A] | no |
| `synopsys` | Synopsys (Custom Compiler, HSPICE, VCS, Design Compiler) | Y-Foundation (2026.03, 2026.06, 2026.09) | sí: anomena AlmaLinux 9 | 19 [A] | no: extracte del cercador [A] | no |
| `siemens` | Siemens EDA (Calibre, Questa, Xpedition) | - | no confirmat | - | no [A] | no |
| `ads` | Keysight ADS | ADS 2026 Update 2.0 | només RHEL 9; AlmaLinux no hi surt | - | no: extracte del cercador [A] | no |
| **Microcontroladors i sondes** | | | | | | |
| `stm32cubeide` | STM32CubeIDE | v2.1.0 (RN0114 Rev 37, 02/2026) | té versió Linux; cap EL 9 anomenat | - | no: extracte del cercador [A] | no |
| `stm32cubeprog` | STM32CubeProgrammer | v2.22.0 (RN0109 Rev 33) | té versió Linux; cap EL 9 anomenat | 1 | no: extracte del cercador [A] | no |
| `stm32cubemx` | STM32CubeMX | - | no confirmat | - | no [A] | no |
| `jlink` | SEGGER J-Link Software / Ozone | - | no confirmat | - | no: extracte del cercador [A] | no |
| `trace32` | Lauterbach TRACE32 | - | no confirmat | - | no: extracte del cercador [A] | no |
| `mcuxpresso` | NXP MCUXpresso IDE | v25.06 | té versió Linux; cap EL 9 anomenat | - | no: extracte del cercador [A] | no |
| `s32ds` | NXP S32 Design Studio | - | no confirmat | - | no [A] | no |
| `ccs` | TI Code Composer Studio | 20.4 | no confirmat | - | no: extracte del cercador [A] | no |
| `modustoolbox` | Infineon ModusToolbox | - | té versió Linux; cap EL 9 anomenat | - | no: extracte del cercador [A] | no |
| `aurix` | Infineon AURIX Development Studio | - | no confirmat | - | no [A] | no |
| `e2studio` | Renesas e2 studio | 2026-07 | té versió Linux; cap EL 9 anomenat | - | no: extracte del cercador [A] | no |
| `mplabx` | Microchip MPLAB X IDE | v6.30 | no confirmat | - | no: extracte del cercador [A] | no |
| **Projectes oberts amb requisits propis** | | | | | | |
| `esp-idf` | Espressif ESP-IDF | v5.5.6 | té versió Linux; cap EL 9 anomenat | 11 | sí | no |
| `zephyr` | Zephyr RTOS i el Zephyr SDK | main (4.5.99), SDK 1.0.1 | té versió Linux; cap EL 9 anomenat | 18 + 4 [A] | sí | no |
| `yocto` | Yocto Project (màquina de compilació) | 5.2 (walnascar) | sí: anomena AlmaLinux 9 | 36 | sí | no |
| **CAN** | | | | | | |
| `peak` | PEAK PCAN (USB, PCIe) | PCAN driver for Linux 8.x | al kernel d'EL 9 | 1 | no: extracte del cercador [A] | no |
| `kvaser` | Kvaser (USB, PCIe) | linuxcan (Kvaser Linux Drivers and SDK) | al kernel d'EL 9 | 1 | no: extracte del cercador [A] | no |
| `vector` | Vector CANoe / CANalyzer i les interfícies VN | Vector Driver Package 26.30.0 for Linux | no: VM de Windows | - | no: extracte del cercador [A] | no |
| **Banc i instruments** | | | | | | |
| `ni` | NI Linux Device Drivers (NI-DAQmx, NI-488.2), LabVIEW | 2026 Q3 | només RHEL 9; AlmaLinux no hi surt (9.6) | 2 [A] | no: extracte del cercador [A] | no |
| `visa-open` | Instruments, el camí obert (PyVISA + pyvisa-py, USBTMC) | - | al kernel d'EL 9 | 2 | sí | no |
| `visa-ni` | NI-VISA | NI Linux Device Drivers 2026 Q3 | només RHEL 9; AlmaLinux no hi surt (9.6) | - | no: extracte del cercador [A] | no |
| `visa-keysight` | Keysight IO Libraries Suite for Linux | 2025 | només RHEL 9; AlmaLinux no hi surt (9.0 a 9.4) | - | no: extracte del cercador [A] | no |
| `visa-rs` | Rohde & Schwarz VISA | 5.12.x | no confirmat | - | no: extracte del cercador [A] | no |
| `saleae` | Saleae Logic 2 | - | té versió Linux; cap EL 9 anomenat | 2 [A] | no: extracte del cercador [A] | no |
| `digilent` | Digilent WaveForms / Adept Runtime | Adept Runtime 2.27.9 | no confirmat | - | no: extracte del cercador [A] | no |

(MATLAB: el que s'ha llegit del fabricant és la llista de paquets que MathWorks publica per a AlmaLinux 9 i RHEL UBI 9,
al repositori de les seves imatges de contenidor; la seva pàgina de requisits només en extractes [A]. Zephyr, ESP-IDF,
Yocto i pyvisa-py: el codi font de la seva documentació. `silik vendor check EINA` ensenya la frase llegida i l'URL.)

Tres coses que surten de llegir-ho, i que un comprador ha de saber:

- **SilikOS és 9.8 i diversos fabricants anomenen menors concretes**: Vivado 2026.1 arriba a la 9.7, Libero, Radiant i
  NI a la 9.6, Keysight IO Libraries 2025 a la 9.4 [A: extractes]. `silik vendor check` ho diu com a `warn`. La sortida
  real és un canal de laboratori congelat a la menor que el fabricant suporta (idea 2).
- **Cadence dona a Alma 9 "suport limitat"** i Synopsys l'anomena com a sistema binàriament compatible [A: extractes].
- **Les eines de microcontroladors gairebé mai anomenen EL 9** (Ubuntu i Fedora). Funcionar no és el mateix que tenir
  suport: aquí no s'ha provat cap.

## Què s'ha executat (13/11/2026, contenidor `almalinux:9`, AlmaLinux 9.8 x86_64, amb CRB i EPEL 9)

| Què | Com | Resultat |
|---|---|---|
| Tots els noms de paquet existeixen | `bash tools/check_deps.sh --vendor` | 145 noms: 144 es resolen, `dfu-util` el compila SilikOS; `redhat-lsb-core` no existeix a EL 9 |
| Cada llista s'instal·la junta | `dnf install --assumeno` de la llista de cada eina (res baixat) | 16 eines amb paquets, cap problema de dependències |
| `silik vendor prepare flexlm vivado cadence` de veritat | dins el contenidor | paquets instal·lats, l'enllaç fet; després les files són `ok` |
| `silik manifest` d'anada i tornada | export A, prepare, export B, `apply A --prune`, `apply B` | `diff A` i `diff B` diuen "the same"; `dnf downgrade` de glibc a la versió d'A inclòs; export en 0,4 s |
| La comparació de versions | `rpm_vercmp` contra `rpm.vercmp` del mateix rpm 4.16 | 2401 parells vàlids, cap diferència |
| El paquet instal·lat | `tools/build_rpms.sh`, `dnf install` de silik-tools i silik-dev | `silik vendor` troba `/usr/share/silikos/vendors.conf`; la regla USBTMC hi és |
| La regla USBTMC fa servir la forma de les de la base | `50-udev-default.rules` i `70-uaccess.rules` de systemd-udev 252-67.el9_8 | la base llegeix `ID_USB_INTERFACES` igual (impressores, PTP) |

**No executat:** cap instal·lador de fabricant; res en un SilikOS instal·lat amb escriptori (NetworkManager, SELinux i
la sessió surten `unknown` al contenidor, com ha de ser); cap instrument USBTMC, cap adaptador CAN amb el driver del
fabricant; `silik manifest apply` amb ajustos, capses o arguments del kernel de veritat (només amb dobles); ARM.

## El manifest

Un JSON ordenat (dues exportacions de la mateixa màquina són els mateixos bytes), sense secrets i sense nom de màquina,
usuari ni MAC si no es demana `--with-host`:

| Secció | Què porta | `apply` |
|---|---|---|
| `base` | id, versió, arquitectura | una altra arquitectura: s'atura; una altra menor: ho diu |
| `repos` | els ids dels repositoris activats (cap URL) | activa `epel` i `crb`; els altres han de ser definits a la màquina |
| `packages` | cada paquet: `nom-època:versió-release.arq @repositori` | `dnf install` / `dnf downgrade` de les versions exactes; treure, només amb `--prune` |
| `kernel` | els paquets del kernel (i `kmod-*`), el kernel en marxa, la línia d'ordres sense el que anomena discos | paquets i arguments (`grubby`), només amb `--kernel`; mai se'n treu cap paquet |
| `settings` | look, accent, glass, energia, actualitzacions automàtiques | les ordres `silik` corresponents |
| `boxes` | les capses (nom, imatge, EL) | `silik eda create`; el contingut d'una capsa no hi és; mai se n'esborra cap |
| `tools` | versions de les eines de banc i EDA obertes; on són els IDE de fabricant | només informa (un IDE és del fabricant) |

Per afegir-hi una secció: una entrada a `MANIFEST_SECTIONS` de `silik` (nom, exportar, comparar, planificar).

Límit: les versions exactes han de ser encara als repositoris. Els d'AlmaLinux només guarden les últimes; per això
"20 màquines idèntiques d'aquí a sis mesos" demana un canal congelat (idea 2). Avui: idèntiques si s'aplica aviat, o
contra un mirall propi.

## Què pagaria un comprador industrial (PROPOSTA: idees, cap és feta ni promesa)

Per ordre de valor per esforç [A: és un judici, no una dada]:

1. **Llista d'eines de fabricant provades de veritat.** Cada fila d'aquesta pàgina amb "provat instal·lant-lo: sí,
   versió, data, màquina". És el que cap altra distribució publica. Demana llicències d'avaluació i hores.
2. **Repositori signat amb un "canal de laboratori" congelat.** Una instantània d'EL 9.x + EPEL + SilikOS per menor
   (9.6, 9.8), que no es mou. `silik manifest apply` deixa de dependre del que els miralls conserven, i el client es
   queda a la menor que el seu fabricant suporta.
3. **Manifest de flota.** `silik manifest diff` contra un fitxer de referència a cada arrencada, i un informe de
   quines màquines del laboratori s'han desviat. La peça d'una sola màquina ja hi és.
4. **ISO sense xarxa i mirall per a sales aïllades (`silik mirror`).** Les empreses de xips treballen sense Internet:
   el canal congelat en un disc, amb les claus, i `silik update` que hi apunta.
5. **Mode servidor de llicències.** Una instal·lació mínima amb nom i MAC fixos, `lmgrd` com a servei, el tallafocs
   obert només als ports de la llicència, i `silik vendor check flexlm` com a diagnosi.
6. **Llista de maquinari certificat.** Estacions i portàtils on s'ha executat tot (gràfics, suspensió, sondes).
7. **Suport alineat amb EL 9 fins al 31/05/2032**, amb un sol responsable.
8. **Carpetes d'evidència per a la qualificació d'eines (ISO 26262, IEC 61508).** El manifest signat de la màquina
   que ha compilat, les versions del compilador, i el registre de cada ordre: matèria primera per a l'expedient del
   client. No és una certificació i no s'ha de vendre com a tal.

## Decisions que són del propietari

- Aconseguir llicències d'avaluació (o instal·ladors amb el seu compte) per convertir files en "provat".
- Si SilikOS segueix l'última menor (9.8) o ofereix també la que la majoria de fabricants anomenen (9.6).
- El canal congelat depèn del repositori signat (clau, host), que ja era la primera decisió pendent.

Sources:
- https://community.revenera.com/s/article/workaround-for-lsb-component-in-rhel
- https://community.flexera.com/t5/FlexNet-Publisher-Forum/FNP-on-RHEL-9/m-p/248927
- https://www.keil.com/support/docs/4044.htm
- https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Supported-Operating-Systems
- https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Checking-Required-Libraries
- https://access.redhat.com/discussions/6995923
- https://www.intel.com/content/www/us/en/docs/programmable/683706/25-3/operating-system-support.html
- https://onlinedocs.microchip.com/oxy/GUID-D6BA99C6-E1C8-44EB-9669-702FBBAA3897-en-US-28/GUID-B0DCEFFF-6CEC-4D57-B4B0-90540F2BBC8A.html
- https://onlinedocs.microchip.com/oxy/GUID-D6BA99C6-E1C8-44EB-9669-702FBBAA3897-en-US-28/GUID-6EC547F0-2A3C-43E9-AB1C-F822E7AB53CF.html
- https://coredocs.s3.amazonaws.com/Libero/2025_2/Tool/libero_soc_v2025_2_release_notes.pdf
- https://www.latticesemi.com/Radiant
- https://github.com/mathworks-ref-arch/container-images/blob/main/matlab-deps/r2026b/almalinux9/base-dependencies-amd64.txt
- https://github.com/mathworks-ref-arch/container-images/blob/main/matlab-deps/README.md
- https://www.mathworks.com/support/requirements/matlab-linux.html
- https://github.com/mathworks-ref-arch/container-images/blob/main/matlab-deps/r2026a/ubi9/base-dependencies.txt
- https://github.com/mathworks-ref-arch/container-images/blob/main/matlab-deps/r2025b/ubi9/base-dependencies.txt
- https://www.cadence.com/en_US/home/support/computing-platform-support/support-road-map-2024x-2027x.html
- https://www.cadence.com/en_US/home/support/computing-platform-support/support-road-map-2022x-2025x.html
- https://community.cadence.com/cadence_technology_forums/pcb-design/f/licensing-and-installation/65488/cadence-tool-compatibility-and-installation-support-on-almalinux
- https://community.cadence.com/cadence_technology_forums/f/custom-ic-skill/62692/ic-23-1-installation-configuration-failure-on-rhel-9
- https://www.synopsys.com/support/licensing-installation-computeplatforms/compute-platforms/release-specific-support/supported-y-foundation.html
- https://www.synopsys.com/support/licensing-installation-computeplatforms/compute-platforms/platform-notice/2025-y-foundation-centos-support-changes.html
- https://synopsys.com/support/licensing-installation-computeplatforms/licensing/scl-supported-os.html
- https://www.europractice.stfc.ac.uk/tools/siemens.html
- https://community.altera.com/discussions/quartus-prime/license-setup-for-questa-on-red-hat/295884
- https://www.keysight.com/jp/ja/lib/software-detail/computer-software/pathwave-advanced-design-system-ads-software-2212036/ads-2026-update-2-0-linux.html
- https://ansyshelp.ansys.com/public/views/secured/corp/v261/en/installation/unix_sysprereqs.html
- https://www.drd.com/wp-content/uploads/2026/03/ansys-platform-support-strategy-plans-march-2026.pdf
- https://www.comsol.com/system-requirements/64/general
- https://www.st.com/resource/en/release_note/rn0114-stm32cubeide-release-v210-stmicroelectronics.pdf
- https://community.st.com/t5/stm32cubeide-mcus/stm-cube-ide-installation-problem-in-rhel/td-p/783224
- https://www.st.com/resource/en/release_note/rn0109-stm32cubeprogrammer-release-v2220-stmicroelectronics.pdf
- https://dev.st.com/stm32cube-docs/prog/2.23.0/en/docs/markup/CubeProg_How_To_Start/CubeProg_Installation.html
- https://kb.segger.com/Linux_specifics
- https://segger.com/products/development-tools/ozone-j-link-debugger/technology/system-requirements
- https://forum.segger.com/index.php/Thread/5002-JLink-broken-Linux-RPM-install-packages
- https://forum.segger.com/index.php/Thread/6318-SOLVED-Unable-to-install-Segger-JLink-on-Linux-udev-rules-error-possible-conflic
- https://support.lauterbach.com/kb/articles/linux-why-isn-t-linux-booting-after-installing-usb-driver-file-10-lauterbach-rules
- https://www2.lauterbach.com/pdf/installation.pdf
- https://www.nxp.com/mcuxpresso/ide
- https://software-dl.ti.com/ccs/esd/documents/ccs_linux_host_support.html
- https://software-dl.ti.com/ccs/esd/CCSv20/CCS_20_4_1/exports/CCS_20.4.1_ReleaseNote.htm
- https://software-dl.ti.com/ccs/esd/CCSv20/CCS_20_0_1/exports/CCS_20.0.1_ReleaseNote.htm
- https://documentation.infineon.com/modustoolbox/docs/general-information
- https://www.renesas.com/en/document/rln/e-studio-2026-07-release-note
- https://www.renesas.com/en/document/mat/quick-start-guide-linux-hosted-version-e-studio
- https://developerhelp.microchip.com/xwiki/bin/view/software-tools/x/requirements
- https://developerhelp.microchip.com/xwiki/bin/view/software-tools/x/archive/linux/
- https://github.com/espressif/esp-idf/blob/release/v5.5/docs/en/get-started/linux-macos-setup.rst
- https://github.com/espressif/esp-idf/blob/release/v5.5/docs/en/get-started/establish-serial-connection.rst
- https://github.com/zephyrproject-rtos/zephyr/blob/main/doc/develop/getting_started/installation_linux.rst
- https://github.com/zephyrproject-rtos/zephyr/blob/main/doc/develop/getting_started/index.rst
- https://github.com/zephyrproject-rtos/zephyr/blob/main/doc/develop/toolchains/zephyr_sdk.rst
- https://github.com/yoctoproject/poky/blob/walnascar/documentation/ref-manual/system-requirements.rst
- https://github.com/yoctoproject/poky/blob/walnascar/documentation/tools/host_packages_scripts/almalinux_essential.sh
- https://github.com/yoctoproject/poky/blob/walnascar/documentation/poky.yaml.in
- https://docs.yoctoproject.org/5.2/ref-manual/system-requirements.html
- https://www.peak-system.com/fileadmin/media/linux/index.php
- https://www.peak-system.com/PCAN-Linux.358.0.html
- https://github.com/torvalds/linux/blob/v6.12/drivers/net/can/usb/peak_usb/pcan_usb_core.c
- https://kvaser.com/?p=30789
- https://old.can-cia.org/fileadmin/resources/documents/publications/cnlm_issues/march_2024/cnlm_24-1_p30_socketcan_versus_linuxcan-make_the_right_choice_adam_raymer_kvaser.pdf
- https://github.com/torvalds/linux/blob/v6.12/drivers/net/can/usb/kvaser_usb/kvaser_usb_core.c
- https://www.vector.com/us/en/download/
- https://www.vector.com/en/product/canoe-server-editions/
- https://www.ni.com/en/support/documentation/compatibility/26/ni-linux-device-drivers-2026-q3-compatibility.html
- https://www.ni.com/docs/en-US/bundle/ni-platform-on-linux-desktop/page/supported-drivers-for-linux-distributions.html
- https://github.com/pyvisa/pyvisa-py/blob/main/docs/source/installation.rst
- https://github.com/torvalds/linux/blob/v6.12/drivers/usb/class/usbtmc.c
- https://helpfiles.keysight.com/IO_Libraries_Suite/English/IOLS_Linux/IOLS/Content/Introductory_Topics/Whats_New_For_Linux_Users.htm
- https://helpfiles.keysight.com/IO_Libraries_Suite/English/IOLS_Linux/IOLS/Content/Introductory_Topics/Reference_Topics/Revision_Matrix.htm
- https://www.rohde-schwarz.com/us/applications/r-s-visa-application-note_56280-148812.html
- https://support.saleae.com/logic-software/sw-installation
- https://support.saleae.com/troubleshooting/linux-permission-requirements-for-logic-software
- https://forum.digilent.com/topic/28753-repository-w-signed-packages-for-digilent-waveforms-rpm/
- https://forum.digilent.com/topic/28525-digilent-adept-runtime-package-header-is-not-signed/
- https://forum.digilent.com/topic/20462-waveform-install-on-linux-mint20/
- https://endoflife.date/almalinux
