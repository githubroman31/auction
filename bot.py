import asyncio
import sqlite3
from pyrogram import Client, filters
import os
import time

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Client(
    "auction_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

DB_PATH = "auction.db"

# ----------------- Database Setup -----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS auctions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name TEXT,
        is_active INTEGER
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS bids (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        auction_id INTEGER,
        user_id INTEGER,
        amount INTEGER,
        FOREIGN KEY(auction_id) REFERENCES auctions(id),
        FOREIGN KEY(user_id) REFERENCES users(user_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS unsold_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_name TEXT,
        captain_id INTEGER,
        vice_captain_id INTEGER
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS team_players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER,
        player_name TEXT,
        FOREIGN KEY(team_id) REFERENCES teams(id)
    )""")

    conn.commit()
    conn.close()

init_db()

# ----------------- User Registration -----------------
@bot.on_message(filters.command("register"))
async def register(client, message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()
    await message.reply_text("✅ You are registered for the auction!")

# ----------------- Auction Start -----------------
@bot.on_message(filters.command("start_auction"))
async def start_auction(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /start_auction <item_name>")

    item = message.text.split(" ", 1)[1]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO auctions (item_name, is_active) VALUES (?, 1)", (item, 1))
    auction_id = c.lastrowid
    conn.commit()
    conn.close()

    await message.reply_text(f"🎉 Auction started for: **{item}**\n\nPlace your bids using /bid <amount>")

    # 30s timeout logic
    await asyncio.sleep(15)
    await message.reply_text(f"⏰ 15 seconds left to bid for **{item}**!")
    await asyncio.sleep(15)

    # End auction automatically
    await end_auction_logic(message.chat.id, auction_id, item)

# ----------------- Place Bid -----------------
@bot.on_message(filters.command("bid"))
async def place_bid(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /bid <amount>")

    try:
        amount = int(message.command[1])
    except:
        return await message.reply_text("❌ Invalid amount")

    user_id = message.from_user.id
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM auctions WHERE is_active = 1 ORDER BY id DESC LIMIT 1")
    auction = c.fetchone()
    if not auction:
        conn.close()
        return await message.reply_text("❌ No active auction right now.")

    auction_id = auction[0]
    c.execute("INSERT INTO bids (auction_id, user_id, amount) VALUES (?, ?, ?)", (auction_id, user_id, amount))
    conn.commit()
    conn.close()
    await message.reply_text(f"✅ Bid placed: {amount}")

# ----------------- End Auction Logic -----------------
async def end_auction_logic(chat_id, auction_id, item):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT user_id, amount FROM bids WHERE auction_id = ? ORDER BY amount DESC", (auction_id,))
    bids = c.fetchall()

    if not bids:
        c.execute("INSERT INTO unsold_items (item_name) VALUES (?)", (item,))
        await bot.send_message(chat_id, f"❌ {item} remained UNSOLD.")
    else:
        winner_id, winning_bid = bids[0]

        # Assign team
        c.execute("SELECT id, captain_id, vice_captain_id, team_name FROM teams WHERE captain_id = ?", (winner_id,))
        team = c.fetchone()
        if not team:
            # Create new team
            c.execute("INSERT INTO teams (team_name, captain_id) VALUES (?, ?)", (f"Team_{winner_id}", winner_id))
            team_id = c.lastrowid
            c.execute("INSERT INTO team_players (team_id, player_name) VALUES (?, ?)", (team_id, item))
        else:
            team_id, captain_id, vice_id, tname = team
            c.execute("INSERT INTO team_players (team_id, player_name) VALUES (?, ?)", (team_id, item))
            if not vice_id and len(bids) > 1:
                c.execute("UPDATE teams SET vice_captain_id = ? WHERE id = ?", (bids[1][0], team_id))

        await bot.send_message(chat_id, f"🏁 SOLD!\n\nItem: **{item}**\nWinner: `{winner_id}`\nWinning Bid: {winning_bid}")

    c.execute("UPDATE auctions SET is_active = 0 WHERE id = ?", (auction_id,))
    conn.commit()
    conn.close()

# ----------------- Show Teams -----------------
@bot.on_message(filters.command("teams"))
async def show_teams(client, message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, team_name, captain_id, vice_captain_id FROM teams")
    teams = c.fetchall()

    if not teams:
        await message.reply_text("❌ No teams yet.")
        return

    text = "🏟️ Teams Overview 🏟️\n\n"
    for team_id, tname, cap, vice in teams:
        c.execute("SELECT player_name FROM team_players WHERE team_id = ?", (team_id,))
        players = [row[0] for row in c.fetchall()]
        text += f"🏆 {tname}\n   👑 Captain: {cap}\n"
        if vice:
            text += f"   🎖️ Vice-Captain: {vice}\n"
        text += "   👥 Players:\n"
        for p in players:
            text += f"      - {p}\n"
        text += "\n"

    await message.reply_text(text)
    conn.close()

# ----------------- Show Unsold -----------------
@bot.on_message(filters.command("unsold"))
async def show_unsold(client, message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT item_name FROM unsold_items")
    items = [row[0] for row in c.fetchall()]
    conn.close()

    if not items:
        await message.reply_text("✅ No unsold items.")
    else:
        text = "📋 Unsold Items:\n" + "\n".join([f" - {i}" for i in items])
        await message.reply_text(text)

# ----------------- Set Team Name -----------------
@bot.on_message(filters.command("set_teamname"))
async def set_teamname(client, message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        return await message.reply_text("Usage: /set_teamname <new_team_name>")
    
    new_name = args[1].strip()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, team_name FROM teams WHERE captain_id = ?", (user_id,))
    team = c.fetchone()

    if not team:
        await message.reply_text("❌ You are not a captain of any team.")
    else:
        team_id, old_name = team
        c.execute("UPDATE teams SET team_name = ? WHERE id = ?", (new_name, team_id))
        conn.commit()
        await message.reply_text(f"✅ Team name updated from **{old_name or 'Unnamed'}** to **{new_name}**")

    conn.close()

# ----------------- Run Bot -----------------
bot.run()
