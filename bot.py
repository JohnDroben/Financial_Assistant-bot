import asyncio
import os
import random
import logging
import aiosqlite
import requests
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from dotenv import load_dotenv




load_dotenv()


# Конфигурация
logging.basicConfig(level=logging.INFO)
DB_NAME = "finance.db"

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher(storage=MemoryStorage())


# =============================================
# КЛАВИАТУРЫ
# =============================================

def main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📊 Мои финансы"))
    builder.row(
        KeyboardButton(text="💱 Курс валют"),
                KeyboardButton(text="💡 Советы"),
    )
    builder.row(KeyboardButton(text="➕ Добавить операцию"))
    return builder.as_markup(resize_keyboard=True)


def categories_keyboard():
    categories = ["🍔 Еда", "🚕 Транспорт", "🏠 Жилье",
                  "🎮 Развлечения", "💊 Здоровье", "👕 Одежда"]
    builder = ReplyKeyboardBuilder()
    for category in categories:
        builder.add(KeyboardButton(text=category))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def transaction_type_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="📈 Доход"))
    builder.add(KeyboardButton(text="📉 Расход"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


# =============================================
# СОСТОЯНИЯ FSM
# =============================================

class AddTransaction(StatesGroup):
    TYPE = State()
    CATEGORY = State()
    AMOUNT = State()
    COMMENT = State()


# =============================================
# БАЗА ДАННЫХ (АСИНХРОННАЯ)
# =============================================

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                balance REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT CHECK(type IN ('income', 'expense')),
                category TEXT,
                amount REAL NOT NULL,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        await db.commit()


async def register_user(user_id: int, full_name: str, username: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, full_name, username) VALUES (?, ?, ?)",
            (user_id, full_name, username)
        )
        await db.commit()


async def add_transaction(user_id: int, data: dict):
    async with aiosqlite.connect(DB_NAME) as db:
        # Добавляем транзакцию
        await db.execute(
            """INSERT INTO transactions 
            (user_id, type, category, amount, comment) 
            VALUES (?, ?, ?, ?, ?)""",
            (user_id, data['type'], data['category'], data['amount'], data.get('comment', ''))
        )

        # Обновляем баланс пользователя
        multiplier = 1 if data['type'] == 'income' else -1
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE telegram_id = ?",
            (multiplier * data['amount'], user_id)
        )
        await db.commit()


async def get_user_balance(user_id: int) -> float:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT balance FROM users WHERE telegram_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_monthly_summary(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        # Получаем доходы/расходы за текущий месяц
        cursor = await db.execute('''
            SELECT 
                type,
                SUM(amount) as total,
                category
            FROM transactions
            WHERE 
                user_id = ? 
                AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
            GROUP BY type, category
        ''', (user_id,))

        rows = await cursor.fetchall()
        return rows


# =============================================
# ОБРАБОТЧИКИ КОМАНД
# =============================================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await register_user(
        user_id=message.from_user.id,
        full_name=message.from_user.full_name,
        username=message.from_user.username
    )

    await message.answer(
        "💰 <b>Финансовый помощник</b>\n\n"
        "Я помогу вам управлять личными финансами:\n"
        "- 📊 Учет доходов и расходов\n"
        "- 💡 Персональные советы по экономии\n"
        "- 📈 Анализ финансовых привычек\n\n"
        "Выберите действие:",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "<b>Доступные команды:</b>\n"
        "/start - Начало работы\n"
        "/balance - Текущий баланс\n"
        "/report - Финансовый отчет\n"
        "/add - Добавить операцию\n\n"
        "<b>Основные функции:</b>\n"
        "• Добавление доходов/расходов\n"
        "• Анализ по категориям\n"
        "• Советы по оптимизации бюджета"
    )
    await message.answer(help_text, parse_mode="HTML")


@dp.message(F.text == "📊 Мои финансы")
async def show_finances(message: Message):
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)

    # Получаем статистику за месяц
    summary = await get_monthly_summary(user_id)

    if not summary:
        await message.answer(
            f"💼 Ваш текущий баланс: <b>{balance:.2f} ₽</b>\n"
            "У вас пока нет операций за этот месяц.",
            parse_mode="HTML"
        )
        return

    # Формируем отчет
    income = 0
    expenses = 0
    report = ["<b>📈 Финансовый отчет за месяц:</b>", ""]

    for row in summary:
        trans_type, total, category = row
        if trans_type == 'income':
            income += total
            report.append(f"⬆️ <b>{category}</b>: +{total:.2f} ₽")
        else:
            expenses += total
            report.append(f"⬇️ <b>{category}</b>: -{total:.2f} ₽")

    report.append("\n📊 <b>Итого:</b>")
    report.append(f"Доходы: <b>+{income:.2f} ₽</b>")
    report.append(f"Расходы: <b>-{expenses:.2f} ₽</b>")
    report.append(f"Баланс: <b>{balance:.2f} ₽</b>")

    # Анализ расходов
    if expenses > 0:
        savings_percent = (income - expenses) / income * 100 if income > 0 else 0
        report.append("\n💡 <b>Анализ:</b>")
        report.append(f"Сбережения: <b>{savings_percent:.1f}%</b> от доходов")

        if savings_percent < 20:
            report.append("Рекомендация: Попробуйте сократить расходы на развлечения и питание вне дома")

    await message.answer("\n".join(report), parse_mode="HTML")


