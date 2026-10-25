import os
from minidb.table import Table
from minidb.errors import IntegrityError, ValidationError, SchemaError

PATH = "test_datasets.tbl"
if os.path.exists(PATH):
    os.remove(PATH)

COLUMNS = [("id", "INT"), ("name", "STRING", 32),
           ("task", "STRING", 16), ("size", "INT")]

# 1. CREATE TABLE + INSERT с авто-ID
t = Table.create(PATH, "datasets", COLUMNS, pk="id")
print(t.insert({"name": "MNIST", "task": "cls", "size": 70000}))       # 1
print(t.insert({"name": "CIFAR-10", "task": "cls", "size": 60000}))    # 2
print(t.insert({"id": 10, "name": "COCO", "task": "det", "size": 1}))  # 10
print(t.insert({"name": "Далее", "task": "cls", "size": 5}))           # 11
t.close()

# 2. «Перезапуск»: схема и данные берутся из файла
t = Table.open(PATH, "datasets")
print([c.name for c in t.schema.columns], "next_id =", t.next_id)
for n, row in t.scan():
    print(n, row)

# 3. Ошибки
def must_fail(exc, row):
    try:
        t.insert(row)
        raise SystemExit(f"Нет ошибки для {row}")
    except exc as e:
        print("ok:", e)

must_fail(IntegrityError, {"id": 1, "name": "X", "task": "t", "size": 1})
must_fail(ValidationError, {"name": "X", "task": "t", "size": "много"})
must_fail(ValidationError, {"name": "X", "task": "t"})
must_fail(ValidationError, {"name": "X", "task": "t", "size": 1, "foo": 1})
assert len(list(t.scan())) == 4        # неудачные вставки ничего не записали
t.close()

try:
    Table.create(PATH, "datasets", COLUMNS, pk="id")
except SchemaError as e:
    print("ok:", e)

print("Все проверки прошли")