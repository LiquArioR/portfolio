import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from datasource.database import Base
from datasource.mapper.game_web_mapper import GameWebMapper
from datasource.model.game_db import GameDB
from datasource.model.user_db import UserDB
from datasource.repository.game_repository import GameRepository
from domain.model.game import Game, GameStatus
from domain.service.auth_service import AuthService
from domain.service.game_service import GameService
from domain.service.jwt_provider import JwtProvider
from utils.password_hasher import PasswordHasher
from web.auth.user_authenticator import UserAuthenticator
from web.controller.auth_controller import AuthController
from web.controller.game_controller import GameController


class GameHistoryTest(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.service = GameService(GameRepository(self.session))
        self.user_id = "user-1"

        self.session.add_all([
            UserDB(user_id="user-1", login="alice", password_hash="hash"),
            UserDB(user_id="user-2", login="bob", password_hash="hash"),
            UserDB(user_id="user-3", login="carol", password_hash="hash"),
            UserDB(user_id="user-4", login="dave", password_hash="hash")
        ])
        self.session.commit()

        self._save_finished(self.user_id, "user-2", self.user_id)
        self._save_finished(self.user_id, "user-2", "user-2")
        self._save_finished(self.user_id, "user-2", None)
        self._save_finished("user-3", "user-4", None)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def _save_finished(self, player_x, player_o, winner):
        game = Game(player_x=player_x, player_o=player_o)
        game.status = GameStatus.DRAW if winner is None else GameStatus.WIN
        game.winner = winner
        self.service.repository.save(game)

    def test_repository_returns_only_users_wins_and_draws(self):
        games = self.service.get_completed_games(self.user_id)

        self.assertEqual(2, len(games))
        self.assertEqual({self.user_id, None}, {game.winner for game in games})
        self.assertTrue(all(
            self.user_id in (game.player_x, game.player_o)
            for game in games
        ))

    def test_leaderboard_returns_top_n_by_win_ratio(self):
        self._save_finished("user-1", "user-3", "user-1")

        leaders = self.service.get_leaderboard(2)

        self.assertEqual(["user-1", "user-2"], [
            leader.user_id for leader in leaders
        ])
        self.assertEqual(0.5, leaders[0].win_ratio)
        self.assertEqual("alice", leaders[0].login)

        all_leaders = self.service.get_leaderboard(10)
        self.assertEqual(4, len(all_leaders))
        self.assertEqual(0.0, all_leaders[-1].win_ratio)

        app = Flask(__name__)
        app.config["JWT_SECRET_KEY"] = "test-secret-with-at-least-32-bytes"
        JWTManager(app)
        authenticator = UserAuthenticator(object(), JwtProvider())
        controller = GameController(
            self.service,
            GameWebMapper(),
            authenticator
        )
        app.register_blueprint(controller.get_routes())
        client = app.test_client()

        self.assertEqual(401, client.get(
            "/api/game/leaderboard?n=2"
        ).status_code)

        with app.app_context():
            token = create_access_token(identity=self.user_id)

        response = client.get(
            "/api/game/leaderboard?n=2",
            headers={"Authorization": f"Bearer {token}"}
        )
        payload = response.get_json()

        self.assertEqual(200, response.status_code)
        self.assertEqual(2, payload["count"])
        self.assertEqual("alice", payload["leaders"][0]["login"])
        self.assertEqual(0.5, payload["leaders"][0]["win_ratio"])

    def test_login_returns_access_token_for_frontend(self):
        user = SimpleNamespace(
            id=self.user_id,
            login="anton",
            password_hash=PasswordHasher().hash_password("secret12")
        )

        class Users:
            @staticmethod
            def get_user_by_login(login):
                return user if login == user.login else None

        app = Flask(__name__)
        app.config["JWT_SECRET_KEY"] = "test-secret-with-at-least-32-bytes"
        JWTManager(app)
        service = AuthService(Users(), JwtProvider())
        app.register_blueprint(AuthController(service).get_routes())

        response = app.test_client().post(
            "/api/auth/login",
            json={"login": "anton", "password": "secret12"}
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("Bearer", payload["type"])
        self.assertEqual(self.user_id, payload["user_id"])
        self.assertTrue(payload["accessToken"])
        self.assertTrue(payload["refreshToken"])

    def test_history_endpoint_requires_bearer_access_token(self):
        app = Flask(__name__)
        app.config["JWT_SECRET_KEY"] = "test-secret-with-at-least-32-bytes"
        JWTManager(app)

        authenticator = UserAuthenticator(object(), JwtProvider())
        controller = GameController(
            self.service,
            GameWebMapper(),
            authenticator
        )
        app.register_blueprint(controller.get_routes())

        client = app.test_client()
        self.assertEqual(401, client.get("/api/game/history").status_code)
        self.assertEqual(
            401,
            client.get(
                "/api/game/history",
                headers={"Authorization": "Basic dXNlcjpwYXNz"}
            ).status_code
        )

        with app.app_context():
            token = create_access_token(identity=self.user_id)

        response = client.get(
            "/api/game/history",
            headers={"Authorization": f"Bearer {token}"}
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual(2, payload["count"])
        self.assertTrue(all("created_at" in game for game in payload["games"]))


if __name__ == "__main__":
    unittest.main()
