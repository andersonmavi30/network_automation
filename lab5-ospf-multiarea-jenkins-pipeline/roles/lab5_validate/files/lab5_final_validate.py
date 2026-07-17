#!/usr/bin/env python3

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consolidate all Lab 5 validation artifacts."
    )
    parser.add_argument(
        "--artifacts-dir",
        required=True,
        help="Path to the Lab 5 artifacts directory.",
    )
    parser.add_argument(
        "--topology-file",
        required=True,
        help="Path to vars/lab5_topology.yml.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where the final summary will be written.",
    )
    return parser.parse_args()


def read_json(path: Path) -> Tuple[Dict[str, Any], str]:
    try:
        with path.open("r", encoding="utf-8") as file_handle:
            return json.load(file_handle), ""
    except FileNotFoundError:
        return {}, f"Required artifact does not exist: {path}"
    except json.JSONDecodeError as error:
        return {}, f"Invalid JSON in {path}: {error}"
    except OSError as error:
        return {}, f"Could not read {path}: {error}"


def load_expected_devices(topology_file: Path) -> List[str]:
    with topology_file.open("r", encoding="utf-8") as file_handle:
        topology_data = yaml.safe_load(file_handle) or {}

    if "lab5_topology" in topology_data:
        topology_data = topology_data["lab5_topology"]

    devices = topology_data.get("devices", {})

    if not isinstance(devices, dict) or not devices:
        raise ValueError(
            f"No devices were found in topology file: {topology_file}"
        )

    return sorted(devices.keys())


def validate_batfish(
    artifacts_dir: Path,
    expected_devices: List[str],
) -> Dict[str, Any]:
    summary_file = (
        artifacts_dir
        / "batfish"
        / "output"
        / "batfish_summary.json"
    )
    summary, read_error = read_json(summary_file)
    errors = []

    if read_error:
        errors.append(read_error)
    else:
        config_count = int(summary.get("config_count", 0))
        parse_status = summary.get("parse_status", [])

        if config_count != len(expected_devices):
            errors.append(
                f"Batfish analyzed {config_count} configurations; "
                f"{len(expected_devices)} were expected."
            )

        if not isinstance(parse_status, list) or not parse_status:
            errors.append("Batfish parse_status is empty or invalid.")
        else:
            failed_configs = []

            for record in parse_status:
                status = str(
                    record.get("Status", record.get("status", ""))
                ).upper()

                if status != "PASSED":
                    failed_configs.append(record)

            if failed_configs:
                errors.append(
                    "One or more configurations did not pass "
                    "Batfish parsing."
                )

    return {
        "artifact": str(summary_file),
        "validation_passed": not errors,
        "config_count": summary.get("config_count", 0),
        "init_issues_count": summary.get("init_issues_count", 0),
        "errors": errors,
    }


def validate_precheck(
    artifacts_dir: Path,
    expected_devices: List[str],
) -> Dict[str, Any]:
    precheck_dir = artifacts_dir / "precheck"
    errors = []
    validated_devices = []

    found_files = {
        path.stem: path
        for path in precheck_dir.glob("*.json")
    }

    missing_devices = sorted(
        set(expected_devices) - set(found_files.keys())
    )
    unexpected_devices = sorted(
        set(found_files.keys()) - set(expected_devices)
    )

    if missing_devices:
        errors.append(
            "Missing precheck artifacts for: "
            + ", ".join(missing_devices)
        )

    if unexpected_devices:
        errors.append(
            "Unexpected precheck artifacts found for: "
            + ", ".join(unexpected_devices)
        )

    for device_name in expected_devices:
        evidence_file = found_files.get(device_name)

        if evidence_file is None:
            continue

        evidence, read_error = read_json(evidence_file)

        if read_error:
            errors.append(read_error)
            continue

        required_fields = [
            "device",
            "management_ip",
            "commands",
            "stdout",
        ]
        missing_fields = [
            field
            for field in required_fields
            if field not in evidence
        ]

        if missing_fields:
            errors.append(
                f"{device_name} precheck is missing fields: "
                + ", ".join(missing_fields)
            )
            continue

        if evidence.get("device") != device_name:
            errors.append(
                f"{device_name} precheck contains an incorrect "
                f"device value: {evidence.get('device')}"
            )
            continue

        commands = evidence.get("commands", [])
        stdout = evidence.get("stdout", [])

        if not isinstance(commands, list) or not commands:
            errors.append(
                f"{device_name} precheck contains no commands."
            )
            continue

        if not isinstance(stdout, list):
            errors.append(
                f"{device_name} precheck stdout is invalid."
            )
            continue

        if len(commands) != len(stdout):
            errors.append(
                f"{device_name} precheck has {len(commands)} commands "
                f"but {len(stdout)} outputs."
            )
            continue

        validated_devices.append(device_name)

    return {
        "artifact_directory": str(precheck_dir),
        "validation_passed": not errors,
        "validated_devices": sorted(validated_devices),
        "errors": errors,
    }


