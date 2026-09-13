import json
import argparse
import contextlib
import io
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

        payload = json.loads(post.call_args.kwargs["data"])
        self.assertNotIn("body", payload)
        self.assertEqual(payload["markdown"].count("https://www.bohaishibei.com/post/"), 9)

    @patch.object(digest, "secret", return_value="test-key")
    @patch.object(digest.requests, "post")
    @patch.dict(digest.os.environ, {"PUBLIC_BASE_URL": "https://example.com/digest"})
    def test_bark_backlog_is_bounded_and_links_to_full_archive(self, post, _secret):
        post.return_value = Mock(status_code=200)
        articles = make_articles(170)
        archive = Path("public/archive/digest.html")

        self.assertTrue(digest.send_bark(articles, archive, Path("public")))

        kwargs = post.call_args.kwargs
        raw = kwargs.get("data") or json.dumps(kwargs["json"]).encode("utf-8")
        payload = json.loads(raw)
        self.assertLessEqual(len(raw), 4096)
        self.assertIn("170", payload["title"])
        self.assertEqual(payload["url"], "https://example.com/digest/archive/digest.html")
        self.assertIn(payload["url"], payload["markdown"])
        self.assertLess(payload["markdown"].count("https://www.bohaishibei.com/post/"), 170)

    @patch.object(digest, "fetch_digest_articles", return_value=make_articles(3))
    @patch.object(digest, "send_bark", side_effect=RuntimeError("413 Request Entity Too Large"))
    @patch.object(digest, "send_feishu", return_value=True)
    def test_partial_delivery_saves_checkpoint_and_does_not_resend(self, feishu, bark, fetch):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            args = argparse.Namespace(
                force_run=False, dry_run=False, min_run_interval_hours=0,
                state_path=root / "state.json", max_age_hours=48, max_pages=0,
                include_seen=False, limit=0, output_dir=root / "output",
                public_dir=root / "public", notify_empty=False,
                require_delivery=True, save_without_delivery=False,
                recover_without_notify=False,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(digest.run(args), 1)
                self.assertEqual(len(digest.load_seen(args.state_path)), 3)
                self.assertTrue((args.public_dir / "index.html").exists())
                self.assertEqual(digest.run(args), 0)
            self.assertEqual(feishu.call_count, 1)
            self.assertEqual(bark.call_count, 1)

    @patch.object(digest, "fetch_digest_articles", return_value=make_articles(170))
    @patch.object(digest, "send_bark")
    @patch.object(digest, "send_feishu")
    def test_recovery_archives_without_delivery_then_normal_run_has_no_backlog(self, feishu, bark, fetch):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            argv = ["digest", "--recover-without-notify", "--require-delivery",
                    "--state-path", str(root / "state.json"),
                    "--public-dir", str(root / "public"),
                    "--output-dir", str(root / "output")]
            with patch.object(digest.sys, "argv", argv):
                args = digest.parse_args()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(digest.run(args), 0)
                self.assertEqual(len(digest.load_seen(args.state_path)), 170)
                archives = list((args.public_dir / "archive").glob("*.html"))
                self.assertEqual(len(archives), 1)
                self.assertIn("/post/169/", archives[0].read_text())
                latest = (args.public_dir / "latest.html").read_bytes()
                args.recover_without_notify = False
                self.assertEqual(digest.run(args), 0)
                self.assertEqual((args.public_dir / "latest.html").read_bytes(), latest)
                self.assertEqual(list((args.public_dir / "archive").glob("*.html")), archives)
            bark.assert_not_called()
            feishu.assert_not_called()

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
