/* SilikOS shell — the Flow looks (see extension.js for the Silik look and for what both share: the icons, Start).
 * One piece at the bottom of the screen and nothing else: no top panel, no rail, no status bar.
 *   bar      across the bottom, paper with an ink line on top: the mark (the Start key), the command field (the last
 *            command `silik` ran; a click opens the COMMAND bar, Super+Space), the applications as icons (the
 *            favourites, then the other open ones; the focused one is inverse video and carries its name), the windows
 *            view, the workspaces, the shell's own status menus and the clock on two lines
 *   island   one floating piece centred above the bottom edge, paper in an ink frame: the mark, the applications, the
 *            windows view, the shell's own status menus, date and time on one line. A band of the screen under and
 *            around it is reserved, so a maximised window stops above it.
 * The top panel is hidden, not rebuilt: its status menus (system menu, keyboard, calendar) are moved into the piece
 * as they are, so they stay the shell's, and they go back to the panel when the look is taken down.
 * A key of an application: click = its window (the next one when it has several and the focus; minimise when it has
 * one and the focus), middle click = a new window. Nothing here runs a system action. */
'use strict';

const { Clutter, Gio, GLib, GnomeDesktop, Pango, Shell, St } = imports.gi;
const Main = imports.ui.main;
const AppFavorites = imports.ui.appFavorites;

const BAR_H = 46;                                 /* the bar, its ink line included */
const ISL_H = 54, ISL_GAP = 12, ISL_TOP = 8;      /* the island, the space under it, the space kept free above it */
const COMMAND_ID = 'org.silikvolt.Command.desktop';

