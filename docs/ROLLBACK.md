# Tornar enrere una actualització: disseny, què hi ha fet i com es fa servir

Estudi de viabilitat del 12/11/2026 (fet per un agent i revisat); implementat el 13/11/2026 seguint-lo. Els paquets
i les eines es van comprovar en un contenidor `almalinux:9` (9.8). **Cap operació LVM, device-mapper ni arrencada
s'ha pogut executar** a la màquina on s'ha escrit (no hi ha device-mapper, KVM ni systemd): tot el que depèn d'un
disc real és "escrit, provat amb substituts, no executat" fins que corri el job `rollback-test` de la CI
(secció 5; `docs/STATUS.md` té què s'ha executat i què no). Els valors numèrics són **PROPOSTA**.

## Com es fa servir

"Què passa quan una actualització em trenca la màquina?" Una ordre:

```bash
silik rollback               # torna / a com era abans de la darrera actualització; pregunta abans; NO reinicia
systemctl reboot             # arrenca, un cop, l'entrada "Revert ..." (silik l'ha deixada triada)
                             # en aquesta arrencada `silik rollback finish` corre sol i deixa /boot a punt
```

Si el sistema ja no arrenca: al menú d'arrencada, l'entrada **"Snapshot silikos-update.N ..."** engega el sistema
tal com era; allà, `silik rollback` fa d'aquell estat el sistema, i es reinicia.

```bash
silik snapshot               # (= status) es pot tornar enrere? volum arrel, ús i creixement del pool, snapshots, /boot
silik snapshot list          # les snapshots, de la més nova a la més vella
silik snapshot create [NOM]  # una a mà (abans d'instal·lar una eina EDA, per exemple); sense nom: manual.N
silik snapshot delete NOM
silik snapshot setup         # en un sistema ja instal·lat sobre LVM thin: snapm, boom-boot, el perfil del pool, trim
silik rollback NOM           # a una snapshot concreta
silik rollback --packages    # sense snapshots (disc no thin): dnf history undo de la darrera actualització
silik update                 # fa la snapshot abans (--no-snapshot: no); després d'un rollback, acaba l'espera
silik doctor system          # fila "rollback": ok / warn / unknown i què cal fer
```

Totes imprimeixen cada ordre que executen (`$ sudo snapm ...`); `--dry-run` no executa res (ni demana contrasenya);
`--json` a `status` i `list`. **`/home` no es toca mai**; el que es perd en tornar enrere és el que s'ha escrit a `/`
des de la snapshot: paquets, `/etc`, `/var`, `/opt` (les instal·lacions EDA a `/opt/eda` també).

## Què hi ha fet (13/11/2026) i què continua sent PROPOSTA

| Peça | Estat | On |
|---|---|---|
| `silik snapshot list / create / delete / status / setup`, `silik rollback [NOM] / finish / --packages` | escrit; 100 tests amb substituts de les eines; **no executat sobre LVM** | `packages/silik-tools/files/silik`, `tests/test_rollback.py`, `tests/standins/tool.py` |
| Ganxo abans d'actualitzar (`/usr/libexec/silikos/pre-update-snapshot`), a les dues unitats d'actualització i a `silik update` | escrit; executat en un contenidor EL 9.8 amb el dnf real (res a actualitzar; alguna cosa a actualitzar; dnf sense xarxa) | `packages/silikos-security` |
| Les unitats no corren arrencant d'una snapshot (`ConditionKernelCommandLine=!snapm.snapset`) ni mentre s'espera després d'un rollback | escrit; `systemd-analyze verify` (systemd 252) no hi troba res | `silikos-update.service`, `silikos-security-update.service` |
| `silik rollback finish` sol, a l'arrencada "Revert" (`silikos-rollback-finish.service`, `ConditionKernelCommandLine=snapm.revert`) | escrit; no arrencat mai | `packages/silikos-security` |
| Perfil LVM `silikos-thin` (autoextensió al 70 %, en passos del 20 %) | escrit; `lvmconfig --validate` (lvm2 2.03.33) el dona per vàlid; **no aplicat mai a un pool** | `/etc/lvm/profile/silikos-thin.profile`; l'aplica el `%post` del kickstart o `silik snapshot setup`, mai un script de paquet |
| `snapm` i `boom-boot` al `%packages`; `Recommends` a `silikos-security` | es resolen a l'AppStream de 9.8 (27 paquets, 5,8 MB, en un contenidor net) | `kickstart/silikos.ks` |
| `[Storage] default_scheme = LVM_THINP` al `product.img` | escrit, en un commit a part (es pot revertir sol); el codi de configuració del mateix anaconda 34.25.7.14, executat en un contenidor amb aquest fitxer, llegeix `default_scheme` = LVM_THINP per al producte SilikOS (LVM per a AlmaLinux); **no instal·lat mai** | `installer/product/etc/anaconda/product.d/silikos.conf`, `tests/test_installer_thin.py` |
| Barra d'estat: `update no snapshot` / `update waiting since the rollback` (EN, CA, ES), al mateix camp que "restart to finish" | escrit; no vist en una sessió | `extension.js` |
| Fila `rollback` a `silik doctor system`; entrades `sys/snapshot`, `sys/snapshot-create`, `sys/rollback` a la barra COMMAND | escrit, amb tests | |
| Job `rollback-test` de la CI (passos 1-6, 8 i 10 del pla) | escrit; el YAML es llegeix; **no executat** (`continue-on-error`) | `.github/workflows/ci.yml`, `tests/install/rollback*.sh`, `rollback*.ks.in` |
| Volum propi per a `/opt/eda`; `silik rescue usb` (ReaR); passos 7, 9, 11 i 12 del pla; xifratge; un disc amb un altre sistema | **no fet**: continua sent PROPOSTA | |

**Valors PROPOSTA** (`/etc/silikos/snapshot.conf`, cap mesurat): es conserven 5 snapshots d'actualització i 14 dies;
cap snapshot nova amb el pool per sobre del 70 % de dades o el 50 % de metadades; `size_policy = 50%FREE`.

### En què s'aparta del disseny de la secció 3, i per què

- **Sense `snapm schedule`.** Un schedule de snapm porta un temporitzador propi i una sola política de poda (nombre
  *o* edat). Aquí la snapshot només es fa abans d'una actualització i la poda vol les dues regles: es crea amb
  `snapm snapset create --bootable --revert --autoindex silikos-update /` i es poda amb `snapm snapset delete`
  (només les `silikos-update.N`; una feta a mà no es poda mai; la més nova es conserva sempre).
- **`--size-policy` explícit (`50%FREE`).** Per defecte snapm demana al pool espai lliure per al doble del que
  ocupa `/` (`200%USED`, llegit a `snapm(8)` i a `_snapm.py`): un pool mig ple no el té mai i la snapshot fallaria.
  `100%FREE` tampoc serveix: snapm arrodoneix cap amunt a un sector i es refusa a si mateix (executat amb el
  `SizePolicy` de snapm 0.7.0: demana 35944689152 bytes quan n'hi ha 35944688675 de lliures). Una snapshot thin no
  ocupa res en crear-se; el que protegeix el pool són els dos llindars i l'autoextensió.
- **El perfil de boom el fa `silik`** abans de la primera snapshot (`boom profile create --from-host
  --uname-pattern el9`). snapm el crea sol només per als noms que boom coneix (Red Hat Enterprise Linux, CentOS
  Stream, Fedora); amb `NAME="SilikOS"` a `/etc/os-release` falla *després* d'haver fet el volum: `Could not
  determine uname pattern for 'SilikOS'` (executat amb el codi de snapm 0.7.0 i boom 1.6.8 a EL 9.8). El perfil es
  fa només en una arrencada normal: pren les opcions de la línia del kernel d'aquella arrencada.
- **Després d'un rollback les actualitzacions automàtiques esperen** (`/etc/silikos/update.hold`, que escriu
  `finish`): si no, l'endemà a les 6 es tornaria a instal·lar el que ha trencat la màquina. `silik update` (a mà,
  amb snapshot abans) acaba l'espera; la barra d'estat i `silik doctor` ho diuen. **Decisió del propietari**: la
  regla era "el sistema s'actualitza sol".
- **`finish` també torna a posar** l'entrada d'un kernel que la base de paquets revertida coneix i que
  l'actualització havia tret de `/boot` (`kernel-install add`), a més de treure les dels que no coneix
  (`kernel-install remove`, el que fa el `%preun` del paquet del kernel), fixar el kernel per defecte
  (`grubby --set-default`) i esborrar les entrades de la snapshot que ja no existeix (`boom entry delete`).
- **`silik rollback` des de la mateixa snapshot arrencada** està permès (és el cas "la màquina ja no arrenca"); el
  que es refusa arrencat d'una snapshot és fer-ne una altra i actualitzar.
- **Si no es pot saber si hi ha actualitzacions** (dnf sense xarxa), no es fa snapshot "per si de cas"; es deixa
  la nota i `pre-update-snapshot settle`, després, la treu si al final cap paquet ha canviat.
- **El que ocupa cada snapshot** no es mostra: `lvs` no dona l'espai exclusiu d'una snapshot thin (caldria
  `thin_ls`). `status` mostra l'ús del pool, quantes n'hi ha i què ocupen les còpies de kernel a `/boot`.

### Què s'ha llegit de les eines (i què s'ha hagut de suposar)

Llegit o executat a EL 9.8 (contenidor, 13/11/2026):
- **snapm 0.7.0**: opcions de `snapset create/delete/revert/list` (`command.py`, `snapm(8)`); el JSON de
  `snapset list --json -o ...`, generat pel seu propi codi d'informes amb conjunts inventats; noms vàlids (sense
  `_`); `snapm.snapset=UUID` i `snapm.revert=UUID` a la línia del kernel; el revert esborra l'entrada "Snapshot" i
  deixa la "Revert"; sense device-mapper acaba amb `ERROR - Command failed: ...` i codi 1; l'entrada "Snapshot"
  munta la resta d'`/etc/fstab` (`/boot`, `/home`) amb `systemd.mount-extra` (`build_snapset_mount_list`); el seu
  `SizePolicy` i la creació del perfil de boom s'han executat (a dalt).
- **boom 1.6.8**: ha escrit ell mateix les entrades (`MACHINEID-BOOTID7-VERSIÓ.conf`, sense clau `id`), la còpia
  de kernel i initramfs (`/boot/boom/cache/SHA1.img` i `vmlinuz-VERSIÓ.boom0`: dues còpies per imatge, cap si ja
  la té), i `boom entry delete --boot-id ID` (les opcions van després de `entry delete`).
- **lvm2 2.03.33**: `lvs --reportformat json --units b --nosuffix -o ...,lv_profile`, `lvchange --metadataprofile`,
  `--monitor y`; el perfil és vàlid i una opció no permesa en un perfil el fa refusar.
- **dnf 4.14**: `check-update` surt amb 100 / 0 / 1; `--security` hi funciona; la transacció de `dnf-automatic`
  surt a `dnf history list` amb la línia d'ordres buida i "Upgrade"; `dnf history undo` real (fet).
- **grubby 8.40, grub2 2.06, kernel-install de systemd 252, 20-grub.install, 50-dracut.install**: llegits (què
  escriuen i què esborren; instal·lar qualsevol kernel el posa per defecte) i **executats**: `silik rollback
  finish` en un contenidor amb un `/boot` fet a mà (un kernel que la base de paquets no coneix, sense mòduls, i
  per defecte): `kernel-install remove` en treu l'entrada i els fitxers, `grubby --set-default` deixa per defecte
  el kernel conegut; `grub2-reboot ID` escriu `next_entry=ID` a `grubenv`.
- **anaconda 34.25.7.14**: `default_scheme = LVM_THINP` a `[Storage]` (a `anaconda.conf`, `rhvh.conf`,
  `ovirt.conf`); `autopart` sense `--type` pren aquest valor (`automatic_module.py`); el seu codi de configuració,
  executat amb el nostre fitxer de producte, dona LVM_THINP per a SilikOS.

Suposat, no vist enlloc on es pogués executar — **[A]**:
- [A] Un volum thin es reconeix a sysfs com un dispositiu amb uuid `LVM-` que té per sota el `-tpool` del pool
  (`/sys/dev/block/M:m/slaves/*/dm/name`). És el que fa servir `silik` per no demanar root; si no és així, dirà
  "no disponible" en un disc que sí que ho és.
- [A] grub2 entén com a identificador d'una entrada el nom del fitxer sense `.conf`: és el que `grubby` desa a
  `saved_entry` (vist) i el que `silik` dona a `grub2-reboot`; que grub2 l'arrenqui només es veu arrencant. Si no,
  la propera arrencada no serà "Revert" i `silik` ja diu quina triar a mà.
- [A] Les files de `lvs --reportformat json` (valors com a text, `lv_profile` buit si no n'hi ha): només se n'ha
  vist el marc, sense cap volum.
- [A] Al `%post` del kickstart (chroot de l'instal·lador), `findmnt /` i `lvs` veuen el volum arrel. Si no, el
  perfil no s'aplica: `silik snapshot status` ho avisa i `silik snapshot setup` ho arregla.
- [A] El merge d'una snapshot thin de `/` acaba en activar el volum a l'arrencada "Revert", abans que corri
  `finish`. Si encara no ha acabat, `finish` deixa les entrades i cal tornar-lo a executar (el test ho detecta).
- [A] `snapm snapset revert` demanat des de la mateixa snapshot arrencada (muntada com a `/`): el merge queda
  per a la propera activació del volum (és el que diu la documentació de LVM per a un origen o una snapshot en ús).
- [A] SELinux deixa fer la snapshot i el `finish` des d'un servei de systemd (corren sense confinar, com
  `dnf-automatic`); cap política pròpia.
- [A] La reserva que deixa l'instal·lador al grup de volums (el test n'informa el percentatge i només exigeix ≥ 5 %).
- [A] En un runner de GitHub, la instal·lació en un disc de 80 GB (dispers) crea `/home`.

### Què queda en desinstal·lar

`rpm -e silikos-security` treu tots els fitxers nous (comprovat en un contenidor). Queden, perquè no són fitxers
del paquet: les snapshots que hi hagi (volums LVM i les seves entrades d'arrencada: `snapm snapset list`,
`snapm snapset delete`) i el nom del perfil al pool (`lvchange --detachprofile VG/POOL`).

## Recomanació

**LVM thin per defecte + `snapm` + `boom-boot`.** Totes dues eines són a l'AppStream d'AlmaLinux 9.8 i no cal tocar
la base. Abans de cada actualització automàtica es fa una snapshot thin de `/` amb entrada d'arrencada, i
`silik rollback` la reverteix.

Si el disc no és LVM thin: `dnf history undo` (amb límits clars) i, opcionalment, un USB de rescat amb ReaR.

**Descartat:**
- Snapper: no existeix a EL 9 ni a EPEL 9.
- Btrfs: el kernel d'EL 9 no en porta el mòdul.
- Stratis: és Technology Preview i l'instal·lador no el sap posar a `/`.
- El rol `snapshot` de rhel-system-roles: demana Ansible.

## 1. Què ofereix EL 9.8 (comprovat al contenidor)

| Paquet | Versió | Nota |
|---|---|---|
| `snapm`, `python3-snapm` | 0.7.0-2.el9 (appstream) | Conjunts de snapshots: plugins lvm2-thin, lvm2-cow i stratis. Ordres `create --bootable --revert`, `revert`, `schedule` (amb GC per nombre o edat), `mount` i `diff` |
| `boom-boot` | 1.6.8-1.el9 (appstream) | Entrades d'arrencada (BLS) per a les snapshots |
| `lvm2` | 2.03.33-4.el9_8.1 | Per defecte: sense autoextensió del pool, discards en passdown |
| `rear` | 2.6-28.el9 | Imatge de rescat |
| `snapper`, `leapp` | — | No hi són (BaseOS, AppStream, CRB, extras, EPEL) |
| `btrfs-progs` | només a EPEL | El kernel no porta `btrfs.ko` |

- **L'entrada d'arrencada copia el kernel que corre** (vmlinuz + initramfs) a `/boot`. Així sobreviu quan dnf esborra
  el kernel, però costa espai a `/boot` (1 GiB).
- **El revert és un `lvconvert --merge`**, que s'acaba en arrencar l'entrada "Revert". En acabar, la snapshot desapareix.
- **L'entrada porta `snapm.snapset=` o `snapm.revert=` a la línia del kernel.** Això permet no actualitzar mai quan
  s'arrenca d'una snapshot.
- **`fstrim.timer` no està activat per defecte.** Sense discard, el pool no allibera els blocs esborrats.
- **`dnf history undo` funciona** (provat: baixar i tornar a pujar glibc i tzdata, scriptlets inclosos). Però falla si
  les versions velles ja no són al repositori, per exemple després d'un canvi de minor, quan passen a vault.

## 2. Instal·lador: LVM thin sense que el kickstart triï el disc

- **`autopart --type=thinp` al kickstart no.** En una instal·lació automàtica, l'instal·lador marca **tots** els discos
  (`select_default_disks()`, anaconda 34.25). Això trencaria la regla.
- **El lloc correcte és el `product.img`.** A `installer/product/etc/anaconda/product.d/silikos.conf`:
  ```
  [Storage]
  default_scheme = LVM_THINP
  ```
  És el que fan RHV Node i oVirt. L'usuari continua triant el disc; "Automatic" llavors fa LVM thin.
- **Què crea:**
  - un pool thin amb `/` (màx. 70 GiB) i `/home`;
  - swap normal;
  - un 20 % del grup lliure (mín. 1 GiB, màx. 100 GiB) per fer créixer el pool.
- **Si l'usuari tria un esquema a mà** (LVM normal o XFS pla): mètode alternatiu.
- **[A] Cal mirar a la VM** si, amb `inst.ks=`, la pantalla de destinació surt amb tots els discos marcats. Afecta la
  regla "el kickstart mai tria disc" encara que no fem servir thin.

## 3. Disseny (el del 12/11/2026; el que s'ha fet i on se n'aparta és a dalt)

**Paquets:** `snapm` i `boom-boot` al `%packages`. Són paquets de la base i no en canvien res.

**Abans de cada actualització** (`ExecStartPre=/usr/libexec/silikos/pre-update-snapshot`, i també a `silik update`):
1. `dnf check-update`: si no hi ha res a actualitzar, no fa res.
2. Si n'hi ha, fa la snapshot (`snapm snapset create-scheduled -c silikos-update`), arrencable i reversible, de `/`.
3. Després poda (`snapm schedule gc`), conservant les 5 darreres i 14 dies (PROPOSTA).
4. Si la snapshot falla, l'actualització es fa igualment, perquè la seguretat va primer. La barra d'estat diu
   "update: no snapshot" (decisió del propietari).

**Barreres:**
- Cap snapshot amb el pool per sobre del 70 % de dades o el 50 % de metadades: primer poda, després avisa.
- Un perfil LVM propi (`/etc/lvm/profile/silikos-thin.profile`) aplicat al pool: autoextensió al 70 %, en passos del
  20 %, tirant de la reserva. No toca `/etc/lvm/lvm.conf`.
- `fstrim.timer` activat.
- Si s'arrenca d'una snapshot, els serveis d'actualització no corren
  (`ConditionKernelCommandLine=!snapm.snapset`).

**Ordres:**
- `silik snapshot list | create | delete | status`. L'estat mostra l'ús del pool, el que ocupa cada snapshot i l'ús de
  `/boot`.
- `silik rollback [NOM]`: reverteix i posa l'entrada "Revert" com a propera arrencada (`grub2-reboot`). **No
  reinicia**: només ho diu.
- `silik rollback finish`: corre sol a la primera arrencada després del revert.
  - Esborra les entrades d'arrencada dels kernels que la base de paquets revertida ja no coneix.
  - Torna a fixar el kernel per defecte.
  - **Sense aquest pas, l'entrada per defecte apuntaria a un kernel sense mòduls i no arrencaria.**

**Què no es toca o no es reverteix:**
- **`/home`:** és un volum a part i no es toca mai. Però comparteix el pool: si el pool s'omple, `/home` també pateix.
- **`/opt/eda` i `/var`:** són a `/`. Un rollback desfà les instal·lacions EDA i els contenidors de root, i una
  instal·lació EDA gran infla les snapshots. PROPOSTA: un volum propi per a `/opt/eda` (cal veure si el
  particionament per defecte ho permet).
- **`/boot/efi`:** no es reverteix. Si grub2 o shim s'han actualitzat, queden nous. És inofensiu, però cal
  documentar-ho.

**Mètode alternatiu** (disc no thin):
- `silik rollback --packages` = `dnf history undo` de la darrera actualització automàtica. Límits:
  - no hi ha versions velles després d'un canvi de minor;
  - no desfà la configuració ni els efectes dels scriptlets;
  - el kernel només es treu, no es torna a posar l'antic;
  - baixar glibc o systemd demana reiniciar.
- `silik rescue usb`: ReaR en un USB que formata l'usuari. `rear recover` torna a crear el disc i l'esborra: només en
  recuperació i amb confirmació.

## 4. Esforç i risc

**Esforç: unes 2 setmanes** [A].

| Peça | Dies |
|---|---|
| `product.img`, `%packages`, perfil LVM, fstrim, condicions | 0,5 |
| `silik snapshot` / `rollback` / `finish`, ganxo d'actualització, barra d'estat, textos EN/CA/ES, tests | 4–5 |
| ReaR i `dnf history undo` | 1–2 |
| Proves en VM | 3–4 |

**Riscos:**
- snapm és encara 0.x i ha tingut errors recents (RHEL-127542: un reanomenament deixava entrades òrfenes).
- `/boot` i `/` poden quedar desquadrats.
- **Pool ple:** XFS s'atura i `/home` també hi cau.
- `/boot` d'1 GiB, amb les còpies de kernels.
- UUID d'XFS duplicat si es munten l'origen i la snapshot alhora.

## 5. Pla de proves en VM real (Ryzen amb KVM, o un runner de CI amb KVM)

**El job `rollback-test`** (`.github/workflows/ci.yml`, `tests/install/rollback.sh`) fa els passos 1-6, 8 i 10 en
màquines virtuals amb la ISO, i cada pas és una anotació de l'execució (`::notice` si passa, `::error` amb la
primera comprovació que falla):
- Instal·la amb el kickstart de la ISO i un `autopart` **sense esquema** (el que surt és el valor per defecte del
  `product.img`), en un disc de 80 GB, i arrenca el sistema quatre vegades (`rollback-check.sh`, una etapa cada
  cop; l'etapa es guarda a `/boot`, que no és dins de la snapshot):
  1. arrencada normal: disposició thin, `silik snapshot create`, poda (7 snapshots més, en queden 5), es baixen a
     propòsit `tzdata`, `expat`, `libxml2` i `sqlite-libs` i s'executa `silikos-update.service` (la snapshot ha de
     sortir al journal abans de l'actualització); s'instal·la un altre kernel *després* de la snapshot;
  2. arrencada de l'entrada "Snapshot": `/` és la snapshot, `/home` l'original, no s'actualitza res, `silik
     rollback` des d'allà;
  3. arrencada "Revert": versions velles, el merge acabat, `finish` ha corregut sol, el kernel instal·lat després
     ja no és a `/boot`, **el kernel per defecte té els seus mòduls**, les actualitzacions esperen;
  4. arrencada normal: el kernel per defecte corre amb mòduls, `silik update` acaba l'espera amb snapshot abans.
- Una segona instal·lació petita en particions normals: `silik snapshot` diu "not available", l'actualització es
  fa igualment i `silik rollback --packages` torna a les versions velles.
- No fa: xifratge, un disc amb un altre sistema, quins discos surten marcats amb `inst.ks` (pas 1), pool ple (7),
  mesures (9), ReaR (10), canvi de minor (11), tall de corrent (12).
- És `continue-on-error` fins que hagi passat: no pot aturar la ISO ni una release.

1. **Instal·lació:**
   - ISO amb `LVM_THINP`, disc triat a mà, Automatic; `lvs -a` ha de mostrar el pool, `/` i `/home` thin, swap normal i
     ~20 % lliure al grup.
   - Repetir amb xifratge, i en un disc amb un altre sistema.
   - Quins discos surten marcats amb `inst.ks`.
2. **Snapshot:** `silik snapshot create`, i mirar `lvs`, `boom list`, `snapm snapset list` i `df /boot`.
3. **Actualització:** baixar a propòsit kernel, glibc, systemd i gnome-shell, i executar `silikos-update.service`. La
   snapshot s'ha de fer abans (journal).
4. **Arrencar la snapshot:** `/` és la snapshot, `/home` és l'original, no s'actualitza res, i l'escriptori va bé.
5. **Rollback:**
   - `silik rollback`, i reiniciar a "Revert".
   - `rpm -q` amb les versions velles, el merge acabat i `finish` ha netejat les entrades.
   - El kernel per defecte té els seus mòduls.
6. **Rollback després d'arrencar un kernel nou:** arrenca l'antic, sense entrades òrfenes.
7. **Pool ple:**
   - Omplir `/` fins al llindar: l'autoextensió, la poda i l'avís han de funcionar.
   - Passar-se a propòsit: veure què fa XFS i com es recupera.
8. **Poda:** 10 conjunts amb un límit de 5. Les entrades i les còpies de `/boot` s'han d'esborrar.
9. **Cost a mesurar:**
   - el temps de crear una snapshot;
   - el % del pool per actualització diària durant una setmana, amb fstrim i sense;
   - fio 4k aleatori amb 0, 1 i 5 snapshots;
   - `systemd-analyze`.
10. **Disc no thin:**
    - `silik snapshot` diu "no disponible";
    - `dnf history undo`;
    - ReaR a un USB virtual i `recover` a un segon disc buit.
11. **Canvi de minor:** de 9.8 a 9.9, amb snapshot i rollback.
12. **Tallar la corrent a mig merge:** a la propera arrencada el merge ha de continuar.

Sources:
- https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/configuring_and_managing_logical_volumes/managing-system-upgrades-with-snapshots_configuring-and-managing-logical-volumes
- https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/9/html/managing_storage_devices/managing-system-upgrades-with-snapshots_managing-storage-devices
- https://issues.redhat.com/browse/RHEL-36667
- https://issues.redhat.com/browse/RHEL-127542
- https://github.com/snapshotmanager/snapm
- https://boom.readthedocs.io/en/latest/user_guide.html
- https://fedoraproject.org/wiki/Changes/StratisAnacondaSupport
- https://bugzilla.redhat.com/show_bug.cgi?id=2135427
- https://repo.almalinux.org/almalinux/9/
