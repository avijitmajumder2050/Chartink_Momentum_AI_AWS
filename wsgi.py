"""Production WSGI entrypoint — gunicorn points here (wsgi:app), not
app.py's own `app` object directly (app:app).

app.py deliberately keeps _start_alert_monitor() out of module-import
scope (see its own comment) so importing app.py alone — a bare WSGI
import, a test suite, tooling — never has the side effect of starting
the background alert-tracking bot. Real serving needs that bot running
exactly once, so this file is the one explicit place that starts it.

Run with a single worker (`gunicorn --workers 1 --threads 4 --bind
0.0.0.0:8000 wsgi:app`) — each additional worker process would import
this module again and start its own copy of the monitor thread,
duplicate-notifying subscribers.
"""

from app import app, _start_alert_monitor

_start_alert_monitor()
