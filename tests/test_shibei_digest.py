import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import shibei_digest as digest


def make_articles(count: int) -> list[digest.Article]:
    return [
        digest.Article(
            title=f"标题 {index} " + "很长" * 50,
            url=f"https://www.bohaishibei.com/post/{index}/",
            published=None,
            summary="摘要内容 " + "说明" * 120,
            category=("科技", "生活", "其他")[index % 3],
        )
        for index in range(count)
    ]


class NotificationRegressionTests(unittest.TestCase):
    def test_selection_counts_apply_no_cap_after_filtering(self) -> None:
        window_start = digest.dt.datetime(2026, 8, 13, tzinfo=digest.dt.timezone.utc)
        articles = make_articles(3) + [
            digest.Article(
                title="广告优惠",
                url="https://www.bohaishibei.com/post/ad/",
                published=None,
                summary="推广",
                category="商业",
            )
        ]

        counts = digest.selection_counts(articles, set(), window_start, include_seen=False)
        selected = digest.select_new_articles(articles, set(), window_start, include_seen=False)

        self.assertEqual(counts["fetched"], 4)
        self.assertEqual(counts["excluded"], 1)
        self.assertEqual(counts["selected_before_limit"], 3)
        self.assertEqual(len(selected), counts["selected_before_limit"])

    def test_feishu_payloads_keep_every_article_link_under_limit(self) -> None:
        articles = make_articles(100)
        payloads = digest.feishu_payloads(articles, Path("digest.html"), None)

        links = [
            node["href"]
            for payload in payloads
            for paragraph in payload["content"]["post"]["zh_cn"]["content"]
            for node in paragraph
            if node.get("tag") == "a" and node.get("text") == "原文"
        ]

        self.assertGreater(len(payloads), 1)
        self.assertEqual({article.url for article in articles}, set(links))
        self.assertEqual(len(articles), len(links))
        for payload in payloads:
            self.assertLessEqual(digest.feishu_payload_bytes(payload), digest.FEISHU_MAX_PAYLOAD_BYTES)

    @patch.object(digest, "secret", return_value="test-key")
    @patch.object(digest.requests, "post")
    def test_bark_markdown_contains_links_for_displayed_articles(
        self, post: Mock, _secret: Mock
    ) -> None:
        response = Mock(status_code=200)
        post.return_value = response
        articles = make_articles(9)

        self.assertTrue(digest.send_bark(articles, Path("digest.html"), None))

        payload = post.call_args.kwargs["json"]
        self.assertNotIn("body", payload)
        self.assertEqual(payload["markdown"].count("https://www.bohaishibei.com/post/"), 9)

    def test_feishu_payload_is_compact_utf8_json(self) -> None:
        articles = make_articles(29)
        payload = digest.feishu_payloads(articles, Path("digest.html"), None)[0]
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

        self.assertEqual(len(encoded), digest.feishu_payload_bytes(payload))
        self.assertLess(len(encoded), 20_000)

    def test_unique_stamp_does_not_overwrite_same_second_archive(self) -> None:
        generated_at = digest.dt.datetime(2026, 8, 13, 12, 34, 56, tzinfo=digest.dt.timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            (directory / "shibei-digest-2026-08-13-123456.html").write_text("first")
            (directory / "shibei-digest-2026-08-13-123456.md").write_text("first")

            self.assertEqual(
                digest.unique_stamp(directory, generated_at),
                "2026-08-13-123456-01",
            )


if __name__ == "__main__":
    unittest.main()
