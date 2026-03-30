import argparse
import subprocess
import sys

import src.config as equations
import src.runner as runner


def build_parser():
    parser = argparse.ArgumentParser(description="Запуск бенчмарков вычисления базиса Гребнера.")
    parser.add_argument(
        "--mode",
        choices=("single", "series"),
        default="single",
        help="single: один прогон, series: серия запусков с изменением CPU/RAM/SWAP.",
    )
    parser.add_argument(
        "--category",
        nargs="+",
        choices=sorted(equations.CATEGORY_MAP.keys()),
        help="Предопределенные группы тестов.",
    )
    parser.add_argument(
        "--all-tests",
        action="store_true",
        help="Запустить все тесты из каталога json.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Пересчитывать тесты, даже если JSON-результат уже существует.",
    )
    parser.add_argument(
        "--memory-interval",
        type=float,
        default=1,
        help="Интервал сэмплирования памяти в секундах.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        help="Таймаут одного теста в секундах. Если превышен, тест прерывается и выполняется следующий.",
    )
    parser.add_argument("--fail-fast", action="store_true", help="Остановиться на первой ошибке.")
    parser.add_argument("--quiet", action="store_true", help="Уменьшить подробность вывода.")
    parser.add_argument("--skip-cpu", action="store_true", help="Не запускать серию изменения CPU.")
    parser.add_argument("--skip-ram", action="store_true", help="Не запускать серию изменения RAM.")
    parser.add_argument("--skip-swap", action="store_true", help="Не запускать серию изменения SWAP.")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.mode == "series":
            return runner.run_series_mode(args)
        return runner.run_single_mode(args)
    except (RuntimeError, FileNotFoundError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
