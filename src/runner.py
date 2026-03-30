import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import src.benchmark as benchmark
import src.config as equations
import src.reporting as reporting
import src.utils as utils

DEFAULT_JSON_DIR = Path("json")
DEFAULT_RESULTS_DIR = Path("results")
DEFAULT_SINGLE_CATEGORIES = ["very_quick", "quick"]
DEFAULT_SERIES_CATEGORIES = ["quick", "medium"]
CPU_VALUES = ("7", "10")
RAM_SERIES = (
    ("4g", "6g"),
)
SWAP_VALUES = ("1.5g", "2g", "4g")
SERIES_DIR_PATTERN = re.compile(r"series_(\d+)$")
SUMMARY_GLOB = "summary_*"


def resolve_categories(mode, categories):
    if categories:
        return categories
    if mode == "series":
        return DEFAULT_SERIES_CATEGORIES
    return DEFAULT_SINGLE_CATEGORIES


def resolve_selected_tests(discovered, categories, all_tests):
    available_order = list(discovered.keys())

    if all_tests:
        return available_order

    selected_names = set()
    for category in categories:
        selected_names.update(equations.CATEGORY_MAP[category])

    return [name for name in available_order if name in selected_names]


def run_single_mode(args):
    run_started = time.perf_counter()
    created_at = time.strftime("%Y%m%d_%H%M%S")
    summary_html_name, summary_csv_name = reporting.build_summary_paths(created_at)
    summary_html_path = Path(summary_html_name)
    summary_csv_path = Path(summary_csv_name)
    cpu, ram, swap = utils.get_launch_params()
    categories = resolve_categories("single", args.category)

    DEFAULT_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    discovered = utils.discover_test_files(DEFAULT_JSON_DIR)
    selected_tests = resolve_selected_tests(
        discovered=discovered,
        categories=categories,
        all_tests=args.all_tests,
    )

    if not selected_tests:
        print("Не выбраны тесты. Проверьте аргументы --category/--all-tests.")
        total_run_time = time.perf_counter() - run_started
        print(f"Общее время работы: {utils.safe_round(total_run_time)}с")
        return 1

    existing = {path.stem for path in DEFAULT_RESULTS_DIR.glob("*.json")}
    failures = []
    completed = 0
    skipped = 0

    print(
        f"Выбрано тестов: {len(selected_tests)} | "
        f"Пропуск готовых тестов={not args.force} | Интервал замера памяти={args.memory_interval}с | "
        f"CPU={cpu} | RAM={ram} | SWAP={swap}"
    )

    for test_name in selected_tests:
        if not args.force and test_name in existing:
            skipped += 1
            continue

        result_path = DEFAULT_RESULTS_DIR / f"{test_name}.json"
        if result_path.exists():
            result_path.unlink()

        try:
            payload = utils.load_json(discovered[test_name])
            result = benchmark.run_test_case(
                test_name=test_name,
                payload=payload,
                memory_interval=args.memory_interval,
                verbose=not args.quiet,
                timeout=args.timeout,
            )
            utils.write_json(result_path, result)
            completed += 1
        except Exception as exc:
            failures.append((test_name, str(exc)))
            print(f"! Ошибка в {test_name}: {exc}")
            if args.fail_fast:
                break

    rows = utils.load_result_rows(DEFAULT_RESULTS_DIR, selected_tests=selected_tests)
    total_run_time = time.perf_counter() - run_started
    summary_total_run_time = sum((row.get("time") or 0) for row in rows)
    if not rows:
        summary_total_run_time = total_run_time
    summary_metadata = reporting.build_run_summary_metadata(
        created_at=created_at,
        cpu=cpu,
        ram=ram,
        swap=swap,
        total_run_time=summary_total_run_time,
        memory_interval=args.memory_interval,
        timeout_seconds=args.timeout,
        categories=categories,
        selected_tests=selected_tests,
        completed=completed,
        skipped=skipped,
        failures=failures,
    )
    reporting.write_summary_reports(rows, summary_html_path, summary_csv_path, summary_metadata)

    print(
        f"Готово. выполнено={completed}, пропущено={skipped}, "
        f"ошибок={len(failures)}, строк_в_summary={len(rows)}"
    )
    if failures:
        print("Тесты с ошибками:")
        for test_name, reason in failures:
            print(f"- {test_name}: {reason}")
        print(f"Общее время работы: {utils.safe_round(total_run_time)}с")
        return 1

    print(f"Общее время работы: {utils.safe_round(total_run_time)}с")
    return 0


