from packages.core.errors import ForbiddenError


class TelegramAuthorizer:
    def __init__(self, authorized_user_ids: set[int]) -> None:
        self._authorized = authorized_user_ids

    def is_authorized(self, telegram_user_id: int) -> bool:
        return telegram_user_id in self._authorized

    def require_authorized(self, telegram_user_id: int) -> None:
        if not self.is_authorized(telegram_user_id):
            raise ForbiddenError(
                "Usuario de Telegram no autorizado",
                details={"telegram_user_id": telegram_user_id},
            )
