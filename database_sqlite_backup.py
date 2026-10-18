# Authorised by NyxLuciferX02

import sqlite3
import os
import psycopg2


# ==========================================
# DATABASE CONNECTION
# ==========================================


DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Render / PostgreSQL
    db = psycopg2.connect(DATABASE_URL)
    cursor = db.cursor()

    print("🐘 PostgreSQL database connected.")

else:
    # Local laptop / SQLite
    db = sqlite3.connect(
        "database.db",
        check_same_thread=False
    )
    cursor = db.cursor()

    print("💻 SQLite database connected.")

cursor = db.cursor()


# ==========================================
# MEMBERS
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS members(
    user_id INTEGER,
    chat_id INTEGER,
    full_name TEXT,
    PRIMARY KEY(user_id, chat_id)
)
""")


# ==========================================
# WELCOME SETTINGS
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS welcome_settings(
    chat_id INTEGER PRIMARY KEY,
    enabled INTEGER DEFAULT 1,
    text TEXT,
    file_id TEXT,
    media_type TEXT DEFAULT 'text'
)
""")


# ==========================================
# BOT USERS
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_users(
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT
)
""")


# ==========================================
# FIX OLD BOT_USERS DATABASE
# ==========================================

cursor.execute("""
PRAGMA table_info(bot_users)
""")

bot_user_columns = [
    row[1]
    for row in cursor.fetchall()
]

if "username" not in bot_user_columns:

    cursor.execute("""
    ALTER TABLE bot_users
    ADD COLUMN username TEXT
    """)


if "full_name" not in bot_user_columns:

    cursor.execute("""
    ALTER TABLE bot_users
    ADD COLUMN full_name TEXT
    """)


# ==========================================
# BOT CHATS
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_chats(
    chat_id INTEGER PRIMARY KEY,
    title TEXT,
    chat_type TEXT
)
""")


# ==========================================
# BOT GROUPS
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_groups(
    chat_id INTEGER PRIMARY KEY,
    title TEXT
)
""")


# ==========================================
# AI CHAT MEMORY
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS chat_memory(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")


# ==========================================
# USER PERSONALITY + MOOD
# ==========================================
#
# IMPORTANT:
# These settings belong to ONE user only.
#
# Example:
#
# User A → funny + happy
# User B → cold + angry
#
# They do NOT affect each other.
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_mood_memory(
    user_id INTEGER PRIMARY KEY,
    mood TEXT DEFAULT 'calm',
    personality TEXT DEFAULT 'normal',
    interests TEXT,
    preferences TEXT,
    notes TEXT
)
""")


# ==========================================
# BOT DEFAULT PERSONALITY
# ==========================================
#
# This is only the fallback/default setting.
# User-specific settings are stored above.
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_personality(
    id INTEGER PRIMARY KEY CHECK (id = 1),
    personality TEXT DEFAULT 'normal',
    mood TEXT DEFAULT 'calm'
)
""")


# ==========================================
# DEFAULT BOT PERSONALITY
# ==========================================

cursor.execute("""
INSERT OR IGNORE INTO bot_personality
(id, personality, mood)
VALUES
(1, 'normal', 'calm')
""")

# ==========================================
# DAILY GROUP AWARDS
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS daily_group_activity(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT,
    full_name TEXT,
    activity_date TEXT NOT NULL,
    message_count INTEGER DEFAULT 0,
    UNIQUE(chat_id, user_id, activity_date)
)
""")

# ==========================================
# MYSTERY MEMBER
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS mystery_member(
    chat_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    username TEXT,
    full_name TEXT,
    mystery_date TEXT NOT NULL
)
""")


# ==========================================
# SAVE DATABASE
# ==========================================

db.commit()


print("✅ Database connected successfully.")
print("✅ All tables checked.")
print("✅ Chat memory ready.")
print("✅ User personality/mood memory ready.")
print("✅ Group database ready.")