# Windows programs on SilikOS

| Route | For | Commands |
|---|---|---|
| Wine | programs Wine runs (many utilities, older tools) | `silik win create NAME`, `silik win install NAME setup.exe`, `silik win run NAME -- prog.exe` |
| Windows virtual machine | programs Wine does not run | `silik win vm create --iso Win11.iso`, `silik win vm start`, `silik win vm app --exe 'C:\...\X2.EXE' --user U` |

- One Wine prefix per program, under `~/.local/share/silikos/wine/`: a broken install does not touch the others.
- The virtual machine is a user session KVM guest (UEFI, TPM 2.0 emulated, 8 GB / 4 CPUs / 80 GB by default) with the
  guest's RDP port forwarded to `127.0.0.1:3389`. Enable Remote Desktop in Windows; `silik win vm app` then opens one
  program as a window of this desktop (RDP RemoteApp, FreeRDP), with the home folder as a drive.
- Windows and the programs need their own licences.

## Altium Designer

Expected [A: from public reports, not tried here]: it does not run usably under Wine (.NET, DirectX, licensing
service). Plan: try it in a Wine prefix once, then use the virtual machine. In the virtual machine the 2D editors work
without a GPU; the 3D view needs DirectX acceleration, which a KVM guest only has with a GPU passed through to it. On
the Ryzen 7 5800HS + RTX 3050 laptop that would mean giving the RTX 3050 to the guest while the desktop stays on the
Radeon graphics: possible in principle, laptop-specific in practice, not tried.

Nothing in this file has been run yet (`docs/STATUS.md`).
