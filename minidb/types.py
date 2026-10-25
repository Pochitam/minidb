import math
import struct
from .errors import ValidationError

MAX_STRING = 255


class IntType:
    name = "INT"
    size = 8

    def validate(self, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError(f"INT ожидает целое число, получено {value!r}")
        if not -2**63 <= value < 2**63:
            raise ValidationError(f"INT вне диапазона: {value}")

    def pack(self, value):
        self.validate(value)
        return struct.pack("<q", value)

    def unpack(self, raw):
        return struct.unpack("<q", raw)[0]

    def parse(self, text):
        try:
            return int(text)
        except (ValueError, TypeError):
            raise ValidationError(f"Не удалось прочитать {text!r} как INT")


class FloatType:
    name = "FLOAT"
    size = 8

    def validate(self, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(f"FLOAT ожидает число, получено {value!r}")
        try:
            finite = math.isfinite(value)
        except OverflowError:          
            finite = False
        if not finite:
            raise ValidationError(f"FLOAT должен быть конечным числом, получено {value!r}")

    def pack(self, value):
        self.validate(value)
        return struct.pack("<d", float(value))

    def unpack(self, raw):
        return struct.unpack("<d", raw)[0]

    def parse(self, text):
        try:
            return float(text)
        except (ValueError, TypeError):
            raise ValidationError(f"Не удалось прочитать {text!r} как FLOAT")


class StringType:
    name = "STRING"

    def __init__(self, length=64):
        self.size = length      

    def validate(self, value):
        if not isinstance(value, str):
            raise ValidationError(f"STRING ожидает строку, получено {value!r}")
        if "\x00" in value:
            raise ValidationError("STRING не может содержать нулевой символ")
        if len(value.encode("utf-8")) > self.size:
            raise ValidationError(f"Строка длиннее {self.size} байт: {value!r}")

    def pack(self, value):
        self.validate(value)
        return value.encode("utf-8").ljust(self.size, b"\x00")

    def unpack(self, raw):
        return raw.rstrip(b"\x00").decode("utf-8")

    def parse(self, text):
        return str(text)


def make_type(name, length=None):
    """Создаёт тип по имени: make_type('STRING', 32)."""
    if not isinstance(name, str):
        raise ValidationError(f"Имя типа должно быть строкой, получено {name!r}")
    name = name.upper()
    if name == "INT":
        return IntType()
    if name == "FLOAT":
        return FloatType()
    if name == "STRING":
        length = 64 if length is None else length
        if isinstance(length, bool) or not isinstance(length, int) \
                or not 1 <= length <= MAX_STRING:
            raise ValidationError(f"Длина STRING от 1 до {MAX_STRING}, получено {length!r}")
        return StringType(length)
    raise ValidationError(f"Неизвестный тип: {name}")