QUADS RoCE Switch Configuration Tool
=====================================

Standalone tool for managing RoCE (RDMA over Converged Ethernet) QoS/CoS configuration on Juniper switches managed by QUADS. RoCE layers on top of existing QinQ configurations and is applied per-cloud.

   * [Overview](#overview)
   * [Prerequisites](#prerequisites)
   * [Usage](#usage)
      * [Install Base RoCE Config](#install-base-roce-config)
      * [Configure Interfaces](#configure-interfaces)
      * [Remove Interface Config](#remove-interface-config)
      * [Uninstall Base RoCE Config](#uninstall-base-roce-config)
      * [Dry Run](#dry-run)
   * [Typical Workflow](#typical-workflow)
   * [What It Does](#what-it-does)
      * [Base Switch Config](#base-switch-config)
      * [Per-Interface Config](#per-interface-config)
   * [Behavior Details](#behavior-details)
   * [Adding Other Switch Vendors](#adding-other-switch-vendors)

## Overview

The tool provides four mutually exclusive actions to manage the RoCE lifecycle on switches:

| Action | Purpose |
|--------|---------|
| `--install-roce` | Install base RoCE QoS config to switches (one-time setup) |
| `--configure` | Apply per-interface RoCE bindings after QUADS allocation |
| `--remove` | Remove per-interface RoCE bindings (return to base QinQ) |
| `--uninstall-roce` | Remove base RoCE config from switches |

It discovers all hosts assigned to a cloud, groups their interfaces by switch IP, and applies or removes configuration via SSH.

## Prerequisites

   - The cloud must have an active assignment
   - Host interfaces must have `switch_ip` and `switch_port` defined
   - SSH key-based access to Juniper switches via the `junos_username` configured in `quads.yml`

## Usage

### Install Base RoCE Config

One-time setup per switch. Installs CoS classifiers, forwarding classes, schedulers, drop profiles, congestion notification, rewrite rules, and the RoCE-Ingress-Map firewall filter. Skips switches that already have it.

```bash
PYTHONPATH=src python -m quads.tools.roce --cloud cloud02 --install-roce
```

### Configure Interfaces

Apply per-interface RoCE bindings after a QUADS allocation. Requires base config to already be installed (will error if not).

```bash
PYTHONPATH=src python -m quads.tools.roce --cloud cloud02 --configure
```

### Remove Interface Config

Remove per-interface RoCE bindings, returning interfaces to base QinQ. Leaves base RoCE config intact on the switch.

```bash
PYTHONPATH=src python -m quads.tools.roce --cloud cloud02 --remove
```

### Uninstall Base RoCE Config

Remove all base RoCE config from the switches. Skips switches that don't have it.

```bash
PYTHONPATH=src python -m quads.tools.roce --cloud cloud02 --uninstall-roce
```

### Dry Run

Add `--dry-run` to any action to see what would happen without making changes. No SSH connections are made.

```bash
PYTHONPATH=src python -m quads.tools.roce --cloud cloud02 --configure --dry-run
```

Example output:

```
Configuring RoCE interfaces for cloud cloud02: 2 switch(es)
[DRY RUN] Would configure interfaces on switch: 10.1.36.200
[DRY RUN] Would apply interface config for: et-0/0/7:0
[DRY RUN] Would apply interface config for: et-0/0/7:1
[DRY RUN] Would configure interfaces on switch: 10.1.36.201
[DRY RUN] Would apply interface config for: et-0/0/8:0
```

## Typical Workflow

```
1. Install base RoCE on switches    --install-roce    (once per switch)
2. QUADS allocates hosts to cloud
3. Apply per-interface RoCE config   --configure       (after allocation)
4. Hosts are used with RoCE
5. Remove per-interface config       --remove          (before reallocation)
6. QUADS deallocates hosts
```

Repeat steps 2-6 for each allocation cycle. Step 1 only needs to run once per switch unless `--uninstall-roce` is used.

## What It Does

### Base Switch Config

Applied once per switch via `--install-roce`. The tool checks for existing config by querying `show configuration class-of-service | display set | match STORAGE-CLASSIFIER` and skips if already present.

**Class-of-service classifiers** - DSCP and IEEE 802.1p classifiers for NVMe-TCP and RoCE lossless traffic.

**Drop profiles** - ECN-based drop profile for RoCE with fill-level thresholds at 55% and 90%.

**Forwarding classes** - Four traffic classes:

| Class | Queue | Notes |
|-------|-------|-------|
| best-effort | 0 | Default traffic |
| roce-lossless | 3 | No-loss, PFC enabled |
| nvme-tcp | 4 | Storage traffic |
| network-control | 7 | Control plane |

**Scheduler allocation:**

| Class | Bandwidth | Priority |
|-------|-----------|----------|
| roce-lossless | 50% | low |
| nvme-tcp | 30% | low |
| qinq (best-effort) | 15% | low |
| network-control | 5% | strict-high |

**Congestion notification** - PFC enabled for IEEE 802.1p code-point 011 (priority 3).

**Firewall filter (RoCE-Ingress-Map)** - Classifies ingress traffic:

   - 802.1p priority 4 -> nvme-tcp forwarding class
   - 802.1p priority 3 -> roce-lossless forwarding class
   - DSCP 26 -> roce-lossless forwarding class
   - All other traffic -> accept (default)

### Per-Interface Config

Applied to each host-facing switch port via `--configure`:

```
set interfaces <port> unit 0 family ethernet-switching filter input RoCE-Ingress-Map
set class-of-service interfaces <port> congestion-notification-profile storage-cnp
set class-of-service interfaces <port> scheduler-map storage-fabric-map
```

Removed via `--remove`:

```
delete interfaces <port> unit 0 family ethernet-switching filter input RoCE-Ingress-Map
delete class-of-service interfaces <port> congestion-notification-profile
delete class-of-service interfaces <port> scheduler-map
```

## Behavior Details

   - **Idempotent** - Junos `set` and `delete` commands are safe to re-apply.
   - **Error handling** - If a switch connection fails, the tool logs the error and continues to the next switch. If an individual interface operation fails, remaining interfaces on that switch still get processed.
   - **Single SSH session per switch** - One pexpect SSH connection per switch, reused for all operations on that switch.
   - **Exit codes** - 0 if everything succeeded, 1 if any operation failed.

## Adding Other Switch Vendors

The Juniper implementation lives in `src/quads/tools/external/juniper_roce.py`. To add support for another vendor (e.g. Arista, Cisco):

   1. Create `src/quads/tools/external/<vendor>_roce.py` with the same interface: `has_base_config()`, `connect()`, `apply_base_config()`, `apply_interface_config(switch_port)`, `remove_base_config()`, `remove_interface_config(switch_port)`, `close()`
   2. Populate the vendor-specific commands
   3. Update `roce.py` to select the appropriate implementation based on switch vendor
