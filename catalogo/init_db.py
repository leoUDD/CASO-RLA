"""Inicializa una base vacía; no importa ni modifica el Excel."""
from pathlib import Path
import sqlite3
from contextlib import closing


def initialize(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(Path(__file__).with_name('sql').joinpath('schema.sql').read_text(encoding='utf-8'))
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        connection.commit()
    return path.resolve()
