#!/usr/bin/env python3
"""gen_site.py: the pages of site/ (GitHub Pages), one text in three languages.

    python3 tools/gen_site.py          writes site/index.html, site/ca/index.html, site/es/index.html, site/404.html

The site is static and asks nothing of another host: the pages, site/style.css (written by hand), the font and the
pictures are all there is; there is no build step on the server, the pages are committed as this writes them and
tests/test_site.py holds them to it. A page is the Silik interface: a title bar that is a command line, a text rail of
numbered keys (the views), a status bar of "key value" fields.

Rules of the text: every statement is one of docs/STATUS.md's rows; what was not run is said. The command output in
OUT is what the commands printed (the container and the date are in RUN): replace it only with what a new run prints.
The mark's files come from tools/gen_marks.py.
"""
import html
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "https://github.com/BTomeu/SilikOs"
BLOB = REPO + "/blob/main/"
LANGS = ("en", "ca", "es")
DATE = "13/11/2026"

# the views: id (the rail's key, the address in the command line), then its name
VIEWS = (
    ("what", ("What it is", "Què és", "Qué es")),
    ("looks", ("Looks", "Aspectes", "Aspectos")),
    ("commands", ("Commands", "Ordres", "Órdenes")),
    ("state", ("State", "Estat", "Estado")),
    ("get", ("Get it", "Com tenir-lo", "Cómo tenerlo")),
)

# what the commands printed: an AlmaLinux 9.8 container (almalinux:9, x86_64) with silik-tools 0.6.14, silik-dev 0.5.0,
# silik-eda-open 0.3.0 and silik-win 0.4.2 built from this repository (tools/build_rpms.sh) and the ngspice 47 of the
# release eda-tools installed with dnf, no weak dependencies; each command run as an ordinary user, 13/11/2026
OUT = {
    "silik eda try sim": """$ cp -r /usr/share/silikos/eda/try/. /home/eng/.cache/silikos/eda-try-8mf25udb
$ cd /home/eng/.cache/silikos/eda-try-8mf25udb
$ ngspice -b inverter.cir > inverter.out
● sim        an inverter's output is high for a low input and low for a high one
1 ok, 0 failed, 0 not run; the files: /home/eng/.cache/silikos/eda-try-8mf25udb
""",
    "silik --dry-run look bar --accent cobalt": """$ gsettings set com.silikvolt.silikos.shell look bar
$ gsettings set com.silikvolt.silikos.shell accent cobalt
$ gsettings set org.gnome.desktop.interface gtk-theme SilikOS-cobalt
$ gsettings set org.gnome.shell.extensions.user-theme name SilikOS-cobalt
$ gsettings set org.gnome.desktop.interface icon-theme SilikOS-Colour
""",
    "silik --dry-run dev can up can0 500k": """$ sudo ip link set can0 down
$ sudo ip link set can0 type can bitrate 500000 restart-ms 100
$ sudo ip link set can0 up
can0 up at 500000 bit/s: `candump can0` shows its frames, `cansend can0 123#DEADBEEF` sends one
""",
    "silik doctor eda windows": """eda
◆ warn     EDA boxes          podman is not installed: no EL6 / EL7 / EL8 boxes
                              fix: sudo dnf -y install podman
◆ warn     open tools         1 of 13; missing: devsim gtkwave iverilog kicad klayout magic netgen nvc qucs-s verilator xschem yosys
                              fix: sudo dnf -y install devsim gtkwave iverilog kicad klayout magic netgen nvc qucs-s verilator xschem yosys
◆ warn     ngspice threads    2, its default, on 4 cores: transistor models evaluated on 2
                              fix: silik eda tune   # silik eda bench measures first

windows
◆ warn     Wine               not installed: Windows programs do not run
                              fix: sudo dnf -y install silik-wine silik-wine-mono silik-wine-gecko
● ok       Wine prefixes      none yet (an installer opened with silik win open SETUP.exe makes "default")
● ok       sandbox            bubblewrap, user namespaces on
? unknown  Windows VM         no /dev/kvm (inside a container)

2 ok, 4 warn, 0 bad, 1 unknown (0.01 s)
""",
}

UI = {
    "title": ("SilikOS: an engineering workstation system", "SilikOS: un sistema per a l'estació de treball d'enginyeria",
              "SilikOS: un sistema para la estación de trabajo de ingeniería"),
    "description": (
        "SilikOS is an engineering workstation system on an Enterprise Linux 9 base: chip and board design, "
        "microcontrollers, the bench and Windows programs on one desktop. A prototype verified in virtual machines.",
        "SilikOS és un sistema per a l'estació de treball d'enginyeria sobre una base Enterprise Linux 9: disseny de xips i de "
        "plaques, microcontroladors, el banc i programes de Windows en un sol escriptori. Un prototip verificat en "
        "màquines virtuals.",
        "SilikOS es un sistema para la estación de trabajo de ingeniería sobre una base Enterprise Linux 9: diseño de chips y "
        "de placas, microcontroladores, el banco y programas de Windows en un solo escritorio. Un prototipo verificado "
        "en máquinas virtuales."),
    "mark": ("The SilikVolt mark", "La marca SilikVolt", "La marca SilikVolt"),
    "sections": ("Views", "Vistes", "Vistas"),
    "language": ("Language", "Llengua", "Idioma"),
    "keys": ("keys 1 to 5", "tecles 1 a 5", "teclas 1 a 5"),
    "repository": ("repository", "repositori", "repositorio"),
    "ready": ("ready", "a punt", "listo"),
    "k_base": ("base", "base", "base"),
    "k_state": ("state", "estat", "estado"),
    "v_state": ("prototype, verified in VM", "prototip, verificat en MV", "prototipo, verificado en MV"),
    "k_licence": ("licence", "llicència", "licencia"),
    "v_licence": ("not chosen", "no triada", "no elegida"),
    "k_date": ("page of", "pàgina del", "página del"),
    "next": ("next", "següent", "siguiente"),
    "ran": ("typed", "escrit", "escrito"),
}

# ---- the text. `code`, [words](address); an address without a scheme is a file of the repository.
RIG = ("The desktop test rig, %s: GNOME Shell 40 in an AlmaLinux 9.8 container, drawn without a graphics card; the session "
       "is in Catalan." % DATE,
       "El banc de proves de l'escriptori, %s: GNOME Shell 40 en un contenidor AlmaLinux 9.8, dibuixat sense targeta "
       "gràfica; la sessió és en català." % DATE,
       "El banco de pruebas del escritorio, %s: GNOME Shell 40 en un contenedor AlmaLinux 9.8, dibujado sin tarjeta "
       "gráfica; la sesión está en catalán." % DATE)

