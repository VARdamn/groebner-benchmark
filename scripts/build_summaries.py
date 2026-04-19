import argparse
import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import src.reporting as reporting
import src.config as config
import src.utils as utils


def _coerce_number(value):
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return value
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return None
    return numeric


def _format_cell(value):
    return utils.format_csv_value(value)


def _load_problem_features(path):
    if not path.exists():
        return {}, []

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        feature_columns = [name for name in (reader.fieldnames or []) if name != "test_name"]
        rows = {}
        for row in reader:
            test_name = row.get("test_name")
            if not test_name:
                continue
            rows[test_name] = row
    return rows, feature_columns


def _discover_run_directories(search_root):
    run_dirs = []
    for metadata_path in sorted(search_root.rglob("metadata.json")):
        run_dirs.append(metadata_path.parent)
    return run_dirs


def _load_raw_rows(search_root):
    rows = []
    for run_dir in _discover_run_directories(search_root):
        metadata = utils.load_json(run_dir / "metadata.json")
        results_dir = run_dir / reporting.TEST_RESULTS_DIRNAME
        result_paths = (
            sorted(results_dir.glob("*.json"))
            if results_dir.exists()
            else sorted(
                path for path in run_dir.glob("*.json") if path.name != "metadata.json"
            )
        )

        for result_path in result_paths:
            result = utils.load_json(result_path)
            row = {}
            for field in reporting.RUN_METADATA_FIELDS:
                if field in {"started_at", "finished_at"}:
                    continue
                row[field] = metadata.get(field)
            for field in reporting.TEST_RESULT_FIELDS:
                row[field] = result.get(field)

            if row.get("crit_sum") is None:
                crit1 = _coerce_number(row.get("crit1"))
                crit2 = _coerce_number(row.get("crit2"))
                if crit1 is not None and crit2 is not None:
                    row["crit_sum"] = utils.safe_round(crit1 + crit2)

            rows.append(row)
    return rows


def _join_features(rows, features_by_test, feature_columns):
    for row in rows:
        feature_row = features_by_test.get(row.get("test_name"), {})
        for column in feature_columns:
            if column in row:
                continue
            row[column] = feature_row.get(column)
    return rows


def _mean(values):
    if not values:
        return None
    return utils.safe_round(statistics.fmean(values))


def _median(values):
    if not values:
        return None
    return utils.safe_round(statistics.median(values))


def _std(values):
    if not values:
        return None
    if len(values) == 1:
        return 0.0
    return utils.safe_round(statistics.pstdev(values))


def _min(values):
    if not values:
        return None
    return utils.safe_round(min(values))


def _max(values):
    if not values:
        return None
    return utils.safe_round(max(values))


def _first_non_empty(rows, key):
    for row in rows:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def _build_aggregated_rows(raw_rows, features_by_test, feature_columns):
    grouped = defaultdict(list)
    for row in raw_rows:
        grouped[(row.get("config_name"), row.get("test_name"))].append(row)

    aggregated_rows = []
    for (config_name, test_name), group_rows in sorted(grouped.items()):
        duration_values = [
            value
            for value in (_coerce_number(row.get("duration_sec")) for row in group_rows)
            if value is not None
        ]
        rss_peak_values = [
            value
            for value in (_coerce_number(row.get("rss_peak_mb")) for row in group_rows)
            if value is not None
        ]
        major_fault_values = [
            value
            for value in (_coerce_number(row.get("major_page_faults")) for row in group_rows)
            if value is not None
        ]
        minor_fault_values = [
            value
            for value in (_coerce_number(row.get("minor_page_faults")) for row in group_rows)
            if value is not None
        ]
        crit_sum_values = [
            value
            for value in (_coerce_number(row.get("crit_sum")) for row in group_rows)
            if value is not None
        ]

        runs_count = len(group_rows)
        ok_runs = sum(1 for row in group_rows if row.get("status") == "ok")
        timeout_runs = sum(1 for row in group_rows if row.get("status") == "timeout")
        error_runs = sum(1 for row in group_rows if row.get("status") == "error")

        aggregated = {
            "config_name": config_name,
            "test_name": test_name,
            "category": _first_non_empty(group_rows, "category"),
            "runs_count": runs_count,
            "ok_runs": ok_runs,
            "timeout_runs": timeout_runs,
            "error_runs": error_runs,
            "completion_rate": utils.safe_round(ok_runs / runs_count) if runs_count else None,
            "duration_mean_sec": _mean(duration_values),
            "duration_median_sec": _median(duration_values),
            "duration_std_sec": _std(duration_values),
            "duration_min_sec": _min(duration_values),
            "duration_max_sec": _max(duration_values),
            "rss_peak_mean_mb": _mean(rss_peak_values),
            "rss_peak_max_mb": _max(rss_peak_values),
            "major_page_faults_mean": _mean(major_fault_values),
            "minor_page_faults_mean": _mean(minor_fault_values),
            "crit_sum_mean": _mean(crit_sum_values),
        }

        feature_row = features_by_test.get(test_name, {})
        for column in feature_columns:
            aggregated[column] = feature_row.get(column)

        aggregated_rows.append(aggregated)

    return aggregated_rows


def _write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _format_cell(row.get(field)) for field in fieldnames})


def build_summaries(search_root, raw_output, aggregated_output, features_path):
    raw_rows = _load_raw_rows(search_root)
    features_by_test, feature_columns = _load_problem_features(features_path)
    raw_rows = _join_features(raw_rows, features_by_test, feature_columns)
    aggregated_rows = _build_aggregated_rows(raw_rows, features_by_test, feature_columns)

    raw_columns = config.RAW_SUMMARY_COLUMNS + [
        column for column in feature_columns if column not in config.RAW_SUMMARY_COLUMNS
    ]
    aggregated_columns = config.AGGREGATED_COLUMNS + [
        column for column in feature_columns if column not in config.AGGREGATED_COLUMNS
    ]

    _write_csv(raw_output, raw_rows, raw_columns)
    _write_csv(aggregated_output, aggregated_rows, aggregated_columns)


def main():
    parser = argparse.ArgumentParser(description="Построение raw и aggregated сводок по run-директориям.")
    parser.add_argument(
        "--search-root",
        default="data",
        help="Корень поиска run-директорий с metadata.json.",
    )
    parser.add_argument(
        "--raw-output",
        help="Путь к выходному raw summary CSV. По умолчанию создаётся внутри --search-root.",
    )
    parser.add_argument(
        "--aggregated-output",
        help="Путь к выходному aggregated summary CSV. По умолчанию создаётся внутри --search-root.",
    )
    parser.add_argument(
        "--features-csv",
        default="data/problem_features.csv",
        help="Предвычисленные признаки задач для join по test_name.",
    )
    args = parser.parse_args()
    search_root = Path(args.search_root)
    raw_output = Path(args.raw_output) if args.raw_output else search_root / "raw_summary.csv"
    aggregated_output = (
        Path(args.aggregated_output)
        if args.aggregated_output
        else search_root / "aggregated_summary.csv"
    )

    build_summaries(
        search_root=search_root,
        raw_output=raw_output,
        aggregated_output=aggregated_output,
        features_path=Path(args.features_csv),
    )


if __name__ == "__main__":
    main()
