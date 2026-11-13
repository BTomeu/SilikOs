# SilikOS: rendiment comparat amb altres sistemes (13/11/2026)

La pregunta del propietari: "com és el rendiment comparat amb altres sistemes operatius?" Aquí hi ha el que s'ha
mesurat, amb `tools/bench_os` (com es fa: `tools/bench_os/README.md`). Cap número és estimat.

## Què es compara, i què no

Es compara **l'espai d'usuari i les eines que porta cada sistema**: cada sistema corre dins la seva imatge oficial
de contenidor, tots sobre **el mateix kernel i la mateixa màquina**. Per tant **no** és una comparació de kernels,
d'arrencada, de memòria en repòs, de resposta de l'escriptori ni de gràfics: res d'això s'ha mesurat (vegeu el final).

- **Màquina:** x86_64, Intel Xeon a 2,30 GHz (una màquina virtual al núvol, 4 processadors, 15 GB), kernel 6.18.44,
  Docker 29.9.2. El contenidor de mesura va sense xarxa, fixat a 4 processadors, escrivint a memòria.
- **Mètode:** una passada d'escalfament i després 5; la xifra és la mediana del temps de rellotge.
- **Entrades:** generades per `tools/bench_os/gen.py`, les mateixes a tots els sistemes. Els programes imprimeixen
  un checksum i tots els sistemes han donat el mateix (Icarus i Verilator també coincideixen entre ells).
- **Columnes:** `almalinux-9` és la base de SilikOS amb CRB i EPEL. `silikos-9` és el mateix més els builds propis
  de SilikOS (ngspice i Yosys, els RPM del release `eda-tools`). Tota la resta de `silikos-9` són **els mateixos
  binaris** que `almalinux-9`: la diferència entre aquestes dues columnes és el soroll de la màquina.
- **Les versions són diferents a cada sistema** (GCC 11 a 16, Python 3.9 a 3.15, Yosys 0.33 a 0.70). És el que rep
  l'usuari de cada sistema, però un compilador més nou no fa la mateixa feina que un de vell.

## El soroll, abans de llegir res

Les dues columnes amb els mateixos binaris difereixen fins a un 15 % (Verilator, fer el model: 2,52 s i 2,90 s;
firmware: 5,51 s i 6,06 s). ngspice, mesurat dues vegades, va canviar fins a un 20 % al mateix sistema. Per tant:

- una diferència de **menys d'un 15 % no és una diferència**;
- les files de menys d'un segon (enllaç, `zstd`, descompressió) només donen l'ordre de magnitud.

## On SilikOS és més lent, o va per darrere

- **Python:** la base porta Python 3.9. El bucle numèric triga 3,27 s; a Ubuntu 24.04 (3.12) 2,64 s, a
  AlmaLinux 10 (3.12) 2,90 s, a Fedora 45 (3.15) 2,96 s: entre un 10 % i un 24 % més lent. Llegir el log CAN:
  2,52 s contra 2,24–2,33 s (al límit del soroll).
- **Gestor de paquets:** instal·lar 4 eines ja baixades triga 1,13 s amb dnf 4; amb el dnf 5 de Fedora, 0,72 s.
- **`xz`, descomprimir:** 0,60 s (xz 5.2.5) contra 0,44 s (xz 5.6 i 5.8). Fila curta: ordre de magnitud.
- **Versions velles:** GCC 11.5 natiu i 12.4 per a ARM, quan Fedora porta 16.2 i 15.2. No s'ha mesurat què hi
  guanya el codi generat més enllà d'aquest programa (vegeu la fila "el programa compilat": tots iguals).
- **ngspice i Yosys no hi són** a AlmaLinux 9 ni a EPEL 9 (ni a AlmaLinux 10 amb EPEL 10). SilikOS els porta
  compilats; sense SilikOS, la base no en té.

## La taula

Mediana de 5 passades i versió de l'eina. En negreta el més ràpid de la fila (recordeu el soroll).

