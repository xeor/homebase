#!/usr/bin/env bash
# Builds the example base. Idempotent-ish: re-running rewrites stub
# files but leaves real git history alone (existing .git/ skips init).
# Run from anywhere: bash example/.homebase/_setup.sh
set -euo pipefail

BASE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE"

write() { mkdir -p "$(dirname "$1")"; cat > "$1"; }
note()  { mkdir -p "$(dirname "$1")"; cat > "$1"; }
gitinit() {
  local p="$1"
  if [ ! -d "$p/.git" ]; then
    git -C "$p" init -q -b main
    git -C "$p" -c user.email=alex@stark.local -c user.name="Alex Stark" \
        commit --allow-empty -q -m "seed: project bootstrap"
  fi
}

############################################################
# 1. homelab-proxmox  (git + terraform + wip)
############################################################
mkdir -p homelab-proxmox
write homelab-proxmox/.base.yaml <<'YAML'
description: Proxmox cluster IaC — VM/LXC layout, cloud-init, backup jobs.
wip: true
tags:
  - homelab
  - proxmox
  - infra:hypervisor
  - lang:terraform
  - prio:high
YAML
write homelab-proxmox/README.md <<'MD'
# homelab-proxmox

Terraform + cloud-init for the 3-node Proxmox cluster.

- `pve-01.lan` — Intel NUC, control + storage
- `pve-02.lan` — Ryzen mini-PC, compute
- `pve-03.lan` — old Dell Optiplex, witness

```sh
terraform init
terraform plan -var-file=secrets.tfvars
```
MD
write homelab-proxmox/main.tf <<'TF'
terraform {
  required_providers {
    proxmox = { source = "telmate/proxmox", version = "~> 3.0" }
  }
}

resource "proxmox_vm_qemu" "k3s_master" {
  name        = "k3s-master-01"
  target_node = "pve-01"
  clone       = "ubuntu-2404-cloudinit"
  cores       = 4
  memory      = 8192
  agent       = 1
}
TF
write homelab-proxmox/NOTES.md <<'MD'
# homelab-proxmox

## Log

### 2026-05-18 09:42
Cluster quorum dropped after pve-03 reboot — manual `pvecm e 1` to
recover. Need to investigate corosync timeout settings.

### 2026-05-12 19:10
Migrated k3s-master to ZFS-backed dataset for snapshot rollback.
MD
gitinit homelab-proxmox

############################################################
# 2. homelab-truenas  (git + readme)
############################################################
mkdir -p homelab-truenas/configs
write homelab-truenas/.base.yaml <<'YAML'
description: TrueNAS SCALE — pool layout, snapshot/replication policy.
tags:
  - homelab
  - truenas
  - infra:storage
YAML
write homelab-truenas/README.md <<'MD'
# homelab-truenas

24-bay Supermicro, 4x6-wide RAIDZ2 + 2x mirror nvme cache.
Hourly snapshots, nightly replication to backup pool.
MD
write homelab-truenas/configs/replication.yaml <<'YAML'
source: tank/data
target: backup/data
schedule: "0 2 * * *"
retention: 30d
YAML
gitinit homelab-truenas

############################################################
# 3. k3s-cluster (k8s manifests, wip)
############################################################
mkdir -p k3s-cluster/apps/grafana k3s-cluster/apps/longhorn
write k3s-cluster/.base.yaml <<'YAML'
description: Personal k3s cluster — kustomize overlays + helm charts.
wip: true
tags:
  - homelab
  - k8s
  - helm
  - lang:yaml
YAML
write k3s-cluster/README.md <<'MD'
# k3s-cluster

Argo-CD bootstraps `apps/` against this branch.
MD
write k3s-cluster/kustomization.yaml <<'YAML'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - apps/grafana
  - apps/longhorn
YAML
write k3s-cluster/apps/grafana/Chart.yaml <<'YAML'
apiVersion: v2
name: grafana
version: 0.1.0
dependencies:
  - name: grafana
    version: 8.5.x
    repository: https://grafana.github.io/helm-charts
YAML
write k3s-cluster/apps/longhorn/Chart.yaml <<'YAML'
apiVersion: v2
name: longhorn
version: 0.1.0
YAML
gitinit k3s-cluster

