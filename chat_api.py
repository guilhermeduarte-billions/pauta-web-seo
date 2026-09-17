from __future__ import annotations


def normalize_space(space: str) -> str:
    return space if space.startswith("spaces/") else f"spaces/{space}"


def get_space(service, space: str) -> dict:
    return service.spaces().get(name=normalize_space(space)).execute()
