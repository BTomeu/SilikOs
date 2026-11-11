/* SilikOS shell — the Silik layout on GNOME Shell (the same parts as SilikStudio's window):
 *   title bar   the mark (the Start key), then the command line (a key that opens the COMMAND bar, Super+Space),
 *               clock and system menu
 *   rail        the task bar, as text keys, digit first: the favourites (Super+1..9 open them), then the other open
 *               applications; the focused one is inverse video, a running one carries an ink edge, an application
 *               with several windows lists them below its key; at the bottom the workspaces and the windows view
 *   Start       a pane that hangs from the mark (click, or the Super key): categories, the applications as rows,
 *               a filter as you type; Enter opens, Esc closes
 *   status bar  the one message channel (the last command `silik` ran, read from $XDG_RUNTIME_DIR/silik-last), then
 *               "key value" fields: workspace, base, kernel, host
 * That is the look "silik". The key `look` of the settings com.silikvolt.silikos.shell (`silik look`) chooses it or
 * one of the Flow looks, "bar" and "island" (flow.js): one piece at the bottom of the screen, the applications as
 * icons. The icons and Start are shared; in a Flow look Start opens from the piece: the applications of the rail as a
 * grid with their digit, the files used last, every application as soon as one types (or Tab), and the session's keys,
 * which run `silik session lock | logout | off`. The look follows the key while the session runs.
 * Nothing here runs a system action: the keys open applications and windows, every action stays in `silik`. */
'use strict';

const { Clutter, Gio, GLib, Gtk, Meta, Pango, PangoCairo, Shell, St } = imports.gi;
const Main = imports.ui.main;
const AppFavorites = imports.ui.appFavorites;
const Util = imports.misc.util;
const Me = imports.misc.extensionUtils.getCurrentExtension();
const Flow = Me.imports.flow;

const RAIL_W = 152, SB_H = 22, START_W = 660, START_H = 520;
const FLOW_W = 640, FLOW_H = 548, PIN_COLS = 4, RECENT_N = 5;      /* Start in a Flow look */
const SCHEMA = 'com.silikvolt.silikos.shell';                      /* key "look": silik | bar | island */
const COMMAND_ID = 'org.silikvolt.Command.desktop';   /* the COMMAND bar is the title bar's command line, not a rail key */

const TEXT = {
    en: { ready: 'ready', ws: 'workspace', base: 'base', kernel: 'kernel', host: 'host', open: 'open', windows: 'Windows',
          filter: 'type to filter', kOpen: 'open', kMove: 'move', kCat: 'category', kClose: 'close', none: 'nothing matches',
          hint: 'Super+Space', search: 'type to search the applications', pinned: 'pinned', recent: 'recent', all: 'all applications',
          lock: 'lock', logout: 'log out', off: 'power off',
          cats: { all: 'All', fav: 'Rail', eda: 'Engineering', win: 'Windows programs', dev: 'Development', office: 'Office',
                  graphics: 'Graphics', net: 'Internet', media: 'Sound and video', tools: 'Tools', system: 'System', other: 'Other' } },
    ca: { ready: 'a punt', ws: 'espai', base: 'base', kernel: 'nucli', host: 'equip', open: 'obertes', windows: 'Finestres',
          filter: 'escriu per filtrar', kOpen: 'obre', kMove: 'mou', kCat: 'categoria', kClose: 'tanca', none: 'no hi ha res que coincideixi',
          hint: 'Super+Espai', search: 'escriu per cercar les aplicacions', pinned: 'ancorades', recent: 'recents', all: 'totes les aplicacions',
          lock: 'bloqueja', logout: 'tanca la sessió', off: 'apaga',
          cats: { all: 'Totes', fav: 'Rail', eda: 'Enginyeria', win: 'Programes de Windows', dev: 'Desenvolupament', office: 'Oficina',
                  graphics: 'Gràfics', net: 'Internet', media: 'So i vídeo', tools: 'Eines', system: 'Sistema', other: 'Altres' } },
    es: { ready: 'listo', ws: 'espacio', base: 'base', kernel: 'núcleo', host: 'equipo', open: 'abiertas', windows: 'Ventanas',
          filter: 'escribe para filtrar', kOpen: 'abre', kMove: 'mueve', kCat: 'categoría', kClose: 'cierra', none: 'nada coincide',
          hint: 'Super+Espacio', search: 'escribe para buscar las aplicaciones', pinned: 'ancladas', recent: 'recientes', all: 'todas las aplicaciones',
          lock: 'bloquea', logout: 'cierra la sesión', off: 'apaga',
          cats: { all: 'Todas', fav: 'Rail', eda: 'Ingeniería', win: 'Programas de Windows', dev: 'Desarrollo', office: 'Oficina',
                  graphics: 'Gráficos', net: 'Internet', media: 'Sonido y vídeo', tools: 'Herramientas', system: 'Sistema', other: 'Otras' } },
};

/* Start's categories: the freedesktop main categories an application declares; the first that matches wins */
const CATS = [
    ['eda', ['Engineering', 'Electronics', 'Science']],
    ['dev', ['Development']],
    ['office', ['Office']],
    ['graphics', ['Graphics']],
    ['net', ['Network']],
    ['media', ['AudioVideo', 'Audio', 'Video']],
    ['system', ['System', 'Settings']],
    ['tools', ['Utility']],
];

function lang() {
    for (const l of GLib.get_language_names()) {
        const k = l.slice(0, 2).toLowerCase();
        if (TEXT[k]) return k;
    }
    return 'en';
}

function readText(path) {
    try {
        const [ok, bytes] = GLib.file_get_contents(path);
        return ok ? imports.byteArray.toString(bytes).trim() : '';
    } catch (e) { return ''; }
}

function osRelease() {
    const o = {};
    for (const line of readText('/etc/os-release').split('\n')) {
        const m = line.match(/^([A-Z_]+)=(.*)$/);
        if (m) o[m[1]] = m[2].replace(/^"|"$/g, '');
    }
    return o;
}

