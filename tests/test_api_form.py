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
    # Setup: do nothing
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
