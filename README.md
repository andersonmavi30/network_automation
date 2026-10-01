# Network Automation (NetDevOps Labs)

🇨🇴 [Español](README.es.md)

A **network automation repository built as Infrastructure as Code** on Cisco devices (IOSv, CSR1000v) in a lab environment (PNETLab). It is organized as a series of progressive labs (**Lab 2 to Lab 6**), each building a complete network configuration and validation pipeline.

This is not an application or an installable package: it is a collection of pipelines where **Git is the Source of Truth** and every network change follows the same flow:

1. **Intent** — declarative topology/intent in YAML versioned in Git.
2. **Render** — configuration generation with **Jinja2** templates.
3. **Pre-deploy validation** with **Batfish** (labs 5 and 6).
4. **Precheck** — verification of the current device state.
5. **Deploy** — with Ansible (`cisco.ios.ios_config`, `network_cli` connection + libssh) or Netmiko (lab 3).
6. **Postcheck** and evidence collection with **Nornir**.
7. **Validation** with **pyATS / Genie** and artifact generation in `artifacts/`.
8. **Rollback / cleanup** — pre-change backups protect deployments and Lab 6 can automatically restore configuration if the deploy fails.

## Platform components

| Component | URL / Detail | Role |
|-----------|--------------|------|
| **NetBox** | `http://192.168.1.16:8000` | Source of Truth and dynamic inventory (`netbox.netbox.nb_inventory`) |
| **AWX** | `http://192.168.1.13:30143` | Job Template orchestrator |
| **Jenkins** | — | Triggers AWX Job Templates via REST API (Lab 5), with automatic rollback |
| **Management network** | `172.30.30.0/26` | OOB connectivity to all devices |

## Repository structure

```
├── ansible.cfg                     # Global config: NetBox inventory, legacy libssh
├── collections/requirements.yml    # Required Ansible collections
├── inventories/netbox/             # Dynamic inventory (nb_inventory plugin)
├── group_vars/                     # Cisco IOS connection vars (root)
├── execution-environments/         # Containerfiles for AWX Execution Environments
│   ├── iosv/                       # Minimal EE (ansible-core 2.15.13) for IOSv
│   └── lab5-csr1000v/              # Full EE (nornir, pyats, genie, pybatfish...)
├── scripts/netbox/                 # NetBox bootstrap from intent (labs 4 and 5)
├── shared/                         # Shared Nornir inventory and scripts (Lab 2)
├── playbooks/awx/                  # AWX smoke test (show_version.yml)
├── docs/                           # Phase documentation
├── lab2-inter-vlan/                # Lab 2: Inter-VLAN routing (Ansible pipeline)
├── lab3-router-on-a-stick/         # Lab 3: Router-on-a-Stick (Python pipeline)
├── lab4-ospf-ansible-pipeline/     # Lab 4: OSPF single-area (100% Ansible)
├── lab5-ospf-multiarea-jenkins-pipeline/  # Lab 5: OSPF multi-area + Jenkins/AWX
└── lab6-eigrp-cicd-pipeline/       # Lab 6: EIGRP + CI/CD + APIs (in progress)
```

## Labs

Each lab is **self-contained** (its own `ansible.cfg`, inventories, vars and `artifacts/` where applicable).

### Lab 2 — Inter-VLAN Routing (`lab2-inter-vlan/`)

Pure Ansible pipeline. `playbooks/lab2_full_change.yml` imports the phases `render → precheck → deploy → postcheck` and then invokes the Nornir/Genie scripts from `shared/scripts/`.

- Intent: `intent/lab2_intent.yml` (VLANs 10/20/30/40, switches SW_DMZ, DSW1, ASW1, ASW2).
- Jinja2 templates in `templates/`.

### Lab 3 — Router-on-a-Stick (`lab3-router-on-a-stick/`)

Same flow as Lab 2 but orchestrated with **Python scripts**: `scripts/lab3_full_change.py` runs `render → precheck → deploy (Netmiko) → postcheck → nornir → genie`.

- Devices: R1 (router), SW_DMZ, ASW1, ASW2.
- Note: the scripts have hardcoded lab credentials (`netdevops`/`cisco`); this is a known historical exception, not a pattern to replicate.

### Lab 4 — OSPF Single-Area (`lab4-ospf-ansible-pipeline/`)

Orchestrated 100% by Ansible with numbered playbooks `00_`–`07_`; `playbooks/lab4_pipeline.yml` imports them in order.

