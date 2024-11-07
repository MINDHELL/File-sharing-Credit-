from bot import Bot
from pyrogram import filters, Client
from config import *
from database.database import *
from helper_func import *
from datetime import datetime
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton 
from pyrogram.enums import ParseMode
import asyncio
import logging
import os
from io import StringIO


# Set up logging
logger = logging.getLogger(__name__)

# Function to delete a message after a specified delay
async def delete_message_after_delay(message: Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Failed to delete message: {e}")

@Client.on_message(filters.command('creditreport') & filters.private & filters.user(ADMINS))
async def generate_credit_report(client: Client, message: Message):
    #Generates a report of all users' credits and top 10 users based on remaining credits.
    try:
        # Fetch all users' credit data from the database
        users = await user_collection.find({}, {"_id": 1, "limit": 1}).to_list(length=None)
        
        # Sort users by remaining credits in descending order
        sorted_users = sorted(users, key=lambda x: x.get("limit", 0), reverse=True)
        top_10_users = sorted_users[:10]

        # Prepare text file data with each user's ID and remaining credits
        output = StringIO()
        output.write("User ID, Remaining Credits\n")
        for user in sorted_users:
            output.write(f"{user['_id']}, {user.get('limit', 0)}\n")

        # Save data to a .txt file
        file_path = "/tmp/user_credits_report.txt"
        with open(file_path, "w") as file:
            file.write(output.getvalue())
        
        # Send the report file to the admin
        await client.send_document(
            chat_id=message.chat.id,
            document=file_path,
            caption="📊 Here is the detailed credit report of all users, sorted by remaining credits."
        )

        # Prepare and send the summary of the top 10 users with highest credits in a table format
        top_10_summary = "🏆 **Top 10 Users by Credits** 🏆\n\n"
        top_10_summary += "┌─────┬────────────┬───────────┐\n"
        top_10_summary += "│ Rank │  User ID       │ Credits     │\n"
        top_10_summary += "├─────┼────────────┼───────────┤\n"
        
        for idx, user in enumerate(top_10_users, start=1):
            top_10_summary += f"│ {idx:^3} │ {user['_id']:^10} │ {user.get('limit', 0):^9} │\n"

        top_10_summary += "└─────┴────────────┴───────────┘"
        
        await message.reply_text(top_10_summary)

        # Cleanup: Delete the temporary file after sending
        os.remove(file_path)

    except Exception as e:
        logger.error(f"Error in generating credit report: {e}")
        await message.reply_text("❌ An error occurred while generating the credit report.")

"""
@Client.on_message(filters.command('creditreport') & filters.private & filters.user(ADMINS))
async def generate_credit_report(client: Client, message: Message):
    #Generates a report of all users' credits and top 10 users based on remaining credits.
    try:
        # Fetch all users' credit data from the database
        users = await user_collection.find({}, {"_id": 1, "limit": 1}).to_list(length=None)
        
        # Sort users by remaining credits in descending order to get the top 10
        sorted_users = sorted(users, key=lambda x: x.get("limit", 0), reverse=True)
        top_10_users = sorted_users[:10]

        # Prepare text file data with each user's ID and remaining credits
        output = StringIO()
        output.write("User ID, Remaining Credits\n")
        for user in users:
            output.write(f"{user['_id']}, {user.get('limit', 0)}\n")

        # Save data to a .txt file
        file_path = "/tmp/user_credits_report.txt"
        with open(file_path, "w") as file:
            file.write(output.getvalue())
        
        # Send the report file to the admin
        await client.send_document(
            chat_id=message.chat.id,
            document=file_path,
            caption="📊 Here is the detailed credit report of all users."
        )

        # Prepare and send the summary of the top 10 users with highest credits
        top_10_summary = "🏆 **Top 10 Users by Credits** 🏆\n\n"
        for idx, user in enumerate(top_10_users, start=1):
            top_10_summary += f"{idx}. User ID: {user['_id']}, Credits: {user.get('limit', 0)}\n"

        await message.reply_text(top_10_summary)

        # Cleanup: Delete the temporary file after sending
        os.remove(file_path)

    except Exception as e:
        logger.error(f"Error in generating credit report: {e}")
        await message.reply_text("❌ An error occurred while generating the credit report.")

"""



@Client.on_message(filters.command('givecredits') & filters.private)
async def give_credits(client: Client, message: Message):
    """Handles the /givecredits command for admins to give credits to a specific user."""
    admin_id = message.from_user.id

    # Check if the user is an admin
    if admin_id not in ADMINS:
        await message.reply_text("❌ You are not authorized to use this command.")
        return

    # Ensure the command has the correct format
    try:
        command_parts = message.text.split()
        if len(command_parts) != 3:
            await message.reply_text("❌ Invalid command format. Use: /givecredits <user_id> <credits>")
            return

        user_id = int(command_parts[1])
        credits_to_add = int(command_parts[2])

        # Find the user in the database
        user_data = await user_collection.find_one({"_id": user_id})
        if not user_data:
            await message.reply_text(f"❌ User with ID {user_id} not found.")
            return

        # Update the user's credit limit
        await user_collection.update_one(
            {"_id": user_id},
            {"$inc": {"limit": credits_to_add}}
        )

        await message.reply_text(f"✅ Successfully added {credits_to_add} credits to user {user_id}.")

    except ValueError:
        await message.reply_text("❌ Invalid user ID or credits value. Please enter valid numbers.")
    except Exception as e:
        logger.error(f"Error while giving credits: {e}")
        await message.reply_text("❌ An error occurred while processing your request. Please try again later.")


# Admin command to add credits to a user
@Client.on_message(filters.command('addcredits') & filters.private & filters.user(ADMINS))
async def add_credits(client: Client, message: Message):
    user_id = message.from_user.id

    if len(message.command) != 2:
        await message.reply_text("Usage: /addcredits credits")
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
        await message.reply_text("Usage: /givepr user_id credits premium_status")
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
        await message.reply_text("Invalid arguments. Ensure user_id and credits are integers.")
    except Exception as e:
        logger.error(f"Error in give_premium_status: {e}")
        await message.reply_text("An error occurred while assigning premium status.")

# User command to check their premium status and remaining credits
@Client.on_message(filters.command('profile') & filters.private)
async def check_premium_status(client: Client, message: Message):
    user_id = message.from_user.id

    # Retrieve user data from the database
    user = await user_collection.find_one({"_id": user_id})

    if user is None:
        await message.reply_text("You are not registered in our database. Please use /start to register.")
        return

    # Check if the user has premium status
    is_premium = user.get("is_premium", False)
    limit = user.get("limit", 0)

    if is_premium:
        # Get premium status information
        premium_status = user.get("premium_status", "Unknown")
        await message.reply_text(
            f"🏆 <b>Premium Status: {premium_status}</b>\n💳 <b>Credits: {limit}</b>",
            parse_mode=ParseMode.HTML
        )
    else:
        # Non-premium users' message
        await message.reply_text(
            f"You are not a premium user.\n<b>Credits:</b> {limit}\nBecome a Premium user: /plans",
            parse_mode=ParseMode.HTML
        )

    # Delete the user's command after a delay to keep the chat clean
    asyncio.create_task(delete_message_after_delay(message, AUTO_DELETE_DELAY))

# User command to check their current credit limit
@Client.on_message(filters.command('check') & filters.private)
async def check_command(client: Client, message: Message):
    user_id = message.from_user.id

    try:
        user = await get_user(user_id)
        user_limit = user.get("limit", START_COMMAND_LIMIT)
        await message.reply_text(f"💳 <b>Your current limit is {user_limit} credits.</b>", parse_mode=ParseMode.HTML)
        asyncio.create_task(delete_message_after_delay(message, AUTO_DELETE_DELAY))
    except Exception as e:
        logger.error(f"Error in check_command: {e}")
        error_message = await message.reply_text("An error occurred while checking your limit.")
        asyncio.create_task(delete_message_after_delay(error_message, AUTO_DELETE_DELAY))


@Client.on_message(filters.command('count') & filters.private)
async def token_stats(client: Client, message: Message):
    """Handles the /token_stats command for admins to view token verification statistics."""
    admin_id = message.from_user.id

    # Check if the user is an admin
    if admin_id not in ADMINS:  # Make sure ADMINS is a list of your admin user IDs
        await message.reply_text("❌ You are not authorized to use this command.")
        return

    try:
        # Get the total number of tokens verified
        total_token_count = await user_collection.count_documents({"token_use_count": {"$gt": 0}})

        # Get the total number of verifications across all users
        total_verifications = await user_collection.aggregate([
            {"$group": {"_id": None, "total_verifications": {"$sum": "$token_use_count"}}}
        ]).to_list(None)
        total_verifications_count = total_verifications[0]['total_verifications'] if total_verifications else 0

        # Get token verification data for the last 24 hours
        last_24_hours = datetime.now() - timedelta(hours=24)
        last_24_hours_data = await user_collection.count_documents({
            "last_token_use_time": {"$gte": last_24_hours}
        })

        # Get token verification data for today
        start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        day_data = await user_collection.count_documents({
            "last_token_use_time": {"$gte": start_of_day}
        })

        # Format the summary message for admins
        summary_message = (
            "📊 **Token Verification Stats** 📊\n\n"
            f"🔹 Total users who verified tokens: {total_token_count}\n"
            f"🔹 Total tokens verified: {total_verifications_count}\n"
            f"🔹 Tokens in last 24 hours: {last_24_hours_data}\n"
            f"🔹 Token verifications today: {day_data}\n"
        )

        # Send the summary message to the admin
        await message.reply_text(summary_message)

    except Exception as e:
        logger.error(f"Error fetching token statistics: {e}")
        await message.reply_text("An error occurred while fetching token statistics. Please try again later.")


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
        logger.error(f"Error occurred while sending UPI info: {e}")

# /help command to show available commands
@Client.on_message(filters.command('help') & filters.private)
async def help_command(client: Client, message: Message):
    help_text = """
📖 <b>Available Commands:</b>

/start - Start the bot and see welcome message.
/help - Show this help message.
/check - Check your current credit limit.
/profile - Check your premium status and remaining credits.
/batch - Create link for more than one posts.
/genlink - Create link for one post.
/stats - Check your bot uptime.
/users - View bot statistics (Admins only).
/broadcast - Broadcast any messages to bot users (Admins only).
/addcredits credits - Add credits to your account (Admins only).
/givecredits user_id credits - Give credits to a user (Admins only).
/givepr user_id credits premium_status - Give premium status to a user (Admins only).
/count - Show token usage statistics (Admins only).
/creditreport - give txt file and top 10 user (Admins only).
/plans - Show available premium plans.
/upi - Show UPI payment options.
"""
    await message.reply(help_text, parse_mode=ParseMode.HTML)

"""
# Handle callback queries for UPI payment info
@Client.on_callback_query(filters.regex('upi_info'))
async def handle_upi_info(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    await upi_info(client, callback_query.message)
"""
