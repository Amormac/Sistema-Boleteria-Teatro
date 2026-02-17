#!/bin/bash
# Test Script for New Features
# Requires services running

# 1. Login as Admin
echo "--- Login ---"
TOKEN=$(curl -s -X POST http://localhost:7000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@teatro.com", "password":"admin"}' | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])")

if [ -z "$TOKEN" ]; then
    echo "Login failed"
    exit 1
fi
echo "Token obtained."

# 2. Create Venue with Images
echo -e "\n--- Create Venue ---"
VENUE_RES=$(curl -s -X POST http://localhost:7001/api/venues \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sala Visual",
    "rows_count": 5,
    "cols_count": 5,
    "image_main": "http://img.com/main.jpg",
    "image_gallery": ["http://img.com/1.jpg", "http://img.com/2.jpg"]
  }')
echo $VENUE_RES
VENUE_ID=$(echo $VENUE_RES | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "Created Venue ID: $VENUE_ID"

# 3. Update Venue
echo -e "\n--- Update Venue ---"
curl -s -X PUT http://localhost:7001/api/venues/$VENUE_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sala Visual Updated",
    "image_main": "http://img.com/new.jpg",
    "image_gallery": []
  }'

# 4. Create Event (Success)
echo -e "\n--- Create Event (Valid) ---"
START_TIME=$(date -u -d '+1 day' +'%Y-%m-%dT%H:00:00Z')
END_TIME=$(date -u -d '+1 day +2 hours' +'%Y-%m-%dT%H:00:00Z')

EVENT_RES=$(curl -s -X POST http://localhost:7001/api/events \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    "venue_id": $VENUE_ID,
    "title": "Evento Test",
    "start_time": \"$START_TIME\",
    "end_time": \"$END_TIME\",
    "price": 10
  }")
echo $EVENT_RES

# 5. Create Event (Overlap Fail)
echo -e "\n--- Create Event (Overlap) ---"
# Same time as above
curl -s -X POST http://localhost:7001/api/events \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    "venue_id": $VENUE_ID,
    "title": "Evento Overlap",
    "start_time": \"$START_TIME\",
    "end_time": \"$END_TIME\",
    "price": 10
  }"

# 6. Delete Venue (Fail due to event)
echo -e "\n--- Delete Venue (Should Fail) ---"
curl -s -X DELETE http://localhost:7001/api/venues/$VENUE_ID \
  -H "Authorization: Bearer $TOKEN"

# 7. Cleanup: Delete Event manually (via DB or ignored for now)
# We can't delete event via API yet (only status update).
# So we can't test successful venue deletion unless we access DB directly.
