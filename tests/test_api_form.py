import pytest
from fastapi.testclient import TestClient
from web.routers.settings import router
from fastapi import FastAPI
import io
import os
import sqlite3
from bot.config import DB_FILE

# Create a test app
app = FastAPI()
app.include_router(router)

client = TestClient(app)

@pytest.fixture(autouse=True)
def cleanup_test_bank():
    # Setup: initialize/migrate database schema
    import asyncio
    import bot.database as db
    asyncio.run(db.init_db())
    yield
    # Teardown: delete DB template
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bank_templates WHERE key = ?", ("TestBankAPI",))
    conn.commit()
    conn.close()

    # Delete files
    for i in range(1, 5):
        for suffix in ["download", "success", "step", "deletion"]:
            for ext in [".jpg", ".png", ".mp4", ".jpeg"]:
                path = f"web/static/images/uploaded/instructions/TestBankAPI_{suffix}{i}{ext}"
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass

def test_save_template_form():
    data = {
        "key": "TestBankAPI",
        "command": "/test",
        "text": "Instruction text",
        "code_length": "4",
        "ai_rules": "",
        "report_template": "",
        "required_screenshots": "1",
        "description": "desc",
        "display_name": "TestBankAPI",
        "is_active": "1",
        "deletion_requirement": "none",
        "logo_removed": "false",
        "screenshots_removed": "false",
        "download_screenshot_removed": "false",
        "success_screenshot_removed": "false",
        "deletion_screenshot_removed": "false",
    }
    
    files = [
        ("download_screenshot_files", ("file1.jpg", io.BytesIO(b"data1"), "image/jpeg")),
        ("download_screenshot_files", ("file2.jpg", io.BytesIO(b"data2"), "image/jpeg"))
    ]
    
    response = client.post("/api/settings/templates", data=data, files=files)
    assert response.status_code == 200

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bank_templates WHERE key = ?", ("TestBankAPI",))
    row = cursor.fetchone()
    assert row is not None
    assert row["download_screenshot_path"] is not None
    conn.close()

def test_retain_existing_files():
    # Save first
    data_save = {
        "key": "TestBankAPI",
        "command": "/test",
        "text": "Instruction text",
        "code_length": "4",
        "ai_rules": "",
        "report_template": "",
        "required_screenshots": "1",
        "description": "desc",
        "display_name": "TestBankAPI",
        "is_active": "1",
        "deletion_requirement": "none",
        "logo_removed": "false",
        "screenshots_removed": "false",
        "download_screenshot_removed": "false",
        "success_screenshot_removed": "false",
        "deletion_screenshot_removed": "false",
    }
    files = [
        ("download_screenshot_files", ("file1.jpg", io.BytesIO(b"data1"), "image/jpeg")),
        ("download_screenshot_files", ("file2.jpg", io.BytesIO(b"data2"), "image/jpeg"))
    ]
    client.post("/api/settings/templates", data=data_save, files=files)

    # Update without files
    data = {
        "key": "TestBankAPI",
        "command": "/test",
        "text": "Instruction text updated",
        "code_length": "4",
        "ai_rules": "",
        "report_template": "",
        "required_screenshots": "1",
        "description": "desc",
        "display_name": "TestBankAPI",
        "is_active": "1",
        "deletion_requirement": "none",
        "logo_removed": "false",
        "screenshots_removed": "false",
        "download_screenshot_removed": "false",
        "success_screenshot_removed": "false",
        "deletion_screenshot_removed": "false",
    }
    
    response = client.post("/api/settings/templates", data=data)
    assert response.status_code == 200
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bank_templates WHERE key = ?", ("TestBankAPI",))
    row = cursor.fetchone()
    assert row is not None
    assert row["download_screenshot_path"] is not None
    conn.close()