/* a Windows program installed through `silik win` (its desktop entry is made by Wine and rewritten by silik) */
function isWin(app) {
    const id = app.get_id(), info = app.get_app_info();
    const exec = info ? (info.get_commandline() || '') : '';
    return id.startsWith('wine-') || exec.includes('silik win ') || (info && (info.get_categories() || '').includes('Wine'));
}

function category(app) {
    if (isWin(app)) return 'win';
    const info = app.get_app_info();
    const cs = info ? (info.get_categories() || '').split(';') : [];
    for (const [k, names] of CATS) if (names.some(n => cs.includes(n))) return k;
    return 'other';
}

/* One family of icons. An application shows its own line (symbolic) icon when it ships one; a terminal, file
 * manager, text editor, browser or settings program without one takes the generic line icon of its kind; anything
 * else (a Windows program, an EDA tool) is its initial in an ink frame. All of them are drawn in the text colour of
 * where they sit, so they follow inverse video. Colour pictures of other styles are not shown. */
const KINDS = [['TerminalEmulator', 'utilities-terminal-symbolic'], ['FileManager', 'system-file-manager-symbolic'],
               ['TextEditor', 'accessories-text-editor-symbolic'], ['WebBrowser', 'web-browser-symbolic'],
               ['Settings', 'preferences-system-symbolic']];

function symbolicName(app) {
    const theme = Gtk.IconTheme.get_default();
    const info = app.get_app_info();
    if (!info) return null;
    const gi = info.get_icon();
    if (gi instanceof Gio.ThemedIcon) {
        for (const n of gi.get_names()) {
            const sn = n.endsWith('-symbolic') ? n : n + '-symbolic';
            if (theme.has_icon(sn)) return sn;
        }
    }
    const cs = (info.get_categories() || '').split(';');
    for (const [c, n] of KINDS) if (cs.includes(c) && theme.has_icon(n)) return n;
    return null;
}

function monogram(name, size) {
    const s = St.ThemeContext.get_for_stage(global.stage).scale_factor;
    const a = new St.DrawingArea({ width: size * s, height: size * s, style_class: 'silik-mono' });
    const ch = ((name || '').trim().charAt(0) || '?').toUpperCase();
    a.connect('repaint', () => {
        const cr = a.get_context();
        const [w, h] = a.get_surface_size();
        Clutter.cairo_set_source_color(cr, a.get_theme_node().get_foreground_color());
        const lw = Math.max(1, Math.round(w / 16));
        cr.setLineWidth(lw);
        cr.rectangle(lw / 2, lw / 2, w - lw, h - lw);
        cr.stroke();
        const layout = PangoCairo.create_layout(cr);
        const fd = Pango.FontDescription.from_string('Cascadia Mono Bold');
        fd.set_absolute_size(h * 0.62 * Pango.SCALE);
        layout.set_font_description(fd);
        layout.set_text(ch, -1);
        const [ink] = layout.get_pixel_extents();
        cr.moveTo((w - ink.width) / 2 - ink.x, (h - ink.height) / 2 - ink.y);
        PangoCairo.show_layout(cr, layout);
        cr.$dispose();
    });
    return a;
}

/* The SilikVolt mark in the title bar: the brand's SMALL cut (SilikStudio, app/js/brand.js: a 28 x 16 box, arc centre
 * (14, 14.2), radius 11.6, stroke 1.9, dot radius 2.2 at (23.86, 8.1)), drawn as a line and a dot at one scale in
 * both directions and in the text colour. It is never put in an icon box: an icon box is square and would stretch it. */
function markSmall() {
    const s = St.ThemeContext.get_for_stage(global.stage).scale_factor;
    const a = new St.DrawingArea({ width: 28 * s, height: 16 * s, style_class: 'silik-mk-mark', y_align: Clutter.ActorAlign.CENTER });
    a.connect('repaint', () => {
        const cr = a.get_context();
        const [w] = a.get_surface_size();
        const k = w / 28;                                   /* one factor: the box keeps 28 : 16 */
        Clutter.cairo_set_source_color(cr, a.get_theme_node().get_foreground_color());
        cr.setLineWidth(1.9 * k);
        cr.setLineCap(1);                                   /* round */
        cr.arc(14 * k, 14.2 * k, 11.6 * k, Math.PI, 2 * Math.PI);
        cr.stroke();
        cr.arc(23.86 * k, 8.1 * k, 2.2 * k, 0, 2 * Math.PI);
        cr.fill();
        cr.$dispose();
    });
    return a;
}

let origIcon = null;   /* the shell's own Shell.App.create_icon_texture, kept while the extension is on */

function silikIcon(app, size) {
    let i;
    const id = app.get_id();
    const sn = symbolicName(app);
    /* SilikVolt's own applications carry the brand's icon (the mark on its ink tile, one ink): shown as it is */
    if (origIcon && (id.startsWith('com.silikvolt.') || id.startsWith('org.silikvolt.')) && app.get_app_info() &&
        app.get_app_info().get_icon()) i = origIcon.call(app, size);
    else if (sn) i = new St.Icon({ icon_name: sn, icon_size: size, style_class: 'silik-app-icon' });
    else i = monogram(app.get_name(), size);
    i.y_align = Clutter.ActorAlign.CENTER;
    return i;
}

function icon(app, size) { return silikIcon(app, size); }

/* A window the shell could not give to an installed program (it shows it under the window's title: "layout1") is
 * listed under the program that owns it when its command line names one: a word of the first arguments (a path's
 * folders and its file name without the extension) that is the command of an installed application. So Magic,
 * started as "wish /usr/lib/magic/tcl/tkcon.tcl ...", and Xschem, whose windows have Tk's class, are "Magic" and
 * "Xschem" in the rail, with their icon. Not for Windows programs: their process number is the sandbox's own. */