############################################################
# 4. home-assistant (smarthome, hass)
############################################################
mkdir -p home-assistant/automations home-assistant/blueprints
write home-assistant/.base.yaml <<'YAML'
description: Home Assistant config — Zigbee2MQTT, Frigate NVR, NSPanel.
tags:
  - smarthome
  - hass
  - zigbee
  - secrets
YAML
write home-assistant/README.md <<'MD'
# home-assistant

YAML config for `hass.lan`. Secrets live in `secrets.yaml` (gitignored).
MD
write home-assistant/configuration.yaml <<'YAML'
homeassistant:
  name: Stark Manor
  unit_system: metric
  time_zone: Europe/Oslo

mqtt:
  broker: mqtt.lan
  username: !secret mqtt_user
  password: !secret mqtt_pw

automation: !include_dir_merge_list automations/
YAML
write home-assistant/automations/morning.yaml <<'YAML'
- alias: Morning ramp
  trigger:
    - platform: time
      at: "06:45:00"
  action:
    - service: light.turn_on
      target: { area_id: bedroom }
      data: { brightness_pct: 20, transition: 600 }
YAML
write home-assistant/NOTES.md <<'MD'
# home-assistant

## Log

### 2026-05-21 22:03
Zigbee mesh keeps dropping the kitchen sensor. Suspect channel
collision with neighbour's wifi — try ch 25.
MD
gitinit home-assistant

############################################################
# 5. esp32-tempsensor (platformio, embedded, wip)
############################################################
mkdir -p esp32-tempsensor/src esp32-tempsensor/include
write esp32-tempsensor/.base.yaml <<'YAML'
description: ESP32 + SHT41 temp/humidity sensor → MQTT → HASS.
wip: true
tags:
  - esp32
  - embedded
  - lang:cpp
  - smarthome
YAML
write esp32-tempsensor/README.md <<'MD'
# esp32-tempsensor

```sh
pio run -t upload
pio device monitor
```
MD
write esp32-tempsensor/platformio.ini <<'INI'
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
lib_deps =
  knolleary/PubSubClient
  sensirion/Sensirion I2C SHT4x
monitor_speed = 115200
INI
write esp32-tempsensor/src/main.cpp <<'CPP'
#include <Arduino.h>
#include <WiFi.h>

void setup() { Serial.begin(115200); }
void loop()  { delay(1000); }
CPP

############################################################
# 6. raspi-pihole (ansible)
############################################################
mkdir -p raspi-pihole/roles/pihole
write raspi-pihole/.base.yaml <<'YAML'
description: Pi-Hole on Raspberry Pi 4 — Ansible-managed.
tags:
  - raspi
  - homelab
  - infra:network
  - ansible
YAML
write raspi-pihole/README.md <<'MD'
# raspi-pihole

```sh
ansible-playbook -i hosts.ini playbook.yml
```
MD
write raspi-pihole/playbook.yml <<'YAML'
- hosts: pihole
  become: true
  roles:
    - pihole
YAML
write raspi-pihole/ansible.cfg <<'INI'
[defaults]
inventory = hosts.ini
host_key_checking = False
INI
write raspi-pihole/hosts.ini <<'INI'
[pihole]
pihole.lan ansible_user=alex
INI
gitinit raspi-pihole

############################################################
# 7. raspi-octoprint  (no git, only readme — shows GIT-less row)
############################################################
mkdir -p raspi-octoprint
write raspi-octoprint/.base.yaml <<'YAML'
description: OctoPrint on Pi Zero 2 W — Ender 3 print server.
tags:
  - raspi
  - 3dprint
YAML
write raspi-octoprint/README.md <<'MD'
# raspi-octoprint

URL: http://octoprint.lan
Webcam: mjpg-streamer @ 5fps
MD

############################################################
# 8. nspanel-firmware.fork  (fork suffix)
############################################################
mkdir -p nspanel-firmware.fork/src
write nspanel-firmware.fork/.base.yaml <<'YAML'
description: Personal fork of nspanel-haui — custom UI screens.
tags:
  - nspanel
  - smarthome
  - esp32
  - fork
YAML
write nspanel-firmware.fork/README.md <<'MD'
# nspanel-firmware (fork)

Upstream: https://github.com/joBr99/nspanel-lovelace-ui
Local patches in `patches/`.
MD
write nspanel-firmware.fork/platformio.ini <<'INI'
[env:nspanel]
platform = espressif32
board = esp32dev
framework = espidf
INI
gitinit nspanel-firmware.fork

