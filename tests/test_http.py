import httpx
import pytest

from carparts.http import PoliteClient, RobotsDisallowed, RobotsRules, SourceBlocked

ROBOTS = """
User-agent: *
Disallow: /sch/
Disallow: /*?q=*
Allow: /sch/allowed$
Disallow: /search

User-agent: carpartshunter
Disallow: /private
"""


def test_wildcards_and_longest_match():
    rules = RobotsRules(ROBOTS, agent_token="someotherbot")
    assert not rules.allowed("/sch/i.html?_nkw=x")
    assert rules.allowed("/sch/allowed")
    assert not rules.allowed("/sch/allowed/more")
    assert not rules.allowed("/list?q=bumper")
    assert rules.allowed("/shop/q-bmw+g20")
    assert not rules.allowed("/search?q=x")


def test_specific_group_wins():
    rules = RobotsRules(ROBOTS)
    assert rules.allowed("/sch/i.html")
    assert not rules.allowed("/private/x")


def _client(handler):
    return PoliteClient(storage=None, default_delay=0, transport=httpx.MockTransport(handler))


def test_client_respects_robots_and_stops_on_403():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /blocked\n")
        if request.url.path == "/forbidden":
            return httpx.Response(403, text="no")
        return httpx.Response(200, text="<html><title>ok</title></html>")

    c = _client(handler)
    assert c.get("https://site.test/ok").status == 200
    with pytest.raises(RobotsDisallowed):
        c.get("https://site.test/blocked/page")
    with pytest.raises(SourceBlocked):
        c.get("https://site.test/forbidden")


def test_captcha_page_is_blocked():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text="<html><head><title>Are you a robot?</title></head></html>")

    with pytest.raises(SourceBlocked):
        _client(handler).get("https://site.test/x")
