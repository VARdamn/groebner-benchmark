import re

TOKEN_PATTERN = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|[()+\-*/^])")
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def extract_active_variables(payload):
    declared_variables = payload.get("variables") or []
    equations = payload.get("equations") or []
    referenced_tokens = []
    seen = set()

    for expression in equations:
        for token in IDENTIFIER_PATTERN.findall(expression):
            if token not in seen:
                referenced_tokens.append(token)
                seen.add(token)

    if not referenced_tokens:
        return declared_variables

    ordered_variables = []
    remaining = set(referenced_tokens)

    for variable in declared_variables:
        if variable in remaining:
            ordered_variables.append(variable)
            remaining.remove(variable)

    for token in referenced_tokens:
        if token in remaining:
            ordered_variables.append(token)
            remaining.remove(token)

    return ordered_variables


def evaluate_expression(expression, symbols):
    stack = []

    for token_type, token_value in _to_rpn(_tokenize(expression)):
        if token_type == "number":
            stack.append(token_value)
        elif token_type == "identifier":
            try:
                stack.append(symbols[token_value])
            except KeyError as exc:
                raise ValueError(f"Неизвестная переменная: {token_value}") from exc
        else:
            _apply_operator(token_value, stack)

    if len(stack) != 1:
        raise ValueError("Выражение разобрано некорректно.")
    return stack[0]


def evaluate_expressions(expressions, symbols):
    return [evaluate_expression(expression, symbols) for expression in expressions]


def _tokenize(expression):
    position = 0
    tokens = []

    while position < len(expression):
        match = TOKEN_PATTERN.match(expression, position)
        if not match:
            snippet = expression[position:position + 32]
            raise ValueError(f"Не удалось разобрать выражение около: {snippet!r}")
        tokens.append(match.group(1))
        position = match.end()

    return tokens


def _to_number(token):
    if "." in token:
        return float(token)
    return int(token)


def _to_rpn(tokens):
    output = []
    operators = []
    previous_kind = None

    for token in tokens:
        if NUMBER_PATTERN.fullmatch(token):
            output.append(("number", _to_number(token)))
            previous_kind = "value"
            continue

        if IDENTIFIER_PATTERN.fullmatch(token):
            output.append(("identifier", token))
            previous_kind = "value"
            continue

        if token == "(":
            operators.append(token)
            previous_kind = "("
            continue

        if token == ")":
            while operators and operators[-1] != "(":
                output.append(("operator", operators.pop()))
            if not operators:
                raise ValueError("Несогласованные скобки в выражении.")
            operators.pop()
            previous_kind = "value"
            continue

        operator = "u-" if token == "-" and previous_kind in (None, "operator", "(") else token
        precedence, associativity, _ = _operator_spec(operator)

        while operators and operators[-1] != "(":
            top_precedence, _, _ = _operator_spec(operators[-1])
            if top_precedence > precedence or (
                top_precedence == precedence and associativity == "left"
            ):
                output.append(("operator", operators.pop()))
            else:
                break

        operators.append(operator)
        previous_kind = "operator"

    while operators:
        operator = operators.pop()
        if operator == "(":
            raise ValueError("Несогласованные скобки в выражении.")
        output.append(("operator", operator))

    return output


def _operator_spec(operator):
    return {
        "+": (1, "left", 2),
        "-": (1, "left", 2),
        "*": (2, "left", 2),
        "/": (2, "left", 2),
        "^": (4, "right", 2),
        "u-": (3, "right", 1),
    }[operator]


def _apply_operator(operator, stack):
    _, _, arity = _operator_spec(operator)
    if len(stack) < arity:
        raise ValueError("Недостаточно операндов в выражении.")

    if operator == "u-":
        value = stack.pop()
        stack.append(-value if isinstance(value, (int, float)) else (-1) * value)
        return

    right = stack.pop()
    left = stack.pop()

    if operator == "+":
        stack.append(left + right)
    elif operator == "-":
        stack.append(left - right)
    elif operator == "*":
        stack.append(left * right)
    elif operator == "/":
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            raise ValueError("Поддерживается деление только числовых коэффициентов.")
        stack.append(left / right)
    else:
        stack.append(_pow(left, right))


def _pow(value, exponent):
    if isinstance(exponent, float):
        if not exponent.is_integer():
            raise ValueError("Степень должна быть целым числом.")
        exponent = int(exponent)

    if not isinstance(exponent, int) or exponent < 0:
        raise ValueError("Степень должна быть неотрицательным целым числом.")

    result = 1
    while exponent:
        if exponent % 2 == 1:
            result = result * value
        value = value * value
        exponent //= 2
    return result
