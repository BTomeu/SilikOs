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
sobre el que tenen darrere, desenfocat, amb el seu marc fi de tinta i una ombra suau. Quin vidre, es tria:

| `silik look --glass …` | al COMMAND bar | què és |
|---|---|---|
| `off` | `look/glass-off` | paper opac, sense vidre |
| `on` (el d'ara) | `look/glass` | paper al 86 % sobre el fons de pantalla desenfocat |
| `clear` | `look/glass-clear` | paper al 70 % sobre el fons de pantalla desenfocat |
| `crystal` | `look/glass-crystal` | paper al 72 %: també es veuen, desenfocades, les finestres del darrere |
| `crystal-thin` | `look/glass-crystal-thin` | paper al 55 %, més desenfocat |

Amb `on` i `clear` es veu el fons, no les finestres: el que hi ha sota el text és sempre el mateix i no gasta res
mentre res no canvia (el desenfocament es fa un cop i es guarda). Amb els dos de cristall es veuen les finestres del
darrere de l'Inici i del COMMAND bar, i segueixen el que fan (si una es mou, es tanca o hi passa text, el vidre ho
mostra): això costa un desenfocament a cada fotograma en què canvia una finestra de sota, només mentre la peça és
oberta. L'illa i la barra, que sempre hi són, només mostren les finestres que tenen just a sota. En tots els modes el
text es llegeix (4,5:1 com a mínim) fins i tot amb negre al darrere: com més fi és el paper, més fosc es fa el text
gris, i al més fi és tinta. Les mesures de cada mode són a `docs/STATUS.md`.

El **fons de pantalla** és un full de dibuix d'enginyeria, i n'hi ha un joc de vuit, cadascun amb el seu bessó fosc:
`silik look --wallpaper wafer | plain | grid | scope | pcb | mesh | schematic | cells` (el mapa d'oblia d'ara, un full
en blanc, una quadrícula de punts, un oscil·loscopi, un circuit imprès, una malla d'elements finits, un esquema, files
de cel·les estàndard), i `NOM-dark` posa el bessó fosc a l'escriptori; al COMMAND bar, `look/wallpaper-…`. Van del més
tranquil (`plain`) al més dens (`cells`), per poder jutjar el vidre sobre fons diferents. La marca hi és, tal com és,
a `wafer` i a `grid`; als altres no hi és. Una imatge pròpia triada a la Configuració no es toca si no es demana.

Els menús del sistema, el calendari, les notificacions, l'indicador de volum, els diàlegs i el canvi de finestra
(Alt+Tab) són del mateix **paper i tinta**: marc fi de tinta, cantonades de 6 px (4 a les tecles), Cascadia Mono, el
que és triat en vídeo invers (o amb l'accent). Són paper opac, no vidre. La barra de títol de l'aspecte Silik i les
pantalles de bloqueig i d'entrada es queden fosques, amb les tecles i el camp de la contrasenya com a tot arreu.

Quan el portàtil va en mode d'**estalvi** (`silik power saver`), el vidre descansa: les peces tornen a paper opac i
recuperen el vidre en sortir-ne (`silik look --glass-saver off` ho desactiva).

### El COMMAND bar

Amb **Super+Espai** s'obre una barra on s'escriu el que es vol: el nom d'una aplicació o una adreça com `eda/try`,
`dev/can`, `win/vm-usb` o `look/island`. Tot el que fa l'escriptori passa per una sola ordre, `silik`, i **sempre
ensenya la línia que executa**: res es fa d'amagat.

La barra **es queda carregada** després del primer cop: en tancar-la s'amaga, i el Super+Espai següent només li
demana que torni. Al banc de proves surt en uns 50 ms en lloc d'uns 190 (`docs/STATUS.md`).

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
primera compilació és un quart més lenta, per això és opcional. Per a un portàtil, `silik power` diu què gasta i
què té la bateria (watts, hores que queden, salut) tal com ho dona el nucli; `silik power check` fa la llista dels
ajustos que decideixen el consum, amb l'ordre que canvia cadascun; `silik power charge 80` limita la càrrega de la
bateria en els portàtils que ho permeten; i `silik power profiles silikos` posa darrere d'«estalvi» un perfil propi que
afegeix el que el de la base es deixa (USB, dispositius PCI, Wi-Fi). Aquest perfil no ve activat. **No s'ha mesurat
cap watt**: res d'això s'ha executat encara en un portàtil de veritat (consum, hores de bateria).

## 5. Seguretat i actualitzacions

La seguretat va en tres capes: el que ve de fàbrica, el que s'activa si es demana, i el que SilikOS no és.

### De fàbrica, sense fer res

- **SELinux** actiu (el de Red Hat), **tallafoc** que tanca les connexions entrants i **ssh** apagat. Res no escolta
  fora de la màquina: els serveis de descoberta de la xarxa (rpcbind, avahi, cups-browsed) vénen apagats i
  `silik listen` els torna a engegar un per un.
- **El sistema s'actualitza sol cada dia** amb tot el que publica la base. Mai reinicia pel seu compte: quan cal
  reiniciar, l'escriptori ho diu. Abans de cada actualització es fa una **instantània** del sistema, i
  `silik rollback` hi torna.
- **El repositori de SilikOS no es pot falsejar amb còpies velles**: el sistema recorda la darrera revisió que ha
  vist i rebutja metadades més antigues, d'un altre canal, d'una altra arquitectura o sense signar. Quan en rebutja
  unes, ho diuen `silik update`, `silik doctor` i la barra d'estat.
- **Cada paquet d'eina que entra a la ISO porta el certificat d'on s'ha construït** (l'atestació de GitHub: aquest
  repositori, la branca `main`, el seu workflow). El que no en porta, es queda fora.
