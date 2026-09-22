"""UI entry point: `python -m app.ui.app`.

Runs the Flask app defined in `app.ui.server`, which serves the
control-tower frontend in `app/ui/static/` and exposes the small JSON API
that frontend calls (`app.ui.server` docstring has the route list). No
business logic lives in either file -- every route ultimately calls
`app.agent.orchestrator.run`.
"""

from app.ui.server import app

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5057, debug=True)
