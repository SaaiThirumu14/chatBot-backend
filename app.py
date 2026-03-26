from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import json
import re
import requests
import os
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Dict, Any
from pymongo import MongoClient
from bson.objectid import ObjectId

load_dotenv()

# 🔑 Gemini API Key
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Use gemini-1.5-flash for reliability or 2.0 if needed
model = genai.GenerativeModel("gemini-2.5-flash") # Reverting name as per snippet logic or staying same but 1.5 is standard, user had 2.5 which might be a typo but let's keep it simple

app = Flask(__name__)
CORS(app)

# -------------------------------
# MONGODB CONFIG
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client['company-prj'] # Database name from MONGO_URI
online_requests = db['onlinerequests'] # Mongoose pluralizes OnlineRequest
session_storage: Dict[str, List[Dict[str, Any]]] = {}

EXTRACTION_PROMPT = """
You are a Clinical Extraction Agent for MediCare AI.
Extract structured appointment data from the user's message and history.

Current Date: {current_date}

Return JSON ONLY with these fields:
- intent: ("book", "cancel", "show", "update", "unwanted", "unknown")
- name: (Patient name)
- phone: (Phone number, digits only)
- date: (YYYY-MM-DD or readable format)
- time: (HH:MM or readable format)
- appointment_id: (e.g. REQ-1001)

Context (History):
{history}

User Message: {message}

Return JSON only.
"""

RESPONSE_PROMPT = """
You are "MediCare AI Assistant", a professional and caring medical concierge.
Generate a natural, helpful response to the user based on the Action Result and the user's message.

Branding Guidelines:
- Professional, empathetic, and concise.
- Use Markdown for emphasis (e.g. **bold**, *italic*).
- If booking was successful, show the **Request ID** clearly in a separate line.
- If fields are missing for a booking (e.g. date or time), ask for them nicely.
- If the user is GREETING you or starting a conversation, you MUST respond exactly in this format:

"Hi! Welcome to the Doctor Clinic Assistant.
You can send a message for the following requests:
• Book an appointment Example: "Book appointment March 20 at 10:30 for Ravi Kumar"
• Cancel an appointment Example: "Cancel appointment REQ-1001"
• View your appointment details Example: "Show my appointment details" or "Show appointment REQ-1001"
• Update missing details Example: "My phone number is 9876543210" or "The appointment is at 4 pm"

Please type your request in a simple sentence and the system will process it for you."

Context:
- User Message: {message}
- Action Result: {action_result}
- Extracted Data: {extracted_data}
- Chat History: {history}

Return the final AI message only.
"""

# -------------------------------
# UTILS
# -------------------------------

def extract_json(text):
    try:
        # Strip potential markdown code blocks
        text = re.sub(r'```json\n?|\n?```', '', text).strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return None

def get_history_text(session_id: str) -> str:
    history = session_storage.get(session_id, [])
    # Convert list to history string
    text = ""
    for msg in history:
        role = "User" if msg.get("isUser") else "Assistant"
        text += f"{role}: {msg.get('text')}\n"
    return text

# -------------------------------
# DATABASE HELPERS (Logic from Express Controller)
# -------------------------------

def db_receive_appointment_request(data):
    name = data.get("name")
    phno = data.get("phno") or data.get("phone")
    date_str = data.get("date")
    time = data.get("time")

    if not all([name, phno, date_str, time]):
        return {"status": False, "message": "Please provide your name, phone, date, and time for appointment booking."}

    # Convert date_str to datetime object for Mongoose compatibility
    try:
        # The extraction prompt asks for YYYY-MM-DD
        booking_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        try:
            # Fallback to other common formats or just use as is if parsing fails
            # (though PyMongo needs a datetime object to store as BSON Date)
            from dateutil import parser
            booking_date = parser.parse(date_str)
        except (ValueError, ImportError):
            booking_date = date_str # Fallback to string if all else fails

    try:
        count = online_requests.count_documents({})
        request_id = f"REQ-{1000 + count + 1}"

        new_request = {
            "patientName": name,
            "patientContact": phno,
            "date": booking_date, 
            "time": time,
            "requestId": request_id,
            "status": "Pending",
            "createdAt": datetime.now(),
            "updatedAt": datetime.now()
        }

        result = online_requests.insert_one(new_request)
        
        return {
            "status": True,
            "message": "Request received successfully.",
            "requestId": str(result.inserted_id),
            "appid": request_id
        }
    except Exception as e:
        return {"status": False, "message": str(e)}

