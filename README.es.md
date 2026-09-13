# Network Automation (NetDevOps Labs)

🇺🇸 [English](README.md)

Repositorio de **automatización de redes estilo Infrastructure as Code** sobre dispositivos Cisco (IOSv, CSR1000v) en un entorno de laboratorio (PNETLab). Está organizado como una serie de laboratorios progresivos (**Lab 2 a Lab 6**) que construyen, cada uno, un pipeline completo de configuración y validación de red.

No es una aplicación ni un paquete instalable: es una colección de pipelines donde **Git es la Source of Truth** y cada cambio de red sigue el mismo flujo:

1. **Intent** — topología/intención declarativa en YAML versionada en Git.
2. **Render** — generación de configuraciones con plantillas **Jinja2**.
3. **Validación pre-deploy** con **Batfish** (labs 5 y 6).
4. **Precheck** — verificación del estado actual de los dispositivos.
5. **Deploy** — con Ansible (`cisco.ios.ios_config`, conexión `network_cli` + libssh) o Netmiko (lab 3).
6. **Postcheck** y recolección de evidencia con **Nornir**.
7. **Validación** con **pyATS / Genie** y generación de artefactos en `artifacts/`.

## Componentes de plataforma

| Componente | URL / Detalle | Rol |
|------------|---------------|-----|
| **NetBox** | `http://192.168.1.16:8000` | Source of Truth e inventario dinámico (`netbox.netbox.nb_inventory`) |
| **AWX** | `http://192.168.1.13:30143` | Orquestador de Job Templates |
| **Jenkins** | — | Dispara los Job Templates de AWX vía API REST (Lab 5), con rollback automático |
| **Red de gestión** | `172.30.30.0/26` | Conectividad OOB hacia todos los dispositivos |

## Estructura del repositorio

```
├── ansible.cfg                     # Config global: inventario NetBox, libssh legacy
├── collections/requirements.yml    # Colecciones Ansible requeridas
├── inventories/netbox/             # Inventario dinámico (plugin nb_inventory)
├── group_vars/                     # Vars de conexión Cisco IOS (raíz)
├── execution-environments/         # Containerfiles para AWX Execution Environments
│   ├── iosv/                       # EE mínimo (ansible-core 2.15.13) para IOSv
│   └── lab5-csr1000v/              # EE completo (nornir, pyats, genie, pybatfish...)
├── scripts/netbox/                 # Bootstrap de NetBox desde intent (labs 4 y 5)
├── shared/                         # Inventario Nornir y scripts compartidos (Lab 2)
├── playbooks/awx/                  # Smoke test de AWX (show_version.yml)
├── docs/                           # Documentación de fases
├── lab2-inter-vlan/                # Lab 2: Inter-VLAN routing (pipeline Ansible)
├── lab3-router-on-a-stick/         # Lab 3: Router-on-a-Stick (pipeline Python)
├── lab4-ospf-ansible-pipeline/     # Lab 4: OSPF single-area (100 % Ansible)
├── lab5-ospf-multiarea-jenkins-pipeline/  # Lab 5: OSPF multi-área + Jenkins/AWX
└── lab6-eigrp-cicd-pipeline/       # Lab 6: EIGRP + CI/CD + APIs (en progreso)
```

## Laboratorios

Cada lab es **autocontenido** (propios `ansible.cfg`, inventarios, vars y `artifacts/` cuando aplica).

### Lab 2 — Inter-VLAN Routing (`lab2-inter-vlan/`)

Pipeline Ansible puro. `playbooks/lab2_full_change.yml` importa las fases `render → precheck → deploy → postcheck` y luego invoca los scripts Nornir/Genie de `shared/scripts/`.

- Intent: `intent/lab2_intent.yml` (VLANs 10/20/30/40, switches SW_DMZ, DSW1, ASW1, ASW2).
- Plantillas Jinja2 en `templates/`.

### Lab 3 — Router-on-a-Stick (`lab3-router-on-a-stick/`)

Mismo flujo que Lab 2 pero orquestado con **scripts Python**: `scripts/lab3_full_change.py` ejecuta `render → precheck → deploy (Netmiko) → postcheck → nornir → genie`.

