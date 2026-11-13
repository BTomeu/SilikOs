# SilikOS, explicat des de zero

Aquest document explica què és SilikOS, per què existeix, com està fet i en quin punt és, per a qui no en sap res.
El detall tècnic és als altres documents de `docs/`; aquí hi ha la idea.

---

## 1. El problema

Un enginyer d'electrònica fa servir, en un dia normal:

- **Eines de disseny de xips i de plaques** (EDA): Cadence Virtuoso, Synopsys, KiCad, simuladors de circuits
  (SPICE), eines de layout.
- **Eines de microcontroladors**: compiladors per a ARM, depuradors, programadors (ST-LINK, J-Link), IDEs dels
  fabricants (STM32CubeIDE, Code Composer Studio).
- **Eines de banc**: lectors de bus CAN, ports sèrie i RS485, analitzadors lògics, oscil·loscopis.
- **Programes de Windows** que no tenen alternativa (Altium, LTspice, CANoe, les eines d'alguns fabricants).

Avui això vol dir tenir-ho escampat: una màquina virtual amb un Red Hat antic per a les eines de xips, un Windows
per als programes de Windows, i un portàtil on cada cosa s'instal·la a mà i es trenca a la primera actualització.

Les eines grans d'EDA (Cadence, Synopsys) només funcionen oficialment sobre **Red Hat Enterprise Linux (RHEL)**.
No sobre Ubuntu ni sobre Windows.

## 2. La idea

**SilikOS és un sistema operatiu per a enginyers d'electrònica que ho porta tot en un sol lloc:**
el disseny de xips i de plaques, els microcontroladors, el banc de proves i els programes de Windows, amb un
escriptori propi i amb SilikStudio (el programari de SilikVolt) com a peça central.

La decisió que ho fa possible: **no fer un sistema operatiu nou, sinó posar-ne un de compatible a sobre d'un que ja
existeix.**

```
┌──────────────────────────────────────────────────────────────┐
│  SilikOS: el que hi posem nosaltres                          │
│  escriptori, eines, banc, Windows, seguretat, actualitzacions│
├──────────────────────────────────────────────────────────────┤
│  AlmaLinux 9: la base, SENSE TOCAR                           │
│  nucli, biblioteques, paquets: idèntics a Red Hat 9          │
└──────────────────────────────────────────────────────────────┘
```

**AlmaLinux 9** és un sistema gratuït que busca la compatibilitat binària (ABI) amb Red Hat Enterprise Linux 9. Un programa fet
per a Red Hat 9 hi funciona tal qual. Per això **no toquem mai la base**: ni el nucli, ni les biblioteques, ni els
fitxers que els instal·ladors comproven. Si la toquéssim, perdríem la compatibilitat, que és tot el valor.

Tot el que és SilikOS són **paquets a sobre** (RPM, el format de Red Hat), que s'instal·len i es desinstal·len com
qualsevol altre.

## 3. Què veu qui l'engega

### L'escriptori

L'escriptori és GNOME (el de Red Hat), però reorganitzat amb una extensió pròpia perquè sigui l'**interfície
Silik**, la mateixa família visual que SilikStudio. Té tres aspectes, que es canvien amb una ordre:

- **illa** (el de per defecte): una peça flotant a baix amb les aplicacions, l'inici i el rellotge;
- **barra**: una barra a baix, d'estil més clàssic;
- **silik**: una línia d'ordres a dalt, un rail de tecles a l'esquerra i una barra d'estat, com un terminal.

Per defecte és **tinta sobre paper**: blanc i negre, net, sense colors decoratius. Si es vol més vida, hi ha
**accents** (acer, cobalt, indi, violeta, groc llamp). Cada accent té un nivell normal i un nivell viu, i també fa que
les icones de les carpetes i els fitxers portin color segons el que contenen: codi, disseny, físic, dades… La tinta
original sempre hi és.

Les peces que floten (l'illa o la barra, l'Inici i el COMMAND bar) són de **vidre**: paper una mica translúcid
(86 %) sobre el fons de pantalla desenfocat, amb el seu marc fi de tinta i una ombra suau. Es veu el fons, no les
finestres de darrere: així el que hi ha sota el text és sempre el mateix i es llegeix bé sigui quin sigui el fons (el
text gris s'ha enfosquit una mica perquè ho compleixi fins i tot sobre negre), i no gasta res mentre res no canvia: el
desenfocament es fa un cop i es guarda. Es treu amb `silik look --glass off` (o `look/glass-off` al COMMAND bar) i
torna amb `--glass on`. Mesurat al banc, sense targeta gràfica: obrir l'Inici triga uns 3 ms més a pintar-se, i el
COMMAND bar té un fotograma més lent quan apareix.

### El COMMAND bar

Amb **Super+Espai** s'obre una barra on s'escriu el que es vol: el nom d'una aplicació o una adreça com `eda/try`,
`dev/can`, `win/vm-usb` o `look/island`. Tot el que fa l'escriptori passa per una sola ordre, `silik`, i **sempre
ensenya la línia que executa**: res es fa d'amagat.

### L'ordre `silik`

És el cervell del sistema. Exemples:

```
silik status                     què és aquest sistema
silik update                     actualitza-ho tot (també ho fa sol cada dia)
silik rollback                   torna el sistema a com era abans de la darrera actualització (docs/ROLLBACK.md)
silik look island --accent cobalt l'aspecte i el color
silik eda try                    les eines de xips fan feines de veritat i diuen si funcionen
silik dev can up can0 500k       engega un lector CAN a 500 kbit/s
silik win open programa.exe      obre un programa de Windows en una capsa tancada
silik secure status              revisa la seguretat del sistema
silik doctor                     diu si l'equip està bé i què cal fer
```

**`silik doctor`** és la revisió de tot l'equip amb una sola ordre. Mira, a la vegada, set àrees: el sistema
(paquets, reinici pendent, l'última actualització automàtica, disc, memòria, serveis caiguts), la seguretat (el
resum de `silik secure status`), la gràfica (la targeta i el controlador; NVIDIA, Wayland o X11), el banc (els lectors
CAN amb el seu estat i errors del bus, i els adaptadors USB que SilikOS coneix: si són teus i què has d'executar), les
eines de xips, Windows (Wine, la capsa, la màquina virtual) i la xarxa (si es troben els servidors d'actualitzacions,
el proxy). Cada línia diu **ok**, **avís**, **malament** o **desconegut** —desconegut quan no ho pot veure, mai ok— i
l'ordre exacta que ho arregla. No canvia res. Tarda unes dècimes de segon (0,14–0,27 s en un EL 9 net). La llista
d'adaptadors (`hardware.tsv`, 143 dispositius) surt de les taules dels controladors del nucli i de les regles dels
projectes originals, amb la font a cada línia; cap no s'ha provat encara amb un aparell de veritat.

## 4. Què porta

| Àmbit | Què hi ha | D'on surt |
|---|---|---|
| **Xips (EDA)** | ngspice, Xschem, Magic, KLayout, Netgen, Yosys, Icarus Verilog, Verilator, NVC (VHDL), Qucs-S, DEVSIM (simulació de dispositius); KiCad està en camí | compilades per nosaltres, o d'EPEL |
| **Eines antigues** | les versions de Cadence/Synopsys fetes per a Red Hat 6 o 7 funcionen dins de **capses** (contenidors) amb aquell sistema antic | `silik eda create` |
| **Microcontroladors** | compilador ARM, gdb, OpenOCD, dfu-util, ST-LINK, stm32flash, esptool, SDCC (8051, STM8, Z80); els IDEs dels fabricants s'instal·len amb `silik dev install` des de la teva descàrrega | EPEL i compilades per nosaltres |
| **Banc** | CAN (PEAK, Kvaser, candleLight, CANable; CAN FD), SavvyCAN, cantools (fitxers DBC), python-can, ports sèrie i RS485, Modbus, Wireshark, PulseView i sigrok (analitzadors lògics, 131 descodificadors; també els barats de 24 MHz amb el firmware fx2lafw) | EL 9, EPEL i compilades per nosaltres |
| **Windows** | Wine per als programes que hi funcionen, dins d'una capsa que no veu els teus fitxers; una màquina virtual Windows per a la resta, on es pot passar un dispositiu USB sencer (per exemple un Vector VN1630, que només té controlador per a Windows) | compilat per nosaltres (Wine 11) |
| **SilikStudio** | la primera tecla de l'escriptori | el seu propi repositori |

Allò que no és de codi obert (Cadence, Altium, els IDEs dels fabricants, CANoe) **no el portem mai**: cadascú
l'instal·la des de la seva descàrrega i amb la seva llicència. SilikOS hi posa el lloc perquè funcioni.

**Energia i rendiment.** `silik power` tria el perfil: rendiment, equilibrat, estalvi o **automàtic**, que és el de
fàbrica: a tota velocitat endollat (un ordinador de taula sempre ho està) i equilibrat amb bateria. Fa servir les
eines de la mateixa base (tuned i tuned-ppd), així que el menú del sistema mostra el mateix perfil. La memòria
comprimida (zram) s'ofereix però no s'activa mai sola, i el disc SSD s'endreça cada setmana. Per al firmware hi ha
`silik dev ccache`: mesurat compilant la HAL d'un STM32G4, tornar a compilar el mateix passa de 8,7 s a 2,9 s, però la
primera compilació és un quart més lenta, per això és opcional. Encara no s'ha mesurat què fa cada perfil en un
portàtil de veritat (consum, hores de bateria).

## 5. Seguretat i actualitzacions

- **SELinux** actiu (el de Red Hat), **tallafoc** que tanca les connexions entrants i **ssh** apagat per defecte.
- **El sistema s'actualitza sol cada dia** amb tot el que publica la base. Mai reinicia pel seu compte: quan cal
  reiniciar, l'escriptori ho diu. Amb `silik update --auto` es tria entre tot, només seguretat o res.
- Els programes de Windows s'executen en una **capsa** (bubblewrap) que no veu les claus SSH ni els documents.
- Els adaptadors USB (lectors CAN, ports sèrie, sondes de depuració) són de **qui seu davant la pantalla**, sense
  haver de donar permisos especials a ningú.

## 6. Com es fa i com es comprova

Tot està en un repositori de GitHub. Hi ha tres maneres de comprovar que funciona, de més ràpida a més real:

1. **Proves automàtiques** (323 ara mateix): comproven el codi de `silik`, els fitxers de l'escriptori, les regles
   de colors…, en segons.
2. **El banc de proves**: un escriptori GNOME de veritat dins d'un contenidor, on s'instal·len els paquets i es fan
   fotos de pantalla. Totes les imatges dels colors, les icones, SavvyCAN o PulseView surten d'aquí.
3. **La instal·lació real**: GitHub construeix la **ISO** (el disc d'instal·lació), la instal·la sola en una màquina
   virtual, engega el sistema instal·lat, el revisa (86 comprovacions la darrera vegada) i desa fotos de pantalla. És
   la prova que compta.

Cada eina que compilem nosaltres passa per una **prova de veritat** en un sistema net: el simulador ha de simular, el
descodificador ha de descodificar, la finestra ha d'obrir-se. No n'hi ha prou que «s'instal·li».

**Regla de la casa:** el fitxer `docs/STATUS.md` té dues taules, *verificat* i *no verificat*. Res passa a la primera
sense haver-ho executat de veritat. Les suposicions es marquen amb [A].

## 7. En quin punt som (12/11/2026)

**Fet i provat:**
- Instal·lació desatesa completa a GitHub: es va fer el darrer cop amb 86 comprovacions correctes.
- Eines d'EDA, microcontroladors i Wine dins de la ISO.
- Els tres aspectes de l'escriptori.

**Fet i provat al banc, encara no en una instal·lació real:**
- Els accents i les icones de color.
- L'aspecte illa per defecte.
- Les actualitzacions automàtiques.
- Les eines CAN i el banc (SavvyCAN, cantools, PulseView…).
- SDCC i el firmware fx2lafw (sense cap analitzador real connectat).
- Els programes Qt (SavvyCAN, PulseView, KLayout) amb l'aspecte i l'accent de SilikOS.
- La secció Banc a l'Inici, i l'Inici que s'obre més ràpid (de 64–76 ms a 15–17 ms amb 152 aplicacions).
- El vidre de l'illa, l'Inici i el COMMAND bar (encès per defecte), amb fons clars, foscos i fotos, a 1x i a 2x.

**Aturat per decisions o coses del propietari:**
- **GitHub no executa feines** per un problema de facturació del compte. Fins que s'arregli, no es pot construir la
  ISO nova ni provar res en instal·lació real (Settings → Billing and plans).
- **Repositori propi de paquets.** Perquè els paquets de SilikOS també s'actualitzin sols, cal:
  - un lloc públic per als paquets: el repositori de codi és privat, i un ordinador instal·lat no hi pot baixar res;
  - una clau de signatura que genera i guarda el propietari.
- **KiCad**: compilat, però la seva prova es va quedar a mitges per la facturació.

**A ARM (aarch64), provat en un contenidor ARM emulat en aquesta màquina (12/11/2026):**
- Els paquets de SilikOS són els mateixos per a les dues arquitectures: es construeixen i s'instal·len sobre AlmaLinux 9
  ARM, `silik` funciona i diu l'arquitectura, i les proves passen amb el Python 3.9 d'ARM.
- L'escriptori, el compilador ARM, gdb, stlink i les eines de banc d'EPEL existeixen per a ARM; dfu-util, stm32flash i
  OpenOCD es compilen per a ARM amb les nostres receptes, i també el simulador ngspice.
- El que no existeix a ARM, `silik` ho diu en lloc de fallar: Wine (al portàtil Snapdragon els programes de Windows
  van al seu propi Windows), les eines dels fabricants d'EDA (són x86_64), el controlador NVIDIA.
- La ISO ARM: `SILIK_ARCH=aarch64 bash tools/build_iso.sh`. Provada amb una còpia petita del disc d'AlmaLinux: el
  menú UEFI diu SilikOS i el nucli arrenca amb la recepta. La ISO real (1,5 GB) no s'ha instal·lat enlloc.
- Al Snapdragon X: com a màquina virtual Hyper-V (no provat). Detall: `docs/HARDWARE.md`.

**Següents passos proposats:**
- Una ISO que instal·li sense xarxa.
- Que l'ordre `silik` i el COMMAND bar arrenquin més ràpid (s'està mesurant).

## 8. Petit glossari

| Paraula | Vol dir |
|---|---|
| **Base** | AlmaLinux 9, el sistema de sota, idèntic a Red Hat 9 |
| **Paquet (RPM)** | un fitxer que instal·la un programa i en sap desinstal·lar-lo i actualitzar-lo |
| **EPEL** | un repositori oficial de paquets extres per a Red Hat, mantingut per Fedora |
| **ISO** | el fitxer del disc d'instal·lació |
| **Kickstart** | la recepta que diu a l'instal·lador què ha de posar, sense preguntes |
| **CI** | les proves automàtiques que GitHub fa a cada canvi |
| **Capsa / contenidor** | un sistema aïllat dins del sistema: per a eines antigues o programes que no són de fiar |
| **Wine** | una capa que fa funcionar programes de Windows a Linux sense Windows |
| **SocketCAN** | la manera com Linux veu un lector CAN: com una interfície de xarxa, `can0` |
| **DBC** | el fitxer que diu què vol dir cada trama d'un bus CAN (tensió, corrent, estat…) |
| **uaccess** | la regla que dona un dispositiu USB a la persona que seu davant la pantalla |
| **Accent** | el color opcional de l'escriptori; per defecte no n'hi ha (tinta) |
