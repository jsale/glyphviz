#!/usr/bin/env python3
"""Turn a folder of paginated Twitter/X **API v2** timeline JSON into the
`tweets.js` an X **archive** contains — the file `tut.py` and the TUT Designer
read.

Why this exists: the Designer needs an archive, and an archive is personal.
This makes a shareable demo out of a public account's v2 timeline instead, and
it is how `twitter_lab/demo_archives/` was built.  It is not specific to those
two accounts: point it at any folder of v2 pages.

    python v2_to_archive.py --timeline DIR --out DIR [--display-name NAME]
                            [--timezone "Eastern Time (US & Canada)"]

Input: a folder of `*.json` files, each holding one or more v2 pages —
`{"data": [ ...tweets... ], "meta": {...}}` — in any pagination order.  Rows
are pooled across every file and de-duplicated by post id.

Output: `tweets.js`, plus `account.js` and `account-timezone.js` when the
information for them was given.

## What the mapping can and cannot carry

The v2 timeline is **poorer than an archive** in two ways that survive into the
demo, and both are stated here rather than papered over:

- **A repost's text is truncated by the API.**  v2 returns a repost as
  `"RT @who: ..."` cut at ~140 characters and ending in an ellipsis; the full
  text lived in an `includes` block these scrapes did not keep.  Kind, time and
  counts are exact, but a repost's character-derived rings (uppercase, special
  characters) measure the truncation, not the post.  Originals, replies and
  quotes — every post the account actually wrote — are complete.
- **There are no media entities.**  v2 reports media by key into an `includes`
  block, so a photo post converts as if it carried no attachment.  This does
  not touch the links ring: an archive does not list media t.co links under
  `entities.urls` either — it files them under `extended_entities`, which is
  why `_entities()` drops them rather than passing them through.  Leaving them
  in was measurably wrong twice over: it inflated the links ring, and because
  a v2 media URL expands to the post's OWN `.../status/<id>/photo/1`, the
  quote-post inference read 538 of CNN's 3,248 photo posts as quotes.

Everything else the tower reads maps exactly: `id`, `created_at`, `text`,
`public_metrics.like_count`/`retweet_count`, hashtags, urls, mentions, and the
reply ids.  Quote posts need no special handling — the archive has no
quote flag and `classify()` infers one from a status link in `entities.urls`,
which v2 supplies for every quote (verified: 372 of 372 in the JLo scrape).

`source` is passed through as the plain v2 string ("SocialFlow"), where an
archive holds an HTML anchor.  Inventing the anchor's URL would be inventing
data, and nothing downstream reads the field.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

# The one format an archive writes a timestamp in, and the one `tut.py` parses
# with `%a %b %d %H:%M:%S %z %Y`.  An archive always states it in UTC.
ARCHIVE_TS = "%a %b %d %H:%M:%S +0000 %Y"


# ---------------------------------------------------------------------------
# Reading the scrape
# ---------------------------------------------------------------------------

def read_pages(timeline_dir: Path) -> list[dict]:
    """Pool every v2 page in a folder into one de-duplicated list of posts."""
    files = sorted(timeline_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"No .json files in {timeline_dir}")

    by_id: dict[str, dict] = {}
    for path in files:
        blob = json.loads(path.read_text(encoding="utf-8"))
        pages = blob if isinstance(blob, list) else [blob]
        for page in pages:
            if not isinstance(page, dict):
                continue
            for row in page.get("data", []) or []:
                if isinstance(row, dict) and row.get("id"):
                    by_id[row["id"]] = row

    if not by_id:
        raise SystemExit(f"{len(files)} file(s) read from {timeline_dir}, but "
                         f"none held a 'data' array of posts.")
    return list(by_id.values())


# ---------------------------------------------------------------------------
# v2 -> archive
# ---------------------------------------------------------------------------

def _ts(created_at: str) -> str:
    """`2021-12-21T05:10:54.000Z` -> `Tue Dec 21 05:10:54 +0000 2021`."""
    when = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return when.astimezone(timezone.utc).strftime(ARCHIVE_TS)


# A t.co link to the post's own attached photo/video/GIF.  v2 lists these
# alongside real links in `entities.urls`; an archive files them under
# `extended_entities` instead, so they must not survive the conversion.  The
# `/photo/1` style suffix is what makes one unambiguous — a quote post's URL
# is a bare `.../status/<id>` and never carries it.
_MEDIA_URL = re.compile(
    r"^https?://(?:www\.)?(?:twitter|x)\.com/[^/]+/status/\d+/"
    r"(?:photo|video|animated_gif)/\d+", re.I)


def _indices(item: dict) -> list[str]:
    """An archive writes entity offsets as strings, so match it."""
    return [str(item.get("start", 0)), str(item.get("end", 0))]


def _entities(v2: dict) -> dict:
    """v2 `entities` -> the archive's four-key shape.

    Both shapes carry the same facts under different names: v2's `mentions`
    are an archive's `user_mentions`, and its `cashtags` are `symbols`.  An
    archive always writes all four keys, empty or not.
    """
    ents = v2.get("entities") or {}

    hashtags = [{"text": h.get("tag", ""), "indices": _indices(h)}
                for h in ents.get("hashtags", [])]
    symbols = [{"text": c.get("tag", ""), "indices": _indices(c)}
               for c in ents.get("cashtags", [])]
    urls = [{"url": u.get("url", ""),
             "expanded_url": u.get("expanded_url", u.get("url", "")),
             "display_url": u.get("display_url", ""),
             "indices": _indices(u)}
            for u in ents.get("urls", [])
            if not _MEDIA_URL.match(u.get("expanded_url", ""))]

    # v2 gives a mention's handle but not the account's display name, which
    # only ever lived in `includes`.  The handle stands in for it rather than
    # a name being made up.
    mentions = []
    for m in ents.get("mentions", []):
        handle = m.get("username", "")
        entry = {"name": handle, "screen_name": handle,
                 "indices": _indices(m)}
        if m.get("id"):
            entry["id_str"] = str(m["id"])
            entry["id"] = str(m["id"])
        mentions.append(entry)

    return {"hashtags": hashtags, "symbols": symbols,
            "user_mentions": mentions, "urls": urls}


def to_archive_tweet(v2: dict) -> dict:
    """One v2 post as the object an archive nests under `"tweet"`."""
    text = v2.get("text", "")
    metrics = v2.get("public_metrics") or {}

    tweet = {
        "retweeted": False,
        "source": v2.get("source", ""),
        "entities": _entities(v2),
        # An archive counts this in UTF-16 units, which is what wrote it.
        "display_text_range": ["0", str(len(text))],
        "favorite_count": str(metrics.get("like_count", 0)),
        "id_str": str(v2["id"]),
        "truncated": False,
        "retweet_count": str(metrics.get("retweet_count", 0)),
        "id": str(v2["id"]),
        "created_at": _ts(v2["created_at"]),
        "favorited": False,
        "full_text": text,
        "lang": v2.get("lang", ""),
    }
    if "possibly_sensitive" in v2:
        tweet["possibly_sensitive"] = bool(v2["possibly_sensitive"])

    # A reply is the one kind the archive flags outright, and both readers
    # check the flag before they look at anything else.
    if v2.get("in_reply_to_user_id"):
        uid = str(v2["in_reply_to_user_id"])
        tweet["in_reply_to_user_id"] = uid
        tweet["in_reply_to_user_id_str"] = uid
    for ref in v2.get("referenced_tweets") or []:
        if ref.get("type") == "replied_to" and ref.get("id"):
            sid = str(ref["id"])
            tweet["in_reply_to_status_id"] = sid
            tweet["in_reply_to_status_id_str"] = sid

    return tweet


# ---------------------------------------------------------------------------
# Writing the archive files
# ---------------------------------------------------------------------------
# Every file in an archive is JavaScript, not JSON: one `window.YTD.<name>.partN
# = [ ... ]` assignment.  Both readers slice at the FIRST '=' in the file, so
# nothing may precede the assignment — no comment, no banner.  What the demo
# needs to say about itself is said in the README beside it.

def write_ytd(path: Path, name: str, rows: list[dict]) -> None:
    body = json.dumps(rows, indent=2, ensure_ascii=False)
    path.write_text(f"window.YTD.{name}.part0 = {body}\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeline", required=True, type=Path,
                    help="folder of paginated v2 *.json pages for one account")
    ap.add_argument("--out", required=True, type=Path,
                    help="folder to write tweets.js (and friends) into")
    ap.add_argument("--username", default=None,
                    help="@handle for account.js (default: the folder's name)")
    ap.add_argument("--display-name", default=None,
                    help="display name for account.js (default: the handle)")
    ap.add_argument("--timezone", default=None, metavar="NAME",
                    help="write account-timezone.js with this zone, e.g. "
                         "'Eastern Time (US & Canada)'.  The v2 timeline does "
                         "NOT carry a zone; supplying one is an editorial "
                         "choice, so say so wherever the result is published.")
    ap.add_argument("--no-account", action="store_true",
                    help="write only tweets.js")
    args = ap.parse_args()

    rows = read_pages(args.timeline)
    username = args.username or args.timeline.name
    display = args.display_name or username

    # Newest first, the order an archive itself is written in.
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    tweets = [{"tweet": to_archive_tweet(r)} for r in rows]

    args.out.mkdir(parents=True, exist_ok=True)
    write_ytd(args.out / "tweets.js", "tweets", tweets)

    if not args.no_account:
        author_ids = {r.get("author_id") for r in rows if r.get("author_id")}
        account = {"username": username, "accountDisplayName": display}
        if len(author_ids) == 1:
            account["accountId"] = author_ids.pop()
        write_ytd(args.out / "account.js", "account", [{"account": account}])

        if args.timezone:
            write_ytd(args.out / "account-timezone.js", "accountTimezone",
                      [{"accountTimezone": {"timeZone": args.timezone}}])

    span = (_ts(rows[-1]["created_at"]), _ts(rows[0]["created_at"]))
    reposts = sum(1 for r in rows if r.get("text", "").startswith("RT @"))
    truncated = sum(1 for r in rows
                    if r.get("text", "").startswith("RT @")
                    and r["text"].rstrip().endswith("…"))
    size = (args.out / "tweets.js").stat().st_size

    print(f"{username}: {len(tweets)} posts  ({size/1_048_576:.1f} MB)")
    print(f"  {span[0]}  ->  {span[1]}")
    print(f"  reposts: {reposts}, of which API-truncated text: {truncated}")
    print(f"  wrote {args.out}")


if __name__ == "__main__":
    main()
