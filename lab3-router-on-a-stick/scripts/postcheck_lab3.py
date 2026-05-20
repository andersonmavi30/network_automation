#!/usr/bin/env python3

from pathlib import Path
import yaml
from netmiko import ConnectHandler


BASE_DIR = Path(__file__).resolve().parents[1]
INTENT_FILE = BASE_DIR / "intent" / "lab3_intent.yml"
POSTCHECK_DIR = BASE_DIR / "artifacts" / "postcheck"

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


def run_postcheck(device_name, device_data):
    device_dir = POSTCHECK_DIR / device_name
    device_dir.mkdir(parents=True, exist_ok=True)

    connection = {
        "device_type": device_data["platform"],
        "host": device_data["mgmt_ip"],
        "username": USERNAME,
        "password": PASSWORD,
        "secret": PASSWORD,
    }

    print(f"[INFO] Connecting to {device_name} - {device_data['mgmt_ip']}")

    with ConnectHandler(**connection) as net_connect:
        net_connect.enable()

        for command in COMMANDS:
            output = net_connect.send_command(command)

            filename = command.replace(" ", "_").replace("-", "_") + ".txt"
            output_file = device_dir / filename

            with open(output_file, "w") as file:
                file.write(output)

            print(f"[OK] {device_name}: saved {command}")

    print(f"[OK] Postcheck completed for {device_name}")


def main():
    intent = load_intent()

    POSTCHECK_DIR.mkdir(parents=True, exist_ok=True)

    target_devices = ["R1", "ASW1", "ASW2", "ASW3"]

    for device_name in target_devices:
        device_data = intent["devices"][device_name]
        run_postcheck(device_name, device_data)

    print("[OK] Lab 3 postcheck completed successfully.")


if __name__ == "__main__":
    main()
