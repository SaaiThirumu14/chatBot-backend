import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
db_name = os.getenv("MONGO_URI").split('/')[-1].split('?')[0] or 'company-prj'

client = MongoClient(MONGO_URI)
db = client[db_name]

print(f"--- DB: {db_name} ---")
colls = db.list_collection_names()
print(f"Total collections: {len(colls)}")
for c in colls:
    print(f" - {c}")