const INTERPRETERS = ['sh', 'bash', 'env', 'python', 'python3', 'perl', 'wish', 'tclsh', 'java', 'gjs', 'node', 'bin', 'usr', 'lib',
                      'lib64', 'share', 'opt', 'local', 'tcl', 'home', 'tmp', 'var', 'etc'];
let programs = null;   /* command -> Shell.App, made when first asked for and again when the installed set changes */

function programOf(app) {
    try {
        if (!app.is_window_backed()) return null;
        if (!programs) {
            programs = new Map();
            for (const info of Shell.AppSystem.get_default().get_installed()) {
                const exe = info.get_executable && info.get_executable();
                const a = exe && Shell.AppSystem.get_default().lookup_app(info.get_id());
                const n = exe ? GLib.path_get_basename(exe) : '';
                if (a && n && !INTERPRETERS.includes(n) && !programs.has(n) && info.should_show()) programs.set(n, a);
            }
        }
        const seen = [];
        for (const w of app.get_windows()) {
            if ((w.get_wm_class() || '').toLowerCase().endsWith('.exe')) return null;
            const pid = w.get_pid();
            if (!pid || pid < 2 || seen.includes(pid)) continue;
            seen.push(pid);
            const [ok, bytes] = GLib.file_get_contents('/proc/' + pid + '/cmdline');
            if (!ok) continue;
            const args = [];                               /* the arguments are separated by zero bytes */
            for (let i = 0, from = 0; i <= bytes.length && args.length < 3 && i < 4096; i++) {
                if (i < bytes.length && bytes[i] !== 0) continue;
                const x = i > from && i - from < 300 ? imports.byteArray.toString(bytes.slice(from, i)) : '';
                if (x && !x.startsWith('-')) args.push(x);
                from = i + 1;
            }
            for (const arg of args) {
                const words = arg.split('/').filter(x => x);
                for (const word of [words.pop() || ''].concat(words.reverse())) {       /* the file's name first, then its folders */
                    const n = word.replace(/\.[A-Za-z0-9]{1,4}$/, '');
                    if (n && !INTERPRETERS.includes(n) && programs.has(n)) return programs.get(n);
                }
            }
        }
    } catch (e) { /* a process that has gone, a file that cannot be read: the window keeps its title */ }
    return null;
}

/* the look asked for: the key of the settings, "silik" when the schema is not on this system */
function lookSettings() {
    try {
        const src = Gio.SettingsSchemaSource.get_default();
        return src && src.lookup(SCHEMA, true) ? new Gio.Settings({ schema_id: SCHEMA }) : null;
    } catch (e) { return null; }
}

class SilikShell {
    enable() {
        this._settings = lookSettings();
        if (this._settings) this._lookSig = this._settings.connect('changed::look', () => { this._down(); this._up(); });
        this._up();
    }

    disable() {
        this._down();
        if (this._settings) { this._settings.disconnect(this._lookSig); this._settings = null; }
    }

    /* ---- a look is put up whole and taken down whole */
    _up() {
        this._t = TEXT[lang()];
        this._sigs = [];
        this._moved = [];
        const look = this._settings ? this._settings.get_string('look') : 'silik';
        this._flow = look === 'bar' || look === 'island'
            ? new Flow.FlowLook(look, { t: this._t, icon, mark: markSmall, programOf, toggleStart: () => this._toggleStart(),
                                        closeStart: () => this._closeStart(), command: () => this._command() })
            : null;
        if (this._flow) this._flow.build();
        else { this._title(); this._rail(); this._status(); }
        this._watchLast();
        this._start();
        const on = (o, s, f) => this._sigs.push([o, o.connect(s, f)]);
        on(Main.layoutManager, 'monitors-changed', () => this._layout());
        on(Main.panel, 'notify::height', () => this._layout());
        on(global.display, 'notify::focus-window', () => this._sync());
        on(Shell.AppSystem.get_default(), 'app-state-changed', () => this._sync());
        on(Shell.AppSystem.get_default(), 'installed-changed', () => { programs = null; this._sync(); });
        on(Shell.WindowTracker.get_default(), 'tracked-windows-changed', () => this._sync());
        on(AppFavorites.getAppFavorites(), 'changed', () => this._sync());
        on(global.workspace_manager, 'active-workspace-changed', () => this._syncWs());
        on(global.workspace_manager, 'notify::n-workspaces', () => this._syncWs());
        on(Main.overview, 'showing', () => this._closeStart());
        /* the session opens on the desktop, not on the overview */
        if (Main.layoutManager._startingUp) {
            this._hadOverview = Main.sessionMode.hasOverview;
            Main.sessionMode.hasOverview = false;
            on(Main.layoutManager, 'startup-complete', () => { Main.sessionMode.hasOverview = this._hadOverview; });
        }
        /* the same icons wherever the shell shows an application (window switcher, windows view, search) */
        this._origIcon = origIcon = Shell.App.prototype.create_icon_texture;
        Shell.App.prototype.create_icon_texture = function (size) {
            const i = silikIcon(this, size);
            /* the windows view then puts the window's own picture (a colour picture of another style) into the icon
               it was given: this one keeps what it shows */
            try { Object.defineProperty(i, 'gicon', { get() { return null; }, set() {} }); } catch (e) { /* it stays as it is */ }
            return i;
        };
        /* the rail is the dash; the Super key opens Start (the windows view keeps its key on the rail) */
        this._dash = Main.overview.dash;
        if (this._dash) { this._dash.hide(); this._dash.set_height(0); }
        Main.overview.toggle = () => {
            if (Main.overview.visible) Main.overview.hide();
            else this._toggleStart();
        };
        this._layout();
        this._sync();
        this._syncWs();
        this._syncMsg();
    }