def test_ai_settings_endpoints():
    # Save current settings to restore later
    orig_res = client.get("/api/settings/ai")
    orig_data = orig_res.json() if orig_res.status_code == 200 else {}

    try:
        # 1. GET AI Settings
        response = client.get("/api/settings/ai")
        assert response.status_code == 200
        data = response.json()
        assert "ai_income_limit" in data
        assert "rules" in data
        assert "examples" in data

        # 2. POST AI settings updates
        body = {
            "ai_income_limit": "26000",
            "ai_turnover_limit": "31000",
            "ai_password_kd": "54321",
            "ai_password_other": "9999"
        }
        response = client.post("/api/settings/ai", json=body)
        assert response.status_code == 200

        # Verify updated settings
        response = client.get("/api/settings/ai")
        data = response.json()
        assert data["ai_income_limit"] == "26000"
        assert data["ai_turnover_limit"] == "31000"
        assert data["ai_password_kd"] == "54321"
        assert data["ai_password_other"] == "9999"
    finally:
        if orig_data:
            client.post("/api/settings/ai", json={
                "ai_income_limit": orig_data.get("ai_income_limit", "25000"),
                "ai_turnover_limit": orig_data.get("ai_turnover_limit", "30000"),
                "ai_password_kd": orig_data.get("ai_password_kd", "12345"),
                "ai_password_other": orig_data.get("ai_password_other", "1111, 1234 або 1232")
            })


def test_ai_rules_endpoints():
    # 1. Add AI rule
    rule_body = {
        "rule_text": "Test AI Rule Text",
        "category": "general",
        "is_active": 1
    }
    response = client.post("/api/settings/ai/rules", json=rule_body)
    assert response.status_code == 200
    rule_id = response.json()["id"]

    # 2. Update AI rule
    updated_rule = {
        "rule_text": "Updated Test AI Rule Text",
        "category": "troubleshooting",
        "is_active": 0
    }
    response = client.put(f"/api/settings/ai/rules/{rule_id}", json=updated_rule)
    assert response.status_code == 200

    # Verify rules list contains the updated rule
    response = client.get("/api/settings/ai")
    rules = response.json()["rules"]
    matching = [r for r in rules if r["id"] == rule_id]
    assert len(matching) == 1
    assert matching[0]["rule_text"] == "Updated Test AI Rule Text"
    assert matching[0]["category"] == "troubleshooting"
    assert matching[0]["is_active"] == 0

    # 3. Toggle AI rule
    response = client.post(f"/api/settings/ai/rules/{rule_id}/toggle?is_active=1")
    assert response.status_code == 200
    
    response = client.get("/api/settings/ai")
    rules = response.json()["rules"]
    matching = [r for r in rules if r["id"] == rule_id]
    assert matching[0]["is_active"] == 1

    # 4. Delete AI rule
    response = client.delete(f"/api/settings/ai/rules/{rule_id}")
    assert response.status_code == 200

    # Verify deleted
    response = client.get("/api/settings/ai")
    rules = response.json()["rules"]
    matching = [r for r in rules if r["id"] == rule_id]
    assert len(matching) == 0


def test_ai_examples_endpoints():
    # 1. Add AI example
    example_body = {
        "client_message": "Test question?",
        "bot_response": "Test answer.",
        "is_active": 1
    }
    response = client.post("/api/settings/ai/examples", json=example_body)
    assert response.status_code == 200
    example_id = response.json()["id"]

    # 2. Update AI example
    updated_example = {
        "client_message": "Updated question?",
        "bot_response": "Updated answer.",
        "is_active": 0
    }
    response = client.put(f"/api/settings/ai/examples/{example_id}", json=updated_example)
    assert response.status_code == 200

    # Verify updated example
    response = client.get("/api/settings/ai")
    examples = response.json()["examples"]
    matching = [e for e in examples if e["id"] == example_id]
    assert len(matching) == 1
    assert matching[0]["client_message"] == "Updated question?"
    assert matching[0]["bot_response"] == "Updated answer."
    assert matching[0]["is_active"] == 0

    # 3. Toggle AI example
    response = client.post(f"/api/settings/ai/examples/{example_id}/toggle?is_active=1")
    assert response.status_code == 200
    
    response = client.get("/api/settings/ai")
    examples = response.json()["examples"]
    matching = [e for e in examples if e["id"] == example_id]
    assert matching[0]["is_active"] == 1

    # 4. Delete AI example
    response = client.delete(f"/api/settings/ai/examples/{example_id}")
    assert response.status_code == 200

    # Verify deleted
    response = client.get("/api/settings/ai")
    examples = response.json()["examples"]
    matching = [e for e in examples if e["id"] == example_id]
    assert len(matching) == 0

