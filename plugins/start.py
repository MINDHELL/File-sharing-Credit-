import asyncio
import base64
import logging
import os
import random
import string
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated
from config import (
    API_ID, API_HASH, BOT_TOKEN, ADMIN_IDS,
    SHORTLINK_API, SHORTLINK_URL,
    AUTO_DELETE_DELAY, LIMIT_INCREASE_AMOUNT,
    START_COMMAND_LIMIT, TUT_VID
)
from helper_func import decode, get_messages, get_shortlink
from database.database import (
    get_user, increase_user_limit, can_increase_credits, 
    set_premium_status, get_token_usage, log_token_usage,
    verify_token, remove_premium_if_low, log_verification
)
import uuid

# Initialize the bot
Bot = Client(
    "PremiumBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Shortzy for URL shortening
shortzy = Shortzy(api_key=SHORTLINK_API, base_site=SHORTLINK_URL)


MAX_TOKEN_USES_PER_DAY = 2  # Maximum times a user can use the token in 24 hours
CREDIT_INCREMENT = 10       # The number of credits to increase per token usage
AUTO_DELETE_DELAY = 100      # Delay to auto-delete messages
ADMIN_IDS = [6695586027]

def generate_token(length=10):
    """Generates a random alphanumeric token."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

async def get_shortlink(url, api, link):
    """Generates a shortened URL using Shortzy."""
    try:
        shortened_link = await shortzy.convert(link)
        return shortened_link
    except Exception as e:
        logger.error(f"Error generating short link: {str(e)}")
        return link  # Fallback to original link if shortening fails

async def delete_message_after_delay(message: Message, delay: int):
    """Deletes a message after a specified delay."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
        logger.debug(f"Deleted message with ID: {message.message_id}")
    except Exception as e:
        logger.error(f"Failed to delete message: {e}")

@Bot.on_message(filters.command('givepr') & filters.user(ADMIN_IDS))
async def give_premium_status(client: Client, message: Message):
    """Admin command to assign premium status and credits to a user."""
    if len(message.command) != 4:
        await message.reply_text("Usage: /givepr <user_id> <credits> <premium_status>")
        return
    
    try:
        user_id = int(message.command[1])
        credits = int(message.command[2])
        premium_status = message.command[3].capitalize()
        
        if premium_status not in ['Bronze', 'Silver', 'Gold']:
            await message.reply_text("Invalid premium status. Choose from Bronze, Silver, Gold.")
            return
        
        # Define credit amounts for each premium status
        premium_credits = {
            'Bronze': 50,
            'Silver': 100,
            'Gold': 200
        }
        
        if credits not in premium_credits.values():
            await message.reply_text("Invalid credit amount for the specified premium status.")
            return
        
        await set_premium_status(user_id, premium_status, credits)
        await message.reply_text(f"Assigned {premium_status} status with {credits} credits to user {user_id}.")
        
        # Notify the user if they are online
        try:
            await client.send_message(
                chat_id=user_id,
                text=f"You have been granted {premium_status} status with {credits} credits by an admin."
            )
            logger.info(f"Notified user {user_id} about premium status assignment.")
        except Exception as e:
            logger.warning(f"Could not notify user {user_id}: {e}")
        
    except ValueError:
        await message.reply_text("Invalid arguments. Ensure <user_id> and <credits> are integers.")
        return
    except Exception as e:
        logger.error(f"Error in give_premium_status: {e}")
        await message.reply_text("An error occurred while assigning premium status.")

@Bot.on_message(filters.command('checkpr') & filters.private)
async def check_premium_status(client: Client, message: Message):
    """User command to check their premium status and remaining credits."""
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if user["is_premium"]:
        status = user.get("premium_status", "Unknown")
        limit = user.get("limit", 0)
        await message.reply_text(f"🏆 **Premium Status:** {status}\n💳 **Credits:** {limit}")
    else:
        await message.reply_text("You are not a premium user.")
    
    # Optionally delete the message after a delay
    asyncio.create_task(delete_message_after_delay(message, AUTO_DELETE_DELAY))

@Bot.on_message(filters.command('addcredits') & filters.private)
async def add_credits(client: Client, message: Message):
    """User command to add credits using tokens, limited to 20 credits per 24 hours."""
    user_id = message.from_user.id
    
    if len(message.command) != 2:
        await message.reply_text("Usage: /addcredits <credits>")
        return
    
    try:
        credits_to_add = int(message.command[1])
        
        if credits_to_add <= 0:
            await message.reply_text("Credits to add must be a positive integer.")
            return
        
        if credits_to_add > 20:
            await message.reply_text("You can only add up to 20 credits at a time.")
            return
        
        # Check if the user can increase their credits within the last 24 hours
        can_add = await can_increase_credits(user_id, credits_to_add)
        
        if not can_add:
            await message.reply_text("You've reached the credit increase limit for today (20 credits). Try again later.")
            return
        
        # Proceed to add credits
        await increase_user_limit(user_id, credits_to_add)
        await log_token_usage(user_id, credits_to_add)
        await message.reply_text(f"✅ Successfully added {credits_to_add} credits to your account.")
        
    except ValueError:
        await message.reply_text("Invalid number of credits. Please enter a valid integer.")
        return
    except Exception as e:
        logger.error(f"Error in add_credits: {e}")
        await message.reply_text("An error occurred while adding credits.")

@Bot.on_message(filters.command('check') & filters.private)
async def check_command(client: Client, message: Message):
    """User command to check their current credit limit."""
    user_id = message.from_user.id

    try:
        user = await get_user(user_id)
        user_limit = user.get("limit", START_COMMAND_LIMIT)
        await message.reply_text(f"💳 **Your current limit is {user_limit} credits.**")
        asyncio.create_task(delete_message_after_delay(message, AUTO_DELETE_DELAY))
    except Exception as e:
        logger.error(f"Error in check_command: {e}")
        error_message = await message.reply_text("An error occurred while checking your limit.")
        asyncio.create_task(delete_message_after_delay(error_message, AUTO_DELETE_DELAY))

@Bot.on_message(filters.command('count') & filters.private)
async def count_command(client: Client, message: Message):
    """Admin command to display token usage statistics."""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.reply_text("You do not have permission to use this command.")
        return
    
    try:
        # Get the count of verifications in the last 24 hours
        last_24h_count = await get_verification_count("24h")

        # Get the count of verifications today
        today_count = await get_verification_count("today")

        count_message = (
            f"📊 **Token Usage Statistics:**\n\n"
            f"• **Last 24 Hours:** {last_24h_count} verifications\n"
            f"• **Today's Verifications:** {today_count} verifications"
        )

        response_message = await message.reply_text(count_message, parse_mode=ParseMode.MARKDOWN)
        asyncio.create_task(delete_message_after_delay(response_message, AUTO_DELETE_DELAY))

    except Exception as e:
        logger.error(f"Error in count_command: {e}")
        error_message = await message.reply_text("An error occurred while retrieving count data.")
        asyncio.create_task(delete_message_after_delay(error_message, AUTO_DELETE_DELAY))

@Bot.on_message(filters.command('start') & filters.private)
async def start_command(client: Client, message: Message):
    """Handles the /start command for user interactions."""
    user_id = message.from_user.id
    text = message.text

    # Ensure user exists in the database
    if not await present_user(user_id):
        try:
            await add_user(user_id)
            logger.info(f"User {user_id} added to the database.")
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")
            await message.reply_text("An error occurred while registering you. Please try again later.")
            return

    # Retrieve user data
    user = await get_user(user_id)
    user_limit = user.get("limit", START_COMMAND_LIMIT)
    previous_token = user.get("verify_token", "")
    is_premium = user.get("is_premium", False)

    # Generate a new token only if previous_token is not available
    if not previous_token:
        previous_token = str(uuid.uuid4())
        await set_previous_token(user_id, previous_token)
        logger.info(f"Generated new token for user {user_id}.")

    # Generate the verification link
    verification_link = f"https://t.me/{client.username}?start=verify_{previous_token}"
    shortened_link = await get_shortlink(SHORTLINK_URL, SHORTLINK_API, verification_link)

    if "verify_" in text:
        provided_token = text.split("verify_", 1)[1]
        previous_token = user_data.get("previous_token")
        token_use_count = user_data.get("token_use_count", 0)
        last_token_use_time = user_data.get("last_token_use_time", datetime.min)
        current_time = datetime.now()

        # Check if the provided token matches the stored token
        if provided_token == previous_token:
            # Calculate the time difference since the last token usage
            time_diff = current_time - last_token_use_time

            # Reset the token use count if 24 hours have passed since the first token use
            if time_diff > timedelta(hours=24):
                token_use_count = 0  # Reset the count after 24 hours

            # Check if the user has exceeded the max token use limit within 24 hours
            if token_use_count >= MAX_TOKEN_USES_PER_DAY:
                error_message = await message.reply_text(
                    f"❌ You have already used your verification token {MAX_TOKEN_USES_PER_DAY} times in the past 24 hours. Please try again later or purchase premium for unlimited access."
                )
                asyncio.create_task(delete_message_after_delay(error_message, AUTO_DELETE_DELAY))
                return

            # Verification successful, increase limit by 10 credits
            await increase_user_limit(user_id, CREDIT_INCREMENT)
            await log_verification(user_id)

            # Update token use count and last token use time in the database
            token_use_count += 1
            await users_collection.update_one(
                {"user_id": user_id},
                {"$set": {
                    "token_use_count": token_use_count,
                    "last_token_use_time": current_time
                }}
            )

            # Inform the user of successful credit increase
            confirmation_message = await message.reply_text(
                f"✅ Your limit has been successfully increased by {CREDIT_INCREMENT} credits! Use /check to view your current limit."
            )
            asyncio.create_task(delete_message_after_delay(confirmation_message, AUTO_DELETE_DELAY))
            return
        else:
            error_message = await message.reply_text("❌ Invalid verification token. Please try again.")
            asyncio.create_task(delete_message_after_delay(error_message, AUTO_DELETE_DELAY))
            return

    # If the limit is reached, prompt the user to use the verification link
    if user_limit <= 0:
        limit_message = (
            "⚠️ **Your credit limit has been reached.**\n"
            "Use the following link to increase your limit by 30 credits (limited to two times in 24 hours):"
        )
        buttons = [
            [InlineKeyboardButton(text='Increase LIMIT', url=shortened_link)],
            [InlineKeyboardButton('Verification Tutorial', url=TUT_VID)]
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply(limit_message, reply_markup=reply_markup, protect_content=False, quote=True)
        asyncio.create_task(delete_message_after_delay(message, AUTO_DELETE_DELAY))
        return

    # Deduct 1 from the user's limit and proceed
    await increase_user_limit(user_id, -1)
    logger.info(f"Deducted 1 credit from user {user_id}. New limit: {user_limit -1}")
	
    if is_premium and user_limit - 1 < 20:
        # Remove premium status and notify the user
        await users_collection.update_one({"user_id": user_id}, {
            "$set": {"premium_status": "normal", "is_premium": False}})
        logger.info(f"Removed premium status for user {user_id} due to low credits.")
        await message.reply("Your premium status has been removed as your credits dropped below 20.")
	    
    text = message.text
    if len(text) > 7:
        try:
            base64_string = text.split(" ", 1)[1]
        except IndexError:
            return
        
        string = await decode(base64_string)
        argument = string.split("-")
        
        if len(argument) == 3:
            try:
                start = int(int(argument[1]) / abs(client.db_channel.id))
                end = int(int(argument[2]) / abs(client.db_channel.id))
            except Exception as e:
                logger.error(f"Error parsing arguments: {e}")
                return
            
            if start <= end:
                ids = range(start, end + 1)
            else:
                ids = list(range(start, end - 1, -1))
        elif len(argument) == 2:
            try:
                ids = [int(int(argument[1]) / abs(client.db_channel.id))]
            except Exception as e:
                logger.error(f"Error parsing arguments: {e}")
                return
        
        temp_msg = await message.reply("Please wait...")
        try:
            messages = await get_messages(client, ids)
        except Exception as e:
            await message.reply_text("Something went wrong..!")
            logger.error(f"Error getting messages: {e}")
            return
        
        await temp_msg.delete()

        for msg in messages:
            caption = CUSTOM_CAPTION.format(previouscaption="" if not msg.caption else msg.caption.html,
                                            filename=msg.document.file_name) if bool(CUSTOM_CAPTION) & bool(msg.document) else "" if not msg.caption else msg.caption.html

            reply_markup = msg.reply_markup if not DISABLE_CHANNEL_BUTTON else None

            try:
                sent_message = await msg.copy(
                    chat_id=message.from_user.id,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    protect_content=PROTECT_CONTENT
                )
                asyncio.create_task(delete_message_after_delay(sent_message, AUTO_DELETE_DELAY))
                await asyncio.sleep(0.5)
            except FloodWait as e:
                await asyncio.sleep(e.x)
                sent_message = await msg.copy(
                    chat_id=message.from_user.id,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    protect_content=PROTECT_CONTENT
                )
                asyncio.create_task(delete_message_after_delay(sent_message, AUTO_DELETE_DELAY))
            except Exception as e:
                logger.error(f"Error copying message: {e}")
                pass
        return
    else:
        reply_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("😊 About Me", callback_data="about"),
                    InlineKeyboardButton("🔒 Close", callback_data="close")
                ]
            ]
        )
        welcome_message = await message.reply_text(
            text=START_MSG.format(
                first=message.from_user.first_name,
                last=message.from_user.last_name,
                username=None if not message.from_user.username else '@' + message.from_user.username,
                mention=message.from_user.mention,
                id=message.from_user.id
            ),
            reply_markup=reply_markup,
            disable_web_page_preview=True,
            quote=True
        )
        asyncio.create_task(delete_message_after_delay(welcome_message, AUTO_DELETE_DELAY))	
        return

