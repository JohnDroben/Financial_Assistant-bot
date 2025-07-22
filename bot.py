import asyncio
import os
import random
import logging
import aiosqlite
import aiohttp  # Заменяем requests на асинхронный клиент
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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DB_NAME = "finance.db"
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")  # Безопасное хранение ключа

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
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================

async def send_transaction_confirmation(message: Message, data: dict):
    """Универсальная функция для подтверждения транзакции"""
    operation_type = "доход" if data["type"] == "income" else "расход"
    await message.answer(
        f"✅ {operation_type.capitalize()} в категории "
        f"<b>{data['category']}</b> на сумму "
        f"<b>{data['amount']:.2f} ₽</b> успешно добавлен!",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )


async def get_exchange_rates():
    """Асинхронное получение курсов валют"""
    url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/latest/USD"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"Ошибка API: {response.status}")
                    return None

                data = await response.json()

                # Проверка успешности запроса
                if data.get('result') != 'success':
                    logger.error(f"Ошибка в ответе API: {data.get('error-type', 'unknown')}")
                    return None

                return data['conversion_rates']

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Ошибка соединения: {str(e)}")
            return None


# =============================================
# ОБРАБОТЧИКИ КОМАНД
# =============================================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    try:
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
    except Exception as e:
        logger.error(f"Ошибка в cmd_start: {str(e)}")
        await message.answer("⚠️ Произошла ошибка при регистрации. Попробуйте позже.")


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
    try:
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
    except Exception as e:
        logger.error(f"Ошибка в show_finances: {str(e)}")
        await message.answer("⚠️ Произошла ошибка при получении финансовых данных.")


@dp.message(F.text == "💱 Курс валют")
async def exchange_rates(message: Message):
    try:
        rates = await get_exchange_rates()

        if not rates:
            await message.answer("⚠️ Не удалось получить актуальные курсы валют. Попробуйте позже.")
            return

        # Основные валюты
        currencies = {
            "USD": "🇺🇸 Доллар США",
            "EUR": "🇪🇺 Евро",
            "CNY": "🇨🇳 Китайский юань",
            "GBP": "🇬🇧 Фунт стерлингов"
        }

        response = ["<b>💱 Актуальные курсы к USD:</b>\n"]

        for code, name in currencies.items():
            if code in rates:
                rate = rates[code]
                response.append(f"{name}: <b>{rate:.2f}</b>")

        # Рассчитываем курс рубля
        if "RUB" in rates:
            rub_rate = rates["RUB"]
            response.append(f"\n🇷🇺 Российский рубль: <b>{rub_rate:.2f}</b>")

            # Дополнительные расчеты
            for code in ["EUR", "GBP", "CNY"]:
                if code in rates:
                    cross_rate = rub_rate / rates[code]
                    response.append(f"{currencies[code]} в рублях: <b>{cross_rate:.2f}</b>")

        response.append("\n<i>Курсы обновляются ежедневно в 12:00 МСК</i>")
        await message.answer("\n".join(response), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в exchange_rates: {str(e)}")
        await message.answer("⚠️ Произошла ошибка при получении курсов валют.")


@dp.message(F.text == "💡 Советы")
async def money_tips(message: Message):
    tips = [
        "🔹 <b>Правило 50/30/20</b>\n50% - основные расходы\n30% - желания\n20% - сбережения",
        "🔹 <b>Автосбережения</b>\nНастройте автоматические переводы 10% от дохода на накопительный счет",
        "🔹 <b>Анализ подписок</b>\nОтмените неиспользуемые подписки (стриминги, сервисы)",
        "🔹 <b>Кэшбек</b>\nИспользуйте карты с кэшбеком для повседневных трат",
        "🔹 <b>Планирование</b>\nСоставляйте список покупок перед походом в магазин",
        "🔹 <b>Экономия на ЖКХ</b>\nУстановите счетчики воды и энергосберегающие лампы",
        "🔹 <b>Правило 24 часов</b>\nПеред крупной покупкой выждите 24 часа"
    ]

    try:
        await message.answer(
            random.choice(tips),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Ещё совет", callback_data="another_tip")]
            ])
        )
    except Exception as e:
        logger.error(f"Ошибка в money_tips: {str(e)}")
        await message.answer("💡 Совет: Всегда имейте финансовую подушку безопасности!")


