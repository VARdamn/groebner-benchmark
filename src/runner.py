import gc
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

import src.benchmark as benchmark
import src.config as config
import src.reporting as reporting
import src.utils as utils

DEFAULT_JSON_DIR = Path("json")
DEFAULT_RESULTS_DIR = Path("data")
DEFAULT_CATEGORIES = ["quick", "medium", "long"]
CPU_VALUES = ("7", "10")
RAM_SERIES = (
    ("4g", "6g"),
)
SWAP_VALUES = ("1.5g", "2g", "4g")
RUN_DIR_PATTERN = re.compile(r"(?P<config_name>[A-Z][A-Za-z0-9.p]+)__run(?P<repeat>\d{2,})$")


def resolve_categories(categories):
    return categories or DEFAULT_CATEGORIES


def resolve_selected_tests(discovered, categories, all_tests, skip_tests=None):
    available_order = list(discovered.keys())
    excluded = set(skip_tests or [])

    if all_tests:
        return [name for name in available_order if name not in excluded]

    selected_names = set()
    for category in categories:
        selected_names.update(config.CATEGORY_MAP[category])

    return [name for name in available_order if name in selected_names and name not in excluded]


def _project_root():
    return Path(__file__).resolve().parent.parent


def _resolve_results_dir(results_dir=None):
    return Path(results_dir) if results_dir else DEFAULT_RESULTS_DIR


def _to_container_path(path):
    target = Path(path)
    if target.is_absolute():
        return str(target.relative_to(_project_root()))
    return str(target)


def _parse_cpu_limit(raw_value):
    numeric = float(str(raw_value).strip())
    return int(numeric) if numeric.is_integer() else numeric


def _format_cpu_value(raw_value):
    numeric = _parse_cpu_limit(raw_value)
    return str(numeric)


def _parse_memory_to_mb(raw_value):
    raw = str(raw_value).strip().lower()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([mg])", raw)
    if not match:
        raise ValueError(f"Некорректное значение памяти: {raw_value}")

    amount = float(match.group(1))
    unit = match.group(2)
    multiplier = 1024 if unit == "g" else 1
    return int(round(amount * multiplier))


def _format_gigabytes_from_mb(value_mb):
    value_gb = value_mb / 1024
    text = f"{value_gb:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _format_gigabytes_from_string(value):
    value_mb = _parse_memory_to_mb(value)
    return f"{_format_gigabytes_from_mb(value_mb)}g"


def _is_running_in_container():
    return Path("/.dockerenv").exists()


def _resolve_named_config(config_id):
    preset = config.BENCHMARK_CONFIGS[config_id]
    ram_mb = _parse_memory_to_mb(preset["ram"])
    swap_budget_mb = _parse_memory_to_mb(preset["swap_budget"])
    memswap_limit_mb = ram_mb + swap_budget_mb

    return {
        "id": config_id,
        "cpu": str(preset["cpu"]),
        "ram": _format_gigabytes_from_string(preset["ram"]),
        "swap_budget": _format_gigabytes_from_string(preset["swap_budget"]),
        "swap": f"{_format_gigabytes_from_mb(memswap_limit_mb)}g",
    }


def _run_single_container_command(
    args,
    categories,
    cpus,
    ram,
    swap,
    results_dir=None,
    config_id=None,
    check=False,
):
    project_dir = _project_root()
    env = os.environ.copy()
    env.update({
        "CPUS": cpus,
        "RAM": ram,
        "SWAP": swap,
    })
    completed = subprocess.run(
        build_single_container_command(
            args,
            categories,
            results_dir=results_dir,
            config_id=config_id,
        ),
        cwd=project_dir,
        env=env,
        check=check,
    )
    return completed.returncode


def _validate_named_config_runtime(config_id):
    resolved_config = _resolve_named_config(config_id)
    current_cpu = _parse_cpu_limit(os.getenv("CPU") or os.getenv("CPUS") or "1")
    current_ram_mb = _parse_memory_to_mb(os.getenv("RAM") or os.getenv("MEMORY") or "1g")
    current_memswap_mb = _parse_memory_to_mb(os.getenv("SWAP") or os.getenv("MEMORY_SWAP") or "1g")

    expected_cpu = _parse_cpu_limit(resolved_config["cpu"])
    expected_ram_mb = _parse_memory_to_mb(resolved_config["ram"])
    expected_memswap_mb = _parse_memory_to_mb(resolved_config["swap"])

    if (
        current_cpu != expected_cpu
        or current_ram_mb != expected_ram_mb
        or current_memswap_mb != expected_memswap_mb
    ):
        raise ValueError(
            "Фактические лимиты контейнера не совпадают с --config "
            f"{config_id}. Запускай с хоста через `python main.py --config {config_id} ...` "
            "или передай корректные CPUS/RAM/SWAP извне."
        )


