#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import pynetbox
import yaml
from pyats.topology import loader


def required_environment(variable_name: str) -> str:
    """Obtiene una variable de entorno obligatoria."""

    value = os.getenv(variable_name)

    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {variable_name}"
        )

    return value


def get_primary_ip(device: Any) -> str:
    """Obtiene la IPv4 primaria de management desde NetBox."""

    if not device.primary_ip4:
        raise RuntimeError(
            f"{device.name} does not have primary_ip4 in NetBox"
        )

    address = getattr(
        device.primary_ip4,
        "address",
        device.primary_ip4,
    )

    return str(address).split("/")[0]


def find_values_by_key(
    data: Any,
    expected_key: str,
) -> list[Any]:
    """Busca recursivamente valores asociados a una clave."""

    values: list[Any] = []

    if isinstance(data, dict):

        for key, value in data.items():

            if str(key).lower() == expected_key.lower():
                values.append(value)

            values.extend(
                find_values_by_key(
                    value,
                    expected_key,
                )
            )

    elif isinstance(data, list):

        for item in data:

            values.extend(
                find_values_by_key(
                    item,
                    expected_key,
                )
            )

    return values


def expected_neighbor_count(
    device_name: str,
    topology: dict[str, Any],
) -> int:
    """
    Calcula vecinos EIGRP esperados.

    Cada interfaz P2P representa una adyacencia esperada.
    """

    if device_name not in topology["devices"]:
        raise RuntimeError(
            f"{device_name} is not defined in topology.yml"
        )

    interfaces = (
        topology["devices"][device_name]["interfaces"]
    )

    return sum(
        1
        for interface_data in interfaces.values()
        if interface_data["type"] == "p2p"
    )


def expected_service_interfaces(
    device_name: str,
    topology: dict[str, Any],
) -> set[str]:
    """Obtiene interfaces del Lab 6 excluyendo management."""

    interfaces = (
        topology["devices"][device_name]["interfaces"]
    )

    return {
        interface_name
        for interface_name, interface_data
        in interfaces.items()
        if interface_data["type"] != "management"
    }


def extract_eigrp_neighbors(
    parsed_neighbors: Any,
) -> set[str]:
    """
    Extrae IPs de vecinos desde la estructura Genie.

    Genie normalmente almacena los vecinos dentro
    de diccionarios llamados eigrp_nbr.
    """

    neighbors: set[str] = set()

    for neighbor_dictionary in find_values_by_key(
        parsed_neighbors,
        "eigrp_nbr",
    ):

        if not isinstance(
            neighbor_dictionary,
            dict,
        ):
            continue

        for neighbor_ip in neighbor_dictionary:
            neighbors.add(
                str(neighbor_ip)
            )

    return neighbors


def extract_eigrp_routes(
    parsed_routes: Any,
) -> set[str]:
    """Extrae prefijos EIGRP del parser estructurado de Genie."""

    routes: set[str] = set()

    for route_dictionary in find_values_by_key(
        parsed_routes,
        "routes",
    ):

        if not isinstance(
            route_dictionary,
            dict,
        ):
            continue

        for prefix in route_dictionary:
            routes.add(
                str(prefix)
            )

    return routes


def extract_interfaces(
    parsed_interfaces: Any,
) -> dict[str, Any]:
    """Obtiene el diccionario de interfaces del parser Genie."""

    interface_values = find_values_by_key(
        parsed_interfaces,
        "interface",
    )

    for value in interface_values:

        if isinstance(value, dict):
            return value

    return {}


def interface_is_up(
    interface_data: dict[str, Any],
) -> bool:
    """Valida estado operacional y protocolo UP."""

    status = str(
        interface_data.get(
            "status",
            "",
        )
    ).lower()

    protocol = str(
        interface_data.get(
            "protocol",
            "",
        )
    ).lower()

    return (
        status == "up"
        and protocol == "up"
    )


def build_testbed(
    devices: list[Any],
    username: str,
    password: str,
    secret: str,
) -> dict[str, Any]:
    """Construye un testbed temporal pyATS para los CSR1000v."""

    testbed: dict[str, Any] = {
        "testbed": {
            "name": "lab6_pyats",
            "credentials": {
                "default": {
                    "username": username,
                    "password": password,
                },
                "enable": {
                    "password": secret,
                },
            },
        },
        "devices": {},
    }

    for device in devices:

        testbed["devices"][device.name] = {
            "os": "iosxe",
            "platform": "csr1000v",
            "type": "router",
            "connections": {
                "cli": {
                    "protocol": "ssh",
                    "ip": get_primary_ip(device),
                    "port": 22,
                }
            },
        }

    return testbed


