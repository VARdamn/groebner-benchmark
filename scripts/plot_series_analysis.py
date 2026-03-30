#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

MPLCONFIGDIR = Path(os.environ.get("MPLCONFIGDIR", Path(tempfile.gettempdir()) / "groebner_matplotlib"))
MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ["MPLCONFIGDIR"] = str(MPLCONFIGDIR)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


RESOURCE_NAMES = ("CPU", "RAM", "SWAP")
COLUMN_MAP = {
    "Имя теста": "test_name",
    "Время (с)": "time_raw",
    "Размерность": "dimension",
    "crit1": "crit1",
    "crit2": "crit2",
    "Средняя память (MB)": "avg_memory_mb",
    "Максимальная память (MB)": "max_memory_mb",
    "Кол. уравнений": "equation_count",
    "Кол. переменных": "variable_count",
    "Память в секунду (MB/s)": "memory_per_sec",
    "Сумма критериев": "criteria_sum",
}
TIMEOUT_RE = re.compile(r"TIMEOUT\s*\(([\d.,]+)")
NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
CONFIG_PREFIX_RE = re.compile(r"^summary_", re.IGNORECASE)


def configure_matplotlib() -> None:
    plt.style.use("default")
    plt.rcParams.update(
        {
            "figure.figsize": (12, 6),
            "axes.grid": True,
            "grid.alpha": 0.25,
            "axes.facecolor": "#fbfdff",
            "figure.facecolor": "#ffffff",
            "axes.edgecolor": "#ccd6eb",
            "axes.titleweight": "bold",
            "axes.labelsize": 11,
            "axes.titlesize": 14,
            "legend.frameon": True,
            "legend.facecolor": "#ffffff",
            "legend.edgecolor": "#dbe2f0",
            "savefig.bbox": "tight",
        }
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Построение аналитических графиков по CSV-итогам серии экспериментов."
    )
    parser.add_argument(
        "--series-dir",
        type=Path,
        help="Каталог вида data/series_X. По умолчанию выбирается последняя серия из data/.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Каталог для результатов анализа. По умолчанию: <series-dir>/analysis.",
    )
    parser.add_argument(
        "--resources",
        nargs="+",
        choices=RESOURCE_NAMES,
        default=list(RESOURCE_NAMES),
        help="Какие серии анализировать.",
    )
    parser.add_argument(
        "--skip-resource-analysis",
        action="store_true",
        help="Не строить стандартный набор графиков по папкам CPU/RAM/SWAP.",
    )
    parser.add_argument("--cpu-base", help="Базовая CPU-конфигурация для сортировки и ускорения.")
    parser.add_argument("--ram-base", help="Базовая RAM-конфигурация для сортировки и ускорения.")
    parser.add_argument("--swap-base", help="Базовая SWAP-конфигурация для сортировки и ускорения.")
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["png", "pdf"],
        help="Форматы выходных файлов графиков.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="Разрешение растровых изображений.")
    parser.add_argument("--pairwise-csv-x", type=Path, help="CSV-файл для оси X в попарном сравнении.")
    parser.add_argument("--pairwise-csv-y", type=Path, help="CSV-файл для оси Y в попарном сравнении.")
    parser.add_argument("--pairwise-x-label", help="Подпись оси X для попарного сравнения.")
    parser.add_argument("--pairwise-y-label", help="Подпись оси Y для попарного сравнения.")
    parser.add_argument("--pairwise-title", help="Заголовок попарного сравнения.")
    parser.add_argument(
        "--pairwise-output-stem",
        default="pairwise_time_comparison",
        help="Базовое имя файлов для попарного сравнения.",
    )
    return parser.parse_args()


