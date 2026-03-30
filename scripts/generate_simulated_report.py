from __future__ import annotations

import csv
import math
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import src.reporting as reporting
import src.utils as utils


BASE_CSV = ROOT_DIR / "data/series_1/RAM/summary_1g.csv"
OUTPUT_DIR = ROOT_DIR / "data/simulated"
CATEGORIES = ["very_quick", "quick", "medium", "long"]


def parse_float(value):
    if value == "":
        return None
    return float(value)


def parse_int(value):
    if value == "":
        return None
    return int(value)


def load_base_rows(path):
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            rows.append(
                {
                    "test": row["Имя теста"],
                    "time": parse_float(row["Время (с)"]),
                    "timed_out": row["Время (с)"].startswith("TIMEOUT"),
                    "timeout_seconds": None,
                    "dimension": parse_int(row["Размерность"]),
                    "crit1": parse_int(row["crit1"]),
                    "crit2": parse_int(row["crit2"]),
                    "avr_memory": parse_float(row["Средняя память (MB)"]),
                    "max_memory": parse_float(row["Максимальная память (MB)"]),
                    "num_equations": parse_int(row["Кол. уравнений"]),
                    "num_vars": parse_int(row["Кол. переменных"]),
                    "mem_per_sec": parse_float(row["Память в секунду (MB/s)"]),
                }
            )
    return rows


def estimate_time_factor(base_time):
    # Deterministic slowdown heuristic relative to the RAM=1g baseline.
    factor = 1.20 + min(0.14, math.log10(max(base_time, 0.01) + 1.0) * 0.06)
    if base_time >= 30:
        factor += 0.03
    if base_time >= 180:
        factor += 0.03
    return factor


def build_simulated_rows(base_rows):
    simulated = []
    for row in base_rows:
        new_row = dict(row)
        base_time = row["time"]
        factor = estimate_time_factor(base_time)
        new_time = utils.safe_round(base_time * factor)
        new_row["time"] = new_time
        if row["max_memory"] not in (None, 0) and new_time not in (None, 0):
            new_row["mem_per_sec"] = utils.safe_round(row["max_memory"] / new_time)
        simulated.append(new_row)
    return simulated


def adjust_for_swap(rows, swap):
    if swap == "2g":
        return [dict(row) for row in rows]

    adjusted = []
    factor = 0.985
    for row in rows:
        new_row = dict(row)
        new_time = utils.safe_round((row.get("time") or 0) * factor)
        new_row["time"] = new_time
        if row["max_memory"] not in (None, 0) and new_time not in (None, 0):
            new_row["mem_per_sec"] = utils.safe_round(row["max_memory"] / new_time)
        adjusted.append(new_row)
    return adjusted


def generate_report(swap):
    base_rows = load_base_rows(BASE_CSV)
    simulated_rows = adjust_for_swap(build_simulated_rows(base_rows), swap)
    total_run_time = sum((row.get("time") or 0) for row in simulated_rows)

    created_at = time.strftime("%Y%m%d_%H%M%S")
    output_stem = f"summary_SIMULATED_cpu7_ram0.5g_swap{swap}"
    html_path = OUTPUT_DIR / f"{output_stem}.html"
    csv_path = OUTPUT_DIR / f"{output_stem}.csv"

    metadata = reporting.build_run_summary_metadata(
        created_at=created_at,
        cpu="7",
        ram="0.5g",
        swap=swap,
        total_run_time=total_run_time,
        memory_interval=1,
        timeout_seconds=7200,
        categories=CATEGORIES,
        selected_tests=[row["test"] for row in simulated_rows],
        completed=len(simulated_rows),
        skipped=0,
        failures=[],
    )
    metadata["Тип данных"] = "SIMULATED"
    metadata["Источник оценки"] = str(BASE_CSV)
    metadata["Примечание"] = (
        "Оценочный отчет, построенный от baseline RAM=1g. "
        "Это не результат реального запуска."
    )

    reporting.write_summary_reports(
        rows=simulated_rows,
        html_path=html_path,
        csv_path=csv_path,
        metadata=metadata,
    )

    print(csv_path)
    print(html_path)
    print(utils.safe_round(total_run_time))


def main():
    generate_report("2g")


if __name__ == "__main__":
    main()
