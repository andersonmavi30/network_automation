#!/usr/bin/env python3

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from pybatfish.client.session import Session
except ImportError:
    print("ERROR: pybatfish no esta instalado")
    sys.exit(1)


EXPECTED_CONFIGS = {
    "R1.cfg",
    "R2.cfg",
    "R3.cfg",
    "R4.cfg",
    "R5.cfg",
    "R6.cfg",
}


def dataframe_to_records(dataframe):
    """Convierte un DataFrame de Batfish a una lista JSON."""

    return json.loads(
        dataframe.to_json(
            orient="records"
        )
    )


def validate_config_files(configs_dir):
    """Valida que existan exactamente las 6 candidate configs."""

    config_files = sorted(
        configs_dir.glob("*.cfg")
    )

    actual_configs = {
        config_file.name
        for config_file in config_files
    }

    if actual_configs != EXPECTED_CONFIGS:
        print("ERROR: Candidate configs incorrectas")
        print(
            f"Esperadas: {sorted(EXPECTED_CONFIGS)}"
        )
        print(
            f"Encontradas: {sorted(actual_configs)}"
        )
        sys.exit(1)

    for config_file in config_files:
        if config_file.stat().st_size == 0:
            print(
                f"ERROR: {config_file.name} esta vacio"
            )
            sys.exit(1)

    return config_files


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Validacion Batfish pre-deploy "
            "para Lab 6 EIGRP"
        )
    )

    parser.add_argument(
        "--snapshot-dir",
        required=True,
    )

    parser.add_argument(
        "--output-dir",
        required=True,
    )

    args = parser.parse_args()

    snapshot_dir = Path(
        args.snapshot_dir
    )

    output_dir = Path(
        args.output_dir
    )

    configs_dir = (
        snapshot_dir / "configs"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    config_files = validate_config_files(
        configs_dir
    )

    batfish_host = os.getenv(
        "BATFISH_HOST",
        "127.0.0.1",
    )

    network = os.getenv(
        "BATFISH_NETWORK",
        "lab6",
    )

    snapshot = os.getenv(
        "BATFISH_SNAPSHOT",
        "lab6_eigrp_predeploy",
    )

    print(
        f"[INFO] Batfish host: {batfish_host}"
    )

    print(
        f"[INFO] Network: {network}"
    )

    print(
        f"[INFO] Snapshot: {snapshot}"
    )

    print(
        f"[INFO] Candidate configs: "
        f"{len(config_files)}"
    )

    bf = Session(
        host=batfish_host
    )

    bf.set_network(
        network
    )

    bf.init_snapshot(
        str(snapshot_dir),
        name=snapshot,
        overwrite=True,
    )

    parse_status = (
        bf.q
        .fileParseStatus()
        .answer()
        .frame()
    )

    init_issues = (
        bf.q
        .initIssues()
        .answer()
        .frame()
    )

    parse_status_file = (
        output_dir
        / "file_parse_status.csv"
    )

    init_issues_file = (
        output_dir
        / "init_issues.csv"
    )

    parse_status.to_csv(
        parse_status_file,
        index=False,
    )

    init_issues.to_csv(
        init_issues_file,
        index=False,
    )

    summary = {
        "batfish_host": batfish_host,
        "network": network,
        "snapshot": snapshot,
        "validation_stage": "pre_deploy",
        "expected_config_count": len(
            EXPECTED_CONFIGS
        ),
        "config_count": len(
            config_files
        ),
        "configs": [
            config.name
            for config in config_files
        ],
        "parse_status": dataframe_to_records(
            parse_status
        ),
        "init_issues_count": len(
            init_issues
        ),
    }

    summary_file = (
        output_dir
        / "batfish_summary.json"
    )

    with open(
        summary_file,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            summary,
            file,
            indent=2,
        )

    failed = False

    if "Status" not in parse_status.columns:
        print(
            "ERROR: Batfish no devolvio "
            "la columna Status"
        )
        failed = True

    else:
        bad_rows = parse_status[
            parse_status["Status"]
            != "PASSED"
        ]

        if not bad_rows.empty:
            print(
                "ERROR: Algunas candidate configs "
                "no fueron parseadas correctamente"
            )

            print(
                bad_rows.to_string(
                    index=False
                )
            )

            failed = True

    if failed:
        print(
            "\nBATFISH LAB6 VALIDATION: FAIL"
        )
        sys.exit(1)

    print(
        "\nBATFISH LAB6 VALIDATION: PASS"
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        print(
            f"\nERROR BATFISH: {error}"
        )
        sys.exit(1)
