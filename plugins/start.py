import asyncio
import base64
import logging
import os
import random
import re
import string
import time
import uuid
from datetime import datetime

import pytz
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated

from bot import Bot  # Ensure 'bot.py' correctly initializes 'Bot' as a Pyrogram Client
from config import (
    ADMINS,
    BAN,
    FORCE_MSG,
    START_MSG,
    CUSTOM_CAPTION,
    IS_VERIFY,
    VERIFY_EXPIRE,
    SHORTLINK_API,
    SHORTLINK_URL,
    DISABLE_CHANNEL_BUTTON,
    PROTECT_CONTENT,
    TUT_VID,
    OWNER_ID,
    DB_NAME,
    DB_URI,
)
from helper_func import (
    subscribed,
    encode,
    decode,
    get_messages,
    get_shortlink,
    get_verify_status,
    update_verify_status,
    get_exp_time,
)
from database.database import *
from shortzy import Shortzy

# Constants (Ensure these are defined appropriately)
CLIENT_USERNAME = "MMS_leak_robot"  # Replace with your bot's username
AUTO_DELETE_DELAY = 60  # Time in seconds after which messages are deleted
LIMIT_INCREASE_AMOUNT = 10  # Amount to increase the user's limit upon verification
START_COMMAND_LIMIT = 15

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Timezone Configuration
tz = pytz.timezone("Asia/Kolkata")

# MongoDB Clients
mongo_client = AsyncIOMotorClient(DB_URI)
db = mongo_client[DB_NAME]
database = mongo_client[DB_NAME]
tokens_collection = db["tokens"]  # Collection for token counts
user_data = db["users"]  # Collection for users =--> user_data = db["users"]   # Collection for user data
premium_user_data = db["pusers"] # Collection for premium users
user_data = database['users']


#___--------

# Initialize Shortzy for URL shortening
shortzy = Shortzy(api_key=SHORTLINK_API, base_site=SHORTLINK_URL)

