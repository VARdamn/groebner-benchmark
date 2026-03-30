import csv
import html
from datetime import datetime

import src.config as equations
import src.utils as utils

SUMMARY_FILE_PREFIX = "summary"
SUMMARY_HTML_SUFFIX = ".html"
SUMMARY_CSV_SUFFIX = ".csv"


def format_created_at(created_at):
    return datetime.strptime(created_at, "%Y%m%d_%H%M%S").strftime("%d.%m.%Y %H:%M:%S")


def build_run_summary_metadata(
    created_at,
    cpu,
    ram,
    swap,
    total_run_time,
    memory_interval,
    timeout_seconds,
    categories,
    selected_tests,
    completed,
    skipped,
    failures,
):
    return {
        "Создано": format_created_at(created_at),
        "CPU": cpu,
        "RAM": ram,
        "SWAP": swap,
        "Общее время работы (с)": utils.safe_round(total_run_time),
        "Выбрано тестов": len(selected_tests),
        "Выполнено": completed,
        "Пропущено": skipped,
        "Ошибок": len(failures),
        "Интервал замера памяти (с)": memory_interval,
        "Таймаут теста (с)": utils.format_csv_value(timeout_seconds) if timeout_seconds is not None else "нет",
        "Категории": " ".join(categories) if categories else "",
    }


def build_summary_paths(created_at):
    return (
        f"{SUMMARY_FILE_PREFIX}_{created_at}{SUMMARY_HTML_SUFFIX}",
        f"{SUMMARY_FILE_PREFIX}_{created_at}{SUMMARY_CSV_SUFFIX}",
    )


def build_summary_table_rows(rows):
    table_rows = []
    for row in rows:
        crit1 = row.get("crit1")
        crit2 = row.get("crit2")
        reduce_value = None
        if crit1 is not None and crit2 is not None:
            reduce_value = int(crit1) + int(crit2)

        time_value = row.get("time")
        if row.get("timed_out"):
            timeout_seconds = row.get("timeout_seconds")
            time_value = f"TIMEOUT ({utils.format_csv_value(timeout_seconds)}с)"

        table_rows.append(
            [
                utils.format_csv_value(row.get("test")),
                utils.format_csv_value(time_value),
                utils.format_csv_value(row.get("dimension")),
                utils.format_csv_value(crit1),
                utils.format_csv_value(crit2),
                utils.format_csv_value(row.get("avr_memory")),
                utils.format_csv_value(row.get("max_memory")),
                utils.format_csv_value(row.get("num_equations")),
                utils.format_csv_value(row.get("num_vars")),
                utils.format_csv_value(row.get("mem_per_sec")),
                utils.format_csv_value(reduce_value),
            ]
        )
    return table_rows


def write_summary_html(summary_path, metadata, table_rows):
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_rows = []
    html_table_rows = []

    for key, value in metadata.items():
        metadata_rows.append(
            "<tr>"
            f"<th>{html.escape(str(key))}</th>"
            f"<td>{html.escape(utils.format_csv_value(value))}</td>"
            "</tr>"
        )

    for values in table_rows:
        cells = "".join(f"<td>{html.escape(value)}</td>" for value in values)
        html_table_rows.append(f"<tr>{cells}</tr>")

    header_cells = "".join(
        f"<th>{html.escape(column)}</th>" for column in equations.SUMMARY_COLUMNS
    )

    document = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Сводка бенчмарков</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fb;
      --card: #ffffff;
      --border: #d7deea;
      --text: #1f2937;
      --muted: #5b6472;
      --accent: #1d4ed8;
      --accent-soft: #dbeafe;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      padding: 16px;
      font-family: "Segoe UI", Tahoma, sans-serif;
      background: linear-gradient(180deg, #eef4ff 0%, var(--bg) 100%);
      color: var(--text);
    }}
    .page {{
      max-width: 1800px;
      margin: 0 auto;
      display: grid;
      gap: 14px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
      overflow: hidden;
    }}
    .card-header {{
      padding: 12px 16px 8px;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(135deg, var(--accent-soft), #ffffff 70%);
    }}
    h1, h2 {{
      margin: 0;
      font-weight: 700;
    }}
    .subtitle {{
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    .meta-table th,
    .meta-table td {{
      padding: 8px 14px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }}
    .meta-table th {{
      width: 220px;
      color: var(--muted);
      font-weight: 600;
      background: #fafcff;
    }}
    .results-wrap {{
      padding: 0 0 4px;
      overflow-x: auto;
    }}
    .results-table th,
    .results-table td {{
      padding: 6px 8px;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
      text-align: left;
      font-size: 12px;
    }}
    .results-table thead th {{
      position: sticky;
      top: 0;
      background: #edf4ff;
      color: #153e75;
      font-weight: 700;
    }}
    .results-table tbody tr:nth-child(even) {{
      background: #fbfdff;
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="card">
      <div class="card-header">
        <h1>Сводка бенчмарков</h1>
        <div class="subtitle">Параметры запуска и общая информация</div>
      </div>
      <table class="meta-table">
        <tbody>
          {''.join(metadata_rows)}
        </tbody>
      </table>
    </section>
    <section class="card">
      <div class="card-header">
        <h2>Результаты по тестам</h2>
        <div class="subtitle">Средняя и максимальная память сохраняются отдельно для каждого теста</div>
      </div>
      <div class="results-wrap">
        <table class="results-table">
          <thead>
            <tr>{header_cells}</tr>
          </thead>
          <tbody>
            {''.join(html_table_rows)}
          </tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""

    summary_path.write_text(document, encoding="utf-8")


def write_summary_csv(summary_path, table_rows):
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=",", lineterminator="\n")
        writer.writerow(equations.SUMMARY_COLUMNS)
        writer.writerows(table_rows)


def write_summary_reports(rows, html_path, csv_path, metadata):
    table_rows = build_summary_table_rows(rows)
    write_summary_html(html_path, metadata, table_rows)
    write_summary_csv(csv_path, table_rows)
