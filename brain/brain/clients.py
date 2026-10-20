"""외부 AI 호출 계층 (CLAUDE.md 3절). 실패를 AuthError(키 문제)와 CallError(일시적 실패) 두 가지로 정리해
두뇌 핵심이 SDK 예외를 몰라도 되게 한다. 사용법은 Context7로 확인했다 (2026-10-15)."""
import asyncio
from dataclasses import dataclass
from typing import Protocol

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from typesafe_sdk import (AsyncTypeSafeClient, RetryPolicy, TypeSafeAuthenticationError,
                          TypeSafePermissionDeniedError)

from .questions import QUESTIONS
from .tuning import Tuning

GEMINI_MODEL = "gemini-3.1-flash-lite"  # 0007


class AuthError(Exception):
    """키가 틀렸다. 키를 다시 넣을 때까지 AI 호출을 멈춘다."""


class CallError(Exception):
    """일시적 실패(네트워크, 시간 초과, 서버 오류). 이번 판단만 건너뛴다."""


@dataclass(frozen=True)
class Readout:
    """Jev가 준 분포 (두뇌 스펙 v2 5절). 결정은 확률 모델이 한다."""
    action: dict[str, float]
    speak: float
    change: dict[str, float]  # 글이 일으키는 기분의 분포: 기분 9개 + 없음 (0019)


def to_readout(resp) -> Readout:
    return Readout(dict(resp.choices["action"].probabilities), resp.nouls["speak"].noul,
                   dict(resp.choices["change"].probabilities))


class Jev(Protocol):
    async def judge(self, state: dict) -> Readout: ...
    async def aclose(self) -> None: ...


class Talker(Protocol):
    async def say(self, system: str, prompt: str) -> str: ...
    async def aclose(self) -> None: ...


class TypeSafeJev:
    def __init__(self, api_key: str, timeout_s: float):
        # 재시도는 하지 않는다: 늦은 판단은 쓸모가 없고, 다음 트리거가 곧 다시 부른다
        self._client = AsyncTypeSafeClient(api_key=api_key, timeout=timeout_s, retry=RetryPolicy(max_retries=0))
        self._timeout = timeout_s

    async def judge(self, state: dict) -> Readout:
        try:
            resp = await asyncio.wait_for(self._client.system_one(state=state, questions=QUESTIONS), self._timeout)
            return to_readout(resp)
        except (TypeSafeAuthenticationError, TypeSafePermissionDeniedError) as e:
            raise AuthError("typesafe") from e
        except Exception as e:
            raise CallError(f"jev {type(e).__name__}") from e

    async def aclose(self) -> None:
        await self._client.aclose()


def is_gemini_auth_error(code: int | None, message: str | None) -> bool:
    # Gemini는 틀린 키에 400 "API key not valid"를 돌려주기도 한다
    return code in (401, 403) or (code == 400 and "API key" in (message or ""))


class GeminiTalker:
    def __init__(self, api_key: str, timeout_s: float):
        self._client = genai.Client(api_key=api_key)
        self._timeout = timeout_s

    async def say(self, system: str, prompt: str) -> str:
        try:
            resp = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=GEMINI_MODEL, contents=prompt,
                    config=genai_types.GenerateContentConfig(system_instruction=system)),
                self._timeout)
        except genai_errors.APIError as e:
            if is_gemini_auth_error(e.code, e.message):
                raise AuthError("gemini") from e
            raise CallError(f"gemini {e.code}") from e
        except Exception as e:
            raise CallError(f"gemini {type(e).__name__}") from e
        return resp.text or ""

    async def aclose(self) -> None:
        await self._client.aio.aclose()


def make_clients(keys: dict[str, str | None], tuning: Tuning) -> tuple[TypeSafeJev, GeminiTalker]:
    return (TypeSafeJev(keys["typesafe"] or "", tuning.jev_timeout_s),
            GeminiTalker(keys["gemini"] or "", tuning.gemini_timeout_s))
