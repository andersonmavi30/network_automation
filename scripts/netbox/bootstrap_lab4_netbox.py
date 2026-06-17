#!/usr/bin/env python3

import os
import sys
import yaml
import requests

NETBOX_URL = os.getenv("NETBOX_URL", "http://192.168.1.16:8000").rstrip("/")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")
SOT_FILE = "lab4-ospf-ansible-pipeline/intent/lab4_source_of_truth.yml"

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
    return value.lower().replace("_", "-").replace(" ", "-")


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
        {"slug": "pnetlab"},
        {"name": "PNETLAB", "slug": "pnetlab", "status": "active"},
    )

    manufacturer = get_or_create(
        "dcim/manufacturers",
        {"slug": "cisco"},
        {"name": "Cisco", "slug": "cisco"},
    )

    roles = {}
    for role_name in ["router", "access_switch", "management_switch"]:
        roles[role_name] = get_or_create(
            "dcim/device-roles",
            {"slug": slugify(role_name)},
            {
                "name": role_name,
                "slug": slugify(role_name),
                "color": "2196f3",
            },
        )

    platform = get_or_create(
        "dcim/platforms",
        {"slug": "cisco-ios"},
        {
            "name": "Cisco IOS",
            "slug": "cisco-ios",
            "manufacturer": manufacturer["id"],
        },
    )

    router_type = get_or_create(
        "dcim/device-types",
        {"slug": "cisco-iosv-router"},
        {
            "manufacturer": manufacturer["id"],
            "model": "Cisco IOSv Router",
            "slug": "cisco-iosv-router",
        },
    )

    switch_type = get_or_create(
        "dcim/device-types",
        {"slug": "cisco-iosv-l2-switch"},
        {
            "manufacturer": manufacturer["id"],
            "model": "Cisco IOSvL2 Switch",
            "slug": "cisco-iosv-l2-switch",
        },
    )

    prefixes = [sot["management"]["network"], sot["lan"]["network"]]
    prefixes.extend(link["network"] for link in sot["links"])

    for prefix in prefixes:
        get_or_create(
            "ipam/prefixes",
            {"prefix": prefix},
            {
                "prefix": prefix,
                "status": "active",
                "description": "Lab 4 automated bootstrap",
            },
        )

    for hostname, data in sot["devices"].items():
        if hostname == "SW_DMZ":
            continue

        role_name = data["role"]
        device_type = router_type if role_name == "router" else switch_type

        device = get_or_create(
            "dcim/devices",
            {"name": hostname},
            {
                "name": hostname,
                "status": "active",
                "site": site["id"],
                "role": roles[role_name]["id"],
                "device_type": device_type["id"],
                "platform": platform["id"],
            },
        )

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

    print("NETBOX LAB4 BOOTSTRAP: DONE")


if __name__ == "__main__":
    main()
