# SilikOS: memo d'estratègia (12/11/2026)

Recerca d'un agent (web + lectura del repositori), revisada. No hi ha cap número inventat; les suposicions van
marcades [A]. Les webs de Cadence i Synopsys no eren accessibles des de la sessió: el que en diem surt dels extractes
del cercador sobre les seves pàgines oficials i s'ha de confirmar a la pàgina de cada release.

## 1. On és únic avui

**El que ningú més ajunta.** No s'ha trobat cap distribució d'escriptori que faci totes aquestes coses alhora:
- és binàriament RHEL 9;
- té capses EL6/7/8 per a les releases antigues de Cadence i Synopsys, amb la xarxa i el hostname de l'amfitrió pensats
  per a FlexLM;
- porta 11 eines EDA obertes compilades per a EL 9, i cadascuna fa una feina real (`silik eda try`);
- té un Wine propi dins una capsa;
- porta l'eina de banc: SocketCAN, SavvyCAN, sigrok i OpenOCD;
- ensenya cada ordre que executa.

**Els altres en fan només una part:**
- **IIC-OSIC-TOOLS:** és un contenidor Ubuntu amb PDKs. No és un sistema i no serveix per a les eines comercials.
- **nix-eda / LibreLane:** reproduïbles, però només per al flux digital obert.
- **Bluefin LTS** (EL10 + bootc): té actualitzacions atòmiques, però no admet layering local. Això trenca els
  instal·ladors de les eines EDA comercials, que demanen RPMs.
- **Fedora Electronic Lab:** va quedar sense mantenidor.
- **Pop!_OS COSMIC:** té polit i NVIDIA, però va sobre Ubuntu.

**La base s'ha reforçat:**
- Synopsys Y-2026 llista AlmaLinux 9.x com a sistema binàriament compatible amb suport.
- Cadence 2025.x hi afegeix Alma 9 i Rocky 9, amb "limited support".
- MATLAB R2026a llista RHEL 9 (a partir de la 9.2).

**El que és real:** la ISO s'instal·la desatesa al CI (86 comprovacions), hi ha els tests unitaris, i l'Inici i `silik`
són més ràpids (mesurat).

**El que encara no ho és:**
- Res s'ha executat en maquinari real: NVIDIA, Wi-Fi, suspensió, adaptadors CAN, flashejar una placa.
- No s'ha provat cap eina de fabricant ni la VM de Windows.
- No hi ha repositori de paquets públic ni signat.
- El CI està aturat per la facturació de GitHub.

Avui és un **prototip excel·lent verificat en VM**, no encara un producte.

## 2. Forats que importen, per impacte i esforç

1. **Repositori de paquets signat i públic, i el CI en marxa.**
   - Impacte màxim i esforç baix, però depèn del propietari: la clau, el host i la facturació.
   - Sense això, els paquets de SilikOS no s'actualitzen mai a les màquines instal·lades.
2. **Maquinari real i una llista de maquinari certificat.**
   - NVIDIA amb els mòduls oberts precompilats d'AlmaLinux (`nvidia-open-kmod`): van signats amb la clau del kernel i
     funcionen amb Secure Boot sense MOK.
   - `silik update` hauria de retenir un kernel nou fins que n'hi hagi el mòdul.
   - `silik hw report`, executat al Ryzen, fa una fila de la llista. A la llista només hi entra el que s'ha executat.
3. **Tornar enrere amb una ordre.**
   - EL 9.6+ porta snapm i boom-boot: snapshots LVM thin amb una entrada al menú d'arrencada.
   - Pas: `silik snap` / `silik rollback`, amb un snapshot abans de cada actualització de risc.
   - Necessita un disc amb LVM thin [A: com oferir-lo sense que el kickstart triï el disc].
4. **Preparació per a les eines de fabricant, sense distribuir-les.**
   - Receptes verificables per a Virtuoso/Spectre, MATLAB, CubeIDE, J-Link, Vivado, Zephyr i Yocto.
   - Cada recepta comprova els prerequisits, les regles udev, el hostid/lmgrd i la versió de la base.
   - Problemes coneguts:
     - CubeIDE només llista Ubuntu i Fedora.
     - Els RPMs de J-Link han tingut dependències trencades.
     - El driver chardev de PEAK i SocketCAN no poden conviure: `silik dev can` ho ha de detectar.
5. **PDKs i el flux digital.** Sense PDK, les eines de xips obertes són una demo. Pas: `silik eda pdk add
   ihp-sg13g2|sky130|gf180`, amb el permís explícit de l'usuari, i un RTL→GDS de prova dins de podman.
6. **La VM de Windows amb un VN1630 de veritat.** El driver de Linux de Vector és només per a Ubuntu, i CANoe d'escriptori
   és només Windows. Pas: provar-ho al Ryzen.
7. **Una ISO sense xarxa i un primer arrencada mínim.** Que pregunti el perfil (xips / embedded / banc), NVIDIA sí o no,
   i el disc preparat per tornar enrere.

## 3. Què no fer

