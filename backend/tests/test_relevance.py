import numpy as np

from app.services.embeddings import HashEmbedder, article_text, from_bytes, to_bytes
from app.services.relevance import cluster_events, profile_texts, relevance_scores


def unit(*values):
    v = np.array(values, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_relevance_is_max_over_profile():
    profile = np.stack([unit(1, 0, 0), unit(0, 1, 0)])
    articles = np.stack([unit(1, 0, 0), unit(0, 1, 0), unit(0, 0, 1), unit(1, 1, 0)])
    scores = relevance_scores(profile, articles)
    assert np.allclose(scores, [1.0, 1.0, 0.0, np.sqrt(0.5)], atol=1e-6)


def test_relevance_handles_empty():
    assert relevance_scores(np.stack([unit(1, 0)]), np.zeros((0, 2))).shape == (0,)


def test_profile_texts_dedupes():
    assert profile_texts("Crypto news", ["bitcoin", "Bitcoin ", "", "crypto news"]) == [
        "Crypto news",
        "bitcoin",
    ]


def test_cluster_complete_linkage():
    # a~b and b~c are similar, but a and c are not: complete linkage keeps c separate.
    a, b, c, d = unit(1, 0, 0), unit(0.9, 0.44, 0), unit(0.6, 0.8, 0), unit(0, 0, 1)
    vectors = np.stack([a, b, c, d])
    assert float(a @ b) > 0.85 and float(b @ c) > 0.85 and float(a @ c) < 0.85
    clusters = cluster_events(vectors, order=[0, 1, 2, 3], threshold=0.85)
    assert clusters == [[0, 1], [2], [3]]


def test_cluster_order_decides_leader():
    vectors = np.stack([unit(1, 0), unit(0.99, 0.1)])
    assert cluster_events(vectors, order=[1, 0], threshold=0.9) == [[1, 0]]
    assert cluster_events(vectors, order=[], threshold=0.9) == []


def test_hash_embedder_similarity_and_roundtrip():
    emb = HashEmbedder()
    v = emb.embed(
        [
            "Bitcoin price climbs above record",
            "Bitcoin price climbs to new record",
            "Pumpkin soup recipe for autumn",
        ]
    )
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0)
    assert float(v[0] @ v[1]) > float(v[0] @ v[2])
    assert np.array_equal(from_bytes(to_bytes(v[0])), v[0])


def test_article_text():
    assert article_text("Title", None) == "Title"
    assert article_text("Title", "Snippet") == "Title. Snippet"