| Càrrega | almalinux-9 | silikos-9 | ubuntu-24.04 | fedora (45) | almalinux-10 |
|---|---|---|---|---|---|
| Build de firmware (Cortex-M4, `make -j4`, -O2) | **5,51 s** · 12.4.0 | 6,06 s · 12.4.0 | 6,03 s · 13.2.1 | 5,94 s · 15.2.0 | 6,55 s · 14.1.0 |
| Compilació nativa (`make -j4`, -O2) | **4,59 s** · 11.5.0 | 4,92 s · 11.5.0 | 5,42 s · 13.3.0 | 5,46 s · 16.2.1 | 5,83 s · 14.3.1 |
| Enllaç natiu | 0,07 s · 2.35.2 | 0,08 s · 2.35.2 | 0,07 s · 2.42 | 0,07 s · 2.47 | **0,06 s** · 2.41 |
| El programa que ha fet cada gcc, executant-se | 5,08 s · 11.5.0 | 5,27 s · 11.5.0 | 5,42 s · 13.3.0 | **5,06 s** · 16.2.1 | 5,39 s · 14.3.1 |
| Icarus Verilog: compilar + simular | 4,73 s · 12.0 | 4,82 s · 12.0 | 5,87 s · 12.0 | **4,38 s** · 13.0 | 4,63 s · 13.0 |
| Verilator: fer el model | **2,52 s** · 5.022 | 2,90 s · 5.022 | 3,14 s · 5.020 | 3,69 s · 5.046 | 3,40 s · 5.030 |
| Verilator: simular | 7,37 s · 5.022 | 7,78 s · 5.022 | 7,44 s · 5.020 | **7,15 s** · 5.046 | 7,54 s · 5.030 |
| ngspice: escala RC (dues mesures) | no empaquetat | 8,18 s i 7,86 s · 47 | 8,24 s i 9,30 s · 42 | 9,38 s · 47 | no empaquetat |
| ngspice: oscil·ladors MOS (dues mesures) | no empaquetat | 3,82 s i 4,15 s · 47 | 4,26 s i 3,39 s · 42 | 4,29 s · 47 | no empaquetat |
| Yosys: síntesi | no empaquetat | **13,27 s** · 0.70 | 41,04 s · 0.33 | 23,30 s · 0.67 | no empaquetat |
| Python: llegir i filtrar un log CAN de 200 MB | 2,52 s · 3.9.25 | 2,64 s · 3.9.25 | 2,33 s · 3.12.3 | **2,24 s** · 3.15.2 | 2,69 s · 3.12.15 |
| Python: bucle numèric | 3,27 s · 3.9.25 | 3,34 s · 3.9.25 | **2,64 s** · 3.12.3 | 2,96 s · 3.15.2 | 2,90 s · 3.12.15 |
| `xz -T1`: comprimir 64 MB | **51,05 s** · 5.2.5 | 53,62 s · 5.2.5 | 55,61 s · 5.4.5 | 59,21 s · 5.8.3 | 52,90 s · 5.6.2 |
| `xz -T1`: descomprimir | 0,60 s | 0,55 s | 0,51 s | 0,44 s | **0,44 s** |
| `zstd -T1`: comprimir 64 MB | 0,31 s · 1.5.5 | **0,23 s** · 1.5.5 | 0,27 s · 1.5.5 | 0,31 s · 1.5.7 | 0,27 s · 1.5.5 |
| `zstd -T1`: descomprimir | 0,11 s | **0,06 s** | 0,06 s | 0,09 s | 0,08 s |
| Gestor de paquets: 4 eines, sense xarxa | 1,13 s · dnf 4.14 | 1,05 s · dnf 4.14 | 1,34 s · apt 2.8.4 | **0,72 s** · dnf 5.4.6 | 1,07 s · dnf 4.20 |

Les línies originals (amb mínim i màxim de cada cel·la): `docs/rendiment-2026-11-13-x86_64.jsonl`.

## Què mostra

- **Yosys:** el build de SilikOS (0.70) sintetitza el disseny en 13,3 s; el de Fedora 45 (0.67) en 23,3 s; el
  d'Ubuntu 24.04 (0.33) en 41,0 s. És l'única diferència gran de la taula. No s'ha mirat per què el de Fedora,
  amb una versió propera, triga 1,75 vegades més. El resultat és semblant: 104 781, 104 891 i 107 723 cel·les.
- **Compilar:** la base compila aquest projecte entre un 10 % i un 27 % més de pressa que els altres (4,59–4,92 s
  contra 5,42–5,83 s). És perquè GCC 11 és més vell i fa menys feina, no perquè el sistema sigui millor.
- **El codi compilat corre igual** amb GCC 11, 13, 14 i 16 (5,06–5,42 s, dins el soroll), en aquest programa.
- **ngspice:** cap diferència que es pugui afirmar entre el build de SilikOS, el d'Ubuntu i el de Fedora.
- **Firmware, Icarus, Verilator simulant, `xz` comprimint:** tot dins el soroll, o gairebé.
- **Paquets que falten:** de les 9 eines provades, a la base n'hi falten 2 (ngspice, Yosys); a Ubuntu 24.04 i a
  Fedora 45, cap. Les dues que falten són les que SilikOS afegeix.

