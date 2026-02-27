from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SwitchTarget:
    id: UUID
    hostname: str
    management_ip: str | None
    snmp_community: str | None


@dataclass(frozen=True, slots=True)
class PortTarget:
    id: UUID
    switch_id: UUID
    name: str
    speed: int
    member_id: UUID | None


@dataclass(frozen=True, slots=True)
class MemberIP:
    member_id: UUID
    member_name: str
    address: str
    af: int  # 4 o 6


@dataclass(slots=True)
class MonitoringTargets:
    switches: list[SwitchTarget] = field(default_factory=list)
    ports: list[PortTarget] = field(default_factory=list)
    member_ips: list[MemberIP] = field(default_factory=list)
