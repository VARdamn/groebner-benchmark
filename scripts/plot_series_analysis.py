from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

MPLCONFIGDIR = Path(
    os.environ.get("MPLCONFIGDIR", Path(tempfile.gettempdir()) / "groebner_matplotlib")
)
MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ["MPLCONFIGDIR"] = str(MPLCONFIGDIR)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


CONFIG_ALIASES = {"cpu7_ram4g_swap0g": "B00"}
SERIES_CONFIGS = {
    "CPU": ["C0.1", "C0.25", "C0.5", "C0.75", "C01", "C04", "B00"],
    "RAM": ["R0.5", "R01", "B00"],
    "SWAP": ["R0.5", "S02", "S04"],
}
CATEGORY_ORDER = ["quick", "medium", "long"]
STATUS_ORDER = ["ok", "timeout", "error"]
STATUS_COLORS = {
    "ok": "#5b8c5a",
    "timeout": "#d49a3a",
    "error": "#b85757",
}
CPU_LIMITS = {
    "C0.1": 0.1,
    "C0.25": 0.25,
    "C0.5": 0.5,
    "C0.75": 0.75,
    "C01": 1.0,
    "C04": 4.0,
    "B00": 7.0,
}
SWAP_GB = {"R0.5": 0.0, "S02": 2.0, "S04": 4.0}
BOX_COLORS = ["#8fbcd4", "#f1b26b", "#c7a9d9", "#93c47d", "#d97c7c", "#7fb3a7", "#b7a07a"]
SCATTER_COLORS = {
    "R0.5": "#d49a3a",
    "R01": "#5c8bd6",
    "S02": "#7f8c8d",
    "S04": "#b85757",
}
FEATURE_COLUMNS = [
    "equation_count",
    "variable_count",
    "dimension",
    "max_total_degree",
    "mean_total_degree",
    "max_terms_per_equation",
    "mean_terms_per_equation",
    "total_terms",
]
BASELINE_METRIC_COLUMNS = [
    "duration_mean_sec",
    "duration_median_sec",
    "rss_peak_mean_mb",
    "rss_peak_max_mb",
    "major_page_faults_mean",
    "minor_page_faults_mean",
]


def configure_matplotlib() -> None:
    plt.style.use("default")
    plt.rcParams.update(
        {
            "figure.facecolor": "#ffffff",
            "axes.facecolor": "#ffffff",
            "axes.edgecolor": "#d6d6d6",
            "axes.grid": True,
            "grid.alpha": 0.25,
            "grid.linestyle": "--",
            "axes.titleweight": "bold",
            "savefig.bbox": "tight",
            "legend.frameon": True,
        }
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Построение графиков из PLOTS.md по данным data/raw_summary.csv и data/aggregated_summary.csv."
    )
    parser.add_argument("--raw-csv", type=Path, default=Path("data/raw_summary.csv"))
    parser.add_argument("--aggregated-csv", type=Path, default=Path("data/aggregated_summary.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/analysis"))
    parser.add_argument("--formats", nargs="+", default=["png"])
    parser.add_argument("--dpi", type=int, default=300)
    return parser.parse_args()


def _normalize_config(value: object) -> str:
    text = "" if value is None else str(value).strip()
    return CONFIG_ALIASES.get(text, text)


def _normalize_category(value: object) -> str:
    return "" if value is None else str(value).strip().lower()


