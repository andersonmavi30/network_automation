#!/usr/bin/env python3

from pathlib import Path
import yaml
from nornir import InitNornir
from nornir_netmiko.tasks import netmiko_send_command


BASE_DIR = Path(__file__).resolve().parents[1]
INTENT_FILE = BASE_DIR / "intent" / "lab3_intent.yml"
NORNIR_DIR = BASE_DIR / "artifacts" / "nornir"
NORNIR_INV_DIR = BASE_DIR / "artifacts" / "nornir_inventory"

USERNAME = "netdevops"
PASSWORD = "cisco"

COMMANDS = [
    "show ip interface brief",
    "show vlan brief",
    "show interfaces trunk",
    "show running-config",
]


def load_intent():
    with open(INTENT_FILE, "r") as file:
        return yaml.safe_load(file)


def build_simple_inventory(intent):
    NORNIR_INV_DIR.mkdir(parents=True, exist_ok=True)

    hosts_file = NORNIR_INV_DIR / "hosts.yml"
    groups_file = NORNIR_INV_DIR / "groups.yml"
    defaults_file = NORNIR_INV_DIR / "defaults.yml"

    target_devices = ["R1", "ASW1", "ASW2", "ASW3"]

    hosts = {}

    for device_name in target_devices:
        device_data = intent["devices"][device_name]

        hosts[device_name] = {
            "hostname": device_data["mgmt_ip"],
            "platform": device_data["platform"],
            "username": USERNAME,
            "password": PASSWORD,
        }

    defaults = {
        "username": USERNAME,
        "password": PASSWORD,
    }

    with open(hosts_file, "w") as file:
        yaml.safe_dump(hosts, file, sort_keys=False)

    with open(groups_file, "w") as file:
        yaml.safe_dump({}, file, sort_keys=False)

    with open(defaults_file, "w") as file:
        yaml.safe_dump(defaults, file, sort_keys=False)

    return hosts_file, groups_file, defaults_file


def collect_commands(task):
    device_dir = NORNIR_DIR / task.host.name
    device_dir.mkdir(parents=True, exist_ok=True)

    for command in COMMANDS:
        result = task.run(
            task=netmiko_send_command,
            command_string=command,
        )

        output = result.result

        filename = command.replace(" ", "_").replace("-", "_") + ".txt"
        output_file = device_dir / filename

        with open(output_file, "w") as file:
            file.write(output)

        print(f"[OK] {task.host.name}: saved {command}")


def main():
    intent = load_intent()

    NORNIR_DIR.mkdir(parents=True, exist_ok=True)

    hosts_file, groups_file, defaults_file = build_simple_inventory(intent)

    nr = InitNornir(
        inventory={
            "plugin": "SimpleInventory",
            "options": {
                "host_file": str(hosts_file),
                "group_file": str(groups_file),
                "defaults_file": str(defaults_file),
            },
        }
    )

    nr.run(task=collect_commands)

    print("[OK] Lab 3 Nornir collection completed successfully.")


if __name__ == "__main__":
    main()
