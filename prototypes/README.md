# Prototypes

Stand-alone scripts used to try out ideas before they go into the application. They are
not imported by the app.

| Script | What it shows |
|---|---|
| `ra_demo.py` | The relational-algebra translator end to end: RA → expression tree → SQL → result, on a sample university database, plus RA-level error messages. Run from `backend/`. |
| `sqlite_vec_spike.py` | Whether this Python can load SQLite extensions, whether sqlite-vec reproduces the expected answers of the sample vector lab (Design Doc 03 §5.2), and whether a pure-Python fallback does too. |

Both need a Python whose `sqlite3` module allows extension loading (e.g. `uv python install 3.11`);
see `fyp-docs/PROGRESS_REPORT_WEEKS_3-4.md` §4.
