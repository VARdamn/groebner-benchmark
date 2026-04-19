# Groebner Benchmark Runner

Инструмент для запуска вычислений базиса Грёбнера по наборам из `json/*.json` с замером времени и памяти, генерацией сводных отчётов и сравнительным анализом серий запусков.

## Назначение

Проект выполняет следующие задачи:

- загружает систему уравнений из JSON-файла
- запускает `GB.algorithm2(...)` из `ginv`
- сохраняет для каждого теста время, память, `crit1`, `crit2` и производные метрики
- формирует сводные отчёты `summary_YYYYMMDD_HHMMSS.html` и `summary_YYYYMMDD_HHMMSS.csv`
- в режиме серии повторяет одинаковый набор тестов в Docker-контейнере с разными лимитами CPU, RAM и SWAP

## Структура проекта

- `main.py`  
  точка входа и CLI
- `src/runner.py`  
  логика режимов `single` и `series`
- `src/benchmark.py`  
  запуск одного теста в отдельном процессе с мониторингом памяти и таймаутом
- `src/reporting.py`  
  генерация HTML- и CSV-сводок
- `src/config.py`  
  категории тестов и колонки итоговой таблицы
- `scripts/plot_series_analysis.py`  
  постобработка CSV из серии и построение графиков

## Подготовка окружения

Требования:

- Python 3.11+
- Docker и Docker Compose для режима `series`

Установка зависимостей:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Быстрый старт

Одиночный запуск с категориями по умолчанию:

```bash
python main.py
```

Серия запусков через Docker:

```bash
python main.py --mode series
```

Построение аналитики по готовой серии:

```bash
./venv/bin/python scripts/plot_series_analysis.py --series-dir data/series_1
```

## Режим `single`

Режим `single` запускает выбранные тесты на текущем хосте.

Если `--category` не указан, по умолчанию берутся категории:
`very_quick quick`

Примеры:

```bash
python main.py
python main.py --mode single --category quick medium
python main.py --mode single --all-tests
python main.py --mode single --force --category long
python main.py --mode single --timeout 60 --category medium
```

После выполнения создаются:

- `results/<test>.json` для каждого завершённого теста
- `results/<test>.json` с `timed_out: true` для теста, остановленного по таймауту
- `summary_YYYYMMDD_HHMMSS.html`
- `summary_YYYYMMDD_HHMMSS.csv`

Если `--force` не указан, уже существующие `results/*.json` пропускаются.

## Режим `series`

Режим `series` запускает `single` внутри Docker-контейнеров с разными лимитами ресурсов.

Если `--category` не указан, по умолчанию берутся категории:
`quick medium`

Примеры:

```bash
python main.py --mode series
python main.py --mode series --skip-ram --skip-swap
python main.py --mode series --category long too_long
python main.py --mode series --all-tests
python main.py --mode series --timeout 120
```

Особенности режима:

- для каждой конфигурации ресурсов поднимается отдельный контейнер
- лимиты задаются при старте контейнера и не меняются внутри уже запущенного процесса
- каталог серии выбирается автоматически как следующий `data/series_X` после уже существующих

Текущие именованные конфигурации CPU в коде:

- `C0.1`
- `C0.25`
- `C0.5`
- `C0.75`
- `C01`
- `C04`
- `B00`
- RAM: `4g` при `SWAP=6g`
- SWAP: `1.5g`, `2g`, `4g` при `RAM=0.5g`

Структура серии:

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

Во время контейнерного прогона индивидуальные `results/*.json` также появляются в корне проекта, потому что контейнер монтирует рабочую директорию как volume.

## Анализ серий

Скрипт `scripts/plot_series_analysis.py` читает итоговые CSV-файлы серии и строит графики.

Базовый запуск:

```bash
./venv/bin/python scripts/plot_series_analysis.py --series-dir data/series_1
```

Если `--series-dir` не указан, скрипт выбирает последнюю серию из `data/`.

Что делает скрипт:

- читает `summary_*.csv` из `CPU`, `RAM`, `SWAP`
- сопоставляет одинаковые тесты между конфигурациями
- учитывает `TIMEOUT`, подставляя значение таймаута как верхнюю оценку времени
- сохраняет графики и агрегированные CSV в `data/series_X/analysis/`

