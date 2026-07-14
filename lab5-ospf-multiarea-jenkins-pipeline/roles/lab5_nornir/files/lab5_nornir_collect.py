#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import pynetbox
import yaml
from nornir import InitNornir
from nornir_netmiko.tasks import netmiko_send_command


COMMANDS = {
    "show_clock": "show clock",
    "show_ip_interface_brief": "show ip interface brief",
    "show_ip_ospf_neighbor": "show ip ospf neighbor",
    "show_ip_route_ospf": "show ip route ospf",
    "show_running_config": "show running-config",
}


def required_environment(variable_name):
    value = os.getenv(variable_name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {variable_name}")
    return value


def get_primary_ip(device):
    if not device.primary_ip4:
        raise RuntimeError(f"{device.name} does not have primary_ip4 in NetBox")

    address = getattr(device.primary_ip4, "address", device.primary_ip4)
    return str(address).split("/")[0]


def expected_neighbor_count(device_name, topology):
    return sum(
        1
        for link in topology.get("links", [])
        if any(
            endpoint.get("device") == device_name
            for endpoint in link.get("endpoints", [])
        )
    )


def count_full_neighbors(output):
    return sum(
        1
        for line in output.splitlines()
        if re.search(r"\bFULL(?:/|\s)", line)
    )


def collect_commands(task):
    for result_name, command in COMMANDS.items():
        task.run(
            name=result_name,
            task=netmiko_send_command,
            command_string=command,
            use_textfsm=False,
            read_timeout=30,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Collect and validate Lab 5 devices with Nornir"
    )
    parser.add_argument("--netbox-url", required=True)
    parser.add_argument("--site", default="lab5")
    parser.add_argument("--topology-file", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    token = required_environment("NETBOX_TOKEN")
    username = required_environment("NORNIR_USERNAME")
    password = required_environment("NORNIR_PASSWORD")
    secret = os.getenv("NORNIR_SECRET", "")

    topology_file = Path(args.topology_file)
    output_dir = Path(args.output_dir)
    backup_dir = output_dir / "backups"

    output_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    with topology_file.open("r", encoding="utf-8") as file:
        topology = yaml.safe_load(file)

    netbox = pynetbox.api(args.netbox_url, token=token)
    devices = sorted(
        netbox.dcim.devices.filter(site=args.site, status="active"),
        key=lambda device: device.name,
    )

    if not devices:
        print(f"ERROR: No active devices found in NetBox site '{args.site}'")
        sys.exit(1)

    hosts = {}

    for device in devices:
        host_data = {
            "hostname": get_primary_ip(device),
            "platform": "cisco_ios",
            "username": username,
            "password": password,
        }

        if secret:
            host_data["connection_options"] = {
                "netmiko": {
                    "extras": {
                        "secret": secret,
                    }
                }
            }

        hosts[device.name] = host_data

    with tempfile.TemporaryDirectory(prefix="lab5_nornir_") as temp_directory:
        inventory_directory = Path(temp_directory)
        host_file = inventory_directory / "hosts.yml"
        group_file = inventory_directory / "groups.yml"
        defaults_file = inventory_directory / "defaults.yml"

        host_file.write_text(
            yaml.safe_dump(hosts, sort_keys=True),
            encoding="utf-8",
        )
        group_file.write_text("{}\n", encoding="utf-8")
        defaults_file.write_text("{}\n", encoding="utf-8")

        nr = InitNornir(
            runner={
                "plugin": "threaded",
                "options": {
                    "num_workers": 5,
                },
            },
            inventory={
                "plugin": "SimpleInventory",
                "options": {
                    "host_file": str(host_file),
                    "group_file": str(group_file),
                    "defaults_file": str(defaults_file),
                },
            },
        )

        try:
            aggregated_result = nr.run(
                name="Lab 5 Nornir collection",
                task=collect_commands,
            )
        finally:
            nr.close_connections()

    summary = {
        "site": args.site,
        "device_count": len(devices),
        "passed_devices": [],
        "failed_devices": [],
    }

    for device in devices:
        device_name = device.name
        outputs = {}
        errors = []

        for result in aggregated_result[device_name]:
            if result.name not in COMMANDS:
                continue

            if result.failed:
                errors.append(
                    {
                        "task": result.name,
                        "error": str(result.exception or result.result),
                    }
                )
            else:
                outputs[result.name] = str(result.result)

        expected_neighbors = expected_neighbor_count(device_name, topology)
        observed_neighbors = count_full_neighbors(
            outputs.get("show_ip_ospf_neighbor", "")
        )

        validation_passed = (
            not errors
            and observed_neighbors == expected_neighbors
        )

        device_evidence = {
            "device": device_name,
            "management_ip": get_primary_ip(device),
            "expected_full_neighbors": expected_neighbors,
            "observed_full_neighbors": observed_neighbors,
            "validation_passed": validation_passed,
            "errors": errors,
            "commands": {
                COMMANDS[result_name]: output
                for result_name, output in outputs.items()
            },
        }

        evidence_file = output_dir / f"{device_name}.json"
        evidence_file.write_text(
            json.dumps(device_evidence, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        running_config = outputs.get("show_running_config")
        if running_config:
            backup_file = backup_dir / f"{device_name}.cfg"
            backup_file.write_text(
                running_config.rstrip() + "\n",
                encoding="utf-8",
            )

        if validation_passed:
            summary["passed_devices"].append(device_name)
        else:
            summary["failed_devices"].append(device_name)

    summary["validation_passed"] = not summary["failed_devices"]

    summary_file = output_dir / "nornir_summary.json"
    summary_file.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if summary["failed_devices"]:
        print(
            "NORNIR LAB5 VALIDATION: FAIL - "
            + ", ".join(summary["failed_devices"])
        )
        sys.exit(1)

    print(
        "NORNIR LAB5 VALIDATION: PASS - "
        + ", ".join(summary["passed_devices"])
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}")
        sys.exit(1)
