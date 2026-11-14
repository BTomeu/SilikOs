# La primera hora amb SilikOS

Per a qui no ha vist mai SilikOS i té una placa, una sonda i un adaptador CAN damunt la taula. L'objectiu: de la ISO
a programar la placa i veure el bus CAN, en menys d'una hora (és l'objectiu: ningú ho ha cronometrat encara), sense
preguntar res a ningú. Si en algun pas has hagut de
preguntar, aquell pas està malament: apunta'l (secció 9).

Cada pas diu fins on està provat. **Res d'aquesta guia s'ha fet encara en maquinari real**: la instal·lació i les
ordres s'han executat en una màquina virtual (CI de GitHub, 13/11/2026); la sonda, la placa i l'adaptador CAN, no.

## 0. Què et cal

| Què | Detall |
|---|---|
| Un PC x86_64 amb UEFI | un disc que es pugui esborrar sencer: la instal·lació n'ocupa 14-15 GB (mesurat al CI). La màquina virtual de prova té 4 GB de memòria; no s'ha provat amb menys |
| Un USB de 4 GB | per a l'instal·lador |
| Xarxa per cable durant la instal·lació | l'instal·lador baixa 2,5 GB (`docs/NUMEROS.md`) |
| La sonda | ST-LINK (o una Nucleo, que en porta un), J-Link o CMSIS-DAP |
| L'adaptador CAN | PCAN-USB, Kvaser, candleLight / CANable, o un altre amb driver al nucli (`docs/DRIVERS.md`) |

Si el portàtil és molt nou, mira abans `docs/DRIVERS.md`: diu quin Wi-Fi, quina xarxa i quins gràfics tenen driver.

## 1. La ISO

Encara no hi ha cap ISO per baixar amb un enllaç fix. Tres maneres:

- **Del CI, la ISO de xarxa (2 GB)**: a GitHub, Actions → CI → l'última execució **en verd** de `main` → Artifacts
  → `silikos-iso` (cal tenir sessió iniciada a GitHub; baixa un `.zip` amb la ISO a dins; es guarda 14 dies).
  És la ISO que aquella mateixa execució ha instal·lat i comprovat. Fins al 14/11/2026 aquest artefacte només es
  desava amb una etiqueta de versió, i no n'hi ha cap: aquesta guia enviava a un artefacte que no existia.
- **Del CI, la ISO sense xarxa (4,6 GB)**: Actions → Offline ISO → Run workflow; quan acaba en verd, Artifacts →
  `silikos-offline-iso`. Porta tots els paquets: la instal·lació no baixa res (`docs/OFFLINE.md`). Cal un USB de 8 GB.
- **Fer-la**: en qualsevol Linux amb `xorriso`, `mtools`, `cpio`, `curl` i `gpg`: `bash tools/build_iso.sh`
  (`docs/BUILD.md`).

Copia-la a l'USB (canvia `sdX` pel teu USB; **esborra l'USB**):

