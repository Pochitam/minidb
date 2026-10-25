import os
import shutil
import tempfile

from minidb.database import Database
from minidb.errors import (IntegrityError, MiniDBError, SchemaError,
                           StorageError, ValidationError)
from minidb.types import make_type

COLUMNS = [("id", "INT"), ("name", "STRING", 8), ("score", "FLOAT")]


def raises(exc, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc as e:
        assert isinstance(e, MiniDBError)     
        return
    raise AssertionError(f"Ожидалась {exc.__name__}")


class Env:
    def __enter__(self):
        self.folder = tempfile.mkdtemp()
        self.db = Database(self.folder)
        self.db.create_table("t", COLUMNS, pk="id")
        return self

    def __exit__(self, *exc):
        self.db.close()
        shutil.rmtree(self.folder)


def test_types_edge_cases():
    f, s, i = make_type("FLOAT"), make_type("STRING", 8), make_type("INT")
    for bad in (float("nan"), float("inf"), -float("inf"), 10**400, True, "1"):
        raises(ValidationError, f.pack, bad)
    raises(ValidationError, s.pack, "a\x00b")
    raises(ValidationError, s.pack, "123456789")
    raises(ValidationError, s.pack, "ёёёёё")       
    raises(ValidationError, i.pack, 2**63)
    raises(ValidationError, i.pack, None)
    for length in (0, -1, 256, 1.5, True):
        raises(ValidationError, make_type, "STRING", length)
    raises(ValidationError, make_type, "BOOL")
    raises(ValidationError, make_type, 5)


def test_insert_errors():
    with Env() as e:
        db = e.db
        raises(ValidationError, db.insert, "t", {"name": "a", "score": "x"})
        raises(ValidationError, db.insert, "t", {"name": 5, "score": 1.0})
        raises(ValidationError, db.insert, "t", {"name": "a"})          
        raises(ValidationError, db.insert, "t", {"name": "a", "score": 1, "zzz": 1})
        raises(ValidationError, db.insert, "t", {"id": 0, "name": "a", "score": 1})
        raises(ValidationError, db.insert, "t", {"id": -3, "name": "a", "score": 1})
        raises(ValidationError, db.insert, "t", {"id": "7", "name": "a", "score": 1})
        raises(ValidationError, db.insert, "t", {"id": True, "name": "a", "score": 1})
        raises(ValidationError, db.insert, "t", "не словарь")
        assert db.select("t") == []                   


def test_primary_key():
    with Env() as e:
        db = e.db
        assert db.insert("t", {"name": "a", "score": 1}) == 1
        assert db.insert("t", {"id": 10, "name": "b", "score": 1}) == 10
        assert db.insert("t", {"name": "c", "score": 1}) == 11     
        raises(IntegrityError, db.insert, "t", {"id": 10, "name": "d", "score": 1})
        raises(IntegrityError, db.insert, "t", {"id": 1, "name": "d", "score": 1})
        assert len(db.select("t")) == 3


def test_create_table_errors():
    with Env() as e:
        db = e.db
        raises(SchemaError, db.create_table, "t", COLUMNS, "id")            
        raises(SchemaError, db.create_table, "x y", COLUMNS, "id")          
        raises(SchemaError, db.create_table, "a", [], "id")                 
        raises(SchemaError, db.create_table, "a", COLUMNS, "nope")          
        raises(SchemaError, db.create_table, "a", COLUMNS, "name")           
        raises(SchemaError, db.create_table, "a", [("id", "INT"), ("id", "INT")], "id")
        raises(SchemaError, db.create_table, "a", [("my col", "INT")], "my col")
        raises(SchemaError, db.create_table, "a", [("1id", "INT")], "1id")
        raises(SchemaError, db.create_table, "a", [("id", "BOOL")], "id")
        raises(SchemaError, db.create_table, "a", [("id", "STRING", 0)], "id")
        raises(SchemaError, db.create_table, "a", ["id"], "id")              
        raises(SchemaError, db.table, "missing")
        assert "a" not in db.tables                                          


def test_corrupted_files():
    folder = tempfile.mkdtemp()
    try:
        #чужой файл с расширением .tbl
        with open(os.path.join(folder, "junk.tbl"), "wb") as f:
            f.write(b"hello, I am not a table" * 100)
        raises(StorageError, Database, folder)
        os.remove(os.path.join(folder, "junk.tbl"))

        open(os.path.join(folder, "empty.tbl"), "wb").close()
        raises(StorageError, Database, folder)
        os.remove(os.path.join(folder, "empty.tbl"))

        #обрезанный файл
        db = Database(folder)
        db.create_table("t", COLUMNS, pk="id")
        db.insert("t", {"name": "a", "score": 1})
        db.close()
        path = os.path.join(folder, "t.tbl")
        with open(path, "r+b") as f:
            f.truncate(os.path.getsize(path) - 5)
        raises(StorageError, Database, folder)

        #неверное число столбцов
        with open(path, "r+b") as f:
            f.seek(0)
            f.write(b"MDB1" + b"\x00" * 8 + bytes([200, 0]))
        raises(StorageError, Database, folder)
    finally:
        shutil.rmtree(folder)


def test_database_path_is_file():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    try:
        raises(StorageError, Database, path)
    finally:
        os.remove(path)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("Все проверки errors прошли")