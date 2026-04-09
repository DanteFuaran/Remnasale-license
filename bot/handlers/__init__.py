from aiogram import Router

from bot.handlers.start import router as start_router
from bot.handlers.clients import router as clients_router
from bot.handlers.user import router as user_router
from bot.handlers.purchase import router as purchase_router
from bot.handlers.settings import router as settings_router
from bot.handlers.payments_admin import router as payments_admin_router
from bot.handlers.compose import router as compose_router
from bot.handlers.backup import router as backup_router
from bot.handlers.install import router as install_router
from bot.handlers.catch_all import router as catch_all_router


def setup_routers(dp_or_router: Router):
    dp_or_router.include_router(start_router)
    dp_or_router.include_router(clients_router)
    dp_or_router.include_router(user_router)
    dp_or_router.include_router(purchase_router)
    dp_or_router.include_router(settings_router)
    dp_or_router.include_router(payments_admin_router)
    dp_or_router.include_router(compose_router)
    dp_or_router.include_router(backup_router)
    dp_or_router.include_router(install_router)
    # catch_all must be last
    dp_or_router.include_router(catch_all_router)
