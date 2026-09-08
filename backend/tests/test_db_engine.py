import pytest

from app.db.engine import get_engine


@pytest.mark.parametrize("url", ["sqlite:///unsupported.db", "mysql://user:private-value@host/db"])
def test_unsupported_database_is_rejected_without_echoing_configuration(url: str) -> None:
    with pytest.raises(ValueError, match="requires PostgreSQL") as failure:
        get_engine(url)
    assert "private-value" not in str(failure.value)


@pytest.mark.parametrize(
    "given, expected",
    [
        ("postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgresql+psycopg://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
    ],
)
def test_normalize_database_url_pins_psycopg_driver(given: str, expected: str) -> None:
    from app.db.engine import _normalize_database_url

    assert _normalize_database_url(given) == expected


def test_get_engine_accepts_provider_style_url(database_url: str) -> None:
    bare_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    engine = get_engine(bare_url)
    assert engine.dialect.driver == "psycopg"