def _build_run_configuration():
    cpu_raw = os.getenv("CPU") or os.getenv("CPUS") or "1"
    memory_raw = os.getenv("RAM") or os.getenv("MEMORY") or "1g"
    memswap_raw = os.getenv("SWAP") or os.getenv("MEMORY_SWAP") or memory_raw

    cpu_limit = _parse_cpu_limit(cpu_raw)
    memory_limit_mb = _parse_memory_to_mb(memory_raw)
    memswap_limit_mb = _parse_memory_to_mb(memswap_raw)
    swap_budget_mb = max(0, memswap_limit_mb - memory_limit_mb)
    config_name = (
        f"cpu{_format_cpu_value(cpu_raw)}_"
        f"ram{_format_gigabytes_from_mb(memory_limit_mb)}g_"
        f"swap{_format_gigabytes_from_mb(swap_budget_mb)}g"
    )

    return {
        "cpu_limit": cpu_limit,
        "memory_limit_mb": memory_limit_mb,
        "memswap_limit_mb": memswap_limit_mb,
        "swap_budget_mb": swap_budget_mb,
        "config_name": config_name,
    }


def _iter_existing_metadata(project_root):
    for metadata_path in project_root.rglob("metadata.json"):
        try:
            yield utils.load_json(metadata_path)
        except (OSError, ValueError):
            continue


def _next_repeat_index(project_root, config_name):
    max_repeat_index = 0

    for metadata in _iter_existing_metadata(project_root):
        if metadata.get("config_name") != config_name:
            continue

        repeat_index = metadata.get("repeat_index")
        if isinstance(repeat_index, int):
            max_repeat_index = max(max_repeat_index, repeat_index)
            continue

        run_id = str(metadata.get("run_id") or "")
        match = RUN_DIR_PATTERN.fullmatch(run_id)
        if match and match.group("config_name") == config_name:
            max_repeat_index = max(max_repeat_index, int(match.group("repeat")))

    return max_repeat_index + 1


def _build_test_categories(discovered):
    category_by_test = {}
    for category, names in config.CATEGORY_MAP.items():
        for test_name in names:
            if test_name in discovered and test_name not in category_by_test:
                category_by_test[test_name] = category
    return category_by_test


def _empty_error_result(test_name, category, error_message):
    return {
        "test_name": test_name,
        "category": category,
        "status": "error",
        "duration_sec": None,
        "rss_avg_mb": None,
        "rss_peak_mb": None,
        "user_cpu_time_sec": None,
        "system_cpu_time_sec": None,
        "cpu_time_total_sec": None,
        "minor_page_faults": None,
        "major_page_faults": None,
        "voluntary_context_switches": None,
        "involuntary_context_switches": None,
        "block_input_ops": None,
        "block_output_ops": None,
        "crit1": None,
        "crit2": None,
        "crit_sum": None,
        "dimension": None,
        "equation_count": None,
        "variable_count": None,
        "error_message": error_message,
    }


def _run_single_test(test_name, category, test_path, args):
    payload = None

    try:
        payload = utils.load_json(test_path)
        return benchmark.run_test_case(
            test_name=test_name,
            payload=payload,
            category=category,
            memory_interval=args.memory_interval,
            verbose=not args.quiet,
            timeout=args.timeout,
        )
    except Exception as exc:
        result = _empty_error_result(
            test_name=test_name,
            category=category,
            error_message=str(exc) or exc.__class__.__name__,
        )
        if not args.quiet:
            print(f"! {test_name}: ошибка: {result['error_message']}")
        return result
    finally:
        payload = None
        gc.collect()


