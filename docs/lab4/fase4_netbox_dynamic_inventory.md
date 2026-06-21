# Lab 4 - Fase 4: NetBox Dynamic Inventory hacia Ansible CLI

## Objetivo

Validar que Ansible lea los dispositivos desde NetBox usando inventario dinámico.

## Estado final

- NetBox dynamic inventory: OK
- Hosts desde NetBox: OK
- Grupos dinámicos limpios: OK
- ansible_host / IP de gestión: OK
- Reachability IP: OK

## Archivos creados

- inventories/netbox/netbox_inventory.yml
- ansible.cfg
- docs/lab4/fase4_netbox_dynamic_inventory.md

## Grupos validados

- sites_pnetlab
- device_roles_router
- device_roles_access_switch
- platforms_cisco_ios

## Comando principal validado

```bash
ansible-inventory --graph
```

## Reachability validado

```bash
ansible all -m ansible.builtin.command -a 'ping -c 2 {{ ansible_host }}' -c local
```

Resultado:

```text
ASW1 OK
R1 OK
R2 OK
R3 OK
R4 OK
```

## Nota SSH Cisco IOSv

SSH manual funciona con:

```bash
ssh -o StrictHostKeyChecking=accept-new -o PreferredAuthentications=password -o PubkeyAuthentication=no netdevops@172.30.30.42
```

Usuario de laboratorio:

```text
netdevops
```

Password de laboratorio:

```text
cisco
```

`network_cli` queda pendiente de ajuste por compatibilidad SSH con IOSv.

## Cierre

Fase 4 completada correctamente.
