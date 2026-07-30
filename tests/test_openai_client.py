import pytest
from bot.services.prompt_service import compile_system_instruction, BASE_MANNER_OF_SPEECH
import bot.openai_client as openai_client
import bot.services.vision_service as vision_service

@pytest.mark.asyncio
async def test_compile_system_instruction_basic(test_db):
    prompt = await compile_system_instruction(current_bank_name="izibank", sent_codes_count=0)
    assert "ОПИС МАНЕРИ СПІЛКУВАННЯ ТА СТИЛЮ" in prompt
    assert "izibank" in prompt.lower() or "НАЛАШТУВАННЯ ТА ПРАВИЛА ДЛЯ БАНКУ" in prompt

@pytest.mark.asyncio
async def test_compile_system_instruction_with_sent_codes(test_db):
    prompt_codes = await compile_system_instruction(current_bank_name="amobank", sent_codes_count=2)
    assert "amobank" in prompt_codes.lower()

@pytest.mark.asyncio
async def test_openai_client_reexports(test_db):
    # Verify backward compatibility re-exports
    assert hasattr(openai_client, "BASE_MANNER_OF_SPEECH")
    assert hasattr(openai_client, "compile_system_instruction")
    assert hasattr(openai_client, "analyze_proceedings_screenshot")
    assert hasattr(openai_client, "verify_deletion_proof")
    assert hasattr(openai_client, "verify_relink_initial_screenshot")

@pytest.mark.asyncio
async def test_vision_service_no_client():
    # Calling vision service with None client should handle safely
    res_proceedings = await vision_service.analyze_proceedings_screenshot(None, b"fake_bytes")
    assert "[UNKNOWN]" in res_proceedings

    is_valid_del, reason_del = await vision_service.verify_deletion_proof(None, b"fake_bytes", "photo")
    assert is_valid_del is True

    is_valid_relink, reason_relink = await vision_service.verify_relink_initial_screenshot(None, b"fake_bytes")
    assert is_valid_relink is True

    is_valid_pumb, reason_pumb = await vision_service.verify_pumb_rebind_step(None, b"fake_bytes", b"example", 0, "test")
    assert is_valid_pumb is True
    assert "пропускаємо" in reason_pumb

