# https://t.me/Ultroid_Official/524
"""
# https://t.me/Ultroid_Official/524

from bot import Bot
from pyrogram import filters
from config import *
from datetime import datetime
from plugins.start import *
from pyrogram.types import Message, CallbackQuery
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import time

# Add /addpr command for admins to add premium subscription
@Bot.on_message(filters.private & filters.command('addpr') & filters.user(ADMINS))
async def add_premium(bot: Bot, message: Message):  # Changed `client: Client` to match `Bot`
    if message.from_user.id not in ADMINS:  # Fix: check if user is in ADMINS
        return await message.reply("You don't have permission to add premium users.")

    try:
        command_parts = message.text.split()
        if len(command_parts) < 3:  # Check if enough arguments are provided
            return await message.reply("Usage: /addpr <user_id> <duration_in_days>")

        target_user_id = int(command_parts[1])
        duration_in_days = int(command_parts[2])
        await add_premium_user(target_user_id, duration_in_days)
        await message.reply(f"User {target_user_id} added to premium for {duration_in_days} days.")
    except Exception as e:
        await message.reply(f"Error: {str(e)}")

# Add /removepr command for admins to remove premium subscription
@Bot.on_message(filters.private & filters.command('removepr') & filters.user(ADMINS))
async def remove_premium(bot: Bot, message: Message):  # Changed `client: Client` to match `Bot`
    if message.from_user.id not in ADMINS:  # Fix: check if user is in ADMINS
        return await message.reply("You don't have permission to remove premium users.")

    try:
        command_parts = message.text.split()
        if len(command_parts) < 2:  # Check if enough arguments are provided
            return await message.reply("Usage: /removepr <user_id>")

        target_user_id = int(command_parts[1])
        await remove_premium_user(target_user_id)
        await message.reply(f"User {target_user_id} removed from premium.")
    except Exception as e:
        await message.reply(f"Error: {str(e)}")

# /myplan command for user subscription status
@Bot.on_message(filters.command('myplan') & filters.private)
async def my_plan(bot: Bot, message: Message):
    is_premium, expiry_time = await get_user_subscription(message.from_user.id)
    
    if is_premium:
        time_left = expiry_time - time.time()
        days_left = int(time_left / 86400)
        response_text = f"✅ Your premium subscription is active. Time left: {days_left} days."
        
        buttons = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Upgrade Plan", callback_data="show_plans")],
             [InlineKeyboardButton("Contact Support", url=f"https://t.me/{OWNER}")]]
        )
    else:
        response_text = "❌ You are not a premium user."
        
        buttons = InlineKeyboardMarkup(
            [[InlineKeyboardButton("View Plans", callback_data="show_plans")],
             [InlineKeyboardButton("Contact Support", url=f"https://t.me/{OWNER}")]]
        )

    await message.reply(response_text, reply_markup=buttons)

# /plans command to show subscription plans
@Bot.on_message(filters.command('plans') & filters.private)
async def show_plans(bot: Bot, message: Message):
    plans_text = """
<b>Available Subscription Plans:</b>

1. 7 Days Premium  - 20₹
2. 15 Days Premium - 35₹
3. 30 Days Premium - 50₹
4. 90 Days Premium - 100₹

🎁 <b>Premium Features:</b>
- No need for verification
- Direct access to files
- Ad-free experience

To subscribe, click the "Pay via UPI" button below.
"""
    buttons = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Pay via UPI", callback_data="upi_info")],
         [InlineKeyboardButton("Contact Support", url=f"https://t.me/{OWNER}")]]
    )

    await message.reply(plans_text, reply_markup=buttons, parse_mode=ParseMode.HTML)

# /upi command to show payment QR and options
@Bot.on_message(filters.command('upi') & filters.private)
async def upi_info(bot: Bot, message: Message):
    await bot.send_photo(
        chat_id=message.chat.id,
        photo=PAYMENT_QR,
        caption=PAYMENT_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Contact Owner", url=f"https://t.me/{OWNER}")]]
        )
    )


"""
