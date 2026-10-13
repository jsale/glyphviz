"""
Load the Lahman Baseball Database CSV files into MySQL: one table per CSV.

Each file becomes a table named after it, lower-cased, so

    Batting.csv         ->  batting
    AllstarFull.csv     ->  allstarfull
    FieldingOFsplit.csv ->  fieldingofsplit

Column names are kept exactly as the CSV spells them (`2B`, `playerID`, ...),
and every identifier is back-quoted, so the digit-led `2B`/`3B` columns are
fine.  Column types are INFERRED from the data, not guessed from the header:
a column is INT/BIGINT if every non-blank value is an integer, DOUBLE if
every one is a number, otherwise VARCHAR (or TEXT when a value is longer than
255 characters).  A blank cell becomes NULL -- in the Lahman files a blank
means "not recorded", never zero or the empty string.

A handful of non-unique indexes are added afterwards on the key columns the
database is joined on (playerID, yearID, teamID, lgID, franchID), because the
visualisation export joins `batting` to `people` and a 128k-row table is slow
to join unindexed.

Usage
-----
    python lahman_to_mysql.py --csv-dir lahman_1871-2025_csv --user root
    python lahman_to_mysql.py --csv-dir ... --database lahman --replace
    python lahman_to_mysql.py --csv-dir ... --only batting people teams

Connection settings come from the command line or the environment, so a
password never has to be typed into a script:

    MYSQL_HOST (127.0.0.1)   MYSQL_PORT (3306)   MYSQL_USER (root)
    MYSQL_PASSWORD (prompted for if unset)       MYSQL_DATABASE (lahman)

Needs `pip install pymysql`.  The database is created if it does not exist.
A table that already exists is SKIPPED unless --replace is given, so a re-run
never silently overwrites anything; a table that fails part-way through is
dropped again, never left half-loaded.
"""

import argparse
import csv
import getpass
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CSV_DIR = HERE / "lahman_1871-2025_csv"

BATCH_ROWS = 2000
INT_RE = re.compile(r"^-?(0|[1-9][0-9]*)$")
FLOAT_RE = re.compile(
    r"^-?((0|[1-9][0-9]*)(\.[0-9]*)?|\.[0-9]+)([eE][-+]?[0-9]+)?$")
INT32_MAX = 2 ** 31 - 1
VARCHAR_STEPS = (8, 16, 32, 64, 128, 255)

# Columns worth an index when a table has them.  Never on a TEXT column.
INDEX_COLUMNS = ("playerID", "yearID", "teamID", "lgID", "franchID")


# ---------------------------------------------------------------------------
# Reading a CSV
# ---------------------------------------------------------------------------

