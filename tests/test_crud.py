import shutil
import tempfile
from contextlib import contextmanager

from minidb.database import Database
from minidb.errors import IntegrityError, SchemaError, ValidationError

COLUMNS = [("id", "INT"), ("name", "STRING", 16), ("score", "FLOAT")]


@contextmanager
def fresh_db():
    folder = tempfile.mkdtemp()
    db = Database(folder)
    db.create_table("items", COLUMNS, pk="id")
    for name, score in [("a", 0.5), ("b", 0.7), ("c", 0.9), ("d", 0.7)]:
        db.insert("items", {"name": name, "score": score})     # id = 1..4
    try:
        yield db, folder
    finally:
        db.close()
        shutil.rmtree(folder)


def raises(exc, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc:
        return
    raise AssertionError(f"Ожидалась {exc.__name__}")


def ids(rows):
    return [r["id"] for r in rows]


def test_operators():
    with fresh_db() as (db, _):
        sel = lambda op, v: ids(db.select("items", where=("score", op, v)))
        assert sel("=", 0.7) == [2, 4]
        assert sel("!=", 0.7) == [1, 3]
        assert sel(">", 0.7) == [3]
        assert sel("<", 0.7) == [1]
        assert sel(">=", 0.7) == [2, 3, 4]
        assert sel("<=", 0.7) == [1, 2, 4]
        assert sel(">", 0) == [1, 2, 3, 4]
        assert ids(db.select("items", where=("name", "=", "b"))) == [2]
        assert len(db.select("items")) == 4


def test_columns():
    with fresh_db() as (db, _):
        rows = db.select("items", ["name"], ("id", "<=", 2))
        assert rows == [{"name": "a"}, {"name": "b"}]
        assert list(db.select("items", ["score", "id"])[0]) == ["score", "id"]
        raises(ValidationError, db.select, "items", ["nope"])
        raises(ValidationError, db.select, "items", [])


def test_bad_conditions():
    with fresh_db() as (db, _):
        raises(ValidationError, db.select, "items", None, ("nope", "=", 1))
        raises(ValidationError, db.select, "items", None, ("id", "~", 1))
        raises(ValidationError, db.select, "items", None, ("score", "=", "abc"))
        raises(ValidationError, db.select, "items", None, ("id", "=", 1.5))
        raises(ValidationError, db.select, "items", None, ("id", "="))
        raises(SchemaError, db.select, "no_such_table")


def test_update():
    with fresh_db() as (db, _):
        assert db.update("items", ("name", "=", "b"), {"score": 0.99}) == 1
        assert db.select("items", ["score"], ("id", "=", 2)) == [{"score": 0.99}]
        assert db.update("items", ("name", "=", "zzz"), {"score": 1.0}) == 0
        raises(ValidationError, db.update, "items", ("id", "=", 1), {"id": 100})
        raises(ValidationError, db.update, "items", None, {"score": 1.0})
        raises(ValidationError, db.update, "items", ("id", "=", 1), {"nope": 1})
        # неверный тип: ничего не должно измениться
        before = db.select("items")
        raises(ValidationError, db.update, "items", None, {"score": "x"}, True)
        assert db.select("items") == before
        assert db.update("items", None, {"score": 0.1}, update_all=True) == 4


def test_delete():
    with fresh_db() as (db, _):
        assert db.delete("items", ("score", "=", 0.7)) == 2
        assert ids(db.select("items")) == [1, 3]
        raises(ValidationError, db.delete, "items", None)
        assert db.delete("items", ("name", "=", "zzz")) == 0
        assert db.insert("items", {"name": "e", "score": 0.1}) == 5 
        assert db.insert("items", {"id": 2, "name": "f", "score": 0.2}) == 2
        raises(IntegrityError, db.insert, "items", {"id": 2, "name": "g", "score": 0.3})
        assert db.delete("items", None, delete_all=True) == 4
        assert db.select("items") == []


def test_persistence():
    with fresh_db() as (db, folder):
        db.update("items", ("id", "=", 1), {"name": "AAA"})
        db.delete("items", ("id", "=", 4))
        expected = db.select("items")
        db.close()

        db2 = Database(folder)                     # «перезапуск»
        assert db2.select("items") == expected
        assert db2.insert("items", {"name": "new", "score": 0.0}) == 5   # next_id сохранился
        db2.close()


def test_create_table_errors():
    with fresh_db() as (db, _):
        raises(SchemaError, db.create_table, "items", COLUMNS, "id")
        raises(SchemaError, db.create_table, "bad name!", COLUMNS, "id")
        raises(SchemaError, db.create_table, "t2", COLUMNS, "nope")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("Все проверки crud прошли")