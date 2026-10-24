import os
from .errors import IntegrityError, SchemaError, StorageError, ValidationError
from .schema import Schema, column_from_spec, HEADER_SIZE
from .storage import Storage


class Table:
    def __init__(self, name, storage, schema, next_id):
        self.name = name
        self.storage = storage
        self.schema = schema
        self.next_id = next_id

    # ---------- CREATE TABLE ----------
    @classmethod
    def create(cls, path, name, columns, pk):
        """columns: [("id","INT"), ("name","STRING",64), ...]"""
        if os.path.exists(path):
            raise SchemaError(f"Таблица {name!r} уже существует")
        schema = Schema([column_from_spec(c) for c in columns], pk)
        storage = Storage(path, schema.record_size, HEADER_SIZE)
        table = cls(name, storage, schema, next_id=1)
        table._save_header()
        return table

    # ---------- открытие существующей ----------
    @classmethod
    def open(cls, path, name):
        if not os.path.exists(path):
            raise SchemaError(f"Таблица {name!r} не найдена")
        # размер записи зависит от схемы, а схема лежит в заголовке,
        # поэтому сначала читаем заголовок «вручную», потом создаём Storage
        with open(path, "rb") as f:
            raw = f.read(HEADER_SIZE)
        schema, next_id = Schema.from_bytes(raw)
        storage = Storage(path, schema.record_size, HEADER_SIZE)
        return cls(name, storage, schema, next_id)

    def _save_header(self):
        self.storage.write_header(self.schema.to_bytes(self.next_id))

    # ---------- INSERT ----------
    def insert(self, row):
        row = dict(row)                       # не портим словарь вызывающего
        s = self.schema

        unknown = set(row) - set(s.by_name)
        if unknown:
            raise ValidationError(f"Неизвестные столбцы: {sorted(unknown)}")

        if row.get(s.pk) is None:             # авто-ID
            row[s.pk] = self.next_id
        else:                                 # PK задан вручную: проверяем дубликат
            if any(r[s.pk] == row[s.pk] for _, r in self.scan()):
                raise IntegrityError(
                    f"Дубликат PRIMARY KEY: {s.pk}={row[s.pk]!r} уже есть")

        missing = [c.name for c in s.columns if c.name not in row]
        if missing:
            raise ValidationError(f"Не указаны столбцы: {missing}")

        data = s.row_to_bytes(row)            # упадёт здесь, если тип не тот,
                                              # а в файл ещё ничего не записано
        self.storage.append(data)

        pk_value = row[s.pk]
        if pk_value >= self.next_id:
            self.next_id = pk_value + 1
            self._save_header()
        return pk_value

    # ---------- чтение (для проверки, полноценный SELECT будет на этапе 3) ----------
    def scan(self):
        """Генератор: (номер записи, словарь) для всех живых записей."""
        for n in range(self.storage.count()):
            alive, row = self.schema.bytes_to_row(self.storage.read(n))
            if alive:
                yield n, row

    def close(self):
        self.storage.close()