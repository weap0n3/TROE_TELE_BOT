import asyncio
from pymongo import MongoClient
import os
from dotenv import load_dotenv
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, Updater

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
DB_URL = os.getenv("DB_URL")
WG_API_KEY = os.getenv("WG_API_KEY")

client = MongoClient(DB_URL)

collection = client["TROEBOT"]["Users"]

session_tasks = {}

stop = False

def final_text(name, battles, win_rate, damage):
    formatted_win_rate = f"{win_rate:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    formatted_damage = f"{damage:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    text=(f"{name}\n"
          f"Боїв - {battles}\n"
          f"Перемог - {formatted_win_rate}%\n"
          f"Урон - {formatted_damage}\n")
    return text


async def get_account_info(account_id):
    url = f"https://api.wotblitz.eu/wotb/account/info/?application_id={WG_API_KEY}&account_id={account_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            return data

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Тебе вітає TROE BOT, щоб розпочати сесію для початки вкажи свій id ігрового аккаунту wotBlitz")

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ При вводі id сталася помилка")
        return
    account_id = context.args[0]
    collection.insert_one({"_id": update.effective_user.id, "account_id": account_id})

    stats = await get_account_info(account_id)
    if stats['data'][account_id] is not None:
        await update.message.reply_text(f"✅ Твій ID {account_id} було додано, і буде використаний для твого подальшого користування")
    else:
        await update.message.reply_text(f"❌ Гравця з ID {account_id} не знайдено, перевір свій ID")

async def start_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in session_tasks:
        await update.message.reply_text("Сесія вже запущена!")
        return

    task = asyncio.create_task(run_session(update,context))
    session_tasks[user_id] = task
    await update.message.reply_text("▶️ Сесію розпочато. Чекаю нових боїв...")


async def run_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last_battle_time = None

    account_id = collection.find_one({"_id": update.effective_user.id}).get("account_id")

    stats = await get_account_info(account_id)

    username = stats['data'][account_id]['nickname']
    wins_old = stats['data'][account_id]['statistics']['all']['wins']
    battles_old = stats['data'][account_id]['statistics']['all']['battles']
    damage_old = stats['data'][account_id]['statistics']['all']['damage_dealt']

    try:
        while True:
            stats = await get_account_info(account_id)
            new_battle_time = stats['data'][account_id]['last_battle_time']
            if new_battle_time != last_battle_time:
                wins_new = stats['data'][account_id]['statistics']['all']['wins']
                battles_new = stats['data'][account_id]['statistics']['all']['battles']
                damage_new = stats['data'][account_id]['statistics']['all']['damage_dealt']
                session_wins = wins_new - wins_old
                session_battles = battles_new - battles_old
                if session_battles == 0:
                    msg = await update.message.reply_text(final_text(username, 0, 0, 0))
                    context.user_data["session_msg_id"] = msg.message_id
                else:
                    damage_session = (damage_new - damage_old) / session_battles
                    session_win_rate = session_wins / session_battles * 100
                    msg_id = context.user_data.get("session_msg_id")
                    if msg_id:
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=msg_id,
                            text=final_text(username, session_battles, session_win_rate, damage_session)
                        )
            last_battle_time = new_battle_time
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        await update.message.reply_text("Сесію зупинено")

async def stop_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    task = session_tasks.get(user_id)
    if task:
        task.cancel()
        del session_tasks[user_id]
    else:
        await update.message.reply_text("Сесія не запущена")

if __name__ == '__main__':
    print("Starting TroeBot...")
    app = Application.builder().token(API_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(CommandHandler("start_session", start_session_command))
    app.add_handler(CommandHandler("stop_session", stop_session_command))

    app.run_polling()