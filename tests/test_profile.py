import os
import sqlite3
import time

from uploader.tiktok_profile import (_CHROME_EPOCH_OFFSET_S,
                                     profile_logged_in)


def make_cookie_db(profile_dir, rows, modern=True):
    parts = ("Default", "Network", "Cookies") if modern \
        else ("Default", "Cookies")
    db = os.path.join(profile_dir, *parts)
    os.makedirs(os.path.dirname(db), exist_ok=True)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE cookies "
                "(name TEXT, host_key TEXT, expires_utc INTEGER)")
    con.executemany("INSERT INTO cookies VALUES (?, ?, ?)", rows)
    con.commit()
    con.close()


def chrome_ts(offset_s):
    return int((time.time() + _CHROME_EPOCH_OFFSET_S + offset_s) * 1_000_000)


def test_valid_sessionid_means_logged_in(tmp_path):
    make_cookie_db(str(tmp_path), [
        ("sessionid", ".tiktok.com", chrome_ts(90 * 86400))])
    assert profile_logged_in(str(tmp_path)) is True


def test_expired_or_missing_sessionid_is_not_logged_in(tmp_path):
    make_cookie_db(str(tmp_path), [
        ("sessionid", ".tiktok.com", chrome_ts(-60)),      # expired
        ("other", ".tiktok.com", chrome_ts(86400)),
        ("sessionid", ".example.com", chrome_ts(86400))])  # wrong site
    assert profile_logged_in(str(tmp_path)) is False


def test_legacy_cookie_db_location_works(tmp_path):
    make_cookie_db(str(tmp_path), [
        ("sessionid", ".tiktok.com", chrome_ts(86400))], modern=False)
    assert profile_logged_in(str(tmp_path)) is True


def test_no_profile_or_corrupt_db_is_false(tmp_path):
    assert profile_logged_in(str(tmp_path / "nope")) is False
    bad = tmp_path / "Default" / "Network"
    bad.mkdir(parents=True)
    (bad / "Cookies").write_bytes(b"not a sqlite file")
    assert profile_logged_in(str(tmp_path)) is False