En resum: per a feina de compilar i simular, l'espai d'usuari d'EL 9 **no és ni més ràpid ni més lent** que el
d'Ubuntu o Fedora de manera que es noti, tret de Python (més lent) i de Yosys (més ràpid amb el build de SilikOS).

## Als runners de GitHub, en x86_64 i en ARM (13/11/2026)

**x86_64, amb tots set sistemes.** Workflow Bench OS, execució 43450793847 (commit 4da5ceb), en una màquina de
GitHub de 4 processadors: el mateix mètode que la taula de dalt, en una altra màquina (no es poden barrejar les
dues). És la primera amb AlmaLinux 9, SilikOS i AlmaLinux 10 a GitHub: a l'anterior (43436445832) un error del nostre
script feia fallar la preparació de `dnf`. Després del temps, la versió de l'eina.

| Càrrega | AlmaLinux 9 | SilikOS | Ubuntu 24.04 | Debian estable | Fedora | openSUSE Tumbleweed | AlmaLinux 10 |
|---|---|---|---|---|---|---|---|
| Build de firmware Cortex-M4 | 6,04 s · 12.4.0 | 6,22 s · 12.4.0 | 6,26 s · 13.2.1 | 6,65 s · 14.2.1 | 7,34 s · 15.2.0 | 6,80 s · 15.3.0 | 7,05 s · 14.1.0 |
| Compilació nativa | 5,23 s · 11.5.0 | 5,12 s · 11.5.0 | 5,61 s · 13.3.0 | 5,68 s · 14.2.0 | 6,48 s · 16.2.1 | 7,32 s · 16.2.1 | 6,31 s · 14.3.1 |
| Enllaçat natiu | 0,07 s · 2.35.2-72.el9 | 0,07 s · 2.35.2-72.el9 | 0,06 s · 2.42 | 0,06 s · 2.44 | 0,07 s · 2.47.20260726 | 0,07 s · 2.47.0.20260921-3 | 0,07 s · 2.41-63.el10.alma.1 |
| El programa compilat, executant-se | 4,72 s · 11.5.0 | 4,78 s · 11.5.0 | 5,00 s · 13.3.0 | 4,84 s · 14.2.0 | 4,92 s · 16.2.1 | 4,82 s · 16.2.1 | 4,96 s · 14.3.1 |
| Icarus Verilog | 3,60 s · 12.0 | 3,59 s · 12.0 | 3,85 s · 12.0 | 3,54 s · 12.0 | 3,57 s · 13.0 | 3,31 s · 13.0 | 3,69 s · 13.0 |
| Verilator, fer el model | 2,28 s · 5.022 / 11.5.0 | 2,07 s · 5.022 / 11.5.0 | 2,56 s · 5.020 / 13.3.0 | 2,66 s · 5.032 / 14.2.0 | 3,73 s · 5.046 / 16.2.1 | ha fallat | 3,03 s · 5.030 / 14.3.1 |
| Verilator, simular | 4,42 s · 5.022 | 4,35 s · 5.022 | 4,40 s · 5.020 | 4,25 s · 5.032 | 4,79 s · 5.046 | ha fallat | 4,59 s · 5.030 |
| ngspice, escala RC | no empaquetat | 2,56 s · 47 | 2,64 s · 42 | 3,20 s · 44.2 | 3,77 s · 47 | 3,59 s · 47 | no empaquetat |
| ngspice, oscil·ladors MOS | no empaquetat | 2,01 s · 47 | 2,13 s · 42 | 1,98 s · 44.2 | 3,11 s · 47 | 2,87 s · 47 | no empaquetat |
| Yosys, síntesi | no empaquetat | 7,91 s · 0.70+post | 24,15 s · 0.33 | 14,32 s · 0.52 | 16,08 s · 0.67+post | no empaquetat | no empaquetat |
| Python, log CAN | 2,18 s · 3.9.25 | 2,14 s · 3.9.25 | 2,27 s · 3.12.3 | 1,78 s · 3.13.5 | 2,13 s · 3.15.2 | 2,61 s · 3.13.16 | 2,29 s · 3.12.15 |
| Python, bucle numèric | 2,40 s · 3.9.25 | 2,34 s · 3.9.25 | 1,85 s · 3.12.3 | 1,89 s · 3.13.5 | 2,19 s · 3.15.2 | 2,72 s · 3.13.16 | 2,05 s · 3.12.15 |
| `xz -T1`, comprimir | 31,27 s · 5.2.5 | 27,24 s · 5.2.5 | 32,71 s · 5.4.5 | 32,50 s · 5.8.1 | 31,47 s · 5.8.3 | 27,45 s · ? | 27,28 s · 5.6.2 |
| `xz -T1`, descomprimir | 0,48 s · 5.2.5 | 0,47 s · 5.2.5 | 0,45 s · 5.4.5 | 0,34 s · 5.8.1 | 0,33 s · 5.8.3 | 0,33 s · ? | 0,33 s · 5.6.2 |
| `zstd -T1`, comprimir | 0,16 s · 1.5.5 | 0,16 s · 1.5.5 | 0,17 s · 1.5.5 | 0,18 s · 1.5.7 | 0,16 s · 1.5.7 | 0,17 s · 1.5.7 | 0,16 s · 1.5.5 |
| `zstd -T1`, descomprimir | 0,04 s · 1.5.5 | 0,04 s · 1.5.5 | 0,05 s · 1.5.5 | 0,05 s · 1.5.7 | 0,04 s · 1.5.7 | 0,04 s · 1.5.7 | 0,04 s · 1.5.5 |
| Instal·lar 4 paquets sense xarxa | 0,82 s · 4.14.0 | 0,80 s · 4.14.0 | 1,12 s · 2.8.4 | 0,96 s · 3.0.4 | 0,61 s · 5.4.6.0 | 0,71 s · ? | 0,70 s · 4.20.0 |