- Dispositivos: R1 (router), SW_DMZ, ASW1, ASW2.
- Nota: los scripts tienen credenciales de laboratorio hardcodeadas (`netdevops`/`cisco`); es una excepción histórica, no un patrón a replicar.

### Lab 4 — OSPF Single-Area (`lab4-ospf-ansible-pipeline/`)

Orquestado 100 % por Ansible con playbooks numerados `00_`–`07_`; `playbooks/lab4_pipeline.yml` los importa en orden.

- Source of truth: `intent/lab4_source_of_truth.yml`; inventario dinámico desde NetBox (`host_vars/` y `group_vars/` locales).
- Topología: R1–R4 (OSPF área 0, enlaces /30 `10.0.x.x`), SW_DMZ, ASW1, PC1 (LAN `10.10.30.0/24`). Ver `lab4-ospf-ansible-pipeline/README.md` para el direccionamiento completo.
- **Regla del lab**: solo la configuración de gestión se hace manual por CLI; todo lo demás lo aplica Ansible.

### Lab 5 — OSPF Multi-Área + Jenkins (`lab5-ospf-multiarea-jenkins-pipeline/`)

OSPF multi-área sobre CSR1000v con roles Ansible (`lab5_render`, `lab5_batfish`, `lab5_precheck`, `lab5_ospf`, `lab5_postcheck`, `lab5_nornir`, `lab5_pyats`, `lab5_validate`, `lab5_cleanup`). `playbooks/lab5_pipeline.yml` importa los playbooks `01_`–`08_`.

- Introduce **Batfish** como gate de validación pre-deploy.
- El `Jenkinsfile` localiza el Job Template de AWX por nombre, lo lanza **solo si `EXECUTE_PIPELINE=true`**, espera el resultado y, en caso de fallo, lanza un rollback automático (template ID 16).
- Credenciales en `group_vars/vault.yml` (Ansible Vault).

### Lab 6 — EIGRP + CI/CD + APIs (`lab6-eigrp-cicd-pipeline/`)

Topología declarativa en `vars/topology.yml` (6 CSR1000v, LAB6). Enfoque API-first:

- `scripts/sync_netbox.py` — sincroniza la topología de Git hacia NetBox.
- `validation/validate_netbox_sot.py` — valida NetBox contra Git (solo lectura).
- `scripts/render_eigrp.py` y `scripts/render_batfish_candidates.py` — render de configs y snapshots para Batfish.
- Playbooks `01_`–`03_` (backup pre-change, Batfish pre-deploy, precheck) con roles `lab6_*`.
- Los subdirectorios `batfish/`, `jenkins/`, `netconf/`, `nornir/`, `postman/`, `pyats/`, `restconf/` están reservados para trabajo futuro.

## Requisitos previos

- Python del entorno de automatización: `/opt/automation/venv/bin/python`.
- Ansible con las colecciones de `collections/requirements.yml`:
  ```bash
  ansible-galaxy collection install -r collections/requirements.yml
  ```
- Acceso a NetBox, AWX y a la red de gestión `172.30.30.0/26`.

### Variables de entorno

| Variable | Uso |
|----------|-----|
| `NETBOX_TOKEN` | **Obligatorio** para scripts de API de NetBox (`bootstrap_*`, `sync_netbox.py`, `validate_netbox_sot.py`) |
| `NETBOX_URL` | Opcional (default `http://192.168.1.16:8000`) |
| `IOS_PASSWORD` | Password SSH de dispositivos IOS en el inventario raíz y Lab 4 |
| `awx-api-token` | Credencial de Jenkins con el token de API de AWX (Lab 5) |

### Ansible Vault

`lab5*/group_vars/vault.yml` y `lab6*/group_vars/vault.yml` están cifrados y definen `vault_ios_username`, `vault_ios_password`, `vault_ios_enable_password`. Ejecutar con `--ask-vault-pass` o un archivo de password de vault.

## Comandos principales

Desde la raíz del repositorio, salvo indicación contraria:

