#!/usr/bin/env python3

import json
from pathlib import Path
from genie.conf.base import Device


BASE_DIR = Path(__file__).resolve().parents[2]
NORNIR_DIR = BASE_DIR / "lab2-inter-vlan" / "artifacts" / "nornir"
REPORT_DIR = BASE_DIR / "lab2-inter-vlan" / "artifacts" / "genie_validation"
REPORT_FILE = REPORT_DIR / "lab2_validation_report.json"

EXPECTED_VLANS = ["10", "20", "30", "40", "70", "80"]
L3_DEVICE = "DSW1"
EXPECTED_SVIS = ["Vlan10", "Vlan20", "Vlan30", "Vlan40", "Vlan70", "Vlan80"]
EXPECTED_ALLOWED_VLANS = "10,20,30,40,70,80"

DEVICES = ["DSW1", "ASW1", "ASW2", "SW_DMZ"]


def parse_output(device_name, command, filename):
    device = Device(name=device_name, os="ios")
    output_file = NORNIR_DIR / device_name / filename
    output = output_file.read_text(encoding="utf-8")

    return device.parse(command, output=output)


def validate_vlans(device_name):
    vlan_file = NORNIR_DIR / device_name / "show_vlan_brief.txt"
    output = vlan_file.read_text(encoding="utf-8")

    missing = []

    for vlan in EXPECTED_VLANS:
        if f"{vlan} " not in output and f"{vlan}\t" not in output:
            missing.append(vlan)

    return {
        "status": "PASS" if not missing else "FAIL",
        "missing_vlans": missing,
    }


def validate_svis():
    parsed = parse_output(
        L3_DEVICE,
        "show ip interface brief",
        "show_ip_interface_brief.txt"
    )

    interfaces = parsed.get("interface", {})

    missing = []
    not_up = []

    for svi in EXPECTED_SVIS:
        if svi not in interfaces:
            missing.append(svi)
            continue

        status = interfaces[svi].get("status")
        protocol = interfaces[svi].get("protocol")

        if status != "up" or protocol != "up":
            not_up.append({
                "interface": svi,
                "status": status,
                "protocol": protocol,
            })

    return {
        "status": "PASS" if not missing and not not_up else "FAIL",
        "missing_svis": missing,
        "not_up_svis": not_up,
    }


def validate_trunks(device_name):
    trunk_file = NORNIR_DIR / device_name / "show_interfaces_trunk.txt"
    output = trunk_file.read_text(encoding="utf-8")

    if device_name == "SW_DMZ":
        return {
            "status": "PASS" if output.strip() == "" else "FAIL",
            "note": "SW_DMZ should not have trunks in this lab",
        }

    has_trunk_output = bool(output.strip())
    clean_output = output.replace(" ", "")

    has_expected_vlans = EXPECTED_ALLOWED_VLANS in clean_output

    return {
        "status": "PASS" if has_trunk_output and has_expected_vlans else "FAIL",
        "has_trunk_output": has_trunk_output,
        "expected_allowed_vlans": EXPECTED_ALLOWED_VLANS,
        "has_allowed_vlans_10_20_30_40_70_80": has_expected_vlans,
    }


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "vlans": {},
        "svis": {},
        "trunks": {},
    }

    for device in DEVICES:
        report["vlans"][device] = validate_vlans(device)
        report["trunks"][device] = validate_trunks(device)

    report["svis"][L3_DEVICE] = validate_svis()

    REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Validation report created: {REPORT_FILE}")

    failures = json.dumps(report).count("FAIL")

    if failures > 0:
        print(f"[FAIL] Validation completed with {failures} failure(s)")
        exit(1)

    print("[PASS] All Lab 2 validations passed")


if __name__ == "__main__":
    main()