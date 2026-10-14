#!/usr/bin/env python3
"""Validate SparkApplication manifests (dags/**/spark-apps/*.yaml) via PyYAML.

Run from the repo root (uses the uv-managed env, which has pyyaml):

    uv run python .agents/skills/dag-edit/scripts/check_spark_app.py <manifest.yaml> [more.yaml ...]

Do NOT validate these files with system `python3` — the venv owns the
dependencies. Without arguments, validates every dags/**/spark-apps/*.yaml.

Exit code 0 if everything passes, 1 otherwise.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

API_VERSION = "sparkoperator.k8s.io/v1beta2"
KIND = "SparkApplication"
APP_FILE_PREFIX = "local:///opt/spark/scripts/"
REQUIRED_SPEC_KEYS = (
    "type",
    "mode",
    "image",
    "mainApplicationFile",
    "sparkVersion",
    "driver",
    "executor",
)


def check_manifest(path: Path) -> list[str]:
    errors: list[str] = []

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"invalid YAML: {exc}"]
    if not isinstance(data, dict):
        return ["top-level YAML is not a mapping"]

    if data.get("apiVersion") != API_VERSION:
        errors.append(f"apiVersion: expected {API_VERSION!r}, got {data.get('apiVersion')!r}")
    if data.get("kind") != KIND:
        errors.append(f"kind: expected {KIND!r}, got {data.get('kind')!r}")

    name = (data.get("metadata") or {}).get("name") or ""
    if not name:
        errors.append("metadata.name is missing")
    elif name != path.stem:
        errors.append(f"metadata.name {name!r} does not match file name {path.stem!r}")

    spec = data.get("spec") or {}
    missing = [key for key in REQUIRED_SPEC_KEYS if key not in spec]
    if missing:
        errors.append(f"spec is missing keys: {', '.join(missing)}")

    main_file = spec.get("mainApplicationFile")
    if not isinstance(main_file, str) or not main_file.startswith(APP_FILE_PREFIX):
        errors.append(f"spec.mainApplicationFile must start with {APP_FILE_PREFIX!r}, got {main_file!r}")
    else:
        rel = Path(main_file[len(APP_FILE_PREFIX):])
        if name and rel.name != name.replace("-", "_") + ".py":
            errors.append(
                f"spec.mainApplicationFile basename {rel.name!r} does not match app name "
                f"(expected {name.replace('-', '_')}.py)"
            )
        repo_rel = Path("scripts") / rel
        if not (repo_rel.exists() or repo_rel.with_suffix(".ipynb").exists()):
            errors.append(f"CI source script not found in repo: {repo_rel} (or {repo_rel.with_suffix('.ipynb')})")

    return errors


def main() -> None:
    argv = sys.argv[1:]
    paths = [Path(arg) for arg in argv] if argv else sorted(Path("dags").glob("**/spark-apps/*.yaml"))
    if not paths:
        sys.exit("usage: check_spark_app.py <manifest.yaml> [more.yaml ...]")

    failed = False
    for path in paths:
        errors = check_manifest(path)
        if errors:
            failed = True
            print(f"INVALID: {path}", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
        else:
            print(f"ok: {path}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
