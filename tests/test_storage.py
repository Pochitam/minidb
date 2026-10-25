import os
import struct
from minidb.types import make_type
from minidb.storage import Storage
from minidb.errors import StorageError

PATH = "test_experiments.tbl"
if os.path.exists(PATH):
    os.remove(PATH)

i, f, s = make_type("INT"), make_type("FLOAT"), make_type("STRING", 16)
flag = struct.Struct("<?")
RECORD_SIZE = 1 + i.size * 3 + f.size + s.size      # 49


def make_record(id_, ds, md, acc, status, alive=True):
    return (flag.pack(alive) + i.pack(id_) + i.pack(ds) + i.pack(md)
            + f.pack(acc) + s.pack(status))


def parse_record(raw):
    return (flag.unpack(raw[0:1])[0], i.unpack(raw[1:9]), i.unpack(raw[9:17]),
            i.unpack(raw[17:25]), f.unpack(raw[25:33]), s.unpack(raw[33:49]))


# 1. Создаём файл и пишем три записи
with Storage(PATH, RECORD_SIZE) as st:
    assert st.count() == 0
    assert st.append(make_record(1, 1, 1, 0.91, "completed")) == 0
    assert st.append(make_record(2, 1, 2, 0.88, "completed")) == 1
    assert st.append(make_record(3, 2, 1, 0.76, "running")) == 2
    st.write_header(b"hello header")

# 2. «Перезапуск»: открываем заново
with Storage(PATH, RECORD_SIZE) as st:
    assert st.count() == 3
    assert st.read_header().rstrip(b"\x00") == b"hello header"
    print(parse_record(st.read(0)))
    print(parse_record(st.read(2)))

    # 3. UPDATE на месте: новая точность у записи 2
    st.write(2, make_record(3, 2, 1, 0.80, "completed"))

    # 4. DELETE: меняем только байт флага у записи 1
    raw = bytearray(st.read(1))
    raw[0] = 0
    st.write(1, bytes(raw))

# 3-й запуск: проверяем, что изменения сохранились
with Storage(PATH, RECORD_SIZE) as st:
    for n in range(st.count()):
        print(n, parse_record(st.read(n)))

# 5. Ошибки
with Storage(PATH, RECORD_SIZE) as st:
    for bad in (lambda: st.read(99), lambda: st.append(b"short")):
        try:
            bad()
            raise SystemExit("Должна быть StorageError")
        except StorageError:
            pass

print("Все проверки прошли")