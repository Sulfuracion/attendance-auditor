"""Unit test verifying that the seed script executes idempotently."""

import pytest

from scripts.seed_local import seed


@pytest.mark.asyncio
async def test_seed_script_idempotency() -> None:
    """Validate that executing seed routine multiple times is safe and idempotent."""
    # First execution
    await seed()
    # Second execution should recognize existing entities without crashing
    await seed()
