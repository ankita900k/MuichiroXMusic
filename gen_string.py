from pyrogram import Client

API_ID = int(input("Enter your API ID: "))
API_HASH = input("Enter your API HASH: ")

app = Client(
    "MuichiroSession",
    api_id=API_ID,
    api_hash=API_HASH,
    in_memory=True
)

with app:
    session_string = app.export_session_string()

    print("\n========== SESSION STRING ==========")
    print(session_string)
    print("====================================")