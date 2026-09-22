import json
from typing import Optional

from sqlalchemy import (
    Float,
    and_,
    case,
    cast,
    func,
    or_,
    select,
    union_all
)
from sqlalchemy.orm import Session

from domain.model.game import Game
from domain.model.leaderboard_entry import LeaderboardEntry
from datasource.model.game_db import GameDB
from datasource.model.user_db import UserDB
from datasource.mapper.game_mapper import GameMapper


class GameRepository:

    def __init__(self, db_session: Session):
        self.db = db_session
        self.mapper = GameMapper()

    def save(self, game: Game) -> Game:
        try:
            existing = (
                self.db
                .query(GameDB)
                .filter(GameDB.game_id == game.id)
                .first()
            )

            if existing:
                existing.player_x = game.player_x
                existing.player_o = game.player_o
                existing.is_computer_opponent = game.is_computer_opponent
                existing.current_player = game.current_player

                # SQLite требует NOT NULL.
                existing.winner = game.winner or ""

                existing.is_finished = game.is_finished()
                existing.updated_at = game.updated_at
                existing.board_cells = json.dumps(game.board.matrix)
                existing.board_size = game.board.size

                self.db.commit()
                self.db.refresh(existing)

                print(
                    f"[DEBUG] Game updated: "
                    f"id={existing.game_id}, "
                    f"is_computer_opponent={existing.is_computer_opponent}"
                )

                return self.mapper.db_to_domain(existing)

            else:
                game_db = self.mapper.domain_to_db(game)

                self.db.add(game_db)
                self.db.commit()
                self.db.refresh(game_db)

                print(
                    f"[DEBUG] Game saved: "
                    f"id={game_db.game_id}, "
                    f"is_computer_opponent={game_db.is_computer_opponent}"
                )

                return self.mapper.db_to_domain(game_db)

        except Exception as e:
            self.db.rollback()

            print(f"[ERROR] GameRepository.save error: {e}")

            raise

    def get_by_id(self, game_id: str) -> Optional[Game]:
        try:
            game_db = (
                self.db
                .query(GameDB)
                .filter(GameDB.game_id == game_id)
                .first()
            )

            if not game_db:
                return None

            return self.mapper.db_to_domain(game_db)

        except Exception:
            self.db.rollback()
            raise

    def get_all(self) -> list:
        try:
            games_db = self.db.query(GameDB).all()

            return [
                self.mapper.db_to_domain(game_db)
                for game_db in games_db
            ]

        except Exception:
            self.db.rollback()
            raise

    def get_completed_by_user_id(self, user_id: str) -> list[Game]:
        """Возвращает победы пользователя и его игры, завершившиеся вничью."""
        try:
            games_db = (
                self.db
                .query(GameDB)
                .filter(
                    and_(
                        or_(
                            GameDB.player_x == user_id,
                            GameDB.player_o == user_id
                        ),
                        GameDB.is_finished.is_(True),
                        or_(
                            GameDB.winner == user_id,
                            GameDB.winner == "",
                            GameDB.winner.is_(None)
                        )
                    )
                )
                .order_by(GameDB.created_at.desc())
                .all()
            )

            return [
                self.mapper.db_to_domain(game_db)
                for game_db in games_db
            ]

        except Exception:
            self.db.rollback()
            raise

    def get_leaderboard(self, limit: int) -> list[LeaderboardEntry]:
        """Возвращает пользователей с наибольшей долей побед."""
        participants = union_all(
            select(
                GameDB.player_x.label("user_id"),
                GameDB.winner.label("winner")
            ).where(GameDB.is_finished.is_(True)),
            select(
                GameDB.player_o.label("user_id"),
                GameDB.winner.label("winner")
            ).where(
                and_(
                    GameDB.is_finished.is_(True),
                    GameDB.player_o.is_not(None)
                )
            )
        ).subquery()

        wins = func.coalesce(func.sum(
            case(
                (participants.c.winner == participants.c.user_id, 1),
                else_=0
            )
        ), 0)
        completed_games = func.count(participants.c.user_id)
        win_ratio = case(
            (
                completed_games > 0,
                cast(wins, Float) / cast(completed_games, Float)
            ),
            else_=0.0
        )

        rows = (
            self.db
            .query(
                UserDB.user_id,
                UserDB.login,
                win_ratio.label("win_ratio"),
                wins.label("wins")
            )
            .outerjoin(
                participants,
                participants.c.user_id == UserDB.user_id
            )
            .group_by(UserDB.user_id, UserDB.login)
            .order_by(
                win_ratio.desc(),
                wins.desc(),
                UserDB.login.asc()
            )
            .limit(limit)
            .all()
        )

        return [
            LeaderboardEntry(
                user_id=row.user_id,
                login=row.login,
                win_ratio=round(float(row.win_ratio), 4)
            )
            for row in rows
        ]
