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
 * Nothing here runs a system action: the keys open applications and windows, every action stays in `silik`. */
'use strict';

const { Clutter, Gio, GLib, Meta, Shell, St } = imports.gi;
const Main = imports.ui.main;
const AppFavorites = imports.ui.appFavorites;
const Util = imports.misc.util;

const RAIL_W = 152, SB_H = 22, START_W = 660, START_H = 520;
const COMMAND_ID = 'org.silikvolt.Command.desktop';   /* the COMMAND bar is the title bar's command line, not a rail key */

const TEXT = {
    en: { ready: 'ready', ws: 'workspace', base: 'base', kernel: 'kernel', host: 'host', open: 'open', windows: 'Windows',
          filter: 'type to filter', kOpen: 'open', kMove: 'move', kCat: 'category', kClose: 'close', none: 'nothing matches',
          cats: { all: 'All', fav: 'Rail', eda: 'Engineering', win: 'Windows programs', dev: 'Development', office: 'Office',
                  graphics: 'Graphics', net: 'Internet', media: 'Sound and video', tools: 'Tools', system: 'System', other: 'Other' } },
    ca: { ready: 'a punt', ws: 'espai', base: 'base', kernel: 'nucli', host: 'equip', open: 'obertes', windows: 'Finestres',
          filter: 'escriu per filtrar', kOpen: 'obre', kMove: 'mou', kCat: 'categoria', kClose: 'tanca', none: 'no hi ha res que coincideixi',
          cats: { all: 'Totes', fav: 'Rail', eda: 'Enginyeria', win: 'Programes de Windows', dev: 'Desenvolupament', office: 'Oficina',
                  graphics: 'Gràfics', net: 'Internet', media: 'So i vídeo', tools: 'Eines', system: 'Sistema', other: 'Altres' } },
    es: { ready: 'listo', ws: 'espacio', base: 'base', kernel: 'núcleo', host: 'equipo', open: 'abiertas', windows: 'Ventanas',
          filter: 'escribe para filtrar', kOpen: 'abre', kMove: 'mueve', kCat: 'categoría', kClose: 'cierra', none: 'nada coincide',
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

function icon(app, size) {
    const i = app.create_icon_texture(size);
    i.add_effect(new Clutter.DesaturateEffect({ factor: 1.0 }));   /* one ink: colour is kept for data */
    i.y_align = Clutter.ActorAlign.CENTER;
    return i;
}

class SilikShell {
    enable() {
        this._t = TEXT[lang()];
        this._sigs = [];
        this._moved = [];
        this._title();
        this._rail();
        this._status();
        this._start();
        const on = (o, s, f) => this._sigs.push([o, o.connect(s, f)]);
        on(Main.layoutManager, 'monitors-changed', () => this._layout());
        on(Main.panel, 'notify::height', () => this._layout());
        on(global.display, 'notify::focus-window', () => this._sync());
        on(Shell.AppSystem.get_default(), 'app-state-changed', () => this._sync());
        on(Shell.AppSystem.get_default(), 'installed-changed', () => this._sync());
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
    }

    disable() {
        this._closeStart();
        delete Main.overview.toggle;
        for (const [o, id] of this._sigs) o.disconnect(id);
        this._sigs = [];
        if (this._mon) { this._mon.cancel(); this._mon = null; }
        if (this._dash) { this._dash.set_height(-1); this._dash.show(); this._dash = null; }
        if (this._hadOverview !== undefined) Main.sessionMode.hasOverview = this._hadOverview;
        for (const a of [this._railBox, this._sb, this._catcher, this._startBox]) { Main.layoutManager.removeChrome(a); a.destroy(); }
        this._mk.destroy(); this._cmd.destroy();
        const dm = Main.panel.statusArea.dateMenu;
        if (dm && this._clockMoved) {
            Main.panel._rightBox.remove_child(dm.container);
            Main.panel._centerBox.add_child(dm.container);
        }
        for (const a of this._moved) a.show();
        this._moved = [];
    }

    /* ---- title bar: the mark (Start) and the command line */
    _title() {
        for (const k of ['activities', 'appMenu']) {
            const b = Main.panel.statusArea[k];
            if (b && b.container.visible) { b.container.hide(); this._moved.push(b.container); }
        }
        this._mk = new St.Button({ style_class: 'silik-mk', reactive: true, track_hover: true, can_focus: true, y_expand: true });
        const mb = new St.BoxLayout({ y_align: Clutter.ActorAlign.CENTER });
        const f = Gio.File.new_for_path('/usr/share/pixmaps/silikos-mark-light.svg');
        const fd = Gio.File.new_for_path('/usr/share/pixmaps/silikos-mark.svg');
        this._mkLight = f.query_exists(null) ? new Gio.FileIcon({ file: f }) : null;
        this._mkDark = fd.query_exists(null) ? new Gio.FileIcon({ file: fd }) : this._mkLight;
        this._mkIcon = this._mkLight ? new St.Icon({ gicon: this._mkLight, style_class: 'silik-mk-icon' }) : null;
        if (this._mkIcon) mb.add_child(this._mkIcon);
        mb.add_child(new St.Label({ text: 'SilikOS', style_class: 'silik-mk-name', y_align: Clutter.ActorAlign.CENTER }));
        this._mk.set_child(mb);
        this._mk.connect('clicked', () => this._toggleStart());

        this._cmd = new St.Button({ style_class: 'silik-cmd', reactive: true, track_hover: true, can_focus: true, x_expand: true, y_expand: true });
        const cb = new St.BoxLayout({ x_expand: true, y_align: Clutter.ActorAlign.CENTER });
        cb.add_child(new St.Label({ text: '›', style_class: 'silik-cmd-pr', y_align: Clutter.ActorAlign.CENTER }));
        cb.add_child(new St.Widget({ style_class: 'silik-cmd-cur', y_align: Clutter.ActorAlign.CENTER }));
        cb.add_child(new St.Widget({ x_expand: true }));
        cb.add_child(new St.Label({ text: 'Super+Space', style_class: 'silik-cmd-hint', y_align: Clutter.ActorAlign.CENTER }));
        this._cmd.set_child(cb);
        this._cmd.connect('clicked', () => {
            Main.overview.hide();
            this._closeStart();
            try { GLib.spawn_command_line_async('silik-command'); } catch (e) { Main.notify('SilikOS', String(e.message)); }
        });
        Main.panel._leftBox.insert_child_at_index(this._mk, 0);
        Main.panel._leftBox.insert_child_at_index(this._cmd, 1);

        const dm = Main.panel.statusArea.dateMenu;
        if (dm && dm.container.get_parent() === Main.panel._centerBox) {
            Main.panel._centerBox.remove_child(dm.container);
            Main.panel._rightBox.insert_child_at_index(dm.container, 0);
            this._clockMoved = true;
        }
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
        const b = this._key(digit, app, app.get_name());
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

    /* ---- Start: a pane hanging from the mark */
    _start() {
        const t = this._t;
        this._catcher = new St.Widget({ reactive: true, visible: false });
        this._catcher.connect('button-press-event', () => { this._closeStart(); return Clutter.EVENT_STOP; });
        this._startBox = new St.BoxLayout({ style_class: 'silik-start', vertical: true, reactive: true, visible: false });
        const head = new St.BoxLayout({ style_class: 'silik-start-head' });
        head.add_child(new St.Label({ text: '›', style_class: 'silik-start-pr', y_align: Clutter.ActorAlign.CENTER }));
        this._entry = new St.Entry({ style_class: 'silik-start-entry', hint_text: t.filter, x_expand: true, can_focus: true,
                                     y_align: Clutter.ActorAlign.CENTER });
        head.add_child(this._entry);
        this._startBox.add_child(head);
        const body = new St.BoxLayout({ y_expand: true });
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
        const kv = (k, v) => {
            const b = new St.BoxLayout({ style_class: 'silik-start-kv' });
            b.add_child(new St.Label({ text: k, style_class: 'silik-start-k' }));
            b.add_child(new St.Label({ text: v }));
            foot.add_child(b);
        };
        kv('Enter', t.kOpen); kv('↑↓', t.kMove); kv('Tab', t.kCat); kv('Esc', t.kClose);
        this._startBox.add_child(foot);
        Main.layoutManager.addChrome(this._catcher);
        Main.layoutManager.addChrome(this._startBox);
        this._entry.clutter_text.connect('text-changed', () => { this._sel = 0; this._fill(); });
        this._entry.clutter_text.connect('key-press-event', (o, ev) => this._startKey(ev));
        this._cat = 'all';
        this._sel = 0;
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
        this._entry.set_text('');
        this._fillCats();
        this._fill();
        this._layout();
        this._catcher.show();
        this._startBox.show();
        this._mk.add_style_class_name('silik-on');
        if (this._mkIcon) this._mkIcon.gicon = this._mkDark;      /* the open key is inverse video */
        if (!Main.pushModal(this._startBox, { actionMode: Shell.ActionMode.POPUP })) {
            this._catcher.hide(); this._startBox.hide(); this._mk.remove_style_class_name('silik-on');
            if (this._mkIcon) this._mkIcon.gicon = this._mkLight;
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
        this._mk.remove_style_class_name('silik-on');
        if (this._mkIcon) this._mkIcon.gicon = this._mkLight;
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
        if (k === Clutter.KEY_Escape) { this._closeStart(); return Clutter.EVENT_STOP; }
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

        /* the last command `silik` ran */
        this._last = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_runtime_dir(), 'silik-last']));
        try {
            this._mon = this._last.monitor_file(Gio.FileMonitorFlags.NONE, null);
            this._mon.connect('changed', () => this._syncMsg());
        } catch (e) { this._mon = null; }
        this._syncMsg();
    }

    _syncMsg() {
        const s = readText(this._last.get_path());
        const i = s.indexOf(' ');
        if (s && i > 0) { this._msgT.text = s.slice(0, i); this._msgX.text = s.slice(i + 1).split('\n')[0]; }
        else { this._msgT.text = ''; this._msgX.text = this._t.ready; }
    }

    _layout() {
        const m = Main.layoutManager.primaryMonitor;
        if (!m) return;
        const s = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        const ph = Main.layoutManager.panelBox.height, sb = SB_H * s, rw = RAIL_W * s;
        this._sb.set_position(m.x, m.y + m.height - sb);
        this._sb.set_size(m.width, sb);
        this._railBox.set_position(m.x, m.y + ph);
        this._railBox.set_size(rw, m.height - ph - sb);
        this._catcher.set_position(m.x, m.y);
        this._catcher.set_size(m.width, m.height);
        this._startBox.set_position(m.x + rw - s, m.y + ph);
        this._startBox.set_size(Math.min(START_W * s, m.width - rw), Math.min(START_H * s, m.height - ph - sb));
    }
}

function init() { return new SilikShell(); }
