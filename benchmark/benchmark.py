"""Замеры времени операций MiniDB на разных объёмах данных.

  python3 benchmark.py                        размеры 1000, 10000, 100000
  python3 benchmark.py --sizes 1000 5000      свои размеры
Результат печатается и сохраняется в docs/benchmark_results.md.
"""
import argparse
import os
import platform
import random
import shutil
import sys
import tempfile
import time

import seed
from minidb.database import Database


def ms(fn):
    t0 = time.perf_counter()
    fn()
    return (time.perf_counter() - t0) * 1000


def avg_ms(fn, args):
    return sum(ms(lambda a=a: fn(a)) for a in args) / len(args)


def run(n, repeats):
    folder = tempfile.mkdtemp(prefix="minidb_bench_")
    try:
        db = Database(folder)
        seed.create_tables(db)
        for name, task, size in seed.DATASETS:
            db.insert("datasets", {"name": name, "task": task, "size": size})
        for name, version in seed.MODELS:
            db.insert("models", {"name": name, "version": version})

        rng = random.Random(42)
        rows = [{"dataset_id": rng.randint(1, 5), "model_id": rng.randint(1, 5),
                 "accuracy": round(rng.uniform(0.6, 0.98), 2),
                 "status": rng.choice(seed.STATUSES)} for _ in range(n)]

        def insert_all():
            for r in rows:                       # INSERT с проверкой FOREIGN KEY
                db.insert("experiments", r)
        insert_total = ms(insert_all)
        size_kb = os.path.getsize(os.path.join(folder, "experiments.tbl")) / 1024

        ids = rng.sample(range(1, n + 1), min(repeats * 3, n))
        sel_ids, upd_ids, del_ids = ids[:repeats], ids[repeats:2 * repeats], ids[2 * repeats:]
        res = dict(
            n=n, size_kb=size_kb,
            insert_total=insert_total / 1000, insert_one=insert_total / n,
            select_all=avg_ms(lambda _: db.select("experiments"), range(3)),
            select_id=avg_ms(lambda i: db.select("experiments", None, ("id", "=", i)), sel_ids),
            select_filter=avg_ms(
                lambda v: db.select("experiments", ["id", "accuracy"], ("accuracy", ">", v)),
                [0.9] * 3),
            update_id=avg_ms(lambda i: db.update("experiments", ("id", "=", i),
                                                 {"status": "completed"}), upd_ids),
            delete_id=avg_ms(lambda i: db.delete("experiments", ("id", "=", i)), del_ids),
            insert_manual=avg_ms(lambda i: db.insert("experiments", {
                "id": n + 1000 + i, "dataset_id": 1, "model_id": 1,
                "accuracy": 0.5, "status": "running"}), range(repeats)),
        )
        db.close()
        return res
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def render(results, repeats):
    lines = [
        "# Результаты benchmark",
        "",
        f"Окружение: Python {platform.python_version()}, {platform.system()} {platform.machine()}.",
        f"Таблица `experiments` с N записями (datasets и models по 5). Время операций над одной "
        f"записью усреднено по {repeats} случайным id, SELECT с фильтром и SELECT * по 3 запускам.",
        "",
        "| Записей | Файл, КБ | INSERT всех, с | INSERT одной, мс | SELECT *, мс | "
        "SELECT WHERE id=?, мс | SELECT WHERE accuracy>0.9, мс | UPDATE по id, мс | "
        "DELETE по id, мс | INSERT с ручным id, мс |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(
            f"| {r['n']:,} | {r['size_kb']:.0f} | {r['insert_total']:.2f} | {r['insert_one']:.3f} | "
            f"{r['select_all']:.1f} | {r['select_id']:.1f} | {r['select_filter']:.1f} | "
            f"{r['update_id']:.1f} | {r['delete_id']:.1f} | {r['insert_manual']:.1f} |")
    lines += [
        "",
        "Поиск, UPDATE, DELETE и проверка дубликата при ручном id идут полным проходом по файлу, "
        "поэтому их время растёт пропорционально числу записей. INSERT с авто-ID не зависит от "
        "размера таблицы: запись дописывается в конец файла.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", type=int, nargs="+", default=[1000, 10000, 100000])
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--out", default=os.path.join("docs", "benchmark_results.md"))
    args = ap.parse_args()

    results = []
    for n in args.sizes:
        print(f"... {n:,} записей", file=sys.stderr, flush=True)
        results.append(run(n, args.repeats))
    text = render(results, args.repeats)
    print(text)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Сохранено в {args.out}", file=sys.stderr)