def _coerce_numeric(frame: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")


def load_frames(raw_csv: Path, aggregated_csv: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(raw_csv)
    aggregated = pd.read_csv(aggregated_csv)

    raw["config_name"] = raw["config_name"].map(_normalize_config)
    aggregated["config_name"] = aggregated["config_name"].map(_normalize_config)
    raw["category"] = raw["category"].map(_normalize_category)
    aggregated["category"] = aggregated["category"].map(_normalize_category)
    raw["status"] = raw["status"].astype(str).str.strip().str.lower()
    raw["test_name"] = raw["test_name"].astype(str).str.strip()
    aggregated["test_name"] = aggregated["test_name"].astype(str).str.strip()
    _coerce_numeric(
        raw,
        [
            "repeat_index",
            "duration_sec",
            "rss_peak_mb",
            "cpu_time_total_sec",
            "crit_sum",
        ],
    )
    _coerce_numeric(
        aggregated,
        [
            "runs_count",
            "ok_runs",
            "timeout_runs",
            "error_runs",
            "completion_rate",
            "duration_mean_sec",
            "duration_median_sec",
            "rss_peak_mean_mb",
            "rss_peak_max_mb",
            "major_page_faults_mean",
            "minor_page_faults_mean",
            "crit_sum_mean",
        ]
        + FEATURE_COLUMNS,
    )
    aggregated["full_ok"] = aggregated["runs_count"].gt(0) & aggregated["ok_runs"].eq(aggregated["runs_count"])
    return raw, aggregated


def save_figure(fig: plt.Figure, output_dir: Path, stem: str, formats: list[str], dpi: int) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    created = []
    for file_format in formats:
        path = output_dir / f"{stem}.{file_format}"
        kwargs = {} if file_format.lower() == "pdf" else {"dpi": dpi}
        fig.savefig(path, **kwargs)
        created.append(path)
    plt.close(fig)
    return created


def full_ok_tests(aggregated: pd.DataFrame, configs: list[str]) -> list[str]:
    subset = aggregated.loc[aggregated["config_name"].isin(configs), ["test_name", "config_name", "full_ok"]].copy()
    pivot = subset.pivot(index="test_name", columns="config_name", values="full_ok")
    pivot = pivot.reindex(columns=configs)
    valid = pivot.notna().all(axis=1) & pivot.fillna(False).all(axis=1)
    return pivot.index[valid].tolist()


def matched_slowdown_rows(
    raw: pd.DataFrame,
    aggregated: pd.DataFrame,
    base_config: str,
    compare_configs: list[str],
) -> pd.DataFrame:
    frames = []
    for config in compare_configs:
        tests = full_ok_tests(aggregated, [base_config, config])
        if not tests:
            continue

        base_rows = raw.loc[
            (raw["config_name"] == base_config)
            & (raw["status"] == "ok")
            & (raw["test_name"].isin(tests)),
            ["test_name", "repeat_index", "duration_sec"],
        ].rename(columns={"duration_sec": "duration_base"})
        cmp_rows = raw.loc[
            (raw["config_name"] == config)
            & (raw["status"] == "ok")
            & (raw["test_name"].isin(tests)),
            ["test_name", "repeat_index", "duration_sec", "category"],
        ].rename(columns={"duration_sec": "duration_cmp"})
        merged = cmp_rows.merge(base_rows, on=["test_name", "repeat_index"], how="inner")
        merged = merged.loc[(merged["duration_base"] > 0) & (merged["duration_cmp"] > 0)].copy()
        if merged.empty:
            continue
        merged["config"] = config
        merged["slowdown"] = merged["duration_cmp"] / merged["duration_base"]
        frames.append(merged)

    if not frames:
        return pd.DataFrame(columns=["test_name", "repeat_index", "category", "config", "slowdown"])
    return pd.concat(frames, ignore_index=True)


def ok_runtime_rows(raw: pd.DataFrame, aggregated: pd.DataFrame, configs: list[str]) -> pd.DataFrame:
    tests = full_ok_tests(aggregated, configs)
    return raw.loc[
        raw["config_name"].isin(configs) & raw["test_name"].isin(tests) & raw["status"].eq("ok")
    ].copy()


def boxplot_data(frame: pd.DataFrame, value_column: str, config_order: list[str]) -> tuple[list[str], list[np.ndarray]]:
    labels = []
    values = []
    for config in config_order:
        series = frame.loc[frame["config_name"].eq(config), value_column].dropna()
        if series.empty:
            continue
        labels.append(config)
        values.append(series.to_numpy(dtype=float))
    return labels, values


def plot_boxplot(
    frame: pd.DataFrame,
    value_column: str,
    config_order: list[str],
    title: str,
    ylabel: str,
    stem: str,
    output_dir: Path,
    formats: list[str],
    dpi: int,
    log_scale: bool = False,
) -> list[Path]:
    labels, values = boxplot_data(frame, value_column, config_order)
    if not values:
        return []

    fig, ax = plt.subplots(figsize=(10, 6))
    box = ax.boxplot(values, patch_artist=True, tick_labels=labels, showfliers=False)
    for patch, color in zip(box["boxes"], BOX_COLORS):
        patch.set_facecolor(color)
        patch.set_alpha(0.8)
    ax.set_title(title)
    ax.set_xlabel("Конфигурация")
    ax.set_ylabel(ylabel)
    if log_scale:
        ax.set_yscale("log")
    return save_figure(fig, output_dir, stem, formats, dpi)


def completion_share_table(
    aggregated: pd.DataFrame,
    configs: list[str],
    category: str | None = None,
) -> pd.DataFrame:
    subset = aggregated.loc[aggregated["config_name"].isin(configs)].copy()
    if category is not None:
        subset = subset.loc[subset["category"].eq(category)].copy()
    grouped = (
        subset.groupby("config_name", observed=False)[["runs_count", "ok_runs", "timeout_runs", "error_runs"]]
        .sum()
        .reindex(configs)
        .fillna(0.0)
    )
    shares = grouped[["ok_runs", "timeout_runs", "error_runs"]].div(
        grouped["runs_count"].replace(0, np.nan), axis=0
    )
    shares.columns = STATUS_ORDER
    return shares.fillna(0.0)


def plot_stacked_completion(
    aggregated: pd.DataFrame,
    configs: list[str],
    title: str,
    stem: str,
    output_dir: Path,
    formats: list[str],
    dpi: int,
    category: str | None = None,
) -> list[Path]:
    shares = completion_share_table(aggregated, configs, category=category)
    if shares.empty:
        return []

    fig, ax = plt.subplots(figsize=(10, 6))
    bottom = np.zeros(len(shares))
    for status in STATUS_ORDER:
        values = shares[status].to_numpy(dtype=float)
        ax.bar(
            shares.index.astype(str),
            values,
            bottom=bottom,
            color=STATUS_COLORS[status],
            label=status,
        )
        bottom += values
    ax.set_title(title)
    ax.set_xlabel("Конфигурация")
    ax.set_ylabel("Доля запусков")
    ax.set_ylim(0, 1.0)
    ax.legend()
    return save_figure(fig, output_dir, stem, formats, dpi)


def plot_cpu_median_slowdown_line(
    slowdown: pd.DataFrame,
    output_dir: Path,
    formats: list[str],
    dpi: int,
) -> list[Path]:
    if slowdown.empty:
        return []

    medians = slowdown.groupby("config", observed=False)["slowdown"].median()
    x_labels = ["C0.1", "C0.25", "C0.5", "C0.75", "C01", "C04", "B00"]
    x_values = [CPU_LIMITS[label] for label in x_labels]
    y_values = [medians.get(label, np.nan) for label in x_labels[:-1]] + [1.0]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(x_values, y_values, marker="o", linewidth=2.0, color="#3f6ea8")
    ax.set_title("CPU: лимит CPU vs медианный коэффициент замедления")
    ax.set_xlabel("CPU limit")
    ax.set_ylabel("Медианный коэффициент замедления относительно B00")
    ax.set_xticks(x_values, [str(value).rstrip("0").rstrip(".") for value in x_values])
    return save_figure(fig, output_dir, "cpu_median_slowdown_line", formats, dpi)


def plot_swap_success_rate_line(
    aggregated: pd.DataFrame,
    output_dir: Path,
    formats: list[str],
    dpi: int,
) -> list[Path]:
    shares = completion_share_table(aggregated, SERIES_CONFIGS["SWAP"])
    if shares.empty:
        return []

    x_labels = SERIES_CONFIGS["SWAP"]
    x_values = [SWAP_GB[label] for label in x_labels]
    y_values = [shares.loc[label, "ok"] if label in shares.index else np.nan for label in x_labels]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(x_values, y_values, marker="o", linewidth=2.0, color="#8b4b5a")
    ax.set_title("SWAP: объём swap vs success rate")
    ax.set_xlabel("Swap, GB")
    ax.set_ylabel("Доля успешных запусков")
    ax.set_xticks(x_values, [str(int(value)) if value.is_integer() else str(value) for value in x_values])
    ax.set_ylim(0, 1.0)
    return save_figure(fig, output_dir, "swap_success_rate_line", formats, dpi)


def plot_ram_failure_scatter(
    aggregated: pd.DataFrame,
    output_dir: Path,
    formats: list[str],
    dpi: int,
) -> list[Path]:
    baseline = aggregated.loc[
        aggregated["config_name"].eq("B00") & aggregated["rss_peak_max_mb"].notna(),
        ["test_name", "rss_peak_max_mb"],
    ].copy()
    if baseline.empty:
        return []

    frames = []
    offsets = {"R0.5": -0.03, "R01": 0.03}
    for config in ["R0.5", "R01"]:
        subset = aggregated.loc[
            aggregated["config_name"].eq(config), ["test_name", "full_ok"]
        ].rename(columns={"full_ok": "outcome"})
        merged = baseline.merge(subset, on="test_name", how="inner")
        if merged.empty:
            continue
        merged["config"] = config
        merged["y"] = merged["outcome"].astype(float) + offsets[config]
        frames.append(merged)

    if not frames:
        return []

    scatter = pd.concat(frames, ignore_index=True)
    fig, ax = plt.subplots(figsize=(10, 6))
    for config in ["R0.5", "R01"]:
        subset = scatter.loc[scatter["config"].eq(config)]
        if subset.empty:
            continue
        ax.scatter(
            subset["rss_peak_max_mb"],
            subset["y"],
            s=36,
            alpha=0.75,
            color=SCATTER_COLORS[config],
            label=config,
        )
    ax.set_title("RAM: baseline peak RSS vs исход под лимитами RAM")
    ax.set_xlabel("Peak RSS в B00, MB")
    ax.set_ylabel("Исход")
    ax.set_yticks([0, 1], ["fail", "ok"])
    ax.legend(title="Конфигурация")
    return save_figure(fig, output_dir, "ram_baseline_rss_vs_outcome_scatter", formats, dpi)


def plot_cpu_category_slowdown(
    slowdown: pd.DataFrame,
    output_dir: Path,
    formats: list[str],
    dpi: int,
) -> list[Path]:
    if slowdown.empty:
        return []

    compare_configs = ["C0.1", "C0.25", "C0.5", "C0.75", "C01", "C04"]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=True)
    plotted = False
    for ax, category in zip(axes, CATEGORY_ORDER):
        subset = slowdown.loc[slowdown["category"].eq(category)]
        labels = []
        values = []
        for config in compare_configs:
            series = subset.loc[subset["config"].eq(config), "slowdown"].dropna()
            if series.empty:
                continue
            labels.append(config)
            values.append(series.to_numpy(dtype=float))
        if values:
            plotted = True
            box = ax.boxplot(values, patch_artist=True, tick_labels=labels, showfliers=False)
            for patch, color in zip(box["boxes"], BOX_COLORS):
                patch.set_facecolor(color)
                patch.set_alpha(0.8)
        ax.set_title(category.upper())
        ax.set_xlabel("CPU-конфигурация")
        ax.grid(True, axis="y", alpha=0.25)
    if not plotted:
        plt.close(fig)
        return []
    axes[0].set_ylabel("Коэффициент замедления относительно B00")
    fig.suptitle("CPU: коэффициент замедления по категориям задач")
    return save_figure(fig, output_dir, "cpu_category_slowdown_boxplot", formats, dpi)


def plot_category_completion_facets(
    aggregated: pd.DataFrame,
    configs: list[str],
    title: str,
    stem: str,
    output_dir: Path,
    formats: list[str],
    dpi: int,
) -> list[Path]:
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=True)
    plotted = False
    for ax, category in zip(axes, CATEGORY_ORDER):
        shares = completion_share_table(aggregated, configs, category=category)
        if not shares.empty and shares.to_numpy().sum() > 0:
            plotted = True
            bottom = np.zeros(len(shares))
            for status in STATUS_ORDER:
                values = shares[status].to_numpy(dtype=float)
                ax.bar(
                    shares.index.astype(str),
                    values,
                    bottom=bottom,
                    color=STATUS_COLORS[status],
                    label=status,
                )
                bottom += values
        ax.set_title(category.upper())
        ax.set_xlabel("Конфигурация")
        ax.set_ylim(0, 1.0)
    if not plotted:
        plt.close(fig)
        return []
    axes[0].set_ylabel("Доля запусков")
    fig.suptitle(title)
    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper right")
    return save_figure(fig, output_dir, stem, formats, dpi)


