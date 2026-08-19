#!/usr/bin/env python3

import ipaddress
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined


BASE_DIR = Path(__file__).resolve().parent.parent

TOPOLOGY_FILE = BASE_DIR / "vars" / "topology.yml"
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "configs"

TEMPLATE_NAME = "eigrp.j2"


def load_topology():
    """Carga la topología declarativa del Lab 6."""

    if not TOPOLOGY_FILE.exists():
        raise FileNotFoundError(
            f"No existe el archivo: {TOPOLOGY_FILE}"
        )

    with open(
        TOPOLOGY_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        return yaml.safe_load(file)


def build_networks(interfaces):
    """
    Calcula las redes EIGRP a partir de las IPs.

    Management queda excluido.
    """

    networks = []

    for interface_name, interface_data in interfaces.items():

        interface_type = interface_data["type"]

        if interface_type == "management":
            continue

        ip_interface = ipaddress.ip_interface(
            interface_data["ip"]
        )

        network = ip_interface.network

        wildcard = ipaddress.IPv4Address(
            int(network.hostmask)
        )

        networks.append(
            {
                "interface": interface_name,
                "network_address": str(
                    network.network_address
                ),
                "prefix_length": network.prefixlen,
                "wildcard": str(wildcard),
            }
        )

    return networks


def build_interfaces(interfaces):
    """
    Convierte las interfaces YAML a objetos simples
    que Jinja2 pueda consumir mediante interface.type.
    """

    result = {}

    for interface_name, interface_data in interfaces.items():

        result[interface_name] = {
            "type": interface_data["type"],
            "ip": interface_data["ip"],
            "peer": interface_data.get("peer"),
        }

    return result


def render_router(
    template,
    router_name,
    router_data,
):
    """Genera la configuración EIGRP para un router."""

    interfaces = build_interfaces(
        router_data["interfaces"]
    )

    networks = build_networks(
        router_data["interfaces"]
    )

    rendered = template.render(
        router_name=router_name,
        interfaces=interfaces,
        networks=networks,
    )

    output_file = OUTPUT_DIR / f"{router_name}.cfg"

    with open(
        output_file,
        "w",
        encoding="utf-8",
    ) as file:
        file.write(rendered.rstrip())
        file.write("\n")

    print(
        f"[RENDER] {router_name} -> {output_file}"
    )


def main():

    print(
        "========================================"
    )
    print(
        " LAB6 - EIGRP JINJA2 RENDER"
    )
    print(
        "========================================"
    )

    topology = load_topology()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    environment = Environment(
        loader=FileSystemLoader(
            TEMPLATES_DIR
        ),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    template = environment.get_template(
        TEMPLATE_NAME
    )

    for router_name, router_data in topology[
        "devices"
    ].items():

        render_router(
            template,
            router_name,
            router_data,
        )

    print()
    print(
        "========================================"
    )
    print(
        " RENDER COMPLETADO"
    )
    print(
        "========================================"
    )


if __name__ == "__main__":

    try:
        main()

    except Exception as error:

        print(
            f"\n[ERROR] {error}"
        )

        sys.exit(1)