- Source of truth: `intent/lab4_source_of_truth.yml`; dynamic inventory from NetBox (local `host_vars/` and `group_vars/`).
- Topology: R1–R4 (OSPF area 0, /30 links `10.0.x.x`), SW_DMZ, ASW1, PC1 (LAN `10.10.30.0/24`). See `lab4-ospf-ansible-pipeline/README.md` for the full addressing.
- **Lab rule**: only the management configuration is done manually via CLI; everything else is applied by Ansible.

### Lab 5 — OSPF Multi-Area + Jenkins (`lab5-ospf-multiarea-jenkins-pipeline/`)

Multi-area OSPF on CSR1000v with Ansible roles (`lab5_render`, `lab5_batfish`, `lab5_precheck`, `lab5_ospf`, `lab5_postcheck`, `lab5_nornir`, `lab5_pyats`, `lab5_validate`, `lab5_cleanup`). `playbooks/lab5_pipeline.yml` imports playbooks `01_`–`08_`.

- Introduces **Batfish** as a pre-deploy validation gate.
- The `Jenkinsfile` locates the AWX Job Template by name, launches it **only if `EXECUTE_PIPELINE=true`**, waits for the result and, on failure, triggers an automatic rollback (template ID 16).
- Credentials in `group_vars/vault.yml` (Ansible Vault).

### Lab 6 — EIGRP + CI/CD + APIs (`lab6-eigrp-cicd-pipeline/`)

Declarative topology in `vars/topology.yml` (6 CSR1000v, LAB6). API-first approach:

- `scripts/sync_netbox.py` — syncs the Git topology into NetBox.
- `validation/validate_netbox_sot.py` — validates NetBox against Git (read-only).
- `scripts/render_eigrp.py` and `scripts/render_batfish_candidates.py` — config rendering and Batfish snapshots.
- Playbooks `00_`–`04_` currently cover cleanup/rollback, pre-change backup, Batfish pre-deploy validation, precheck and deploy.
- `04_deploy.yml` runs the backup and deploy roles, validates that a usable pre-change backup exists before modifying the router, protects the management interface, configures service interfaces and EIGRP, and performs an immediate configuration rollback from backup if the deploy block fails and `lab6_rollback_on_failure` is enabled.
- `00_cleanup.yml` invokes `lab6_cleanup` and can target all routers or a subset through `target_hosts`; it removes the Lab 6 EIGRP process, cleans only non-management interfaces and saves the resulting configuration.
- Implemented roles: `lab6_backup`, `lab6_batfish`, `lab6_precheck`, `lab6_deploy` and `lab6_cleanup`.
- Current Lab 6 artifacts are organized under `artifacts/backups/`, `artifacts/batfish/` and `artifacts/precheck/`.

## Prerequisites

- Automation environment Python: `/opt/automation/venv/bin/python`.
- Ansible with the collections from `collections/requirements.yml`:
  ```bash
  ansible-galaxy collection install -r collections/requirements.yml
  ```
- Access to NetBox, AWX and the management network `172.30.30.0/26`.

### Environment variables

| Variable | Usage |
|----------|-------|
| `NETBOX_TOKEN` | **Required** for NetBox API scripts (`bootstrap_*`, `sync_netbox.py`, `validate_netbox_sot.py`) |
| `NETBOX_URL` | Optional (default `http://192.168.1.16:8000`) |
| `IOS_PASSWORD` | SSH password for IOS devices in the root inventory and Lab 4 |
| `awx-api-token` | Jenkins credential holding the AWX API token (Lab 5) |

### Ansible Vault

`lab5*/group_vars/vault.yml` and `lab6*/group_vars/vault.yml` are encrypted and define `vault_ios_username`, `vault_ios_password`, `vault_ios_enable_password`. Run with `--ask-vault-pass` or a vault password file.

## Main commands

From the repository root, unless otherwise noted:

