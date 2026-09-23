import requests

response = requests.get("http://localhost:8000/api/bitcoin/price")
print(response.json())