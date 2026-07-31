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
    """Return a required environment variable or stop execution."""

    value = os.getenv(variable_name)

    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {variable_name}"
        )

    return value


def get_primary_ip(device: Any) -> str:
    """Return the management IPv4 address defined in NetBox."""

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
    """Recursively find all values associated with a key."""

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


def find_dictionary_by_key(
    data: Any,
    expected_key: str,
) -> dict[str, Any] | None:
    """Recursively find a dictionary stored under a key."""

    if isinstance(data, dict):
        for key, value in data.items():
            if (
                str(key).lower() == expected_key.lower()
                and isinstance(value, dict)
            ):
                return value

            result = find_dictionary_by_key(
                value,
                expected_key,
            )

            if result is not None:
                return result

    elif isinstance(data, list):
        for item in data:
            result = find_dictionary_by_key(
                item,
                expected_key,
            )

            if result is not None:
                return result

    return None


def contains_truthy_value(
    data: Any,
    keys: list[str],
) -> bool:
    """Determine whether parsed data contains a positive flag."""

    truthy_strings = {
        "true",
        "yes",
        "enabled",
        "area border router",
        "abr",
    }

    for key in keys:
        for value in find_values_by_key(data, key):
            if isinstance(value, bool) and value:
                return True

            if str(value).strip().lower() in truthy_strings:
                return True

    return False


def expected_neighbor_ids(
    device_name: str,
    topology: dict[str, Any],
) -> set[str]:
    """Calculate expected OSPF neighbor router IDs."""

    neighbors: set[str] = set()

    for link in topology.get("links", []):
        endpoints = link.get("endpoints", [])

        endpoint_devices = [
            endpoint.get("device")
            for endpoint in endpoints
        ]

        if device_name not in endpoint_devices:
            continue

        for endpoint in endpoints:
            peer_name = endpoint.get("device")

            if peer_name == device_name:
                continue

            peer_loopback = (
                topology["devices"][peer_name]["loopback0"]
                .split("/")[0]
            )

            neighbors.add(peer_loopback)

    return neighbors


def extract_full_neighbors(
    parsed_neighbors: Any,
) -> dict[str, str]:
    """Extract OSPF neighbors whose state begins with FULL."""

    full_neighbors: dict[str, str] = {}

    def walk(data: Any) -> None:
        if isinstance(data, dict):
            for key, value in data.items():
                if (
                    str(key).lower() == "neighbors"
                    and isinstance(value, dict)
                ):
                    for neighbor_id, neighbor_data in value.items():
                        states = find_values_by_key(
                            neighbor_data,
                            "state",
                        )

                        normalized_states = [
                            str(state).strip().upper()
                            for state in states
                        ]

                        full_state = next(
                            (
                                state
                                for state in normalized_states
                                if state.startswith("FULL")
                            ),
                            None,
                        )

                        if full_state:
                            full_neighbors[str(neighbor_id)] = (
                                full_state
                            )

                walk(value)

        elif isinstance(data, list):
            for item in data:
                walk(item)

    walk(parsed_neighbors)

    return full_neighbors


def route_is_inter_area(
    route_entry: dict[str, Any],
) -> bool:
    """Determine whether an OSPF route is inter-area."""

    route_attribute_keys = [
        "source_protocol_codes",
        "route_code",
        "route_type",
        "path_type",
        "route_level",
    ]

    values: list[Any] = []

    for key in route_attribute_keys:
        values.extend(
            find_values_by_key(
                route_entry,
                key,
            )
        )

    normalized_values = [
        str(value)
        .strip()
        .upper()
        .replace("-", " ")
        .replace("_", " ")
        for value in values
    ]

    return any(
        value == "O IA"
        or value == "IA"
        or "INTER AREA" in value
        for value in normalized_values
    )


