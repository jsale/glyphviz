"""
Converting a Twitter/X API v2 timeline into the archive's `tweets.js`.

The tool that builds `twitter_lab/demo_archives/` from a v2 scrape. What is
pinned here is the mapping's *consequences* rather than its field names: every
assertion goes through `tut.py`'s own reader and `classify()`/`measure()`,
because the only thing that matters about the conversion is that the reference
implementation reads the result the way it reads a real archive.

The load-bearing case is the media URL. v2 lists a post's own attached photo
under `entities.urls`, expanded to `.../status/<own id>/photo/1`; an archive
files media under `extended_entities` and leaves `entities.urls` for real
links. Passing them through was wrong twice over -- it inflated the links ring
AND, because the URL is a status URL, the quote-post inference read 538 of
CNN's 3,248 photo posts as quote posts.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

_LAB = Path(__file__).resolve().parent.parent / 'twitter_lab'
if str(_LAB) not in sys.path:
    sys.path.insert(0, str(_LAB))

import tut                                                   # noqa: E402
from v2_to_archive import (                                  # noqa: E402
    _entities, _ts, read_pages, to_archive_tweet, write_ytd,
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def v2_post(**over):
    """A minimal v2 post, overridable per test."""
    post = {
        "id": "1473159018189254659",
        "author_id": "759251",
        "created_at": "2021-12-21T05:10:54.000Z",
        "text": "A federal judge has ruled against a notable attempt.",
        "lang": "en",
        "source": "SocialFlow",
        "possibly_sensitive": False,
        "public_metrics": {"retweet_count": 29, "reply_count": 26,
                           "like_count": 122, "quote_count": 3},
    }
    post.update(over)
    return post


def url(expanded, start=0, end=23):
    return {"start": start, "end": end, "url": "https://t.co/xxxx",
            "expanded_url": expanded, "display_url": expanded[:20]}


def through_reader(tmp_path, posts, keywords=()):
    """Write the archive, then read it back the way tut.py reads a real one."""
    write_ytd(tmp_path / "tweets.js", "tweets",
              [{"tweet": to_archive_tweet(p)} for p in posts])
    return tut.load_archive(tmp_path, list(keywords), utc=True)


# --------------------------------------------------------------------------
# timestamps
# --------------------------------------------------------------------------

def test_timestamp_is_the_format_tut_parses():
    stamp = _ts("2021-12-21T05:10:54.000Z")
    assert stamp == "Tue Dec 21 05:10:54 +0000 2021"
    # The real check: tut.py's own format string has to accept it.
    back = datetime.strptime(stamp, tut.TWITTER_TS)
    assert back.isoformat() == "2021-12-21T05:10:54+00:00"


def test_timestamp_without_milliseconds_also_parses():
    assert _ts("2019-04-14T22:00:10Z") == "Sun Apr 14 22:00:10 +0000 2019"


# --------------------------------------------------------------------------
# the media-URL rule
# --------------------------------------------------------------------------

@pytest.mark.parametrize("expanded", [
    "https://twitter.com/CNN/status/1473058166221021188/video/1",
    "https://twitter.com/CNN/status/1473058166221021188/photo/1",
    "https://x.com/JLo/status/1441871952919007233/animated_gif/1",
    "https://www.twitter.com/CNN/status/1473058166221021188/photo/2",
])
def test_media_permalinks_are_dropped(expanded):
    ents = _entities({"entities": {"urls": [url(expanded)]}})
    assert ents["urls"] == []


@pytest.mark.parametrize("expanded", [
    "https://cnn.it/3mnfNK9",                                   # a real link
    "https://twitter.com/dolcegabbana/status/1441871952919007233",  # a quote
])
def test_real_links_survive(expanded):
    ents = _entities({"entities": {"urls": [url(expanded)]}})
    assert [u["expanded_url"] for u in ents["urls"]] == [expanded]


def test_photo_post_reads_as_an_original_with_no_links(tmp_path):
    """The whole reason the rule exists, checked where it is felt."""
    own = "https://twitter.com/CNN/status/1473058166221021188/photo/1"
    arch = through_reader(tmp_path, [v2_post(
        id="1473058166221021188",
        entities={"urls": [url(own)]},
    )])
    post, = arch.posts
    assert post.kind == "original"
    assert post.urls == 0


def test_quote_post_still_reads_as_a_quote(tmp_path):
    """An archive has no quote flag, so the inference is all there is."""
    arch = through_reader(tmp_path, [v2_post(
        text="✨✨✨ https://t.co/rLju6AFXIL",
        entities={"urls": [url("https://twitter.com/dolcegabbana/status/1441871952919007233")]},
        referenced_tweets=[{"type": "quoted", "id": "1441871952919007233"}],
    )])
    assert arch.posts[0].kind == "quote"
    assert arch.posts[0].urls == 1


# --------------------------------------------------------------------------
# the other three kinds
# --------------------------------------------------------------------------

def test_reply_carries_both_id_pairs_and_reads_as_a_reply(tmp_path):
    tweet = to_archive_tweet(v2_post(
        in_reply_to_user_id="759251",
        referenced_tweets=[{"type": "replied_to", "id": "1472685700323713031"}],
    ))
    assert tweet["in_reply_to_user_id"] == tweet["in_reply_to_user_id_str"] == "759251"
    assert (tweet["in_reply_to_status_id"] == tweet["in_reply_to_status_id_str"]
            == "1472685700323713031")
    assert tut.classify(tweet) == "reply"


def test_repost_reads_as_a_repost(tmp_path):
    arch = through_reader(tmp_path, [v2_post(text="RT @someone: a thing…")])
    assert arch.posts[0].kind == "retweet"


def test_plain_post_reads_as_an_original(tmp_path):
    assert through_reader(tmp_path, [v2_post()]).posts[0].kind == "original"


# --------------------------------------------------------------------------
# entities and metrics
# --------------------------------------------------------------------------

def test_entities_take_the_archive_names_and_string_indices():
    ents = _entities({"entities": {
        "hashtags": [{"start": 4, "end": 12, "tag": "GlowUp"}],
        "cashtags": [{"start": 0, "end": 5, "tag": "TWTR"}],
        "mentions": [{"start": 13, "end": 20, "username": "Sephora", "id": "1234"}],
        "urls": [url("https://cnn.it/3mnfNK9")],
    }})
    assert set(ents) == {"hashtags", "symbols", "user_mentions", "urls"}
    assert ents["hashtags"] == [{"text": "GlowUp", "indices": ["4", "12"]}]
    assert ents["symbols"] == [{"text": "TWTR", "indices": ["0", "5"]}]
    # v2 gives the handle but never the display name -- it lived in `includes`
    # -- so the handle stands in rather than a name being invented.
    assert ents["user_mentions"] == [{"name": "Sephora", "screen_name": "Sephora",
                                      "indices": ["13", "20"],
                                      "id_str": "1234", "id": "1234"}]


def test_all_four_entity_keys_are_written_even_when_empty():
    """An archive always states all four; a reader may index them blind."""
    ents = _entities({})
    assert ents == {"hashtags": [], "symbols": [], "user_mentions": [], "urls": []}


def test_metrics_survive_as_the_numbers_the_rings_draw(tmp_path):
    arch = through_reader(tmp_path, [v2_post(
        public_metrics={"like_count": 40008, "retweet_count": 5338,
                        "reply_count": 0, "quote_count": 0},
    )])
    post, = arch.posts
    assert (post.likes, post.reposts) == (40008, 5338)


def test_counts_are_written_as_strings_like_a_real_archive():
    tweet = to_archive_tweet(v2_post())
    assert tweet["favorite_count"] == "122"
    assert tweet["retweet_count"] == "29"
    assert tweet["id"] == tweet["id_str"] == "1473159018189254659"


# --------------------------------------------------------------------------
# reading the scrape
# --------------------------------------------------------------------------

def test_read_pages_pools_files_and_dedupes_by_id(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(
        {"data": [v2_post(id="1"), v2_post(id="2")], "meta": {}}), encoding="utf-8")
    # Some scrapes wrote a list of pages per file rather than one page.
    (tmp_path / "b.json").write_text(json.dumps(
        [{"data": [v2_post(id="2"), v2_post(id="3")], "meta": {}}]), encoding="utf-8")

    assert sorted(r["id"] for r in read_pages(tmp_path)) == ["1", "2", "3"]


def test_read_pages_refuses_a_folder_with_nothing_in_it(tmp_path):
    with pytest.raises(SystemExit):
        read_pages(tmp_path)


# --------------------------------------------------------------------------
# the file itself
# --------------------------------------------------------------------------

def test_nothing_precedes_the_assignment(tmp_path):
    """Both readers slice at the FIRST '=' in the file, so a banner comment
    ahead of the assignment -- or any '=' in one -- would break them."""
    path = tmp_path / "tweets.js"
    write_ytd(path, "tweets", [{"tweet": to_archive_tweet(v2_post())}])
    raw = path.read_text(encoding="utf-8")

    assert raw.startswith("window.YTD.tweets.part0 = ")
    assert raw.index("=") == raw.index("window.YTD.tweets.part0 =") + len(
        "window.YTD.tweets.part0 ")
    assert len(tut.unwrap(tut.read_ytd(path), "tweet")) == 1


def test_non_ascii_text_survives_the_round_trip(tmp_path):
    """One mangled byte silently drops labels downstream, so emoji and
    accents have to come back out exactly as they went in."""
    text = "5️⃣ 2️⃣ … ¡qué rico! \U0001f984"
    arch = through_reader(tmp_path, [v2_post(text=text)])
    assert arch.posts[0].text == text
