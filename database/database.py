
from pymongo import MongoClient
"""
import motor.motor_asyncio
from config import DB_URI, DB_NAME

dbclient = motor.motor_asyncio.AsyncIOMotorClient(DB_URI)
database = dbclient[DB_NAME]

user_data = database['users']

default_verify = {
    'is_verified': False,
    'verified_time': 0,
    'verify_token': "",
    'link': ""
}

client = MongoClient(DB_URI)
db = client[DB_NAME]
users = db["users"]

async def add_user(id):
    users.insert_one({"_id": id, "limit": 10, "is_verified": False, "verify_token": "", "verified_time": 0})

async def present_user(user_id: int):
    found = await user_data.find_one({'_id': user_id})
    return bool(found)

async def db_verify_status(user_id):
    user = await user_data.find_one({'_id': user_id})
    if user:
        return user.get('verify_status', default_verify)
    return default_verify

async def db_update_verify_status(user_id, verify):
    await user_data.update_one({'_id': user_id}, {'$set': {'verify_status': verify}})

async def full_userbase():
    user_docs = user_data.find()
    user_ids = [doc['_id'] async for doc in user_docs]
    return user_ids

async def del_user(user_id: int):
    await user_data.delete_one({'_id': user_id})
    return

async def update_user_limit(id, limit):
    users.update_one({"_id": id}, {"$set": {"limit": limit}})

async def get_user_limit(id):
    user = users.find_one({"_id": id})
    return user.get("limit", 0) if user else 0

async def get_verify_status(id):
    user = users.find_one({"_id": id})
    return user if user else {"is_verified": False, "verify_token": "", "verified_time": 0}

async def update_verify_status(id, is_verified=None, verify_token=None, verified_time=None):
    update_fields = {}
    if is_verified is not None:
        update_fields["is_verified"] = is_verified
    if verify_token is not None:
        update_fields["verify_token"] = verify_token
    if verified_time is not None:
        update_fields["verified_time"] = verified_time

    users.update_one({"_id": id}, {"$set": update_fields})


# db.py
"""
from motor.motor_asyncio import AsyncIOMotorClient
from config import DB_URI, DB_NAME

# Initialize MongoDB Client
mongo_client = AsyncIOMotorClient(DB_URI)
db = mongo_client[DB_NAME]

# Collections
users_collection = db["users"]  # Collection for users
tokens_collection = db["tokens"]  # Collection for token counts

# Default user data structure
default_user = {
    "_id": None,  # User ID
    "limit": 15,  # Starting credits
    "is_premium": False,  # Premium status
    "is_verified": False,
    "verify_token": "",
    "verified_time": 0
}

# Add a new user
async def add_user(user_id: int):
    user = default_user.copy()
    user["_id"] = user_id
    await users_collection.insert_one(user)

# Check if user exists
async def present_user(user_id: int) -> bool:
    user = await users_collection.find_one({'_id': user_id})
    return bool(user)

# Get user data
async def get_user_data(user_id: int):
    user = await users_collection.find_one({'_id': user_id})
    if not user:
        # If user doesn't exist, add them
        await add_user(user_id)
        user = await users_collection.find_one({'_id': user_id})
    return user

# Update user data
async def update_user_data(user_id: int, data: dict):
    await users_collection.update_one({'_id': user_id}, {'$set': data})

# Delete user
async def del_user(user_id: int):
    await users_collection.delete_one({'_id': user_id})

# Get all user IDs
async def full_userbase():
    user_docs = users_collection.find()
    user_ids = [doc['_id'] async for doc in user_docs]
    return user_ids

# Token-related functions
async def set_token(user_id: int, token: str):
    await update_user_data(user_id, {"verify_token": token})

async def get_token(user_id: int) -> str:
    user = await get_user_data(user_id)
    return user.get('verify_token', "")

async def increment_user_limit(user_id: int, amount: int = 10):
    await users_collection.update_one({'_id': user_id}, {'$inc': {'limit': amount}})

async def decrement_user_limit(user_id: int, amount: int = 1):
    await users_collection.update_one({'_id': user_id}, {'$inc': {'limit': -amount}})

async def get_user_limit(user_id: int) -> int:
    user = await get_user_data(user_id)
    return user.get('limit', 0)

async def set_premium(user_id: int, is_premium: bool):
    await update_user_data(user_id, {"is_premium": is_premium})

