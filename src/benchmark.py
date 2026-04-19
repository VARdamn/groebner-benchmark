import concurrent.futures
import gc
import multiprocessing
import resource
import time
from ginv.gb import GB
from ginv.monom import Monom
from ginv.poly import Poly
import psutil

import src.utils as utils
from src.polynomial_tools import evaluate_expressions, extract_active_variables

def _build_variable_poly(index, variables_count):
    poly = Poly()
    monom = Monom(0 if idx != index else 1 for idx in range(variables_count))
    term = [monom, 1]

    if hasattr(poly, "append"):
        poly.append(term)
    elif hasattr(poly, "terms"):
        poly.terms.append(term)
    else:
        raise RuntimeError("Неподдерживаемый API Poly: не найдены 'append' и 'terms'.")

    return poly


def init_polynomial_context(variables):
    Monom.init(variables)
    Monom.variables = variables.copy()
    Monom.zero = Monom(0 for _ in variables)
    Monom.cmp = Monom.TOPdeglex
    Poly.cmp = Monom.TOPdeglex

    return {
        name: _build_variable_poly(index, len(variables))
        for index, name in enumerate(variables)
    }


def _build_problem_info(payload, category):
    variables = extract_active_variables(payload)
    equations = payload.get("equations") or []
    dimension = payload.get("dimension")

    return {
        "variables": variables,
        "equations": equations,
        "category": category,
        "dimension": int(dimension) if dimension is not None else len(variables),
        "equation_count": len(equations),
        "variable_count": len(variables),
    }


def _build_result(test_name, info, status, duration_sec):
    return {
        "test_name": test_name,
        "category": info["category"],
        "status": status,
        "duration_sec": utils.safe_round(duration_sec) if duration_sec is not None else None,
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
        "dimension": info["dimension"],
        "equation_count": info["equation_count"],
        "variable_count": info["variable_count"],
    }


def _build_timeout_result(test_name, info, timeout):
    return _build_result(test_name, info, "timeout", timeout)


def _build_error_result(test_name, info, duration_sec, error_message, metrics=None):
    result = _build_result(test_name, info, "error", duration_sec)
    if metrics:
        result.update(metrics)
    result["error_message"] = _stringify_error(error_message)
    return result


def _stringify_error(error):
    if isinstance(error, BaseException):
        message = str(error).strip()
        return message or error.__class__.__name__
    return str(error).strip()


def _collect_rusage_delta(start_usage, end_usage):
    if start_usage is None or end_usage is None:
        return {
            "user_cpu_time_sec": None,
            "system_cpu_time_sec": None,
            "cpu_time_total_sec": None,
            "minor_page_faults": None,
            "major_page_faults": None,
            "voluntary_context_switches": None,
            "involuntary_context_switches": None,
            "block_input_ops": None,
            "block_output_ops": None,
        }

    user_cpu_time = max(0.0, end_usage.ru_utime - start_usage.ru_utime)
    system_cpu_time = max(0.0, end_usage.ru_stime - start_usage.ru_stime)

    return {
        "user_cpu_time_sec": utils.safe_round(user_cpu_time),
        "system_cpu_time_sec": utils.safe_round(system_cpu_time),
        "cpu_time_total_sec": utils.safe_round(user_cpu_time + system_cpu_time),
        "minor_page_faults": max(0, int(end_usage.ru_minflt - start_usage.ru_minflt)),
        "major_page_faults": max(0, int(end_usage.ru_majflt - start_usage.ru_majflt)),
        "voluntary_context_switches": max(0, int(end_usage.ru_nvcsw - start_usage.ru_nvcsw)),
        "involuntary_context_switches": max(0, int(end_usage.ru_nivcsw - start_usage.ru_nivcsw)),
        "block_input_ops": max(0, int(end_usage.ru_inblock - start_usage.ru_inblock)),
        "block_output_ops": max(0, int(end_usage.ru_oublock - start_usage.ru_oublock)),
    }


def _normalize_result(result, mem_log):
    result = dict(result)
    if mem_log:
        result["rss_avg_mb"] = utils.safe_round(sum(mem_log) / len(mem_log))
        result["rss_peak_mb"] = utils.safe_round(max(mem_log))

    crit1 = result.get("crit1")
    crit2 = result.get("crit2")
    if result.get("crit_sum") is None and crit1 is not None and crit2 is not None:
        result["crit_sum"] = crit1 + crit2

    return result