- **Més looks i accents.** Tres looks i sis accents n'hi ha prou; a partir d'ara, polir i no afegir-ne.
- **Seguir invertint en una shell pròpia sobre GNOME 40.** EL10 porta GNOME 47 i Wayland.
- **Altium dins Wine.** L'historial diu que la VM és el camí.
- **Compilar el que ja és a EPEL**, ni GHDL (a EL 9 no hi ha cap compilador d'Ada viable).
- **Snapdragon X1 en metall**, ni convertir SilikOS a bootc sobre EL 9.
- **Mesurar el progrés amb les comprovacions del CI.** La mètrica són les files de maquinari i d'eines reals.

## 4. "Premium minimalista" que no sigui cosmètic

- **Una fulla de números per release** (`silik bench system`), mesurada a la màquina de referència: arrencada fins a
  l'escriptori, latència de l'Inici i del COMMAND bar, temps d'actualització, temps de tornar enrere.
- **Recuperació amb una ordre:** `silik rollback`, amb un snapshot automàtic abans dels canvis de risc.
- **Reproduïbilitat:** `silik manifest export/apply`, la llista exacta de paquets per tenir la màquina del laboratori
  igual que la teva.
- **Dues llistes públiques:** el maquinari certificat i les eines de fabricant, cada fila amb data i estat (provat / no
  provat).
- **Silenci:** cap telemetria, i el sistema no reinicia mai pel seu compte.
- **Transparència com a missatge central:** cada acció ensenya l'ordre que executa, i mai es diu "ok" del que no es veu.
- **Un sol horitzó de suport:** fins al 31/05/2032, alineat amb EL 9.

## 5. Riscos

- **Cicle d'EL 9.** El suport complet s'acaba el 31/05/2027 i el manteniment el 31/05/2032. Els portàtils nous poden no
  funcionar amb el kernel 5.14 [A].
- **Migració a EL 10.**
  - Treu Xorg i porta GNOME 47.
  - Les extensions de GNOME 45 i posteriors són mòduls ES: `silik-shell` s'ha de portar, no només recompilar.
  - Els paquets de tercers per a EL 10 seran x86-64-v3 [A].
  - SilikOS 10 quan els dos grans fabricants d'EDA suportin EL 10 [A: ~2027–28].
- **GNOME 40 envelleix:** les aplicacions GTK4 no agafen el tema GTK3.
- **ARM:** l'X1 té poc suport; ARM queda com a VM o com a experiment d'EL 10.
- **NVIDIA:** el mòdul pot arribar més tard que el kernel. Per això cal la retenció del kernel i poder tornar enrere.
- **Un sol mantenidor i dependència de GitHub:** el repositori s'ha de poder moure a un altre host.
- **Suport "limitat" de Cadence sobre Alma:** `silik identity base` ajuda, però el risc comercial hi és.

Sources:
- https://www.cadence.com/en_US/home/support/computing-platform-support/support-road-map-2024x-2027x.html
- https://www.cadence.com/en_US/home/support/computing-platform-support/support-road-map-2022x-2025x.html
- https://community.cadence.com/cadence_technology_forums/pcb-design/f/licensing-and-installation/65488/cadence-tool-compatibility-and-installation-support-on-almalinux
- https://www.synopsys.com/support/licensing-installation-computeplatforms/compute-platforms/release-specific-support/supported-y-foundation.html
- https://github.com/iic-jku/IIC-OSIC-TOOLS
- https://github.com/fossi-foundation/nix-eda
- https://fossi-foundation.org/librelane
- https://openroad-flow-scripts.readthedocs.io/en/latest/index2.html
- https://docs.projectbluefin.io/blog/bluefin-lts-ga/
- https://wiki.almalinux.org/sigs/Atomic
- https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/configuring_and_managing_logical_volumes/managing-system-upgrades-with-snapshots_configuring-and-managing-logical-volumes
- https://www.redhat.com/en/blog/rhel-10-plans-wayland-and-xorg-server
- https://endoflife.date/almalinux
- https://almalinux.org/blog/2025-08-06-announcing-native-nvidia-suport/
- https://wiki.almalinux.org/documentation/nvidia.html
- https://forums.almalinux.org/t/technical-incident-report-nvidia-driver-almalinux-9-7-kernel-incompatibility/7216
- https://www.mathworks.com/support/requirements/matlab-linux.html
- https://www.vector.com/en/product/canoe-server-editions/
- https://docs.yoctoproject.org/5.2/ref-manual/system-requirements.html
- https://docs.zephyrproject.org/latest/develop/getting_started/installation_linux.html
- https://community.st.com/t5/stm32cubeide-mcus/stm-cube-ide-installation-problem-in-rhel/td-p/783224
- https://forum.segger.com/index.php/Thread/5002-JLink-broken-Linux-RPM-install-packages
- https://www.peak-system.com/PCAN-Linux.358.0.html
- https://codeweavers.com/compatibility/crossover/altium-designer
- https://fedoraproject.org/wiki/Electronic_Lab
- https://www.cnx-software.com/2026/09/25/qualcomm-releases-linux-developer-preview-snapdragon-x2/
