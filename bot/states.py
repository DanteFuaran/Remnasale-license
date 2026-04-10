from aiogram.fsm.state import State, StatesGroup


class AddServerState(StatesGroup):
    waiting_name = State()
    waiting_period = State()


class RenameState(StatesGroup):
    waiting_name = State()


class SettingsIntervalState(StatesGroup):
    waiting_interval = State()


class SettingsOfflineGraceState(StatesGroup):
    waiting_days = State()


class SettingsSupportUrlState(StatesGroup):
    waiting_url = State()


class SettingsCommunityUrlState(StatesGroup):
    waiting_url = State()


class SendMessageState(StatesGroup):
    composing = State()
    waiting_text = State()


class BroadcastState(StatesGroup):
    composing = State()
    waiting_text = State()


class QuickReplyState(StatesGroup):
    waiting_text = State()


class DurationState(StatesGroup):
    waiting_days = State()


class GatewayFieldState(StatesGroup):
    waiting_value = State()


class PurchaseState(StatesGroup):
    selecting_products = State()
    selecting_duration = State()
    selecting_payment = State()
    waiting_payment = State()


class BrandingBannerState(StatesGroup):
    waiting_photo = State()


class AutoBackupTokenState(StatesGroup):
    waiting_token = State()


class AutoBackupChatIdState(StatesGroup):
    waiting_chat_id = State()


class SettingsLicenseHostState(StatesGroup):
    waiting_host = State()


class DonateMessageState(StatesGroup):
    waiting_text = State()


class DonateBtnLabelState(StatesGroup):
    waiting_label = State()


class DonateBtnUrlState(StatesGroup):
    waiting_url = State()