def build_device_diagnostic(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Genera resumen sanitizado por dispositivo."""

    failed_checks = [
        check_name
        for check_name, passed
        in evidence["checks"].items()
        if not passed
    ]

    return {
        "validation_passed": (
            evidence["validation_passed"]
        ),
        "management_ip": (
            evidence["management_ip"]
        ),
        "expected_eigrp_neighbors": (
            evidence["expected_eigrp_neighbors"]
        ),
        "observed_eigrp_neighbors": (
            evidence.get(
                "observed_eigrp_neighbors",
                [],
            )
        ),
        "observed_eigrp_routes": (
            evidence.get(
                "observed_eigrp_routes",
                [],
            )
        ),
        "service_interfaces": (
            evidence.get(
                "service_interfaces",
                {},
            )
        ),
        "checks": evidence["checks"],
        "failed_checks": failed_checks,
        "errors": evidence["errors"],
    }


def validate_device(
    device: Any,
    device_data: dict[str, str],
    topology: dict[str, Any],
    output_directory: Path,
) -> dict[str, Any]:
    """Conecta a un router y valida EIGRP con Genie."""

    device_name = device.name

    expected_neighbors = expected_neighbor_count(
        device_name,
        topology,
    )

    service_interfaces = (
        expected_service_interfaces(
            device_name,
            topology,
        )
    )

    evidence: dict[str, Any] = {
        "device": device_name,
        "management_ip": (
            device_data["management_ip"]
        ),
        "expected_eigrp_neighbors": (
            expected_neighbors
        ),
        "expected_service_interfaces": (
            sorted(service_interfaces)
        ),
        "checks": {},
        "errors": [],
        "parsed": {},
    }

    try:

        device.connect(
            via="cli",
            log_stdout=False,
            learn_hostname=True,
            connection_timeout=30,
        )

        parsed_neighbors = device.parse(
            "show ip eigrp neighbors"
        )

        parsed_routes = device.parse(
            "show ip route eigrp"
        )

        parsed_interfaces = device.parse(
            "show ip interface brief"
        )

        evidence["parsed"] = {
            "show_ip_eigrp_neighbors": (
                parsed_neighbors
            ),
            "show_ip_route_eigrp": (
                parsed_routes
            ),
            "show_ip_interface_brief": (
                parsed_interfaces
            ),
        }

        observed_neighbors = (
            extract_eigrp_neighbors(
                parsed_neighbors
            )
        )

        observed_routes = (
            extract_eigrp_routes(
                parsed_routes
            )
        )

        parsed_interface_data = (
            extract_interfaces(
                parsed_interfaces
            )
        )

        interface_results: dict[
            str,
            bool,
        ] = {}

        for interface_name in sorted(
            service_interfaces
        ):

            interface_data = (
                parsed_interface_data.get(
                    interface_name
                )
            )

            interface_results[
                interface_name
            ] = (
                isinstance(
                    interface_data,
                    dict,
                )
                and interface_is_up(
                    interface_data
                )
            )

        evidence[
            "observed_eigrp_neighbors"
        ] = sorted(
            observed_neighbors
        )

        evidence[
            "observed_eigrp_routes"
        ] = sorted(
            observed_routes
        )

        evidence[
            "service_interfaces"
        ] = interface_results

        evidence["checks"][
            "eigrp_neighbors"
        ] = (
            len(observed_neighbors)
            == expected_neighbors
        )

        evidence["checks"][
            "eigrp_routes"
        ] = (
            len(observed_routes) > 0
        )

        evidence["checks"][
            "service_interfaces_up"
        ] = (
            all(
                interface_results.values()
            )
            and bool(
                interface_results
            )
        )

    except Exception as error:

        evidence["errors"].append(
            f"{type(error).__name__}: {error}"
        )

        evidence["checks"].setdefault(
            "eigrp_neighbors",
            False,
        )

        evidence["checks"].setdefault(
            "eigrp_routes",
            False,
        )

        evidence["checks"].setdefault(
            "service_interfaces_up",
            False,
        )

    finally:

        try:

            if device.is_connected():
                device.disconnect()

        except Exception:
            pass

    evidence["validation_passed"] = (
        not evidence["errors"]
        and all(
            evidence["checks"].values()
        )
    )

    evidence_file = (
        output_directory
        / f"{device_name}.json"
    )

    evidence_file.write_text(
        json.dumps(
            evidence,
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    return evidence


def main() -> None:
    """Ejecuta la validacion pyATS/Genie del Lab 6."""

    parser = argparse.ArgumentParser(
        description=(
            "Validate Lab 6 EIGRP "
            "using pyATS and Genie parsers"
        )
    )

    parser.add_argument(
        "--netbox-url",
        required=True,
    )

    parser.add_argument(
        "--site",
        default="lab6",
    )

    parser.add_argument(
        "--topology-file",
        required=True,
    )

    parser.add_argument(
        "--output-dir",
        required=True,
    )

    args = parser.parse_args()

    netbox_token = required_environment(
        "NETBOX_TOKEN"
    )

    username = required_environment(
        "PYATS_USERNAME"
    )

    password = required_environment(
        "PYATS_PASSWORD"
    )

    secret = required_environment(
        "PYATS_SECRET"
    )

    topology_file = Path(
        args.topology_file
    )

    output_directory = Path(
        args.output_dir
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    with topology_file.open(
        "r",
        encoding="utf-8",
    ) as file:

        topology = yaml.safe_load(file)

    netbox = pynetbox.api(
        args.netbox_url,
        token=netbox_token,
    )

    devices = sorted(
        netbox.dcim.devices.filter(
            site=args.site,
            status="active",
        ),
        key=lambda device: device.name,
    )

    if not devices:

        raise RuntimeError(
            "No active devices found in NetBox site "
            f"'{args.site}'"
        )

    expected_devices = set(
        topology.get(
            "devices",
            {},
        )
    )

    netbox_devices = {
        device.name
        for device in devices
    }

    if netbox_devices != expected_devices:

        raise RuntimeError(
            "NetBox devices do not match topology intent. "
            f"NetBox={sorted(netbox_devices)}, "
            f"Topology={sorted(expected_devices)}"
        )

    testbed_data = build_testbed(
        devices,
        username,
        password,
        secret,
    )

    with tempfile.TemporaryDirectory(
        prefix="lab6_pyats_"
    ) as temporary_directory:

        testbed_file = (
            Path(temporary_directory)
            / "testbed.yml"
        )

        testbed_file.write_text(
            yaml.safe_dump(
                testbed_data,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        testbed = loader.load(
            str(testbed_file)
        )

        device_inventory = {
            device.name: {
                "management_ip": (
                    get_primary_ip(device)
                ),
            }
            for device in devices
        }

        results: list[
            dict[str, Any]
        ] = []

        for device_name in sorted(
            testbed.devices
        ):

            results.append(
                validate_device(
                    testbed.devices[
                        device_name
                    ],
                    device_inventory[
                        device_name
                    ],
                    topology,
                    output_directory,
                )
            )

    passed_devices = [
        result["device"]
        for result in results
        if result["validation_passed"]
    ]

    failed_devices = [
        result["device"]
        for result in results
        if not result["validation_passed"]
    ]

    device_results = {
        result["device"]: (
            build_device_diagnostic(
                result
            )
        )
        for result in results
    }

    summary = {
        "site": args.site,
        "device_count": len(results),
        "passed_devices": passed_devices,
        "failed_devices": failed_devices,
        "validation_passed": (
            not failed_devices
        ),
        "device_results": device_results,
    }

    summary_file = (
        output_directory
        / "pyats_summary.json"
    )

    summary_file.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    if failed_devices:

        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "failed_devices": (
                        failed_devices
                    ),
                    "device_results": {
                        device_name: (
                            device_results[
                                device_name
                            ]
                        )
                        for device_name
                        in failed_devices
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        sys.exit(1)

    print(
        json.dumps(
            {
                "status": "PASS",
                "passed_devices": (
                    passed_devices
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":

    try:

        main()

    except Exception as error:

        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "error_type": (
                        type(error).__name__
                    ),
                    "error": str(error),
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        sys.exit(1)
