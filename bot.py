import os
import asyncio
from pyrogram import Client, filters

API_ID = int(os.getenv("API_ID", "25021528"))
API_HASH = os.getenv("API_HASH", "ea73f0e2e8595b85030aa59a11b3ef3b")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8474302248:AAHv8ysTaoYi36tSqDgKJ-bI5yZ-sh7vd2U")

bot = Client("auction_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== Global State =====
current_creator = None
purse_amount = None
registered_players = {}  # player_name: xp
unsold_players = []
current_player = None
highest_bid = 0
highest_bidder = None
auction_task = None

# Teams structure: {team_name: {"captain": str, "vice": None, "players": [], "spent": 0, "purse": int}}
teams = {}
sold_players = {}


# ===== Helper: Check if user is admin =====
async def is_admin(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    member = await bot.get_chat_member(chat_id, user_id)
    return member.status in ["administrator", "creator"]


# ===== Set Purse =====
@bot.on_message(filters.command("set_purse"))
async def set_purse(client, message):
    global purse_amount, current_creator

    if not (message.from_user.id == current_creator or await is_admin(message)):
        return await message.reply("⚠️ Only creator/admin can set purse!")

    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply("Usage: /set_purse <amount>")

    purse_amount = int(message.command[1])
    current_creator = message.from_user.id
    await message.reply(f"💰 Purse set to {purse_amount} XP by {message.from_user.first_name}")


# ===== Register Player =====
@bot.on_message(filters.command("register"))
async def register_player(client, message):
    global registered_players, unsold_players

    if not (message.from_user.id == current_creator or await is_admin(message)):
        return await message.reply("⚠️ Only creator/admin can register players!")

    if len(message.command) < 3 or not message.command[2].isdigit():
        return await message.reply("Usage: /register <player_name> <xp (1-8)>")

    name = message.command[1]
    xp = int(message.command[2])
    registered_players[name] = xp
    unsold_players.append(name)
    await message.reply(f"✅ Registered player: {name} (XP: {xp})")


# ===== Create Team =====
@bot.on_message(filters.command("create_team"))
async def create_team(client, message):
    global teams

    if not (message.from_user.id == current_creator or await is_admin(message)):
        return await message.reply("⚠️ Only creator/admin can create teams!")

    if len(message.command) < 3:
        return await message.reply("Usage: /create_team <team_name> <@captain_username>")

    team_name = message.command[1]
    captain_username = message.command[2].lstrip("@")

    try:
        user = await client.get_users(captain_username)
    except:
        return await message.reply("⚠️ Invalid username")

    teams[team_name] = {"captain": user.first_name, "vice": None, "players": [], "spent": 0, "purse": purse_amount}
    await message.reply(f"👑 Team {team_name} created with captain {user.first_name}")


# ===== Start Auction (automatic next player) =====
@bot.on_message(filters.command("start_auction"))
async def start_auction(client, message):
    global current_player, highest_bid, highest_bidder, auction_task, current_creator

    if not unsold_players:
        return await message.reply("⚠️ No unsold players left!")

    current_player = unsold_players.pop(0)
    highest_bid = 0
    highest_bidder = None
    current_creator = message.from_user.id
    await message.reply(f"🏏 Auction started for **{current_player}**!\n💰 Current Bid: 0 XP")

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

    try:
        amount = int(message.command[1])
    except:
        return await message.reply("⚠️ Invalid amount.")

    # Check if sender is captain
    user_name = message.from_user.first_name
    team_name = None
    for t, info in teams.items():
        if info["captain"] == user_name:
            team_name = t
            break
    if not team_name:
        return await message.reply("⚠️ Only team captains can bid!")

    purse_left = teams[team_name]["purse"] - teams[team_name]["spent"]
    if amount <= highest_bid:
        return await message.reply(f"⚠️ Bid must be higher than {highest_bid} XP!")
    if amount > purse_left:
        return await message.reply(f"⚠️ Not enough purse! Available: {purse_left} XP")

    highest_bid = amount
    highest_bidder = team_name
    await message.reply(f"💸 {user_name} bid {highest_bid} XP for **{current_player}**")


# ===== End Auction =====
@bot.on_message(filters.command("end_auction"))
async def end_auction(client, message):
    if not (message.from_user.id == current_creator or await is_admin(message)):
        return await message.reply("⚠️ Only creator/admin can end auction!")

    await finalize_auction(message.chat.id)


# ===== Teams =====
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


# ===== Unsold Players =====
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
    global current_player, highest_bid, highest_bidder, sold_players, teams, auction_task

    if not current_player:
        return

    if highest_bidder:
        team = teams[highest_bidder]
        team["spent"] += highest_bid
        team["players"].append((current_player, highest_bid))

        # Vice captain auto assign
        if not team.get("vice") and len(team["players"]) >= 2:
            team["vice"] = current_player

        sold_players[highest_bidder] = {
            "captain": team["captain"],
            "vice": team.get("vice"),
            "players": team["players"]
        }

        await bot.send_message(chat_id, f"✅ SOLD! {current_player} bought by {team['captain']} for {highest_bid} XP")
    else:
        unsold_players.append(current_player)
        await bot.send_message(chat_id, f"🚫 UNSOLD! {current_player}")

    current_player = None
    highest_bid = 0
    highest_bidder = None
    if auction_task:
        auction_task.cancel()
        auction_task = None