def _run_test_case_inner(test_name, payload, category):
    info = _build_problem_info(payload, category)

    try:
        parsed_equations = evaluate_expressions(
            info["equations"],
            init_polynomial_context(info["variables"]),
        )
    except Exception as exc:
        return _build_error_result(test_name, info, None, exc)

    gb = GB()
    start_usage = resource.getrusage(resource.RUSAGE_SELF)
    started = time.perf_counter()

    try:
        gb.algorithm2(parsed_equations)
    except Exception as exc:
        return _build_error_result(
            test_name,
            info,
            time.perf_counter() - started,
            exc,
            _collect_rusage_delta(start_usage, resource.getrusage(resource.RUSAGE_SELF)),
        )

    result = _build_result(test_name, info, "ok", time.perf_counter() - started)
    result.update(_collect_rusage_delta(start_usage, resource.getrusage(resource.RUSAGE_SELF)))
    result["crit1"] = None if getattr(gb, "crit1", None) is None else int(gb.crit1)
    result["crit2"] = None if getattr(gb, "crit2", None) is None else int(gb.crit2)
    if result["crit1"] is not None and result["crit2"] is not None:
        result["crit_sum"] = result["crit1"] + result["crit2"]
    return result


def run_test_case(test_name, payload, category, memory_interval, verbose, timeout=None):
    if timeout is not None and timeout <= 0:
        raise ValueError("Таймаут должен быть положительным числом.")
    if memory_interval <= 0:
        raise ValueError("Интервал замера памяти должен быть положительным числом.")

    info = _build_problem_info(payload, category)
    parent_process = _get_current_process()
    known_child_pids = _list_child_pids(parent_process)
    executor = concurrent.futures.ProcessPoolExecutor(
        max_workers=1,
        mp_context=multiprocessing.get_context("spawn"),
    )
    future = executor.submit(_run_test_case_inner, test_name, payload, category)

    wait_for_shutdown = True
    try:
        result = _collect_future_result(
            executor=executor,
            future=future,
            parent_process=parent_process,
            known_child_pids=known_child_pids,
            test_name=test_name,
            info=info,
            memory_interval=memory_interval,
            timeout=timeout,
        )
        wait_for_shutdown = result.get("status") != "timeout"
    finally:
        _shutdown_executor(executor, wait_for_shutdown)
        gc.collect()

    if verbose:
        _print_result(result)
    return result


def _collect_future_result(
    executor,
    future,
    parent_process,
    known_child_pids,
    test_name,
    info,
    memory_interval,
    timeout,
):
    started = time.perf_counter()
    next_sample_at = 0.0
    monitored_process = None
    mem_log = []

    while not future.done():
        elapsed = time.perf_counter() - started

        if monitored_process is None:
            monitored_process = _resolve_worker_process(executor, parent_process, known_child_pids)

        if timeout is not None and elapsed >= timeout:
            _terminate_worker_process(monitored_process)
            future.cancel()
            return _normalize_result(_build_timeout_result(test_name, info, timeout), mem_log)

        if elapsed >= next_sample_at:
            sample = _sample_process_memory_mb(monitored_process)
            if sample is not None:
                mem_log.append(sample)
            next_sample_at += memory_interval

        time.sleep(min(0.05, memory_interval))

    final_sample = _sample_process_memory_mb(monitored_process)
    if final_sample is not None:
        mem_log.append(final_sample)

    try:
        result = future.result(timeout=1)
    except Exception as exc:
        result = _build_error_result(
            test_name,
            info,
            time.perf_counter() - started,
            f"Ошибка в процессе теста: {_stringify_error(exc)}",
        )

    return _normalize_result(result, mem_log)


def _print_result(result):
    if result["status"] == "timeout":
        print(f"! {result['test_name']}: таймаут после {result['duration_sec']}с")
        return

    if result["status"] == "error":
        print(f"! {result['test_name']}: ошибка: {result.get('error_message', 'unknown error')}")
        return

    print(
        f"+ {result['test_name']}: время={result['duration_sec']}с, "
        f"rss_peak={result['rss_peak_mb']}MB, crit1={result['crit1']}, crit2={result['crit2']}"
    )


def _get_current_process():
    try:
        return psutil.Process()
    except psutil.Error:
        return None


def _list_child_pids(process):
    return {child.pid for child in _list_child_processes(process)}


def _list_child_processes(process):
    if process is None:
        return []
    try:
        return process.children(recursive=False)
    except (psutil.Error, OSError):
        return []


def _resolve_worker_process(executor, parent_process, known_child_pids):
    processes = getattr(executor, "_processes", None) or {}

    for process in processes.values():
        pid = getattr(process, "pid", None)
        if pid is None:
            continue
        try:
            return psutil.Process(pid)
        except psutil.Error:
            continue

    for child in _list_child_processes(parent_process):
        if child.pid not in known_child_pids:
            return child

    return None


def _terminate_worker_process(process):
    if process is None:
        return

    try:
        process.terminate()
        process.wait(timeout=1)
        return
    except psutil.TimeoutExpired:
        pass
    except psutil.Error:
        return

    try:
        process.kill()
        process.wait(timeout=1)
    except psutil.Error:
        return


def _shutdown_executor(executor, wait):
    try:
        executor.shutdown(wait=wait, cancel_futures=True)
    except TypeError:
        executor.shutdown(wait=wait)


def _sample_process_memory_mb(process):
    if process is None:
        return None
    try:
        return process.memory_info().rss / (1024 * 1024)
    except psutil.Error:
        return None
