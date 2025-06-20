import os
import logging
import aiosqlite
import asyncio
import datetime
import random
from aiogram import Bot, Dispatcher, types, Router
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, Message
from aiogram.filters import Command, CommandStart, BaseFilter
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from openrouter_llm import generate_motivation

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
DB_FILE = "users.db"

CHECKIN_QUESTION = "Сделал ли ты сегодня шаги к своей цели? Ответь 'да' или 'нет'."
VICTORY_MESSAGE = "Поздравляю! Ты достиг своей цели! 🎉"
NEW_GOAL_BUTTON = "Новая цель"

form_router = Router()

# class IsInitializedFilter(BaseFilter):
#     async def __call__(self, message: Message) -> bool:
#         user = await get_user(message.from_user.id)
#         return user is not None and user[2] is not None

class GoalStates(StatesGroup):
    waiting_for_goal = State()
    goal_set = State()
    checkin = State()

def get_checkin_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да"), KeyboardButton(text="Нет")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Выбери вариант"
    )
    return kb

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

def get_goal_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=NEW_GOAL_BUTTON)]],
        resize_keyboard=True
    )
    return kb


@form_router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.set_state(GoalStates.waiting_for_goal)
    await message.answer(
        "Привет! Напиши свою цель или привычку, которую хочешь внедрить или убрать. "
        "Я буду тебе помогать мотивацией!",
        reply_markup=get_goal_keyboard()
    )

@form_router.message(lambda m: m.text == NEW_GOAL_BUTTON)
async def switch_theme(message: types.Message, state: FSMContext):
    await state.set_state(GoalStates.waiting_for_goal)
    await message.answer(
        "Опиши новую цель или привычку, которую ты хочешь изменить."
    )

@form_router.message(GoalStates.waiting_for_goal)
async def handle_goal(message: types.Message, state: FSMContext):
    user = message.from_user
    goal = message.text.strip()
    if not goal or goal == NEW_GOAL_BUTTON:
        return
    await set_goal(user, goal)
    await message.answer(
        f"Твоя цель сохранена!\nТеперь я буду регулярно отправлять тебе мотивационные сообщения.",
        reply_markup=get_goal_keyboard()
    )
    await send_next_motivation(user.id, message.bot)
    await state.set_state(GoalStates.goal_set)

@form_router.message(
    # GoalStates.checkin,
    lambda m: m.text and m.text.lower() in ["да", "нет"]
)
async def handle_checkin(message: types.Message, state: FSMContext):
    user = message.from_user
    answer = message.text.lower().strip()
    user_row = await get_user(user.id)
    if not user_row or not user_row[2]:
        return
    hardness = user_row[3]
    if answer == "да":
        await update_hardness(user.id, -1)
        if hardness <= 1:
            await message.answer(VICTORY_MESSAGE, reply_markup=ReplyKeyboardRemove())
            await set_goal(user, None)  # Clear goal
            await state.set_state(GoalStates.waiting_for_goal)  # optionally reset to new goal
        else:
            await message.answer(f"Молодец! Продолжаем!", reply_markup=ReplyKeyboardRemove())
            await state.set_state(GoalStates.goal_set)
    elif answer == "нет":
        await update_hardness(user.id, +3)
        await message.answer(f"Не сдавайся! Я с тобой.", reply_markup=ReplyKeyboardRemove())
        await state.set_state(GoalStates.goal_set)
    
    await update_last_checkin(user.id)

async def send_next_motivation(user_id, bot):
    user = await get_user(user_id)
    if not user or not user[2]:  # goal is at index 2
        return
    goal = user[2]
    hardness = user[3]
    prompt = (
       f'''Замотивируй чтобы удовлетворить следующий запрос '{goal}'. Степень жесткости мотивации должна быть {hardness} из 21. Ответ предоставь в JSON в следующем формате {{"motivation":"<текст мотивации на русском языке>"}}.'''
    )
    try:
        motivation = generate_motivation(prompt)
        await bot.send_message(user_id, motivation, reply_markup=get_goal_keyboard())
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
    await bot.send_message(
        user_id, 
        CHECKIN_QUESTION,
        reply_markup=get_checkin_keyboard()
    )
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

async def main():
    logging.basicConfig(level=logging.DEBUG)
    await init_db()
    bot = Bot(token=TELEGRAM_TOKEN)
    dp = Dispatcher()

    dp.include_router(form_router)

    # dp.message.register(cmd_start, Command(commands=["start"]))
    # dp.message.register(switch_theme, lambda m: m.text == NEW_GOAL_BUTTON)
    # dp.message.register(handle_goal, lambda m: m.text and m.text not in [NEW_GOAL_BUTTON, "да", "нет"] and not m.text.startswith('/'))
    # dp.message.register(handle_checkin, lambda m: m.text in ["да", "нет"])

    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_and_send, "interval", minutes=30, args=[bot])
    scheduler.start()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
