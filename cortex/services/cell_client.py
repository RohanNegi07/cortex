"""Wrapper around CELL integration utilities."""

from cortex.integrations.cell_api import (
    get_velocity_summary as _get_velocity_summary,
    push_tasks_to_cell as _push_tasks_to_cell,
    clear_velocity_cache as _clear_velocity_cache,
)


async def get_velocity_summary(*args, **kwargs):
    return await _get_velocity_summary(*args, **kwargs)


async def push_tasks_to_cell(*args, **kwargs):
    return await _push_tasks_to_cell(*args, **kwargs)


async def clear_velocity_cache(*args, **kwargs):
    return await _clear_velocity_cache(*args, **kwargs)
