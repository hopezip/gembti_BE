"""app/game/client.py 단위 테스트

Steam API HTTP 호출을 mock으로 처리하므로 실제 네트워크 연결 불필요.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.game.client import (
    fetch_app_details,
    fetch_app_list,
    fetch_app_reviews,
    fetch_current_players,
)

# ── fetch_app_details ─────────────────────────────────────────────────────────


def _mock_client(json_body: dict, status_code: int = 200) -> httpx.AsyncClient:
    """httpx.AsyncClient.get 을 mock하는 헬퍼."""
    mock_response = MagicMock()
    mock_response.json.return_value = json_body
    mock_response.raise_for_status = MagicMock()
    if status_code >= 400:
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock()
        )

    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=mock_response)
    return client


@pytest.mark.asyncio
async def test_fetch_app_details_success():
    """type=game 인 앱은 data dict를 반환한다."""
    app_id = 730
    body = {
        str(app_id): {
            "success": True,
            "data": {
                "type": "game",
                "name": "Counter-Strike 2",
                "short_description": "FPS game",
                "header_image": "https://cdn.steam.com/cs2.jpg",
                "is_free": True,
                "genres": [{"id": "1", "description": "Action"}],
                "categories": [{"id": "2", "description": "Single-player"}],
                "supported_languages": "English, Korean",
            },
        }
    }
    client = _mock_client(body)
    result = await fetch_app_details(app_id, client)

    assert result is not None
    assert result["name"] == "Counter-Strike 2"
    assert result["type"] == "game"


@pytest.mark.asyncio
async def test_fetch_app_details_non_game_type_returns_none():
    """type != 'game' (DLC, movie 등) 은 None 반환."""
    app_id = 999
    body = {
        str(app_id): {
            "success": True,
            "data": {"type": "dlc", "name": "Some DLC"},
        }
    }
    client = _mock_client(body)
    result = await fetch_app_details(app_id, client)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_app_details_success_false_returns_none():
    """success=False 응답은 None 반환."""
    app_id = 111
    body = {str(app_id): {"success": False}}
    client = _mock_client(body)
    result = await fetch_app_details(app_id, client)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_app_details_http_error_returns_none():
    """HTTP 오류 시 None 반환 (예외 전파 없음)."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = httpx.ConnectError("timeout")

    result = await fetch_app_details(730, client)

    assert result is None


# ── fetch_app_list ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_app_list_single_page():
    """have_more_results=False → 한 페이지로 종료, app_id 목록 반환."""
    body = {
        "response": {
            "apps": [{"appid": 730}, {"appid": 570}, {"appid": 440}],
            "have_more_results": False,
        }
    }
    mock_response = MagicMock()
    mock_response.json.return_value = body
    mock_response.raise_for_status = MagicMock()

    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("app.game.client.httpx.AsyncClient", return_value=mock_client_instance):
        result = await fetch_app_list()

    assert result == [730, 570, 440]


@pytest.mark.asyncio
async def test_fetch_app_list_pagination():
    """have_more_results=True → last_appid로 다음 페이지 요청."""
    page1 = {
        "response": {
            "apps": [{"appid": 1}, {"appid": 2}],
            "have_more_results": True,
            "last_appid": 2,
        }
    }
    page2 = {
        "response": {
            "apps": [{"appid": 3}, {"appid": 4}],
            "have_more_results": False,
        }
    }

    responses = [page1, page2]
    call_count = 0

    async def mock_get(url, **kwargs):
        nonlocal call_count
        response = MagicMock()
        response.json.return_value = responses[call_count]
        response.raise_for_status = MagicMock()
        call_count += 1
        return response

    mock_client_instance = AsyncMock()
    mock_client_instance.get = mock_get
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("app.game.client.httpx.AsyncClient", return_value=mock_client_instance):
        result = await fetch_app_list()

    assert result == [1, 2, 3, 4]
    assert call_count == 2


@pytest.mark.asyncio
async def test_fetch_app_list_http_error_returns_empty():
    """HTTP 오류 시 빈 목록 반환 (break)."""
    mock_client_instance = AsyncMock()
    mock_client_instance.get.side_effect = httpx.ConnectError("error")
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("app.game.client.httpx.AsyncClient", return_value=mock_client_instance):
        result = await fetch_app_list()

    assert result == []


# ── fetch_app_reviews ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_app_reviews_success():
    """리뷰 통계 dict 반환."""
    summary = {
        "total_reviews": 100000,
        "total_positive": 95000,
        "total_negative": 5000,
    }
    body = {"query_summary": summary}
    client = _mock_client(body)

    result = await fetch_app_reviews(730, client)

    assert result == summary
    assert result["total_positive"] == 95000


@pytest.mark.asyncio
async def test_fetch_app_reviews_http_error_returns_none():
    """HTTP 오류 시 None 반환."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = httpx.ConnectError("timeout")

    result = await fetch_app_reviews(730, client)

    assert result is None


# ── fetch_current_players ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_current_players_success():
    """현재 접속자 수 int 반환."""
    body = {"response": {"player_count": 12345}}
    client = _mock_client(body)

    result = await fetch_current_players(730, client)

    assert result == 12345


@pytest.mark.asyncio
async def test_fetch_current_players_http_error_returns_none():
    """HTTP 오류 시 None 반환."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = httpx.ConnectError("timeout")

    result = await fetch_current_players(730, client)

    assert result is None