def generate_token(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
    
# Helper Functions for Token Counting
async def increment_token_count(user_id: int):
    """Increments the total token count for today and the user's token count."""
    today = datetime.now(tz).strftime("%Y-%m-%d")
    # Increment total tokens for today
    await tokens_collection.update_one(
        {"date": today},
        {"$inc": {"today_tokens": 1, "total_tokens": 1}},
        upsert=True,
    )
    # Increment user's token count
    await tokens_collection.update_one(
        {"user_id": user_id},
        {"$inc": {"user_tokens": 1}},
        upsert=True,
    )


async def get_today_token_count():
    """Retrieves today's total token count."""
    today = datetime.now(tz).strftime("%Y-%m-%d")
    doc = await tokens_collection.find_one({"date": today})
    return doc["today_tokens"] if doc and "today_tokens" in doc else 0


async def get_total_token_count():
    """Retrieves the total token count."""
    pipeline = [
        {
            "$group": {
                "_id": None,
                "total": {"$sum": "$total_tokens"},
            }
        }
    ]
    result = await tokens_collection.aggregate(pipeline).to_list(length=1)
    return result[0]["total"] if result else 0


async def get_user_token_count(user_id: int):
    """Retrieves the token count for a specific user."""
    doc = await tokens_collection.find_one({"user_id": user_id})
    return doc["user_tokens"] if doc and "user_tokens" in doc else 0


# MongoDB Helper Functions for Premium Users
async def add_premium_user(user_id, duration_in_days):
    """Adds a premium user with an expiry time."""
    expiry_time = time.time() + duration_in_days * 86400  # Convert days to seconds
    await user_data.update_one(
        {"user_id": user_id},
        {"$set": {"is_premium": True, "expiry_time": expiry_time}},
        upsert=True,
    )


async def remove_premium_user(user_id):
    """Removes premium status from a user."""
    await user_data.update_one(
        {"user_id": user_id},
        {"$set": {"is_premium": False, "expiry_time": None}},
    )


async def get_user_subscription(user_id):
    """Fetches a user's subscription status and expiry time."""
    user = await user_data.find_one({"user_id": user_id})
    if user:
        return user.get("is_premium", False), user.get("expiry_time", None)
    return False, None


async def is_premium_user(user_id):
    """Checks if a user is currently a premium user."""
    is_premium, expiry_time = await get_user_subscription(user_id)
    if is_premium and expiry_time > time.time():
        return True
    return False


# Short Link Generator
async def generate_short_link(link: str):
    """Generates a shortened link using Shortzy."""
    try:
        shortened_link = await shortzy.convert(link)
        return shortened_link
    except Exception as e:
        logger.error(f"Error generating short link: {str(e)}")
        return link  # Fallback to original link if shortening fails


# Message Deletion Helper
async def delete_message_after_delay(message: Message, delay: int):
    """Deletes a message after a specified delay."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Failed to delete message: {e}")


# Command Handlers

@Bot.on_message(filters.command("check") & filters.private)
async def check_command(client: Client, message: Message):
    """Handles the /check command to display the user's current limit."""
    user_id = message.from_user.id
    try:
        user_limit = await get_user_limit(user_id)  # Ensure this function is defined
        limit_message = await message.reply_text(f"Your current limit is {user_limit}.")
        asyncio.create_task(delete_message_after_delay(limit_message, AUTO_DELETE_DELAY))
    except Exception as e:
        logger.error(f"Error in check_command: {e}")
        error_message = await message.reply_text("An error occurred while checking your limit.")
        asyncio.create_task(delete_message_after_delay(error_message, AUTO_DELETE_DELAY))


@Bot.on_message(filters.command("count") & filters.private)
async def count_command(client: Client, message: Message):
    """Handles the /count command to display token usage statistics."""
    try:
        # Get the count of users who used a token in the last 24 hours
        last_24h_count = await get_verification_count("24h")  # Ensure this function is defined

        # Get the count of users who used a token today
        today_count = await get_verification_count("today")  # Ensure this function is defined

        count_message = (
            f"📊 **Token Usage Statistics:**\n\n"
            f"• **Last 24 Hours:** {last_24h_count} users\n"
            f"• **Today's Token Users:** {today_count} users"
        )

        response_message = await message.reply_text(count_message, parse_mode=ParseMode.MARKDOWN)
        asyncio.create_task(delete_message_after_delay(response_message, AUTO_DELETE_DELAY))

    except Exception as e:
        logger.error(f"Error in count_command: {e}")
        error_message = await message.reply_text("An error occurred while retrieving count data.")
        asyncio.create_task(delete_message_after_delay(error_message, AUTO_DELETE_DELAY))

"""
@Bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    # Handles the /start command with token verification and user registration.
    user_id = message.from_user.id
    user = message.from_user

    # Check if the user is the owner
    if user_id == OWNER_ID:
        await message.reply("👑 You are the owner! Welcome back.")
        return

    # Register the user if not already present
    if not await present_user(user_id):
        try:
            await add_user(user_id)
            logger.info(f"Registered new user: {user_id}")
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")
            await message.reply("An error occurred during registration. Please try again later.")
            return

    # Retrieve user data
    user_data = await user_data.find_one({"user_id": user_id})
    if not user_data:
        logger.error(f"User data not found for user_id: {user_id}")
        await message.reply("An error occurred. Please try again later.")
        return

    user_limit = user_data.get("limit", START_COMMAND_LIMIT)
    previous_token = user_data.get("previous_token")

    premium_status = await is_premium_user(user_id)
    verify_status = await get_verify_status(user_id)  # Ensure this function is defined

    # Generate a new token if not present
    if not previous_token:
        previous_token = str(uuid.uuid4())
        await user_data.update_one(
            {"user_id": user_id},
            {"$set": {"previous_token": previous_token}},
            upsert=True,
        )
        logger.info(f"Generated new token for user {user_id}: {previous_token}")

    # Generate the verification link
    verification_link = f"https://t.me/{CLIENT_USERNAME}?start=verify_{previous_token}"
    shortened_link = await generate_short_link(verification_link)

    # Check if the user is providing a verification token
    if len(message.text.split()) > 1 and "verify_" in message.text:
        provided_token = message.text.split("verify_", 1)[1]
        if provided_token == previous_token:
            # Verification successful, increase limit
            new_limit = user_limit + LIMIT_INCREASE_AMOUNT
            await update_user_limit(user_id, new_limit)  # Ensure this function is defined
            await log_verification(user_id)  # Ensure this function is defined
            await increment_token_count(user_id)
            confirmation_message = await message.reply_text(
                "✅ Your limit has been successfully increased by 10! Use /check to view your credits."
            )
            asyncio.create_task(delete_message_after_delay(confirmation_message, AUTO_DELETE_DELAY))
            return
        else:
            error_message = await message.reply_text("❌ Invalid verification token. Please try again.")
            asyncio.create_task(delete_message_after_delay(error_message, AUTO_DELETE_DELAY))
            return

    # If the user is not premium and the limit is reached, prompt to increase limit
    if not premium_status and user_limit <= 0:
        limit_message = (
            "🔒 **Your limit has been reached.**\n"
            "Use /check to view your credits.\n\n"
            "👉 **Increase your limit by verifying: [Click Here]({})**".format(shortened_link)
        )
        buttons = [
            [
                InlineKeyboardButton(
                    text="📈 Increase LIMIT",
                    url=shortened_link
                ),
                InlineKeyboardButton(
                    text="🔄 Try Again",
                    url=f"https://t.me/{CLIENT_USERNAME}?start=default"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎥 Verification Tutorial",
                    url=TUT_VID
                )
            ]
        ]

        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply(
            text=limit_message,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
            quote=True,
            parse_mode=ParseMode.MARKDOWN
        )
        asyncio.create_task(delete_message_after_delay(message, AUTO_DELETE_DELAY))
        return

    # Deduct 1 from the user's limit only if not premium
    if not premium_status:
        await update_user_limit(user_id, user_limit - 1)  # Ensure this function is defined

    # Handle the rest of the start command logic
    text = message.text
    if len(text.split()) > 1 and (verify_status["is_verified"] or premium_status):
        try:
            base64_string = text.split(" ", 1)[1]
            decoded_string = await decode(base64_string)
            arguments = decoded_string.split("-")

            ids = []
            if len(arguments) == 3:
                start = int(int(arguments[1]) / abs(YOUR_CHANNEL_ID))  # Replace YOUR_CHANNEL_ID accordingly
                end = int(int(arguments[2]) / abs(YOUR_CHANNEL_ID))
                if start <= end:
                    ids = list(range(start, end + 1))
                else:
                    ids = list(range(start, end - 1, -1))
            elif len(arguments) == 2:
                single_id = int(int(arguments[1]) / abs(YOUR_CHANNEL_ID))
                ids = [single_id]
            else:
                logger.error("Invalid number of arguments in decoded string.")
                return

            temp_msg = await message.reply("⏳ Please wait while processing your request...")
            try:
                messages = await get_messages(client, ids)  # Ensure this function is defined
            except Exception as e:
                await message.reply_text("❌ Something went wrong while fetching messages!")
                logger.error(f"Error getting messages: {e}")
                return

            await temp_msg.delete()

            for msg in messages:
                if msg.document:
                    caption = CUSTOM_CAPTION.format(
                        previouscaption=msg.caption.html if msg.caption else "",
                        filename=msg.document.file_name
                    )
                else:
                    caption = msg.caption.html if msg.caption else ""

                reply_markup = msg.reply_markup if not DISABLE_CHANNEL_BUTTON else None

                try:
                    sent_message = await msg.copy(
                        chat_id=user_id,
                        caption=caption,
                        parse_mode="html",
                        reply_markup=reply_markup,
                        protect_content=PROTECT_CONTENT
                    )
                    asyncio.create_task(delete_message_after_delay(sent_message, AUTO_DELETE_DELAY))
                    await asyncio.sleep(0.5)
                except FloodWait as e:
                    logger.warning(f"FloodWait encountered. Sleeping for {e.x} seconds.")
                    await asyncio.sleep(e.x)
                    sent_message = await msg.copy(
                        chat_id=user_id,
                        caption=caption,
                        parse_mode="html",
                        reply_markup=reply_markup,
                        protect_content=PROTECT_CONTENT
                    )
                    asyncio.create_task(delete_message_after_delay(sent_message, AUTO_DELETE_DELAY))
            return
        except Exception as e:
            logger.error(f"Error in processing /start command: {e}")
            await message.reply_text("❌ An error occurred while processing your request.")
            return
    else:
        # Send welcome message with buttons
        reply_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("😊 About Me", callback_data="about"),
                    InlineKeyboardButton("🔒 Close", callback_data="close")
                ]
            ]
        )
        welcome_text = (
            f"👋 Hello, {user.first_name}!\n\n"
            f"• **User ID:** `{user_id}`\n"
            f"• **Username:** @{user.username if user.username else 'N/A'}"
        )
        welcome_message = await message.reply_text(
            text=welcome_text,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
            quote=True,
            parse_mode=ParseMode.MARKDOWN
        )
        asyncio.create_task(delete_message_after_delay(welcome_message, AUTO_DELETE_DELAY))
        return
"""

async def retrieve_files_for_premium(client, message):
    # Your logic to retrieve files directly from the channel for premium users
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
        

@Client.on_message(filters.command('start') & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    id = message.from_user.id
    UBAN = BAN  # Owner's ID

    # Check if the user is the owner (UBAN)
    if user_id == UBAN:
        await message.reply("You are the U-BAN! Additional actions can be added here.")
        return

    # Register the user if not present
    if not await present_user(user_id):
        try:
            await add_user(user_id)
            logger.info(f"User {user_id} added to the database.")
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")
            await message.reply("An error occurred while registering you. Please try again later.")
            return

    # Retrieve or initialize user data
    user_data = await user_data.find_one({"user_id": user_id})

    # Ensure user_data is not None before accessing fields
    if not user_data:
        # Insert new user data if not present
        await user_data.insert_one({
            "user_id": user_id,
            "limit": START_COMMAND_LIMIT,
            "previous_token": None,
            "is_premium": False,
            "is_verified": False
        })
        user_data = await user_data.find_one({"user_id": user_id})  # Re-fetch the inserted data

    # Now safely access user data fields
    user_limit = user_data.get("limit", START_COMMAND_LIMIT)
    previous_token = user_data.get("previous_token")
    is_premium = user_data.get("is_premium", False)
    

    premium_status = await is_premium_user(user_id)  # Check if user is premium
    verify_status = await get_verify_status(user_id)  # Ensure this function is defined

    is_premium = user_data.get("is_premium", False)

    # Generate a new token if not present
    if not previous_token:
        previous_token = str(uuid.uuid4())
        await user_data.update_one(
            {"user_id": user_id},
            {"$set": {"previous_token": previous_token}},
            upsert=True
        )
        logger.info(f"Generated new token for user {user_id}.")

    # Retrieve user data
    user_data = await user_data.find_one({"_id": user_id})
    user_limit = user_data.get("limit", START_COMMAND_LIMIT)
    previous_token = user_data.get("previous_token")


    # Generate the verification link
    verification_link = f"https://t.me/{client.username}?start=verify_{previous_token}"
    shortened_link = await get_shortlink(SHORTLINK_URL, SHORTLINK_API, verification_link)

    # Premium users have unlimited access
    if is_premium:
        # Premium users bypass the limit and token verification
        premium_message = await message.reply("✅ You are a premium user with unlimited access.", quote=True)
        asyncio.create_task(delete_message_after_delay(premium_message, AUTO_DELETE_DELAY))

        # Directly retrieve the file from the channel or proceed with premium functionality
        await retrieve_files_for_premium(client, message)
        return
        
    # Check if the user is providing a verification token
    if len(message.text) > 7 and "verify_" in message.text:
        provided_token = message.text.split("verify_", 1)[1]
        if provided_token == previous_token:
            # Verification successful, increase limit by 10
            await update_user_limit(user_id, user_limit + LIMIT_INCREASE_AMOUNT)
            await log_verification(user_id)
            confirmation_message = await message.reply_text("✅ Your limit has been successfully increased by 10! , use /check cmd check your credits")
            asyncio.create_task(delete_message_after_delay(confirmation_message, AUTO_DELETE_DELAY))
            return
        else:
            error_message = await message.reply_text("Invalid verification token. Please try again.")
            asyncio.create_task(delete_message_after_delay(error_message, AUTO_DELETE_DELAY))
            return
            

    # If the limit is reached, prompt the user to use the verification link
    if user_limit <= 0:
        limit_message = "Your limit has been reached , use /check cmd check your credits. Use the following link to increase your limit "
        buttons = []

        try:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text='Increase LIMIT',
                        url=shortened_link
                    )
                ]
            )
        except IndexError:
            logger.error("IndexError: message.command[1] is missing or invalid")

        # Ensure message.command has at least 2 elements before accessing message.command[1]
        try:
            try_again_button = InlineKeyboardButton(
                'Try Again',
                url=f"https://t.me/{client.username}?start=default"
            )
            buttons.append([try_again_button])
        except IndexError:
            logger.error("IndexError: message.command[1] is missing or invalid")
            buttons.append(
                [
                    InlineKeyboardButton('Try Again', url=f"https://t.me/{client.username}?start=default")
                ]
            )

        buttons.append(
            [
                InlineKeyboardButton('Verification Tutorial', url=TUT_VID)
            ]
        )
        
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply(limit_message, reply_markup=reply_markup, protect_content=False, quote=True)
        asyncio.create_task(delete_message_after_delay(message, AUTO_DELETE_DELAY))
        return

    # Deduct 1 from the user's limit and continue with the normal start command process
    await update_user_limit(user_id, user_limit - 1)

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

