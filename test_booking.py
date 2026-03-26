
import requests
import json

url = "http://localhost:5001/chat"
payload = {
    "message": "Book an appointment for raj, phone: 7894561230, date: 27/3/2026, time: 2pm",
    "session_id": "test_session"
}
headers = {
    "Content-Type": "application/json"
}

response = requests.post(url, data=json.dumps(payload), headers=headers)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
