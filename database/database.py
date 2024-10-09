import os
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient
import motor.motor_asyncio
from config import DB_URI as MONGO_URI, DB_NAME

DB_URI = os.environ.get("DATABASE_URL", "mongodb+srv://ultroidxTeam:ultroidxTeam@cluster0.gabxs6m.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
DB_NAME = os.environ.get("DATABASE_NAME", "Cluser10")

# Initialize MongoDB Client
mongo_client = AsyncIOMotorClient(DB_URI)
db = mongo_client[DB_NAME]

# Collections
user_data = db["users"]
tokens_collection = db["tokens"]

# Default user data structure
default_user = {
    "_id": None,  # User ID
    "limit": 15,  # Starting credits
    "is_premium": False,  # Premium status
    "is_verified": False,
    "verify_token": "",
    "verified_time": 0
}

# Ensure all functions use '_id' as the user identifier
async def add_user(user_id: int):
    user = default_user.copy()
    user["_id"] = user_id  # Use '_id' instead of 'user_id'
    try:
        await user_data.insert_one(user)
    except Exception as e:
        print(f"Error adding user: {e}")

async def present_user(user_id: int) -> bool:
    try:
        user = await user_data.find_one({'_id': user_id})  # Use '_id'
        return bool(user)
    except Exception as e:
        print(f"Error checking user presence: {e}")
        return False

async def get_user_data(user_id: int):
    try:
        user = await user_data.find_one({'_id': user_id})  # Use '_id'
        if not user:
            await add_user(user_id)
            user = await user_data.find_one({'_id': user_id})
        return user
    except Exception as e:
        print(f"Error getting user data: {e}")
        return None

async def update_user_data(user_id: int, data: dict):
    try:
        await user_data.update_one({"_id": user_id}, {"$set": data})
    except Exception as e:
        print(f"Error updating user data: {e}")

async def update_user_limit(id: int, limit: int):
    try:
        await user_data.update_one({"_id": id}, {"$set": {"limit": limit}})
    except Exception as e:
        print(f"Error updating user limit: {e}")

async def get_verify_status(id: int):
    try:
        user = await user_data.find_one({"_id": id})  # Use 'await' and '_id'
        return user if user else {"is_verified": False, "verify_token": "", "verified_time": 0}
    except Exception as e:
        print(f"Error getting verify status: {e}")
        return {"is_verified": False, "verify_token": "", "verified_time": 0}

async def update_verify_status(id: int, is_verified=None, verify_token=None, verified_time=None):
    update_fields = {}
    if is_verified is not None:
        update_fields["is_verified"] = is_verified
    if verify_token is not None:
        update_fields["verify_token"] = verify_token
    if verified_time is not None:
        update_fields["verified_time"] = verified_time

    try:
        await user_data.update_one({"_id": id}, {"$set": update_fields})
    except Exception as e:
        print(f"Error updating verify status: {e}")

async def del_user(user_id: int):
    try:
        await user_data.delete_one({'_id': user_id})
    except Exception as e:
        print(f"Error deleting user: {e}")

async def full_userbase():
    try:
        user_docs = user_data.find()
        user_ids = [doc['_id'] async for doc in user_docs]
        return user_ids
    except Exception as e:
        print(f"Error getting full userbase: {e}")
        return []

async def set_token(user_id: int, token: str):
    try:
        await update_user_data(user_id, {"verify_token": token})
    except Exception as e:
        print(f"Error setting token: {e}")

async def get_token(user_id: int) -> str:
    try:
        user = await get_user_data(user_id)
        return user.get('verify_token', "")
    except Exception as e:
        print(f"Error getting token: {e}")
        return ""

async def increment_user_limit(user_id: int, amount: int = 10):
    try:
        await user_data.update_one({'_id': user_id}, {'$inc': {'limit': amount}})
    except Exception as e:
        print(f"Error incrementing user limit: {e}")

async def decrement_user_limit(user_id: int, amount: int = 1):
    try:
        await user_data.update_one({'_id': user_id}, {'$inc': {'limit': -amount}})
    except Exception as e:
        print(f"Error decrementing user limit: {e}")

async def get_user_limit(user_id: int) -> int:
    try:
        user = await get_user_data(user_id)
        return user.get('limit', 0)
    except Exception as e:
        print(f"Error getting user limit: {e}")
        return 0

async def set_premium(user_id: int, is_premium: bool):
    try:
        await update_user_data(user_id, {"is_premium": is_premium})
    except Exception as e:
        print(f"Error setting premium status: {e}")

async def db_verify_status(user_id: int):
    try:
        user = await user_data.find_one({'_id': user_id})
        if user:
            return user.get('verify_status', default_verify)
        return default_verify
    except Exception as e:
        print(f"Error getting verify status: {e}")
        return default_verify

async def db_update_verify_status(user_id: int, verify):
    try:
        await user_data.update_one({'_id': user_id}, {'$set': {'verify_status': verify}})
    except Exception as e:
        print(f"Error updating verify status: {e}")
