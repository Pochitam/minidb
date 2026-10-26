import os
import re
from .errors import (IntegrityError, MiniDBError, SchemaError,
                     StorageError, ValidationError)
from .table import Table

EXT = ".tbl"
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
NAME_LEN = 32


class Database:

    def __init__(self, folder):
        if os.path.exists(folder) and not os.path.isdir(folder):
            raise StorageError(f"{folder!r} не папка")
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self.tables = {}
        try:
            for fname in sorted(os.listdir(folder)):
                if fname.endswith(EXT):
                    name = fname[:-len(EXT)]
                    try:
                        self.tables[name] = Table.open(self._path(name), name)
                    except MiniDBError as e:
                        raise StorageError(f"Файл {fname}: {e}") from e
        except Exception:
            self.close()                 
            raise

    def _path(self, name):
        return os.path.join(self.folder, name + EXT)

    # таблицы
    def create_table(self, name, columns, pk, foreign_keys=None):
        """foreign_keys: [("dataset_id", "datasets", "id"), ...]"""
        if not isinstance(name, str) or not NAME_RE.match(name) or len(name) > NAME_LEN:
            raise SchemaError(f"Плохое имя таблицы: {name!r}")
        if name in self.tables:
            raise SchemaError(f"Таблица {name!r} уже существует")

        fks = list(foreign_keys or [])
        for fk in fks:
            try:
                col, ref_table, ref_col = fk
            except (TypeError, ValueError):
                raise SchemaError(f"Плохое описание FOREIGN KEY: {fk!r}")
            ref = self.tables.get(ref_table)
            if ref is None:
                raise SchemaError(
                    f"FOREIGN KEY {col!r}: таблица {ref_table!r} не найдена (создайте её раньше)")
            if ref.schema.pk != ref_col:
                raise SchemaError(
                    f"FOREIGN KEY должен ссылаться на PRIMARY KEY {ref_table}.{ref.schema.pk}, "
                    f"а не на {ref_col!r}")

        self.tables[name] = Table.create(self._path(name), name, columns, pk, fks)
        return self.tables[name]

    def table(self, name):
        if name not in self.tables:
            raise SchemaError(f"Таблица {name!r} не найдена")
        return self.tables[name]

    def _check_fk(self, table, values):
        if not isinstance(values, dict):
            return                                   # ошибку типа выдаст сама Table
        for col, ref_table, ref_col in table.schema.fks:
            value = values.get(col)
            if value is None:
                continue                             # «не указан» поймает Table
            table.schema.by_name[col].type.validate(value)
            if not self.tables[ref_table].exists(value):
                raise IntegrityError(
                    f"FOREIGN KEY: в {ref_table} нет записи с {ref_col}={value!r} "
                    f"(столбец {table.name}.{col})")

    def _check_not_referenced(self, table, where):
        """Запрет удалять записи, на которые кто-то ссылается."""
        referencing = [(other, col)
                       for other in self.tables.values()
                       for col, ref_table, _ in other.schema.fks
                       if ref_table == table.name]
        if not referencing:
            return
        pk = table.schema.pk
        ids = {r[pk] for r in table.select([pk], where)}
        if not ids:
            return
        for other, col in referencing:
            for _, row in other.scan():
                if row[col] in ids:
                    raise IntegrityError(
                        f"Нельзя удалить {table.name}.{pk}={row[col]}: на запись ссылается "
                        f"{other.name}.{other.schema.pk}={row[other.schema.pk]} (столбец {col})")

    # CRUD
    def insert(self, table, row):
        t = self.table(table)
        self._check_fk(t, row)
        return t.insert(row)

    def select(self, table, columns=None, where=None):
        return self.table(table).select(columns, where)

    def update(self, table, where, values, update_all=False):
        t = self.table(table)
        self._check_fk(t, values)
        return t.update(where, values, update_all)

    def delete(self, table, where, delete_all=False):
        t = self.table(table)
        if where is None and not delete_all:
            raise ValidationError(
                "DELETE без условия удалит все записи: укажите where или delete_all=True")
        self._check_not_referenced(t, where)
        return t.delete(where, delete_all)

    # закрытие
    def close(self):
        for t in self.tables.values():
            t.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()