@dp.message(F.text == "💱 Курс валют")
async def exchange_rates(message: Message):
    rates = {
        "USD": 75.50,
        "EUR": 82.30,
        "CNY": 10.45,
        "GBP": 95.20
    }

    response = ["<b>💱 Актуальные курсы:</b>",""]
    for currency, rate in rates.items():
        url = "https://v6.exchangerate-api.com/v6/09edf8b2bb246e1f801cbfba/latest/USD"
        try:
            response = requests.get(url)
            data = response.json()
            if response.status_code != 200:
                await message.answer("Не удалось получить данные о курсе валют!")
                return
            usd_to_rub = data['conversion_rates']['RUB']
            eur_to_usd = data['conversion_rates']['EUR']
            cny_to_usd = data['conversion_rates']['CNY']
            gbp_to_usd = data['conversion_rates']['GBP']

            euro_to_rub =  usd_to_rub / eur_to_usd
            cny_to_rub = usd_to_rub / cny_to_usd
            gbp_to_rub = usd_to_rub / gbp_to_usd

            await message.answer(f"1 USD - {usd_to_rub:.2f}  RUB\n"
                                 f"1 EUR - {euro_to_rub:.2f}  RUB\n" 
                                 f"1 CNY - {cny_to_rub:.2f}  RUB\n"
                                 f"1 GBP - {gbp_to_rub:.2f}  RUB"
                                 )

        except:
            await message.answer("Произошла ошибка")

        response.append(f"{currency}/RUB: <b>{rate:.2f}</b>")

    response.append("\n<i>Курсы обновляются ежедневно в 12:00 МСК</i>")
    await message.answer("\n".join(response), parse_mode="HTML")


@dp.message(F.text == "💡 Советы")
async def money_tips(message: Message):
    tips = [
        "🔹 <b>Правило 50/30/20</b>\n 50% - основные расходы\n30% - желания\n20% - сбережения",
        "🔹 <b>Автосбережения</b>\n Настройте автоматические переводы 10% от дохода на накопительный счет",
        "🔹 <b>Анализ подписок</b>\n Отмените неиспользуемые подписки (стриминги, сервисы)",
        "🔹 <b>Кэшбек</b>\n Используйте карты с кэшбеком для повседневных трат",
        "🔹 <b>Планирование</b>\n Составляйте список покупок перед походом в магазин"
    ]

    await message.answer(
        random.choice(tips),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ещё совет", callback_data="another_tip")]
        ])
    )


@dp.message(F.text == "➕ Добавить операцию")
async def add_transaction_start(message: Message, state: FSMContext):
    await state.set_state(AddTransaction.TYPE)
    await message.answer(
        "Выберите тип операции:",
        reply_markup=transaction_type_keyboard()
    )


# =============================================
# FSM: ДОБАВЛЕНИЕ ОПЕРАЦИИ
# =============================================

@dp.message(AddTransaction.TYPE)
async def process_type(message: Message, state: FSMContext):
    if message.text not in ["📈 Доход", "📉 Расход"]:
        await message.answer("Пожалуйста, выберите тип операции с клавиатуры")
        return

    await state.update_data(
        type="income" if message.text == "📈 Доход" else "expense"
    )
    await state.set_state(AddTransaction.CATEGORY)
    await message.answer("Выберите категорию:", reply_markup=categories_keyboard())


@dp.message(AddTransaction.CATEGORY)
async def process_category(message: Message, state: FSMContext):
    # Проверка пользовательских категорий
    if message.text.startswith("/"):
        await message.answer("Используйте клавиатуру для выбора категории")
        return

    await state.update_data(category=message.text)
    await state.set_state(AddTransaction.AMOUNT)
    await message.answer("Введите сумму:", reply_markup=types.ReplyKeyboardRemove())


@dp.message(AddTransaction.AMOUNT)
async def process_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer("Пожалуйста, введите корректную сумму (число больше 0)")
        return

    await state.update_data(amount=amount)
    await state.set_state(AddTransaction.COMMENT)
    await message.answer("Добавьте комментарий (или нажмите /skip):")


@dp.message(AddTransaction.COMMENT)
async def process_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    data["comment"] = message.text

    await add_transaction(message.from_user.id, data)
    await state.clear()

    operation_type = "доход" if data["type"] == "income" else "расход"
    await message.answer(
        f"✅ {operation_type.capitalize()} в категории "
        f"<b>{data['category']}</b> на сумму "
        f"<b>{data['amount']:.2f} ₽</b> успешно добавлен!",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )


# Пропуск комментария
@dp.message(Command("skip"), AddTransaction.COMMENT)
async def skip_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    await add_transaction(message.from_user.id, data)
    operation_type = "доход" if data["type"] == "income" else "расход"
    await message.answer(
        f"✅ {operation_type.capitalize()} в категории "
        f"<b>{data['category']}</b> на сумму "
        f"<b>{data['amount']:.2f} ₽</b> успешно добавлен!",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )


# =============================================
# ЗАПУСК БОТА
# =============================================

async def main():
    await init_db()
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())