def discover_latest_series_dir(root: Path) -> Path:
    candidates = []
    for path in root.glob("series_*"):
        if not path.is_dir():
            continue
        match = re.search(r"(\d+)$", path.name)
        if match:
            candidates.append((int(match.group(1)), path))

    if not candidates:
        raise FileNotFoundError(f"Не найдено ни одной серии в каталоге {root}")

    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def normalize_test_name(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.strip()
    if not text:
        return ""
    text = Path(text).stem
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def parse_config_value(path: Path) -> str:
    stem = path.stem
    stem = CONFIG_PREFIX_RE.sub("", stem)
    return stem


def config_sort_key(config: str) -> tuple[float, str]:
    match = NUMBER_RE.search(config)
    number = float(match.group(0).replace(",", ".")) if match else math.inf
    return number, config


def parse_time_value(value: object) -> tuple[float | None, float | None, bool]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None, None, False

    text = str(value).strip()
    if not text:
        return None, None, False

    timeout_match = TIMEOUT_RE.search(text)
    if timeout_match:
        timeout_seconds = float(timeout_match.group(1).replace(",", "."))
        return None, timeout_seconds, True

    try:
        return float(text.replace(",", ".")), None, False
    except ValueError:
        return None, None, False


def coerce_numeric_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")


def prepare_summary_frame(frame: pd.DataFrame, resource: str, config: str, source_file: Path) -> pd.DataFrame:
    frame = frame.rename(columns={column: COLUMN_MAP.get(column, column) for column in frame.columns})
    if "test_name" not in frame.columns or "time_raw" not in frame.columns:
        raise ValueError(f"В файле {source_file} не найдены обязательные колонки 'Имя теста' и 'Время (с)'")

    frame["resource"] = resource
    frame["config"] = config
    frame["source_file"] = str(source_file)
    frame["test_name"] = frame["test_name"].astype(str).str.strip()
    frame["test_key"] = frame["test_name"].map(normalize_test_name)

    parsed_time = frame["time_raw"].map(parse_time_value)
    frame["time_seconds"] = parsed_time.map(lambda item: item[0])
    frame["timeout_seconds"] = parsed_time.map(lambda item: item[1])
    frame["timed_out"] = parsed_time.map(lambda item: item[2])
    frame["effective_time_seconds"] = frame["time_seconds"].where(
        frame["time_seconds"].notna(), frame["timeout_seconds"]
    )

    coerce_numeric_columns(
        frame,
        [
            "dimension",
            "crit1",
            "crit2",
            "avg_memory_mb",
            "max_memory_mb",
            "equation_count",
            "variable_count",
            "memory_per_sec",
            "criteria_sum",
        ],
    )
    return frame


def load_resource_data(series_dir: Path, resource: str) -> pd.DataFrame:
    resource_dir = series_dir / resource
    if not resource_dir.exists():
        raise FileNotFoundError(f"Каталог {resource_dir} не найден")

    csv_paths = sorted(resource_dir.glob("summary_*.csv"), key=lambda path: config_sort_key(parse_config_value(path)))
    if not csv_paths:
        raise FileNotFoundError(f"В каталоге {resource_dir} нет CSV-файлов summary_*.csv")

    frames = []
    for csv_path in csv_paths:
        frame = prepare_summary_frame(
            frame=pd.read_csv(csv_path),
            resource=resource,
            config=parse_config_value(csv_path),
            source_file=csv_path,
        )
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.loc[combined["test_key"] != ""].copy()

    duplicates = combined.duplicated(subset=["test_key", "config"], keep="first")
    if duplicates.any():
        combined = combined.loc[~duplicates].copy()

    combined["config"] = pd.Categorical(
        combined["config"],
        categories=sorted(combined["config"].unique(), key=config_sort_key),
        ordered=True,
    )
    return combined


def load_single_summary(csv_path: Path, dataset_label: str | None = None) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"Файл {csv_path} не найден")

    frame = prepare_summary_frame(
        frame=pd.read_csv(csv_path),
        resource="PAIRWISE",
        config=dataset_label or csv_path.stem,
        source_file=csv_path,
    )
    frame = frame.loc[frame["test_key"] != ""].copy()
    frame = frame.loc[~frame.duplicated(subset=["test_key"], keep="first")].copy()
    return frame


def parse_summary_html_metadata(summary_html_path: Path) -> dict[str, str]:
    if not summary_html_path.exists():
        return {}

    html_text = summary_html_path.read_text(encoding="utf-8")
    metadata = {}
    for key in ("CPU", "RAM", "SWAP"):
        match = re.search(rf"<th>{key}</th><td>([^<]+)</td>", html_text)
        if match:
            metadata[key] = match.group(1).strip()
    return metadata