```bash
sudo dd if=SilikOS-9.8-x86_64-netinstall.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

Des de Windows [A: no provat aquí]: un programa que escrigui la imatge tal com és, byte a byte (balenaEtcher; o
Rufus, triant «DD Image» quan pregunta el mode). Un llapis fet amb Ventoy o copiant-hi els fitxers a mà no val:
el menú busca l'instal·lador i el seu kickstart per l'etiqueta del volum de la ISO.

Provat: la ISO es construeix i s'instal·la a cada execució del CI. @MEDIA@ Des d'un USB en una màquina real: no.

## 2. Instal·lar

1. Arrenca de l'USB. Al menú, **Install SilikOS 9.8**.
2. Tria l'idioma.
3. **Installation Destination**: tria tu el disc. L'instal·lador no n'esborra cap fins que tu ho confirmes, però
   mira bé quins surten marcats: amb més d'un disc pot ser que els marqui tots [llegit al codi de l'instal·lador,
   no vist]; desmarca els que no vols tocar. Deixa
   "Automatic": fa el disc de manera que després es pugui tornar enrere d'una actualització (`silik rollback`).
   Marca **Encrypt my data** i posa-hi una contrasenya llarga: l'instal·lador no ho marca tot sol, i sense xifrar
   qui tingui el portàtil a les mans en llegeix el disc (`docs/DISK.md`; després, `silik disk`).
4. Crea el teu usuari i comença. Quan acabi, reinicia i treu l'USB.

Provat: instal·lació desatesa en màquina virtual (168 comprovacions bé a l'execució 43566415197). Amb les pantalles a
mà i en un disc real: no.

### En un disc extern, per entrar-hi des del menú d'arrencada

Per provar SilikOS sense tocar el disc de l'ordinador: el sistema sencer en un disc extern, i el menú d'arrencada
de l'ordinador (F12, F9 o Esc en engegar, segons el fabricant) per triar. **Provat en màquines virtuals, no encara
en un disc ni en un ordinador de veritat** (`tests/install/external.sh`, workflow External disk: la instal·lació
amb UEFI en un disc USB al costat d'un altre disc que fa d'«el de l'ordinador», i l'arrencada després). El que
segueix s'ha vist allà, tret del que va marcat [A]. Detall: `docs/DISK.md`.

Abans de començar:

- Si Windows té BitLocker, tingues la **clau de recuperació** a mà (account.microsoft.com/devices/recoverykey)
  abans de tocar res del firmware [A: no s'ha provat amb Windows al costat].
- Desendolla els altres discos externs i llapis USB que no facin falta: així a la pantalla de discos només hi ha
  el que vols.
- El disc extern **s'esborrarà sencer**.

1. Endolla el disc extern (millor un SSD en una caixa USB 3, en un port USB 3) i l'USB de l'instal·lador.
2. Arrenca de l'USB de l'instal·lador (menú d'arrencada del firmware). Al menú de SilikOS, la **tercera entrada**:
   **Install SilikOS 9.8 on an external disk (the boot order of this computer is kept)**. Amb aquesta entrada:
   - l'instal·lador no es posa el primer a la llista d'arrencada de l'ordinador ni en treu cap entrada (vist: la
     llista, igual abans i després de la instal·lació);
   - **els discos de l'ordinador no surten a la pantalla**: l'instal·lador només ensenya els discos que són per USB,
     i per tant el disc intern no es pot marcar per error. Vist a la prova (execució
     43587008261): la prova no anomena cap disc i esborra tots els que l'instal·lador ensenya; el disc «de
     l'ordinador» en surt idèntic byte a byte. **Només les ISO fetes a partir del commit 27309ef (14/11/2026) ho
     porten.**
3. **Installation Destination**: hi ha d'haver el disc extern (i potser l'USB de l'instal·lador). Marca el disc
   extern; guia't per la mida i el nom. Si no hi surt cap disc, el teu disc extern no va per USB (Thunderbolt,
   eSATA): torna enrere i fes servir la primera entrada, mirant molt bé què marques.
   Deixa «Automatic». [A: així és l'instal·lador de la base; no vist aquí, la prova no passa per les pantalles]
   Si el disc ja tenia particions, l'instal·lador demana alliberar espai: «Reclaim space» → «Delete all» →
   «Reclaim space»; només toca el disc marcat.
4. Marca **Encrypt my data** amb una contrasenya llarga: un disc extern es perd més fàcilment que un ordinador.
   La demanarà cada cop que engeguis (vist a cada arrencada de la prova).
5. Crea l'usuari, comença, i quan acabi apaga, treu l'USB de l'instal·lador i engega amb el menú d'arrencada del
   firmware: tria el disc extern.

Després (vist a la prova, tret del que va marcat):

- **Apaga el sistema abans de desendollar el disc.** Si es treu mentre funciona, el sistema cau a l'instant.
- **El primer cop que s'arrenca des del disc extern, el carregador de la base s'afegeix a la llista de l'ordinador
  amb el nom `almalinux` i s'hi posa el primer** (i en una màquina amb TPM reinicia un cop). Des de llavors, amb el
  disc endollat, l'ordinador entra a SilikOS tot sol; sense el disc, al que tenia [A: un firmware se salta
  l'entrada d'un disc que no hi és; no vist en un de veritat]. Per tornar a posar primer el sistema de
  l'ordinador: la configuració del firmware, o des de SilikOS `sudo efibootmgr` (la llista) i
  `sudo efibootmgr -o NÚMERO,NÚMERO,...` (l'ordre).
- El disc de l'ordinador no es toca: a la prova, el disc que fa d'«el de l'ordinador» és idèntic byte a byte
  després de la instal·lació i després de dues arrencades des del disc extern.
- `silik disk check` diu el que cal saber d'un sistema en disc extern.
- **El TPM**: `silik disk tpm enroll` lliga el disc a *aquest* ordinador. Si el disc ha d'anar d'un ordinador a
  un altre, deixa'l amb la contrasenya i prou.
- **En un altre ordinador**: el disc tal com queda instal·lat arrenca en un altre ordinador per USB, també amb
  Secure Boot activat. Perquè arrenqui també endollat per SATA o NVMe, `silik disk check` dona dues ordres (un
  paquet de la base i `dracut`) que refan l'arrencada amb tots els controladors.
- La protecció USB i el perfil d'estalvi deixen en pau el disc on és el sistema (USBGuard l'accepta; el perfil
  no l'adorm).

## 3. El primer minut a l'escriptori

- La peça de baix és l'illa: la marca a l'esquerra obre l'**Inici** (o la tecla Super).
- **Super+Espai** obre el COMMAND bar: escrius una adreça (`sys/`, `dev/`, `look/`...) i a sota veus l'ordre que
  s'executarà. Tot el que fa l'escriptori és una ordre `silik` que pots copiar.
- Obre un terminal (és a l'Inici, entre els ancorats).

## 4. Com està la màquina

```bash
silik doctor          # sistema, seguretat, gràfics, maquinari, banc, EDA, Windows, xarxa: ok / warn / bad i l'ordre que ho arregla
silik hw check        # cada dispositiu amb el seu driver, o "cap driver en aquest nucli" i què fer
```

Si `silik doctor` diu `bad` en alguna cosa que no sigui "el disc no està xifrat", apunta-ho.

Provat: en màquina virtual. Amb el teu maquinari: és el primer que volem saber.

## 5. La sonda i la placa

```bash
silik dev tools       # el compilador ARM, OpenOCD, dfu-util, les eines de l'ST-LINK... i què falta
silik dev try         # les eines fan feina de veritat: compilen un programa per a Cortex-M4, l'enllacen, el depuren
```

Connecta la sonda (no cal ser root: les regles ja donen la sonda a qui seu a la pantalla):

```bash
silik dev try probe   # OpenOCD veu la sonda?
st-info --probe       # (ST-LINK) quina placa hi ha
```

Programar un ELF amb OpenOCD (canvia `stm32g4x` per la teva família):

```bash
openocd -f interface/stlink.cfg -f target/stm32g4x.cfg -c "program build/firmware.elf verify reset exit"
```

STM32CubeIDE no ve amb el sistema (és d'ST): baixa'l de la web d'ST i

```bash
silik dev install ~/Baixades/en.st-stm32cubeide_*.sh.zip
```

Provat: `silik dev try` passa en màquina virtual (7 feines). Amb una sonda i una placa: no. `silik dev install` amb
l'instal·lador real d'ST: no.

## 6. El bus CAN

```bash
silik dev can                     # els adaptadors que veu
silik dev can up can0 500k        # imprimeix les tres ordres `ip link` que fa, i les fa
candump can0                      # el que passa pel bus
cansend can0 123#DEADBEEF         # envia una trama
```

- CAN FD: `silik dev can up can0 500k --fd 2M`. Només escoltar, sense ni reconèixer trames: `--listen`.
- Amb finestres: SavvyCAN (a l'Inici, categoria Banc). Amb un DBC: `candump can0 | cantools decode fitxer.dbc` (el paquet
  silik-pylab; `silik dev tools` diu si hi és).

Provat: les ordres, en màquina virtual sense adaptador. Amb un adaptador i un bus: no.

## 7. El port sèrie

```bash
silik dev serial                  # els ports i què són
picocom -b 115200 /dev/ttyACM0    # Ctrl-A Ctrl-X per sortir
```

## 8. Si vols anar un pas més enllà: una prova automàtica (experimental)

```bash
mkdir prova && cd prova
silik hil new                     # un exemple: una ECU simulada, el seu DBC i un pla
silik hil run ecu.plan            # 23 passos; no cal maquinari
```

El pla és un fitxer de text: quines trames s'envien, què s'espera i en quant de temps, quin requisit verifica cada pas.
`bench.plan` és el mateix per a una placa de veritat (`docs/HIL.md`). Només s'ha executat amb l'ECU simulada.

## 9. Si alguna cosa falla

- **L'USB de l'instal·lador no surt al menú d'arrencada del firmware**: torna'l a escriure (a dalt, secció 1) i
  prova un altre port. [A]
- **La pantalla es queda negra en arrencar l'instal·lador o el sistema** (portàtils amb gràfics NVIDIA) [A: no
  vist; és el remei habitual de la base]: al menú, tecla `e` sobre l'entrada, afegeix `nomodeset` al final de la
  línia que comença per `linux`, i Ctrl+X. Amb el sistema instal·lat: `silik hw nvidia` diu què hi ha i què fer.
- **L'instal·lador no troba xarxa** (la ISO de xarxa baixa els paquets): cable, o el mòbil per USB, o el Wi-Fi a
  «Network & Host Name» i després torna a obrir «Installation Source». O fes servir la ISO sense xarxa.
- Una actualització ha trencat alguna cosa: `silik rollback` (torna a com estava abans de l'última actualització) i
  reinicia.
- Per explicar-ho, envia aquestes dues sortides:

```bash
silik doctor --json > doctor.json
silik hw check --json > maquinari.json
```

- I apunta **on t'has encallat**: quin pas, què esperaves i què ha passat. Aquesta llista és el que fa falta per
  convertir això en un producte.

## Què queda escrit de la teva hora

Si has arribat al final, digues-nos el temps que has trigat i el model del PC. `maquinari.json` de la teva màquina és
la primera fila de la llista de maquinari provat: avui aquesta llista és buida.
