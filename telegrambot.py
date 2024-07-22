from typing import Final
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue, Job
import json
import requests
from datetime import datetime, timezone, timedelta
import time

bottoken: Final = "bot key/token"
botusername: Final = "@bot username"


DATA_SLICE_DAYS = 1
DATETIME_FORMAT = "%Y-%m-%dT%H:%M"
counter = 0

# Store running tasks to manage them
tasks = {}

# API call function to fetch Bitcoin price
async def fetch_bitcoin_price() -> float:
    timeslot_end = datetime.now(timezone.utc)
    end_date = timeslot_end.strftime(DATETIME_FORMAT)
    start_date = (timeslot_end - timedelta(days=DATA_SLICE_DAYS)).strftime(DATETIME_FORMAT)
    url = f'https://api.exchange.coinbase.com/products/BTC-EUR/candles?granularity=900&start={start_date}&end={end_date}'
    headers = {"Accept": "application/json"}
    response = requests.get(url, headers=headers)
    external_data = json.loads(response.text)
    latest_price = external_data[-1][4]  # Closing price of the latest entry
    return float(latest_price)

# API call function to fetch Bitcoin price 24 hours ago
async def fetch_bitcoin_price_24h_ago() -> float:
    timeslot_end = datetime.now(timezone.utc)
    timeslot_start = timeslot_end - timedelta(hours=24)
    end_date = timeslot_start.strftime(DATETIME_FORMAT)
    start_date = (timeslot_start - timedelta(hours=1)).strftime(DATETIME_FORMAT)
    url = f'https://api.exchange.coinbase.com/products/BTC-EUR/candles?granularity=3600&start={start_date}&end={end_date}'
    headers = {"Accept": "application/json"}
    response = requests.get(url, headers=headers)
    external_data = json.loads(response.text)
    price_24h_ago = external_data[0][4]  # Closing price of the first entry in the last hour segment
    return float(price_24h_ago)

# Commands
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot Active! Use /help for the commands.")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global counter
    counter = 0
    chat_id = update.message.chat_id
    if chat_id in tasks:
        tasks[chat_id].schedule_removal()
        del tasks[chat_id]
        await update.message.reply_text("Bot Stopped!")
    else:
        await update.message.reply_text("No active task to stop.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("I send Bitcoin prices in intervals!\nWrite <start> and then the interval in seconds.\n(Example: <start 5> or <start minute>)")

# Interval functions
async def send_interval(context: ContextTypes.DEFAULT_TYPE):
    global counter
    counter += 1
    job = context.job
    chat_id = job.data['chat_id']
    price = await fetch_bitcoin_price()
    price24hr = await fetch_bitcoin_price_24h_ago()
    if price > price24hr:
        percent = f'+{round(((price / price24hr) * 100) - 100, 2)}%'
    elif price < price24hr:
        percent = f'-{round(((price24hr / price) * 100) - 100, 2)}%'
    elif price == price24hr:
        percent = '+0%'
    else:
        percent = 'Error in calculation!'
    await context.bot.send_message(chat_id=chat_id, text=(f'({counter}) NEW: €{price} (old:€{price24hr})\n--> {percent} from 24hrs ago'))
 
# Response handler
async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    text = text.lower()
    chat_id = update.message.chat_id
    job_queue = context.job_queue

    if 'start minute' in text:
        interval = 60
    elif 'start hour' in text:
        interval = 3600
    elif 'start day' in text:
        interval = 86400
    elif 'start' in text:
        interval = int(''.join(filter(str.isdigit, text)))
    else:
        await update.message.reply_text("Unknown command. Use /help to see available commands.")
        return

    if chat_id in tasks:
        tasks[chat_id].schedule_removal()

    job = job_queue.run_repeating(send_interval, interval, data={'chat_id': chat_id})
    tasks[chat_id] = job
    await update.message.reply_text(f"Started sending Bitcoin prices every {interval} seconds.")

# Message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_type: str = update.message.chat.type
    usertext: str = update.message.text
    print(f'User "{update.message.chat.id}" in "{message_type}": {usertext}')

    if message_type == "group":
        if botusername in usertext:
            newusertext: str = usertext.replace(botusername, "").strip()
            await handle_response(update, context, newusertext)
        else:
            return
    else:
        await handle_response(update, context, usertext)

async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f'Update "{update}" caused error "{context.error}"')

if __name__ == '__main__':  
    print('Bot starting...')
    app = Application.builder().token(bottoken).build()

    # Commands
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('stop', stop_command))
    app.add_handler(CommandHandler('help', help_command))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    # Errors
    app.add_error_handler(error)
    print('Bot polling...')
    app.run_polling(poll_interval=1)