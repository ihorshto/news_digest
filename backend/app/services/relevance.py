"""Relevance scoring and event clustering on normalized embeddings."""

import numpy as np


def cluster_events(vectors: np.ndarray, order: list[int], threshold: float) -> list[list[int]]:
    """Group articles into events with complete linkage.

    An article joins an existing cluster only if its similarity to *every* member is
    at least `threshold` (mutual similarity), so a chain of loosely related stories
    never collapses into one event. `order` (e.g. by relevance, best first) decides
    which article leads each cluster. Returns clusters as lists of indices.
    """
    if len(order) == 0:
        return []
    sims = vectors @ vectors.T
    clusters: list[list[int]] = []
    for idx in order:
        for cluster in clusters:
            if all(sims[idx, member] >= threshold for member in cluster):
                cluster.append(idx)
                break
        else:
            clusters.append([idx])
    return clusters


def profile_texts(description: str, queries: list[str]) -> list[str]:
    """Texts that describe the topic: the description plus its search queries.

    Short queries match headlines much better than a long description does
    (see DECISIONS.md: calibration), so relevance is the best match over all of them.
    """
    seen: set[str] = set()
    texts = []
    for text in [description, *queries]:
        key = text.strip().lower()
        if key and key not in seen:
            seen.add(key)
            texts.append(text.strip())
    return texts


def relevance_scores(profile_vectors: np.ndarray, article_vectors: np.ndarray) -> np.ndarray:
    """Max cosine similarity of each article to any profile vector."""
    if len(article_vectors) == 0 or len(profile_vectors) == 0:
        return np.zeros(len(article_vectors), dtype=np.float32)
    return (article_vectors @ profile_vectors.T).max(axis=1)
