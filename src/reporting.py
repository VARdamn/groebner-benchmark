from pathlib import Path

import src.utils as utils

TEST_RESULTS_DIRNAME = "results"

RUN_METADATA_FIELDS = [
    "run_id",
    "repeat_index",
    "config_name",
    "cpu_limit",
    "memory_limit_mb",
    "memswap_limit_mb",
    "swap_budget_mb",
    "timeout_sec",
    "started_at",
    "finished_at",
]

TEST_RESULT_FIELDS = [
    "test_name",
    "category",
    "status",
    "duration_sec",
    "rss_avg_mb",
    "rss_peak_mb",
    "user_cpu_time_sec",
    "system_cpu_time_sec",
    "cpu_time_total_sec",
    "minor_page_faults",
    "major_page_faults",
    "voluntary_context_switches",
    "involuntary_context_switches",
    "block_input_ops",
    "block_output_ops",
    "crit1",
    "crit2",
    "crit_sum",
    "dimension",
    "equation_count",
    "variable_count",
]


def _ordered_payload(payload, required_fields):
    ordered = {field: payload.get(field) for field in required_fields}
    for key, value in payload.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def ensure_run_directory(run_dir):
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=False)
    (run_path / TEST_RESULTS_DIRNAME).mkdir()
    return run_path


def write_run_metadata(run_dir, metadata):
    run_path = Path(run_dir)
    payload = _ordered_payload(metadata, RUN_METADATA_FIELDS)
    utils.write_json(run_path / "metadata.json", payload)


def write_test_result(run_dir, result):
    run_path = Path(run_dir)
    payload = _ordered_payload(result, TEST_RESULT_FIELDS)
    test_name = payload["test_name"]
    utils.write_json(run_path / TEST_RESULTS_DIRNAME / f"{test_name}.json", payload)
