# AGENTS.md

Guía para agentes de IA que trabajen en este repositorio. Asume que el lector no conoce el proyecto.

## Descripción general

Repositorio de **automatización de redes (NetDevOps)** organizado como una serie de laboratorios progresivos (Lab 2 a Lab 6) sobre dispositivos Cisco (IOSv, CSR1000v) en un entorno de laboratorio (PNETLab). No es una aplicación ni un paquete: es una colección de pipelines de configuración de red estilo *Infrastructure as Code*.

Flujo común de cada laboratorio (Git como Source of Truth):

1. **Intent / Topología declarativa en YAML** (versionada en Git).
2. **Render** de configuraciones con plantillas **Jinja2**.
3. **Validación pre-deploy** con **Batfish** (labs 5 y 6).
4. **Precheck** del estado actual de los dispositivos.
5. **Deploy** con Ansible (`cisco.ios.ios_config`, conexión `network_cli` + libssh) o Netmiko (lab 3).
6. **Postcheck** y recolección de evidencia con **Nornir**.
7. **Validación** con **pyATS / Genie** y generación de artefactos en `artifacts/`.

Componentes de plataforma:

- **NetBox** (`http://192.168.1.16:8000`) como Source of Truth / inventario dinámico (`netbox.netbox.nb_inventory`).
- **AWX** (`http://192.168.1.13:30143`) como orquestador de Job Templates.
- **Jenkins** dispara los Job Templates de AWX vía API REST (Lab 5).
- Red de gestión: `172.30.30.0/26`.

## Estructura del repositorio

### Raíz (compartido)

- `ansible.cfg` — configuración global; inventario por defecto `inventories/netbox/netbox_inventory.yml` (dinámico desde NetBox).
- `collections/requirements.yml` — colecciones Ansible: `netbox.netbox`, `cisco.ios`, `ansible.netcommon`, `ansible.utils`.
- `inventories/netbox/netbox_inventory.yml` — plugin `nb_inventory`; agrupa por `sites`, `device_roles`, `platforms`.
- `group_vars/platforms_cisco_ios.yml` — vars de conexión Cisco IOS (usuario `netdevops`, password desde `IOS_PASSWORD`, libssh con algoritmos legacy).
- `execution-environments/` — `Containerfile` para AWX Execution Environments:
  - `iosv/` — EE mínimo (ansible-core 2.15.13 + colecciones) para IOSv; activa `update-crypto-policies --set LEGACY`.
  - `lab5-csr1000v/` — EE completo con `nornir`, `pyats`, `genie`, `pybatfish`, `pynetbox`, `netmiko`, etc.
- `scripts/netbox/bootstrap_lab{4,5}_netbox.py` — poblan NetBox desde los archivos de intent de cada lab.
- `shared/inventories/` — inventario Nornir compartido (`nornir_hosts.yml`, `nornir_groups.yml`).
- `shared/scripts/` — scripts compartidos de Lab 2 (`collect_lab2_nornir.py`, `validate_lab2_genie.py`).
- `playbooks/awx/show_version.yml` — smoke test de AWX contra el grupo `platforms_cisco_ios`.
- `docs/` — documentación de fases (p. ej. `docs/lab4/fase4_netbox_dynamic_inventory.md`).

### Labs (cada uno es autocontenido)

