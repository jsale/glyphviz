"""Your data in GlyphViz: from a spreadsheet to a scene (City Climate Rings).

The workflow lesson for new users: a flat table -> a prompt to Claude with the
glyphviz skill -> the scene it writes -> dropped onto a real (never shown)
MainWindow through the app's own drop handler, MainWindow.apply_drop.

Everything shown is real:
  * the table is examples/City_Climate_Rings_Example/city_climate.csv, fetched
    by fetch_climate.py from NASA POWER (daily, 2001-2020, averaged by month);
  * the prompt is prompt.md, and the scene is what build_climate_rings.py
    (Claude's generator for that prompt, built with the skill) writes, into
    this lesson's out/ folder at render time; the generator verifies its
    geometry through GlyphViz's engine and refuses to write a scene that
    disagrees.

Filming trick, and the one thing a viewer can't do from the default view: the
orbit camera's "up" is always world +Z, so a ring on a city at latitude 19
has its bars pointing sideways across the screen. So the GLOBE turns instead
(it is an ordinary rotatable node): Euler XYZ (0, -(90 - lat), -lon) brings a
city to the top of the globe, measured through the engine, and from azimuth 0
that shows north up and east right -- January at the top of every clock.
"""
import sys
from pathlib import Path

from glyphviz_core.node import ROTATION_MODE_EULER_XYZ
from lessonkit import (Callout, Key, Lesson, Shot, text_card, AMBER, BG, CHALK, CORAL,
                       TEAL, ease)
from lessons._common import world

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "examples" / "City_Climate_Rings_Example"
sys.path.insert(0, str(DATA))
import build_climate_rings as gen  # noqa: E402

GRID = 2
TOP = (0.0, 0.0, 180.0)          # just above the city a pose brings to the top
CITIES = {}                       # name -> (lat, lon)


def _scene_ids():
    """Node ids by label, from the generator itself (it is deterministic)."""
    data = gen.load_data()
    rows = gen.build(data)
    for city, g in data.groupby("city", sort=False):
        CITIES[city] = (float(g.lat.iloc[0]), float(g.lon.iloc[0]))
    return data, rows, {r["text"]: r["id"] for r in rows}


def pose(city):
    lat, lon = CITIES[city]
    return (-(90.0 - lat), -lon)          # (rotate_y, rotate_z)


def turn(a, b, u0=0.08, u1=0.72):
    """Rotate the globe from pose a to pose b across part of the shot."""
    pa = a if isinstance(a, tuple) else pose(a)
    pb = pose(b)

    def animate(L, u):
        g = L.node(GRID)
        if g is None:
            return
        k = ease((u - u0) / (u1 - u0))
        g.rotation_mode = ROTATION_MODE_EULER_XYZ
        g.rotate_x = 0.0
        g.rotate_y = pa[0] + (pb[0] - pa[0]) * k
        g.rotate_z = pa[1] + (pb[1] - pa[1]) * k
    return animate


def close(u, az=0.0, el=38.0, dist=64.0):
    return Key(u, az=az, el=el, dist=dist, target=TOP)


