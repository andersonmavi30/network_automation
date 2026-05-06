#!/usr/bin/env python3

from pathlib import Path
from nornir import InitNornir
from nornir_netmiko.tasks import netmiko_send_command


BASE_DIR = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = BASE_DIR / "lab2-inter-vlan" / "artifacts" / "nornir"

COMMANDS = [
    "show vlan brief",
    "show interfaces trunk",
    "show ip interface brief",
    "show running-config",
]


def collect_show_commands(task):
    device_dir = ARTIFACTS_DIR / task.host.name
    device_dir.mkdir(parents=True, exist_ok=True)

    for command in COMMANDS:
        result = task.run(
            task=netmiko_send_command,
            command_string=command,
        )

        filename = command.replace(" ", "_").replace("/", "_") + ".txt"
        output_file = device_dir / filename

        output_file.write_text(result.result, encoding="utf-8")


def main():
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    nr = InitNornir(
        inventory={
            "plugin": "SimpleInventory",
            "options": {
                "host_file": str(BASE_DIR / "shared" / "inventories" / "nornir_hosts.yml"),
                "group_file": str(BASE_DIR / "shared" / "inventories" / "nornir_groups.yml"),
            },
        }
    )

    result = nr.run(task=collect_show_commands)

    for host, multi_result in result.items():
        if multi_result.failed:
            print(f"[FAILED] {host}")
            for item in multi_result:
                if item.failed:
                    print(f"  Command: {item.name}")
                    print(f"  Error: {item.exception}")
        else:
            print(f"[OK] {host}")


if __name__ == "__main__":
    main()