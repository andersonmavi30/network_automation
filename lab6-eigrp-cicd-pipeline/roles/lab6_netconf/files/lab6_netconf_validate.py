#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pynetbox
import yaml
from ncclient import manager


CISCO_NATIVE_NAMESPACE = (
    "http://cisco.com/ns/yang/Cisco-IOS-XE-native"
)

NATIVE_INTERFACE_FILTER = f"""
<native xmlns="{CISCO_NATIVE_NAMESPACE}">
  <interface/>
</native>
"""


def required_environment(variable_name: str) -> str:
    """Obtiene una variable de entorno obligatoria."""

    value = os.getenv(variable_name)

    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {variable_name}"
        )

    return value


def get_primary_ip(device: Any) -> str:
    """Obtiene la IPv4 primaria de management desde NetBox."""

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


def local_name(tag: str) -> str:
    """Elimina el namespace XML de un tag."""

    if "}" in tag:
        return tag.split("}", 1)[1]

    return tag


def expected_interfaces(
    device_name: str,
    topology: dict[str, Any],
) -> set[str]:
    """Obtiene las interfaces esperadas desde topology.yml."""

    if device_name not in topology["devices"]:
        raise RuntimeError(
            f"{device_name} is not defined in topology.yml"
        )

    return set(
        topology["devices"][device_name]["interfaces"].keys()
    )


def extract_native_interfaces(
    xml_data: str,
) -> set[str]:
    """
    Extrae nombres de interfaces desde Cisco-IOS-XE-native.

    Ejemplo YANG/XML:
      interface
        GigabitEthernet
          name 1

    Resultado:
      GigabitEthernet1
    """

    root = ElementTree.fromstring(
        xml_data
    )

    namespace = {
        "native": CISCO_NATIVE_NAMESPACE,
    }

    interface_container = root.find(
        ".//native:interface",
        namespace,
    )

    if interface_container is None:
        return set()

    interfaces: set[str] = set()

    for interface_entry in interface_container:

        interface_type = local_name(
            interface_entry.tag
        )

        name_element = interface_entry.find(
            f"{{{CISCO_NATIVE_NAMESPACE}}}name"
        )

        if name_element is None:
            continue

        if not name_element.text:
            continue

        interface_name = (
            f"{interface_type}"
            f"{name_element.text.strip()}"
        )

        interfaces.add(
            interface_name
        )

    return interfaces


def has_native_capability(
    capabilities: list[str],
) -> bool:
    """Valida que IOS XE anuncie Cisco-IOS-XE-native."""

    return any(
        "Cisco-IOS-XE-native" in capability
        for capability in capabilities
    )


def validate_device(
    device: Any,
    topology: dict[str, Any],
    username: str,
    password: str,
    output_directory: Path,
) -> dict[str, Any]:
    """Valida un router mediante NETCONF/YANG."""

    device_name = device.name
    management_ip = get_primary_ip(
        device
    )

    expected = expected_interfaces(
        device_name,
        topology,
    )

    evidence: dict[str, Any] = {
        "device": device_name,
        "management_ip": management_ip,
        "netconf_port": 830,
        "expected_interfaces": sorted(
            expected
        ),
        "observed_interfaces": [],
        "server_capability_count": 0,
        "native_yang_capability": False,
        "checks": {},
        "errors": [],
    }

    connection = None

    try:

        connection = manager.connect(
            host=management_ip,
            port=830,
            username=username,
            password=password,
            hostkey_verify=False,
            allow_agent=False,
            look_for_keys=False,
            device_params={
                "name": "iosxe",
            },
            timeout=30,
        )

        capabilities = sorted(
            str(capability)
            for capability
            in connection.server_capabilities
        )

        native_capability = (
            has_native_capability(
                capabilities
            )
        )

        evidence[
            "server_capability_count"
        ] = len(
            capabilities
        )

        evidence[
            "native_yang_capability"
        ] = native_capability

        capability_file = (
            output_directory
            / f"{device_name}_capabilities.json"
        )

        capability_file.write_text(
            json.dumps(
                {
                    "device": device_name,
                    "capabilities": capabilities,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        reply = connection.get_config(
            source="running",
            filter=(
                "subtree",
                NATIVE_INTERFACE_FILTER,
            ),
        )

        xml_output = reply.xml

        xml_file = (
            output_directory
            / f"{device_name}_interfaces.xml"
        )

        xml_file.write_text(
            xml_output,
            encoding="utf-8",
        )

        observed = (
            extract_native_interfaces(
                xml_output
            )
        )

        missing_interfaces = (
            expected - observed
        )

        evidence[
            "observed_interfaces"
        ] = sorted(
            observed
        )

        evidence[
            "missing_interfaces"
        ] = sorted(
            missing_interfaces
        )

        evidence["checks"][
            "netconf_session"
        ] = True

        evidence["checks"][
            "native_yang_model"
        ] = native_capability

        evidence["checks"][
            "expected_interfaces_present"
        ] = (
            not missing_interfaces
        )

    except Exception as error:

        evidence["errors"].append(
            f"{type(error).__name__}: {error}"
        )

        evidence["checks"].setdefault(
            "netconf_session",
            False,
        )

        evidence["checks"].setdefault(
            "native_yang_model",
            False,
        )

        evidence["checks"].setdefault(
            "expected_interfaces_present",
            False,
        )

    finally:

        if connection is not None:

            try:
                connection.close_session()

            except Exception:
                pass

    evidence["validation_passed"] = (
        not evidence["errors"]
        and all(
            evidence["checks"].values()
        )
    )

    evidence_file = (
        output_directory
        / f"{device_name}.json"
    )

    evidence_file.write_text(
        json.dumps(
            evidence,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return evidence


def main() -> None:
    """Ejecuta validacion NETCONF/YANG del Lab 6."""

    parser = argparse.ArgumentParser(
        description=(
            "Validate Lab 6 IOS XE devices "
            "using NETCONF and YANG"
        )
    )

    parser.add_argument(
        "--netbox-url",
        required=True,
    )

    parser.add_argument(
        "--site",
        default="lab6",
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
        "NETCONF_USERNAME"
    )

    password = required_environment(
        "NETCONF_PASSWORD"
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

        topology = yaml.safe_load(
            file
        )

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
            "No active devices found in "
            f"NetBox site '{args.site}'"
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
            "NetBox devices do not match "
            "topology intent. "
            f"NetBox={sorted(netbox_devices)}, "
            f"Topology={sorted(expected_devices)}"
        )

    results: list[
        dict[str, Any]
    ] = []

    for device in devices:

        results.append(
            validate_device(
                device,
                topology,
                username,
                password,
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
        "protocol": "NETCONF",
        "port": 830,
        "yang_model": (
            "Cisco-IOS-XE-native"
        ),
        "device_count": len(
            results
        ),
        "passed_devices": (
            passed_devices
        ),
        "failed_devices": (
            failed_devices
        ),
        "validation_passed": (
            not failed_devices
        ),
    }

    summary_file = (
        output_directory
        / "netconf_summary.json"
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
                    "failed_devices": (
                        failed_devices
                    ),
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
                "passed_devices": (
                    passed_devices
                ),
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
                    "error_type": (
                        type(error).__name__
                    ),
                    "error": str(error),
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        sys.exit(1)