def build() -> Lesson:
    data, rows, _ids = _scene_ids()
    f = gen.fmt

    def val(city, month):
        return data[(data.city == city) & (data.month == month)].iloc[0]

    def at(city, month, kind):
        """A node id by the generator's own label. The rain column's hidden
        top and its Link share a label, so they are told apart by type."""
        r = val(city, month)
        where = f"{city} · {month}"
        key = {"bead": f"{where} · mean {f(r.mean_c)}",
               "high": f"{where} · high {f(r.high_c)}",
               "rain": f"{where} · rain {int(r.precip_mm)} mm",
               "rainbar": f"{where} · rain {int(r.precip_mm)} mm"}[kind]
        want = 7 if kind == "rainbar" else 5
        return next(r_["id"] for r_ in rows if r_["text"] == key and r_["type"] == want)

    mj, mm = val("Moscow", "Jul"), val("Mumbai", "Jul")
    moscow_jul_temp = f"July: {mj.low_c:.0f} to {mj.high_c:.0f} °C"
    moscow_jul_mm = f"July rain: {int(mj.precip_mm)} mm"
    mumbai_jul_mm = f"July: {int(mm.precip_mm)} mm"

    scene_dir = {}

    def prepare(lesson, out: Path):
        scene_dir["path"] = gen.write_scene(out / "City_Climate_Rings").parent

    def drop(L):
        # Exactly what a drag-and-drop of the folder does in the app.
        L.win.apply_drop([str(scene_dir["path"])])
        L.vp.selected_node_ids = set()

    # --- the three "before the app" cards, all from the real files
    head = "city          month  high_c  low_c  precip_mm"
    table = [head]
    for _, r in data.head(6).iterrows():
        table.append(f"{r.city:<13} {r.month:<5} {r.high_c:>6.1f} {r.low_c:>6.1f} {r.precip_mm:>9}")
    table.append("…")
    last = data.iloc[-1]
    table.append(f"{last.city:<13} {last.month:<5} {last.high_c:>6.1f} {last.low_c:>6.1f} {last.precip_mm:>9}")
    prompt = (DATA / "prompt.md").read_text(encoding="utf-8").split("---", 1)[1].strip()
    import textwrap
    prompt_lines = []
    for para in prompt.split("\n\n"):
        prompt_lines += textwrap.wrap(" ".join(para.split()), 62) + [""]
    n_nodes = len(rows)
    files = ["City_Climate_Rings/",
             f"  climate_rings_gv_node.csv    {n_nodes:,} rows",
             "  media/01_bluemarble.png      the globe's map",
             "",
             "checked with GlyphViz's own engine:",
             "  31 clock faces, January north, running clockwise",
             "  every bar upright, every length exact"]

    moscow_jan, moscow_jul = at("Moscow", "Jan", "bead"), at("Moscow", "Jul", "bead")
    moscow_jul_hi = at("Moscow", "Jul", "high")
    moscow_jul_rain = at("Moscow", "Jul", "rain")
    mumbai_jul_rain = at("Mumbai", "Jul", "rain")
    mumbai_jul_bar = at("Mumbai", "Jul", "rainbar")
    sydney_jan, sydney_jul = at("Sydney", "Jan", "bead"), at("Sydney", "Jul", "bead")
    sing_jan = at("Singapore", "Jan", "bead")

    shots = [
        Shot(title="Your Data in GlyphViz", heading="From a spreadsheet to a scene",
             say="Here's data you might already have: a spreadsheet of monthly "
                 "climate for thirty one cities. One row per city per month, with "
                 "the average high, low, and rainfall. Three hundred and seventy "
                 "two rows.",
             keys=[Key(0, az=30, el=25, dist=40, target=(0, 0, 0)),
                   Key(1, az=40, el=25, dist=40)],
             card=text_card("city_climate.csv", table, sub="372 rows: 31 cities x 12 months",
                            footer="NASA POWER, 2001 to 2020, averaged by month")),
        Shot(heading="Describe the picture",
             say="Give it to Claude with the GlyphViz skill, and describe what you "
                 "want to see: each city on a globe, a clock face of months "
                 "coloured by temperature, and on every month, a temperature bar "
                 "and a rainfall column.",
             keys=[Key(0, az=40, el=25, dist=40, target=(0, 0, 0)),
                   Key(1, az=50, el=25, dist=40)],
             card=text_card("Your prompt, to Claude with the glyphviz skill",
                            prompt_lines[:-1], color=AMBER, mono=False)),
        Shot(heading="Claude writes the scene",
             say="Claude writes the scene: one row for every piece of every glyph, "
                 "over three thousand of them. It checks the geometry with "
                 "GlyphViz's own engine before handing it over.",
             keys=[Key(0, az=50, el=25, dist=40, target=(0, 0, 0)),
                   Key(1, az=60, el=25, dist=40)],
             card=text_card("What comes back", files, color=TEAL)),
        Shot(heading="Drop it on the window",
             say="Drag the folder onto GlyphViz, and there it is. Three hundred and "
                 "seventy two rows, now a globe of climate you can explore.",
             keys=[Key(0, az=60, el=25, dist=40, target=(0, 0, 0)),
                   Key(0.3, az=40, el=18, dist=560, target=(0, 0, 0)),
                   Key(1, az=75, el=20, dist=500)],
             events=[(0.25, drop)],
             state=dict(show_tags=True, show_tags_selected_only=True),
             keycap="Drag & drop", keycap_note="the scene folder"),
        Shot(heading="Each ring is a year",
             say="Each ring is one city's year. January sits at the top, and the "
                 "months run clockwise. Moscow's ring swings from deep blue in "
                 "winter to warm orange in summer.",
             keys=[
                 Key(0, az=75, el=20, dist=500, target=(0, 0, 0)),
                 Key(0.45, az=10, el=30, dist=330, target=(0, 0, 70)),
                 close(0.85), close(1.0, az=6)],
             animate=turn((0.0, 0.0), "Moscow", 0.05, 0.75),
             callouts=[Callout(moscow_jan, "January", 0.8, 0.99, offset=(-120, -70),
                               color=TEAL),
                       Callout(moscow_jul, "July", 0.85, 0.99, offset=(120, 60),
                               color=CORAL)]),
        Shot(heading="Height is temperature",
             say="Each bar spans the month's average low to high. The higher it "
                 "stands, the warmer the month. The blue column beside it is the "
                 "month's rainfall.",
             keys=[close(0, az=6), Key(1, az=-20, el=24, dist=52, target=TOP)],
             callouts=[Callout(moscow_jul_hi, moscow_jul_temp, 0.15, 0.99,
                               offset=(110, -70), ring=False, color=CORAL),
                       Callout(moscow_jul_rain, moscow_jul_mm, 0.45, 0.99,
                               offset=(-120, -60), ring=False, color=(70, 150, 255))]),
        Shot(heading="Singapore",
             say="Singapore is the opposite. One colour all year round, every bar "
                 "at the same height, and rain in every month.",
             keys=[Key(0, az=-20, el=24, dist=52, target=TOP),
                   Key(0.35, az=-10, el=30, dist=360, target=(0, 0, 70)),
                   close(0.8, az=0), close(1.0, az=10)],
             animate=turn("Moscow", "Singapore"),
             callouts=[Callout(sing_jan, "Singapore", 0.8, 0.99, offset=(-110, -80),
                               ring=False, color=AMBER)]),
        Shot(heading="Mumbai: the monsoon",
             say="Mumbai has a monsoon. From June to September, the rain columns "
                 "tower over the rest of the year.",
             keys=[close(0, az=10), Key(0.35, az=15, el=30, dist=320, target=(0, 0, 70)),
                   Key(0.8, az=0, el=26, dist=72, target=(0, 0, 184)),
                   Key(1, az=-8, el=26, dist=70)],
             animate=turn("Singapore", "Mumbai"),
             callouts=[Callout(mumbai_jul_rain, mumbai_jul_mm, 0.8, 0.99,
                               offset=(110, -40), ring=False, color=(70, 150, 255))]),
        Shot(heading="Across the equator",
             say="Cross the equator, and the seasons flip. In Sydney, the warm "
                 "colours sit at the top of the clock, right where Moscow's were blue.",
             keys=[Key(0, az=-8, el=26, dist=70, target=(0, 0, 184)),
                   Key(0.35, az=5, el=30, dist=360, target=(0, 0, 70)),
                   close(0.8), close(1.0, az=8)],
             animate=turn("Mumbai", "Sydney"),
             callouts=[Callout(sydney_jan, "January: summer", 0.8, 0.99,
                               offset=(-130, -70), color=CORAL),
                       Callout(sydney_jul, "July: winter", 0.85, 0.99,
                               offset=(120, 60), color=TEAL)]),
        Shot(heading="Click anything",
             say="Every piece is labelled. Click a glyph to read its value.",
             keys=[close(0, az=8), Key(1, az=20, el=32, dist=58, target=TOP)],
             animate=turn("Sydney", "Mumbai", 0.0, 0.4),
             events=[(0.55, lambda L: L.win._table.select_by_id(mumbai_jul_bar))],
             keycap="Click", keycap_note="read a glyph's label"),
        Shot(heading="Your turn",
             say="Any table with a handful of columns can become a scene like this. "
                 "Describe it, drop it in, and explore.",
             keys=[Key(0, az=20, el=32, dist=58, target=TOP),
                   Key(0.5, az=40, el=24, dist=480, target=(0, 0, 0)),
                   Key(1, az=90, el=22, dist=520)],
             select=set()),
        Shot(heading="Recap",
             say="That's your data in GlyphViz.",
             keys=[Key(0, az=90, el=22, dist=520, target=(0, 0, 0)),
                   Key(1, az=110, el=22, dist=540)], min_dur=7,
             summary=["A spreadsheet you already have",
                      "Describe the scene to Claude + the glyphviz skill",
                      "Drop the folder on GlyphViz",
                      "Click anything to read its value"]),
    ]
    return Lesson(name="climate_rings", title="Your Data in GlyphViz",
                  nodes=[world()], shots=shots, use_window=True,
                  prepare=prepare, voice="af_heart")
