#!/usr/bin/env bash
# Populates _archive/<year>/<YYYY-MM-DD>_<name>/ with realistic stubs.
set -euo pipefail
BASE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE"

write() { mkdir -p "$(dirname "$1")"; cat > "$1"; }

# 2023
mkdir -p _archive/2023/2023-02-14_thesis-final
write _archive/2023/2023-02-14_thesis-final/.base.yaml <<'YAML'
description: Master's thesis — kept for nostalgia.
tags:
  - school
  - archived
YAML
write _archive/2023/2023-02-14_thesis-final/README.md <<'MD'
# Thesis (Feb 2023)

Title: "Cold-start latency in serverless workloads"
Defended: 2023-02-14.
MD
write _archive/2023/2023-02-14_thesis-final/thesis.tex <<'TEX'
\documentclass{article}
\begin{document}
\title{Cold-start latency in serverless workloads}
\maketitle
\end{document}
TEX

# 2024
mkdir -p _archive/2024/2024-03-12_old-laptop-migration
write _archive/2024/2024-03-12_old-laptop-migration/.base.yaml <<'YAML'
description: Migration script set from the X1C7 to the Framework 13.
tags:
  - linux
  - dotfiles
  - archived
YAML
write _archive/2024/2024-03-12_old-laptop-migration/NOTES.md <<'MD'
# old-laptop-migration

Done. Kept for the rsync filter list.
MD

mkdir -p _archive/2024/2024-08-01_first-rust-tutorial/src
write _archive/2024/2024-08-01_first-rust-tutorial/.base.yaml <<'YAML'
description: Following the rust book — chapters 1-12.
tags:
  - lang:rust
  - learning
  - archived
YAML
write _archive/2024/2024-08-01_first-rust-tutorial/Cargo.toml <<'TOML'
[package]
name = "guessing-game"
version = "0.1.0"
edition = "2021"
TOML
write _archive/2024/2024-08-01_first-rust-tutorial/src/main.rs <<'RS'
fn main() { println!("guess!"); }
RS

# 2025
mkdir -p _archive/2025/2025-01-10_failed-startup-idea
write _archive/2025/2025-01-10_failed-startup-idea/.base.yaml <<'YAML'
description: "Receipts-as-a-service" — pivoted, then shelved.
tags:
  - project
  - archived
  - lang:python
YAML
write _archive/2025/2025-01-10_failed-startup-idea/README.md <<'MD'
# Receipts-as-a-Service

> RIP. Couldn't find product-market fit. Kept the OCR pipeline.
MD
write _archive/2025/2025-01-10_failed-startup-idea/pyproject.toml <<'TOML'
[project]
name = "raas"
version = "0.0.1"
TOML

mkdir -p _archive/2025/2025-06-22_homelab-v1-supermicro
write _archive/2025/2025-06-22_homelab-v1-supermicro/.base.yaml <<'YAML'
description: First-gen homelab on a single Supermicro chassis — replaced.
tags:
  - homelab
  - proxmox
  - archived
YAML
write _archive/2025/2025-06-22_homelab-v1-supermicro/README.md <<'MD'
# homelab v1

24-core E5-2680v3, 128GB ECC. Loud. Replaced by 3x mini-PC cluster.
MD

mkdir -p _archive/2025/2025-11-30_kube-the-hard-way
write _archive/2025/2025-11-30_kube-the-hard-way/.base.yaml <<'YAML'
description: Kelsey Hightower walkthrough — completed.
tags:
  - k8s
  - learning
  - archived
YAML
write _archive/2025/2025-11-30_kube-the-hard-way/NOTES.md <<'MD'
# kube-the-hard-way

Done. etcd + apiserver + kubelet by hand. Worth doing once.
MD

# 2026 (recent archive)
mkdir -p _archive/2026/2026-02-03_old-blog-engine
write _archive/2026/2026-02-03_old-blog-engine/.base.yaml <<'YAML'
description: Hugo blog — moved to a hosted Ghost instance.
tags:
  - blog
  - content
  - archived
  - lang:go
YAML
write _archive/2026/2026-02-03_old-blog-engine/README.md <<'MD'
# blog (hugo)

Replaced by Ghost @ blog.alexstark.dev.
MD
write _archive/2026/2026-02-03_old-blog-engine/config.toml <<'TOML'
baseURL  = "https://alexstark.dev/"
theme    = "papermod"
TOML

echo "archive done."