# Utility function to delete a message after a delay
async def delete_message_after_delay(message: Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await message.delete()
        logger.info(f"Deleted message from user {message.from_user.id} after {delay} seconds.")
    except Exception as e:
        logger.error(f"Error deleting message: {e}")


# Increase or decrease user credits
async def increase_user_limit(user_id, increment):
    user_data = await users_collection.find_one({"user_id": user_id})
    if not user_data:
        logger.warning(f"User {user_id} not found in the database.")
        return

    new_limit = user_data.get("credits", 0) + increment
    if new_limit < 0:
        new_limit = 0

    await users_collection.update_one({"user_id": user_id}, {"$set": {"credits": new_limit}})

    logger.info(f"User {user_id}'s credit limit updated to {new_limit}.")

# Admin command to give premium status and credits
@app.on_message(filters.command("givepr") & filters.user(ADMIN_IDS))
async def give_premium_status(client: Client, message: Message):
    try:
        _, user_id, credits, premium_status = message.text.split()
        user_id = int(user_id)
        credits = int(credits)

        if premium_status not in PREMIUM_TIERS:
            await message.reply("Invalid premium status. Choose from: bronze, silver, gold.")
            return

        user_data = await users_collection.find_one({"user_id": user_id})
        if not user_data:
            user_data = {"user_id": user_id, "credits": 0, "is_premium": False, "premium_status": "normal"}

        user_data["credits"] = credits
        user_data["is_premium"] = True
        user_data["premium_status"] = premium_status

        await users_collection.update_one({"user_id": user_id}, {"$set": user_data}, upsert=True)
        await message.reply(f"User {user_id} is now a {premium_status} member with {credits} credits!")
    except Exception as e:
        await message.reply(f"Error: {e}")


# Command for users to check their premium status and remaining credits
@app.on_message(filters.command("checkpr"))
async def check_premium(client: Client, message: Message):
    user_id = message.from_user.id
    user_data = await users_collection.find_one({"user_id": user_id})

    if not user_data:
        await message.reply("You are not registered in the system.")
        return

    credits = user_data.get("credits", 0)
    premium_status = user_data.get("premium_status", "normal")

    await message.reply(f"You have {credits} credits and your premium status is {premium_status}.")


# Admin command to manually increase or decrease credits
@app.on_message(filters.command("givecredits") & filters.user(ADMIN_IDS))
async def give_credits(client: Client, message: Message):
    try:
        _, user_id, credits = message.text.split()
        user_id = int(user_id)
        credits = int(credits)

        await increase_user_limit(user_id, credits)
        await message.reply(f"Gave {credits} credits to user {user_id}.")
    except Exception as e:
        await message.reply(f"Error: {e}")


# User command to add 20 credits every 24 hours (normal users only)
@app.on_message(filters.command("addcredits"))
async def add_credits(client: Client, message: Message):
    user_id = message.from_user.id
    user_data = await users_collection.find_one({"user_id": user_id})

    if not user_data:
        user_data = {"user_id": user_id, "credits": 0, "is_premium": False, "premium_status": "normal"}

    last_added_time = user_data.get("last_added_time")
    current_time = datetime.now()

    if last_added_time:
        time_diff = current_time - last_added_time
        if time_diff < timedelta(hours=24):
            await message.reply("You can only add credits once every 24 hours.")
            return

    user_data["credits"] += CREDIT_LIMIT
    user_data["last_added_time"] = current_time

    # Update premium status
    new_status = check_premium_status(user_data)
    user_data["premium_status"] = new_status
    user_data["is_premium"] = new_status != "normal"

    await users_collection.update_one({"user_id": user_id}, {"$set": user_data}, upsert=True)
    await message.reply(f"{CREDIT_LIMIT} credits added! You now have {user_data['credits']} credits.")


# Function to check premium status
def check_premium_status(user_data):
    credits = user_data.get("credits", 0)
    if credits >= PREMIUM_TIERS.get('gold', 0):
        return "gold"
    elif credits >= PREMIUM_TIERS.get('silver', 0):
        return "silver"
    elif credits >= PREMIUM_TIERS.get('bronze', 0):
        return "bronze"
    return "normal"


# Function to auto-remove premium if credits are too low
async def auto_remove_premium(user_id):
    user_data = await users_collection.find_one({"user_id": user_id})
    if user_data.get("is_premium", False) and user_data.get("credits", 0) < 20:
        # Remove premium status
        user_data["is_premium"] = False
        user_data["premium_status"] = "normal"
        await users_collection.update_one({"user_id": user_id}, {"$set": user_data})
        logger.info(f"Removed premium status for user {user_id}.")
        return True
    return False



#=========================================================================================##

WAIT_MSG = """"<b>Processing ...</b>"""

REPLY_ERROR = """<code>Use this command as a replay to any telegram message with out any spaces.</code>"""

#=====================================================================================##

    
    
@Bot.on_message(filters.command('start') & filters.private)
async def not_joined(client: Client, message: Message):
    buttons = [
        [
            InlineKeyboardButton(text="Join Channel", url=client.invitelink),
            InlineKeyboardButton(text="Join Channel", url=client.invitelink2),
        ],
        [
            InlineKeyboardButton(text="Join Channel", url=client.invitelink3),
            #InlineKeyboardButton(text="Join Channel", url=client.invitelink4),
        ]
    ]
    try:
        buttons.append(
            [
                InlineKeyboardButton(
                    text = 'Try Again',
                    url = f"https://t.me/{client.username}?start={message.command[1]}"
                )
            ]
        )
    except IndexError:
        pass

    await message.reply(
        text = FORCE_MSG.format(
                first = message.from_user.first_name,
                last = message.from_user.last_name,
                username = None if not message.from_user.username else '@' + message.from_user.username,
                mention = message.from_user.mention,
                id = message.from_user.id
            ),
        reply_markup = InlineKeyboardMarkup(buttons),
        quote = True,
        disable_web_page_preview = True
    )



@Bot.on_message(filters.command('users') & filters.private & filters.user(ADMINS))
async def get_users(client: Bot, message: Message):
    msg = await client.send_message(chat_id=message.chat.id, text=WAIT_MSG)
    users = await full_userbase()
    await msg.edit(f"{len(users)} users are using this bot")

@Bot.on_message(filters.private & filters.command('broadcast') & filters.user(ADMINS))
async def send_text(client: Bot, message: Message):
    if message.reply_to_message:
        query = await full_userbase()
        broadcast_msg = message.reply_to_message
        total = 0
        successful = 0
        blocked = 0
        deleted = 0
        unsuccessful = 0
        
        pls_wait = await message.reply("<i>Broadcasting Message.. This will Take Some Time</i>")
        for chat_id in query:
            try:
                await broadcast_msg.copy(chat_id)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except UserIsBlocked:
                await del_user(chat_id)
                blocked += 1
            except InputUserDeactivated:
                await del_user(chat_id)
                deleted += 1
            except:
                unsuccessful += 1
                pass
            total += 1
        
        status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""
        
        return await pls_wait.edit(status)

    else:
        msg = await message.reply(REPLY_ERROR)
        await asyncio.sleep(8)
        await msg.delete()



