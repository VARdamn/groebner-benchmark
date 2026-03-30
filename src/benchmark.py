import concurrent.futures
import multiprocessing
import time

import psutil

import src.utils as utils


def load_ginv_classes():
    from ginv.gb import GB
    from ginv.monom import Monom
    from ginv.poly import Poly

    return GB, Monom, Poly


def _build_variable_poly(Monom, Poly, index, var_count):
    poly = Poly()
    monom = Monom(0 if idx != index else 1 for idx in range(var_count))
    term = [monom, 1]

    if hasattr(poly, "append"):
        poly.append(term)
    elif hasattr(poly, "terms"):
        poly.terms.append(term)
    else:
        raise RuntimeError("Неподдерживаемый API Poly: не найдены 'append' и 'terms'.")
    return poly


def init_polynomial_context(variables):
    _, Monom, Poly = load_ginv_classes()
    Monom.init(variables)
    Monom.variables = variables.copy()
    Monom.zero = Monom(0 for _ in Monom.variables)
    Monom.cmp = Monom.TOPdeglex
    Poly.cmp = Monom.TOPdeglex

    symbols = {}
    for idx, name in enumerate(variables):
        symbols[name] = _build_variable_poly(Monom, Poly, idx, len(variables))
    return symbols


def parse_equations(raw_equations, symbols):
    parsed = []
    for raw in raw_equations:
        expression = raw.replace("^", "**")
        parsed.append(eval(expression, {"__builtins__": {}}, symbols))  # noqa: S307
    return parsed


def _build_timeout_result(test_name, payload, timeout):
    variables = payload.get("variables") or []
    equations_raw = payload.get("equations") or []
    dimension = payload.get("dimension")

    return {
        "test": test_name,
        "time": utils.safe_round(timeout),
        "timed_out": True,
        "timeout_seconds": utils.safe_round(timeout),
        "dimension": int(dimension) if dimension is not None else len(variables),
        "crit1": None,
        "crit2": None,
        "avr_memory": None,
        "max_memory": None,
        "num_equations": len(equations_raw),
        "num_vars": len(variables),
        "mem_per_sec": None,
    }


def _run_test_case_inner(test_name, payload):
    GB, _, _ = load_ginv_classes()
    variables = payload.get("variables")
    equations_raw = payload.get("equations")
    dimension = payload.get("dimension")

    symbols = init_polynomial_context(variables)
    parsed_equations = parse_equations(equations_raw, symbols)

    gb = GB()
    started = time.perf_counter()
    gb.algorithm2(parsed_equations)
    elapsed = time.perf_counter() - started

    result = {
        "test": test_name,
        "time": utils.safe_round(elapsed),
        "timed_out": False,
        "timeout_seconds": None,
        "dimension": int(dimension) if dimension is not None else len(variables),
        "crit1": int(gb.crit1),
        "crit2": int(gb.crit2),
        "avr_memory": None,
        "max_memory": None,
        "num_equations": len(equations_raw),
        "num_vars": len(variables),
        "mem_per_sec": None,
    }
    return result
def run_test_case(test_name, payload, memory_interval, verbose, timeout=None):
    if timeout is not None and timeout <= 0:
        raise ValueError("Таймаут должен быть положительным числом.")
    if memory_interval <= 0:
        raise ValueError("Интервал замера памяти должен быть положительным числом.")

    parent_process = _get_current_process()
    known_child_pids = _list_child_pids(parent_process)
    executor = concurrent.futures.ProcessPoolExecutor(
        max_workers=1,
        mp_context=multiprocessing.get_context("spawn"),
    )
    future = executor.submit(
        _run_test_case_inner,
        test_name=test_name,
        payload=payload,
    )

    wait_for_shutdown = True
    try:
        result = _collect_future_result_with_monitoring(
            executor=executor,
            future=future,
            parent_process=parent_process,
            known_child_pids=known_child_pids,
            test_name=test_name,
            payload=payload,
            memory_interval=memory_interval,
            timeout=timeout,
        )
        wait_for_shutdown = not result.get("timed_out", False)
    finally:
        _shutdown_executor(
            executor=executor,
            wait=wait_for_shutdown,
        )

    if verbose:
        if result.get("timed_out"):
            print(f"! {test_name}: таймаут после {result['timeout_seconds']}с")
        else:
            print(
                f"+ {test_name}: время={result['time']}с, "
                f"макс_память={result['max_memory']}MB, crit1={result['crit1']}, crit2={result['crit2']}"
            )
    return result


def _collect_future_result_with_monitoring(
    executor,
    future,
    parent_process,
    known_child_pids,
    test_name,
    payload,
    memory_interval,
    timeout,
):
    started = time.perf_counter()
    next_sample_at = 0.0
    mem_log = []
    monitored = None

    while True:
        now = time.perf_counter()
        elapsed = now - started

        if monitored is None:
            monitored = _resolve_worker_process(
                executor=executor,
                parent_process=parent_process,
                known_child_pids=known_child_pids,
            )

        if timeout is not None and elapsed >= timeout and not future.done():
            _terminate_worker_process(monitored)
            future.cancel()
            return _build_timeout_result(
                test_name=test_name,
                payload=payload,
                timeout=timeout,
            )

        if elapsed >= next_sample_at:
            sample = _sample_process_memory_mb(monitored)
            if sample is not None:
                mem_log.append(sample)
            next_sample_at += memory_interval

        if future.done():
            break

        sleep_for = 0.05
        if timeout is not None:
            sleep_for = min(sleep_for, max(0.01, timeout - elapsed))
        time.sleep(sleep_for)

    final_sample = _sample_process_memory_mb(monitored)
    if final_sample is not None:
        mem_log.append(final_sample)

    try:
        worker_result = future.result(timeout=1)
    except Exception as exc:
        raise RuntimeError(f"Ошибка в процессе теста: {exc}") from exc

    return _attach_memory_stats(
        result=worker_result,
        mem_log=mem_log,
    )


def _get_current_process():
    try:
        return psutil.Process()
    except psutil.Error:
        return None


def _resolve_worker_process(executor, parent_process, known_child_pids):
    process = _resolve_executor_worker_process(executor)
    if process is not None:
        return process

    if parent_process is None:
        return None

    for child in _list_child_processes(parent_process):
        if child.pid not in known_child_pids:
            return child

    return None


def _resolve_executor_worker_process(executor):
    processes = getattr(executor, "_processes", None)
    if not processes:
        return None

    for process in processes.values():
        pid = getattr(process, "pid", None)
        if pid is None:
            continue
        try:
            return psutil.Process(pid)
        except psutil.Error:
            continue

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


def _attach_memory_stats(result, mem_log):
    result = dict(result)
    max_memory = max(mem_log) if mem_log else None
    avg_memory = (sum(mem_log) / len(mem_log)) if mem_log else None
    elapsed = result.get("time")
    mem_per_sec = None
    if max_memory is not None and elapsed not in (None, 0):
        mem_per_sec = max_memory / elapsed

    result["avr_memory"] = utils.safe_round(avg_memory)
    result["max_memory"] = utils.safe_round(max_memory)
    result["mem_per_sec"] = utils.safe_round(mem_per_sec)
    return result
