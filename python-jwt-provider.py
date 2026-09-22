from typing import Optional

from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_jwt_in_request,
    get_jwt_identity
)


class JwtProvider:
    """
    Провайдер JWT-токенов.

    Отвечает за:
    - создание access token;
    - создание refresh token;
    - проверку access token;
    - проверку refresh token;
    - получение UUID пользователя из токена.
    """

    # =========================================================
    # ACCESS TOKEN
    # =========================================================

    def generate_access_token(self, user) -> str:
        """
        Создаёт access token.

        В identity сохраняется UUID пользователя.
        """

        return create_access_token(
            identity=str(user.id)
        )

    # =========================================================
    # REFRESH TOKEN
    # =========================================================

    def generate_refresh_token(self, user) -> str:
        """
        Создаёт refresh token.

        В identity сохраняется UUID пользователя.
        """

        return create_refresh_token(
            identity=str(user.id)
        )

    # =========================================================
    # VALIDATE ACCESS TOKEN
    # =========================================================

    def validate_access_token(self, token: str) -> bool:
        """
        Проверяет access token.

        Возвращает:
        True  - токен корректный
        False - токен неправильный/просрочен
        """

        try:

            decoded = decode_token(token)

            return decoded.get("type") == "access"

        except Exception as e:

            print(
                f"[DEBUG] Invalid access token: {e}"
            )

            return False

    # =========================================================
    # VALIDATE REFRESH TOKEN
    # =========================================================

    def validate_refresh_token(self, token: str) -> bool:
        """
        Проверяет refresh token.
        """

        try:

            decoded = decode_token(token)

            return decoded.get("type") == "refresh"

        except Exception as e:

            print(
                f"[DEBUG] Invalid refresh token: {e}"
            )

            return False

    # =========================================================
    # GET UUID FROM TOKEN
    # =========================================================

    def get_uuid_from_token(
        self,
        token: str
    ) -> Optional[str]:
        """
        Получает UUID пользователя из JWT.
        """

        try:

            decoded = decode_token(token)

            return decoded.get("sub")

        except Exception as e:

            print(
                f"[DEBUG] Cannot get UUID from token: {e}"
            )

            return None

    # =========================================================
    # GET UUID FROM CURRENT REQUEST
    # =========================================================

    def get_uuid_from_request(self) -> Optional[str]:
        """
        Получает UUID пользователя из текущего
        Authorization: Bearer <accessToken>
        """

        try:

            verify_jwt_in_request()

            return str(
                get_jwt_identity()
            )

        except Exception as e:

            print(
                f"[DEBUG] JWT request validation failed: {e}"
            )

            return None