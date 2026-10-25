import os
from .errors import IntegrityError, SchemaError, ValidationError
from .query import matches, validate_condition
from .schema import Schema, column_from_spec, HEADER_SIZE
from .storage import Storage


class Table:
    def __init__(self, name, storage, schema, next_id):
        self.name = name
        self.storage = storage
        self.schema = schema
        self.next_id = next_id

    # CREATE TABLE
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

    # открытие существующей
    @classmethod
    def open(cls, path, name):
        if not os.path.exists(path):
            raise SchemaError(f"Таблица {name!r} не найдена")
        with open(path, "rb") as f:
            raw = f.read(HEADER_SIZE)
        schema, next_id = Schema.from_bytes(raw)
        storage = Storage(path, schema.record_size, HEADER_SIZE)
        return cls(name, storage, schema, next_id)

    def _save_header(self):
        self.storage.write_header(self.schema.to_bytes(self.next_id))

    # INSERT
    def insert(self, row):
        if not isinstance(row, dict):
            raise ValidationError(f"Строка должна быть словарём, получено {row!r}")
        row = dict(row)                       # не портим словарь вызывающего
        s = self.schema

        unknown = set(row) - set(s.by_name)
        if unknown:
            raise ValidationError(f"Неизвестные столбцы: {sorted(unknown)}")

        auto = row.get(s.pk) is None
        if auto:
            row[s.pk] = self.next_id          # авто-ID

        missing = [c.name for c in s.columns if c.name not in row]
        if missing:
            raise ValidationError(f"Не указаны столбцы: {missing}")

        data = s.row_to_bytes(row)            # проверка типов всех полей, файл не тронут

        pk_value = row[s.pk]
        if pk_value < 1:
            raise ValidationError(f"{s.pk} должен быть положительным, получено {pk_value}")
        if not auto and any(r[s.pk] == pk_value for _, r in self.scan()):
            raise IntegrityError(f"Дубликат PRIMARY KEY: {s.pk}={pk_value!r} уже есть")

        # сначала счётчик, потом запись: при сбое между ними id лишь пропадёт,
        # а не выдастся повторно
        if pk_value >= self.next_id:
            self.next_id = pk_value + 1
            self._save_header()
        self.storage.append(data)
        return pk_value

    # чтение всех живых записей
    def scan(self):
        """Генератор: (номер записи, словарь) для всех живых записей."""
        for n in range(self.storage.count()):
            alive, row = self.schema.bytes_to_row(self.storage.read(n))
            if alive:
                yield n, row


    def _find(self, where):
        """[(номер, строка)] всех живых записей, подходящих под условие."""
        return [(n, row) for n, row in self.scan() if matches(row, where)]

    # SELECT
    def select(self, columns=None, where=None):
        s = self.schema
        if columns is None:
            columns = [c.name for c in s.columns]
        else:
            if not columns:
                raise ValidationError("Список столбцов пуст")
            unknown = [c for c in columns if c not in s.by_name]
            if unknown:
                raise ValidationError(f"Неизвестные столбцы: {unknown}")
        validate_condition(where, s)

        return [{c: row[c] for c in columns} for _, row in self._find(where)]

    # UPDATE
    def update(self, where, values, update_all=False):
        s = self.schema
        if where is None and not update_all:
            raise ValidationError(
                "UPDATE без условия изменит всю таблицу: укажите where или update_all=True")
        validate_condition(where, s)

        if not values:
            raise ValidationError("Нечего обновлять: values пуст")
        unknown = [c for c in values if c not in s.by_name]
        if unknown:
            raise ValidationError(f"Неизвестные столбцы: {unknown}")
        if s.pk in values:
            raise ValidationError(f"Нельзя менять PRIMARY KEY ({s.pk})")

        updates = []
        for n, row in self._find(where):
            new_row = {**row, **values}
            updates.append((n, s.row_to_bytes(new_row)))

        for n, data in updates:
            self.storage.write(n, data)
        return len(updates)

    # DELETE
    def delete(self, where, delete_all=False):
        s = self.schema
        if where is None and not delete_all:
            raise ValidationError(
                "DELETE без условия удалит все записи: укажите where или delete_all=True")
        validate_condition(where, s)

        targets = self._find(where)
        for n, row in targets:
            self.storage.write(n, s.row_to_bytes(row, alive=False))   # флаг = 0
        return len(targets)

    def close(self):
        self.storage.close()