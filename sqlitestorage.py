import json
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable, Dict, Optional

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import (
    BaseEventIsolation,
    BaseStorage,
    StateType,
    StorageKey,
)

DEFAULT_SQLITE_LOCK_TIMEOUT = 60

_JsonLoads = Callable[..., Any]
_JsonDumps = Callable[..., str]


class SQLiteStorage(BaseStorage):
    def __init__(
        self,
        db_path: str,
        state_ttl: Optional[int] = None,
        data_ttl: Optional[int] = None,
        json_loads: _JsonLoads = json.loads,
        json_dumps: _JsonDumps = json.dumps,
    ) -> None:
        self.db_path = db_path
        self.state_ttl = state_ttl
        self.data_ttl = data_ttl
        self.json_loads = json_loads
        self.json_dumps = json_dumps

        self._create_tables()

    def _create_tables(self) -> None:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Create states table
        c.execute('''
            CREATE TABLE IF NOT EXISTS states (
                chat_id INTEGER,
                user_id INTEGER,
                state TEXT,
                PRIMARY KEY (chat_id, user_id)
            )
        ''')

        # Create data table
        c.execute('''
            CREATE TABLE IF NOT EXISTS data (
                chat_id INTEGER,
                user_id INTEGER,
                data TEXT,
                PRIMARY KEY (chat_id, user_id)
            )
        ''')

        # Create locks table
        c.execute('''
            CREATE TABLE IF NOT EXISTS locks (
                chat_id INTEGER,
                user_id INTEGER,
                expiry_time INTEGER,
                PRIMARY KEY (chat_id, user_id)
            )
        ''')

        conn.commit()
        conn.close()

    async def close(self) -> None:
        pass

    async def set_state(
        self,
        key: StorageKey,
        state: StateType = None,
    ) -> None:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        if state is None:
            c.execute('DELETE FROM states WHERE chat_id=? AND user_id=?', (key.chat_id, key.user_id))
        else:
            c.execute('INSERT OR REPLACE INTO states (chat_id, user_id, state) VALUES (?, ?, ?)',
                      (key.chat_id, key.user_id, state.state if isinstance(state, State) else state))

        conn.commit()
        conn.close()

    async def get_state(
        self,
        key: StorageKey,
    ) -> Optional[str]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('SELECT state FROM states WHERE chat_id=? AND user_id=?', (key.chat_id, key.user_id))
        result = c.fetchone()

        conn.close()

        return result[0] if result else None

    async def set_data(
        self,
        key: StorageKey,
        data: Dict[str, Any],
    ) -> None:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        if not data:
            c.execute('DELETE FROM data WHERE chat_id=? AND user_id=?', (key.chat_id, key.user_id))
        else:
            c.execute('INSERT OR REPLACE INTO data (chat_id, user_id, data) VALUES (?, ?, ?)',
                      (key.chat_id, key.user_id, self.json_dumps(data)))

        conn.commit()
        conn.close()

    async def get_data(
        self,
        key: StorageKey,
    ) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('SELECT data FROM data WHERE chat_id=? AND user_id=?', (key.chat_id, key.user_id))
        result = c.fetchone()

        conn.close()

        return self.json_loads(result[0]) if result else {}


class SQLiteEventIsolation(BaseEventIsolation):
    def __init__(self, db_path: str, lock_timeout: int = DEFAULT_SQLITE_LOCK_TIMEOUT) -> None:
        self.db_path = db_path
        self.lock_timeout = lock_timeout

    @asynccontextmanager
    async def lock(self, key: StorageKey) -> AsyncGenerator[None, None]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('INSERT OR IGNORE INTO locks (chat_id, user_id, expiry_time) VALUES (?, ?, ?)',
                  (key.chat_id, key.user_id, self._get_expiry_time()))

        try:
            conn.commit()
            yield None
        finally:
            c.execute('DELETE FROM locks WHERE chat_id=? AND user_id=?', (key.chat_id, key.user_id))
            conn.commit()
            conn.close()

    async def close(self) -> None:
        pass

    def _get_expiry_time(self) -> int:
        # Calculate expiry time based on current time and lock timeout
        return int(time.time() + self.lock_timeout)