def build_testbed(
    devices: list[Any],
    username: str,
    password: str,
    secret: str,
) -> dict[str, Any]:
    """Build a temporary pyATS testbed for the CSR1000v routers."""

    testbed: dict[str, Any] = {
        "testbed": {
            "name": "lab5_pyats",
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
    """Build a sanitized device diagnostic for the summary."""

    failed_checks = [
        check_name
        for check_name, passed in evidence["checks"].items()
        if not passed
    ]

    return {
        "validation_passed": evidence["validation_passed"],
        "management_ip": evidence["management_ip"],
        "expected_router_id": evidence["expected_router_id"],
        "observed_router_ids": evidence.get(
            "observed_router_ids",
            [],
        ),
        "expected_full_neighbors": evidence[
            "expected_full_neighbors"
        ],
        "observed_full_neighbors": evidence.get(
            "observed_full_neighbors",
            {},
        ),
        "expected_abr": evidence["expected_abr"],
        "expected_inter_area_routes": evidence[
            "expected_inter_area_routes"
        ],
        "observed_inter_area_routes": evidence.get(
            "observed_inter_area_routes",
            {},
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
    """Connect to one router and validate its OSPF state."""

    device_name = device.name

    expected_router_id = (
        topology["devices"][device_name]["loopback0"]
        .split("/")[0]
    )

    expected_neighbors = expected_neighbor_ids(
        device_name,
        topology,
    )

    expected_abr_devices = set(
        topology.get(
            "validation",
            {},
        ).get(
            "expected_abr",
            [],
        )
    )

    expected_routes = (
        topology.get(
            "validation",
            {},
        )
        .get(
            "expected_inter_area_routes",
            {},
        )
        .get(
            device_name,
            [],
        )
    )

    evidence: dict[str, Any] = {
        "device": device_name,
        "management_ip": device_data["management_ip"],
        "expected_router_id": expected_router_id,
        "expected_full_neighbors": sorted(expected_neighbors),
        "expected_abr": device_name in expected_abr_devices,
        "expected_inter_area_routes": expected_routes,
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

        parsed_ospf = device.parse(
            "show ip ospf"
        )

        parsed_neighbors = device.parse(
            "show ip ospf neighbor"
        )

        parsed_routes = device.parse(
            "show ip route ospf"
        )

        parsed_interfaces = device.parse(
            "show ip interface brief"
        )

        evidence["parsed"] = {
            "show_ip_ospf": parsed_ospf,
            "show_ip_ospf_neighbor": parsed_neighbors,
            "show_ip_route_ospf": parsed_routes,
            "show_ip_interface_brief": parsed_interfaces,
        }

        observed_router_ids = {
            str(router_id)
            for router_id in find_values_by_key(
                parsed_ospf,
                "router_id",
            )
        }

        full_neighbors = extract_full_neighbors(
            parsed_neighbors
        )

        observed_neighbor_ids = set(
            full_neighbors
        )

        evidence["observed_router_ids"] = sorted(
            observed_router_ids
        )

        evidence["observed_full_neighbors"] = (
            full_neighbors
        )

        evidence["checks"]["router_id"] = (
            expected_router_id in observed_router_ids
        )

        evidence["checks"]["full_neighbors"] = (
            observed_neighbor_ids == expected_neighbors
        )

        if device_name in expected_abr_devices:
            evidence["checks"]["abr"] = (
                contains_truthy_value(
                    parsed_ospf,
                    [
                        "area_border_router",
                        "abr",
                    ],
                )
            )
        else:
            evidence["checks"]["abr"] = True

        route_results: dict[str, dict[str, bool]] = {}

        for prefix in expected_routes:
            route_entry = find_dictionary_by_key(
                parsed_routes,
                prefix,
            )

            route_results[prefix] = {
                "present": route_entry is not None,
                "inter_area": (
                    route_is_inter_area(route_entry)
                    if route_entry is not None
                    else False
                ),
            }

        evidence["observed_inter_area_routes"] = (
            route_results
        )

        evidence["checks"]["inter_area_routes"] = all(
            route_data["present"]
            and route_data["inter_area"]
            for route_data in route_results.values()
        )

        if not expected_routes:
            evidence["checks"]["inter_area_routes"] = True

    except Exception as error:
        evidence["errors"].append(
            f"{type(error).__name__}: {error}"
        )

        evidence["checks"].setdefault(
            "router_id",
            False,
        )

        evidence["checks"].setdefault(
            "full_neighbors",
            False,
        )

        evidence["checks"].setdefault(
            "abr",
            False,
        )

        evidence["checks"].setdefault(
            "inter_area_routes",
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
        and all(evidence["checks"].values())
    )

    evidence_file = (
        output_directory / f"{device_name}.json"
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
    """Run the Lab 5 pyATS validation."""

    parser = argparse.ArgumentParser(
        description=(
            "Validate Lab 5 OSPF using pyATS and Genie parsers"
        )
    )

    parser.add_argument(
        "--netbox-url",
        required=True,
    )

    parser.add_argument(
        "--site",
        default="lab5",
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
        prefix="lab5_pyats_"
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
                "management_ip": get_primary_ip(device),
            }
            for device in devices
        }

        results: list[dict[str, Any]] = []

        for device_name in sorted(
            testbed.devices
        ):
            results.append(
                validate_device(
                    testbed.devices[device_name],
                    device_inventory[device_name],
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
        result["device"]: build_device_diagnostic(
            result
        )
        for result in results
    }

    summary = {
        "site": args.site,
        "device_count": len(results),
        "passed_devices": passed_devices,
        "failed_devices": failed_devices,
        "validation_passed": not failed_devices,
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
                    "failed_devices": failed_devices,
                    "device_results": {
                        device_name: device_results[
                            device_name
                        ]
                        for device_name in failed_devices
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
                "passed_devices": passed_devices,
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
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        sys.exit(1)