############################################################
# 9. terraform-aws-baseline (worktree parent — git init w/ branches)
############################################################
mkdir -p terraform-aws-baseline/modules/vpc
write terraform-aws-baseline/.base.yaml <<'YAML'
description: Org-wide AWS baseline — accounts, OUs, SSO, guardrails.
tags:
  - work
  - cloud:aws
  - lang:terraform
  - prio:high
  - secrets
YAML
write terraform-aws-baseline/README.md <<'MD'
# terraform-aws-baseline

Terragrunt-wrapped baseline applied per account.

```sh
terragrunt run-all plan
```
MD
write terraform-aws-baseline/main.tf <<'TF'
module "vpc" {
  source = "./modules/vpc"
  cidr   = var.cidr
}
TF
write terraform-aws-baseline/modules/vpc/main.tf <<'TF'
resource "aws_vpc" "this" {
  cidr_block = var.cidr
}

variable "cidr" { type = string }
TF
write terraform-aws-baseline/NOTES.md <<'MD'
# terraform-aws-baseline

## Log

### 2026-05-23 14:00
Spinning out a worktree for the EKS module so I can keep the SCP
patch branch in `main` clean.
MD
gitinit terraform-aws-baseline

############################################################
# 10. terraform-gcp-vpc
############################################################
mkdir -p terraform-gcp-vpc
write terraform-gcp-vpc/.base.yaml <<'YAML'
description: Shared-VPC scaffolding for the staging GCP project.
tags:
  - work
  - cloud:gcp
  - lang:terraform
YAML
write terraform-gcp-vpc/README.md <<'MD'
# terraform-gcp-vpc
MD
write terraform-gcp-vpc/main.tf <<'TF'
resource "google_compute_network" "vpc" {
  name                    = "staging-vpc"
  auto_create_subnetworks = false
}
TF
gitinit terraform-gcp-vpc

############################################################
# 11. kubectl-helper (go cli)
############################################################
mkdir -p kubectl-helper/cmd
write kubectl-helper/.base.yaml <<'YAML'
description: Personal kubectl wrapper — context picker + pod-grep.
tags:
  - lang:go
  - cli
  - work
  - k8s
YAML
write kubectl-helper/README.md <<'MD'
# kubectl-helper

```sh
go install ./cmd/kx
kx ctx
kx pgrep nginx
```
MD
write kubectl-helper/go.mod <<'GO'
module github.com/alexstark/kubectl-helper

go 1.23
GO
write kubectl-helper/cmd/main.go <<'GO'
package main

func main() {}
GO
gitinit kubectl-helper

############################################################
# 12. aws-cost-report (python, secrets tag)
############################################################
mkdir -p aws-cost-report/src/aws_cost_report
write aws-cost-report/.base.yaml <<'YAML'
description: Pulls Cost Explorer rollups, posts a Slack digest.
tags:
  - lang:python
  - cloud:aws
  - scripting
  - secrets
YAML
write aws-cost-report/README.md <<'MD'
# aws-cost-report

```sh
uv sync
uv run aws-cost-report --month 2026-05
```
MD
write aws-cost-report/pyproject.toml <<'TOML'
[project]
name = "aws-cost-report"
version = "0.2.0"
requires-python = ">=3.12"
dependencies = ["boto3>=1.35", "slack-sdk>=3.27"]

[project.scripts]
aws-cost-report = "aws_cost_report:main"
TOML
write aws-cost-report/src/aws_cost_report/__init__.py <<'PY'
def main() -> None:
    print("aws-cost-report stub")
PY
write aws-cost-report/NOTES.md <<'MD'
# aws-cost-report

## Log

### 2026-05-02 08:15
Cost Explorer started returning empty pages for May — pagination bug
in boto3 1.35.4. Pinning to 1.35.2 fixed it.
MD
gitinit aws-cost-report

############################################################
# 13. dotfiles
############################################################
mkdir -p dotfiles/fish/conf.d dotfiles/nvim
write dotfiles/.base.yaml <<'YAML'
description: Cross-host dotfiles — fish, nvim, kitty, tmux, git.
tags:
  - dotfiles
  - linux
  - prio:high
YAML
write dotfiles/README.md <<'MD'
# dotfiles

