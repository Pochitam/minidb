import os
from .errors import StorageError


class Storage:
    def __init__(self, path, record_size, header_size=1024):
        self.path = path
        self.record_size = record_size
        self.header_size = header_size

        exists = os.path.exists(path)
        self.file = open(path, "r+b" if exists else "w+b")

        if not exists:
            self.file.write(b"\x00" * header_size)
            self.file.flush()
        else:
            try:
                self._check_file()
            except StorageError:
                self.file.close()  
                raise

    def _check_file(self):
        size = os.fstat(self.file.fileno()).st_size
        if size < self.header_size:
            raise StorageError(f"Файл {self.path} повреждён: нет заголовка")
        if (size - self.header_size) % self.record_size != 0:
            raise StorageError(
                f"Файл {self.path} повреждён: размер данных не кратен размеру записи")

    # ---------- заголовок ----------
    def read_header(self):
        self.file.seek(0)
        return self.file.read(self.header_size)

    def write_header(self, data):
        if len(data) > self.header_size:
            raise StorageError(
                f"Заголовок {len(data)} байт не влезает в {self.header_size}")
        self.file.seek(0)
        self.file.write(data.ljust(self.header_size, b"\x00"))
        self.file.flush()

    # ---------- записи ----------
    def offset(self, n):
        """Смещение записи с номером n от начала файла."""
        return self.header_size + n * self.record_size

    def count(self):
        """Сколько записей в файле (включая помеченные удалёнными)."""
        size = os.fstat(self.file.fileno()).st_size
        return (size - self.header_size) // self.record_size

    def _check_data(self, data):
        if len(data) != self.record_size:
            raise StorageError(
                f"Запись {len(data)} байт, ожидалось {self.record_size}")

    def _check_number(self, n):
        if not 0 <= n < self.count():
            raise StorageError(f"Записи №{n} не существует")

    def append(self, data):
        """Дописывает запись в конец, возвращает её номер."""
        self._check_data(data)
        n = self.count()
        self.file.seek(self.offset(n))
        self.file.write(data)
        self.file.flush()
        return n

    def read(self, n):
        self._check_number(n)
        self.file.seek(self.offset(n))
        return self.file.read(self.record_size)

    def write(self, n, data):
        """Перезаписывает существующую запись на месте."""
        self._check_data(data)
        self._check_number(n)
        self.file.seek(self.offset(n))
        self.file.write(data)
        self.file.flush()

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()