#!/usr/bin/env python3

from pathlib import Path
import yaml
from jinja2 import Environment, FileSystemLoader


BASE_DIR = Path(__file__).resolve().parents[1]
INTENT_FILE = BASE_DIR / "intent" / "lab3_intent.yml"
TEMPLATE_DIR = BASE_DIR / "templates"
RENDERED_DIR = BASE_DIR / "artifacts" / "rendered"


def load_intent():
    with open(INTENT_FILE, "r") as file:
        return yaml.safe_load(file)


def render_template(env, template_name, data):
    template = env.get_template(template_name)
    return template.render(**data)


def save_config(device_name, config):
    RENDERED_DIR.mkdir(parents=True, exist_ok=True)

    output_file = RENDERED_DIR / f"{device_name}.cfg"

    with open(output_file, "w") as file:
        file.write(config.strip() + "\n")

    print(f"[OK] Rendered config created: {output_file}")


def build_trunk_interfaces(switch_name, switch_data):
    trunk_interfaces = []

    if "trunk_to_router" in switch_data:
        trunk_interfaces.append(
            {
                "interface": switch_data["trunk_to_router"],
                "connected_to": "R1",
            }
        )

    if "trunk_to_upstream" in switch_data:
        trunk_interfaces.append(
            {
                "interface": switch_data["trunk_to_upstream"],
                "connected_to": switch_data["upstream_switch"],
            }
        )

    for trunk in switch_data.get("downstream_trunks", []):
        trunk_interfaces.append(
            {
                "interface": trunk["interface"],
                "connected_to": trunk["connected_to"],
            }
        )

    return trunk_interfaces


def render_router_config(env, intent):
    router_config = render_template(
        env,
        "router_subinterfaces.j2",
        {
            "router_on_a_stick": intent["router_on_a_stick"],
            "vlans": intent["vlans"],
        },
    )

    save_config("R1", router_config)


def render_switch_configs(env, intent):
    for switch_name, switch_data in intent["access_switches"].items():
        trunk_interfaces = build_trunk_interfaces(switch_name, switch_data)

        vlans_config = render_template(
            env,
            "switch_vlans.j2",
            {
                "vlans": intent["vlans"],
            },
        )

        trunks_config = render_template(
            env,
            "switch_trunks.j2",
            {
                "trunk_interfaces": trunk_interfaces,
                "vlans": intent["vlans"],
            },
        )

        access_ports_config = render_template(
            env,
            "switch_access_ports.j2",
            {
                "access_ports": switch_data["access_ports"],
            },
        )

        full_config = "\n".join(
            [
                vlans_config,
                trunks_config,
                access_ports_config,
            ]
        )

        save_config(switch_name, full_config)


def main():
    intent = load_intent()

    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    render_router_config(env, intent)
    render_switch_configs(env, intent)

    print("[OK] Lab 3 render completed successfully.")


if __name__ == "__main__":
    main()