WHAT = (
    ("lead", (
        "An engineering workstation system for electronics: chip and board design, microcontrollers, the bench and "
        "Windows programs on one desktop, with one command behind every action.",
        "Un sistema per a l'estació de treball d'enginyeria electrònica: disseny de xips i de plaques, microcontroladors, el "
        "banc i programes de Windows en un sol escriptori, amb una sola ordre darrere de cada acció.",
        "Un sistema para la estación de trabajo de ingeniería electrónica: diseño de chips y de placas, "
        "microcontroladores, el banco y programas de Windows en un solo escritorio, con una sola orden detrás de cada "
        "acción.")),
    ("p", (
        "Underneath it is Enterprise Linux 9: AlmaLinux's packages and kernel, unchanged, so that a program written "
        "for Red Hat Enterprise Linux 9 finds the system it expects. SilikOS is packages on top: they install and "
        "uninstall like any other. It is a prototype: [State](#state) says what has been run and what has not.",
        "A sota hi ha Enterprise Linux 9: els paquets i el nucli d'AlmaLinux, sense tocar, perquè un programa fet per a "
        "Red Hat Enterprise Linux 9 hi trobi el sistema que espera. SilikOS són paquets a sobre: s'instal·len i es "
        "desinstal·len com qualsevol altre. És un prototip: [Estat](#state) diu què s'ha executat i què no.",
        "Debajo hay Enterprise Linux 9: los paquetes y el núcleo de AlmaLinux, sin tocar, para que un programa hecho "
        "para Red Hat Enterprise Linux 9 encuentre el sistema que espera. SilikOS son paquetes encima: se instalan y "
        "se desinstalan como cualquier otro. Es un prototipo: [Estado](#state) dice qué se ha ejecutado y qué no.")),
    ("fig", "command.png", 1600, 545, (
        "The COMMAND bar with the address look/ typed: the list of look addresses (look/bar, look/cobalt, look/glass, "
        "look/island and others) with what each one does, and at its foot the line that Enter will run: $ silik look bar.",
        "El COMMAND bar amb l'adreça look/ escrita: la llista d'adreces d'aspecte (look/bar, look/cobalt, look/glass, "
        "look/island i d'altres) amb el que fa cadascuna i, al peu, la línia que executarà Enter: $ silik look bar.",
        "El COMMAND bar con la dirección look/ escrita: la lista de direcciones de aspecto (look/bar, look/cobalt, "
        "look/glass, look/island y otras) con lo que hace cada una y, al pie, la línea que ejecutará Enter: "
        "$ silik look bar."), (
        "The COMMAND bar (Super+Space): an address, what it does, and the line it will run. The picture is cut to the "
        "pane (in a narrow window, to its left part). " + RIG[0],
        "El COMMAND bar (Super+Espai): una adreça, què fa i la línia que executarà. La imatge està retallada al "
        "plafó (en una finestra estreta, a la seva part esquerra). " + RIG[1],
        "El COMMAND bar (Super+Espacio): una dirección, qué hace y la línea que ejecutará. La imagen está recortada "
        "al panel (en una ventana estrecha, a su parte izquierda). " + RIG[2])),
    ("h2", ("parts", "parts", "partes")),
    ("table", None, (
        (("base", "base", "base"), (
            "AlmaLinux 9.8: its packages and its kernel from its own repositories, unchanged. SilikOS carries the "
            "base's version number.",
            "AlmaLinux 9.8: els seus paquets i el seu nucli, dels seus repositoris, sense tocar. SilikOS porta el "
            "número de versió de la base.",
            "AlmaLinux 9.8: sus paquetes y su núcleo, de sus repositorios, sin tocar. SilikOS lleva el número de "
            "versión de la base.")),
        (("desktop", "escriptori", "escritorio"), (
            "GNOME Shell 40 on X11 with the Silik shell: three looks of the same shell, one ink on paper, an accent "
            "for who wants one, Cascadia Mono, English, Catalan and Spanish.",
            "GNOME Shell 40 sobre X11 amb la shell Silik: tres aspectes de la mateixa shell, una tinta sobre paper, un "
            "accent per a qui en vulgui, Cascadia Mono, anglès, català i castellà.",
            "GNOME Shell 40 sobre X11 con la shell Silik: tres aspectos de la misma shell, una tinta sobre papel, un "
            "acento para quien lo quiera, Cascadia Mono, inglés, catalán y castellano.")),
        (("`silik`", "`silik`", "`silik`"), (
            "One command behind every action of the desktop. It prints each command it runs; `--dry-run` prints "
            "them and runs nothing.",
            "Una sola ordre darrere de cada acció de l'escriptori. Ensenya cada ordre que executa; `--dry-run` les "
            "ensenya i no executa res.",
            "Una sola orden detrás de cada acción del escritorio. Muestra cada orden que ejecuta; `--dry-run` las "
            "muestra y no ejecuta nada.")),
        (("chips", "xips", "chips"), (
            "The open EDA tools, built for EL 9 from their authors' sources: Xschem, ngspice, Qucs-S, Magic, KLayout, "
            "Netgen, Yosys, NVC, DEVSIM; Icarus Verilog, Verilator and GTKWave from EPEL. Boxes with an EL6, EL7 or "
            "EL8 userland for older releases of the vendors' tools.",
            "Les eines EDA obertes, compilades per a EL 9 des de les fonts dels seus autors: Xschem, ngspice, Qucs-S, "
            "Magic, KLayout, Netgen, Yosys, NVC, DEVSIM; Icarus Verilog, Verilator i GTKWave d'EPEL. Capses amb un "
            "sistema EL6, EL7 o EL8 per a versions antigues de les eines dels fabricants.",
            "Las herramientas EDA abiertas, compiladas para EL 9 desde las fuentes de sus autores: Xschem, ngspice, "
            "Qucs-S, Magic, KLayout, Netgen, Yosys, NVC, DEVSIM; Icarus Verilog, Verilator y GTKWave de EPEL. Cajas "
            "con un sistema EL6, EL7 o EL8 para versiones antiguas de las herramientas de los fabricantes.")),
        (("embedded", "microcontroladors", "microcontroladores"), (
            "The GNU ARM compiler with its C library, the base's debugger, OpenOCD, dfu-util, ST-LINK's tools, "
            "stm32flash, SDCC. A vendor's IDE (STM32CubeIDE, Code Composer Studio) is installed from your own download.",
            "El compilador GNU per a ARM amb la seva biblioteca de C, el depurador de la base, OpenOCD, dfu-util, les "
            "eines d'ST-LINK, stm32flash, SDCC. L'IDE d'un fabricant (STM32CubeIDE, Code Composer Studio) s'instal·la "
            "des de la teva descàrrega.",
            "El compilador GNU para ARM con su biblioteca de C, el depurador de la base, OpenOCD, dfu-util, las "
            "herramientas de ST-LINK, stm32flash, SDCC. El IDE de un fabricante (STM32CubeIDE, Code Composer Studio) "
            "se instala desde tu descarga.")),
        (("bench", "banc", "banco"), (
            "CAN through SocketCAN, SavvyCAN, cantools and python-can, serial and RS-485 terminals, sigrok and "
            "PulseView for logic analysers.",
            "CAN amb SocketCAN, SavvyCAN, cantools i python-can, terminals sèrie i RS-485, sigrok i PulseView per a "
            "analitzadors lògics.",
            "CAN con SocketCAN, SavvyCAN, cantools y python-can, terminales serie y RS-485, sigrok y PulseView para "
            "analizadores lógicos.")),
        (("Windows", "Windows", "Windows"), (
            "A double-click on an `.exe` runs it with Wine (our build of Wine 11.0 for EL 9) in a sandbox that does "
            "not see the rest of the home folder. The Windows virtual machine for what Wine cannot run is written; it has "
            "not been run.",
            "Un doble clic en un `.exe` l'executa amb Wine (el nostre Wine 11.0 compilat per a EL 9) dins d'una capsa "
            "que no veu la resta de la carpeta personal. La màquina virtual de Windows per al que Wine no pot executar "
            "està escrita; no s'ha executat.",
            "Un doble clic en un `.exe` lo ejecuta con Wine (nuestro Wine 11.0 compilado para EL 9) dentro de una "
            "caja que no ve el resto de la carpeta personal. La máquina virtual de Windows para lo que Wine no puede "
            "ejecutar está escrita; no se ha ejecutado.")),
        (("security", "seguretat", "seguridad"), (
            "SELinux enforcing (the base's), a firewall zone that drops incoming connections, sshd off, updates "
            "installed daily; the system never restarts by itself. `silik secure status` audits it.",
            "SELinux en mode enforcing (el de la base), una zona del tallafoc que descarta les connexions entrants, "
            "sshd apagat, actualitzacions instal·lades cada dia; el sistema no reinicia mai pel seu compte. "
            "`silik secure status` ho revisa.",
            "SELinux en modo enforcing (el de la base), una zona del cortafuegos que descarta las conexiones "
            "entrantes, sshd apagado, actualizaciones instaladas cada día; el sistema nunca reinicia por su cuenta. "
            "`silik secure status` lo revisa.")),
        (("SilikStudio", "SilikStudio", "SilikStudio"), (
            "The SilikVolt engineering suite as a native application: a window of its own, the first key of the rail.",
            "La suite d'enginyeria de SilikVolt com a aplicació nativa: una finestra pròpia, la primera tecla del rail.",
            "La suite de ingeniería de SilikVolt como aplicación nativa: una ventana propia, la primera tecla del "
            "rail.")),
    )),
    ("fig", "silikstudio.png", 1440, 900, (
        "SilikStudio in a SilikOS session in the Silik look: the result of an autocross lap simulation, with speed, "
        "power and state-of-charge traces, a table of energy losses and the sector times.",
        "SilikStudio en una sessió de SilikOS amb l'aspecte Silik: el resultat d'una simulació d'una volta "
        "d'autocròs, amb les corbes de velocitat, potència i estat de càrrega, una taula de pèrdues d'energia i els "
        "temps per sector.",
        "SilikStudio en una sesión de SilikOS con el aspecto Silik: el resultado de una simulación de una vuelta de "
        "autocross, con las curvas de velocidad, potencia y estado de carga, una tabla de pérdidas de energía y los "
        "tiempos por sector."), (
        "SilikStudio in SilikOS, in a container session on 10/11/2026.",
        "SilikStudio a SilikOS, en una sessió dins d'un contenidor, el 10/11/2026.",
        "SilikStudio en SilikOS, en una sesión dentro de un contenedor, el 10/11/2026.")),
    ("h2", ("made for", "fet per a", "hecho para")),
    ("ul", (
        ("electronics and chip-design engineers who need an EL 9 workstation for the EDA tools and a desktop for "
         "everything else;",
         "enginyers d'electrònica i de disseny de xips que necessiten una estació EL 9 per a les eines EDA i un "
         "escriptori per a la resta;",
         "ingenieros de electrónica y de diseño de chips que necesitan una estación EL 9 para las herramientas EDA y "
         "un escritorio para lo demás;"),
        ("university labs: the open flow (schematic, simulation, layout, LVS, synthesis) installed, and tried by one "
         "command;",
         "laboratoris d'universitat: el flux obert (esquema, simulació, layout, LVS, síntesi) instal·lat, i provat "
         "amb una ordre;",
         "laboratorios de universidad: el flujo abierto (esquema, simulación, layout, LVS, síntesis) instalado, y "
         "probado con una orden;"),
        ("Formula Student and other embedded teams: compiler, debugger, flashing, CAN and serial on one system, "
         "beside SilikStudio.",
         "equips de Formula Student i altres equips de sistemes encastats: compilador, depurador, programació, CAN i "
         "sèrie en un sol sistema, al costat de SilikStudio.",
         "equipos de Formula Student y otros equipos de sistemas embebidos: compilador, depurador, programación, CAN "
         "y serie en un solo sistema, junto a SilikStudio."),
    )),
)

