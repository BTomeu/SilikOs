# boots the disk the emulated installation made (QEMU without KVM, no network device), logs in as root on the
# serial console, and asks the installed system a few things
import socket, subprocess, sys, time
disk, log = sys.argv[1], sys.argv[2]
q = subprocess.Popen(["qemu-system-x86_64", "-accel", "tcg,thread=multi", "-cpu", "max", "-machine", "q35", "-m", "4096", "-smp", "4",
                      "-display", "none", "-drive", "file=%s,if=virtio,format=qcow2" % disk, "-nic", "none",
                      "-serial", "tcp:127.0.0.1:4555,server,nowait", "-monitor", "none"])
time.sleep(2)
s = socket.create_connection(("127.0.0.1", 4555))
s.settimeout(5)
buf = b""
out = open(log, "wb")
def until(word, limit):
    global buf
    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            d = s.recv(65536)
        except socket.timeout:
            d = b""
        if d:
            out.write(d); out.flush(); buf += d
        if word in buf:
            buf = buf[buf.rindex(word) + len(word):]
            return True
    return False
ok = until(b"login: ", 1500)
print("login prompt:", ok, flush=True)
if ok:
    s.send(b"root\n"); until(b"assword: ", 120); s.send(b"silikos-ci\n"); until(b"]# ", 180)
    for cmd in ("cat /etc/redhat-release", "uname -r", "rpm -qa | wc -l", "ls /sys/class/net", "getenforce",
                "systemctl is-system-running", "tail -1 /root/silikos-mirror-verify.log", "grep -c . /root/silikos-mirror-verify.log",
                "rpm -q kernel grub2-efi-x64 grub2-pc", "firewall-cmd --state", "echo BOOT-TEST-DONE"):
        s.send(cmd.encode() + b"\n"); until(b"]# ", 240)
    s.send(b"poweroff\n"); time.sleep(60)
q.terminate()
