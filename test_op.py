import os
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
db_name = os.getenv("MONGO_URI").split('/')[-1].split('?')[0] or 'company-prj'
client = MongoClient(MONGO_URI)
db = client[db_name]
online_requests = db['onlinerequests']

try:
    test_doc = {
        "patientName": "TEST_BOT",
        "patientContact": "1234567890",
        "date": "2026-03-27",
        "time": "14:00",
        "requestId": "REQ-TEST",
        "status": "Pending",
        "createdAt": datetime.now(),
        "updatedAt": datetime.now()
    }
    res = online_requests.insert_one(test_doc)
    print(f"Insert success: {res.inserted_id}")
    
    del_res = online_requests.delete_one({"_id": res.inserted_id})
    print(f"Delete success: {del_res.deleted_count}")
except Exception as e:
    print(f"Failure: {e}")
