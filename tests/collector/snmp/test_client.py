from __future__ import annotations

import pytest
from pysnmp.proto.rfc1902 import (
    Counter32,
    Counter64,
    Gauge32,
    Integer,
    Integer32,
    OctetString,
    Unsigned32,
)

from ixforge_collector.collector.snmp.client import _to_native


class TestToNative:
    @pytest.mark.parametrize(
        ("snmp_val", "expected"),
        [
            (Counter32(1000000), 1000000),
            (Counter64(9999999999), 9999999999),
            (Gauge32(100), 100),
            (Integer(1), 1),
            (Integer32(-5), -5),
            (Unsigned32(42), 42),
        ],
        ids=["counter32", "counter64", "gauge32", "integer", "integer32", "unsigned32"],
    )
    def test_integer_types_return_int(self, snmp_val: object, expected: int) -> None:
        result = _to_native(snmp_val)
        assert result == expected
        assert isinstance(result, int)

    def test_counter64_large_value(self) -> None:
        large = 2**64 - 1
        result = _to_native(Counter64(large))
        assert result == large
        assert isinstance(result, int)

    def test_octet_string_returns_str(self) -> None:
        result = _to_native(OctetString("GigabitEthernet0/0/1"))
        assert isinstance(result, str)
        assert "GigabitEthernet0/0/1" in result

    def test_counter32_zero(self) -> None:
        result = _to_native(Counter32(0))
        assert result == 0
        assert isinstance(result, int)