LOOKS = (
    ("p", (
        "One shell, three looks: `silik look island`, `silik look bar`, `silik look silik`. One ink on paper by "
        "default; `silik look --accent` gives one colour (steel, cobalt, silicon indigo, volt violet or spark yellow) "
        "to what is selected, focused or running. The floating pieces are glass over the blurred wallpaper; "
        "`silik look --glass off` makes them solid paper.",
        "Una shell, tres aspectes: `silik look island`, `silik look bar`, `silik look silik`. Per defecte, una tinta "
        "sobre paper; `silik look --accent` dona un color (acer, cobalt, indi silici, violeta volt o groc llamp) al "
        "que és triat, enfocat o en marxa. Les peces flotants són de vidre sobre el fons de pantalla desenfocat; "
        "`silik look --glass off` les fa de paper opac.",
        "Una shell, tres aspectos: `silik look island`, `silik look bar`, `silik look silik`. Por defecto, una tinta "
        "sobre papel; `silik look --accent` da un color (acero, cobalto, índigo silicio, violeta volt o amarillo "
        "chispa) a lo que está elegido, enfocado o en marcha. Las piezas flotantes son de vidrio sobre el fondo de "
        "pantalla desenfocado; `silik look --glass off` las hace de papel opaco.")),
    ("fig", "look-island.png", 1600, 1000, (
        "The SilikOS desktop in the island look: a file manager and a terminal open, and one floating piece at the "
        "bottom with the Start key, the applications and the clock.",
        "L'escriptori de SilikOS amb l'aspecte illa: un gestor de fitxers i un terminal oberts, i una peça flotant a "
        "baix amb la tecla d'Inici, les aplicacions i el rellotge.",
        "El escritorio de SilikOS con el aspecto isla: un gestor de archivos y un terminal abiertos, y una pieza "
        "flotante abajo con la tecla de Inicio, las aplicaciones y el reloj."), (
        "<b>island</b>, the default: one floating piece at the bottom.",
        "<b>illa</b>, el de per defecte: una peça flotant a baix.",
        "<b>isla</b>, el de por defecto: una pieza flotante abajo.")),
    ("fig", "look-bar.png", 1600, 1000, (
        "The same desktop in the bar look: one bar along the bottom with the Start key, a command field, the "
        "applications, the workspaces and the clock.",
        "El mateix escriptori amb l'aspecte barra: una barra a baix amb la tecla d'Inici, un camp d'ordres, les "
        "aplicacions, els espais de treball i el rellotge.",
        "El mismo escritorio con el aspecto barra: una barra abajo con la tecla de Inicio, un campo de órdenes, las "
        "aplicaciones, los espacios de trabajo y el reloj."), (
        "<b>bar</b>: one bar at the bottom.",
        "<b>barra</b>: una barra a baix.",
        "<b>barra</b>: una barra abajo.")),
    ("fig", "look-silik.png", 1600, 1000, (
        "The same desktop in the Silik look: a command line in the title bar, a text rail of numbered keys on the "
        "left (SilikStudio, Files, Terminal, Text Editor, Settings) and a status bar with the workspace, base, "
        "kernel, host and power fields.",
        "El mateix escriptori amb l'aspecte Silik: una línia d'ordres a la barra de títol, un rail de tecles "
        "numerades a l'esquerra (SilikStudio, Fitxers, Terminal, Editor de text, Paràmetres) i una barra d'estat amb "
        "els camps d'espai, base, nucli, equip i energia.",
        "El mismo escritorio con el aspecto Silik: una línea de órdenes en la barra de título, un rail de teclas "
        "numeradas a la izquierda (SilikStudio, Archivos, Terminal, Editor de texto, Configuración) y una barra de "
        "estado con los campos de espacio, base, núcleo, equipo y energía."), (
        "<b>silik</b>: the command line on top, a text rail, a status bar.",
        "<b>silik</b>: la línia d'ordres a dalt, un rail de text, una barra d'estat.",
        "<b>silik</b>: la línea de órdenes arriba, un rail de texto, una barra de estado.")),
    ("fig", "start.png", 1600, 1000, (
        "Start in the Silik look: a pane hanging from the mark, with the categories All, Rail, Engineering, Bench, "
        "Windows programs, Tools and System, and the applications of the first: COMMAND, GTKWave, KLayout, Magic, "
        "Netgen, ngspice, PulseView, Qucs-S, SavvyCAN, SilikStudio, Xschem and others.",
        "L'Inici amb l'aspecte Silik: un plafó que penja de la marca, amb les categories Totes, Rail, Enginyeria, "
        "Banc, Programes de Windows, Eines i Sistema, i les aplicacions de la primera: COMMAND, GTKWave, KLayout, "
        "Magic, Netgen, ngspice, PulseView, Qucs-S, SavvyCAN, SilikStudio, Xschem i d'altres.",
        "El Inicio con el aspecto Silik: un panel que cuelga de la marca, con las categorías Todas, Rail, "
        "Ingeniería, Banco, Programas de Windows, Herramientas y Sistema, y las aplicaciones de la primera: COMMAND, "
        "GTKWave, KLayout, Magic, Netgen, ngspice, PulseView, Qucs-S, SavvyCAN, SilikStudio, Xschem y otras."), (
        "Start (the Super key): the applications by category, filtered as you type.",
        "L'Inici (la tecla Super): les aplicacions per categoria, filtrades mentre escrius.",
        "El Inicio (la tecla Super): las aplicaciones por categoría, filtradas mientras escribes.")),
    ("p", (
        "The pictures: " + RIG[0][0].lower() + RIG[0][1:] + " It runs as root, with a stand-in terminal. Pictures of "
        "the system as the CI installs it in a virtual machine are on the branch "
        "[ci-results](" + REPO + "/tree/ci-results).",
        "Les imatges: " + RIG[1][0].lower() + RIG[1][1:] + " Funciona com a root, amb un terminal de substitució. Les "
        "imatges del sistema tal com la CI l'instal·la en una màquina virtual són a la branca "
        "[ci-results](" + REPO + "/tree/ci-results).",
        "Las imágenes: " + RIG[2][0].lower() + RIG[2][1:] + " Funciona como root, con un terminal de sustitución. Las "
        "imágenes del sistema tal como la CI lo instala en una máquina virtual están en la rama "
        "[ci-results](" + REPO + "/tree/ci-results).")),
)

