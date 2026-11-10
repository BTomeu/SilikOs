/* SilikOS shell — the Silik layout on GNOME Shell (the same three parts as SilikStudio's window):
 *   title bar   the mark, then the command line (a key that opens the COMMAND bar, Super+Space), clock and system menu
 *   rail        text keys, digit first: the favourites (Super+1..9 open them), then the other open applications;
 *               the focused one is inverse video, a running one carries a square
 *   status bar  the one message channel (the last command `silik` ran, read from $XDG_RUNTIME_DIR/silik-last), then
 *               "key value" fields: workspace, base, kernel, host
 * Nothing here runs a system action: the keys open applications, every action stays in `silik`. */
'use strict';

const { Clutter, Gio, GLib, Meta, Shell, St } = imports.gi;
const Main = imports.ui.main;
const AppFavorites = imports.ui.appFavorites;
const ExtensionUtils = imports.misc.extensionUtils;

const RAIL_W = 124, SB_H = 22;
const COMMAND_ID = 'org.silikvolt.Command.desktop';   /* the COMMAND bar is the title bar's command line, not a rail key */

const TEXT = {
    en: { apps: 'Applications', ready: 'ready', ws: 'workspace', base: 'base', kernel: 'kernel', host: 'host', cmd: 'command' },
    ca: { apps: 'Aplicacions', ready: 'a punt', ws: 'espai', base: 'base', kernel: 'nucli', host: 'equip', cmd: 'comanda' },
    es: { apps: 'Aplicaciones', ready: 'listo', ws: 'espacio', base: 'base', kernel: 'núcleo', host: 'equipo', cmd: 'comando' },
};

function lang() {
    for (const l of GLib.get_language_names()) {
        const k = l.slice(0, 2).toLowerCase();
        if (TEXT[k]) return k;
    }
    return 'en';
}

function osRelease() {
    const o = {};
    try {
        const [ok, bytes] = GLib.file_get_contents('/etc/os-release');
        if (ok) {
            for (const line of imports.byteArray.toString(bytes).split('\n')) {
                const m = line.match(/^([A-Z_]+)=(.*)$/);
                if (m) o[m[1]] = m[2].replace(/^"|"$/g, '');
            }
        }
    } catch (e) { }
    return o;
}

function readText(path) {
    try {
        const [ok, bytes] = GLib.file_get_contents(path);
        return ok ? imports.byteArray.toString(bytes).trim() : '';
    } catch (e) { return ''; }
}

class SilikShell {
    enable() {
        this._t = TEXT[lang()];
        this._sigs = [];
        this._moved = [];
        this._title();
        this._rail();
        this._status();
        const on = (o, s, f) => this._sigs.push([o, o.connect(s, f)]);
        on(Main.layoutManager, 'monitors-changed', () => this._layout());
        on(Main.panel, 'notify::height', () => this._layout());
        on(global.display, 'notify::focus-window', () => this._sync());
        on(Shell.AppSystem.get_default(), 'app-state-changed', () => this._sync());
        on(Shell.AppSystem.get_default(), 'installed-changed', () => this._sync());
        on(AppFavorites.getAppFavorites(), 'changed', () => this._sync());
        on(global.workspace_manager, 'active-workspace-changed', () => this._syncStatus());
        on(global.workspace_manager, 'notify::n-workspaces', () => this._syncStatus());
        /* the session opens on the desktop, not on the overview */
        if (Main.layoutManager._startingUp) {
            this._hadOverview = Main.sessionMode.hasOverview;
            Main.sessionMode.hasOverview = false;
            on(Main.layoutManager, 'startup-complete', () => { Main.sessionMode.hasOverview = this._hadOverview; });
        }
        /* the rail is the dash */
        this._dash = Main.overview.dash;
        if (this._dash) { this._dashH = this._dash.height; this._dash.hide(); this._dash.set_height(0); }
        this._layout();
        this._sync();
        this._syncStatus();
    }

    disable() {
        for (const [o, id] of this._sigs) o.disconnect(id);
        this._sigs = [];
        if (this._mon) { this._mon.cancel(); this._mon = null; }
        if (this._dash) { this._dash.set_height(-1); this._dash.show(); this._dash = null; }
        if (this._hadOverview !== undefined) Main.sessionMode.hasOverview = this._hadOverview;
        for (const a of [this._railBox, this._sb]) { Main.layoutManager.removeChrome(a); a.destroy(); }
        this._mk.destroy(); this._cmd.destroy();
        const dm = Main.panel.statusArea.dateMenu;
        if (dm && this._clockMoved) {
            Main.panel._rightBox.remove_child(dm.container);
            Main.panel._centerBox.add_child(dm.container);
        }
        for (const a of this._moved) a.show();
        this._moved = [];
    }