    _down() {
        this._closeStart();
        delete Main.overview.toggle;
        if (this._origIcon) { Shell.App.prototype.create_icon_texture = this._origIcon; this._origIcon = origIcon = null; }
        for (const [o, id] of this._sigs) o.disconnect(id);
        this._sigs = [];
        programs = null;
        if (this._mon) { this._mon.cancel(); this._mon = null; }
        if (this._dash) { this._dash.set_height(-1); this._dash.show(); this._dash = null; }
        if (this._hadOverview !== undefined) Main.sessionMode.hasOverview = this._hadOverview;
        for (const a of [this._catcher, this._startBox]) { Main.layoutManager.removeChrome(a); a.destroy(); }
        if (this._flow) { this._flow.destroy(); this._flow = null; return; }
        for (const a of [this._railBox, this._sb]) { Main.layoutManager.removeChrome(a); a.destroy(); }
        this._mk.destroy(); this._cmd.destroy();
        const dm = Main.panel.statusArea.dateMenu;
        if (dm && this._clockMoved) {
            Main.panel._rightBox.remove_child(dm.container);
            Main.panel._centerBox.add_child(dm.container);
            this._clockMoved = false;
        }
        /* the shell's own keys come back only where the session's mode has them: on the lock screen (where the shell
           turns extensions off) it has just hidden them, and showing them there put "Activities" and the name of the
           focused program on a locked screen */
        const p = Main.sessionMode.panel || {};
        const has = [].concat(p.left || [], p.center || [], p.right || []);
        for (const [k, c] of this._moved) if (has.includes(k)) c.show();
        this._moved = [];
    }

    /* ---- title bar: the mark (Start) and the command line */
    _title() {
        for (const k of ['activities', 'appMenu']) {
            const b = Main.panel.statusArea[k];
            if (!b) continue;
            b.container.hide();
            this._moved.push([k, b.container]);
            this._sigs.push([b.container, b.container.connect('show', c => c.hide())]);   /* the panel shows it again when the session's mode changes */
        }
        this._mk = new St.Button({ style_class: 'silik-mk', reactive: true, track_hover: true, can_focus: true, y_expand: true });
        const mb = new St.BoxLayout({ y_align: Clutter.ActorAlign.CENTER });
        mb.add_child(markSmall());
        mb.add_child(new St.Label({ text: 'SilikOS', style_class: 'silik-mk-name', y_align: Clutter.ActorAlign.CENTER }));
        this._mk.set_child(mb);
        this._mk.connect('clicked', () => this._toggleStart());

        this._cmd = new St.Button({ style_class: 'silik-cmd', reactive: true, track_hover: true, can_focus: true, x_expand: true, y_expand: true });
        const cb = new St.BoxLayout({ x_expand: true, y_align: Clutter.ActorAlign.CENTER });
        cb.add_child(new St.Label({ text: '›', style_class: 'silik-cmd-pr', y_align: Clutter.ActorAlign.CENTER }));
        cb.add_child(new St.Widget({ style_class: 'silik-cmd-cur', y_align: Clutter.ActorAlign.CENTER }));
        cb.add_child(new St.Widget({ x_expand: true }));
        cb.add_child(new St.Label({ text: this._t.hint, style_class: 'silik-cmd-hint', y_align: Clutter.ActorAlign.CENTER }));
        this._cmd.set_child(cb);
        this._cmd.connect('clicked', () => this._command());
        Main.panel._leftBox.insert_child_at_index(this._mk, 0);
        Main.panel._leftBox.insert_child_at_index(this._cmd, 1);

        const dm = Main.panel.statusArea.dateMenu;
        if (dm && dm.container.get_parent() === Main.panel._centerBox) {
            Main.panel._centerBox.remove_child(dm.container);
            Main.panel._rightBox.insert_child_at_index(dm.container, 0);
            this._clockMoved = true;
        }
    }

    /* the COMMAND bar (Super+Space) */
    _command() {
        Main.overview.hide();
        this._closeStart();
        try { GLib.spawn_command_line_async('silik-command'); } catch (e) { Main.notify('SilikOS', String(e.message)); }
    }

    /* ---- rail: the task bar */
    _rail() {
        this._railBox = new St.BoxLayout({ style_class: 'silik-rail', vertical: true, reactive: true });
        this._keys = new St.BoxLayout({ vertical: true });
        this._openT = new St.Label({ text: this._t.open, style_class: 'silik-rail-h' });
        this._open = new St.BoxLayout({ vertical: true });
        this._railBox.add_child(this._keys);
        this._railBox.add_child(this._openT);
        this._railBox.add_child(this._open);
        this._railBox.add_child(new St.Widget({ y_expand: true }));
        this._wsBox = new St.BoxLayout({ style_class: 'silik-ws' });
        this._railBox.add_child(this._wsBox);
        const wins = this._key('', null, this._t.windows);
        wins.connect('clicked', () => {
            this._closeStart();
            if (Main.overview.visible) Main.overview.hide(); else Main.overview.show();
        });
        this._railBox.add_child(wins);
        Main.layoutManager.addChrome(this._railBox, { affectsStruts: true, trackFullscreen: true });
    }

    _key(digit, app, name) {
        const b = new St.Button({ style_class: 'silik-key', reactive: true, track_hover: true, can_focus: true, x_expand: true,
                                  button_mask: St.ButtonMask.ONE | St.ButtonMask.TWO });
        const box = new St.BoxLayout({ x_expand: true });
        box.add_child(new St.Widget({ style_class: 'silik-key-edge', y_align: Clutter.ActorAlign.CENTER }));   /* ink when it runs */
        box.add_child(new St.Label({ text: digit, style_class: 'silik-key-n', y_align: Clutter.ActorAlign.CENTER }));
        if (app) box.add_child(icon(app, 16));
        box.add_child(new St.Label({ text: name, style_class: app ? 'silik-key-t' : 'silik-key-t silik-key-plain', x_expand: true,
                                     y_align: Clutter.ActorAlign.CENTER }));
        b.set_child(box);
        return b;
    }

