import os
from pymongo import MongoClient
from dotenv import load_dotenv
import traceback

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
print(f"Connecting to: {MONGO_URI}")

try:
    client = MongoClient(MONGO_URI)
    # Explicitly get the DB name from the URI or default to company-prj
    db_name = MONGO_URI.split('/')[-1].split('?')[0]
    if not db_name:
        db_name = 'company-prj'
    print(f"Database name extracted: {db_name}")
    db = client[db_name]
    
    # Try an operation
    collections = db.list_collection_names()
    print(f"Collections: {collections}")
    
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
