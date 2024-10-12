# database/database.py

from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URI, DB_NAME, START_COMMAND_LIMIT
from datetime import datetime, timedelta
import logging

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MongoDB Client
mongo_client = AsyncIOMotorClient(DB_URI)
db = mongo_client[DB_NAME]

# Collections
user_collection = db['user_collection']
token_collection = db['tokens']
verification_log_collection = db['verification_logs']

# Default user data structure
default_user = {
    "_id": None,  # User ID
    "limit": START_COMMAND_LIMIT,  # Starting credits
    "is_premium": False,  # Premium status
    "premium_status": None,  # e.g., Silver, Bronze, Gold
    "token_usage": [],  # List of timestamps when tokens were used to increase credits
    "verify_token": "",
    "verified_time": 0
}

async def log_verification(user_id):
    """Logs a verification event for a user."""
    await verification_log_collection.insert_one({
        "user_id": user_id,
        "timestamp": datetime.utcnow()
    })
    logger.info(f"Logged verification for user {user_id}")

async def get_verification_count(timeframe):
    """Counts verifications based on the specified timeframe."""
    current_time = datetime.utcnow()
    
    if timeframe == "24h":
        start_time = current_time - timedelta(hours=24)
    elif timeframe == "today":
        start_time = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    elif timeframe == "monthly":
        start_time = current_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        logger.warning(f"Invalid timeframe: {timeframe}")
        return 0  # Invalid timeframe
    
    count = await verification_log_collection.count_documents({
        "timestamp": {"$gte": start_time, "$lt": current_time}
    })
    
    logger.info(f"Verification count for {timeframe}: {count}")
    return count

async def cleanup_old_logs():
    """Cleans up verification logs older than 24 hours."""
    expiry_time = datetime.utcnow() - timedelta(hours=24)
    result = await verification_log_collection.delete_many({
        "timestamp": {"$lt": expiry_time}
    })
    logger.info(f"Cleaned up {result.deleted_count} old verification logs.")

async def get_previous_token(user_id):
    """Retrieves the previous verification token for a user."""
    user = await user_collection.find_one({"_id": user_id})
    token = user.get("verify_token") if user else None
    logger.debug(f"Retrieved previous token for user {user_id}: {token}")
    return token

async def set_previous_token(user_id, token):
    """Sets a new verification token for a user."""
    await user_collection.update_one(
        {"_id": user_id},
        {"$set": {"verify_token": token}},
        upsert=True
    )
    logger.info(f"Set new token for user {user_id}: {token}")

async def add_user(user_id):
    """Adds a new user to the database with default settings."""
    user = default_user.copy()
    user["_id"] = user_id
    await user_collection.insert_one(user)
    logger.info(f"Added new user with ID: {user_id}")

async def present_user(user_id):
    """Checks if a user exists in the database."""
    user = await user_collection.find_one({"_id": user_id})
    exists = user is not None
    logger.debug(f"User {user_id} exists: {exists}")
    return exists

async def full_userbase():
    """Retrieves all user IDs from the database."""
    user_docs = user_collection.find()
    user_ids = [doc['_id'] async for doc in user_docs]
    logger.info(f"Retrieved full user base with {len(user_ids)} users.")
    return user_ids

async def del_user(user_id: int):
    """Deletes a user from the database."""
    result = await user_collection.delete_one({'_id': user_id})
    if result.deleted_count:
        logger.info(f"Deleted user with ID: {user_id}")
    else:
        logger.warning(f"Attempted to delete non-existent user with ID: {user_id}")

async def get_user(user_id):
    """Retrieves user data, adding the user if they do not exist."""
    user = await user_collection.find_one({"_id": user_id})
    if user is None:
        await add_user(user_id)
        user = await user_collection.find_one({"_id": user_id})
    logger.debug(f"Retrieved user data for {user_id}: {user}")
    return user

async def update_user(user_id, update_data):
    """Updates user data with the provided fields."""
    await user_collection.update_one({"_id": user_id}, {"$set": update_data})
    logger.info(f"Updated user {user_id} with data: {update_data}")

async def increase_user_limit(user_id, credits):
    """Increases the user's credit limit by the specified amount."""
    await user_collection.update_one(
        {"_id": user_id},
        {"$inc": {"limit": credits}}
    )
    logger.info(f"Increased limit for user {user_id} by {credits} credits.")

async def set_premium_status(user_id, status, credits):
    """Sets the user's premium status and assigns credits based on the status."""
    await user_collection.update_one(
        {"_id": user_id},
        {
            "$set": {
                "is_premium": True,
                "premium_status": status,
                "limit": credits
            }
        },
        upsert=True
    )
    logger.info(f"Set premium status for user {user_id} to {status} with {credits} credits.")

async def can_increase_credits(user_id, credits, time_limit=24):
    """Checks if the user can increase their credits based on the time limit."""
    user = await get_user(user_id)
    token_usage = user.get("token_usage", [])
    
    # Remove timestamps older than time_limit hours
    cutoff_time = datetime.utcnow() - timedelta(hours=time_limit)
    recent_usage = [usage for usage in token_usage if usage >= cutoff_time]
    
    # Update the user's token_usage to only include recent_usage
    await user_collection.update_one(
        {"_id": user_id},
        {"$set": {"token_usage": recent_usage}}
    )
    
    usage_count = sum([credit for credit in recent_usage])
    
    if usage_count + credits > 20:
        logger.warning(f"User {user_id} cannot increase credits by {credits}. Current usage: {usage_count}")
        return False
    logger.info(f"User {user_id} can increase credits by {credits}. Current usage: {usage_count}")
    return True

async def log_token_usage(user_id, credits):
    """Logs the credit increase usage for rate limiting."""
    current_time = datetime.utcnow()
    await user_collection.update_one(
        {"_id": user_id},
        {
            "$push": {
                "token_usage": {
                    "$each": [credits],
                    "$slice": -100  # Keep the last 100 entries to prevent unbounded growth
                }
            }
        }
    )
    logger.info(f"Logged token usage for user {user_id}: {credits} credits.")

async def remove_premium_if_low(user_id):
    """Removes premium status if user's credits fall below 20."""
    user = await get_user(user_id)
    if user["is_premium"] and user["limit"] < 20:
        await user_collection.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "is_premium": False,
                    "premium_status": None
                }
            }
        )
        logger.info(f"Removed premium status from user {user_id} due to low credits.")
        return True
    return False
