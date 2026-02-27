import threading
from datetime import UTC, datetime

from ixforge_collector.collector.snmp.rate import RateCalculator


class TestRateCalculatorFirstPoll:
    def test_first_poll_returns_negative(self) -> None:
        calc = RateCalculator()
        rate = calc.calculate("switch1", "eth0", "octets_in", 5000, datetime.now(tz=UTC))
        assert rate == -1

    def test_different_metrics_independent_first_poll(self) -> None:
        calc = RateCalculator()
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        rate_in = calc.calculate("switch1", "eth0", "octets_in", 1000, ts)
        rate_out = calc.calculate("switch1", "eth0", "octets_out", 5000, ts)
        assert rate_in == -1
        assert rate_out == -1


class TestRateCalculatorNormalRate:
    def test_second_poll_calculates_rate(self) -> None:
        calc = RateCalculator()
        calc.calculate("switch1", "eth0", "octets_in", 1000, datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC))
        rate = calc.calculate("switch1", "eth0", "octets_in", 2000, datetime(2024, 1, 15, 10, 0, 10, tzinfo=UTC))
        assert rate == 100.0

    def test_multiple_interfaces(self) -> None:
        calc = RateCalculator()
        ts1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        ts2 = datetime(2024, 1, 15, 10, 0, 10, tzinfo=UTC)
        calc.calculate("switch1", "eth0", "octets_in", 1000, ts1)
        calc.calculate("switch1", "eth1", "octets_in", 2000, ts1)
        calc.calculate("switch2", "eth0", "octets_in", 3000, ts1)
        rate1 = calc.calculate("switch1", "eth0", "octets_in", 2000, ts2)
        rate2 = calc.calculate("switch1", "eth1", "octets_in", 4000, ts2)
        rate3 = calc.calculate("switch2", "eth0", "octets_in", 6000, ts2)
        assert rate1 == 100.0
        assert rate2 == 200.0
        assert rate3 == 300.0

    def test_multiple_metrics_same_interface(self) -> None:
        calc = RateCalculator()
        ts1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        ts2 = datetime(2024, 1, 15, 10, 0, 10, tzinfo=UTC)
        calc.calculate("switch1", "eth0", "octets_in", 1000, ts1)
        calc.calculate("switch1", "eth0", "octets_out", 5000, ts1)
        rate_in = calc.calculate("switch1", "eth0", "octets_in", 2000, ts2)
        rate_out = calc.calculate("switch1", "eth0", "octets_out", 10000, ts2)
        assert rate_in == 100.0
        assert rate_out == 500.0

    def test_zero_counter_delta_returns_zero(self) -> None:
        calc = RateCalculator()
        ts1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        ts2 = datetime(2024, 1, 15, 10, 0, 10, tzinfo=UTC)
        calc.calculate("switch1", "eth0", "octets_in", 5000, ts1)
        rate = calc.calculate("switch1", "eth0", "octets_in", 5000, ts2)
        assert rate == 0.0


class TestRateCalculatorCounterWrap:
    def test_counter_wrap(self) -> None:
        calc = RateCalculator()
        max_uint64 = 2**64 - 1
        calc.calculate("switch1", "eth0", "octets_in", max_uint64 - 1000, datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC))
        rate = calc.calculate("switch1", "eth0", "octets_in", 500, datetime(2024, 1, 15, 10, 0, 10, tzinfo=UTC))
        assert abs(rate - 150.1) < 0.1

    def test_counter_wrap_exact_max(self) -> None:
        calc = RateCalculator()
        max_uint64 = 2**64 - 1
        calc.calculate("switch1", "eth0", "octets_in", max_uint64, datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC))
        rate = calc.calculate("switch1", "eth0", "octets_in", 0, datetime(2024, 1, 15, 10, 0, 10, tzinfo=UTC))
        assert abs(rate - 0.1) < 0.01


class TestRateCalculatorTimeDelta:
    def test_zero_time_delta_returns_negative(self) -> None:
        calc = RateCalculator()
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        calc.calculate("switch1", "eth0", "octets_in", 1000, ts)
        rate = calc.calculate("switch1", "eth0", "octets_in", 2000, ts)
        assert rate == -1

    def test_negative_time_delta_returns_negative(self) -> None:
        calc = RateCalculator()
        calc.calculate("switch1", "eth0", "octets_in", 1000, datetime(2024, 1, 15, 10, 0, 10, tzinfo=UTC))
        rate = calc.calculate("switch1", "eth0", "octets_in", 2000, datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC))
        assert rate == -1


class TestRateCalculatorClearState:
    def test_clear_state(self) -> None:
        calc = RateCalculator()
        ts1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        ts2 = datetime(2024, 1, 15, 10, 0, 10, tzinfo=UTC)
        ts3 = datetime(2024, 1, 15, 10, 0, 20, tzinfo=UTC)
        calc.calculate("switch1", "eth0", "octets_in", 1000, ts1)
        calc.calculate("switch1", "eth0", "octets_in", 2000, ts2)
        calc.clear_state("switch1", "eth0")
        rate = calc.calculate("switch1", "eth0", "octets_in", 3000, ts3)
        assert rate == -1

    def test_clear_state_does_not_affect_other_interfaces(self) -> None:
        calc = RateCalculator()
        ts1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        ts2 = datetime(2024, 1, 15, 10, 0, 10, tzinfo=UTC)
        calc.calculate("switch1", "eth0", "octets_in", 1000, ts1)
        calc.calculate("switch1", "eth1", "octets_in", 1000, ts1)
        calc.clear_state("switch1", "eth0")
        rate_eth0 = calc.calculate("switch1", "eth0", "octets_in", 2000, ts2)
        rate_eth1 = calc.calculate("switch1", "eth1", "octets_in", 2000, ts2)
        assert rate_eth0 == -1
        assert rate_eth1 == 100.0

    def test_clear_all(self) -> None:
        calc = RateCalculator()
        ts1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        ts2 = datetime(2024, 1, 15, 10, 0, 10, tzinfo=UTC)
        calc.calculate("switch1", "eth0", "octets_in", 1000, ts1)
        calc.calculate("switch2", "eth1", "octets_out", 2000, ts1)
        calc.clear_all()
        rate1 = calc.calculate("switch1", "eth0", "octets_in", 2000, ts2)
        rate2 = calc.calculate("switch2", "eth1", "octets_out", 4000, ts2)
        assert rate1 == -1
        assert rate2 == -1


class TestRateCalculatorThreadSafety:
    def test_thread_safety(self) -> None:
        calc = RateCalculator()
        errors: list[str] = []
        barrier = threading.Barrier(4)

        def worker(switch_name: str) -> None:
            barrier.wait()
            ts1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
            ts2 = datetime(2024, 1, 15, 10, 0, 10, tzinfo=UTC)
            rate1 = calc.calculate(switch_name, "eth0", "octets_in", 1000, ts1)
            if rate1 != -1:
                errors.append(f"{switch_name}: first poll should be -1, got {rate1}")
            rate2 = calc.calculate(switch_name, "eth0", "octets_in", 2000, ts2)
            if rate2 != 100.0:
                errors.append(f"{switch_name}: expected 100.0, got {rate2}")

        threads = [threading.Thread(target=worker, args=(f"switch{i}",)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert not errors, f"Thread safety errors: {errors}"