```bash
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

# Lab 4 (usa su ansible.cfg local)
cd lab4-ospf-ansible-pipeline && ansible-playbook playbooks/lab4_pipeline.yml

# Lab 5 (requiere vault password)
cd lab5-ospf-multiarea-jenkins-pipeline && ansible-playbook playbooks/lab5_pipeline.yml --ask-vault-pass

# Lab 6
cd lab6-eigrp-cicd-pipeline
export NETBOX_TOKEN=<token>
python3 scripts/sync_netbox.py                  # sincronizar NetBox
python3 validation/validate_netbox_sot.py       # validar NetBox vs Git
python3 scripts/render_eigrp.py                 # renderizar configs a configs/
ansible-playbook playbooks/01_backup_prechange.yml --ask-vault-pass

# Construir Execution Environments (ejemplo)
cd execution-environments/lab5-csr1000v && podman build -t ee-lab5-csr1000v .
```

## Convención de `artifacts/`

Cada lab guarda evidencia en `artifacts/`:

- `rendered/` — configuraciones renderizadas (versionadas en Git).
- `precheck/`, `postcheck/`, `deploy/` — evidencia de cada fase.
- `nornir/` — salidas `show` recolectadas con Nornir.
- `genie/` / `pyats/` — reportes JSON de validación.
- `batfish/` — resultados de validación pre-deploy.
- `backups/` — backups pre-change (algunos ignorados en `.gitignore` por su tamaño).

Los `.gitkeep` mantienen los directorios vacíos bajo control de versiones.

## Validación y testing

No hay framework de tests tradicional (pytest, CI unitario): la validación es propia del dominio de redes y actúa como **gate del pipeline** — cada fase aborta el flujo si falla.

- **Batfish** (validación offline pre-deploy): labs 5 y 6, salida en `artifacts/batfish/output/`.
- **pyATS / Genie**: parsean los `show` recolectados por Nornir y generan reportes JSON; exit code ≠ 0 si hay FAIL.
- **Validación de SoT**: `lab6*/validation/validate_netbox_sot.py` compara NetBox contra `vars/topology.yml` (solo lectura).
- Al modificar un pipeline: como mínimo `ansible-playbook --syntax-check` del playbook afectado y, si es posible, un run de render/precheck sin deploy.

## Convenciones de código

- **Idioma**: mezcla de español e inglés. Documentación, `Jenkinsfile` y scripts recientes (labs 5 y 6) en **español**; labs 2 y 3 en inglés. Mantener el idioma del archivo que se edita.
- **Playbooks numerados** por fase (`00_cleanup`, `01_render`, `02_precheck`, ...) más un `*_pipeline.yml` que solo hace `import_playbook` en orden.
- **Roles Ansible** con prefijo del lab (`lab5_*`, `lab6_*`), con `defaults/`, `tasks/`, `vars/` y `files/` para scripts Python.
- Deploy siempre desde archivo renderizado: `cisco.ios.ios_config` con `src: .../artifacts/rendered/{{ inventory_hostname }}.cfg` y `save_when`.
- Toda evidencia se guarda con `delegate_to: localhost`.
- Scripts Python: `#!/usr/bin/env python3`, rutas relativas con `Path(__file__).resolve().parent`, salida con prefijos `[OK]` / `[FAIL]` / `[PASS]` y `sys.exit(1)` ante error.

## Consideraciones de seguridad

- **Nunca** commitear credenciales en claro: usar Ansible Vault o variables de entorno (`NETBOX_TOKEN`, `IOS_PASSWORD`).
- Las conexiones usan `ansible.netcommon.network_cli` con **libssh** y algoritmos legacy (`ssh-rsa`, `diffie-hellman-group-exchange-sha1`, ...) porque los IOSv del laboratorio son antiguos; `host_key_checking = False` es requisito del entorno de laboratorio, **no** una recomendación general.
- Los scripts de NetBox deshabilitan la verificación TLS (`verify=False`) porque el NetBox del lab usa HTTP/certificado autofirmado; deliberado y solo válido para el laboratorio.
- El `Jenkinsfile` de Lab 5 tiene modo seguro: sin `EXECUTE_PIPELINE=true` solo valida que el Job Template existe, sin lanzarlo.

## 📄 Licencia

Este proyecto está licenciado bajo la [Licencia MIT](LICENSE).

## Documentación adicional

- `AGENTS.md` — guía detallada para agentes de IA (estructura, comandos, convenciones).
- `lab4-ospf-ansible-pipeline/README.md` — direccionamiento y topología completos del Lab 4.
- `docs/lab4/` — documentación de fases (p. ej. inventario dinámico NetBox).