- `lab2-inter-vlan/` — Inter-VLAN routing. Pipeline Ansible puro: `playbooks/lab2_full_change.yml` importa `render → precheck → deploy → postcheck` y luego invoca los scripts Nornir/Genie de `shared/scripts/`. Intent en `intent/lab2_intent.yml`, plantillas en `templates/`.
- `lab3-router-on-a-stick/` — mismo flujo pero con **scripts Python** (`scripts/lab3_full_change.py` orquesta `render → precheck → deploy (Netmiko) → postcheck → nornir → genie`). Credenciales hardcodeadas de laboratorio (`netdevops`/`cisco`).
- `lab4-ospf-ansible-pipeline/` — OSPF single-area, orquestado 100 % por Ansible con playbooks numerados `00_`–`07_`; `playbooks/lab4_pipeline.yml` los importa en orden. Source of truth en `intent/lab4_source_of_truth.yml`; inventario dinámico NetBox (`host_vars/` y `group_vars/` locales). Regla del lab: solo la configuración de gestión se hace manual por CLI; todo lo demás lo aplica Ansible.
- `lab5-ospf-multiarea-jenkins-pipeline/` — OSPF multi-área con roles Ansible (`roles/lab5_render`, `lab5_batfish`, `lab5_precheck`, `lab5_ospf`, `lab5_postcheck`, `lab5_nornir`, `lab5_pyats`, `lab5_validate`, `lab5_cleanup`). `playbooks/lab5_pipeline.yml` importa los playbooks `01_`–`08_`. El `Jenkinsfile` localiza el Job Template de AWX por nombre, lo lanza solo si `EXECUTE_PIPELINE=true`, espera el resultado y, en caso de fallo, lanza un rollback automático (template ID 16). Credenciales en `group_vars/vault.yml` (Ansible Vault).
- `lab6-eigrp-cicd-pipeline/` — EIGRP + CI/CD + APIs. Topología declarativa en `vars/topology.yml` (6 CSR1000v). Scripts Python: `scripts/sync_netbox.py` (sincroniza topología a NetBox), `validation/validate_netbox_sot.py` (valida NetBox contra Git, read-only), `scripts/render_eigrp.py`, `scripts/render_batfish_candidates.py`. Playbooks numerados `01_`–`03_` (backup pre-change, Batfish pre-deploy, precheck) con roles `lab6_*`. Los subdirectorios `batfish/`, `jenkins/`, `netconf/`, `nornir/`, `postman/`, `pyats/`, `restconf/` están vacíos o reservados para trabajo futuro.

### Convención de `artifacts/`

Cada lab guarda evidencia en `artifacts/`: `rendered/` (configs renderizadas, versionadas), `precheck/`, `postcheck/`, `deploy/`, `nornir/`, `genie|pyats/`, `batfish/`, `backups/`. Los `.gitkeep` mantienen directorios vacíos. Algunos artefactos pesados o temporales están ignorados en `.gitignore` (p. ej. backups reales pre-change y snapshots temporales de Batfish del Lab 6).

## Comandos principales

Desde la raíz del repositorio, salvo que se indique lo contrario:

```bash
# Instalar colecciones Ansible
ansible-galaxy collection install -r collections/requirements.yml

# Verificar inventario dinámico NetBox
ansible-inventory --graph

# Reachability de los hosts del inventario
ansible all -m ansible.builtin.command -a 'ping -c 2 {{ ansible_host }}' -c local

# Smoke test AWX
ansible-playbook playbooks/awx/show_version.yml

# Lab 2 (pipeline Ansible completo)
ansible-playbook lab2-inter-vlan/playbooks/lab2_full_change.yml

# Lab 3 (pipeline Python completo)
python3 lab3-router-on-a-stick/scripts/lab3_full_change.py

# Lab 4 (desde lab4-ospf-ansible-pipeline/, usa su ansible.cfg local)
cd lab4-ospf-ansible-pipeline && ansible-playbook playbooks/lab4_pipeline.yml

# Lab 5 (desde lab5-ospf-multiarea-jenkins-pipeline/; requiere vault password)
cd lab5-ospf-multiarea-jenkins-pipeline && ansible-playbook playbooks/lab5_pipeline.yml --ask-vault-pass

# Lab 6 (desde lab6-eigrp-cicd-pipeline/)
cd lab6-eigrp-cicd-pipeline
export NETBOX_TOKEN=<token>
python3 scripts/sync_netbox.py                  # sincronizar NetBox
python3 validation/validate_netbox_sot.py       # validar NetBox vs Git
python3 scripts/render_eigrp.py                 # renderizar configs a configs/
ansible-playbook playbooks/01_backup_prechange.yml --ask-vault-pass

# Construir Execution Environments (ejemplo)
cd execution-environments/lab5-csr1000v && podman build -t ee-lab5-csr1000v .
```

## Entorno y variables requeridas