def build_metadata_label(csv_path: Path, explicit_label: str | None) -> str:
    if explicit_label:
        return explicit_label

    metadata = parse_summary_html_metadata(csv_path.with_suffix(".html"))
    parts = []
    for key in ("RAM", "SWAP"):
        value = metadata.get(key)
        if value:
            parts.append(f"{key}={value}")
    if parts:
        return ", ".join(parts)
    cpu_value = metadata.get("CPU")
    if cpu_value:
        return f"CPU={cpu_value}"
    return csv_path.stem


def infer_output_dir(series_dir: Path | None, pairwise_csv_x: Path | None, pairwise_csv_y: Path | None, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit

    if series_dir is not None:
        return series_dir / "analysis"

    if pairwise_csv_x is not None and pairwise_csv_y is not None:
        common_root = Path(os.path.commonpath([pairwise_csv_x.resolve(), pairwise_csv_y.resolve()]))
        return common_root / "analysis"

    return Path("analysis")


def choose_base_config(frame: pd.DataFrame, explicit_value: str | None) -> str:
    configs = [str(config) for config in frame["config"].cat.categories if config is not None]
    if not configs:
        raise ValueError("Не найдено ни одной конфигурации для анализа")

    if explicit_value:
        if explicit_value not in configs:
            raise ValueError(f"Базовая конфигурация {explicit_value!r} отсутствует. Доступно: {', '.join(configs)}")
        return explicit_value

    return configs[0]


def build_time_matrix(frame: pd.DataFrame, value_column: str) -> pd.DataFrame:
    matrix = frame.pivot(index="test_key", columns="config", values=value_column)
    matrix = matrix.sort_index()
    return matrix


def build_test_label_map(frame: pd.DataFrame) -> dict[str, str]:
    labels = (
        frame.sort_values(["test_name", "config"])
        .drop_duplicates(subset=["test_key"], keep="first")
        .set_index("test_key")["test_name"]
    )
    return labels.to_dict()


def sort_tests_by_base_time(matrix: pd.DataFrame, base_config: str) -> list[str]:
    if base_config not in matrix.columns:
        raise ValueError(f"Базовая конфигурация {base_config!r} отсутствует в матрице результатов")

    sortable = matrix.loc[matrix[base_config].notna(), [base_config]].sort_values(by=base_config)
    remaining = [index for index in matrix.index if index not in sortable.index]
    return list(sortable.index) + remaining


def save_figure(fig: plt.Figure, output_dir: Path, stem: str, formats: Iterable[str], dpi: int) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    created_files = []
    for file_format in formats:
        output_path = output_dir / f"{stem}.{file_format}"
        save_kwargs = {"dpi": dpi}
        if file_format.lower() == "pdf":
            save_kwargs = {}
        fig.savefig(output_path, **save_kwargs)
        created_files.append(output_path)
    plt.close(fig)
    return created_files


def annotate_timeout_markers(
    ax: plt.Axes, frame: pd.DataFrame, ordered_tests: list[str], config_order: list[str], color_map: dict[str, str]
) -> None:
    timed_out = frame.loc[frame["timed_out"] & frame["test_key"].isin(ordered_tests)]
    if timed_out.empty:
        return

    order_map = {test_key: idx for idx, test_key in enumerate(ordered_tests)}
    for config in config_order:
        subset = timed_out.loc[timed_out["config"].astype(str) == config]
        if subset.empty:
            continue
        ax.scatter(
            subset["test_key"].map(order_map),
            subset["effective_time_seconds"],
            marker="x",
            s=35,
            linewidths=1.3,
            color=color_map[config],
            alpha=0.9,
        )


def plot_time_comparison(
    frame: pd.DataFrame,
    resource: str,
    base_config: str,
    output_dir: Path,
    formats: Iterable[str],
    dpi: int,
) -> list[Path]:
    matrix = build_time_matrix(frame, "effective_time_seconds")
    ordered_tests = sort_tests_by_base_time(matrix, base_config)
    matrix = matrix.reindex(ordered_tests)
    label_map = build_test_label_map(frame)
    config_order = [str(config) for config in matrix.columns]
    colors = plt.cm.tab10(np.linspace(0, 1, len(config_order)))
    color_map = {config: color for config, color in zip(config_order, colors)}

    fig, ax = plt.subplots(figsize=(14, 7))
    x_values = np.arange(len(matrix.index))
    for config in config_order:
        series = matrix[config]
        valid = series.notna()
        if not valid.any():
            continue
        ax.plot(
            x_values[valid.to_numpy()],
            series[valid].to_numpy(),
            marker="o",
            markersize=3.2,
            linewidth=1.6,
            label=f"{resource}={config}",
            color=color_map[config],
        )

    annotate_timeout_markers(ax, frame, ordered_tests, config_order, color_map)

    ax.set_title(f"{resource}: сравнение времени по всем задачам")
    ax.set_xlabel(f"Задачи, отсортированные по времени базовой конфигурации {resource}={base_config}")
    ax.set_ylabel("Время вычисления, с")
    ax.set_yscale("log")
    ax.legend(ncol=min(4, len(config_order)))
    ax.grid(True, which="both", alpha=0.25)

    if len(ordered_tests) <= 35:
        ax.set_xticks(x_values)
        ax.set_xticklabels([label_map.get(test_key, test_key) for test_key in ordered_tests], rotation=75, ha="right")
    else:
        ax.set_xticks([])

    return save_figure(fig, output_dir, f"{resource.lower()}_time_comparison", formats, dpi)


def plot_time_distribution(
    frame: pd.DataFrame,
    resource: str,
    output_dir: Path,
    formats: Iterable[str],
    dpi: int,
) -> list[Path]:
    config_order = [str(config) for config in frame["config"].cat.categories]
    values = []
    labels = []
    for config in config_order:
        subset = frame.loc[(frame["config"].astype(str) == config) & frame["time_seconds"].notna(), "time_seconds"]
        if subset.empty:
            continue
        labels.append(config)
        values.append(subset.to_numpy())

    if not values:
        return []

    fig, ax = plt.subplots(figsize=(12, 6))
    box = ax.boxplot(values, patch_artist=True, tick_labels=labels, showfliers=False)
    palette = plt.cm.Set2(np.linspace(0, 1, len(values)))
    for patch, color in zip(box["boxes"], palette):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)

    ax.set_title(f"{resource}: распределение времени по конфигурациям")
    ax.set_xlabel("Конфигурация")
    ax.set_ylabel("Время вычисления, с")
    ax.set_yscale("log")
    ax.text(
        0.99,
        0.99,
        "TIMEOUT исключены из boxplot",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        color="#5b6575",
    )
    return save_figure(fig, output_dir, f"{resource.lower()}_time_distribution", formats, dpi)


