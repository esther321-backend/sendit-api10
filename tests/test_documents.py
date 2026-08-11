# tests/test_documents.py
import pytest
import io

@pytest.fixture
def auth_headers(client, test_user):
    client.post("/register", json=test_user)
    response = client.post(
        "/login",
        data={"username": test_user["username"], "password": test_user["password"]}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_upload_document_success(client, auth_headers):
    file_data = io.BytesIO(b"Sample PDF content for waybill")
    files = {"file": ("waybill.pdf", file_data, "application/pdf")}
    data = {"city": "Nyeri", "country": "Kenya", "description": "Nyeri waybill"}

    response = client.post("/documents/upload", files=files, data=data, headers=auth_headers)
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["message"] == "Document uploaded successfully"
    assert "document_id" in res_json

def test_upload_invalid_file_extension(client, auth_headers):
    file_data = io.BytesIO(b"Executable content")
    files = {"file": ("script.exe", file_data, "application/octet-stream")}
    data = {"city": "Nyeri"}

    response = client.post("/documents/upload", files=files, data=data, headers=auth_headers)
    assert response.status_code == 400
    assert "File type not allowed" in response.json()["detail"]

def test_list_documents(client, auth_headers):
    response = client.get("/documents", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
