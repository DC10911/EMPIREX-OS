from core.modules.sandbox_runner import run_in_sandbox


def test_sandbox_unavailable_reported_honestly(monkeypatch):
    """כשאין Docker בסביבה — הסטטוס חייב לומר זאת בפירוש, לא לדמות הצלחה."""
    import core.modules.sandbox_runner as sandbox_module
    monkeypatch.setattr(sandbox_module, "docker_available", lambda: False)

    result = run_in_sandbox("print('hello')")

    assert result.status == "sandbox_unavailable"
    assert "Docker" in result.stderr
