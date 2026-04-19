import json
import math


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


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, payload):
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def format_csv_value(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