- **USB amb la pantalla bloquejada**: un dispositiu nou es rebutja (USBGuard). Un teclat o un ratolí sí que
  s'accepten, per poder desbloquejar. El que s'ha rebutjat es queda rebutjat fins que es torna a endollar o es
  diu `silik usb allow`.
- **Programes de Windows en una capsa** (bubblewrap) que no veu les claus SSH ni els documents. Un fitxer que no
  s'ha executat mai aquí es pregunta abans, i la resposta per defecte és **aïllat**: `silik win open --isolated`
  li dona una pantalla pròpia (no pot llegir el teclat ni fotografiar les altres finestres), xarxa només de
  sortida, cap clau, ni targeta gràfica ni so.
- Els adaptadors USB del banc (lectors CAN, ports sèrie, sondes) són de **qui seu davant la pantalla**, sense
  permisos especials.

### Si es demana

| Ordre | Què fa | Què costa |
|---|---|---|
| `silik secure status` | una trentena de línies, cadascuna **ok**, **avís**, **malament** o **desconegut**, amb l'ordre que ho arregla | res: només mira |
| `silik secure level hardened` | 19 ajustos d'un cop: el nucli es tanca i només carrega mòduls signats, la memòria es posa a zero en repartir-la, l'IOMMU estricte, deu contrasenyes dolentes bloquegen el compte deu minuts, la pantalla d'entrada no ensenya usuaris… | els mòduls sense signar deixen de carregar (NVIDIA compilat a la màquina abans d'enrolar-ne la clau, VirtualBox), no hi ha hibernació, i algunes eines de depuració del nucli no van. Cada ajust es pot deixar fora amb `--without`, i `silik secure level default` ho desfà tot |
| xifrar el disc | es marca a l'instal·lador; després `silik disk tpm enroll` lliga el disc al xip TPM de la màquina amb un **PIN** | cal escriure el PIN a cada arrencada. Si canvia l'arrencada segura o el disc es posa en una altra màquina, el PIN ja no obre i cal la contrasenya o la clau de recuperació |

`docs/HARDENED.md` diu què costa cada ajust, un per un; `docs/DISK.md`, el disc; `docs/USB.md`, l'USB.

### El que no és

- **No és GrapheneOS ni Qubes.** La base no es toca (és la condició de la compatibilitat amb Red Hat), i per tant el
  nucli i les biblioteques són els de RHEL 9, sense endurir més del que es pot amb ajustos.
- **La sessió és X11** (les eines EDA ho demanen): dos programes de la mateixa sessió es poden veure el teclat l'un
  a l'altre. Per això la capsa aïllada de Windows porta el seu propi servidor de pantalla.
- **Els programes que engega l'usuari no van confinats** (ni les eines EDA ni els IDE): el que protegeix d'ells és
  el compte d'usuari, no una capsa.
- **Res no és impenetrable.** S'ha auditat dues vegades atacant-lo (13 i 14/11/2026). La primera va trobar forats
  al nostre codi, i es van arreglar. La segona no va trobar cap camí d'un usuari normal a root; el que va trobar a
  la cadena de paquets i a la capsa de Windows es va arreglar, i el que queda obert és a `docs/SECURITY.md`.

## 6. Com es fa i com es comprova

Tot està en un repositori de GitHub. Hi ha tres maneres de comprovar que funciona, de més ràpida a més real:

1. **Proves automàtiques** (més de 1600 ara mateix): comproven el codi de `silik`, els fitxers de l'escriptori, les regles
   de colors…, en segons.