def plot_baseline_runtime_scatter(
    aggregated: pd.DataFrame,
    output_dir: Path,
    formats: list[str],
    dpi: int,
) -> list[Path]:
    baseline = aggregated.loc[
        aggregated["config_name"].eq("B00")
        & aggregated["full_ok"]
        & aggregated["crit_sum_mean"].notna()
        & aggregated["duration_median_sec"].gt(0),
        ["crit_sum_mean", "duration_median_sec", "category"],
    ].copy()
    if baseline.empty:
        return []

    palette = {"quick": "#5b8c5a", "medium": "#3f6ea8", "long": "#b85757"}
    baseline["log_duration"] = np.log10(baseline["duration_median_sec"])

    fig, ax = plt.subplots(figsize=(10, 6))
    for category in CATEGORY_ORDER:
        subset = baseline.loc[baseline["category"].eq(category)]
        if subset.empty:
            continue
        ax.scatter(
            subset["crit_sum_mean"],
            subset["log_duration"],
            s=40,
            alpha=0.8,
            color=palette[category],
            label=category.upper(),
        )
    ax.set_title("B00: crit_sum_mean vs log(runtime)")
    ax.set_xlabel("crit_sum_mean")
    ax.set_ylabel("log10(duration_sec)")
    ax.legend(title="Категория")
    return save_figure(fig, output_dir, "baseline_crit_sum_vs_runtime_scatter", formats, dpi)


