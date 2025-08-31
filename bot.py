# bot.py
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

bot = Client("auction_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

current_player = None
highest_bid = 0
highest_bidder = None
auction_running = False
sold_players = {}
unsold_players = []


async def end_auction(chat_id):
    global current_player, highest_bid, highest_bidder, auction_running
    if highest_bidder:
        team_name = f"Team_{highest_bidder.id}"
        if team_name not in sold_players:
            sold_players[team_name] = {
                "captain": highest_bidder.first_name,
                "players": []
            }
        sold_players[team_name]["players"].append(current_player)
        await bot.send_message(chat_id, f"✅ SOLD! {current_player} bought by {highest_bidder.mention} for {highest_bid}")
    else:
        unsold_players.append(current_player)
        await bot.send_message(chat_id, f"❌ UNSOLD: {current_player}")

    current_player = None
    highest_bid = 0
    highest_bidder = None
    auction_running = False


@bot.on_message(filters.command("start_auction"))
async def start_auction(_, message: Message):
    global current_player, highest_bid, highest_bidder, auction_running
    if auction_running:
        return await message.reply("⚠️ Auction already running!")

    if len(message.command) < 2:
        return await message.reply("Usage: /start_auction <player_name>")

    current_player = " ".join(message.command[1:])
    highest_bid = 0
    highest_bidder = None
    auction_running = True

    await message.reply(f"🎬 Auction started for **{current_player}**! Use /bid <amount>")

    await asyncio.sleep(15)
    if highest_bid == 0:
        await message.reply("⏳ 15s left and no bids yet...")

    await asyncio.sleep(15)
    if auction_running:
        await end_auction(message.chat.id)


@bot.on_message(filters.command("bid"))
async def bid(_, message: Message):
    global highest_bid, highest_bidder
    if not auction_running:
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
    await message.reply(f"💰 Highest bid now {amount} by {highest_bidder.mention}")


@bot.on_message(filters.command("teams"))
async def teams(_, message: Message):
    if not sold_players:
        return await message.reply("⚠️ No teams yet.")
    text = "🏆 **Teams** 🏆\n\n"
    for team, data in sold_players.items():
        text += f"**{team}**\n👑 Captain: {data['captain']}\n👥 Players: {', '.join(data['players'])}\n\n"
    await message.reply(text)


@bot.on_message(filters.command("unsold"))
async def unsold(_, message: Message):
    if not unsold_players:
        return await message.reply("✅ No unsold players.")
    await message.reply("❌ Unsold Players:\n" + "\n".join(unsold_players))
