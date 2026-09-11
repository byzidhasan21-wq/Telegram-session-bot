import asyncio
import json
import logging
import sqlite3
import aiosqlite
import os
import sys
import random
import socks
import csv
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
import zipfile
import re
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardButton, BotCommand, BufferedInputFile
)

from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from pyrogram import Client as PyroClient
from pyrogram.errors import SessionPasswordNeeded

# ---------- API & BOT CONFIG ----------
API_ID = 36365225
API_HASH = "79e6068bfc6a4a05e27847086255b4bd"
BOT_TOKEN = "8914818871:AAHEi5JTZanvyNM394I7mQSrxxovaLhHTpk"
INITIAL_ADMIN_ID = 6513728669

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- Bot & Dispatcher Setup (aiogram 3) ----------
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)


# ---------- aiogram 3 keyboard compatibility (supports .add / row_width like aiogram 2) ----------
from aiogram.types import InlineKeyboardMarkup as _RawInlineKeyboardMarkup

class InlineKeyboardMarkup(_RawInlineKeyboardMarkup):
    """Drop-in helper so old keyboard.add() and row_width=N keep working on aiogram 3."""
    def __init__(self, row_width: int = None, inline_keyboard=None, **kwargs):
        super().__init__(inline_keyboard=list(inline_keyboard or []), **kwargs)
        object.__setattr__(self, "_row_width", row_width or 1)
        object.__setattr__(self, "_buf", [])

    def add(self, *buttons):
        buf = object.__getattribute__(self, "_buf")
        rw = object.__getattribute__(self, "_row_width")
        for b in buttons:
            buf.append(b)
            if len(buf) >= rw:
                self.inline_keyboard.append(list(buf))
                buf.clear()
        return self

    def row(self, *buttons):
        self._flush()
        self.inline_keyboard.append(list(buttons))
        return self

    def _flush(self):
        buf = object.__getattribute__(self, "_buf")
        if buf:
            self.inline_keyboard.append(list(buf))
            buf.clear()

    def model_dump(self, **kwargs):
        self._flush()
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs):
        self._flush()
        return super().model_dump_json(**kwargs)



# ---------- Enhanced safe_md ----------
def safe_md(text: str) -> str:
    if not text:
        return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return ''.join(f"\\{char}" if char in escape_chars else char for char in text)

# ---------- Database Setup ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(SCRIPT_DIR, "bot_data.db")
PYROGRAM_WORKDIR = os.path.join(SCRIPT_DIR, "pyrogram_sessions")
os.makedirs(PYROGRAM_WORKDIR, exist_ok=True)

# ---------- Country Info ----------
COUNTRY_INFO = {
    "880": ("🇧🇩", "Bangladesh"),
    "91": ("🇮🇳", "India"),
    "92": ("🇵🇰", "Pakistan"),
    "94": ("🇱🇰", "Sri Lanka"),
    "977": ("🇳🇵", "Nepal"),
    "1": ("🇺🇸", "USA"),
    "44": ("🇬🇧", "UK"),
    "49": ("🇩🇪", "Germany"),
    "33": ("🇫🇷", "France"),
    "7": ("🇷🇺", "Russia"),
    "86": ("🇨🇳", "China"),
    "81": ("🇯🇵", "Japan"),
    "82": ("🇰🇷", "South Korea"),
    "62": ("🇮🇩", "Indonesia"),
    "60": ("🇲🇾", "Malaysia"),
    "66": ("🇹🇭", "Thailand"),
    "84": ("🇻🇳", "Vietnam"),
    "234": ("🇳🇬", "Nigeria"),
    "254": ("🇰🇪", "Kenya"),
    "27": ("🇿🇦", "South Africa"),
    "55": ("🇧🇷", "Brazil"),
    "52": ("🇲🇽", "Mexico"),
    "54": ("🇦🇷", "Argentina"),
    "56": ("🇨🇱", "Chile"),
    "57": ("🇨🇴", "Colombia"),
    "20": ("🇪🇬", "Egypt"),
    "212": ("🇲🇦", "Morocco"),
    "213": ("🇩🇿", "Algeria"),
    "216": ("🇹🇳", "Tunisia"),
    "218": ("🇱🇾", "Libya"),
    "964": ("🇮🇶", "Iraq"),
    "966": ("🇸🇦", "Saudi Arabia"),
    "971": ("🇦🇪", "UAE"),
    "973": ("🇧🇭", "Bahrain"),
    "965": ("🇰🇼", "Kuwait"),
    "974": ("🇶🇦", "Qatar"),
    "968": ("🇴🇲", "Oman"),
    "98": ("🇮🇷", "Iran"),
    "90": ("🇹🇷", "Turkey"),
    "380": ("🇺🇦", "Ukraine"),
    "48": ("🇵🇱", "Poland"),
    "31": ("🇳🇱", "Netherlands"),
    "32": ("🇧🇪", "Belgium"),
    "41": ("🇨🇭", "Switzerland"),
    "46": ("🇸🇪", "Sweden"),
    "47": ("🇳🇴", "Norway"),
    "45": ("🇩🇰", "Denmark"),
    "358": ("🇫🇮", "Finland"),
    "351": ("🇵🇹", "Portugal"),
    "34": ("🇪🇸", "Spain"),
    "39": ("🇮🇹", "Italy"),
    "30": ("🇬🇷", "Greece"),
    "36": ("🇭🇺", "Hungary"),
    "40": ("🇷🇴", "Romania"),
    "359": ("🇧🇬", "Bulgaria"),
    "420": ("🇨🇿", "Czech Republic"),
    "421": ("🇸🇰", "Slovakia"),
    "386": ("🇸🇮", "Slovenia"),
    "385": ("🇭🇷", "Croatia"),
    "381": ("🇷🇸", "Serbia"),
    "387": ("🇧🇦", "Bosnia"),
    "389": ("🇲🇰", "North Macedonia"),
    "355": ("🇦🇱", "Albania"),
    "372": ("🇪🇪", "Estonia"),
    "371": ("🇱🇻", "Latvia"),
    "370": ("🇱🇹", "Lithuania"),
    "375": ("🇧🇾", "Belarus"),
    "373": ("🇲🇩", "Moldova"),
    "374": ("🇦🇲", "Armenia"),
    "994": ("🇦🇿", "Azerbaijan"),
    "995": ("🇬🇪", "Georgia"),
    "7": ("🇰🇿", "Kazakhstan"),
    "998": ("🇺🇿", "Uzbekistan"),
    "993": ("🇹🇲", "Turkmenistan"),
    "996": ("🇰🇬", "Kyrgyzstan"),
    "992": ("🇹🇯", "Tajikistan"),
    "975": ("🇧🇹", "Bhutan"),
    "960": ("🇲🇻", "Maldives"),
    "856": ("🇱🇦", "Laos"),
    "855": ("🇰🇭", "Cambodia"),
    "95": ("🇲🇲", "Myanmar"),
    "63": ("🇵🇭", "Philippines"),
    "65": ("🇸🇬", "Singapore"),
    "673": ("🇧🇳", "Brunei"),
    "670": ("🇹🇱", "Timor-Leste"),
    "61": ("🇦🇺", "Australia"),
    "64": ("🇳🇿", "New Zealand"),
    "679": ("🇫🇯", "Fiji"),
    "675": ("🇵🇬", "Papua New Guinea"),
    "686": ("🇰🇮", "Kiribati"),
    "692": ("🇲🇭", "Marshall Islands"),
    "691": ("🇫🇲", "Micronesia"),
    "674": ("🇳🇷", "Nauru"),
    "677": ("🇸🇧", "Solomon Islands"),
    "678": ("🇻🇺", "Vanuatu"),
    "685": ("🇼🇸", "Samoa"),
    "676": ("🇹🇴", "Tonga"),
    "682": ("🇨🇰", "Cook Islands"),
    "690": ("🇹🇰", "Tokelau"),
    "683": ("🇳🇺", "Niue"),
    "684": ("🇦🇸", "American Samoa"),
    "687": ("🇳🇨", "New Caledonia"),
    "689": ("🇵🇫", "French Polynesia"),
    "688": ("🇹🇻", "Tuvalu"),
    "681": ("🇼🇫", "Wallis and Futuna"),
}

# ---------- Async DB context manager ----------
# Concurrent login limit (max simultaneous Telethon/Pyrogram clients)
LOGIN_SEMAPHORE = asyncio.Semaphore(40)  # allow ~40 parallel logins safely
SESSION_CREATE_LOCK = asyncio.Lock()

@asynccontextmanager
async def db_connection():
    conn = await aiosqlite.connect(DB_NAME, timeout=30)
    conn.row_factory = aiosqlite.Row
    try:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA busy_timeout=30000")
        yield conn
    finally:
        await conn.close()

# ---------- Database Initialization ----------
async def init_db():
    try:
        if not os.access(SCRIPT_DIR, os.W_OK):
            logger.error(f"Directory {SCRIPT_DIR} is not writable.")
            sys.exit(1)
        async with db_connection() as conn:
            # Existing tables...
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT UNIQUE NOT NULL,
                    lib TEXT NOT NULL,
                    session_string TEXT,
                    device_info TEXT,
                    twofa_enabled INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    proxy TEXT,
                    device_model TEXT,
                    system_version TEXT,
                    app_version TEXT,
                    spam_status TEXT DEFAULT 'Unknown',
                    added_by INTEGER,
                    status TEXT DEFAULT 'New',
                    api_id INTEGER,
                    api_hash TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS countries (
                    country_code TEXT PRIMARY KEY,
                    country_name TEXT,
                    is_allowed INTEGER DEFAULT 1,
                    flag_emoji TEXT,
                    price REAL DEFAULT 0,
                    capacity INTEGER DEFAULT 0,
                    current_count INTEGER DEFAULT 0,
                    api_id INTEGER,
                    api_hash TEXT,
                    proxy TEXT,
                    confirmation_timer INTEGER DEFAULT 5
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS wallets (
                    user_id INTEGER PRIMARY KEY,
                    balance REAL DEFAULT 0
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    type TEXT,
                    amount REAL,
                    status TEXT DEFAULT 'completed',
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # New table for multiple API credentials per country
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS country_apis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    country_code TEXT NOT NULL,
                    api_id INTEGER NOT NULL,
                    api_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (country_code) REFERENCES countries(country_code) ON DELETE CASCADE
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS country_proxies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    country_code TEXT NOT NULL,
                    proxy TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (country_code) REFERENCES countries(country_code) ON DELETE CASCADE
                )
            """)
            await conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (INITIAL_ADMIN_ID,))

            # Add new columns for claim/pin features
            cursor = await conn.execute("PRAGMA table_info(accounts)")
            existing_cols = [row[1] for row in await cursor.fetchall()]
            new_account_cols = {
                'claim_status': "TEXT DEFAULT 'pending'",
                'claim_retry_time': 'TIMESTAMP',
                'claim_attempts': 'INTEGER DEFAULT 0',
                'pinned_message_id': 'INTEGER',
                'pinned_chat_id': 'INTEGER',
                'api_id': 'INTEGER',
                'api_hash': 'TEXT'
            }
            for col, col_type in new_account_cols.items():
                if col not in existing_cols:
                    await conn.execute(f"ALTER TABLE accounts ADD COLUMN {col} {col_type}")

            # User verification columns (captcha + group join)
            cursor_u = await conn.execute("PRAGMA table_info(users)")
            user_cols = [row[1] for row in await cursor_u.fetchall()]
            new_user_cols = {
                'captcha_passed': 'INTEGER DEFAULT 0',
                'captcha_attempts': 'INTEGER DEFAULT 0',
                'group_joined': 'INTEGER DEFAULT 0',
            }
            for col, col_type in new_user_cols.items():
                if col not in user_cols:
                    await conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")

            # Create indexes
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_phone ON accounts(phone)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_added_by ON accounts(added_by)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_claim_status ON accounts(claim_status)")
            
            # ---------- Global Bot Toggle ----------
            await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_enabled', '1')")
            # ---------------------------------------------

            await conn.commit()
            logger.info(f"Database initialized at {DB_NAME}")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        sys.exit(1)

# ---------- Country API Management ----------
async def get_country_apis(country_code: str):
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT id, api_id, api_hash FROM country_apis WHERE country_code = ?", (country_code,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def add_country_api(country_code: str, api_id: int, api_hash: str):
    async with db_connection() as conn:
        await conn.execute("INSERT INTO country_apis (country_code, api_id, api_hash) VALUES (?, ?, ?)",
                           (country_code, api_id, api_hash))
        await conn.commit()

async def remove_country_api(api_id: int):
    async with db_connection() as conn:
        await conn.execute("DELETE FROM country_apis WHERE id = ?", (api_id,))
        await conn.commit()

async def get_country_proxies(country_code: str):
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT id, proxy FROM country_proxies WHERE country_code = ?", (country_code,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def add_country_proxy(country_code: str, proxy: str):
    async with db_connection() as conn:
        await conn.execute("INSERT INTO country_proxies (country_code, proxy) VALUES (?, ?)", (country_code, proxy))
        await conn.commit()

async def remove_country_proxy(proxy_id: int):
    async with db_connection() as conn:
        await conn.execute("DELETE FROM country_proxies WHERE id = ?", (proxy_id,))
        await conn.commit()

# ---------- Lib Toggle Settings ----------
async def get_lib_toggle(lib_name: str) -> bool:
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT value FROM settings WHERE key = ?", (f"lib_enabled_{lib_name.lower()}",))
        row = await cursor.fetchone()
        return row['value'] == '1' if row else True

async def set_lib_toggle(lib_name: str, enabled: bool):
    val = '1' if enabled else '0'
    async with db_connection() as conn:
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"lib_enabled_{lib_name.lower()}", val))
        await conn.commit()

# ---------- Support ID ----------
async def get_support_id():
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT value FROM settings WHERE key = 'support_id'")
        row = await cursor.fetchone()
        return row['value'] if row else "@Support"

async def set_support_id(support_id):
    async with db_connection() as conn:
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('support_id', ?)", (support_id,))
        await conn.commit()

# ---------- Country Helpers ----------
async def get_country_code_from_phone(phone: str) -> str:
    phone = phone.strip().replace(' ', '').replace('-', '')
    if phone.startswith('+'):
        phone = phone[1:]
    for length in [3, 2, 1]:
        if len(phone) >= length:
            code = phone[:length]
            async with db_connection() as conn:
                cursor = await conn.execute("SELECT * FROM countries WHERE country_code = ?", (code,))
                row = await cursor.fetchone()
                if row:
                    return code
    return phone[:3]

async def get_country_name_from_code(code: str) -> str:
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT country_name FROM countries WHERE country_code = ?", (code,))
        row = await cursor.fetchone()
        if row and row['country_name']:
            return row['country_name']
    return code

async def is_country_allowed(phone: str) -> bool:
    code = await get_country_code_from_phone(phone)
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT is_allowed FROM countries WHERE country_code = ?", (code,))
        row = await cursor.fetchone()
        if row is not None:
            return bool(row['is_allowed'])
        return False

async def set_country_status(code: str, is_allowed: int, name: str = None):
    flag = None
    if code in COUNTRY_INFO:
        flag, auto_name = COUNTRY_INFO[code]
        if not name:
            name = auto_name
    async with db_connection() as conn:
        await conn.execute("""
            INSERT OR REPLACE INTO countries (country_code, country_name, is_allowed, flag_emoji)
            VALUES (?, ?, ?, ?)
        """, (code, name, is_allowed, flag))
        await conn.commit()

async def get_country_config(code: str):
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM countries WHERE country_code = ?", (code,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def update_country_config(code: str, **kwargs):
    set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
    values = list(kwargs.values()) + [code]
    async with db_connection() as conn:
        await conn.execute(f"UPDATE countries SET {set_clause} WHERE country_code = ?", values)
        await conn.commit()

async def get_all_countries():
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM countries ORDER BY country_code")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_country_flag(code: str) -> str:
    if code in COUNTRY_INFO:
        return COUNTRY_INFO[code][0]
    return "🏳️"

# ---------- Wallet Helpers ----------
async def get_user_balance(user_id: int) -> float:
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT balance FROM wallets WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            return row['balance']
        else:
            await conn.execute("INSERT OR IGNORE INTO wallets (user_id, balance) VALUES (?, 0)", (user_id,))
            await conn.commit()
            return 0.0

async def set_user_balance(user_id: int, amount: float):
    async with db_connection() as conn:
        await conn.execute("INSERT OR REPLACE INTO wallets (user_id, balance) VALUES (?, ?)", (user_id, amount))
        await conn.commit()

async def add_balance(user_id: int, amount: float, description="Admin adjustment"):
    current = await get_user_balance(user_id)
    new_balance = current + amount
    await set_user_balance(user_id, new_balance)
    await create_transaction(user_id, 'credit', amount, 'completed', description)

async def deduct_balance(user_id: int, amount: float, description="Account submission"):
    current = await get_user_balance(user_id)
    if current < amount:
        return False
    new_balance = current - amount
    await set_user_balance(user_id, new_balance)
    await create_transaction(user_id, 'debit', amount, 'completed', description)
    return True

async def create_transaction(user_id: int, type: str, amount: float, status: str = 'completed', description: str = ""):
    async with db_connection() as conn:
        await conn.execute("""
            INSERT INTO transactions (user_id, type, amount, status, description)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, type, amount, status, description))
        await conn.commit()

async def get_user_transactions(user_id: int, limit=20):
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def request_withdrawal(user_id: int, amount: float, method: str = "Manual"):
    current = await get_user_balance(user_id)
    if amount > current:
        return False, "Insufficient balance"
    # Immediately deduct balance from user wallet
    new_balance = current - amount
    await set_user_balance(user_id, new_balance)
    async with db_connection() as conn:
        await conn.execute("""
            INSERT INTO transactions (user_id, type, amount, status, description)
            VALUES (?, 'withdrawal', ?, 'pending', ?)
        """, (user_id, amount, f"Withdrawal request via {method}"))
        await conn.commit()
    return True, "Withdrawal request submitted. Balance deducted."