```sh
./install.sh
```
MD
write dotfiles/install.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
stow -t "$HOME" fish nvim kitty tmux git
SH
chmod +x dotfiles/install.sh
write dotfiles/fish/conf.d/aliases.fish <<'FISH'
alias g  'git'
alias k  'kubectl'
alias tf 'terraform'
alias hb 'b'
FISH
gitinit dotfiles

############################################################
# 14. arch-install-notes (no git, just markdown)
############################################################
mkdir -p arch-install-notes
write arch-install-notes/.base.yaml <<'YAML'
description: Reinstall recipe — ZFS-on-root + secure boot + ssh keys.
tags:
  - linux
  - notes
  - prio:low
YAML
write arch-install-notes/README.md <<'MD'
# arch-install-notes

Step-by-step for a fresh Arch + ZFS install.
MD
write arch-install-notes/NOTES.md <<'MD'
# arch-install-notes

## Disks
- nvme0n1 → root (zfs)
- nvme1n1 → home (zfs)

## Pacstrap
```
pacstrap -K /mnt base linux-zen zfs-dkms
```
MD

############################################################
# 15. rust-port-scanner (wip, rust)
############################################################
mkdir -p rust-port-scanner/src
write rust-port-scanner/.base.yaml <<'YAML'
description: Async TCP scanner — learning tokio + ratatui.
wip: true
tags:
  - lang:rust
  - networking
  - cli
YAML
write rust-port-scanner/README.md <<'MD'
# rust-port-scanner

```sh
cargo run --release -- 192.168.1.0/24
```
MD
write rust-port-scanner/Cargo.toml <<'TOML'
[package]
name = "rust-port-scanner"
version = "0.1.0"
edition = "2024"

[dependencies]
tokio    = { version = "1", features = ["full"] }
ratatui  = "0.28"
TOML
write rust-port-scanner/src/main.rs <<'RS'
fn main() {
    println!("scan stub");
}
RS
gitinit rust-port-scanner

############################################################
# 16. go-prometheus-exporter
############################################################
mkdir -p go-prometheus-exporter
write go-prometheus-exporter/.base.yaml <<'YAML'
description: Prometheus exporter for the homelab UPS via NUT.
tags:
  - lang:go
  - observability
  - homelab
YAML
write go-prometheus-exporter/README.md <<'MD'
# go-prometheus-exporter

NUT → Prometheus. Listens on :9115.
MD
write go-prometheus-exporter/go.mod <<'GO'
module github.com/alexstark/nut-exporter

go 1.23

require github.com/prometheus/client_golang v1.20.5
GO
write go-prometheus-exporter/main.go <<'GO'
package main

func main() {}
GO
gitinit go-prometheus-exporter

############################################################
# 17. bash-backup-scripts
############################################################
mkdir -p bash-backup-scripts
write bash-backup-scripts/.base.yaml <<'YAML'
description: Restic snapshots + healthcheck.io ping.
tags:
  - lang:bash
  - scripting
  - linux
  - homelab
YAML
write bash-backup-scripts/README.md <<'MD'
# bash-backup-scripts

Cron entries: `crontab -l | grep restic`.
MD
write bash-backup-scripts/backup.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
restic backup /srv/data --tag nightly
curl -fsS https://hc-ping.com/$HC_UUID > /dev/null
SH
chmod +x bash-backup-scripts/backup.sh
gitinit bash-backup-scripts

############################################################
# 18. notes-cve-2025-12345 (security wip)
############################################################
mkdir -p notes-cve-2025-12345
write notes-cve-2025-12345/.base.yaml <<'YAML'
description: Triage notes for CVE-2025-12345 (containerd path traversal).
wip: true
tags:
  - security
  - cve
  - k8s
  - prio:high
YAML
write notes-cve-2025-12345/NOTES.md <<'MD'
# CVE-2025-12345

Affected: containerd <= 1.7.22 when run with runc fallback.
Internal exposure: 3 EKS clusters on 1.27. Bump to 1.7.23 staged.

## Log

### 2026-05-22 11:00
Confirmed exploit reproduces in lab. Drafting internal advisory.
MD

############################################################
# 19. cloud-cost-dashboard (python + ts)
############################################################
mkdir -p cloud-cost-dashboard/backend/src cloud-cost-dashboard/frontend/src
write cloud-cost-dashboard/.base.yaml <<'YAML'
description: FastAPI + React dashboard — multi-cloud cost rollups.
tags:
  - work
  - webdev
  - lang:python
  - lang:typescript
  - cloud:aws
  - cloud:gcp
