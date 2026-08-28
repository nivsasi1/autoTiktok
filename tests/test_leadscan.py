from types import SimpleNamespace

import pytest

from leadscan import scan


def place(**kw):
    base = dict(place_id="p1", name="Shop", category="cafe", address="St 1",
                phone="03-000", maps_url="", website="", rating=4.5,
                reviews=100, lat=32.0, lng=34.8)
    base.update(kw)
    return scan.Place(**base)


def stub_get(monkeypatch, *, status=200, html="", url=None, raises=None):
    def fake_get(target, **_):
        if raises:
            raise raises
        return SimpleNamespace(status_code=status, text=html,
                               url=url if url is not None else target)
    monkeypatch.setattr(scan.requests, "get", fake_get)


def test_tiles_cover_bbox_and_scale_with_radius():
    bbox = (32.05, 34.79, 32.10, 34.84)
    coarse = scan.tile_centers(bbox, 400)
    fine = scan.tile_centers(bbox, 150)
    assert len(fine) > len(coarse) > 1
    assert all(bbox[0] <= lat <= bbox[2] + 1e-6 for lat, _ in fine)
    assert all(bbox[1] <= lng <= bbox[3] + 1e-6 for _, lng in fine)


def test_permanently_closed_places_are_dropped():
    assert scan.to_place({"id": "x", "businessStatus": "CLOSED_PERMANENTLY"}) is None
    assert scan.to_place({"id": "x", "businessStatus": "OPERATIONAL"}) is not None


def test_missing_website_needs_no_request():
    p = place(website="")
    scan.grade(p)                      # no stub: a request here would explode
    assert p.verdict == "NO_SITE"


@pytest.mark.parametrize("url", [
    "https://www.facebook.com/mycafe",
    "https://instagram.com/mycafe",
    "https://wa.me/972500000000",
])
def test_social_pages_are_not_websites(url):
    p = place(website=url)
    scan.grade(p)
    assert p.verdict == "SOCIAL_ONLY"


def test_retired_google_builder_is_dead_without_fetching():
    p = place(website="https://mycafe.business.site")
    scan.grade(p)
    assert p.verdict == "DEAD"


def test_unreachable_and_error_sites_are_dead(monkeypatch):
    stub_get(monkeypatch, raises=scan.requests.ConnectionError("dns"))
    p = place(website="https://gone.example")
    scan.grade(p)
    assert p.verdict == "DEAD" and p.notes == "ConnectionError"

    stub_get(monkeypatch, status=503)
    q = place(website="https://broken.example")
    scan.grade(q)
    assert q.verdict == "DEAD" and q.http_status == "503"


def test_parked_domain_detected_in_both_languages(monkeypatch):
    for html in ("<p>This domain may be for sale</p>", "<h1>האתר בבנייה</h1>"):
        stub_get(monkeypatch, html=html)
        p = place(website="https://parked.example")
        scan.grade(p)
        assert p.verdict == "PARKED"


def test_healthy_site_needs_https_and_mobile(monkeypatch):
    good = '<meta name="viewport" content="width=device-width">'
    stub_get(monkeypatch, html=good, url="https://good.example")
    p = place(website="https://good.example")
    scan.grade(p)
    assert p.verdict == "HEALTHY" and p.mobile_ok and p.https_ok

    stub_get(monkeypatch, html="<body>desktop only</body>", url="http://old.example")
    q = place(website="http://old.example")
    scan.grade(q)
    assert q.verdict == "WEAK"
    assert "no-mobile" in q.notes and "no-https" in q.notes


def test_score_ranks_dead_sites_above_healthy_and_rewards_demand():
    dead = place(verdict="DEAD", reviews=500)
    healthy = place(verdict="HEALTHY", reviews=500)
    quiet = place(verdict="DEAD", reviews=0)
    assert scan.score(dead) > scan.score(healthy)
    assert scan.score(dead) > scan.score(quiet)
    assert scan.score(dead) <= 100


def test_report_and_csv_round_trip(tmp_path, capsys):
    places = [place(place_id=str(i), verdict=v, score=scan.score(place(verdict=v)))
              for i, v in enumerate(["NO_SITE", "DEAD", "HEALTHY", "WEAK"])]
    scan.summarize(places, calls=3, area="Testville")
    out = capsys.readouterr().out
    assert "Testville" in out and "no real website" in out

    dest = tmp_path / "leads.csv"
    scan.write_csv(places, str(dest))
    rows = dest.read_text(encoding="utf-8-sig").splitlines()
    assert rows[0].startswith("score,verdict,name")
    assert len(rows) == 5
