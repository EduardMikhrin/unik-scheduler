"""The catalog and the KPI API spell the same courses differently."""

from __future__ import annotations

from unik_scheduler.kpi.matching import SubjectMatcher, normalize

CATALOG_GRAPHICS = "Інженерна комп’ютерна графіка"  # U+2019
API_GRAPHICS = "Інженерна комп'ютерна графіка"  # U+0027

CATALOG_TIMESERIES = (
    "Аналіз та обробка часових рядів (TimeSeries) "
    "(Сертифікатна програма Data Science із Sigma Software)"
)
API_TIMESERIES = (
    "Аналіз та обробка часових рядів (Time Series) "
    "(Сертифікатна програма Data Science із Sigma Software)"
)

CATALOG_RL = "Основи глибокого навчання з підкріпленням"
API_RL = "Основи глибого навчання з підкріпленням"  # typo lives in the API


def build(*rows: tuple[int, str, str | None]) -> SubjectMatcher:
    return SubjectMatcher(
        [
            (sid, name, normalize(name), normalize(alias) if alias else None)
            for sid, name, alias in rows
        ]
    )


def test_apostrophe_variants_normalize_to_the_same_key():
    assert normalize(CATALOG_GRAPHICS) == normalize(API_GRAPHICS)


def test_en_dash_and_case_are_normalized():
    assert normalize("Основи WEB – технологій") == normalize("основи web - технологій")


def test_normalization_alone_matches_the_apostrophe_case():
    matcher = build((14, CATALOG_GRAPHICS, None))
    assert matcher.match(API_GRAPHICS) == 14


def test_spacing_variant_needs_an_alias():
    without = build((25, CATALOG_TIMESERIES, None))
    assert without.match(API_TIMESERIES) is None

    with_alias = build((25, CATALOG_TIMESERIES, API_TIMESERIES))
    assert with_alias.match(API_TIMESERIES) == 25


def test_api_side_typo_needs_an_alias():
    without = build((26, CATALOG_RL, None))
    assert without.match(API_RL) is None

    with_alias = build((26, CATALOG_RL, API_RL))
    assert with_alias.match(API_RL) == 26


def test_unmatched_name_gets_an_actionable_suggestion():
    matcher = build((26, CATALOG_RL, None))
    candidate = matcher.suggest(API_RL)
    assert candidate is not None
    assert candidate.subject_id == 26
    assert candidate.ratio > 0.9


def test_unrelated_name_suggests_nothing():
    matcher = build((26, CATALOG_RL, None))
    assert matcher.suggest("Фізичне виховання") is None
