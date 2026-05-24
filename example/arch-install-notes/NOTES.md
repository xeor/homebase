# arch-install-notes

## Disks
- nvme0n1 → root (zfs)
- nvme1n1 → home (zfs)

## Pacstrap
```
pacstrap -K /mnt base linux-zen zfs-dkms
```
