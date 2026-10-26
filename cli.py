import re
import shlex
import sys

from minidb.database import Database
from minidb.display import format_table
from minidb.errors import MiniDBError, ValidationError

HELP = """Команды:
  tables                              список таблиц
  describe <table>                    столбцы, PK, связи
  create <table> <col:TYPE> ... pk=<col> [fk=<col>:<table>.<col> ...]
        TYPE: INT, FLOAT, STRING(16)
  insert <table> col=val ...
  select <table> [columns a,b] [where col op value]
  update <table> set col=val ... where col op value      (или "all" вместо where)
  delete <table> where col op value                      (или "delete <table> all")
  help, exit
Операторы: = != > < >= <=      Значения с пробелами: name="Fashion MNIST"
Примеры:
  insert experiments dataset_id=1 model_id=2 accuracy=0.9 status=running
  select experiments columns id,accuracy where status = completed
  update experiments set status=completed where id = 3
  delete experiments where id = 3"""

WHERE_RE = re.compile(r"^\s*(\w+)\s*(>=|<=|!=|=|>|<)\s*(.+?)\s*$")
COL_RE = re.compile(r"^(\w+):(\w+)(?:\((\d+)\))?$")
FK_RE = re.compile(r"^(\w+):(\w+)\.(\w+)$")


def fail(msg):
    raise ValidationError(msg)


def split_at(tokens, keyword):
    """[a, b, where, c] -> ([a, b], [c]); без ключевого слова -> (tokens, None)."""
    low = [t.lower() for t in tokens]
    if keyword in low:
        i = low.index(keyword)
        return tokens[:i], tokens[i + 1:]
    return tokens, None


def parse_where(db, table, tokens):
    if not tokens:
        fail("После where нужно условие: столбец оператор значение")
    m = WHERE_RE.match(" ".join(tokens))
    if not m:
        fail(f"Не удалось разобрать условие: {' '.join(tokens)!r}")
    col, op, text = m.groups()
    schema = db.table(table).schema
    if col not in schema.by_name:
        fail(f"Неизвестный столбец: {col!r}")
    return (col, op, schema.by_name[col].type.parse(text))   # текст -> тип столбца


def parse_assignments(db, table, tokens):
    schema = db.table(table).schema
    values = {}
    for tok in tokens:
        key, sep, text = tok.partition("=")
        if not sep or not key:
            fail(f"Ожидалось столбец=значение, получено {tok!r}")
        if key not in schema.by_name:
            fail(f"Неизвестный столбец: {key!r}")
        if key in values:
            fail(f"Столбец {key!r} указан дважды")
        values[key] = schema.by_name[key].type.parse(text)
    return values


# команды
def cmd_help(db, args):
    print(HELP)


def cmd_tables(db, args):
    if not db.tables:
        print("(таблиц нет)")
    for name, t in db.tables.items():
        print(f"{name}: {len(t.select())} записей")


def cmd_describe(db, args):
    if len(args) != 1:
        fail("Использование: describe <table>")
    t = db.table(args[0])
    for c in t.schema.columns:
        type_ = f"STRING({c.type.size})" if c.type.name == "STRING" else c.type.name
        marks = []
        if c.name == t.schema.pk:
            marks.append("PRIMARY KEY")
        for col, ref_table, ref_col in t.schema.fks:
            if col == c.name:
                marks.append(f"-> {ref_table}.{ref_col}")
        print(f"  {c.name:<14}{type_:<12}{' '.join(marks)}")


def cmd_create(db, args):
    if len(args) < 2:
        fail("Использование: create <table> <col:TYPE> ... pk=<col> [fk=col:table.col]")
    name, columns, pk, fks = args[0], [], None, []
    for tok in args[1:]:
        if tok.lower().startswith("pk="):
            pk = tok[3:]
        elif tok.lower().startswith("fk="):
            m = FK_RE.match(tok[3:])
            if not m:
                fail(f"fk ожидает вид столбец:таблица.столбец, получено {tok!r}")
            fks.append(m.groups())
        else:
            m = COL_RE.match(tok)
            if not m:
                fail(f"Столбец ожидается в виде имя:ТИП, получено {tok!r}")
            col, type_, length = m.groups()
            columns.append((col, type_, int(length)) if length else (col, type_))
    if pk is None:
        fail("Укажите pk=<столбец>")
    db.create_table(name, columns, pk, fks)
    print(f"Таблица {name} создана")


def cmd_insert(db, args):
    if len(args) < 2:
        fail("Использование: insert <table> col=val ...")
    table = args[0]
    new_id = db.insert(table, parse_assignments(db, table, args[1:]))
    print(f"Вставлено, {db.table(table).schema.pk} = {new_id}")


def cmd_select(db, args):
    if not args:
        fail("Использование: select <table> [columns a,b] [where col op value]")
    table = args[0]
    head, where_tokens = split_at(args[1:], "where")
    columns = None
    if head:
        if head[0].lower() != "columns" or len(head) < 2:
            fail("Ожидалось: columns a,b")
        columns = " ".join(head[1:]).replace(",", " ").split()
    where = parse_where(db, table, where_tokens) if where_tokens is not None else None
    rows = db.select(table, columns, where)
    shown = columns or [c.name for c in db.table(table).schema.columns]
    print(format_table(rows, shown))


def cmd_update(db, args):
    if not args:
        fail("Использование: update <table> set col=val ... where col op value")
    table = args[0]
    head, where_tokens = split_at(args[1:], "where")
    update_all = False
    if where_tokens is None:
        if head and head[-1].lower() == "all":
            update_all, head = True, head[:-1]
        else:
            fail('UPDATE без условия: добавьте "where ..." или слово all в конце')
    if not head or head[0].lower() != "set":
        fail("После таблицы ожидается set col=val ...")
    values = parse_assignments(db, table, head[1:])
    where = parse_where(db, table, where_tokens) if where_tokens is not None else None
    print(f"Обновлено записей: {db.update(table, where, values, update_all)}")


def cmd_delete(db, args):
    if not args:
        fail("Использование: delete <table> where col op value")
    table = args[0]
    head, where_tokens = split_at(args[1:], "where")
    delete_all = False
    if where_tokens is None:
        if [h.lower() for h in head] == ["all"]:
            delete_all = True
        else:
            fail('DELETE без условия: добавьте "where ..." или слово all')
    elif head:
        fail(f"Лишнее перед where: {' '.join(head)!r}")
    where = parse_where(db, table, where_tokens) if where_tokens is not None else None
    print(f"Удалено записей: {db.delete(table, where, delete_all)}")


COMMANDS = {"help": cmd_help, "tables": cmd_tables, "describe": cmd_describe,
            "create": cmd_create, "insert": cmd_insert, "select": cmd_select,
            "update": cmd_update, "delete": cmd_delete}


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else "data"
    try:
        db = Database(folder)
    except MiniDBError as e:
        print(f"Не удалось открыть базу: {e}")
        return 1
    print(f"MiniDB, база: {folder}/  (help - список команд, exit - выход)")
    while True:
        try:
            line = input("minidb> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        try:
            tokens = shlex.split(line)
        except ValueError as e:                 
            print(f"Ошибка разбора: {e}")
            continue
        cmd = tokens[0].lower()
        if cmd in ("exit", "quit"):
            break
        handler = COMMANDS.get(cmd)
        if handler is None:
            print(f"Неизвестная команда {cmd!r}, см. help")
            continue
        try:
            handler(db, tokens[1:])
        except MiniDBError as e:
            print(f"Ошибка ({type(e).__name__}): {e}")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())