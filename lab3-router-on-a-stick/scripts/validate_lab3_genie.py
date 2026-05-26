#!/usr/bin/env python3

import json
from pathlib import Path
import yaml
from netmiko import ConnectHandler


BASE_DIR = Path(__file__).resolve().parents[1]
INTENT_FILE = BASE_DIR / "intent" / "lab3_intent.yml"
REPORT_DIR = BASE_DIR / "artifacts" / "genie_validation"
REPORT_FILE = REPORT_DIR / "lab3_validation_report.json"

USERNAME = "netdevops"
PASSWORD = "cisco"


def load_intent():
    with open(INTENT_FILE, "r") as file:
        return yaml.safe_load(file)


def connect_device(device_data):
    connection = {
        "device_type": device_data["platform"],
        "host": device_data["mgmt_ip"],
        "username": USERNAME,
        "password": PASSWORD,
        "secret": PASSWORD,
    }

    net_connect = ConnectHandler(**connection)
    net_connect.enable()
    return net_connect


def check_result(condition, success_msg, fail_msg):
    if condition:
        return {"status": "PASS", "message": success_msg}

    return {"status": "FAIL", "message": fail_msg}


def validate_router(intent):
    device_name = "R1"
    device_data = intent["devices"][device_name]
    router_info = intent["router_on_a_stick"]
    vlans = intent["vlans"]

    results = {}

    print(f"[INFO] Validating {device_name}")

    with connect_device(device_data) as net_connect:
        ip_brief = net_connect.send_command(
            "show ip interface brief",
            use_genie=True,
        )

        running_config = net_connect.send_command("show running-config")

    physical_interface = router_info["physical_interface"]

    for vlan in vlans:
        subinterface = f"{physical_interface}.{vlan['id']}"
        expected_ip = vlan["gateway"]

        interface_data = ip_brief.get("interface", {}).get(subinterface, {})
        configured_ip = interface_data.get("ip_address")
        status = interface_data.get("status")
        protocol = interface_data.get("protocol")

        results[subinterface] = {
            "ip_address": check_result(
                configured_ip == expected_ip,
                f"{subinterface} has expected IP {expected_ip}",
                f"{subinterface} expected IP {expected_ip}, found {configured_ip}",
            ),
            "line_status": check_result(
                status == "up",
                f"{subinterface} status is up",
                f"{subinterface} status is {status}",
            ),
            "protocol_status": check_result(
                protocol == "up",
                f"{subinterface} protocol is up",
                f"{subinterface} protocol is {protocol}",
            ),
            "dot1q": check_result(
                f"encapsulation dot1Q {vlan['id']}" in running_config,
                f"{subinterface} has dot1Q {vlan['id']}",
                f"{subinterface} missing dot1Q {vlan['id']}",
            ),
        }

    return results


def build_expected_trunks(switch_data):
    expected_trunks = []

    if "trunk_to_router" in switch_data:
        expected_trunks.append(switch_data["trunk_to_router"])

    if "trunk_to_upstream" in switch_data:
        expected_trunks.append(switch_data["trunk_to_upstream"])

    for trunk in switch_data.get("downstream_trunks", []):
        expected_trunks.append(trunk["interface"])

    return expected_trunks


def validate_switch(device_name, device_data, switch_data, vlans):
    results = {}

    print(f"[INFO] Validating {device_name}")

    with connect_device(device_data) as net_connect:
        vlan_output = net_connect.send_command("show vlan brief")
        trunk_output = net_connect.send_command("show interfaces trunk")
        running_config = net_connect.send_command("show running-config")

    expected_vlan_ids = [str(vlan["id"]) for vlan in vlans]
    expected_vlan_names = {str(vlan["id"]): vlan["name"] for vlan in vlans}

    results["vlans"] = {}

    for vlan_id in expected_vlan_ids:
        vlan_line = next(
            (
                line for line in vlan_output.splitlines()
                if line.strip().startswith(vlan_id + " ")
            ),
            ""
        )

        vlan_data = bool(vlan_line)
        vlan_name = vlan_line.split()[1] if vlan_line else None

        results["vlans"][vlan_id] = {
            "exists": check_result(
                bool(vlan_data),
                f"VLAN {vlan_id} exists",
                f"VLAN {vlan_id} does not exist",
            ),
            "name": check_result(
                vlan_name == expected_vlan_names[vlan_id],
                f"VLAN {vlan_id} name is {expected_vlan_names[vlan_id]}",
                f"VLAN {vlan_id} expected name {expected_vlan_names[vlan_id]}, found {vlan_name}",
            ),
        }

    results["trunks"] = {}

    for trunk_interface in build_expected_trunks(switch_data):
        interface_config_block = f"interface {trunk_interface}"

        results["trunks"][trunk_interface] = {
            "mode": check_result(
                interface_config_block in running_config
                and "switchport mode trunk" in running_config,
                f"{trunk_interface} is configured as trunk",
                f"{trunk_interface} is not configured as trunk",
            ),
            "allowed_vlans": check_result(
                f"switchport trunk allowed vlan {','.join(expected_vlan_ids)}" in running_config,
                f"{trunk_interface} allows VLANs {','.join(expected_vlan_ids)}",
                f"{trunk_interface} does not allow expected VLANs {','.join(expected_vlan_ids)}",
            ),
            "operational_output": check_result(
                trunk_interface in trunk_output
                or trunk_interface.replace("GigabitEthernet", "Gi") in trunk_output,
                f"{trunk_interface} appears in show interfaces trunk",
                f"{trunk_interface} does not appear in show interfaces trunk",
            ),
        }

    results["access_ports"] = {}

    for port in switch_data["access_ports"]:
        interface = port["interface"]
        vlan_id = str(port["vlan"])

        results["access_ports"][interface] = {
            "access_vlan": check_result(
                f"switchport access vlan {vlan_id}" in running_config,
                f"{interface} is assigned to VLAN {vlan_id}",
                f"{interface} is not assigned to VLAN {vlan_id}",
            ),
            "access_mode": check_result(
                "switchport mode access" in running_config,
                f"{interface} has access mode configured",
                f"{interface} missing access mode",
            ),
        }

    return results


def has_failures(data):
    if isinstance(data, dict):
        if data.get("status") == "FAIL":
            return True

        return any(has_failures(value) for value in data.values())

    if isinstance(data, list):
        return any(has_failures(item) for item in data)

    return False


def main():
    intent = load_intent()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "lab": intent["lab"]["name"],
        "router": {},
        "switches": {},
        "overall_result": "UNKNOWN",
    }

    report["router"] = validate_router(intent)

    for switch_name, switch_data in intent["access_switches"].items():
        device_data = intent["devices"][switch_name]
        report["switches"][switch_name] = validate_switch(
            switch_name,
            device_data,
            switch_data,
            intent["vlans"],
        )

    report["overall_result"] = "FAIL" if has_failures(report) else "PASS"

    with open(REPORT_FILE, "w") as file:
        json.dump(report, file, indent=2)

    print(f"[OK] Validation report created: {REPORT_FILE}")
    print(f"[RESULT] LAB 3 RESULT: {report['overall_result']}")

    if report["overall_result"] == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
