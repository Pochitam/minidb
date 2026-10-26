import os
import random
import sys

from minidb.database import Database

DATASETS = [("MNIST", "cls", 70000), ("CIFAR-10", "cls", 60000),
            ("COCO", "det", 330000), ("IMDB", "nlp", 50000),
            ("SQuAD", "qa", 100000)]
MODELS = [("ResNet", "1.0"), ("BERT", "1.1"), ("ViT", "1.0"),
          ("LSTM", "2.0"), ("YOLO", "5.0")]
STATUSES = ["completed", "completed", "completed", "running", "failed"]


def create_tables(db):
    db.create_table("datasets",
                    [("id", "INT"), ("name", "STRING", 32),
                     ("task", "STRING", 16), ("size", "INT")], pk="id")
    db.create_table("models",
                    [("id", "INT"), ("name", "STRING", 32),
                     ("version", "STRING", 16)], pk="id")
    db.create_table("experiments",
                    [("id", "INT"), ("dataset_id", "INT"), ("model_id", "INT"),
                     ("accuracy", "FLOAT"), ("status", "STRING", 16)], pk="id",
                    foreign_keys=[("dataset_id", "datasets", "id"),
                                  ("model_id", "models", "id")])


def fill(db, experiments=20, seed=42):
    rng = random.Random(seed)                    
    for name, task, size in DATASETS:
        db.insert("datasets", {"name": name, "task": task, "size": size})
    for name, version in MODELS:
        db.insert("models", {"name": name, "version": version})

    rows = [(1, 1, 0.91, "completed"), (1, 2, 0.88, "completed"), (2, 1, 0.76, "running")]
    for i in range(len(rows), experiments):
        rows.append((rng.randint(1, len(DATASETS)), rng.randint(1, len(MODELS)),
                     round(rng.uniform(0.60, 0.98), 2), rng.choice(STATUSES)))
    for dataset_id, model_id, accuracy, status in rows:
        db.insert("experiments", {"dataset_id": dataset_id, "model_id": model_id,
                                  "accuracy": accuracy, "status": status})


def build(folder):
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            if f.endswith(".tbl"):
                os.remove(os.path.join(folder, f))
    db = Database(folder)
    create_tables(db)
    fill(db)
    return db


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "data"
    db = build(folder)
    for name, t in db.tables.items():
        print(f"{name}: {len(t.select())} записей")
    db.close()
    print(f"База создана в папке {folder}/")