2. **El banc de proves**: un escriptori GNOME de veritat dins d'un contenidor, on s'instal·len els paquets i es fan
   fotos de pantalla. Totes les imatges dels colors, les icones, SavvyCAN o PulseView surten d'aquí.
3. **La instal·lació real**: GitHub construeix la **ISO** (el disc d'instal·lació), la instal·la sola en una màquina
   virtual, engega el sistema instal·lat, el revisa (166 comprovacions la darrera vegada) i desa fotos de pantalla.
   Tres proves més fan el mateix amb el disc xifrat, el nivell endurit i el tornar enrere.
   És la prova que compta.

Cada eina que compilem nosaltres passa per una **prova de veritat** en un sistema net: el simulador ha de simular, el
descodificador ha de descodificar, la finestra ha d'obrir-se. No n'hi ha prou que «s'instal·li».

**Regla de la casa:** el fitxer `docs/STATUS.md` té dues taules, *verificat* i *no verificat*. Res passa a la primera
sense haver-ho executat de veritat. Les suposicions es marquen amb [A].

## 7. Què té de bo i què no

Sense adorns. Cada punt diu on s'ha vist; «vist» vol dir executat, no pensat.

### El que té de bo

| Què | On s'ha vist |
|---|---|
| **Compatibilitat amb Red Hat 9 intacta**: la base no es toca, i una prova ho vigila a cada canvi | les proves automàtiques; la instal·lació de la CI |
| **Tot en un**: xips, microcontroladors, banc i Windows en una instal·lació desatesa, amb les eines provades fent feina de veritat (13 de 13 eines EDA, 7 de 7 de microcontroladors) | CI, sistema instal·lat en màquina virtual |
| **Una sola ordre, `silik`, que ensenya el que fa**: res passa d'amagat, i `--dry-run` no toca res | tot el sistema |
| **Menys memòria que la base de sèrie**: 160 a 175 MB menys que l'AlmaLinux Workstation, a la mateixa màquina | workflow Compare, 14/11/2026 |
| **L'escriptori no costa temps**: la shell amb la nostra extensió arrenca igual de ràpid que la de sèrie (1,39–1,45 s contra 1,43–1,49 s) | workflow Compare, tres execucions |
| **Tornar enrere d'una actualització** en un disc de veritat | CI, 70 comprovacions |
| **Disc xifrat lligat al TPM amb PIN**: obre amb el PIN; no obre si canvia l'arrencada segura o la màquina | CI, 90 comprovacions, TPM de programari |
| **Nivell endurit**: el nucli rebutja un mòdul sense signar | CI, 96 comprovacions |
| **USB bloquejat amb la pantalla bloquejada** | CI, amb dispositius endollats a la màquina virtual |
| **Capsa aïllada de Windows** que no arriba a la pantalla, al bus ni a les claus de la sessió | CI, amb SELinux actiu |
| **Instal·lació sense xarxa**: una ISO de 4,6 GB que ho porta tot | workflow Offline ISO, 133 comprovacions |
| **Diu la veritat de si mateix**: `docs/STATUS.md` separa el verificat del no verificat, i una comprovació que falta és una fallada, no un silenci | la CI mateixa |

### El que no té de bo

| Què | Per què | Què s'hi pot fer |
|---|---|---|
| **No s'ha engegat mai en maquinari de veritat** | tot és màquina virtual i contenidor | una setmana al Ryzen i al portàtil: és el pas que falta de debò |
| **Cap watt mesurat, cap hora de bateria** | no hi ha hagut cap portàtil | el mateix |
| **Arriba a l'escriptori una mica més tard que la base** (0,08 a 0,71 s, dins del soroll de la mesura) | la sessió X11, que cal per a l'EDA | res: és una decisió presa |
| **El repositori de paquets no està publicat ni signat** | falten GitHub Pages i la clau, que són del propietari | fins llavors, un sistema instal·lat no rep les novetats de SilikOS (sí les de la base) |
| **La capsa aïllada de Windows encara veu la xarxa local** (el router, un NAS) | la xarxa de la capsa és «només de sortida», no «només internet» | 4 a 6 hores de feina; no començat |
| **Ocupa més**: 8,1 GB contra 5,3 GB de la base, 1557 paquets contra 1231 | porta les eines | són paquets: el que no es fa servir es pot desinstal·lar |
| **GNOME 40 i X11 són vells** | són els de RHEL 9 | EL 10 està estudiat (`docs/EL10.md`), no fet |
| **Les eines dels fabricants (Cadence, Synopsys, Altium) no s'han provat** | no en tenim cap llicència | qui en tingui, `silik eda` i `docs/EDA.md` |
| **Cap adaptador de banc provat** (CAN, sondes, analitzadors) | no n'hi ha hagut cap | el banc de l'equip |
| **A ARM no hi ha Wine ni les eines EDA dels fabricants** | no existeixen per a ARM | `silik` ho diu en lloc de fallar |
| **Un sol mantenidor i cap usuari encara** | és un prototip | fer-lo servir |

### El que no farà mai

- Portar programari que no és de codi obert, llicències o claus.
- Tocar la base per ser «més segur» o «més ràpid»: perdria l'única cosa que el fa útil per a l'EDA.
- Triar o esborrar un disc pel seu compte a la instal·lació.
- Dir que una cosa funciona sense haver-la executat.

## 8. En quin punt som (14/11/2026)

**Vist en un sistema instal·lat (màquina virtual amb KVM, a GitHub, SELinux actiu):**

| Prova | Resultat | Execució |
|---|---|---|
| Instal·lació desatesa, escriptori, eines, Windows, USB, auditoria | 166 comprovacions bé, 0 malament | CI 43549553439 |
| Nivell endurit: posar-lo, reiniciar, comprovar, treure'l | 96 bé, 0 malament | CI 43560389589 |
| Disc xifrat + arrencada segura + TPM amb PIN, nou arrencades | 90 bé, 0 malament | CI 43560389589 |
| Actualitzar i tornar enrere | 70 bé, 0 malament | CI 43560389589 |
| ISO sense xarxa, en una màquina sense targeta de xarxa | 133 bé, 0 malament | Offline ISO 43560436638 |
| Al costat de l'AlmaLinux de sèrie | 160–175 MB menys de memòria; escriptori 0,08–0,71 s més tard | Compare 43560434143 |

Dues comprovacions d'USB de la primera fila (`silik usb allow` i que el dimoni rebutgi un usuari sense sudo) no
s'havien executat mai per un error de l'script de prova, trobat i arreglat el 14/11: la propera execució les dirà.

Les proves automàtiques són més de 1600, i passen a la CI de GitHub a x86_64 i a ARM.

**Fet i provat al banc, encara no en una instal·lació real:**
- La barra d'estat que diu «repositori rebutjat».
- Les eines CAN i el banc (SavvyCAN, cantools, PulseView…): sense cap adaptador de veritat.
- Els temps de l'Inici i del COMMAND bar (el banc dibuixa sense targeta gràfica).

**Només ho pot fer el propietari:**
- **Activar GitHub Pages** (Settings → Pages → Source: GitHub Actions): sense això cap sistema instal·lat pot rebre
  les novetats de SilikOS.
- **La clau de signatura** dels paquets (`docs/SIGNING.md`): ara el repositori surt sense signar i cap sistema
  l'accepta.
- **Regles de protecció** de la branca `main` i de les etiquetes `v*` a GitHub.
- **Triar la llicència** del codi.
- **Provar-lo en maquinari**: `docs/PRIMERA-HORA.md`.

**No provat enlloc:** cap maquinari real (ni el Ryzen, ni un portàtil, ni un TPM de veritat, ni una sonda, ni un
adaptador CAN, ni un USB d'instal·lació).

**A ARM (aarch64):**
- Els paquets de SilikOS són els mateixos per a les dues arquitectures, i es construeixen i es proven en màquines
  ARM de GitHub a cada canvi.
- L'escriptori, el compilador ARM, gdb, stlink i les eines de banc existeixen per a ARM; dfu-util, stm32flash,
  OpenOCD i ngspice es compilen amb les nostres receptes.
- El que no existeix a ARM, `silik` ho diu en lloc de fallar: Wine, les eines dels fabricants d'EDA, el controlador
  NVIDIA.
- La ISO ARM no s'ha instal·lat enlloc. Al Snapdragon X: com a màquina virtual Hyper-V (no provat).
  Detall: `docs/HARDWARE.md`.

**Següents passos proposats:**
- Fer-lo servir una setmana al Ryzen i en un portàtil, i apuntar on falla.
- Publicar i signar el repositori (els passos del propietari).
- Tancar la xarxa local a la capsa aïllada de Windows.

## 9. Petit glossari

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
| **TPM** | un xip de la placa que guarda una clau i només la dona si la màquina ha arrencat com sempre |
| **Arrencada segura (Secure Boot)** | el firmware només engega un sistema signat |
| **Lockdown** | el nucli no es deixa modificar ni per l'administrador mentre funciona |
| **Atestació** | el certificat de GitHub que diu on i com s'ha construït un fitxer |
| **USBGuard** | el servei que decideix quins dispositius USB s'accepten |