- AlmaLinux 9 i SilikOS porten els mateixos binaris de la base: on aquesta taula els separa (`xz`: 31,27 contra
  27,24 s amb el mateix xz 5.2.5; Verilator: 2,28 contra 2,07 s) és el soroll d'una sola execució en una màquina
  compartida, un 10-15 %. Cap diferència d'aquesta mida entre dues columnes vol dir res.
- El que SilikOS hi afegeix és el que la base no empaqueta: ngspice 47 i Yosys 0.70 (els nostres paquets). Yosys
  0.70 sintetitza en 7,91 s el que el 0.33 d'Ubuntu fa en 24,15 s i el 0.67 de Fedora en 16,08 s: és la versió i
  com està compilada, no el sistema.
- On la base va per darrere: el Python 3.9 en el bucle numèric (2,34-2,40 s contra 1,85 s del 3.12 d'Ubuntu).

**aarch64, els mateixos set**, la feina ARM de la mateixa execució (una màquina ARM de GitHub, 4 processadors):

| Càrrega | AlmaLinux 9 | SilikOS | Ubuntu 24.04 | Debian estable | Fedora | openSUSE Tumbleweed | AlmaLinux 10 |
|---|---|---|---|---|---|---|---|
| Build de firmware Cortex-M4 | 5,56 s · 12.4.0 | 5,52 s · 12.4.0 | 5,62 s · 13.2.1 | 5,92 s · 14.2.1 | 6,11 s · 15.2.0 | 5,64 s · 15.3.0 | 6,45 s · 14.1.0 |
| Compilació nativa | 5,46 s · 11.5.0 | 5,65 s · 11.5.0 | 5,04 s · 13.3.0 | 5,32 s · 14.2.0 | 5,88 s · 16.2.1 | 7,02 s · 16.2.1 | 6,08 s · 14.3.1 |
| Enllaçat natiu | 0,07 s · 2.35.2-72.el9 | 0,08 s · 2.35.2-72.el9 | 0,06 s · 2.42 | 0,06 s · 2.44 | 0,05 s · 2.47.20260726 | 0,06 s · 2.47.0.20260921-3 | 0,06 s · 2.41-63.el10.alma.1 |
| El programa compilat, executant-se | 3,97 s · 11.5.0 | 3,96 s · 11.5.0 | 3,69 s · 13.3.0 | 3,68 s · 14.2.0 | 3,72 s · 16.2.1 | 3,71 s · 16.2.1 | 3,71 s · 14.3.1 |
| Icarus Verilog | 6,10 s · 12.0 | 6,10 s · 12.0 | 5,95 s · 12.0 | 5,83 s · 12.0 | 5,12 s · 13.0 | 5,08 s · 13.0 | 6,04 s · 13.0 |
| Verilator, fer el model | 2,81 s · 5.022 / 11.5.0 | 2,78 s · 5.022 / 11.5.0 | 3,01 s · 5.020 / 13.3.0 | 3,17 s · 5.032 / 14.2.0 | 3,95 s · 5.046 / 16.2.1 | ha fallat | 3,68 s · 5.030 / 14.3.1 |
| Verilator, simular | 5,20 s · 5.022 | 5,18 s · 5.022 | 5,18 s · 5.020 | 4,91 s · 5.032 | 5,60 s · 5.046 | ha fallat | 5,08 s · 5.030 |
| ngspice, escala RC | no empaquetat | sense paquet ARM publicat | 2,74 s · 42 | 2,98 s · 44.2 | 2,78 s · 47 | 2,80 s · 47 | no empaquetat |
| ngspice, oscil·ladors MOS | no empaquetat | sense paquet ARM publicat | 3,21 s · 42 | 3,12 s · 44.2 | 3,73 s · 47 | 3,72 s · 47 | no empaquetat |
| Yosys, síntesi | no empaquetat | sense paquet ARM publicat | 32,22 s · 0.33 | 17,65 s · 0.52 | 18,07 s · 0.67+post | no empaquetat | no empaquetat |
| Python, log CAN | 3,10 s · 3.9.25 | 3,10 s · 3.9.25 | 2,94 s · 3.12.3 | 2,63 s · 3.13.5 | 2,97 s · 3.15.2 | 3,48 s · 3.13.16 | 3,03 s · 3.12.15 |
| Python, bucle numèric | 4,03 s · 3.9.25 | 4,03 s · 3.9.25 | 3,24 s · 3.12.3 | 3,17 s · 3.13.5 | 3,60 s · 3.15.2 | 3,56 s · 3.13.16 | 3,25 s · 3.12.15 |
| `xz -T1`, comprimir | 37,56 s · 5.2.5 | 35,26 s · 5.2.5 | 33,12 s · 5.4.5 | 31,90 s · 5.8.1 | 28,59 s · 5.8.3 | 27,63 s · ? | 34,38 s · 5.6.2 |
| `xz -T1`, descomprimir | 0,45 s · 5.2.5 | 0,45 s · 5.2.5 | 0,45 s · 5.4.5 | 0,43 s · 5.8.1 | 0,43 s · 5.8.3 | 0,42 s · ? | 0,43 s · 5.6.2 |
| `zstd -T1`, comprimir | 0,25 s · 1.5.5 | 0,24 s · 1.5.5 | 0,25 s · 1.5.5 | 0,27 s · 1.5.7 | 0,24 s · 1.5.7 | 0,24 s · 1.5.7 | 0,25 s · 1.5.5 |
| `zstd -T1`, descomprimir | 0,07 s · 1.5.5 | 0,07 s · 1.5.5 | 0,07 s · 1.5.5 | 0,08 s · 1.5.7 | 0,07 s · 1.5.7 | 0,07 s · 1.5.7 | 0,07 s · 1.5.5 |
| Instal·lar 4 paquets sense xarxa | 0,93 s · 4.14.0 | 0,96 s · 4.14.0 | 0,89 s · 2.8.4 | 0,93 s · 3.0.4 | 0,66 s · 5.4.6.0 | 0,66 s · ? | 1,03 s · 4.20.0 |

- A ARM, SilikOS no hi té ngspice ni Yosys: els nostres paquets d'aquestes eines es construeixen i es proven per a
  ARM (workflow EDA tools) però el release `eda-tools` encara només porta els d'x86_64.
- La resta de files de SilikOS són les de la base, com a x86_64: on se separen d'AlmaLinux 9 (`xz`: 37,56 contra
  35,26 s) és soroll.

Les dues màquines no es poden comparar entre elles amb aquestes taules (no se sap quin processador és cadascuna: el
log no ho diu), i una sola execució per màquina no dona el soroll. El que sí que es veu a totes dues: el Yosys 0.33
d'Ubuntu triga molt més que el 0.52 de Debian i el 0.67 de Fedora, el Python 3.9 de la base és el més lent en el
bucle numèric, i el Verilator d'openSUSE no funciona amb aquest mètode.

## Què no s'ha mesurat

- **ngspice i Yosys de SilikOS en ARM:** el release `eda-tools` no en porta els paquets ARM.
- **`xz` amb 500 MB:** trigava 7 minuts per passada; s'ha mesurat amb 64 MB.
- **Arrencada, memòria en repòs, latència de l'escriptori, GPU, disc real, bateria:** res. Demanen maquinari real
  amb cada sistema instal·lat, no contenidors.
- **Kernel:** el d'EL 9 (5.14) contra els 6.x dels altres no s'ha comparat; aquí tots corrien sobre el 6.18.
- **Eines comercials** (Spectre, Vivado, MATLAB): cap.
- **Maquinari real:** tot això és una màquina virtual compartida; d'aquí ve el soroll del 15 %.
