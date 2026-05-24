#!/usr/bin/env python3

import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BASE_DIR / "scripts"

STEPS = [
    {
        "name": "Render configs",
        "script": "render_lab3.py",
    },
    {
        "name": "Precheck",
        "script": "precheck_lab3.py",
    },
    {
        "name": "Deploy",
        "script": "deploy_lab3.py",
    },
    {
        "name": "Postcheck",
        "script": "postcheck_lab3.py",
    },
    {
        "name": "Nornir collection",
        "script": "collect_lab3_nornir.py",
    },
    {
        "name": "pyATS / Genie validation",
        "script": "validate_lab3_genie.py",
    },
]


def run_step(step):
    script_path = SCRIPTS_DIR / step["script"]

    if not script_path.exists():
        print(f"[FAIL] Script not found: {script_path}")
        return False

    print("=" * 70)
    print(f"[START] {step['name']}")
    print(f"[SCRIPT] {script_path}")
    print("=" * 70)

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=BASE_DIR,
    )

    if result.returncode != 0:
        print(f"[FAIL] {step['name']} failed")
        return False

    print(f"[OK] {step['name']} completed successfully")
    return True


def main():
    print("=" * 70)
    print("[INFO] Starting Lab 3 full change pipeline")
    print("=" * 70)

    for step in STEPS:
        success = run_step(step)

        if not success:
            print("=" * 70)
            print("[RESULT] LAB 3 RESULT: FAIL")
            print("=" * 70)
            raise SystemExit(1)

    print("=" * 70)
    print("[RESULT] LAB 3 RESULT: PASS")
    print("=" * 70)


if __name__ == "__main__":
    main()