# Callback Query Handler for Token Count

@Bot.on_callback_query(filters.regex(r"^check_tokens$"))
async def check_tokens_callback(client: Client, callback_query: CallbackQuery):
    """Handles callback queries for checking token statistics."""
    user_id = callback_query.from_user.id
    is_admin = user_id in ADMINS

    try:
        # Fetch token counts
        today_tokens = await get_today_token_count()
        total_tokens = await get_total_token_count()
        user_tokens = await get_user_token_count(user_id)

        if is_admin:
            # For admins, display more detailed stats
            users = await full_userbase()  # Ensure this function is defined
            user_token_details = ""
            user_token_counts = {}
            for uid in users:
                try:
                    token_count = await get_user_token_count(uid)
                    user_token_counts[uid] = token_count
                except Exception as e:
                    logger.error(f"Error fetching token count for user {uid}: {e}")
                    user_token_counts[uid] = 0  # Default to 0 if there's an error

            # Sort users based on token counts
            sorted_users = sorted(
                user_token_counts,
                key=lambda uid: user_token_counts[uid],
                reverse=True
            )[:10]  # Top 10 users

            for user in sorted_users:
                tokens = user_token_counts[user]
                user_token_details += f"• **User ID:** `{user}` - **Tokens:** `{tokens}`\n"

            response = (
                f"📈 **🔹 Admin Token Statistics 🔹**\n\n"
                f"• **Today's Token Count:** `{today_tokens}`\n"
                f"• **Total Token Count:** `{total_tokens}`\n\n"
                f"• **Top Users:**\n{user_token_details}"
            )
        else:
            # For regular users
            response = (
                f"📊 **Your Token Statistics** 📊\n\n"
                f"• **Today's Token Count:** `{today_tokens}`\n"
                f"• **Total Token Count:** `{total_tokens}`\n"
                f"• **Your Token Count:** `{user_tokens}`"
            )

        await callback_query.answer()
        await callback_query.message.edit_text(
            text=response,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔒 Close", callback_data="close")]]
            )
        )
    except Exception as e:
        logger.error(f"Error in check_tokens_callback: {e}")
        await callback_query.answer("❌ An error occurred while fetching token statistics.", show_alert=True)


