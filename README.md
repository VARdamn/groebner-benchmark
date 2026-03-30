# Groebner Benchmark Runner

Инструмент для запуска вычислений базиса Грёбнера по наборам из `json/*.json` с замером времени и памяти, генерацией сводных отчётов и сравнительным анализом серий запусков.

## Что делает проект

- Загружает систему уравнений из JSON-файла.
- Запускает `GB.algorithm2(...)` из `ginv`.
- Для каждого теста сохраняет:
  - время выполнения;
  - среднюю и максимальную память;
  - `crit1`, `crit2`;
  - производные метрики вроде `mem_per_sec`.
- Формирует сводные отчёты:
  - `summary_YYYYMMDD_HHMMSS.html`;
  - `summary_YYYYMMDD_HHMMSS.csv`.
- В режиме серии прогоняет одинаковый набор тестов в Docker-контейнере с разными лимитами CPU, RAM и SWAP и складывает отчёты в `data/series_X/`.

## Структура проекта

- `main.py`:
  точка входа и CLI.
- `src/runner.py`:
  логика режимов `single` и `series`.
- `src/benchmark.py`:
  запуск одного теста в отдельном процессе с мониторингом памяти и таймаутом.
- `src/reporting.py`:
  генерация HTML- и CSV-сводок.
- `src/config.py`:
  категории тестов и колонки итоговой таблицы.
- `scripts/plot_series_analysis.py`:
  постобработка CSV из серии и построение графиков.

## Требования

- Python 3.11+.
- Docker и Docker Compose для режима `series`.

Установка зависимостей:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Режимы запуска

### `single`

Одиночный запуск выбранных тестов на текущем хосте.

Если `--category` не указан, по умолчанию используются категории:
`very_quick quick`.

Примеры:

```bash
python main.py
python main.py --mode single --category quick medium
python main.py --mode single --all-tests
python main.py --mode single --force --category long
python main.py --mode single --timeout 60 --category medium
```

Что создаётся:

- `results/<test>.json` для каждого успешно завершённого или прерванного по таймауту теста;
- `summary_YYYYMMDD_HHMMSS.html`;
- `summary_YYYYMMDD_HHMMSS.csv`.

Если `--force` не указан, уже существующие `results/*.json` пропускаются.

### `series`

Серия запусков через Docker с изменением лимитов ресурсов контейнера.

Если `--category` не указан, по умолчанию используются категории:
`quick medium`.

Примеры:

```bash
python main.py --mode series
python main.py --mode series --skip-ram --skip-swap
python main.py --mode series --category long too_long
python main.py --mode series --all-tests
python main.py --mode series --timeout 120
```

Важно:

- режим `series` запускает `docker compose run --rm groebner-bench ...`;
- для каждой конфигурации ресурсов поднимается отдельный контейнер;
- лимиты задаются при старте контейнера, поэтому они не меняются "на лету" внутри одного процесса;
- каталог серии выбирается автоматически как следующий `data/series_X` после уже существующих.

Текущие конфигурации в коде:

- CPU: `7`, `10`
- RAM: `4g` при `SWAP=6g`
- SWAP: `1.5g`, `2g`, `4g` при `RAM=0.5g`

## Результаты серии

После серии создаётся структура вида:

```text
data/
  series_1/
    CPU/
      summary_7.html
      summary_7.csv
      summary_10.html
      summary_10.csv
    RAM/
      summary_4g.html
      summary_4g.csv
    SWAP/
      summary_1.5g.html
      summary_1.5g.csv
      summary_2g.html
      summary_2g.csv
      summary_4g.html
      summary_4g.csv
```

Внутри серии хранятся именно summary-файлы. Индивидуальные `results/*.json` также создаются во время каждого контейнерного прогона в корне проекта, потому что контейнер монтирует текущую директорию как volume.

## Анализ серий

Для построения графиков по итоговым CSV используйте:

```bash
./venv/bin/python scripts/plot_series_analysis.py --series-dir data/series_1
```

По умолчанию скрипт:

