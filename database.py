# Authorised by NyxLuciferX02

import os
import sqlite3
import psycopg2


# ==========================================
# DATABASE CONNECTION
# ==========================================

DATABASE_URL = os.getenv("DATABASE_URL")

USE_POSTGRES = bool(DATABASE_URL)


if USE_POSTGRES:

    print("🐘 Connecting to PostgreSQL...")

    db = psycopg2.connect(DATABASE_URL)

    cursor = db.cursor()

    print("🐘 PostgreSQL database connected.")

else:

    print("💻 Connecting to local SQLite...")

    db = sqlite3.connect(
        "database.db",
        check_same_thread=False
    )

    cursor = db.cursor()

    print("💻 SQLite database connected.")


# ==========================================
# MEMBERS
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS members(
    user_id BIGINT,
    chat_id BIGINT,
    username TEXT,
    full_name TEXT,
    PRIMARY KEY(user_id, chat_id)
)
""")


# ==========================================
# WELCOME SETTINGS
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS welcome_settings(
    chat_id BIGINT PRIMARY KEY,
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
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    full_name TEXT
)
""")


# ==========================================
# BOT CHATS
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_chats(
    chat_id BIGINT PRIMARY KEY,
    title TEXT,
    chat_type TEXT
)
""")


# ==========================================
# BOT GROUPS
# ==========================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_groups(
    chat_id BIGINT PRIMARY KEY,
    title TEXT
)
""")


# ==========================================
# AI CHAT MEMORY
# ==========================================

if USE_POSTGRES:

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_memory(
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

else:

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

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_mood_memory(
    user_id BIGINT PRIMARY KEY,
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_personality(
    id INTEGER PRIMARY KEY,
    personality TEXT DEFAULT 'normal',
    mood TEXT DEFAULT 'calm',

    CONSTRAINT bot_personality_single_row
    CHECK (id = 1)
)
""")


# ==========================================
# DEFAULT BOT PERSONALITY
# ==========================================

if USE_POSTGRES:

    cursor.execute("""
    INSERT INTO bot_personality
    (id, personality, mood)
    VALUES
    (1, 'normal', 'calm')
    ON CONFLICT (id) DO NOTHING
    """)

else:

    cursor.execute("""
    INSERT OR IGNORE INTO bot_personality
    (id, personality, mood)
    VALUES
    (1, 'normal', 'calm')
    """)


# ==========================================
# DAILY GROUP ACTIVITY
# ==========================================

if USE_POSTGRES:

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_group_activity(
        id BIGSERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        username TEXT,
        full_name TEXT,
        activity_date TEXT NOT NULL,
        message_count INTEGER DEFAULT 0,

        UNIQUE(chat_id, user_id, activity_date)
    )
    """)

else:

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
    chat_id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    username TEXT,
    full_name TEXT,
    mystery_date DATE NOT NULL
)
""")


# ==========================================
# COMMIT
# ==========================================

db.commit()


# ==========================================
# STATUS
# ==========================================

if USE_POSTGRES:

    print("🐘 PostgreSQL database ready.")

else:

    print("💻 SQLite database ready.")


print("✅ All tables checked.")
print("✅ Chat memory ready.")
print("✅ User personality/mood memory ready.")
print("✅ Group database ready.")