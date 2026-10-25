import re
import struct
from .errors import SchemaError, StorageError, ValidationError
from .types import make_type

MAGIC = b"MDB1"
HEADER_SIZE = 1024
NAME_LEN = 32
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TYPE_CODES = {"INT": 1, "FLOAT": 2, "STRING": 3}
CODE_TYPES = {v: k for k, v in TYPE_CODES.items()}

_HEAD = struct.Struct("<4sQBB")
_COL = struct.Struct("<32sBH")   
_FLAG = struct.Struct("<?")
MAX_COLUMNS = (HEADER_SIZE - _HEAD.size) // _COL.size


class Column:
    def __init__(self, name, type_):
        self.name = name
        self.type = type_


def column_from_spec(spec):
    """("size", "INT") или ("name", "STRING", 64) -> Column."""
    try:
        name, type_name, *rest = spec
    except (TypeError, ValueError):
        raise SchemaError(f"Плохое описание столбца: {spec!r}")
    try:
        return Column(name, make_type(type_name, rest[0] if rest else None))
    except ValidationError as e:
        raise SchemaError(f"Столбец {name!r}: {e}")


class Schema:
    def __init__(self, columns, pk):
        if not columns:
            raise SchemaError("В таблице нет столбцов")
        if len(columns) > MAX_COLUMNS:
            raise SchemaError(f"Не больше {MAX_COLUMNS} столбцов")
        names = [c.name for c in columns]
        for n in names:
            if (not isinstance(n, str) or not NAME_RE.match(n)
                    or len(n.encode("utf-8")) > NAME_LEN):
                raise SchemaError(
                    f"Плохое имя столбца {n!r}: буквы, цифры, _, не с цифры, до {NAME_LEN} символов")
        if len(set(names)) != len(names):
            raise SchemaError("Имена столбцов повторяются")
        if pk not in names:
            raise SchemaError(f"PRIMARY KEY {pk!r} не найден среди столбцов")

        self.columns = columns
        self.pk = pk
        self.pk_index = names.index(pk)
        if columns[self.pk_index].type.name != "INT":
            raise SchemaError("PRIMARY KEY должен быть типа INT")

        self.by_name = {c.name: c for c in columns}
        self.record_size = _FLAG.size + sum(c.type.size for c in columns)

    # строка таблицы <-> байты
    def row_to_bytes(self, row, alive=True):
        parts = [_FLAG.pack(alive)]
        for c in self.columns:
            parts.append(c.type.pack(row[c.name])) 
        return b"".join(parts)

    def bytes_to_row(self, raw):
        alive = _FLAG.unpack(raw[:1])[0]
        row, pos = {}, 1
        for c in self.columns:
            row[c.name] = c.type.unpack(raw[pos:pos + c.type.size])
            pos += c.type.size
        return alive, row

    # схема <-> байты заголовка
    def to_bytes(self, next_id):
        out = [_HEAD.pack(MAGIC, next_id, len(self.columns), self.pk_index)]
        for c in self.columns:
            length = c.type.size if c.type.name == "STRING" else 0
            out.append(_COL.pack(c.name.encode("utf-8"),
                                 TYPE_CODES[c.type.name], length))
        return b"".join(out)

    @classmethod
    def from_bytes(cls, raw):
        """Возвращает (schema, next_id). Любая порча заголовка -> StorageError."""
        if len(raw) < _HEAD.size:
            raise StorageError("Заголовок слишком короткий")
        magic, next_id, ncols, pk_index = _HEAD.unpack_from(raw, 0)
        if magic != MAGIC:
            raise StorageError("Это не файл MiniDB (неверная сигнатура)")
        if not 1 <= ncols <= MAX_COLUMNS or pk_index >= ncols:
            raise StorageError("Заголовок повреждён: неверное число столбцов или PK")

        columns, pos = [], _HEAD.size
        for _ in range(ncols):
            name, code, length = _COL.unpack_from(raw, pos)
            pos += _COL.size
            if code not in CODE_TYPES:
                raise StorageError(f"Заголовок повреждён: неизвестный код типа {code}")
            try:
                name = name.rstrip(b"\x00").decode("utf-8")
                columns.append(Column(name, make_type(CODE_TYPES[code], length or None)))
            except (UnicodeDecodeError, ValidationError) as e:
                raise StorageError(f"Заголовок повреждён: {e}")
        try:
            return cls(columns, columns[pk_index].name), next_id
        except SchemaError as e:
            raise StorageError(f"Заголовок повреждён: {e}")