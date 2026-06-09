from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class SQLiteKV:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with sqlite3.connect(str(self.path), timeout=10) as db:
            db.execute("create table if not exists kv (namespace text, name text, value text, primary key(namespace, name))")
            db.commit()

    def get_json(self, namespace: str, name: str) -> dict[str, Any] | None:
        with self._lock, sqlite3.connect(str(self.path), timeout=10) as db:
            row = db.execute("select value from kv where namespace = ? and name = ?", (namespace, name)).fetchone()
        if not row:
            return None
        try:
            return json.loads(str(row[0]))
        except json.JSONDecodeError:
            return None

    def put_json(self, namespace: str, name: str, value: dict[str, Any]) -> None:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
        with self._lock, sqlite3.connect(str(self.path), timeout=10) as db:
            db.execute("delete from kv where namespace = ? and name = ?", (namespace, name))
            db.execute("insert into kv(namespace, name, value) values (?, ?, ?)", (namespace, name, payload))
            db.commit()
