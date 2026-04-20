Postman WebSocket instructions for Shortcut Showdown

Postman limitation
------------------
Postman does not reliably import WebSocket requests from a collection JSON. The HTTP requests in this collection (create/join/start/get room/leave) will import correctly, but WebSocket connections must be created manually in the Postman app.

Manual steps (quick)
--------------------
1. Open the Postman desktop app (recommended).  
2. Import this collection to get the HTTP requests.  
3. Create a WebSocket connection for Player 1:  
   - Click **New > WebSocket**.  
   - Enter: `ws://127.0.0.1:8000/ws` and click **Connect**.  
   - On connect you'll receive a JSON message like:  
     `{ "event": "connect", "player_id": "<id>" }`  
   - Copy that `player_id` into Postman environment variable `player_id`.
4. Repeat step 3 in a second WebSocket tab to connect Player 2; save their id to `player2_id`.
5. Use the imported HTTP requests in the collection to `Create Lobby`, `Join Lobby`, and `Start Game` (they use the `player_id` variables you set).
6. Send inputs via the WebSocket "Send" box with JSON messages, for example:  
   - Correct input example: `{ "event": "input", "keys": ["ctrl","c"] }`  
   - Incorrect input example: `{ "event": "input", "keys": ["wrong"] }`  
7. Watch the WebSocket message stream for events: `progress_update`, `penalty`, `spam_blocked`, and `game_result`.

Notes & troubleshooting
-----------------------
- If you need the WS messages scripted for automation, consider using a small Node/Python script that opens a WebSocket connection and sends the JSON messages; Postman's collection import won't convert WS tabs into programmatic WS scripts automatically.
- The collection still contains all HTTP steps you can run directly after creating the WS connections.

Contact
-------
If you'd like, I can:  
- Add a small `ws-client.py` script to the repo to automate WS connect/send for tests, or  
- Attempt a more advanced collection format that some users have reported works with newer Postman versions (less reliable).  
Tell me which you prefer and I'll implement it.