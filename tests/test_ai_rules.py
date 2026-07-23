import pytest
import bot.database as db
from bot.services.ai_rules_service import (
    add_ai_rule,
    get_all_ai_rules,
    get_active_ai_rules,
    toggle_ai_rule,
    update_ai_rule,
    delete_ai_rule,
    add_ai_example,
    get_all_ai_examples,
    get_active_ai_examples,
    toggle_ai_example,
    update_ai_example,
    delete_ai_example,
)

@pytest.mark.asyncio
async def test_ai_rules_crud(test_db):
    # Test add AI rule
    rule_id = await add_ai_rule("Тестове правило ШІ", category="general", is_active=1)
    assert rule_id > 0

    all_rules = await get_all_ai_rules()
    active_rules = await get_active_ai_rules(category="general")
    assert any(r["id"] == rule_id and r["rule_text"] == "Тестове правило ШІ" for r in all_rules)
    assert any(r["id"] == rule_id for r in active_rules)

    # Test update rule
    await update_ai_rule(rule_id, "Оновлене правило ШІ", category="general", is_active=1)
    rules_after_update = await get_all_ai_rules()
    updated_rule = next(r for r in rules_after_update if r["id"] == rule_id)
    assert updated_rule["rule_text"] == "Оновлене правило ШІ"

    # Test toggle rule
    await toggle_ai_rule(rule_id, is_active=0)
    active_after_toggle = await get_active_ai_rules()
    assert not any(r["id"] == rule_id for r in active_after_toggle)

    # Test delete rule
    await delete_ai_rule(rule_id)
    rules_after_delete = await get_all_ai_rules()
    assert not any(r["id"] == rule_id for r in rules_after_delete)


@pytest.mark.asyncio
async def test_ai_examples_crud(test_db):
    # Test add AI example
    example_id = await add_ai_example("Привіт", "Вітаю! Чим допомогти?", is_active=1)
    assert example_id > 0

    all_examples = await get_all_ai_examples()
    active_examples = await get_active_ai_examples()
    assert any(e["id"] == example_id and e["client_message"] == "Привіт" for e in all_examples)
    assert any(e["id"] == example_id for e in active_examples)

    # Test update example
    await update_ai_example(example_id, "Привіт!", "Доброго дня!", is_active=1)
    examples_after_update = await get_all_ai_examples()
    updated_ex = next(e for e in examples_after_update if e["id"] == example_id)
    assert updated_ex["bot_response"] == "Доброго дня!"

    # Test toggle example
    await toggle_ai_example(example_id, is_active=0)
    active_after_toggle = await get_active_ai_examples()
    assert not any(e["id"] == example_id for e in active_after_toggle)

    # Test delete example
    await delete_ai_example(example_id)
    examples_after_delete = await get_all_ai_examples()
    assert not any(e["id"] == example_id for e in examples_after_delete)


@pytest.mark.asyncio
async def test_ai_rules_database_compatibility(test_db):
    # Test re-export compatibility via bot.database
    r_id = await db.add_ai_rule("Сумісне правило", category="test", is_active=1)
    assert r_id > 0

    rules = await db.get_active_ai_rules("test")
    assert any(r["id"] == r_id for r in rules)

    await db.delete_ai_rule(r_id)
