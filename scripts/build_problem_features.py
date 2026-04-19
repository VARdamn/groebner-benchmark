import argparse
import csv
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.polynomial_tools import evaluate_expression, extract_active_variables
import src.utils as utils

FEATURE_COLUMNS = [
    "test_name",
    "equation_count",
    "variable_count",
    "dimension",
    "max_total_degree",
    "mean_total_degree",
    "max_terms_per_equation",
    "mean_terms_per_equation",
    "total_terms",
]


class Polynomial:
    def __init__(self, variables_count, terms=None):
        self.variables_count = variables_count
        self.terms = {
            tuple(monomial): coefficient
            for monomial, coefficient in (terms or {}).items()
            if coefficient != 0
        }

    @classmethod
    def variable(cls, index, variables_count):
        powers = [0] * variables_count
        powers[index] = 1
        return cls(variables_count, {tuple(powers): 1})

    @classmethod
    def constant(cls, value, variables_count):
        return cls(variables_count, {tuple([0] * variables_count): value})

    def _coerce(self, other):
        if isinstance(other, Polynomial):
            if other.variables_count != self.variables_count:
                raise ValueError("Несовпадающее количество переменных.")
            return other
        if isinstance(other, (int, float)):
            return Polynomial.constant(other, self.variables_count)
        raise TypeError(f"Неподдерживаемый тип: {type(other)!r}")

    def __add__(self, other):
        result = dict(self.terms)
        for monomial, coefficient in self._coerce(other).terms.items():
            result[monomial] = result.get(monomial, 0) + coefficient
            if result[monomial] == 0:
                del result[monomial]
        return Polynomial(self.variables_count, result)

    def __radd__(self, other):
        return self + other

    def __sub__(self, other):
        return self + (-self._coerce(other))

    def __rsub__(self, other):
        return self._coerce(other) - self

    def __neg__(self):
        return Polynomial(
            self.variables_count,
            {monomial: -coefficient for monomial, coefficient in self.terms.items()},
        )

    def __mul__(self, other):
        other = self._coerce(other)
        result = {}
        for left_monomial, left_coefficient in self.terms.items():
            for right_monomial, right_coefficient in other.terms.items():
                monomial = tuple(a + b for a, b in zip(left_monomial, right_monomial))
                result[monomial] = result.get(monomial, 0) + left_coefficient * right_coefficient
                if result[monomial] == 0:
                    del result[monomial]
        return Polynomial(self.variables_count, result)

    def __rmul__(self, other):
        return self * other

    @property
    def total_degree(self):
        if not self.terms:
            return 0
        return max(sum(monomial) for monomial in self.terms)

    @property
    def term_count(self):
        return len(self.terms)


def parse_polynomial(expression, variables):
    symbols = {
        variable: Polynomial.variable(index, len(variables))
        for index, variable in enumerate(variables)
    }
    parsed = evaluate_expression(expression, symbols)
    if isinstance(parsed, Polynomial):
        return parsed
    if isinstance(parsed, (int, float)):
        return Polynomial.constant(parsed, len(variables))
    raise TypeError(f"Неподдерживаемый результат выражения: {type(parsed)!r}")


def build_feature_row(test_name, payload):
    variables = extract_active_variables(payload)
    equations = payload.get("equations") or []
    dimension = payload.get("dimension")

    polynomials = [parse_polynomial(expression, variables) for expression in equations]
    total_degrees = [polynomial.total_degree for polynomial in polynomials]
    term_counts = [polynomial.term_count for polynomial in polynomials]

    return {
        "test_name": test_name,
        "equation_count": len(equations),
        "variable_count": len(variables),
        "dimension": int(dimension) if dimension is not None else len(variables),
        "max_total_degree": max(total_degrees, default=0),
        "mean_total_degree": utils.safe_round(sum(total_degrees) / len(total_degrees)) if total_degrees else 0,
        "max_terms_per_equation": max(term_counts, default=0),
        "mean_terms_per_equation": utils.safe_round(sum(term_counts) / len(term_counts)) if term_counts else 0,
        "total_terms": sum(term_counts),
    }


def build_problem_features(json_dir, output_path):
    rows = []
    for test_name, path in sorted(utils.discover_test_files(json_dir).items()):
        rows.append(build_feature_row(test_name, utils.load_json(path)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FEATURE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Построение числовых признаков для задач из json/.")
    parser.add_argument("--json-dir", default="json", help="Каталог с входными JSON-задачами.")
    parser.add_argument("--output", default="data/problem_features.csv", help="Путь к выходному CSV.")
    args = parser.parse_args()

    build_problem_features(Path(args.json_dir), Path(args.output))


if __name__ == "__main__":
    main()
