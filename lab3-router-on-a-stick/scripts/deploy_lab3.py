#!/usr/bin/env python3

from pathlib import Path
import yaml
from netmiko import ConnectHandler


BASE_DIR = Path(__file__).resolve().parents[1]
INTENT_FILE = BASE_DIR / "intent" / "lab3_intent.yml"
RENDERED_DIR = BASE_DIR / "artifacts" / "rendered"

USERNAME = "netdevops"
PASSWORD = "cisco"


def load_intent():
    with open(INTENT_FILE, "r") as file:
        return yaml.safe_load(file)


def load_config(device_name):
    config_file = RENDERED_DIR / f"{device_name}.cfg"

    if not config_file.exists():
        raise FileNotFoundError(f"Rendered config not found: {config_file}")

    with open(config_file, "r") as file:
        return file.read().splitlines()


def deploy_config(device_name, device_data):
    config_commands = load_config(device_name)

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

        print(f"[INFO] Deploying config to {device_name}")
        output = net_connect.send_config_set(config_commands)

        print(output)

        save_output = net_connect.save_config()
        print(save_output)

    print(f"[OK] Deploy completed for {device_name}")


def main():
    intent = load_intent()

    target_devices = ["R1", "ASW1", "ASW2", "ASW3"]

    for device_name in target_devices:
        device_data = intent["devices"][device_name]
        deploy_config(device_name, device_data)

    print("[OK] Lab 3 deploy completed successfully.")


if __name__ == "__main__":
    main()
