def test_seed_lists_permissions() -> None:
    from app.seed import EMPLOYEE, PERMISSIONS
    assert len(PERMISSIONS) == 18
    assert {"purchase.read", "purchase.receive"} <= EMPLOYEE
    assert "user.manage" not in EMPLOYEE
