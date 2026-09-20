import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient

from app import auth, jobs, main
from app.db import session_key
from app.settings import settings


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.operations = []

    def hset(self, key, mapping):
        self.operations.append(lambda: self.redis.hashes.setdefault(key, {}).update(mapping))
        return self

    def expire(self, key, seconds):
        self.operations.append(lambda: self.redis.expirations.__setitem__(key, seconds))
        return self

    def lpush(self, key, value):
        self.operations.append(lambda: self.redis.lists.setdefault(key, []).insert(0, value))
        return self

    def incr(self, key):
        def operation():
            value = int(self.redis.values.get(key, "0")) + 1
            self.redis.values[key] = str(value)
            return value

        self.operations.append(operation)
        return self

    def execute(self):
        return [operation() for operation in self.operations]


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.hashes = {}
        self.lists = {}
        self.expirations = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, seconds, value):
        self.values[key] = value
        self.expirations[key] = seconds

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            existed = key in self.values or key in self.hashes
            self.values.pop(key, None)
            self.hashes.pop(key, None)
            self.expirations.pop(key, None)
            deleted += int(existed)
        return deleted

    def pipeline(self):
        return FakePipeline(self)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def getdel(self, key):
        return self.values.pop(key, None)

    def ping(self):
        return True


@pytest.fixture
def client(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(auth, "r", fake)
    monkeypatch.setattr(jobs, "r", fake)
    monkeypatch.setattr(main, "r", fake)
    monkeypatch.setattr(settings, "app_password", "test-mochi")
    monkeypatch.setattr(settings, "login_max_attempts", 8)
    with TestClient(main.app) as test_client:
        yield test_client, fake


def login(client):
    return client.post("/auth/login", json={"password": "test-mochi"})


def valid_job():
    return {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}


def test_login_correcto_creates_persistent_session(client):
    test_client, fake = client

    response = login(test_client)

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}
    token = response.cookies.get(settings.session_cookie_name)
    assert token
    assert fake.get(session_key(token)) == "authenticated"
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Max-Age=2592000" in set_cookie


def test_login_incorrecto_no_crea_sesion(client):
    test_client, fake = client

    response = test_client.post("/auth/login", json={"password": "incorrecta"})

    assert response.status_code == 401
    assert not response.cookies.get(settings.session_cookie_name)
    assert not any(key.startswith("session:") for key in fake.values)


def test_endpoint_protegido_sin_sesion(client):
    test_client, _ = client

    response = test_client.post("/v1/jobs", json=valid_job())

    assert response.status_code == 401


def test_endpoint_protegido_con_sesion(client):
    test_client, _ = client
    assert login(test_client).status_code == 200

    response = test_client.post("/v1/jobs", json=valid_job())

    assert response.status_code == 202
    assert response.json()["status"] == "queued"


def test_logout_invalida_la_sesion(client):
    test_client, fake = client
    assert login(test_client).status_code == 200
    token = test_client.cookies.get(settings.session_cookie_name)

    response = test_client.post("/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"authenticated": False}
    assert fake.get(session_key(token)) is None
    assert test_client.get("/auth/me").json() == {"authenticated": False}
    assert test_client.post("/v1/jobs", json=valid_job()).status_code == 401


def test_sesion_expirada_o_inexistente_es_rechazada(client):
    test_client, fake = client
    assert login(test_client).status_code == 200
    token = test_client.cookies.get(settings.session_cookie_name)
    fake.delete(session_key(token))

    assert test_client.get("/auth/me").json() == {"authenticated": False}
    assert test_client.get("/v1/jobs/nonexistent").status_code == 401


def test_rate_limit_basico_del_login(client, monkeypatch):
    test_client, _ = client
    monkeypatch.setattr(settings, "login_max_attempts", 2)

    assert test_client.post("/auth/login", json={"password": "no"}).status_code == 401
    assert test_client.post("/auth/login", json={"password": "no"}).status_code == 401
    response = test_client.post("/auth/login", json={"password": "test-mochi"})

    assert response.status_code == 429
    assert response.headers["retry-after"] == str(settings.login_window_seconds)


def test_la_contrasena_no_se_devuelve_y_la_ui_no_expone_detalles_tecnicos(client):
    test_client, _ = client
    password = settings.app_password

    responses = [
        test_client.get("/"),
        test_client.get("/auth/me"),
        test_client.post("/auth/login", json={"password": password}),
    ]

    for response in responses:
        assert password not in response.text

    html = responses[0].text.lower()
    for forbidden in ("api token", "bearer", "api_key", "authorization"):
        assert forbidden not in html


def test_egress_requires_session_and_does_not_expose_proxy(client, monkeypatch):
    test_client, _ = client
    monkeypatch.setattr(settings, "download_egress", "residential")
    monkeypatch.setattr(
        settings,
        "residential_proxy",
        SecretStr("socks5h://user:password@100.64.0.10:1080"),
    )
    monkeypatch.setattr(main, "residential_proxy_reachable", lambda: True)

    assert test_client.get("/v1/egress").status_code == 401
    assert login(test_client).status_code == 200

    response = test_client.get("/v1/egress")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "residential",
        "configured": True,
        "reachable": True,
    }
    assert "100.64.0.10" not in response.text
    assert "user:password" not in response.text