COMMANDS = (
    ("p", (
        "Every action of the desktop goes through `silik`, and `silik` prints the commands it runs. The COMMAND bar "
        "shows the same line before Enter.",
        "Cada acció de l'escriptori passa per `silik`, i `silik` ensenya les ordres que executa. El COMMAND bar "
        "ensenya la mateixa línia abans d'Enter.",
        "Cada acción del escritorio pasa por `silik`, y `silik` muestra las órdenes que ejecuta. El COMMAND bar "
        "muestra la misma línea antes de Enter.")),
    ("table", "cmds", (
        (("`silik status`",) * 3, (
            "what this system is: base, kernel, SilikOS packages, the desktop",
            "què és aquest sistema: base, nucli, paquets de SilikOS, l'escriptori",
            "qué es este sistema: base, núcleo, paquetes de SilikOS, el escritorio")),
        (("`silik doctor`",) * 3, (
            "is this workstation healthy: system, security, graphics, bench, EDA, Windows, network. Each line says "
            "ok, warn, bad or unknown, and the command that fixes it. Unknown, never ok, for what it cannot see. It "
            "changes nothing",
            "si l'equip està bé: sistema, seguretat, gràfics, banc, EDA, Windows, xarxa. Cada línia diu ok, avís, "
            "malament o desconegut, i l'ordre que ho arregla. Desconegut, mai ok, per al que no pot veure. No canvia "
            "res",
            "si el equipo está bien: sistema, seguridad, gráficos, banco, EDA, Windows, red. Cada línea dice ok, "
            "aviso, mal o desconocido, y la orden que lo arregla. Desconocido, nunca ok, para lo que no puede ver. "
            "No cambia nada")),
        (("`silik update`",) * 3, (
            "updates every package, then says whether to restart; `--auto all`, `security` or `off` sets the daily "
            "automatic updates",
            "actualitza tots els paquets i diu si cal reiniciar; `--auto all`, `security` o `off` tria les "
            "actualitzacions automàtiques diàries",
            "actualiza todos los paquetes y dice si hay que reiniciar; `--auto all`, `security` u `off` elige las "
            "actualizaciones automáticas diarias")),
        (("`silik look`",) * 3, (
            "the look: `island`, `bar` or `silik`; `--accent`, `--glass on` or `off`",
            "l'aspecte: `island`, `bar` o `silik`; `--accent`, `--glass on` o `off`",
            "el aspecto: `island`, `bar` o `silik`; `--accent`, `--glass on` u `off`")),
        (("`silik eda tools`",) * 3, (
            "the open EDA tools on this system; `silik eda try` makes them do real jobs together; `silik eda bench` "
            "and `tune` measure and set the simulator's threads",
            "les eines EDA obertes d'aquest sistema; `silik eda try` els fa fer feines de veritat juntes; "
            "`silik eda bench` i `tune` mesuren i trien els fils del simulador",
            "las herramientas EDA abiertas de este sistema; `silik eda try` les hace hacer trabajos de verdad "
            "juntas; `silik eda bench` y `tune` miden y eligen los hilos del simulador")),
        (("`silik eda create`",) * 3, (
            "a box with an EL6, EL7 or EL8 userland for an older release of a vendor's tool; `enter`, `run`, `list`",
            "una capsa amb un sistema EL6, EL7 o EL8 per a una versió antiga de l'eina d'un fabricant; `enter`, "
            "`run`, `list`",
            "una caja con un sistema EL6, EL7 o EL8 para una versión antigua de la herramienta de un fabricante; "
            "`enter`, `run`, `list`")),
        (("`silik dev tools`",) * 3, (
            "the embedded tools on this system; `silik dev try` builds, debugs and talks to a probe",
            "les eines de microcontroladors d'aquest sistema; `silik dev try` compila, depura i parla amb una sonda",
            "las herramientas de microcontroladores de este sistema; `silik dev try` compila, depura y habla con una "
            "sonda")),
        (("`silik dev can`",) * 3, (
            "the CAN interfaces; `up can0 500k` brings one up; `silik dev serial` lists the serial ports and what "
            "they are",
            "les interfícies CAN; `up can0 500k` n'engega una; `silik dev serial` llista els ports sèrie i què són",
            "las interfaces CAN; `up can0 500k` enciende una; `silik dev serial` lista los puertos serie y qué son")),
        (("`silik dev install FILE`",) * 3, (
            "runs the installer of STM32CubeIDE or Code Composer Studio that you downloaded",
            "executa l'instal·lador d'STM32CubeIDE o de Code Composer Studio que has baixat",
            "ejecuta el instalador de STM32CubeIDE o de Code Composer Studio que has descargado")),
        (("`silik win open FILE.exe`",) * 3, (
            "what a double-click runs: the program in its sandbox; `silik win apps` lists the installed Windows "
            "programs",
            "el que executa un doble clic: el programa dins de la seva capsa; `silik win apps` llista els programes "
            "de Windows instal·lats",
            "lo que ejecuta un doble clic: el programa dentro de su caja; `silik win apps` lista los programas de "
            "Windows instalados")),
        (("`silik power`",) * 3, (
            "the power profile: `performance`, `balanced`, `saver` or `auto`, through the base's tuned; `zram`, "
            "`trim`",
            "el perfil d'energia: `performance`, `balanced`, `saver` o `auto`, amb el tuned de la base; `zram`, "
            "`trim`",
            "el perfil de energía: `performance`, `balanced`, `saver` o `auto`, con el tuned de la base; `zram`, "
            "`trim`")),
        (("`silik secure status`",) * 3, (
            "a read-only audit of the system's security; `silik secure apply` sets the SilikOS defaults and prints "
            "what it runs",
            "una revisió de la seguretat del sistema, que només llegeix; `silik secure apply` posa els valors de "
            "SilikOS i ensenya què executa",
            "una revisión de la seguridad del sistema, que solo lee; `silik secure apply` pone los valores de "
            "SilikOS y muestra qué ejecuta")),
    )),
    ("h2", ("what they print", "què escriuen", "qué escriben")),
    ("p", (
        "Run on " + DATE + " in an AlmaLinux 9.8 container with four SilikOS packages (silik-tools, silik-dev, "
        "silik-eda-open, silik-win) and our ngspice installed, as an ordinary user. There is no desktop and no "
        "hardware there, and most tools are absent: the output says so. The lines that begin with `$` are `silik`'s: "
        "the commands it runs.",
        "Executat el " + DATE + " en un contenidor AlmaLinux 9.8 amb quatre paquets de SilikOS (silik-tools, "
        "silik-dev, silik-eda-open, silik-win) i el nostre ngspice instal·lats, com a usuari normal. Allà no hi ha "
        "escriptori ni maquinari, i la majoria d'eines no hi són: la sortida ho diu. Les línies que comencen per `$` "
        "són de `silik`: les ordres que executa. La sortida de `silik` aquí és en anglès.",
        "Ejecutado el " + DATE + " en un contenedor AlmaLinux 9.8 con cuatro paquetes de SilikOS (silik-tools, "
        "silik-dev, silik-eda-open, silik-win) y nuestro ngspice instalados, como usuario normal. Allí no hay "
        "escritorio ni hardware, y la mayoría de herramientas no están: la salida lo dice. Las líneas que empiezan "
        "por `$` son de `silik`: las órdenes que ejecuta. La salida de `silik` aquí está en inglés.")),
    ("out", "silik eda try sim"),
    ("out", "silik --dry-run look bar --accent cobalt"),
    ("out", "silik --dry-run dev can up can0 500k"),
    ("out", "silik doctor eda windows"),
)

