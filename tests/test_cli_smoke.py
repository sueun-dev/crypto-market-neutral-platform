from __future__ import annotations


def test_cli_exit_option(monkeypatch, capsys) -> None:
    import builtins

    from overseas_exchange_hedge import cli

    monkeypatch.setattr(builtins, "input", lambda *args, **kwargs: "0")
    cli.main([])
    out = capsys.readouterr().out
    assert "Market-Neutral Workflow Selection" in out


def test_module_entrypoint(monkeypatch) -> None:
    import builtins

    monkeypatch.setattr(builtins, "input", lambda *args, **kwargs: "0")

    from overseas_exchange_hedge.__main__ import main

    main([])


def test_cli_named_mode_dispatch(monkeypatch) -> None:
    from overseas_exchange_hedge import cli

    called: list[str] = []
    monkeypatch.setattr(cli, "_run_overseas_auto_entry", lambda: called.append("auto"))
    cli.main(["contango-auto"])
    assert called == ["auto"]
