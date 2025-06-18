import os
import logging
import aiosqlite
import asyncio
import datetime
import random
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, ChatMemberHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from openrouter_llm import generate_motivation

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
DB_FILE = "users.db"

CHECKIN_QUESTION = "Сделал ли ты сегодня шаги к своей цели? Ответь 'да' или 'нет'."
VICTORY_MESSAGE = "Поздравляю! Ты достиг своей цели! 🎉"

STATE_AWAIT_GOAL = 1

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("Сменить цель"), KeyboardButton("Удалить чат и все данные")]
    ],
    resize_keyboard=True
)

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            goal TEXT,
            hardness INTEGER DEFAULT 10,
            last_sent TIMESTAMP,
            last_checkin TIMESTAMP
        )''')
        await db.commit()

async def set_goal(user, goal):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO users (user_id, username, goal, hardness, last_sent, last_checkin)
            VALUES (?, ?, ?, 10, NULL, NULL)
            ON CONFLICT(user_id) DO UPDATE SET goal=excluded.goal, hardness=10
        ''', (user.id, user.username, goal))
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def update_hardness(user_id, delta):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            UPDATE users SET hardness = MIN(MAX(hardness + ?, 1), 21) WHERE user_id = ?
        ''', (delta, user_id))
        await db.commit()

async def update_last_sent(user_id):
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('UPDATE users SET last_sent = ? WHERE user_id = ?', (now, user_id))
        await db.commit()

async def update_last_checkin(user_id):
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('UPDATE users SET last_checkin = ? WHERE user_id = ?', (now, user_id))
        await db.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Напиши свою цель или привычку, которую хочешь внедрить или убрать. "
        "Я буду тебе помогать мотивацией!"
    )

async def handle_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip().lower()

    # Handle button "Сменить цель"
    if text == "сменить цель":
        await update.message.reply_text(
            "Опиши новую цель или привычку, которую ты хочешь изменить.",
            reply_markup=MAIN_KEYBOARD
        )
        context.user_data["awaiting_goal"] = True
        return

    # Handle button "Удалить чат и все данные"
    if text == "удалить чат и все данные":
        await delete_user(user.id)
        await update.message.reply_text(
            "Все твои данные удалены. Чтобы начать заново — напиши новую цель.",
            reply_markup=MAIN_KEYBOARD
        )
        context.user_data.clear()
        return

    # Set new goal if in goal-setting mode, or no goal yet
    if context.user_data.get("awaiting_goal") or not (await get_user(user.id))[2]:
        await set_goal(user, update.message.text.strip())
        await update.message.reply_text(
            "Твоя цель сохранена!\nТеперь я буду регулярно отправлять тебе мотивационные сообщения.",
            reply_markup=MAIN_KEYBOARD
        )
        context.user_data["awaiting_goal"] = False
        await send_next_motivation(user.id, context.bot)
    else:
        # Handle regular text (optionally)
        pass

async def send_next_motivation(user_id, bot):
    user = await get_user(user_id)
    if not user or not user[2]:  # goal is at index 2
        return
    goal = user[2]
    hardness = user[3]
    prompt = (
        f'''Замотивируй чтобы удовлетворить следующий запрос '{goal}'. Степень жесткости мотивации должна быть {hardness} из 21. Ответ предоставь в JSON в следующем формате {{"motivation":"..."}}'''
    )
    try:
        motivation = generate_motivation(prompt)
        await bot.send_message(user_id, motivation, reply_markup=MAIN_KEYBOARD)
        await update_last_sent(user_id)
    except Exception as e:
        logging.warning(f"Failed to send to {user_id}: {e}")

async def send_daily_checkin(user_id, bot):
    user = await get_user(user_id)
    if not user or not user[2]:
        return
    last_checkin = user[5]
    now = datetime.datetime.utcnow()
    if last_checkin:
        dt = datetime.datetime.fromisoformat(last_checkin)
        if (now - dt).total_seconds() < 23 * 3600:  # not yet 24h
            return
    await bot.send_message(user_id, CHECKIN_QUESTION, reply_markup=MAIN_KEYBOARD)
    await update_last_checkin(user_id)

async def check_and_send(bot):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT user_id, last_sent FROM users') as cursor:
            users = await cursor.fetchall()
    now = datetime.datetime.utcnow()
    for user_id, last_sent in users:
        # Schedule motivational message if 1–4 hours passed since last
        if not last_sent:
            should_send = True
        else:
            dt = datetime.datetime.fromisoformat(last_sent)
            hours_passed = (now - dt).total_seconds() / 3600
            should_send = hours_passed >= random.uniform(1, 4)
        if should_send:
            await send_next_motivation(user_id, bot)
        await send_daily_checkin(user_id, bot)

async def handle_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    answer = update.message.text.lower().strip()
    user_row = await get_user(user.id)
    if not user_row or not user_row[2]:
        return
    hardness = user_row[3]
    if answer == "да":
        await update_hardness(user.id, -1)
        if hardness <= 1:
            await update.message.reply_text(VICTORY_MESSAGE, reply_markup=MAIN_KEYBOARD)
        else:
            await update.message.reply_text(f"Молодец! Продолжаем!", reply_markup=MAIN_KEYBOARD)
    elif answer == "нет":
        await update_hardness(user.id, +1)
        await update.message.reply_text(f"Не сдавайся! Я с тобой.", reply_markup=MAIN_KEYBOARD)
    await update_last_checkin(user.id)

async def delete_user(user_id):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('DELETE FROM users WHERE user_id=?', (user_id,))
        await db.commit()

async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member and update.my_chat_member.chat.type == "private":
        new_status = update.my_chat_member.new_chat_member.status
        user_id = update.my_chat_member.chat.id
        if new_status in ["kicked", "left"]:
            await delete_user(user_id)
            logging.info(f"User {user_id} removed the bot, deleted from DB.")

async def async_main():
    logging.basicConfig(level=logging.DEBUG)
    await init_db()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_goal))
    app.add_handler(MessageHandler(filters.Regex("^(да|нет)$"), handle_checkin))
    app.add_handler(ChatMemberHandler(chat_member_update, chat_member_types="my_chat_member"))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_and_send, "interval", minutes=30, args=[app.bot])
    scheduler.start()
    await app.run_polling()

if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(async_main())
