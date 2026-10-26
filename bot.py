import os
import asyncio
import sqlite3
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Токен берется из настроек Environment Variables на Render (или можно вписать в кавычки вторым аргументом)
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_ТОКЕН_ЗДЕСЬ")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class TradeStates(StatesGroup):
    waiting_for_amount = State()

# --- БАЗА ДАННЫХ (SQLite) ---
def init_db():
    conn = sqlite3.connect("microinvest.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    usd_balance REAL DEFAULT 100.0,
                    btc_amount REAL DEFAULT 0.0,
                    gold_amount REAL DEFAULT 0.0,
                    daily_save REAL DEFAULT 5.0
                )''')
    conn.commit()
    conn.close()

def get_user(user_id: int):
    conn = sqlite3.connect("microinvest.db")
    c = conn.cursor()
    c.execute("SELECT usd_balance, btc_amount, gold_amount, daily_save FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        row = (100.0, 0.0, 0.0, 5.0)
    conn.close()
    return row

def update_user(user_id: int, usd: float, btc: float, gold: float):
    conn = sqlite3.connect("microinvest.db")
    c = conn.cursor()
    c.execute("UPDATE users SET usd_balance = ?, btc_amount = ?, gold_amount = ? WHERE user_id = ?",
              (usd, btc, gold, user_id))
    conn.commit()
    conn.close()

# --- КОТИРОВКИ В РЕАЛЬНОМ ВРЕМЕНИ ---
async def get_live_prices():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,pax-gold&vs_currencies=usd"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                data = await resp.json()
                return {
                    "btc": float(data["bitcoin"]["usd"]),
                    "gold": float(data["pax-gold"]["usd"])
                }
    except Exception:
        return {"btc": 68000.0, "gold": 2750.0}

# --- КЛАВИАТУРЫ ---
def main_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="💼 Мой портфель")
    kb.button(text="📈 Купить активы")
    kb.button(text="🐷 Отложить за сегодня (+$5)")
    kb.button(text="🔄 Актуальные курсы")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

def buy_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🟠 Купить Bitcoin (BTC)", callback_data="buy_btc")
    kb.button(text="🟡 Купить Золото (XAU)", callback_data="buy_gold")
    kb.adjust(1)
    return kb.as_markup()

# --- ЛОГИКА БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    get_user(message.from_user.id)
    await message.answer(
        "👋 **Добро пожаловать в демо-приложение для микроинвестиций!**\n\n"
        "На вашем демо-счете уже есть **$100.00**.\n"
        "Здесь вы можете:\n"
        "• Ежедневно пополнять копилку виртуальными долларами\n"
        "• Покупать **Bitcoin** и **Золото** на любую сумму по реальным биржевым ценам.\n\n"
        "Выберите действие в меню ниже:",
        reply_markup=main_kb(),
        parse_mode="Markdown"
    )

@dp.message(F.text == "🔄 Актуальные курсы")
async def show_rates(message: types.Message):
    prices = await get_live_prices()
    await message.answer(
        f"🌍 **Биржевые котировки в реальном времени:**\n\n"
        f"🟠 **Bitcoin (BTC):** ${prices['btc']:,.2f}\n"
        f"🟡 **Золото (1 унция XAU):** ${prices['gold']:,.2f}",
        parse_mode="Markdown"
    )

@dp.message(F.text == "💼 Мой портфель")
async def show_portfolio(message: types.Message):
    usd, btc, gold, daily = get_user(message.from_user.id)
    prices = await get_live_prices()
    
    btc_val = btc * prices["btc"]
    gold_val = gold * prices["gold"]
    total_val = usd + btc_val + gold_val

    await message.answer(
        f"💼 **Ваш инвестиционный портфель:**\n\n"
        f"💵 Свободный кэш (копилка): **${usd:,.2f}**\n"
        f"🟠 Bitcoin: **{btc:.6f} BTC** (~${btc_val:,.2f})\n"
        f"🟡 Золото: **{gold:.5f} oz** (~${gold_val:,.2f})\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 **Общая стоимость активов:** **${total_val:,.2f}**",
        parse_mode="Markdown"
    )

@dp.message(F.text == "🐷 Отложить за сегодня (+$5)")
async def save_daily(message: types.Message):
    usd, btc, gold, daily = get_user(message.from_user.id)
    usd += daily
    update_user(message.from_user.id, usd, btc, gold)
    await message.answer(
        f"✅ Вы отложили **${daily:.2f}** в ежедневную копилку!\n"
        f"💵 Доступный баланс для покупок: **${usd:,.2f}**",
        parse_mode="Markdown"
    )

@dp.message(F.text == "📈 Купить активы")
async def buy_menu(message: types.Message):
    usd, _, _, _ = get_user(message.from_user.id)
    await message.answer(
        f"💵 Доступно в копилке: **${usd:,.2f}**\n"
        f"Какой актив вы хотите докупить в портфель?",
        reply_markup=buy_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("buy_"))
async def select_asset(callback: types.CallbackQuery, state: FSMContext):
    asset = callback.data.split("_")[1]
    asset_name = "Bitcoin (BTC)" if asset == "btc" else "Золото (XAU)"
    
    await state.update_data(asset=asset)
    await state.set_state(TradeStates.waiting_for_amount)
    await callback.message.answer(
        f"Введите сумму в долларах ($), на которую хотите купить **{asset_name}** (например: `2.5` или `15`):",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(TradeStates.waiting_for_amount)
async def process_buy(message: types.Message, state: FSMContext):
    try:
        amount_usd = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число (например, `5`).", parse_mode="Markdown")
        return

    usd, btc, gold, _ = get_user(message.from_user.id)

    if amount_usd <= 0:
        await message.answer("❌ Сумма покупки должна быть больше нуля.")
        return
    if amount_usd > usd:
        await message.answer(f"❌ Недостаточно средств в копилке. Ваш баланс: **${usd:,.2f}**", parse_mode="Markdown")
        return

    data = await state.get_data()
    asset = data["asset"]
    prices = await get_live_prices()

    if asset == "btc":
        bought_units = amount_usd / prices["btc"]
        btc += bought_units
        asset_label = f"{bought_units:.6f} BTC"
        rate_label = f"${prices['btc']:,.2f}"
    else:
        bought_units = amount_usd / prices["gold"]
        gold += bought_units
        asset_label = f"{bought_units:.5f} унций золота"
        rate_label = f"${prices['gold']:,.2f}"

    usd -= amount_usd
    update_user(message.from_user.id, usd, btc, gold)
    await state.clear()

    await message.answer(
        f"🎉 **Сделка успешно выполнена!**\n\n"
        f"📥 Куплено: **{asset_label}**\n"
        f"💵 Потрачено: **${amount_usd:,.2f}** (по курсу {rate_label})\n"
        f"💰 Остаток в копилке: **${usd:,.2f}**",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )

# --- ФОНОВЫЙ ВЕБ-СЕРВЕР ДЛЯ RENDER (ПОДДЕРЖАНИЕ РАБОТЫ 24/7) ---
async def health_check(request):
    return web.Response(text="MicroInvest Bot is running 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    init_db()
    await start_web_server()
    print("✅ Сервер и бот запущены на 24/7!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