- читает `summary_*.csv` из `CPU`, `RAM`, `SWAP`;
- находит одинаковые тесты между конфигурациями;
- учитывает `TIMEOUT`, используя значение таймаута как верхнюю оценку времени;
- сохраняет графики и агрегированные CSV в `data/series_X/analysis/`.

Полезные примеры:

```bash
./venv/bin/python scripts/plot_series_analysis.py --series-dir data/series_1 --resources CPU RAM
./venv/bin/python scripts/plot_series_analysis.py --series-dir data/series_1 --cpu-base 7 --ram-base 4g
./venv/bin/python scripts/plot_series_analysis.py --output-dir reports/series_1_analysis --series-dir data/series_1
./venv/bin/python scripts/plot_series_analysis.py --skip-resource-analysis --pairwise-csv-x data/series_1/SWAP/summary_4g.csv --pairwise-csv-y data/series_1/RAM/summary_4g.csv --pairwise-output-stem ram_vs_swap_tradeoff
```

Скрипт строит:

- сравнение времени по задачам;
- распределение времени;
- долю задач, где конфигурация была лучшей;
- геометрическое среднее времени;
- суммарное время серии;
- scatter plot ускорения относительно базовой конфигурации.

Также поддерживается попарное сравнение двух произвольных CSV-файлов.

Если `--series-dir` не указан, скрипт автоматически выберет последнюю серию из `data/`.

## Docker

### Сборка образа

```bash
docker build -t groebner-bench .
```

### Запуск контейнера

По умолчанию контейнер стартует с командой:

```bash
python main.py --category very_quick quick
```

Пример явного запуска:

```bash
CPUS=1.0 RAM=1g SWAP=1g docker compose run --rm groebner-bench
```

Пример запуска с аргументами:

```bash
CPUS=1.0 RAM=1g SWAP=1g docker compose run --rm groebner-bench --mode single --category quick medium
```

Переменные окружения:

- `CPUS` управляет лимитом CPU контейнера;
- `RAM` управляет `mem_limit`;
- `SWAP` управляет `memswap_limit`;
- внутри контейнера значения дополнительно пробрасываются как `CPU`, `RAM`, `SWAP` и попадают в summary-метаданные.

## Категории тестов

Категории берутся из `src/config.py`:

- `very_quick`
- `quick`
- `medium`
- `long`
- `too_long`

При указании `--all-tests` категории игнорируются, и запускаются все JSON из каталога `json/`.

## Полезные параметры CLI

- `--mode single|series`
  выбор режима запуска.
- `--category ...`
  одна или несколько категорий из `src/config.py`.
- `--all-tests`
  запуск всех найденных JSON из каталога `json/`.
- `--force`
  пересчитывать тесты, даже если `results/<test>.json` уже существует.
- `--memory-interval`
  интервал сэмплирования памяти в секундах.
- `--timeout`
  таймаут одного теста в секундах.
- `--fail-fast`
  остановиться на первой ошибке.
- `--quiet`
  уменьшить подробность вывода.
- `--skip-cpu`, `--skip-ram`, `--skip-swap`
  пропуск соответствующей части серии в режиме `series`.

## Как работает `--memory-interval`

`--memory-interval` задаёт шаг, с которым родительский процесс снимает RSS дочернего процесса с вычислением.

- Меньшее значение, например `0.01`:
  точнее ловит короткие пики памяти, но добавляет overhead.
- Большее значение, например `0.5`:
  меньше влияет на скорость, но может пропустить кратковременные пики.

Для сравнимых экспериментов лучше использовать одинаковое значение во всех запусках.

## Как работает `--timeout`

Если задан `--timeout`, каждый тест выполняется в отдельном процессе с ограничением по времени.

- если тест завершился вовремя, результат сохраняется как обычно;
- если время вышло, дочерний процесс принудительно завершается;
- для такого теста сохраняется JSON-результат с `timed_out: true`;
- в summary в колонке времени значение отображается как `TIMEOUT (<seconds>с)`.
