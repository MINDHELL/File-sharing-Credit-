# https://t.me/Ultroid_Official/524

from bot import Bot
from pyrogram import filters, Client
from config import *
from database.database import *
from helper_func import *
from datetime import datetime
#from plugins.start import *
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
import asyncio
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Admin command to manually increase or decrease credits
@Client.on_message(filters.command("givecredits") & filters.user(ADMINS))
async def give_credits(client: Client, message: Message):
    try:
        _, user_id, credits = message.text.split()
        user_id = int(user_id)
        credits = int(credits)

        await increase_user_limit(user_id, credits)
        await message.reply(f"Gave {credits} credits to user {user_id}.")
    except Exception as e:
        await message.reply(f"Error: {e}")

# Admin command to add credits to a user
@Client.on_message(filters.command('addcredits') & filters.private & filters.user(ADMINS))
async def add_credits(client: Client, message: Message):
    user_id = message.from_user.id

    if len(message.command) != 2:
        await message.reply_text("Usage: /addcredits <credits>")
        return

    try:
        credits_to_add = int(message.command[1])
        
        if credits_to_add <= 0 or credits_to_add > 20:
            await message.reply_text("You can only add between 1 and 20 credits at a time.")
            return
        
        can_add = await can_increase_credits(user_id, credits_to_add)
        if not can_add:
            await message.reply_text("You've reached the credit increase limit for today (20 credits). Try again later.")
            return

        await increase_user_limit(user_id, credits_to_add)
        await log_token_usage(user_id, credits_to_add)
        await message.reply_text(f"✅ Successfully added {credits_to_add} credits to your account.")

    except ValueError:
        await message.reply_text("Invalid number of credits. Please enter a valid integer.")
    except Exception as e:
        logger.error(f"Error in add_credits: {e}")
        await message.reply_text("An error occurred while adding credits.")

# Admin command to assign premium status and credits to a user
@Client.on_message(filters.command('givepr') & filters.user(ADMINS))
async def give_premium_status(client: Client, message: Message):
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
        
        if credits != premium_credits[premium_status]:
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
    except Exception as e:
        logger.error(f"Error in give_premium_status: {e}")
        await message.reply_text("An error occurred while assigning premium status.")

# User command to check their premium status and remaining credits
@Client.on_message(filters.command('profile') & filters.private)
async def check_premium_status(client: Client, message: Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if user.get("is_premium", False):
        status = user.get("premium_status", "Unknown")
        limit = user.get("limit", 0)
        await message.reply_text(f"🏆 **Premium Status:** {status}\n💳 **Credits:** {limit}")
    else:
        await message.reply_text("You are not a premium user. \n**Credits:** {limit}" \nBecome Premium user /plans")
    
    asyncio.create_task(delete_message_after_delay(message, AUTO_DELETE_DELAY))

# User command to check their current credit limit
@Client.on_message(filters.command('check') & filters.private)
async def check_command(client: Client, message: Message):
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

# Admin command to display token usage statistics
@Client.on_message(filters.command('count') & filters.private)
async def count_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in ADMINS:
        await message.reply_text("You do not have permission to use this command.")
        return
    
    try:
        last_24h_count = await get_verification_count("24h")
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

# /plans command to show subscription plans
@Client.on_message(filters.command('plans') & filters.private)
async def show_plans(client: Client, message: Message):
    plans_text = """
🎁 <b>Available Subscription Plans:</b>

1. 50  Credit - Bronze Premium - 20₹
2. 100 Credit - Silver Premium - 35₹
3. 200 Credit - Gold   Premium - 50₹

To subscribe, click the "Pay via UPI" button below or use /upi cmd 
"""
    buttons = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Pay via UPI", callback_data="upi_info")],
         [InlineKeyboardButton("Contact Support", url=f"https://t.me/{OWNER}")]]
    )

    await message.reply(plans_text, reply_markup=buttons, parse_mode=ParseMode.HTML)

# /upi command to show payment QR and options
@Client.on_message(filters.command('upi') & filters.private)
async def upi_info(client: Client, message: Message):
    try:
        await client.send_photo(
            chat_id=message.chat.id,
            photo=PAYMENT_QR,
            caption=PAYMENT_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Contact Owner", url=f"https://t.me/{OWNER}")]]
            )
        )
    except Exception as e:
        await message.reply_text("Sorry, I couldn't send the UPI information. Please try again later.")
        print(f"Error occurred while sending UPI info: {e}")

# /help command to show available commands
@Client.on_message(filters.command('help') & filters.private)
async def help_command(client: Client, message: Message):
    help_text = """
📖 <b>Available Commands:</b>

/start - Start the bot and see welcome message.
/help - Show this help message.
/check - Check your current credit limit.
/profile - Check your premium status and remaining credits.
/batch - create link for more than one posts.
/genlink - create link for one post.
/stats - checking your bot uptime.
/users - view bot statistics (Admins only).
/broadcast - broadcast any messages to bot users (Admins only).
/addcredits <credits> - Add credits to your account (Admins only).
/givecredits <user_id> <credits> - Give credits to a user (Admins only).
/givepr <user_id> <credits> <premium_status> - Assign premium status to a user (Admins only).
/count - Show token usage statistics (Admins only).
/plans - View subscription plans.
/upi - Show UPI payment details.
    """
    await message.reply(help_text, parse_mode=ParseMode.HTML)
