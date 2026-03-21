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

load_dotenv()

# 🔑 Gemini API Key
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Use gemini-1.5-flash for reliability or 2.0 if needed
model = genai.GenerativeModel("gemini-2.5-flash")

app = Flask(__name__)
CORS(app)

# -------------------------------
# CONFIG
# -------------------------------
BASE_URL = os.getenv("CLINICAL_API_URL", "http://localhost:5000/api/n8n")

# In-memory chat history (Global for demo, use DB for production)
session_storage: Dict[str, List[Dict[str, Any]]] = {}

# -------------------------------
# SYSTEM PROMPTS
# -------------------------------

EXTRACTION_PROMPT = """
You are a Clinical Extraction Agent for MediCare AI.
Extract structured appointment data from the user's message and history.

Current Date: {current_date}

Return JSON ONLY with these fields:
- intent: ("book", "cancel", "show", "update", "unwanted", "unknown")
- name: (Patient name)
- phone: (Phone number, digits only)
- date: (YYYY-MM-DD)
- time: (HH:MM)
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
• Cancel an appointment Example: "Cancel appointment EQ1001"
• View your appointment details Example: "Show my appointment details" or "Show appointment EQ1001"
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
# CONTROLLERS
# -------------------------------

def call_book_appointment(data):
    missing = []
    if not data.get("name"): missing.append("name")
    if not data.get("phone"): missing.append("phone number")
    if not data.get("date"): missing.append("date")
    if not data.get("time"): missing.append("time")

    if missing:
        return f"MISSING_FIELDS: {', '.join(missing)}"

    payload = {
        "name": data["name"],
        "phno": data["phone"],
        "date": data["date"],
        "time": data["time"]
    }

    try:
        res = requests.post(f"{BASE_URL}/receiver", json=payload, timeout=5)
        result = res.json()
        if result.get("status"):
            return f"SUCCESS: Booking confirmed. Request ID is **{result.get('appid')}**."
        return f"ERROR: Backend rejected booking - {result.get('message', 'Unknown error')}"
    except Exception as e:
        return f"ERROR: Backend failed - {str(e)}"

def call_cancel_appointment(data):
    aid = data.get("appointment_id")
    if not aid:
        return "MISSING_FIELDS: appointment ID"

    try:
        res = requests.delete(f"{BASE_URL}/delete/{aid}", timeout=5)
        result = res.json()
        deleted = result.get("onlineRequestsDeleted", 0)
        if deleted > 0:
            return f"SUCCESS: Appointment **{aid}** has been cancelled successfully."
        return f"ERROR: No matching pending appointment found for ID **{aid}**."
    except Exception as e:
        return f"ERROR: Connection failure - {str(e)}"

def call_show_appointment(data):
    aid = data.get("appointment_id")
    if not aid:
        return "MISSING_FIELDS: appointment ID"

    try:
        res = requests.get(f"{BASE_URL}/view/{aid}", timeout=5)
        result = res.json()
        if not result:
            return f"NOT_FOUND: No record found for ID **{aid}**."
        
        record = result[0] if isinstance(result, list) and len(result) > 0 else result
        details = (
            f"Patient: {record.get('patientName', 'N/A')}\n"
            f"Date: {record.get('date', 'N/A')}\n"
            f"Time: {record.get('time', 'N/A')}\n"
            f"Status: {record.get('status', 'N/A')}"
        )
        return f"SUCCESS: Found details for {aid}:\n{details}"
    except Exception as e:
        return f"ERROR: Could not retrieve data - {str(e)}"

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

    try:
        res = requests.put(f"{BASE_URL}/update/{aid}", json=payload, timeout=5)
        if res.status_code == 200:
            return f"SUCCESS: Appointment **{aid}** has been updated."
        return f"ERROR: Failed to update"
    except Exception as e:
        return f"ERROR: Backend connection failed - {str(e)}"

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
# ROUTES
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

if __name__ == "__main__":
    app.run(port=5001, debug=True)
