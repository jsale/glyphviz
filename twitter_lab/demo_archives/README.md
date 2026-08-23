# Demo archives

Two archives anyone can build a Timeline Tower from without having to ask X
for their own, which takes a day or two and is personal when it arrives.

| Zip | Posts | Span | What it shows |
|---|---|---|---|
| `TUT_demo_CNN.zip` | 3,248 | 13 Nov – 21 Dec 2021 | a newsroom firehose: five weeks, one post every 15 minutes, a hard daily rhythm on the bearing ring |
| `TUT_demo_JLo.zip` | 3,218 | Apr 2019 – Dec 2021 | two and a half years and all four post kinds in quantity — the one that shows what the needle colours mean, and the one to try `helix` on |

They are deliberately a contrasting pair: one is a **short dense** record where
the tower's shape is the working day, the other a **long sparse** one where the
shape is the calendar.

Each zip unpacks to a folder holding a `data` directory, exactly like a real X
archive, so the instructions are the same ones the docs already give:

```text
python tut.py --archive TUT_demo_CNN/data --out .
```

or drop that `data` folder onto `tut_designer.html`.

## These are not X archive downloads

They were rebuilt from public Twitter/X **API v2** timeline scrapes into the
archive's file format by [`../v2_to_archive.py`](../v2_to_archive.py):

```text
python v2_to_archive.py --timeline <scrape>/CNN --out demo_archives/TUT_demo_CNN/data \
       --username CNN --display-name "CNN" --timezone "Eastern Time (US & Canada)"
python v2_to_archive.py --timeline <scrape>/JLo --out demo_archives/TUT_demo_JLo/data \
       --username JLo --display-name "Jennifer Lopez" --timezone "Pacific Time (US & Canada)"
```

Every post was public when it was collected in December 2021. The scrapes are
not in this repo; the converter's docstring is the record of exactly what the
mapping does with each field.

**Two limits the v2 API imposes and the conversion cannot lift**, both stated in
each archive's own `README.txt` as well:

- **A repost's text is truncated** by the API at ~140 characters — 74 of CNN's
  78 reposts, 823 of JLo's 1,516. Time, kind and counts are exact; the
  character-derived rings (uppercase, special characters) measure the
  truncation. Every post either account actually wrote is complete.
- **Media attachments are absent** — v2 reports them by key into an `includes`
  block the scrapes did not keep.

The `account-timezone.js` in each is an **editorial addition**: a v2 timeline
carries no zone, and reading CNN's day in UTC would shift the whole clock face
five hours. Deleting that file, or ticking UTC, reads the tower in UTC.

## Why the working copies are not committed

The unpacked folders are gitignored and the zips are what ship — the same deal
as the big GTDB and cyclone scenes. `tweets.js` is 3.4 MB for CNN and 4.2 MB
for JLo; the zips are a quarter of that.

## Verified

Both archives were read back through `tut.py`'s own loader and then through
`parity_check.mjs`, which runs the designer page's real JavaScript against the
script's CSV. All six combinations — two accounts × three layouts — pass
identical on every column of every node (~22k nodes each), so what a user
downloads from the page matches what the script builds from the same files.

Classification was checked against v2's `referenced_tweets`, which is ground
truth the archive format has no room for: CNN agrees on all 3,248 posts, and
JLo on 3,167 of 3,218. The 51 are posts that link to someone else's tweet
without formally quoting it, which the documented inference calls a quote — a
real archive of the same account would say the same.
