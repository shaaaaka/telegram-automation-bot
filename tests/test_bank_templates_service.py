import pytest
import bot.database as db
from bot.services.bank_templates_service import (
    get_all_bank_templates,
    save_bank_template,
    delete_bank_template,
    get_bank_template_db,
    get_bank_template_with_key_db,
    get_bank_display_name,
)

@pytest.mark.asyncio
async def test_bank_templates_crud(test_db):
    # Save a template
    await save_bank_template(
        key="test_bank_key",
        command="/testbank",
        text="Test instruction",
        code_length=6,
        display_name="Test Bank"
    )

    templates = await get_all_bank_templates()
    assert "test_bank_key" in templates
    assert templates["test_bank_key"]["code_length"] == 6

    # Get by bank name
    tpl = await get_bank_template_db("test_bank_key")
    assert tpl is not None
    assert tpl["display_name"] == "Test Bank"

    key, tpl_key = await get_bank_template_with_key_db("test_bank_key")
    assert key == "test_bank_key"

    disp_name = await get_bank_display_name("test_bank_key")
    assert disp_name == "Test Bank"

    # Delete template
    await delete_bank_template("test_bank_key")
    templates_after = await get_all_bank_templates()
    assert "test_bank_key" not in templates_after


@pytest.mark.asyncio
async def test_bank_templates_database_reexport_compatibility(test_db):
    await db.save_bank_template(
        key="compat_bank",
        command="/compat",
        text="Compat instruction",
        display_name="Compat Bank"
    )

    tpl = await db.get_bank_template_db("compat_bank")
    assert tpl is not None
    assert tpl["display_name"] == "Compat Bank"

    disp_name = await db.get_bank_display_name("compat_bank")
    assert disp_name == "Compat Bank"

    await db.delete_bank_template("compat_bank")
