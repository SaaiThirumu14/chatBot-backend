import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import re
import requests
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Dict, Any
from pymongo import MongoClient
from bson.objectid import ObjectId

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client['company-prj'] # Database name from MONGO_URI
online_requests = db['onlinerequests'] # Mongoose pluralizes OnlineRequest

def db_receive_appointment_request(data):
    name = data.get("name")
    phno = data.get("phno") or data.get("phone")
    date = data.get("date")
    time = data.get("time")

    if not all([name, phno, date, time]):
        return {"status": False, "message": "Missing fields"}

    try:
        count = online_requests.count_documents({})
        request_id = f"REQ-{1000 + count + 1}"

        new_request = {
            "patientName": name,
            "patientContact": phno,
            "date": date,
            "time": time,
            "requestId": request_id,
            "status": "Pending",
            "createdAt": datetime.now(),
            "updatedAt": datetime.now()
        }

        result = online_requests.insert_one(new_request)
        return {
            "status": True,
            "appid": request_id
        }
    except Exception as e:
        print(f"DB ERROR: {e}")
        return {"status": False, "message": str(e)}

# SIMULATE THE EXTRACTION RESULT
extracted_from_user = {
    "intent": "book",
    "name": "raj",
    "phone": "7894561230",
    "date": "2026-03-27",
    "time": "14:00"
}

res = db_receive_appointment_request(extracted_from_user)
print(f"SIMULATION RESULT: {res}")
if not res.get("status"):
    print(f"ERROR: {res.get('message')}")
else:
    # CLEANUP if success
    online_requests.delete_one({"requestId": res.get("appid")})
    print("Cleanup successful")