    /* ---- title bar: the mark and the command line */
    _title() {
        for (const k of ['activities', 'appMenu']) {
            const b = Main.panel.statusArea[k];
            if (b && b.container.visible) { b.container.hide(); this._moved.push(b.container); }
        }
        this._mk = new St.Button({ style_class: 'silik-mk', reactive: true, track_hover: true, can_focus: true, y_expand: true });
        const mb = new St.BoxLayout({ y_align: Clutter.ActorAlign.CENTER });
        const f = Gio.File.new_for_path('/usr/share/pixmaps/silikos-mark-light.svg');
        if (f.query_exists(null)) mb.add_child(new St.Icon({ gicon: new Gio.FileIcon({ file: f }), style_class: 'silik-mk-icon' }));
        mb.add_child(new St.Label({ text: 'SilikOS', style_class: 'silik-mk-name', y_align: Clutter.ActorAlign.CENTER }));
        this._mk.set_child(mb);
        this._mk.connect('clicked', () => Main.overview.toggle());

        this._cmd = new St.Button({ style_class: 'silik-cmd', reactive: true, track_hover: true, can_focus: true, x_expand: true, y_expand: true });
        const cb = new St.BoxLayout({ x_expand: true, y_align: Clutter.ActorAlign.CENTER });
        cb.add_child(new St.Label({ text: '›', style_class: 'silik-cmd-pr', y_align: Clutter.ActorAlign.CENTER }));
        cb.add_child(new St.Widget({ style_class: 'silik-cmd-cur', y_align: Clutter.ActorAlign.CENTER }));
        cb.add_child(new St.Widget({ x_expand: true }));
        cb.add_child(new St.Label({ text: 'Super+Space', style_class: 'silik-cmd-hint', y_align: Clutter.ActorAlign.CENTER }));
        this._cmd.set_child(cb);
        this._cmd.connect('clicked', () => {
            Main.overview.hide();
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

    /* ---- rail */
    _rail() {
        this._railBox = new St.BoxLayout({ style_class: 'silik-rail', vertical: true, reactive: true });
        this._keys = new St.BoxLayout({ vertical: true });
        this._hr = new St.Widget({ style_class: 'silik-hr' });
        this._open = new St.BoxLayout({ vertical: true });
        this._railBox.add_child(this._keys);
        this._railBox.add_child(this._hr);
        this._railBox.add_child(this._open);
        this._railBox.add_child(new St.Widget({ y_expand: true }));
        const apps = this._key('', this._t.apps, false);
        apps.connect('clicked', () => {
            if (Main.overview.visible) Main.overview.hide();
            else if (Main.overview.showApps) Main.overview.showApps();
            else Main.overview.show();
        });
        this._railBox.add_child(apps);
        Main.layoutManager.addChrome(this._railBox, { affectsStruts: true, trackFullscreen: true });
    }

    _key(digit, name, running) {
        const b = new St.Button({ style_class: 'silik-key', reactive: true, track_hover: true, can_focus: true, x_expand: true,
                                  button_mask: St.ButtonMask.ONE | St.ButtonMask.TWO });
        const box = new St.BoxLayout({ x_expand: true });
        box.add_child(new St.Label({ text: digit, style_class: 'silik-key-n', y_align: Clutter.ActorAlign.CENTER }));
        box.add_child(new St.Label({ text: name, style_class: 'silik-key-t', x_expand: true, y_align: Clutter.ActorAlign.CENTER }));
        box.add_child(new St.Label({ text: running ? '■' : '', style_class: 'silik-key-m', y_align: Clutter.ActorAlign.CENTER }));
        b.set_child(box);
        return b;
    }

    _appKey(app, digit, focus) {
        const run = app.state !== Shell.AppState.STOPPED;
        const b = this._key(digit, app.get_name(), run);
        if (focus === app) b.add_style_class_name('silik-on');
        b.connect('clicked', (w, button) => {
            Main.overview.hide();
            if (run && button !== 2) app.activate();
            else app.open_new_window(-1);
        });
        return b;
    }

    _sync() {
        const fav = AppFavorites.getAppFavorites().getFavorites();
        const focus = Shell.WindowTracker.get_default().focus_app;
        this._keys.destroy_all_children();
        this._open.destroy_all_children();
        fav.forEach((app, i) => this._keys.add_child(this._appKey(app, i < 9 ? String(i + 1) : '', focus)));
        const ids = fav.map(a => a.get_id());
        const others = Shell.AppSystem.get_default().get_running()
            .filter(a => !ids.includes(a.get_id()) && a.get_id() !== COMMAND_ID &&
                         a.get_windows().some(w => !w.is_skip_taskbar() && w.get_wm_class_instance() !== 'silik-command'));
        for (const app of others) this._open.add_child(this._appKey(app, '', focus));
        this._hr.visible = others.length > 0;
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

    _syncStatus() {
        const wm = global.workspace_manager;
        this._ws.text = (wm.get_active_workspace_index() + 1) + '/' + wm.get_n_workspaces();
    }

    _layout() {
        const m = Main.layoutManager.primaryMonitor;
        if (!m) return;
        const s = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        const ph = Main.layoutManager.panelBox.height, sb = SB_H * s;
        this._sb.set_position(m.x, m.y + m.height - sb);
        this._sb.set_size(m.width, sb);
        this._railBox.set_position(m.x, m.y + ph);
        this._railBox.set_size(RAIL_W * s, m.height - ph - sb);
    }
}

function init() { return new SilikShell(); }
