import os
import shutil
import tempfile
from contextlib import contextmanager

import seed
from minidb.database import Database
from minidb.errors import IntegrityError, MiniDBError, SchemaError, ValidationError
from minidb.schema import Schema, column_from_spec

GOOD = {"dataset_id": 1, "model_id": 1, "accuracy": 0.9, "status": "completed"}


def raises(exc, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc as e:
        assert isinstance(e, MiniDBError)
        return
    raise AssertionError(f"Ожидалась {exc.__name__}")


@contextmanager
def small_db():
    """Три таблицы: 3 датасета и 2 модели, experiments пусты."""
    folder = tempfile.mkdtemp()
    db = Database(folder)
    seed.create_tables(db)
    for n in ("D1", "D2", "D3"):
        db.insert("datasets", {"name": n, "task": "cls", "size": 10})
    for n in ("M1", "M2"):
        db.insert("models", {"name": n, "version": "1"})
    try:
        yield db, folder
    finally:
        db.close()
        shutil.rmtree(folder)


def test_insert_fk():
    with small_db() as (db, _):
        assert db.insert("experiments", GOOD) == 1
        raises(IntegrityError, db.insert, "experiments", {**GOOD, "dataset_id": 99})
        raises(IntegrityError, db.insert, "experiments", {**GOOD, "model_id": 99})
        raises(IntegrityError, db.insert, "experiments", {**GOOD, "dataset_id": 0})
        raises(ValidationError, db.insert, "experiments", {**GOOD, "dataset_id": "1"})
        raises(ValidationError, db.insert, "experiments", {**GOOD, "dataset_id": None})
        raises(ValidationError, db.insert, "experiments",
               {"model_id": 1, "accuracy": 0.5, "status": "x"})        # нет dataset_id
        assert len(db.select("experiments")) == 1
        assert db.insert("experiments", GOOD) == 2        # неудачные вставки не сжигают id


def test_update_fk():
    with small_db() as (db, _):
        db.insert("experiments", GOOD)
        assert db.update("experiments", ("id", "=", 1), {"dataset_id": 2}) == 1
        raises(IntegrityError, db.update, "experiments", ("id", "=", 1), {"dataset_id": 99})
        raises(IntegrityError, db.update, "experiments", ("id", "=", 1), {"model_id": 99})
        raises(ValidationError, db.update, "experiments", ("id", "=", 1), {"dataset_id": "x"})
        assert db.select("experiments", ["dataset_id"], ("id", "=", 1)) == [{"dataset_id": 2}]
        assert db.update("experiments", ("id", "=", 1), {"status": "failed"}) == 1


def test_delete_restrict():
    with small_db() as (db, _):
        db.insert("experiments", GOOD)                              # D1, M1
        db.insert("experiments", {**GOOD, "model_id": 2})           # D1, M2
        db.insert("experiments", {**GOOD, "dataset_id": 2})         # D2, M1

        raises(IntegrityError, db.delete, "datasets", ("id", "=", 1))
        raises(IntegrityError, db.delete, "models", ("id", "=", 1))
        # одна из подходящих записей (D1) занята: не удаляется ничего, даже свободная D3
        raises(IntegrityError, db.delete, "datasets", ("size", "<", 100))
        assert len(db.select("datasets")) == 3
        raises(ValidationError, db.delete, "datasets", None)

        assert db.delete("datasets", ("id", "=", 3)) == 1           # на D3 никто не ссылается
        assert db.delete("experiments", ("dataset_id", "=", 1)) == 2
        assert db.delete("datasets", ("id", "=", 1)) == 1           # теперь можно
        raises(IntegrityError, db.delete, "datasets", ("id", "=", 2))
        assert db.delete("experiments", None, delete_all=True) == 1
        assert db.delete("datasets", None, delete_all=True) == 1
        assert db.delete("models", None, delete_all=True) == 2


def test_create_table_fk_errors():
    folder = tempfile.mkdtemp()
    try:
        db = Database(folder)
        db.create_table("a", [("id", "INT"), ("name", "STRING", 8)], "id")
        cols = [("id", "INT"), ("a_id", "INT"), ("txt", "STRING", 8)]
        for bad in ([("a_id", "nope", "id")],              # нет таблицы
                    [("a_id", "a", "name")],               # не PK
                    [("zzz", "a", "id")],                  # нет столбца
                    [("txt", "a", "id")],                  # столбец не INT
                    ["xy"], [5],                           # мусор
                    [("a_id", "a", "id"), ("a_id", "a", "id")]):   # повтор
            raises(SchemaError, db.create_table, "b", cols, "id", bad)
        assert "b" not in db.tables
        assert not os.path.exists(os.path.join(folder, "b.tbl"))
        db.create_table("b", cols, "id", [("a_id", "a", "id")])
        db.close()
    finally:
        shutil.rmtree(folder)


def test_persistence_fk():
    with small_db() as (db, folder):
        db.insert("experiments", GOOD)
        db.close()
        db2 = Database(folder)                              # «перезапуск»
        assert db2.table("experiments").schema.fks == [
            ("dataset_id", "datasets", "id"), ("model_id", "models", "id")]
        raises(IntegrityError, db2.insert, "experiments", {**GOOD, "dataset_id": 99})
        raises(IntegrityError, db2.delete, "datasets", ("id", "=", 1))
        db2.close()


def test_header_roundtrip():
    cols = [column_from_spec(c) for c in
            [("id", "INT"), ("a_id", "INT"), ("b_id", "INT"), ("t", "STRING", 20)]]
    fks = [("a_id", "alpha", "id"), ("b_id", "beta", "pk")]
    schema = Schema(cols, "id", fks)
    raw = schema.to_bytes(7).ljust(1024, b"\x00")
    back, next_id = Schema.from_bytes(raw)
    assert next_id == 7 and back.fks == fks and back.pk == "id"
    assert [c.name for c in back.columns] == ["id", "a_id", "b_id", "t"]


def test_seed():
    folder = tempfile.mkdtemp()
    try:
        db = seed.build(folder)
        ds = {r["id"] for r in db.select("datasets")}
        md = {r["id"] for r in db.select("models")}
        exps = db.select("experiments")
        assert (len(ds), len(md), len(exps)) == (5, 5, 20)
        for r in exps:
            assert r["dataset_id"] in ds and r["model_id"] in md
            assert 0 <= r["accuracy"] <= 1
        assert exps[0] == {"id": 1, "dataset_id": 1, "model_id": 1,
                           "accuracy": 0.91, "status": "completed"}
        db.close()
        db2 = seed.build(folder)                            # повторный запуск = те же данные
        assert db2.select("experiments") == exps
        db2.close()
    finally:
        shutil.rmtree(folder)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("Все проверки fk прошли")