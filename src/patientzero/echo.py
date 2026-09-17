"""Simhash-based echo detection: clusters near-duplicate title+snippet text so
syndicated/copy-paste coverage doesn't get counted as independent corroboration
(spec sec 4.2).
"""
import hashlib
import re

from patientzero.models import EchoCluster, SearchResult

DEFAULT_NUM_BITS = 64
SHINGLE_SIZE = 3


def _normalize(text: str) -> str:
    normalized = re.sub(r"[^\w\s]", "", text.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def _shingles(text: str, size: int = SHINGLE_SIZE) -> set[str]:
    normalized = _normalize(text)
    if len(normalized) < size:
        return {normalized} if normalized else set()
    return {normalized[i : i + size] for i in range(len(normalized) - size + 1)}


def simhash(text: str, num_bits: int = DEFAULT_NUM_BITS) -> int:
    shingles = _shingles(text)
    if not shingles:
        return 0

    bit_votes = [0] * num_bits
    for shingle in shingles:
        digest = hashlib.sha256(shingle.encode("utf-8")).digest()
        hash_int = int.from_bytes(digest, "big")
        for bit in range(num_bits):
            if (hash_int >> bit) & 1:
                bit_votes[bit] += 1
            else:
                bit_votes[bit] -= 1

    result = 0
    for bit in range(num_bits):
        if bit_votes[bit] > 0:
            result |= 1 << bit
    return result


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def cluster_results(
    results: list[SearchResult], distance_threshold: int = 3
) -> list[EchoCluster]:
    hashes = [simhash(f"{r.title} {r.snippet}") for r in results]
    n = len(results)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i in range(n):
        for j in range(i + 1, n):
            if hamming_distance(hashes[i], hashes[j]) <= distance_threshold:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(i)

    clusters = []
    for indices in groups.values():
        domains = {results[i].domain for i in indices}
        clusters.append(EchoCluster(result_indices=tuple(indices), domain_count=len(domains)))
    return clusters