var FlowLook = class FlowLook {
    /* host: { t, icon(app, size), mark(), programOf(app), toggleStart(), closeStart(), command() } */
    constructor(kind, host) {
        this.kind = kind === 'island' ? 'island' : 'bar';
        this._h = host;
        this._taken = [];
    }

    build() {
        const island = this.kind === 'island', t = this._h.t;
        this._panelAway();
        this._piece = new St.BoxLayout({ style_class: island ? 'silik-flow silik-island' : 'silik-flow silik-bar', reactive: true });

        this._mk = new St.Button({ style_class: 'silik-fmk', reactive: true, track_hover: true, can_focus: true });
        const mark = this._h.mark();                         /* at its own size: a key never stretches the mark */
        mark.x_align = Clutter.ActorAlign.CENTER;
        mark.y_align = Clutter.ActorAlign.CENTER;
        this._mk.set_child(mark);
        if (island) this._mk.y_align = Clutter.ActorAlign.CENTER;
        this._mk.connect('clicked', () => this._h.toggleStart());
        this._piece.add_child(this._mk);

        if (island) {
            this._piece.add_child(new St.Widget({ style_class: 'silik-isep', y_align: Clutter.ActorAlign.CENTER }));
        } else {
            this._cmd = new St.Button({ style_class: 'silik-fcmd', reactive: true, track_hover: true, can_focus: true,
                                        y_align: Clutter.ActorAlign.CENTER });
            const cb = new St.BoxLayout({ x_expand: true });
            cb.add_child(new St.Label({ text: '›', style_class: 'silik-fcmd-pr', y_align: Clutter.ActorAlign.CENTER }));
            this._cur = new St.Widget({ style_class: 'silik-fcmd-cur', y_align: Clutter.ActorAlign.CENTER });
            cb.add_child(this._cur);
            this._last = new St.Label({ style_class: 'silik-fcmd-last', x_expand: true, y_align: Clutter.ActorAlign.CENTER });
            this._last.clutter_text.ellipsize = Pango.EllipsizeMode.END;
            cb.add_child(this._last);
            cb.add_child(new St.Label({ text: t.hint, style_class: 'silik-fcmd-hint', y_align: Clutter.ActorAlign.CENTER }));
            this._cmd.set_child(cb);
            this._cmd.connect('clicked', () => this._h.command());
            this._piece.add_child(this._cmd);
        }

        this._apps = new St.BoxLayout({ style_class: 'silik-aks', reactive: true });      /* reactive: it hears the pointer leave */
        this._apps.x_expand = true;                 /* said twice: only a changed value stops the keys' own wish to grow */
        this._apps.x_expand = false;
        this._apps.connect('leave-event', () => {              /* the pointer has left the keys: the name goes to the focus */
            if (!this._onApps() && this._named !== Shell.WindowTracker.get_default().focus_app) this.sync();
            return Clutter.EVENT_PROPAGATE;
        });
        this._piece.add_child(this._apps);

        /* the windows view (the shell's overview): its own key, and the cell of the workspace one is on */
        this._view = new St.Button({ style_class: 'silik-ak silik-ak-view', reactive: true, track_hover: true, can_focus: true,
                                     accessible_name: t.windows });
        this._view.set_child(new St.Icon({ icon_name: 'focus-windows-symbolic', icon_size: island ? 22 : 18, style_class: 'silik-app-icon' }));
        this._view.connect('clicked', () => this._windowsView());
        if (island) this._view.y_align = Clutter.ActorAlign.CENTER;
        if (island) {
            this._piece.add_child(this._view);
            this._piece.add_child(new St.Widget({ style_class: 'silik-isep', y_align: Clutter.ActorAlign.CENTER }));
        } else {
            this._piece.add_child(new St.Widget({ x_expand: true }));
            this._piece.add_child(this._view);
            this._wsBox = new St.BoxLayout({ style_class: 'silik-fws', y_align: Clutter.ActorAlign.CENTER });
            this._piece.add_child(this._wsBox);
        }

        this._tray = new St.BoxLayout({ style_class: 'silik-tray' });
        this._piece.add_child(this._tray);
        this._takeMenus();
        this._clock();

        Main.layoutManager.addChrome(this._piece, { affectsStruts: !island, trackFullscreen: true });
        if (island) {
            /* a floating actor makes no strut: an unseen band along the bottom edge does, and lets the pointer through */
            this._band = new St.Widget({ reactive: false });
            Main.layoutManager.addChrome(this._band, { affectsStruts: true, affectsInputRegion: false, trackFullscreen: true });
            this._widthSig = this._piece.connect('notify::width', () => this.layout());
        }
    }

    destroy() {
        if (this._wall) { this._wall.disconnect(this._wallSig); this._wall = null; }
        if (this._fmt) { this._fmt.disconnect(this._fmtSig); this._fmt = null; }
        if (this._widthSig) { this._piece.disconnect(this._widthSig); this._widthSig = 0; }
        const dm = Main.panel.statusArea.dateMenu;
        if (this._clockBox) {
            this._clockBox.destroy();
            this._clockBox = null;
            if (dm && dm._clockDisplay) dm._clockDisplay.show();
        }
        /* the shell's menus go back where they were, in their order (unless the shell took them back itself) */
        for (const [c, box, i] of this._taken) {
            if (c.get_parent() !== this._tray) continue;
            this._tray.remove_child(c);
            box.insert_child_at_index(c, Math.min(i, box.get_n_children()));
        }
        this._taken = [];
        if (this._band) { Main.layoutManager.removeChrome(this._band); this._band.destroy(); this._band = null; }
        Main.layoutManager.removeChrome(this._piece);
        this._piece.destroy();
        this._piece = null;
        this._panelBack();
    }

    /* ---- the top panel: hidden while a Flow look is up, with its strut; the same panel comes back */
    _panelAway() {
        const lm = Main.layoutManager;
        this._tracked = lm._findActor(lm.panelBox) >= 0;
        if (this._tracked) lm._untrackActor(lm.panelBox);       /* tracked, the layout shows it again and keeps its strut */
        lm.panelBox.hide();
        if (lm._rightPanelBarrier) { lm._rightPanelBarrier.destroy(); lm._rightPanelBarrier = null; }
    }

    _panelBack() {
        const lm = Main.layoutManager;
        if (this._tracked && lm._findActor(lm.panelBox) < 0) lm._trackActor(lm.panelBox, { affectsStruts: true, trackFullscreen: true });
        lm.panelBox.show();
        lm._updatePanelBarrier();
    }

    _takeMenus() {
        const take = c => {
            const box = c.get_parent();
            if (!box) return;
            this._taken.push([c, box, box.get_children().indexOf(c)]);
            box.remove_child(c);
            this._tray.add_child(c);
        };
        const dm = Main.panel.statusArea.dateMenu;
        for (const c of Main.panel._rightBox.get_children()) if (!dm || c !== dm.container) take(c);
        if (dm) take(dm.container);                              /* the clock closes the piece */
    }

    /* ---- the clock: ours inside the shell's calendar key (bar: time over date; island: date, then time) */
    _clock() {
        const dm = Main.panel.statusArea.dateMenu;
        if (!dm || !dm._clockDisplay || !dm._clockDisplay.get_parent()) return;
        const bar = this.kind === 'bar';
        this._clockBox = new St.BoxLayout({ vertical: bar, style_class: 'silik-clock', y_align: Clutter.ActorAlign.CENTER });
        this._time = new St.Label({ style_class: 'silik-clock-t', x_align: Clutter.ActorAlign.END });
        this._date = new St.Label({ style_class: 'silik-clock-d', x_align: Clutter.ActorAlign.END, y_align: Clutter.ActorAlign.CENTER });
        if (bar) { this._clockBox.add_child(this._time); this._clockBox.add_child(this._date); }
        else { this._clockBox.add_child(this._date); this._clockBox.add_child(this._time); }
        dm._clockDisplay.hide();
        dm._clockDisplay.get_parent().insert_child_above(this._clockBox, dm._clockDisplay);
        this._wall = new GnomeDesktop.WallClock();
        this._wallSig = this._wall.connect('notify::clock', () => this._tick());
        this._fmt = new Gio.Settings({ schema_id: 'org.gnome.desktop.interface' });
        this._fmtSig = this._fmt.connect('changed::clock-format', () => this._tick());
        this._tick();
    }

    _tick() {
        const now = GLib.DateTime.new_now_local();
        this._time.text = (now.format(this._fmt.get_string('clock-format') === '12h' ? '%l:%M %p' : '%H:%M') || '').trim();
        this._date.text = (now.format('%a %-e %Ob') || now.format('%a %-e %b') || '').trim();
    }

    _windowsView() {
        this._h.closeStart();
        if (Main.overview.visible) Main.overview.hide(); else Main.overview.show();
    }

    /* ---- the applications */
    _onApps() {
        const [px, py] = global.get_pointer();
        const [x, y] = this._apps.get_transformed_position();
        const [w, h] = this._apps.get_transformed_size();
        return px >= x && px < x + w && py >= y && py < y + h;
    }

    _appKey(app, focusApp) {
        const island = this.kind === 'island';
        const run = app.state !== Shell.AppState.STOPPED;
        const on = focusApp === app;
        const as = this._h.programOf(app) || app;            /* the name and icon of the program behind a nameless window */
        const b = new St.Button({ style_class: 'silik-ak', reactive: true, track_hover: true, can_focus: true,
                                  accessible_name: as.get_name(), button_mask: St.ButtonMask.ONE | St.ButtonMask.TWO });
        const w = new St.Widget({ layout_manager: new Clutter.BinLayout(), x_expand: true, y_expand: true });
        const line = new St.Widget({ style_class: 'silik-ak-line', x_expand: true, y_expand: true,   /* ink when it runs */
                                     y_align: island ? Clutter.ActorAlign.END : Clutter.ActorAlign.START });
        const box = new St.BoxLayout({ style_class: 'silik-ak-box', x_expand: true, y_expand: true,
                                       x_align: Clutter.ActorAlign.CENTER, y_align: Clutter.ActorAlign.CENTER });
        box.add_child(this._h.icon(as, 22));
        if (app === this._named && !island)
            box.add_child(new St.Label({ text: as.get_name(), style_class: 'silik-ak-t', y_align: Clutter.ActorAlign.CENTER }));
        w.add_child(line);
        w.add_child(box);
        b.set_child(w);
        if (run) b.add_style_class_name('silik-run');
        if (on) b.add_style_class_name('silik-on');
        if (island) b.y_align = Clutter.ActorAlign.CENTER;
        b.connect('clicked', (o, button) => {
            this._h.closeStart();
            const seen = Main.overview.visible;
            Main.overview.hide();
            if (!run || button === 2) { app.open_new_window(-1); return; }
            const wins = app.get_windows().filter(x => !x.is_skip_taskbar());
            if (!on || seen || !wins.length) app.activate();
            else if (wins.length > 1) Main.activateWindow(wins[wins.length - 1]);       /* the one used longest ago: a round of all */
            else if (wins[0].can_minimize()) wins[0].minimize();
        });
        return b;
    }

    sync() {
        const fav = AppFavorites.getAppFavorites().getFavorites();
        const focusApp = Shell.WindowTracker.get_default().focus_app;
        const ids = fav.map(a => a.get_id());
        const others = Shell.AppSystem.get_default().get_running()
            .filter(a => !ids.includes(a.get_id()) && a.get_id() !== COMMAND_ID &&
                         a.get_windows().some(w => !w.is_skip_taskbar() && w.get_wm_class_instance() !== 'silik-command'));
        const all = fav.concat(others);
        /* the bar writes the name on the key of the focused application, which makes it wider. While the pointer is on
           the keys the name stays where it is, so the keys do not move under it (a click that minimises a window is
           followed by a click on the same place to bring it back) */
        if (!this._named || !all.includes(this._named) || !this._onApps()) this._named = focusApp;
        this._apps.destroy_all_children();
        for (const app of all) this._apps.add_child(this._appKey(app, focusApp));
    }

    syncWs() {
        if (!this._wsBox) return;
        const wm = global.workspace_manager;
        const n = wm.get_n_workspaces(), cur = wm.get_active_workspace_index();
        this._wsBox.destroy_all_children();
        for (let i = 0; i < n; i++) {
            const b = new St.Button({ style_class: 'silik-ws-cell', label: String(i + 1), reactive: true, track_hover: true, can_focus: true });
            if (i === cur) b.add_style_class_name('silik-on');
            b.connect('clicked', () => {
                if (i === wm.get_active_workspace_index()) this._windowsView();
                else wm.get_workspace_by_index(i).activate(global.get_current_time());
            });
            this._wsBox.add_child(b);
        }
    }

    /* the last command `silik` ran ("HH:MM command"), in the command field */
    syncMsg(s) {
        if (!this._last) return;
        const i = s.indexOf(' ');
        const text = s && i > 0 ? s.slice(i + 1).split('\n')[0] : '';
        this._last.text = text;
        this._cur.visible = !text;
    }

    markOn(on) {
        if (on) this._mk.add_style_class_name('silik-on'); else this._mk.remove_style_class_name('silik-on');
    }

    layout() {
        const m = Main.layoutManager.primaryMonitor;
        if (!m || !this._piece) return;
        const s = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        if (this.kind === 'bar') {
            this._piece.set_position(m.x, m.y + m.height - BAR_H * s);
            this._piece.set_size(m.width, BAR_H * s);
            return;
        }
        const band = (ISL_GAP + ISL_H + ISL_TOP) * s;
        this._band.set_position(m.x, m.y + m.height - band);
        this._band.set_size(m.width, band);
        const [, w] = this._piece.get_preferred_width(-1);
        this._piece.set_position(m.x + Math.max(0, Math.floor((m.width - w) / 2)), m.y + m.height - (ISL_GAP + ISL_H) * s);
        this._piece.set_height(ISL_H * s);
    }

    /* where Start opens: on the bar from the left edge, or centred above the island */
    startPlace(w, h) {
        const m = Main.layoutManager.primaryMonitor;
        const s = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        if (this.kind === 'bar') {
            h = Math.min(h, m.height - BAR_H * s);
            w = Math.min(w, m.width);
            return [m.x, m.y + m.height - BAR_H * s - h, w, h];
        }
        const top = (ISL_GAP + ISL_H + ISL_TOP) * s;
        h = Math.min(h, m.height - top - ISL_TOP * s);
        w = Math.min(w, m.width);
        return [m.x + Math.floor((m.width - w) / 2), m.y + m.height - top - h, w, h];
    }
};
