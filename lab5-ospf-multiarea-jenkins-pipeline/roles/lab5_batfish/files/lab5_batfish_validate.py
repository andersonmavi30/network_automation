#!/usr/bin/env python3

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from pybatfish.client.session import Session
except ImportError:
    print("ERROR: pybatfish is not installed")
    sys.exit(1)


def dataframe_to_records(df):
    return json.loads(df.to_json(orient="records"))


def main():
    parser = argparse.ArgumentParser(description="Validate Lab 5 rendered configs with Batfish")
    parser.add_argument("--snapshot-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    snapshot_dir = Path(args.snapshot_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    configs_dir = snapshot_dir / "configs"
    config_files = sorted(configs_dir.glob("*.cfg"))

    if not config_files:
        print(f"ERROR: No .cfg files found in {configs_dir}")
        sys.exit(1)

    batfish_host = os.getenv("BATFISH_HOST", "127.0.0.1")
    network = os.getenv("BATFISH_NETWORK", "lab5")
    snapshot = os.getenv("BATFISH_SNAPSHOT", "lab5_ospf_multiarea")

    bf = Session(host=batfish_host)
    bf.set_network(network)
    bf.init_snapshot(str(snapshot_dir), name=snapshot, overwrite=True)

    parse_status = bf.q.fileParseStatus().answer().frame()
    init_issues = bf.q.initIssues().answer().frame()

    parse_status.to_csv(output_dir / "file_parse_status.csv", index=False)
    init_issues.to_csv(output_dir / "init_issues.csv", index=False)

    summary = {
        "batfish_host": batfish_host,
        "network": network,
        "snapshot": snapshot,
        "config_count": len(config_files),
        "configs": [cfg.name for cfg in config_files],
        "parse_status": dataframe_to_records(parse_status),
        "init_issues_count": len(init_issues),
    }

    with open(output_dir / "batfish_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    failed = False

    if "Status" in parse_status.columns:
        bad_rows = parse_status[parse_status["Status"] != "PASSED"]
        if not bad_rows.empty:
            print("ERROR: Some configs did not parse correctly")
            print(bad_rows.to_string(index=False))
            failed = True

    if failed:
        sys.exit(1)

    print("BATFISH LAB5 VALIDATION: PASS")


if __name__ == "__main__":
    main()
