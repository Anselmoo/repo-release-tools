"""Bundled EOL data and language metadata."""

RUST_WARN_LAG = 2
RUST_ERROR_LAG = 4

BUNDLED_EOL_DATA: dict[str, list[dict[str, object]]] = {
    "python": [
        {"cycle": "3.14", "releaseDate": "2025-10-07", "eol": "2030-10-31"},
        {"cycle": "3.13", "releaseDate": "2024-10-07", "eol": "2029-10-31"},
        {"cycle": "3.12", "releaseDate": "2023-10-02", "eol": "2028-10-31"},
        {"cycle": "3.11", "releaseDate": "2022-10-24", "eol": "2027-10-31"},
        {"cycle": "3.10", "releaseDate": "2021-10-04", "eol": "2026-10-31"},
        {"cycle": "3.9", "releaseDate": "2020-10-05", "eol": "2025-10-31"},
        {"cycle": "3.8", "releaseDate": "2019-10-14", "eol": "2024-10-07"},
        {"cycle": "3.7", "releaseDate": "2018-06-27", "eol": "2023-06-27"},
    ],
    "nodejs": [
        {"cycle": "24", "releaseDate": "2025-05-06", "eol": "2028-04-30"},
        {"cycle": "23", "releaseDate": "2024-10-16", "eol": "2025-06-01"},
        {"cycle": "22", "releaseDate": "2024-04-24", "eol": "2027-04-30"},
        {"cycle": "21", "releaseDate": "2023-10-17", "eol": "2024-06-01"},
        {"cycle": "20", "releaseDate": "2023-04-18", "eol": "2026-04-30"},
        {"cycle": "18", "releaseDate": "2022-04-19", "eol": "2025-04-30"},
        {"cycle": "16", "releaseDate": "2021-04-20", "eol": "2023-09-11"},
    ],
    "go": [
        {"cycle": "1.26", "releaseDate": "2026-02-11", "eol": False},
        {"cycle": "1.25", "releaseDate": "2025-08-12", "eol": False},
        {"cycle": "1.24", "releaseDate": "2025-02-11", "eol": "2026-02-11"},
        {"cycle": "1.23", "releaseDate": "2024-08-13", "eol": "2025-08-12"},
        {"cycle": "1.22", "releaseDate": "2024-02-06", "eol": "2025-02-11"},
        {"cycle": "1.21", "releaseDate": "2023-08-08", "eol": "2024-08-13"},
    ],
    "rust": [
        {"cycle": "1.95", "releaseDate": "2026-04-16", "eol": False},
        {"cycle": "1.94", "releaseDate": "2026-03-06", "eol": "2026-04-16"},
        {"cycle": "1.93", "releaseDate": "2026-01-22", "eol": "2026-03-06"},
        {"cycle": "1.92", "releaseDate": "2025-12-11", "eol": "2026-01-22"},
        {"cycle": "1.91", "releaseDate": "2025-10-30", "eol": "2025-12-11"},
        {"cycle": "1.90", "releaseDate": "2025-09-04", "eol": "2025-10-30"},
        {"cycle": "1.89", "releaseDate": "2025-07-10", "eol": "2025-09-04"},
        {"cycle": "1.88", "releaseDate": "2025-05-15", "eol": "2025-07-10"},
    ],
}

_EOL_API_SLUG: dict[str, str] = {
    "python": "python",
    "nodejs": "nodejs",
    "node": "nodejs",
    "go": "go",
    "rust": "rust",
}

SUPPORTED_LANGUAGES = frozenset(_EOL_API_SLUG.keys())
