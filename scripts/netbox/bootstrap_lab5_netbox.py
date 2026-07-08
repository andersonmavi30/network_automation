#!/usr/bin/env python3

import os
import sys
from pathlib import Path

import yaml
import requests

NETBOX_URL = os.getenv("NETBOX_URL", "http://192.168.1.16:8000").rstrip("/")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")

REPO_ROOT = Path(__file__).resolve().parents[2]
SOT_FILE = REPO_ROOT / "lab5-ospf-multiarea-jenkins-pipeline/vars/lab5_topology.yml"

if not NETBOX_TOKEN:
    print("ERROR: NETBOX_TOKEN environment variable is not set")
    sys.exit(1)

session = requests.Session()
session.headers.update({
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
})


def slugify(value):
    return str(value).lower().replace("_", "-").replace(" ", "-")


def nb_get(endpoint, **params):
    response = session.get(f"{NETBOX_URL}/api/{endpoint}/", params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def nb_create(endpoint, payload):
    response = session.post(f"{NETBOX_URL}/api/{endpoint}/", json=payload, timeout=15)
    response.raise_for_status()
    return response.json()


def nb_patch(endpoint, obj_id, payload):
    response = session.patch(f"{NETBOX_URL}/api/{endpoint}/{obj_id}/", json=payload, timeout=15)
    response.raise_for_status()
    return response.json()


def get_or_create(endpoint, lookup, payload):
    result = nb_get(endpoint, **lookup)

    if result["count"] > 0:
        obj = result["results"][0]
        print(f"EXISTS: {endpoint} -> {obj.get('name', obj.get('prefix', obj.get('address')))}")
        return obj

    obj = nb_create(endpoint, payload)
    print(f"CREATED: {endpoint} -> {obj.get('name', obj.get('prefix', obj.get('address')))}")
    return obj


def main():
    with open(SOT_FILE, "r", encoding="utf-8") as f:
        sot = yaml.safe_load(f)

    site = get_or_create(
        "dcim/sites",
        {"slug": "lab5"},
        {"name": "LAB5", "slug": "lab5", "status": "active"},
    )

    manufacturer = get_or_create(
        "dcim/manufacturers",
        {"slug": "cisco"},
        {"name": "Cisco", "slug": "cisco"},
    )

    role = get_or_create(
        "dcim/device-roles",
        {"slug": "router"},
        {"name": "router", "slug": "router", "color": "2196f3"},
    )

    platform = get_or_create(
        "dcim/platforms",
        {"slug": "cisco-ios-xe"},
        {
            "name": "Cisco IOS XE",
            "slug": "cisco-ios-xe",
            "manufacturer": manufacturer["id"],
        },
    )

    device_type = get_or_create(
        "dcim/device-types",
        {"slug": "cisco-csr1000v"},
        {
            "manufacturer": manufacturer["id"],
            "model": "Cisco CSR1000v",
            "slug": "cisco-csr1000v",
        },
    )

    prefixes = []
    prefixes.append("172.30.30.0/26")

    for link in sot["links"]:
        prefixes.append(link["network"])

    for lan in sot["lans"]:
        prefixes.append(lan["network"])

    for device_data in sot["devices"].values():
        prefixes.append(device_data["loopback0"])

    for prefix in prefixes:
        get_or_create(
            "ipam/prefixes",
            {"prefix": prefix},
            {
                "prefix": prefix,
                "status": "active",
                "description": "Lab 5 OSPF multi-area automated bootstrap",
            },
        )

    devices = {}

    for hostname, data in sot["devices"].items():
        device = get_or_create(
            "dcim/devices",
            {"name": hostname},
            {
                "name": hostname,
                "status": "active",
                "site": site["id"],
                "role": role["id"],
                "device_type": device_type["id"],
                "platform": platform["id"],
                "description": f"Lab 5 role: {data['role']}",
            },
        )

        devices[hostname] = device

        mgmt_intf = get_or_create(
            "dcim/interfaces",
            {"device_id": device["id"], "name": "Management0"},
            {
                "device": device["id"],
                "name": "Management0",
                "type": "virtual",
                "description": "Management interface",
            },
        )

        mgmt_ip = get_or_create(
            "ipam/ip-addresses",
            {"address": f"{data['mgmt_ip']}/26"},
            {
                "address": f"{data['mgmt_ip']}/26",
                "status": "active",
                "description": f"{hostname} management IP",
                "assigned_object_type": "dcim.interface",
                "assigned_object_id": mgmt_intf["id"],
            },
        )

        nb_patch("dcim/devices", device["id"], {"primary_ip4": mgmt_ip["id"]})

        loopback_intf = get_or_create(
            "dcim/interfaces",
            {"device_id": device["id"], "name": "Loopback0"},
            {
                "device": device["id"],
                "name": "Loopback0",
                "type": "virtual",
                "description": "OSPF router-id source",
            },
        )

        get_or_create(
            "ipam/ip-addresses",
            {"address": data["loopback0"]},
            {
                "address": data["loopback0"],
                "status": "active",
                "description": f"{hostname} Loopback0",
                "assigned_object_type": "dcim.interface",
                "assigned_object_id": loopback_intf["id"],
            },
        )

    for link in sot["links"]:
        for endpoint in link["endpoints"]:
            device = devices[endpoint["device"]]

            intf = get_or_create(
                "dcim/interfaces",
                {"device_id": device["id"], "name": endpoint["interface"]},
                {
                    "device": device["id"],
                    "name": endpoint["interface"],
                    "type": "1000base-t",
                    "description": f"Lab5 link {link['name']} area {link['area']}",
                },
            )

            get_or_create(
                "ipam/ip-addresses",
                {"address": endpoint["ip"]},
                {
                    "address": endpoint["ip"],
                    "status": "active",
                    "description": f"{endpoint['device']} {endpoint['interface']} - {link['name']}",
                    "assigned_object_type": "dcim.interface",
                    "assigned_object_id": intf["id"],
                },
            )

    for lan in sot["lans"]:
        device = devices[lan["gateway_device"]]

        intf = get_or_create(
            "dcim/interfaces",
            {"device_id": device["id"], "name": lan["gateway_interface"]},
            {
                "device": device["id"],
                "name": lan["gateway_interface"],
                "type": "1000base-t",
                "description": f"Gateway for {lan['name']} area {lan['area']}",
            },
        )

        get_or_create(
            "ipam/ip-addresses",
            {"address": lan["gateway_ip"]},
            {
                "address": lan["gateway_ip"],
                "status": "active",
                "description": f"{lan['gateway_device']} gateway for {lan['name']}",
                "assigned_object_type": "dcim.interface",
                "assigned_object_id": intf["id"],
            },
        )

    print("NETBOX LAB5 BOOTSTRAP: DONE")


if __name__ == "__main__":
    main()