    _appKeys(box, app, digit, focusApp, focusWin) {
        const run = app.state !== Shell.AppState.STOPPED;
        const as = programOf(app) || app;                  /* the name and icon of the program behind a nameless window */
        const b = this._key(digit, as, as.get_name());
        if (run) b.add_style_class_name('silik-run');
        if (focusApp === app) b.add_style_class_name('silik-on');
        b.connect('clicked', (w, button) => {
            Main.overview.hide();
            if (run && button !== 2) app.activate();
            else app.open_new_window(-1);
        });
        box.add_child(b);
        const wins = app.get_windows().filter(w => !w.is_skip_taskbar());
        if (wins.length < 2) return;
        for (const w of wins) {            /* several windows: each one is a key below the application's */
            const wb = new St.Button({ style_class: 'silik-win', reactive: true, track_hover: true, can_focus: true, x_expand: true });
            wb.set_child(new St.Label({ text: w.get_title() || '', x_expand: true, y_align: Clutter.ActorAlign.CENTER }));
            if (w === focusWin) wb.add_style_class_name('silik-on');
            wb.connect('clicked', () => { Main.overview.hide(); Main.activateWindow(w); });
            box.add_child(wb);
        }
    }

    _sync() {
        if (this._flow) { this._flow.sync(); return; }
        const fav = AppFavorites.getAppFavorites().getFavorites();
        const focusApp = Shell.WindowTracker.get_default().focus_app;
        const focusWin = global.display.focus_window;
        this._keys.destroy_all_children();
        this._open.destroy_all_children();
        fav.forEach((app, i) => this._appKeys(this._keys, app, i < 9 ? String(i + 1) : '', focusApp, focusWin));
        const ids = fav.map(a => a.get_id());
        const others = Shell.AppSystem.get_default().get_running()
            .filter(a => !ids.includes(a.get_id()) && a.get_id() !== COMMAND_ID &&
                         a.get_windows().some(w => !w.is_skip_taskbar() && w.get_wm_class_instance() !== 'silik-command'));
        for (const app of others) this._appKeys(this._open, app, '', focusApp, focusWin);
        this._openT.visible = others.length > 0;
    }

    _syncWs() {
        if (this._flow) { this._flow.syncWs(); return; }
        const wm = global.workspace_manager;
        const n = wm.get_n_workspaces(), cur = wm.get_active_workspace_index();
        this._wsBox.destroy_all_children();
        for (let i = 0; i < n; i++) {
            const b = new St.Button({ style_class: 'silik-ws-cell', label: String(i + 1), reactive: true, track_hover: true, can_focus: true });
            if (i === cur) b.add_style_class_name('silik-on');
            b.connect('clicked', () => wm.get_workspace_by_index(i).activate(global.get_current_time()));
            this._wsBox.add_child(b);
        }
        if (this._ws) this._ws.text = (cur + 1) + '/' + n;
    }

    /* ---- Start: a pane hanging from the mark (Silik), or standing on the piece at the bottom (Flow) */
    _start() {
        const t = this._t, flow = this._flow;
        this._catcher = new St.Widget({ reactive: true, visible: false });
        this._catcher.connect('button-press-event', () => { this._closeStart(); return Clutter.EVENT_STOP; });
        this._startBox = new St.BoxLayout({ style_class: flow ? 'silik-start silik-start-flow silik-start-' + flow.kind : 'silik-start',
                                            vertical: true, reactive: true, visible: false });
        const head = new St.BoxLayout({ style_class: 'silik-start-head' });
        head.add_child(new St.Label({ text: '›', style_class: 'silik-start-pr', y_align: Clutter.ActorAlign.CENTER }));
        this._entry = new St.Entry({ style_class: 'silik-start-entry', hint_text: flow ? t.search : t.filter, x_expand: true, can_focus: true,
                                     y_align: Clutter.ActorAlign.CENTER });
        head.add_child(this._entry);
        this._startBox.add_child(head);
        if (flow) this._startHome();
        const body = this._body = new St.BoxLayout({ y_expand: true });
        this._cats = new St.BoxLayout({ style_class: 'silik-start-cats', vertical: true, x_expand: false });
        body.add_child(this._cats);
        this._scroll = new St.ScrollView({ style_class: 'silik-start-scroll', x_expand: true, y_expand: true,
                                           hscrollbar_policy: St.PolicyType.NEVER, vscrollbar_policy: St.PolicyType.AUTOMATIC,
                                           overlay_scrollbars: true });
        this._list = new St.BoxLayout({ vertical: true });
        this._scroll.add_actor(this._list);
        body.add_child(this._scroll);
        this._startBox.add_child(body);
        const foot = new St.BoxLayout({ style_class: 'silik-start-foot' });
        if (flow) {
            /* who is at the machine, and the session's keys: each one is a command of `silik` */
            const who = GLib.get_real_name();
            foot.add_child(new St.Label({ text: who && who !== 'Unknown' ? who : GLib.get_user_name(), style_class: 'silik-start-user',
                                          x_expand: true, y_align: Clutter.ActorAlign.CENTER }));
            for (const k of ['lock', 'logout', 'off']) {
                const b = new St.Button({ style_class: 'silik-start-sk', label: t[k], reactive: true, track_hover: true, can_focus: true,
                                          y_align: Clutter.ActorAlign.CENTER });
                b.connect('clicked', () => this._session(k));
                foot.add_child(b);
            }
        } else {
            const kv = (k, v) => {
                const b = new St.BoxLayout({ style_class: 'silik-start-kv' });
                b.add_child(new St.Label({ text: k, style_class: 'silik-start-k' }));
                b.add_child(new St.Label({ text: v }));
                foot.add_child(b);
            };
            kv('Enter', t.kOpen); kv('↑↓', t.kMove); kv('Tab', t.kCat); kv('Esc', t.kClose);
        }
        this._startBox.add_child(foot);
        Main.layoutManager.addChrome(this._catcher);
        Main.layoutManager.addChrome(this._startBox);
        this._entry.clutter_text.connect('text-changed', () => { this._sel = 0; this._fill(); });
        this._entry.clutter_text.connect('key-press-event', (o, ev) => this._startKey(ev));
        this._cat = 'all';
        this._sel = 0;
        this._view = 'home';
    }