STATE = (
    ("p", (
        "A prototype verified in virtual machines and containers, not a product. The repository keeps two tables, "
        "verified and not verified, with how each row was run: [docs/STATUS.md](docs/STATUS.md). Nothing enters the "
        "first without having been run.",
        "Un prototip verificat en màquines virtuals i contenidors, no un producte. El repositori té dues taules, "
        "verificat i no verificat, amb com s'ha executat cada fila: [docs/STATUS.md](docs/STATUS.md). Res entra a "
        "la primera sense haver-se executat.",
        "Un prototipo verificado en máquinas virtuales y contenedores, no un producto. El repositorio tiene dos "
        "tablas, verificado y no verificado, con cómo se ha ejecutado cada fila: [docs/STATUS.md](docs/STATUS.md). "
        "Nada entra en la primera sin haberse ejecutado.")),
    ("h2", ("verified", "verificat", "verificado")),
    ("table", "head", (
        ((("what", "how"), ("què", "com"), ("qué", "cómo")),),
        (("installation", "instal·lació", "instalación"), (
            "The ISO installs unattended in a virtual machine, the installed system boots and checks itself. "
            "GitHub Actions, workflow CI; the last complete run when this page was written: 13/11/2026, commit "
            "f14e5cd, 121 checks ok, none failed; it started in 11.3 to 12.0 s (9.3 s in the run before: it depends on "
            "the runner) with about 985 MB in use. Beside the stock "
            "AlmaLinux 9 Workstation in one virtual machine (workflow Compare) it used 151 to 166 MB less memory and "
            "reached the desktop 0.65 to 0.85 s later (its session is X11, the base's Wayland): not faster to start.",
            "La ISO s'instal·la sola en una màquina virtual, el sistema instal·lat arrenca i es revisa ell mateix. "
            "GitHub Actions, workflow CI; l'última execució completa quan es va escriure aquesta pàgina: 13/11/2026, "
            "commit f14e5cd, 121 comprovacions correctes, cap de fallada; va arrencar en 11,3 a 12,0 s (9,3 s a "
            "l'execució anterior: depèn del runner) amb uns 985 MB en ús. Al "
            "costat de l'AlmaLinux 9 Workstation de sèrie en una mateixa màquina virtual (workflow Compare) va fer "
            "servir de 151 a 166 MB menys de memòria i va arribar a l'escriptori de 0,65 a 0,85 s més tard (la seva "
            "sessió és X11, la de la base Wayland): no arrenca més ràpid.",
            "La ISO se instala sola en una máquina virtual, el sistema instalado arranca y se revisa a sí mismo. "
            "GitHub Actions, workflow CI; la última ejecución completa cuando se escribió esta página: 13/11/2026, "
            "commit f14e5cd, 121 comprobaciones correctas, ninguna fallida; arrancó en 11,3 a 12,0 s (9,3 s en la "
            "ejecución anterior: depende del runner) con unos 985 MB en uso. Al "
            "lado del AlmaLinux 9 Workstation de serie en una misma máquina virtual (workflow Compare) usó de 151 a "
            "166 MB menos de memoria y llegó al escritorio de 0,65 a 0,85 s más tarde (su sesión es X11, la de la "
            "base Wayland): no arranca más rápido.")),
        (("desktop", "escriptori", "escritorio"), (
            "The three looks, Start, the COMMAND bar, the login and lock screens: on that installed system, on its "
            "screen.",
            "Els tres aspectes, l'Inici, el COMMAND bar, les pantalles d'entrada i de bloqueig: en aquell sistema "
            "instal·lat, a la seva pantalla.",
            "Los tres aspectos, el Inicio, el COMMAND bar, las pantallas de entrada y de bloqueo: en aquel sistema "
            "instalado, en su pantalla.")),
        (("chips", "xips", "chips"), (
            "`silik eda try` on that installed system: 13 jobs ok (an inverter from schematic to layout and back, a "
            "counter down to gates, a diode in the device simulator).",
            "`silik eda try` en aquell sistema instal·lat: 13 feines correctes (un inversor de l'esquema al layout i "
            "tornar, un comptador fins a portes, un díode al simulador de dispositius).",
            "`silik eda try` en aquel sistema instalado: 13 trabajos correctos (un inversor del esquema al layout y "
            "vuelta, un contador hasta puertas, un diodo en el simulador de dispositivos).")),
        (("Windows", "Windows", "Windows"), (
            "Programs written for the tests (64 and 32 bit, an installer, an .msi, a .NET program) run with our "
            "Wine in the sandbox, with SELinux enforcing, on that installed system.",
            "Programes fets per a les proves (de 64 i de 32 bits, un instal·lador, un .msi, un programa .NET) "
            "funcionen amb el nostre Wine dins de la capsa, amb SELinux en mode enforcing, en aquell sistema "
            "instal·lat.",
            "Programas hechos para las pruebas (de 64 y de 32 bits, un instalador, un .msi, un programa .NET) "
            "funcionan con nuestro Wine dentro de la caja, con SELinux en modo enforcing, en aquel sistema "
            "instalado.")),
        (("embedded", "microcontroladors", "microcontroladores"), (
            "`silik dev try`: 7 jobs ok (build, C library, C++, debug, probe, DFU, ST-LINK) in a clean EL 9 and on "
            "the installed system. No board was connected.",
            "`silik dev try`: 7 feines correctes (compilar, biblioteca de C, C++, depurar, sonda, DFU, ST-LINK) en "
            "un EL 9 net i al sistema instal·lat. No hi havia cap placa connectada.",
            "`silik dev try`: 7 trabajos correctos (compilar, biblioteca de C, C++, depurar, sonda, DFU, ST-LINK) en "
            "un EL 9 limpio y en el sistema instalado. No había ninguna placa conectada.")),
        (("ARM", "ARM", "ARM"), (
            "The SilikOS packages build on AlmaLinux 9 for aarch64, and so do most of its tools, which pass their "
            "trials there: on GitHub's ARM runners (a few under emulation only).",
            "Els paquets de SilikOS es construeixen sobre AlmaLinux 9 per a aarch64, i la majoria de les seves eines "
            "també, i hi passen les seves proves: als runners ARM de GitHub (unes quantes només sota emulació).",
            "Los paquetes de SilikOS se construyen sobre AlmaLinux 9 para aarch64, y la mayoría de sus herramientas "
            "también, y pasan allí sus pruebas: en los runners ARM de GitHub (unas cuantas solo bajo emulación).")),
    )),
    ("h2", ("not verified", "no verificat", "no verificado")),
    ("ul", (
        ("any real hardware: graphics drivers (NVIDIA), Wi-Fi, suspend, a CAN adapter on a bus, flashing or "
         "debugging a board, a logic analyser;",
         "cap maquinari real: controladors gràfics (NVIDIA), Wi-Fi, suspensió, un adaptador CAN en un bus, programar "
         "o depurar una placa, un analitzador lògic;",
         "ningún hardware real: controladores gráficos (NVIDIA), Wi-Fi, suspensión, un adaptador CAN en un bus, "
         "programar o depurar una placa, un analizador lógico;"),
        ("any vendor tool: Cadence, Synopsys, Altium, STM32CubeIDE, Code Composer Studio;",
         "cap eina de fabricant: Cadence, Synopsys, Altium, STM32CubeIDE, Code Composer Studio;",
         "ninguna herramienta de fabricante: Cadence, Synopsys, Altium, STM32CubeIDE, Code Composer Studio;"),
        ("the Windows virtual machine;", "la màquina virtual de Windows;", "la máquina virtual de Windows;"),
        ("SilikOS installed on an ARM machine;", "SilikOS instal·lat en una màquina ARM;",
         "SilikOS instalado en una máquina ARM;"),
        ("what each power profile does on a laptop: power drawn, battery hours;",
         "què fa cada perfil d'energia en un portàtil: consum, hores de bateria;",
         "qué hace cada perfil de energía en un portátil: consumo, horas de batería;"),
        ("what `silik --help` marks as experimental (a project's pinned tools, the bench test runner, the mirror "
         "for a network without Internet, the vendors' requirement lists): run in containers or with stand-ins only.",
         "el que `silik --help` marca com a experimental (les eines fixades d'un projecte, les proves de banc, el "
         "mirall per a una xarxa sense Internet, les llistes de requisits dels fabricants): executat només en contenidors o amb substituts.",
         "lo que `silik --help` marca como experimental (las herramientas fijadas de un proyecto, las pruebas de "
         "banco, el espejo para una red sin Internet, las listas de requisitos de los fabricantes): ejecutado solo en contenedores o con sustitutos."),
    )),
    ("p", (
        "There is no signed package repository yet, so an installed system does not receive new versions of "
        "SilikOS's own packages; the base's updates arrive from the base. The list above is the short one: "
        "[docs/STATUS.md](docs/STATUS.md) has every row.",
        "Encara no hi ha un repositori de paquets signat, de manera que un sistema instal·lat no rep versions noves "
        "dels paquets de SilikOS; les actualitzacions de la base arriben de la base. La llista de dalt és la curta: "
        "[docs/STATUS.md](docs/STATUS.md) té totes les files.",
        "Todavía no hay un repositorio de paquetes firmado, así que un sistema instalado no recibe versiones nuevas "
        "de los paquetes de SilikOS; las actualizaciones de la base llegan de la base. La lista de arriba es la "
        "corta: [docs/STATUS.md](docs/STATUS.md) tiene todas las filas.")),
)

