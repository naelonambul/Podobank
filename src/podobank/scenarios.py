"""Seeded synthetic transaction scenario generation."""

from __future__ import annotations

import random
from dataclasses import dataclass

SUPPORTED_SCENARIOS = frozenset({"baseline", "deposits", "withdrawals", "transfers"})


@dataclass(frozen=True)
class ScenarioOperation:
    operation_type: str
    amount_won: int
    source_index: int
    destination_index: int | None = None


@dataclass(frozen=True)
class GeneratedScenario:
    name: str
    count: int
    seed: int
    operations: tuple[ScenarioOperation, ...]


def generate_scenario(name: str, count: int, seed: int) -> GeneratedScenario:
    if name not in SUPPORTED_SCENARIOS:
        raise ValueError(f"Scenario '{name}' is not supported.")
    if count < 1 or count > 100:
        raise ValueError("Scenario count must be between 1 and 100.")
    if isinstance(seed, bool) or seed < 0:
        raise ValueError("Scenario seed must be a non-negative integer.")

    generator = random.Random(seed)
    operations: list[ScenarioOperation] = []
    for _ in range(count):
        operation_type = (
            generator.choice(("deposit", "withdrawal", "transfer"))
            if name == "baseline"
            else name[:-1]
            if name.endswith("s")
            else name
        )
        source_index = generator.randrange(2)
        amount_won = generator.randint(1_000, 25_000)
        destination_index = 1 - source_index if operation_type == "transfer" else None
        operations.append(
            ScenarioOperation(
                operation_type=operation_type,
                amount_won=amount_won,
                source_index=source_index,
                destination_index=destination_index,
            )
        )
    return GeneratedScenario(name=name, count=count, seed=seed, operations=tuple(operations))