    /* Start's first page in a Flow look: the rail's applications as a grid, digit first (Super+digit opens them), and
       the files used last (the desktop's own list of recent files); typing, Tab or the key on the right lists everything */
    _startHome() {
        const t = this._t;
        this._home = new St.BoxLayout({ style_class: 'silik-home', vertical: true, y_expand: true });
        const h = new St.BoxLayout({ style_class: 'silik-home-h' });
        h.add_child(new St.Label({ text: t.pinned, x_expand: true, y_align: Clutter.ActorAlign.CENTER }));
        const all = new St.Button({ style_class: 'silik-home-all', label: t.all + ' ›', reactive: true, track_hover: true });
        all.connect('clicked', () => { this._view = 'all'; this._sel = 0; this._fill(); this._entry.grab_key_focus(); });
        h.add_child(all);
        this._home.add_child(h);
        this._pins = new St.Widget({ style_class: 'silik-pins', layout_manager: new Clutter.GridLayout({ column_homogeneous: true }),
                                     x_expand: true });
        this._pins.y_expand = true;                 /* said twice: only a changed value stops the cells' own wish to grow */
        this._pins.y_expand = false;                /* from reaching the grid, which would take the whole page */
        this._home.add_child(this._pins);
        this._recT = new St.Label({ text: t.recent, style_class: 'silik-home-h' });
        this._home.add_child(this._recT);
        this._recs = new St.BoxLayout({ style_class: 'silik-recs', vertical: true });
        this._home.add_child(this._recs);
        this._startBox.add_child(this._home);
    }

    _recentFiles() {
        try {
            const home = GLib.get_home_dir();
            return Gtk.RecentManager.get_default().get_items()
                .filter(i => i.is_local() && !i.get_private_hint() && i.exists())
                .sort((a, b) => b.get_modified() - a.get_modified()).slice(0, RECENT_N)
                .map(i => {
                    const dir = GLib.path_get_dirname(i.get_uri_display() || '');
                    return { uri: i.get_uri(), name: i.get_display_name(), gicon: i.get_gicon(),
                             dir: dir === home ? '~' : dir.startsWith(home + '/') ? '~' + dir.slice(home.length) : dir };
                });
        } catch (e) { return []; }
    }

    _fillHome() {
        this._pins.destroy_all_children();
        this._recs.destroy_all_children();
        this._homeKeys = [];
        const grid = this._pins.layout_manager;
        const favs = AppFavorites.getAppFavorites().getFavorites().slice(0, 3 * PIN_COLS);
        favs.forEach((app, i) => {
            const as = programOf(app) || app;
            const b = new St.Button({ style_class: 'silik-pin', reactive: true, track_hover: true, x_expand: true });
            const w = new St.Widget({ layout_manager: new Clutter.BinLayout(), x_expand: true, y_expand: true });
            w.add_child(new St.Label({ text: i < 9 ? String(i + 1) : '', style_class: 'silik-pin-n', x_expand: true, y_expand: true,
                                       x_align: Clutter.ActorAlign.START, y_align: Clutter.ActorAlign.START }));
            const col = new St.BoxLayout({ vertical: true, style_class: 'silik-pin-box', x_expand: true, y_expand: true,
                                           x_align: Clutter.ActorAlign.CENTER, y_align: Clutter.ActorAlign.CENTER });
            const ic = icon(as, 28);
            ic.x_align = Clutter.ActorAlign.CENTER;
            col.add_child(ic);
            col.add_child(new St.Label({ text: as.get_name(), style_class: 'silik-pin-t', x_align: Clutter.ActorAlign.CENTER }));
            w.add_child(col);
            b.set_child(w);
            b.connect('clicked', () => this._launch(app));
            grid.attach(b, i % PIN_COLS, Math.floor(i / PIN_COLS), 1, 1);
            this._homeKeys.push({ b, go: () => this._launch(app) });
        });
        for (let i = favs.length; i % PIN_COLS; i++)       /* the row is ruled to its end */
            grid.attach(new St.Widget({ style_class: 'silik-pin silik-pin-none', x_expand: true }), i % PIN_COLS, Math.floor(i / PIN_COLS), 1, 1);
        this._nPins = favs.length;
        const files = this._recentFiles();
        this._recT.visible = files.length > 0;
        for (const f of files) {
            const b = new St.Button({ style_class: 'silik-rec', reactive: true, track_hover: true, x_expand: true });
            const box = new St.BoxLayout({ x_expand: true });
            if (f.gicon) box.add_child(new St.Icon({ gicon: f.gicon, icon_size: 16, y_align: Clutter.ActorAlign.CENTER }));
            box.add_child(new St.Label({ text: f.name, style_class: 'silik-rec-name', y_align: Clutter.ActorAlign.CENTER }));
            box.add_child(new St.Label({ text: f.dir, style_class: 'silik-rec-dir', x_expand: true, y_align: Clutter.ActorAlign.CENTER }));
            b.set_child(box);
            const go = () => {
                this._closeStart();
                try { Gio.AppInfo.launch_default_for_uri(f.uri, global.create_app_launch_context(0, -1)); }
                catch (e) { Main.notify('SilikOS', String(e.message)); }
            };
            b.connect('clicked', go);
            this._recs.add_child(b);
            this._homeKeys.push({ b, go });
        }
        if (this._sel >= this._homeKeys.length) this._sel = Math.max(0, this._homeKeys.length - 1);
        if (this._homeKeys.length) this._homeKeys[this._sel].b.add_style_class_name('silik-on');
    }