GET = (
    ("p", (
        "Today there is no release to download and no package repository published. The installer of the CI's last "
        "green run is its artifact `silikos-iso` (GitHub Actions, with a GitHub account, for a limited time); or build "
        "it from the repository. Try it in a virtual machine first, since nothing has been run on real hardware.",
        "Avui no hi ha cap release per baixar ni cap repositori de paquets publicat. L'instal·lador de l'última "
        "execució en verd de la CI és el seu artefacte `silikos-iso` (GitHub Actions, amb un compte de GitHub, durant un "
        "temps limitat); o construeix-lo des del repositori. Prova'l primer en una màquina virtual, perquè res no s'ha "
        "executat en maquinari real.",
        "Hoy no hay ninguna release para descargar ni ningún repositorio de paquetes publicado. El instalador de la "
        "última ejecución en verde de la CI es su artefacto `silikos-iso` (GitHub Actions, con una cuenta de GitHub, "
        "durante un tiempo limitado); o constrúyelo desde el repositorio. Pruébalo primero en una máquina virtual, "
        "porque nada se ha ejecutado en hardware real.")),
    ("pre", "git clone " + REPO + " && cd SilikOs\n"
            "bash tools/build_rpms.sh                # rpmbuild, createrepo_c\n"
            "python3 -m unittest discover -s tests   # Python 3.9 or later\n"
            "bash tools/build_iso.sh                 # xorriso, mtools, cpio, curl, gpg, isomd5sum; repo.almalinux.org"),
    ("p", (
        "`tools/build_rpms.sh` builds the packages and their repository metadata; `tools/build_iso.sh`, the network "
        "installer ISO. "
        "The installer downloads the base system from AlmaLinux's and EPEL's repositories, so the machine needs a "
        "network. It never selects or erases a disk: you choose it. The steps, and how to put SilikOS on an "
        "installed AlmaLinux 9: [docs/BUILD.md](docs/BUILD.md).",
        "`tools/build_rpms.sh` construeix els paquets i les metadades del seu repositori; `tools/build_iso.sh`, la ISO "
        "d'instal·lació per xarxa. L'instal·lador baixa el sistema base dels repositoris d'AlmaLinux i d'EPEL, de manera que la "
        "màquina necessita xarxa. No tria ni esborra mai cap disc: el tries tu. Els passos, i com posar SilikOS en "
        "un AlmaLinux 9 ja instal·lat: [docs/BUILD.md](docs/BUILD.md).",
        "`tools/build_rpms.sh` construye los paquetes y los metadatos de su repositorio; `tools/build_iso.sh`, la ISO "
        "de instalación por red. El instalador descarga el sistema base de los repositorios de AlmaLinux y de EPEL, así "
        "que la máquina necesita red. Nunca elige ni borra ningún disco: lo eliges tú. Los pasos, y cómo poner "
        "SilikOS en un AlmaLinux 9 ya instalado: [docs/BUILD.md](docs/BUILD.md).")),
    ("h2", ("repository", "repositori", "repositorio")),
    ("table", None, (
        (("[BTomeu/SilikOs](" + REPO + ")",) * 3, (
            "the source: packages, kickstart, installer, tests",
            "el codi: paquets, kickstart, instal·lador, proves",
            "el código: paquetes, kickstart, instalador, pruebas")),
        (("[docs/STATUS.md](docs/STATUS.md)",) * 3, (
            "what has been run, and what has not", "què s'ha executat, i què no", "qué se ha ejecutado, y qué no")),
        (("[docs/BUILD.md](docs/BUILD.md)",) * 3, (
            "building the packages and the ISO, installing", "construir els paquets i la ISO, instal·lar",
            "construir los paquetes y la ISO, instalar")),
        (("[docs/SECURITY.md](docs/SECURITY.md)",) * 3, (
            "what the system sets, and why", "què configura el sistema, i per què",
            "qué configura el sistema, y por qué")),
        (("[SECURITY.md](SECURITY.md)",) * 3, (
            "reporting a vulnerability privately", "avisar d'una vulnerabilitat en privat",
            "avisar de una vulnerabilidad en privado")),
    )),
    ("h2", ("licence, brand", "llicència, marca", "licencia, marca")),
    ("ul", (
        ("The licence of SilikOS's own code is not chosen yet: until it is, all rights are reserved. The base and "
         "the tools keep their own licences. Cascadia Mono, the typeface of this page, is under the "
         "[SIL Open Font License](site:fonts/CascadiaMono-LICENSE.txt).",
         "La llicència del codi propi de SilikOS encara no està triada: fins llavors, tots els drets reservats. La "
         "base i les eines mantenen les seves llicències. Cascadia Mono, la lletra d'aquesta pàgina, té la "
         "[SIL Open Font License](site:fonts/CascadiaMono-LICENSE.txt).",
         "La licencia del código propio de SilikOS todavía no está elegida: hasta entonces, todos los derechos "
         "reservados. La base y las herramientas mantienen sus licencias. Cascadia Mono, la letra de esta página, "
         "tiene la [SIL Open Font License](site:fonts/CascadiaMono-LICENSE.txt)."),
        ("The names SilikOS, SilikStudio and SilikVolt and the SilikVolt mark are not licensed for reuse.",
         "Els noms SilikOS, SilikStudio i SilikVolt i la marca SilikVolt no tenen llicència de reutilització.",
         "Los nombres SilikOS, SilikStudio y SilikVolt y la marca SilikVolt no tienen licencia de reutilización."),
        ("No vendor software is in the repository or in the system: EDA tools, Windows and Windows programs are the "
         "user's own licences. SilikOS is not affiliated with or endorsed by the AlmaLinux OS Foundation, Red Hat, "
         "or the vendors and projects whose tools it names.",
         "No hi ha programari de cap fabricant ni al repositori ni al sistema: les eines EDA, Windows i els "
         "programes de Windows són llicències de l'usuari. SilikOS no està afiliat ni avalat per l'AlmaLinux OS "
         "Foundation, Red Hat, ni els fabricants i projectes de les eines que anomena.",
         "No hay software de ningún fabricante ni en el repositorio ni en el sistema: las herramientas EDA, Windows "
         "y los programas de Windows son licencias del usuario. SilikOS no está afiliado ni avalado por la AlmaLinux "
         "OS Foundation, Red Hat, ni los fabricantes y proyectos de las herramientas que nombra."),
        ("This page sets no cookie, counts nothing and asks nothing of another host.",
         "Aquesta pàgina no posa cap galeta, no compta res i no demana res a cap altre servidor.",
         "Esta página no pone ninguna cookie, no cuenta nada y no pide nada a ningún otro servidor."),
    )),
)

