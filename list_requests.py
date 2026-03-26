
import os
import json
from pymongo import MongoClient
from dotenv import load_dotenv
from bson import json_util

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client['company-prj']
requests = db['onlinerequests']

print(f"--- DB: company-prj, Collection: onlinerequests ---")
for doc in requests.find():
    # Use json_util for better formatting of ObjectId, datetime, etc.
    print(json.dumps(doc, indent=2, default=json_util.default))
