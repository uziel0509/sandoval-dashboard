from __future__ import annotations
import pytest, sys, os
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/var/www/sandoval")


def _mock_db_empty():
    db = MagicMock()
    r = MagicMock()
    r.fetchone.return_value = None
    r.fetchall.return_value = []
    db.execute.return_value = r
    return db


def test_build_push_payload_fields():
    from utils.notifications import _build_push_payload
    p = _build_push_payload(title="Test", body="Body", tag="t-1",
                            url="/admin/", entity_type="cita", entity_id=1)
    for k in ("title","body","icon","badge","tag","url","sound","vibrate","data"):
        assert k in p, f"missing key {k}"
    assert p["data"]["type"] == "cita"
    assert p["data"]["entity_id"] == 1
    assert "/assets/logo_sandoval_trans.png" in p["icon"]
    assert "/assets/sounds/notify.mp3" in p["sound"]
    assert isinstance(p["vibrate"], list)


def test_payload_title_truncated_at_80():
    from utils.notifications import _build_push_payload
    p = _build_push_payload(title="A"*200, body="B"*300, tag="t", url="/",
                            entity_type="test", entity_id=0)
    assert len(p["title"]) == 80
    assert len(p["body"]) == 200


def test_notify_admin_nueva_cita_no_row_returns_early():
    from utils.notifications import notify_admin_nueva_cita
    notify_admin_nueva_cita(_mock_db_empty(), 1, 999)


def test_notify_admin_resumen_dia_sin_actividad_no_push():
    from utils.notifications import notify_admin_resumen_dia
    db = MagicMock()
    res = MagicMock()
    res.fetchone.return_value = (0, 0.0)
    db.execute.return_value = res
    with patch("utils.flota.send_push_to_user") as m:
        notify_admin_resumen_dia(db, 1)
        m.assert_not_called()


def test_notify_cliente_listo_entrega_sin_cliente_no_push():
    from utils.notifications import notify_cliente_listo_entrega
    db = MagicMock()
    res = MagicMock()
    res.fetchone.return_value = ("O-001", "ABC123", None)
    db.execute.return_value = res
    with patch("utils.flota.send_push_to_user") as m:
        notify_cliente_listo_entrega(db, 1, "O-001")
        m.assert_not_called()


def test_notify_admin_nueva_cita_calls_execute():
    from utils.notifications import notify_admin_nueva_cita
    db = MagicMock()
    call_count = [0]
    def side(query, params=None):
        call_count[0] += 1
        res = MagicMock()
        s = str(query)
        if "FROM citas" in s:
            res.fetchone.return_value = (1, "2026-05-01", "09:00", "Mant", "Juan", "P", "A123")
        elif "push_subscriptions" in s or "usuario_id" in s:
            m2 = MagicMock()
            m2.__getitem__ = lambda s2, i: 42
            res.fetchall.return_value = [m2]
        else:
            res.fetchone.return_value = None
            res.fetchall.return_value = []
        return res
    db.execute.side_effect = side
    with patch("utils.flota.send_push_to_user"):
        notify_admin_nueva_cita(db, 1, 1)
    assert call_count[0] >= 1