def db_delete_by_phone(id_param):
    if not id_param:
        return {"status": False, "message": "Request ID is required"}
    
    try:
        # Match by requestId as in Express controller
        res = online_requests.delete_many({"requestId": id_param, "status": "Pending"})
        return {
            "status": True,
            "message": "Deletion sequence completed across all clinical buffers.",
            "onlineRequestsDeleted": res.deleted_count
        }
    except Exception as e:
        return {"status": False, "message": str(e)}

def db_view_by_id(id_param):
    if not id_param:
        return {"status": False, "message": "Request ID is required"}
    
    try:
        cursor = online_requests.find({"requestId": id_param})
        results = []
        for doc in cursor:
            doc['_id'] = str(doc['_id'])
            if 'createdAt' in doc: doc['createdAt'] = str(doc['createdAt'])
            if 'updatedAt' in doc: doc['updatedAt'] = str(doc['updatedAt'])
            results.append(doc)
        return results
    except Exception as e:
        return {"status": False, "message": str(e)}

def db_update_by_id(id_param, updates_dict):
    if not id_param:
        return {"status": False, "message": "Request ID is required"}
    
    # Filter empty/none updates
    updates = {}
    for k, v in updates_dict.items():
        if v not in [None, "", "null", "undefined"]:
            updates[k] = v
            
    if not updates:
        return {"status": False, "message": "No valid fields to update"}

    try:
        updates['updatedAt'] = datetime.now()
        result = online_requests.find_one_and_update(
            {"requestId": id_param, "status": "Pending"},
            {"$set": updates},
            return_document=True
        )
        
        if not result:
            return {"status": False, "message": "No pending request found with this ID"}
        
        result['_id'] = str(result['_id'])
        if 'createdAt' in result: result['createdAt'] = str(result['createdAt'])
        if 'updatedAt' in result: result['updatedAt'] = str(result['updatedAt'])
        
        return result
    except Exception as e:
        return {"status": False, "message": str(e)}

# -------------------------------
# CHATBOT CONTROLLERS (Internal wrappers)
# -------------------------------

def call_book_appointment(data):
    missing = []
    if not data.get("name"): missing.append("name")
    if not (data.get("phone") or data.get("phno")): missing.append("phone number")
    if not data.get("date"): missing.append("date")
    if not data.get("time"): missing.append("time")

    if missing:
        return f"MISSING_FIELDS: {', '.join(missing)}"

    result = db_receive_appointment_request(data)
    if result.get("status"):
        return f"SUCCESS: Booking confirmed. Request ID is **{result.get('appid')}**."
    return f"ERROR: Booking failed - {result.get('message', 'Unknown error')}"

def call_cancel_appointment(data):
    aid = data.get("appointment_id")
    if not aid:
        return "MISSING_FIELDS: appointment ID"

    result = db_delete_by_phone(aid)
    if result.get("status"):
        deleted = result.get("onlineRequestsDeleted", 0)
        if deleted > 0:
            return f"SUCCESS: Appointment **{aid}** has been cancelled successfully."
        return f"ERROR: No matching pending appointment found for ID **{aid}**."
    return f"ERROR: Operation failed - {result.get('message')}"

def call_show_appointment(data):
    aid = data.get("appointment_id")
    if not aid:
        return "MISSING_FIELDS: appointment ID"

    result = db_view_by_id(aid)
    if isinstance(result, list):
        if not result:
            return f"NOT_FOUND: No record found for ID **{aid}**."
        
        record = result[0]
        details = (
            f"Patient: {record.get('patientName', 'N/A')}\n"
            f"Date: {record.get('date', 'N/A')}\n"
            f"Time: {record.get('time', 'N/A')}\n"
            f"Status: {record.get('status', 'N/A')}"
        )
        return f"SUCCESS: Found details for {aid}:\n{details}"
    return f"ERROR: {result.get('message')}"

