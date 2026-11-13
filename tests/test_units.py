# The systemd units SilikOS ships that run as root with no one typing: each is confined to what it needs
# (`systemd-analyze security`: 9.6 "UNSAFE" before 13/11/2026's audit; 1.5 to 1.7 after, run in the rig with the
# services still doing their work: docs/STATUS.md), or says why it is not.
import glob
import os
import re
import unittest

from test_silik import ROOT

CONFINED = {
    "packages/silikos-power/files/silikos-power-auto.service": {"tunables": True, "write": None},
    "packages/silikos-power/files/silikos-power-charge.service": {"tunables": False, "write": None},      # it writes a file of /sys
    "packages/silikos-desktop/files/silikos-themes.service": {"tunables": True, "write": "/usr/share/themes"},
}
# these run dnf or the boot loader's tools as root over the whole system: a sandbox around them would be a pretence
WHOLE_SYSTEM = ("silikos-update.service", "silikos-security-update.service", "silikos-rollback-finish.service")
ALWAYS = ("CapabilityBoundingSet=", "PrivateNetwork=yes", "RestrictAddressFamilies=AF_UNIX", "PrivateDevices=yes", "PrivateTmp=yes",
          "ProtectHome=yes", "ProtectSystem=strict", "ProtectKernelModules=yes", "ProtectKernelLogs=yes", "ProtectControlGroups=yes",
          "RestrictNamespaces=yes", "RestrictSUIDSGID=yes", "LockPersonality=yes", "MemoryDenyWriteExecute=yes",
          "SystemCallArchitectures=native", "SystemCallFilter=@system-service")


def lines(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return [l.strip() for l in f.read().splitlines() if l.strip() and not l.startswith("#")]


class Units(unittest.TestCase):
    def test_every_unit_is_confined_or_named(self):
        units = sorted(glob.glob(os.path.join(ROOT, "packages/*/files/*.service")))
        self.assertTrue(units)
        for u in units:
            rel = os.path.relpath(u, ROOT)
            self.assertTrue(rel in CONFINED or os.path.basename(u) in WHOLE_SYSTEM, "%s: a new unit is confined, or listed with its reason" % rel)

    def test_the_confinement(self):
        for path, want in CONFINED.items():
            ls = lines(path)
            for d in ALWAYS:
                self.assertIn(d, ls, "%s: %s" % (path, d))
            self.assertEqual("ProtectKernelTunables=yes" in ls, want["tunables"], path)
            self.assertEqual([l for l in ls if l.startswith("ReadWritePaths=")], ["ReadWritePaths=" + want["write"]] if want["write"] else [], path)
            # no user, no ambient capability, no way back out
            self.assertFalse([l for l in ls if re.match(r"(AmbientCapabilities|User|PrivateUsers)=", l)], path)

    def test_nothing_claims_what_was_not_run(self):
        """NoNewPrivileges changes the SELinux domain a service's program gets: not run under SELinux, so not set [A]"""
        for path in CONFINED:
            self.assertFalse([l for l in lines(path) if l.startswith("NoNewPrivileges=")], path)

    def test_the_services_still_start_what_they_started(self):
        self.assertIn("ExecStart=/usr/bin/silik power apply", lines("packages/silikos-power/files/silikos-power-auto.service"))
        self.assertIn("ExecStart=/usr/bin/silik power charge apply", lines("packages/silikos-power/files/silikos-power-charge.service"))
        th = lines("packages/silikos-desktop/files/silikos-themes.service")
        self.assertIn("ExecStart=-/usr/libexec/silikos/shell-theme", th)
        self.assertIn("ExecStart=-/usr/libexec/silikos/gtk-theme", th)


if __name__ == "__main__":
    unittest.main()
