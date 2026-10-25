from minidb.types import make_type
from minidb.errors import ValidationError

i, f, s = make_type("INT"), make_type("FLOAT"), make_type("STRING", 16)

# туда-обратно
assert i.unpack(i.pack(42)) == 42
assert i.unpack(i.pack(-7)) == -7
assert f.unpack(f.pack(0.91)) == 0.91
assert s.unpack(s.pack("completed")) == "completed"
assert s.unpack(s.pack("привет")) == "привет"

# размеры фиксированы
assert len(i.pack(1)) == len(i.pack(10**12)) == 8
assert len(s.pack("a")) == len(s.pack("completed")) == 16

# parse
assert i.parse("42") == 42
assert i.parse("-5") == -5
assert f.parse("0.91") == 0.91
assert f.parse("1") == 1.0
assert s.parse("2024") == "2024"

# ошибки
bad_pack = [(i, "abc"), (i, 1.5), (i, True), (f, "x"), (s, 123), (s, "x" * 17)]
for t, bad in bad_pack:
    try:
        t.pack(bad)
        raise SystemExit(f"Нет ошибки pack: {t.name} {bad!r}")
    except ValidationError:
        pass

for t, bad in [(i, "abc"), (i, "1.5"), (i, ""), (f, "abc"), (f, "")]:
    try:
        t.parse(bad)
        raise SystemExit(f"Нет ошибки parse: {t.name} {bad!r}")
    except ValidationError:
        pass

print("Все проверки types прошли")