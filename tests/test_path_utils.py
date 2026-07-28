from __future__ import annotations

from sancho.path_utils import dedupe_name, normalize_extension, safe_filename, safe_slug


def test_basic_slug() -> None:
    assert safe_slug("Alabama Population Data") == "alabama-population-data"


def test_empty_falls_back() -> None:
    assert safe_slug("") == "dataset"
    assert safe_slug("   ") == "dataset"


def test_all_punctuation_keeps_signal_via_hash() -> None:
    out = safe_slug("@#$%^&*")
    assert out.startswith("dataset__")


def test_slashes_and_unsafe_chars_removed() -> None:
    out = safe_slug('a/b\\c:d*e?"f')
    assert "/" not in out and "\\" not in out and ":" not in out
    assert "*" not in out and "?" not in out and '"' not in out


def test_repeated_separators_collapse() -> None:
    assert safe_slug("a   b___c---d") == "a-b-c-d"


def test_unicode_punctuation() -> None:
    out = safe_slug("Café — Déjà Vu!!!")
    assert out and " " not in out
    assert out.strip("-_.") == out


def test_long_truncated_with_deterministic_hash() -> None:
    a = safe_slug("x" * 200)
    b = safe_slug("x" * 200)
    assert a == b  # stable
    assert len(a) <= 48
    assert "__" in a


def test_distinct_long_inputs_do_not_collide() -> None:
    a = safe_slug("alpha" * 40)
    b = safe_slug("beta" * 40)
    assert a != b


def test_emojis_and_hostile_unicode_never_reach_filenames() -> None:
    # Emojis and exotic/dangerous unicode must be stripped to pure ASCII so they
    # can never appear in a filename, folder, or path.
    hostile = ["📊data", "中国人口", "💀🔥💯", "‮RTL", "null\x00byte", "naïve café", "a/b\\c"]
    for value in hostile:
        slug = safe_slug(value)
        fname = safe_filename(value, "csv")
        assert all(ord(c) < 128 for c in slug), f"non-ASCII leaked: {slug!r}"
        assert all(ord(c) < 128 for c in fname), f"non-ASCII leaked: {fname!r}"
        assert "\x00" not in slug and "‮" not in slug
        assert "/" not in slug and "\\" not in slug
    # Emoji-only input still yields a usable, stable, non-empty name.
    assert safe_slug("💀🔥💯") == safe_slug("💀🔥💯")
    assert safe_slug("💀🔥💯").startswith("dataset__")


def test_windows_reserved_name_is_escaped() -> None:
    assert safe_slug("CON") != "con"
    assert safe_slug("nul").startswith("nul-")


def test_normalize_extension() -> None:
    assert normalize_extension("CSV") == ".csv"
    assert normalize_extension(".JSON") == ".json"
    assert normalize_extension("") == ""
    assert normalize_extension(None) == ""
    assert normalize_extension("../evil") == ".evil"


def test_safe_filename_keeps_extension_off_length_budget() -> None:
    name = safe_filename("x" * 200, "csv")
    stem, _, ext = name.rpartition(".")
    assert ext == "csv"
    assert len(stem) <= 48


def test_dedupe_name() -> None:
    taken: set[str] = set()
    assert dedupe_name("a.csv", taken) == "a.csv"
    assert dedupe_name("a.csv", taken) == "a__2.csv"
    assert dedupe_name("a.csv", taken) == "a__3.csv"
    assert dedupe_name("b", taken) == "b"
    assert dedupe_name("b", taken) == "b__2"


def test_dedupe_name_is_case_insensitive() -> None:
    taken: set[str] = set()
    dedupe_name("Data.CSV", taken)
    assert dedupe_name("data.csv", taken) == "data__2.csv"
