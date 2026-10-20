"""database.py — SQLite baza (aiosqlite bilan).

Foydalanuvchi sozlamalari, tarix va kunlik limitlar saqlanadi.

Jadvallar:
  users      — foydalanuvchi sozlamalari (til, ovoz, tezlik)
  history    — oxirgi matnlar (har foydalanuvchi uchun 10 ta)
  daily_usage — kunlik so'rovlar hisobi
"""

import aiosqlite
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "bot.db"

# Sozlama qiymatlari
VALID_LANGUAGES = ("uz", "ru", "en")
VALID_GENDERS = ("male", "female")
VALID_SPEEDS = ("slow", "normal", "fast")

DEFAULT_SETTINGS = {
    "language": "uz",
    "voice_gender": "male",
    "speed": "normal",
    "voice_id": "",
}


async def init_db() -> None:
    """Bazani yaratadi (mavjud bo'lsa — e'tiborsiz qoldiradi)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                language TEXT DEFAULT 'uz',
                voice_gender TEXT DEFAULT 'male',
                speed TEXT DEFAULT 'normal',
                voice_id TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migratsiya: eski bazalarda voice_id ustuni yo'q
        await _ensure_column(db, "users", "voice_id", "TEXT DEFAULT ''")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_usage (
                user_id INTEGER,
                date TEXT,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
        """)
        await db.commit()
        logger.info("Baza tayyor: %s", DB_PATH)


async def _ensure_column(db, table: str, column: str, ddl: str) -> None:
    """Ustun mavjud bo'lmasa — qo'shib qo'yadi (migratsiya)."""
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        rows = await cur.fetchall()
    existing = {r[1] for r in rows}
    if column not in existing:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        logger.info("Migratsiya: %s.%s qo'shildi", table, column)


async def get_settings(user_id: int) -> dict:
    """Foydalanuvchi sozlamalarini oladi. Mavjud bo'lmasa — default."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT language, voice_gender, speed, voice_id FROM users WHERE user_id = ?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return {
                    "language": row["language"],
                    "voice_gender": row["voice_gender"],
                    "speed": row["speed"],
                    "voice_id": row["voice_id"] or "",
                }
    # Foydalanuvchi bazada yo'q — yaratamiz
    await update_settings(user_id, **DEFAULT_SETTINGS)
    return dict(DEFAULT_SETTINGS)


async def update_settings(user_id: int, **kwargs) -> None:
    """Foydalanuvchi sozlamalarini yangilaydi.

    FAQAT berilgan maydonlar o'zgartiriladi — qolganlari saqlanib qoladi.
    Masalan: update_settings(uid, voice_id="x") — til/jins/tezlik tegilmaydi.
    """
    fields: dict = {}

    if "language" in kwargs:
        lang = kwargs["language"]
        if lang not in VALID_LANGUAGES:
            lang = "uz"
        fields["language"] = lang

    if "voice_gender" in kwargs:
        gender = kwargs["voice_gender"]
        if gender not in VALID_GENDERS:
            gender = "male"
        fields["voice_gender"] = gender

    if "speed" in kwargs:
        speed = kwargs["speed"]
        if speed not in VALID_SPEEDS:
            speed = "normal"
        fields["speed"] = speed

    if "voice_id" in kwargs:
        fields["voice_id"] = kwargs["voice_id"] or ""

    if not fields:
        return

    cols = list(fields.keys())
    placeholders = ", ".join("?" for _ in cols)
    assignments = ", ".join(f"{c} = excluded.{c}" for c in cols)
    sql = (
        f"INSERT INTO users (user_id, {', '.join(cols)}) "
        f"VALUES (?, {placeholders}) "
        f"ON CONFLICT(user_id) DO UPDATE SET {assignments}"
    )

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(sql, (user_id, *fields.values()))
        await db.commit()


async def add_history(user_id: int, text: str) -> None:
    """Foydalanuvchi matnini tarixga qo'shadi (oxirgi 10 tasi saqlanadi)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO history (user_id, text) VALUES (?, ?)",
            (user_id, text[:2000])
        )
        # Faqat oxirgi 10 tini qoldiramiz
        await db.execute("""
            DELETE FROM history WHERE user_id = ? AND id NOT IN (
                SELECT id FROM history WHERE user_id = ?
                ORDER BY id DESC LIMIT 10
            )
        """, (user_id, user_id))
        await db.commit()


async def get_history(user_id: int, limit: int = 10) -> list[str]:
    """Foydalanuvchining oxirgi matnlarini oladi (yangisidan boshlab)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT text FROM history WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def check_daily_limit(user_id: int, limit: int) -> bool:
    """Kunlik limitni tekshiradi. True = cheklovsiz, False = limit tugagan."""
    if limit <= 0:
        return True  # Limit yo'q (0 yoki manfiy = cheklovsiz)
    import datetime
    today = datetime.date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT count FROM daily_usage WHERE user_id = ? AND date = ?",
            (user_id, today)
        ) as cur:
            row = await cur.fetchone()
            count = row[0] if row else 0
            return count < limit


async def increment_usage(user_id: int) -> None:
    """Kunlik so'rovlar hisobini oshiradi."""
    import datetime
    today = datetime.date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO daily_usage (user_id, date, count) VALUES (?, ?, 1)
            ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1
        """, (user_id, today))
        await db.commit()


async def get_total_users() -> int:
    """Jami foydalanuvchilar soni (admin uchun)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_today_requests() -> int:
    """Bugungi jami so'rovlar soni (admin uchun)."""
    import datetime
    today = datetime.date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT SUM(count) FROM daily_usage WHERE date = ?",
            (today,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row and row[0] else 0


async def get_total_requests() -> int:
    """Jami so'rovlar soni (admin uchun)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT SUM(count) FROM daily_usage") as cur:
            row = await cur.fetchone()
            return row[0] if row and row[0] else 0


async def get_all_user_ids() -> list[int]:
    """Barcha foydalanuvchi ID larini oladi (broadcast uchun)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def get_user_usage(user_id: int) -> tuple[int, int]:
    """Foydalanuvchining (bugungi, jami) so'rovlar sonini qaytaradi."""
    import datetime
    today = datetime.date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT count FROM daily_usage WHERE user_id = ? AND date = ?",
            (user_id, today),
        ) as cur:
            row = await cur.fetchone()
            today_count = row[0] if row else 0
        async with db.execute(
            "SELECT SUM(count) FROM daily_usage WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            total_count = row[0] if row and row[0] else 0
    return today_count, total_count


async def get_user_history_count(user_id: int) -> int:
    """Foydalanuvchi tarixida nechta matn bor."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM history WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def clear_history(user_id: int) -> None:
    """Foydalanuvchi tarixini tozalaydi."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        await db.commit()
