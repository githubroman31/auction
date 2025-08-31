import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

# Env se credentials le raha hai
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

bot = Client(
    "auction_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# In-memory DB (tum chaho to sqlite use kar sakte ho)
current_auction = None
highest_bid = 0
highest_bidder = None
auction_task = None
sold_players = {}
unsold_players = []

async def end_auction(chat_id):
    global current_auction, highest_bid, highest_bidder
    if highest_bidder:
        # Sold
        team_name = f"Team_{highest_bidder.id}"
        if team_name not in sold_players:
            sold_players[team_name] = {
                "captain": highest_bidder.first_name,
                "vice_captain": None,
                "players": []
            }
        sold_players[team_name]["players"].append(current_auction)
        await bot.send_message(
            chat_id,
            f"✅ SOLD! **{current_auction}** bought by {highest_bidder.mention} for {highest_bid}."
        )
    else:
        # Unsold
        unsold_players.append(current_auction)
        await bot.send_message(chat_id, f"❌ UNSOLD: {current_auction}")
    # Reset auction
    current_auction = None
    highest_bid = 0
    highest_bidder = None

@bot.on_message(filters.command("start_auction"))
async def start_auction(_, message: Message):
    global current_auction, highest_bid, highest_bidder, auction_task
    if len(message.command) < 2:
        return await message.reply("Usage: /start_auction <player_name>")
    if current_auction:
        return await message.reply("⚠️ Auction already running!")

    current_auction = " ".join(message.command[1:])
    highest_bid = 0
    highest_bidder = None
    await message.reply(f"🎬 Auction started for **{current_auction}**! Place your bids with /bid <amount>")

    async def countdown():
        global auction_task
        await asyncio.sleep(15)
        if highest_bid == 0:
            await message.reply("⏳ 15s left and no bids yet...")
        await asyncio.sleep(15)
        await end_auction(message.chat.id)
        auction_task = None

    auction_task = asyncio.create_task(countdown())

@bot.on_message(filters.command("bid"))
async def bid(_, message: Message):
    global highest_bid, highest_bidder
    if not current_auction:
        return await message.reply("⚠️ No auction running now.")
    if len(message.command) < 2:
        return await message.reply("Usage: /bid <amount>")

    try:
        amount = int(message.command[1])
    except ValueError:
        return await message.reply("❌ Invalid bid amount.")

    if amount <= highest_bid:
        return await message.reply(f"⚠️ Bid must be higher than {highest_bid}")

    highest_bid = amount
    highest_bidder = message.from_user
    await message.reply(f"💰 New highest bid: {amount} by {highest_bidder.mention}")

@bot.on_message(filters.command("teams"))
async def teams(_, message: Message):
    if not sold_players:
        return await message.reply("⚠️ No teams yet.")
    text = "🏆 **Teams** 🏆\n\n"
    for team, data in sold_players.items():
        text += f"**{team}**\n"
        text += f"👑 Captain: {data['captain']}\n"
        text += f"⭐ Vice Captain: {data['vice_captain'] or 'Not set'}\n"
        text += f"👥 Players: {', '.join(data['players'])}\n\n"
    await message.reply(text)

@bot.on_message(filters.command("unsold"))
async def unsold(_, message: Message):
    if not unsold_players:
        return await message.reply("✅ No unsold players.")
    await message.reply("❌ Unsold Players:\n" + "\n".join(unsold_players))

bot.run()
