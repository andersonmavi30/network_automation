#!/usr/bin/env python3

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import pynetbox
import yaml
from pyats.topology import loader


def required_environment(variable_name):
    value = os.getenv(variable_name)

    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {variable_name}"
        )

    return value


def get_primary_ip(device):
    if not device.primary_ip4:
        raise RuntimeError(
            f"{device.name} does not have primary_ip4 in NetBox"
        )

    address = getattr(device.primary_ip4, "address", device.primary_ip4)
    return str(address).split("/")[0]


def find_values_by_key(data, expected_key):
    values = []

    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() == expected_key.lower():
                values.append(value)

            values.extend(find_values_by_key(value, expected_key))

    elif isinstance(data, list):
        for item in data:
            values.extend(find_values_by_key(item, expected_key))

    return values


def find_dictionary_by_key(data, expected_key):
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key) == expected_key and isinstance(value, dict):
                return value

            result = find_dictionary_by_key(value, expected_key)

            if result is not None:
                return result

    elif isinstance(data, list):
        for item in data:
            result = find_dictionary_by_key(item, expected_key)

            if result is not None:
                return result

    return None


def contains_truthy_value(data, keys):
    for key in keys:
        for value in find_values_by_key(data, key):
            if isinstance(value, bool) and value:
                return True

            if str(value).strip().lower() in {
                "true",
                "yes",
                "enabled",
                "area border router",
                "abr",
            }:
                return True

    return False


def expected_neighbor_ids(device_name, topology):
    neighbors = set()

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


def extract_full_neighbors(parsed_neighbors):
    full_neighbors = {}

    def walk(data):
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

                        if any(
                            state.startswith("FULL")
                            for state in normalized_states
                        ):
                            full_neighbors[str(neighbor_id)] = (
                                normalized_states[0]
                                if normalized_states
                                else "FULL"
                            )

                walk(value)

        elif isinstance(data, list):
            for item in data:
                walk(item)

    walk(parsed_neighbors)
    return full_neighbors


def route_is_inter_area(route_entry):
    keys = [
        "source_protocol_codes",
        "route_code",
        "route_type",
        "path_type",
        "route_level",
    ]

    values = []

    for key in keys:
        values.extend(find_values_by_key(route_entry, key))

    normalized_values = [
        str(value).strip().upper().replace("-", " ")
        for value in values
    ]

    return any(
        value == "O IA"
        or "INTER AREA" in value
        or value == "IA"
        for value in normalized_values
    )


def build_testbed(devices, username, password, secret):
    testbed = {
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
            "os": "ios",
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


def validate_device(device, device_data, topology, output_directory):
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
        topology.get("validation", {}).get("expected_abr", [])
    )
    expected_routes = (
        topology.get("validation", {})
        .get("expected_inter_area_routes", {})
        .get(device_name, [])
    )

    evidence = {
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
            log_stdout=False,
            learn_hostname=True,
            connection_timeout=30,
        )

        parsed_ospf = device.parse("show ip ospf")
        parsed_neighbors = device.parse("show ip ospf neighbor")
        parsed_routes = device.parse("show ip route ospf")
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
        observed_neighbor_ids = set(full_neighbors)

        evidence["observed_router_ids"] = sorted(
            observed_router_ids
        )
        evidence["observed_full_neighbors"] = full_neighbors

        evidence["checks"]["router_id"] = (
            expected_router_id in observed_router_ids
        )
        evidence["checks"]["full_neighbors"] = (
            observed_neighbor_ids == expected_neighbors
        )

        if device_name in expected_abr_devices:
            evidence["checks"]["abr"] = contains_truthy_value(
                parsed_ospf,
                [
                    "area_border_router",
                    "abr",
                ],
            )
        else:
            evidence["checks"]["abr"] = True

        route_results = {}

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

        evidence["observed_inter_area_routes"] = route_results
        evidence["checks"]["inter_area_routes"] = all(
            route_data["present"]
            and route_data["inter_area"]
            for route_data in route_results.values()
        )

        if not expected_routes:
            evidence["checks"]["inter_area_routes"] = True

    except Exception as error:
        evidence["errors"].append(str(error))

        evidence["checks"].setdefault("router_id", False)
        evidence["checks"].setdefault("full_neighbors", False)
        evidence["checks"].setdefault("abr", False)
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

    evidence_file = output_directory / f"{device_name}.json"
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


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Validate Lab 5 OSPF using pyATS and Genie parsers"
        )
    )
    parser.add_argument("--netbox-url", required=True)
    parser.add_argument("--site", default="lab5")
    parser.add_argument("--topology-file", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    netbox_token = required_environment("NETBOX_TOKEN")
    username = required_environment("PYATS_USERNAME")
    password = required_environment("PYATS_PASSWORD")
    secret = required_environment("PYATS_SECRET")

    topology_file = Path(args.topology_file)
    output_directory = Path(args.output_dir)
    output_directory.mkdir(parents=True, exist_ok=True)

    with topology_file.open("r", encoding="utf-8") as file:
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
            f"No active devices found in NetBox site '{args.site}'"
        )

    expected_devices = set(topology.get("devices", {}))
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
            Path(temporary_directory) / "testbed.yml"
        )
        testbed_file.write_text(
            yaml.safe_dump(
                testbed_data,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        testbed = loader.load(str(testbed_file))

        device_inventory = {
            device.name: {
                "management_ip": get_primary_ip(device),
            }
            for device in devices
        }

        results = []

        for device_name in sorted(testbed.devices):
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

    summary = {
        "site": args.site,
        "device_count": len(results),
        "passed_devices": passed_devices,
        "failed_devices": failed_devices,
        "validation_passed": not failed_devices,
    }

    summary_file = (
        output_directory / "pyats_summary.json"
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
            "PYATS LAB5 VALIDATION: FAIL - "
            + ", ".join(failed_devices)
        )
        sys.exit(1)

    print(
        "PYATS LAB5 VALIDATION: PASS - "
        + ", ".join(passed_devices)
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}")
        sys.exit(1)