def call_update_appointment(data):
    aid = data.get("appointment_id")
    if not aid:
        return "MISSING_FIELDS: appointment ID"

    payload = {}
    mapping = {"name": "patientName", "phone": "patientContact", "date": "date", "time": "time"}
    for ai_k, mod_k in mapping.items():
        if data.get(ai_k):
            payload[mod_k] = data[ai_k]

    if not payload:
        return "NO_UPDATES: No new information provided to update."

    result = db_update_by_id(aid, payload)
    if "status" in result and not result["status"]:
        return f"ERROR: {result.get('message')}"
    return f"SUCCESS: Appointment **{aid}** has been updated."

# -------------------------------
# AGENT LOGIC
# -------------------------------

def process_agent(session_id, user_message):
    history_text = get_history_text(session_id)
    curr_date = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Extraction
    extraction_prompt = EXTRACTION_PROMPT.format(
        current_date=curr_date,
        history=history_text, 
        message=user_message
    )
    try:
        r1 = model.generate_content(extraction_prompt)
        extracted = extract_json(r1.text) or {"intent": "unknown"}
    except Exception:
        extracted = {"intent": "unknown"}

    # 2. Action
    intent = extracted.get("intent")
    action_result = "NO_ACTION"

    if intent == "book":
        action_result = call_book_appointment(extracted)
    elif intent == "cancel":
        action_result = call_cancel_appointment(extracted)
    elif intent == "show":
        action_result = call_show_appointment(extracted)
    elif intent == "update":
        action_result = call_update_appointment(extracted)
    elif intent == "unwanted":
        action_result = "SECURITY: Access denied."
    elif intent == "unknown":
        action_result = "GREETING_OR_CHATTING"

    # 3. NLG
    response_prompt = RESPONSE_PROMPT.format(
        message=user_message,
        action_result=action_result,
        extracted_data=json.dumps(extracted),
        history=history_text
    )
    
    try:
        r2 = model.generate_content(response_prompt)
        final_reply = r2.text.strip()
    except Exception:
        final_reply = "I'm sorry, I'm having trouble responding. Please try again."

    # 4. History Update
    if session_id not in session_storage:
        session_storage[session_id] = []
    
    session_storage[session_id].append({"text": user_message, "isUser": True})
    session_storage[session_id].append({"text": final_reply, "isUser": False})
    
    # Prune history to last 10 turns
    if len(session_storage[session_id]) > 20:
        session_storage[session_id] = session_storage[session_id][-20:]

    return final_reply, extracted

# -------------------------------
# BOT ROUTES
# -------------------------------

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json or {}
    message = data.get("message")
    session_id = data.get("session_id", "default")

    if not message:
        return jsonify({"error": "No message"}), 400

    reply, extracted = process_agent(session_id, message)
    return jsonify({"reply": reply, "extracted": extracted})

@app.route("/reset", methods=["POST"])
def reset():
    session_id = (request.json or {}).get("session_id", "default")
    session_storage.pop(session_id, None)
    return jsonify({"status": "Reset"})

# -------------------------------
# N8N LEGACY ROUTES (Merged from Express)
# -------------------------------

@app.route("/api/n8n/receiver", methods=["POST"])
def n8n_receiver():
    data = request.json or {}
    result = db_receive_appointment_request(data)
    return jsonify(result), 201 if result.get("status") else 400

@app.route("/api/n8n/delete/<id>", methods=["DELETE"])
def n8n_delete(id):
    result = db_delete_by_phone(id)
    return jsonify(result), 200 if result.get("status") else 500

@app.route("/api/n8n/view/<id>", methods=["GET"])
def n8n_view(id):
    result = db_view_by_id(id)
    if isinstance(result, list):
        return jsonify(result), 200
    return jsonify(result), 500

@app.route("/api/n8n/update/<id>", methods=["PUT"])
def n8n_update(id):
    data = request.json or {}
    result = db_update_by_id(id, data)
    if "status" in result and not result["status"]:
        return jsonify(result), 404
    return jsonify(result), 200

if __name__ == "__main__":
    app.run(port=5001, debug=True)