def compute_wins(matrix: pd.DataFrame, tolerance: float = 1e-12) -> pd.Series:
    wins = pd.Series(0.0, index=matrix.columns, dtype=float)
    comparable_rows = matrix.dropna(how="all")
    for _, row in comparable_rows.iterrows():
        valid = row.dropna()
        if valid.empty:
            continue
        best_value = valid.min()
        best_configs = valid.index[np.isclose(valid.to_numpy(dtype=float), best_value, atol=tolerance, rtol=0.0)]
        share = 1.0 / len(best_configs)
        for config in best_configs:
            wins.loc[config] += share
    return wins


def plot_best_share(
    frame: pd.DataFrame,
    resource: str,
    output_dir: Path,
    formats: Iterable[str],
    dpi: int,
) -> tuple[list[Path], pd.Series, int]:
    matrix = build_time_matrix(frame, "effective_time_seconds")
    comparable = matrix.dropna(how="all")
    wins = compute_wins(comparable)
    compared_tasks = len(comparable)
    shares = wins / compared_tasks if compared_tasks else wins

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar([str(item) for item in shares.index], shares.values, color=plt.cm.Paired(np.linspace(0, 1, len(shares))))
    ax.set_title(f"{resource}: доля задач с лучшим временем")
    ax.set_xlabel("Конфигурация")
    ax.set_ylabel("Доля побед")
    ax.set_ylim(0, max(1.0, shares.max() * 1.15 if len(shares) else 1.0))

    for bar, share_value, win_value in zip(bars, shares.values, wins.values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{share_value:.1%}\n({win_value:.1f})",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    created = save_figure(fig, output_dir, f"{resource.lower()}_best_share", formats, dpi)
    return created, wins, compared_tasks


def geometric_mean(values: pd.Series) -> float:
    filtered = values.dropna()
    filtered = filtered.loc[filtered > 0]
    if filtered.empty:
        return float("nan")
    return float(np.exp(np.log(filtered).mean()))


def plot_geometric_mean(
    frame: pd.DataFrame,
    resource: str,
    output_dir: Path,
    formats: Iterable[str],
    dpi: int,
) -> tuple[list[Path], pd.Series, int]:
    matrix = build_time_matrix(frame, "effective_time_seconds")
    common_matrix = matrix.dropna(how="any")
    geomeans = common_matrix.apply(geometric_mean, axis=0)

    if common_matrix.empty:
        return [], geomeans, 0

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(
        [str(item) for item in geomeans.index],
        geomeans.values,
        color=plt.cm.Accent(np.linspace(0, 1, len(geomeans))),
    )
    ax.set_title(f"{resource}: геометрическое среднее времени")
    ax.set_xlabel("Конфигурация")
    ax.set_ylabel("Геометрическое среднее, с")
    ax.set_yscale("log")
    ax.text(
        0.99,
        0.99,
        f"Общие задачи без пропусков: {len(common_matrix)}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        color="#5b6575",
    )
    for bar, value in zip(bars, geomeans.values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.3g}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    created = save_figure(fig, output_dir, f"{resource.lower()}_geometric_mean", formats, dpi)
    return created, geomeans, len(common_matrix)


def plot_total_time(
    frame: pd.DataFrame,
    resource: str,
    output_dir: Path,
    formats: Iterable[str],
    dpi: int,
) -> tuple[list[Path], pd.Series]:
    totals = (
        frame.groupby("config", observed=False)["effective_time_seconds"].sum(min_count=1).sort_index()
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(
        [str(item) for item in totals.index],
        totals.values,
        color=plt.cm.Dark2(np.linspace(0, 1, len(totals))),
    )
    ax.set_title(f"{resource}: суммарное время серии")
    ax.set_xlabel("Конфигурация")
    ax.set_ylabel("Суммарное время, с")
    ax.set_yscale("log")
    for bar, value in zip(bars, totals.values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.3g}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    created = save_figure(fig, output_dir, f"{resource.lower()}_total_time", formats, dpi)
    return created, totals


def plot_speedup_scatter(
    frame: pd.DataFrame,
    resource: str,
    base_config: str,
    output_dir: Path,
    formats: Iterable[str],
    dpi: int,
) -> list[Path]:
    matrix = build_time_matrix(frame, "effective_time_seconds")
    if base_config not in matrix.columns:
        return []

    compare_configs = [str(config) for config in matrix.columns if str(config) != base_config]
    if not compare_configs:
        return []

    fig, ax = plt.subplots(figsize=(12, 6))
    colors = plt.cm.tab10(np.linspace(0, 1, len(compare_configs)))

    for config, color in zip(compare_configs, colors):
        subset = matrix[[base_config, config]].dropna()
        subset = subset.loc[(subset[base_config] > 0) & (subset[config] > 0)]
        if subset.empty:
            continue
        speedup = subset[base_config] / subset[config]
        ax.scatter(
            subset[base_config],
            speedup,
            label=f"{resource}={config}",
            s=25,
            alpha=0.75,
            color=color,
            edgecolors="none",
        )

    ax.axhline(1.0, linestyle="--", linewidth=1.2, color="#6b7280")
    ax.set_title(f"{resource}: ускорение относительно базовой конфигурации {base_config}")
    ax.set_xlabel(f"Время в базовой конфигурации {resource}={base_config}, с")
    ax.set_ylabel("Ускорение = T_base / T_config")
    ax.set_xscale("log")
    ax.legend(ncol=min(4, len(compare_configs)))
    return save_figure(fig, output_dir, f"{resource.lower()}_speedup_scatter", formats, dpi)


def build_pairwise_comparison_table(x_frame: pd.DataFrame, y_frame: pd.DataFrame) -> pd.DataFrame:
    x_subset = x_frame[
        ["test_key", "test_name", "time_seconds", "timeout_seconds", "timed_out", "effective_time_seconds"]
    ].rename(
        columns={
            "test_name": "test_name_x",
            "time_seconds": "time_seconds_x",
            "timeout_seconds": "timeout_seconds_x",
            "timed_out": "timed_out_x",
            "effective_time_seconds": "effective_time_seconds_x",
        }
    )
    y_subset = y_frame[
        ["test_key", "test_name", "time_seconds", "timeout_seconds", "timed_out", "effective_time_seconds"]
    ].rename(
        columns={
            "test_name": "test_name_y",
            "time_seconds": "time_seconds_y",
            "timeout_seconds": "timeout_seconds_y",
            "timed_out": "timed_out_y",
            "effective_time_seconds": "effective_time_seconds_y",
        }
    )
    merged = x_subset.merge(y_subset, on="test_key", how="inner")
    merged["test_name"] = merged["test_name_y"].fillna(merged["test_name_x"])
    merged = merged.dropna(subset=["effective_time_seconds_x", "effective_time_seconds_y"]).copy()
    merged = merged.sort_values("test_name")
    if merged.empty:
        raise ValueError("После объединения не осталось общих задач с числовым временем или таймаутом")
    return merged


def classify_pairwise_outcome(
    merged: pd.DataFrame, tolerance: float = 1e-12
) -> tuple[pd.Series, pd.Series, pd.Series]:
    x_values = merged["effective_time_seconds_x"].to_numpy(dtype=float)
    y_values = merged["effective_time_seconds_y"].to_numpy(dtype=float)
    ties = np.isclose(x_values, y_values, atol=tolerance, rtol=0.0)
    y_faster = (~ties) & (y_values < x_values)
    x_faster = (~ties) & (x_values < y_values)
    return pd.Series(y_faster, index=merged.index), pd.Series(x_faster, index=merged.index), pd.Series(ties, index=merged.index)


def plot_pairwise_time_comparison(
    x_frame: pd.DataFrame,
    y_frame: pd.DataFrame,
    x_label: str,
    y_label: str,
    title: str,
    output_dir: Path,
    output_stem: str,
    formats: Iterable[str],
    dpi: int,
) -> tuple[list[Path], pd.DataFrame, dict[str, float]]:
    merged = build_pairwise_comparison_table(x_frame, y_frame)
    y_faster, x_faster, ties = classify_pairwise_outcome(merged)

    x_values = merged["effective_time_seconds_x"].to_numpy(dtype=float)
    y_values = merged["effective_time_seconds_y"].to_numpy(dtype=float)
    timeout_mask = merged["timed_out_x"].to_numpy(dtype=bool) | merged["timed_out_y"].to_numpy(dtype=bool)
    ratio = x_values / y_values
    merged["slowdown_ratio_x_to_y"] = ratio
    merged = merged.sort_values("slowdown_ratio_x_to_y").reset_index(drop=True)
    ratio = merged["slowdown_ratio_x_to_y"].to_numpy(dtype=float)
    timeout_mask = (merged["timed_out_x"] | merged["timed_out_y"]).to_numpy(dtype=bool)

    fig, ax = plt.subplots(figsize=(12, 7))
    x_axis = np.arange(1, len(merged) + 1)
    upper_limit = max(ratio.max() * 1.08, 1.05)
    lower_limit = 1.0 / upper_limit
    ax.axhspan(1.0, upper_limit, color="#fde68a", alpha=0.25, zorder=0)
    ax.axhline(1.0, linestyle="--", linewidth=1.5, color="#4b5563")
    ax.plot(
        x_axis,
        ratio,
        color="#b45309",
        linewidth=2.1,
        marker="o",
        markersize=3.5,
    )
    ax.scatter(
        x_axis[timeout_mask],
        ratio[timeout_mask],
        facecolors="none",
        edgecolors="#111827",
        linewidths=1.2,
        s=70,
    )
    ax.set_yscale("log")
    ax.set_ylim(lower_limit, upper_limit)
    ax.set_xlabel("Номер тестовой задачи")
    ax.set_ylabel("Отношение времен T1 / T2")
    ax.set_title(title)
    ax.set_xlim(1, len(merged))
    ax.grid(True, which="both", axis="y", alpha=0.25)
    ax.text(
        len(merged) * 0.98,
        1.0,
        "Т1 = Т2",
        ha="right",
        va="bottom",
        fontsize=9.5,
        color="#4b5563",
    )

    summary = {
        "common_tasks": float(len(merged)),
        "y_faster_count": float(y_faster.sum()),
        "x_faster_count": float(x_faster.sum()),
        "ties_count": float(ties.sum()),
        "x_total_time_seconds": float(np.sum(x_values)),
        "y_total_time_seconds": float(np.sum(y_values)),
        "x_median_time_seconds": float(np.median(x_values)),
        "y_median_time_seconds": float(np.median(y_values)),
        "timeout_points": float(timeout_mask.sum()),
        "min_slowdown_ratio_x_to_y": float(np.min(ratio)),
        "median_slowdown_ratio_x_to_y": float(np.median(ratio)),
        "max_slowdown_ratio_x_to_y": float(np.max(ratio)),
    }

    legend_handles = [
        Line2D([], [], linestyle="none", label=f"T1 = {x_label}"),
        Line2D([], [], linestyle="none", label=f"T2 = {y_label}"),
        Line2D([], [], linestyle="none", label=f"ΣT1 = {summary['x_total_time_seconds']:.1f} с"),
        Line2D([], [], linestyle="none", label=f"ΣT2 = {summary['y_total_time_seconds']:.1f} с"),
    ]
    ax.legend(
        handles=legend_handles,
        loc="upper left",
        framealpha=0.95,
        handlelength=0,
        handletextpad=0.0,
        borderpad=0.7,
        labelspacing=0.5,
    )
    legend = ax.get_legend()
    if legend is not None:
        for handle in legend.legend_handles:
            handle.set_visible(False)

    created_files = save_figure(fig, output_dir, output_stem, formats, dpi)

    merged_export = merged.copy()
    merged_export["y_faster"] = y_faster.to_numpy()
    merged_export["x_faster"] = x_faster.to_numpy()
    merged_export["tie"] = ties.to_numpy()
    merged_csv_path = output_dir / f"{output_stem}_merged.csv"
    summary_csv_path = output_dir / f"{output_stem}_summary.csv"
    merged_export.to_csv(merged_csv_path, index=False)
    pd.DataFrame([summary]).to_csv(summary_csv_path, index=False)
    created_files.extend([merged_csv_path, summary_csv_path])
    return created_files, merged_export, summary


def build_resource_summary(
    frame: pd.DataFrame,
    wins: pd.Series,
    compared_tasks: int,
    geomeans: pd.Series,
    geomean_task_count: int,
    totals: pd.Series,
) -> pd.DataFrame:
    grouped = frame.groupby("config", observed=False)
    summary = pd.DataFrame(
        {
            "config": [str(config) for config in frame["config"].cat.categories],
            "completed_tasks": grouped["time_seconds"].count().reindex(frame["config"].cat.categories, fill_value=0).to_numpy(),
            "timeout_tasks": grouped["timed_out"].sum().reindex(frame["config"].cat.categories, fill_value=0).to_numpy(),
            "total_effective_time_seconds": totals.reindex(frame["config"].cat.categories).to_numpy(),
            "geometric_mean_effective_time_seconds": geomeans.reindex(frame["config"].cat.categories).to_numpy(),
            "best_share": (wins / compared_tasks).reindex(frame["config"].cat.categories, fill_value=0.0).to_numpy()
            if compared_tasks
            else np.zeros(len(frame["config"].cat.categories)),
            "effective_tasks_for_geomean": geomean_task_count,
        }
    )
    return summary


def save_resource_tables(
    frame: pd.DataFrame,
    summary: pd.DataFrame,
    resource: str,
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    long_path = output_dir / f"{resource.lower()}_merged_results.csv"
    wide_path = output_dir / f"{resource.lower()}_effective_time_matrix.csv"
    summary_path = output_dir / f"{resource.lower()}_summary_stats.csv"

    export_frame = frame.copy()
    export_frame["config"] = export_frame["config"].astype(str)
    export_frame.to_csv(long_path, index=False)
    build_time_matrix(frame, "effective_time_seconds").to_csv(wide_path)
    summary.to_csv(summary_path, index=False)
    return [long_path, wide_path, summary_path]


def analyze_resource(
    series_dir: Path,
    resource: str,
    base_config: str | None,
    output_dir: Path,
    formats: Iterable[str],
    dpi: int,
) -> tuple[list[Path], pd.DataFrame]:
    frame = load_resource_data(series_dir, resource)
    resolved_base = choose_base_config(frame, base_config)
    resource_output_dir = output_dir / resource.lower()

    created_files = []
    created_files.extend(plot_time_comparison(frame, resource, resolved_base, resource_output_dir, formats, dpi))
    created_files.extend(plot_time_distribution(frame, resource, resource_output_dir, formats, dpi))

    best_share_files, wins, compared_tasks = plot_best_share(frame, resource, resource_output_dir, formats, dpi)
    created_files.extend(best_share_files)

    geomean_files, geomeans, geomean_task_count = plot_geometric_mean(
        frame, resource, resource_output_dir, formats, dpi
    )
    created_files.extend(geomean_files)

    total_files, totals = plot_total_time(frame, resource, resource_output_dir, formats, dpi)
    created_files.extend(total_files)
    created_files.extend(plot_speedup_scatter(frame, resource, resolved_base, resource_output_dir, formats, dpi))

    summary = build_resource_summary(frame, wins, compared_tasks, geomeans, geomean_task_count, totals)
    created_files.extend(save_resource_tables(frame, summary, resource, resource_output_dir))

    print(f"[{resource}] базовая конфигурация: {resolved_base}")
    print(summary.to_string(index=False))
    print()
    return created_files, summary


def main() -> int:
    configure_matplotlib()
    args = parse_args()

    base_map = {
        "CPU": args.cpu_base,
        "RAM": args.ram_base,
        "SWAP": args.swap_base,
    }

    created_files = []
    series_dir = None
    if not args.skip_resource_analysis:
        series_dir = args.series_dir or discover_latest_series_dir(Path("data"))

    output_dir = infer_output_dir(series_dir, args.pairwise_csv_x, args.pairwise_csv_y, args.output_dir)
    print(f"Каталог результатов: {output_dir}")

    if series_dir is not None:
        print(f"Источник данных: {series_dir}")
        print()
        for resource in args.resources:
            resource_dir = series_dir / resource
            if not resource_dir.exists():
                print(f"[{resource}] каталог отсутствует, пропускаю")
                continue
            files, _ = analyze_resource(
                series_dir=series_dir,
                resource=resource,
                base_config=base_map[resource],
                output_dir=output_dir,
                formats=args.formats,
                dpi=args.dpi,
            )
            created_files.extend(files)

    if args.pairwise_csv_x or args.pairwise_csv_y:
        if args.pairwise_csv_x is None or args.pairwise_csv_y is None:
            raise ValueError("Для попарного сравнения нужно передать оба файла: --pairwise-csv-x и --pairwise-csv-y")

        x_label = build_metadata_label(args.pairwise_csv_x, args.pairwise_x_label)
        y_label = build_metadata_label(args.pairwise_csv_y, args.pairwise_y_label)
        title = args.pairwise_title or "Сравнение конфигураций памяти по относительному времени вычисления"
        pairwise_output_dir = output_dir / "pairwise"
        x_frame = load_single_summary(args.pairwise_csv_x, dataset_label=x_label)
        y_frame = load_single_summary(args.pairwise_csv_y, dataset_label=y_label)
        pairwise_files, _, summary = plot_pairwise_time_comparison(
            x_frame=x_frame,
            y_frame=y_frame,
            x_label=x_label,
            y_label=y_label,
            title=title,
            output_dir=pairwise_output_dir,
            output_stem=args.pairwise_output_stem,
            formats=args.formats,
            dpi=args.dpi,
        )
        created_files.extend(pairwise_files)

        print("[PAIRWISE] сравнение двух конфигураций")
        print(f"Ось X: {x_label}")
        print(f"Ось Y: {y_label}")
        print(
            f"Общие задачи: {int(summary['common_tasks'])} | "
            f"медиана отношения T(X)/T(Y): {summary['median_slowdown_ratio_x_to_y']:.3f} | "
            f"диапазон: {summary['min_slowdown_ratio_x_to_y']:.3f}..{summary['max_slowdown_ratio_x_to_y']:.3f}"
        )
        print(
            f"Суммарное время X: {summary['x_total_time_seconds']:.1f} с | "
            f"Y: {summary['y_total_time_seconds']:.1f} с"
        )
        print(
            f"Медиана X: {summary['x_median_time_seconds']:.3f} с | "
            f"Y: {summary['y_median_time_seconds']:.3f} с"
        )
        print()

    if not created_files:
        raise FileNotFoundError("Не удалось построить ни одного графика: проверьте входные данные и выбранные серии.")

    print("Созданные файлы:")
    for path in created_files:
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
