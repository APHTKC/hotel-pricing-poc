import asyncio
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx

from app.models import Hotel
from app.models import RateObservation, ScrapeStatus
from scrapers.ota.base import OtaRateProvider
from scrapers.ota.booking_com import BookingComProvider, _room_size_sqm, parse_availability
from scrapers.ota.config import load_ota_property_mappings
from scrapers.ota.registry import OTA_PROVIDER_SPECS, configured_ota_providers
from services.rate_parity import canonical_comparison_key


class ExampleProvider(OtaRateProvider):
    platform = "booking_com"

    async def fetch_rates(self, hotel, source_property_id, check_in, check_out, adults=2):
        return []


def test_ota_registry_requires_complete_partner_credentials():
    assert configured_ota_providers({}) == []
    assert configured_ota_providers({"AGODA_API_KEY": "key"}) == []
    configured = configured_ota_providers(
        {"AGODA_API_KEY": "key", "AGODA_SITE_ID": "site"}
    )
    assert [spec.platform for spec in configured] == ["agoda"]
    assert {spec.platform for spec in OTA_PROVIDER_SPECS} == {
        "booking_com",
        "agoda",
        "expedia_group",
        "rakuten_travel",
    }


def test_ota_provider_tags_rate_source_metadata():
    observation = RateObservation(
        observation_id="sample",
        queried_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        check_in=date(2026, 10, 1),
        check_out=date(2026, 10, 2),
        lead_days=10,
        hotel_id="sample_hotel",
        hotel_name="Sample Hotel",
        room_type_name="Deluxe",
        rate_plan_name="Flexible",
        total_price=Decimal("10000"),
        currency="TWD",
        source_url="https://example.com/rate",
        status=ScrapeStatus.LIVE,
    )

    tagged = ExampleProvider().tag_observation(observation, "property-123")

    assert tagged.source_platform == "booking_com"
    assert tagged.source_method == "partner_api"
    assert tagged.source_property_id == "property-123"


def _hotel() -> Hotel:
    return Hotel(
        id="capella_taipei",
        name="Capella Taipei",
        short_name="Capella",
        city="Taipei",
        district="Songshan",
        country="TW",
        booking_url="https://example.com/capella",
        adapter="capella",
    )


def test_booking_com_availability_parser_preserves_price_and_policies():
    queried_at = datetime(2026, 9, 21, tzinfo=timezone.utc)
    rows = parse_availability(
        {
            "data": {
                "currency": "TWD",
                "url": "https://www.booking.com/hotel/tw/example.html",
                "rooms": [{"id": 55, "name": "Deluxe King"}],
                "products": [
                    {
                        "id": "product-1",
                        "room": 55,
                        "policies": {
                            "meal_plan": {"plan": "breakfast_included"},
                            "cancellation": {
                                "type": "free_cancellation",
                                "free_cancellation_until": "2026-10-01T16:00:00+00:00",
                            },
                        },
                        "price": {
                            "base": {"booker_currency": 10000},
                            "total": {"booker_currency": 11550},
                        },
                    }
                ],
            }
        },
        _hotel(),
        "123456",
        date(2026, 10, 2),
        date(2026, 10, 3),
        2,
        queried_at,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.room_type_name == "Deluxe King"
    assert row.breakfast_included is True
    assert row.price_before_tax == Decimal("10000")
    assert row.total_price == Decimal("11550")
    assert row.total_twd == Decimal("11550")
    assert row.source_platform == "booking_com"
    assert row.source_property_id == "123456"


def test_booking_com_room_size_requires_and_normalizes_explicit_units():
    assert _room_size_sqm({"value": 55, "unit": "SQM"}) == Decimal("55")
    assert _room_size_sqm({"value": 538, "unit": "sqft"}) == Decimal("49.98")
    assert _room_size_sqm({"value": 55}) is None
    assert _room_size_sqm(55) is None
    assert _room_size_sqm({"value": 55, "unit": "unknown"}) is None


def test_booking_com_parser_uses_normalized_room_size_for_comparison():
    rows = parse_availability(
        {
            "data": {
                "currency": "TWD",
                "rooms": [
                    {
                        "id": 55,
                        "name": "Deluxe King",
                        "size": {"value": 538, "unit": "SQFT"},
                    }
                ],
                "products": [
                    {
                        "id": "product-1",
                        "room": 55,
                        "policies": {
                            "meal_plan": {"plan": "room_only"},
                            "cancellation": {"type": "non_refundable"},
                        },
                        "price": {"total": {"booker_currency": 9000}},
                    }
                ],
            }
        },
        _hotel(),
        "123456",
        date(2026, 10, 2),
        date(2026, 10, 3),
        2,
        datetime(2026, 9, 21, tzinfo=timezone.utc),
    )

    assert rows[0].room_size_sqm == Decimal("49.98")
    assert rows[0].size_band == "45–59㎡"


def test_booking_com_provider_uses_partner_headers_and_expected_request():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/accommodations/details"):
            return httpx.Response(
                200,
                json={"data": [{"rooms": [{"id": "55", "name": {"en-gb": "Deluxe"}}]}]},
            )
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": {"currency": "TWD", "products": []}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = BookingComProvider("secret", "affiliate-1", client=client)
    try:
        rows = asyncio.run(
            provider.fetch_rates(
                _hotel(), "123456", date(2026, 10, 2), date(2026, 10, 3)
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert rows == []
    assert captured["headers"]["authorization"] == "Bearer secret"
    assert captured["headers"]["x-affiliate-id"] == "affiliate-1"
    assert captured["body"]["accommodation"] == 123456
    assert captured["body"]["currency"] == "TWD"
    assert captured["body"]["extras"] == ["products", "extra_charges"]


def test_booking_com_property_discovery_is_hotel_only_and_normalized():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "123456",
                        "type": "hotel",
                        "name": {"en-gb": "Capella Taipei"},
                        "location": {
                            "city_name": {"en-gb": "Taipei"},
                            "country": "tw",
                        },
                    },
                    {"id": "-2637882", "type": "city", "name": "Taipei"},
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = BookingComProvider("secret", "affiliate-1", client=client)
    try:
        candidates = asyncio.run(provider.discover_properties("Capella Taipei"))
    finally:
        asyncio.run(client.aclose())

    assert candidates == [
        {
            "id": "123456",
            "name": "Capella Taipei",
            "city": "Taipei",
            "country": "tw",
        }
    ]
    assert captured["headers"]["authorization"] == "Bearer secret"
    assert captured["body"] == {
        "query": "Capella Taipei",
        "country": "tw",
        "language": "en-gb",
        "filters": {"types": ["hotel"]},
    }


def test_booking_com_property_discovery_rejects_short_queries():
    provider = BookingComProvider(
        "secret",
        "affiliate-1",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: None)),
    )
    try:
        try:
            asyncio.run(provider.discover_properties("ab"))
        except ValueError as error:
            assert "3+" in str(error)
        else:
            raise AssertionError("Expected short query to be rejected")
    finally:
        asyncio.run(provider.client.aclose())