# Additional Command Handlers

@Bot.on_message(filters.command("users") & filters.private & filters.user(ADMINS))
async def get_users(client: Client, message: Message):
    """Admin command to get the total number of users."""
    try:
        wait_msg = await client.send_message(chat_id=message.chat.id, text="⏳ Fetching user data...")
        users = await full_userbase()  # Ensure this function is defined
        await wait_msg.edit_text(f"📋 **Total Users:** `{len(users)}`")
    except Exception as e:
        logger.error(f"Error in get_users: {e}")
        await message.reply_text("❌ An error occurred while fetching user data.")


@Bot.on_message(filters.private & filters.command("broadcast") & filters.user(ADMINS))
async def broadcast_message(client: Client, message: Message):
    """Admin command to broadcast a message to all users."""
    if message.reply_to_message:
        try:
            users = await full_userbase()  # Ensure this function is defined
            broadcast_msg = message.reply_to_message
            total = len(users)
            successful = 0
            blocked = 0
            deleted = 0
            unsuccessful = 0

            pls_wait = await message.reply("📢 Broadcasting message... Please wait.")
            for chat_id in users:
                try:
                    await broadcast_msg.copy(chat_id)
                    successful += 1
                except FloodWait as e:
                    logger.warning(f"FloodWait: Sleeping for {e.x} seconds.")
                    await asyncio.sleep(e.x)
                    await broadcast_msg.copy(chat_id)
                    successful += 1
                except UserIsBlocked:
                    await del_user(chat_id)  # Ensure this function is defined
                    blocked += 1
                except InputUserDeactivated:
                    await del_user(chat_id)
                    deleted += 1
                except Exception as e:
                    logger.error(f"Failed to send message to {chat_id}: {e}")
                    unsuccessful += 1

            status = (
                f"📣 **Broadcast Completed** 📣\n\n"
                f"• **Total Users:** `{total}`\n"
                f"• **Successful:** `{successful}`\n"
                f"• **Blocked Users:** `{blocked}`\n"
                f"• **Deleted Accounts:** `{deleted}`\n"
                f"• **Unsuccessful:** `{unsuccessful}`"
            )
            await pls_wait.edit(status)
        except Exception as e:
            logger.error(f"Error in broadcast_message: {e}")
            await message.reply_text("❌ An error occurred during broadcasting.")
    else:
        error_message = (
            "⚠️ **Broadcast Error:**\n"
            "Please reply to the message you want to broadcast."
        )
        await message.reply_text(error_message)


