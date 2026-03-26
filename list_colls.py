import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
# Extract DB name from URI
db_name = os.getenv("MONGO_URI").split('/')[-1].split('?')[0] or 'company-prj'

client = MongoClient(MONGO_URI)
db = client[db_name]

print(f"DATABASE: {db_name}")
for coll in db.list_collection_names():
    count = db[coll].count_documents({})
    print(f"Collection: {coll} | Count: {count}")