async def get_pending_withdrawals():
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM transactions WHERE type='withdrawal' AND status='pending' ORDER BY created_at")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def process_withdrawal(transaction_id: int, approve: bool):
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
        tx = await cursor.fetchone()
        if not tx:
            return False, None, None, None
        if tx['status'] != 'pending':
            return False, None, None, None
        user_id = tx['user_id']
        amount = tx['amount']
        description = tx['description'] if ('description' in tx.keys() and tx['description']) else ''
        if approve:
            # Balance already deducted at request time
            await conn.execute("UPDATE transactions SET status='approved' WHERE id = ?", (transaction_id,))
        else:
            # Reject → refund balance
            await conn.execute("UPDATE wallets SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            await conn.execute("UPDATE transactions SET status='rejected' WHERE id = ?", (transaction_id,))
        await conn.commit()
        return True, user_id, amount, description

# ---------- Account Status ----------
async def update_account_status(phone: str, status: str):
    async with db_connection() as conn:
        await conn.execute("UPDATE accounts SET status = ? WHERE phone = ?", (status, phone))
        await conn.commit()

# ---------- User Management ----------
async def add_or_update_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    async with db_connection() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name
        """, (user_id, username, first_name, last_name))
        await conn.execute("INSERT OR IGNORE INTO wallets (user_id, balance) VALUES (?, 0)", (user_id,))
        await conn.commit()

async def get_user_row(user_id: int):
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def set_user_captcha_passed(user_id: int, passed: bool = True):
    async with db_connection() as conn:
        await conn.execute(
            "UPDATE users SET captcha_passed = ?, captcha_attempts = 0 WHERE user_id = ?",
            (1 if passed else 0, user_id)
        )
        await conn.commit()

async def increment_captcha_attempts(user_id: int) -> int:
    async with db_connection() as conn:
        await conn.execute(
            "UPDATE users SET captcha_attempts = COALESCE(captcha_attempts, 0) + 1 WHERE user_id = ?",
            (user_id,)
        )
        await conn.commit()
        cursor = await conn.execute("SELECT captcha_attempts FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row['captcha_attempts'] if row else 1

async def reset_captcha_attempts(user_id: int):
    async with db_connection() as conn:
        await conn.execute("UPDATE users SET captcha_attempts = 0 WHERE user_id = ?", (user_id,))
        await conn.commit()

async def set_user_group_joined(user_id: int, joined: bool = True):
    async with db_connection() as conn:
        await conn.execute(
            "UPDATE users SET group_joined = ? WHERE user_id = ?",
            (1 if joined else 0, user_id)
        )
        await conn.commit()

async def is_user_in_force_group(user_id: int) -> bool:
    """Check if user is member of the User Join Group (not admin session group)."""
    group_id = await get_user_join_group_id()
    if not group_id:
        return True  # no force-join group set → skip
    try:
        member = await bot.get_chat_member(group_id, user_id)
        status = member.status if hasattr(member, 'status') else str(member)
        if status in ('member', 'administrator', 'creator', 'restricted'):
            return True
        return False
    except Exception as e:
        logger.warning(f"User join group membership check failed for {user_id}: {e}")
        return False

# backward-compatible alias used in older code paths
async def is_user_in_admin_group(user_id: int) -> bool:
    return await is_user_in_force_group(user_id)

def generate_math_captcha():
    a = random.randint(1, 20)
    b = random.randint(1, 20)
    op = random.choice(['+', '-', '*'])
    if op == '+':
        ans = a + b
    elif op == '-':
        # keep non-negative
        if b > a:
            a, b = b, a
        ans = a - b
    else:
        a = random.randint(2, 12)
        b = random.randint(2, 10)
        ans = a * b
    question = f"{a} {op} {b} = ?"
    return question, ans

async def get_user_join_group_invite():
    """Return (group_id, title, invite_link) for User Join Group."""
    group_id = await get_user_join_group_id()
    if not group_id:
        return None, None, None
    title = "Join Group"
    link = None
    try:
        chat = await bot.get_chat(group_id)
        title = chat.title or f"Group {group_id}"
        # 1) public username
        if getattr(chat, 'username', None):
            link = f"https://t.me/{chat.username}"
        # 2) existing invite_link
        if not link and getattr(chat, 'invite_link', None):
            link = chat.invite_link
        # 3) create new invite (bot must be admin with invite permission)
        if not link:
            try:
                inv = await bot.create_chat_invite_link(
                    chat_id=group_id,
                    name="BotUserJoin",
                    creates_join_request=False
                )
                link = inv.invite_link
            except Exception as e:
                logger.warning(f"create_chat_invite_link failed: {e}")
                try:
                    inv = await bot.export_chat_invite_link(group_id)
                    link = inv if isinstance(inv, str) else getattr(inv, 'invite_link', None)
                except Exception as e2:
                    logger.warning(f"export_chat_invite_link failed: {e2}")
    except Exception as e:
        logger.warning(f"get_user_join_group_invite failed: {e}")
        title = f"Group {group_id}"
    return group_id, title, link

def build_join_group_keyboard(link: str = None) -> InlineKeyboardMarkup:
    """Always show: [Group Link] on top (if any), then [I have joined]."""
    kb = InlineKeyboardMarkup(row_width=1)
    if link:
        kb.add(InlineKeyboardButton("🔗 Group Link — Join করুন", url=link))
    kb.add(InlineKeyboardButton("✅ I have joined", callback_data="verify_group_joined"))
    return kb

async def send_join_group_prompt(chat_id: int, prefix: str = ""):
    """Send standard join-group message with link + I have joined."""
    group_id, title, link = await get_user_join_group_invite()
    if not group_id:
        return False
    text = (
        f"{prefix}"
        f"📢 **Group Join আবশ্যক**\n\n"
        f"বট ব্যবহার করতে নিচের গ্রুপে join করুন:\n"
        f"**{safe_md(title)}**\n\n"
    )
    if link:
        text += f"1️⃣ উপরে **Group Link** বাটনে ক্লিক করে join করুন\n"
        text += f"2️⃣ তারপর **✅ I have joined** চাপুন\n\n"
        text += f"🔗 Link: {link}"
    else:
        text += (
            "⚠️ Invite link তৈরি হয়নি।\n"
            "অ্যাডমিন: বটকে গ্রুপে **Admin** বানিয়ে Invite Users পারমিশন দিন।\n"
            "গ্রুপে join করে ✅ I have joined চাপুন।"
        )
    kb = build_join_group_keyboard(link)
    await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True)
    return True

async def get_all_users():
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM users ORDER BY added_at DESC")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_user_account_count(user_id: int):
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT COUNT(*) as count FROM accounts WHERE added_by = ?", (user_id,))
        row = await cursor.fetchone()
        return row['count'] if row else 0

async def reset_user_account(user_id: int):
    async with db_connection() as conn:
        await conn.execute("DELETE FROM accounts WHERE added_by = ?", (user_id,))
        await conn.commit()

# ---------- Admin Management ----------
async def is_admin(user_id: int) -> bool:
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row is not None

async def add_admin(user_id: int, username: str = None):
    async with db_connection() as conn:
        await conn.execute("INSERT OR REPLACE INTO admins (user_id, username) VALUES (?, ?)", (user_id, username))
        await conn.commit()

async def remove_admin(user_id: int):
    async with db_connection() as conn:
        await conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await conn.commit()

async def list_admins():
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM admins ORDER BY added_at")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

# ---------- Global Settings ----------
async def get_global_2fa_password():
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT value FROM settings WHERE key = 'global_2fa_password'")
        row = await cursor.fetchone()
        return row['value'] if row else None

async def set_global_2fa_password(password):
    async with db_connection() as conn:
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('global_2fa_password', ?)", (password,))
        await conn.commit()

async def get_global_proxy():
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT value FROM settings WHERE key = 'global_proxy'")
        row = await cursor.fetchone()
        return row['value'] if row else None

async def set_global_proxy(proxy_str):
    async with db_connection() as conn:
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('global_proxy', ?)", (proxy_str,))
        await conn.commit()

async def remove_global_proxy():
    async with db_connection() as conn:
        await conn.execute("DELETE FROM settings WHERE key = 'global_proxy'")
        await conn.commit()

async def get_admin_group_id():
    """Admin Session Group — session files, pin, admin broadcasts"""
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT value FROM settings WHERE key = 'admin_group_id'")
        row = await cursor.fetchone()
        return int(row['value']) if row and row['value'] else None

async def set_admin_group_id(group_id):
    async with db_connection() as conn:
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_group_id', ?)", (str(group_id),))
        await conn.commit()

async def get_user_join_group_id():
    """User Force-Join Group — users must join this to use bot"""
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT value FROM settings WHERE key = 'user_join_group_id'")
        row = await cursor.fetchone()
        return int(row['value']) if row and row['value'] else None

async def set_user_join_group_id(group_id):
    async with db_connection() as conn:
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('user_join_group_id', ?)", (str(group_id),))
        await conn.commit()

async def clear_user_join_group_id():
    async with db_connection() as conn:
        await conn.execute("DELETE FROM settings WHERE key = 'user_join_group_id'")
        await conn.commit()

async def reset_all_data():
    async with db_connection() as conn:
        await conn.execute("DELETE FROM accounts")
        await conn.execute("DELETE FROM users")
        await conn.execute("DELETE FROM wallets")
        await conn.execute("DELETE FROM transactions")
        await conn.execute("DELETE FROM settings WHERE key IN ('global_2fa_password', 'global_proxy', 'admin_group_id')")
        await conn.execute("DELETE FROM country_apis")
        await conn.execute("DELETE FROM country_proxies")
        await conn.commit()

# ---------- Global Bot Toggle ----------
async def is_bot_enabled() -> bool:
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT value FROM settings WHERE key = 'bot_enabled'")
        row = await cursor.fetchone()
        return row['value'] == '1' if row else True

async def set_bot_enabled(enabled: bool):
    val = '1' if enabled else '0'
    async with db_connection() as conn:
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('bot_enabled', ?)", (val,))
        await conn.commit()

# ---------- User Preferences ----------
async def get_user_default_lib(user_id: int) -> str:
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT value FROM settings WHERE key = ?", (f"user_{user_id}_default_lib",))
        row = await cursor.fetchone()
        if row and row['value'] in ['telethon', 'pyrogram']:
            return row['value']
        return 'telethon'

async def set_user_default_lib(user_id: int, lib: str):
    async with db_connection() as conn:
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"user_{user_id}_default_lib", lib))
        await conn.commit()

async def get_user_auto_add_mode(user_id: int) -> bool:
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT value FROM settings WHERE key = ?", (f"user_{user_id}_auto_add",))
        row = await cursor.fetchone()
        return row['value'] == '1' if row else False

async def set_user_auto_add_mode(user_id: int, enabled: bool):
    val = '1' if enabled else '0'
    async with db_connection() as conn:
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"user_{user_id}_auto_add", val))
        await conn.commit()

# ---------- Proxy Parsing ----------
def parse_proxy(proxy_str):
    if not proxy_str:
        return None
    proxy_str = proxy_str.strip().rstrip('/')
    protocol = None
    if proxy_str.startswith('socks5://'):
        protocol = 'socks5'
        proxy_str = proxy_str[9:]
    elif proxy_str.startswith('http://'):
        protocol = 'http'
        proxy_str = proxy_str[7:]
    elif proxy_str.startswith('https://'):
        protocol = 'http'
        proxy_str = proxy_str[8:]
    parts = proxy_str.split(':')
    if len(parts) < 2:
        return None
    host = parts[0]
    try:
        port = int(parts[1])
    except:
        return None
    username = password = None
    if len(parts) >= 3:
        username = parts[2]
    if len(parts) >= 4:
        password = parts[3]
    if not protocol:
        protocol = 'socks5' if username else 'http'
    return {'protocol': protocol, 'host': host, 'port': port, 'username': username, 'password': password}

def get_telethon_proxy(proxy_str):
    p = parse_proxy(proxy_str)
    if not p:
        return None
    proxy_type = socks.SOCKS5 if p['protocol'] == 'socks5' else socks.HTTP
    proxy_dict = {'proxy_type': proxy_type, 'addr': p['host'], 'port': p['port']}
    if p['username']:
        proxy_dict['username'] = p['username']
    if p['password']:
        proxy_dict['password'] = p['password']
    return proxy_dict

def get_pyrogram_proxy(proxy_str):
    p = parse_proxy(proxy_str)
    if not p:
        return None
    scheme = 'socks5' if p['protocol'] == 'socks5' else 'http'
    proxy_dict = {'scheme': scheme, 'hostname': p['host'], 'port': p['port']}
    if p['username']:
        proxy_dict['username'] = p['username']
    if p['password']:
        proxy_dict['password'] = p['password']
    return proxy_dict

async def get_proxy_for_phone(phone):
    code = await get_country_code_from_phone(phone)
    # Prefer multiple proxies list (random)
    proxies = await get_country_proxies(code)
    if proxies:
        return random.choice(proxies)['proxy']
    country_cfg = await get_country_config(code)
    if country_cfg and country_cfg.get('proxy'):
        return country_cfg['proxy']
    return await get_global_proxy() or None

# ---------- Device Generation (1000+) ----------
DEVICE_LIST = []
def generate_device_list():
    global DEVICE_LIST
    brands = {
        "Samsung": ["Galaxy S21", "Galaxy S22", "Galaxy S23", "Galaxy S24", "Galaxy A52", "Galaxy A54", "Galaxy A73", "Galaxy Note 20", "Galaxy Z Flip4", "Galaxy Z Fold4", "Galaxy M33", "Galaxy M53"],
        "Xiaomi": ["Redmi Note 10", "Redmi Note 11", "Redmi Note 12", "Mi 11", "Mi 12", "Mi 13", "Poco X3", "Poco X5", "Poco F4", "Redmi 9", "Redmi 10", "Redmi 12"],
        "OnePlus": ["9", "9 Pro", "10 Pro", "11", "Nord 2", "Nord CE 2", "8T", "Nord 3"],
        "Google": ["Pixel 5", "Pixel 6", "Pixel 6a", "Pixel 7", "Pixel 7a", "Pixel 8", "Pixel 4a", "Pixel 8 Pro"],
        "iPhone": ["11", "12", "12 Pro", "13", "13 Pro", "13 mini", "14", "14 Pro", "15", "15 Pro", "SE 2020", "SE 2022"],
        "Oppo": ["Reno 5", "Reno 6", "Reno 7", "Reno 8", "A74", "A78", "F19", "Find X5"],
        "Vivo": ["V21", "V23", "V25", "V27", "Y20", "Y33s", "Y35", "X60", "X70", "X80"],
        "Realme": ["8", "9 Pro", "10", "11", "C25", "C35", "GT Master", "GT Neo 3", "Narzo 50"],
        "Motorola": ["Moto G60", "Moto G72", "Edge 20", "Edge 30", "G40 Fusion", "Razr 5G", "G82"],
        "Huawei": ["P40", "P50", "Nova 8", "Nova 9", "Mate 40", "Mate 50", "Y9a", "Y90"],
        "Infinix": ["Note 12", "Hot 20", "Zero 5G", "Note 30", "Smart 7"],
        "Tecno": ["Spark 8", "Camon 19", "Pova 4", "Spark 10", "Camon 20"],
        "Nokia": ["G21", "G50", "X20", "C31", "G60"],
        "Sony": ["Xperia 5", "Xperia 1 III", "Xperia 10 IV"],
        "Asus": ["ROG Phone 5", "Zenfone 8", "ROG Phone 6"],
    }
    android_versions = ["Android 10", "Android 11", "Android 12", "Android 13", "Android 14"]
    ios_versions = ["iOS 14.8", "iOS 15.7", "iOS 16.6", "iOS 17.2", "iOS 17.5"]
    app_versions_android = [
        "Telegram Android 8.9.0", "Telegram Android 9.0.1", "Telegram Android 9.1.0",
        "Telegram Android 9.2.0", "Telegram Android 10.0.0", "Telegram Android 10.2.5",
        "Telegram Android 10.6.2", "Telegram Android 11.1.0"
    ]
    app_versions_ios = [
        "Telegram iOS 8.9.0", "Telegram iOS 9.0.1", "Telegram iOS 9.1.0",
        "Telegram iOS 9.4.0", "Telegram iOS 10.0.5", "Telegram iOS 10.3.1"
    ]
    for brand, models in brands.items():
        for model in models:
            if brand == "iPhone":
                for ios in ios_versions:
                    for app in app_versions_ios:
                        DEVICE_LIST.append({"device_model": f"{brand} {model}", "system_version": ios, "app_version": app})
            else:
                for android in android_versions:
                    for app in app_versions_android:
                        DEVICE_LIST.append({"device_model": f"{brand} {model}", "system_version": android, "app_version": app})
    # Pad to at least 1200 unique-looking entries
    base_len = len(DEVICE_LIST)
    if base_len < 1200:
        for i in range(1200 - base_len):
            DEVICE_LIST.append({
                "device_model": f"Generic Device {i+1}",
                "system_version": random.choice(android_versions),
                "app_version": random.choice(app_versions_android)
            })
    random.shuffle(DEVICE_LIST)
    logger.info(f"Device list generated: {len(DEVICE_LIST)} devices")

generate_device_list()

def get_random_device():
    return random.choice(DEVICE_LIST)

async def with_login_slot(coro):
    """Limit concurrent Telethon/Pyrogram connections for 100+ users safety"""
    async with LOGIN_SEMAPHORE:
        return await coro

# ---------- Account Functions (modified to store api_id/api_hash) ----------
async def save_account(phone, lib, session_string, device_info=None, twofa_enabled=0,
                 proxy=None, client_device_info=None, spam_status='Unknown', added_by=None,
                 status='New', api_id=None, api_hash=None):
    async with db_connection() as conn:
        await conn.execute("""
            INSERT OR REPLACE INTO accounts 
            (phone, lib, session_string, device_info, twofa_enabled, proxy, device_model, system_version, app_version, spam_status, added_by, status,
             claim_status, claim_retry_time, claim_attempts, api_id, api_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, 0, ?, ?)
        """, (phone, lib, session_string, json.dumps(device_info), twofa_enabled,
              proxy,
              client_device_info['device_model'] if client_device_info else None,
              client_device_info['system_version'] if client_device_info else None,
              client_device_info['app_version'] if client_device_info else None,
              spam_status, added_by, status,
              api_id, api_hash))
        await conn.commit()
        code = await get_country_code_from_phone(phone)
        async with db_connection() as conn2:
            await conn2.execute("UPDATE countries SET current_count = current_count + 1 WHERE country_code = ?", (code,))
            await conn2.commit()
    # Pin the pending account in admin group
    await pin_pending_account(phone, lib, added_by)
    await save_session_files_locally(added_by, phone, lib, session_string, device_info, spam_status, proxy, status=status, api_id=api_id, api_hash=api_hash)

async def get_all_accounts():
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM accounts ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_account(phone):
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM accounts WHERE phone = ?", (phone,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def delete_account(phone):
    async with db_connection() as conn:
        code = await get_country_code_from_phone(phone)
        await conn.execute("UPDATE countries SET current_count = current_count - 1 WHERE country_code = ?", (code,))
        await conn.execute("DELETE FROM accounts WHERE phone = ?", (phone,))
        await conn.commit()

async def update_2fa(phone, enabled):
    async with db_connection() as conn:
        await conn.execute("UPDATE accounts SET twofa_enabled = ? WHERE phone = ?", (enabled, phone))
        await conn.commit()

async def update_spam_status(phone, status):
    async with db_connection() as conn:
        await conn.execute("UPDATE accounts SET spam_status = ? WHERE phone = ?", (status, phone))
        await conn.commit()

async def update_claim_status(phone, claim_status, retry_time=None):
    async with db_connection() as conn:
        if retry_time:
            await conn.execute("UPDATE accounts SET claim_status = ?, claim_retry_time = ? WHERE phone = ?", (claim_status, retry_time, phone))
        else:
            await conn.execute("UPDATE accounts SET claim_status = ? WHERE phone = ?", (claim_status, phone))
        await conn.commit()

async def increment_claim_attempts(phone):
    async with db_connection() as conn:
        await conn.execute("UPDATE accounts SET claim_attempts = claim_attempts + 1 WHERE phone = ?", (phone,))
        await conn.commit()

async def get_pending_claims():
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM accounts WHERE claim_status = 'pending'")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_retry_claims():
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM accounts WHERE claim_status = 'retry' AND claim_retry_time <= datetime('now')")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

# ---------- Pinning Functions ----------
async def pin_pending_account(phone, lib, added_by):
    group_id = await get_admin_group_id()
    if not group_id:
        logger.warning("No admin group set, cannot pin account. Please set Admin Group first.")
        return
    acc = await get_account(phone)
    if not acc:
        return
    if acc.get('pinned_message_id') and acc.get('pinned_chat_id'):
        return
    text = (
        f"⏳ **Pending Confirmation**\n"
        f"Phone: `{phone}`\n"
        f"Lib: `{lib}`\n"
        f"Added by: `{added_by}`\n"
        f"Created: {acc['created_at']}"
    )
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("📥 Claim Now", callback_data=f"claim_admin_{phone}"))
    try:
        msg = await bot.send_message(group_id, text, reply_markup=keyboard, parse_mode="Markdown")
        try:
            await bot.pin_chat_message(group_id, msg.message_id, disable_notification=True)
        except Exception as pin_err:
            logger.warning(f"Could not pin message for {phone} (bot may lack pin rights): {pin_err}")
        async with db_connection() as conn:
            await conn.execute(
                "UPDATE accounts SET pinned_message_id = ?, pinned_chat_id = ? WHERE phone = ?",
                (msg.message_id, group_id, phone)
            )
            await conn.commit()
        logger.info(f"Pending account {phone} posted & attempted pin in admin group.")
    except Exception as e:
        logger.error(f"Failed to post/pin account {phone}: {e}")

async def unpin_pending_account(phone):
    acc = await get_account(phone)
    if not acc:
        return
    pinned_msg_id = acc.get('pinned_message_id')
    pinned_chat_id = acc.get('pinned_chat_id')
    if pinned_msg_id and pinned_chat_id:
        try:
            # Try unpin specific message
            await bot.unpin_chat_message(chat_id=pinned_chat_id, message_id=pinned_msg_id)
        except Exception as e:
            logger.warning(f"Failed to unpin specific message for {phone}: {e}")
            try:
                # Fallback: try unpin all (if API supports)
                await bot.unpin_all_chat_messages(chat_id=pinned_chat_id)
            except Exception as e2:
                logger.warning(f"Failed to unpin all for {phone}: {e2}")
        async with db_connection() as conn:
            await conn.execute(
                "UPDATE accounts SET pinned_message_id = NULL, pinned_chat_id = NULL WHERE phone = ?",
                (phone,)
            )
            await conn.commit()
        logger.info(f"Unpinned pending account {phone}")

# ---------- Claim Logic (improved) ----------
async def logout_other_sessions(client):
    if isinstance(client, TelegramClient):
        sessions = await client.get_sessions()
        current_session = client.session
        for session in sessions:
            if session != current_session and session.is_authenticated():
                try:
                    await client.revoke_session(session)
                except Exception as e:
                    logger.warning(f"Failed to revoke session: {e}")
    else:
        try:
            sessions = await client.get_active_sessions()
            current_session_id = client.session_id
            for session in sessions:
                if session.id != current_session_id:
                    try:
                        await client.revoke_session(session.id)
                    except Exception as e:
                        logger.warning(f"Failed to revoke Pyrogram session: {e}")
        except Exception as e:
            logger.warning(f"Error getting active sessions: {e}")

async def claim_account(phone, user_id=None, force=False):
    acc = await get_account(phone)
    if not acc:
        return False, "Account not found", None, None
    if acc['claim_status'] == 'claimed':
        return False, "Already claimed", None, 'claimed'
    country_code = await get_country_code_from_phone(phone)
    country_cfg = await get_country_config(country_code)
    timer_minutes = country_cfg.get('confirmation_timer', 5) if country_cfg else 5
    
    # Fix timezone: SQLite CURRENT_TIMESTAMP is UTC. Use UTC for comparison.
    try:
        created_str = acc['created_at']
        if 'Z' in created_str or '+' in created_str:
            created_time = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
        else:
            # Assume UTC if no timezone info
            created_time = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        created_time = datetime.now(timezone.utc)
    
    now_utc = datetime.now(timezone.utc)
    if not force:
        unlock_time = created_time + timedelta(minutes=timer_minutes)
        if now_utc < unlock_time:
            remaining_seconds = (unlock_time - now_utc).total_seconds()
            remaining_min = max(1, int(remaining_seconds // 60))
            return False, f"Confirmation period not over. Wait approx {remaining_min} more minutes.", None, 'pending'
    client, proxy_str = await client_from_session_with_retry(phone, retries=1)
    if not client:
        return False, "Cannot login to account.", None, 'failed'
    try:
        if not await client.is_user_authorized():
            return False, "Session not authorized.", None, 'failed'

        # ---------- 1. Check other active sessions first ----------
        sessions_count = 0
        try:
            if isinstance(client, TelegramClient):
                sessions = await client.get_sessions()
                sessions_count = len([s for s in sessions if s.is_authenticated()])
            else:
                sessions = await client.get_active_sessions()
                sessions_count = len(sessions)
        except Exception as e:
            logger.warning(f"Could not get sessions for {phone}: {e}")
            sessions_count = 1  # assume only current if failed

        if sessions_count > 1:
            if not force:
                # User claim: tell them to logout other sessions and try again
                return False, f"⚠️ অন্য ডিভাইসে {sessions_count-1}টি Active Session আছে।\nসব লগআউট করে আবার Claim বাটনে ক্লিক করুন।", None, 'pending'
            else:
                # Admin force claim: logout other sessions
                await logout_other_sessions(client)

        # ---------- 2. No other sessions → Check Frozen / Spam ----------
        spam_status = await check_spam_status(client, phone)
        if spam_status != 'Clean':
            await update_spam_status(phone, spam_status)
            return False, f"❌ Account is {spam_status} (Frozen/Limited). Cannot claim.", None, 'failed'

        # ---------- 3. All OK → Complete Claim ----------
        if isinstance(client, TelegramClient):
            session_string = client.session.save()
        else:
            session_string = await client.export_session_string()
        me = await client.get_me()
        device_info = {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "username": me.username,
            "phone": phone,
            "device_model": acc.get('device_model', 'Unknown'),
            "platform": acc.get('system_version', 'Unknown'),
        }
        await update_claim_status(phone, 'claimed')
        await update_account_status(phone, 'Claimed')
        await unpin_pending_account(phone)
        session_data = {
            "phone": phone,
            "lib": acc['lib'],
            "session_string": session_string,
            "device_info": device_info,
            "twofa_enabled": acc['twofa_enabled'],
            "spam_status": spam_status,
            "created_at": acc['created_at'],
            "proxy": acc['proxy'],
            "device_model": acc['device_model'],
            "system_version": acc['system_version'],
            "app_version": acc['app_version'],
            "added_by": acc['added_by'],
            "api_id": acc['api_id'],
            "api_hash": acc['api_hash']
        }
        await client.disconnect()

        # Add balance to the user who added the account
        added_by = acc['added_by']
        if added_by:
            price = country_cfg.get('price', 0) if country_cfg else 0
            if price > 0:
                await add_balance(added_by, price, f"Account claimed: {phone} (Country: +{country_code})")
                try:
                    await bot.send_message(added_by, f"💰 আপনি `{phone}` অ্যাকাউন্ট ক্লেইমের জন্য `${price:.2f}` পেয়েছেন!", parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"Failed to notify user {added_by}: {e}")

        return True, "Claim successful!", session_data, 'claimed'
    except Exception as e:
        logger.error(f"Claim error for {phone}: {e}")
        await update_claim_status(phone, 'failed')
        return False, f"Error: {str(e)}", None, 'failed'
    finally:
        try:
            await client.disconnect()
        except:
            pass

async def claim_all_pending(force=False):
    results = []
    pending = await get_pending_claims()
    retry = await get_retry_claims()
    accounts = pending + retry
    for acc in accounts:
        phone = acc['phone']
        success, msg, _, status = await claim_account(phone, force=force)
        results.append((phone, success, msg, status))
    return results

# ---------- Background Retry Task ----------
async def retry_claim_worker():
    while True:
        try:
            retry_accounts = await get_retry_claims()
            for acc in retry_accounts:
                phone = acc['phone']
                success, msg, session_data, status = await claim_account(phone, force=True)
                if success:
                    admins = await list_admins()
                    for admin in admins:
                        await send_session_files_to_admin(admin['user_id'], session_data, phone)
                    if acc['added_by']:
                        await send_session_files_to_admin(acc['added_by'], session_data, phone)
                    group_id = await get_admin_group_id()
                    if group_id:
                        await bot.send_message(group_id, f"✅ Account `{phone}` claimed successfully after retry.")
                    await increment_claim_attempts(phone)
                else:
                    await increment_claim_attempts(phone)
                    attempts = (await get_account(phone))['claim_attempts']
                    if attempts >= 3:
                        await update_claim_status(phone, 'failed')
                        group_id = await get_admin_group_id()
                        if group_id:
                            await bot.send_message(group_id, f"❌ Account `{phone}` claim failed after 3 attempts.")
                await asyncio.sleep(1)
            await asyncio.sleep(600)
        except Exception as e:
            logger.error(f"Retry worker error: {e}")
            await asyncio.sleep(600)

async def send_session_files_to_admin(admin_id, session_data, phone):
    json_bytes = json.dumps(session_data, indent=2).encode('utf-8')
    json_file = BytesIO(json_bytes)
    json_file.name = f"{phone}_session.json"
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        zf.writestr("tdata/placeholder.txt", "tdata conversion not implemented")
    zip_buffer.seek(0)
    zip_file = BytesIO(zip_buffer.getvalue())
    zip_file.name = f"{phone}_tdata.zip"
    try:
        await bot.send_document(admin_id, json_file)
        await bot.send_document(admin_id, zip_file)
        await bot.send_message(admin_id, f"✅ Claimed session files for `{phone}`", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send files to {admin_id}: {e}")

async def send_session_files_to_all_admins(phone, lib, session_string, device_info, spam_status, api_id=None, api_hash=None):
    group_id = await get_admin_group_id()
    if not group_id:
        logger.warning("No admin group set, cannot send session files.")
        return
    session_data = {
        "phone": phone,
        "lib": lib,
        "session_string": session_string,
        "device_info": device_info,
        "twofa_enabled": bool(await get_global_2fa_password()),
        "spam_status": spam_status,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "api_id": api_id,
        "api_hash": api_hash
    }
    json_bytes = json.dumps(session_data, indent=2).encode('utf-8')
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        zf.writestr("tdata/placeholder.txt", "tdata conversion not implemented")
    zip_buffer.seek(0)
    caption = f"📱 **New Login**\nPhone: `{safe_md(phone)}`\nLib: `{safe_md(lib)}`\nSpam Status: `{safe_md(spam_status)}`"
    try:
        json_file = BytesIO(json_bytes)
        json_file.name = f"{phone}_session.json"
        await bot.send_document(group_id, json_file, caption=caption, parse_mode="Markdown")
        zip_file = BytesIO(zip_buffer.getvalue())
        zip_file.name = f"{phone}_tdata.zip"
        await bot.send_document(group_id, zip_file)
    except Exception as e:
        logger.error(f"Failed to send files to group: {e}")

# ---------- client_from_session (fixed to use stored API) ----------
async def client_from_session_with_retry(phone, retries=1):
    acc = await get_account(phone)
    if not acc or not acc['session_string']:
        return None, None
    proxy_str = await get_proxy_for_phone(phone)
    lib = acc['lib']
    session_string = acc['session_string']
    device_model = acc['device_model']
    system_version = acc['system_version']
    app_version = acc['app_version']
    # Use stored API credentials, fallback to global constants
    api_id = acc.get('api_id') or API_ID
    api_hash = acc.get('api_hash') or API_HASH
    for attempt in range(retries):
        try:
            if lib == 'telethon':
                proxy = get_telethon_proxy(proxy_str) if proxy_str else None
                client = TelegramClient(
                    StringSession(session_string), api_id, api_hash,
                    proxy=proxy,
                    device_model=device_model,
                    system_version=system_version,
                    app_version=app_version,
                    timeout=15
                )
            else:
                proxy = get_pyrogram_proxy(proxy_str) if proxy_str else None
                client = PyroClient(
                    phone, api_id=api_id, api_hash=api_hash,
                    session_string=session_string,
                    proxy=proxy,
                    device_model=device_model,
                    system_version=system_version,
                    app_version=app_version,
                    workdir=PYROGRAM_WORKDIR
                )
            async with LOGIN_SEMAPHORE:
                await client.connect()
            if await client.is_user_authorized():
                return client, proxy_str
            else:
                await client.disconnect()
                continue
        except Exception as e:
            logger.warning(f"Client for {phone} failed: {e}")
            try:
                await client.disconnect()
            except:
                pass
            continue
        if attempt < retries - 1:
            await asyncio.sleep(1)
    return None, None

async def client_from_session(phone):
    client, _ = await client_from_session_with_retry(phone)
    return client

# ---------- Spam Check ----------
async def check_spam_status(client, phone=None):
    try:
        if isinstance(client, TelegramClient):
            spam_bot = await client.get_entity('@SpamBot')
            msg = await client.send_message(spam_bot, '/start')
            await asyncio.sleep(3)
            async for reply in client.iter_messages(spam_bot, limit=10, min_id=msg.id):
                if reply.sender_id == spam_bot.id:
                    text = (reply.text or "").lower()
                    if any(k in text for k in ['good news', 'no limits', 'no restrictions', 'not limited', 'free']):
                        status = 'Clean'
                    elif any(k in text for k in ['limited', 'restricted', 'banned']):
                        status = 'Limited'
                    else:
                        status = 'Unknown'
                    break
            else:
                status = 'Unknown'
        else:
            spam_bot = await client.get_users('@SpamBot')
            msg = await client.send_message(spam_bot.id, '/start')
            await asyncio.sleep(3)
            async for message in client.get_chat_history(spam_bot.id, limit=10):
                if message.id > msg.id and message.from_user and message.from_user.id == spam_bot.id:
                    text = (message.text or "").lower()
                    if any(k in text for k in ['good news', 'no limits', 'no restrictions', 'not limited', 'free']):
                        status = 'Clean'
                    elif any(k in text for k in ['limited', 'restricted', 'banned']):
                        status = 'Limited'
                    else:
                        status = 'Unknown'
                    break
            else:
                status = 'Unknown'
        if status == 'Limited' and phone:
            await update_account_status(phone, 'Spam')
            try:
                if isinstance(client, TelegramClient):
                    await client.log_out()
                else:
                    await client.terminate()
            except:
                pass
            try:
                await client.disconnect()
            except:
                pass
            await delete_account(phone)
        return status
    except Exception as e:
        logger.error(f"Spam check failed: {e}")
        return 'Unknown'

# ---------- Apply Global 2FA ----------
async def apply_global_2fa(client, phone, current_password=None):
    password = await get_global_2fa_password()
    if not password:
        return 0
    try:
        if isinstance(client, TelegramClient):
            await client.edit_2fa(new_password=password, hint="")
        else:
            await client.change_cloud_password(current_password=current_password or "", new_password=password, hint="")
        await update_2fa(phone, 1)
        return 1
    except Exception as e:
        logger.error(f"Failed to apply global 2FA for {phone}: {e}")
        return 0

async def save_session_files_locally(added_by, phone, lib, session_string, device_info, spam_status, proxy, status=None, api_id=None, api_hash=None):
    """Save session under Account_Management / User / Country / Status / Date"""
    try:
        code = await get_country_code_from_phone(phone)
        country_name = await get_country_name_from_code(code) or code
        # sanitize folder names
        country_name = re.sub(r'[^\w\-\+\. ]', '_', str(country_name))
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        status_folder = (status or spam_status or "New").replace(" ", "_")
        user_folder = f"user_{added_by}" if added_by else "user_unknown"
        base_dir = os.path.join(
            SCRIPT_DIR, "Account_Management",
            user_folder,
            f"+{code}_{country_name}",
            status_folder,
            today
        )
        os.makedirs(base_dir, exist_ok=True)
        session_data = {
            "phone": phone,
            "lib": lib,
            "session_string": session_string,
            "device_info": device_info,
            "spam_status": spam_status,
            "status": status or "New",
            "proxy": proxy,
            "added_by": added_by,
            "api_id": api_id,
            "api_hash": api_hash,
            "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }
        file_path = os.path.join(base_dir, f"{phone}_{lib}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        # also write a small tdata placeholder zip next to it
        zip_path = os.path.join(base_dir, f"{phone}_tdata.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("tdata/placeholder.txt", "tdata conversion not implemented")
            zf.writestr(f"{phone}_session.json", json.dumps(session_data, indent=2))
        logger.info(f"Session saved: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Failed to save session locally for {phone}: {e}")
        return None

# ---------- States ----------
class LoginStates(StatesGroup):
    choosing_lib = State()
    entering_phone = State()
    entering_code = State()
    entering_password = State()
    waiting_for_phone_continuous = State()

class VerifyStates(StatesGroup):
    waiting_captcha = State()
    waiting_group_join = State()

class AdminStates(StatesGroup):
    waiting_for_add_admin_id = State()
    waiting_for_2fa_password = State()
    waiting_for_proxy_host = State()
    waiting_for_proxy_port = State()
    waiting_for_proxy_username = State()
    waiting_for_proxy_password = State()
    waiting_for_group_id = State()
    waiting_for_user_join_group_id = State()
    waiting_for_broadcast_admins_message = State()
    waiting_for_broadcast_users_message = State()
    waiting_for_reset_confirmation = State()
    waiting_for_send_user_id = State()
    waiting_for_send_message = State()
    waiting_for_reset_user_id = State()
    waiting_for_support_id = State()
    waiting_for_country_code = State()
    waiting_for_balance_user_id = State()
    waiting_for_balance_amount = State()
    waiting_for_country_price = State()
    waiting_for_country_capacity = State()
    waiting_for_country_api_id = State()
    waiting_for_country_api_hash = State()
    waiting_for_country_proxy = State()
    waiting_for_country_timer = State()
    waiting_for_broadcast_pin_confirm = State()
    waiting_for_add_api_id = State()
    waiting_for_add_api_hash = State()
    waiting_for_remove_api_select = State()
    waiting_for_add_proxy = State()
    waiting_for_remove_proxy_select = State()

class RemoveAdminStates(StatesGroup):
    waiting_for_remove_admin_id = State()

class ImportStates(StatesGroup):
    waiting_for_import_data = State()
    waiting_for_phone = State()
    waiting_for_lib = State()

class UserSettingsStates(StatesGroup):
    main = State()
    toggle_auto = State()
    set_default_lib = State()

class WalletStates(StatesGroup):
    main = State()
    withdrawal_amount = State()
    withdrawal_method = State()
    withdrawal_details = State()

class SearchStates(StatesGroup):
    waiting_for_search_query = State()

class BulkDeleteStates(StatesGroup):
    waiting_for_phone_list = State()

# ---------- Temporary Data ----------
login_data = {}
import_data = {}
proxy_data = {}
pending_config = {}
last_broadcast = {}

# ---------- Keyboards ----------
async def main_menu_keyboard(user_id):
    admin = await is_admin(user_id)
    if admin:
        keyboard = [
            [KeyboardButton("➕ Create Login"), KeyboardButton("📋 Accounts")],
            [KeyboardButton("💳 My Wallet"), KeyboardButton("🌍 Countries & Pricing")],
            [KeyboardButton("⚙️ Settings")],
            [KeyboardButton("📊 Statistics"), KeyboardButton("ℹ️ Account Info")],
            [KeyboardButton("👤 My Settings"), KeyboardButton("📞 Support")]
        ]
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    else:
        keyboard = [
            [KeyboardButton("➕ Add Account"), KeyboardButton("📋 Account List")],
            [KeyboardButton("💳 My Wallet"), KeyboardButton("🌍 Countries & Pricing")],
            [KeyboardButton("👤 My Settings")],
            [KeyboardButton("📞 Support")]
        ]
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def settings_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📨 Read Messages"), KeyboardButton("🗑 Delete Session")],
            [KeyboardButton("🚪 Revoke Session"), KeyboardButton("📤 Export Files")],
            [KeyboardButton("🔐 Set 2FA (All)"), KeyboardButton("⚙️ Proxy Settings")],
            [KeyboardButton("🔍 Health Check"), KeyboardButton("📥 Import Session")],
            [KeyboardButton("📦 Bulk Export"), KeyboardButton("👑 Admin Panel")],
            [KeyboardButton("🔄 Restart Bot"), KeyboardButton("🔙 Main Menu")],
            [KeyboardButton("🤖 Check Spam (All)")]
        ],
        resize_keyboard=True
    )

def proxy_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("➕ Set New Proxy"), KeyboardButton("🗑 Remove Proxy")],
            [KeyboardButton("🔙 Settings Menu")]
        ],
        resize_keyboard=True
    )

def admin_panel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("➕ Add Admin"), KeyboardButton("➖ Remove Admin")],
            [KeyboardButton("📋 List Admins"), KeyboardButton("🏢 Set Admin Group")],
            [KeyboardButton("📢 Set User Join Group")],
            [KeyboardButton("📢 Broadcast to Admins"), KeyboardButton("📢 Broadcast to All Users")],
            [KeyboardButton("👥 User List"), KeyboardButton("📨 Send Message")],
            [KeyboardButton("🔄 Reset User Account"), KeyboardButton("🗑 Reset All Data")],
            [KeyboardButton("🌍 Country Management"), KeyboardButton("⚡ Toggle Libraries")],
            [KeyboardButton("📞 Set Support ID"), KeyboardButton("🔍 Check Proxies")],
            [KeyboardButton("💰 Finance Management"), KeyboardButton("🔎 Search Accounts")],
            [KeyboardButton("📁 Bulk Delete"), KeyboardButton("📤 Export CSV")],
            [KeyboardButton("📂 Session Files"), KeyboardButton("📋 Claim Accounts")],
            [KeyboardButton("🌐 Toggle Bot"), KeyboardButton("🔙 Main Menu")]
        ],
        resize_keyboard=True
    )

async def lib_keyboard():
    telethon_active = await get_lib_toggle('telethon')
    pyrogram_active = await get_lib_toggle('pyrogram')
    buttons = []
    if telethon_active:
        buttons.append(KeyboardButton("🐍 Telethon"))
    if pyrogram_active:
        buttons.append(KeyboardButton("🔥 Pyrogram"))
    keyboard = []
    if buttons:
        keyboard.append(buttons)
    keyboard.append([KeyboardButton("🔙 Main Menu")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton("❌ Cancel")]],
        resize_keyboard=True
    )

def reset_confirm_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("✅ YES, Reset All"), KeyboardButton("❌ NO, Cancel")]
        ],
        resize_keyboard=True
    )

async def account_select_keyboard(prefix, accounts=None):
    if accounts is None:
        accounts = await get_all_accounts()
    keyboard = InlineKeyboardMarkup(row_width=1)
    for acc in accounts:
        keyboard.add(InlineKeyboardButton(f"📱 {acc['phone']}", callback_data=f"{prefix}_{acc['phone']}"))
    keyboard.add(InlineKeyboardButton("🔙 Back", callback_data="main_menu_inline"))
    return keyboard

async def user_settings_keyboard(user_id):
    auto_status = "✅ ON" if await get_user_auto_add_mode(user_id) else "❌ OFF"
    default_lib = await get_user_default_lib(user_id)
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(f"🔄 Auto-Add: {auto_status}", callback_data="user_settings_toggle_auto"),
        InlineKeyboardButton(f"📚 Default Lib: {default_lib.capitalize()}", callback_data="user_settings_change_lib")
    )
    keyboard.add(InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu_inline"))
    return keyboard

# ---------- Set Bot Commands ----------
async def set_bot_commands():
    commands = [
        BotCommand(command="start", description="Start Again"),

    ]
    await bot.set_my_commands(commands)

# ---------- Helper: Check bot enabled + captcha + group join ----------
async def ensure_bot_enabled(user_id: int, message: types.Message) -> bool:
    """Full access gate: admin bypass, bot on, captcha passed, still in admin group."""
    if await is_admin(user_id):
        return True
    if not await is_bot_enabled():
        await message.answer("⚠️ বটটি বর্তমানে বন্ধ আছে। দয়া করে অ্যাডমিনের সাথে যোগাযোগ করুন।")
        return False

    user = await get_user_row(user_id)
    if not user:
        await add_or_update_user(user_id)
        user = await get_user_row(user_id)

    # 1) Captcha must be passed
    if not user.get('captcha_passed'):
        await message.answer(
            "🔐 আগে **Captcha** সমাধান করতে হবে।\n"
            "/start চাপুন এবং Math প্রশ্নের উত্তর দিন।"
        )
        return False

    # 2) Must stay in User Join Group (if set) — separate from Admin Session Group
    group_id = await get_user_join_group_id()
    if group_id:
        in_group = await is_user_in_force_group(user_id)
        if not in_group:
            await set_user_group_joined(user_id, False)
            group_id2, title, link = await get_user_join_group_invite()
            kb = build_join_group_keyboard(link)
            text = (
                f"📢 **Group Join আবশ্যক**\n\n"
                f"বট ব্যবহার করতে গ্রুপে join করুন:\n"
                f"**{safe_md(title or 'Join Group')}**\n\n"
            )
            if link:
                text += "1️⃣ **🔗 Group Link** বাটনে ক্লিক করে join করুন\n"
                text += "2️⃣ তারপর **✅ I have joined** চাপুন\n\n"
                text += f"Link: {link}\n\n"
            else:
                text += "⚠️ Link পাওয়া যায়নি — অ্যাডমিন বটকে গ্রুপে Admin বানান।\n"
            text += "Group ছেড়ে দিলে বট ব্যবহার করা যাবে না।"
            await message.answer(text, reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True)
            return False
        else:
            if not user.get('group_joined'):
                await set_user_group_joined(user_id, True)

    return True


captcha_answers = {}

# ---------- Handlers ----------
@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    await add_or_update_user(
        uid,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name
    )
    if await is_admin(uid):
        await message.answer("🔐 **Welcome Admin!**", reply_markup=await main_menu_keyboard(uid), parse_mode="Markdown")
        return
    if not await is_bot_enabled():
        await message.answer("⚠️ বটটি বর্তমানে বন্ধ আছে।")
        return

    user = await get_user_row(uid)
    # Captcha gate
    if not user.get('captcha_passed'):
        attempts = user.get('captcha_attempts') or 0
        if attempts >= 5:
            await message.answer("🚫 Captcha ৫ বার ব্যর্থ হয়েছিল। Attempts রিসেট করা হলো — আবার চেষ্টা করুন।")
            await reset_captcha_attempts(uid)
        q, ans = generate_math_captcha()
        captcha_answers[uid] = ans
        att = (await get_user_row(uid)).get('captcha_attempts') or 0
        await message.answer(
            "🔐 **নতুন ইউজার ভেরিফিকেশন**\n\n"
            "বট ব্যবহার করতে Math Captcha সমাধান করুন:\n\n"
            f"🧮 `{q}`\n\n"
            "শুধু উত্তরের সংখ্যা লিখুন।\n"
            f"চেষ্টা: `{att}` / 5",
            parse_mode="Markdown"
        )
        await state.set_state(VerifyStates.waiting_captcha)
        return

    # Group gate (User Join Group — not Admin Session Group)
    group_id = await get_user_join_group_id()
    if group_id and not await is_user_in_force_group(uid):
        await set_user_group_joined(uid, False)
        _, title, link = await get_user_join_group_invite()
        kb = build_join_group_keyboard(link)
        text = (
            f"📢 **Group Join আবশ্যক**\n\n"
            f"**{safe_md(title or 'Join Group')}** গ্রুপে join করুন।\n\n"
        )
        if link:
            text += "1️⃣ **🔗 Group Link** চাপুন → Join\n"
            text += "2️⃣ তারপর **✅ I have joined** চাপুন\n\n"
            text += f"Link: {link}"
        else:
            text += "⚠️ Link নেই — অ্যাডমিন বটকে গ্রুপে Admin + Invite permission দিন।"
        await message.answer(text, reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True)
        await state.set_state(VerifyStates.waiting_group_join)
        return

    await set_user_group_joined(uid, True)
    name = message.from_user.first_name or message.from_user.username or str(uid)
    await message.answer(
        f"👋 **Welcome, {safe_md(name)}!**\n\nবট ব্যবহার করতে পারবেন।",
        reply_markup=await main_menu_keyboard(uid),
        parse_mode="Markdown"
    )


@router.message(VerifyStates.waiting_captcha)
async def process_captcha_answer(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if message.text and message.text.startswith('/'):
        return
    try:
        user_ans = int(message.text.strip())
    except Exception:
        await message.answer("❌ শুধু সংখ্যা লিখুন। উদাহরণ: `12`", parse_mode="Markdown")
        return
    correct = captcha_answers.get(uid)
    if correct is None:
        q, ans = generate_math_captcha()
        captcha_answers[uid] = ans
        await message.answer(f"নতুন প্রশ্ন:\n🧮 `{q}`", parse_mode="Markdown")
        return
    if user_ans == correct:
        await set_user_captcha_passed(uid, True)
        captcha_answers.pop(uid, None)
        await state.clear()
        await message.answer("✅ **Captcha সঠিক!**")
        group_id = await get_user_join_group_id()
        if group_id and not await is_user_in_force_group(uid):
            _, title, link = await get_user_join_group_invite()
            kb = build_join_group_keyboard(link)
            text = (
                f"📢 এখন গ্রুপে join করুন:\n**{safe_md(title or 'Join Group')}**\n\n"
            )
            if link:
                text += "1️⃣ **🔗 Group Link** → Join\n2️⃣ **✅ I have joined**\n\n"
                text += f"Link: {link}"
            else:
                text += "⚠️ Link নেই — অ্যাডমিন বটকে গ্রুপে Admin বানান।"
            await message.answer(text, reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True)
            await state.set_state(VerifyStates.waiting_group_join)
            return
        name = message.from_user.first_name or message.from_user.username or str(uid)
        await message.answer(
            f"👋 **Welcome, {safe_md(name)}!**",
            reply_markup=await main_menu_keyboard(uid),
            parse_mode="Markdown"
        )
        return

    attempts = await increment_captcha_attempts(uid)
    left = 5 - attempts
    if left <= 0:
        await state.clear()
        captcha_answers.pop(uid, None)
        await message.answer("🚫 ৫ বার ভুল হয়েছে। পরে /start দিয়ে আবার চেষ্টা করুন।")
        return
    q, ans = generate_math_captcha()
    captcha_answers[uid] = ans
    await message.answer(
        f"❌ ভুল উত্তর। বাকি চেষ্টা: `{left}` / 5\n\nনতুন প্রশ্ন:\n🧮 `{q}`",
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "verify_group_joined")
async def verify_group_joined_cb(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    uid = callback_query.from_user.id
    if await is_admin(uid):
        await bot.send_message(uid, "Admin — skip.", reply_markup=await main_menu_keyboard(uid))
        await state.clear()
        return
    user = await get_user_row(uid)
    if user and not user.get('captcha_passed'):
        await bot.send_message(uid, "আগে Captcha সমাধান করুন। /start চাপুন।")
        return
    if not await is_user_in_force_group(uid):
        try:
            await callback_query.answer(text="এখনও Group-এ join করেননি!", show_alert=True)
        except Exception:
            pass
        await bot.send_message(uid, "❌ Group-এ join করে আবার ✅ I have joined চাপুন।")
        return
    await set_user_group_joined(uid, True)
    await state.clear()
    name = callback_query.from_user.first_name or callback_query.from_user.username or str(uid)
    uname = f"@{callback_query.from_user.username}" if callback_query.from_user.username else ""
    await bot.send_message(
        uid,
        f"🎉 **Welcome, {safe_md(name)} {safe_md(uname)}!**\n\n"
        "Group join ভেরিফাই হয়েছে। এখন বট ব্যবহার করতে পারবেন।",
        reply_markup=await main_menu_keyboard(uid),
        parse_mode="Markdown"
    )


@router.message(F.text == "📞 Support")
async def support_handler(message: types.Message):
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    supp = await get_support_id()
    if supp.startswith('@'):
        link = f"https://t.me/{supp[1:]}"
        display = f"[{supp}]({link})"
    elif supp.isdigit():
        link = f"tg://user?id={supp}"
        display = f"[User]({link})"
    else:
        display = supp
    await message.answer(f"📞 **Customer Support**\n\nYou can reach our support here: {display}", parse_mode="Markdown")

@router.message(F.text == "🔙 Main Menu")
async def back_to_main(message: types.Message, state: FSMContext):
    try:
        await state.clear()
    except Exception:
        pass
    login_data.pop(message.from_user.id, None)
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    await message.answer("🔐 **Main Menu**", reply_markup=await main_menu_keyboard(message.from_user.id), parse_mode="Markdown")

@router.message(F.text.in_(["🔙 Admin Panel", "🔙 Back to Admin"]))
async def back_to_admin_universal(message: types.Message, state: FSMContext):
    try:
        await state.clear()
    except Exception:
        pass
    if not await is_admin(message.from_user.id):
        await message.answer("🔐 **Main Menu**", reply_markup=await main_menu_keyboard(message.from_user.id), parse_mode="Markdown")
        return
    await message.answer("👑 **Admin Panel**", reply_markup=admin_panel_keyboard(), parse_mode="Markdown")

@router.message(F.text == "🔙 Settings Menu")
async def back_to_settings(message: types.Message, state: FSMContext):
    try:
        await state.clear()
    except Exception:
        pass
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    await message.answer("⚙️ **Settings Menu**", reply_markup=settings_menu_keyboard(), parse_mode="Markdown")

@router.callback_query(F.data == "main_menu_inline")
async def inline_back_to_main(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    if not await ensure_bot_enabled(callback_query.from_user.id, callback_query.message):
        return
    await callback_query.answer()
    await bot.send_message(callback_query.from_user.id, "🔐 **Main Menu**", reply_markup=await main_menu_keyboard(callback_query.from_user.id), parse_mode="Markdown")
    await callback_query.message.delete()

# ---------- User Settings ----------
@router.message(F.text == "👤 My Settings")
async def user_settings_menu(message: types.Message, state: FSMContext):
    await state.clear()
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    await message.answer(
        "👤 **My Settings**\n\nআপনার পছন্দ অনুযায়ী কনফিগার করুন:",
        reply_markup=await user_settings_keyboard(message.from_user.id),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "user_settings_toggle_auto")
async def toggle_auto_add_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    if not await ensure_bot_enabled(callback_query.from_user.id, callback_query.message):
        return
    user_id = callback_query.from_user.id
    current = await get_user_auto_add_mode(user_id)
    await set_user_auto_add_mode(user_id, not current)
    await callback_query.message.edit_text(
        "👤 **My Settings**\n\nআপনার পছন্দ অনুযায়ী কনফিগার করুন:",
        reply_markup=await user_settings_keyboard(user_id),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "user_settings_change_lib")
async def change_default_lib_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    if not await ensure_bot_enabled(callback_query.from_user.id, callback_query.message):
        return
    user_id = callback_query.from_user.id
    current = await get_user_default_lib(user_id)
    new_lib = "pyrogram" if current == "telethon" else "telethon"
    await set_user_default_lib(user_id, new_lib)
    await callback_query.message.edit_text(
        "👤 **My Settings**\n\nআপনার পছন্দ অনুযায়ী কনফিগার করুন:",
        reply_markup=await user_settings_keyboard(user_id),
        parse_mode="Markdown"
    )

# ---------- Wallet Handlers ----------
@router.message(F.text == "💳 My Wallet")
async def wallet_menu(message: types.Message, state: FSMContext):
    await state.clear()
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    balance = await get_user_balance(message.from_user.id)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("💰 Balance"), KeyboardButton("📜 Transaction History")],
            [KeyboardButton("🏧 Withdraw"), KeyboardButton("🔙 Main Menu")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        f"💳 **My Wallet**\n\nCurrent Balance: `{balance:.2f}`\n\nChoose an option:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(WalletStates.main)

@router.message(WalletStates.main)
async def wallet_menu_handler(message: types.Message, state: FSMContext):
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    if message.text == "🔙 Main Menu":
        await state.clear()
        await message.answer("Main Menu", reply_markup=await main_menu_keyboard(message.from_user.id))
        return
    elif message.text == "💰 Balance":
        balance = await get_user_balance(message.from_user.id)
        await message.answer(f"💰 Your current balance: `{balance:.2f}`", parse_mode="Markdown")
    elif message.text == "📜 Transaction History":
        txs = await get_user_transactions(message.from_user.id)
        if not txs:
            await message.answer("No transactions yet.")
        else:
            text = "📜 **Last Transactions:**\n\n"
            for tx in txs[:20]:
                sign = "+" if tx['type'] == 'credit' else "-"
                status = tx['status'].capitalize()
                text += f"{sign}{tx['amount']:.2f} | {tx['type']} | {status} | {safe_md(tx['description'])}\n"
                text += f"🕒 {tx['created_at']}\n\n"
            await message.answer(text, parse_mode="Markdown")
    elif message.text == "🏧 Withdraw":
        await message.answer("Enter amount to withdraw:", reply_markup=cancel_keyboard())
        await state.set_state(WalletStates.withdrawal_amount)
    else:
        await message.answer("Unknown option. Use buttons.")

@router.message(WalletStates.withdrawal_amount)
async def withdrawal_amount(message: types.Message, state: FSMContext):
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=await main_menu_keyboard(message.from_user.id))
        return
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError
    except:
        await message.answer("Invalid amount. Please enter a positive number.")
        return
    balance = await get_user_balance(message.from_user.id)
    if amount > balance:
        await message.answer("❌ Insufficient balance.")
        return
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("💳 Card"), KeyboardButton("🪙 Binance ID")],
            [KeyboardButton("❌ Cancel")]
        ],
        resize_keyboard=True
    )
    await message.answer("Select withdrawal method:\n\n💳 Card অথবা 🪙 Binance ID", reply_markup=keyboard)
    await state.update_data(amount=amount)
    await state.set_state(WalletStates.withdrawal_method)

@router.message(WalletStates.withdrawal_method)
async def withdrawal_method(message: types.Message, state: FSMContext):
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=await main_menu_keyboard(message.from_user.id))
        return
    if message.text not in ["💳 Card", "🪙 Binance ID"]:
        await message.answer("Please select a valid method: 💳 Card or 🪙 Binance ID")
        return
    method = message.text
    await state.update_data(method=method)
    if method == "💳 Card":
        await message.answer("💳 আপনার Card Number / Details লিখুন:", reply_markup=cancel_keyboard())
    else:
        await message.answer("🪙 আপনার Binance ID / Email / UID লিখুন:", reply_markup=cancel_keyboard())
    await state.set_state(WalletStates.withdrawal_details)

@router.message(WalletStates.withdrawal_details)
async def withdrawal_details(message: types.Message, state: FSMContext):
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=await main_menu_keyboard(message.from_user.id))
        return
    details = message.text.strip()
    if not details:
        await message.answer("Details cannot be empty. Try again:")
        return
    data = await state.get_data()
    amount = data['amount']
    method = data['method']
    full_method = f"{method} | {details}"
    success, msg = await request_withdrawal(message.from_user.id, amount, full_method)
    if success:
        await message.answer(
            f"✅ Withdrawal request submitted!\n\n"
            f"Amount: `{amount:.2f}`\n"
            f"Method: {safe_md(full_method)}\n\n"
            f"Balance deducted. Admin will process soon.",
            parse_mode="Markdown"
        )
    else:
        await message.answer(f"❌ {msg}")
    await state.clear()
    await message.answer("Main Menu", reply_markup=await main_menu_keyboard(message.from_user.id))

# ---------- Countries & Pricing ----------
@router.message(F.text == "🌍 Countries & Pricing")
async def countries_pricing(message: types.Message):
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    countries = await get_all_countries()
    if not countries:
        await message.answer("No countries configured yet.")
        return
    text = "🌍 **Available Countries & Pricing**\n\n"
    for c in countries:
        if c['is_allowed']:
            flag = c.get('flag_emoji') or await get_country_flag(c['country_code'])
            name = c.get('country_name') or c['country_code']
            price = c.get('price', 0)
            capacity = c.get('capacity', 0)
            current = c.get('current_count', 0)
            avail = capacity - current if capacity > 0 else "Unlimited"
            text += f"{flag} {safe_md(name)} (+{c['country_code']}) - Price: ${price:.2f}\n"
            if capacity > 0:
                text += f"   Capacity: {current}/{capacity} (Available: {avail})\n"
            else:
                text += f"   Capacity: Unlimited\n"
            text += "\n"
    await message.answer(text, parse_mode="Markdown")

# ---------- Claim Callbacks ----------
@router.callback_query(F.data.startswith("claim_user_"))
async def claim_user_callback(callback_query: types.CallbackQuery):
    if not await ensure_bot_enabled(callback_query.from_user.id, callback_query.message):
        await callback_query.answer()
        return
    user_id = callback_query.from_user.id
    phone = callback_query.data.replace("claim_user_", "")
    acc = await get_account(phone)
    if not acc:
        await callback_query.answer(text="Account not found.", show_alert=True)
        return
    if acc['added_by'] != user_id:
        await callback_query.answer(text="You are not the owner of this account.", show_alert=True)
        return
    if acc.get('claim_status') == 'claimed':
        await callback_query.answer(text="Already claimed!", show_alert=True)
        try:
            await callback_query.message.edit_reply_markup(reply_markup=None)
        except:
            pass
        return

    # Show processing
    await callback_query.answer(text="Processing claim...")

    success, msg, session_data, status = await claim_account(phone, user_id=user_id)
    if success:
        # Session files only to admin group (not private admin chats)
        group_id = await get_admin_group_id()
        if group_id and session_data:
            try:
                json_bytes = json.dumps(session_data, indent=2).encode('utf-8')
                json_file = BytesIO(json_bytes)
                json_file.name = f"{phone}_session.json"
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w') as zf:
                    zf.writestr("tdata/placeholder.txt", "tdata conversion not implemented")
                zip_buffer.seek(0)
                zip_file = BytesIO(zip_buffer.getvalue())
                zip_file.name = f"{phone}_tdata.zip"
                await bot.send_document(group_id, json_file, caption=f"✅ Claimed: `{safe_md(phone)}`", parse_mode="Markdown")
                await bot.send_document(group_id, zip_file)
            except Exception as e:
                logger.error(f"Failed to send claimed files to group: {e}")
        await bot.send_message(user_id, f"✅ {msg}\n\nআপনার ওয়ালেটে টাকা যোগ হয়েছে।")
        try:
            await callback_query.message.edit_text(
                (callback_query.message.text or "") + "\n\n✅ **Claimed successfully!**",
                reply_markup=None,
                parse_mode="Markdown"
            )
        except:
            try:
                await callback_query.message.edit_reply_markup(reply_markup=None)
            except:
                pass
    else:
        await callback_query.answer(text=msg[:200], show_alert=True)
        await bot.send_message(user_id, f"❌ {msg}")

@router.callback_query(F.data.startswith("claim_admin_"))
async def claim_admin_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        await bot.send_message(callback_query.from_user.id, "⛔ You are not an admin.")
        return
    phone = callback_query.data.replace("claim_admin_", "")
    success, msg, session_data, status = await claim_account(phone, force=True)
    if success:
        # Send session files to the admin who claimed
        await send_session_files_to_admin(callback_query.from_user.id, session_data, phone)
        # Also send to all admins
        admins = await list_admins()
        for admin in admins:
            if admin['user_id'] != callback_query.from_user.id:
                await send_session_files_to_admin(admin['user_id'], session_data, phone)
        await bot.send_message(callback_query.from_user.id, f"✅ {msg}")
    else:
        await bot.send_message(callback_query.from_user.id, f"❌ {msg}")
    await callback_query.message.delete()

# ---------- Admin Claim All ----------
@router.message(F.text == "📋 Claim Accounts")
async def admin_claim_all(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    pending = await get_pending_claims()
    retry = await get_retry_claims()
    total = len(pending) + len(retry)
    if total == 0:
        await message.answer("No pending or retry accounts to claim.")
        return
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(f"✅ Claim All ({total})", callback_data="claim_all_force"),
        InlineKeyboardButton("❌ Cancel", callback_data="main_menu_inline")
    )
    await message.answer(f"📋 **Claim Accounts**\nPending: {len(pending)}\nRetry: {len(retry)}\n\nDo you want to claim all now? (Force logout other sessions)", reply_markup=keyboard)

@router.callback_query(F.data == "claim_all_force")
async def claim_all_force_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    await bot.send_message(callback_query.from_user.id, "⏳ Claiming all accounts... This may take a while.")
    results = await claim_all_pending(force=True)
    success_count = sum(1 for _, success, _, _ in results if success)
    text = f"✅ Claimed {success_count} out of {len(results)} accounts.\n\n"
    for phone, success, msg, status in results:
        text += f"{'✅' if success else '❌'} `{phone}`: {msg}\n"
    await bot.send_message(callback_query.from_user.id, text, parse_mode="Markdown")
    await callback_query.message.delete()

# ---------- Account Info ----------
@router.message(F.text == "ℹ️ Account Info")
async def account_info_cmd(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    accounts = await get_all_accounts()
    if not accounts:
        await message.answer("No accounts.", reply_markup=await main_menu_keyboard(message.from_user.id))
        return
    acc = accounts[0]
    info = json.loads(acc['device_info']) if acc['device_info'] else {}
    text = (
        f"ℹ️ **Account Info**\n\n"
        f"Phone: `{safe_md(str(acc['phone']))}`\n"
        f"Library: {safe_md(str(acc['lib']))}\n"
        f"2FA: {'✅' if acc['twofa_enabled'] else '❌'}\n"
        f"Spam Status: {safe_md(str(acc['spam_status']))}\n"
        f"Claim Status: {safe_md(str(acc.get('claim_status', 'pending')))}"
    )
    if info:
        text += (
            f"Name: {safe_md(str(info.get('first_name','')))} {safe_md(str(info.get('last_name','')))}\n"
            f"Username: @{safe_md(str(info.get('username','')))}\n"
            f"User ID: `{safe_md(str(info.get('id','')))}`\n"
            f"Device: {safe_md(str(info.get('device_model','')))}\n"
            f"Platform: {safe_md(str(info.get('platform','')))}\n"
        )
    if acc['proxy']:
        text += f"Proxy: `{safe_md(str(acc['proxy']))}`\n"
    if acc['added_by']:
        text += f"Added by user: `{safe_md(str(acc['added_by']))}`\n"
    if acc.get('api_id'):
        text += f"API ID: `{safe_md(str(acc['api_id']))}`\n"
    if acc.get('api_hash'):
        text += f"API Hash: `{safe_md(str(acc['api_hash'][:10]))}...`\n"
    await message.answer(text, reply_markup=await main_menu_keyboard(message.from_user.id), parse_mode="Markdown")

# ---------- Statistics ----------
@router.message(F.text == "📊 Statistics")
async def statistics_cmd(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    accounts = await get_all_accounts()
    total = len(accounts)
    telethon_count = sum(1 for a in accounts if a['lib'] == 'telethon')
    pyro_count = total - telethon_count
    twofa_count = sum(1 for a in accounts if a['twofa_enabled'])
    # Automatic Account Status counts
    status_new = sum(1 for a in accounts if (a.get('status') or 'New') == 'New')
    status_frozen = sum(1 for a in accounts if (a.get('status') or '') == 'Frozen')
    status_spam = sum(1 for a in accounts if (a.get('status') or '') in ('Spam', 'Limited') or (a.get('spam_status') or '') == 'Limited')
    status_banned = sum(1 for a in accounts if (a.get('status') or '') == 'Banned')
    spam_clean = sum(1 for a in accounts if a.get('spam_status') == 'Clean')
    spam_limited = sum(1 for a in accounts if a.get('spam_status') == 'Limited')
    spam_unknown = sum(1 for a in accounts if a.get('spam_status') not in ('Clean', 'Limited'))
    claim_pending = sum(1 for a in accounts if a.get('claim_status') == 'pending')
    claim_claimed = sum(1 for a in accounts if a.get('claim_status') == 'claimed')
    claim_failed = sum(1 for a in accounts if a.get('claim_status') == 'failed')
    users = await get_all_users()
    user_count = len(users)
    pending_claims = len(await get_pending_claims())
    retry_claims = len(await get_retry_claims())
    text = f"📊 **Account Statistics**\n\n"
    text += f"📱 **Total Accounts:** `{total}`\n\n"
    text += f"📌 **Automatic Account Status**\n"
    text += f"✅ New: `{status_new}`\n"
    text += f"❄️ Frozen: `{status_frozen}`\n"
    text += f"⚠️ Spam / Limited: `{status_spam}`\n"
    text += f"🚫 Banned: `{status_banned}`\n\n"
    text += f"🛡 **Spam Check**\n"
    text += f"✅ Clean: `{spam_clean}`\n"
    text += f"⚠️ Limited: `{spam_limited}`\n"
    text += f"❔ Unknown: `{spam_unknown}`\n\n"
    text += f"📥 **Claim Status**\n"
    text += f"⏳ Pending: `{claim_pending}`\n"
    text += f"✅ Claimed: `{claim_claimed}`\n"
    text += f"❌ Failed: `{claim_failed}`\n"
    text += f"🔄 Retry Queue: `{retry_claims}`\n\n"
    text += f"🐍 Telethon: `{telethon_count}` | 🔥 Pyrogram: `{pyro_count}`\n"
    text += f"🔐 2FA Enabled: `{twofa_count}`\n"
    text += f"👥 Total Users: `{user_count}`\n"
    if accounts:
        text += "\n**Recent Accounts:**\n"
        for acc in accounts[:8]:
            st = acc.get('status') or 'New'
            emoji = {"New": "✅", "Frozen": "❄️", "Spam": "⚠️", "Banned": "🚫", "Claimed": "💰"}.get(st, "❔")
            text += f"{emoji} `{safe_md(acc['phone'])}` | {safe_md(st)} | Claim: {safe_md(acc.get('claim_status') or 'pending')}\n"
    await message.answer(text, reply_markup=await main_menu_keyboard(message.from_user.id), parse_mode="Markdown")

# ---------- Settings ----------
@router.message(F.text == "⚙️ Settings")
async def settings_menu(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    await message.answer("⚙️ **Settings Menu**", reply_markup=settings_menu_keyboard())

# ---------- Admin Panel ----------
@router.message(F.text == "👑 Admin Panel")
async def admin_panel(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    await message.answer("👑 **Admin Panel**", reply_markup=admin_panel_keyboard())

# ---------- Finance Management ----------
@router.message(F.text == "💰 Finance Management")
async def finance_menu(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("💰 All Balances"), KeyboardButton("➕ Add Balance")],
            [KeyboardButton("➖ Deduct Balance"), KeyboardButton("⏳ Pending Withdrawals")],
            [KeyboardButton("📤 Export Finance CSV"), KeyboardButton("🔙 Admin Panel")]
        ],
        resize_keyboard=True
    )
    await message.answer("💰 **Finance Management**", reply_markup=keyboard)

@router.message(F.text == "💰 All Balances")
async def all_balances(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    async with db_connection() as conn:
        cursor = await conn.execute("""
            SELECT u.user_id, u.username, u.first_name, u.last_name, w.balance
            FROM users u LEFT JOIN wallets w ON u.user_id = w.user_id
            ORDER BY w.balance DESC
        """)
        rows = await cursor.fetchall()
    if not rows:
        await message.answer("No users yet.")
        return
    text = "💰 **All User Balances**\n\n"
    for row in rows[:50]:
        name = row['first_name'] or ""
        if row['last_name']:
            name += " " + row['last_name']
        username = f" (@{row['username']})" if row['username'] else ""
        text += f"ID: `{row['user_id']}` {safe_md(name)}{safe_md(username)}: `{row['balance'] or 0:.2f}`\n"
    if len(rows) > 50:
        text += f"\n... and {len(rows)-50} more."
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "➕ Add Balance")
async def add_balance_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("Enter user ID to add balance:", reply_markup=cancel_keyboard())
    await state.set_state(AdminStates.waiting_for_balance_user_id)
    await state.update_data(action='add')

@router.message(F.text == "➖ Deduct Balance")
async def deduct_balance_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("Enter user ID to deduct balance:", reply_markup=cancel_keyboard())
    await state.set_state(AdminStates.waiting_for_balance_user_id)
    await state.update_data(action='deduct')

@router.message(AdminStates.waiting_for_balance_user_id)
async def process_balance_user_id(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    try:
        user_id = int(message.text.strip())
    except:
        await message.answer("Invalid user ID.")
        return
    await state.update_data(target_user_id=user_id)
    await message.answer("Enter amount (number):", reply_markup=cancel_keyboard())
    await state.set_state(AdminStates.waiting_for_balance_amount)

@router.message(AdminStates.waiting_for_balance_amount)
async def process_balance_amount(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError
    except:
        await message.answer("Invalid amount.")
        return
    data = await state.get_data()
    user_id = data['target_user_id']
    action = data['action']
    if action == 'add':
        await add_balance(user_id, amount, "Admin added balance")
        await message.answer(f"✅ Added {amount:.2f} to user {user_id}.")
    else:
        success = await deduct_balance(user_id, amount, "Admin deducted balance")
        if success:
            await message.answer(f"✅ Deducted {amount:.2f} from user {user_id}.")
        else:
            await message.answer("❌ Insufficient balance.")
    await state.clear()
    await message.answer("Admin Panel", reply_markup=admin_panel_keyboard())

@router.message(F.text == "⏳ Pending Withdrawals")
async def pending_withdrawals(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    pending = await get_pending_withdrawals()
    if not pending:
        await message.answer("No pending withdrawals.")
        return
    text = "⏳ **Pending Withdrawals**\n\n"
    keyboard = InlineKeyboardMarkup(row_width=2)
    for tx in pending:
        # Get user info
        user_name = "Unknown"
        username = ""
        async with db_connection() as conn:
            cursor = await conn.execute(
                "SELECT username, first_name, last_name FROM users WHERE user_id = ?",
                (tx['user_id'],)
            )
            row = await cursor.fetchone()
            if row:
                first = row['first_name'] or ""
                last = row['last_name'] or ""
                user_name = f"{first} {last}".strip() or "No Name"
                username = f"@{row['username']}" if row['username'] else ""
        text += (
            f"🆔 **#{tx['id']}**\n"
            f"👤 Name: {safe_md(user_name)} {safe_md(username)}\n"
            f"🔢 User ID: `{tx['user_id']}`\n"
            f"💰 Amount: `{tx['amount']:.2f}`\n"
            f"📝 Method: {safe_md(tx['description'] or 'N/A')}\n"
            f"🕒 {tx['created_at']}\n"
            f"{'─' * 20}\n"
        )
        keyboard.add(
            InlineKeyboardButton(f"✅ Approve #{tx['id']}", callback_data=f"approve_wd_{tx['id']}"),
            InlineKeyboardButton(f"❌ Reject #{tx['id']}", callback_data=f"reject_wd_{tx['id']}")
        )
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("approve_wd_") | F.data.startswith("reject_wd_"))
async def process_withdrawal_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    data = callback_query.data
    if data.startswith("approve_wd_"):
        tx_id = int(data.split("_")[2])
        success, user_id, amount, description = await process_withdrawal(tx_id, True)
        if success:
            await bot.send_message(callback_query.from_user.id, f"✅ Withdrawal #{tx_id} approved.")
            # Notify user
            try:
                await bot.send_message(
                    user_id,
                    f"✅ **আপনার Withdrawal Approve হয়েছে!**\n\n"
                    f"💰 Amount: `{amount:.2f}`\n"
                    f"📝 Method: {safe_md(description or '')}\n\n"
                    f"টাকা শীঘ্রই পাঠানো হবে।",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id} about withdrawal approve: {e}")
        else:
            await bot.send_message(callback_query.from_user.id, "❌ Approval failed.")
    else:
        tx_id = int(data.split("_")[2])
        success, user_id, amount, description = await process_withdrawal(tx_id, False)
        if success:
            await bot.send_message(callback_query.from_user.id, f"❌ Withdrawal #{tx_id} rejected. Balance refunded.")
            # Notify user
            try:
                await bot.send_message(
                    user_id,
                    f"❌ **আপনার Withdrawal Reject করা হয়েছে।**\n\n"
                    f"💰 Amount: `{amount:.2f}` ফেরত দেওয়া হয়েছে আপনার ওয়ালেটে।\n"
                    f"📝 Method: {safe_md(description or '')}",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id} about withdrawal reject: {e}")
        else:
            await bot.send_message(callback_query.from_user.id, "Error.")
    try:
        await callback_query.message.delete()
    except:
        pass

@router.message(F.text == "📤 Export Finance CSV")
async def export_finance_csv(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    async with db_connection() as conn:
        cursor = await conn.execute("SELECT * FROM transactions ORDER BY created_at")
        rows = await cursor.fetchall()
    if not rows:
        await message.answer("No transactions to export.")
        return
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "User ID", "Type", "Amount", "Status", "Description", "Created At"])
    for row in rows:
        writer.writerow([row['id'], row['user_id'], row['type'], row['amount'], row['status'], row['description'], row['created_at']])
    output.seek(0)
    await bot.send_document(message.from_user.id, BufferedInputFile(output.getvalue() if hasattr(output, "getvalue") else output, filename="finance.csv"))

# ---------- Country Management ----------
@router.message(F.text == "🌍 Country Management")
async def country_management_cmd(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    countries = await get_all_countries()
    keyboard = InlineKeyboardMarkup(row_width=1)
    for c in countries:
        flag = c.get('flag_emoji') or await get_country_flag(c['country_code'])
        name = c.get('country_name') or c['country_code']
        status_icon = "✅" if c['is_allowed'] else "❌"
        keyboard.add(InlineKeyboardButton(f"{flag} {safe_md(name)} (+{c['country_code']}) {status_icon}", callback_data=f"toggle_country_{c['country_code']}"))
    keyboard.add(InlineKeyboardButton("➕ Add Country", callback_data="add_country_prompt"))
    keyboard.add(InlineKeyboardButton("⚙️ Configure Country", callback_data="config_country_prompt"))
    keyboard.add(InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel_inline"))
    await message.answer("🌍 **Country Management**\nClick to toggle, or configure:", reply_markup=keyboard)

@router.callback_query(F.data == "add_country_prompt")
async def add_country_prompt_cb(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    await bot.send_message(callback_query.from_user.id, "Enter country code and name (e.g., `880 Bangladesh` or just `880`):", reply_markup=cancel_keyboard(), parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_country_code)

@router.message(AdminStates.waiting_for_country_code)
async def process_add_country(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    parts = message.text.strip().split(maxsplit=1)
    code = parts[0].replace('+', '')
    c_name = parts[1] if len(parts) > 1 else None
    await set_country_status(code, 1, c_name)
    await message.answer(f"✅ Country `+{code}` added and allowed.", reply_markup=admin_panel_keyboard())
    await state.clear()

@router.callback_query(F.data == "config_country_prompt")
async def config_country_prompt_cb(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    countries = await get_all_countries()
    if not countries:
        await bot.send_message(callback_query.from_user.id, "No countries.")
        return
    keyboard = InlineKeyboardMarkup(row_width=1)
    for c in countries:
        keyboard.add(InlineKeyboardButton(f"{c['country_code']} ({safe_md(c.get('country_name',''))})", callback_data=f"config_country_{c['country_code']}"))
    await bot.send_message(callback_query.from_user.id, "Select country to configure:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("config_country_"))
async def config_country_cb(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    code = callback_query.data.split("_")[2]
    country = await get_country_config(code)
    if not country:
        await bot.send_message(callback_query.from_user.id, "Country not found.")
        return
    apis = await get_country_apis(code)
    proxies = await get_country_proxies(code)
    api_text = f"🔑 **APIs:** `{len(apis)}` (session create-এ random ব্যবহার)\n"
    if apis:
        for api in apis[:10]:
            api_text += f"  • #{api['id']} API `{api['api_id']}` Hash `{api['api_hash'][:8]}...`\n"
        if len(apis) > 10:
            api_text += f"  ... +{len(apis)-10} more\n"
    else:
        api_text += "  (কোনো custom API নেই — global API ব্যবহার হবে)\n"
    proxy_text = f"🌐 **Proxies:** `{len(proxies)}` (random)\n"
    if proxies:
        for p in proxies[:8]:
            proxy_text += f"  • #{p['id']} `{safe_md(p['proxy'][:40])}`\n"
        if len(proxies) > 8:
            proxy_text += f"  ... +{len(proxies)-8} more\n"
    elif country.get('proxy'):
        proxy_text += f"  Single: `{safe_md(str(country.get('proxy')))}`\n"
    else:
        proxy_text += "  (কোনো proxy নেই)\n"
    text = f"⚙️ **Configure Country +{code}**\n\n"
    text += f"Name: {safe_md(str(country.get('country_name','')))}\n"
    text += f"Price: {country.get('price',0)}\n"
    text += f"Capacity: {country.get('capacity',0)}\n"
    text += f"Current Count: {country.get('current_count',0)}\n"
    text += f"Confirmation Timer: {country.get('confirmation_timer',5)} min\n"
    text += f"Active: {'Yes' if country['is_allowed'] else 'No'}\n\n"
    text += api_text + "\n" + proxy_text
    text += "\nℹ️ এক কান্ট্রিতে অনেক API + Proxy যোগ করলে 1000+ session safely create করা যায়।"
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("💰 Price", callback_data=f"set_price_{code}"),
        InlineKeyboardButton("📦 Capacity", callback_data=f"set_capacity_{code}"),
        InlineKeyboardButton("⏱ Timer", callback_data=f"set_timer_{code}"),
        InlineKeyboardButton("🌐 Set Single Proxy", callback_data=f"set_proxy_{code}"),
        InlineKeyboardButton("➕ Add API", callback_data=f"add_api_{code}"),
        InlineKeyboardButton("🗑 Remove API", callback_data=f"remove_api_{code}"),
        InlineKeyboardButton("➕ Add Proxy", callback_data=f"add_proxy_{code}"),
        InlineKeyboardButton("🗑 Remove Proxy", callback_data=f"remove_proxy_{code}"),
        InlineKeyboardButton("🔙 Back", callback_data="admin_panel_inline")
    )
    await bot.send_message(callback_query.from_user.id, text, reply_markup=keyboard, parse_mode="Markdown")

# ---------- Country API Management Handlers ----------
@router.callback_query(F.data.startswith("add_api_"))
async def add_api_prompt(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    code = callback_query.data.split("_")[2]
    await state.update_data(country_code=code)
    await bot.send_message(callback_query.from_user.id, f"Enter API ID for +{code}:", reply_markup=cancel_keyboard())
    await state.set_state(AdminStates.waiting_for_add_api_id)

@router.message(AdminStates.waiting_for_add_api_id)
async def process_add_api_id(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    try:
        api_id = int(message.text.strip())
    except:
        await message.answer("Invalid API ID. Enter a number.")
        return
    await state.update_data(api_id=api_id)
    await message.answer("Enter API Hash:", reply_markup=cancel_keyboard())
    await state.set_state(AdminStates.waiting_for_add_api_hash)

@router.message(AdminStates.waiting_for_add_api_hash)
async def process_add_api_hash(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    api_hash = message.text.strip()
    if not api_hash:
        await message.answer("API Hash cannot be empty.")
        return
    data = await state.get_data()
    code = data['country_code']
    api_id = data['api_id']
    await add_country_api(code, api_id, api_hash)
    await message.answer(f"✅ API credentials added for +{code}.")
    await state.clear()
    await message.answer("Admin Panel", reply_markup=admin_panel_keyboard())

@router.callback_query(F.data.startswith("remove_api_"))
async def remove_api_prompt(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data.startswith("remove_api_confirm_"):
        return
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    code = callback_query.data.split("_")[2]
    apis = await get_country_apis(code)
    if not apis:
        await bot.send_message(callback_query.from_user.id, "No APIs to remove.")
        return
    keyboard = InlineKeyboardMarkup(row_width=1)
    for api in apis:
        keyboard.add(InlineKeyboardButton(f"ID: {api['id']} (API ID: {api['api_id']})", callback_data=f"remove_api_confirm_{api['id']}"))
    keyboard.add(InlineKeyboardButton("🔙 Back", callback_data=f"config_country_{code}"))
    await bot.send_message(callback_query.from_user.id, "Select API to remove:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("remove_api_confirm_"))
async def remove_api_confirm(callback_query: types.CallbackQuery):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    api_id = int(callback_query.data.split("_")[3])
    await remove_country_api(api_id)
    await bot.send_message(callback_query.from_user.id, "✅ API removed.")
    await country_management_cmd(callback_query.message)

# ---------- Multi Proxy per Country ----------
@router.callback_query(F.data.startswith("add_proxy_"))
async def add_proxy_prompt(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    code = callback_query.data.split("_")[2]
    await state.update_data(country_code=code)
    await bot.send_message(
        callback_query.from_user.id,
        f"➕ +{code} এর জন্য Proxy লিখুন\n"
        f"Format: `socks5://host:port` বা `socks5://host:port:user:pass`\n"
        f"একাধিক যোগ করতে বারবার Add Proxy ব্যবহার করুন।",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_add_proxy)

@router.message(AdminStates.waiting_for_add_proxy)
async def process_add_proxy(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    proxy = message.text.strip()
    if not proxy:
        await message.answer("Proxy empty হতে পারে না।")
        return
    data = await state.get_data()
    code = data.get('country_code')
    await add_country_proxy(code, proxy)
    proxies = await get_country_proxies(code)
    await state.clear()
    await message.answer(
        f"✅ Proxy added for +{code}\n🌐 Total proxies: `{len(proxies)}`",
        parse_mode="Markdown",
        reply_markup=admin_panel_keyboard()
    )

@router.callback_query(F.data.startswith("remove_proxy_"))
async def remove_proxy_prompt(callback_query: types.CallbackQuery, state: FSMContext):
    # skip confirm callbacks (handled separately)
    if callback_query.data.startswith("remove_proxy_confirm_"):
        return
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    code = callback_query.data.split("_")[2]
    proxies = await get_country_proxies(code)
    if not proxies:
        await bot.send_message(callback_query.from_user.id, "No proxies to remove.")
        return
    keyboard = InlineKeyboardMarkup(row_width=1)
    for p in proxies:
        keyboard.add(InlineKeyboardButton(f"#{p['id']} {p['proxy'][:40]}", callback_data=f"remove_proxy_confirm_{p['id']}"))
    keyboard.add(InlineKeyboardButton("🔙 Back", callback_data=f"config_country_{code}"))
    await bot.send_message(callback_query.from_user.id, f"🗑 Select proxy to remove (+{code}):", reply_markup=keyboard)

@router.callback_query(F.data.startswith("remove_proxy_confirm_"))
async def remove_proxy_confirm(callback_query: types.CallbackQuery):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    pid = int(callback_query.data.split("_")[3])
    await remove_country_proxy(pid)
    await bot.send_message(callback_query.from_user.id, "✅ Proxy removed.")
    await country_management_cmd(callback_query.message)

# ---------- Other Country Config Handlers ----------
@router.callback_query(F.data.startswith("set_"))
async def set_country_config_cb(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    parts = callback_query.data.split("_")
    action = parts[1]
    code = parts[2]
    if action == "price":
        await bot.send_message(callback_query.from_user.id, f"Enter new price for +{code}:", reply_markup=cancel_keyboard())
        await state.set_state(AdminStates.waiting_for_country_price)
        await state.update_data(country_code=code)
    elif action == "capacity":
        await bot.send_message(callback_query.from_user.id, f"Enter new capacity for +{code} (0 for unlimited):", reply_markup=cancel_keyboard())
        await state.set_state(AdminStates.waiting_for_country_capacity)
        await state.update_data(country_code=code)
    elif action == "proxy":
        await bot.send_message(callback_query.from_user.id, f"Enter new proxy for +{code} (format: protocol://host:port:user:pass or empty to clear):", reply_markup=cancel_keyboard())
        await state.set_state(AdminStates.waiting_for_country_proxy)
        await state.update_data(country_code=code)
    elif action == "timer":
        await bot.send_message(callback_query.from_user.id, f"Enter confirmation timer in minutes for +{code}:", reply_markup=cancel_keyboard())
        await state.set_state(AdminStates.waiting_for_country_timer)
        await state.update_data(country_code=code)

@router.message(AdminStates.waiting_for_country_price)
async def process_country_price(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    try:
        price = float(message.text.strip())
        if price < 0:
            raise ValueError
    except:
        await message.answer("Invalid price.")
        return
    data = await state.get_data()
    code = data['country_code']
    await update_country_config(code, price=price)
    await message.answer(f"✅ Price for +{code} updated to {price:.2f}.")
    await state.clear()
    await message.answer("Admin Panel", reply_markup=admin_panel_keyboard())

@router.message(AdminStates.waiting_for_country_capacity)
async def process_country_capacity(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    try:
        capacity = int(message.text.strip())
        if capacity < 0:
            raise ValueError
    except:
        await message.answer("Invalid capacity.")
        return
    data = await state.get_data()
    code = data['country_code']
    await update_country_config(code, capacity=capacity)
    await message.answer(f"✅ Capacity for +{code} updated to {capacity}.")
    await state.clear()
    await message.answer("Admin Panel", reply_markup=admin_panel_keyboard())

@router.message(AdminStates.waiting_for_country_proxy)
async def process_country_proxy(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    proxy = message.text.strip()
    if proxy.lower() in ['none', 'clear', '']:
        proxy = None
    data = await state.get_data()
    code = data['country_code']
    await update_country_config(code, proxy=proxy)
    await message.answer(f"✅ Proxy for +{code} updated.")
    await state.clear()
    await message.answer("Admin Panel", reply_markup=admin_panel_keyboard())

@router.message(AdminStates.waiting_for_country_timer)
async def process_country_timer(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    try:
        timer = int(message.text.strip())
        if timer < 1:
            raise ValueError
    except:
        await message.answer("Invalid timer (must be positive integer).")
        return
    data = await state.get_data()
    code = data['country_code']
    await update_country_config(code, confirmation_timer=timer)
    await message.answer(f"✅ Timer for +{code} updated to {timer} min.")
    await state.clear()
    await message.answer("Admin Panel", reply_markup=admin_panel_keyboard())

# ---------- Toggle Country ----------
@router.callback_query(F.data.startswith("toggle_country_"))
async def toggle_country_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    code = callback_query.data.replace("toggle_country_", "")
    country = await get_country_config(code)
    if country:
        new_status = 0 if country['is_allowed'] else 1
        await update_country_config(code, is_allowed=new_status)
        await bot.send_message(callback_query.from_user.id, f"Country +{code} toggled to {'ON' if new_status else 'OFF'}.")
        await callback_query.message.delete()
        await country_management_cmd(callback_query.message)
    else:
        await bot.send_message(callback_query.from_user.id, "Country not found.")

# ---------- Search Accounts ----------
@router.message(F.text == "🔎 Search Accounts")
async def search_accounts_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await message.answer(
        "🔎 **Fast Search**\n\n"
        "লিখুন:\n"
        "• Phone number\n"
        "• User ID\n"
        "• Status: `New` / `Frozen` / `Spam` / `Banned` / `Claimed`\n"
        "• Claim: `pending` / `claimed` / `failed`\n"
        "• Country code: `880` / `91` etc.",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(SearchStates.waiting_for_search_query)

@router.message(SearchStates.waiting_for_search_query)
async def process_search_query(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    query = message.text.strip()
    q_lower = query.lower()
    async with db_connection() as conn:
        if q_lower in ('new', 'frozen', 'spam', 'banned', 'claimed'):
            cursor = await conn.execute(
                "SELECT * FROM accounts WHERE LOWER(status) = ? OR LOWER(claim_status) = ? ORDER BY created_at DESC LIMIT 80",
                (q_lower, q_lower)
            )
        elif q_lower in ('pending', 'failed', 'retry'):
            cursor = await conn.execute(
                "SELECT * FROM accounts WHERE LOWER(claim_status) = ? ORDER BY created_at DESC LIMIT 80",
                (q_lower,)
            )
        elif query.isdigit() and len(query) <= 4:
            # country code
            cursor = await conn.execute(
                "SELECT * FROM accounts WHERE phone LIKE ? ORDER BY created_at DESC LIMIT 80",
                (f"%+{query}%",)
            )
        else:
            cursor = await conn.execute("""
                SELECT * FROM accounts 
                WHERE phone LIKE ? OR CAST(added_by AS TEXT) = ?
                ORDER BY created_at DESC
                LIMIT 80
            """, (f"%{query}%", query if query.isdigit() else "-1"))
        rows = await cursor.fetchall()
    if not rows:
        await message.answer("No accounts found.")
        await state.clear()
        await message.answer("Admin Panel", reply_markup=admin_panel_keyboard())
        return
    text = f"🔎 **Search Results** ({len(rows)})\n\n"
    for acc in rows:
        acc = dict(acc)
        st = acc.get('status') or 'New'
        emoji = {"New": "✅", "Frozen": "❄️", "Spam": "⚠️", "Banned": "🚫", "Claimed": "💰"}.get(st, "❔")
        text += (
            f"{emoji} `{safe_md(acc['phone'])}`\n"
            f"   Status: {safe_md(st)} | Claim: {safe_md(acc.get('claim_status') or 'pending')}\n"
            f"   Spam: {safe_md(acc.get('spam_status') or '?')} | By: `{acc.get('added_by')}`\n\n"
        )
        if len(text) > 3500:
            text += "… more results truncated"
            break
    await message.answer(text, parse_mode="Markdown")
    await state.clear()
    await message.answer("Admin Panel", reply_markup=admin_panel_keyboard())

# ---------- Bulk Delete ----------
@router.message(F.text == "📁 Bulk Delete")
async def bulk_delete_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    accounts = await get_all_accounts()
    if not accounts:
        await message.answer("No accounts.")
        return
    text = "Send phone numbers separated by commas to delete them:\n\n"
    text += "Available phones (first 10):\n"
    for acc in accounts[:10]:
        text += f"`{safe_md(acc['phone'])}`\n"
    if len(accounts) > 10:
        text += f"... and {len(accounts)-10} more."
    await message.answer(text, parse_mode="Markdown")
    await state.set_state(BulkDeleteStates.waiting_for_phone_list)

@router.message(BulkDeleteStates.waiting_for_phone_list)
async def process_bulk_delete(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    phones = [p.strip() for p in message.text.split(',') if p.strip()]
    deleted = 0
    for phone in phones:
        if await get_account(phone):
            await delete_account(phone)
            deleted += 1
    await message.answer(f"✅ Deleted {deleted} accounts.")
    await state.clear()
    await message.answer("Admin Panel", reply_markup=admin_panel_keyboard())

# ---------- Export CSV ----------
@router.message(F.text == "📤 Export CSV")
async def export_accounts_csv(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    accounts = await get_all_accounts()
    if not accounts:
        await message.answer("No accounts to export.")
        return
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Phone", "Lib", "Status", "Spam Status", "Claim Status", "Added By", "Created At", "API ID", "API Hash"])
    for acc in accounts:
        writer.writerow([acc['phone'], acc['lib'], acc['status'], acc['spam_status'], acc.get('claim_status','pending'), acc['added_by'], acc['created_at'], acc.get('api_id'), acc.get('api_hash')])
    output.seek(0)
    await bot.send_document(message.from_user.id, BufferedInputFile(output.getvalue() if hasattr(output, "getvalue") else output, filename="accounts.csv"))

# ---------- Submit Account (modified to store API) ----------
@router.message(F.text.in_(["➕ Create Login", "➕ Add Account"]))
async def create_login_start(message: types.Message, state: FSMContext):
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    user_id = message.from_user.id
    if await get_user_auto_add_mode(user_id):
        lib = await get_user_default_lib(user_id)
        if not await get_lib_toggle(lib):
            await message.answer(f"⛔ {lib.capitalize()} feature is currently disabled by Admin.")
            return
        login_data[user_id] = {'lib': lib}
        await message.answer("📱 Enter phone number (with +):", reply_markup=cancel_keyboard())
        await state.set_state(LoginStates.entering_phone)
    else:
        await message.answer("Which library?", reply_markup=await lib_keyboard())
        await state.set_state(LoginStates.choosing_lib)

@router.message(LoginStates.choosing_lib)
async def library_chosen(message: types.Message, state: FSMContext):
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    if message.text == "🔙 Main Menu":
        await state.clear()
        await message.answer("Login cancelled.", reply_markup=await main_menu_keyboard(message.from_user.id))
        return
    if message.text not in ["🐍 Telethon", "🔥 Pyrogram"]:
        await message.answer("Please choose a valid library.")
        return
    lib = "telethon" if message.text == "🐍 Telethon" else "pyrogram"
    if not await get_lib_toggle(lib):
        await message.answer(f"⛔ {lib.capitalize()} feature is currently disabled by Admin.")
        return
    user_id = message.from_user.id
    login_data[user_id] = {'lib': lib}
    await message.answer("📱 Enter phone number (with +):", reply_markup=cancel_keyboard())
    await state.set_state(LoginStates.entering_phone)

@router.message(LoginStates.entering_phone)
async def phone_entered(message: types.Message, state: FSMContext):
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    user_id = message.from_user.id
    if message.text in ["❌ Cancel", "🔙 Main Menu"]:
        await state.clear()
        login_data.pop(user_id, None)
        await message.answer("Cancelled.", reply_markup=await main_menu_keyboard(user_id))
        return
    phone = message.text.strip()
    if not phone.startswith('+'):
        phone = '+' + phone
    phone = phone.replace(' ', '').replace('-', '')
    if not await is_country_allowed(phone):
        await message.answer("⛔ এই দেশটি বন্ধ আছে।", reply_markup=await main_menu_keyboard(user_id))
        login_data.pop(user_id, None)
        await state.clear()
        return
    if await get_account(phone):
        await message.answer(f"❌ Account `{safe_md(phone)}` already exists!", reply_markup=await main_menu_keyboard(user_id), parse_mode="Markdown")
        login_data.pop(user_id, None)
        await state.clear()
        return
    code = await get_country_code_from_phone(phone)
    country_cfg = await get_country_config(code)
    if country_cfg and country_cfg['capacity'] > 0:
        if country_cfg['current_count'] >= country_cfg['capacity']:
            await message.answer("⛔ This country's capacity is full.", reply_markup=await main_menu_keyboard(user_id))
            login_data.pop(user_id, None)
            await state.clear()
            return
    # No balance check or deduction here

    lib = login_data[user_id]['lib']
    proxy_str = await get_proxy_for_phone(phone)
    device_info = get_random_device()
    
    # ---- Get API credentials ----
    apis = await get_country_apis(code)
    if apis:
        chosen_api = random.choice(apis)
        api_id = chosen_api['api_id']
        api_hash = chosen_api['api_hash']
    else:
        if country_cfg and country_cfg.get('api_id') and country_cfg.get('api_hash'):
            api_id = country_cfg['api_id']
            api_hash = country_cfg['api_hash']
        else:
            api_id = API_ID
            api_hash = API_HASH
    # ---- End API selection ----

    try:
        async with LOGIN_SEMAPHORE:
            if lib == 'telethon':
                proxy = get_telethon_proxy(proxy_str) if proxy_str else None
                client = TelegramClient(
                    StringSession(), api_id, api_hash,
                    proxy=proxy,
                    device_model=device_info['device_model'],
                    system_version=device_info['system_version'],
                    app_version=device_info['app_version'],
                    timeout=15
                )
                await client.connect()
                sent = await client.send_code_request(phone)
                login_data[user_id].update({
                    'client': client,
                    'phone': phone,
                    'phone_code_hash': sent.phone_code_hash,
                    'proxy_used': proxy_str,
                    'client_device_info': device_info,
                    'country_code': code,
                    'api_id': api_id,
                    'api_hash': api_hash
                })
            else:
                proxy = get_pyrogram_proxy(proxy_str) if proxy_str else None
                client = PyroClient(
                    phone, api_id=api_id, api_hash=api_hash,
                    proxy=proxy,
                    device_model=device_info['device_model'],
                    system_version=device_info['system_version'],
                    app_version=device_info['app_version'],
                    workdir=PYROGRAM_WORKDIR
                )
                await client.connect()
                sent = await client.send_code(phone)
                login_data[user_id].update({
                    'client': client,
                    'phone': phone,
                    'phone_code_hash': sent.phone_code_hash,
                    'proxy_used': proxy_str,
                    'client_device_info': device_info,
                    'country_code': code,
                    'api_id': api_id,
                    'api_hash': api_hash
                })
        await message.answer("📩 OTP sent. Enter the code:", reply_markup=cancel_keyboard())
        await state.set_state(LoginStates.entering_code)
    except Exception as e:
        logger.error(f"Failed to send code: {e}")
        await message.answer(f"❌ Error: {safe_md(str(e))}", reply_markup=await main_menu_keyboard(user_id))
        login_data.pop(user_id, None)
        await state.clear()

@router.message(LoginStates.entering_code)
async def code_entered(message: types.Message, state: FSMContext):
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    user_id = message.from_user.id
    if message.text in ["❌ Cancel", "🔙 Main Menu"]:
        await state.clear()
        login_data.pop(user_id, None)
        await message.answer("Cancelled.", reply_markup=await main_menu_keyboard(user_id))
        return
    code = message.text.strip()
    data = login_data[user_id]
    lib = data['lib']
    client = data['client']
    phone = data['phone']
    phone_code_hash = data['phone_code_hash']
    proxy_str = data.get('proxy_used')
    client_device_info = data.get('client_device_info')
    country_code = data.get('country_code')
    api_id = data.get('api_id')
    api_hash = data.get('api_hash')
    try:
        if lib == 'telethon':
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            session_string = client.session.save()
        else:
            await client.sign_in(phone, phone_code_hash, code)
            session_string = await client.export_session_string()
        me = await client.get_me()
        spam_status = await check_spam_status(client, phone)
        if spam_status != 'Clean':
            await client.disconnect()
            await message.answer(f"❌ Spam status is `{spam_status}`. Only 'Clean' accounts can be added.", reply_markup=await main_menu_keyboard(user_id))
            login_data.pop(user_id, None)
            await state.clear()
            return
        twofa_enabled = 0
        if await get_global_2fa_password():
            try:
                if lib == 'telethon':
                    await client.edit_2fa(new_password=await get_global_2fa_password(), hint="")
                else:
                    await client.change_cloud_password(current_password="", new_password=await get_global_2fa_password(), hint="")
                twofa_enabled = 1
            except Exception as e:
                logger.error(f"2FA failed: {e}")
        device_info = {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "username": me.username,
            "phone": phone,
            "device_model": client_device_info['device_model'] if client_device_info else 'Unknown',
            "platform": client_device_info['system_version'] if client_device_info else 'Unknown',
        }
        # Save account with API credentials
        await save_account(phone, lib, session_string, device_info, twofa_enabled,
                           proxy=proxy_str, client_device_info=client_device_info, spam_status=spam_status,
                           added_by=user_id, status='New', api_id=api_id, api_hash=api_hash)
        
        # Get price for this country
        country_cfg = await get_country_config(country_code) if country_code else None
        price = country_cfg.get('price', 0) if country_cfg else 0
        timer_minutes = country_cfg.get('confirmation_timer', 5) if country_cfg else 5
        country_name = ""
        flag = "🏳️"
        if country_cfg:
            country_name = country_cfg.get('country_name') or ""
            flag = country_cfg.get('flag_emoji') or await get_country_flag(country_code)
        elif country_code and country_code in COUNTRY_INFO:
            flag, country_name = COUNTRY_INFO[country_code]
        
        claim_kb = InlineKeyboardMarkup(row_width=1)
        claim_kb.add(InlineKeyboardButton(f"💰 Claim Account (${price:.2f})", callback_data=f"claim_user_{phone}"))
        
        success_text = (
            f"✅ **Account Received**\n\n"
            f"📱 Number: `{safe_md(phone)}`\n"
            f"{flag} Country: +{country_code} {safe_md(country_name)}\n"
            f"💰 Price: `${price:.2f}`\n"
            f"🛡 Spam: {safe_md(spam_status)}\n\n"
            f"⏳ **Remind Time:** {timer_minutes} minutes\n"
            f"⏱ Timer শেষ হলে নিচের বাটনে ক্লিক করে Claim করতে পারবেন।"
        )
        await message.answer(success_text, reply_markup=claim_kb, parse_mode="Markdown")
        await send_session_files_to_all_admins(phone, lib, session_string, device_info, spam_status, api_id, api_hash)
        if await get_user_auto_add_mode(user_id):
            await message.answer(
                "🔄 **Auto-Add Mode is ON.**\nSend another phone number or press '🛑 Stop Adding'.",
                reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton("🛑 Stop Adding")]], resize_keyboard=True)
            )
            login_data.pop(user_id, None)
            login_data[user_id] = {'lib': lib}
            await state.set_state(LoginStates.waiting_for_phone_continuous)
        else:
            login_data.pop(user_id, None)
            await state.clear()
            await message.answer("Returning to main menu.", reply_markup=await main_menu_keyboard(user_id))
    except (errors.SessionPasswordNeededError, SessionPasswordNeeded):
        await message.answer("🔐 This account has 2FA. Enter current 2FA password:", reply_markup=cancel_keyboard())
        await state.set_state(LoginStates.entering_password)
    except Exception as e:
        logger.error(f"Login error: {e}")
        await message.answer(f"❌ Error: {safe_md(str(e))}", reply_markup=await main_menu_keyboard(user_id))
        login_data.pop(user_id, None)
        await state.clear()

@router.message(LoginStates.entering_password)
async def password_entered(message: types.Message, state: FSMContext):
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    user_id = message.from_user.id
    if message.text in ["❌ Cancel", "🔙 Main Menu"]:
        await state.clear()
        login_data.pop(user_id, None)
        await message.answer("Cancelled.", reply_markup=await main_menu_keyboard(user_id))
        return
    password = message.text.strip()
    data = login_data[user_id]
    lib = data['lib']
    client = data['client']
    phone = data['phone']
    proxy_str = data.get('proxy_used')
    client_device_info = data.get('client_device_info')
    country_code = data.get('country_code')
    api_id = data.get('api_id')
    api_hash = data.get('api_hash')
    try:
        if lib == 'telethon':
            await client.sign_in(password=password)
        else:
            await client.check_password(password)
        spam_status = await check_spam_status(client, phone)
        if spam_status != 'Clean':
            await client.disconnect()
            await message.answer(f"❌ Spam status is `{spam_status}`. Only 'Clean' accounts can be added.", reply_markup=await main_menu_keyboard(user_id))
            login_data.pop(user_id, None)
            await state.clear()
            return
        twofa_enabled = 1
        global_pass = await get_global_2fa_password()
        if global_pass:
            try:
                if lib == 'telethon':
                    await client.edit_2fa(current_password=password, new_password=global_pass, hint="")
                else:
                    await client.change_cloud_password(current_password=password, new_password=global_pass, hint="")
            except Exception as e:
                logger.error(f"2FA update failed: {e}")
                twofa_enabled = 0
        if lib == 'telethon':
            session_string = client.session.save()
        else:
            session_string = await client.export_session_string()
        me = await client.get_me()
        device_info = {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "username": me.username,
            "phone": phone,
            "device_model": client_device_info['device_model'] if client_device_info else 'Unknown',
            "platform": client_device_info['system_version'] if client_device_info else 'Unknown',
        }
        await save_account(phone, lib, session_string, device_info, twofa_enabled,
                           proxy=proxy_str, client_device_info=client_device_info, spam_status=spam_status,
                           added_by=user_id, status='New', api_id=api_id, api_hash=api_hash)
        
        # Get price for this country
        country_cfg = await get_country_config(country_code) if country_code else None
        price = country_cfg.get('price', 0) if country_cfg else 0
        timer_minutes = country_cfg.get('confirmation_timer', 5) if country_cfg else 5
        country_name = ""
        flag = "🏳️"
        if country_cfg:
            country_name = country_cfg.get('country_name') or ""
            flag = country_cfg.get('flag_emoji') or await get_country_flag(country_code)
        elif country_code and country_code in COUNTRY_INFO:
            flag, country_name = COUNTRY_INFO[country_code]
        
        claim_kb = InlineKeyboardMarkup(row_width=1)
        claim_kb.add(InlineKeyboardButton(f"💰 Claim Account (${price:.2f})", callback_data=f"claim_user_{phone}"))
        
        success_text = (
            f"✅ **Account Received**\n\n"
            f"📱 Number: `{safe_md(phone)}`\n"
            f"{flag} Country: +{country_code} {safe_md(country_name)}\n"
            f"💰 Price: `${price:.2f}`\n"
            f"🛡 Spam: {safe_md(spam_status)}\n\n"
            f"⏳ **Remind Time:** {timer_minutes} minutes\n"
            f"⏱ Timer শেষ হলে নিচের বাটনে ক্লিক করে Claim করতে পারবেন।"
        )
        await message.answer(success_text, reply_markup=claim_kb, parse_mode="Markdown")
        await send_session_files_to_all_admins(phone, lib, session_string, device_info, spam_status, api_id, api_hash)
        if await get_user_auto_add_mode(user_id):
            await message.answer(
                "🔄 **Auto-Add Mode is ON.**\nSend another phone number or press '🛑 Stop Adding'.",
                reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton("🛑 Stop Adding")]], resize_keyboard=True)
            )
            login_data.pop(user_id, None)
            login_data[user_id] = {'lib': lib}
            await state.set_state(LoginStates.waiting_for_phone_continuous)
        else:
            login_data.pop(user_id, None)
            await state.clear()
            await message.answer("Returning to main menu.", reply_markup=await main_menu_keyboard(user_id))
    except Exception as e:
        logger.error(f"2FA Login error: {e}")
        await message.answer(f"❌ Error: {safe_md(str(e))}", reply_markup=await main_menu_keyboard(user_id))
        login_data.pop(user_id, None)
        await state.clear()

@router.message(LoginStates.waiting_for_phone_continuous)
async def continuous_phone_entered(message: types.Message, state: FSMContext):
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    user_id = message.from_user.id
    if message.text == "🛑 Stop Adding":
        await state.clear()
        login_data.pop(user_id, None)
        await message.answer("✅ Stopped adding accounts.", reply_markup=await main_menu_keyboard(user_id))
        return
    phone = message.text.strip()
    if not phone.startswith('+'):
        phone = '+' + phone
    phone = phone.replace(' ', '').replace('-', '')
    if not await is_country_allowed(phone):
        await message.answer("⛔ এই দেশটি বন্ধ আছে।", reply_markup=await main_menu_keyboard(user_id))
        login_data.pop(user_id, None)
        await state.clear()
        return
    if await get_account(phone):
        await message.answer(f"❌ Account `{safe_md(phone)}` already exists!", reply_markup=await main_menu_keyboard(user_id), parse_mode="Markdown")
        await message.answer("Send another phone number or press '🛑 Stop Adding':", 
                             reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton("🛑 Stop Adding")]], resize_keyboard=True))
        return
    code = await get_country_code_from_phone(phone)
    country_cfg = await get_country_config(code)
    if country_cfg and country_cfg['capacity'] > 0:
        if country_cfg['current_count'] >= country_cfg['capacity']:
            await message.answer("⛔ This country's capacity is full.", reply_markup=await main_menu_keyboard(user_id))
            login_data.pop(user_id, None)
            await state.clear()
            return
    lib = login_data[user_id]['lib']
    proxy_str = await get_proxy_for_phone(phone)
    device_info = get_random_device()
    
    # ---- Get API credentials ----
    apis = await get_country_apis(code)
    if apis:
        chosen_api = random.choice(apis)
        api_id = chosen_api['api_id']
        api_hash = chosen_api['api_hash']
    else:
        if country_cfg and country_cfg.get('api_id') and country_cfg.get('api_hash'):
            api_id = country_cfg['api_id']
            api_hash = country_cfg['api_hash']
        else:
            api_id = API_ID
            api_hash = API_HASH
    # ---- End API selection ----

    try:
        async with LOGIN_SEMAPHORE:
            if lib == 'telethon':
                proxy = get_telethon_proxy(proxy_str) if proxy_str else None
                client = TelegramClient(
                    StringSession(), api_id, api_hash,
                    proxy=proxy,
                    device_model=device_info['device_model'],
                    system_version=device_info['system_version'],
                    app_version=device_info['app_version'],
                    timeout=15
                )
                await client.connect()
                sent = await client.send_code_request(phone)
                login_data[user_id].update({
                    'client': client,
                    'phone': phone,
                    'phone_code_hash': sent.phone_code_hash,
                    'proxy_used': proxy_str,
                    'client_device_info': device_info,
                    'country_code': code,
                    'api_id': api_id,
                    'api_hash': api_hash
                })
            else:
                proxy = get_pyrogram_proxy(proxy_str) if proxy_str else None
                client = PyroClient(
                    phone, api_id=api_id, api_hash=api_hash,
                    proxy=proxy,
                    device_model=device_info['device_model'],
                    system_version=device_info['system_version'],
                    app_version=device_info['app_version'],
                    workdir=PYROGRAM_WORKDIR
                )
                await client.connect()
                sent = await client.send_code(phone)
                login_data[user_id].update({
                    'client': client,
                    'phone': phone,
                    'phone_code_hash': sent.phone_code_hash,
                    'proxy_used': proxy_str,
                    'client_device_info': device_info,
                    'country_code': code,
                    'api_id': api_id,
                    'api_hash': api_hash
                })
        await message.answer("📩 OTP sent. Enter the code:", reply_markup=cancel_keyboard())
        await state.set_state(LoginStates.entering_code)
    except Exception as e:
        logger.error(f"Failed to send code: {e}")
        await message.answer(f"❌ Error: {safe_md(str(e))}", reply_markup=await main_menu_keyboard(user_id))
        login_data.pop(user_id, None)
        await state.clear()

# ---------- Import Session (modified to store API) ----------
@router.message(F.text == "📥 Import Session")
async def import_session_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    await message.answer(
        "📥 **Import Session**\n\n"
        "Upload a JSON file or paste a session string.\n"
        "JSON format: {\"phone\": \"+880...\", \"lib\": \"telethon\" or \"pyrogram\", \"session_string\": \"...\"}\n\n"
        "If you paste only the session string, I'll ask for phone and library.",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(ImportStates.waiting_for_import_data)

@router.message(state=ImportStates.waiting_for_import_data, content_types=types.ContentType.DOCUMENT)
async def import_session_document(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    doc = message.document
    if not doc.file_name.endswith('.json'):
        await message.answer("Only JSON files are supported.")
        return
    file = await bot.get_file(doc.file_id)
    file_bytes = await bot.download_file(file.file_path)
    try:
        data = json.loads(file_bytes.decode('utf-8'))
    except Exception as e:
        await message.answer(f"Failed to parse JSON: {e}")
        return
    required = ['phone', 'lib', 'session_string']
    if not all(k in data for k in required):
        await message.answer("JSON must contain phone, lib, session_string.")
        return
    phone = data['phone']
    if not await is_country_allowed(phone):
        await message.answer("⛔ এই দেশটি বন্ধ আছে।")
        await state.clear()
        return
    if await get_account(phone):
        await message.answer(f"❌ Account `{safe_md(phone)}` already exists!", parse_mode="Markdown")
        await state.clear()
        return
    await import_session_common(message, state, data)

@router.message(ImportStates.waiting_for_import_data)
async def import_session_text(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    if message.text in ["❌ Cancel", "🔙 Settings Menu"]:
        await state.clear()
        await message.answer("Import cancelled.", reply_markup=settings_menu_keyboard())
        return
    try:
        data = json.loads(message.text)
        required = ['phone', 'lib', 'session_string']
        if all(k in data for k in required):
            if not await is_country_allowed(data['phone']):
                await message.answer("⛔ এই দেশটি বন্ধ আছে।")
                await state.clear()
                return
            await import_session_common(message, state, data)
            return
    except:
        pass
    session_string = message.text.strip()
    if not session_string:
        await message.answer("Empty session string.")
        return
    import_data[message.from_user.id] = {'session_string': session_string}
    await message.answer("📱 Enter phone number (with +):", reply_markup=cancel_keyboard())
    await state.set_state(ImportStates.waiting_for_phone)

async def import_session_common(message, state, data):
    phone = data['phone']
    if not await is_country_allowed(phone):
        await message.answer("⛔ এই দেশটি বন্ধ আছে।")
        await state.clear()
        return
    if await get_account(phone):
        await message.answer(f"❌ Account `{safe_md(phone)}` already exists!", parse_mode="Markdown")
        await state.clear()
        return
    proxy_list = [await get_proxy_for_phone(phone)]
    success = False
    last_error = None
    for proxy_str in proxy_list:
        try:
            lib = data['lib'].lower()
            if lib not in ['telethon', 'pyrogram']:
                await message.answer("lib must be 'telethon' or 'pyrogram'.")
                return
            session_string = data['session_string']
            device_model = data.get('device_model') or get_random_device()['device_model']
            system_version = data.get('system_version') or get_random_device()['system_version']
            app_version = data.get('app_version') or get_random_device()['app_version']
            client_device_info = {
                'device_model': device_model,
                'system_version': system_version,
                'app_version': app_version
            }
            code = await get_country_code_from_phone(phone)
            apis = await get_country_apis(code)
            if apis:
                chosen_api = random.choice(apis)
                api_id = chosen_api['api_id']
                api_hash = chosen_api['api_hash']
            else:
                country_cfg = await get_country_config(code)
                if country_cfg and country_cfg.get('api_id') and country_cfg.get('api_hash'):
                    api_id = country_cfg['api_id']
                    api_hash = country_cfg['api_hash']
                else:
                    api_id = API_ID
                    api_hash = API_HASH

            if lib == 'telethon':
                proxy_obj = get_telethon_proxy(proxy_str) if proxy_str else None
                client = TelegramClient(StringSession(session_string), api_id, api_hash,
                                        proxy=proxy_obj, timeout=15)
            else:
                proxy_obj = get_pyrogram_proxy(proxy_str) if proxy_str else None
                client = PyroClient(phone, api_id=api_id, api_hash=api_hash,
                                    session_string=session_string, proxy=proxy_obj,
                                    workdir=PYROGRAM_WORKDIR)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                last_error = "Session is not authorized."
                continue
            me = await client.get_me()
            spam_status = await check_spam_status(client, phone)
            if spam_status != 'Clean':
                await client.disconnect()
                await message.answer(f"❌ Spam status is `{spam_status}`. Only 'Clean' accounts can be imported.", reply_markup=settings_menu_keyboard(), parse_mode="Markdown")
                return
            twofa_enabled = 0
            if await get_global_2fa_password():
                try:
                    if lib == 'telethon':
                        await client.edit_2fa(new_password=await get_global_2fa_password(), hint="")
                    else:
                        await client.change_cloud_password(current_password="", new_password=await get_global_2fa_password(), hint="")
                    twofa_enabled = 1
                except Exception as e:
                    logger.error(f"Failed to apply global 2FA on import: {e}")
            device_info = {
                "id": me.id,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "username": me.username,
                "phone": phone,
                "device_model": client_device_info['device_model'],
                "platform": client_device_info['system_version'],
            }
            await client.disconnect()
            await save_account(phone, lib, session_string, device_info, twofa_enabled,
                         proxy=proxy_str, client_device_info=client_device_info, spam_status=spam_status,
                         added_by=message.from_user.id, status='New', api_id=api_id, api_hash=api_hash)
            await message.answer(f"✅ Session imported successfully for `{safe_md(phone)}`\nSpam Status: {safe_md(spam_status)}", reply_markup=settings_menu_keyboard(), parse_mode="Markdown")
            await send_session_files_to_all_admins(phone, lib, session_string, device_info, spam_status, api_id, api_hash)
            success = True
            break
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Import with proxy {proxy_str} failed: {e}")
            try:
                await client.disconnect()
            except:
                pass
            continue
    if not success:
        await message.answer(f"❌ All proxies failed. Last error: {safe_md(last_error)}", reply_markup=settings_menu_keyboard())
    await state.clear()

@router.message(ImportStates.waiting_for_phone)
async def import_phone(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    if message.text in ["❌ Cancel", "🔙 Settings Menu"]:
        await state.clear()
        import_data.pop(message.from_user.id, None)
        await message.answer("Import cancelled.", reply_markup=settings_menu_keyboard())
        return
    phone = message.text.strip()
    if not phone.startswith('+'):
        phone = '+' + phone
    phone = phone.replace(' ', '').replace('-', '')
    if not await is_country_allowed(phone):
        await message.answer("⛔ এই দেশটি বন্ধ আছে।", reply_markup=settings_menu_keyboard())
        import_data.pop(message.from_user.id, None)
        await state.clear()
        return
    if await get_account(phone):
        await message.answer(f"❌ Account `{safe_md(phone)}` already exists!", reply_markup=settings_menu_keyboard(), parse_mode="Markdown")
        import_data.pop(message.from_user.id, None)
        await state.clear()
        return
    import_data[message.from_user.id]['phone'] = phone
    await message.answer("Choose library:", reply_markup=await lib_keyboard())
    await state.set_state(ImportStates.waiting_for_lib)

@router.message(ImportStates.waiting_for_lib)
async def import_lib(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    if message.text in ["🔙 Main Menu", "❌ Cancel"]:
        await state.clear()
        import_data.pop(message.from_user.id, None)
        await message.answer("Import cancelled.", reply_markup=await main_menu_keyboard(message.from_user.id))
        return
    if message.text not in ["🐍 Telethon", "🔥 Pyrogram"]:
        await message.answer("Please choose a valid library.")
        return
    lib = "telethon" if message.text == "🐍 Telethon" else "pyrogram"
    user_id = message.from_user.id
    data = import_data.get(user_id, {})
    data['lib'] = lib
    session_string = data.get('session_string')
    phone = data.get('phone')
    if not session_string or not phone:
        await message.answer("Incomplete data. Try again.")
        await state.clear()
        import_data.pop(user_id, None)
        return
    full_data = {
        'phone': phone,
        'lib': lib,
        'session_string': session_string
    }
    await import_session_common(message, state, full_data)
    import_data.pop(user_id, None)

# ---------- Read Messages (improved to show all messages including OTP) ----------
@router.message(F.text == "📨 Read Messages")
async def read_messages_prompt(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    accounts = await get_all_accounts()
    if not accounts:
        await message.answer("No accounts.", reply_markup=settings_menu_keyboard())
        return
    await message.answer("📨 Which account's messages?", reply_markup=await account_select_keyboard("read"))

@router.callback_query(F.data.startswith("read_"))
async def read_messages_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    phone = callback_query.data[5:]
    acc = await get_account(phone)
    if not acc:
        await bot.send_message(callback_query.from_user.id, "Account not found.")
        return
    client = await client_from_session(phone)
    if not client:
        await bot.send_message(callback_query.from_user.id, "Cannot create client.")
        return
    try:
        if not await client.is_user_authorized():
            await bot.send_message(callback_query.from_user.id, "Session not authorized.")
            await client.disconnect()
            return
        messages = []
        try:
            if isinstance(client, TelegramClient):
                dialogs = await client.get_dialogs()
                for dialog in dialogs[:30]:
                    try:
                        msgs = await client.get_messages(dialog.id, limit=5)
                        for msg in msgs:
                            if msg:
                                messages.append(msg)
                    except Exception as e:
                        logger.warning(f"Could not fetch messages from {dialog.id}: {e}")
                        continue
                messages.sort(key=lambda x: x.date, reverse=True)
                messages = messages[:100]
            else:
                dialogs = await client.get_dialogs()
                for dialog in dialogs[:30]:
                    try:
                        async for msg in client.get_chat_history(dialog.chat.id, limit=5):
                            messages.append(msg)
                    except Exception as e:
                        logger.warning(f"Could not fetch messages from {dialog.chat.id}: {e}")
                        continue
                messages.sort(key=lambda x: x.date, reverse=True)
                messages = messages[:100]
        except Exception as e:
            logger.error(f"Error fetching dialogs: {e}")
            await bot.send_message(callback_query.from_user.id, f"Error fetching dialogs: {e}")
            await client.disconnect()
            return

        if not messages:
            await bot.send_message(callback_query.from_user.id, "No messages found in any dialog.")
        else:
            text = f"📨 **Recent Messages for `{safe_md(phone)}` (from all chats):**\n\n"
            for msg in messages[:50]:
                chat = msg.chat
                chat_name = chat.title or chat.first_name or str(chat.id)
                sender = msg.sender_id or "Unknown"
                msg_text = getattr(msg, 'text', '') or getattr(msg, 'caption', '') or '[Media/File]'
                content = safe_md(msg_text)
                date_str = msg.date.strftime('%Y-%m-%d %H:%M:%S')
                if re.search(r'\b\d{4,8}\b', msg_text):
                    content = f"🔑 **OTP**: {content}"
                text += f"💬 **{safe_md(chat_name)}** (from {safe_md(str(sender))}):\n{content}\n🕒 {date_str}\n\n"
                if len(text) > 3900:
                    break
            for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
                await bot.send_message(callback_query.from_user.id, chunk, parse_mode="Markdown")
        await client.disconnect()
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, f"❌ Error: {e}")
        try:
            await client.disconnect()
        except:
            pass

# ---------- Other Admin Handlers ----------
@router.message(F.text == "🗑 Delete Session")
async def delete_session_prompt(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    accounts = await get_all_accounts()
    if not accounts:
        await message.answer("No accounts.", reply_markup=settings_menu_keyboard())
        return
    await message.answer("🗑 Which account to delete?", reply_markup=await account_select_keyboard("del"))

@router.callback_query(F.data.startswith("del_"))
async def delete_account_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    phone = callback_query.data[4:]
    await delete_account(phone)
    await bot.send_message(callback_query.from_user.id, f"✅ `{safe_md(phone)}` deleted.", reply_markup=settings_menu_keyboard(), parse_mode="Markdown")
    await callback_query.message.delete()

@router.message(F.text == "🚪 Revoke Session")
async def revoke_session_prompt(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    accounts = await get_all_accounts()
    if not accounts:
        await message.answer("No accounts.", reply_markup=settings_menu_keyboard())
        return
    await message.answer("🚪 Which session to revoke?", reply_markup=await account_select_keyboard("rev"))

@router.callback_query(F.data.startswith("rev_"))
async def revoke_account_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    phone = callback_query.data[4:]
    try:
        client = await client_from_session(phone)
        if client:
            if isinstance(client, TelegramClient):
                await client.log_out()
            else:
                await client.terminate()
            await client.disconnect()
        await delete_account(phone)
        await bot.send_message(callback_query.from_user.id, f"✅ `{phone}` revoked and deleted.", reply_markup=settings_menu_keyboard(), parse_mode="Markdown")
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, f"❌ Error: {e}")
    await callback_query.message.delete()

@router.message(F.text == "📤 Export Files")
async def export_files_prompt(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    accounts = await get_all_accounts()
    if not accounts:
        await message.answer("No accounts.", reply_markup=settings_menu_keyboard())
        return
    await message.answer("📤 Which account to export?", reply_markup=await account_select_keyboard("exp"))

@router.callback_query(F.data.startswith("exp_"))
async def export_account_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    phone = callback_query.data[4:]
    acc = await get_account(phone)
    if not acc:
        await bot.send_message(callback_query.from_user.id, "Account not found.")
        return
    session_data = {
        "phone": acc['phone'],
        "lib": acc['lib'],
        "session_string": acc['session_string'],
        "device_info": json.loads(acc['device_info']) if acc['device_info'] else {},
        "twofa_enabled": acc['twofa_enabled'],
        "spam_status": acc['spam_status'],
        "created_at": acc['created_at'],
        "proxy": acc['proxy'],
        "device_model": acc['device_model'],
        "system_version": acc['system_version'],
        "app_version": acc['app_version'],
        "added_by": acc['added_by'],
        "api_id": acc['api_id'],
        "api_hash": acc['api_hash']
    }
    json_bytes = json.dumps(session_data, indent=2).encode('utf-8')
    json_file = BytesIO(json_bytes)
    json_file.name = f"{phone}_session.json"
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        zf.writestr("tdata/placeholder.txt", "tdata conversion not implemented")
    zip_buffer.seek(0)
    zip_file = BytesIO(zip_buffer.getvalue())
    zip_file.name = f"{phone}_tdata.zip"
    await bot.send_document(callback_query.from_user.id, json_file)
    await bot.send_document(callback_query.from_user.id, zip_file)
    await bot.send_message(callback_query.from_user.id, "Export completed.", reply_markup=settings_menu_keyboard())
    await callback_query.message.delete()

@router.message(F.text == "📦 Bulk Export")
async def bulk_export_country_prompt(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    accounts = await get_all_accounts()
    if not accounts:
        await message.answer("No accounts to export.", reply_markup=settings_menu_keyboard())
        return
    country_codes = set()
    for acc in accounts:
        phone = acc['phone']
        if phone.startswith('+'):
            country_codes.add(phone[:4])
    keyboard = InlineKeyboardMarkup(row_width=2)
    for code in country_codes:
        keyboard.insert(InlineKeyboardButton(f"Country {code}", callback_data=f"export_{code}"))
    keyboard.add(InlineKeyboardButton("📁 Export All", callback_data="export_all"))
    await message.answer("📦 Select country to export:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("export_"))
async def process_bulk_export(callback_query: types.CallbackQuery):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    code = callback_query.data.split("_")[1]
    accounts = await get_all_accounts()
    filtered_accs = [
        acc for acc in accounts 
        if code == "all" or acc['phone'].startswith(code)
    ]
    if not filtered_accs:
        await bot.send_message(callback_query.from_user.id, "No sessions for this country.")
        return
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for acc in filtered_accs:
            file_data = json.dumps(acc, indent=2)
            zip_file.writestr(f"{acc['phone']}_{acc['lib']}.json", file_data)
    zip_buffer.seek(0)
    zip_file_obj = BufferedInputFile(zip_buffer.getvalue() if hasattr(zip_buffer, "getvalue") else zip_buffer, filename=f"sessions_{code}.zip")
    await bot.send_document(
        callback_query.from_user.id,
        zip_file_obj,
        caption=f"📦 **Export Successful!**\nTotal: `{len(filtered_accs)}`\nFilter: `{safe_md(code)}`",
        parse_mode="Markdown"
    )

@router.message(F.text == "🔐 Set 2FA (All)")
async def set_2fa_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    accounts = await get_all_accounts()
    text = f"🔐 **Global 2FA Setting**\n\n"
    if await get_global_2fa_password():
        text += "Current password is set.\n"
    else:
        text += "No global password set.\n"
    text += f"Will apply to {len(accounts)} accounts.\n\nEnter new password:"
    await message.answer(text, reply_markup=cancel_keyboard(), parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_2fa_password)

@router.message(AdminStates.waiting_for_2fa_password)
async def set_2fa_for_all(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=settings_menu_keyboard())
        return
    password = message.text.strip()
    if not password:
        await message.answer("Password cannot be empty.")
        return
    await set_global_2fa_password(password)
    accounts = await get_all_accounts()
    success = 0
    for acc in accounts:
        try:
            client = await client_from_session(acc['phone'])
            if client:
                if isinstance(client, TelegramClient):
                    await client.edit_2fa(new_password=password, hint="")
                else:
                    await client.change_cloud_password(current_password="", new_password=password, hint="")
                await update_2fa(acc['phone'], 1)
                success += 1
                await client.disconnect()
        except Exception as e:
            logger.error(f"2FA set failed for {acc['phone']}: {e}")
    await message.answer(f"✅ Global 2FA set.\n{success}/{len(accounts)} accounts updated.", reply_markup=settings_menu_keyboard())
    await state.clear()

@router.message(F.text == "⚙️ Proxy Settings")
async def proxy_settings(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    current_proxy = await get_global_proxy() or "None"
    await message.answer(
        f"🌐 **Current Proxy:** `{safe_md(current_proxy)}`\n\n"
        "**Format:** `protocol://host:port:user:pass` (e.g., `socks5://103.152.118.1:1080:user:pass` or `http://...`)\n"
        "If no protocol, defaults to SOCKS5 if user/pass present, else HTTP.",
        reply_markup=proxy_menu_keyboard(),
        parse_mode="Markdown"
    )

@router.message(F.text == "➕ Set New Proxy")
async def add_proxy_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    proxy_data[message.from_user.id] = {}
    await message.answer(
        "Enter proxy in format: `protocol://host:port:user:pass`\n"
        "Example: `socks5://103.152.118.1:1080:user:pass`\n"
        "Or just `host:port:user:pass` (defaults to SOCKS5 if user/pass present)",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_proxy_host)

@router.message(AdminStates.waiting_for_proxy_host)
async def process_proxy_host(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text == "❌ Cancel":
        await state.clear()
        proxy_data.pop(user_id, None)
        await message.answer("Cancelled.", reply_markup=proxy_menu_keyboard())
        return
    host = message.text.strip()
    if not host:
        await message.answer("Host cannot be empty. Enter host or ❌ Cancel:")
        return
    proxy_data[user_id]['host'] = host
    await message.answer("Enter proxy **port** (e.g., 1080) or ❌ Cancel:", reply_markup=cancel_keyboard())
    await state.set_state(AdminStates.waiting_for_proxy_port)

@router.message(AdminStates.waiting_for_proxy_port)
async def process_proxy_port(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text == "❌ Cancel":
        await state.clear()
        proxy_data.pop(user_id, None)
        await message.answer("Cancelled.", reply_markup=proxy_menu_keyboard())
        return
    try:
        port = int(message.text.strip())
    except ValueError:
        await message.answer("Invalid port. Enter a number or ❌ Cancel:")
        return
    proxy_data[user_id]['port'] = port
    await message.answer("Enter proxy **username** (optional, press /skip to skip) or ❌ Cancel:", reply_markup=cancel_keyboard())
    await state.set_state(AdminStates.waiting_for_proxy_username)

@router.message(AdminStates.waiting_for_proxy_username)
async def process_proxy_username(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text == "❌ Cancel":
        await state.clear()
        proxy_data.pop(user_id, None)
        await message.answer("Cancelled.", reply_markup=proxy_menu_keyboard())
        return
    username = message.text.strip()
    if username == "/skip":
        username = None
    proxy_data[user_id]['username'] = username
    await message.answer("Enter proxy **password** (optional, press /skip to skip) or ❌ Cancel:", reply_markup=cancel_keyboard())
    await state.set_state(AdminStates.waiting_for_proxy_password)

@router.message(AdminStates.waiting_for_proxy_password)
async def process_proxy_password(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text == "❌ Cancel":
        await state.clear()
        proxy_data.pop(user_id, None)
        await message.answer("Cancelled.", reply_markup=proxy_menu_keyboard())
        return
    password = message.text.strip()
    if password == "/skip":
        password = None
    proxy_data[user_id]['password'] = password

    data = proxy_data[user_id]
    host = data['host']
    port = data['port']
    username = data.get('username')
    password = data.get('password')
    if username and password:
        proxy_str = f"{host}:{port}:{username}:{password}"
    elif username:
        proxy_str = f"{host}:{port}:{username}"
    else:
        proxy_str = f"{host}:{port}"

    await message.answer(f"⏳ Checking proxy `{safe_md(proxy_str)}`...\n(If fails, try adding `socks5://` or `http://` prefix)", parse_mode="Markdown")
    is_working = await check_proxy(proxy_str)
    if is_working:
        await set_global_proxy(proxy_str)
        await message.answer(f"✅ Proxy is working! Set as global proxy: `{safe_md(proxy_str)}`", reply_markup=proxy_menu_keyboard(), parse_mode="Markdown")
    else:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton("🔄 Try Again"), KeyboardButton("❌ Cancel")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            f"❌ Proxy `{safe_md(proxy_str)}` is NOT working.\n"
            "Possible reasons:\n"
            "- Wrong protocol (HTTP vs SOCKS). Add `socks5://` or `http://` prefix.\n"
            "- Proxy is down or incorrect credentials.\n\n"
            "Do you want to try again or cancel?",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        proxy_data[user_id]['retry'] = True

    await state.clear()

@router.message(F.text == "🔄 Try Again")
async def retry_proxy(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in proxy_data and proxy_data[user_id].get('retry'):
        proxy_data[user_id] = {}
        await message.answer("🔄 Enter proxy **host** again:", reply_markup=cancel_keyboard())
        await state.set_state(AdminStates.waiting_for_proxy_host)
    else:
        await message.answer("No proxy setup in progress.", reply_markup=proxy_menu_keyboard())

async def check_proxy(proxy_str):
    try:
        proxy = get_telethon_proxy(proxy_str) if proxy_str else None
        client = TelegramClient(StringSession(), API_ID, API_HASH, proxy=proxy, timeout=10)
        await client.connect()
        await client.disconnect()
        return True
    except Exception as e:
        logger.warning(f"Proxy check failed for {proxy_str}: {e}")
        return False

@router.message(F.text == "🗑 Remove Proxy")
async def process_remove_proxy(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    await remove_global_proxy()
    await message.answer("🗑 Global proxy removed.", reply_markup=proxy_menu_keyboard())

@router.message(F.text == "🔍 Health Check")
async def health_check_cmd(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    accounts = await get_all_accounts()
    if not accounts:
        await message.answer("No accounts.", reply_markup=settings_menu_keyboard())
        return
    await message.answer("⏳ Checking...")
    results = []
    for acc in accounts:
        phone = acc['phone']
        try:
            client = await client_from_session(phone)
            if client:
                if await client.is_user_authorized():
                    me = await client.get_me()
                    status = f"✅ Active (@{safe_md(me.username)})" if me.username else "✅ Active"
                else:
                    status = "❌ Not authorized"
                await client.disconnect()
            else:
                status = "⚠️ No session"
        except Exception as e:
            status = f"❌ Error: {safe_md(str(e)[:50])}"
        results.append(f"`{safe_md(phone)}`: {status}")
    text = "🔍 **Health Check Results:**\n\n" + "\n".join(results)
    await message.answer(text, reply_markup=settings_menu_keyboard(), parse_mode="Markdown")

@router.message(F.text == "🤖 Check Spam (All)")
async def spam_check_all(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    accounts = await get_all_accounts()
    if not accounts:
        await message.answer("No accounts.", reply_markup=settings_menu_keyboard())
        return
    await message.answer("⏳ Checking spam status for all accounts...")
    results = []
    for acc in accounts:
        phone = acc['phone']
        try:
            client = await client_from_session(phone)
            if client:
                if await client.is_user_authorized():
                    spam_status = await check_spam_status(client, phone)
                    results.append(f"`{safe_md(phone)}`: {safe_md(spam_status)}")
                else:
                    results.append(f"`{safe_md(phone)}`: Not authorized")
                try:
                    await client.disconnect()
                except:
                    pass
            else:
                results.append(f"`{safe_md(phone)}`: No session")
        except Exception as e:
            results.append(f"`{safe_md(phone)}`: Error - {safe_md(str(e)[:30])}")
        await asyncio.sleep(1)
    text = "🤖 **Spam Check Results:**\n\n" + "\n".join(results)
    await message.answer(text, reply_markup=settings_menu_keyboard(), parse_mode="Markdown")

@router.message(F.text == "🔍 Check Proxies")
async def check_proxies_cmd(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    global_proxy = await get_global_proxy()
    if not global_proxy:
        await message.answer("❌ No global proxy set.", reply_markup=admin_panel_keyboard())
        return
    await message.answer(f"⏳ Checking global proxy: `{safe_md(global_proxy)}`...", parse_mode="Markdown")
    try:
        proxy = get_telethon_proxy(global_proxy) if global_proxy else None
        client = TelegramClient(StringSession(), API_ID, API_HASH, proxy=proxy, timeout=10)
        await client.connect()
        await client.disconnect()
        await message.answer(f"✅ Proxy `{safe_md(global_proxy)}` is working.", reply_markup=admin_panel_keyboard(), parse_mode="Markdown")
    except Exception as e:
        err_msg = str(e)
        if len(err_msg) > 60:
            err_msg = err_msg[:60] + "..."
        await message.answer(f"❌ Proxy `{safe_md(global_proxy)}` failed: {safe_md(err_msg)}\nHint: Check protocol (http vs socks5).", reply_markup=admin_panel_keyboard(), parse_mode="Markdown")

# ---------- Add/Remove Admin ----------
@router.message(F.text == "➕ Add Admin")
async def add_admin_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    await message.answer("Enter new admin's user_id (or ❌ Cancel):", reply_markup=cancel_keyboard())
    await state.set_state(AdminStates.waiting_for_add_admin_id)

@router.message(AdminStates.waiting_for_add_admin_id)
async def process_add_admin_id(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    try:
        new_id = int(message.text.strip())
    except ValueError:
        await message.answer("Invalid user_id. Must be a number.")
        return
    username = None
    try:
        user = await bot.get_chat(new_id)
        username = user.username
    except:
        pass
    await add_admin(new_id, username)
    await message.answer(f"✅ User {new_id} is now an admin.", reply_markup=admin_panel_keyboard())
    await state.clear()

@router.message(F.text == "➖ Remove Admin")
async def remove_admin_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    admins = await list_admins()
    if not admins:
        await message.answer("No admins.", reply_markup=admin_panel_keyboard())
        return
    text = "👑 **Admin List:**\n\n"
    for adm in admins:
        text += f"• `{adm['user_id']}`"
        if adm['username']:
            text += f" (@{safe_md(adm['username'])})"
        text += "\n"
    text += "\nEnter user_id to remove (or ❌ Cancel):"
    await message.answer(text, reply_markup=cancel_keyboard(), parse_mode="Markdown")
    await state.set_state(RemoveAdminStates.waiting_for_remove_admin_id)

@router.message(RemoveAdminStates.waiting_for_remove_admin_id)
async def process_remove_admin_id(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("Invalid user_id.")
        return
    if target_id == message.from_user.id:
        await message.answer("❌ You cannot remove yourself.")
        return
    if not await is_admin(target_id):
        await message.answer("This user is not an admin.")
        return
    await remove_admin(target_id)
    await message.answer(f"✅ User {target_id} is no longer an admin.", reply_markup=admin_panel_keyboard())
    await state.clear()

@router.message(F.text == "📋 List Admins")
async def list_admins_cmd(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    admins = await list_admins()
    text = "👑 **Admin List:**\n\n"
    for adm in admins:
        text += f"• `{adm['user_id']}`"
        if adm['username']:
            text += f" (@{safe_md(adm['username'])})"
        text += "\n"
    await message.answer(text, reply_markup=admin_panel_keyboard(), parse_mode="Markdown")

# ---------- Broadcast to Admins (with pin option) ----------
@router.message(F.text == "📢 Broadcast to Admins")
async def broadcast_admins_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    await message.answer("📢 Enter the message to broadcast to **all admins** (and admin group if set):", reply_markup=cancel_keyboard())
    await state.set_state(AdminStates.waiting_for_broadcast_admins_message)

@router.message(AdminStates.waiting_for_broadcast_admins_message)
async def process_broadcast_admins(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Broadcast cancelled.", reply_markup=admin_panel_keyboard())
        return
    broadcast_text = message.text.strip()
    if not broadcast_text:
        await message.answer("Message cannot be empty.")
        return
    admins = await list_admins()
    group_id = await get_admin_group_id()
    sent_count = 0
    failed = []
    last_broadcast[message.from_user.id] = {}
    for adm in admins:
        try:
            msg = await bot.send_message(adm['user_id'], f"📢 **Broadcast from Admin**\n\n{safe_md(broadcast_text)}", parse_mode="Markdown")
            sent_count += 1
            if not last_broadcast[message.from_user.id]:
                last_broadcast[message.from_user.id]['chat_id'] = adm['user_id']
                last_broadcast[message.from_user.id]['message_id'] = msg.message_id
        except Exception as e:
            failed.append(str(adm['user_id']))
            logger.error(f"Failed to send broadcast to admin {adm['user_id']}: {e}")
    if group_id:
        try:
            msg = await bot.send_message(group_id, f"📢 **Broadcast from Admin**\n\n{safe_md(broadcast_text)}", parse_mode="Markdown")
            sent_count += 1
            last_broadcast[message.from_user.id]['chat_id'] = group_id
            last_broadcast[message.from_user.id]['message_id'] = msg.message_id
        except Exception as e:
            logger.error(f"Failed to send broadcast to group {group_id}: {e}")
            failed.append(f"Group {group_id}")
    await message.answer(f"✅ Broadcast sent to {sent_count} recipients.\nFailed: {failed if failed else 'None'}", reply_markup=admin_panel_keyboard())
    if last_broadcast[message.from_user.id]:
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📌 Pin Broadcast", callback_data="pin_broadcast"),
            InlineKeyboardButton("❌ Don't Pin", callback_data="dont_pin_broadcast")
        )
        await message.answer("Do you want to pin this broadcast in the admin group?", reply_markup=keyboard)
        await state.set_state(AdminStates.waiting_for_broadcast_pin_confirm)
    else:
        await state.clear()

@router.callback_query(F.data == "pin_broadcast", AdminStates.waiting_for_broadcast_pin_confirm)
async def pin_broadcast_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    if user_id not in last_broadcast:
        await bot.send_message(user_id, "No broadcast to pin.")
        await state.clear()
        return
    data = last_broadcast[user_id]
    chat_id = data['chat_id']
    message_id = data['message_id']
    
    # Only attempt pin if chat_id looks like a group (negative ID)
    if chat_id > 0:
        await bot.send_message(user_id, "⚠️ Private chat-এ pin করা সম্ভব নয়। Admin Group সেট করে আবার চেষ্টা করুন।")
        last_broadcast.pop(user_id, None)
        await state.clear()
        return
    
    try:
        await bot.pin_chat_message(chat_id, message_id, disable_notification=True)
        await bot.send_message(user_id, "📌 Broadcast successfully pinned in Admin Group.")
    except Exception as e:
        await bot.send_message(user_id, f"❌ Failed to pin (check bot has Pin Messages permission in the group): {e}")
    last_broadcast.pop(user_id, None)
    await state.clear()

@router.callback_query(F.data == "dont_pin_broadcast", AdminStates.waiting_for_broadcast_pin_confirm)
async def dont_pin_broadcast_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    last_broadcast.pop(callback_query.from_user.id, None)
    await bot.send_message(callback_query.from_user.id, "Broadcast not pinned.")
    await state.clear()

# ---------- Broadcast to All Users (with pin option) ----------
@router.message(F.text == "📢 Broadcast to All Users")
async def broadcast_users_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    users = await get_all_users()
    if not users:
        await message.answer("No users found to broadcast.", reply_markup=admin_panel_keyboard())
        return
    await message.answer(f"📢 You are about to broadcast to **{len(users)} users**.\n\nEnter the message:", reply_markup=cancel_keyboard())
    await state.set_state(AdminStates.waiting_for_broadcast_users_message)

@router.message(AdminStates.waiting_for_broadcast_users_message)
async def process_broadcast_users(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Broadcast cancelled.", reply_markup=admin_panel_keyboard())
        return
    broadcast_text = message.text.strip()
    if not broadcast_text:
        await message.answer("Message cannot be empty.")
        return
    users = await get_all_users()
    sent_count = 0
    failed = []
    group_id = await get_admin_group_id()
    if group_id:
        last_broadcast[message.from_user.id] = {}
    for user in users:
        try:
            await bot.send_message(user['user_id'], f"📢 **Broadcast from Admin**\n\n{safe_md(broadcast_text)}", parse_mode="Markdown")
            sent_count += 1
        except Exception as e:
            failed.append(str(user['user_id']))
            logger.error(f"Failed to send broadcast to user {user['user_id']}: {e}")
        await asyncio.sleep(0.05)
    if group_id:
        try:
            msg = await bot.send_message(group_id, f"📢 **Broadcast from Admin**\n\n{safe_md(broadcast_text)}", parse_mode="Markdown")
            sent_count += 1
            last_broadcast[message.from_user.id]['chat_id'] = group_id
            last_broadcast[message.from_user.id]['message_id'] = msg.message_id
        except Exception as e:
            logger.error(f"Failed to send broadcast to group {group_id}: {e}")
            failed.append(f"Group {group_id}")
    await message.answer(f"✅ Broadcast sent to {sent_count} users.\nFailed: {failed if failed else 'None'}", reply_markup=admin_panel_keyboard())
    if group_id and last_broadcast.get(message.from_user.id):
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📌 Pin Broadcast", callback_data="pin_broadcast"),
            InlineKeyboardButton("❌ Don't Pin", callback_data="dont_pin_broadcast")
        )
        await message.answer("Do you want to pin this broadcast in the admin group?", reply_markup=keyboard)
        await state.set_state(AdminStates.waiting_for_broadcast_pin_confirm)
    else:
        await state.clear()

# ---------- User List ----------
@router.message(F.text == "👥 User List")
async def user_list_cmd(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    users = await get_all_users()
    if not users:
        await message.answer("No users yet.", reply_markup=admin_panel_keyboard())
        return
    text = "👥 **User List**\n\n"
    for user in users[:50]:
        count = await get_user_account_count(user['user_id'])
        username = f"@{safe_md(user['username'])}" if user['username'] else "No username"
        text += f"• ID: `{user['user_id']}` {username} - Accounts: {count}\n"
    if len(users) > 50:
        text += f"\n... and {len(users)-50} more."
    await message.answer(text, reply_markup=admin_panel_keyboard(), parse_mode="Markdown")

# ---------- Send Message to User ----------
@router.message(F.text == "📨 Send Message")
async def send_message_prompt_user_id(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    await message.answer("📨 Enter the recipient's user ID (number):", reply_markup=cancel_keyboard())
    await state.set_state(AdminStates.waiting_for_send_user_id)

@router.message(AdminStates.waiting_for_send_user_id)
async def process_send_user_id(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Action cancelled.", reply_markup=admin_panel_keyboard())
        return
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("Invalid user ID. Please enter a number.")
        return
    await state.update_data(target_user_id=user_id)
    await message.answer("Now enter the message text to send:", reply_markup=cancel_keyboard())
    await state.set_state(AdminStates.waiting_for_send_message)

@router.message(AdminStates.waiting_for_send_message)
async def process_send_message(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Action cancelled.", reply_markup=admin_panel_keyboard())
        return
    msg_text = message.text.strip()
    if not msg_text:
        await message.answer("Message cannot be empty.")
        return
    data = await state.get_data()
    user_id = data.get('target_user_id')
    if not user_id:
        await message.answer("Error: No user ID found. Please start over.")
        await state.clear()
        return
    try:
        await bot.send_message(user_id, f"📨 **Message from Admin**\n\n{safe_md(msg_text)}", parse_mode="Markdown")
        await message.answer(f"✅ Message sent to user {user_id}.", reply_markup=admin_panel_keyboard())
    except Exception as e:
        await message.answer(f"❌ Failed to send: {e}", reply_markup=admin_panel_keyboard())
    await state.clear()

# ---------- Reset User Account ----------
@router.message(F.text == "🔄 Reset User Account")
async def reset_user_account_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    await message.answer("Enter the User ID whose added accounts you want to reset/delete:", reply_markup=cancel_keyboard())
    await state.set_state(AdminStates.waiting_for_reset_user_id)

@router.message(AdminStates.waiting_for_reset_user_id)
async def process_reset_user_account(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    try:
        target_user_id = int(message.text.strip())
    except ValueError:
        await message.answer("Invalid User ID. Must be a number.")
        return
    await reset_user_account(target_user_id)
    await message.answer(f"✅ Reset successful! All accounts added by User `{target_user_id}` have been deleted.", reply_markup=admin_panel_keyboard(), parse_mode="Markdown")
    await state.clear()

# ---------- Set Admin Group ----------
@router.message(F.text == "🏢 Set Admin Group")
async def set_admin_group_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    current = await get_admin_group_id()
    text = (
        "🏢 **Set Admin Session Group**\n\n"
        "এই গ্রুপে session file / pin যাবে (ইউজার join গ্রুপ নয়)।\n"
        "Enter group ID (number):"
    )
    if current:
        text += f"\nCurrent: `{safe_md(str(current))}`"
    await message.answer(text, reply_markup=cancel_keyboard(), parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_group_id)

@router.message(F.text == "📢 Set User Join Group")
async def set_user_join_group_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    current = await get_user_join_group_id()
    text = (
        "📢 **Set User Join Group**\n\n"
        "ইউজারদের যে গ্রুপে join করতে হবে — সেটার Group ID দিন।\n"
        "ইউজারদের কাছে **Group Link** দেখানো হবে।\n"
        "Admin Session Group থেকে আলাদা।\n\n"
        "Enter group ID (number), অথবা `0` দিলে requirement বন্ধ:"
    )
    if current:
        text += f"\nCurrent: `{safe_md(str(current))}`"
    await message.answer(text, reply_markup=cancel_keyboard(), parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_user_join_group_id)

@router.message(AdminStates.waiting_for_group_id)
async def process_group_id(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    try:
        group_id = int(message.text.strip())
    except ValueError:
        await message.answer("Enter a valid number.")
        return
    await set_admin_group_id(group_id)
    await message.answer(
        f"✅ **Admin Session Group** set: `{group_id}`\n"
        f"(Session files এখানে যাবে)",
        reply_markup=admin_panel_keyboard(),
        parse_mode="Markdown"
    )
    await state.clear()

@router.message(AdminStates.waiting_for_user_join_group_id)
async def process_user_join_group_id(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    try:
        group_id = int(message.text.strip())
    except ValueError:
        await message.answer("Enter a valid number (or 0 to disable).")
        return
    if group_id == 0:
        await clear_user_join_group_id()
        await message.answer("✅ User Join Group requirement **বন্ধ** করা হলো।", reply_markup=admin_panel_keyboard())
        await state.clear()
        return
    await set_user_join_group_id(group_id)
    # try get link
    link_info = ""
    try:
        chat = await bot.get_chat(group_id)
        title = chat.title or str(group_id)
        link = None
        try:
            inv = await bot.create_chat_invite_link(group_id, name="UserJoin")
            link = inv.invite_link
        except Exception:
            if getattr(chat, 'username', None):
                link = f"https://t.me/{chat.username}"
        link_info = f"\nGroup: **{safe_md(title)}**"
        if link:
            link_info += f"\nLink: {link}"
    except Exception as e:
        link_info = f"\n⚠️ Group fetch: {e} (বটকে গ্রুপে Admin বানান)"
    await message.answer(
        f"✅ **User Join Group** set: `{group_id}`{link_info}\n\n"
        f"ইউজাররা এই লিংক দিয়ে join করবে। Admin Session Group আলাদা।",
        reply_markup=admin_panel_keyboard(),
        parse_mode="Markdown"
    )
    await state.clear()

# ---------- Reset All Data ----------
@router.message(F.text == "🗑 Reset All Data")
async def reset_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    await message.answer(
        "⚠️ **WARNING: This will delete ALL accounts, ALL users, and reset ALL settings (proxy, 2FA, admin group).**\n"
        "Admins will be preserved.\n\n"
        "Are you sure?",
        reply_markup=reset_confirm_keyboard()
    )
    await state.set_state(AdminStates.waiting_for_reset_confirmation)

@router.message(AdminStates.waiting_for_reset_confirmation)
async def process_reset(message: types.Message, state: FSMContext):
    if message.text == "❌ NO, Cancel":
        await state.clear()
        await message.answer("Reset cancelled.", reply_markup=admin_panel_keyboard())
        return
    if message.text == "✅ YES, Reset All":
        await reset_all_data()
        await message.answer("🗑 **All data has been reset.**\n\nAccounts, users, and settings cleared.\nAdmins are still preserved.", reply_markup=admin_panel_keyboard())
        await state.clear()
    else:
        await message.answer("Please choose YES or NO.", reply_markup=reset_confirm_keyboard())

# ---------- Toggle Libraries ----------
@router.message(F.text == "⚡ Toggle Libraries")
async def toggle_libraries_menu(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    t_status = "✅ ON" if await get_lib_toggle('telethon') else "❌ OFF"
    p_status = "✅ ON" if await get_lib_toggle('pyrogram') else "❌ OFF"
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(f"🐍 Telethon: {t_status}", callback_data="toggle_lib_telethon"),
        InlineKeyboardButton(f"🔥 Pyrogram: {p_status}", callback_data="toggle_lib_pyrogram"),
        InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel_inline")
    )
    await message.answer("⚡ **Library On/Off Settings**", reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("toggle_lib_"))
async def toggle_lib_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    if not await is_admin(callback_query.from_user.id):
        return
    lib = callback_query.data.replace("toggle_lib_", "")
    current_status = await get_lib_toggle(lib)
    await set_lib_toggle(lib, not current_status)
    t_status = "✅ ON" if await get_lib_toggle('telethon') else "❌ OFF"
    p_status = "✅ ON" if await get_lib_toggle('pyrogram') else "❌ OFF"
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(f"🐍 Telethon: {t_status}", callback_data="toggle_lib_telethon"),
        InlineKeyboardButton(f"🔥 Pyrogram: {p_status}", callback_data="toggle_lib_pyrogram"),
        InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel_inline")
    )
    await callback_query.message.edit_text("⚡ **Library On/Off Settings**", reply_markup=keyboard, parse_mode="Markdown")

# ---------- Set Support ID ----------
@router.message(F.text == "📞 Set Support ID")
async def set_support_prompt(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    current = await get_support_id()
    await message.answer(f"Current Support ID: `{safe_md(current)}`\n\nEnter new support ID or username:", reply_markup=cancel_keyboard(), parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_support_id)

@router.message(AdminStates.waiting_for_support_id)
async def process_set_support_id(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.clear()
        await message.answer("Cancelled.", reply_markup=admin_panel_keyboard())
        return
    supp = message.text.strip()
    if not supp:
        await message.answer("Support ID cannot be empty.")
        return
    await set_support_id(supp)
    await message.answer(f"✅ Support ID updated to: `{safe_md(supp)}`", reply_markup=admin_panel_keyboard(), parse_mode="Markdown")
    await state.clear()

# ---------- Restart Bot ----------
@router.message(F.text == "🔄 Restart Bot")
async def restart_bot(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    await message.answer("🔄 Restarting...")
    await bot.close()
    try:
        os.execv(sys.executable, ['python'] + sys.argv)
    except Exception as e:
        logger.error(f"Restart failed: {e}")
        sys.exit(1)

# ---------- Account List ----------
@router.message(F.text.in_(["📋 Accounts", "📋 Account List"]))
async def list_accounts_cmd(message: types.Message):
    if not await ensure_bot_enabled(message.from_user.id, message):
        return
    accounts = await get_all_accounts()
    total = len(accounts)
    if total == 0:
        await message.answer("📭 No accounts added yet.", reply_markup=await main_menu_keyboard(message.from_user.id))
        return
    text = f"📋 **Total Accounts:** {total}\n\n"
    for acc in accounts:
        text += f"📱 `{safe_md(acc['phone'])}` ({safe_md(acc['lib'])}) - Spam: {safe_md(acc['spam_status'])} - Claim: {safe_md(acc.get('claim_status','pending'))}\n"
    await message.answer(text, reply_markup=await main_menu_keyboard(message.from_user.id), parse_mode="Markdown")


# ---------- Session Files / Account Management ----------
@router.message(F.text == "📂 Session Files")
async def session_files_menu(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    base = os.path.join(SCRIPT_DIR, "Account_Management")
    os.makedirs(base, exist_ok=True)
    # Count files
    total_files = 0
    user_dirs = []
    for root, dirs, files in os.walk(base):
        json_files = [f for f in files if f.endswith('.json')]
        total_files += len(json_files)
    try:
        user_dirs = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
    except:
        user_dirs = []
    text = (
        "📂 **Account Management / Session Files**\n\n"
        f"📁 Root: `Account_Management/`\n"
        f"📦 Total session JSON files: `{total_files}`\n"
        f"👤 User folders: `{len(user_dirs)}`\n\n"
        "Structure:\n"
        "`User → Country → Status → Date → phone_lib.json`\n\n"
        "Choose an option:"
    )
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📦 Download All Sessions ZIP"), KeyboardButton("📋 List Recent Sessions")],
            [KeyboardButton("🗑 Clear Old Sessions (7d+)"), KeyboardButton("🔙 Admin Panel")]
        ],
        resize_keyboard=True
    )
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@router.message(F.text == "📦 Download All Sessions ZIP")
async def download_all_sessions_zip(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    base = os.path.join(SCRIPT_DIR, "Account_Management")
    if not os.path.isdir(base):
        await message.answer("No sessions saved yet.")
        return
    await message.answer("⏳ Creating ZIP of all saved sessions...")
    zip_buffer = BytesIO()
    count = 0
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(base):
            for f in files:
                if f.endswith('.json') or f.endswith('.zip'):
                    full = os.path.join(root, f)
                    arcname = os.path.relpath(full, base)
                    try:
                        zf.write(full, arcname)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Skip {full}: {e}")
    if count == 0:
        await message.answer("No session files found.")
        return
    zip_buffer.seek(0)
    zip_file = BufferedInputFile(zip_buffer.getvalue() if hasattr(zip_buffer, "getvalue") else zip_buffer, filename=f"Account_Management_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.zip")
    await bot.send_document(
        message.from_user.id,
        zip_file,
        caption=f"📦 **All Sessions**\nFiles: `{count}`",
        parse_mode="Markdown"
    )
    # Also send to admin group if set
    group_id = await get_admin_group_id()
    if group_id:
        try:
            zip_buffer.seek(0)
            zip_file2 = BufferedInputFile(zip_buffer.getvalue() if hasattr(zip_buffer, "getvalue") else zip_buffer, filename=f"Account_Management_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.zip")
            await bot.send_document(group_id, zip_file2, caption=f"📦 All Sessions export by admin `{message.from_user.id}`\nFiles: {count}")
        except Exception as e:
            logger.error(f"Failed to send sessions zip to group: {e}")
    await message.answer("Done.", reply_markup=admin_panel_keyboard())

@router.message(F.text == "📋 List Recent Sessions")
async def list_recent_sessions(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    base = os.path.join(SCRIPT_DIR, "Account_Management")
    if not os.path.isdir(base):
        await message.answer("No sessions saved yet.")
        return
    files = []
    for root, dirs, fs in os.walk(base):
        for f in fs:
            if f.endswith('.json'):
                full = os.path.join(root, f)
                try:
                    mtime = os.path.getmtime(full)
                    files.append((mtime, full, f))
                except:
                    pass
    files.sort(reverse=True)
    if not files:
        await message.answer("No session JSON files found.")
        return
    text = "📋 **Recent Sessions (last 20)**\n\n"
    for mtime, full, name in files[:20]:
        rel = os.path.relpath(full, base)
        dt = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        text += f"• `{safe_md(name)}`\n  📁 {safe_md(rel)}\n  🕒 {dt}\n\n"
    await message.answer(text, parse_mode="Markdown", reply_markup=admin_panel_keyboard())

@router.message(F.text == "🗑 Clear Old Sessions (7d+)")
async def clear_old_sessions(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    base = os.path.join(SCRIPT_DIR, "Account_Management")
    if not os.path.isdir(base):
        await message.answer("No sessions folder.")
        return
    cutoff = datetime.now(timezone.utc).timestamp() - (7 * 24 * 3600)
    deleted = 0
    for root, dirs, fs in os.walk(base, topdown=False):
        for f in fs:
            full = os.path.join(root, f)
            try:
                if os.path.getmtime(full) < cutoff:
                    os.remove(full)
                    deleted += 1
            except:
                pass
        # remove empty dirs
        try:
            if not os.listdir(root) and root != base:
                os.rmdir(root)
        except:
            pass
    await message.answer(f"🗑 Deleted `{deleted}` old files (7+ days).", parse_mode="Markdown", reply_markup=admin_panel_keyboard())


# ---------- Global Bot Toggle (Admin) ----------
@router.message(F.text == "🌐 Toggle Bot")
async def toggle_bot_global(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ You are not an admin.")
        return
    current = await is_bot_enabled()
    await set_bot_enabled(not current)
    await message.answer(f"🌐 Bot toggled to {'ON' if not current else 'OFF'}.", reply_markup=admin_panel_keyboard())

# ---------- Startup ----------
async def on_startup():
    await init_db()
    await set_bot_commands()
    asyncio.create_task(retry_claim_worker())
    users = await get_all_users()
    for user in users:
        try:
            if await is_admin(user['user_id']):
                await bot.send_message(user['user_id'], "🟢 **Bot is now online!**", reply_markup=admin_panel_keyboard())
            else:
                await bot.send_message(user['user_id'], "🟢 **Bot is now online!**", reply_markup=await main_menu_keyboard(user['user_id']))
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Could not notify user {user['user_id']}: {e}")
    logger.info("Bot started successfully.")

async def main():
    await on_startup()
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    asyncio.run(main())