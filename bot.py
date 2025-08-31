import os
import asyncio
import sqlite3
from pyrogram import Client, filters

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

bot = Client("auction-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# SQLite setup
conn = sqlite3.connect("auction.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS sold (player TEXT, team TEXT, price INTEGER)")
cur.execute("CREATE TABLE IF NOT EXISTS unsold (player TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS teams (team TEXT, captain TEXT)")
conn.commit()

current_player = None
current_bid = 0
current_bidder = None
auction_active = False
bid_task = None


async def auto_close(chat_id):
    """Close auction after inactivity"""
    global auction_active, current_player, current_bid, current_bidder

    await asyncio.sleep(15)
    if auction_active:
        await bot.send_message(chat_id, f"⚠️ 15 seconds left for {current_player}! Place your bids fast!")
    await asyncio.sleep(15)

    if auction_active:
        if current_bidder:
            await bot.send_message(chat_id, f"✅ SOLD! {current_player} goes to {current_bidder} for {current_bid} coins.")
            cur.execute("INSERT INTO sold VALUES (?, ?, ?)", (current_player, current_bidder, current_bid))
            cur.execute("INSERT OR IGNORE INTO teams VALUES (?, ?)", (current_bidder, current_bidder))
        else:
            await bot.send_message(chat_id, f"❌ UNSOLD! No bids for {current_player}.")
            cur.execute("INSERT INTO unsold VALUES (?)", (current_player,))
        conn.commit()

        auction_active = False
        current_player = None


@bot.on_message(filters.command("start_auction"))
async def start_auction(client, message):
    global auction_active, current_player, current_bid, current_bidder, bid_task
    if auction_active:
        return await message.reply("⚠️ Another auction is already running. End it first.")

    if len(message.command) < 2:
        return await message.reply("Usage: /start_auction <player_name>")

    current_player = " ".join(message.command[1:])
    current_bid = 0
    current_bidder = None
    auction_active = True

    await message.reply(f"🎬 Auction started for **{current_player}**!\nUse `/bid <amount>` to place your bids.")

    bid_task = asyncio.create_task(auto_close(message.chat.id))


@bot.on_message(filters.command("bid"))
async def bid(client, message):
    global current_bid, current_bidder, auction_active
    if not auction_active:
        return await message.reply("⚠️ No active auction. Start one with /start_auction")

    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply("Usage: /bid <amount>")

    amount = int(message.command[1])
    if amount <= current_bid:
        return await message.reply(f"⚠️ Bid must be higher than {current_bid}")

    current_bid = amount
    current_bidder = message.from_user.first_name
    await message.reply(f"💰 {current_bidder} bids {current_bid} coins for {current_player}!")


@bot.on_message(filters.command("end_auction"))
async def end_auction(client, message):
    global auction_active, current_player, current_bid, current_bidder, bid_task
    if not auction_active:
        return await message.reply("⚠️ No active auction to end.")

    if bid_task:
        bid_task.cancel()

    if current_bidder:
        await message.reply(f"✅ SOLD! {current_player} goes to {current_bidder} for {current_bid} coins.")
        cur.execute("INSERT INTO sold VALUES (?, ?, ?)", (current_player, current_bidder, current_bid))
        cur.execute("INSERT OR IGNORE INTO teams VALUES (?, ?)", (current_bidder, current_bidder))
    else:
        await message.reply(f"❌ UNSOLD! No bids for {current_player}.")
        cur.execute("INSERT INTO unsold VALUES (?)", (current_player,))
    conn.commit()

    auction_active = False
    current_player = None


@bot.on_message(filters.command("teams"))
async def teams(client, message):
    cur.execute("SELECT team, captain FROM teams")
    rows = cur.fetchall()
    if not rows:
        return await message.reply("⚠️ No teams created yet.")

    txt = "📋 Teams:\n"
    for r in rows:
        txt += f"🏏 {r[0]} (Captain: {r[1]})\n"
    await message.reply(txt)


@bot.on_message(filters.command("unsold"))
async def unsold(client, message):
    cur.execute("SELECT player FROM unsold")
    rows = cur.fetchall()
    if not rows:
        return await message.reply("✅ No unsold players yet.")

    txt = "❌ Unsold Players:\n" + "\n".join([f"- {r[0]}" for r in rows])
    await message.reply(txt)
