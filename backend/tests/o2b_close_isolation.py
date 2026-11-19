"""Never allow the closeout consumer fixtures on an ordinary database."""

import os


def is_close_consumer_database(db):
    url = db.bind.url
    if db.bind.dialect.name != "postgresql":
        return False
    identity = (url.host, url.port, url.database, url.username)
    return (
        (
            os.getenv("PYPMIS_O2B_CLOSE_FIXTURE") == "disposable-only"
            and identity == ("127.0.0.1", 5558, "o2b_close_consumers", "o2b_close_migration")
        )
        or (
            os.getenv("PYPMIS_O2B_CLOSE2_BROWSER_FIXTURE") == "disposable-only"
            and identity == ("127.0.0.1", 5557, "o2b_browser", "o2b")
        )
        or (
            os.getenv("PYPMIS_O2C_FIXTURE") == "disposable-only"
            and identity
            in {
                ("127.0.0.1", 5561, "o2c", "o2c"),
                ("127.0.0.1", 5562, "o2c", "o2c"),
            }
        )
    )
