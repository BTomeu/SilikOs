# Tornar enrere una actualització: estudi i disseny (12/11/2026)

Estudi de viabilitat fet per un agent i revisat. Els paquets es van comprovar en un contenidor `almalinux:9` (9.8); cap
operació LVM, device-mapper ni arrencada s'ha pogut executar aquí (no hi ha device-mapper ni KVM). La part de disseny
és una **PROPOSTA**.

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

## 3. Disseny (PROPOSTA)

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
