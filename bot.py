import os
import asyncio
from pyrogram import Client, filters

API_ID = int(os.getenv("API_ID", "25021528"))
API_HASH = os.getenv("API_HASH", "ea73f0e2e8595b85030aa59a11b3ef3b")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8474302248:AAHv8ysTaoYi36tSqDgKJ-bI5yZ-sh7vd2U")

bot = Client("auction_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== Global State =====
current_creator = None  # Current auction controller (who started)
purse_amount = None
registered_players = {}  # {player_name: xp}
current_player = None
highest_bid = 0
highest_bidder = None
auction_task = None
teams = {}  # {team_name: {"captain": str, "vice_captain": str, "players": [], "spent": int, "purse": int}}
sold_players = {}
unsold_players = []


# ===== Helper: Check if user is admin =====
async def is_admin(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    member = await bot.get_chat_member(chat_id, user_id)
    return member.status in ["administrator", "creator"]


# ===== Set Purse (creator/admin only) =====
@bot.on_message(filters.command("set_purse"))
async def set_purse(client, message):
    global purse_amount, current_creator

    if not (message.from_user.id == current_creator or await is_admin(message)):
        return await message.reply("⚠️ Only auction creator or admin can set purse!")

    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply("Usage: /set_purse <amount>")

    purse_amount = int(message.command[1])
    current_creator = message.from_user.id
    await message.reply(f"💰 Purse set to {purse_amount} XP by {message.from_user.first_name}")


# ===== Register Player (creator/admin only) =====
@bot.on_message(filters.command("register"))
async def register_player(client, message):
    global registered_players

    if not (message.from_user.id == current_creator or await is_admin(message)):
        return await message.reply("⚠️ Only auction creator or admin can register players!")

    if len(message.command) < 3 or not message.command[2].isdigit():
        return await message.reply("Usage: /register <player_name> <xp (1-8)>")

    name = message.command[1]
    xp = int(message.command[2])
    registered_players[name] = xp
    await message.reply(f"✅ Registered player: {name} (XP: {xp})")


# ===== Add Player Later (creator/admin only) =====
@bot.on_message(filters.command("add_player"))
async def add_player(client, message):
    global registered_players, unsold_players

    if not (message.from_user.id == current_creator or await is_admin(message)):
        return await message.reply("⚠️ Only auction creator or admin can add players!")

    if len(message.command) < 3 or not message.command[2].isdigit():
        return await message.reply("Usage: /add_player <player_name> <xp (1-8)>")

    name = message.command[1]
    xp = int(message.command[2])
    registered_players[name] = xp
    unsold_players.append(name)
    await message.reply(f"➕ Player {name} (XP {xp}) added to unsold pool.")


# ===== Start Auction (anyone/public) =====
@bot.on_message(filters.command("start_auction"))
async def start_auction(client, message):
    global current_player, highest_bid, highest_bidder, auction_task, current_creator

    if len(message.command) < 2:
        return await message.reply("Usage: /start_auction <player_name>")

    player = message.command[1]
    if player not in registered_players:
        return await message.reply("⚠️ Player not registered!")

    current_player = player
    highest_bid = 0
    highest_bidder = None
    current_creator = message.from_user.id  # Whoever starts becomes current auction creator
    await message.reply(f"🏏 Auction started for **{player}**!\n💰 Current Bid: 0 XP")

    if auction_task:
        auction_task.cancel()
    auction_task = asyncio.create_task(auction_timer(message.chat.id))


# ===== Bid (captains only) =====
@bot.on_message(filters.command("bid"))
async def bid(client, message):
    global highest_bid, highest_bidder, current_player, teams

    if not current_player:
        return await message.reply("⚠️ No active auction!")

    if len(message.command) < 2:
        return await message.reply("Usage: /bid <amount>")

    user_name = message.from_user.first_name
    team_name = f"Team {user_name}"

    # Only captain can bid
    if team_name not in teams or teams[team_name]["captain"] != user_name:
        return await message.reply("⚠️ Only team captains can place bids!")

    try:
        amount = int(message.command[1])
    except:
        return await message.reply("⚠️ Invalid amount.")

    purse_left = teams[team_name]["purse"] - teams[team_name]["spent"]
    if amount <= highest_bid:
        return await message.reply(f"⚠️ Bid must be higher than {highest_bid} XP!")
    if amount > purse_left:
        return await message.reply(f"⚠️ Not enough purse! Available: {purse_left} XP")

    highest_bid = amount
    highest_bidder = user_name
    await message.reply(f"💸 {highest_bidder} placed a bid of {highest_bid} XP for **{current_player}**")


# ===== End Auction (creator/admin only) =====
@bot.on_message(filters.command("end_auction"))
async def end_auction(client, message):
    if not (message.from_user.id == current_creator or await is_admin(message)):
        return await message.reply("⚠️ Only current auction creator/admin can end auction!")

    await finalize_auction(message.chat.id)


# ===== Teams (public) =====
@bot.on_message(filters.command("teams"))
async def show_teams(client, message):
    if not sold_players:
        return await message.reply("⚠️ No teams yet!")

    text = "📋 Teams:\n"
    for team, data in sold_players.items():
        text += f"\n👑 {data['captain']}'s Team:\n"
        for p, amt in data['players']:
            text += f"  • {p} ({amt} XP)\n"
        if data.get("vice"):
            text += f"  🥈 Vice Captain: {data['vice']}\n"
    await message.reply(text)


# ===== Unsold Players (public) =====
@bot.on_message(filters.command("unsold"))
async def show_unsold(client, message):
    if not unsold_players:
        return await message.reply("✅ No unsold players")
    await message.reply("🚫 Unsold Players:\n" + "\n".join(unsold_players))


# ===== Auction Timer =====
async def auction_timer(chat_id):
    global current_player
    try:
        await asyncio.sleep(15)
        if current_player:
            await bot.send_message(chat_id, "⏳ 15s left! Place final bids...")
        await asyncio.sleep(15)
        if current_player:
            await finalize_auction(chat_id)
    except asyncio.CancelledError:
        pass


# ===== Finalize Auction =====
async def finalize_auction(chat_id):
    global current_player, highest_bid, highest_bidder, sold_players, unsold_players, teams, auction_task

    if not current_player:
        return

    if highest_bidder:
        team = teams[f"Team {highest_bidder}"]
        team["spent"] += highest_bid
        team["players"].append((current_player, highest_bid))

        # Captain / Vice Captain
        if not team["captain"]:
            team["captain"] = current_player
        elif not team.get("vice"):
            team["vice"] = current_player

        sold_players[f"Team {highest_bidder}"] = {
            "captain": team["captain"],
            "vice": team.get("vice"),
            "players": team["players"]
        }

        await bot.send_message(chat_id, f"✅ SOLD! {current_player} bought by {highest_bidder} for {highest_bid} XP")
    else:
        unsold_players.append(current_player)
        await bot.send_message(chat_id, f"🚫 UNSOLD! {current_player}")

    current_player = None
    highest_bid = 0
    highest_bidder = None
    if auction_task:
        auction_task.cancel()
        auction_task = None