def plot_correlation_heatmap(
    aggregated: pd.DataFrame,
    output_dir: Path,
    formats: list[str],
    dpi: int,
) -> list[Path]:
    baseline = aggregated.loc[aggregated["config_name"].eq("B00") & aggregated["full_ok"]].copy()
    feature_columns = [column for column in FEATURE_COLUMNS if column in baseline.columns]
    metric_columns = [column for column in BASELINE_METRIC_COLUMNS if column in baseline.columns]
    if baseline.empty or not feature_columns or not metric_columns:
        return []

    corr = baseline[feature_columns + metric_columns].corr(numeric_only=True).loc[feature_columns, metric_columns]
    if corr.empty:
        return []

    fig, ax = plt.subplots(figsize=(8, 6))
    image = ax.imshow(corr.to_numpy(dtype=float), cmap="coolwarm", vmin=-1, vmax=1, aspect="auto")
    ax.set_title("B00: корреляции признаков и runtime/memory метрик")
    ax.set_xticks(range(len(metric_columns)), metric_columns, rotation=45, ha="right")
    ax.set_yticks(range(len(feature_columns)), feature_columns)
    for row_index in range(len(feature_columns)):
        for col_index in range(len(metric_columns)):
            value = corr.iat[row_index, col_index]
            label = "" if pd.isna(value) else f"{value:.2f}"
            ax.text(col_index, row_index, label, ha="center", va="center", fontsize=8)
    fig.colorbar(image, ax=ax, shrink=0.85, label="Корреляция")
    return save_figure(fig, output_dir, "baseline_feature_runtime_corr_heatmap", formats, dpi)


