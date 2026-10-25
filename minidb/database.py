import os
import re
from .errors import MiniDBError, SchemaError, StorageError
from .table import Table

EXT = ".tbl"
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
    def create_table(self, name, columns, pk):
        if not NAME_RE.match(name):
            raise SchemaError(f"Плохое имя таблицы: {name!r}")
        if name in self.tables:
            raise SchemaError(f"Таблица {name!r} уже существует")
        self.tables[name] = Table.create(self._path(name), name, columns, pk)
        return self.tables[name]

    def table(self, name):
        if name not in self.tables:
            raise SchemaError(f"Таблица {name!r} не найдена")
        return self.tables[name]

    # CRUD
    def insert(self, table, row):
        return self.table(table).insert(row)

    def select(self, table, columns=None, where=None):
        return self.table(table).select(columns, where)

    def update(self, table, where, values, update_all=False):
        return self.table(table).update(where, values, update_all)

    def delete(self, table, where, delete_all=False):
        return self.table(table).delete(where, delete_all)

    # закрытие
    def close(self):
        for t in self.tables.values():
            t.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()