import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from functools import wraps
from flask import Flask, request, jsonify
import threading
import logging
from aiohttp import *



logging.basicConfig(level=logging.DEBUG)


# Настройки логирования
logging.basicConfig(level=logging.INFO)

# Настройки Flask
app = Flask(__name__)

@app.route("/")
def index():
    return "Flask-приложение работает!"

# Настройки API партнерки
PARTNER_API_URL = "https://api.guruleads.ru/1.0"
PARTNER_ACCESS_TOKEN = "57c24d5675cd17655c1b039b54fbe081"

# Токен бота
BOT_TOKEN = "8097724924:AAHUQQMdVVHgMC6MdnzUmXBNer5RjptquMk"
WEBHOOK_URL = "https://123user123.pythonanywhere.com/webhook"

PROXY_URL = "http://51.195.137.60:80"

bot = Bot(token=BOT_TOKEN, proxy=PROXY_URL)  # Прокси напрямую в бот
dp = Dispatcher(bot)
# Словарь для хранения данных о пользователях
user_data = {}

# ID администратора
ADMIN_ID = 851939762

# Главное меню
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔑 Профиль"), KeyboardButton(text="🔍 Поиск заданий")],
        [KeyboardButton(text="📋 Доп. Информация"), KeyboardButton(text="✅ Меню")]
    ],
    resize_keyboard=True
)

# Декоратор для проверки активации
def require_activation(handler):
    @wraps(handler)
    async def wrapper(message: types.Message, *args, **kwargs):
        user_id = message.from_user.id
        if user_id not in user_data or not user_data[user_id].get("activated", False):
            await message.answer("Пожалуйста, выполните команду /start, чтобы начать пользоваться ботом.")
            return
        return await handler(message, *args, **kwargs)
    return wrapper

# Функция для выполнения запроса к API партнерки
async def call_partner_api(endpoint, method, params=None):
    url = f"{PARTNER_API_URL}/{endpoint}/{method}?access-token={PARTNER_ACCESS_TOKEN}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                error_message = await response.text()
                raise Exception(f"API Error: {error_message}")

# Функция обработки вебхуков от партнерки
@app.route("/partner_webhook", methods=["POST"])
def partner_webhook():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "Empty or invalid JSON"}), 400

        logging.info(f"Webhook data received: {data}")

        event = data.get("event")
        if not event:
            return jsonify({"status": "error", "message": "Missing 'event' field"}), 400

        user_id = data.get("user_id")
        reward = data.get("reward", 0)
        task_name = data.get("task_name", "")

        if user_id in user_data:
            user_data[user_id]["balance"] += reward
            user_data[user_id]["tasks"][task_name] = reward

            asyncio.create_task(bot.send_message(
                user_id,
                f"✅ Задание '{task_name}' выполнено! Ваш баланс пополнен на {reward}₽."
            ))

            asyncio.create_task(bot.send_message(
                ADMIN_ID,
                f"Пользователь {user_id} выполнил задание '{task_name}' и получил {reward}₽."
            ))

        return jsonify({"status": "ok"})

    except Exception as e:
        logging.error(f"Error in /partner_webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Команда /start
@dp.message(Command(commands=['start', 'help']))
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {"balance": 0, "tasks": {}, "activated": True, "last_task": None, "username": message.from_user.full_name}
    else:
        user_data[user_id]["activated"] = True

    text = (
        "🔽 <b>Меню</b>\n"
        "✅ Количество партнёров: 4\n"
        "📍 Активных заданий: 4\n"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu)

# Профиль пользователя
@dp.message(lambda message: message.text == "🔑 Профиль")
@require_activation
async def profile_handler(message: types.Message):
    user_id = message.from_user.id
    balance = user_data.get(user_id, {}).get("balance", 0)
    text = (
        "🔽 <b>Профиль</b>\n"
        "\n"
        f"Баланс:\n💳 Доступно к выводу: {balance}₽\n"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu)

# Поиск заданий
@dp.message(lambda message: message.text == "🔍 Поиск заданий")
@require_activation
async def search_tasks(message: types.Message):
    text = "🔽 <b>Доступные задания:</b>"
    task_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="МТС - 500₽", url="https://gl.guruleads.ru/click/33753/2798?erid=LjN8KPUwq")],
            [InlineKeyboardButton(text="Газпромбанк - 600₽", url="https://gl.guruleads.ru/click/33753/1139?erid=LjN8KRohD")],
            [InlineKeyboardButton(text="ВТБ - 600₽", url="https://gl.guruleads.ru/click/33753/1442?erid=LjN8KPvwo")],
            [InlineKeyboardButton(text="Совкомбанк - 400₽", url="https://gl.guruleads.ru/click/33753/2435?erid=LjN8KBkyv")]
        ]
    )
    await message.answer(text, parse_mode="HTML", reply_markup=task_buttons)

# Завершение задания
@dp.callback_query(lambda c: c.data == "complete_task")
async def complete_task(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    last_task = user_data[user_id].get("last_task")

    if not last_task:
        await callback_query.answer("Нет активного задания для завершения.", show_alert=True)
        return

    reward = last_task["reward"]
    user_data[user_id]["balance"] += reward
    user_data[user_id]["tasks"][last_task["name"]] = reward
    user_data[user_id]["last_task"] = None

    admin_text = (
        f"Пользователь {callback_query.from_user.full_name} ({user_id}) завершил задание:\n"
        f"{last_task['name']} на сумму {reward}₽."
    )
    await bot.send_message(ADMIN_ID, admin_text)

    await callback_query.answer(f"Задание '{last_task['name']}' завершено!")
    await callback_query.message.answer(
        f"✅ Задание {last_task['name']} завершено! Ваш баланс пополнен на {reward}₽.",
        reply_markup=main_menu
    )

# Команда /users
@dp.message(Command(commands=['users']))
async def send_users(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        text = "Пользователи:\n"
        for user_id, data in user_data.items():
            text += f"{data.get('username', 'Неизвестный')} ({user_id})\n"
        await message.answer(text if text != "Пользователи:\n" else "Нет пользователей.")

# Команда /tasks
@dp.message(Command(commands=['tasks']))
async def send_tasks(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        text = "Завершенные задания:\n"
        for user_id, data in user_data.items():
            completed_tasks = data.get("tasks", {})
            for task_name, reward in completed_tasks.items():
                text += f"Пользователь {data.get('username', 'Неизвестный')} ({user_id}) завершил {task_name} на {reward}₽\n"
        await message.answer(text if text != "Завершенные задания:\n" else "Нет завершенных заданий.")

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        json_update = request.get_json()
        update = types.Update(**json_update)
        asyncio.run(dp.update.update(update))
        return jsonify({"status": "ok"})
    except Exception as e:
        logging.error(f"Error in /webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

async def on_startup():
    # Проверка доступности API Telegram (без использования aiohttp.ClientSession)
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        async with session.get("https://api.telegram.org") as response:
            print(await response.text())

    # Установка вебхука
    await bot.set_webhook(WEBHOOK_URL)
async def on_shutdown():
    await bot.session.close()
    logging.info("Сессия бота закрыта")



if __name__ == "__main__":

    try:
        asyncio.run(on_startup())
        app.run(debug=True, host="0.0.0.0", port=8080, use_reloader=False)
    except KeyboardInterrupt:
        logging.info("Приложение остановлено пользователем")
    finally:
        asyncio.run(on_shutdown())