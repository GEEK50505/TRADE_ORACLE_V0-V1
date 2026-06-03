import importlib


def test_build_report_marks_runtime_state_failure_as_blocker(monkeypatch):
    readiness = importlib.import_module("scripts.check_forward_test_readiness")
    settings = importlib.import_module("config.settings")

    monkeypatch.setenv("TRADE_ORACLE_TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TRADE_ORACLE_TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("SUPABASE_URL", "https://supabase.example.test")
    monkeypatch.setenv("SUPABASE_KEY", "service-role-key")
    monkeypatch.setenv("MT5_LOGIN", "123")
    monkeypatch.setenv("MT5_PASSWORD", "secret")
    monkeypatch.setenv("MT5_SERVER", "FTMO-Demo")

    monkeypatch.setattr(settings, "TRADE_ORACLE_EXECUTION_BACKEND", "mt5")
    monkeypatch.setattr(settings, "TRADE_ORACLE_AUDIT_BACKEND", "supabase")
    monkeypatch.setattr(settings, "TRADE_ORACLE_BENCHMARK_BACKEND", "supabase")
    monkeypatch.setattr(settings, "TRADE_ORACLE_RUNTIME_STATE_BACKEND", "supabase")
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://supabase.example.test")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "service-role-key")
    monkeypatch.setattr(
        readiness,
        "_read_runtime_state",
        lambda *_args, **_kwargs: {
            "ok": False,
            "backend": "supabase",
            "error_type": "ConnectError",
            "message": "network down",
        },
    )
    monkeypatch.setattr(
        readiness,
        "_check_supabase_tables",
        lambda *_args, **_kwargs: {"ok": True, "checked": True, "tables": []},
    )

    report = readiness.build_report(env_file="does-not-exist.env", check_supabase=True)

    assert "runtime_state_probe_failed" in report["blockers"]
    assert report["ready_for_forward_testing_start"] is False


def test_build_report_allows_forward_testing_start_with_only_open_review(monkeypatch):
    readiness = importlib.import_module("scripts.check_forward_test_readiness")
    settings = importlib.import_module("config.settings")

    monkeypatch.setenv("TRADE_ORACLE_TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TRADE_ORACLE_TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("SUPABASE_URL", "https://supabase.example.test")
    monkeypatch.setenv("SUPABASE_KEY", "service-role-key")
    monkeypatch.setenv("MT5_LOGIN", "123")
    monkeypatch.setenv("MT5_PASSWORD", "secret")
    monkeypatch.setenv("MT5_SERVER", "FTMO-Demo")

    monkeypatch.setattr(settings, "TRADE_ORACLE_EXECUTION_BACKEND", "mt5")
    monkeypatch.setattr(settings, "TRADE_ORACLE_AUDIT_BACKEND", "supabase")
    monkeypatch.setattr(settings, "TRADE_ORACLE_BENCHMARK_BACKEND", "supabase")
    monkeypatch.setattr(settings, "TRADE_ORACLE_RUNTIME_STATE_BACKEND", "supabase")
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://supabase.example.test")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "service-role-key")
    monkeypatch.setattr(
        readiness,
        "_read_runtime_state",
        lambda *_args, **_kwargs: {
            "ok": True,
            "backend": "supabase",
            "open_review_count": 1,
            "open_reviews": [{"thread_id": "thread-1"}],
            "telegram_update_offset_checkpoint_present": True,
        },
    )
    monkeypatch.setattr(
        readiness,
        "_check_supabase_tables",
        lambda *_args, **_kwargs: {"ok": True, "checked": True, "tables": []},
    )

    report = readiness.build_report(env_file="does-not-exist.env", check_supabase=True)

    assert "open_pending_review" in report["blockers"]
    assert report["startup_blockers"] == []
    assert report["ready_for_forward_testing_start"] is True
    assert report["ready_for_new_once_cycle"] is False
