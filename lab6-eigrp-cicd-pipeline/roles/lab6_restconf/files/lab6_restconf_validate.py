#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import pynetbox
import requests
import urllib3
import yaml


urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)


HEADERS = {
    "Accept": "application/yang-data+json",
}


RESTCONF_ENDPOINTS = {
    "restconf_root": {
        "path": "/restconf/",
        "required": False,
        "description": "RESTCONF API root",
    },
    "native_root": {
        "path": (
            "/restconf/data/"
            "Cisco-IOS-XE-native:native"
        ),
        "required": True,
        "description": (
            "Cisco IOS XE native YANG root"
        ),
    },
    "hostname": {
        "path": (
            "/restconf/data/"
            "Cisco-IOS-XE-native:native/"
            "hostname"
        ),
        "required": False,
        "description": "Device hostname",
    },
    "interfaces": {
        "path": (
            "/restconf/data/"
            "Cisco-IOS-XE-native:native/"
            "interface"
        ),
        "required": True,
        "description": (
            "Cisco IOS XE native interfaces"
        ),
    },
    "router": {
        "path": (
            "/restconf/data/"
            "Cisco-IOS-XE-native:native/"
            "router"
        ),
        "required": False,
        "description": (
            "Cisco IOS XE native routing configuration"
        ),
    },
    "ietf_interfaces": {
        "path": (
            "/restconf/data/"
            "ietf-interfaces:interfaces"
        ),
        "required": False,
        "description": (
            "IETF interfaces YANG model"
        ),
    },
    "yang_library": {
        "path": (
            "/restconf/data/"
            "ietf-yang-library:yang-library"
        ),
        "required": False,
        "description": (
            "YANG library and supported models"
        ),
    },
    "operations": {
        "path": "/restconf/operations",
        "required": False,
        "description": (
            "Available RESTCONF RPC operations"
        ),
    },
}


def required_environment(
    variable_name: str,
) -> str:
    """Obtiene una variable de entorno obligatoria."""

    value = os.getenv(
        variable_name
    )

    if not value:

        raise RuntimeError(
            "Missing required environment variable: "
            f"{variable_name}"
        )

    return value


def get_primary_ip(
    device: Any,
) -> str:
    """Obtiene la IPv4 primaria de management desde NetBox."""

    if not device.primary_ip4:

        raise RuntimeError(
            f"{device.name} does not have "
            "primary_ip4 in NetBox"
        )

    address = getattr(
        device.primary_ip4,
        "address",
        device.primary_ip4,
    )

    return str(
        address
    ).split("/")[0]


def expected_interfaces(
    device_name: str,
    topology: dict[str, Any],
) -> set[str]:
    """Obtiene interfaces esperadas desde topology.yml."""

    if device_name not in topology[
        "devices"
    ]:

        raise RuntimeError(
            f"{device_name} is not defined "
            "in topology.yml"
        )

    return set(
        topology[
            "devices"
        ][
            device_name
        ][
            "interfaces"
        ].keys()
    )


def extract_native_interfaces(
    data: dict[str, Any],
) -> set[str]:
    """
    Extrae interfaces del modelo Cisco-IOS-XE-native.

    Ejemplo:

    GigabitEthernet:
      - name: "1"
      - name: "2"

    Resultado:

    GigabitEthernet1
    GigabitEthernet2
    """

    interfaces: set[str] = set()

    def walk(
        value: Any,
    ) -> None:

        if isinstance(
            value,
            dict,
        ):

            for key, child in value.items():

                interface_type = (
                    str(
                        key
                    ).split(":")[-1]
                )

                if isinstance(
                    child,
                    list,
                ):

                    for entry in child:

                        if (
                            isinstance(
                                entry,
                                dict,
                            )
                            and "name" in entry
                        ):

                            interfaces.add(
                                f"{interface_type}"
                                f"{entry['name']}"
                            )

                walk(
                    child
                )

        elif isinstance(
            value,
            list,
        ):

            for item in value:

                walk(
                    item
                )

    walk(
        data
    )

    return interfaces


