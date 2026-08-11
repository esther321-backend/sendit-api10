# tests/test_integration.py
import pytest
import io

def test_full_sendit_flow(client, test_user):
    # 1. Register User
    reg_resp = client.post("/register", json=test_user)
    assert reg_resp.status_code in [200, 201]

    # 2. Login User
    login_resp = client.post(
        "/login",
        data={"username": test_user["username"], "password": test_user["password"]}
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Upload Document
    file_data = io.BytesIO(b"Invoice 1001 content")
    files = {"file": ("invoice1001.pdf", file_data, "application/pdf")}
    upload_resp = client.post("/documents/upload", files=files, data={"city": "Nairobi"}, headers=headers)
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["document_id"]

    # 4. Fetch Uploaded Document Details
    doc_resp = client.get(f"/documents/{doc_id}", headers=headers)
    assert doc_resp.status_code == 200
    assert doc_resp.json()["city"] == "Nairobi"# tests/test_integration.py

