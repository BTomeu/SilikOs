# SilikOS — LVM metadata profile for the thin pool that holds / (and /home): the pool grows by itself.
# When the pool's data or metadata are 70 % used, LVM (dmeventd, lvm2-monitor.service) adds 20 % of its size, taken
# from the free space of the volume group (the installer's Automatic partitioning leaves 20 % of it free for this).
# The two figures are the example of lvm.conf(5) itself; the base's default is 100 (never grows).   PROPOSAL values.
# Applied to the pool by the kickstart on a new installation, by `silik snapshot setup` on a running one:
#   lvchange --metadataprofile silikos-thin VG/POOL
# /etc/lvm/lvm.conf is not changed. Why: a snapshot kept before each update makes the pool fill faster, and a full
# pool stops every file system in it (docs/ROLLBACK.md).
activation {
	thin_pool_autoextend_threshold=70
	thin_pool_autoextend_percent=20
}