@Bot.on_message(filters.command("tokencount") & filters.private)
async def token_count_command(client: Client, message: Message):
    """Handles the /tokencount command to display token statistics."""
    user_id = message.from_user.id
    is_admin = user_id in ADMINS

    try:
        # Fetch token counts
        today_tokens = await get_today_token_count()
        total_tokens = await get_total_token_count()
        user_tokens = await get_user_token_count(user_id)

        if is_admin:
            # For admins, display more detailed stats
            users = await full_userbase()  # Ensure this function is defined
            user_token_details = ""
            user_token_counts = {}
            for uid in users:
                try:
                    token_count = await get_user_token_count(uid)
                    user_token_counts[uid] = token_count
                except Exception as e:
                    logger.error(f"Error fetching token count for user {uid}: {e}")
                    user_token_counts[uid] = 0  # Default to 0 if there's an error

            # Sort users based on token counts
            sorted_users = sorted(
                user_token_counts,
                key=lambda uid: user_token_counts[uid],
                reverse=True
            )[:10]  # Top 10 users

            for user in sorted_users:
                tokens = user_token_counts[user]
                user_token_details += f"• **User ID:** `{user}` - **Tokens:** `{tokens}`\n"

            response = (
                f"📈 **🔹 Admin Token Statistics 🔹**\n\n"
                f"• **Today's Token Count:** `{today_tokens}`\n"
                f"• **Total Token Count:** `{total_tokens}`\n\n"
                f"• **Top Users:**\n{user_token_details}"
            )
        else:
            # For regular users
            response = (
                f"📊 **Your Token Statistics** 📊\n\n"
                f"• **Today's Token Count:** `{today_tokens}`\n"
                f"• **Total Token Count:** `{total_tokens}`\n"
                f"• **Your Token Count:** `{user_tokens}`"
            )

        await message.reply_text(
            text=response,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔒 Close", callback_data="close")]]
            )
        )
    except Exception as e:
        logger.error(f"Error in token_count_command: {e}")
        await message.reply_text("❌ An error occurred while fetching token statistics.")



@Bot.on_message(filters.command('start') & filters.private)
async def not_joined(client: Client, message: Message):
    buttons = [
        [
            InlineKeyboardButton(text="Join Channel", url=client.invitelink),
            #InlineKeyboardButton(text="Join Channel", url=client.invitelink2),
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

# Credits (Optional: You can remove or modify this section as needed)
"""
💡 **Credits:**
- **Bot Developed by:** @phdlust
- **GitHub:** [sahiildesai07](https://github.com/sahiildesai07)
- **Telegram:** [ultroidxTeam](https://t.me/ultroidxTeam)
- **YouTube:** [PhdLust](https://www.youtube.com/@PhdLust)
"""

"""
# Run the Bot
if __name__ == "__main__":
    logger.info("Bot is starting...")
    Bot.run()
"""
