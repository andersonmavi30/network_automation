#!/usr/bin/env python3

from pathlib import Path
import yaml
from nornir import InitNornir
from nornir.core.inventory import Inventory, Hosts, Host, Groups, Defaults
from nornir_netmiko.tasks import netmiko_send_command


BASE_DIR = Path(__file__).resolve().parents[1]
INTENT_FILE = BASE_DIR / "intent" / "lab3_intent.yml"
NORNIR_DIR = BASE_DIR / "artifacts" / "nornir"

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


def build_inventory(intent):
    hosts = Hosts()
    groups = Groups()
    defaults = Defaults(username=USERNAME, password=PASSWORD)

    target_devices = ["R1", "ASW1", "ASW2", "ASW3"]

    for device_name in target_devices:
        device_data = intent["devices"][device_name]

        hosts[device_name] = Host(
            name=device_name,
            hostname=device_data["mgmt_ip"],
            platform=device_data["platform"],
            username=USERNAME,
            password=PASSWORD,
        )

    return Inventory(hosts=hosts, groups=groups, defaults=defaults)


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

    inventory = build_inventory(intent)

    nr = InitNornir(
        inventory={
            "plugin": "DictInventory",
            "options": {
                "hosts": inventory.hosts,
                "groups": inventory.groups,
                "defaults": inventory.defaults,
            },
        }
    )

    nr.run(task=collect_commands)

    print("[OK] Lab 3 Nornir collection completed successfully.")


if __name__ == "__main__":
    main()