def find_next_series_dir(data_dir):
    max_index = 0
    if data_dir.exists():
        for path in data_dir.iterdir():
            if not path.is_dir():
                continue
            match = SERIES_DIR_PATTERN.fullmatch(path.name)
            if match:
                max_index = max(max_index, int(match.group(1)))
    return data_dir / f"series_{max_index + 1}"


def list_summary_files(project_dir):
    return {
        path
        for path in project_dir.glob(SUMMARY_GLOB)
        if path.is_file() and path.suffix in {".html", ".csv"}
    }


def collect_new_summary_files(project_dir, before):
    new_files = sorted(list_summary_files(project_dir) - before)
    if not new_files:
        raise RuntimeError("Не удалось найти новые summary_*.html/csv после запуска.")
    return new_files


def build_single_container_command(args, categories):
    command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "groebner-bench",
        "--mode",
        "single",
        "--force",
        "--memory-interval",
        str(args.memory_interval),
    ]

    if args.timeout is not None:
        command.extend(["--timeout", str(args.timeout)])

    if args.fail_fast:
        command.append("--fail-fast")
    if args.quiet:
        command.append("--quiet")

    if args.all_tests:
        command.append("--all-tests")
    else:
        command.extend(["--category", *categories])

    return command


def run_series_item(args, project_dir, target_dir, cpus, ram, swap, label, summary_value, categories):
    print()
    print(f"=== {label} ===")
    print(f"CPUS={cpus} RAM={ram} SWAP={swap} categories={' '.join(categories)}")

    before = list_summary_files(project_dir)
    env = os.environ.copy()
    env.update({"CPUS": cpus, "RAM": ram, "SWAP": swap})

    subprocess.run(
        build_single_container_command(args, categories),
        cwd=project_dir,
        env=env,
        check=True,
    )

    target_dir.mkdir(parents=True, exist_ok=True)
    for source in collect_new_summary_files(project_dir, before):
        destination = target_dir / f"summary_{summary_value}{source.suffix}"
        if destination.exists():
            raise RuntimeError(f"Файл уже существует: {destination}")
        shutil.move(str(source), str(destination))
        print(f"moved {source.name} -> {destination}")


def run_series_mode(args):
    project_dir = Path(__file__).resolve().parent.parent
    categories = resolve_categories("series", args.category)
    data_dir = project_dir / "data"
    series_dir = find_next_series_dir(data_dir)
    cpu_dir = series_dir / "CPU"
    ram_dir = series_dir / "RAM"
    swap_dir = series_dir / "SWAP"
    cpu_dir.mkdir(parents=True, exist_ok=True)
    ram_dir.mkdir(parents=True, exist_ok=True)
    swap_dir.mkdir(parents=True, exist_ok=True)

    print(f"Project dir: {project_dir}")
    print(f"Series dir: {series_dir}")
    print(f"Categories: {' '.join(categories)}")

    if not args.skip_cpu:
        for cpus in CPU_VALUES:
            run_series_item(
                args=args,
                project_dir=project_dir,
                target_dir=cpu_dir,
                cpus=cpus,
                ram="5g",
                swap="7g",
                label=f"CPU series: CPUS={cpus}",
                summary_value=cpus,
                categories=categories,
            )

    if not args.skip_ram:
        for ram, swap in RAM_SERIES:
            run_series_item(
                args=args,
                project_dir=project_dir,
                target_dir=ram_dir,
                cpus="7",
                ram=ram,
                swap=swap,
                label=f"RAM series: RAM={ram} SWAP={swap}",
                summary_value=ram,
                categories=categories,
            )

    if not args.skip_swap:
        for swap in SWAP_VALUES:
            run_series_item(
                args=args,
                project_dir=project_dir,
                target_dir=swap_dir,
                cpus="7",
                ram="0.5g",
                swap=swap,
                label=f"SWAP series: SWAP={swap}",
                summary_value=swap,
                categories=categories,
            )

    print()
    print("Все серии завершены.")
    print(f"CPU summaries: {cpu_dir}")
    print(f"RAM summaries: {ram_dir}")
    print(f"SWAP summaries: {swap_dir}")
    return 0
