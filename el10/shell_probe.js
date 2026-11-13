(() => {
    /* run inside GNOME Shell by el10/shell_run.sh (org.gnome.Shell.Eval, which the shell allows in --unsafe-mode):
       what the ported extension has put up, asked of the extension's own object. Then Start is opened, so that the
       second picture shows it. Returns the facts separated by ' ;; ' (no backslash in this file: gdbus reads its argument as GVariant text). */
    const out = [];
    const say = (k, f) => { try { out.push(k + ': ' + f()); } catch (e) { out.push(k + ': ERROR ' + e.message); } };
    const e = Main.extensionManager.lookup('silik-shell@silikvolt.com');
    const x = e && e.stateObj;
    if (!x) return 'no extension object';
    say('look', () => x._flow ? x._flow.kind : 'silik');
    say('pieces on the stage', () => x._pieces().map(a => a.get_stage() ? Math.round(a.width) + 'x' + Math.round(a.height) + '@' + Math.round(a.x) + ',' + Math.round(a.y) : 'not on stage').join(' '));
    say('top panel visible', () => Main.layoutManager.panelBox.visible);
    say('work area of the primary monitor', () => { const r = Main.layoutManager.getWorkAreaForMonitor(Main.layoutManager.primaryIndex); return r.width + 'x' + r.height + '@' + r.x + ',' + r.y; });
    say('keys', () => x._flow ? x._flow._keys.size + ' application key(s), ' + x._flow._tray.get_n_children() + ' shell menu(s) in the tray'
        : x._keys.get_n_children() + ' rail key(s); status bar fields: ' + x._sb.get_children().map(f => f.get_children().map(l => l.text).join('=')).join(' | '));
    say('settings', () => 'look=' + x._settings.get_string('look') + ' accent=' + x._settings.get_string('accent') + ' glass=' + x._settings.get_boolean('glass'));
    say('icon of an application is ours', () => { const a = Shell.AppSystem.get_default().get_installed().map(i => Shell.AppSystem.get_default().lookup_app(i.get_id())).filter(a => a)[0]; const i = a.create_icon_texture(16); return a.get_id() + ' -> ' + i.constructor.name + ' ' + (i.style_class || ''); });
    say('applications Start lists', () => x._appList().length);
    say('recent files read', () => x._recentFiles().length);
    say('Start opens', () => { x._toggleStart(); return x._startOpen + ', grab seat state ' + (x._grab ? x._grab.get_seat_state() : 'no grab') + ', ' + Math.round(x._startBox.width) + 'x' + Math.round(x._startBox.height); });
    return out.join(' ;; ');
})()
