/* MADE BY el10/port_shell.py from packages/silikos-desktop/files/shell-ext/flow.js (the GNOME Shell 40 extension of
   SilikOS 9) for GNOME Shell 49 (EL 10). Do not edit: change the EL 9 file or the script's rules. */
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
 * one and the focus), middle click = a new window. Nothing here runs a system action.
 * The keys are kept, not rebuilt: a change of focus, of what runs or of the windows changes the keys that changed
 * (so a key under the pointer stays under it, and nothing blinks). An application that is starting has its line at
 * once, pulsing until its first window is there. Every window is told where its key is, so the shell's own minimise
 * goes to the key and comes back from it.
 * Motion (the end of this file's head: ease, pulse) is short and only where something changes place or state; with
 * the desktop's animations off, or taken away by the shell (software rendering, a remote session), every change is
 * made at once. Nothing moves, and no timer runs, while nothing changes. */
import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GnomeDesktop from 'gi://GnomeDesktop';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import Mtk from 'gi://Mtk';
import Pango from 'gi://Pango';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as AppFavorites from 'resource:///org/gnome/shell/ui/appFavorites.js';
import * as Background from 'resource:///org/gnome/shell/ui/background.js';

const BAR_H = 46;                                 /* the bar, its ink line included */
const ISL_H = 54, ISL_GAP = 12, ISL_TOP = 8;      /* the island, the space under it, the space kept free above it */
export const ISL_R = 6;                                    /* its corners (stylesheet.css: .silik-island, .silik-start-island) */
const COMMAND_ID = 'org.silikvolt.Command.desktop';

/* ---- motion: the one door. Times in ms. */
export const T_KEY = 130;                                  /* a key comes or goes, the name on the focused key */
export const T_START_IN = 150, T_START_OUT = 90;           /* Start rises from the piece, and leaves faster */
export const T_LOOK_OUT = 90, T_LOOK_IN = 150;             /* one look gives way to another */
const T_PULSE = 480, PULSES = 12;                 /* an application is starting: the line breathes, for six seconds at most */

/* are animations on? The desktop's setting, unless the shell has taken them away */
export function animated() {
    return St.Settings.get().enable_animations;
}

/* ease(actor, props, ms, mode, done): the properties reach their values in ms, or at once when animations are off or
   the actor is not on screen. done(finished) is called once, also when the change was cut short (finished false). */
export function ease(actor, props, ms, mode, done) {
    if (!animated() || !actor.mapped) {
        for (const p of Object.keys(props)) actor.remove_transition(p.replace(/_/g, '-'));
        actor.set(props);
        if (done) done(true);
        return;
    }
    actor.ease(Object.assign({}, props, { duration: ms, mode: mode === undefined ? Clutter.AnimationMode.EASE_OUT_QUAD : mode,
                                           onStopped: done ? finished => done(finished) : undefined }));
}

/* pulse(actor): its opacity breathes a fixed number of times and ends where it began; still(actor) ends it now */
export function pulse(actor) {
    if (!animated() || !actor.mapped || actor.get_transition('opacity')) return;
    actor.ease({ opacity: 60, duration: T_PULSE, mode: Clutter.AnimationMode.EASE_IN_OUT_SINE, repeatCount: PULSES - 1, autoReverse: true,
                 onStopped: () => { actor.opacity = 255; } });
}

export function still(actor) {
    actor.remove_transition('opacity');
    actor.opacity = 255;
}

export function cls(actor, name, on) {
    if (on) actor.add_style_class_name(name); else actor.remove_style_class_name(name);
}

export class FlowLook {
    /* host: { t, icon(app, size), mark(), programOf(app), toggleStart(), closeStart(), command() } */
    constructor(kind, host) {
        this.kind = kind === 'island' ? 'island' : 'bar';
        this._h = host;
        this._taken = [];
        this._keys = new Map();                              /* application -> its key */
        this._starting = new Map();                          /* applications started and still without a window (-> our time limit, or 0) */
    }

    /* what of this look is on the screen (a change of look fades it) */
    pieces() {
        return this._piece ? [this._piece] : [];
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
        this._view.set_child(new St.Icon({ icon_name: 'shell-focus-windows-symbolic', icon_size: island ? 22 : 18, style_class: 'silik-app-icon' }));
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

    /* the piece's glass (the key "glass"): made or taken away; layout() keeps it under the piece */
    glass(on) {
        if (!on === !this._mica) return;
        if (on) {
            this._mica = new Mica(this._piece, Main.layoutManager.primaryIndex, false, this.kind === 'island' ? ISL_R : 0);
            this.layout();
        } else { this._mica.destroy(); this._mica = null; }
    }

    destroy() {
        this._gone = true;
        if (this._mica) { this._mica.destroy(); this._mica = null; }
        if (this._geomLater) { global.compositor.get_laters().remove(this._geomLater); this._geomLater = 0; }
        for (const k of this._keys.values())                 /* the windows forget the keys */
            for (const w of k.app.get_windows()) w.set_icon_geometry(null);
        this._keys.clear();
        for (const id of this._starting.values()) if (id) GLib.source_remove(id);
        this._starting.clear();
        if (this._wall) { this._wall.disconnect(this._wallSig); this._wall = null; }
        if (this._fmt) { this._fmt.disconnect(this._fmtSig); this._fmt = null; }
        if (this._widthSig) { this._piece.disconnect(this._widthSig); this._widthSig = 0; }
        const dm = Main.panel.statusArea.dateMenu;
        if (this._clockBox) {
            this._clockBox.destroy();
            this._clockBox = null;
            if (dm && dm._clockDisplay) dm._clockDisplay.show();
        }
        /* the shell's menus go back where they were, in their order (unless the shell took them back itself). They
           were taken one by one from the front, so each index was read with the earlier ones gone: put back last
           first, each at its index, they stand in their first order again */
        for (const [c, box, i] of this._taken.slice().reverse()) {
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
        lm.panelBox.show();                                       /* (first: tracking it hides it again over a full-screen window) */
        if (this._tracked && lm._findActor(lm.panelBox) < 0) lm._trackActor(lm.panelBox, { affectsStruts: true, trackFullscreen: true });
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
        this._clockBox = new St.BoxLayout({ orientation: bar ? Clutter.Orientation.VERTICAL : Clutter.Orientation.HORIZONTAL, style_class: 'silik-clock', y_align: Clutter.ActorAlign.CENTER });
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

    /* a key: made once for an application, then only changed */
    _makeKey(app) {
        const island = this.kind === 'island';
        const b = new St.Button({ style_class: 'silik-ak', reactive: true, track_hover: true, can_focus: true,
                                  button_mask: St.ButtonMask.ONE | St.ButtonMask.TWO });
        const w = new St.Widget({ layout_manager: new Clutter.BinLayout(), x_expand: true, y_expand: true });
        const plate = new St.Widget({ style_class: 'silik-ak-plate', x_expand: true, y_expand: true, opacity: 0 });   /* ink under the focused one */
        const line = new St.Widget({ style_class: 'silik-ak-line', x_expand: true, y_expand: true,   /* ink when it runs */
                                     y_align: island ? Clutter.ActorAlign.END : Clutter.ActorAlign.START });
        const box = new St.BoxLayout({ style_class: 'silik-ak-box', x_expand: true, y_expand: true,
                                       x_align: Clutter.ActorAlign.CENTER, y_align: Clutter.ActorAlign.CENTER });
        w.add_child(plate);
        w.add_child(line);
        w.add_child(box);
        b.set_child(w);
        if (island) b.y_align = Clutter.ActorAlign.CENTER;
        const k = { app, b, plate, line, box, as: null, label: null, named: false, on: false, leaving: false };
        b.connect('clicked', (o, button) => this._click(k, button));
        return k;
    }

    /* the icon and the name on a key: those of the program behind a nameless window; changed only when that changes */
    _dress(k) {
        /* (a window that was found to be a program's stays that program's: when the program ends, its command line is
           gone a moment before its window, and the key would be drawn again under the window's title) */
        const as = this._h.programOf(k.app) || (k.as && k.as !== k.app ? k.as : k.app);
        if (as === k.as) return;
        k.as = as;
        k.box.destroy_all_children();
        k.box.add_child(this._h.icon(as, 22));
        k.label = null;
        k.named = false;
        if (this.kind === 'bar') {
            k.label = new St.Label({ text: as.get_name(), style_class: 'silik-ak-t', y_align: Clutter.ActorAlign.CENTER, visible: false });
            k.label.clip_to_allocation = true;               /* while its width eases, the name is cut at the edge: */
            k.label.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;                    /* not spilled, not dotted */
            k.box.add_child(k.label);
        }
        k.b.accessible_name = as.get_name();
    }

    /* the bar writes the name on the key of the focused application: it comes and goes with an eased width */
    _name(k, want, move) {
        const l = k.label;
        if (!l || k.named === want) return;
        k.named = want;
        if (want) {
            l.remove_all_transitions();
            l.set_width(-1);
            l.show();
            if (!move) { l.opacity = 255; return; }
            const [, nat] = l.get_preferred_width(-1);
            l.set_width(0);
            l.opacity = 0;
            ease(l, { width: nat, opacity: 255 }, T_KEY, undefined, () => {
                if (this._gone || !k.named) return;
                l.set_width(-1);
                l.opacity = 255;
                this._geomSoon();
            });
        } else if (!move) {
            l.remove_all_transitions();
            l.hide();
        } else {
            l.set_width(l.width);
            ease(l, { width: 0, opacity: 0 }, T_KEY, undefined, () => {
                if (this._gone || k.named) return;
                l.hide();
                this._geomSoon();
            });
        }
    }

    /* inverse video on the key of the focused application: the ink plate fades in or out, and the colours of what
       stands on it turn at the middle, where ink and paper both read on the half-way grey */
    _lit(k, on, move) {
        if (k.on === on) return;
        k.on = on;
        const p = k.plate;
        if (!move || !animated() || !p.mapped) {
            p.remove_all_transitions();
            p.opacity = on ? 255 : 0;
            cls(k.b, 'silik-on', on);
            return;
        }
        ease(p, { opacity: 128 }, T_KEY / 2, Clutter.AnimationMode.LINEAR, () => {
            if (this._gone || k.on !== on) return;           /* (it changed again meanwhile: the later change goes on) */
            cls(k.b, 'silik-on', on);
            ease(p, { opacity: on ? 255 : 0 }, T_KEY / 2, Clutter.AnimationMode.LINEAR);
        });
    }

    /* a key that was not there comes in from no width (the island grows around its centre); one that goes, goes the same way */
    _enter(k) {
        const b = k.b;
        if (!animated() || !b.mapped) return;
        const [, nat] = b.get_preferred_width(-1);
        b.clip_to_allocation = true;
        b.set_width(0);
        b.opacity = 0;
        ease(b, { width: nat, opacity: 255 }, T_KEY, undefined, () => {
            if (this._gone || k.leaving) return;
            b.set_width(-1);
            b.opacity = 255;
            b.clip_to_allocation = false;
            this._geomSoon();
        });
    }

    _leave(k) {
        const b = k.b;
        k.leaving = true;
        this._keys.delete(k.app);
        b.reactive = false;
        still(k.line);
        b.clip_to_allocation = true;
        b.set_width(b.width);
        ease(b, { width: 0, opacity: 0 }, T_KEY, undefined, () => { if (!this._gone) b.destroy(); });
    }

    _click(k, button) {
        const app = k.app;
        this._h.closeStart();
        const seen = Main.overview.visible;
        Main.overview.hide();
        if (app.state === Shell.AppState.STOPPED || button === 2) {
            const stopped = app.state === Shell.AppState.STOPPED;
            app.open_new_window(-1);
            if (stopped) this.started(app);
            return;
        }
        const wins = app.get_windows().filter(x => !x.is_skip_taskbar());
        this._geom();                                        /* where the window goes to, or comes from: this key, now */
        if (!k.on || seen || !wins.length) app.activate();
        else if (wins.length > 1) Main.activateWindow(wins[wins.length - 1]);       /* the one used longest ago: a round of all */
        else if (wins[0].can_minimize()) wins[0].minimize();
    }

    /* An application that is starting is shown at once, before it has a window: its key is there, with its line, and
       the line breathes. The shell says "starting" only for programs that announce their start; one opened from a key
       or from Start is taken as starting here, until it has a window or for six seconds (one time limit, then none). */
    started(app) {
        if (app.get_id() === COMMAND_ID || app.state === Shell.AppState.RUNNING) return;
        const info = app.get_app_info();
        if (info && info.get_boolean('Terminal')) return;    /* (it will be a window of the terminal: that key shows it) */
        this._forget(app);
        this._starting.set(app, GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_PULSE * PULSES, () => {
            this._starting.delete(app);
            if (!this._gone) this.sync();
            return GLib.SOURCE_REMOVE;
        }));
        this.sync();
    }

    _forget(app) {
        const id = this._starting.get(app);
        if (id) GLib.source_remove(id);
        this._starting.delete(app);
    }

    appState(app) {                                          /* (the shell's own word on it) */
        if (app.state === Shell.AppState.RUNNING) this._forget(app);
        else if (app.state === Shell.AppState.STARTING) { if (!this._starting.has(app) && app.get_id() !== COMMAND_ID) this._starting.set(app, 0); }
        else if (this._starting.get(app) === 0) this._starting.delete(app);
    }

    sync() {
        const fav = AppFavorites.getAppFavorites().getFavorites();
        const focusApp = Shell.WindowTracker.get_default().focus_app;
        const ids = fav.map(a => a.get_id());
        const others = Shell.AppSystem.get_default().get_running()
            .filter(a => !ids.includes(a.get_id()) && a.get_id() !== COMMAND_ID &&
                         a.get_windows().some(w => !w.is_skip_taskbar() && w.get_wm_class_instance() !== 'silik-command'));
        /* a program whose window the shell could not give to its application (Magic, Xschem, Netgen: Tk's class) has
           started when that window is there: the key that stood for it while it started becomes the window's key */
        for (const a of others) {
            const as = a.is_window_backed() ? this._h.programOf(a) : null;
            if (!as || !this._starting.has(as) || as.state === Shell.AppState.RUNNING) continue;
            const k = this._keys.get(as);
            this._forget(as);
            if (k && !ids.includes(as.get_id()) && !this._keys.has(a)) { this._keys.delete(as); k.app = a; this._keys.set(a, k); }
        }
        for (const a of this._starting.keys())
            if (!ids.includes(a.get_id()) && !others.includes(a)) others.push(a);
        /* the open applications keep the order in which their keys came (the shell lists them in no order of its own) */
        const came = Array.from(this._keys.keys());
        const place = a => { const i = came.indexOf(a); return i < 0 ? came.length : i; };
        others.sort((a, b) => place(a) - place(b));
        const all = fav.concat(others);
        /* the bar writes the name on the key of the focused application, which makes it wider. While the pointer is on
           the keys the name stays where it is, so the keys do not move under it (a click that minimises a window is
           followed by a click on the same place to bring it back) */
        if (!this._named || !all.includes(this._named) || !this._onApps()) this._named = focusApp;
        const move = !!this._synced;                         /* the keys of a look just put up are simply there */
        for (const [app, k] of this._keys) if (!all.includes(app)) this._leave(k);
        const kept = new Set(Array.from(this._keys.values()).map(k => k.b));
        const going = new Set(this._apps.get_children().filter(c => !kept.has(c)));     /* keys on their way out keep their place */
        let at = 0;
        for (const app of all) {
            let k = this._keys.get(app);
            const fresh = !k;
            if (fresh) {
                k = this._makeKey(app);
                this._keys.set(app, k);
            }
            this._dress(k);
            while (going.has(this._apps.get_child_at_index(at))) at++;
            if (fresh) this._apps.insert_child_at_index(k.b, at);
            else if (this._apps.get_child_at_index(at) !== k.b) this._apps.set_child_at_index(k.b, at);
            at++;
            const starting = app.state !== Shell.AppState.RUNNING && this._starting.has(app);
            cls(k.b, 'silik-run', starting || app.state !== Shell.AppState.STOPPED);
            this._lit(k, focusApp === app, move && !fresh);
            if (starting) pulse(k.line); else still(k.line);
            this._name(k, app === this._named, move && !fresh);
            if (fresh && move) this._enter(k);
        }
        this._synced = true;
        this._geomSoon();
    }

    /* every window knows the rectangle of its key: the shell's minimise goes there, and comes back from there */
    _geom() {
        if (this._gone) return;
        for (const k of this._keys.values()) {
            const [x, y] = k.b.get_transformed_position();
            const [w, h] = k.b.get_transformed_size();
            if (!(w > 0 && h > 0)) continue;
            const r = new Mtk.Rectangle({ x: Math.round(x), y: Math.round(y), width: Math.round(w), height: Math.round(h) });
            for (const win of k.app.get_windows()) win.set_icon_geometry(r);
        }
    }

    _geomSoon() {                                            /* once, after the keys have their places */
        if (this._geomLater || this._gone) return;
        this._geomLater = global.compositor.get_laters().add(Meta.LaterType.IDLE, () => {
            this._geomLater = 0;
            this._geom();
            return GLib.SOURCE_REMOVE;
        });
    }

    syncWs() {
        if (!this._wsBox) return;
        const wm = global.workspace_manager;
        const n = wm.get_n_workspaces(), cur = wm.get_active_workspace_index();
        const cells = this._wsBox.get_children();
        if (cells.length === n) {                            /* the same cells: only the one that is on changes */
            cells.forEach((c, i) => cls(c, 'silik-on', i === cur));
            return;
        }
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
            if (this._mica) this._mica.place(m.x, m.y + m.height - BAR_H * s, m.width, BAR_H * s);
            return;
        }
        const band = (ISL_GAP + ISL_H + ISL_TOP) * s;
        this._band.set_position(m.x, m.y + m.height - band);
        this._band.set_size(m.width, band);
        const [, w] = this._piece.get_preferred_width(-1);
        const x = m.x + Math.max(0, Math.floor((m.width - w) / 2)), y = m.y + m.height - (ISL_GAP + ISL_H) * s;
        this._piece.set_position(x, y);
        this._piece.set_height(ISL_H * s);
        if (this._mica) this._mica.place(x, y, w, ISL_H * s);
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
        /* a pane a few pixels wider or narrower than the island under it reads as a mistake: within 24 px it takes the
           island's width, and their edges line up (seen in the rig: 640 over 636) */
        const iw = this._piece.get_preferred_width(-1)[1];
        if (Math.abs(iw - w) <= 24 * s) w = iw;
        w = Math.min(w, m.width);
        return [m.x + Math.floor((m.width - w) / 2), m.y + m.height - top - h, w, h];
    }
}

/* ---- glass (the key "glass"): a pane is paper at 0.86 (glass.css) over its glass, the wallpaper under it blurred.
   Only the wallpaper, never the windows: what shows through a pane is the same whatever is open, so nothing behind it
   can make its text unreadable, and it costs nothing at rest. The blur is the shell's own (Shell.BlurEffect) in ACTOR
   mode: made when the glass is first painted and kept until the wallpaper or the pane's place or size change; a still
   screen, a key that lights up or a clock that ticks paint the kept picture. (Its BACKGROUND mode, which blurs the
   screen as it is, was tried and left: GNOME Shell 40 then blurs what is outside the part of the screen being redrawn
   as it was in an older frame, and every small change left a lighter box on the pane; seen in the rig, 12/11/2026.)
   The glass ends where the pane's frame ends: a rounded pane's glass is cut to its corners. */
export const GLASS_SIGMA = 16;                                /* the blur's radius in px at scale 1 */

/* The glass is blurred a margin wider than the pane, so that its edges blur what really is next to them, and a mask
   cuts it to the pane, square or with its corners. The blur also draws in the nothing beyond its picture: the glass
   grew transparent toward its edges, over about 4 sigma (seen in the rig: the windows behind the COMMAND bar showed
   at its edges). The mask takes that out: a pixel of the glass is the average of the wallpaper it was made from,
   its colour divided by its coverage (the picture is premultiplied: rgb / a). What the mask writes is blended as
   straight colour and alpha (written premultiplied, the rounded edge came out with a dark fringe: seen in the rig),
   so its alpha is the pane's opacity times the mask's edge.
   The mask is drawn on the picture the shell made of the glass, whose box Clutter makes larger than the actor
   (_clutter_actor_box_enlarge_for_effects, GNOME Shell 40: 3 px more, the actor 2 px in from the top left when it
   stands on whole pixels, as the glass does: place() rounds). Without that the corners of the COMMAND bar's glass
   were not cut (seen in the rig). */
const PAD = 2, GROW = 3;
const ROUND_DECL = 'uniform vec2 silik_tex;\nuniform vec2 silik_off;\nuniform vec2 silik_size;\nuniform float silik_radius;\n';
const ROUND_CODE = 'vec2 silik_p = cogl_tex_coord_in[0].xy * silik_tex - silik_off;\n' +
    'vec2 silik_q = abs(silik_p - 0.5 * silik_size) - (0.5 * silik_size - vec2(silik_radius));\n' +
    'float silik_d = length(max(silik_q, 0.0)) + min(max(silik_q.x, silik_q.y), 0.0) - silik_radius;\n' +
    'vec3 silik_rgb = cogl_color_out.a > 0.004 ? cogl_color_out.rgb / cogl_color_out.a : vec3(0.0);\n' +
    'cogl_color_out = vec4(silik_rgb, cogl_color_in.a * clamp(0.5 - silik_d, 0.0, 1.0));\n';

const RoundMask = GObject.registerClass({ GTypeName: 'SilikRoundMask' }, class RoundMask extends Shell.GLSLEffect {
    _init(params) {
        super._init(params);
        this._at = ['silik_tex', 'silik_off', 'silik_size', 'silik_radius'].map(n => this.get_uniform_location(n));
    }

    vfunc_build_pipeline() {
        this.add_glsl_snippet(Cogl.SnippetHook.FRAGMENT, ROUND_DECL, ROUND_CODE, false);
    }

    /* the actor is W x H; the pane, of corners R, stands M in from its edges */
    shape(W, H, m, r) {
        this.set_uniform_float(this._at[0], 2, [W + GROW, H + GROW]);
        this.set_uniform_float(this._at[1], 2, [PAD + m, PAD + m]);
        this.set_uniform_float(this._at[2], 2, [W - 2 * m, H - 2 * m]);
        this.set_uniform_float(this._at[3], 1, [r]);
    }
});

/* Mica(pane, monitor, inside, radius): the glass of PANE, on the wallpaper of that monitor. INSIDE: it is the pane's
   own lowest child (a window); else the pane's sibling just under it, with the pane's opacity, rise and visibility.
   RADIUS: the pane's corners in px at scale 1 (0: square). place(x, y, w, h) says where the pane is on the screen.
   The glass is never hidden: while its pane is hidden it is at opacity 0, which the shell does not paint. A hidden
   actor that is shown again is drawn from scratch, and the blur with it (measured in the rig: 7-11 ms more at each
   opening of Start then). */
export class Mica {
    constructor(pane, monitor, inside, radius) {
        const s = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        this._inside = inside;
        this._mon = monitor;
        this._r = radius * s;
        this._m = 3 * GLASS_SIGMA * s;                   /* the margin blurred beyond the pane: the blur reaches 3 sigma */
        this._at = null;
        this.actor = new St.Widget({ reactive: false });
        this._glass = new St.Widget({ clip_to_allocation: true, reactive: false });
        this.actor.add_child(this._glass);
        /* the mask on the holder, the blur on the glass in it: both on the glass, the blur came out shifted in the
           mask's picture and the pane's edges let what is behind through (seen in the rig) */
        this._mask = new RoundMask();
        this.actor.add_effect(this._mask);
        this._glass.add_effect(new Shell.BlurEffect({ mode: Shell.BlurMode.ACTOR, radius: 2 * GLASS_SIGMA * s, brightness: 1 }));
        this._bg = new Background.BackgroundManager({ container: this._glass, monitorIndex: monitor, controlPosition: false });
        this._addSig = this._glass.connect('child-added', () => this._wall());         /* (a new wallpaper's actor) */
        if (inside) pane.insert_child_below(this.actor, null);
        else {
            pane.get_parent().insert_child_below(this.actor, pane);
            this._binds = [pane.bind_property('translation-y', this.actor, 'translation-y', GObject.BindingFlags.SYNC_CREATE)];
            const seen = () => { this.actor.opacity = pane.visible ? pane.opacity : 0; };
            this._pane = pane;
            this._paneSigs = [pane.connect('notify::visible', seen), pane.connect('notify::opacity', seen)];
            seen();
        }
    }

    place(x, y, w, h) {
        const at = [x, y, w, h].map(Math.round), m = this._m;
        if (this._at && at.every((v, i) => v === this._at[i])) return;     /* (unchanged: the kept blur stays) */
        this._at = at;
        /* (the holder is the whole blurred rectangle and the glass stands at its origin: the mask's picture is the
           holder's own box, which leaves out a child at negative places; seen in the rig) */
        if (this._inside) this.actor.set_position(-m, -m); else this.actor.set_position(at[0] - m, at[1] - m);
        this.actor.set_size(at[2] + 2 * m, at[3] + 2 * m);
        this._glass.set_size(at[2] + 2 * m, at[3] + 2 * m);
        this._mask.shape(at[2] + 2 * m, at[3] + 2 * m, m, this._r);
        this._wall();
    }

    /* the wallpaper sits where it is on the screen, seen through the glass's rectangle */
    _wall() {
        const mon = Main.layoutManager.monitors[this._mon];
        if (!mon || !this._at) return;
        for (const c of this._glass.get_children()) c.set_position(mon.x - this._at[0] + this._m, mon.y - this._at[1] + this._m);
    }

    destroy() {
        if (this._binds) this._binds.forEach(b => b.unbind());
        if (this._paneSigs) this._paneSigs.forEach(id => this._pane.disconnect(id));
        this._binds = this._paneSigs = null;
        this._glass.disconnect(this._addSig);
        if (this._bg) { this._bg.destroy(); this._bg = null; }
        this.actor.destroy();
    }
}