    /* the grid's keys: left and right along the applications, up and down by rows, then down the files */
    _moveHome(dx, dy) {
        const n = this._homeKeys.length, p = this._nPins;
        if (!n) return;
        let i = this._sel;
        if (dx) i = i < p ? Math.max(0, Math.min(p - 1, i + dx)) : i;
        else if (dy > 0) i = i >= p ? Math.min(n - 1, i + 1) : i + PIN_COLS < p ? i + PIN_COLS       /* the cell below, or the last */
            : Math.floor(i / PIN_COLS) < Math.floor((p - 1) / PIN_COLS) ? p - 1 : Math.min(n - 1, p);   /* of a short row, or the files */
        else if (dy < 0) i = i < p ? (i - PIN_COLS >= 0 ? i - PIN_COLS : i) : (i > p ? i - 1 : Math.max(0, p - 1 - (p - 1) % PIN_COLS));
        this._homeKeys[this._sel].b.remove_style_class_name('silik-on');
        this._sel = Math.max(0, Math.min(n - 1, i));
        this._homeKeys[this._sel].b.add_style_class_name('silik-on');
    }

    _session(what) {
        this._closeStart();
        try { GLib.spawn_command_line_async('silik session ' + what); } catch (e) { Main.notify('SilikOS', String(e.message)); }
    }

    _toggleStart() {
        if (this._startOpen) this._closeStart(); else this._openStart();
    }

    _openStart() {
        if (this._startOpen) return;
        const sys = Shell.AppSystem.get_default();
        this._apps = Gio.AppInfo.get_all().filter(i => i.should_show()).map(i => sys.lookup_app(i.get_id())).filter(a => a)
            .map(a => ({ app: a, name: a.get_name() || '', desc: a.get_description() || '', cat: category(a) }));
        this._apps.sort((a, b) => a.name.localeCompare(b.name));
        this._favIds = AppFavorites.getAppFavorites().getFavorites().map(a => a.get_id());
        this._cat = 'all';
        this._sel = 0;
        this._view = 'home';
        this._entry.set_text('');
        this._fillCats();
        this._fill();
        this._layout();
        this._catcher.show();
        this._startBox.show();
        this._markOn(true);
        if (!Main.pushModal(this._startBox, { actionMode: Shell.ActionMode.POPUP })) {
            this._catcher.hide(); this._startBox.hide(); this._markOn(false);
            return;
        }
        this._startOpen = true;
        this._entry.grab_key_focus();
    }

    _closeStart() {
        if (!this._startOpen) return;
        this._startOpen = false;
        Main.popModal(this._startBox);
        this._catcher.hide();
        this._startBox.hide();
        this._markOn(false);
    }

    _markOn(on) {
        if (this._flow) this._flow.markOn(on);
        else if (on) this._mk.add_style_class_name('silik-on');
        else this._mk.remove_style_class_name('silik-on');
    }

    /* a Flow look's Start is on its first page until one types or asks for everything */
    _atHome() {
        return !!this._flow && this._view === 'home' && !this._entry.get_text().trim();
    }

    _catList() {
        const have = new Set(this._apps.map(a => a.cat));
        return ['all', 'fav'].concat(['eda', 'win', 'dev', 'office', 'graphics', 'net', 'media', 'tools', 'system', 'other'].filter(k => have.has(k)));
    }

    _fillCats() {
        this._cats.destroy_all_children();
        for (const k of this._catList()) {
            const b = new St.Button({ style_class: 'silik-start-cat', label: this._t.cats[k], reactive: true, track_hover: true,
                                      x_align: Clutter.ActorAlign.FILL });
            b.get_child().x_align = Clutter.ActorAlign.START;
            if (k === this._cat) b.add_style_class_name('silik-on');
            b.connect('clicked', () => { this._cat = k; this._sel = 0; this._fillCats(); this._fill(); this._entry.grab_key_focus(); });
            this._cats.add_child(b);
        }
    }

    _fill() {
        if (this._flow) {
            const home = this._atHome();
            this._home.visible = home;
            this._body.visible = !home;
            if (home) { this._fillHome(); this._layout(); return; }
            this._layout();
        }
        const q = this._entry.get_text().trim().toLowerCase();
        this._shown = this._apps.filter(a =>
            (this._cat === 'all' || (this._cat === 'fav' ? this._favIds.includes(a.app.get_id()) : a.cat === this._cat)) &&
            (!q || a.name.toLowerCase().includes(q) || a.desc.toLowerCase().includes(q)));
        if (this._sel >= this._shown.length) this._sel = Math.max(0, this._shown.length - 1);
        this._list.destroy_all_children();
        this._rows = [];
        this._shown.forEach((a, i) => {
            const b = new St.Button({ style_class: 'silik-start-row', reactive: true, track_hover: true, x_expand: true });
            const box = new St.BoxLayout({ x_expand: true });
            box.add_child(icon(a.app, 16));
            box.add_child(new St.Label({ text: a.name, style_class: 'silik-start-name', y_align: Clutter.ActorAlign.CENTER }));
            box.add_child(new St.Label({ text: a.desc, style_class: 'silik-start-desc', x_expand: true, y_align: Clutter.ActorAlign.CENTER }));
            b.set_child(box);
            if (i === this._sel) b.add_style_class_name('silik-on');
            b.connect('clicked', () => this._launch(a.app));
            this._list.add_child(b);
            this._rows.push(b);
        });
        if (!this._shown.length) this._list.add_child(new St.Label({ text: this._t.none, style_class: 'silik-start-none' }));
    }

    _move(d) {
        if (!this._rows.length) return;
        this._rows[this._sel].remove_style_class_name('silik-on');
        this._sel = Math.max(0, Math.min(this._rows.length - 1, this._sel + d));
        this._rows[this._sel].add_style_class_name('silik-on');
        Util.ensureActorVisibleInScrollView(this._scroll, this._rows[this._sel]);
    }