# a picture cut to a pane, and its left part for a narrow window: name, width, height
NARROW = {"command.png": ("command-narrow.png", 1100, 668)}
BODY = {"what": WHAT, "looks": LOOKS, "commands": COMMANDS, "state": STATE, "get": GET}
# the rail's second group: files of the repository, by their names
FILES = (("README.md", BLOB + "README.md"), ("docs/STATUS.md", BLOB + "docs/STATUS.md"),
         ("docs/BUILD.md", BLOB + "docs/BUILD.md"), ("SECURITY.md", BLOB + "SECURITY.md"))

KEYS_JS = """document.addEventListener('keydown', function (e) {
  if (e.ctrlKey || e.altKey || e.metaKey || e.defaultPrevented) return;
  var a = document.querySelector('.rail a[data-key="' + e.key + '"]');
  if (a) { a.focus(); a.click(); }
});"""


def esc(s):
    return html.escape(s, quote=True)


def inline(s, root):
    """the text's small markup: `code`, [words](address), <b> kept; everything else escaped"""
    out, pos = [], 0
    for m in re.finditer(r"`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)|<b>([^<]+)</b>", s):
        out.append(esc(s[pos:m.start()]))
        if m.group(1) is not None:
            out.append("<code>%s</code>" % esc(m.group(1)))
        elif m.group(2) is not None:
            href = m.group(3)
            if href.startswith("site:"):
                href = root + href[5:]
            elif not href.startswith(("#", "https://")):
                href = BLOB + href
            out.append('<a href="%s">%s</a>' % (esc(href), esc(m.group(2))))
        else:
            out.append("<b>%s</b>" % esc(m.group(4)))
        pos = m.end()
    out.append(esc(s[pos:]))
    return "".join(out)