def plot_feature_vs_failure_scatter(
    aggregated: pd.DataFrame,
    output_dir: Path,
    formats: list[str],
    dpi: int,
) -> list[Path]:
    baseline_rss = aggregated.loc[
        aggregated["config_name"].eq("B00") & aggregated["rss_peak_max_mb"].notna(),
        ["test_name", "rss_peak_max_mb"],
    ].rename(columns={"rss_peak_max_mb": "peak_rss_b00"})
    if baseline_rss.empty:
        return []

    frames = []
    offsets = {"R0.5": -0.09, "R01": -0.03, "S02": 0.03, "S04": 0.09}
    for config in ["R0.5", "R01", "S02", "S04"]:
        subset = aggregated.loc[
            aggregated["config_name"].eq(config), ["test_name", "full_ok"]
        ].rename(columns={"full_ok": "outcome"})
        merged = baseline_rss.merge(subset, on="test_name", how="inner")
        if merged.empty:
            continue
        merged["config"] = config
        merged["y"] = merged["outcome"].astype(float) + offsets[config]
        frames.append(merged)

    if not frames:
        return []

    scatter = pd.concat(frames, ignore_index=True)
    fig, ax = plt.subplots(figsize=(10, 6))
    for config in ["R0.5", "R01", "S02", "S04"]:
        subset = scatter.loc[scatter["config"].eq(config)]
        if subset.empty:
            continue
        ax.scatter(
            subset["peak_rss_b00"],
            subset["y"],
            s=34,
            alpha=0.75,
            color=SCATTER_COLORS[config],
            label=config,
        )
    ax.set_title("Признак задачи vs вероятность отказа")
    ax.set_xlabel("peak_rss_B00, MB")
    ax.set_ylabel("Исход")
    ax.set_yticks([0, 1], ["fail", "ok"])
    ax.legend(title="Конфигурация")
    return save_figure(fig, output_dir, "feature_vs_failure_scatter", formats, dpi)


