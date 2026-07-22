from types import SimpleNamespace

import bot.database as db
from bot.services.line_assignment import build_bank_selection_rows, send_line_assignment_messages


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append(("send_message", chat_id, text))
        return SimpleNamespace(message_id=10)

    async def send_photo(self, chat_id, photo, **kwargs):
        self.calls.append(("send_photo", chat_id))
        return SimpleNamespace(message_id=11)

    async def delete_message(self, chat_id, message_id):
        self.calls.append(("delete_message", chat_id, message_id))


class FakeBotFailing:
    async def send_message(self, chat_id, text, **kwargs):
        raise RuntimeError("send failed")

    async def send_photo(self, chat_id, photo, **kwargs):
        return SimpleNamespace(message_id=11)

    async def delete_message(self, chat_id, message_id):
        pass


def test_build_bank_selection_rows():
    keyboard = build_bank_selection_rows(
        ["bank.kd", "IziBank"],
        client_id=123,
        selected=["IziBank"],
        passed_banks=["bank.kd"],
        banned_banks=[],
    )

    assert len(keyboard) == 1
    assert len(keyboard[0]) == 2

    assert keyboard[0][0].text == "[ ] bank.kd (✅ Пройдено)"
    assert keyboard[0][0].callback_data == "toggle_123_bank.kd"

    assert keyboard[0][1].text == "[x] IziBank"
    assert keyboard[0][1].callback_data == "toggle_123_IziBank"


def test_build_bank_selection_rows_banned():
    keyboard = build_bank_selection_rows(
        ["Alliance"],
        client_id=1,
        banned_banks=["Alliance"],
    )
    assert keyboard[0][0].text == "[ ] Alliance (❌ Бан)"


async def test_send_line_assignment_messages(test_db):
    await db.assign_line_to_session(12345, 1)

    fake_bot = FakeBot()
    result = await send_line_assignment_messages(12345, 1, fake_bot)

    assert result is not None
    assert result["client_msg_id"] == 10

    session = await db.get_session(12345)
    assert "IziBank" in session.get("notified_banks", "")
    assert session["line_id"] == 1

    send_texts = [call[2] for call in fake_bot.calls if call[0] == "send_message"]
    assert "Реєстрація робиться за моїм номером телефону, скажете коли потрібен буде СМС код" in send_texts
    assert "`+380111111111`" in send_texts


async def test_send_line_assignment_messages_rollback(test_db):
    await db.assign_line_to_session(12345, 1)

    result = await send_line_assignment_messages(12345, 1, FakeBotFailing())
    assert result is None

    line = await db.get_line(1)
    assert line["status"] == "available"

    session = await db.get_session(12345)
    assert session["line_id"] is None
    assert session["status"] == "registered"

class FakeState:
    def __init__(self):
        self.data = {}
        self.state = None

    async def get_data(self):
        return self.data

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def set_state(self, state):
        self.state = state

async def test_send_line_assignment_messages_relink(test_db):
    # Save a template for izibank with allow_relink = 1
    await db.save_bank_template(
        key="izibank",
        command="/izibank",
        text="Instruction text",
        allow_relink=1,
        relink_instruction_text="Relink instruction"
    )

    await db.assign_line_to_session(12345, 1)

    fake_bot = FakeBot()
    fake_state = FakeState()
    result = await send_line_assignment_messages(12345, 1, fake_bot, state=fake_state)

    assert result is not None
    assert result["client_msg_id"] == 10

    # The client should have received choice prompt
    send_texts = [call[2] for call in fake_bot.calls if call[0] == "send_message"]
    assert any("\u0440\u0435\u0454\u0441\u0442\u0440\u0430\u0446" in t for t in send_texts)
    
    # State should be updated
    assert fake_state.state is not None
    assert "relink_choice_msg_id" in fake_state.data
    assert fake_state.data["bank_name"] == "izibank"