def test_visible_browser_check_log_is_structured_and_non_retrying():
    path = Path("data/ota_browser_checks.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert rows
    keys = set()
    for row in rows:
        assert row["status"] in {"no_availability", "blocked", "verification_required"}
        assert row["reason"]
        assert row["occupancy"] == {"adults": 2, "children": 0, "rooms": 1}
        key = (
            row["hotel_id"],
            row["source_platform"],
            row["check_in"],
            row["check_out"],
        )
        assert key not in keys
        keys.add(key)

    by_hotel = {row["hotel_id"]: row for row in rows}
    for hotel_id, property_slug in {
        "le_meridien_taipei": "le-meridien-taipei",
        "taipei_marriott": "taipei-marriott",
    }.items():
        row = by_hotel[hotel_id]
        assert row["status"] == "no_availability"
        assert row["check_in"] == "2026-10-19"
        assert row["check_out"] == "2026-10-20"
        assert property_slug in row["source_url"]

    courtyard = by_hotel["courtyard_taipei"]
    assert courtyard["status"] == "no_availability"
    assert courtyard["check_in"] == "2026-12-19"
    assert courtyard["check_out"] == "2026-12-20"
    assert "courtyard-by-marriott-taipei" in courtyard["source_url"]

    courtyard_downtown = by_hotel["courtyard_taipei_downtown"]
    assert courtyard_downtown["status"] == "no_availability"
    assert courtyard_downtown["check_in"] == "2026-11-11"
    assert courtyard_downtown["check_out"] == "2026-11-12"
    assert "courtyard-by-marriott-taipei-downtown" in courtyard_downtown["source_url"]

    hotel_proverbs = by_hotel["hotel_proverbs_taipei"]
    assert hotel_proverbs["status"] == "no_availability"
    assert hotel_proverbs["check_in"] == "2026-11-11"
    assert hotel_proverbs["check_out"] == "2026-11-12"
    assert "hotel-proverbs-taipei" in hotel_proverbs["source_url"]

    renaissance = by_hotel["renaissance_taipei_shihlin"]
    assert renaissance["status"] == "no_availability"
    assert renaissance["check_in"] == "2026-11-12"
    assert renaissance["check_out"] == "2026-11-13"
    assert "renaissance-taipei-shihlin" in renaissance["source_url"]

    humble_house = by_hotel["humble_house_taipei"]
    assert humble_house["status"] == "no_availability"
    assert humble_house["check_in"] == "2026-11-13"
    assert humble_house["check_out"] == "2026-11-14"
    assert "humble-house-taipei-curio-collection-by-hilton" in humble_house["source_url"]

    kimpton = by_hotel["kimpton_da_an"]
    assert kimpton["status"] == "no_availability"
    assert kimpton["check_in"] == "2026-11-15"
    assert kimpton["check_out"] == "2026-11-16"
    assert "kimpton-da-an" in kimpton["source_url"]

    indigo = by_hotel["indigo_taipei_north"]
    assert indigo["status"] == "no_availability"
    assert indigo["check_in"] == "2026-11-16"
    assert indigo["check_out"] == "2026-11-17"
    assert "indigo-taipei-north" in indigo["source_url"]

    resonance = by_hotel["hotel_resonance_taipei"]
    assert resonance["status"] == "no_availability"
    assert resonance["check_in"] == "2026-11-17"
    assert resonance["check_out"] == "2026-11-18"
    assert "/resonance." in resonance["source_url"]

    doubletree = by_hotel["doubletree_taipei_zhongshan"]
    assert doubletree["status"] == "no_availability"
    assert doubletree["check_in"] == "2026-11-18"
    assert doubletree["check_out"] == "2026-11-19"
    assert "doubletree-by-hilton-taipei-zhongshan" in doubletree["source_url"]

    howard = by_hotel["howard_plaza_taipei"]
    assert howard["status"] == "no_availability"
    assert howard["check_in"] == "2026-11-19"
    assert howard["check_out"] == "2026-11-20"
    assert "the-howard-plaza-taipei" in howard["source_url"]

    grand_view = by_hotel["grand_view_resort_beitou"]
    assert grand_view["status"] == "no_availability"
    assert grand_view["check_in"] == "2026-11-20"
    assert grand_view["check_out"] == "2026-11-21"
    assert "grand-view-resort-beitou" in grand_view["source_url"]

    miramar = by_hotel["miramar_garden_taipei"]
    assert miramar["status"] == "no_availability"
    assert miramar["check_in"] == "2026-11-21"
    assert miramar["check_out"] == "2026-11-22"
    assert "miramar-garden" in miramar["source_url"]

    kagaya = by_hotel["radium_kagaya_taipei"]
    assert kagaya["status"] == "no_availability"
    assert kagaya["check_in"] == "2026-11-22"
    assert kagaya["check_out"] == "2026-11-23"
    assert "ri-sheng-sheng-jia-he-wu-guo-ji-wen-quan-fan-dian" in kagaya["source_url"]

    landis = by_hotel["the_landis_taipei"]
    assert landis["status"] == "no_availability"
    assert landis["check_in"] == "2026-11-23"
    assert landis["check_out"] == "2026-11-24"
    assert "the-landis-taipei" in landis["source_url"]

    gracery = by_hotel["hotel_gracery_taipei"]
    assert gracery["status"] == "no_availability"
    assert gracery["check_in"] == "2026-11-24"
    assert gracery["check_out"] == "2026-11-25"
    assert "ge-la-si-li-tai-bei-fan-dian" in gracery["source_url"]

    episode_daan = by_hotel["episode_daan_taipei"]
    assert episode_daan["status"] == "no_availability"
    assert episode_daan["check_in"] == "2026-11-26"
    assert episode_daan["check_out"] == "2026-11-27"
    assert "episode-daan-taipei" in episode_daan["source_url"]

    regent = by_hotel["regent_taipei"]
    assert regent["status"] == "no_availability"
    assert regent["check_in"] == "2026-11-27"
    assert regent["check_out"] == "2026-11-28"
    assert "the-regent-taipei" in regent["source_url"]

    intercontinental_taichung = by_hotel["intercontinental_taichung"]
    assert intercontinental_taichung["status"] == "no_availability"
    assert intercontinental_taichung["check_in"] == "2026-11-28"
    assert intercontinental_taichung["check_out"] == "2026-11-29"
    assert "intercontinental-hotels-taichung-an-ihg" in intercontinental_taichung["source_url"]

    the_lin = by_hotel["the_lin_taichung"]
    assert the_lin["status"] == "no_availability"
    assert the_lin["check_in"] == "2026-11-29"
    assert the_lin["check_out"] == "2026-11-30"
    assert "the-lin-hotel" in the_lin["source_url"]

    millennium = by_hotel["millennium_taichung"]
    assert millennium["status"] == "no_availability"
    assert millennium["check_in"] == "2026-11-30"
    assert millennium["check_out"] == "2026-12-01"
    assert "millennium-vee-taichung" in millennium["source_url"]

    le_meridien = by_hotel["le_meridien_taichung"]
    assert le_meridien["status"] == "no_availability"
    assert le_meridien["check_in"] == "2026-12-01"
    assert le_meridien["check_out"] == "2026-12-02"
    assert "le-meridien-taichung" in le_meridien["source_url"]

    intercontinental_kaohsiung = by_hotel["intercontinental_kaohsiung"]
    assert intercontinental_kaohsiung["status"] == "no_availability"
    assert intercontinental_kaohsiung["check_in"] == "2026-12-02"
    assert intercontinental_kaohsiung["check_out"] == "2026-12-03"
    assert "intercontinental-kaohsiung-an-ihg" in intercontinental_kaohsiung["source_url"]

    kaohsiung_marriott = by_hotel["kaohsiung_marriott"]
    assert kaohsiung_marriott["status"] == "no_availability"
    assert kaohsiung_marriott["check_in"] == "2026-12-03"
    assert kaohsiung_marriott["check_out"] == "2026-12-04"
    assert "kaohsiung-marriott" in kaohsiung_marriott["source_url"]

    amnis = by_hotel["silks_club_kaohsiung"]
    assert amnis["status"] == "no_availability"
    assert amnis["check_in"] == "2026-12-04"
    assert amnis["check_out"] == "2026-12-05"
    assert "jing-ying-guo-ji-xing-guan" in amnis["source_url"]

    tai_urban = by_hotel["tai_urban_resort"]
    assert tai_urban["status"] == "no_availability"
    assert tai_urban["check_in"] == "2026-12-05"
    assert tai_urban["check_out"] == "2026-12-06"
    assert "cheng-yi-jiu-dian" in tai_urban["source_url"]

    eda_royal = by_hotel["eda_royal"]
    assert eda_royal["status"] == "no_availability"
    assert eda_royal["check_in"] == "2026-12-06"
    assert eda_royal["check_out"] == "2026-12-07"
    assert "kaohsiung-e-da-world" in eda_royal["source_url"]

    nikko_kaohsiung = by_hotel["hotel_nikko_kaohsiung"]
    assert nikko_kaohsiung["status"] == "no_availability"
    assert nikko_kaohsiung["check_in"] == "2026-12-07"
    assert nikko_kaohsiung["check_out"] == "2026-12-08"
    assert "nikko-kaohsiung" in nikko_kaohsiung["source_url"]

    grand_hilai_kaohsiung = by_hotel["grand_hilai_kaohsiung"]
    assert grand_hilai_kaohsiung["status"] == "no_availability"
    assert grand_hilai_kaohsiung["check_in"] == "2026-12-08"
    assert grand_hilai_kaohsiung["check_out"] == "2026-12-09"
    assert "hanlai-da-fan-dian" in grand_hilai_kaohsiung["source_url"]

    sheraton_hsinchu = by_hotel["sheraton_hsinchu"]
    assert sheraton_hsinchu["status"] == "no_availability"
    assert sheraton_hsinchu["check_in"] == "2026-12-09"
    assert sheraton_hsinchu["check_out"] == "2026-12-10"
    assert "sheraton-hsinchu" in sheraton_hsinchu["source_url"]

    episode_hsinchu = by_hotel["episode_hsinchu"]
    assert episode_hsinchu["status"] == "no_availability"
    assert episode_hsinchu["check_in"] == "2026-12-10"
    assert episode_hsinchu["check_out"] == "2026-12-11"
    assert "miramar-hsinchu" in episode_hsinchu["source_url"]


def test_repository_visible_browser_snapshots_are_canonical_products():
    path = Path("data/ota_browser_snapshots.jsonl")
    rows = [
        RateObservation.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert {row.hotel_id for row in rows} >= {
        "capella_taipei",
        "w_taipei",
        "hotel_metropolitan_premier_taipei",
        "okura_prestige_taipei",
        "hotel_resonance_taipei",
        "doubletree_taipei_zhongshan",
        "humble_house_taipei",
        "kimpton_da_an",
        "episode_daan_taipei",
        "indigo_taipei_north",
        "hotel_proverbs_taipei",
        "le_meridien_taipei",
        "courtyard_taipei_downtown",
        "renaissance_taipei_shihlin",
        "howard_plaza_taipei",
        "intercontinental_taipei",
    }
    assert all(row.source_method == "visible_browser_snapshot" for row in rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in rows
        if row.tax_inclusion != "unknown"
    )
    w_rows = [row for row in rows if row.hotel_id == "w_taipei"]
    assert {row.breakfast_included for row in w_rows} == {False, True}
    latest_w_query = max(row.queried_at for row in w_rows)
    latest_w_rows = [row for row in w_rows if row.queried_at == latest_w_query]
    assert len(latest_w_rows) == 7
    assert len({row.room_type_code for row in latest_w_rows}) == 7
    assert {row.room_size_sqm for row in latest_w_rows} == {
        Decimal("43"), Decimal("46"), Decimal("70"), Decimal("95")
    }
    assert min(row.total_price for row in latest_w_rows) == Decimal("13860")
    assert max(row.total_price for row in latest_w_rows) == Decimal("25410")
    assert {row.source_platform for row in latest_w_rows} == {"expedia_group"}
    assert {row.breakfast_included for row in latest_w_rows} == {False}
    assert all(row.tax_inclusion == "included" for row in latest_w_rows)
    assert all(canonical_comparison_key(row) is not None for row in latest_w_rows)
    palais_rows = [row for row in rows if row.hotel_id == "palais_de_chine"]
    latest_palais_query = max(row.queried_at for row in palais_rows)
    palais_rows = [
        row for row in palais_rows if row.queried_at == latest_palais_query
    ]
    assert len(palais_rows) == 9
    assert len({row.room_type_code for row in palais_rows}) == 9
    assert {row.room_size_sqm for row in palais_rows} == {
        Decimal("30"), Decimal("37"), Decimal("50"), Decimal("67")
    }
    assert {row.breakfast_included for row in palais_rows} == {True}
    assert min(row.total_price for row in palais_rows) == Decimal("11829")
    assert max(row.total_price for row in palais_rows) == Decimal("20372")
    assert all(row.tax_inclusion == "unknown" for row in palais_rows)
    assert all(canonical_comparison_key(row) is None for row in palais_rows)
    jr_rows = [
        row for row in rows
        if row.hotel_id == "hotel_metropolitan_premier_taipei"
    ]
    latest_jr_query = max(row.queried_at for row in jr_rows)
    jr_rows = [row for row in jr_rows if row.queried_at == latest_jr_query]
    assert len(jr_rows) == 14
    assert len({row.room_type_code for row in jr_rows}) == 10
    assert {row.room_size_sqm for row in jr_rows} == {
        Decimal("36"), Decimal("43"), Decimal("62")
    }
    assert {row.breakfast_included for row in jr_rows} == {False, True}
    assert min(row.total_price for row in jr_rows) == Decimal("6975")
    assert max(row.total_price for row in jr_rows) == Decimal("13485")
    assert all(row.tax_inclusion == "unknown" for row in jr_rows)
    assert all(canonical_comparison_key(row) is None for row in jr_rows)
    okura_rows = [
        row for row in rows
        if row.hotel_id == "okura_prestige_taipei"
        and row.source_platform == "booking_com"
    ]
    latest_okura_query = max(row.queried_at for row in okura_rows)
    okura_rows = [row for row in okura_rows if row.queried_at == latest_okura_query]
    assert len(okura_rows) == 8
    assert len({row.room_type_code for row in okura_rows}) == 4
    assert {row.room_size_sqm for row in okura_rows} == {Decimal("44")}
    assert {row.breakfast_included for row in okura_rows} == {False, True}
    assert min(row.total_price for row in okura_rows) == Decimal("8384")
    assert max(row.total_price for row in okura_rows) == Decimal("12181")
    assert all(row.tax_inclusion == "unknown" for row in okura_rows)
    assert all(canonical_comparison_key(row) is None for row in okura_rows)
    okura_expedia_rows = [
        row for row in rows
        if row.hotel_id == "okura_prestige_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(okura_expedia_rows) == 4
    assert len({row.room_type_code for row in okura_expedia_rows}) == 4
    assert {row.room_size_sqm for row in okura_expedia_rows} == {Decimal("44")}
    assert {row.breakfast_included for row in okura_expedia_rows} == {False}
    assert min(row.total_price for row in okura_expedia_rows) == Decimal("8384")
    assert max(row.total_price for row in okura_expedia_rows) == Decimal("9419")
    assert all(row.tax_inclusion == "included" for row in okura_expedia_rows)
    assert all(canonical_comparison_key(row) is not None for row in okura_expedia_rows)
    mo_rows = [row for row in rows if row.hotel_id == "mo_taipei"]
    assert len(mo_rows) == 22
    hotels_com_mo = [
        row for row in mo_rows if row.source_platform == "expedia_group"
    ]
    assert len(hotels_com_mo) == 15
    assert {row.room_size_sqm for row in hotels_com_mo} == {
        Decimal("55"), Decimal("70"), Decimal("86"), Decimal("110"),
        Decimal("133")
    }
    assert min(row.total_price for row in hotels_com_mo) == Decimal("14079")
    assert max(row.total_price for row in hotels_com_mo) == Decimal("60684")
    assert all(row.tax_inclusion == "included" for row in hotels_com_mo)
    assert all(canonical_comparison_key(row) is not None for row in hotels_com_mo)
    shangrila_rows = [row for row in rows if row.hotel_id == "shangrila_taipei"]
    assert len(shangrila_rows) == 28
    booking_shangrila = [
        row for row in shangrila_rows if row.source_platform == "booking_com"
    ]
    hotels_com_shangrila = [
        row for row in shangrila_rows if row.source_platform == "expedia_group"
    ]
    assert len(booking_shangrila) == 10
    assert {row.room_size_sqm for row in booking_shangrila} == {
        Decimal("40"), Decimal("60"), Decimal("72")
    }
    assert all(row.tax_inclusion == "unknown" for row in booking_shangrila)
    assert all(canonical_comparison_key(row) is None for row in booking_shangrila)
    assert len(hotels_com_shangrila) == 18
    assert {row.room_size_sqm for row in hotels_com_shangrila} == {
        Decimal("36"), Decimal("40"), Decimal("41"), Decimal("56"),
        Decimal("60"), Decimal("75")
    }
    assert {row.breakfast_included for row in hotels_com_shangrila} == {
        False, True
    }
    assert min(row.total_price for row in hotels_com_shangrila) == Decimal("8830")
    assert max(row.total_price for row in hotels_com_shangrila) == Decimal("27203")
    assert all(row.tax_inclusion == "included" for row in hotels_com_shangrila)
    assert all(
        canonical_comparison_key(row) is not None for row in hotels_com_shangrila
    )
    royal_nikko_rows = [
        row for row in rows if row.hotel_id == "royal_nikko_taipei"
    ]
    assert len(royal_nikko_rows) == 7
    assert {row.source_platform for row in royal_nikko_rows} == {
        "expedia_group"
    }
    assert {row.room_size_sqm for row in royal_nikko_rows} == {
        Decimal("32"), Decimal("38"), Decimal("65")
    }
    assert {row.breakfast_included for row in royal_nikko_rows} == {False, True}
    assert min(row.total_price for row in royal_nikko_rows) == Decimal("6732")
    assert max(row.total_price for row in royal_nikko_rows) == Decimal("13690")
    assert all(row.tax_inclusion == "included" for row in royal_nikko_rows)
    assert all(canonical_comparison_key(row) is not None for row in royal_nikko_rows)
    eslite_rows = [
        row for row in rows
        if row.hotel_id == "eslite_hotel"
        and row.source_platform == "expedia_group"
    ]
    assert len(eslite_rows) == 5
    assert {row.room_size_sqm for row in eslite_rows} == {
        Decimal("43"), Decimal("53"), Decimal("69")
    }
    assert {row.breakfast_included for row in eslite_rows} == {False}
    assert min(row.total_price for row in eslite_rows) == Decimal("7708")
    assert max(row.total_price for row in eslite_rows) == Decimal("12987")
    assert all(row.tax_inclusion == "included" for row in eslite_rows)
    assert all(canonical_comparison_key(row) is not None for row in eslite_rows)
    gaia_rows = [
        row for row in rows
        if row.hotel_id == "the_gaia_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(gaia_rows) == 4
    assert {row.room_size_sqm for row in gaia_rows} == {
        Decimal("36"), Decimal("50"), Decimal("66")
    }
    assert {row.breakfast_included for row in gaia_rows} == {True}
    assert min(row.total_price for row in gaia_rows) == Decimal("10292")
    assert max(row.total_price for row in gaia_rows) == Decimal("61358")
    assert all(row.tax_inclusion == "included" for row in gaia_rows)
    assert all(canonical_comparison_key(row) is not None for row in gaia_rows)
    solaria_rows = [
        row for row in rows
        if row.hotel_id == "solaria_nishitetsu_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(solaria_rows) == 8
    assert {row.room_size_sqm for row in solaria_rows} == {
        Decimal("21"), Decimal("23"), Decimal("24"), Decimal("26"),
        Decimal("33")
    }
    assert {row.breakfast_included for row in solaria_rows} == {False}
    assert min(row.total_price for row in solaria_rows) == Decimal("7645")
    assert max(row.total_price for row in solaria_rows) == Decimal("12385")
    assert all(row.tax_inclusion == "included" for row in solaria_rows)
    assert all(canonical_comparison_key(row) is not None for row in solaria_rows)
    grand_hotel_rows = [
        row for row in rows
        if row.hotel_id == "grand_hotel_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(grand_hotel_rows) == 4
    assert {row.room_size_sqm for row in grand_hotel_rows} == {
        Decimal("20"), Decimal("36"), Decimal("79")
    }
    assert {row.breakfast_included for row in grand_hotel_rows} == {False, True}
    assert min(row.total_price for row in grand_hotel_rows) == Decimal("4487")
    assert max(row.total_price for row in grand_hotel_rows) == Decimal("11928")
    assert all(row.tax_inclusion == "included" for row in grand_hotel_rows)
    assert all(canonical_comparison_key(row) is not None for row in grand_hotel_rows)
    grand_hilai_rows = [
        row for row in rows
        if row.hotel_id == "grand_hilai_taipei"
        and row.source_platform == "booking_com"
    ]
    assert len(grand_hilai_rows) == 5
    assert {row.room_size_sqm for row in grand_hilai_rows} == {
        Decimal("44"), Decimal("59")
    }
    assert {row.breakfast_included for row in grand_hilai_rows} == {False, True}
    assert {row.total_price for row in grand_hilai_rows} == {
        Decimal("7650"), Decimal("8925"), Decimal("19825")
    }
    assert all(row.tax_inclusion == "unknown" for row in grand_hilai_rows)
    assert all(canonical_comparison_key(row) is None for row in grand_hilai_rows)
    grand_hilai_expedia_rows = [
        row for row in rows
        if row.hotel_id == "grand_hilai_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(grand_hilai_expedia_rows) == 4
    assert {row.room_size_sqm for row in grand_hilai_expedia_rows} == {
        Decimal("44"), Decimal("59")
    }
    assert {row.breakfast_included for row in grand_hilai_expedia_rows} == {
        False, True
    }
    assert min(row.total_price for row in grand_hilai_expedia_rows) == Decimal("7488")
    assert max(row.total_price for row in grand_hilai_expedia_rows) == Decimal("16416")
    assert all(row.tax_inclusion == "included" for row in grand_hilai_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None for row in grand_hilai_expedia_rows
    )
    mayfull_rows = [
        row for row in rows
        if row.hotel_id == "grand_mayfull_taipei"
        and row.source_platform == "booking_com"
    ]
    assert len(mayfull_rows) == 12
    assert {row.room_size_sqm for row in mayfull_rows} == {
        Decimal("50"), Decimal("60"), Decimal("70"), Decimal("95"), Decimal("105")
    }
    assert {row.breakfast_included for row in mayfull_rows} == {False, True}
    assert min(row.total_price for row in mayfull_rows) == Decimal("6718")
    assert max(row.total_price for row in mayfull_rows) == Decimal("37884")
    assert all(row.tax_inclusion == "unknown" for row in mayfull_rows)
    assert all(canonical_comparison_key(row) is None for row in mayfull_rows)
    mayfull_expedia_rows = [
        row for row in rows
        if row.hotel_id == "grand_mayfull_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(mayfull_expedia_rows) == 5
    assert {row.room_size_sqm for row in mayfull_expedia_rows} == {
        Decimal("50"), Decimal("60"), Decimal("70"), Decimal("105")
    }
    assert {row.breakfast_included for row in mayfull_expedia_rows} == {False, True}
    assert min(row.total_price for row in mayfull_expedia_rows) == Decimal("20561")
    assert max(row.total_price for row in mayfull_expedia_rows) == Decimal("54830")
    assert all(row.tax_inclusion == "included" for row in mayfull_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None for row in mayfull_expedia_rows
    )
    grand_hyatt_rows = [row for row in rows if row.hotel_id == "grand_hyatt_taipei"]
    assert len(grand_hyatt_rows) == 38
    hotels_com_hyatt = [
        row for row in grand_hyatt_rows if row.source_platform == "expedia_group"
    ]
    assert len(hotels_com_hyatt) == 10
    assert {row.room_size_sqm for row in hotels_com_hyatt} == {
        Decimal("33"), Decimal("40"), Decimal("50"), Decimal("60"),
        Decimal("83")
    }
    assert min(row.total_price for row in hotels_com_hyatt) == Decimal("12017")
    assert max(row.total_price for row in hotels_com_hyatt) == Decimal("25156")
    assert all(row.tax_inclusion == "included" for row in hotels_com_hyatt)
    assert all(canonical_comparison_key(row) is not None for row in hotels_com_hyatt)
    sheraton_rows = [
        row for row in rows
        if row.hotel_id == "sheraton_grand_taipei"
        and row.source_platform == "booking_com"
    ]
    latest_sheraton_query = max(row.queried_at for row in sheraton_rows)
    sheraton_rows = [
        row for row in sheraton_rows if row.queried_at == latest_sheraton_query
    ]
    assert len(sheraton_rows) == 14
    assert {row.room_size_sqm for row in sheraton_rows} == {
        Decimal("32"), Decimal("35"), Decimal("40")
    }
    assert {row.breakfast_included for row in sheraton_rows} == {False, True}
    assert min(row.total_price for row in sheraton_rows) == Decimal("9240")
    assert max(row.total_price for row in sheraton_rows) == Decimal("12821")
    assert all(row.tax_inclusion == "unknown" for row in sheraton_rows)
    assert all(canonical_comparison_key(row) is None for row in sheraton_rows)

    sheraton_expedia_rows = [
        row for row in rows
        if row.hotel_id == "sheraton_grand_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(sheraton_expedia_rows) == 7
    assert {row.room_size_sqm for row in sheraton_expedia_rows} == {
        Decimal("32"), Decimal("35"), Decimal("40")
    }
    assert {row.breakfast_included for row in sheraton_expedia_rows} == {False}
    assert min(row.total_price for row in sheraton_expedia_rows) == Decimal("8501")
    assert max(row.total_price for row in sheraton_expedia_rows) == Decimal("11550")
    assert all(row.tax_inclusion == "included" for row in sheraton_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in sheraton_expedia_rows
    )

    grand_view_expedia_rows = [
        row for row in rows
        if row.hotel_id == "grand_view_resort_beitou"
        and row.source_platform == "expedia_group"
    ]
    assert len(grand_view_expedia_rows) == 7
    assert {row.room_size_sqm for row in grand_view_expedia_rows} == {
        Decimal("49"), Decimal("50"), Decimal("56"), Decimal("63")
    }
    assert {row.breakfast_included for row in grand_view_expedia_rows} == {True}
    assert min(row.total_price for row in grand_view_expedia_rows) == Decimal("15725")
    assert max(row.total_price for row in grand_view_expedia_rows) == Decimal("27572")
    assert all(row.tax_inclusion == "included" for row in grand_view_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in grand_view_expedia_rows
    )

    kagaya_expedia_rows = [
        row for row in rows
        if row.hotel_id == "radium_kagaya_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(kagaya_expedia_rows) == 11
    assert {row.room_size_sqm for row in kagaya_expedia_rows} == {
        Decimal("43"), Decimal("50"), Decimal("52"), Decimal("53")
    }
    assert {row.breakfast_included for row in kagaya_expedia_rows} == {False, True}
    assert min(row.total_price for row in kagaya_expedia_rows) == Decimal("15447")
    assert max(row.total_price for row in kagaya_expedia_rows) == Decimal("38144")
    assert all(row.tax_inclusion == "included" for row in kagaya_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in kagaya_expedia_rows
    )

    resonance_rows = [
        row for row in rows if row.hotel_id == "hotel_resonance_taipei"
    ]
    assert len(resonance_rows) == 2
    assert {row.room_size_sqm for row in resonance_rows} == {Decimal("30")}
    assert {row.breakfast_included for row in resonance_rows} == {False, True}
    assert {row.total_price for row in resonance_rows} == {
        Decimal("10395"), Decimal("10857")
    }
    assert all(row.tax_inclusion == "unknown" for row in resonance_rows)
    assert all(canonical_comparison_key(row) is None for row in resonance_rows)

    doubletree_rows = [
        row for row in rows
        if row.hotel_id == "doubletree_taipei_zhongshan"
        and row.source_platform == "booking_com"
    ]
    assert len(doubletree_rows) == 4
    assert {row.room_size_sqm for row in doubletree_rows} == {
        Decimal("33"), Decimal("46")
    }
    assert {row.breakfast_included for row in doubletree_rows} == {False, True}
    assert min(row.total_price for row in doubletree_rows) == Decimal("11204")
    assert max(row.total_price for row in doubletree_rows) == Decimal("16748")
    assert all(row.tax_inclusion == "unknown" for row in doubletree_rows)
    assert all(canonical_comparison_key(row) is None for row in doubletree_rows)

    doubletree_expedia_rows = [
        row for row in rows
        if row.hotel_id == "doubletree_taipei_zhongshan"
        and row.source_platform == "expedia_group"
    ]
    assert len(doubletree_expedia_rows) == 6
    assert {row.room_size_sqm for row in doubletree_expedia_rows} == {
        Decimal("33"), Decimal("35"), Decimal("36"), Decimal("46")
    }
    assert {row.breakfast_included for row in doubletree_expedia_rows} == {False}
    assert min(row.total_price for row in doubletree_expedia_rows) == Decimal("6699")
    assert max(row.total_price for row in doubletree_expedia_rows) == Decimal("12243")
    assert all(row.tax_inclusion == "included" for row in doubletree_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in doubletree_expedia_rows
    )

    humble_house_rows = [
        row for row in rows
        if row.hotel_id == "humble_house_taipei"
        and row.source_platform == "booking_com"
    ]
    assert len(humble_house_rows) == 4
    assert {row.room_size_sqm for row in humble_house_rows} == {
        Decimal("26"), Decimal("36")
    }
    assert {row.breakfast_included for row in humble_house_rows} == {False}
    assert min(row.total_price for row in humble_house_rows) == Decimal("10395")
    assert max(row.total_price for row in humble_house_rows) == Decimal("13282")
    assert all(row.tax_inclusion == "unknown" for row in humble_house_rows)
    assert all(canonical_comparison_key(row) is None for row in humble_house_rows)

    humble_house_expedia_rows = [
        row for row in rows
        if row.hotel_id == "humble_house_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(humble_house_expedia_rows) == 8
    assert {row.room_size_sqm for row in humble_house_expedia_rows} == {
        Decimal("26"), Decimal("36"), Decimal("53")
    }
    assert {row.breakfast_included for row in humble_house_expedia_rows} == {
        False
    }
    assert min(row.total_price for row in humble_house_expedia_rows) == Decimal("10395")
    assert max(row.total_price for row in humble_house_expedia_rows) == Decimal("20790")
    assert all(row.tax_inclusion == "included" for row in humble_house_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in humble_house_expedia_rows
    )

    taipei_marriott_expedia_rows = [
        row for row in rows
        if row.hotel_id == "taipei_marriott"
        and row.source_platform == "expedia_group"
    ]
    assert len(taipei_marriott_expedia_rows) == 16
    assert {row.room_size_sqm for row in taipei_marriott_expedia_rows} == {
        Decimal("40"), Decimal("43"), Decimal("51"), Decimal("66"),
        Decimal("79")
    }
    assert {row.breakfast_included for row in taipei_marriott_expedia_rows} == {
        False
    }
    assert min(row.total_price for row in taipei_marriott_expedia_rows) == Decimal("7928")
    assert max(row.total_price for row in taipei_marriott_expedia_rows) == Decimal("47702")
    assert all(row.tax_inclusion == "included" for row in taipei_marriott_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in taipei_marriott_expedia_rows
    )

    kimpton_rows = [
        row for row in rows
        if row.hotel_id == "kimpton_da_an"
        and row.source_platform == "booking_com"
    ]
    latest_kimpton_query = max(row.queried_at for row in kimpton_rows)
    kimpton_rows = [
        row for row in kimpton_rows if row.queried_at == latest_kimpton_query
    ]
    assert len(kimpton_rows) == 11
    assert {row.room_size_sqm for row in kimpton_rows} == {
        Decimal("32"), Decimal("37"), Decimal("38"), Decimal("58")
    }
    assert {row.breakfast_included for row in kimpton_rows} == {False}
    assert min(row.total_price for row in kimpton_rows) == Decimal("11689")
    assert max(row.total_price for row in kimpton_rows) == Decimal("24394")
    assert all(row.tax_inclusion == "unknown" for row in kimpton_rows)
    assert all(canonical_comparison_key(row) is None for row in kimpton_rows)

    kimpton_expedia_rows = [
        row for row in rows
        if row.hotel_id == "kimpton_da_an"
        and row.source_platform == "expedia_group"
    ]
    assert len(kimpton_expedia_rows) == 4
    assert {row.room_size_sqm for row in kimpton_expedia_rows} == {
        Decimal("37"), Decimal("38")
    }
    assert {row.breakfast_included for row in kimpton_expedia_rows} == {False}
    assert min(row.total_price for row in kimpton_expedia_rows) == Decimal("22061")
    assert max(row.total_price for row in kimpton_expedia_rows) == Decimal("29395")
    assert all(row.tax_inclusion == "included" for row in kimpton_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in kimpton_expedia_rows
    )

    taipei_garden_expedia_rows = [
        row for row in rows
        if row.hotel_id == "taipei_garden_hotel"
        and row.source_platform == "expedia_group"
    ]
    assert len(taipei_garden_expedia_rows) == 9
    assert {row.room_size_sqm for row in taipei_garden_expedia_rows} == {
        Decimal("31"), Decimal("34"), Decimal("35")
    }
    assert {row.breakfast_included for row in taipei_garden_expedia_rows} == {
        False
    }
    assert min(row.total_price for row in taipei_garden_expedia_rows) == Decimal("13855")
    assert max(row.total_price for row in taipei_garden_expedia_rows) == Decimal("16957")
    assert all(row.tax_inclusion == "included" for row in taipei_garden_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in taipei_garden_expedia_rows
    )

    intercontinental_taichung_expedia_rows = [
        row for row in rows
        if row.hotel_id == "intercontinental_taichung"
        and row.source_platform == "expedia_group"
    ]
    assert len(intercontinental_taichung_expedia_rows) == 9
    assert {row.room_size_sqm for row in intercontinental_taichung_expedia_rows} == {
        Decimal("40"), Decimal("55")
    }
    assert {row.breakfast_included for row in intercontinental_taichung_expedia_rows} == {
        False
    }
    assert min(row.total_price for row in intercontinental_taichung_expedia_rows) == Decimal("11907")
    assert max(row.total_price for row in intercontinental_taichung_expedia_rows) == Decimal("18664")
    assert all(row.tax_inclusion == "included" for row in intercontinental_taichung_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in intercontinental_taichung_expedia_rows
    )

    the_lin_taichung_expedia_rows = [
        row for row in rows
        if row.hotel_id == "the_lin_taichung"
        and row.source_platform == "expedia_group"
    ]
    assert len(the_lin_taichung_expedia_rows) == 13
    assert {row.room_size_sqm for row in the_lin_taichung_expedia_rows} == {
        Decimal("50"), Decimal("53"), Decimal("56"), Decimal("63")
    }
    assert {row.breakfast_included for row in the_lin_taichung_expedia_rows} == {
        False, True
    }
    assert min(row.total_price for row in the_lin_taichung_expedia_rows) == Decimal("4748")
    assert max(row.total_price for row in the_lin_taichung_expedia_rows) == Decimal("10633")
    assert all(row.tax_inclusion == "included" for row in the_lin_taichung_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in the_lin_taichung_expedia_rows
    )

    millennium_taichung_expedia_rows = [
        row for row in rows
        if row.hotel_id == "millennium_taichung"
        and row.source_platform == "expedia_group"
    ]
    assert len(millennium_taichung_expedia_rows) == 6
    assert {row.room_size_sqm for row in millennium_taichung_expedia_rows} == {
        Decimal("32"), Decimal("36"), Decimal("53")
    }
    assert {row.breakfast_included for row in millennium_taichung_expedia_rows} == {
        False, True
    }
    assert min(row.total_price for row in millennium_taichung_expedia_rows) == Decimal("3690")
    assert max(row.total_price for row in millennium_taichung_expedia_rows) == Decimal("8735")
    assert all(row.tax_inclusion == "included" for row in millennium_taichung_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in millennium_taichung_expedia_rows
    )

    le_meridien_taichung_expedia_rows = [
        row for row in rows
        if row.hotel_id == "le_meridien_taichung"
        and row.source_platform == "expedia_group"
    ]
    assert len(le_meridien_taichung_expedia_rows) == 2
    assert {row.room_size_sqm for row in le_meridien_taichung_expedia_rows} == {
        Decimal("43")
    }
    assert {row.breakfast_included for row in le_meridien_taichung_expedia_rows} == {
        False
    }
    assert {row.total_price for row in le_meridien_taichung_expedia_rows} == {
        Decimal("7277")
    }
    assert all(row.tax_inclusion == "included" for row in le_meridien_taichung_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in le_meridien_taichung_expedia_rows
    )

    windsor_taichung_expedia_rows = [
        row for row in rows
        if row.hotel_id == "windsor_taichung"
        and row.source_platform == "expedia_group"
    ]
    assert len(windsor_taichung_expedia_rows) == 5
    assert {row.room_size_sqm for row in windsor_taichung_expedia_rows} == {
        Decimal("31"), Decimal("37"), Decimal("41"), Decimal("76")
    }
    assert {row.breakfast_included for row in windsor_taichung_expedia_rows} == {
        False, True
    }
    assert min(row.total_price for row in windsor_taichung_expedia_rows) == Decimal("5848")
    assert max(row.total_price for row in windsor_taichung_expedia_rows) == Decimal("14553")
    assert all(row.tax_inclusion == "included" for row in windsor_taichung_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in windsor_taichung_expedia_rows
    )

    intercontinental_kaohsiung_expedia_rows = [
        row for row in rows
        if row.hotel_id == "intercontinental_kaohsiung"
        and row.source_platform == "expedia_group"
    ]
    assert len(intercontinental_kaohsiung_expedia_rows) == 9
    assert {row.room_size_sqm for row in intercontinental_kaohsiung_expedia_rows} == {
        Decimal("36"), Decimal("46"), Decimal("56")
    }
    assert {row.breakfast_included for row in intercontinental_kaohsiung_expedia_rows} == {
        False
    }
    assert min(row.total_price for row in intercontinental_kaohsiung_expedia_rows) == Decimal("7830")
    assert max(row.total_price for row in intercontinental_kaohsiung_expedia_rows) == Decimal("16860")
    assert all(row.tax_inclusion == "included" for row in intercontinental_kaohsiung_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in intercontinental_kaohsiung_expedia_rows
    )

    kaohsiung_marriott_expedia_rows = [
        row for row in rows
        if row.hotel_id == "kaohsiung_marriott"
        and row.source_platform == "expedia_group"
    ]
    assert len(kaohsiung_marriott_expedia_rows) == 8
    assert {row.room_size_sqm for row in kaohsiung_marriott_expedia_rows} == {
        Decimal("46"), Decimal("69"), Decimal("92")
    }
    assert {row.breakfast_included for row in kaohsiung_marriott_expedia_rows} == {False}
    assert min(row.total_price for row in kaohsiung_marriott_expedia_rows) == Decimal("5387")
    assert max(row.total_price for row in kaohsiung_marriott_expedia_rows) == Decimal("16364")
    assert all(row.tax_inclusion == "included" for row in kaohsiung_marriott_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in kaohsiung_marriott_expedia_rows
    )

    courtyard_downtown_expedia_rows = [
        row for row in rows
        if row.hotel_id == "courtyard_taipei_downtown"
        and row.source_platform == "expedia_group"
    ]
    assert len(courtyard_downtown_expedia_rows) == 4
    assert {row.room_size_sqm for row in courtyard_downtown_expedia_rows} == {Decimal("30")}
    assert {row.breakfast_included for row in courtyard_downtown_expedia_rows} == {False}
    assert min(row.total_price for row in courtyard_downtown_expedia_rows) == Decimal("10973")
    assert max(row.total_price for row in courtyard_downtown_expedia_rows) == Decimal("15362")
    assert all(row.tax_inclusion == "included" for row in courtyard_downtown_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in courtyard_downtown_expedia_rows
    )

    courtyard_expedia_rows = [
        row for row in rows
        if row.hotel_id == "courtyard_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(courtyard_expedia_rows) == 2
    assert {row.room_size_sqm for row in courtyard_expedia_rows} == {
        Decimal("62"), Decimal("90")
    }
    assert {row.breakfast_included for row in courtyard_expedia_rows} == {True}
    assert min(row.total_price for row in courtyard_expedia_rows) == Decimal("18480")
    assert max(row.total_price for row in courtyard_expedia_rows) == Decimal("20790")
    assert all(row.tax_inclusion == "included" for row in courtyard_expedia_rows)
    assert all(canonical_comparison_key(row) is not None for row in courtyard_expedia_rows)

    episode_rows = [
        row for row in rows
        if row.hotel_id == "episode_daan_taipei"
        and row.source_platform == "booking_com"
    ]
    assert len(episode_rows) == 8
    assert {row.room_size_sqm for row in episode_rows} == {
        Decimal("30"), Decimal("33"), Decimal("36")
    }
    assert {row.breakfast_included for row in episode_rows} == {False, True}
    assert min(row.total_price for row in episode_rows) == Decimal("8432")
    assert max(row.total_price for row in episode_rows) == Decimal("10164")
    assert all(row.tax_inclusion == "unknown" for row in episode_rows)
    assert all(canonical_comparison_key(row) is None for row in episode_rows)

    episode_expedia_rows = [
        row for row in rows
        if row.hotel_id == "episode_daan_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(episode_expedia_rows) == 5
    assert {row.room_size_sqm for row in episode_expedia_rows} == {
        Decimal("30"), Decimal("36")
    }
    assert {row.breakfast_included for row in episode_expedia_rows} == {False}
    assert min(row.total_price for row in episode_expedia_rows) == Decimal("13052")
    assert max(row.total_price for row in episode_expedia_rows) == Decimal("13629")
    assert all(row.tax_inclusion == "included" for row in episode_expedia_rows)
    assert all(canonical_comparison_key(row) is not None for row in episode_expedia_rows)

    indigo_rows = [
        row for row in rows
        if row.hotel_id == "indigo_taipei_north"
        and row.source_platform == "booking_com"
    ]
    assert len(indigo_rows) == 8
    assert {row.room_size_sqm for row in indigo_rows} == {
        Decimal("35"), Decimal("36"), Decimal("40"), Decimal("60")
    }
    assert {row.breakfast_included for row in indigo_rows} == {False, True}
    assert min(row.total_price for row in indigo_rows) == Decimal("7213")
    assert max(row.total_price for row in indigo_rows) == Decimal("12988")
    assert all(row.tax_inclusion == "included" for row in indigo_rows)
    assert all(canonical_comparison_key(row) is not None for row in indigo_rows)

    indigo_expedia_rows = [
        row for row in rows
        if row.hotel_id == "indigo_taipei_north"
        and row.source_platform == "expedia_group"
    ]
    assert len(indigo_expedia_rows) == 6
    assert {row.room_size_sqm for row in indigo_expedia_rows} == {
        Decimal("36"), Decimal("40"), Decimal("60"), Decimal("73")
    }
    assert {row.breakfast_included for row in indigo_expedia_rows} == {False}
    assert min(row.total_price for row in indigo_expedia_rows) == Decimal("5523")
    assert max(row.total_price for row in indigo_expedia_rows) == Decimal("11298")
    assert all(row.tax_inclusion == "included" for row in indigo_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None for row in indigo_expedia_rows
    )

    proverbs_rows = [
        row for row in rows
        if row.hotel_id == "hotel_proverbs_taipei"
        and row.source_platform == "booking_com"
    ]
    assert len(proverbs_rows) == 8
    assert {row.room_size_sqm for row in proverbs_rows} == {
        Decimal("33"), Decimal("37"), Decimal("38"), Decimal("41")
    }
    assert {row.breakfast_included for row in proverbs_rows} == {False, True}
    assert min(row.total_price for row in proverbs_rows) == Decimal("8270")
    assert max(row.total_price for row in proverbs_rows) == Decimal("10950")
    assert all(row.tax_inclusion == "unknown" for row in proverbs_rows)
    assert all(canonical_comparison_key(row) is None for row in proverbs_rows)

    proverbs_expedia_rows = [
        row for row in rows
        if row.hotel_id == "hotel_proverbs_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(proverbs_expedia_rows) == 3
    assert {row.room_size_sqm for row in proverbs_expedia_rows} == {
        Decimal("37"), Decimal("38"), Decimal("41")
    }
    assert {row.breakfast_included for row in proverbs_expedia_rows} == {False}
    assert min(row.total_price for row in proverbs_expedia_rows) == Decimal("14621")
    assert max(row.total_price for row in proverbs_expedia_rows) == Decimal("17363")
    assert all(row.tax_inclusion == "included" for row in proverbs_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None for row in proverbs_expedia_rows
    )

    le_meridien_booking_rows = [
        row for row in rows
        if row.hotel_id == "le_meridien_taipei"
        and row.source_platform == "booking_com"
    ]
    assert len(le_meridien_booking_rows) == 18
    assert {row.room_size_sqm for row in le_meridien_booking_rows} == {
        Decimal("38"), Decimal("60"), Decimal("75")
    }
    assert {row.breakfast_included for row in le_meridien_booking_rows} == {False, True}
    assert min(row.total_price for row in le_meridien_booking_rows) == Decimal("15015")
    assert max(row.total_price for row in le_meridien_booking_rows) == Decimal("57981")
    assert all(row.tax_inclusion == "unknown" for row in le_meridien_booking_rows)
    assert all(canonical_comparison_key(row) is None for row in le_meridien_booking_rows)

    le_meridien_expedia_rows = [
        row for row in rows
        if row.hotel_id == "le_meridien_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(le_meridien_expedia_rows) == 9
    assert {row.room_size_sqm for row in le_meridien_expedia_rows} == {
        Decimal("35"), Decimal("38"), Decimal("60"), Decimal("75")
    }
    assert {row.breakfast_included for row in le_meridien_expedia_rows} == {False}
    assert min(row.total_price for row in le_meridien_expedia_rows) == Decimal("15015")
    assert max(row.total_price for row in le_meridien_expedia_rows) == Decimal("56364")
    assert all(row.tax_inclusion == "included" for row in le_meridien_expedia_rows)
    assert all(canonical_comparison_key(row) is not None for row in le_meridien_expedia_rows)

    courtyard_downtown_rows = [
        row for row in rows
        if row.hotel_id == "courtyard_taipei_downtown"
        and row.source_platform == "booking_com"
    ]
    assert len(courtyard_downtown_rows) == 12
    assert {row.room_size_sqm for row in courtyard_downtown_rows} == {
        Decimal("28"), Decimal("30")
    }
    assert {row.breakfast_included for row in courtyard_downtown_rows} == {
        False, True
    }
    assert min(row.total_price for row in courtyard_downtown_rows) == Decimal("7508")
    assert max(row.total_price for row in courtyard_downtown_rows) == Decimal("10164")
    assert all(row.tax_inclusion == "unknown" for row in courtyard_downtown_rows)
    assert all(
        canonical_comparison_key(row) is None for row in courtyard_downtown_rows
    )

    renaissance_rows = [
        row for row in rows
        if row.hotel_id == "renaissance_taipei_shihlin"
        and row.source_platform == "booking_com"
    ]
    assert len(renaissance_rows) == 7
    assert {row.room_size_sqm for row in renaissance_rows} == {Decimal("31")}
    assert {row.breakfast_included for row in renaissance_rows} == {False, True}
    assert min(row.total_price for row in renaissance_rows) == Decimal("7415")
    assert max(row.total_price for row in renaissance_rows) == Decimal("9516")
    assert all(row.tax_inclusion == "unknown" for row in renaissance_rows)
    assert all(canonical_comparison_key(row) is None for row in renaissance_rows)

    renaissance_expedia_rows = [
        row for row in rows
        if row.hotel_id == "renaissance_taipei_shihlin"
        and row.source_platform == "expedia_group"
    ]
    assert len(renaissance_expedia_rows) == 2
    assert {row.room_size_sqm for row in renaissance_expedia_rows} == {Decimal("31")}
    assert {row.breakfast_included for row in renaissance_expedia_rows} == {False}
    assert min(row.total_price for row in renaissance_expedia_rows) == Decimal("12689")
    assert max(row.total_price for row in renaissance_expedia_rows) == Decimal("13489")
    assert all(row.tax_inclusion == "included" for row in renaissance_expedia_rows)
    assert all(canonical_comparison_key(row) is not None for row in renaissance_expedia_rows)

    howard_rows = [
        row for row in rows
        if row.hotel_id == "howard_plaza_taipei"
        and row.source_platform == "booking_com"
    ]
    assert len(howard_rows) == 4
    assert {row.room_size_sqm for row in howard_rows} == {
        Decimal("20"), Decimal("26")
    }
    assert {row.breakfast_included for row in howard_rows} == {False, True}
    assert {row.total_price for row in howard_rows} == {
        Decimal("5850"), Decimal("7050")
    }
    assert all(row.tax_inclusion == "unknown" for row in howard_rows)
    assert all(canonical_comparison_key(row) is None for row in howard_rows)

    howard_expedia_rows = [
        row for row in rows
        if row.hotel_id == "howard_plaza_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(howard_expedia_rows) == 2
    assert {row.room_size_sqm for row in howard_expedia_rows} == {
        Decimal("20"), Decimal("26")
    }
    assert {row.breakfast_included for row in howard_expedia_rows} == {False}
    assert {row.total_price for row in howard_expedia_rows} == {Decimal("5350")}
    assert all(row.tax_inclusion == "included" for row in howard_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None for row in howard_expedia_rows
    )

    miramar_expedia_rows = [
        row for row in rows
        if row.hotel_id == "miramar_garden_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(miramar_expedia_rows) == 9
    assert {row.room_size_sqm for row in miramar_expedia_rows} == {
        Decimal("42"), Decimal("89")
    }
    assert {row.breakfast_included for row in miramar_expedia_rows} == {
        False, True
    }
    assert min(row.total_price for row in miramar_expedia_rows) == Decimal("3671")
    assert max(row.total_price for row in miramar_expedia_rows) == Decimal("6257")
    assert all(row.tax_inclusion == "included" for row in miramar_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None for row in miramar_expedia_rows
    )

    intercontinental_rows = [
        row for row in rows
        if row.hotel_id == "intercontinental_taipei"
        and row.source_platform == "booking_com"
    ]
    assert len(intercontinental_rows) == 12
    assert {row.room_size_sqm for row in intercontinental_rows} == {
        Decimal("38"), Decimal("43"), Decimal("76")
    }
    assert {row.breakfast_included for row in intercontinental_rows} == {False, True}
    assert min(row.total_price for row in intercontinental_rows) == Decimal("12936")
    assert max(row.total_price for row in intercontinental_rows) == Decimal("31554")
    assert all(row.tax_inclusion == "unknown" for row in intercontinental_rows)
    assert all(
        canonical_comparison_key(row) is None for row in intercontinental_rows
    )

    intercontinental_expedia_rows = [
        row for row in rows
        if row.hotel_id == "intercontinental_taipei"
        and row.source_platform == "expedia_group"
    ]
    assert len(intercontinental_expedia_rows) == 6
    assert {row.room_size_sqm for row in intercontinental_expedia_rows} == {
        Decimal("38"), Decimal("48")
    }
    assert {row.breakfast_included for row in intercontinental_expedia_rows} == {
        False
    }
    assert min(row.total_price for row in intercontinental_expedia_rows) == Decimal("16262")
    assert max(row.total_price for row in intercontinental_expedia_rows) == Decimal("22107")
    assert all(row.tax_inclusion == "included" for row in intercontinental_expedia_rows)
    assert all(
        canonical_comparison_key(row) is not None
        for row in intercontinental_expedia_rows
    )


def test_ota_mapping_loader_ignores_blank_property_ids(tmp_path):
    config = tmp_path / "ota.yaml"
    config.write_text(
        "providers:\n  booking_com:\n    enabled: true\n    properties:\n"
        "      capella_taipei: '123456'\n      mo_taipei: ''\n",
        encoding="utf-8",
    )
    enabled, mappings = load_ota_property_mappings(config, "booking_com")
    assert enabled is True
    assert mappings == {"capella_taipei": "123456"}
