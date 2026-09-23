import requests

# Define the API URL (adjust for your local setup)
API_URL = "http://127.0.0.1:8000/api/transactions/"

# Refactored sample transaction data (Deposit from external to bank)
transaction_data = {
    "type": "Deposit",
    "timestamp": "2025-02-04T12:30:00",
    "from_account_id": 99,       # External source
    "to_account_id": 1,         # Bank
    "amount": 1000.00,          # total amount deposited
    "fee_amount": 0.50,         # fee in USD
    "fee_currency": "USD",
    "cost_basis_usd": 0,        # for USD deposits, usually 0 (no BTC involved)
    "source": "Income",
    "purpose": None,
    "is_locked": False
}

# Send POST request to the API
response = requests.post(API_URL, json=transaction_data)

# Print the response
print("Response status code:", response.status_code)
print("Response JSON:", response.json())
