# Lab 4 - OSPF Single Area Ansible Pipeline

## Objective

Build an Ansible-based automation pipeline to configure and validate an OSPF single-area topology.

Ansible will be the main orchestrator. It will call each phase of the lab:

- Precheck
- Render configurations
- Deploy OSPF configuration
- Postcheck
- Collect evidence
- Validate with pyATS / Genie
- Generate final artifacts

## Important rule

Only the management configuration is applied manually by CLI.

All lab configuration must be deployed by Ansible:

- Interface IP addressing
- Loopbacks
- OSPF process
- OSPF area 0
- LAN configuration
- Validation
- Artifacts

## Topology

Devices:

- SW_DMZ
- ASW1
- R1
- R2
- R3
- R4
- PC1

## Management Network

Network: 172.30.30.0/26

| Device | Management IP |
|--------|---------------|
| SW_DMZ | 172.30.30.40 |
| ASW1   | 172.30.30.41 |
| R1     | 172.30.30.42 |
| R2     | 172.30.30.43 |
| R3     | 172.30.30.44 |
| R4     | 172.30.30.45 |

## OSPF Lab Addressing

| Link | Network |
|------|---------|
| R1-R2 | 10.0.12.0/30 |
| R1-R3 | 10.0.13.0/30 |
| R2-R3 | 10.0.23.0/30 |
| R2-R4 | 10.0.24.0/30 |
| R3-R4 | 10.0.34.0/30 |

## Loopbacks

| Router | Loopback0 |
|--------|-----------|
| R1 | 1.1.1.1/32 |
| R2 | 2.2.2.2/32 |
| R3 | 3.3.3.3/32 |
| R4 | 4.4.4.4/32 |

## LAN

| Device | IP |
|--------|----|
| R1 LAN Gateway | 10.10.30.254/24 |
| PC1 | 10.10.30.1/24 |

## Final expected command

```bash
ansible-playbook playbooks/lab4_pipeline.yml