Примеры:

```bash
./venv/bin/python scripts/plot_series_analysis.py --series-dir data/series_1 --resources CPU RAM
./venv/bin/python scripts/plot_series_analysis.py --series-dir data/series_1 --cpu-base 7 --ram-base 4g
./venv/bin/python scripts/plot_series_analysis.py --output-dir reports/series_1_analysis --series-dir data/series_1
./venv/bin/python scripts/plot_series_analysis.py --skip-resource-analysis --pairwise-csv-x data/series_1/SWAP/summary_4g.csv --pairwise-csv-y data/series_1/RAM/summary_4g.csv --pairwise-output-stem ram_vs_swap_tradeoff
```

Скрипт строит:

- сравнение времени по задачам
- распределение времени
- долю задач, где конфигурация оказалась лучшей
- геометрическое среднее времени
- суммарное время серии
- scatter plot ускорения относительно базовой конфигурации

Также доступно попарное сравнение двух произвольных CSV-файлов.

## Docker

Сборка образа:

```bash
docker build -t groebner-bench .
```

Контейнер по умолчанию стартует с командой:

```bash
python main.py --category very_quick quick
```

Запуск контейнера с лимитами:

```bash
CPUS=1.0 RAM=1g SWAP=1g docker compose run --rm groebner-bench
```

Запуск контейнера с аргументами:

```bash
CPUS=1.0 RAM=1g SWAP=1g docker compose run --rm groebner-bench --mode single --category quick medium
```

Переменные окружения:

- `CPUS` задаёт лимит CPU контейнера
- `RAM` задаёт `mem_limit`
- `SWAP` задаёт `memswap_limit`
- внутри контейнера значения дополнительно пробрасываются как `CPU`, `RAM`, `SWAP` и попадают в summary-метаданные

## Категории тестов

Категории определены в `src/config.py`:

- `very_quick`
- `quick`
- `medium`
- `long`
- `too_long`

При указании `--all-tests` категории игнорируются, и запускаются все JSON из каталога `json/`.

## Справочник флагов `main.py`

### `--mode`

Назначение: выбор режима запуска  
Значения: `single`, `series`  
По умолчанию: `single`

### `--category`

Назначение: выбор одной или нескольких категорий из `src/config.py`  
Формат: `--category quick medium`  
По умолчанию:

- для `single` берутся `very_quick quick`
- для `series` берутся `quick medium`

### `--all-tests`

Назначение: запуск всех найденных JSON-файлов из каталога `json/`  
Тип: флаг без значения  
По умолчанию: выключен

### `--force`

Назначение: повторный расчёт тестов даже при наличии `results/<test>.json`  
Тип: флаг без значения  
По умолчанию: выключен

### `--memory-interval`

Назначение: интервал сэмплирования памяти в секундах  
Формат: `--memory-interval 0.1`  
По умолчанию: `1`

Практика:

- меньшее значение точнее ловит короткие пики памяти, но добавляет overhead
- большее значение меньше влияет на скорость, но может пропустить кратковременные пики
- для сравнимых экспериментов лучше держать одно и то же значение во всех запусках

### `--timeout`

Назначение: ограничение времени одного теста в секундах  
Формат: `--timeout 60`  
По умолчанию: не задан

Поведение:

- тест выполняется в отдельном процессе
- при превышении лимита дочерний процесс завершается принудительно
- для такого теста сохраняется JSON-результат с `timed_out: true`
- в summary время отображается как `TIMEOUT (<seconds>с)`

### `--fail-fast`

Назначение: остановка на первой ошибке  
Тип: флаг без значения  
По умолчанию: выключен

### `--quiet`

Назначение: уменьшение подробности вывода в консоль  
Тип: флаг без значения  
По умолчанию: выключен

### `--skip-cpu`

Назначение: пропуск CPU-части серии  
Тип: флаг без значения  
Контекст: только для `--mode series`

### `--skip-ram`

Назначение: пропуск RAM-части серии  
Тип: флаг без значения  
Контекст: только для `--mode series`

### `--skip-swap`

Назначение: пропуск SWAP-части серии  
Тип: флаг без значения  
Контекст: только для `--mode series`