def main() -> int:
    configure_matplotlib()
    args = parse_args()
    raw, aggregated = load_frames(args.raw_csv, args.aggregated_csv)
    created_files: list[Path] = []

    cpu_runtime = ok_runtime_rows(raw, aggregated, SERIES_CONFIGS["CPU"])
    ram_runtime = ok_runtime_rows(raw, aggregated, SERIES_CONFIGS["RAM"])
    swap_runtime = ok_runtime_rows(raw, aggregated, SERIES_CONFIGS["SWAP"])

    cpu_slowdown = matched_slowdown_rows(
        raw,
        aggregated,
        "B00",
        ["C0.1", "C0.25", "C0.5", "C0.75", "C01", "C04"],
    )
    ram_slowdown = matched_slowdown_rows(raw, aggregated, "B00", ["R0.5", "R01"])
    swap_slowdown = matched_slowdown_rows(raw, aggregated, "R0.5", ["S02", "S04"])

    cpu_ratio = raw.loc[
        raw["config_name"].isin(SERIES_CONFIGS["CPU"])
        & raw["status"].eq("ok")
        & raw["duration_sec"].gt(0)
        & raw["cpu_time_total_sec"].notna(),
        ["config_name", "cpu_time_total_sec", "duration_sec"],
    ].copy()
    cpu_ratio["cpu_over_wall"] = cpu_ratio["cpu_time_total_sec"] / cpu_ratio["duration_sec"]

    created_files.extend(
        plot_boxplot(
            cpu_runtime,
            "duration_sec",
            SERIES_CONFIGS["CPU"],
            "CPU: boxplot времени выполнения",
            "duration_sec",
            "cpu_duration_boxplot",
            args.output_dir,
            args.formats,
            args.dpi,
            log_scale=True,
        )
    )
    created_files.extend(
        plot_boxplot(
            cpu_slowdown.rename(columns={"config": "config_name"}),
            "slowdown",
            ["C0.1", "C0.25", "C0.5", "C0.75", "C01", "C04"],
            "CPU: boxplot коэффициента замедления относительно B00",
            "T(config) / T(B00)",
            "cpu_slowdown_boxplot",
            args.output_dir,
            args.formats,
            args.dpi,
        )
    )
    created_files.extend(
        plot_boxplot(
            cpu_ratio,
            "cpu_over_wall",
            SERIES_CONFIGS["CPU"],
            "CPU: boxplot отношения cpu_time_total / duration_sec",
            "cpu_time_total / duration_sec",
            "cpu_cpu_ratio_boxplot",
            args.output_dir,
            args.formats,
            args.dpi,
        )
    )
    created_files.extend(plot_cpu_median_slowdown_line(cpu_slowdown, args.output_dir, args.formats, args.dpi))
    created_files.extend(
        plot_stacked_completion(
            aggregated,
            SERIES_CONFIGS["CPU"],
            "CPU: completion rate по конфигурациям",
            "cpu_completion_rate_stacked",
            args.output_dir,
            args.formats,
            args.dpi,
        )
    )

    created_files.extend(
        plot_boxplot(
            ram_runtime,
            "duration_sec",
            SERIES_CONFIGS["RAM"],
            "RAM: boxplot времени выполнения",
            "duration_sec",
            "ram_duration_boxplot",
            args.output_dir,
            args.formats,
            args.dpi,
            log_scale=True,
        )
    )
    created_files.extend(
        plot_boxplot(
            ram_slowdown.rename(columns={"config": "config_name"}),
            "slowdown",
            ["R0.5", "R01"],
            "RAM: boxplot коэффициента замедления относительно B00",
            "T(config) / T(B00)",
            "ram_slowdown_boxplot",
            args.output_dir,
            args.formats,
            args.dpi,
        )
    )
    created_files.extend(
        plot_stacked_completion(
            aggregated,
            SERIES_CONFIGS["RAM"],
            "RAM: completion rate по конфигурациям",
            "ram_completion_rate_stacked",
            args.output_dir,
            args.formats,
            args.dpi,
        )
    )
    created_files.extend(
        plot_stacked_completion(
            aggregated,
            SERIES_CONFIGS["RAM"],
            "RAM: completion rate по LONG-задачам",
            "ram_completion_rate_long_stacked",
            args.output_dir,
            args.formats,
            args.dpi,
            category="long",
        )
    )
    created_files.extend(plot_ram_failure_scatter(aggregated, args.output_dir, args.formats, args.dpi))

    created_files.extend(
        plot_boxplot(
            swap_runtime,
            "duration_sec",
            SERIES_CONFIGS["SWAP"],
            "SWAP: boxplot времени выполнения",
            "duration_sec",
            "swap_duration_boxplot",
            args.output_dir,
            args.formats,
            args.dpi,
            log_scale=True,
        )
    )
    created_files.extend(
        plot_boxplot(
            swap_slowdown.rename(columns={"config": "config_name"}),
            "slowdown",
            ["S02", "S04"],
            "SWAP: boxplot коэффициента замедления относительно R0.5",
            "T(config) / T(R0.5)",
            "swap_slowdown_boxplot",
            args.output_dir,
            args.formats,
            args.dpi,
        )
    )
    created_files.extend(
        plot_stacked_completion(
            aggregated,
            SERIES_CONFIGS["SWAP"],
            "SWAP: completion rate по конфигурациям",
            "swap_completion_rate_stacked",
            args.output_dir,
            args.formats,
            args.dpi,
        )
    )
    created_files.extend(plot_swap_success_rate_line(aggregated, args.output_dir, args.formats, args.dpi))

    created_files.extend(plot_cpu_category_slowdown(cpu_slowdown, args.output_dir, args.formats, args.dpi))
    created_files.extend(
        plot_category_completion_facets(
            aggregated,
            SERIES_CONFIGS["RAM"],
            "RAM: completion rate по категориям задач",
            "ram_category_completion_rate_stacked",
            args.output_dir,
            args.formats,
            args.dpi,
        )
    )
    created_files.extend(
        plot_category_completion_facets(
            aggregated,
            SERIES_CONFIGS["SWAP"],
            "SWAP: completion rate по категориям задач",
            "swap_category_completion_rate_stacked",
            args.output_dir,
            args.formats,
            args.dpi,
        )
    )

    created_files.extend(plot_baseline_runtime_scatter(aggregated, args.output_dir, args.formats, args.dpi))
    created_files.extend(plot_correlation_heatmap(aggregated, args.output_dir, args.formats, args.dpi))
    created_files.extend(plot_feature_vs_failure_scatter(aggregated, args.output_dir, args.formats, args.dpi))

    if not created_files:
        raise FileNotFoundError("Не удалось построить ни одного графика.")

    print("Созданные файлы:")
    for path in created_files:
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
