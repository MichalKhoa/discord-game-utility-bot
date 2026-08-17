import os
import sqlite3
import aiosqlite
import csv
import io
from typing import Optional, List, Dict, Any

class PlayerDatabase:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(base_dir, 'data', 'players.db')
        else:
            self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    async def init_db(self, auto_migrate: bool = True):
        """Initializes SQLite database and tables with auto-migration for new columns."""
        async with aiosqlite.connect(self.db_path) as db:
            # WAL mode for concurrency safety without locks
            await db.execute('PRAGMA journal_mode=WAL;')
            await db.execute('PRAGMA synchronous=NORMAL;')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS players (
                    fid TEXT PRIMARY KEY,
                    kid TEXT NOT NULL DEFAULT '278',
                    name TEXT,
                    alliance TEXT,
                    discord_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    warning_count INTEGER NOT NULL DEFAULT 0,
                    warning_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Ensure all defined columns exist on pre-existing DB files
            player_columns = {
                "kid": "TEXT NOT NULL DEFAULT '278'",
                "name": "TEXT",
                "alliance": "TEXT",
                "discord_id": "INTEGER",
                "status": "TEXT NOT NULL DEFAULT 'ACTIVE'",
                "warning_count": "INTEGER NOT NULL DEFAULT 0",
                "warning_reason": "TEXT",
                "created_at": "TIMESTAMP",
                "updated_at": "TIMESTAMP",
            }
            await self._ensure_columns(db, "players", player_columns)

            await db.execute('CREATE INDEX IF NOT EXISTS idx_players_status ON players(status)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_players_kid ON players(kid)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_players_alliance ON players(alliance)')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS redeemed_codes (
                    code TEXT PRIMARY KEY,
                    redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    redeemed_by INTEGER,
                    success_count INTEGER DEFAULT 0,
                    total_attempted INTEGER DEFAULT 0
                )
            ''')

            redeemed_columns = {
                "redeemed_at": "TIMESTAMP",
                "redeemed_by": "INTEGER",
                "success_count": "INTEGER DEFAULT 0",
                "total_attempted": "INTEGER DEFAULT 0",
            }
            await self._ensure_columns(db, "redeemed_codes", redeemed_columns)

            await db.commit()

        # Check if tables are empty, if so attempt migrations
        if auto_migrate:
            await self._auto_migrate_if_empty()
            await self._auto_migrate_redeemed_codes()

    async def _ensure_columns(self, db, table_name: str, expected_columns: Dict[str, str]):
        """Dynamically alters table to add any newly added columns if table already existed."""
        cursor = await db.execute(f"PRAGMA table_info({table_name})")
        existing_cols = {row[1] for row in await cursor.fetchall()}
        for col_name, col_def in expected_columns.items():
            if col_name not in existing_cols:
                await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}")

    async def _auto_migrate_if_empty(self):
        """Migrates from playerIDs.txt if the database table has 0 rows."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT COUNT(*) FROM players')
            row = await cursor.fetchone()
            if row and row[0] > 0:
                return

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        txt_path = os.path.join(base_dir, 'playerIDs.txt')
        if not os.path.exists(txt_path):
            txt_path = os.path.join(base_dir, 'data', 'playerIDs.txt')

        if os.path.exists(txt_path):
            await self.import_legacy_txt(txt_path)

    @staticmethod
    def parse_raw_player_text(content: str, default_kingdom: str = "278") -> List[Dict[str, Any]]:
        """
        Parses raw text or CSV containing player IDs.
        Supports:
        - Exported CSV: fid,kid,name,alliance,status,warning_count,warning_reason
        - Standard text with # Alliance headers: 117280427 278 Name or 117280427 Name
        - Comma/tab separated lists: 117280427, 278, Name, NOR
        """
        current_alliance = ""
        players = []

        lines = content.splitlines()
        try:
            csv_reader = list(csv.reader(lines))
        except Exception:
            csv_reader = [l.split(',') for l in lines]

        for raw_line, csv_parts in zip(lines, csv_reader):
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith('#'):
                header = line.lstrip('#').strip()
                if header:
                    current_alliance = header
                continue

            if ',' in raw_line:
                clean_parts = [p.strip() for p in csv_parts if p.strip()]
            else:
                clean_parts = [p.strip() for p in line.replace('\t', ' ').split() if p.strip()]

            if not clean_parts:
                continue

            if clean_parts[0].lower() in ("fid", "player_id", "player id"):
                continue

            if not clean_parts[0].isdigit():
                continue

            fid = clean_parts[0]
            kid = default_kingdom
            name = ""
            alliance = current_alliance
            status = "ACTIVE"
            warning_count = 0
            warning_reason = None

            if ',' in raw_line:
                if len(clean_parts) > 1 and clean_parts[1].isdigit() and int(clean_parts[1]) <= 999999:
                    kid = clean_parts[1]
                    name = clean_parts[2] if len(clean_parts) > 2 else ""
                    if len(clean_parts) > 3:
                        alliance = clean_parts[3] or current_alliance
                    if len(clean_parts) > 4 and clean_parts[4].upper() in ("ACTIVE", "FLAGGED", "DISABLED"):
                        status = clean_parts[4].upper()
                    if len(clean_parts) > 5 and clean_parts[5].isdigit():
                        warning_count = int(clean_parts[5])
                    if len(clean_parts) > 6:
                        warning_reason = clean_parts[6] or None
                elif len(clean_parts) > 1:
                    name = clean_parts[1]
                    if len(clean_parts) > 2:
                        alliance = clean_parts[2] or current_alliance
            else:
                if len(clean_parts) > 1:
                    if clean_parts[1].isdigit() and int(clean_parts[1]) <= 999999:
                        kid = clean_parts[1]
                        name = " ".join(clean_parts[2:]) if len(clean_parts) > 2 else ""
                    else:
                        name = " ".join(clean_parts[1:])

            players.append({
                "fid": fid,
                "kid": kid,
                "name": name,
                "alliance": alliance,
                "status": status,
                "warning_count": warning_count,
                "warning_reason": warning_reason
            })
        return players

    async def import_legacy_txt(self, file_path: str, default_kingdom: str = "278") -> int:
        """Parses legacy playerIDs.txt with # Alliance headers and FID Name lines."""
        if not os.path.exists(file_path):
            return 0

        encodings = ['utf-8-sig', 'utf-8', 'latin-1']
        content = ""
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except Exception:
                continue

        players = self.parse_raw_player_text(content, default_kingdom=default_kingdom)
        if players:
            await self.bulk_upsert_players(players)
        return len(players)

    async def upsert_player(
        self,
        fid: str,
        kid: str = "278",
        name: str = "",
        alliance: str = "",
        discord_id: Optional[int] = None,
        status: str = "ACTIVE",
        warning_count: int = 0,
        warning_reason: Optional[str] = None
    ) -> bool:
        """Inserts or updates a player record."""
        fid = str(fid).strip()
        kid = str(kid).strip() if kid else "278"
        name = name.strip() if name else ""
        alliance = alliance.strip() if alliance else ""

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO players (fid, kid, name, alliance, discord_id, status, warning_count, warning_reason, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(fid) DO UPDATE SET
                    kid = excluded.kid,
                    name = CASE WHEN excluded.name != '' THEN excluded.name ELSE players.name END,
                    alliance = CASE WHEN excluded.alliance != '' THEN excluded.alliance ELSE players.alliance END,
                    discord_id = COALESCE(excluded.discord_id, players.discord_id),
                    status = excluded.status,
                    warning_count = excluded.warning_count,
                    warning_reason = excluded.warning_reason,
                    updated_at = CURRENT_TIMESTAMP
            ''', (fid, kid, name, alliance, discord_id, status, warning_count, warning_reason))
            await db.commit()
        return True

    async def bulk_upsert_players(self, players: List[Dict[str, Any]]) -> int:
        """Bulk upserts a list of player dicts."""
        if not players:
            return 0
        async with aiosqlite.connect(self.db_path) as db:
            for p in players:
                fid = str(p.get("fid", "")).strip()
                if not fid:
                    continue
                kid = str(p.get("kid", "278")).strip() or "278"
                name = str(p.get("name", "")).strip()
                alliance = str(p.get("alliance", "")).strip()
                discord_id = p.get("discord_id")
                status = p.get("status", "ACTIVE")
                warning_count = int(p.get("warning_count", 0))
                warning_reason = p.get("warning_reason")

                await db.execute('''
                    INSERT INTO players (fid, kid, name, alliance, discord_id, status, warning_count, warning_reason, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(fid) DO UPDATE SET
                        kid = excluded.kid,
                        name = CASE WHEN excluded.name != '' THEN excluded.name ELSE players.name END,
                        alliance = CASE WHEN excluded.alliance != '' THEN excluded.alliance ELSE players.alliance END,
                        discord_id = COALESCE(excluded.discord_id, players.discord_id),
                        status = excluded.status,
                        warning_count = excluded.warning_count,
                        warning_reason = excluded.warning_reason,
                        updated_at = CURRENT_TIMESTAMP
                ''', (fid, kid, name, alliance, discord_id, status, warning_count, warning_reason))
            await db.commit()
        return len(players)

    async def update_player_name_and_kid(self, fid: str, name: str, kid: Optional[str] = None) -> bool:
        """Updates a player's in-game nickname and optionally kingdom ID."""
        fid = str(fid).strip()
        name = str(name).strip()
        async with aiosqlite.connect(self.db_path) as db:
            if kid:
                await db.execute('''
                    UPDATE players
                    SET name = ?, kid = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE fid = ?
                ''', (name, str(kid).strip(), fid))
            else:
                await db.execute('''
                    UPDATE players
                    SET name = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE fid = ?
                ''', (name, fid))
            await db.commit()
        return True

    async def get_player(self, fid: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single player by FID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM players WHERE fid = ?', (str(fid).strip(),))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_active_players(self) -> List[Dict[str, Any]]:
        """Returns all players with status = 'ACTIVE' or 'FLAGGED' (not DISABLED)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM players WHERE status != 'DISABLED' ORDER BY CAST(fid AS INTEGER)")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_all_players(self, status: Optional[str] = None, alliance: Optional[str] = None, kingdom: Optional[str] = None) -> List[Dict[str, Any]]:
        """Query players with optional filters."""
        query = 'SELECT * FROM players WHERE 1=1'
        params = []
        if status:
            query += ' AND status = ?'
            params.append(status.upper())
        if alliance:
            query += ' AND alliance = ?'
            params.append(alliance)
        if kingdom:
            query += ' AND kid = ?'
            params.append(str(kingdom).strip())

        query += ' ORDER BY alliance, name, CAST(fid AS INTEGER)'

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def search_players(self, term: str, limit: int = 25) -> List[Dict[str, Any]]:
        """Search players by FID, name, or alliance."""
        term = f"%{term.strip()}%"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT * FROM players
                WHERE fid LIKE ? OR name LIKE ? OR alliance LIKE ?
                ORDER BY name, CAST(fid AS INTEGER)
                LIMIT ?
            ''', (term, term, term, limit))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_flagged_players(self) -> List[Dict[str, Any]]:
        """Returns all flagged or disabled players."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT * FROM players
                WHERE status IN ('FLAGGED', 'DISABLED') OR warning_count > 0
                ORDER BY warning_count DESC, name
            ''')
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def flag_player(self, fid: str, reason: str, auto_disable_threshold: int = 3) -> Dict[str, Any]:
        """Increments warning strikes for a player and flags or disables them."""
        fid = str(fid).strip()
        player = await self.get_player(fid)
        if not player:
            return {"error": "Player not found"}

        new_count = player["warning_count"] + 1
        new_status = "FLAGGED"
        if new_count >= auto_disable_threshold or "ROLE NOT EXIST" in reason.upper():
            new_status = "DISABLED"

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE players
                SET warning_count = ?,
                    warning_reason = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE fid = ?
            ''', (new_count, reason, new_status, fid))
            await db.commit()

        return {"fid": fid, "warning_count": new_count, "status": new_status, "reason": reason}

    async def unflag_player(self, fid: str) -> bool:
        """Clears all warnings and sets status to ACTIVE."""
        fid = str(fid).strip()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                UPDATE players
                SET warning_count = 0,
                    warning_reason = NULL,
                    status = 'ACTIVE',
                    updated_at = CURRENT_TIMESTAMP
                WHERE fid = ?
            ''', (fid,))
            await db.commit()
            return cursor.rowcount > 0

    async def delete_player(self, fid: str) -> bool:
        """Deletes a player by FID."""
        fid = str(fid).strip()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('DELETE FROM players WHERE fid = ?', (fid,))
            await db.commit()
            return cursor.rowcount > 0

    async def prune_flagged(self, min_strikes: int = 3) -> int:
        """Deletes players that exceed strike threshold or are marked DISABLED."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                DELETE FROM players
                WHERE warning_count >= ? OR status = 'DISABLED'
            ''', (min_strikes,))
            await db.commit()
            return cursor.rowcount

    async def get_alliances(self) -> List[str]:
        """Returns distinct alliances."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT DISTINCT alliance FROM players WHERE alliance IS NOT NULL AND alliance != '' ORDER BY alliance")
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

    async def get_stats(self) -> Dict[str, Any]:
        """Returns summary statistics."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT COUNT(*) as total FROM players')
            total = (await cursor.fetchone())['total']

            cursor = await db.execute("SELECT COUNT(*) as active FROM players WHERE status = 'ACTIVE'")
            active = (await cursor.fetchone())['active']

            cursor = await db.execute("SELECT COUNT(*) as flagged FROM players WHERE status = 'FLAGGED'")
            flagged = (await cursor.fetchone())['flagged']

            cursor = await db.execute("SELECT COUNT(*) as disabled FROM players WHERE status = 'DISABLED'")
            disabled = (await cursor.fetchone())['disabled']

            cursor = await db.execute("SELECT kid, COUNT(*) as count FROM players GROUP BY kid ORDER BY count DESC LIMIT 5")
            kingdoms = [dict(r) for r in await cursor.fetchall()]

            cursor = await db.execute("SELECT alliance, COUNT(*) as count FROM players WHERE alliance != '' GROUP BY alliance ORDER BY count DESC LIMIT 5")
            alliances = [dict(r) for r in await cursor.fetchall()]

            return {
                "total": total,
                "active": active,
                "flagged": flagged,
                "disabled": disabled,
                "kingdoms": kingdoms,
                "alliances": alliances
            }

    async def export_csv(self) -> str:
        """Exports all players as a CSV string."""
        players = await self.get_all_players()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["fid", "kid", "name", "alliance", "status", "warning_count", "warning_reason"])
        for p in players:
            writer.writerow([
                p.get("fid", ""),
                p.get("kid", "278"),
                p.get("name", ""),
                p.get("alliance", ""),
                p.get("status", "ACTIVE"),
                p.get("warning_count", 0),
                p.get("warning_reason") or ""
            ])
        return output.getvalue()

    async def _auto_migrate_redeemed_codes(self):
        """Migrates legacy redeemed_codes.txt into redeemed_codes table if empty."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT COUNT(*) FROM redeemed_codes')
            row = await cursor.fetchone()
            if row and row[0] > 0:
                return

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for file_name in ['redeemed_codes.txt', os.path.join('data', 'redeemed_codes.txt')]:
            txt_path = os.path.join(base_dir, file_name) if not file_name.startswith(base_dir) else file_name
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        codes = [line.strip().upper() for line in f if line.strip() and not line.strip().startswith('#')]
                    async with aiosqlite.connect(self.db_path) as db:
                        for code in codes:
                            await db.execute('INSERT OR IGNORE INTO redeemed_codes (code) VALUES (?)', (code,))
                        await db.commit()
                    break
                except Exception as e:
                    print(f"Error migrating redeemed codes from {txt_path}: {e}")

    async def is_code_redeemed(self, code: str) -> Optional[Dict[str, Any]]:
        """Checks if a gift code exists in the database. Returns dict or None."""
        code = str(code).strip().upper()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM redeemed_codes WHERE UPPER(code) = ?', (code,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def log_redeemed_code(self, code: str, redeemed_by: Optional[int] = None, success_count: int = 0, total_attempted: int = 0) -> bool:
        """Logs or updates a successfully redeemed code."""
        code = str(code).strip().upper()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO redeemed_codes (code, redeemed_at, redeemed_by, success_count, total_attempted)
                VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    redeemed_at = CURRENT_TIMESTAMP,
                    redeemed_by = COALESCE(excluded.redeemed_by, redeemed_codes.redeemed_by),
                    success_count = excluded.success_count,
                    total_attempted = excluded.total_attempted
            ''', (code, redeemed_by, success_count, total_attempted))
            await db.commit()
            return True

    async def get_redeemed_codes(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns list of recently redeemed codes."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM redeemed_codes ORDER BY redeemed_at DESC LIMIT ?', (limit,))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def batch_update_kingdom(self, new_kid: str, alliance: Optional[str] = None, fids: Optional[List[str]] = None) -> int:
        """Mass updates Kingdom ID for an alliance or specific list of FIDs."""
        new_kid = str(new_kid).strip()
        if not new_kid or not (alliance or fids):
            return 0

        query = "UPDATE players SET kid = ?, updated_at = CURRENT_TIMESTAMP WHERE "
        params = [new_kid]
        conditions = []
        if alliance:
            conditions.append("alliance = ?")
            params.append(alliance.strip())
        if fids:
            clean_fids = [str(f).strip() for f in fids if str(f).strip().isdigit()]
            if clean_fids:
                placeholders = ",".join("?" for _ in clean_fids)
                conditions.append(f"fid IN ({placeholders})")
                params.extend(clean_fids)

        if not conditions:
            return 0
        query += " OR ".join(conditions)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, params)
            await db.commit()
            return cursor.rowcount

    async def batch_update_alliance(self, new_alliance: str, fids: Optional[List[str]] = None, current_alliance: Optional[str] = None) -> int:
        """Mass updates Alliance tag for specific FIDs or renames an alliance."""
        new_alliance = str(new_alliance).strip()
        if not (fids or current_alliance):
            return 0

        query = "UPDATE players SET alliance = ?, updated_at = CURRENT_TIMESTAMP WHERE "
        params = [new_alliance]
        conditions = []
        if current_alliance:
            conditions.append("alliance = ?")
            params.append(current_alliance.strip())
        if fids:
            clean_fids = [str(f).strip() for f in fids if str(f).strip().isdigit()]
            if clean_fids:
                placeholders = ",".join("?" for _ in clean_fids)
                conditions.append(f"fid IN ({placeholders})")
                params.extend(clean_fids)

        if not conditions:
            return 0
        query += " OR ".join(conditions)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, params)
            await db.commit()
            return cursor.rowcount

    async def batch_delete_players(self, fids: Optional[List[str]] = None, alliance: Optional[str] = None) -> int:
        """Deletes players matching list of FIDs or alliance."""
        if not fids and not alliance:
            return 0

        query = "DELETE FROM players WHERE "
        params = []
        conditions = []
        if alliance:
            conditions.append("alliance = ?")
            params.append(alliance.strip())
        if fids:
            clean_fids = [str(f).strip() for f in fids if str(f).strip().isdigit()]
            if clean_fids:
                placeholders = ",".join("?" for _ in clean_fids)
                conditions.append(f"fid IN ({placeholders})")
                params.extend(clean_fids)

        if not conditions:
            return 0
        query += " OR ".join(conditions)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, params)
            await db.commit()
            return cursor.rowcount

    async def batch_set_status(self, new_status: str, fids: Optional[List[str]] = None, alliance: Optional[str] = None) -> int:
        """Bulk updates status (e.g. ACTIVE, FLAGGED, DISABLED) for matching players."""
        new_status = new_status.strip().upper()
        if not fids and not alliance:
            return 0

        query = "UPDATE players SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE "
        params = [new_status]
        conditions = []
        if alliance:
            conditions.append("alliance = ?")
            params.append(alliance.strip())
        if fids:
            clean_fids = [str(f).strip() for f in fids if str(f).strip().isdigit()]
            if clean_fids:
                placeholders = ",".join("?" for _ in clean_fids)
                conditions.append(f"fid IN ({placeholders})")
                params.extend(clean_fids)

        if not conditions:
            return 0
        query += " OR ".join(conditions)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, params)
            await db.commit()
            return cursor.rowcount


