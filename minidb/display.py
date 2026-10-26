def format_table(rows, columns=None):
    if columns is None:
        if not rows:
            return "(0 строк)"
        columns = list(rows[0])
    widths = [max([len(c)] + [len(str(r[c])) for r in rows]) for c in columns]
    lines = [" | ".join(c.ljust(w) for c, w in zip(columns, widths)),
             "-+-".join("-" * w for w in widths)]
    for r in rows:
        lines.append(" | ".join(str(r[c]).ljust(w) for c, w in zip(columns, widths)))
    lines.append(f"({len(rows)} строк)")
    return "\n".join(lines)