@dp.message(F.text == "➕ Добавить операцию")
async def add_transaction_start(message: Message, state: FSMContext):
    try:
        await state.set_state(AddTransaction.TYPE)
        await message.answer(
            "Выберите тип операции:",
            reply_markup=transaction_type_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в add_transaction_start: {str(e)}")
        await message.answer("⚠️ Не удалось начать добавление операции. Попробуйте позже.")


# =============================================
# FSM: ДОБАВЛЕНИЕ ОПЕРАЦИИ (с обработкой ошибок)
# =============================================

@dp.message(AddTransaction.TYPE)
async def process_type(message: Message, state: FSMContext):
    try:
        if message.text not in ["📈 Доход", "📉 Расход"]:
            await message.answer("Пожалуйста, выберите тип операции с клавиатуры")
            return

        await state.update_data(
            type="income" if message.text == "📈 Доход" else "expense"
        )
        await state.set_state(AddTransaction.CATEGORY)
        await message.answer("Выберите категорию:", reply_markup=categories_keyboard())
    except Exception as e:
        logger.error(f"Ошибка в process_type: {str(e)}")
        await message.answer("⚠️ Ошибка при обработке типа операции.")
        await state.clear()


@dp.message(AddTransaction.CATEGORY)
async def process_category(message: Message, state: FSMContext):
    try:
        if message.text.startswith("/"):
            await message.answer("Используйте клавиатуру для выбора категории")
            return

        await state.update_data(category=message.text)
        await state.set_state(AddTransaction.AMOUNT)
        await message.answer("Введите сумму:", reply_markup=types.ReplyKeyboardRemove())
    except Exception as e:
        logger.error(f"Ошибка в process_category: {str(e)}")
        await message.answer("⚠️ Ошибка при обработке категории.")
        await state.clear()


@dp.message(AddTransaction.AMOUNT)
async def process_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0:
            await message.answer("Сумма должна быть больше нуля")
            return
    except (ValueError, TypeError):
        await message.answer("Пожалуйста, введите корректную сумму (число больше 0)")
        return
    except Exception as e:
        logger.error(f"Ошибка в process_amount: {str(e)}")
        await message.answer("⚠️ Ошибка при обработке суммы.")
        await state.clear()
        return

    try:
        await state.update_data(amount=amount)
        await state.set_state(AddTransaction.COMMENT)
        await message.answer("Добавьте комментарий (или нажмите /skip):")
    except Exception as e:
        logger.error(f"Ошибка в process_amount (update): {str(e)}")
        await message.answer("⚠️ Ошибка при обработке суммы.")
        await state.clear()


@dp.message(AddTransaction.COMMENT)
async def process_comment(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        data["comment"] = message.text

        await add_transaction(message.from_user.id, data)
        await state.clear()
        await send_transaction_confirmation(message, data)
    except Exception as e:
        logger.error(f"Ошибка в process_comment: {str(e)}")
        await message.answer("⚠️ Не удалось добавить операцию. Попробуйте снова.")
        await state.clear()


# Пропуск комментария
@dp.message(Command("skip"), AddTransaction.COMMENT)
async def skip_comment(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        await state.clear()

        await add_transaction(message.from_user.id, data)
        await send_transaction_confirmation(message, data)
    except Exception as e:
        logger.error(f"Ошибка в skip_comment: {str(e)}")
        await message.answer("⚠️ Не удалось добавить операцию. Попробуйте снова.")
        await state.clear()


# =============================================
# ЗАПУСК БОТА
# =============================================

async def main():
    await init_db()
    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.critical(f"Критическая ошибка: {str(e)}")