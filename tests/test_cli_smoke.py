from __future__ import annotations


def test_cli_exit_option(monkeypatch, capsys) -> None:
    import builtins

    from overseas_exchange_hedge import cli

    monkeypatch.setattr(builtins, "input", lambda *args, **kwargs: "0")
    cli.main()
    out = capsys.readouterr().out
    assert "헤지 모드 선택" in out


def test_module_entrypoint(monkeypatch) -> None:
    import builtins

    monkeypatch.setattr(builtins, "input", lambda *args, **kwargs: "0")

    from overseas_exchange_hedge.__main__ import main

    main()