YAML
write cloud-cost-dashboard/README.md <<'MD'
# cloud-cost-dashboard

```sh
just dev
```
MD
write cloud-cost-dashboard/backend/pyproject.toml <<'TOML'
[project]
name = "ccd-backend"
version = "0.0.1"
requires-python = ">=3.12"
dependencies = ["fastapi", "uvicorn[standard]"]
TOML
write cloud-cost-dashboard/pyproject.toml <<'TOML'
[project]
name = "cloud-cost-dashboard"
version = "0.0.1"
requires-python = ">=3.12"
TOML
write cloud-cost-dashboard/frontend/package.json <<'JSON'
{
  "name": "ccd-frontend",
  "version": "0.0.1",
  "private": true,
  "dependencies": {
    "react": "^19.0.0",
    "vite": "^6.0.0"
  }
}
JSON
write cloud-cost-dashboard/package.json <<'JSON'
{
  "name": "cloud-cost-dashboard",
  "private": true,
  "workspaces": ["frontend"]
}
JSON
write cloud-cost-dashboard/NOTES.md <<'MD'
# cloud-cost-dashboard

## Log

### 2026-05-15 16:40
Switched from polling to SSE for live cost streams — frontend now
holds a single connection per session.
MD
gitinit cloud-cost-dashboard

############################################################
# 20. talk-cloudnative-2026
############################################################
mkdir -p talk-cloudnative-2026
write talk-cloudnative-2026/.base.yaml <<'YAML'
description: KubeCon EU 2026 talk — "Cold Incident Response at Scale".
tags:
  - talk
  - public
  - k8s
  - content
YAML
write talk-cloudnative-2026/README.md <<'MD'
# talk-cloudnative-2026

Reveal.js deck + speaker notes. Dry-run with team 2026-06-01.
MD
write talk-cloudnative-2026/slides.md <<'MD'
# Cold Incident Response at Scale

---

## Who am I
- 8 years SRE
- Homelab nut
- @alexstark

---

## What "cold" means
...
MD

############################################################
# 21. 2026-04-15_meeting-notes-q2 (date-prefixed active project)
############################################################
mkdir -p "2026-04-15_meeting-notes-q2"
write "2026-04-15_meeting-notes-q2/.base.yaml" <<'YAML'
description: Q2 planning meeting — action items + decisions.
tags:
  - work
  - meeting
  - notes
YAML
write "2026-04-15_meeting-notes-q2/NOTES.md" <<'MD'
# Q2 planning — 2026-04-15

Attendees: Alex, Priya, Sam, Lena

## Decisions
- Pause GCP migration until Q3
- Hire 1x platform eng
- Adopt internal cost-dashboard cluster-wide

## Action items
- [ ] @alex — draft platform-eng JD by 04-22
- [x] @priya — finalize FY26 budget
MD

############################################################
# 22. recipes
############################################################
mkdir -p recipes
write recipes/.base.yaml <<'YAML'
description: Personal recipe book — markdown, one file per dish.
tags:
  - personal
YAML
write recipes/README.md <<'MD'
# recipes
MD
write recipes/sourdough.md <<'MD'
# Sourdough

500g flour, 350g water, 100g starter, 10g salt.
MD

############################################################
# 23. homebanking-export.tmp (scratch + finance)
############################################################
mkdir -p homebanking-export.tmp
write homebanking-export.tmp/.base.yaml <<'YAML'
description: Throwaway script to flatten DNB CSV exports.
tags:
  - scratch
  - finance
  - lang:python
YAML
write homebanking-export.tmp/flatten.py <<'PY'
import csv, sys
for row in csv.DictReader(sys.stdin, delimiter=";"):
    print(row["Dato"], row["Beløp"], row["Tekst"])
PY

############################################################
# 24. 2026-05-20_random-scratch.tmp (date + tmp scratch)
############################################################
mkdir -p "2026-05-20_random-scratch.tmp"
write "2026-05-20_random-scratch.tmp/.base.yaml" <<'YAML'
tags:
  - scratch
YAML
: > "2026-05-20_random-scratch.tmp/scratchpad.txt"

echo "active projects done."
