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
_FK = struct.Struct("<32s32s32s")   
_FLAG = struct.Struct("<?")
MAX_FKS = 4
MAX_COLUMNS = (HEADER_SIZE - _HEAD.size - 1 - MAX_FKS * _FK.size) // _COL.size   # 17


def _valid_name(n):
    return isinstance(n, str) and NAME_RE.match(n) is not None \
        and len(n.encode("utf-8")) <= NAME_LEN


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
    def __init__(self, columns, pk, fks=None):
        if not columns:
            raise SchemaError("В таблице нет столбцов")
        if len(columns) > MAX_COLUMNS:
            raise SchemaError(f"Не больше {MAX_COLUMNS} столбцов")
        names = [c.name for c in columns]
        for n in names:
            if not _valid_name(n):
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
        self.fks = self._check_fks(fks or [])

    def _check_fks(self, fks):
        if len(fks) > MAX_FKS:
            raise SchemaError(f"Не больше {MAX_FKS} FOREIGN KEY на таблицу")
        result, seen = [], set()
        for fk in fks:
            try:
                col, ref_table, ref_col = fk
            except (TypeError, ValueError):
                raise SchemaError(f"Плохое описание FOREIGN KEY: {fk!r}")
            if col not in self.by_name:
                raise SchemaError(f"FOREIGN KEY: столбец {col!r} не найден")
            if self.by_name[col].type.name != "INT":
                raise SchemaError(f"FOREIGN KEY {col!r} должен быть типа INT")
            if not _valid_name(ref_table) or not _valid_name(ref_col):
                raise SchemaError(f"FOREIGN KEY {col!r}: плохое имя ссылки {ref_table!r}.{ref_col!r}")
            if col in seen:
                raise SchemaError(f"На столбец {col!r} уже задан FOREIGN KEY")
            seen.add(col)
            result.append((col, ref_table, ref_col))
        return result

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
        out.append(bytes([len(self.fks)]))
        for col, ref_table, ref_col in self.fks:
            out.append(_FK.pack(col.encode("utf-8"), ref_table.encode("utf-8"),
                                ref_col.encode("utf-8")))
        return b"".join(out)

    @classmethod
    def from_bytes(cls, raw):
        if len(raw) < HEADER_SIZE:
            raise StorageError("Заголовок слишком короткий")
        magic, next_id, ncols, pk_index = _HEAD.unpack_from(raw, 0)
        if magic != MAGIC:
            raise StorageError("Это не файл MiniDB (неверная сигнатура)")
        if not 1 <= ncols <= MAX_COLUMNS or pk_index >= ncols:
            raise StorageError("Заголовок повреждён: неверное число столбцов или PK")
        try:
            columns, pos = [], _HEAD.size
            for _ in range(ncols):
                name, code, length = _COL.unpack_from(raw, pos)
                pos += _COL.size
                if code not in CODE_TYPES:
                    raise StorageError(f"Заголовок повреждён: неизвестный код типа {code}")
                name = name.rstrip(b"\x00").decode("utf-8")
                columns.append(Column(name, make_type(CODE_TYPES[code], length or None)))

            fk_count = raw[pos]
            pos += 1
            if fk_count > MAX_FKS:
                raise StorageError("Заголовок повреждён: неверное число FOREIGN KEY")
            fks = []
            for _ in range(fk_count):
                parts = _FK.unpack_from(raw, pos)
                pos += _FK.size
                fks.append(tuple(p.rstrip(b"\x00").decode("utf-8") for p in parts))
            return cls(columns, columns[pk_index].name, fks), next_id
        except StorageError:
            raise
        except (UnicodeDecodeError, ValidationError, SchemaError, struct.error) as e:
            raise StorageError(f"Заголовок повреждён: {e}")