def block(b, i, root, first):
    kind = b[0]
    if kind in ("p", "lead"):
        return '<p%s>%s</p>' % (' class="lead"' if kind == "lead" else "", inline(b[1][i], root))
    if kind == "h2":
        return "<h2>%s</h2>" % esc(b[1][i])
    if kind == "ul":
        return "<ul>\n%s\n</ul>" % "\n".join("<li>%s</li>" % inline(item[i], root) for item in b[1])
    if kind == "fig":
        _, name, w, h, alt, cap = b
        img = ('<img src="%simg/%s" width="%d" height="%d" alt="%s"%s>'
               % (root, name, w, h, esc(alt[i]), "" if first else ' loading="lazy"'))
        cls = ""
        if name in NARROW:
            # cut to a pane of the desktop: the picture ends at the pane's own frame (no second frame around it), and
            # a narrow window takes the pane's left part, where the text still reads
            nname, nw, nh = NARROW[name]
            img = ('<picture><source srcset="%simg/%s" media="(max-width: 560px)" width="%d" height="%d">%s</picture>'
                   % (root, nname, nw, nh, img))
            cls = ' class="pane"'
        return ('<figure%s>\n<a href="%simg/%s">%s</a>\n<figcaption>%s</figcaption>\n</figure>'
                % (cls, root, name, img, inline(cap[i], root)))
    if kind == "table":
        _, cls, rows = b
        head = ""
        if cls == "head":
            head = "<thead><tr>%s</tr></thead>\n" % "".join('<th scope="col">%s</th>' % esc(c) for c in rows[0][0][i])
            rows, cls = rows[1:], None
        body = "\n".join('<tr><th scope="row">%s</th><td>%s</td></tr>' % (inline(k[i], root), inline(v[i], root)) for k, v in rows)
        return "<table%s>\n%s<tbody>\n%s\n</tbody>\n</table>" % (' class="%s"' % cls if cls else "", head, body)
    if kind == "pre":
        return "<pre>%s</pre>" % esc(b[1])
    if kind == "out":
        return ('<pre><span class="o">›</span> <b>%s</b>\n%s</pre>' % (esc(b[1]), esc(OUT[b[1]].rstrip("\n"))))
    raise ValueError(kind)


def page(lang):
    i = LANGS.index(lang)
    root = "" if lang == "en" else "../"
    t = lambda k: UI[k][i]
    here = {"en": "index.html", "ca": "ca/index.html", "es": "es/index.html"}
    o = ['<!doctype html>', '<html lang="%s">' % lang, "<head>", '<meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">',
         "<title>%s</title>" % esc(t("title")), '<meta name="description" content="%s">' % esc(t("description")),
         '<meta name="color-scheme" content="light dark">',
         '<link rel="icon" href="%sfavicon.svg" type="image/svg+xml">' % root,
         '<link rel="stylesheet" href="%sstyle.css">' % root]
    o += ['<link rel="alternate" hreflang="%s" href="%s%s">' % (l, root, here[l]) for l in LANGS if l != lang]
    o += ["</head>", "<body>", '<header class="tb">',
          '<a class="mk" href="#what"><picture><source srcset="%simg/mark.svg" media="(prefers-color-scheme: dark)">'
          '<img src="%simg/mark-light.svg" width="35" height="20" alt="%s"></picture><span>SilikOS</span></a>'
          % (root, root, esc(t("mark"))),
          '<div class="cmd" aria-hidden="true"><span class="cmd-pr">›</span><span class="cmd-path"></span>'
          '<span class="cmd-cur"></span><span class="cmd-hint">%s</span></div>' % esc(t("keys")),
          '<nav class="tb-r" aria-label="%s">' % esc(t("language"))]
    for l in LANGS:
        o.append('<a href="%s%s" lang="%s" hreflang="%s"%s>%s</a>'
                 % (root, here[l], l, l, ' aria-current="page"' if l == lang else "", l.upper()))
    o += ['<a class="gh" href="%s">GitHub</a>' % REPO, "</nav>", "</header>",
          '<nav class="rail" aria-label="%s">' % esc(t("sections"))]
    for n, (ident, name) in enumerate(VIEWS, 1):
        o.append('<a href="#%s" accesskey="%d" data-key="%d"><span class="n">%d</span>%s</a>' % (ident, n, n, n, esc(name[i])))
    o.append('<div class="rail-h">%s</div>' % esc(t("repository")))
    o += ['<a class="x" href="%s">%s</a>' % (href, esc(name)) for name, href in FILES]
    o += ["</nav>", "<main>"]
    for n, (ident, name) in enumerate(VIEWS, 1):
        o.append('<section id="%s">' % ident)
        o.append("<h1>%s</h1>" % ("SilikOS" if ident == "what" else esc(name[i])))
        first = True
        for b in BODY[ident]:
            o.append(block(b, i, root, first and ident == "what"))
            if b[0] == "fig":
                first = False
        if n < len(VIEWS):
            nid, nname = VIEWS[n]
            o.append('<a class="next" href="#%s"><span class="n">%d</span>%s</a>' % (nid, n + 1, esc(nname[i])))
        o.append("</section>")
    o += ["</main>", '<footer class="sb">', '<span class="msg">%s</span>' % esc(t("ready"))]
    for k, v in ((t("k_base"), "EL 9.8"), (t("k_state"), t("v_state")), (t("k_licence"), t("v_licence")), (t("k_date"), DATE)):
        o.append('<span class="f"><span class="k">%s</span><span class="v">%s</span></span>' % (esc(k), esc(v)))
    o += ["</footer>", "<script>", KEYS_JS, "</script>", "</body>", "</html>", ""]
    return "\n".join(o)


def not_found():
    """404.html: a server gives it at any address, so it carries its own few rules and no picture"""
    css = ("body{margin:0;min-height:100vh;display:grid;grid-template-rows:40px 1fr auto;background:#f7f6f3;color:#1a1b1e;"
           "font:14px/1.6 'Cascadia Mono','DejaVu Sans Mono',ui-monospace,Menlo,Consolas,monospace}"
           ".tb{display:flex;align-items:center;padding:0 14px;background:#1a1b1e;color:#f7f6f3;font-size:13px;font-weight:600}"
           "main{padding:26px 16px;max-width:78ch}h1{margin:0 0 16px;padding-bottom:10px;border-bottom:1px solid #1a1b1e;"
           "font-size:20px;font-weight:600}p{margin:0 0 10px}a{color:inherit;text-underline-offset:3px}"
           "a:focus-visible{outline:2px solid currentColor;outline-offset:2px}"
           ".sb{display:flex;gap:7px;padding:4px 14px;border-top:1px solid #1a1b1e;font-size:12px}.k{color:#6b6d72}"
           "@media (prefers-color-scheme:dark){body{background:#17181b;color:#ecebe7}.tb{background:#ecebe7;color:#17181b}"
           "h1{border-color:#ecebe7}.sb{border-color:#ecebe7}.k{color:#9a9b9f}}")
    lines = (("en", "This address is not a page of the site.", "Start"),
             ("ca", "Aquesta adreça no és cap pàgina del lloc.", "Inici"),
             ("es", "Esta dirección no es ninguna página del sitio.", "Inicio"))
    o = ['<!doctype html>', '<html lang="en">', "<head>", '<meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">', "<title>SilikOS: 404</title>",
         '<meta name="color-scheme" content="light dark">', "<style>%s</style>" % css, "</head>", "<body>",
         '<header class="tb">SilikOS</header>', "<main>", "<h1>404</h1>"]
    for l, words, start in lines:
        o.append('<p lang="%s">%s <a href="./">%s</a></p>' % (l, esc(words), esc(start)))
    o += ['<p><a href="%s">%s</a></p>' % (REPO, REPO.replace("https://", "")), "</main>",
          '<footer class="sb"><span class="k">status</span><span>404</span></footer>', "</body>", "</html>", ""]
    return "\n".join(o)


def outputs():
    """(path in the repository, its text) of every page; tests/test_site.py compares the committed pages with these"""
    return [("site/index.html", page("en")), ("site/ca/index.html", page("ca")), ("site/es/index.html", page("es")),
            ("site/404.html", not_found())]


def main():
    for rel, text in outputs():
        p = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        print(rel)


if __name__ == "__main__":
    main()