def save_response(
    output_directory: Path,
    device_name: str,
    endpoint_name: str,
    response: requests.Response,
) -> None:
    """Guarda la respuesta RESTCONF para usarla como artifact."""

    output_file = (
        output_directory
        / f"{device_name}_{endpoint_name}.json"
    )

    try:

        data = response.json()

        output_file.write_text(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    except ValueError:

        output_file = (
            output_directory
            / f"{device_name}_{endpoint_name}.txt"
        )

        output_file.write_text(
            response.text,
            encoding="utf-8",
        )


def get_endpoint(
    session: requests.Session,
    base_url: str,
    endpoint_name: str,
    endpoint_data: dict[str, Any],
    output_directory: Path,
    device_name: str,
) -> dict[str, Any]:
    """Ejecuta un GET RESTCONF y almacena evidencia."""

    path = endpoint_data[
        "path"
    ]

    url = (
        f"{base_url}"
        f"{path}"
    )

    result: dict[str, Any] = {
        "name": endpoint_name,
        "method": "GET",
        "path": path,
        "url": url,
        "required": endpoint_data[
            "required"
        ],
        "description": endpoint_data[
            "description"
        ],
        "status_code": None,
        "successful": False,
        "data": None,
        "error": None,
    }

    try:

        response = session.get(
            url,
            headers=HEADERS,
            verify=False,
            timeout=30,
        )

        result[
            "status_code"
        ] = response.status_code

        result[
            "successful"
        ] = (
            200
            <= response.status_code
            < 300
        )

        save_response(
            output_directory,
            device_name,
            endpoint_name,
            response,
        )

        if result[
            "successful"
        ]:

            try:

                result[
                    "data"
                ] = response.json()

            except ValueError:

                result[
                    "data"
                ] = None

    except Exception as error:

        result[
            "error"
        ] = (
            f"{type(error).__name__}: "
            f"{error}"
        )

    return result


def build_postman_catalog(
    output_directory: Path,
) -> None:
    """
    Genera catalogo de endpoints reutilizable
    posteriormente en Postman.
    """

    catalog = []

    for name, endpoint in (
        RESTCONF_ENDPOINTS.items()
    ):

        catalog.append(
            {
                "name": name,
                "method": "GET",
                "path": endpoint[
                    "path"
                ],
                "required": endpoint[
                    "required"
                ],
                "description": endpoint[
                    "description"
                ],
                "accept": (
                    "application/yang-data+json"
                ),
            }
        )

    catalog_file = (
        output_directory
        / "restconf_endpoint_catalog.json"
    )

    catalog_file.write_text(
        json.dumps(
            catalog,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def validate_device(
    device: Any,
    topology: dict[str, Any],
    username: str,
    password: str,
    output_directory: Path,
) -> dict[str, Any]:
    """Valida un router mediante varios endpoints RESTCONF."""

    device_name = device.name

    management_ip = get_primary_ip(
        device
    )

    expected = expected_interfaces(
        device_name,
        topology,
    )

    base_url = (
        f"https://{management_ip}"
    )

    evidence: dict[str, Any] = {
        "device": device_name,
        "management_ip": management_ip,
        "protocol": "RESTCONF",
        "transport": "HTTPS",
        "yang_model": (
            "Cisco-IOS-XE-native"
        ),
        "expected_interfaces": sorted(
            expected
        ),
        "observed_interfaces": [],
        "missing_interfaces": [],
        "endpoints": {},
        "checks": {},
        "errors": [],
    }

    session = requests.Session()

    session.auth = (
        username,
        password,
    )

    endpoint_results: dict[
        str,
        dict[str, Any],
    ] = {}

    for endpoint_name, endpoint_data in (
        RESTCONF_ENDPOINTS.items()
    ):

        endpoint_results[
            endpoint_name
        ] = get_endpoint(
            session,
            base_url,
            endpoint_name,
            endpoint_data,
            output_directory,
            device_name,
        )

    evidence[
        "endpoints"
    ] = {
        name: {
            "method": result[
                "method"
            ],
            "path": result[
                "path"
            ],
            "required": result[
                "required"
            ],
            "status_code": result[
                "status_code"
            ],
            "successful": result[
                "successful"
            ],
            "error": result[
                "error"
            ],
        }
        for name, result
        in endpoint_results.items()
    }

    required_results = [
        result
        for result
        in endpoint_results.values()
        if result[
            "required"
        ]
    ]

    evidence["checks"][
        "required_endpoints"
    ] = all(
        result[
            "successful"
        ]
        for result
        in required_results
    )

    interface_result = (
        endpoint_results[
            "interfaces"
        ]
    )

    interface_data = (
        interface_result.get(
            "data"
        )
    )

    if (
        interface_result[
            "successful"
        ]
        and isinstance(
            interface_data,
            dict,
        )
    ):

        observed = (
            extract_native_interfaces(
                interface_data
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
            "expected_interfaces_present"
        ] = (
            not missing_interfaces
        )

    else:

        evidence["checks"][
            "expected_interfaces_present"
        ] = False

    for name, result in (
        endpoint_results.items()
    ):

        if (
            result[
                "required"
            ]
            and not result[
                "successful"
            ]
        ):

            evidence[
                "errors"
            ].append(
                "Required RESTCONF endpoint "
                f"'{name}' failed. "
                f"HTTP={result['status_code']} "
                f"error={result['error']}"
            )

    evidence[
        "validation_passed"
    ] = (
        not evidence[
            "errors"
        ]
        and all(
            evidence[
                "checks"
            ].values()
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
    """Ejecuta validacion RESTCONF/YANG del Lab 6."""

    parser = argparse.ArgumentParser(
        description=(
            "Validate Lab 6 IOS XE devices "
            "using RESTCONF and YANG"
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

    netbox_token = (
        required_environment(
            "NETBOX_TOKEN"
        )
    )

    username = (
        required_environment(
            "RESTCONF_USERNAME"
        )
    )

    password = (
        required_environment(
            "RESTCONF_PASSWORD"
        )
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

    build_postman_catalog(
        output_directory
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

    if (
        netbox_devices
        != expected_devices
    ):

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
        result[
            "device"
        ]
        for result in results
        if result[
            "validation_passed"
        ]
    ]

    failed_devices = [
        result[
            "device"
        ]
        for result in results
        if not result[
            "validation_passed"
        ]
    ]

    summary = {
        "site": args.site,
        "protocol": "RESTCONF",
        "transport": "HTTPS",
        "yang_model": (
            "Cisco-IOS-XE-native"
        ),
        "device_count": len(
            results
        ),
        "tested_endpoints": (
            len(
                RESTCONF_ENDPOINTS
            )
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
        / "restconf_summary.json"
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
                    "error": str(
                        error
                    ),
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        sys.exit(1)
