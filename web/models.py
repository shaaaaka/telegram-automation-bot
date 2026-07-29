from typing import List, Optional
from pydantic import BaseModel


__all__ = [
    "BanksSelection",
    "LineAssignment",
    "CodeRouting",
    "LineAdd",
    "TemplateSendRequest",
    "ClientMessage",
    "AppSettingsUpdate",
    "BankTemplateUpdate",
    "BankProfileUpdate",
    "AIRuleCreate",
    "AIExampleCreate",
    "AISettingsUpdate",
    "AILearnRequest",
    "VerificationMethodCreate",
    "VerificationMethodUpdate",
]


class BanksSelection(BaseModel):
    selected_banks: List[str]
class LineAssignment(BaseModel):
    line_id: int
class CodeRouting(BaseModel):
    code: str
class LineAdd(BaseModel):
    id: int
    line_id: int | None = None
    phone_number: str
    bank: str
class TemplateSendRequest(BaseModel):
    template_key: str
class ClientMessage(BaseModel):
    message: str
    reply_to_message_id: Optional[int] = None
class AppSettingsUpdate(BaseModel):
    reminder_delay_minutes: str
    reminder_text: str
    reminders_enabled: str
    giver_request_format: Optional[str] = None
    giver_request_retry_format: Optional[str] = None
    client_number_assigned_format: Optional[str] = None
    admin_id: Optional[str] = None
    anketa_chat_id: Optional[str] = None
    giver_chat_id: Optional[str] = None
    archive_group_id: Optional[str] = None
    sms_cooldown_seconds: Optional[str] = None
    sleep_mode_enabled: Optional[str] = None
    sleep_mode_start: Optional[str] = None
    sleep_mode_end: Optional[str] = None
    sleep_mode_timezone: Optional[str] = None
    sleep_mode_reply: Optional[str] = None
class BankTemplateUpdate(BaseModel):
    key: str
    command: str
    text: str
    code_length: Optional[int] = 4

class BankProfileUpdate(BaseModel):
    profile_key: str
    name: Optional[str] = None
    selected_banks: List[str] = []
    bot_username: Optional[str] = None
    bot_token: Optional[str] = None
    avatar_data_url: Optional[str] = None
    is_active: Optional[int] = 1
    sort_order: Optional[int] = 0
class AIRuleCreate(BaseModel):
    rule_text: str
    category: str = "general"
    is_active: Optional[int] = 1
class AIExampleCreate(BaseModel):
    client_message: str
    bot_response: str
    is_active: Optional[int] = 1
class AISettingsUpdate(BaseModel):
    ai_income_limit: str
    ai_turnover_limit: str
    ai_password_kd: str
    ai_password_other: str
class AILearnRequest(BaseModel):
    client_ids: list[int] = None


class VerificationMethodCreate(BaseModel):
    key: Optional[str] = None
    display_name: Optional[str] = None
    allowed_banks: Optional[List[str]] = None
    linked_bots: Optional[List[str]] = None
    required_client_fields: Optional[List[str]] = None
    initial_message: Optional[str] = None
    is_active: Optional[int] = 1
    sort_order: Optional[int] = 0


class VerificationMethodUpdate(BaseModel):
    key: Optional[str] = None
    display_name: Optional[str] = None
    allowed_banks: Optional[List[str]] = None
    linked_bots: Optional[List[str]] = None
    required_client_fields: Optional[List[str]] = None
    initial_message: Optional[str] = None
    is_active: Optional[int] = None
    sort_order: Optional[int] = None