- Python del entorno de automatización: `/opt/automation/venv/bin/python` (referenciado por los playbooks de Lab 2).
- Variables de entorno:
  - `NETBOX_TOKEN` — obligatorio para los scripts que hablan con la API de NetBox (`bootstrap_*`, `sync_netbox.py`, `validate_netbox_sot.py`). `NETBOX_URL` es opcional (default `http://192.168.1.16:8000`).
  - `IOS_PASSWORD` — password SSH de los dispositivos IOS en el inventario raíz y en Lab 4.
  - Jenkins: credencial `awx-api-token` (token de API de AWX).
- Ansible Vault: `lab5*/group_vars/vault.yml` y `lab6*/group_vars/vault.yml` están cifrados; definen `vault_ios_username`, `vault_ios_password`, `vault_ios_enable_password`. Ejecutar con `--ask-vault-pass` o archivo de password de vault.
- Las conexiones a dispositivos usan `ansible.netcommon.network_cli` con `ansible_network_os: cisco.ios.ios` y **libssh** con algoritmos legacy (`ssh-rsa`, `diffie-hellman-group-exchange-sha1`, etc.) porque los IOSv del laboratorio son antiguos; no quitar estos ajustes.

## Testing y validación

No hay framework de tests tradicional (no hay pytest, CI de tests unitarios, ni `package.json`/`pyproject.toml`). La "validación" es propia del dominio de redes y es **gate del pipeline**: cada fase aborta el flujo si falla.

- **Batfish** (validación offline pre-deploy): `roles/lab5_batfish/files/lab5_batfish_validate.py` y `lab6-eigrp-cicd-pipeline/roles/lab6_batfish/files/lab6_batfish_validate.py`; salida en `artifacts/batfish/output/`.
- **pyATS / Genie**: parsean `show` recogidos por Nornir y generan reportes JSON (`artifacts/genie_validation/`, `artifacts/pyats/`). Exit code != 0 si hay FAIL.
- **Validación de SoT**: `lab6*/validation/validate_netbox_sot.py` compara NetBox contra `vars/topology.yml` (solo lectura).
- Al modificar un pipeline, verificar como mínimo: `ansible-playbook --syntax-check` del playbook afectado y, si es posible, un run de render/precheck sin deploy.

## Convenciones de código

- **Idioma**: mezcla de español e inglés. La documentación, el `Jenkinsfile` y los comentarios de los scripts más recientes (labs 5 y 6) están en **español**; los labs 2 y 3 están en inglés. Mantener el idioma del archivo que se edita.
- **Playbooks numerados** por fase (`00_cleanup`, `01_render`, `02_precheck`, ...) más un `*_pipeline.yml` que solo hace `import_playbook` en orden. Las fases nuevas siguen esa numeración.
- **Roles Ansible** con prefijo del lab (`lab5_*`, `lab6_*`), cada uno con `defaults/`, `tasks/`, `vars/` (y `files/` para scripts Python que el rol ejecuta).
- Deploy de configuración siempre desde archivo renderizado: `cisco.ios.ios_config` con `src: .../artifacts/rendered/{{ inventory_hostname }}.cfg` y `save_when`. No empujar líneas sueltas de configuración si existe plantilla.
- Toda evidencia se guarda en `artifacts/` con `delegate_to: localhost`.
- Scripts Python: `#!/usr/bin/env python3`, `Path(__file__).resolve().parent` para rutas relativas al lab, salida por consola con prefijos `[OK]` / `[FAIL]` / `[PASS]`, y `sys.exit(1)` ante error para que el pipeline se detenga.

## Consideraciones de seguridad

- **Nunca** commitear credenciales en claro: usar Ansible Vault (`group_vars/vault.yml`) o variables de entorno (`NETBOX_TOKEN`, `IOS_PASSWORD`). Excepción histórica conocida: los scripts de Lab 3 tienen credenciales de laboratorio hardcodeadas (`netdevops`/`cisco`); no replicar ese patrón en código nuevo.
- Los scripts de NetBox deshabilitan la verificación TLS (`verify=False`) porque el NetBox del lab usa HTTP/certificado autofirmado; es deliberado y solo válido para el laboratorio.
- `host_key_checking = False` y los algoritmos SSH legacy son requisito del entorno de laboratorio, no una recomendación general.
- El `Jenkinsfile` de Lab 5 tiene modo seguro: sin `EXECUTE_PIPELINE=true` solo valida que el Job Template existe, sin lanzarlo. Respetar esa protección.
