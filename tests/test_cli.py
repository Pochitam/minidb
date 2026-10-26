import os
import shutil
import subprocess
import sys
import tempfile

import seed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_cli(folder, commands):
    result = subprocess.run([sys.executable, "cli.py", folder], cwd=ROOT,
                            input="\n".join(commands) + "\nexit\n",
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    return result.stdout


def test_cli_session():
    folder = tempfile.mkdtemp()
    try:
        seed.build(folder).close()
        out = run_cli(folder, [
            "tables",
            "select experiments where accuracy > 0.9",
            'select datasets columns name,size where name = "COCO"',
            "insert experiments dataset_id=1 model_id=1 accuracy=0.5 status=running",
            "insert experiments dataset_id=99 model_id=1 accuracy=0.5 status=running",
            "update experiments set status=completed where id = 21",
            "delete datasets where id = 1",
            "delete experiments where id = 21",
            "delete experiments",
            "insert experiments dataset_id=abc model_id=1 accuracy=0.5 status=x",
            "select nope",
            "foo",
        ])
        assert "experiments: 20 записей" in out
        assert "0.91" in out
        assert "COCO" in out
        assert "Вставлено, id = 21" in out
        assert "IntegrityError" in out                 
        assert "Обновлено записей: 1" in out
        assert "Удалено записей: 1" in out
        assert out.count("ValidationError") >= 2       
        assert "SchemaError" in out                   
        assert "Неизвестная команда" in out
    finally:
        shutil.rmtree(folder)


def test_cli_persistence():
    folder = tempfile.mkdtemp()
    try:
        seed.build(folder).close()
        run_cli(folder, ["insert models name=NewNet version=9"])
        out = run_cli(folder, ["select models where name = NewNet"])   
        assert "NewNet" in out
    finally:
        shutil.rmtree(folder)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("Все проверки cli прошли")