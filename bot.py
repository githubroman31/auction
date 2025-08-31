import os
import asyncio
from pyrogram import Client, filters

# ====== BOT CONFIG ======
API_ID = int(os.getenv("API_ID", "25021528"))
API_HASH = os.getenv("API_HASH", "ea73f0e2e8595b85030aa59a11b3ef3b")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8474302248:AAHv8ysTaoYi36tSqDgKJ-bI5yZ-sh7vd2U")

bot = Client("auction_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ====== GLOBAL STATES ======
auction_creator = None
purse_amount = None
registered_players = set()
current_player = None
highest_bid = 0
highest_bidder = None
auction_task = None
sold_players = {}
unsold_players = []

# ====== COMMANDS ======

# Set purse (only once to initialize creator)
@bot.on_message(filters.command("set_purse"))
async def set_purse(client, message):
    global auction_creator, purse_amount

    if auction_creator and message.from_user.id != auction_creator:
        return await message.reply("⚠️ Only auction creator can reset purse!")

    if len(message.command) < 2:
        return await message.reply("Usage: /set_purse <amount>")

    purse_amount = int(message.command[1])
    auction_creator = message.from_user.id
    await message.reply(f"💰 Purse set to {purse_amount} XP\n👑 Auction creator: {message.from_user.first_name}")

# Change creator
@bot.on_message(filters.command("set_creator"))
async def set_creator(client, message):
    global auction_creator

    if message.from_user.id != auction_creator:
        return await message.reply("⚠️ Only current auction creator can transfer rights!")

    if message.reply_to_message:
        new_creator = message.reply_to_message.from_user
    elif len(message.command) > 1:
        username = message.command[1]
        try:
            new_creator = await client.get_users(username)
        except:
            return await message.reply("⚠️ Invalid username.")
    else:
        return await message.reply("Usage: /set_creator @username or reply to user")

    auction_creator = new_creator.id
    await message.reply(f"👑 Auction control transferred to **{new_creator.first_name}**")

# Register players
@bot.on_message(filters.command("register"))
async def register_player(client, message):
    global registered_players, auction_creator

    if message.from_user.id != auction_creator:
        return await message.reply("⚠️ Only auction creator can register players!")

    if len(message.command) < 2:
        return await message.reply("Usage: /register <player_name>")

    player = " ".join(message.command[1:])
    registered_players.add(player)
    await message.reply(f"✅ Registered player: {player}")

# Start auction
@bot.on_message(filters.command("start_auction"))
async def start_auction(client, message):
    global current_player, highest_bid, highest_bidder, auction_task

    if message.from_user.id != auction_creator:
        return await message.reply("⚠️ Only auction creator can start auctions!")

    if len(message.command) < 2:
        return await message.reply("Usage: /start_auction <player_name>")

    player = " ".join(message.command[1:])
    if player not in registered_players:
        return await message.reply("⚠️ Player not registered!")

    current_player = player
    highest_bid = 0
    highest_bidder = None
    await message.reply(f"🏏 Auction started for **{player}**!\n💰 Current Bid: 0 XP")

    if auction_task:
        auction_task.cancel()
    auction_task = asyncio.create_task(auction_timer(client, message.chat.id))

# Bid
@bot.on_message(filters.command("bid"))
async def bid(client, message):
    global highest_bid, highest_bidder, current_player

    if not current_player:
        return await message.reply("⚠️ No active auction right now!")

    if len(message.command) < 2:
        return await message.reply("Usage: /bid <amount>")

    try:
        amount = int(message.command[1])
    except:
        return await message.reply("⚠️ Invalid amount.")

    if amount <= highest_bid:
        return await message.reply("⚠️ Bid must be higher than current bid!")

    highest_bid = amount
    highest_bidder = message.from_user
    await message.reply(f"💸 {highest_bidder.first_name} placed a bid of {highest_bid} XP for **{current_player}**")

# End auction manually
@bot.on_message(filters.command("end_auction"))
async def end_auction(client, message):
    if message.from_user.id != auction_creator:
        return await message.reply("⚠️ Only auction creator can end auctions!")

    await finalize_auction(client, message.chat.id)

# Teams
@bot.on_message(filters.command("teams"))
async def teams(client, message):
    if not sold_players:
        return await message.reply("⚠️ No players sold yet!")

    text = "📋 Teams:\n"
    for captain_id, data in sold_players.items():
        captain_name = data['captain']
        text += f"\n👑 {captain_name}'s Team:\n"
        for p, amt in data['players']:
            text += f"  • {p} ({amt} XP)\n"
    await message.reply(text)

# Unsold
@bot.on_message(filters.command("unsold"))
async def unsold(client, message):
    if not unsold_players:
        return await message.reply("⚠️ No unsold players.")
    await message.reply("🚫 Unsold Players:\n" + "\n".join(unsold_players))

# ====== HELPERS ======
async def auction_timer(client, chat_id):
    global current_player
    try:
        await asyncio.sleep(15)
        await client.send_message(chat_id, "⏳ 15s left! Place your bids fast!")
        await asyncio.sleep(15)
        await finalize_auction(client, chat_id)
    except asyncio.CancelledError:
        pass

async def finalize_auction(client, chat_id):
    global current_player, highest_bid, highest_bidder, sold_players, unsold_players, auction_task

    if not current_player:
        return

    if highest_bidder:
        cap_id = highest_bidder.id
        if cap_id not in sold_players:
            sold_players[cap_id] = {"captain": highest_bidder.first_name, "players": []}
        sold_players[cap_id]["players"].append((current_player, highest_bid))
        await client.send_message(chat_id, f"✅ SOLD! **{current_player}** bought by {highest_bidder.first_name} for {highest_bid} XP")
    else:
        unsold_players.append(current_player)
        await client.send_message(chat_id, f"🚫 UNSOLD! **{current_player}**")

    current_player = None
    highest_bid = 0
    highest_bidder = None
    if auction_task:
        auction_task.cancel()
        auction_task = None
