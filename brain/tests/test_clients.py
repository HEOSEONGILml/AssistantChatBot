import asyncio
from types import SimpleNamespace

import pytest

from brain import clients


def test_to_readout_reads_all_four_answers():
    resp = SimpleNamespace(
        choices={"action": SimpleNamespace(probabilities={"beg": 1.0}),
                 "change": SimpleNamespace(probabilities={"변화없음": 1.0}),
                 "command": SimpleNamespace(probabilities={"sit": 0.9, "none": 0.1})},
        nouls={"speak": SimpleNamespace(noul=0.4), "user_down": SimpleNamespace(noul=0.7), "soothe": SimpleNamespace(noul=0.2),
               "hush": SimpleNamespace(noul=0.1)},
    )
    assert clients.to_readout(resp) == clients.Readout({"beg": 1.0}, 0.4, {"변화없음": 1.0}, 0.7, 0.2, 0.1, {"sit": 0.9, "none": 0.1})


async def test_jev_unexpected_shape_becomes_call_error(monkeypatch):
    jev = clients.TypeSafeJev("k", timeout_s=1)
    async def odd(**kwargs):
        return SimpleNamespace(choices={}, nouls={})
    monkeypatch.setattr(jev._client, "system_one", odd)
    with pytest.raises(clients.CallError):
        await jev.judge({})
    await jev.aclose()


@pytest.mark.parametrize("code,message,expected", [
    (401, "unauthorized", True),
    (403, "forbidden", True),
    (400, "API key not valid. Please pass a valid API key.", True),
    (400, "Invalid argument", False),
    (500, "internal", False),
    (None, None, False),
])
def test_gemini_auth_error_detection(code, message, expected):
    assert clients.is_gemini_auth_error(code, message) is expected


async def test_jev_timeout_becomes_call_error(monkeypatch):
    jev = clients.TypeSafeJev("k", timeout_s=0.01)
    async def slow(**kwargs):
        await asyncio.sleep(1)
    monkeypatch.setattr(jev._client, "system_one", slow)
    with pytest.raises(clients.CallError):
        await jev.judge({"상황": "x"})
    await jev.aclose()


async def test_jev_unexpected_error_becomes_call_error(monkeypatch):
    jev = clients.TypeSafeJev("k", timeout_s=1)
    async def boom(**kwargs):
        raise RuntimeError("network")
    monkeypatch.setattr(jev._client, "system_one", boom)
    with pytest.raises(clients.CallError):
        await jev.judge({})
    await jev.aclose()


async def test_gemini_timeout_becomes_call_error(monkeypatch):
    talker = clients.GeminiTalker("k", timeout_s=0.01)
    async def slow(**kwargs):
        await asyncio.sleep(1)
    monkeypatch.setattr(talker._client.aio.models, "generate_content", slow)
    with pytest.raises(clients.CallError):
        await talker.say("sys", "prompt")
    await talker.aclose()


async def test_gemini_returns_text(monkeypatch):
    talker = clients.GeminiTalker("k", timeout_s=1)
    seen = {}
    async def fake(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(text="멍! 안녕")
    monkeypatch.setattr(talker._client.aio.models, "generate_content", fake)
    assert await talker.say("sys", "prompt") == "멍! 안녕"
    assert seen["model"] == clients.GEMINI_MODEL and seen["contents"] == "prompt"
    await talker.aclose()


def test_readout_has_owner_down_default():
    from brain.clients import Readout
    assert Readout({}, 0.5, {}).user_down == 0.0
