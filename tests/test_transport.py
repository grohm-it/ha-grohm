"""Trasporto HTTP vero (aiohttp) contro un server GraphQL locale finto."""

from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from custom_components.grohm.api import (
    GrohmApi,
    GrohmConnectionError,
    GrohmUnsupportedAccountError,
    create_session,
)


@pytest.fixture
async def server(socket_enabled):
    state = {"account_type": "0", "status": 200}

    async def graphql(request: web.Request) -> web.Response:
        if state["status"] != 200:
            return web.Response(status=state["status"], text="<html>504</html>")
        body = await request.json()
        query = body["query"]
        if "mutation Login" in query:
            resp = web.json_response(
                {
                    "data": {
                        "login": {
                            "__typename": "LoginSuccess",
                            "user": {
                                "id": "7",
                                "email": "x",
                                "accountType": state["account_type"],
                            },
                        }
                    }
                }
            )
            resp.set_cookie("sessionid", "abc", httponly=True)
            resp.set_cookie("csrftoken", "tok")
            return resp
        if "mutation Logout" in query:
            resp = web.json_response({"data": {"logout": True}})
            resp.del_cookie("sessionid")
            return resp
        if request.cookies.get("sessionid") != "abc":
            if "query Me" in query:
                return web.json_response({"data": {"me": None}})
            return web.json_response(
                {"data": None, "errors": [{"message": "Not authenticated"}]}, status=403
            )
        assert request.headers.get("X-CSRFToken") == "tok"
        if "query Me" in query:
            return web.json_response(
                {
                    "data": {
                        "me": {
                            "id": "7",
                            "email": "x",
                            "accountType": state["account_type"],
                        }
                    }
                }
            )
        if "query MyDevices" in query:
            return web.json_response(
                {
                    "data": {
                        "myDevices": {
                            "items": [{"id": "9"}],
                            "pageInfo": {"hasNextPage": False},
                        }
                    }
                }
            )
        return web.json_response({"data": None, "errors": [{"message": "unexpected"}]})

    app = web.Application()
    app.router.add_post("/graphql", graphql)
    srv = TestServer(app, host="localhost")  # CookieJar ignora i cookie degli IP
    await srv.start_server()
    yield srv, state
    await srv.close()


async def test_cookie_session_and_relogin(server):
    srv, _ = server
    session = create_session()
    api = GrohmApi(session, "a@b.it", "pw", endpoint=str(srv.make_url("/graphql")))
    try:
        await api.login()
        assert await api.device_ids() == ["9"]
        session.cookie_jar.clear()  # cookie perso/scaduto → 403 → nuovo login
        assert await api.device_ids() == ["9"]
    finally:
        await session.close()


async def test_installer_refused_over_http(server):
    srv, state = server
    state["account_type"] = "2"
    session = create_session()
    api = GrohmApi(session, "a@b.it", "pw", endpoint=str(srv.make_url("/graphql")))
    try:
        with pytest.raises(GrohmUnsupportedAccountError):
            await api.login()
        assert not any(c.key == "sessionid" and c.value for c in session.cookie_jar)
    finally:
        await session.close()


async def test_gateway_error(server):
    srv, state = server
    state["status"] = 504
    session = create_session()
    api = GrohmApi(session, "a@b.it", "pw", endpoint=str(srv.make_url("/graphql")))
    try:
        with pytest.raises(GrohmConnectionError):
            await api.login()
    finally:
        await session.close()
