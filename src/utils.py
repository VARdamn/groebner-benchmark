import json
import math
import os


def safe_round(value, digits=4):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return round(value, digits)


def discover_test_files(json_dir):
    if not json_dir.exists():
        raise FileNotFoundError(f"JSON directory not found: {json_dir}")
    return {path.stem: path for path in sorted(json_dir.glob("*.json"))}


def normalize_test_name(name):
    clean = name.strip()
    if clean.endswith(".json"):
        clean = clean[:-5]
    return clean


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, payload):
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def load_result_rows(results_dir, selected_tests=None):
    rows = []
    selected_set = set(selected_tests) if selected_tests is not None else None
    for path in sorted(results_dir.glob("*.json")):
        if selected_set is not None and path.stem not in selected_set:
            continue
        data = load_json(path)
        required = {"test", "time", "crit1", "crit2"}
        if not required.issubset(data.keys()):
            continue
        rows.append(data)
    return rows


def format_csv_value(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def get_launch_params():
    cpu = os.getenv("CPU") or os.getenv("CPUS") or "не указано"
    ram = os.getenv("RAM") or os.getenv("MEMORY") or "не указано"
    swap = os.getenv("SWAP") or os.getenv("MEMORY_SWAP") or "не указано"
    return cpu, ram, swap
