import pytest

from app.steam.client import (
    SteamLibraryPayloadError,
    SteamLibraryVisibility,
    parse_owned_games_payload,
)


def test_parse_owned_games_payload_accepts_matching_game_count() -> None:
    result = parse_owned_games_payload(
        {
            "response": {
                "game_count": 2,
                "games": [{"appid": 10}, {"appid": 20}],
            }
        }
    )

    assert result.visibility == SteamLibraryVisibility.PUBLIC
    assert result.game_count == 2
    assert [game["appid"] for game in result.games] == [10, 20]


def test_parse_owned_games_payload_rejects_count_mismatch() -> None:
    with pytest.raises(SteamLibraryPayloadError, match="게임 수 불일치"):
        parse_owned_games_payload(
            {
                "response": {
                    "game_count": 2,
                    "games": [{"appid": 10}],
                }
            }
        )


def test_parse_owned_games_payload_rejects_duplicate_app_ids() -> None:
    with pytest.raises(SteamLibraryPayloadError, match="중복 AppID"):
        parse_owned_games_payload(
            {
                "response": {
                    "game_count": 2,
                    "games": [{"appid": 10}, {"appid": 10}],
                }
            }
        )


def test_parse_owned_games_payload_handles_public_empty_library() -> None:
    result = parse_owned_games_payload({"response": {"game_count": 0}})

    assert result.visibility == SteamLibraryVisibility.EMPTY
    assert result.game_count == 0
    assert result.games == []
