#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


VALID_STATUSES = {
    "SUCCESS",
    "FAILURE",
    "SKIPPED",
}


def load_yaml(path: Path) -> dict[str, Any]:
    """Carga el manifest YAML del Lab 6."""

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError(
            f"Invalid YAML structure in {path}"
        )

    return data


def load_runtime_results(
    path: Path | None,
) -> dict[str, Any]:
    """
    Carga resultados producidos por Jenkins.

    Si el archivo aún no existe, devuelve un diccionario vacío.
    """

    if path is None:
        return {}

    if not path.exists():
        return {}

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            f"Invalid JSON structure in {path}"
        )

    return data


def normalize_status(
    status: str | None,
) -> str:
    """Normaliza estados usados por Jenkins/AWX."""

    if not status:
        return "SKIPPED"

    normalized = str(status).upper()

    aliases = {
        "SUCCESSFUL": "SUCCESS",
        "FAILED": "FAILURE",
        "ERROR": "FAILURE",
        "CANCELED": "FAILURE",
        "CANCELLED": "FAILURE",
        "NEVER UPDATED": "SKIPPED",
        "NEW": "SKIPPED",
        "PENDING": "SKIPPED",
        "WAITING": "SKIPPED",
        "RUNNING": "SKIPPED",
    }

    normalized = aliases.get(
        normalized,
        normalized,
    )

    if normalized not in VALID_STATUSES:
        return "SKIPPED"

    return normalized


def build_stage_results(
    manifest: dict[str, Any],
    runtime_results: dict[str, Any],
) -> dict[str, Any]:
    """Construye el resultado consolidado de cada etapa."""

    stages = manifest.get(
        "stages",
        {},
    )

    runtime_stages = runtime_results.get(
        "stages",
        {},
    )

    output: dict[str, Any] = {}

    ordered_stages = sorted(
        stages.items(),
        key=lambda item: item[1].get(
            "order",
            999,
        ),
    )

    for stage_name, stage_definition in ordered_stages:
        runtime_stage = runtime_stages.get(
            stage_name,
            {},
        )

        status = normalize_status(
            runtime_stage.get(
                "status"
            )
        )

        stage_result: dict[str, Any] = {
            "order": stage_definition.get(
                "order"
            ),
            "source": stage_definition.get(
                "source"
            ),
            "required": bool(
                stage_definition.get(
                    "required",
                    True,
                )
            ),
            "status": status,
        }

        if runtime_stage.get(
            "awx_job_id"
        ) is not None:
            stage_result[
                "awx_job_id"
            ] = runtime_stage[
                "awx_job_id"
            ]

        if runtime_stage.get(
            "job_template"
        ):
            stage_result[
                "job_template"
            ] = runtime_stage[
                "job_template"
            ]

        if runtime_stage.get(
            "artifact"
        ):
            stage_result[
                "artifact"
            ] = runtime_stage[
                "artifact"
            ]

        if runtime_stage.get(
            "message"
        ):
            stage_result[
                "message"
            ] = runtime_stage[
                "message"
            ]

        output[
            stage_name
        ] = stage_result

    return output


def calculate_pipeline_status(
    stage_results: dict[str, Any],
) -> str:
    """
    Calcula el estado global del pipeline.

    Las etapas opcionales pueden quedar en SKIPPED durante
    una ejecución exitosa. Una etapa opcional en FAILURE
    sigue provocando FAILURE global.
    """

    statuses = [
        stage[
            "status"
        ]
        for stage in stage_results.values()
    ]

    if "FAILURE" in statuses:
        return "FAILURE"

    required_statuses = [
        stage[
            "status"
        ]
        for stage in stage_results.values()
        if stage.get(
            "required",
            True,
        )
    ]

    if required_statuses and all(
        status == "SUCCESS"
        for status in required_statuses
    ):
        return "SUCCESS"

    return "SKIPPED"


def build_summary(
    manifest: dict[str, Any],
    runtime_results: dict[str, Any],
) -> dict[str, Any]:
    """Construye el JSON final del Lab 6."""

    lab = manifest.get(
        "lab",
        {},
    )

    stage_results = build_stage_results(
        manifest,
        runtime_results,
    )

    status = calculate_pipeline_status(
        stage_results
    )

    successful_stages = [
        name
        for name, stage in stage_results.items()
        if stage[
            "status"
        ] == "SUCCESS"
    ]

    failed_stages = [
        name
        for name, stage in stage_results.items()
        if stage[
            "status"
        ] == "FAILURE"
    ]

    skipped_stages = [
        name
        for name, stage in stage_results.items()
        if stage[
            "status"
        ] == "SKIPPED"
    ]

    return {
        "lab": {
            "id": lab.get(
                "id",
                "lab6",
            ),
            "name": lab.get(
                "name"
            ),
            "protocol": lab.get(
                "protocol"
            ),
            "process": lab.get(
                "process"
            ),
            "autonomous_system": lab.get(
                "autonomous_system"
            ),
        },
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "pipeline_status": status,
        "summary": {
            "total_stages": len(
                stage_results
            ),
            "successful": len(
                successful_stages
            ),
            "failed": len(
                failed_stages
            ),
            "skipped": len(
                skipped_stages
            ),
        },
        "successful_stages": successful_stages,
        "failed_stages": failed_stages,
        "skipped_stages": skipped_stages,
        "stages": stage_results,
    }


def write_summary(
    summary: dict[str, Any],
    output_path: Path,
) -> None:
    """Guarda el resumen JSON."""

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build Lab 6 artifact summary "
            "from manifest and Jenkins/AWX results."
        )
    )

    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to artifacts/manifest.yml",
    )

    parser.add_argument(
        "--runtime-results",
        help=(
            "Optional JSON generated by Jenkins "
            "with AWX stage results."
        ),
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Destination lab6_summary.json",
    )

    args = parser.parse_args()

    manifest_path = Path(
        args.manifest
    )

    runtime_path = (
        Path(args.runtime_results)
        if args.runtime_results
        else None
    )

    output_path = Path(
        args.output
    )

    manifest = load_yaml(
        manifest_path
    )

    runtime_results = load_runtime_results(
        runtime_path
    )

    summary = build_summary(
        manifest,
        runtime_results,
    )

    write_summary(
        summary,
        output_path,
    )

    print(
        json.dumps(
            {
                "pipeline_status": summary[
                    "pipeline_status"
                ],
                "total_stages": summary[
                    "summary"
                ][
                    "total_stages"
                ],
                "successful": summary[
                    "summary"
                ][
                    "successful"
                ],
                "failed": summary[
                    "summary"
                ][
                    "failed"
                ],
                "skipped": summary[
                    "summary"
                ][
                    "skipped"
                ],
                "output": str(
                    output_path
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
