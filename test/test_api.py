import requests
import datetime
import json

BASE_URL = "http://127.0.0.1:8000"
TODAY = str(datetime.date.today())

def print_result(description, response):
    print(f"\n--- {description} ---")
    print(f"HTTP Status: {response.status_code}")
    # Pretty print the JSON response
    print(json.dumps(response.json(), indent=2))

# 1. Create a dummy student to attach scores to
print("Initializing test sequence...")
student_res = requests.post(f"{BASE_URL}/students/?name=Test+Student")
student_id = student_res.json().get("id")

if not student_id:
    print("Failed to create student. Is the server running?")
    exit(1)

# 2. Test a Valid Payload
valid_payload = {
    "student_id": student_id,
    "subject": "Mathematics",
    "marks_obtained": 85,
    "total_marks": 100,
    "assessment_date": TODAY,
    "status": "present"
}
res = requests.post(f"{BASE_URL}/scores/", json=valid_payload)
print_result("Test 1: Valid Score Entry (85/100)", res)

# 3. Test Edge Case: Impossible Score (Teacher Typo)
invalid_too_high = valid_payload.copy()
invalid_too_high["marks_obtained"] = 120
res = requests.post(f"{BASE_URL}/scores/", json=invalid_too_high)
print_result("Test 2: Marks Exceed Total (120/100)", res)

# 4. Test Edge Case: Negative Score
invalid_negative = valid_payload.copy()
invalid_negative["marks_obtained"] = -10
res = requests.post(f"{BASE_URL}/scores/", json=invalid_negative)
print_result("Test 3: Negative Marks (-10/100)", res)

# 5. Test Edge Case: Missing Marks when Present
invalid_missing = valid_payload.copy()
invalid_missing["marks_obtained"] = None
res = requests.post(f"{BASE_URL}/scores/", json=invalid_missing)
print_result("Test 4: Missing Marks but Marked 'Present'", res)

# 6. Test Edge Case: Excused Absence (Missing Marks Valid)
valid_excused = valid_payload.copy()
valid_excused["status"] = "excused"
valid_excused["marks_obtained"] = None
res = requests.post(f"{BASE_URL}/scores/", json=valid_excused)
print_result("Test 5: Valid Excused Absence (No Marks Required)", res)
