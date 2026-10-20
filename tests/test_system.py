import pytest

from juice_mate.sources.system import NetworkSpeed, _Rate, gpu_load


class Fake:
    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def __call__(self) -> float:
        return self.values.pop(0)


def test_rate_is_bytes_per_second_since_the_last_read() -> None:
    rate = _Rate(counter=Fake(1000, 3000, 3500), clock=Fake(10.0, 12.0, 12.5))  # type: ignore[arg-type]
    assert rate.per_second() == 1000
    assert rate.per_second() == 1000


def test_a_counter_reset_is_not_negative_traffic() -> None:
    rate = _Rate(counter=Fake(5000, 10), clock=Fake(0.0, 1.0))  # type: ignore[arg-type]
    assert rate.per_second() == 0


def test_zero_interval_does_not_divide_by_zero() -> None:
    rate = _Rate(counter=Fake(0, 100), clock=Fake(1.0, 1.0))  # type: ignore[arg-type]
    assert rate.per_second() == 0


def test_gpu_load_sums_processes_per_engine_and_takes_the_busiest() -> None:
    instances = {
        "pid_1_luid_0x0000_0x9C2A_phys_0_eng_0_engtype_3D": 20.0,
        "pid_2_luid_0x0000_0x9C2A_phys_0_eng_0_engtype_3D": 15.0,
        "pid_3_luid_0x0000_0x9C2A_phys_0_eng_1_engtype_3D": 30.0,
        "pid_3_luid_0x0000_0x9C2A_phys_0_eng_5_engtype_VideoDecode": 90.0,
    }
    assert gpu_load(instances) == 35.0


def test_gpu_load_is_capped_and_empty_is_zero() -> None:
    assert (
        gpu_load({"pid_1_luid_0x0_0x1_phys_0_eng_0_engtype_3D": 60, "pid_2_luid_0x0_0x1_phys_0_eng_0_engtype_3D": 70})
        == 100
    )
    assert gpu_load({}) == 0


def test_network_direction_is_checked() -> None:
    with pytest.raises(ValueError, match="direction"):
        NetworkSpeed("sideways")
