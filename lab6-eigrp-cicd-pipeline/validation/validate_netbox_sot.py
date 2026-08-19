#!/usr/bin/env python3

import os
import sys
from pathlib import Path

import requests
import yaml


NETBOX_URL = os.getenv(
    "NETBOX_URL",
    "http://192.168.1.16:8000",
).rstrip("/")

NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")

BASE_DIR = Path(__file__).resolve().parent.parent
TOPOLOGY_FILE = BASE_DIR / "vars" / "topology.yml"


if not NETBOX_TOKEN:
    print("[ERROR] Variable NETBOX_TOKEN no definida.")
    sys.exit(1)


HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Accept": "application/json",
}


errors = []


def api_get(endpoint, params=None):
    """Consulta la API de NetBox sin modificar información."""

    response = requests.get(
        f"{NETBOX_URL}/api/{endpoint}",
        headers=HEADERS,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def get_single(endpoint, **params):
    """Devuelve un único objeto de NetBox."""

    data = api_get(
        endpoint,
        params=params,
    )

    if data["count"] == 0:
        return None

    return data["results"][0]


def load_topology():
    """Carga la topología declarativa almacenada en Git."""

    with open(
        TOPOLOGY_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        return yaml.safe_load(file)


def check(condition, ok_message, error_message):
    """Registra PASS o FAIL."""

    if condition:
        print(f"[PASS] {ok_message}")
    else:
        print(f"[FAIL] {error_message}")
        errors.append(error_message)


def validate_devices(topology):
    """Valida los routers pertenecientes al LAB6."""

    expected_devices = set(
        topology["devices"].keys()
    )

    lab_slug = topology["lab"]["name"].lower()

    data = api_get(
        "dcim/devices/",
        params={
            "site": lab_slug,
            "status": "active",
            "limit": 100,
        },
    )

    actual_devices = {
        device["name"]
        for device in data["results"]
    }

    check(
        actual_devices == expected_devices,
        f"Devices LAB6 correctos: {sorted(actual_devices)}",
        (
            "Devices LAB6 no coinciden. "
            f"Esperados={sorted(expected_devices)} "
            f"Actuales={sorted(actual_devices)}"
        ),
    )


def validate_device(
    router_name,
    router_data,
    topology,
):
    """Valida atributos, interfaces e IPs de un router."""

    print()
    print(
        f"========== {router_name} =========="
    )

    device = get_single(
        "dcim/devices/",
        name=router_name,
    )

    if not device:
        message = f"{router_name} no existe en NetBox"
        print(f"[FAIL] {message}")
        errors.append(message)
        return

    defaults = topology["defaults"]

    check(
        device["site"]["name"] == topology["lab"]["name"],
        f"{router_name} pertenece a {topology['lab']['name']}",
        f"{router_name}: site incorrecto",
    )

    check(
        device["role"]["name"] == defaults["role"],
        f"{router_name} role={defaults['role']}",
        f"{router_name}: role incorrecto",
    )

    check(
        device["platform"]["name"] == defaults["platform"],
        f"{router_name} platform={defaults['platform']}",
        f"{router_name}: platform incorrecta",
    )

    check(
        device["device_type"]["model"]
        == defaults["device_type"],
        (
            f"{router_name} device_type="
            f"{defaults['device_type']}"
        ),
        f"{router_name}: device_type incorrecto",
    )

    primary_ip = (
        device.get("primary_ip4") or {}
    ).get("address")

    check(
        primary_ip == router_data["management_ip"],
        (
            f"{router_name} primary_ip4="
            f"{router_data['management_ip']}"
        ),
        (
            f"{router_name}: primary_ip4 incorrecta. "
            f"Esperada={router_data['management_ip']} "
            f"Actual={primary_ip}"
        ),
    )

    validate_interfaces(
        device,
        router_name,
        router_data,
    )


def validate_interfaces(
    device,
    router_name,
    router_data,
):
    """Valida interfaces e IPs exactamente contra topology.yml."""

    data = api_get(
        "dcim/interfaces/",
        params={
            "device_id": device["id"],
            "limit": 100,
        },
    )

    actual_interfaces = {
        interface["name"]: interface
        for interface in data["results"]
    }

    expected_interfaces = set(
        router_data["interfaces"].keys()
    )

    actual_names = set(
        actual_interfaces.keys()
    )

    check(
        actual_names == expected_interfaces,
        f"{router_name} interfaces coinciden",
        (
            f"{router_name}: interfaces no coinciden. "
            f"Esperadas={sorted(expected_interfaces)} "
            f"Actuales={sorted(actual_names)}"
        ),
    )

    for interface_name, interface_data in router_data[
        "interfaces"
    ].items():

        interface = actual_interfaces.get(
            interface_name
        )

        if not interface:
            continue

        expected_mgmt = (
            interface_data["type"]
            == "management"
        )

        check(
            interface["mgmt_only"] == expected_mgmt,
            (
                f"{router_name} {interface_name} "
                f"mgmt_only={expected_mgmt}"
            ),
            (
                f"{router_name} {interface_name}: "
                "mgmt_only incorrecto"
            ),
        )

        validate_ip(
            router_name,
            interface,
            interface_data["ip"],
        )


def validate_ip(
    router_name,
    interface,
    expected_ip,
):
    """Valida que una IP exista y esté asociada a la interfaz correcta."""

    ip = get_single(
        "ipam/ip-addresses/",
        address=expected_ip,
    )

    if not ip:
        message = (
            f"{router_name} {interface['name']}: "
            f"IP {expected_ip} no existe"
        )

        print(f"[FAIL] {message}")
        errors.append(message)
        return

    assigned_object = (
        ip.get("assigned_object") or {}
    )

    assigned_interface = assigned_object.get(
        "name"
    )

    check(
        assigned_interface == interface["name"],
        (
            f"{router_name} {interface['name']} "
            f"IP={expected_ip}"
        ),
        (
            f"{router_name} {interface['name']}: "
            f"{expected_ip} asociada a "
            f"{assigned_interface}"
        ),
    )


def main():
    print(
        "========================================"
    )
    print(
        " LAB6 - VALIDACION NETBOX SOURCE OF TRUTH"
    )
    print(
        "========================================"
    )

    topology = load_topology()

    validate_devices(
        topology
    )

    for router_name, router_data in topology[
        "devices"
    ].items():

        validate_device(
            router_name,
            router_data,
            topology,
        )

    print()
    print(
        "========================================"
    )

    if errors:
        print(
            f" RESULTADO: FAIL ({len(errors)} errores)"
        )
        print(
            "========================================"
        )

        for error in errors:
            print(f" - {error}")

        sys.exit(1)

    print(
        " RESULTADO: PASS - NETBOX COINCIDE CON GIT"
    )
    print(
        "========================================"
    )

    sys.exit(0)


if __name__ == "__main__":

    try:
        main()

    except requests.RequestException as error:
        print(
            f"\n[ERROR] API NetBox: {error}"
        )
        sys.exit(1)

    except Exception as error:
        print(
            f"\n[ERROR] {error}"
        )
        sys.exit(1)
