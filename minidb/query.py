import operator
from .errors import ValidationError

OPS = {
    "=": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
}


def validate_condition(cond, schema):
    if cond is None:
        return
    if not isinstance(cond, (tuple, list)) or len(cond) != 3:
        raise ValidationError(
            f"Условие должно быть (столбец, оператор, значение), получено {cond!r}")
    col, op, value = cond
    if col not in schema.by_name:
        raise ValidationError(f"Неизвестный столбец в условии: {col!r}")
    if op not in OPS:
        raise ValidationError(
            f"Неизвестный оператор {op!r}, допустимы: {', '.join(OPS)}")
    schema.by_name[col].type.validate(value)    # тип значения = тип столбца


def matches(row, cond):
    if cond is None:
        return True
    col, op, value = cond
    return OPS[op](row[col], value)