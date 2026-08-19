"""MdDesk v0.6 AI Provider layer tests (plan §3.1 / §3.4 / §6).

Covers:
  * AIProviderConfig: defaults, timeout normalization, sanitized describe()
  * ClientFactory: the ONLY client construction path; unsupported provider
    raises ProviderConfigError; timeout + max_retries=0 reach the OpenAI SDK
  * Connection test matrix: success / DNS-connect failure / HTTP auth
    failure / timeout / malformed response / rate limit / client build error
  * Secret handling: the API key and Authorization header NEVER appear in
    any test result message (they must never reach UI / logs / reports)

Run: python tests/test_v06_provider.py   (or: pytest tests/test_v06_provider.py)
Qt-free, network-free (fake clients), headless.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import openai  # noqa: E402

from src.ai_provider import (  # noqa: E402
    AIProviderConfig,
    CAPABILITY_IMAGE_DESCRIPTION,
    CAPABILITY_OCR,
    ClientFactory,
    ConnectionTestResult,
    ProviderConfigError,
    SUPPORTED_CAPABILITIES,
    SUPPORTED_PROVIDERS,
    test_connection as probe_connection,
)
from src.settings import (  # noqa: E402
    AI_TIMEOUT_DEFAULT_SECONDS,
    PROVIDER_OPENAI_COMPATIBLE,
)

SECRET = "sk-VERY-SECRET-KEY-1234567890"


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


# --------------------------------------------------------------------------- #
# Fake OpenAI-compatible client / response                                    #
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, code: int):
        self.status_code = code
        self.headers = {}
        self.request = None
        self.is_success = False


class _Msg:
    def __init__(self, c):
        self.content = c


class _Choice:
    def __init__(self, c):
        self.message = _Msg(c)


class _Resp:
    def __init__(self, c="pong"):
        self.choices = [_Choice(c)]


def _err(kind: str, message: str = "err"):
    if kind == "auth":
        return openai.AuthenticationError(message=message, response=_FakeResp(401), body=None)
    if kind == "permission":
        return openai.PermissionDeniedError(message=message, response=_FakeResp(403), body=None)
    if kind == "ratelimit":
        return openai.RateLimitError(message=message, response=_FakeResp(429), body=None)
    if kind == "badrequest":
        return openai.BadRequestError(message=message, response=_FakeResp(400), body=None)
    if kind == "notfound":
        return openai.NotFoundError(message=message, response=_FakeResp(404), body=None)
    if kind == "connection":
        return openai.APIConnectionError(message=message, request=None)
    if kind == "timeout":
        return openai.APITimeoutError(request=None)
    if kind == "status":
        return openai.InternalServerError(message=message, response=_FakeResp(500), body=None)
    raise ValueError(kind)


class FakeClient:
    """chat.completions.create returns a canned response or raises."""

    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc
        self.calls = []

        client = self

        class _Completions:
            def create(self, model=None, messages=None, **kw):
                client.calls.append({"model": model, "messages": messages, **kw})
                if client._exc is not None:
                    raise client._exc
                if client._result is Exception:  # malformed: no .choices
                    return object()
                return client._result

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


class _BoomFactory:
    """A client factory that fails to build the client."""

    def __call__(self, config):
        raise RuntimeError(f"cannot build client for {config.endpoint}")


# --------------------------------------------------------------------------- #
# 1. Provider config model                                                    #
# --------------------------------------------------------------------------- #
def test_provider_config_model():
    ok = True
    cfg = AIProviderConfig()
    ok &= _check("1a. 默认 provider = openai-compatible",
                 cfg.provider == PROVIDER_OPENAI_COMPATIBLE, cfg.provider)
    ok &= _check("1b. 默认 timeout = 60s",
                 cfg.timeout_seconds == AI_TIMEOUT_DEFAULT_SECONDS, cfg.timeout_seconds)
    ok &= _check("1c. timeout 越界被钳制 (0 -> min)",
                 AIProviderConfig(timeout_seconds=0).timeout_seconds == 1.0)
    ok &= _check("1d. timeout 越界被钳制 (99999 -> max)",
                 AIProviderConfig(timeout_seconds=99999).timeout_seconds == 600.0)
    ok &= _check("1e. 非法 timeout 回退默认 (str)",
                 AIProviderConfig(timeout_seconds="abc").timeout_seconds == 60.0)
    ok &= _check("1f. describe() 不含 API Key",
                 SECRET not in AIProviderConfig(api_key=SECRET, endpoint="https://x/v1",
                                                model="gpt-4o").describe())
    ok &= _check("1g. describe() 清理带密 URL",
                 "key=" not in AIProviderConfig(
                     endpoint="https://x/v1?key=" + SECRET).describe())
    ok &= _check("1h. capability 词表 = {ocr, image_description}",
                 set(SUPPORTED_CAPABILITIES) == {CAPABILITY_OCR, CAPABILITY_IMAGE_DESCRIPTION})
    ok &= _check("1i. provider 词表仅 openai-compatible",
                 SUPPORTED_PROVIDERS == (PROVIDER_OPENAI_COMPATIBLE,))
    assert ok


# --------------------------------------------------------------------------- #
# 2. Client factory                                                           #
# --------------------------------------------------------------------------- #
def test_client_factory():
    ok = True
    try:
        ClientFactory.create(AIProviderConfig(provider="claude"))
        ok &= _check("2a. 不支持的 provider 报错", False, "no exception")
    except ProviderConfigError:
        ok &= _check("2a. 不支持的 provider 报错", True)
    except Exception as e:  # noqa: BLE001
        ok &= _check("2a. 不支持的 provider 报错", False, repr(e))

    cfg = AIProviderConfig(api_key=SECRET, endpoint="https://gw.example/v1",
                           model="gpt-4o", timeout_seconds=12.5)
    client = ClientFactory.create(cfg)
    ok &= _check("2b. 构建 OpenAI 客户端成功", client is not None)
    ok &= _check("2c. base_url 传入", str(client.base_url).startswith("https://gw.example"), )
    ok &= _check("2d. timeout 传入",
                 float(client.timeout) == 12.5, client.timeout)
    ok &= _check("2e. max_retries=0（timeout 为硬上限）",
                 getattr(client, "max_retries", -1) == 0, getattr(client, "max_retries", None))
    # Client construction must not leak the key in any exception/str form we
    # later log: verify the client does not stringify the key.
    ok &= _check("2f. client repr 不含 key", SECRET not in repr(client))
    assert ok


# --------------------------------------------------------------------------- #
# 3. Connection test matrix (plan §3.4 / §6 Connection)                       #
# --------------------------------------------------------------------------- #
def _probe(client=None, factory=None, **kw):
    cfg = AIProviderConfig(api_key=kw.pop("api_key", SECRET),
                           endpoint=kw.pop("endpoint", "https://gw.example/v1"),
                           model=kw.pop("model", "gpt-4o"), **kw)
    return probe_connection(cfg, client=client, client_factory=factory)


def test_connection_matrix():
    ok = True

    # success
    r = _probe(client=FakeClient(result=_Resp("pong")))
    ok &= _check("3a. success -> ok", r.ok, r.message)
    ok &= _check("3b. success 消息含模型名", "gpt-4o" in r.message, r.message)
    ok &= _check("3c. success 记录耗时", r.duration_ms >= 0)

    # DNS / connect failure
    r = _probe(client=FakeClient(exc=_err("connection")))
    ok &= _check("3d. 连接失败 -> 不 ok", not r.ok, r.message)
    ok &= _check("3e. 连接失败消息可理解", "无法连接" in r.message, r.message)

    # HTTP auth failure
    r = _probe(client=FakeClient(exc=_err("auth", message="bad key " + SECRET)))
    ok &= _check("3f. 鉴权失败 -> 不 ok", not r.ok)
    ok &= _check("3g. 鉴权失败消息含 401 提示", "401" in r.message, r.message)

    # timeout
    r = _probe(client=FakeClient(exc=_err("timeout")))
    ok &= _check("3h. 超时 -> 不 ok", not r.ok)
    ok &= _check("3i. 超时消息可理解", "超时" in r.message, r.message)

    # malformed response (200 but no choices)
    r = _probe(client=FakeClient(result=Exception))
    ok &= _check("3j. 畸形响应 -> 不 ok", not r.ok, r.message)
    ok &= _check("3k. 畸形响应消息提及格式", "格式" in r.message or "choices" in r.message)

    # rate limit = service reachable & authenticated
    r = _probe(client=FakeClient(exc=_err("ratelimit")))
    ok &= _check("3l. 限流(429) 报告服务可达", "429" in r.message and ("可用" in r.message), r.message)

    # model not found
    r = _probe(client=FakeClient(exc=_err("notfound")))
    ok &= _check("3m. 404 -> 不 ok 且提示检查模型/Endpoint",
                 (not r.ok) and ("模型" in r.message or "Endpoint" in r.message), r.message)

    # unsupported provider
    r = probe_connection(AIProviderConfig(provider="claude", model="x"))
    ok &= _check("3n. 不支持的 provider -> 不 ok", not r.ok and "Provider" in r.message)

    # client build failure
    r = _probe(factory=_BoomFactory())
    ok &= _check("3o. 客户端构建失败 -> 不 ok 且不抛异常", not r.ok, r.message)
    assert ok


# --------------------------------------------------------------------------- #
# 4. Connection test never raises + secrets never leak                        #
# --------------------------------------------------------------------------- #
def test_connection_never_raises_and_no_secret_leak():
    ok = True
    leaky = openai.APIConnectionError(
        message=f"GET https://gw.example/v1?key={SECRET} Authorization=Bearer {SECRET}",
        request=None,
    )
    results = [
        _probe(client=FakeClient(exc=leaky)),
        _probe(client=FakeClient(exc=RuntimeError(f"api_key={SECRET} token={SECRET}"))),
        _probe(client=FakeClient(exc=_err("auth", message="Bearer " + SECRET))),
        _probe(factory=_BoomFactory()),
        probe_connection(AIProviderConfig(provider="claude", model="m")),
        probe_connection(AIProviderConfig(api_key=SECRET, model="m",
                                           endpoint="https://x/v1?token=" + SECRET)),
    ]
    for i, r in enumerate(results):
        ok &= _check(f"4{i}. 结果对象合法", isinstance(r, ConnectionTestResult))
        blob = r.message + r.endpoint + r.to_dict().__str__()
        ok &= _check(f"4{i}b. 消息/endpoint 不含 secret", SECRET not in blob,
                     blob[:120])
    # And the probe always terminates with a duration.
    ok &= _check("4x. 所有探测均有 duration", all(r.duration_ms >= 0 for r in results))
    assert ok


def _main():
    ok = True
    ok &= test_provider_config_model()
    ok &= test_client_factory()
    ok &= test_connection_matrix()
    ok &= test_connection_never_raises_and_no_secret_leak()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_main())
