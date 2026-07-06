import config


def test_every_account_niche_exists():
    for name, acct in config.ACCOUNTS.items():
        assert acct.niche in config.NICHES, name


def test_every_account_niche_has_hashtags():
    for acct in config.ACCOUNTS.values():
        tags = config.HASHTAGS[acct.niche]
        assert len(tags["fixed"]) >= 3
        assert len(tags["pool"]) >= 4


def test_posting_paths_defined():
    assert config.OUTBOX_DIR == "outbox"
    assert config.POST_LOG_PATH == "posts.jsonl"
    assert config.CAPTION_TITLE_CHARS == 90
    assert config.POST_JITTER_MAX_S == 900