```bash
# Verify the NetBox dynamic inventory
ansible-inventory --graph

# Reachability of inventory hosts
ansible all -m ansible.builtin.command -a 'ping -c 2 {{ ansible_host }}' -c local

# AWX smoke test
ansible-playbook playbooks/awx/show_version.yml

# Lab 2 (full Ansible pipeline)
ansible-playbook lab2-inter-vlan/playbooks/lab2_full_change.yml

# Lab 3 (full Python pipeline)
python3 lab3-router-on-a-stick/scripts/lab3_full_change.py

# Lab 4 (uses its local ansible.cfg)
cd lab4-ospf-ansible-pipeline && ansible-playbook playbooks/lab4_pipeline.yml

# Lab 5 (requires vault password)
cd lab5-ospf-multiarea-jenkins-pipeline && ansible-playbook playbooks/lab5_pipeline.yml --ask-vault-pass

# Lab 6
cd lab6-eigrp-cicd-pipeline
export NETBOX_TOKEN=<token>
python3 scripts/sync_netbox.py                  # sync NetBox
python3 validation/validate_netbox_sot.py       # validate NetBox vs Git
python3 scripts/render_eigrp.py                 # render configs to configs/
ansible-playbook playbooks/01_backup_prechange.yml --ask-vault-pass
ansible-playbook playbooks/02_batfish_predeploy.yml --ask-vault-pass
ansible-playbook playbooks/03_precheck.yml --ask-vault-pass
ansible-playbook playbooks/04_deploy.yml --ask-vault-pass

# Lab 6 cleanup / rollback (all routers by default)
ansible-playbook playbooks/00_cleanup.yml --ask-vault-pass

# Example: cleanup only selected routers
ansible-playbook playbooks/00_cleanup.yml --ask-vault-pass -e 'target_hosts=R1:R2'

# Build Execution Environments (example)
cd execution-environments/lab5-csr1000v && podman build -t ee-lab5-csr1000v .
```

## `artifacts/` convention

Each lab stores evidence in `artifacts/`:

- `rendered/` — rendered configurations (versioned in Git).
- `precheck/`, `postcheck/`, `deploy/` — evidence from each phase.
- `nornir/` — `show` outputs collected with Nornir.
- `genie/` / `pyats/` — JSON validation reports.
- `batfish/` — pre-deploy validation results.
- `backups/` — pre-change backups (some ignored in `.gitignore` due to size).

`.gitkeep` files keep empty directories under version control.

## Validation and testing

There is no traditional test framework (pytest, unit-test CI): validation is domain-specific and acts as a **pipeline gate** — each phase aborts the flow if it fails.

- **Batfish** (offline pre-deploy validation): labs 5 and 6, output in `artifacts/batfish/output/`.
- **pyATS / Genie**: parse the `show` outputs collected by Nornir and generate JSON reports; exit code ≠ 0 on any FAIL.
- **SoT validation**: `lab6*/validation/validate_netbox_sot.py` compares NetBox against `vars/topology.yml` (read-only).
- When modifying a pipeline: at minimum run `ansible-playbook --syntax-check` on the affected playbook and, if possible, a render/precheck run without deploy.

## Code conventions

- **Language**: mix of Spanish and English. Documentation, `Jenkinsfile` and recent scripts (labs 5 and 6) in **Spanish**; labs 2 and 3 in English. Keep the language of the file being edited.
- **Playbooks numbered** by phase (`00_cleanup`, `01_render`, `02_precheck`, ...) plus a `*_pipeline.yml` that only does `import_playbook` in order.
- **Ansible roles** prefixed with the lab name (`lab5_*`, `lab6_*`), with `defaults/`, `tasks/`, `vars/` and `files/` for Python scripts.
- Deployment always from a rendered file: `cisco.ios.ios_config` with `src: .../artifacts/rendered/{{ inventory_hostname }}.cfg` and `save_when`.
- All evidence is saved with `delegate_to: localhost`.
- Python scripts: `#!/usr/bin/env python3`, paths relative with `Path(__file__).resolve().parent`, console output with `[OK]` / `[FAIL]` / `[PASS]` prefixes and `sys.exit(1)` on error.

## Security considerations

- **Never** commit plaintext credentials: use Ansible Vault or environment variables (`NETBOX_TOKEN`, `IOS_PASSWORD`).
- Connections use `ansible.netcommon.network_cli` with **libssh** and legacy algorithms (`ssh-rsa`, `diffie-hellman-group-exchange-sha1`, ...) because the lab IOSv devices are old; `host_key_checking = False` is a lab environment requirement, **not** a general recommendation.
- NetBox scripts disable TLS verification (`verify=False`) because the lab NetBox uses HTTP/self-signed certificates; deliberate and only valid for the lab.
- The Lab 5 `Jenkinsfile` has a safe mode: without `EXECUTE_PIPELINE=true` it only validates that the Job Template exists, without launching it.

## 📄 License

This project is licensed under the [MIT License](LICENSE).

## Additional documentation

- `AGENTS.md` — detailed guide for AI agents (structure, commands, conventions).
- `lab4-ospf-ansible-pipeline/README.md` — full Lab 4 addressing and topology.
- `docs/lab4/` — phase documentation (e.g. NetBox dynamic inventory).
