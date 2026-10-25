import shutil
from minidb.database import Database
from minidb.errors import MiniDBError

FOLDER = "demo_data"


def show(title, rows):
    print(f"\n--- {title} ---")
    if not rows:
        print("(пусто)")
        return
    cols = list(rows[0])
    w = [max(len(str(c)), *(len(str(r[c])) for r in rows)) for c in cols]
    print(" | ".join(str(c).ljust(x) for c, x in zip(cols, w)))
    print("-+-".join("-" * x for x in w))
    for r in rows:
        print(" | ".join(str(r[c]).ljust(x) for c, x in zip(cols, w)))


shutil.rmtree(FOLDER, ignore_errors=True)    

print("1. Создаём базу и таблицу")
db = Database(FOLDER)
db.create_table("datasets",
                [("id", "INT"), ("name", "STRING", 32),
                 ("task", "STRING", 16), ("size", "INT")],
                pk="id")

print("2. INSERT")
for name, task, size in [("MNIST", "cls", 70000), ("CIFAR-10", "cls", 60000),
                         ("COCO", "det", 330000), ("IMDB", "nlp", 50000)]:
    new_id = db.insert("datasets", {"name": name, "task": task, "size": size})
    print("   вставлена запись id =", new_id)

show("3. SELECT *", db.select("datasets"))
show("   SELECT name, size WHERE size > 60000",
     db.select("datasets", ["name", "size"], ("size", ">", 60000)))

print("\n4. UPDATE и DELETE")
print("   обновлено:", db.update("datasets", ("name", "=", "MNIST"), {"size": 70001}))
print("   удалено:  ", db.delete("datasets", ("task", "=", "det")))
show("   SELECT *", db.select("datasets"))

print("\n5. Ошибки")
for row in [{"id": 1, "name": "X", "task": "t", "size": 1},    
            {"name": "X", "task": "t", "size": "много"}]:  
    try:
        db.insert("datasets", row)
    except MiniDBError as e:
        print(f"   {type(e).__name__}: {e}")

db.close()

print("\n6. Перезапуск: открываем базу заново")
db = Database(FOLDER)
show("   SELECT * после перезапуска", db.select("datasets"))
db.close()