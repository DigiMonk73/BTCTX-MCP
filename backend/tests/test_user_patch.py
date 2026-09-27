#!/usr/bin/env python3
from backend.tests.conftest import default_login
import requests

BASE_URL = "http://127.0.0.1:8000/api"  # Adjust if your server runs at a different URL/port

def main():
    session = requests.Session()

    # -------------------------------------------------
    # 1) Log in as the default user: admin/password
    # -------------------------------------------------
    login_payload = default_login()
    resp = session.post(f"{BASE_URL}/login", json=login_payload)
    if resp.status_code != 200:
        print("❌ Login failed:", resp.status_code, resp.text)
        return
    print("✅ Logged in as admin:", resp.json())

    # -------------------------------------------------
    # 2) Get /users to confirm we see the existing user
    # -------------------------------------------------
    resp = session.get(f"{BASE_URL}/users")
    if resp.status_code == 200:
        print("✅ GET /users =>", resp.json())
    else:
        print("❌ GET /users failed:", resp.status_code, resp.text)
        return

    # Expect something like: [ {"id": 1, "username": "admin"} ]
    users = resp.json()
    if not users:
        print("❌ No user returned. Database might be empty?")
        return
    
    user_id = users[0]["id"]  # typically 1 for your default admin
    print(f"User found. ID={user_id}, username={users[0]['username']}")

    # -------------------------------------------------
    # 3) PATCH /users/{id} to change username/password
    #    This tests partial update of the user
    # -------------------------------------------------
    new_creds = {
        "username": "rick",
        "password": "0123456789",
    }
    resp = session.patch(f"{BASE_URL}/users/{user_id}", json=new_creds)
    if resp.status_code == 200:
        print("✅ PATCH success:", resp.json())
    else:
        print("❌ PATCH failed:", resp.status_code, resp.text)
        return

    # -------------------------------------------------
    # 4) Confirm the update "stuck" by GET /users again
    # -------------------------------------------------
    resp = session.get(f"{BASE_URL}/users")
    if resp.status_code != 200:
        print("❌ GET /users after patch failed:", resp.status_code, resp.text)
        return

    updated_users = resp.json()
    print("✅ GET /users =>", updated_users)
    # Check the user’s new username
    user = next(u for u in updated_users if u["id"] == user_id)
    if user["username"] == "NewAdminName":
        print("✅ Username was updated successfully in the DB!")
    else:
        print("❌ Username not updated. Got:", user["username"])

    # -------------------------------------------------
    # 5) (Optional) Log out
    # -------------------------------------------------
    resp = session.post(f"{BASE_URL}/logout")
    if resp.status_code == 200:
        print("✅ Logged out:", resp.json())
    else:
        print("⚠️ Logout error or not implemented:", resp.status_code, resp.text)

if __name__ == "__main__":
    main()
