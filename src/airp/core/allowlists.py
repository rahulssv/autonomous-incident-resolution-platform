from __future__ import annotations

from fnmatch import fnmatchcase


def is_namespace_allowed(namespace: str | None, allowlist: list[str] | tuple[str, ...]) -> bool:
    """Return whether a Kubernetes namespace is permitted for read-only evidence."""

    if namespace is None:
        return False
    patterns = _normalized_patterns(allowlist)
    if not patterns:
        return True
    candidate = namespace.strip().casefold()
    return any(pattern == "*" or fnmatchcase(candidate, pattern.casefold()) for pattern in patterns)


def is_github_repository_allowed(
    repository: str | None, allowlist: list[str] | tuple[str, ...]
) -> bool:
    """Return whether a GitHub repository URL or slug is permitted for read-only evidence."""

    normalized_repository = normalize_github_repository(repository)
    if normalized_repository is None:
        return False
    patterns = _normalized_repository_patterns(allowlist)
    if not patterns:
        return True
    candidate = normalized_repository.casefold()
    return any(pattern == "*" or fnmatchcase(candidate, pattern.casefold()) for pattern in patterns)


def normalize_github_repository(repository: str | None) -> str | None:
    if repository is None:
        return None
    value = repository.strip()
    if not value:
        return None

    if value.startswith("git@github.com:"):
        value = value.removeprefix("git@github.com:")
    elif "github.com/" in value:
        value = value.split("github.com/", 1)[1]

    if value.startswith("orgs/"):
        value = value.removeprefix("orgs/")
        if "/" not in value:
            return None
    value = value.removesuffix(".git").strip("/")
    parts = [part for part in value.split("/") if part]
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def _normalized_patterns(allowlist: list[str] | tuple[str, ...]) -> list[str]:
    return [item.strip() for item in allowlist if item and item.strip()]


def _normalized_repository_patterns(allowlist: list[str] | tuple[str, ...]) -> list[str]:
    patterns: list[str] = []
    for item in _normalized_patterns(allowlist):
        if item == "*":
            patterns.append(item)
            continue
        if "github.com/orgs/" in item:
            org = item.split("github.com/orgs/", 1)[1].strip("/")
            if org:
                patterns.append(f"{org}/*")
                continue
        normalized = normalize_github_repository(item)
        if normalized is not None:
            patterns.append(normalized)
            continue
        value = item.removesuffix(".git").strip("/")
        if "/" not in value:
            patterns.append(f"{value}/*")
        else:
            patterns.append(value)
    return patterns
