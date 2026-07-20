import pytest
import os
import bot.database as db
from bot.services.line_assignment import send_line_assignment_messages
from tests.test_services import FakeBot


@pytest.mark.asyncio
async def test_save_and_get_bank_template_with_multiple_paths(test_db):
    # Save a template with multiple paths and descriptions
    await db.save_bank_template(
        key="TestBank",
        command="/testbank",
        text="Instruction Text",
        code_length=4,
        screenshot_path="/static/img1.jpg,/static/img2.jpg",
        download_screenshot_path="/static/dl1.jpg,/static/dl2.jpg",
        success_screenshot_path="/static/success1.jpg,/static/success2.jpg",
        deletion_screenshot_path="/static/del1.jpg,/static/del2.mp4",
        deletion_requirement="video",
        instruction_text="Custom step instructions",
        success_text="Custom success instructions",
        deletion_text="Custom deletion instructions"
    )

    template = await db.get_bank_template_db("TestBank")
    assert template is not None
    assert template["screenshot_path"] == "/static/img1.jpg,/static/img2.jpg"
    assert template["download_screenshot_path"] == "/static/dl1.jpg,/static/dl2.jpg"
    assert template["success_screenshot_path"] == "/static/success1.jpg,/static/success2.jpg"
    assert template["deletion_screenshot_path"] == "/static/del1.jpg,/static/del2.mp4"
    assert template["deletion_requirement"] == "video"
    assert template["instruction_text"] == "Custom step instructions"
    assert template["success_text"] == "Custom success instructions"
    assert template["deletion_text"] == "Custom deletion instructions"


@pytest.mark.asyncio
async def test_multiple_download_screenshots_sending(test_db):
    # Prepare files
    os.makedirs("web/static", exist_ok=True)
    with open("web/static/dl1.jpg", "w") as f:
        f.write("fake")
    with open("web/static/dl2.jpg", "w") as f:
        f.write("fake")

    try:
        # Save template with 2 paths
        await db.save_bank_template(
            key="TestBank",
            command="/testbank",
            text="Test Download Instructions",
            code_length=4,
            download_screenshot_path="/static/dl1.jpg,/static/dl2.jpg"
        )

        # Set up active line for assignment
        await db.add_or_update_line(2, "+380222222222", "TestBank")
        await db.assign_line_to_session(12345, 2)

        fake_bot = FakeBot()
        # Mock send_media_group on fake_bot
        media_group_calls = []
        async def fake_send_media_group(chat_id, media, **kwargs):
            media_group_calls.append((chat_id, media))
            from types import SimpleNamespace
            return [SimpleNamespace(photo=[SimpleNamespace(file_id="abc")])]
        fake_bot.send_media_group = fake_send_media_group

        await send_line_assignment_messages(12345, 2, fake_bot)

        # Verify that send_media_group was called instead of send_photo
        assert len(media_group_calls) == 1
        chat_id, media = media_group_calls[0]
        assert chat_id == 12345
        assert len(media) == 2
        assert media[0].caption == "Test Download Instructions"

    finally:
        # Clean up files
        try:
            os.remove("web/static/dl1.jpg")
            os.remove("web/static/dl2.jpg")
        except Exception:
            pass
