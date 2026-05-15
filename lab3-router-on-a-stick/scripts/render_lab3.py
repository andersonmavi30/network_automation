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


def main():
    intent = load_intent()

    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Render R1 config
    r1_config = render_template(
        env,
        "router_subinterfaces.j2",
        {
            "router_on_a_stick": intent["router_on_a_stick"],
            "vlans": intent["vlans"],
        },
    )
    save_config("R1", r1_config)

    # Render access switch configs
    for switch_name, switch_data in intent["access_switches"].items():
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
                "trunk_to_router": switch_data["trunk_to_router"],
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

    print("[OK] Lab 3 render completed successfully.")


if __name__ == "__main__":
    main()