def validate_postcheck(
    artifacts_dir: Path,
    expected_devices: List[str],
) -> Dict[str, Any]:
    postcheck_dir = artifacts_dir / "postcheck"
    errors = []
    device_results = {}

    found_files = {
        path.stem: path
        for path in postcheck_dir.glob("*.json")
    }

    missing_devices = sorted(
        set(expected_devices) - set(found_files.keys())
    )
    unexpected_devices = sorted(
        set(found_files.keys()) - set(expected_devices)
    )

    if missing_devices:
        errors.append(
            "Missing postcheck artifacts for: "
            + ", ".join(missing_devices)
        )

    if unexpected_devices:
        errors.append(
            "Unexpected postcheck artifacts found for: "
            + ", ".join(unexpected_devices)
        )

    for device_name in expected_devices:
        evidence_file = found_files.get(device_name)

        if evidence_file is None:
            continue

        evidence, read_error = read_json(evidence_file)

        if read_error:
            errors.append(read_error)
            continue

        expected_neighbors = int(
            evidence.get("expected_ospf_neighbors", -1)
        )
        observed_neighbors = int(
            evidence.get("observed_full_ospf_neighbors", -1)
        )

        device_passed = (
            expected_neighbors >= 0
            and observed_neighbors == expected_neighbors
        )

        device_results[device_name] = {
            "expected_ospf_neighbors": expected_neighbors,
            "observed_full_ospf_neighbors": observed_neighbors,
            "validation_passed": device_passed,
        }

        if not device_passed:
            errors.append(
                f"{device_name} has {observed_neighbors} FULL OSPF "
                f"neighbors; {expected_neighbors} were expected."
            )

    return {
        "artifact_directory": str(postcheck_dir),
        "validation_passed": not errors,
        "devices": device_results,
        "errors": errors,
    }


def validate_structured_summary(
    summary_file: Path,
    validation_name: str,
    expected_devices: List[str],
) -> Dict[str, Any]:
    summary, read_error = read_json(summary_file)
    errors = []

    if read_error:
        errors.append(read_error)
    else:
        device_count = int(summary.get("device_count", 0))
        passed_devices = sorted(summary.get("passed_devices", []))
        failed_devices = sorted(summary.get("failed_devices", []))
        validation_passed = bool(
            summary.get("validation_passed", False)
        )

        if device_count != len(expected_devices):
            errors.append(
                f"{validation_name} validated {device_count} devices; "
                f"{len(expected_devices)} were expected."
            )

        if passed_devices != expected_devices:
            errors.append(
                f"{validation_name} passed_devices does not match "
                "the expected topology devices."
            )

        if failed_devices:
            errors.append(
                f"{validation_name} reported failed devices: "
                + ", ".join(failed_devices)
            )

        if not validation_passed:
            errors.append(
                f"{validation_name} reported validation_passed=false."
            )

    return {
        "artifact": str(summary_file),
        "validation_passed": not errors,
        "device_count": summary.get("device_count", 0),
        "passed_devices": summary.get("passed_devices", []),
        "failed_devices": summary.get("failed_devices", []),
        "errors": errors,
    }


def main() -> None:
    args = parse_arguments()

    artifacts_dir = Path(args.artifacts_dir).resolve()
    topology_file = Path(args.topology_file).resolve()
    output_dir = Path(args.output_dir).resolve()

    try:
        expected_devices = load_expected_devices(topology_file)
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"FINAL VALIDATION ERROR: {error}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    stages = {
        "batfish": validate_batfish(
            artifacts_dir,
            expected_devices,
        ),
        "precheck": validate_precheck(
            artifacts_dir,
            expected_devices,
        ),
        "postcheck": validate_postcheck(
            artifacts_dir,
            expected_devices,
        ),
        "nornir": validate_structured_summary(
            artifacts_dir / "nornir" / "nornir_summary.json",
            "Nornir",
            expected_devices,
        ),
        "pyats": validate_structured_summary(
            artifacts_dir / "pyats" / "pyats_summary.json",
            "pyATS",
            expected_devices,
        ),
    }

    failed_stages = [
        stage_name
        for stage_name, stage_result in stages.items()
        if not stage_result["validation_passed"]
    ]

    final_summary = {
        "lab": "Lab 5 - OSPF Multi-Area Jenkins AWX Pipeline",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "expected_devices": expected_devices,
        "stage_count": len(stages),
        "passed_stages": sorted(
            set(stages.keys()) - set(failed_stages)
        ),
        "failed_stages": failed_stages,
        "validation_passed": not failed_stages,
        "stages": stages,
    }

    summary_file = output_dir / "lab5_validation_summary.json"
    summary_file.write_text(
        json.dumps(
            final_summary,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(final_summary, indent=2, ensure_ascii=False))

    if failed_stages:
        print(
            "LAB5 FINAL VALIDATION: FAIL - "
            + ", ".join(failed_stages),
            file=sys.stderr,
        )
        sys.exit(1)

    print("LAB5 FINAL VALIDATION: PASS")


if __name__ == "__main__":
    main()
