#!/usr/bin/env python3

import os
import sys
from pathlib import Path

import requests
import urllib3
import yaml


# Deshabilita warnings SSL si en algún momento NetBox usa certificado autofirmado.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

NETBOX_URL = os.getenv(
    "NETBOX_URL",
    "http://192.168.1.16:8000",
).rstrip("/")

NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")

BASE_DIR = Path(__file__).resolve().parent.parent
TOPOLOGY_FILE = BASE_DIR / "vars" / "topology.yml"


if not NETBOX_TOKEN:
    print("ERROR: variable NETBOX_TOKEN no definida.")
    sys.exit(1)


HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


# ============================================================
# FUNCIONES API
# ============================================================

def api_get(endpoint, params=None):
    """Realiza una consulta GET contra la API de NetBox."""

    response = requests.get(
        f"{NETBOX_URL}/api/{endpoint}",
        headers=HEADERS,
        params=params,
        verify=False,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def api_post(endpoint, payload):
    """Crea un objeto mediante POST."""

    response = requests.post(
        f"{NETBOX_URL}/api/{endpoint}",
        headers=HEADERS,
        json=payload,
        verify=False,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def api_patch(endpoint, object_id, payload):
    """Actualiza parcialmente un objeto existente."""

    response = requests.patch(
        f"{NETBOX_URL}/api/{endpoint}/{object_id}/",
        headers=HEADERS,
        json=payload,
        verify=False,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def get_single(endpoint, **params):
    """
    Busca un objeto en NetBox.

    Devuelve:
      - primer objeto encontrado
      - None si no existe
    """

    data = api_get(
        endpoint,
        params=params,
    )

    if data["count"] == 0:
        return None

    return data["results"][0]


# ============================================================
# TOPOLOGÍA
# ============================================================

def load_topology():
    """Carga vars/topology.yml."""

    if not TOPOLOGY_FILE.exists():
        raise RuntimeError(
            f"No existe archivo de topología: {TOPOLOGY_FILE}"
        )

    with open(
        TOPOLOGY_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        return yaml.safe_load(file)


# ============================================================
# SITE
# ============================================================

def ensure_site(topology):
    """Crea LAB6 si no existe."""

    lab = topology["lab"]

    site = get_single(
        "dcim/sites/",
        name=lab["name"],
    )

    if site:
        print(
            f"[OK] Site {lab['name']} ya existe "
            f"(ID {site['id']})"
        )

        return site

    payload = {
        "name": lab["name"],
        "slug": lab["name"].lower(),
        "status": "active",
        "description": lab["description"],
    }

    site = api_post(
        "dcim/sites/",
        payload,
    )

    print(
        f"[CREATE] Site {lab['name']} creado "
        f"(ID {site['id']})"
    )

    return site


# ============================================================
# OBJETOS AUXILIARES NETBOX
# ============================================================

def get_named_object(endpoint, name):
    """Busca objetos que utilizan el campo name."""

    obj = get_single(
        endpoint,
        name=name,
    )

    if not obj:
        raise RuntimeError(
            f"No existe '{name}' en /api/{endpoint}"
        )

    return obj


def get_device_type(model):
    """
    Device Type utiliza el campo model.

    Ejemplo:
      Cisco CSR1000v
    """

    device_type = get_single(
        "dcim/device-types/",
        model=model,
    )

    if not device_type:
        raise RuntimeError(
            f"No existe Device Type '{model}' en NetBox"
        )

    return device_type


# ============================================================
# DEVICES
# ============================================================

def ensure_device(
    name,
    topology,
    site,
):
    """Crea o actualiza un router."""

    defaults = topology["defaults"]

    device_type = get_device_type(
        defaults["device_type"]
    )

    role = get_named_object(
        "dcim/device-roles/",
        defaults["role"],
    )

    platform = get_named_object(
        "dcim/platforms/",
        defaults["platform"],
    )

    payload = {
        "name": name,
        "device_type": device_type["id"],
        "role": role["id"],
        "site": site["id"],
        "platform": platform["id"],
        "status": defaults["status"],
        "description": topology["lab"]["description"],
    }

    device = get_single(
        "dcim/devices/",
        name=name,
    )

    if device:
        device = api_patch(
            "dcim/devices",
            device["id"],
            payload,
        )

        print(
            f"[UPDATE] {name} "
            f"(ID {device['id']})"
        )

        return device

    device = api_post(
        "dcim/devices/",
        payload,
    )

    print(
        f"[CREATE] {name} "
        f"(ID {device['id']})"
    )

    return device


# ============================================================
# INTERFACES
# ============================================================

def ensure_interface(
    device,
    interface_name,
    interface_data,
):
    """Crea o actualiza una interfaz."""

    interface = get_single(
        "dcim/interfaces/",
        device_id=device["id"],
        name=interface_name,
    )

    semantic_type = interface_data["type"]

    payload = {
        "device": device["id"],
        "name": interface_name,
        "type": "1000base-t",
        "enabled": True,
        "description": semantic_type.upper(),
        "mgmt_only": semantic_type == "management",
    }

    if interface:
        interface = api_patch(
            "dcim/interfaces",
            interface["id"],
            payload,
        )

        print(
            f"  [UPDATE] {interface_name} "
            f"({semantic_type})"
        )

        return interface

    interface = api_post(
        "dcim/interfaces/",
        payload,
    )

    print(
        f"  [CREATE] {interface_name} "
        f"({semantic_type})"
    )

    return interface


# ============================================================
# IP ADDRESSES
# ============================================================

def ensure_ip(
    interface,
    address,
    router_name,
):
    """Crea o actualiza una IP y la asocia a su interfaz."""

    ip = get_single(
        "ipam/ip-addresses/",
        address=address,
    )

    payload = {
        "address": address,
        "status": "active",
        "assigned_object_type": "dcim.interface",
        "assigned_object_id": interface["id"],
        "description": (
            f"{router_name} - {interface['name']}"
        ),
    }

    if ip:
        ip = api_patch(
            "ipam/ip-addresses",
            ip["id"],
            payload,
        )

        print(
            f"    [UPDATE] {address} "
            f"-> {interface['name']}"
        )

        return ip

    ip = api_post(
        "ipam/ip-addresses/",
        payload,
    )

    print(
        f"    [CREATE] {address} "
        f"-> {interface['name']}"
    )

    return ip


# ============================================================
# PRIMARY MANAGEMENT IP
# ============================================================

def set_primary_ip(
    device,
    primary_ip,
):
    """Configura la IP management como Primary IPv4 del router."""

    api_patch(
        "dcim/devices",
        device["id"],
        {
            "primary_ip4": primary_ip["id"],
        },
    )

    print(
        f"  [PRIMARY] "
        f"{device['name']} -> "
        f"{primary_ip['address']}"
    )


# ============================================================
# SINCRONIZACIÓN
# ============================================================

def main():

    print(
        "========================================"
    )
    print(
        " LAB6 - NETBOX SOURCE OF TRUTH SYNC"
    )
    print(
        "========================================"
    )

    topology = load_topology()

    site = ensure_site(
        topology
    )

    for router_name, router_data in topology[
        "devices"
    ].items():

        print()
        print(
            f"========== {router_name} =========="
        )

        device = ensure_device(
            router_name,
            topology,
            site,
        )

        management_ip_object = None

        for (
            interface_name,
            interface_data,
        ) in router_data["interfaces"].items():

            interface = ensure_interface(
                device,
                interface_name,
                interface_data,
            )

            ip = ensure_ip(
                interface,
                interface_data["ip"],
                router_name,
            )

            if (
                interface_data["type"]
                == "management"
            ):
                management_ip_object = ip

        if management_ip_object:
            set_primary_ip(
                device,
                management_ip_object,
            )

        else:
            print(
                f"WARNING: {router_name} "
                "no tiene interfaz management definida."
            )

    print()
    print(
        "========================================"
    )
    print(
        " SINCRONIZACION COMPLETADA"
    )
    print(
        "========================================"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    try:
        main()

    except requests.HTTPError as error:

        print(
            f"\nERROR HTTP NetBox: {error}"
        )

        if error.response is not None:
            print(
                f"Respuesta NetBox: "
                f"{error.response.text}"
            )

        sys.exit(1)

    except requests.RequestException as error:

        print(
            f"\nERROR API NetBox: {error}"
        )

        sys.exit(1)

    except Exception as error:

        print(
            f"\nERROR: {error}"
        )

        sys.exit(1)
