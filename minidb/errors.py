class MiniDBError(Exception):
    """Базовая ошибка нашей СУБД."""

class ValidationError(MiniDBError):
    """Значение не подходит под тип поля."""

class StorageError(MiniDBError):
    """Проблема с файлом: повреждён, неверный размер записи, выход за границы."""

class SchemaError(MiniDBError):
    """Неверное описание таблицы или столбца."""

class IntegrityError(MiniDBError):
    """Нарушение целостности: дубликат PK, неверный FK."""