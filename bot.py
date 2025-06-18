import os
import logging
import aiosqlite
import asyncio
import datetime
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from openrouter_llm import generate_motivations_bulk

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
DB_FILE = "users.db"

BUTTONS = [
    ("Не убедительно", +1),
    ("Заставляет задуматься", 0),
    ("Воу-воу по-легче", -1),
]

def get_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text, callback_data=str(delta)) for text, delta in BUTTONS]
    ])

HARDNESS_LABELS = {0: "easy", 1: "medium", 2: "hard"}

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            join_time TIMESTAMP,
            last_message_time TIMESTAMP,
            hardness INTEGER DEFAULT 1,
            days_on_streak INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1
        )''')
        await db.execute('''
        CREATE TABLE IF NOT EXISTS scheduled_messages (
            user_id INTEGER,
            day INTEGER,
            hardness INTEGER,
            message TEXT,
            sent INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, day)
        )''')
        await db.commit()

async def add_user(user):
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT OR IGNORE INTO users (user_id, username, join_time, last_message_time, hardness, days_on_streak)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user.id, user.username, now, now, 1, 0))
        await db.commit()

async def update_hardness(user_id, delta):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            UPDATE users SET hardness = MIN(MAX(hardness + ?, 0), 2) WHERE user_id = ?
        ''', (delta, user_id))
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def schedule_user_messages(user_id, hardness_map):
    # Schedule 365 messages (1 per day), randomly from supplied lists for each type
    days = 365
    schedule = []
    for day in range(days):
        # Randomly pick a hardness (start with current, user will adjust via feedback)
        # For initial assignment, just distribute equally
        hardness = day % 3
        msg = random.choice(hardness_map[HARDNESS_LABELS[hardness]])
        schedule.append((user_id, day, hardness, msg, 0))
    async with aiosqlite.connect(DB_FILE) as db:
        await db.executemany('''
            INSERT OR REPLACE INTO scheduled_messages (user_id, day, hardness, message, sent)
            VALUES (?, ?, ?, ?, ?)
        ''', schedule)
        await db.commit()

async def get_next_message(user_id):
    async with aiosqlite.connect(DB_FILE) as db:
        # Select next unsent message for this user
        async with db.execute('''
            SELECT day, hardness, message FROM scheduled_messages
            WHERE user_id = ? AND sent = 0
            ORDER BY day ASC LIMIT 1
        ''', (user_id,)) as cursor:
            return await cursor.fetchone()

async def mark_message_sent(user_id, day):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            UPDATE scheduled_messages SET sent = 1 WHERE user_id = ? AND day = ?
        ''', (user_id, day))
        await db.commit()

async def update_last_sent(user_id):
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            UPDATE users SET last_message_time = ?, days_on_streak = days_on_streak + 1 WHERE user_id = ?
        ''', (now, user_id))
        await db.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await add_user(user)
    await update.message.reply_text(
        "Привет! Я твой мотивационный коуч по отказу от курения. "
        "Буду присылать тебе 3 мотивационных сообщения в день, подбирая их по твоей реакции. "
        "Первое сообщение уже летит тебе!",
    )
    # Generate personalized batch and schedule messages if not present
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            'SELECT COUNT(*) FROM scheduled_messages WHERE user_id=?', (user.id,)
        ) as cursor:
            count = (await cursor.fetchone())[0]
    if count == 0:
        # Generate 3*users messages (as only 1 user now, generate 3)
        motivations = await asyncio.get_event_loop().run_in_executor(None, generate_motivations_bulk, 3)
        await schedule_user_messages(user.id, motivations)
    # Send first message
    await send_next_motivation(user.id, context.bot)

async def feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    delta = int(query.data)
    user_id = query.from_user.id
    await update_hardness(user_id, delta)
    await query.answer("Спасибо за обратную связь!")
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text("Твоя реакция учтена. Следующее сообщение будет через 8 часов.")

async def send_next_motivation(user_id, bot):
    row = await get_next_message(user_id)
    if not row:
        return
    day, hardness, message = row
    keyboard = get_keyboard()
    try:
        await bot.send_message(
            user_id,
            f"{message}",
            reply_markup=keyboard
        )
        await mark_message_sent(user_id, day)
        await update_last_sent(user_id)
    except Exception as e:
        logging.warning(f"Failed to send to {user_id}: {e}")

async def scheduled_sender(app):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT user_id, last_message_time, days_on_streak FROM users WHERE active = 1') as cursor:
            users = await cursor.fetchall()
    now = datetime.datetime.utcnow()
    for user_id, last_msg, streak in users:
        if streak >= 365:
            continue  # Finished program
        # Send if >=8h since last message
        try:
            last_dt = datetime.datetime.fromisoformat(last_msg)
        except Exception:
            last_dt = now - datetime.timedelta(hours=9)
        if (now - last_dt).total_seconds() >= 8 * 3600:
            await send_next_motivation(user_id, app.bot)

async def async_main():
    logging.basicConfig(level=logging.DEBUG)
    await init_db()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(feedback_callback))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(scheduled_sender, "interval", hours=1, args=[app])
    scheduler.start()

    # This manages the event loop itself; don't call asyncio.run()
    await app.run_polling()

if __name__ == "__main__":
    # In normal scripts, use:
    # asyncio.run(async_main())
    #
    # BUT for ptb >=20, just:
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # And call directly:
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(async_main())