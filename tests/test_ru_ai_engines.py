"""Fork tests: Russian AI engines (Yandex Alice AI).

Sources (checked 2026-11-04):
- yandex.ru/support/webmaster/ru/robot-workings/check-yandex-robots —
  YandexAdditional / YandexAdditionalBot are robots.txt tokens that limit
  showing page content in YandexGPT quick answers and Alice search answers.
- yandex.ru/support/webmaster/ru/robot-workings/user-agent — a group for the
  exact robot name wins over `User-agent: Yandex`, which wins over `*`;
  when a Yandex group exists, `*` is not used by Yandex robots.
"""

from __future__ import annotations

from geo_optimizer.core.audit_platform import audit_platform_citation
from geo_optimizer.models.config import AI_BOTS, BOT_TIERS
from geo_optimizer.models.results import (
    CitabilityResult,
    ContentResult,
    LlmsTxtResult,
    MetaResult,
    RobotsResult,
    SchemaResult,
    SignalsResult,
)
from geo_optimizer.utils.robots_parser import classify_bot, parse_robots_txt


def _status(bot: str, robots_txt: str):
    return classify_bot(bot, "", parse_robots_txt(robots_txt))


class TestYandexGroupMatching:
    def test_yandex_group_applies_to_yandex_bots_instead_of_wildcard(self):
        robots = "User-agent: Yandex\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
        status = _status("YandexAdditional", robots)
        assert status.status == "blocked"
        assert status.matched_agent == "Yandex"
        assert status.via_wildcard is False

    def test_exact_robot_group_wins_over_yandex_group(self):
        robots = "User-agent: Yandex\nDisallow: /\n\nUser-agent: YandexBot\nAllow: /\n"
        assert _status("YandexBot", robots).status == "allowed"
        assert _status("YandexAdditional", robots).status == "blocked"

    def test_yandex_group_does_not_affect_other_vendors(self):
        robots = "User-agent: Yandex\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
        status = _status("GPTBot", robots)
        assert status.status == "allowed"
        assert status.via_wildcard is True

    def test_yandex_bot_falls_back_to_wildcard_without_yandex_group(self):
        status = _status("YandexBot", "User-agent: *\nDisallow: /\n")
        assert status.status == "blocked"
        assert status.via_wildcard is True


class TestYandexBotsRegistered:
    def test_yandex_bots_are_checked(self):
        for bot in ("YandexBot", "YandexAdditional", "YandexAdditionalBot"):
            assert bot in AI_BOTS

    def test_yandex_bots_are_search_tier(self):
        assert {"YandexBot", "YandexAdditional", "YandexAdditionalBot"} <= BOT_TIERS["search"]


def _alice(robots: RobotsResult, **kw):
    result = audit_platform_citation(
        robots=robots,
        llms=LlmsTxtResult(),
        schema=kw.get("schema", SchemaResult()),
        meta=kw.get("meta", MetaResult()),
        content=kw.get("content", ContentResult()),
        citability=kw.get("citability", CitabilityResult()),
        signals=SignalsResult(),
    )
    return next(p for p in result.platforms if p.platform == "yandex_alice")


class TestYandexAlicePlatform:
    def test_open_site_scores_above_site_that_hides_from_alice(self):
        open_site = _alice(RobotsResult(found=True, bots_allowed=["YandexBot", "YandexAdditional"]))
        hidden = _alice(RobotsResult(found=True, bots_allowed=["YandexBot"], bots_blocked=["YandexAdditional"]))
        assert open_site.score > hidden.score

    def test_blocked_alice_token_is_the_first_recommendation(self):
        hidden = _alice(RobotsResult(found=True, bots_allowed=["YandexBot"], bots_blocked=["YandexAdditionalBot"]))
        assert "YandexAdditional" in hidden.recommendations[0]

    def test_blocked_yandexbot_is_reported(self):
        blocked = _alice(RobotsResult(found=True, bots_blocked=["YandexBot"]))
        assert any("YandexBot" in r for r in blocked.recommendations)

    def test_fragment_ready_content_raises_score(self):
        robots = RobotsResult(found=True, bots_allowed=["YandexBot", "YandexAdditional"])
        rich = _alice(
            robots,
            schema=SchemaResult(any_schema_found=True, has_faq=True, has_organization=True),
            meta=MetaResult(has_title=True, has_description=True, has_canonical=True),
            content=ContentResult(has_h1=True, word_count=800),
            citability=CitabilityResult(total_score=75),
        )
        bare = _alice(robots)
        assert rich.score > bare.score
        assert rich.score <= 100


def _robots_fix(**robots_kw):
    from geo_optimizer.core.fixer import generate_robots_fix
    from geo_optimizer.models.results import AuditResult

    result = AuditResult(url="https://example.ru", robots=RobotsResult(found=True, **robots_kw))
    return generate_robots_fix(result, "https://example.ru")


class TestRobotsFixLeavesYandexGroupsAlone:
    """A `User-agent: YandexBot` group replaces the whole `User-agent: Yandex`
    group for that robot, dropping its Disallow and Clean-param rules, so the
    fixer must never append Yandex groups to an existing robots.txt."""

    def test_only_yandex_bots_to_fix_gives_no_fix(self):
        assert _robots_fix(bots_blocked=["YandexBot", "YandexAdditional"]) is None

    def test_yandex_bots_are_dropped_from_mixed_append(self):
        fix = _robots_fix(bots_missing=["GPTBot"], bots_blocked=["YandexBot"])
        assert "User-agent: GPTBot" in fix.content
        assert "Yandex" not in fix.content