    _startKey(ev) {
        const k = ev.get_key_symbol();
        if (this._atHome()) {
            if (k === Clutter.KEY_Escape) { this._closeStart(); return Clutter.EVENT_STOP; }
            if (k === Clutter.KEY_Right) { this._moveHome(1, 0); return Clutter.EVENT_STOP; }
            if (k === Clutter.KEY_Left) { this._moveHome(-1, 0); return Clutter.EVENT_STOP; }
            if (k === Clutter.KEY_Down) { this._moveHome(0, 1); return Clutter.EVENT_STOP; }
            if (k === Clutter.KEY_Up) { this._moveHome(0, -1); return Clutter.EVENT_STOP; }
            if (k === Clutter.KEY_Return || k === Clutter.KEY_KP_Enter) {
                if (this._homeKeys.length) this._homeKeys[this._sel].go();
                return Clutter.EVENT_STOP;
            }
            if (k === Clutter.KEY_Tab || k === Clutter.KEY_ISO_Left_Tab) {
                this._view = 'all'; this._sel = 0; this._fillCats(); this._fill();
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        }
        if (k === Clutter.KEY_Escape) {
            if (this._flow) {                               /* back to the first page; Esc there closes */
                this._view = 'home'; this._cat = 'all'; this._sel = 0;
                if (this._entry.get_text()) this._entry.set_text(''); else { this._fillCats(); this._fill(); }
            } else {
                this._closeStart();
            }
            return Clutter.EVENT_STOP;
        }
        if (k === Clutter.KEY_Down) { this._move(1); return Clutter.EVENT_STOP; }
        if (k === Clutter.KEY_Up) { this._move(-1); return Clutter.EVENT_STOP; }
        if (k === Clutter.KEY_Page_Down) { this._move(10); return Clutter.EVENT_STOP; }
        if (k === Clutter.KEY_Page_Up) { this._move(-10); return Clutter.EVENT_STOP; }
        if (k === Clutter.KEY_Return || k === Clutter.KEY_KP_Enter) {
            if (this._shown.length) this._launch(this._shown[this._sel].app);
            return Clutter.EVENT_STOP;
        }
        if (k === Clutter.KEY_Tab || k === Clutter.KEY_ISO_Left_Tab) {
            const cs = this._catList();
            const d = k === Clutter.KEY_Tab && !(ev.get_state() & Clutter.ModifierType.SHIFT_MASK) ? 1 : -1;
            this._cat = cs[(cs.indexOf(this._cat) + d + cs.length) % cs.length];
            this._sel = 0;
            this._fillCats();
            this._fill();
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _launch(app) {
        this._closeStart();
        if (app.state !== Shell.AppState.STOPPED) app.activate(); else app.open_new_window(-1);
    }

    /* ---- status bar */
    _status() {
        const t = this._t;
        this._sb = new St.BoxLayout({ style_class: 'silik-sb', reactive: true });
        const msg = new St.BoxLayout({ style_class: 'silik-f silik-msg', x_expand: true });
        this._msgT = new St.Label({ style_class: 'silik-k', y_align: Clutter.ActorAlign.CENTER });
        this._msgX = new St.Label({ style_class: 'silik-v', y_align: Clutter.ActorAlign.CENTER, x_expand: true });
        msg.add_child(this._msgT);
        msg.add_child(this._msgX);
        this._sb.add_child(msg);
        const field = (k, v) => {
            const f = new St.BoxLayout({ style_class: 'silik-f' });
            f.add_child(new St.Label({ text: k, style_class: 'silik-k', y_align: Clutter.ActorAlign.CENTER }));
            const val = new St.Label({ text: v, style_class: 'silik-v', y_align: Clutter.ActorAlign.CENTER });
            f.add_child(val);
            this._sb.add_child(f);
            return val;
        };
        this._ws = field(t.ws, '');
        const os = osRelease();
        const el = (os.PLATFORM_ID || '').replace(/^platform:/, '').replace(/[0-9]+$/, '').toUpperCase();
        if (el && os.VERSION_ID) field(t.base, el + ' ' + os.VERSION_ID);
        const k = readText('/proc/sys/kernel/osrelease');
        if (k) field(t.kernel, k);
        field(t.host, GLib.get_host_name());
        Main.layoutManager.addChrome(this._sb, { affectsStruts: true, trackFullscreen: true });
    }

    /* the last command `silik` ran: the status bar's message, or the command field of the bar */
    _watchLast() {
        this._last = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_runtime_dir(), 'silik-last']));
        try {
            this._mon = this._last.monitor_file(Gio.FileMonitorFlags.NONE, null);
            this._mon.connect('changed', () => this._syncMsg());
        } catch (e) { this._mon = null; }
    }

    _syncMsg() {
        const s = readText(this._last.get_path());
        if (this._flow) { this._flow.syncMsg(s); return; }
        const i = s.indexOf(' ');
        if (s && i > 0) { this._msgT.text = s.slice(0, i); this._msgX.text = s.slice(i + 1).split('\n')[0]; }
        else { this._msgT.text = ''; this._msgX.text = this._t.ready; }
    }

    _layout() {
        const m = Main.layoutManager.primaryMonitor;
        if (!m) return;
        const s = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        this._catcher.set_position(m.x, m.y);
        this._catcher.set_size(m.width, m.height);
        if (this._flow) {
            this._flow.layout();
            /* Start's first page is as tall as what it holds (few pinned applications and no recent file leave no
               empty paper); the list of everything keeps the full height, so it does not jump while one types */
            let fh = FLOW_H * s;
            if (this._atHome()) {
                this._startBox.set_height(-1);
                const [, nat] = this._startBox.get_preferred_height(Math.min(FLOW_W * s, m.width));
                if (nat > 0) fh = Math.min(fh, nat);
            }
            const [x, y, w, h] = this._flow.startPlace(FLOW_W * s, fh);
            this._startBox.set_position(x, y);
            this._startBox.set_size(w, h);
            return;
        }
        const ph = Main.layoutManager.panelBox.height, sb = SB_H * s, rw = RAIL_W * s;
        this._sb.set_position(m.x, m.y + m.height - sb);
        this._sb.set_size(m.width, sb);
        this._railBox.set_position(m.x, m.y + ph);
        this._railBox.set_size(rw, m.height - ph - sb);
        this._startBox.set_position(m.x + rw - s, m.y + ph);
        this._startBox.set_size(Math.min(START_W * s, m.width - rw), Math.min(START_H * s, m.height - ph - sb));
    }
}

function init() { return new SilikShell(); }
