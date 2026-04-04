from bot.keyboards.common import server_status, PERIOD_LABELS
from bot.keyboards.admin import (
    main_menu_kb, clients_kb, server_detail_kb, compose_kb,
    period_kb, add_period_kb, cancel_kb,
)
from bot.keyboards.user import (
    user_servers_kb, user_server_kb,
    user_view_servers_kb, user_view_server_kb, user_view_empty_kb,
    user_main_menu_kb,
)
from bot.keyboards.settings import (
    settings_kb, sync_kb, setting_edit_kb, setting_edit_pending_kb,
    backup_kb, payments_kb, gateway_detail_kb,
    gateway_placement_kb, gateway_currency_kb,
)
from bot.keyboards.purchase import (
    product_selection_kb, purchase_duration_kb, payment_method_kb,
)
