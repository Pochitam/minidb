import struct
from .errors import ValidationError

class IntType():
    name = "INT"
    size = 8

    def validate(self, value):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError(f"INT ожидает целое число, а вы мне {value!r}")
        if not -2**63 <= value< 2**63:
            raise ValidationError(f"Соре число должно быть в промежутке [-2**63, 2**63]")
    
    def pack(self, value):
        self.validate(value)
        return struct.pack("<q", value)
    
    def unpack(self, raw):
        return struct.unpack("<q", raw)[0]

class FloatType():
    name="FLOAT"
    size = 8

    def validate(self, value):
        if not( isinstance(value, (float, int))) or isinstance(value, bool):
            raise ValidationError(f"FLOAT ожидает число, а вы мне {value!r}")
    
    def pack(self, value):
        self.validate(value)
        return struct.pack("<d", value)
    
    def unpack(self, raw):
        return struct.unpack("<d", raw)[0]

class StrType():
    name = "STRING"
    def __init__(self, size=64):
        self.size = size

    def validation(self, value):
        if not(isinstance(value, str)):
            raise ValidationError(f"STR ожидает строку, а у вас {value!r}")
        if len(value.encode("utf-8")) > self.size:
            raise ValidationError(f"Строка длиннее {self.size} байт: {value!r}") 
    
    def pack(self, value):
        self.validation(value)
        return value.encode("utf-8").ljust(self.size, b"\x00")

    def unpack(self,raw):
        return raw.rstrip(b"\x00").decode("utf-8")