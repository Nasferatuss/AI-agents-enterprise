"""Schema reflection → compact text description for the agent prompt.

The description is deterministic (sorted tables/columns) so the system prompt
stays byte-stable for prompt caching.
"""

from sqlalchemy import Engine, inspect


def reflect_tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def schema_description(engine: Engine) -> str:
    insp = inspect(engine)
    lines: list[str] = []
    for table in sorted(insp.get_table_names()):
        fks = {
            fk["constrained_columns"][0]: f"{fk['referred_table']}.{fk['referred_columns'][0]}"
            for fk in insp.get_foreign_keys(table)
            if fk["constrained_columns"]
        }
        cols = []
        for col in insp.get_columns(table):
            ref = f" -> {fks[col['name']]}" if col["name"] in fks else ""
            cols.append(f"  {col['name']} {col['type']}{ref}")
        lines.append(f"TABLE {table}\n" + "\n".join(cols))
    return "\n\n".join(lines)