def _run_selected_tests(args, run_dir, discovered, selected_tests, category_by_test):
    failures = []
    completed = 0
    timeout_count = 0

    for test_name in selected_tests:
        category = category_by_test.get(test_name, "")
        result = None
        try:
            result = _run_single_test(test_name, category, discovered[test_name], args)
            reporting.write_test_result(run_dir, result)
            completed += 1

            if result["status"] == "timeout":
                timeout_count += 1
            elif result["status"] == "error":
                failures.append((test_name, result.get("error_message") or "unknown error"))
                if args.fail_fast:
                    break
        finally:
            result = None
            gc.collect()

    return completed, timeout_count, failures


def _run_single_iteration(args, results_dir, discovered, selected_tests, category_by_test):
    run_started = time.perf_counter()
    started_at = datetime.now().isoformat(timespec="seconds")
    run_config = _build_run_configuration()
    config_name = args.config or run_config["config_name"]
    repeat_index = _next_repeat_index(_project_root(), config_name)
    run_id = f"{config_name}__run{repeat_index:02d}"
    run_dir = reporting.ensure_run_directory(results_dir / run_id)
    print(
        f"Run ID={run_id} | Тестов={len(selected_tests)} | "
        f"Интервал замера памяти={args.memory_interval}с | "
        f"CPU={run_config['cpu_limit']} | RAM={run_config['memory_limit_mb']}MB | "
        f"MEMSWAP={run_config['memswap_limit_mb']}MB | SWAP_BUDGET={run_config['swap_budget_mb']}MB"
    )

    try:
        completed, timeout_count, failures = _run_selected_tests(
            args=args,
            run_dir=run_dir,
            discovered=discovered,
            selected_tests=selected_tests,
            category_by_test=category_by_test,
        )
    finally:
        finished_at = datetime.now().isoformat(timespec="seconds")
        reporting.write_run_metadata(
            run_dir,
            {
                "run_id": run_id,
                "repeat_index": repeat_index,
                "config_name": config_name,
                "cpu_limit": run_config["cpu_limit"],
                "memory_limit_mb": run_config["memory_limit_mb"],
                "memswap_limit_mb": run_config["memswap_limit_mb"],
                "swap_budget_mb": run_config["swap_budget_mb"],
                "timeout_sec": args.timeout,
                "started_at": started_at,
                "finished_at": finished_at,
            },
        )

    total_run_time = time.perf_counter() - run_started
    print(
        f"Готово. run_dir={run_dir} | выполнено={completed} | "
        f"timeout={timeout_count} | ошибок={len(failures)}"
    )

    if failures:
        print("Тесты с ошибками:")
        for test_name, reason in failures:
            print(f"- {test_name}: {reason}")
        print(f"Общее время работы: {utils.safe_round(total_run_time)}с")
        return 1

    print(f"Общее время работы: {utils.safe_round(total_run_time)}с")
    return 0


def _validate_repeat(args):
    if args.repeat <= 0:
        raise ValueError("Флаг --repeat должен быть положительным целым числом.")


def _run_container_spec(args, categories, spec, check=False):
    if spec.get("label"):
        print()
        print(f"=== {spec['label']} ===")
        print(f"CPUS={spec['cpu']} RAM={spec['ram']} SWAP={spec['swap']} categories={' '.join(categories)}")
    elif spec.get("id"):
        print(
            f"Config {spec['id']} | CPU={spec['cpu']} | "
            f"RAM={spec['ram']} | SWAP_BUDGET={spec['swap_budget']}"
        )

    results_dir = spec.get("results_dir")
    before = _list_run_directories(results_dir) if results_dir else None
    exit_code = _run_single_container_command(
        args=args,
        categories=categories,
        cpus=spec["cpu"],
        ram=spec["ram"],
        swap=spec["swap"],
        results_dir=results_dir,
        config_id=spec.get("id"),
        check=check,
    )

    if before is None:
        return exit_code

    created = sorted(_list_run_directories(results_dir) - before)
    if not created:
        raise RuntimeError(f"Не удалось найти новый run directory в {results_dir}")

    for run_dir in created:
        print(f"created {run_dir}")
    return exit_code


