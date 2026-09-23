from backend.models.user import User


def test_user_model():
    user = User(username="testuser", password_hash="dummy_hash")
    assert user.username == "testuser"


def test_read_main(auth_client):
    response = auth_client.get("/api/accounts/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)