def read_csv(path):
    """Return (header, rows).  UTF-8 first (a BOM is dropped), cp1252 if the
    file is not valid UTF-8 -- which is what an older Lahman release was."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with open(path, newline="", encoding=encoding) as fh:
                reader = csv.reader(fh)
                header = next(reader)
                rows = list(reader)
            return [h.strip() for h in header], rows
        except UnicodeDecodeError:
            continue
    raise ValueError("%s is neither UTF-8 nor cp1252" % path)


def table_name_for(path):
    """`FieldingOFsplit.csv` -> `fieldingofsplit`."""
    return re.sub(r"[^a-z0-9_]", "_", Path(path).stem.lower())


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------

def infer_type(values):
    """
    The narrowest MySQL type that holds every non-blank value, as
    (sql_type, kind) where kind is 'int' | 'float' | 'text'.
    """
    longest = 0
    is_int = is_float = True
    int_lo = int_hi = 0
    seen = False
    for v in values:
        if v == "":
            continue
        seen = True
        if len(v) > longest:
            longest = len(v)
        if is_int:
            if INT_RE.match(v):
                n = int(v)
                if n < int_lo:
                    int_lo = n
                if n > int_hi:
                    int_hi = n
            else:
                is_int = False
        if not is_int and is_float and not FLOAT_RE.match(v):
            is_float = False
    if not seen:
        return "VARCHAR(8)", "text"
    if is_int:
        if int_lo >= -INT32_MAX and int_hi <= INT32_MAX:
            return "INT", "int"
        return "BIGINT", "int"
    if is_float:
        return "DOUBLE", "float"
    if longest > VARCHAR_STEPS[-1]:
        return "TEXT", "text"
    for step in VARCHAR_STEPS:
        if longest <= step:
            return "VARCHAR(%d)" % step, "text"
    return "TEXT", "text"


def quote_ident(name):
    return "`" + name.replace("`", "``") + "`"


def build_create_table(table, header, types):
    cols = ",\n  ".join("%s %s NULL" % (quote_ident(h), t[0])
                        for h, t in zip(header, types))
    return ("CREATE TABLE %s (\n  %s\n) ENGINE=InnoDB "
            "DEFAULT CHARSET=utf8mb4" % (quote_ident(table), cols))


def convert(value, kind):
    if value == "":
        return None
    if kind == "int":
        return int(value)
    if kind == "float":
        return float(value)
    return value


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_table(conn, path, replace):
    """Create and fill one table.  Returns (table, rows_loaded, status)."""
    table = table_name_for(path)
    header, rows = read_csv(path)
    width = len(header)
    # A short row (trailing blanks trimmed by a spreadsheet) is padded; a
    # long one is a genuinely malformed line and stops the load.
    for n, row in enumerate(rows, start=2):
        if len(row) > width:
            raise ValueError("%s line %d has %d fields, header has %d"
                             % (Path(path).name, n, len(row), width))
        if len(row) < width:
            row.extend([""] * (width - len(row)))

    types = [infer_type(col) for col in zip(*rows)] if rows else \
        [("VARCHAR(8)", "text")] * width

    with conn.cursor() as cur:
        cur.execute("SHOW TABLES LIKE %s", (table,))
        exists = cur.fetchone() is not None
        if exists and not replace:
            return table, 0, "skipped (exists; use --replace)"
        if exists:
            cur.execute("DROP TABLE %s" % quote_ident(table))
        cur.execute(build_create_table(table, header, types))

    kinds = [t[1] for t in types]
    insert = "INSERT INTO %s (%s) VALUES (%s)" % (
        quote_ident(table), ", ".join(quote_ident(h) for h in header),
        ", ".join(["%s"] * width))
    try:
        with conn.cursor() as cur:
            for start in range(0, len(rows), BATCH_ROWS):
                cur.executemany(insert, [
                    [convert(v, k) for v, k in zip(row, kinds)]
                    for row in rows[start:start + BATCH_ROWS]])
            for h, t in zip(header, types):
                if h in INDEX_COLUMNS and t[0] != "TEXT":
                    cur.execute("CREATE INDEX %s ON %s (%s)" % (
                        quote_ident("idx_%s_%s" % (table, h.lower())),
                        quote_ident(table), quote_ident(h)))
            cur.execute("SELECT COUNT(*) FROM %s" % quote_ident(table))
            (count,) = cur.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        with conn.cursor() as cur:       # never leave a half-loaded table
            cur.execute("DROP TABLE IF EXISTS %s" % quote_ident(table))
        raise
    if count != len(rows):
        raise RuntimeError("%s: loaded %d rows but the CSV has %d"
                           % (table, count, len(rows)))
    return table, count, "ok"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Import the Lahman CSV files into MySQL, one table per CSV.")
    ap.add_argument("--csv-dir", default=os.environ.get("LAHMAN_CSV_DIR",
                                                        str(DEFAULT_CSV_DIR)),
                    help="folder holding the Lahman *.csv files "
                         "(env LAHMAN_CSV_DIR; default: lahman_1871-2025_csv "
                         "beside this script)")
    ap.add_argument("--host", default=os.environ.get("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("MYSQL_PORT", "3306")))
    ap.add_argument("--user", default=os.environ.get("MYSQL_USER", "root"))
    ap.add_argument("--password", default=os.environ.get("MYSQL_PASSWORD"),
                    help="prefer the MYSQL_PASSWORD environment variable; "
                         "prompted for if neither is given")
    ap.add_argument("--database", default=os.environ.get("MYSQL_DATABASE",
                                                         "lahman"))
    ap.add_argument("--replace", action="store_true",
                    help="drop and reload tables that already exist "
                         "(default: skip them)")
    ap.add_argument("--only", nargs="+", metavar="TABLE",
                    help="load just these tables, e.g. --only batting people")
    args = ap.parse_args(argv)

    try:
        import pymysql
    except ImportError:
        sys.exit("This script needs PyMySQL:  pip install pymysql")

    csv_dir = Path(args.csv_dir)
    files = sorted(csv_dir.glob("*.csv"), key=lambda p: p.name.lower())
    if not files:
        sys.exit("No .csv files in %s -- pass --csv-dir" % csv_dir)
    if args.only:
        wanted = {w.lower() for w in args.only}
        files = [f for f in files if table_name_for(f) in wanted]
        missing = wanted - {table_name_for(f) for f in files}
        if missing:
            sys.exit("No CSV for: %s" % ", ".join(sorted(missing)))

    password = args.password
    if password is None:
        password = getpass.getpass("MySQL password for %s@%s: "
                                   % (args.user, args.host))

    if not re.fullmatch(r"[A-Za-z0-9_]+", args.database):
        sys.exit("--database may only contain letters, digits and _")
    try:
        conn = pymysql.connect(host=args.host, port=args.port, user=args.user,
                               password=password, charset="utf8mb4",
                               autocommit=False)
    except RuntimeError as exc:           # MySQL 8 auth without TLS
        sys.exit("%s\n(for MySQL 8's default login:  pip install cryptography)"
                 % exc)
    except pymysql.MySQLError as exc:
        sys.exit("Could not connect to %s@%s: %s"
                 % (args.user, args.host, exc))
    with conn.cursor() as cur:
        cur.execute("CREATE DATABASE IF NOT EXISTS `%s` "
                    "DEFAULT CHARACTER SET utf8mb4" % args.database)
        cur.execute("USE `%s`" % args.database)
    conn.commit()

    print("Loading %d CSV files from %s into %s@%s/%s\n"
          % (len(files), csv_dir, args.user, args.host, args.database))
    print("  %-22s %10s  %7s  %s" % ("table", "rows", "seconds", "status"))
    failures = 0
    for path in files:
        t0 = time.time()
        try:
            table, count, status = load_table(conn, path, args.replace)
        except Exception as exc:                          # keep going
            failures += 1
            table, count, status = table_name_for(path), 0, "FAILED: %s" % exc
        print("  %-22s %10s  %7.1f  %s"
              % (table, "{:,}".format(count), time.time() - t0, status))
    conn.close()
    if failures:
        sys.exit("\n%d table(s) failed." % failures)
    print("\nDone.")


if __name__ == "__main__":
    main()