def run_single_mode(args):
    _validate_repeat(args)
    categories = resolve_categories(args.category)

    if not _is_running_in_container():
        if not args.config:
            raise ValueError(
                "Пропущен флаг --config. "
            )
        return _run_container_spec(args, categories, _resolve_named_config(args.config))

    if args.config:
        _validate_named_config_runtime(args.config)

    results_dir = _resolve_results_dir(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    discovered = utils.discover_test_files(DEFAULT_JSON_DIR)
    selected_tests = resolve_selected_tests(
        discovered=discovered,
        categories=categories,
        all_tests=args.all_tests,
        skip_tests=args.skip_tests,
    )

    if not selected_tests:
        print("Не выбраны тесты. Проверьте аргументы --category/--all-tests.")
        return 1
    category_by_test = _build_test_categories(discovered)

    exit_code = 0
    for iteration in range(1, args.repeat + 1):
        if args.repeat > 1:
            print()
            print(f"=== Повтор {iteration}/{args.repeat} ===")

        current_exit_code = _run_single_iteration(
            args=args,
            results_dir=results_dir,
            discovered=discovered,
            selected_tests=selected_tests,
            category_by_test=category_by_test,
        )
        if current_exit_code != 0:
            exit_code = current_exit_code
            if args.fail_fast:
                break

    return exit_code


def find_next_series_dir(data_dir):
    max_index = 0
    if data_dir.exists():
        for path in data_dir.iterdir():
            if not path.is_dir():
                continue
            match = re.fullmatch(r"series_(\d+)", path.name)
            if match:
                max_index = max(max_index, int(match.group(1)))
    return data_dir / f"series_{max_index + 1}"


def _list_run_directories(target_dir):
    if not target_dir.exists():
        return set()

    return {
        path
        for path in target_dir.iterdir()
        if path.is_dir() and RUN_DIR_PATTERN.fullmatch(path.name)
    }


def build_single_container_command(args, categories, results_dir=None, config_id=None):
    command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "groebner-bench",
        "--mode",
        "single",
        "--memory-interval",
        str(args.memory_interval),
    ]

    if args.timeout is not None:
        command.extend(["--timeout", str(args.timeout)])
    if args.repeat != 1:
        command.extend(["--repeat", str(args.repeat)])
    effective_config_id = config_id or args.config
    if effective_config_id:
        command.extend(["--config", effective_config_id])
    resolved_results_dir = _resolve_results_dir(results_dir or args.results_dir)
    if resolved_results_dir != DEFAULT_RESULTS_DIR:
        command.extend(["--results-dir", _to_container_path(resolved_results_dir)])
    if args.fail_fast:
        command.append("--fail-fast")
    if args.quiet:
        command.append("--quiet")

    if args.all_tests:
        command.append("--all-tests")
    else:
        command.extend(["--category", *categories])
    if args.skip_tests:
        command.extend(["--skip-tests", *args.skip_tests])

    return command


def _build_series_runs(args, series_dir):
    runs = []

    if not args.skip_cpu:
        for cpus in CPU_VALUES:
            runs.append({
                "label": f"CPU series: CPUS={cpus}",
                "cpu": cpus,
                "ram": "5g",
                "swap": "7g",
                "results_dir": series_dir / "CPU",
            })

    if not args.skip_ram:
        for ram, swap in RAM_SERIES:
            runs.append({
                "label": f"RAM series: RAM={ram} SWAP={swap}",
                "cpu": "7",
                "ram": ram,
                "swap": swap,
                "results_dir": series_dir / "RAM",
            })

    if not args.skip_swap:
        for swap in SWAP_VALUES:
            runs.append({
                "label": f"SWAP series: SWAP={swap}",
                "cpu": "7",
                "ram": "0.5g",
                "swap": swap,
                "results_dir": series_dir / "SWAP",
            })

    return runs


def run_series_mode(args):
    _validate_repeat(args)
    categories = resolve_categories(args.category)
    project_dir = _project_root()
    data_dir = _resolve_results_dir(args.results_dir)
    series_dir = find_next_series_dir(data_dir)
    target_dirs = {name: series_dir / name for name in ("CPU", "RAM", "SWAP")}
    for target_dir in target_dirs.values():
        target_dir.mkdir(parents=True, exist_ok=True)
    print(f"Project dir: {project_dir}")
    print(f"Series dir: {series_dir}")
    print(f"Categories: {' '.join(categories)}")

    for spec in _build_series_runs(args, series_dir):
        _run_container_spec(args, categories, spec, check=True)

    print()
    print("Все серии завершены.")
    for series_name, target_dir in target_dirs.items():
        print(f"{series_name} runs: {target_dir}")
    return 0
