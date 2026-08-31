"""The catalog file is hand-maintained, so parsing has to be forgiving but exact."""

from __future__ import annotations

import json

import pytest

from unik_scheduler.catalog.importer import CatalogError, _fields_of, parse_catalog

# Mirrors the real file: extra bookkeeping keys, `selected`, and the null/"" split.
RAW = {
    "normative": [
        {
            "id": 1,
            "name": "Управління проєктами",
            "short_name": "Управління проєктами",
            "department": "ІСТ",
            "semester": 7,
            "credits": 3.0,
            "control": "залік",
            "chat_url": "",
            "conferences": {"lecture": "", "practice": None, "lab": ""},
        }
    ],
    "electives": [
        {
            "id": 16,
            "name": "Тестування та контроль якості (QA) вбудованих систем "
            "(Сертифікатна програма ESI&IoT з компанією Global Logic)",
            "department": "ОТ",
            "semester": 7,
            "component": "9Ф",
            "credits": 4.0,
            "control": "залік",
            "selected": True,
            "chat_url": "https://t.me/qa_chat",
            "conferences": {"lecture": "https://meet.example/lec", "practice": None, "lab": ""},
        }
    ],
    "meta": {"source_plan": "my.kpi.ua", "course": 4},
}


def test_extra_bookkeeping_keys_are_ignored():
    catalog = parse_catalog(json.dumps(RAW).encode("utf-8"))
    assert len(catalog.normative) == 1
    assert len(catalog.electives) == 1


def test_selected_maps_onto_default_selected():
    catalog = parse_catalog(json.dumps(RAW).encode("utf-8"))
    assert catalog.electives[0].default_selected is True
    assert catalog.normative[0].default_selected is False


def test_null_and_empty_conference_are_not_the_same_thing():
    catalog = parse_catalog(json.dumps(RAW).encode("utf-8"))
    fields = _fields_of("normative", catalog.normative[0])
    # "" -> the course has lectures, link not filled in yet
    assert fields["has_lecture"] is True
    assert fields["conf_lecture"] is None
    # None -> the course has no practicals at all
    assert fields["has_practice"] is False


def test_filled_link_survives_the_round_trip():
    catalog = parse_catalog(json.dumps(RAW).encode("utf-8"))
    fields = _fields_of("elective", catalog.electives[0])
    assert fields["conf_lecture"] == "https://meet.example/lec"
    assert fields["chat_url"] == "https://t.me/qa_chat"
    assert fields["has_lab"] is True and fields["conf_lab"] is None


def test_match_key_is_derived_from_the_name():
    catalog = parse_catalog(json.dumps(RAW).encode("utf-8"))
    fields = _fields_of("normative", catalog.normative[0])
    assert fields["match_key"] == "управління проєктами"
    assert fields["alias_match_key"] is None


def test_duplicate_ids_are_rejected():
    payload = {"normative": RAW["normative"], "electives": [dict(RAW["electives"][0], id=1)]}
    with pytest.raises(CatalogError, match="Повторювані id"):
        parse_catalog(json.dumps(payload).encode("utf-8"))


def test_broken_json_reports_the_line():
    with pytest.raises(CatalogError, match="коректний JSON"):
        parse_catalog(b'{"normative": [},')


def test_empty_catalog_is_rejected():
    with pytest.raises(CatalogError, match="немає жодного предмета"):
        parse_catalog(b'{"normative": [], "electives": []}')


def test_non_object_payload_is_rejected():
    with pytest.raises(CatalogError):
        parse_catalog(b"[1, 2, 3]")


def test_missing_required_field_names_the_location():
    payload = {"normative": [{"id": 1, "name": "X"}], "electives": []}
    with pytest.raises(CatalogError, match="semester"):
        parse_catalog(json.dumps(payload).encode("utf-8"))
